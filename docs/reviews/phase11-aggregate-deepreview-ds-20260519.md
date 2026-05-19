# Phase 11 Aggregate Deepreview / Phase Acceptance Validation — AgentDS — 2026-05-20

## Verdict: PASS — BLOCKING COUNT = 0

Phase 11 从 accepted plan commit `9223cbf` 到 HEAD `4d32f66` 的 5 个 Slice 全部通过深度审查。所有验证命令通过。无 blocking finding。Phase acceptance 条件满足。

---

## 1. Review Scope

- **设计真源**: `docs/host/design.md` §27 / §27.1
- **实施真源**: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- **审查区间**: `9223cbf` (accepted plan) → `4d32f66` (HEAD, Slice 5 accepted)
- **未提交变更**: `docs/host/implementation-control.md` gate 状态 hash 回写（纯文档追踪更新，无生产代码）
- **Slice 实现与 review artifacts**: `docs/reviews/phase11-slice[1-5]-*` 共 34 个文件，每 slice 均经 implementation → MiMo/DS code review → controller adjudication → 必要时 fix → re-review → re-adjudication
- **审查角色**: AgentDS，strict aggregate reviewer，不修改文件、不提交

---

## 2. 验证命令结果

| 命令 | 结果 | 证据 |
|------|------|------|
| `pytest tests/host -q` | **793 passed, 1 skipped** | 47.21s，零失败 |
| `pytest tests/runtime -q` | **107 passed** | 1.93s，零失败 |
| `python -m pyright dayu/host dayu/runtime tests/host tests/runtime` | **0 errors, 0 warnings, 0 informations** | 全量 type clean |
| `git diff --check` | **clean** | 无空白/冲突标记问题 |

---

## 3. Recovery Truth Source 审查（§27 / Plan §27）

### 3.1 Durable truth 作为唯一真源 ✓

实现证据链:

- `dayu/host/recovery.py:188`: `read_non_terminal_runs(transaction)` — 读取 durable `host_runs` 表
- `dayu/host/recovery.py:583-587`: `read_attempt_by_id` + `read_dispatch_record_by_attempt_id` — 读取 durable `host_attempts` / `host_attempt_dispatch_records` 表
- `dayu/host/recovery.py:365`: `read_host_instance` — 读取 durable `host_instances` 表
- `dayu/host/recovery.py:264-265`: `self.event_log_store.count_recovery_dispatches_for_run(transaction, ...)` — 读取 canonical EventLog `RUN_STARTED` + payload `start_reason=recovery`

**未读取 projection / read-model / memory snapshot / audit / trace / outbox / timeline / RunResult**。`StartupRecoveryScanner` 的 scan 方法直接通过 `transaction_runner.run_write(operation)` 执行，内部只操作 durable state、EventLog 和 liveness primitive。

- `dayu/host/durable/event_log.py:601-626`: `count_recovery_dispatches_for_run` 只通过 `count_committed_events_by_run_and_type` 读取 canonical EventLog，按 `event_type="RUN_STARTED"` 和 `payload.start_reason == "recovery"` 过滤；不读取 projection / read-model / diagnostic events / 非 canonical payload 文本匹配。

### 3.2 Positive orphan proof 边界 ✓

`dayu/host/recovery_process.py:200-339` `classify_orphan_candidate` 分类逻辑:

1. `owner_host_instance_id` 缺失 → `OrphanProofInconclusive(reason="missing_owner_host_instance_id")` (行 216-222)
2. `owner_liveness` 为 None → `OrphanProofInconclusive(reason="missing_owner_liveness_row")` (行 223-230)
3. `row.status is not RUNNING` → `OrphanProofInconclusive` (行 232-239)
4. `heartbeat_at` 解析失败 → `OrphanProofInconclusive` (行 243-249)
5. `policy.now - heartbeat_at <= stale_after` → `OwnerStillLive` (行 250-256)
6. `evidence is None` → `OrphanProofInconclusive` (行 274-281)
7. `evidence.pid != row.pid` → `OrphanProofInconclusive` (行 282-289)
8. `evidence.probe_error_code is not None` → `OrphanProofInconclusive` (行 290-297)
9. `not evidence.exists` → `PositiveOrphanProof(reason="owner_pid_missing")` (行 298-304)
10. `observed_start_token mismatch` → `PositiveOrphanProof` (行 305-314)
11. `observed_boot_id mismatch` → `PositiveOrphanProof` (行 315-325)
12. `observed_start_token == row.process_start_token` → `OwnerStillLive(reason="owner_process_identity_matched")` (行 326-332)
13. 剩余情况 → `OrphanProofInconclusive(reason="pid_live_without_identity_proof")` (行 333-339)

**判决**: heartbeat stale 单独不构成 positive proof（必须同时满足 heartbeat stale + pid missing 或启动指纹 mismatch）；pid 单独不构成 positive proof（pid live 但指纹缺失 → inconclusive）；classifier 只读，不写数据库。

### 3.3 CAS ordering ✓

`dayu/host/durable/run_transition.py:1326` `close_startup_orphan_attempt_in_transaction`:

- **Recoverable 路径**: 同一 write transaction 内依次 append `ATTEMPT_LOST` → `RUN_RECOVERING`，并同事务更新 Attempt terminal refs、Run status / current attempt refs
- **Unrecoverable 路径**: 同一 write transaction 内依次 append `ATTEMPT_LOST` → `RUN_LOST`

`dayu/host/durable/run_transition.py:1488` `start_recovery_run_with_starting_attempt_in_transaction`:

- 同一 write transaction 内 append `RUN_STARTED(start_reason=recovery)` → 更新 Run `RUNNING` / current Attempt → insert new Attempt `STARTING` → append `ATTEMPT_STARTED` → insert dispatch record `pending`

`dayu/host/recovery.py:410-437` `_close_positive_orphan` 在 `close_startup_orphan_attempt_in_transaction` 的 CAS recheck 中传递 `expected_run_status`、`expected_attempt_status`、`expected_dispatch_status`、`owner_heartbeat_at`、`stale_after` 等完整 recheck 参数，满足 design §27 的 CAS recheck 要求。

### 3.4 RECOVERING dispatch ✓

`dayu/host/recovery.py:471-534` `_start_recovery_dispatch_or_ready`:

- 创建新 `attempt_id`、`execution_id`、`dispatch_record_id`（高熵 uuid4.hex 前缀）
- 调用 `start_recovery_run_with_starting_attempt_in_transaction` 提交 `RUN_STARTED(start_reason=recovery)` + `ATTEMPT_STARTED` + pending dispatch record
- 事务提交后通过 `dispatch_wakeup_port.wake_dispatch(pending_dispatch)` 唤醒 scheduler（`recovery.py:203-205`）
- 不直接调用 WorkerProxy

`dayu/host/open_host.py:461-466` 确认 `StartupRecoveryScanner` 在 `scheduler` 打开后、`admission_service` 创建前执行 scan，dispatch_wakeup_port 传入 scheduler。scan 在 `__aenter__` 返回 ready public handle 前完成。

### 3.5 RECOVERING cancel ✓

`dayu/host/admission.py:1695-1757` `_cancel_recovering`:

- 对于 `RECOVERING` 状态 Run，调用 `cancel_recovering_run_in_transaction` 直接 append `CANCEL_REQUESTED` + `RUN_CANCELLED`
- 不创建 Attempt terminal
- 不传播 WorkerProxy cancel (`active_cancel_target=None`)
- 记录幂等（`idempotency_store.record_idempotent_result`）

`dayu/host/command.py:555` `cancel_run` docstring: "当前覆盖 queued、pre-dispatch `STARTING`、pre-accept dispatching、active worker、`WAITING` 与 `RECOVERING`。"

`dayu/host/command.py:610` `cancel_session_runs` docstring: "当前覆盖 queued、pre-dispatch `STARTING`、pre-accept dispatching、active worker、`WAITING` 与 `RECOVERING`。"

### 3.6 open_host startup scan ✓

`dayu/host/open_host.py:461-466`:

```python
StartupRecoveryScanner(
    transaction_runner=durable_store.transaction_runner,
    event_log_store=EventLogStore(),
    dispatch_wakeup_port=scheduler,
    recovery_owner_host_instance_id=scheduler.host_instance_id,
).scan()
```

scan 在 scheduler 打开后、admission service 创建前、ready log 之前执行。Service 不需要调用额外 recovery command。

---

## 4. Public API Preservation ✓

| 检查项 | 结果 |
|--------|------|
| `open_host(options)` 签名 | 未变；返回 `AbstractAsyncContextManager[Host]` |
| `OpenHostOptions` 字段 | 无新增/删除/语义变更 |
| `Host` public handle methods | 未变；`cancel_run`/`cancel_session_runs` 扩展覆盖 RECOVERING 但不改变调用签名 |
| `watch_session_events` contract | 未变；仍返回 `AsyncIterator[HostEvent]` |
| 新增 public recovery command | 无 |
| 新增 public recovery policy option | 无 |
| 新增 alternate startup API | 无 |
| Service 接入方式 | 同一 `open_host` → session acquisition → public commands → `watch_session_events` 流程 |

`git diff 9223cbf..HEAD -- dayu/host/api/ dayu/host/__init__.py` 确认零变更。

---

## 5. No Engine Changes ✓

`git log 9223cbf..HEAD -- dayu/engine/ --oneline` 输出空行。五个 Slice 均未修改 `dayu/engine/` 任何文件。

commit 级别的文件变更确认:
- Slice 1: `dayu/host/` 4 files, `tests/host/` 2 files
- Slice 2: `dayu/host/` 3 files (+ new recovery.py), `tests/host/` 2 files
- Slice 3: `dayu/host/` 4 files, `tests/host/` 4 files
- Slice 4: `dayu/host/` 4 files, `tests/host/` 4 files
- Slice 5: `tests/host/` 4 files (+ new recovery_support.py), `tests/runtime/` 1 file

总计 `dayu/host/` 触及 7 个模块，`dayu/runtime/` 触及 1 个模块 (lane.py)，`dayu/engine/` 零变更。

---

## 6. No Lease / Fencing / Takeover ✓

`dayu/host/durable/liveness.py:1-6` 模块 docstring:

> "这些 row 是后续 recovery 的输入之一，但本模块不实现 lease、fencing、takeover、dispatch join、orphan classifier、Attempt LOST 或 Run RECOVERING。"

`dayu/host/dispatch.py:7-8` 模块 docstring:

> "`dispatching` 与 lane token 只作为诊断和容量控制，不表达 owner truth、lease、fencing 或 takeover proof。"

`dayu/host/dispatch.py:1582-1649` heartbeat loop:
- 只刷新当前 scheduler 自己的 `host_instance_id` row
- 不刷新其它 instance 的 heartbeat
- 不因 heartbeat stale 自动标记其它 instance 的 Attempt 为 LOST
- fatal exit 只 `best_effort_mark_host_instance_stopping` 当前自己的 row

`dayu/host/dispatch.py:3135` process_start_token 使用 `uuid4().hex`（高熵随机），不再是旧版可预测占位 `dispatch-{host_handle_id}`。

---

## 7. Runtime Lane 不升级为 Host Truth ✓

`dayu/runtime/lane.py:4-5`:

> "它只表达运行期资源容量 claim，不表达 Host durable truth、lease / fencing、Attempt owner、EventLog ordering、admission 或 recovery proof。"

`grep "from dayu\.(host|engine|service|fins)" dayu/runtime/lane.py` 输出空行 — 零 Host/Engine/Service/Fins 依赖。

`dayu/runtime/lane.py:524-532` `LaneController.close()`:
- 设置 `_closed = True`
- 设置 `_close_reason`
- wake pending acquire（通过 `_claim_changed.set()`）
- 新 acquire 请求收到 `LaneAcquireCancelled`

`dayu/runtime/lane.py:476-492` acquire 路径:
- 在 `_closed` 检查后返回 `LaneAcquireCancelled`

---

## 8. Multi-process Live-owner Safety ✓

`tests/host/test_recovery_multiprocess.py:49-96` `test_live_second_process_open_does_not_recover_or_harm_owner`:

证据链（引用自 DS Slice 5 code review）:
1. Owner 进程存活且持有 active Attempt
2. Probe 进程（不同 pid）打开同一 DB → 正常退出 (exitcode=0)
3. Owner 进程仍存活
4. EventLog 中无 `ATTEMPT_LOST`
5. EventLog 中无 `RUN_RECOVERING`
6. Attempt 数仍为 1
7. `current_attempt_id` 未被替换

`tests/host/test_recovery_multiprocess.py:99-140` `test_crashed_owner_reopens_and_final_answer_is_public_streamed`:

证据链:
1. Owner 崩溃（terminated pid + stale heartbeat）
2. Recovery 通过 public `open_host(options)` 打开
3. 通过 public `watch_session_events` 获得 terminal HostEvent
4. `terminal.kind is HostEventKind.SUCCEEDED`
5. `terminal.final_answer.content == f"recovered-final:{run_id}"`
6. Public `RunSnapshot` 为 `RunStatus.SUCCEEDED`
7. 新 Attempt id ≠ 旧 Attempt id

---

## 9. Projection Lag Non-truth ✓

`dayu/host/recovery.py:8-9`:

> "它不实现 public API、不直接调用 WorkerProxy，也不读取 projection/read-model。"

实现中所有 scanner 读取均通过 `transaction` 下的 `read_non_terminal_runs`、`read_attempt_by_id`、`read_dispatch_record_by_attempt_id`、`read_host_instance`、`EventLogStore.count_recovery_dispatches_for_run` 完成 — 全部是 durable 真源读取。

`docs/reviews/phase11-slice2-code-review-ds-20260519.md` 确认 Slice 2 测试中 projection 被 disable/lag 后 recovery decision 仍基于 EventLog / state rows。

`docs/reviews/phase11-slice5-code-review-ds-20260519.md` Slice 5 multi-process tests 中 `event_type_count`、`attempt_count_for_run`、`current_attempt_id_for_run` 全部读自 durable 表 (`event_log`、`host_attempts`、`host_runs`)，不经过 projection/read-model。

---

## 10. Host Instance Lifecycle 收紧 ✓

`dayu/host/durable/liveness.py:42-44`:

```python
_REGISTER_RUNNING_SOURCE_STATUSES = (
    HostInstanceStatus.RUNNING,
)
```

旧版 `_REGISTER_RUNNING_SOURCE_STATUSES` 含 `STOPPING` 的宽松行为已收紧。重复 `register_current_instance` 对 `STOPPING`/`STOPPED`/`CRASHED_SUSPECTED` 抛出 `HostInstanceLifecycleConflictError`。

Heartbeat source status 限制为仅 `RUNNING` (行 45)。Stopping/stopped 标记 source status 正确约束。

---

## 11. Graceful Shutdown vs Cancel 区分 ✓

`dayu/host/open_host.py:363-390` `_PublicHostHandle.close()`:

1. 先设置 `_closed = True` 拒绝新 public 操作
2. `await self._scheduler.close()` — 停止 promotion/dispatch/lane waits/active worker tasks，mark host instance stopping/stopped best-effort
3. projection catch-up best-effort flush
4. command handle close

关闭路径不 append `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED`、`RUN_LOST` 或伪造 terminal fact。

---

## 12. README / Test Docs 同步 ✓

| 文件 | 变更 | 评估 |
|------|------|------|
| `dayu/host/README.md` | 新增 recovery semantics、positive orphan proof 边界、graceful shutdown vs cancel 区分、RECOVERING canceled `CANCELLED` 说明 | 符合 `dayu/host/` 修改触发 `dayu/host/README.md` 更新规则 |
| `tests/README.md` | 新增 recovery multiprocess 运行命令、lane race 测试范围描述 | 符合 `tests/` 修改触发 `tests/README.md` 更新规则 |
| `dayu/README.md` | 未变更 | 符合预期（未改变分层边界） |
| 根 `README.md` | 未变更 | 符合预期（无 CLI/command usage 变化） |

---

## 13. 未提交变更审查

`git diff docs/host/implementation-control.md`:

```diff
-当前 gate：Phase 11 Slice 5 accepted local commit。
-下一 gate：Phase 11 aggregate deepreview / phase acceptance validation。
+当前 gate：Phase 11 aggregate deepreview / phase acceptance validation。
+下一 gate：Phase 11 aggregate deepreview adjudication / fix decision。
...
+当前 gate 追加事实（Phase 11 Slice 5 accepted commit）：Accepted Slice 5 local
+commit hash 为 `4d32f66`。Controller 追加 phase acceptance validation：
+`pytest tests/runtime -q` 107 passed。当前进入 Phase 11 aggregate deepreview /
+phase acceptance validation。
```

纯 gate 状态追踪更新；不修改设计、不引入新约束、不含生产代码。**可安全提交。**

---

## 14. Findings

### Blocking (0)

无。

### High (0)

无。

### Medium (1)

**M1. Heartbeat interval 硬编码 1.0s vs stale_after 30s 关系未文档化**

- 文件: `dayu/host/dispatch.py`
- 证据: `_host_instance_heartbeat_loop` 使用 `self._lane_heartbeat_interval_seconds`，该值来自 `HostLocalExecutionOptions.lane_heartbeat_interval_seconds`，默认值在 HostLocalExecutionOptions 中定义；`_DEFAULT_STALE_AFTER_SECONDS = 30` 在 `dayu/host/recovery.py:58`
- 判定: heartbeat 周期 < stale 阈值的约束成立（1s < 30s），但两者的耦合关系未在任何内部 docstring 或模块级注释中说明。这不影响 correctness，但后续调参时可能误调 heartbeat 大于 stale 导致误判。
- 建议: 在 `recovery.py` `_DEFAULT_STALE_AFTER_SECONDS` 附近或 dispatch.py heartbeat 函数中添加注释说明 ratio constraint。
- 归属: Phase 11 后续可调参时处理。

### Low (2)

**L1. StdlibPidLivenessProbe 的 platform-specific evidence 有限**

- 文件: `dayu/host/recovery_process.py:69-114`
- 证据: `StdlibPidLivenessProbe` 的 `observed_start_token` 与 `observed_boot_id` 始终为 `None`。这意味着当前 portable probe 只能通过 pid missing 获得 positive proof；pid reused mismatch 与 boot_id mismatch 在 stdlib probe 上不可达。
- 判定: Plan 已将此标记为 deferred / non-blocking risk ("Portable pid-reuse proof is limited. First version should only produce positive proof for pid-missing unless platform process start evidence is directly available.")。Classifier 正确处理了 `observed_start_token is None` 和 `observed_boot_id is None` 的分支，pid live 且无指纹时返回 inconclusive。**不阻塞。**
- 归属: 后续平台级 probe 增强时处理。

**L2. WAITING recovery 完全是 diagnostic-only**

- 文件: `dayu/host/recovery.py:232-236`
- 证据: WAITING Run 分类为 `WAITING_DIAGNOSTIC_ONLY`，reason 固定为 `"waiting_adapter_observation_unavailable"`。不创建 Attempt，不推进状态，不恢复 wait observation。
- 判定: Plan §Slice 2 明确要求 WAITING recovery 若 adapter observation 不可用则走 diagnostic-only fallback，记录 structured diagnostic log 或 `event_class=diagnostic` EventLog。当前实现只产出 scan action reason 字符串；diagnostic EventLog 写入未实现。**但由于当前 phase 的 WAITING recovery 在 design doc §27 中已有明确语义为"不创建 Attempt"且 plan 将"watch polling performance" deferred 到后续 phase，该 gap 不构成 blocking。**
- 归属: 后续 public lifecycle hardening / production watch scale owner。

---

## 15. Residual Risks

| 风险 | 归属 | 性质 |
|------|------|------|
| Stdlib probe 不支持 pid reuse proof | 后续平台 probe 增强 | 已知，plan deferred |
| Heartbeat interval / stale_after 比例说明缺失 | Phase 11 可调参 | Medium finding M1 |
| WAITING diagnostic-only 未写 structured diagnostic EventLog | 后续 public lifecycle | Low finding L2 |
| 生产 stale threshold 调优需求 | 后续 production tuning | 已知，plan deferred |
| Watch polling performance (20ms) | Phase 11 后续 / production watch scale | 已知，plan deferred |
| Watcher close 行为变更 (`HostClosedError`) | 后续 public lifecycle | 已知，plan deferred |

---

## 16. Phase Acceptance Decision

**PASS — Phase 11 aggregate deepreview 通过，blocking count = 0。**

验证总结：
- 5 个 Slice 逐 slice 通过 code review + controller adjudication
- Phase acceptance 命令全部通过：host tests 793 passed, runtime tests 107 passed, pyright 0 errors, git diff --check clean
- Recovery truth source 完全来自 durable EventLog / Run / Attempt / dispatch / liveness rows
- Positive orphan proof 最小判定条件正确实现且不可绕过
- CAS ordering 在 write transaction 内保证 EventLog append → state row update 同事务
- RECOVERING dispatch 通过 scheduler wake 而非直接 WorkerProxy
- RECOVERING cancel 正确支持，cancel_session_runs 覆盖 RECOVERING
- Graceful shutdown 不伪造 terminal facts
- Public API 零变更
- Engine 零变更
- 无 lease / fencing / takeover
- Runtime lane 未升级为 Host truth
- 多进程 live-owner 不被误杀证明成立
- Crash recovery 通过 public event stream 可见证明成立
- Projection lag 不影响 recovery decision 证明成立
- README 同步正确

下一 gate: Controller 进入 Phase 11 aggregate deepreview adjudication / fix decision，随后可推进到 ready-to-open-draft-PR。
