# WU-CM-12-FIX-R1 Final Closeout

## Scope

- Work unit: `WU-CM-12-FIX-R1`
- PR: https://github.com/noho/dayu-agent-r/pull/150
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Result

`WU-CM-12-FIX-R1` is closed locally and pushed to draft PR #150.

The fix removes the over-designed legality checks that treated accepted EventLog-derived LLM input material as illegal only because it exceeded private Host DTO or retrieval constants. Current input, post-compact delta material, accepted tool evidence, compact material, and RunInput material now shrink only through deterministic selection, whole-item / whole-section keep-drop, provenance-preserving chunk semantics where explicitly implemented, or fail closed.

## Accepted Commits

- Accepted repair plan: `d904445e`
- Accepted slices:
  - Slice 1: `21ae992b`
  - Slice 2: `f468654c`
  - Slice 3: `cc30b304`
- Accepted aggregate deepreview fix: `a729ab18`
- Aggregate review control record: `5382afc7`
- Accepted PR review fix: `6b66732f`
- PR review control record: `430da835`

## Review Evidence

- Aggregate deepreview: `docs/reviews/code-review-20260618-193713.md`, `docs/reviews/code-review-20260618-195224.md`
- Aggregate fix: `docs/reviews/wu-cm-12-fix-r1-aggregate-fix-codex-20260618.md`
- Aggregate focused re-review: `docs/reviews/code-review-20260618-195017.md`, `docs/reviews/code-review-20260618-195038.md`
- PR review: `docs/reviews/pr-150-review-20260618-195915.md`, `docs/reviews/pr-150-review-20260618-200404.md`
- PR review fix: `docs/reviews/wu-cm-12-pr-review-fix-codex-20260618.md`
- PR review focused re-review: `docs/reviews/code-review-20260618-201316.md`, `docs/reviews/code-review-20260618-201451.md`

## Validation

- `pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py -q`: PASS, `127 passed`
- `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q`: PASS, `118 passed`
- Combined Host memory / compact / run-input validation: PASS, `240 passed`
- Aggregate fix validation: `pytest tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q`: PASS, `90 passed`
- PR review fix validation: `pytest tests/host/test_run_input_builder.py -q`: PASS, `80 passed`
- `pyright dayu/ tests/ utils/`: PASS, `0 errors`
- `git diff --check`: PASS
- Draft PR #150 status after push: open draft, no status checks reported by GitHub at closeout time.

## Behavior Closed

- `CurrentInputAnchorVNext.text` no longer has a private max-char legality guard.
- `EvidenceReadableItemVNext.response_text` no longer has a private max-char legality guard.
- Default evidence chunking has been removed from compact material production.
- Accepted tool evidence material no longer has the private `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` row cap.
- Ordinary accepted compacted view rendering no longer uses `_COMPACT_SUMMARY_MAX_CHARS` lossy summary projection.
- Memory projection no longer silently truncates accepted compact semantic fields with Host-local `_bounded_text`; over-policy items are whole-item dropped with diagnostics.
- PR review fix tightened fallback diagnostics and added boundary coverage for fallback selected-window caps.

## Code Constant Audit

Audit target: code constants still present in production code, not defined as fields in `dayu/config/execution_profiles.json` `memory_projection_policy`, and plausibly related to LLM-facing memory material, compact material, or compact output production.

| Constant / family | Location | Status | Explanation |
|---|---|---|---|
| `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` | production code | Deleted | No production match in `dayu/**/*.py`; current input anchor is not field-level truncated. |
| `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS` | production code | Deleted | No production match in `dayu/**/*.py`; vNext current input DTO only requires non-empty text. |
| `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` | production code | Deleted | No production match in `dayu/**/*.py`; default evidence chunking is removed. |
| `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS` | production code | Deleted | No production match in `dayu/**/*.py`; vNext evidence DTO only requires non-empty response text. |
| `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` | production code | Deleted | No production match in `dayu/**/*.py`; accepted evidence material is read through EventLog-backed material view and whole-block filters. |
| `_COMPACT_SUMMARY_MAX_CHARS` | production code | Deleted | No production match in `dayu/**/*.py`; ordinary RunInput no longer uses a lossy compact summary cap. |
| `max_evidence_blocks` | production code | Deleted | No production match in `dayu/**/*.py`; private accepted-evidence retrieval count parameter is removed. |
| `_evidence_chunks`, `_EvidenceChunk`, `evidence_chunk_label` | production code | Deleted | No production match in `dayu/**/*.py`; no dead default chunk helper remains. |
| `DEFAULT_MEMORY_*` policy defaults | `dayu/host/memory.py` | Retained as code fallback defaults for policy fields | These are not independent material production constants. They populate `MemoryProjectionPolicy` when no configured policy is supplied; the same policy fields are defined in `execution_profiles.json` `memory_projection_policy`. User review accepted this default fallback category. |
| `MAX_VNEXT_SESSION_SUMMARY_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | This bounds LLM-generated compact output candidate text at accept barrier. It does not truncate EventLog-derived input material or rendered compact input material. |
| `MAX_VNEXT_FACT_CLAIM_TEXT_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation, not source material selection or rendering. |
| `MAX_VNEXT_ANSWER_ANCHOR_TEXT_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_FORWARD_INTENT_TEXT_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_REFERENCE_CONTINUITY_TEXT_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_DIAGNOSTIC_TEXT_CHARS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_SOURCE_LABELS_PER_ITEM` | `dayu/host/compaction.py` | Retained as parser safety guard | Limits candidate provenance label count during output parsing; not a material production cap. |
| `MAX_VNEXT_FACT_ITEMS` | `dayu/host/compaction.py` | Retained as parser safety guard | Limits LLM-generated candidate item count at accept barrier; memory projection output caps still come from `MemoryProjectionPolicy`. |
| `MAX_VNEXT_ANSWER_ANCHOR_ITEMS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_FORWARD_INTENT_ITEMS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `MAX_VNEXT_DIAGNOSTIC_ITEMS` | `dayu/host/compaction.py` | Retained as parser safety guard | Same category: output candidate validation. |
| `_POST_COMPACT_BASE_MESSAGE_COUNT` | `dayu/host/compaction_operation.py`, `dayu/host/llm_compaction.py` | Retained but not material production | Fixed message-envelope count for compact budget estimation. It does not select, truncate, summarize, preview, or drop LLM-facing material. |
| `_MAX_SAFE_EXCEPTION_MESSAGE_CHARS` | `dayu/host/compaction_operation.py` | Retained but not material production | Diagnostic exception text safety bound for logs / repair diagnostics; not EventLog-derived memory or compact material. |
| `_DEFAULT_MEMORY_PROJECTION_CATCHUP_BATCH_SIZE` | `dayu/host/engine_ingest.py` | Retained but not LLM-facing material production | Projection maintenance batch size; not RunInput / compact material production. |
| `_LABEL_CHUNK_SEPARATOR`, `_FIRST_ORDINAL`, `_CURRENT_ANCHOR_ORDINAL` | `dayu/host/compact_material.py` | Retained but not production volume caps | Prompt-local label grammar and deterministic ordinal constants. They preserve provenance labels and do not control material amount. |

Conclusion: no remaining production code constant acts as a private field-length cap, lossy preview / summary cap, default evidence chunk cap, or accepted-evidence row cap for EventLog-derived LLM-facing material outside `memory_projection_policy`.

## Residual Risks

- `WU-CM-12-S4-R1`: reactive compact recovery tier 1-3 remains deferred to WU-CM-13 and is not a reason to retain private material guards.
- `WU-CM-12-PR-R1`: future cleanup should decide whether `dayu/host/compaction_evidence.py` is still needed after FIX-R1 or should be deleted / documented.
- `WU-CM-12-PR-R2`: future governance may document or align defensive-depth asymmetry between parser safety guards and memory projection caps.
- `WU-CM-12-PR-R3`: future diagnostics work may decide whether to persist recovery-tier rejected attempts individually.

## Notes For PR Description

- `_facts_from_accepted_event` also fixed an old bug: a single fact without evidence labels no longer drops all already-accepted facts; the invalid fact is skipped and diagnosed while valid facts are retained.
- Draft PR #150 remains draft; this closeout does not approve, mark ready, merge, request reviewers, or close external issues.
