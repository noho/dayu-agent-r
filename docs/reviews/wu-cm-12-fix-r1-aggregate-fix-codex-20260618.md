# WU-CM-12-FIX-R1 aggregate deepreview fix

## 改动文件

- `dayu/host/compact_material.py`
- `tests/host/test_compaction_operation.py`
- `docs/reviews/wu-cm-12-fix-r1-aggregate-fix-codex-20260618.md`

## 修复 findings

1. `dayu/host/compact_material.py`：移除 `_provenance_from_evidence_blocks` 的未使用形参 `evidence_blocks`，同步更新唯一调用点，并删除 `del evidence_blocks`。函数行为保持为依据 `selected_blocks` 生成 evidence provenance。
2. `tests/host/test_compaction_operation.py`：将旧 chunking 语义测试名 `test_evidence_chunks_share_same_durable_query_text` 改为 `test_evidence_block_shares_durable_query_text_without_chunking`。测试语义与断言未修改。

## 验证结果

- `source .venv/bin/activate` 后运行 `pytest tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q`：通过，`90 passed in 0.54s`。
- `source .venv/bin/activate` 后运行 `pyright dayu/host/compact_material.py tests/host/test_compaction_operation.py`：通过，`0 errors, 0 warnings, 0 informations`。
- 运行 `git diff --check`：通过，无输出。

## README 检查

- 已阅读 `dayu/host/README.md` 与 `tests/README.md` 的 Agent 更新约束。
- 本次修改不改变 Host 架构、公共契约、关键机制、测试分层或运行方式，未触发 README 内容更新。

## 残余风险

- 残余风险低。本次只删除死参数和改测试名，不改变 compact material provenance 生成逻辑或测试断言。
