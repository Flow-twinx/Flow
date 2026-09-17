import json
import pathlib

SHORTCUTS_FILE = pathlib.Path.home() / ".flow/shortcuts.json"

DEFAULT_SHORTCUTS = {
    "pl": "play",
    "sh": "search",
    "ls": "list",
    "lk": "like",
    "ul": "unlike",
    "dl": "download",
    "dl-d": "delete",
    "rd": "radio",
    "sw": "switch",
    "hl": "help",
    "cf": "config",
    "ex": "exit",
    "svn": "savan",
    "svn-s": "savan-s",
    "plist": "playlist",
}

_shortcuts = {}

def load():
    global _shortcuts
    _shortcuts = DEFAULT_SHORTCUTS.copy()
    if SHORTCUTS_FILE.exists():
        try:
            saved = json.loads(SHORTCUTS_FILE.read_text())
            _shortcuts.update(saved)
        except (json.JSONDecodeError, OSError):
            pass

def save():
    SHORTCUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHORTCUTS_FILE.write_text(json.dumps(_shortcuts, indent=2))

def resolve(cmd):
    return _shortcuts.get(cmd, DEFAULT_SHORTCUTS.get(cmd, cmd))

def get_all():
    return _shortcuts

def get_list():
    return list(_shortcuts.items())

def set_shortcut(key, value):
    _shortcuts[key] = value
    save()

def remove(key):
    _shortcuts.pop(key, None)
    save()

def cmd_short(extra, tprint):
    items = get_list()
    if not extra:
        if not items:
            tprint("No shortcuts defined")
            return
        tprint("Shortcuts:")
        for i, (key, val) in enumerate(items, 1):
            tprint(f"  {i}. {key:8s} -> {val}")
        tprint(f"\n  short add <key> <cmd>  - add new alias")
        tprint(f"  short remove <idx>     - remove alias")
        return

    if extra[0] == "add":
        if len(extra) < 3:
            tprint("Usage: short add <key> <command>")
            return
        key = extra[1].lower()
        val = extra[2].lower()
        if key in _shortcuts:
            set_shortcut(key, val)
            tprint(f"  {key:8s} -> {val}  (updated)")
        else:
            set_shortcut(key, val)
            tprint(f"  {key:8s} -> {val}  (added)")
        return

    if extra[0] == "remove":
        if len(extra) < 2:
            tprint("Usage: short remove <index>")
            return
        try:
            idx = int(extra[1])
        except ValueError:
            tprint("Index must be a number")
            return
        items = get_list()
        if idx < 1 or idx > len(items):
            tprint(f"Index out of range (1-{len(items)})")
            return
        key, val = items[idx - 1]
        remove(key)
        tprint(f"  Removed: {key} -> {val}")
        return

    try:
        idx = int(extra[0])
    except ValueError:
        tprint("Usage: short [index] [new_command] | short add <key> <cmd> | short remove <idx>")
        return

    if idx < 1 or idx > len(items):
        tprint(f"Index out of range (1-{len(items)})")
        return

    key, val = items[idx - 1]
    if len(extra) == 1:
        tprint(f"  {idx}. {key:8s} -> {val}")
    else:
        new_val = extra[1].lower()
        set_shortcut(key, new_val)
        tprint(f"  {idx}. {key:8s} -> {new_val}  (updated)")
