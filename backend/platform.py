"""Cross-platform OS helpers: detection, live-pid checks, detached spawning."""

import os
import signal
import subprocess
import sys


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return os.name == "nt"


def can_fork() -> bool:
    return hasattr(os, "fork")


def pid_exists(pid) -> bool:
    """True when ``pid`` is a live process on this OS."""
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(int(pid))
    except Exception:
        pass
    if is_windows():
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def kill_pid(pid, force: bool = False) -> bool:
    """Terminate a process gracefully, or forcefully when ``force`` is set."""
    if not pid:
        return False
    try:
        import psutil

        proc = psutil.Process(int(pid))
        if force:
            proc.kill()
        else:
            proc.terminate()
        return True
    except Exception:
        pass
    if is_windows():
        return False
    try:
        os.kill(int(pid), signal.SIGKILL if force else signal.SIGTERM)
        return True
    except (OSError, ValueError):
        return False


def spawn_detached(argv: list, **kwargs) -> subprocess.Popen:
    """Start a child in its own session/process group, independent of the parent."""
    if is_windows():
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        kwargs.setdefault("close_fds", True)
        return subprocess.Popen(argv, creationflags=flags, **kwargs)
    return subprocess.Popen(argv, start_new_session=True, **kwargs)
