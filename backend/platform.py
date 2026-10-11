"""Cross-platform OS helpers: detection, live-pid checks, detached spawning."""

import os
import signal
import subprocess
import sys
from pathlib import Path


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return os.name == "nt"


def widen_stdio() -> None:
    """Force UTF-8 on stdout/stderr so cp1252 pipes survive box-drawing output."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


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


def bootstrap_vlc() -> None:
    """Point python-vlc at a system VLC install before ``import vlc`` runs.

    Linux is left alone (apt/brew already place libvlc where python-vlc's
    default search looks). On Windows the exact libvlc.dll is exported as
    PYTHON_VLC_LIB_PATH. On macOS that variable is *never* set: python-vlc's
    darwin branch has to preload libvlccore before libvlc, and pinning the lib
    path skips that and fails to load. macOS only gets a plugin path (and, for
    a Homebrew install, DYLD_LIBRARY_PATH).
    """
    if is_linux() or os.environ.get("PYTHON_VLC_LIB_PATH"):
        return
    plugins = None
    if is_macos():
        base = Path("/Applications/VLC.app/Contents/MacOS")
        if (base / "lib/libvlccore.dylib").exists():
            plugins = next(
                (base / p for p in ("plugins", "modules") if (base / p).is_dir()),
                None,
            )
        else:
            for root in ("/opt/homebrew/lib", "/usr/local/lib"):
                if (Path(root) / "libvlc.dylib").exists():
                    dyld = os.environ.get("DYLD_LIBRARY_PATH", "")
                    os.environ["DYLD_LIBRARY_PATH"] = (
                        str(root) + (os.pathsep + dyld if dyld else "")
                    )
                    plugins = Path(root) / "vlc/plugins"
                    break
    elif is_windows():
        dirs = [Path(sys.executable).resolve().parent]
        for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(env)
            if root:
                dirs.append(Path(root) / "VideoLAN" / "VLC")
        for d in dirs:
            if (d / "libvlc.dll").exists():
                os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(d / "libvlc.dll"))
                plugins = d / "plugins"
                break
    if plugins is not None and plugins.is_dir():
        os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(plugins))
