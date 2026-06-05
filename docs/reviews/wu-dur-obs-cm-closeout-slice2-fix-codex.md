# WU-DUR-P01 Slice 2 Fix - Codex

## status

fixed

## changed files

Fix-specific files:

- `dayu/host/durable/schema.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-fix-codex.md`

Existing Slice 2 implementation files remain modified in the workspace. `docs/host/issues-implementation-control.md` was already modified in the current workspace and is outside this fix gate allowed file set; this fix did not edit or revert it.

## accepted findings mapping

- S2-F1 blocking: fixed. Engine-internal continuation `iteration_started` now causes Host ingest to write a canonical `RUNNER_CALL_INPUT_ASSEMBLED` limited-signal manifest when no matching manifest exists for that Engine iteration.
- S2-F2 medium: fixed. Tool Trace no longer hardcodes non-complete diagnostic details to `None`; it reads typed diagnostic fields from canonical payload and fails closed if a non-complete signal lacks a diagnostic object.
- S2-F3 medium: fixed. Continuation limited-signal validation is now visible through the canonical manifest event and Tool Trace projection, not only through `EventClass.PREVIEW`.

## implementation evidence

- `EngineEvent` still owns only execution-local observations; no Host runner call index, manifest ref, source refs, memory refs, compact refs, or tool schema refs were added to Engine events.
- `EngineEventIngestor` handles `iteration_started` before generic preview mapping. It looks for a manifest matching the same attempt / execution and Engine iteration. If none exists, it writes `RUNNER_CALL_INPUT_ASSEMBLED` as `EventClass.CANONICAL_FACT`.
- The continuation manifest is explicitly `limited_signal`: it records Host-owned `runner_call_index`, manifest ref / digest, Engine-observed `message_count`, `role_sequence_digest`, iteration identity, bounded source refs, projector metadata summary, and typed diagnostic reason `missing_projection_artifact`.
- The continuation manifest body stores no full message text, prompt, memory snapshot, compact material, provider raw request / response, or raw provider dict.
- Existing ordinary RunInputBuilder manifests remain complete signals. The manifest lookup now avoids matching continuation iterations to the ordinary first-call manifest by requiring exact `iteration_id`, or allowing the pre-existing ordinary manifest only for `iteration_index == 0` when its iteration id is not yet bound.
- `runner_call_input_manifest` schema version and media type constants were moved to `dayu/host/durable/schema.py` so RunInputBuilder and Engine ingest share one contract source.

## tests / pyright / diff-check results

- `source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`
  - Result: `155 passed in 1.14s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: clean

## README sync

- `dayu/host/README.md` now documents canonical limited-signal manifests for Engine-internal continuation when full Host source / projector material is unavailable.
- `tests/README.md` now documents coverage for continuation canonical limited-signal manifests and Tool Trace non-complete typed diagnostic projection.
- `dayu/engine/README.md` did not require a fix-specific update because the Engine-owned event boundary did not change in this gate.

## remaining risks

- Continuation manifests are intentionally limited-signal because Host ingest cannot recover the full Engine-internal rendered message list, per-message content digests, and source/projector mapping from the current Engine event contract without moving Host-owned refs into Engine or adding a broader production handoff. The canonical diagnostic makes that limitation explicit.
- Artifact-store fallback for manifest bodies remains outside this fix because composition-root artifact threshold wiring is outside the allowed file set; current continuation manifests are bounded summaries and do not inline large content.

## ready for re-review

yes
