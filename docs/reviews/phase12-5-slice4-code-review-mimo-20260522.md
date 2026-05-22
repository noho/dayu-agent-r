# Phase 12.5 Slice 4 Code Review: LLM Compactor Structured JSON Rewrite

## 0. Review Metadata

- Review agent: AgentMiMo
- Date: 2026-05-22
- Gate: Phase 12.5 Slice 4 code review
- Plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- Design source: `docs/host/design.md`
- Baseline: HEAD=e0cc8a1
- Changed files: `dayu/host/llm_compaction.py`, `tests/host/test_llm_compaction.py`, `dayu/host/README.md`

## 1. Verdict

**Accept with minor fix.** Slice 4 implementation is structurally correct. One stale docstring should be fixed before merge.

## 2. Findings

### F1 [Low] Stale docstring references old budget helper name

**File:** `dayu/host/llm_compaction.py` (diff line ~1013, `_estimate_preserved_context_tokens` docstring)

**Evidence:**
```python
该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，避免 LLM
compactor 继续穿过旧 verified/tool fact 预算 helper。
```

**Issue:** "旧 verified/tool fact 预算 helper" references the removed `estimate_compacted_context_budget` from `compaction_budget.py`. The comment is factually stale — the old helper has been removed and replaced by the new inline estimation. The wording implies the old helper still exists and needs avoidance, which is misleading.

**Fix:** Replace with:
```
该估算只依赖 Slice 3 冻结后的 ``CompactionRequest`` 字段，基于保留引用占比与
文本片段 token 估算得出 compact 后预算。
```

### F2 [Info] `_MIN_SUMMARY_LENGTH` name semantically mismatched

**File:** `dayu/host/llm_compaction.py:67`

**Evidence:** `_MIN_SUMMARY_LENGTH = 1` — used in `_parse_proposal` as `len(raw) < _MIN_SUMMARY_LENGTH` to reject empty proposals.

**Issue:** Name says "summary" but context is now JSON proposal. Functional correctness is not affected (value=1 just rejects empty string, which is correct). Name is a carry-over from the old plain-text path.

**Fix (optional):** Rename to `_MIN_PROPOSAL_LENGTH = 1` for clarity.

### F3 [Info] `_range_tuple` max_items bound is generous

**File:** `dayu/host/llm_compaction.py` (`_range_tuple` function)

**Evidence:**
```python
values = _required_sequence(proposal, key, max_items=len(allowed_refs))
```

**Issue:** `max_items=len(allowed_refs)` allows up to N ranges where N is the number of input event refs. In practice, compact ranges should be far fewer. Not a correctness issue — `CompactInputRange.__post_init__` validates non-empty fields — but the bound is loose.

**Fix:** No action required. Tighter bounds can be added in a future compactor quality pass.

## 3. Positive Observations

### 3.1 Pure text summary path fully removed

Old `_candidate_from_summary(request, summary)` is replaced by `_candidate_from_final_answer(request, outcome.content)`. Plain text final answers now raise `LLMCompactionProposalError("compactor proposal is not valid JSON: ...")`. No silent acceptance path remains.

### 3.2 Parser uses typed constructors from Slice 3 shared constants

`_evidence_backed_fact_candidates()` constructs `EvidenceBackedFactCandidate` instances, whose `__post_init__` enforces:
- `claim_text` non-empty and <= `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS` (2000)
- `evidence_refs` non-empty and <= `MAX_EVIDENCE_REFS_PER_FACT` (16)
- `attributes` JSON <= `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS` (4096)

Similarly, `MinimumPreserveItemCandidate.__post_init__` enforces `text` <= `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS` (1200) and `source_refs` <= `MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM` (16).

No bypass of Host accept barrier. No duplicate business semantic validation.

### 3.3 Ref validation correctly scoped

| Ref type | Allowed source | Validator |
|---|---|---|
| fact `evidence_refs` | `request.accepted_evidence_refs` | `_bounded_known_refs` in `_evidence_backed_fact_candidates` |
| summary `confirmed_fact_refs` | `request.evidence_backed_fact_refs` | `_bounded_known_refs` in `_episode_summary_candidate` |
| summary `tool_finding_refs` | `request.accepted_evidence_refs` | `_bounded_known_refs` in `_episode_summary_candidate` |
| preserve `source_refs` | `request.input_event_refs` | `_bounded_known_refs` in `_minimum_preserve_item_candidates` |
| `preserved_input_event_refs` | `request.input_event_refs` | `_bounded_known_refs` in `_candidate_from_final_answer` |
| `preserved_accepted_evidence_refs` | `request.accepted_evidence_refs` | `_bounded_known_refs` in `_candidate_from_final_answer` |
| `preserved_evidence_backed_fact_refs` | `request.evidence_backed_fact_refs` | `_bounded_known_refs` in `_candidate_from_final_answer` |
| range endpoints | `request.input_event_refs` | `_bounded_known_refs` in `_range_tuple` |

No ref can point to user input, assistant summary, or non-existent evidence as fact evidence.

### 3.4 No Any/object/untyped signatures, no hasattr/getattr, no compatibility wrappers

All function signatures use explicit types. `cast(Mapping[str, JsonValue], parsed)` at line 471 is a safe narrowing after `isinstance(parsed, Mapping)` check — pyright accepts it. No `hasattr`/`getattr` usage. No old-name aliases or fallback reads.

### 3.5 Budget estimation self-contained

`_budget_after_compact` now estimates in-module using `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` from `context_budget`, removing the dependency on `compaction_budget.estimate_compacted_context_budget`. The estimation covers system prompt, current input, preserved refs, and proportional budget retention. Conservative by design (takes max of text-based and proportional estimates).

### 3.6 Tests cover required smoke behaviors

| Required behavior | Test |
|---|---|
| Valid structured JSON -> CompactionCandidate | `test_llm_context_compactor_maps_final_answer_to_candidate` |
| Plain text rejected | `test_llm_context_compactor_rejects_empty_plain_text_or_non_final_output` |
| Malformed JSON rejected | `test_llm_context_compactor_rejects_malformed_and_schema_invalid_json` |
| Schema-invalid JSON rejected | `test_llm_context_compactor_rejects_malformed_and_schema_invalid_json` |
| Overlong claim_text rejected | `test_llm_context_compactor_rejects_overlong_structured_text` |
| Overlong minimum preserve text rejected | `test_llm_context_compactor_rejects_overlong_structured_text` |
| Non-accepted evidence refs rejected | `test_llm_context_compactor_rejects_non_accepted_evidence_refs` |
| Truncated output rejected | `test_llm_context_compactor_rejects_truncated_final_output` |
| Host-owned refs preserved | `test_llm_context_compactor_preserves_host_owned_refs_and_evidence` |

### 3.7 README wording sync correct

`dayu/host/README.md` change: "final summary" -> "final proposal". Scope-appropriate, no stale terminology.

## 4. Residual Risks

- **LLM fact extraction quality:** Model-dependent; not a code review concern. Covered by compactor quality pass in later phases.
- **Individual fact/minimum-preserve item schema validation in LLM compaction layer:** Tests validate overlong text rejection via shared constants, but do not individually test empty `claim_text`, empty `evidence_refs`, invalid `evidence_kind` enum, or empty `source_refs` at the LLM compaction layer. These are covered by Slice 3 `__post_init__` constructors, but a schema-invalid-fact-candidate test at the LLM layer would strengthen confidence. Not blocking.
- **Budget estimation accuracy:** New inline estimation replaces `estimate_compacted_context_budget`. Conservative (max of text-based and proportional). Accuracy will be validated in integration smoke (Slice 7).

## 5. Validation Results

- `pytest tests/host/test_llm_compaction.py` — 13/13 passed
- `pyright dayu/host/llm_compaction.py` — 0 errors, 0 warnings, 0 informations
