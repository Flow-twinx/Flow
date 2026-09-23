import json
import os
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
STATUS_FILE = HOME / ".flow/status.json"
CONFIG_FILE = HOME / ".flow/config.json"
LIBRARY_FILE = HOME / ".flow/library.json"
FLOW_BIN = os.environ.get("FLOW_BIN", "flow")

API_VERSION = 2


def _run(*flow_args):
    return subprocess.run([FLOW_BIN, *flow_args], capture_output=True, text=True)


def control(*flow_args):
    """Run a flow CLI command and return its exit code (output streams through)."""
    return subprocess.call([FLOW_BIN, *flow_args])


def current_track():
    """Current track info dict: title/duration/playing/thumbnail/ts, or {}."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def is_playing():
    return bool(current_track().get("playing", False))


def get_config(key):
    """Read a config value (string, number, bool) or None."""
    r = _run("--config-get", key)
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    try:
        return json.loads(out)
    except ValueError:
        return out


def get_configs():
    out = {}
    for key in (
        "primary",
        "secondary",
        "tertiary",
        "theme",
        "spinner",
        "display",
        "barwidth",
        "barheight",
        "barspacing",
        "barchar",
        "sensitivity",
        "format",
        "max_search",
        "max_radio",
        "ad_skip",
        "down_on_like",
    ):
        val = get_config(key)
        if val is not None:
            out[key] = val
    return out


def set_config(key, value):
    """Set a config value through the validated setter.
    Returns (ok, message). Only safe cosmetic keys are writable."""
    r = _run("--config-set", key, str(value))
    ok = r.returncode == 0
    return ok, (r.stdout or r.stderr).strip()


def set_theme(name):
    return set_config("theme", name)


def list_themes():
    r = _run("--theme", "list")
    out = r.stdout.strip()
    if "Themes:" not in out:
        return []
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    return [t.strip() for t in out.split("Themes:", 1)[1].split(",")]


def set_spinner(chars):
    return set_config("spinner", chars)


def pause():
    return control("--pause")


def next():
    return control("--next")


def previous():
    return control("--previous")


def seek(sec):
    return control("--seek", str(int(sec)))


def seek_back(sec):
    return control("--seekb", str(int(sec)))


def like():
    return control("--like")


def unlike():
    return control("--unlike")


def download():
    return control("--download")


def status_card():
    return control("--status")


def library_stats():
    """Counts from ~/.flow/library.json: {songs, liked, duration}."""
    try:
        songs = json.loads(LIBRARY_FILE.read_text())
    except Exception:
        songs = []
    if isinstance(songs, dict):
        songs = list(songs.values())
    liked = [s for s in songs if s.get("liked", False)]
    total = sum(int(s.get("duration", 0) or 0) for s in songs)
    return {"songs": len(songs), "liked": len(liked), "duration": total}


def plugin_info():
    return {
        "api_version": API_VERSION,
        "name": os.environ.get("FLOW_PLUGIN_NAME", ""),
        "home": os.environ.get("FLOW_PLUGIN_HOME", ""),
        "background": os.environ.get("FLOW_PLUGIN_BG", "0") == "1",
        "flow_bin": FLOW_BIN,
        "python": sys.version.split()[0],
    }
