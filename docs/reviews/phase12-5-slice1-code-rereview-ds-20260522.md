# Phase 12.5 Slice 1 Code Re-Review — AgentDS

- **Gate**: Phase 12.5 Slice 1 code re-review (post-fix)
- **Role**: Independent code review agent (AgentDS). Re-review only. No modifications.
- **Original reviews**: `phase12-5-slice1-code-review-mimo-20260522.md`, `phase12-5-slice1-code-review-ds-20260522.md`
- **Controller adjudication**: `phase12-5-slice1-code-review-controller-adjudication-20260522.md`
- **Date**: 2026-05-22

## Re-Review Scope

Verify S1-F1 (controller-accepted MiMo S1-02) is fixed and no new blocking issue was introduced.

## Adjudication Mandate

Controller required fix (excerpt):

- Rename `stable:verified_facts` to `stable:evidence_backed_facts`
- Rename the local helper / docstring text from verified/tool-verified wording to evidence-backed wording
- Update focused `tests/host/test_run_input_builder.py` references for the block id / diagnostic id if they fail due to the rename
- Do not implement Slice 5 rendering semantics

## S1-F1 Fix Verification

### 1. Block ID Rename (`dayu/host/run_input.py:1618`)

**Before**: `block_id="stable:verified_facts"`
**After**: `block_id="stable:evidence_backed_facts"`

→ **FIXED.**

### 2. Function Rename (`dayu/host/run_input.py:1720`)

**Before**: `def _memory_verified_fact_message(`
**After**: `def _memory_evidence_backed_fact_message(`

→ **FIXED.**

### 3. Docstring / Message Text Rename

| Location | Before | After | Status |
|---|---|---|---|
| `run_input.py:1723` | `tool-verified facts memory block` | `evidence-backed facts memory block` | **FIXED** |
| `run_input.py:1725` | `verified fact 元组` | `evidence-backed fact 元组` | **FIXED** |
| `run_input.py:1731` | `Memory tool-verified facts:` | `Memory evidence-backed facts:` | **FIXED** |

### 4. Test Updates (`tests/host/test_run_input_builder.py`)

| Line | Before | After | Status |
|---|---|---|---|
| 122 | `VerifiedFactView` | `EvidenceBackedFactView` | **FIXED** |
| 509 | `Memory tool-verified facts:` | `Memory evidence-backed facts:` | **FIXED** |
| 548 | `Memory tool-verified facts:` | `Memory evidence-backed facts:` | **FIXED** |
| 555 | `stable:verified_facts` | `stable:evidence_backed_facts` | **FIXED** |
| 685 | `stable:verified_facts` | `stable:evidence_backed_facts` | **FIXED** |
| 1110 | `max_verified_facts=16` | `max_evidence_backed_facts=16` | **FIXED** |
| 1223-1247 | `verified_facts=`, `VerifiedFactView(`, `TOOL_VERIFIED`, `TOOL_VERIFIED_FACT` | `evidence_backed_facts=`, `EvidenceBackedFactView(`, `EVIDENCE_BACKED`, `EVIDENCE_BACKED_FACT` | **FIXED** |
| 1322, 1392 | `verified_facts=` | `evidence_backed_facts=` | **FIXED** |
| 1361 | `verified_facts=()` | `evidence_backed_facts=()` | **FIXED** |

### 5. Slice 5 Rendering Semantics NOT Introduced

`_memory_evidence_backed_fact_message()` still renders in the existing digest-only format (`fact=...`). No `claim_text`, `evidence_refs`, or `evidence_kind` fields were added to the message body.

→ **FIXED** (correctly deferred).

## New File in Diff: `dayu/host/durable/schema.py`

The fix introduced changes to `dayu/host/durable/schema.py` (not in the original Slice 1 diff):

| Line | Before | After |
|---|---|---|
| 741 | `'verified_fact'` | `'evidence_backed_fact'` |
| 749 | `'tool_verified'` | `'evidence_backed'` |

**Assessment**: This is a necessary cascade of the enum/constant renames (`_ITEM_KIND_EVIDENCE_BACKED_FACT`, `MemoryClaimStatus.EVIDENCE_BACKED`). The SQL CHECK constraints contain literal string values that must match the renamed constants; without this change, inserting new rows with renamed `item_kind` / `claim_status` values would fail SQL validation. The change is minimal (4 lines) and introduces no new semantics.

Technically `schema.py` is not in the Slice 1 allowed files list, but the change is a direct type-safety consequence of the rename, analogous to how `run_input.py` needed import/type fallout changes. It does not expand Slice 1 scope.

**Verdict**: Non-blocking observation. The change is correct and necessary.

## Remaining Old Terms (Correctly Deferred)

### `tests/host/test_run_input_builder.py`

```
2764: "proposed_verified_fact_refs": [],
2776: "preserved_fact_refs": {"tool_fact_refs": [], "verified_fact_refs": []},
```

These are in `CONTEXT_COMPACTED` event payload fixtures used by compaction-related tests. They belong to Slice 3 (compaction contract rename). Controller explicitly noted: "remaining proposed_verified/preserved_verified refs in test_run_input_builder fixtures belong to later compaction slices unless they break Slice 1 acceptance." They do not break Slice 1 acceptance (tests pass).

### `tests/runtime/test_config_loader.py`

```
579: def test_old_max_verified_facts_key_fails_fast(tmp_path: Path) -> None:
580:     """旧 max_verified_facts 配置 key 必须作为未知字段失败。"""
588:     memory_projection["max_verified_facts"] = max_facts
```

These are in the intentional old-key rejection test. The test must use the old key name to verify it is rejected. Correct.

### `dayu/host/run_input.py`

No remaining old terms in the changed lines. The grep for `stable:verified_facts|_memory_verified_fact_message|tool-verified|Memory tool-verified` returns zero matches.

## Validation Results (Controller Confirmed)

- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_run_input_builder.py` → **74 passed** (was 42 before fix, +32 from test_run_input_builder.py)
- `pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/host/durable/schema.py dayu/runtime/config_loader.py dayu/service/host_assembly.py dayu/host/run_input.py` → **0 errors**

## Findings Summary

| ID | Severity | Description | Status |
|---|---|---|---|
| S1-F1 | MEDIUM | `stable:verified_facts` block_id and RunInputBuilder naming | **FIXED** |
| — | LOW | `schema.py` CHECK constraint update (necessary cascade, not in plan's allowed files) | **OBSERVATION** (non-blocking) |
| — | INFO | Remaining `proposed_verified_fact_refs` / `verified_fact_refs` in test_run_input_builder.py fixtures | **DEFERRED** to Slice 3 |
| — | INFO | Remaining old terms in test_config_loader.py | **INTENTIONAL** (old-key rejection tests) |

## Verdict

**PASS.** S1-F1 is fully fixed. No new blocking issues introduced. All controller-mandated renames are verified correct. Validation passes cleanly (74 tests, 0 pyright errors). The `schema.py` CHECK constraint update is a minimal necessary cascade and does not introduce scope risk. Slice 1 is accepted.
