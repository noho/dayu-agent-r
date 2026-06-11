# WU-PROJ-01 Residual Aggregate Deepreview Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-ds.md`

## 结论

Aggregate deepreview accepted with fix required。

两路 deepreview 均为 `PASS`，无 blocking correctness finding。总控接受 PASS 部分，但接受 2 个需要在当前 PR 修正的维护性 / 文档精度 finding，并进入 fix gate。

## Accepted Findings

### AGG-F1: 删除 `MemoryProjectionRepairPurpose` 中不再使用的 required / rebuild enum 值

裁决：`accepted`

直接证据：

- 生产代码中 `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` 与 `MemoryProjectionRepairPurpose.REBUILD_BEFORE_DISPATCH` 已无 consumer。
- `dispatch.py` required catch-up / rebuild correctness path 已改为 `budget=None`，不再通过 `purpose` 选择预算。
- 剩余引用只在 tests 中构造 `MemoryProjectionCatchupBudget`，而 `purpose` 现在只用于日志 / diagnostic metadata，不应保留已经不代表生产路径的 enum 值。

Fix 要求：

- 删除 `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` 与 `MemoryProjectionRepairPurpose.REBUILD_BEFORE_DISPATCH`。
- 更新相关测试，改用仍存在且语义有效的 `BEST_EFFORT_AFTER_COMMIT` 或按测试意图调整断言。
- 不新增兼容 alias / wrapper。

### AGG-F2: 修正控制文档 CAP-R1 focused tests 计数

裁决：`accepted`

MiMo 独立复验同一 focused test set 在 S3/S4 新增测试后为 174 passed，而控制文档仍写 173 passed。该偏差只影响文档精度，但控制文档是真源，应修正。

Fix 要求：

- 将 `docs/host/issues-implementation-control.md` 中 WU-PROJ-01 行的 `CAP-R1 focused tests -> 173 passed` 更新为当前事实 `174 passed`，或明确写成 CAP/S3S4 combined focused set 174 passed。

## Rejected Findings

### AGG-F3: opportunistic one-batch 行为保守

裁决：`rejected-with-reason`

当前 one-batch opportunistic catch-up 已明确命名为非 correctness 行为，required dispatch catch-up 会追到 required cursor、idle 或 failure。没有数据证明需要调大 opportunistic batch count；当前 PR 不做性能调参。

### AGG-F4: 极端 post-compact delta SQL 查询性能

裁决：`rejected-with-reason`

完整读取 latest accepted compact 到 current input 前的 canonical EventLog delta 是本次设计目标。极端数据量下的 selection / segmentation / budget 处理属于 downstream material selection 与 Context Governance，不应重新在 source builder 加 cap。

## 验证要求

AgentCodex fix 后必须至少运行：

- `python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py`
- `pyright`
- `git diff --check`
