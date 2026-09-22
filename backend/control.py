import json
import os
import pathlib
import time

CONTROL_FILE = pathlib.Path.home() / ".flow/web_command.json"

COMMANDS = {"stop", "next", "previous", "seek", "seekb"}


def send(command: str, delta=None):
    if command not in COMMANDS:
        return
    data = {"command": command, "ts": time.time()}
    if delta is not None:
        data["delta"] = delta
    CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTROL_FILE.with_name(CONTROL_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, CONTROL_FILE)


def take():
    """Atomically consume the pending command.

    The file is rename()'d out of the way before reading, so a command written
    between our read and an earlier non-atomic unlink can't be deleted, and two
    concurrent pollers can't double-deliver: only the poller that wins the
    rename sees the command.
    """
    consumed = CONTROL_FILE.with_name(CONTROL_FILE.name + ".consumed")
    try:
        os.replace(CONTROL_FILE, consumed)
    except FileNotFoundError:
        return ""
    try:
        data = json.loads(consumed.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
    finally:
        consumed.unlink(missing_ok=True)
    command = data.get("command", "")
    if "delta" in data:
        return data
    return command