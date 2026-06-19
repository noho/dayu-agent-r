# WU-CM-12-FIX-R1 Slice 1 Code Review Fix

## Scope

- Gate: code review fix
- Finding source:
  - `docs/reviews/code-review-20260618-184822.md`
  - `docs/reviews/code-review-20260618-185121.md`
- Accepted finding: `tests/host/test_compaction_operation.py::test_evidence_chunks_share_same_durable_query_text` 仍断言旧默认 chunk label `E1.1/E1.2/E1.3`，但 Slice 1 production code 已移除默认 evidence chunking，正确行为是单个 `E1` block。

## Changed Files

- `tests/host/test_compaction_operation.py`
  - 将测试 docstring 从“durable request 被 chunk”迁移为“长 evidence 默认不 chunk，单个 block 使用同一 durable request 的 query_text”。
  - 将测试内部标识与辅助 docstring 从 chunk 语义迁移为 no-chunk / evidence label 语义。
  - 将 label 断言改为单个 `E1`。
  - 增加断言确认不存在 `E1.1` / `E1.2` / `E1.3`，且 label 不含 chunk-style `.`。
  - 保留 durable request query_text 断言，确认 query_text 仍来自 accepted evidence 对应的 durable tool request arguments。
- `docs/reviews/wu-cm-12-fix-r1-s1-fix-codex-20260618.md`
  - 记录本次 code review fix 的变更、验证、文档决策与残余风险。

说明：测试函数名保留为原 node id，是为了满足 handoff 中明确要求的验证命令；测试 docstring 和断言语义已不再描述 durable request 被 chunk。

## Finding Status

- Status: accepted finding fixed
- Production code: 未修改
- 结论：review finding 指向的是测试迁移缺口，不是 production defect。当前测试已迁移到 Slice 1 的 no-default-chunk 语义。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py::test_evidence_chunks_share_same_durable_query_text -q`
  - Result: `1 passed in 0.29s`
- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py -q`
  - Result: `127 passed in 0.51s`
- `source .venv/bin/activate && pyright dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: clean

## README / Docs Decision

- `tests/README.md` 已检查。该 README 只在新增测试层级、测试运行方式或测试维护规则变化时需要同步更新。
- 本次只迁移既有 Host compaction 测试中的断言与说明，不新增测试层级、不改变运行方式、不改变维护规则，因此不更新 README。
- 除本 fix artifact 外，不更新 implementation report。

## Residual Risks

- 测试函数名仍包含 `chunks`，这是为保留 handoff 指定的 pytest node id。测试说明与断言已明确 no-default-chunk 语义，后续若不再依赖旧 node id，可单独重命名。
- 单条超长 evidence 不再默认拆分后的 compactor input 预算风险仍由 Context Governance selection / fallback / fail-closed 处理，不属于本 code review fix 范围。
