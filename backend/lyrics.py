from ytmusicapi import YTMusic

_yt = None


def _get_yt():
    global _yt
    if _yt is None:
        _yt = YTMusic()
    return _yt


def _extract_lines(result):
    if not result or not isinstance(result, dict):
        return None
    lines = result.get("lyrics", [])
    if not lines:
        return None
    return [
        {"text": l.text, "start": l.start_time / 1000, "end": l.end_time / 1000}
        for l in lines
        if l.text.strip() != "♪"
    ]


def fetch_lyrics(video_id, title=None):
    try:
        yt = _get_yt()

        wp = yt.get_watch_playlist(video_id)
        browse_id = wp.get("lyrics")
        if browse_id and isinstance(browse_id, str):
            result = yt.get_lyrics(browse_id, timestamps=True)
            lines = _extract_lines(result)
            if lines:
                return lines

        if title:
            results = yt.search(title, filter="songs", limit=3)
            for r in results:
                rid = r.get("id")
                if rid and rid != video_id:
                    wp2 = yt.get_watch_playlist(rid)
                    bid = wp2.get("lyrics")
                    if bid and isinstance(bid, str):
                        result = yt.get_lyrics(bid, timestamps=True)
                        lines = _extract_lines(result)
                        if lines:
                            return lines

    except Exception:
        pass
    return None


def find_line(lyrics, elapsed):
    if not lyrics:
        return None
    for line in lyrics:
        if line["start"] <= elapsed < line["end"]:
            return line["text"]
    return None
