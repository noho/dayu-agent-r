# P12.6 Slice 2 Code Re-Review — AgentMiMo

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Re-reviewer: AgentMiMo
- Re-review base: `c0a5b18` (gateflow: accept P12.6 slice 1)
- Re-review scope: workspace diff for P12.6 Slice 2, excluding `docs/host/implementation-control.md`
- Source artifacts:
  - `docs/reviews/p12-6-slice2-code-review-controller-adjudication-20260524.md`
  - `docs/reviews/p12-6-slice2-fix-codex-20260524.md`
  - `docs/reviews/p12-6-slice2-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice2-code-review-ds-20260524.md`
- Date: 2026-05-24

## Verdict: PASS

三项 accepted findings (A1 / A2 / A3) 均已按 controller adjudication 要求完成修复，未引入新回归。Deferred items 确认不需本轮修复。

---

## Accepted Findings 修复验证

### A1 — renderer/classifier 共享 header source

- **状态**: PASS
- **证据**: `dayu/host/run_input.py:131-140` 定义模块级 header 常量：
  - `_MEMORY_USER_GOALS_HEADER`
  - `_MEMORY_CONFIRMED_SUBJECTS_HEADER`
  - `_MEMORY_EVIDENCE_BACKED_FACTS_HEADER`
  - `_MEMORY_QUESTIONS_AND_ASSUMPTIONS_HEADER`
  - `_MEMORY_MINIMUM_PRESERVE_HEADER`
  - `_MEMORY_EPISODE_SUMMARIES_HEADER`
- **验证**: `_memory_material_kind` (`run_input.py:2075-2093`) 使用 `content.startswith(_MEMORY_EVIDENCE_BACKED_FACTS_HEADER)` 等引用同一常量；renderer 函数 `_memory_evidence_backed_fact_message`、`_memory_question_and_assumption_message`、`_memory_episode_summary_message` 也引用同一常量。不再有孤立硬编码前缀分支。
- **回归**: 无。

### A2 — inline delta gate 只用 `max_lag_events_for_inline_delta`

- **状态**: PASS
- **证据**: `dayu/host/compact_material.py:687` 条件为：
  ```python
  if lag_events > policy.max_lag_events_for_inline_delta:
  ```
  已删除 `or lag_events > policy.max_delta_repair_events` 附加硬门槛。
- **新增测试**: `test_compact_material.py:246-268` `test_snapshot_cursor_inline_delta_uses_inline_lag_threshold_only` 覆盖 lag 在 inline 阈值内（`max_lag_events_for_inline_delta=2`）但超过 delta repair budget（`max_delta_repair_events=1`）时仍接受 inline delta view。断言 `result.inline_delta_repair_view is not None`。
- **注意**: `DurableMemorySnapshotProvider._load_memory_snapshot_tx` (`run_input.py:744-746`) 仍保留 `or lag_events > self._policy.max_delta_repair_events` 条件。该 provider 是 production wiring path 的独立实现，不在 Slice 2 controller adjudication 范围内（adjudication 明确针对 `check_compact_memory_snapshot_cursor`），不构成本 slice 回归。
- **回归**: 无。

### A3 — `excluded_reason_codes` key 注解语义

- **状态**: PASS
- **证据**: `dayu/host/compaction.py:600` 注解为：
  ```python
  excluded_reason_codes: Mapping[str, str] = field(default_factory=dict)
  ```
  已从 `Mapping[PromptLocalMaterialLabel, str]` 改为 `Mapping[str, str]`，docstring (line 589) 描述为"被排除 block id 到 reason code 的映射"，语义一致。
- **回归**: 无。运行时 shape 未变，仍为字符串到字符串的只读 mapping。

---

## Deferred Items 确认

| Item | 状态 | 说明 |
|------|------|------|
| DS M3 `event_sequence=None` | Deferred to Slice 5 | continuity / compact blocks 仍为 `event_sequence=None`，与裁决一致 |
| Snapshot text escaping | Non-blocking residual | 未修改，与裁决一致 |
| Stable kind ordering | Non-blocking residual | `_BLOCK_KIND_ORDER` stable kinds 全为 0，未修改，与裁决一致 |

---

## 回归检查

### 测试

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
# 93 passed in 1.78s
```

93 passed（原 92 + 新增 1 个 A2 测试），无失败。

### Pyright

```bash
python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/compaction.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
# 0 errors, 0 warnings, 0 informations
```

### Git diff check

```bash
git diff --check
# passed
```

### 禁止模式检查

- `hasattr` / `getattr` / `Any` / `object`: 无新增违规。
- 兼容性 wrapper / facade: 无。
- 反向依赖: 无。

---

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| A1 renderer/classifier 共享 header source | PASS |
| A2 inline delta gate 只用 max_lag_events_for_inline_delta | PASS |
| A3 excluded_reason_codes key 注解语义 | PASS |
| Deferred items 不需本轮修复 | CONFIRMED |
| 测试 93 passed | PASS |
| Pyright 0 errors | PASS |
| git diff --check | PASS |
| 无新回归 | PASS |
