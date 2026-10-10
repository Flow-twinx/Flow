import json
import pathlib
import re

import pytest

from backend import config
from backend.Online import youtube


def _clean(out):
    return re.sub(r"\x1b\[[0-9;]*m", "", out)


def test_progress_bar_fills_to_fraction():
    bar = config.progress_bar(0.5, 8)
    assert bar == (
        f"{config.Primary}{config.ProgChar * 4}{config.Reset}"
        f"{config.Muted}{config.ProgCharEm * 4}{config.Reset}"
    )


def test_progress_bar_clamps():
    full = config.progress_bar(1.5, 4)
    assert full == (
        f"{config.Primary}{config.ProgChar * 4}{config.Reset}"
        f"{config.Muted}{config.ProgCharEm * 0}{config.Reset}"
    )
    zero = config.progress_bar(-1, 4)
    assert zero == (
        f"{config.Primary}{''}{config.Reset}"
        f"{config.Muted}{config.ProgCharEm * 4}{config.Reset}"
    )


def test_prog_char_em_default_is_single_shade_char():
    assert config.ProgCharEm == "░"
    assert len(config.ProgCharEm) == 1


def test_prog_char_em_limits_to_one_char():
    msg = config._apply_prog_char_em("ab")
    assert "changed to a" in msg
    assert config.ProgCharEm == "a"
    config._apply_prog_char_em("░")


def test_prog_char_em_accepts_named_chars():
    config._apply_prog_char_em("block")
    assert config.ProgCharEm == "█"
    config._apply_prog_char_em("░")


def test_prog_chars_persist_and_load():
    config._apply_prog_char(".")
    saved = json.loads(
        pathlib.Path(config.CONFIG_FILE).read_text()
    )
    assert saved["prog_char"] == "."
    config._apply_prog_char_em("-")
    saved = json.loads(
        pathlib.Path(config.CONFIG_FILE).read_text()
    )
    assert saved["prog_char_em"] == "-"
    config._load_config()
    assert config.ProgChar == "."
    assert config.ProgCharEm == "-"
    config._apply_prog_char("█")
    config._apply_prog_char_em("░")


@pytest.fixture
def restore_config_globals():
    yield
    config.Display = "bars"
    config.BarWidth = 20
    config.BarHeight = 40
    config.BarSpacing = 1
    config.BarChar = "\u2588"
    config.ProgChar = "\u2588"
    config.ProgCharEm = "\u2591"
    config.Sensitivity = 1.0
    config.SPINNER = "|/-\\"
    config.Primary = config.CYAN
    config.Secondary = config.PURPLE
    config.Tertiary = config.BLUE
    config._STYLE["primary"] = "cyan"
    config._STYLE["secondary"] = "purple"
    config._STYLE["tertiary"] = "blue"
    config.ProgressColumns = ["bar", "percentage", "time_remaining"]
    config.FORMAT = "webm"
    config.MAX_SEARCH_RESULTS = 5
    config.MAX_RESULTS_RADIO = 35
    config.AD_SKIP = True
    config.DOWN_ON_LIKE = True
    config.NOTIFY = True


def _fake_interactive(monkeypatch, tmp_path, answers_seq):
    import questionary.prompts as qp

    answers = iter(answers_seq)
    asked = []
    collected = {}

    class _FakePrompt:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def unsafe_ask(self, patch_stdout=None):
            when = self.kwargs.get("when")
            if when is not None and not when(collected):
                return None
            name = self.kwargs.get("name")
            value = next(answers)
            if name is not None:
                collected[name] = value
            asked.append(name)
            return value

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(
        qp,
        "AVAILABLE_PROMPTS",
        {"select": _FakePrompt, "text": _FakePrompt, "confirm": _FakePrompt},
    )
    config._interactive_config()
    return asked


def test_interactive_config_picks_one_setting(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    asked = _fake_interactive(monkeypatch, tmp_path, ["bar_width", "30"])
    assert len(asked) == 2  # one pick + one value edit
    out = _clean(capsys.readouterr().out)
    assert "Bar width changed to 30" in out
    assert config.BarWidth == 30
    # nothing else was edited
    assert config.Display == "bars"
    assert config.ProgChar == "\u2588"
    assert config.ProgCharEm == "\u2591"


def test_interactive_config_picks_display(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    _fake_interactive(monkeypatch, tmp_path, ["display", "rich"])
    out = _clean(capsys.readouterr().out)
    assert "Display mode changed to rich" in out
    assert config.Display == "rich"


def test_interactive_config_picks_prog_char(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    _fake_interactive(monkeypatch, tmp_path, ["prog_char", "|"])
    out = _clean(capsys.readouterr().out)
    assert "Progress char changed to |" in out
    assert config.ProgChar == "|"


def test_interactive_config_picks_theme(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    _fake_interactive(monkeypatch, tmp_path, ["theme", "sunset"])
    out = _clean(capsys.readouterr().out)
    assert "Theme changed to 'sunset'" in out
    assert config._STYLE["primary"] == "orange1"
    assert config._STYLE["secondary"] == "pink1"


def test_interactive_config_picks_confirm(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    _fake_interactive(monkeypatch, tmp_path, ["notify", False])
    out = _clean(capsys.readouterr().out)
    assert "Desktop notifications set to False" in out
    assert config.NOTIFY is False


def test_interactive_config_lists_every_setting(restore_config_globals):
    config.Display = "rich"
    rows = config._interactive_rows()
    keys = {r[0] for r in rows}
    assert len(rows) == len(keys)  # no duplicate keys
    for key in (
        "display", "primary", "secondary", "tertiary", "theme", "spinner",
        "progress_columns", "format", "bar_width", "bar_height", "bar_spacing",
        "bar_char", "prog_char", "prog_char_em", "sensitivity", "ad_skip",
        "down_on_like", "notify", "max_search", "max_radio",
    ):
        assert key in keys


def test_interactive_config_hides_rich_columns_outside_rich(restore_config_globals):
    config.Display = "bars"
    keys = {r[0] for r in config._interactive_rows()}
    assert "progress_columns" not in keys
    assert "display" in keys


def test_display_mode_accepts_progress():
    assert "progress" in config._DISPLAY_MODES
    msg = config._apply_display("progress")
    assert "changed to progress" in msg


def test_display_mode_accepts_rich():
    assert "rich" in config._DISPLAY_MODES
    msg = config._apply_display("rich")
    assert "changed to rich" in msg


def test_progress_columns_accept_rich_options():
    assert all(c in config._RICH_COLUMN_NAMES for c in config.ProgressColumns)
    msg = config._apply_progress_columns("bar,percentage")
    assert "set to" in msg
    assert config.ProgressColumns == ["bar", "percentage"]
    other = config._apply_progress_columns("spinner time_remaining")
    assert "set to" in other
    bad = config._apply_progress_columns("bogus")
    assert "Unknown" in bad
    assert "bar" in bad and "spinner" in bad


def test_rich_color_styles_accepted():
    msg = config._apply_color("primary", "#ff8800")
    assert "changed to" in msg
    assert config._STYLE["primary"] == "#ff8800"
    bad = config._apply_color("secondary", "not_a_color")
    assert "Unknown" in bad


def test_rich_display_panel_renders(capsys, restore_config_globals):
    import backend.rich_display as rich_display

    disp = rich_display.NowPlaying("Some Track", artist="Artist", duration=120)
    disp.start()
    disp.update(30.0, paused=True)
    disp.stop()
    out = capsys.readouterr().out
    assert "Some Track" in out
    assert "Artist" in out
    assert "[Paused]" in out


def test_render_progress_writes_live_line(capsys):
    config.render_progress(63, 180, 8)
    out = _clean(capsys.readouterr().out)
    assert out.startswith("\r")
    assert "1:03 / 3:00" in out
    assert "35%" in out


def test_youtube_progress_hook_renders_bar(capsys):
    youtube.progress_hook(
        {
            "status": "downloading",
            "downloaded_bytes": 5_000_000,
            "total_bytes": 10_000_000,
            "info_dict": {"title": "Outro"},
        }
    )
    out = _clean(capsys.readouterr().out)
    assert out.startswith("\r")
    assert "Outro" in out
    assert "50.0%" in out


def test_youtube_progress_hook_ignores_other_statuses(capsys):
    youtube.progress_hook({"status": "finished"})
    assert capsys.readouterr().out == ""


def test_rich_progress_columns_dedupe(restore_config_globals):
    import backend.rich_display as rich_display

    config.ProgressColumns = ["bar", "task", "percentage"]
    columns = rich_display._progress().columns
    names = [type(c).__name__ for c in columns]
    assert names.count("TaskProgressColumn") == 1
    assert "BarColumn" in names


def test_rich_panel_width_is_small(restore_config_globals):
    import backend.rich_display as rich_display
    from rich.console import Console

    disp = rich_display.NowPlaying("Track", duration=60)
    disp.console = Console(width=100)
    assert 30 <= disp._panel_width() <= 80
    disp.console = Console(width=80)
    assert disp._panel_width() == 32


def test_rich_display_active_gates_on_display(monkeypatch, restore_config_globals):
    import backend.rich_display as rich_display
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    config.Display = "bars"
    assert rich_display.active() is False
    config.Display = "rich"
    assert rich_display.active() is True


def test_rich_panel_renders_track_metadata(capsys, restore_config_globals):
    import backend.rich_display as rich_display

    disp = rich_display.NowPlaying("First", duration=60)
    disp.start()
    disp.set_track(
        "Second", artist="Artist", album="Album", duration=120, status="playing"
    )
    disp.update(5.0)
    disp.stop()
    out = capsys.readouterr().out
    assert "Second" in out
    assert "Artist" in out
    assert "Album" in out
    assert "playin" in out  # subtitle truncates at the small width


def test_connection_spinner_delegates_to_rich(monkeypatch, restore_config_globals):
    import cli.main as cli_main
    import backend.rich_display as rich_display

    calls = []
    monkeypatch.setattr(rich_display, "active", lambda: True)
    monkeypatch.setattr(
        rich_display, "spinner_run", lambda stop, label="": calls.append(label)
    )
    config.Display = "rich"
    cli_main._spinner(lambda: True)
    assert calls == ["Checking connection"]


def test_search_spinner_delegates_to_rich(monkeypatch, restore_config_globals):
    from backend.Online import commands as online_commands
    import backend.rich_display as rich_display

    calls = []
    monkeypatch.setattr(rich_display, "active", lambda: True)
    monkeypatch.setattr(
        rich_display, "spinner_run", lambda stop, label="": calls.append(label)
    )
    config.Display = "rich"
    online_commands._spinner(lambda: True, label="Searching")
    assert calls == ["Searching"]


def test_download_hook_delegates_to_rich(monkeypatch, restore_config_globals):
    import backend.rich_display as rich_display

    calls = []
    monkeypatch.setattr(rich_display, "active", lambda: True)
    monkeypatch.setattr(
        rich_display,
        "download_update",
        lambda got, total: calls.append((got, total)),
    )
    youtube.progress_hook(
        {
            "status": "downloading",
            "downloaded_bytes": 5_000_000,
            "total_bytes": 10_000_000,
        }
    )
    assert calls == [(5_000_000, 10_000_000)]