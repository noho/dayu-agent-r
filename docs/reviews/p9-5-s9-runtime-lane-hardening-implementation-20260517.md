# P9.5 S9 Runtime Lane Hardening Implementation

日期：2026-05-17

## 动机判断

S9 动机成立。`dayu.runtime.lane` 是层中立 capacity primitive，只能表达运行期容量 claim。若 acquire 取消、heartbeat/token lost、release failure 或 controller close 语义不稳定，上层 Host dispatch 很容易把运行期容量状态误读成 Host truth、Attempt owner 或 recovery 证据。因此本轮只收紧 runtime lane 自身的取消与 cleanup 行为，不引入 Host state、EventLog、lease/fencing/takeover 或 recovery proof。

Stop condition 未触发：实现不需要修改 Host / Engine / Fins，不需要新增 Host 状态机，也不改变 lane token 的非真源定位。

## 改动文件

- `dayu/runtime/lane.py`
  - 新增 typed `_await_task_after_outer_cancellation` helper，在外层 task 已取消后继续等待已 shield 的 DB claim / release task 完成，抵抗 repeated outer cancellation 打断 cleanup。
  - untracked release 普通失败现在写 warning 并透传 `RuntimeLaneError`；取消路径仍保留 `asyncio.CancelledError` 作为调用方可见结果。
  - release failure 与 heartbeat close reason 使用模块级常量，避免新增诊断魔法字符串。
- `tests/runtime/test_lane.py`
  - 新增 repeated outer cancellation during claim cleanup 测试，证明已插入 claim 会被清理且调用方仍看到 `CancelledError`。
  - 新增 untracked release 普通失败 warning + `RuntimeLaneError` 测试。
  - 新增 `LaneController.close(reason=...)` 遇到单个 held token release 失败时仍继续 best-effort release 其它 token 的测试。
- `dayu/README.md`
  - 同步 runtime lane 当前行为：协作式取消优先 timeout，heartbeat/token lost 与 release failure 通过 runtime lane error 或 warning 暴露。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py`：31 passed。
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：通过，无输出。

## 文档决策

本次触及 `dayu/runtime/lane.py`，按 AGENTS.md 检查 `dayu/README.md` runtime section。该 section 已描述 lane public behavior，需要同步取消优先级与 release / heartbeat 可观测错误语义，因此做了最小更新。未修改其它 README，因为没有 Host / Engine / Fins 行为或用户命令入口变化。

## 残余风险

- `close(reason=...)` 仍是 best-effort release：若底层 SQLite release 失败，失败 claim 只能依赖 TTL stale cleanup；这是 runtime capacity 语义，不提升为 Host recovery proof。
- lane 仍不承诺 FIFO、公平性、lease/fencing、Attempt owner、takeover 或跨机器分布式容量。
- idle scheduler sleeping task 的 Host dispatch 覆盖留给 S10，未在 runtime lane 内越界模拟 Host scheduler。

## 停止状态

implementation 完成；未 commit、未 push、未创建 PR。
