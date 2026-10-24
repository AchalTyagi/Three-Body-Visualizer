from gravity_lab.themes import FIELD_HEATMAP_STOPS, THEMES


def test_all_themes_use_midnight_dark_heatmap_palette():
    expected = THEMES["Midnight Dark"]["field_stops"]
    assert tuple(expected) == FIELD_HEATMAP_STOPS
    assert all(theme["field_stops"] == expected for theme in THEMES.values())


def test_theme_backgrounds_remain_theme_specific():
    assert len({theme["plot_bg"] for theme in THEMES.values()}) > 1
