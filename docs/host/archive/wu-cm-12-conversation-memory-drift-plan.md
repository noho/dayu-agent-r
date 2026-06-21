# WU-CM-12 Conversation Memory Drift Repair Plan

## 1. Goal / Motivation / Success Signal

Goal: repair implementation drift between the current Conversation Memory / Context Governance code and the updated Host design truth in `docs/host/design.md` chapter 24 Conversation Memory and chapter 25 Context Governance. The output of this gate is a code-generation-ready implementation plan only.

Motivation judgment: the motivation is real, but not every listed risk is still a live failure.

- Real drift: LLM-facing memory / compact / RunInput material still has private field-level caps and lossy summaries outside the single `MemoryProjectionPolicy` owner. Examples include `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200` in [compact_material.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compact_material.py:89), `_COMPACT_SUMMARY_MAX_CHARS = 1200` in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:163), `_vnext_compact_candidate_summary(... return text[:max_summary_chars])` in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:3200), and `_bounded_text(... return text[:char_cap])` in [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:2936).
- Real drift: protected recent floor is currently item/block based. `memory._limit_selected_recent_window` protects the last N user/assistant items rather than host_run_id turn groups in [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:1950), `compact_material._protected_recent_raw_block_ids` protects raw blocks in [compact_material.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compact_material.py:1496), and fallback selection slices raw blocks in [context_fallback.py](/Users/leo/workspace/dayu-agent-r/dayu/host/context_fallback.py:365).
- Real drift: tier 4/5 dispatch fallback exists, but tier 1-3 compact recovery fallback and section-aware degrade are not implemented as the design state machine. Dispatch jumps from failed compact attempt to `_append_compaction_failed_with_proactive_fallback(...)` in [dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:1337), which chooses dispatch/fail-closed recent-window fallback in [dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:1851).
- Partially closed risk: selected fallback block ids are already checked against the material view before rendering. `_fallback_context_messages` raises if a selected block id is missing in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:2710). The implementation still needs stronger tests around source refs and turn-group same-source selection/rendering.
- Closed residual: the two WU-CLI-ACTIVITY-01 public smoke tests currently pass locally:
  `pytest tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q` returned `2 passed`.

Success signal: after implementation, Conversation Memory uses a single typed Host policy view for all LLM-facing memory/material production, compact input / ordinary RunInput / fallback RunInput share selection and rendering semantics, tier 1-3 compact recovery and tier 4/5 dispatch fallback are covered by deterministic tests, selected block ids cannot disappear between selection and rendering, protected recent floor is host_run_id turn-group based, and the affected test set plus full pyright pass.

## 2. Design Document Alignment

The implementation source of truth is the updated `docs/host/design.md`.

- `docs/host/conversation-memory-material-budget-discussion.md` is rationale / handoff reference only.
- `docs/host/design.md` chapter 24 states that selected recent window is derived from `post_compact_delta_material`, protects recent turn groups where `turn_group_id = host_run_id`, and treats `memory_projection_policy` as the only owner for LLM-facing memory/material production in [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2813) and [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2817).
- It forbids LLM-facing field-level silent truncation / preview / summary in [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2866).
- It requires compact input, ordinary RunInput and fallback RunInput to share the same `assemble(...)` material semantics in [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2870).
- It defines Context Governance as a one-way consumer of EventLog-backed material, not a memory writer, in [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:3163) and [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:3165).
- It defines tier 1-3 compact recovery fallback and tier 4-5 dispatch fallback in [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:3193) and [design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:3261).
- The focused design re-review requires the plan to choose stable section-aware degrade ordering and tests for no text truncation / no new summary in [wu-cm-12-design-writeback-rereview-mimo-20260618.md](/Users/leo/workspace/dayu-agent-r/docs/reviews/wu-cm-12-design-writeback-rereview-mimo-20260618.md:33), [wu-cm-12-design-writeback-rereview-mimo-20260618.md](/Users/leo/workspace/dayu-agent-r/docs/reviews/wu-cm-12-design-writeback-rereview-mimo-20260618.md:92), and [wu-cm-12-design-writeback-rereview-mimo-20260618.md](/Users/leo/workspace/dayu-agent-r/docs/reviews/wu-cm-12-design-writeback-rereview-mimo-20260618.md:146).

## 3. Non-Goals / Scope Boundary

- Do not introduce semantic search, vector recall, prompt-conditioned retrieval or a long-term retrieval framework.
- Do not implement User Profile Memory or a Conversation Memory eval benchmark.
- Do not modify UI / log / diagnostic preview rules unless a code path proves they enter LLM-facing memory material.
- Do not modify raw tool output capture, download, conversion or ToolRuntime truncation policy.
- Do not add Host / Engine public API, durable schema, EventLog canonical semantics, Engine provider contract or cross-layer contract.
- Do not change `docs/host/design.md`, `docs/host/issues-implementation-control.md`, review artifacts, production code or tests in this plan gate.

## 4. First-Principles Judgment And Direct Code Evidence

The root cause is not missing long-term memory. The system already has EventLog-backed material builders, memory projection, compact artifacts and dispatch fallback. The drift is that multiple implementation helpers still act as independent LLM-facing material policy owners, and fallback recovery is only partially implemented.

Direct evidence:

- `MemoryProjectionPolicy` has the intended typed fields and validates fallback caps relative to normal selected window caps in [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:761) and [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:867). Service and ConfigLoader map the config into this typed policy in [host_assembly.py](/Users/leo/workspace/dayu-agent-r/dayu/service/host_assembly.py:1330) and [config_loader.py](/Users/leo/workspace/dayu-agent-r/dayu/runtime/config_loader.py:235).
- Despite that, memory projection truncates accepted compact fields with `_bounded_text`, including session summary and facts in [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:1711) and [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:1803). The helper silently returns `text[:char_cap]` in [memory.py](/Users/leo/workspace/dayu-agent-r/dayu/host/memory.py:2936).
- Compact material uses private caps for current input and evidence chunks in [compact_material.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compact_material.py:89). Evidence chunking is allowed only if provenance is explicit; current input silent truncation is not allowed.
- Ordinary RunInput still renders accepted compacted view as a summary/count string and silently cuts it in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:1475), [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:3160), and [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:3233). This is exactly the "summary 化" risk for LLM-facing material.
- Ordinary RunInput normalizes system envelope titles from local constants in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:163) and [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:2533). This is acceptable only if those constants become the single Host renderer truth and stop creating independent cap/title policy.
- `RunInputBuilder.build_material_blocks(...)` exposes a shared material block source in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:1952), but pre-dispatch compact uses `build_pre_dispatch_compact_material_view(...)` directly in [dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:1047). The plan must converge these paths through the same typed material/view semantics without making Context Governance depend on memory snapshot.
- `select_compact_segment(...)` already has a `selected_recent_window_turn_floor` parameter, but `_protected_recent_raw_block_ids` counts raw blocks, not host_run_id groups, in [compact_material.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compact_material.py:850) and [compact_material.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compact_material.py:1496).
- `build_recent_window_fallback_selection(...)` keeps current input, stable blocks and raw block floor, then appends reverse chronological raw blocks in [context_fallback.py](/Users/leo/workspace/dayu-agent-r/dayu/host/context_fallback.py:333). It uses `selected_recent_window_turn_floor` from `memory_projection_policy` in [dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:1967), but it does not use fallback item/char caps yet.
- Dispatch already wires active fallback provider into ordinary RunInput in [dispatch.py](/Users/leo/workspace/dayu-agent-r/dayu/host/dispatch.py:2898), and `run_input._fallback_context_messages` fail-closes on missing selected block ids in [run_input.py](/Users/leo/workspace/dayu-agent-r/dayu/host/run_input.py:2723).
- Tests cover existing fallback dispatch and current smoke behavior, but not turn-group floor or section-aware tier 1-3. Existing examples: fallback selection in [test_run_input_builder.py](/Users/leo/workspace/dayu-agent-r/tests/host/test_run_input_builder.py:817), fallback rendering in [test_run_input_builder.py](/Users/leo/workspace/dayu-agent-r/tests/host/test_run_input_builder.py:965), proactive fallback dispatch in [test_dispatch_scheduler.py](/Users/leo/workspace/dayu-agent-r/tests/host/test_dispatch_scheduler.py:4550), and reactive fallback dispatch in [test_dispatch_scheduler.py](/Users/leo/workspace/dayu-agent-r/tests/host/test_dispatch_scheduler.py:5045).

## 5. Affected Files / Modules For Implementation

Allowed implementation modules after this plan is accepted:

- `dayu/host/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/context_fallback.py`
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/compaction.py` only if an internal typed helper is needed for tier/degrade dataclasses.
- `dayu/service/host_assembly.py`, `dayu/runtime/config_loader.py`, `dayu/config/execution_profiles.json` only for policy mapping validation tests or if typed owner conversion proves incomplete. No schema field additions are expected.
- Affected tests under `tests/host/`: compact material, memory projection, run input builder, dispatch scheduler, public multiturn/tool smoke and compact public smoke.

## 6. Contract / Schema / State-Machine / Public Interface Changes

No public API, durable schema, EventLog canonical semantics, Engine contract or cross-layer contract change is approved by this plan.

Allowed state-machine change is internal Host dispatch behavior only:

- Existing `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, `CONTEXT_COMPACTED` and `CONTEXT_COMPACTION_FAILED` events remain the only facts.
- Tier 1-3 compact recovery fallback may run additional internal compactor calls using deterministic material variants, but accepted output still commits through existing `CONTEXT_COMPACTED`.
- Tier 4-5 dispatch fallback continues to use existing `CONTEXT_COMPACTION_FAILED` fallback fields and ordinary RunInput rendering.

Blocking user decision: stop if implementation proves a new public field, durable table, EventLog type, Engine message role or provider contract is required. Do not smuggle such state through metadata, extra payload or raw dict.

## 7. Implementation Decisions

1. Single material policy owner:
   `MemoryProjectionPolicy` remains the only Host policy owner for selected recent window caps, fallback selected window caps, protected floor, section caps and inline repair guard. Private renderer caps must be removed or converted into whole-item keep/drop / chunking with provenance / fail-closed behavior.

2. Shared material view:
   Keep EventLog as compact material truth. Introduce only internal typed helpers in Host if needed, for example `RunInputMaterialBlock.turn_group_id: str | None` and selector helpers. Compact input must not depend on memory snapshot as a precondition.

3. Turn group:
   `turn_group_id` is `host_run_id`. All material blocks created from a committed Host Run must carry the same `turn_group_id` for that Run. Current input anchor uses the current `run.run_id`. Stable compacted semantic blocks may have `turn_group_id=None`.

4. Protected recent floor:
   Protect the newest N turn groups, not newest N raw blocks. A protected group includes eligible user input, assistant final answer, accepted tool evidence and user-visible outcome material for that Host Run. If floor conflicts with cap, floor wins until hard threshold; if floor itself cannot fit, tier 5 / fail closed handles it.

5. Section-aware degrade:
   Tier 2 keeps semantic sections in this fixed section priority: evidence-backed facts, reference continuity, answer anchors, forward intents, session summary. Within a section, the sorting field/direction is fixed: first sort by the semantic item's maximum source EventLog sequence descending when every compared item has a source sequence; if a source sequence is absent, sort by original material order ascending, then stable block id ascending. The same helper/order must be reused by ordinary, compact and fallback paths. Dropping is whole-item/whole-section only. It must not truncate text, rewrite facts, rewrite summary, create a new summary, create new compacted view semantics or materialize memory.

6. Tiered fallback scope:
   Tier 1-3 are internal compact recovery fallback variants only when compactor and artifact root are configured and the Run state still permits compaction. Each tier submits at most one compactor call after the normal semantic repair path fails. Normal semantic repair path means the bounded whole-candidate repair attempts owned by Host Context Governance for the original immutable compaction request. The recovery loop must observe cancellation/stale-state before every tier attempt, after every proposal returns and immediately before commit. Proactive path uses a durable Run state observation token because no worker token exists before dispatch; reactive path reuses the run-local cancellation token from the Engine envelope. This keeps total extra work bounded by fixed tiers and avoids new policy fields.

7. Tier 4-5 dispatch fallback:
   Continue using current `CONTEXT_COMPACTION_FAILED` plus `fallback_action`. Apply fallback selected item/char caps from `MemoryProjectionPolicy`, not just context budget hard threshold. Rendering remains ordinary RunInput rendering with selected ids checked against the same material view.

## 8. Implementation Slices

### S1: Material Block And Policy Owner Convergence

Objective: make Host material blocks carry the data needed for shared selection and remove private LLM-facing material caps as policy owners.

Allowed files/modules:
`dayu/host/compact_material.py`, `dayu/host/memory.py`, `dayu/host/run_input.py`, focused tests in `tests/host/test_compact_material.py`, `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`.

Exact allowed changes:

- Add `turn_group_id: str | None` to `RunInputMaterialBlock` and all builders that create it.
- Populate `turn_group_id` from `RunRow.run_id` or row `run_id` for user input, assistant final answer, accepted tool evidence and current input blocks.
- Keep `turn_group_id=None` for stable accepted compacted semantic blocks unless their source Run is directly known.
- Remove or stop using `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` for LLM-facing current input. Current input is whole keep/drop/fail-closed.
- Keep evidence chunking only where chunk labels preserve parent provenance. Tests must assert chunk labels and parent refs exist.
- Replace `_bounded_text` silent truncation for LLM-facing compact-derived semantic fields with whole-item keep/drop at section cap time. If a single protected/floor item exceeds policy hard constraints and cannot be chunked with provenance, surface diagnostic/fail-closed through the caller rather than returning `text[:cap]`.
- When EventLog payload / artifact refs are unreadable, digest-mismatched, missing or otherwise corrupted while building LLM-facing material, do not synthesize partial material. Emit the existing structured diagnostic where the caller has a diagnostic path; otherwise fail closed. If a corrupted raw block is not required for floor/current-input correctness, whole-drop is allowed only with diagnostic evidence and only when the remaining selected material still satisfies floor invariants.

Functions/classes/types:
`RunInputMaterialBlock`, `run_input_material_block`, `build_pre_dispatch_compact_material_view`, `build_run_input_material_blocks`, `_selected_user_item`, `_selected_assistant_item`, `_selected_evidence_item`, `_session_summary_from_accepted_event`, `_facts_from_accepted_event`, `_bounded_text`.

Call paths/data flow:
EventLog/payload/artifact -> material block with `turn_group_id` -> selector -> compact pack / fallback renderer. No new public API.

Error handling/invariants:

- Missing `turn_group_id` is allowed only for stable semantic material.
- Durable payload / artifact corruption cannot become LLM-facing text. Corrupted required current input or protected floor material fails closed; corrupted optional material may be whole-dropped only with diagnostic evidence.
- LLM-facing text cannot be silently shortened.
- Whole item drop must emit existing memory budget diagnostic where applicable.
- Current input anchor cannot be dropped by ordinary selection; if it alone cannot fit, later fallback/fail-closed handles it.

Non-goals:
No tier 1-3 dispatch changes in this slice.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
- `source .venv/bin/activate && pyright dayu/host/compact_material.py dayu/host/memory.py dayu/host/run_input.py tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`

Completion signal:
Tests prove no LLM-facing compact/memory field returns a silent prefix string, material blocks carry expected `turn_group_id`, durable payload / artifact corruption is diagnosed or fail-closed, and existing compact material shape tests still pass.

Stop condition:
Stop if fixing silent truncation requires changing accepted compact output schema or EventLog payload schema.

### S2: Turn-Group Selected Recent Window And Fallback Selection

Objective: make selected recent window and fallback selected window protect Host admitted user Run groups rather than raw item counts.

Allowed files/modules:
`dayu/host/memory.py`, `dayu/host/compact_material.py`, `dayu/host/context_fallback.py`, `dayu/host/run_input.py`, tests in `tests/host/test_memory_projection.py`, `tests/host/test_compact_material.py`, `tests/host/test_run_input_builder.py`.

Exact allowed changes:

- Replace raw item floor logic with a shared internal helper that computes newest N non-null `turn_group_id` groups.
- Apply the helper in memory projection selected recent window, compact segment protection and fallback recent window selection.
- Apply `fallback_selected_recent_window_item_cap` and `fallback_selected_recent_window_char_cap` from `MemoryProjectionPolicy` in fallback selection. The context budget policy remains the hard-budget estimator; memory policy decides fallback selected window production.
- Fix the floor/cap/budget priority algorithm for fallback selection:
  1. Build the protected floor first from newest `selected_recent_window_turn_floor` eligible `turn_group_id` groups. This set is never reduced by fallback item cap or fallback char cap.
  2. Estimate the floor-only messages with the hard budget estimator. If floor-only exceeds hard threshold, do not trim the floor; route to tier 5 / fail closed according to dispatch state.
  3. Starting after the protected floor, append non-floor candidates in deterministic reverse material recency while both fallback caps allow the whole next block: selected item count must stay within `fallback_selected_recent_window_item_cap`, and selected character count must stay within `fallback_selected_recent_window_char_cap`. A candidate that would exceed either fallback cap is whole-block skipped and no later less-recent candidate may be used to evade ordering.
  4. Run the hard budget estimator after each whole-block append. If the append makes the selection exceed hard threshold, remove that entire appended block and stop appending. Do not prefix-truncate or partially keep the block.
  5. The final selected set is `floor + accepted appended blocks`. If no non-floor block can be appended, floor-only remains the fallback window unless step 2 routed to tier 5 / fail closed.
- Ensure protected group includes user, assistant, accepted evidence and current eligible run outcome material for the same `turn_group_id`.
- If an eligible raw turn block lacks `run_id` / `turn_group_id`, do not silently skip it from protected floor calculation. The implementation must either repair the source path so the block gets the correct `turn_group_id`, or emit a diagnostic and fail closed when the block is needed to satisfy the protected floor.

Functions/classes/types:
`_limit_selected_recent_window`, `select_compact_segment`, `_protected_recent_raw_block_ids` or replacement helper, `build_recent_window_fallback_selection`, `RecentWindowFallbackSelection`, `_raw_turn_count`.

Call paths/data flow:
MemoryProjectionPolicy -> shared turn-group selector -> selected ids -> material pack / fallback payload -> RunInput renderer.

State transitions:
No new EventLog types. Existing fallback payload `selected_block_ids` must refer to selected material blocks from the same frozen view.

Error handling/invariants:

- Floor wins over item/char caps.
- If floor set itself exceeds hard budget, fallback action becomes fail closed or tier 5 according to dispatch state.
- Fallback caps only limit non-floor appended candidates; they never demote floor material.
- Missing `turn_group_id` on eligible raw turn blocks is a source-path error, not a nullable fallback path.
- Durable payload / artifact corruption during selection is diagnosed and fail-closed when it prevents trustworthy selected material.
- Selected ids must be unique.

Non-goals:
Do not introduce retrieval or prompt-conditioned relevance ranking.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
- `source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/compact_material.py dayu/host/context_fallback.py dayu/host/run_input.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py`

Completion signal:
Tests create at least two Host Run groups with multiple blocks per group and prove the floor preserves all eligible blocks from the newest N groups, not merely N raw items. Additional tests cover floor/cap/budget priority, including floor-only over hard threshold, an appended block that exceeds fallback item/char caps, an appended block that exceeds hard budget and is whole-block rolled back, and missing `run_id` / missing `turn_group_id` on an eligible raw block producing source-path repair expectation or fail-closed diagnostic rather than silent removal.

Stop condition:
Stop if turn-group data cannot be derived from committed Host facts without a durable schema change.

### S3: Shared Rendering And Selected-Id Provenance Guards

Objective: ensure compact input, ordinary RunInput and fallback RunInput render from the same selected material view, and fail closed when selected ids / source refs drift.

Allowed files/modules:
`dayu/host/run_input.py`, `dayu/host/compact_material.py`, `dayu/host/context_fallback.py`, tests in `tests/host/test_run_input_builder.py`, `tests/host/test_compact_material.py`, `tests/host/test_dispatch_scheduler.py`.

Exact allowed changes:

- Extract internal material rendering helper(s) that accept `tuple[RunInputMaterialBlock, ...]` plus selected block ids and return Engine messages / compact pack inputs without reselecting.
- Strengthen `_fallback_context_messages` to check not only missing ids but also current input source ref, duplicate ids, selected source refs, fallback digest consistency when available, selected material view digest consistency when available, `turn_group_id` consistency for selected protected groups, and protected group consistency between selection payload and rendered material.
- Remove LLM-facing accepted compacted view summary/count rendering from ordinary RunInput. Render complete selected semantic items from memory projection sections, or whole-drop by policy before rendering.
- Keep one-system-message envelope behavior unchanged.

Functions/classes/types:
`RunInputBuilder.build`, `RunInputBuilder.build_material_blocks`, `_fallback_context_messages`, `_fallback_message_from_material_block`, `_compact_artifact_message_content`, `_vnext_compact_candidate_summary`, `_memory_messages`, `_normalize_ordinary_run_messages`.

Call paths/data flow:
Selected ids -> selected blocks from frozen material view -> role-preserving messages or system envelope section -> Engine request. No fallback renderer may read EventLog independently.

Error handling/invariants:

- Any selected id absent from material view raises `HostDurableError`.
- Any fallback current input mismatch raises `HostDurableError`.
- Any selected source refs mismatch, fallback digest / material view mismatch, selected duplicate id, mixed protected `turn_group_id`, or protected group consistency mismatch raises `HostDurableError`.
- Any LLM-facing internal governance ref in system envelope continues to raise.

Non-goals:
Do not change Engine message dataclasses or add `tool` role for historical evidence.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q`
- `source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py`

Completion signal:
Tests prove selected ids render all and only selected blocks, source refs are preserved, and accepted compacted semantic material is not rendered as lossy summary/count text. The test suite must include deliberately mismatched fixtures for selected id missing, current_input_ref mismatch, selected source_refs mismatch, fallback digest / material view mismatch, mixed turn_group_id and protected group consistency mismatch; every mismatch must fail closed with `HostDurableError`.

Stop condition:
Stop if correct rendering requires changing Engine message roles.

### S4: Tier 1-3 Compact Recovery Fallback

Objective: implement design tiers 1-3 as bounded internal compact recovery variants before existing tier 4/5 dispatch fallback.

Allowed files/modules:
`dayu/host/dispatch.py`, `dayu/host/compact_material.py`, optionally `dayu/host/compaction.py` for internal typed helper, tests in `tests/host/test_dispatch_scheduler.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_compact_material.py`.

Exact allowed changes:

- Add an internal deterministic recovery loop after normal `run_compaction_operation(...)` returns no accepted candidate and before `_append_compaction_failed_with_proactive_fallback(...)`.
- Tier 1: rebuild compact input with tighter fallback selected recent window using `fallback_selected_recent_window_*` caps.
- Tier 2: apply section-aware compacted view degrade with fixed section priority: evidence-backed facts, reference continuity, answer anchors, forward intents, session summary. Within each section, use the same sorting field/direction fixed in Decision 5: maximum source EventLog sequence descending when all compared items have source sequences; otherwise original material order ascending, then stable block id ascending.
- Tier 3: build delta-only compact input with empty latest accepted compacted view and bounded post-compact delta/current input.
- Each tier calls the same Host-owned compactor path with at most one attempt. Accepted output commits through existing `_append_compacted_event(...)`.
- Before each tier attempt, after its proposal returns and immediately before `_append_compacted_event(...)`, check durable Run state, input cursor, session state, execution identity and cancellation/stale-state. Stale, cancelled, session closed, execution replaced or cursor mismatch stops the recovery loop and must not write `CONTEXT_COMPACTED`.
- Proactive recovery uses a durable Run state observation token for those checks. Reactive recovery reuses the run-local cancellation token from the Engine envelope and still rechecks durable Run state/cursor before commit.
- If all tiers fail or are not applicable, fall through to existing tier 4/5 dispatch fallback.

Functions/classes/types:
`_execute_proactive_compaction`, `_prepare_compact_before_dispatch`, `_append_compaction_failed_with_proactive_fallback`, `select_compact_segment`, `build_compact_material_pack`, `CompactionRequest`.

State transitions:

- Original `CONTEXT_COMPACTION_REQUESTED` remains the operation anchor.
- Rejected tier proposals may be recorded through existing `CONTEXT_COMPACTION_ATTEMPT_REJECTED` if `run_compaction_operation` returns them.
- Accepted tier output writes existing `CONTEXT_COMPACTED`.
- All-tier failure writes existing `CONTEXT_COMPACTION_FAILED` once before dispatch fallback/fail-closed.

Error handling/invariants:

- Tier fallback must recheck Run status/input cursor before committing accepted output.
- Tier fallback must also recheck durable Run status, input cursor, session closed state, execution replacement and cancellation/stale-state before every tier attempt and immediately after every tier proposal returns.
- Stale/cancelled/session-closed/execution-replaced/cursor-mismatch proposals are discarded and never write `CONTEXT_COMPACTED`.
- No tier may create Session Semantic Memory directly.
- Section-aware degrade may only whole-drop items/sections. It may not truncate, rewrite, summarize or synthesize semantic items.
- Section-aware degrade tests must prove byte-exact keep/drop behavior: long semantic item text must either remain byte-exact equal to the original item or be absent as a whole item. Summary text must either remain exact-match with the original latest accepted compacted view or be whole-dropped. Prefix truncation, summary rewrite, new summary creation and new Session Semantic Memory are forbidden.
- Compactor missing/artifact root missing skips tier 1-3 and goes directly to tier 4/5.

Non-goals:
No new policy fields. No new EventLog type. No durable schema change.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q`
- `source .venv/bin/activate && pyright dayu/host/dispatch.py dayu/host/compact_material.py dayu/host/compaction.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py`

Completion signal:
Tests show tier 1/tier 2/tier 3 independent test scenarios and independent assertions:

- tier 1 independent test: normal repair fails, tighter fallback selected recent window succeeds, compact input uses `fallback_selected_recent_window_*` caps, and accepted output commits `CONTEXT_COMPACTED`.
- tier 2 independent test: tier 1 fails, section-aware degraded compacted view plus fallback caps succeeds, section priority and sorting field/direction are deterministic, forbidden actions are absent, and accepted output commits `CONTEXT_COMPACTED`.
- tier 3 independent test: tier 1 and tier 2 fail, delta-only compact input with empty latest accepted compacted view succeeds, and accepted output commits `CONTEXT_COMPACTED`.
- stale-state tests cover cancellation between tier 1 failure and tier 2 attempt, cancellation after tier proposal returns, and cursor/execution mismatch before commit; each case must not write `CONTEXT_COMPACTED`.
- tier 4/5 fallback dispatch writes `CONTEXT_COMPACTION_FAILED` without compact artifact after all tier 1-3 paths fail or are inapplicable.

Stop condition:
Stop if adding tier metadata to durable payload appears necessary for correctness. That would be a user design decision.

### S5: Public Smoke Reconciliation, Regression Matrix, README Decision

Objective: finalize tests, pyright, public smoke re-adjudication and README checks.

Allowed files/modules:
Tests under `tests/host/`, README files only if trigger checks prove the implemented code changes belong to their reader scope. No design/control artifact modifications unless the implementation gate explicitly allows them.

Exact allowed changes:

- Add/adjust focused tests for no silent truncation, turn-group floor, fallback selected caps, selected-id/source-ref same-source rendering, tier 1-3 recovery and tier 4/5 dispatch fallback.
- Include adversarial fixtures, not only happy paths: selected-id/source-ref provenance mismatch, missing `run_id` / missing `turn_group_id`, durable payload / artifact corruption, section-aware degrade long-text byte-exact keep/drop, and tier 1/tier 2/tier 3 independent trigger paths.
- Keep the two public smoke tests as passing regression evidence:
  `tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer`
  and
  `tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity`.
- Run README trigger checks:
  modifying `dayu/host/` requires checking `dayu/host/README.md`;
  modifying `tests/host/` requires checking `tests/README.md`;
  modifying `dayu/runtime/` or config mapping requires checking relevant config/test README duties.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`

Completion signal:
Affected tests and full pyright pass, README check is documented, and implementation report states changed files, validation, residual risk and public smoke reconciliation.

Stop condition:
Stop if public smoke regresses in a way that implies public Host API or Engine contract change.

## 9. Expected Assertions

The implementation tests must assert:

- No LLM-facing `display_text`, `text`, `claim_text`, `answer_text`, `response_text` or `summary_text` is silently truncated to a fixed prefix.
- Evidence chunking, if used, includes parent provenance and stable chunk labels.
- `selected_recent_window_turn_floor=N` protects the newest N `host_run_id` groups and all eligible blocks inside those groups.
- Missing `run_id` / missing `turn_group_id` on an eligible raw turn block cannot silently remove that block from protected floor; the test must observe source-path repair or diagnostic/fail-closed behavior.
- Durable EventLog payload / artifact corruption cannot produce untrusted LLM-facing material; required material corruption fails closed, and optional whole-drop paths include diagnostic evidence.
- `fallback_selected_recent_window_item_cap` and `fallback_selected_recent_window_char_cap` are enforced for fallback selected window production with fixed floor/cap/budget priority: floor first, floor-only hard budget check, append whole candidates under fallback caps, estimator check after each append, whole-block rollback on hard budget overflow, and tier 5 / fail closed if floor-only exceeds hard threshold.
- Selected block ids in fallback payload all exist in the rendering material view; deliberately mismatched fixtures for selected id missing, current_input_ref mismatch, selected source_refs mismatch, fallback digest / material view mismatch, mixed turn_group_id and protected group consistency mismatch all fail closed.
- Tier 1/tier 2/tier 3 independent test scenarios each have independent assertions for their own assemble semantics and accepted `CONTEXT_COMPACTED` path; tier 4-5 dispatch fallback does not write compact artifact, does not materialize memory snapshot and has `CONTEXT_COMPACTION_FAILED` diagnostic evidence.
- Tier 1-3 recovery loop cancellation/stale-state tests cover checks before tier attempt, after proposal return and before commit. Proactive path uses durable Run state observation token; reactive path reuses run-local cancellation token. Stale/cancelled/session-closed/execution-replaced/cursor-mismatch cases do not write `CONTEXT_COMPACTED`.
- Section-aware degrade never truncates semantic item text, rewrites summary/fact/anchor/intent/reference continuity, creates a new summary or creates Session Semantic Memory. Long-text fixtures must prove byte-exact keep/drop: retained item text equals original bytes, dropped items are absent as whole items, summary is exact-match or whole-drop, and prefix truncation is explicitly rejected.
- Tier 2 section-aware degrade uses the fixed sorting field/direction: maximum source EventLog sequence descending when available for every compared item; otherwise material order ascending, then stable block id ascending. Tests assert deterministic ordering under the same input cursor, material source cursor and policy.
- The two WU-CLI-ACTIVITY-01 residual public smokes pass and are treated as regression coverage.

## 10. Docs Decision

This implementation will modify `dayu/host/` and `tests/host/`, so the implementation gate must check `dayu/host/README.md` and `tests/README.md` according to repository rules before deciding whether to update them.

Expected README decision: update only if final code changes alter documented Host Conversation Memory / Context Governance behavior or test command responsibilities. Do not mechanically rewrite README for private helper names or internal slice mechanics.

## 11. Risks / Open Questions

- Tier 1-3 compact recovery extra compactor calls are bounded by fixed tiers, not by a new public policy. If reviewers require operator-configurable tier attempt counts, stop for design decision.
- Removing silent truncation may expose existing tests that expected prefix behavior. Fix the tests to assert whole-item drop/chunk/fail-closed semantics; do not preserve truncation in production.
- Section-aware degrade ordering relies on available source recency, but the sorting field/direction is fixed by this plan. If a semantic item lacks EventLog sequence, use material order ascending and stable block id ascending rather than inventing importance scoring.
- If any material path lacks `run_id` / `turn_group_id` for eligible raw turn blocks, implementation must trace the EventLog source and fix the projection path, or fail closed with diagnostic evidence when floor correctness depends on that block. Do not add nullable fallbacks that silently remove the block from protected floor.
- Durable payload / artifact corruption handling belongs to material construction and selection, not to LLM-facing rendering. Do not render partial text from corrupted refs to keep dispatch moving.
- Cancellation / stale-state in tier 1-3 recovery is a hard stop for `CONTEXT_COMPACTED`, not a repairable proposal failure.

## 12. Why This Is Not Over-Designed

The plan does not add retrieval, search, new public policy, new schema, new EventLog types or Engine changes. It reuses the existing Host-owned EventLog material builders, `MemoryProjectionPolicy`, `RunInputMaterialBlock`, `run_compaction_operation`, compact events and dispatch fallback payload. The only new structure is internal selection/rendering discipline needed to make current design truth executable and testable.

## 13. Completion Report Format For Implementation Agent

The implementation closeout must report:

- Changed files.
- Slice(s) completed.
- Direct evidence summary for policy owner, no silent truncation, turn-group floor, tier fallback and selected-id rendering.
- Validation commands and results.
- README decision.
- Public smoke reconciliation result for the two WU-CLI-ACTIVITY-01 residual tests.
- Residual risks / open questions, with owner or stop decision.

## 14. Plan Gate Validation

Plan artifact validation required in this gate:

- `git diff --check`
- `git diff --no-index --check /dev/null docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`
