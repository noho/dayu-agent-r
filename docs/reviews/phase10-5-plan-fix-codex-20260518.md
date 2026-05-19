# Phase 10.5 Plan Fix Report

## Gate

当前 gate：P10.5 plan fix。

本 artifact 只记录 plan fix 结果：不实现代码、不修改 `dayu/` 源码、不修改 tests、不修改 README、不修改 `docs/host/implementation-control.md`、不提交、不 push、不进入 implementation gate。

## Inputs

Source review artifacts:

- `docs/reviews/phase10-5-plan-review-mimo-20260518.md`
- `docs/reviews/phase10-5-plan-review-ds-20260518.md`

Controller adjudication artifact:

- `docs/reviews/phase10-5-plan-review-controller-adjudication-20260518.md`

Fixed plan artifact:

- `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`

Design / control truth referenced by the plan fix request:

- `docs/host/design.md`
- `docs/host/implementation-control.md`

## Accepted Finding IDs

Controller accepted for plan fix:

- A1. Slice dependency and Slice 2 request-shape boundary
- A2. Public handle session/read wrappers ownership
- A3. HostEventStream disposition
- A4. Compactor baseline None semantics and field mapping
- A5. HostToolingOptions shape note

## Fix Status

| Finding | Status | Plan location | Fix summary |
| --- | --- | --- | --- |
| A1 | Fixed | `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:281` | Added explicit sequencing `Slice 1 -> Slice 2 -> {Slice 3, Slice 4} -> Slice 5 -> Slice 6`; clarified Slice 2 may validate queue wakeup with the current request shape, Slice 3 migrates `SubmitFollowupRequest`, and Slice 2 must not pre-implement steer / retry / replay. |
| A2 | Fixed | `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:351` | Assigned public async handle delegation ownership to Slice 2 for `ensure_session`、`create_session`、`get_session`、`get_run`, and for later public command wrappers while leaving command semantics to their owner slices. |
| A3 | Fixed | `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:444` | Added Slice 4 instruction to remove `HostEventStream` from `dayu.host` public exports if present; if retained, it may only be an internal `AsyncIterator[HostEvent]` type alias / Protocol, not a Service-facing stream handle. |
| A4 | Fixed | `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:238`, `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:274`, `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:356` | Added fail-closed semantics for `compactor_baseline=None`; required Slice 2 mapping from `OpenHostOptions.compactor_baseline` to internal compactor fields; updated S4 compact owner to include Slice 2 wiring coverage. |
| A5 | Fixed | `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:146`, `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:260`, `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md:308` | Clarified that `HostToolingOptions` reuses the existing typed shape; if ToolRuntime policy typed fields are missing, Slice 1 must add typed fields and must not use extra payload, service locator, profile lookup, or unstructured dicts. |

## Changed Files

- Modified: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Added: `docs/reviews/phase10-5-plan-fix-codex-20260518.md`

No source files, tests, README files, `docs/host/implementation-control.md`, existing review artifacts, commits, or pushes were changed by this fix report task.

## Validation

This was a documentation-only plan fix gate. No implementation code changed.

Validation performed:

- Targeted text checks with `rg` for A1-A5 terms and expected plan anchors.
- Targeted line checks with `nl -ba ... | sed -n ...` around the inserted plan sections.
- `git status --short` checks to confirm the task scope and avoid accidental source / test / README changes.

Validation not run:

- `pytest` was not run because this gate only modifies plan / review documentation.
- `pyright` was not run because no Python source or tests were modified.

## New Risks / Open Questions

No new Blocking Questions For Controller were introduced.

Residual implementation risks remain the same as the plan's existing residual risks:

- Real runner matrix depends on provider secrets / network availability.
- Real compactor smoke depends on a real compactor adapter / provider availability.
- Phase 11+ items remain out of scope: recovery, stuck cancel watchdog, tools discovery, outbox drain, remote execution, purge / retention cleanup.

## Artifact Path

- `docs/reviews/phase10-5-plan-fix-codex-20260518.md`
