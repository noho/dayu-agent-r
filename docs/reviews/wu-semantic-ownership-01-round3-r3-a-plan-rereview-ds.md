# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Re-review (DS)

## Review metadata

- **Re-review type**: adversarial plan re-review after AgentCodex plan fix
- **Reviewer**: DS (planreview skill, re-review pass)
- **Timestamp**: 2026-07-12T12:16:32+08:00
- **Gate**: plan re-review gate, before implementation
- **Risk level**: production-high
- **Review target**: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- **Plan-fix artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`
- **Prior review inputs**:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-controller-adjudication.md`
- **Control sources referenced**:
  - `docs/phaseflow-umbrella-optimization-control.md` §Slice 切分约束, §Review 路由优化
  - `AGENTS.md`
  - `docs/host/issues-implementation-control.md`

## Re-review scope

1. Verify every accepted finding in controller adjudication is actually fixed in the plan: DS F-01 through F-06, MiMo F1 through F6.
2. Verify the new 8-slice structure is justified under control-doc optimization constraints.
3. Verify R3-A accepted findings remain fully covered: DR-006/007/008/009/010/011/012/017/025/029 and MiMo/DS confirmations.
4. Verify S2-S5 handoffs are coherent: no orphan half-state, no impossible intermediate tests, no hidden implementation redesign.
5. Verify S1 schema feasibility pre-check, projector metadata descriptor shape, _HostDurableActor typing/thread ownership, fatal/admission deterministic test, S3/S6/S8 contract clarifications are concrete enough for implementation.
6. Verify no new material plan defect was introduced.

---

## 1. Controller Accepted Finding Fix Verification

### DS F-01: S2 over-broad slice → **FIXED**

- **Controller requirement**: Split S2 into at least 2 sub-slices along semantic owner boundaries.
- **Plan fix**: Old single S2 decomposed into S2 (admin opener/public durable actor, line 298), S3 (scheduler health/admission/retry/replay, line 389), S4 (startup recovery batching, line 481), S5 (active-cancel watchdog/classification, line 542).
- **Verification**: Each new slice has independent goal, non-goals, allowed files, tests, anti-cases, stop condition. S2 allowed production files reduced from ~13 to 11 (with 2 new), allowed tests from ~24 to 22. S3-S5 each have 4-7 allowed production files. Old single-S2 heading not found in updated plan (confirmed by plan-fix artifact scan).
- **Verdict**: Fixed. The decomposition follows semantic owner boundaries: actor/connection ownership (S2), health/admission state machine (S3), recovery cursor (S4), cancel governance (S5).

### DS F-02: fatal/admission race test underspecified → **FIXED**

- **Controller requirement**: Specify deterministic race test mechanics with synchronization points, fatal injection method, barrier, durable/wake assertions.
- **Plan fix**: "Deterministic fatal/admission race mechanics" section (lines 430-443) specifies:
  - Real temporary durable DB + S2 real actor
  - Typed `_BarrierDurableInvoker` implementing S2 private invoker Protocol
  - `asyncio.Event` for `actor_entered`/`actor_release` synchronization
  - Recording wake port via thread-safe bridge with `PendingDispatchRecord`
  - Admission-first script: 5 fixed steps with explicit event ordering
  - Fatal-first script: direct `report_fatal()` then concurrent submit/read/cancel
  - Caller-cancellation variant with `CancelledError` + wake-before-fatal assertion
  - Explicit prohibition of sleep/probabilistic oracles
- **Verdict**: Fixed. Test mechanism is deterministic, uses real actor (not fake durable results), and covers all three scenarios (admission-first, fatal-first, caller-cancel).

### DS F-03: daemon observation lifecycle incomplete → **FIXED**

- **Controller requirement**: Specify late-result/result-queue shutdown gate and bounded tracking of outstanding observation threads.
- **Plan fix**: Frozen contract §6.6-6.9 (lines 148-152) specifies:
  - `max_outstanding_adapter_calls` cap with typed capacity diagnostic/backoff
  - Token lifecycle: `ACTIVE -> INVALIDATED -> FINISHED` with typed gate
  - `publish(token, typed_result)` under shared lock, validates token still ACTIVE and supervisor generation not closed
  - Timeout/supervisor close INVALIDATE first, then drain; late publish only returns dropped
  - Shared monotonic close deadline, not multiplied by thread count
  - Supervisor CLOSING/STOPPED status tracking with thread ref counting
  - Thread holds only adapter, immutable snapshot, token, `Queue(maxsize=1)` — no store/transaction/command handle/resolver/scheduler port
- **Verdict**: Fixed. Lifecycle is complete: create → track → publish/invalidate → finish → deref. Late result cannot access durable store. Thread cap prevents unbounded accumulation.

### DS F-04: S1 schema feasibility unknown → **FIXED**

- **Controller requirement**: Add S1 pre-check that reads current durable payload DDL and proves existing columns support validation.
- **Plan fix**: Two locations:
  - Frozen contract §1.8 (line 107): "S1 任何代码编辑前执行只读 schema feasibility pre-check" with explicit column expectations and zero-code-edit stop condition.
  - S1 §实施前 schema feasibility pre-check (lines 234-244): Concrete bash commands (`rg -n` patterns), expected column evidence, stop status `blocked-return-to-plan-review-before-code-edit`, and explicit prohibition of DDL/user_version/migration.
- **Verdict**: Fixed. Pre-check is concrete, executable, and gated before any code edit. Plan correctly asserts current DDL evidence supports the check but requires re-verification at implementation time.

### DS F-05: process start ambiguity → **FIXED**

- **Controller requirement**: Make start failure non-retryable on same handle, or require explicit proof no child process exists.
- **Plan fix**: Frozen contract §8.2 (line 165): "任何`start()`异常都保留start-attempt gate，同一handle一律不可再次start，也不依赖`pid is None`/`is_alive() is False`猜测'从未启动'。调用方若要重试必须先close该handle并创建新实例"
- **Verdict**: Fixed. Plan chooses the safer path: no retry on same handle, no runtime guessing. Caller must create new handle for retry. This eliminates the orphan process risk DS F-05 identified.

### DS F-06: Host/HostAdmin Protocol split unclear → **FIXED**

- **Controller requirement**: State that Host and HostAdmin are independent protocols with no compatibility wrapper or inheritance.
- **Plan fix**: Frozen contract §2.2 (line 112): "`Host`与`HostAdmin`是两个独立Protocol，不继承、不互相扩展，也不保留compatibility wrapper". Explicit method sets: execution Host retains execution/read/outbox/cancel/watch, removes list/purge/storage-admin; HostAdmin exposes get_session/list_sessions/purge_session/report_storage_usage/run_storage_maintenance/close.
- **Verdict**: Fixed. Clear independent Protocol specification with explicit method sets and no compatibility shim.

### MiMo F1: DR-017/DR-029 diagnosis mismatch / S5 overdesign → **FIXED**

- **Controller requirement**: Correct diagnosis text. DR-029 is release-failure-after-attempted-release, not release-before-attempt. DR-017 is partial start/cleanup poisoning. Preserve concurrency gates; focus on retryable cleanup, not five-state rewrite.
- **Plan fix**:
  - First-principles table (lines 63, 65): DR-017 corrected to "partial start/cleanup poisoning"; DR-029 corrected to "release-failure-after-attempted-release，不是release-before-attempt"
  - Frozen contract §8 (lines 162-168): Explicitly rejects five-state rewrite. Preserves `_closed` as concurrency gate. Separates "close started" from "cleanup completed". Uses single-flight shielded task + step completion tracking. Lane: successful tokens removed, failed tokens retained, only commit completed when heartbeat stopped AND held_tokens empty.
  - S8 tests (lines 784-793): Covers pre/post-spawn start failure, partial cleanup step completion, queue feeder in finally, concurrent close single-flight, lane two-token one-fails retry.
- **Verdict**: Fixed. Diagnosis corrected to match code evidence. Fix preserves concurrency protection while making cleanup retryable. No five-state rewrite.

### MiMo F2: S2 over-broad slice → **FIXED**

- Same as DS F-01. Both reviewers flagged S2 scope; plan fix decomposes into S2-S5.
- **Verdict**: Fixed (merged with DS F-01 fix).

### MiMo F3: projector metadata descriptor shape inconsistent → **FIXED**

- **Controller requirement**: Explicitly define shared projector metadata descriptor shape and how all three producers populate it.
- **Plan fix**: Frozen contract §1.3 (lines 102-103): Six-field `ProjectorMetadata` descriptor: `projector_metadata_id: str`, `projector_id: closed enum`, `projector_schema_version: str`, `projector_digest: sha256 digest`, `purpose: closed enum`, `source_contract_refs: tuple[HostInternalRef, ...]`. Three producer fill rules: `run_input.py`/`engine_ingest.py` from existing typed metadata; `compaction_operation.py` must rename `metadata_id` → `projector_metadata_id` and explicitly fill `projector_schema_version`/`source_contract_refs`. Tool Trace projects 5 fields from descriptor only.
- **Verdict**: Fixed. Shape is explicit with field names, types, and per-producer population rules. Compactor normalization is specified.

### MiMo F4: durable actor thread-safety underspecified → **FIXED**

- **Controller requirement**: Define actor callable typing, command handle ownership, scheduler connection source, event-loop bridge, close order, busy/retry rules.
- **Plan fix**: Frozen contract §2.3-2.9 (lines 113-119):
  - `_HostDurableInvoker` Protocol: `invoke(operation: Callable[[HostCommandHandle], T]) -> Awaitable[T]`, `close() -> Awaitable[None]`
  - Single `ThreadPoolExecutor(max_workers=1)`, worker creates/uses/closes private `HostCommandHandle` + connection; handle/connection never leave thread
  - Scheduler receives independent scheduler-owned store (same WAL/foreign keys/busy timeout, different connection)
  - `_ThreadsafeSchedulerWakeupPort`: `call_soon_threadsafe()` + typed `Future`, actor thread blocks on future; `_ThreadsafeActiveWorkerCancelPort`: registry cancel + token write + `on_cancel()` all on opener loop
  - Caller cancellation semantics: read/admin caller cancel propagates immediately (actor still drains); new-work caller cancel shielded within admission lease (S3)
  - Close order: gate→poller→drain actor→close scheduler→flush projection→close actor handle→shutdown executor→close scheduler store; admin close only actor chain
- **Verdict**: Fixed. Typing, connection ownership, bridge semantics, and close order are all specified at implementation-ready detail.

### MiMo F5: wait expiry helper relation unclear → **FIXED**

- **Controller requirement**: Specify `_expire_wait_in_transaction()` input/output and how it constructs the failed outcome.
- **Plan fix**: Frozen contract §6.1-6.3 (lines 144-146):
  - Typed `ExpireWaitInput(wait_id, observed_at, actor, source)` and `ExpireWaitResult(transition, queue_promotion_session_id, idempotent_replay)`
  - Accepts caller-provided `HostTransaction`, does not create nested transaction or call public `resolve_wait()`
  - Constructs `ResolveWaitFailedOutcome(result=ToolResultFailure(ok=False, error="wait_deadline_expired", message=<业务可读期限说明>, hint=None, meta=None), payload_ref=None)`
  - Reuses `_wait_resolution_payload_plan()`, stable event-id plan, `WaitingRunTerminalInput`, then calls `fail_run_from_waiting_in_transaction()`
  - Idempotency key/digest from wait id, durable deadline, fixed reason only
- **Verdict**: Fixed. Input/output types, transaction ownership, outcome construction, and reuse of existing transition are all specified.

### MiMo F6: DR-017 queue cleanup → **FIXED** (merged into S8 correction)

- **Controller requirement**: Covered by S5 narrowed correction; add tests for partial close failure and second close cleanup.
- **Plan fix**: Frozen contract §8.3 (line 166): "queue close/feeder cleanup即使kill/join/process.close失败也必须尝试；所有等待使用finite budget". S8 anti-case #3 (line 788): "kill、process join、process close分别抛transient exception：后续queue.close与feeder cleanup仍由finally尝试；完成步骤有记录，第二次close只补未完成步骤".
- **Verdict**: Fixed. Queue feeder cleanup is explicitly in finally path. Step completion tracking enables retry of remaining steps.

---

## 2. 8-Slice Structure Justification

**Control-doc baseline**: `docs/phaseflow-umbrella-optimization-control.md` §Slice 切分约束 says production state-machine/durable changes default to 2-4 slices; plans above 3 must justify why merging is not possible. The constraint is per-slice scope guidance, not a hard total-slice cap.

**Plan justification** (lines 170-199):
- Explicitly acknowledges 8 > 5 threshold and that extra gate cost is "有意承担"
- Cost-benefit analysis: old single S2 bundled actor ownership, health state machine, recovery cursor, watchdog event, and cancel classification — concerns with different semantic owners, failure injection modes, rollback blast radii, and reviewer expertise. The fixed cost of 3 extra implementation/review/commit gates is lower than debugging combined cross-thread/transaction/recovery/cancel failures in one production-high slice.
- Each slice is behaviorally self-contained, not mechanically split by file or finding:
  - S1: durable bytes/provenance/size owner
  - S2: admin opener + public durable actor (independent Protocol, actor connection ownership, bridge, close order)
  - S3: execution health + admission atomic boundary (on stable S2 actor/bridge)
  - S4: startup recovery keyset/watermark/transaction owner
  - S5: active-cancel watchdog + cancel snapshot classification
  - S6: wait terminal + bounded observation/shutdown
  - S7: compaction attempt cancellation scope
  - S8: layer-neutral runtime partial cleanup completion
- Explicit "禁止合并关系": S2+S3 (connection errors vs health state machine errors need independent rollback), S3+S4 (fatal lease correctness doesn't depend on recovery cursor), S4+S5 (recovery batching and cancel classification are reviewer-confirmed different owners/failure matrices), S6+S7, S8+any Host slice, S1+S2 (runner payload stress localization would be buried by opener concurrency changes).

**Assessment**: The justification meets the control-doc requirement. Each of the 8 slices has independent goal, non-goals, allowed files, tests, anti-cases, validation commands, review focus, and stop condition. The dependency chain is linear and each handoff is concrete. The 8 slices are more reviewable than old S2 — a reviewer can assess S2's actor thread-safety without also auditing S3's health state machine or S5's watchdog event semantics. **Accepted.**

---

## 3. R3-A Accepted Finding Coverage Preservation

Plan includes a traceability ledger (§R3-A accepted finding / confirmation traceability, lines 821-844) mapping every accepted finding to slice, required tests, required source scan, and slice stop evidence.

| Accepted finding | Slice | Coverage status |
|---|---|---|
| DR-006 runner-call hot payload unbounded | S1 | 0/1/12/300 producer matrix, production stress 12/12, hot payload <4096 |
| DR-010 descriptor content/digest split | S1 | Schema pre-check, SQLite/artifact tamper matrix, config ref/digest tamper |
| compact_material wrong call ref fallback | S1 | Missing/wrong-type/identity-mismatch request ref tests |
| DR-007 admin command opens execution Host | S2 | No-secret real Service+CLI list/purge, zero execution side effects |
| DR-011 async Host blocks event loop | S2 | External `BEGIN IMMEDIATE` + Event barrier ticker, thread identity |
| DR-009 scheduler fatal not propagated | S3 | Deterministic admission-first/fatal-first/caller-cancel race |
| dispatch retry exhaustion self-closes | S3 | One-shot retry exhaustion → final dispatch, no scheduler close |
| idempotent admission replay skips wake | S3 | Pending dispatch/pre-start replay matching wake derivation |
| recovery single huge transaction | S4 | Batch=2, fixed watermark/time, mid-batch failure/replay |
| watchdog wakeup drop | S5 | Tick barrier second-wake → second tick, Event not Queue |
| cancel_run deferred race | S5 | Transaction spy, multi-process snapshot race |
| DR-008 expired wait remains WAITING | S6 | Helper contract, poll/direct/callback, result/cancel/expiry race |
| DR-012 wait adapter can hang close | S6 | Stuck poll/abandon, late publish, cap=1, shared close deadline |
| Fins wait-adapter reverse dependency split | S6 | Host bounded contract only; `dayu/fins/` diff empty |
| DR-025 compactor timeout contaminates parent | S7 | Timeout→repair success, parent cancel precedence, child-only timeout |
| proactive compaction TOCTOU | S7 | Recorder→pre-call check, provider count=0 on stale snapshot |
| DR-017 process partial start/cleanup poisoning | S8 | Pre/post-spawn failure, step completion, queue feeder, concurrent close |
| DR-029 lane completion after failed release | S8 | Two-token one-release-fails, second retry, concurrent cancel/heartbeat |

All 10 accepted DR findings and all 7 confirmations (retry exhaustion, watchdog wake, proactive compaction TOCTOU, recovery batching, cancel classification, compact ref fallback, Fins boundary) are mapped. The Fins reverse-dependency R3-D half is correctly deferred per controller adjudication. No finding is omitted, merged into "related tests pass," or deferred to another R3 sub-WU.

**Coverage preserved. ✓**

---

## 4. S2-S5 Handoff Coherence

### Dependency chain

```
S1 → S2 (actor/bridge) → S3 (health/admission) → S4 (recovery batching) → S5 (cancel watchdog/classification)
```

### Handoff contracts

| Transition | Handoff | Concrete contract |
|---|---|---|
| S2→S3 | Actor + bridge + scheduler wake port | S3 "在S2稳定actor/bridge之上关闭execution health与new-work admission原子边界". S3 allowed files explicitly exclude S2's `_durable_actor.py`; any required actor change stops S3. |
| S3→S4 | Health gate READY + critical-task supervisor | S4 non-goals: "不修改health lease、watchdog、cancel command或public API". Recovery batches all succeed → health gate READY. |
| S2+S3→S5 | Active cancel bridge (S2) + critical-task supervisor (S3) | S5 non-goals: "不修改recovery cursor、health state machine、actor connection或wait adapter". S5 only modifies cancel owner internals (watchdog event, cancel classification). |

### Orphan half-state check

- **After S2**: Actor/bridge exists. Scheduler still works as before (no health gate yet). Admin opener functional. No orphan — existing execution Host behavior preserved until S3 adds health gate.
- **After S3**: Health gate active. Admission lease covers actor+wake. Recovery still uses old single-transaction scan. No orphan — recovery correctness is independent of health gate; old recovery path still works.
- **After S4**: Recovery uses keyset batching. Health gate still gates READY on all batches. No orphan — recovery batching is a drop-in replacement for old single-transaction scan.
- **After S5**: Watchdog uses level-triggered Event. Cancel classification is transaction-local. No orphan — watchdog/cancel are self-contained governance changes.

### Impossible intermediate test check

Each slice's non-goals explicitly prevent testing later-slice behavior:
- S2 non-goals: "本slice不实现health state machine、admission lease、recovery batching、watchdog event或cancel classification"
- S3 non-goals: "不修改startup recovery分页（S4）、watchdog level trigger或cancel classification（S5）"
- S4 non-goals: "不修改health lease、watchdog、cancel command或public API"
- S5 non-goals: "不修改recovery cursor、health state machine、actor connection或wait adapter"

**Handoffs coherent. No orphan half-state, no impossible intermediate tests, no hidden implementation redesign. ✓**

---

## 5. Concrete Specification Assessment

### S1 schema feasibility pre-check

Lines 234-244: Concrete `rg -n` commands targeting specific column names (`host_sqlite_payloads`, `payload_format`, `payload_json`, `payload_size_bytes`, `payload_digest`, `payload_descriptors`, `payload_ref`, `payload_kind`, `sqlite_payload_id`). Expected evidence: both payload tables have all columns; resolver can join/read in same transaction. Stop status: `blocked-return-to-plan-review-before-code-edit`. **Concrete. ✓**

### Projector metadata descriptor shape

Lines 102-103: Six fields with types: `projector_metadata_id: str`, `projector_id: closed enum`, `projector_schema_version: str`, `projector_digest: sha256 digest`, `purpose: closed enum`, `source_contract_refs: tuple[HostInternalRef, ...]`. Per-producer fill rules specified. Tool Trace projects 5 fields from descriptor. **Concrete. ✓**

### _HostDurableActor typing/thread ownership

Lines 113-119: `_HostDurableInvoker` Protocol with `invoke(operation: Callable[[HostCommandHandle], T]) -> Awaitable[T]`. Single `ThreadPoolExecutor(max_workers=1)`. Worker creates/owns/uses/closes private `HostCommandHandle` + connection; handle/connection never leave thread. Scheduler gets independent store. Two typed bridges (`_ThreadsafeSchedulerWakeupPort`, `_ThreadsafeActiveWorkerCancelPort`). Caller cancellation semantics per operation type. Fixed close order. **Concrete. ✓**

### Fatal/admission deterministic test

Lines 430-443: Typed `_BarrierDurableInvoker` + `asyncio.Event` synchronization. Recording wake port. Admission-first script: 5 fixed steps. Fatal-first script: direct `report_fatal()` + concurrent submit/read/cancel. Caller-cancellation variant. Explicit "不使用sleep/probabilistic race oracle". **Concrete. ✓**

### S3 contract clarifications (health gate, admission lease, retry)

Lines 124-128: `HostExecutionHealthGate` states: `STARTING -> READY -> UNAVAILABLE -> CLOSING -> CLOSED`. Admission lease covers: READY check → actor transaction → commit → thread-safe scheduler wake → actor future drain. Fatal/admission ordering: only two legal outcomes. Retry exhaustion is transient (backoff + reconcile, no scheduler close). Idempotent replay derives wake from durable snapshot. **Concrete. ✓**

### S6 contract clarifications (wait expiry, observation, shutdown)

Lines 144-152: Typed `ExpireWaitInput`/`ExpireWaitResult`. Helper accepts caller-provided transaction. Constructs `ResolveWaitFailedOutcome` with fixed fields. Observation token: `ACTIVE -> INVALIDATED -> FINISHED`. `publish()` under lock validates token state + supervisor generation. `max_outstanding_adapter_calls` cap. Shared monotonic close deadline. Supervisor CLOSING→STOPPED with thread ref counting. **Concrete. ✓**

### S8 contract clarifications (partial cleanup, lane retry)

Lines 162-168: Rejects five-state rewrite. Single-flight shielded cleanup task. Step completion tracking for retry. Lane: successful tokens removed, failed tokens retained, `_close_completed` only when heartbeat stopped + held_tokens empty + no error. Caller cancellation doesn't overwrite cleanup result. **Concrete. ✓**

---

## 6. New Material Defect Scan

Scanned for:
- Scope creep into R3-B/C/D/E territory → None found. Non-goals per slice explicitly exclude downstream sub-WUs.
- Orphan findings not mapped to any slice → None found. Traceability table covers all 10 DR findings + 7 confirmations.
- Hidden implementation redesign → None found. S2 explicitly states "不引入通用async SQLite driver，不把scheduler整体迁移到另一event loop"; S5 states "不扩张cancel支持状态"; S8 states "不重构runtime God file".
- Contradictory constraints between slices → None found. S3 explicitly prohibits modifying S2's `_durable_actor.py`. S4 non-goals prevent modifying S3's health lease. S5 non-goals prevent modifying S4's recovery cursor.
- Missing allowed-file entries for required changes → None found. Each slice has explicit allowed production files/modules and allowed tests/docs.
- Infeasible validation commands → None found. All `pytest` commands reference existing or explicitly allowed-new test files. All `rg` source scans target concrete patterns.
- README decisions contradicting AGENTS.md triggers → None found. Plan correctly identifies which READMEs need updates and which don't, per AGENTS.md trigger rules.

**No new material plan defect found.**

---

## Residual Risks (unchanged from original plan)

The plan's residual risks section (lines 903-908) correctly tracks:

1. Fins wait-adapter reverse dependency → R3-D (controller-adjudicated boundary split)
2. Daemon thread may run until process exit → tracked by cap, token invalidated, no durable authority
3. Scheduler-owned transactions could cause heartbeat freeze → deferred to lock probe; new R3-A residual if confirmed
4. Fresh-schema policy → tampered descriptors fail closed; pre-deploy audit is ops concern
5. Health gate fatal leaves committed work for next healthy opener → public error must be retryable

These are properly owned and tracked. No new residual risks introduced by the plan fix.

---

## Final Plan Re-review Conclusion

**Pass**

All 12 controller-accepted plan-review findings (DS F-01 through F-06, MiMo F1 through F6) are fixed in the updated plan with concrete, verifiable corrections. The 8-slice structure is justified under control-doc optimization constraints with explicit cost-benefit analysis and per-slice owner closure. All 10 original R3-A accepted DR findings and 7 confirmations remain fully covered with per-finding traceability to slice, tests, source scans, and stop evidence. S2-S5 handoffs are coherent with concrete contracts and no orphan half-states. All challenged specifications (schema pre-check, descriptor shape, actor typing, fatal race test, S3/S6/S8 contracts) are concrete enough for implementation. No new material plan defect was introduced.

The plan is code-generation-ready for the implementation gate.
