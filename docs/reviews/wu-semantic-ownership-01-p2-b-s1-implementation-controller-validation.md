# WU-SEMANTIC-OWNERSHIP-01 P2-B S1 Implementation Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-B`
- Slice: `S1`
- Gate: implementation controller validation before dual-agent review
- Accepted plan commit: `823ee002`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-codex.md`

## Motivation Check

动机成立，且本 slice 的严重性限定为 P2 测试 owner 风险：

- `tests/host/test_import_boundary.py` 原 import scanner 只覆盖 absolute `from` import，不能证明相对 import 未绕过 Host / Runtime / Engine 边界测试。
- compact / run-input 业务测试曾直接构造 `ConversationMemorySnapshotVNext(...)`，并散落 `snapshot_digest="pending"` 后再回填 digest 的重复模式。
- 这些问题不会直接改变 production Host memory 语义，但会削弱后续 S2 和全仓 deepreview 对 semantic ownership drift 的检测能力。

## Owner Boundary

- import dependency fact 的 owner 是 `tests/host/test_import_boundary.py` 的 AST scanner；修复必须统一把 absolute / relative import 投影为绝对模块名。
- memory snapshot 测试数据 owner 是 `tests/host/memory_snapshot_factories.py`；业务测试只表达要覆盖的 memory view，不直接持有 snapshot digest 中间态。
- production Conversation Memory、RunInputBuilder、durable memory projection、terminal answer continuity 属于 P2-B S2，本 slice 不修改 `dayu/host/` production 文件。

## Controller Changes

总控在 AgentCodex 实现基础上补强了 source-scan 防线：

- `snapshot_digest="pending"` 检测从固定字符串匹配改为 AST call keyword 扫描，能识别空格、单引号和换行格式。
- `ConversationMemorySnapshotVNext(...)` 检测从固定字符串匹配改为 AST call 扫描，能识别直接调用、属性调用、`as` 导入别名和简单赋值别名。
- 新增两个 scanner 单元测试，证明上述 source-scan 不依赖源码字面格式。

## Propagation Audit

1. import-boundary tests 从被扫描源码文件和 package root 产生 import fact。
2. scanner 将 `import`、absolute `from` import 和 relative `from` import 统一解析为绝对模块名。
3. Host / Runtime / Engine boundary tests 继续只消费绝对模块名并匹配 forbidden prefix；相对 import 不再被静默跳过。
4. memory snapshot 测试事实由 shared factory 产生。
5. factory 内部使用生产 memory dataclasses 与 `calculate_memory_snapshot_digest(...)` 生成 canonical digest。
6. compact material 与 RunInputBuilder 业务测试消费同源 snapshot；测试体不再手写 pending digest 或直接构造 snapshot。
7. AST source-scan 测试持续约束 compact / run-input / memory projection 测试不新增 pending digest 散落，并约束 compact / run-input 不绕过 shared factory 直接构造 snapshot。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py`: `23 passed`
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py`: `203 passed`
- `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed
- Source scan:
  - `ConversationMemorySnapshotVNext` direct constructor appears only in `tests/host/memory_snapshot_factories.py`; business test references are type annotations or schema contract checks.
  - No `snapshot_digest="pending"` / equivalent keyword-value sentinel remains in compact / run-input / memory projection business tests.

## README Decision

`tests/README.md` was updated because this slice changes tests-only Host memory snapshot maintenance conventions. No production README trigger is hit because no production `dayu/` code or public CLI / Service / Host behavior changed.

## Controller Review Entry

Proceed to implementation review. Reviewer focus:

- Relative import resolution must fail loudly when package root or import level is invalid.
- AST scanner must not silently miss relative imports at existing boundary test call sites.
- Memory snapshot factory must use production dataclasses and digest helpers without production hooks.
- Business tests must not regain local pending digest or direct snapshot construction.
- S2 production semantic changes must remain untouched until S1 is accepted.
