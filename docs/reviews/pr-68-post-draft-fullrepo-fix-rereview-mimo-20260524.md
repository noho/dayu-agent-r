# PR 68 Post-Draft Full-Repo Fix Re-Review MiMo 20260524

## Gate

- Gate: P12.6 post-draft full-repo fix re-review gate for PR 68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Fix artifact: `docs/reviews/pr-68-post-draft-fullrepo-fix-codex-20260524.md`
- Review date: 2026-05-25
- Scope: A1-A9 only; independent re-verification of uncommitted post-draft full-repo fix

## Validation Commands and Results

| Command | Result |
|---------|--------|
| `python -m pytest tests/host/test_memory_repair.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_tool_runtime_schema_projection.py tests/runtime/test_tool_truncation.py tests/host/test_durable_transaction.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | **103 passed** in 1.29s |
| `python -m pyright dayu/ tests/` | **0 errors, 0 warnings, 0 informations** |
| `python -m pytest tests/ -x -q` | **1653 passed, 1 skipped** in 69.54s |
| `git diff --check` | **CLEAN** |
| Import boundary: `ToolBundleSourceKind` / `ToolBundleSourceRef` from `dayu.host` | **CLEAN** — zero remaining imports from `dayu.host` or `dayu.host.tooling` |

## Per-Finding Re-Review

### A1: `memory_repair.py` has no direct tests — FIXED

- **Evidence**: `tests/host/test_memory_repair.py` (349 lines, 4 tests) is a new untracked file.
- **Coverage verified**:
  - `test_rebuild_resets_projection_and_finishes_empty_batch` — covers rebuild reset + empty batch termination.
  - `test_catch_up_accumulates_batches_until_short_batch` — covers multi-batch cursor/batch accumulation and short-batch termination.
  - `test_catch_up_stops_on_failure_and_counts_failure` — covers failure-triggered stop and failure counting.
  - `test_catchup_port_delegates_to_catch_up_function` — covers `ConversationMemoryProjectionCatchupPort` delegation.
- **Quality**: Tests use fakes with `monkeypatch` for `ProjectionRunner` and `reset_conversation_memory_projection`; assertions verify cursor tracking, batch accumulation, and failure semantics.
- **Regression risk**: None — module was previously untested; all existing tests unaffected.
- **Verdict**: **FIXED**

### A2: Remove `ToolBundleSourceKind` / `ToolBundleSourceRef` Host compatibility re-export — FIXED

- **Evidence**:
  - `dayu/host/tooling.py:106-111` — `__all__` no longer includes `ToolBundleSourceKind` or `ToolBundleSourceRef`.
  - `dayu/host/__init__.py:93-98` — import block no longer imports source ref types from tooling; `__all__` no longer lists them.
  - `dayu/host/tooling.py:16` — import changed from `dayu.contracts` (barrel) to `dayu.contracts.tool_source` (direct module), only `ToolBundleSourceRef` kept for internal use.
  - `dayu/host/tool_runtime.py:56` — now imports `ToolBundleSourceRef` directly from `dayu.contracts.tool_source` instead of through `dayu.host.tooling`.
- **Caller cleanup verified**: `grep` for `from dayu.host import.*ToolBundleSourceKind` and `from dayu.host.tooling import.*ToolBundleSourceRef` returns zero matches across all `.py` files.
- **Test cleanup verified**: `test_package_exports.py` removed source ref entries from `EXPECTED_TOOLING_EXPORTS`; 15 test files updated import paths.
- **README sync**: `dayu/host/README.md` updated to remove source ref types from tooling construction exports list and note `dayu.contracts.tool_source` as truth source. `tests/README.md` updated tooling options description.
- **Regression risk**: None — all callers updated; full test suite passes.
- **Verdict**: **FIXED**

### A3: Compaction semantic repair disabled by default — FIXED

- **Evidence**: `dayu/host/context_policy.py:22` — `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 2` (was 1).
- **Behavior change**: Default now allows first proposal + one semantic repair attempt before hard failure.
- **Regression risk**: Low — existing tests assert the default through the constant; `test_compaction_operation.py` tests exercise the retry loop.
- **Verdict**: **FIXED**

### A4: Open-question quality check rejects legitimate empty / clear outcomes — FIXED

- **Evidence**: `dayu/host/context_governance.py:617-653` — `_open_questions_retained` now:
  1. Calls `_original_open_questions_present(request)` — if no original open questions in material, returns `True` immediately (empty/CLEAR accepted).
  2. If originals exist: accepts summary retention (`len > 0`), non-empty `REPLACE`, or `CLEAR` (evidence-supported).
  3. `_original_open_questions_present` (line 639-653) checks `CompactMaterialBlockKind.OPEN_QUESTION` and `WORKING_ASSUMPTION` in stable + history input.
- **Tests verified** in `test_compaction_contract.py`:
  - `test_quality_accepts_clear_when_request_has_no_original_open_questions` — no-original CLEAR accepted.
  - `test_quality_rejects_original_open_questions_without_retention_or_clear` — original MISSING rejected.
  - `test_quality_accepts_evidence_supported_clear_for_original_open_questions` — original evidence-supported CLEAR accepted.
- **Regression risk**: None — existing quality check tests still pass; new tests cover the previously untested branches.
- **Verdict**: **FIXED**

### A5: Multi-pass compaction merge overstates preserved refs — FIXED

- **Evidence**: `dayu/host/compaction_operation.py:344-355` — `_merge_pass_candidates` now unions `candidate.preserved_canonical_evidence_refs` and `candidate.preserved_evidence_backed_fact_refs` from each accepted pass candidate instead of copying `request.canonical_evidence_refs` / `request.evidence_backed_fact_refs`.
- **Test verified**: `test_reactive_multi_pass_merges_only_candidate_preserved_refs` in `test_compaction_operation.py` — asserts merged `preserved_evidence_backed_fact_refs == ()` when pass candidates do not preserve them, even though request has refs.
- **Regression risk**: None — merge logic is conservative (union of actual preserves, never exceeds request refs).
- **Verdict**: **FIXED**

### A6: `_summary_pretends_evidence_backed_fact` missing test coverage — FIXED

- **Evidence**: `test_compaction_contract.py:427-446` — `test_quality_rejects_preserved_fact_ref_outside_request_subset` creates a candidate with `preserved_evidence_backed_fact_refs=("fact-existing-1", "fact-outside-request")` and asserts `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` rejection.
- **Regression risk**: None — adds coverage for previously untested branch.
- **Verdict**: **FIXED**

### A7: `tool_runtime_schema_projection.py` has no functional tests — FIXED

- **Evidence**: `tests/host/test_tool_runtime_schema_projection.py` (134 lines, 3 tests) is a new untracked file.
- **Coverage verified**:
  - `test_valid_projection_indexes_definitions_and_digests_schema` — valid bundle acceptance, name index, digest, JSON schema.
  - `test_definitions_by_name_rejects_duplicate_names` — duplicate effective tool name rejection.
  - `test_reserved_name_conflict_rejects_framework_tool_name` — reserved `fetch_more` name conflict rejection.
- **Regression risk**: None — new test file; existing tests unaffected.
- **Verdict**: **FIXED**

### A8: `tool_truncation.py` has no direct tests — FIXED

- **Evidence**: `tests/runtime/test_tool_truncation.py` (162 lines, 6 tests) is a new untracked file.
- **Coverage verified**:
  - `test_no_truncation_disabled_spec_returns_original` — disabled spec passthrough.
  - `test_exact_declared_threshold_is_preserved` — declared limits not overridden.
  - `test_truncation_missing_limit_uses_policy_default` — missing limit filled from policy default.
  - `test_empty_policy_defaults_reject_enabled_truncation` — missing policy default raises `ValueError`.
  - `test_multibyte_target_path_is_preserved_as_typed_spec` — multibyte field path preserved.
  - `test_default_values_must_be_strict_ints` — `bool` rejected as `int` for TTL and limit defaults.
- **Regression risk**: None — new test file; existing tests unaffected.
- **Verdict**: **FIXED**

### A9: Log after-commit callback secondary errors — FIXED

- **Evidence**: `dayu/host/durable/transaction.py:400-405` — when `first_error is not None` and a subsequent callback raises, `_LOGGER.exception(...)` logs the secondary failure with `callback_index` and `first_error_index`.
- **Test verified**: `test_after_commit_failure_still_attempts_later_callbacks` in `test_durable_transaction.py` — asserts:
  - Second callback still runs after first failure.
  - `HostAfterCommitError` is raised with first failure as `__cause__`.
  - `"after-commit callback secondary failure"` appears in `caplog.text`.
- **Regression risk**: None — first error semantics unchanged; secondary failures now visible in logs.
- **Verdict**: **FIXED**

## Regression Check

| Concern | Status |
|---------|--------|
| Removing Host `ToolBundleSourceKind` / `ToolBundleSourceRef` re-exports | **CLEAN** — all callers updated, zero remaining `dayu.host` imports |
| Changing default compaction attempts from 1 to 2 | **CLEAN** — existing tests pass; behavior change is intentional |
| Open-question quality check behavior change | **CLEAN** — stricter for originals (MISSING rejected), more permissive for no-originals (CLEAR accepted) |
| Multi-pass preserved refs merge change | **CLEAN** — union of actual preserves is conservative; test proves no overstatement |
| `memory_repair.py` new tests | **CLEAN** — 4 tests, all pass, no production code changes |
| `tool_runtime_schema_projection.py` new tests | **CLEAN** — 3 tests, all pass, no production code changes |
| `tool_truncation.py` new tests | **CLEAN** — 6 tests, all pass, no production code changes |
| After-commit secondary-error logging | **CLEAN** — first error semantics preserved; secondary failures logged |
| Full test suite | **1653 passed, 1 skipped** — no regressions |
| pyright | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **CLEAN** |
| README sync | **CLEAN** — `dayu/host/README.md` and `tests/README.md` updated for re-export removal |

## Verdict

**PASS**

All 9 accepted findings (A1-A9) are fixed with direct file/line evidence. Each fix is verified by focused tests, full test suite (1653 passed), pyright (0 errors), and diff check. No regressions detected from any fix.

**Ready for accepted post-draft full-repo review commit.**
