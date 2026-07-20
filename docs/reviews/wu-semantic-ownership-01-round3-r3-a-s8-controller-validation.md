# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S8 Controller Validation

## Decision

`ready-for-code-review`

控制侧复核确认 S8 实现动机成立：原缺陷不是调用方补偿不足，而是 runtime owner 把 close-start gate 当作 cleanup completion 使用。修复位置保持在 `dayu.runtime` 的资源生命周期 owner 内，没有把语义下沉到 Host 或测试夹具。

## Scope Check

- Production diff 仅触及 `dayu/runtime/interruptible_process.py` 与 `dayu/runtime/lane.py`。
- Test/doc diff 仅触及 `tests/runtime/test_interruptible_process.py`、`tests/runtime/test_lane.py` 与 `tests/README.md`。
- `tests/README.md` 的职责是记录当前测试分层与维护约定；本轮新增 runtime partial cleanup / single-flight / retry 覆盖，属于该 README 的同步范围。
- 未修改 Host production、Engine、Service、Fins、UI 或 public runtime exports。

## Contract Evidence

- `InterruptibleProcessHandle.start()` 保持 `_started` 作为同 handle start-attempt gate，新增 `_start_completed` 表达 wait/interrupt 可用性。
- `InterruptibleProcessHandle.close()` 新增 `_cleanup_completed`、`_cleanup_progress`、private `_cleanup_lock` 与 `_cleanup_task`，cleanup completion 只能由 process/queue checkpoint 全部成功证明。
- Process signal/join/close 与 queue close/cancel-join/join 分别记录完成状态；首错传播但独立 queue cleanup 继续。
- Public close caller cancellation 通过 `asyncio.shield()` 不取消 private cleanup task，后续 close 可读取同一 task 或补偿未完成步骤。
- `LaneController.close()` 保持 `_closed` 作为拒绝新 acquire / 唤醒 waiter gate，新增 `_close_lock`、`_close_task` 与 `_heartbeat_stopped`。
- `_close_completed=True` 的唯一写入在 heartbeat stopped 且 `_held_tokens` 为空之后；failed token 保留在 owner 集合中供下一次 close 重试。
- runtime import boundary scan 只命中 `dayu/runtime/__init__.py` 的架构说明 docstring；AST import boundary 测试通过，未出现业务层反向依赖。

## Validation

```text
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q

210 passed in 6.18s
```

```text
source .venv/bin/activate
python -m pyright dayu/runtime/ tests/runtime/ tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py

0 errors, 0 warnings, 0 informations
```

```text
rg -n "_started|_closed|cleanup|join_thread|cancel_join_thread" dayu/runtime/interruptible_process.py
rg -n "_close_completed = True|_held_tokens|close_task|close_lock" dayu/runtime/lane.py
rg -n "dayu\.(engine|host|service|ui|fins)" dayu/runtime
git diff --check
```

Source scan classification:

- `_started` / `_closed` no longer act as proof of resource cleanup completion.
- Process cleanup checkpoints and Lane held-token completion have owner-local progress markers.
- `rg dayu\.(...)` only found runtime package documentation text; no Python import violation.
- `git diff --check` produced no output.

## Review Handoff Focus

Reviewers must verify:

- same-handle `start()` retry remains rejected after pre/post-spawn failure;
- process close uses single-flight cleanup and retries only incomplete checkpoints;
- caller cancellation cannot cancel private cleanup;
- queue cleanup continues after process checkpoint failure;
- lane close completes only after heartbeat stopped and held tokens are empty;
- failed lane tokens are retried without re-releasing successful tokens;
- no Host production compensation or runtime reverse dependency was introduced.

## Residual Risk

No blocker found before code review. The only intentional boundary is that cooperative caller cancellation is protected; full event-loop destruction remains outside S8 and belongs to the caller's loop lifecycle owner.
