"""Thin ctypes layer over the Win32 calls we need: low-level keyboard hook,
SendInput, the clipboard and a single-instance mutex."""

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Tag on every event we inject so our own hook can ignore it.
INJECT_TAG = 0x57575748  # "WWWH"

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL, VK_V = 0x11, 0x56
VK_MASK = 0xE8  # unassigned; used to stop a lone Alt release from opening menus
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


class KeyboardHook:
    """Runs a WH_KEYBOARD_LL hook on its own thread and reports (vk, is_down).

    The callback must return quickly; Windows silently drops slow hooks.
    """

    def __init__(self, callback):
        self.callback = callback
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._proc = HOOKPROC(self._hook_proc)  # keep a reference alive

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code == 0:
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if info.dwExtraInfo != INJECT_TAG:
                is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                try:
                    self.callback(info.vkCode, is_down)
                except Exception:  # never let an exception kill the hook
                    pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self._error = None if hook else ctypes.WinError(ctypes.get_last_error())
        self._ready.set()
        if not hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise self._error

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


def _key_input(vk=0, scan=0, flags=0):
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=INJECT_TAG)
    return item


def send_inputs(items):
    array = (INPUT * len(items))(*items)
    sent = user32.SendInput(len(items), array, ctypes.sizeof(INPUT))
    if sent != len(items):
        raise ctypes.WinError(ctypes.get_last_error())


def tap_mask_key():
    send_inputs([_key_input(VK_MASK), _key_input(VK_MASK, flags=KEYEVENTF_KEYUP)])


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


GUI_MENU_FLAGS = 0x4 | 0x8 | 0x10  # GUI_INMENUMODE | GUI_SYSTEMMENUMODE | GUI_POPUPMENUMODE
VK_ESCAPE = 0x1B
user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))


def foreground_in_menu_mode():
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(0, ctypes.byref(info)):  # 0 = foreground thread
        return False
    return bool(info.flags & GUI_MENU_FLAGS)


def leave_menu_mode():
    """A lone Alt tap puts the window in keyboard-menu mode, which would eat
    our Ctrl+V key-downs. Press Esc until the window is back to normal."""
    for _ in range(3):
        if not foreground_in_menu_mode():
            return
        send_inputs([_key_input(VK_ESCAPE), _key_input(VK_ESCAPE, flags=KEYEVENTF_KEYUP)])
        time.sleep(0.05)


def press_ctrl_v():
    send_inputs([
        _key_input(VK_CONTROL),
        _key_input(VK_V),
        _key_input(VK_V, flags=KEYEVENTF_KEYUP),
        _key_input(VK_CONTROL, flags=KEYEVENTF_KEYUP),
    ])


def foreground_window():
    return user32.GetForegroundWindow()


def wait_for_modifiers_released(timeout=5.0):
    deadline = time.monotonic() + timeout
    while any(user32.GetAsyncKeyState(vk) & 0x8000
              for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


def type_unicode(text):
    items = []
    data = text.replace("\r\n", "\n").replace("\n", "\r").encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        items.append(_key_input(scan=unit, flags=KEYEVENTF_UNICODE))
        items.append(_key_input(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    if items:
        send_inputs(items)


class _Clipboard:
    def __enter__(self):
        for _ in range(20):  # another app may hold it briefly
            if user32.OpenClipboard(None):
                return self
            time.sleep(0.025)
        raise ctypes.WinError(ctypes.get_last_error())

    def __exit__(self, *exc):
        user32.CloseClipboard()


def get_clipboard_text():
    with _Clipboard():
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)


def _global_bytes(data):
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def set_clipboard_text(text, keep_out_of_history=True):
    with _Clipboard():
        user32.EmptyClipboard()
        handle = _global_bytes((text + "\0").encode("utf-16-le"))
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        if keep_out_of_history:
            # Tells Win+V clipboard history and cloud sync to skip this entry.
            fmt = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
            user32.SetClipboardData(fmt, _global_bytes(b"\0"))


def enable_dpi_awareness():
    """Per-monitor DPI awareness, so the overlay is drawn crisp at its real size."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass


def claim_single_instance(name):
    handle = kernel32.CreateMutexW(None, False, name)
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    return handle, not already
