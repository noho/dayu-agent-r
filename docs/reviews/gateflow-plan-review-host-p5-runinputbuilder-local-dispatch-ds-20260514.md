# Phase 5 Plan Review: RunInputBuilder / LocalProxy / EngineEvent Ingest / Local Dispatch

## Scope

Reviewed artifact: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`

Design/control truth and prior gate artifacts:
- `docs/host/design.md` §17, §22, §23
- `docs/host/implementation-control.md` Phase 5
- `docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md`
- `docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md`
- `docs/reviews/gateflow-phase-design-fix-host-p5-codex-20260514.md`
- `docs/reviews/gateflow-phase-design-fix-re-review-host-p5-controller-adjudication-20260514.md`

## Result

**Plan accepted with 2 non-blocking findings. No blocking findings.**

---

## Non-blocking findings

### F-N1. Severity: Moderate — Dispatch record diagnostic fields: `worker_accept_event_sequence` and `worker_accept_event_id` semantics underspecified

**Evidence:**

Plan §3.2 defines new dispatch diagnostic columns including `worker_accept_event_id TEXT NULL` and `worker_accept_event_sequence INTEGER NULL`. Section §3.3 states "record worker accept refs on dispatch record, status remains dispatching". The plan does not define:
1. Whether `worker_accept_event_id` refers to the `ATTEMPT_RUNNING` EventLog event_id or a separate worker-level event.
2. Whether `worker_accept_event_sequence` is the global EventLog `event_sequence` or a worker-local sequence.
3. The nullability rule says `worker_accept_event_id` / `worker_accept_event_sequence` must be "all NULL or all non-NULL" — but does not say which table/sequence they reference.

**Impact:**

Implementation agent would need to invent these semantics. In the worst case, the fields reference a non-existent "worker accept event" that was never designed, or they could collide with the EventLog's own event_id domain.

**Recommendation:**

Resolve during implementation: clarify in P5-S1 that `worker_accept_event_id` is the `ATTEMPT_RUNNING` EventLog `event_id` and `worker_accept_event_sequence` is its global `event_sequence`. This is a narrow disambiguation, not a design gap.

---

### F-N2. Severity: Low — `ExecutionTargetRef` and `AgentPolicy` typed definitions deferred to API module without explicit shape

**Evidence:**

Plan §3.4 §3.5 and P5-S2 repeatedly reference concepts not yet typed in `dayu/host/api.py`:
- `RunnerSpec` — mentioned in §3.4 as a `PolicySnapshotProvider` output
- `RunnerCallOptions` — same
- `AgentPolicy` — mentioned in §3.4, used in `ToolSchemaSnapshotProvider` and `AgentRunRequest`
- `AgentRunRequest` — plan defines it but does not commit to the exact API module placement (plan says "Phase 5 必须使用显式 typed dataclass 注入" in §3.4, but does not bind it to a specific module or state whether it extends `dayu.engine` contracts)

The plan correctly states Engine contracts must not be modified (§3.1, §3.1 stop condition). However, `AgentRunRequest` sits at the boundary — it is consumed by Engine's `run_agent_messages(request)` call path. Plan does not specify whether `AgentRunRequest` is a Host-local dataclass that maps to Engine's existing `AgentRunRequest`, or a new Host-owned type that Engine is expected to accept.

**Impact:**

P5-S2 slices `dayu/host/api.py` for new "typed local execution options" but does not explicitly place `AgentRunRequest`, `RunnerSpec`, `RunnerCallOptions`, or `AgentPolicy` there. Implementation agent may place them in `run_input.py` instead, creating import coupling between dispatch and run_input that didn't need to exist.

**Recommendation:**

Resolve during implementation: define `AgentRunRequest` as a Host-owned dataclass in `dayu/host/api.py` or `dayu/host/run_input.py`, and clarify that it maps to Engine's existing request type at the LocalProxy boundary (not by extending Engine contracts). Treat `RunnerSpec`, `RunnerCallOptions`, `AgentPolicy` as Host-owned policy dataclasses.

---

## Adversarial failure pass (below the fold)

All adversarial scenarios below were tested; none produced a blocking finding.

### A1. Multiple dispatch race on `waiting_for_lane` → `dispatching`

**Tested:** Two schedulers poll same pending dispatch record. One CAS-wins pending → waiting_for_lane, acquires lane, durable recheck passes, CAS → dispatching. The other sees status already waiting_for_lane, CAS loses.

**Result:** Plan §3.3 durable recheck requires `dispatch record waiting_for_lane or pending`, so second scheduler would also pass recheck (it reads `waiting_for_lane`). However, `execution_id` match + only-one-`dispatching` CAS on `attempt_id` unique constraint provides the second CAS loser. Plan correctly relies on unique constraint rather than a dedicated fencing CAS. **No gap.**

### A2. Cancel wins pre-worker race, but scheduler already holds lane and hasn't rechecked yet

**Tested:** Cancel commits durable facts while scheduler is between `waiting_for_lane` commit and durable recheck.

**Result:** Plan §3.3 durable recheck requires "no cancel / terminal accepted". Cancel has appended `CANCELLED` facts; recheck sees these and CAS-loses. Plan §4.3 correctly covers this. **No gap.**

### A3. EngineEvent arrives after terminal closeout has already committed

**Tested:** Worker accepted, Engine emits final_answer, Host commits SUCCEEDED. Worker then emits a late reasoning_delta or iteration_completed.

**Result:** Plan §3.5 preview event mapping, and §3.1 ingest validation rule "terminal 后迟到事件...不得污染 canonical EventLog". Late preview/delta would be rejected at ingest boundary. **No gap.**

### A4. `cancel_session_runs` encounters WAITING Run

**Tested:** Session has one `RUNNING` Run and one `WAITING` Run. `cancel_session_runs` called.

**Result:** Plan §3.7: "若同 Session 存在 WAITING 或 RECOVERING non-terminal Run，必须在追加任何 cancel fact 前返回 UNSUPPORTED_OPERATION，保持无 partial mutation". This is correct — the entire operation fails before any mutation. **No gap.**

### A5. `AgentRunRequest` construction without `USER_INPUT_ACCEPTED` payload

**Tested:** EventLog has `USER_INPUT_ACCEPTED` but `payload_json` is empty or missing `display_text`.

**Result:** Plan §3.4 requires prompt from `USER_INPUT_ACCEPTED.payload_json.display_text`. If that field is absent, RunInputBuilder can't construct a valid message. Plan stop condition P5-S2 says "如果无法从 durable `USER_INPUT_ACCEPTED` 重建当前 prompt，停止". This is correct — missing data should stop, not silently degrade. **No gap.**

### A6. WorkerProxy accepted → `ATTEMPT_RUNNING` appended, then Engine immediately crashes before any events

**Tested:** `accept_worker_running_in_transaction` commits, then worker process crashes before emitting any EngineEvent.

**Result:** Plan §3.6 clean EOF without terminal → FAILED, stream error/worker crash → LOST. Host would observe stream error/close and route to LOST closeout. **No gap.**

### A7. Two cancel operations race on same active Run — duplicate `RUN_CANCELLING`

**Tested:** Two `cancel_run` calls for same Attempt RUNNING arrive concurrently.

**Result:** Plan §3.7: "若 Run 已 CANCELLING，不重复 append RUN_CANCELLING". The second CAS would see Run status already CANCELLING (from first transaction) and skip the append. **No gap.**

### A8. `cancel_session_runs` replay after first execution created new queued Runs

**Tested:** First `cancel_session_runs` executes, cancels all non-terminal Runs. New `start_run` creates new queued Run. Replay of same `cancel_session_runs`.

**Result:** Plan §3.7: "同 key replay 返回当前 SessionSnapshot，不取消首次操作后新接受的 Run". Idempotency record returns the previous result without mutating the new queued Run. **No gap.**

---

## Plan-gate checklist verification

Per controller adjudication artifact `gateflow-phase-design-fix-re-review-host-p5-controller-adjudication-20260514.md`, all carried-forward plan-gate checks are verified:

| # | Check | Plan coverage | Verdict |
| --- | --- | --- | --- |
| DS-F3 | minimal canonical payload fields | §3.5 lists full field sets for all terminal events | **PASS** |
| DS-F4 | dispatch diagnostic fields and nullability | §3.2 defines columns and per-status nullability rules | **PASS** (with F-N1 clarification) |
| DS-F5 | RunInputBuilder real vs noop provider set | §3.4 explicitly separates real and noop providers | **PASS** |
| DS-F6 | `cancel_session_runs` partial completion idempotency | §3.7 defines idempotency scope, partial completion semantics, replay behavior | **PASS** |
| MiMo-F-O1 | `dispatching` final record state after worker accept | §3.2: "dispatching 在 WorkerProxy accept 后仍保留为 dispatch record 的最终非取消状态" | **PASS** |
| MiMo-F-O4 | context compaction failure handling | §3.5: unsupported → diagnostic + FAILED, no RECOVERING | **PASS** |
| MiMo-F-O5 | `usage_reported` handling | §3.5: PROJECTION_SIGNAL with no state mutation | **PASS** |

---

## Import boundary audit

Plan §2.3 prohibits modification of Engine contracts, `dayu.runtime`, `dayu.fins/`, `dayu/service/`, `dayu/ui/`. P5-S6 integration tests include import boundary tests to verify `dayu.runtime` does not import `dayu.host`/`dayu.engine`, and `dayu.engine` does not import `dayu.host`. These tests are correctly scoped. **No issue.**

---

## Slice sequencing and ownership audit

| Slice | Dependencies | Owner module | Cross-slice coupling risk |
| --- | --- | --- | --- |
| P5-S1 | Phase 3 state module (existing) | durable/ | Low — pure schema + mutation primitives |
| P5-S2 | P5-S1 for AttemptSnapshot shape | run_input.py (new) | Low — only reads durable state |
| P5-S3 | P5-S1 + P5-S2 + runtime/lane | dispatch.py, local_proxy.py (new) | Moderate — orchestrates S1 mutations with S2 input |
| P5-S4 | P5-S1 + P5-S3 envelope types | engine_ingest.py (new) | Low — consumes S3 event candidates |
| P5-S5 | P5-S3 active registry + P5-S4 closeout paths | admission.py, command.py | Moderate — extends existing cancel logic |
| P5-S6 | All prior slices | integration tests | Low — integration validation |

Sequencing is correct: schema first (S1), input builder next (S2), dispatch + proxy next (S3), ingest next (S4), cancel completion (S5), integration closeout (S6). S1-S2 could run in parallel; S3 depends on both. **No issue.**

---

## Test coverage assessment

Plan defines 12 test files with explicit coverage requirements per slice. Key scenario coverage:

- Schema nullability per status: covered in S1
- dispatch CAS loser path: covered in S1, S3
- duplicate event idempotency: covered in S4
- stale execution_id rejection: covered in S4
- `cancel_session_runs` partial mutation guard: covered in S5
- `cancel_session_runs` replay idempotency: covered in S5
- lane acquire timeout closeout: covered in S3
- pre-worker cancel race: covered in S3, S5
- active cancel propagation: covered in S5
- clean EOF → FAILED, worker crash → LOST: covered in S4, S6
- RunInputBuilder determinism: covered in S2
- import boundaries: covered in S6

Gap: Plan does not test scheduler close during lane acquire (i.e., `handle close` while `waiting_for_lane`). P5-S3 tests cover "handle close 取消 pending acquire" but it's unclear whether the test exercises close *during* acquire wait vs close *before* acquire. This is a low-severity testing gap covered by the scheduler `close()` contract in §3.3; implementation can add this case.

---

## Stop conditions audit

All five slice stop conditions are unambiguous and correctly placed:

- S1: fresh schema compatibility (no old-schema reads)
- S2: durable-only prompt reconstruction (no UI/request fallback)
- S3: lane DB independence (no merge with Host DB), active truth only after `ATTEMPT_RUNNING`
- S4: Engine contract integrity (no Host identity leakage), no automatic RECOVERING
- S5: no wait record or recovery dispatch cancel

---

## Pyright / README obligations

- Plan correctly requires pyright after each slice.
- README trigger rules in §5 correctly follow CLAUDE.md README constraints.
- `dayu/host/README.md` and `tests/README.md` are correctly identified as must-update.
- `dayu/README.md` update is conditional (only if Host status claims RunInputBuilder/LocalProxy don't exist).
- Root `README.md` default is no-update; correct since Phase 5 adds no CLI commands.

---

## Deferred owner tracking

Plan §7 closeout report correctly maps deferred capabilities to phase owners:
- Phase 6: ToolRuntime / fetch_more
- Phase 7: WAITING / resolve_wait
- Phase 9: Memory
- Phase 10: Context Governance
- Phase 11: Recovery
- Phase 13: Observer / Sink
- Phase 14: RemoteProxy
