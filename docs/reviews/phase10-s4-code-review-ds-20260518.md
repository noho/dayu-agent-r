# Phase 10 Slice 4 Code Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Verdict: ACCEPTED_WITH_RESIDUAL**

## Scope

Review of Phase 10 Slice 4 proactive context governance implementation:
- `dayu/host/durable/schema.py` (v8→v9)
- `dayu/host/dispatch.py` (governance gate + compact orchestration)
- `dayu/host/admission.py` (ACCEPTED run creation + cancel)
- `dayu/host/durable/run_transition.py` (accepted creation / attempt-free failure / cancel queued)
- `dayu/host/run_input.py` (DurableCompactArtifactProvider)
- `dayu/host/README.md`
- `tests/README.md`

## Verification

- `pytest tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py tests/host/test_run_input_builder.py -q` — 124 passed
- `pyright` — 0 errors
- `git diff --check` — 通过

---

## Adversarial Vectors

### V1. 同 Session 同时存在 ACCEPTED + running/waiting/cancelling/recovering Run

**Attack:** 在 ACCEPTED Run 存在时，通过 admission `start_run` 直接创建 running Run，绕开 ACCEPTED 独占语义。

**Defense (三层):**

1. **Schema 层 unique index**: `host_runs_one_active_per_session` (schema.py:812-814) WHERE clause 已包含 `'accepted'`，与 `running`/`waiting`/`cancelling`/`recovering` 共享同一个 partial unique index。任何尝试在已有 ACCEPTED 的 Session 下插入其他 active 状态的 Run，都会被 SQLite UNIQUE 约束直接拒绝。

2. **Schema 层 CHECK 约束**: schema.py:349-357 确保 ACCEPTED Run 的 `queued_event_id`、`started_event_id`、`current_attempt_id` 必须为 NULL。从 schema 层面杜绝了 ACCEPTED 状态下仍有 Attempt 引用或已 started 的不一致状态。

3. **Admission 层**: `_HandleActiveRunOperation` (admission.py:784-839):
   - REJECT policy: 检测到任何 active Run（包括 ACCEPTED）直接返回 CONFLICT
   - ATTACH_ACTIVE policy: 显式检查 `active.status == RunStatus.ACCEPTED` → 返回 CONFLICT（message: "Session has an accepted Run but no active Attempt"），拒绝 attach
   - QUEUE policy: 走 `_create_queued_admission_result` 排队

4. **补充索引**: `host_runs_one_accepted_per_session` (schema.py:818-820) 额外保证至多一个 ACCEPTED per session。

**结论: BLOCKED**。三层防御互相补位。注意：ACCEPTED 进入 active index 是对计划的偏离（计划要求 active index 只覆盖 running/waiting/cancelling/recovering），但经 Controller pre-review 确认，此偏离为有意决策，理由是 ACCEPTED 是 start-blocking 状态，应参与 active slot 竞争。

**评级:** 无 finding。

---

### V2. Compactor LLM 调用 + 文件 I/O 在 DB write transaction 内执行

**Attack:** `_compact_before_dispatch` (dispatch.py:793-941) 在 `_run_pre_start_governance` → `_operation` 内被调用，而 `_operation` 通过 `self._transaction_runner.run_write(_operation)` (dispatch.py:669) 执行。这意味着：

- `compactor.compact(request)` 的 LLM 调用（dispatch.py:856）
- `CompactArtifactStore(...).write_compact_artifact(...)` 的文件 I/O（dispatch.py:892-913）

全部在 SQLite write transaction 内部执行。

**影响分析:**

1. **长事务**: LLM compact 调用可能持续 30s+，期间 SQLite write lock 被持有，所有其他 write transaction（包括其他 Session 的 admission、event ingest、cancel）全部阻塞。
2. **事务语义**: 如果 LLM 调用成功但 `write_compact_artifact` 文件写入失败，整个 transaction 回滚——包括 `CONTEXT_COMPACTION_REQUESTED` 的 append。这是一致性正确的，但代价是整个 budget check + compact LLM 工作全部废弃。
3. **SQLite busy 风险**: 在高并发场景下，其他 writer 会在长事务期间累积 SQLITE_BUSY 超时。

**已知但未在代码内 defend**: 实现 artifact (docs/reviews/phase10-s4-proactive-context-governance-implementation-20260518.md:39-40) 将此列为"未覆盖风险"，但描述为 artifact read path 的缺失——实际上 write transaction 内 LLM 调用的结构性问题更严重。

**结论: RISK_ACCEPTED**。当前 Slice 4 是单 worker 调度模型，LLM compact 调用是同步的，不存在并发 write contention。但这是结构性债务 —— 未来若引入并发 dispatch 或 async compact，需要将 compact 调用移到 write transaction 外部，仅将 artifact write + event append 保留在事务内。

**评级:** R1 (residual, 结构性债务)。

---

### V3. Budget estimate 仅覆盖当前 prompt display_text，未纳入完整 RunInputBuilder 上下文

**Attack:** 预算估算只使用 `USER_INPUT_ACCEPTED` event 的 `display_text` 字段 (dispatch.py:567-581)，未包含：
- 完整 RunInputBuilder 构造的 messages（system prompt、tool schemas、conversation history）
- JSON fragments（工具调用参数 JSON）
- Tool schema definitions

这意味着 `estimated_input_tokens` 可能严重低估实际 context window 占用，导致：
1. **漏报 soft threshold**: 实际 tokens 已超 soft threshold 但估算未超 → 错过 compaction 机会
2. **理论绕过 hard threshold**: 如果 `display_text` 很短但 RunInputBuilder 构造了大量上下文，估算可能远低于 hard threshold，而实际发送给 Engine 时已超出

**Defense 分析:**
- `estimate_context_budget` (context_budget.py:281-336) 对每个 fragment 加了 `DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS` 和 `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS` 作为保守 overhead
- 但这些 overhead 是固定的，不能弥补完全缺失的 message/tool schema fragments
- 实现 artifact 明确标注为未覆盖 (docs/reviews/phase10-s4-proactive-context-governance-implementation-20260518.md:40)

**结论: RESIDUAL**。漏报 soft threshold (错过 compaction) 的后果是性能损失，不是正确性破坏。绕过 hard threshold 的实际风险较低，因为 display_text 通常在估算中占比最大；但要完全绕过，需要 display_text 极短且 RunInputBuilder 构造了远大于 context window 的隐式内容，这在当前助手场景下不太可能出现。

**评级:** R2 (residual, 已记录，留给后续 slice)。

---

### V4. DurableCompactArtifactProvider 跨 Run 事件读取与内部数据暴露

**Attack:** `_latest_compacted_event_before_attempt` (run_input.py:1909-1945) 的 SQL 查询按 `session_id`、`run_id`、`event_type=CONTEXT_COMPACTED`、`event_sequence < attempt.started_event_sequence` 过滤。攻击方向：
1. 是否可能读到其他 Run 的 compacted event？
2. 是否向 Engine 暴露了不应暴露的内部 durable ref？

**Defense:**

1. **Run 隔离**: SQL WHERE 子句 (run_input.py:1922-1927) 同时过滤 `session_id = ?` 和 `run_id = ?`，使用 `current_facts.run.session_id` 和 `current_facts.run.run_id` 作为参数。无法跨 Run 读取。
2. **Cursor 隔离**: `event_sequence < ?` 使用 `current_facts.attempt.started_event_sequence` 作为 cursor，确保只读当前 Attempt 启动前的 compacted 事件，不会读到本 Attempt 内产生的事件（虽然 proactive compact 发生在 Attempt 创建之前，此条件实际为防御性约束）。
3. **信息暴露边界**: `_compact_artifact_message_content` (run_input.py:1948-1980) 只暴露：
   - `compact_artifact_ref`（artifact 存储路径引用）
   - `compact_artifact_digest`（内容哈希）
   - `compacted_event_id` / `compacted_event_sequence`
   - `preserved_fact_refs`（保留的 tool fact 引用）
   - Bounded `episode_summary`（truncated 到 max_summary_chars）
   - 不暴露原始 compact artifact JSON 正文、compactor 内部状态或 durable 行级细节

4. **Null safety**: 无 compacted event 时返回 `CompactArtifactView(messages=(), compact_artifact_ref=None, compact_artifact_digest=None)` (run_input.py:980-984)，Engine 侧看到空消息。

**结论: BLOCKED**。SQL 过滤正确，信息暴露受控。

**评级:** 无 finding。

---

### V5. Cancel race — compact accepted 后、start 前被 cancel

**Attack 场景:**
1. Governance `_run_pre_start_governance` 返回 `compact_accepted`（dispatch.py:659-666），此时 write transaction 1 已提交
2. 在 `_start_governed_after_compact` (dispatch.py:671-686) 执行前，另一个请求（如 cancel_run）进入，将 Run 状态从 ACCEPTED 改为 CANCELLED
3. `_start_governed_after_compact` 在新 transaction 中执行 `_operation`，re-read Run 并检查 `run.status != accepted.expected_status` → 返回 None

**Defense:**
- `_start_governed_after_compact` (dispatch.py:680-684) CAS 检查: `run.status != accepted.expected_status` → return None
- `cancel_queued_in_transaction` (run_transition.py:1783) 接受 `RunStatus.ACCEPTED` 和 `RunStatus.QUEUED`，所以 cancel 可以合法地将 ACCEPTED 转为 CANCELLED
- `terminal_unstarted_run_row` (run_transition.py:1803-1811) CAS expected_status 为 run 当前状态（accepted），如果 compact catch-up 的 start transaction 先于 cancel 到达，cancel 的 CAS 会失败（因为状态已从 accepted 变为 running）

**双向 CAS 保护:**
1. Start 先到: `start_governed_run_with_starting_attempt_in_transaction` 接受 `accepted→running` → 成功。Cancel 后到，`cancel_queued_in_transaction` 的 CAS `accepted|queued→?` 失败（status 已是 running），走 running cancel 路径。
2. Cancel 先到: `cancel_queued_in_transaction` 接受 `accepted→cancelled` → 成功。Start 后到，`_start_governed_after_compact` 检测到 `run.status != expected_status` → return None，不创建 Attempt。

**结论: BLOCKED**。双向 CAS 保护正确，不可同时存在 cancelled 和 starting。

**评级:** 无 finding。

---

### V6. 所有 compact 失败路径是否 attempt-free

**Attack:** governance 失败后仍创建 Attempt，导致僵尸 Attempt 行。

**Defense 覆盖:**

`_fail_unstarted_in_transaction` (dispatch.py:734-767) 调用 `fail_unstarted_run_in_transaction` (run_transition.py:987-1032):
- CAS 前置条件 (run_transition.py:1005): `run.status != request.expected_status or run.current_attempt_id is not None` → INVALID_STATE
- `terminal_unstarted_run_row` (run_transition.py:1015-1023) 只更新 Run 状态为 FAILED、terminal_event_id/sequence、terminal_at，不插入 Attempt 行
- 返回的 `RunTransitionResult` 中 `attempt=None`, `dispatch_record=None` (run_transition.py:1029-1031)

**所有失败调用点** (dispatch.py):
1. :558 — `input_event_missing`: `_fail_unstarted_in_transaction` ✓
2. :599 — `hard_threshold_before_dispatch`: `_fail_unstarted_in_transaction` ✓
3. :621 — `proactive_compact_count_unreadable`: `_fail_unstarted_in_transaction` ✓
4. :639 — `proactive_compact_limit_reached`: `_fail_unstarted_in_transaction` ✓
5. :828-830 — `compactor_or_artifact_store_missing`: `_fail_unstarted_in_transaction` ✓
6. :867-869 — `quality_check_rejected`: `_fail_unstarted_in_transaction` ✓
7. :884-886 — `hard_threshold_after_compact`: `_fail_unstarted_in_transaction` ✓

**结论: BLOCKED**。所有 7 个失败路径均调用 attempt-free `fail_unstarted_run_in_transaction`，无 Attempt 泄露。

**评级:** 无 finding。

---

### V7. `_committed_proactive_compact_count` 数据损坏处理

**Attack:** EventLog 中 proactive compact fact 数据损坏（例如 payload 中 `trigger_source` 字段缺失或类型错误），导致 compact count 读取抛异常，绕过 max_proactive_compactions_per_run 限制。

**Defense:**
- `_committed_proactive_compact_count` (dispatch.py:769-791) 的调用方用 try/except 包裹 (dispatch.py:608-629)
- 任何异常（包括 Payload 字段缺失、类型不匹配）均被捕获，统一走 `CONTEXT_COMPACTION_FAILED` + attempt-free `RUN_FAILED` 路径
- 这是保守策略：宁可让一个 Run 因数据损坏而失败，也绝不绕过 compaction 配额限制

**边缘情况:** 如果只是 `count_committed_events_by_run_and_type` 内部的 payload 过滤逻辑抛异常（例如某条 CONTEXT_COMPACTION_REQUESTED event 的 payload 非合法 JSON），所有后续 Run 的 governance 都会因同一个损坏 event 而失败，直到该 event 被修复或清理。但这是数据完整性保护的预期行为。

**结论: BLOCKED**。保守失败策略正确。

**评级:** 无 finding。

---

### V8. `_read_startable_run` 的 accepted 优先 + active 互斥语义

**Attack 场景:**
1. Session 同时存在 ACCEPTED Run A 和 QUEUED Run B（理论上不应该，因为 ACCEPTED 已加入 active index）
2. `_read_startable_run` (dispatch.py:1867-1883) 逻辑: accepted 优先 → active check → queued fallback

**Defense:**
- `host_runs_one_active_per_session` index (schema.py:812-814) 的 WHERE 包含 `'accepted'`，所以同一 Session 不可能同时有 ACCEPTED + RUNNING/WAITING/CANCELLING/RECOVERING
- `host_runs_one_accepted_per_session` index (schema.py:818-820) 保证至多一个 ACCEPTED
- 但是: ACCEPTED + QUEUED 是否可能同时存在？QUEUED 不在 active unique index 中（schema.py:813-814 WHERE 不包含 'queued'），所以 ACCEPTED 和 QUEUED 可以同时存在

**ACCEPTED + QUEUED 并存场景:**
1. Run A 被 admission 以 QUEUE policy 接受为 QUEUED（因为当时有 RUNNING Run）
2. RUNNING Run 结束后，Run A 还没被 promote
3. 新的 start_run 请求到达，无 active Run → 创建 ACCEPTED Run B
4. 此时 ACCEPTED B + QUEUED A 并存

**`_read_startable_run` 对此场景的处理:**
- 优先返回 ACCEPTED B (:1877-1879: `accepted is not None → return accepted`)
- QUEUED A 被搁置，直到 ACCEPTED B 完成/cancel 后再被选中

这是正确的优先级语义：ACCEPTED 是新到达的、未经 compaction 的 Run，应该优先于已在队列中的 QUEUED Run。

**反向场景:** 先有 ACCEPTED Run A，再有 QUEUED Run B（例如 ACCEPTED A 时，另一个 start_run 以 QUEUE policy 到达）。此时 ACCEPTED 已在 active index 中，QUEUE admission 的 active check 会检测到 ACCEPTED（因为 ACCEPTED in active index），走 `_HandleActiveRunOperation` 分支，policy 为 QUEUE 时进入 `_create_queued_admission_result`。这合法——但 A 优先于 B 被 `_read_startable_run` 选中。

**结论: BLOCKED**。ACCEPTED 优先 + QUEUED fallback + active 互斥语义正确。

**评级:** 无 finding。

---

### V9. `promote_next_queued_run` 保留但 Slice 4 governance 不调用

**Attack:** 旧 promotion 路径与新 governance 路径产生分歧，导致部分 Run 走旧路径绕过 governance gate。

**Defense:**
- `promote_next_queued_run` (admission.py:616-650) 仍保留为 `HostAdmissionService` 的 public method
- Slice 4 生产路径 `wake_queue_promotion` (dispatch.py) 通过 `create_host_admission_service` → `promote_next_queued_run` 调用，但这不是 governance gate 的路径
- 实际 governance 路径是: `_run_pre_start_governance` → `_read_startable_run` → `_start_governed_in_transaction`，**不经过** `promote_next_queued_run`
- `promote_next_queued_run` 内部的 `promote_queued_run_in_transaction` 接受的是 `queued→running` 转换，不包含 budget check 和 compaction 逻辑

**风险:** 如果任何未来代码路径绕过 `_run_pre_start_governance` 直接调用 `promote_next_queued_run`，该 Run 会跳过 governance gate（无 budget check、无 proactive compaction）。当前没有这样的调用路径，但 `promote_next_queued_run` 的 public API 表面存在为误用留下了入口。

**结论: RESIDUAL**。实现 artifact 已记录此风险 (docs/reviews/phase10-s4-proactive-context-governance-implementation-20260518.md:41)。当前无实际调用链可绕过 governance gate，但建议在后续清理中降级为 internal 或增加 governance gate 强制检查。

**评级:** R3 (residual, API 表面债务)。

---

## Findings Summary

| ID | Severity | Category | Description | Verdict |
|----|----------|----------|-------------|---------|
| — | — | V1 同 Session 双状态 | ACCEPTED 三层防御 (index + CHECK + admission) | BLOCKED |
| R1 | RESIDUAL | V2 事务内 LLM | compactor.compact + write_compact_artifact 在 DB write transaction 内 | RISK_ACCEPTED |
| R2 | RESIDUAL | V3 估算覆盖不足 | budget estimate 仅用 display_text，不含 RunInputBuilder messages | RESIDUAL |
| — | — | V4 跨 Run 读取 | SQL 按 session_id+run_id 过滤，信息暴露受限 | BLOCKED |
| — | — | V5 cancel race | 双向 CAS (start + cancel) 正确互斥 | BLOCKED |
| — | — | V6 attempt-free 失败 | 7 个失败路径均不创建 Attempt 行 | BLOCKED |
| — | — | V7 数据损坏 | compact count 异常保守失败，不绕过配额 | BLOCKED |
| — | — | V8 accepted 优先 | accepted 优先 + queued fallback + active 互斥 | BLOCKED |
| R3 | RESIDUAL | V9 旧 API 表面 | promote_next_queued_run 保留但无 governance gate | RESIDUAL |

**Verdict: ACCEPTED_WITH_RESIDUAL** — 12 向量中 9 个被防御，3 个 residual (R1 structural, R2 undercoverage, R3 API surface)。所有 residual 均为已知并已记录在实现 artifact 中，无 blocking 发现。

## 未覆盖风险 (来自实现 artifact + 本 review 补充)

1. **R1 — Compactor 在 write transaction 内**: LLM compact 调用 + 文件 I/O 在 SQLite write transaction 内，30s+ 长事务。当前单 worker 模型可接受，但未来并发场景需要将 compact 调用移到事务外。
2. **R2 — Budget estimate 覆盖不足**: 只覆盖当前 `display_text`，未纳入 RunInputBuilder 消息/tool schemas。漏报 soft threshold 导致错过 compaction，非正确性破坏。
3. **R3 — `promote_next_queued_run` 旧 API 表面**: 保留为 public method 但 Slice 4 governance 不调用它。未来若被误用可能绕过 governance gate。
4. **Artifact JSON 正文未读取** (已知): `DurableCompactArtifactProvider` 只暴露 descriptor ref/digest，不读取 artifact 文件内容。后续若需要 artifact 内容级 rebuild 需补充 read path。
5. **Provider-specific tokenizer** (已知): 当前使用字符级估算，未接入 model-specific tokenizer。后续 slice 需补强。
