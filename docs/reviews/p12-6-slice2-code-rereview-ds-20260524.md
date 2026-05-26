# P12.6 Slice 2 Code Re-Review — AgentDS

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Re-review role: AgentDS (code re-reviewer, 不改代码/不提交/不 push)
- Review base: HEAD = `c0a5b18` (P12.6 Slice 1 accepted)
- Source artifacts:
  - `docs/reviews/p12-6-slice2-code-review-controller-adjudication-20260524.md`
  - `docs/reviews/p12-6-slice2-fix-codex-20260524.md`
  - `docs/reviews/p12-6-slice2-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice2-code-review-ds-20260524.md`
- Scope: workspace diff for P12.6 Slice 2 (excluding `docs/host/implementation-control.md`)

## Verdict

**PASS** — 三项 accepted findings (A1/A2/A3) 全部修复到位，deferred items 不需本轮修复，无新引入回归。

---

## 1. Accepted Findings 验证

### A1 — ✅ VERIFIED: renderer/classifier 共享 header source

**文件**: `dayu/host/run_input.py`

**证据**:
- 模块级常量定义 (L131–L140): `_MEMORY_EVIDENCE_BACKED_FACTS_HEADER`, `_MEMORY_QUESTIONS_AND_ASSUMPTIONS_HEADER`, `_MEMORY_EPISODE_SUMMARIES_HEADER`
- 渲染端引用: `_build_memory_evidence_facts_message` (L1788), `_build_memory_questions_assumptions_message` (L1814), `_build_memory_episode_summaries_message` (L1923)
- 分类器 `_memory_material_kind` (L2075–L2093) 引用: L2083 (`_MEMORY_EVIDENCE_BACKED_FACTS_HEADER`), L2085 (`_MEMORY_QUESTIONS_AND_ASSUMPTIONS_HEADER`), L2087 (`_MEMORY_EPISODE_SUMMARIES_HEADER`)

**结论**: 渲染端与分类器共享同一组 typed module-level 常量。不再有孤立硬编码前缀分支。修复完整。

### A2 — ✅ VERIFIED: inline delta gate 只用 `max_lag_events_for_inline_delta`

**文件**: `dayu/host/compact_material.py` (L687)

**证据**:
```python
if lag_events > policy.max_lag_events_for_inline_delta:
```
原 `or lag_events > policy.max_delta_repair_events` 条件已删除。

**测试覆盖** (`tests/host/test_compact_material.py` L246–L268):
- `test_snapshot_cursor_inline_delta_uses_inline_lag_threshold_only`
- 配置: `max_lag_events_for_inline_delta=2`, `max_delta_repair_events=1`, lag=2
- lag=2 在 inline 阈值内 (≤2) 但超过 delta repair budget (2>1)
- 断言: inline delta 被接受 (`result.snapshot.cursor.checkpoint_event_sequence == 4`, `result.inline_delta_repair_view is not None`)

**结论**: 修复完整。行为与 plan §6.6 一致。

### A3 — ✅ VERIFIED: `excluded_reason_codes` key 注解语义纠正

**文件**: `dayu/host/compaction.py` (L600)

**证据**:
```python
excluded_reason_codes: Mapping[str, str] = field(default_factory=dict)
```
原 `Mapping[PromptLocalMaterialLabel, str]` 已改为 `Mapping[str, str]`。docstring 中 "被排除 block id 到 reason code 的映射" 与注解语义一致。

**结论**: 修复完整。不再误导为 prompt-local label。

---

## 2. Deferred Items 确认

### D1 (DS M3): `event_sequence=None` for continuity/compact blocks

**状态**: 维持 deferred，不需本轮修复。

**证据** (`dayu/host/run_input.py` L2001, L2014, L2027):
```python
event_sequence=None,
```
Controller 裁决 deferred 到 Slice 5 wiring。当前 Slice 2 通过 `block_id` tie-breaker 保证确定性，event_sequence=None 不影响 correctness。

### D2 (DS L1): `_snapshot_goal_text` 引用 `subject.ref_kind.value`

**状态**: 已在前次 DS 审查中被 controller 判定为 rejected（ref_kind 为 `HostNeutralRefKind` StrEnum）。本次不涉及。

### D3 (DS L2 / I1): snapshot text escaping / stable kind ordering

**状态**: controller 判定为 non-blocking residual。本次 fix 未修改相关代码，维持原状。

---

## 3. 回归检查

### 3.1 测试

```bash
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py -q
# 93 passed in 1.82s
```

原 DS 审查时 92 passed，现在 93 passed（+1 A2 新测试）。无测试回退。

### 3.2 类型检查

```bash
python -m pyright dayu/host/compact_material.py dayu/host/run_input.py \
  dayu/host/memory.py dayu/host/memory_repair.py \
  tests/host/test_compact_material.py tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py
# 0 errors, 0 warnings, 0 informations
```

### 3.3 Git diff

```bash
git diff --check
# clean, no whitespace errors
```

### 3.4 变更范围

修复严格限定在 controller 指定的文件：
- `dayu/host/run_input.py` (A1)
- `dayu/host/compact_material.py` (A2)
- `dayu/host/compaction.py` (A3)
- `tests/host/test_compact_material.py` (A2 测试)

无越界变更，无 public API 变更。

### 3.5 禁止模式

- 无 `Any` / `object` / `hasattr` / `getattr` 新增使用
- 无 lazy seam 引入
- 无兼容性 wrapper/re-export
- 无魔法字符串（A1 将原硬编码字符串提升为模块常量，反而减少了魔法字符串）

---

## 4. Validation Summary

| 检查项 | 状态 |
|--------|------|
| A1: shared header constants | ✅ |
| A2: inline delta gate | ✅ |
| A3: excluded_reason_codes annotation | ✅ |
| A2 test coverage (lag in inline threshold, exceeds repair budget) | ✅ |
| Deferred items 不需本轮修复 | ✅ |
| 93 tests passed | ✅ |
| pyright 0 errors | ✅ |
| git diff --check clean | ✅ |
| 无越界变更 | ✅ |
| 无新增禁止模式 | ✅ |

**Re-review 结论**: PASS。Slice 2 可接受。
