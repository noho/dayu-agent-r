# WU-TOOLS-01-F01-02 Aggregate Deepreview Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F01-02`
- Gate: aggregate deepreview adjudication
- Design source: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-02-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-aggregate-deepreview-ds.md`
- Date: 2026-06-08

## Controller Decision

Aggregate deepreview is accepted with no required fix. The work unit may proceed to accepted deepreview commit.

Both AgentMiMo and AgentDS concluded PASS. They independently validated that all migrated Fins / Web / Doc tools in scope have explicit cancellation token propagation, that long-running or risk-bearing paths have cooperative cancellation checkpoints appropriate to their risk class, that Host remains the cancellation governance truth, and that LLM-facing schemas do not expose Host internal execution context fields.

## Findings

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| `_save_cancelled` directly writes `CANCELLED` in the create-submit gap | AgentDS | rejected-with-reason | This is the intended terminal handling for a job that has been durably created but never submitted. It does not replace Host cancel truth or introduce a second cancel state machine. |
| Legacy Web / Doc / Fins read tools project cancellation through `ToolBusinessError(code=\"tool_cancelled\")` instead of `ToolCancelledOutcome` | AgentDS | deferred-with-owner | This is the accepted WU residual risk R3. It requires an adapter-wide cancellation outcome contract decision and is outside this WU. |
| Synchronous requests / filesystem / processor calls cannot be physically interrupted by token | AgentDS | deferred-with-owner | This is the accepted WU residual risk R2. Current implementation uses bounded timeouts plus checkpoints before and after blocking calls; physical interruption belongs to provider-specific runtime or wait/cancel follow-up design. |
| Informational lock-order / helper duplication observations | AgentMiMo | rejected-with-reason | They do not demonstrate a current correctness issue. Any future common helper extraction must first respect layer boundaries and avoid leaking tool-specific errors into `dayu.runtime`. |

## Success Signal Review

- Cancellation propagation audit: accepted. The aggregate matrix covers Fins awaiting 2, Web 2, Doc 5, and Fins read 9 tool entries.
- Long transaction response: accepted. Fins awaiting tools cover pre-start and create-submit gap cancellation; background job cancel remains durable job-store governed.
- Risk-based checkpoints: accepted. Web provider fallback, Doc file/processor paths, and Fins read/search/XBRL loops have cooperative checkpoints.
- Host cancel truth: accepted. Tools observe tokens only; no tool-private cancel truth replaces Host durable cancel.
- Awaiting accept orphan job window: deferred with owner. Two-stage startup is not implemented in this WU and must not be introduced without Host / Engine design-source update.
- LLM-facing schema isolation: accepted. Tests cover `properties` and `required` exclusion for `execution_context` and `cancellation_token`.
- README / tests / pyright: accepted. Required validations are green, and README updates were made only where production/test documentation boundaries required them.

## Residual Risk

No new active residual risk is introduced by aggregate deepreview.

Remaining residual risks and destinations:

- R1 awaiting accept orphan job / two-stage startup: deferred to WU-WAIT-03 or an independent design follow-up.
- R2 non-preemptible synchronous I/O / processor internals: accepted limitation for this WU; provider-specific owners may add deeper interruption support later.
- R3 legacy adapter cancellation outcome projection: deferred to a separate adapter cancellation contract WU.
