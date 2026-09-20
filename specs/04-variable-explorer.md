# 04 — Variable explorer and DataFrame inspector

Status: implemented locally. Priority: medium. Depends on: [01](01-python-api.md),
[02](02-python-session.md), and [03](03-results-and-debugging.md).

## Goal

Inspect session data and move useful results to the spreadsheet without writing export code.

## Requirements

- Refresh a variable list after execution, with name, type, shape/length where safely known,
  and a short preview. Hide internal helper names by default.
- Inspect only while the session is idle; show the last snapshot as stale while running.
- Keep objects in the worker. Request metadata and bounded pages using session-scoped handles.
- Do not call arbitrary object properties, `__repr__`, or user-defined iteration merely to
  populate the list. Use explicit adapters for supported built-in and Pandas types.
- Paginate large DataFrames and Series; show column labels, index, dtypes, and missing values.
- Allow sorting in the inspector without mutating the user's original DataFrame.
- Support copying a selection and writing a table to an explicit destination cell, with
  header/index options, overwrite confirmation, conversion preview, and one undo action.
- Invalidate handles on restart or variable replacement and reject stale requests cleanly.
- Bound inspection time, rows, columns, and payload size; report when a preview is partial.

## Non-goals

Editing arbitrary Python objects, recursive introspection of every object type, or persisting
the live namespace in a workbook. The first version is an inspector, not an object debugger.

## Acceptance and verification

- Small scalars, lists, DataFrames, and Series display predictable metadata and previews.
- A large DataFrame fetches bounded pages without copying its full contents to the UI.
- Sorting the view does not change the original object.
- Objects with side-effecting or failing representation methods are not evaluated implicitly.
- Export uses the API conversion rules, handles conflicts, and undoes in a single step.
- Restart and rapid variable replacement cannot display data from obsolete handles.

Starting points: `script_dialog.py`, `scripting.py`, `model.py`; add a focused inspector widget
only when implementing this phase.
