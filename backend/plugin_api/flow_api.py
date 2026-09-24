"""Typed client for the Flow daemon socket (plugin API v3).

Plugins never spawn the `flow` CLI to read state, control the player, or
touch config. This module connects to the resident daemon socket
(`~/.flow/flow.sock`, mode 0600) and calls a small typed method surface
(`backend/rpc.py` — the protocol + capability contract live there):

- state    current_track / is_playing / status / library_stats   (file reads)
- player   pause / resume / next / previous / seek / seek_back / like /
           unlike / download                (host-routed player control)
- config   get_config / get_configs / set_config   (PLUGIN_SAFE_KEYS enforced
           host-side; unknown keys and unsafe keys are rejected host-side)
- ui       set_theme / list_themes / set_spinner
- raw      raw_cli                         (only when host grants ``raw`` to
           this plugin — plugin.json `"raw": true` or FLOW_PLUGIN_RAW=1 at
           launch; the daemon validates the capability from the *installed*
           manifest, not from anything the plugin can forge)

The old generic `control(*flow_args)` subprocess passthrough is gone from
the documented surface. A deprecated subprocess fallback is kept only for
plugins that haven't been re-API'd yet — it warns and calls the real
`flow` CLI, and it is *always* less capable than the socket.

Reads stay file-based (status.json / library.json / config.json) — cheap,
no IPC round trip. Only writes/controls go over the socket.
"""

import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import warnings

HOME = pathlib.Path.home()

STATUS_FILE = HOME / ".flow/status.json"
CONFIG_FILE = HOME / ".flow/config.json"
LIBRARY_FILE = HOME / ".flow/library.json"
STATS_FILE = HOME / ".flow/status.json"

API_VERSION = 3

_CONNECT_TIMEOUT = 5.0
_FRAME_TIMEOUT = 30.0
_MAX_FRAME = 1 << 20


# ---------------------------------------------------------------------------
# Socket connection + frame I/O
# ---------------------------------------------------------------------------

def _default_socket() -> pathlib.Path:
    return HOME / ".flow/flow.sock"


def socket_path() -> str:
    """The daemon socket path (from FLOW_SOCKET, else ~/.flow/flow.sock)."""
    return str(os.environ.get("FLOW_SOCKET") or _default_socket())


def _connect() -> socket.socket | None:
    target = socket_path()
    if not os.path.exists(target):
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(_CONNECT_TIMEOUT)
    try:
        sock.connect(target)
    except OSError:
        try:
            sock.close()
        except OSError:
            pass
        return None
    return sock


def _read_frame(sock: socket.socket):  # -> dict | None
    """Read one newline-delimited JSON frame from the daemon."""
    data = sock.recv(65536)
    if not data:
        return None
    # Daemon sends one frame per line (json.dumps + "\\n").
    line = data.decode().strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except ValueError:
        return None


def _send_frame(sock: socket.socket, payload: dict) -> dict | None:
    """Send a request frame and return its response."""
    try:
        sock.sendall((json.dumps(payload) + "\n").encode())
    except OSError:
        return None
    return _read_frame(sock)


def _hello(sock: socket.socket) -> dict:
    """Handshake: tell the daemon who we are so capability gating is host-validated."""
    name = os.environ.get("FLOW_PLUGIN_NAME", "")
    return _send_frame(sock, {"method": "hello", "params": {"name": name}}) or {}


# ---------------------------------------------------------------------------
# Typed method dispatch
# ---------------------------------------------------------------------------

def _call(method: str, **params) -> dict:
    """Typed call over the socket. Returns the daemon's response dict."""
    sock = _connect()
    if sock is None:
        return _deprecated_fallback(method, **params)
    try:
        _hello(sock)
        return _send_frame(
            sock, {"method": method, "params": params}
        ) or {"error": "no response"}
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _deprecated_fallback(method: str, **params) -> dict:
    """No daemon socket — old subprocess passthrough (deprecated, warns)."""
    warnings.warn(
        "flow_api v3: no daemon socket found; falling back to a subprocess "
        "call. Install 'flow daemon' for the typed socket API.",
        DeprecationWarning,
        stacklevel=2,
    )
    _flow_args = _method_to_cli(method, params)
    if not _flow_args:
        return {
            "error": f"no subprocess fallback for '{method}'",
            "deprecated": True,
        }
    try:
        proc = subprocess.run([FLOW_BIN, *_flow_args], capture_output=True, text=True)
    except OSError as exc:
        return {"error": f"subprocess fallback failed: {exc}"}
    return {
        "result": (proc.stdout or proc.stderr).strip(),
        "code": proc.returncode,
        "deprecated": True,
    }


def _method_to_cli(method: str, params: dict) -> list[str]:
    """Map a typed socket method back to a legacy CLI flag set (fallback only)."""
    mapping = {
        "pause": ["--pause"],
        "resume": ["--pause"],
        "next": ["--next"],
        "previous": ["--previous"],
        "like": ["--like"],
        "unlike": ["--unlike"],
        "download": ["--download"],
        "status": ["--status"],
        "current_track": ["--status"],
        "is_playing": ["--status"],
    }
    if method in ("seek", "seek_back"):
        sec = int(params.get("seconds", 0))
        return ["--seek" if method == "seek" else "--seekb", str(sec)]
    if method == "set_config":
        return ["--config-set", str(params.get("key", "")), str(params.get("value", ""))]
    if method == "get_config":
        return ["--config-get", str(params.get("key", ""))]
    if method == "set_theme":
        return ["--config-set", "theme", str(params.get("name", ""))]
    if method == "set_spinner":
        return ["--config-set", "spinner", str(params.get("chars", ""))]
    if method == "library_stats":
        return ["--library-stats"]  # legacy flag if it exists
    return mapping.get(method) or []


FLOW_BIN = os.environ.get("FLOW_BIN") or "flow"

_flags_to_click = {
    "--pause": "pause",
    "--resume": "resume",
    "--next": "next",
    "--previous": "previous",
    "--seek": "seek",
    "--seekb": "seekb",
    "--like": "like",
    "--unlike": "unlike",
    "--download": "download",
}


def control(*flow_args):
    """Deprecated: generic flow CLI control passthrough (v2 compat surface).

    Replaced by the typed surface below. Kept so old plugins don't break: it
    warns and runs the `flow` CLI as a subprocess. The daemon deliberately
    has no generic passthrough method, so this never touches the socket.
    """
    warnings.warn(
        "flow_api.control() is deprecated; use flow_api.pause()/resume()/"
        "next()/seek()/like() etc.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _run(*flow_args).returncode


# ---------------------------------------------------------------------------
# State reads (file-based — cheap)
# ---------------------------------------------------------------------------

def current_track():
    """Current track info dict: title/duration/playing/thumbnail/ts, or {}."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def is_playing():
    return bool(current_track().get("playing", False))


def status_card():
    """Rendered status card (renders the CLI status to a string)."""
    r = _call("status")
    return r.get("result") if isinstance(r, dict) else ""


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


# ---------------------------------------------------------------------------
# Player controls (typed, host-routed over the socket)
# ---------------------------------------------------------------------------

def pause():
    return _call("pause")


def resume():
    return _call("resume")


def next():
    return _call("next")


def previous():
    return _call("previous")


def seek(sec):
    return _call("seek", seconds=float(sec))


def seek_back(sec):
    return _call("seek_back", seconds=float(sec))


def like():
    return _call("like")


def unlike():
    return _call("unlike")


def download():
    return _call("download")


def players():
    """Live registered players: ``[{"kind", "pid", "port"?}, ...]``.

    Empty list when nothing is playing/registered (CLI player, TUI, web).
    """
    r = _call("players")
    if r.get("error"):
        return {"error": r["error"]}
    return r.get("result", [])


# ---------------------------------------------------------------------------
# Config (typed, PLUGIN_SAFE_KEYS enforced host-side)
# ---------------------------------------------------------------------------

def get_config(key, default=None):
    """Read a config value through the daemon (host-validated key)."""
    r = _call("get_config", key=key)
    result = r.get("result")
    if isinstance(result, dict):
        if "error" in result:
            return default
        if "value" in result:
            return result["value"]
    if r.get("error"):
        return default
    return default


def get_configs(keys):
    """Fetch a set of configs by safe keys; returns {key: value}."""
    out = {}
    for key in keys:
        val = get_config(key)
        if val is not None:
            out[key] = val
    return out


def set_config(key, value):
    """Set a config value through the daemon (host-validated keys only).

    Returns (ok, message). Unsafe keys are rejected host-side."""
    r = _call("set_config", key=key, value=str(value))
    result = r.get("result")
    if isinstance(result, dict):
        if "error" in result:
            return False, result["error"]
        return True, result.get("message", "")
    if r.get("error"):
        return False, r["error"]
    return True, ""


def set_theme(name):
    return set_config("theme", name)


def list_themes():
    r = _call("list_themes")
    result = r.get("result")
    if isinstance(result, dict):
        return result.get("themes") or []
    if isinstance(result, list):
        return result
    return []


def set_spinner(chars):
    return set_config("spinner", chars)


# ---------------------------------------------------------------------------
# Raw (gated host-side — only when the daemon granted `raw` for this plugin)
# ---------------------------------------------------------------------------

def raw_cli(*flow_args):
    """Run arbitrary flow CLI flags — ONLY when the host granted `raw`.

    The daemon validates this from the plugin's *installed* manifest
    (`"raw": true` in plugin.json, or FLOW_PLUGIN_RAW=1 at launch). Plugins
    without that capability get an error back regardless of what they pass.
    """
    r = _call("raw_cli", args=list(flow_args))
    if r.get("error"):
        return {"error": r["error"]}
    return r.get("result", {})


# ---------------------------------------------------------------------------
# Deprecated subprocess passthrough (v2 compat surface)
# ---------------------------------------------------------------------------

def _run(*flow_args):
    """Run a flow CLI subprocess (deprecated; socket is the forward path)."""
    return subprocess.run(
        [FLOW_BIN, *flow_args], capture_output=True, text=True
    )


__all__ = [
    "API_VERSION",
    "current_track",
    "is_playing",
    "status_card",
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
    "socket_path",
]
