# Code Review — testfix re-review (AgentMiMo)

## Scope

- Mode: current changes (re-review of testfix)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-testfix-rereview-mimo.md`
- Included scope: `tests/host/test_wait_poller_runtime.py`
- Excluded scope: 生产代码（本轮未修改）
- Parallel review coverage: 无
- Input artifact: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-testfix-codex.md`
- Background artifact: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-mimo.md`（本轮审查其 F-1 是否关闭）

## 检查点结果

### 1. 是否改为等待 durable wait status RESOLVED

**是。** diff 第 685-688 行：

```python
_wait_until(
    lambda: _read_wait(host._transaction_runner(), seeded.wait_id).status
    is WaitRecordStatus.RESOLVED
)
```

`_read_wait`（来自 `tests.host.test_resolve_wait_command`）通过 `transaction_runner.run_read` → `read_wait_record_by_id` 读取 durable store，返回 `WaitRecordRow`。等待条件与最终断言读取的事实同源（均为 durable DB），消除了原 race condition：`poll_count` 递增不等于 resolve 事务已提交。

### 2. 是否仍保留 elapsed_seconds cadence 断言

**是。** diff 第 691-692 行：

```python
elapsed_seconds = adapter.poll_started_at[1] - adapter.poll_started_at[0]
assert elapsed_seconds < 0.3
```

`poll_started_at` 在 `_SequenceAdapter.poll_wait` 入口处通过 `time.monotonic()` 记录（diff 第 240 行），测量的是两次 poll start 之间的真实墙钟间隔。`not_ready_observe_interval_seconds=0.01` 时，此断言验证 loop 未被 `poll_interval_seconds=0.5` 拖慢。cadence 验证逻辑未被削弱。

### 3. 目标测试重复运行 10 次是否可信

**可信。** 独立验证结果：

```
Run 1:  1 passed in 0.31s
Run 2:  1 passed in 0.32s
Run 3:  1 passed in 0.32s
Run 4:  1 passed in 0.31s
Run 5:  1 passed in 0.32s
Run 6:  1 passed in 0.31s
Run 7:  1 passed in 0.31s
Run 8:  1 passed in 0.32s
Run 9:  1 passed in 0.32s
Run 10: 1 passed in 0.32s
```

修复前 10 次运行 6 次失败，修复后 10/10 通过。失败率从 ~60% 降至 0%，修复可信。

### 4. 受影响矩阵 / pyright / diff check

- **受影响测试矩阵**: `152 passed, 3 warnings`。warnings 来自 `edgar` 依赖 deprecation，非本轮引入。✓
- **pyright**: `0 errors, 0 warnings, 0 informations`。✓
- **git diff --check**: 无输出，通过。✓

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- background timing 测试仍依赖本机线程调度来验证 `elapsed_seconds < 0.3`，但不再依赖调度顺序判断 durable terminal status。单线程 `drain_once_for_test()` 测试已覆盖主要 correctness，background 测试只捕捉 sleep cadence 回归。此风险 accepted。
- DS F-3（空轮询 next-due 额外 DB 读）仍 defer，本轮未涉及。

## 结论

**Pass.**

MiMo F-1 已关闭：`test_background_loop_uses_not_ready_due_before_poll_interval` 现在等待 durable wait status `RESOLVED`（通过 `_read_wait` → `read_wait_record_by_id`），断言读取的事实与等待条件同源。`elapsed_seconds` cadence 断言保留且未被削弱。独立验证 10/10 通过，受影响矩阵、pyright、diff check 均通过。

DS F-1、DS F-2 生产修复未被回退。本轮只修改测试同步条件，不涉及生产代码。
