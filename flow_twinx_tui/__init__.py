import argparse
import os


def _running_pid():
    """Best-effort PID of a running Flow player (flowt TUI first, then VLC)."""
    from backend import config

    for getter, clearer in (
        (config.read_tui_pid, config.clear_tui_pid),
        (config.read_pid, config.clear_pid),
    ):
        pid = getter()
        if pid is None:
            continue
        try:
            import psutil

            alive = psutil.Process(pid).is_running()
        except Exception:
            alive = False
        if not alive:
            clearer()
            continue
        return pid
    return None


def _is_tui_pid(pid):
    """True when the pid belongs to a running Flow TUI."""
    from backend import config

    return config.read_tui_pid() == pid


def _control(sig, label, require_tui=False):
    pid = _running_pid()
    if pid is None:
        return False, f"{label}: no running Flow player (start `flowt` first)"
    if require_tui and not _is_tui_pid(pid):
        return False, f"{label}: no running Flow TUI (start `flowt` first)"
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return False, f"{label}: player PID {pid} is gone"
    return True, f"{label} (PID {pid})"


def _show_status() -> None:
    from backend.status import show as show_status

    show_status()


def main():
    parser = argparse.ArgumentParser(
        prog="flowt",
        description="Flow — terminal UI music player",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="show the playback status card and exit",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="toggle play/pause in a running Flow session (flowt or background VLC)",
    )
    parser.add_argument(
        "--next",
        action="store_true",
        help="skip to the next track in a running Flow session",
    )
    parser.add_argument(
        "--previous",
        action="store_true",
        help="go back to the previous track in a running Flow session",
    )
    parser.add_argument(
        "--repeat",
        action="store_true",
        help="toggle repeat in a running Flow TUI; otherwise start the TUI with repeat enabled",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="toggle shuffle in a running Flow TUI; otherwise start the TUI with shuffle enabled",
    )
    args = parser.parse_args()

    if args.status:
        _show_status()
        return

    from backend import config

    controls = (
        (args.pause, config.SIG_STOP, "Pause toggled", False),
        (args.next, config.SIG_NEXT, "Next", False),
        (args.previous, config.SIG_PREV, "Previous", False),
        (args.repeat, config.SIG_REPEAT, "Repeat toggled", True),
        (args.shuffle, config.SIG_SHUFFLE, "Shuffle toggled", True),
    )
    active = [(sig, label, require_tui) for flag, sig, label, require_tui in controls if flag]
    hard = args.pause or args.next or args.previous

    if active and _running_pid() is not None:
        delivered = True
        for sig, label, require_tui in active:
            ok, msg = _control(sig, label, require_tui=require_tui)
            print(msg)
            if require_tui and not ok:
                # A plain VLC player is running — repeat/shuffle only apply to the TUI.
                delivered = False
        if delivered:
            return
        if hard:
            return
        # Only --repeat/--shuffle were requested and couldn't target a TUI:
        # fall through and launch a new TUI with those modes enabled.

    if active and hard and _running_pid() is None:
        print("No running Flow player to control. Start `flowt` first.")
        return

    from .main import Flow

    Flow(mode=None, repeat=args.repeat, shuffle=args.shuffle).run()


if __name__ == "__main__":
    main()