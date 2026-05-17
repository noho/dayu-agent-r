# P9 Aggregate Deepreview Controller Adjudication

日期：2026-05-17

范围：Phase 9 Conversation Memory / Session Memory Projection，`f27ce8a..1b19b35`

## Verdict

PASS。

AgentMiMo 与 AgentDS 两份 aggregate deepreview 均给出 PASS，remaining blocking findings 为 0。Phase 9 满足 ready-to-open-draft-PR gate。

## Review Artifacts

- AgentMiMo: `docs/reviews/p9-aggregate-deepreview-mimo-20260517.md`
- AgentDS: `docs/reviews/p9-aggregate-deepreview-ds-20260517.md`

## Controller Judgment

P9 的核心实现符合设计裁决：

- Memory 是 session-level 财报分析工作台状态投影，不是聊天记录压缩器。
- `verified_facts` 只来自 `TOOL_RESULT_ACCEPTED`，类型级强制 `tool_verified` claim status 与 tool provenance。
- `RUN_SUCCEEDED` final answer 与 `USER_INPUT_ACCEPTED` 不会进入 verified facts。
- RunInputBuilder memory 注入顺序与 budget 策略符合 P9 裁决，当前用户 prompt 仍由 current run fact 提供。
- projection lag / repair / catch-up 是 projection-local 行为，不进入 Run recovery，不修改 EventLog 或 Run / Attempt / wait / dispatch truth。
- Issue 39 只预留 Host-neutral anchor / claim / provenance / trace 边界，没有实现长期 retrieval、业务 signal ledger 或 public edit/reset/forget API。
- Schema 按 fresh-only v6 处理，无旧库兼容路径。

## Non-blocking Findings

Controller 接受以下 findings 为 deferred / tracked，不阻塞 PR：

- `MemoryIncludedReason` / `MemoryExcludedReason` 粒度低于 plan 规格；owner 为 Phase 10 / Tool Trace phase，在下游 consumer 稳定前统一。
- unsupported event type diagnostic 当前复用 `SNAPSHOT_DAMAGED` reason，`UNSUPPORTED_EVENT_TYPE` excluded reason 尚无 item-level consumer；owner 为后续 schema hardening。
- budget 丢弃 items 只记录 aggregate diagnostic，不保留 per-item excluded reason；owner 为 Tool Trace / Phase 13。
- stable layer budget 按 block 裁剪，不做 block 内截断；owner 为 Phase 10 provider-aware budget work。
- pinned state 共用一个 `max_pinned_items` cap；owner 为 Phase 10 policy refinement。
- `WorkingAssumptionView` 基础设施已落地，但 P9 没有主动数据填充路径；owner 为 Phase 10 proactive compaction / issue 39 retrieval。
- `current_goal` first-write-wins 语义未单独写入 design；owner 为 steer / goal-change hardening gate，当前 P9 的目标稳定语义可接受。
- `SessionContinuityProvider` protocol 的 `snapshot` 参数当前在 durable implementation 中被忽略；owner 为 Phase 10 protocol cleanup。
- dispatch / waiting 层存在低风险冗余 catch-up 调用；owner 为 production wiring cleanup。
- preview facts exclusion、memory import boundary、lag non-mutation 分支和 catch-up end-to-end 可补专项测试；owner 为 Host hardening，不阻塞当前 PR。
- production concrete memory catch-up port 未由 public command handle 默认接入；owner 为后续 Host / Service composition wiring。

## Final Gate Validation

P9-S4 后已验证：

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py`：129 passed。
- `pyright dayu/host tests/host`：0 errors。
- `git diff --check`：通过。

Reviewer 额外验证：

- AgentMiMo: `pyright` memory / run_input / projection subset 0 errors；memory / run_input / durable schema subset 63 passed。
- AgentDS: 手动验证 memory / durable memory / memory_repair import boundary 与 weak typing discipline，无 blocking finding。

## Decision

Phase 9 aggregate deepreview accepted。进入 ready-to-open-draft-PR；用户已授权 draft PR gate，可继续 push、创建 draft PR 并推进 PR review。
