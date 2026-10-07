"""Play history and library totals."""

import time

from backend import history, library

from . import out
from .common import stamp


def history_cmd(sort="recent", limit=20, since=None):
    """List what was played, newest first unless --sort says otherwise."""
    start = _since(since)
    rows = history.timeline(sort=sort, limit=limit, since=start)
    payload = [
        {
            "video_id": row["video_id"],
            "title": row["title"],
            "artist": row["artist"] or "",
            "played_at": row["played_at"],
            "played": stamp(row["played_at"]),
            "play_count": row["play_count"],
        }
        for row in rows
    ]
    text = []
    for row in payload:
        who = f" - {row['artist']}" if row["artist"] else ""
        count = f"  x{row['play_count']}" if row["play_count"] > 1 else ""
        text.append(f"{row['played']}  {row['title']}{who}{count}")
    out.emit(payload, text or ["nothing played yet"])


def _since(value):
    if not value or value == "all":
        return None
    days = history.RANGES.get(value)
    if days is None:
        out.fail(f"unknown range {value!r}; use {', '.join(history.RANGES)}")
    return time.time() - days * 86400


def stats():
    """Library and play totals."""
    totals = history.totals()
    payload = dict(library.stats())
    payload["online_plays"] = totals["online_plays"]
    payload["online_songs"] = totals["online_songs"]
    payload["online_today"] = totals["online_today"]
    payload["per_day"] = [{"days_ago": offset, "plays": count} for offset, count in history.per_day(7)]
    text = [
        f"plays        {payload['total_plays']}",
        f"today        {payload['played_today']}",
        f"unique       {payload['unique_songs']}",
        f"downloaded   {payload['downloaded']}",
        f"liked        {payload['liked']}",
        f"online logs  {payload['online_plays']} over {payload['online_songs']} songs",
        f"last 7 days  " + " ".join(str(day["plays"]) for day in payload["per_day"]),
    ]
    out.emit(payload, text)
