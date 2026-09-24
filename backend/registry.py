"""Player registry — single source of truth for live Flow players.

Every interface that can receive player control (the CLI/background VLC
player, the TUI, the web server) registers itself here, so routing and
status agree on *who is actually running right now*. The registry is a
file-based store, ``~/.flow/players.json``, keyed by player kind::

    {"vlc": {"pid": 1234, "ts": 1700000000.0},
     "tui": {"pid": 5678, "ts": 1700000000.0},
     "web": {"pid": 9012, "port": 5000, "ts": 1700000000.0}}

Kinds
-----
- ``vlc``  the CLI / background player (also claimed by the running TUI)
- ``tui``  the text UI (flowt)
- ``web``  the web server (flow-web)

Legacy pid files (``vlc.pid``, ``tui.pid``, ``web.pid`` + ``web_port``)
continue to be written by ``backend/config.py`` and ``web/main.py`` as
mirrors so pre-registry readers keep working. Routing prefers the registry
and falls back to those files via :func:`resolve`, so a slot registered by an
older Flow still routes correctly.

This module is intentionally stdlib-only, so it can be imported by the
daemon, the web server, the TUI, and plugins without import cycles.
"""

import json
import os
import pathlib
import time

HOME = pathlib.Path.home()
STATE_DIR = HOME / ".flow"
PLAYERS_FILE = STATE_DIR / "players.json"

KINDS = ("vlc", "tui", "web")

LEGACY_PID_FILES = {
    "vlc": STATE_DIR / "vlc.pid",
    "tui": STATE_DIR / "tui.pid",
    "web": STATE_DIR / "web.pid",
}
LEGACY_PORT_FILE = STATE_DIR / "web_port"


def _read() -> dict:
    try:
        data = json.loads(PLAYERS_FILE.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write(data: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PLAYERS_FILE.with_name(PLAYERS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, PLAYERS_FILE)


def _alive(pid) -> bool:
    """True when the pid belongs to a live process."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def entry(kind: str) -> dict | None:
    """Registry record for ``kind`` when it is registered and alive."""
    rec = _read().get(kind)
    if not rec or not _alive(rec.get("pid")):
        return None
    return rec


def register(kind: str, pid: int, port: int | None = None) -> dict:
    """Register (or refresh) a live player of the given kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown player kind {kind!r}")
    data = _read()
    rec = {"pid": int(pid), "ts": time.time()}
    if port is not None:
        rec["port"] = int(port)
    data[kind] = rec
    _write(data)
    return rec


def unregister(kind: str, pid: int | None = None):
    """Remove a player. With ``pid``, only removes when it matches."""
    data = _read()
    rec = data.get(kind)
    if not rec:
        return
    if pid is not None and int(rec.get("pid", -1)) != int(pid):
        return
    del data[kind]
    _write(data)


def clear():
    """Drop every registered player."""
    _write({})


def live() -> list[dict]:
    """All live players as routing records: ``{kind, pid, port?}``."""
    out = []
    for kind, rec in _read().items():
        if _alive(rec.get("pid")):
            row = {"kind": kind, "pid": int(rec["pid"])}
            if rec.get("port") is not None:
                row["port"] = int(rec["port"])
            out.append(row)
    return out


def resolve(kind: str) -> dict | None:
    """Routing lookup: the registry first, then the legacy pid file."""
    rec = entry(kind)
    if rec:
        return rec
    pid_file = LEGACY_PID_FILES.get(kind)
    if pid_file and pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid = None
        if _alive(pid):
            rec = {"pid": pid}
            if kind == "web":
                try:
                    rec["port"] = int(LEGACY_PORT_FILE.read_text().strip())
                except (ValueError, OSError):
                    pass
            return rec
    return None


def has(kind: str) -> bool:
    """True when a live player of ``kind`` is reachable."""
    return resolve(kind) is not None


def prune():
    """Drop registry entries whose pid is dead (e.g. crashed players)."""
    data = _read()
    clean = {k: v for k, v in data.items() if _alive(v.get("pid"))}
    if len(clean) != len(data):
        _write(clean)