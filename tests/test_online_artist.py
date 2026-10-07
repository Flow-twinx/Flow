"""Tests for `artist <name>` in online mode.

Online there is no library to filter, so the artist is matched where YouTube
puts it: the title of each result. When nothing in the results credits that
name, the artist of the track that is playing (or played last) is tried
instead, which is what makes `artist karan` work while a Karan Aujla track is
loaded.
"""

import pytest

from backend import library
from backend.Online import commands as online


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    """`_do_search` is faked so no network call is made; `name songs` -> results."""
    results_by_artist = {
        "karan aujla songs": [
            ("id1", "Four You EP | Karan Aujla", "3:11"),
            ("id2", "52 Bars (Official Video) Karan Aujla | Ikky", "2:34"),
            ("id3", "Softly Karan Aujla", "2:58"),
            ("id4", "Some Other Artist", "3:40"),
        ],
        "arijit singh songs": [
            ("id5", "Kesariya Arijit Singh", "4:30"),
        ],
    }

    def fake_do_search(query):
        online._last_results = [
            ({"id": vid, "webpage_url": f"https://youtu.be/{vid}"}, title, dur)
            for vid, title, dur in results_by_artist.get(query.lower(), [])
        ]

    played = []
    monkeypatch.setattr(online, "_do_search", fake_do_search)
    monkeypatch.setattr(online, "_play_queue", lambda results, args: played.extend(results))
    monkeypatch.setattr(online.config, "kill_stored", lambda: False)
    monkeypatch.setattr(online, "_clear_all_nav", lambda: None)
    yield played


def _titles(played):
    return [title for _entry, title, _dur in played]


def _args(**flags):
    import argparse

    args = argparse.Namespace(bg=False, download=False, repeat=False, shuffle=False)
    for key, value in flags.items():
        setattr(args, key, value)
    return args


def test_only_results_whose_title_credits_the_artist_are_kept(fake_search):
    online.artist_track(["Karan Aujla"], _args())
    assert _titles(fake_search) == [
        "52 Bars (Official Video) Karan Aujla | Ikky",
        "Four You EP | Karan Aujla",
        "Softly Karan Aujla",
    ]


def test_the_artist_name_is_searched_with_songs(fake_search, monkeypatch):
    seen = []
    monkeypatch.setattr(
        online, "_do_search", lambda q: seen.append(q) or setattr(online, "_last_results", [])
    )
    online.artist_track(["Arijit Singh"], _args())
    assert seen == ["Arijit Singh songs"]


def test_results_are_sorted_by_title_not_search_rank(fake_search):
    online.artist_track(["Karan Aujla"], _args())
    assert _titles(fake_search) == sorted(_titles(fake_search), key=str.lower)


def test_s_shuffles_the_results(fake_search, monkeypatch):
    monkeypatch.setattr(online.random, "shuffle", lambda items: items.reverse())
    online.artist_track(["Karan Aujla"], _args(shuffle=True))
    assert _titles(fake_search) == [
        "Softly Karan Aujla",
        "Four You EP | Karan Aujla",
        "52 Bars (Official Video) Karan Aujla | Ikky",
    ]


def test_no_match_falls_back_to_the_queue_artist(fake_search, monkeypatch, capsys):
    """`artist karan` finds nothing, so the artist of the last played track is used."""
    library.track_download("queuevid", "/tmp/queuevid.opus", "Softly")
    library.update_meta("queuevid", {"artist": "Karan Aujla"})
    monkeypatch.setattr(online, "_last_played", ({"id": "queuevid"}, "Softly"))
    monkeypatch.setattr(online.status, "read", lambda: {})

    online.artist_track(["karan"], _args())

    assert "trying 'Karan Aujla' from the queue" in capsys.readouterr().out
    assert len(fake_search) == 3


def test_it_says_what_it_is_playing(fake_search, capsys):
    """The count and the artist are printed; `i()` returns None, so nesting it would."""
    online.artist_track(["Karan Aujla"], _args())
    out = capsys.readouterr().out
    assert "3 song(s) by Karan Aujla" in out
    assert "None" not in out


def test_a_bare_artist_explains_itself(fake_search, capsys):
    online.artist_track([], _args())
    assert "Usage: artist" in capsys.readouterr().out
    assert fake_search == []


def test_an_unknown_artist_says_so(fake_search, monkeypatch, capsys):
    monkeypatch.setattr(online, "_last_played", None)
    monkeypatch.setattr(online.status, "read", lambda: {})
    online.artist_track(["nobody at all"], _args())
    assert "No results for artist" in capsys.readouterr().out