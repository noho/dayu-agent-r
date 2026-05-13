## Work Gate

fix

## Source Review Artifact

- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-controller-adjudication-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 2: `dayu.runtime.lane` cross-process coordinator

## Controller-Accepted Finding IDs

- M1/D1
- M2
- D2

## Per-Finding Fix Status

- M1/D1: fixed
  - `LaneController.open` 已改为 async classmethod。
  - DB parent 准备和 SQLite DB 初始化通过 `asyncio.to_thread` 执行，避免 async 调用方阻塞事件循环。
  - `tests/runtime/test_lane.py` 与 `tests/runtime/test_lane_multiprocess.py` 中所有调用点已同步改为 `await LaneController.open(...)` 或在同步父进程测试中用 `asyncio.run(...)`。
- M2: fixed
  - heartbeat loop 已新增 `RuntimeLaneError` 分支。
  - controller 记录首次 heartbeat error，停止接受新 acquire，唤醒 pending acquire。
  - 后续 acquire 会抛出首次记录的结构化 `RuntimeLaneError`。
  - 新增 focused test `test_heartbeat_runtime_error_stops_new_acquire`。
- D2: fixed
  - heartbeat loop 中 `RuntimeLaneClaimLostError` 只标记对应 token lost/released 并继续处理其它 token。
  - 单个 claim lost 不再关闭整个 controller。
  - `close()` 即使 controller 已因 heartbeat error / closed 状态停止新 acquire，也会 best-effort release 剩余 held tokens，并保持 idempotent。
  - 新增 focused test `test_heartbeat_lost_claim_does_not_close_controller`。

## Finding Title Status Updates

- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
  - `F-01` 标题更新为 `已修复`，并补充 fix status。
  - `F-02` 标题更新为 `已修复`，并补充 fix status。
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
  - `Finding 1` 标题更新为 `已修复`，并补充 fix status。
  - `Finding 2` 标题更新为 `已修复`，并补充 fix status。

## Changed Files

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
- `docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`

## Validation

- command: `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - result: passed, `16 passed`
- command: `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py -q`
  - result: passed, `3 passed`
- command: `source .venv/bin/activate && python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- command: `git diff --check`
  - result: passed

## New Risks / Open Questions / Plan Deviation

- new risk: 无。
- new open question: 无。
- plan deviation: 无。`LaneController.open` 已回到 approved async public API shape。

## Residual Risks And Uncovered Areas

- risk: SQLite 高并发 busy 抖动仍可能影响 acquire latency。
  - classification: later phase or work unit
  - owner or destination: Phase 11 multi-process hardening / runtime lane 压力观察。
- risk: 跨进程 clock skew 会影响 stale cleanup 精确时间。
  - classification: later phase or work unit
  - owner or destination: Phase 11 multi-process hardening。
- risk: workspace runtime lane DB cleanup policy 未定义。
  - classification: later phase or work unit
  - owner or destination: 后续 Host composition root / workspace lifecycle phase。

## Artifact Path

`docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`
