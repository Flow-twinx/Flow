"""Tests for the offline radio seed and the offline flag handling.

`radio` used to drop its whole argument list and shuffle the library no matter
what you asked for, so `radio Senorita` was indistinguishable from a bare
`radio` — the song name was silently ignored. It now takes the same
`radio <song name> [index]` seed online mode does.

`-f <format>` is an online *download* flag, but offline mode routes every
command through `config.merge_flags`, so `-f` swallowed the token after it and
ate the song name (`play -f Senorita`). Offline mode has nothing to download,
so it now rejects the flag instead of consuming a value.

Uses the scratch `HOME` from `conftest.py`; the library itself is faked so the
assertions are about ordering and argument handling, not disk scanning.
"""

import os
import pathlib

import pytest

from backend.Offline import commands as offline


LIBRARY = [
    pathlib.Path(f"/music/{name}.mp3")
    for name in ("Senorita", "Banjaara", "Dangal", "Sailor", "Thoda Thoda Pyaar")
]


@pytest.fixture(autouse=True)
def fake_library(monkeypatch):
    """A five-song library whose stems double as their display titles."""
    monkeypatch.setattr(offline.lib, "get_all_songs", lambda: list(LIBRARY))
    monkeypatch.setattr(
        offline.lib, "find_songs", lambda q: [p for p in LIBRARY if q.lower() in p.stem.lower()]
    )
    monkeypatch.setattr(offline.lib, "display_name", lambda p: p.stem)
    monkeypatch.setattr(offline, "_last_results", [])
    yield


def stems(paths):
    return [p.stem for p in paths]


# ---------------------------------------------------------------------------
# radio seed
# ---------------------------------------------------------------------------

def test_bare_radio_still_shuffles_the_whole_library():
    queue = offline._radio_queue(None)
    assert sorted(stems(queue)) == sorted(stems(LIBRARY))


def test_a_song_name_seeds_the_queue_and_keeps_every_song():
    queue = offline._radio_queue("Senorita")
    assert queue[0].stem == "Senorita"
    # Radio still loops the library, it just starts where you asked.
    assert sorted(stems(queue)) == sorted(stems(LIBRARY))


def test_an_exact_song_name_is_a_seed():
    assert offline._radio_seed("Thoda Thoda Pyaar").stem == "Thoda Thoda Pyaar"


def test_a_trailing_index_picks_that_match():
    assert offline._radio_seed("a 2").stem == "Banjaara"


def test_a_lone_index_picks_from_the_last_results(monkeypatch):
    monkeypatch.setattr(offline, "_last_results", [LIBRARY[2]])
    assert offline._radio_seed("1").stem == "Dangal"


def test_a_lone_index_with_no_results_is_reported():
    """Not a crash and not a silent full shuffle — the reason is printed."""
    assert offline._radio_seed("1") is None
    assert offline._radio_queue("1") is None


def test_an_out_of_range_index_is_rejected():
    assert offline._radio_seed("a 99") is None
    assert offline._radio_queue("a 99") is None


def test_an_unknown_song_name_is_reported_not_ignored():
    assert offline._radio_seed("no such song") is None
    assert offline._radio_queue("no such song") is None


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_the_queue_is_published_for_the_next_index(monkeypatch):
    """`radio <name>` publishes its queue the way online mode publishes tracks."""
    import os
    import pty
    import sys

    master, slave = pty.openpty()
    published = {}

    def stop_after_first_track(path, title, args=None, **kwargs):
        published["queue"] = list(offline._radio_tracks)
        raise KeyboardInterrupt

    monkeypatch.setattr(offline.player, "play_file", stop_after_first_track)
    monkeypatch.setattr(sys, "stdin", type("Fake", (), {"fileno": lambda self: slave})())
    monkeypatch.setattr(offline.os, "open", _refuse_dev_tty)
    try:
        offline.radio(["Senorita"], _args())
    finally:
        for fd in (master, slave):
            try:
                os.close(fd)
            except OSError:
                pass
    assert published["queue"][0].stem == "Senorita"
    assert sorted(stems(published["queue"])) == sorted(stems(LIBRARY))


def _refuse_dev_tty(path, *flags):
    """Radio prefers /dev/tty; make it use the pty we handed it instead.

    Without this, a test run from a real terminal would reconfigure that
    terminal — Ctrl+Q would stay remapped after the suite finished.
    """
    if path == "/dev/tty":
        raise OSError("no controlling terminal")
    return os.open(path, *flags)


# ---------------------------------------------------------------------------
# flags
# ---------------------------------------------------------------------------

def _args():
    return type("Args", (), {"bg": False, "download": False, "repeat": False,
                             "shuffle": False, "repeat_count": 0, "multi": False})()


def test_dash_f_does_not_swallow_the_song_name(monkeypatch):
    """`-f` is a download format; offline has nothing to download it with."""
    played = []
    monkeypatch.setattr(offline.player, "play_file", lambda p, t, *a, **k: played.append(p.stem))
    offline.run("play", ["-f", "Senorita"], _args())
    assert played == ["Senorita"]


def test_dash_f_on_radio_does_not_swallow_the_seed(monkeypatch):
    """Same trap on radio: the seed is what makes `radio <name>` work."""
    got = []
    monkeypatch.setattr(offline, "radio", lambda extra, args: got.append(extra))
    offline.run("radio", ["-f", "Senorita"], _args())
    assert got == [["Senorita"]]
