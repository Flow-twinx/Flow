import errno
import fcntl
import os
import pathlib
import random
import signal
import sys
import termios
import threading
import time

from backend import config, help_detail, library, playlist, plist_cli, shortcuts
from backend.config import merge_flags
from backend.Offline import player as off_player
from backend.Online import player, savan, youtube

P = config.Primary
S = config.Secondary
T = config.Tertiary
M = config.Muted
E = config.RED
G = config.GREY
R = config.Reset

m = lambda t: print(f"{M}{t}{R}")
e = lambda t: print(f"{E}{t}{R}")
i = lambda t: print(f"{P if config.Mode == 'Online' else S}{t}{R}")

_last_results = []
_last_played = None

PAGE_STEP = 5
MAX_PAGE_RESULTS = 30

_radio_quit = False
_radio_skip = False
_radio_tracks = []


def _radio_sigint(sig, frame):
    global _radio_skip
    _radio_skip = True


def _radio_sigquit(sig, frame):
    global _radio_quit
    _radio_quit = True


def _fork_bg(label):
    config.kill_stored()
    pid = os.fork()
    if pid > 0:
        config.save_pid(pid)
        i(f"{label} in background (PID: {pid})")
        return False
    player.setup_nav_signals()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    return True


class _StopPlayback(Exception):
    """Raised by _nav_delta when playback should stop cleanly (MPRIS Stop)."""


def _clear_all_nav():
    """Drop every nav flag on both player modules.

    Called before a playback queue starts so an idle signal press (e.g. Stop
    or Prev while nothing was playing) can't poison the next queue via a stale
    flag left in the *other* module.
    """
    for mod in (player, off_player):
        mod._stop_req = False
        mod._prev_req = False
        mod._next_req = False


def _nav_delta():
    # Snapshot both modules' flags, then clear all of them. The entry-reset in
    # play_entry/play_file/play_url only touches their own module's flags, so a
    # stale flag in the other module would otherwise be misread here.
    stop = player._stop_req or off_player._stop_req
    prev = player._prev_req or off_player._prev_req
    player._stop_req = off_player._stop_req = False
    player._prev_req = off_player._prev_req = False
    player._next_req = off_player._next_req = False
    if stop:
        raise _StopPlayback
    if prev:
        return -1
    return 1


COMMANDS = {
    "play": "Play a song from YouTube",
    "search": "Search YouTube for tracks",
    "savan": "Play a song from JioSaavn (alias: svn)",
    "savan-s": "Search JioSaavn for tracks (alias: svn-s)",
    "radio": "Generate a mix | radio <song> [index] | -p save as playlist | -d download",
    "like": "Like a song",
    "unlike": "Unlike the currently playing song",
    "download": "Download audio from YouTube | -f <format> (opus, m4a, mp3, webm)",
    "delete": "Delete a downloaded song (alias: dl-d)",
    "playlist": "Manage playlists | create add remove list play rename move dup merge sort clear dedupe info export import download",
    "switch": "Switch to Offline mode",
    "help": "Show this help message",
    "short": "Show/update command shortcuts",
    "config": "Change primary/secondary/tertiary colors, format, display",
    "check": "Check all dependencies (ffmpeg, vlc, yt-dlp, psutil)",
    "export": "Backup ~/.flow config to ~/Downloads",
    "exit": "Exit Flow",
}


def run(cmd: str, extra: list[str], args):
    cmd = shortcuts.resolve(cmd)
    inf = "-i" in extra
    extra = [x for x in extra if x != "-i"]
    playlist_name = None
    if "-p" in extra:
        pi = extra.index("-p")
        extra = extra[:pi] + extra[pi + 1 :]
        if extra and not extra[0].startswith("-"):
            playlist_name = extra.pop(0)
        setattr(args, "save_playlist", playlist_name or True)
    extra, args = (
        merge_flags(extra, args)
        if cmd not in ("config", "check", "short")
        else (extra, args)
    )
    if cmd == "play":
        play(extra, args)
    elif cmd == "search":
        search(" ".join(extra) if extra else "", args)
    elif cmd in ("savan", "svn"):
        savan_cmd(extra, args)
    elif cmd in ("savan-s", "svn-s"):
        savan_search(" ".join(extra) if extra else "")
    elif cmd == "like":
        like_track()
    elif cmd == "unlike":
        unlike_track()
    elif cmd == "download":
        download(extra, args)
    elif cmd in ("delete", "dl-d"):
        delete_download(extra)
    elif cmd == "switch":
        switch_mode()
    elif cmd == "help":
        show_help(inf)
    elif cmd in ("radio", "rd"):
        radio(extra, args)
    elif cmd in ("playlist", "plist"):
        playlist_cmd(extra, args)
    elif cmd == "short":
        shortcuts.cmd_short(extra, m)
    elif cmd == "config":
        config.cmd_config(extra, args)
    elif cmd == "check":
        config.check_deps()
    elif cmd == "export":
        config.export_flow()
    else:
        print(f"Unknown command: {cmd}")


def _spinner(stop, label="Searching"):
    chars = config.SPINNER
    i = 0
    while not stop():
        sys.stdout.write(f"\r{P}{label}... {chars[i]}{R}")
        sys.stdout.flush()
        time.sleep(0.1)
        i = (i + 1) % len(chars)
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()


def _do_search(query):
    global _last_results, _radio_tracks
    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
    t.start()
    _last_results = youtube.search(query, config.MAX_SEARCH_RESULTS)
    _radio_tracks = []
    stop = True
    t.join()


def _print_results(results):
    for idx, (entry, title, dur) in enumerate(results, 1):
        mins, secs = divmod(int(dur), 60)
        uploader = entry.get("uploader", "")
        m(f"  {idx}. {_truncate_title(title)}  ({mins}:{secs:02d}) [{uploader}]")


def _fetch_more(query, limit):
    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
    t.start()
    results = youtube.search(query, limit)
    stop = True
    t.join()
    return results


def _fmt_choice(idx, entry, title, dur):
    mins, secs = divmod(int(dur), 60)
    uploader = entry.get("uploader", "")
    label = f"{idx}. {_truncate_title(title)}  ({mins}:{secs:02d})"
    if uploader:
        label += f"  [{uploader}]"
    return label


def _style():
    from ..ui import questionary_style

    return questionary_style()


def _active_flags(args):
    if args is None:
        return ""
    parts = []
    if getattr(args, "download", False):
        parts.append("download=true")
    if getattr(args, "shuffle", False):
        parts.append("shuffle=true")
    if getattr(args, "repeat", False):
        count = getattr(args, "repeat_count", 0) or 0
        parts.append("repeat=true" if count <= 0 else f"repeat=true(x{count})")
    if getattr(args, "bg", False):
        parts.append("bg=true")
    return " ".join(parts)


def _select_result(query, allow_skip, args=None):
    global _last_results
    limit = len(_last_results)
    flags = _active_flags(args)
    try:
        import questionary
    except ImportError:
        pass
    else:
        if sys.stdin.isatty():
            while True:
                choices = []
                for idx, (entry, title, dur) in enumerate(_last_results, 1):
                    choices.append(
                        questionary.Choice(
                            title=_fmt_choice(idx, entry, title, dur),
                            value=idx - 1,
                        )
                    )
                more_label = "↻ Load more results"
                choices.append(questionary.Choice(title=more_label, value="more"))
                instruction = "(↑↓ navigate, Enter to play)"
                if flags:
                    instruction = f"{flags} | {instruction}"
                try:
                    choice = questionary.select(
                        "Play which track?",
                        choices=choices,
                        default=0,
                        instruction=instruction,
                        style=_style(),
                    ).ask()
                except KeyboardInterrupt, EOFError:
                    return None
                if choice == "more":
                    if limit >= MAX_PAGE_RESULTS:
                        e("    No more results")
                        continue
                    new_limit = min(limit + PAGE_STEP, MAX_PAGE_RESULTS)
                    more = _fetch_more(query, new_limit)
                    if len(more) <= len(_last_results):
                        e("    No more results")
                        continue
                    _last_results = more
                    limit = len(_last_results)
                    continue
                if choice is None:
                    return None
                return choice

    if not sys.stdin.isatty():
        return None if allow_skip else 0
    while True:
        _print_results(_last_results)
        hint = "m for more" + (", Enter to skip" if allow_skip else ", default 1")
        if flags:
            prompt = f"Play which track? [{flags}] [1-{len(_last_results)}, {hint}] "
        else:
            prompt = f"Play which track? [1-{len(_last_results)}, {hint}] "
        try:
            choice = input(f"{P}{prompt}{R}").strip().lower()
        except EOFError, KeyboardInterrupt:
            return None if allow_skip else 0
        if choice in ("m", "more"):
            if limit >= MAX_PAGE_RESULTS:
                e("    No more results")
                continue
            limit = min(limit + PAGE_STEP, MAX_PAGE_RESULTS)
            more = _fetch_more(query, limit)
            if len(more) <= len(_last_results):
                e("    No more results")
                continue
            _last_results = more
            continue
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(_last_results):
                return idx
        if not choice:
            return None if allow_skip else 0
        e("    Invalid choice")


def _pick_result(query, allow_skip, args=None):
    return _select_result(query, allow_skip, args)


def _choose_result(query, results, args=None):
    if len(results) == 1:
        return 0
    return _pick_result(query, allow_skip=False, args=args)


def play(extra: list[str], args):
    if config.kill_stored():
        print(f"{P}Stopped VLC{R}")
    _clear_all_nav()
    global _last_results, _last_played
    arg = " ".join(extra) if extra else None
    if not arg:
        print("No song specified")
        return

    if getattr(args, "download", False):
        download(extra, args)

    if arg == "liked":
        _play_liked(args)
        return

    repeat = getattr(args, "repeat", False)
    shuffle = getattr(args, "shuffle", False)

    if arg.isdigit():
        idx = int(arg) - 1
        if idx < 0 or idx >= len(_last_results):
            print("Index out of range")
            return
        entry, title, _ = _last_results[idx]
        entry = _resolve_entry(entry)
        _last_played = (entry, title)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        if repeat:
            repeat_count = getattr(args, "repeat_count", 0)
            iteration = 0
            try:
                while True:
                    player.play_entry(entry, title, args)
                    if player._stop_req:
                        player._stop_req = False
                        break
                    iteration += 1
                    if repeat_count > 0 and iteration >= repeat_count:
                        break
            except KeyboardInterrupt, _StopPlayback:
                pass
        else:
            player.play_entry(entry, title, args)
        return

    _do_search(arg)
    if not _last_results:
        print("No results found")
        return

    if repeat or shuffle:
        results = list(_last_results)
        if shuffle:
            random.shuffle(results)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        repeat_count = getattr(args, "repeat_count", 0)
        iteration = 0
        try:
            while True:
                idx = 0
                while 0 <= idx < len(results):
                    entry, title, _ = results[idx]
                    entry = _resolve_entry(entry)
                    _last_played = (entry, title)
                    player.play_entry(
                        entry,
                        title,
                        args,
                        nav=(idx + 1 < len(results), idx > 0),
                    )
                    idx += _nav_delta()
                if not repeat:
                    break
                iteration += 1
                if repeat_count > 0 and iteration >= repeat_count:
                    break
        except KeyboardInterrupt, _StopPlayback:
            pass
    else:
        idx = _choose_result(arg, _last_results, args)
        if idx is None:
            return
        entry, title, _ = _last_results[idx]
        entry = _resolve_entry(entry)
        _last_played = (entry, title)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        player.play_entry(entry, title, args)


def resume(title, args):
    global _last_results, _last_played
    _do_search(title)
    if not _last_results:
        e("     No results found to resume")
        return
    entry, t, _ = _last_results[0]
    entry = _resolve_entry(entry)
    _last_played = (entry, t)
    if getattr(args, "bg", False):
        if not _fork_bg("Resuming"):
            return
    player.play_entry(entry, t, args)


def _resolve_entry(entry):
    if entry.get("formats"):
        return entry
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    if not url:
        return entry
    full = youtube.get_entry(url)
    return full if full else entry


def _play_liked(args):
    global _last_played
    liked = library.get_liked_entries()
    if not liked:
        e("     No liked songs yet")
        return
    if getattr(args, "bg", False):
        if not _fork_bg("Now playing"):
            return
    tracks = [(s["title"], "") for s in liked if s.get("title")]
    if not tracks:
        e("     No liked songs yet")
        return
    if getattr(args, "shuffle", False):
        random.shuffle(tracks)
    repeat = getattr(args, "repeat", False)
    repeat_count = getattr(args, "repeat_count", 0)
    iteration = 0
    try:
        while True:
            idx = 0
            while 0 <= idx < len(tracks):
                title, url = tracks[idx]
                _do_search(title)
                if not _last_results:
                    m(f"    Skipping {_truncate_title(title)} (not found)")
                    idx += 1
                    continue
                entry, _, _ = _last_results[0]
                entry = _resolve_entry(entry)
                _last_played = (entry, title)
                player.play_entry(
                    entry,
                    title,
                    args,
                    nav=(idx + 1 < len(tracks), idx > 0),
                )
                idx += _nav_delta()
            if not repeat:
                break
            iteration += 1
            if repeat_count > 0 and iteration >= repeat_count:
                break
    except KeyboardInterrupt, _StopPlayback:
        pass


_savan_results = []


def savan_cmd(extra, args):
    if config.kill_stored():
        print(f"{P}Stopped VLC{R}")
    _clear_all_nav()
    global _savan_results, _last_played
    arg = " ".join(extra) if extra else None
    if not arg:
        e("No song specified")
        return

    repeat = getattr(args, "repeat", False)
    shuffle = getattr(args, "shuffle", False)

    if arg.isdigit():
        idx = int(arg) - 1
        if idx < 0 or idx >= len(_savan_results):
            e("Index out of range")
            return
        entry, title, dur = _savan_results[idx]
        url = savan.best_url(entry)
        if not url:
            e("No playable URL found")
            return
        _last_played = (entry, title)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        if repeat:
            repeat_count = getattr(args, "repeat_count", 0)
            iteration = 0
            try:
                while True:
                    player.play_url(
                        url, title, args, dur, savan.thumb_url(entry), entry=entry
                    )
                    if player._stop_req:
                        player._stop_req = False
                        break
                    iteration += 1
                    if repeat_count > 0 and iteration >= repeat_count:
                        break
            except KeyboardInterrupt, _StopPlayback:
                pass
        else:
            player.play_url(url, title, args, dur, savan.thumb_url(entry), entry=entry)
        return

    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
    t.start()
    _savan_results = savan.search(arg)
    stop = True
    t.join()
    if not _savan_results:
        e("No results found")
        return

    if repeat or shuffle:
        results = list(_savan_results)
        if shuffle:
            random.shuffle(results)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        repeat_count = getattr(args, "repeat_count", 0)
        iteration = 0
        try:
            while True:
                idx = 0
                while 0 <= idx < len(results):
                    entry, title, dur = results[idx]
                    url = savan.best_url(entry)
                    if not url:
                        e(f"No playable URL for {_truncate_title(title)}, skipping")
                        idx += 1
                        continue
                    _last_played = (entry, title)
                    player.play_url(
                        url,
                        title,
                        args,
                        dur,
                        savan.thumb_url(entry),
                        entry=entry,
                        nav=(idx + 1 < len(results), idx > 0),
                    )
                    idx += _nav_delta()
                if not repeat:
                    break
                iteration += 1
                if repeat_count > 0 and iteration >= repeat_count:
                    break
        except KeyboardInterrupt, _StopPlayback:
            pass
    else:
        entry, title, dur = _savan_results[0]
        url = savan.best_url(entry)
        if not url:
            e("No playable URL found")
            return
        _last_played = (entry, title)
        if getattr(args, "bg", False):
            if not _fork_bg("Now playing"):
                return
        player.play_url(url, title, args, dur, savan.thumb_url(entry), entry=entry)


def savan_search(query):
    global _savan_results
    if not query:
        e("Search query required")
        return
    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
    t.start()
    _savan_results = savan.search(query)
    stop = True
    t.join()
    if not _savan_results:
        e("No results found")
        return
    for i, (_, title, dur) in enumerate(_savan_results, 1):
        mins, secs = divmod(int(dur), 60)
        m(f"  {i}. {_truncate_title(title)}  ({mins}:{secs:02d})")


def like_track():
    global _last_played
    if not _last_played:
        e("     No song currently playing")
        return
    entry, title = _last_played
    if entry is None:
        e("     No URL for current song (local track)")
        return
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    if not url:
        e("     No URL for current song")
        return
    config.dev_print(
        "Like Track",
        {
            "title": title,
            "url": url,
            "video_id": entry.get("id"),
            "webpage_url": entry.get("webpage_url"),
            "original_url": entry.get("original_url"),
        },
    )
    video_id = library.key_for(url, entry.get("id"))
    if library.is_liked(video_id):
        library.mark_unliked(video_id)
        i(f"    Unliked: {_truncate_title(title)}")
    else:
        library.mark_liked(video_id, title)
        i(f"    Liked: {_truncate_title(title)}")
        if entry.get("id"):
            try:
                library.download_thumbnail(video_id, entry.get("thumbnail"))
            except Exception:
                pass
            if not library.get_download_path(video_id):
                if config.DOWN_ON_LIKE:
                    _like_autodownload(url, video_id, title)


def _like_autodownload(url: str, video_id: str, title: str):
    fmt = config.FORMAT
    if fmt != "webm" and not config.FFMPEG:
        fmt = "webm"
    try:
        stop = False
        t = threading.Thread(
            target=_spinner,
            args=(lambda: stop, f"Downloading liked song: {_truncate_title(title)}"),
            daemon=True,
        )
        t.start()
        try:
            youtube.download_url(url, config.DOWNLOAD_DIR, fmt=fmt)
        finally:
            stop = True
            t.join()
        i(f"    Downloaded: {_truncate_title(title)}")
    except Exception as exc:
        e(f"    Auto-download failed: {exc}")


def _vid_from_thumb(thumb):
    if not thumb:
        return None
    try:
        for pat in ("/vi_webp/", "/vi/"):
            if pat in thumb:
                vid = thumb.split(pat)[1].split("/")[0].split("?")[0]
                if vid and len(vid) == 11:
                    return vid
        return None
    except Exception:
        return None


def _resolve_current(title, thumb):
    vid = _vid_from_thumb(thumb)
    if vid:
        url = f"https://www.youtube.com/watch?v={vid}"
        return url, vid
    _do_search(title)
    if not _last_results:
        return None, None
    entry, _, _ = _last_results[0]
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    return url, entry.get("id")


def act_on_current(action, title, thumb=None):
    if action == "download":
        _download_current(title, thumb)
    elif action == "unlike":
        _unlike_current(title, thumb)
    else:
        _like_current(title, thumb)


def _download_current(title, thumb):
    url, vid = _resolve_current(title, thumb)
    if not url:
        e("    Could not find the current track online")
        return
    vid = vid or _vid_from_thumb(thumb) or ""
    existing = library.get_download_path(vid) if vid else None
    if existing:
        i(f"    Already downloaded: {_truncate_title(title)}")
        return
    fmt = config.FORMAT
    if fmt != "webm" and not config.FFMPEG:
        fmt = "webm"
    stop = False
    t = threading.Thread(
        target=_spinner,
        args=(lambda: stop, f"Downloading: {_truncate_title(title)}"),
        daemon=True,
    )
    t.start()
    try:
        youtube.download_url(url, config.DOWNLOAD_DIR, fmt=fmt)
    finally:
        stop = True
        t.join()
    i(f"    Downloaded: {_truncate_title(title)}")


def _like_current(title, thumb):
    url, vid = _resolve_current(title, thumb)
    if not url:
        e("    Could not find the current track online")
        return
    if not vid:
        vid = _vid_from_thumb(thumb)
    video_id = library.key_for(url, vid)
    if library.is_liked(video_id):
        library.mark_unliked(video_id)
        i(f"    Unliked: {_truncate_title(title)}")
    else:
        library.mark_liked(video_id, title)
        i(f"    Liked: {_truncate_title(title)}")
        if vid:
            try:
                library.download_thumbnail(video_id, thumb)
            except Exception:
                pass
            if config.DOWN_ON_LIKE and not library.get_download_path(video_id):
                _like_autodownload(url, video_id, title)


def unlike_track():
    global _last_played
    if not _last_played:
        e("     No song currently playing")
        return
    entry, title = _last_played
    if entry is None:
        e("     No URL for current song (local track)")
        return
    url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    if not url:
        e("     No URL for current song")
        return
    video_id = library.key_for(url, entry.get("id"))
    if library.is_liked(video_id):
        library.mark_unliked(video_id)
        i(f"    Unliked: {_truncate_title(title)}")
    else:
        m(f"    Not liked: {_truncate_title(title)}")


def _unlike_current(title, thumb):
    url, vid = _resolve_current(title, thumb)
    if not url:
        e("    Could not find the current track online")
        return
    if not vid:
        vid = _vid_from_thumb(thumb)
    video_id = library.key_for(url, vid)
    if library.is_liked(video_id):
        library.mark_unliked(video_id)
        i(f"    Unliked: {_truncate_title(title)}")
    else:
        m(f"    Not liked: {_truncate_title(title)}")


def search(query: str, args=None):
    global _last_results, _last_played
    if not query:
        print("Search query required")
        return
    _clear_all_nav()
    _do_search(query)
    if not _last_results:
        print("No results found")
        return
    idx = _pick_result(query, allow_skip=True, args=args)
    if idx is None:
        return
    entry, title, _ = _last_results[idx]

    if args is not None and getattr(args, "download", False):
        download([str(idx + 1)], args)
        return

    entry = _resolve_entry(entry)
    _last_played = (entry, title)
    if args is not None and getattr(args, "bg", False):
        if not _fork_bg("Now playing"):
            return
    repeat = getattr(args, "repeat", False) if args is not None else False
    if repeat:
        repeat_count = getattr(args, "repeat_count", 0) if args is not None else 0
        iteration = 0
        try:
            while True:
                player.play_entry(entry, title, args)
                if player._stop_req:
                    player._stop_req = False
                    break
                iteration += 1
                if repeat_count > 0 and iteration >= repeat_count:
                    break
        except KeyboardInterrupt, _StopPlayback:
            pass
    else:
        player.play_entry(entry, title, args)


_truncate_title = config._truncate_title


def _select_radio_seed(query):
    global _last_results
    _do_search(query)
    if not _last_results:
        return None
    idx = _pick_result(query, allow_skip=True)
    if idx is None:
        return None
    entry, title, _ = _last_results[idx]
    return title


def radio(extra, args):
    if config.kill_stored():
        print(f"{P}Stopped VLC{R}")
    _clear_all_nav()
    global _radio_tracks
    query = " ".join(extra) if extra else None
    if not query:
        e("     Usage: radio <song_name> [index]")
        return

    parts = query.rsplit(" ", 1)
    if len(parts) == 1 and parts[0].isdigit():
        idx = int(parts[0]) - 1
        if _radio_tracks and 0 <= idx < len(_radio_tracks):
            title, vid, dur = _radio_tracks[idx]
            url = f"https://www.youtube.com/watch?v={vid}"
            config.dev_print(
                "Radio (play by index)",
                {
                    "title": title,
                    "video_id": vid,
                    "url": url,
                    "duration": f"{dur}s",
                },
            )
            entry = youtube.get_entry(url)
            if getattr(args, "bg", False):
                if not _fork_bg("Now playing"):
                    return
            player.play_entry(entry, title, args)
            return
        if _last_results and 0 <= idx < len(_last_results):
            entry, title, _ = _last_results[idx]
            query = title
        else:
            e("     Index out of range or no results loaded")
            return
    elif len(parts) > 1 and parts[-1].isdigit():
        idx = int(parts[-1]) - 1
        query = parts[0]
        if _radio_tracks and 0 <= idx < len(_radio_tracks):
            title, vid, dur = _radio_tracks[idx]
            url = f"https://www.youtube.com/watch?v={vid}"
            config.dev_print(
                "Radio (play by query+index)",
                {
                    "title": title,
                    "video_id": vid,
                    "url": url,
                    "duration": f"{dur}s",
                },
            )
            entry = youtube.get_entry(url)
            if getattr(args, "bg", False):
                if not _fork_bg("Now playing"):
                    return
            player.play_entry(entry, title, args)
            return
        e("     Index out of range or no radio loaded")
        return

    seed = _select_radio_seed(query)
    if not seed:
        return

    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
    t.start()
    tracks = youtube.fetch_radio(seed, config.MAX_RESULTS_RADIO)
    stop = True
    t.join()

    if not tracks:
        e("     No radio tracks found")
        return

    _radio_tracks = tracks

    save_pl = getattr(args, "save_playlist", None)
    pl_name = save_pl if isinstance(save_pl, str) else tracks[0][0]
    if save_pl:
        if not playlist.exists(pl_name):
            playlist.create(pl_name)
        added = skipped = 0
        for title, vid, dur in _radio_tracks:
            url = f"https://www.youtube.com/watch?v={vid}"
            state, _ = playlist.add_track(
                pl_name,
                playlist.make_track(
                    title=title, ref=url, video_id=vid, duration=int(dur or 0)
                ),
            )
            if state == "added":
                added += 1
            elif state == "skipped":
                skipped += 1
        msg = f"    Saved {added} tracks to playlist: {pl_name}"
        if skipped:
            msg += f" ({skipped} duplicates skipped)"
        i(msg)
        if not getattr(args, "download", False):
            return

    if getattr(args, "download", False):
        dl_dir = playlist.download_dir(pl_name) if save_pl else config.DOWNLOAD_DIR
    else:
        dl_dir = None

    if getattr(args, "shuffle", False):
        random.shuffle(_radio_tracks)

    global _radio_quit, _radio_skip
    _radio_quit = False
    _radio_skip = False

    if getattr(args, "bg", False):
        if not _fork_bg(f"Playing {len(_radio_tracks)} tracks"):
            return

    old_sigint = signal.signal(signal.SIGINT, _radio_sigint)
    old_sigquit = signal.signal(signal.SIGQUIT, _radio_sigquit)
    old_sigusr1 = signal.getsignal(signal.SIGUSR1)

    fd = sys.stdin.fileno()
    tty_fd = None
    old_term = None
    old_fd_flags = None
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
        ctl = tty_fd
    except OSError:
        ctl = fd
    try:
        old_term = termios.tcgetattr(ctl)
        new = termios.tcgetattr(ctl)
        new[0] &= ~termios.IXON
        new[6][termios.VQUIT] = 0x11
        new[6][termios.VSUSP] = 0
        termios.tcsetattr(ctl, termios.TCSADRAIN, new)
        old_fd_flags = fcntl.fcntl(ctl, fcntl.F_GETFL)
        fcntl.fcntl(ctl, fcntl.F_SETFL, old_fd_flags | os.O_NONBLOCK)
    except termios.error, OSError:
        pass

    def _radio_sigusr1(sig, frame):
        player._sigusr1_toggle(sig, frame)

    signal.signal(signal.SIGUSR1, _radio_sigusr1)
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)
    player._radio_active = True

    radio_stop = threading.Event()

    def _radio_input_reader():
        try:
            while not radio_stop.is_set():
                try:
                    ch = os.read(ctl, 1)
                except OSError as ex:
                    if ex.errno == errno.EAGAIN:
                        time.sleep(0.05)
                        continue
                    break
                if not ch:
                    break
                if ch == b"\x10":
                    os.kill(os.getpid(), signal.SIGUSR1)
        except OSError:
            pass

    radio_reader = threading.Thread(target=_radio_input_reader, daemon=True)
    radio_reader.start()

    flags = {"quit": lambda: _radio_quit, "skip": lambda: _radio_skip}

    repeat = getattr(args, "repeat", False)
    repeat_count = getattr(args, "repeat_count", 0)
    iteration = 0

    try:
        while True:
            idx = 0
            while 0 <= idx < len(_radio_tracks) and not _radio_quit:
                title, vid, dur = _radio_tracks[idx]
                url = f"https://www.youtube.com/watch?v={vid}"
                config.dev_print(
                    "Radio (playing track)",
                    {
                        "title": title,
                        "video_id": vid,
                        "url": url,
                        "duration": f"{dur}s",
                        "position": f"{idx + 1}/{len(_radio_tracks)}",
                    },
                )
                entry = youtube.get_entry(url)

                next_title = None
                if idx + 1 < len(_radio_tracks):
                    n_title, n_vid, n_dur = _radio_tracks[idx + 1]
                    next_title = n_title
                    n_short = _truncate_title(n_title)
                    n_mins, n_secs = divmod(int(n_dur), 60)
                    print(f"{T}\n\t[⥤ Next: {n_short:30s} {n_mins}:{n_secs:02d}]{R}")

                _radio_skip = False
                if dl_dir:
                    filepath = youtube.download_url(url, dl_dir)
                    i(
                        f"    Downloaded ({idx + 1}/{len(_radio_tracks)}): {_truncate_title(title)}"
                    )
                    off_player.play_file(
                        filepath,
                        title,
                        args,
                        next_title=next_title,
                        nav=(idx + 1 < len(_radio_tracks), idx > 0),
                    )
                else:
                    player.play_entry(
                        entry,
                        title,
                        args,
                        flags=flags,
                        next_title=next_title,
                        nav=(idx + 1 < len(_radio_tracks), idx > 0),
                    )
                idx += _nav_delta()
            if not repeat or _radio_quit:
                break
            iteration += 1
            if repeat_count > 0 and iteration >= repeat_count:
                break
    except KeyboardInterrupt, _StopPlayback:
        _radio_quit = True
    finally:
        player._radio_active = False
        radio_stop.set()
        if radio_reader.is_alive():
            radio_reader.join(timeout=0.2)
        if old_term is not None:
            try:
                if old_fd_flags is not None:
                    fcntl.fcntl(ctl, fcntl.F_SETFL, old_fd_flags)
                termios.tcsetattr(ctl, termios.TCSADRAIN, old_term)
            except termios.error, OSError:
                pass
        if tty_fd is not None:
            try:
                os.close(tty_fd)
            except OSError:
                pass
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGQUIT, old_sigquit)
        signal.signal(signal.SIGUSR1, old_sigusr1)


def download(extra: list[str], args=None):
    global _last_results
    fmt = None
    if args is not None and getattr(args, "format", None):
        fmt = str(args.format).lower()
    elif "-f" in extra:
        fi = extra.index("-f")
        if fi + 1 < len(extra):
            fmt = extra[fi + 1].lower()
            extra = extra[:fi] + extra[fi + 2 :]
        else:
            e("Usage: download <query> -f <format>")
            return
    if fmt and fmt not in ("opus", "m4a", "mp3", "webm"):
        e("Unknown format. Options: opus, m4a, mp3, webm")
        return
    if not fmt:
        fmt = config.FORMAT
    if fmt != "webm" and not config.FFMPEG:
        e(f"ffmpeg not found. Cannot convert to {fmt}. Install ffmpeg or use webm.")
        return

    arg = " ".join(extra) if extra else None
    if not arg:
        e("No song specified")
        return

    url = None
    title = "Unknown"
    if arg.isdigit():
        idx = int(arg) - 1
        if idx < 0 or idx >= len(_last_results):
            e("     Index out of range")
            return
        entry, _, _ = _last_results[idx]
        url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
        if not url and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        title = entry.get("title", "Unknown")
    else:
        _do_search(arg)
        if not _last_results:
            e("     No results found")
            return
        idx = _choose_result(arg, _last_results, args)
        if idx is None:
            return
        entry, _, _ = _last_results[idx]
        url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
        if not url and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        title = entry.get("title", "Unknown")

    if not url:
        e("     No URL found for this entry")
        return

    vid = entry.get("id") or ""
    if vid:
        existing = library.get_download_path(vid)
        if existing:
            existing_ext = pathlib.Path(existing).suffix.lstrip(".").lower()
            if existing_ext == fmt:
                i(f"    Already downloaded: {_truncate_title(title)}")
                return

    label = f"Downloading: {_truncate_title(title)}"
    if fmt != "webm":
        label += f" → {fmt}"
    stop = False
    t = threading.Thread(target=_spinner, args=(lambda: stop, label), daemon=True)
    t.start()
    try:
        youtube.download_url(url, config.DOWNLOAD_DIR, fmt=fmt)
    finally:
        stop = True
        t.join()
    if fmt != "webm":
        i(f"    Downloaded and converted to {fmt}: {_truncate_title(title)}")
    else:
        i(f"    Downloaded: {_truncate_title(title)}")


# def backfill_metadata():
#     ids = library.get_downloaded_ids()
#     if not ids:
#         e("     No downloaded songs in the library")
#         return 1
#     import yt_dlp

#     i(f"    Fetching metadata for {len(ids)} downloaded songs...")
#     updated = 0
#     skipped = 0
#     failed = 0
#     for pos, video_id in enumerate(ids, 1):
#         tag = f"[{pos}/{len(ids)}] {video_id}"
#         existing = library.get(video_id) or {}
#         if existing.get("artist") or existing.get("duration"):
#             skipped += 1
#             continue
#         try:
#             with yt_dlp.YoutubeDL(youtube.ydl_opts_play) as ydl:
#                 info = ydl.extract_info(
#                     f"https://www.youtube.com/watch?v={video_id}", download=False
#                 )
#         except Exception as exc:
#             failed += 1
#             m(f"    {tag}: failed ({exc})")
#             continue
#         if not info:
#             failed += 1
#             m(f"    {tag}: no metadata returned")
#             continue
#         meta = library.meta_from_info(info)
#         meta["title"] = info.get("title", "")
#         library.update_meta(video_id, meta)  # saves library.json right here
#         updated += 1
#         label = meta.get("title") or video_id
#         artist = meta.get("artist") or ""
#         album = f" [{meta['album']}]" if meta.get("album") else ""
#         dur = meta.get("duration")
#         dur_s = f" ({dur // 60}:{dur % 60:02d})" if dur else ""
#         i(
#             f"    {tag}: {_truncate_title(label)}{dur_s}{album}"
#             + (f" — {artist}" if artist else "")
#         )
#     tail = f" ({skipped} already done, {failed} failed)" if skipped or failed else ""
#     print(f"\n{P}Backfilled metadata for {updated}/{len(ids)} songs{R}{tail}")
#     return 0


def backfill_metadata():
    """Rebuild library.json entries for the downloaded songs on disk.

    If ~/.flow gets wiped, library.json is gone but the audio files under
    ~/.flow/downloads/ usually survive — they are named <video_id>.<ext>,
    so the video id is recoverable straight from the filename. This scans
    the download dir, fetches metadata + thumbnail for each id and
    (re)creates the library entries. Idempotent: ids that already carry
    metadata in the library are skipped.
    """
    files = sorted(
        f
        for f in config.DOWNLOAD_DIR.rglob("*")
        if f.is_file() and f.suffix.lower() in _AUDIO_EXTS
    )
    if not files:
        m("     No downloaded songs found in ~/.flow/downloads")
        return 1

    import yt_dlp

    i(f"    Rebuilding library entries for {len(files)} downloaded file(s)...")
    updated = 0
    skipped = 0
    failed = 0
    with yt_dlp.YoutubeDL(youtube.ydl_opts_play) as ydl:
        for pos, f in enumerate(files, 1):
            video_id = f.stem
            tag = f"[{pos}/{len(files)}] {video_id}"
            existing = library.get(video_id) or {}
            if (
                existing.get("title")
                or existing.get("artist")
                or existing.get("duration")
            ):
                skipped += 1
                continue
            try:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
            except Exception as exc:
                failed += 1
                m(f"    {tag}: failed ({exc})")
                continue
            if not info:
                failed += 1
                m(f"    {tag}: no metadata returned")
                continue
            title = info.get("title") or ""
            meta = library.meta_from_info(info)
            library.track_download(video_id, str(f), title, meta)  # saves library.json right here
            try:
                library.download_thumbnail(video_id)
            except Exception:
                pass
            updated += 1
            label = _truncate_title(title) if title else video_id
            artist = meta.get("artist") or ""
            album = f" [{meta['album']}]" if meta.get("album") else ""
            dur = meta.get("duration")
            dur_s = f" ({dur // 60}:{dur % 60:02d})" if dur else ""
            i(
                f"    {tag}: {label}{dur_s}{album}"
                + (f" — {artist}" if artist else "")
            )
    tail = f" ({skipped} already done, {failed} failed)" if skipped or failed else ""
    print(f"\n{P}Rebuilt metadata for {updated}/{len(files)} songs{R}{tail}")
    return 0


_AUDIO_EXTS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".ogg",
    ".opus",
    ".wma",
    ".aac",
    ".webm",
}


def _find_vid_by_path(index, path):
    for _vid, info in index.items():
        if info.get("path") == path:
            return _vid
    return None


def delete_download(extra: list[str]):
    global _last_results
    arg = " ".join(extra) if extra else None
    if not arg:
        e("Usage: delete <name | index>")
        return

    vid = None
    title = None
    if arg.isdigit():
        idx = int(arg) - 1
        if idx < 0 or idx >= len(_last_results):
            e("     Index out of range")
            return
        entry, title, _ = _last_results[idx]
        vid = entry.get("id")
    else:
        index = library.load()
        matches = [
            (_vid, info.get("path"), info.get("title", ""))
            for _vid, info in index.items()
            if arg.lower() in info.get("title", "").lower()
            or arg.lower() in (_vid or "").lower()
        ]
        if len(matches) == 1:
            vid, _, title = matches[0]
        elif len(matches) > 1:
            m("    Multiple matches:")
            for i, (_vid, _path, t) in enumerate(matches, 1):
                m(f"      {i}. {_truncate_title(t)}")
            return
        else:
            candidates = [
                f
                for f in sorted(config.DOWNLOAD_DIR.rglob("*"))
                if f.is_file()
                and f.suffix.lower() in _AUDIO_EXTS
                and (
                    arg.lower() in f.stem.lower()
                    or arg.lower() in library.title_for_stem(f.stem).lower()
                )
            ]
            if not candidates:
                e(f"     No downloaded song matching '{arg}'")
                return
            if len(candidates) > 1:
                m("    Multiple matches:")
                for i, f in enumerate(candidates, 1):
                    m(f"      {i}. {library.title_for_stem(f.stem)}")
                return
            path = str(candidates[0])
            vid = _find_vid_by_path(index, path)
            title = library.title_for_stem(candidates[0].stem)

    if not vid:
        e("     No video id found for this song")
        return

    path = library.get_download_path(vid)
    if not path:
        e("     Song not found in downloads")
        return

    try:
        ans = input(
            f"{M}Delete '{_truncate_title(title or pathlib.Path(path).stem)}'? (y/N) {R}"
        )
    except EOFError:
        return
    if ans.strip().lower() not in ("y", "yes"):
        m("    Cancelled")
        return

    if library.delete(vid):
        i(f"    Deleted: {_truncate_title(title or pathlib.Path(path).stem)}")
    else:
        e("     Nothing to delete")


def switch_mode():
    config.Mode = "Offline"


def playlist_cmd(extra, args):
    global _last_played
    _clear_all_nav()

    def add_source(target_words, args):
        target = target_words[0]
        if target.isdigit():
            idx = int(target) - 1
            if idx < 0 or idx >= len(_last_results):
                e("Index out of range")
                return None
            entry, title, dur = _last_results[idx]
        else:
            query = " ".join(target_words)
            _do_search(query)
            if not _last_results:
                e("No results found")
                return None
            entry, title, dur = _last_results[0]
        vid = entry.get("id", "")
        url = (
            entry.get("webpage_url")
            or entry.get("url")
            or f"https://www.youtube.com/watch?v={vid}"
        )
        track = playlist.make_track(
            title=title, ref=url, video_id=vid, duration=int(dur or 0)
        )
        local = playlist.find_local_copy(vid)
        if local:
            track["local_path"] = local
        return track

    def play(actual, tracks, args):
        global _last_played
        tracks = list(tracks)
        if getattr(args, "shuffle", False):
            random.shuffle(tracks)
        repeat = getattr(args, "repeat", False)
        repeat_count = getattr(args, "repeat_count", 0)
        iteration = 0
        if getattr(args, "bg", False):
            if not _fork_bg(f"Playing playlist: {actual}"):
                return
        try:
            while True:
                idx = 0
                while 0 <= idx < len(tracks):
                    s = tracks[idx]
                    title = s.get("title", "Unknown")
                    short = _truncate_title(title)
                    src = playlist.resolve_track(s)
                    next_title = (
                        tracks[idx + 1].get("title") if idx + 1 < len(tracks) else None
                    )
                    if isinstance(src, pathlib.Path):
                        print(
                            f"{P}Playing local copy: {short}...{R}",
                            end="\r",
                            flush=True,
                        )
                        _last_played = (None, title)
                        playlist.backfill_local(actual, idx, src)
                        off_player.play_file(
                            src,
                            title,
                            args,
                            next_title=next_title,
                            nav=(idx + 1 < len(tracks), idx > 0),
                        )
                        idx += _nav_delta()
                        continue
                    vid = s.get("id", "")
                    url = src or f"https://www.youtube.com/watch?v={vid}"
                    print(f"{P}Fetching: {short}...{R}", end="\r", flush=True)
                    entry = youtube.get_entry(url)
                    if not entry:
                        m(f"    Skipping {short} (unavailable)")
                        idx += 1
                        continue
                    _last_played = (entry, title)
                    player.play_entry(
                        entry,
                        title,
                        args,
                        next_title=next_title,
                        nav=(idx + 1 < len(tracks), idx > 0),
                    )
                    idx += _nav_delta()
                if not repeat:
                    break
                iteration += 1
                if repeat_count > 0 and iteration >= repeat_count:
                    break
        except KeyboardInterrupt, _StopPlayback:
            pass

    def list_liked():
        liked = library.get_liked_entries()
        if not liked:
            m("No liked songs yet")
            return
        i("  liked:")
        for idx, s in enumerate(liked, 1):
            m(f"  {idx}. {_truncate_title(s.get('title', 'Unknown'))}")

    def download(actual, tracks, args):
        dl_dir = playlist.download_dir(actual)
        i(f"    Downloading {len(tracks)} songs to {dl_dir}...")
        done = 0
        for idx, s in enumerate(tracks, 1):
            vid = s.get("id", "")
            url = s.get("ref") or f"https://www.youtube.com/watch?v={vid}"
            try:
                youtube.download_url(url, dl_dir)
                local = playlist.find_local_copy(vid) or str(dl_dir)
                playlist.backfill_local(actual, idx - 1, local)
                done += 1
                i(
                    f"    Downloaded ({idx}/{len(tracks)}): {_truncate_title(s.get('title'))}"
                )
            except Exception as exc:
                e(
                    f"     Failed ({idx}/{len(tracks)}): {_truncate_title(s.get('title'))} - {exc}"
                )
        if done == len(tracks):
            i(f"    All {done} tracks available on device")

    plist_cli.handle(
        extra,
        args,
        {
            "add_source": add_source,
            "play": play,
            "play_liked": _play_liked,
            "list_liked": list_liked,
            "download": download,
        },
    )


def show_help(inf=False):
    if inf:
        print(f"{T}Online Commands (detailed):{R}")
        for cmd, lines in help_detail._online_help().items():
            for line in lines:
                print(f"  {line}")
            print()
    else:
        print(f"{T}Online Commands:{R}")
        for cmd, desc in COMMANDS.items():
            print(f"  {T}{cmd:12s}{R} {G}{desc}{R}")
        print(
            f"  {T}plugins{R} {G}install/list/run/update Flow plugins | flow plugins list{R}"
        )
        print(f"{G}  Use 'help -i' for detailed usage{R}")
