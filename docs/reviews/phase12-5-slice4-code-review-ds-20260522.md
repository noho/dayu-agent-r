# Phase 12.5 Slice 4 Code Review: LLM Compactor Structured JSON Rewrite

## 0. Review Metadata

- Review agent: AgentDS
- Date: 2026-05-22
- Gate: Phase 12.5 Slice 4 code review
- Plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- Design source: `docs/host/design.md`
- Baseline: HEAD=e0cc8a1 `gateflow: accept phase 12.5 slice 3`
- Changed files: `dayu/host/llm_compaction.py`, `tests/host/test_llm_compaction.py`, `dayu/host/README.md`

## 1. Verdict

**Accept with findings.** Slice 4 core contract is structurally correct: plain-text path removed, strict JSON enforced, typed constructors gate all value validation. Three medium-severity findings need attention before Slice 5/7 integration, but none block this slice's stop condition.

## 2. Adversarial Contract Smoke

### 2.1 Structured JSON → CompactionCandidate (Pass)

Line 380-447, `_candidate_from_final_answer()`: Full mapping path from raw JSON through `_parse_proposal` → per-section constructors → `CompactionCandidate`. Evidence refs are bounded by `request.accepted_evidence_refs` (line 569-572), source refs bounded by `request.input_event_refs` (line 606-609), and all typed constructors (`EvidenceBackedFactCandidate`, `MinimumPreserveItemCandidate`, `EpisodeSummaryCandidate`) enforce their own `__post_init__` validation. Any `KeyError | TypeError | ValueError` from parsing or construction becomes `LLMCompactionProposalError` (line 443-447), which is a proposal failure — no `CompactionCandidate` is produced.

### 2.2 Plain Text / Malformed / Schema-Invalid Rejected (Pass)

- Plain text: `_parse_proposal` line 459 rejects empty text (`len(raw) < _MIN_SUMMARY_LENGTH`). Non-JSON string raises `JSONDecodeError` → `LLMCompactionProposalError` (line 463-465).
- Malformed JSON: `json.loads` raises `JSONDecodeError` → `LLMCompactionProposalError` (line 463-465).
- Schema-invalid: `_REQUIRED_PROPOSAL_KEYS` check at lines 472-476 rejects any object missing required top-level keys.
- Truncated output: `finish_reason == LENGTH` rejected at line 203-206 before parsing.
- Tests: `test_llm_context_compactor_rejects_empty_plain_text_or_non_final_output`, `test_llm_context_compactor_rejects_malformed_and_schema_invalid_json`, `test_llm_context_compactor_rejects_truncated_final_output` — all pass.

### 2.3 Optional Fields Not Wrongly Rejected (Pass)

- `EpisodeSummaryCandidate.next_step`: `_optional_string_or_none` (line 515) — allows missing, null, or string.
- `PinnedPatchOperation.MISSING` / `CLEAR` with `value: null`: `_validate_patch_value` (line 711-716) explicitly allows null for MISSING/CLEAR.
- `retained_current_user_input_ref`: `_retained_current_user_input_ref` (line 637-639) explicitly allows `null` (returns `None`).
- `attributes` as empty `{}`: `_required_mapping` accepts any `Mapping`, including empty. `EvidenceBackedFactCandidate.__post_init__` validates JSON size ≤ 4096 chars, empty `{}` is 2 chars — passes.
- Empty candidate lists: `_required_sequence` at line 823 allows `len(value) == 0` (only checks `> max_items`). Empty `evidence_backed_fact_candidates: []` and `minimum_preserve_item_candidates: []` produce empty tuples.

### 2.4 Non-Evidence Refs Rejected (Pass)

`_bounded_known_refs` (line 938-957) rejects any ref not in `allowed_refs`. For fact candidates, `allowed_refs=request.accepted_evidence_refs` — no user input, assistant answer, summary, or working-assumption ref can pass. For minimum preserve items, `allowed_refs=request.input_event_refs` — items can only reference compact input events.

## 3. Findings

### F1 [Medium-High] `compaction_budget.py` Dead Code with Stale Fields

**File:** `dayu/host/compaction_budget.py` (entire file, 117 lines)

**Evidence:**
- Lines 86-88 reference `request.tool_fact_refs` and `request.verified_fact_refs` — these `CompactionRequest` fields were renamed/removed in Slice 3.
- Lines 103-104: same stale field references in `_estimate_preserved_share_from_budget`.
- Zero imports from any `.py` file (confirmed: `rg "from.*compaction_budget|import.*compaction_budget|compaction_budget\." --glob '*.py'` → no matches).
- `llm_compaction.py` removed its import of `estimate_compacted_context_budget` from this module and inlined its own private `_budget_after_compact`, `_estimate_preserved_context_tokens`, `_preserved_ref_texts`, `_estimate_preserved_share_from_budget`.

**Risk:** If any future code accidentally imports `estimate_compacted_context_budget` from `compaction_budget.py`, it will raise `AttributeError` at runtime because `CompactionRequest` no longer has `tool_fact_refs` or `verified_fact_refs`. Dead code with stale field references is a latent runtime crash.

**Fix:** Delete `dayu/host/compaction_budget.py`. It has zero callers and its field references are stale. The replacement logic lives in `llm_compaction.py` (private helpers) and `fake_compaction.py` (independent test helper). This aligns with plan §4.1: "no compatibility code, no re-export."

**Plan reference:** Plan §4.1 命名迁移: "禁止新增旧名 alias、旧名 property、旧 key fallback、旧 JSON key 兼容读取。旧库按全新 schema 起库处理。"

---

### F2 [Medium] `_budget_after_compact` Only Counts `episode.goal`, Not Full Compact Output

**File:** `dayu/host/llm_compaction.py`, lines 440, 996-1006

**Evidence:**
```python
budget_after_compact=_budget_after_compact(
    request, episode.goal  # ← only goal text, not full summary
),
```
```python
def _budget_after_compact(request: CompactionRequest, summary: str) -> int:
    summary_tokens = _estimate_text_tokens(summary)
    preserved_tokens = _estimate_preserved_context_tokens(request)
    return summary_tokens + preserved_tokens
```

**Issue:** The "summary" token estimate only counts `episode.goal` (typically ~20-50 chars). It does NOT count:
- `episode_title`
- `completed_actions` text
- `confirmed_fact_summaries` text
- `user_constraints` text
- `open_questions` text
- `next_step` text
- Fact candidate `claim_text` entries
- Minimum preserve `text` entries
- Pinned patch `value` fields

A realistic compact output could be 500-2000+ characters of new content beyond `episode.goal`, representing 150-600+ estimated tokens not accounted for.

**Hard threshold bypass risk:** The check in `compaction_operation.py:159-162` compares `candidate.budget_after_compact >= request.budget_before_compact.hard_threshold_tokens`. If the estimate is too low, a compact candidate could pass the hard threshold recheck when post-compact context actually exceeds the threshold.

**Mitigating factors:**
1. `_estimate_preserved_share_from_budget` (line 1051-1071) provides a proportional floor: `ceil(estimated_input_tokens * retained_count / source_count)`. If most refs are retained, this can dominate `typed_fragment_tokens`.
2. `max(typed_fragment_tokens, preserved_share)` at line 1028-1030 takes the larger of the two.
3. The check in `compaction_operation.py` provides operational defense — if the estimate is wrong, a subsequent compaction cycle would catch it.
4. The plan calls this a "本地估算" (local estimate), not a precise measurement.

**Fix (not in this slice):** In Slice 5 or 7 integration, consider using the canonical JSON size of the full `CompactionCandidate.to_json()` output as a more accurate proxy, or at minimum include the full `episode_summary_candidate` text fields. Document the current estimation's known gap in the budget estimation comment.

**Plan reference:** Plan §4.8 冻结常量, §7 Slice 4: "compact 后预算按统一 Host token 估算常数计算"

---

### F3 [Medium] `_estimate_preserved_context_tokens` Includes Compactor's System Prompt

**File:** `dayu/host/llm_compaction.py`, lines 1009-1031

**Evidence:**
```python
typed_fragment_tokens = sum(
    _estimate_text_tokens(fragment)
    for fragment in (
        _SYSTEM_PROMPT,  # ← compactor system prompt, NOT post-compact context
        request.current_message_summary.summary_text,
        request.current_message_summary.current_user_input_ref,
        *_preserved_ref_texts(request),
    )
)
```

**Issue:** `_SYSTEM_PROMPT` is the prompt sent TO the compactor LLM. After compaction, the compactor's system prompt is NOT part of the preserved context for the next run. Including it inflates the budget_after_compact estimate, making the estimate more conservative (higher = more likely to fail hard threshold recheck). While this is "safe" for hard threshold enforcement (it errs on the side of rejecting insufficient compaction), it is semantically wrong and introduces unnecessary conservatism that could cause valid compactions to be rejected.

**Fix:** Replace `_SYSTEM_PROMPT` with a separate parameter representing the post-compact system prompt estimate, or accept a `system_prompt` parameter like the old `estimate_compacted_context_budget` did. If a precise post-compact system prompt estimate isn't available at this layer, document the conservative choice explicitly.

---

### F4 [Low] No Test for Empty Candidate Lists

**File:** `tests/host/test_llm_compaction.py`

**Evidence:** `_proposal_json()` always generates exactly 1 fact candidate and 1 minimum preserve item. No test exercises `evidence_backed_fact_candidates: []` or `minimum_preserve_item_candidates: []`.

**Issue:** Empty candidate lists should be valid (no facts extracted, no items to preserve), but this path is untested. The `_required_sequence` function correctly allows `len(value) == 0` (only rejects `> max_items`), and `_evidence_backed_fact_candidates` / `_minimum_preserve_item_candidates` would return `tuple()` (line 585, 622). But without a test, a future change could accidentally break this.

**Fix:** Add a test like `test_llm_context_compactor_accepts_empty_candidate_lists` with `_proposal_json(empty_candidates=True)` that sets both arrays to `[]`.

**Plan reference:** Plan §7 Slice 4 tests: "valid structured JSON final answer maps to CompactionCandidate including fact and minimum preserve candidates" — empty is a valid case of "including."

---

### F5 [Low] No Test for Invalid Enum Values in Structured JSON

**File:** `tests/host/test_llm_compaction.py`

**Evidence:** All tests use valid `evidence_kind: "observed_value"` and `preserve_reason: "needed_for_recent_reference"`. No test passes invalid enum strings.

**Issue:** If the LLM outputs `"evidence_kind": "hallucinated_kind"`, `EvidenceBackedFactKind("hallucinated_kind")` will raise `ValueError`. This is caught by the outer `except (KeyError, TypeError, ValueError) as exc:` and becomes `LLMCompactionProposalError`. Correct behavior, but untested.

**Fix:** Add a test with `evidence_kind="invalid"` and `preserve_reason="invalid"` asserting `LLMCompactionProposalError`.

---

### F6 [Low] Stale Docstring Comment

**File:** `dayu/host/llm_compaction.py`, line ~1013 (`_estimate_preserved_context_tokens` docstring)

**Evidence:**
```python
该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，避免 LLM
compactor 继续穿过旧 verified/tool fact 预算 helper。
```

**Issue:** The phrase "避免 LLM compactor 继续穿过旧 verified/tool fact 预算 helper" is stale. The old helper (`compaction_budget.estimate_compacted_context_budget`) has been removed and replaced. The docstring implies it still exists and must be avoided, which is misleading.

**Fix:** Rewrite to: "该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，使用统一的字符/token 常数进行保守估算。"

**Note:** Also flagged by AgentMiMo review (F1).

---

### F7 [Info] Plan Boundary Compliance (Pass)

| Check | Result | Evidence |
|-------|--------|----------|
| Plain-text path removed | PASS | Lines 202-207 replaced old `_candidate_from_summary` with `_candidate_from_final_answer` |
| No second LLM call | PASS | Single `compact()` call, no extraction loop |
| Provenance governed by EventLog | PASS | `candidate_id` is local diagnostic (`f"llm-compact:{request.run_id}"`); evidence refs from Host-owned `_preservation_evidence` |
| No old verified/tool_fact semantics | PASS | Zero hits for `verified_fact|tool_fact` in `llm_compaction.py` |
| Shared constants used | PASS | `MAX_EVIDENCE_BACKED_FACT_CANDIDATES`, `MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES`, `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS`, `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS` all imported from `dayu.host.compaction` |
| Tests cover all plan-required | PASS | 5 plan-required tests all present and passing (see §2 above) |
| Pyright clean | PASS | 0 errors, 0 warnings |
| README change in scope | PASS | Only 1 word change: "summary" → "proposal" |

### F8 [Info] Test Coverage Analysis

13 tests, all pass. Coverage breakdown:

| Category | Tests | Notes |
|----------|-------|-------|
| Request construction | 2 | `builds_tool_disabled_request`, `does_not_use_thread_bridge` |
| Happy path | 2 | `maps_final_answer_to_candidate`, `budget_counts_preserved_context` |
| Rejection: plain/malformed/schema | 2 | `rejects_empty_plain_text_or_non_final_output`, `rejects_malformed_and_schema_invalid_json` |
| Rejection: overlong text | 1 | `rejects_overlong_structured_text` (both claim_text and min_preserve_text) |
| Rejection: non-evidence refs | 1 | `rejects_non_accepted_evidence_refs` |
| Rejection: truncated | 1 | `rejects_truncated_final_output` |
| Runner behavior | 2 | `applies_runner_timeout`, `uses_runner_retry_policy` |
| Sanitization | 1 | `sanitizes_failed_runner_outcome` |
| Host-owned refs | 1 | `preserves_host_owned_refs_and_evidence` |

Gaps: empty candidate lists (F4), invalid enums (F5). These are covered at the contract layer by `tests/host/test_compaction_contract.py` (Slice 3), so the risk is low.

## 4. Residual Risks

| Risk | Owner | Severity | Notes |
|------|-------|----------|-------|
| `compaction_budget.py` dead code with stale fields | This slice | Medium-High | F1; should be deleted before Slice 5 |
| Budget underestimation due to `episode.goal` only | Slice 7 integration | Medium | F2; known limitation, integration smoke catches severe cases |
| Conservative over-estimate from `_SYSTEM_PROMPT` | Slice 5/7 | Low-Medium | F3; errs on safe side but may cause false rejects |
| Budget estimation accuracy vs real token counts | Slice 7 | Low | No live runner in unit tests; integration smoke validates |
| LLM proposal schema compliance in production | Slice 7 | Model-dependent | Prompt describes schema inline; LLM may deviate. Bounded repair in `compaction_operation.py` handles retry. |

## 5. Slice Stop Condition

Plan §7 Slice 4 stop condition: "If structured JSON parsing / schema validation cannot work within bounded repair attempts, stop and report Blocking Questions For Controller."

**Assessment:** Stop condition NOT triggered. All JSON parsing, schema validation, and value construction work correctly within a single attempt. Bounded repair is handled by `compaction_operation.py` (Slice 3), not by the compactor itself — this is correct separation of concerns.

## 6. Validation

```
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py
→ 13 passed in 0.57s

source .venv/bin/activate && pyright dayu/host/llm_compaction.py
→ 0 errors, 0 warnings, 0 informations
```

## 7. Recommendation

1. **Delete `dayu/host/compaction_budget.py`** (F1) — zero callers, stale fields, latent runtime crash risk.
2. **Fix stale docstring** (F6) — trivial wording cleanup.
3. **F2, F3** — document in budget estimation comments as known limitations for Slice 7 integration validation. Not blockers for this slice.
4. **F4, F5** — optional test additions. Contract-layer tests in Slice 3 provide partial coverage.
