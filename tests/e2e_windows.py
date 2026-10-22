"""End-to-end test on a real Windows desktop session.

Starts prompt-expert with a WAV file standing in for the microphone, presses and
holds the real Alt key through SendInput (so it goes through the low-level
hook like a physical key), and checks what lands in a focused text box and in
Notepad. Must run inside the logged-on user's desktop, not a service/SSH
session.

    python tests\\e2e_windows.py --case ko --model small
"""

import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from winwhisper import APP_NAME, win32  # noqa: E402
from winwhisper.config import app_dir  # noqa: E402

user32 = win32.user32
user32.FindWindowW.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = win32.LRESULT
VK_LMENU = 0xA4
SENTINEL_CLIP = "ORIGINAL-CLIPBOARD-이전내용"
CASES = {
    "ko": ("ko_hello.wav", ["윈도우", "테스트"]),
    "en": ("en_hello.wav", ["Windows", "test"]),
}


def key(vk, up=False):
    item = win32.INPUT(type=win32.INPUT_KEYBOARD)
    scan = user32.MapVirtualKeyW(vk, 0)
    item.ki = win32.KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=win32.KEYEVENTF_KEYUP if up else 0,
                               time=0, dwExtraInfo=0)  # untagged: the hook must see it
    return item


def hold_alt(seconds):
    win32.send_inputs([key(VK_LMENU)])
    end = time.time() + seconds
    while time.time() < end:  # physical keys auto-repeat while held
        time.sleep(0.05)
        win32.send_inputs([key(VK_LMENU)])
    win32.send_inputs([key(VK_LMENU, up=True)])


def wait_for(predicate, timeout, interval=0.25):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def foreground_title():
    hwnd = user32.GetForegroundWindow()
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buffer, 256)
    return buffer.value


def find_child_text(top_class, child_classes):
    top = user32.FindWindowW(top_class, None)
    if not top:
        return None
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, name, 128)
        if name.value in child_classes:
            found.append(hwnd)
        return True

    user32.EnumChildWindows(top, enum_proc(visit), 0)
    for hwnd in found:
        length = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.SendMessageW(hwnd, 0x000D, length + 1, ctypes.addressof(buffer))  # WM_GETTEXT
        if buffer.value:
            return buffer.value
    return ""


class AppProcess:
    """The app under test; a windowed exe has no stdout, so also watch its log file."""

    def __init__(self, wav, model, workdir, exe=None):
        config = Path(workdir) / "config.json"
        config.write_text(json.dumps({"model": model, "language": "auto"}), encoding="utf-8")
        self.lines = []
        self.log_file = app_dir() / f"{APP_NAME}.log"
        self.log_offset = self.log_file.stat().st_size if self.log_file.exists() else 0
        command = [exe] if exe else [sys.executable, "-m", "winwhisper"]
        self.proc = subprocess.Popen(
            command + ["--no-tray", "--test-audio", str(wav), "--config", str(config)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace")
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def log_lines(self):
        if not self.log_file.exists():
            return []
        with open(self.log_file, "rb") as log:
            log.seek(self.log_offset)
            return log.read().decode("utf-8", "replace").splitlines()

    def saw(self, needle):
        return any(needle in line for line in self.lines + self.log_lines())

    def stop(self):
        self.proc.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), default="ko")
    parser.add_argument("--wav", help="override the case's WAV file")
    parser.add_argument("--expect", action="append", help="override the case's expected words")
    parser.add_argument("--model", default="small")
    parser.add_argument("--result", default=str(ROOT / "e2e-result.json"))
    parser.add_argument("--app-exe", help="test a built prompt-expert.exe instead of the source tree")
    parser.add_argument("--skip-notepad", action="store_true")
    args = parser.parse_args()
    case_wav, case_expect = CASES[args.case]
    args.wav = args.wav or str(ROOT / "tests" / "fixtures" / case_wav)
    args.expect = args.expect or case_expect

    results = {"checks": {}, "log": []}
    check = results["checks"]
    work = Path(tempfile.mkdtemp(prefix="winwhisper-e2e-"))
    mirror = work / "target.txt"
    previous_clipboard = win32.get_clipboard_text()
    win32.set_clipboard_text(SENTINEL_CLIP, keep_out_of_history=False)

    app = AppProcess(Path(args.wav).resolve(), args.model, work, args.app_exe)
    target = subprocess.Popen([sys.executable, str(ROOT / "tests" / "target_window.py"), str(mirror)])
    notepad = None
    try:
        check["model_loaded"] = bool(wait_for(lambda: app.saw("model ready"), 900, 1))
        wait_for(lambda: foreground_title() == "prompt-expert E2E target", 15)
        check["target_focused"] = foreground_title() == "prompt-expert E2E target"
        if not check["model_loaded"] or not check["target_focused"]:
            raise RuntimeError("Model or test window is not ready; refusing to send keys")

        # 1. a quick tap of Alt must not dictate anything
        hold_alt(0.1)
        time.sleep(3)
        check["tap_ignored"] = mirror.read_text(encoding="utf-8") == "" and not app.saw("transcribed")

        # 2. hold Alt ~1.5 s: the WAV is "spoken", transcribed and pasted
        started = time.time()
        hold_alt(1.5)
        overlay = user32.FindWindowW("PromptExpertOverlay", None)
        check["overlay_shown"] = bool(overlay) and bool(user32.IsWindowVisible(overlay))
        text = wait_for(lambda: mirror.read_text(encoding="utf-8").strip(), 300)
        results["target_text"] = text
        keys = Path(str(mirror) + ".keys")
        results["target_keys"] = keys.read_text(encoding="utf-8").splitlines() if keys.exists() else []
        results["latency_seconds"] = round(time.time() - started, 1)
        check["text_inserted"] = bool(text)
        check["expected_words"] = all(word in text for word in args.expect)
        check["focus_kept_after_alt"] = foreground_title() == "prompt-expert E2E target"
        time.sleep(1)
        check["clipboard_restored"] = win32.get_clipboard_text() == SENTINEL_CLIP

        # 3. same thing into Notepad, whose menu bar Alt would normally activate
        if not args.skip_notepad:
            target.kill()
            notepad = subprocess.Popen(["notepad.exe"])
            wait_for(lambda: user32.FindWindowW("Notepad", None), 20)
            time.sleep(2)
            hwnd = user32.FindWindowW("Notepad", None)
            user32.SetForegroundWindow(hwnd)
            time.sleep(1)
            hold_alt(1.5)
            notepad_text = wait_for(lambda: find_child_text("Notepad", {"RichEditD2DPT", "Edit"}), 300)
            results["notepad_text"] = notepad_text
            check["notepad_inserted"] = bool(notepad_text) and all(w in notepad_text for w in args.expect)
    finally:
        results["log"] = (app.lines or app.log_lines())[-40:]
        app.stop()
        for proc in (target, notepad):
            if proc:
                proc.kill()
        if previous_clipboard is not None:
            win32.set_clipboard_text(previous_clipboard)
        results["passed"] = all(check.values())
        Path(args.result).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if results["passed"] else 1)


if __name__ == "__main__":
    main()
