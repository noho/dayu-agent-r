# WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: S2 code re-review controller adjudication
- Accepted finding: `P3-K-S2-CR-F01`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-ds.md`
- Fix artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s2-rereview-ds.md`

## Decision

S2 is accepted after fix and re-review.

`P3-K-S2-CR-F01` is closed as `已修复`. AgentMiMo and AgentDS independently confirmed:

- `attempt_count_for_run(...)` now uses `_HOST_DB_FILENAME`.
- `current_attempt_id_for_run(...)` now uses `_HOST_DB_FILENAME`.
- `"host.sqlite3"` remains only in the `_HOST_DB_FILENAME` constant definition within `tests/host/recovery_support.py`.
- Focused recovery/admission validation passed.
- Pyright passed with zero errors.
- `git diff --check` passed.
- No production code, S1/S3 files, README, control doc, or broad raw SQL refactor was introduced by the fix.

## Finding Status

| Finding | Source | Decision | Final status | Reason |
| --- | --- | --- | --- | --- |
| `P3-K-S2-CR-F01` | AgentDS code review | accepted | 已修复 | The two remaining same-file DB path literals now use `_HOST_DB_FILENAME`, closing the local constant-boundary inconsistency introduced during S2. |

AgentMiMo reported no material findings in the initial S2 code review. AgentDS's additional residual note about other `"host.sqlite3"` literals outside the S2 file/scope is not a current S2 blocker; it remains outside this approved slice and was not expanded into a broader cleanup to avoid scope drift.

## Residual Risk Classification

| Residual risk | Classification | Controller decision |
| --- | --- | --- |
| Stress suite failures in scheduler cleanup and runner-call manifest payload paths. | Assigned outside current slice | Static diff and failure traces show these paths are unrelated to S2 helper semantics. They remain evidence for later stress / scheduler / payload work, not a P3-K S2 blocker. |
| Other `tests/host` files may still contain DB filename literals. | Outside approved S2 scope | This S2 finding concerned the file-local constant introduced in `recovery_support.py`. A repository-wide DB filename cleanup would require a separate owner/scope decision. |
| Remaining raw SQL diagnostic and fault-injection helpers. | Accepted current-scope risk | The approved S2 plan explicitly keeps non-equivalent global diagnostics and impossible-state fault injection as raw SQL with clear docstring ownership. |

## Validation

Controller validation for S2 implementation:

- Public smoke / compact focused tests: `18 passed, 1 skipped`
- Recovery/admission focused tests: `9 passed`
- Support module compile/import checks: pass
- Source scan: `projection_checkpoint_sequence(...)` calls `read_projection_checkpoint(...)`; retained helpers are classified; no cursor replay helper misuse
- Pyright: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: pass

Controller validation for S2 fix:

- DB filename literal scan: literal remains only in `_HOST_DB_FILENAME`
- Recovery/admission focused tests: `9 passed`
- Pyright: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: pass

## Propagation Audit

- Durable checkpoint read truth now flows from `dayu.host.durable.projection.read_projection_checkpoint(...)` to the test helper projection.
- Diagnostic-only raw SQL helpers explicitly project test synchronization diagnostics rather than durable truth.
- Fault-injection-only raw SQL helpers explicitly own impossible recovery states for tests and do not represent production APIs.
- No production durable state, trace, memory, audit, prompt, schema, or user / LLM-facing output changed.

## Completion Status

P3-K S2 implementation, code review, accepted fix, re-review, and controller adjudication are complete. All accepted S2 findings are closed. Next Gateflow entry is accepted S2 slice commit, then P3-K S3 implementation.
