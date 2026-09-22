import atexit
import curses
import errno
import fcntl
import os
import pathlib
import signal
import sys
import termios
import threading
import time

import vlc

from backend import config, library, mpris, status, visualizer

_truncate_title = config._truncate_title

P = config.Primary
S = config.Secondary
T = config.Tertiary


M = config.Muted
E = config.RED
R = config.Reset

m = lambda t: print(f"{M}{t}{R}")
e = lambda t: print(f"{E}{t}{R}")
i = lambda t: print(f"{P if config.Mode == 'Online' else S}{t}{R}")
ter = lambda t: print(f"{T}{t}{R}")

_paused = False
_player = None
_original_term = None
_radio_active = False
_stop_reader = threading.Event()
_reader_thread = None

_next_req = False
_prev_req = False
_stop_req = False
_nav = (False, False)


def _clear_stale_pid():
    if config.read_pid() == os.getpid():
        config.clear_pid()


atexit.register(_clear_stale_pid)


def _sigusr1_toggle(sig, frame):
    global _paused
    _paused = not _paused
    if _player:
        _player.pause()


def _sigusr2_next(sig, frame):
    global _next_req
    _next_req = True
    if _player:
        _player.stop()


def _sigusr3_prev(sig, frame):
    global _prev_req
    _prev_req = True
    if _player:
        _player.stop()


def _sigusr4_stop(sig, frame):
    global _stop_req
    _stop_req = True
    if _player:
        _player.stop()


def _seek_current(sig, frame):
    delta_ms = config.read_seek()
    config.clear_seek()
    if _player and delta_ms:
        cur = _player.get_time()
        if cur is not None and cur >= 0:
            _player.set_time(max(0, int(cur) + delta_ms))


def setup_nav_signals():
    signal.signal(signal.SIGUSR1, _sigusr1_toggle)
    signal.signal(signal.SIGUSR2, _sigusr2_next)
    signal.signal(config.SIG_PREV, _sigusr3_prev)
    signal.signal(config.SIG_STOP_ALL, _sigusr4_stop)
    signal.signal(config.SIG_SEEK_FWD, _seek_current)
    signal.signal(config.SIG_SEEK_BWD, _seek_current)


def _setup_pause_input():
    global _original_term
    if _radio_active:
        signal.signal(signal.SIGUSR1, _sigusr1_toggle)
        setup_nav_signals()
        return
    fd = sys.stdin.fileno()
    try:
        _original_term = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[0] &= ~termios.IXON
        new[6][termios.VSUSP] = 0
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
    except termios.error, OSError:
        _original_term = None
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    signal.signal(signal.SIGUSR1, _sigusr1_toggle)
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)
    setup_nav_signals()
    _stop_reader.clear()
    _reader_thread = threading.Thread(target=_input_reader, daemon=True)
    _reader_thread.start()


def _input_reader():
    fd = sys.stdin.fileno()
    try:
        while not _stop_reader.is_set():
            try:
                ch = os.read(fd, 1)
            except OSError as ex:
                if ex.errno == errno.EAGAIN:
                    time.sleep(0.05)
                    continue
                break
            if ch == b"\x10":
                os.kill(os.getpid(), signal.SIGUSR1)
    except OSError:
        pass


def _restore_pause_input():
    global _original_term, _reader_thread
    _stop_reader.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=0.2)
    _reader_thread = None
    if _original_term is not None:
        try:
            fd = sys.stdin.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
            termios.tcsetattr(fd, termios.TCSADRAIN, _original_term)
        except termios.error, OSError:
            pass
        _original_term = None


def _flags_str(args):
    if not args:
        return ""
    parts = []
    if getattr(args, "repeat", False):
        count = getattr(args, "repeat_count", 0)
        parts.append(f"[Repeat:{'∞' if count < 0 else count}]")
    if getattr(args, "shuffle", False):
        parts.append("[Shuffle:On]")
    return "  ".join(parts)


def _restart_current(player):
    global _prev_req, _paused
    if _next_req or _stop_req:
        return False
    if not _nav[1]:
        _prev_req = False
        _paused = False
        try:
            player.play()
            player.set_time(0)
        except Exception:
            # Failed to restart: don't claim success, or the display loop
            # would spin forever waiting for a state that never changes.
            return False
        return True
    return False


def _attach_vlc_events():
    p = _player
    if p is None:
        return
    try:
        em = p.event_manager()
    except Exception:
        return

    def _on_event(event):
        try:
            t = event.type
            if t == vlc.EventType.MediaPlayerPlaying:
                mpris.set_status(mpris.PLAYING)
            elif t == vlc.EventType.MediaPlayerPaused:
                mpris.set_status(mpris.PAUSED)
            elif t in (
                vlc.EventType.MediaPlayerStopped,
                vlc.EventType.MediaPlayerEndReached,
            ):
                mpris.set_status(mpris.STOPPED)
        except Exception:
            pass

    for etype in (
        vlc.EventType.MediaPlayerPlaying,
        vlc.EventType.MediaPlayerPaused,
        vlc.EventType.MediaPlayerStopped,
        vlc.EventType.MediaPlayerEndReached,
    ):
        try:
            em.event_attach(etype, _on_event)
        except Exception:
            pass


def _display_loop(player, title=None, args=None, next_title=None, stop_check=None):
    global _paused
    display = config.Display
    if display == "bars" and not (sys.stdin.isatty() and sys.stdout.isatty()):
        display = "none"
    if display == "none":
        while player.get_state() not in (vlc.State.Ended, vlc.State.Error):
            if stop_check and stop_check():
                break
            if _stop_req or _next_req:
                break
            if _prev_req:
                if _restart_current(player):
                    continue
                break
            time.sleep(0.1)
        return

    if display == "bars":
        shuffle = bool(getattr(args, "shuffle", False))
        repeat = bool(getattr(args, "repeat", False))
        visualizer.set_status(
            title, shuffle=shuffle, repeat=repeat, next_title=next_title
        )

    if display == "bars":
        stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        stdscr.keypad(True)
        if not visualizer.start(stdscr, S):
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.curs_set(1)
            curses.endwin()
            return

    paused_printed = False
    try:
        while player.get_state() not in (vlc.State.Ended, vlc.State.Error):
            if stop_check and stop_check():
                break
            if _stop_req or _next_req:
                break
            if _prev_req:
                if _restart_current(player):
                    continue
                break
            if _paused:
                if not paused_printed:
                    visualizer.set_paused(True)
                    if display == "bars":
                        try:
                            stdscr.addstr(0, 0, "  [Paused]  ", curses.A_BOLD)
                            stdscr.refresh()
                        except curses.error:
                            pass
                    else:
                        sys.stdout.write(f"\r  {T}[Paused]{R}  ")
                        sys.stdout.flush()
                    paused_printed = True
                try:
                    time.sleep(0.1)
                except OSError:
                    pass
                continue
            if paused_printed:
                visualizer.set_paused(False)
                paused_printed = False
            if display == "bars":
                visualizer.draw()
            try:
                time.sleep(0.08)
            except OSError:
                pass
    finally:
        if display == "bars":
            visualizer.stop()
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.curs_set(1)
            curses.endwin()
        else:
            sys.stdout.write("\r" + " " * 60 + "\r\n")
            sys.stdout.flush()


def play_file(filepath, title, args=None, flags=None, next_title=None, nav=None):
    global _player, _paused, _next_req, _prev_req, _stop_req, _nav
    _paused = False
    _next_req = False
    _prev_req = False
    _stop_req = False
    _nav = tuple(nav) if nav else (False, False)
    config.save_pid(os.getpid())
    config.clear_seek()
    devnull = os.open(os.devnull, os.O_RDWR)
    old_stderr = os.dup(2)
    os.dup2(devnull, 2)
    try:
        instance = vlc.Instance("--no-video --quiet")
        _player = instance.media_player_new()
        media = instance.media_new(str(filepath))
        _player.set_media(media)
        _player.play()
        _setup_pause_input()

        duration = 0
        for _ in range(50):
            duration = _player.get_length() / 1000
            if duration > 0:
                break
            time.sleep(0.1)
        if duration <= 0:
            duration = 0
        thumb = library.thumbnail_path(filepath.stem)
        if not pathlib.Path(thumb).exists():
            thumb = None
        status.update(title, duration, thumbnail=thumb)
        dur_min, dur_sec = divmod(int(duration), 60)
        flags_str = _flags_str(args)
        if config.Display != "bars":
            i(f"\nPlaying : {_truncate_title(title)}")
            m(
                f"    [{dur_min}:{dur_sec:02d}]  {flags_str}"
                if flags_str
                else f"    [{dur_min}:{dur_sec:02d}]"
            )

        video_id = filepath.stem
        artist = ""
        album = ""
        lib_entry = library.get(video_id)
        if lib_entry:
            artist = lib_entry.get("artist") or ""
            album = lib_entry.get("album") or ""
        art_path = ""
        if thumb:
            art_path = str(thumb)
        mpris.load_track(
            video_id,
            title,
            duration,
            artist=artist,
            album=album,
            art_path=art_path,
            has_next=_nav[0],
            has_prev=True,
        )
        mpris.set_position_getter(lambda: _player.get_time() if _player else 0)
        _attach_vlc_events()

        def stop_check():
            if flags:
                if flags.get("quit", lambda: False)():
                    _player.stop()
                    return True
                if flags.get("skip", lambda: False)():
                    _player.stop()
                    return True
            return False

        try:
            _display_loop(
                _player,
                title=title,
                args=args,
                next_title=next_title,
                stop_check=stop_check,
            )
        except KeyboardInterrupt:
            _player.stop()
            sys.stdout.write("\n")
            sys.stdout.flush()
            raise
        finally:
            _restore_pause_input()
    finally:
        _restore_pause_input()  # idempotent; covers errors between setup and the loop
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
        os.close(devnull)
