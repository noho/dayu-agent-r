# Phase 12.5 Slice 4 Re-Review: LLM Compactor Structured JSON Rewrite (Repair Pass)

## 0. Review Metadata

- Review agent: AgentMiMo
- Date: 2026-05-22
- Gate: Phase 12.5 Slice 4 repair re-review
- Prior review: `docs/reviews/phase12-5-slice4-code-review-mimo-20260522.md`
- Baseline: HEAD=e0cc8a1
- Changed files: `dayu/host/llm_compaction.py`, `tests/host/test_llm_compaction.py`, `dayu/host/README.md`, `dayu/host/compaction_budget.py` (deleted)

## 1. Verdict

**PASS.** All identified findings are fixed. No new blocking issues introduced.

## 2. Finding Verification

### MiMo F1 [Low] Stale docstring — FIXED

**Evidence:** `_estimate_preserved_context_tokens` docstring now reads:
```
该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，基于保留
引用占比、当前输入和 post-compact 系统提示保守估算 compact 后预算。
```
No reference to "旧 verified/tool fact 预算 helper" remains.

### DS F1 [Medium] compaction_budget.py stale dependency — FIXED

**Evidence:**
- `dayu/host/compaction_budget.py` deleted (file no longer exists).
- `rg "estimate_compacted_context_budget|from .*compaction_budget|import .*compaction_budget|compaction_budget\." dayu tests` returns no hits (controller verified).
- `llm_compaction.py` now imports `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` from `dayu.host.context_budget` and estimates in-module.

### DS F2 [Medium] budget_after_compact only counted episode.goal — FIXED

**Evidence:** `_budget_after_compact` signature now accepts `(request, episode, pinned_patch, fact_candidates, preserve_items)` and delegates to `_structured_output_texts()` which collects:
- `episode.episode_title`, `episode.goal`, `episode.completed_actions`, `episode.confirmed_fact_summaries`, `episode.user_constraints`, `episode.open_questions`, `episode.next_step`
- `_pinned_patch_texts(pinned_patch)` covering `current_goal.value`, `confirmed_subjects.value`, `user_constraints.value`, `open_questions.value`
- Each `fact_candidate.claim_text`
- Each `preserve_item.label` and `preserve_item.text`

Budget = `structured_output_tokens + preserved_tokens` (both text-based and proportional max).

### DS F3 [Low] System prompt estimate naming — FIXED

**Evidence:** Two constants now clearly separated:
- `_SYSTEM_PROMPT` (line 76): actual compactor system prompt, used in `_agent_request` at line 231.
- `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE` (line 87): post-compact budget estimation text, used in `_estimate_preserved_context_tokens` at line 1119.

Docstring correctly says "post-compact 系统提示" not "compactor 系统提示".

### DS F6 [Low] Budget test for structured output text growth — FIXED

**Evidence:** New test `test_llm_context_compactor_budget_counts_structured_output_text`:
- Creates short candidate with `claim_text="short fact"`, `minimum_preserve_text="short preserve"`.
- Creates long candidate with `claim_text="material fact " * 120`, `minimum_preserve_text="continuity item " * 70`.
- Asserts `episode.goal` unchanged between both.
- Asserts `long_candidate.budget_after_compact > short_candidate.budget_after_compact`.

### F4/F5 (Info, from prior review) — Deferred, agreed

- F4 (`_MIN_SUMMARY_LENGTH` naming): Cosmetic, functionally correct. Deferred.
- F5 (`_range_tuple` max_items bound): Loose but non-blocking. Deferred.

## 3. No New Issues

- No `Any`, `object`, or untyped signatures introduced.
- No `hasattr`/`getattr` usage.
- No compatibility wrappers or old-name references.
- `_SYSTEM_PROMPT` correctly used for actual compactor prompt; `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE` correctly used for budget estimation only.
- README wording updated to reflect expanded budget coverage (structured summary text, pinned patch text, fact claim, minimum preserve text, post-compact system prompt).

## 4. Validation Results

- `pytest tests/host/test_llm_compaction.py` — 14/14 passed
- `pyright dayu/host/llm_compaction.py` — 0 errors, 0 warnings, 0 informations
- `rg "estimate_compacted_context_budget|compaction_budget"` — no hits (controller verified)
