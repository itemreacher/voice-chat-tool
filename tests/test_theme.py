from pathlib import Path

import pytest

from vct import theme
from vct.paths import resource_dir

NORMAL_TEXT = 4.5  # WCAG AA for body text


@pytest.mark.parametrize("fg,bg", [
    (theme.TEXT, theme.BG), (theme.TEXT, theme.PANEL), (theme.MUTED, theme.BG),
    (theme.MUTED, theme.PANEL), (theme.GOLD, theme.BG), (theme.GOLD, theme.PANEL_HI),
    (theme.GOLD_HI, theme.PANEL), (theme.MUTED, theme.PANEL_HI),
    (theme.BG, theme.RED), (theme.BG, theme.RED_HI), (theme.BG, theme.GOLD),
    (theme.BG, theme.TEAL), (theme.BG, theme.GOLD_HI), (theme.BG, theme.MUTED),
])
def test_text_contrast_is_readable(fg, bg):
    assert theme.contrast(fg, bg) >= NORMAL_TEXT


def test_contrast_extremes():
    assert theme.contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert theme.contrast("#777777", "#777777") == pytest.approx(1.0)


def test_every_state_has_a_colour():
    from vct.gui import STATE_TEXT

    assert set(STATE_TEXT) == set(theme.STATE_COLORS)


def test_resource_dir():
    here = Path("/p")
    assert resource_dir(False, None, here) == here
    assert resource_dir(True, "/bundle", here) == Path("/bundle")
    assert resource_dir(True, None, here) == here
