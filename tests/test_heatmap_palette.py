from gravity_lab.themes import FIELD_HEATMAP_STOPS, THEMES


def test_both_themes_share_the_same_heatmap_palette():
    expected = list(FIELD_HEATMAP_STOPS)
    assert set(THEMES) == {"Light", "Dark"}
    assert all(theme["field_stops"] == expected for theme in THEMES.values())


def test_theme_backgrounds_remain_theme_specific():
    assert len({theme["plot_bg"] for theme in THEMES.values()}) > 1
