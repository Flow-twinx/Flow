import os
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()


def _flow_cmd() -> list[str]:
    if os.environ.get("FLOW_BIN"):
        return os.environ["FLOW_BIN"].split()
    found = shutil.which("flow")
    if found:
        return [found]
    return [sys.executable, "-m", "cli.main"]


def run(*flow_args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [*_flow_cmd(), *flow_args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return 1, "flow binary not found"
    except OSError as exc:
        return 1, str(exc)
    out = proc.stdout or proc.stderr or ""
    return proc.returncode, out
