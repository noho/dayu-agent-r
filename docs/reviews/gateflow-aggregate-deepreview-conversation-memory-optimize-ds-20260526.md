# Aggregate Deepreview — Conversation Memory Optimize

- **Date**: 2026-05-26
- **Branch**: `feat/phase-12-5-conversation-memory-optimize`
- **Base**: `main`
- **Diff scope**: 277 files, +44870 / -2143 lines
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Prior aggregate reviews**:
  - `docs/reviews/phase12-5-aggregate-deepreview-ds-20260522.md` (Phase 12.5, 3 blocking)
  - `docs/reviews/p12-6-aggregate-deepreview-ds-20260524.md` (Phase 12.6, PASS with 1 MEDIUM)
- **Smoke slice reviews**:
  - `docs/reviews/gateflow-code-review-conversation-memory-smoke-ds-20260526.md` (PASS)
  - `docs/reviews/gateflow-code-review-conversation-memory-smoke-mimo-20260526.md` (PASS)
- **Parallel review coverage**: 5 subagents covering evidence/compaction, state machine/dispatch, memory projection, architecture boundaries, ToolRuntime/ingest. Each subagent traced real code paths with evidence-based findings. Main reviewer independently verified all prior CRITICAL/HIGH finding fixes and adjudicated subagent findings.

---

## Verdict: PASS

No blocking findings. All 3 prior CRITICAL/HIGH Phase 12.5 blocking findings are verified fixed. The smoke commit (cc0b452) is public-API-only and introduces no regressions. 2 new MEDIUM findings (text policy divergence — deferred from P12.5; multi-pass attempt counter starvation — new), 10 LOW observations. No CRITICAL or HIGH findings. Prior accepted residual risks remain non-blocking.

---

## Phase 12.5 Blocking Finding Fix Verification

### Fix 1 [曾 CRITICAL] — Evidence 内容现已流入 LLM compactor prompt

**Phase 12.5 Finding**: `_user_prompt()` 只传递不透明 evidence refs，LLM 看不到 tool result 内容，evidence_backed_facts 实质依赖幻觉生成。

**Fix verified**. 证据链路：

1. `CompactEvidenceBlock` (`compaction.py:400-460`) 现包含 `readable_tool_name`、`readable_query_text`、`raw_result_text`、`readable_source_text` 四个字段，均为实际 evidence 内容。
2. `CompactEvidenceBlock.llm_json()` (`compaction.py:485`) 将上述字段全部暴露给 LLM。
3. `CompactMaterialPack.llm_json()` (`compaction.py:795-805`) 聚合四个 section（stable/history/evidence/current_input_anchor），都通过各自 `llm_json()` 输出。
4. `CompactionRequest.llm_material_json()` (`compaction.py:946-952`) 调用 `self.material_pack.llm_json()`。
5. `_compaction_request_prompt_block()` (`llm_compaction.py:382-398`) 对 `request.llm_material_json()` 做 `json.dumps()` 后注入 user prompt。
6. Compactor scene prompt (`conversation_compaction.md:10`) 明确要求 "evidence-backed fact 只能引用 `evidence_input` 中已经给出的 prompt-local evidence labels"。

旧 `CompactionRequest.accepted_evidence_envelopes` 字段已从 `compaction.py` 完全移除（grep 确认零引用）。

**验证人**: 主 reviewer 沿 `CompactEvidenceBlock → llm_json() → CompactMaterialPack.llm_json() → CompactionRequest.llm_material_json() → _compaction_request_prompt_block()` 完整链路走读确认。

### Fix 2 [曾 CRITICAL] — Memory projection lag 不再触发 Run→FAILED

**Phase 12.5 Finding**: `SNAPSHOT_LAG_OVER_THRESHOLD` 与 `SNAPSHOT_DAMAGED`/`SNAPSHOT_MISSING` 统一走 terminal closeout，导致可恢复投影滞后误杀业务 Run。

**Fix verified**. 证据：

1. `dispatch.py:2281-2293` — `_build_run_input_with_lag_repair()` 中 `MemoryProjectionRepairRequired` 被 catch，当 `reason is SNAPSHOT_LAG_OVER_THRESHOLD` 时走 lag rebuild retry，不触发 closeout。
2. `dispatch.py:2423-2435` — 非 lag reason 才 re-raise；lag reason 触发 warning + rebuild。
3. `dispatch.py:2560-2576` — `_catch_up_memory_projection_before_worker()` 现检查 `result.failures == 0`；failures > 0 时触发 `rebuild_conversation_memory_projection()`。

**验证人**: 主 reviewer 沿 `_catch_up_memory_projection_before_worker → _build_run_input_with_lag_repair → _safe_closeout_worker_startup_timeout` 分支走读确认。

### Fix 3 [曾 HIGH] — FakeContextCompactor 现从 material JSON 消费 evidence 内容

**Phase 12.5 Finding**: FakeCompactor 仅遍历 `accepted_evidence_refs` 字符串列表构造 fact candidates，绕过证据提取链。

**Fix verified**. 证据：

1. `fake_compaction.py:60-61` — `FakeContextCompactor.compact()` 调用 `fake_compaction_proposal_from_material_json(_json_object(request.llm_material_json(), ...))`，从 LLM-facing material JSON 读取 evidence 内容。
2. `fake_compaction.py:283-310` — `_fact_candidate_json()` 从 material JSON 的 `evidence_input` section 读取每个 block 的 `result_text`（line 300），并用 `f"Canonical evidence material: {raw_result}"` 构造 claim_text（line 304）。
3. 此路径与真实 `LLMContextCompactor` 共享相同的 `_candidate_from_final_answer()` 解析器（line 63）。

**验证人**: 主 reviewer 沿 `FakeContextCompactor.compact() → fake_compaction_proposal_from_material_json() → _fact_candidate_json()` 完整链路走读确认。

### Fix 4 [曾 HIGH] — catch-up projection failure 现被显式检测并触发 rebuild

**Phase 12.5 Finding**: `_catch_up_memory_projection_before_worker` 不检查 catch_up 返回值，failure 被静默忽略后由 lag check 误诊。

**Fix verified**. 证据：

- `dispatch.py:2560-2576` — `result.failures == 0` 时正常返回；failures > 0 时 log warning 并调用 `rebuild_conversation_memory_projection()`。

### Fix 5 [曾 HIGH] — EvidenceBackedFactView 现校验 claim_text 长度

**Phase 12.5 Finding**: `__post_init__` 仅校验非空，不校验长度上限。

**Fix verified**. 证据：

- `memory.py:430-431` — `if len(self.claim_text) > MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS: raise ValueError(...)`

### Fix 6 [曾 MEDIUM] — open_questions 现使用归一化去重

**Phase 12.5 Finding**: open_questions 仅精确匹配去重。

**Fix verified**. 证据：

- `memory.py:386` — `_dedupe_text_tuple_by_normalized_text(self.open_questions)` 在 `PinnedStateView.__post_init__` 中调用。

### Fix 7 [曾 MEDIUM] — working_assumptions 现使用归一化去重

**Phase 12.5 Finding**: working_assumptions 完全无去重。

**Fix verified**. 证据：

- `memory.py:2626-2649` — `_dedupe_working_assumptions_by_normalized_summary()` 使用 `_normalized_text()` 按 assumption_summary 去重，保留 EventLog sequence 更新的 view。

---

## New Findings

### Finding 1 [MEDIUM] — `_payload_with_terminal_summary` 双实现仍存在 text policy 分歧

- **入口/函数**: `_payload_with_terminal_summary` (两处独立实现)
- **文件(行号)**: `dayu/host/durable/memory.py:212` vs `dayu/host/run_input.py:2496`
- **输入场景**: 同一 `RUN_SUCCEEDED` EventLog row 被两个路径消费。
- **实际分支**: durable path (line 228) 使用 `PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY`；inline delta path (run_input.py:2513) 使用 `PayloadSummaryTextPolicy.STRICT_NON_EMPTY`。
- **预期行为**: 相同 EventLog row 应产生一致的 assistant conclusion item。
- **实际行为**: 空字符串 terminal summary 在 durable path 被接受为有效内容，在 inline delta path 被判定为 None 并 fall through 到 terminal_summary_ref 解析路径。
- **直接证据**: 对比 `durable/memory.py:228` (`STRICT_ALLOW_EMPTY`) 与 `run_input.py:2513` (`STRICT_NON_EMPTY`)。
- **影响**: 同一 Run 的不同 Attempt 可能看到不同的 continuity 内容。低概率触发，需 terminal summary 恰好为空字符串。
- **建议改法和验证点**: 统一为同一 text policy（建议 `STRICT_ALLOW_EMPTY`，语义更保守），或抽取共享 `_payload_with_terminal_summary` 函数到公共模块。
- **修复风险**: 低
- **严重程度**: 中 — 已在 Phase 12.5 标记为 MEDIUM，未被 P12.6 修复。行为分歧跨两个独立模块，后续维护容易遗忘。

### Finding 2 [LOW] — Reactive path 非 RECOVERING 丢弃仍无 diagnostic

- **入口/函数**: `_execute_reactive_compaction` 内部 transaction
- **文件(行号)**: `dayu/host/engine_ingest.py:1515-1519`
- **输入场景**: compact operation 完成后 Run 已被并发进程改为非 RECOVERING。
- **实际分支**: `latest.run.status is not RunStatus.RECOVERING` → 直接返回 `pending.result_prefix`，无 `CONTEXT_COMPACTION_FAILED` 写入。
- **影响**: 极端边界情况，不导致数据损坏。已在 P12.6 aggregate review 标记为 LOW，控制器接受。
- **严重程度**: 低

### Finding 3 [LOW] — `_compact_pressure_reserve_tokens` 死分支

- **入口/函数**: `_compact_pressure_reserve_tokens`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory.py:1089-1099`
- **输入场景**: 任意 `context_window_size` 值。
- **实际分支**: if/else 两个分支均返回 `_COMPACT_PRESSURE_RESERVE_TOKENS`（8192）。
- **影响**: 对当前目标模型（大窗口）无实际影响。已在 smoke code review 标记为 LOW。
- **严重程度**: 低

### Finding 4 [LOW] — `_compact_pressure_padding` 被重复调用

- **入口/函数**: `_print_compact_pressure_plan` / `_round2_prompt`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory.py:1040, 1354`
- **输入场景**: Round 2 执行时。
- **实际分支**: 两次调用 `_compact_pressure_padding(options)` 构造相同的压力文本。
- **影响**: 微小性能开销，不导致行为差异。已在 smoke code review 标记为 LOW。
- **严重程度**: 低

### Finding 6 [MEDIUM] — Multi-pass compaction operation attempt counter 跨 pass 共享导致后期 pass 被饿死

- **入口/函数**: `run_compaction_operation`
- **文件(行号)**: `dayu/host/compaction_operation.py:126-129, 246`
- **输入场景**: `_reactive_compaction_pass_queue` 构造多 pass 队列（`len(selected_block_ids) > 1`），且较早 pass 消耗了全部 attempt 预算。
- **实际分支**: `attempt_number` 在 line 126 初始化为 1，跨所有 pass 共享递增（line 185/213/242/246）。若 pass 1 在 `attempt_number=3` 时成功（`max_attempts=3`），line 246 将 `attempt_number` 递增到 4。pass 2 的 while 条件 `4 <= 3` 立即为 False，`pass_accepted` 保持 False，line 247-254 返回 `_FAILURE_MAX_ATTEMPTS_EXHAUSTED`。
- **预期行为**: 每个 pass 应有独立的 attempt 预算，或至少区分 "本 pass 从未尝试" 与 "本 pass 耗尽尝试"。
- **实际行为**: pass 2 被静默跳过，无 diagnostic 区分 "pass never attempted due to shared counter exhaustion" 与 "pass exhausted own attempts"。
- **直接证据**: 
  1. `compaction_operation.py:126` — `attempt_number = 1` 在 pass 循环外初始化
  2. `compaction_operation.py:129` — `while attempt_number <= max_attempts and not pass_accepted` 跨 pass 共享
  3. `compaction_operation.py:246` — pass 成功后仍递增 `attempt_number += 1`
  4. `engine_ingest.py:3059-3088` — 多 pass 队列在生产代码中使用
- **影响**: 多 block 的 reactive compaction 可能在 pass 2+ 被饿死，导致部分 material block 的 compaction 结果丢失。此 bug 仅在 `max_compaction_attempts_per_operation` 较小且 pass 1 经历多次重试后成功时触发。
- **建议改法和验证点**: 每个 pass 重置 `attempt_number` 为 1，或将 `max_attempts` 定义为 per-pass 上限；同时当 pass 被跳过时添加 diagnostic `rejected_attempt` 记录。
- **修复风险**: 低 — 循环重构仅影响 compaction_operation.py 内部
- **严重程度**: 中 — 真实可触发的功能缺陷，但触发条件需要多 pass + pass 1 经历重试

### Finding 7 [LOW] — `_readable_query_text` 仅输出 `tool_call_id`，query 内容对 LLM 不可读

- **入口/函数**: `_readable_query_text`
- **文件(行号)**: `dayu/host/compaction_evidence.py:266`
- **输入场景**: 构造 `InitialEvidenceMaterial` 时。
- **实际分支**: 返回 `f"tool_call_id={envelope.tool_call_id}"`。envelope 的 `normalized_arguments_digest` 是 SHA-256 hash，不包含可读参数。
- **影响**: LLM 在 compaction prompt 中看到的 `query_text` 字段仅包含不透明 tool_call_id，无法从中理解工具查询语义。LLM 仍然可以从 `tool_name` + `result_text` 推断上下文，但 query_text 字段未提供额外信号。
- **严重程度**: 低 — tool_name + result_text 通常足够；query 参数可通过 normalized_arguments 重建但非当前设计目标

### Finding 8 [LOW] — `PinnedStateView.confirmed_subjects` 缺少去重校验

- **入口/函数**: `PinnedStateView.__post_init__`
- **文件(行号)**: `dayu/host/memory.py:369, 373-387`
- **输入场景**: 构造 `PinnedStateView` 时。
- **实际分支**: `current_goal`、`user_constraints`、`open_questions` 均有去重校验，但 `confirmed_subjects` tuple 允许重复 `OpaqueMemoryRef` 条目。
- **影响**: 重复 subject 会在 prompt 渲染中产生重复行（`run_input.py:2019-2020`），轻微浪费上下文预算。
- **严重程度**: 低

### Finding 9 [LOW] — Proactive compaction 取消未接入 scheduler close

- **入口/函数**: `_execute_proactive_compaction` / `LocalDispatchScheduler.close`
- **文件(行号)**: `dayu/host/dispatch.py:1137, 1741-1780`
- **输入场景**: scheduler close 时 proactive compaction 正在执行。
- **实际分支**: proactive compaction 使用 `_DurableRunCancellationToken`（仅观察 durable Run state），而 `close()` 的 `cancel_all()` 仅作用于 `_HostCancellationToken` entries。close() 返回前不等待 in-flight proactive compaction 终止。
- **影响**: 实践中 benign — proactive compaction 在下一次 loop iteration 检查 durable Run state 时会自然终止。但 close() 不保证所有在途操作完全终止。
- **严重程度**: 低

### Finding 10 [LOW] — EvidenceBackedFactCandidate.__post_init__ 不校验 evidence_refs 格式

- **入口/函数**: `EvidenceBackedFactCandidate.__post_init__`
- **文件(行号)**: `dayu/host/compaction.py:767-772`
- **输入场景**: 构造 candidate 时传入非 evidence 格式字符串。
- **实际分支**: 仅调用 `_require_bounded_string_tuple`，不校验前缀格式。
- **影响**: 两层后续防线（quality check + payload validator）保护正常路径。已在 Phase 12.5 标记为 MEDIUM，P12.6 控制器接受为 deferred。
- **严重程度**: 低

### Finding 11 [LOW] — Evidence chunking 无 record 边界感知

- **入口/函数**: `_evidence_chunks`
- **文件(行号)**: `dayu/host/compact_material.py:1686`
- **输入场景**: 单个 evidence result 文本超过 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` (4096)。
- **实际分支**: `text[start : start + EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS]` 在固定字节数处切割，不感知 JSON record 或行边界。
- **影响**: 结构化 JSON evidence 可能在 mid-record 处被截断。对纯文本 evidence 无影响。
- **严重程度**: 低

### Finding 12 [LOW] — Hot/cold payload hot path 省略 `payload_digest`

- **入口/函数**: `_tool_result_payload_plan`
- **文件(行号)**: `dayu/host/tool_runtime.py:3636-3644`
- **输入场景**: cold-storage 分支构造 hot inline payload 时。
- **实际分支**: `evidence_payload_digest=None`，尽管 `descriptor.payload_digest` 已计算完成。
- **影响**: consumer 需额外 descriptor resolution round-trip 获取 digest。微小性能开销，不导致正确性问题。
- **严重程度**: 低

---

## Architecture & Boundary Verification

### 分层架构 — PASS

- `dayu/host/` 零 import `dayu/service/`、`dayu/ui/`、`dayu/fins/`
- `dayu/engine/` 零 import `dayu/host/`、`dayu/service/`
- `dayu/runtime/` 零 import `dayu/engine/`、`dayu/host/`、`dayu/service/`、`dayu/ui/`、`dayu/fins/`
- `dayu/host/__init__.py` 公开导出无内部实现泄漏
- 无 `hasattr`/`getattr` 在变更代码中
- 无兼容性 re-export 或 wrapper/facade
- 旧 `collect_compaction_request_evidence_inputs` (Session range 读取) 已移除，替换为 `collect_selected_compaction_request_evidence_inputs` (selected refs 读取)

### 状态机安全 — PASS

- Proactive compaction: dispatch 前执行，不创建 Attempt；失败 Run→FAILED
- Reactive compaction: 校验 attempt_id + execution_id → 关闭 Attempt → Run→RECOVERING → compact → 新 Attempt
- Multi-pass: 中间产物 transient in-memory，最终提交单个 merged `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`
- Stale/cancelled/cursor-mismatch: 正确丢弃 stale proposal，不写 `CONTEXT_COMPACTED`
- `SNAPSHOT_LAG_OVER_THRESHOLD` 触发 rebuild retry，不再误杀 Run
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 作为 `EventClass.CANONICAL_FACT` 写入
- 所有 compact 事件通过 `EventLog.append_event()` 写入，不绕过 EventLog

### Memory 正确性 — PASS

- Memory projection 只消费 committed canonical EventLog facts
- Pinned state 渲染当前值，tri-state patch (MISSING/CLEAR/REPLACE) 应用后丢弃
- Evidence-backed facts 只来自 CONTEXT_COMPACTED payload 的 fact candidates
- Fact dedup: `(normalized claim_text, sorted evidence_refs, evidence_kind)` key
- `EvidenceBackedFactView.__post_init__` 现校验 claim_text 长度上限
- `open_questions` 使用 `_normalized_text()` 去重
- `working_assumptions` 使用 `_dedupe_working_assumptions_by_normalized_summary()` 去重
- Snapshot cursor 校验: lag ≤ threshold → inline delta repair; lag > threshold → rebuild
- Snapshot digest 强制校验
- `FINAL_ANSWER` 不自动升级为 evidence_backed_fact

### ToolRuntime / Ingest — PASS

- ToolRuntime accept barrier 正确构造 `AcceptedEvidenceEnvelope`（含 evidence_id, tool_name, tool_query, result_ref）
- Hot/cold payload 处理正确
- `result_preview` 被 fail-closed 拒绝
- Engine ingest 正确分类 EngineEvent → Host event
- Reactive compact trigger 路径完整：Engine context_compaction_requested → Host ingest → closeout → compact → new Attempt
- Compaction operation 状态机正确：PENDING → IN_PROGRESS → COMPLETED/FAILED
- Usage event 缺失不导致 Run 失败

### Smoke 实现 — PASS

- 严格 public API only: `open_host`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session`、`get_run`
- 无 durable store / EventLog / memory table 直接访问
- Anti-cheat: 无 context slot 注入、无 scene prompt 泄露、被测公司仅出现在合法位置
- Mock tool session-scoped 计数防止 recovery 污染
- 断言分层正确：硬断言聚焦关键路径，soft observation 覆盖观测项
- Pressure 校准遵循 additive 原则

### 类型与 Docstring — PASS

- 零 `Any`/`object` 在变更代码中
- 所有新增函数完整中文 docstring（参数、返回值、异常）
- `0 errors, 0 warnings, 0 informations` (pyright, per implementation reports)

---

## Subagent Coverage Map

| Subagent | Scope | Key Files | Key Findings |
|---|---|---|---|
| Evidence/Compaction | Evidence content flow, material pack, FakeCompactor | compaction.py, llm_compaction.py, compact_material.py, compaction_evidence.py, fake_compaction.py | Query text opaque (LOW), evidence chunking no boundary awareness (LOW), FakeCompactor imports private symbol (LOW) |
| State Machine/Dispatch | Dispatch safety, proactive/reactive paths, cancellation, recovery | dispatch.py, engine_ingest.py, context_governance.py, compaction_operation.py | Multi-pass attempt counter starvation (MEDIUM), proactive cancel not wired to close (LOW), reactive non-RECOVERING silent discard reconfirmed (LOW), rebuild result unchecked (LOW) |
| Memory Projection | Memory correctness, dedup, snapshot, projection continuity | memory.py, durable/memory.py, run_input.py | Dual text policy confirmed (MEDIUM), confirmed_subjects no dedup (LOW), all prior fixes verified |
| Architecture Boundaries | Import discipline, public API, layering, God objects | __init__.py files, api.py, host_assembly.py, runtime/*.py | HostDispatchScheduler God object (pre-existing, non-blocking), EngineEvent type in public API (pre-existing design), all layer boundaries PASS |
| ToolRuntime/Ingest | Accept barrier, engine ingest, compaction operation | tool_runtime.py, engine_ingest.py, compaction_operation.py, evidence.py | Hot-path payload_digest omission (LOW), evidence source_refs/locator_refs hardcoded empty (LOW), accept barrier retry sleep unguarded (LOW) |
| Main Reviewer | Prior fix verification, smoke review, finding adjudication | All production + smoke files | All 7 prior fixes verified, 2 MEDIUM + 10 LOW findings adjudicated |

---

## Open Questions

无。

---

## Residual Risks / Deferred Tracking

| Risk | Severity | Status | Owner |
|---|---|---|---|
| Multi-pass attempt counter 跨 pass 共享饿死后期 pass | 中 | **New** — Finding 6，需修复 | P12.7 / 后续 phase |
| `_payload_with_terminal_summary` 双实现 text policy 分歧 | 中 | Deferred — P12.5→P12.6 未修复，本次 Finding 1 | 后续 phase |
| HostDispatchScheduler God object (~2403 行, 35+ methods) | 中 | Pre-existing — 非本 phase 回归，建议后续拆分 | 后续 refactor |
| Reactive path 非 RECOVERING 丢弃无 diagnostic | 低 | Accepted residual — P12.6 controller | 后续 robustness |
| EvidenceBackedFactCandidate evidence_refs 格式校验弱 | 低 | Accepted residual — P12.5 controller | 后续 defense-in-depth |
| evidence_backed_facts 驱逐无重要性排序 | 低 | Accepted residual — P12.5 controller | 后续 policy |
| 空 candidate + 空 evidence 静默通过 quality check | 低 | Accepted residual — P12.5 controller | 后续 diagnostic |
| Payload validator 不独立检查 evidence coverage | 低 | Accepted residual — P12.5 controller | 后续 defense-in-depth |
| Public compact smoke 缺少 reactive 路径端到端触发 | 低 | Accepted residual — P12.6 controller | 后续 smoke |
| `confirmed_subjects` 缺少去重校验 | 低 | **New** — Finding 8 | 后续 defense-in-depth |
| Proactive compaction 取消未接入 scheduler close | 低 | **New** — Finding 9 | 后续 robustness |
| Query text 仅含 tool_call_id 不含可读参数 | 低 | **New** — Finding 7 | 后续 enhancement |
| Hot-path payload_digest 省略导致额外 resolution round-trip | 低 | **New** — Finding 12 | 后续 perf |
| Smoke `_compact_pressure_reserve_tokens` 死分支 | 低 | Known — smoke code review N1 | Smoke 维护 |

---

## Validation Reviewed

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/ tests/engine/ tests/runtime/ tests/service/` | 全量通过 (per implementation reports) |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE` | SMOKE PASS, tool call count=1, Round 4 assertion pass, compact artifact count=4 |
| 分层 import audit | PASS — 零反向依赖 |
| 类型标注完整性 | PASS — 零 `Any`/`object` |
| Docstring 完整性 | PASS — 全部中文 docstring |

---

## Areas Not Fully Covered

1. **Reactive compaction smoke-level end-to-end**: 仅在单元测试 (`test_compaction_operation.py`) 覆盖，无 public API 边界的 reactive smoke test。已知 P12.6 controller 接受。
2. **多轮 compaction 间 evidence_backed_facts 存活**: 两次连续 compaction 后 facts 存活路径无专门测试。当前 smoke 仅验证单次 compaction 后的四轮 continuity。
3. **跨进程并发 compaction**: 单机多进程下的 proactive/reactive compaction 竞态无测试覆盖。当前测试为单进程。
4. **真实 Fins 工具路径**: 所有 smoke 使用 mock tool，不验证真实财报工具、财报仓储或真实财报数值。

---

## Review Conclusion

**Verdict: PASS.** Phase 12.5 的 3 个 CRITICAL/HIGH blocking findings 全部验证已修复。Phase 12.6 新增的 conversation memory redesign 实现完整，架构边界、状态机安全、memory 正确性均通过审查。Smoke commit (cc0b452) 为 public-API-only，无回归。

2 个 MEDIUM findings：
1. `_payload_with_terminal_summary` 双实现 text policy 分歧 — 已知跨 phase deferred 项
2. Multi-pass compaction operation attempt counter 跨 pass 共享导致后期 pass 被饿死 — 新发现，建议 P12.7 修复

10 个 LOW findings，均为已接受 residual risks 或新发现的低影响项。无 CRITICAL 或 HIGH 阻塞项。6 个并行 subagent 审查覆盖 evidence/compaction、state machine/dispatch、memory projection、architecture boundaries、ToolRuntime/ingest 五个风险面，与主 reviewer 独立验证形成交叉确认。
