# PR 190 F11/F12 Aggregate MiMo Re-Review

## Scope

- **Mode**: aggregate re-review（finding closure verification）
- **PR**: #190 `fix(cli): close interactive conformance gaps`
- **Branch**: `codex/interactive-oracle` → `main`
- **Base for re-review**: `2cf1b4ac` + uncommitted fix in `tests/host/test_compaction_contract.py`（1 line added）
- **Fix artifact**: `docs/reviews/pr-190-f11-f12-aggregate-fix-20260806.md`
- **Adjudication artifact**: `docs/reviews/pr-190-f11-f12-aggregate-review-adjudication-20260806.md`
- **Review date**: 2026-08-06
- **Reviewer**: MiMo（re-review）
- **Re-review scope**: verify accepted DS-01 closure; verify rejected DS-02/DS-03 untouched; verify no runtime/prompt/schema/registry/docs/README/PR drift; verify original MiMo aggregate PASS remains valid at current worktree.

## DS-01 Closure Verification

**Accepted finding**: `CompactSemanticSectionV3` enum values and `_ROOT` structure descriptor field names are independently maintained and can drift.

**Fix**: add exact ordered equality assertion to existing owner-level test `test_compact_structure_owner_projects_template_schema_rules_and_parser`.

**Evidence of closure**:

1. Test file diff（uncommitted）: exactly 1 line added at `tests/host/test_compaction_contract.py:139`:
   ```python
   assert tuple(item.value for item in CompactSemanticSectionV3) == tuple(template)[1:]
   ```
   This matches the adjudication's prescribed assertion exactly: compares `CompactSemanticSectionV3` ordered values against `compact_output_template_v3()` keys excluding the root `schema` key.

2. Owner test passes: `1 passed in 0.32s`.

3. The assertion is order-sensitive and catches field rename/add/delete/reorder drift between the two owners without exporting `_ROOT`, adding a second owner, or changing runtime behavior.

**Verdict: DS-01 closed.**

## Rejected Finding Verification

### DS-02 — Prompt business descriptions handwritten (rejected-with-reason)

**Verification**: `dayu/config/prompts/scenes/conversation_compaction_user.md` was not modified by the fix. The diff from `3087b1b9..HEAD` reflects original PR changes only (prompt simplification from 13,919→3,337 bytes), not fix changes. No test or production code change was made to address DS-02. Adjudication decision respected.

**Verdict: rejected finding untouched.**

### DS-03 — Broad `except Exception` in fallback (rejected-with-reason for this work unit)

**Verification**: `dayu/host/compact_pipeline.py` was not modified by the fix. The broad `except Exception` at line 798 remains unchanged. No test or production code change was made to address DS-03. Adjudication decision respected.

**Verdict: rejected finding untouched.**

## Drift Verification

| Surface | Drift check | Result |
| --- | --- | --- |
| Runtime/production code | `git diff HEAD --stat` shows only `tests/host/test_compaction_contract.py` (1 line added) | **No drift** |
| Prompt (`conversation_compaction_user.md`) | Not modified by fix; original PR changes only | **No drift** |
| Schema (`compact_structure.py`) | Not modified by fix | **No drift** |
| Registry (`cli_ci_oracles.json`, `cli_ci_scenarios.json`) | Not modified by fix; original PR changes only | **No drift** |
| Docs/README | Not modified by fix | **No drift** |
| PR body/behavior | Not modified by fix | **No drift** |
| `git diff --check` | Clean, no whitespace issues | **Pass** |

## Original MiMo Aggregate PASS Verification

All key test suites from the original MiMo review pass at current worktree with the fix applied:

| Suite | Result |
| --- | --- |
| `tests/host/test_compaction_contract.py` | 28 passed |
| `tests/host/test_llm_compaction.py` + `test_run_input_builder.py` + `test_memory_projection.py` + `test_compaction_operation.py` + `test_compaction_terminal.py` | 213 passed |
| `tests/host/test_context_compact_events.py` + `test_tool_trace_queries.py` + `test_tool_trace_analysis.py` | 136 passed |
| Owner invariant (DS-01 specific) | 1 passed |
| **Total verified** | **378 passed** |

All test results identical to original MiMo aggregate review. No regression.

## Validation Suite Results

| Check | Command | Result |
| --- | --- | --- |
| Owner invariant | `pytest tests/host/test_compaction_contract.py::test_compact_structure_owner_projects_template_schema_rules_and_parser -q` | 1 passed in 0.32s |
| Coverage | `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py --cov=dayu.host.compact_structure --cov-fail-under=80` | 90% (203 stmts, 21 missed), ≥80% pass |
| pyright | `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| Ruff | `ruff check tests/host/test_compaction_contract.py` | All checks passed |
| JSON | `python -m json.tool docs/cli_ci_oracles.json` + `cli_ci_scenarios.json` | Both valid |
| `git diff --check` | `git diff --check` | Clean |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `DS-01`：**closed**。owner-level test invariant 已验证，原 MiMo PASS 仍有效。
- `DS-03` 所述既有 traceback observability debt：**assigned to later work unit**，owner 为 Host observability。不在本 re-review scope。
- Replacement scenario adjudication：**assigned to later work unit**，owner 为 Oracle controller。不在本 re-review scope。

## Conclusion

**PASS**。DS-01 已通过 owner-level test invariant 关闭；rejected DS-02、DS-03 均未被修改；无 runtime/prompt/schema/registry/docs/README/PR drift；原始 MiMo aggregate PASS 在当前 worktree 仍有效（378 tests pass）。所有 validation suite（coverage ≥80%、pyright、Ruff、JSON、`git diff --check`）通过。
