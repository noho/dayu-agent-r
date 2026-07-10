# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Re-Review

## Scope

- Mode: re-review gate
- Work unit: WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization
- Slice: S3 - Typed Engine error codes and propagation audit
- Finding under review: P3-D-S3-CR-F01
- Output file: docs/reviews/wu-semantic-ownership-01-p3-d-s3-rereview-mimo.md

## Sources

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-codex.md`
- Controller fix validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-controller-validation.md`
- Original MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-mimo.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-ds.md`

## Re-Review Checklist

### 1. Agent tests no longer compare typed error_code directly to string literals

**Status: ✅ Passed**

验证方法：执行 `rg -n "\\.error_code\\s*(==|!=)\\s*\\\"|\\\"[^\\\"]+\\\"\\s*(==|!=)\\s*.*\\.error_code" tests/engine/test_agent_phase2.py`，无命中。

直接证据：所有 `.error_code` 断言现在使用 helper 函数，不直接与字符串字面量比较。

### 2. EngineRunErrorCode assertions prove enum identity and serialized value

**Status: ✅ Passed**

验证方法：检查 `_assert_engine_run_error_code` helper 函数实现（`tests/engine/test_agent_phase2.py:105-117`）。

直接证据：
```python
def _assert_engine_run_error_code(
    actual: EngineErrorCode, expected: EngineRunErrorCode
) -> None:
    assert actual is expected
    assert serialize_engine_error_code(actual) == expected.value
```

该函数同时验证：
- 枚举身份：`actual is expected`
- 序列化值：`serialize_engine_error_code(actual) == expected.value`

### 3. RunnerSpecificErrorCode assertions prove wrapper type, source, and serialized value

**Status: ✅ Passed**

验证方法：检查 `_assert_runner_specific_error_code` helper 函数实现（`tests/engine/test_agent_phase2.py:120-137`）。

直接证据：
```python
def _assert_runner_specific_error_code(
    actual: EngineErrorCode,
    *,
    expected_value: str,
    expected_source: RunnerSpecificErrorSource,
) -> None:
    assert isinstance(actual, RunnerSpecificErrorCode)
    assert actual.source is expected_source
    assert serialize_engine_error_code(actual) == expected_value
```

该函数同时验证：
- Wrapper 类型：`isinstance(actual, RunnerSpecificErrorCode)`
- 来源身份：`actual.source is expected_source`
- 序列化值：`serialize_engine_error_code(actual) == expected_value`

### 4. Weak-typing guard precisely prevents direct `.error_code == "..."` or `.error_code != "..."` regressions in Agent tests without brittle Host durable text false positives

**Status: ✅ Passed**

验证方法：检查 `test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings` 测试实现（`tests/engine/test_weak_typing_guard.py:344-370`）。

直接证据：
- Guard 只扫描 `tests/engine/test_agent_phase2.py`，不扫描 Host durable text 或其它非 typed 语义
- 使用 AST 分析识别 `.error_code` 属性访问与字符串字面量的直接 `==` / `!=` 比较
- Guard 精确约束 Agent typed error-code 行为测试，避免 brittle broad scan

### 5. No production behavior, README/doc, LLM-facing path, or Host projection was unnecessarily changed

**Status: ✅ Passed**

验证方法：检查 fix artifact 和 controller validation。

直接证据：
- Fix artifact 明确声明："未修改生产行为"
- Controller validation 确认："No production behavior was changed in the fix gate"
- 只修改了测试文件：`tests/engine/test_agent_phase2.py` 和 `tests/engine/test_weak_typing_guard.py`
- 未修改任何 production 代码、README、doc、LLM-facing path 或 Host projection

## 验证结果

### 测试

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_weak_typing_guard.py -q
# 72 passed in 0.30s

source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q
# 149 passed in 0.18s
```

### pyright

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations
```

### 源码扫描

```bash
rg -n "\\.error_code\\s*(==|!=)\\s*\\\"|\\\"[^\\\"]+\\\"\\s*(==|!=)\\s*.*\\.error_code" tests/engine/test_agent_phase2.py
# 无命中
```

## Finding Status

**P3-D-S3-CR-F01: 已修复**

Fix 成功关闭了 controller accepted finding。所有 re-review checklist 项目均通过验证。

## New Material Findings

未发现新的 material defect。

## Residual Risk

- S3 intentional string-only constructor break 保持原 accepted residual risk，本次不改变。
- Provider-specific wrapper source 仍只在 Engine typed wrapper 内可见，Host durable/public projection 仍是 serialized text；如未来需要公开 source，需要新的 Engine/Host public contract。

## Conclusion

S3 re-review complete.

P3-D-S3-CR-F01 已被 fix 关闭。所有 re-review checklist 项目均通过验证，未发现新的 material defect。Fix 只修改了测试代码，未修改生产行为、README/doc、LLM-facing path 或 Host projection。
