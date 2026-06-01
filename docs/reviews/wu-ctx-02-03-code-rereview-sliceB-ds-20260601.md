# WU-CTX-02 + WU-CTX-03 Slice B Focused Code Re-review

## Review metadata

- **Review type**: Focused re-review（controller adjudication 后的 fix 复核）
- **Review target**: DS-F1、DS-F2 fix 验证；DS-F3、DS-F9 边界确认
- **Source reviews**:
  - `docs/reviews/wu-ctx-02-03-code-review-sliceB-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md`
- **Controller adjudication**: `docs/reviews/wu-ctx-02-03-code-controller-adjudication-sliceB-20260601.md`
- **Fix artifact**: `docs/reviews/wu-ctx-02-03-fix-sliceB-codex-20260601.md`
- **Review date**: 2026-06-01
- **Reviewer**: DS (focused re-review)

## Review scope

按 controller adjudication 第 4 节限定范围：

1. DS-F1 fix 验证：`_assert_failed_payload_no_fallback` 是否已抽取到共享 helper，两个测试模块是否复用，helper 是否有中文 docstring 和严格类型
2. DS-F2 fix 验证：`test_context_compact_events.py` 是否覆盖 not_applicable + fallback fields、dispatch 缺失/null fallback field、fail_closed 缺失/null fallback field
3. DS-F3 是否保持 deferred-with-owner
4. DS-F9 是否未被扩大为必修
5. 是否无 production behavior change 超出 Slice B

## DS-F1 验证：已修复

### 共享 helper 文件

`tests/host/_context_compaction_assertions.py` 新增，提供 `assert_failed_payload_no_fallback`。

**中文 docstring**: 完整，包含 `:param`、`:returns`、`:raises` 说明。

**严格类型签名**:
```python
def assert_failed_payload_no_fallback(
    payload: Mapping[str, JsonValue],
    *,
    expected_operation_id: str | None,
    expected_attempt_count: int,
    expected_retry_repair_budget_exhausted: bool,
) -> None:
```
无 `Any` / `object` 使用。

### 调用方验证

- `tests/host/test_dispatch_scheduler.py:69` — `from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback`；5 处 call site（line 3291, 3399, 3449, 3495, 3538）
- `tests/host/test_engine_ingest_mapping.py:114` — `from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback`；5 处 call site（line 533, 645, 764, 801, 878）

### 旧重复 helper 清理

`_assert_failed_payload_no_fallback`（下划线前缀旧名）在两个测试模块中均无匹配，确认已删除。

### 结论

DS-F1 **已修复**。

## DS-F2 验证：已修复

### 新增测试清单

`tests/host/test_context_compact_events.py` 新增 3 个拒绝路径测试：

| 测试函数 | 覆盖路径 | 验证点 |
|---|---|---|
| `test_failed_payload_rejects_not_applicable_with_fallback_fields` (line 394) | `not_applicable` + 任一 fallback 字段非 `None` | 遍历 4 个 fallback 字段逐个注入非 `None` 值，断言 `ValueError` + 匹配错误消息 |
| `test_failed_payload_rejects_dispatch_missing_or_null_fallback_field` (line 449) | `dispatch` + `fallback_input_window` 缺失 / `None` | 缺失断言 `"fallback_input_window is required"`；置 `None` 断言 `"fallback_input_window must be mapping"` |
| `test_failed_payload_rejects_fail_closed_missing_or_null_fallback_field` (line 467) | `fail_closed` + `fallback_budget_result` 缺失 / `None` | 缺失断言 `"fallback_budget_result is required"`；置 `None` 断言 `"fallback_budget_result must be mapping"` |

### 测试完备性

- `not_applicable` 拒绝路径覆盖了全部 4 个 fallback 诊断字段（`fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`）
- `dispatch` 拒绝路径覆盖了缺失和置 `None` 两种场景
- `fail_closed` 拒绝路径覆盖了缺失和置 `None` 两种场景
- 所有新增测试均有中文 docstring

### 结论

DS-F2 **已修复**。

## DS-F3 验证：deferred-with-owner（维持）

- `tests/host/test_context_compact_events.py` 中无 `context_budget_policy_missing` 或 `input_event_missing` 相关测试
- `tests/host/test_engine_ingest_mapping.py` 中无新增针对这两条路径的集成测试
- Owner 仍为 WU-CTX Slice D / aggregate review
- 本次 fix 未扩大范围到 DS-F3

## DS-F9 验证：rejected-with-reason（维持）

- 冗余括号在 `dayu/host/engine_ingest.py:1554, 1744` 和 `dayu/host/dispatch.py:1160, 1626` 仍存在
- 本次 fix 未处理 DS-F9，未扩大范围

## Production behavior 验证

`git diff --stat HEAD` 显示修改文件：

```
 dayu/host/context_events.py               |  87 +++++++++++
 dayu/host/dispatch.py                     |  57 +++++++
 dayu/host/engine_ingest.py                |  42 +++++
 tests/host/test_context_compact_events.py | 249 +++++++++++++++++++++-
 tests/host/test_dispatch_scheduler.py     |  60 ++++++-
 tests/host/test_engine_ingest_mapping.py  |  43 +++++-
```

3 个 production 文件的变更为原 Slice B implementation 内容（payload builder/validator 扩展、proactive/reactive helper），未在本次 fix 中新增 production 修改。本次 fix 仅修改 3 个测试文件和新增 1 个共享 helper 文件。

## Fix artifact 自报状态校验

Fix artifact 自报：
- pytest `129 passed in 1.38s`
- pyright `0 errors, 0 warnings, 0 informations`

与原始 Slice B review 独立验证（pytest `126 passed`，pyright `0 errors`）对比：测试数量从 126 增至 129（新增 3 个 DS-F2 拒绝路径测试），pyright 仍为零报错。自报数据与预期一致。

## 结论

| Finding | 状态 |
|---|---|
| DS-F1 | **已修复** |
| DS-F2 | **已修复** |
| DS-F3 | **deferred-with-owner**（维持） |
| DS-F9 | **rejected-with-reason**（维持） |

DS-F1 和 DS-F2 均已按 controller adjudication 要求正确修复。DS-F3 保持 deferred-with-owner，DS-F9 保持 rejected。无 scope expansion，无 production behavior change 超出 Slice B。

## Unresolved count

0

## Blocking questions

无。

## Artifact path

- `docs/reviews/wu-ctx-02-03-code-rereview-sliceB-ds-20260601.md`
