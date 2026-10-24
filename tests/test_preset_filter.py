from gravity_lab.presets import PRESETS, PRESET_NAMES
from gravity_lab.ui.preset_panel import filter_preset_names


def test_preset_filter_returns_all_items_for_blank_query():
    assert filter_preset_names("", PRESET_NAMES, PRESETS, "Custom") == ["Custom", *PRESET_NAMES]


def test_preset_filter_matches_names_case_insensitively():
    result = filter_preset_names("figure-eight", PRESET_NAMES, PRESETS, "Custom")
    assert result[0] == "Custom"
    assert any("Figure-eight" in name for name in result)
    assert len(result) < len(PRESET_NAMES) + 1


def test_preset_filter_matches_family_and_description():
    by_family = filter_preset_names("isosceles", PRESET_NAMES, PRESETS, "Custom")
    by_description = filter_preset_names("nominal period", PRESET_NAMES, PRESETS, "Custom")
    assert len(by_family) >= 1
    assert len(by_description) > 1


def test_preset_filter_keeps_custom_model_available_for_no_matches():
    assert filter_preset_names("no such preset", PRESET_NAMES, PRESETS, "Custom") == ["Custom"]
