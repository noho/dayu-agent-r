# Phase 12.5 Aggregate Deepreview — Adversarial Pass

## Scope

- **Mode**: Current changes (aggregate deepreview)
- **Branch**: `feat/phase-12-5-conversation-memory-optimize`
- **Base**: `main` (HEAD: `0dbcc5a`)
- **Review date**: 2026-05-23 02:05 UTC+8
- **Output file**: `docs/reviews/phase12-5-aggregate-deepreview-ds-20260522.md`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Diff scope**: 78 files, +12080 / -1125 lines
- **Included**: All `dayu/` production code, all `tests/` test code, `docs/`, `dayu/config/`
- **Excluded**: `.venv/`, `workspace/`, `dayu/render/`, `utils/`, prior review artifacts
- **Parallel review coverage**:
  - Agent (ad1db7e3): Contracts & EventLog payload — `context_events.py`, `evidence.py`, `compaction_evidence.py`, `durable/schema.py`
  - Agent (aa2bfa39): Memory projection & durable — `memory.py`, `durable/memory.py`, `context_governance.py`, `compact_artifact.py`, `dispatch.py`
  - Agent (a6620706): LLM compaction & evidence extraction — `llm_compaction.py`, `compaction.py`, `compaction_evidence.py`, `context_governance.py`
  - Agent (aed98911): RunInputBuilder & ToolRuntime — `run_input.py`, `tool_runtime.py`, `engine_ingest.py`
  - Agent (a99c5e79): Config schema & layering — `execution_profiles.json`, `config_loader.py`, `host_assembly.py`, `dispatch.py`, import audit
  - Agent (a7c83cd5): Tests & coverage — all `tests/host/test_*.py`, `tests/host/fake_compaction.py`, `tests/runtime/test_config_loader.py`, `tests/service/test_host_assembly.py`
  - Main reviewer: additional root-cause trace of `_user_prompt()` evidence content gap, `ToolRuntime` accept barrier, `CompactionRequest` construction in `dispatch.py`/`engine_ingest.py`

---

## Findings

### 1-严重-LLM compactor 从未收到 evidence 信封内容，evidence_backed_facts 实质依赖幻觉生成

- **入口/函数**: `_user_prompt()` → `_agent_request()` → `LLMContextCompactor.compact()`
- **文件(行号)**: `dayu/host/llm_compaction.py` 行 317-369, 214-246, 189-211
- **输入场景**: 任意 proactive 或 reactive compaction。`CompactionRequest.accepted_evidence_envelopes` 持有完整 `AcceptedEvidenceEnvelope` 对象（含 `tool_name`、`tool_query`、`result_ref`、`source_refs`、`locator_refs`），但 LLM prompt 只接收不透明 ref 字符串。
- **实际分支**: `_user_prompt()` 行 331 调用 `_refs_text(request.accepted_evidence_refs)` — 该属性（`compaction.py` 行 355-364）从 envelopes 派生但只返回 `evidence_id` 字符串列表（如 `"evidence:event-abc-123"`）。`_agent_request()` 行 230-232 构造只含 `_SYSTEM_PROMPT` + `_user_prompt(request)` 两条消息的 `AgentRunRequest`。`to_json()`（含完整 envelope 序列化）未被任何 prompt 构造路径使用。
- **预期行为**: 设计文档 §25 行 2670-2672 要求 "evidence-backed fact candidates 基于 compact 输入中的 accepted evidence envelope 生成 `claim_text`、`evidence_kind`、`evidence_refs`"。LLM 必须能访问 envelope 中的 `tool_name`、`tool_query` 和 tool result 内容摘要，才能从真实证据中提取 claim。
- **实际行为**: LLM 只看到不透明 evidence ID 字符串 + 当前用户输入摘要 + JSON schema 模板。`claim_text` 和 `evidence_kind` 只能从当前用户输入摘要推导或幻觉，无法与 tool result 内容建立实质关联。
- **直接证据**:
  1. `compaction.py:230`: `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` — 完整数据存在于请求中
  2. `compaction.py:355-364`: `accepted_evidence_refs` property 只返回 evidence IDs
  3. `llm_compaction.py:331`: `f"accepted_evidence_refs: {_refs_text(request.accepted_evidence_refs)}"` — prompt 只使用 refs
  4. `llm_compaction.py:230-232`: Engine request 只含 system+user 两条消息
  5. 整个 `llm_compaction.py` 无任何对 `accepted_evidence_envelope` 或 evidence content 的引用
- **影响**: evidence_backed_facts 的 `claim_text` 与 `evidence_kind` 无法证明来自 accepted evidence。LLM 可能：将 tool result A 的数据归因到 evidence ref B；凭空生成 claim_text 并随意关联一个 evidence ref；将当前用户输入中的内容错误标记为 evidence-backed。Host 下游校验（`context_governance.py` 行 366-380, `context_events.py` 行 898-930）只验证 claim_text 非空/长度受限、evidence_refs 是 accepted evidence IDs 子集、evidence_kind 是合法枚举——无法检测 claim 语义是否真正源自 evidence。这与用户核心关注点直接冲突："evidence_backed_facts must be evidence-backed rather than hallucinated"。
- **建议改法和验证点**: `_user_prompt()` 必须为每个 `AcceptedEvidenceEnvelope` 至少序列化 `tool_name`、`tool_query` 关键字段、`result_ref` 摘要以及 `source_refs`/`locator_refs` 的不透明元数据。若 tool result payload 可通过 `payload_ref` 读取并在 prompt 预算内呈现摘要，也应纳入 compact 输入。修复后需验证：LLM 能看到 evidence 内容 → 生成的 claim_text 有办法与 evidence 建立可追溯关联 → FakeCompactor 也需同步修复以覆盖真实证据提取链。
- **修复风险**: 中 — 需同时修改 prompt 构建、可能的 payload 回读、FakeCompactor 测试 double、以及 prompt 长度预算（加入 evidence 内容后 prompt 会增大）。
- **严重程度**: 严重

### 2-严重-Memory 投影滞后触发 Run→FAILED 状态迁移，违反设计约束

- **入口/函数**: `_start_worker` → `_safe_closeout_worker_startup_timeout` → `_closeout_worker_startup_timeout` → `terminal_closeout_in_transaction`
- **文件(行号)**: `dayu/host/dispatch.py` 行 2090-2107, 2479, 2499-2500
- **输入场景**: `_catch_up_memory_projection_before_worker` 因 projection failure 提前退出，snapshot cursor 滞后超过 `max_lag_events_for_inline_delta` 阈值。`DurableMemorySnapshotProvider._load_memory_snapshot_tx` 抛出 `MemoryProjectionRepairRequired(reason=SNAPSHOT_LAG_OVER_THRESHOLD)`。
- **实际分支**: dispatch 将 `MemoryProjectionRepairRequired`（含 `SNAPSHOT_LAG_OVER_THRESHOLD` 原因）与 `SNAPSHOT_DAMAGED`/`SNAPSHOT_MISSING` 统一走 `_safe_closeout_worker_startup_timeout` → `_closeout_worker_startup_timeout` → `terminal_closeout_in_transaction`，将 Run 迁移至 `FAILED`（`run_terminal_status=RunStatus.FAILED`, `attempt_terminal_status=AttemptStatus.FAILED`）。
- **预期行为**: `docs/host/design.md` 行 2626 明确要求 "memory projection lag 不得触发 Run 状态迁移，不得把 Run 推入 RECOVERING"。投影滞后是可恢复的 read model 问题，不应导致业务 Run 失败。
- **实际行为**: 暂时性 snapshot lag 导致整个业务 Run→FAILED。
- **直接证据**: `dispatch.py` 行 2090-2098 对所有 `MemoryProjectionRepairRequired` 统一走 closeout 路径，未区分 `reason` 字段。`terminal_closeout_in_transaction` 行 2499-2500 写入 FAILED。
- **影响**: 投影暂时滞后（可恢复）导致业务 Run 失败，对终端用户体验有显著破坏。Run 原本可以继续执行并追平投影。
- **建议改法和验证点**: dispatch 应根据 `exc.repair_request.reason` 区分处理 — `SNAPSHOT_DAMAGED` 和 `SNAPSHOT_MISSING` 可走 Run→FAILED；`SNAPSHOT_LAG_OVER_THRESHOLD` 应触发 projection repair（如调用 `rebuild_conversation_memory_projection`）或返回 requeued，不改变 Run 状态。
- **修复风险**: 中 — 需要拆分异常处理路径并确保 repair 路径的事务安全。
- **严重程度**: 严重

### 3-高-FakeContextCompactor 绕过 AcceptedEvidenceEnvelope 证据提取链，测试路径为 false positive

- **入口/函数**: `FakeContextCompactor._fact_candidates()`
- **文件(行号)**: `tests/host/fake_compaction.py` 行 203-221
- **输入场景**: FakeCompactor 被用于所有 compaction contract/operation/artifact store 测试。
- **实际分支**: `_fact_candidates()` 从 `request.accepted_evidence_refs`（字符串 ID 列表）直接构造 fact candidates，完全不使用 `request.accepted_evidence_envelopes` 中的 `tool_name`、`tool_query`、`result_ref` 等内容。
- **预期行为**: FakeCompactor 应至少消费 envelope 的部分字段（如 `evidence_id`、`tool_name`）来构造有意义的 test candidates，从而覆盖证据提取的完整链路。
- **实际行为**: 所有依赖 FakeCompactor 的测试（`test_compaction_contract.py`、`test_compaction_operation.py`、`test_compact_artifact_store.py`）都在一个"证据内容从未流经 compactor"的假象下通过。
- **直接证据**: `fake_compaction.py` 行 203-221 仅遍历 `request.accepted_evidence_refs` 字符串列表，不访问 `accepted_evidence_envelopes`。
- **影响**: 即使发现 1 被修复（LLM 收到 evidence 内容），FakeCompactor 也不会验证该链路。测试无法证明 evidence_backed_facts 的 claim_text 真的来自 accepted evidence。
- **建议改法和验证点**: 修改 `FakeContextCompactor._fact_candidates()` 从 `request.accepted_evidence_envelopes` 构造 candidates，至少使用 envelope 的 `evidence_id` 和 `tool_name` 字段，确保 `evidence_refs` 正确对齐。
- **修复风险**: 低
- **严重程度**: 高

### 4-高-catch-up projection failure 被静默忽略，随后 lag check 触发误杀 Run→FAILED

- **入口/函数**: `_catch_up_memory_projection_before_worker` → `catch_up_conversation_memory_projection`
- **文件(行号)**: `dayu/host/dispatch.py` 行 2274-2292
- **输入场景**: projection runner 在 catch-up 批次中遇到 `failures > 0`（`_run_memory_projection_until_idle` 返回），catch-up 提前终止。
- **实际分支**: `catch_up_conversation_memory_projection` 返回含 `failures > 0` 的 result，但 `_catch_up_memory_projection_before_worker` 不检查 result 继续执行。随后 `DurableMemorySnapshotProvider._load_memory_snapshot_tx` 检测到 lag 超过阈值，抛出 `MemoryProjectionRepairRequired(SNAPSHOT_LAG_OVER_THRESHOLD)`，触发 Run→FAILED（发现 2）。
- **预期行为**: catch-up failure 应被显式检测并触发 projection repair，而非静默忽略后由 lag check 误诊为"lag over threshold"。
- **实际行为**: catch-up 失败的根因（projection failure）在事件链路中被诊断为"lag over threshold"，最终表现为 Run 失败。caller 无法区分"还没追上"（正常工作中）与"追上失败"（需要 repair）。
- **直接证据**: `dispatch.py` 行 2284-2292 调用 catch_up 后不检查返回值。`memory_repair.py` 行 251 在 failures > 0 时 break 但 `catch_up_conversation_memory_projection` 不 raise。
- **影响**: 导致发现 2 的 Run→FAILED 更容易触发。连续 catch-up failure 可导致多轮对话中的每个新 Run 都立即失败。
- **建议改法和验证点**: `_catch_up_memory_projection_before_worker` 应检查返回的 `failures` 值，projection failures > 0 时应直接 raise 或触发 repair。
- **修复风险**: 低
- **严重程度**: 高

### 5-高-EvidenceBackedFactView 缺少 claim_text 长度上限校验，防御纵深缺口

- **入口/函数**: `EvidenceBackedFactView.__post_init__`、`_evidence_backed_facts_from_compacted_event`
- **文件(行号)**: `dayu/host/memory.py` 行 421（仅 `_require_non_empty`）、行 1425-1495（不校验长度）
- **输入场景**: 从序列化数据反序列化 `EvidenceBackedFactView`（行 2934-2959），或从已持久化但 payload 损坏的 compacted event 构造 fact（行 1425-1495）。
- **实际分支**: `__post_init__` 只校验 claim_text 非空，不校验长度。长度上限 `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000` 仅在 `context_events.py` compaction candidate 阶段调用，不在 view 构造或反序列化阶段。
- **预期行为**: 设计文档行 2557-2558 要求 "Host 只校验 claim_text 非空且长度受限"。长度校验应在所有构造路径上生效，不仅依赖上游 proposal 阶段的校验。
- **实际行为**: 若 EventLog payload 被损坏或绕过 proposal stage，超长 claim_text 可进入 memory snapshot。
- **直接证据**: `memory.py` 行 421 无长度检查；行 1460 仅调用 `_required_str` 不校验长度。
- **影响**: 超长 claim_text 可进入 memory block 渲染，挤占 LLM 上下文预算。
- **建议改法和验证点**: 在 `EvidenceBackedFactView.__post_init__` 加入 `len(self.claim_text) <= MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS` 校验。在 `_evidence_backed_facts_from_compacted_event` 行 1460 后加入长度校验。
- **修复风险**: 低
- **严重程度**: 高

### 6-高-空 candidate 列表且空 evidence refs 场景静默通过 quality check，诊断性缺失

- **入口/函数**: `_fact_candidates_accepted`、`_retained_accepted_evidence_with_no_fact_candidate`
- **文件(行号)**: `dayu/host/context_governance.py` 行 343-363, 行 383-409, 行 87
- **输入场景**: compactor 返回空 `evidence_backed_fact_candidates` 列表，且请求中 `accepted_evidence_refs` 也为空（compact 范围内无 accepted tool evidence）。
- **实际分支**: `_fact_candidates_accepted` 对空列表返回 `True`。`_retained_accepted_evidence_with_no_fact_candidate` 因 `len(accepted_evidence_ids) > 0` 为 False 而跳过（行 87）。两条 guard 均通过，quality check 返回 `accepted=True`。
- **预期行为**: 无 accepted evidence 时不应产出 fact，逻辑正确。但此路径与"evidence 收集代码有 bug 导致空集合"无法区分。
- **实际行为**: 静默通过，缺少可诊断性。
- **直接证据**: `context_governance.py` 行 358-363 对空 tuple 返回 True；行 87 的条件短路由屏蔽了 `len(accepted_evidence_ids) == 0` 场景。
- **影响**: 若 upstream evidence 收集代码有 bug 导致 `accepted_evidence_refs` 被错误清空，compactor 返回空 candidates 会静默通过。
- **建议改法和验证点**: 当 `len(accepted_evidence_ids) == 0` 且 candidates 为空时，emit 低级别 diagnostic event（非 rejection），trace compact range 为何无 evidence。
- **修复风险**: 低
- **严重程度**: 中

### 7-中-payload validator 不独立校验"有 accepted evidence 但无 fact candidate"场景

- **入口/函数**: `validate_context_compacted_payload` → `_validate_fact_candidates`
- **文件(行号)**: `dayu/host/context_events.py` 行 314, 898-930
- **输入场景**: 手动构造的 `CONTEXT_COMPACTED` payload 中 `evidence_backed_fact_candidates` 为空列表，但 `preserved_fact_refs.accepted_evidence_refs` 非空。
- **实际分支**: `_validate_fact_candidates` 只对已有 candidates 做逐条校验（行 914-930），不对"accepted_evidence_refs 非空但 candidates 为空"做额外检查。
- **预期行为**: 有 accepted evidence 但无 fact candidate 覆盖时，应拒绝——与 quality check 中 `ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING`（`compaction.py` 行 77-79）语义一致。
- **实际行为**: payload 层验证不重复 quality check 的覆盖校验，仅依赖 quality check gate 前置过滤。若绕过 quality check 直接 append（异常路径），payload-level 验证不能独立阻止此场景。
- **直接证据**: `context_events.py` 行 898-930 无 `len(candidates) == 0 and len(accepted_evidence_refs) > 0` 的分支检查。
- **影响**: defense-in-depth gap。正常路径由 quality check 保护，但 payload validator 不提供独立防线。
- **建议改法和验证点**: 在 `_validate_fact_candidates` 新增检查。
- **修复风险**: 低
- **严重程度**: 中

### 8-中-evidence_backed_facts 限制策略仅保留最新（LIFO），无重要性排序

- **入口/函数**: `_limit_evidence_backed_facts`
- **文件(行号)**: `dayu/host/memory.py` 行 2112
- **输入场景**: evidence_backed_facts 数量超过 `policy.max_evidence_backed_facts`（默认 16）。
- **实际分支**: `items[-policy.max_evidence_backed_facts:]` 仅保留最后 N 条，丢弃最早的事实。丢弃时仅生成 `BUDGET_LIMIT_REACHED` diagnostic（行 2114-2119），不记录哪些事实被丢弃。
- **预期行为**: 设计文档行 2588 将 evidence_backed_facts 定位为稳定层，全量注入不参与 history pool 竞争。但 LIFO 驱逐可能丢弃长期有效的高价值事实（如"口径已确认"）而保留近期较低价值的事实。`evidence_kind` 枚举已存在但未用于驱逐优先级。
- **实际行为**: 纯 LIFO 驱逐。
- **直接证据**: `memory.py` 行 2112 `items[-policy.max_evidence_backed_facts:]`。
- **影响**: 长对话中关键归因事实可能被驱逐。
- **建议改法和验证点**: 考虑基于 `evidence_kind` 分层驱逐，或至少在 diagnostic 中记录被驱逐事实的 candidate_id 列表。
- **修复风险**: 低
- **严重程度**: 中

### 9-中-RunInputBuilder `_payload_with_terminal_summary` 双实现策略分歧

- **入口/函数**: `DurableMemorySnapshotProvider._repair_inline_delta` vs `ConversationMemoryProjectionConsumer.apply_event`
- **文件(行号)**: `dayu/host/run_input.py` 行 2012 vs `dayu/host/durable/memory.py` 行 228
- **输入场景**: 同一 `RUN_SUCCEEDED` EventLog row，内联 summary payload 字段存在但内容为空字符串。
- **实际分支**: durable path 使用 `STRICT_ALLOW_EMPTY` — 空字符串被接受为有效内容；inline delta path 使用 `STRICT_NON_EMPTY` — 空字符串被判定为 `None`，fall through 到 terminal_summary_ref 解析路径。
- **预期行为**: 两种投影路径应对同一 EventLog row 产生相同的 assistant conclusion item。
- **实际行为**: 两处 `_payload_with_terminal_summary` 实现近乎重复，仅 text policy 参数不同。inline delta repair 与 durable snapshot 的 assistant_conclusion 内容不一致，可能导致 RunInputBuilder 呈现给 LLM 的信息偶然漂移。
- **直接证据**: 对比 `durable/memory.py` 行 227-229 和 `run_input.py` 行 2010-2012。
- **影响**: 同一 Run 的不同 Attempt 可能看到不同的 continuity 内容。
- **建议改法和验证点**: 统一为同一 text policy（建议 `STRICT_ALLOW_EMPTY`），或抽取共享函数。
- **修复风险**: 低
- **严重程度**: 中

### 10-中-EvidenceBackedFactCandidate.__post_init__ 不校验 evidence_refs 格式

- **入口/函数**: `EvidenceBackedFactCandidate.__post_init__`
- **文件(行号)**: `dayu/host/compaction.py` 行 745-781
- **输入场景**: 构造 `EvidenceBackedFactCandidate` 时传入非 evidence 格式的字符串作为 `evidence_refs`（如 `"assistant_final_answer_ref"`）。
- **实际分支**: `__post_init__` 只校验 `evidence_refs` 为非空 bounded 字符串 tuple（行 767-772），不检查 refs 是否为合法 evidence id 格式（`evidence:<event_id>`），也不检查指向已接受 evidence。
- **预期行为**: 设计约束要求 evidence_refs 只指向 accepted evidence envelope。
- **实际行为**: 类型层面 evidence_refs 为无约束字符串 tuple。校验在两层后续防线完成（quality check + payload validator）。但 dataclass 层自身没有格式约束。
- **直接证据**: `compaction.py` 行 767-772 仅调用 `_require_bounded_string_tuple`。
- **影响**: 若在 bypass quality check 的情况下构造 CompactionCandidate，可注入非 evidence 来源的 refs。
- **建议改法和验证点**: 在 `__post_init__` 中至少校验 evidence_refs 的格式前缀 `evidence:`。
- **修复风险**: 低
- **严重程度**: 中

---

## 确认合规项 (无问题)

| 检查项 | 结果 | 位置 |
|---|---|---|
| 分层架构 UI→Service→Host→Engine 无反向依赖 | PASS | 全量 import audit |
| dayu.runtime 无业务层 import | PASS | runtime/ 下所有文件 |
| dayu.host 无 dayu.fins 导入 | PASS | host/ 下所有文件 |
| 旧 llm_models.json / run.json 已删除 | PASS | 磁盘确认 |
| 旧 verified_* / tool_fact_refs 全部 fail-closed | PASS | memory.py:2736, durable/memory.py:967, context_events.py:943 |
| execution_profiles.json 包含全部 6 类 policy | PASS | 4 个 profile 均含 run_baseline, compactor_baseline, context_budget_policy, memory_projection_policy, tool_truncation_policy, agent_policy |
| memory_projection_policy 15 字段全部存在 | PASS | ratio/floor/cap 各组独立正确 |
| context_budget_policy ratio-first 字段齐全 | PASS | soft_threshold_context_ratio, hard_threshold_context_ratio 等 |
| ConfigLoader 校验 memory_projection_policy 通过 `_require_exact_fields` | PASS | config_loader.py:1431-1481 |
| Host 装配 Service→Host 单向依赖 | PASS | host_assembly.py:838-867 |
| AcceptedEvidenceEnvelope 记录 evidence_id, producer_event_ref, tool_name, tool_call_id, tool_query, result_ref | PASS | evidence.py:149-193; tool_runtime.py:3551-3577 |
| ToolRuntime accept barrier 正确形成 accepted evidence envelope | PASS | tool_runtime.py:1928-2059, 3526-3527 |
| USER_INPUT_ACCEPTED 是 RunInputBuilder 中当前 prompt 的唯一事实入口 | PASS | run_input.py:512-557, 1338-1341 |
| RunInputBuilder 渲染 evidence_backed_facts 包含 claim_text + evidence_refs | PASS | run_input.py:1726-1751 |
| Memory stable block 注入顺序体现财报分析优先级 | PASS | run_input.py:1615-1638 |
| FINAL_ANSWER 不自动升级为 evidence_backed_fact | PASS | engine_ingest.py:753-757（结构性不变量：producer_kind=HOST_PROJECTION） |
| Pinned state patch 三态语义正确（MISSING/CLEAR/REPLACE） | PASS | compaction.py:55-60, context_governance.py:490-521, llm_compaction.py:704-724 |
| Minimum preserve item 校验正确 | PASS | compaction.py:815-846, context_governance.py:431-444 |
| Compaction operation durable 状态机正确 | PASS | compaction_operation.py:82-200 |
| Durable schema v6 memory projection 相关 migration | PASS | durable/schema.py |
| Context Governance 不绕过 EventLog 直接写 memory snapshot | PASS | context_governance.py 无 TABLE_HOST_MEMORY_* 引用 |
| evidence_backed_facts 只来自 CONTEXT_COMPACTED | PASS | memory.py:1205-1219 |
| pinned_state 包含全部 required fields | PASS | memory.py:354-367 |
| Snapshot cursor 追踪和 delta 重建 | PASS | memory.py:243-274, 786-823, 825-889 |
| Snapshot digest 强制校验 | PASS | memory.py:1028-1038 |

---

## Open Questions

1. **发现 1 的根因是否属于设计意图**：`_user_prompt()` 仅传递 evidence refs 而非 evidence 内容，是否是已知的 V1 设计折中（compaction-gated extraction 中 LLM 通过 raw turns 间接读取 tool results）？如果 raw turn 内容在未来的 prompt 注入中会包含 tool result 文本，那么发现 1 的严重程度可以从"严重"降级。但从当前代码看，`input_event_refs` 仅包含当前用户输入 ref，`recent_raw_turn_refs` 和 `older_raw_turn_refs` 也仅包含 opaque refs 而非实际内容。需要设计方确认此路径的预期行为。
2. **发现 2 的 severity 裁决**：Snapshot lag 触发 Run→FAILED 是否在 Phase 10/11 设计中有意为之？如果是，需要更新 `docs/host/design.md` 行 2626 的描述以反映实际行为。
3. **多轮 compaction 间 evidence_backed_facts 存活路径是否已在 Slice 7 覆盖**：控制文档提到 "no-compaction / post-compaction follow-up 端到端 smoke 仍归 Slice 7"（行 1667），但 6 个代理均未发现专门测试覆盖两次连续 compaction 后 facts 存活。此 gap 是否已包含在 Slice 7 的 smoke 范围内？

## Residual Risk

| 风险 | 严重程度 | Owner |
|---|---|---|
| evidence_backed_facts 的 claim_text 无法证明来自 accepted evidence（发现 1） | 严重 | Phase 12.5 implementation — LLM prompt 需要注入 evidence 内容 |
| Memory projection lag 误杀 Run（发现 2+4） | 严重 | Phase 12.5 / Phase 11 recovery — dispatch.py 异常处理路径需拆分 |
| FakeCompactor 绕过证据提取链，测试 false positive（发现 3） | 高 | Phase 12.5 test — fake_compaction.py 需消费 envelope 内容 |
| EvidenceBackedFactView claim_text 长度无防御纵深（发现 5） | 高 | Phase 12.5 implementation — memory.py view constructor |
| 空 candidate + 空 evidence 静默通过（发现 6） | 中 | Phase 12.5 implementation — context_governance.py diagnostic |
| Payload validator 不独立检查覆盖（发现 7） | 中 | Phase 12.5 implementation — context_events.py defense-in-depth |
| evidence_backed_facts LIFO 驱逐（发现 8） | 中 | Phase 12.5 / future — memory.py policy refinement |
| `_payload_with_terminal_summary` 双实现分歧（发现 9） | 中 | Phase 12.5 implementation — run_input.py / durable/memory.py 统一 |
| EvidenceBackedFactCandidate 格式校验弱（发现 10） | 中 | Phase 12.5 implementation — compaction.py constructor |
| 旧 `verified_*` contract 残留引用仅限 fail-closed guard 和 review artifacts | 低 | 无需处理 — 确认无活跃生产路径使用 |
| Public-path no-compaction continuity smoke 未新增（控制文档行 1676） | 低 | Phase 12.5 后续 — 需补充端到端测试 |
| `compaction_evidence.py` 使用 session-filtered `start_event_sequence=1` 保守读取（控制文档行 1677） | 低 | Phase 12.5 / performance hardening — 派生 session min sequence |
| Candidate JSON helper duplication（控制文档行 1677-1678） | 低 | Phase 12.5 cleanup — aggregate polish |

## Verdict

**NOT ready-to-open-draft-PR.** 发现 1（LLM compactor 未收到 evidence 内容，evidence_backed_facts 实质依赖幻觉生成）为 blockers，直接命中用户核心关注点"evidence_backed_facts must be evidence-backed rather than hallucinated"。发现 2（memory projection lag 触发 Run→FAILED）违反设计文档 §24 明确禁止的约束。发现 3（FakeCompactor 测试 false positive）意味着即使发现 1 被修复，测试也无法验证修复的有效性。

必须修复发现 1 和 2 后重新评审。发现 3、4、5 建议在 draft PR 前修复。发现 6-10 可作为 deferred 或 draft PR 内修复项。

其余架构边界、Config schema、分层约束、EventLog payload 形状、ToolRuntime accept barrier、RunInputBuilder 渲染、旧 contract fail-closed 均通过审查，无需变更。
