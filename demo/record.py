"""Records the usage demo from the host: drives the VM keyboard through the
QEMU monitor (so Alt is a real hardware key press) while grabbing frames.

    python demo/record.py OUT_DIR

Writes OUT_DIR/frames/NNNNN.png and OUT_DIR/timeline.json.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

VM = Path(os.environ.get("WINWHISPER_VM_DIR", Path.home() / "winwhisper-vm"))
VM_SH = Path(__file__).resolve().parent.parent / "vm" / "vm.sh"
FPS = 5


class Monitor:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.lock = threading.Lock()
        self._read_until_prompt()

    def _read_until_prompt(self):
        data = b""
        while not data.endswith(b"(qemu) "):
            data += self.sock.recv(65536)
        return data

    def cmd(self, line):
        with self.lock:
            self.sock.sendall(line.encode() + b"\n")
            return self._read_until_prompt()


KEYS = {" ": "spc", ":": "shift-semicolon", "\n": "ret", ".": "dot", ",": "comma", "-": "minus"}


def type_text(monitor, text, delay=0.09):
    for ch in text:
        if ch in KEYS:
            key = KEYS[ch]
        elif ch.isupper():
            key = "shift-" + ch.lower()
        else:
            key = ch
        monitor.cmd(f"sendkey {key}")
        time.sleep(delay)


def transcribed_count():
    out = subprocess.run(
        [str(VM_SH), "ssh", r"(Select-String -Path $env:APPDATA\WinWhisper\winwhisper.log -Pattern 'transcribed').Count"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    try:
        return int(out.stdout.strip() or 0)
    except ValueError:
        return -1


def main():
    out = Path(sys.argv[1])
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    monitor = Monitor(VM / "mon.sock")
    events = []
    t0 = time.time()
    stop = threading.Event()
    frame_times = []

    def mark(name):
        events.append({"name": name, "t": round(time.time() - t0, 2)})
        print(f"{events[-1]['t']:7.2f}s  {name}", flush=True)

    def capture():
        n = 0
        while not stop.is_set():
            started = time.time()
            path = frames / f"{n:05d}.png"
            monitor.cmd(f"screendump {path} -f png")
            frame_times.append(round(started - t0, 3))
            n += 1
            time.sleep(max(0, 1 / FPS - (time.time() - started)))

    baseline = transcribed_count()
    thread = threading.Thread(target=capture, daemon=True)
    thread.start()

    def wait_transcribed(expected, timeout=240):
        end = time.time() + timeout
        while time.time() < end and transcribed_count() < expected:
            time.sleep(1.5)

    mark("desktop")
    time.sleep(4)
    mark("open_notepad")
    monitor.cmd("sendkey meta_l-r")
    time.sleep(1.5)
    type_text(monitor, "notepad\n")
    time.sleep(3.5)
    mark("type_header")
    type_text(monitor, "Meeting notes:\n")
    time.sleep(1.5)

    mark("hold1_start")
    monitor.cmd("sendkey alt 6600")  # QEMU holds the key down for 6.6 s
    time.sleep(6.6)
    mark("hold1_end")
    wait_transcribed(baseline + 1)
    mark("text1")
    time.sleep(4)

    type_text(monitor, "\n")
    time.sleep(1)
    mark("hold2_start")
    monitor.cmd("sendkey alt 3600")
    time.sleep(3.6)
    mark("hold2_end")
    wait_transcribed(baseline + 2)
    mark("text2")
    time.sleep(5)
    mark("end")

    stop.set()
    thread.join()
    (out / "timeline.json").write_text(json.dumps({"events": events, "frames": frame_times}, indent=1))


if __name__ == "__main__":
    main()
