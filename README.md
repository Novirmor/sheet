# Sheet

Sheet is a small SQLite-backed desktop spreadsheet built with Python and Qt.

## File-format scope

- `.sheet` is the only document format opened and saved by Sheet.
- CSV is supported only for importing and exporting tabular data.
- CSV import does not replace the current document or preserve formulas, formatting, scripts, or
  other workbook features.
- Excel `.xlsx` and `.xls` documents are intentionally out of scope.

## Development progress

- [x] Native `.sheet` persistence, atomic saves, and crash recovery
- [x] Cell editing, formatting, undo/redo, structural editing, and sorting
- [x] Formula engine and clickable function picker
- [x] Isolated Python workspace with Pandas and Plotly support
- [x] Basic CSV import and export
- [x] CSV preview, destination options, and overwrite confirmation
- [x] CSV export options for raw formulas or calculated display values
- [x] Progress reporting, cancellation, and malformed-row errors

## Engineering plan: keep it simple

New behavior is secondary to making the existing application easy to understand and change. Refactors
must preserve behavior and pass the complete verification suite after every step.

### Rules

- Prefer plain functions and small data classes over frameworks and inheritance.
- Give each module and class one clear responsibility.
- Target at most 300 lines per Python module; review any module above 450 lines.
- Target at most 30 lines per function; review any function above 50 lines.
- Keep Qt UI builders below roughly 75 lines.
- Do not split cohesive files only to satisfy a number.
- Do not add service locators, event buses, controller hierarchies, or one-method classes.
- Keep old public methods as thin wrappers while moving implementation, so changes remain safe.
- Add or improve tests before extracting risky behavior.

Static resources are exceptions: `theme.py` may remain larger because it is primarily one stylesheet.

### Phase 1: Pure helpers

- [x] Move repeated selection rectangle logic from `window.py` to `selection.py`.
- [x] Move CSV-to-cell mapping, conflict counting, and range projection to `csv_transfer.py`.
- [x] Move `GridState` and pure insert/delete/sort transformations from `workbook.py` to
  `grid_state.py`.
- [x] Keep compatibility wrappers in `MainWindow` and `Workbook` until callers are migrated.

### Phase 2: Small reusable widgets

- [x] Move `CodeEditor`, `LineNumberArea`, and `PythonHighlighter` from `script_dialog.py` to
  `code_editor.py`.
- [x] Keep `ScriptWorkspace` focused on coordinating scripts and process results.
- [x] Extract a script-library panel only if `ScriptWorkspace` remains difficult to navigate after
  the editor extraction.

### Phase 3: Reduce `MainWindow`

- [x] Move action, menu, and toolbar construction to small builder functions in
  `window_actions.py`.
- [x] Keep document open/save/close methods together; do not create a controller unless they can be
  separated without passing the entire window around.
- [x] Keep signal wiring explicit and visible.

### Phase 4: Simplify workbook storage

- [x] Move atomic snapshot writing and recovery discovery to `workbook_storage.py`.
- [x] Keep `Workbook` responsible for document state and formula recalculation.
- [x] Preserve `.sheet` compatibility, recovery metadata, atomic replacement, and undo behavior.

### Phase 5: Formula cleanup when needed

- [x] Move formula-reference parsing and transformation to `formula_references.py` if that logic
  grows further.
- [x] Replace the long built-in function branch with a plain function table or small evaluator
  function.
- [x] Do not introduce a plugin architecture for built-in formulas.

### Files that should stay together for now

- `database.py`: one cohesive SQLite repository.
- `scripting.py`: a small API plus one process boundary.
- `csv_io.py`: focused CSV parsing and writing.
- `coordinates.py` and `formatting.py`: already small and cohesive.
- `theme.py`: mostly static QSS, so splitting it would add packaging complexity.

### Definition of done for each refactor

- No user-visible behavior changes unless separately requested.
- Existing import paths and public methods remain available during migration.
- Ruff formatting and linting pass.
- Static type checks pass.
- All tests pass on Linux and in the Windows GitHub Actions build.
- The changed code is smaller or more cohesive without adding unnecessary abstractions.
