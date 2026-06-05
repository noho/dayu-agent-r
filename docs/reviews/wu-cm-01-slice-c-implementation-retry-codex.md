# WU-CM-01 Slice C Implementation Retry - Codex

## Gate Status

- Gate: WU-CM-01 Slice C implementation gate
- Branch: `phaseflow/wu-cm-01`
- Status: blocker / implementation stopped
- Commits: no commit, no push, no PR
- Stash: not used

## Production Changes

- `dayu/host/memory.py` was partially replaced with a vNext memory contract draft:
  - introduced vNext-style `ConversationMemorySnapshot` fields: `session_summary_memory`, `evidence_fact_memory`, `answer_anchor_memory`, `forward_intent_memory`, `trace_memory`, `diagnostics`
  - introduced vNext-style `MemoryProjectionPolicy` fields following the latest gate prompt: `selected_recent_window_floor_turns`, `projection_max_repair_attempts`, `projection_max_rebuild_rows`, `projection_max_catchup_rows`, `max_memory_items_per_category`, `max_text_chars_per_memory_item`
  - added old snapshot / compact payload key fail-closed checks for `pinned_state`, `working_assumptions`, `conversation_continuity`, `episode_summary_candidate`, `pinned_state_patch_candidate`, `minimum_preserve_item_candidates`, `preserved_fact_refs`, `preservation_evidence`, and `evidence_backed_fact_candidates`

This production change is not a vertical closure. Direct consumers still compile against old fields and require coordinated migration before pyright can be clean.

## Test Changes

- None.

The direct consumer tests still assert old memory fields and old policy names. Updating tests without completing production consumers would only hide an incomplete contract migration.

## README Changes

- None.

README synchronization is blocked until the implementation is pyright-clean. Current stale README evidence is listed below.

## Direct Evidence

Old policy fields remain active in runtime config and service assembly:

- `dayu/runtime/config_loader.py:240-242` documents `max_evidence_backed_facts`, `max_working_assumptions`, and `recent_raw_turns_floor`.
- `dayu/runtime/config_loader.py:257-259` still defines those fields in the runtime config dataclass.
- `dayu/runtime/config_loader.py:1522-1524` still requires old config field names.
- `dayu/runtime/config_loader.py:1542-1544` still loads old field names.
- `dayu/config/execution_profiles.json:28-30`, `110-112`, `192-194`, and `274-276` still provide old `memory_projection_policy` keys.
- `dayu/service/host_assembly.py:999-1001` still maps old runtime policy fields into Host policy.

Old snapshot fields remain active in direct consumers:

- `dayu/host/durable/memory.py:648-652` still serializes `snapshot.evidence_backed_facts`, `snapshot.working_assumptions`, and `snapshot.conversation_continuity.items`.
- `dayu/host/compact_material.py:1454-1495` still renders `snapshot.pinned_state`, `snapshot.evidence_backed_facts`, and `snapshot.working_assumptions`.
- `dayu/host/run_input.py:1981-2018` still reads `snapshot.conversation_continuity.items` and `snapshot.evidence_backed_facts`.
- `dayu/host/run_input.py:2085-2161` still renders `snapshot.pinned_state` and `snapshot.working_assumptions`.
- `dayu/host/dispatch.py:3670` still reads `snapshot_row.snapshot.evidence_backed_facts`.

Old recent-window floor naming remains active in production:

- `dayu/host/compact_material.py:577-603` still accepts `recent_raw_turns_floor`.
- `dayu/host/context_fallback.py:123-153` still defines `recent_raw_turns_floor`.
- `dayu/host/dispatch.py:1851-1852` still reads `memory_projection_policy.recent_raw_turns_floor`.
- `dayu/host/engine_ingest.py:1279-1280` still reads `_memory_projection_policy.recent_raw_turns_floor`.

Tests remain old-contract oriented:

- `tests/host/test_memory_projection.py` still has many assertions on `snapshot.pinned_state`, `snapshot.working_assumptions`, `snapshot.conversation_continuity.items`, and `snapshot.evidence_backed_facts`.
- `tests/host/test_run_input_builder.py:1655-1657` still constructs old `MemoryProjectionPolicy` fields.
- `tests/host/test_compact_material.py:691-693` still constructs old `MemoryProjectionPolicy` fields.
- `tests/service/test_host_assembly.py:170` and `1006-1008` still assert/load old policy keys.
- `tests/runtime/test_config_loader.py:135-137`, `343`, `644`, and `654` still assert old config policy keys.

README still describes old concepts:

- `dayu/host/README.md:262-268` still documents stable layer, history pool, `evidence_backed_facts`, working assumptions, recent raw turns, episode summaries, and minimum preserve continuity.
- `dayu/config/README.md:87` still documents `max_evidence_backed_facts`.
- `tests/README.md:134` still describes old memory projection and RunInputBuilder coverage around `evidence_backed_facts`, working assumptions, minimum preserve, and recent raw continuity.

## Contract Conflict

There is a policy shape conflict that should be adjudicated before another implementation retry:

- The latest gate prompt requires `MemoryProjectionPolicyVNext` to use `selected_recent_window_floor_turns`, `projection_max_repair_attempts`, `projection_max_rebuild_rows`, `projection_max_catchup_rows`, `max_memory_items_per_category`, and `max_text_chars_per_memory_item`.
- `docs/host/design.md:95` requires `memory_projection_policy` to include `selected_recent_window_turn_floor` plus per-section item / char caps including `evidence_fact_item_cap`, `session_summary_char_cap`, `answer_anchor_item_cap`, `forward_intent_item_cap`, and `reference_continuity_item_cap`.
- `docs/host/wu-cm-01-conversation-memory-plan.md:389` repeats the design-source field list and names `selected_recent_window_turn_floor`, not `selected_recent_window_floor_turns`.
- `docs/host/wu-cm-01-conversation-memory-plan.md:360` explicitly says engine ingest should migrate to `selected_recent_window_turn_floor` or the slice's explicitly new field.

Because the prompt and design source disagree on exact policy names and budget shape, a pyright-clean implementation can be produced only after selecting the authoritative contract. Continuing by adding aliases or wrappers is explicitly forbidden by the gate.

## Validation

Executed:

```bash
python -m py_compile dayu/host/memory.py
```

Result: passed.

Not executed:

- Requested pytest batches
- `python -m pyright dayu/ tests/ utils/`

Reason: the vertical closure is knowingly incomplete; pyright would fail on direct consumers still referencing removed old fields. Running the full suite at this stage would produce expected noise rather than gate evidence.

## README Check

README trigger conditions are hit by `dayu/host`, `dayu/config`, `tests`, `dayu/service`, and `dayu/runtime` scope. README files were not updated because the implementation is blocked before a stable, verified code state exists.

Required after contract adjudication and implementation:

- `dayu/host/README.md`: replace old stable layer / working assumptions / minimum preserve descriptions with vNext memory sections.
- `dayu/config/README.md`: replace old memory policy field names with the selected vNext policy contract.
- `tests/README.md`: replace old memory test coverage descriptions with vNext snapshot / projection / prompt assembly coverage.
- `dayu/README.md`: check whether service assembly / runtime config boundary wording needs adjustment after the final mapping is implemented.

## Residual Risks

- Requires controller/design decision: exact `MemoryProjectionPolicyVNext` field shape and naming.
- Covered by Slice C after blocker resolution: durable memory rows, projection repair / rebuild / catch-up, compact material previous view, RunInputBuilder prompt assembly, dispatch precondition / fallback, service assembly, runtime config loader, execution profiles, direct consumer tests, README sync.
- Deferred by plan, not reopened here: full eval issue #80, User Profile issue #115, recall issue #39.
