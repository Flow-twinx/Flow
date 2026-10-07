"""Tests for the one-word tags trimmed out of a track's metadata.

A download keeps two tags: `language` (one word, from YouTube's language field
or the script the title/description is written in) and `artist` (the credited
name, not the channel). `language` is what `lang <tag>` filters on and `artist`
is what `artist <name>` filters on, so a wrong tag hides a song from playback
by tag.
"""

import pytest

from backend import library, tags


@pytest.mark.parametrize(
    "value,expected",
    [
        ("pa", "punjabi"),
        ("hi", "hindi"),
        ("en-US", "english"),
        ("zh_Hans", "chinese"),
        (["ta"], "tamil"),
        ("Punjabi", "punjabi"),
        ("INDIAN", "other"),
        ("xx", "other"),
        ("", ""),
        (None, ""),
        ([], ""),
    ],
)
def test_normalize_language_gives_one_word(value, expected):
    assert tags.normalize_language(value) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("बुल्लेया", "hindi"),
        ("బుల్లేయ", "telugu"),
        ("தமிழ் பாடல்", "tamil"),
        ("ਪੰਜਾਬੀ ਗਾਣਾ", "punjabi"),
        ("Айел ай", "russian"),
        ("안녕하세요", "korean"),
        ("こんにちは", "japanese"),
        ("52 Bars", "english"),
        ("", ""),
    ],
)
def test_detect_language_reads_the_script(text, expected):
    assert tags.detect_language(text) == expected


def test_the_language_field_beats_the_script():
    """A Roman-script Punjabi title still tags as punjabi."""
    info = {"title": "52 Bars", "language": "pa", "description": ""}
    assert tags.tags_from_info(info)["language"] == "punjabi"


def test_the_script_is_used_when_youtube_reports_no_language():
    assert tags.tags_from_info({"title": "బుల్లేయ song"})["language"] == "telugu"
    assert tags.tags_from_info({"title": "Bulleya"})["language"] == "english"


def test_the_title_wins_over_a_foreign_description():
    info = {"title": "బుల్లేయ", "description": "Singer: Someone"}
    assert tags.tags_from_info(info)["language"] == "telugu"


def test_the_yt_dlp_artist_is_used_when_present():
    info = {"title": "Senorita", "artist": "Marshmello, Shippai"}
    assert tags.artist_from_info(info) == "Marshmello, Shippai"


def test_a_list_of_artists_is_kept_whole():
    info = {"title": "Thoda Thoda Pyaar", "artists": ["Stebin Ben", "Nilesh Ahuja"]}
    assert tags.artist_from_info(info) == "Stebin Ben, Nilesh Ahuja"


@pytest.mark.parametrize("junk", ["None", "none", "null", "N/A", "unknown", "  "])
def test_placeholder_artists_are_dropped(junk):
    """yt-dlp hands back the literal string "None" for plenty of music videos."""
    info = {"title": "Senorita | Marshmello, Shippai", "artist": junk}
    assert tags.artist_from_info(info) == "Marshmello, Shippai"


def test_the_description_credit_is_used_when_youtube_has_no_artist():
    info = {
        "title": "Aage Peeche Golmaal",
        "artist": None,
        "description": "Sandeep Rehaan & Karan Aujla Present\nSINGER/LYRICS/COMPOSER - KARAN AUJLA\nMUSIC - IKKY",
    }
    assert tags.artist_from_info(info) == "KARAN AUJLA"


def test_the_title_is_the_last_resort_for_an_artist():
    info = {"title": "Senorita | Marshmello, Shippai | Senorita"}
    assert tags.artist_from_info(info) == "Marshmello, Shippai"


def test_a_title_with_nothing_credited_yields_no_artist():
    assert tags.artist_from_info({"title": "Aage Peeche Golmaal"}) == ""


def test_meta_from_info_trims_to_what_the_library_stores():
    info = {
        "title": "52 Bars (Official Video) Karan Aujla | Ikky",
        "language": "pa",
        "album": "Four You EP",
        "duration": 191,
        "categories": ["Music"],
        "tags": ["52 bars", "four you"],
    }
    assert library.meta_from_info(info) == {
        "artist": "Karan Aujla",
        "language": "punjabi",
        "album": "Four You EP",
        "duration": 191,
    }


@pytest.fixture
def song():
    """A fresh video id per test, so the shared scratch library stays clean."""
    song.counter = getattr(song, "counter", 0) + 1
    return f"tagvid{song.counter:03d}"


def test_a_download_stores_both_tags(song, tmp_path):
    path = tmp_path / f"{song}.opus"
    path.write_bytes(b"")
    library.track_download(
        song,
        str(path),
        "52 Bars",
        library.meta_from_info(
            {"title": "52 Bars (Official Video) Karan Aujla", "language": "pa"}
        ),
    )
    entry = library.get(song)
    assert entry["language"] == "punjabi"
    assert entry["artist"] == "Karan Aujla"


def test_a_tag_is_stored_lower_case(song, tmp_path):
    path = tmp_path / f"{song}.opus"
    path.write_bytes(b"")
    library.track_download(song, str(path), "x", {"language": "  Punjabi "})
    assert library.get(song)["language"] == "punjabi"