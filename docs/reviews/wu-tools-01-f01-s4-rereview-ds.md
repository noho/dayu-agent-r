# WU-TOOLS-01-F01 Slice S4 Fix Re-review Artifact

## Gate Metadata

- Gate: deep review (定向复审)。
- Work unit: `WU-TOOLS-01-F01`。
- Slice: `S4 - Download / Preprocess Awaiting Tool Providers`。
- Branch: `host-wu-tools-01-f01`。
- 输入裁决: `docs/reviews/wu-tools-01-f01-s4-code-review-controller-adjudication.md`。
- 输入 fix artifact: `docs/reviews/wu-tools-01-f01-s4-fix-codex.md`。
- 复审范围: 仅验证 3 条 accepted findings 的修复状态，不重新全量评审。

## 结论：pass

三条 accepted findings 均已正确修复，fix 未引入新的 correctness / architecture / test regression。

## 逐项修复验证

### F01-S4-001 — 共享 helpers 提取

**状态：已修复。**

- 新增私有模块 `dayu/fins/tools/_ingestion_tool_helpers.py`，承载 7 个共享辅助函数：`_awaiting_outcome_from_job_start`、`_failed_outcome`、`_required_text`、`_optional_text`、`_optional_nullable_text`、`_optional_text_tuple`、`_optional_bool`。
- `download_tools.py:21-29` 仅导入所需 helper，不导入自身不用的函数，保持依赖最小化。
- `preprocess_tools.py:22-28` 同理。
- 各工具模块保留自身职责不变：tool name（`DOWNLOAD_TOOL_NAME`、`PREPROCESS_TOOL_NAME`）、schema 定义（`_download_parameters_schema`、`_preprocess_parameters_schema`）、request construction（`_download_request_from_arguments`、`_preprocess_request_from_arguments`）。
- 无重复 helper 逻辑残留。

### F01-S4-002 — OSError 与 unexpected exception 测试覆盖

**状态：已修复。**

- `tests/fins/test_fins_ingestion_tools.py` 新增 4 个聚焦测试：
  - `test_download_tool_os_error_from_start_returns_start_failed_outcome`（line 256）：注入 `_OSErrorCreateJobStore` 在 `create_job` 时抛 `OSError`，断言 `ToolFailedOutcome` 且 `error == "fins_download_start_failed"`。
  - `test_download_tool_unexpected_start_exception_returns_start_failed_outcome`（line 276）：注入 `_RuntimeErrorExecutor` 在 `submit` 时抛 `RuntimeError`，断言 `ToolFailedOutcome` 且 `error == "fins_download_start_failed"`。
  - `test_preprocess_tool_os_error_from_start_returns_start_failed_outcome`（line 296）：同下载 OSError 覆盖预处理路径。
  - `test_preprocess_tool_unexpected_start_exception_returns_start_failed_outcome`（line 316）：同下载 RuntimeError 覆盖预处理路径。
- 测试夹具边界清晰：`_OSErrorCreateJobStore` 模拟持久化失败，`_RuntimeErrorExecutor` 模拟后台提交失败，两者通过 `_runtime_with_job_store` / `_runtime_with_executor` 注入独立的 `FinsIngestionRuntime` 实例。
- 异常类型区分正确：`OSError` 走 `except OSError:` 分支（`download_tools.py:79`、`preprocess_tools.py:78`），`RuntimeError`（及任意非特定 Exception）走 `except Exception:` 分支（`download_tools.py:87`、`preprocess_tools.py:86`）。

### F01-S4-003 — Awaiting outcome 测试等待 job 终态

**状态：已修复。**

- `test_download_tool_returns_external_job_awaiting_outcome`（line 175）：先断言 `ToolAwaitingOutcome` 和 `EXTERNAL_JOB`（lines 194-195），then 通过同一 workspace 派生的 `DefaultFinsRuntime.create(workspace_root=...).get_ingestion_runtime()` 读取 job record 并验证 `operation_kind` 和 `normalized_ticker`（lines 196-199），最后调用 `_wait_ingestion_job_terminal` 等待终态（line 200）。
- `test_preprocess_tool_returns_external_job_awaiting_outcome`（line 203）：相同模式，line 222-228。
- `_wait_ingestion_job_terminal`（line 459）：以 5s 超时、20ms 间隔轮询，在 `SUCCEEDED`/`FAILED`/`CANCELLED` 任一终态到达时返回。超时未达终态抛 `AssertionError`。
- 生产 callable（`FinsDownloadToolCallable.__call__`、`FinsPreprocessToolCallable.__call__`）均保持非阻塞：仅在 durable job 创建后返回 `ToolAwaitingOutcome`，不轮询 job 完成。

## 新增 Findings

无。

对本次 fix 涉及的所有模块进行了下列检查，未发现新增 correctness / architecture / test regression：

- **helper 模块重用正确性**：`download_tools.py` 和 `preprocess_tools.py` 各自只导入所需 helper，无多余导入；helper 函数签名在生产和测试间一致。
- **异常处理层次正确**：`OSError` 的 catch 在 `except OSError:` 而非 `except Exception:`，`RuntimeError` 和任意非预期异常走 `except Exception:`；两层 catch 互不遮蔽。
- **测试隔离性**：`_OSErrorCreateJobStore` 和 `_RuntimeErrorExecutor` 通过 `_runtime_with_job_store` / `_runtime_with_executor` 构造独立 `FinsIngestionRuntime` 实例注入，不依赖全局状态或 monkeypatching。
- **`__init__.py` 导出语义**：`discover_tools`（read）、`discover_download_tools`、`discover_preprocess_tools` 均为显式命名导出，非 compatibility re-export；符合计划禁止旧兼容转发的约束。
- **provider 层无重复**：`download_provider.py` 和 `preprocess_provider.py` 共享 `parse_fins_workspace_root_config` 用于 config 解析；各自的 `_source_ref()` 函数是 5 行工厂函数，抽取将构成过度抽象，不符合项目 "三个相似行优于过早抽象" 的指导原则。

## 验证命令与结果

```
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py -q
```
结果：**60 passed**，3 warnings（仅 `edgar` 库 deprecation warnings，与本次改动无关）。

```
source .venv/bin/activate && pyright
```
结果：**0 errors, 0 warnings, 0 informations**。

## README 同步决策

本次 fix 仅涉及工具适配层私有 helper 组织方式和测试覆盖补充，不改变用户可见命令、配置入口、provider contract、tool name、tool schema、awaiting outcome 或任何 README 职责范围内的稳定行为。不触发 CLAUDE.md 中任何 README 更新规则。不更新 README。
