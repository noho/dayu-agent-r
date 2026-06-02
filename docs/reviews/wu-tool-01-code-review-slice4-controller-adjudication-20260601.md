# WU-TOOL-01 Slice 4 Code Review Controller Adjudication

## Gate

- Work unit: WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics
- Slice: Slice 4 - Regression Matrix, README Sync, Type Check
- Gate: code review
- Controller role: adjudication only；不直接实施 specialist code change。

## Inputs

- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation report: `docs/reviews/wu-tool-01-implementation-slice4-codex-20260601.md`
- Code review:
  - `docs/reviews/wu-tool-01-code-review-slice4-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-review-slice4-ds-20260601.md`

## Adjudication

No blocking findings. Slice 4 code/doc review passes.

- Cross-Attempt regression is accepted: same `run_id`, different Attempt, same tool/args executes as a fresh request, does not reuse prior refs, and duplicate key differs by Attempt scope.
- Fresh ToolRuntime handle / restart regression is accepted: same Attempt id and same tool/args re-executes with a fresh in-memory governance object, and the test names this as non-durable in-memory behavior rather than a correctness premise.
- `dayu/host/README.md` update is within Host README responsibility and replaces run-scoped duplicate registry wording with attempt-local in-memory duplicate governance plus `HostToolingOptions.duplicate_governance_policy` configuration surface.
- `tests/README.md` update is within test README responsibility and replaces old run-scoped duplicate registry coverage wording with attempt-scoped / in-flight / cross-Attempt / restart / trace scope coverage.
- Terminology grep residual matches are accepted because they belong to truncation cursor, reactive compaction token, or test data id contexts, not duplicate governance.

## Non-blocking Notes

- `test_duplicate_key_includes_attempt_id` was renamed and strengthened into behavior-level cross-Attempt regression. The original key-scope assertion remains covered.
- The implementation report references `test_reactive_recovery_uses_fresh_duplicate_governance_attempt`, which was introduced earlier and not modified in Slice 4. This is acceptable because Slice 4 relies on the already accepted dispatch regression as part of the final matrix.

## Controller Verification

Controller ran:

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tooling_options.py
source .venv/bin/activate && pyright
rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md
```

Result:

- Targeted pytest: 123 passed
- `pyright`: 0 errors, 0 warnings, 0 informations
- Terminology grep: remaining matches are allowed truncation cursor, reactive compaction token, or test data id contexts; no duplicate governance run-scoped/run-local wording remains.

## Decision

Slice 4 reaches accepted checkpoint and may be committed.
