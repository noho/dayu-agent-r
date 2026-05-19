# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase-11-recovery`
- Base: `9223cbf` (accepted plan commit; HEAD 等于 base，所有变更均处于未暂存工作区)
- Output file: `docs/reviews/phase11-slice1-code-review-mimo-20260519.md`
- Included scope: Phase 11 Slice 1 全部允许文件的未提交工作区变更
  - `dayu/host/durable/liveness.py`（修改）
  - `dayu/host/recovery_process.py`（新增）
  - `dayu/host/dispatch.py`（修改）
  - `tests/host/test_host_instance_liveness.py`（修改）
  - `tests/host/test_recovery_orphan_classifier.py`（新增）
  - `dayu/host/README.md`（修改）
- Excluded scope: `docs/host/implementation-control.md`（实现前已存在的外部未提交变更，非本次 slice 产物）；`docs/reviews/phase11-slice1-implementation-codex-20260519.md`（实现 artifact，非生产代码）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Verification Detail

### 1. Lifecycle 收紧：STOPPING 不能回刷为 RUNNING

- `_REGISTER_RUNNING_SOURCE_STATUSES` 已收紧为仅 `(HostInstanceStatus.RUNNING,)`（`liveness.py:42-44`）。
- `register_current_instance` 在 existing row 存在时，先检查 `_TERMINAL_STATUSES`（`STOPPED`, `CRASHED_SUSPECTED`），再尝试 UPDATE WHERE `status IN (RUNNING)`。`STOPPING` 不在允许来源内，UPDATE 零命中后由 `_raise_liveness_update_conflict` 分类为 `HostInstanceLifecycleConflictError`。
- 测试 `test_stopping_instance_register_does_not_revert_to_running` 直接验证此行为，并确认 row 状态仍为 `STOPPING`。
- 测试 `test_stopping_instance_heartbeat_does_not_revert_to_running` 验证 heartbeat 同样拒绝 `STOPPING` 状态。
- 测试 `test_terminal_instance_does_not_revert_to_running_or_stopping` 参数化覆盖 `STOPPED` 和 `CRASHED_SUSPECTED` 终态。

### 2. process_start_token 高熵且独立

- `_new_dispatch_host_instance_identity`（`dispatch.py:3111-3128`）使用 `uuid4().hex` 生成 32 字符十六进制 token，与 `host_instance_id`（即 `host_handle_id`）分开生成。
- 不使用 timestamp、handle id、pid 或其派生值。
- 测试 `test_dispatch_host_instance_identity_uses_high_entropy_token` 验证：token 不等于 host_instance_id、不等于旧格式 `dispatch-{id}`、两次调用产出不同 token、长度为 32、合法十六进制。

### 3. Heartbeat task 生命周期与失败行为

- `HostDispatchScheduler.open` 在 register 后调用 `_start_host_instance_heartbeat()`（`dispatch.py:601`），创建后台 asyncio task。
- 心跳间隔为 `_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0`（`dispatch.py:192`），远小于 recovery stale threshold（测试中使用 30s）。
- 正常 refresh 失败（`HostTransactionRetryExhaustedError`）记录 warning 后继续下一轮重试（`dispatch.py:1599-1609`）。
- fatal exit（其他异常）记录 structured error 后 best-effort 标记当前 scheduler 自己的 instance 为 `STOPPING`，然后 return（`dispatch.py:1610-1622`）。
- close 先 mark stopping，再 cancel heartbeat/drain/promotion tasks，再 cancel active workers，再 close lane，最后 mark stopped（`dispatch.py:1540-1571`）。
- `_best_effort_mark_host_instance_stopping` 和 `_best_effort_mark_host_instance_stopped` 均 catch 所有异常并记录 warning，不阻断 close 流程（`dispatch.py:1645-1691`）。

### 4. Orphan classifier 真源与 typed 输出

- `recovery_process.py` 是只读模块：不扫描 durable store、不写数据库、不推进 Run/Attempt 状态。
- 输入为 `DurableOrphanCandidate`（durable owner + liveness row）+ `ProcessEvidence`（进程探测）+ `OrphanClassificationPolicy`（时间策略）。
- 输出为 typed union：`PositiveOrphanProof | OwnerStillLive | OrphanProofInconclusive`。
- 分类逻辑严格按证据链走：missing owner -> inconclusive；missing liveness -> inconclusive；owner not RUNNING -> inconclusive；heartbeat parse failed -> inconclusive；heartbeat recent -> still live；heartbeat stale + pid missing -> positive；heartbeat stale + pid exists + start token mismatch -> positive；heartbeat stale + pid exists + boot id mismatch -> positive；heartbeat stale + pid exists + identity matched -> still live；heartbeat stale + pid exists + no identity proof -> inconclusive。
- 测试覆盖全部 10 个分类路径，加上 `StdlibPidLivenessProbe` 的存在性检查和无效 pid 拒绝。

### 5. Classifier 不写 DB

- `classify_orphan_candidate` 不接收 `HostTransaction`、`HostTransactionRunner` 或任何写入端口。
- 函数签名只接受 `DurableOrphanCandidate`、`ProcessEvidence | None`、`OrphanClassificationPolicy`，返回 `OrphanClassification`。
- 模块内无 `execute`、`INSERT`、`UPDATE`、`DELETE` 或任何持久化调用。

### 6. 无 Engine / public API / schema 变更

- `recovery_process.py` 只导入 `dayu.host.durable.codec` 和 `dayu.host.durable.liveness`，不导入 `dayu.engine`。
- `dispatch.py` 的 `dayu.engine.contracts.engine_events` 导入为既有依赖，非本次新增。
- 无新增 public API、public `OpenHostOptions` 字段或 schema 字段。
- `recovery_process.py` 不修改 `TABLE_HOST_INSTANCES` schema，只通过 liveness 模块读取既有 row。

### 7. 测试充分性

- `test_host_instance_liveness.py`：17 个测试，覆盖 register/heartbeat lifecycle、identity conflict、identity drift race、boot_id tolerance、mark stopping/stopped、dispatch identity generation。
- `test_recovery_orphan_classifier.py`：13 个测试，覆盖全部 orphan classification 路径和 `StdlibPidLivenessProbe`。
- 实现 artifact 报告 `30 passed in 0.40s`。
- pyright `0 errors, 0 warnings, 0 informations`。

### 8. Docstring / 类型约束

- `recovery_process.py` 所有 public 和 private 函数/类均有完整中文 docstring，包含 `:param`、`:returns`、`:raises`。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `ProcessLivenessProbe` 使用 `typing.Protocol`，不使用 `object`。
- `OrphanClassification` 使用 `typing.TypeAlias`，不使用 `Any`。

### 9. README 同步

- `dayu/host/README.md` Dispatch 路径段新增 Host instance liveness heartbeat、高熵 process token、只读 orphan classifier 语义说明。
- 更新范围限于 Slice 1 已实现内容，不记录 startup recovery scan、CAS closeout 或 recovery dispatch。

## Open Questions

无。

## Residual Risk

- `docs/host/implementation-control.md` 存在实现前已有的外部未提交变更，与本次 slice 无关，需在后续 commit 管理中注意隔离。
- Slice 1 不覆盖 startup recovery scan、CAS closeout、recovery dispatch、RECOVERING cancel、graceful shutdown（Slice 2-4 owner）。
- stdlib pid probe 只能证明 pid 存在/不存在，不能证明 pid 复用后的启动指纹 mismatch；classifier 支持该能力但本 slice 不添加平台特定进程指纹探测。
