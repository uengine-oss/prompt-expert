"""End-to-end test of the Explorer Copy Path menu on Windows.

Runs each menu command exactly as Explorer would (the registry command line
with %1 / %V filled in) and checks the clipboard, the Recent/Open submenus,
the legacy CopyPath migration and uninstall.

    python tests\\e2e_copypath.py [--app-exe path\\to\\prompt-expert.exe]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from winwhisper import pathmenu, win32  # noqa: E402

HKCU = winreg.HKEY_CURRENT_USER
CLASSES = r"Software\Classes"


def reg_value(path, name=""):
    try:
        with winreg.OpenKey(HKCU, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def menu_command(target):
    return reg_value(rf"{CLASSES}\{target}\shell\{pathmenu.VERB}\command")


def explorer_run(command_line, path):
    """Fill in the placeholder the way Explorer does and start the command line as-is."""
    line = command_line.replace("%1", path).replace("%V", path)
    started = time.time()
    result = subprocess.run(line, timeout=60)
    return result.returncode, time.time() - started


def submenu(kind):
    store = pathmenu.SUBMENUS[kind][0]
    entries = []
    for index in range(pathmenu.MAX_ENTRIES):
        base = rf"{CLASSES}\{store}\shell\{index:02d}"
        label = reg_value(base)
        if label is None:
            break
        entries.append((label, reg_value(base + r"\command")))
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-exe")
    parser.add_argument("--result", default=str(ROOT / "e2e-copypath-result.json"))
    args = parser.parse_args()
    app = [args.app_exe] if args.app_exe else [sys.executable.replace("python.exe", "pythonw.exe"),
                                               str(ROOT / "run_winwhisper.py")]
    check, info = {}, {}

    # A machine that still has the old PowerShell CopyPath installed.
    legacy_dir = Path(os.environ["LOCALAPPDATA"]) / "CopyPath"
    legacy_dir.mkdir(exist_ok=True)
    (legacy_dir / "history.json").write_text(json.dumps({"Id": "legacy1", "Path": r"C:\Windows"}),
                                             encoding="utf-8-sig")
    with winreg.CreateKey(HKCU, rf"{CLASSES}\*\shell\CopyPath.Copy\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "legacy")
    history = pathmenu.history_file()
    history.unlink(missing_ok=True)

    base = Path(os.environ["TEMP"]) / "pe-copypath" / "공백 폴더 & R&D"
    shutil.rmtree(base.parent, ignore_errors=True)
    base.mkdir(parents=True)
    target_file = base / "한글 파일 (1).txt"
    target_file.write_text("copy path test", encoding="utf-8")

    try:
        subprocess.run(app + ["--install-shell-menu"], check=True, timeout=60)
        check["verbs_for_all_targets"] = all(menu_command(t) for t in pathmenu.TARGETS)
        check["submenu_links"] = all(
            reg_value(rf"{CLASSES}\{t}\shell\{store}", "ExtendedSubCommandsKey") == store
            for t in pathmenu.TARGETS for store, _ in pathmenu.SUBMENUS.values())
        check["legacy_menu_removed"] = reg_value(rf"{CLASSES}\*\shell\CopyPath.Copy\command") is None
        check["legacy_history_imported"] = [e[0] for e in submenu("recent")] == ["Windows - C:\\"]

        cases = [
            ("file", "*", str(target_file), str(target_file)),
            ("folder", "Directory", str(base), str(base)),
            ("drive root", "Drive", "C:\\", "C:\\"),
            ("folder background", r"Directory\Background", str(base), str(base)),
        ]
        timings = []
        for name, target, given, expected in cases:
            win32.set_clipboard_text("before", keep_out_of_history=False)
            code, seconds = explorer_run(menu_command(target), given)
            timings.append(round(seconds, 2))
            check[f"copy_{name}"] = code == 0 and win32.get_clipboard_text() == expected
            info[f"clipboard_{name}"] = win32.get_clipboard_text()
        info["copy_seconds"] = timings

        recent = submenu("recent")
        info["recent_labels"] = [label for label, _ in recent]
        # folder copied twice (folder + background) is kept once, newest first
        check["recent_order_dedup"] = info["recent_labels"] == [
            pathmenu.menu_label(str(base)), "C:\\", pathmenu.menu_label(str(target_file)), "Windows - C:\\"]
        check["open_mirrors_recent"] = [e[0] for e in submenu("open")] == info["recent_labels"]

        win32.set_clipboard_text("before", keep_out_of_history=False)
        code, _ = explorer_run(recent[2][1], "")
        check["recent_recopies"] = code == 0 and win32.get_clipboard_text() == str(target_file)
        check["recent_moves_to_front"] = submenu("recent")[0][0] == pathmenu.menu_label(str(target_file))

        before = notepad_pids()
        code, _ = explorer_run(submenu("open")[0][1], "")
        time.sleep(4)
        check["open_launches_default_app"] = code == 0 and bool(notepad_pids() - before)
        subprocess.run(["taskkill", "/IM", "Notepad.exe", "/F"], capture_output=True)

        code = subprocess.run(app + ["--recent-path", "no-such-id"], timeout=60).returncode
        error_file = pathmenu.app_dir() / "last-error.txt"
        check["bad_entry_reports_error"] = code == 1 and "no longer available" in error_file.read_text(encoding="utf-8")

        subprocess.run(app + ["--uninstall-shell-menu"], check=True, timeout=60)
        check["uninstall_removes_menus"] = not any(menu_command(t) for t in pathmenu.TARGETS) and not submenu("recent")
    finally:
        shutil.rmtree(base.parent, ignore_errors=True)
        shutil.rmtree(legacy_dir, ignore_errors=True)
        result = {"checks": check, "info": info, "passed": bool(check) and all(check.values())}
        Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["passed"] else 1)


def notepad_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Notepad.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {line.split('","')[1] for line in out.splitlines() if line.startswith('"')}


if __name__ == "__main__":
    main()
