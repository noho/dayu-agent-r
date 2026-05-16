# Host Phase 7 Plan Fix - Codex - 2026-05-16

## Gate

- **current gate**: Phase 7 plan fix
- **source review adjudication**: `docs/reviews/host-phase7-plan-review-controller-adjudication-20260516.md`
- **fixed plan**: `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- **allowed write paths**:
  - `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
  - `docs/reviews/host-phase7-plan-fix-codex-20260516.md`

## Scope

本次只修复 controller accepted PF1-PF12。未修改设计真源、总控文档、源码、测试、分支、commit、PR 或外部状态。

## Per-finding Fix Status

### PF1 - 已修复 - late result diagnostic 与 wait resolution idempotency 顺序冲突

- 在 §3.9 调整 `resolve_wait` pipeline：先读取 wait record / Run / Attempt 并按状态分类，再读取有效 resolution 幂等记录。
- 明确 `cancelled` / `lost` / terminal Run 不属于有效 resolution replay，直接进入 §3.10.1 late rejection path。
- 明确 `resolved` / `failed` 不同 key 返回 `INVALID_STATE`，不写 canonical fact、不写 late diagnostic、不创建 Attempt。

### PF2 - 已修复 - EngineEvent awaiting / suspended 行为矩阵缺失

- 在 §3.13 新增行为矩阵，覆盖 Run.status、Attempt/execution match、accepted refs 是否存在、`TOOL_AWAITING` / `RUN_SUSPENDED` event type。
- 明确任何 Engine awaiting/suspended path 都不得调用 `_close_terminal` 或等价 terminal closeout。

### PF3 - 已修复 - WAITING cancel 集成锚点不明确

- 在 §3.11 增加 command / admission / durable helper 集成锚点。
- 明确 `cancel_run` 与 `cancel_session_runs` 都经 admission，并复用同一 WAITING cancel core helper。
- 明确 CAS 前置条件、`cancel_active_wait_records_for_run(...)`、不追加 `ATTEMPT_CANCELLED`、after-commit `WaitCancelNotification`。

### PF4 - 已修复 - WAITING -> RUNNING transition helper 缺失

- 在 §3.9 新增 `resume_run_from_waiting_in_transaction(...)` 交付物。
- 明确输入、CAS 前置条件、写入字段、事件 refs、dispatch record 创建边界和返回类型。
- 明确 failed/lost waiting closeout 使用独立 helper 或 typed terminal mode，不能创建 dispatch record。

### PF5 - 已修复 - TOOL_RESULT_ACCEPTED wait payload 字段未指定

- 在 §3.10 列出 ordinary Phase 6 fields 与 wait-specific incremental fields。
- 明确 wait-specific fields 包含 `wait_id`、`resolution_source`、`resolution_kind`、`outcome_digest`、`wait_record_status_before/after`、adapter / external job / snapshot / provider refs、resume refs。
- 明确 `_event_payload.py` helper ownership。

### PF6 - 已修复 - key/ref 长度约束未具体化

- 在 §3.6.1 新增长度约束表。
- 明确 `WaitAdapterKey`、`external_job_id`、`snapshot_id`、provider status ref、wait id、resume token、idempotency key 的上限。
- 明确 dataclass validation 与 DDL `CHECK` 的一致性要求。

### PF7 - 已修复 - ToolFactKind.LOST slice ownership 不明确

- 在 §4.1 把 `dayu/host/tool_runtime.py` 加入 P7-S1 allowed files，仅限 `HostPayloadRef` import migration 与 `ToolFactKind.LOST`。
- 在 P7-S1 exact changes 明确新增 `ToolFactKind.LOST`。
- 在 P7-S1 tests 明确 `ToolFactKind.LOST` 必须在 P7-S3 前可用。

### PF8 - 已修复 - outcome digest / payload ref 互斥语义不清

- 在 §3.2 增加 outcome ref 互斥规则。
- 明确 lost outcome 无 `payload_ref`，非 lost outcome 无 `provider_status_ref`。
- 明确 digest 输入包含所有非空 typed fields，并对 optional fields 使用显式 `null` sentinel。

### PF9 - 已修复 - poller 生命周期与并发模型未指定

- 在 §3.12 增加 poller 运行模型、启动/停止边界、`poll_once` / background loop、Host handle close 约束。
- 明确 poller 不跨 transaction await 外部 adapter，不持有 EventLog appender / wait writer，只通过 `resolve_wait` 改状态。
- 明确 restart 扫描 active poll waits 仅是 Phase 7 最小恢复，完整 recovery 仍归 Phase 11。
- 明确同进程 in-flight set 与跨进程 CAS/idempotency 分工。

### PF10 - 已修复 - resolved / failed wait different-key 拒绝测试缺失

- 在 P7-S3 tests 新增 resolved wait different key 与 failed wait different key 用例。
- 明确期望为 `INVALID_STATE`，不追加 canonical fact、不创建 Attempt。

### PF11 - 已修复 - late diagnostic idempotency 策略未收敛

- 在 §3.10.1 固定独立 `wait_late_rejection` idempotency scope。
- 明确 `scope_id=wait_id`，caller key 作为 idempotency key。
- 明确 same key + same late digest 返回既有 diagnostic refs；same key + different late digest 返回 conflict diagnostic/error，不追加无限 diagnostic events。
- 在 P7-S4 exact changes / tests 加入该 scope 和重复场景。

### PF12 - 已修复 - open questions must be answered in plan

- `HostPayloadRef`：§3.2 和 P7-S1 exact changes 明确移入 `dayu.host.api`，ToolRuntime 改 import。
- `_event_payload.py`：§3.10、P7-S2、P7-S3、P7-S4 明确 helper ownership。
- `ResolveWaitRequest.context`：§3.2 和 P7-S1 exact changes 明确保留 `context: HostCallContext`。

## Blocking Questions For Controller

无。

## Validation

已执行：

```bash
git diff --check -- docs/host/phase7-tool-awaiting-resolve-wait-plan.md docs/reviews/host-phase7-plan-fix-codex-20260516.md
```

结果：通过，无 whitespace error。

本 fix 未运行 pytest / pyright，因为本 gate 只修改 plan 与 fix artifact，未修改代码或测试。

## Residual Risk

- 本 fix 只收敛 plan 规格，不验证实现可行性。具体实现仍需按 slice validation 和后续 plan re-review / code review gate 执行。
