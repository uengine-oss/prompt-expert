"""Draws the recording overlay frames (no Win32 here, so it can be previewed anywhere)."""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 196, 46  # logical pixels; scaled by monitor DPI
BARS = 17
SS = 2  # supersampling for anti-aliased shapes


def level_to_unit(rms):
    """Map an RMS amplitude to 0..1 on a loudness-like (dB) scale."""
    db = 20 * math.log10(max(rms, 1e-6))
    return min(1.0, max(0.0, (db + 56) / 52))


def _load_font(size):
    for name in ("malgunbd.ttf", "malgun.ttf", "segoeuib.ttf", "arial.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size), name.startswith("malgun")
    return ImageFont.load_default(), False


class Painter:

    def __init__(self, scale=1.0, font=None, korean=True):
        self.scale = scale
        self.size = (round(WIDTH * scale), round(HEIGHT * scale))
        px = round(13 * scale * SS)
        self.font, self.korean = (font, korean) if font else _load_font(px)

    def frame(self, mode, t, levels, elapsed):
        w, h = self.size[0] * SS, self.size[1] * SS
        s = self.scale * SS
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(22, 22, 26, 238),
                            outline=(255, 255, 255, 40), width=max(1, round(s)))
        cy = h / 2
        if mode == "recording":
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.2))
            r = 5.5 * s
            cx = 22 * s
            d.ellipse((cx - r * 1.9, cy - r * 1.9, cx + r * 1.9, cy + r * 1.9), fill=(255, 69, 58, int(70 * pulse)))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 69, 58, 255))
            bar_w, gap = 3 * s, 2.8 * s
            x0 = 40 * s
            max_h = h - 16 * s
            for i, value in enumerate(levels):
                bh = max(3 * s, value * max_h)
                x = x0 + i * (bar_w + gap)
                alpha = int(150 + 105 * (i / max(1, len(levels) - 1)))
                d.rounded_rectangle((x, cy - bh / 2, x + bar_w, cy + bh / 2), radius=bar_w / 2,
                                    fill=(255, 255, 255, alpha))
            label = f"{int(elapsed) // 60}:{int(elapsed) % 60:02d}"
            d.text((w - 14 * s, cy), label, font=self.font, fill=(255, 255, 255, 200), anchor="rm")
        else:  # "busy" (transcribing) or "loading" (model not ready yet)
            cx = 26 * s
            for i in range(3):
                phase = t * 2 * math.pi * 1.4 - i * 0.7
                lift = (0.5 + 0.5 * math.sin(phase)) * 5 * s
                a = int(140 + 115 * (0.5 + 0.5 * math.sin(phase)))
                x = cx + (i - 1) * 9 * s
                d.ellipse((x - 3 * s, cy - lift - 3 * s, x + 3 * s, cy - lift + 3 * s), fill=(255, 196, 64, a))
            if mode == "loading":
                text = "모델 준비 중" if self.korean else "Loading model"
            else:
                text = "받아쓰는 중" if self.korean else "Transcribing"
            d.text((48 * s, cy), text, font=self.font, fill=(255, 255, 255, 230), anchor="lm")
            if elapsed >= 3:  # show that it is still working, not stuck
                seconds = f"{int(elapsed)}초" if self.korean else f"{int(elapsed)}s"
                d.text((w - 16 * s, cy), seconds, font=self.font, fill=(255, 255, 255, 150), anchor="rm")
        return img.resize(self.size, Image.LANCZOS)
