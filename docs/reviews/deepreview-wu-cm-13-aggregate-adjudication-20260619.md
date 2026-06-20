# WU-CM-13 Aggregate Deepreview Adjudication

## Scope

- Work unit: `WU-CM-13`
- Gate: aggregate deepreview after all accepted implementation slices
- Accepted implementation commits:
  - Slice 1: `0390c9ad`
  - Slice 2a: `b180a510`
  - Slice 2b: `7b0367ab`
  - Slice 2c: `7aab0f94`
- Aggregate review artifacts:
  - `docs/reviews/deepreview-wu-cm-13-aggregate-mimo-20260619.md`
  - `docs/reviews/deepreview-wu-cm-13-aggregate-ds-20260619.md`

## Controller Validation

- `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 305 tests.
- `python -m pyright dayu/ tests/ utils/` passed with 0 errors, 0 warnings, 0 informations.
- `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto` passed. The smoke reported `SMOKE COMPACT_ACCEPTANCE status=pass requested_proactive=4 compacted_proactive=4 failed_total=0 artifact_files=12` and `SMOKE PASS public Host conversation memory scenario smoke`.
- `git diff --check` passed before adjudication edits.

## Judgment

Both aggregate reviews are accepted as PASS. No fix gate is required.

WU-CM-13 satisfies the accepted plan:

- proactive dispatch and reactive ingest both build compact requests through `build_normal_compact_request_plan(...)` from `compact_pipeline.py`;
- proactive tier recovery, reactive pass queue, and proactive/reactive fallback decision inputs are owned by shared compact pipeline helpers;
- ordinary post-compaction RunInput protected raw-tail eligibility and memory dedup are owned by `select_ordinary_protected_raw_tail(...)`;
- WU-CM-14 protected recent answer preservation is no longer a proactive-only, reactive-only, or RunInput-only semantic path;
- fallback RunInput rendering remains intentionally unchanged and no tier 5 / `fallback_tier` path was introduced;
- LLM-facing accepted tool evidence rendering filters internal event, payload, artifact, and digest provenance while preserving business-readable source text;
- no public API, durable schema, EventLog canonical semantic, Engine contract, or compact artifact contract changes were introduced.

## Finding Decisions

| Finding | Decision | Reason |
|---|---|---|
| `WU-CM-13-S1-R1` compact quality / provenance edge | closed | The old malformed compacted payload fact-ref edge no longer maps to the new typed helper boundary: `build_compacted_payload_input(...)` receives typed `ConversationCompactOutputVNext`, while candidate quality rejection remains covered at operation level and evidence-label/provenance mapping remains covered by compact payload/material tests. Aggregate review artifacts independently accepted this closure. |
| Smoke hard gate | closed for local acceptance | The required public Host conversation memory smoke was run without modifying the smoke and passed in `memory-compact` mode. This satisfies the user-added WU-CM-13 acceptance criterion for local phaseflow. |

## Conclusion

WU-CM-13 aggregate deepreview is accepted. Proceed to accepted deepreview commit. After that commit is recorded in the control doc, the next gate is ready-to-open-draft-PR / PR workflow decision.
