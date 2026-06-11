# WU-PROJ-01 Residual Aggregate Deepreview Fix

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview fix
- Date: 2026-06-11
- Agent: AgentCodex
- Artifact: `docs/reviews/wu-proj-01-residual-aggregate-deepreview-fix-codex.md`

## 修改摘要

- `dayu/host/memory_repair.py`
  - 删除 `MemoryProjectionRepairPurpose.REQUIRED_BEFORE_DISPATCH`。
  - 删除 `MemoryProjectionRepairPurpose.REBUILD_BEFORE_DISPATCH`。
  - 未保留兼容 alias、wrapper 或 re-export。
- `tests/host/test_memory_repair.py`
  - 将仅用于构造 `MemoryProjectionCatchupBudget` 的旧 required / rebuild purpose 引用改为 `BEST_EFFORT_AFTER_COMMIT`。
  - 保持测试意图不变：这些用例验证 bounded-loop budget、target reached、checkpoint 推进和 `budget=None` correctness path，不验证旧 purpose 分支。
- `docs/host/issues-implementation-control.md`
  - WU-PROJ-01 行记录当前事实：CAP/S3/S4 focused set `174 passed`。
  - 保留 S3/S4 `tests/host/test_dispatch_scheduler.py` `68 passed`、`pyright` 0 errors、`git diff --check` passed 信息。

## 直接证据

- 总控裁决 `docs/reviews/wu-proj-01-residual-aggregate-deepreview-controller-adjudication.md` 接受 AGG-F1 / AGG-F2：
  - required / rebuild correctness path 已改为 `budget=None`。
  - `purpose` 只应作为 budget 日志 / diagnostic metadata。
  - 需要删除不再代表生产路径的 required / rebuild enum 值。
- 修改后搜索结果：
  - `rg "REQUIRED_BEFORE_DISPATCH|REBUILD_BEFORE_DISPATCH" dayu/host tests/host docs/host/issues-implementation-control.md` 无生产代码、允许测试或控制文档残留。
  - 剩余旧 enum 名称只出现在 controller adjudication artifact 中，作为 accepted finding / fix 要求的历史描述，未改写为当前事实。
- 非目标核对：
  - 未修改 `dayu/host/dispatch.py`。
  - 未修改 opportunistic batch count。
  - 未重新给 source builder 加 cap。
  - 未修改 production dispatch / projection correctness 行为；required / rebuild catch-up 仍由既有 `budget=None` 路径表达。

## 验证结果

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py`
  - 结果：`91 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && git diff --check`
  - 结果：passed，无输出

## README 判断

- 已阅读 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。
  - 本轮没有改变 `dayu.host` package 的公共接口、架构边界、状态机、关键执行路径或扩展点。
  - 删除的是已无生产 consumer 的内部 enum 值，且 correctness path 已由既有 `budget=None` 表达。
  - 因此不更新 `dayu/host/README.md`。
- 已阅读 `tests/README.md`。
  - 本轮没有新增测试层级、测试目录职责或常用命令。
  - 仅更新既有测试中的 enum 引用以匹配当前生产语义。
  - 因此不更新 `tests/README.md`。

## 剩余风险

- 当前 fix gate 无未分类 residual risk。
- 未覆盖项：本轮只运行用户要求的三文件 focused tests、pyright 和 diff-check；未重新运行 PR 级完整 Host affected test set。
- 既有 aggregate deepreview 中 rejected 的 opportunistic batch count / source builder cap 议题保持原裁决，本轮未处理且不应处理。

## 完成状态

- Accepted fixes AGG-F1 / AGG-F2 已修复。
- 未进入 re-review 或后续 gate。
- 未 commit、push、PR 或 merge。
