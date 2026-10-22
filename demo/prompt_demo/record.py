"""Records the "dictate a prompt + Copy Path" demo from the host.

    python demo/prompt_demo/record.py OUT_DIR SAY1_SECONDS SAY2_SECONDS

Expects the VM desktop prepared by scene.ps1 (prompt window in front,
Explorer on the sales folder behind it, prompt-expert running with the two
demo WAVs as its microphone). Writes OUT_DIR/frames/*.png + timeline.json.
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vmctl import RIGHT, VM  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FPS = 12

# Screen positions on the 1024x768 VM (see scene.ps1 for the window layout).
PROMPT_BOX = (330, 400)
PROMPT_END = (330, 470)  # inside the box, below the text: caret goes to the end
EXPLORER_TAB = (940, 300)
SALES_FILE = (860, 525)  # "2026 3분기 지역별 매출.xlsx"
SHOW_MORE = (598, 500)
COPY_PATH = (750, 247)
RECENT_PATHS = (760, 303)


def transcribed_count():
    out = subprocess.run(
        [str(ROOT / "vm" / "vm.sh"), "ssh",
         r"(Select-String -Path $env:APPDATA\prompt-expert\prompt-expert.log -Pattern 'transcribed').Count"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    try:
        return int(out.stdout.strip() or 0)
    except ValueError:
        return -1


def main():
    out = Path(sys.argv[1])
    say1, say2 = float(sys.argv[2]), float(sys.argv[3])
    (out / "frames").mkdir(parents=True, exist_ok=True)
    vm = VM()
    stop = threading.Event()
    frame_times = []

    def capture():
        n = 0
        while not stop.is_set():
            started = time.time()
            vm.shot(str(out / "frames" / f"{n:05d}.png"))
            frame_times.append(round(started - vm.t0, 3))
            n += 1
            time.sleep(max(0, 1 / FPS - (time.time() - started)))

    def wait_transcribed(expected, timeout=300):
        end = time.time() + timeout
        while time.time() < end and transcribed_count() < expected:
            time.sleep(1.0)

    baseline = transcribed_count()
    vm.move(512, 700, 0.01)
    thread = threading.Thread(target=capture, daemon=True)
    thread.start()

    vm.mark("start")
    time.sleep(2.5)
    vm.mark("focus")
    vm.click(*PROMPT_BOX, duration=1.0)
    time.sleep(3.5)

    vm.mark("hold1_start")
    vm.hold("alt", (say1 + 0.8) * 1000)
    time.sleep(say1 + 0.8)
    vm.mark("hold1_end")
    wait_transcribed(baseline + 1)
    vm.mark("text1")
    time.sleep(2.5)
    vm.keys("ret")

    vm.mark("explorer")
    vm.click(*EXPLORER_TAB, duration=0.9)
    time.sleep(1.2)
    vm.click(*SALES_FILE, button=RIGHT, duration=0.8)
    vm.mark("menu1")
    time.sleep(1.8)
    vm.click(*SHOW_MORE, duration=0.7)
    vm.mark("menu2")
    time.sleep(1.5)
    vm.move(*COPY_PATH, 0.7)
    time.sleep(0.8)
    vm.click()
    vm.mark("copied")
    time.sleep(1.5)

    vm.mark("back")
    vm.click(*PROMPT_END, duration=1.0)
    time.sleep(1.0)
    vm.keys("ctrl-v")
    vm.mark("pasted")
    time.sleep(3.0)
    vm.keys("ret")
    time.sleep(0.8)

    vm.mark("hold2_start")
    vm.hold("alt", (say2 + 0.8) * 1000)
    time.sleep(say2 + 0.8)
    vm.mark("hold2_end")
    wait_transcribed(baseline + 2)
    vm.mark("text2")
    time.sleep(3.5)

    vm.mark("recent")
    vm.click(*EXPLORER_TAB, duration=0.9)
    time.sleep(1.0)
    vm.click(*SALES_FILE, button=RIGHT, duration=0.8)
    time.sleep(1.6)
    vm.click(*SHOW_MORE, duration=0.7)
    time.sleep(1.3)
    vm.move(*RECENT_PATHS, 0.7)
    vm.mark("recent_open")
    time.sleep(4.5)
    vm.keys("esc", "esc", "esc")
    vm.mark("final")
    vm.click(330, 40, duration=0.8)  # prompt window to the front
    time.sleep(3.5)
    vm.mark("end")

    stop.set()
    thread.join()
    (out / "timeline.json").write_text(json.dumps(
        {"events": vm.events, "frames": frame_times, "cursor": vm.cursor_log}, indent=1))


if __name__ == "__main__":
    main()
