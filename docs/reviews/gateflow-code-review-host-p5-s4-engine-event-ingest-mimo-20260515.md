# Gateflow Code Review: Host P5-S4 EngineEvent Ingest Mapping And Terminal Closeout

- **Review role**: AgentMiMo
- **Gate**: P5-S4 EngineEvent Ingest Mapping And Terminal Closeout code review
- **Implementation artifact**: `docs/reviews/gateflow-implementation-host-p5-s4-engine-event-ingest-20260515.md`
- **Design source**: `docs/host/design.md` §13.4, §17, §22
- **Accepted plan**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S4, §3.1, §3.5, §3.6
- **Date**: 2026-05-15

## Scope Expansion Review: `dayu/host/durable/state.py`

Original P5-S4 allowed files 不含 `state.py`。Implementation 新增两个 row CAS helper：

- `cancel_cancelling_run_row(...)`: CAS `Run CANCELLING -> CANCELLED`
- `cancel_running_attempt_row(...)`: CAS `Attempt RUNNING -> CANCELLED`

**裁决：scope expansion 架构合理，可接受。**

理由：
1. `state.py` 拥有所有 Run / Attempt row 的 dataclass、enum、codec 与 CAS mutation helper。`cancel_running_run_row`、`cancel_queued_run_row`、`cancel_starting_attempt_row`、`terminal_run_row`、`terminal_attempt_row` 等同类 helper 均已存在于 `state.py`。新增两个 helper 遵循同一 pattern。
2. 若把这两条 CAS SQL 写在 `run_transition.py`，将直接绕过 durable state 边界，违反 `state.py` 作为 row mutation 真源的分层约定。
3. diff 限制在 121 行（含 docstring 和 validation），scope 最小。
4. `run_transition.py` 通过 import 使用这两个 helper，与现有 `cancel_running_run_row` 等调用方式一致。

## Validation Results

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q` | **10 passed** (0.22s) |
| `pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **passed** (无 trailing whitespace / tab 问题) |

## Review Findings

### B1. `ingest()` 中 DUPLICATE terminal result 未触发 queue promotion wakeup

**Severity**: Blocking
**File**: `dayu/host/engine_ingest.py:268-277`

```python
result = self._transaction_runner.run_write(_operation)
if result.terminal_closeout and result.status == EngineIngestStatus.ACCEPTED:
    self._wakeup_port.wake_queue_promotion(candidate.envelope.session_id)
    # ...
return result  # DUPLICATE 时 promotion_triggered=False，不触发 wakeup
```

当 terminal candidate 重放（DUPLICATE）时，`promotion_triggered=False`，不调用 `wake_queue_promotion`。如果第一次调用的 promotion wakeup 失败或未被消费，重放不会重试 promotion。§3.6 plan 明确要求"Terminal closeout 成功后必须触发同 Session queue promotion check"。

**建议修复**：DUPLICATE terminal result 也应触发 `wake_queue_promotion`，或在 `ingest()` 方法的 return 路径对 `terminal_closeout=True` 统一触发：

```python
result = self._transaction_runner.run_write(_operation)
if result.terminal_closeout:
    self._wakeup_port.wake_queue_promotion(candidate.envelope.session_id)
    return EngineIngestResult(
        status=result.status,
        events=result.events,
        terminal_closeout=True,
        promotion_triggered=True,
        reason=result.reason,
    )
return result
```

注意：`_close_worker_lifecycle` 也有同样的问题（line 799）。

### B2. `run_suspended` / `tool_awaiting` / `provider_protocol_error` 路径缺失测试

**Severity**: Non-blocking (测试覆盖)
**File**: `tests/host/test_engine_ingest_mapping.py`

当前测试只覆盖 `final_answer`、`run_failed`（两种）、`context_compaction_requested`、`usage_reported`、duplicate、stale。以下路径未被测试覆盖：

- `run_suspended` -> diagnostic + `ATTEMPT_FAILED` / `RUN_FAILED`，reason=`unsupported_waiting_path`
- `tool_awaiting` -> diagnostic + `ATTEMPT_FAILED` / `RUN_FAILED`，reason=`unsupported_waiting_path`
- `provider_protocol_error` -> diagnostic + raw payload descriptor

§3.1 要求"不支持的 Phase 5 事件：`tool_awaiting` / `run_suspended`：append diagnostic，随后以 `ATTEMPT_FAILED` / `RUN_FAILED` 收口"。建议补齐测试。

### B3. preview event 路径缺失测试

**Severity**: Non-blocking (测试覆盖)
**File**: `tests/host/test_engine_ingest_mapping.py`

`_is_preview_event` 覆盖 8 种 EngineEventType（`iteration_started`、`content_delta` 等），`_preview_payload` 有 8 个 isinstance 分支。测试中未覆盖任何 preview event 的 ingest 路径。建议至少测试一种 preview event 确认 `EventClass.PREVIEW` 不改状态。

### B4. `run_cancelled` without active cancel 路径未测试

**Severity**: Non-blocking (测试覆盖)
**File**: `tests/host/test_phase5_local_execution_integration.py`

`_close_active_cancel` 在 `cancelling is None` 时返回 rejected diagnostic。集成测试只测试了"有 active cancel 时的 run_cancelled"，未测试"无 active cancel 时 run_cancelled 被拒绝"。建议补齐。

## Design Compliance Verification

### EngineEvent contract 保持 Host-agnostic

- `EngineEvent` 公共 contract 未修改。`attempt_id` / `execution_id` / `dispatch_record_id` 只通过 `LocalEngineEnvelope` 携带。**Pass**。

### Event id derivation 与 duplicate idempotency

- `_event_id()` 使用 `sha256_digest_json({execution_id, worker_event_index, event_class, event_type, sub_index})`，确定性、抗碰撞。**Pass**。
- `_duplicate_terminal_event_ids()` 对所有 terminal event type 计算预期 event id。**Pass**。
- `_existing_rows()` 检查所有预期 id 是否已存在。**Pass**。
- 非 terminal event（preview、projection_signal、diagnostic、provider_protocol_error）未做 duplicate check——这些 event 的 idempotency 由 EventLog `event_id` UNIQUE 约束和 `event_body_digest` identity check 保证。**Pass**。

### Durable Run / Attempt / dispatch identity validation

- `_validate_durable_context()` 检查 run、attempt、dispatch_record 存在性，以及 session_id、run_id、execution_id、dispatch_record_id 全量匹配。**Pass**。
- Stale execution_id 返回 None -> rejected diagnostic。**Pass**。
- Terminal-late rejection 通过 `_late_rejection_reason()` 检查 `run.terminal_event_id` 和 `attempt.terminal_event_id`。**Pass**。

### final_answer -> ATTEMPT_SUCCEEDED + RUN_SUCCEEDED

- `terminal_summary` 包含 `content`、`finish_reason`、`filtered`、`degraded`。**Pass**。
- `terminal_summary` 写入 SQLite payload descriptor，EventLog payload 只保存 `terminal_summary_ref` / `terminal_summary_digest`。**Pass**。
- `dispatch_record_id` 和 `finish_reason` 进入 ATTEMPT_SUCCEEDED payload。**Pass**。

### run_failed(false/true)

- `recoverable=False`: 直接 `ATTEMPT_FAILED` + `RUN_FAILED`。**Pass**。
- `recoverable=True`: diagnostic (含 `unsupported_later_owner=phase10`) + `ATTEMPT_FAILED` + `RUN_FAILED`。**Pass**。
- Plan reason 使用 `_REASON_UNSUPPORTED_RECOVERY_POLICY`。**Pass**。

### context_compaction_requested (budget_state=None)

- 允许 `budget_state=None`，diagnostic payload 中 `budget_state_present=False`。**Pass**。
- 随后 `ATTEMPT_FAILED` + `RUN_FAILED`，reason=`unsupported_recovery_policy`，`unsupported_later_owner=phase10`。**Pass**。

### run_suspended / tool_awaiting unsupported

- `_diagnostic_then_failed_waiting()` append diagnostic（reason=`unsupported_waiting_path`）+ `_unsupported_waiting_plan()`（`unsupported_later_owner=phase7`）。**Pass**。

### usage_reported projection_signal

- `EventClass.PROJECTION_SIGNAL`，event_type=`USAGE_REPORTED`。**Pass**。
- 不改 Run / Attempt 状态。测试验证 Run/Attempt 保持 RUNNING。**Pass**。

### Clean EOF / worker lost closeout

- `close_clean_eof()`: `ATTEMPT_FAILED` + `RUN_FAILED`，reason=`stream_ended_without_terminal`。**Pass**。
- `close_worker_lost()`: `ATTEMPT_LOST` + `RUN_LOST`，reason=`worker_lost_before_terminal`。**Pass**。
- 两者通过 `_close_worker_lifecycle()` 合成 `RunFailedData(recoverable=False)` candidate 走标准校验和 terminal closeout。**Pass**。

### run_cancelled after active cancel

- `_close_active_cancel()` 查找 `RUN_CANCELLING` event，提取 `cancel_request_event_id`。**Pass**。
- 调用 `active_cancel_closeout_in_transaction()`，CAS `Run CANCELLING -> CANCELLED` + `Attempt RUNNING -> CANCELLED`。**Pass**。
- 测试验证 payload 中 `cancel_request_event_id` 正确。**Pass**。
- 无 active cancel 时 `cancelling is None` -> rejected diagnostic。代码正确；建议补齐测试（见 B4）。

### Terminal closeout queue promotion wakeup

- `ingest()` 和 `_close_worker_lifecycle()` 在 `terminal_closeout=True AND status=ACCEPTED` 时调用 `wake_queue_promotion`。**Pass**（但 DUPLICATE 时缺失，见 B1）。

### EngineEvent mapping completeness (§13.4)

| EngineEvent | Expected Mapping | Implemented | Test |
| --- | --- | --- | --- |
| `final_answer` | `ATTEMPT_SUCCEEDED` + `RUN_SUCCEEDED` | Yes | Yes |
| `run_failed(false)` | `ATTEMPT_FAILED` + `RUN_FAILED` | Yes | Yes |
| `run_failed(true)` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` | Yes | Yes |
| `run_cancelled` (after active cancel) | `ATTEMPT_CANCELLED` + `RUN_CANCELLED` | Yes | Yes |
| `context_compaction_requested` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` | Yes | Yes |
| `run_suspended` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` | Yes | **No** |
| `tool_awaiting` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` | Yes | **No** |
| `usage_reported` | `PROJECTION_SIGNAL / USAGE_REPORTED` | Yes | Yes |
| `provider_protocol_error` | `PROVIDER_PROTOCOL_ERROR` diagnostic | Yes | **No** |
| 8 preview events | `PREVIEW` | Yes | **No** |
| unsupported type | rejected diagnostic | Yes | implicit (stale test path) |

### 本地异常 terminal closeout (§3.6)

| 场景 | Expected | Implemented | Test |
| --- | --- | --- | --- |
| clean EOF without terminal | `FAILED` / `stream_ended_without_terminal` | Yes | Yes |
| stream error / worker crash | `LOST` / `worker_lost_before_terminal` | Yes | Yes |
| unsupported recovery | `FAILED` / `unsupported_recovery_policy` | Yes | Yes |
| unsupported waiting | `FAILED` / `unsupported_waiting_path` | Yes | **No** |

## Coding Constraint Verification

| 约束 | 结果 |
| --- | --- |
| 禁止 `Any` / `object` / 无类型参数 | Pass — 所有 public signature 均有完整类型 |
| 中文 docstring | Pass — 所有函数、类、模块均有中文 docstring，含参数/返回值/异常 |
| 禁止魔法数字/字符串 | Pass — 使用模块级常量（`_EVENT_SOURCE`、`_EVENT_TYPE_*`、`_REASON_*`）|
| 禁止兼容性代码 | Pass — 无兼容性 re-export / wrapper |
| 禁止 `extra payload` 滥用 | Pass — payload 字段均为显式 typed |
| 禁止 God object | Pass — `EngineEventIngestor` 职责单一；`_TerminalPlan` 是 internal dataclass |
| 禁止胶水 seam / lazy import | Pass — 无 lazy import |
| 禁止反向依赖 | Pass — `engine_ingest.py` import `durable` 子模块，无反向 |

## Summary

- **Blocking findings**: 1 (B1: DUPLICATE terminal result 缺失 promotion wakeup)
- **Non-blocking findings**: 3 (B2: 缺少 3 种路径测试; B3: 缺少 preview 测试; B4: 缺少 run_cancelled without active cancel 测试)
- **Scope expansion**: `state.py` 新增 2 个 CAS helper，架构合理，可接受
- **Validation**: pytest 10 passed, pyright 0 errors, git diff --check passed
- **Artifact**: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`
