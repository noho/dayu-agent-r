# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: HEAD (uncommitted diff)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-mimo.md`
- Included scope:
  - `dayu/fins/direct_event_text.py` (new file)
  - `dayu/fins/ingestion_runtime.py` (modified)
  - `dayu/fins/ingestion/wait_adapter.py` (modified)
  - `tests/fins/test_fins_ingestion_runtime.py` (modified)
  - `tests/fins/test_fins_ingestion_tools.py` (modified)
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-controller-validation.md`
- Excluded scope: `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`
- Parallel review coverage: 无

## Findings

### 001-未修复-低-direct_failure_message fallback_message 空白字符串被忽略

- **入口/函数**: `dayu/fins/direct_event_text.py:direct_failure_message`
- **文件(行号)**: `dayu/fins/direct_event_text.py:102-105`
- **输入场景**: 调用方传入 `fallback_message="   "` (纯空白字符串)
- **实际分支**: `stripped = fallback_message.strip()` 后为空，继续按 `error_kind` 选择默认消息
- **预期行为**: 上游已清洗过的业务失败说明应被尊重，即使原始值是空白
- **实际行为**: 纯空白字符串被忽略，返回 `error_kind` 对应的默认消息
- **直接证据**: `if stripped: return stripped` 在 `stripped` 为空时跳过
- **影响**: 仅影响边界情况；上游 `_safe_direct_error_message` 和 `_safe_observation_message` 都会先清洗，实际不会传入纯空白。当前调用方均传入 `None` 或已清洗文本，无实际影响。
- **建议改法和验证点**: 无需修改。当前行为符合"fallback_message 为空时按分类生成默认说明"的 docstring 承诺。纯空白等价于空。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Evidence Summary

### Owner Boundary 验证

1. **`direct_event_text.py` 依赖边界**：✅ 成立
   - 只 import `FinsErrorKind`, `FinsOperationKind`, `FinsResultStatus` (来自 `dayu.fins.direct_events`)
   - 不 import `FinsEvent`, `FinsResultSummary`, `FinsProgress`, `FinsIngestionRuntime`, Host outcome types, storage, wait adapter/runtime
   - 通过 `rg` 扫描确认无违禁 import

2. **Runtime/Adapter 只产生 typed facts**：✅ 成立
   - `ingestion_runtime.py` 删除了 `_DIRECT_CANCELLED_MESSAGE`, `_DIRECT_FAILURE_TITLE`, `_DIRECT_SUCCESS_TITLE`, `_DIRECT_ERROR_TEXT_FALLBACK` 等硬编码文案
   - `_emit_direct_result` 不再接受 `title` 参数，改为内部调用 `direct_result_title(...)`
   - `_safe_direct_error_message` 新增 `error_kind` 参数，内部调用 `direct_failure_message(...)`
   - `_observation_failure_result` 和 `_observation_cancelled_result` 改为接受 `operation_kind` 而非 `message`，内部使用 helper

3. **`wait_adapter.py` 文案投影**：✅ 成立
   - `_failed_outcome` 的 `hint` 改为 `wait_failed_hint()`
   - `_cancelled_outcome` 的 `message` 和 `hint` 改为 `wait_cancelled_message()` 和 `wait_cancelled_hint()`
   - `_failure_message` 仍从 `result.error_message` 提取，但 `result.error_message` 现在由 `direct_failure_message(...)` 设置，不再包含 diagnostic message

### Diagnostic Message 泄漏复核

4. **Observation diagnostic message 不会投影给 LLM/user**：✅ 已修正
   - `record.message` 仍设置为 `"Observation was cancelled before activation."` 等 diagnostic message (行 2437)
   - 但 `record.result.error_message` 使用 `direct_failure_message(error_kind=..., fallback_message=None)` (行 5116-5119, 5148-5151, 5186-5189)
   - `wait_adapter._failure_message` 优先使用 `result.error_message` (行 568-569)，只有为空时才 fallback 到 `snapshot.message`
   - Controller validation 已修正此问题：diagnostic message 保留在 `record.message` 作为 process-local 诊断，不再 feed 到 `FinsResultSummary.error_message`

### 传播路径一致性

5. **Direct progress/result/wait failed/cancelled 传播路径**：✅ 语义一致
   - Direct progress: runtime 产生 typed stage → `direct_progress_message(stage=...)` 选择文案 → `FinsEvent(PROGRESS).message`
   - Direct result: runtime 产生 status/details/error_kind → `direct_result_title(...)` 和 `direct_failure_message(...)` → `FinsResultSummary` 和 `FinsEvent(RESULT)`
   - Wait failed: `wait_adapter._failed_outcome` → `wait_failed_hint()` → `ToolFailedOutcome.hint`
   - Wait cancelled: `wait_adapter._cancelled_outcome` → `wait_cancelled_message()` 和 `wait_cancelled_hint()` → `ToolCancelledOutcome.message/hint`
   - 无下游特例分支、无兼容 wrapper/re-export

6. **`FinsOperationKind` 枚举覆盖**：✅ 完整
   - `_failure_title_for_operation` 覆盖所有 7 个枚举值：`DOWNLOAD`, `PREPROCESS`, `UPLOAD`, `UPLOAD_FILING`, `UPLOAD_MATERIAL`, `PROCESS_FILING`, `PROCESS_MATERIAL`
   - 使用 `assert_never` 确保 exhaustive check
   - `FinsErrorKind` 和 `FinsResultStatus` 同样使用 `assert_never`

### 测试覆盖

7. **测试覆盖 helper、runtime direct stream、wait adapter outcome**：✅ 充分
   - `test_direct_event_text_helper_owns_result_titles_and_failure_messages`: 覆盖 `direct_result_title`, `direct_failure_message`, 以及 4 个 specific message helper
   - `test_direct_event_text_helper_owns_progress_and_wait_copy`: 覆盖 `direct_progress_message` (含 unknown stage fallback), `wait_failed_hint`, `wait_cancelled_message`, `wait_cancelled_hint`
   - `test_direct_stream_duplicate_result_raises_protocol_error`: 验证 `_emit_direct_result` 不再接受 `title`
   - `test_cancel_prepared_observation_prevents_later_activation_submit`: 验证 cancelled result 使用 `direct_failure_message`
   - `test_unexpected_activation_exception_terminalizes_prepared_observation`: 验证 failed result 使用 `direct_failure_message`
   - `test_fins_wait_poll_adapter_maps_observation_statuses`: 验证 wait outcome 使用 helper 文案
   - 覆盖率 86%，未覆盖行是 `assert_never` 分支（exhaustive check，无需测试）

### 未覆盖区域

8. **Legacy job sidecar messages**：按设计保留
   - `_append_job_event_warn(...)` 和 job lifecycle messages (`已记录取消请求`, `job 已进入队列` 等) 仍在 `ingestion_runtime.py`
   - 目标是 job event/audit sidecar，不是 direct stream 或 Host wait outcome
   - 不属于 S2 scope

9. **Source-specific download adapter progress messages**：按设计保留
   - 下载适配器提供的 progress message 是 adapter-provided business inputs
   - 通过 runtime 传递，不是 runtime-owned generic direct/wait copy
   - 不属于 S2 scope

## Open Questions

- 无

## Residual Risk

- `_failure_message` 的 `snapshot.message` fallback 路径（`wait_adapter.py:570-571`）在当前实现中不会被触发，因为 `result.error_message` 总是由 `direct_failure_message` 设置为非空值。如果未来有新的 observation closeout 路径绕过 `_observation_failure_result`/`_observation_cancelled_result`/`_mark_observation_failed`，可能重新引入 diagnostic message 泄漏风险。当前代码路径已通过测试覆盖。
- `direct_progress_message` 对未知 stage 返回通用文案 `"财报处理进度已更新"`，这是合理的 fallback 行为，但未来新增 progress stage 时需要同步更新 `_PROGRESS_MESSAGES` 字典。
