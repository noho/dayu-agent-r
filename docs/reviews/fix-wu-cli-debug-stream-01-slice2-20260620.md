# WU-CLI-DEBUG-STREAM-01 Slice 2 Fix Report

## Scope

本次 fix gate 只处理 code review adjudication 接受的三项：

1. 移除 Slice 2 在 `tests/engine/runners/openai/test_runner_diagnostics.py` 新增的 `type: ignore[attr-defined]`。
2. 为 `dayu/engine/runners/openai/sse_parser.py` 的 SSE done-token `STREAM_DEBUG` 诊断补充 `provider_request_id`。
3. 收紧 `dayu/host/engine_ingest.py` 中 `_engine_ingest_log_level` 的返回值 docstring。

未修改 `docs/host/issues-implementation-control.md`。

## Changes

- `test_runner_diagnostics.py`
  - 新增局部 `_DelayedSessionClient` 与 `_RunnerWithDelayedSessionClient` 测试类型，用于替换 stream diagnostics 测试中的 Runner HTTP client。
  - 移除了 `_collect_stream_diagnostic_events(...)` 中 Slice 2 新增的 `type: ignore[attr-defined]`。
  - fake SSE response 增加 `x-request-id=req-stream-1`，并断言 STREAM_DEBUG 下的 done-token 诊断包含 `provider_request_id=req-stream-1`。
  - 保持 gating 行为不变：ordinary `DEBUG` 不捕获 heartbeat / done-token stream diagnostics，`STREAM_DEBUG_LOG_LEVEL` 捕获。
- `sse_parser.py`
  - `sse.done_token received` 仍使用 `STREAM_DEBUG_LOG_LEVEL`，并增加 `provider_request_id=%s` 结构化字段。
  - 未记录 SSE chunk 正文、content delta、reasoning delta、tool arguments 或 response body。
- `engine_ingest.py`
  - `_engine_ingest_log_level` docstring 改为说明返回 Python logging 可消费的整数级别，delta 事件使用 Dayu 自定义 `STREAM_DEBUG` 级别。
  - 未改变 Host ingest 行为。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q`
  - 结果：`13 passed in 0.67s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## README Check

已按触发规则检查 `dayu/engine/README.md`、`dayu/host/README.md` 与 `tests/README.md` 的更新边界。当前 fix gate 范围严格限定为 adjudication 接受项；README / test README 文档同步属于后续 README slice，本文不扩大修复范围。

## Residual Risk

- 未运行完整测试套件；本 gate 按要求运行了受影响 Host / Engine logging 测试和全量 pyright。
- stream diagnostics gating 测试仍依赖受控 `asyncio.sleep` 触发 heartbeat；现有参数与 review 裁决一致，风险低。
