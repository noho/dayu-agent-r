# P9.5 S9 Runtime Lane Hardening — Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR。
- Slice: S9 Runtime Lane Hardening。
- Design source: `docs/host/design.md`。
- Control source: `docs/host/implementation-control.md`。
- Implementation artifact: `docs/reviews/p9-5-s9-runtime-lane-hardening-implementation-20260517.md`。
- Code review artifacts:
  - `docs/reviews/p9-5-s9-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s9-code-review-ds-20260517.md`

## Controller Judgment

Accepted。

S9 的动机成立：`dayu.runtime.lane` 是层中立 capacity primitive，不是 Host truth。若 acquire cancellation、release cleanup、heartbeat/token lost 或 controller close 行为不稳定，上层 Host dispatch 会更容易把 runtime capacity 状态误读为 Attempt owner、lease、fencing 或 recovery proof。当前实现只收紧 runtime lane 自身的取消与 cleanup 语义，没有引入 Host / Engine / Fins 依赖，也没有新增 Host state、EventLog、lease、fencing、takeover 或 recovery proof。

## Review Findings

- AgentMiMo review：0 blocking findings，0 non-blocking findings。唯一 info observation 为 `_await_task_after_outer_cancellation` 的 `task.result()` 会透传 task 自身异常；当前 claim / release 同步路径已把 SQLite 与 runtime 错误结构化为 `RuntimeLaneError`，该 observation 不构成 S9 blocker。
- AgentDS review：0 blocking findings，0 non-blocking findings。Residual risks 均指向既有 non-goals：`close()` best-effort release 失败后依赖 TTL cleanup、无 FIFO / fairness / lease / fencing、idle scheduler sleeping task 留给 S10。
- Controller 裁决：不需要 fix。当前实现满足 S9 对 cancellation precision、untracked release failure warning/error、close best-effort release 和 runtime import boundary 的要求。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py`：31 passed。
- `source .venv/bin/activate && pytest tests/runtime`：93 passed。
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`：0 errors。
- `git diff --check`：clean。
- Weak typing scan for S9 touched production/test files found no `Any` / `object` / `hasattr` / `getattr` usage.

## Residual Risk

- `LaneController.close(reason=...)` 仍是 best-effort release；SQLite release 失败的 claim 只能依赖 TTL stale cleanup。该风险属于 runtime capacity availability，不是 Host recovery proof。
- lane 仍不承诺 FIFO、公平性、lease / fencing、Attempt owner、takeover 或跨机器分布式容量；这些仍是明确 non-goals。
- idle scheduler sleeping task interaction 需要 Host dispatch 语义，按 plan 留给 S10 覆盖，不在 S9 越界实现。

## Final Decision

S9 accepted。可以提交 S9 implementation / review artifacts，并推进总控文档到 P9.5 S10。
