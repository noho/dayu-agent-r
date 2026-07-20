# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Code Review Re-Review

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Gate: code review re-review (post-fix)
- Reviewer: AgentMiMo
- Generated: `20260713-001707`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-fix-codex.md`

## Task

Verify accepted findings R3-C-S1-CR-F01 and R3-C-S1-CR-F02 are fixed in the current working tree. Also verify fix did not introduce new material blockers, did not implement S2/S3, and did not implement tool-security.

## Finding Verification

### R3-C-S1-CR-F01 — `_replace_directory` should fail closed if target already exists

- **Required fix**: Before `os.replace(source, target)`, reject an existing target path. Also reject a symlink target even if broken. Add owner-level test proving `_replace_directory()` raises and leaves source/target unchanged when target already exists.
- **Production code evidence**:
  - `dayu/fins/storage/_fs_storage_infra.py:300-301`: `if target.exists() or target.is_symlink(): raise OSError(f"directory replace target 已存在: {target}")`
  - Check is placed before `os.replace()` call at line 304
  - Covers both existing directory and broken symlink targets
- **Test evidence**:
  - `tests/fins/test_fins_storage_atomicity.py:799-838`: `test_replace_directory_rejects_existing_or_broken_symlink_target`
  - Parametrized with `("directory", "broken_symlink")` — 2 test cases
  - For directory: creates source with "source" and target with "target", asserts `OSError` with "target 已存在", then asserts `(source / "state.txt").read_text() == "source"` and `(target / "state.txt").read_text() == "target"` — both unchanged
  - For broken symlink: creates source with "source" and target as broken symlink, asserts `OSError`, then asserts `target.is_symlink()` and `os.readlink(target) == expected_link_target` — symlink unchanged
- **Verdict**: **FIXED**. Fail-closed check covers existing directory and broken symlink. Test proves both source and target are unchanged after rejection.

### R3-C-S1-CR-F02 — direct `_normalize_object_key` test coverage

- **Required fix**: Import `_normalize_object_key` in test file and add direct parameterized tests for valid normalization and invalid values at the owner helper boundary.
- **Test evidence**:
  - `tests/fins/test_fins_storage_atomicity.py:45`: `from dayu.fins.storage._fs_storage_utils import ... _normalize_object_key ...`
  - `tests/fins/test_fins_storage_atomicity.py:88-107`: `test_object_key_owner_normalizes_valid_values` — parametrized with 2 valid cases: `"AAPL/filings/report.md"` → `"AAPL/filings/report.md"` and `" BRK.B / reports-2024 / annual.report.pdf "` → `"BRK.B/reports-2024/annual.report.pdf"` (verifies per-component trim)
  - `tests/fins/test_fins_storage_atomicity.py:110-128`: `test_object_key_owner_rejects_invalid_values` — parametrized with 8 invalid cases: `""`, `"   "`, `"/absolute"`, `"a//b"`, `"a/../b"`, `"a/./b"`, `"a\\b"`, `"C:/b"` — all assert `ValueError`
  - Existing `test_local_file_store_rejects_invalid_object_keys_without_external_writes` (line 135) still present as consumer-level coverage
- **Verdict**: **FIXED**. Direct owner-level import and parametrized tests for both valid and invalid values. Consumer-level indirect tests retained.

## New Blockers Check

The fix changes are minimal and scoped:

1. `_replace_directory` — added 2-line defensive guard (`target.exists() or target.is_symlink()` + `raise OSError`). No new abstractions, no new dependencies, no new public contracts.
2. Test file — added 12 new test cases (2 for F01, 2 valid + 8 invalid for F02). All use existing test helpers and patterns.

No new material blockers introduced. No changes to production behavior beyond the defensive guard.

## S2/S3 Scope Check

- No S2 files modified (upload/download workflows, CN/HK models, ingestion runtime untouched)
- No S3 files modified (Host wait adapter, Service wait adapter, host_assembly untouched)
- Only `_fs_storage_infra.py` (S1 allowed) and `test_fins_storage_atomicity.py` (S1 allowed test) modified

## Tool-Security Boundary Check

- `rg -n 'allowlist|symlink-safe|SSRF|byte-budget|tool.schema|TLS|redirect' dayu/fins/storage/ tests/fins/test_fins_storage_atomicity.py` — no matches
- The broken symlink guard in `_replace_directory` is a storage-owner internal precondition check, not upload source authority or URL provenance policy
- No LLM-facing schema, prompt, or tool schema changes

## Validation

```bash
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
```
Result: `130 passed, 3 warnings` (was 118 before fix; +12 new tests)

```bash
python -m pyright dayu/fins/storage/ tests/fins/test_fins_storage_atomicity.py
```
Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```
Result: pass, no output

---

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无新 residual risk。F01 的 TOCTOU（target check 与 `os.replace` 之间）由 storage owner 内部 ticker lock 保护，已在 fix artifact 中记录。

---

## Re-Review Conclusion

**Status: pass**

Both accepted findings verified as fixed. R3-C-S1-CR-F01 adds fail-closed guard for existing/broken-symlink targets with source/target immutability proof. R3-C-S1-CR-F02 adds direct owner-level `_normalize_object_key` import and parametrized valid/invalid tests. No new blockers, no S2/S3 scope drift, no tool-security drift.

## Completion Report

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-rereview-mimo.md`
- **fixed findings count**: 2
- **remaining findings count**: 0
- **new findings count**: 0
- **blocking questions count**: 0
