# WU-PROJ-01 Residual Aggregate Deepreview Re-Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview re-review
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-ds.md`

## 结论

Aggregate deepreview fix re-review accepted。

AgentMiMo 与 AgentDS 均裁决 `PASS`，无 blocking findings，无非阻塞 findings。总控接受该结论。

## 关闭依据

- `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH` 与 `MemoryProjectionRepairPurpose.REBUILD_BEFORE_DISPATCH` 已删除，生产代码、允许测试与控制文档中无残留引用。
- `tests/host/test_memory_repair.py` 的 budget tests 改用 `BEST_EFFORT_AFTER_COMMIT`，测试意图保持不变；`purpose` 不驱动 catch-up / rebuild 行为分支。
- `docs/host/issues-implementation-control.md` 已修正 CAP/S3/S4 focused set 为 174 passed，并记录 aggregate deepreview fix / re-review 状态。
- 未触碰 `dispatch.py` correctness path、opportunistic batch count 或 compact source builder caps。

## 流程备注

AgentMiMo 在 re-review 期间误创建了只包含自身 artifact 的 commit `c0a34ef1`，违反了 review gate 的 no-commit 指令。该 commit 只增加 `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-mimo.md`，不修改生产代码、测试或控制文档。总控不回滚该 commit，后续 accepted deepreview commit 将记录完整 gate 状态。

## 验证

总控复验：

- `python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py` -> 91 passed
- `pyright` -> 0 errors
- `git diff --check` -> passed
- `rg "REQUIRED_BEFORE_DISPATCH|REBUILD_BEFORE_DISPATCH" dayu/host tests/host docs/host/issues-implementation-control.md` -> no hits

## 后续

进入 accepted deepreview commit，然后准备 PR update push。
