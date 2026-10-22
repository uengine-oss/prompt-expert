"""Explorer right-click "Copy Path" / "Recent Paths" / "Open Paths" menus
(merged from the standalone CopyPath tool).

Explorer runs `prompt-expert.exe --copy-path "<path>"` etc.; each call does
its one job and exits. The recent-paths submenus are plain registry verbs
that are rewritten after every change, so no shell extension DLL is needed.
They appear under "Show more options" (Shift+F10) on Windows 11.
"""

import json
import logging
import ntpath  # Windows path rules, also when unit-tested elsewhere
import os
import sys
import uuid
from pathlib import Path

from .config import app_dir

log = logging.getLogger(__name__)

MAX_ENTRIES = 10
CLASSES = r"Software\Classes"
TARGETS = ("*", "Directory", r"Directory\Background", "Drive")
VERB = "PromptExpert.CopyPath"
SUBMENUS = {"recent": ("PromptExpert.RecentPaths", "Recent Paths"),
            "open": ("PromptExpert.OpenPaths", "Open Paths")}
LEGACY_VERBS = ("CopyPath.Copy", "CopyPath.Recent", "CopyPath.Open")


# ---------------------------------------------------------------- history

def history_file():
    return app_dir() / "path-history.json"


def _legacy_history():
    """History kept by the old PowerShell CopyPath ([{Id, Path}], or one object)."""
    path = Path(os.environ.get("LOCALAPPDATA", "")) / "CopyPath" / "history.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    rows = [rows] if isinstance(rows, dict) else rows
    return [{"id": r["Id"], "path": r["Path"]} for r in rows if isinstance(r, dict) and r.get("Path")]


def load_history():
    path = history_file()
    if not path.exists():
        return _legacy_history()[:MAX_ENTRIES]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []


def save_history(rows):
    path = history_file()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def remember(rows, path):
    """Move (or add) path to the front, keeping its id, at most MAX_ENTRIES."""
    existing = next((r for r in rows if r["path"] == path), None)
    entry = {"id": existing["id"] if existing else uuid.uuid4().hex, "path": path}
    return ([entry] + [r for r in rows if r["path"] != path])[:MAX_ENTRIES]


def normalize(raw):
    # Drive roots and folder backgrounds arrive as "C:\." so a trailing
    # backslash never escapes the closing quote on the command line.
    if not raw or not ntpath.isabs(raw):
        raise ValueError("An absolute path is required.")
    return ntpath.normpath(raw)


def menu_label(path):
    """Name - start of parent folder; the real path is never shortened."""
    stripped = path.rstrip("\\")
    name = ntpath.basename(stripped) or path
    parent = ntpath.dirname(stripped) if ntpath.basename(stripped) else ""
    if len(parent) > 32:
        parent = parent[:32] + "..."
    if len(name) > 48:
        name = name[:30] + "..." + name[-14:]
    label = f"{name} - {parent}" if parent else name
    return label.replace("&", "&&")  # & would become a menu accelerator


# ---------------------------------------------------------------- registry

def self_command():
    """How Explorer should start us: the frozen exe, or pythonw + the source tree."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().parent.parent / "run_winwhisper.py"
    return f'"{pythonw}" "{script}"'


def _delete_tree(root, path):
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, f"{path}\\{child}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def _set(path, value=None, **named):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        if value is not None:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)
        for name, data in named.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, data)


def refresh_menus(rows=None):
    import winreg
    rows = load_history() if rows is None else rows
    command = self_command()
    for kind, (store, _) in SUBMENUS.items():
        base = f"{CLASSES}\\{store}\\shell"
        _delete_tree(winreg.HKEY_CURRENT_USER, base)
        if not rows:
            _set(f"{base}\\00", "(No recent paths)")
            _set(f"{base}\\00\\command", f"{command} --noop")
        for index, row in enumerate(rows):
            entry = f"{base}\\{index:02d}"
            _set(entry, menu_label(row["path"]))
            _set(f"{entry}\\command", f"{command} --{kind}-path {row['id']}")


def remove_legacy_menus():
    """Drop the old PowerShell CopyPath verbs so the menu does not show twice."""
    import winreg
    for target in TARGETS:
        for verb in LEGACY_VERBS:
            _delete_tree(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\{target}\\shell\\{verb}")
    for store in ("CopyPath.Recent", "CopyPath.Open"):
        _delete_tree(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\{store}")


def install():
    remove_legacy_menus()
    command = self_command()
    icon = sys.executable if getattr(sys, "frozen", False) else ""
    for target in TARGETS:
        shell = f"{CLASSES}\\{target}\\shell"
        placeholder = '"%V\\."' if target == r"Directory\Background" else '"%1\\."' if target == "Drive" else '"%1"'
        _set(f"{shell}\\{VERB}", "Copy Path", MultiSelectModel="Single", **({"Icon": icon} if icon else {}))
        _set(f"{shell}\\{VERB}\\command", f"{command} --copy-path {placeholder}")
        for store, title in SUBMENUS.values():
            _set(f"{shell}\\{store}", MUIVerb=title, ExtendedSubCommandsKey=store)
    rows = load_history()
    save_history(rows)  # also carries over the legacy history on first install
    refresh_menus(rows)


def uninstall():
    import winreg
    for target in TARGETS:
        for verb in (VERB, *(store for store, _ in SUBMENUS.values())):
            _delete_tree(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\{target}\\shell\\{verb}")
    for store, _ in SUBMENUS.values():
        _delete_tree(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\{store}")


def installed():
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{CLASSES}\\*\\shell\\{VERB}"))
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------- actions

def run(action, argument=None):
    """Entry point for the --copy-path / --recent-path / --open-path flags."""
    from . import win32

    mutex = win32.kernel32.CreateMutexW(None, False, "Local\\prompt-expert-copy-path")
    win32.kernel32.WaitForSingleObject(mutex, 10000)
    try:
        rows = load_history()
        if action == "copy":
            path = normalize(argument)
            win32.set_clipboard_text(path, keep_out_of_history=False)
            rows = remember(rows, path)
        else:
            row = next((r for r in rows if r["id"] == argument), None)
            if row is None:
                raise ValueError("This history entry is no longer available.")
            if action == "recent":
                win32.set_clipboard_text(row["path"], keep_out_of_history=False)
                rows = remember(rows, row["path"])
            else:
                if not os.path.exists(row["path"]):
                    raise ValueError("This file or folder has moved or no longer exists.")
                os.startfile(row["path"])
        save_history(rows)
        refresh_menus(rows)
        return 0
    except Exception as error:
        # Success is silent, like the original; failures stay diagnosable.
        log.exception("copy-path %s failed", action)
        (app_dir() / "last-error.txt").write_text(str(error), encoding="utf-8")
        return 1
    finally:
        win32.kernel32.ReleaseMutex(mutex)
        win32.kernel32.CloseHandle(mutex)
