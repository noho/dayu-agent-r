# Aggregate Deep Review — WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A

## Scope

- Mode: aggregate deep review (current changes, 8-slice implementation)
- Branch: `phaseflow/host-issues-control`
- Base (plan commit): `4a282850` (Record round3 r3-a plan acceptance)
- HEAD: `c8634b9d` (Record round3 r3-a s8 acceptance)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-aggregate-deepreview-ds.md`
- Included scope:
  - R3-A implementation/control commits between `4a282850` and `c8634b9d` (16 commits: 8 "Accept" + 8 "Record")
  - 121 files changed: `dayu/host/` (core), `dayu/runtime/` (S8), `dayu/service/` (admin wiring), `dayu/cli/` (session command), tests, docs, READMEs
  - All 8 slices: S1 (durable integrity/manifest), S2 (admin opener/actor), S3 (scheduler health/admission), S4 (recovery batching), S5 (active-cancel watchdog), S6 (wait expiry/observation), S7 (compaction cancellation), S8 (runtime cleanup)
- Excluded scope:
  - R3-B/R3-C/R3-D/R3-E/R3-F changes outside R3-A scope
  - `main` branch history not in R3-A commit range
  - `dayu/config/`, `dayu/fins/` (confirmed unmodified by R3-A)
- Parallel review coverage:
  - Subagent 1 (Explore): `open_host.py` — complete lifecycle, close order, health gate, two-connection model, S8 layer neutrality
  - Subagent 2 (Explore): `dispatch.py` + `admission.py` — health gate, admission lease, watchdog Event, cancel classification, critical task fatal, retry exhaustion, idempotent replay, wake unavailable
  - Subagent 3 (Explore): `waiting.py` + `wait_adapter.py` + `_wait_observation.py` — wait expiry atomicity, late result rejection, observation token SM, bounded cap, supervisor close, unbounded join check, thread isolation, legacy deletion, FAILED vs LOST separation
  - Subagent 4 (Explore): `durable/payload_resolution.py` + `_runner_call_manifest.py` + `durable/tool_trace.py` + `compact_material.py` — six-condition integrity, hot payload bounded contract, manifest full validator, Codex-F1/F2/F3 fix verification
  - Subagent 5 (Explore): `recovery.py` + `compaction_operation.py` + `runtime/interruptible_process.py` + `runtime/lane.py` — keyset batching, compaction cancellation scope, runtime close single-flight
  - Subagent 6 (Explore): `_durable_actor.py` + `command.py` + `api.py` + `_execution_health.py` + `service/host_admin.py` — actor, bridges, Protocol separation, admin opener, public API, UNAVAILABLE retryable
  - Subagent 7 (Explore): README/docs + test coverage + source scans
  - All subagents performed line-by-line walkthrough with exact line number evidence

## Findings

未发现实质性问题。

All seven aggregate review focuses passed verification with direct code-path evidence:

### 1. Single Semantic Owner After All Slices

- **Host lifecycle**: `HostExecutionHealthGate` (`_execution_health.py:107-208`) is sole owner of `STARTING -> READY -> UNAVAILABLE -> CLOSING -> CLOSED`. `_PublicHostHandle` delegates close truth to `health_gate.raise_if_public_closed()` (`open_host.py:1119-1126`), no independent `_closed` bool.
- **Wait terminal**: `_expire_wait_in_transaction` (`waiting.py:1330-1511`) is sole owner of wait expiry; commits `RunStatus.FAILED` + `WaitRecordStatus.FAILED` atomically in caller-provided transaction. Late result rejection (`waiting.py:918-949`) commits expiry first, then `WAIT_LATE_RESULT_REJECTED`, then raises.
- **Admin durable**: `HostAdmin` Protocol (`api.py:3554-3627`) is independent of `Host` Protocol (`api.py:3630-3823`), no inheritance, no compatibility wrapper. Admin opener (`open_host.py:1521-1550`) constructs no scheduler/recovery/wait-poller/lane/worker/scene/tool/model-secret.
- **Durable integrity**: `resolve_json_payload` (`durable/payload_resolution.py:45`) is sole owner of six-condition payload verification. All consumers (terminal, outbox, evidence, Tool Trace, recovery, RunInput) delegate to this resolver.
- **Runner-call manifest**: `_runner_call_manifest.py` is sole owner of `RunnerCallHotAtoms` bounded contract and `parse_runner_call_manifest` full validator. Hot/manifest identity cross-check at `_runner_call_manifest.py:1244-1281` catches split-brain.

### 2. No Downstream Repair or Guess

- **Cancel classification**: All classification happens inside single write transaction snapshot (`admission.py:_CancelRunOperation.__call__`, lines 1548-1645). No post-write re-read. `_is_deferred_cancel_state()` confirmed deleted (zero hits in `.py` files).
- **Watchdog signal**: `asyncio.Event` (`dispatch.py:1002`) replaced `Queue(maxsize=1)` (confirmed zero hits for `Queue(maxsize=1)` in dispatch.py). Level-triggered semantics: clear before tick (`dispatch.py:2739`), set during tick re-sets event for next round.
- **Idempotent replay**: Wake derived from 11-condition durable Run/Attempt/dispatch snapshot check (`admission.py:4100-4114`), not from bool flag.
- **Retry exhaustion**: `HostTransactionRetryExhaustedError` caught in drain loops, logged, backoff, continue — no self-close, no `UNAVAILABLE` transition.
- **Recovery batching**: Keyset cursor (`NonTerminalRunKeysetCursor`) with strict composite comparison, `LIMIT ?`, no OFFSET. Zero `read_non_terminal_runs()` calls in recovery call graph. Each batch independent write transaction; wake only after commit; cursor advance guard against infinite loop.
- **Observation thread isolation**: Thread holds only adapter, immutable `WaitRecordRow` snapshot, observation token, `Queue(maxsize=1)`. Never holds store, transaction, command handle, resolver, or scheduler port.
- **Compaction cancellation**: `_CompactionAttemptCancellationToken` per attempt (`compaction_operation.py:705-707`); parent checked first (`compaction_operation.py:595`); `request_cancel` writes child-local only (`compaction_operation.py:636-638`); pre-call recheck after manifest recorder but before provider call (`compaction_operation.py:1015-1018`).
- **Wake unavailable**: `_raise_if_wake_unavailable` (`dispatch.py:2697-2714`) raises typed `HostApiError(code=UNAVAILABLE, retryable=True)`, never silently returns.

### 3. No Duplicate Semantic Facts, Mixed Ownership, Fallback, Loose Protocol, or Hidden Shim

- Zero `hasattr`/`getattr` in new code paths.
- Zero loose string protocol — all inter-module contracts use typed dataclasses/Protocols/enums.
- Zero fallback payload resolution — `resolve_json_payload` fails closed on any of six conditions.
- Zero caller-side state inference from timestamps/logs/private fields.
- S5 Event clear-before-tick design explicitly documented in code comment (`dispatch.py:2719-2721`), no implicit contract.
- `_release_expired_or_invalid_boundary` confirmed deleted (zero hits in `.py` files).

### 4. S1 Runner-Call Provenance and S8 Runtime Cleanup Do Not Create New Drift

- **S1**: `_runner_call_manifest.py` is layer-neutral manifest contract; consumed by Host (`dispatch.py`, `engine_ingest.py`, `compact_material.py`, `durable/tool_trace.py`) via typed `parse_runner_call_manifest` / `parse_runner_call_hot_payload`. No Host lifecycle semantic leaked into manifest parser.
- **S8**: `runtime/interruptible_process.py` and `runtime/lane.py` confirmed zero imports from `dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins`. Runtime layer neutrality enforced by `runtime/__init__.py:14-16` architectural constraint.
- **S8 in Host**: `open_host.py` only imports `VERBOSE_LOG_LEVEL` from runtime; runtime primitives used only through `dispatch.py` and `tool_runtime.py` as configuration passthrough.

### 5. R3-A Residuals Properly Deferred

All deferred items from S2 controller adjudication remain properly owned:

| Deferred Item | S2 ID | Owner/Destination | R3-A Status |
|---|---|---|---|
| `DurableActor.close_handle()` check-then-assign double-close | MiMo-RR1 | Future durable actor hardening | Not triggered in R3-A |
| `_run_callback_on_event_loop` no timeout | MiMo-RR2 | Future liveness/supervision hardening | Bridge callbacks bounded (scheduler wake/active cancel) |
| `DurableActor.shutdown_executor()` synchronous wait | MiMo-RR3 | Future actor close hardening | Close order drains before executor shutdown |
| Active-cancel watchdog `QueueFull` wake drop | MiMo-RR4 | S5 | Addressed in S5 (Event replacement) |
| Deferred cancel post-write read | MiMo-RR5 | S5 | Addressed in S5 (single-transaction classification) |
| Admin close executor fallback | DS residual | Future durable actor/admin close hardening | No current blocking path |

S5 deferred items (MiMo-RR4, MiMo-RR5) were addressed within R3-A scope. Remaining four deferred items belong to future hardening work, not R3-A blockers.

### 6. Test Coverage

Tests cover owner-level contract paths across all slices:

| Coverage Path | Slices | Key Test Files |
|---|---|---|
| Failure paths | All 7 | `test_wait_expiry_closeout.py`, `test_scheduler_health.py`, `test_compaction_cancellation_scope.py` |
| Cancel paths | S5, S7, S1 | `test_active_cancel_dispatch.py`, `test_compaction_cancellation_scope.py` |
| Retry paths | S6, S4, S3 | `test_wait_poller_runtime.py`, `test_recovery_scan.py`, `test_dispatch_scheduler.py` |
| Recovery paths | S4, S3 | `test_recovery_scan.py`, `test_open_host_runtime.py` |
| Concurrency paths | S5, S6, S2, S1 | `test_admission_multiprocess.py`, `test_wait_expiry_closeout.py`, `test_durable_actor.py` |

Test quality observations:
- All race tests use deterministic `asyncio.Event`/`threading.Event`/actor FIFO barriers as oracle. Zero `asyncio.sleep(n)` as correctness oracle.
- Pyright: 0 errors, 0 warnings.
- `git diff --check`: pass (one minor newline-at-EOF whitespace in `tests/service/test_host_admin.py:84`).

### 7. README/Doc Trigger Compliance

| Doc | Status | Evidence |
|---|---|---|
| `dayu/host/README.md` | Updated | Host/HostAdmin separation, durable actor, health gate, admission lease, bounded observation, watchdog, wait expiry, compaction cancellation all documented |
| `dayu/README.md` | Updated | Host/HostAdmin boundary, admin assembly, two-handle entry points documented |
| `tests/README.md` | Updated | All R3-A test files listed with coverage area descriptions |
| `docs/host/design.md` | Updated | ExecutionHealthGate SM, watchdog Event, wait expiry helper, compaction cancellation token, startup recovery defer all specified |
| Root `README.md` | N/A | No user-visible entry/CLI/output change in R3-A scope |

## Open Questions

无。

## Residual Risk

1. **Cross-slice integration test gap**: No single test exercises the full chain (recovery → watchdog → admission → wait observation → compaction cancellation) in one scenario. Each mechanism is tested in isolation. Multi-process concurrency tests (`test_admission_multiprocess.py`) and production stress suite (`test_host_production_stress.py`) provide indirect cross-mechanism coverage. The plan's `production-high` validation profile (umbrella control line 199) partially addresses this.

2. **`test_open_host_runtime.py` hotspot**: Modified across 4 slices (S2-S5), now 829+ lines. Convergence of multiple lifecycle concerns in a single test file increases the risk of test ordering dependencies and makes future slice isolation harder.

3. **`test_dispatch_scheduler.py` hotspot**: Modified across 3 slices (S3, S5, S7). Similar convergence concern.

4. **Legacy `read_non_terminal_runs()` retention**: Still defined in `durable/state.py:1927` and exercised in `test_state_schema.py:484`. Not in recovery call graph. Intentional retention for schema-level tests and non-recovery consumers, explicitly deferred beyond S4 scope in plan.

5. **Minor whitespace**: `tests/service/test_host_admin.py:84` has a new blank line at EOF (`git diff --check` reports it). Non-blocking, cleanup opportunity.

6. **S1 diagnostic error opacity**: `_runner_call_manifest.py:1281` raises `"runner-call hot/manifest identity mismatch"` without indicating which of the 16 fields diverged. Security correct, debuggability reduced. Low priority.

7. **Uncooperative provider daemon thread**: S6 bounds Host risk through outstanding cap, INVALIDATED tokens, dropped publishes, and lack of durable authority. Provider cooperative cancellation remains deferred to R3-D per controller adjudication.

8. **`cancel_join_thread()` CPython dependency**: S8 `multiprocessing.Queue.cancel_join_thread()` depends on CPython documented behavior. Non-CPython runtimes may produce unbounded wait. This is the official Python multiprocessing close pattern; not a new S8 risk.

## Validation Scans

| Scan | Result |
|---|---|
| `_is_deferred_cancel_state` in `.py` files | Zero hits (confirmed deleted) |
| `Queue(maxsize=1)` in `dispatch.py` | Zero hits (confirmed replaced by Event) |
| `read_non_terminal_runs` in `recovery.py` | Zero hits (confirmed keyset migration) |
| `_release_expired_or_invalid_boundary` in `.py` files | Zero hits (confirmed deleted) |
| `from dayu.host\|engine\|service\|ui\|fins` in `dayu/runtime/` | Zero hits (confirmed layer neutrality) |
| `dayu/engine/` modifications in R3-A diff | Empty (confirmed S7 scope compliance) |
| `dayu/fins/` modifications in R3-A diff | Empty (confirmed R3-D boundary) |
| `dayu/config/` modifications in R3-A diff | Empty (confirmed R3-F freeze) |
| Pyright | 0 errors, 0 warnings |
| `git diff --check` | Pass (one minor newline-at-EOF) |
