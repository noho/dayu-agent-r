# Host Phase 7 P7-S4 Controller Adjudication

日期：2026-05-16

## Scope

- Slice：P7-S4 WAITING Cancel, Late Result Diagnostic, Poll / Manual Adapter, EngineEvent Confirmation
- Implementation artifact：`docs/reviews/host-phase7-implementation-s4-wait-cancel-late-poll-20260516.md`
- MiMo review：`docs/reviews/host-phase7-code-review-s4-mimo-20260516.md`
- DS review：`docs/reviews/host-phase7-code-review-s4-ds-20260516.md`

## Findings

未接受 blocking finding。

MiMo review 未发现实质性问题。DS review 未发现实质性问题，提出 3 个 open questions，controller 裁决如下：

- S4-Q1：`WAITING` Run 但 current Attempt 非 `SUSPENDED` 时，`cancel_session_runs` 当前会落入 unsupported target，而不是 internal invariant error。
  - 来源：DS open question。
  - 裁决：accepted-as-residual。
  - 理由：`WAITING` Run 与 `SUSPENDED` Attempt 由 P7-S2 accept transaction 同源推进，正常状态机不可达该不一致状态。当前行为不会破坏已支持路径；若后续需要更强数据损坏诊断，应由 Host durable invariant hardening 补充显式 internal error 与测试。
  - 状态：non-blocking residual。
- S4-Q2：Poller idempotency key 不含 `observed_at`，但 resolution digest 包含 `observed_at`。
  - 来源：DS open question。
  - 裁决：accepted-as-residual。
  - 理由：当前 in-process `poll_once()` 成功 resolve 后 wait record 会退出 poll observation；write transaction 失败时不会提交 resolution idempotency record。现有路径不存在已提交幂等记录但 wait 仍保持 `WAITING` 的正常重试场景。若后续把 poll resolve 外部化、引入 retry queue 或跨进程 poller，应重新裁决 observed timestamp 与幂等 digest 的关系。
  - 状态：non-blocking residual。
- S4-Q3：late result rejection 统一返回 `INVALID_STATE`，没有机器可读 detail 区分 `wait_cancelled` / `wait_lost` / `run_terminal` / `invalid_wait_state`。
  - 来源：DS open question。
  - 裁决：deferred public contract hardening。
  - 理由：当前 `HostApiErrorDetail` 只覆盖 steer conflict detail。为 late result 增加 typed detail 会扩展 public API contract，不属于 P7-S4 最小 slice。P7-S4 已通过 canonical `WAIT_LATE_RESULT_REJECTED` diagnostic event 保留机器可读 rejection reason，public error detail 可在后续 Host API detail union 扩展时处理。
  - 状态：non-blocking residual。

## Accepted Evidence

- `cancel_run` 与 `cancel_session_runs` 的 `WAITING` 分支复用同一个 `cancel_waiting_run_in_transaction(...)` transition，不创建 resume Attempt。
- `cancel_waiting_run_in_transaction(...)` 在同一 write transaction 内追加 `CANCEL_REQUESTED`、取消 active wait records、追加 `RUN_CANCELLED` 并 CAS Run `WAITING -> CANCELLED`。
- late result diagnostic 只覆盖 `CANCELLED`、`LOST`、owner Run terminal 与 invalid wait state；`RESOLVED` / `FAILED` 的不同 key 请求只返回 `INVALID_STATE`，不写 late diagnostic。
- `wait_late_rejection` 独立幂等 scope 支持同 key 同 digest 重放、同 key 异 digest 冲突，避免 late diagnostic 重复写入。
- `WaitPoller.poll_once()` 只在 read transaction 中取快照，adapter 调用发生在 Host transaction 外；ready / lost 统一走 public resolve port，cancelled wait 只触发 adapter abandon。
- EngineEvent ingest 对 `RUN_SUSPENDED` / `TOOL_AWAITING` 只写 diagnostic confirmation，不创建 wait state，不把 Run / Attempt 失败收口。
- `dayu/host/README.md` 与 `tests/README.md` 已按当前代码事实同步 P7-S4 能力与测试入口。
- 未修改 Engine、contracts、fins、service、ui、recovery、outbox、audit 或 tool trace read-model。

## Verification

- `source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`
  - 结果：`42 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`388 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## Verdict

P7-S4 accepted。可进入 accepted slice commit 与总控文档 checkpoint。

## Residual Risk

- Engine contract 当前不携带 Host accepted wait refs；P7-S4 只能做 diagnostic / idempotent confirmation，不能验证 Engine awaiting event 与 Host accepted wait refs 完全匹配。
- Poller 仍是最小单轮入口，不包含后台调度循环、退避、并发 in-flight fencing 或 adapter 错误重试治理。
- `WAITING` Run + 非 `SUSPENDED` Attempt 的防御性 internal invariant error、poller retry 外部化后的幂等 digest 策略、late result typed public error detail 均为后续 hardening / API contract 扩展项。
