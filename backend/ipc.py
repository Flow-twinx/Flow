"""Cross-process player control: POSIX signals on Linux, a localhost socket elsewhere."""

import json
import os
import signal as _signal
import socket
import threading

from backend import config, platform

_SIGNAL_ATTR = {
    "pause": "SIG_STOP",
    "next": "SIG_NEXT",
    "prev": "SIG_PREV",
    "seek_fwd": "SIG_SEEK_FWD",
    "seek_bwd": "SIG_SEEK_BWD",
    "repeat": "SIG_REPEAT",
    "shuffle": "SIG_SHUFFLE",
    "stop_all": "SIG_STOP_ALL",
}

WEB_COMMANDS = {
    "pause": "stop",
    "next": "next",
    "prev": "previous",
    "seek_fwd": "seek",
    "seek_bwd": "seekb",
}

_dispatch = None
_server_port = None


def signal_for(action: str):
    """Signal number carrying ``action`` on this platform, or None."""
    return getattr(config, _SIGNAL_ATTR.get(action, ""), None)


def serve(dispatch, kind: str = "vlc") -> int | None:
    """Install control handlers in this process; returns a socket port off Linux."""
    global _dispatch, _server_port
    _dispatch = dispatch
    for action in _SIGNAL_ATTR:
        sig = signal_for(action)
        if sig is None:
            continue
        try:
            _signal.signal(sig, lambda s, f, a=action: _call(a, None))
        except (ValueError, OSError, RuntimeError):
            pass
    if platform.is_linux():
        return None
    if _server_port is None:
        _server_port = _start_server()
    return _server_port


def dispatch(action: str, payload=None) -> bool:
    """Run ``action`` inside this process (self-control without signals)."""
    return _call(action, payload)


def send(entry, action: str, payload=None) -> bool:
    """Deliver ``action`` to a player registry entry; True when delivered."""
    if not entry:
        return False
    port = entry.get("ctl_port")
    if port:
        return _send_socket(int(port), action, payload)
    sig = signal_for(action)
    if sig is None or platform.is_windows():
        return False
    try:
        os.kill(int(entry["pid"]), sig)
        return True
    except (ProcessLookupError, OSError, ValueError):
        return False


def send_to(kind: str, action: str, payload=None) -> bool:
    """Resolve ``kind`` in the player registry and deliver ``action`` to it."""
    from backend import registry

    return send(registry.resolve(kind), action, payload)


def _call(action: str, payload) -> bool:
    handler = _dispatch
    if handler is None or not action:
        return False
    try:
        handler(action, payload)
        return True
    except TypeError:
        try:
            handler(action)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _start_server() -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    port = srv.getsockname()[1]
    threading.Thread(target=_serve_loop, args=(srv,), daemon=True).start()
    return port


def _serve_loop(srv):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        try:
            data = conn.recv(65536)
        except OSError:
            data = b""
        finally:
            conn.close()
        if not data:
            continue
        try:
            msg = json.loads(data.decode())
        except (ValueError, UnicodeDecodeError):
            continue
        _call(msg.get("action", ""), msg.get("payload"))


def _send_socket(port: int, action: str, payload=None) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=5) as s:
            s.sendall(json.dumps({"action": action, "payload": payload}).encode())
        return True
    except OSError:
        return False
