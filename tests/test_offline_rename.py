"""Tests for `rename` in offline mode.

A number has to mean the row it means in the `list` output — the library
sorted ascending by name — no matter what ran before it. `_last_results` is
volatile (every `search`, `play` and `list` replaces it), so resolving an
index through it meant `re 1` renamed whichever song happened to sit first in
an unrelated list: the listing said `1. 52 Bars`, the prompt said `Bulleya`.

Uses the scratch `HOME` from `conftest.py`; the library is faked so the
assertions are about target resolution, not disk scanning.
"""

import builtins
import pathlib

import pytest

from backend.Offline import commands as offline

SORTED = [
    pathlib.Path(f"/music/{name}.mp3")
    for name in ("52 Bars", "Aankhon", "Bulleya", "Zed")
]


@pytest.fixture(autouse=True)
def fake_library(monkeypatch):
    monkeypatch.setattr(offline.lib, "get_songs", lambda: list(SORTED))
    monkeypatch.setattr(
        offline.lib,
        "find_songs",
        lambda q: [p for p in SORTED if q.lower() in p.stem.lower()],
    )
    monkeypatch.setattr(offline.lib, "display_name", lambda p: p.stem)
    monkeypatch.setattr(offline, "_last_results", [])
    yield


@pytest.fixture
def renames(monkeypatch):
    """Record what `library.rename` would have written."""
    calls = []
    monkeypatch.setattr(offline.library, "rename", lambda vid, title: calls.append((vid, title)) or True)
    return calls


@pytest.fixture
def typed(monkeypatch):
    """Answer the `New name for '...'` prompt and capture what it said."""
    seen = {}

    def fake_input(prompt=""):
        seen["prompt"] = prompt
        return seen.get("answer", "Second Try")

    monkeypatch.setattr(builtins, "input", fake_input)
    return seen


def _args():
    return type("Args", (), {"bg": False, "download": False, "repeat": False,
                             "shuffle": False, "repeat_count": 0, "multi": False})()


def test_a_number_means_the_row_in_the_sorted_listing():
    assert offline._match_songs("1", prefer_library=True)[0].stem == "52 Bars"
    assert offline._match_songs("3", prefer_library=True)[0].stem == "Bulleya"


def test_a_stale_last_results_cannot_hijack_the_number(monkeypatch):
    """The regression: Bulleya was first in `_last_results`, so `re 1` hit it."""
    monkeypatch.setattr(offline, "_last_results", [SORTED[2]])
    assert offline._match_songs("1", prefer_library=True)[0].stem == "52 Bars"


def test_a_number_past_the_library_falls_back_to_last_results(monkeypatch):
    monkeypatch.setattr(offline, "_last_results", [pathlib.Path("/music/x.mp3")] * 9)
    assert offline._match_songs("7", prefer_library=True)[0].stem == "x"


def test_an_out_of_range_number_is_reported():
    assert offline._match_songs("500", prefer_library=True) is None


def test_a_name_still_matches_without_an_index():
    assert [p.stem for p in offline._match_songs("Bulley", prefer_library=True)] == ["Bulleya"]


def test_rename_asks_for_the_new_name_and_stores_it(renames, typed):
    offline.rename_track(["1"])
    assert renames == [("52 Bars", "Second Try")]
    assert "New name for '52 Bars (#1)'" in typed["prompt"]


def test_the_prompt_repeats_the_list_number(renames, typed):
    """So the row you picked is visible before you commit to it."""
    offline.rename_track(["3"])
    assert "#3" in typed["prompt"]
    assert renames == [("Bulleya", "Second Try")]


def test_a_blank_answer_changes_nothing(renames, typed):
    typed["answer"] = ""
    offline.rename_track(["1"])
    assert renames == []


def test_the_re_alias_dispatches_to_rename(renames, typed):
    offline.run("re", ["Bulleya"], _args())
    assert renames == [("Bulleya", "Second Try")]


def test_a_bare_rename_explains_itself(renames, typed, capsys):
    offline.rename_track([])
    assert renames == []
    assert "rename <name | index>" in capsys.readouterr().out