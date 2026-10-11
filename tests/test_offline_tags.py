"""Tests for tags: `lang`, `artist` playback and the `tags` editor/commands.

A tag only works if the numbers add up: `lang punjabi` has to reach the
punjabi songs and nothing else, `artist karan` has to reach the Karan Aujla
songs, both ascending by name. `tags` adds, removes, renames and deletes
free-form tags and the language/artist columns directly in `library.db`.

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
    with library._write() as conn:
        conn.execute("DELETE FROM song_tags")
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


def test_tags_add_puts_a_free_form_tag_on_one_song(fake_library, capsys):
    offline.tags_cmd(["add", "Zed", "roadtrip"], _args())
    assert library.song_tags("tagplay0") == ["roadtrip"]
    assert "Tagged" in capsys.readouterr().out


def test_tags_add_matches_by_list_index_too(fake_library, monkeypatch):
    monkeypatch.setattr(
        offline.lib,
        "get_songs",
        lambda: [
            pathlib.Path("/songs/tagplay2.opus"),
            pathlib.Path("/songs/tagplay0.opus"),
        ],
    )
    offline.tags_cmd(["add", "1", "workout"], _args())
    assert library.song_tags("tagplay2") == ["workout"]


def test_tags_remove_takes_a_tag_off_a_song(fake_library):
    library.set_song_tag("tagplay0", "roadtrip", True)
    offline.tags_cmd(["remove", "Zed", "roadtrip"], _args())
    assert library.song_tags("tagplay0") == []


def test_tags_rename_renames_a_tag_everywhere(fake_library):
    library.set_song_tag("tagplay0", "roadtrip", True)
    library.set_song_tag("tagplay1", "roadtrip", True)
    offline.tags_cmd(["rename", "roadtrip", "driving"], _args())
    assert library.song_tags("tagplay0") == ["driving"]
    assert library.song_tags("tagplay1") == ["driving"]
    assert library.all_song_tags() == [("driving", 2)]


def test_tags_delete_drops_a_tag_everywhere(fake_library):
    library.set_song_tag("tagplay0", "roadtrip", True)
    library.set_song_tag("tagplay1", "roadtrip", True)
    offline.tags_cmd(["delete", "roadtrip"], _args())
    assert library.all_song_tags() == []


def test_tags_list_shows_languages_artists_and_free_form_tags(fake_library, capsys):
    library.set_song_tag("tagplay0", "roadtrip", True)
    offline.tags_cmd(["list"], _args())
    out = capsys.readouterr().out
    assert "Languages:" in out
    assert "punjabi (2)" in out
    assert "Artists:" in out
    assert "Tags:" in out
    assert "roadtrip (1)" in out


def test_the_preview_file_flow_is_gone():
    assert not hasattr(offline, "scan_tags")
    assert not hasattr(offline, "apply_tags")
    assert not hasattr(offline, "PREVIEW_FILE")


def test_an_unknown_tags_action_lists_the_ones_that_work(capsys):
    offline.tags_cmd(["frobnicate"], _args())
    out = capsys.readouterr().out
    assert "tags add" in out
    assert "tags delete" in out


def test_song_tags_are_sorted_and_counted(fake_library):
    library.set_song_tag("tagplay0", "roadtrip", True)
    library.set_song_tag("tagplay0", "gym", True)
    library.set_song_tag("tagplay1", "roadtrip", True)
    assert library.song_tags("tagplay0") == ["gym", "roadtrip"]
    assert library.all_song_tags() == [("roadtrip", 2), ("gym", 1)]


def test_rename_tag_merges_instead_of_duplicating(fake_library):
    library.set_song_tag("tagplay0", "gym", True)
    library.set_song_tag("tagplay0", "workout", True)
    library.set_song_tag("tagplay1", "workout", True)
    assert library.rename_tag("workout", "gym") == 2
    assert library.song_tags("tagplay0") == ["gym"]
    assert library.all_song_tags() == [("gym", 2)]


def test_clearing_a_download_drops_its_free_form_tags(fake_library):
    library.set_song_tag("tagplay0", "roadtrip", True)
    library.clear_download("tagplay0")
    assert library.song_tags("tagplay0") == []
    assert library.all_song_tags() == []


def test_set_song_field_sets_and_clears(fake_library):
    assert library.set_song_field("tagplay0", "language", "telugu")
    assert library.get("tagplay0")["language"] == "telugu"
    assert library.set_song_field("tagplay0", "language", "")
    assert library.get("tagplay0")["language"] is None


def test_tag_mutation_refuses_unknown_songs():
    assert not library.set_song_tag("ghost", "roadtrip", True)
    assert not library.set_song_field("ghost", "language", "hindi")


def test_rename_field_tag_is_comma_aware(fake_library):
    changed = library.rename_field_tag("artist", "Ikky", "Ikky Singh")
    assert changed == 1
    assert library.get("tagplay2")["artist"] == "Karan Aujla, Ikky Singh"


def test_delete_field_tag_keeps_the_other_parts(fake_library):
    changed = library.delete_field_tag("artist", "Ikky")
    assert changed == 1
    assert library.get("tagplay2")["artist"] == "Karan Aujla"


def test_delete_field_tag_clears_a_sole_value_to_none(fake_library):
    changed = library.delete_field_tag("language", "hindi")
    assert changed == 1
    assert library.get("tagplay1")["language"] is None


def test_field_tag_matching_is_case_insensitive(fake_library):
    assert library.rename_field_tag("artist", "ikky", "Ikky S.") == 1
    assert library.get("tagplay2")["artist"] == "Karan Aujla, Ikky S."