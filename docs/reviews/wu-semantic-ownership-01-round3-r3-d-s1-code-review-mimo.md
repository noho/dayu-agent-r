# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review — AgentMiMo

## Review Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review`
- Reviewer: `AgentMiMo`
- Timestamp: 2026-07-13
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-controller-validation.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`

## Scope And Validation Check

### Diff Scope

17 files changed: 15 production + 2 test (plus 1 new test file). All files are within accepted S1 allowlist. No Host/Engine, R3-E, tool-security, upload/download security, 6-K dual-engine routing, or full DocumentMeta migration scope creep detected.

### Validation Commands (Verified Independently)

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
72 passed, 3 warnings

pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
4 passed, 45 deselected, 3 warnings

python -m pyright dayu/fins/domain/financial_result_contract.py dayu/fins/domain/xbrl_result_contract.py dayu/fins/tools/result_types.py dayu/fins/tools/read_runtime.py dayu/fins/tools/read_runtime_helpers.py
0 errors, 0 warnings, 0 informations
```

## Review Focus Areas — Evidence-Based Analysis

### 1. Field-Level Data-Flow (processor → domain validator → read projection → result type → LLM description)

**Financial statement path:**
- `processor.get_financial_statement()` returns domain `FinancialStatementResult` (all 9 fields required).
- `read_runtime.py:1621-1650` calls `validate_financial_statement_result_payload()` then copies all fields to public `FinancialStatementResult` (result_types.py).
- Public result declares all fields required: `ticker/document_id/citation/statement_type/periods/rows/currency/units/scale/data_quality/reason/statement_locator`.
- No shadow TypedDict, no cast bag, no optional field copy, no locator fallback.

**XBRL query path:**
- `processor.query_xbrl_facts()` returns `XbrlFactsResult` (domain: `query_params/facts/total/data_quality/reason`).
- `read_runtime.py:1730-1762` catches `XbrlQueryExecutionError`, validates via `_normalize_xbrl_query_payload`, projects to `XbrlQueryResult`.
- `NormalizedXbrlQueryPayload` (read_runtime_helpers.py) adds `deduped_fact_count` and copies `data_quality/reason` from validated result.
- Public `XbrlQueryResult` (result_types.py) required fields: `ticker/document_id/citation/query_params/facts/total/deduped_fact_count/data_quality/reason`.

**Verdict: PASS.** Field-level data-flow is lossless. Producer-owned fields propagate through validation to public result without recomputation or fallback.

### 2. Producer-Owned periods/scale/data_quality/reason/statement_locator

**Evidence:**
- `financial_result_contract.py:60-88`: `FinancialStatementResult` TypedDict declares all fields required.
- `financial_result_contract.py:189-245`: `validate_financial_statement_result_payload` fail-closed validator.
- `read_runtime.py:1621-1650`: read projection copies validated fields verbatim; no `.get()` fallback, no default value injection.
- All processor callers (sec_processor, bs_report_form_common, bs_six_k_processor, html_financial_statement_common, six_k_form_common) construct complete result dicts with all required fields.

**Verdict: PASS.** Fields are producer-owned. Read runtime validates and copies, never recomputes.

### 3. XBRL Quality/Reason Matrix

Verified against plan's state matrix:

| Condition | Processor result | Tool-visible result | Correct? |
| --- | --- | --- | --- |
| XBRL unavailable | `partial/xbrl_not_available` | successful degraded value | ✅ |
| >=1 success, 0 rows, 0 failures | `xbrl/None`, `total=0` | legitimate empty success | ✅ |
| >=1 success, >=1 failure | `partial/query_partially_failed` | successful degraded value | ✅ |
| all attempted fail | `XbrlQueryExecutionError` raised | `FinsReadBusinessError(xbrl_query_failed)` | ✅ |
| concepts empty | `ValueError` raised | invalid_argument | ✅ |

**Direct evidence:**
- `sec_xbrl_query.py:472-534`: `_query_facts_rows` returns `XbrlConceptQuerySummary` with explicit `attempted/successful/failed_concepts`.
- `sec_processor.py:709-757` and `bs_report_form_common.py:325-342`: both callers use `summary.failed_concepts` to determine `data_quality/reason`.
- `xbrl_result_contract.py:102-110`: validator rejects `extracted` for XBRL, rejects `xbrl_not_available` with non-empty facts, requires partial to have reason.
- `read_runtime.py:1730-1745`: catches `XbrlQueryExecutionError`, maps to `FinsReadBusinessError(ErrorCode.XBRL_QUERY_FAILED)`.

**Verdict: PASS.** Matrix is consistent across all five states.

### 4. deduped_fact_count Ownership

**Producer/domain boundary:**
- `XbrlFactsResult` (xbrl_result_contract.py): fields are `query_params/facts/total/data_quality/reason`. No `deduped_fact_count`.
- `validate_xbrl_facts_result_payload` rejects raw payloads containing `deduped_fact_count` (line 89).

**Read projection:**
- `NormalizedXbrlQueryPayload` (read_runtime_helpers.py:1420-1430): required `deduped_fact_count`.
- `_normalize_xbrl_query_payload` always writes `deduped_fact_count=len(deduped_facts)` (line 1472).
- `XbrlQueryResult` (result_types.py): required `deduped_fact_count`.

**Raw `total` protection:**
- `normalized_payload["total"] = validated.total` (read_runtime_helpers.py:1471) — preserves producer raw count.
- `deduped_fact_count` cannot overwrite `total`; they are separate fields.

**Verdict: PASS.** `deduped_fact_count` is exclusively read-owned. Producer/domain validator rejects it. Raw `total` is preserved.

### 5. LLM-Facing Description Self-Sufficiency

**Direct evidence (fins_tools.py:853-860, 930-938):**
- `get_financial_statement` description: explains `periods` (period_end/fiscal_year/fiscal_period), `scale` (units/thousands/millions/billions/null), `units` (currency/measurement unit), `data_quality` (xbrl/extracted/partial), `reason`.
- `query_xbrl_facts` description: explains `total` (去重前), `deduped_fact_count` (去重后), `data_quality=xbrl` (正常执行, total=0 = 没有匹配 fact), `partial` (XBRL 不可用或部分概念查询失败).

**Forbidden terms scan:**
- No `Host`, `Engine`, `event_id`, `digest`, `cursor`, `SSRF`, `allowlist` in either description.

**Test verification:** `test_financial_tool_descriptions_explain_owner_fields` in `test_fins_storage_provider.py` asserts all required tokens and forbidden terms.

**Verdict: PASS.** Descriptions are self-explanatory, business-readable, and free of internal governance terms.

### 6. Test Quality — Owner-Level Contract Assertions

**Positive evidence:**
- `test_financial_read_contracts.py`: characterizes edgartools `execute()` boundary, quality/reason matrix, scale truth, XBRL caller mapping, HTML/OCR scale/units, OCR income-summary fallback.
- `test_fins_read_runtime.py`: tests `deduped_fact_count` always projected, producer dedup field rejected, raw total preserved.
- `test_read_runtime_semantic_ownership_guards.py`: tests all-failed → typed business failure, financial result round-trip with owner fields.
- `test_fins_storage_provider.py`: tests tool descriptions, process-target XBRL failure envelope.

**Finding (non-blocking):** `test_get_financial_statement_rejects_missing_or_non_list_rows` first fixture has `rows=[]` + `data_quality="partial"` + `reason="statement_empty"`. Domain validator accepts this (correct — empty rows with partial quality and reason is valid). Test catches `ValueError` from downstream `rows` iteration, not from contract validation. Test name implies contract-level rejection but actual failure is incidental.

**Verdict: PASS (with non-blocking residual).** Tests generally assert owner-level contracts, not incidental behavior.

### 7. Scope Creep Check

- No tool-security changes.
- No R3-E changes.
- No upload/download security schema changes.
- No 6-K dual-engine routing changes.
- No full DocumentMeta migration.
- No compatibility re-exports, wrappers, or facades.
- No `filing_semantics.py` changes (S1 reuses existing `FiscalPeriod`/`FinancialDataQuality`).

**Verdict: PASS.** Implementation stays within S1 scope.

## Findings

### F1 — Non-blocking: Test fixture passes domain validator; test catches downstream error

**Severity:** non-blocking (test quality, no production impact)

**File:line:** `tests/fins/test_read_runtime_semantic_ownership_guards.py:709-767`

**Direct evidence:** First parametrized fixture `{rows: [], data_quality: "partial", reason: "statement_empty"}` passes `validate_financial_statement_result_payload()` (verified via direct invocation). Test catches `ValueError` from `read_runtime.py`'s `for _row in statement_payload["rows"]` iteration, which matches `"rows"` regex incidentally.

**Failure mode:** Test does not assert the owner-level contract it names. If a future change makes `rows` iteration succeed on empty list without raising, the test would silently pass without verifying contract enforcement.

**Required fix:** None for S1 pass. Optionally: add a direct `validate_financial_statement_result_payload` assertion for the "rows not list" case, or adjust the fixture so the first parametrized case actually fails domain validation.

**Test impact:** No — test still passes and exercises the read path.

## Non-Blocking Residuals

1. **`_is_json_value` duplication:** Identical implementation in `financial_result_contract.py:386-407` and `xbrl_result_contract.py:143-156`. Could be extracted to a shared domain helper. Not a semantic ownership issue.

2. **Duplicate import lines:** `read_runtime_helpers.py:28-31` has two separate imports from `xbrl_result_contract`. Could be consolidated. Not a correctness issue.

## Final Decision

**PASS.** All seven review focus areas verified correct. Field-level data-flow is lossless. Producer-owned fields propagate without fallback/shadow/extra bag. XBRL quality/reason matrix is consistent across all five states. `deduped_fact_count` is exclusively read-owned with raw `total` protected. LLM-facing descriptions are self-explanatory and free of internal terms. Tests assert owner-level contracts. No scope creep detected. One non-blocking test quality residual identified.
