import argparse
import json
import os
import shutil
import signal
import sys
import threading
import time
import urllib.request
from pathlib import Path

import psutil

if __name__ == "__main__" and __package__ is None:
    __package__ = "flow_twinx"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, shortcuts
from backend.Offline import commands as _offline_commands
from backend.Online import commands as _online_commands
from backend.ping import is_connected

from .tui import input as tui_input
from .tui import show_banner

_COMMAND_MODULES = {
    "Online": _online_commands,
    "Offline": _offline_commands,
}


P = config.Primary
S = config.Secondary
M = config.Muted
R = config.Reset

SHELL_AUTO_BG = {"radio", "savan"}


def _web_alive(WEB_PID):
    if not WEB_PID.exists():
        return False
    try:
        return psutil.Process(int(WEB_PID.read_text().strip())).is_running()
    except Exception:
        return False


def _send_web_command(port, command, payload=None):
    data = {"command": command}
    if payload:
        data.update(payload)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/control",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def _send_control(command, sig, label, payload=None):
    WEB_PID = Path.home() / ".flow/web.pid"
    WEB_PORT = Path.home() / ".flow/web_port"

    pid = config.read_pid()
    if pid is not None:
        try:
            os.kill(pid, sig)
            print(f"{P}{label} (VLC PID: {pid}){R}")
            return
        except ProcessLookupError:
            config.clear_pid()

    if _web_alive(WEB_PID):
        port = None
        if WEB_PORT.exists():
            try:
                port = int(WEB_PORT.read_text().strip())
            except ValueError, OSError:
                port = None
        if port and _send_web_command(port, command, payload):
            print(f"{P}{label} (web player){R}")
            return

    print(f"{M}No VLC or web player running{R}")


def _spinner(stop):
    chars = "|/-\\"
    i = 0
    while not stop():
        sys.stdout.write(f"\r{P}Checking connection... {chars[i]}{R}")
        sys.stdout.flush()
        time.sleep(0.1)
        i = (i + 1) % len(chars)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def _load_commands():
    return _COMMAND_MODULES[config.Mode]


def _check_vlc():
    try:
        import vlc
    except ImportError:
        print(
            f"{config.RED}VLC is not installed. Flow requires VLC to play audio.{config.Reset}\n"
            f"{config.Muted}Install it with:{config.Reset}\n"
            f"  {config.Tertiary}sudo apt install vlc{config.Reset}"
            f"  {config.Muted}  # Debian/Ubuntu{config.Reset}\n"
            f"  {config.Tertiary}sudo dnf install vlc{config.Reset}"
            f"  {config.Muted}  # Fedora{config.Reset}\n"
            f"  {config.Tertiary}sudo pacman -S vlc{config.Reset}"
            f"  {config.Muted}  # Arch Linux{config.Reset}\n"
            f"  {config.Tertiary}brew install vlc{config.Reset}"
            f"  {config.Muted}  # macOS{config.Reset}"
        )
        sys.exit(1)


def _setup_island():
    src = Path(__file__).resolve().parent.parent / "backend" / "Hyprland" / "island.qml"
    dest_dir = Path.home() / ".config" / "quickshell"
    dest = dest_dir / "flow-island.qml"
    if not src.exists():
        print(f"{config.RED}island.qml not found in this installation ({src}){R}")
        sys.exit(1)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"{P}Music island installed → {dest}{R}")
    print(f"{M}Launch it with:{R} {S}quickshell -p {dest}{R}")


def _resume(args):
    from backend import status as _status

    data = _status._read()
    title = (data.get("title") or "").strip()
    thumb = data.get("thumbnail") or ""
    if not title:
        print(f"{M}No last-played track in ~/.flow/status.json{R}")
        return

    online = thumb.startswith(("http://", "https://"))
    offline = (".cache/" in thumb) or thumb.startswith(str(Path.home() / ".flow"))
    args.bg = True

    if online:
        config.Mode = "Online"
        _online_commands.resume(title, args)
    elif offline:
        config.Mode = "Offline"
        _offline_commands.resume(title, args, thumb)
    else:
        print(
            f"{M}Could not tell if last track is online or offline (thumbnail: {thumb}){R}"
        )


def _act_current(action):
    from backend import status as _status

    data = _status._read()
    title = (data.get("title") or "").strip()
    thumb = data.get("thumbnail") or ""
    if not title:
        print(f"{M}No last-played track in ~/.flow/status.json{R}")
        return 1

    web_pid = Path.home() / ".flow/web.pid"
    has_player = config.read_pid() is not None or _web_alive(web_pid)
    if not has_player:
        print(f"{M}No player is currently running (no pid file){R}")
        return 1

    if not (data.get("playing") and _status._fresh(data)):
        print(f"{M}No track is currently playing{R}")
        return 1

    online = thumb.startswith(("http://", "https://"))
    offline = (".cache/" in thumb) or thumb.startswith(str(Path.home() / ".flow"))
    if online:
        config.Mode = "Online"
        _online_commands.act_on_current(action, title, thumb)
    elif offline:
        config.Mode = "Offline"
        _offline_commands.act_on_current(action, title, thumb)
    else:
        print(
            f"{M}Could not tell if current track is online or offline (thumbnail: {thumb}){R}"
        )
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Flow Music Player")
    parser.add_argument("--play", nargs="+", help="play a song")
    parser.add_argument(
        "--play-off", nargs="+", help="play a song from the local library (offline)"
    )
    parser.add_argument("--rd", nargs="+", help="play radio mix")
    parser.add_argument(
        "--radio-off",
        nargs="*",
        help="play radio (shuffled local library) without going online",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume the last played track from ~/.flow/status.json",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="toggle stop/resume playback (VLC or web player)",
    )
    parser.add_argument(
        "--next",
        action="store_true",
        help="play next track (VLC or web player)",
    )
    parser.add_argument(
        "--previous",
        action="store_true",
        help="play previous track (VLC or web player)",
    )
    parser.add_argument(
        "--seek",
        type=int,
        metavar="SEC",
        help="seek forward SEC seconds in the running player (VLC or web player)",
    )
    parser.add_argument(
        "--seekb",
        type=int,
        metavar="SEC",
        help="seek backward SEC seconds in the running player (VLC or web player)",
    )
    parser.add_argument(
        "--status", action="store_true", help="show playback and web mode status"
    )
    parser.add_argument(
        "--like",
        action="store_true",
        help="like the currently playing song (requires an active player)",
    )
    parser.add_argument(
        "--unlike",
        action="store_true",
        help="unlike the currently playing song (requires an active player)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the currently playing song (requires an active player)",
    )
    # parser.add_argument(
    #     "--meta",
    #     action="store_true",
    #     help="backfill metadata in library.json for already downloaded songs (temporary)",
    # )
    parser.add_argument(
        "--setup-island",
        action="store_true",
        help="install the Hyprland music island into ~/.config/quickshell",
    )
    parser.add_argument("command", nargs="?", default=None, help="subcommand (play, search, list, ...)")
    parser.add_argument("--check", action="store_true", help="check all dependencies")

    args, unknown = parser.parse_known_args()

    if getattr(args, "setup_island", False):
        _setup_island()
        sys.exit(0)

    _check_vlc()

    if getattr(args, "check", False):
        print(f"{P}Dependency Check:{R}\n")
        config.check_deps()
        sys.exit(0)

    if getattr(args, "status", False):
        from backend.status import show as show_status

        show_status()
        sys.exit(0)

    shortcuts.load()

    control_args = []
    if getattr(args, "pause", False):
        control_args.append(("stop", signal.SIGUSR1, "Toggled pause/resume", None))
    if getattr(args, "next", False):
        control_args.append(("next", signal.SIGUSR2, "Skipped to next track", None))
    if getattr(args, "previous", False):
        control_args.append(
            ("previous", config.SIG_PREV, "Went to previous track", None)
        )
    if getattr(args, "seek", None) is not None:
        control_args.append(
            ("seek", config.SIG_SEEK_FWD, "Seeked forward", getattr(args, "seek"))
        )
    if getattr(args, "seekb", None) is not None:
        control_args.append(
            ("seekb", config.SIG_SEEK_BWD, "Seeked backward", -getattr(args, "seekb"))
        )
    if control_args:
        for command, sig, label, delta in control_args:
            if delta is not None:
                if config.read_pid() is not None:
                    config.write_seek(delta * 1000)
                label = f"{label} {abs(delta)}s"
            _send_control(
                command,
                sig,
                label,
                payload={"delta": delta} if delta is not None else None,
            )
        sys.exit(0)

    if getattr(args, "like", False):
        sys.exit(_act_current("like"))
    if getattr(args, "unlike", False):
        sys.exit(_act_current("unlike"))
    if getattr(args, "download", False):
        sys.exit(_act_current("download"))
    # if getattr(args, "meta", False):
    #     sys.exit(_online_commands.backfill_metadata())

    forced_offline = False
    if getattr(args, "resume", False):
        _resume(args)
        sys.exit(0)
    if getattr(args, "play_off", None) is not None:
        args.command = "play"
        unknown = args.play_off + unknown
        forced_offline = True
        args.bg = True
    elif getattr(args, "radio_off", None) is not None:
        args.command = "radio"
        unknown = args.radio_off + unknown
        forced_offline = True
    elif getattr(args, "play", None) is not None:
        args.command = "play"
        unknown = args.play + unknown
    elif getattr(args, "rd", None) is not None:
        args.command = "radio"
        unknown = args.rd + unknown
    elif args.command and args.command not in (
        "play",
        "search",
        "savan",
        "svn",
        "savan-s",
        "svn-s",
        "like",
        "unlike",
        "download",
        "delete",
        "dl-d",
        "switch",
        "help",
        "short",
        "config",
        "check",
        "radio",
        "rd",
        "playlist",
        "plist",
        "exit",
    ):
        unknown = [args.command] + unknown
        args.command = "play"

    if forced_offline:
        config.Mode = "Offline"
    else:
        stop = False
        t = threading.Thread(target=_spinner, args=(lambda: stop,), daemon=True)
        t.start()
        try:
            if is_connected():
                config.Mode = "Online"
            else:
                config.Mode = "Offline"
        finally:
            stop = True
            t.join()

    commands = _load_commands()

    if args.command:
        resolved = []
        for item in unknown:
            if item.startswith("-"):
                alias = item[1:]
                resolved_cmd = shortcuts.resolve(alias)
                if resolved_cmd != alias:
                    if args.command is None:
                        args.command = resolved_cmd
                    continue
            resolved.append(item)
        unknown = resolved

        if args.command in SHELL_AUTO_BG:
            args.bg = True

        try:
            commands.run(args.command, unknown, args)
        except KeyboardInterrupt:
            pass
    else:
        show_banner()
        if unknown:
            print(f"{M}Unknown command: {' '.join(unknown)}{R}")
        while True:
            try:
                parts = tui_input().strip().split()
                if not parts:
                    continue
                cmd = parts[0].lower()
                extra = parts[1:]
                cmd = shortcuts.resolve(cmd)
                if cmd in ("exit", "quit", "q"):
                    print(f"{M}Goodbye!{R}")
                    break
                cmd_args = argparse.Namespace(**vars(args))
                for flag in ("bg", "download", "repeat", "shuffle"):
                    setattr(cmd_args, flag, False)
                cmd_args.repeat_count = 0
                try:
                    commands.run(cmd, extra, cmd_args)
                except KeyboardInterrupt:
                    config.clear_pid_if(os.getpid())
                if getattr(cmd_args, "bg", False):
                    break
                if cmd == "switch":
                    commands = _load_commands()
                    show_banner()
            except EOFError, KeyboardInterrupt:
                print(f"{M}\nGoodbye!{R}")
                break


if __name__ == "__main__":
    main()
