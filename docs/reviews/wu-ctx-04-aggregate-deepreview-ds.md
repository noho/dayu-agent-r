# WU-CTX-04 Aggregate Deepreview

## Scope

- Mode: current changes（相对 main merge baseline 的完整 WU diff）
- Branch: `feat/wu-ctx-04`
- Base: `974f9e1686f6e26f96830cd3478edc9d0d686c45`（PR #181 merge commit）
- Tip: `24dfcf37`（accepted Slice 3 commit）
- Output file: `docs/reviews/wu-ctx-04-aggregate-deepreview-ds.md`
- Included scope: 全部 production Python 文件（26 个）、tests（76 个）、config JSON（1 个）、
  README/docs/design（6 个 README + design.md + issues-implementation-control.md）、
  review/control artifacts（全部 Slice 1/2/3 及 plan acceptance artifacts）
- Excluded scope: `docs/reviews/` 下各 Slice 中间 review artifact（仅作为上下文引用，
  不作为再次审查对象）；`docs/host/archive/` 下历史文档；`utils/` smoke 脚本
- Parallel review coverage:
  - Subagent 1 (ade4e0e3): attachment access ownership + native mutex lifecycle
  - Subagent 2 (a1039360): proactive single-operation recovery + config cleanup
  - Subagent 3 (a0ead753): dispatch scheduler + target-only cancel/watchdog +
    canonical reason + terminal producer
  - Subagent 4 (a8617629): durable layer + SQLite batching + state schema
  - Subagent 5 (add7f036): schema/public API/LLM-facing/README cross-slice coherence
  - 主 reviewer（DS）：跨 slice 全量检查 + adversarial failure pass + 过度耦合检查 +
    semantic ownership drift 检查 + 已关闭 finding 验证 + 各 subagent 结论裁决

## 审查方法

1. 先读取 `AGENTS.md`、`CLAUDE.md`、`docs/host/design.md`、
   `docs/host/issues-implementation-control.md`、accepted plan 与三个 Slice
   acceptance artifacts，理解 WU 目标、非目标、设计裁决与验收信号。
2. 以 `974f9e16` 为 base，展开完整 7862 行 diff，识别全部 124 个变更文件。
3. 启动 5 个 subagent 做并行专项深挖：attachment access ownership、proactive
   single-operation recovery、dispatch/cancel/watchdog、durable/SQLite batching、
   schema/README coherence。
4. 主 reviewer 同步独立做全量 cross-cutting 检查：stale field grep、reverse
   dependency、hasattr/getattr 使用、close barrier 排序、canonical reason
   投影链、SQLite batching 计算、attachment lifecycle、proactive 单操作
   不变量、config cleanup 完整性、public export 正确性、LLM-facing 文本纯洁性、
   README/design/doc 一致性。
5. 对 5 个 subagent 的 30+ proposed findings 逐项裁决：接受、驳回（附理由）、
   降级（附理由）、标记为 deferred/reference。
6. 针对每个已接受的 Slice acceptance finding（CTRL-S3-001/002/003、CTRL-S2-001、
   PRR-001/002、CR-DS-001），沿同一条 logic/data path 验证 root-cause closure
   是否有回归。
7. 整合、去重、复核全部证据链，输出最终 aggregate verdict。

## 跨 Slice 已关闭 Finding 回归验证

### CTRL-S3-001（execution-owner cancel poll 独立于 Session reconciliation）

**验证结果：fixed，无回归。** `_active_worker_cancel_reconciliation_loop`
（dispatch.py:3706-3733）是独立 periodic loop，仅调用
`reconcile_active_worker_cancels_once`，不进入 `reconcile_owned_sessions_once`
或 proactive compactor await 链。两个 loop 拥有独立的 health component
（`_CRITICAL_COMPONENT_ACTIVE_CANCEL_OWNER` vs `_CRITICAL_COMPONENT_PROMOTION`），
在 scheduler close 时被独立取消。`reconcile_active_worker_cancels_once`
只使用 `_active_registry.snapshot_identities()` 做精确 identity 查询，不扫描
workspace-wide。

### CTRL-S3-002（canonical cancel reason 由 run-transition typed delivery 投影）

**验证结果：fixed，无回归。** `OwnedAttemptCancelDelivery`（run_transition.py:152-169）
的 `reason` 字段来自 `_validate_exact_owned_cancel_requested_event` 对
`CANCEL_REQUESTED` EventLog row payload 的严格六字段校验。`reconcile_active_worker_cancels_once`
（dispatch.py:3133）使用 `delivery.reason` 传播到 `ActiveCancelMessage.reason` →
`_active_registry.cancel()` → `CancellationToken`。替代常量 `durable_cancel_requested`
已从全库移除（grep 零命中）。跨 opener 测试同时断言 cancellation token 与 worker
hook 收到 canonical reason。

**观察（非回归）：** `_cancelled_eof_candidate`（dispatch.py:5014-5016）在 token
reason 为 None 时使用 fallback `"host_cancelled"`，这是一个 Engine 侧 cancel-eof
诊断 event 的合成 reason，不是 canonical `CANCEL_REQUESTED` reason 的替代品。
该 `EngineEvent(RUN_CANCELLED)` 是 Engine 对 cancel 的观察，与 Host canonical
`CANCEL_REQUESTED` fact 是两个不同的语义层。`cancel_request_event_id` link 正确
保留，canonical reason 可通过 event-join 恢复。这是有意设计，不构成 CTRL-S3-002
回归。

### CTRL-S3-003（SQLite batching 在 transaction 内先校验后查询）

**验证结果：fixed，无回归。** 输入校验（state.py:2247-2259）在第一个 SQL
statement 前对所有 identity 做 owner/session_id/run_id/attempt_id/execution_id
非空校验与 duplicate 拒绝。batch size 推导为 `(999 - 1) // 5 = 199`，单 batch
parameters 为 `199 * 5 + 1 = 996 <= 999`。跨 batch 的 `request_order` 使用
`batch_start` 作为绝对起始值（line 2268），`candidates.extend()` 按 batch
顺序追加，保证全局输入顺序。205 identity 逆序跨 batch 反例的测试已通过。

### CTRL-S2-001（zero-request orphan/unknown proactive history fail-closed）

**验证结果：fixed，无回归。** `_project_state`（proactive_compaction.py:379-382）
对所有 rows 先做 `session_id`/`run_id` identity 校验，再进行 event_type 分发。
orphan/reactive-only rows 被正确隔离。INVALID state 保留 terminal evidence
防止第二 terminal。dispatcher 无 safe id 时调用 `_fail_unstarted_in_transaction`，
Run = FAILED，零增量 provider/Attempt/新 request。

### PRR-001（Host close scheduler-before-unlock lifecycle barrier）

**验证结果：fixed，无回归。** `_close_owned_resources`（open_host.py:1527-1538）：
`begin_host_close` → `health_gate.begin_closing` → wait poller close →
`durable_actor.stop_and_drain` → `drain_host_close` → `scheduler.close()`
→ `release_host_close`。scheduler mandatory quiescence 严格在 mutex release
之前。scheduler.close() 内部执行：cancel_all active workers → cancel/drain
background tasks → close worker handles → clear registry → close lane →
mark instance STOPPED（dispatch.py:3200-3255）。

### PRR-002（reactive caller scope 封闭）

**验证结果：fixed，无回归。** `engine_ingest.py` 内 reactive 路径仅做
`CompactionEvent` schema 机械适配，既有 count/overflow/recovery/fallback 不变。
`test_engine_ingest_mapping.py` 与 `test_compaction_cancellation_scope.py`
已纳入测试面。

### CR-DS-001（native mutex partial FD cleanup 诊断链）

**验证结果：fixed，无回归。** `_close_partial_file_descriptor`
（native_mutex.py:339-364）使用 `ExceptionGroup` cause 同时保留 prior native
error 与 partial close error 的 identity、cause 和 traceback。

### compact_pipeline.py tier_2 segment fix

**验证结果：correct fix，非回归。** `compact_pipeline.py:538` 将 tier_2 的
`selected_segment` 从 `root_request_plan.selected_segment` 改为
`bounded_selection`，与 tier_1 行为一致。此前 tier_2 recovery 使用了未截断的
root selection，使 section degrade recovery 无效。

## Findings

### F-01 [中] — `drain_host_close` 缺少超时机制，lease 泄漏可导致 Host close 永久挂起

- **入口/函数**: `HostSessionAttachmentRegistry.drain_host_close`
- **文件(行号)**: `session_attachment.py:556-573`
- **输入场景**: 任何 `SessionWorkLease` 未被正确释放（如 `release_when_done` 绑定的
  Future 永不 resolve、或 `release()` 从未被调用）
- **实际分支**: `drain_host_close` 使用 `asyncio.Event.wait()` 无超时参数，永久阻塞
  在 `record.mutation_drained.wait()` 或 `record.new_work_drained.wait()`
- **预期行为**: 在合理时间内完成 drain，若超时则记录 hanging lease 的诊断信息并
  按 fail-closed 策略处理
- **实际行为**: 永久挂起，Host close 无法推进，mutex 永远不会被释放。scheduler
  和其他 Host 资源也会卡在 CLOSING 状态
- **直接证据**: `session_attachment.py:569-572`：`await record.mutation_drained.wait()`
  与 `await record.new_work_drained.wait()` 均为裸 `Event.wait()`，无 timeout 参数
- **影响**: 若发生 lease 计数 bug，Host close 永久阻塞，需要外部 kill 进程
- **建议改法和验证点**: 为 `drain_host_close` 增加可配置的超时参数，超时后记录
  每个 hanging lease 的 `session_id` 与 lease 计数，然后 raise。在 `release_host_close`
  中处理未 drain 的 lease（当前第 586 行已在校验 drain 未完成时 raise，增加
  hanging lease 诊断信息）
- **修复风险（中）**: 超时行为的引入需要新增 runtime policy 字段或超时常量；
  超时后记录但不释放 mutex 是 fail-closed 的保守策略
- **严重程度（中）**: 依赖 lease 计数机制的正确性，当前生产路径无已知 lease 泄漏
  bug，但缺少超时防御使 Host close 路径脆弱

### F-02 [低] — Windows `_lock_file_descriptor` 内 `os.lseek` 与 `locking` 共享 try/except

- **入口/函数**: `_lock_file_descriptor`
- **文件(行号)**: `native_mutex.py:275-284`
- **输入场景**: 极低概率。Windows 平台上 `os.lseek(fd, 0, SEEK_SET)` 因 descriptor
  异常（如外部 fcntl 修改）产生 `EACCES`
- **实际分支**: `_is_busy_error` 将 `EACCES` 判定为 busy，返回 `None`
- **预期行为**: lseek 失败应 fail-closed（raise `StrictNativeMutexUnavailableError`）
- **实际行为**: 被误判为"已有其他 opener 持有 mutex"，调用方按 RO 模式继续，
  mutex 保护被绕过
- **直接证据**: `native_mutex.py:278-284`：`os.lseek` 与 `locking_windows.locking`
  在同一 `try` 块内，`_is_busy_error`（line 296-298）不区分 lseek 与 locking 的
  errno 来源
- **影响**: 极端条件下 mutex 保护被静默绕过，但正常文件 descriptor 上的
  `lseek(fd, 0, SEEK_SET)` 不应产生 `EACCES`
- **建议改法和验证点**: 将 `os.lseek` 移到 `try` 块外部独立 fail（类似
  `_prepare_windows_lock_file` 将 lseek 置于 locking 之前的模式）
- **修复风险（低）**: 单行移动，不改变 busy/fail 判定逻辑
- **严重程度（低）**: 极低触发概率，且仅影响 Windows 平台

### F-03 [低] — `release_host_close` 在 mutex 释放失败时 `_host_close_released` 永久为 False

- **入口/函数**: `HostSessionAttachmentRegistry.release_host_close`
- **文件(行号)**: `session_attachment.py:575-605`
- **输入场景**: native mutex unlock 因不可恢复的系统调用错误（如 `EIO`）失败
- **实际分支**: `_release_record` 在 mutex release 失败时（line 782-788）设置
  `record.close_error`、设置 `record.close_completed.set()`，但不删除 record
  也不将 state 改为 CLOSED；record 留在 `_records` 中
- **预期行为**: `_host_close_released` 应在 release 被尝试后标记（即使部分失败）
- **实际行为**: `self._records` 非空 → `_host_close_released` 永不为 True →
  `begin_host_close` 的幂等检查（line 550）永不过早返回 → 每次重试都返回
  相同的缓存错误（line 774-780）
- **直接证据**: `session_attachment.py:602`：`if not self._records: self._host_close_released = True`；
  line 782-788：`_release_record` 在 mutex unlock 失败时不删除 record
- **影响**: fail-closed 的预期行为（不能静默成功），但 `_host_close_released` 的
  语义需要文档澄清
- **建议改法和验证点**: 文档化 `_host_close_released` 只表示"所有 record 已成功
  移除"，而非"release 已被调用过"。或将幂等性检查改为独立标记
- **修复风险（低）**: 仅涉及语义文档化
- **严重程度（低）**: 当前行为是设计意图内的 fail-closed

### F-04 [低] — 已取消的 close task 导致 record 无法通过 `_close_attachment` 重试

- **入口/函数**: `_close_attachment`
- **文件(行号)**: `session_attachment.py:709-724`
- **输入场景**: `_run_attachment_close` task 被取消（如 event loop shutdown），
  此后再次调用 `_close_attachment`
- **实际分支**: `record.close_task` 非 None（指向已取消的 task），`record.state`
  不是 CLOSED → 第 722 行 `await asyncio.shield(record.close_task)` 立即抛出
  `CancelledError`，无代码路径重置 `close_task` 或重建 task
- **预期行为**: 应识别已取消的 task 并重建
- **实际行为**: 持续抛出 `CancelledError`，record 卡在 CLOSING
- **直接证据**: `session_attachment.py:720-722`：`close_task` 仅在首次调用时创建，
  永不重置为 None
- **影响**: 仅在 event loop shutdown 期间的极端情况下触发。Host close 场景中
  `release_host_close` 会绕开 `_close_attachment` 直接调用 `_release_record`
  （line 593），因此 Host close 不受影响
- **建议改法和验证点**: 在 `_close_attachment` 中增加已取消 task 的重建逻辑：
  若 `record.close_task.done()` 且 `record.close_task.cancelled()` 且 state
  不是 CLOSED，重置 `record.close_task = None` 并重新创建
- **修复风险（低）**: 仅影响窄边界场景
- **严重程度（低）**: 极低触发概率，Host close 路径不受影响

### F-05 [低] — `_acquire_lease` 缺少 record lifecycle state 防御性检查

- **入口/函数**: `_acquire_lease`
- **文件(行号)**: `session_attachment.py:659-680`
- **输入场景**: 未来新增调用方绕过 state 检查直接调用 `_acquire_lease`
- **实际分支**: 仅检查 record 是否在 `_records` 中（line 672），不校验
  `record.state` 是否为 ACTIVE 或 RECOVERING
- **预期行为**: 内部 API 应有防御性 state 断言
- **实际行为**: 若未来调用方绕过 state 检查，可为 CLOSING/CLOSED record 创建 lease
- **直接证据**: `session_attachment.py:672`：`if self._records.get(record.session_id) is not record`
  是唯一的 guard
- **影响**: 当前所有调用方（`acquire_mutation_lease`、`try_acquire_new_work_lease`、
  `_acquire_recovery_work_lease`）在调用前都做了 state 检查，无当前 bug
- **建议改法和验证点**: 在 `_acquire_lease` 中增加 state 断言，至少拒绝
  CLOSING/CLOSED state
- **修复风险（低）**: 防御性加强
- **严重程度（低）**: 仅未来风险，当前无 bug

### F-06 [参考] — 多条 terminal closeout 路径使用不同 reason 语义（有意设计，非 bug）

- **入口/函数**: `active_cancel_closeout_in_transaction`、`active_cancel_watchdog_closeout_in_transaction`、
  `terminal_closeout_in_transaction`
- **文件(行号)**: `run_transition.py:2285`、`dispatch.py:4884/4920`、多处
- **观察**: 终端 reason 因 producer 不同而不同：
  - Engine-aware cancel closeout 使用 `data.reason`（Engine token reason）
  - watchdog closeout 使用 `_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON`（`"active_cancel_watchdog_closeout"`）
  - 普通 terminal closeout 使用传入的 `reason`（Engine 终态 reason）
- **直接证据**: 各 producer 向各自的 closeout function 传入不同的 reason 值
- **影响**: 下游消费者若按 `reason` 字段做逻辑判断，需要区分 producer 类型。
  各 terminal event 均正确保留了 `cancel_request_event_id` link 用于 event-join
  恢复 canonical reason
- **严重程度（参考）**: 这是有意设计的分层 terminal ownership，不是 bug

## Open Questions

1. **`drain_host_close` 超时策略**：当前设计假设所有 lease 最终都会被释放。
   若未来需要超时 + 强制 drain 的降级路径，需要先定义超时 policy 的 owner
   （runtime config？Host construction input？）与超时后的行为（记录诊断后强制
   释放 mutex？保留 mutex 但完成 Host close？）。

2. **compactor input projection inline vs file-based 切换**：
   `DurableCompactorProposalManifestRecorder` 从 file-based 切换到 inline
   `write_bounded_json_payload`，需确认 bounded JSON payload 的 size threshold
   与大 compactor input projection 的兼容性。

3. **artifact orphan GC**：文件系统上的 digest-addressed artifact 在 SQLite
   transaction rollback 后可能遗留孤儿文件。当前设计依赖 digest 去重减少浪费，
   但长期运行后累计的孤儿 artifact 需要 periodic GC（已在 WU-RET-04 / #156
   中作为 compaction artifact retention 的子项跟踪）。

## Residual Risk

1. **Windows strict-native mutex 环境验证**：实现与 unit contract 已覆盖，
   当前执行环境只完成 POSIX 验证。属于 cross-platform environment residual，
   不改变 strict-native/fail-closed public contract。

2. **provider process crash 不承诺外部 side effect exactly-once**：accepted non-goal。
   durable prepared manifest 保守消耗 attempt 并从下一 schedule stage 恢复。

3. **poll cadence 影响 physical cancel 延迟**：execution-owner cancel reconciliation
   受 `dispatch_poll_interval_seconds` 约束，最坏情况下 cancel 延迟为该间隔。
   属于既有 runtime-policy owner，不阻塞本 WU。

4. **定制 SQLite runtime 若主动降低 variable limit**：当前 batch size 基于 SQLite
   legacy default 999。若定制构建使用 <999 的 limit，需独立 runtime-policy work
   unit 适配。不改变 correctness。

5. **tier_2 segment fix 缺少直接单元测试**：`compact_pipeline.py` 的 tier_2 使用
   `bounded_selection` 而非 `root_request_plan.selected_segment` 的修复缺少直接
   断言 tier_2 request plan 的 selected_segment 等同于 bounded_selection 的测试。
   当前覆盖为间接（通过 startup recovery integration test）。

6. **`drain_host_close` 超时缺失**：参见 F-01。当前依赖 lease 计数正确性，
   无已知泄漏 bug 但有结构性脆弱性。

7. **fresh schema 拒绝旧 persisted CONTEXT_COMPACTION_REQUESTED payload**：
   若 pre-WU-CTX-04 的 Run 有 incomplete proactive operation，旧 request
   payload 缺少新 required fields（`operation_id`、
   `max_compaction_attempts_per_operation`、`frozen_material_list_digest`、
   `frozen_material_refs`），会被 `_require_exact_fields` 拒绝，projection
   返回 INVALID，dispatcher fail-closed。这是 fresh schema 设计的预期行为。

## Verdict

**`pass`**。

经过 5 个专项 subagent 并行深挖与本 reviewer 的全量 cross-cutting 检查：

- 所有 7 项已接受的 Slice finding（CTRL-S3-001/002/003、CTRL-S2-001、
  PRR-001/002、CR-DS-001）的 root-cause closure 均无回归。
- `max_proactive_compactions_per_run` 彻底删除（production/tests/config/docs
  stale grep 均为零）。
- `durable_cancel_requested` 替代常量完全移除（全库零命中）。
- Native mutex 严格 fail-closed，没有 soft-lock fallback。
- Session attachment lifecycle（RECOVERING→ACTIVE→CLOSING→CLOSED）正确实施，
  lease 计数与 drain 机制正确。
- Scheduler close barrier 在 mutex release 之前正确排序。
- Proactive single-operation 不变量在 projection、dispatcher gate 与 SQLite
  write transaction 三层加固。
- Target-only cancel/watchdog 在所有关键路径上正确替代 workspace-wide scan。
- Canonical cancel reason 由 run-transition typed delivery 投影，CTRL-S3-002
  正确闭合。
- SQLite batching 输入校验先于 SQL 执行，batch size 计算正确，跨 batch 顺序
  保持。
- Host/Service/Config/Tests/Runtime README 与 package exports 未见与实现不一致。
- LLM-facing 文本（prompts）无内部术语泄漏。
- 未发现 `hasattr`/`getattr` 补偿、兼容性 re-export 或反向依赖。

**Actionable finding 数量**：5 项（F-01 中，F-02 低，F-03 低，F-04 低，F-05 低）。

- F-01（中）：`drain_host_close` 缺少超时——为当前设计的结构性脆弱点，建议
  纳入后续 Host close robustness work unit，但当前无已知触发路径与测试反例。
- F-02（低）：Windows lseek 与 locking 共享 try/except——极低触发概率且仅影响
  Windows，可随下一次 Windows CI 验证一并修复。
- F-03/F-04/F-05（低）：均属于防御性改进或文档澄清，不涉及当前正确性问题。

**Blocking questions**：None。

**建议的下一步**：
1. Controller 裁决本 aggregate deepreview 的 5 项 findings。
2. 按裁决结果进入 draft PR readiness（若全部接受/reject/defer 则继续；
   若有 needs-fix 则先修复/re-review）。
3. Draft PR readiness 时同步完成：
   - 控制文档 `docs/host/issues-implementation-control.md` 更新（当前
     uncommitted 的 aggregate-deepreview-in-flight 状态变更需正式提交）
   - 最终 pyright 与受影响测试矩阵确认
   - GitHub Issue #112 状态更新
