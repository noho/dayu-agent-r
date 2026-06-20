# PR Review — WU-CLI-DEBUG-STREAM-01 (AgentDS)

## Scope

- Mode: PR review
- Repository: noho/dayu-agent-r
- PR: #158 https://github.com/noho/dayu-agent-r/pull/158
- Title: WU-CLI-DEBUG-STREAM-01 debug stream diagnostics
- Author: noho
- Head branch: wu-cli-debug-stream-01
- Base branch: main
- Output file: docs/reviews/pr-review-wu-cli-debug-stream-01-ds-20260620.md
- Included scope: full PR diff (8 production files, 8 test files, 3 doc files, 19 review artifacts)
- Excluded scope: 无（全量 PR 审查）
- Parallel review coverage: 无（AgentDS 单路独立 PR review）
- Design truth sources: docs/host/design.md, docs/engine/design.md
- Control doc: docs/host/issues-implementation-control.md
- Issue: #148 https://github.com/noho/dayu-agent-r/issues/148

## Review Execution Summary

### 1. Issue #148 行为契约核查

逐条核对 Issue #148 五项验收标准：

| 验收标准 | 结论 | 直接证据 |
|---|---|---|
| 1. `--debug` 不再默认输出大量逐 delta ingest 日志 | ✅ 通过 | `_engine_ingest_log_level()` 对 delta 返回 `STREAM_DEBUG_LOG_LEVEL`(9)，低于 `logging.DEBUG`(10)，普通 DEBUG handler 不发射。`tests/host/test_logging.py:206-234` `test_engine_ingest_delta_stream_debug_records_are_gated` 直接验证。 |
| 2. `--debug-stream` 可以输出逐 stream delta / ingest 诊断 | ✅ 通过 | `_resolve_level(debug_stream=True)` → `LogLevel.STREAM_DEBUG`(9)，低于 `DEBUG`(10)，同时发射 STREAM_DEBUG 与 DEBUG 记录。`tests/runtime/test_log.py:169-180` 验证。 |
| 3. `--debug-stream` 可与 `--debug` 组合；单独使用时行为在 CLI help 中明确 | ✅ 通过 | `_resolve_level` 最前面检查 `debug_stream`，返回 `LogLevel.STREAM_DEBUG`。help 文本说明"启用普通 DEBUG 以及高频 stream delta、SSE、逐 delta ingest 诊断"。 |
| 4. README / CLI help 说明 `--debug` 与 `--debug-stream` 的区别 | ✅ 通过 | README.md:304-305 说明 `--debug` 适用场景（Host 打开、命令提交、调度、Runner HTTP 请求和终态收口）与 `--debug-stream` 适用场景（stream delta、stream idle heartbeat、SSE 完成标记和 Host 逐 delta ingest 诊断）。 |
| 5. 覆盖 CLI 参数解析与日志开关行为测试 | ✅ 通过 | 7 个测试文件覆盖：`tests/runtime/test_log_levels.py`（常量定义）、`tests/runtime/test_log.py`（注册与优先级）、`tests/cli/test_arg_parsing.py`（参数解析）、`tests/cli/test_prompt_command.py` / `tests/cli/test_interactive_command.py`（兼容性守卫）、`tests/host/test_logging.py`（Host ingest gating）、`tests/engine/runners/openai/test_runner_diagnostics.py`（Runner stream gating）。 |

### 2. `--debug-stream` 与 `--debug`/`--quiet`/`--log-level` 优先级核查

逐路径走读 `_resolve_level()`（`dayu/runtime/log.py:229-259`）：

| 输入组合 | 代码路径 | 最终级别 | 预期 |
|---|---|---|---|
| `debug_stream=True` 单独 | Line 240-241 → `LogLevel.STREAM_DEBUG` | STREAM_DEBUG (9) | ✅ |
| `debug_stream=True, log_level="debug"` (--debug-stream --debug) | Line 240-241 → `LogLevel.STREAM_DEBUG`（先于 log_level 检查） | STREAM_DEBUG (9) | ✅ |
| `debug_stream=True, log_level="error"` (--debug-stream --quiet) | Line 240-241 → `LogLevel.STREAM_DEBUG`（先于 log_level 检查） | STREAM_DEBUG (9) | ✅ |
| `log_level="debug"` (--debug) | Line 242-250 → `LogLevel["DEBUG"]` | DEBUG (10) | ✅ |
| `log_level="error"` (--quiet) | Line 242-250 → `LogLevel["ERROR"]` | ERROR (40) | ✅ |
| 无参数 | Line 259 → `LogLevel.INFO` | INFO (20) | ✅ |

优先级链 `debug_stream > log_level > quiet > debug > verbose > info > 默认 INFO` 在实现中严格保持。`test_parse_cli_args_debug_stream_and_quiet_runtime_precedence`（`tests/cli/test_arg_parsing.py:1033-1048`）直接验证 argparse 层与 runtime 层之间的优先级传导。

### 3. Stream 诊断迁移完整性

逐站点核对旧级别 → 新级别迁移：

| 日志站点 | 文件 | 旧级别 | 新级别 | 状态 |
|---|---|---|---|---|
| Host ingest delta (accepted/committed) | `dayu/host/engine_ingest.py:3264-3265` | `logging.DEBUG` | `STREAM_DEBUG_LOG_LEVEL` | ✅ |
| Host ingest non-delta | `dayu/host/engine_ingest.py:3266` | `VERBOSE_LOG_LEVEL` | `VERBOSE_LOG_LEVEL` | ✅ 不变 |
| OpenAI runner `stream_idle.heartbeat` | `dayu/engine/runners/openai/runner.py:897-903` | `_LOGGER.debug(...)` | `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)` | ✅ |
| OpenAI SSE `sse.done_token received` | `dayu/engine/runners/openai/sse_parser.py:347-351` | `_LOGGER.debug(...)` | `_LOGGER.log(STREAM_DEBUG_LOG_LEVEL, ...)` | ✅ |
| OpenAI runner `attempt.start` / `http.post` / `http.response` | `dayu/engine/runners/openai/runner.py` | `logging.DEBUG` | `logging.DEBUG` | ✅ 不变 |
| Protocol warnings/errors | 上述各文件 | `WARNING`/`ERROR` | `WARNING`/`ERROR` | ✅ 不变 |

未发现任何 warning/error/lifecycle/HTTP DEBUG 被误降级。`test_stream_diagnostics_require_stream_debug_log_level`（`tests/engine/runners/openai/test_runner_diagnostics.py:288-328`）在单测试内完整验证 DEBUG 级别抑制 heartbeat/done-token 而 STREAM_DEBUG 级别放出。

### 4. 用户 Follow-Up 核查

| 检查项 | 结论 | 证据 |
|---|---|---|
| `--log-level critical` 已加入 argparse choices | ✅ 已修复 | `dayu/cli/arg_parsing.py:23` — `LOG_LEVEL_CHOICES` 包含 `"critical"` |
| `LogLevel.CRITICAL` 存在且可被 `_resolve_level()` 解析 | ✅ 对齐 | `dayu/runtime/log_levels.py:21` — `CRITICAL_LOG_LEVEL: Final[int] = logging.CRITICAL`；`dayu/runtime/log.py:102` — `CRITICAL = CRITICAL_LOG_LEVEL` |
| 未来站点 reminder residual 已删除 | ✅ 已清理 | `grep -rn "future.site\|future_site"` 对全部 8 个生产文件无匹配 |
| `tests/cli/test_arg_parsing.py` 覆盖 `--log-level critical` | ✅ 覆盖 | 160 passed 测试中包含 critical 级别解析路径 |

### 5. PR Body 准确性核查

| 声明 | 验证结果 |
|---|---|
| 160 passed | ✅ `pytest ... -q` → `160 passed, 3 warnings in 5.27s` |
| pyright 0 errors | ✅ `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations` |
| `git diff --check` clean | ✅ 当前工作区 clean（`git status` 确认） |
| Residual Risks: None | ⚠️ PR body 写 "None"，但 plan 与 aggregate reviews 识别 RR-1（未来新增 stream 诊断可能错误使用 DEBUG 而非 STREAM_DEBUG）。此 RR 属于 forward-looking process risk 而非 PR 引入的代码缺陷；不构成 PR body 实质性错误。 |

### 6. 分层边界核查

按 `docs/host/design.md` 第 2 节固定分层 `UI -> Service -> Host -> Engine` 与 `dayu.runtime` 层中立约束逐项检查：

| 检查项 | 结论 | 证据 |
|---|---|---|
| `dayu.runtime.log_levels` 不导入上层 | ✅ | 只 import `logging`, `typing.Final` |
| `dayu.runtime.log` 不导入上层 | ✅ | 只 import stdlib、`dayu.contracts.json_value`（公共契约）、`dayu.runtime.log_levels` |
| CLI → Runtime 正向依赖 | ✅ | `dayu/cli/main.py:43` import `dayu.runtime.log` |
| Host → Runtime 正向依赖 | ✅ | `dayu/host/engine_ingest.py:203` import `dayu.runtime.log_levels` |
| Engine → Runtime 正向依赖 | ✅ | `dayu/engine/runners/openai/runner.py:161` import `dayu.runtime.log_levels` |
| 无反向依赖 | ✅ | Runtime 层不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` |
| 无跨层穿透 | ✅ | CLI 不直接读取 Host/Engine 内部状态；Host/Engine 不读取 CLI 参数 |
| 无 schema/state-machine/public contract 非预期变更 | ✅ | 本 PR 只在 Runtime 层新增 `STREAM_DEBUG_LOG_LEVEL` 常量与 `LogLevel.STREAM_DEBUG` 枚举；Host/Engine 的 EventLog、Session/Run/Attempt 状态机、Event 契约均未变更 |

### 7. LLM-Facing 文本约束核查

按 CLAUDE.md 中 LLM-facing 文本约束逐项检查本 PR 引入的 LLM 可消费内容：

| 约束 | 检查结果 |
|---|---|
| 只写模型完成当前任务所需的动作/输入/输出/判断规则 | ✅ README 新增文本只描述用户可见行为（stream delta、SSE、ingest），不暴露内部实现术语 |
| 结构化输出自足说明 | ✅ 本 PR 不新增 LLM-facing structured output |
| 内部治理标识只在必要时暴露 | ✅ `sse_parser.py` 新增 `provider_request_id` 只在日志中出现，不在 LLM prompt 中暴露 |
| 不把系统状态伪装成业务事实 | ✅ 本 PR 只改日志级别，不进入 prompt/memory/evidence |
| 不让模型依赖隐式规则 | ✅ 本 PR 不改 prompt/tool schema |
| tool schema 提供业务可读语义 | ✅ 本 PR 不改 tool schema |

### 8. README 触发规则核查

按 CLAUDE.md README 更新触发规则逐项核对：

| 触发条件 | 是否命中 | 实际动作 |
|---|---|---|
| `dayu/engine/` 修改 | ✅ 命中 | `dayu/engine/README.md` — 复查确认无需更新（Runner 公开契约和 Engine 开发者可见语义未变） |
| `dayu/host/` 修改 | ✅ 命中 | `dayu/host/README.md` — 复查确认无需更新（Host 公开契约和状态机语义未变） |
| `dayu/runtime/` 修改 | ⚠️ CLAUDE.md 无 explicit trigger for runtime | `dayu/runtime/log.py` 与 `dayu/runtime/log_levels.py` 修改属 Runtime 层，无对应 README 触发规则，不构成缺失 |
| CLI 入口/参数/用户可见行为变化 | ✅ 命中 | 根 `README.md` 已更新 ✅ |
| `tests/` 修改 | ✅ 命中 | `tests/README.md` 已更新 ✅ |
| 分层关系/装配方式变化 | 未命中 | 本 PR 不改变分层边界 |

### 9. memory_repair.catch_up.budget_exhausted 核查

确认：当前 `main` 与 `wu-cli-debug-stream-01` 的 `dayu/host/memory_repair.py` 中 `MemoryProjectionRepairStopReason` 只有 `IDLE` / `TARGET_REACHED` / `FAILURE`，无 `BUDGET_EXHAUSTED`。`_log_repair_result()` 只在 `result.failures > 0` 时 warning。本 PR 未修改 memory_repair 模块。**无回归证据，不构成 finding。**

### 10. 测试矩阵核查

| 测试面 | 覆盖情况 | 关键测试文件 | 预期覆盖 |
|---|---|---|---|
| Runtime 常量定义 | `STREAM_DEBUG_LOG_LEVEL == 9 < 10`，隔离导入无副作用 | `tests/runtime/test_log_levels.py` | ✅ |
| Runtime 级别注册 | `logging.getLevelName(9) == "STREAM_DEBUG"` | `tests/runtime/test_log.py` | ✅ |
| Runtime 优先级解析 | `debug_stream > log_level > quiet > debug > verbose > info > default` | `tests/runtime/test_log.py` | ✅ |
| DEBUG 抑制 STREAM_DEBUG | `caplog.at_level(DEBUG)` 不捕获 STREAM_DEBUG 记录 | `tests/runtime/test_log.py` | ✅ |
| STREAM_DEBUG 同时发射二者 | `caplog.at_level(STREAM_DEBUG)` 同时捕获 DEBUG 和 STREAM_DEBUG | `tests/runtime/test_log.py` | ✅ |
| CLI 解析 | `--debug-stream` 解析、help 文本、与 `--debug`/`--quiet` 组合 | `tests/cli/test_arg_parsing.py` | ✅ |
| CLI main 装配 | 初始与 cleanup 配置传递正确 | `tests/cli/test_arg_parsing.py` | ✅ |
| CLI prompt/interactive 兼容 | unsupported option 守卫、stdout 洁净 | `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py` | ✅ |
| Host ingest delta gating | delta → STREAM_DEBUG，non-delta → VERBOSE | `tests/host/test_logging.py` | ✅ |
| Host ingest DEBUG 抑制 | `caplog.at_level(DEBUG)` 不捕获 delta ingest | `tests/host/test_logging.py` | ✅ |
| Runner stream heartbeat gating | DEBUG 抑制 heartbeat；STREAM_DEBUG 放出 | `tests/engine/runners/openai/test_runner_diagnostics.py` | ✅ |
| Runner SSE done-token gating | DEBUG 抑制 done-token；STREAM_DEBUG 放出 | `tests/engine/runners/openai/test_runner_diagnostics.py` | ✅ |

未发现测试覆盖缺口。每个关键行为变更均有直接测试断言。

---

## Findings

未发现实质性问题。

### 非 Finding 说明

以下各项经逐代码路径审查，确认为设计意图内行为，不构成 finding：

1. **`--debug-stream` 与 `--quiet` 组合时静默选择 stream-debug**：`_resolve_level()` 在有 `debug_stream=True` 时第一优先返回 `STREAM_DEBUG`，不检查 `log_level`。plan 明确这是最高优先级设计，`test_parse_cli_args_debug_stream_and_quiet_runtime_precedence` 验证此行为，help 文本和 README 均警告不要组合矛盾参数。不构成 correctness bug。

2. **`set_level_from_flags()` 的 `debug`/`verbose`/`info`/`quiet` 参数在 CLI 路径始终为 `False`**：argparse 通过 `store_const` 将这些 flag 归一化为 `log_level` 字符串。`set_level_from_flags()` 接口保留这些参数是为非 CLI 调用方提供灵活性；在当前 CLI 路径中它们是 dead parameters，但不造成 harm。不构成接口设计问题。

3. **`--debug-stream` help 文本偏保守**：help 文本说"不要与互相矛盾的日志等级参数组合使用"，但实现上 `--debug-stream` 有最高优先级且可与任何组合安全使用。plan 和 README 有更详细说明，help 文本的保守措辞不会误导用户。不构成文档不足。

4. **`LogLevel.STREAM_DEBUG = 9` 低于 stdlib 预定义级别范围**：stdlib logging 的 `addLevelName()` 和 `setLevel()` 均接受任意正整数。数值 9 有意选择：低于 DEBUG=10 确保普通 DEBUG 阈值抑制它，同时 STREAM_DEBUG=9 阈值下 DEBUG=10 仍可发射。已有测试 `test_log_level_stream_debug_registered_with_stdlib` 验证。不构成兼容性问题。

5. **`_engine_ingest_log_level()` 非 delta 事件使用 `VERBOSE_LOG_LEVEL`（15）**：在 `--debug`（10）下这些日志不发射。这是 pre-existing 行为，plan 明确确认不改变非 delta ingest 日志级别。Host lifecycle 诊断（`host.command.accepted`、runner HTTP 等）在不同模块、不同 logger 使用不同级别，不属于 `_engine_ingest_log_level()` 范围。不构成遗漏。

6. **SSE done-token 日志新增 `provider_request_id`**：`sse_parser.py:348-349` 在 done-token 日志中追加 `provider_request_id=%s`。该字段从 HTTP response header `x-request-id` 提取，为 `None` 时 `%s` 格式化输出 `None`，不会崩溃。该 ID 是 provider 侧的请求关联标识，不暴露 API key 或业务内容。`tests/engine/runners/openai/test_runner_diagnostics.py:324` 直接断言 `"sse.done_token received provider_request_id=req-stream-1"`。不构成信息泄漏或格式错误。

---

## Open Questions

无。

## Residual Risk

- **RR-1**：未来 Engine Runner 或 Host ingest 新增 stream 诊断时可能错误使用 `logging.DEBUG` 而非 `STREAM_DEBUG_LOG_LEVEL`。  
  缓解：现有测试按站点锁定期望级别；README 已定义 `--debug` vs `--debug-stream` 语义区分；后续 review gate 应检查新增日志站点的级别选择。Owner: 后续 WU review gate。

- **RR-2**：`--log-level stream_debug` 在 argparse 层不被接受（不在 `LOG_LEVEL_CHOICES` 中），但 `_resolve_level()` 的字符串路径通过 `LogLevel[normalized]` 可解析 `STREAM_DEBUG`。用户只能通过 `--debug-stream` 启用 stream debug。  
  状态：设计意图（`--debug-stream` 是唯一入口）。若未来需要在 `--log-level` 中支持，需显式更新 `LOG_LEVEL_CHOICES` 并评估与 `--debug-stream` flag 的交互。Owner: 后续 WU（如需要）。

---

## Conclusion

**PASS**

PR #158 完整满足 Issue #148 全部行为契约与验收标准。普通 `--debug` 不输出高频 per-delta stream 诊断；`--debug-stream` 显式启用普通 DEBUG 加 stream delta / SSE / per-delta ingest 诊断；`--debug-stream` 与 `--debug`/`--quiet`/`--log-level` 优先级正确。用户 follow-up（`--log-level critical`、删除未来站点残留）均已正确处理。

Runtime/CLI/Host/Engine 分层正确，无反向依赖，无 schema/state-machine/public contract 非预期变化。Host ingest delta、OpenAI stream idle heartbeat、SSE done-token 迁移完整；warnings/errors/lifecycle/HTTP DEBUG 无一误降级。Prompt/interactive compatibility guard 与 README/tests README 准确、不过度承诺、不泄漏内部治理术语。测试矩阵充分（160 passed），pyright 0 errors。

无 must-fix findings。
