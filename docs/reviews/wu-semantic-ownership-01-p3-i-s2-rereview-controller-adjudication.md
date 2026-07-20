# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-I`
- Slice: `S2 CLI Terminal Cursor After Successful Render`
- Initial code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-rereview-ds.md`

## Finding Closure

| Finding | Controller decision | Re-review status |
|---|---|---|
| DS-F1: interactive `terminal is None` cursor non-advancement lacked explicit assertion | accepted | closed |
| DS-F2: cursor write failure propagation lacked tests across prompt / startup / interactive | accepted | closed |

## Controller Validation

- Focused matrix: `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q`
  - Result: `100 passed, 3 warnings`
- CLI suite: `pytest tests/cli -q`
  - Result: `294 passed, 3 warnings`
- Type check: `python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- Whitespace: `git diff --check`
  - Result: passed

## Propagation Audit

- Host/Service terminal facts remain the source of truth for terminal status, terminal event id, event sequence, final answer, error, cancel reason, and lost-run reason.
- CLI renderers still own stdout/stderr rendering and renderer exit-code mapping.
- CLI terminal cursor persistence now advances after successful terminal rendering for success, failed, cancelled, and lost terminal statuses.
- `terminal is None` local interrupt paths have no terminal event to project and therefore do not advance cursor.
- Cursor write failure remains an uncaught local CLI delivery persistence failure; it does not rewrite Host/Service terminal facts or renderer policy.

## Controller Decision

S2 is accepted. Both review agents returned PASS after the fix, all accepted findings are closed, and no new material finding remains open for this slice.
