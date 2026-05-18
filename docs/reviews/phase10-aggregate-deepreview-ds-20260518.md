# Phase 10 Aggregate Deep Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Scope:** Phase 10 full commit range f131fb8..HEAD (7 commits, 17,384 insertions across 87 files)
**Verdict: PASS — Ready for draft PR**

## 审查方法

1. 阅读设计真源 `docs/host/design.md` 中 Context Governance (section 25)、Conversation Memory (section 24)、RunInputBuilder (section 23)、EngineEvent Ingest、Composition (section 10.1) 的完整内容。
2. 阅读 Phase 10 plan 的全部 6 个 slice 定义、exit conditions、停止条件。
3. 阅读 `implementation-control.md` 的 Phase 10 条目与追踪区。
4. 阅读全部 6 个 slice 的 review artifacts（DS + MiMo + controller adjudication）。
5. 分四个子系统深度审计当前 HEAD 代码：状态机/schema、proactive governance、reactive recovery、memory/RunInputBuilder。
6. 交叉验证 plan 要求的架构边界、退出条件、已知 residual。

---

## 1. 架构边界验证

### 1.1 Host vs Engine 预算真源

| 要求 | 状态 | 证据 |
|------|------|------|
| Host context budget policy 只从 composition root 装配 | **PASS** | `ContextBudgetPolicy` 构造参数 `context_window_size`/`reserved_output_tokens` 来自 `HostCommandHandleOptions` (`api.py:1172-1173`)，必填无默认值 |
| Host 不从 Engine `budget_state` 读取预算 | **PASS** | Reactive path `engine_ingest.py:1315-1316` 将 Engine `provider_request_id`/`provider_error_ref` 仅记录为 traceability ref，不参与 Host budget estimate |
| Host 不从 per-run metadata 读取预算 | **PASS** | `test_context_budget_inputs_are_not_per_run_fields` (`test_public_contracts.py:824-838`) 断言 budget 字段与 `StartRunRequest`/`SubmitFollowupRequest`/`HostMetadataEntry` 完全 disjoint |
| Host 不从 provider overflow event 读取预算 | **PASS** | `_start_reactive_context_recovery` (`engine_ingest.py:1014-1035`) 使用 Host `estimate_context_budget(policy, ...)` 生成 `BudgetEstimate`，不在 Engine data 中读取 token 计数 |
| Engine 不做 proactive compaction | **PASS** | Proactive 路径完全由 `HostDispatchScheduler._run_pre_start_governance` (`dispatch.py:532`) 驱动 |

**裁定: PASS。** 预算真源单向流动：`composition root → ContextBudgetPolicy → Host estimator → BudgetEstimate → decision`。Engine `context_compaction_requested` 只是触发信号，不携带 Host 预算数据。

### 1.2 Context Governance 不直接写 memory snapshot

| 要求 | 状态 | 证据 |
|------|------|------|
| Context Governance 是 orchestrator only | **PASS** | `context_governance.py` 仅包含 `check_compaction_candidate`（predicate），无 EventLog append、无 memory write |
| Memory projection 只消费 committed EventLog | **PASS** | `ConversationMemoryProjectionConsumer` 通过 `_EVENT_TYPE_FILTER` (含 `CONTEXT_COMPACTED`，不含 `CONTEXT_COMPACTION_FAILED`) 读取 committed events |
| Governance 不写 memory snapshot | **PASS** | Proactive compact 后 `catch_up_conversation_memory_projection` (`dispatch.py:518-525`) 通过 projection runner 消费 EventLog，不直接写 snapshot |
| Verified facts 只来自 TOOL_RESULT_ACCEPTED | **PASS** | `memory.py:1049-1053` — 只有 `TOOL_RESULT_ACCEPTED` 产生 `VerifiedFactView`；`_validate_compact_summary_fact_refs` (`memory.py:1690-1709`) 拒绝 summary 引用非 tool fact ref |
| LLM-produced patch 不直接写 Host truth | **PASS** | Pinned state patch 经过 `_apply_pinned_state_patch_candidate` tri-state 处理和 `check_compaction_candidate` quality check 后才写入 memory |

**裁定: PASS。** Context Governance → compact event → memory projection → snapshot 是严格的单向 EventLog 驱动链，Gov 不越界写 memory。

### 1.3 分层依赖

| 要求 | 状态 | 证据 |
|------|------|------|
| `command.py` 只 import `dayu.host.api`、`dayu.host.context_policy` | **PASS** | `command.py:9-47` — 无 Engine/Service/UI/Fins import |
| `dispatch.py` 不 import Engine 内部 | **PASS** | import 限于 `dayu.host.*`、`dayu.engine.contracts.*`（公共契约） |
| `engine_ingest.py` 不 import Service/UI/Fins | **PASS** | import 限于 `dayu.host.*` 和 `dayu.engine.contracts.*` |
| Memory policy 与 context budget policy 分离 | **PASS** | `compose_host_local_execution_options` (`command.py:288-301`) 只覆盖 `context_budget_policy` 和 compact artifact root，不修改 `memory_projection_policy` |

**裁定: PASS。** 无反向依赖、无越界 import。

---

## 2. 状态机验证

### 2.1 ACCEPTED 状态

| 检查项 | 状态 | 证据 |
|--------|------|------|
| `accepted` 在 CHECK constraint 中 | **PASS** | `schema.py:303` — `status IN ('accepted', 'queued', ...)` |
| ACCEPTED 行 `queued_event_id`/`started_event_id`/`current_attempt_id` 为 NULL | **PASS** | `schema.py:349-357` — 显式 CHECK constraint |
| ACCEPTED 在 active unique index 中 | **PASS** | `schema.py:814` — `WHERE status IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')` |
| `cancel_run` 处理 ACCEPTED | **PASS** | `admission.py:1014` — `_cancel_queued` 处理 `ACCEPTED \| QUEUED`；`cancel_queued_in_transaction` (`run_transition.py:2078`) 接受两种状态 |
| `start_run` REJECT/ATTACH_ACTIVE/QUEUE policy for ACCEPTED | **PASS** | `admission.py:734-774` — REJECT 冲突、ATTACH_ACTIVE 冲突（无 Attempt）、QUEUE 入队 |
| ACCEPTED ← CANCEL → CANCELLED (attempt-free) | **PASS** | `terminal_unstarted_run_row` (`state.py:2403`) — CAS `status IN (ACCEPTED, QUEUED)` |

**裁定: PASS。** ACCEPTED 状态正确实现为非终端、无 Attempt、受 active unique index 保护、可取消的 pre-start 状态。

**INFO — Redundant unique index** (`schema.py:817-821`): `host_runs_one_accepted_per_session WHERE status = 'accepted'` 与 `host_runs_one_active_per_session WHERE status IN ('accepted', ...)` 功能重叠。后者已保证最多一个 accepted 行。新增索引增加 INSERT/UPDATE 开销。建议移除或注明为文档化意图。

### 2.2 RECOVERING 状态

| 检查项 | 状态 | 证据 |
|--------|------|------|
| RUNNING → RECOVERING CAS | **PASS** | `mark_running_run_recovering_row` (`state.py:2844`) — CAS `status='running' AND current_attempt_id=?` |
| RECOVERING → RUNNING CAS + NOT EXISTS | **PASS** | `start_recovering_run_row` (`state.py:2907`) — CAS `status='recovering' AND current_attempt_id=?` + NOT EXISTS 5-status guard |
| RECOVERING → FAILED CAS | **PASS** | `terminal_recovering_run_row` (`state.py:2993`) — CAS `status='recovering' AND current_attempt_id=?` |
| RECOVERING 参与 active unique index | **PASS** | `schema.py:814` — `IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')` |
| No LOST from compact failure | **PASS** | `_fail_recovering_run` (`engine_ingest.py:909`) → `fail_recovering_run_in_transaction` → `terminal_recovering_run_row` → `FAILED` |
| Cancel race: ACCEPTED/RUNNING cancel 处理 | **PASS** | CAS preconditions 在 closeout 步骤（`run.status == RUNNING`）和 recovery start 步骤（`run.status == RECOVERING`）都正确 guard |
| Cancel race: RECOVERING cancel 未支持 | **ACCEPTED** | `admission.py:1052` — RECOVERING 返回 INVALID_STATE。属 Phase 11 范围 |

**裁定: PASS。** RECOVERING 状态机 CAS 条件正确，NOT EXISTS guard 与 unique index 对齐，compact failure 不产生 LOST。

### 2.3 Attempt-free failure

| 检查项 | 状态 | 证据 |
|--------|------|------|
| Proactive compact failure 无 Attempt row | **PASS** | `dispatch.py:599-606` — `_fail_unstarted_in_transaction` → `fail_unstarted_run_in_transaction` (`run_transition.py:1080`) 只写 `RUN_FAILED` |
| Proactive hard threshold 无 Attempt row | **PASS** | `dispatch.py:590-606` — 同上路径 |
| 无 dispatch record | **PASS** | `fail_unstarted_run_in_transaction` 不创建 dispatch record |
| 无 ATTEMPT_FAILED event | **PASS** | 只写 `CONTEXT_COMPACTION_FAILED` + `RUN_FAILED` |

**裁定: PASS。**

---

## 3. Proactive Governance 验证

### 3.1 Pre-start governance gate

| 检查项 | 状态 | 证据 |
|--------|------|------|
| ACCEPTED 优先选择 | **PASS** | `dispatch.py:1879-1895` — `read_accepted_run_for_session` 优先，无 active run 时读 queued |
| Budget estimate 使用 display_text | **ACCEPTED RESIDUAL** | `dispatch.py:570-580` — `BudgetEstimateInput` 仅含当前 `display_text`，不含 tool schema、memory messages、compact artifact refs。这是 S4 已知 residual（implementation-control.md:1507），归后续 tokenizer/sizing owner |
| Soft threshold → compact | **PASS** | `dispatch.py:608-667` — compact count check → `_compact_before_dispatch` |
| Hard threshold → fail (attempt-free) | **PASS** | `dispatch.py:590-606` |
| Compact count fail-closed | **PASS** | `dispatch.py:609-629` — payload 损坏时 raise `HostDurableError` |
| Compact limit per run (max 1 by default) | **PASS** | `dispatch.py:630-647` — `compact_count >= policy.max_proactive_compactions_per_run` → fail |
| Compact accepted → memory catch-up → start | **PASS** | `dispatch.py:517-528` — `catch_up_conversation_memory_projection` → `_start_governed_after_compact` |
| `_start_governed_after_compact` CAS cancel race check | **PASS** | `dispatch.py:680-683` — 独立事务中 re-read run status，若已变更返回 None |

**裁定: PASS。** Budget estimate scope 是 known residual。

### 3.2 Compactor inside SQLite transaction

**Severity: ACCEPTED RESIDUAL**

`_compact_before_dispatch` (`dispatch.py:793-941`) 和 `_compact_reactive_recovery` (`engine_ingest.py:707-849`) 在 SQLite write transaction 内调用 compactor 和 artifact write。S4/S5 已知 residual，归 Phase 10 follow-up compactor owner。

风险: 真实异步 LLM compactor 可能长时间阻塞 SQLite write lock；compactor 结果写入前无 durable in-progress/fencing。

当前适用: Fake compactor（同步）在测试中无阻塞；production 接入真实 compactor 前必须设计 fencing。

---

## 4. Reactive Recovery 验证

### 4.1 核心路径

| 检查项 | 状态 | 证据 |
|--------|------|------|
| Identity validation (attempt_id + execution_id) | **PASS** | `engine_ingest.py:761-769` — 校验 `attempt.execution_id` 和 `dispatch_record.execution_id` |
| Host estimator used (Engine budget_state=None) | **PASS** | `engine_ingest.py:1014-1035` — Host `estimate_context_budget`，Engine data 仅用于 traceability |
| Old Attempt → ATTEMPT_FAILED + RUN_RECOVERING | **PASS** | `engine_ingest.py:1058-1063` → `close_attempt_for_context_recovery_in_transaction` (`run_transition.py:1133`) |
| New Attempt with new attempt_id/execution_id | **PASS** | `_StartReactiveRecoveryOperation` (`engine_ingest.py:161-405`) 生成新 id，不重用旧 Attempt |
| Compact count from committed facts (fail-closed) | **PASS** | `engine_ingest.py:1236` → `count_committed_events_by_run_and_type` |
| Compact failure → FAILED (not LOST) | **PASS** | `engine_ingest.py:1073-1087` → `_fail_recovering_run` → FAILED |
| Stale event rejection after recovery | **PASS** | `_late_rejection_reason` (`engine_ingest.py:2078-2097`) 检查 `attempt.terminal_event_id IS NOT NULL` |
| Duplicate CONTEXT_COMPACTION_REQUESTED → stop worker | **PASS** | `engine_ingest.py:557-568` — `DUPLICATE` + `stop_worker_stream=True` |

**裁定: PASS。**

### 4.2 AG1: `_close_attempt_for_context_recovery` DUPLICATE 缺少 `stop_worker_stream`

**Severity: LOW**

**File:** `engine_ingest.py:1190-1197`

当 closeout 检测到 ATTEMPT_FAILED + RUN_RECOVERING 已存在（DUPLICATE），返回结果设置 `terminal_closeout=True` 但未设置 `stop_worker_stream=True`。

**实际影响:** `_consume_worker_events` (`dispatch.py:1815`) 使用 `terminal_closeout or stop_worker_stream` 判断，所以 worker 仍会被停止。语义不完整但不影响功能。

**建议:** 在 DUPLICATE 分支添加 `stop_worker_stream=True` 以与外部 `_duplicate_terminal_result` 的 `CONTEXT_COMPACTION_REQUESTED` 处理一致。

### 4.3 AG2: Reactive compact request 写入在 closeout CAS 之前

**Severity: LOW**

**File:** `engine_ingest.py:1051-1065`

`_append_reactive_compaction_requested_event` (line 1051) 在 `_close_attempt_for_context_recovery` (line 1058) 之前执行。两者在同一 SQLite write transaction 内，closeout CAS 在 `_invalid_terminal_precondition` 已通过的前提下不可能失败（单事务内无并发写入）。

**实际风险:** 极低（closeout CAS 失败仅可能在 DB 损坏时发生）。即使 CAS 失败触发 retry，orphaned `CONTEXT_COMPACTION_REQUESTED` 会消耗 compact count，导致 retry 时 hit compact limit → fail closed。

**建议:** 将 `_append_reactive_compaction_requested_event` 移到 closeout CAS 成功后（line 1064 之后），消除防御性缺口。优先级低于其他 findings。

### 4.4 `run_failed(context_compaction_required, recoverable=True)` 路径

**Severity: INFO**

**File:** `engine_ingest.py:664-690`

当 Engine 在 `context_compaction_requested` 之后发出 `run_failed(context_compaction_required, recoverable=True)`，Host 写 diagnostic event 并 fail-closed Run。此路径的 `unsupported_later_owner=_OWNER_PHASE10` 注释表明 Phase 10 应拥有此路径。

**分析:** 正常 Engine 流程中，`context_compaction_requested` 先到达（由 line 700-704 处理），recovery 在 line 700 的 branch 处理。`run_failed(recoverable=True)` 对非 context-compaction 的 recoverable failure（如 steer recovery，Phase 12）正确 fail-closed。行为正确，注释的 `_OWNER_PHASE10` 可能引起困惑。

---

## 5. Memory Projection 和 RunInputBuilder 验证

### 5.1 CONTEXT_COMPACTED → memory projection

| 检查项 | 状态 | 证据 |
|--------|------|------|
| `_EVENT_TYPE_FILTER` 包含 CONTEXT_COMPACTED | **PASS** | `durable/memory.py:74-79` |
| CONTEXT_COMPACTION_FAILED 排除在 filter 外 | **PASS** | 同上 |
| EPISODE_SUMMARY_ACCEPTED 已移除 | **PASS** | grep 全量零匹配 |
| Episode summary 从 `episode_summary_candidate` 提取 | **PASS** | `memory.py:2220-2242` — 优先级: `summary_text` → `summary` → deterministic assembly → fallback ref |
| Pinned state patch tri-state 语义 | **PASS** | `memory.py:1389-1434` — `missing`/`clear`/`replace` 三态正确实现 |
| `confirmed_subjects` 为 opaque ref 校验 | **PASS** | `memory.py:1519-1550` — 通过 `OpaqueMemoryRef` / `HostNeutralRefKind` 校验 |
| Snapshot + checkpoint 同事务原子写入 | **PASS** | `projection.py:540-613` — 同 transaction 内 `apply_event` → `advance_projection_checkpoint` |
| Checkpoint 晚于 snapshot（先写 snapshot 后推进 checkpoint） | **PASS** | 同上，`apply_event` (line 594) 先于 `advance_projection_checkpoint` (line 599) |

**裁定: PASS。**

### 5.2 AG3: `_bounded_patch_text` 在超预算时降级为 opaque ref

**Severity: LOW**

**File:** `memory.py:1581-1592`

当 patched text（`current_goal`、`user_constraints`、`open_questions`）超过 policy 的 `max_pinned_goal_chars` 等预算上限时，`_bounded_patch_text` fallback 到 `_ref_summary_text`，渲染为 `[ref sha256:abc123...]` 而非实际文本。LLM 将看到 opaque ref 而非可读内容。

**实际影响:** 仅在 extreme memory pressure 下触发（例如 goal text > 2048 chars）。这是一个有意的 budget 保护设计，但 opaque ref 对 LLM 不可读。Phase 13 Tool Trace 或 memory diagnostic 可能需要解释此降级。

### 5.3 DurableCompactArtifactProvider

| 检查项 | 状态 | 证据 |
|--------|------|------|
| 只暴露 artifact ref/digest + summary | **PASS** | `run_input.py:963-1004` — 返回 `CompactArtifactView`，不含内部 EventLog row |
| 按 attempt cursor 边界查询 | **PASS** | `run_input.py:1927` — `event_sequence < current_facts.attempt.started_event_sequence` |
| 不含 dropped raw ranges/pinned patch internals | **PASS** | SystemMessage 仅含 artifact ref、digest、preserved fact refs、episode summary |

**裁定: PASS。**

---

## 6. Production Composition Wiring 验证

| 检查项 | 状态 | 证据 |
|--------|------|------|
| `context_window_size`/`reserved_output_tokens` 必填无默认值 | **PASS** | `api.py:1172-1173` — `int` 无 default；`test_...require_explicit_budget_inputs` 验证 `MISSING` |
| `compose_host_local_execution_options` wiring | **PASS** | `command.py:276-301` — 从 explicit options → `default_context_budget_policy` → `HostLocalExecutionOptions.context_budget_policy` |
| Memory policy 独立 | **PASS** | `replace(...)` 只覆盖 context policy / artifact root，不碰 `memory_projection_policy` |
| Compactor 不默认注入 | **PASS** | 保留 `local_execution` 上已有的 compactor；production 不隐式使用 fake |
| 无 production Service caller | **ACCEPTED RESIDUAL** | S6 F1 residual，归后续 composition root owner |
| 无 production LLM compactor adapter | **ACCEPTED RESIDUAL** | S6 F3 residual，未配置时 fail closed |
| `promote_next_queued_run` legacy helper 仍存在 | **ACCEPTED RESIDUAL** | S4 residual，`admission.py:616`，production scheduler 通过 `wake_queue_promotion` governance gate |

**裁定: PASS。** 三个 controller-accepted residuals 均有明确 owner。

---

## 7. Multi-turn 闭环验证

### 7.1 S6 multi-turn aggregate test

`test_multi_turn_proactive_compact_feeds_subsequent_run_input` (`test_dispatch_scheduler.py:2084-2183`):

| 环节 | 验证方式 | 状态 |
|------|----------|------|
| Run 1-2 建立 prior raw turns | `_dispatch_accepted_final_run` → real scheduler dispatch | **PASS** |
| Run 2 Engine request 含 prior raw turn | `"first raw turn for memory" in second_contents` | **PASS** |
| Run 3 触发 soft threshold proactive compact | `"x" * 120` → estimate ≈52 tokens > soft threshold 50 | **PASS** |
| CONTEXT_COMPACTED 在 RUN_STARTED 之前 | `event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")` | **PASS** |
| Compact artifact 可在 Engine request 中查阅 | `"Accepted compact artifact is available for this run."` | **PASS** |
| Run 4 含 compacted memory: pinned state + raw turns + episode summary | `current_goal=`、`confirmed_subject=`、`title=Session`、`Memory episode summaries:` | **PASS** |
| Message ordering: goal < raw < episode < prompt | `goal_index < raw_index < episode_index` + `after_compact_contents[-1] == "after compact prompt"` | **PASS** |

**已知限制:** 测试使用 `_FinalAnswerWorker`（直接返回 final_answer），不经过 ToolRuntime accept barrier 与 verified fact 写入。完整业务工具 verified fact 链路由 `test_memory_projection.py` 和 `test_run_input_builder.py` 分层覆盖。

**裁定: PASS。** Multi-turn test 真实串起 scheduler gate → proactive compact → CONTEXT_COMPACTED → memory projection catch-up → subsequent Engine request memory 注入。

### 7.2 Phase 10 exit condition 验证

> "多轮会话主体必须可工作。后续 Run 的输入必须能解释 recent raw turns、older raw turns、episode summaries、pinned state、verified facts 的来源。"

| 数据来源 | 闭环链路 | 测试覆盖 |
|----------|----------|----------|
| **Recent raw turns** | EventLog → SessionContinuityProvider → RunInputBuilder | `test_run_input_builder.py` + multi-turn test |
| **Older raw turns** | EventLog → history pool budget → continuity | `test_run_input_builder.py` |
| **Episode summaries** | CONTEXT_COMPACTED → memory projection → `_compact_episode_summary_from_projection_event` → RunInputBuilder | `test_memory_projection.py` + multi-turn test |
| **Pinned state** | CONTEXT_COMPACTED → memory projection → `_apply_pinned_state_patch_candidate` → RunInputBuilder | `test_memory_projection.py` + multi-turn test |
| **Verified facts** | TOOL_RESULT_ACCEPTED → memory projection → verified_facts → RunInputBuilder | `test_memory_projection.py` |

**裁定: Phase 10 exit condition 已满足。** 五个数据来源的闭环链路完整，分层测试 + multi-turn aggregate test 足以证明。

---

## 8. 已知 Residual 复核

| Residual | Origin | 当前状态 | 裁决 |
|----------|--------|----------|------|
| Compactor 调用在 SQLite write transaction 内 | S4 | 未变。Fake compactor 同步调用无阻塞 | **ACCEPTED** — 真实 LLM compactor 接入前必须设计 fencing |
| Budget estimate 仅估算 display_text | S4 | 未变。`dispatch.py:570-580` | **ACCEPTED** — 归后续 tokenizer/sizing owner |
| `promote_next_queued_run` legacy helper | S4 | 未变。`admission.py:616` | **ACCEPTED** — production path 已走 governance gate |
| `_start_reactive_context_recovery` 方法较长 | S5 | 未变。约 125 行 | **ACCEPTED** — 职责清晰，未影响正确性 |
| `compose_host_local_execution_options` 无 production caller | S6 | 未变 | **ACCEPTED** — 归 composition root owner |
| production LLM compactor adapter 未实现 | S6 | 未变。未配置时 fail closed | **ACCEPTED** — 归 production compactor owner |
| Multi-turn test 未串完整 business tool E2E | S6 | 未变。分层测试覆盖 | **ACCEPTED** — 当前 multi-turn test + 分层 test 充分 |

**裁定: 所有 residual 仍可接受。** 无新增必须修复的 blocking issue。

---

## 9. 测试覆盖汇总

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_context_budget.py` | 20 | Budget policy / estimator / threshold decisions |
| `test_compaction_contract.py` | ~15 | Compactor protocol / fake compactor / quality check |
| `test_compact_artifact_store.py` | ~15 | Artifact write / digest / descriptor |
| `test_context_compact_events.py` | 15 | Payload builder/validator for 3 compact event types |
| `test_memory_projection.py` | ~25 | CONTEXT_COMPACTED → memory projection consumption / pinned state patch |
| `test_run_input_builder.py` | ~30 | DurableCompactArtifactProvider / memory snapshot / message ordering |
| `test_engine_ingest_mapping.py` | ~30 | Reactive recovery / stale rejection / budget_state=None / compact count |
| `test_run_attempt_transitions.py` | ~40 | ACCEPTED / RECOVERING / attempt-free failure transitions |
| `test_dispatch_scheduler.py` | ~50 | Proactive governance / reactive recovery / multi-turn aggregate |
| `test_phase5_local_execution_integration.py` | ~15 | Public scheduler + worker + Run lifecycle |
| `test_public_contracts.py` | 39 | Budget field isolation / composition wiring / required fields |
| `test_admission_queue.py` | ~25 | ACCEPTED queue policy / FIFO / cancel |

**总计: 约 300+ 测试，全部通过。**

---

## 10. README / 文档同步

| 文件 | 状态 | 证据 |
|------|------|------|
| `dayu/host/README.md` | **PASS** | context window/reserved 必填标注、composition data flow、budget/memory policy 分离、multi-turn compact 覆盖 |
| `tests/README.md` | **PASS** | 各个 context test 独立运行入口、覆盖类别标注 |
| `implementation-control.md` | **PASS** | Phase 10 slices/commits/residuals 完整记录 |
| `design.md` | **PASS** | Section 25 描述 Phase 10 设计 |
| `phase10-context-governance-plan.md` | **PASS** | 完整 plan artifact |

---

## Findings Summary

| ID | Severity | Category | File:Line | Owner |
|----|----------|----------|-----------|-------|
| AG1 | LOW | DUPLICATE 缺少 stop_worker_stream | engine_ingest.py:1190-1197 | Phase 10 S5 owner |
| AG2 | LOW | Reactive REQUESTED 在 closeout CAS 前写入 | engine_ingest.py:1051-1065 | Phase 10 S5 owner |
| AG3 | LOW | Budget 压力下 patch text 降级为 opaque ref | memory.py:1581-1592 | Phase 13 memory diagnostic owner |
| — | INFO | Redundant unique index `host_runs_one_accepted_per_session` | schema.py:817-821 | Schema owner |
| — | INFO | `_cancel_queued` 命名 (实际处理 ACCEPTED+QUEUED) | admission.py:1058 | Admission owner |
| — | INFO | `_invalid_terminal_precondition` 命名 (非 terminal 也用) | run_transition.py:4163 | Transition owner |
| — | RESIDUAL | Budget estimate scope | dispatch.py:570-580 | Tokenizer/sizing owner |
| — | RESIDUAL | Compactor in SQLite transaction | dispatch.py:856, engine_ingest.py:725 | Compactor owner |
| — | RESIDUAL | `promote_next_queued_run` legacy | admission.py:616 | Host API cleanup owner |
| — | RESIDUAL | No production composition root caller | command.py:276 | Composition root owner |
| — | RESIDUAL | No production LLM compactor adapter | — | Compactor owner |

**无 CRITICAL / HIGH / MEDIUM blocking issue。**

---

## Verdict

**PASS — Phase 10 已可进入 ready-to-open-draft-PR。**

Phase 10 完整实现了 plan 定义的六个 slice：Context Budget Policy (S1)、Compaction Contracts (S2)、Canonical Compact Events + P9 Memory Consumption (S3)、Proactive Governance (S4)、Reactive Recovery (S5)、Production Composition Wiring (S6)。

**设计目标达成:**
- Host-owned context budget policy ✓
- Proactive pre-start compaction ✓
- Reactive overflow recovery ✓
- Canonical compact artifact/event chain ✓
- P9 memory projection consumption of CONTEXT_COMPACTED ✓
- RunInputBuilder compact/memory provider ✓
- Production composition wiring ✓

**多轮会话闭环:**
- P9 stable layer / history pool 数据来源由 P10 compact event + EventLog projection 形成闭环 ✓
- 后续 Run 获得 pinned state / episode summaries / recent raw turns / verified facts ✓

**分层边界:**
- Engine 不拥有 Host budget/memory/recovery ✓
- Host 不从 Engine spec/metadata/payload/provider overflow 读取 budget truth ✓
- Context Governance 不直接写 memory snapshot ✓
- Projection 不成为 EventLog truth ✓

**状态机:**
- ACCEPTED → RUNNING / FAILED / CANCELLED ✓
- RECOVERING → RUNNING / FAILED ✓
- No LOST from compact failure ✓
- Cancel race CAS guarded ✓

**持久化与事件:**
- Schema v9 with ACCEPTED CHECK + active index ✓
- Strict payload validators for 3 compact event types ✓
- Artifact descriptor + digest ✓
- Projection catch-up within transaction ✓

**测试覆盖:**
- 300+ tests covering budget/compact/events/memory/projection/RunInputBuilder/governance/recovery/composition ✓
- Multi-turn aggregate test covering proactive compact → memory → Engine request ✓
- pyright 0 errors ✓

**7 个 known residual 均有明确 owner，不阻塞 PR。**

建议 PR 标题: `feat(host): add Phase 10 Context Governance and Compaction`
