# Python workspace implementation tasks

Status: implemented and validated on Windows and Linux, including packaged external
environment launches. Remaining work is the unimplemented debugger proposal
([08](08-debugger-integration.md)).
Task IDs are stable for future issues and commits.

## Foundation — reliability before new UI

- [x] F-01 Add regression tests for child exit without a result, stop, runtime failure, and late replies.
- [x] F-02 Define document/session/run/source identifiers and a versioned, bounded message schema.
- [x] F-03 Add workbook snapshot conflict detection, including edits, undo/redo, and replacement.
- [x] F-04 Establish bounded shutdown behavior and Linux process test fixtures.

## Phase 1 — [Python API](01-python-api.md)

- [x] API-01 Capture existing signatures and examples in compatibility tests.
- [x] API-02 Specify conversion and validation rules; implement table-driven tests.
- [x] API-03 Fix DataFrame index/header combinations and cover empty and missing-value cases.
- [x] API-04 Validate batched writes atomically and preserve single-action undo/redo.
- [x] API-05 Create shared public API metadata and update workspace help.
- [x] API-06 Verify all spec acceptance criteria and run `task check`.

## Phase 2 — [Session and console](02-python-session.md)

- [x] SES-01 Implement the execution state machine and protocol using the foundation tests.
- [x] SES-02 Add persistent worker lifecycle, serialized commands, and fresh sheet snapshots.
- [x] SES-03 Add multiline console, bounded history, Run Selection, and fresh-run mode.
- [x] SES-04 Add interrupt escalation, optional timeout, restart, and unexpected-exit recovery.
- [x] SES-05 Handle document close/replacement and stale result rejection end to end.
- [x] SES-06 Verify UI responsiveness and native Linux packaging.

## Phase 3 — [Results and debugging](03-results-and-debugging.md)

- [x] RES-01 Stream ordered stdout/stderr with batching, caps, and truncation notices.
- [x] RES-02 Return structured exceptions and implement source-aware traceback navigation.
- [x] RES-03 Add `display()` dispatch, bounded table results, and Plotly browser fallback.
- [x] RES-04 Add duration/status, bounded run history, clear controls, and explicit rerun semantics.
- [x] RES-05 Test heavy output, stale frames, interrupted runs, and result cleanup.
- [x] RES-06 Keep Plotly's browser fallback; defer embedded chart rendering without adding a dependency.

## Phase 4 — [Variable explorer](04-variable-explorer.md)

- [x] VAR-01 Define safe metadata adapters and session-scoped object handles.
- [x] VAR-02 Add the variable panel with idle refresh and stale-state indicators.
- [x] VAR-03 Implement bounded DataFrame/Series pages and non-mutating view sorting.
- [x] VAR-04 Add selection copy and confirmed table-to-sheet export through API transactions.
- [x] VAR-05 Test large objects, unsafe representation methods, stale handles, and export undo.

## Phase 5 — [Editor intelligence](05-editor-intelligence.md)

- [x] IDE-01 Improve built-in completion and signature help using public API metadata.
- [x] IDE-02 Add debounced, versioned syntax diagnostics without executing source.
- [x] IDE-03 Keep optional semantic tooling dependency-free; show its unavailable state explicitly.
- [x] IDE-04 Use virtual documents and provide the built-in completion/signature fallback.
- [x] IDE-05 Align built-in execution with the app interpreter and handle unavailable external tooling.
- [x] IDE-06 Test insertion behavior, stale replies, missing imports, and no-backend fallback.

## Phase 6 — [Navigation and refactoring](06-navigation-and-refactoring.md)

- [x] NAV-01 Add bounded cross-script search and explicit linked-file search scope.
- [x] NAV-02 Add symbol outline, folding, and navigation history.
- [x] NAV-03 Provide conservative AST definition/reference lookup and explicit optional-backend fallback.
- [x] NAV-04 Implement rename preview, version validation, and grouped buffer undo.
- [x] NAV-05 Test stale edits, unrelated symbols, cancelled rename, and external-file save behavior.

## Phase 7 — [Environments](07-python-environments.md)

- [x] ENV-01 Define interpreter compatibility and probe protocol; keep external worker launch unavailable until a dedicated bootstrap is packaged.
- [x] ENV-02 Implement interpreter discovery/selection and local path settings.
- [x] ENV-03 Invalidate active sessions on environment changes and explicitly block unavailable external execution.
- [x] ENV-04 Add package inspection and explicit dependency install/update previews.
- [x] ENV-05 Add optional `uv` environment creation and portable declaration workflow.
- [x] ENV-06 Test incompatible interpreters, spaced paths, failed installs, and offline fallback.
- [x] ENV-07 Smoke-test external environments from packaged Windows and Linux applications.
  Verified on Linux locally and on Windows CI (run 35528028534): `Sheet --smoke-test
  [--smoke-test-interpreter PATH]` covers the worker spawn bootstrap, persistent session,
  probe protocol, external launch and execution, and explicit rejected states; CI also
  launches a uv-created external environment from the packaged build.
- [x] ENV-08 Package the worker bootstrap and implement external session launch over a
  validated stdio/pipe protocol shared with the built-in session loop.
- [x] ENV-09 Route session, console, selection, fresh-run, and restart commands through the
  selected external interpreter with the same stale-result and interrupt rules.

## Release gates — repeat for each delivered phase

- [x] REL-01 Review the phase's acceptance criteria and mark only verified tasks complete.
- [x] REL-02 Run `task check` and resolve lint, formatting, typing, and test failures.
- [x] REL-03 Run `task package` and verify the native application's version and affected workflows.
- [x] REL-04 Validate Windows CI and process-related smoke tests where relevant.
  Windows CI runs the full check suite, the packaged `--smoke-test`, and a packaged
  external-environment launch (green run 35528028534).
- [x] REL-05 Review limits, error messages, document compatibility, and single-action undo behavior.
  Findings fixed: frozen builds no longer probe their own executable as an interpreter;
  console history is bounded; the model's undo stack is no longer Qt-parented (a
  teardown-order crash destroying Python-subclassed undo commands).

## Deferred, not prerequisites

- [x] FUT-01 Write a separate debugger integration proposal for breakpoints, stepping, and watches.
  See [08-debugger-integration.md](08-debugger-integration.md); implementation tasks remain
  unchecked there until separately planned.

Excel compatibility, remote kernels, and plugin frameworks are not part of this task list.
