"""Gated raw-CLI bridge for the Flow daemon.

This is the *only* arbitrary flag surface a plugin can reach, and it's gated
server-side by `backend/rpc.py` (`raw_cli` requires the plugin to be installed
with `"raw": true` in its manifest, or launched with `FLOW_PLUGIN_RAW=1`).

It simply runs the real `flow` CLI as a subprocess with the given flow args and
returns `(returncode, captured_output)`. There is no default-API passthrough:
regex-cli passthrough of arbitrary flow flags is gone; only typed, host-validated
methods plus this one gated escape hatch exist. See `docs/dev/plugins.md`.
"""

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
    """Run ``flow <flow_args...>`` as a subprocess.

    Returns ``(exit_code, captured_output)``. Output is captured from stdout,
    falling back to stderr when the CLI writes there instead.
    """
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
