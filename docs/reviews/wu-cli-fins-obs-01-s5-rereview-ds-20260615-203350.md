# WU-CLI-FINS-OBS-01 Slice S5 Fix Re-Review

## Scope

- Mode: current changes (uncommitted, relative to S5-fix base)
- Branch: `phaseflow/host-issues-implementation`
- Base: accepted S5 implementation commit + adjudication
- Adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-code-review-adjudication-20260615-201806.md`
- Fix document: `docs/reviews/wu-cli-fins-obs-01-s5-fix-codex.md`
- Review target: S5-FIX-01, S5-FIX-02, S5-FIX-03
- Output file: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-ds-20260615-203350.md`
- Included scope:
  - `dayu/runtime/log.py` — 新增 `log_verbose`, `bounded_payload_keys`, `DEFAULT_LOG_PAYLOAD_KEY_LIMIT`, `LogArgument`
  - `dayu/cli/commands/fins.py` — 去重 helper、移除 duplicate ERROR log、新增 verbose/debug 事件诊断
  - `dayu/cli/main.py` — CLI main 直接调用 `runtime_log.set_level_from_flags`
  - `dayu/service/fins_direct.py` — 去重 helper、新增 Service 层 ERROR 真源 try/except、新增 verbose/debug 诊断
  - `tests/runtime/test_log.py` — 新增 `log_verbose` 调用点 logger 归属测试、`bounded_payload_keys` 有界 keys 测试
  - `tests/cli/test_arg_parsing.py` — 新增 CLI main log assembly spy 测试（含 no-flag 默认）
  - `tests/cli/test_fins_commands.py` — 新增默认日志不污染、verbose 骨架、debug 详情、stream/cancel failure 传播防线测试
  - `tests/README.md` — 同步测试覆盖事实
- Excluded scope: `docs/host/issues-implementation-control.md`（control doc 状态更新，非代码变更）
- Review method: 沿真实执行路径逐行走读 + adversarial failure pass

## Validation

- Pyright: `0 errors, 0 warnings, 0 informations`
- Tests: `137 passed, 3 warnings`（warnings 为 edgar 依赖废弃提示，与本次变更无关）
- `git diff --check`: passed

## Findings

未发现实质性问题。

## S5-FIX-01 逐项验证：runtime logging helper 去重

### 入口/函数: `dayu.runtime.log.log_verbose`, `dayu.runtime.log.bounded_payload_keys`

- **去重状态**: CLI (`dayu/cli/commands/fins.py`) 与 Service (`dayu/service/fins_direct.py`) 原有的本地重复 verbose helper、payload key helper 和常量已移除，统一改用 `dayu.runtime.log` 中的实现。
- **调用点 logger 归属**: `log_verbose(logger, ...)` 显式接收调用点 `logging.Logger` 参数。CLI 传入 `_LOGGER = logging.getLogger(__name__)` → 输出 `[dayu.cli.commands.fins]`；Service 传入同名 `_LOGGER` → 输出 `[dayu.service.fins_direct]`。`tests/runtime/test_log.py:test_log_verbose_uses_call_site_logger` 直接断言输出包含 `dayu.runtime_log_helper.case`，证明保留调用点 logger 名称。
- **payload key 安全**: `bounded_payload_keys` 只返回 `tuple(sorted(payload.keys()))[:DEFAULT_LOG_PAYLOAD_KEY_LIMIT]`，不读取、不格式化、不暴露 payload values。`tests/runtime/test_log.py:test_bounded_payload_keys_exposes_only_sorted_keys` 在 payload 中包含 `"z": "secret-value"`，断言 `"secret-value" not in keys`，直接证明 value 不泄露。
- **架构合规**: `dayu.runtime.log` 的 import 链为 `dayu.contracts.json_value.JsonValue`（公共契约类型）与 `dayu.runtime.log_levels`（runtime 子包），无 `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins` 依赖，符合 `dayu.runtime` 层中立约束。
- **类型合规**: `LogArgument: TypeAlias = str | int | float | bool | None`，无 `Any`/`object`/无类型签名。

**结论**: S5-FIX-01 完全合规。

## S5-FIX-02 逐项验证：CLI 不 duplicate ERROR 日志

### 入口/函数: `dayu.service.fins_direct.FinsDirectCommandService`

- **Service ERROR 真源**: 三项关键 runtime 调用已包装 try/except + `_LOGGER.exception(...)` + `raise`。

  | 位置 | 操作 | 真源 |
  |---|---|---|
  | `stream_job_events_until_terminal:570-582` | `self._runtime.read_job_events(...)` | "Fins direct job event read failed; job_id=%s after_sequence=%s" |
  | `stream_job_events_until_terminal:607-614` | `self._runtime.read_job(...)` | "Fins direct terminal fallback read failed; job_id=%s" |
  | `request_cancel:644-648` | `self._runtime.request_cancel(...)` | "Fins direct cancel request failed; job_id=%s" |

  每次 `except Exception` 记录 ERROR traceback 后原样 `raise`，保证异常传播不被吞没。

### 入口/函数: `dayu.cli.commands.fins._consume_fins_direct_events`

- **CLI 消费路径**: `async for event in service.stream_job_events_until_terminal(handle)` 无 try/except 包装，stream failure 异常直接向上传播。函数内仅调用 `_log_fins_direct_event_received`（VERBOSE/DEBUG 级别诊断）和 `render_fins_direct_event`（用户 UI 输出），无 `_LOGGER.exception(...)` 调用。

### 入口/函数: `dayu.cli.commands.fins._wait_for_terminal_handling_sigint`

- **CLI cancel 路径**: `service.request_cancel(handle.job_id)` 无 try/except 包装，cancel failure 异常直接向上传播。函数内仅 `runtime_log.log_verbose(...)` 记录 cancel 意图（VERBOSE 级别），无 `_LOGGER.exception(...)` 调用。
- **异常传播完整链**: `Service._runtime.*` raise → Service try/except 记录 ERROR → Service re-raise → `stream_job_events_until_terminal`/`request_cancel` 抛出 → `_consume_fins_direct_events`/`_wait_for_terminal_handling_sigint` 透传 → `_run_fins_direct_command_async` 透传 → `run_fins_direct_command` catch `Exception` → `render_cli_error(...)` → 返回 `EXIT_FAILURE`。用户看到 stderr 错误消息，Service 日志输出含完整 traceback。
- **cancel 语义不变**: 第一次 SIGINT → `service.request_cancel(job_id)` 发起 durable cancel → 终端渲染 cancel 提示 → 继续等待终态。第二次 SIGINT → 本地退出返回 `None` → `EXIT_KEYBOARD_INTERRUPT`。cancel 流程未变。
- **KeyboardInterrupt 处理不变**: `run_fins_direct_command` 独立 catch `KeyboardInterrupt` → `EXIT_KEYBOARD_INTERRUPT`，与 exception 通用路径分离。
- **UI error rendering 不变**: `FinsDirectUsageError`、`UploadBatchPlanUsageError`、`UploadBatchPlanEmptyError`、`CliFinsUsageError` 各自有独立 catch 分支，退出码语义不变。

### 测试防线

- `test_cli_stream_failure_propagates_without_duplicate_error_log`: monkeypatch `fins_command._LOGGER.exception` → `_raise_on_cli_exception_log`（任何调用即抛 `AssertionError`），验证 stream failure 向上传播且 CLI 不调用 `_LOGGER.exception`。
- `test_cli_cancel_failure_propagates_without_duplicate_error_log`: 同上 monkeypatch，验证 cancel failure 传播且 CLI 不重复记录 ERROR。

**结论**: S5-FIX-02 完全合规，ERROR 真源在 Service，CLI 不 duplicate，异常/cancel/UI error 语义不变。

## S5-FIX-03 逐项验证：默认 log-level spy 直接覆盖

### 入口/函数: `tests/cli/test_arg_parsing.py:test_main_configures_runtime_log_from_parsed_cli_flags`

- **覆盖矩阵**: 5 条 parametrize 用例全覆盖 `log_level` 输入路径。

  | argv | expected_log_level | 来源 |
  |---|---|---|
  | `("prompt", "hello")` | `"info"` | argparse `DEFAULT_LOG_LEVEL = "info"` |
  | `("prompt", "hello", "--debug")` | `"debug"` | argparse `--debug` `const="debug"` |
  | `("prompt", "hello", "--verbose")` | `"verbose"` | argparse `--verbose` `const="verbose"` |
  | `("prompt", "hello", "--quiet")` | `"error"` | argparse `--quiet` `const="error"` |
  | `("prompt", "hello", "--log-level", "warn")` | `"warn"` | argparse `--log-level` 显式值 |

- **spy 验证**: `monkeypatch.setattr(cli_main.runtime_log, "set_level_from_flags", spy_set_level_from_flags)` 直接拦截 `runtime_log.set_level_from_flags` 调用，记录传入参数。断言 `log_level` 等于 `expected_log_level`，且 `debug`/`verbose`/`info`/`quiet` 全部为 `False`（因 CLI main 把解析职责交给 argparse，`log_level` 已是归一结果）。
- **default case 直接证明**: `("prompt", "hello")` → `log_level="info"`，证明无 flag 情况下 argparse 默认 `"info"` 直接进入 `set_level_from_flags`，满足裁决要求的 "directly prove `runtime_log.set_level_from_flags` is invoked with the parser-normalized default log level"。

**结论**: S5-FIX-03 完全合规。

## 交叉检查

### 新增 Any/object/无类型签名
无。`LogArgument` 为显式 union 类型；`bounded_payload_keys` 参数和返回值完全类型化；所有新增 docstring 包含完整参数/返回值/异常说明。

### 分层反向依赖
无。`dayu.runtime.log` 仅 import `dayu.contracts.json_value`（公共契约）与 `dayu.runtime.log_levels`（runtime 子包），不触及 `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`。CLI 与 Service 的 `import dayu.runtime.log` 为正向依赖。

### LLM-facing 语义
无问题。新增内容为日志诊断消息与测试断言，不进入 LLM context、tool schema、prompt 或 system/user/assistant message。

### README 触发
- `tests/README.md`: 已更新，涵盖 CLI log assembly spy、默认不污染 progress、verbose 骨架/debug 详情、duplicate ERROR 去重防线、runtime logging helper 测试。✅
- `dayu/service/README.md`: 未触发。Service public boundary 未变化，现有文档已覆盖 event observation、terminal fallback、durable cancel request。✅
- `dayu/README.md`: 未触发。日志辅助函数收敛到 `dayu.runtime.log` 属于运行时基础设施内部演进，UI/Service/Host/Agent 分层关系无变化。✅

### 测试覆盖
- 新增 `tests/runtime/test_log.py`: `test_log_verbose_uses_call_site_logger`（调用点 logger 归属）、`test_bounded_payload_keys_exposes_only_sorted_keys`（有界 key 不泄值）
- 新增 `tests/cli/test_arg_parsing.py`: `test_main_configures_runtime_log_from_parsed_cli_flags`（5 参数化，含默认）
- 新增 `tests/cli/test_fins_commands.py`: `test_fins_direct_default_log_does_not_pollute_progress_output`、`test_fins_direct_verbose_log_outputs_execution_skeleton`、`test_fins_direct_debug_log_outputs_event_details`、`test_cli_stream_failure_propagates_without_duplicate_error_log`、`test_cli_cancel_failure_propagates_without_duplicate_error_log`
- 既有测试全部通过，无退化。

### Adversarial failure pass
- `log_verbose` 在 VERBOSE 级别未注册时静默跳过（`isinstance(verbose_level, int)` 守卫），已在模块导入时 `logging.addLevelName(VERBOSE_LOG_LEVEL, _VERBOSE_LEVEL_NAME)` 注册，且 `test_log_level_verbose_registered_with_stdlib` 直接验证。不构成真实风险。
- `bounded_payload_keys` 对超大 payload（超过 8 keys）先全量排序再截断，但 payload 在 Fins ingestion event 场景下受 runtime 约束，不超过 `FINS_DIRECT_JOB_EVENT_READ_LIMIT` 相关边界。不构成真实性能风险。
- Service `request_cancel` 的 `except Exception` 使用 `_LOGGER.exception(...)` — 若 logging 框架本身失败（如磁盘满），`logging.exception` 默认不抛异常（Python `logging.Handler.handleError` 静默处理），不会因诊断日志导致原异常被吞没。

## Open Questions

无。

## Residual Risk

- Prompt / interactive token or content streaming 不在 S5 scope，为已接受计划范围排除项。
- Runtime log handler timing 与 stdout handler 假设仍为 adjudication 记录的 deferred low residual risk；本次 fix 未扩大该区域。

## Conclusion

**PASS**

三项 accepted finding (S5-FIX-01, S5-FIX-02, S5-FIX-03) 全部正确实现，无新增 Any/object/无类型签名、无分层反向依赖、无 LLM-facing 语义问题、README 触发正确、测试覆盖充分，pyright 零报错，全部 137 个相关测试通过。
