# P8.5 Slice 5a Implementation Report

- **work gate**: implementation
- **work unit**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **assigned slice**: P8.5 Slice 5a — Attempt Lease Diagnostic Corrections
- **approved plan**: `docs/host/phase8.5-plan.md`
- **artifact path**: `docs/host/phase8.5-s5a-implementation-report.md`

## Assigned Scope

只处理 attempt lease 诊断、防御性校验和 `next_attempt_index()` 独立测试：

- 新增独立 `AttemptFencingReason.RUN_ID_MISMATCH`。
- BUSY 不复用 fencing reason，新增独立 busy reason。
- `AttemptLeaseResult` 暴露独立 busy reason 字段。
- `lease_context` 显式校验 `run_id`、`attempt_index`、`recovered_from_attempt_id`。
- 为 `AttemptLeaseStore.next_attempt_index()` 补无 attempt、active、terminal、gap/conflict 独立测试。

## Explicit Non-goals

- 未修改 public Host API。
- 未把 attempt 语义移动到 `dayu.runtime`。
- 未实施 Slice 5b adversarial hardening。
- 未创建 commit、PR 或 closeout。

## Changed Files

- `dayu/host/_attempt_lease.py`
- `dayu/host/_attempt_supervisor.py`
- `dayu/host/_run_state_store.py`
- `tests/host/test_phase8_attempt_supervisor.py`
- `tests/host/test_phase8_attempt_fencing.py`
- `tests/host/test_phase8_attempt_lease_store.py`
- `dayu/host/README.md`
- `docs/host/phase8.5-s5a-implementation-report.md`

## Plan Items Implemented

- `RUN_ID_MISMATCH`: 已新增到 `AttemptFencingReason`，`AttemptScopedRunEventAppender` 的 run id 校验失败现在使用该 reason。
- BUSY reason: 已新增 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT`，`AttemptLeaseResult.busy_reason` 独立承载 BUSY 语义；BUSY 结果的 `reason` 保持 `None`。
- `lease_context` 参数校验: 已在 acquire 前拒绝空 `run_id`、负数 `attempt_index`、空串 `recovered_from_attempt_id`。
- `next_attempt_index()` 独立测试: 已覆盖无 attempt、active、terminal、gap/conflict。

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py -q`
  - 结果：通过，`44 passed`
- 额外验证：`source .venv/bin/activate && pytest tests/host/test_phase8_attempt_lease_store.py -q`
  - 结果：通过，`29 passed`

## Documentation Decision

已更新 `dayu/host/README.md` 中 attempt-scoped append 的 run id mismatch reason，从 `OWNER_MISMATCH` 同步为 `RUN_ID_MISMATCH`。根 README、Engine README、Fins README、Config README、Tests README 不涉及当前行为边界，未更新。

## Plan Gaps Or Controller Questions

无。为表达 `AttemptLeaseResult` 与 enum 变更，实际修改了内部 lease 契约模块 `dayu/host/_attempt_lease.py`；该模块是 store / supervisor 共用的 attempt lease 类型真源，不涉及 public Host API。

## Residual Risks And Uncovered Areas

- residual risk: `AttemptSupervisor._require_acquired()` 仍把 BUSY 转换成 `AttemptFencingError(reason=STORAGE_CONFLICT)` 抛给调用方。
  - classification: accepted as covered by current slice boundary
  - reason: 本 slice 要求 BUSY 结果不复用 fencing reason，并未引入 public Host API 变更或新的 busy exception contract；store 层 typed result 已保留独立 busy reason。
- uncovered area: 更广泛的 adversarial lease hardening 未实施。
  - classification: accepted as covered by later slice in the approved plan
  - destination: Slice 5b

## Completion Signal

Slice 5a implementation complete。代码、测试、README 同步和 implementation artifact 均已完成。

## Stop Condition Status

已在当前 implementation gate 停止；未启动 Slice 5b，未进入 review、commit、PR 或 closeout。
