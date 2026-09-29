"""`summary` — play-count reporting for the CLI (shared by both modes).

Reads the *whole* picture: `library.db` holds `song_count` for every song in
every mode, while `history.db` holds the online-only play timeline. The ranked
table below therefore counts local playback too, which is the point — the web
History panel is the online-only view of the same data.

Sort keys differ from the web History panel on purpose: the CLI ranks a
per-song table (`plays`, `recent`, `name`, `artist`) because a terminal is bad
at showing a long event log; the web panel sorts a timeline
(`recent`, `oldest`, `most`, `least`) because a scrollable column is bad at
showing aggregates.
"""

import shutil
import time

from backend import config, history, library

P = config.Primary
T = config.Tertiary
M = config.Muted
E = config.RED
G = config.GREY
R = config.Reset

#: `--sort` keys, in the order they are listed in the help text.
SORTS = ("plays", "recent", "name", "artist")

COMMANDS = {
    "summary": "Play summary | -l per-song table | -s <sort> | --top N | -c clear history",
}

DEFAULT_SORT = "plays"
DEFAULT_TOP = 20


def _tty_width(default: int = 96) -> int:
    try:
        return max(72, min(140, shutil.get_terminal_size().columns))
    except Exception:
        return default


def _ago(ts: float) -> str:
    if not ts:
        return "never"
    delta = max(0.0, time.time() - ts)
    mins = delta / 60
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{int(mins)}m ago"
    hours = mins / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    if days < 365:
        return f"{int(days / 7)}w ago"
    return f"{int(days / 365)}y ago"


def _truncate(text: str, width: int) -> str:
    text = text or ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _parse_args(extra: list[str]) -> dict:
    """Pull our own flags out of `extra`.

    `merge_flags` never sees these (the command modules exclude `summary`), so
    `-l` / `-s` / `--top` survive to get here instead of being eaten as
    playback flags.
    """
    opts = {
        "list": False,
        "sort": DEFAULT_SORT,
        "top": DEFAULT_TOP,
        "clear": False,
        "help": False,
        "rest": [],
    }
    i = 0
    while i < len(extra):
        token = extra[i]
        if token in ("-l", "--list"):
            opts["list"] = True
        elif token in ("-h", "--help", "-?"):
            opts["help"] = True
        elif token == "-c" or token == "--clear":
            opts["clear"] = True
        elif token in ("-s", "--sort"):
            i += 1
            if i >= len(extra):
                opts["sort"] = None
                break
            value = extra[i].lower()
            opts["sort"] = value if value in SORTS else None
        elif token.startswith("--sort="):
            value = token.split("=", 1)[1].lower()
            opts["sort"] = value if value in SORTS else None
        elif token in ("-n", "--top"):
            i += 1
            if i >= len(extra):
                opts["top"] = DEFAULT_TOP
                break
            opts["top"] = extra[i]
        elif token.startswith("--top="):
            opts["top"] = token.split("=", 1)[1]
        else:
            opts["rest"].append(token)
        i += 1
    try:
        opts["top"] = max(1, min(int(opts["top"]), 500))
    except (TypeError, ValueError):
        opts["top"] = DEFAULT_TOP
    return opts


def _sort_rows(rows: list[dict], sort: str) -> list[dict]:
    if sort == "recent":
        return sorted(rows, key=lambda r: r["last_played"], reverse=True)
    if sort == "name":
        return sorted(rows, key=lambda r: r["title"].lower())
    if sort == "artist":
        return sorted(rows, key=lambda r: (r["artist"].lower(), r["title"].lower()))
    return sorted(
        rows,
        key=lambda r: (r["song_count"], r["last_played"]),
        reverse=True,
    )


def _box(title: str, rows: list[tuple], width: int) -> None:
    """The same `┌─ Title ─┐` card `flow --status` prints."""
    inner = width - 2
    print(f"\n{P}┌─ {title} {'─' * max(0, inner - len(title) - 4)}{R}")
    for label, value in rows:
        text = f"  {label:<16}{value}"
        print(f"{P}│{R} {_truncate(text, inner - 1)}")
    print(f"{P}└{'─' * inner}{R}\n")


def _top_artist(rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        artist = (row.get("artist") or "").strip()
        if not artist:
            continue
        counts[artist] = counts.get(artist, 0) + row["song_count"]
    if not counts:
        return "-"
    best = max(counts.items(), key=lambda kv: kv[1])
    return f"{best[0]} {G}({best[1]} plays){R}"


def show_stats() -> None:
    lib = library.stats()
    online = history.totals()
    rows = library.play_rows()
    width = _tty_width()
    _box(
        "Flow Summary",
        [
            ("total plays", f"{G}{lib['total_plays']}{R}"),
            ("unique songs", f"{G}{lib['unique_songs']}{R}"),
            ("played today", f"{G}{lib['played_today']}{R}"),
            (
                "online plays",
                f"{G}{online['online_plays']}{R} {M}(history.db){R}",
            ),
            (
                "top artist",
                _top_artist(rows) if rows else f"{M}no plays yet{R}",
            ),
        ],
        width,
    )
    if not rows:
        return
    week = history.per_day(7)
    bar_width = 24
    peak = max((c for _, c in week), default=0)
    print(f"{T}  last 7 days{R}")
    if peak:
        for offset, count in week:
            filled = int(round((count / peak) * bar_width))
            label = "today" if offset == 0 else f"-{offset}d"
            print(
                f"  {M}{label:>6}{R} {P}{'█' * filled}{R}"
                f"{G}{' ' * (bar_width - filled)}{R} {count}"
            )
    else:
        print(f"  {M}no online plays logged in the last 7 days{R}")
    print()


def show_table(sort: str = DEFAULT_SORT, top: int = DEFAULT_TOP) -> None:
    rows = _sort_rows(library.play_rows(), sort)
    if not rows:
        print(f"{M}Nothing has been played yet{R}")
        return
    shown = rows[:top]
    title_w = max(12, _tty_width() - 52)
    # Width of the header rule, measured without the colour codes.
    rule_w = 2 + 6 + 2 + 12 + 2 + 16 + 2 + 5
    print()
    print(f"  {T}{'PLAYS':>6}  {'LAST PLAYED':<12}  {'ARTIST':<16}  TITLE{R}")
    print(f"  {G}{'─' * rule_w}{R}")
    for row in shown:
        plays = row["song_count"]
        color = P if plays > 1 else M
        artist = _truncate(row["artist"] or "-", 16).ljust(16)
        print(
            f"  {color}{plays:>6}{R}  "
            f"{M}{_ago(row['last_played']):<12}{R}  "
            f"{G}{artist}{R}  "
            f"{_truncate(row['title'], title_w)}"
        )
    print()
    if len(rows) > len(shown):
        print(f"{M}  showing {len(shown)} of {len(rows)} — --top N for more{R}")
    print()


def clear_history() -> None:
    removed = history.clear()
    print(f"{P}Cleared {removed} logged online play(s){R}")
    print(f"{M}  song_count totals in library.db are untouched{R}")


def cmd_summary(extra: list[str], args=None) -> None:
    opts = _parse_args(list(extra or []))
    if opts["help"]:
        print_help()
        return
    if opts["sort"] is None:
        print(f"{E}Unknown sort key. Use one of: {', '.join(SORTS)}{R}")
        return
    if opts["clear"]:
        clear_history()
        return
    if opts["list"]:
        show_table(opts["sort"], opts["top"])
    else:
        show_stats()


def print_help() -> None:
    print(f"{T}summary{R} {M}[-l] [-s sort] [--top N] [-c]{R}")
    print(f"{G}  Play statistics, and the ranked per-song table.{R}")
    print(f"  {M}-l{R}          {G}List the per-song table instead of the stats card{R}")
    print(f"  {M}-s{R} {M}<sort>{R}   {G}Table sort: {', '.join(SORTS)} (default: {DEFAULT_SORT}){R}")
    print(f"  {M}--top{R} {M}<N>{R}    {G}Rows to show in the table (default: {DEFAULT_TOP}){R}")
    print(f"  {M}-c{R}          {G}Clear the online play history (history.db){R}")
    print(f"{G}  Counts come from library.db (every mode); the web History panel{R}")
    print(f"{G}  shows the online-only timeline from history.db.{R}")
    print()
