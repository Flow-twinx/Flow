"""Output plumbing: a private stdout for us, the fd-level void for everything else."""

import contextlib
import json
import os
import sys

_stdout = None
_json = False


def init(as_json=False):
    """Keep a private copy of stdout so backend chatter can be dropped later."""
    global _stdout, _json
    _json = bool(as_json)
    sys.stdout.flush()
    previous = _stdout
    _stdout = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    if previous is not None:
        previous.close()


def emit(payload=None, text=None):
    """Print text (a line or a list of lines), or payload as JSON when --json is set."""
    if _json:
        _stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        _stdout.flush()
        return
    for line in text if isinstance(text, list) else [text]:
        if line is not None:
            _stdout.write(str(line) + "\n")
    _stdout.flush()


def fail(message, code=1):
    """Report a failure on stderr and exit; --json callers also get an error document."""
    sys.stderr.write(f"flow-min: {message}\n")
    if _json:
        _stdout.write(json.dumps({"error": message}, ensure_ascii=False) + "\n")
        _stdout.flush()
    raise SystemExit(code)


@contextlib.contextmanager
def quiet():
    """Swallow stdout and stderr, spinner threads and yt-dlp warnings included."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = (os.dup(1), os.dup(2))
    null = os.open(os.devnull, os.O_RDWR)
    os.dup2(null, 1)
    os.dup2(null, 2)
    try:
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        os.close(null)


def fork_bg():
    """Fork for background playback: the parent gets the child pid, the child goes quiet."""
    sys.stdout.flush()
    from backend import platform

    if not platform.can_fork():
        return None
    pid = os.fork()
    if pid:
        from backend import config

        config.save_pid(pid)
        return pid
    null = os.open(os.devnull, os.O_RDWR)
    os.dup2(null, 0)
    os.dup2(null, 1)
    os.dup2(null, 2)
    if null > 2:
        os.close(null)
    return None
