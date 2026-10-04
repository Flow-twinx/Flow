"""Tests that the web GUI lists songs ascending by name.

Web files are named after the YouTube id, so ordering the listings by filename
left the Local Files, Liked, Album and local-search panels in an order that
looked random next to the CLI's name-sorted `list`. Every route the GUI renders
a list of songs in now sorts on the displayed title, so all surfaces agree.
"""

import pathlib
import shutil

import pytest

from backend import library
from web import app as web_app


@pytest.fixture(autouse=True)
def clean_library_tree():
    """Start every test with an empty music tree; ids and titles are unique per test."""
    for base in (web_app.FLOW_DIR, web_app.MUSIC_DIR):
        shutil.rmtree(base, ignore_errors=True)
    yield


@pytest.fixture
def web_client():
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as client:
        yield client


def seed(path: pathlib.Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    library.track_download(path.stem, str(path), title)


def seed_download(name: str, title: str) -> pathlib.Path:
    path = web_app.FLOW_DIR / name
    seed(path, title)
    return path


def titles(client, url):
    return [row["title"] for row in client.get(url).get_json()["results"]]


def test_local_files_are_sorted_by_name_not_filename(web_client):
    """Ids are the reverse of the titles here, so filename order would fail."""
    seed_download("t1_zzz1.opus", "Alpha")
    seed_download("t1_aaa2.opus", "Zulu")
    seed_download("t1_mmm3.opus", "Mid")

    assert titles(web_client, "/offline") == ["Alpha", "Mid", "Zulu"]


def test_a_rename_moves_the_song_in_the_local_listing(web_client):
    seed_download("t2_zzz1.opus", "Alpha")
    seed_download("t2_aaa2.opus", "Zulu")
    assert titles(web_client, "/offline") == ["Alpha", "Zulu"]

    ok = web_client.post(
        "/api/library/rename", json={"video_id": "t2_aaa2", "title": "Aaa Zulu"}
    )
    assert ok.status_code == 200
    assert titles(web_client, "/offline") == ["Aaa Zulu", "Alpha"]


def test_a_new_download_slots_into_its_alphabetical_place(web_client):
    seed_download("t3_mmm1.opus", "Mid")
    seed_download("t3_zzz2.opus", "Zed")
    seed_download("t3_bra3.opus", "Bravo")

    assert titles(web_client, "/offline") == ["Bravo", "Mid", "Zed"]


def test_liked_songs_are_sorted_by_name(web_client):
    liked = web_app.FLOW_DIR / "liked songs"
    seed(liked / "t4_zzz3.opus", "Mid")
    seed(liked / "t4_aaa4.opus", "Bravo")

    assert titles(web_client, "/api/liked") == ["Bravo", "Mid"]


def test_album_songs_are_sorted_by_name(web_client):
    album = web_app.MUSIC_DIR / "Road Trip"
    seed(album / "t5_yyy5.mp3", "Delta")
    seed(album / "t5_xxx6.mp3", "Charlie")

    assert titles(web_client, "/api/album/Road%20Trip") == ["Charlie", "Delta"]


def test_local_search_results_are_sorted_by_name(web_client):
    seed_download("t6_zzz7.opus", "Match Zulu")
    seed_download("t6_aaa8.opus", "Match Alpha")

    assert titles(web_client, "/api/local-search?q=match") == ["Match Alpha", "Match Zulu"]


def test_a_song_missing_from_the_library_sorts_by_its_filename(web_client):
    """No library row means the filename is the displayed name, like the CLI."""
    orphan = web_app.FLOW_DIR / "zzz_orphan.opus"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"")
    seed_download("t7_yyy8.opus", "Zulu")

    assert titles(web_client, "/offline") == ["Zulu", "zzz_orphan"]