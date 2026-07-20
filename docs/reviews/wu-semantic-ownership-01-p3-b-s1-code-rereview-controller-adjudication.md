# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 code re-review controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`.
- Gate: S1 code re-review controller adjudication.
- Re-reviews:
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-rereview-ds.md`
- Decision: accept S1 and enter accepted slice commit gate.

## Finding status

| Finding | MiMo | DS | Controller |
| --- | --- | --- | --- |
| `P3-B-S1-CR-F01` | fixed | fixed | closed |
| `P3-B-S1-CR-F02` | fixed | fixed | closed |

The raw durable-row path now produces an Outbox-specific `HostDurableError` which the public API exposes as the cause of `HostApiError(INTERNAL_ERROR)`. Non-text canonical `finish_reason` fails closed in both Outbox projection and succeeded HostEvent read. No compatibility conversion or alternate owner was introduced.

## Validation accepted

- Focused P3-B matrix: `75 passed`.
- Propagation/ProjectionRunner regression: `305 passed`.
- Pyright: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.
- New material findings: 0.

## Decision

- Accepted findings closed: 2 of 2.
- Blocking open question: none.
- S1 verdict: accepted.
- Next gate: accepted P3-B S1 commit, then aggregate deepreview.
- Umbrella status: active.
