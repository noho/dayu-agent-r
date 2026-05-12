# ToolExecutor Batch Handshake Plan Re-review

- **review gate name**: plan re-review
- **reviewed target**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **source review artifact**: `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512.md`
- **plan fix artifact**: `docs/reviews/gateflow-plan-fix-tool-executor-batch-20260512.md`
- **review scope**: only the 4 controller-accepted plan review findings and whether the revised plan is handoff-ready / code-generation-ready
- **reviewer conclusion**: pass
- **artifact path**: `docs/reviews/gateflow-plan-re-review-tool-executor-batch-20260512.md`

## Scope Boundary

本次复核只验证原 plan review 中 4 个已接受 finding 是否被 revised plan 修复。未重新设计方案，未扩展 implementation scope，未修改代码，也未进入 implementation。

## Re-review Results

### Finding 1: suspended terminal records do not carry enough identity to close mixed-awaiting resume semantics

- **status**: fixed
- **evidence**: revised plan now defines `AssistantToolCallBatchSnapshot` with `iteration_id`, `assistant_content`, `assistant_reasoning_content`, and full `tool_calls: tuple[ToolCallRequest, ...]`; it explicitly requires `tool_calls` to preserve `arguments`, `index_in_iteration`, `tool_call_id`, `name`, and `provider_state`.
- **evidence**: `AcceptedToolExecutionRecord` and `AwaitingToolExecutionRecord` now carry both `batch_snapshot` and full `call: ToolCallRequest`.
- **evidence**: terminal `RunSuspendedData` and `EngineRunOutcomeSuspended` now carry `accepted_records` and `awaiting_records`; `run_agent_and_wait` must preserve those records exactly.
- **evidence**: revised tests require reconstructing the assistant tool-call message from `record.batch_snapshot`, including assistant content, reasoning content, arguments, and provider state.
- **assessment**: The originally missing resume-complete identity is now specified as a concrete public contract. Implementation no longer needs to invent the mixed-awaiting resume shape.

### Finding 2: implementation slices knowingly create pyright-red intermediate states

- **status**: fixed
- **evidence**: revised plan states every slice is a pyright-green review checkpoint and forbids delivering a "pyright may fail until later slice" intermediate state.
- **evidence**: revised Slice 1 is now a vertical checkpoint that includes public contracts, `tool_declaration`, Engine event/outcome shapes, `dayu/engine/agent.py`, exports, and touched tests in the same slice.
- **evidence**: Slice 1 validation includes focused pytest plus `pyright`; the stop condition says to return to Controller if pyright cannot pass without reintroducing old compatibility facades.
- **evidence**: Slices 2 and 3 also include `pyright` validation, with no expected red state.
- **assessment**: The sequencing issue is fixed. Slice 1 is large, but that size is justified by the no-compatibility constraint and by the need to keep the repo type-checkable at the checkpoint.

### Finding 3: batch outcome mismatch validation is underspecified for duplicate returned records

- **status**: fixed
- **evidence**: revised error semantics define strict bijection: `len(records) == len(calls)`, every input id appears exactly once, no unknown id, and no duplicate returned id; duplicate returned ids are fatal even when set equality appears to pass.
- **evidence**: Slice 1 implementation steps repeat the same strict validation requirements before processing records.
- **evidence**: Slice 2 and the final validation matrix require tests for missing id, unknown id, duplicate returned id including set-equality-hidden duplicates, and non-input return order.
- **assessment**: The one-input-call-to-one-record invariant is now implementable and testable.

### Finding 4: public event consumer breakage is not fully surfaced in risks and docs/test scope

- **status**: fixed
- **evidence**: revised plan adds an explicit public contract break section covering `ToolResultAcceptedData.record`, `ToolAwaitingData.record`, `RunSuspendedData.accepted_records/awaiting_records`, `EngineRunOutcomeSuspended.accepted_records/awaiting_records`, old single request/context export removal, and the old single-tool executor signature removal.
- **evidence**: revised Slice 2 requires public event/outcome shape assertions for the new record fields and terminal record tuples.
- **evidence**: docs decision requires documenting the event/outcome migration, `AssistantToolCallBatchSnapshot`, and removal of old single request/context exports in Engine/Host docs.
- **evidence**: residual risks and completion report format now explicitly call out downstream imports and old flat event/outcome field breakage.
- **assessment**: The public breaking surface is now deliberate, visible, and covered by docs/test/completion-report scope.

## Open Questions

无 blocking questions。

## Residual Risks

- Slice 1 is necessarily broad because removing old public request/context types without compatibility requires contracts, helper APIs, Engine contracts, Agent runtime, exports, and tests to move together. This is a reviewability risk, but not a blocker because the plan gives exact files, ordered steps, validation commands, expected assertions, and a stop condition.
- Host / ToolRuntime orphan cleanup after timeout remains explicitly tracked as Host / ToolRuntime responsibility in docs scope. This is outside the current Engine contract migration and is not blocking.

## Handoff Readiness

The revised plan is handoff-ready and code-generation-ready for implementation. The 4 accepted findings are fixed, no accepted finding remains partially fixed or not fixed, and no new blocker was found within the requested re-review scope.
