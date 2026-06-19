# WU-CM-14 Plan Review — Adversarial Review (AgentDS)

## Review Metadata

| 项目 | 值 |
|---|---|
| review target | `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md` |
| work unit | WU-CM-14 Recent Final Answer Preservation for Ordinal Follow-ups |
| gate | plan review |
| reviewer | AgentDS |
| design sources | `docs/host/design.md:2528-2603, 3193-3320`, `docs/engine/design.md:487-501` |
| control source | `docs/host/issues-implementation-control.md:207, 243, 1689-1736, 1748-1807` |
| code evidence | `dayu/host/dispatch.py:1515-1530, 1853-1859, 2192-2224`, `dayu/host/engine_ingest.py:3795-3801, 3883-3918, 4009-4072`, `dayu/host/run_input.py:1759-1794, 2300-2333`, `dayu/host/compact_material.py:454-545, 885-960, 1658-1742, 2037-2078, 2179-2239, 2242-2327` |
| date | 2026-06-19 |

## Executive Summary

**Verdict: CONDITIONAL PASS with 3 HIGH findings that must be addressed before code generation.**

The plan correctly identifies three root causes with direct code evidence, maps them to minimal implementation changes within WU-CM-14 scope, and respects all non-goals (no new floor, no ordinal parser, no prompt-pattern-specific retention, no public API/schema changes). No CRITICAL (blocking) findings.

The 3 HIGH findings concern: (H1) underspecified transaction/EventLogStore access for the new RunInput raw tail rendering, (H2) imprecise activation condition for ordinary RunInput path, and (H3) test plan reactive coverage not meeting the control document's "同义 preservation" acceptance signal. All are resolvable with plan amendments, not redesign.

## Code Evidence Verification

All 13 code claims were independently verified against the current working tree. Results:

| Plan Line | Claim | Verified | Notes |
|---|---|---|---|
| 24-27 | `build_pre_dispatch_compact_material_view` reads from EventLog, delta sources `USER_INPUT_ACCEPTED`/`RUN_SUCCEEDED`/`TOOL_RESULT_ACCEPTED`, maps to turn-group material blocks, maps evidence with readable tool name/query/source text | ✅ | `compact_material.py:454-499, 2037-2078, 2179-2239, 2242-2327` |
| 28 | `_protected_recent_turn_group_block_ids` exists, eligible blocks include user/assistant/evidence | ✅ | `compact_material.py:1658-1742`; `is_turn_group_material_block` at 1731-1742 confirms user/assistant/evidence kinds |
| 29 | Ordinary path with `fallback is None` only uses `memory.messages + compact.messages + continuity.messages` | ✅ | `run_input.py:1789-1794` — no EventLog-backed post-compact delta |
| 30 | `_memory_selected_recent_window_messages` renders from memory snapshot, not EventLog-backed material | ✅ | `run_input.py:2300-2333` — reads `SelectedRecentWindowItem` from memory projection |
| 31 | Fallback renderer can render selected material blocks as Engine messages, skips current input anchor | ✅ | `run_input.py:2650-2859` `_fallback_context_messages` |
| 32 | Proactive compact recovery tier passes floor | ✅ | `dispatch.py:1515-1530` passes `memory_policy.selected_recent_window_turn_floor` |
| 32 | Normal proactive compact selection does NOT pass floor | ✅ | `dispatch.py:1853-1859` — `selected_recent_window_turn_floor` defaults to 0 |
| 33 | Proactive dispatch fallback passes floor | ✅ | `dispatch.py:2220-2222` passes `self._local_execution.memory_projection_policy.selected_recent_window_turn_floor` |
| 34 | Reactive root compact selection does NOT pass floor | ✅ | `engine_ingest.py:3795-3801` — `selected_recent_window_turn_floor` defaults to 0 |
| 35 | Reactive frozen material assembly uses empty memory/compact/continuity | ✅ | `engine_ingest.py:4058-4072` — `MemorySnapshotView(messages=())`, `CompactArtifactView(messages=())`, `SessionContinuityView(messages=())` |
| 36 | Reactive fallback selection passes floor from `pending.selected_recent_window_turn_floor` | ✅ | `engine_ingest.py:3906` |

All code evidence is consistent with the plan's claims. No fabrication or misattribution found.

## Findings

### HIGH Severity

---

#### H1: Underspecified transaction/EventLogStore access for ordinary RunInput raw tail rendering

**Location:** Plan Section 4, Implementation Outline point 2.

**Evidence:** The plan proposes using `build_pre_dispatch_compact_material_view(...)` as the source for protected recent raw tail. This function requires a `HostTransaction` and `EventLogStore`:

```python
# compact_material.py:454-460
def build_pre_dispatch_compact_material_view(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_display_text: str,
) -> PreDispatchCompactMaterialView:
```

`RunInputBuilder` (run_input.py:1700-1757) receives typed providers but does NOT receive a `HostTransaction` or `EventLogStore` directly. During `build()`, providers return typed views without exposing their internal transaction management. The plan does not specify:

1. Whether to introduce a new provider (e.g., `ProtectedRecentRawTailProvider`) with its own transaction management, or to reuse an existing provider.
2. If reusing an existing provider, which one — `CompactArtifactProvider` is closest semantically but its current contract returns `CompactArtifactView`, not material blocks.
3. If adding a new provider, its exact contract signature and how it participates in the existing provider assembly.

**Risk:** The implementation agent may either (a) bypass the provider pattern and access `EventLogStore` directly in `run_input.py`, breaking the typed provider boundary, or (b) make ad-hoc architectural decisions that should be in the plan.

**Recommendation:** Add to the plan: (a) the name and contract of the new provider or the specific existing provider to extend, (b) how it obtains a transaction (likely through the same pattern as existing providers — constructing `EventLogStore()` and reading within a provider-managed transaction scope), and (c) where in `build()` the new material gets injected into `bounded_context_messages`.

**Suggested adjudication:** Accepted — address in plan before implementation.

---

#### H2: Imprecise activation condition for ordinary RunInput raw tail rendering

**Location:** Plan Section 4, Implementation Outline point 2: "Activation condition should be post-compaction ordinary dispatch, for example when `CompactArtifactView.compact_artifact_ref is not None` for the current Run / Attempt."

**Evidence:** The `CompactArtifactView.compact_artifact_ref` is `str | None` (run_input.py:397). It is `None` only in "Phase 5 noop" (no compact has occurred). It is non-`None` when a compact artifact exists. However, the plan does not enumerate the edge cases:

1. **Compact attempted but failed (`CONTEXT_COMPACTION_FAILED`)**: Does `compact_artifact_ref` remain from a prior successful compact, or is it `None` for the current Run? If a prior compact artifact exists but the current Run is in a fallback path (no compact), the condition would incorrectly activate raw tail rendering in the fallback path, potentially duplicating the fallback's own floor rendering.
2. **Tier 4/5 fallback path**: The fallback path already has its own material selection with floor (via `build_recent_window_fallback_selection`). If the new raw tail rendering also activates in the fallback path, there could be double-rendering.
3. **First Run (no prior compact)**: `compact_artifact_ref` is `None`, correctly skipping raw tail rendering.

**Risk:** The activation condition as stated could cause the raw tail rendering to fire in fallback paths where it's redundant, or miss cases where compaction was attempted but produced no accepted artifact.

**Recommendation:** Refine the activation condition to explicitly enumerate: (a) `compact_artifact_ref is not None` AND (b) `fallback is None` (not in tier 4/5 dispatch fallback), AND (c) the protected recent raw tail material is not already covered by the memory snapshot's selected recent window items. Add focused tests for each boundary case.

**Suggested adjudication:** Accepted — refine in plan before implementation.

---

#### H3: Test plan reactive coverage doesn't meet control document acceptance signal

**Location:** Plan Section 5, Required Test 6; Control Document line 1806.

**Evidence:** The control document requires:

> 测试还必须覆盖 proactive 与 reactive compact 触发下的同义 preservation 结果，除非 plan gate 明确证明某一路径不会经过该 preservation owner。

The plan's test 6 says:

> "If a full scheduler-level reactive test is too heavy, add a focused test around the frozen reactive material assembly plus `build_recent_window_fallback_selection(...)`, but the stop condition must still prove Engine-bound messages can render the selected raw tail."

This is a conditional that hedges on the control document's acceptance signal. The plan does not:
1. Provide a concrete argument (with code evidence) that the focused test is semantically equivalent to a full E2E reactive test.
2. Explain why the reactive compact-SUCCESS path (where compact succeeds and recovery dispatch goes through ordinary RunInput) would be covered by test 3, even though it is architecturally the same ordinary RunInput path.
3. Commit to an E2E reactive test if the focused test cannot prove equivalence.

**Mitigating factor:** The reactive compact-success path reuses the same ordinary RunInput `build()` method after recovery dispatch, so test 3 (ordinary RunInput raw tail boundary regression) would cover it. The reactive compact-failure path uses `_reactive_fallback_decision` → `build_recent_window_fallback_selection`, which is what the focused test would cover. If the plan explicitly states this architectural argument, the test coverage may be sufficient.

**Recommendation:** Amend the test plan to either: (a) explicitly argue that test 3 covers reactive compact-success (since recovery dispatch goes through the same ordinary `build()`), and upgrade test 6 from "focused test if too heavy" to a committed focused test with concrete assertions, OR (b) commit to a full scheduler-level reactive E2E test.

**Suggested adjudication:** Accepted — refine in plan before implementation.

---

### MEDIUM Severity

---

#### M1: Allowed test file `tests/host/test_compaction_operation.py` has no corresponding required test

**Location:** Plan Section 5 (allowed test files) vs. required tests 1-7.

**Evidence:** `tests/host/test_compaction_operation.py` is listed as an allowed test file but none of the 7 required tests explicitly targets it. Compare with `tests/host/test_run_input_builder.py` which is listed AND targeted by tests 1, 3. Either the file should be removed from the allowed list, or a specific test requirement should be added (e.g., "verify compaction operation still correctly handles the protected floor exclusion reason in its quality gate").

**Recommendation:** Either remove the file from allowed test files or add a specific test requirement referencing it. Given that `compact_material.py` changes may touch selection semantics that `test_compaction_operation.py` exercises, adding a brief regression check is the safer choice.

**Suggested adjudication:** Accepted — clean up before implementation.

---

#### M2: Plan doesn't discuss duplicate message risk between memory snapshot selected recent window and new raw tail rendering

**Location:** Plan Section 4, Implementation Outline point 2.

**Evidence:** The ordinary RunInput path currently concatenates `memory.messages + compact.messages + continuity.messages` (run_input.py:1790-1794). The memory snapshot may already contain a selected recent window rendered by `_memory_selected_recent_window_messages` (run_input.py:2300-2333), which includes user/assistant messages from the memory projection's `SelectedRecentWindowItem` entries. When the new raw tail rendering also produces user/assistant messages from EventLog-backed post-compact delta material for the same turn groups, there could be duplicate (or near-duplicate) messages.

The plan's test 7 (current input anchor regression) covers the specific case of current input duplication, but does not cover historical turn duplication between memory snapshot and raw tail.

**Risk:** The implementation could produce Engine messages with duplicate assistant final answer text, bloating context and confusing the model.

**Recommendation:** Either (a) add dedup logic based on `turn_group_id` / `event_id` between memory snapshot selected recent window and protected recent raw tail, or (b) if the memory snapshot's selected recent window is capped/empty post-compaction, explicitly argue that duplication is architecturally impossible.

**Suggested adjudication:** Accepted — address in plan or implementation with explicit dedup rule.

---

#### M3: Reactive frozen material repair boundary between WU-CM-14 and WU-CM-13 is fuzzy

**Location:** Plan Section 4, Implementation Outline point 3.

**Evidence:** The plan says "Keep deeper 'exactly freeze the original overflow ordinary material list' convergence as WU-CM-13-owned residual if broader material unification is needed; WU-CM-14 must still ensure protected recent raw tail semantics do not drift." This correctly respects the WU-CM-13 boundary but doesn't provide a concrete stop condition for what "enough for WU-CM-14" means in the reactive path.

The control document (line 1756) requires WU-CM-14 preservation to "落在 proactive / reactive 共享的代码路径上." The plan's implementation outline point 3 says to reuse `build_pre_dispatch_compact_material_view(...)` — which IS a shared code path. But the concrete integration point in `_frozen_reactive_material_blocks` is not specified.

**Recommendation:** Add a concrete stop condition for the reactive frozen material repair: e.g., "After the repair, `_frozen_reactive_material_blocks(...)` must produce material blocks that include post-compact delta turn-group material (user prompt, assistant final answer, accepted tool evidence) for the most recent `selected_recent_window_turn_floor` turn groups, as verified by a focused unit test."

**Suggested adjudication:** Accepted — tighten in plan before implementation.

---

### LOW Severity

---

#### L1: `build_pre_dispatch_compact_material_view` double-read concern not addressed

**Location:** Plan Section 4, Implementation Outline point 2.

**Observation:** The plan proposes calling `build_pre_dispatch_compact_material_view(...)` during RunInput building. This function is already called during pre-dispatch compact material construction (in dispatch.py before compaction). Calling it again during RunInput building for the same Run would result in a second EventLog read of the same post-compact delta. While this is idempotent (EventLog is immutable), it's worth noting in the plan as acceptable overhead or suggesting memoization if the material view is already available from the compact path.

**Recommendation:** Note in the plan that the double-read is acceptable (EventLog immutability guarantees consistency) or wire the already-constructed `PreDispatchCompactMaterialView` from the compact path to the RunInput builder if the additional read is a concern.

---

#### L2: Implementation outline point 2 "for example when" language

**Location:** Plan Section 4, Implementation Outline point 2.

**Observation:** The activation condition is stated as "for example when `CompactArtifactView.compact_artifact_ref is not None`." The "for example" suggests this is one possible condition, not the definitive one. For code-generation readiness, the condition should be definitive.

**Recommendation:** Replace "for example when" with the definitive condition, after addressing H2.

---

#### L3: Section 9 residual risk could be more specific

**Location:** Plan Section 9, Blocking Questions.

**Observation:** The residual risk statement is qualitatively correct but doesn't enumerate what specific reactive behaviors are deferred to WU-CM-13 vs. fixed in WU-CM-14. Adding a brief bullet list would improve handoff clarity.

---

## Scope Boundary Verification

### ✅ Respected boundaries

| Constraint | Verified |
|---|---|
| No new WU-CM-14专属 floor | ✅ Plan explicitly reuses `selected_recent_window_turn_floor` |
| No ordinal parser | ✅ Plan Section 4 explicitly says "不做 prompt-pattern-specific retention" |
| No prompt-pattern-specific retention | ✅ Same as above |
| No public API changes | ✅ Section 4: "No changes planned to public API, schema, EventLog event types" |
| No schema changes | ✅ Same as above |
| No EventLog event type changes | ✅ Same as above |
| No memory kind changes | ✅ Same as above |
| No policy field changes | ✅ Plan only passes existing `selected_recent_window_turn_floor` |
| LLM-facing text constraint compliance | ✅ Test 5 covers negative assertions for bare tool requests, internal refs |
| No WU-CM-13 scope creep | ✅ Plan explicitly defers broader pipeline convergence to WU-CM-13 |

### ⚠️ Boundary risks

| Risk | Severity | Mitigation |
|---|---|---|
| New internal provider/view in `run_input.py` could be misperceived as a new public provider contract | LOW | Plan says "internal typed provider/view" — ensure implementation keeps it module-private |
| `compact_material.py` changes under "only if an existing private helper must be reused or narrowly exposed through `__all__`" | LOW | Gate any `__all__` exposure with explicit justification in implementation |

## Allowed Files Assessment

| File | Justification | Assessment |
|---|---|---|
| `dayu/host/run_input.py` | Ordinary RunInput raw tail rendering | ✅ Correct — this is where the ordinary path gap is |
| `dayu/host/dispatch.py` | Normal proactive compact selection floor pass | ✅ Correct — the two-line fix site |
| `dayu/host/engine_ingest.py` | Reactive root compact selection floor pass + frozen material repair | ✅ Correct — the reactive gap sites |
| `dayu/host/compact_material.py` | Only for narrow helper reuse | ⚠️ Borderline — `_protected_recent_turn_group_block_ids` and `protected_recent_turn_group_ids_for_material_blocks` are already accessible; `build_pre_dispatch_compact_material_view` is already importable. No new exposure should be needed. The "only if" guard is appropriate. |

The allowed files are neither too broad nor too narrow. The `compact_material.py` inclusion is appropriately guarded.

## Test Plan Assessment

### Strengths

1. **Test 1 (E2E proactive regression)**: The "four detailed numbered items → '详细解释第三条' → compact → verify" scenario directly tests the user-facing symptom. This is the right smoke test.

2. **Test 2 (compact selection floor regression)**: Verifying that normal proactive compact passes floor and excludes protected blocks addresses root cause #1.

3. **Test 5 (negative LLM-facing boundary)**: Explicit assertions that bare tool requests, tool_call_id, event_id, payload_ref, digest, cursor, and Host governance state don't enter Engine messages. This directly enforces the LLM-facing text constraints from AGENTS.md and design.md.

4. **Test 7 (current input anchor regression)**: Prevents the most common implementation mistake (treating current input as historical material).

### Gaps

1. **Reactive E2E coverage**: As noted in H3, the test plan hedges on reactive E2E testing.

2. **Duplicate message risk**: As noted in M2, no test covers the scenario where memory snapshot selected recent window overlaps with EventLog-backed raw tail.

3. **Test 4 eligible material boundary**: The "user-visible outcome material" concept is not concretely defined. What specific EventLog event types constitute "user-visible outcome material"? Is it `RUN_SUCCEEDED` final answer only, or does it include `RUN_FAILED` diagnostics, `RUN_CANCELLED` reason, etc.?

4. **No explicit tie-breaking test**: When `selected_recent_window_turn_floor > 0` but the eligible turn groups are fewer than the floor (e.g., first Run of a session), what happens? The plan and tests don't cover degenerate floor cases.

### Coverage distribution

| Test | Root Cause Covered | Path Covered |
|---|---|---|
| Test 1 (E2E) | All three | Proactive compact-success → ordinary RunInput |
| Test 2 (selection floor) | #1 | Proactive normal compact selection |
| Test 3 (ordinary RunInput) | #2 | Post-compaction ordinary RunInput |
| Test 4 (eligible boundary) | #2 | Material boundary |
| Test 5 (negative LLM) | #2 | LLM-facing constraint |
| Test 6 (fallback) | #3 | Proactive fallback + reactive fallback |
| Test 7 (current anchor) | #2 | Current input handling |

Gap: Reactive compact-SUCCESS → recovery ordinary RunInput is architecturally covered by test 3 (same `build()` method) but not explicitly argued. Reactive root compact selection floor pass (root cause #1 for reactive) is not directly tested — test 2 covers proactive selection but not the reactive `_reactive_compaction_request` call site.

## Design Source Alignment

### ✅ Aligned

- Plan's root cause analysis correctly maps to design's `assemble(...)` semantics (design.md:3194-3259): tier 0 normal must use `protected_recent_floor_policy`, which the current code doesn't feed properly.
- Plan's material boundary (history user prompt, assistant final answer, accepted readable tool evidence) matches design's eligible material block types (design.md:3296-3300).
- Plan's "never render current input anchor as history" matches design's `current_input_anchor` semantics (design.md:3297).
- Plan's LLM-facing constraint (no tool_call_id, event_id, payload_ref, digest, cursor) matches design's internal ref replacement table (design.md:2605-2616).

### ⚠️ Partial alignment

- Design.md:3288 says "selection 的候选集合是 `post_compact_delta_material`，不从 `latest_accepted_compacted_view` 中重新选择 raw recent window." The plan's implementation outline point 2 correctly uses `build_pre_dispatch_compact_material_view` (which constructs post-compact delta). However, the plan doesn't explicitly state that the raw tail rendering must also respect this constraint — it should not pull raw turns from the compacted view.

## README Trigger Judgment Verification

The plan's Section 6 correctly follows AGENTS.md README 触发规则:

- Plan gate does not modify code, so README updates are not triggered during plan gate. ✅
- Future implementation touches `dayu/host` → check `dayu/host/README.md` constraints. ✅
- Future implementation touches `tests` → check `tests/README.md` constraints. ✅
- The plan correctly identifies that `dayu/host/README.md` and `tests/README.md` should be checked per their own Agent update constraints, rather than mechanically updated. ✅
- Root README is correctly excluded: no user-facing CLI/Web/WeChat/install/command changes. ✅

## Residual Risks

| ID | Risk | Severity | Owner |
|---|---|---|---|
| RR-1 | Reactive compact-success path floor preservation depends on the same ordinary RunInput path as proactive; if the reactive recovery dispatch bypasses the ordinary `build()` method, the fix is incomplete | MEDIUM | Implementation verification |
| RR-2 | `build_pre_dispatch_compact_material_view` double-read during RunInput building adds latency to dispatch hot path | LOW | Performance monitoring |
| RR-3 | If `selected_recent_window_turn_floor` is 0 in some policy configurations, the entire fix is a no-op — this is correct behavior but should be verified | LOW | Test coverage |
| RR-4 | Reactive "freeze exact overflow ordinary material list" (deferred to WU-CM-13) may require revisiting the WU-CM-14 frozen material repair if the WU-CM-13 unification changes the material source | LOW | WU-CM-13 preflight |

## Validation

```bash
git diff --check -- docs/reviews/plan-review-wu-cm-14-ds.md
```

## Conclusion

**CONDITIONAL PASS.** The plan is well-grounded in code evidence, correctly identifies three root causes, and respects all scope boundaries and non-goals. The 3 HIGH findings (H1: underspecified provider/transaction access, H2: imprecise activation condition, H3: test reactive coverage gap) must be addressed in the plan before entering implementation gate. The 3 MEDIUM findings should be addressed but are not blocking.

No CRITICAL findings. No scope violation. No design source contradiction. No evidence fabrication.

The plan is code-generation-ready after resolving H1, H2, and H3.
