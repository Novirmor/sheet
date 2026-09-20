# 06 — Navigation and refactoring

Status: implemented locally. Priority: medium. Depends on: [05](05-editor-intelligence.md)
for semantic operations; basic search and outline can ship independently.

## Goal

Navigate a growing script library and change Python symbols safely without building an
entire project-management framework.

## Requirements

- Search all stored scripts, with source names, line previews, case/whole-word options,
  cancellation, and bounded results. Search linked external files only within explicit scope.
- Add a function/class outline from syntax analysis, code folding, and back/forward navigation.
- Preserve current find and go-to-line shortcuts; make new commands available through menus.
- Add go-to-definition and find references when supported by the optional analysis backend.
- Distinguish script-library renaming from Python symbol renaming in labels and help.
- Preview semantic rename edits grouped by source before applying them.
- Validate source versions before applying a rename. If any source changed, reject the stale
  edit set and recompute instead of partially applying it.
- Apply accepted edits as one logical operation with undo across affected script buffers.
- Never silently write external files. Keep changed linked sources dirty until explicitly saved.
- Warn before leaving unsynchronized changes and preserve cursor position when switching scripts.

## Non-goals

Regex-based symbol renaming presented as semantic refactoring, automatic extract-function,
repository-wide crawling, and built-in Git management.

## Acceptance and verification

- Search finds matches across named scripts and opens the correct source and line.
- Outline and folding handle nested functions/classes and incomplete source without crashing.
- Definition/reference results respect active source versions and configured search scope.
- Rename does not change unrelated strings, comments, or same-spelled symbols.
- Cancelled or stale rename leaves every source unchanged; accepted rename can be undone.
- Tests include stored scripts, unsaved edits, linked files, and unavailable semantic tooling.

Starting points: `script_documents.py`, `script_library.py`, `script_source.py`, `code_editor.py`.
