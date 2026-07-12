# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Code Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A / S1`
- Gate: code review controller adjudication
- Time: `2026-07-12T13:44:14+0800`
- Branch: `phaseflow/host-issues-control`
- Baseline: accepted plan `4a282850`, control-doc plan acceptance `41bd6ca9`
- Inputs:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-controller-validation.md`

## Controller Decision

S1 code review does not pass. AgentCodex identified three evidence-backed owner-boundary defects that are inside S1 scope and must be fixed before accepted slice commit.

MiMo reported pass and DS reported pass with low-severity observations, but both pass conclusions missed at least one strict-consumer or full-manifest semantic path. The controller decision is therefore not majority-based; it follows direct code/design evidence.

## Finding Adjudication

### Codex-F1: strict compact path downgrades durable payload corruption to missing evidence

- Decision: `accepted`
- Severity: high
- Owner: compact material strict consumer boundary plus shared durable payload resolver.
- Evidence: `project_accepted_tool_result()` catches `HostDurableError` from `event_payload_object()` and returns an unavailable diagnostic; `_accepted_tool_evidence_delta_blocks()` then returns `()` before request provenance checks. For compact material, this turns accepted evidence payload corruption into silent omission.
- Required fix: compact strict path must resolve the result payload through the shared integrity owner before lenient projection can swallow read failures. `HostDurableError` must propagate from compact material construction for descriptor/row/artifact/canonical JSON corruption. Add tamper tests that prove compact material fails closed for accepted result payload damage.

### Codex-F2: Tool Trace validates manifest bytes and metadata item shape, not the complete manifest semantic graph

- Decision: `accepted`
- Severity: medium
- Owner: `dayu.host._runner_call_manifest` as runner-call manifest contract owner; Tool Trace must consume typed validated output from that owner.
- Evidence: Engine continuation message entries use `projector:{message.index}:{message.role}`, while the manifest metadata array contains only `projector:{iteration_index}:engine-observed`. Tool Trace reads the digest-verified JSON but only validates the six-field metadata item shape and uniqueness, not message count, contiguous indexes, message-entry metadata refs, closed `projector_id` / `purpose`, or hot/manifest identity consistency. `docs/host/design.md` requires those invariants.
- Required fix: add a full manifest parser/validator owned by `_runner_call_manifest`, validate schema/identity/count/index/message metadata refs/closed enums, make continuation entries reference existing metadata, and have Tool Trace project summaries only from the typed validated manifest. Replace tests that treat metadata-only JSON as a valid manifest with real producer manifests and fail-closed counterexamples.

### Codex-F3: shared hot owner validates writers, but consumers still synthesize complete diagnostics

- Decision: `accepted`
- Severity: medium
- Owner: `_runner_call_manifest` hot payload contract owner; Tool Trace and Engine ingest are consumers.
- Evidence: `tool_trace._runner_call_diagnostic()` and `engine_ingest._runner_call_payload_diagnostic()` return complete diagnostics from sibling scalar fields when `validation_status="complete"` without requiring or validating `diagnostic`. Current tests also accept `diagnostic=None`, while S1 design requires complete hot payload diagnostic to be explicit.
- Required fix: expose and use a shared typed hot payload parser/validator from `_runner_call_manifest`. Complete diagnostics must be read and cross-checked against status/count/digest; missing, mismatched, legacy array, or malformed diagnostic shapes must fail closed. Align `docs/host/design.md` so it no longer says complete diagnostic may be null.

### DS-F1: ordinary RunInput `iteration_index=None` may hide future manifest values

- Decision: `rejected-with-reason`
- Severity: low
- Reason: no current execution path writes a non-null ordinary RunInput `iteration_index`; the finding is future-defensive and does not demonstrate an existing S1 semantic failure. It can be revisited if ordinary RunInput begins accepting iteration-owned input.

### DS-F2: compact material extra validation calls may be out of S1 scope

- Decision: `rejected-with-reason`
- Severity: low
- Reason: direct `git diff 41bd6ca9 -- dayu/host/compact_material.py` shows the cited `validate_previous_compacted_view_pair`, `previous_answer_anchor_block_text`, `parse_context_compacted_semantic_payload`, and `ConversationCompactOutputVNext` usages already existed in the accepted baseline. Current S1 diff only touches `_accepted_tool_evidence_delta_blocks` in this area.

## Fix Gate

AgentCodex must fix Codex-F1, Codex-F2, and Codex-F3 in one S1 fix pass. The fix must stay within S1 scope:

- no schema DDL or migration;
- no S2-S8 lifecycle/admin/scheduler behavior;
- no compatibility fallback for old hot rows or old manifest shapes;
- no downstream repair in Tool Trace, Engine ingest, compact material, or tests;
- owner-level tests must assert fail-closed behavior at the shared owner boundary.

Expected fix artifact:

`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-fix-codex.md`

Required validation after fix:

- focused S1 matrix from controller validation;
- stress suite serial;
- `python -m pyright dayu/host tests/host`;
- targeted scans for removed `projector_metadata_summary` hot usage, null complete diagnostic success fixtures, and metadata-only manifest success fixtures;
- `git diff --check`.
