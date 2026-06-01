# WU-CTX-02 + WU-CTX-03 Slice B Focused Code Re-Review

## 1. Re-Review 元信息

- **Gate**: WU-CTX-02 + WU-CTX-03 Slice B focused code re-review
- **Reviewer**: AgentMiMo
- **日期**: 2026-06-01
- **Source reviews**: `docs/reviews/wu-ctx-02-03-code-review-sliceB-mimo-20260601.md`、`docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md`
- **Controller adjudication**: `docs/reviews/wu-ctx-02-03-code-controller-adjudication-sliceB-20260601.md`
- **Fix artifact**: `docs/reviews/wu-ctx-02-03-fix-sliceB-codex-20260601.md`

## 2. 复核范围

只复核以下四项，不扩大范围：

1. DS-F1 是否已修复
2. DS-F2 是否已修复
3. DS-F3 是否保持 deferred-with-owner
4. DS-F9 是否未被扩大为必修

## 3. Finding 复核

### DS-F1: `_assert_failed_payload_no_fallback` 重复定义 → 已修复

**裁决要求**: 抽取到 `tests/host/_context_compaction_assertions.py`，两测试模块复用，中文 docstring，严格类型，无 `Any`/`object`。

**证据**:

| 验证点 | 结果 |
|---|---|
| 共享 helper 存在于 `tests/host/_context_compaction_assertions.py` | 存在，第 10-42 行 |
| 中文 docstring | 有，第 17-26 行，包含参数、返回值、异常 |
| 类型签名严格 | `payload: Mapping[str, JsonValue]`、`expected_operation_id: str | None`、`expected_attempt_count: int`、`expected_retry_repair_budget_exhausted: bool`；无 `Any`、无 `object` |
| `test_dispatch_scheduler.py` 导入共享 helper | 第 69 行: `from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback` |
| `test_engine_ingest_mapping.py` 导入共享 helper | 第 114 行: `from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback` |
| 旧重复 helper 已删除 | `grep` 确认两测试文件中无 `def _assert_failed_payload_no_fallback` 定义 |

**结论: 已修复**

---

### DS-F2: `_validate_failed_fallback_fields` 拒绝路径缺测试 → 已修复

**裁决要求**: 补三类拒绝路径测试——`not_applicable` 携带非 None fallback 字段必须拒绝；`dispatch` 缺失/置空必需 fallback 字段必须拒绝；`fail_closed` 缺失/置空必需 fallback 字段必须拒绝。

**证据**:

| 测试函数 | 行号 | 覆盖路径 | 验证 |
|---|---|---|---|
| `test_failed_payload_rejects_not_applicable_with_fallback_fields` | 394-446 | `not_applicable` + 4 个 fallback 字段逐一设为非 None → `ValueError` | 遍历 4 个字段，每个用 `pytest.raises(ValueError, match=...)` 验证 |
| `test_failed_payload_rejects_dispatch_missing_or_null_fallback_field` | 449-464 | `dispatch` + 删除 `fallback_input_window` → `ValueError`；`dispatch` + `fallback_input_window=None` → `ValueError` | 缺失和置空两条子路径均覆盖 |
| `test_failed_payload_rejects_fail_closed_missing_or_null_fallback_field` | 467-482 | `fail_closed` + 删除 `fallback_budget_result` → `ValueError`；`fail_closed` + `fallback_budget_result=None` → `ValueError` | 缺失和置空两条子路径均覆盖 |

**结论: 已修复**

---

### DS-F3: `context_budget_policy_missing` / `input_event_missing` 无集成测试 → 保持 deferred-with-owner

**证据**: `grep` 确认 `test_context_compact_events.py` 中无 `context_budget_policy_missing` 或 `input_event_missing` 相关新增测试。Fix artifact 未声称处理 DS-F3，owner 仍为 WU-CTX Slice D / aggregate review。

**结论: 保持 deferred-with-owner，未扩大范围**

---

### DS-F9: 冗余括号 → 保持 rejected，未被扩大为必修

**证据**: `dispatch.py:1160` 和 `dispatch.py:1626` 仍存在 `retry_repair_budget_exhausted=(...)` 冗余括号。Fix artifact 未声称处理 DS-F9，fix 范围未扩大。

**结论: 保持 rejected，未扩大**

---

## 4. 验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| pytest | `pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q` | `129 passed in 1.21s` |
| pyright | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |

测试从 fix artifact 报告的 129 passed 独立复现一致。

## 5. 结论

**全部通过。** DS-F1 和 DS-F2 已修复且证据充分；DS-F3 保持 deferred-with-owner；DS-F9 保持 rejected 且未被扩大。Fix 范围严格遵守 controller adjudication，未引入 production behavior 变更。

## 6. Blocking questions

无。

## 7. Unresolved count

0（本次 re-Review scope 内无未解决项）。

## 8. Artifact path

- `docs/reviews/wu-ctx-02-03-code-rereview-sliceB-mimo-20260601.md`
