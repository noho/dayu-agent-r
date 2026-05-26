# Phase 12.5 Slice 1 Re-Review: Contract Rename And Config Schema

- **Gate**: Phase 12.5 Slice 1 code re-review
- **Reviewer**: AgentMiMo
- **Date**: 2026-05-22
- **Original reviews**: `phase12-5-slice1-code-review-mimo-20260522.md`, `phase12-5-slice1-code-review-ds-20260522.md`
- **Controller adjudication**: `phase12-5-slice1-code-review-controller-adjudication-20260522.md`

## 1. S1-F1 Fix Verification

Controller-accepted finding S1-F1 required renaming `stable:verified_facts` block id and related naming in `dayu/host/run_input.py`.

### Fix Evidence

| Required Change | Status | Evidence |
|---|---|---|
| `stable:verified_facts` → `stable:evidence_backed_facts` | **FIXED** | `run_input.py:1618` (diff) |
| `_memory_verified_fact_message` → `_memory_evidence_backed_fact_message` | **FIXED** | `run_input.py:1720` |
| docstring "tool-verified facts" → "evidence-backed facts" | **FIXED** | `run_input.py:1723` |
| message text "Memory tool-verified facts:" → "Memory evidence-backed facts:" | **FIXED** | `run_input.py:1731` (diff) |
| test references updated | **FIXED** | `test_run_input_builder.py:506,545,555,685,1110,1223,1322,1361,1389` |

Fix is complete and correct.

## 2. New Changes Beyond S1-F1

### 2.1 `dayu/host/durable/schema.py` CHECK Constraint Update

**New in this diff** (not in original review): SQL DDL CHECK constraints updated:

- `item_kind` CHECK: `'verified_fact'` → `'evidence_backed_fact'` (line 741)
- `claim_status` CHECK: `'tool_verified'` → `'evidence_backed'` (line 751)

This is necessary schema fallout from the `durable/memory.py` constant rename. Without it, the durable storage would reject rows with the new item kind values. Correct and required.

### 2.2 `tests/host/test_run_input_builder.py` Expanded Scope

Beyond the S1-F1 block id fix, this file now includes:
- Import: `VerifiedFactView` → `EvidenceBackedFactView`
- Policy constructor: `max_verified_facts` → `max_evidence_backed_facts`
- Snapshot field: `verified_facts` → `evidence_backed_facts`
- Enum values: `TOOL_VERIFIED` → `EVIDENCE_BACKED`, `TOOL_VERIFIED_FACT` → `EVIDENCE_BACKED_FACT`
- Fixture data: `VerifiedFactView(...)` → `EvidenceBackedFactView(...)`

All correct. This is the "focused compile/type fallout in `tests/host/*`" allowed by plan §7 Slice 1.

## 3. Remaining Old Names — Classified

Two remaining old-name references in `test_run_input_builder.py`:

| Location | Content | Classification |
|---|---|---|
| Line 2764 | `"proposed_verified_fact_refs": []` | Compaction payload fixture — belongs to Slice 3/4 per plan §7 |
| Line 2776 | `"verified_fact_refs": []` | Compaction payload fixture — belongs to Slice 3/4 per plan §7 |

Per controller note: "remaining proposed_verified/preserved_verified refs in test_run_input_builder fixtures belong to later compaction slices unless they break Slice 1 acceptance." These do not break Slice 1 acceptance — they are compaction payload keys, not memory contract keys.

`tests/runtime/test_config_loader.py:579-596` — `test_old_max_verified_facts_key_fails_fast` intentionally uses the old key name as test input to verify rejection. This is correct test design, not a stale term.

## 4. Stale-Term Search: Slice 1 Production Files

Searched all Slice 1 allowed production files for `verified_facts|max_verified_facts|VerifiedFact|verified_fact|TOOL_VERIFIED`:

| File | Matches |
|---|---|
| `dayu/host/memory.py` | 0 |
| `dayu/host/durable/memory.py` | 0 |
| `dayu/host/run_input.py` | 0 |
| `dayu/runtime/config_loader.py` | 0 |
| `dayu/service/host_assembly.py` | 0 |
| `dayu/config/execution_profiles.json` | 0 |
| `dayu/README.md` | 0 |
| `dayu/host/README.md` | 0 |

All Slice 1 production files are clean.

## 5. Validation Confirmed

Controller reports:
- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_run_input_builder.py` → **74 passed**
- `pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/host/durable/schema.py dayu/runtime/config_loader.py dayu/service/host_assembly.py dayu/host/run_input.py` → **0 errors**

## 6. No New Blocking Issues

The S1-F1 fix introduced no new correctness, scope, or compatibility issues. The `durable/schema.py` change is necessary schema fallout. The expanded test file changes are within allowed scope.

## 7. Verdict

**PASS.** S1-F1 is fixed. No new blocking issues. All Slice 1 production files are clean of old verified terms. Validation passes. Slice 1 should be accepted.
