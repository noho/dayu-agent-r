# PR 50 Controller Adjudication

- **PR**: https://github.com/noho/dayu-agent-r/pull/50
- **title**: Host Phase 3 admission state machine
- **date**: 2026-05-14
- **review inputs**:
  - `docs/reviews/pr-50-review-20260514-1555.md`
  - `docs/reviews/pr-50-review-20260514-1603.md`
  - `docs/reviews/pr-50-review-20260514-1604.md`
  - `docs/reviews/pr-50-review-20260514-1555.md` updated after initial read; this adjudication includes its later Finding 1 / Finding 3 additions.

## Summary

Controller accepts two blocking / merge-gating issues and one low-risk maintainability fix:

- `PR50-C-001`: accepted. Post-commit wakeup must be best-effort and must not prevent queue promotion after an active slot is released.
- `PR50-C-002`: accepted. `git diff --check main...HEAD` must pass; current PR diff contains trailing whitespace in a review artifact.
- `PR50-C-003`: accepted. `_require_event_sequence` should use the existing `EventLogStore` read API instead of direct SQL against `event_log`.

The remaining findings are rejected or deferred because they conflict with the approved Phase 3 plan, describe future phase behavior, or request broad hardening tests beyond the PR merge gate. The updated DS finding that asks to include `resolved_execution_target` in follow-up idempotency digest is explicitly rejected because Phase 3 plan and tests deliberately require the opposite behavior.

## Accepted Findings

### PR50-C-001: Post-commit wakeup can block durable queue promotion

- **source findings**:
  - `pr-50-review-20260514-1555.md` finding 2
  - `pr-50-review-20260514-1603.md` finding 1
  - `pr-50-review-20260514-1604.md` findings 1 / 2, accepted only for the wakeup-failure part
- **severity**: high
- **decision**: accepted
- **evidence**:
  - `HostAdmissionService.cancel_run` and `closeout_attempt_terminal` call `_promote_after_release` after the main durable transaction commits.
  - `_promote_after_release` currently calls `wakeup_port.wake_queue_promotion(session_id)` before `promote_next_queued_run(session_id)`.
  - `AdmissionWakeupPort` documents that concrete implementations may raise `RuntimeError`.
- **impact**: A non-durable wakeup failure can prevent the durable promotion attempt after the active slot has already been released. This can leave a queued Run stuck until some other caller manually triggers promotion.
- **required fix**:
  - Durable promotion must be attempted before queue wakeup notification.
  - Queue wakeup failure must not prevent or roll back the promotion result.
  - Add regression tests for active cancel and terminal closeout with a failing queue wakeup port.
- **not accepted from source findings**: Swallowing arbitrary durable promotion failures is not accepted in this PR. `promote_next_queued_run` still represents a durable convergence attempt; if its SQLite transaction fails, that remains an internal durable error until Phase 5 introduces scheduler retry / scan semantics.
- **owner**: AgentCodex fix.

### PR50-C-002: PR diff whitespace check fails

- **source finding**: `pr-50-review-20260514-1603.md` finding 2
- **severity**: low but merge-gating
- **decision**: accepted
- **evidence**: `git diff --check main...HEAD` reports trailing whitespace in `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md:133-150`.
- **impact**: The PR body and Gateflow records claim diff check passed, but the full PR diff check fails.
- **required fix**: Remove trailing whitespace and rerun `git diff --check main...HEAD`.
- **owner**: AgentCodex fix.

### PR50-C-003: `_require_event_sequence` bypasses `EventLogStore`

- **source finding**: `pr-50-review-20260514-1555.md` finding 6
- **severity**: low
- **decision**: accepted
- **evidence**: `admission.py` directly queries `event_log` through `TABLE_EVENT_LOG` even though `EventLogStore.read_event_by_id` already exists.
- **impact**: Low maintainability risk; EventLog reads in admission are split between the store abstraction and direct SQL.
- **required fix**: Route `_require_event_sequence` through `EventLogStore.read_event_by_id` and remove the direct schema-table dependency if no longer needed.
- **owner**: AgentCodex fix.

## Rejected Or Deferred Findings

### Follow-up queue digest excludes `resolved_execution_target`

- **source finding**: updated `pr-50-review-20260514-1555.md` finding 1
- **decision**: rejected.
- **reason**: The finding contradicts the approved Phase 3 plan. The plan explicitly requires follow-up queue idempotency digest to exclude `resolved_execution_target`; same-key same-digest retries must return the first persisted Run even if a later caller supplies a different resolved target. The field is a caller-resolved execution decision, not part of the semantic idempotency key for `submit_followup_queue`.
- **direct plan evidence**:
  - `docs/host/phase3-session-run-attempt-admission-plan.md` states that follow-up queue digest excludes `resolved_execution_target`.
  - The same plan requires repeated same-key / same-digest follow-up retries with a different later resolved target to return the first Run and not mutate `host_runs.execution_target`.
  - `tests/host/test_admission_queue.py::test_followup_idempotency_excludes_later_resolved_execution_target` already locks this behavior.
- **owner**: none for PR 50. If Phase 4 public command path wants a different target-resolution contract, it must reopen design discussion before changing this behavior.

### ATTACH_ACTIVE does not append an EventLog fact

- **source finding**: updated `pr-50-review-20260514-1555.md` finding 3
- **decision**: rejected.
- **reason**: The approved Phase 3 plan explicitly states that `queue_policy=attach_active` with an active Run appends no EventLog row, creates an idempotency record with a null event ref, and returns the active Run. Adding a new canonical event would be a state/event contract change and would exceed PR review fix scope.
- **direct plan evidence**:
  - `docs/host/phase3-session-run-attempt-admission-plan.md` defines attach-active result refs with null event ref.
  - The plan pseudocode says attach-active records the idempotency result and skips the final `USER_INPUT_ACCEPTED` event step because no new Run or canonical fact is created.
  - `tests/host/test_admission_queue.py::test_reject_and_attach_active_have_expected_event_and_idempotency_effects` asserts the no-EventLog side effect behavior.
- **owner**: none for PR 50. Phase 4 may revisit public audit wording only through design discussion.

### Broad failure-path test coverage list

- **source findings**:
  - `pr-50-review-20260514-1555.md` finding 4
  - `pr-50-review-20260514-1604.md` finding 8
- **decision**: rejected as PR-blocking scope; partially accepted only where tied to `PR50-C-001`.
- **reason**: Phase 3 already has state, admission and multiprocess coverage for the planned invariants. The broad list includes useful hardening ideas, but it does not identify a current behavioral defect beyond the accepted wakeup/promotion issue.
- **owner**: future owner depends on touched behavior. Phase 4 owns public API edge coverage; Phase 5 owns dispatch / active worker cancel coverage; Phase 11 owns multiprocess hardening.

### `closeout_attempt_terminal` has no idempotency replay

- **source findings**:
  - `pr-50-review-20260514-1555.md` finding 4
  - `pr-50-review-20260514-1604.md` finding 7
- **decision**: rejected for Phase 3, deferred to Phase 5 EngineEvent ingest owner.
- **reason**: The approved Phase 3 plan explicitly states that `internal_terminal_closeout` is not a public command and tests may call it without idempotency. If a later production owner needs idempotent terminal ingest, that owner must define the operation idempotency contract.
- **owner**: Phase 5 RunInputBuilder 与本地执行 Dispatch / EngineEvent ingest owner.

### Cancel CAS status code inconsistency

- **source finding**: `pr-50-review-20260514-1604.md` finding 3
- **decision**: rejected.
- **reason**: `cancel_running_run_row` has an extra `current_attempt_id` CAS predicate, so `rowcount=0` with latest status still `RUNNING` can represent an identity-race CAS loss. `cancel_queued_run_row` and `cancel_starting_attempt_row` only CAS on id + status; under the same SQLite write transaction, `rowcount=0` while latest remains in the expected status is not the same reachable condition. Unifying all three would make the result less precise.

### REJECT policy does not write idempotency record

- **source finding**: `pr-50-review-20260514-1604.md` finding 4
- **decision**: rejected.
- **reason**: The approved Phase 3 plan explicitly requires `reject` with active Run to append no EventLog row and create no idempotency record. Existing tests assert this behavior.

### ATTACH_ACTIVE idempotent replay can return a Run that is no longer active

- **source finding**: `pr-50-review-20260514-1604.md` finding 5
- **decision**: rejected.
- **reason**: The approved Phase 3 plan says repeated same-digest `attach_active` calls return the originally attached Run by idempotency result ref. The latest Run row may have advanced by the time of replay; that does not create duplicate work or violate durable truth. Phase 4 public snapshot shaping may choose clearer naming if needed.
- **owner for future API wording**: Phase 4 Host Public API Command Path owner.

### Attempt DDL includes future statuses not all reachable in Phase 3

- **source finding**: `pr-50-review-20260514-1604.md` finding 6
- **decision**: rejected.
- **reason**: Phase 3 schema intentionally encodes the Host design status sets, while Phase 3 transition helpers implement only the Phase 3-owned subset. Removing design statuses would make the schema less aligned with `docs/host/design.md`.

## Open Questions Closed

- `WAITING` / `CANCELLING` / `RECOVERING` in active Run definitions are intentional forward-compatible Host status semantics. Phase 3 creates only `RUNNING` active Runs; later phases own transitions into the other active states.
- Deferred items are already tracked in `docs/host/implementation-control.md`; the accepted fix should keep that tracking intact.

## Required Verification After Fix

- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`
- `git diff --check main...HEAD`
