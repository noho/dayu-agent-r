# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Code Re-Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: main
- Output file: docs/reviews/wu-semantic-ownership-01-p3-c-s1-rereview-mimo.md
- Included scope:
  - `dayu/host/compact_payload.py`
  - `dayu/host/memory.py`
  - `dayu/host/durable/schema.py`
  - `tests/host/test_context_compact_events.py`
- Excluded scope: S2/S3 contract、controller artifact、README
- Parallel review coverage: 无

## Review Inputs

- controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-code-review-controller-adjudication.md`
- fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-fix-codex.md`
- controller validation: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-fix-controller-validation.md`
- accepted plan: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`

## Findings

未发现实质性问题。

## Accepted Findings 复核

### P3-C-S1-CR-F01 — Path-aware nested label validation

**复核结论：PASS**

证据链：

1. **单一 path-aware helper 已实现**：`compact_payload.py:850-875` 新增 `_required_unique_text_list(payload, field_name, *, path, allow_empty=False)`，复用 `_required_text_list` 后做非空与唯一性检查，duplicate 时报告 `{path}[{index}] must be unique`。

2. **覆盖所有需要唯一性的 nested label/source-label lists**：
   - `session_summary.source_labels`（第 254-259 行）
   - `evidence_backed_facts[*].evidence_labels`（第 280-284 行）
   - `evidence_backed_facts[*].source_labels`（第 288-293 行，`allow_empty=True`）
   - `answer_anchors[*].answer_source_labels`（第 324-328 行）
   - `forward_intents[*].source_labels`（第 379-383 行）
   - `reference_continuity_items[*].source_labels`（第 410-414 行）
   - `diagnostics[*].source_labels`（第 436-441 行，`allow_empty=True`）

3. **错误路径保留完整 indexed JSON path**：所有 path 从 `accepted_candidate` 根开始，格式为 `accepted_candidate.<section>[i].<field>` 或 `accepted_candidate.<section>[i].<field>[j]`。

4. **不是 fact-only 特例**：测试覆盖了 `forward_intents[*].source_labels` duplicate（第 265-282 行），证明修复适用于所有 nested label 类型。

5. **optional list 处理正确**：`evidence_backed_facts[*].source_labels` 和 `diagnostics[*].source_labels` 使用 `allow_empty=True`，符合 typed contract。

### P3-C-S1-CR-F02 — Dead Memory diagnostic enum

**复核结论：PASS**

证据链：

1. **enum member 已移除**：`memory.py:157-170` `MemoryDiagnosticReason` 中无 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`。

2. **durable DDL allowlist 已同步**：`schema.py:977-1004` `_HOST_MEMORY_DIAGNOSTICS_DDL` 的 reason CHECK 约束不包含 `evidence_backed_fact_candidate_invalid`。

3. **source scan 零匹配**：
   - `rg -n "EVIDENCE_BACKED_FACT_CANDIDATE_INVALID|evidence_backed_fact_candidate_invalid" dayu tests` → zero match。

### P3-C-S1-CR-F03 — Contract-only business text helper

**复核结论：PASS**

证据链：

1. **helper 已删除**：`compact_payload.py` 中无 `accepted_compact_business_texts` 函数。

2. **S1-only test 已删除**：`test_context_compact_events.py` 中无 `accepted_compact_business_texts` 相关断言。

3. **无假 consumer**：`rg -n "accepted_compact_business_texts" dayu tests` → zero match。

4. **无 S2/S3 contract 提前落地**：
   - `rg -n "estimate_post_compact_budget|AcceptedToolEvidenceLLMMaterial|render_accepted_tool_evidence_for_llm|accepted_compact_business_texts" dayu tests` → zero match。

## 额外审查

### Semantic owner boundary

修复落在 parser owner（`compact_payload.py`）与 durable diagnostic contract（`memory.py`、`durable/schema.py`）。未在 Memory、RunInput、测试夹具或展示层添加下游特例。

### Durable state/schema consistency

`MemoryDiagnosticReason` enum 成员与 `_HOST_MEMORY_DIAGNOSTICS_DDL` reason CHECK 约束保持同步。dead enum 删除后，durable schema 不再包含该值。

### Typed enum projection

`MemoryDiagnosticReason` 仍为 `StrEnum`，JSON 序列化/反序列化路径不变。

### LLM-facing material

无裸 ref/digest 替代 LLM-facing 文本。`_required_unique_text_list` 的错误消息是 developer-facing，不进入 LLM 上下文。

### README 触发判断

触发规则：`dayu/host/` 修改 → 检查 `dayu/host/README.md`。

已读取 README 的 `Agent更新约束【必须遵守】`。本次修改是：
- 补 parser diagnostic path 精度
- 删除 dead diagnostic reason
- 删除无 consumer helper

不改变 Host 稳定开发接口、公共契约或架构说明，不修改 README。

### Tests 跟随 owner boundary

新增测试在 `test_context_compact_events.py` 中，位于 parser owner 的测试边界内，覆盖了：
- summary empty `source_labels` parser-owner path 回归（第 214-228 行）
- fact `evidence_labels` / `source_labels` duplicate indexed path 回归（第 231-262 行）
- `forward_intents[*].source_labels` duplicate indexed path 回归（第 265-282 行）

### Coverage/pyright 证据

- `python -m pytest ... -q` → `259 passed in 1.30s`
- `python -m pyright dayu/host/compact_payload.py dayu/host/memory.py dayu/host/durable/schema.py` → `0 errors, 0 warnings, 0 informations`

## Open Questions

无。

## Residual Risk

- `covered by later approved slice`：S2 previous compacted view、ordinary duplicate compact renderer、post-compact budget helper 与 `context_budget.estimate_post_compact_budget()` 原子实现。
- `covered by later approved slice`：S3 accepted evidence typed material、唯一 LLM renderer 与 typed mismatch exception。
- 未分类 residual risk：0。
