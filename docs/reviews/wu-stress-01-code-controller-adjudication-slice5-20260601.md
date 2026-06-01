# WU-STRESS-01 Slice 5 Code Review Controller Adjudication

## Gate

- **Gate**: Slice 5 code review adjudication
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Slice**: Slice 5 mixed Host stress with deterministic fault injection
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice5-codex-20260601.md`
- **Review artifacts**:
  - `docs/reviews/wu-stress-01-code-review-slice5-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice5-ds-20260601.md`

## Controller Position

Both reviewers returned **PASS**. The implementation satisfies the Slice 5 plan without production code, public contract, durable schema or watch cursor changes. MiMo specifically verified the non-obvious `RUN_LOST` watch behavior: `RUN_LOST` is a durable/public snapshot fact but not a `HostEventKind`, so primary watcher counts `(4, 5, 4)` are correct.

Two low-severity DS findings should be fixed before acceptance because they are cheap diagnostic/readability improvements inside the same touched test file.

## Finding Decisions

### DS-01: `_SLICE5_PRIMARY_TERMINAL_COUNTS` needs maintenance explanation

- **Decision**: accepted, fix before re-review.
- **Reason**: The counts are intentionally not equal to per-session run counts because `RUN_LOST` is not emitted as a public `HostEvent`. That distinction is easy to break during future script edits.
- **Required fix**: Add a concise Chinese comment near `_SLICE5_PRIMARY_TERMINAL_COUNTS` explaining each tuple entry and the `RUN_LOST` exclusion, or add an equivalent local helper/constant naming that makes this explicit. Do not change behavior unless the explanation exposes a real mismatch.

### DS-02: `_slice5_timeout_summary` dedupe fields are internally inconsistent

- **Decision**: accepted, fix before re-review.
- **Reason**: Timeout summary is diagnostic output. `terminal_duplicate_count=0` with `terminal_dedupe_ok=False` can mislead readers even though `failure_boundary="unknown"` carries the primary signal.
- **Required fix**: Make timeout summary placeholder values internally consistent. Prefer `terminal_duplicate_count=0` and `terminal_dedupe_ok=True` to express "no duplicate evidence was available in this synthetic timeout summary"; keep `scheduler_drained=False`, `liveness_stale_detected=False` and `failure_boundary="unknown"` as the failure signal. If choosing a different representation, document why it is not contradictory.

## Required Fix Validation

After the focused fix, run:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k mixed_host_stress -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
```

## Next Gate

Dispatch a focused Slice 5 fix to AgentCodex. After the fix artifact is produced, request independent re-review from AgentMiMo and AgentDS before controller acceptance.

## Re-Review And Final Acceptance

### Re-review artifacts

- `docs/reviews/wu-stress-01-code-rereview-slice5-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-rereview-slice5-ds-20260601.md`

Both re-reviewers returned **PASS**. DS-01 and DS-02 are closed:

- `_SLICE5_PRIMARY_TERMINAL_COUNTS` now has a local Chinese explanation for `(4, 5, 4)`: `RUN_LOST` is a durable/public snapshot fact and is not emitted as `HostEvent` to live watchers.
- `_slice5_timeout_summary` now uses internally consistent synthetic timeout placeholders: `terminal_duplicate_count=0`, `terminal_dedupe_ok=True`, and `failure_boundary="unknown"` remains the failure signal.

Controller reran:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k mixed_host_stress -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Results:

- Slice 5 targeted stress passed: `1 passed, 4 deselected`.
- Full Host production stress file passed: `5 passed`.
- Package/export/import/weak typing guard tests passed: `25 passed`.
- Pyright reported `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

README decision: no `tests/README.md` update is required because Slice 5 did not change stress marker policy, default pytest exclusion, command syntax, or summary schema.

**Controller decision**: accept Slice 5 for local commit. Remaining residual risks are accepted for this work unit and must be carried to aggregate review: pytest-timeout can still terminate the process before internal summary generation if the event loop is globally wedged; `RUN_LOST` is not a live `HostEventKind`; and mixed stress is deterministic bounded coverage rather than fuzz/soak.
