# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S8 Implementation（AgentCodex）

## 状态

`ready-for-code-review`

本轮仅实施 S8：Layer-neutral Runtime Partial Cleanup Completion。未 commit、push、创建 PR、修改总控文档或进入后续 gate。

## 第一性原理与 owner 判定

1. `start()` / `close()` 的前置布尔值是并发 gate，不是副作用完成证明。`Process.start()` 一旦被尝试，同一 handle 就不能恢复 start 权限；但 start 是否成功、process/queue 哪些 cleanup 已完成必须独立记录。
2. process、process join、process handle close、queue close 与 feeder cleanup 是不同资源 checkpoint。一个 checkpoint 失败不能阻止独立 queue cleanup；下一次 close 只能补未完成步骤，不能重复已经成功的破坏性操作。
3. caller cancellation 只取消本 caller 对 cleanup 的等待，不应取消资源 cleanup 本身。正确 owner 是 handle 内的 private single-flight task，由 async lock 保护并通过 `asyncio.shield()` 等待。
4. Lane 的 `_closed=True` 正确拥有“拒绝新 acquire / 唤醒 waiter”语义；`_close_completed=True` 则只能由“heartbeat 已停止、`_held_tokens` 为空、本轮无 error”共同证明。failed token 必须继续留在 `_held_tokens`，供下一次 close 重试。
5. 两个修复都是层中立 runtime resource lifecycle，不属于 Host/Engine/Service/Fins。Host 调用方只传播 cleanup error，不拥有重复补偿逻辑。

## 实际变更

### `dayu/runtime/interruptible_process.py`

- 保留 `_started` start-attempt gate，并新增私有 `_start_completed`，start exception 后同一 handle 始终不可重试。
- 保留 `_closed` close-started gate，并新增 `_cleanup_completed`、private async lock 与 single `_cleanup_task`。
- 新增私有 `_ProcessCleanupProgress`，分别记录：
  - process signal；
  - bounded process join；
  - process handle close；
  - queue close；
  - queue cancel-join；
  - queue feeder join。
- close caller 通过 `asyncio.shield()` 等待 private task；caller cancellation 不取消 cleanup。取消后的 task exception 由 observer 消费并记录，后续 close 仍可读取结果或启动补偿 attempt。
- pre-spawn start failure 跳过不合法的 kill/join，但仍执行 process.close 与 queue cleanup；模拟 PID 已建立的 post-spawn failure 执行 kill/join/process.close。
- process checkpoint 首错被保留并最终抛出，但 queue cleanup 始终继续。
- `Queue.join_thread()` 前先调用 documented `cancel_join_thread()`，明确使用 cancel-join 语义避免无 timeout API 形成无界 feeder join。

### `dayu/runtime/lane.py`

- 新增 private `_close_lock`、single `_close_task` 与 `_heartbeat_stopped` completion marker。
- 首次非空 close reason 保持真源；后续 concurrent/retry close 不覆盖。
- private close attempt 只停止 heartbeat 一次，并对 held token 做 snapshot best-effort release。
- release 成功沿既有 owner 从 `_held_tokens` 删除；失败 token 保留，首错原样传播。
- `_close_completed=True` 只在 heartbeat stopped、held tokens 为空且本轮无 error 的分支写入。
- caller cancellation 不取消 private close task；concurrent callers 共享同一 attempt 的成功或异常。
- heartbeat error 只在尚无 close reason 时写入稳定 reason，不覆盖更早的 close reason。

未修改 `dayu/runtime/__init__.py`：新增状态均为 resource owner 私有实现，不需要扩大 package public export。

### Tests

- `tests/runtime/test_interruptible_process.py`
  - pre-spawn / post-spawn `Process.start()` failure 与同 handle non-retry；
  - kill、process join、process close、queue close、cancel-join、queue join 六个 transient checkpoint failure；
  - 每个失败后 queue cleanup 与 retry-only-incomplete-step；
  - kill/join/process-close/queue-close/queue-join 五个 caller cancellation checkpoint；
  - concurrent callers 共享 single cleanup task 与同一 failure。
- `tests/runtime/test_lane.py`
  - 两 token 中首次 release 失败：成功 token 删除、failed token 保留、completed=false，第二次只重试 failed token；
  - concurrent close + caller cancellation 共享 cleanup，heartbeat stop/release 各一次；
  - concurrent callers 观察同一 release failure，后续 close 重试 remaining token；
  - 首次 close reason 稳定。
- `tests/runtime/test_lane_multiprocess.py`、`tests/runtime/test_import_boundary.py` 与 Host close/dispatch suites 全量回归通过。
- Host production 未改；既有 `test_scheduler_close_marks_cleanup_done_when_cleanup_raises` 继续证明调用方传播 lane cleanup error，不在 Host 实现补偿 cleanup。

## S8 必须反例覆盖

1. **pre-spawn failure**：同 handle 第二次 start 拒绝；close 只执行 process-valid close 与 queue close/cancel-join/join；新 handle 可正常 start/close。
2. **post-spawn failure**：fake 在设置 PID/alive 后抛 start error；同 handle 不可重试；close kill/join/process.close，最终无 live fake process。
3. **cleanup checkpoint exceptions**：六 checkpoint 参数化测试证明首错传播、独立 queue cleanup 继续、成功步骤不重复、第二次 close 补齐未完成步骤。
4. **caller cancellation**：五 checkpoint 参数化测试由 callback/barrier 定位取消点；public caller 收到 `CancelledError`，private cleanup task 继续，第二 caller/close 最终完成。
5. **concurrent process close**：两个 caller 共享同一 task、只执行一套 cleanup并收到同一 exception instance；后续 retry 完成。
6. **Lane partial release**：capacity=2，首次只让第一 token release 失败；第二 token 成功移除，failed token 保留，`_close_completed=False`；第二 close 只重试第一 token并提交 completed。
7. **Lane concurrent close/cancel/heartbeat**：barrier test 证明 first reason 稳定、heartbeat stop 一次、release 一次、一个 caller cancellation 不影响另一 caller与最终 completed；共享 failure test 证明 concurrent callers 不启动两套 release。
8. **层中立与调用方传播**：runtime AST import-boundary、Host scheduler/open-host suites 均通过；没有 Host production 补偿或 runtime 反向依赖。

所有新增并发测试使用 `threading.Event`、callback 或 task barrier；没有以随机 sleep 次数作为 race correctness oracle。

## 验证结果

### Required pytest

```text
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q

210 passed in 6.26s
```

### Required pyright

```text
python -m pyright dayu/runtime/ tests/runtime/ tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py

0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n "_started|_closed|cleanup|join_thread|cancel_join_thread" dayu/runtime/interruptible_process.py
```

分类：

- `_started` 只作为 start-attempt gate；`_start_completed` 才允许 wait/interrupt 操作。
- `_closed` 只作为 close-started/start-rejection gate；幂等 return 读取 `_cleanup_completed`。
- private lock/task 提供 single-flight；六个 cleanup checkpoint 均有独立 success marker。
- `cancel_join_thread()` 明确先于 `join_thread()`，使用 documented cancel-join 语义，不存在裸 feeder join completion 假设。

```text
rg -n "_close_completed = True|_held_tokens|close_task|close_lock" dayu/runtime/lane.py
```

分类：

- `_close_lock` / `_close_task` 只拥有 concurrent close single-flight。
- 成功 release 的唯一 `_held_tokens.pop(...)` 仍在 token release/lost owner。
- `_close_completed=True` 唯一命中位于 `_heartbeat_stopped` 校验和 `_held_tokens` 空校验之后；错误分支先抛出，不会提交 completed。

```text
rg -n "dayu\.(engine|host|service|ui|fins)" dayu/runtime
```

结果只命中 `dayu/runtime/__init__.py` 的架构说明 docstring；无 Python import 命中。`tests/runtime/test_import_boundary.py` 的 AST scan 已通过。

```text
git diff --check
```

结果：无输出。

## README 判断

- `dayu.runtime` 当前没有独立 README，且本轮没有新增 public export、配置、用户入口或跨层装配语义，因此不修改根 README、`dayu/README.md` 或其它 package README。
- tests 覆盖矩阵发生实质变化，命中 `tests/README.md` 职责：已补充 partial start/cleanup、single-flight caller cancellation、Lane remaining-token retry 与 heartbeat completion 测试说明。

## Residual risk

- `cancel_join_thread()` 表达“close 时不再等待 queue feeder 刷新”的 documented cleanup 选择；handle close 已拒绝新操作，close 不承诺保留尚未被 wait 消费的业务结果。这与既有 close 资源释放语义一致，不改变 process result contract。
- 若承载 private cleanup task 的整个 event loop 被外力直接销毁，Python async task 无法继续；S8 保证的是 cooperative caller cancellation / concurrent close 下 completion，不扩张为进程级 event-loop crash recovery。该边界由 runtime 调用方的 loop lifecycle 拥有，不是当前 slice blocker。
- 未发现未分类或阻塞 code review 的 S8 residual risk。

## 结论

S8 stop condition 未触发：pre/post-spawn、全部 cleanup checkpoints、caller cancellation、process/lane concurrent close、Lane partial release retry、multiprocess lane与 runtime import boundary 全部通过；无同 handle start retry、无 failed token completed short-circuit、无 Host 反向依赖。

最终状态：`ready-for-code-review`。
