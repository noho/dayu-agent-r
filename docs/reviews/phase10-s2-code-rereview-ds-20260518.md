# Phase 10 Slice 2 Code Re-Review — AgentDS

**Re-Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Verdict: PASS**

## Scope

Re-review 仅确认以下总控接受项的修复状态：DS B1 / M1 / M2 / R2，MiMo M1（与 DS B1 同源）。不重新做无限范围审查。

## Verification

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q` | 17 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

---

## Fixed Findings

| 来源 | 编号 | 描述 | 修复验证 |
|------|------|------|----------|
| DS | B1 | `CompactionRequest.__post_init__` 对 `current_message_summary` 的 `isinstance` 校验晚于属性访问 | ✅ `compaction.py:211-214` isinstance 检查先于 `:216` 属性访问 |
| DS / MiMo | M1 | 缺少 `current_message_summary` 错误类型直测 | ✅ `test_compaction_contract.py:195-204` 直测非法类型抛 `TypeError` |
| DS | M2 | 缺少 `CompactQualityCheckResult` accepted/rejection invariant 直测 | ✅ `test_compaction_contract.py:242-279` 两个 invariant 直测；`compaction.py:829-834` invariant 校验 |
| DS | R2 | Reactive compact 缺少 attempt/execution 必填校验 | ✅ `compaction.py:199-207` REACTIVE trigger 强制要求 `attempt_id`/`execution_id` 非 None；`test_compaction_contract.py:207-239` 覆盖 None 与空字符串路径 |

### B1 修复细节

`compaction.py:211-221` 的校验顺序：
1. `isinstance(self.current_message_summary, CurrentMessageSummary)` 类型检查（`:211-214`）
2. `self.current_message_summary.current_user_input_ref` 属性访问（`:215-221`）

非法类型（如 `str`）现在稳定抛出 `TypeError`，不再先触发 `AttributeError`。

### R2 修复细节

`compaction.py:199-207` 在 `_require_optional_non_empty` 校验之后，对 `REACTIVE` trigger 做独立排空检查：

```python
if self.trigger_source is ContextCompactionTriggerSource.REACTIVE:
    if self.attempt_id is None:
        raise ValueError("CompactionRequest.attempt_id is required for reactive compaction")
    if self.execution_id is None:
        raise ValueError("CompactionRequest.execution_id is required for reactive compaction")
```

测试覆盖四个路径：`None` attempt、`None` execution、`""` attempt、`""` execution（后二者由前置 `_require_optional_non_empty` 拒绝，均匹配 `ValueError` 与对应字段名）。

### README 同步

`dayu/host/README.md:127` 已更新："proactive compact 的 Attempt / execution refs 可以为 `None`；reactive compact 必须携带非空 Attempt / execution refs。"

---

## New Findings

（无）

本次修复未引入新的 blocking、high、medium 或 low 问题。修复范围严格限定于：调整校验顺序（B1）、新增校验分支（R2）、新增测试（M1/M2）、README 同步。

---

## Residual Risks

1. **open_questions_retained=False 仍不作为拒绝原因。** `_open_questions_retained()` 仅在 `CompactQualityCheckResult` 中记录状态，未被对应 `CompactQualityIssue` 拒绝路径消费。后续 orchestration slice 需明确语义：是"记录但放行"还是"记录并拒绝"。
2. **真实 LLM compactor adapter 与 canonical compact event 未实现。** 属于 Slice 3+ / Slice 6 范围，本轮未涉及。
3. **MiMo L1 / L2 / L3 未处理。** L1（`_require_string_tuple` 空元素错误消息细化）、L2（`to_json` 列表推导简化）、L3（`_require_optional_non_empty` 重复定义）均非总控要求的阻塞项，未在本轮 fix 中处理。

---

## File Index

| 文件 | 修复区域 | 状态 |
|------|---------|------|
| `dayu/host/compaction.py` | :199-207 (R2), :211-221 (B1), :829-834 (M2 invariant) | ✅ 修复无误 |
| `tests/host/test_compaction_contract.py` | :195-204 (M1), :207-239 (R2), :242-279 (M2) | ✅ 覆盖充分 |
| `dayu/host/README.md` | :127 proactive/reactive refs 说明 | ✅ 已同步 |

---

## Summary

- **Verdict:** PASS
- **Compliant fixes:** DS B1, DS M1, DS M2, DS R2 — all verified
- **New findings:** 0
- **Remaining blocking:** 0
- **Remaining high:** 0
- **Total tests:** 17 passed (was 13)
- **Pyright:** 0 errors / 0 warnings / 0 informations
