# WU-PROJ-01-CAP-R1 Implementation

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: CAP-R1 implementation only
- Agent: AgentCodex
- Date: 2026-06-11
- Branch: `wu-proj-01`
- Scope: 不处理 `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1`

## 动机判断

动机成立，严重性没有被高估。

第一性原理上，compact material source builder 的职责是从 Host durable truth 构造事实材料边界：latest accepted compact、post-compact canonical EventLog delta、current input anchor。固定 `256` delta rows、固定 `8` evidence blocks 或 query text 截断都属于在 source 阶段丢事实，会把 correctness 交给任意常量；LLM-facing 最终纳入多少材料应由 Context Governance / segment selection / budget 负责。

Memory projection 的 dispatch 前 required catch-up / rebuild 也是 correctness 前置条件：它必须追到 required cursor、idle 或 failure。固定 `max_batches` / `max_scanned_events` 只能作为非 correctness opportunistic 行为，不能作为生产 dispatch 正确性语义。

## 改动摘要

- `dayu/host/compact_material.py`
  - 移除 pre-dispatch source builder 的 `max_delta_events` / `max_evidence_blocks` 参数与固定 cap。
  - `_post_compact_delta_rows(...)` 按 latest compact boundary 到 current input 前的完整 canonical EventLog delta 读取。
  - `_pre_dispatch_delta_material_blocks(...)` 不再按 evidence block 数 fail closed。
  - query text helper 只做 `normalized_material_text(...)`，不再截断或追加 truncated marker。

- `dayu/host/dispatch.py`
  - required-before-dispatch catch-up 改为 `budget=None`，按 `batch_size` 多批追到 required cursor、idle 或 failure。
  - rebuild-before-dispatch 改为 `budget=None`，按 required cursor 重建到目标、idle 或 failure。
  - compact accepted 后的轻量 projection 推进保留为 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1`，文档说明它不影响 worker accept 前 correctness catch-up。

- `dayu/host/open_host.py`
  - after-commit memory projection catch-up 重命名为 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`。
  - docstring 明确该预算只影响 commit 后轻量推进，不参与 dispatch required / rebuild correctness catch-up。

- Tests
  - 新增 pre-dispatch 超过旧 256 delta rows 仍完整读取。
  - 新增 accepted evidence 超过旧 8 blocks 不 fail closed。
  - 新增长 query text 超过旧 1200 字符仍完整保留。
  - 新增 required catch-up 跨 17 批追到 target。
  - 新增 rebuild 跨 33 批追到 target。
  - 调整 open_host dispatch 测试，证明 after-commit 不追账时，dispatch required catch-up 仍会追到 cursor 并接受 worker。

## 常量清单

已删除 / 移除生产 correctness 语义：

- `_READABLE_QUERY_TEXT_MAX_CHARS` from `dayu/host/compact_material.py`
- `_READABLE_QUERY_TRUNCATED_MARKER` from `dayu/host/compact_material.py`
- `_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS`
- `_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS`
- `_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES`
- `_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES`
- `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES`
- `_MEMORY_PROJECTION_AFTER_COMMIT_MAX_BATCHES`

保留但重新命名并限定为非 correctness opportunistic 行为：

- `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT = 1`
- `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT = 1`

## 验证结果

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py`
  - Result: `125 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings`
- `git diff --check`
  - Result: passed

## README 决策

已检查：

- `dayu/host/README.md`
- `tests/README.md`

不更新 README。原因：

- `dayu/host/README.md` 已说明 Context Governance / Memory 的稳定边界：pre-dispatch compact material 由 EventLog / payload / artifact truth 构造，Memory 只消费 accepted compact，不反向作为 compact input truth。
- 本次没有新增 Host public API、OpenHostOptions 字段、测试层级、测试运行入口或分层边界。
- 新测试只补现有 `tests/host` 文件内的 CAP-R1 回归，不需要扩展 `tests/README.md` 的测试分类说明。

## 剩余风险

- `dayu/host/compaction_evidence.py` 仍存在旧 `_READABLE_QUERY_TEXT_MAX_CHARS` / truncated marker helper；该文件不在本次用户给定 allowed files 内，且不是本轮 pre-dispatch source builder 路径，因此本 gate 未修改。若 controller 要求全仓库删除同名 query cap，需要单独扩大 allowed files 或由后续 owner 处理。
- CAP-R1 已完成本地 implementation 与验证；`WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1` 未处理，仍需独立 gate。
