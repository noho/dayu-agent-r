# P9.5 Pre-P10 Cross-Repository Hardening Plan Re-Review — AgentMiMo

- Reviewer: AgentMiMo
- Date: 2026-05-17
- Re-review target: `docs/host/p9-5-pre-p10-hardening-plan.md` (post-fix version)
- Controller adjudication: `docs/reviews/p9-5-plan-review-controller-adjudication-20260517.md`
- Original review: `docs/reviews/p9-5-plan-review-mimo-20260517.md`
- DS review: `docs/reviews/p9-5-plan-review-ds-20260517.md`
- Gate: re-review after required plan fix

## Verdict

**PASS.** All accepted findings are fixed. No new blockers introduced by the plan fix.

## Accepted Finding Fix Status

### DS F1 [MEDIUM] S14 `current_goal` first-write-wins underspecified — FIXED

Controller required: define current code owner/path, write path, enforcement strategy, and targeted validation expectation.

Plan fix evidence (lines 323-331):

- **Type definition location**: `PinnedStateView.current_goal: str | None` in `dayu/host/memory.py`. Verified at `memory.py:313`.
- **Write path**: `build_conversation_memory_snapshot_from_events(...)` → `project_conversation_memory_event(...)` → `_pinned_state_with_user_input(...)`. Verified: `_pinned_state_with_user_input` exists at `memory.py:1365`.
- **Enforcement direction**: first-write-wins in `_pinned_state_with_user_input(...)`: read `pinned_state.current_goal`, set only when `None`. Verified at `memory.py:1390-1392`: `current_goal = pinned_state.current_goal; if current_goal is None: current_goal = text`.
- **Test strategy**: "add targeted tests that build a snapshot from two or more USER_INPUT_ACCEPTED events and assert the first accepted user input remains pinned_state.current_goal while later user inputs are appended as user_constraints."
- **Fallback**: "If implementation discovers current code no longer enforces first-write-wins, fix only `_pinned_state_with_user_input(...)` using the same transaction-free pure projection direction."
- **Boundary**: "Do not add DB uniqueness, CAS, state-machine transition, or schema history retention for this item."

All code references verified against the actual repository. The S14 `current_goal` item is now code-generation-ready.

### DS F2 [MEDIUM] S14 legacy `SessionContinuityProvider` parameters underspecified — FIXED

Controller required: identify module/path, legacy parameter behavior, bypass mechanism, and remove-vs-tighten decision rule.

Plan fix evidence (lines 323-331, 332-334):

- **Module path**: `SessionContinuityProvider` protocol in `dayu/host/run_input.py`; `DurableSessionContinuityProvider` is production implementation. Verified: `run_input.py:307` and `run_input.py:529`.
- **Bypass mechanism**: "the RunInputBuilder composition point, which appends `*continuity.messages` after memory messages and before the current user prompt. Any provider that reintroduces historical raw turns there can bypass `MemoryProjectionPolicy.history_pool_size_units`." Verified: `history_pool_size_units` exists at `memory.py:591`.
- **Decision rule**: "The preferred decision is remove legacy historical raw-turn behavior from production continuity entirely." Tighten only "if a non-history use is directly evidenced, such as resume wait accepted fact reconstruction."
- **Tightened boundary**: "The tightened provider may emit only bounded, non-history, current-run resume/system facts... it must not accept parameters that control history count, raw turn inclusion, before-event replay, or budget bypass."
- **Legacy cleanup**: "Remove unused legacy reader paths or parameters when no production code uses them."
- **Stop condition**: "any `SessionContinuityProvider` historical raw-turn path appears necessary for current behavior. Historical continuity must be reassigned to memory/P10 design."

The remove-vs-tighten decision rule is clear and evidence-gated. The bypass mechanism is concrete and testable.

### DS F3 [LOW] S10/S14 shared `test_resolve_wait_command.py` — FIXED

Controller accepted as non-blocking, required dispatch/plan guidance.

Plan fix:
- Implementation Decisions #7 (line 89): "Shared test files must be treated as accumulated assertions. Later slices may refactor shared fixtures, but must not delete, weaken, skip, or bypass prior-slice assertions; any fixture refactor affecting a shared file must be reported in the slice artifact with the prior assertions it preserves."
- S10 (line 264): "When editing `tests/host/test_resolve_wait_command.py`, add S10-specific assertions without weakening existing resolve_wait behavior tests, and leave fixture names/shape stable for S14 unless a fixture refactor is reported explicitly."
- S14 (line 338): "When editing `tests/host/test_resolve_wait_command.py`, preserve S10 late-rejection/catch-up assertions. If S14 needs shared fixture changes for memory catch-up, report the fixture refactor and list the S10 assertions that still pass."

Triple coverage (Implementation Decisions + S10 + S14) is thorough.

### DS F4 [LOW] S15 should audit existing logs before adding new logs — FIXED

Controller required: add S15 instruction to audit existing logs first.

Plan fix (line 354): "Audit existing Engine/Host log calls before adding new ones. Classify each relevant path as already correct, missing, mis-leveled, missing required typed ids/refs, or unsafe because it logs oversized/sensitive data."

Audit-first instruction with explicit classification categories. Sufficient for implementation.

### DS F5 [LOW] S11 private-module test dependency risk — FIXED

Controller required: add S11 stop condition/guidance for behavior tests vs. private-module imports.

Plan fix:
- S11 (line 278): "If moving types used by tests, prefer behavior tests through public documented entries. Tests may import a true private owner only when the test is explicitly an import-boundary or private-invariant test and no public behavior can prove the invariant."
- S11 (line 279): "Do not create test-only private re-export, facade, or compatibility wrapper to preserve old test imports."
- S11 stop condition (line 287): added "test-only private re-export" to the stop list.

Clear hierarchy: behavior test preferred > import-boundary test with justification > no test-only re-export.

### MiMo F-01 [LOW] Slice dependencies are implicit — FIXED

Controller required: add dependency/dispatch-order guidance.

Plan fix — Implementation Decisions #6 (line 87): "Dispatch order is sequential by default: S0, S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, S16, S17, S18. Controller may parallelize only disjoint read-only review work or explicitly independent implementation slices with non-overlapping write sets. S14 depends on S10 for shared `resolve_wait` / dispatch catch-up test ownership; S16 should run after ownership-sensitive refactors S1/S3/S11/S14 unless controller dispatches it as audit-only."

Explicit sequential default with named cross-slice dependencies. Sufficient.

### MiMo F-02 [LOW] S15 logger acquisition mode unspecified — FIXED

Controller required: add guidance to follow existing project logger pattern.

Plan fix (line 355): "Follow each module's existing logger acquisition pattern. Where local code already uses module-level `logging.getLogger(__name__)`, keep that pattern and do not introduce constructor-injected loggers. If a module has no logger and needs one, default to module-level `_LOGGER = logging.getLogger(__name__)`."

Explicit convention with default fallback. Sufficient.

### MiMo F-03 [LOW] S14 `current_goal` ambiguity — DUPLICATE of DS F1

Controller marked as duplicate. Covered by DS F1 fix above. **FIXED**.

### MiMo F-04 [LOW] S6 unknown enum test layer ambiguity — FIXED

Controller required: clarify S6 tests should distinguish DB CHECK from Python mapping fail-closed.

Plan fix (line 202): "Keep DB CHECK and Python mapping tests separate. S5 owns direct SQL invalid-row tests that should fail at SQLite CHECK / FK level. S6 owns mapping fail-closed tests; for unknown enum values that DB CHECK would reject, construct the durable row dataclass or mapping helper input directly so the Python mapping layer is exercised."

Clear ownership split with concrete test strategy. Sufficient.

### MiMo F-05 [LOW] Slice commit organization unspecified — FIXED

Controller required: add controller/git strategy guidance.

Plan fix — Implementation Decisions #8 (line 90): "Accepted slice commit strategy is controller-owned. High-risk slices with public API, schema, state-machine, ToolRuntime, dispatch, runner, or memory semantics stay as separate accepted commits. Adjacent low-risk slices may be combined only by explicit controller decision before staging."

Controller-owned with explicit high/low risk criteria. Sufficient.

### MiMo F-06 [LOW] S2 "directly evidenced parser defects" standard unspecified — FIXED

Controller required: add S2 evidence standard.

Plan fix (line 134): "Direct evidence means at least one of: existing failing test, directly inspected current code path contradicting current contract, provider protocol behavior reproduced by a focused fake/fixture, or official provider/protocol documentation that applies to the current OpenAI-compatible parser. Theory-only edge cases and speculative hardening are out of scope."

Four concrete evidence types with explicit out-of-scope boundary. Sufficient.

### MiMo F-07 [LOW] pyright baseline unspecified — FIXED

Controller required: add S0 baseline pyright check.

Plan fix (line 101): "Run and record `source .venv/bin/activate && python -m pyright dayu tests` as the type-check baseline before S1. If baseline has errors, classify them as pre-existing; later slices must not introduce new errors, expand existing errors, or leave touched-file errors unfixed."

Baseline recording with clear handling rule. Sufficient.

### MiMo F-08 [LOW] S11 extraction granularity risk — FIXED

Controller required: add S11 guidance to extract only where it removes real coupling.

Plan fix (line 276): "Extract only if it removes real coupling or is needed to make S12/S16 changes localized. The listed owners are candidate groupings, not required new modules; small cohesive code may stay in `tool_runtime.py`."

On-demand extraction with explicit "candidate, not required" framing. Sufficient.

## New Blocker Check

The plan-fix introduced no new blockers:

1. **S14 code evidence is verified.** All referenced types (`PinnedStateView`, `_pinned_state_with_user_input`, `SessionContinuityProvider`, `DurableSessionContinuityProvider`, `MemoryProjectionPolicy.history_pool_size_units`) exist in the actual codebase at the referenced locations.
2. **S14 enforcement logic is verified.** `_pinned_state_with_user_input` at `memory.py:1390-1392` implements exactly the first-write-wins pattern described: `current_goal = pinned_state.current_goal; if current_goal is None: current_goal = text`.
3. **S14 remove-vs-tighten decision rule is evidence-gated.** The plan correctly makes "remove" the default and "tighten" contingent on direct evidence of non-history use. This prevents implementation drift toward preserving legacy behavior.
4. **Non-blocking guidance integrated cleanly.** Implementation Decisions grew from 5 to 8 items; each addition is a one-sentence rule that doesn't contradict existing decisions or introduce architectural ambiguity.
5. **S10/S14 shared test ownership has triple coverage** (Implementation Decisions #7 + S10 line 264 + S14 line 338), which is more than sufficient.
6. **No scope expansion.** All fixes are within the adjudicated required-action scope. No P10+ semantics were introduced.

## Conclusion

- **Accepted findings fixed**: 12/12 (DS F1-F5, MiMo F-01 through F-08, with F-03 as duplicate of F-1)
- **New blockers**: 0
- **Re-review verdict**: PASS. Plan is ready for accepted plan commit and implementation dispatch.
