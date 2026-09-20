# Python workspace development specs

Status: implemented locally; the documents remain the behavioral contract and record deferred
platform release gates.

## Goal and scope

Develop Sheet into a Python-powered data workspace: a spreadsheet, an embedded editor,
an interactive execution session, and practical inspection tools.

- `.sheet` remains the native document format; CSV remains a data interchange format.
- Excel `.xlsx` and `.xls` compatibility is explicitly out of scope.
- Preserve existing workbook files, script sources, public Python methods, and undo behavior.
- Prefer small functions, data classes, explicit Qt signals, and existing dependencies.
- Do not introduce a plugin framework or attempt to reproduce a full general-purpose IDE.

## Current baseline

The application has a named-script library, a Qt editor, basic fixed-word completion,
syntax checking on Run, and a fresh spawned process for each script. Scripts receive a
workbook snapshot plus `sheet`, `pd`, and `px`. Successful cell changes become one undoable
action. Output is returned after execution; there is no persistent session or variable explorer.

Process isolation protects UI responsiveness, not security. Python scripts execute with the
user's permissions. File, network, and other external side effects cannot be undone by Sheet.

## Specifications and delivery order

| Phase | Specification | Prerequisites |
| --- | --- | --- |
| 1 | [Spreadsheet Python API](01-python-api.md) | Existing scripting API |
| 2 | [Persistent console and execution session](02-python-session.md) | Phase 1 transaction rules |
| 3 | [Results and debugging tools](03-results-and-debugging.md) | Phase 2 execution protocol |
| 4 | [Variable explorer and DataFrame inspector](04-variable-explorer.md) | Phases 1–3 |
| 5 | [Completion and diagnostics](05-editor-intelligence.md) | Phase 1 API metadata |
| 6 | [Navigation and refactoring](06-navigation-and-refactoring.md) | Phase 5 for semantic tools |
| 7 | [Python environments and dependencies](07-python-environments.md) | Phase 2 launch protocol |
| — | [Debugger integration proposal](08-debugger-integration.md) | Phases 2–4 (unimplemented) |

Phase 5 basic editor work can proceed independently once the API contract is stable.
External interpreters are delivered last, but the session protocol must not assume shared
Python objects or a particular launch mechanism.

## Shared requirements

- Qt widgets and the live workbook are accessed only on the UI thread.
- Python execution, expensive inspection, and language tooling must not block the UI.
- Associate requests and replies with document, session, run, and source-version identifiers.
- Reject stale results rather than silently applying them to another document or source version.
- Bound output, previews, message sizes, and retained history; make truncation visible.
- Never execute scripts, install packages, or enable external tools merely by opening a document.
- Keep optional tools optional, with clear unavailable states and basic offline fallbacks.
- Avoid pickled user objects across process boundaries; use validated structured messages.
- Add no dependencies until their need, packaging impact, and supported Python versions are checked.

## Definition of done

Each phase needs focused unit tests, relevant Qt/process integration tests, and passing
`task check` (Ruff formatting/lint, ty, pytest). Execution-related phases also need native
packaging smoke tests and Windows CI validation. Timing tests should use bounded waits and
deterministic fixtures instead of arbitrary sleeps.

Track implementation in [TASKS.md](TASKS.md). Keep tasks unchecked until implemented and verified.
