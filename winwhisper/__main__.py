import argparse
import json
import logging
import os
import sys

from . import APP_NAME
from .config import app_dir, load_config, update_config


def setup_logging(verbose):
    handlers = [logging.FileHandler(app_dir() / f"{APP_NAME}.log", encoding="utf-8")]
    if sys.stderr is not None:  # None in a windowed (no console) build
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Hold Alt, speak, release: text appears.")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--model", help="override the Whisper model (tiny, base, small, medium, large-v3-turbo, ...)")
    parser.add_argument("--transcribe", metavar="WAV", help="transcribe a WAV file, print the text and exit")
    parser.add_argument("--test-audio", metavar="WAV", action="append",
                        help="use this WAV instead of the microphone (repeat to cycle through several)")
    parser.add_argument("--set", metavar="KEY=VALUE", action="append",
                        help="change a config value and exit (e.g. --set overlay=false); used by the installer")
    menu = parser.add_argument_group("Explorer Copy Path menu (run by Explorer and the installer)")
    menu.add_argument("--copy-path", metavar="PATH", help="copy PATH to the clipboard and remember it")
    menu.add_argument("--recent-path", metavar="ID", help="copy a remembered path again")
    menu.add_argument("--open-path", metavar="ID", help="open a remembered file or folder")
    menu.add_argument("--install-shell-menu", action="store_true")
    menu.add_argument("--uninstall-shell-menu", action="store_true")
    menu.add_argument("--noop", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-tray", action="store_true", help="run without a tray icon (Ctrl+C to quit)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    for name in ("stdout", "stderr"):  # windowed exe: progress bars need somewhere to write
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    config = load_config(args.config)
    if args.model:
        config["model"] = args.model

    if args.noop:
        return
    if args.copy_path or args.recent_path or args.open_path:
        from . import pathmenu
        action, value = next((a, v) for a, v in (("copy", args.copy_path), ("recent", args.recent_path),
                                                  ("open", args.open_path)) if v)
        sys.exit(pathmenu.run(action, value))
    if args.install_shell_menu or args.uninstall_shell_menu:
        from . import pathmenu
        pathmenu.install() if args.install_shell_menu else pathmenu.uninstall()
        return

    if args.set:
        changes = {}
        for item in args.set:
            key, _, value = item.partition("=")
            try:
                changes[key] = json.loads(value)
            except json.JSONDecodeError:
                changes[key] = value
        update_config(changes, args.config)
        return

    if args.transcribe:
        from .audio import read_wav
        from .transcriber import Transcriber
        transcriber = Transcriber(config["model"], config["device"], config["compute_type"],
                                  config["language"], config["initial_prompt"],
                                  beam_size=config["beam_size"], cpu_model=config["cpu_model"])
        print(transcriber.transcribe(read_wav(args.transcribe)))
        return

    from . import win32
    from .app import DictationApp, Tray
    from .pathmenu import self_command

    _mutex, first = win32.claim_single_instance(f"Local\\{APP_NAME}-single-instance")
    if not first:
        logging.getLogger(__name__).warning("%s is already running", APP_NAME)
        return

    win32.enable_dpi_awareness()
    app = DictationApp(config, test_audio=args.test_audio, config_file=args.config)
    if args.no_tray:
        app.start()
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            app.stop()
        return
    app.tray = Tray(app, self_command())
    app.start()
    app.tray.run()


if __name__ == "__main__":
    main()
