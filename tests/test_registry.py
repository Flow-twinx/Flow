"""Player registry tests — live-process registration, routing, fallback.

Uses real short-lived subprocesses so pid liveness checks are exercised end
to end. All state lands under the scratch HOME from ``conftest.py``.
"""

import subprocess

from backend import config, registry


def _sleeper():
    return subprocess.Popen(["sleep", "60"])


def _wait_dead(proc):
    proc.kill()
    proc.wait()
    import time

    time.sleep(0.1)


def test_register_via_config_mirrors_legacy_pid_file():
    proc = _sleeper()
    try:
        config.save_pid(proc.pid)
        entry = registry.resolve("vlc")
        assert entry is not None and entry["pid"] == proc.pid
        # legacy mirror still written for pre-registry readers
        assert registry.LEGACY_PID_FILES["vlc"].read_text().strip() == str(proc.pid)
    finally:
        _wait_dead(proc)
        config.clear_pid()


def test_clear_pid_unregisters():
    proc = _sleeper()
    config.save_pid(proc.pid)
    config.clear_pid()
    assert registry.resolve("vlc") is None
    proc.kill()
    proc.wait()


def test_dead_player_not_resolved_or_live():
    proc = _sleeper()
    config.save_pid(proc.pid)
    _wait_dead(proc)
    assert registry.resolve("vlc") is None
    assert registry.live() == []
    registry.clear()


def test_legacy_pid_file_fallback():
    proc = _sleeper()
    try:
        registry.clear()
        registry.LEGACY_PID_FILES["vlc"].write_text(str(proc.pid))
        entry = registry.resolve("vlc")
        assert entry is not None and entry["pid"] == proc.pid
    finally:
        _wait_dead(proc)
        registry.LEGACY_PID_FILES["vlc"].unlink(missing_ok=True)
        registry.clear()


def test_web_registry_entry_carries_port():
    proc = _sleeper()
    try:
        registry.register("web", proc.pid, port=5000)
        entry = registry.resolve("web")
        assert entry["pid"] == proc.pid
        assert entry["port"] == 5000
        assert registry.live() == [{"kind": "web", "pid": proc.pid, "port": 5000}]
    finally:
        _wait_dead(proc)
        registry.clear()


def test_web_legacy_port_fallback():
    proc = _sleeper()
    try:
        registry.clear()
        registry.LEGACY_PID_FILES["web"].write_text(str(proc.pid))
        registry.LEGACY_PORT_FILE.write_text("5001")
        entry = registry.resolve("web")
        assert entry["pid"] == proc.pid
        assert entry["port"] == 5001
    finally:
        _wait_dead(proc)
        registry.LEGACY_PID_FILES["web"].unlink(missing_ok=True)
        registry.LEGACY_PORT_FILE.unlink(missing_ok=True)
        registry.clear()


def test_unregister_pid_match_semantics():
    proc = _sleeper()
    try:
        registry.register("vlc", proc.pid)
        registry.unregister("vlc", proc.pid + 999)  # wrong pid -> kept
        assert registry.resolve("vlc") is not None
        registry.unregister("vlc", proc.pid)  # matching pid -> removed
        assert registry.resolve("vlc") is None
        assert registry._read() == {}
    finally:
        _wait_dead(proc)
        registry.clear()


def test_unknown_kind_rejected():
    import pytest

    with pytest.raises(ValueError):
        registry.register("nope", 1234)


def test_prune_drops_dead_entries():
    proc = _sleeper()
    config.save_pid(proc.pid)
    _wait_dead(proc)
    assert registry._read()  # stale entry still on disk
    registry.prune()
    assert registry._read() == {}