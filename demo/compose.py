"""Turns a demo/record.py capture into the narrated usage video (macOS: needs
`say` with the Yuna voice, ffmpeg, numpy and Pillow).

    python demo/compose.py CAPTURE_DIR OUT.mp4
"""

import json
import subprocess
import sys
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
W, H, FPS, RATE = 1280, 720, 30, 48000
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BG, PANEL, CARD = (15, 23, 42), (30, 41, 59), (51, 65, 85)
TEXT, MUTED = (248, 250, 252), (148, 163, 184)
BLUE, RED, AMBER = (59, 130, 246), (239, 68, 68), (245, 158, 11)
VM_BOX = (24, 16, 800, 600)  # x, y, w, h of the VM screen; subtitles go below it
TRAY_CROP = (498, 560, 588, 592)
STEPS = ["입력할 곳에 커서 두기", "Alt 누른 채 말하기", "Alt 떼기", "글자가 자동 입력됨"]


def font(size, weight="Regular"):
    index = {"Regular": 0, "Medium": 2, "SemiBold": 4, "Bold": 6}[weight]
    return _font(size, index)


@lru_cache(None)
def _font(size, index):
    return ImageFont.truetype(FONT, size, index=index)


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    return lines + [line]


# ---------------------------------------------------------------- audio

def tts(text, workdir, name):
    path = Path(workdir) / f"{name}.wav"
    subprocess.run(["say", "-v", "Yuna", "-r", "190", "-o", str(path),
                    "--data-format=LEI16@48000", text], check=True)
    return load_wav(path)


def load_wav(path):
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    if rate != RATE:
        x = np.arange(int(len(data) * RATE / rate)) * rate / RATE
        data = np.interp(x, np.arange(len(data)), data).astype(np.float32)
    return data


def tone(freqs, duration=0.07, volume=0.25):
    parts = []
    for f in freqs:
        t = np.arange(int(RATE * duration)) / RATE
        fade = np.minimum(1, np.minimum(t, duration - t) * 200)
        parts.append(volume * fade * np.sin(2 * np.pi * f * t))
    return np.concatenate(parts).astype(np.float32)


# ---------------------------------------------------------------- shots

class Shot:
    def __init__(self, kind, narration=None, duration=0, **opts):
        self.kind, self.narration, self.min_duration, self.opts = kind, narration, duration, opts


def build_shots(ev):
    e = {x["name"]: x["t"] for x in ev}

    def demo(a, b, speed=1.0, **opts):
        return Shot("demo", src=(e[a], e[b]), speed=speed, **opts)

    return [
        Shot("title", "윈위스퍼 사용법입니다. 알트 키를 누른 채 말하고 손을 떼면, 받아쓴 글자가 지금 커서가 있는 입력창에 바로 들어갑니다.", 3),
        Shot("install", "먼저 압축을 풀고 윈위스퍼 실행 파일을 실행하세요. 처음 실행할 때 음성 인식 모델을 한 번 내려받고, 트레이 아이콘이 파란색으로 바뀌면 준비가 끝납니다.", 3),
        _with(demo("desktop", "open_notepad", tray=True), "실행 중에는 작업 표시줄 오른쪽에 마이크 아이콘이 표시됩니다."),
        _with(demo("open_notepad", "hold1_start", step=0), "받아쓸 곳, 예를 들어 메모장을 열고 커서를 둡니다."),
        demo("hold1_start", "hold1_end", step=1, hold=True, speech="demo_ko.wav", tray=True,
             caption='Alt를 누른 채 말하는 중 — "내일 오전 열 시에 디자인 리뷰 회의가 있습니다. 개발팀과 마케팅팀 모두 참석해 주세요."'),
        _with(demo("hold1_end", "text1", speed=10, step=2, fast=True, tray=True), "알트 키를 떼면 받아쓰기가 시작되고,"),
        _with(demo("text1", "hold2_start", step=3), "잠시 후 커서 위치에 문장이 입력됩니다."),
        demo("hold2_start", "hold2_end", step=1, hold=True, speech="demo_en.wav", tray=True,
             caption='Alt를 누른 채 말하는 중 — "Please send me the final report by Friday afternoon."'),
        _with(demo("hold2_end", "text2", speed=8, step=2, fast=True, tray=True), "언어는 자동으로 감지되므로,"),
        _with(demo("text2", "end", step=3), "영어로 말해도 그대로 받아씁니다."),
        Shot("tips", "알트 키를 짧게 누르거나 알트 탭 같은 조합키를 쓸 때는 받아쓰기가 시작되지 않습니다. 단축키와 모델, 언어는 트레이 메뉴의 설정 파일에서 바꿀 수 있습니다.", 3),
        Shot("end", "음성은 모두 이 피씨 안에서 처리되며, 인터넷으로 전송되지 않습니다.", 3),
    ]


def _with(shot, narration):
    shot.narration = narration
    return shot


# ---------------------------------------------------------------- drawing

def card(kind):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if kind in ("title", "end"):
        d.rounded_rectangle((W / 2 - 46, 150, W / 2 + 46, 242), 46, fill=BLUE)
        mic(d, W / 2, 196, 1.4)
        title = "WinWhisper" if kind == "title" else "음성은 PC 안에서만 처리됩니다"
        sub = ("Alt를 누른 채 말하고, 떼면 입력창에 글자가 들어갑니다" if kind == "title"
               else "인터넷 전송 없음 · 모델은 처음 한 번만 다운로드")
        for text, fnt, y, color in ((title, font(64, "Bold"), 290, TEXT), (sub, font(30, "Medium"), 390, MUTED)):
            d.text((W / 2, y), text, font=fnt, fill=color, anchor="mt")
        if kind == "title":
            d.text((W / 2, 470), "Windows용 MacWhisper식 받아쓰기 · 사용법", font=font(24), fill=MUTED, anchor="mt")
        return img
    heading, items = {
        "install": ("설치와 실행", [
            ("1", "WinWhisper.zip 압축 풀기"),
            ("2", "WinWhisper.exe 실행 → 작업 표시줄에 마이크 아이콘"),
            ("3", "첫 실행 때 음성 인식 모델 자동 다운로드 (회색 아이콘)"),
            ("4", "아이콘이 파란색이 되면 준비 완료"),
        ]),
        "tips": ("알아두면 좋은 점", [
            ("•", "Alt를 짧게 탭하거나 Alt+Tab 같은 조합키는 받아쓰기 안 함"),
            ("•", "트레이 아이콘 우클릭 → 설정 파일 열기: hotkey · model · language"),
            ("•", "트레이 메뉴 \"Windows 시작 시 실행\"으로 자동 시작"),
            ("•", "받아쓴 뒤 원래 클립보드 내용은 그대로 복원"),
        ]),
    }[kind]
    d.text((120, 110), heading, font=font(52, "Bold"), fill=TEXT)
    y = 220
    for bullet, text in items:
        d.rounded_rectangle((120, y, 1160, y + 76), 16, fill=PANEL)
        d.text((160, y + 38), bullet, font=font(30, "Bold"), fill=BLUE, anchor="mm")
        d.text((200, y + 38), text, font=font(28, "Medium"), fill=TEXT, anchor="lm")
        y += 96
    return img


def mic(d, cx, cy, s, color="white"):
    d.rounded_rectangle((cx - 9 * s, cy - 24 * s, cx + 9 * s, cy + 6 * s), 9 * s, fill=color)
    d.arc((cx - 16 * s, cy - 12 * s, cx + 16 * s, cy + 16 * s), 0, 180, fill=color, width=int(4 * s))
    d.line((cx, cy + 16 * s, cx, cy + 24 * s), fill=color, width=int(4 * s))


@lru_cache(maxsize=64)
def source_frame(path):
    return Image.open(path).convert("RGB")


def demo_frame(src, shot, local_t, subtitle):
    img = Image.new("RGB", (W, H), BG)
    x, y, w, h = VM_BOX
    img.paste(src if src.size == (w, h) else src.resize((w, h), Image.LANCZOS), (x, y))
    d = ImageDraw.Draw(img, "RGBA")
    opts = shot.opts

    # right panel
    px = x + w + 24
    d.text((px, y + 4), "WinWhisper", font=font(32, "Bold"), fill=TEXT)
    d.text((px, y + 48), "Alt 길게 눌러 받아쓰기", font=font(18, "Medium"), fill=MUTED)
    sy = y + 96
    for i, label in enumerate(STEPS):
        active = opts.get("step") == i
        d.rounded_rectangle((px, sy, W - 24, sy + 48), 12, fill=BLUE if active else PANEL)
        d.text((px + 18, sy + 24), str(i + 1), font=font(20, "Bold"), fill=TEXT if active else MUTED, anchor="lm")
        d.text((px + 46, sy + 24), label, font=font(19, "Medium" if active else "Regular"),
               fill=TEXT if active else MUTED, anchor="lm")
        sy += 58

    # Alt keycap
    ky = sy + 18
    pressed = opts.get("hold")
    off = 6 if pressed else 0
    d.rounded_rectangle((px + 4, ky + 10, px + 124, ky + 96), 14, fill=(10, 14, 26))
    d.rounded_rectangle((px, ky + off, px + 120, ky + 86 + off), 14, fill=RED if pressed else CARD)
    d.text((px + 60, ky + 43 + off), "Alt", font=font(34, "Bold"), fill=TEXT, anchor="mm")
    status = (f"누르고 있는 중  {local_t:0.1f}초" if pressed else "손 뗌" if opts.get("step") in (2, 3) else "")
    d.text((px + 140, ky + 44), status, font=font(19, "Medium"), fill=RED if pressed else MUTED, anchor="lm")

    # tray zoom
    ty = ky + 120
    d.text((px, ty), "트레이 아이콘 (확대)", font=font(17, "Medium"), fill=MUTED)
    crop = src.crop(TRAY_CROP).resize((270, 96), Image.LANCZOS)
    img.paste(crop, (px, ty + 28))
    d.rounded_rectangle((px - 2, ty + 26, px + 272, ty + 126), 8, outline=BLUE if opts.get("tray") else CARD, width=3)
    lx = px
    for color, label in ((BLUE, "대기"), (RED, "녹음"), (AMBER, "받아쓰기")):
        d.ellipse((lx, ty + 142, lx + 14, ty + 156), fill=color)
        d.text((lx + 20, ty + 149), label, font=font(16), fill=MUTED, anchor="lm")
        lx += 86

    if opts.get("fast"):
        badge = f"{opts['speed']:g}배속 재생 · 테스트 VM이라 느림 (일반 PC는 몇 초)"
        bw = d.textlength(badge, font=font(18, "Medium")) + 32
        d.rounded_rectangle((x + w - bw - 12, y + 12, x + w - 12, y + 50), 19, fill=(245, 158, 11, 235))
        d.text((x + w - 12 - bw / 2, y + 31), badge, font=font(18, "Medium"), fill=(20, 20, 20), anchor="mm")

    if subtitle:
        fnt = font(23, "Medium")
        lines = wrap(d, subtitle, fnt, w - 40)
        top = y + h + 14 + (32 if len(lines) == 1 else 0) // 2
        for i, line in enumerate(lines[:3]):
            d.text((x + w / 2, top + 32 * i), line, font=fnt, fill=TEXT, anchor="mt")
    return img


def card_frame(base, subtitle):
    if not subtitle:
        return base
    img = base.copy()
    d = ImageDraw.Draw(img, "RGBA")
    fnt = font(25, "Medium")
    lines = wrap(d, subtitle, fnt, W - 240)
    bh = 20 + 36 * len(lines)
    d.rounded_rectangle((100, H - bh - 40, W - 100, H - 40), 14, fill=(0, 0, 0, 160))
    for i, line in enumerate(lines):
        d.text((W / 2, H - bh - 30 + 18 + 36 * i), line, font=fnt, fill=TEXT, anchor="mt")
    return img


# ---------------------------------------------------------------- main

def main():
    capture, out = Path(sys.argv[1]), Path(sys.argv[2])
    timeline = json.loads((capture / "timeline.json").read_text())
    frame_times = np.array(timeline["frames"])
    frames = sorted((capture / "frames").glob("*.png"))
    shots = build_shots(timeline["events"])
    work = tempfile.mkdtemp(prefix="winwhisper-video-")

    # lay out the shots in output time; narration decides how long each runs
    t = 0.0
    audio_parts = []
    for i, shot in enumerate(shots):
        voice = tts(shot.narration, work, f"n{i}") if shot.narration else None
        need = len(voice) / RATE + 0.6 if voice is not None else 0
        if shot.kind == "demo":
            a, b = shot.opts["src"]
            natural = (b - a) / shot.opts["speed"]
            if shot.opts["speed"] > 1 and need > natural:
                shot.opts["speed"] = (b - a) / need  # slow the fast-forward instead of freezing
                natural = need
            shot.duration = max(natural, need)
        else:
            shot.duration = max(shot.min_duration, need + 0.4)
        shot.start = t
        if voice is not None:
            audio_parts.append((t + 0.25, voice))
        if shot.opts.get("hold"):
            audio_parts.append((t + 0.35, tone([660, 880])))  # app's start chime
            audio_parts.append((t + 0.6, load_wav(FIXTURES / shot.opts["speech"]) * 0.9))
            audio_parts.append((t + shot.duration, tone([880, 660])))
        t += shot.duration
    total = t

    audio = np.zeros(int(total * RATE) + RATE, dtype=np.float32)
    for start, clip in audio_parts:
        s = int(start * RATE)
        audio[s:s + len(clip)] += clip[: len(audio) - s]
    audio = np.clip(audio / max(1.0, np.abs(audio).max() / 0.95), -1, 1)
    wav_path = Path(work) / "audio.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((audio * 32767).astype("<i2").tobytes())

    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", str(wav_path), "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    cards = {}
    for n in range(int(total * FPS)):
        now = n / FPS
        shot = next(s for s in reversed(shots) if s.start <= now)
        local = now - shot.start
        subtitle = shot.opts.get("caption") or shot.narration
        if shot.kind == "demo":
            a, b = shot.opts["src"]
            src_t = min(b, a + local * shot.opts["speed"])
            index = max(0, int(np.searchsorted(frame_times, src_t, side="right")) - 1)
            img = demo_frame(source_frame(frames[min(index, len(frames) - 1)]), shot, local, subtitle)
        else:
            if shot.kind not in cards:
                cards[shot.kind] = card(shot.kind)
            img = card_frame(cards[shot.kind], subtitle)
        ffmpeg.stdin.write(img.tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"{out}  {total:.1f}s")


if __name__ == "__main__":
    main()
