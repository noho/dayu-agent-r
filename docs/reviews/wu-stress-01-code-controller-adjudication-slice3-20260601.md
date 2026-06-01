# WU-STRESS-01 Slice 3 Code Review Controller Adjudication

## Gate

- **Gate**: Slice 3 code review adjudication
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Slice**: Slice 3 sustained watch stress with slow consumer and reconnect
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice3-codex-20260601.md`
- **Review artifacts**:
  - `docs/reviews/wu-stress-01-code-review-slice3-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice3-ds-20260601.md`

## Controller Position

Slice 3 implementation is directionally correct and stays within test-only scope, but it should not be accepted yet. The accepted plan requires deterministic behavior assignment before public submit dispatch can observe the run, and it explicitly asks for per-session watch lag samples. These are not stylistic preferences; they are part of the stress proof. A focused fix is required before Slice 3 can enter re-review.

The design source confirms that `watch_session_events` is a live watch without caller cursor or disconnect replay. Therefore, reconnect assertions must continue to verify only post-reconnect terminal observation, while disconnect-window terminal truth is proven through primary watcher, public snapshot, Outbox and durable diagnostics.

## Finding Decisions

### MIMO-F01 / DS-F02: post-submit `set_run_behavior` race

- **Decision**: accepted, fix in current Slice 3 before re-review.
- **Reason**: A production stress test must make fault scripts deterministic. Assigning `FAILED` after `submit_followup` returns leaves a scheduling window where the worker can accept with default behavior. This weakens the test's root cause signal and conflicts with the plan's explicit queue-before-submit direction.
- **Required fix**: Replace the affected post-submit `factory.set_run_behavior(...)` calls with a pre-submit queued behavior path such as `_submit_scripted_followup(..., StressWorkerBehavior.FAILED)`, or an equivalent deterministic helper.

### DS-F01: `behavior_for_run` docstring omits queued behavior fallback

- **Decision**: accepted, fix in current Slice 3.
- **Reason**: `DeterministicStressWorkerFactory` is now part of the stable stress helper surface for later slices. Its docstring must describe the queue fallback so future test authors do not accidentally reintroduce post-submit behavior assignment.
- **Required fix**: Update the Chinese docstring to state the lookup order: explicit run behavior, queued next-accept behavior, default behavior.

### MIMO-F02: `close_host_event_iterator` duplicated helper semantics

- **Decision**: accepted as documentation/ownership fix, not as forced cross-module import.
- **Reason**: The helper is small and test-local, and importing recovery-specific helper code into stress support could create a worse ownership dependency. The immediate problem is unclear ownership and duplication rationale.
- **Required fix**: Keep the helper in `stress_support.py` if desired, but update its docstring to explicitly state that it mirrors the recovery test cleanup semantics for a test-local stress helper and is not a compatibility wrapper or production lifecycle abstraction.

### MIMO-F03: magic thresholds in reconnect and gap diagnostics

- **Decision**: accepted, fix in current Slice 3.
- **Reason**: These thresholds encode plan expectations and should be derived from named constants or scenario data. Hard-coded values make future stress scale changes fragile.
- **Required fix**: Introduce named constants or derive thresholds from expected counts / `gap_run_ids`, including secondary first attach count, reconnect terminal count and disconnect gap count.

### DS-F03: `gap_diagnostics_ok` name overstates what it checks

- **Decision**: accepted, fix in current Slice 3.
- **Reason**: Failure boundaries must map to the actual violated proof. A property named as full gap proof but checking only Outbox coverage can mislead future debugging.
- **Required fix**: Either rename/split the predicate so it represents Outbox gap coverage precisely, or expand the predicate so it truly covers primary/public/outbox/durable gap proof. Keep `failure_boundary="projection"` only for projection/Outbox failure.

### DS-F04: global `watch_lag_samples` rather than per-session diagnostics

- **Decision**: accepted, fix in current Slice 3.
- **Reason**: The plan explicitly requires per-session lag samples. A single global queue can hide a slow or starved session behind faster sessions, weakening the sustained-watch proof.
- **Required fix**: Preserve per-session lag diagnostics, for example via `watch_lag_samples_by_session: tuple[tuple[int, ...], ...]`, then flatten only when populating `HostStressSummary.watch_lag_samples`. `watch_lag_ok` should verify each session has samples and final lag drains.

### MIMO-F04: redundant `tuple([...])`

- **Decision**: accepted, fix opportunistically in current Slice 3.
- **Reason**: This is low risk and inside the same touched file.
- **Required fix**: Remove unnecessary intermediate lists where no semantic value is added.

## Deferred / Rejected Items

- **Reconnect replay cursor**: rejected for current work unit. The design source states public watch has no caller cursor and no offline replay responsibility. Reconnect remains "observe post-reconnect terminal"; disconnect-window truth is proven through primary watcher, public snapshot, Outbox and durable diagnostic.
- **Slice 5 terminal dedupe redesign**: deferred to Slice 5 as planned. Slice 3 only needs to avoid duplicate terminal observations in this scenario.

## Required Fix Validation

After the fix, run:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q
python -m pyright dayu/ tests/ utils/
```

## Next Gate

Dispatch a focused Slice 3 fix to AgentCodex. After the fix artifact is produced, request independent re-review from AgentMiMo and AgentDS before controller acceptance.

## Re-Review Controller Decision

### Re-review artifacts

- `docs/reviews/wu-stress-01-code-rereview-slice3-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md`

Both re-reviewers returned **PASS** and verified that the original controller-accepted findings were closed. However, AgentDS raised two low findings and two open questions. One open question maps directly to the accepted plan's expected assertion that the secondary reconnect watcher observes the terminal run id submitted after reconnect. A final focused fix is required before controller acceptance.

### DS re-review F-01: `consumer_cancel_ok` docstring overstates predicate scope

- **Decision**: accepted, fix with docstring precision unless implementation can cheaply encode all four checks in typed diagnostics.
- **Reason**: The test body covers all four required consumer-cancel steps, but the property only checks EventLog count stability and worker cancel count. The docstring should not claim a wider predicate than the code enforces.
- **Required fix**: Update the property docstring and return description to state the exact two checks, or add the missing fields to diagnostics and include all four checks.

### DS re-review F-02: primary watcher double close

- **Decision**: accepted, fix in current Slice 3 if low-risk.
- **Reason**: The current double close is functionally harmless, but the stress test should keep cleanup intent explicit because watcher lifecycle is part of the tested contract.
- **Required fix**: Track whether primary watchers were already closed, or move normal cleanup to a single path so the finally block only performs fallback cleanup.

### DS open question: reconnect count without reconnect run id assertion

- **Decision**: accepted, fix in current Slice 3.
- **Reason**: The plan requires the reconnect watcher to observe the terminal run ids submitted after reconnect. Counting one event is weaker than asserting that the observed event belongs to the `reconnect_run_id`.
- **Required fix**: Carry the expected reconnect run id into diagnostics or add an explicit assertion after `secondary_reconnect_events` is collected. `reconnect_ok` should prove the reconnect event run id, not only event count.

### DS open question: weak lag threshold

- **Decision**: accepted as tightening if local and low-risk.
- **Reason**: With per-session count-based lag, `_SLICE3_RUN_COUNT` is a cross-session upper bound and does not add useful signal. The intended upper bound is per-session.
- **Required fix**: Use a per-session lag limit such as `_SLICE3_RUNS_PER_SESSION` or another named constant derived from per-session run count. Keep final drain to zero as the strongest assertion.

### Residual items not requiring fix

- `read_latest_event_sequence` may remain if intended for later slices; it is already documented as diagnostic and does not affect Slice 3 correctness.
- The deterministic bounded nature of the stress scenario remains an accepted residual risk for WU-STRESS-01.
- `compute_watch_lag` may continue to serve numeric lag deltas, but if touched by the fix, comments or local helper names should avoid implying global sequence semantics for per-session count usage.

## Final Fix Validation

After the final focused fix, run:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q
python -m pyright dayu/ tests/ utils/
```

## Final Acceptance

### Final re-review artifacts

- `docs/reviews/wu-stress-01-code-final-rereview-slice3-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-final-rereview-slice3-ds-20260601.md`

Both final focused re-reviews returned **PASS** with no new findings. The final fix closed the DS re-review low findings and open questions:

- `consumer_cancel_ok` docstring now precisely describes the two structured diagnostics fields covered by the property while the test body covers the other two consumer-cancel steps.
- `reconnect_ok` now proves that `secondary_reconnect_events` contains the exact `expected_reconnect_run_id`, and the test body also asserts the same run id immediately after collection.
- `primary_watchers_closed` prevents normal-path double close while preserving fallback cleanup on exceptions.
- `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT` derives lag bound from per-session run count.

Controller reran the required validation:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q
python -m pyright dayu/ tests/ utils/
```

Results: Slice 3 targeted stress passed (`1 passed, 2 deselected`), full stress file passed (`3 passed`), watch/event-stream regressions passed (`20 passed`), and pyright reported `0 errors, 0 warnings, 0 informations`.

README decision: no `tests/README.md` update is required because Slice 3 did not change stress marker policy, default pytest exclusion, command syntax or test-running contract.

**Controller decision**: accept Slice 3 for local commit. Remaining residual risk is the accepted WU-STRESS-01 risk that this is a deterministic bounded stress scenario, not randomized fuzzing or slow-disk pressure testing.
