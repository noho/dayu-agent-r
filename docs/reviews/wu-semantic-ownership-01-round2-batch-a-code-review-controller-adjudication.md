# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Code Review Controller Adjudication

## Scope

- Batch: A - Web/Doc/FMP boundary safety plus OpenAI retry count.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-controller-validation.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-ds.md`

## Decisions

### DS-F01 - Playwright URL safety uses wrong exception type

Decision: accepted.

Reason: same URL safety owner fact is projected differently across requests and Playwright paths. This is a direct semantic ownership violation and can change LLM-facing recovery semantics.

Required fix:
- Playwright blocked URL path must raise or translate to the same Web fetch URL safety exception used by requests/meta-refresh paths.
- Tests must verify Playwright blocked URL projects `permission_denied` with safety diagnostics.

### DS-F02 - HTTP redirect hops not tracked in meta-refresh visited set

Decision: accepted.

Reason: not a private-network bypass, but the loop-prevention owner is split between redirect and meta-refresh handling. The fix is low-risk and directly adjacent to Batch A redirect ownership.

Required fix:
- Track redirect hop URLs in the visited URL set or otherwise make meta-refresh loop prevention consume the same hop history.

### DS-F03 - Body-limit exception context may read unbounded response.content

Decision: accepted.

Reason: the body-limit owner must not call a diagnostic helper that may read the remaining unbounded raw body after a limit trip. The external impact is bounded, but it directly violates the accepted body-limit owner correction.

Required fix:
- `_FetchBodyLimitExceeded` must not eagerly build context by reading `response.content`.
- Use bounded already-read excerpt / empty diagnostic context, or make context construction explicitly bounded.

### DS-F04 - Retry change is mathematical clarification

Decision: rejected-with-reason.

Reason: reviewer records this as non-defect; current tests validate desired retry-count contract.

### DS-F05 - Redundant decompressed-size check

Decision: rejected-with-reason.

Reason: defense-in-depth redundancy is acceptable and not a material semantic ownership defect.

## MiMo Review

MiMo reported pass with zero material findings. Residual live-browser smoke risk remains recorded, not blocking Batch A fix.

