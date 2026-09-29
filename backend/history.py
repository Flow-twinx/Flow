"""Play-event log for online streams (`~/.flow/history.db`).

One row per play, holding only what a timeline needs: the song name, the
artist, and when it was played. Offline/local playback is deliberately *not*
logged here — local files are counted by `library.bump_play()` (the
`song_count` column in `library.db`) but never produce a timeline row, so the
history stays a record of what you streamed.

`library.db` answers "how many times have I played this song" across every
mode; this file answers "what did I listen to, and when".
"""

import pathlib
import sqlite3
import time
from contextlib import contextmanager

DB_FILE = pathlib.Path.home() / ".flow/history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id  TEXT NOT NULL DEFAULT '',
    title     TEXT NOT NULL,
    artist    TEXT,
    played_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plays_at    ON plays(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_plays_video ON plays(video_id);
"""

#: Timeline sort keys exposed to the web History panel.
SORTS = ("recent", "oldest", "most", "least")

#: Range presets (in days) exposed to the web History panel.
RANGES = {"today": 1, "7d": 7, "30d": 30, "all": 0}


@contextmanager
def _session():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(_SCHEMA)
        yield conn
    finally:
        conn.close()


def _row_to_play(row) -> dict:
    return {
        "id": row["id"],
        "video_id": row["video_id"] or "",
        "title": row["title"],
        "artist": row["artist"] or "",
        "played_at": float(row["played_at"]),
        "play_count": 1,
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def record(video_id: str, title: str, artist: str = "", ts: float | None = None):
    """Append one online play. Silently gives up on an empty title."""
    if not title:
        return
    with _session() as conn:
        conn.execute(
            "INSERT INTO plays (video_id, title, artist, played_at) VALUES (?, ?, ?, ?)",
            (video_id or "", title, artist or "", ts if ts is not None else time.time()),
        )


def record_play(
    video_id: str,
    title: str,
    artist: str = "",
    mode: str = "online",
    duration=0,
) -> int:
    """The single play-tracking entry point used by every player.

    Always bumps `song_count` in `library.db` (online *and* offline). Appends a
    `history.db` row only for online streams, per the module docstring. Never
    raises — a bookkeeping failure must not interrupt playback.
    """
    if not video_id and not title:
        return 0
    from backend import library

    try:
        count = library.bump_play(video_id, title=title, artist=artist, duration=duration)
    except Exception:
        count = 0
    if mode == "online" and title:
        try:
            record(video_id, title, artist)
        except Exception:
            pass
    return count


def clear() -> int:
    """Drop every logged play. Returns how many rows were removed."""
    with _session() as conn:
        removed = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
        conn.execute("DELETE FROM plays")
        return removed


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _since_ts(since: float | None) -> float:
    return since if since else 0.0


def timeline(
    sort: str = "recent",
    limit: int = 100,
    offset: int = 0,
    since: float | None = None,
    unique: bool = False,
) -> list[dict]:
    """Play events for the web History panel.

    ``sort`` is one of `SORTS`; ``since`` is a unix timestamp lower bound.
    ``unique`` collapses repeat plays of the same song down to its most recent
    event (and pairs it with a play count), which is what the "unique songs"
    toggle uses.
    """
    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0

    # `most` / `least` rank by play count, which only means anything once the
    # events are collapsed per song — so those two sorts imply the grouped
    # view whether or not `unique` was asked for.
    if unique or sort in ("most", "least"):
        rows = _grouped_rows(_since_ts(since))
        if sort == "oldest":
            rows = rows[::-1]
        elif sort in ("most", "least"):
            rows = sorted(
                rows,
                key=lambda r: (r["play_count"], r["played_at"]),
                reverse=sort == "most",
            )
        return rows[offset:offset + limit]

    order = "ASC" if sort == "oldest" else "DESC"
    with _session() as conn:
        rows = conn.execute(
            "SELECT id, video_id, title, artist, played_at FROM plays "
            "WHERE played_at >= ? ORDER BY played_at " + order + " LIMIT ? OFFSET ?",
            (_since_ts(since), limit, offset),
        ).fetchall()
    return [_row_to_play(r) for r in rows]


def _grouped_rows(since: float) -> list[dict]:
    """One row per distinct song, newest play first, each with a play count.

    A song is identified by its `video_id`, falling back to the title for rows
    that never had one (a JioSaavn play from an older build, say).
    """
    with _session() as conn:
        rows = conn.execute(
            "SELECT MIN(id) AS id, video_id, title, artist, MAX(played_at) AS played_at,"
            "       COUNT(*) AS play_count "
            "FROM plays WHERE played_at >= ? "
            "GROUP BY COALESCE(NULLIF(video_id, ''), title) "
            "ORDER BY played_at DESC",
            (since,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "video_id": row["video_id"] or "",
            "title": row["title"],
            "artist": row["artist"] or "",
            "played_at": float(row["played_at"]),
            "play_count": int(row["play_count"] or 0),
        }
        for row in rows
    ]


def top(since: float | None = None, limit: int = 20) -> list[dict]:
    """Most-played online songs in `history.db`."""
    with _session() as conn:
        rows = conn.execute(
            "SELECT video_id, title, artist, COUNT(*) AS play_count, "
            "       MAX(played_at) AS last_played "
            "FROM plays WHERE played_at >= ? "
            "GROUP BY COALESCE(NULLIF(video_id, ''), title) "
            "ORDER BY play_count DESC, last_played DESC LIMIT ?",
            (_since_ts(since), int(limit)),
        ).fetchall()
    return [
        {
            "video_id": row["video_id"] or "",
            "title": row["title"],
            "artist": row["artist"] or "",
            "play_count": int(row["play_count"] or 0),
            "last_played": float(row["last_played"] or 0.0),
        }
        for row in rows
    ]


def count() -> int:
    with _session() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0])


def totals() -> dict:
    """Online-stream play totals, used by the CLI summary."""
    now = time.time()
    day_start = now - 86400
    with _session() as conn:
        row = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT COALESCE(NULLIF(video_id, ''), title)),"
            "       SUM(CASE WHEN played_at >= ? THEN 1 ELSE 0 END) "
            "FROM plays",
            (day_start,),
        ).fetchone()
    return {
        "online_plays": int(row[0] or 0),
        "online_songs": int(row[1] or 0),
        "online_today": int(row[2] or 0),
    }


def per_day(days: int = 7) -> list[tuple]:
    """`(day_offset, play_count)` for the last `days` days, oldest first."""
    now = time.time()
    out = []
    with _session() as conn:
        for offset in range(days - 1, -1, -1):
            start = now - (offset + 1) * 86400
            end = now - offset * 86400
            row = conn.execute(
                "SELECT COUNT(*) FROM plays WHERE played_at >= ? AND played_at < ?",
                (start, end),
            ).fetchone()
            out.append((offset, int(row[0] or 0)))
    return out
