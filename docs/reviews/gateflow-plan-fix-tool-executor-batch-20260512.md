# ToolExecutor Batch Handshake Plan Fix

- **work gate name**: fix
- **work-unit name**: ToolExecutor batch handshake
- **source review artifact**: `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512.md`
- **plan artifact fixed**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **controller-accepted finding ids**: 1, 2, 3, 4
- **artifact path**: `docs/reviews/gateflow-plan-fix-tool-executor-batch-20260512.md`

## Fix Summary

### Finding 1

- **status**: fixed-pending-re-review
- **fix**: The plan now defines `AssistantToolCallBatchSnapshot` with `iteration_id`, `assistant_content`, `assistant_reasoning_content`, and full `tool_calls: tuple[ToolCallRequest, ...]`. `AcceptedToolExecutionRecord` and `AwaitingToolExecutionRecord` now carry `batch_snapshot` and full `call: ToolCallRequest`, so mixed-awaiting suspended terminal records preserve arguments, provider state and assistant roundtrip context.
- **validation expected by plan**: Mixed-awaiting `run_agent_and_wait` tests must reconstruct assistant tool-call message facts from terminal records, including assistant content, reasoning content, arguments and provider state.

### Finding 2

- **status**: fixed-pending-re-review
- **fix**: Implementation slices were restructured into pyright-green checkpoints. The old contract-only and event-only slices were replaced with a single vertical contract + helper + Engine agent migration slice, followed by edge-case hardening and documentation sync.
- **validation expected by plan**: Each slice includes `source .venv/bin/activate && pyright` with no expected intermediate failure state.

### Finding 3

- **status**: fixed-pending-re-review
- **fix**: The plan now specifies strict bijection validation for batch outcome records: `len(records) == len(calls)`, every input id appears exactly once, no unknown id, and duplicate returned id is fatal even if set equality would pass.
- **validation expected by plan**: Tests must cover missing id, unknown id, duplicate returned id and non-input order.

### Finding 4

- **status**: fixed-pending-re-review
- **fix**: The plan now has an explicit public contract break section covering `ToolResultAcceptedData.record`, `ToolAwaitingData.record`, `RunSuspendedData.accepted_records/awaiting_records`, `EngineRunOutcomeSuspended.accepted_records/awaiting_records`, and removal of old single request/context exports.
- **validation expected by plan**: Tests, docs and completion report must explicitly cover these event/outcome breaks.

## Changed Files

- `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512.md`
- `docs/reviews/gateflow-plan-fix-tool-executor-batch-20260512.md`

## Validation

No production code or tests were modified. This fix pass is documentation-only and should proceed to plan re-review.

## New Risks Or Open Questions

- No new blocking open questions introduced.
- Residual risk is limited to re-review confirming that the revised plan is handoff-ready and code-generation-ready.
