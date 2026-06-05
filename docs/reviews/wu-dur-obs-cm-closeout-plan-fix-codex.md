# WU-DUR / WU-OBS / WU-CM Closeout Plan Fix

## Gate

- Work unit group: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: plan fix
- Agent: AgentCodex
- Fixed plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Design source read: `docs/host/design.md`
- Control doc read: `docs/host/issues-implementation-control.md`
- Accepted findings source: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-controller-adjudication.md`

## Status

fixed

## Changed Files

- Modified: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Added: `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`

No production code, tests, README, `design.md`, or control doc were modified.

## Accepted Findings Fixed Mapping

| Finding | Fix |
|---|---|
| A1 Slice 0 contract shape too abstract | Added a consolidated contract appendix defining `RunnerCallInputAssemblyManifest`, `RunnerCallMessageEntry`, `ProjectorMetadata`, `ToolCallArgumentsAtom`, Tool Trace signal, diagnostic contract, and compactor identity. Each table includes field name, type, requiredness, semantics, digest/ref boundary, and validation rule. |
| A2 inline-vs-ref and storage-form unresolved | Fixed tool-call arguments as mixed bounded inline / payload descriptor using `payload_inline_threshold_bytes` from design.md §13.1. Defined descriptor kinds `tool_call_arguments_json`, `tool_call_semantic_query_text`, `runner_call_input_manifest`, `runner_call_projection_artifact`, and `compactor_input_projection`. Fixed runner-call manifest storage as `RUNNER_CALL_INPUT_ASSEMBLED` canonical audit/reconstruction event plus payload descriptor/artifact body, with no Run state truth semantics. |
| A3 limited-signal / mismatch diagnostic shape undefined | Added `RunnerCallReconstructionDiagnostic` with `status`, closed `DiagnosticReason`, missing atom/ref fields, observed/expected count and digest fields, and `consumer_boundary`. Updated Slice 4/5 to consume this typed shape. |
| A4 `runner_call_kind` incomplete and overlapping | Replaced the old overlapping kind list with closed `RunnerCallKind` and separate `RunnerCallTriggerReason`. The plan now covers initial/follow-up, tool continuation, forced answer, length continuation, retry/replay/resume, and context compaction without overloading one enum. |
| A5 compactor internal runner-call identity ambiguous | Added `CompactorRunnerCallIdentity` with `parent_host_run_id`, `parent_session_id`, `compaction_operation_id`, `compactor_engine_run_id`, attempt number, request digest, input projection ref, accepted compact event ref, and rejected diagnostic ref. Updated Slice 3 to use `runner_call_kind=compactor_proposal`. |
| A6 WU-CM-01-F02 motivation overstated | Rewrote goal, motivation, success signal, and Slice 5 language to state that `EvidenceReadableItem.tool_name` already carries tool identity; the real gap is missing arguments / semantic query in `query_text`. |
| A7 Slice 0 design review sub-gate missing | Added Slice 0.5 with artifact path `docs/reviews/wu-dur-obs-cm-closeout-design-review.md`, review owner, acceptance criteria, and stop condition. Slice 1-7 cannot be dispatched before this review passes. |

## Accepted Non-blocking Improvements

- Added explicit manifest size-boundary tests: Slice 2 now requires a focused test proving manifests do not inline full messages and remain size-bounded.
- Clarified Engine vs Host ownership: Engine owns execution-local observations; Host owns `runner_call_index`, manifest refs/digests, source refs, projector metadata, and durable writes.
- Clarified `semantic_input_digest`: semantic query is an independent optional readable atom, not assumed to be the digest preimage and not a replacement.
- Defined chunked evidence behavior: chunks from the same tool call share the same base `query_text`; chunk labels carry chunk identity; long arguments are bounded and not repeated.
- Marked tests as `existing` or `new focused`.
- Aligned smoke scope with the four control-doc utility scripts and listed `smoke_host_public_diagnostics.py`.
- Added fresh workspace / DB path requirement for fresh-schema-only smoke validation.
- Kept prompt rewrite as Slice 6 and documented why: final prompt validation depends on durable manifest / trace / compact query shape; moving it earlier does not reduce contract risk.
- Scoped provider-specific assistant `tool_calls` / `reasoning_content`: Slice 0 design review must either include typed digest fields if the Engine contract supports them or defer to a later WU-ENG provider-contract owner; raw dict bags are forbidden.

## Remaining Risks / Open Questions

- No blocking open question remains in the plan.
- Residual risk remains that Slice 0 design writeback could over-expand manifest fields; the new Slice 0.5 design review must reject any writeback that turns the manifest into a hidden messages dump.
- Provider-specific raw assistant/provider state remains deferred unless existing typed Engine contracts are sufficient.

## Why The Plan Is Now Code-generation-ready

The implementation agent no longer needs to invent durable schema shape, enum semantics, inline/ref thresholds, payload descriptor kinds, manifest storage form, Tool Trace diagnostics, or compactor parent/self identity. The plan fixes those decisions at contract level and adds a design review gate before code slices, so implementation can proceed by writing `design.md` first and then generating code against that accepted contract.

## Validation

- This gate only modified plan documentation; pytest and pyright were not required.
- Scope check performed with `git diff --name-only` and `git status --short`. `git diff --name-only` shows pre-existing tracked change `docs/host/issues-implementation-control.md`, which this gate did not modify or revert. The files created/edited by this gate are the allowed plan artifact and expected fix artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md` and `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`.
