# WU-CM-14 Plan Review — AgentMiMo

## Review Metadata

- **Reviewer**: AgentMiMo (adversarial plan review)
- **Date**: 2026-06-19
- **Plan artifact**: `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md`
- **Design truths**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Verdict**: **PASS** — no blocking findings

## Findings

### F-01: Test 1 end-to-end scenario only covers proactive path [LOW]

**Location**: Plan §5 Test 1

**Evidence**: Test 1 seeds turn N / N+1 and forces pre-dispatch compact before dispatch, then asserts Engine messages contain the protected recent raw tail. This only exercises the proactive compact-success → ordinary dispatch path. The reactive compact-success → recovery dispatch path is not covered by an equivalent end-to-end test with the same four-item final answer scenario.

**Plan's position**: Test 6 (fallback regression) partially covers reactive by simulating "reactive context overflow / compact failure path" and asserting recovery/fallback RunInput includes the protected recent raw tail. However, test 6 covers fallback (tier 4/5), not the reactive compact-success → recovery Attempt ordinary dispatch path.

**Assessment**: If the reactive frozen material assembly fix (implementation outline item 3) produces correct material blocks but the recovery dispatch rendering has a separate bug, test 1 won't catch it and test 6 only covers fallback, not compact-success recovery. The plan should either extend test 1 to cover both proactive and reactive, or add a focused test 1b for reactive compact-success ordinal follow-up.

**Severity**: LOW — the reactive path is partially covered by tests 2 and 6, and the root cause fix is in material assembly which tests 2 and 3 do cover.

**Suggested verdict**: accepted — add a focused reactive compact-success regression during implementation; no plan rewrite needed.

### F-02: Test 4 eligible material boundary references undefined `USER_VISIBLE_RUN_STATE` [LOW]

**Location**: Plan §5 Test 4

**Evidence**: Test 4 says "if implementation identifies an already-defined `USER_VISIBLE_RUN_STATE` projection path, assert it is rendered as business-readable trace material without Host state refs." Code search for `USER_VISIBLE_RUN_STATE` in `dayu/host/` found no matching event type or projection path. The `CompactMaterialBlockKind` enum in `compact_material.py` does not include a run-state kind; the closest is `USER_INPUT`, `ASSISTANT_FINAL_ANSWER`, and `ACCEPTED_TOOL_EVIDENCE`.

**Assessment**: This is a conditional clause ("if implementation identifies"), so it does not block the plan. But the plan should be aware that user-visible Run outcome material (success/failure/cancel terminal) may not currently be materialized as a separate material block kind. Implementation may need to add it to trace_material or skip it.

**Severity**: LOW — conditional clause, does not block plan.

**Suggested verdict**: accepted — implementation will discover the right mechanism; the conditional wording is appropriate.

### F-03: Reactive frozen material assembly fix (item 3) is underspecified [MEDIUM]

**Location**: Plan §4 Implementation outline item 3

**Evidence**: The plan says `_frozen_reactive_material_blocks(...)` must reuse `build_pre_dispatch_compact_material_view(...)` plus current input anchor. However:

1. `build_pre_dispatch_compact_material_view(...)` requires a `HostTransaction`, `session_id`, `input_cursor`, `memory_snapshot_cursor`, and `policy_digest`. The current `_frozen_reactive_material_blocks(...)` already has a transaction and context, but does not have `policy_digest` or `memory_snapshot_cursor` readily available.

2. The plan says "Keep deeper 'exactly freeze the original overflow ordinary material list' convergence as WU-CM-13-owned residual." This means WU-CM-14 is only doing a partial fix to the reactive path — enough to preserve the protected recent raw tail, but not a full material list freeze. The partial fix boundary is not precisely stated.

3. The plan says the fix should ensure "protected recent raw tail semantics do not drift" between proactive and reactive, but the reactive frozen material assembly is structurally different from the proactive material view assembly. The plan does not explain how to verify semantic equivalence without full material list convergence.

**Assessment**: This is the most technically challenging part of the plan. The proactive path fix (items 1 and 2) is straightforward — pass an existing parameter and add a rendering path. The reactive fix requires constructing a material view in a context where one does not currently exist. The plan correctly identifies this as overlapping with WU-CM-13, but the partial fix boundary needs sharper definition during implementation.

**Severity**: MEDIUM — does not block plan gate, but implementation must stop and raise a blocking question if the reactive partial fix cannot be cleanly bounded.

**Suggested verdict**: accepted — plan correctly defers full convergence to WU-CM-13 and has a stop condition (§8: "Do not split unless the reactive path requires broader WU-CM-13 pipeline convergence. If that happens, stop before implementation expansion and raise a blocking question with direct state-machine evidence.").

### F-04: Implementation outline item 2 activation condition is vague [LOW]

**Location**: Plan §4 Implementation outline item 2

**Evidence**: The plan says "Activation condition should be post-compaction ordinary dispatch, for example when `CompactArtifactView.compact_artifact_ref is not None` for the current Run / Attempt." In the current `RunInputBuilder.build()` code (run_input.py:1779-1781), `compact` is loaded via provider and its `compact_artifact_ref` may be non-None from a *previous* run's compact, not the current one. The plan does not specify how to distinguish "this run just had a compact" from "there's an older compact artifact."

**Assessment**: The fallback provider (`_context_fallback_provider`) already tracks whether the current run has a compact/fallback context. If `fallback is not None`, the fallback path is taken and the protected recent raw tail is already partially handled by the fallback renderer. The gap is specifically in the `fallback is None` ordinary path after a successful compact. The activation condition needs to be: "compact artifact exists AND the current run's dispatch is post-compaction AND no fallback was triggered." This is discoverable during implementation.

**Severity**: LOW — the fallback/compact state is already tracked; the activation condition is an implementation detail.

**Suggested verdict**: accepted — implementation will discover the precise condition from the existing fallback/compact state tracking.

### F-05: No risk of WU-CM-13 scope creep [PASS]

**Location**: Plan §1, §4, §8, §9

**Evidence**: The plan explicitly states: "本 WU 不新增 WU-CM-14 专属 floor、不新增 ordinal follow-up floor、不做 prompt-pattern-specific retention、不做 deterministic final answer outline parser." The allowed files are `run_input.py`, `dispatch.py`, `engine_ingest.py`, and narrowly `compact_material.py`. The plan does not propose changes to public API, schema, EventLog event types, compact payload schema, memory kind, policy fields, prompt parser, or ordinal-specific rules. The residual risk section explicitly defers reactive pipeline convergence to WU-CM-13.

**Assessment**: No scope creep detected. The plan stays within WU-CM-14 boundaries.

**Verdict**: PASS — no finding.

### F-06: No risk of new policy/parser/schema [PASS]

**Location**: Plan §4, §5

**Evidence**: The plan reuses `MemoryProjectionPolicy.selected_recent_window_turn_floor` and `protected_recent_turn_group_ids_for_material_blocks(...)`. No new policy fields, no ordinal parser, no prompt-pattern-specific retention. Test 5 explicitly asserts bare `TOOL_CALL_REQUESTED` / tool request atoms do not enter Engine messages and internal refs do not appear in LLM-facing content.

**Assessment**: No new policy/parser/schema risk detected.

**Verdict**: PASS — no finding.

### F-07: LLM-facing material boundary is correctly specified [PASS]

**Location**: Plan §4 item 2, §5 Test 5

**Evidence**: The plan specifies eligible material as: history user prompt, assistant final answer, accepted readable tool evidence, user-visible outcome material. It explicitly excludes: bare tool request, Host internal refs (event_id, tool_call_id, payload_ref, digest, cursor, Attempt id, execution id, fallback diagnostic refs, Host governance state, Engine state). This aligns with `docs/host/design.md:2591-2603` (accepted compacted view as business summary only, Answer Anchor Memory as outline not fact) and `docs/host/design.md:3284-3292` (compact selection preserves current input anchor and protected recent floor).

**Assessment**: The LLM-facing boundary is correctly specified and matches design truth.

**Verdict**: PASS — no finding.

### F-08: Root cause has direct code evidence [PASS]

**Location**: Plan §2, §3

**Evidence verified against codebase**:

1. `dispatch.py:1853-1859` — `select_compact_segment(trigger_source=CompactSegmentTrigger.PROACTIVE, ...)` with no `selected_recent_window_turn_floor` parameter (defaults to 0). **Confirmed.**
2. `dispatch.py:1515-1523` — recovery tier passes `memory_policy.selected_recent_window_turn_floor`. **Confirmed.**
3. `engine_ingest.py:3795-3801` — `select_compact_segment(trigger_source=CompactSegmentTrigger.REACTIVE, ...)` with no `selected_recent_window_turn_floor`. **Confirmed.**
4. `engine_ingest.py:4058-4072` — `_frozen_reactive_material_blocks(...)` passes empty `MemorySnapshotView(messages=(), ...)`, `CompactArtifactView(messages=(), ...)`, `SessionContinuityView(messages=())`. **Confirmed.**
5. `run_input.py:1789-1794` — `if fallback is None: bounded_context_messages = (*memory.messages, *compact.messages, *continuity.messages)` with no EventLog-backed post-compact delta rendering. **Confirmed.**
6. `dispatch.py:2192-2224` — proactive fallback passes `selected_recent_window_turn_floor`. **Confirmed.**

All three root cause claims are directly evidenced by code.

**Verdict**: PASS — no finding.

### F-09: README trigger judgment is correct [PASS]

**Location**: Plan §6

**Evidence**: Plan correctly identifies that implementation touches `dayu/host/` and `tests/`, so it must check `dayu/host/README.md` and `tests/README.md` Agent update constraints. The plan does not pre-commit to README changes, which is correct because the protected recent floor behavior is internal Host material selection semantics, not user-facing CLI/Web/WeChat workflow or install steps.

**Verdict**: PASS — no finding.

## Residual Risks

| ID | Risk | Severity | Owner |
|---|---|---|---|
| WU-CM-14-RR-1 | Reactive frozen material assembly partial fix may not achieve full semantic equivalence with proactive path; full convergence deferred to WU-CM-13 | MEDIUM | WU-CM-13 |
| WU-CM-14-RR-2 | `USER_VISIBLE_RUN_STATE` material boundary may not have a current material block kind implementation; may need trace_material extension or explicit non-goal | LOW | Implementation |
| WU-CM-14-RR-3 | Post-compaction activation condition for ordinary RunInput raw tail rendering needs precise implementation discovery | LOW | Implementation |

## Test Gaps

| Gap | Description | Severity |
|---|---|---|
| TG-1 | No end-to-end reactive compact-success ordinal follow-up test (only fallback covered by test 6) | LOW |
| TG-2 | Test 4 eligible material boundary for user-visible outcome material is conditional, not guaranteed | LOW |

## Conclusion

**PASS** — no blocking findings. The plan is code-generation-ready with the following caveats:

1. Implementation must stop and raise a blocking question if the reactive frozen material assembly partial fix cannot be cleanly bounded against WU-CM-13.
2. Test 1 should be extended or supplemented with a reactive compact-success regression during implementation.
3. The post-compaction activation condition for ordinary RunInput raw tail rendering is an implementation detail discoverable from existing fallback/compact state tracking.

The plan correctly identifies root cause with direct code evidence, stays within WU-CM-14 scope, reuses existing `selected_recent_window_turn_floor` / protected recent floor without new policy/parser/schema, correctly specifies LLM-facing material boundaries, and has adequate test coverage with minor gaps.
