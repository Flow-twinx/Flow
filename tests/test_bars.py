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

        def unsafe_ask(self):
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


def test_interactive_config_offers_prog_chars_for_progress(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    asked = _fake_interactive(
        monkeypatch,
        tmp_path,
        [
            "progress", "cyan", "purple", "blue", "webm",
            "|", "-",
            True, True, True, "5", "35",
        ],
    )
    # display, 3 colors, format, prog_char, prog_char_em, 3 confirms,
    # max_search, max_radio — the visualizer questions (width/height/
    # spacing/char/sensitivity) must NOT fire for progress.
    assert len(asked) == 12
    out = _clean(capsys.readouterr().out)
    assert "Progress char changed to |" in out
    assert "Progress empty char changed to -" in out
    assert "Bar width" not in out
    assert "Bar char changed" not in out
    assert "Bar height" not in out
    assert "Bar spacing" not in out
    assert "Sensitivity" not in out
    assert config.Display == "progress"
    assert config.ProgChar == "|"
    assert config.ProgCharEm == "-"


def test_interactive_config_hides_bar_chars_for_lyrics(
    monkeypatch, tmp_path, restore_config_globals
):
    asked = _fake_interactive(
        monkeypatch,
        tmp_path,
        [
            "lyrics", "cyan", "purple", "blue", "webm",
            True, True, True, "5", "35",
        ],
    )
    # display, 3 colors, format, 3 confirms, max_search, max_radio
    assert len(asked) == 10
    assert config.Display == "lyrics"


def test_interactive_config_keeps_visualizer_options_for_bars(
    monkeypatch, tmp_path, capsys, restore_config_globals
):
    asked = _fake_interactive(
        monkeypatch,
        tmp_path,
        [
            "bars", "cyan", "purple", "blue", "webm",
            "30", "40", "1", "|", "1.0",
            True, True, True, "5", "35",
        ],
    )
    assert len(asked) == 15
    out = _clean(capsys.readouterr().out)
    assert "Bar width changed to 30" in out
    assert "Bar height changed to 40" in out
    assert "Bar spacing changed to 1" in out
    assert "Bar char changed to |" in out
    assert "Sensitivity changed to 1.0" in out
    assert "Progress char" not in out
    assert config.BarWidth == 30
    assert config.BarHeight == 40
    assert config.BarSpacing == 1
    assert config.BarChar == "|"


def test_display_mode_accepts_progress():
    assert "progress" in config._DISPLAY_MODES
    msg = config._apply_display("progress")
    assert "changed to progress" in msg


def test_display_mode_accepts_rich():
    assert "rich" in config._DISPLAY_MODES
    msg = config._apply_display("rich")
    assert "changed to rich" in msg


def test_interactive_config_asks_rich_columns_for_rich(
    monkeypatch, tmp_path, restore_config_globals
):
    asked = _fake_interactive(
        monkeypatch,
        tmp_path,
        [
            "rich", "bar, time_remaining", "cyan", "purple", "blue", "webm",
            True, True, True, "5", "35",
        ],
    )
    # display, progress_columns, 3 colors, format, 3 confirms,
    # max_search, max_radio — the prog_char questions must NOT fire.
    assert len(asked) == 11
    assert config.Display == "rich"
    assert config.ProgressColumns == ["bar", "time_remaining"]


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