# Phase 12.5 Slice 1 Code Review: Contract Rename And Config Schema

- **Gate**: Phase 12.5 Slice 1 code review
- **Reviewer**: AgentMiMo
- **Approved plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Date**: 2026-05-22

## 1. Scope Compliance

### 1.1 Allowed Files (per plan §7 Slice 1)

| File | In diff | In plan | Status |
|---|---|---|---|
| `dayu/host/memory.py` | Yes | Yes | OK |
| `dayu/host/durable/memory.py` | Yes | Yes | OK |
| `dayu/runtime/config_loader.py` | Yes | Yes | OK |
| `dayu/service/host_assembly.py` | Yes | Yes | OK |
| `dayu/config/execution_profiles.json` | Yes | Yes | OK |
| `tests/runtime/test_config_loader.py` | Yes | Yes | OK |
| `tests/service/test_host_assembly.py` | Yes | Yes | OK |
| `dayu/README.md` | Yes | Conditional (§9) | OK — stale term cleanup |
| `dayu/host/README.md` | Yes | Conditional (§9) | OK — stale term cleanup |

No out-of-scope production files touched. No out-of-scope test files touched.

### 1.2 Import Refactor in `host_assembly.py` / `test_host_assembly.py`

**Finding S1-01 [LOW / out-of-scope cleanup]**: Both `dayu/service/host_assembly.py` and `tests/service/test_host_assembly.py` change import paths: `from dayu.host import ...` becomes `from dayu.host.api import ...`, and `HostToolingOptions` moves to `from dayu.host.tooling import HostToolingOptions`. These symbols ARE still re-exported from `dayu/host/__init__.py`, so the old import paths remain valid. This is a style/consistency cleanup, not required by the rename. It does not break anything, but it is technically outside Slice 1's stated objective.

**Verdict**: Non-blocking. The change is correct and harmless. Acceptable to include.

## 2. Correctness: Contract Rename Completeness

### 2.1 Memory Contract (`dayu/host/memory.py`)

All planned renames verified:

- `VerifiedFactView` → `EvidenceBackedFactView` ✓
- `verified_facts` field → `evidence_backed_facts` ✓
- `max_verified_facts` → `max_evidence_backed_facts` ✓
- `DEFAULT_MEMORY_MAX_VERIFIED_FACTS` → `DEFAULT_MEMORY_MAX_EVIDENCE_BACKED_FACTS` ✓
- `MemoryClaimStatus.TOOL_VERIFIED` → `EVIDENCE_BACKED` ✓
- `MemoryIncludedReason.TOOL_VERIFIED_FACT` → `EVIDENCE_BACKED_FACT` ✓
- `_verified_fact_from_projection_event` → `_evidence_backed_fact_from_projection_event` ✓
- `_verified_fact_to_json_value` → `_evidence_backed_fact_to_json_value` ✓
- `_verified_fact_from_json_value` → `_evidence_backed_fact_from_json_value` ✓
- `_limit_verified_facts` → `_limit_evidence_backed_facts` ✓
- Snapshot JSON key `verified_facts` → `evidence_backed_facts` ✓
- Policy JSON key `max_verified_facts` → `max_evidence_backed_facts` ✓
- All `__post_init__` error messages updated ✓
- All docstrings updated ✓

No compatibility shims, aliases, or fallback keys added.

### 2.2 Durable Memory (`dayu/host/durable/memory.py`)

- `_ITEM_KIND_VERIFIED_FACT` → `_ITEM_KIND_EVIDENCE_BACKED_FACT` ✓
- `_insert_verified_fact_item` → `_insert_evidence_backed_fact_item` ✓
- `_verified_fact_item_json_value` → `_evidence_backed_fact_item_json_value` ✓
- `_payload_digest_for_verified_fact` → `_payload_digest_for_evidence_backed_fact` ✓
- All docstrings updated ✓

### 2.3 Config Loader (`dayu/runtime/config_loader.py`)

- `MemoryProjectionConfig.max_verified_facts` → `max_evidence_backed_facts` ✓
- Allowed field set updated ✓
- Parser uses `_require_positive_int_field` on new key ✓

### 2.4 Execution Profiles (`dayu/config/execution_profiles.json`)

All 4 profiles updated from `max_verified_facts` to `max_evidence_backed_facts` ✓.

### 2.5 Service Assembly (`dayu/service/host_assembly.py`)

- `_memory_projection_policy_from_config` uses `policy.max_evidence_backed_facts` ✓

### 2.6 `run_input.py` Block ID — **REMAINING STALE TERM**

**Finding S1-02 [MEDIUM / correctness]**: `dayu/host/run_input.py:1618` still uses block id `stable:verified_facts`:

```python
blocks.append(_MemoryStableBlock(block_id="stable:verified_facts", message=facts))
```

Plan §4.1 explicitly requires: "RunInputBuilder block id `stable:verified_facts` → `stable:evidence_backed_facts`."

The field access `snapshot.evidence_backed_facts` was correctly renamed (line 1616), but the block id string literal was not. The function name `_memory_verified_fact_message` (line 1715) was also not renamed, though this is a private function and less critical.

Additionally, `tests/host/test_run_input_builder.py` references `stable:verified_facts` at lines 555 and 685. These would need to match.

**Verdict**: This is a correctness gap against the plan. The block id is a contract-level identifier embedded in diagnostic items and stable block ordering. It should be renamed to `stable:evidence_backed_facts` per the plan. **Blocking** for Slice 1 acceptance.

## 3. Fail-Fast Behavior

### 3.1 Config Rejects Old Key

New test `test_old_max_verified_facts_key_fails_fast` (tests/runtime/test_config_loader.py:576) correctly verifies that the old key `max_verified_facts` is rejected as an unknown field. The allowed field set in `_parse_memory_projection` only includes `max_evidence_backed_facts`. ✓

### 3.2 Snapshot JSON Uses New Key

`conversation_memory_snapshot_from_json_value` requires `evidence_backed_facts` key (line 2751). Old `verified_facts` key would fail with `_required_list` error. ✓

## 4. No Compatibility Shims

Searched all changed files for:
- Old-name property aliases: None found ✓
- Old-key fallback reads: None found ✓
- Old-name re-exports: None found ✓

## 5. Tests

### 5.1 Controller Validation

Per the gate description:
- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py` → 42 passed ✓
- `pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/runtime/config_loader.py dayu/service/host_assembly.py dayu/host/run_input.py` → 0 errors ✓

### 5.2 New Test Coverage

- `test_old_max_verified_facts_key_fails_fast`: Tests old config key rejection ✓
- `test_default_runtime_config_files_load_as_typed_views`: Added assertion for `max_evidence_backed_facts == 256` ✓
- `test_compose_open_host_options_uses_runtime_tuning_from_config`: Added assertion for `max_evidence_backed_facts == 256` ✓
- Test helper `_execution_profile_record` and `_write_execution_profile_overlay` use new key ✓

### 5.3 Remaining Old Names in Tests

Many test files (`test_memory_projection.py`, `test_run_input_builder.py`, `test_compaction_contract.py`, etc.) still use old names like `VerifiedFactView`, `verified_facts`, `TOOL_VERIFIED`, `max_verified_facts`. These are all in files NOT in Slice 1's allowed scope. They belong to Slices 3–6 (compaction, projection, run_input builder). This is expected and correct — each slice handles its own test files.

## 6. README Sync

### 6.1 `dayu/README.md`

- "verified fact" → "evidence-backed fact" in architecture bullet point ✓

### 6.2 `dayu/host/README.md`

- "verified fact" → "evidence-backed fact" in Memory Projection section ✓
- Two occurrences updated in the same paragraph ✓

### 6.3 Remaining Stale Terms in Docs

Searched `dayu/README.md`, `dayu/host/README.md` — no remaining `verified_facts` or `max_verified_facts` terms. ✓

Root `README.md` and `dayu/config/README.md` were not touched. The grep for stale terms in those files should be verified but they are outside the immediate diff scope.

## 7. Findings Summary

| ID | Severity | File | Description | Blocking? |
|---|---|---|---|---|
| S1-01 | LOW | `host_assembly.py`, `test_host_assembly.py` | Import path refactor (re-export → direct) is out-of-scope cleanup but harmless | No |
| S1-02 | MEDIUM | `run_input.py:1618` | Block id `stable:verified_facts` not renamed to `stable:evidence_backed_facts` per plan §4.1 | **Yes** |

## 8. Verdict

**Conditional PASS.** One blocking finding:

- S1-02: `run_input.py:1618` block id `stable:verified_facts` must be renamed to `stable:evidence_backed_facts`, and function `_memory_verified_fact_message` should be renamed to `_memory_evidence_backed_fact_message` for consistency. Corresponding test references in `test_run_input_builder.py` (lines 555, 685) must also be updated.

Once S1-02 is fixed, Slice 1 should be accepted. All other renames are complete, fail-fast behavior is correct, no compatibility shims exist, tests pass, and doc sync is accurate for the allowed scope.
