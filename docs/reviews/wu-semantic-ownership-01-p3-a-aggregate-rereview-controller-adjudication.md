# WU-SEMANTIC-OWNERSHIP-01 P3-A aggregate re-review controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-A`.
- Gate: aggregate re-review controller adjudication.
- Review base/head: `2400a04c` through current working tree after the accepted aggregate fix.
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-rereview-ds.md`
- Decision: accept the aggregate fix and enter accepted deepreview commit gate.

## Review merge

- AgentMiMo: PASS; `P3-A-AGG-F01` and `P3-A-AGG-F02` closed; 0 new material finding.
- AgentDS: PASS; `P3-A-AGG-F01` and `P3-A-AGG-F02` closed; 0 new material finding.
- Both reviewers independently verified the full P3-A S1/S2/S3 range plus the uncommitted aggregate fix, rather than only reviewing the final two changed files.

## Finding adjudication

### P3-A-AGG-F01 - closed

`_read_active_run_id` now dynamically consumes `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`, matching the public active-run read. The real-SQLite test replaces the owner set with `{QUEUED}` and proves public read and `SessionSnapshot.active_run_id` remain aligned. The old hardcoded query would fail that test.

### P3-A-AGG-F02 - closed

All four start-transition active-run CAS guards now consume the same owner-generated SQL clause and serialized parameters. The parameterized real-SQLite test proves all four transitions return `CAS_LOST` for an owner-defined queued sibling and retain the unblocked `UPDATED -> RUNNING` path.

### P3-A-AGG-F03 - deferred with owner

Non-terminal EventLog taxonomy remains assigned to P3-J. Both reviewers confirmed it is not a current P3-A blocker.

### New material findings - none

Neither reviewer found a new correctness, stability, maintainability, or semantic-ownership defect requiring a fix loop.

## Residual reconciliation

| Residual | Controller disposition | Owner / destination |
| --- | --- | --- |
| Partial unique-index DDL repeats the current five start-blocking status literals | Current members are aligned and schema tests guard the present contract; future closed-set/schema hardening remains required when the enum changes | P3-J |
| Non-terminal EventLog constants remain distributed | Explicit P3-A non-goal | P3-J |
| Admission `allowed_pairs` overlaps the lifecycle closeout-supported subset | Current branches are semantically correct; remove the weak duplicate contract during lifecycle/schema contract hardening | P3-J |
| Terminal answer/outbox continuity consumes P3-A facts downstream | Approved later sub WU | P3-B |
| Real cross-process Engine/Host terminal race stress is not represented | No current failure evidence; retain as EventLog/concurrency hardening coverage | P3-J / production stress validation |

No residual is left without an owner. None is evidence that the accepted aggregate fix is incomplete.

## Validation accepted

- Controller affected matrix: `337 passed`.
- AgentDS affected matrix: `337 passed`.
- AgentMiMo focused and aggregate subsets: `238 passed`.
- Full pyright: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.
- Import and source scans: clean.
- Propagation audit: the owner chain from `RunStatus` and durable row rules through `START_BLOCKING_RUN_STATUSES`, SQL material, public/private reads, snapshot projection, and four write guards is closed.

## Completion

- Accepted findings closed: 2 of 2.
- New material findings: 0.
- Blocking open question: none.
- Aggregate re-review verdict: accepted.
- Next gate: accepted P3-A deepreview commit, then P3-B plan gate.
- Umbrella status: still active; P3-A does not close `WU-SEMANTIC-OWNERSHIP-01`.
