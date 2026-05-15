# PR 54 Additional Review Fix Artifact

## Gate

- Gate: PR 54 additional review accepted-fix gate
- Role: AgentCodex implementation/fix worker
- Source controller artifact: `docs/reviews/pr-54-review-additional-controller-adjudication-20260515.md`
- Source review artifacts:
  - `docs/reviews/pr-54-review-20260515-1221.md`
  - `docs/reviews/pr-54-review-20260515-1224.md`

## Summary

本轮只修复 controller accepted current fix items A1-A10；未实现 rejected / deferred 项，包括 active cancel dispatch record cancelled、非 terminal duplicate precheck、token-cancel build short-circuit、active cancel port refactor、watchdog / hang timeout、logging-only drain refactor与 helper cleanup。

## Per-Finding Status

- A1 已修复：`_consume_worker_events` 的 envelope 构造、`handle.local_worker_id` 读取、ingestor 构造与事件循环统一进入 `try/finally`，pre-event 异常也会注销 active worker、关闭 handle、释放 lane token。
- A2 已修复：preview event 分类同时校验 `EngineEventType` 与对应 data class；`data=None` 或错误 data 类型会进入 rejected diagnostic。
- A3 已修复：RunInputBuilder current facts 只接受 Run `RUNNING`、Attempt `STARTING`、dispatch record `DISPATCHING` 且 identity 匹配的 snapshot。
- A4 已修复：`AttemptDispatchSnapshot.__post_init__` 拒绝非 `CancellationToken`，覆盖 `None` token。
- A5 已修复：`_run_mutation_result_for_active` 在 rowcount=0 且最新 Run 为终态时返回 `CAS_LOST`。
- A6 已修复：`_validate_terminal_input` 将 terminal event type helper 的 `ValueError` 转换为 `HostDurableError`。
- A7 已修复：`HostDispatchScheduler.close()` 不再直接 close active handles，只发送 cancel 并取消 active task，handle close / lane release 由 consume task finally 负责。
- A8 已修复：`_DefaultLocalWorkerHandle.close()` close 后清空 `_events`，close-after-close 为 no-op，events-after-close 明确抛 `RuntimeError`。
- A9 已修复：补充真实 Default LocalProxy 的 Engine stream raise、empty stream，以及 scheduler 经真实 proxy 将 stream error 映射为 `LOST` 的测试。
- A10 已修复：Host import boundary test 禁止 `dayu.host` 导入 `dayu.config`。

未回写 source review artifact 标题状态；本 handoff 的 allowed docs scope 只包含本 fix artifact 与 README。上述状态映射供 re-review 使用。

## Files Changed

Production:

- `dayu/host/api.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/local_proxy.py`
- `dayu/host/run_input.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`

Tests:

- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_run_input_builder.py`

Docs:

- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/pr-54-review-additional-fix-host-p5-local-dispatch-codex-20260515.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_run_attempt_transitions.py -q`
  - Result: `107 passed in 0.72s`
- `source .venv/bin/activate && pytest tests/host tests/runtime -q`
  - Result: `375 passed in 5.77s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Residual Risk

- 本轮未处理 controller rejected / deferred 项；active cancel watchdog、RemoteProxy、observability cleanup、duplicate helper cleanup 与 multi-scheduler cancel port 仍按 controller artifact 的 owner / destination 跟踪。
- `_consume_worker_events` pre-event 异常路径现在释放资源，但不会把该 pre-event Host 编程 / durable 异常额外写入 worker_lost closeout；本轮 accepted finding 只要求资源不泄露。
- Source review artifact 标题状态未修改，因为当前 worker allowed docs scope 未包含 `1221` / `1224` 两份 source artifacts。

