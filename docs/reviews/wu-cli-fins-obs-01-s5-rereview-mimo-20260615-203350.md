# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-mimo-20260615-203350.md`
- Included scope: S5 fix 后未提交改动（`dayu/runtime/log.py`、`dayu/cli/main.py`、`dayu/cli/commands/fins.py`、`dayu/service/fins_direct.py`、`tests/runtime/test_log.py`、`tests/cli/test_arg_parsing.py`、`tests/cli/test_fins_commands.py`、`tests/README.md`、`docs/host/issues-implementation-control.md`），相对于已接受的 S5 implementation + 裁决。
- Excluded scope: 已提交的 S1–S4 slice、未涉及的 engine/fins/contracts 模块。
- Parallel review coverage: 无

## Findings

未发现实质性问题。

S5-FIX-01、S5-FIX-02、S5-FIX-03 三项 accepted finding 均已正确实现，详见下方逐项验证。

### S5-FIX-01 验证：runtime logging helper 去重

- `dayu/runtime/log.py` 新增 `log_verbose(logger, message, *args: LogArgument)`，显式接收调用点 stdlib logger，保留模块 logger 归属。实现正确：`logging.getLevelName("VERBOSE")` 返回已注册的 int level，`logger.log(verbose_level, message, *args)` 走 stdlib 标准路径。
- `dayu/runtime/log.py` 新增 `bounded_payload_keys(payload: Mapping[str, JsonValue]) -> tuple[str, ...]` 与 `DEFAULT_LOG_PAYLOAD_KEY_LIMIT = 8`。只返回排序后 key 切片，不读取/格式化/暴露 value。
- `dayu/cli/commands/fins.py` 和 `dayu/service/fins_direct.py` 已移除本地重复的 verbose helper、payload key helper 与常量，统一使用 `dayu.runtime.log` 导出。
- `__all__` 已更新，导出 `log_verbose`、`bounded_payload_keys`、`DEFAULT_LOG_PAYLOAD_KEY_LIMIT`、`LogArgument`。
- 调用点 logger 仍为各自模块的 `_LOGGER = logging.getLogger(__name__)`，未收敛到 runtime。

### S5-FIX-02 验证：CLI 不再 duplicate ERROR

- `_consume_fins_direct_events`（`fins.py:611`）不再调用 `_LOGGER.exception(...)`。Service `stream_job_events_until_terminal`（`fins_direct.py:570-582`）保留 `_LOGGER.exception("Fins direct job event read failed; ...")` 作为 ERROR 真源，异常原样 `raise`。
- `_wait_for_terminal_handling_sigint`（`fins.py:584`）的 `service.request_cancel(handle.job_id)` 调用不再包裹 `_LOGGER.exception(...)`。Service `request_cancel`（`fins_direct.py:644-648`）保留 `_LOGGER.exception("Fins direct cancel request failed; ...")` 作为 ERROR 真源，异常原样 `raise`。
- 异常传播路径未改变：Service 抛出的异常经 CLI `_run_fins_direct_command_async` 向上传播至 `run_fins_direct_command` 的 `except Exception` 分支，由 `render_cli_error` 输出用户可见错误，返回 `EXIT_FAILURE`。
- 测试 `test_cli_stream_failure_propagates_without_duplicate_error_log` 和 `test_cli_cancel_failure_propagates_without_duplicate_error_log` 通过 monkeypatch `_LOGGER.exception` 为 `_raise_on_cli_exception_log`（断言失败），直接证明 CLI 层不再对 Service 已负责的异常记录 ERROR。

### S5-FIX-03 验证：默认 log-level spy 覆盖

- `test_main_configures_runtime_log_from_parsed_cli_flags` 参数化覆盖五种场景：`("prompt", "hello")` → `log_level="info"`（默认）、`--debug` → `"debug"`、`--verbose` → `"verbose"`、`--quiet` → `"error"`、`--log-level warn` → `"warn"`。
- spy 直接拦截 `cli_main.runtime_log.set_level_from_flags`，断言传入参数与 parser 归一后的 `log_level` 值一致。
- 默认 case 的 `log_level="info"` 与 `arg_parsing.py` 的 `DEFAULT_LOG_LEVEL = "info"` 一致。

### 其它检查项

- **Any/object/无类型签名**: 未新增。`LogArgument: TypeAlias = str | int | float | bool | None` 为精确标量类型别名。所有新增函数签名均有完整类型标注。
- **分层反向依赖**: `dayu.runtime.log` 仅 import `dayu.contracts.json_value.JsonValue`（contracts 低于 runtime），未 import CLI/Service/Host/Engine。CLI 和 Service 对 `dayu.runtime.log` 的 import 方向正确（上层 → 下层）。
- **LLM-facing 语义**: 本轮改动不涉及 tool schema、prompt、memory/compact/evidence material，无 LLM-facing 语义问题。
- **README 触发**: `tests/README.md` 已同步 CLI log assembly、duplicate ERROR 去重与 runtime logging helper 的测试事实。`dayu/service/README.md` 不更新（Service public boundary 未变化）。`dayu/README.md` 不更新（分层关系无变化）。`dayu/runtime/README.md` 不在触发规则内。
- **测试缺口**: 82 passed, 0 failed。`test_log_verbose_uses_call_site_logger` 验证 helper 保留调用点 logger name。`test_bounded_payload_keys_exposes_only_sorted_keys` 验证 key 排序、有界、不暴露 value。stream/cancel failure 传播测试覆盖了 S5-FIX-02 的关键路径。

## Open Questions

- 无。

## Residual Risk

- Prompt / interactive token or content streaming 仍不在 S5 范围内，与既往 deferred risk 一致。
- Runtime log handler timing 和 stdout handler 假设仍为既往 deferred low residual risk；本轮 fix 未扩展该区域。
- 本轮新增的 `_log_fins_direct_event_received`（CLI 层）和 `_log_runtime_event_received`（Service 层）对同一底层事件分别记录 verbose 和 debug 诊断。两层日志在不同抽象层级、不同 detail 粒度，设计意图合理；但若未来 event volume 增长，需关注 debug 日志的 I/O 成本。
