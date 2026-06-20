# Code Review: WU-CLI-DEBUG-STREAM-01 Slice 1

- **Reviewer**: AgentMiMo
- **Date**: 2026-06-20
- **Scope**: Runtime log level + CLI `--debug-stream` plumbing
- **Plan artifact**: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- **Implementation artifact**: `docs/reviews/implementation-wu-cli-debug-stream-01-slice1-20260620.md`

---

## Verdict: APPROVED

实现完全符合 plan Slice 1 的设计意图与预期断言，无阻塞性发现。

---

## Findings

### F1 — `--debug-stream` help 文本建议"不要与互相矛盾的日志等级参数组合使用"但未强制

- **Severity**: Nit
- **File**: `dayu/cli/arg_parsing.py:354-358`
- **Evidence**: help 文本写"不要与互相矛盾的日志等级参数组合使用"，但 parser 不做任何互斥约束；`_resolve_level()` 中 `debug_stream=True` 无条件优先于 `log_level`、`quiet` 等。因此 `--quiet --debug-stream` 实际结果是 STREAM_DEBUG（而非用户可能预期的 quiet + stream 双重效果），与 help 建议矛盾。
- **Assessment**: 行为正确（plan 明确要求 `debug_stream` 最高优先级），help 文本是"建议"而非"拒绝"，属于有意的 UX 选择。但 help 中"不要与互相矛盾的日志等级参数组合使用"这一措辞可能让用户困惑——如果组合是被接受且有确定行为的，help 应该描述行为而非建议避免。
- **Adjudication**: **deferred-with-owner** — 属于 CLI UX 措辞微调，不阻塞 Slice 1。可在 Slice 4 README 更新时一并审视 help 措辞是否改为描述确定行为（如"`--debug-stream` 优先于所有日志等级参数"）。

### F2 — `--debug-stream` 与 `--quiet` 组合时 `quiet` flag 被静默忽略

- **Severity**: Low
- **File**: `dayu/runtime/log.py:240-241`
- **Evidence**: `_resolve_level()` 在 `debug_stream=True` 时直接 `return LogLevel.STREAM_DEBUG`，跳过后续所有分支包括 `quiet`。用户传 `--quiet --debug-stream` 时 argparse 不拒绝，runtime 也不警告，结果是 STREAM_DEBUG 而非 quiet+stream。
- **Assessment**: 这是 plan 的明确设计决定（Implementation Decision #2: "`--debug-stream` is additive and strongest verbosity"）。行为正确，但缺少对冲突组合的显式诊断。Slice 1 scope 内不做互斥约束是合理的。
- **Adjudication**: **deferred-with-owner** — 可在 Slice 3 或后续迭代中考虑是否对明显冲突组合（quiet + debug_stream）输出 stderr 警告。

### F3 — `test_log_levels.py` 子进程测试同时验证了 STREAM_DEBUG 和 VERBOSE 的未注册行为

- **Severity**: Nit (positive)
- **File**: `tests/runtime/test_log_levels.py:67-79`
- **Evidence**: 子进程只导入 `log_levels` 模块，断言 `getLevelName(9)` 返回 `"Level 9"` 而非 `"STREAM_DEBUG"`，`getLevelName(15)` 返回 `"Level 15"` 而非 `"VERBOSE"`。这正确证明了纯常量模块不执行 stdlib 注册。
- **Assessment**: 测试设计正确且充分。子进程隔离确保了模块导入副作用的断言不被其他测试污染。
- **Adjudication**: **accepted**

### F4 — `main()` cleanup 路径在 `parse_cli_args` 失败时 `debug_stream_for_cleanup` 保持默认 `False`

- **Severity**: Nit
- **File**: `dayu/cli/main.py:83-88`
- **Evidence**: `debug_stream_for_cleanup = False` 在 `try` 外初始化；如果 `parse_cli_args(argv)` 抛出 `SystemExit`（如 `--help` 或用法错误），`debug_stream_for_cleanup` 保持 `False`，`log_level_for_cleanup` 保持 `None`。随后 `finally` 块调用 `set_level_from_flags(log_level=None, debug_stream=False, ...)` 解析为 INFO 并恢复 stderr。
- **Assessment**: 行为安全——`set_level_from_flags` 对 `log_level=None, debug_stream=False` 返回 INFO 是正确默认。`opened_log_stream` 此时为 `None`（解析失败时尚未打开文件），所以 cleanup 实际上无操作（`finally` 中 `opened_log_stream is not None` 为 `False`，不进入内层 `finally`）。这是正确的防御性编程。
- **Adjudication**: **accepted**

### F5 — `_LogAssemblyCall` dataclass 新增 `debug_stream` 字段位于 `log_level` 和 `verbose` 之间

- **Severity**: Nit
- **File**: `tests/cli/test_arg_parsing.py:97`
- **Evidence**: `_LogAssemblyCall` 字段顺序为 `log_level, debug, debug_stream, verbose, info, quiet, stream`。这与 `set_level_from_flags` 签名顺序 `log_level, debug, verbose, info, quiet, debug_stream, stream` 不一致。
- **Assessment**: dataclass 字段顺序不影响功能（比较使用 `==`），但与函数签名顺序不一致可能降低可读性。这是测试代码中的低影响不一致。
- **Adjudication**: **deferred-with-owner** — 极低优先级的代码风格一致性问题，可在后续维护中调整。

### F6 — `test_parse_cli_args_accepts_debug_and_debug_stream_combination` 验证了 argparse 层面的共存

- **Severity**: Nit (positive)
- **File**: `tests/cli/test_arg_parsing.py:1024-1031`
- **Evidence**: 测试传入 `("--debug", "--debug-stream")` 后断言 `debug_stream is True` 且 `log_level == "debug"`。这证明 argparse 层面两个 flag 可以共存，`--debug` 写入 `log_level`，`--debug-stream` 写入 `debug_stream`，不互相覆盖。
- **Assessment**: 测试正确覆盖了 plan 要求的组合场景。argparse 层面的解析与 runtime 层面的优先级（`_resolve_level` 中 `debug_stream` 最高）形成完整的两级验证。
- **Adjudication**: **accepted**

### F7 — `test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both` 使用 `sys.stdout` 作为测试 stream

- **Severity**: Nit
- **File**: `tests/runtime/test_log.py:416-435`
- **Evidence**: 测试使用 `configure(level=LogLevel.DEBUG, stream=sys.stdout)` 然后通过 `capsys` 捕获 `stdout`。这依赖 `configure` 将 handler 安装到 `sys.stdout` 后 `capsys` 能捕获到。
- **Assessment**: `capsys` 捕获 `sys.stdout` 和 `sys.stderr` 的替换机制是 pytest 标准行为，`StreamHandler(stream=sys.stdout)` 写入的内容会被 `capsys` 捕获。测试设计正确。
- **Adjudication**: **accepted**

---

## Review Focus Checklist

| Focus Area | Status | Evidence |
|---|---|---|
| STREAM_DEBUG_LOG_LEVEL 低于 DEBUG 且 stdlib 注册 | ✅ | `log_levels.py:15` 定义 `DEBUG - 1 = 9`；`log.py:75` 注册 `addLevelName(9, "STREAM_DEBUG")`；`test_log.py:217-222` 验证 `getLevelName(9) == "STREAM_DEBUG"` |
| `set_level_from_flags(debug_stream=True)` 优先于已解析 log_level | ✅ | `log.py:240-241` 在 `_resolve_level()` 中 `debug_stream` 检查先于 `log_level`；`test_log.py:141-152` 验证 `debug_stream=True` + `log_level="info"` → STREAM_DEBUG |
| CLI `--debug-stream` parser/default/help 行为 | ✅ | `arg_parsing.py:349-358` 注册 `store_true` 全局参数；`_new_default_namespace()` 设置 `debug_stream=False`；`test_arg_parsing.py:213-221, 246-255` 验证 help 包含 flag |
| `main()` cleanup 传播 `debug_stream` | ✅ | `main.py:83,88` 保存；`main.py:101,123` 两次 `set_level_from_flags` 均传入；`test_arg_parsing.py:412-509` spy 验证两次调用均包含 `debug_stream` |
| 测试证明 DEBUG 抑制 STREAM_DEBUG、STREAM_DEBUG 同时输出二者 | ✅ | `test_log.py:416-435` 配置 DEBUG 时 STREAM_DEBUG 记录被抑制、普通 DEBUG 可见；配置 STREAM_DEBUG 时两者均可见 |
| 无 Host/Engine stream 诊断迁移 | ✅ | diff 中无 `engine_ingest.py`、`runner.py`、`sse_parser.py` 变更 |
| 无 README 更新 | ✅ | diff 中无 README 文件变更 |
| 无 weak typing / Any / object / missing docstring 回归 | ✅ | 所有新增参数有类型标注；`set_level_from_flags` 新增 `debug_stream: bool = False` 有完整 docstring；`LogLevel.STREAM_DEBUG` 有 docstring 描述 |

---

## Residual Risks

1. **Host/Engine 迁移未开始（Slice 2）**: `STREAM_DEBUG_LOG_LEVEL` 已在 runtime 层定义并注册，但 `dayu/host/engine_ingest.py` 的 `_engine_ingest_log_level()` 和 OpenAI runner 的 stream heartbeat / SSE done-token 仍使用 `logging.DEBUG`。当前 `--debug-stream` 虽然能将 logger 阈值调到 STREAM_DEBUG，但 Host/Engine 还没有代码实际使用该 level 输出记录。这意味着 `--debug-stream` 在 Slice 1 完成后等价于 `--debug`（在实际输出层面），直到 Slice 2 完成后才真正有差异化输出。

2. **`LOG_LEVEL_CHOICES` 未包含 `stream_debug`**: `arg_parsing.py:17-23` 的 `LOG_LEVEL_CHOICES` 不包含 `"stream_debug"`，因此 `--log-level stream_debug` 会触发 argparse 用法错误。用户只能通过 `--debug-stream` flag 进入 STREAM_DEBUG 级别。这是有意设计（`--debug-stream` 是独立 flag，不是 log-level 枚举值），但与 `--log-level` 的覆盖范围形成不对称。

3. **Plan 提及的 `critical` 不在 `LOG_LEVEL_CHOICES` 中**: plan Risks 节指出 root README 提到 `critical` 但 parser choices 不包含它。这是 pre-existing 问题，不在本 Slice scope 内，但 Slice 4 README 更新时需注意不要强化这个不一致。

---

## Uncovered Areas (Out of Slice 1 Scope)

- `unsupported_execution_option_names()` 未显式验证排除 `--debug-stream`（Slice 3）。
- `tests/cli/test_prompt_command.py` / `test_interactive_command.py` 中手动构造 `ParsedCliArgs` 的 helper 未检查是否需要新增 `debug_stream` 字段（Slice 3）。
- Host/Engine 高频诊断 level 迁移（Slice 2）。
- README 用户文档（Slice 4）。
