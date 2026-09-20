# 01 — Spreadsheet Python API

Status: implemented locally. Priority: high. Dependencies: none.

## Goal

Provide a predictable, discoverable API for moving data between Python and the sheet,
without breaking existing scripts.

## Baseline

`src/sheet/scripting.py` exposes `SheetAPI`: `rows`, `columns`, `get`, `raw`, `set`,
`clear`, `range`, `write`, `dataframe`, and `write_dataframe`. `range()` currently
returns nested lists; `dataframe()` uses the keyword `headers=True`.

## Requirements

- Preserve those names, return types, and keyword arguments. Do not replace `range()`
  with a range object as part of this work.
- Describe every public method in one metadata source usable by API help and completion.
- Define conversion rules for empty cells, `None`, booleans, numbers, strings, formulas,
  Pandas missing values, and unsupported objects. Do not silently stringify unsupported data.
- Define DataFrame header/index behavior, including duplicate headers and empty frames.
- Correct the index alignment when writing a DataFrame without a header but with its index.
- Validate an entire batch before applying it; failed validation leaves the sheet unchanged.
- Keep successful script changes, including dimension growth, in one undo action.
- Identify the input snapshot and reject a result if the workbook was edited or replaced
  while execution was in progress. Explain how to rerun against the latest data.

Compatible usage:

```python
df = sheet.dataframe("A1:D100", headers=True)
summary = df.groupby("category", as_index=False)["amount"].sum()
sheet.write_dataframe("F1", summary, include_header=True, include_index=False)
```

## Non-goals

Multiple sheets, Excel semantics, a live SQLite handle, and unrestricted UI manipulation.
Any future range-object API must be additive and separately specified.

## Acceptance and verification

- Existing API tests and example scripts continue to work unchanged.
- Table-driven tests cover all header/index combinations, missing values, and empty frames.
- Invalid writes produce actionable errors with no partial cell updates.
- Failed runs and stale results do not mutate the workbook; successful runs undo and redo once.
- API help accurately reflects public signatures and conversion rules.

Starting points: `scripting.py`, `model.py`, `script_execution.py`, `tests/test_scripting.py`.
