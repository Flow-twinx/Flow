"""Cross-platform raw keyboard input: termios on POSIX, msvcrt on Windows."""

import errno
import os
import signal
import sys
import threading
import time

from backend import platform

_CTRL_Q = 0x11
_PAUSE_KEY = 0x10


def install_quit_key(fd=None):
    """Map Ctrl+Q to Ctrl+C (termios on POSIX); a no-op on Windows."""
    if platform.is_windows():
        return lambda: None
    import termios

    try:
        target = sys.stdin.fileno() if fd is None else fd
        if not os.isatty(target):
            return lambda: None
        old_term = termios.tcgetattr(target)
        new = termios.tcgetattr(target)
        new[0] &= ~termios.IXON
        new[6][termios.VQUIT] = _CTRL_Q
        termios.tcsetattr(target, termios.TCSADRAIN, new)
    except (termios.error, OSError, ValueError, AttributeError):
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
            import termios

            termios.tcsetattr(target, termios.TCSADRAIN, old_term)
        except (termios.error, OSError, ValueError):
            pass

    return restore


class RawReader:
    """Daemon thread reading single stdin keys without blocking.

    POSIX: stdin is made raw-ish and non-blocking (restored on stop).
    Windows: an msvcrt.kbhit()/getwch() polling thread. Each key byte is
    handed to ``callback`` as an int; start()/stop() are idempotent.
    """

    def __init__(self, callback, fd=None):
        self.callback = callback
        self._fd = sys.stdin.fileno() if fd is None else fd
        self._stop = threading.Event()
        self._thread = None
        self._restore = None

    def start(self):
        if self._thread is not None:
            return
        if platform.is_windows():
            self._thread = threading.Thread(target=self._msvcrt_loop, daemon=True)
        else:
            self._restore = self._posix_prepare()
            if self._restore is None:
                return
            self._thread = threading.Thread(target=self._posix_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
            self._thread = None
        if self._restore is not None:
            self._restore()
            self._restore = None

    def _posix_prepare(self):
        import fcntl
        import termios

        try:
            if not os.isatty(self._fd):
                return None
            old_term = termios.tcgetattr(self._fd)
            new = termios.tcgetattr(self._fd)
            new[0] &= ~termios.IXON
            new[6][termios.VSUSP] = 0
            termios.tcsetattr(self._fd, termios.TCSADRAIN, new)
            flags = fcntl.fcntl(self._fd, fcntl.F_GETFL)
            fcntl.fcntl(self._fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except (termios.error, OSError, ValueError, AttributeError):
            return None
        try:
            signal.signal(signal.SIGTSTP, signal.SIG_IGN)
        except (ValueError, OSError):
            pass

        def restore():
            try:
                fcntl.fcntl(self._fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                termios.tcsetattr(self._fd, termios.TCSADRAIN, old_term)
            except (termios.error, OSError, ValueError):
                pass

        return restore

    def _posix_loop(self):
        while not self._stop.is_set():
            try:
                ch = os.read(self._fd, 1)
            except OSError as ex:
                if getattr(ex, "errno", None) == errno.EAGAIN:
                    time.sleep(0.05)
                    continue
                break
            if not ch:
                break
            self._emit(ch[0])

    def _msvcrt_loop(self):
        import msvcrt

        while not self._stop.is_set():
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    # Function/arrow keys are two bytes; swallow the second.
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                self._emit(ord(ch))
            else:
                time.sleep(0.05)

    def _emit(self, ch):
        try:
            self.callback(ch)
        except Exception:
            pass