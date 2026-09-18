from sheet.window_find import matches, replace_value


def test_find_helpers_match_and_replace_without_case_sensitivity() -> None:
    assert matches("Coffee shop", "coffee", match_case=False)
    assert replace_value("Coffee shop", "coffee", "tea", match_case=False) == "tea shop"
