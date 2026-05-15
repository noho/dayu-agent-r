# Host P5-S3 Dispatch Scheduler, Lane And LocalProxy Controller 裁决

## Gate

- Work unit: Host Phase 5 RunInputBuilder local dispatch
- Slice: P5-S3 Dispatch Scheduler, Lane And LocalProxy
- Role: controller adjudication
- Branch: `feat/host-phase5-local-dispatch`
- Design source: `docs/host/design.md` §17 / §22
- Approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S3, §3.4, §3.5, §4

## 输入

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s3-dispatch-scheduler-localproxy-20260514.md`
- MiMo code review: `docs/reviews/gateflow-code-review-host-p5-s3-dispatch-scheduler-localproxy-mimo-20260515.md`
- DS code review: `docs/reviews/gateflow-code-review-host-p5-s3-dispatch-scheduler-localproxy-ds-20260514.md`

## 裁决

接受 P5-S3 slice。两份独立 review 均确认无 blocking finding，核心实现满足 plan 中的 scheduler、lane、LocalProxy 和 worker accept 边界要求。

可接受的稳定事实：

- `HostDispatchScheduler` 实现 `pending -> waiting_for_lane -> dispatching -> worker accepted` 路径。
- runtime lane 使用独立 lane DB，lane token 只表达 capacity，不表达 Host truth、lease、fencing 或 Attempt owner。
- durable recheck 和 accept transaction 均校验 Run / Attempt / dispatch record 当前状态，CAS loser 和 pre-accept cancel race 不调用 worker，并释放 lane。
- lane acquire timeout 与 worker accept timeout 均以 `worker_startup_timeout` 收口为 Run / Attempt `FAILED`。
- worker accept 后追加 `ATTEMPT_RUNNING`，再把 Attempt 推进到 `RUNNING`，并记录 dispatch worker accept refs；dispatch record status 仍保持 `dispatching`。
- `ATTEMPT_RUNNING` payload 已包含 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id`。
- Default LocalProxy worker 只调用 Engine public `run_agent_messages(request)` 并暴露事件流；不做 EngineEvent ingest 或 terminal closeout。
- Host -> Engine import 在 LocalProxy 边界内合法；Engine 仍不导入 Host，Host 仍不得导入 Fins / Service / UI。

## Findings 裁决

- `HostCommandHandleOptions.local_execution` lifecycle wiring: accepted as nonblocking residual。P5-S3 已提供 typed options、scheduler 和 LocalProxy baseline；`local_execution=None` 时保持现有 no-op wakeup 行为。command-handle 启动 / 关闭 scheduler 的完整生命周期接入由后续 controller-opened scope 处理，不阻塞当前 slice。
- `_NeverCancelledToken` placeholder: accepted as nonblocking residual。P5-S3 的 cancel coverage 依赖 durable recheck 和 pre-accept cancel race；Engine run-local cancellation token propagation 属于 P5-S5。
- handle close pending acquire / active worker cancel test gap: accepted as residual。当前 lane release 主路径和 close 实现已被 review 接受；scheduler close 的更完整覆盖转交 P5-S5 / 后续 lifecycle wiring scope。
- `_consume_worker_events` discards events: intended P5-S3 boundary。P5-S4 负责 EngineEvent ingest mapping 和 terminal closeout。
- DS L1 `_snapshot_from_dispatch` unused `dispatch_record` parameter: accepted-as-fixed。签名已收敛为只接收 `PendingDispatchRecord`，避免文档信号与实际数据来源不一致。
- DS L2 duplicate `_NeverCancelledToken` in test and production: accepted as nonblocking residual。测试局部 token 不扩大生产接口；后续如需要共享 helper，必须先确认公共契约归属。

## 验证

Review 前验证已通过：

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q`: 27 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`: 0 errors。
- `git diff --check`: passed。

当前裁决后的签名清理与 README 同步需要在 accepted slice commit 前重新运行同一组验证。

## 后续 owner

- P5-S4: EngineEvent ingest mapping、remote event identity validation、terminal closeout。
- P5-S5: active / session-scope cancel propagation、run-local cancellation token、worker cancel best-effort path。
- 后续 command-handle lifecycle wiring scope: `HostLocalExecutionOptions` 从 construction options 接入 scheduler open / close / wakeup。
