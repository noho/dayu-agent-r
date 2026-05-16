# Host Phase 7 P7-S4 Implementation - WAITING Cancel, Late Result, Poll, Engine Confirmation

## 状态

已完成 P7-S4 implementation。未提交 commit、未 push、未开 PR。

## 改动

- `cancel_run` / `cancel_session_runs` 支持取消 `WAITING` Run，复用 `cancel_waiting_run_in_transaction(...)`，取消 active wait records 并把 Run 置为 `CANCELLED`，不创建 resume Attempt。
- 新增 `cancel_active_wait_records_for_run(...)` 的 poll 可观察读取配套 helper，以及 `cancel_waiting_run_row(...)` / `cancel_waiting_run_in_transaction(...)` 路径。
- `resolve_wait` 对已取消、已终态或 owner Run 已终态的 late result 写入 `WAIT_LATE_RESULT_REJECTED` diagnostic，使用独立 `wait_late_rejection` 幂等 scope；同 key 同 digest 不重复写 diagnostic，同 key 异 digest 返回幂等冲突且不追加事件。
- 新增最小 `WaitPoller` / `WaitPollAdapter` / `WaitPollAdapterRegistry`。poller 只读取 poll wait 快照；外部 adapter 调用在 Host transaction 外；ready/lost 统一走 `resolve_wait`；cancelled wait 只调用 adapter abandon。
- EngineEvent ingest 对 `RUN_SUSPENDED` / `TOOL_AWAITING` 改为 diagnostic confirmation，不创建 Host wait state，不把 active/WAITING Run 失败收口。
- Controller 抽查修正：`RESOLVED` / `FAILED` wait record 的不同 key 请求只返回 `INVALID_STATE`，不写 `WAIT_LATE_RESULT_REJECTED`；`CANCELLED` / `LOST` 与 owner Run terminal 才进入 late diagnostic path。
- `dayu/host/README.md` 与 `tests/README.md` 已按当前代码事实同步 WAITING cancel、late diagnostic、最小 poller 与 Engine awaiting confirmation 测试覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`：42 passed。
- `source .venv/bin/activate && pytest tests/host -q`：388 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors。
- `git diff --check`：通过。

## 风险与未覆盖

- Engine contract 当前不携带 Host accepted wait refs；P7-S4 只能实现 diagnostic/idempotent confirmation 与缺 ref 不建状态，无法校验“matching refs”。
- Poller 是最小单轮实现，不包含调度循环、退避、并发 in-flight fencing 或 adapter 错误重试治理。
- README 已做最小同步；P7-S5 仍需做 Phase 7 聚合级文档/验证收口。
