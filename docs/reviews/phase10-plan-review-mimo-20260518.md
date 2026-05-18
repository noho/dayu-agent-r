# Phase 10 Context Governance / Compaction — Plan Review

- Reviewer: AgentMiMo
- Date: 2026-05-18
- Artifact reviewed: `docs/host/phase10-context-governance-plan.md`
- Related: `docs/host/design.md` §23-25, `docs/host/implementation-control.md` Phase 10

---

## Verdict

**CHANGES_REQUESTED**

---

## Summary

Phase 10 plan 整体架构正确：proactive failure 不创建 Attempt、reactive recovery 走 `RECOVERING` + 新 Attempt、P9 memory projection 消费 `CONTEXT_COMPACTED` 而非旧 `EPISODE_SUMMARY_ACCEPTED`、budget 真源来自 Host typed policy 而非 Engine overflow。slice 依赖顺序合理（Budget → Compactor → Events/P9 → Proactive → Reactive → Wiring），non-goals 对齐 design，residual risks 诚实。

但有 3 条 blocking findings 需要修复后才能派 implementation agent 执行：`cancel_run` 不识别 `ACCEPTED` 状态、`promote_queued_run_in_transaction` 缺少 P10 governance gate 改造描述、`CONTEXT_COMPACTED` payload 在 memory projection 中的解析逻辑不够具体。另有 2 条 high、4 条 medium、3 条 low。

---

## Findings

### B1. `cancel_run` admission path 不识别 `RunStatus.ACCEPTED`

**Severity: blocking**

Plan §State Machine / Pre-start Governance Gate 声明添加 `RunStatus.ACCEPTED = "accepted"` 到 `RunStatus` enum 和 schema CHECK。但当前 `admission.py:1044-1048` 的 `cancel_run` 只处理 `QUEUED`、`RUNNING`、`CANCELLING`、`WAITING` 和 terminal 状态。未知状态直接抛出 `INVALID_STATE` 错误。

新增 `ACCEPTED` 后，`cancel_run` 对 `ACCEPTED` 状态的 Run 会落入最后的 `raise HostApiError(code=INVALID_STATE)` 分支，导致已 accepted 但未 started 的 Run 无法被取消。

**Evidence:**
- `dayu/host/admission.py:1006-1048`：cancel_run 只匹配 QUEUED、RUNNING、CANCELLING、WAITING 和 terminal。
- `dayu/host/api.py:261-277`：当前 RunStatus 无 ACCEPTED 成员。

**Impact:** Slice 4 引入 `ACCEPTED` 状态后，必须同步修改 cancel_run 处理逻辑。`ACCEPTED` 状态的 Run 无 Attempt、无 dispatch record，cancel 应类似 `QUEUED` 的简单收口。

**Recommendation:** Plan Slice 4 的 Allowed files / modules 已包含 `dayu/host/admission.py`，应在 Exact changes 中显式列出：cancel_run 必须处理 `ACCEPTED` 状态的 Run（追加 `RUN_CANCELLED`，设终态，不创建 Attempt）。

---

### B2. `promote_queued_run_in_transaction` 缺少 P10 governance gate 改造描述

**Severity: blocking**

Plan §Pre-start Governance Gate 声明："Promotion from QUEUED should also go through the same proactive governance gate before RUN_STARTED / ATTEMPT_STARTED。"但当前 `run_transition.py:758-837` 的 `promote_queued_run_in_transaction` 直接在同事务中创建 `RUN_STARTED` + `ATTEMPT_STARTED` + dispatch record，无任何 governance gate。

Plan 的 Exact changes 只描述了 `start_accepted_run_with_starting_attempt_in_transaction` 和 `fail_accepted_run_before_attempt_in_transaction` 两个新 helper，没有说明如何改造 promotion 路径使其经过 governance gate。

**Evidence:**
- `dayu/host/durable/run_transition.py:791-828`：promotion 直接 append RUN_STARTED + ATTEMPT_STARTED + dispatch record。
- `dayu/host/admission.py:917-932`：`_PromoteNextQueuedRunOperation` 直接调用 `promote_queued_run_in_transaction`。

**Impact:** 如果不改造 promotion 路径，QUEUED → RUNNING 的转换会绕过 proactive governance gate，导致首 Run 超预算时直接 dispatch 而不触发 compact。这是一个语义不一致的 gap。

**Recommendation:** Plan 应在 Slice 4 中明确两种方案之一：
1. `promote_queued_run_in_transaction` 改为先设 status=ACCEPTED，然后走 governance gate（与 start_run 的 ACCEPTED 路径合并）。
2. 新增 `promote_queued_run_through_governance_in_transaction` helper，由 admission 调用，在事务内先 governance evaluate 再决定是否 RUN_STARTED / ATTEMPT_STARTED。

---

### B3. `CONTEXT_COMPACTED` payload 在 memory projection 中的解析逻辑不够具体

**Severity: blocking**

Plan Slice 3 声明 `project_conversation_memory_event` 必须解析 `CONTEXT_COMPACTED` payload 并物化 episode summary 和 pinned state patch。但当前 `memory.py:1049-1051` 的 `_episode_summary_from_projection_event` 只处理 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED` 的 payload 结构。

`CONTEXT_COMPACTED` payload（plan §Canonical Compact Events 定义）包含 `episode_summary_candidate`、`pinned_state_patch_candidate`、`preserved_fact_refs` 等新字段。这些字段的结构与现有 `EPISODE_SUMMARY_ACCEPTED` payload 不同。Plan 没有说明：

1. `_episode_summary_from_projection_event` 是否需要重构为接受新 payload 结构。
2. pinned state patch 的三态语义如何在 projection 中具体实现（`_pinned_state_with_user_input` 当前只处理 USER_INPUT_ACCEPTED 的 deterministic projection）。
3. 是否需要新增 `_apply_pinned_state_patch_candidate` 辅助函数。

**Evidence:**
- `dayu/host/memory.py:1049-1051`：当前只消费 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED`。
- `dayu/host/memory.py:1038-1045`：`_pinned_state_with_user_input` 只处理 USER_INPUT_ACCEPTED。
- `docs/host/phase10-context-governance-plan.md:280-285`：描述了目标行为但未给出实现路径。

**Impact:** Slice 3 是 P10 的核心变更之一。如果 projection 解析逻辑不具体，implementation agent 需要自行设计 payload 结构与解析路径，可能偏离 design intent。

**Recommendation:** Plan Slice 3 应补充：
- `CONTEXT_COMPACTED` payload 中 `episode_summary_candidate` 和 `pinned_state_patch_candidate` 的 typed dataclass 定义（可复用 compactor output 结构）。
- `project_conversation_memory_event` 中新增 `_CONTEXT_COMPACTED` 分支的伪代码或描述，说明 episode summary 如何映射为 `ConversationContinuityKind.EPISODE_SUMMARY`，pinned patch 如何按字段三态更新 `PinnedStateView`。
- 是否复用现有 `_episode_summary_from_projection_event` 或新建 `_compact_episode_summary_from_projection_event`。

---

### H1. Per-Run proactive trigger count 的 EventLog 查询未说明

**Severity: high**

Plan §Context Policy 声明："proactive / reactive 每个 Run 第一版各最多 compact 一次，计数来自 committed `CONTEXT_COMPACTION_REQUESTED` facts，不用内存 flag。"但没有说明：

1. 如何查询某 Run 已有的 `CONTEXT_COMPACTION_REQUESTED` fact 数量（是新增 EventLog reader helper 还是复用现有 query）。
2. 该查询在哪个事务中执行（governance gate 事务还是独立 read 事务）。
3. 如果查询失败或超时，fail-open 还是 fail-closed。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:86`："计数来自 committed CONTEXT_COMPACTION_REQUESTED facts，不用内存 flag。"
- 当前 EventLog reader 未见按 Run id + event type 计数的现成 helper。

**Impact:** 这是防止 compact loop 的关键机制。如果查询路径不明确，implementation agent 可能用内存 flag 替代（违反 plan intent）或实现不一致的查询方式。

**Recommendation:** Plan 应在 Slice 4 或 Slice 5 中明确：新增 `count_committed_events_by_run_and_type(transaction, run_id, event_type) -> int` helper，放在 `dayu/host/durable/event_log.py` 或现有 reader 模块中。

---

### H2. `start_accepted_run_with_starting_attempt_in_transaction` 与现有 helper 的关系不清晰

**Severity: high**

Plan §Pre-start Governance Gate 声明新增 `start_accepted_run_with_starting_attempt_in_transaction`，但没有说明它与现有 `create_running_run_with_starting_attempt_in_transaction`（`run_transition.py:679`）的关系。

具体问题：
1. 新 helper 是否复用 `RUN_ACCEPTED` 事件（即 accepted_event_id / accepted_event_sequence），还是重新创建？
2. `create_running_run_with_starting_attempt_in_transaction` 是否保留（供非 governance 路径使用）还是被替代？
3. 新 helper 的 `CreateRunningRunInput` 是否需要调整字段（例如去掉 attempt_id，因为 governance gate 决定后再分配）？

**Evidence:**
- `dayu/host/durable/run_transition.py:679-736`：`create_running_run_with_starting_attempt_in_transaction` 同事务创建 RUN_ACCEPTED + RUN_STARTED + ATTEMPT_STARTED + dispatch record。
- `docs/host/phase10-context-governance-plan.md:166`："Add transition helper start_accepted_run_with_starting_attempt_in_transaction that appends RUN_STARTED(start_reason=initial)、ATTEMPT_STARTED and creates dispatch record only after proactive governance allows dispatch."

**Impact:** 如果新 helper 与旧 helper 职责重叠或接口不一致，会导致两条路径的 Run 创建语义分裂。

**Recommendation:** Plan 应明确：
- 新 helper 接受已存在的 `RUN_ACCEPTED` event（status=accepted 的 Run row），只追加 `RUN_STARTED` + `ATTEMPT_STARTED` + dispatch record。
- `create_running_run_with_starting_attempt_in_transaction` 在 P10 后不再由 start_run 直接调用；它的原子 ACCEPTED→STARTED→ATTEMPT_STARTED 语义被拆分为两步。
- 是否保留旧 helper 供未来用途或标记为 deprecated。

---

### M1. Conservative estimator 常量命名与放置位置未指定

**Severity: medium**

Plan §Context Policy 声明："实现中用命名常量，不散落 magic number"和"所有系数必须是命名 policy 常量"。但没有指定这些常量的命名、放置模块或默认值。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:84-92`。

**Impact:** Implementation agent 需要自行决定常量命名和放置。不同 agent 可能做出不一致选择。

**Recommendation:** Plan 应列出关键常量示例，例如：
- `DEFAULT_SAFETY_MARGIN_RATIO = 0.2`（对应 soft threshold 80%）
- `DEFAULT_CHAR_TO_TOKEN_RATIO = 4`（保守估算）
- `DEFAULT_PER_MESSAGE_OVERHEAD_TOKENS = 10`
- 放置在 `dayu/host/context_budget.py` 模块级。

---

### M2. Production composition wiring 的具体接入步骤不详细

**Severity: medium**

Plan Slice 6 描述了目标数据流，但没有说明 `context_window_size` 和 `reserved_output_tokens` 如何从 Service / composition root 传递到 `HostLocalExecutionOptions`。当前 `command.py:719` 装配了 `artifact_root` 等 durable payload policy，但未见 context budget 相关字段。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:436-449`：数据流描述存在但接入步骤不详细。
- `dayu/host/command.py:719`：当前装配路径无 context budget。

**Impact:** Slice 6 是最后一个 slice，如果 wiring 路径不清晰，可能导致整个 P10 无法端到端工作。

**Recommendation:** Plan Slice 6 应明确：
- `HostLocalExecutionOptions` 新增哪些字段（`context_budget_policy: ContextBudgetPolicy` 还是 `context_budget_provider: ContextBudgetProvider`）。
- `command.py` 中如何从 `HostCommandHandleOptions` 读取并传递这些字段。
- 是否需要更新 `create_host_local_execution_options` 工厂函数。

---

### M3. `CONTEXT_COMPACTED` 不直接改变 Run / Attempt 状态的表述需要澄清

**Severity: medium**

Plan §Slice 3 声明 "`CONTEXT_COMPACTED` itself does not directly mutate Run / Attempt state"。但在 proactive flow 中，`CONTEXT_COMPACTED` 是同一事务序列的一部分，事务提交后 Run status 从 ACCEPTED 变为 RUNNING。表述容易被误解为 `CONTEXT_COMPACTED` 完全不影响状态。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:291-293`。

**Impact:** 低，但可能导致 implementation agent 在事务边界设计上犯错。

**Recommendation:** 改为 "`CONTEXT_COMPACTED` 事件本身不包含 Run/Attempt 状态变更 payload；状态变更由同一事务中的 `RUN_STARTED` / `ATTEMPT_STARTED` 完成"。

---

### M4. Schema CHECK constraint 变更的向后兼容性未讨论

**Severity: medium**

Plan 声明要在 `schema.py` 的 `host_runs.status` CHECK 中添加 `'accepted'`。当前 P9 生产库已有数据。Plan 未说明这是 fresh schema 起库（符合 CLAUDE.md "schema 变更一律按全新 schema 起库处理"）还是需要兼容升级。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:162`。
- `CLAUDE.md`："涉及 schema 变更时：一律按全新 schema 起库处理；禁止旧库兼容读取、兼容测试，除非当前任务明确要求兼容升级。"

**Impact:** 如果 P9 生产库已存在，CHECK constraint 变更需要重建表或使用 `ALTER TABLE`。Plan 应明确选择。

**Recommendation:** Plan 应添加一行说明："P10 schema 变更遵循 CLAUDE.md 全新 schema 起库约定；旧库数据不保留。"

---

### L1. `FakeContextCompactor` 放置路径的 import boundary 未明确

**Severity: low**

Plan 声明 "推荐 production 放 `dayu/host/fake_compaction.py` 仅用于 tests / local composition 明确注入"。但 `CLAUDE.md` 要求 "禁止胶水 seam"。如果 `fake_compaction.py` 在 production 包中，需要确保它不被 production code path 隐式导入。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:110`。

**Impact:** 低。现有 `NoopCompactArtifactProvider` 已有类似模式（`run_input.py:888`），可作为参考。

**Recommendation:** 保持现有模式：fake/noop 放在 production 包但只由 composition root 显式注入，不在默认路径使用。

---

### L2. `usage_reported` projection signal 的 payload 扩展范围未限定

**Severity: low**

Plan Slice 1 声明 "Extend usage projection signal payload, if needed, to include policy/estimator observation refs while preserving no state transition"。但 "if needed" 不确定。如果不需要扩展，应明确不改。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:200`。
- `dayu/host/engine_ingest.py:549-553`：当前 USAGE_REPORTED 只做 projection signal。

**Impact:** 低。如果 usage payload 不扩展，`UsageObservation` 只在 Host 内部使用。

**Recommendation:** 明确：P10 不扩展 USAGE_REPORTED 的 EventLog payload；`UsageObservation` 只在 Context Governance 内部记录，不进入 EventLog。

---

### L3. Tests README 触发更新规则的描述过于笼统

**Severity: low**

Plan §Docs Update Decision 声明更新 `tests/README.md`，但没有说明具体新增哪些测试类别描述。

**Evidence:**
- `docs/host/phase10-context-governance-plan.md:497`。

**Impact:** 低。Implementation agent 可以自行添加，但可能导致描述风格不一致。

**Recommendation:** Plan 应列出 tests/README.md 需要新增的类别：`test_context_budget`、`test_compaction_contract`、`test_compact_artifact_store`、`test_context_compact_events`。

---

## Non-issues / False Positives

以下疑虑经代码证据验证后确认为 non-issue：

1. **`RunStatus.RECOVERING` 已在 schema 和 enum 中存在**：`api.py:273` 有 `RECOVERING = "recovering"`，`schema.py:307` CHECK 包含 `'recovering'`，`schema.py:803` active-run index 包含 `'recovering'`。P10 只需首次写入该状态，无需 schema 变更。✅

2. **`CONTEXT_COMPACTED` 是否在 P9 memory projection event filter 中**：当前 filter (`durable/memory.py:74-78`) 只包含 `EPISODE_SUMMARY_ACCEPTED`。Plan Slice 3 明确要求扩展 filter 包含 `CONTEXT_COMPACTED`。这是计划中的变更，不是遗漏。✅

3. **stable layer / history pool 数据来源完整性**：Plan §Truth Sources 和 §25 的设计文档正确覆盖了 raw turns（USER_INPUT_ACCEPTED + RUN_SUCCEEDED）、episode summaries（CONTEXT_COMPACTED）、pinned state patch（CONTEXT_COMPACTED）、verified facts（TOOL_RESULT_ACCEPTED）。owner 清晰。✅

4. **Engine overflow 不作为预算真源**：Plan 多处强调（§Motivation、§Slice 1 stop condition、§Slice 5），`CONTEXT_COMPACTION_REQUESTED` 从 Engine 来时仍使用 Host estimator。与 design.md §25.1 一致。✅

5. **proactive failure 不创建 Attempt**：Plan §Pre-start Governance Gate 和 §Slice 4 的 stop condition 都明确要求。这与 `create_running_run_with_starting_attempt_in_transaction` 的当前行为（同时创建 Attempt）冲突，但 plan 已通过引入 ACCEPTED pre-start 状态解决。✅

---

## Residual Risks (PASS 时也需列出)

1. **`RunStatus.ACCEPTED` 的广泛测试更新**：新增 public enum 成员和 schema CHECK 值会影响所有 RunStatus 枚举测试、schema 验证测试、admission 测试和 dispatch 测试。Risk 已在 plan 中识别。

2. **Engine 双重事件的幂等性**：Engine 可能同时 emit `context_compaction_requested` 和 `run_failed(context_compaction_required)`。Plan 要求 idempotent 处理，但实现复杂度可能被低估。

3. **Real LLM compactor 未就绪**：Fake compactor 可验证 Host governance，但 production 需要显式注入 compactor port。Plan 已识别。

4. **Conservative estimator 过度触发 compact**：char-to-token 上界估算可能导致不必要的 proactive compaction。这是有意的 fail-safe 设计，但可能影响用户体验。

5. **Orphan artifact 文件**：crash 发生在 artifact 文件写入和 DB event 提交之间时，artifact 文件成为孤立残留。Plan 已识别并明确归 Phase 11。

---

## Appendix: Evidence Index

| File | Lines | Relevance |
|------|-------|-----------|
| `dayu/host/api.py` | 261-277 | RunStatus enum，无 ACCEPTED |
| `dayu/host/durable/schema.py` | 297-313 | host_runs.status CHECK，无 'accepted' |
| `dayu/host/durable/schema.py` | 798-804 | active-run unique index，不含 'accepted' |
| `dayu/host/admission.py` | 1006-1048 | cancel_run 不识别 ACCEPTED |
| `dayu/host/admission.py` | 917-932 | promote 直接调用 promote_queued_run_in_transaction |
| `dayu/host/durable/run_transition.py` | 679-736 | create_running_run_with_starting_attempt_in_transaction |
| `dayu/host/durable/run_transition.py` | 758-837 | promote_queued_run_in_transaction 直接创建 RUN_STARTED + ATTEMPT_STARTED |
| `dayu/host/memory.py` | 997-1058 | project_conversation_memory_event，消费 EPISODE_SUMMARY_ACCEPTED |
| `dayu/host/memory.py` | 313-338 | PinnedStateView 定义 |
| `dayu/host/durable/memory.py` | 70-78 | event filter 只含 EPISODE_SUMMARY_ACCEPTED |
| `dayu/host/engine_ingest.py` | 513-530 | CONTEXT_COMPACTION_REQUESTED 当前按 unsupported recovery 收口 |
| `dayu/host/engine_ingest.py` | 549-553 | USAGE_REPORTED 为 projection signal |
| `dayu/host/run_input.py` | 338-350 | CompactArtifactProvider protocol |
| `dayu/host/run_input.py` | 888-906 | NoopCompactArtifactProvider |
| `dayu/host/run_input.py` | 1209-1223 | message 顺序：scene, memory, compact, continuity, user prompt |
| `dayu/host/run_input.py` | 1267, 1303 | 工厂函数硬接 no-op compact provider |
| `dayu/host/dispatch.py` | 798-862 | _run_input_builder_for_dispatch 只注入 memory provider |
| `dayu/host/dispatch.py` | 720-725 | dispatch 前 catch_up_memory_projection |
