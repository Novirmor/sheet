# 05 — Completion and diagnostics

Status: implemented locally. Priority: medium. Depends on: [01](01-python-api.md) for API metadata.

## Goal

Offer useful Python assistance while preserving a lightweight editor that works without
external language tooling.

## Baseline

`CodeEditor` already provides syntax highlighting, line numbers, and fixed-word completion.
Syntax validation currently runs when the user presses Run. Ruff and ty are development
dependencies, not existing editor integrations.

## Requirements

- Improve the built-in fallback with Python keywords, full `sheet` API completion, signatures,
  and help text. Preserve existing indentation, shortcuts, and source synchronization.
- Add debounced syntax diagnostics that do not execute the buffer; show location and message.
- Research an optional language backend for semantic completion, hover, signatures, and
  diagnostics. Record compatibility, startup cost, packaging impact, and a dependency decision
  before implementing it. Do not assume a language server or analysis library is installed.
- Resolve imports against the active execution interpreter. Until environment selection is
  available, use the application's runtime rather than a guessed system Python.
- Represent stored scripts with stable virtual document identities and versioned source.
- Ignore late replies for old versions. Cancel obsolete requests and bound diagnostics volume.
- Keep all analysis out of the UI thread; handle unavailable or crashed tooling gracefully.
- Explain missing optional tooling without downloading or installing it automatically.
- Generate API metadata/stubs from the same source used by help to avoid signature drift.

## Non-goals

AI code generation, automatic code execution for completion, and mandatory network services.

## Acceptance and verification

- `sheet.` offers every supported public method, including DataFrame helpers.
- Syntax errors update after edits and clear when corrected, without requiring Run.
- Completion insertion respects cursor position and does not corrupt adjacent text.
- Stale diagnostics and completions never overwrite newer editor state.
- Editing and running scripts work normally with the optional backend absent or stopped.
- Tests cover stored scripts, external files, missing imports, and backend restart.

Starting points: `code_editor.py`, `script_source.py`, `script_dialog.py`.
