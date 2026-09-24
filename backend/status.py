import json
import os
import pathlib
import time

STATUS_FILE = pathlib.Path.home() / ".flow/status.json"
WEB_PORT_FILE = pathlib.Path.home() / ".flow/web_port"


def update(title, duration=0, playing=True, thumbnail=None):
    data = {
        "title": title or "Unknown",
        "duration": int(duration or 0),
        "playing": bool(playing),
        "thumbnail": thumbnail or "",
        "ts": time.time(),
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_name(STATUS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, STATUS_FILE)


def _read():
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def read():
    return _read()


def _web_active():
    from backend import registry

    return registry.resolve("web") is not None


def _web_port():
    from backend import registry

    entry = registry.resolve("web")
    if entry and entry.get("port"):
        return entry["port"]
    try:
        return int(WEB_PORT_FILE.read_text().strip())
    except Exception:
        return None


def _fresh(data):
    ts = data.get("ts", 0)
    dur = data.get("duration", 0)
    return time.time() - ts <= max(120.0, dur + 30.0)


def _print_plain(Primary, GREY, Reset, entries):
    sep = f"{GREY}{'─' * 44}{Reset}"
    print(f"\n{Primary}┌─ Flow Status{Reset}")
    print(sep)
    for label, rendered, _ in entries:
        print(f"{Primary}│{Reset}  {label:<17}: {rendered}")
    print(sep)
    print(f"{Primary}└─{Reset}\n")


def _vid_from_thumb(thumb: str):
    """Best-effort video id extraction from a thumb URL or local cache path."""
    if not thumb:
        return None
    try:
        for pat in ("/vi_webp/", "/vi/", ".cache/"):
            if pat in thumb:
                return thumb.split(pat)[1].split("/")[0].split(".")[0] or None
    except Exception:
        return None
    return None


def show():
    from . import library
    from .config import CYAN, GREY, WHITE, Muted, Primary, Reset

    from backend import registry

    registry.prune()  # drop dead players from ~/.flow/players.json
    data = _read()
    web = _web_active()
    port = _web_port()
    playing = bool(data.get("playing")) and _fresh(data)

    title = data.get("title", "None")
    if len(title) > 42:
        title = title[:42] + "..."
    thumb_raw = data.get("thumbnail", "")
    thumb = thumb_raw
    flow_prefix = str(pathlib.Path.home() / ".flow")
    if thumb.startswith(flow_prefix):
        thumb = thumb[len(flow_prefix) :]
    if len(thumb) > 120:
        thumb = thumb[:120] + "..."
    dur = int(data.get("duration", 0))
    mins, secs = divmod(dur, 60)
    dur_str = f"{mins}:{secs:02d}"

    status_val = "playing" if playing else "not playing"
    status_col = CYAN if playing else Muted
    web_val = f"{port} active" if web else "not active"
    stat = "currently playing" if playing else "last played"
    web_col = CYAN if web else Muted

    vid = _vid_from_thumb(thumb_raw)
    artist = album = ""
    if vid:
        entry = library.get(vid) or {}
        artist = entry.get("artist") or ""
        album = entry.get("album") or ""

    entries = [
        ("status", f"{status_col}{status_val}{Reset}", len(status_val)),
        ("web_mode", f"{web_col}{web_val}{Reset}", len(web_val)),
        (stat, f"{WHITE}{title}{Reset}", len(title)),
    ]
    if artist:
        entries.append(("artist", f"{WHITE}{artist}{Reset}", len(artist)))
    if album:
        entries.append(("album", f"{WHITE}{album}{Reset}", len(album)))
    entries += [
        ("thumbnail", f"{WHITE}{thumb}{Reset}", len(thumb)),
        ("total duration", f"{WHITE}{dur_str}{Reset}", len(dur_str)),
    ]

    _print_plain(Primary, GREY, Reset, entries)