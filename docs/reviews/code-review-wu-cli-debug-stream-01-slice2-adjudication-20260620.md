# WU-CLI-DEBUG-STREAM-01 Slice 2 Code Review Adjudication

## Verdict

Slice 2 进入 fix gate。

两路 review 均确认生产路径迁移方向正确：Host ingest delta、OpenAI runner stream idle heartbeat、SSE done-token diagnostics 已从 ordinary DEBUG 迁移到 `STREAM_DEBUG_LOG_LEVEL`，非 stream 的 lifecycle / HTTP DEBUG 与 warnings 保持不变。

## Accepted Findings

1. 接受 AgentMiMo Finding 1：Slice 2 新增测试行 `runner._http_client._session = session  # type: ignore[attr-defined]` 扩散了类型绕过。虽然仓库内已有类似测试注入模式，但本 slice 不应新增 `type: ignore`。修复应移除本 slice 新增的类型绕过，并保持 pyright 0 errors。
2. 接受 AgentDS Finding 1：`sse.done_token received` 可补充 `provider_request_id`，使 stream diagnostics 与同模块其他诊断记录保持结构化风格。该日志仍必须使用 `STREAM_DEBUG_LOG_LEVEL`，不得泄露正文内容。
3. 接受 AgentDS Finding 2：`_engine_ingest_log_level` docstring 中“stdlib logging level 数值”措辞不精确。修复应说明返回的是 Python logging 可消费的整数级别，其中 delta 使用 Dayu 自定义 `STREAM_DEBUG` 级别。

## Rejected Or Deferred Findings

- AgentMiMo Finding 2 / AgentDS Finding 5 关于 `_Delayed*` helper 体量与平行 fake 结构：不作为本 slice must-fix。延迟 readany 是 heartbeat gating 测试的直接输入条件，局部 helper 避免扩展共享 fake 的接口契约。
- AgentMiMo Finding 3 / AgentDS Finding 4 关于 heartbeat timing：不作为本 slice must-fix。当前 `delay_seconds=0.06`、`heartbeat=0.02`、`timeout=0.5` 给出足够余量，测试验证的是 bounded idle wait 的真实行为。
- AgentDS Finding 3 关于 REASONING_DELTA / TOOL_CALL_DELTA 端到端 stream path：不作为本 slice must-fix。Host helper test 已覆盖三类 delta level 映射；SSE done-token 处理与 chunk 内容类型无关。

## Fix Instructions

AgentCodex should make a narrow Slice 2 fix:

- Remove the newly introduced `type: ignore[attr-defined]` from `tests/engine/runners/openai/test_runner_diagnostics.py` without adding a new type-ignore, `Any`, `object`, or broad production test seam.
- Keep the stream diagnostics gating test behavior intact: ordinary `logging.DEBUG` must not capture stream heartbeat / done-token diagnostics; `STREAM_DEBUG_LOG_LEVEL` must capture them.
- Change the SSE done-token log message to include `provider_request_id` while keeping it at `STREAM_DEBUG_LOG_LEVEL`.
- Tighten `_engine_ingest_log_level` docstring wording only; do not change Host ingest behavior beyond the accepted Slice 2 semantics.

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`
