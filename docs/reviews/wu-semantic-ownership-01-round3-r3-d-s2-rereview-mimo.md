# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Code Re-Review

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: code re-review
- Re-reviewer: `AgentMiMo`
- Timestamp: `20260713-101841`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-controller-adjudication.md`
- Original review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-mimo.md`

## Scope

只复核 controller accepted finding `R3-D-S2-CR-F01` 的 fix，不重新做全量 S2 review，不 review S3/R3-E/tool-security。

## Finding Status

### R3-D-S2-CR-F01：_get_or_create_processor 中不可达 except FinsSourceDecodeError 分支

| 属性 | 值 |
| --- | --- |
| Finding ID | `R3-D-S2-CR-F01` |
| Controller decision | `accepted / low` |
| Fix status | **已修复** |
| Evidence | 见下方验证 |

#### 验证结果

1. **死代码删除验证**
   - 检查 `dayu/fins/tools/read_runtime.py` 中 `_get_or_create_processor()` 方法（lines 2544-2641）。
   - 确认该方法中**不存在** `except FinsSourceDecodeError` 分支。
   - 该方法直接调用 `_create_processor()`，无同义异常捕获。

2. **Owner 边界验证**
   - 检查 `_create_processor()` 方法（lines 2643-2700）。
   - 确认 `except FinsSourceDecodeError as exc:` 分支**仅存在于** `_create_processor()`（line 2695）。
   - 该分支将 `FinsSourceDecodeError` 转换为 `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED, ...)`（lines 2696-2700）。
   - `_create_processor()` 是 `FinsSourceDecodeError -> FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)` 转换的唯一 owner。

3. **Invalid UTF-8 行为验证**
   - 测试 `test_read_runtime_maps_invalid_utf8_to_source_decode_failure` 通过。
   - 测试确认：非法 UTF-8 输入仍由 owner 映射为既有 source decode typed failure，行为不变。
   - 测试断言：`error_info.value.code is ErrorCode.SOURCE_DECODE_FAILED`，`isinstance(error_info.value.__cause__, FinsSourceDecodeError)`，`registry.create_count == 0`，`runtime._processor_cache.size() == 0`。

4. **回归验证**
   - `pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`：37 passed。
   - `python -m pyright dayu/ tests/ utils/`：0 errors, 0 warnings, 0 informations。
   - `git diff --check`：通过，无输出。

#### 修复完整性判定

Fix 完整且正确：
- 不可达的 `except FinsSourceDecodeError` 分支已从 `_get_or_create_processor()` 中删除。
- `_create_processor()` 仍唯一拥有 `FinsSourceDecodeError -> FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)` 转换。
- Invalid UTF-8 行为不变，测试验证通过。
- 未引入新的 material issue。

## New Findings Count

0

## Blocking Questions

无。

## Residual Risk

- 本 fix 未引入新的 residual risk。
- 下游-side `errors="ignore"` 仍位于 S2 read owner 路径和本 gate allowed files 之外。分类：`assigned to later work unit / outside current slice`。
- 非 UTF-8 业务 charset 支持仍需独立 encoding-policy owner。分类：`assigned to later work unit`。
- Cache revision 读取开销仍待实际 profiling 后裁决。分类：`assigned to later work unit`。
- 完整 `pytest tests/fins -q` 仍由 approved S3 aggregate validation 覆盖。分类：`covered by later approved slice`。

上述风险均继承 controller adjudication，未因本次死代码删除而扩大。

## Conclusion

**Finding `R3-D-S2-CR-F01` 已修复。** Fix 正确删除了 `_get_or_create_processor()` 中不可达的 `except FinsSourceDecodeError` 分支，保持 `_create_processor()` 作为该转换的唯一 owner，invalid UTF-8 行为不变，未引入新 material issue。本 re-review 通过，可进入下一 gate。
