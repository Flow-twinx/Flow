"""Tests for playing the library by tag: `lang`, `artist` and `tags`.

A tag only works if the numbers add up: `lang punjabi` has to reach the
punjabi songs and nothing else, `artist karan` has to reach the Karan Aujla
songs, both ascending by name, and `tags scan` must not touch `library.db`
before `tags apply` runs.

Uses the scratch `HOME` from `conftest.py`; playback is faked so the
assertions are about which songs were queued, not about VLC.
"""

import argparse
import pathlib

import pytest

from backend import library
from backend.Offline import commands as offline


def _args(**flags):
    args = argparse.Namespace(
        bg=False, download=False, repeat=False, shuffle=False, repeat_count=0, multi=False
    )
    for key, value in flags.items():
        setattr(args, key, value)
    return args


@pytest.fixture(autouse=True)
def fake_library(monkeypatch, tmp_path):
    songs = {}
    for idx, (name, language, artist) in enumerate(
        (
            ("Zed Track", "punjabi", "Karan Aujla"),
            ("Alpha Track", "hindi", "Arijit Singh"),
            ("Mid Track", "punjabi", "Karan Aujla, Ikky"),
            ("Untuned", "", ""),
        )
    ):
        video_id = f"tagplay{idx}"
        path = tmp_path / f"{video_id}.opus"
        path.write_bytes(b"")
        library.track_download(
            video_id, str(path), name, {"language": language, "artist": artist}
        )
        songs[name] = path

    played = []

    def fake_play_queue(paths, args):
        played.extend(pathlib.Path(p) for p in paths)

    monkeypatch.setattr(offline, "_play_queue", fake_play_queue)
    monkeypatch.setattr(
        offline, "_play_liked", lambda args: played.append("liked")
    )
    yield played


def _names(played):
    """Only this module's rows: the scratch library.db is shared with other tests."""
    return [pathlib.Path(p).stem for p in played if "tagplay" in str(p)]


def test_lang_plays_every_song_with_that_tag(fake_library):
    offline.lang_track(["punjabi"], _args())
    assert _names(fake_library) == ["tagplay2", "tagplay0"]


def test_lang_matches_a_partial_tag(fake_library):
    offline.lang_track(["pun"], _args())
    assert len(fake_library) == 2


def test_lang_with_no_match_says_so(fake_library, capsys):
    offline.lang_track(["telugu"], _args())
    assert fake_library == []
    assert "No downloaded songs tagged 'telugu'" in capsys.readouterr().out


def test_a_bare_lang_lists_the_tags_instead(fake_library, capsys):
    offline.lang_track([], _args())
    out = capsys.readouterr().out
    assert "Usage: lang" in out
    assert "punjabi" in out
    assert fake_library == []


def test_artist_plays_every_song_by_that_artist(fake_library):
    offline.artist_track(["karan"], _args())
    assert _names(fake_library) == ["tagplay2", "tagplay0"]


def test_artist_matches_a_full_name_too(fake_library):
    offline.artist_track(["Arijit Singh"], _args())
    assert _names(fake_library) == ["tagplay1"]


def test_s_is_the_shuffle_flag(fake_library, monkeypatch):
    monkeypatch.setattr(offline.random, "shuffle", lambda items: items.reverse())
    offline.lang_track(["punjabi"], _args(shuffle=True))
    assert _names(fake_library) == ["tagplay0", "tagplay2"]


def test_untagged_songs_are_never_played_by_tag(fake_library):
    offline.lang_track(["a"], _args())
    offline.artist_track([""], _args())
    assert "tagplay3" not in _names(fake_library)


def test_the_alias_dispatches(fake_library):
    offline.run("ar", ["Karan Aujla"], _args())
    assert len(fake_library) == 2


def test_lang_is_not_an_online_command():
    from backend.Online import commands as online

    assert "lang" not in online.COMMANDS
    assert "artist" in online.COMMANDS


def test_tags_scan_writes_a_file_and_changes_nothing(monkeypatch, tmp_path):
    preview = tmp_path / "tags-preview.tsv"
    monkeypatch.setattr(offline, "PREVIEW_FILE", preview)
    monkeypatch.setattr(
        "backend.Online.youtube.fetch_info",
        lambda video_id: {"title": "Zed Track", "language": "pa"},
    )
    library.track_download("scanvid", str(tmp_path / "scanvid.opus"), "Scan Me")

    offline.tags_cmd(["scan"], _args())

    body = preview.read_text().splitlines()
    assert body[0].startswith("# video_id")
    assert any("scanvid\tpunjabi\t" in line for line in body)
    assert (library.get("scanvid").get("language") or "") == ""


def test_tags_apply_saves_language_and_only_fills_a_missing_artist(monkeypatch, tmp_path):
    preview = tmp_path / "tags-preview.tsv"
    preview.write_text(
        "# video_id\tlanguage\tartist\ttitle\n"
        "tagplay0\tpunjabi\tSomebody New\tZed Track\n"
        "tagplay1\thindi\tArijit Singh\tAlpha Track\n"
    )
    monkeypatch.setattr(offline, "PREVIEW_FILE", preview)

    offline.tags_cmd(["apply"], _args())

    assert library.get("tagplay0")["language"] == "punjabi"
    assert library.get("tagplay0")["artist"] == "Karan Aujla"
    assert library.get("tagplay1")["artist"] == "Arijit Singh"


def test_tags_apply_skips_rows_that_are_gone(monkeypatch, tmp_path, capsys):
    preview = tmp_path / "tags-preview.tsv"
    preview.write_text("ghostvid\thindi\tNobody\tVanished\n")
    monkeypatch.setattr(offline, "PREVIEW_FILE", preview)

    offline.tags_cmd(["apply"], _args())

    assert "no longer in the library" in capsys.readouterr().out


def test_tags_apply_without_a_preview_explains_itself(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(offline, "PREVIEW_FILE", tmp_path / "nothing.tsv")
    offline.tags_cmd(["apply"], _args())
    assert "run: tags scan" in capsys.readouterr().out


def test_an_unknown_tags_action_lists_the_ones_that_work(capsys):
    offline.tags_cmd(["frobnicate"], _args())
    assert "tags scan" in capsys.readouterr().out


def test_tags_lists_languages_and_artists(fake_library, capsys):
    offline.tags_cmd([], _args())
    out = capsys.readouterr().out
    assert "Languages:" in out
    assert "punjabi (2)" in out
    assert "Artists:" in out