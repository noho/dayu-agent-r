# Host Phase 1 Slice 2 Code Review Controller Adjudication

## Work Gate

code review controller adjudication

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Assigned Slice

Slice 2: `dayu.runtime.lane` cross-process coordinator。

## Reviewed Artifacts

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- AgentMiMo code review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md`
- AgentDS code review: `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md`
- Approved plan: `docs/host/phase1-public-contract-runtime-plan.md`

## Summary

两份 review 均确认 Slice 2 没有 blocking finding，验证命令通过，且无 Host / Engine / Fins / ToolRuntime 夹带。

Controller 裁决：两个低 / 中等级 finding 影响 approved public API shape 与 heartbeat ownership 语义，必须在当前 slice 修复后进入 focused re-review。信息类 observation 不要求修改。

## Controller Decisions

### M1 / D1: `LaneController.open` 为同步方法，plan 指定为 async public API

- Source: AgentMiMo F-01, AgentDS Finding 1。
- Decision: accepted。
- Rationale: approved plan 明确 `LaneController.open` public API shape 是 `async def open(...) -> LaneController`。这是后续 Host composition root 可依赖的公共契约，不能通过 implementation artifact 事后改写为 sync。
- Required fix: 将 `LaneController.open` 改为 async classmethod，并同步所有 tests / child process helper 调用为 `await LaneController.open(...)` 或等价 async 调用。不得修改 approved plan。若需要保持同步内部初始化，可在 async 方法中用 `asyncio.to_thread` 包装 DB parent / init，避免阻塞 event loop。

### M2: heartbeat loop 未处理不可恢复 `RuntimeLaneError`

- Source: AgentMiMo F-02。
- Decision: accepted。
- Rationale: approved plan 要求 background heartbeat 遇到不可恢复 SQLite error 时记录 first heartbeat error、停止接受新 acquire，并让后续 acquire 返回 cancelled 或抛结构化 `RuntimeLaneError`。当前 task 异常逃逸且无人检查，会让调用方在错误窗口内误判仍持有 capacity。
- Required fix: 为 heartbeat loop 增加 `RuntimeLaneError` 分支，记录 first heartbeat error，停止新 acquire，唤醒 pending acquire，并确保后续 acquire 可观测该结构化错误或 cancelled outcome。增加 focused test 覆盖该行为。

### D2: 单个 claim lost 时 heartbeat loop 关闭整个 controller 且 close 不释放其它 held tokens

- Source: AgentDS Finding 2。
- Decision: accepted。
- Rationale: plan 区分单 token lost 与不可恢复 SQLite error。单个 token lost 应标记该 token lost / released，不应关闭整个 controller，更不应让其它 held tokens 只能等 TTL stale cleanup。
- Required fix: `RuntimeLaneClaimLostError` 分支只标记对应 token lost 并继续处理其它 token；不要关闭 controller。`close()` 必须能在 heartbeat 已标记 controller closed / errored 后仍 best-effort release 剩余 held tokens。增加 test 覆盖多个 held tokens 中一个丢失时其余 token 仍可 refresh / release。

### M3: `_format_datetime` 对 UTC datetime 冗余 `astimezone(UTC)`

- Source: AgentMiMo F-03。
- Decision: rejected-for-fix。
- Rationale: 该调用是无害防御性格式化，不影响 correctness、contract 或 performance。
- Required fix: none。

### D3: `_wait_before_retry` 期间不即时观察 CancellationToken

- Source: AgentDS Finding 3。
- Decision: rejected-for-fix。
- Rationale: cancellation 延迟上限为 `poll_interval_seconds`，符合当前 poll-based acquire 设计。实现已在每轮 acquire loop 和 wait 入口检查 token。
- Required fix: none。

## Required Fix Scope

Fix agent 允许修改：

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py` only if public API async shape requires boundary helper adjustment
- `docs/reviews/gateflow-implementation-host-p1-s2-runtime-lane-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-mimo-20260513.md` and `docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-ds-20260513.md` only for finding status updates
- fix artifact: `docs/reviews/gateflow-fix-host-p1-s2-runtime-lane-20260513.md`

Fix agent must not modify Host / Engine / Fins / Service / UI, `dayu.runtime.filelock`, `pyproject.toml`, `dayu/runtime/__init__.py`, `dayu/README.md` or `tests/README.md` unless a validation failure proves the code fix is impossible without a doc update.

## Required Validation

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py`
- `git diff --check`

## Next Gate

Proceed to fix gate for accepted findings M1/D1, M2 and D2. After fix, run MiMo + DS focused code re-review.

## Artifact Path

`docs/reviews/gateflow-code-review-host-p1-s2-runtime-lane-controller-adjudication-20260513.md`
