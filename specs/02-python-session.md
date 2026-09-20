# 02 — Persistent console and execution session

Status: implemented locally. Priority: high. Depends on: [01](01-python-api.md).

## Goal

Run scripts, selections, and console commands in a shared namespace without blocking Qt.

## Requirements

- Use one child process per active document session; never execute user code on the UI thread.
- Expose explicit states: stopped, starting, idle, running, interrupting, and failed.
- Support Run Script, Run Selection, multiline console input, command history, Restart Session,
  and Interrupt. Keep a separate fresh-run option for current reproducible one-shot behavior.
- Preserve variables between successful commands. Rebind `sheet` to a fresh workbook snapshot
  at the start of each command; retain `pd` and `px` convenience aliases.
- Serialize execution: reject or visibly queue a second request; never run two commands at once.
- Carry source identity, source text version, run ID, session ID, and snapshot revision in messages.
- Validate messages and bound payload sizes. Specify the protocol before choosing its transport.
- Detect child exit even when no final result arrives. Restore controls and report the failure.
- Attempt interruption with a bounded grace period; if termination is required, explain that
  session variables were lost. Provide an optional execution timeout.
- Close, document replacement, and environment changes must stop the old process and discard
  its pending replies. Shutdown must not wait indefinitely on UI-thread callbacks.
- Keep failed-command cell writes uncommitted. State clearly that Python variables and external
  side effects may already have changed when an exception occurs.

## Persistence and safety

Persist script source, not the live namespace or arbitrary Python objects. Console history is
session-only initially and has a clear action. No code runs automatically when opening a file.
Process isolation is not a sandbox; show this distinction in execution help.

## Non-goals

Jupyter compatibility, remote kernels, concurrent commands, and asynchronous `input()` prompts.
Unsupported interactive input must fail clearly rather than hanging a run.

## Acceptance and verification

- A console assignment is available to the next command and to a script in the same session.
- Restart clears variables; fresh-run execution does not alter the persistent namespace.
- A long-running command leaves the UI responsive and can be interrupted.
- Exceptions, abrupt process exit, timeout, document replacement, and app close recover cleanly.
- No late result can change a closed, replaced, or edited workbook.
- Process lifecycle tests run on Linux and Windows, including a packaged-app smoke test.

Starting points: `scripting.py`, `script_execution.py`, `script_dialog.py`.
