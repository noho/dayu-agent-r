# PR Review Fix — Draft PR #172

## Gate

- Work unit: WU-CLI-SMOKE-01
- Gate: PR review fix / re-review evidence
- Agent: AgentCodex
- Date: 2026-07-06
- PR: https://github.com/noho/dayu-agent-r/pull/172
- Branch: `phase/host-issues-control`
- Review inputs: `docs/reviews/pr-172-review-20260706-210832.md`, `docs/reviews/pr-172-review-ds.md`
- Controller adjudication: fix DS-F01 and DS-F02 now; defer DS-F03.

## Scope

Only controller-accepted PR review findings were changed:

- `docs/host/design.md`
- `tests/host/test_host_activity_event_projection.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/pr-172-review-fix-codex.md`

No commit, push, PR state change, merge, or issue mutation was performed.

## First-Principles Judgment

DS-F01 is a real maintainability defect because `REASONING_DELTA` is now intentionally written as a `PREVIEW` EventLog row for live thinking projection, while the Host design mapping table still said it remained a non-durable delta with no EventLog row. The design document is the Host design truth, so leaving it stale would make a future implementation change likely to break thinking display silently.

DS-F02 is not a production behavior bug, because terminal events should never receive thinking payloads in the current projection path. It is still valid defensive hardening: the guard exists in `HostEvent.__post_init__()` and should be locked by a focused test so future projection mistakes fail loudly.

DS-F03 remains deferred by controller decision. The single-turn `CliThinkingRenderer` dedupe set is correct for current renderer lifetime and token-scale thinking streams; bounding policy belongs to future CLI UI/runtime hardening if user requirements change.

## Finding Status

| Finding | Controller decision | Fix status | Evidence |
|---|---|---|---|
| DS-F01 | accepted required current fix | 已修复 | `docs/host/design.md` now states that transient delta is limited to `content_delta` / `tool_call_delta`, and `reasoning_delta` maps to `PREVIEW` for live thinking display only. |
| DS-F02 | accepted current low test hardening | 已修复 | `tests/host/test_host_activity_event_projection.py::test_terminal_host_event_rejects_thinking_payload` constructs a terminal `HostEvent` with `HostThinkingView` and asserts `ValueError`. |
| DS-F03 | deferred / do not fix now | 未修复 | Residual remains assigned to future CLI UI/runtime hardening by controller adjudication. |

## README / Docs Decision

- `docs/host/design.md` was updated because DS-F01 directly concerned the design truth.
- `docs/host/issues-implementation-control.md` was updated to record PR review fix status and next entry point.
- `dayu/host/README.md` already matched the implementation: it states reasoning delta writes a `PREVIEW` row only for live thinking display.
- `tests/README.md` was checked. No update was needed because this change adds one focused test inside an existing Host test layer and does not introduce a new test layer, command family, or maintenance convention.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_host_activity_event_projection.py -q`
  - Result: `17 passed in 0.47s`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/service/test_entrypoint_runtime.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_thinking_renderer.py -q`
  - Result: `176 passed, 3 warnings in 3.58s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass

## Residual Risks

| Risk | Classification | Owner / Destination | Status |
|---|---|---|---|
| `REASONING_DELTA` PREVIEW row retention / cleanup policy | assigned to later work unit | WU-RET-03 / GitHub Issue #78 under #43 retention lane | deferred-with-owner |
| `CliThinkingRenderer._seen_dedupe_keys` is unbounded within one renderer lifetime | assigned to later work unit | Future CLI UI/runtime hardening if user requests expandable or long-running thinking display | deferred-with-owner |

## Completion Status

PR review fix gate implementation is complete for controller-accepted findings. Next entry point is controller re-review, then accepted PR review commit / push if accepted.
