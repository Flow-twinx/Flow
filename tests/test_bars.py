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

    class _FakePrompt:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def unsafe_ask(self):
            asked.append(self.kwargs.get("name"))
            return next(answers)

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