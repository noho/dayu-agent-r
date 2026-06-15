# WU-CLI-FINS-OBS-01 Slice S5 Fix

## Scope

- Gate: code review fix
- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: S5 CLI logging assembly and command UI/log audit
- Source adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-code-review-adjudication-20260615-201806.md`
- Accepted findings fixed: `S5-FIX-01`, `S5-FIX-02`, `S5-FIX-03`

## First-Principles Judgment

三项 accepted finding 成立。CLI 和 Service 原本各自持有相同 verbose helper、payload key helper 与常量，属于层中立 runtime 日志能力重复实现；Service 的 event stream / cancel request failure 更接近 root cause，CLI 对同一异常再记录 `logger.exception(...)` 会产生 duplicate ERROR；CLI main 的 no-flag 默认路径需要直接证明 parser 默认 `log_level` 进入 runtime log 装配。

本轮只修复 S5 accepted findings，不进入 S6，不实现 prompt / interactive token streaming，不改变 public architecture、cancel 语义、terminal handling、异常传播或 UI error rendering。

## Changes

- `dayu/runtime/log.py`
  - 新增 `log_verbose(logger, ...)`，显式接收调用点 stdlib logger，保留模块 logger 归属。
  - 新增 `bounded_payload_keys(...)` 与 `DEFAULT_LOG_PAYLOAD_KEY_LIMIT`，只暴露排序后的有界 payload keys，不读取或输出 payload values。

- `dayu/cli/commands/fins.py`
  - 移除本地重复 verbose helper、payload key helper 与常量，改用 `dayu.runtime.log` helper。
  - 保留本模块 `_LOGGER = logging.getLogger(__name__)`。
  - 移除 `_consume_fins_direct_events` 与 `_wait_for_terminal_handling_sigint` 中对 Service stream / cancel failure 的 duplicate `logger.exception(...)`；异常仍原样向上传播，外层 CLI command 仍负责用户可见错误渲染。

- `dayu/service/fins_direct.py`
  - 移除本地重复 verbose helper、payload key helper 与常量，改用 `dayu.runtime.log` helper。
  - 保留本模块 `_LOGGER = logging.getLogger(__name__)`。
  - 保留 Service 对 event read failure、terminal fallback read failure、cancel request failure 的 ERROR traceback 真源。

- `tests/runtime/test_log.py`
  - 新增 runtime helper 测试，验证 `log_verbose(...)` 保留调用点 logger name，`bounded_payload_keys(...)` 只返回排序且有界的 keys。

- `tests/cli/test_arg_parsing.py`
  - CLI main log assembly spy 增加 no-flag default case，直接断言 parser 默认 `log_level="info"` 传入 `runtime_log.set_level_from_flags(...)`。

- `tests/cli/test_fins_commands.py`
  - 新增 Service stream failure 与 cancel failure 传播测试，防止 CLI 对同一异常重复记录 ERROR。

- `tests/README.md`
  - 同步 CLI log assembly、duplicate ERROR 去重与 runtime logging helper 的测试事实。

## Finding Status

| Finding | Status | Evidence |
| --- | --- | --- |
| `S5-FIX-01` | 已修复 | CLI / Service 重复 helper 和常量收敛到 `dayu.runtime.log`，调用点仍传入各自 stdlib logger，payload helper 只返回 bounded keys。 |
| `S5-FIX-02` | 已修复 | CLI stream / cancel failure 路径不再调用 `_LOGGER.exception(...)`，Service 保留 event stream / cancel request failure 的 ERROR 真源，异常传播与 UI rendering 未改。 |
| `S5-FIX-03` | 已修复 | `test_main_configures_runtime_log_from_parsed_cli_flags` 覆盖无 flag 的 parser 默认 `log_level="info"`。 |

## Docs Decision

- `tests/README.md`：已更新。原因是本轮新增并改变测试覆盖事实。
- `dayu/service/README.md`：不更新。Service public boundary 未变化，现有说明已覆盖 event observation、terminal fallback 与 durable cancel request；本轮只调整内部日志 helper 归属与 ERROR 真源。
- `dayu/README.md`：不更新。分层关系、公共架构和日志职责无新增 public contract。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py -q`
  - Result: `137 passed, 3 warnings`.
  - Warnings: edgar dependency deprecation warnings; no test failure.

- `source .venv/bin/activate && python -m pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py`
  - Result: `0 errors, 0 warnings, 0 informations`.

- `git diff --check`
  - Result: passed.

## Residual Risks

- Prompt / interactive token or content streaming remains outside S5 and is still excluded by approved scope.
- Runtime log handler timing and stdout handler assumptions remain the previously deferred low residual risk; this fix does not expand that area.
- No unclassified residual risk remains for the three accepted S5 findings.

## Completion Status

Fix implementation complete; validation passed; ready for S5 re-review.
