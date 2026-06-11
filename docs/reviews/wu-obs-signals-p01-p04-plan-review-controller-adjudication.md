# WU-OBS-SIGNALS-01 Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: plan review controller adjudication
- Plan artifact: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-plan-review-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-plan-review-ds.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Controller decision: plan requires fix before implementation.

## Overall Judgment

Both reviews support combining WU-OBS-P01 / P02 / P03 / P04 into WU-OBS-SIGNALS-01. The combination is valid because all four signals share the same Host-owned path:

```text
Engine / ToolRuntime / Context canonical or diagnostic fact
-> EventLog canonical / diagnostic / projection_signal
-> ToolTraceProjectionConsumer
-> hot trace_summary_json + cold JSONL
-> future WU-OBS-00 analyzer
```

The plan remains within scope: it does not implement the analyzer, does not change Engine budget ownership, does not make Tool Trace durable truth, and does not change ToolRuntime execution semantics. However, several review findings identify missing contract detail that would force the implementation agent to make design decisions. Those findings are accepted and must be fixed in the plan artifact before implementation.

## Finding Adjudication

| Source | Finding | Decision | Controller reason | Required plan fix |
|---|---|---|---|---|
| AgentMiMo | MIMO-001 P01 `context_pressure` source incomplete / budget decision fields not explicitly sourced | accepted | The plan says to reuse `BudgetEstimate` and `decide_context_budget`, but it does not explicitly state that `_append_projection_signal` will add a new Host-owned `context_pressure` payload object containing derived budget decision fields. Implementation should not have to choose between EventLog payload contract change and projection-layer recomputation. | Clarify that `USAGE_REPORTED` projection_signal payload contract is extended with `context_pressure`; the fields are produced in Engine ingest from Host context budget policy and not recomputed by Tool Trace projection. |
| AgentMiMo | MIMO-002 P02 `tool_timing` changes `TOOL_RESULT_ACCEPTED` payload contract | accepted | Adding `tool_timing` to a canonical payload is a payload contract extension even if it does not change execution semantics. The plan must name that boundary and require consumer impact checks. | Explicitly mark `tool_timing` as additive Host EventLog payload field, not SQLite schema, not state-machine change, and require tests that existing consumers tolerate additive fields. |
| AgentMiMo | MIMO-003 P03 `failure_metadata` changes `TOOL_RESULT_ACCEPTED` payload contract | accepted | Same contract-scope issue as MIMO-002, with higher semantic risk because this field is analyzer-facing. | Explicitly mark `failure_metadata` as additive payload field and list affected consumers/tests. |
| AgentMiMo | MIMO-004 P04 `partial_tool_call_signal` changes `PROVIDER_PROTOCOL_ERROR` diagnostic payload contract | accepted | The only stable source for bounded summaries is `ProviderProtocolErrorData.partial_tool_calls`; implementation must add the structured diagnostic payload field intentionally. | Explicitly mark `partial_tool_call_signal` as additive diagnostic payload field produced by Host ingest. |
| AgentMiMo | MIMO-005 EventLog payload contract change scope underexplained | accepted | This duplicates MIMO-002 through MIMO-004 at architectural level and is valid. | Add a dedicated payload contract impact section covering canonical, diagnostic, and projection_signal payload additions and why no schema migration/state transition change is needed. |
| AgentMiMo | MIMO-006 `repair_hint` bounding lacks threshold | accepted | Bounded text requires an explicit, testable threshold. | Define a private constant and numeric threshold in the plan, with digest/truncated flag behavior and tests. |
| AgentDS | DS-001 P03 missing explicit `tool_cancelled` variant | accepted | `ToolCancelledOutcome` is not a tool failure and must not be mapped into `tool_failed`. This is required before implementation. | Add `failure_kind="tool_cancelled"` variant with `cancel_reason`, bounded `cancel_message`, bounded `cancel_hint`, and tests. |
| AgentDS | DS-002 P01 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` context pressure treatment undecided | accepted | Attempt rejected rows carry budget-after-attempt and next policy decision; WU-OBS-00 should not have to parse raw context event payload to follow the budget chain. | Decide that `CONTEXT_COMPACTION_ATTEMPT_REJECTED` gets a compact `context_pressure` projection shape derived from existing payload fields. |
| AgentDS | DS-003 `_trace_summary` signature expansion risks God function | accepted | The existing function already has many parameters. Adding four more directly would violate project maintainability constraints. | Require a grouped carrier such as `_TraceSummarySignals` or an extension of `_ToolTraceExtract` so `_trace_summary` does not gain four independent parameters. |
| AgentDS | DS-004 Unified `failure_metadata` shape has coupling risk | accepted | A single object can work only as a discriminated union with sealed variants and clear null semantics. | Define `failure_metadata` as a discriminated union keyed by `failure_kind`; list allowed variants and variant-specific fields. |
| AgentDS | DS-005 OBS-SIG-00 caller update wording can blur slice boundaries | accepted | The plan should keep foundation slice mechanical and leave payload extraction to individual slices. | Clarify OBS-SIG-00 only adds grouped signal carrier and passes empty/default signals; P01-P04 populate actual values. |
| AgentDS | DS-006 `repair_hint` threshold missing | accepted | Same as MIMO-006. | Covered by MIMO-006 required fix. |
| AgentDS | DS-007 `policy_ref` / digest LLM-facing constraint missing | accepted | AGENTS.md requires internal refs/digests to be labeled as diagnostic provenance, not business facts or reasoning grounds. | Mark `policy_ref`, `estimator_digest`, `operation_id`, refs and digests as diagnostic provenance only; analyzer LLM-facing output must translate them into business-readable wording. |

## Rejected / Deferred / Needs More Evidence

No plan review findings are rejected, deferred, or marked needs-more-evidence. All accepted findings are plan clarification/design-detail fixes and do not require changing Host or Engine design truth before the plan fix gate.

## Required Plan Fix Scope

AgentCodex must update only `docs/host/wu-obs-signals-p01-p04-plan.md` and address the accepted findings above. The fix should not edit source code, tests, README, control doc, or review artifacts.

The fix must preserve these controller decisions:

- WU-OBS-SIGNALS-01 remains a combined work unit.
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` participates in P01 `context_pressure` projection with a minimal shape derived from existing payload fields.
- New signal fields are additive EventLog payload contract extensions, not SQLite schema changes and not state-machine changes.
- `failure_metadata` is a discriminated union keyed by `failure_kind`.
- `tool_cancelled` is a distinct failure metadata variant.
- `_trace_summary` must not grow four independent optional parameters; use a grouped carrier.
- Internal refs/digests/policy labels are diagnostic provenance only and must not be used as LLM-facing business facts.

## Residual Risks

No unclassified residual risk remains at plan review. Existing plan residual risks retain owners:

- Optional `ToolResultMeta` duration absence: handled by WU-OBS-SIGNALS-01 P02 limited signal.
- Partial arguments raw payload absence: assigned to WU-OBS-00 analyzer limited-signal reporting.
- Large-scale aggregation over unindexed `trace_summary_json`: assigned to WU-OBS-00 analyzer or future query/retention work.

## Completion Status

Plan review gate completed. Next gate is plan fix via AgentCodex.
