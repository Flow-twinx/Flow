"""Daemon RPC tests: typed dispatch + validation (in-process), plus a real
socket E2E against the resident daemon when the `flow` binary is available.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend import config, registry, rpc

HAS_FLOW = shutil.which("flow") is not None or (
    Path(sys.executable).parent / "flow"
).exists()


def _flow_bin():
    local = Path(sys.executable).parent / "flow"
    return str(local) if local.exists() else shutil.which("flow")


# ---------------------------------------------------------------------------
# In-process dispatch (no socket) — fast validation unit tests
# ---------------------------------------------------------------------------

def test_handle_unknown_method():
    resp = rpc.handle({"method": "nope"})
    assert "error" in resp
    assert "Unknown method" in resp["error"]


def test_hello_returns_version_and_no_raw():
    resp = rpc.handle({"method": "hello", "params": {"name": "x"}})
    assert resp["api_version"] == 3
    assert resp["capabilities"] == {"raw": False}


def test_introspect_lists_players():
    resp = rpc.handle({"method": "introspect"})
    assert resp["result"]["api_version"] == 3
    assert "players" in resp["result"]["methods"]
    assert "show_volume" not in resp["result"]["safe_keys"]


def test_set_config_rejects_unsafe_key():
    resp = rpc.handle(
        {"method": "set_config", "params": {"key": "show_volume", "value": 1}}
    )
    assert "error" in resp["result"]
    assert "not writable" in resp["result"]["error"]


def test_set_config_accepts_safe_key():
    before = config.config_get("theme")[0]
    resp = rpc.handle({"method": "set_config", "params": {"key": "theme", "value": "spinner"}})
    assert "error" not in resp
    config.apply_config("theme", before)


def test_set_config_rejects_none_value():
    resp = rpc.handle({"method": "set_config", "params": {"key": "theme", "value": None}})
    assert "error" in resp["result"]
    assert "cannot be None" in resp["result"]["error"]


def test_raw_cli_gated_without_capability():
    resp = rpc.handle({"method": "raw_cli", "params": {"args": ["--status"]}}, conn=None)
    assert "error" in resp
    assert "disabled" in resp["error"]


def test_players_method_reflects_registry():
    proc = subprocess.Popen(["sleep", "60"])
    try:
        registry.register("vlc", proc.pid)
        resp = rpc.handle({"method": "players"})
        assert {"kind": "vlc", "pid": proc.pid} in resp["result"]
    finally:
        proc.kill()
        proc.wait()
        registry.clear()


def test_status_and_current_track_are_dicts():
    assert isinstance(rpc.handle({"method": "status"})["result"], dict)
    assert isinstance(rpc.handle({"method": "current_track"})["result"], dict)
    assert isinstance(rpc.handle({"method": "is_playing"})["result"], bool)


def test_pause_routes_to_web_command_file_when_no_player():
    from backend import control

    registry.clear()
    resp = rpc.handle({"method": "pause"})
    assert "web player" in resp["result"]
    command = control.take()
    assert command == "stop"


# ---------------------------------------------------------------------------
# E2E: real daemon socket
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_FLOW, reason="flow binary not available")
def test_daemon_socket_e2e():
    flow = _flow_bin()
    sock_path = str(Path(os.environ["HOME"]) / ".flow/flow.sock")
    # No daemon should be running in the scratch HOME; make sure.
    subprocess.run([flow, "daemon", "quit"], capture_output=True, text=True)
    time.sleep(0.3)

    start = subprocess.run([flow, "daemon", "start"], capture_output=True, text=True)
    assert start.returncode == 0
    try:
        from backend.plugin_api import flow_api

        assert os.path.exists(sock_path)
        assert isinstance(flow_api.status_card(), dict)
        assert flow_api.players() == []
        intro = flow_api._call("introspect")["result"]
        assert "players" in intro["methods"]
        assert flow_api.socket_path() == sock_path
    finally:
        quit_rc = subprocess.run([flow, "daemon", "quit"], capture_output=True, text=True)
        assert quit_rc.returncode == 0
        time.sleep(0.3)
        assert not os.path.exists(sock_path)