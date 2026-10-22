"""Text-to-speech with ElevenLabs for the demo videos.

    ELEVENLABS_API_KEY=... python demo/elevenlabs_tts.py VOICE_ID OUT_DIR lines.json

lines.json maps names to text (or to {"tts": text, ...}); writes OUT_DIR/<name>.wav (48 kHz mono) and a
16 kHz copy for lines used as microphone input. Existing files are kept, so
re-running only synthesizes new or changed lines.
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODEL = "eleven_multilingual_v2"


def synthesize(voice, text, mp3_path):
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": MODEL,
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}).encode(),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        mp3_path.write_bytes(response.read())


def main():
    voice, out = sys.argv[1], Path(sys.argv[2])
    lines = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    for name, text in lines.items():
        text = text["tts"] if isinstance(text, dict) else text
        digest = hashlib.sha1(f"{voice}|{MODEL}|{text}".encode()).hexdigest()[:10]
        mp3 = out / f"{name}-{digest}.mp3"
        if not mp3.exists():
            synthesize(voice, text, mp3)
        for rate, suffix in ((48000, ""), (16000, "_16k")):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", str(rate),
                            "-c:a", "pcm_s16le", str(out / f"{name}{suffix}.wav")], check=True)
        print(name, mp3.name)


if __name__ == "__main__":
    main()
