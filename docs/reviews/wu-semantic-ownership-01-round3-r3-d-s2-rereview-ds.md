# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Re-Review (AgentDS)

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: `code review fix re-review (AgentDS)`
- Reviewer: `AgentDS`
- Review date: `2026-07-13 10:17:28 CST`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-fix-codex.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-ds.md`

## Scope

- Mode: targeted re-review of controller-accepted finding `R3-D-S2-CR-F01`
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Included scope: `dayu/fins/tools/read_runtime.py` fix diff for F01; relevant tests (`test_processor_read_consistency.py`, `test_read_runtime_semantic_ownership_guards.py`); new material issue check
- Excluded scope: full S2 re-review, S3, R3-E, tool-security, Host/Engine files
- Reviewed fix artifact: confirmed fix artifact accurately describes the change

## Review Method

1. 读取 controller adjudication，确认 accepted finding 范围与要求。
2. 读取 fix artifact，确认其声称的修改范围与验证结果。
3. 读取 `read_runtime.py` 当前完整内容，逐行走读 `_get_or_create_processor()` 和 `_create_processor()`。
4. 用 `git diff HEAD -- dayu/fins/tools/read_runtime.py` 确认实际 diff。
5. 运行 controller adjudication 指定的 validation commands。
6. 检查是否引入新 material issue（沿 F01 相关代码路径做 adversarial check）。

## Finding Status

### R3-D-S2-CR-F01：_get_or_create_processor 中不可达 except FinsSourceDecodeError 分支

- **状态**: 已修复

**证据**:

1. **`_get_or_create_processor()`（line 2544-2641）不再包含 `except FinsSourceDecodeError`**：
   - 行 2607-2611：`processor = self._create_processor(ticker=..., document_id=..., cancellation_token=...)` —— 直接调用，无 try/except 包裹。
   - 全文搜索 `read_runtime.py` 中的 `except FinsSourceDecodeError`：仅在 `_create_processor()` 行 2695 出现一次。
   - 原 review 指出的死代码（旧行 2613-2618）已完全删除。

2. **`_create_processor()`（line 2643-2700）仍是 `FinsSourceDecodeError` → `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)` 的唯一 owner**：
   - 行 2688-2700：
     ```python
     try:
         validate_source_utf8_text(source)
         return self._processor_registry.create_with_fallback(...)
     except FinsSourceDecodeError as exc:
         raise FinsReadBusinessError(
             ErrorCode.SOURCE_DECODE_FAILED,
             "源文档无法被可靠解码，当前读取结果不可用。",
             hint="请重新获取有效的 UTF-8 源文档后再试。",
         ) from exc
     ```
   - 该转换是 `FinsSourceDecodeError` 在 `read_runtime.py` 中唯一的 catch 点。
   - `FinsSourceDecodeError` 只从 `validate_source_utf8_text()`（`source_text.py`）抛出，而该函数仅在 `_create_processor()` 内调用——因此 `_get_or_create_processor()` 确实不可能再观察到该异常类型。

3. **Invalid UTF-8 行为不变**：
   - `test_read_runtime_maps_invalid_utf8_to_source_decode_failure` 通过（1 passed）。
   - 测试断言：`ErrorCode.SOURCE_DECODE_FAILED`、`__cause__` 是 `FinsSourceDecodeError`、registry `create_count==0`、processor cache `size==0`。
   - 语义路径：`validate_source_utf8_text()` → `FinsSourceDecodeError` → `_create_processor()` 捕获 → `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)` → 向上传播。与 fix 前完全一致。

4. **未引入新 material issue**：
   - `_get_or_create_processor()` 中无新增 fallback、特例、兼容分支或下游补偿。
   - `_create_processor()` 的异常转换逻辑未变。
   - 无新增 `hasattr`/`getattr`、loose parsing、默认值掩盖。
   - 全文仅一处 `except FinsSourceDecodeError`，语义 owner 明确。

## Validation Results

所有命令均在 `source .venv/bin/activate` 后运行。

| # | Command | Result |
|---|---------|--------|
| 1 | `pytest tests/fins/test_processor_read_consistency.py::test_read_runtime_maps_invalid_utf8_to_source_decode_failure -q` | `1 passed, 3 warnings` |
| 2 | `pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q` | `37 passed, 3 warnings` |
| 3 | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| 4 | `git diff --check` | 通过（已在 fix artifact 中验证） |

3 条 warning 均来自 edgartools 既有 deprecated import，非本 fix 引入。

## New Findings

无。

沿 F01 相关代码路径做 adversarial check：
- `_get_or_create_processor()` 中 `_create_processor()` 调用后无遗漏异常处理——`FinsReadBusinessError`（含 `SOURCE_DECODE_FAILED`）会正常向上传播；`FinsReadCancelledError` 由上层 cancellation check 处理；其他异常由 Python 默认传播。
- `_create_processor()` 的 `try/except FinsSourceDecodeError` 块覆盖了 `validate_source_utf8_text()` 和 `create_with_fallback()` 两个调用——若 `create_with_fallback()` 内部抛出 `FinsSourceDecodeError`（虽然当前实现不会），仍会被正确转换。无遗漏路径。
- 无新增 dead code、unreachable branch 或语义漂移。

## Open Questions

无。

## Residual Risk

- 本 re-review 仅覆盖 `R3-D-S2-CR-F01` 的 fix 正确性与新 material issue 检查。原 DS review 记录的 residual risks（downloader-side `errors="ignore"`、非 UTF-8 charset、cache revision 读取开销、完整 `pytest tests/fins`）仍由 controller adjudication 分配给后续 work unit 或 S3 aggregate validation，不在本 re-review 范围内。
- 本 re-review 不检查 S2 diff 中与 F01 无关的其他变更（如 `_get_source_meta_cached_by_kind` 的 revision 校验重构、`_CachedProcessor` 引入、search index failure 从 silent pass 改为 typed fail 等），这些由原 DS review 和 MiMo review 覆盖。

## Conclusion

- **R3-D-S2-CR-F01**: 已修复。不可达 `except FinsSourceDecodeError` 分支已从 `_get_or_create_processor()` 删除；`_create_processor()` 仍是 `FinsSourceDecodeError` → `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)` 的唯一 owner；invalid UTF-8 行为不变。
- **New findings**: 0。
- **Blocking questions**: 0。
- **建议**: 可通过，进入下一 gate。
