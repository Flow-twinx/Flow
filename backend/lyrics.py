import bisect
import json
import logging
import operator
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

LRCLIB_API = "https://lrclib.net/api"
LRCLIB_TIMEOUT = 6
USER_AGENT = "flow-twinx"

HIT_TTL = 60 * 60
MISS_TTL = 10 * 60
CACHE_MAX = 50

_cache = {}
_cache_lock = threading.Lock()

_yt = None
_yt_lock = threading.Lock()

_LRC_TIME = re.compile(r"\[(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_WORD = re.compile(r"<[^>]*>")
_SPACES = re.compile(r"\s+")
_BRACKETED = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_JOINED = re.compile(r"\s+[-–—]\s+")

_NOISE_WORDS = {
    "official", "video", "audio", "music", "lyric", "lyrics", "lyrical",
    "visualizer", "hd", "hq", "4k", "mv", "m/v", "explicit", "clean",
    "remaster", "remastered", "version", "full", "song", "topic", "vevo",
}
_DECORATION_WORDS = {
    "official", "video", "audio", "lyric", "lyrics", "lyrical", "visualizer",
    "mv", "m/v", "topic", "vevo",
}
_LAST_LINE_SECONDS = 5.0
_START = operator.itemgetter("start")


def _get_yt():
    global _yt
    if _yt is None:
        with _yt_lock:
            if _yt is None:
                from ytmusicapi import YTMusic

                _yt = YTMusic()
    return _yt


def _stamp(match):
    hours, minutes, seconds, frac = match.groups()
    total = int(seconds) + int(minutes) * 60
    if hours is not None:
        total += int(hours) * 3600
    if frac:
        total += int((frac + "000")[:3]) / 1000
    return total


def parse_lrc(text, duration=0):
    if not text:
        return []
    stamps = []
    for raw in text.splitlines():
        matches = list(_LRC_TIME.finditer(raw))
        if not matches:
            continue
        body = _SPACES.sub(" ", _LRC_WORD.sub("", _LRC_TIME.sub("", raw))).strip()
        for match in matches:
            stamps.append((_stamp(match), body))
    if not stamps:
        return []

    stamps.sort(key=lambda pair: pair[0])
    lines = []
    for index, (start, body) in enumerate(stamps):
        if index + 1 < len(stamps):
            end = stamps[index + 1][0]
        else:
            end = float(duration) if duration else start + _LAST_LINE_SECONDS
        if end <= start:
            end = start + _LAST_LINE_SECONDS
        lines.append({"text": body, "start": round(start, 3), "end": round(end, 3)})
    return lines


def parse_plain(text):
    if not text:
        return []
    return [line.strip() for line in text.replace("\r", "").split("\n")]


def _is_noise(text):
    words = text.lower().split()
    if not words:
        return True
    if len(words) > 3:
        return False
    if len(words) == 1:
        return words[0] in _DECORATION_WORDS
    return words[0] in _NOISE_WORDS or all(w in _NOISE_WORDS for w in words)


def _segments(title):
    text = _BRACKETED.sub(" ", title or "")
    return [p.strip() for p in _JOINED.split(text) if p.strip()]


def clean_title(title):
    parts = _segments(title)
    if len(parts) > 1:
        useful = [p for p in parts if not _is_noise(p)] or parts
        parts = [useful[-1]]
    words = parts[0].split() if parts else []
    while words and words[-1].lower() in _NOISE_WORDS and (
        len(words) > 1 or words[0].lower() in _DECORATION_WORDS
    ):
        words.pop()
    return " ".join(words)


def split_artist_title(title):
    parts = _segments(title)
    useful = [p for p in parts if not _is_noise(p)]
    if len(useful) < 2:
        return "", useful[0] if useful else (title or "").strip()
    return " ".join(useful[:-1]), useful[-1]


def _lrclib_json(endpoint, params):
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    if not query:
        return None
    req = urllib.request.Request(
        f"{LRCLIB_API}/{endpoint}?{query}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=LRCLIB_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.debug("LRCLIB %s?%s -> HTTP %s", endpoint, query, exc.code)
    except Exception as exc:
        logger.warning("LRCLIB %s request failed: %s", endpoint, exc)
    return None


def _score(record, duration):
    try:
        gap = abs(float(record.get("duration") or 0) - float(duration or 0))
    except (TypeError, ValueError):
        gap = 0.0
    return (
        0 if (record.get("syncedLyrics") or "").strip() else 1,
        0 if not record.get("instrumental") else 1,
        gap if duration else 0.0,
    )


def _from_lrclib(record, duration=0):
    if not isinstance(record, dict):
        return None
    synced_raw = (record.get("syncedLyrics") or "").strip()
    plain_raw = (record.get("plainLyrics") or "").strip()
    if not synced_raw and not plain_raw:
        return None
    lines = parse_lrc(synced_raw, duration) if synced_raw else []
    plain = parse_plain(plain_raw) if plain_raw else []
    if not plain and synced_raw:
        plain = [line for line in parse_plain(_LRC_TIME.sub("", synced_raw)) if line]
    return {
        "lines": lines,
        "plain": plain,
        "synced": bool(lines),
        "source": "lrclib",
    }


def _fetch_lrclib(track, artist, album, duration):
    plain_hit = None
    if track and artist:
        found = _from_lrclib(
            _lrclib_json(
                "get",
                {
                    "track_name": track,
                    "artist_name": artist,
                    "album_name": album,
                    "duration": int(duration) if 0 < duration <= 3600 else 0,
                },
            ),
            duration,
        )
        if found and found["synced"]:
            return found
        plain_hit = plain_hit or found

    if track:
        results = _lrclib_json("search", {"track_name": track, "artist_name": artist})
        if isinstance(results, list) and results:
            found = _from_lrclib(min(results, key=lambda r: _score(r, duration)), duration)
            if found and (found["synced"] or plain_hit is None):
                return found
    return plain_hit


def _yt_lines(result):
    if not result or not isinstance(result, dict):
        return None
    lines = [
        {
            "text": line.text,
            "start": (line.start_time or 0) / 1000,
            "end": (line.end_time or line.start_time or 0) / 1000,
        }
        for line in result.get("lyrics", [])
        if line.text.strip() != "♪" and line.start_time is not None
    ]
    return lines or None


def _lyrics_for_browse(yt, playlist):
    browse_id = (playlist or {}).get("lyrics")
    if not browse_id or not isinstance(browse_id, str):
        return None
    return _yt_lines(yt.get_lyrics(browse_id, timestamps=True))


def _from_ytmusic(lines):
    return {
        "lines": lines,
        "plain": [line["text"] for line in lines],
        "synced": True,
        "source": "ytmusic",
    }


def _fetch_ytmusic(video_id, title):
    yt = _get_yt()
    if video_id:
        lines = _lyrics_for_browse(yt, yt.get_watch_playlist(video_id))
        if lines:
            return _from_ytmusic(lines)

    if title:
        for result in yt.search(title, filter="songs", limit=3):
            rid = result.get("id")
            if not rid or rid == video_id:
                continue
            lines = _lyrics_for_browse(yt, yt.get_watch_playlist(rid))
            if lines:
                return _from_ytmusic(lines)
    return None


def _cache_get(key):
    with _cache_lock:
        cached = _cache.get(key)
        if not cached:
            return None, False
        stored, value = cached
        if time.time() - stored > (HIT_TTL if value else MISS_TTL):
            _cache.pop(key, None)
            return None, False
        return value, True


def _cache_put(key, value):
    with _cache_lock:
        if key not in _cache and len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.time(), value)


def clear_cache():
    with _cache_lock:
        _cache.clear()


def fetch_lyrics(video_id=None, title=None, artist=None, album=None, duration=0):
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0

    track = clean_title(title)
    artist = (artist or "").strip()
    if track and not artist:
        artist, track = split_artist_title(title)

    key = f"{video_id or ''}|{track}|{artist}".lower().strip("|")
    if not key:
        return None
    cached, hit = _cache_get(key)
    if hit:
        return cached

    found = None
    if track or video_id:
        try:
            found = _fetch_lrclib(track, artist, (album or "").strip(), duration)
        except Exception as exc:
            logger.warning("LRCLIB lookup failed for %s: %s", key, exc)
    if found and (found["synced"] or not video_id):
        _cache_put(key, found)
        return found

    try:
        fallback = _fetch_ytmusic(video_id, title or track)
    except Exception as exc:
        logger.warning("YouTube Music lyrics failed for %s: %s", key, exc)
        fallback = None

    found = fallback or found
    _cache_put(key, found)
    return found


def _as_lines(lyrics):
    if isinstance(lyrics, dict):
        return lyrics.get("lines") or []
    return lyrics or []


def find_index(lyrics, elapsed):
    lines = _as_lines(lyrics)
    if not lines:
        return -1
    idx = bisect.bisect_right(lines, elapsed, key=_START) - 1
    if idx < 0 or elapsed >= lines[idx]["end"]:
        return -1
    return idx


def find_line(lyrics, elapsed):
    lines = _as_lines(lyrics)
    idx = find_index(lines, elapsed)
    return lines[idx]["text"] if idx >= 0 else None