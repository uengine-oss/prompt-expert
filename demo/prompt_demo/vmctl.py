"""Drives the test VM through QEMU: smooth mouse moves and clicks (QMP
absolute pointer events), held keys and screen grabs (HMP monitor), while
logging the pointer path (ramfb frames do not include the cursor, so the
compositor draws it from this log)."""

import json
import os
import socket
import threading
import time
from pathlib import Path

VM_DIR = Path(os.environ.get("WINWHISPER_VM_DIR", Path.home() / "winwhisper-vm"))
SCREEN = (1024, 768)
LEFT, RIGHT = "left", "right"


class VM:
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(VM_DIR / "mon.sock"))
        self.lock = threading.Lock()
        self._read()
        self.qmp = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.qmp.connect(str(VM_DIR / "qmp.sock"))
        self.qmp_file = self.qmp.makefile("r")
        self.qmp_file.readline()  # greeting
        self._qmp("qmp_capabilities")
        self.t0 = time.time()
        self.pointer = (SCREEN[0] // 2, SCREEN[1] // 2)
        self.cursor_log = []  # (t, x, y, pressed)
        self.events = []

    def _read(self):
        data = b""
        while not data.endswith(b"(qemu) "):
            data += self.sock.recv(65536)

    def cmd(self, line):
        with self.lock:
            self.sock.sendall(line.encode() + b"\n")
            self._read()

    def _qmp(self, command, **arguments):
        self.qmp.sendall(json.dumps({"execute": command, "arguments": arguments}).encode() + b"\n")
        while True:
            reply = json.loads(self.qmp_file.readline())
            if "return" in reply or "error" in reply:
                if "error" in reply:
                    raise RuntimeError(reply["error"])
                return reply["return"]

    def _input(self, *events):
        self._qmp("input-send-event", events=list(events))

    def now(self):
        return round(time.time() - self.t0, 3)

    def mark(self, name):
        self.events.append({"name": name, "t": self.now()})
        print(f"{self.now():7.2f}s  {name}", flush=True)

    def _abs(self, x, y):
        self._input({"type": "abs", "data": {"axis": "x", "value": int(x * 32767 / (SCREEN[0] - 1))}},
                    {"type": "abs", "data": {"axis": "y", "value": int(y * 32767 / (SCREEN[1] - 1))}})
        self.pointer = (x, y)
        self.cursor_log.append((self.now(), x, y, 0))

    def move(self, x, y, duration=0.6):
        x0, y0 = self.pointer
        steps = max(1, int(duration * 40))
        for i in range(1, steps + 1):
            p = i / steps
            ease = p * p * (3 - 2 * p)
            self._abs(x0 + (x - x0) * ease, y0 + (y - y0) * ease)
            time.sleep(duration / steps)

    def click(self, x=None, y=None, button=LEFT, duration=0.6):
        if x is not None:
            self.move(x, y, duration)
        self.cursor_log.append((self.now(), *self.pointer, button))
        self._input({"type": "btn", "data": {"down": True, "button": button}})
        time.sleep(0.09)
        self._input({"type": "btn", "data": {"down": False, "button": button}})
        self.cursor_log.append((self.now(), *self.pointer, 0))

    def keys(self, *names, gap=0.15):
        for name in names:
            self.cmd(f"sendkey {name}")
            time.sleep(gap)

    def hold(self, key, ms):
        self.cmd(f"sendkey {key} {int(ms)}")  # QEMU releases it after ms

    def shot(self, path):
        self.cmd(f"screendump {path} -f png")
