# Aggregate Fix: Host Phase 3 Session / Run / Attempt Admission

- **Date**: 2026-05-14
- **Scope**: Aggregate deepreview non-blocking fix for Host Phase 3 admission/state machine
- **Base HEAD**: `49fc1d5 gateflow: accept host phase3 s6 multiprocess docs`
- **Review Artifacts**:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-ds-20260514.md`

## Controller Decision

Controller 裁决无 blocking finding；本次只接受 AgentDS 的两个 non-blocking findings，作为当前 aggregate fix。

## Fixes

### N-1. `_require_event_sequence` 不再硬编码 `event_log`

- File: `dayu/host/admission.py`
- Change: `_require_event_sequence` 的 SQL 表名改为使用 `dayu.host.durable.schema.TABLE_EVENT_LOG`。
- Boundary: `dayu.host.durable.schema` 是 durable schema convention 真源，只依赖 durable error，不引入反向依赖或循环依赖。
- Behavior impact: 无行为变化；当前常量值仍为 `event_log`。

### N-2. `terminal_run_row` docstring 补充 Phase 3 边界说明

- File: `dayu/host/durable/state.py`
- Change: docstring 明确 `WAITING` 源状态是为后续 phase 的 wait resolve 路径预留；Phase 3 调用方通过前置检查只传 `RUNNING`。
- Behavior impact: 无逻辑变化。

## Scope Control

- 未修改 schema、状态机逻辑、CAS 条件或测试断言。
- 未新增兼容逻辑。
- 未扩大 Phase 3 行为范围。

## Verification

- `source .venv/bin/activate && pytest tests/host -q`: 157 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: passed
