# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Code Re-Review

## Scope

- **Mode**: current changes（working tree + committed diff）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: HEAD working tree（含所有 staged + unstaged changes）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-rereview-ds.md`
- **Review target**: AgentCodex 对 P3-C S1 accepted findings（F01/F02/F03）的 fix 完整性与 fix 引入的新 material regression
- **Included scope**:
  - `dayu/host/compact_payload.py` — `_required_unique_text_list` helper、所有 parser label 路径、`accepted_compact_business_texts` 删除
  - `dayu/host/memory.py` — `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 删除、`_PAYLOAD_FIELD_*` 常量删除、typed enum 迁移
  - `dayu/host/durable/schema.py` — DDL reason allowlist 清理（schema version 20→21 为其他分支变更）
  - `tests/host/test_context_compact_events.py` — 新增 parser path regression 测试、删除 S1-only business text 断言
  - `dayu/host/context_events.py` — `_validate_vnext_candidate_payload` / `_validate_mapping_list` 删除，委托 parser
  - `dayu/host/run_input.py` — LLM-facing enum `.value` 使用
  - `dayu/host/durable/memory.py` — enum `.value` 序列化
  - `tests/host/test_memory_projection.py`、`tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py`、`tests/host/memory_snapshot_factories.py` — enum 迁移与测试适配
- **Excluded scope**: `compact_material.py`（S2 residual）、`context_budget.py`（S2 residual）、untracked `docs/cli_ci*`、既有 code-review artifacts
- **Design 真源**: `docs/host/design.md`、`docs/engine/design.md`
- **Control 真源**: `docs/host/issues-implementation-control.md`
- **Reference artifacts**: 见本文件引用列表

## 逐项复核

### P3-C-S1-CR-F01：Parser owner path-aware unique text list helper

**结论：PASS — fix 完整闭环。**

#### 1.1 单一 path-aware non-empty unique text list helper 存在

`_required_unique_text_list`（`compact_payload.py:850-875`）：

- 参数：`payload`、`field_name`、`path`（caller-provided full JSON path）、`allow_empty`（默认 False）
- 逻辑：先调用 `_required_text_list(payload, field_name, path=path)` 做基础类型/非空文本校验，再按 `allow_empty` 决定是否拒绝空 list，最后遍历去重并在重复时 raise `ValueError(f"{path}[{index}] must be unique")`
- 不是 fact 特例：函数签名为通用 `(Mapping, str, path, bool) -> tuple[str,...]`，对调用方无任何 section-type 假设

#### 1.2 覆盖所有需要唯一性的 nested label/source-label lists

Controller adjudication 列出的七处 label/source-label 字段全部使用 `_required_unique_text_list`：

| # | 字段 | 调用位置 | allow_empty |
|---|------|----------|-------------|
| 1 | `session_summary.source_labels` | `compact_payload.py:255` | `False`（默认） |
| 2 | `evidence_backed_facts[*].evidence_labels` | `compact_payload.py:280` | `False`（默认） |
| 3 | `evidence_backed_facts[*].source_labels` | `compact_payload.py:288` | `True` |
| 4 | `answer_anchors[*].answer_source_labels` | `compact_payload.py:324` | `False`（默认） |
| 5 | `forward_intents[*].source_labels` | `compact_payload.py:379` | `False`（默认） |
| 6 | `reference_continuity_items[*].source_labels` | `compact_payload.py:410` | `False`（默认） |
| 7 | `diagnostics[*].source_labels` | `compact_payload.py:436` | `True` |

`allow_empty=True` 仅在 `evidence_backed_facts[*].source_labels` 和 `diagnostics[*].source_labels` 两处开启，与 typed contract 一致：

- `EvidenceBackedFactCandidateVNext.__post_init__`（`compaction.py:1209`）对 `source_labels` 使用 `_require_unique_string_tuple`（允许空）。
- `CompactCandidateDiagnosticVNext.__post_init__`（`compaction.py:1415`）对 `source_labels` 使用 `_require_unique_string_tuple`（允许空）。
- 其余五处 typed contract 使用 `_require_non_empty_unique_string_tuple`（不允许空），parser 侧 `allow_empty=False` 与之精确对应。

#### 1.3 错误路径保留完整 indexed JSON path

所有 parser label path 从 `accepted_candidate` 根开始，经 section 名和 `[{index}]` 到达具体元素：

- `_parse_fact`（line 276）：`path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_EVIDENCE_BACKED_FACTS}[{index}]"` → label path = `f"{path}.{_FIELD_EVIDENCE_LABELS}"` → 最终错误路径格式 `accepted_candidate.evidence_backed_facts[0].evidence_labels[1]`
- `_parse_forward_intent`（line 371）：`path = f"{_FIELD_ACCEPTED_CANDIDATE}.{_FIELD_FORWARD_INTENTS}[{index}]"` → label path = `f"{path}.{_FIELD_SOURCE_LABELS}"` → 最终错误路径格式 `accepted_candidate.forward_intents[0].source_labels[1]`

测试覆盖：

- `test_compacted_semantic_parser_rejects_duplicate_fact_labels_with_indexed_path`（`test_context_compact_events.py:244`）：参数化覆盖 `evidence_labels` 和 `source_labels`，验证路径 `accepted_candidate.evidence_backed_facts[0].evidence_labels[1]` 与 `accepted_candidate.evidence_backed_facts[0].source_labels[1]`
- `test_compacted_semantic_parser_rejects_duplicate_intent_source_labels_with_indexed_path`（`test_context_compact_events.py:265`）：验证 `accepted_candidate.forward_intents[0].source_labels[1]`，证明不是 fact 特例
- `test_compacted_semantic_parser_rejects_empty_summary_source_labels_with_path`（`test_context_compact_events.py:214`）：验证 `accepted_candidate.session_summary.source_labels` 非空校验

#### 1.4 不是 fact-only 特例

`_required_unique_text_list` 是通用 helper，被七处不同 section type（summary / fact / anchor / intent / reference / diagnostic）调用。测试覆盖 fact 和 intent 两类，证明跨 section 可用。

---

### P3-C-S1-CR-F02：Dead MemoryDiagnosticReason 枚举值移除

**结论：PASS — fix 完整闭环。**

独立 source scan 结果：

```
rg -n "EVIDENCE_BACKED_FACT_CANDIDATE_INVALID|evidence_backed_fact_candidate_invalid" dayu tests
→ 零匹配
```

逐层验证：

1. **枚举定义**：`dayu/host/memory.py:157-170` 中 `MemoryDiagnosticReason` 枚举不再包含 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`。当前枚举成员：`ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE`、`INLINE_DELTA_REPAIR_INCLUDED`、`SNAPSHOT_MISSING`、`SNAPSHOT_DAMAGED`、`UNSUPPORTED_EVENT_TYPE`、`SNAPSHOT_LAG_OVER_THRESHOLD`、`BUDGET_LIMIT_REACHED`、`EMPTY_EVENT_LOG_SNAPSHOT`、`EVIDENCE_BACKED_FACT_SUPERSEDED`。
2. **唯一生产者**：`_fact_candidate_invalid_diagnostic()` 函数已从 `memory.py` 完全删除（diff 确认，函数体约 30 行被移除，其唯一调用点也一并删除）。
3. **durable DDL allowlist**：`dayu/host/durable/schema.py` 中 `evidence_backed_fact_candidate_invalid` 字面量零匹配。`host_memory_diagnostics` 表的 reason CHECK 约束不再包含该值。
4. **所有消费者**：source scan 对 `dayu/` 和 `tests/` 均零匹配，确认没有任何代码尝试构造、读取或匹配该枚举值。
5. **测试**：相关测试已在 S1 implementation 阶段更新（`test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint` 等），不再依赖此枚举值。

---

### P3-C-S1-CR-F03：`accepted_compact_business_texts()` 删除

**结论：PASS — fix 完整闭环。**

独立 source scan 结果：

```
rg -n "accepted_compact_business_texts" dayu tests
→ 零匹配
```

逐层验证：

1. **函数定义**：已从 `compact_payload.py` 完全删除。
2. **测试断言**：`test_context_compact_events.py` 中不再有 `accepted_compact_business_texts` 调用。
3. **假 consumer 扫描**：零匹配，确认未添加任何 fake consumer 维持该函数的存活假象。
4. **S2/S3 提前实现扫描**：

   ```
   rg -n "estimate_post_compact_budget|AcceptedToolEvidenceLLMMaterial|render_accepted_tool_evidence_for_llm|accepted_compact_business_texts" dayu tests
   → 零匹配
   ```

   确认未提前实现 S2 budget estimator、S3 accepted evidence material 或 renderer contract。
5. **S2 后续约束已记录**：fix artifact 明确要求 S2 必须与 `context_budget.estimate_post_compact_budget()` 原子实现 business text traversal，不会复制到其他 S1 consumer。

---

## 额外审查

### Semantic Owner Boundary

- **Persisted candidate read boundary**：`parse_context_compacted_semantic_payload()` 是 parser owner。所有 consumer（`durable/memory.py:_memory_projection_payload_view`、`run_input.py:_memory_projection_event_from_row`、`context_events.py:validate_context_compacted_payload`）均通过该函数获得 typed candidate，不存在绕过 parser 的裸 JSON 字段访问。
- **Label uniqueness**：唯一性校验收束到 parser owner 的 `_required_unique_text_list`。typed constructor 中的 `_require_non_empty_unique_string_tuple` / `_require_unique_string_tuple` 作为二次防御存在，但 primary enforcement 已前移到 parser。
- **Field name constants**：`_PAYLOAD_FIELD_*` 常量从 `memory.py` 移除，收束到 `compact_payload.py` parser owner。`memory.py` 不再持有 candidate JSON field name 常量，确认 semantic ownership 未漂移。
- **已知 residual**：`compact_material.py` 仍持有自己的 `_PAYLOAD_FIELD_*` 常量（`compact_material.py:110-129`）并独立解析 `accepted_candidate` JSON。这是 P3-C S2 的已知工作，不在本次 fix scope 内，fix 亦未扩大此问题。

### Durable State / Schema Consistency

- Schema version 从 20 → 21（`durable/schema.py:34`），但此变更为 `host_runs.cancel_request_event_id` DDL 新增，不属于 P3-C S1 scope。P3-C S1 未修改 durable table schema。
- `host_memory_diagnostics` 表的 reason CHECK 约束不再包含 `evidence_backed_fact_candidate_invalid`（已确认零匹配）。
- Snapshot JSON codec（`memory.py` 中 `_forward_intent_to_json_value` / `_reference_item_to_json_value` / 对应 `from_json` 函数）使用 `.value` 序列化、`StrEnum(str)` 反序列化，输出与旧 `str` 值一致，向下兼容已有 snapshot 数据。

### Typed Enum Projection

- `ForwardIntent.intent_type`：`str` → `ForwardIntentTypeVNext`
- `ForwardIntent.status`：`str` → `ForwardIntentStatusVNext`
- `ReferenceContinuityItem.reason`：`str` → `ReferenceContinuityReasonVNext`
- 所有消费者一致使用 typed enum：
  - Memory model（`memory.py:600,602,410`）：typed field + `isinstance` 校验
  - Durable table 序列化（`durable/memory.py`）：`.value`
  - Snapshot JSON 序列化/反序列化（`memory.py`）：`.value` / `StrEnum(str)`
  - LLM-facing 消息（`run_input.py:2392-2393,2412`）：`.value`
  - 测试 fixtures（`test_context_compact_events.py`、`test_compact_material.py`、`test_run_input_builder.py`、`memory_snapshot_factories.py`）：typed enum 字面量

### LLM-facing Material 不被裸 ref/digest 替代

验证两条关键 LLM-facing 渲染路径：

- `_memory_forward_intent_message`（`run_input.py:2390-2394`）：
  ```
  f"type={intent.intent_type.value}; status={intent.status.value}; text={intent.text}"
  ```
  输出示例：`forward_intent=type=next_step_note; status=open; text=Compare quarters next.` — 全部为 LLM 可读业务文本。

- `_memory_reference_continuity_message`（`run_input.py:2411-2413`）：
  ```
  f"reference_continuity=reason={item.reason.value}; text={item.text}"
  ```
  输出示例：`reference_continuity=reason=local_reference; text=Keep revenue comparison context.` — 全部为 LLM 可读业务文本。

- 内部治理标识（`event_id`、`digest`、`payload_ref`）未进入 LLM-facing message body。`run_input.py:350` 明确注释 "digest，仅用于 provider 内部去重，不进入 LLM-facing messages"。

### README 触发判断

修改触及 `dayu/host/` 目录。验证 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`：

- 当前 README 已描述 "persisted accepted compact candidate 在唯一 strict typed read boundary 恢复，非法 shape、digest 或 enum fail closed，Memory projection 不再自行解释 nested candidate JSON"。
- 本次 fix 仅改进 parser diagnostic path 精度、删除 dead diagnostic reason、删除无 consumer helper。这些不改变 Host 稳定开发接口、公共契约或架构说明。
- 结论：README 无需更新，判断正确。

### Tests 是否跟随 Owner Boundary

- Parser owner 测试（`test_context_compact_events.py`）：新增 `test_compacted_semantic_parser_rejects_empty_summary_source_labels_with_path`、`test_compacted_semantic_parser_rejects_duplicate_fact_labels_with_indexed_path`（参数化两条）、`test_compacted_semantic_parser_rejects_duplicate_intent_source_labels_with_indexed_path`，全部落在 parser owner 边界验证重复/空 label 的 fail-closed 行为。
- Memory projection 测试（`test_memory_projection.py`）：`test_snapshot_json_rejects_invalid_compact_enum`、`test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint` 验证 enumeration fail-closed 传导到 checkpoint 行为。
- 测试 fixtures（`memory_snapshot_factories.py`、`test_compact_material.py`、`test_run_input_builder.py`）：enum 字面量迁移，无逻辑变更。
- 删除的测试：`test_accepted_compact_preserves_budget_diagnostic_before_invalid_fact`、`test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels`（因 empty evidence_labels 现在在 parser boundary fail closed，测试前提不再成立）。删除理由正确，不是为掩盖 regression。

### Coverage / Pyright 证据

独立验证：

```
source .venv/bin/activate && python -m pytest \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compact_material.py -q
→ 259 passed in 1.30s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations
```

Coverage 数据（引用 fix artifact 报告，独立验证一致）：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/host/compact_payload.py` | 80% |
| `dayu/host/context_events.py` | 93% |
| `dayu/host/durable/memory.py` | 86% |
| `dayu/host/durable/schema.py` | 92% |
| `dayu/host/memory.py` | 92% |
| `dayu/host/run_input.py` | 88% |

总覆盖率 89.07%，`--cov-fail-under=80` 通过。Coverage 证据可信。

---

## Propagation Audit

### Nested label/source-label duplicate 语义传播链

```
CONTEXT_COMPACTED.accepted_candidate
  → compact_payload.parse_context_compacted_semantic_payload()
    → _required_unique_text_list(path="accepted_candidate.<section>[i].<field>")
      → typed ConversationCompactOutputVNext constructor（二次防御）
        → ContextCompactedSemanticPayload.accepted_candidate
          → MemoryProjectionEvent.compacted_semantics
            → Conversation Memory projection / snapshot / RunInput renderer
```

一致性结论：duplicate label 在 parser owner fail closed。所有下游 consumer 只接收 typed candidate，不自行解释 nested JSON。未在 Memory、RunInput、测试夹具或展示层添加下游特例。

### Memory diagnostic reason 语义传播链

```
invalid persisted compact fact candidate（已废弃路径）
  → compact_payload parser ValueError（新路径：parser boundary fail closed）
    → projection boundary failure handling
      → 不再生成 MemoryDiagnostic（旧 EVIDENCE_BACKED_FACT_CANDIDATE_INVALID 路径已消除）
```

一致性结论：dead enum member 已从 `MemoryDiagnosticReason` 删除；durable DDL reason allowlist 同步清理；production/test source scan 零匹配。

### S2 business text helper 语义

```
S1: persisted semantic parser → typed candidate（仅此）
S2: typed candidate → context_budget.estimate_post_compact_budget()（待原子实现）
```

一致性结论：S1 不保留无 consumer traversal helper；未添加假 consumer；未复制 traversal 到其他 S1 consumer。

---

## Findings

未发现实质性问题。

三项 accepted findings（P3-C-S1-CR-F01/F02/F03）均完整闭环。Fix 未引入新 material regression。

## Open Questions

无。

## Residual Risk

1. **`compact_material.py` 独立 candidate 解析未迁移**（已知 S2 residual）：`compact_material.py` 仍持有自己的 `_PAYLOAD_FIELD_*` 常量（`compact_material.py:110-129`）并独立解析 `accepted_candidate` JSON。同一 `CONTEXT_COMPACTED` payload 仍有两个 read boundary（parser + compact_material）。本次 fix 未扩大此窗口期风险，也未缩小。S2 迁移前若有人修改 `ConversationCompactOutputVNext.to_json()` 字段名，`compact_material.py` 的 previous view 解析将静默失效。

2. **`allow_empty=True` 路径无显式 positive 测试**：当前 `_candidate()` fixture 中 fact 和 diagnostic 的 `source_labels` 均为非空。parser 的 `allow_empty=True` 分支（接收空 list）仅通过 typed constructor 的 `_require_unique_string_tuple` 间接验证，无显式 parser-level 正例测试。风险极低——如果 `allow_empty=True` 行为错误（例如意外拒绝空 list），roundtrip 测试不会捕获，但 typed constructor 的校验会提供二次防御。

3. **旧 snapshot durable 数据兼容性**：snapshot JSON 中 `intent_type`/`status`/`reason` 从 `str` 改为 `StrEnum(str)` 反序列化——若存在手工插入的非合法 enum 值，反序列化 fail closed。当前无证据表明存在此类数据，且 fix 未改变此风险面。

4. **`_previous_compacted_forward_intents_vnext` / `_previous_compacted_reference_continuity_vnext`**（`compact_material.py:3276,3290+`）：这些函数仍从 raw candidate JSON 解析 forward intents 和 reference continuity items，使用 compact_material 自己的 field name 常量。它们不经过 `parse_context_compacted_semantic_payload`，因此不受 parser 的 enum/label 校验保护。S2 迁移前若数据损坏，compact_material previous view 可能产生误导性输出。S2 需将这些消费者迁移到 typed candidate。

---

## 结论

**PASS** — 三项 accepted findings（P3-C-S1-CR-F01/F02/F03）全部完整闭环，fix 未引入新 material regression。

- 259 tests passed，pyright 0 errors
- 所有移除符号（`EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`、`evidence_backed_fact_candidate_invalid`、`accepted_compact_business_texts`）production/test source scan 零匹配
- Parser owner `_required_unique_text_list` 覆盖全部七处 nested label/source-label 字段，错误路径保留完整 indexed JSON path
- Semantic owner boundary、durable state/schema、typed enum projection、LLM-facing material 一致性验证通过
- Residual risk 均为已知 S2/S3 deferred scope，无新引入风险

可 proceed 到下一 gate。
