# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-debug-stream-01`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cli-debug-stream-01-slice4-mimo-20260620.md`
- Included scope:
  - `README.md`（unstaged diff）：CLI 共享参数表、`prompt` / `interactive` 参数摘要与示例
  - `tests/README.md`（unstaged diff）：CLI / runtime / Host / Engine logging 覆盖职责
  - `docs/host/issues-implementation-control.md`（unstaged diff）：总控状态推进
  - `docs/reviews/implementation-wu-cli-debug-stream-01-slice4-20260620.md`（untracked）：Slice 4 实现说明
- Excluded scope: 生产代码、测试代码、`dayu/host/README.md`、`dayu/engine/README.md`
- Parallel review coverage: 无

## Review Method

按 deepreview Current Changes Mode 执行：

1. 读取 diff intent：implementation artifact、plan Slice 4 scope、总控状态
2. 对齐 contracts：README `Agent更新约束`、tests/README `README更新边界`、plan design source alignment
3. 追踪 implementation paths：实际 CLI parser `--debug-stream` 注册、`STREAM_DEBUG_LOG_LEVEL = 9`、`_resolve_level()` 优先级、`_engine_ingest_log_level()` 分层、CLI main wiring
4. 验证 tests/README 声称与实际测试函数一一对应
5. 检查 README 触发规则是否遗漏

## Findings

未发现实质性问题。

逐项审查结果：

### 1. README.md 是否符合自身 Agent更新约束

**结论：符合。**

- 所有新增内容均属用户可见 CLI 行为：参数表新增 `--debug-stream` 行、说明段解释 `--debug` 与 `--debug-stream` 的用途差异、`--detail` 与诊断日志的分离关系、`prompt` / `interactive` 参数摘要补齐 `--debug-stream`、示例命令补齐用法。
- 未写入 Host / Engine 内部架构、公共契约、状态机、测试清单、work-unit 过程状态或内部治理术语。
- 未写入未落地能力或未来计划。
- implementation artifact 记录了已读取各 README 的 `Agent更新约束`。

### 2. `--debug` / `--debug-stream` / `--detail` / `--log-file` 关系是否准确

**结论：准确。**

代码证据链：

- `dayu/cli/arg_parsing.py:349-358`：`--debug-stream` 注册为 `action="store_true", dest="debug_stream"`
- `dayu/runtime/log_levels.py:14`：`STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1`（值为 9）
- `dayu/runtime/log.py:229-259`：`_resolve_level()` 中 `if debug_stream: return LogLevel.STREAM_DEBUG`，`debug_stream` 优先级最高
- `dayu/host/engine_ingest.py:206-212, 3256-3266`：`content_delta` / `reasoning_delta` / `tool_call_delta` 使用 `STREAM_DEBUG_LOG_LEVEL`，非 delta 骨架使用 `VERBOSE_LOG_LEVEL`

README 声称与代码一致：

| README 声称 | 代码验证 |
|---|---|
| `--debug-stream` 包含普通 `--debug` 诊断 | `STREAM_DEBUG(9) < DEBUG(10)`，logger 设为 level 9 时 level 10 的 DEBUG 记录也通过 |
| `--debug-stream` 额外输出 stream delta / SSE / 逐 delta ingest | `_engine_ingest_log_level()` 对 delta 类型返回 `STREAM_DEBUG_LOG_LEVEL`，Runner diagnostics 对 heartbeat / done-token 使用 stream-debug |
| `--detail` 是终端 activity stream，与诊断日志独立 | CLI main 中 activity 输出走 stdout/stderr watcher，诊断日志走 Python logging → `--log-file`，两者无交叉 |
| `--log-file` 只改变诊断日志位置 | CLI main 中 `log_stream` 只传给 `set_level_from_flags(stream=...)`，不改变 activity watcher 输出通道 |

### 3. tests/README.md 是否只记录已落地测试事实

**结论：是。**

diff 中三处修改均对应已存在的测试函数：

| tests/README.md 新增描述 | 对应实际测试 |
|---|---|
| CLI main 覆盖 `--debug-stream` 解析 | `test_arg_parsing.py:test_parse_cli_args_accepts_debug_stream`（line 1015）、`test_main_configures_runtime_log_from_parsed_cli_flags`（line 414，parametrized with `--debug-stream`） |
| `--debug-stream` 不进入旧 Agent 执行参数 | `test_interactive_command.py:test_interactive_debug_stream_is_not_unsupported_execution_option`（line 1359） |
| `--debug-stream` 诊断不污染 stdout | `test_prompt_command.py:test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout`（line 820，parametrized with `--debug-stream`）、`test_interactive_command.py:test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout`（line 816，parametrized with `--debug-stream`） |
| runtime logging 覆盖 stream-debug 级别与抑制行为 | `test_log.py:test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both`（line 430）、`test_log_levels.py:test_stream_debug_log_level_constant_is_below_debug`（line 48） |
| Host ingest delta 使用 stream-debug 级别 | `test_logging.py:test_engine_ingest_delta_events_use_stream_debug_log_level`（line 180）、`test_engine_ingest_delta_stream_debug_records_are_gated`（line 206） |
| Runner diagnostics stream-debug gating | `test_runner_diagnostics.py:test_stream_diagnostics_require_stream_debug_log_level`（line 288） |

tests/README.md 未写入用户手册、设计文档、未落地测试体系或时间敏感记录。符合 `README更新边界` 约束。

### 4. 未修改 dayu/host/README.md、dayu/engine/README.md 的理由

**结论：理由成立。**

- `dayu/host/README.md` `Agent更新约束`：只写 Host package 稳定开发接口、公共契约、架构、关键路径和机制。本次变更仅涉及 `engine_ingest.py` 中 delta 事件的日志级别重分类（`VERBOSE` → `STREAM_DEBUG`），不改变 Host public contract、状态机、EventLog 语义或 HostEvent 语义。
- `dayu/engine/README.md` `Agent更新约束`：只写 Engine package 稳定开发接口、公共契约、架构、事件流、Runner 机制和扩展点。本次变更不涉及 EngineEvent / RunnerEvent contract、RunnerSpec / RunnerCallOptions 字段或 Engine public API。
- plan Slice 4 scope 明确允许这两个文件"only if implementation introduces stable developer-facing package semantics that these README scopes require"，本次变更不满足该条件。

### 5. `memory_repair.catch_up.budget_exhausted` 处理

**结论：合理排除。**

总控 blocking open questions 记录："Plan gate explicitly excludes `memory_repair.catch_up.budget_exhausted` from implementation scope because current code has already removed that stop reason and preserves warning only for actual memory repair failures。"

代码证据：当前 `dayu/host/` 中已无 `budget_exhausted` stop reason，required catch-up / rebuild / projection failures 仍正常 warning。本 WU 只保留 no-regression verification，不将其作为待解决噪音处理。

### 6. 文档误导、过度承诺、过长难维护、术语错误或触发规则遗漏

**结论：无误导、无过度承诺、无术语错误。**

- README 使用用户可理解的描述（"stream delta"、"SSE 完成标记"、"逐 delta ingest"），与 CLI help 文本一致，不暴露内部实现术语。
- 控制文档术语与 design source 对齐：`EngineEvent stream`、`RunnerEvent stream`、`SSE stream`、`Host event stream` 四类 stream 术语在 plan 中已有明确区分。
- README 触发规则检查：本次变更涉及 `tests/` 修改（触发 `tests/README.md` 更新，已做）和用户可见 CLI 参数变化（触发根 `README.md` 更新，已做）。`docs/host/issues-implementation-control.md` 是总控文档变更，不命中任何 README 触发规则。未遗漏。

## Open Questions

- **既有 `--log-level` choices 不一致**：根 README 第 290 行 `--log-level` 描述列出 `critical` 作为可选值，但实际 CLI parser `LOG_LEVEL_CHOICES`（`dayu/cli/arg_parsing.py:17-23`）只包含 `debug`、`verbose`、`info`、`warn`、`error`，不含 `critical`。该不一致在 implementation artifact 中已标为"既有非本 WU 范围"，Slice 4 未扩大修复。不阻塞本次 review，但建议后续修正。

## Residual Risk

- Slice 4 只更新文档，不重新运行 pytest。前序 Slice 1-3 已由代码和测试覆盖 `--debug-stream` 全链路行为，本 Slice 按要求运行 `git diff --check` 与 `pyright`，无新增代码风险。
- 控制文档 `issues-implementation-control.md` 的状态推进（gate → code review、WU status → review）为过程记录，不影响代码行为。

## Conclusion

**PASS**。Slice 4 README / tests README 变更准确、完整、符合各文档自身约束，tests/README 声称与实际测试一一对应，未修改 Host / Engine README 的理由成立，`memory_repair.catch_up.budget_exhausted` 排除合理。唯一 open question 是既有 `--log-level` choices 不一致，非本 WU 范围。
