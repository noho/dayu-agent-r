# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S1 - ToolResult invariant and ToolRuntime LLM-facing hint cleanup`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-rereview-ds.md`

## Controller Decision

Both independent re-reviews return `PASS`, with zero new material findings and zero blocking questions.

P3-E S1 is accepted as complete. This closes:

- `P3-E-S1-CR-F01`
- `P3-E-S1-CR-F02`
- `P3-E-S1-CR-F03`
- `P3-E-S1-CR-F04`

## Closure Evidence

### P3-E-S1-CR-F01

Closed. `tests/tools/` cancellation tests now assert ToolRuntime synthetic failure `hint is None`, while the ToolRuntime-owned policy diagnostic reason remains `tool_runtime_cancelled`.

### P3-E-S1-CR-F02

Closed. `_truncation_failure` no longer accepts or discards a `reason_code`, and `_TRUNCATION_*_REASON` dead constants are removed. The structured truncation error remains `truncation_error`.

### P3-E-S1-CR-F03

Closed. Truncation failure tests now assert `error`, exact scenario-specific `message`, and `hint is None` through a shared helper. The covered scenarios include cursor missing, token mismatch, cursor used, invalid request, TTL expiry, scope mismatch, digest mismatch, and unreplaceable target.

### P3-E-S1-CR-F04

Closed. Accept rejection tests now prove `idempotency_conflict` remains in the accept barrier owner-authored message, `hint is None`, and raw fake result text is not leaked.

## Validation Accepted

Controller validation already passed:

- affected pytest matrix: `233 passed, 1 skipped, 3 warnings`
- pyright: `0 errors, 0 warnings, 0 informations`
- source scans for hidden hint protocol and truncation dead constants
- `git diff --check`
- coverage workaround: `137 passed, 17 deselected`; `dayu/contracts/tool_result.py` `100%`, `dayu/host/tool_runtime.py` `85%`

## Residual Risk

- P3-E S2 and S3 remain unimplemented and must continue under the accepted P3-E plan.
- Full-repository tests were not run for S1 closeout; the affected matrix, pyright, source scans, diff check, and coverage workaround were sufficient for this slice gate.

## Next Gate

Proceed to `WU-SEMANTIC-OWNERSHIP-01 P3-E S2 - wait callback typed provider status ref and accepted status projection`.

