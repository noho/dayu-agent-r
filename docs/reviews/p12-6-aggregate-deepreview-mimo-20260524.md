# P12.6 Aggregate Deep Review — AgentMiMo

日期：2026-05-24
审查范围：`8749be9..69ca9ce` (P12.6 plan-fix checkpoint → slice 7 accepted)
设计真源：`docs/host/design.md` §24 / §25
计划文档：`docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`

---

## Verdict: PASS

P12.6 全部 7 个 slice 通过 aggregate deep review。无 blocking findings。

---

## 必查项逐条审查结果

### 1. EventLog ledger dump / Session 起点 range collector 进入 compactor prompt

**PASS — 无违规。**

- `start_event_sequence=1` 在 `dayu/host/` 生产代码中零匹配。
- `dispatch.py` 和 `engine_ingest.py` 的 `CompactionRequest` 构造均使用 `material_pack=...` / `segment_selection=...`，不再从 Session 起点读取 EventLog range。
- `llm_compaction.py` 的 `_compaction_request_prompt_block()` 调用 `request.llm_material_json()`，只返回四个 material pack sections，不含 EventLog ledger wrapper。

### 2. `result_preview` 读取、生成或作为 evidence extraction 输入

**PASS — 无违规。**

- `result_preview` 在 `dayu/host/` 中仅出现在 `compaction_evidence.py:302-311` 的 `_reject_result_preview()` migration guard，该函数在 payload 中出现 `result_preview` 时抛出 `HostDurableError`，是正确的防御代码，非使用路径。
- `test_public_compact_smoke.py` 多处断言 `"result_preview" not in material_text`。
- Evidence material 从 `TOOL_RESULT_ACCEPTED` canonical fact 引用的 payload/descriptor 读取 raw tool outcome，经 digest 校验后构造 readable evidence block text。

### 3. event id / payload ref / digest / cursor / policy / artifact descriptor 作为 LLM semantic input

**PASS — 无违规。**

- `llm_compaction.py` 的 prompt 渲染只使用 `request.llm_material_json()`，返回四个 material pack sections。
- `test_prompt_renders_material_pack_without_ledger_dump` 断言 prompt 不含 `payload_digest`、`payload_ref`、`outcome_digest`、`accepted_evidence_envelopes`、`compact_raw_context`、`input_event_refs`、`canonical_source_refs`、`memory_snapshot_cursor`、`policy_snapshot`。
- Prompt asset `conversation_compaction_user.md` 使用 prompt-local labels（`E1`、`C1`、`H1`），不要求 `input_event_refs`、`accepted_evidence_refs` 或 `preserved_input_event_refs`。

### 4. compact material pack 是否 prompt-local labels + Host provenance map

**PASS — 无违规。**

- `CompactMaterialPack` 包含 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor` 四个 sections 和 internal `provenance_map`。
- `PromptLocalProvenanceEntry` 保存 canonical source refs、EventLog refs、content digest、accepted evidence id。
- `PromptLocalEvidenceMap` 是 `provenance_map` 的 evidence-only 受限子集。
- Prompt-local label 生成由 `compact_material.py` 的模块级私有 helper 控制（`material_label()`、`evidence_chunk_label()`、`current_input_anchor_label()`），格式由 `_SECTION_PREFIXES` 常量映射。
- Parser 将 LLM 输出的 prompt-local labels 映射为 canonical refs 后再构造 `CompactionCandidate`。
- accepted tool evidence raw content 通过 digest-checked payload/raw result descriptor 读取。

### 5. proactive/reactive Context Governance 遵守 Host lifecycle/cancellation/commit barrier

**PASS — 无违规。**

- `compaction_operation.py` 的 `run_compaction_operation()` 支持 multi-pass：每个 pass 独立运行 LLM proposal，所有 pass 成功后 merge 为单个 `CompactionCandidate`，只提交一个 `CONTEXT_COMPACTED`。
- 任一 pass 失败且 budget 耗尽，整个 operation 提交一个 `CONTEXT_COMPACTION_FAILED`。
- 中间 pass output 仅在内存中累积（`accepted_candidates` list），不写 EventLog。
- stale/cancelled/session closed/execution replaced/cursor mismatch 时丢弃 proposal，不写 `CONTEXT_COMPACTED`。
- Proactive compaction 通过 durable Run 状态观察 token；reactive compaction 复用 Engine envelope 的 run-local cancellation token。
- `_requires_budget_acceptance()` 对 reactive trigger 跳过 hard-threshold gate，避免 post-compact 估算不准导致误判。

### 6. memory projection / RunInputBuilder 保持 bounded deterministic working set

**PASS — 无违规。**

- `memory.py` 中 `_merge_evidence_backed_facts_by_dedupe_key()` 使用 `(normalized_claim_text, sorted_evidence_refs, evidence_kind)` 去重，较新 extraction event sequence 优先。
- `_limit_evidence_backed_facts()` / `_limit_continuity_items()` 强制 policy caps。
- `_expire_covered_minimum_preserve_items()` 移除被 stable fact 或 episode summary 覆盖的 items。
- `RUN_SUCCEEDED` 创建 `ASSISTANT_CONCLUSION` continuity item，`claim_status=ASSUMPTION`，不自动升级为 evidence_backed_fact。
- `run_input.py` 的 `_memory_messages()` 渲染顺序符合 design §24：stable blocks → raw turns → minimum preserve → episode summaries。
- Stable fact block 包含 `claim_text` 和 `evidence_refs`，不退化为 digest-only。
- `test_public_compact_smoke.py` 断言 no-compaction path 的 recent raw turns continuity 正常工作。

### 7. Public compact smoke 覆盖 P12.6 success signals

**PASS — 全部覆盖。**

| 场景 | 测试 |
|------|------|
| no-compaction recent raw turns continuity | `test_public_compact_smoke.py:96` |
| post-compaction evidence-backed fact reuse | `test_public_compact_smoke.py:146` |
| long user input + minimum preserve resolution | `test_public_compact_smoke.py:247` |
| long tool result from raw evidence (not preview) | `test_public_compact_smoke.py:212` |
| long session multiple compact + bounded memory | `test_public_compact_smoke.py:302` |
| proactive compact with duplicate prompt | `test_public_compact_smoke.py:359` |

Fake compactor 使用 prompt-local labels 输出 JSON，不生成 canonical Host refs。Real provider smoke 为 optional。

### 8. 分层约束 / 类型约束 / 中文 docstring / README / 无兼容 wrapper

**PASS — 无违规。**

- **反向依赖**：`rg "import dayu\.service|import dayu\.ui|import dayu\.fins" dayu/host/` 零匹配。
- **类型约束**：`compaction.py`、`compact_material.py`、`compaction_evidence.py`、`llm_compaction.py` 中无 `Any`、`object`、无类型参数或返回值。
- **hasattr/getattr**：上述文件中零使用。
- **中文 docstring**：`compact_material.py`(128)、`compaction.py`(233)、`compaction_evidence.py`(46)、`llm_compaction.py`(100)、`compaction_operation.py`(50)、`memory.py`(324)、`run_input.py`(266)。
- **README**：`dayu/host/README.md` 更新 Context Compaction 段（material pack、segment selection、provenance mapping、reactive multi-pass）和 Memory 段（evidence-backed facts dedupe、bounded working set、minimum preserve expiry、episode summaries bounded）。`dayu/README.md` 更新 Context Governance 术语（tool facts → accepted tool evidence）。`tests/README.md` 新增 test group。无越界写法。
- **兼容 wrapper**：旧字段 `input_event_refs`、`accepted_evidence_envelopes`、`compact_raw_context_items`、`CurrentMessageSummary`、`CompactRawContextItem` 在 `dayu/host/` 中零匹配。

---

## Findings

无 blocking 或 needs-fix findings。

### F1 — INFO：`_reject_result_preview()` migration guard 可后续清理

- **文件**：`dayu/host/compaction_evidence.py:302-311`
- **证据**：该函数在 payload 中出现 `result_preview` 时抛出 `HostDurableError`，是防御性拒绝逻辑。
- **影响**：零运行时影响，仅在历史旧格式 payload 出现时触发。
- **建议**：保留。当确认所有旧 EventLog 中无 `result_preview` payload 后可移除。

---

## Residual Risks

| 风险 | Owner | 说明 |
|------|-------|------|
| 大 session rebuild performance | 后续 phase | 本 phase 只要求语义正确、bounded、可测试 |
| Prompt-local label → canonical provenance mapping 扩大 artifact/diagnostic 面 | Reviewer | 需确认未把 raw prompt 或敏感 provider payload 写入 EventLog |
| V1 relevance strategy 使用 Host-neutral text overlap/recency | 后续 retrieval owner | 不能理解财报业务语义 |
| Reactive multi-pass 消耗有限 LLM proposal budget | 设计选择 | 预算耗尽 fail closed 是设计选择 |

---

## Tests Reviewed

| 测试文件 | 覆盖范围 |
|----------|---------|
| `test_compaction_contract.py` | quality-check rejection paths, pinned patch tri-state |
| `test_llm_compaction.py` | prompt 无 ledger dump, parser label mapping, envelope metadata 排除 |
| `test_compaction_operation.py` | multi-pass, single terminal event, budget gate |
| `test_compact_material.py` | deterministic selection, one-to-one section, snapshot cursor |
| `test_public_compact_smoke.py` | 6 个 P12.6 success signal 场景 |
| `test_memory_projection.py` | dedupe, bounded working set, expiry, no auto-upgrade |
| `test_run_input_builder.py` | rendering order, claim_text+evidence_refs, bounded raw turns |
| `test_dispatch_scheduler.py` | material pack request construction |
| `test_engine_ingest_mapping.py` | material pack request construction |
| `test_context_compact_events.py` | event payload 结构 |
| `test_compact_artifact_store.py` | artifact stores material pack digest |
| `test_context_budget.py` | budget policy |
| `test_toolruntime_accept_barrier.py` | accept barrier |

**总计**：326 passed, 1 skipped (6.80s)

---

## 验证命令

```bash
source .venv/bin/activate

# 测试
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_context_budget.py tests/host/test_toolruntime_accept_barrier.py -q

# 类型检查
python -m pyright dayu/host/compaction.py dayu/host/compact_material.py dayu/host/compaction_evidence.py dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_events.py dayu/host/compact_artifact.py dayu/host/memory.py dayu/host/run_input.py dayu/host/payload_resolution.py dayu/host/compact_payload.py

# 旧字段残留检查
rg -n "accepted_evidence_envelopes|compact_raw_context_items|current_message_summary|CurrentMessageSummary|CompactRawContextItem|compact_raw_context|accepted_evidence_refs|preserved_input_event_refs" dayu/host/

# Session 起点 range collector
rg -n "start_event_sequence.*=.*1" dayu/host/

# result_preview（仅 migration guard 允许）
rg -n "result_preview" dayu/host/

# 类型违规
rg -n "\bAny\b|: object\b|-> object\b" dayu/host/compaction.py dayu/host/compact_material.py dayu/host/compaction_evidence.py dayu/host/llm_compaction.py

# 反向依赖
rg -n "import dayu\.service|import dayu\.ui|import dayu\.fins|from dayu\.service|from dayu\.ui|from dayu\.fins" dayu/host/
```
