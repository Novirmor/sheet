from sheet.script_api import api_member, api_member_names
from sheet.script_intelligence import (
    apply_rename_plan,
    folding_ranges,
    outline,
    rename_plan,
    search_sources,
    syntax_diagnostics,
)


def test_api_metadata_drives_members_and_signatures() -> None:
    assert {"dataframe", "write_dataframe"} <= set(api_member_names())
    member = api_member("write_dataframe")
    assert member is not None
    assert member.signature.startswith("sheet.write_dataframe")


def test_syntax_diagnostics_do_not_execute_source() -> None:
    diagnostics = syntax_diagnostics("raise RuntimeError('should not run')\ndef broken(:\n    pass")

    assert diagnostics[0].line == 2
    assert "invalid syntax" in diagnostics[0].message


def test_outline_and_folding_are_safe_for_incomplete_source() -> None:
    source = "class Report:\n    def build(self):\n        return 1\n"

    assert [(item.kind, item.name, item.depth) for item in outline(source)] == [
        ("class", "Report", 0),
        ("function", "build", 1),
    ]
    assert folding_ranges(source) == ((1, 3), (2, 3))
    assert outline("def incomplete(") == ()


def test_library_search_honors_scope_options_and_limit() -> None:
    matches = search_sources(
        {"main": "value = 1\nValue = 2", "report": "value_total = 3\nvalue = 4"},
        "value",
        whole_word=True,
        limit=2,
    )

    assert [(match.source_name, match.line) for match in matches] == [("main", 1), ("main", 2)]


def test_ast_rename_does_not_touch_other_scopes_comments_or_strings() -> None:
    source = """def first():
    value = 1
    return value

def second():
    value = 2
    return value

# value
label = "value"
"""
    plan = rename_plan({"main": source}, {"main": 7}, "main", 2, 4, "amount")

    assert plan is not None
    assert plan.source_versions == {"main": 7}
    updated = apply_rename_plan({"main": source}, plan)["main"]
    assert "amount = 1" in updated
    assert "return amount" in updated
    assert "value = 2" in updated
    assert '# value\nlabel = "value"' in updated


def test_rename_rejects_unresolved_and_invalid_symbols() -> None:
    source = "print(missing)"

    assert rename_plan({"main": source}, {"main": 1}, "main", 1, 6, "present") is None
    assert rename_plan({"main": source}, {"main": 1}, "main", 1, 6, "not valid") is None
