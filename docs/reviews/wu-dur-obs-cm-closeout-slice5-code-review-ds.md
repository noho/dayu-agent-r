# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice5-code-review-ds.md`
- Review date: 2026-06-05
- Included scope:
  - `dayu/host/compaction_evidence.py` — `_readable_query_text()` 及辅助函数（limited-signal、bounded、同源校验）
  - `tests/host/test_compaction_operation.py` — Slice 5 新增 focused tests
  - `dayu/host/README.md` — Context Compaction 段 query_text 行为同步
  - `tests/README.md` — test coverage 清单同步
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — control doc 更新不在本次 review scope
  - Slice 0-4, Slice 6-7 已实现/待实现内容
  - `dayu/host/compact_material.py`, `dayu/host/compaction.py` — 未修改，仅作为消费方验证
- Plan source: `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 5 (lines 547-558)
- Implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice5-implementation-codex.md`

## Findings

### 未发现实质性 blocking 问题

经逐行走读 `_readable_query_text()` 全部六条分支、同源校验 `_request_atoms_match_envelope()`、
参数解析链路 `tool_call_request_atoms()` → `_read_arguments_json()` / `_read_semantic_query()`、
chunking 消费路径 `build_initial_material_pack()` → `_evidence_chunks()` → `CompactEvidenceBlock`
→ `EvidenceReadableItemVNext`，以及 tests 中所有 focused coverage 路径，**未发现 correctness、
stability 或 maintainability 级别 blocking defect**。

以下逐项回应对照 review requirements 的验证结果，以及识别的 residual risks / test gaps。

---

### Review Point 逐项验证

#### 1. query_text 必须从 durable TOOL_CALL_REQUESTED atoms 通过 tool_call_requested_event_ref 派生

**通过。** `compaction_evidence.py:296-328` 的 `_readable_query_text()` 完整读取路径：

1. `requested_ref = envelope.tool_query.tool_call_requested_event_ref` (line 296) — 从 envelope 取 ref
2. `request_row = event_log_store.read_event_by_id(transaction, requested_ref)` (line 302) — 从 EventLog 读 request event
3. `atoms = tool_call_request_atoms(transaction, request_row)` (line 314) — 解析 durable atoms（含 `arguments_json`、`semantic_query_text`）

全程不接触 `raw_tool_outcome`、`result_preview` 或 tool result content。`_reject_result_preview()` (line 269-278) 主动拒绝旧 `result_preview` 字段。

#### 2. semantic_query_text 必须优先于 arguments fallback

**通过。** `compaction_evidence.py:325-329`:

```python
if atoms.semantic_query_text is not None:
    return _bounded_query_text(atoms.semantic_query_text)
return _bounded_query_text(
    f"{_READABLE_ARGUMENTS_PREFIX}{canonical_json_dumps(atoms.arguments_json)}"
)
```

测试 `test_evidence_input_prefers_semantic_query_from_tool_request_atom` (test:1417-1476) 验证了 semantic query 优先输出。

#### 3. arguments fallback 必须有界、canonical、业务可读，不暴露 Host 内部 refs/digests/cursors

**通过。** Fallback 输出 `工具参数: {"arguments":{...}}`：
- `工具参数: ` 前缀 (line 49) 为业务中文标识
- `canonical_json_dumps(atoms.arguments_json)` 输出的是 digest-verified canonical JSON preimage，即 `{"arguments": {"company":"MSFT", ...}}` 格式，不含 tool_call_id、event_id、payload_ref、digest、cursor
- `_bounded_query_text()` (line 350-364) 截断到 1200 字符 + `[truncated_query_text]` marker

测试 `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` (test:1311-1414) 验证了 arguments JSON 格式和内容不包含内部 refs。

#### 4. 缺失/不可读/不匹配时必须 emit structured limited-signal，不能静默退化

**通过。** `compaction_evidence.py:296-328` 覆盖所有路径：

| 触发条件 | 行号 | limited-signal reason |
|---|---|---|
| `requested_ref is None` | 298-301 | 已验收工具请求参数材料缺失 |
| `request_row is None` | 303-307 | 已验收工具请求参数材料缺失 |
| session mismatch | 308-312 | 工具请求与当前证据来源不一致 |
| `tool_call_request_atoms` raise | 315-319 | 已验收工具请求参数材料不可验证 |
| `_request_atoms_match_envelope` False | 320-324 | 工具请求与当前证据来源不一致 |

输出格式 `状态=limited_signal；原因=...；说明=...` (line 367-383)，不含任何 Host refs/digests。测试 `test_evidence_input_missing_tool_request_atom_emits_limited_signal` (test:1479-1524) 验证了 missing request atom 时输出 limited-signal 且不暴露 tool_call_id 或 event_id。

#### 5. evidence/request 同源校验必须覆盖 tool_call_id、tool_name、normalized_arguments_digest 和 session boundary

**通过。** `_request_atoms_match_envelope()` (line 332-347) 校验三项字段一致性；session boundary 校验在 line 308-312 (`request_row.session_id != result_row.session_id`)。两项校验正交但互补，构成完整的同源校验链。

#### 6. chunked evidence 必须共享 base query_text，chunk ordinal 只在 label 中

**通过。** `compact_material.py:997-1008` 的 `_evidence_chunks()` 为每 chunk 创建 `CompactEvidenceBlock` 时，`evidence_label` 使用 chunk.label (E1.1/E1.2/E1.3)，但 `readable_query_text` 使用 `material.readable_query_text`（每 chunk 相同）。LLM-facing `EvidenceReadableItemVNext` (line 1906-1916) 中 `source_label` 取自 `block.evidence_label`（含 ordinal），`query_text` 取自 `block.readable_query_text`（共享）。

测试 `test_evidence_chunks_share_same_durable_query_text` (test:1527-1622) 验证三 chunk label 分别为 E1.1/E1.2/E1.3，query_text 均相同。

#### 7. compact candidate output schema 不得变化；result content 不得混入 query_text

**通过。** 未修改 `EvidenceReadableItemVNext`、`CompactEvidenceBlock`、`InitialEvidenceMaterial` 的 schema 字段。raw_result_text 与 readable_query_text 独立赋值（`compaction_evidence.py:237-238`），result content 不进入 query_text 路径。`_reject_result_preview()` 主动拒绝旧字段。

#### 8. tests 不得有 test-only production bridges；README 不得越界

**通过。** 测试通过公开入口 `collect_selected_compaction_request_evidence_inputs()` 调用生产路径，`_collect_selected_query_text()` / `_collect_selected_evidence_ids()` 等为 test-local helper，不修改生产模块。README 变更：`dayu/host/README.md` 在 Context Compaction 段补充一句 query_text 行为说明（符合 Host 开发手册职责）；`tests/README.md` 在 test coverage 清单补充 "accepted evidence query_text 消费 durable tool-call request atoms"（符合测试手册职责）。均未越界。

---

## Open Questions

1. **`_LIMITED_SIGNAL_DETAIL_UNAVAILABLE` 在两个不同路径复用**：`requested_ref is None` (line 296) 和 `request_row is None` (line 302) 使用相同的 detail 文本 `"无法从已验收工具请求恢复查询参数"`。这两个场景语义不同（ref 缺失 vs. ref 指向不存在的事件），当前 detail 无法区分。未来如需更精确诊断可能需要分列。当前不构成 functional defect，因为 reason 字段相同（`_LIMITED_SIGNAL_REASON_MISSING_ARGUMENTS`），且两者都意味着"缺少请求材料"。

2. **`_bounded_query_text` 的 whitespace 规范化可能影响 semantic_query_text 格式**：line 358 的 `" ".join(text.split())` 会将所有 whitespace（包括换行）折叠为单空格。若 future semantic_query_text 包含有意义的换行或缩进格式，会被丢弃。当前所有测试中的 semantic_query_text 均为单行中文，不受影响。建议在 spec 中明确 semantic_query_text 应为单行文本。

## Residual Risk

1. **Session boundary mismatch path 无直接 focused test**：`_readable_query_text()` line 308-312 的跨 Session 同源校验仅在现有代码路径中存在，无独立测试覆盖该分支。低风险——Session mismatch 场景在生产环境中极少发生（request event 和 result event 在正常流程中必定同 Session），且该分支输出 limited-signal（fail-safe），不会导致错误 query_text 被投影给 LLM。

2. **`_request_atoms_match_envelope` 返回 False 分支无直接 focused test**：tool_call_id / tool_name / normalized_arguments_digest 与 envelope 不匹配的路径未被独立测试覆盖。低风险——该路径同样输出 limited-signal（fail-safe），且 `tool_call_request_atoms()` 的 digest 校验链已在 `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` 中验证 arguments digest 一致性。

3. **`tool_call_event_ref` 字段在无 request ref 时的回退值语义不精确**：`compaction_evidence.py:228` 行 `tool_call_event_ref=(envelope.tool_query.tool_call_requested_event_ref or row.event_id)`，当 request ref 为 None 时，回退到 `row.event_id`（即 TOOL_RESULT_ACCEPTED event id）。`InitialEvidenceMaterial.tool_call_event_ref` 的 docstring 描述为 "TOOL_CALL_REQUESTED event ref"，但此回退值实际指向 TOOL_RESULT_ACCEPTED 事件。当前 `_readable_query_text()` 不使用此字段（独立解析 ref），故不产生功能影响，但 downstream consumer 若信任该字段语义可能被误导。建议：要么将该字段类型改为 `str | None` 并在此场景设为 None，要么在 docstring 中说明回退语义。低 risk——当前无已知 consumer 依赖此字段的正确 TOOL_CALL_REQUESTED 语义，且该路径已通过 `_readable_query_text()` 输出 limited-signal。

4. **暂无 test 覆盖 `_bounded_query_text` 的截断边界**：当 query_text 恰好等于或略超 `_READABLE_QUERY_TEXT_MAX_CHARS` (1200) 时，截断行为无直接断言。低风险——截断逻辑简单，`_bounded_query_text` 为纯函数，无外部依赖，且被所有 query_text 输出路径间接覆盖。

## Verdict

**PASS** — Slice 5 实现满足 plan 中所有 invariants 和 review requirements。无 blocking findings。建议接受当前实现，可选在后续 slice 或独立 maintenance 中处理 residual risk 项 3（`tool_call_event_ref` 回退值语义）。
