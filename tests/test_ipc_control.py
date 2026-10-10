"""Control IPC round-trips: the localhost control socket (all OSes) plus the
POSIX signal path, both delivered to an in-process dispatch handler."""

import os
import time

from backend import ipc, registry


def _wait(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_socket_control_round_trip():
    """A registry entry with a ctl_port receives actions over the socket."""
    received = []
    ipc._dispatch = lambda action, payload=None: received.append((action, payload))
    port = ipc._start_server()
    try:
        registry.register("vlc", os.getpid(), ctl_port=port)
        assert ipc.send_to("vlc", "pause") is True
        assert ipc.send_to("vlc", "seek_fwd", {"delta": 5000}) is True
        assert _wait(lambda: ("pause", None) in received)
        assert _wait(lambda: ("seek_fwd", {"delta": 5000}) in received)
    finally:
        registry.clear()
        ipc._dispatch = None


def test_signal_control_round_trip_on_posix():
    """On Linux, actions with a mapped signal reach the handler via os.kill."""
    if os.name == "nt" or ipc.signal_for("pause") is None:
        return
    received = []
    ipc.serve(lambda action, payload=None: received.append(action), kind="vlc")
    try:
        registry.register("vlc", os.getpid())
        assert ipc.send_to("vlc", "pause") is True
        assert _wait(lambda: "pause" in received)
    finally:
        registry.clear()


def test_send_is_false_for_unknown_entry():
    assert ipc.send(None, "pause") is False
    assert ipc.send({}, "pause") is False


def test_windows_control_is_socket_only():
    """On Windows there are no control signals: only the ctl_port socket works."""
    if os.name != "nt":
        return
    assert ipc.signal_for("pause") is None
    ipc._dispatch = lambda action, payload=None: None
    registry.register("vlc", os.getpid())  # no ctl_port -> no signal path
    try:
        assert ipc.send_to("vlc", "pause") is False
    finally:
        registry.clear()