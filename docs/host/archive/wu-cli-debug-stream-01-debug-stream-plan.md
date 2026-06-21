# WU-CLI-DEBUG-STREAM-01 `--debug-stream` Plan

## Goal / Motivation / Success Signal

本 work unit 为 Dayu CLI 增加显式 `--debug-stream` 诊断开关，使逐 `content_delta` / `reasoning_delta` / `tool_call_delta`、SSE / stream 协议心跳、Host ingest per-delta accepted / committed 等高频诊断只在用户明确打开时输出。

动机成立。Issue #148 的问题不是日志文件位置或 activity stream UI 问题，而是当前 `--debug` 会把 `dayu` namespace logger 调到 stdlib `DEBUG`，而 Host ingest 对 transient delta 使用 `DEBUG` 记录 accepted / committed，导致普通 DEBUG 诊断被逐 delta 日志淹没。

成功信号：

- `dayu-cli prompt "..." --debug --log-file <path>` 保留 Host open / command / admission / dispatch / runner HTTP / terminal closeout / warning / error 等常规诊断，但不输出逐 delta `host.engine_ingest.accepted` / `host.engine_ingest.committed`。
- `dayu-cli prompt "..." --debug-stream --log-file <path>` 单独使用时输出普通 DEBUG 诊断以及 stream-only 诊断。
- `--debug-stream` 可与 `--debug` 同时出现；组合结果等价于 stream-debug 最细粒度诊断。
- CLI help 与 README 说明 `--debug` 和 `--debug-stream` 的差异。
- CLI parsing、runtime logging switch、Host ingest delta log level、OpenAI stream/SSE diagnostic gating 均有测试覆盖。

## Non-Goals / Scope Boundary

- 不改变 Host / Engine event contract，不新增 EngineEvent、HostEvent、EventLog event type、payload schema 或 state transition。
- 不改变 activity stream 用户可见行为；activity stream 仍由 CLI UI / Service / Host event stream 路径决定，不进入 Python logging。
- 不重构整个 CLI logging subsystem，不引入 logger registry、动态业务策略、per-module 配置文件或新诊断框架。
- 不把 final answer、业务正文、大段 LLM content 或 tool payload value 新增复制进 debug 日志。
- 不修复 `memory_repair.catch_up.budget_exhausted`。当前代码已经没有该 stop reason；本 WU 只把它作为不回归核对项。
- 不改变旧 `--debug-sse` / `--debug-tool-delta` 的 unsupported execution option 裁决；它们仍是 Agent 执行参数遗留入口，不承担本 WU 的全局日志装配语义。
- 不更新 `docs/host/issues-implementation-control.md`，由 phaseflow 总控在后续 gate 处理。

## Design Source Alignment

`docs/host/design.md` 固定 `UI -> Service -> Host -> Engine` 分层：CLI 属于 UI / composition entry，Host 负责 Run / Attempt / EventLog 治理，Engine 只产出单次 run 的 `EngineEvent stream`。因此本 WU 只能在 CLI 参数与 runtime logging 装配层控制诊断输出，不应把 CLI flag 传入 Host / Engine request contract，也不应让 Host / Engine 读取 UI 状态。

`docs/engine/design.md` 已区分四类 stream 术语：

- `EngineEvent stream`：Engine 对调用方的异步事件流。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流。
- `SSE stream` / provider streaming：Runner 与 provider 的传输能力。
- `Host event stream`：Host 从 EventLog cursor 派生的订阅 / 补读流。

本 WU 的 `--debug-stream` 只控制 Python logging 诊断中的 stream 细粒度记录，不改变上述任一 stream 的行为、数据契约、cursor、持久化或 UI 投影。

## First-Principles Judgment And Direct Code Evidence

从第一性原理看，普通 `--debug` 的价值是定位一次 CLI/Host/Engine 调用链中的异常路径；逐 delta ingest 的价值是定位 streaming、SSE、Engine delta 到 Host ingest 的细粒度丢失或乱序问题。两者频率和读者不同，混在同一个 DEBUG level 下会降低普通问题定位信噪比，所以需要更细粒度的日志开关。

直接代码证据：

- `dayu/cli/arg_parsing.py` 的全局参数已有 `--debug` / `--verbose` / `--info` / `--quiet`，它们通过写入 `log_level` 表达；`ParsedCliArgs` 还保留旧 `debug_sse` / `debug_tool_delta` 字段，且 `_add_agent_execution_arguments()` 只把旧参数挂在 `prompt` / `interactive` / `session resume` 的 Agent 执行参数面。
- `dayu/cli/main.py` 在解析后调用 `runtime_log.set_level_from_flags(log_level=args.log_level, debug=False, verbose=False, info=False, quiet=False, stream=log_stream)`，当前没有传入 stream-diagnostic 维度。
- `dayu/runtime/log.py` 只配置 `logging.getLogger("dayu")` namespace logger 和 marker handler，并支持 custom `VERBOSE=15`；默认 suppress 第三方 logger 到 WARNING，适合作为新增层中立 stream-debug level 的装配点。当前没有 filter 体系，也没有 record 分类。
- `dayu/host/engine_ingest.py` 中 `_DELTA_ENGINE_EVENT_TYPES` 包含 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`；`_engine_ingest_log_level()` 对这些 delta 返回 `logging.DEBUG`，`_ingest_before_reactive_compaction()` 与 `_finish_ingest()` 用该 level 输出 `host.engine_ingest.accepted` / `host.engine_ingest.committed`。这就是普通 `--debug` 输出 massive per-delta ingest 日志的直接根因。
- `dayu/host/engine_ingest.py` 的 `_ingest_validated()` 对 transient delta 返回 `_accepted_no_event_result()`，不会写 durable EventLog；本 WU 只改变诊断 level，不改变 transient delta 的 non-durable 语义。
- `dayu/engine/runners/openai/runner.py` 中 `runner.attempt.start`、`runner.http.post`、`runner.http.response` 是普通 DEBUG 诊断，应继续随 `--debug` 输出；`runner.stream_idle.heartbeat` 属于 stream idle 心跳诊断，应随 `--debug-stream` 输出。
- `dayu/engine/runners/openai/sse_parser.py` 中 `sse.done_token received` 是 SSE 协议诊断，可迁移到 stream-debug level；当前没有逐 SSE chunk 内容日志，不需要新增。
- `tests/host/test_logging.py` 当前断言 delta ingest 日志使用 `logging.DEBUG`，说明测试已锁定旧行为，需要随新 gating 更新。
- `dayu/host/memory_repair.py` 当前 `MemoryProjectionRepairStopReason` 只有 `IDLE` / `TARGET_REACHED` / `FAILURE`；`_log_repair_result()` 只有 `result.failures > 0` 时 warning，成功 catch-up / rebuild 汇总走 `VERBOSE_LOG_LEVEL`。因此 `budget_exhausted` warning 已不是当前代码事实，本 WU 不处理。
- GitHub Issue #148 明确要求 `--debug` 不再默认输出逐 reasoning/content delta ingest 日志，`--debug-stream` 显式打开逐 stream delta / ingest 诊断。

## Affected Files / Modules

Production code:

- `dayu/runtime/log_levels.py`
- `dayu/runtime/log.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `dayu/host/engine_ingest.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`

Tests:

- `tests/runtime/test_log.py`
- `tests/runtime/test_log_levels.py`
- `tests/cli/test_arg_parsing.py`
- `tests/host/test_logging.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`
- Relevant prompt / interactive tests only if `ParsedCliArgs` construction or unsupported execution option assertions require updates.

Docs:

- `README.md`
- `tests/README.md`
- `dayu/host/README.md` and `dayu/engine/README.md` only if implementation changes stable developer-facing logging semantics there. Expected decision: no update needed unless the implemented wording introduces package-level stable API beyond runtime logging constants.

## Contract / Schema / State-Machine / Public Interface Changes

- Public CLI interface changes: add global `--debug-stream`.
- Internal runtime logging interface changes: add a stream-diagnostic log level below stdlib DEBUG and teach `set_level_from_flags()` to resolve `debug_stream=True`.
- No durable schema changes.
- No Host / Engine event contract changes.
- No Host Run / Attempt / EventLog state-machine changes.
- No Service / Host / Engine request dataclass fields are added.

## Implementation Decisions

1. Use a dedicated log level instead of a logging filter.

   Add `STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1` in `dayu.runtime.log_levels`, register stdlib level name `STREAM_DEBUG` in `dayu.runtime.log`, and add `LogLevel.STREAM_DEBUG`. Because logging emits records whose numeric level is greater than or equal to the logger/handler threshold, normal `DEBUG=10` will not emit `STREAM_DEBUG=9`, while `STREAM_DEBUG=9` will emit both stream diagnostics and ordinary DEBUG / VERBOSE / INFO records.

   This is less brittle than a handler filter because it does not inspect log message text, dynamic `LogRecord` extra fields, module names, or event payloads. It also follows the existing runtime pattern that already defines `VERBOSE=15` as a Dayu custom level.

2. `--debug-stream` is additive and strongest verbosity.

   Add `ParsedCliArgs.debug_stream: bool` with default `False` and register `--debug-stream` on the global parent parser. `dayu/cli/main.py` passes `debug_stream=args.debug_stream` into `runtime_log.set_level_from_flags()` for initial configuration and cleanup reconfiguration.

   `set_level_from_flags()` must resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` before any parsed `log_level` value. This means `--debug-stream` is the explicit most-verbose diagnostic request once it reaches runtime logging, including when argparse has already resolved `--debug`, `--verbose`, `--info`, `--quiet`, or `--log-level <level>` into a `log_level` value. This makes single `--debug-stream` behavior explicit: it is equivalent to normal DEBUG plus stream-only diagnostics. If a user also supplies `--debug`, the effective result remains stream-debug.

   CLI help and README wording must describe the intended non-contradictory usage: `--debug-stream` enables ordinary DEBUG diagnostics plus high-frequency stream delta / SSE / per-delta ingest diagnostics. Users should not combine mutually contradictory log-level flags such as quiet/error-only requests with `--debug-stream`.

3. Keep ordinary DEBUG useful.

   Leave runner lifecycle and HTTP diagnostics at DEBUG:

   - `runner.attempt.start`
   - `runner.http.post`
   - `runner.http.response`
   - retry / terminal warnings and errors

   Move only stream-specific high-frequency diagnostics:

   - Host ingest delta accepted / committed via `_engine_ingest_log_level()` returning `STREAM_DEBUG_LOG_LEVEL` for `_DELTA_ENGINE_EVENT_TYPES`.
   - OpenAI runner stream idle heartbeat from DEBUG to `STREAM_DEBUG_LOG_LEVEL`.
   - OpenAI SSE done-token diagnostic from DEBUG to `STREAM_DEBUG_LOG_LEVEL`.

   Warnings for protocol errors, malformed usage, idle timeout, HTTP failures, and cleanup failures remain WARNING regardless of `--debug-stream`.

4. Do not revive old Agent execution flags.

   `--debug-sse` and `--debug-tool-delta` remain old unsupported execution options for prompt/interactive command request construction. `--debug-stream` is a global CLI logging switch and should not be added to `unsupported_execution_option_names()`.

5. Do not log content values.

   Host ingest accepted / committed logs already include ids, worker event index, event type, status and counts, not delta text. The implementation must preserve that shape. Engine/SSE changes must not add chunk text, content delta, reasoning delta, final answer, tool arguments, or raw response body to logs.

## Small Implementation Slices

### Slice 1: Runtime log level and CLI flag plumbing

Objective: make `--debug-stream` parse and configure a stream-debug threshold without touching Host / Engine call contracts.

Allowed files:

- `dayu/runtime/log_levels.py`
- `dayu/runtime/log.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `tests/runtime/test_log.py`
- `tests/runtime/test_log_levels.py`
- `tests/cli/test_arg_parsing.py`

Exact changes:

- Add `STREAM_DEBUG_LOG_LEVEL` to `log_levels.py` and `__all__`.
- Register `STREAM_DEBUG` level name in `runtime/log.py`.
- Add `LogLevel.STREAM_DEBUG`.
- Extend `set_level_from_flags()` signature with `debug_stream: bool = False`, document it, and resolve it to `LogLevel.STREAM_DEBUG` before `log_level`.
- Add `debug_stream: bool` to `ParsedCliArgs` and `_new_default_namespace()`.
- Add global `--debug-stream` help text. Help must say single use enables normal DEBUG plus stream delta / SSE diagnostics.
- In `cli/main.py`, preserve `debug_stream_for_cleanup` and pass it into both `set_level_from_flags()` calls.
- Update CLI main spy structures and expectations to include `debug_stream`.

Expected assertions:

- `parse_cli_args(("prompt", "x", "--debug-stream")).debug_stream is True`.
- `parse_cli_args(("prompt", "x", "--debug", "--debug-stream"))` accepts both flags, keeps `debug_stream is True`, and resolves the ordinary debug flag into the parsed log-level field.
- Global help and command help include `--debug-stream`.
- `main(("prompt", "x", "--debug-stream"))` passes `debug_stream=True` and `log_level="info"` to runtime log assembly for both the initial configuration call and the cleanup reconfiguration call.
- `set_level_from_flags(log_level="info", debug_stream=True, ...) is LogLevel.STREAM_DEBUG`.
- `set_level_from_flags(log_level="debug", debug_stream=True, ...) is LogLevel.STREAM_DEBUG`, covering combined `--debug` and `--debug-stream` runtime resolution.
- Configured `LogLevel.DEBUG` suppresses a `STREAM_DEBUG_LOG_LEVEL` record; configured `LogLevel.STREAM_DEBUG` emits it and also emits ordinary DEBUG.

### Slice 2: Host / Engine stream diagnostics level migration

Objective: move only stream-specific high-frequency logs below DEBUG.

Allowed files:

- `dayu/host/engine_ingest.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `tests/host/test_logging.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`

Exact changes:

- Import `STREAM_DEBUG_LOG_LEVEL` where needed.
- Change `_engine_ingest_log_level()` so delta event types return `STREAM_DEBUG_LOG_LEVEL`; non-delta remains `VERBOSE_LOG_LEVEL`.
- Change `runner.stream_idle.heartbeat` log call to `STREAM_DEBUG_LOG_LEVEL`.
- Change `sse.done_token received` log call to `STREAM_DEBUG_LOG_LEVEL`.
- Add / update tests proving ordinary DEBUG does not capture stream-debug records and stream-debug level does.
- Rename the old `tests/host/test_logging.py` test `test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name, for example `test_engine_ingest_delta_events_use_stream_debug_log_level`.
- Keep protocol warnings at WARNING and runner lifecycle DEBUG tests unchanged.

Expected assertions:

- `_engine_ingest_log_level(EngineEventType.CONTENT_DELTA) == STREAM_DEBUG_LOG_LEVEL`.
- `_engine_ingest_log_level(EngineEventType.REASONING_DELTA) == STREAM_DEBUG_LOG_LEVEL`.
- `_engine_ingest_log_level(EngineEventType.TOOL_CALL_DELTA) == STREAM_DEBUG_LOG_LEVEL`.
- `_engine_ingest_log_level(EngineEventType.ITERATION_STARTED) == VERBOSE_LOG_LEVEL`.
- Runner attempt / HTTP diagnostics still appear under DEBUG.
- Stream heartbeat / SSE done-token only appear when caplog/logger threshold is set to `STREAM_DEBUG_LOG_LEVEL`.

### Slice 3: Prompt / interactive compatibility tests and unsupported legacy option guard

Objective: ensure the new global flag does not become an unsupported Agent execution option and does not pollute stdout.

Allowed files:

- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- Other CLI tests only where construction helpers require `ParsedCliArgs.debug_stream`.

Exact changes:

- If tests manually instantiate `ParsedCliArgs`, add `debug_stream=False`.
- Add focused assertions only if current prompt / interactive tests route global flags through command runners; otherwise rely on `test_arg_parsing.py` to avoid unnecessary duplication.
- Keep existing unsupported old flags assertions for `--debug-sse`, `--debug-tool-delta`, `--debug-sse-sample-rate`, and `--debug-sse-throttle-sec`.

Expected assertions:

- `--debug-stream` is not listed by `unsupported_execution_option_names()`.
- Existing `--verbose` / `--debug` stdout cleanliness tests remain valid.

### Slice 4: README / tests README update

Objective: document user-visible CLI behavior and test coverage responsibilities.

Allowed files:

- `README.md`
- `tests/README.md`
- `dayu/host/README.md` / `dayu/engine/README.md` only if implementation introduces stable developer-facing package semantics that these README scopes require.

Exact changes:

- Read each target README's `Agent更新约束【必须遵守】` before editing.
- In root `README.md` CLI shared parameters, add `--debug-stream` and explain:
  - `--debug` is for ordinary diagnostics.
  - `--debug-stream` is for high-frequency stream delta / SSE / per-delta ingest diagnostics.
  - Single `--debug-stream` includes ordinary debug diagnostics.
  - Activity stream remains separate from diagnostic logs.
- In `tests/README.md`, update CLI/runtime/Host/Engine logging coverage summary.
- Do not document work-unit process state or internal event contracts in root README.

Expected decision:

- Root `README.md` must be updated because CLI public help / user-visible diagnostics changed.
- `tests/README.md` must be updated because test coverage description changes.
- `dayu/host/README.md` and `dayu/engine/README.md` likely do not need updates because Host / Engine public contracts and developer-facing event semantics do not change; plan review should re-check after implementation diff.

## Tests / Validation Commands

Plan gate validation:

```bash
git diff --check
```

Implementation gate required validation:

```bash
source .venv/bin/activate
pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q
python -m pyright dayu/ tests/ utils/
```

If prompt / interactive tests are touched:

```bash
source .venv/bin/activate
pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q
```

If README files are touched:

```bash
git diff --check README.md tests/README.md
```

Expected implementation assertions:

- No new pyright errors.
- Normal DEBUG no longer emits `STREAM_DEBUG_LOG_LEVEL` records.
- `--debug-stream` emits both ordinary DEBUG and stream-debug diagnostics.
- Host ingest non-delta logs remain VERBOSE.
- Memory repair success path remains VERBOSE and failure-only warning behavior remains unchanged.

## README / Docs Decision

Implementation must update `README.md` because a user-visible global CLI flag and diagnostics behavior change.

Implementation must update `tests/README.md` because CLI/runtime/Host/Engine logging coverage changes.

Implementation probably does not update `dayu/host/README.md` or `dayu/engine/README.md`: no Host / Engine public event contract, state machine, or package API changes are planned. If the implementation adds a stable public logging constant to developer-facing docs, re-check both README scopes before deciding.

No design source update is needed because the plan aligns with existing Host / Engine stream terminology and does not change architecture or contracts.

## Risks / Open Questions / Residual Risks

Blocking open questions: none found.

Residual risks:

- Some future stream diagnostics may still be added at ordinary DEBUG by mistake. Mitigation: tests should name the expected stream-only level for Host ingest and current OpenAI stream diagnostics, and README should define the distinction.
- `--debug-stream` combined with quieter log-level flags is inherently conflicting. Planned behavior is that `--debug-stream` wins once `debug_stream=True` reaches runtime logging because it explicitly requests the most verbose diagnostic mode. CLI help and README should state that `--debug-stream` enables ordinary DEBUG plus stream diagnostics, and users should not combine mutually contradictory log-level flags.
- Current OpenAI Runner has no per-byte or per-SSE-chunk content logger. This WU must not add one just to satisfy the flag; it only gates existing stream diagnostics and Host per-delta ingest logs.
- Root README currently mentions `critical` for `--log-level` while parser choices in `dayu/cli/arg_parsing.py` do not include it. This is a pre-existing documentation/parser mismatch outside Issue #148 unless implementation work directly touches `LOG_LEVEL_CHOICES`.

## Why This Is Not Over-Designed

The plan adds one global CLI flag and one runtime logging level, then reclassifies existing high-frequency records. It avoids new Host / Engine request fields, config files, logger registries, dynamic filters, payload classifiers, event schema changes, and activity stream changes.

The custom level is justified by existing local precedent (`VERBOSE=15`) and by the exact logging problem: ordinary DEBUG and stream-delta DEBUG need different thresholds while still sharing the same `dayu` namespace handler and log file.

## Completion Report Format

Implementation completion should report:

- Files changed.
- Final behavior for `--debug`, `--debug-stream`, and combined usage.
- Tests run and results, including pyright.
- README/docs updated or explicitly not updated with reason.
- Residual risks, including whether any stream diagnostics remain at ordinary DEBUG by deliberate decision.
