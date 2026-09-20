# 03 — Results and debugging tools

Status: implemented locally. Priority: high. Depends on: [02](02-python-session.md).

## Goal

Make execution output useful and failures easy to locate, before introducing a full debugger.

## First release

- Stream stdout and stderr as separate, ordered channels with run and sequence identifiers.
- Coalesce high-volume output to keep Qt responsive; cap retained text and show truncation.
- Present text, errors, tabular results, and Plotly results in distinct views.
- Add an explicit `display(value)` execution helper for supported rich results. Ordinary
  `print()` keeps its normal behavior. Unsupported display types get a bounded safe summary.
- Render tables through a bounded model, not thousands of individual Qt widgets.
- Preserve browser-based Plotly viewing as the initial fallback; do not assume QtWebEngine
  is installed. Evaluate any embedded renderer separately, including packaging costs.
- Return structured exception frames with filename, script identity, line, and source version.
- Clicking a frame opens the matching source. Never jump to the same line in an unrelated file.
- Show execution duration, status, and a bounded session-only run history.
- Rerun uses the captured source, with a warning if the editor has changed, and a fresh sheet
  snapshot. Make the distinction from running the current editor buffer visible.
- Clear results independently of session variables; clear old-document results on replacement.

## Later milestone

Breakpoints, stepping, call stacks, and watches require a separate debugger integration
decision. Do not block the first release on them or add a debugger dependency speculatively.

## Acceptance and verification

- Output arrives before completion, in channel order, without freezing under heavy output.
- Runtime and syntax errors navigate correctly for stored scripts and external files.
- Old-source tracebacks are visibly marked stale rather than applied to the wrong buffer.
- Tables and Plotly results have explicit size limits and working fallback behavior.
- History eviction and clearing release retained results; rerun behavior is covered by tests.

Starting points: `script_execution.py`, `script_dialog.py`, `scripting.py`.
