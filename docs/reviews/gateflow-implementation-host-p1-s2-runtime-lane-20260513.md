## Work Gate

implementation

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 2: `dayu.runtime.lane` cross-process coordinator

## Approved Plan

`docs/host/phase1-public-contract-runtime-plan.md`

## Assigned Scope

- allowed files/modules:
  - `dayu/runtime/lane.py`
  - `tests/runtime/test_lane.py`
  - `tests/runtime/test_lane_multiprocess.py`
  - `tests/runtime/test_import_boundary.py`
  - `dayu/README.md`
  - `tests/README.md`
  - `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- explicit non-goals:
  - 不接入 Host dispatch。
  - 不实现 Host store 默认路径、Host cancel propagation、Attempt owner、lease / fencing、recovery proof、EventLog identity。
  - 不修改 `dayu/runtime/__init__.py`、Host / Engine / Fins / Service / UI 代码。

## Changed Files

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`

## Plan Items Implemented

- 新增 `LaneConfig`、`LaneOwner`、`SQLiteLaneCoordinatorConfig`、`LaneClaimToken`、acquire outcome dataclasses、`LaneAcquireOutcome` TypeAlias、`LaneController` 与 runtime lane error classes。
- `LaneController.open(...)` 为 async classmethod，显式接收 `SQLiteLaneCoordinatorConfig(db_path=...)`；`owner=None` 时使用随机 owner id、当前 pid、`process_start_token=None`；DB parent 准备与初始化通过 `asyncio.to_thread` 执行。
- 独立 SQLite runtime lane DB 初始化，设置 `PRAGMA journal_mode=WAL` 与 per-connection `busy_timeout`，schema 只保存 runtime capacity claim 字段。
- successful acquire 的 stale cleanup、active count、insert 在同一个 `BEGIN IMMEDIATE` SQLite 短事务内完成。
- waiting acquire 使用 poll / event wakeup，不持有长事务；支持 non-blocking、正 timeout、默认 timeout、无限等待、CancellationToken cancellation、`Task.cancel()` 透传。
- token `refresh()` / controller-managed heartbeat / token `release()` 已实现；release 幂等并按 `lane_name + claim_id + owner_id` 删除 claim；单 token lost 只标记该 token，不关闭整个 controller；不可恢复 heartbeat `RuntimeLaneError` 会停止新 acquire 并暴露结构化错误。
- `LaneController.close()` 幂等，停止新 acquire，唤醒 pending acquire 为 cancelled，并 best-effort release 当前 tokens。
- 多进程测试覆盖共享 DB capacity invariant、持有时 non-blocking timed out、release 后其它进程 acquire、crash 后 TTL stale cleanup eventual acquire。
- README 同步 runtime lane 当前能力与测试命令。

## Not Implemented

- `dayu/runtime/__init__.py` docstring 未更新：本 handoff 明确禁止编辑该文件，且实现不需要该变更。
- Host dispatch 集成、Host cancel 与 lane cancel 组合、Attempt owner、lease / fencing、recovery proof、EventLog ordering 均为 explicit non-goals。

## Validation

- command: `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - result: passed, `16 passed`
  - key assertions: config validation、DB schema/WAL、async open、acquire/heartbeat/release、timeouts、CancellationToken cancellation、Task.cancel propagation、close semantics、heartbeat RuntimeLaneError handling、single token lost isolation、claim lost refresh、single-process capacity invariant、multi-process capacity invariant、release and stale cleanup paths。
- command: `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py -q`
  - result: passed, `3 passed`
  - key assertions: runtime import boundary covers `lane.py` and no runtime reverse dependency on Engine / Host / Service / UI / Fins。
- command: `source .venv/bin/activate && python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- command: `git diff --check`
  - result: passed

## Documentation Update

- updated:
  - `dayu/README.md`: runtime lane 从设计要求同步为当前已实现层中立能力。
  - `tests/README.md`: 增加 runtime lane 单进程 / 多进程测试命令与覆盖范围。
- not updated and reason:
  - `dayu/runtime/__init__.py`: handoff 禁止编辑；无实现 blocker。
  - 根目录 `README.md`: 本 slice 不改变用户安装、配置、CLI、trace/render 入口或常用工作流。

## Plan Gaps / Controller Questions

- 无。

## Residual Risks And Uncovered Areas

- risk: SQLite 高并发下 busy 抖动仍可能影响 acquire latency。
  - classification: later phase or work unit
  - owner or destination: Phase 11 multi-process hardening / runtime lane 压力观察；当前 slice 已验证 capacity invariant 不破坏。
- risk: 跨进程 clock skew 会影响 stale cleanup 精确时间。
  - classification: later phase or work unit
  - owner or destination: Phase 11 multi-process hardening；当前语义只承诺 runtime capacity eventual cleanup，不承诺 Host truth。
- risk: workspace runtime lane DB cleanup policy 未定义。
  - classification: later phase or work unit
  - owner or destination: 后续 Host composition root / workspace lifecycle phase；当前 slice 只使用显式 db_path 与测试 tmp_path。

## Completion Signal

met: `dayu.runtime.lane` 满足 Phase 1 runtime capacity primitive，unit + multi-process tests、import boundary、pyright 与 diff check 均通过。

## Stop Condition Status

none hit

## Artifact Path

`docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
