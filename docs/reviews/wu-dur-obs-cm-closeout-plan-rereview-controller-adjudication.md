# WU-DUR / WU-OBS / WU-CM Closeout Plan Re-review Controller Adjudication

## Gate

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: plan fix re-review adjudication
- Fixed plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Plan fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-ds.md`

## Verdict

Re-review result: pass.

Controller judgment: accepted findings A1-A7 are fixed. The plan is now code-generation-ready for Slice 0 design contract writeback, with a mandatory Slice 0.5 design review sub-gate before code implementation slices.

## Finding Status

| Finding | Controller status | Basis |
|---|---|---|
| A1 Slice 0 contract shape too abstract | 已修复 | Both reviewers verified the consolidated contract appendix now defines field names, types, requiredness, semantics, digest/ref boundaries and validation rules. |
| A2 inline/ref and storage-form decisions unresolved | 已修复 | Both reviewers verified arguments storage, descriptor kinds and runner-call manifest storage form are explicit. |
| A3 limited-signal / mismatch diagnostic shape undefined | 已修复 | Both reviewers verified `RunnerCallReconstructionDiagnostic` and closed reason/status enums. |
| A4 `runner_call_kind` incomplete and overlapping | 已修复 | Both reviewers verified `RunnerCallKind` and `RunnerCallTriggerReason` split classification and cover required paths. |
| A5 compactor parent/self identity ambiguous | 已修复 | Both reviewers verified `CompactorRunnerCallIdentity` separates parent Host run, compaction operation and compactor Engine run identity. |
| A6 WU-CM-01-F02 motivation overstated | 已修复 | Both reviewers verified the plan now states `tool_name` already carries tool identity and the gap is arguments / semantic query readability. |
| A7 missing Slice 0 design review sub-gate | 已修复 | Both reviewers verified Slice 0.5 has artifact path, owner, acceptance criteria and hard stop condition. |

## Residual Risks

- `RunnerCallKind` / trigger reason compatibility matrix remains a Slice 0 design-review detail. Owner: Slice 0.5 design review.
- Provider-specific assistant `tool_calls` / `reasoning_content` fields are included only if existing typed Engine contracts support them; otherwise they must be deferred with owner. Owner: Slice 0.5 design review.
- Chunked evidence query behavior remains a Slice 5 focused implementation/test detail. Owner: Slice 5 implementation review.

All residual risks have owners and do not block accepting the plan.

## Next Gate

Next gate: accepted plan commit.

After the accepted plan commit, phaseflow may dispatch Slice 0 implementation to AgentCodex. Slice 1-7 must not be dispatched until Slice 0.5 design review passes.
