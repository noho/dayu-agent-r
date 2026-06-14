# PR Review Re-review

## Scope

- Mode: Focused re-review
- Original review: `docs/reviews/pr-review-20260614-ds.md`
- Fix artifact: `docs/reviews/pr-review-fix-20260614.md`
- PR: 140
- Branch: `work/cm-05-06-08-09`
- Base: `main`
- Output file: `docs/reviews/pr-review-rereview-20260614-ds.md`
- Included scope: 单 finding fix（`_bounded_known_refs` 移除）及其对 PR 140 整体 correctness / stability 的影响

## Fix Verification

### 变更内容

`dayu/host/llm_compaction.py` 中移除未调用的私有函数 `_bounded_known_refs`（原行 1191–1210）。变更仅删除 dead code，不修改任何执行路径、类型签名、公共 API 或 LLM-facing 语义。

### 验证结果

| 检查项 | 结果 |
|---|---|
| `grep -rn '_bounded_known_refs' dayu/ tests/` | 无命中，确认已完全移除 |
| `pytest tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` | 212 passed, 1 skipped |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |
| `git diff --check` | clean |

### 新问题检查

- 变更仅删除一个无调用方的私有函数；不引入新 import、新逻辑、新类型或新状态变更。
- 不影响 WU-CM-05 typed parsing 的现有测试覆盖；37 个 `test_llm_compaction.py` 用例全部通过。
- 不影响其余三个 WU 的任何执行路径或测试覆盖。
- 不改变 `dayu/host/__init__.py` 导出列表、公共契约或 durable schema。

## Finding 最终状态

| 编号 | 简述 | 原始严重程度 | 状态 |
|---|---|---|---|
| 1 | `_bounded_known_refs` 为未调用死代码 | 低 | **已修复** |

## Residual Risk

无新增 residual risk。原有 Open Questions（Q1: `_bounded_known_refs` 预期接入点、Q2: WU-CM-09 identity read failure 分支追踪）中，Q1 因该函数已被移除而自然关闭；Q2 仍维持原状态（non-blocking 确认项）。

## Conclusion

**PASS**

Accepted finding 已修复，未引入新问题。所有验证通过。允许 accepted PR review commit / push / draft-PR-pass。
