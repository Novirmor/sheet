# 07 — Python environments and dependencies

Status: implemented locally. Priority: medium. Depends on: [02](02-python-session.md).
Integrates with: [05](05-editor-intelligence.md).

## Goal

Let users choose a reproducible Python environment without modifying Sheet's own packaged
runtime or hiding environment setup behind document loading.

## Requirements

- Default to the application runtime; optionally select a compatible existing interpreter
  or explicitly create a project-local environment with an available `uv` executable.
- Define the supported interpreter range and worker bootstrap requirements before enabling
  selection. Validate version, required packages, protocol handshake, and launch capability.
- Store machine-specific interpreter paths in local settings, not portable workbook content.
  Keep dependency declarations separate and portable in a user-chosen project directory.
- Start external interpreters through an explicit subprocess command and validated protocol;
  do not assume the existing multiprocessing launcher can switch interpreters.
- Pass command arguments without shell interpolation. Do not execute startup scripts implicitly.
- Show interpreter path/version, package versions, missing requirements, and operation logs.
- Require explicit confirmation of install/update commands and destination environment.
  No automatic package installs on import errors, document open, or interpreter selection.
- Use a reproducible dependency declaration and lock workflow; specify file ownership and
  preview changes before overwriting existing project metadata.
- On environment change, stop the old session, invalidate inspected objects and analysis,
  and explain that variables are lost. Restart only through a visible user action.
- Support offline/unavailable-tool states. Never install into a frozen application's bundle.
- Mark arbitrary external environments as user-controlled, not security sandboxes.

## Non-goals

Conda management, remote execution, secret management, automatic environment activation from
untrusted files, and an unrestricted package marketplace.

## Acceptance and verification

- Default execution continues to work without `uv` or an external interpreter.
- A compatible interpreter completes the handshake and runs sheet/Pandas examples.
- Incompatible or missing interpreters produce actionable errors before launching a session.
- Install actions show exact arguments and target location and never start without confirmation.
- Tests cover paths with spaces, failed installs, offline operation, switching, and shutdown.
- Windows and Linux packaged builds can launch a validated external environment.

Starting points: `scripting.py`, `script_execution.py`, `app.py`, `tools/package.py`.
