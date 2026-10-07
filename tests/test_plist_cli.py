import argparse
import re
import uuid

import pytest

from backend import config, playlist, plist_cli


def _clean(out: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", out)


@pytest.fixture
def plname():
    name = f"m-test-{uuid.uuid4().hex[:6]}"
    playlist.create(name)
    yield name
    playlist.delete(name)


def _track_source(words, args=None):
    word = words[0]
    if word == "missing":
        return None
    return playlist.make_track(title=word, ref="x://" + word, video_id=word)


def _titles(name):
    return [t.get("title") for t in playlist.get(name)]


def test_add_multi_adds_one_track_per_word(plname, capsys):
    plist_cli.handle(
        ["add", "-m", plname, "alpha", "beta", "gamma"],
        hooks={"add_source": _track_source},
    )
    assert _titles(plname) == ["alpha", "beta", "gamma"]
    out = _clean(capsys.readouterr().out)
    assert "Added 3 to" in out
    assert "alpha, beta, gamma" in out


def test_add_multi_flag_after_the_name(plname, capsys):
    plist_cli.handle(
        ["add", plname, "-m", "alpha", "beta"],
        hooks={"add_source": _track_source},
    )
    assert _titles(plname) == ["alpha", "beta"]


def test_add_multi_skips_duplicates_and_reports_failures(plname, capsys):
    plist_cli.handle(
        ["add", "-m", plname, "alpha", "alpha", "missing"],
        hooks={"add_source": _track_source},
    )
    assert _titles(plname) == ["alpha"]
    out = _clean(capsys.readouterr().out)
    assert "1 skipped, 1 failed" in out


def test_add_without_m_keeps_single_query_joining(plname, capsys):
    seen = []

    def hook(words, args=None):
        seen.append(tuple(words))
        return _track_source(words)

    plist_cli.handle(["add", plname, "alpha", "beta"], hooks={"add_source": hook})
    assert seen == [("alpha", "beta")]
    assert _titles(plname) == ["alpha"]


def test_remove_multi_by_index_resolves_high_to_low(plname, capsys):
    for w in ("alpha", "beta", "gamma", "delta"):
        playlist.add_track(
            plname, playlist.make_track(title=w, ref="x://" + w, video_id=w)
        )
    plist_cli.handle(["remove", "-m", plname, "1", "3", "10"])
    assert _titles(plname) == ["beta", "delta"]
    out = _clean(capsys.readouterr().out)
    assert "Removed 2 from" in out
    assert "1 not found" in out


def test_remove_multi_by_title(plname, capsys):
    for w in ("alpha", "beta", "gamma"):
        playlist.add_track(
            plname, playlist.make_track(title=w, ref="x://" + w, video_id=w)
        )
    plist_cli.handle(["remove", plname, "-m", "gamma", "alpha"])
    assert _titles(plname) == ["beta"]


def test_add_multi_survives_shell_merge_flags(plname, capsys):
    # In the interactive shell `-m` is stripped into args.multi by
    # config.merge_flags() before plist_cli sees the rest of the line.
    args = argparse.Namespace()
    extra, args = config.merge_flags(["add", "-m", plname, "alpha", "beta"], args)
    assert extra == ["add", plname, "alpha", "beta"]
    assert getattr(args, "multi") is True
    plist_cli.handle(extra, args, hooks={"add_source": _track_source})
    assert _titles(plname) == ["alpha", "beta"]
    out = _clean(capsys.readouterr().out)
    assert "Added 2 to" in out


def test_remove_multi_survives_shell_merge_flags(plname, capsys):
    for w in ("alpha", "beta", "gamma"):
        playlist.add_track(
            plname, playlist.make_track(title=w, ref="x://" + w, video_id=w)
        )
    args = argparse.Namespace()
    extra, args = config.merge_flags(["remove", "-m", plname, "1", "3"], args)
    plist_cli.handle(extra, args)
    assert _titles(plname) == ["beta"]