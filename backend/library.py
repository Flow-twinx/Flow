import fcntl
import hashlib
import json
import os
import pathlib
import urllib.request

from backend.config import _truncate_title

LIBRARY_FILE = pathlib.Path.home() / ".flow/library.json"
THUMB_CACHE = pathlib.Path.home() / ".flow/downloads/.cache"
_LOCK_FILE = pathlib.Path.home() / ".flow/library.lock"

# Metadata fields once stored but no longer wanted; purged on every save.
_REMOVED_META_KEYS = {
    "track",
    "uploader",
    "channel",
    "upload_date",
    "release_date",
    "view_count",
    "like_count",
    "url",
}


def load() -> dict:
    if not LIBRARY_FILE.exists():
        return {}
    try:
        data = json.loads(LIBRARY_FILE.read_text())
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError, OSError:
        pass
    return {}


def _atomic_write(path: pathlib.Path, data: dict):
    """Write JSON atomically so a crash mid-write can never truncate the file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


class _library_lock:
    """Exclusive cross-process lock guarding library read-modify-write cycles."""

    def __init__(self):
        self._fh = None

    def __enter__(self):
        LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(_LOCK_FILE, "a+")
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()
        self._fh = None


def _mutate(fn):
    """Serialize a load → mutate → save cycle. ``fn(library)`` may mutate
    ``library`` in place and must return True when a save is needed."""
    with _library_lock():
        library = load()
        changed = fn(library)
        if changed:
            save(library)
        return library


def save(library: dict):
    for entry in library.values():
        if isinstance(entry, dict):
            if entry.get("title"):
                entry["title"] = _truncate_title(entry["title"])
            for key in _REMOVED_META_KEYS:
                entry.pop(key, None)
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(LIBRARY_FILE, library)


def thumbnail_path(video_id: str) -> str:
    return str(THUMB_CACHE / f"{video_id}.jpg")


def thumbnail_url_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _set_thumbnail(video_id: str, path: str):
    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            return False
        entry["thumbnail"] = path
        library[video_id] = entry
        return True

    _mutate(mutate)


def download_thumbnail(video_id: str, thumb_url: str = "") -> str | None:
    if not video_id:
        return None
    path = thumbnail_path(video_id)
    if pathlib.Path(path).exists():
        _set_thumbnail(video_id, path)
        return path
    if not thumb_url:
        thumb_url = thumbnail_url_for(video_id)
    candidates = [thumb_url]
    if "i.ytimg.com/vi/" in thumb_url:
        try:
            vid = thumb_url.split("/vi/")[1].split("/")[0]
            candidates.insert(0, f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg")
        except IndexError:
            pass
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if not data:
                continue
            THUMB_CACHE.mkdir(parents=True, exist_ok=True)
            pathlib.Path(path).write_bytes(data)
            _set_thumbnail(video_id, path)
            return path
        except Exception:
            continue
    return None


def key_for(url: str, video_id: str = "") -> str:
    if video_id:
        return video_id
    if url:
        return f"s:{hashlib.sha1(url.encode()).hexdigest()}"
    return ""


def _default_entry(video_id: str, title: str = "") -> dict:
    return {
        "liked": False,
        "downloaded": False,
        "title": title,
        "song": None,
        "thumbnail": thumbnail_path(video_id),
    }


def get(video_id: str) -> dict | None:
    return load().get(video_id)


def get_title(video_id: str) -> str:
    entry = get(video_id)
    if entry and entry.get("title"):
        return entry["title"]
    return video_id


def title_for_stem(stem: str) -> str:
    return get_title(stem)


def is_liked(video_id: str) -> bool:
    entry = get(video_id)
    return bool(entry and entry.get("liked"))


def is_downloaded(video_id: str) -> bool:
    return get_download_path(video_id) is not None


def get_download_path(video_id: str) -> str | None:
    entry = get(video_id)
    if not entry or not entry.get("downloaded"):
        return None
    return entry.get("song")


def get_downloaded_ids() -> list:
    return sorted(
        k for k, v in load().items()
        if isinstance(v, dict) and v.get("downloaded") and v.get("song")
    )


def get_liked_ids() -> list:
    return sorted(
        k for k, v in load().items() if isinstance(v, dict) and v.get("liked")
    )


def get_liked_entries() -> list:
    return [
        {"video_id": k, "title": v.get("title", "")}
        for k, v in load().items()
        if isinstance(v, dict) and v.get("liked")
    ]


def get_speed_dial_ids() -> list:
    return sorted(
        k for k, v in load().items()
        if isinstance(v, dict) and v.get("speed_dial")
    )


def get_speed_dial_entries() -> list:
    return [
        {"video_id": k, "title": v.get("title", "")}
        for k, v in load().items()
        if isinstance(v, dict) and v.get("speed_dial")
    ]


def mark_speed_dial(video_id: str, title: str = "", path: str = ""):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            entry = _default_entry(video_id, title)
        entry["speed_dial"] = True
        if title and not entry.get("title"):
            entry["title"] = title
        if path:
            entry["song"] = path
        entry["thumbnail"] = thumbnail_path(video_id)
        library[video_id] = entry
        return True

    _mutate(mutate)


def unmark_speed_dial(video_id: str):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            return False
        entry.pop("speed_dial", None)
        if not entry.get("liked") and not entry.get("downloaded") and not entry.get("song"):
            library.pop(video_id, None)
        else:
            library[video_id] = entry
        return True

    _mutate(mutate)


def mark_liked(video_id: str, title: str = ""):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            entry = _default_entry(video_id, title)
        entry["liked"] = True
        if title and not entry.get("title"):
            entry["title"] = title
        entry["thumbnail"] = thumbnail_path(video_id)
        library[video_id] = entry
        return True

    _mutate(mutate)


def mark_unliked(video_id: str):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            return False
        entry["liked"] = False
        if not entry.get("downloaded"):
            library.pop(video_id, None)
        else:
            library[video_id] = entry
        return True

    _mutate(mutate)


def track_download(video_id: str, path: str, title: str = "", meta=None):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            entry = _default_entry(video_id, title)
        entry["downloaded"] = True
        entry["song"] = path
        if title and not entry.get("title"):
            entry["title"] = title
        if meta:
            for k, v in meta.items():
                if v not in (None, ""):
                    entry[k] = v
        entry["thumbnail"] = thumbnail_path(video_id)
        library[video_id] = entry
        return True

    _mutate(mutate)


def meta_from_info(info: dict) -> dict:
    """Best-effort metadata extraction from a yt-dlp info dict.

    Only artist, album and duration are kept; anything else that was
    previously stored is deliberately dropped (see _REMOVED_META_KEYS).
    """
    meta = {}
    artist = info.get("artist")
    if not artist:
        artists = info.get("artists")
        if (
            isinstance(artists, list)
            and artists
            and all(isinstance(a, str) for a in artists)
        ):
            artist = ", ".join(artists)
    if isinstance(artist, (list, tuple)):
        artist = ", ".join(str(a) for a in artist if a) or None
    if artist:
        meta["artist"] = str(artist)
    if info.get("album"):
        meta["album"] = info.get("album")
    duration = info.get("duration")
    if duration:
        try:
            meta["duration"] = int(duration)
        except (TypeError, ValueError):
            pass
    return meta


def update_meta(video_id: str, meta: dict):
    """Merge fetched/backfilled metadata into the library entry."""
    if not video_id or not meta:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            entry = _default_entry(video_id)
        for k, v in meta.items():
            if v not in (None, ""):
                entry[k] = v
        library[video_id] = entry
        return True

    _mutate(mutate)


def clear_download(video_id: str):
    if not video_id:
        return

    def mutate(library):
        entry = library.get(video_id)
        if entry is None:
            return False
        entry["downloaded"] = False
        entry["song"] = None
        if not entry.get("liked"):
            library.pop(video_id, None)
        else:
            library[video_id] = entry
        return True

    _mutate(mutate)


def delete(video_id: str) -> bool:
    path = get_download_path(video_id)
    removed = bool(path)
    if path:
        p = pathlib.Path(path)
        if p.exists():
            p.unlink()
        stem = p.stem if p.suffix else p.name
        for other in p.parent.glob(f"{stem}*"):
            if other != p:
                try:
                    other.unlink()
                except OSError:
                    pass
    thumb = THUMB_CACHE / video_id
    for other in THUMB_CACHE.glob(f"{thumb.name}*"):
        try:
            other.unlink()
        except OSError:
            pass
    clear_download(video_id)
    return removed
