# WU-CM-14 Plan Re-Review — AgentDS

## Review Metadata

| 项目 | 值 |
|---|---|
| review type | plan re-review (follow-up to accepted findings) |
| fixed plan | `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md` |
| previous reviews | `docs/reviews/plan-review-wu-cm-14-ds.md` (AgentDS), `docs/reviews/plan-review-wu-cm-14-mimo.md` (AgentMiMo) |
| reviewer | AgentDS |
| date | 2026-06-19 |

## Executive Summary

**Verdict: PASS.** All 3 HIGH findings and all 3 MEDIUM findings from the DS review are closed. All 4 MiMo findings (F-01 through F-04) that intersected with DS findings are also closed. MiMo F-02 (USER_VISIBLE_RUN_STATE, LOW) was accepted as conditional — no change required. The fixed plan is now code-generation-ready with no remaining blocking or conditional findings.

## Finding-by-Finding Closure Verification

### DS-H1: Underspecified transaction/EventLogStore access → CLOSED

**What DS-H1 required:**
- Provider name and contract
- Transaction ownership mechanism
- Policy floor source
- Exact RunInputBuilder injection point

**What the fixed plan provides (lines 68-97):**

| Requirement | Fixed Plan Evidence |
|---|---|
| Provider contract | `_ProtectedRecentRawTailView(messages, material_blocks, source_refs)` (line 70); `_ProtectedRecentRawTailProvider.load_protected_recent_raw_tail(snapshot, current_facts, memory, compact)` (line 71) |
| Noop for tests | `_NoopProtectedRecentRawTailProvider` returns empty view (line 72) |
| Durable provider | `_DurableProtectedRecentRawTailProvider` owns `HostTransactionRunner`, `EventLogStore`, resolved `MemoryProjectionPolicy`; mirrors `DurableAcceptedToolEvidenceMaterialProvider` pattern (line 73) |
| Injection mechanism | New internal dependency in `RunInputBuilder.__init__` with noop default (line 74) |
| Injection point | `memory.messages + compact.messages + protected_recent_raw_tail.messages + continuity.messages`; fallback branch remains exclusively `_fallback_context_messages(...)` (lines 76-77) |

**Code existence verification:** `HostTransactionRunner` exists at `dayu/host/durable/transaction.py` and is already used by `tool_trace.py`, `recovery.py`, `audit.py`, `command.py`, `memory_repair.py`. `DurableAcceptedToolEvidenceMaterialProvider` exists at `run_input.py:1316` — the new provider mirrors this established pattern.

**Verdict: CLOSED.** ✅

---

### DS-H2 / MiMo F-04: Imprecise activation condition → CLOSED

**What DS-H2 required:**
- Definitive activation condition (not "for example when")
- Fallback double-rendering prevention
- Old compact artifact mis-trigger prevention

**What the fixed plan provides (lines 78-86):**

| Requirement | Fixed Plan Evidence |
|---|---|
| Definitive call-site condition | `compact.compact_artifact_ref is not None` AND `fallback is None` (lines 79-80); explicitly means "ordinary post-compaction dispatch, not current-input-only first dispatch and not fallback dispatch" (line 81) |
| Fallback double-rendering guard | Fallback branch exclusively `_fallback_context_messages(...)` and must not also call/render the raw-tail provider (line 77); new Test 4 asserts activation skipped when `fallback is not None` (line 145) |
| Old artifact mis-trigger | Provider-side validation: compact artifact loaded for current `run_id` and before current Attempt start cursor (line 82); existing `DurableCompactArtifactProvider` already queries `run_id = current_facts.run.run_id AND event_sequence < current_facts.attempt.started_event_sequence` (confirmed at `run_input.py:3155-3173`) |
| Reactive compact-success | Explicitly covered: recovery dispatch creates new Attempt for same Run, enters same ordinary `build()` no-fallback branch (line 85) |

**Code existence verification:** The existing `DurableCompactArtifactProvider` at `run_input.py:3148-3181` already scopes queries by `run_id` and `event_sequence < attempt.started_event_sequence` — old artifact mis-trigger is architecturally impossible under the current provider contract.

**Verdict: CLOSED.** ✅

---

### DS-H3 / MiMo F-01: Reactive coverage gap → CLOSED

**What DS-H3 required:**
- Reactive compact-success regression (not just fallback)
- Proof that recovery dispatch reaches ordinary `RunInputBuilder.build()`
- Reactive fallback test committed, not optional

**What the fixed plan provides:**

| Requirement | Fixed Plan Evidence |
|---|---|
| Reactive compact-success test | New Test 2 (lines 128-133): "Simulate or drive accepted reactive compact, then build the recovery Attempt request through ordinary `RunInputBuilder.build()` with `fallback is None`." Code evidence: "reactive compact-success dispatch still creates a new Attempt for the same Run and reaches ordinary `RunInputBuilder.build()`; the distinguishing state is `RUN_STARTED(start_reason=recovery)`, while the message assembly owner is the same no-fallback ordinary branch." |
| Equivalence proof | "If a full scheduler-level reactive E2E is not used, the focused test must explicitly construct the recovery Attempt state and call the same public/internal builder path used by dispatch, not only test helper functions" (line 133) |
| Reactive fallback committed | "Reactive fallback is a committed focused test, not optional" (line 165); equivalence criteria: uses same frozen material assembly, same fallback selection, same active fallback payload/view shape, same RunInput fallback renderer as production (line 166) |

**Verdict: CLOSED.** ✅

---

### DS-M1: test_compaction_operation.py allowed file → CLOSED

**What DS-M1 required:** Remove from allowed files or add specific test requirement.

**What the fixed plan provides:**

| Change | Evidence |
|---|---|
| Removed from allowed test files (Section 5) | Lines 114-117: only `test_run_input_builder.py`, `test_compact_material.py`, `test_dispatch_scheduler.py`, `test_memory_projection.py` |
| Removed from allowed test files (Section 8) | Lines 227-230: same four files |
| Removed from validation commands (Section 7) | Line 202: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` |

**Verdict: CLOSED.** ✅

---

### DS-M2: Duplicate message risk → CLOSED

**What DS-M2 required:** Dedup rule between memory selected recent window and EventLog raw tail, plus test coverage.

**What the fixed plan provides:**

| Requirement | Fixed Plan Evidence |
|---|---|
| Dedup mechanism | Extend internal `MemorySnapshotView` with defaulted private provenance fields (source refs / content digests); no public API or durable schema change (line 93) |
| Dedup rule for user/assistant | Drop raw-tail block when its canonical event/evidence provenance or rendered content digest is already represented by memory selected recent window (line 94) |
| Dedup rule for evidence | Compare both evidence id and tool-result event ref; compact material uses canonical evidence id while memory selected evidence may carry event id (line 95) |
| Test coverage | New Test 5 (lines 147-151): memory snapshot with overlapping selected recent window; assert each historical message exactly once; assert evidence not duplicated; assert current prompt exactly once |

**Verdict: CLOSED.** ✅

---

### DS-M3 / MiMo F-03: Reactive frozen material repair stop condition → CLOSED

**What DS-M3 required:** Concrete, testable stop condition for WU-CM-14 reactive fix boundary.

**What the fixed plan provides:**

| Requirement | Fixed Plan Evidence |
|---|---|
| Concrete stop condition | "After repair, `_frozen_reactive_material_blocks(...)` must produce material blocks for the most recent `selected_recent_window_turn_floor` eligible turn groups from post-compact delta material, including committed user prompt, assistant final answer, and accepted readable tool evidence when those events exist" (line 102) |
| Minimum bar | "The focused reactive material assembly test must prove those three block classes are present before `build_recent_window_fallback_selection(...)` runs; merely proving current input anchor exists is insufficient" (line 103) |
| WU-CM-13 boundary | "Keep deeper 'exactly freeze the original overflow ordinary material list' convergence as WU-CM-13-owned residual" (line 104) |
| Test coverage | New Test 9 (lines 170-173): seed post-compact delta with ≥2 turn groups, set floor to 1 or 2; assert material blocks for protected turn groups include user/assistant/evidence; assert exactly one current input anchor, not treated as historical |

**Verdict: CLOSED.** ✅

---

### MiMo F-02: USER_VISIBLE_RUN_STATE conditional → No change required

**Previous status:** LOW severity, accepted as conditional. MiMo noted "implementation will discover the right mechanism; the conditional wording is appropriate."

**Current plan status:** The conditional clause remains (line 157): "if implementation identifies an already-defined `USER_VISIBLE_RUN_STATE` projection path, assert it is rendered as business-readable trace material without Host state refs." This is unchanged, which is correct — MiMo already accepted this as a LOW conditional.

**Verdict:** No change required. Not a re-review finding.

---

## Scope Boundary Verification (Re-confirmed)

| Constraint | Status | Evidence |
|---|---|---|
| No new WU-CM-14专属 floor | ✅ | Line 9; reuses `selected_recent_window_turn_floor` |
| No ordinal parser | ✅ | Line 9 |
| No prompt-pattern-specific retention | ✅ | Line 9 |
| No public API changes | ✅ | Line 58 |
| No schema changes | ✅ | Line 58 |
| No EventLog event type changes | ✅ | Line 58 |
| No memory kind changes | ✅ | Line 58 |
| No policy field changes | ✅ | Line 58; only passes existing field |
| No WU-CM-13 scope creep | ✅ | Lines 104, 257-258: explicitly defers pipeline convergence |

## Allowed Files Re-verification

| File | Status | Notes |
|---|---|---|
| `dayu/host/run_input.py` | ✅ | Provider + injection point |
| `dayu/host/dispatch.py` | ✅ | Two-line floor pass fix |
| `dayu/host/engine_ingest.py` | ✅ | Reactive floor pass + frozen material repair |
| `dayu/host/compact_material.py` | ✅ | Guarded with "only if" clause; no new exposure needed since `build_pre_dispatch_compact_material_view` already importable |
| `tests/host/test_compaction_operation.py` | ✅ | Removed (was DS-M1) |

## Test Plan Coverage (10 tests, up from 7)

| # | Test | Paths Covered | Root Causes | New/Changed |
|---|---|---|---|---|
| 1 | Proactive E2E regression | Proactive compact-success → ordinary | All three | — |
| 2 | Reactive compact-success regression | Reactive compact-success → recovery ordinary | #2 | **NEW** (DS-H3) |
| 3 | Compact selection floor regression | Proactive normal + reactive root selection | #1 | Extended to reactive |
| 4 | Ordinary RunInput raw tail boundary | Post-compaction ordinary; activation skip conditions | #2 | Added skip assertions (DS-H2) |
| 5 | Duplicate prevention regression | Memory overlap + raw tail dedup | #2 | **NEW** (DS-M2) |
| 6 | Eligible material boundary | Material type enumeration | #2 | — |
| 7 | Negative LLM-facing boundary | Internal ref / bare tool request exclusion | #2 | — |
| 8 | Fallback regression | Proactive + reactive fallback | #3 | Reactive committed (DS-H3) |
| 9 | Reactive frozen material assembly stop-condition | Frozen material block composition | #3 | **NEW** (DS-M3) |
| 10 | Current input anchor regression | Current input dedup | #2 | — |

## Additional Verification

### DS-L1 (double-read concern):
Fixed plan line 97: "Re-reading EventLog in this provider is acceptable for WU-CM-14: EventLog / payload truth is immutable after commit, and the provider uses a short read transaction. Passing an already-built `PreDispatchCompactMaterialView` through dispatch state would be broader WU-CM-13 pipeline convergence and is not required here." — **Explicitly acknowledged and justified.** ✅

### DS-L2 ("for example when" language):
The imprecise "for example when" language is replaced with definitive conditions throughout (lines 78-86). — **Fixed.** ✅

### DS-L3 (residual risk specificity):
Fixed plan Section 9 now lists residual risks as three concrete bullet points (lines 255-259). — **Addressed.** ✅

### Provider mirror pattern:
The new `_DurableProtectedRecentRawTailProvider` is specified to mirror `DurableAcceptedToolEvidenceMaterialProvider` (line 73). Verified: `DurableAcceptedToolEvidenceMaterialProvider` exists at `run_input.py:1316` and follows the same `HostTransactionRunner` + `EventLogStore` ownership pattern. The mirror is architecturally sound.

## Residual Risks (Post-Re-Review)

| ID | Risk | Severity | Owner |
|---|---|---|---|
| RR-1 | Recovery dispatch might not reach ordinary `RunInputBuilder.build()` after reactive compact-success — the plan's equivalence proof would be invalidated | LOW | Implementation verification; plan has stop condition (line 259) |
| RR-2 | `build_pre_dispatch_compact_material_view` double-read latency in dispatch hot path | LOW | Acceptable per plan line 97 |
| RR-3 | WU-CM-13 unification may revisit the reactive frozen material repair | LOW | WU-CM-13 preflight |

No new residual risks introduced by the plan amendments.

## Validation

```bash
git diff --check -- docs/reviews/plan-rereview-wu-cm-14-ds.md
```

## Conclusion

**PASS.** All 9 findings from the two prior reviews (DS-H1, DS-H2, DS-H3, DS-M1, DS-M2, DS-M3, MiMo F-01, MiMo F-03, MiMo F-04) are closed with concrete evidence from the fixed plan. The remaining MiMo F-02 (LOW) was accepted as-is and requires no change.

The fixed plan is code-generation-ready. No blocking or conditional findings remain.
