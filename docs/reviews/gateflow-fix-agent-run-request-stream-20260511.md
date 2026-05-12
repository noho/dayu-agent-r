# Gateflow Fix Artifact: AgentRunRequest.stream

## Work Gate

- Gate: fix
- Work-unit: Engine contract/README refactor review fix
- Assigned finding: F1
- Role boundary: implementation/fix worker only; did not start `$gateflow` / `/gateflow`, did not redo plan/review, did not enter commit/PR/closeout.

## Source Review Reports

- `docs/reviews/code-review-20260511-2007.md`
- `docs/reviews/code-review-20260511-2013.md`
- Related but out of current fix scope: `docs/reviews/code-review-20260511-2012.md` for accepted F2 (`tool_awaiting` README test coverage), handled by another worker.

## Controller Decisions

- F1 accepted: `AgentRunRequest.stream` is a public contract field, but `_AsyncAgent` does not consume it; `RunnerCallOptions.stream` is already the Runner/provider stream control source. Fix must remove the double source of truth.
- R1 rejected: removal of `event_id` / `sequence` is an explicit architecture decision; no Host ordering/idempotency suggestion was implemented here.
- F2 accepted but out of scope for this worker: no README or README test changes were made for `tool_awaiting`.

## Fix Status

- F1: fixed.
- Removed `stream` from `AgentRunRequest` dataclass and docstring.
- Kept `RunnerCallOptions.stream` unchanged as the only provider stream control.
- Removed `stream=` from all directly failing `AgentRunRequest(...)` construction sites found in Engine tests and the smoke utility used by those tests.
- Synchronized `docs/engine/design.md` AgentRunRequest field table and related `AsyncAgent.run_messages` request-field wording to remove Engine request `stream`.
- Did not add compatibility alias, deprecated default, wrapper, or new stream behavior.

## Changed Files

- `dayu/engine/contracts/agent_run.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `utils/smoke_async_agent_providers.py`
- `docs/engine/design.md`

## Validation

- `source .venv/bin/activate && pytest tests/engine -q`
  - Result: passed, `300 passed in 1.10s`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed, no output.

## New Risks Or Open Questions

- No new risk introduced by the F1 fix.
- `utils/smoke_async_agent_providers.py` was minimally touched because it directly constructed `AgentRunRequest(stream=...)` and the required pyright command includes `utils/`.
- Workspace still contains unrelated dirty changes from the broader Engine contract/README refactor and user-owned `AGENTS.md` / `CLAUDE.md` edits; this fix did not revert or intentionally modify those files.

## Residual Risks And Uncovered Areas

- F2 remains intentionally uncovered by this artifact and is assigned to the separate README worker per controller handoff.
- External callers outside this repository that still construct `AgentRunRequest(stream=...)` will need to update to `RunnerCallOptions.stream`; no compatibility path was added by design.

## Artifact Path

- `docs/reviews/gateflow-fix-agent-run-request-stream-20260511.md`
