# Host Phase 7 Plan Re-Review - MiMo - 2026-05-16

## Review Target

- **Fixed plan**: `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- **Fix artifact**: `docs/reviews/host-phase7-plan-fix-codex-20260516.md`
- **Controller adjudication**: `docs/reviews/host-phase7-plan-review-controller-adjudication-20260516.md`
- **Prior review**: `docs/reviews/host-phase7-plan-review-mimo-20260516.md`

## PF1-PF12 Verification

### PF1 - late result diagnostic 与 wait resolution idempotency 顺序冲突

**裁决要求**: pipeline 应先读取 wait record status；若状态不可接收新 resolution，则进入 late rejection path。

**Plan 修复验证**:

- §3.9 步骤 3: "Status classification happens before idempotency replay" ✓
- §3.9 步骤 5: `cancelled`/`lost`/terminal Run → "Go directly to the late rejection path in §3.10.1 using independent `wait_late_rejection` idempotency" ✓
- §3.9 步骤 6: `resolved`/`failed` → 不进入 late rejection，只允许 same-key same-digest 幂等重放；不同 key 返回 `INVALID_STATE` ✓
- §3.9 步骤 7: `waiting` → 正常 `wait_resolution` 幂等检查 ✓

**关键验证**: 步骤 6 不走 late rejection 是正确的——`resolved`/`failed` 已有 committed resolution，不同 key 的尝试是无效 resolution 而非迟到结果。只有 `cancelled`/`lost`/terminal 才是"已无法接收新 resolution"的状态。§3.10.1 明确: "Already `resolved` / `failed` wait records with a different key are invalid-state resolution attempts and do not use late rejection idempotency unless the owning Run has separately become terminal outside the recorded wait resolution path" ✓

**结论**: PF1 已关闭 ✓

### PF2 - EngineEvent awaiting / suspended 行为矩阵缺失

**裁决要求**: 给出 `(Run.status, Attempt/execution match, accepted refs present, event type)` 行为表。

**Plan 修复验证**:

- §3.13 新增完整行为矩阵，覆盖 9 种 Run.status × match × refs × event_type 组合 ✓
- 矩阵列: `Run status | Attempt/execution match | Accepted refs present and match wait record | Event type | Required behavior` ✓
- "No `TOOL_AWAITING` / `RUN_SUSPENDED` EngineEvent path may call `_close_terminal`, `terminal_closeout_in_transaction`, `terminal_run_row` or an equivalent terminal closeout helper" ✓
- P7-S4 tests 要求覆盖 `WAITING` with/without refs、`RUNNING` without refs、terminal states ✓

**结论**: PF2 已关闭 ✓

### PF3 - WAITING cancel 集成锚点不明确

**裁决要求**: 指定 module/service path、durable helper、CAS 前置条件、ATTEMPT_CANCELLED 处理、after-commit notification。

**Plan 修复验证**:

- §3.11 明确 4 个集成锚点: `command.py` → `admission.py` → `run_transition.py` → `state.py`/`wait_state.py` ✓
- `cancel_waiting_run_in_transaction(...)` in `run_transition.py` ✓
- `cancel_active_wait_records_for_run(...)` in state helpers ✓
- CAS 前置条件: Run `WAITING`, no terminal refs, Attempt `SUSPENDED`, at least one active wait ✓
- "Do not create `ATTEMPT_CANCELLED` for the suspended Attempt" ✓
- `WaitCancelNotification(run_id, wait_ids, adapter_keys, external_job_refs)` after commit ✓
- Both `cancel_run` and `cancel_session_runs` delegate to same core helper ✓

**结论**: PF3 已关闭 ✓

### PF4 - WAITING -> RUNNING transition helper 缺失

**裁决要求**: 新增 `resume_run_from_waiting(...)` 或等价 helper。

**Plan 修复验证**:

- §3.9 新增 `resume_run_from_waiting_in_transaction(...)` ✓
- 输入: transaction, EventLog store, wait_id, run/attempt ids, new attempt/execution/dispatch ids, event ids, occurred_at, actor/source, resolution payload, worker kind/execution target ✓
- CAS 前置条件: Run `WAITING`, Attempt `SUSPENDED`, wait record `waiting`, no terminal refs, unique active wait invariant ✓
- 写入: append `RESUME_REQUESTED` + `TOOL_RESULT_ACCEPTED`; CAS wait to `resolved`; append `RUN_STARTED(resume)`; insert new `STARTING` Attempt; update Run `RUNNING`; append `ATTEMPT_STARTED`; insert dispatch record ✓
- 返回类型: typed result with `StateMutationStatus`, `RunRow`, `AttemptRow`, `DispatchRecordRow | None`, event refs ✓
- Failed/lost closeout: separate helpers or typed terminal mode, no dispatch record ✓

**结论**: PF4 已关闭 ✓

### PF5 - TOOL_RESULT_ACCEPTED wait payload 字段未指定

**裁决要求**: 列出 wait-specific 增量字段。

**Plan 修复验证**:

- §3.10 列出 Ordinary Phase 6 fields (22 个) ✓
- §3.10 列出 Wait-specific incremental fields (15 个): `wait_id`, `resolution_source`, `resolution_kind`, `resolution_idempotency_key`, `observed_at`, `wait_record_status_before/after`, `wait_created_event_ref`, `wait_updated_event_ref`, `adapter_key`, `external_job_ref`, `snapshot_ref`, `provider_status_ref`, `resume_attempt_id`, `resume_dispatch_record_id` ✓
- `_event_payload.py` helper ownership: `tool_awaiting_payload(...)`, `run_waiting_payload(...)`, `attempt_suspended_payload(...)`, `resume_requested_payload(...)`, `tool_result_wait_resolution_payload(...)`, `wait_late_result_rejected_payload(...)` ✓
- P7-S2 exact changes 列出 S2 的 3 个 helpers ✓
- P7-S3 exact changes 列出 S3 的 2 个 helpers ✓
- P7-S4 exact changes 隐含 S4 的 1 个 helper ✓

**结论**: PF5 已关闭 ✓

### PF6 - key/ref 长度约束未具体化

**裁决要求**: 给出具体长度上限。

**Plan 修复验证**:

- §3.6.1 新增完整长度约束表，9 个字段 ✓
- `wait_id`: 128, `adapter_key`: 128, `tool_call_id`: 256, `tool_name`: 128, `resume_token`: 2048, `snapshot_id`: 256, `external_job_id`: 512, `status_ref`: 512, `idempotency_key`: 256 ✓
- Dataclass validation 与 DDL CHECK 一致性要求 ✓
- "If existing helper constants already define stricter limits... implementation must use the stricter existing limit" ✓

**结论**: PF6 已关闭 ✓

### PF7 - ToolFactKind.LOST slice ownership 不明确

**裁决要求**: 把 `ToolFactKind.LOST` 放入具体 slice 的 exact changes 和 allowed files。

**Plan 修复验证**:

- §4.1 P7-S1 allowed files: `dayu/host/tool_runtime.py` "only for `HostPayloadRef` import migration and `ToolFactKind.LOST` enum extension" ✓
- P7-S1 exact changes: "Add `ToolFactKind.LOST` in `dayu/host/tool_runtime.py` during this slice so later resolve slices can emit lost wait results without modifying unowned files" ✓
- P7-S1 tests: "`ToolFactKind.LOST` is present before P7-S3" ✓

**结论**: PF7 已关闭 ✓

### PF8 - outcome digest / payload ref 互斥语义不清

**裁决要求**: 明确 lost/non-lost 的 ref 互斥和 digest null sentinel。

**Plan 修复验证**:

- §3.2 新增 "Outcome ref 互斥规则" ✓
- "completed / failed / cancelled outcome 可以携带 `payload_ref`，必须没有 `provider_status_ref`" ✓
- "lost outcome 可以携带 `provider_status_ref`，必须没有 `payload_ref`" ✓
- "digest 输入必须对每个可选 typed field 写入显式 `null` sentinel" ✓
- "这样可避免'字段缺失'和'字段为空'生成同构 digest" ✓
- "digest 输入必须覆盖所有非空 typed fields" ✓

**结论**: PF8 已关闭 ✓

### PF9 - poller 生命周期与并发模型未指定

**裁决要求**: 明确运行模型、启动/停止边界、transaction 约束、restart 恢复。

**Plan 修复验证**:

- §3.12 新增完整 poller 生命周期规格 ✓
- "Host-runtime owned, not process-global" ✓
- "constructed by Host composition root with a `HostCommandHandle` / transaction runner, adapter registry and bounded poll policy" ✓
- "starts when the owning Host handle / scheduler runtime starts and stops on handle close / scheduler close" ✓
- "explicit `poll_once()` / `drain_once()` method for deterministic tests" ✓
- "background loop... must be cancellable and must not survive Host handle close" ✓
- "Restart recovery is limited to scanning durable active `resume_policy=POLL AND status='waiting'` wait records" ✓
- "Full orphan recovery... remain Phase 11" ✓
- "short read transaction, releases the transaction, calls external adapter outside any Host transaction, then submits... in a separate command transaction" ✓
- "in-process in-flight set keyed by `wait_id`" ✓
- "Cross-process concurrency is governed by wait record CAS and `resolve_wait` idempotency" ✓
- "must not hold EventLog appender or wait-state writer ports" ✓

**结论**: PF9 已关闭 ✓

### PF10 - resolved/failed wait different-key 拒绝测试缺失

**裁决要求**: 新增 `resolved`/`failed` wait 不同 key 返回 `INVALID_STATE` 测试。

**Plan 修复验证**:

- P7-S3 tests 新增: "Already `resolved` wait with a different `idempotency_key` returns `INVALID_STATE`, appends no canonical fact and creates no Attempt" ✓
- P7-S3 tests 新增: "Already `failed` wait with a different `idempotency_key` returns `INVALID_STATE`, appends no canonical fact and creates no Attempt" ✓

**结论**: PF10 已关闭 ✓

### PF11 - late diagnostic idempotency 策略未收敛

**裁决要求**: 使用独立 `wait_late_rejection` idempotency scope。

**Plan 修复验证**:

- §3.10.1 新增完整 late rejection idempotency 规格 ✓
- `scope_kind = "wait_late_rejection"` ✓
- `scope_id = wait_id` ✓
- `idempotency_key = ResolveWaitRequest.idempotency_key` ✓
- "Same key + same late digest returns existing diagnostic refs" ✓
- "Same key + different late digest returns idempotency conflict diagnostic / error and must not append unbounded diagnostic events" ✓
- P7-S4 tests 覆盖: "Same late rejection key + same digest returns existing diagnostic refs and appends no second diagnostic" ✓
- P7-S4 tests 覆盖: "Same late rejection key + different digest returns idempotency conflict diagnostic / error and appends no unbounded diagnostics" ✓

**结论**: PF11 已关闭 ✓

### PF12 - open questions must be answered in plan

**裁决要求**: HostPayloadRef 移入 api、_event_payload.py helper ownership、ResolveWaitRequest.context 保留。

**Plan 修复验证**:

- HostPayloadRef: §3.2 "implementation 必须把该 dataclass 移入 `dayu.host.api`"；P7-S1 exact changes "Move current `HostPayloadRef` from `dayu.host.tool_runtime` to `dayu.host.api`" ✓
- `_event_payload.py`: §3.10 列出 6 个 helper 函数；P7-S2/S3/S4 各自列出所属 helper ✓
- `ResolveWaitRequest.context`: §3.2 "`ResolveWaitRequest.context: HostCallContext` 必须保留"；P7-S1 exact changes "Change `ResolveWaitRequest` to retain `context: HostCallContext`" ✓

**结论**: PF12 已关闭 ✓

## New Issues Check

对修复后的 plan 做 adversarial scan，检查修复是否引入新问题：

1. **`resolve_wait` pipeline 步骤 6 的 `resolved`/`failed` 处理**: 步骤 6 允许 same-key same-digest 幂等重放已有 resolution，不同 key 返回 `INVALID_STATE`。这与 §3.10.1 的 late rejection scope 独立——`resolved`/`failed` 的不同 key 不走 late rejection，而是直接 `INVALID_STATE`。语义正确：已有 committed resolution 的 wait 不是"迟到结果"，而是"无效的第二次 resolution 尝试"。✓ 无新问题。

2. **`_event_payload.py` 跨 slice 共享**: S2、S3、S4 都列出该文件。每个 slice 添加不同 helper 函数，不重叠。S2: `tool_awaiting_payload`, `run_waiting_payload`, `attempt_suspended_payload`。S3: `resume_requested_payload`, `tool_result_wait_resolution_payload`。S4: `wait_late_result_rejected_payload`。✓ 无 ownership 冲突。

3. **`WaitCancelNotification` 类型位置**: §3.11 引入 `WaitCancelNotification(run_id, wait_ids, adapter_keys, external_job_refs)` 作为 after-commit 通知。Plan 未指定该类型的定义文件。S4 allowed files 包含 `wait_adapter.py`，适合作为该类型定义位置。✓ 低风险，implementation agent 可推断。

4. **`resume_run_from_waiting_in_transaction(...)` 写入 `RUN_STARTED(start_reason=resume)`**: 设计 §20 明确 "append `RUN_STARTED(start_reason=resume)`"。这是一条新 EventLog event，与 initial `RUN_STARTED` 共存。Run row 的 `started_event_id` 将指向 resume 的 `RUN_STARTED`。这是有意设计，不是重复 event。✓ 无新问题。

5. **§3.9 步骤 2 在步骤 3 之前构建 digest**: 步骤 2 构建 `resolution_digest` 和 `late_rejection_digest`，步骤 3 才读 wait record。Implementation agent 可以在验证通过后、进入 transaction 前构建两个 digest，或在 transaction 内按需构建。✓ 不影响正确性。

## Open Questions

无。

## Residual Risks

与 fix 前一致，无新增 residual risk：

- Callback productization 延迟。
- External job physical cancel best-effort only。
- Cross-process duplicate governance 限制。
- Recovery scan 归 Phase 11。
- Tool trace projection 归后续 phase。

## Conclusion

**PASS**

PF1-PF12 全部已关闭，修复质量符合 controller 裁决要求。修复后的 plan 无 blocking accepted finding 残留，可以进入 accepted plan commit gate。

关键修复质量评估：

- PF1 的 pipeline 重排序是最关键修复。新步骤 3→5→6→7 的状态分类优先于幂等检查，且正确区分了 `cancelled`/`lost`（late rejection）与 `resolved`/`failed`（invalid state）的不同语义路径。
- PF2 的 EngineEvent 行为矩阵覆盖了所有 Run.status × match × refs × event_type 组合，implementation agent 无需自行推断。
- PF3/PF4 的 helper 交付物具体到函数签名、CAS 前置条件、写入字段和返回类型，code-generation-ready。
- PF9 的 poller 生命周期规格覆盖了运行模型、transaction 边界、并发控制和 restart 恢复。
- PF11 的独立 `wait_late_rejection` scope 与 `wait_resolution` scope 完全解耦，不会产生无限 diagnostic。
