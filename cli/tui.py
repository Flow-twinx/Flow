import builtins
import os
import signal
import sys
import termios

from backend import config

BANNER = r"""
███████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║     ██╔═══██╗██║    ██║
█████╗  ██║     ██║   ██║██║ █╗ ██║
██╔══╝  ██║     ██║   ██║██║███╗██║
██║     ███████╗╚██████╔╝╚███╔███╔╝
╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
"""


def show_banner():
    c = config.Primary if config.Mode == "Online" else config.Secondary
    builtins.print(f"{c}{BANNER}{config.Reset}")
    builtins.print(
        f"{config.Muted}         Flow Music Player v{config.VERSION}{config.Reset}"
    )
    builtins.print(f"{c}         Mode : {config.Mode}{config.Reset}")
    if config.DEV_MODE:
        print(f"     {config.RED}       [Dev Mode]{config.Reset}")
    builtins.print()


def clear_screen():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def input(prompt: str = "") -> str:
    if config.Mode == "Online":
        return builtins.input(f"{config.Primary}{prompt}$ {config.Reset}")
    elif config.Mode == "Offline":
        return builtins.input(f"{config.Secondary}{prompt}$ {config.Reset}")
    return builtins.input(prompt)


_CTRL_Q = 0x11


def install_quit_key(fd=None):
    """Make Ctrl+Q leave the shell, exactly like Ctrl+C does.

    Ctrl+Q raises no signal on a stock terminal: it is XON (resume output), so
    it is swallowed by flow control while a command is running and arrives as a
    plain byte while readline is editing a line. The only way to make it quit
    is to take XON away and hand the terminal's QUIT character to it, then
    catch SIGQUIT and re-raise it as the KeyboardInterrupt the shell loop
    already treats as "leave".

    Radio mode does the same remap for its own lifetime and restores whatever
    it found on exit, so the two nest safely. Anything that is not a real
    terminal (piped stdin, background fork) is a no-op.

    `fd` exists so tests can point this at a pty slave; it defaults to stdin.

    Returns the callable that puts the terminal and handler back.
    """
    try:
        if fd is None:
            fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return lambda: None
        old_term = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[0] &= ~termios.IXON
        new[6][termios.VQUIT] = _CTRL_Q
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
    except (AttributeError, ValueError, OSError, termios.error):
        return lambda: None

    def _sigquit(sig, frame):
        raise KeyboardInterrupt

    try:
        old_handler = signal.signal(signal.SIGQUIT, _sigquit)
    except (ValueError, OSError):
        old_handler = None

    def restore():
        if old_handler is not None:
            try:
                signal.signal(signal.SIGQUIT, old_handler)
            except (ValueError, OSError):
                pass
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        except (OSError, termios.error):
            pass

    return restore
