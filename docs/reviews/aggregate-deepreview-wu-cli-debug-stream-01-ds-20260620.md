# Aggregate Deepreview — WU-CLI-DEBUG-STREAM-01 (AgentDS)

## Scope

- Mode: current changes
- Branch: `wu-cli-debug-stream-01`
- Base: `main`
- Output file: `docs/reviews/aggregate-deepreview-wu-cli-debug-stream-01-ds-20260620.md`
- Included scope: 所有 WU-CLI-DEBUG-STREAM-01 改动，覆盖 commits `61bc9a9d`、`f53762a5`、`67ca96fb`、`c0c125f3`、`928281bd`、`8e100e7c`、`f084a340`、`3481da68`
- Excluded scope: 无（全量审查）
- Parallel review coverage: 无（AgentDS 单路独立最终 review）
- Design sources: `docs/host/design.md`、`docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Plan: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- GitHub Issue: #148

## Review Execution Summary

### 逐条重点核查

#### 1. Issue #148 行为契约

| 场景 | 预期 | 实际 | 证据 |
|---|---|---|---|
| `--debug` 单独 | 普通 DEBUG（Host open/command/admission/dispatch/runner HTTP/terminal closeout/warning/error），不输出逐 delta ingest / stream heartbeat / SSE done-token | ✅ 符合 | `_engine_ingest_log_level()` 对 delta 返回 `STREAM_DEBUG_LOG_LEVEL`（9），低于 `logging.DEBUG`（10），普通 DEBUG handler 不发射；Runner heartbeat 与 SSE done-token 使用 `STREAM_DEBUG_LOG_LEVEL`；Runner lifecycle/HTTP 保持 `logging.DEBUG`；warnings 保持 `WARNING` |
| `--debug-stream` 单独 | 普通 DEBUG + stream delta / SSE / per-delta ingest 诊断 | ✅ 符合 | `_resolve_level(debug_stream=True)` → `LogLevel.STREAM_DEBUG`（9），低于 `DEBUG`（10），同时发射 STREAM_DEBUG 与 DEBUG 记录 |
| `--debug --debug-stream` 组合 | 等价于 `--debug-stream`（stream-debug 最细粒度） | ✅ 符合 | `_resolve_level` 在最前面检查 `debug_stream`，返回 `LogLevel.STREAM_DEBUG`，忽略已解析的 `log_level="debug"` |
| `--debug-stream --quiet` | `debug_stream` 优先级最高（stream-debug） | ✅ 符合 | `test_parse_cli_args_debug_stream_and_quiet_runtime_precedence` 验证 `resolved is LogLevel.STREAM_DEBUG`；help 文本警告不要与矛盾参数组合 |
| 优先级链 | `debug_stream` > `log_level` > `quiet` > `debug` > `verbose` > `info` > 默认 INFO | ✅ 符合 | `_resolve_level()` 代码路径按此顺序检查；每个分支都有对应测试 |

#### 2. 分层正确性

| 检查项 | 结论 | 证据 |
|---|---|---|
| Runtime 层中立 | ✅ | `dayu.runtime.log_levels` 只定义整数常量，不注册 level name、不安装 handler、不读取配置 |
| Runtime log 装配层中立 | ✅ | `dayu.runtime.log` 操作 `logging.getLogger("dayu")` namespace logger，不依赖 Host/Engine/CLI |
| CLI → Runtime | ✅ | `dayu/cli/main.py` 导入 `dayu.runtime.log`（runtime 层），传递 `debug_stream` 给 `set_level_from_flags()` |
| Host → Runtime | ✅ | `dayu/host/engine_ingest.py` 导入 `STREAM_DEBUG_LOG_LEVEL` 从 `dayu.runtime.log_levels`（runtime 层） |
| Engine → Runtime | ✅ | `dayu/engine/runners/openai/runner.py` 与 `sse_parser.py` 导入 `STREAM_DEBUG_LOG_LEVEL` 从 `dayu.runtime.log_levels` |
| 无反向依赖 | ✅ | Runtime 层不导入任何 Host/Engine/CLI/Service 模块 |
| 无跨层穿透 | ✅ | CLI 不直接读取 Host/Engine 内部状态；Host/Engine 不读取 CLI 参数 |

#### 3. Stream 诊断迁移完整性

| 日志站点 | 旧级别 | 新级别 | 状态 |
|---|---|---|---|
| Host `_engine_ingest_log_level()` delta events | `logging.DEBUG` | `STREAM_DEBUG_LOG_LEVEL` | ✅ 已迁移 |
| Host `_engine_ingest_log_level()` non-delta events | `VERBOSE_LOG_LEVEL` | `VERBOSE_LOG_LEVEL` | ✅ 不变 |
| OpenAI runner `stream_idle.heartbeat` | `logging.DEBUG` | `STREAM_DEBUG_LOG_LEVEL` | ✅ 已迁移 |
| OpenAI SSE `sse.done_token received` | `logging.DEBUG` | `STREAM_DEBUG_LOG_LEVEL` | ✅ 已迁移（且新增 `provider_request_id` 上下文） |
| OpenAI runner `attempt.start` / `http.post` / `http.response` | `logging.DEBUG` | `logging.DEBUG` | ✅ 不变 |
| Protocol warnings/errors | `WARNING`/`ERROR` | `WARNING`/`ERROR` | ✅ 不变 |

未发现任何 warning/error/lifecycle/HTTP DEBUG 被误降级。

#### 4. Prompt/Interactive 兼容性

| 检查项 | 结论 | 证据 |
|---|---|---|
| `--debug-stream` 不在 `unsupported_execution_option_names()` 中 | ✅ | `test_prompt_debug_stream_is_not_unsupported_execution_option()` 和 `test_interactive_debug_stream_is_not_unsupported_execution_option()` 均通过 |
| `--debug-stream` 诊断不污染 stdout | ✅ | `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` 和 `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` 已扩展参数化覆盖 `--debug-stream` |
| 旧 `--debug-sse` / `--debug-tool-delta` unsupported 守卫不变 | ✅ | 旧 Agent 执行参数守卫测试保持通过 |
| README 不泄漏内部治理术语 | ✅ | README 只暴露用户可见行为（stream delta、SSE、ingest），不提及 `EngineEvent`、`_DELTA_ENGINE_EVENT_TYPES`、`STREAM_DEBUG_LOG_LEVEL`、`_engine_ingest_log_level` 等内部术语 |
| tests README 描述准确 | ✅ | tests README 更新覆盖了 runtime stream-debug 级别、Host delta ingest gating、Runner stream heartbeat/done-token gating、CLI `--debug-stream` 参数 |

#### 5. 测试矩阵与残余风险

| 测试面 | 覆盖情况 | 文件 |
|---|---|---|
| Runtime 常量定义 | `STREAM_DEBUG_LOG_LEVEL == 9 < 10`，隔离导入无副作用 | `tests/runtime/test_log_levels.py` |
| Runtime 级别注册 | `logging.getLevelName(9) == "STREAM_DEBUG"` | `tests/runtime/test_log.py` |
| Runtime 优先级解析 | `debug_stream > log_level > quiet > debug > verbose > info > default`，DEBUG 抑制 STREAM_DEBUG，STREAM_DEBUG 同时发射二者 | `tests/runtime/test_log.py` |
| CLI 解析 | `--debug-stream` 解析、help 文本、与 `--debug` 组合、与 `--quiet` 组合的 runtime 优先级 | `tests/cli/test_arg_parsing.py` |
| CLI main 装配 | 初始配置与 cleanup 配置均传递正确 `debug_stream`，日志文件路径正确 | `tests/cli/test_arg_parsing.py` |
| CLI prompt/interactive 兼容 | unsupported option 守卫、stdout 洁净 | `tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py` |
| Host ingest gating | delta 使用 `STREAM_DEBUG_LOG_LEVEL`，non-delta 保持 `VERBOSE_LOG_LEVEL`；DEBUG 抑制 delta ingest 日志 | `tests/host/test_logging.py` |
| Runner stream gating | DEBUG 抑制 heartbeat/done-token；STREAM_DEBUG 发射 | `tests/engine/runners/openai/test_runner_diagnostics.py` |

pyright: `dayu/ tests/ utils/` 0 errors, 0 warnings ✓

全量 affected 测试: 159 passed, 3 third-party edgar deprecation warnings ✓

残余风险（已识别且有 owner）：
- 未来新增 stream 诊断可能错误使用 DEBUG 而非 STREAM_DEBUG。缓解：现有测试按站点锁定期望级别，README 已定义级别区分语义；后续 review 应检查。
- `--debug-stream` 与 `--quiet` 等矛盾参数组合时静默选择 stream-debug。缓解：help 文本警告，README 说明。

#### 6. memory_repair.catch_up.budget_exhausted

确认：当前 `main` 与 `wu-cli-debug-stream-01` 均已移除 `MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED`。`_log_repair_result()` 只在 `result.failures > 0` 时 warning，成功 catch-up/rebuild 汇总走 `VERBOSE_LOG_LEVEL`。本分支不涉及 memory_repair 模块变更。**无回归证据，不构成 finding。**

#### 7. Pre-existing README `--log-level critical` mismatch

确认事实：
- `README.md` 表格行 `--log-level` 的说明文本包含 `critical`
- `dayu/cli/arg_parsing.py` 的 `LOG_LEVEL_CHOICES` 为 `("debug", "verbose", "info", "warn", "error")`，不含 `critical`
- 本次 diff 未修改 `LOG_LEVEL_CHOICES`
- 本次 diff 对 README 的修改仅新增 `--debug-stream` 相关内容，未修改既有 `--log-level` 行

**结论：确认为本 WU 外 pre-existing residual，本分支未加剧该问题。不构成 blocker。**

## Findings

未发现实质性问题。

### 非 Finding 说明

以下各项经逐代码路径审查，确认为设计意图内行为，不构成 finding：

1. **`--debug-stream` 与 `--quiet` 组合时静默选择 stream-debug**：`_resolve_level()` 在有 `debug_stream=True` 时第一优先返回 `STREAM_DEBUG`，不检查 `log_level`。plan 明确这是最高优先级设计，help 文本和 README 均警告不要组合矛盾参数。`test_parse_cli_args_debug_stream_and_quiet_runtime_precedence` 验证了此行为。不构成 correctness bug。

2. **`set_level_from_flags()` 的 `debug`/`verbose`/`info`/`quiet` 参数在 CLI 路径始终为 False**：argparse 通过 `store_const` 将这些 flag 归一化为 `log_level` 字符串。`set_level_from_flags()` 接口保留这些参数是为了非 CLI 调用方灵活性和接口稳定性；在当前 CLI 路径中它们是 dead parameters，但保留它们不造成 harm。不构成接口设计问题。

3. **`--debug-stream` 帮助文本较简略**：help 文本说明了用途和矛盾参数警告，README 有更详细说明。plan 明确不引入新的诊断框架或配置复杂度。不构成文档不足。

4. **`LogLevel.STREAM_DEBUG = 9` 低于 stdlib 预定义级别范围**：stdlib logging 的 `addLevelName()` 和 `setLevel()` 均接受任意正整数。数值 9 是有意选择：低于 DEBUG=10 确保普通 DEBUG 阈值抑制它，同时 STREAM_DEBUG=9 阈值下 DEBUG=10 仍可发射。已有测试 `test_log_level_stream_debug_registered_with_stdlib` 验证。不构成兼容性问题。

## Open Questions

无。

## Residual Risk

- **RR-1**：未来 Engine Runner 或 Host ingest 新增 stream 诊断时可能错误使用 `logging.DEBUG` 而非 `STREAM_DEBUG_LOG_LEVEL`。  
  缓解：现有测试按站点锁定期望级别（`test_engine_ingest_delta_events_use_stream_debug_log_level`、`test_stream_diagnostics_require_stream_debug_log_level`）；README 已定义 `--debug` vs `--debug-stream` 的语义区分；后续 review 应检查新增日志站点的级别选择。Owner: 后续 WU review gate。

- **RR-2**：Pre-existing `README.md` `--log-level critical` 与 `LOG_LEVEL_CHOICES` 不匹配。  
  状态：本 WU 外 pre-existing residual。Owner: 后续 CLI 文档/参数对齐 WU。本 WU 未加剧该问题。

## Conclusion

**PASS**

全 WU 满足 Issue #148 行为契约。`--debug` 不输出高频 per-delta stream 诊断；`--debug-stream` 显式启用普通 DEBUG 加 stream delta / SSE / per-delta ingest 诊断；`--debug-stream` 可与 `--debug` 组合且优先级正确。Runtime/CLI/Host/Engine 分层正确，无反向依赖，无 schema/state-machine/public Host/Engine contract 非预期变化。Host ingest delta、OpenAI stream idle heartbeat、SSE done-token 迁移完整，warnings/errors/lifecycle/HTTP DEBUG 未误降级。Prompt/interactive compatibility guard 与 README/tests README 准确、不过度承诺、不泄漏内部治理术语。测试矩阵充分，pyright 0 errors，159 测试通过。两个 residual risk 均有明确 owner。

验证命令结果：
- `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`: **159 passed**, 3 third-party warnings
- `python -m pyright dayu/ tests/ utils/`: **0 errors, 0 warnings**
