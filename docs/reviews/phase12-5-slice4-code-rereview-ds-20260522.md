# Phase 12.5 Slice 4 Code Re-Review: LLM Compactor Structured JSON Rewrite (Repair Verification)

## 0. Review Metadata

- Review agent: AgentDS
- Date: 2026-05-22
- Gate: Phase 12.5 Slice 4 targeted re-review (repair verification)
- Original review: `docs/reviews/phase12-5-slice4-code-review-ds-20260522.md`
- Plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- Design source: `docs/host/design.md`
- Baseline: HEAD=e0cc8a1

## 1. Verdict

**PASS.** All four targeted findings (F1/F2/F3/F6) are fixed. No regression, no scope violation, no type error. Deferred findings F4/F5 remain low-risk and do not block Slice 5.

## 2. Finding Verification

### F1 [Medium-High] `compaction_budget.py` Dead Code — FIXED

**Verification:**
- `test -f dayu/host/compaction_budget.py` → DELETED
- `rg "estimate_compacted_context_budget|compaction_budget\." dayu tests` → zero hits
- `llm_compaction.py` import of `compaction_budget` removed (was already removed in original Slice 4)

**Assessment:** Complete. No stale `CompactionRequest` field references remain. No latent import crash risk.

---

### F2 [Medium] `_budget_after_compact` Only Counted `episode.goal` — FIXED

**Verification (file: `dayu/host/llm_compaction.py`):**

1. **Signature expanded (line 1004-1010):**
   ```python
   def _budget_after_compact(
       request: CompactionRequest,
       episode: EpisodeSummaryCandidate,
       pinned_patch: PinnedStatePatchCandidate,
       fact_candidates: tuple[EvidenceBackedFactCandidate, ...],
       preserve_items: tuple[MinimumPreserveItemCandidate, ...],
   ) -> int:
   ```
   Previously accepted only `(request, summary: str)` where summary was `episode.goal`.

2. **Structured output text extraction (lines 1034-1064):**
   `_structured_output_texts` collects:
   - `episode.episode_title`, `episode.goal`
   - `episode.completed_actions[*]`
   - `episode.confirmed_fact_summaries[*]`
   - `episode.user_constraints[*]`
   - `episode.open_questions[*]`
   - `episode.next_step` (if not None)
   - Pinned patch replace values via `_pinned_patch_texts` (line 1067-1079)
   - `fact_candidates[*].claim_text`
   - `preserve_items[*].label` + `preserve_items[*].text`

3. **Null-safe helpers (lines 1082-1103):**
   `_optional_text(value: str | None)` returns `(value,)` or `()`.
   `_optional_string_tuple_texts(value: tuple[str, ...] | None)` returns the tuple or `()`.
   Both correctly handle the tri-state patch model (MISSING/CLEAR → `value=None`).

4. **Call site updated (line 444-449):**
   ```python
   budget_after_compact=_budget_after_compact(
       request, episode, pinned_patch, fact_candidates, preserve_items,
   ),
   ```

5. **Test proof (lines 139-177):**
   `test_llm_context_compactor_budget_counts_structured_output_text` constructs two candidates with identical `episode.goal` but different `claim_text`/`minimum_preserve_text` lengths, then asserts `long_candidate.budget_after_compact > short_candidate.budget_after_compact` AND `long_candidate.episode_summary_candidate.goal == short_candidate.episode_summary_candidate.goal`. This directly proves that text beyond `episode.goal` drives the estimate.

**Assessment:** Complete. All structured output text fields contribute to budget estimation. The specific scenario described in original F2 (overlong `claim_text` not counted) is now tested.

---

### F3 [Medium] `_SYSTEM_PROMPT` Miscounted as Post-Compact Context — FIXED

**Verification (file: `dayu/host/llm_compaction.py`):**

1. **Separation of concerns (lines 76-90):**
   ```python
   _SYSTEM_PROMPT = (
       "You are a host-owned context compaction component. ..."
   )
   _POST_COMPACT_SYSTEM_PROMPT_ESTIMATE = (
       "Host post-compact run context includes compact summary, pinned state, "
       "current input, preserved refs, evidence-backed facts, and continuity items."
   )
   ```
   Clear separation: `_SYSTEM_PROMPT` is the compactor LLM prompt (line 231, sent to Engine as system message). `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE` is a semantically descriptive conservative estimate for post-compact runs.

2. **Usage in budget estimation (line 1119):**
   ```python
   typed_fragment_tokens = sum(
       _estimate_text_tokens(fragment)
       for fragment in (
           _POST_COMPACT_SYSTEM_PROMPT_ESTIMATE,  # ← was _SYSTEM_PROMPT
           ...
       )
   )
   ```

3. **Docstring accuracy (line 1109-1110):**
   "基于保留引用占比、当前输入和 post-compact 系统提示保守估算 compact 后预算"
   No stale reference to "旧 verified/tool fact 预算 helper."

**Assessment:** Complete. The two prompts are semantically separated. The post-compact estimate is labeled as such. The docstring is accurate.

---

### F6 [Low] Stale Docstring — FIXED

**Verification:** The docstring at `_estimate_preserved_context_tokens` (lines 1107-1113) no longer references "旧 verified/tool fact 预算 helper." See F3 verification above for the replacement text.

**Assessment:** Complete.

---

### Additional Change: `_MIN_SUMMARY_LENGTH` → `_MIN_PROPOSAL_LENGTH`

**Observation (line 67):** The constant was renamed to match the "proposal" terminology used throughout the module. Value unchanged (still 1). Cleanup is consistent with the module's terminology migration from "summary" to "proposal."

**Assessment:** Minor, safe. No semantic change.

## 3. Deferred Findings Status

### F4 [Low] No Test for Empty Candidate Lists — REMAINS DEFERRED

**Current state:** Still untested at the `test_llm_compaction.py` level. The `_required_sequence` function correctly allows `len(value) == 0`, producing empty tuples. The contract-dataclass `__post_init__` check on `EvidenceBackedFactCandidate.evidence_refs` (non-empty required) is tested in Slice 3's `test_compaction_contract.py`.

**Risk assessment:** Low. The empty-list path is structurally correct. A future change that broke it would need to add a `len(value) < min_items` check to `_required_sequence`, which would be caught by a simple test. Deferrable to Slice 5 or 7.

### F5 [Low] No Test for Invalid Enum Values — REMAINS DEFERRED

**Current state:** Still untested. `EvidenceBackedFactKind("invalid")` raises `ValueError` via `StrEnum.__new__`, caught by outer `except (KeyError, TypeError, ValueError)` → `LLMCompactionProposalError`. Same for `MinimumPreserveReason`.

**Risk assessment:** Low. This is Python built-in `StrEnum` behavior, validated indirectly through the happy-path test (valid enum passes). Contract-layer tests in Slice 3 also validate enum construction. Deferrable to Slice 5 or 7.

## 4. Scope Boundary Audit

| Check | Result | Evidence |
|-------|--------|----------|
| Only allowed files modified | PASS | `llm_compaction.py`, `test_llm_compaction.py`, `README.md` |
| `compaction_budget.py` removal only | PASS | Deleted, zero callers |
| No new public API | PASS | All new functions are `_private` (module-level) |
| No second LLM call path | PASS | Single `compact()` → `_candidate_from_final_answer` path unchanged |
| No Engine/Fins/Service boundary breach | PASS | No imports or changes outside `dayu/host/` |
| No old verified/tool_fact semantics introduced | PASS | `rg` on all stale patterns returns zero hits |
| Pyright clean | PASS | 0 errors, 0 warnings, 0 informations |
| All tests pass | PASS | 14 passed in 0.59s |
| New test properly scoped | PASS | Tests budget estimation directly; no external dependencies |

## 5. Regression Check

Compared to original Slice 4 review baseline:

| Original test | Status | Notes |
|---------------|--------|-------|
| `does_not_use_thread_bridge` | PASS | Unchanged |
| `builds_tool_disabled_request` | PASS | Unchanged |
| `maps_final_answer_to_candidate` | PASS | budget_after_compact still > 8 |
| `budget_counts_preserved_context` | PASS | budget_after_compact still >= 80 |
| `rejects_empty_plain_text_or_non_final_output` | PASS | Unchanged |
| `rejects_malformed_and_schema_invalid_json` | PASS | Unchanged |
| `rejects_overlong_structured_text` | PASS | Unchanged |
| `rejects_non_accepted_evidence_refs` | PASS | Unchanged |
| `rejects_truncated_final_output` | PASS | Unchanged |
| `applies_runner_timeout` | PASS | Unchanged |
| `sanitizes_failed_runner_outcome` | PASS | Unchanged |
| `preserves_host_owned_refs_and_evidence` | PASS | Unchanged |
| `uses_runner_retry_policy_without_owning_semantic_repair` | PASS | Unchanged |
| **NEW** `budget_counts_structured_output_text` | PASS | Direct proof of F2 fix |

No regression on any existing test.

## 6. README Sync

README change (1 paragraph, 5 modifications):
- "覆盖 summary" → "覆盖 structured summary 文本、pinned patch 文本、fact claim、minimum preserve 文本" — reflects F2 fix scope
- "系统提示" → "post-compact 系统提示" — reflects F3 fix
- "final summary" → "final proposal" — terminology consistency

Within Slice 4 bounds. Broader README sync belongs to Slice 7.

## 7. Conclusion

All four DS findings are fixed. No regressions, no scope violations, no new findings. F4/F5 remain deferred low-risk and do not block Slice 5. Slice 4 is ready for Slice 5 (Memory Projection Materialization).

**Remaining blockers: 0.**
