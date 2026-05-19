# Phase 11 Plan Re-Review — AgentMiMo 2026-05-19

## Review Target

`docs/host/phase11-host-lifecycle-recovery-plan.md` (post-fix)

## Review Scope

Re-review after AgentCodex plan fix pass. Verify:

- Accepted findings F1–F5 and DS 1-U are fixed in plan artifact.
- MiMo F6 remains no-action per controller adjudication.
- No new blockers introduced by fix.
- Plan remains aligned to `docs/host/design.md` §1, §2, §10, §17, §27, §27.1 and P10.5 public contract.

## Review Inputs

- Fixed plan: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- Fix artifact: `docs/reviews/phase11-plan-fix-codex-20260519.md`
- Controller adjudication: `docs/reviews/phase11-plan-review-controller-adjudication-20260519.md`
- Original MiMo review: `docs/reviews/phase11-plan-review-mimo-20260519.md`
- DS review: `docs/reviews/phase11-plan-review-ds-20260519.md`
- Design truth: `docs/host/design.md` §1, §2, §10, §17, §27, §27.1

## Per-Finding Verification

### MiMo F1 / DS A2: process_start_token entropy

**Controller required fix**: update Slice 1 to require high-entropy stdlib token generation, separate from `host_instance_id`, forbid timestamp/handle-id/pid derived tokens.

**Plan fix (Slice 1 L135)**:

> `process_start_token` 必须和 `host_instance_id` 分开生成，使用 `uuid4().hex` 或等效 stdlib 高熵随机值，不得使用 timestamp、handle id、pid 或这些值派生出的 token，也不得继续使用 `dispatch-{host_handle_id}` 这类可预测占位。

**Verdict: FIXED.** Explicit high-entropy requirement, explicit prohibition of predictable sources, separate generation from `host_instance_id`.

---

### MiMo F2 / DS 2-U: WAITING recovery observation fallback

**Controller required fix**: update Slice 2 to require diagnostic-only fallback when wait adapter observation is unavailable or wake fails, no Run/Attempt state mutation and no Attempt creation.

**Plan fix (Slice 2 L164)**:

> `WAITING` recovery 若 adapter observation 不可用、adapter 不支持重挂、或 wake 失败，必须走 diagnostic-only fallback：记录 structured diagnostic log 或 `event_class=diagnostic` 的 EventLog 事件；不得推进 Run / Attempt 状态，不得创建 Attempt，不得把 diagnostic 再读作 recovery truth。

**Verdict: FIXED.** Diagnostic-only fallback, no state mutation, no Attempt creation, diagnostic not treated as recovery truth.

---

### MiMo F3: heartbeat task failure mode

**Controller required fix**: update Slice 1 to require heartbeat loop exception handling, structured diagnostic logging, and best-effort current-instance `stopping` mark on fatal heartbeat task exit.

**Plan fix (Slice 1 L137)**:

> Heartbeat loop 必须捕获并输出 structured diagnostic logging。单次 refresh 异常可按 policy 继续重试；若 heartbeat task fatal exit，必须 best-effort 将当前 scheduler 自己的 host instance 标记为 `STOPPING`，不得标记或修改其它 host instance row。

**Verdict: FIXED.** Exception handling, structured logging, best-effort current-instance STOPPING on fatal exit, scope limited to own instance.

---

### MiMo F4: RECOVERING cancel idempotency scope

**Controller required fix**: update Slice 4 to state `cancel_run` idempotency scope remains `(run_id, client_request_id)` and `cancel_session_runs` scope remains `(session_id, client_request_id)` with per-run result stability.

**Plan fix (Slice 4 L234)**:

> Idempotency scope is explicit and unchanged: `cancel_run` is scoped by `(run_id, client_request_id)`; `cancel_session_runs` is scoped by `(session_id, client_request_id)`. For `cancel_session_runs`, per-run result stability applies only to Runs included in the original session-scope command result and must not affect later newly created Runs in the same session.

**Verdict: FIXED.** Explicit scope declaration for both commands, per-run result stability bounded to original result set.

---

### MiMo F5: recovery dispatch count helper boundary

**Controller required fix**: update Slice 2 to require a typed EventLog helper filtered by `run_id` and canonical `RUN_STARTED` events, counting only payloads with `start_reason=recovery`.

**Plan fix (Slice 2 L173)**:

> Add typed EventLog recovery dispatch count helper in the durable/EventLog boundary: helper must filter by `run_id` and canonical `RUN_STARTED` events, and only count events whose payload has `start_reason=recovery`. It must not count projection/read-model rows, diagnostic events, old Attempt snapshots, or non-canonical payload text matches outside the typed event codec.

**Verdict: FIXED.** Typed helper, filtered by run_id and canonical RUN_STARTED, counts only start_reason=recovery payload, explicit exclusions.

---

### DS 1-U: RunInputBuilder canonical-fact hardening

**Controller required fix**: add Slice 3 exact change allowing necessary typed RunInputBuilder / dispatch-path hardening to ensure recovery messages are built from canonical facts; if files outside stated ownership boundary are needed, stop and return to Controller.

**Plan fix (Slice 3 L202)**:

> If current `RunInputBuilder` cannot rebuild recovery messages only from canonical EventLog facts and payload descriptors, Slice 3 may perform necessary typed hardening inside `RunInputBuilder` / dispatch-path ownership so the dispatched `AgentRunRequest.messages` are derived from canonical facts. Do not treat projection, memory snapshot, read model, audit, trace, outbox, timeline, `RunResult`, or projection checkpoint as truth. If this hardening needs files outside Slice 3 allowed files, stop and return to Controller before editing them.

**Verdict: FIXED.** Hardening task elevated from risk note to explicit Slice 3 exact change, projection/memory truth forbidden, stop condition for out-of-boundary file needs.

---

### MiMo F6: Slice 2 / Slice 3 both touching run_transition.py

**Controller decision**: rejected as no-action. Plan already sequences S2 before S3.

**Verdict: NO ACTION, CONFIRMED.** Slice dependency ordering S1→S2→S3→S4→S5 is explicit in plan structure.

---

## New Blocker Check

Verified the fix did not introduce:

- New public API or OpenHostOptions fields: none.
- New schema fields: none (recovery count via EventLog).
- Engine modifications: none.
- New reverse dependencies: none.
- State machine inconsistencies: none. Contract section (L82-97) remains consistent with design §27.
- File ownership violations: all slices stay within allowed files per controller adjudication.
- Stop condition gaps: 12 stop conditions (L331-342) remain comprehensive.

## Design Alignment Verification

### §1 Design Goals

| Goal | Plan Coverage |
|------|---------------|
| Durable facts recoverable | Plan L11: recovery scan reads only Run/Attempt indexes, EventLog canonical facts, dispatch record, host instance liveness row |
| Host is lifecycle truth | Plan L11-12: Recovery coordinator in `dayu/host/recovery.py`, all state transitions through Host durable transaction |
| Multi-process not误杀 | Plan L103-108: positive orphan proof requires heartbeat stale + pid evidence + CAS recheck |
| Engine not owning Host state | Plan Non-goals L26: no Engine code modification |

### §2 Layer Boundaries

| Boundary | Plan Coverage |
|----------|---------------|
| Recovery owns startup scan | Plan L51: Recovery coordinator in `dayu/host/recovery.py` |
| Attempt Dispatch only consumes committed records | Plan L110, L200: recovery creates pending dispatch, wakes scheduler |
| RunInputBuilder from typed input providers | Plan L110, L201-202: rebuild from canonical EventLog facts |
| No reverse dependencies | Plan Non-goals L28-29: no Engine/projection/memory truth |

### §10 Durable Store

| Invariant | Plan Coverage |
|-----------|---------------|
| CAS-style state transitions | Plan L94-97: all recovery transitions use CAS recheck |
| EventLog + state index same transaction | Plan L94-97: ATTEMPT_LOST + RUN_RECOVERING/RUN_LOST in one write transaction |
| No projection as governance truth | Plan Non-goals L29, Slice 2 L174: projection lag tests assert recovery uses EventLog/state rows only |

### §17 WorkerProxy / Dispatch

| Requirement | Plan Coverage |
|-------------|---------------|
| dispatching not lease/fencing | Plan Non-goals L30, design §17 L1816 |
| CAS recheck before dispatch | Plan L108: recheck Run/Attempt/dispatch/host instance in transition helper |
| RunInputBuilder from canonical facts | Plan L201-202: explicit hardening task |
| Recovery creates pending dispatch | Plan L199-200: new Attempt + dispatch record, wake scheduler |

### §27 Host Lifecycle / Recovery

| Requirement | Plan Coverage |
|-------------|---------------|
| ACCEPTED/QUEUED/WAITING 原地保留 | Plan L161-164: keep, schedule wake/check, diagnostic-only fallback |
| RUNNING/CANCELLING positive orphan proof | Plan L85-87, L103-108: classifier + CAS recheck |
| RECOVERING creates new Attempt | Plan L88, L199: new Attempt + new execution_id + dispatch record |
| Recovery input only durable truth | Plan L29: Non-goals explicitly list excluded sources |
| CANCELLING orphan → LOST | Plan L111: ATTEMPT_LOST + RUN_LOST, reason cancel_in_flight_attempt_lost |
| Recovery count via EventLog | Plan L79-80, L173: typed helper, start_reason=recovery |
| Positive orphan proof minimum criteria | Plan L103-108, L134: heartbeat stale + pid evidence + CAS recheck |

### §27.1 Accepted Prompt Recovery Semantics

| Requirement | Plan Coverage |
|-------------|---------------|
| USER_INPUT_ACCEPTED durable accepted as prerequisite | Plan L204: integration test seeds crash after USER_INPUT_ACCEPTED |
| RunInputBuilder rebuilds from EventLog | Plan L110, L201-202 |
| New Attempt + new execution_id | Plan L199 |
| Final answer visible through Host event stream | Plan L204: observe through watch_session_events |
| Structured FAILED/LOST on recovery failure | Plan L87, L90: structured reason required |

### P10.5 Public Contract Preservation

| Contract | Plan Coverage |
|----------|---------------|
| No new public API | Plan L73: no new public API, no new OpenHostOptions fields |
| open_host recovery internal | Plan L74: startup side effect extended internally |
| watch_session_events sees recovery events | Plan L75: recovery events as normal Host events, no recovery-specific stream |
| No new public recovery command | Plan Non-goals L32 |

## Open Questions

None.

## Residual Risks

| # | Risk | Status |
|---|------|--------|
| R1 | Portable pid-reuse proof limited to pid-missing on first version | Unchanged from original review, non-blocking |
| R2 | Internal stale threshold affects recovery latency | Unchanged, non-blocking |
| R3 | Recovery E2E timing sensitivity | Unchanged, plan suggests deterministic setup |
| R4 | Lane close/acquire fixes touch dayu.runtime | Unchanged, scope limited |
| R5 | RunInputBuilder hardening may need files outside Slice 3 boundary | Now explicitly addressed by stop condition in Slice 3 L202 |

## Conclusion

**PASS, blocking count = 0.**

All accepted findings (F1–F5, DS 1-U) verified fixed in plan artifact. MiMo F6 confirmed no-action. No new blockers introduced. Plan remains aligned to `docs/host/design.md` §1, §2, §10, §17, §27, §27.1 and P10.5 frozen public contract.

Plan is implementation-ready.
