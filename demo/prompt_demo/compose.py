"""Composes the narrated "voice prompt + Copy Path" demo (1920x1080).

    python demo/prompt_demo/compose.py TAKE_DIR TTS_DIR OUT.mp4

TAKE_DIR comes from record.py; TTS_DIR holds the ElevenLabs clips named after
the keys in narration.json (made by demo/elevenlabs_tts.py).
"""

import json
import subprocess
import sys
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from compose import (AMBER, BG, BLUE, CARD, MUTED, PANEL, RATE, RED, TEXT, font, load_wav,  # noqa: E402
                     mic, tone, wrap)

W, H, FPS = 1920, 1080, 30
VM_X, VM_Y, VM_W, VM_H = 36, 28, 1229, 922  # the 1024x768 VM screen at 1.2x
SCALE = VM_W / 1024
PX, PW = 1300, 584  # right panel
ZOOM_W, ZOOM_H = 560, 315
STEPS = ["입력창 클릭", "Alt 누른 채 말하기", "탐색기에서 Copy Path", "프롬프트에 붙여넣기 (Ctrl+V)",
         "말로 이어 쓰기", "Recent Paths로 다시 쓰기"]
LINES = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))

# Zoom regions on the VM screen (x, y, width); height follows 16:9.
PROMPT_ZOOM = (40, 250, 600)
PILL_ZOOM = (352, 560, 320)
MENU_ZOOM = (455, 165, 570)
COPY_ZOOM = (650, 170, 380)
RECENT_ZOOM = (60, 160, 640)


class Shot:
    def __init__(self, kind, src=None, speed=1.0, narr=(), step=None, zoom=None, minimum=0.0, **opts):
        self.kind, self.src, self.speed, self.narr = kind, src, speed, list(narr)
        self.step, self.zoom, self.minimum, self.opts = step, zoom, minimum, opts


def build_shots(e):
    return [
        Shot("title", narr=["n_title"], minimum=4),
        Shot("demo", (e["start"], e["focus"] + 2.4), narr=["n_setup"], step=0, zoom=PROMPT_ZOOM),
        Shot("demo", (e["focus"] + 2.4, e["hold1_start"]), narr=["n_hold1"], step=1, zoom=PROMPT_ZOOM),
        Shot("demo", (e["hold1_start"], e["hold1_end"]), step=1, zoom=PILL_ZOOM, hold="say1"),
        Shot("demo", (e["hold1_end"], e["text1"] - 0.6), speed=8, step=1, zoom=PILL_ZOOM, fast=True),
        Shot("demo", (e["text1"] - 0.6, e["explorer"]), narr=["n_after1"], step=1, zoom=PROMPT_ZOOM),
        Shot("demo", (e["explorer"], e["menu2"]), narr=["n_explorer"], step=2, zoom=MENU_ZOOM),
        Shot("demo", (e["menu2"], e["back"]), narr=["n_copy"], step=2, zoom=COPY_ZOOM),
        Shot("demo", (e["back"], e["hold2_start"]), narr=["n_paste", "n_hold2"], step=3, zoom=PROMPT_ZOOM,
             paste_at=e["pasted"]),
        Shot("demo", (e["hold2_start"], e["hold2_end"]), step=4, zoom=PILL_ZOOM, hold="say2"),
        Shot("demo", (e["hold2_end"], e["text2"] - 0.6), speed=8, step=4, zoom=PILL_ZOOM, fast=True),
        Shot("demo", (e["text2"] - 0.6, e["recent"]), narr=["n_after2"], step=4, zoom=PROMPT_ZOOM),
        Shot("demo", (e["recent"], e["recent_open"]), speed=1.6, step=5, zoom=MENU_ZOOM),
        Shot("demo", (e["recent_open"], e["final"]), narr=["n_recent"], step=5, zoom=RECENT_ZOOM),
        # the finished prompt, unobstructed (same text as after the Recent Paths detour)
        Shot("demo", (e["text2"] + 0.8, e["recent"]), narr=["n_end"], zoom=PROMPT_ZOOM),
        Shot("end", minimum=3.5),
    ]


# ---------------------------------------------------------------- drawing

def title_card(kind):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((W / 2 - 70, 230, W / 2 + 70, 370), 70, fill=BLUE)
    mic(d, W / 2, 300, 2.1)
    d.text((W / 2, 430), "prompt-expert", font=font(96, "Bold"), fill=TEXT, anchor="mt")
    if kind == "title":
        lines = [("말로 쓰는 AI 프롬프트, 파일 경로는 클릭 한 번으로", 40, TEXT),
                 ("Alt 길게 눌러 받아쓰기  ·  탐색기 Copy Path", 30, MUTED)]
    else:
        lines = [("음성 인식은 PC 안에서 처리  ·  경로 기록도 이 PC에만", 36, TEXT),
                 ("prompt-expert-Setup 하나로 두 기능 모두 설치", 30, MUTED)]
    y = 580
    for text, size, color in lines:
        d.text((W / 2, y), text, font=font(size, "Medium"), fill=color, anchor="mt")
        y += size + 30
    return img


@lru_cache(maxsize=48)
def vm_frame(path):
    return Image.open(path).convert("RGB")


@lru_cache(maxsize=48)
def vm_scaled(path):
    return vm_frame(path).resize((VM_W, VM_H), Image.LANCZOS)


def keycap(d, x, y, label, pressed, width=110):
    off = 5 if pressed else 0
    d.rounded_rectangle((x + 4, y + 9, x + width + 4, y + 79), 14, fill=(10, 14, 26))
    d.rounded_rectangle((x, y + off, x + width, y + 70 + off), 14, fill=RED if pressed else CARD)
    d.text((x + width / 2, y + 35 + off), label, font=font(30, "Bold"), fill=TEXT, anchor="mm")


def subtitle(d, text, top, left, width):
    fnt = font(32, "Medium")
    lines = wrap(d, text, fnt, width - 40)[:2]
    y = top + (22 if len(lines) == 1 else 0)
    for line in lines:
        d.text((left + width / 2, y), line, font=fnt, fill=TEXT, anchor="mt")
        y += 46


def demo_frame(src_path, shot, local, src_t, caption):
    img = Image.new("RGB", (W, H), BG)
    img.paste(vm_scaled(src_path), (VM_X, VM_Y))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((VM_X - 2, VM_Y - 2, VM_X + VM_W + 1, VM_Y + VM_H + 1), 6, outline=CARD, width=2)

    d.text((PX, 34), "prompt-expert", font=font(46, "Bold"), fill=TEXT)
    d.text((PX, 96), "말로 쓰는 프롬프트 + 탐색기 Copy Path", font=font(22, "Medium"), fill=MUTED)
    y = 150
    for i, label in enumerate(STEPS):
        active = shot.step == i
        done = shot.step is not None and i < shot.step
        d.rounded_rectangle((PX, y, PX + PW, y + 50), 12, fill=BLUE if active else PANEL)
        d.text((PX + 22, y + 25), "✓" if done else str(i + 1), font=font(22, "Bold"),
               fill=TEXT if active or done else MUTED, anchor="mm")
        d.text((PX + 46, y + 25), label, font=font(22, "Medium" if active else "Regular"),
               fill=TEXT if active else (200, 208, 220) if done else MUTED, anchor="lm")
        y += 58

    ky = y + 18
    holding = shot.opts.get("hold") and src_t < shot.src[1] - 0.05
    pasting = "paste_at" in shot.opts and -0.3 <= src_t - shot.opts["paste_at"] <= 0.9
    keycap(d, PX, ky, "Alt", holding)
    keycap(d, PX + 150, ky, "Ctrl", pasting)
    d.text((PX + 275, ky + 35), "+", font=font(30, "Bold"), fill=MUTED, anchor="mm")
    keycap(d, PX + 300, ky, "V", pasting, width=80)
    state = (f"누르고 말하는 중  {local:0.1f}초" if holding else "붙여넣기" if pasting else "")
    d.text((PX + 400, ky + 35), state, font=font(20, "Medium"), fill=RED if holding else BLUE, anchor="lm")

    zy = ky + 110
    d.text((PX, zy), "확대", font=font(20, "Medium"), fill=MUTED)
    if shot.zoom:
        zx, zyy, zw = shot.zoom
        zh = zw * 9 / 16
        crop = vm_frame(src_path).crop((zx, zyy, zx + zw, zyy + zh)).resize((ZOOM_W, ZOOM_H), Image.LANCZOS)
        img.paste(crop, (PX, zy + 32))
        d.rounded_rectangle((PX - 2, zy + 30, PX + ZOOM_W + 2, zy + 32 + ZOOM_H + 2), 8, outline=BLUE, width=3)
        # where the inset comes from, on the main view
        rx, ry = VM_X + zx * SCALE, VM_Y + zyy * SCALE
        d.rectangle((rx, ry, rx + zw * SCALE, ry + zh * SCALE), outline=(59, 130, 246, 170), width=3)

    if shot.opts.get("fast"):
        badge = f"{shot.speed:0.0f}배속  ·  테스트 VM이라 느림 (일반 PC는 수 초)"
        fnt = font(22, "Medium")
        bw = d.textlength(badge, font=fnt) + 40
        d.rounded_rectangle((VM_X + VM_W - bw - 16, VM_Y + 16, VM_X + VM_W - 16, VM_Y + 62), 23, fill=(*AMBER, 240))
        d.text((VM_X + VM_W - 16 - bw / 2, VM_Y + 39), badge, font=fnt, fill=(20, 20, 20), anchor="mm")

    if caption:
        subtitle(d, caption, VM_Y + VM_H + 12, VM_X, VM_W)
    return img


def card_frame(base, caption):
    if not caption:
        return base
    img = base.copy()
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((160, 860, W - 160, 1010), 18, fill=(0, 0, 0, 120))
    subtitle(d, caption, 892, 160, W - 320)
    return img


# ---------------------------------------------------------------- main

def main():
    take, tts, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    timeline = json.loads((take / "timeline.json").read_text())
    events = {x["name"]: x["t"] for x in timeline["events"]}
    frame_times = np.array(timeline["frames"])
    frames = sorted((take / "frames").glob("*.png"))
    shots = build_shots(events)

    t, parts, captions = 0.0, [], []
    for shot in shots:
        clips = [(key, load_wav(tts / f"{key}.wav")) for key in shot.narr]
        need = sum(len(c) / RATE + 0.35 for _, c in clips) + (0.4 if clips else 0)
        if shot.src:
            a, b = shot.src
            natural = (b - a) / shot.speed
            if shot.speed > 1 and need > natural:
                shot.speed = (b - a) / need
                natural = need
            shot.duration = max(natural, need, shot.minimum)
        else:
            shot.duration = max(shot.minimum, need)
        shot.start = t
        at = t + 0.3
        for key, clip in clips:
            parts.append((at, clip))
            captions.append((at - 0.2, at + len(clip) / RATE + 0.3, LINES[key]["caption"]))
            at += len(clip) / RATE + 0.35
        if shot.opts.get("hold"):
            hold_len = shot.src[1] - shot.src[0]
            parts.append((t + 0.35, tone([660, 880])))
            parts.append((t + 0.5, load_wav(tts / f"{shot.opts['hold']}.wav")))
            parts.append((t + hold_len, tone([880, 660])))
            captions.append((t, t + hold_len, LINES[shot.opts["hold"]]["caption"]))
        t += shot.duration
    total = t

    audio = np.zeros(int((total + 1) * RATE), dtype=np.float32)
    for start, clip in parts:
        s = int(start * RATE)
        audio[s:s + len(clip)] += clip[: len(audio) - s]
    audio = np.clip(audio / max(1.0, float(np.abs(audio).max()) / 0.95), -1, 1)
    wav_path = Path(tempfile.mkdtemp()) / "audio.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((audio * 32767).astype("<i2").tobytes())

    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", str(wav_path), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    cards = {}
    for n in range(int(total * FPS)):
        now = n / FPS
        shot = next(s for s in reversed(shots) if s.start <= now)
        local = now - shot.start
        caption = next((text for a, b, text in reversed(captions) if a <= now < b), None)
        if shot.kind == "demo":
            a, b = shot.src
            src_t = min(b, a + local * shot.speed)
            index = max(0, int(np.searchsorted(frame_times, src_t, side="right")) - 1)
            img = demo_frame(frames[min(index, len(frames) - 1)], shot, local, src_t, caption)
        else:
            if shot.kind not in cards:
                cards[shot.kind] = title_card(shot.kind)
            img = card_frame(cards[shot.kind], caption)
        ffmpeg.stdin.write(img.tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"{out}  {total:.1f}s")


if __name__ == "__main__":
    main()
