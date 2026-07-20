# WU-SEMANTIC-OWNERSHIP-01 AR-F06 closeout correction Controller validation

## Decision

`AR-F06` 最终裁决为：

`REJECTED_NOT_A_DEFECT / EXPECTED_HOST_CLOSE_AND_STARTUP_RECOVERY / NO_RESIDUAL / NO_FIX_OWNER`

此前 aggregate / closeout artifact 把“Host 关闭期间 Run B 不立即晋升、等待下一次 Host 启动恢复”记为 scheduler/lifecycle residual。该 defect framing 与 Host 设计真源直接矛盾，因此被本记录 supersede；历史 review artifact 保留当时的审查证据，但不再代表当前 Controller 状态。

## Design truth

- `docs/host/design.md:580-584`：queued Run 只在 Session 没有 active Run 时 promotion；Host startup recovery scan 必须触发 queue-promotion check。
- `docs/host/design.md:938-942`：Host opener close 是 handle lifecycle，不是 cancel；close 必须停止 scheduler/promotion 且不再启动新 Attempt，不得伪造 Run terminal fact。
- `docs/host/design.md:3542-3557`：startup recovery 保持 `QUEUED` 状态，并在 committed page 后投递 matching queue-promotion wake；全部 recovery/wake 完成后才进入 `READY`。
- `docs/host/design.md:3634-3640`：durable accepted prompt 在 Host 正常 close 后重启，仍应最终产出 answer。

## Code-path verification

- `dayu/host/open_host.py:1370-1395`：`open_host` 在 `mark_ready()` 前通过 durable actor 完成 `_StartupRecoveryActorOperation`。
- `dayu/host/recovery.py:328-340,380-390`：scanner 对 `QUEUED` Run 产生 `QUEUE_PROMOTION_CHECK`，并在 batch commit 后调用 `wake_queue_promotion(session_id)`。
- `dayu/host/dispatch.py:1111-1130,1221-1257`：scheduler 接收 promotion wake，执行 pre-start governance，并在产生 pending dispatch 后唤醒 dispatch。
- `dayu/host/dispatch.py:1797-1825,4338-4354`：无 active Run 时选择最早 queued Run，原子创建 `RUN_STARTED`、`ATTEMPT_STARTED`、Attempt 与 dispatch record；queued path 使用 `start_reason=queue_promotion`。

## Runtime validation

定向 owner/component tests：

```text
tests/host/test_recovery_scan.py::test_scan_queued_does_not_mutate_or_create_attempt
tests/host/test_open_host_runtime.py::test_open_host_startup_recovery_dispatches_gracefully_closed_run
tests/host/test_admission_queue.py::test_terminal_closeout_promotes_exactly_one_queued_run_after_commit
3 passed
```

额外使用真实 public `open_host` 路径和同一临时 SQLite 执行 close/reopen smoke：

```text
before_close_B=queued
after_reopen_A=succeeded
after_reopen_B=succeeded
worker_accept_order=A -> B
```

这证明实现不只“扫描到 B”：重启后先恢复占用 active slot 的 A，A terminal 释放 slot 后，B 被 promotion、worker accept 并进入 `SUCCEEDED`。

## Closeout effect

- `AR-F06` 不需要产品、测试或 UI/Service catch 修复。
- `AR-F06` 不创建 future Host scheduler/lifecycle owner、替代 WU 或 residual。
- `WU-SEMANTIC-OWNERSHIP-01` 当前 residual risk 为 `0`。
- Issue 142、151、175、177、178、Web/WeChat/render trackers 与 Gemini 测试账号条件保持各自既有分类，但它们是 deferred/excluded scope 或环境条件，不是本 WU residual。
