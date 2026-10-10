"""Age-gated / format-less videos must fail loudly instead of fake-playing.

Without authentication yt-dlp gets *no formats* for age-restricted videos,
which surfaced as "Requested format is not available"; the CLI then fell back
to the flat search entry and told VLC to open the watch-page URL, so playback
sat at 0:00. get_entry now classifies the failure and prints an actionable
hint, and play_entry refuses webpage URLs.
"""

import pytest

from backend import sponsor
from backend.Online import youtube


def test_entry_failure_classifies_reasons():
    assert (
        youtube._entry_failure(RuntimeError("Sign in to confirm your age")) == "age"
    )
    assert youtube._entry_failure(RuntimeError("This video is age-restricted")) == "age"
    assert (
        youtube._entry_failure(
            RuntimeError("This video is only available to signed-in users")
        )
        == "signin"
    )
    assert (
        youtube._entry_failure(
            RuntimeError(
                "ERROR: [youtube] x: Requested format is not available. "
                "Use --list-formats for a list of available formats"
            )
        )
        == "format"
    )
    assert youtube._entry_failure(RuntimeError("random network error")) == "other"


def test_get_entry_format_failure_mentions_no_audio(monkeypatch, capsys):
    def boom(url, opts=None, with_segments=True):
        raise RuntimeError("Requested format is not available. Use --list-formats")

    monkeypatch.setattr(sponsor, "stream_info", boom)

    assert youtube.get_entry("https://youtu.be/zzz") is None
    assert "no playable audio format" in capsys.readouterr().out