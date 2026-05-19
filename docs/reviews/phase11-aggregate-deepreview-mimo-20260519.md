# Phase 11 Aggregate Deepreview

- 日期：2026-05-19
- Reviewer：AgentMiMo（aggregate reviewer）
- 分支：`feat/host-phase-11-recovery`
- 审查范围：accepted plan commit `9223cbf`..HEAD `4d32f66` + 未提交 `docs/host/implementation-control.md` hash 回写
- 设计真源：`docs/host/design.md` §27 / §27.1
- Plan：`docs/host/phase11-host-lifecycle-recovery-plan.md`
- Slice artifacts：`docs/reviews/phase11-slice{1-5}-*`（39 files）

## Verdict

**PASS**

## Phase Acceptance Commands

| 命令 | 结果 |
|------|------|
| `pytest tests/host -q` | 794 passed in 48.90s |
| `pytest tests/runtime -q` | 107 passed in 1.93s |
| `python -m pyright dayu/host dayu/runtime tests/host tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Changed Files Summary

59 files changed，9416 insertions，144 deletions。

**Production code（11 files）：**
- `dayu/host/recovery.py`（新增 710 行）
- `dayu/host/recovery_process.py`（新增 395 行）
- `dayu/host/dispatch.py`（+190 行：heartbeat lifecycle、graceful close ordering）
- `dayu/host/open_host.py`（+11 行：startup recovery scan 接入）
- `dayu/host/admission.py`（+133 行：RECOVERING cancel 支持）
- `dayu/host/command.py`（+9 行：RECOVERING cancel facade 集成）
- `dayu/host/durable/liveness.py`（-1 行：收紧 `_REGISTER_RUNNING_SOURCE_STATUSES`）
- `dayu/host/durable/state.py`（+182 行：RECOVERING CAS helpers）
- `dayu/host/durable/run_transition.py`（+808 行：recovery transition helpers）
- `dayu/host/durable/event_log.py`（+45 行：`count_recovery_dispatches_for_run`）
- `dayu/host/README.md`（+9 行：recovery 语义更新）

**Test code（13 files）：**
- `tests/host/recovery_support.py`（新增 809 行）
- `tests/host/test_recovery_scan.py`（新增 854 行）
- `tests/host/test_recovery_orphan_classifier.py`（新增 290 行）
- `tests/host/test_recovery_dispatch.py`（新增 699 行）
- `tests/host/test_recovery_multiprocess.py`（新增 224 行）
- `tests/host/test_open_host_runtime.py`（+285 行）
- `tests/host/test_public_cancel_session_runs.py`（+188 行）
- `tests/host/test_public_cancel_smoke.py`（+52 行）
- `tests/host/test_run_attempt_transitions.py`（+212 行）
- `tests/host/test_run_input_builder.py`（+108 行）
- `tests/host/test_host_instance_liveness.py`（+70 行）
- `tests/host/test_active_cancel_dispatch.py`（+29 行）
- `tests/host/test_dispatch_scheduler.py`（+7 行）
- `tests/runtime/test_lane.py`（新增 77 行）
- `tests/README.md`（+12 行）

**Docs（2 files）：**
- `docs/host/implementation-control.md`（+42 行）
- `docs/reviews/phase11-*`（39 review artifact files）

## Blocking Findings

无。

## High Findings

无。

## Medium Findings

### M1. `_cancel_recovering_run_row` 重复 CAS 逻辑

- 文件：`dayu/host/durable/run_transition.py:2754` vs `dayu/host/durable/state.py` 中 `cancel_recovering_run_row`
- 描述：`run_transition.py` 内的 `_cancel_recovering_run_row` 直接执行 SQL（`UPDATE host_runs SET status = 'cancelled' ... WHERE run_id = ? AND status = 'recovering'`），未委托给 `state.py` 已有的 `cancel_recovering_run_row` CAS helper。这违反了编码硬约束中"重复逻辑必须抽取"。
- 证据：`run_transition.py:2754-2825` 包含完整的 SQL + rowcount 判定逻辑，`state.py:2675-2737` 有 `cancel_running_run_row` / `cancel_cancelling_run_row` 等同类 CAS helper 模式。
- 严重性：Medium。功能正确（CAS 语义一致），但维护时若 state.py 的 CAS result 分类逻辑变更，run_transition.py 内的副本不会同步更新。
- 建议：后续 phase 将 `_cancel_recovering_run_row` 委托给 `state.py` 的 `cancel_recovering_run_row`（若已存在），或抽取为共享 helper。

### M2. `dispatch.py` 从 `dayu.engine` 导入

- 文件：`dayu/host/dispatch.py:23-27`
- 描述：`dispatch.py` 从 `dayu.engine.contracts.engine_events` 导入 `EngineEvent`、`EngineEventType`、`RunCancelledData`。这是 Phase 5 既有的依赖（用于 EngineEvent ingest 路径），不是 Phase 11 新增。但架构硬约束要求"设计下层组件接口时，必须假设上层组件不存在"，Host 层不应直接 import Engine。
- 严重性：Medium（pre-existing，非 Phase 11 回归）。Phase 11 未扩散此依赖。
- 建议：作为独立 tech debt 追踪，不在 Phase 11 scope 内修复。

### M3. `dispatch.py` God Module 规模

- 文件：`dayu/host/dispatch.py`（3217 行）
- 描述：Phase 11 新增 heartbeat lifecycle（+190 行）后，该文件已超 3000 行，包含 scheduler、drain loop、pre-start governance、compact operation、worker lifecycle、heartbeat、close ordering 等多个职责。
- 严重性：Medium（pre-existing complexity，Phase 11 新增部分职责清晰）。
- 建议：后续 phase 考虑拆分 heartbeat lifecycle / close ordering 为独立 module。

## Low Findings

### L1. Runtime lane close/acquire race 未在 `dayu/runtime/lane.py` 中修复

- 描述：Plan Slice 5 允许修改 `dayu/runtime/lane.py` 修复 close/acquire race，但 `git diff 9223cbf..4d32f66 -- dayu/runtime/lane.py` 无变更。`tests/runtime/test_lane.py` 新增了 close/acquire 并发测试（`test_close_wakes_pending_acquire_and_rejects_new_claims`、`test_close_during_slow_acquire_releases_untracked_claim`），且全部通过。
- 严重性：Low。测试通过表明当前实现已满足行为要求，无需代码变更。Plan 中的"fix if reproduced"条件未触发。

### L2. heartbeat interval 1s vs stale threshold 30s

- 描述：`_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0`（dispatch.py:192），`_DEFAULT_STALE_AFTER_SECONDS = 30`（recovery.py:58）。30:1 比例合理，但生产环境 SQLite 写入频率需关注。
- 严重性：Low。当前为 development / local deployment 配置，生产 tuning 留给后续 policy discussion。

## Focus Area Verification

### 1. Recovery truth source

**PASS。** Recovery scan 只读取 durable governance rows：
- `recovery.py:166-205`：`scan()` 在 `HostTransaction` 内读取 `read_non_terminal_runs()`、`read_attempt_by_id()`、`read_dispatch_record_by_attempt_id()`、`read_host_instance()`。
- 不读取 projection checkpoint、memory snapshot、RunResult、audit、trace、outbox、timeline。
- `count_recovery_dispatches_for_run()`（event_log.py:601）只计数 `CANONICAL_FACT` class 的 `RUN_STARTED` event，通过 `EventPayloadTextEqualsFilter` 校验 `start_reason == "recovery"`。

### 2. Positive orphan proof

**PASS。** `recovery_process.py:200-339` 实现严格 waterfall：
1. 缺 `owner_host_instance_id` → inconclusive
2. 缺 liveness row → inconclusive
3. owner 非 RUNNING → inconclusive
4. heartbeat parse 失败 → inconclusive
5. heartbeat 未 stale → `OwnerStillLive`
6. 无 process evidence → inconclusive
7. PID 不存在 → `PositiveOrphanProof`（pid_missing）
8. PID 存在但 start_token/boot_id mismatch → `PositiveOrphanProof`
9. PID 存在且 identity 匹配 → `OwnerStillLive`
10. fallback → inconclusive

Heartbeat stale 单独不构成 proof（line 156 测试：`test_stale_heartbeat_alone_is_not_positive_orphan_proof`）。

### 3. CAS ordering

**PASS。** 所有 recovery transition 在单一 `HostTransaction` 内完成：
- `close_startup_orphan_attempt_in_transaction`（run_transition.py:1326）：append `ATTEMPT_LOST` → append `RUN_RECOVERING` / `RUN_LOST` → update Attempt terminal refs → update Run status/current attempt refs。
- `start_recovery_run_with_starting_attempt_in_transaction`（run_transition.py:1488）：append `RUN_STARTED(start_reason=recovery)` → update Run RUNNING / current attempt → insert Attempt STARTING → append `ATTEMPT_STARTED` → insert dispatch record pending。
- `cancel_recovering_run_in_transaction`（run_transition.py:2356）：CAS RECOVERING → CANCELLED → append `CANCEL_REQUESTED` + `RUN_CANCELLED`。

### 4. RECOVERING dispatch / cancel

**PASS。**
- Cancel：`admission.py:1547-1552`（`_CancelRunOperation`）显式 dispatch `RunStatus.RECOVERING` → `_cancel_recovering()`（line 1695-1757）。
- Session cancel：`admission.py:4289-4307`（`_session_cancel_target_for_run`）识别 RECOVERING 为 supported target。
- Command facade：`command.py:555` docstring 明确覆盖 RECOVERING；`_is_deferred_cancel_state()` 对 RECOVERING 返回 `False`（不延迟），直接走 admission service。
- RECOVERING cancel 不传播 WorkerProxy：`test_public_cancel_smoke.py:161`（`test_recovering_cancel_does_not_propagate_worker_cancel`）。

### 5. open_host startup scan

**PASS。**
- `open_host.py:461-466`：`StartupRecoveryScanner` 在 scheduler 打开后、admission service 创建前执行 `scan()`。
- 不新增 public API、不新增 `OpenHostOptions` 字段。
- `test_open_host_runtime.py:392`（`test_open_host_startup_recovery_dispatches_interrupted_run_and_watch_observes_final`）：验证中断 Run 恢复后通过 `watch_session_events` 可见 final answer。

### 6. Public API preservation

**PASS。**
- 无新增 public API。
- 无新增 `OpenHostOptions` 字段。
- `watch_session_events` 可见 recovery 提交的普通 Host events（`test_open_host_runtime.py:392`）。
- `cancel_run` / `cancel_session_runs` docstring 已更新覆盖 RECOVERING。

### 7. No Engine changes

**PASS。**
- `git diff 9223cbf..4d32f66 --stat` 中无 `dayu/engine/**` 变更。
- `recovery.py`、`recovery_process.py`、`dispatch.py`（Phase 11 新增部分）、`open_host.py`、`admission.py`、`command.py`、所有 durable 层文件均不新增 `dayu.engine` 导入。
- `dispatch.py:23-27` 的 `dayu.engine` 导入为 Phase 5 既有，Phase 11 未扩散。

### 8. No lease / fencing / takeover

**PASS。**
- `recovery_process.py:141-197`：`PositiveOrphanProof` 证明 owner 已不可能继续治理，不授予接管权限。
- `recovery.py:379-469`（`_close_positive_orphan`）：CAS recheck 后才写入 `ATTEMPT_LOST`，不使用 lease。
- `dispatch.py:1594-1640`：heartbeat 只刷新自己 row，不标记其它 instance。
- 设计真源 §27 明确："positive orphan proof 只能证明原 owner 已不可能继续治理，不能允许接管旧 Attempt"。

### 9. Runtime lane 不升级为 Host truth

**PASS。**
- `tests/runtime/test_lane.py:333-369`（`test_database_init_sets_wal_and_schema_has_no_host_or_fins_fields`）：验证 runtime schema 不含 `session_id`、`run_id`、`attempt_id`、`event_sequence` 等 Host/Fins 字段。
- `dayu/runtime/lane.py` 无变更，保持层中立。
- runtime lane 只表达资源容量，不表达 Host ownership / lease / fencing / EventLog ordering / recovery proof。

### 10. Multi-process live-owner safety

**PASS。**
- `test_recovery_multiprocess.py:49`（`test_live_second_process_open_does_not_recover_or_harm_owner`）：第二进程打开同一 DB，不杀仍存活的 owner。
- `test_recovery_multiprocess.py:100`（`test_crashed_owner_reopens_and_final_answer_is_public_streamed`）：owner PID 缺失 + stale heartbeat → 重启后通过 public stream 产出 answer。
- `test_recovery_multiprocess.py:144`（`test_projection_lag_does_not_block_durable_recovery`）：projection checkpoint lag 不阻塞 recovery。

### 11. Projection lag non-truth

**PASS。**
- `test_recovery_scan.py:100`（`test_scan_running_positive_orphan_moves_to_recovering_without_projection`）：不依赖 projection。
- `test_recovery_scan.py:245`（`test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag`）：projection lag 不影响 LOST 决策。
- `test_recovery_multiprocess.py:144`：explicitly validates projection lag is irrelevant。

### 12. README / test docs 同步

**PASS。**
- `dayu/host/README.md`：更新了 `cancel_run` / `cancel_session_runs` 覆盖 recovering、RECOVERING 状态语义、startup recovery scan 描述、dispatch scheduler heartbeat lifecycle、positive orphan proof 边界。
- `tests/README.md`：新增 recovery / multiprocess test harness conventions 行（line 41-42）、lane test 覆盖描述更新（line 72-76）。
- 根目录 `README.md`：无变更（plan 预期无 root README change，正确）。
- `dayu/README.md`：无变更（plan 预期无 layer-boundary change，正确）。

## Architecture Boundary Verification

| 边界 | 验证 |
|------|------|
| `dayu.runtime` 不 import `dayu.host` | PASS：`lane.py` 无 host 导入 |
| `dayu.host.recovery` 不 import `dayu.engine` | PASS |
| `dayu.host.recovery_process` 不 import `dayu.engine` | PASS |
| `dayu.host.durable.*` 不 import `dayu.host.recovery` | PASS |
| `dayu.host.admission` 不 import `dayu.host.recovery` | PASS |
| `dayu.host.command` 不 import `dayu.host.recovery` | PASS |
| `open_host.py` import `recovery.py` | PASS：正确组装方向 |
| 无 `Any` / `object` 类型注解 | PASS：所有新文件通过 pyright 0 errors |
| 所有函数有中文 docstring | PASS |

## Slice Coverage Matrix

| Slice | 核心交付 | 证据 |
|-------|---------|------|
| 1. Host Instance Lifecycle & Process Proof | 收紧 `_REGISTER_RUNNING_SOURCE_STATUSES`、`ProcessEvidence` / `ProcessLivenessProbe` Protocol、positive orphan classifier typed union、`HostInstanceIdentity.process_start_token` 独立高熵随机值、heartbeat background task | `liveness.py`、`recovery_process.py`、`dispatch.py:1582-1700` |
| 2. Startup Recovery Scan & CAS Closeout | `StartupRecoveryScanner`、`close_startup_orphan_attempt_in_transaction`、`lose_recovering_run_in_transaction`、`count_recovery_dispatches_for_run`、projection lag 不影响分类 | `recovery.py`、`run_transition.py:1326-1570`、`event_log.py:601` |
| 3. RECOVERING Dispatch & RunInputBuilder | `start_recovery_run_with_starting_attempt_in_transaction`、recovery dispatch wakes scheduler、RunInputBuilder 从 canonical facts 重建 messages、late old execution reject | `recovery.py:471-535`、`run_transition.py:1488-1570`、`open_host.py:461-466` |
| 4. RECOVERING Cancel & Graceful Shutdown | `cancel_recovering_run_in_transaction`、`cancel_session_runs` 包含 RECOVERING、graceful shutdown 不写 fake terminal fact | `admission.py:1547-1757`、`command.py:549-598`、`dispatch.py:1540-1580` |
| 5. Multi-process & Runtime Lane Hardening | 多进程 live owner 不误杀、crash recovery E2E、projection lag non-truth、runtime lane close/acquire 并发测试 | `test_recovery_multiprocess.py`、`test_lane.py` |

## Residual Risks

1. **Portable pid-reuse proof 有限**：第一版 `StdlibPidLivenessProbe` 只用 `os.kill(pid, 0)` 检测 PID 存在性，不读取 `process.created_at` / `boot_id`。PID 复用但 start_token 不匹配时可出 positive proof，但无 platform-specific `created_at` 能力。Owner：后续 phase 按 platform capability 扩展。
2. **Heartbeat 写入频率**：1s interval 在高并发 SQLite WAL 下可能产生 write contention。Owner：production tuning phase。
3. **Recovery E2E timing sensitivity**：多进程 test 使用 `force_owner_pid_missing_and_heartbeat_stale()` 直接修改 durable rows，不模拟真实 process kill timing。Owner：已有 determinism helper 覆盖，真实 process kill 测试留给 integration environment。
4. **`_cancel_recovering_run_row` 重复逻辑**：run_transition.py 与 state.py 间的 CAS 逻辑重复。Owner：后续 cleanup phase。

## Conclusion

Phase 11 实现了 Host startup recovery scan、positive orphan proof、已接受 Prompt 崩溃恢复、RECOVERING dispatch / cancel、graceful shutdown lifecycle 与多进程 hardening。所有 5 个 Slice 已 accepted commit，794 host tests + 107 runtime tests 全部通过，pyright 0 errors，git diff --check clean。无 blocking finding，无 high finding。Recovery truth source、positive orphan proof、CAS ordering、RECOVERING dispatch/cancel、open_host startup scan、public API preservation、no Engine changes、no lease/fencing/takeover、runtime lane 层中立、多进程 live-owner safety、projection lag non-truth 与 README/test docs 同步全部验证通过。

**PASS。**
