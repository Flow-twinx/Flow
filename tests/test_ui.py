from backend import config
from backend import ui


def test_questionary_style_builds_from_current_palette():
    # Both modes must build a valid prompt_toolkit Style from the rich
    # palette (named colors, hex, styled strings) without ValueError.
    online = ui.questionary_style("online")
    offline = ui.questionary_style("offline")
    assert str(online)
    assert str(offline)
    assert ui.questionary_style() is not None


def test_cname_resolves_ansi_codes_from_rich_styles():
    # ANSI codes that still reach _cname (old call sites / plugins)
    # must resolve back to a prompt_toolkit color instead of crashing.
    for code in (config.Primary, config.Secondary, config.Tertiary):
        color = config._cname(code)
        assert color
        assert color != code  # resolved, not passed through raw


def test_cname_resolves_arbitrary_rich_styles():
    assert config._cname("#ff8800") == "#ff8800"
    assert config._cname("bold spring_green3").startswith("#")