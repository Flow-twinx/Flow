"""Pause/resume must reach `~/.flow/status.json` from the CLI players.

`_display_loop` used to only tell the visualizer and stdout about a pause, so
`flow status`, the Hyprland island and `--like` all still reported *playing*
for a paused track. `_publish_play_state` republishes the last track with
`playing=False` on the pause edge (and back to `True` on resume).
"""

import pytest

from backend import status
from backend.Offline import player as _offline
from backend.Online import player as _online

_EMPTY = {"title": "", "duration": 0, "thumbnail": None}


@pytest.fixture(params=[_offline, _online], ids=["offline", "online"])
def module(request):
    """Each player module in turn, with its last-track state seeded."""
    mod = request.param
    mod._now.update(title="Test Song", duration=214, thumbnail="/tmp/thumb.jpg")
    mod._paused = False
    yield mod
    mod._now.update(_EMPTY)
    mod._paused = False


def test_pause_edge_writes_playing_false(module):
    module._paused = True
    module._publish_play_state()

    data = status.read()
    assert data["playing"] is False
    assert data["title"] == "Test Song"
    assert data["duration"] == 214
    assert data["thumbnail"] == "/tmp/thumb.jpg"
    # "not playing" / "last played" is derived from this flag alone.
    assert status._fresh(data)


def test_resume_edge_writes_playing_true(module):
    module._paused = False
    module._publish_play_state()

    assert status.read()["playing"] is True


def test_no_write_before_any_track(module):
    module._now.update(_EMPTY)
    status.STATUS_FILE.unlink(missing_ok=True)

    module._paused = True
    module._publish_play_state()

    assert not status.STATUS_FILE.exists()


def test_paused_track_fails_the_command_gate(module):
    """`--like` / `--download` gate on playing+fresh; paused must not pass."""
    module._paused = True
    module._publish_play_state()
    data = status.read()

    assert not (data.get("playing") and status._fresh(data))