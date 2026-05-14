# Controller Adjudication: Full Repository Deep Reviews

- **Date**: 2026-05-14
- **Branch at collection**: `fix/host-phase-4`
- **Reviewed repository state**: `main` includes PR 51 merge commit `d9feaaf`
- **Input review artifacts**:
  - `docs/reviews/repo-review-20260514-1936.md`
  - `docs/reviews/repo-review-20260514-1937.md`
  - `docs/reviews/repo-review-20260514-1942.md`
- **Controller role**: consolidate duplicate findings, reject findings that conflict with design truth, assign true residual risks to an owner / destination, and identify immediate fix work units.

## Executive Verdict

The three reviews surfaced real defects and useful hardening work, but several highest-severity claims are not current blockers because they contradict the design truth or assume an execution mode the current code intentionally does not provide.

Immediate high-priority accepted work:

1. Engine OpenAI runner cancellation / response cleanup race.
2. Host liveness lifecycle hardening before Phase 11 uses liveness rows as recovery inputs.
3. Durable artifact / bootstrap hardening.
4. Engine parser/provider robustness fixes.
5. Contract and type strictness cleanup.
6. Digest / validation helper deduplication.

Rejected or reclassified as deferred design scope:

1. Host crash recovery missing: already owned by Phase 11.
2. `purge_session` implementation missing: already owned by Phase 15.
3. `close_session` allowing existing Run continuation: explicitly required by design.
4. `cancel_session_runs` no-promotion: explicitly documented Phase 4 behavior and not a stranded-queue bug because queued targets are cancelled in the same operation.
5. EventLog same-id race under normal `BEGIN IMMEDIATE` writer path: reviewer assumption is invalid for the current transaction contract.

## Accepted Findings

### A1 — Engine runner response cleanup on cancellation

- **Source findings**: `repo-review-20260514-1942.md` H-1, related cleanup notes M-6.
- **Decision**: accepted.
- **Severity**: high.
- **Owner / destination**: Engine runner fix work unit.
- **Reasoning**: `AsyncOpenAIRunner._do_attempt()` obtains `response` before entering the `try/finally` that releases it. The local runner adapter raises `_RunnerInterrupted` when cancellation wins. A simultaneous completion/cancel race can prevent the response from reaching the `finally` block. The fix must cover both "response not yet established" and "response established" paths.
- **Required validation**: add a cancellation race test with fake response/session proving `response.release()` is called exactly when a response was acquired and not called before acquisition.

### A2 — Host liveness lifecycle hardening

- **Source findings**: `repo-review-20260514-1937.md` 01 / 02, `repo-review-20260514-1936.md` 6.
- **Decision**: accepted as Phase 11 hardening prerequisite.
- **Severity**: medium-high.
- **Owner / destination**: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening.
- **Reasoning**: `register_current_instance()` currently moves an existing same-identity row back to `RUNNING`; `_mark_current_instance_status()` lacks source-status guards and does not check update rowcount. The control doc already records that Phase 11 must decide whether to tighten these transitions before interpreting liveness rows for recovery. This is not a current recovery bug because Phase 11 recovery is not implemented, but it must be fixed before liveness becomes recovery truth.
- **Required validation**: tests for `STOPPED` / `CRASHED_SUSPECTED` not reverting to `RUNNING` or `STOPPING`, and rowcount zero surfacing as structured identity/lifecycle error.

### A3 — Durable artifact and schema bootstrap hardening

- **Source findings**: `repo-review-20260514-1936.md` 5 / 7 / 18, `repo-review-20260514-1937.md` 12 / 13.
- **Decision**: accepted.
- **Severity**: medium.
- **Owner / destination**: Durable store / Phase 15 production hardening.
- **Reasoning**: bootstrap DDL currently runs in autocommit mode; artifact write cleanup after `os.replace()` only unlinks the temp path; `_write_temp_file` can leak a file descriptor if `os.fdopen` fails. The symlink TOCTOU claim is lower risk in the default single-user workspace but should be considered with the same artifact hardening package.
- **Required validation**: bootstrap failure rollback test where feasible, artifact post-replace failure cleanup test, fd cleanup test, and containment regression test.

### A4 — Engine parser/provider robustness

- **Source findings**: `repo-review-20260514-1936.md` 9 / 10 / 14 / 16 / 17, `repo-review-20260514-1937.md` 06 / 07 / 08 / 09 / 10, `repo-review-20260514-1942.md` 25 / 26 / 36 / 37 / 38 / 39.
- **Decision**: partially accepted.
- **Severity**: medium.
- **Owner / destination**: Engine runner/parser hardening work unit.
- **Accepted items**:
  - Use `TERMINAL_ENGINE_EVENT_TYPES` in `run_agent_and_wait`.
  - Add `assert_never` exhaustiveness guards to closed-union `match` sites.
  - Detect context overflow markers even on 5xx responses if bounded body read remains safe.
  - Fix `ClientPayloadError` docstring mismatch.
  - Move lazy `json` import to module top.
  - Add truncation marker for diagnostic message truncation.
  - Add low-risk parser diagnostics / dead-code cleanup.
- **Needs design decision**:
  - Whether malformed `usage` should downgrade to warning or remain protocol error. Current behavior is harsh but can be intentional protocol strictness; do not silently change without deciding the runner contract.
- **Required validation**: targeted OpenAI runner parser tests plus pyright for `dayu/engine tests/engine`.

### A5 — Contract and public type strictness

- **Source findings**: `repo-review-20260514-1936.md` 13, `repo-review-20260514-1937.md` 17 / 18 / 19 / 20, `repo-review-20260514-1942.md` L-3 / L-7 / 31 / 32 / 42.
- **Decision**: partially accepted.
- **Severity**: medium.
- **Owner / destination**: Contracts cleanup work unit.
- **Accepted items**:
  - `ToolTruncateSpec.strategy` should use `ToolTruncationStrategy | None` rather than `str | None`.
  - Contract-layer docstrings should avoid referencing concrete Engine internal type paths.
  - `TerminalResultSummary` should reject non-terminal statuses.
  - Future `FollowupSnapshot(STEER)` shape should require `target_run_id`.
  - `ToolTruncateSpec.limits` needs documented or typed key semantics.
- **Needs design decision**:
  - Whether `GeminiToolCallState` remains a closed public provider-state member or moves behind a neutral `JsonValue` provider state. This touches public contract shape and should not be done as a drive-by fix.
  - Whether `JsonValue` should gain runtime validation; the current module explicitly states it is a type alias, not a validator.

### A6 — Host digest / validation helper duplication

- **Source findings**: `repo-review-20260514-1936.md` 11 / 20, `repo-review-20260514-1937.md` 14 / 15 / 30.
- **Decision**: accepted.
- **Severity**: medium for digest duplication, low for validation helper duplication.
- **Owner / destination**: Host refactor work unit before further public API expansion.
- **Reasoning**: digest helpers are duplicated across admission, command, and session lifecycle. Because these functions define idempotency semantics, future drift would be correctness-affecting. `_require_positive_sequence`, dispatch mutation result handling, and `_require_non_empty` duplication are lower-risk cleanup.
- **Required validation**: existing Host tests plus focused digest-conflict tests proving unchanged semantic digests.

### A8 — Runtime cancellation / lane hardening

- **Source findings**: `repo-review-20260514-1936.md` 4 / 15, `repo-review-20260514-1937.md` 16, `repo-review-20260514-1942.md` M-5 / L-4 / L-5 / L-8 / 27 / 28 / 29.
- **Decision**: accepted as runtime hardening, severity downgraded where current callers do not trigger the path.
- **Severity**: low-medium.
- **Owner / destination**: runtime hardening work unit, with Phase 11 pressure tests for lane behavior.
- **Reasoning**: custom awaitable cleanup is a valid public helper edge case but current Dayu callers mostly pass coroutine / Task. Lane shield release and heartbeat-loss notification are real cancellation-edge hardening items. `getattr` in SQLite classification has an explicit stub-compatibility reason and is accepted as non-blocking.

### A9 — Maintainability refactors

- **Source findings**: `repo-review-20260514-1942.md` H-5 / M-2 / M-7 / M-8, `repo-review-20260514-1936.md` 16.
- **Decision**: accepted as non-blocking refactor backlog.
- **Severity**: medium for long-term maintainability, not an immediate correctness blocker.
- **Owner / destination**: separate refactor plans after state-machine phases stabilize.
- **Reasoning**: `_AsyncAgent`, `LaneController`, and `state.py` are large and should be split, but these changes are too broad to combine with correctness fixes. Message compaction / Host-readable message history belongs to Host context governance work.

## Rejected Or Reclassified Findings

### R1 — EventLog same-id UNIQUE race under current transaction path

- **Source findings**: `repo-review-20260514-1936.md` 1, related `repo-review-20260514-1942.md` 41.
- **Decision**: rejected as current correctness bug; accepted only as future defensive note.
- **Reasoning**: current write operations run under `HostTransactionRunner.run_write()` with `BEGIN IMMEDIATE`, so two writers cannot both pass the pre-insert read for the same SQLite durable DB. The review assumes concurrent writers can run the SELECT/INSERT window simultaneously, which is false for the intended write path. If a future path bypasses `run_write`, it must document or enforce equivalent serialization.

### R2 — `run_write` COMMIT retry repeats committed side effects

- **Source finding**: `repo-review-20260514-1936.md` 2.
- **Decision**: rejected as stated; accepted as doc hardening.
- **Reasoning**: the implementation rolls back on `sqlite3.Error` before retrying. SQLite transaction-side effects from `operation()` are not committed on that path. The valid residual risk is that operation bodies must not perform external side effects before commit; current operation bodies are durable transaction bodies. The docstring can say this explicitly.

### R3 — CAS failure after EventLog append should be normal structured result

- **Source finding**: `repo-review-20260514-1936.md` 3.
- **Decision**: rejected as current concurrency bug.
- **Reasoning**: with `BEGIN IMMEDIATE`, the transition operation owns the write transaction. CAS failure after an EventLog append indicates a stale internal precondition or implementation bug, not ordinary concurrent writer loss. Throwing and rolling back the transaction is acceptable.

### R4 — `cancel_session_runs` should promote queued Run

- **Source findings**: `repo-review-20260514-1936.md` 12, `repo-review-20260514-1937.md` 03.
- **Decision**: rejected.
- **Reasoning**: Phase 4 `cancel_session_runs` cancels all supported non-terminal targets in one operation. If a queued Run exists and is supported, it is cancelled, not left waiting for promotion. If any unsupported non-terminal Run exists, the operation fails before mutation. README and control docs explicitly say this path does not trigger promotion.

### R5 — `close_session` must reject active / queued Runs

- **Source findings**: `repo-review-20260514-1942.md` M-1 / M-3.
- **Decision**: rejected.
- **Reasoning**: design truth explicitly states `close_session` only closes new input entry; it does not cancel, terminate, purge, or delete existing Runs. Already accepted queued / active Runs may continue to terminal. This is not a TOCTOU bug; it is the intended `close` vs `cancel` separation.

### R6 — Missing Host crash recovery is a current blocker

- **Source finding**: `repo-review-20260514-1942.md` H-2.
- **Decision**: reclassified as deferred design scope.
- **Reasoning**: Phase 11 explicitly owns startup recovery scan, positive orphan proof, and RECOVERING dispatch. The current code is not production-complete before Phase 11, but this is not a regression in the completed phases.

### R7 — Missing `purge_session` is a current blocker

- **Source finding**: `repo-review-20260514-1942.md` H-3.
- **Decision**: reclassified as deferred design scope.
- **Reasoning**: Phase 4 intentionally freezes the public signature and returns `UNSUPPORTED_OPERATION`; Phase 15 owns destructive cleanup and purge tombstone semantics.

### R8 — `allow_private_network_url=false` proves active SSRF vulnerability

- **Source finding**: `repo-review-20260514-1937.md` 05.
- **Decision**: rejected by scope.
- **Reasoning**: the reviewed tree does not contain the web fetch implementation or a planned config-file loading path. A `run.json` field without an implementation consumer is not an executable SSRF bypass and is not a current bug.

### R9 — `llm_models.json` placeholders / loader behavior are bugs

- **Source findings**: `repo-review-20260514-1937.md` 04 / 23 / 33 and related `llm_models.json` observations.
- **Decision**: rejected by owner decision.
- **Reasoning**: user explicitly ruled that `llm_models.json` placeholder / loader behavior is not a bug. These items must not be treated as accepted findings or included in automatic fix scope.

### R10 — `run.json` unused fields / missing tests are bugs

- **Source findings**: `repo-review-20260514-1937.md` 24 / 34 and related `run.json` observations.
- **Decision**: rejected by owner decision.
- **Reasoning**: user explicitly ruled that `run.json` is not a bug because the project has not yet planned to implement config-file loading. These items must not be treated as accepted findings or included in automatic fix scope.

## Proposed Fix Sequencing

1. **Engine runner cancellation cleanup**: fix A1 with regression tests.
2. **Engine parser/provider strictness**: fix accepted parts of A4.
3. **Host liveness hardening**: fix A2 before Phase 11 starts.
4. **Host digest/helper dedupe**: fix A6 before adding more public command paths.
5. **Durable artifact/bootstrap hardening**: fix A3 as production-hardening work.
6. **Contracts cleanup**: fix non-design-breaking parts of A5; open a design decision for provider-specific tool-call state.
7. **Runtime/lane hardening**: fold into Phase 11 pressure testing.
8. **Large refactors**: split `_AsyncAgent`, `LaneController`, and `state.py` only as dedicated refactor plans.

## Validation

No production code was changed by this adjudication. The controller inspected the cited implementation and design/control docs to classify findings. No test run was required for the adjudication artifact itself.

## Tracking Requirement

None of the accepted residual risks may remain conversation-only. The next implementation work unit selected from this adjudication must cite this artifact and carry the relevant accepted finding ids into its plan / fix artifact.
