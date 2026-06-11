# WU-PROJ-01 Aggregate Deepreview Fix Re-Review

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview re-review
- Date: 2026-06-11
- Reviewer: AgentMiMo
- Artifacts reviewed:
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-fix-codex.md`
- Diff scope: uncommitted changes in `dayu/host/memory_repair.py`, `tests/host/test_memory_repair.py`, `docs/host/issues-implementation-control.md`

## Scope

- Mode: current changes (aggregate deepreview fix re-review)
- Branch: wu-proj-01
- Base: main
- Output file: `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-mimo.md`
- Included scope: aggregate deepreview fix 变更的 3 个文件及其关联行为、文档、测试意图
- Excluded scope: 未触及的 dispatch/projection correctness 行为、opportunistic batch count、source builder caps

## Findings

未发现实质性问题。

### 审查逐项核对

#### 1. `REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 删除且无兼容残留

- **直接证据**: `dayu/host/memory_repair.py` diff 删除了两个 enum 值（原行 37-38），剩余 `BEST_EFFORT_AFTER_COMMIT` 唯一值。`rg "REQUIRED_BEFORE_DISPATCH|REBUILD_BEFORE_DISPATCH" dayu/ tests/ docs/host/issues-implementation-control.md` 无命中。生产代码无 alias、wrapper 或 re-export。
- **判定**: ✅ 符合 AGG-F1 fix 要求。

#### 2. 测试正确改用 `BEST_EFFORT_AFTER_COMMIT`，意图未削弱

- **直接证据**: `tests/host/test_memory_repair.py` 5 处 `purpose` 参数从 `REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 改为 `BEST_EFFORT_AFTER_COMMIT`。
- **意图分析**: `purpose` 在生产代码中仅用于类型校验（行 74-75）和日志/diagnostic metadata（行 203-208, 264-270, 529-538），不驱动任何行为分支。被修改的 5 个测试分别验证：rebuild reset、budget exhausted、target reached、rebuild budget exhausted、checkpoint 推进——这些行为均不受 `purpose` 值影响。
- **判定**: ✅ 测试意图完整保留，purpose 变更不影响断言覆盖。

#### 3. 控制文档修正 focused count 为 174 并记录 fix/re-review gate

- **直接证据**: `docs/host/issues-implementation-control.md` diff 中 WU-PROJ-01 行更新为 "CAP/S3/S4 focused set to 174 passed"，gate 状态更新为 `aggregate-deepreview-re-review`，记录了 AgentCodex fix artifact 和 controller 复验结果。
- **判定**: ✅ 符合 AGG-F2 fix 要求，gate 状态正确推进。

#### 4. 未误改 dispatch/projection correctness 行为、opportunistic batch count、source builder caps

- **直接证据**: `git diff` 仅涉及 3 个文件。`dayu/host/dispatch.py` 未修改。`REQUIRED_BEFORE_DISPATCH` / `REBUILD_BEFORE_DISPATCH` 在 `dispatch.py` 中无引用。correctness path 已由既有 `budget=None` 表达，本轮未触及。
- **判定**: ✅ 非目标区域无侵入。

#### 5. README 判断

- **直接证据**: fix artifact 记录了 README 判断逻辑——删除的是已无生产 consumer 的内部 enum 值，不影响公共接口、架构边界或状态机，因此不更新 `dayu/host/README.md` 和 `tests/README.md`。
- **判定**: ✅ 判断合理。

#### 6. 类型与测试验证

- **直接证据**: controller 复验 `pyright` 0 errors、`python -m pytest ... -> 91 passed`、`git diff --check` passed。
- **判定**: ✅ 类型和测试无回归。

## Open Questions

- 无。

## Residual Risk

- 本轮 re-review 基于 uncommitted diff 的静态走读，未重新执行测试或 pyright（controller 已复验通过）。
- 既有 aggregate deepreview 中 rejected 的 opportunistic batch count / source builder cap 议题保持原裁决，不属于本轮 fix scope。
- `MemoryProjectionRepairPurpose` 现在仅剩 `BEST_EFFORT_AFTER_COMMIT` 一个值。如果未来 purpose 需要驱动行为分支，需重新评估 enum 设计；当前 purpose 仅用于日志/diagnostic，单值无风险。

## 结论

**PASS**

无 blocking findings，无非阻塞 findings。AgentCodex fix 正确实现了 controller adjudication 要求的 AGG-F1 和 AGG-F2，测试意图未削弱，非目标区域无侵入，类型和测试验证通过。
