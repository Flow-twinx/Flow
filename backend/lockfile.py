"""Cross-platform advisory file lock: flock on POSIX, msvcrt.locking on Windows."""

import contextlib
import os


@contextlib.contextmanager
def locked(path):
    """Hold an exclusive lock on ``path`` for the duration of the block."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        _acquire(fd)
        yield
    finally:
        try:
            _release(fd)
        finally:
            os.close(fd)


def _acquire(fd):
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _release(fd):
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
