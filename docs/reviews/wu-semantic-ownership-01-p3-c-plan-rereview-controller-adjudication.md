# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Re-Review Controller Adjudication

## Decision

- AgentMiMo verdict: PASS with one low-risk source-scan gap.
- AgentDS verdict: pass-with-risks with three new findings.
- Original `P3-C-PF-01` through `P3-C-PF-06`: accepted as closed.
- New gate decision: `second-plan-fix-required`.

The new observations are current-code findings, not implementation details that may be left implicit. All are accepted before the plan can be committed.

## New Required Fixes

| ID | Source | Decision | Required plan change |
|---|---|---|---|
| P3-C-RR-PF-01 | DS-01 | accepted | Add `compact_pipeline.py` to the concrete S2 contract change and remove the unused `messages` property from `CompactPipelineCompactArtifactView`. Verify the protocol still exposes exactly the provenance fields consumed by protected-raw-tail selection and that `CompactArtifactView` remains a structural subtype. |
| P3-C-RR-PF-02 | DS-02 | accepted | Explicitly delete the entire `build_run_input_material_blocks()` loop over `compact.messages`; do not wait for a source scan to discover it. State how compact provenance remains available without creating a material block. |
| P3-C-RR-PF-03 | DS-03 | accepted | Add an exact no-rename mapping table: `CompactEvidenceBlock.readable_tool_name <- material.tool_name`, `readable_query_text <- query_text`, `raw_result_text <- result_text`, `readable_source_text <- source_text`, and `EvidenceReadableItemVNext.response_text <- result_text`. `block.text` remains the shared four-field renderer output and is never used for these component fields. |
| P3-C-RR-PF-04 | MiMo source-scan gap | accepted | Add a zero-match scan covering `_previous_compacted_*_vnext` and the main `_previous_compacted_view_vnext`, so all removed string-round-trip helpers are an enforceable acceptance criterion. |
| P3-C-RR-PF-05 | controller direct verification of MiMo observation | accepted | Correct the false claim that `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` has a current proposal-budget owner. Direct `rg` proves it and adjacent `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE` / `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` are unused. Add `llm_compaction.py` to S2 only to delete these three dead constants; do not move, re-export, or preserve them as a second owner. Add zero-match scans. |

## Scope

- The three implementation slices remain unchanged.
- No production code or tests are changed in this plan gate.
- No compatibility path, schema migration, callback, adapter facade, or lazy import is authorized.
- `CompactPipelineCompactArtifactView` remains a narrow protocol for compact provenance consumed by the pipeline; it must not be removed or widened into a generic bag.
- P3-C-RR-PF-05 is a directly related semantic-owner correction, not a broad dead-code cleanup.

## Next Gate

AgentCodex performs a second plan fix for `P3-C-RR-PF-01` through `P3-C-RR-PF-05`, then AgentMiMo and AgentDS independently re-review the amended plan. The plan is not accepted until both return zero material findings.
