# Phase 10 Slice 3 Adversarial Re-Review — AgentDS

**Re-Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Base Review:** `phase10-s3-code-review-ds-20260518.md`
**Fix Report:** `phase10-s3-code-review-fix-codex-20260518.md`
**Verdict: PASS**

---

## Scope

仅复核 Codex fix 中处理的两项 DS finding：
1. DS M1：`validate_context_compacted_payload` 不拒绝非空 `proposed_verified_fact_refs`
2. DS residual：replace patch value 非法结构只在 memory projection 阶段失败，validator 未提前拒绝

同时回归验证原始审查中的 6 项 adversarial check：
- accepted quality result fail closed
- pinned patch evidence fail closed
- confirmed_subjects opaque ref fail closed
- 未知 patch 字段 fail closed
- memory projection 不新建 verified fact
- 新增测试真实覆盖失败路径

---

## Verification

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 79 passed (原 77) |
| `pyright` | 0 errors, 0 warnings, 0 informations |

---

## Fixed Findings

### M1: `proposed_verified_fact_refs` 非空拒绝 — FIXED

**防御路径:** `context_events.py:273-277`

```python
proposed_fact_refs = _optional_text_list(
    summary, _FIELD_PROPOSED_VERIFIED_FACT_REFS
)
if len(proposed_fact_refs) > 0:
    raise ValueError("compact summary must not propose verified facts")
```

- `_optional_text_list` :568-589 处理三种情况：字段缺失 → 返回 `()`；值为 `null` → 返回 `()`；值为非文本 list → 抛 `ValueError`
- 仅 list 非空时触发 reject

**测试覆盖:** `test_context_compact_events.py:138-147` — 构造 `proposed_verified_fact_refs: ["fake-fact"]`，断言 `ValueError` 匹配 `"must not propose verified facts"`。

**验证结论:** ✅ 修复完整。`proposed_verified_fact_refs` 非空现在在 payload validator 层 fail closed，不再仅依赖 typed builder 默认值与 quality checker。

---

### Residual: replace patch value 提前校验 — FIXED

**防御路径 1:** `_validate_patch_evidence` :638-639 新增调用：

```python
if operation is PinnedPatchOperation.REPLACE:
    _validate_replace_patch_value(value, field_name)
```

**防御路径 2:** `_validate_replace_patch_value` :663-683 按字段类型分发：

| 字段 | 校验 | 行号 |
|------|------|------|
| `current_goal` | `_required_text(patch_field, "value")` — 非空文本 | :674-676 |
| `confirmed_subjects` | 每项 `_validate_confirmed_subject_item` — Host-neutral opaque ref | :678-681 |
| `user_constraints` / `open_questions` (及其他) | 每项 `_require_non_empty_text_value` — 非空文本 | :682-683 |

**测试覆盖:** `test_context_compact_events.py:164-175` — `current_goal` replace 但 `del current_goal["value"]`，断言 `ValueError` 匹配 `"value must be non-empty text"`。

**验证结论:** ✅ 修复完整。replace 操作的 value 类型/内容现在在 validator 层提前校验，不再等到 memory projection 才失败。

---

## Regression Verification: 原 6 项 Adversarial Checks

### Check 1: accepted quality result fail closed

`:709-721` 未变 — `_validate_quality_check_result` 仍强制 `accepted=True`、`rejection_reasons` 为空、四个 retention flags 均为 True。

测试 `test_compacted_payload_rejects_rejected_quality_result` 仍通过。✅

### Check 2: pinned patch evidence fail closed

`:611-639` `_validate_patch_evidence` 增强（新增加 replace value 校验），原有 evidence refs 检查保留：
- 非 MISSING 操作必须有非空 evidence refs (:633-635)
- evidence refs 必须在 evidence_ids 内 (:636-637)
- 未知字段 reject (:624-625)
- 非 Mapping 字段 reject (:628-629)

测试 `test_compacted_payload_rejects_patch_without_preservation_evidence` 仍通过。✅

### Check 3: confirmed_subjects opaque ref fail closed

`:642-660` `_validate_confirmed_subject_patch` 未变，仍通过 `_validate_confirmed_subject_item` → `_validate_opaque_ref_text` / `_validate_opaque_ref_kind` 拒绝自由业务字符串。

新增 `_validate_replace_patch_value` :678-681 对 `confirmed_subjects` replace 逐项调用相同验证。

测试 `test_compacted_payload_rejects_free_form_confirmed_subject` 仍通过。✅

### Check 4: 未知 patch 字段 fail closed

`:624-625` `if field_name not in _PATCH_ALLOWED_FIELDS: raise ValueError("pinned patch field is not supported")` 未变。`_PATCH_ALLOWED_FIELDS` :108-116 仍为 `frozenset({candidate_id, current_goal, confirmed_subjects, user_constraints, open_questions})`。

测试 `test_compacted_payload_rejects_direct_patch_field_without_tristate` 仍通过。✅

### Check 5: memory projection 不新建 verified fact

`memory.py:1066-1074` `CONTEXT_COMPACTED` handler 未变：仅调用 `validate_context_compacted_payload`（已增强）、`_validate_compact_summary_fact_refs`、创建 continuity item、更新 pinned state。`verified_facts` 变量仅在 `TOOL_RESULT_ACCEPTED` handler :1053 被修改。

测试 `test_context_compacted_summary_fact_refs_do_not_create_verified_facts` 仍通过。✅

### Check 6: 新增测试覆盖真实失败路径

| 测试 | 覆盖项 | 失败路径真实性 |
|------|--------|---------------|
| `test_compacted_payload_rejects_summary_proposed_verified_fact_refs` (:138) | M1 fix | 手工注入 `proposed_verified_fact_refs: ["fake-fact"]` 到 payload JSON → validator 拒绝。真实绕过 typed builder 的攻击路径。 |
| `test_compacted_payload_rejects_replace_patch_without_value` (:164) | residual fix | 手工 `del current_goal["value"]` → `_required_text` 抛 `ValueError`。模拟恶意构造 replace patch 缺 value 的攻击路径。 |

两次新增测试均直接操作 JSON payload（不经过 typed builder），真实模拟 EventLog 回放或手工构造攻击场景。✅

---

## New Findings

（无）

本次 fix 未引入新的 blocking、high、medium 或 low 问题。两处修复均在 validator 层增加防御，不影响已有测试，不改变 memory projection 或 consumer filter。

---

## Residual Risks

1. **M1 原 residual（open_questions_retained 不作为拒绝原因）** 不属于本次 fix 范围，仍由 Slice 4+ orchestration 决议。
2. **Real LLM compactor adapter 未实现** — Slice 6 范围。
3. **`_PATCH_ALLOWED_FIELDS` frozenset 与 memory.py `_apply_pinned_state_patch_candidate` 字段处理是手工同步** — 当前 4 个字段一致，若新增 pinned 字段需同步两处。这是原始审查 L1 类问题，非本 fix 引入。
4. **`_validate_replace_patch_value` 对未知字段名 fall through 到通用 text tuple 校验** (:682-683) — 当前 `_PATCH_ALLOWED_FIELDS` 内已知字段均正确处理，但若未来新增字段（如新的 opaque ref 类型字段）且未在 `_validate_replace_patch_value` 增加分支，将按 text tuple 校验而非 opaque ref。此为 forward-compatibility 注意项，非当前 bug。

---

## Summary

- **Verdict: PASS**
- **DS M1 (proposed_verified_fact_refs):** ✅ 修复完成，validator 层 fail closed
- **DS residual (replace value 提前校验):** ✅ 修复完成，validator 层提前拒绝
- **原 6 项 adversarial checks:** ✅ 全部回归通过，无退化
- **New findings:** 0
- **Tests:** 79 passed (原 77, +2 new)
- **Pyright:** 0 errors
