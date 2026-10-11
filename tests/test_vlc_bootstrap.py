"""Unit tests for `backend.platform.bootstrap_vlc` — python-vlc env hints.

python-vlc resolves libvlc at ``import vlc`` time, so the bootstrap must pick
the right library/plugin dirs on macOS and Windows before any import. These
tests fake the OS detection and the filesystem layout (the app bundle / the
portable VLC tree) and assert the exported ``PYTHON_VLC_*`` vars.
"""

import os
import pathlib

from backend import platform


def _clear(monkeypatch):
    monkeypatch.delenv("PYTHON_VLC_LIB_PATH", raising=False)
    monkeypatch.delenv("PYTHON_VLC_MODULE_PATH", raising=False)


def test_linux_is_a_noop(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(platform, "is_linux", lambda: True)
    monkeypatch.setattr(platform, "is_macos", lambda: False)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    platform.bootstrap_vlc()
    assert "PYTHON_VLC_LIB_PATH" not in os.environ
    assert "PYTHON_VLC_MODULE_PATH" not in os.environ


def test_macos_locates_the_app_bundle(monkeypatch, tmp_path):
    _clear(monkeypatch)
    app = tmp_path / "VLC.app" / "Contents" / "MacOS"
    (app / "lib").mkdir(parents=True)
    (app / "plugins").mkdir()
    (app / "lib" / "libvlc.dylib").write_bytes(b"x")
    (app / "lib" / "libvlccore.dylib").write_bytes(b"x")
    real_path = pathlib.Path

    def fake_path(p):
        p = str(p)
        if p.startswith("/Applications/VLC.app"):
            p = p.replace("/Applications/VLC.app", str(tmp_path / "VLC.app"))
        return real_path(p)

    monkeypatch.setattr(platform, "Path", fake_path)
    monkeypatch.setattr(platform, "is_linux", lambda: False)
    monkeypatch.setattr(platform, "is_macos", lambda: True)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    platform.bootstrap_vlc()
    # Never pin the lib path on macOS: python-vlc must preload libvlccore.
    assert "PYTHON_VLC_LIB_PATH" not in os.environ
    assert os.environ["PYTHON_VLC_MODULE_PATH"].endswith("plugins")


def test_macos_homebrew_fallback_uses_dyld(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.delenv("DYLD_LIBRARY_PATH", raising=False)
    libdir = tmp_path / "lib"
    (libdir / "vlc" / "plugins").mkdir(parents=True)
    (libdir / "libvlc.dylib").write_bytes(b"x")
    real_path = pathlib.Path

    def fake_path(p):
        p = str(p)
        if p.startswith("/opt/homebrew"):
            p = p.replace("/opt/homebrew", str(tmp_path))
        elif p.startswith("/Applications"):
            p = p.replace("/Applications", str(tmp_path / "extra"))
        return real_path(p)

    monkeypatch.setattr(platform, "Path", fake_path)
    monkeypatch.setattr(platform, "is_linux", lambda: False)
    monkeypatch.setattr(platform, "is_macos", lambda: True)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    platform.bootstrap_vlc()
    assert "PYTHON_VLC_LIB_PATH" not in os.environ
    assert os.environ["DYLD_LIBRARY_PATH"].startswith("/opt/homebrew/lib")


def test_windows_locates_installed_vlc(monkeypatch, tmp_path):
    _clear(monkeypatch)
    vlc_dir = tmp_path / "VideoLAN" / "VLC"
    (vlc_dir / "plugins").mkdir(parents=True)
    (vlc_dir / "libvlc.dll").write_bytes(b"x")
    monkeypatch.setattr(platform, "Path", pathlib.Path)
    monkeypatch.setattr(platform, "is_linux", lambda: False)
    monkeypatch.setattr(platform, "is_macos", lambda: False)
    monkeypatch.setattr(platform, "is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    platform.bootstrap_vlc()
    assert os.environ["PYTHON_VLC_LIB_PATH"] == str(vlc_dir / "libvlc.dll")
    assert os.environ["PYTHON_VLC_MODULE_PATH"] == str(vlc_dir / "plugins")


def test_pre_set_lib_path_is_trusted(monkeypatch):
    monkeypatch.setenv("PYTHON_VLC_LIB_PATH", "C:\\fake\\libvlc.dll")
    monkeypatch.delenv("PYTHON_VLC_MODULE_PATH", raising=False)
    monkeypatch.setattr(platform, "is_linux", lambda: False)
    monkeypatch.setattr(platform, "is_macos", lambda: True)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    platform.bootstrap_vlc()
    assert os.environ["PYTHON_VLC_LIB_PATH"] == "C:\\fake\\libvlc.dll"
    assert "PYTHON_VLC_MODULE_PATH" not in os.environ