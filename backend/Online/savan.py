import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

from backend import config

API_BASE = "https://teenapi.dino.icu/api"


def search(query, limit=10):
    params = urllib.parse.urlencode({"query": query, "limit": str(limit)})
    url = f"{API_BASE}/search/songs?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError, json.JSONDecodeError, OSError:
        return []
    if not isinstance(data, dict) or not data.get("success"):
        return []
    results = (data.get("data") or {}).get("results", [])
    out = []
    for r in results:
        if not isinstance(r, dict):
            continue
        name = r.get("name", "Unknown")
        dur = r.get("duration", 0)
        artists = r.get("artists")
        primary = artists.get("primary") if isinstance(artists, dict) else None
        if primary and isinstance(primary, list) and isinstance(primary[0], dict):
            artist = primary[0].get("name", "Unknown")
        else:
            artist = "Unknown"
        out.append((r, f"{name} - {artist}", dur))
    for entry, title, dur in out:
        album = entry.get("album")
        config.dev_print(
            "Savan Search Result",
            {
                "title": title,
                "song_id": entry.get("id"),
                "duration": f"{dur}s",
                "album": album.get("name") if isinstance(album, dict) else None,
                "download_urls": len(entry.get("downloadUrl") or []),
            },
        )
    return out


def thumb_url(entry) -> str:
    if not isinstance(entry, dict):
        return ""
    images = entry.get("image") or []
    if not isinstance(images, list):
        return ""
    for img in images:
        if isinstance(img, dict) and img.get("quality") == "500x500" and img.get("url"):
            return img["url"]
    for img in images:
        if isinstance(img, dict) and img.get("url"):
            return img["url"]
    return ""


def best_url(entry):
    if not isinstance(entry, dict):
        return None
    dls = entry.get("downloadUrl") or []
    if not isinstance(dls, list) or not dls:
        return None
    pref = {"320kbps", "160kbps", "96kbps", "48kbps", "12kbps"}
    best = None
    for q in pref:
        for dl in dls:
            if isinstance(dl, dict) and dl.get("quality") == q and dl.get("url"):
                best = dl["url"]
                break
        if best:
            break
    if not best:
        for dl in dls:
            if isinstance(dl, dict) and dl.get("url"):
                best = dl["url"]
                break
    if not best:
        return None
    config.dev_print(
        "Savan Best URL",
        {
            "title": entry.get("name", "Unknown"),
            "selected_url": best[:80] + "..." if len(best) > 80 else best,
            "available_qualities": [
                dl["quality"]
                for dl in dls
                if isinstance(dl, dict) and dl.get("quality")
            ],
        },
    )
    return best


def download(url, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        urllib.request.urlretrieve(url, part)
    except Exception as exc:
        part.unlink(missing_ok=True)
        config.down_notify(url, error=True)
        raise
    part.replace(dest)
    config.down_notify(url)
    return dest
