import json

import pytest

from backend import lyrics
from web import app as web_app


LRC = """[ar:Queen]
[ti:Bohemian Rhapsody]
[00:00.15] Is this the real life? Is this just fantasy?
[00:07.13] Caught in a landslide, no escape from reality
[00:55.36] Mama, just killed a man
[01:01.95] Put a gun against his head, pulled my trigger, now he's dead
"""

FLAT_LRC = "[00:01] hello\n[00:04] world\n"


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeYTLine:
    def __init__(self, text, start_time, end_time=None):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time


def test_parse_lrc_skips_metadata_and_sets_ends():
    lines = lyrics.parse_lrc(LRC)
    assert [line["text"] for line in lines] == [
        "Is this the real life? Is this just fantasy?",
        "Caught in a landslide, no escape from reality",
        "Mama, just killed a man",
        "Put a gun against his head, pulled my trigger, now he's dead",
    ]
    assert lines[0]["start"] == 0.15
    assert lines[0]["end"] == 7.13
    assert lines[3]["start"] == 61.95


def test_parse_lrc_last_line_ends_at_duration():
    lines = lyrics.parse_lrc(FLAT_LRC, duration=10)
    assert lines[-1]["end"] == 10
    assert lyrics.parse_lrc(FLAT_LRC)[-1]["end"] == 9.0


def test_parse_lrc_handles_hours_repeats_and_word_tags():
    lines = lyrics.parse_lrc(
        "[00:01.00] <00:01.00> hey <00:01.50> there\n"
        "[01:02:03.45] late\n"
        "[00:09.00][00:09.50] twice\n"
    )
    assert lines[0]["text"] == "hey there"
    assert [line["start"] for line in lines] == [1.0, 9.0, 9.5, 3723.45]


def test_parse_lrc_ignores_non_numeric_tags_and_empty_input():
    assert lyrics.parse_lrc("[ar:Queen]\n[al:News of the World]\n") == []
    assert lyrics.parse_lrc("") == []


def test_clean_title_strips_youtube_noise():
    assert lyrics.clean_title("Queen - Bohemian Rhapsody (Official Video)") == (
        "Bohemian Rhapsody"
    )
    assert lyrics.clean_title("Bohemian Rhapsody - Official Music Video [HD]") == (
        "Bohemian Rhapsody"
    )
    assert lyrics.clean_title("Artist - Song (Lyrics) - Official Video") == "Song"
    assert lyrics.clean_title("official video") == ""


def test_split_artist_title():
    assert lyrics.split_artist_title("Radiohead - Creep (Official Video)") == (
        "Radiohead",
        "Creep",
    )
    assert lyrics.split_artist_title("Creep") == ("", "Creep")


def test_synced_only_record_still_yields_clean_plain_text():
    found = lyrics._from_lrclib({"syncedLyrics": FLAT_LRC})
    assert found["plain"] == ["hello", "world"]


def test_find_line_and_find_index():
    lines = lyrics.parse_lrc(FLAT_LRC)
    assert lyrics.find_line(lines, 2) == "hello"
    assert lyrics.find_line(lines, 5) == "world"
    assert lyrics.find_index(lines, 0.5) == -1
    assert lyrics.find_line({"lines": lines}, 5) == "world"
    assert lyrics.find_line([], 1) is None


@pytest.fixture
def client():
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_lyrics_cache():
    lyrics.clear_cache()
    yield
    lyrics.clear_cache()


@pytest.fixture
def lrclib(monkeypatch):

    calls = []

    def fake_json(endpoint, params):
        calls.append((endpoint, params))
        if endpoint == "get":
            return records.get("get")
        return records.get("search")

    records = {"get": None, "search": None}
    monkeypatch.setattr(lyrics, "_lrclib_json", fake_json)
    return records, calls


@pytest.fixture
def no_ytmusic(monkeypatch):
    monkeypatch.setattr(
        lyrics,
        "_fetch_ytmusic",
        lambda *a, **k: pytest.fail("ytmusic should not be reached"),
    )


def test_lrclib_get_is_preferred(lrclib, no_ytmusic):
    records, calls = lrclib
    records["get"] = {"syncedLyrics": FLAT_LRC, "plainLyrics": "hello\nworld"}

    found = lyrics.fetch_lyrics("vid1", title="Bohemian Rhapsody", artist="Queen")

    assert found["source"] == "lrclib"
    assert found["synced"] is True
    assert found["lines"][0]["start"] == 1.0
    assert [endpoint for endpoint, _ in calls] == ["get"]


def test_ytmusic_used_when_lrclib_has_nothing(lrclib, monkeypatch):
    records, _ = lrclib
    seen = {}

    def fake_ytmusic(video_id, title):
        seen["title"] = title
        return {
            "lines": [{"text": "yt line", "start": 1.0, "end": 3.0}],
            "plain": ["yt line"],
            "synced": True,
            "source": "ytmusic",
        }

    monkeypatch.setattr(lyrics, "_fetch_ytmusic", fake_ytmusic)

    found = lyrics.fetch_lyrics("vid1", title="Nothing Known Here")

    assert found["source"] == "ytmusic"
    assert seen["title"] == "Nothing Known Here"


def test_synced_ytmusic_beats_unsynced_lrclib(lrclib, monkeypatch):
    records, calls = lrclib
    records["get"] = {"plainLyrics": "just words"}
    records["search"] = []
    monkeypatch.setattr(
        lyrics,
        "_fetch_ytmusic",
        lambda *a, **k: {
            "lines": [{"text": "timed", "start": 0.0, "end": 1.0}],
            "plain": ["timed"],
            "synced": True,
            "source": "ytmusic",
        },
    )

    found = lyrics.fetch_lyrics("vid1", title="Some Song", artist="Nobody")

    assert found["source"] == "ytmusic"
    assert [endpoint for endpoint, _ in calls] == ["get", "search"]


def test_search_answers_when_artist_unknown(lrclib, no_ytmusic):
    records, calls = lrclib
    records["search"] = [
        {"syncedLyrics": "", "plainLyrics": "live cut", "duration": 300},
        {"syncedLyrics": FLAT_LRC, "plainLyrics": "hello\nworld", "duration": 202},
    ]

    found = lyrics.fetch_lyrics(title="Blinding Lights", duration=202)

    assert found["synced"] is True
    assert calls[0][0] == "search"


def test_untimed_lrclib_hit_kept_when_no_video_id(lrclib, no_ytmusic):
    records, _ = lrclib
    records["get"] = {"plainLyrics": "just words"}

    found = lyrics.fetch_lyrics(title="Local Track", artist="Nobody")

    assert found["synced"] is False
    assert found["plain"] == ["just words"]


def test_no_source_anywhere_returns_none(lrclib, monkeypatch):
    monkeypatch.setattr(lyrics, "_fetch_ytmusic", lambda *a, **k: None)
    assert lyrics.fetch_lyrics(title="Obscure", artist="Nobody") is None


def test_ytmusic_failure_is_swallowed(lrclib, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ytmusic down")

    monkeypatch.setattr(lyrics, "_fetch_ytmusic", boom)
    assert lyrics.fetch_lyrics("vid1", title="Obscure") is None


def test_results_are_cached(lrclib, monkeypatch):
    records, calls = lrclib
    records["get"] = {"syncedLyrics": FLAT_LRC}
    monkeypatch.setattr(lyrics, "_fetch_ytmusic", lambda *a, **k: None)

    first = lyrics.fetch_lyrics("vid1", title="Cached Song")
    second = lyrics.fetch_lyrics("vid1", title="Cached Song")

    assert first is second
    assert len(calls) == 1


def test_corrected_title_re_queries_the_same_video(lrclib):
    records, calls = lrclib
    records["get"] = {"syncedLyrics": FLAT_LRC}

    lyrics.fetch_lyrics("vid1", title="52 bars karan")
    lyrics.fetch_lyrics("vid1", title="52 Bars")

    assert len(calls) == 2


def test_lrclib_json_survives_http_errors(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(lyrics.urllib.request, "urlopen", boom)
    assert lyrics._lrclib_json("get", {"track_name": "x", "artist_name": "y"}) is None


def test_lrclib_json_returns_payload(monkeypatch):
    monkeypatch.setattr(
        lyrics.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResponse({"trackName": "x"}),
    )
    assert lyrics._lrclib_json("get", {"track_name": "x"}) == {"trackName": "x"}


def test_web_route_returns_normalized_lyrics(client, monkeypatch):
    seen = {}

    def fake_fetch(video_id=None, title=None, artist=None, album=None, duration=0):
        seen.update(
            video_id=video_id,
            title=title,
            artist=artist,
            duration=duration,
        )
        return {
            "lines": [{"text": "hello", "start": 1.0, "end": 4.0}],
            "plain": ["hello"],
            "synced": True,
            "source": "lrclib",
        }

    monkeypatch.setattr(web_app.lyrics, "fetch_lyrics", fake_fetch)

    response = client.get(
        "/api/lyrics",
        query_string={
            "video_id": "vid1",
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "duration": 355,
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["found"] is True
    assert body["lyrics"]["source"] == "lrclib"
    assert body["lyrics"]["lines"][0]["text"] == "hello"
    assert seen == {
        "video_id": "vid1",
        "title": "Bohemian Rhapsody",
        "artist": "Queen",
        "duration": 355.0,
    }


def test_web_route_reports_miss(client, monkeypatch):
    monkeypatch.setattr(web_app.lyrics, "fetch_lyrics", lambda *a, **k: None)
    response = client.get("/api/lyrics", query_string={"title": "Obscure"})
    assert response.get_json() == {"lyrics": None, "found": False}


def test_web_route_requires_a_track(client):
    assert client.get("/api/lyrics").status_code == 400