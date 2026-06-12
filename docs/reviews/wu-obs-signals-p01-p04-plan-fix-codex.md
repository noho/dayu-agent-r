# WU-OBS-SIGNALS-01 Plan Fix Codex Artifact

## Metadata

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `plan fix`
- Plan artifact: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Controller adjudication artifact: `docs/reviews/wu-obs-signals-p01-p04-plan-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-plan-fix-codex.md`

## Changed Plan Sections

- `EventLog payload contract`
- `Shared Projection Shape`
- `P01 Context Pressure / Budget Snapshot`
- `P03 Structured Failure Metadata`
- `P04 Partial Tool-call Summary`
- `OBS-SIG-00 Shared Tool Trace Signal Foundation`
- `OBS-SIG-01` through `OBS-SIG-04` implementation slices and validation notes
- `Risks / Open Questions / Residual Risks`

## Accepted Findings Coverage

All controller-accepted findings were covered in the plan artifact:

- P01 `USAGE_REPORTED.context_pressure` is Host-owned, produced in Engine ingest from Host budget policy, `BudgetEstimate`, and `decide_context_budget`; Tool Trace projection only copies it.
- `tool_timing`, `failure_metadata`, and `partial_tool_call_signal` are documented as additive EventLog payload contract extensions, not SQLite schema or state-machine changes.
- P03 defines independent `tool_cancelled` variant with cancellation reason, bounded message, bounded hint, truncation flags, digests, and cancellation-vs-failure tests.
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` now has a minimal `context_pressure` projection shape derived from existing payload fields.
- OBS-SIG-00 requires a grouped signal carrier and forbids adding four independent `_trace_summary` parameters.
- `failure_metadata` is a closed discriminated union keyed by `failure_kind`, with variant-specific fields and explicit null semantics.
- Foundation slice boundary is clarified: it wires empty/default grouped signals only; P01-P04 populate actual values.
- Bounded text uses `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512` with truncation flag and original-text digest rules.
- `policy_ref`, `estimator_digest`, `operation_id`, refs, and digests are marked diagnostic provenance only, not business facts or LLM reasoning grounds.
- Combined WU, non-goals, and stop conditions remain unchanged: no analyzer, no Engine public contract change, no SQLite migration, no ToolRuntime execution semantic change.

## Validation

- Pytest: not run.
- Pyright: not run.
- Reason: this was a plan fix gate and only documentation artifacts were changed; no production code or tests were modified.

## Residual Risks

- Implementation must still prove additive payload fields do not affect existing EventLog consumers.
- Implementation must verify actual source fields are available for P01 context compaction projections.
- Large-scale aggregation over unindexed `trace_summary_json` remains assigned to future analyzer/query work.
- Bounded free-form text still carries sensitivity risk, mitigated by truncation and digest rules in the plan.

## Completion Status

Plan fix gate completed by Codex. No code, tests, README, control document, existing review artifacts, commit, push, PR, merge, implementation gate, review gate, or re-review gate were performed.
