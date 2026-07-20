# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Aggregate Deepreview

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A`
- Role: AgentMiMo (aggregate deepreview gate)
- Branch: `phaseflow/host-issues-control`
- Base: `4a282850` (accepted plan commit) → `c8634b9d` (current HEAD)
- Review date: `2026-07-12T19:59:47+0800`
- Mode: current changes (aggregate over 8 implementation slices)
- Artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-aggregate-deepreview-mimo.md`

## Scope

- 8 implementation slices (S1–S8), 121 files changed, ~20k insertions
- Focus: cross-slice interaction, state machine closure, contract consistency, residual blocker detection
- Excluded: R3-B/C/D/E/F changes, branch-vs-main history outside R3-A code paths

## Aggregate Review Inputs

| Slice | MiMo Review | Controller Adjudication | Status |
|-------|-------------|------------------------|--------|
| S1 | `s1-code-review-mimo.md` → rereview `s1-code-review-rereview-mimo.md` | `s1-code-review-rereview-controller-adjudication.md` | PASS (fix gate satisfied) |
| S2 | `s2-code-review-mimo.md` | `s2-code-review-controller-adjudication.md` | PASS |
| S3 | `s3-code-review-mimo.md` | `s3-code-review-controller-adjudication.md` | PASS |
| S4 | `s4-code-review-mimo.md` | `s4-code-review-controller-adjudication.md` | PASS |
| S5 | `s5-code-review-mimo.md` | `s5-code-review-controller-adjudication.md` | PASS |
| S6 | `s6-code-review-mimo.md` | `s6-code-review-controller-adjudication.md` | PASS |
| S7 | `s7-code-review-mimo.md` | `s7-code-review-controller-adjudication.md` | PASS |
| S8 | `s8-code-review-mimo.md` | `s8-code-review-controller-adjudication.md` | PASS |

## Findings

未发现实质性问题。

以下为各 slice 已接受 finding 的 aggregate traceability 确认，以及跨 slice 合约一致性验证结论。

## Aggregate Finding Traceability

### S1 Durable Integrity + Bounded Runner-call Provenance (DR-006, DR-010, compact provenance)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-006 runner-call hot payload unbounded | **fixed** | `_runner_call_manifest.py` 唯一 owner；三个 producer（ordinary/continuation/compactor）通过 `RunnerCallHotAtoms` typed atoms 产出固定 shape hot payload；`projector_metadata_summary` 从 hot payload 移除；`test_runner_call_hot_payload_contract.py` 覆盖 0/1/12/300 messages producer matrix 与 7 种 tamper 场景；production stress 12/12 通过。 |
| DR-010 descriptor content/digest split | **fixed** | `dayu/host/durable/payload_resolution.py` 唯一 owner；SQLite payload 同时校验 ref/digest/size/format/canonical bytes；artifact payload 校验 containment/digest/size；`test_durable_payload_integrity.py` 覆盖 7 种单原子篡改 + non-canonical + artifact tamper；effective execution config 重算 sha256。 |
| compact_material wrong call ref fallback | **fixed** | `compact_material.py` 不再用 result event id 代替 call event id；缺失/错误类型/identity mismatch 均 fail closed；Codex-F1 fix 确保 strict compact path 通过 shared integrity owner 解析 payload，corruption 不再静默降级。 |
| Codex-F1 compact strict path downgrade | **fixed** (S1 fix gate) | rereview 确认 strict path 通过 shared resolver 解析 accepted result payload；`HostDurableError` 传播，不降级为 missing evidence。 |
| Codex-F2 manifest semantic graph | **fixed** (S1 fix gate) | `_runner_call_manifest` 有完整 typed manifest parser/validator；Tool Trace 仅从 typed validated manifest 投影 summary。 |
| Codex-F3 hot diagnostic synthesis | **fixed** (S1 fix gate) | `_runner_call_manifest` 暴露 typed hot payload parser；complete diagnostic 必须显式存在并 cross-check。 |

### S2 Host Admin + Public Durable Actor (DR-007, DR-011)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-007 admin command opens execution Host | **fixed** | `open_host_admin()` 独立 opener，只启动 durable actor；`HostAdmin` Protocol 与 `Host` 无继承关系；CLI session list/purge 使用 admin opener；`test_public_host_admin.py` 验证 zero execution side effects。 |
| DR-011 async Host blocks event loop | **fixed** | `_HostDurableActor` 单线程 actor 拥有 connection/thread/close；所有 public async command/read/watch 经 actor；`_ThreadsafeSchedulerWakeupPort` / `_ThreadsafeActiveWorkerCancelPort` 做线程安全 bridge；`test_durable_actor.py` 验证 thread identity 与 caller cancellation 不中断 FIFO。 |
| MiMo-RR1 actor close race | deferred-with-owner | 当前 `_closed` gate 使 race 不可达；非当前 blocker。 |
| MiMo-RR2 bridge callback no timeout | deferred-with-owner | 当前 bridge callback 有界；非当前 blocker。 |
| MiMo-RR3 executor shutdown on event loop | deferred-with-owner | 当前 close 顺序 drain 在先；非当前 blocker。 |

### S3 Scheduler Health / Admission Lease / Retry / Idempotent Replay (DR-009)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-009 scheduler fatal not propagated | **fixed** | `HostExecutionHealthGate` 唯一 lifecycle owner（STARTING→READY→UNAVAILABLE→CLOSING→CLOSED）；`report_fatal()` 与 `acquire_admission()` 共享 admission lock；`test_scheduler_health.py` 覆盖 deterministic admission-first/fatal-first/caller-cancel race。 |
| dispatch retry exhaustion self-closes | **fixed** | `HostTransactionRetryExhaustedError` 为 transient，不关 scheduler/不 cancel workers；按 poll interval 退避重试。 |
| idempotent admission replay skips wake | **fixed** | replay 从 Run/Attempt/dispatch snapshot 重新派生 wake；`test_admission_multiprocess.py` 验证 pending dispatch/pre-start replay matching wake。 |
| DS-F2 `_raise_if_wake_unavailable` dead code | non-blocking cleanup | 不影响正确性。 |

### S4 Startup Recovery Keyset Batching

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| recovery single huge transaction | **fixed** | keyset cursor `(accepted_event_sequence, run_id)` + fixed upper watermark + fixed `policy.now`；每批独立 write transaction；`test_recovery_scan.py` 覆盖 batch=2 bounded/stable、mid-scan insert deferral、batch failure/rerun convergence。 |

### S5 Active-cancel Watchdog & Transaction-local Classification

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| watchdog wakeup drop | **fixed** | `asyncio.Queue(maxsize=1)` → `asyncio.Event` level-triggered；tick 前 clear，tick 期间新 wake 保持 set；`test_active_cancel_dispatch.py` 覆盖 second-wake barrier。 |
| cancel_run deferred race | **fixed** | `_CancelRunOperation` 在同一 write transaction 返回 classification；删除 `_is_deferred_cancel_state()` 与 post-write read；`test_active_cancel_dispatch.py` 覆盖 transaction spy。 |

### S6 Wait Expiry、Bounded Observation 与 Host Shutdown (DR-008, DR-012)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-008 expired wait remains WAITING | **fixed** | `_expire_wait_in_transaction()` 在 caller-provided transaction 内完成 FAILED terminal + idempotent key；poller 对 EXPIRED 调用同一 helper；`test_wait_expiry_closeout.py` 覆盖 helper contract、multiprocess first-committer-wins。 |
| DR-012 wait adapter can hang close | **fixed** | `WaitPollerSupervisor` 使用 finite `close_drain_timeout_seconds`（不允许 None）+ shared monotonic deadline + `max_outstanding_adapter_calls` cap；observation token gate ACTIVE→INVALIDATED→FINISHED；`test_wait_observation_runner.py` 覆盖 stuck poll/abandon、cap=1、shared deadline。 |
| S6-3 IdempotencyStore instantiation inconsistency | accepted (cosmetic) | 不影响正确性。 |

### S7 Compaction Attempt Cancellation (DR-025)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-025 compactor timeout contaminates parent | **fixed** | 每 attempt 新 `_CompactionAttemptCancellationToken(parent)`；timeout 只写 child；parent cancel 始终优先；`test_compaction_cancellation_scope.py` 覆盖 timeout→success、parent cancel precedence、running visibility。 |
| proactive compaction TOCTOU | **fixed** | manifest commit 后、provider call 前 `_ensure_compactor_proposal_active()` recheck；recorder hook 改变 durable snapshot 时 provider count=0。 |

### S8 Layer-neutral Runtime Partial Cleanup (DR-017, DR-029)

| Accepted Finding | Fix Status | Aggregate Evidence |
|---|---|---|
| DR-017 process partial start/cleanup poisoning | **fixed** | `_started` 与 `_closed` 为并发 gate；`_cleanup_completed` 与 `_ProcessCleanupProgress` 分离 completion；`asyncio.shield()` 防止 caller cancellation 取消 cleanup；`test_interruptible_process.py` 覆盖 pre/post-spawn start failure、6 个 cleanup checkpoint partial failure、concurrent close。 |
| DR-029 lane completion after failed release | **fixed** | `_close_completed` 只在 heartbeat stopped + `_held_tokens` empty + no error 时写入；failed token 保留，第二次 close 重试；`test_lane.py` 覆盖 two-token one-release-fails、concurrent close、first reason stability。 |

## Cross-Slice Contract Consistency

### 验证维度

1. **S1 manifest → S7 compaction**: `CompactionAttemptRejected` 引用 `proposal_manifest_ref/digest`，来自 `DurableCompactorProposalManifestRecorder`，使用 S1 的 `runner_call_hot_payload()`。合约边界清洁，无 re-derivation。

2. **S2 actor → S3 health gate**: health gate 独立于 actor；admission 通过 `acquire_admission()` 取 lease 后提交 actor operation；actor 不引用 health gate。单一 lifecycle owner。

3. **S3 health gate → S4 recovery**: recovery 在 actor thread 运行，返回 immutable result；health gate 在所有 startup critical 组件成功后才 `mark_ready()`。STARTING 状态允许 scheduler wake 以支持 recovery batch dispatch。

4. **S5 watchdog → S3 supervisor**: watchdog 通过 `_supervise_critical_task()` 包装；unexpected exit → `report_fatal()` → UNAVAILABLE。watchdog 不直接操作 health gate。

5. **S6 wait expiry → S2 actor**: expiry 通过 `_CommandHandleWaitResolver` 经 command path；poller 通过 resolver 委托，不直接操作 store。cancel 路径通过 durable state 独立于 poller。

6. **S7 compaction token → S5 cancel**: proactive token 读 durable Run state；parent cancel 传播到 child。post-compaction transaction 独立验证 Run snapshot。

7. **S8 runtime → S2 close order**: close 顺序为 health gate CLOSING → wait poller → actor drain → scheduler → projection → actor handle → executor → scheduler store → health gate CLOSED。open-failure path 镜像同一顺序。

**结论**: 七个跨 slice 合约边界全部清洁：无 fallback、shim 或 re-derivation；状态机 ownership 单一来源；typed interface 无 Any/object/无类型 lambda。

## Semantic Ownership Drift 验证

| 业务事实/状态 | 唯一 owner | 验证结论 |
|---|---|---|
| runner-call hot payload shape | `_runner_call_manifest.py` | ✓ 三个 producer 只传 typed atoms，consumer 只从 validated manifest 投影 |
| descriptor ref/digest/size/content | `durable/payload_resolution.py` | ✓ 所有 consumer 委托 shared resolver |
| effective execution config digest | `_execution_config_projection.py` | ✓ 重算 sha256，校验 digest/ref |
| execution vs admin Host capability | `host/api.py` opener/handle contract | ✓ 独立 Protocol，无继承 |
| async durable connection/thread | `_HostDurableActor` | ✓ single-thread actor owns connection |
| scheduler health / admission | `HostExecutionHealthGate` | ✓ 唯一 lifecycle owner，共享 admission lock |
| wait deadline terminal outcome | `waiting._expire_wait_in_transaction()` | ✓ 同事务 FAILED，poller/direct/callback 共用 helper |
| proposal timeout cancellation | `_CompactionAttemptCancellationToken` | ✓ child token，parent 优先 |
| process/lane close completion | 各自 runtime owner | ✓ `_cleanup_completed` / `_close_completed` 与 gate 分离 |

## Deferred-with-Owner 汇总

以下为 controller 已裁决的 deferred 项，当前 R3-A 代码路径无直接 blocker 证据：

| Item | Owner | 说明 |
|---|---|---|
| S2 actor close check-then-assign race | future durable actor hardening | 当前 `_closed` gate 使 race 不可达 |
| S2 bridge callback no timeout | future liveness/supervision | 当前 bridge callback 有界 |
| S2 executor shutdown sync on event loop | future actor close hardening | 当前 close 顺序 drain 在先 |
| S2 admin close executor fallback | future admin close hardening | 当前无 failure path |
| S4 legacy `read_non_terminal_runs()` | cleanup pass | S4 recovery 不调用 |
| S6 non-cooperative provider daemon thread | R3-D cooperative cancellation | host 侧已 bounded（cap/token/drop） |
| Fins wait-adapter reverse dependency | R3-D half | S6 只交付 Host bounded contract |

## Residual Risk

1. **Polling test helpers**: `_wait_for_run_status` / `_wait_for_attempt_status` 使用 10ms sleep loop（最多 100 次），理论 1s 超时。CI 负载下可能 flaky，但不影响正确性判断。
2. **No chaos/fault-injection**: 未覆盖 SQLite corruption、disk-full、network filesystem locking。属于运维/部署层面风险。
3. **No concurrent `open_host` integration test**: multiprocess test 使用低层 durable store，未测完整 `open_host` lifecycle 并发。
4. **Actor store close failure**: `test_open_host_runtime.py` close-order test 只测 scheduler close failure（`_RaisingSchedulerClose`），未测 actor store close 失败路径。
5. **Fresh-schema behavior**: S1 对旧 hot rows、metadata-only manifests、non-closing manifest graphs 会 fail closed。部署前若需处理历史数据，需运维审计。
6. **Recovery non-atomic wake delivery**: batch commit 后多个 wake callback 非原子；已通过 idempotent replay 在 next healthy opener 缓解。

## Validation / Scans

本次 aggregate review 执行了以下分析：

- 读取全部 8 份 MiMo slice review + 8 份 controller adjudication + S1 fix/rereview artifacts
- 读取 R3-A plan（`wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`）确认 traceability matrix
- 跨 slice 合约一致性分析：7 个关键交互维度逐文件走读（`open_host.py`、`_durable_actor.py`、`_execution_health.py`、`dispatch.py`、`admission.py`、`waiting.py`、`wait_adapter.py`、`compaction_operation.py`、`_runner_call_manifest.py`、`interruptible_process.py`、`lane.py`）
- 测试覆盖分析：14 个关键测试文件逐函数走读，确认 cross-slice integration 路径、failure/cancel/retry/recovery/concurrency 覆盖
- 未执行：pytest 全量跑、pyright、source scan（由各 slice gate 已完成，aggregate 不重复验证）

## Conclusion

**status: pass**

8 个 slices 合并后，R3-A 的全部 accepted findings 均已 fixed（含 S1 fix gate satisfied）。跨 slice 合约边界清洁，状态机 ownership 单一来源，无 semantic ownership drift。Deferred 项均有明确 owner 且当前代码路径无 blocker 证据。测试覆盖了关键 cross-slice integration 路径与 failure/concurrency 场景。未发现实质性问题。
