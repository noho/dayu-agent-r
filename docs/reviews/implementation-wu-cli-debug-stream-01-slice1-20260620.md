# WU-CLI-DEBUG-STREAM-01 Slice 1 Implementation

## Scope

仅实现 Slice 1：Runtime log level + CLI `--debug-stream` plumbing。
未修改 Host / Engine ingest、runner、SSE parser，也未进入后续 Slice。

## Changed Files

- `dayu/runtime/log_levels.py`
  - 新增 `STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1` 并导出。
- `dayu/runtime/log.py`
  - 注册 stdlib level name `STREAM_DEBUG`。
  - 新增 `LogLevel.STREAM_DEBUG`。
  - `set_level_from_flags()` 新增 `debug_stream` 参数，并优先解析为 `STREAM_DEBUG`。
- `dayu/cli/arg_parsing.py`
  - `ParsedCliArgs` 与默认 namespace 新增 `debug_stream: bool = False`。
  - 新增全局 `--debug-stream` 参数及 help 文本。
- `dayu/cli/main.py`
  - 保存 `debug_stream_for_cleanup`。
  - 初始日志装配和 cleanup 日志装配均传入 `debug_stream`。
- `tests/runtime/test_log.py`
  - 覆盖 `debug_stream=True` 优先于已解析 `log_level`。
  - 覆盖 `STREAM_DEBUG` stdlib 注册。
  - 覆盖 DEBUG 阈值抑制 STREAM_DEBUG 记录，STREAM_DEBUG 阈值同时输出 stream-debug 与普通 DEBUG。
- `tests/runtime/test_log_levels.py`
  - 覆盖 STREAM_DEBUG 常量数值低于 DEBUG。
  - 覆盖仅导入常量模块不注册 stdlib level name。
- `tests/cli/test_arg_parsing.py`
  - 覆盖 `--debug-stream` 解析、与 `--debug` 组合解析、顶层与命令 help。
  - 覆盖 `main()` 两次 runtime log 装配均传入 `debug_stream=True`。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q`
  - Result: `88 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings from installed dependency.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported a newer available version notice only.
- `git diff --check`
  - Result: passed.

## Docs Decision

本 Slice 不更新 README。根 README 的用户可见 CLI 文档更新属于 approved plan 的 Slice 4；本 Slice 仅完成 runtime level 与 CLI plumbing。

未修改：

- `docs/host/issues-implementation-control.md`
- Host / Engine files
- README files
- plan / review artifacts other than this required implementation artifact

## Residual Risks / Uncovered Areas

- Host ingest delta、OpenAI runner stream heartbeat、SSE done-token 仍未迁移到 `STREAM_DEBUG_LOG_LEVEL`；这是 Slice 2 范围。
- Prompt / interactive compatibility guard 与 legacy unsupported execution option 断言仍是 Slice 3 范围。
- README 用户说明仍是 Slice 4 范围。
