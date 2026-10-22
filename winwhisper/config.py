import json
import os
from pathlib import Path

from . import APP_NAME

DEFAULTS = {
    "hotkey": "alt",
    "min_hold_seconds": 0.35,
    "model": "large-v3-turbo",
    "device": "auto",
    "compute_type": "auto",
    "cpu_model": "small",
    "beam_size": 1,
    "language": "auto",
    "initial_prompt": "",
    "paste_method": "clipboard",
    "restore_clipboard": True,
    "sounds": True,
    "overlay": True,
    "max_record_seconds": 300,
    "input_device": None,
}


def app_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path():
    return app_dir() / "config.json"


def update_config(changes, path=None):
    """Change only these keys in the config file (used by the tray and the installer)."""
    path = Path(path) if path else config_path()
    config = load_config(path)
    config.update(changes)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config(path=None):
    path = Path(path) if path else config_path()
    config = dict(DEFAULTS)
    if path.exists():
        config.update(json.loads(path.read_text(encoding="utf-8")))
    else:
        path.write_text(json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    return config
