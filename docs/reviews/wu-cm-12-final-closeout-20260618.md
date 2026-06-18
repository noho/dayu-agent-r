# WU-CM-12 Final Closeout

## Scope

WU-CM-12 repaired Conversation Memory design drift after writing the accepted semantics from `docs/host/conversation-memory-material-budget-discussion.md` back into `docs/host/design.md`. The implementation completed S1-S5 and aggregate deepreview.

Accepted implementation commits:

- Plan accepted: `8186f678`
- S1 material / policy owner convergence: `7f71c731`
- S2 turn-group fallback selection: `7b239aef`
- S3 selected-id provenance rendering guards: `3bab485c`
- S4 proactive tier 1-3 compact recovery: `c12e9952`
- S5 public smoke / residual reconciliation: `2c46631b`
- Aggregate deepreview closure: `a94a090d`

## Aggregate Review

- MiMo aggregate deepreview: `docs/reviews/deepreview-wu-cm-12-mimo-20260618.md`
- DS aggregate deepreview: `docs/reviews/deepreview-wu-cm-12-ds-20260618.md`
- Focused re-review: `docs/reviews/deepreview-wu-cm-12-rereview-mimo-20260618.md`; `docs/reviews/deepreview-wu-cm-12-rereview-ds-20260618.md`

Conclusion: PASS. DS low-severity doc findings were fixed and re-reviewed.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_public_compact_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py -q`
  - Aggregate result: `330 passed, 1 skipped`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: PASS

## Public Smoke Reconciliation

- `tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer`: PASS
- `tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity`: PASS
- `tests/host/test_public_compact_smoke.py`: PASS (`11 passed, 1 skipped`)

The WU-CLI-ACTIVITY-01 residual `WU-CLI-ACTIVITY-01-PR-R1` is closed by this evidence.

## Constant Audit

The following audit covers code constants that still appear in memory / compact / RunInput material paths and are not direct values in `dayu/config/execution_profiles.json` `memory_projection_policy`.

| Constant / helper | Location | Status | Reason |
|---|---|---|---|
| `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` | removed from `dayu/host/compact_material.py` | deleted | Former private current-input LLM-facing cap. Removed in S1; current input is no longer silently truncated before compact material construction. |
| `_CURRENT_INPUT_TRUNCATED_MARKER` | removed from `dayu/host/compact_material.py` | deleted | Former marker for current input prefix truncation. Removed with the private current-input cap. |
| `_COMPACT_SUMMARY_MAX_CHARS` | removed from `dayu/host/run_input.py` | deleted | Former ordinary RunInput compact-summary cap. S3 renders selected semantic material instead of summary/count preview text. |
| `_bounded_text` | removed from `dayu/host/memory.py` | deleted | Former field-level silent truncation helper for compact-derived semantic fields. S1/S5 use whole-item drop plus diagnostics. |
| `DEFAULT_SELECTED_RECENT_WINDOW_*`, `DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_*`, `DEFAULT_EVIDENCE_FACT_*`, `DEFAULT_SESSION_SUMMARY_CHAR_CAP` | `dayu/host/memory.py` | retained as typed policy defaults | These are defaults for `MemoryProjectionPolicy`, not a second runtime owner. Config profiles explicitly map the same fields through `memory_projection_policy`. |
| `MAX_VNEXT_*` output item/text constants | `dayu/host/compaction.py` | retained as schema/parser safety guards | These validate compactor input/output DTOs and reject invalid candidates. Host no longer uses them to silently truncate LLM-facing material. |
| `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS` | `dayu/host/compaction.py` | retained as schema constraint | Overlong current input is not truncated. S5 changed public compact smoke expectations so this path does not call the compactor or write compact artifacts; dispatch fallback handles the Run. |
| `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` | `dayu/host/compact_material.py` | retained as chunking-with-provenance guard | Evidence text is split into labeled chunks with parent provenance; it is not prefix-truncated. |
| `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS` | `dayu/host/compaction.py` | retained as schema guard for evidence chunks | Keeps each chunk within DTO constraints after provenance-preserving chunking. |
| `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` | `dayu/host/run_input.py` | deferred-with-owner | This caps the number of recent accepted tool-evidence rows read into RunInput material. It does not truncate text and is outside WU-CM-12's Conversation Memory policy-owner repair scope, but it remains a retrieval-volume constant not defined by `memory_projection_policy`. Future accepted-tool-evidence material governance should assign an owner before changing it. |
| `_SYSTEM_SECTION_*`, `_MEMORY_*_HEADER`, `_ACCEPTED_COMPACTED_VIEW_PREFIX`, `_RECENT_EVIDENCE_PREFIX`, `_ACCEPTED_TOOL_EVIDENCE_PREFIX` | `dayu/host/run_input.py` | retained as renderer labels | These are stable section labels / headings, not material production caps. |
| `_REASON_*`, `_PAYLOAD_FIELD_*`, event id prefixes, fallback status/action strings | Host modules | retained as diagnostics/schema labels | These are durable or diagnostic labels, not LLM-facing material quantity controls. |

## Residuals

- `WU-CLI-ACTIVITY-01-PR-R1`: closed.
- `WU-CM-12-S1-R1`: closed by `_facts_from_accepted_event` root-cause fix and regression test.
- `WU-CM-12-S4-R1`: deferred to `WU-CM-13 Reactive compact recovery follow-up`. WU-CM-13 is not active/default next work and must not enter implementation until assigned by user or GitHub Issue.
- Accepted tool evidence material retrieval volume (`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`): deferred as a separate governance follow-up if required; not blocking WU-CM-12 because no silent truncation or Conversation Memory policy conflict remains.

## README Decision

No README update is required. The changes are internal Host Conversation Memory / Context Governance implementation and tests. They do not change Host public API, CLI/UI user workflows, test directory responsibilities, or documented setup / run commands.

## Final Decision

WU-CM-12 is complete locally and ready for draft PR gate.
