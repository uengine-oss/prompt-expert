"""Floating recording indicator, in the spirit of MacWhisper's: a small pill at
the bottom of the active monitor with a live level waveform while recording
and a pulsing "받아쓰는 중" while transcribing.

Frames are drawn with Pillow and pushed to a per-pixel-alpha layered window,
so edges stay smooth. The window never activates and lets clicks through, so
the app being dictated into keeps focus.
"""

import collections
import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes

import numpy as np

from .overlay_painter import BARS, Painter, level_to_unit
from .win32 import kernel32, user32

log = logging.getLogger(__name__)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shcore = ctypes.WinDLL("shcore")

FPS = 30

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x80000, 0x20, 0x8
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
ULW_ALPHA, AC_SRC_ALPHA = 0x2, 0x1
PM_REMOVE = 0x1

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
user32.CreateWindowExW.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT)
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.GetDC.argtypes = (wintypes.HWND,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
shcore.GetDpiForMonitor.argtypes = (wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(wintypes.UINT),
                                    ctypes.POINTER(wintypes.UINT))


class Overlay:
    def __init__(self, level_source):
        """level_source() returns the current input RMS (0..1 amplitude)."""
        self.level_source = level_source
        self._commands = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
        self._thread.start()

    def show_recording(self):
        self._commands.put("recording")

    def show_busy(self):
        self._commands.put("busy")

    def show_loading(self):
        self._commands.put("loading")

    def hide(self):
        self._commands.put("hide")

    # -- window thread -------------------------------------------------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _create_window(self):
        self._proc = WNDPROC(self._wndproc)
        hinstance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinstance, lpszClassName="PromptExpertOverlay")
        user32.RegisterClassW(ctypes.byref(wc))
        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        return user32.CreateWindowExW(ex, "PromptExpertOverlay", "prompt-expert", WS_POPUP,
                                      0, 0, 1, 1, None, None, hinstance, None)

    def _placement(self):
        monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        dpi_x, dpi_y = wintypes.UINT(96), wintypes.UINT(96)
        try:
            shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        except OSError:
            pass
        return info.rcWork, dpi_x.value / 96

    def _push(self, hwnd, image, x, y, alpha):
        w, h = image.size
        rgba = np.asarray(image, dtype=np.uint16)
        premultiplied = (rgba[:, :, :3] * rgba[:, :, 3:4] // 255).astype(np.uint8)
        bgra = np.dstack([premultiplied[:, :, ::-1], rgba[:, :, 3].astype(np.uint8)])
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h,
                                  biPlanes=1, biBitCount=32, biCompression=0)
        screen = user32.GetDC(None)
        memdc = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(memdc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, np.ascontiguousarray(bgra).ctypes.data, w * h * 4)
        old = gdi32.SelectObject(memdc, bitmap)
        blend = BLENDFUNCTION(0, 0, max(0, min(255, int(alpha * 255))), AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(x, y)), ctypes.byref(wintypes.SIZE(w, h)),
                                   memdc, ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
        gdi32.SelectObject(memdc, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(None, screen)

    def _run(self):
        try:
            hwnd = self._create_window()
        except Exception:
            log.exception("overlay unavailable")
            return
        msg = wintypes.MSG()
        painter, mode, target, alpha = None, None, 0.0, 0.0
        levels = collections.deque([0.0] * BARS, maxlen=BARS)
        smoothed, started, x, y = 0.0, 0.0, 0, 0
        visible = False
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            try:
                while True:
                    command = self._commands.get_nowait()
                    if command == "hide":
                        target = 0.0
                        continue
                    if command == "recording" or mode is None or alpha == 0:
                        work, scale = self._placement()
                        if painter is None or painter.scale != scale:
                            painter = Painter(scale)
                        w, h = painter.size
                        x = (work.left + work.right - w) // 2
                        y = work.bottom - h - round(28 * scale)
                    if command != mode or alpha == 0:
                        started = time.monotonic()
                    if command == "recording":
                        levels.extend([0.0] * BARS)
                    mode, target = command, 1.0
            except queue.Empty:
                pass

            alpha += (target - alpha) * 0.35 if abs(target - alpha) > 0.02 else (target - alpha)
            if alpha > 0 and painter is not None:
                if mode == "recording":
                    value = level_to_unit(self.level_source())
                    smoothed = max(value, smoothed * 0.6 + value * 0.4)
                    levels.append(smoothed)
                now = time.monotonic()
                self._push(hwnd, painter.frame(mode, now, list(levels), now - started), x, y, alpha)
                if not visible:
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
                    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                    visible = True
            elif visible:
                user32.ShowWindow(hwnd, SW_HIDE)
                visible = False
            time.sleep(1 / FPS if visible else 0.03)
