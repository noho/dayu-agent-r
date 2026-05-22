# Code Re-Review — P12-S2-F1 Fix

## Scope

- Mode: re-review of accepted fix P12-S2-F1
- Original review: `docs/reviews/phase12-slice2-code-review-ds-20260521.md`
- Controller adjudication: `docs/reviews/phase12-slice2-code-review-controller-adjudication-20260521.md`
- Updated implementation artifact: `docs/reviews/phase12-slice2-implementation-codex-20260520.md` (Fix Addendum)
- Output file: `docs/reviews/phase12-slice2-rereview-ds-20260521.md`
- Fix changes:
  - `dayu/runtime/tools_discovery.py` — `_normalize_json_value` Mapping key type check
  - `tests/runtime/test_tools_discovery_digest.py` — `test_schema_mapping_with_non_string_key_is_rejected`

## P12-S2-F1 Verification

### Fix implementation

`dayu/runtime/tools_discovery.py:569-570`，在 `_normalize_json_value` 的 `Mapping` 分支内新增两行：

```python
if not isinstance(key, str):
    raise TypeError("JsonValue object key must be str")
```

该检查位于 key 值被放入 `result` dict 之前，确保非字符串键在 canonical digest 序列化之前 fail fast，而不是被 `json.dumps` 静默转换为字符串。

### Test coverage

`tests/runtime/test_tools_discovery_digest.py:306-335`，新增 `test_schema_mapping_with_non_string_key_is_rejected`：

- 构造 malformed `ToolParametersSchema`，其 `properties` 为 `{1: {"type": "string"}}`（整数键）
- 通过 `cast(Mapping[str, JsonValue], ...)` 注入以绕过类型检查
- 断言 `_discover_digest` 抛出 `TypeError`，消息匹配 `"JsonValue object key must be str"`
- 测试在 digest 生成路径（`_tool_definitions_digest` → `_canonical_json_digest` → `_normalize_json_value`）上验证快速失败

### Regression check

| 检查项 | 结果 |
|--------|------|
| 所有已有 digest 测试（stability、callable identity、schema/truncate/tags/display changes） | 通过 |
| Source refs 规范化测试（kind/id/version 保留、digest 替换） | 通过 |
| reserved name 测试（fetch_more 拒绝） | 通过 |
| 原有 tools_discovery 测试（9 个） | 通过 |
| import boundary 测试（5 个） | 通过 |
| pyright | 0 errors, 0 warnings |
| 新增 import 或依赖 | 无 |
| 架构边界违规 | 无 |

## Verdict

**PASS** — P12-S2-F1 fixed, 0 new blocking findings.

修复精确针对原始 finding：`_normalize_json_value` 在 Mapping 分支对非字符串键 fail fast，新增测试覆盖 malformed schema properties 注入路径。无回归，无 scope 蔓延，架构边界完整。

## Validation Commands

```text
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py \
  tests/runtime/test_tools_discovery_digest.py \
  tests/runtime/test_import_boundary.py -v
# Result: 23 passed in 0.65s

source .venv/bin/activate && python -m pyright \
  dayu/runtime/tools_discovery.py \
  tests/runtime/test_tools_discovery_digest.py
# Result: 0 errors, 0 warnings, 0 informations
```
