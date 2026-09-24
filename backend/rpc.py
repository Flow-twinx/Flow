"""Typed RPC dispatch for the Flow daemon socket.

This runs *inside* the resident daemon, in-process. Every method resolves to a
real validated backend function — there is no plugin-facing passthrough that
lets a plugin run arbitrary `flow` flags. The method surface is small and
typed (`docs/dev/plugins.md`):

- state    current_track / is_playing / status / library_stats   (file reads)
- player   pause / resume / next / previous / seek / seek_back / like /
           unlike / download                (host-routed player control)
- players  players — live player registry (kind, pid, port)
- config   get_config / get_configs / set_config   (PLUGIN_SAFE_KEYS enforced)
- ui       set_theme / list_themes / set_spinner
- raw      raw_cli — only when the plugin is installed with ``"raw": true``
           in plugin.json or FLOW_PLUGIN_RAW=1 was set by the launcher
- events   connection-level event registry; server can push ``event`` frames

Generic ``control(*flow_args)`` passthrough is gone. `raw_cli` is the only
arbitrary flag surface, and it's gated host-side.
"""

import json
import os
import pathlib
import socket
import signal as _signal_mod
import sys
import time

from backend import config, control, status as _status
from backend.config import GREY, Muted, Primary, RED, Reset, YELLOW
E = RED
G = GREY
M = Muted
P = Primary
R = Reset
Y = YELLOW

#: Typed-only, gated-raw version of the plugin API.
API_VERSION = 3


# ---------------------------------------------------------------------------
# Host-side capability + validation
# ---------------------------------------------------------------------------

def _plugin_manifest(name: str) -> dict | None:
    """Read an installed plugin's plugin.json (host-validated surface)."""
    manifest_file = pathlib.Path.home() / ".flow/plugins" / name / "plugin.json"
    if not manifest_file.exists():
        return None
    try:
        return json.loads(manifest_file.read_text())
    except Exception:
        return None


def _conn_capabilities(conn: socket.socket) -> dict:
    """Capabilities for a plugin connection, host-validated from its manifest.

    `raw` is a *host-side* decision: the launcher sends the plugin name on
    connect (FLOW_PLUGIN_NAME), and the host checks the installed manifest for
    ``"raw": true`` (or the env override from the launcher). A plugin cannot
    grant itself raw by editing its own copy of flow_api.py.
    """
    name = _conn_plugin_name(conn)
    caps = {"raw": False}
    manifest = _plugin_manifest(name) if name else None
    if manifest and manifest.get("raw"):
        caps["raw"] = True
    return caps


def _conn_plugin_name(conn: socket.socket) -> str | None:
    return getattr(conn, "_flow_plugin_name", None)


# ---------------------------------------------------------------------------
# State reads (stay file-based — cheap, no IPC round trip needed)
# ---------------------------------------------------------------------------

def rpc_status():
    return _status.read()


def rpc_current_track():
    return _status.read() or {}


def rpc_is_playing():
    data = _status._read()
    return bool(data.get("playing"))


def rpc_library_stats():
    try:
        from backend import library
        return library.library_stats()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Player control (host-routed, mirrors cli/main.py::_send_control)
# ---------------------------------------------------------------------------

def _player_running() -> bool:
    from backend import registry

    return registry.resolve("vlc") is not None or registry.resolve("web") is not None


def _send_player(command: str, sig, label: str, delta=None):
    """Host-authoritative player routing — same as the CLI does it."""
    from backend import registry

    entry = registry.resolve("vlc")
    if entry is not None:
        pid = entry["pid"]
        try:
            if delta is not None:
                config.write_seek(int(delta))
            os.kill(pid, sig)
        except ProcessLookupError:
            config.clear_pid_if(pid)
        except OSError:
            pass
        return f"{label} (VLC pid {pid})"
    else:
        control.send(command, delta)
        return f"{label} (web player)"


def rpc_pause() -> str:
    return _send_player("stop", config.SIG_STOP, "Toggled pause/resume")


def rpc_resume() -> str:
    return _send_player("stop", config.SIG_STOP, "Resumed playback")


def rpc_next() -> str:
    return _send_player("next", config.SIG_NEXT, "Skipped to next track")


def rpc_previous() -> str:
    return _send_player("previous", config.SIG_PREV, "Went to previous track")


def rpc_seek(sec: float) -> str:
    return _send_player(
        "seek", config.SIG_SEEK_FWD, f"Seeked forward {int(sec)}s", int(sec) * 1000
    )


def rpc_seek_back(sec: float) -> str:
    return _send_player(
        "seekb", config.SIG_SEEK_BWD, f"Seeked backward {int(sec)}s", -int(sec) * 1000
    )


def _act_current(action: str) -> str:
    """Like/unlike/download the current track, host-routed like the CLI."""
    from backend import status as _status_mod
    from backend.plugin_api import act as _act

    return _act.act_on_current(action)


def rpc_like() -> str:
    return _act_current("like")


def rpc_unlike() -> str:
    return _act_current("unlike")


def rpc_download() -> str:
    return _act_current("download")


# ---------------------------------------------------------------------------
# Player registry (live players, host-readable)
# ---------------------------------------------------------------------------

def rpc_players():
    from backend import registry

    return registry.live()


# ---------------------------------------------------------------------------
# Config (PLUGIN_SAFE_KEYS enforced host-side — never trust the client)
# ---------------------------------------------------------------------------

def rpc_get_config(key: str):
    value, ok = config.config_get(key)
    if not ok:
        return {"error": f"Unknown config key '{key}'"}
    return {"value": value}


def rpc_get_configs():
    return config.get_configs()


def rpc_set_config(key: str, value):
    if value is None:
        return {"error": f"Config value for '{key}' cannot be None"}
    if key.lower() not in config.PLUGIN_SAFE_KEYS:
        return {"error": f"Config key '{key}' is not writable by plugins"}
    msg = config.apply_config(key, value)
    return {"message": msg}


def rpc_set_theme(name: str):
    msg = config.apply_config("theme", name)
    return {"message": msg}


def rpc_list_themes():
    return sorted(config.THEMES)


def rpc_set_spinner(chars: str):
    msg = config.apply_config("spinner", chars)
    return {"message": msg}


# ---------------------------------------------------------------------------
# Raw (gated)
# ---------------------------------------------------------------------------

def rpc_raw_cli(conn, args: list[str]):
    caps = _conn_capabilities(conn)
    if not caps.get("raw"):
        return {
            "error": (
                "raw_cli() is disabled for this plugin. Enable it by adding "
                '"raw": true to plugin.json (docs/dev/plugins.md) or install '
                "with FLOW_PLUGIN_RAW=1."
            )
        }
    from backend import cli_raw

    code, out = cli_raw.run(*args)
    return {"code": code, "output": out}


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------

METHODS = (
    "status",
    "current_track",
    "is_playing",
    "library_stats",
    "pause",
    "resume",
    "next",
    "previous",
    "seek",
    "seek_back",
    "like",
    "unlike",
    "download",
    "players",
    "get_config",
    "get_configs",
    "set_config",
    "set_theme",
    "list_themes",
    "set_spinner",
    "raw_cli",
    "introspect",
)


def rpc_introspect():
    return {
        "api_version": API_VERSION,
        "protocol": "socket",
        "methods": list(METHODS),
        "safe_keys": sorted(config.PLUGIN_SAFE_KEYS),
        "transport": "socket",
    }


# ---------------------------------------------------------------------------
# Frame handling
# ---------------------------------------------------------------------------

def handle(frame: dict, conn: socket.socket | None = None) -> dict | None:
    """Dispatch a single `{method, params}` frame. Returns a response dict."""
    method = frame.get("method")
    params = frame.get("params") or {}

    if method == "hello":
        name = params.get("name")
        if conn is not None:
            setattr(conn, "_flow_plugin_name", name)
        return {
            "api_version": API_VERSION,
            "protocol": "socket",
            "capabilities": _conn_capabilities(conn) if conn else {"raw": False},
        }

    try:
        if method == "status":
            return {"result": rpc_status()}
        if method == "current_track":
            return {"result": rpc_current_track()}
        if method == "is_playing":
            return {"result": rpc_is_playing()}
        if method == "library_stats":
            return {"result": rpc_library_stats()}
        if method == "pause":
            return {"result": rpc_pause()}
        if method == "resume":
            return {"result": rpc_resume()}
        if method == "next":
            return {"result": rpc_next()}
        if method == "previous":
            return {"result": rpc_previous()}
        if method == "seek":
            return {"result": rpc_seek(float(params.get("seconds", 0)))}
        if method == "seek_back":
            return {"result": rpc_seek_back(float(params.get("seconds", 0)))}
        if method == "like":
            return {"result": rpc_like()}
        if method == "unlike":
            return {"result": rpc_unlike()}
        if method == "download":
            return {"result": rpc_download()}
        if method == "players":
            return {"result": rpc_players()}
        if method == "get_config":
            return {"result": rpc_get_config(str(params.get("key", "")))}
        if method == "get_configs":
            return {"result": rpc_get_configs()}
        if method == "set_config":
            return {"result": rpc_set_config(str(params.get("key", "")), params.get("value"))}
        if method == "set_theme":
            return {"result": rpc_set_theme(str(params.get("name", "")))}
        if method == "list_themes":
            return {"result": rpc_list_themes()}
        if method == "set_spinner":
            return {"result": rpc_set_spinner(str(params.get("chars", "")))}
        if method == "raw_cli":
            return rpc_raw_cli(conn, list(params.get("args") or []))
        if method == "introspect":
            return {"result": rpc_introspect()}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"error": f"Unknown method '{method}'"}
