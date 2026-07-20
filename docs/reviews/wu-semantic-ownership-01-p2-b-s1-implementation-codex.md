# WU-SEMANTIC-OWNERSHIP-01 P2-B S1 Implementation - Codex

## Direct Evidence And Motivation Confirmation

- 动机成立，且严重性保持 P2：本次直接证据只落在测试 owner，而不是 production memory 语义。
- `tests/host/test_import_boundary.py` 原 `_imported_module_names(...)` 只收集 `ast.ImportFrom` 中 `node.level == 0` 的绝对 `from` import；相对 import 会被漏扫，import-boundary 测试 owner 没有覆盖真实依赖路径。
- `tests/host/test_compact_material.py` 与 `tests/host/test_run_input_builder.py` 存在业务测试直接构造 `ConversationMemorySnapshotVNext(...)`、写入 `snapshot_digest="pending"` 后再回填 digest 的重复模式；snapshot digest 中间态泄漏到业务测试体。
- `tests/host/test_memory_projection.py` 当前未发现 `snapshot_digest="pending"` 散落；本次只增加 source-scan 防线，未迁移其 production memory 语义相关测试。

## Owner Boundary

- import dependency scan 的 owner 是 `tests/host/test_import_boundary.py` 的 AST scanner；修复必须在 scanner 统一解析 absolute / relative import，不能让各边界测试自行猜测相对 import。
- memory snapshot 测试数据的 owner 是 tests-only factory：`tests/host/memory_snapshot_factories.py`。业务测试只表达要覆盖的 memory view 语义，digest placeholder 和 canonical digest 回填集中在 factory/helper。
- production Conversation Memory、RunInputBuilder、durable memory projection、terminal answer continuity 均不属于 S1，本次未修改 `dayu/host/`。

## Implementation Summary

- `tests/host/test_import_boundary.py`
  - `_imported_module_names(...)` 改为接收 `scanned_file` 与 `package_root`。
  - 新增相对 import 解析：`level == 1` 映射当前 package，`level == 2` 映射父 package，`node.module is None` 返回解析后的 package prefix。
  - 对文件不在 package root、package root 不是 Python package、相对回溯超出 package root 等情况 fail loudly。
  - 增加 absolute、same-package relative、parent-package relative、no-module relative、unresolvable relative 覆盖。
  - 增加 source scan：compact/run-input/memory projection 业务测试不得散落 pending digest；compact/run-input 不得直接构造 `ConversationMemorySnapshotVNext(...)`。
- `tests/host/memory_snapshot_factories.py`
  - 新增 empty/rich/current-input/reference-continuity snapshot factory。
  - 新增 cursor、policy digest、snapshot digest 回填 helper。
  - 内部使用生产 memory dataclasses 与 `calculate_memory_snapshot_digest(...)`。
- `tests/host/test_compact_material.py` / `tests/host/test_run_input_builder.py`
  - 迁移 snapshot 构造和 digest 回填到共享 factory。
  - 保留业务测试自身的 memory view 差异断言，不改生产语义。
- `tests/README.md`
  - 最小补充 Host memory snapshot 测试数据维护约定。

## Propagation Audit For S1

1. import-boundary tests 从源码文件路径和 package root 产生模块依赖事实。
2. scanner 将 absolute import 与 relative import 统一投影为绝对模块名。
3. 各边界测试继续只消费绝对模块名并匹配 forbidden prefix；相对 import 不再被静默跳过。
4. memory snapshot 测试事实由 shared factory 产生。
5. factory 内部用生产 dataclass 校验字段，用生产 digest helper 生成 canonical snapshot digest。
6. compact material 与 RunInputBuilder 业务测试消费同源 snapshot；测试体不再持有 digest 中间态 sentinel。
7. source-scan 测试持续约束 compact/run-input/memory projection 不新增 pending digest 散落，并约束 compact/run-input 不重新直接构造 snapshot。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py`：21 passed。
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py`：203 passed。
- `source .venv/bin/activate && pyright`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：通过。

## README Decision

- 已读取 `tests/README.md`。
- 本次新增 tests-only shared memory snapshot factory，属于测试维护约定，不是新增测试层级；因此只在 Host P12.6 memory semantic smoke 段落追加一句维护约定，不机械同步其它 README。

## Residual Risks / Stop Conditions

- S1 未处理 terminal answer continuity projection contract；`docs/host/design.md`、`dayu/host/_terminal_answer.py`、`dayu/host/durable/memory.py`、`dayu/host/run_input.py` 等 S2 范围未触碰。
- 本次没有改变 production memory durable schema、RunInputBuilder production projection 或 terminal payload 语义。
- 若后续发现 source-scan 需要允许某个专门 digest invariant 测试直接构造 snapshot，应先把允许位置收敛到 factory 或明确命名的 digest invariant 测试，再调整 scanner。
