# Code Review

## Scope

- Mode: current changes
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Base: `main`
- Output file: `docs/reviews/phase12-5-slice7-code-review-mimo-20260522.md`
- Included scope: 9 files — `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_compact_artifact_store.py`, `tests/host/test_compaction_contract.py`, `tests/host/test_memory_projection.py`, `tests/host/test_public_contracts.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_run_input_builder.py`
- Excluded scope: Engine, Fins, Service, UI, runtime production code
- Parallel review coverage: 4 subagents — old verified terms scan, production public contract verification, test meaning check, README sync accuracy

## Findings

未发现实质性问题。

### Verification Summary

**1. Old `verified_facts` / `tool_fact_refs` — fail-closed only, no stale public contract**

Production `dayu/` code contains old term occurrences only as rejection guards:

| Location | Pattern | Purpose |
|---|---|---|
| `context_events.py:100-102` | `_FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS`, `_FIELD_OLD_VERIFIED_FACT_REFS` | Constants for reject-on-sight |
| `context_events.py:335,943` | `if old_field in payload: raise ValueError(...)` | Fail-closed on old compact payload keys |
| `durable/memory.py:79,967-969` | `_ITEM_KIND_OLD_VERIFIED_FACT` + `raise HostDurableError(...)` | Fail-closed on old durable item kind |
| `memory.py:2736-2737` | `if "verified_facts" in mapping: raise ValueError(...)` | Fail-closed on old snapshot JSON key |

Test files exercise these rejection guards (`test_old_snapshot_verified_facts_key_fails_closed`, `test_old_durable_verified_fact_item_kind_fails_closed`, `test_old_max_verified_facts_key_fails_fast`, `test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs`). No production code path uses old names as active logic. `VerifiedFact` class and `max_verified_facts` field: zero matches in `dayu/`.

**2. Production public contracts — fully migrated**

| Old Name | New Canonical Name | Location |
|---|---|---|
| `max_verified_facts` | `max_evidence_backed_facts` | `memory.py:665` `MemoryProjectionPolicy` |
| `verified_facts` | `evidence_backed_facts` | `memory.py:825` `ConversationMemorySnapshot` |
| `tool_fact_refs` / `accepted_tool_fact_refs_retained` | `accepted_evidence_envelopes` / `accepted_evidence_refs_retained` | `compaction.py:222,1020` |
| `verified_fact_refs` | `evidence_backed_fact_refs` | `compaction.py:231` `CompactionRequest` |

**3. Tests — meaningful behavioral coverage, not snapshot-only**

| Test File | New/Modified Test | Behavior Proven | Trivial? |
|---|---|---|---|
| `test_compaction_contract.py` | `test_fact_candidates_can_reference_accepted_evidence_envelopes` | Fact candidates bind to accepted evidence envelopes; quality gate accepts | No |
| `test_memory_projection.py` | `test_compaction_confirmed_facts_do_not_drift_or_create_summary_fact` | Facts materialize with exact content; summary stays as continuity; no phantom summary-fact | No |
| `test_resolve_wait_command.py` | Renamed + rewritten | Tool results advance cursor but do NOT create `evidence_backed_facts` | No |
| `test_run_input_builder.py` | `test_gross_margin_followup_uses_post_compaction_evidence_backed_facts` | Full pipeline: event -> memory projection -> rendered LLM messages with post-compaction facts | No |
| `test_run_input_builder.py` | `test_minimum_preserve_resolves_second_factor_without_full_long_input` | Minimum preserve items render correctly; long input compacted away | No |
| `test_compact_artifact_store.py` | Field rename in existing test | Mechanical rename tracking domain model | N/A |
| `test_public_contracts.py` | `max_verified_facts` -> `max_evidence_backed_facts` | Mechanical rename tracking domain model | N/A |

**4. README sync — accurate, no stale terms**

- `dayu/config/README.md`: `max_evidence_backed_facts` field name and description match production code.
- `dayu/host/README.md`: `evidence_backed_facts` field name, compaction-gated extraction description, minimum preserve description, RunInputBuilder memory snapshot provider wiring — all accurate.
- `tests/README.md`: P12.5 memory semantic smoke section describes actual tests; field names match production; no stale `verified_facts` / `tool_fact_refs` remain in any README.
- Cross-cutting check: zero `verified_facts` / `tool_fact_refs` matches in all three README files.

**5. Architecture boundary — no forbidden scope**

All changes are within Host domain (`tests/host/`, `dayu/host/README.md`, `dayu/config/README.md`, `tests/README.md`). No imports into Engine, Fins, Service, or UI.

**6. Slice 7 smoke target — `evidence_backed_facts` success path proven**

`test_run_input_builder.py::test_gross_margin_followup_uses_post_compaction_evidence_backed_facts` proves the Slice 7 smoke target: a user asking a follow-up about gross margin correctly receives post-compaction `evidence_backed_facts` with `claim_text` and `evidence_refs` in the rendered LLM message context, and older raw turns are excluded.

## Open Questions

无。

## Residual Risk

- `test_compact_artifact_store.py` 和 `test_public_contracts.py` 的改动是机械重命名，不增加新覆盖。这两个文件已有充分的既有测试覆盖，风险可控。
- `test_run_input_builder.py` 的 `_compact_payload` helper 经过重构后参数化（`fact_candidates`、`minimum_preserve_items`），需确认所有既有调用点的默认行为未改变。验证结果：221 tests passed，无回归。
