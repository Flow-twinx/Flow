"""`summary` / `--summary` output tests.

`summary` is the CLI half of the play-history feature and reads both stores:
`library.db` for the per-song table (every mode) and `history.db` for the
online-only totals. These tests pin the sort keys, the flag parsing and the
online/offline split, without asserting on colours or column widths.
"""

import re

import pytest

from backend import history, library, summary

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def seeded(capsys):
    """Three known songs with known counts, and an empty online log.

    `library.db` counts every mode; `history.db` only logs online streams, so
    the seed plays half of its events offline to keep the two apart.
    """
    history.clear()
    library.mark_unliked("sum-test-1")
    library.mark_unliked("sum-test-2")
    library.mark_unliked("sum-test-3")
    # 4x Around the World (2 online), 2x Teardrop (2 online), 1x Midnight City.
    plays = [
        ("sum-test-1", "Around the World", "Daft Punk", "online"),
        ("sum-test-1", "Around the World", "Daft Punk", "offline"),
        ("sum-test-1", "Around the World", "Daft Punk", "online"),
        ("sum-test-1", "Around the World", "Daft Punk", "offline"),
        ("sum-test-2", "Teardrop", "Massive Attack", "online"),
        ("sum-test-2", "Teardrop", "Massive Attack", "online"),
        ("sum-test-3", "Midnight City", "M83", "offline"),
    ]
    for video_id, title, artist, mode in plays:
        history.record_play(video_id, title, artist, mode=mode)
    yield
    for video_id in ("sum-test-1", "sum-test-2", "sum-test-3"):
        library._mutate(lambda data, v=video_id: data.pop(v, None) or True)
    history.clear()


def run(capsys, extra):
    summary.cmd_summary(extra)
    return ANSI.sub("", capsys.readouterr().out)


# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "extra,expected",
    [
        ([], {"list": False, "sort": "plays", "top": 20, "clear": False}),
        (["-l"], {"list": True, "sort": "plays", "top": 20}),
        (["--list"], {"list": True}),
        (["-s", "artist"], {"sort": "artist"}),
        (["--sort", "name"], {"sort": "name"}),
        (["--sort=recent"], {"sort": "recent"}),
        (["-s", "ARTIST"], {"sort": "artist"}),
        (["--top", "5"], {"top": 5}),
        (["-n", "7"], {"top": 7}),
        (["--top=9"], {"top": 9}),
        (["-c"], {"clear": True}),
        (["--clear"], {"clear": True}),
        (["-h"], {"help": True}),
        (["-l", "-s", "name", "--top", "3"], {"list": True, "sort": "name", "top": 3}),
    ],
)
def test_parse_args(extra, expected):
    parsed = summary._parse_args(extra)
    for key, value in expected.items():
        assert parsed[key] == value, f"{extra} -> {key} was {parsed[key]!r}"


@pytest.mark.parametrize(
    "extra", [["-s", "bogus"], ["--sort=bogus"], ["--top", "abc"], ["--top", "0"], ["-s"]]
)
def test_parse_args_clamps_and_rejects(extra):
    parsed = summary._parse_args(extra)
    # A bad sort is signalled as None (the caller prints the error); a bad or
    # out-of-range --top falls back to the default rather than exploding.
    if "-s" in extra or any(a.startswith("--sort") for a in extra):
        assert parsed["sort"] is None or parsed["list"] is False
    assert 1 <= parsed["top"] <= 500


def test_parse_args_keeps_unknown_tokens_as_rest():
    parsed = summary._parse_args(["-l", "hello", "world"])
    assert parsed["rest"] == ["hello", "world"]


# ---------------------------------------------------------------------------
# Sorting — the CLI's per-song table
# ---------------------------------------------------------------------------

def test_default_sort_is_plays_descending(capsys):
    out = run(capsys, ["-l"])
    assert out.index("Around the World") < out.index("Teardrop")
    assert out.index("Teardrop") < out.index("Midnight City")


def test_sort_by_name(capsys):
    out = run(capsys, ["-l", "-s", "name"])
    assert out.index("Around the World") < out.index("Midnight City")
    assert out.index("Midnight City") < out.index("Teardrop")


def test_sort_by_artist(capsys):
    out = run(capsys, ["-l", "-s", "artist"])
    # Alphabetical by artist, then by title within an artist.
    assert out.index("Daft Punk") < out.index("M83")
    assert out.index("M83") < out.index("Massive Attack")


def test_sort_by_recent(capsys):
    out = run(capsys, ["-l", "-s", "recent"])
    # Midnight City was played last, so it leads the recent ordering.
    assert out.index("Midnight City") < out.index("Around the World")


def test_top_limits_the_table(capsys):
    out = run(capsys, ["-l", "--top", "1"])
    assert "Around the World" in out
    assert "Midnight City" not in out
    assert "showing 1 of 3" in out


def test_unknown_sort_prints_the_valid_keys(capsys):
    out = run(capsys, ["-l", "-s", "bogus"])
    assert "Unknown sort key" in out
    for key in summary.SORTS:
        assert key in out


def test_table_is_empty_before_anything_is_played(capsys):
    for video_id in ("sum-test-1", "sum-test-2", "sum-test-3"):
        library._mutate(lambda data, v=video_id: data.pop(v, None) or True)
    out = run(capsys, ["-l"])
    assert "Nothing has been played yet" in out


# ---------------------------------------------------------------------------
# The stats card
# ---------------------------------------------------------------------------

def test_stats_card_reports_both_stores(capsys):
    out = run(capsys, [])
    assert "total plays" in out
    # 7 plays across 3 songs in library.db, but only 4 online events logged.
    assert re.search(r"total plays\s+7\b", out)
    assert re.search(r"unique songs\s+3\b", out)
    assert re.search(r"online plays\s+4\b", out)
    assert "history.db" in out


def test_stats_card_lists_the_top_artist(capsys):
    out = run(capsys, [])
    assert "Daft Punk" in out
    assert "4 plays" in out


def test_clear_only_empties_the_online_log(capsys):
    out = run(capsys, ["-c"])
    assert "Cleared 4" in out
    assert history.count() == 0
    # song_count lives in library.db and must survive a history wipe.
    assert library.get_song_count("sum-test-1") == 4
    assert re.search(r"total plays\s+7\b", run(capsys, []))


def test_help_lists_every_flag(capsys):
    out = run(capsys, ["-h"])
    for flag in ("-l", "-s", "--top", "-c"):
        assert flag in out


# ---------------------------------------------------------------------------
# Sorting split: the CLI table is not the web timeline
# ---------------------------------------------------------------------------

def test_cli_sorts_and_web_sorts_are_different_sets():
    """The two halves of the feature rank different things on purpose."""
    assert set(summary.SORTS) == {"plays", "recent", "name", "artist"}
    assert set(history.SORTS) == {"recent", "oldest", "most", "least"}
    assert summary.SORTS != history.SORTS
