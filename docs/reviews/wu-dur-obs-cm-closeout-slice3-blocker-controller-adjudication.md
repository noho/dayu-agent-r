# WU-DUR-P01 Slice 3 Blocker Controller Adjudication

## Verdict

blocker accepted. Slice 3 must be retried with an expanded allowed file set.

## Reviewed Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-blocker-review-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-blocker-review-ds.md`
- `docs/host/wu-dur-obs-cm-closeout-plan.md`
- `docs/host/design.md`

## Decision Basis

The blocker is real. Slice 3 requires a durable compactor proposal runner-call manifest before the compactor proposal call, and accepted / rejected compact events must reference that manifest. The production owner chain crosses files outside the initial allowed set:

- `dayu/host/compaction_operation.py` owns the proposal attempt loop and attempt number.
- `dayu/host/dispatch.py` owns `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED` durable EventLog writes.
- `dayu/host/durable/schema.py` is the correct single truth source for `compactor_input_projection` descriptor kind.

Implementing only inside `llm_compaction.py`, `context_events.py`, or `engine_ingest.py` would require a side channel, fake manifest, preview-only artifact, or re-running material selection. All of those violate the design and AGENTS constraints.

## Reslice Decision

The plan remains valid; the slice owner boundary was too narrow. Retry Slice 3 with an expanded allowed file set.

Minimum expanded allowed files:

- `dayu/host/llm_compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_payload.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_public_compact_smoke.py`
- `dayu/host/README.md`
- `tests/README.md`

If `ContextCompactor` protocol changes are required, the retry must stop and produce a follow-up blocker before editing `dayu/host/compaction.py`.

## Required Retry Scope

- Add production manifest data flow from compactor proposal request construction through `CompactionOperationResult` / `CompactionAttemptRejected` to compact EventLog payloads.
- Add `compactor_input_projection` descriptor kind in `dayu.host.durable.schema`.
- Ensure `CONTEXT_COMPACTED` references the accepted proposal manifest.
- Ensure rejected / failed proposal attempts reference their proposal manifest through typed payload fields.
- Keep compactor proposal as Host-owned internal runner call, not a Host admitted Run.
- Do not change compact output schema.

## Next Gate

Slice 3 implementation retry with expanded allowed files.
