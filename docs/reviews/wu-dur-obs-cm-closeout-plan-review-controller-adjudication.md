# WU-DUR / WU-OBS / WU-CM Closeout Plan Review Controller Adjudication

## Gate

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-plan-review-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-plan-review-ds.md`

## Verdict

Plan review result: fail, requires plan fix.

Controller judgment: the plan's motivation and dependency chain are accepted, but the plan is not yet code-generation-ready. Both reviewers found the same root issue: the plan delegates too many schema, manifest, digest and signal-shape decisions to implementation. That violates the gate requirement that implementation must not invent public/durable contracts.

## Accepted Blocking Findings

### A1. Slice 0 contract shape is too abstract

Source findings: MiMo F-01/F-02, DS B1.

Ruling: accepted.

Reason: Slice 0 is the design true-source writeback for all later slices. The plan must specify concrete contract shapes or explicit design acceptance criteria before code implementation begins.

Required fix: amend the plan with a consolidated contract appendix for `RunnerCallInputAssemblyManifest`, message entry shape, projector metadata shape, tool-call arguments atom shape, and Tool Trace signal shape. Each field must include name, type, requiredness, semantics, digest/ref boundary and validation rule.

### A2. Inline-vs-ref and storage-form decisions are unresolved

Source findings: MiMo F-03/F-04/F-06, DS B1.

Ruling: accepted.

Reason: arguments storage and runner-call manifest storage determine durable schema and payload descriptor shape. Leaving this to implementation would create divergent truth boundaries.

Required fix: amend the plan to decide whether tool-call arguments use bounded inline, payload ref, or both; define the exact threshold by reusing the existing payload inline threshold policy if applicable; define payload descriptor kind names; decide whether runner-call manifest is canonical event, artifact, payload descriptor, or a combination, and state why it does not become Run state truth.

### A3. `limited-signal` / `mismatch` diagnostic shape is undefined

Source findings: MiMo F-05, DS N5 and checklist.

Ruling: accepted.

Reason: WU-OBS-P00, F02 and F01 all rely on limited-signal as a fallback. Without a shared typed shape, each slice can invent incompatible diagnostics.

Required fix: define the diagnostic contract with status enum, reason enum, missing atom/ref fields, observed/expected counts or digests where relevant, and the consumer boundary.

### A4. `runner_call_kind` is incomplete and overlapping

Source findings: DS B2; related to MiMo F-02.

Ruling: accepted.

Reason: the manifest must identify call kind without ambiguity. The current enum omits retry/replay/resume/follow-up distinctions and overlaps tool continuation with forced answer.

Required fix: define a closed enum or typed classification model with non-overlapping semantics. If multiple dimensions are needed, split kind from trigger/reason instead of overloading one enum.

### A5. Compactor internal runner-call identity is ambiguous

Source findings: DS B3; related to MiMo F-06/F-11.

Ruling: accepted.

Reason: compactor has its own Engine run identity while being parented to a Host user run and compaction operation. The plan must not blur self and parent ids.

Required fix: define explicit parent/self fields such as parent Host run id, compaction operation id, and compactor Engine run id or equivalent typed identity. Clarify how this relates to existing `CONTEXT_COMPACTED` artifact refs and rejected attempt diagnostics.

### A6. Plan overstates the compact query gap

Source findings: DS B4.

Ruling: accepted.

Reason: design.md already requires `tool_name` in `EvidenceReadableItem`; the actual gap is arguments / semantic query readability in `query_text`, not total tool identity loss.

Required fix: narrow the motivation and success signal for WU-CM-01-F02 accordingly.

### A7. Slice 0 needs a design review sub-gate before code slices

Source findings: DS B5.

Ruling: accepted.

Reason: current plan review cannot validate the future `design.md` writeback. Slice 0 must be reviewed and accepted before Slice 1-7 implementation.

Required fix: add a design-review sub-gate after Slice 0 with artifact path, acceptance criteria and stop condition.

## Accepted Non-blocking Plan Improvements

- Add explicit tests proving manifests do not inline full messages and stay size-bounded.
- Clarify Engine vs Host ownership for role sequence digest, runner-call index and manifest refs.
- Discuss existing `semantic_input_digest` and whether semantic query is its preimage or a separate optional readable atom.
- Define chunked evidence query text behavior operationally.
- Mark which test files are existing and which are new.
- Align smoke entry counting with the control doc's four utility smoke scripts.
- Add smoke workspace freshness note for fresh-schema-only behavior.

## Rejected Or Deferred Findings

None rejected.

Prompt rewrite reordering is deferred-with-owner to the plan fix agent. It may remain late if the fixed plan explains why validation should happen after durable slices, or move earlier if the agent can preserve dependency clarity.

Provider-specific assistant `tool_calls` / `reasoning_content` handling is deferred-with-owner to Slice 0 design review. The fixed plan must either scope it into Slice 0/2 or explicitly assign it to a later WU if it would expand this chain.

## Next Gate

Next gate: plan fix by AgentCodex.

Expected fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`.

Stop condition: if the plan cannot be amended without making new architecture decisions beyond `docs/host/design.md`, AgentCodex must report blocked instead of inventing the design.
