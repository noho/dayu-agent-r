# Code Re-Review — Phase 12.6 Slice 1

**结论: PASS**

## Scope

- **Mode**: current changes (workspace diff against HEAD)
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Base**: HEAD (8749be9 gateflow: accept plan fix for P12.6 slice 1)
- **Gate**: code re-review — verify accepted findings D-F1, D-F2, D-F3, M-F3 are fixed; verify rejected MiMo base-mismatch findings do not apply to current diff; ensure no new regressions
- **Output file**: docs/reviews/p12-6-slice1-code-rereview-mimo-20260524.md
- **Included scope**: 19 files in current workspace diff against HEAD
- **Excluded scope**: Committed changes at HEAD; files not in current workspace diff
- **Parallel review coverage**: 无

## Accepted Findings Verification

### D-F1: `CONTEXT_COMPACTED` payload writer/reader divergent evidence ref keys — 已修复 ✓

- **验证方式**: `rg accepted_evidence_refs dayu/host/run_input.py` → 0 matches; `rg canonical_evidence_refs dayu/host/run_input.py` → 3 matches (constant definition line 115, usage lines 2160/2167)
- **实际变更**: `run_input.py` diff 仅 4 处修改：常量名 `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_REFS` → `_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS`，值 `"canonical_evidence_refs"`，局部变量名和 f-string 同步更新。变更范围精准，未引入 Slice 6 scope creep
- **跨组件一致性**: `context_events.py:85` 写入 key `"canonical_evidence_refs"`，`run_input.py:115/2160` 读取同一 key。writer/reader 现在使用相同 payload key
- **测试覆盖**: `test_run_input_builder.py` 新增 focused coverage 验证读取 `canonical_evidence_refs`

### D-F2: `_range_tuple` 对空 canonical source refs 的隐式 IndexError — 已修复 ✓

- **验证方式**: `llm_compaction.py:806-807` 新增显式校验
- **实际变更**:
  ```python
  if len(entry.canonical_source_refs) == 0:
      raise ValueError(f"{field_name} label has no canonical source refs: {label}")
  ```
- **错误语义**: `ValueError` 替代隐式 `IndexError`，错误信息包含 `field_name` 和 `label`，可直接定位问题 material provenance entry
- **测试覆盖**: `test_llm_compaction.py` 新增 focused coverage 验证空 canonical source refs 抛出 `ValueError`

### D-F3: `context_events.py` 常量名与 payload key 不一致 — 已修复 ✓

- **验证方式**: `rg "accepted_evidence" dayu/host/context_events.py` → 0 matches (仅旧字段拒绝逻辑中的 `_FIELD_OLD_*` 常量保留 `OLD` 前缀，这是正确的 payload 兼容性校验)
- **实际变更**:
  - `_FIELD_ACCEPTED_EVIDENCE_REFS` → `_FIELD_CANONICAL_EVIDENCE_REFS` (line 85)
  - `_FIELD_ACCEPTED_EVIDENCE_REFS_RETAINED` → `_FIELD_CANONICAL_EVIDENCE_REFS_RETAINED` (line 111)
  - `_FIELD_RETAINED_ACCEPTED_EVIDENCE_REFS` → `_FIELD_RETAINED_CANONICAL_EVIDENCE_REFS` (line 117)
- **payload key 值未变**: 常量值仍为 `"canonical_evidence_refs"` / `"canonical_evidence_refs_retained"` / `"retained_canonical_evidence_refs"`，纯重命名，无行为变更

### M-F3: 测试 docstring 残留 `accepted_evidence_envelopes` — 已修复 ✓

- **验证方式**: `rg "accepted_evidence_envelopes" tests/` → 0 matches
- **实际变更**: docstring 已更新为当前 evidence material / canonical evidence 语义

## Rejected MiMo Findings 验证

### M-F1 (Rejected): `run_input.py` / `memory.py` 修改超出 Slice 1 boundary — 不适用 ✓

- **验证**: `git diff HEAD --name-only` 确认 `memory.py` 不在当前 diff 中。`run_input.py` 在 diff 中，但仅为 D-F1 修复的 4 处精准修改（常量重命名 + 变量同步），不是 Slice 6 的 memory projection 重构
- **结论**: base correction 有效，M-F1 描述的问题不在当前 diff 范围内

### M-F2 (Rejected): 18 个未授权测试文件被修改 — 不适用 ✓

- **验证**: `git diff HEAD --name-only -- tests/` 显示 8 个测试文件，均属于 Slice 1 允许列表或 D-F1/D-F2/D-F3/M-F3 修复引入的 focused test
- **结论**: base correction 有效，M-F2 描述的问题不在当前 diff 范围内

## 回归检查

### 旧 CompactionRequest 字段删除完整性 ✓

- `rg "input_event_refs|current_message_summary|compact_raw_context_items|accepted_evidence_envelopes" dayu/host/ tests/` → 0 matches
- 旧类型 `CompactRawContextItem` / `CompactRawContextKind` / `CurrentMessageSummary` 全仓 0 matches
- 无兼容别名、compat re-export 或 wrapper 残留

### Prompt-local label / provenance 映射完整性 ✓

- `compact_material.py` 仍是 label 生成和校验的唯一 owner
- `llm_compaction.py` 通过 `provenance_map` 将 prompt-local labels 映射为 canonical refs
- 未知 label → `ValueError`；空 canonical_source_refs → `ValueError`（D-F2 修复）
- `_canonical_evidence_refs_for_labels` 对 evidence label 无 `accepted_evidence_id` → `ValueError`

### API boundary 无漂移 ✓

- `run_input.py` 变更仅限常量重命名和局部变量同步，未修改函数签名或公共契约
- 未修改 `dayu/host/api.py`、`OpenHostOptions`、`SubmitFollowupRequest` 或 Engine public contracts

### 测试与类型检查 ✓

- 178 tests passed (8 个 Slice 1 相关测试文件)
- pyright 0 errors, 0 warnings, 0 informations (10 个文件)

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Segment selection 占位实现**: `initial_segment_selection` 选择 material pack 中所有 labels，不做 already-represented pruning 或 budget-based selection。按 plan 延期至 Slice 2。
- **Memory snapshot cursor 未校验**: `memory_snapshot_cursor=None`。按 plan 延期至 Slice 2。
- **Evidence raw_result_text JSON encoding**: LLM-facing text 使用 JSON 编码，可读性不如 display text。已知延期至 Slice 3。
