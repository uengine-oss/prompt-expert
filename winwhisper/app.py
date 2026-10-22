"""Wires the hotkey, microphone, Whisper and text insertion together."""

import logging
import math
import os
import queue
import struct
import threading
import time
import wave

from . import APP_NAME, pathmenu, win32
from .audio import FileRecorder, Recorder
from .config import app_dir, config_path, update_config
from .hotkey import HoldDetector, HoldListener, parse_hotkey
from .transcriber import Transcriber

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _tone_file(name, freqs, duration=0.07):
    path = app_dir() / f"{name}.wav"
    if not path.exists():
        rate = 22050
        frames = bytearray()
        for freq in freqs:
            count = int(rate * duration)
            for i in range(count):
                fade = min(1.0, i / 200, (count - i) / 200)
                frames += struct.pack("<h", int(9000 * fade * math.sin(2 * math.pi * freq * i / rate)))
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(bytes(frames))
    return str(path)


class Sounds:
    def __init__(self, enabled):
        self.enabled = enabled
        self.start_file = _tone_file("start", [660, 880]) if enabled else None
        self.stop_file = _tone_file("stop", [880, 660]) if enabled else None

    def _play(self, path):
        if path:
            import winsound
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except RuntimeError:  # no output device; feedback is optional
                pass

    def start(self):
        self._play(self.start_file)

    def stop(self):
        self._play(self.stop_file)


class Inserter:
    def __init__(self, method="clipboard", restore_clipboard=True):
        self.method = method
        self.restore_clipboard = restore_clipboard

    def insert(self, text):
        if win32.foreground_in_menu_mode():
            log.info("target window is in menu mode; leaving it before inserting")
            win32.leave_menu_mode()
        if self.method == "type":
            win32.type_unicode(text)
            return
        previous = win32.get_clipboard_text() if self.restore_clipboard else None
        win32.set_clipboard_text(text)
        time.sleep(0.03)
        win32.press_ctrl_v()
        if previous is not None:
            time.sleep(0.4)  # let the target app read the clipboard first
            win32.set_clipboard_text(previous)


class DictationApp(HoldListener):
    def __init__(self, config, test_audio=None, on_text=None, config_file=None):
        self.config = config
        self.config_file = config_file
        self.recorder = FileRecorder(test_audio) if test_audio else Recorder(
            device=config["input_device"], max_seconds=config["max_record_seconds"])
        self.transcriber = Transcriber(
            model=config["model"], device=config["device"], compute_type=config["compute_type"],
            language=config["language"], initial_prompt=config["initial_prompt"])
        self.inserter = Inserter(config["paste_method"], config["restore_clipboard"])
        self.sounds = Sounds(config["sounds"])
        self.detector = HoldDetector(parse_hotkey(config["hotkey"]), config["min_hold_seconds"], self)
        self.hook = win32.KeyboardHook(self.detector.on_key)
        self.on_text = on_text
        self.tray = None
        self.overlay = None
        if config["overlay"]:
            self.set_overlay(True)
        # Recorder control and transcription each get one worker so the hook
        # thread never blocks and pastes keep the order they were spoken in.
        self._control = queue.Queue()
        self._jobs = queue.Queue()
        self._recording = False

    def set_overlay(self, enabled):
        if enabled and self.overlay is None:
            from .overlay import Overlay
            self.overlay = Overlay(lambda: self.recorder.level)
        elif not enabled and self.overlay is not None:
            self.overlay.hide()
            self.overlay = None
        self.config["overlay"] = enabled

    def _show(self, state):
        overlay = self.overlay
        if overlay:
            {"recording": overlay.show_recording, "busy": overlay.show_busy,
             "loading": overlay.show_loading, "idle": overlay.hide}[state]()

    # HoldListener: called from the hook/timer threads, so only enqueue.
    def started(self):
        self._control.put("start")

    def confirmed(self):
        self._control.put("confirm")

    def cancelled(self):
        self._control.put("cancel")

    def finished(self):
        self._control.put("finish")

    def _control_loop(self):
        while True:
            command = self._control.get()
            try:
                if command == "start":
                    self.recorder.start()
                    self._recording = True
                elif command == "confirm":
                    win32.tap_mask_key()
                    self.sounds.start()
                    self._set_status("recording")
                    self._show("recording")
                elif command in ("cancel", "finish") and self._recording:
                    samples = self.recorder.stop()
                    self._recording = False
                    if command == "finish":
                        self.sounds.stop()
                        self._set_status("busy")
                        self._show("busy")
                        self._jobs.put(samples)
                    else:
                        self._set_status("idle")
                        self._show("idle")
            except Exception:
                log.exception("control command %s failed", command)
                self._recording = False
                self._set_status("idle")
                self._show("idle")

    def _job_loop(self):
        while True:
            samples = self._jobs.get()
            try:
                if self.transcriber.model is None:
                    # First run downloads the model; say so instead of looking stuck.
                    log.info("dictation waiting for the model to finish loading")
                    self._show("loading")
                    self.transcriber.load()
                    self._show("busy")
                started = time.perf_counter()
                text = self.transcriber.transcribe(samples)
                log.info("transcribed %.1fs of audio in %.1fs: %r",
                         len(samples) / 16000, time.perf_counter() - started, text)
                if text:
                    self.inserter.insert(text)
                    if self.on_text:
                        self.on_text(text)
            except Exception:
                log.exception("transcription failed")
            if self._jobs.empty():
                self._show("idle")
                self._set_status("idle" if self.transcriber.model else "loading")

    def _load_model(self):
        self._set_status("loading")
        try:
            self.transcriber.load()
            self._set_status("idle")
        except Exception:
            log.exception("could not load model")
            self._set_status("error")

    def _set_status(self, status):
        if self.tray:
            self.tray.set_status(status)

    def start(self):
        for target in (self._control_loop, self._job_loop, self._load_model):
            threading.Thread(target=target, daemon=True).start()
        self.hook.start()
        log.info("listening; hold %s to dictate", self.config["hotkey"])

    def stop(self):
        self.hook.stop()


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enabled, command):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


class Tray:
    COLORS = {"idle": (90, 160, 255), "recording": (230, 60, 60), "busy": (240, 180, 40),
              "loading": (150, 150, 150), "error": (120, 0, 0)}
    LABELS = {"idle": "대기 중", "recording": "녹음 중", "busy": "받아쓰는 중",
              "loading": "모델 불러오는 중", "error": "오류 (로그 확인)"}

    def __init__(self, app, launch_command):
        import pystray

        self.app = app
        self.launch_command = launch_command
        self.icon = pystray.Icon(APP_NAME, self._image("loading"), self._title("loading"), menu=pystray.Menu(
            pystray.MenuItem(lambda item: f"모델: {app.transcriber.model_name}", None, enabled=False),
            pystray.MenuItem(lambda item: f"단축키: {app.config['hotkey']} 길게 누르기", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("설정 파일 열기", lambda: os.startfile(config_path())),
            pystray.MenuItem("로그 폴더 열기", lambda: os.startfile(app_dir())),
            pystray.MenuItem("Windows 시작 시 실행", self._toggle_autostart,
                             checked=lambda item: autostart_enabled()),
            pystray.MenuItem("녹음 애니메이션 표시", self._toggle_overlay,
                             checked=lambda item: bool(app.overlay)),
            pystray.MenuItem("탐색기 우클릭 메뉴 (Copy Path)", self._toggle_path_menu,
                             checked=lambda item: pathmenu.installed()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", self._quit),
        ))

    def _title(self, status):
        return f"{APP_NAME} – {self.LABELS[status]}"

    def _image(self, status):
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((4, 4, 60, 60), fill=self.COLORS[status])
        draw.rounded_rectangle((24, 14, 40, 38), radius=8, fill="white")  # microphone
        draw.arc((18, 24, 46, 46), 0, 180, fill="white", width=4)
        draw.line((32, 46, 32, 52), fill="white", width=4)
        return image

    def set_status(self, status):
        self.icon.icon = self._image(status)
        self.icon.title = self._title(status)

    def _toggle_autostart(self, icon, item):
        set_autostart(not autostart_enabled(), self.launch_command)

    def _toggle_overlay(self, icon, item):
        self.app.set_overlay(not self.app.overlay)
        update_config({"overlay": bool(self.app.overlay)}, self.app.config_file)

    def _toggle_path_menu(self, icon, item):
        pathmenu.uninstall() if pathmenu.installed() else pathmenu.install()

    def _quit(self, icon, item):
        self.app.stop()
        icon.stop()

    def run(self):
        self.icon.run()
