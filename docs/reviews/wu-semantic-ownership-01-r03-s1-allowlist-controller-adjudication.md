# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Allowlist Controller Adjudication

## 1. Verdict

Controller verdict：**TEST-ONLY-ALLOWLIST-EXPANSION-ACCEPTED**。

R03 accepted plan 对 S1 的生产 owner 与产品语义边界保持不变；仅补入全 Host 回归直接证明受同一 strict canonical-material contract 影响的四个测试文件：

- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

这不是新 slice、不是新 WU，也不授权修改额外生产文件。

## 2. Direct evidence and motivation

- accepted S1 五个原始目标测试文件：`180 passed`。
- S1 request/awaiting/replay 关键字回归：`36 passed, 1894 deselected`。
- 全 Host 回归：`1903 passed, 1 skipped, 21 failed, 5 deselected`。
- 21 个失败只分布在上述四个测试文件；其 fixture/断言仍依赖缺失 canonical request/envelope 时的 skip、旧 fallback、limited signal 或不完整 trace row。
- 这些测试期待与已裁决 contract 直接冲突：RunInput、Memory、Compact、LLM-readable Tool Trace 所需 canonical material 缺失时必须统一 `HostDurableError`，不得 skip/fallback/limited。

因此问题是 accepted plan 的测试传播 allowlist 漏项，不是生产设计需要兼容。若在生产层恢复 fallback 会违反 Topic 3、Topic 4 与 owner-boundary 裁决。

## 3. Authorized boundary

AgentCodex 可从当前未提交实现继续，只迁移上述四个测试文件中的 fixture 和 owner-level assertions：

- 完整成功 fixture 必须创建 identity/digest 同源的 canonical `TOOL_CALL_REQUESTED` 与 accepted evidence envelope；
- 缺失、错链、身份不一致、digest 不一致必须断言 `HostDurableError`，并按消费者职责断言不继续发布 snapshot/compact/trace；
- 不得用 mock/fake 固化旧 skip/fallback/limited 行为；
- 不得修改额外生产文件，不得实施 R03-S2/S3。

迁移后必须重跑原五文件矩阵、上述四文件矩阵、全 Host 回归、逐生产文件 coverage、全量 pyright、source/propagation scans 与 `git diff --check`；README 与 implementation artifact 仍按原任务完成。
