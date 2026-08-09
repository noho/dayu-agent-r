# PR-190 F13 S1 Full-Slice Code Review — AgentMiMo

## Gate metadata

- work unit / slice: F13 / S1（compaction v4 全栈：contract → material → boundary → governance → replacement → durable → rolling → Memory → reconnect → call sites）
- reviewer: AgentMiMo
- base commit: `62445b59c7a644133b15ca29d34c6e678aa2c047`
- reviewed diff identity: `d82dd47e26fd32537bb6d80780bbf5c97ede0a97`
- review date: 2026-08-06
- prerequisites: C1/C2/C3 均 accepted，其覆盖 source/config/test 文件未改变

## Verdict: **accepted**

无 blocking / high / medium finding。3 个 low residual 均来自 C1/C2 已 accepted 的观察，不改变 S1 contract 正确性。

## Cross-cutting verification

### 1. Semantic owner 唯一性

| 业务事实 | 唯一 owner | 验证 |
|---|---|---|
| v4 DTO / 不变量 / accepted truth | `compaction.py` | frozen/slots，`_CompactAcceptancePermit` 私有许可 |
| structure descriptor → template/schema/rules/parser | `compact_structure.py` `_ROOT` | 四投影同源，parser round-trip |
| acceptance gate | `context_governance.py` `accept_compact_candidate_v4` | 固定顺序：binding → derivation → duplicate → info → caps |
| durable schema-5 strict parser | `compact_payload.py` `ContextCompactedSemanticPayload.__post_init__` | 完整重验 proposal↔boundary↔replacement↔coverage↔aggregate↔audit |
| per-fact provenance projection | `CompactAcceptedReplacementV4.canonical_evidence_refs` (property) + `derive_compact_accepted_replacement_v4` | 逐 fact refs 从 boundary ordered unique union；aggregate 是 property 派生 |
| label binding validator | `compact_proposal_boundary_binding_issues_v4` | governance 与 durable parser 复用同一函数 |
| replacement binding validator | `validate_compact_proposal_replacement_binding_v4` | re-derive + equality check |
| Memory per-fact refs | `memory.py` `_facts_from_accepted_event` | 逐 atom 读 `fact.canonical_evidence_refs`，不读 aggregate |

无 dual owner、无第二 provenance source、无 `hasattr/getattr` 分支。

### 2. Proposal audit-only / replacement truth

- `CompactAcceptedTruthV4` 持有 `proposal`（audit）+ `replacement`（consumer truth）。
- durable payload 同时持久化 `accepted_proposal` 与 `accepted_replacement`（`compact_payload.py`、`context_events.py`）。
- `accepted_evidence_mapping_refs` 从 `replacement.canonical_evidence_refs` 派生，不再作为显式参数传入（`context_events.py:1230`、`compact_pipeline.py:290-296`）。
- 所有 consumer（Memory/RunInput/dispatch/engine_ingest/rolling）从 `accepted_replacement` 投影。
- `accepted_candidate` / `candidate_binding_v4` residue scan：零命中。

### 3. Per-fact provenance：boundary → durable → rolling → Memory → reconnect 同源

**链路追踪：**

1. **boundary 构造**：`CompactSourceBoundaryEntryV4.__post_init__` 对 `EVIDENCE_MATERIAL` / `PREVIOUS_EVIDENCE_FACT` 强制 `canonical_evidence_refs` 非空；其余 kind 强制为空。
2. **replacement derivation**：`derive_compact_accepted_replacement_v4` retained 从 boundary entry 原子复制 refs；new fact 按 boundary 顺序 extend + `dict.fromkeys` 去重。
3. **durable 持久化**：schema-5 strict parser 逐 fact 恢复 `canonical_evidence_refs`；aggregate = replacement property 派生。
4. **rolling**：`_previous_compacted_view_pair_from_replacement` 对每个 `replacement.evidence_facts` atom 同时取 `claim` + `canonical_evidence_refs`。
5. **Memory**：`_facts_from_accepted_event` 逐 fact 构造 `EvidenceBackedFactView(evidence_refs=fact.canonical_evidence_refs)`。
6. **reconnect**：经 `parse_context_compacted_semantic_payload` strict parser 恢复 replacement，复用同一 Memory projection。
7. **RunInput**：`CompactPipelineAcceptedPayloadInput.accepted_evidence_mapping_refs` 是 `replacement.canonical_evidence_refs` 的只读 property，用于 represented refs 整体视图。

手工复算验证（`test_retained_plus_two_source_new_fact_has_exact_per_fact_and_aggregate_refs`）：
- retained `P1` refs = `(previous-a, previous-b)`
- new `(E1,E2)` refs = `(current-a, shared, current-b)`
- aggregate = `(previous-a, previous-b, current-a, shared, current-b)`

无 aggregate 反写 per-fact、无跨 atom refs 共享、无旧 singular `accepted_evidence_id` 残留。

### 4. Repair / exhaustion / fallback / stale / late 无污染

- repair 每次走完整 `accept_compact_candidate_v4`（`compaction_operation.py:1023`），无 shortcut。
- repair feedback 只投影 bounded typed issues（`build_compact_repair_feedback_v4`）。
- budget exhaust → `_failed_operation_result(accepted_truth=None)`，不物化 artifact / replacement。
- stale / cancellation 由 `_CompactionAttemptCancellationToken` parent 优先逻辑保证丢弃。
- rejected / failed candidate 无 accepted replacement 读取入口。

### 5. Fake 无 heuristic

- `_typed_repair_omits_evidence_facts`：检查 `CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM` + `json_path.startswith('$["evidence_facts"]')`。
- `_prompt_repair_omits_evidence_facts`：从 repair prompt 的 typed JSON block 读取 issue code + json_path。
- 两者均为 deterministic typed-code 匹配，无 claim 文本比较、无关键词、无 fuzzy similarity。
- `FakeContextCompactor` 通过 production `accept_compact_candidate_v4` 构造 accepted truth。

### 6. 无 compat / drop ledger / downstream 补偿 / god object

- 无 v3 alias / re-export / dual reader / compatibility shim。
- 无 `explicitly_dropped_sources` / `diagnostics` 旧字段。
- 无 flat aggregate 反向写 fact。
- 无下游 fallback 补偿（dispatch/engine_ingest 无 `except` 补偿路径）。
- 每个模块职责单一，无 god object / god function。

### 7. Allowed scope 无越界

S1 实现完整覆盖 plan 步骤 1-6，未提前实现 S2 的：
- public Tool Trace 新 typed fact projection / `ResolvedCompactorEvidenceFact`
- README 更新
- integration 文案

`test_tool_trace_queries.py` 仅做 v3/schema-5 fixture 迁移，未引入 S2 新语义。

### 8. S2 边界清晰

S2 拥有：public Tool Trace 新投影、README、real provider integration。
S1 已交付：v4 contract、material/boundary/governance/replacement、durable schema-5、rolling、Memory、reconnect、call sites、fake、874 tests。

## Mandatory owner tests 1-15 覆盖矩阵

| # | 测试维度 | 文件 | 覆盖要点 |
|---|---|---|---|
| 1 | v4 DTO shape / frozen / no-default | `test_compaction_contract.py` | `CompactCandidateV4` 7 fields、`CompactAcceptedEvidenceFactV4` 4 fields、`CompactOutputCapsV4` 9 fields |
| 2 | boundary binding validator | `test_compaction_contract.py` | label existence / duplicate / kind / canonical order |
| 3 | retained+new refs 顺序与 dedup | `test_compaction_contract.py` | retained `P1` + new `E1,E2` 手工复算 |
| 4 | strict parser accept/reject | `test_llm_compaction.py` | exact key、duplicate key、unknown key、invalid type/enum |
| 5 | repair feedback bounded typed | `test_llm_compaction.py` | issue count/char limits、脱敏、whole-proposal requirement |
| 6 | prompt 自足 / 脱敏 | `test_llm_compaction.py` | 无 digest/refs/governance 术语；adversarial material 保留原文 |
| 7 | material → boundary provenance | `test_compact_material.py` | current evidence / previous fact refs 非空；non-evidence 为空 |
| 8 | governance acceptance | `test_compact_pipeline.py` + `test_compaction_contract.py` | combined duplicate/info/caps/audit；retain-only 合法 |
| 9 | durable schema-5 binding | `test_context_compact_events.py` | proposal↔boundary↔replacement↔coverage↔aggregate↔audit 全重验 |
| 10 | durable tamper detection | `test_context_compact_events.py` | claim/selection/refs/aggregate/replacement tamper parametrize |
| 11 | rolling per-fact provenance | `test_compact_material.py` | previous fact atom claim+refs 同源 |
| 12 | Memory per-fact refs | `test_memory_projection.py` | 逐 atom `evidence_refs`，无 aggregate 污染 |
| 13 | repair exhaustion / fallback | `test_compaction_operation.py` | budget exhaust → no accepted truth；stale/late → single terminal |
| 14 | reconnect strict parser | `test_run_input_builder.py` + `test_public_compact_smoke.py` | 经 strict parser 恢复 replacement |
| 15 | fake typed repair | `fake_compaction.py` + `test_public_compact_smoke.py` | typed issue code + json_path，无 heuristic |

## Test / Host smoke / real provider 区分

| 类型 | 范围 | 说明 |
|---|---|---|
| owner contract tests | 874 passed（C1: 64, C2: 215+40, C3: 555） | DTO 不变量、parser 行为、binding validator、provenance union |
| Host smoke / integration | `test_public_compact_smoke.py`、runtime assembly | Host public API + fake compactor，不调用真实 LLM |
| real provider / interactive | 不在 S1 范围 | 归 S2；S1 不声称验证真实 LLM 行为或 interactive CLI |

Controller 独占重跑完整命令：`595 passed, 1 skipped, 3 warnings`（第三方 edgar deprecation）。`git diff --check` 通过。diff identity 仍为 `d82dd47e`。

## Findings

### F-01 (low)：非 evidence kind boundary entry 带非空 refs 无显式 negative test

- severity: low
- file:line: `compaction.py:702-706`
- 反例: 构造 `TRACE_MATERIAL` / `ANSWER_MATERIAL` 等 kind 带非空 `canonical_evidence_refs`
- 修法: 补充 parametrized negative test 覆盖六种非 evidence kind
- verdict: **accepted**（production code 强制 fail closed，仅缺显式回归保护）

### F-02 (low)：durable parser `context_labels` / `omitted_coverage.source_labels` 定向 tamper 无独立 case

- severity: low
- file:line: `test_context_compact_events.py:609-637`
- 反例: 修改 `context_labels` 或 `omitted_coverage.source_labels` 后断言 parse 失败
- 修法: 在 tamper parametrize 中追加独立条目
- verdict: **accepted**（replacement 全对象相等比较间接覆盖，不阻塞）

### F-03 (low)：`CompactRepairFeedbackV4.required_action` 带默认值

- severity: low
- file:line: `compaction.py:2437`
- 反例: 若改为无默认值，所有构造点必须显式传 `COMPACT_REPAIR_REQUIRED_ACTION`
- 修法: accepted-as-is（frozen 常量 + `__post_init__` 强制校验，不产生语义漂移）
- verdict: **accepted**
