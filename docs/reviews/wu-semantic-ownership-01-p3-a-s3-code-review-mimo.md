# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 Code Review — AgentMiMo

## Gate / scope

- Gate：independent code review。
- Review target：base commit `aa229575` 之后当前 workspace 的 S3 implementation。
- Reviewer：AgentMiMo。
- 必读：`AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`、plan S3、implementation artifact、controller validation。
- 不修改生产代码 / 测试 / README / control doc；不 commit / push / PR；不进入 fix。

## Verdict

**PASS** — 无 blocking finding。3 个 low-severity observation，0 个 needs-more-evidence。

## Validation 执行结果

```text
# S3 required test matrix
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py -q
161 passed in 1.81s

# Import cycle
python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok

# Terminal constant source scan
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
(no output — clean)

# Synthetic EngineEvent construction scan
rg "EngineEvent\(|type=EngineEventType\.RUN_FAILED|RunFailedData\(" dayu/host/engine_ingest.py
(no output — clean)

# pyright
0 errors, 0 warnings, 0 informations

# git diff --check
(no output — clean)
```

## Adversarial Findings

### Finding 1 — LOW: `_late_host_lifecycle_rejection_reason` 不检查 `WAITING` / `SUSPENDED` 的 Engine waiting confirmation exception

**file:line**：`dayu/host/engine_ingest.py:3733-3749`

**描述**：`_late_host_lifecycle_rejection_reason` 当前逻辑为：terminal status → reject，`CANCELLING` → reject，其余 → accept。但 `_late_engine_event_rejection_reason`（Engine-origin path）对 `WAITING` + `SUSPENDED` 有专门的 Engine waiting confirmation exception，允许 tool_awaiting / run_suspended 事件在等待状态下被确认。

Host lifecycle path 的 `close_clean_eof` / `close_worker_lost` 在 `WAITING` / `SUSPENDED` 状态下会走到 `_late_host_lifecycle_rejection_reason`，此时返回 `None`（允许 closeout），会把 `WAITING` Run 收口为 `FAILED` 或 `LOST`。

**直接代码路径**：

```python
# engine_ingest.py:3743-3748
if is_terminal_run_status(context.run.status) or is_terminal_attempt_status(
    context.attempt.status
):
    return _REASON_TERMINAL_ALREADY_CLOSED
if context.run.status is RunStatus.CANCELLING:
    return _REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL
return None  # WAITING/SUSPENDED 走到这里，允许 closeout
```

**判定**：这实际上是 **正确行为**。Host lifecycle signal（worker EOF / crash）在 `WAITING` 状态下到达时，worker 已经断开，Run 应该被收口为 `FAILED` 或 `LOST`，而不是保留 `WAITING` 等待永远不会回来的 worker。Engine waiting confirmation exception 只适用于 Engine-origin 的 `tool_awaiting` / `run_suspended` 确认事件，不适用于 worker lifecycle signal。

**建议**：不需要修复。但建议在 `_late_host_lifecycle_rejection_reason` 的 docstring 中明确说明 `WAITING` / `SUSPENDED` 下允许 closeout 的设计意图，避免后续维护者误判为遗漏。

**controller 裁决建议**：accepted-as-correct（行为正确，docstring 可选改进）。

---

### Finding 2 — LOW: `is_dispatch_record_direct_cancelable` 对 `CANCELLED` 状态返回 `False` 但测试覆盖已验证

**file:line**：`dayu/host/durable/state.py:663-686`

**描述**：`is_dispatch_record_direct_cancelable` 的实现覆盖了 `PENDING`、`WAITING_FOR_LANE`、`DISPATCHING`（无 worker accepted facts）→ `True`；`DISPATCHING`（有 worker accepted facts）或 `CANCELLED` → `False`。

测试 `test_dispatch_record_direct_cancelable_predicate_owned_by_durable_state`（`test_active_cancel_dispatch.py:360-414`）通过参数化覆盖了完整决策表：`(PENDING, False, True)`、`(WAITING_FOR_LANE, False, True)`、`(DISPATCHING, False, True)`、`(DISPATCHING, True, False)`、`(CANCELLED, False, False)`。

**判定**：实现正确，测试覆盖完整。`CANCELLED` 状态的 dispatch record 已经被取消，不应再允许 direct cancel。

**controller 裁决建议**：accepted-as-correct。

---

### Finding 3 — LOW: Host lifecycle terminal payload 的 `host_lifecycle_ref` 格式在测试中硬编码

**file:line**：`tests/host/test_engine_ingest_mapping.py:2884-2887`、`tests/host/test_engine_ingest_mapping.py:2948-2951`

**描述**：测试断言 `host_lifecycle_ref` 的完整格式字符串，例如：

```python
assert terminal_payload["host_lifecycle_ref"] == (
    f"host-lifecycle:{seeded.execution_id}:1:worker_clean_eof:"
    "stream_ended_without_terminal"
)
```

这些断言依赖 `_host_lifecycle_ref` 的输出格式。如果 ref 格式变化，测试会失败。

**判定**：这是 **有意设计**。host_lifecycle_ref 是治理来源标签，测试需要验证其格式稳定性。格式硬编码在测试中是正确的防御性测试模式。implementation artifact 已明确 ref 格式为 `host-lifecycle:{execution_id}:{worker_event_index}:{lifecycle_source}:{plan.reason}`。

**controller 裁决建议**：accepted-as-correct（测试格式断言是稳定性保障）。

---

## Adversarial Check 逐项结果

### 1. Worker EOF/crash 不再伪造 EngineEvent

**PASS**。

- `rg "EngineEvent\(|type=EngineEventType\.RUN_FAILED|RunFailedData\(" dayu/host/engine_ingest.py` 无匹配。
- `_close_worker_lifecycle` 使用 `_HostLifecycleCloseoutCandidate`，不构造 `EngineEvent`。
- Host lifecycle identity 使用 `event-host-lifecycle-` 命名空间，与 `event-engine-` 不重合。
- terminal payload 的 `source` 为 `host.worker_lifecycle`，`host_lifecycle_ref` 为 `host-lifecycle:...` 格式。
- 测试 `test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source` 和 `test_worker_lost_closeout_uses_lost_event_ids_and_duplicate` 验证了 identity、source、payload ref 不含伪造 Engine 语义。

### 2. Duplicate / partial-duplicate / first-committer CAS

**PASS**。

- `_duplicate_host_lifecycle_terminal_result` 通过 `_host_lifecycle_terminal_event_ids` 计算预期 event ids，检查 `_existing_rows` 是否全部存在。
- `_duplicate_terminal_result`（Engine-origin path）通过 `_duplicate_terminal_event_ids` 计算预期 ids。
- `terminal_closeout_in_transaction` 使用 `TerminalCloseoutInput` 执行 CAS，返回 `StateMutationStatus.UPDATED` / `CAS_LOST`。
- `_close_host_lifecycle_terminal` 在 CAS 失败时返回 `REJECTED` + `terminal_closeout_precondition_failed`。
- 测试 `test_worker_lost_closeout_uses_lost_event_ids_and_duplicate` 验证重复 closeout 幂等。
- 测试 `test_duplicate_candidate_returns_existing_result` 验证 Engine-origin 重复幂等。

### 3. CANCELLING decision table

**PASS**。

- `_late_host_lifecycle_rejection_reason` 对 `CANCELLING` 返回 `_REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL`。
- `_append_host_lifecycle_diagnostic` 写入 `HOST_LIFECYCLE_DIAGNOSTIC` diagnostic，不写 `FAILED` / `LOST` terminal facts。
- 测试 `test_host_lifecycle_after_run_cancelling_is_diagnostic_only` 覆盖 `worker_clean_eof` 和 `worker_lost` 两种 lifecycle source，验证：
  - `status == REJECTED`
  - `terminal_closeout is False`
  - `event_type == "HOST_LIFECYCLE_DIAGNOSTIC"`
  - `event_id.startswith("event-host-lifecycle-")`
  - `source == "host.worker_lifecycle"`
  - `reason == "host_lifecycle_after_active_cancel"`
  - `RUN_FAILED`、`ATTEMPT_FAILED`、`RUN_LOST`、`ATTEMPT_LOST` 计数均为 0
  - Run status 保持 `CANCELLING`，Attempt status 保持 `RUNNING`
- Engine-origin `FINAL_ANSWER` / `RUN_FAILED` 在 `CANCELLING` 下走 late terminal after active cancel（已有测试覆盖）。

### 4. Late rejection status truth 与 WAITING/SUSPENDED exception

**PASS**。

- `_late_engine_event_rejection_reason`（Engine-origin）使用 `is_terminal_run_status` / `is_terminal_attempt_status`，保留 `WAITING` + `SUSPENDED` 的 waiting confirmation exception。
- `_late_host_lifecycle_rejection_reason`（Host lifecycle）使用同一 status predicates，`WAITING` / `SUSPENDED` 下允许 closeout（worker 已断开）。
- 测试 `test_late_rejection_uses_status_even_when_terminal_refs_are_missing` 验证 status-terminal + refs-missing 的异常 typed context 仍被拒绝。
- terminal refs 只由 `validate_terminal_event_refs_shape` 做 row consistency 校验，不参与 late routing。

### 5. Direct-cancel durable predicate

**PASS**。

- `is_dispatch_record_direct_cancelable` 封装 `PENDING`、`WAITING_FOR_LANE`、pre-worker `DISPATCHING` 判定。
- `command.py:_is_predispatch_starting_run` 消费 `is_dispatch_record_direct_cancelable`，不再直接检查 worker accepted nullable refs。
- 测试 `test_dispatch_record_direct_cancelable_predicate_owned_by_durable_state` 覆盖完整决策表。
- 测试 `test_cancel_run_waiting_for_lane_skips_later_dispatch`、`test_cancel_run_dispatching_pre_accept_stays_cancelled` 覆盖 public cancel path。

### 6. Propagation audit

**PASS**。

- Run terminal event type：`run_terminal_event_type_for_status` → `lifecycle_events.HostRunEventType` → `engine_ingest._run_terminal_event_type` → `terminal_closeout_in_transaction` → EventLog + Run row status。同一 helper，无重复映射。
- Attempt terminal event type：`closeout_attempt_terminal_event_type_for_status` → `lifecycle_events.HostAttemptEventType` → `engine_ingest._closeout_attempt_event_type` → `terminal_closeout_in_transaction` → EventLog + Attempt row status。
- Worker lifecycle closeout：`_HostLifecycleCloseoutCandidate` → `event-host-lifecycle-` ids + `host.worker_lifecycle` source → shared durable terminal transaction → EventLog + status rows。
- `HOST_LIFECYCLE_DIAGNOSTIC` 只写 diagnostic event class，`source` 为 `host.worker_lifecycle`，payload 不含伪造 Engine event type / ref，不伪装财报事实或用户结论。
- 用户 / LLM 可见输出：terminal snapshot / outbox / memory 只消费 committed terminal facts 和 durable status，不读取 lifecycle candidate 或 host lifecycle ref。

### 7. AGENTS.md 合规

**PASS**。

- 函数提供完整中文 docstring（参数、返回值、异常）。
- 类与模块提供中文概览 docstring。
- 无 `Any`、`object`、无类型参数 / 返回值。
- 无 `hasattr` / `getattr` seam。
- 无魔法字符串重复（`_HOST_LIFECYCLE_EVENT_SOURCE`、`_HOST_LIFECYCLE_EVENT_ACTOR` 等均为模块级常量）。
- 无 God function / dataclass。
- README 更新：`dayu/host/README.md` 已同步 worker lifecycle 与 EngineEvent 是两条 typed path 的稳定边界说明。`tests/README.md` 未变化。

### 8. 测试覆盖

**PASS**。

- 测试覆盖 public path：`close_clean_eof`、`close_worker_lost`、`ingest`（terminal / non-terminal）、`cancel_run`、`cancel_session_runs`。
- 不只测 private helper：`test_terminal_plans_use_lifecycle_event_owner_helpers` 直接断言 plan 的 event type 来自 lifecycle owner helper。
- 不构造不可能 row shape：`test_late_rejection_uses_status_even_when_terminal_refs_are_missing` 构造的 status-terminal + refs-missing 上下文用于验证 predicate 行为，不是生产可达 shape。
- active cancel decision table 测试覆盖 Engine-origin（FINAL_ANSWER / RUN_FAILED）与 Host lifecycle（clean EOF / worker lost）四种输入。

### 9. Scope 不扩张

**PASS**。

- 未触及 P3-B final answer / outbox continuity。
- 未修改 `docs/host/issues-implementation-control.md`。
- 非 terminal EventLog 常量未统一 owner 化（按 plan 分类为 P3-J / EventLog schema hardening）。
- 未引入 new `RunStatus` 成员、schema migration 或 dispatch state machine。

## Residual Risks / Uncovered Areas

- 跨进程 Engine terminal 与 Host lifecycle terminal 同时提交的 stress case 未包含在 S3；正确性由 EventLog unique identity、terminal CAS 与 first-committer-wins transaction 保证。归后续 production stress / EventLog hardening。
- `event-host-lifecycle-` 是新的 identity namespace；旧 synthetic Engine lifecycle ids 不做兼容读取。按项目 fresh-schema / no-compatibility 约束，属于已裁决 non-goal。
- 非 terminal EventLog 常量仍未统一 owner 化，归 P3-J。
- P3-B 未触碰。

## Artifact

- artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-mimo.md`
- finding 数：3（全部 LOW）
- verdict：PASS
