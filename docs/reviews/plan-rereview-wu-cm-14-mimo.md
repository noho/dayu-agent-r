# WU-CM-14 Plan Re-Review — AgentMiMo

## Re-Review Metadata

- **Reviewer**: AgentMiMo (focused re-review)
- **Date**: 2026-06-19
- **Plan artifact**: `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md`
- **Previous reviews**: `docs/reviews/plan-review-wu-cm-14-mimo.md`, `docs/reviews/plan-review-wu-cm-14-ds.md`
- **Verdict**: **PASS** — all accepted findings resolved

## Finding Closure Verification

### DS-H1: Underspecified transaction/EventLogStore access for ordinary RunInput raw tail rendering — **CLOSED**

**Previous review**: DS found that `RunInputBuilder` does not receive `HostTransaction` or `EventLogStore` directly, and the plan did not specify the provider contract.

**Current plan** (§4 item 2): The plan now specifies:
- Typed view: `_ProtectedRecentRawTailView(messages: tuple[AgentMessage, ...], material_blocks: tuple[RunInputMaterialBlock, ...], source_refs: tuple[str, ...])`
- Provider contract: `_ProtectedRecentRawTailProvider.load_protected_recent_raw_tail(snapshot, current_facts, memory, compact) -> _ProtectedRecentRawTailView`
- Noop variant: `_NoopProtectedRecentRawTailProvider` for tests / legacy assembly
- Durable variant: `_DurableProtectedRecentRawTailProvider` owns `HostTransactionRunner`, `EventLogStore`, and `MemoryProjectionPolicy`; mirrors `DurableAcceptedToolEvidenceMaterialProvider`; opens a read transaction and calls `build_pre_dispatch_compact_material_view(...)` inside that provider-managed transaction
- Injection: provider injected into `RunInputBuilder.__init__` as internal dependency with noop default

**Assessment**: Provider contract is fully specified: name, typed view, load signature, noop/durable variants, transaction ownership pattern (mirrors existing provider), and injection point. The plan explicitly states "do not make `RunInputBuilder.build()` read durable store directly." This is code-generation-ready.

**Verdict**: CLOSED.

---

### DS-H2 / MiMo F-04: Imprecise activation condition — **CLOSED**

**Previous review**: DS found the activation condition "for example when `compact.compact_artifact_ref is not None`" was imprecise, risking fallback double-rendering or old compact artifact mis-trigger. MiMo found the activation condition vague.

**Current plan** (§4 item 2): The plan now specifies:
- Definitive call-site activation condition: `compact.compact_artifact_ref is not None` AND `fallback is None`
- These conditions mean: current dispatch is an ordinary post-compaction dispatch, not current-input-only first dispatch and not fallback dispatch
- Definitive provider-side validation: compact artifact was loaded for current `run_id` before current Attempt start cursor; post-compact delta has eligible protected turn-group material
- Older compact artifact mis-trigger prevention: provider query boundary reads `CONTEXT_COMPACTED` with `run_id = current_facts.run.run_id` and `event_sequence < current_facts.attempt.started_event_sequence`
- Fallback branch remains exclusively `_fallback_context_messages(...)` and must not also call/render the raw-tail provider

**Assessment**: The activation condition is now definitive, not "for example." It explicitly prevents fallback double-rendering (`fallback is None` guard) and old compact artifact mis-trigger (provider query boundary with `run_id` and `event_sequence` check). Each edge case from DS-H2 is addressed.

**Verdict**: CLOSED.

---

### DS-H3 / MiMo F-01: Reactive compact-success regression — **CLOSED**

**Previous review**: DS found the test plan hedged on reactive E2E testing. MiMo found test 1 only covers the proactive path with no equivalent reactive compact-success test.

**Current plan** (§5): The plan now has:
- Test 2: "Reactive compact-success regression" — explicit committed test, not optional. Seeds the four-item scenario, simulates accepted reactive compact, builds recovery Attempt request through ordinary `RunInputBuilder.build()` with `fallback is None`, asserts same protected recent raw tail.
- Test 2 includes architectural argument: "reactive compact-success dispatch still creates a new Attempt for the same Run and reaches ordinary `RunInputBuilder.build()`; the distinguishing state is `RUN_STARTED(start_reason=recovery)`, while the message assembly owner is the same no-fallback ordinary branch."
- Test 2 adds fallback hedge: "If a full scheduler-level reactive E2E is not used, the focused test must explicitly construct the recovery Attempt state and call the same public/internal builder path used by dispatch, not only test helper functions."
- Test 8: "Reactive fallback is a committed focused test, not optional." Explicitly exercises `_frozen_reactive_material_blocks(...)`, `_reactive_fallback_decision(...)`, `build_recent_window_fallback_selection(...)`, and `_fallback_context_messages(...)`.
- Test 9: "Reactive frozen material assembly stop-condition regression" — seeds post-compact delta, asserts `_frozen_reactive_material_blocks(...)` produces protected turn-group blocks.

**Assessment**: The control document acceptance signal ("测试还必须覆盖 proactive 与 reactive compact 触发下的同义 preservation 结果") is now met: test 1 covers proactive compact-success, test 2 covers reactive compact-success through the same ordinary `build()` path, test 8 covers reactive fallback (committed, not optional), and test 9 covers reactive frozen material assembly. The architectural equivalence argument (recovery dispatch → same ordinary `build()`) is explicit.

**Verdict**: CLOSED.

---

### DS-M1: `test_compaction_operation.py` allowed file — **CLOSED**

**Previous review**: DS found `tests/host/test_compaction_operation.py` was listed as an allowed test file but had no corresponding required test.

**Current plan** (§5, §8): The current plan's allowed test files are:
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_memory_projection.py` only if memory assertions need adjustment

`test_compaction_operation.py` is no longer listed. The validation commands (§7) also no longer include it.

**Assessment**: The orphaned allowed file has been removed. If `compact_material.py` changes touch selection semantics that `test_compaction_operation.py` exercises, the implementation can add it back with a specific test requirement, but the plan no longer lists it without justification.

**Verdict**: CLOSED.

---

### DS-M2: Duplicate message risk between memory selected recent window and raw tail — **CLOSED**

**Previous review**: DS found no discussion of duplicate message risk when memory snapshot's selected recent window overlaps with EventLog-backed raw tail.

**Current plan** (§4 item 2, §5 Test 5): The plan now specifies:
- Dedup logic: "extend the internal `MemorySnapshotView` with defaulted private provenance fields sufficient for dedupe, such as selected recent source refs / content digests, without changing public API or durable schema"
- Drop rule: "drop a raw-tail block when its canonical event/evidence provenance or rendered content digest is already represented by memory selected recent window"
- Evidence-specific rule: "for accepted evidence, compare both evidence id and tool-result event ref when available, because compact material uses canonical evidence id while memory selected evidence may carry the event id"
- Test 5: "Duplicate prevention regression" — asserts each historical message appears exactly once; includes accepted evidence overlap
- Stop condition (§8): "overlapping memory selected recent window and EventLog-backed raw tail do not duplicate messages"

**Assessment**: The plan now has explicit dedup rules with provenance-based matching, a dedicated test, and a stop condition. The dedup approach is sound: it uses the existing provenance fields rather than introducing new ones, and it handles the evidence id / event id asymmetry.

**Verdict**: CLOSED.

---

### DS-M3 / MiMo F-03: Reactive frozen material repair stop condition — **CLOSED**

**Previous review**: DS found the reactive frozen material repair boundary between WU-CM-14 and WU-CM-13 was fuzzy. MiMo found the fix underspecified.

**Current plan** (§4 item 3): The plan now specifies:
- Concrete WU-CM-14 stop condition: "after repair, `_frozen_reactive_material_blocks(...)` must produce material blocks for the most recent `selected_recent_window_turn_floor` eligible turn groups from post-compact delta material, including committed user prompt, assistant final answer, and accepted readable tool evidence when those events exist"
- Focused test requirement: "The focused reactive material assembly test must prove those three block classes are present before `build_recent_window_fallback_selection(...)` runs; merely proving current input anchor exists is insufficient"
- WU-CM-13 boundary: "Keep deeper 'exactly freeze the original overflow ordinary material list' convergence as WU-CM-13-owned residual"
- §9 residual risk: "Reactive 'freeze exact overflow ordinary material list' is larger than WU-CM-14 and overlaps WU-CM-13. WU-CM-14 fixes only the protected recent raw tail floor by reusing EventLog-backed post-compact delta material and existing floor policy."

**Assessment**: The stop condition is now concrete and testable: produce material blocks for the most recent protected turn groups (user prompt, assistant final answer, accepted tool evidence). The boundary with WU-CM-13 is explicit: WU-CM-14 does the minimum for preservation, WU-CM-13 does full pipeline convergence.

**Verdict**: CLOSED.

---

### MiMo F-02: `USER_VISIBLE_RUN_STATE` material boundary — **NO CHANGE NEEDED**

**Previous review**: MiMo found `USER_VISIBLE_RUN_STATE` does not exist in the codebase; the plan's conditional clause was appropriate.

**Current plan** (§5 Test 6): Unchanged — still conditional: "if implementation identifies an already-defined `USER_VISIBLE_RUN_STATE` projection path, assert it is rendered as business-readable trace material without Host state refs."

**Assessment**: No change needed. The conditional wording is correct.

**Verdict**: NO CHANGE NEEDED.

---

### Scope Boundary Re-verification — **PASS**

| Constraint | Verified |
|---|---|
| No new WU-CM-14 专属 floor | ✅ Reuses `selected_recent_window_turn_floor` |
| No ordinal parser | ✅ Plan §4: "不做 prompt-pattern-specific retention" |
| No public API/schema/EventLog changes | ✅ §4: "No changes planned to public API, schema, EventLog event types, compact payload schema, memory kind, policy fields, prompt parser, or ordinal-specific rules" |
| No WU-CM-13 scope creep | ✅ §9 explicitly defers full pipeline convergence to WU-CM-13 |
| LLM-facing text constraint | ✅ §4 item 2, §5 Test 7 |
| Module-private provider/view | ✅ §4 item 2: "Add a module-private typed provider/view in `run_input.py`" |

## Residual Risks

All residual risks from the previous round remain non-blocking:

| ID | Risk | Severity | Owner |
|---|---|---|---|
| WU-CM-14-RR-1 | Reactive frozen material partial fix may not achieve full semantic equivalence; full convergence deferred to WU-CM-13 | MEDIUM | WU-CM-13 |
| WU-CM-14-RR-2 | `USER_VISIBLE_RUN_STATE` material kind may not exist | LOW | Implementation |
| WU-CM-14-RR-3 | Post-compaction activation condition is implementation detail | LOW | Implementation |
| DS-RR-2 | `build_pre_dispatch_compact_material_view` double-read during RunInput building | LOW | Acceptable (EventLog immutable) |
| DS-RR-4 | WU-CM-13 unification may revisit WU-CM-14 frozen material repair | LOW | WU-CM-13 preflight |

No new residual risks introduced by the plan amendments.

## Conclusion

**PASS** — all 6 accepted findings from the previous round are resolved:

| Finding | Status |
|---|---|
| DS-H1 (provider/transaction contract) | CLOSED — module-private provider/view with noop/durable variants, mirrors existing pattern |
| DS-H2 / MiMo F-04 (activation condition) | CLOSED — definitive condition with fallback guard and provider-side run_id/sequence check |
| DS-H3 / MiMo F-01 (reactive regression) | CLOSED — committed test 2 with architectural equivalence argument; test 8 reactive fallback committed |
| DS-M1 (test_compaction_operation.py) | CLOSED — removed from allowed files |
| DS-M2 (duplicate risk) | CLOSED — provenance-based dedup rules and dedicated test 5 |
| DS-M3 / MiMo F-03 (reactive stop condition) | CLOSED — concrete stop condition with three block classes and focused test requirement |

The plan is code-generation-ready. No remaining findings require Codex fix.
