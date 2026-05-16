# Host Phase 7 Plan Re-Review (DS) — 2026-05-16

## 审查范围

- **复审目标**: fixed `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- **fix artifact**: `docs/reviews/host-phase7-plan-fix-codex-20260516.md`
- **裁决依据**: `docs/reviews/host-phase7-plan-review-controller-adjudication-20260516.md`
- **前次 review**: `docs/reviews/host-phase7-plan-review-ds-20260516.md`
- **方法**: adversarial plan re-review，逐项验证 PF1–PF12 已按 controller adjudication 要求关闭，并对 fixed plan 做独立 adversarial pass 检查是否引入新问题

## PF1–PF12 逐项验证

### PF1 — late result diagnostic 与 wait resolution idempotency 顺序冲突

Controller 要求: pipeline 先读 wait record status 分类，不可接收新 resolution 的状态直接进入 late rejection path。

Fixed plan evidence:
- §3.9 step 3: "read wait record, Run and current Attempt before reading wait resolution idempotency. Status classification happens before idempotency replay." ✓
- §3.9 step 5: `cancelled`/`lost`/terminal Run → late rejection path in §3.10.1 ✓
- §3.9 step 6: `resolved`/`failed` → only idempotent replay, different key → `INVALID_STATE` ✓
- §3.10.1: independent `wait_late_rejection` scope with full specification ✓

**Verdict: CLOSED**

### PF2 — EngineEvent awaiting/suspended 缺少精确行为矩阵

Controller 要求: 给出 (Run.status, Attempt/execution match, accepted refs, event type) 行为表，不得调用 terminal closeout。

Fixed plan evidence:
- §3.13: 9-row behavior matrix covering `WAITING` with/without refs, `RUNNING` with/without refs, terminal/cancelling states, non-terminal no-match ✓
- §3.13: "No TOOL_AWAITING / RUN_SUSPENDED EngineEvent path may call _close_terminal, terminal_closeout_in_transaction, terminal_run_row or an equivalent terminal closeout helper." ✓
- P7-S4 tests: "Engine awaiting/suspended behavior matrix in §3.13 is covered for WAITING with refs, WAITING without refs, RUNNING without refs and terminal Run states." ✓

**Verdict: CLOSED**

### PF3 — WAITING cancel 与现有 cancel 状态机集成锚点

Controller 要求: 指定 WAITING 分支的模块锚点、core helper 复用、CAS 前置条件、after-commit notification。

Fixed plan evidence:
- §3.11 "Integration anchors": `command.py` → `admission.py` → `run_transition.py` `cancel_waiting_run_in_transaction(...)` → `state.py`/`wait_state.py` `cancel_active_wait_records_for_run(...)` ✓
- §3.11: "Both public paths must delegate to the same core operation object / helper" ✓
- §3.11 cancel path step 3: explicit CAS preconditions (Run=WAITING, no terminal refs, Attempt=SUSPENDED, ≥1 active wait) ✓
- §3.11 cancel path step 7: explicitly not creating `ATTEMPT_CANCELLED` ✓
- §3.11 cancel path step 8: after-commit `WaitCancelNotification` to poller ✓
- P7-S4 exact changes: three explicit state helper additions ✓

**Verdict: CLOSED**

### PF4 — WAITING → RUNNING transition helper

Controller 要求: 新增 `resume_run_from_waiting(...)` helper，明确 CAS 前置条件、写入字段、返回类型。

Fixed plan evidence:
- §3.9 "Required transition helper": `resume_run_from_waiting_in_transaction(...)` in `dayu/host/durable/run_transition.py` ✓
- Full inputs specification: transaction, EventLog store, wait_id, run_id, attempt_id, new attempt/execution/dispatch IDs, event IDs, occurred_at, actor/source, resolution payload, worker kind/execution target ✓
- CAS preconditions: Run=WAITING + current_attempt_id matches; Attempt=SUSPENDED; wait=waiting; no terminal Run refs; unique active wait invariant ✓
- Writes specification: append events, CAS wait record, append RUN_STARTED, insert Attempt, update Run, append ATTEMPT_STARTED, insert dispatch record — all in one transaction ✓
- Return type: `StateMutationStatus`, `RunRow`, `AttemptRow`, `DispatchRecordRow | None`, event refs ✓
- Failed/lost terminal helpers also specified ✓

**Verdict: CLOSED**

### PF5 — TOOL_RESULT_ACCEPTED wait resolution payload 扩展字段

Controller 要求: 列出 wait resolution 场景增量字段，区分 ordinary 与 wait-specific 字段。

Fixed plan evidence:
- §3.10: complete list of Phase 6 ordinary fields retained ✓
- §3.10: 15 wait-specific incremental fields including `wait_id`, `resolution_source`, `resolution_kind`, `resolution_idempotency_key`, `observed_at`, `wait_record_status_before`/`after`, `adapter_key`, `external_job_ref`, `snapshot_ref`, `provider_status_ref`, `resume_attempt_id`, `resume_dispatch_record_id` ✓
- `ToolFactKind.LOST` ownership assigned to P7-S1 ✓

**Verdict: CLOSED**

### PF6 — key/ref 长度约束

Controller 要求: 给出具体长度上限，dataclass validation 与 DDL CHECK 一致性。

Fixed plan evidence:
- §3.6.1: 9-row table with field names, max lengths, dataclass validation, DDL CHECK expressions ✓
- Explicit constraints: wait_id(128), adapter_key(128), tool_call_id(256), tool_name(128), resume_token(2048), snapshot_id(256), external_job_id(512), provider_status_ref(512), idempotency_keys(256) ✓
- "dataclass validation 与 DDL CHECK 必须使用同一常量语义" ✓
- P7-S1 tests: "Max length validation and DDL CHECK reject overlong adapter_key, snapshot_id, external_job_id, provider status ref and idempotency keys." ✓

**Verdict: CLOSED**

### PF7 — ToolFactKind.LOST slice ownership

Controller 要求: 放入具体 slice exact changes 和 allowed files。

Fixed plan evidence:
- §4.1 P7-S1: `dayu/host/tool_runtime.py` added for `HostPayloadRef` import migration and `ToolFactKind.LOST` enum extension ✓
- P7-S1 exact changes: "Add ToolFactKind.LOST in dayu/host/tool_runtime.py during this slice" ✓
- P7-S1 tests: "ToolFactKind.LOST is present before P7-S3" ✓
- Code fact verified: `ToolFactKind` enum exists at `dayu/host/tool_runtime.py:178` with COMPLETED/FAILED/CANCELLED/REUSE/GOVERNED_ERROR; LOST is a net-new member ✓

**Verdict: CLOSED**

### PF8 — outcome digest / payload ref 互斥语义

Controller 要求: lost outcome 无 payload_ref，非 lost outcome 无 provider_status_ref，digest 用 null sentinel。

Fixed plan evidence:
- §3.2 "Outcome ref 互斥规则": three explicit rules ✓
  - "completed / failed / cancelled outcome 可以携带 payload_ref，必须没有 provider_status_ref" ✓
  - "lost outcome 可以携带 provider_status_ref，必须没有 payload_ref" ✓
  - "digest 输入必须对每个可选 typed field 写入显式 null sentinel" with concrete examples ✓
- P7-S1 tests: "Lost outcome rejects payload_ref; non-lost outcomes reject provider_status_ref." ✓

**Verdict: CLOSED**

### PF9 — poller 生命周期与并发模型

Controller 要求: 明确第一版运行模型、启动/停止边界、transaction 调用约束。

Fixed plan evidence:
- §3.12: "WaitPoller first version is Host-runtime owned, not process-global. It is constructed by Host composition root with a HostCommandHandle / transaction runner, adapter registry and bounded poll policy." ✓
- "It starts when the owning Host handle / scheduler runtime starts and stops on handle close / scheduler close." ✓
- "Poller supports an explicit poll_once() / drain_once() method for deterministic tests." ✓
- "Restart recovery is limited to scanning durable active resume_policy=POLL AND status='waiting' wait records on poller start / tick. Full orphan recovery ... remain Phase 11." ✓
- "Poller reads active poll waits in a short read transaction, releases the transaction, calls external adapter outside any Host transaction" ✓
- "Poller maintains an in-process in-flight set keyed by wait_id" with cross-process CAS/idempotency fallback ✓
- "Poller must not hold EventLog appender or wait-state writer ports." ✓

**Verdict: CLOSED**

### PF10 — resolved/failed wait different-key 拒绝测试

Controller 要求: 新增测试 different key → INVALID_STATE，不追加 canonical fact，不创建 Attempt。

Fixed plan evidence:
- P7-S3 tests: "Already resolved wait with a different idempotency_key returns INVALID_STATE, appends no canonical fact and creates no Attempt." ✓
- P7-S3 tests: "Already failed wait with a different idempotency_key returns INVALID_STATE, appends no canonical fact and creates no Attempt." ✓

**Verdict: CLOSED**

### PF11 — late diagnostic idempotency 策略

Controller 要求: 独立 `wait_late_rejection` idempotency scope，scope_id=wait_id。

Fixed plan evidence:
- §3.10.1: full scope specification with `scope_kind="wait_late_rejection"`, `scope_id=wait_id`, `idempotency_key=ResolveWaitRequest.idempotency_key` ✓
- "Same key + same late digest returns existing diagnostic refs" ✓
- "Same key + different late digest returns idempotency conflict diagnostic / error and must not append unbounded diagnostic events." ✓
- §3.10.1 last sentence: resolved/failed + different key → no late rejection idempotency use (unless terminal Run) ✓
- P7-S4 exact changes: "Implement independent wait_late_rejection idempotency scope from §3.10.1; do not use wait_resolution records for late diagnostics." ✓
- P7-S4 tests: same-key same-digest replay + same-key different-digest conflict ✓

**Verdict: CLOSED**

### PF12 — open questions 收敛

Controller 要求: HostPayloadRef import 迁移、_event_payload.py helpers 归属、ResolveWaitRequest.context 保留。

Fixed plan evidence:
- §3.2: `HostPayloadRef` move to `dayu.host.api`, ToolRuntime import updated ✓
- §3.2: "ResolveWaitRequest.context: HostCallContext 必须保留，仍作为 mutating request 的调用上下文" ✓
- P7-S1 exact changes: "Move current HostPayloadRef from dayu.host.tool_runtime to dayu.host.api; update dayu/host/tool_runtime.py imports" ✓
- P7-S1 exact changes: "Change ResolveWaitRequest to retain context: HostCallContext" ✓
- §3.10: all `_event_payload.py` helper functions listed with ownership ✓
- P7-S2 exact changes: `tool_awaiting_payload`, `run_waiting_payload`, `attempt_suspended_payload` ✓
- P7-S3 exact changes: `resume_requested_payload`, `tool_result_wait_resolution_payload` ✓
- P7-S4 allowed files: `_event_payload.py` ✓

**Verdict: CLOSED**

---

## 独立 Adversarial Pass

对 fixed plan 执行独立 adversarial 扫描，检查 fix 是否引入新问题。

### 已检查的 Attack Surface

| Surface | 结论 |
|---------|------|
| Host/Engine 边界 | 无新违规。EngineEvent 行为矩阵完整，terminal closeout 禁令明确。 |
| Wait record 状态机 | 5 状态 (waiting/resolved/failed/cancelled/lost) 的所有转换路径均有 pipeline 步骤或 helper 覆盖。 |
| resolve_wait 幂等 | 三个 scope (wait_accept / wait_resolution / wait_late_rejection) 各自独立，互不污染。 |
| WAITING cancel | 集成锚点 (command→admission→run_transition→state) 完整，CAS 前置条件明确，single-run 与 session-scope 复用同一 core helper。 |
| Run transition helpers | `resume_run_from_waiting_in_transaction` 输入/前置条件/写入/返回类型均充分具体。Failed/lost terminal helpers 已提及但规格不如 resume helper 详细——可接受，实现 Agent 可按同模式推导。 |
| Poller lifecycle | 启动/停止边界明确，transaction 约束清晰，restart 扫描范围已限定。 |
| Length constraints | 所有 typed string fields 有具体上限，dataclass 与 DDL 一致性要求明确。 |
| Outcome ref 互斥 | completed/failed/cancelled → payload_ref only; lost → provider_status_ref only; digest 含 null sentinel。 |
| Slice boundaries | 各 slice 的 allowed files 变更精确，跨 slice 的 file ownership（如 admission.py 在 S3/S4 的不同职责）明确区分。 |
| Test coverage | 所有 critical paths + failure paths + race conditions 均有测试。不同-key 拒绝、late diagnostic idempotency、EngineEvent 行为矩阵均已覆盖。 |
| docs/README trigger | P7-S5 明确只更新 `dayu/host/README.md`，不更新 design.md 或 control.md。 |

### 一个已识别但非阻塞的边界情况

§3.9 step 5 的 late rejection 触发条件包含 "owning Run is already terminal"，而 step 6 对 `resolved`/`failed` wait 的 replay 规则未受 Run 终态影响。在 "Run terminal + wait=resolved" 场景下，若 step 5 先于 step 6 执行，会对一个已成功 concluded 的 wait 产生 late rejection diagnostic。建议实现 Agent 优先按 wait record 自身状态分类（resolved/failed → step 6；cancelled/lost → step 5），仅在 wait=waiting 时检查 Run 终态。这不构成 plan blocking finding，因为两种实现都不会导致状态 corruption，且 plan review gate 后的 code review 可最终确认。

---

## Open Questions

无新的 open questions。前次 review 的 3 个 open questions 已通过 PF12 全部收敛。

---

## Residual Risks (Plan §11 已记录)

| 风险 | 评估 |
|------|------|
| Callback 产品化推迟 | 可接受 |
| External job physical cancel best-effort | 可接受 |
| Cross-process duplicate governance in-memory | 可接受 |
| Recovery scan 推迟到 Phase 11 | 可接受；poller restart 扫描已做最小覆盖 |
| Tool trace projection 推迟 | 可接受；diagnostic events 已提供输入 |

---

## 最终结论

**PASS**

全部 12 项 controller accepted findings (PF1–PF12) 已被 plan fix 逐项关闭，证据明确、可验证。独立 adversarial pass 未发现新的 blocking issue。Fixed plan 达到 code-generation-ready 标准，可以进入 implementation gate。
