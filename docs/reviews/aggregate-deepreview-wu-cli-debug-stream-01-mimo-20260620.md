# Aggregate Deep Review — WU-CLI-DEBUG-STREAM-01

## Scope

- Mode: current changes
- Branch: `wu-cli-debug-stream-01`
- Base: `main`
- Reviewer: AgentMiMo (Claude Code Agent)
- Output file: `docs/reviews/aggregate-deepreview-wu-cli-debug-stream-01-mimo-20260620.md`
- Commits reviewed: `61bc9a9d`, `f53762a5`, `67ca96fb`, `c0c125f3`, `928281bd`, `8e100e7c`, `f084a340`, `3481da68`
- Design truth sources: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Plan doc: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`

### Changed production files

| File | Layer | Change |
|------|-------|--------|
| `dayu/runtime/log_levels.py` | Runtime | 新增 `STREAM_DEBUG_LOG_LEVEL = DEBUG - 1` 常量 |
| `dayu/runtime/log.py` | Runtime | 注册 STREAM_DEBUG level name、`LogLevel.STREAM_DEBUG` 枚举、`set_level_from_flags` 新增 `debug_stream` 参数 |
| `dayu/cli/arg_parsing.py` | CLI | 新增 `--debug-stream` 全局参数 |
| `dayu/cli/main.py` | CLI | 传递 `debug_stream` 到 `set_level_from_flags` |
| `dayu/engine/runners/openai/runner.py` | Engine | stream idle heartbeat 从 `DEBUG` 改为 `STREAM_DEBUG` |
| `dayu/engine/runners/openai/sse_parser.py` | Engine | SSE done-token 从 `DEBUG` 改为 `STREAM_DEBUG` |
| `dayu/host/engine_ingest.py` | Host | delta event ingest 从 `DEBUG` 改为 `STREAM_DEBUG` |

### Changed test files

| File | Change |
|------|--------|
| `tests/runtime/test_log_levels.py` | 验证 `STREAM_DEBUG_LOG_LEVEL` 常量与隔离导入无副作用 |
| `tests/runtime/test_log.py` | 验证 STREAM_DEBUG 注册、优先级、DEBUG 抑制 / STREAM_DEBUG 放出 |
| `tests/cli/test_arg_parsing.py` | 验证 `--debug-stream` help 显示、解析透传、`set_level_from_flags` 调用 |
| `tests/cli/test_interactive_command.py` | 验证 `--debug-stream` 不是 unsupported old flag、诊断不污染 stdout |
| `tests/cli/test_prompt_command.py` | 验证 `--debug-stream` 不是 unsupported old flag、诊断不污染 stdout |
| `tests/engine/runners/openai/test_runner_diagnostics.py` | 验证 heartbeat / done-token 的 STREAM_DEBUG gating |
| `tests/host/test_logging.py` | 验证 delta ingest 使用 STREAM_DEBUG 且受 DEBUG 抑制 |
| `tests/README.md` | 更新测试覆盖说明 |

### 验证结果

- **Tests**: 40 个关键测试全部通过（`pytest -x -q`）
- **Pyright**: 0 errors, 0 warnings, 0 informations

---

## Findings

未发现实质性问题。

### 详细审查结论

#### 1. Issue #148 需求满足度

**结论：满足。**

- `STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1` (= 9)，低于 stdlib DEBUG (10)。当 level 为 DEBUG 时，`log(9, ...)` 不会输出；当 level 为 STREAM_DEBUG 时，`log(9, ...)` 和 `debug(...)` 都会输出。
- `_resolve_level` 中 `debug_stream` 优先级最高（第 1 位），高于 `log_level` 字符串、`quiet`、`debug`、`verbose`、`info`。
- `--debug-stream` 是 `store_true` 的独立 bool flag，不写入 `log_level`；`--debug` 是 `store_const` 写入 `log_level="debug"`。两者可组合且不冲突：`--debug-stream` 覆盖 `--debug`。
- 三处高频 stream 诊断（ingest delta、heartbeat、done-token）全部从 `DEBUG` 迁移到 `STREAM_DEBUG`。普通 warnings/errors/lifecycle/HTTP DEBUG 日志未被误降级。

#### 2. 分层正确性

**结论：正确，无反向依赖。**

- `dayu/runtime/log_levels.py` 只依赖 stdlib `logging` 和 `typing`，是层中立常量。
- `dayu/runtime/log.py` 依赖 `dayu.runtime.log_levels` 和 `dayu.contracts.json_value`（符合 runtime 可依赖更底层公共契约约束）。
- `dayu/cli/arg_parsing.py` 和 `dayu/cli/main.py` 导入 `dayu.runtime.log`（CLI → Runtime，正向）。
- `dayu/engine/runners/openai/runner.py` 和 `sse_parser.py` 导入 `dayu.runtime.log_levels`（Engine → Runtime，正向）。
- `dayu/host/engine_ingest.py` 导入 `dayu.runtime.log_levels`（Host → Runtime，正向）。
- 无 Runtime → Engine / Host / CLI 反向导入。
- 无 schema、state-machine 或 public Host/Engine contract 非预期变化。

#### 3. Host ingest delta / heartbeat / done-token 迁移完整性

**结论：完整。**

- `engine_ingest.py:_engine_ingest_log_level`: delta 事件返回 `STREAM_DEBUG_LOG_LEVEL`，非 delta 返回 `VERBOSE_LOG_LEVEL`。`_DELTA_ENGINE_EVENT_TYPES` 包含 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`。
- `runner.py:_iter_response_bytes_with_idle`: heartbeat 日志从 `_LOGGER.debug(...)` 改为 `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)`。
- `sse_parser.py:_dispatch_event_payload`: done-token 日志从 `_LOGGER.debug(...)` 改为 `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)`。
- 所有 `_LOGGER.warning(...)` 和 `_LOGGER.error(...)` 调用未被修改，保持原有级别。
- `_LOGGER.debug(...)` 用于 HTTP POST、response status 等非高频路径，未被误迁移到 STREAM_DEBUG。

#### 4. Prompt/Interactive 兼容性守卫

**结论：准确、不过度承诺。**

- `--debug-stream` 是全局参数（`_build_global_arguments_parent`），不是旧 Agent 执行参数（`_add_agent_execution_arguments`）。
- `unsupported_execution_option_names` 只检查旧执行参数，不包含 `--debug-stream`。测试 `test_interactive_debug_stream_is_not_unsupported_execution_option` 和 `test_prompt_debug_stream_is_not_unsupported_execution_option` 直接验证此行为。
- 诊断不污染 stdout 测试（`test_*_verbose_debug_diagnostics_do_not_pollute_stdout`）已扩展覆盖 `--debug-stream`。
- README 中 `--debug-stream` 描述不泄漏内部治理术语（如 event_id、payload_ref、cursor 等）。

#### 5. 测试矩阵与 README 触发规则

**结论：足够。**

- Runtime 常量、枚举注册、优先级、DEBUG 抑制 / STREAM_DEBUG 放出：全覆盖。
- CLI 参数解析、help 文本、runtime 透传：全覆盖。
- Engine heartbeat / done-token STREAM_DEBUG gating：全覆盖。
- Host delta ingest STREAM_DEBUG gating：全覆盖。
- Prompt/interactive 兼容性守卫：全覆盖。
- `tests/README.md` 已更新 logging 覆盖说明。
- `README.md` 已更新参数表、说明、示例，触发规则命中（CLI 入口变化 → 根目录 README.md）。

#### 6. memory_repair.catch_up.budget_exhausted

按指令要求，此为已修复 bug，非噪音项。当前分支未发现回归证据，不作为 finding。

#### 7. Pre-existing README --log-level critical mismatch

**结论：确认为本 WU 外 residual。**

- `main` 分支 `README.md` 第 290 行列出 `--log-level` 可选 `critical`，但 `LOG_LEVEL_CHOICES` 只包含 `debug`、`verbose`、`info`、`warn`、`error`（无 `critical`）。
- 本分支未修改 `LOG_LEVEL_CHOICES`，未加剧此问题。
- `set_level_from_flags` 的字符串路径可解析 `critical`（因为 `LogLevel.CRITICAL` 存在），但 argparse 不会接受它作为 `--log-level` 的值。
- 此 mismatch 不属于本 WU 范围，不作为 blocker。

---

## Open Questions

无。

## Residual Risk

- `--log-level stream_debug` 在 argparse 层不被接受（不在 `LOG_LEVEL_CHOICES` 中），但 `_resolve_level` 的字符串路径可以解析它。用户无法通过 `--log-level stream_debug` 启用 stream debug，只能用 `--debug-stream`。这是设计意图而非 bug，但未在文档中说明。
- `--debug-stream` 的 argparse help 文本说"不要与互相矛盾的日志等级参数组合使用"，但实现上 `--debug-stream` 有最高优先级且可与任何组合安全使用。help 文本略显保守但不致误导。

---

## Conclusion

**PASS**

本 WU 实现完整、分层正确、测试充分。Issue #148 的全部需求已满足：普通 `--debug` 不输出高频 per-delta stream diagnostics；`--debug-stream` 显式启用普通 DEBUG 加 stream delta / SSE / per-delta ingest 诊断；`--debug-stream` 与 `--debug` 可组合且优先级正确。无 must-fix findings。
