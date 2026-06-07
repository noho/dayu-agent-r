# WU-TOOLS-01-F01 Slice S4 Fix Re-Review

## Gate Metadata

- Gate: re-review.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S4 - Download / Preprocess Awaiting Tool Providers`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s4-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-s4-fix-codex.md`
  - `dayu/fins/tools/_ingestion_tool_helpers.py`
  - `dayu/fins/tools/download_tools.py`
  - `dayu/fins/tools/preprocess_tools.py`
  - `tests/fins/test_fins_ingestion_tools.py`

## 结论

**pass**

三条 accepted findings 均已正确修复，fix 未引入新 correctness / architecture / test regression。

## 逐项 Finding 修复状态

### F01-S4-001 - 共享 helpers 抽取 - 已修复

**要求**: 将 download/preprocess 共用的 awaiting outcome 构造、failed outcome 构造、必填/可选参数读取逻辑收敛到 `dayu/fins/tools/` 下的私有模块；保留各工具自身的 request construction、tool name、schema 和 outcome。

**验证结果**:

- `dayu/fins/tools/_ingestion_tool_helpers.py` 已作为私有模块存在，包含 7 个共享函数：
  - `_awaiting_outcome_from_job_start` - awaiting outcome 构造
  - `_failed_outcome` - failed outcome 构造
  - `_required_text` / `_optional_text` / `_optional_nullable_text` - 文本参数读取
  - `_optional_text_tuple` - 字符串数组参数读取
  - `_optional_bool` - 布尔参数读取
- `download_tools.py:21-29` 从 `_ingestion_tool_helpers` 导入全部 7 个函数，自行保留 `_download_request_from_arguments`、`DOWNLOAD_TOOL_NAME`、`_download_parameters_schema` 和 `build_fins_download_tool`。
- `preprocess_tools.py:22-28` 从 `_ingestion_tool_helpers` 导入 5 个函数（不含 `_optional_text` 和 `_optional_nullable_text`，因 preprocess 不需要这两个参数类型），自行保留 `_preprocess_request_from_arguments`、`PREPROCESS_TOOL_NAME`、`_preprocess_parameters_schema`、`build_fins_preprocess_tool` 和 `_optional_source_kind`。
- 两个工具模块的 tool name、schema、LLM-facing description、tags 和 outcome 语义均未改变。
- 工具模块间无直接依赖，各自独立。

**结论**: 通过。重复逻辑已收敛，工具特定行为保持不变。

### F01-S4-002 - OSError / unexpected exception 测试 - 已修复

**要求**: download/preprocess callable 的 OSError 和 unexpected exception 路径均有聚焦测试，返回 `ToolFailedOutcome` 与 start-failed 语义正确。

**验证结果**:

- `test_fins_ingestion_tools.py:256-273` - `test_download_tool_os_error_from_start_returns_start_failed_outcome`: 注入 `_OSErrorCreateJobStore`（line 85-102）模拟 job store 创建失败，断言返回 `ToolFailedOutcome` 且 error 为 `fins_download_start_failed`。
- `test_fins_ingestion_tools.py:276-293` - `test_download_tool_unexpected_start_exception_returns_start_failed_outcome`: 注入 `_RuntimeErrorExecutor`（line 105-123）模拟 executor 提交失败，断言返回 `ToolFailedOutcome` 且 error 为 `fins_download_start_failed`。
- `test_fins_ingestion_tools.py:296-313` - `test_preprocess_tool_os_error_from_start_returns_start_failed_outcome`: 同样注入 `_OSErrorCreateJobStore`，断言返回 `ToolFailedOutcome` 且 error 为 `fins_preprocess_start_failed`。
- `test_fins_ingestion_tools.py:316-333` - `test_preprocess_tool_unexpected_start_exception_returns_start_failed_outcome`: 同样注入 `_RuntimeErrorExecutor`，断言返回 `ToolFailedOutcome` 且 error 为 `fins_preprocess_start_failed`。
- 4 个测试覆盖了 2 个工具 × 2 种异常路径 = 4 个组合，error code 与 production 代码中的 `_ERROR_JOB_START_FAILED` 常量一致（`download_tools.py:33` 和 `preprocess_tools.py:32`）。

**结论**: 通过。异常路径测试完整覆盖，error code 与生产代码对齐。

### F01-S4-003 - awaiting outcome 终态等待 - 已修复

**要求**: awaiting outcome 测试在断言 `ToolAwaitingOutcome` 后，通过共享 workspace runtime 等待返回 job id 到 terminal state；生产 callable 仍非阻塞。

**验证结果**:

- `test_download_tool_returns_external_job_awaiting_outcome`（line 175-200）:
  1. 调用工具 callable，断言返回 `ToolAwaitingOutcome`（line 194）
  2. 断言 `await_kind` 为 `EXTERNAL_JOB`（line 195）
  3. 通过 `DefaultFinsRuntime.create(workspace_root)` 构造共享 runtime（line 196）
  4. 读取 job record 验证 `operation_kind` 为 `DOWNLOAD` 且 `normalized_ticker` 为 `AAPL`（line 197-199）
  5. 调用 `_wait_ingestion_job_terminal` 等待终态（line 200）
- `test_preprocess_tool_returns_external_job_awaiting_outcome`（line 203-228）: 同样结构，验证 `PREPROCESS` 操作类型。
- `_wait_ingestion_job_terminal`（line 459-482）: 使用 `time.monotonic()` 超时 5 秒、20ms 轮询间隔，通过 `runtime.read_job` 检查 `status in _TERMINAL_JOB_STATUSES`（SUCCEEDED / FAILED / CANCELLED）。
- 生产 callable（`download_tools.py:47-95`、`preprocess_tools.py:46-94`）在 `runtime.start_download` / `runtime.start_preprocess` 返回后立即返回 `_awaiting_outcome_from_job_start(start)`，无任何等待或轮询逻辑。

**结论**: 通过。测试正确等待终态，生产 callable 保持非阻塞。

## 新增 Findings

无。

## 验证命令与结果

### pytest

```
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py -q
```

结果: **60 passed, 3 warnings**。仅有 edgar 依赖 deprecation warnings，不影响功能。

### pyright

```
source .venv/bin/activate && pyright
```

结果: **0 errors, 0 warnings, 0 informations**。pyright 提示有新版本可用，不影响类型验证。

## 代码抽查

对以下文件做了定向抽查，未发现 correctness / architecture / test regression：

- `dayu/fins/tools/download_provider.py` - provider 注册结构正确
- `dayu/fins/tools/preprocess_provider.py` - provider 注册结构正确
- `dayu/fins/tools/provider.py` - read provider 未受影响
- `dayu/fins/tools/__init__.py` - 导出无变化

## Residual Risk

- 本次未覆盖真实网络 downloader 成功路径；该路径不属于 controller accepted findings 范围。
- executor 提交异常测试在 durable job 创建后触发失败 outcome，遗留 queued record 是当前 runtime start 边界行为，本次未改变生产语义。
