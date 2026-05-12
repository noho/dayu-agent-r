# ToolExecutor Batch Handshake Plan Review

- **review gate name**: plan review
- **reviewed target**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **review scope**: ToolExecutor batch public contract, Engine batch state machine, suspended outcome shape, cancellation / awaiting / cancelled semantics, implementation slicing, tests, docs decision
- **review method**: `$planreview` evidence-based adversarial review
- **reviewer conclusion**: fail
- **artifact path**: `docs/reviews/gateflow-plan-review-tool-executor-batch-20260512.md`

## Assumptions Tested

- Motivation: Runner and Engine event surface already operate around tool-call batches, while `ToolExecutor.execute` remains single-call; moving batch governance to Host / ToolRuntime is directionally justified.
- Architecture boundary: Engine should keep LLM loop and state-machine ownership; Host / ToolRuntime may own internal batch scheduling, approval, rate limit, cancellation and orphan cleanup.
- Public contract: breaking old `ToolExecutionRequest` and old event shapes is allowed by the work unit, but the plan must still make all public breakages explicit and code-generation-ready.
- Mixed awaiting: if `run_agent_and_wait` promises terminal records sufficient for later explicit resume, those records must contain enough facts to reconstruct the necessary assistant tool-call roundtrip, not only outcome ids.
- Slice validation: each implementation slice should be reviewable and should not knowingly leave pyright red unless the plan combines the dependent work into the same slice/checkpoint.

## Findings

### 1-未修复-[高]-suspended terminal records do not carry enough identity to close mixed-awaiting resume semantics
- **Plan位置**: §5.6 Engine Suspension Records, §6.2 Batch Contains Awaiting, §12 Risks and Residual Risk Tracking
- **问题类型**: 契约缺失 / 状态机漏洞 / 不可直接实施
- **计划当前写法**: `AcceptedToolExecutionRecord` contains `iteration_id`, `tool_call_id`, `name`, `index_in_iteration`, and `outcome`; `AwaitingToolExecutionRecord` contains `iteration_id`, `tool_call_id`, `name`, `index_in_iteration`, `await_spec`, and `snapshot`. `RunSuspendedData` / `EngineRunOutcomeSuspended` carry only `accepted_records` and `awaiting_records`. The plan says `run_agent_and_wait` "只保证 terminal 携带恢复所需的 batch accepted / awaiting facts" and that callers can reconstruct full batch facts for later explicit resume.
- **为什么有问题**: The proposed terminal records omit `ToolCallRequest.arguments`, `ToolCallRequest.provider_state`, and the assistant tool-call message content/reasoning fields. For a mixed awaiting batch, the plan also says Engine will not inject tool messages and resume is delegated to the caller. A wait-style caller has no event history, so the terminal outcome must be sufficient on its own if the plan claims it carries resume facts. With the proposed shape, the caller cannot reconstruct the assistant `tool_calls` message or provider continuation state for providers that need `provider_state`.
- **直接证据**: Plan lines 181-217 define the two record shapes without `arguments` or `provider_state`; line 221 claims terminal carries recovery facts for aggregate callers; lines 249-252 say mixed awaiting does not inject messages and resume is caller-constructed; line 533 claims the records let stream and wait callers reconstruct full batch facts. Current `ToolCallRequest` includes `arguments` and `provider_state` in `dayu/contracts/tool_call.py:55-71`. Current Engine message injection needs `record.call.name`, `record.call.arguments`, and `record.call.provider_state` to build `AssistantToolCall` in `dayu/engine/agent.py:1596-1608`.
- **影响**: 聚合调用方无法可靠恢复 mixed awaiting batch；provider_state 丢失会导致 provider roundtrip 不完整；实施 Agent 可能按当前记录形状实现后才在恢复设计或后续测试中返工。
- **建议改法和验证点**: Make the terminal/event record identity complete for resume, preferably by carrying `call: ToolCallRequest` in `AcceptedToolExecutionRecord` and `AwaitingToolExecutionRecord`, or by explicitly carrying `arguments` and `provider_state` plus any assistant content/reasoning facts needed by the chosen resume contract. If the plan does not intend terminal outcome to be resume-complete, remove that claim and classify the missing resume contract as a blocking open question. Add a `run_agent_and_wait` mixed batch test that reconstructs the required assistant tool-call facts, including arguments and provider_state.
- **修复风险（中）**: Expanding record shape is straightforward but affects event contract, docs, tests, and public exports.
- **严重程度（高）**:

### 2-未修复-[高]-implementation slices knowingly create pyright-red intermediate states
- **Plan位置**: §9 Implementation Slices, especially Slice 1, Slice 3, and Slice 4
- **问题类型**: 切片过粗 / 不可直接实施 / 测试缺口
- **计划当前写法**: Slice 1 removes single request/context types and changes `ToolExecutor.execute`, then still lists `pyright` as validation while stating "Pyright may still fail in later production files until Slice 2 lands". Slice 3 changes event and suspended outcome contracts, then lists `pyright`, while Slice 4 later updates `dayu/engine/agent.py` to compile against those new shapes.
- **为什么有问题**: The project constraint requires pyright after changes with no new or expanded type errors. A slice that knowingly leaves later production files broken is not a valid implementation checkpoint. Slice 3 has the same issue even though the plan does not call it out: current Agent constructs `ToolResultAcceptedData(iteration_id=..., tool_call_id=..., outcome=...)`, `ToolAwaitingData(tool_call_id=..., await_spec=...)`, and maps `RunSuspendedData.await_spec/snapshot`; after Slice 3 those fields would be removed before Slice 4 updates the Agent.
- **直接证据**: Plan lines 347-352 include Slice 1 pyright validation but also admit pyright may fail until Slice 2. Plan lines 386-396 change `ToolResultAcceptedData`, `ToolAwaitingData`, `RunSuspendedData`, and `EngineRunOutcomeSuspended` before Agent migration. Current Agent uses old event fields in `dayu/engine/agent.py:1428-1432`, `1458-1464`, `1827-1831`, and `2271-2277`. Current `tool_declaration.py` imports `ToolExecutionRequest` and types `FunctionToolExecutor.execute` with the old signature in `dayu/contracts/tool_declaration.py:17-43`.
- **影响**: Implementation agent either ignores per-slice pyright, combines slices ad hoc, or performs unplanned work outside assigned slice to regain type safety. Review becomes hard because intermediate checkpoints are not independently green.
- **建议改法和验证点**: Re-slice into pyright-green checkpoints. At minimum, merge Slice 1 and Slice 2 into one contract-helper checkpoint, and merge event contract changes with the minimal Agent compile migration that consumes the new fields. Alternatively introduce temporary private dual-shape adapters only if explicitly justified, but the current project constraints discourage compatibility shims. Each slice validation must include pyright with no known expected failures.
- **修复风险（中）**: Requires plan restructuring and possibly a different vertical slice order; it does not require changing the overall batch design.
- **严重程度（高）**:

### 3-未修复-[中]-batch outcome mismatch validation is underspecified for duplicate returned records
- **Plan位置**: §7 Error and Race Semantics, §9 Slice 4, §10 Test / Validation Matrix, §12 Risks
- **问题类型**: 契约缺失 / 状态机漏洞 / 测试缺口
- **计划当前写法**: The plan says "batch outcome record 集合不匹配输入 call ids" fails with `tool_batch_outcome_mismatch`, Slice 4 says "Validate returned records exactly match input call ids", and tests mention a generic "batch record mismatch" assertion.
- **为什么有问题**: "id set" is not enough to define a batch outcome contract. A buggy executor can return duplicate records for one input id and omit another, or return the right set plus an extra duplicate. If implementation uses set equality or a dict keyed by `tool_call_id`, duplicates can be silently overwritten while Engine proceeds as if the batch is valid. That violates the one-input-call-to-one-record invariant needed for tool message pairing and event order.
- **直接证据**: Plan line 279 uses "record 集合" wording; line 420 says "exactly match input call ids" but does not specify bijection, duplicate-output rejection, or length equality; lines 451 and 507 only require generic mismatch tests. Current plan does explicitly prevalidate duplicate input ids at line 280, but does not specify duplicate returned record handling.
- **影响**: 错误 executor 输出可能被静默接受；某个工具 outcome 丢失或被另一个 duplicate 覆盖；LLM-facing tool message pairing 和 `tool_calls_batch_done.tool_call_ids` 可变得不可信。
- **建议改法和验证点**: Specify a strict bijection: `len(records) == len(calls)`, every input id appears exactly once, no unknown id appears, and duplicate returned ids are fatal even if the set of ids appears correct. Add focused tests for missing id, extra unknown id, duplicate returned id, and records returned in non-input order.
- **修复风险（低）**: Mostly specification and tests; implementation can use a `Counter` or explicit seen-id map with duplicate detection.
- **严重程度（中）**:

### 4-未修复-[中]-public event consumer breakage is not fully surfaced in risks and docs/test scope
- **Plan位置**: §5.6 Engine Suspension Records, §8 Affected Files / Modules, §10 Test / Validation Matrix, §12 Risks and Residual Risk Tracking, §13 Completion Report Format
- **问题类型**: 契约缺失 / 测试缺口 / 文档缺口
- **计划当前写法**: The plan changes `ToolResultAcceptedData` and `ToolAwaitingData` from flat public event fields to `record` fields, and changes suspended terminal fields. The residual-risk section only calls out downstream imports of old `ToolExecutionRequest` as an intentional public break.
- **为什么有问题**: `ToolResultAcceptedData`, `ToolAwaitingData`, `RunSuspendedData`, and `EngineRunOutcomeSuspended` are public Engine contract types, not private implementation details. Existing consumers and tests access `event.data.tool_call_id`, `event.data.await_spec`, and `result.await_spec` directly. Since compatibility is intentionally not preserved, the plan must explicitly document this as a public event/outcome breaking change and include migration assertions/docs so the breakage is deliberate rather than accidental.
- **直接证据**: Plan lines 206-219 change event/terminal shapes; lines 531-539 list residual risks but only mention old `ToolExecutionRequest` imports. Current public event data classes expose flat fields in `dayu/engine/contracts/engine_events.py:177-225` and `316-327`. Existing tests access flat fields in `tests/engine/test_agent_phase3_tool_call.py:1320-1330`, and `tests/engine/test_agent_phase2.py` has direct `RunSuspendedData(...)` construction and `result.await_spec` assertions.
- **影响**: 事件消费者破坏面被低估；README/design docs may fail to tell callers how to migrate; review acceptance can miss public API breakage outside the executor request path.
- **建议改法和验证点**: Add an explicit public contract break section covering `ToolResultAcceptedData.record`, `ToolAwaitingData.record`, `RunSuspendedData.accepted_records/awaiting_records`, and `EngineRunOutcomeSuspended.accepted_records/awaiting_records`. Update docs decision to require those migration details in Engine docs. Add tests that assert the new event data shape and package exports, and update completion report risk wording to include event/outcome consumers, not only old request imports.
- **修复风险（低）**: Mostly plan/documentation/test-scope clarification; implementation already needs to migrate these fields.
- **严重程度（中）**:

## Open Questions

- **blocking**: What is the intended resume-complete identity for mixed awaiting batches: full `ToolCallRequest` in records, a separate assistant tool-call snapshot, or a narrower non-resume terminal contract? This must be settled before implementation because it changes public event/outcome dataclasses and tests.
  - **controller decision**: accepted
  - **fix status**: fixed-pending-re-review
  - **plan fix summary**: plan now chooses an explicit `AssistantToolCallBatchSnapshot` and requires accepted / awaiting records to carry both `batch_snapshot` and full `call: ToolCallRequest`.
- **non-blocking**: `ToolCancelledOutcome` currently uses `reason: str`, `message`, `hint`, and `meta` without a `recoverable` field. This is defensible because current tool failure outcomes also expose `hint` rather than run-level `recoverable`, but docs/tests should treat `reason` as a stable neutral code rather than prose.

## Residual Risks

- Motivation is valid and not over-designed in the reviewed code context: Runner already emits batch tool calls and Engine already has batch-ready/done events, while `ToolExecutor.execute` remains single-call.
- `BatchToolExecutionRecord(tool_call_id, outcome)` is sufficient for Engine to associate returned outcomes with in-memory input calls during the same handshake if and only if strict one-record-per-input-id validation is specified.
- Failed-batch policy for `ToolCancelledOutcome` remains a product semantics risk: "all cancelled" will reset the consecutive-failed counter under the current plan. I did not mark this as blocking because the plan intentionally separates tool-level cancellation from failure, but it should remain visible in code review and behavior tests.
- The docs decision is directionally correct, but it depends on fixing finding 4 so public event/outcome migration is documented explicitly.

## Controller Decision Status

- Finding 1: controller decision `accepted`; fix status `fixed-pending-re-review`; fix recorded in `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md` §5.6, §6.2, §9, §10, §12.
- Finding 2: controller decision `accepted`; fix status `fixed-pending-re-review`; fix recorded in `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md` §9.
- Finding 3: controller decision `accepted`; fix status `fixed-pending-re-review`; fix recorded in `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md` §7, §9, §10, §12.
- Finding 4: controller decision `accepted`; fix status `fixed-pending-re-review`; fix recorded in `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md` §5.7, §9, §10, §11, §12, §13.

## Plan Fix Artifact

- **fix artifact path**: `docs/reviews/gateflow-plan-fix-tool-executor-batch-20260512.md`
- **current fix gate status**: fixed-pending-re-review
