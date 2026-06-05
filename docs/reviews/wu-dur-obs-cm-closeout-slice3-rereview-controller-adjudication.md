# WU-DUR-P01 Slice 3 Re-Review Controller Adjudication

## Verdict

accepted

## Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-fix-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-rereview-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-rereview-ds.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-controller-adjudication.md`
- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- Current workspace diff

## Accepted Findings Status

| Finding | Controller status | Evidence |
|---|---|---|
| Reactive accepted compact lacks proposal manifest ref/digest | fixed | Both re-reviews verify `engine_ingest.py` passes `proposal_manifest_recorder` and writes `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` into reactive `CONTEXT_COMPACTED`. |
| Reactive rejected attempts lack proposal manifest ref/digest | fixed | Both re-reviews verify reactive `CONTEXT_COMPACTION_ATTEMPT_REJECTED` receives `proposal_manifest_ref` / `proposal_manifest_digest` from `CompactionAttemptRejected`. |
| Proactive manifest path regression risk | fixed / no regression | Both re-reviews verify proactive dispatch still records manifest before proposal runner call and still fail-closes accepted compact without manifest ref/digest. |
| Accepted compact missing proposal manifest guard lacks direct test | fixed | `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed` covers ref and digest missing cases. |

## New Findings Adjudication

### N1. `DurableCompactorProposalManifestRecorder` is not listed in `compaction_operation.__all__`

- Source: AgentDS re-review
- Severity: low
- Decision: rejected-with-reason
- Rationale: `DurableCompactorProposalManifestRecorder` is a Host-internal durable helper used by explicit same-layer imports from `dispatch.py` and `engine_ingest.py`. `__all__` controls star import/public export convention; adding the recorder would broaden the module's public surface without a current caller need. The absence from `__all__` does not affect explicit imports, tests, pyright, or runtime behavior. Keeping it out is consistent with minimizing public contract exposure.

## Residual Risks

The following residual risks remain tracked in `docs/host/issues-implementation-control.md` and are not Slice 3 blockers:

- `WU-DUR-P01-S2-R1`
- `WU-DUR-P01-S2-R2`
- `WU-DUR-P01-S3-R1`
- `WU-DUR-P01-S3-R2`

The reactive generic non-prepared compactor behavior noted by AgentMiMo is not accepted as an additional residual risk for this slice. The controller fix task explicitly allowed generic non-prepared fake compactors to remain without proposal manifests; production `LLMContextCompactor` uses the prepared path.

## Validation Evidence

Controller local validation before acceptance:

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
  - `94 passed, 1 skipped`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## Next Gate

Create accepted Slice 3 commit after final focused validation.

