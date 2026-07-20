# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Re-Review Controller Adjudication

## Scope

- Batch: A - Web/Doc/FMP boundary safety plus OpenAI retry count.
- Review fix: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-codex.md`
- Review fix validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-rereview-ds.md`

## Findings Final State

- DS-F01: fixed. Playwright URL safety violations now preserve the Web fetch URL safety owner exception across worker process boundaries and project as `permission_denied`.
- DS-F02: fixed. HTTP redirect hop URLs are included in the visited set used by meta-refresh loop prevention.
- DS-F03: fixed. Body-limit exception diagnostics no longer read unbounded `response.content`.
- DS-F04: rejected-with-reason in code-review adjudication; no fix required.
- DS-F05: rejected-with-reason in code-review adjudication; no fix required.

## Validation

- Controller validation after review fix:
  - Batch A focused matrix: `118 passed, 1 skipped`.
  - Pyright: `0 errors, 0 warnings, 0 informations`.
  - `git diff --check`: pass.
  - Source scan for old fuzzy fallback / `allow_redirects=True`: no matches.
- MiMo re-review: pass, zero material findings.
- DS re-review: pass, zero material findings.

## Controller Decision

Batch A is accepted locally. Remaining Batch B/C/D/E work remains open.

## Residual Risk

- Live browser smoke was not run; deterministic Playwright worker/projection tests cover the owner semantics.
- Batch B/C/D/E remain unstarted.

