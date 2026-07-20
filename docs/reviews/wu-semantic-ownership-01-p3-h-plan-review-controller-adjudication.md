# WU-SEMANTIC-OWNERSHIP-01 P3-H plan review controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Gate: plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- Goal artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-goal-confirmation.md`
- AgentMiMo review artifact: `docs/reviews/plan-review-20260711-061858.md`
- AgentDS review artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-ds.md`

## Controller Decision

Both reviewers returned `pass-with-risks`. The plan direction is accepted: P3-H should move LLM-facing and user-visible prose to the owning projection/copy boundary, not delete useful output or redesign durable state. However, the current plan is not yet code-generation-ready because several plan details leave implementation agents to decide scope and API shape.

Decision: enter plan-fix gate before implementation. Do not modify production code yet.

## Accepted Plan Fixes

### P3-H-PF-01 - Clarify Fins direct-stream versus job-event sidecar scope

- Sources: AgentMiMo F1, F6; AgentDS Finding 2.
- Decision: `accepted`.
- Rationale: The plan must explicitly classify Fins text by propagation path. All text entering `FinsEvent`, wait outcome, or tool result is current P3-H scope. Text used only as durable/job sidecar state must be explicitly listed as in-scope or out-of-scope with owner and reason; implementation must not guess.
- Required plan fix: update S2 with a concrete scope table for direct stream, wait adapter, and job sidecar text. If job sidecar text remains out of scope, record why it is not a current P3-H blocker and how scans avoid pretending it was moved.

### P3-H-PF-02 - Expand and downgrade source scans to evidence checks

- Sources: AgentMiMo F2, F3; AgentDS Finding 5.
- Decision: `accepted`.
- Rationale: Current scan patterns miss known direct evidence in Web preferred summary and Fins runtime text. Scans are useful as structural checks, not exhaustive proof.
- Required plan fix: expand Web and Fins scans to cover all known P3-H source literals/builders, including `_build_search_web_preferred_summary` and its Chinese summary fragments. State that scans complement tests, helper coverage, and propagation audit rather than replacing them.

### P3-H-PF-03 - Specify Web `SearchWebOutput` migration and imports

- Sources: AgentDS Finding 3.
- Decision: `accepted`.
- Rationale: The plan must be direct enough to prevent compatibility aliases or ad hoc type choices.
- Required plan fix: name the provider-owned fact type, name the projection-owned LLM-facing output type, specify the builder function signature, and specify import direction for `web_tools.py` and tests.

### P3-H-PF-04 - Narrow Web display-name handling to the actual tool declaration owner

- Sources: AgentMiMo F4; AgentDS Open Question 3.
- Decision: `accepted`.
- Rationale: `@tool(...)` declaration is already a projection/declaration boundary for `display_name` and `description`. Moving display names to a separate helper is not required by the root cause and adds needless indirection.
- Required plan fix: revise S1 and BI-6 disposition so display names/descriptions may remain in the `@tool` declaration site. The helper should own cancellation/recovery text and search-result guidance only, unless implementation finds direct evidence of duplicate display-name ownership.

### P3-H-PF-05 - Choose the `web_cancellation_text.py` path

- Sources: AgentMiMo F5; AgentDS Open Question 1.
- Decision: `accepted`.
- Rationale: The plan currently gives mutually valid choices. The implementation gate should not decide whether to delete, keep, or replace the old module.
- Required plan fix: choose one path. Preferred: replace `web_cancellation_text.py` with the new Web projection text owner, update imports directly, and do not keep a compatibility re-export.

### P3-H-PF-06 - Specify Fins direct text helper API boundary

- Sources: AgentMiMo F7; AgentDS Finding 2 / residual risk.
- Decision: `accepted`.
- Rationale: The helper must not become a second `FinsEvent` contract or construct full event objects.
- Required plan fix: specify that `direct_event_text.py` provides typed text constants and small lookup functions only; it must not import or construct `FinsEvent`, `FinsResultSummary`, or `FinsProgress`. Use `FinsOperationKind`, `FinsResultStatus`, and `FinsErrorKind` only as typed inputs where needed.

## Confirmed / Non-Blocking Findings

- DS12 hidden `ToolResultFailure.hint` protocol disposition is confirmed evidence-invalid for current P3-H scope. Keep the regression source scan.
- Fins `direct_events.py` owns event contract shape and validation; it does not currently own the Chinese text content. The plan may add a text helper without replacing `direct_events.py`.
- Three implementation slices remain acceptable after plan fixes.
- Web public tool success JSON should remain stable; moving construction owner is acceptable if public shape stays unchanged.

## Residual Risks

- If plan-fix keeps any job sidecar text out of P3-H scope, it must name the owner/destination and not let the aggregate source scan claim all runtime UI text has moved.
- Implementation must maintain current public tool JSON shape and direct-stream behavior unless the plan explicitly calls out a behavior change and test expectation.

## Next Gate

Dispatch AgentCodex to the plan-fix gate for `P3-H-PF-01` through `P3-H-PF-06`. The fix gate must update only the plan artifact unless it finds the accepted fixes require changing goal confirmation or design truth.
