# WU-RUNTIME-02 Slice 2 Implementation Artifact

## Gate / Role

- **Gate**: implementation
- **Role**: implementation specialist
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Slice**: Slice 2 - 外层取消后的 shielded task 等待改为有界等待
- **Approved plan**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Non-goals observed**: 未提交、未 push、未创建 PR；未修改 Host / Engine / Service / UI / Fins / Config；未修改 DB schema、public API、`__all__` 或 `LaneClaimToken.released` public field。

## Changed Files

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/README.md`
- `docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md`

Controller 已存在的 `docs/host/host-core-followup-implementation-control.md` dirty bookkeeping 修改保持未触碰。

## Implemented Plan Items

- 新增 `_OUTER_CANCELLATION_CLEANUP_GRACE_SECONDS: Final[float] = 0.25`，并为 cleanup timeout、late observer diagnostic、tracked / untracked release、refresh、claim fallback 增加稳定私有日志消息常量。
- 新增 `_outer_cancellation_cleanup_timeout_seconds(coordinator)`，返回 `busy_timeout_seconds + grace`，并提供中文 docstring。
- 新增私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`，不加入 `__all__`。
- `_await_task_after_outer_cancellation(task, *, timeout_seconds)` 改为 monotonic deadline 有界等待；timeout 时抛私有错误；repeated outer cancel 下继续让出事件循环；不会取消底层 shielded task。
- 为 cleanup timeout 后放弃等待的 claim / release / refresh task 注册私有 done callback observer，消费 late result / exception：
  - late acquired claim 记录 TTL fallback diagnostic；
  - late claim / release / refresh failure 记录带 lane、claim、operation / error type 的诊断日志。
- 更新 `_try_claim_once`、`_refresh_token`、`_release_token`、`_release_untracked_claim`：
  - cleanup timeout 后对外仍抛最初 `asyncio.CancelledError`；
  - tracked release timeout 不标记 token released，保留后续 release / close 重试机会；
  - refresh timeout 不标记 token lost / released；
  - untracked claim / release timeout 记录 TTL fallback diagnostic；
  - 底层在上限内完成时保留原有 success / lost / RuntimeLaneError 语义。
- 更新 lane 单测：
  - cleanup timeout helper 计算测试；
  - `_await_task_after_outer_cancellation` timeout 不取消底层 task 测试；
  - 原 repeated cancel helper 测试补传 `timeout_seconds`；
  - acquire public path 的 claim cleanup timeout + late acquired observer 测试；
  - tracked release cleanup timeout 后 token 保留并可重试测试。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py -q`
  - Result: `36 passed in 1.22s`
- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - Result: `39 passed in 2.03s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check -- dayu/runtime/lane.py tests/runtime/test_lane.py tests/README.md`
  - Result: passed, no output

## Docs Decision

- `tests/README.md` updated because Slice 2 added explicit runtime lane test coverage for bounded outer-cancellation cleanup and late result observation.
- No root README / `dayu/README.md` update: public usage, CLI/config entry points, layering, and runtime lane stable responsibility did not change.

## Residual Risks / Uncovered Areas

- Cleanup timeout deliberately does not kill the underlying Python thread; this is the selected plan behavior. Capacity recovery for abandoned successful untracked claims relies on existing TTL stale cleanup.
- Late successful tracked release is consumed by observer but does not mutate `LaneClaimToken.released`; the token remains retryable as required by the approved plan.
- No DB schema or public API migration coverage was added because this slice intentionally makes only private runtime control-flow changes.

## Stop Status

- Slice 2 implementation complete.
- No blocking open question found.
- No need to stop for public API, schema, or hanging task/thread limitations.
