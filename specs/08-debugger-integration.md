# 08 — Debugger integration proposal

Status: proposal, intentionally unimplemented. Depends on: [02](02-python-session.md),
[03](03-results-and-debugging.md), [04](04-variable-explorer.md).
Integrates with: [07](07-python-environments.md).

## Goal

Add breakpoints, stepping, and watches to the embedded Python session without new
dependencies, reusing the existing process-isolated session protocol, the variable
explorer's inspection machinery, and the shared worker loop so external interpreters
gain the same debugger for free.

## Proposed design

- Extend the session protocol with a versioned `debug` message family instead of a new
  transport: `debug_start` (with breakpoint list), `debug_step` (`next`, `in`, `out`,
  `continue`, `pause`), and `debug_stop`. Unknown kinds stay ignorable so old workers
  and new parents interoperate during upgrades.
- Drive debugging from the worker's existing `sys.settrace` hook, which already powers
  interrupts. A debug run replaces the plain execute loop: the trace function stops on
  matching breakpoints and emits a `debug_stop` message with the frame's file, line,
  function name, and a bounded stack list.
- Watches reuse inspection requests: a paused frame's `f_locals` and `f_globals` feed
  the same bounded, non-mutating snapshot adapters the variable explorer uses. A new
  `evaluate` inspection kind evaluates one bounded expression in the paused frame and
  returns a `VariablePage`-style preview; repr/evaluate errors become text, never
  exceptions that kill the session.
- Breakpoints are line-based, stored per source identity and validated against the
  source version at start; stale mappings are rejected with a visible message, matching
  the stale-result rules. Conditional breakpoints evaluate in the paused frame with the
  same bounds as watches; condition errors disable the breakpoint and report once.
- The session state machine gains a paused sub-state within `RUNNING`; while paused,
  the UI stays responsive, the editor is read-only, and no other command may start.
  Stepping executes user code in the same namespace; cell writes still commit only at
  command completion, so pausing never applies partial sheet changes.
- Interrupt during a pause or between steps reuses the existing interrupt escalation;
  restart clears debugger state with the rest of the session.
- UI: breakpoint markers in the editor gutter (click to toggle), a debug control row
  (Start debugging, Continue, Step over/in/out, Stop), and a watches panel that reuses
  the variable explorer table with per-stop refresh and stale-state indicators.

## Decisions still required before implementation

- Whether `input()`-style interactive prompts can be emulated while paused, or stay
  unsupported as today.
- The breakpoint cap, watch cap, and evaluation timeout values, following the existing
  `MAX_*` limit conventions.
- Whether the call-stack panel is a plain list in v1 or supports frame switching for
  watches (frame switching adds protocol surface; a list is safer first).

## Non-goals

Remote debugging, attaching to arbitrary external processes, multiprocess debugging,
time-travel or rewind debugging, mutable watches or state editing, and debugging
inside GUI event loops.

## Acceptance and verification

- A breakpoint stops a running script while the UI stays responsive; stepping moves
  through lines and frames; watches update at each stop without executing sheet writes.
- Stale source versions reject breakpoint mapping; failed conditions disable safely;
  interrupt, timeout, restart, and unexpected exit recover cleanly from paused states.
- External interpreters support the same flow through the shared worker loop.
- Focused protocol tests plus Qt tests with deterministic fixtures; `task check` and
  packaging smoke tests stay green with no new dependencies.

## Suggested tasks

- [ ] DBG-01 Extend the session protocol with the `debug` message family and tests.
- [ ] DBG-02 Implement the settrace debug run loop with breakpoints and stepping.
- [ ] DBG-03 Add frame inspection, bounded `evaluate` watches, and condition handling.
- [ ] DBG-04 Add gutter breakpoints, debug controls, and the watches panel.
- [ ] DBG-05 Test pause/resume/interrupt/restart, stale versions, and external parity.

Starting points: `scripting.py` (`_run_session_loop`, `_execute_session_source`),
`external_worker.py`, `script_dialog.py`, `code_editor.py`, `script_inspector.py`.
