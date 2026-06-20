# Plan Review: WU-CLI-DEBUG-STREAM-01

- **Reviewer**: MiMo (plan review agent)
- **Date**: 2026-06-20
- **Plan artifact**: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Issue**: [#148](https://github.com/noho/dayu-agent-r/issues/148)
- **Current gate**: plan review

---

## Overall Verdict

**PASS_WITH_FINDINGS**

Plan 可进入 code generation gate，但有 2 个 accepted finding 需要在实现前裁决或在实现中处理。

---

## Findings

### F-1: `--debug-stream` 与显式 quiet flag 冲突时优先级未明确

**严重性**: medium
**类型**: design consistency
**文件证据**: `dayu/runtime/log.py:218-245`（`_resolve_level` 当前优先级）、plan "Implementation Decisions §2"

**Plan 声明**:
- §2："`--debug-stream` wins because it explicitly requests the most verbose diagnostic mode"
- Risks："`--debug-stream` combined with quieter log-level flags is inherently conflicting. Planned behavior is that `--debug-stream` wins"

**代码事实**:
当前 `_resolve_level` 优先级为 `log_level str > quiet > debug > verbose > info`。Plan 说 `set_level_from_flags()` 应 "resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` before ordinary `log_level` strings"，但同时 Risks 段说 "CLI help should avoid implying it is a narrow additive filter over an otherwise quiet threshold"。

**问题**:
如果用户显式传递 `--log-level critical --debug-stream` 或 `--quiet --debug-stream`，按 plan 说的 "before ordinary log_level strings" 语义，结果会是 `STREAM_DEBUG`（level 9），覆盖了用户明确要求的 quiet 行为。这违反了当前 CLI 参数设计的直觉：显式 `--log-level` 应最高优先级。

**建议**:
实现时应让 `debug_stream` 在 `_resolve_level` 中的优先级低于显式 `log_level` 字符串和 `quiet`，但高于 `debug`。即：
1. `log_level` 显式字符串（最高）
2. `quiet`
3. `debug_stream` → `STREAM_DEBUG`
4. `debug`
5. `verbose`
6. `info`
7. 默认 `INFO`

这样 `--quiet --debug-stream` → ERROR（quiet 胜），`--debug-stream` 单独 → STREAM_DEBUG，`--debug --debug-stream` → STREAM_DEBUG（debug_stream 胜过 debug）。CLI help 应注明 `--debug-stream` 胜过 `--debug` / `--verbose` / `--info`，但不胜过 `--quiet` 或显式 `--log-level`。

---

### F-2: `--debug-stream` cleanup 路径缺少测试断言

**严重性**: low
**类型**: test coverage gap
**文件证据**: `dayu/cli/main.py:86,96-103,117-124`（两处 `set_level_from_flags` 调用）、`tests/cli/test_arg_parsing.py:92-101`（`_LogAssemblyCall` spy 结构）

**Plan 声明**:
Slice 1 说 "In `cli/main.py`, preserve `debug_stream_for_cleanup` and pass it into both `set_level_from_flags()` calls"。

**代码事实**:
`main()` 在 try 块中调用 `set_level_from_flags`（line 96），在 finally 块中再次调用（line 117）用于 cleanup。当前 cleanup 调用没有传入 `debug_stream` 参数。Plan 要求两处都传入 `debug_stream`，但没有明确列出 cleanup 路径的测试断言。

**问题**:
`_LogAssemblyCall` spy 结构（test_arg_parsing.py:92-101）需要新增 `debug_stream: bool` 字段，且应有断言验证 cleanup 调用也携带正确的 `debug_stream` 值。Plan Slice 1 的 "Expected assertions" 只列了 parse 和初始配置断言，遗漏了 cleanup 路径。

**建议**:
在 Slice 1 实现时，补充 cleanup 路径的 spy 断言：
- `main(("prompt", "x", "--debug-stream"))` 的 cleanup `set_level_from_flags` 调用应携带 `debug_stream=True`。

---

## Verified Plan Claims

以下 plan 声明经代码验证均成立：

### V-1: `--debug-stream` 不会成为 unsupported execution option

**证据**: `--debug-stream` 注册在 global parent parser（plan Slice 1），而 `unsupported_execution_option_names()`（`dayu/cli/agent_entrypoint.py:232-265`）只检查 `_add_agent_execution_arguments()` 注册的 Agent 执行参数（`--debug-sse`、`--debug-tool-delta` 等）。`--debug-stream` 是全局日志开关，不在 Agent 执行参数面，不会被拦截。

### V-2: 旧 `--debug-sse` / `--debug-tool-delta` 保持 unsupported

**证据**: `unsupported_execution_option_names()`（`agent_entrypoint.py:245-248`）显式检查 `args.debug_sse` 和 `args.debug_tool_delta`，并在 prompt/interactive 命令入口抛出 `CliCommandUsageError`。Plan 正确保留这些旧字段为 unsupported execution option。

### V-3: `_engine_ingest_log_level` 对 delta 事件返回 `logging.DEBUG` 是根因

**证据**: `engine_ingest.py:3256-3265` 的 `_engine_ingest_log_level` 对 `_DELTA_ENGINE_EVENT_TYPES`（`CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`，定义在 line 206-212）返回 `logging.DEBUG`。`_ingest_before_reactive_compaction`（line 700-713）和 `_finish_ingest`（line 758-777）使用该 level 输出 `host.engine_ingest.accepted` / `host.engine_ingest.committed`。`tests/host/test_logging.py:187-188` 锁定了旧行为。

### V-4: `runner.stream_idle.heartbeat` 是 stream 诊断，应迁移到 STREAM_DEBUG

**证据**: `runner.py:897-902` 使用 `_LOGGER.debug("runner.stream_idle.heartbeat ...")`。同文件的 `runner.attempt.start`（line 373）、`runner.http.post`（line 581）、`runner.http.response`（line 607）是普通生命周期诊断，应保持 DEBUG。迁移 heartbeat 到 STREAM_DEBUG 符合语义。

### V-5: `sse.done_token received` 是 SSE 协议诊断，应迁移到 STREAM_DEBUG

**证据**: `sse_parser.py:346` 使用 `_LOGGER.debug("sse.done_token received")`。这是唯一的 DEBUG 调用；其余均为 WARNING（协议错误）。迁移 done-token 到 STREAM_DEBUG 合理。

### V-6: `memory_repair.catch_up.budget_exhausted` 已不是当前代码事实

**证据**: `tests/host/test_logging.py:163-177` 验证 memory catch-up 路径只输出 `stop_reason=idle`。Plan 正确指出当前 `MemoryProjectionRepairStopReason` 只有 `IDLE` / `TARGET_REACHED` / `FAILURE`，且 `_log_repair_result()` 只在 `result.failures > 0` 时 warning。

### V-7: Plan 不改变 Host / Engine event contract

**证据**: Plan 所有变更只涉及 Python logging level 常量和 CLI 参数，不修改 `EngineEvent`、`EngineEventType`、`EventLog` schema、`RunRow`/`AttemptRow` 状态机或 `AgentRunRequest` 字段。

### V-8: `VERBOSE=15` 自定义 level 先例成立

**证据**: `dayu/runtime/log_levels.py:15` 定义 `VERBOSE_LOG_LEVEL: Final[int] = 15`，`dayu/runtime/log.py:73` 注册 `logging.addLevelName(VERBOSE_LOG_LEVEL, "VERBOSE")`。新增 `STREAM_DEBUG=9` 遵循同一模式。

### V-9: Plan 正确识别 pre-existing `critical` 文档/parser 不匹配

**证据**: `LOG_LEVEL_CHOICES`（`arg_parsing.py:17-23`）不含 `"critical"`，但 README.md line 290 列出 `critical` 为 `--log-level` 选项。`LogLevel` 枚举（`log.py:96`）包含 `CRITICAL`。Plan 正确将此标记为 pre-existing 问题，不在本 WU 范围。

### V-10: 设计源对齐成立

**证据**: `docs/host/design.md` 确认 `UI -> Service -> Host -> Engine` 分层。CLI 属于 UI/composition entry。Plan 只在 CLI 参数和 `dayu.runtime.log` 装配层操作，不把 CLI flag 传入 Host/Engine request contract。`docs/engine/design.md` §1.1 的四类 stream 术语边界被 plan 正确引用且不越界。

---

## Residual Risks

1. **未来 stream 诊断被错误添加到普通 DEBUG**: Plan 正确识别此风险并通过测试和 README 定义缓解。建议在 `dayu/runtime/log_levels.py` 的 `STREAM_DEBUG_LOG_LEVEL` docstring 中注明使用场景。

2. **OpenAI runner 测试覆盖**: 当前 `test_runner_diagnostics.py` 只测试非流式场景。Plan Slice 2 要求 "Stream heartbeat / SSE done-token only appear when caplog/logger threshold is set to `STREAM_DEBUG_LOG_LEVEL`"，可能需要 streaming mock 基础设施。Plan 应在实现时评估是否需要新增 streaming 测试 fixture。

3. **`LOG_LEVEL_CHOICES` 不含 `critical`**: Pre-existing 问题。若实现 Slice 4 更新 README 时触及 `--log-level` 说明，应避免扩大不匹配范围。

---

## Conclusion

Plan 设计合理，动机成立，代码证据充分，不越层界。两个 finding 均不阻塞 code generation，但 F-1（优先级冲突）应在实现前裁决具体优先级规则，避免实现后返工。
