# Phase 15 Slice P15-S5 Implementation Artifact

## Gate / Scope

- Gate: Phase 15 Slice P15-S5 Projection Cleanup, Rebuild Confidence, And Local Hardening.
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md` Slice P15-S5.
- Role: AgentCodex implementation specialist only; no controller action, no review, no commit, no push, no PR.
- Non-goals honored: no Engine / Service / UI / Fins changes, no RemoteProxy / RemoteStub path, no public API shape change, no OpenHostOptions change, no public error code change, no audit JSONL semantic change.

## Changed Files

- `dayu/host/durable/projection.py`
  - Added `ProjectionResetResult`.
  - Added `reset_projection_refs_for_deleted_events(...)`, owned by the projection durable module.
  - The helper deletes checkpoint/failure rows only when their EventLog ref is in the caller-provided deleted EventLog ids and the consumer is explicitly rebuildable.
  - The helper rejects non-rebuildable consumers before deleting any projection rows.
- `dayu/host/durable/purge.py`
  - Narrow adjacent change: replaced purge-local private checkpoint/failure reset SQL with the new projection durable helper.
  - Direct evidence: P15-S5 requires “Add projection reset helper”; prior reset implementation lived privately inside purge, so using the new owner helper required this small call-site update.
- `dayu/host/recovery.py`
  - Added a Session row existence recheck before recovery classification mutates or wakes any non-terminal Run.
  - Missing Session rows now produce `StartupRecoveryDecision.NOT_FOUND` with reason `session_missing`.
- `dayu/host/dispatch.py`
  - Added Session row existence recheck to queue promotion candidate reads.
  - Added Session row existence recheck before lane-acquired dispatch moves to `DISPATCHING`.
- `tests/host/test_projection_checkpoint.py`
  - Added direct helper tests for rebuildable-only projection checkpoint/failure reset.
- `tests/host/test_projection_read_model.py`
  - Added rebuild test proving purge deletes target Session facts and read model repair replays only remaining EventLog rows.
- `tests/host/test_recovery_scan.py`
  - Added missing-Session guard coverage showing recovery does not append recovery/lost facts from residual non-terminal Run rows.
- `tests/host/test_purge_session.py`
  - Added independent-process smoke: process A opens public Host and purges; process B opens a separate public Host handle and verifies `get_session`, `get_run`, `retry_run`, `replay_run`, and `watch_session_events` fail closed with existing `NOT_FOUND`.

## Implementation Strategy

- Moved projection reset ownership to `dayu.host.durable.projection` instead of leaving purge-specific SQL as the only implementation.
- Kept purge precondition truth unchanged: Session / Run / Attempt / EventLog governance rows remain the only purge truth. The projection helper consumes already-collected EventLog ids and never decides whether purge is allowed.
- Hardened recovery and dispatch at their local candidate reads and final dispatch recheck, so residual or concurrently missing Session rows are skipped rather than recovered or dispatched.
- Used actual `multiprocessing.Process` smoke with separate Python processes and separate SQLite connections; no same-process multi-handle substitute and no remote worker / wire protocol.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_purge_session.py -q
```

Result:

```text
74 passed in 6.01s
```

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

## README Decision

- README not updated in this slice.
- Reason: the handoff explicitly says not to implement S6 docs/import-boundary/full validation. P15-S5 changed local hardening and tests, but did not change user-facing commands, public API shape, configuration, or stable Host architecture text. Documentation updates for implemented purge semantics remain assigned to P15-S6 by the approved plan.

## Residual Risks / Uncovered Areas

- RemoteProxy / RemoteStub multiprocess purge behavior remains out of scope and deferred to the existing remote follow-up owner.
- Multiprocess race coverage proves post-commit independent-process read-after-purge fail-closed behavior. It does not add artificial sleeps inside the purge transaction; SQLite transaction/CAS ordering remains the intended mechanism for simultaneous command-vs-purge races.
- The recovery missing-Session test uses a controlled FK-disabled residual row to prove the defensive guard. Normal purge still deletes Run rows with FK enforcement on, so this is a hardening test rather than the standard purge path.

## Completion Status

P15-S5 implementation complete and locally validated. No commit, push, review, or PR action was performed.
