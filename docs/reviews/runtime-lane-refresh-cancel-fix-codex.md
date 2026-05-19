# Runtime Lane Refresh Cancel Fix — AgentCodex

日期：2026-05-19

## 动机判断

动机成立。`LaneController._refresh_token()` 通过 `asyncio.shield(refresh_task)` 保护 SQLite 线程事务不被外层取消打断，但原实现没有处理外层 `asyncio.CancelledError`。一旦 heartbeat task 或调用方在 refresh 事务进行中被取消，底层 refresh task 会继续执行，而 `_refresh_token()` 已退出，后续 `RuntimeLaneError` / `RuntimeLaneClaimLostError` 可能变成未收口 task exception，且该 task 不再有明确 owner。该问题违反 runtime task lifecycle 必须有 owner / cleanup 的约束。

## 修复

- `dayu/runtime/lane.py`
  - `_refresh_token()` 新增外层 `CancelledError` cleanup 分支，复用 `_await_task_after_outer_cancellation(...)` 持续等待 shielded refresh task 完成。
  - 底层 refresh 成功时先更新 `token.expires_at`，再重新抛出原始 cancellation。
  - 底层返回 `RuntimeLaneClaimLostError` 时先标记 token lost / released 并唤醒 waiter，再重新抛出 cancellation。
  - 底层返回 `RuntimeLaneError` 时记录结构化错误日志并重新抛出 cancellation，避免吞掉调用方取消或留下未收口异常。
- `tests/runtime/test_lane.py`
  - 新增 refresh 外层取消后底层成功、claim lost、runtime error 三条 deterministic 覆盖，证明 cleanup 已等待底层 task 完成，并按结果更新 `expires_at` / lost 状态或记录日志。
- `tests/README.md`
  - 同步 runtime lane 测试覆盖说明，把 shielded refresh cancellation cleanup 纳入当前测试事实。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py -q`
  - `26 passed in 0.54s`
- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - `29 passed in 1.40s`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/host`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过，无输出。

## 残余风险

- refresh 取消 cleanup 中的 `RuntimeLaneError` 仍以日志暴露，调用方可见结果保持 `CancelledError`；这与 claim / release 的取消 cleanup 语义一致，但运行期容量 row 可能需要依赖后续 heartbeat / release / TTL cleanup 收口。
- 本修复只处理 runtime lane refresh task lifecycle，不改变 lane 的非 Host truth 定位，也不引入 lease / fencing / recovery proof。
