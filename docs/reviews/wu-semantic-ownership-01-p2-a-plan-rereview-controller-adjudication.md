# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: plan re-review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-controller-validation.md`
- Initial plan reviews:
  - `docs/reviews/plan-review-20260709-p2-a-mimo.md`
  - `docs/reviews/plan-review-20260709-p2-a-ds.md`
- Controller plan-review adjudication/fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/plan-review-20260709-p2-a-rereview-mimo.md`
  - `docs/reviews/plan-review-20260709-p2-a-rereview-ds.md`

## Verdict

Accepted.

Both AgentMiMo and AgentDS re-reviews concluded `pass`. All accepted initial plan-review findings are closed in the current P2-A plan, and neither review introduced a new blocking finding.

## Accepted Finding Closure

| Finding | Source | Controller status |
|---|---|---|
| S1 glue facade risk: prompt / interactive must call the new public helper internally and delete old private helpers | AgentMiMo | Closed |
| S1 context slot ownership: command modules construct slot values; helper accepts already-built values | AgentDS | Closed |
| S1 RuntimeDisplayController separation | AgentDS | Closed |
| S2 broad `RuntimeError` semantics | AgentMiMo | Closed by requiring CLI-private `FinsDirectStreamContractViolation(RuntimeError)` |
| S1 import-boundary automation | AgentMiMo / AgentDS | Closed by requiring AST-level CLI boundary test |
| S3 prompt / interactive `NOT_FOUND` exit-code policy | AgentDS | Closed |
| S3 `HostApiError` helper pure function coverage | AgentDS | Closed |

## Controller Decision

P2-A plan may enter implementation after the accepted plan commit.

Implementation must preserve the plan's owner boundaries:

- CLI existing-session execution composition owns shared command execution identity, runtime preparation, and Host submit/watch orchestration.
- Prompt and interactive command modules continue to own their distinct context slot construction before calling the shared helper.
- CLI Fins direct streaming owns only the CLI observation of Service direct-stream contract violation; it must not manufacture a fake Fins business terminal event.
- CLI `HostApiError` presentation owns user-facing message and exit-code mapping only; Host remains the owner of durable error facts.

## Implementation Stop Conditions

The implementation agent must stop and return to controller adjudication if any of these conditions occur:

- Extracting shared prompt / interactive execution would require duplicating REPL or terminal display semantics.
- The Fins direct Service stream contract is not stable across real command paths.
- The prompt / interactive `HostApiError` policy would need to change user-visible CLI contracts beyond the accepted plan.

## Next Gate

Move from `plan-rereview` to `accepted-plan`, then dispatch P2-A implementation to AgentCodex.
