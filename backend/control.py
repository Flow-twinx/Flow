import json
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
    CONTROL_FILE.write_text(json.dumps(data))


def take():
    if not CONTROL_FILE.exists():
        return ""
    try:
        data = json.loads(CONTROL_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
    finally:
        CONTROL_FILE.unlink(missing_ok=True)
    command = data.get("command", "")
    if "delta" in data:
        return data
    return command
