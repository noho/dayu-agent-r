# Code Review — awaiting poller latency testfix re-review (AgentDS)

## Scope

- Mode: current changes (re-review of testfix only)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-testfix-rereview-ds.md`
- Included scope: `tests/host/test_wait_poller_runtime.py`（仅 `test_background_loop_uses_not_ready_due_before_poll_interval` 的修改）
- Excluded scope: 生产代码、其他测试、DS F-1/F-3 结论（本轮不扩大审查范围）
- Parallel review coverage: 无（单 reviewer 逐行走读）
- 输入 artifact:
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-mimo.md`（MiMo F-1 flaky finding）
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-testfix-codex.md`（Codex testfix 记录）

## 检查点逐项验证

### 1. test_background_loop_uses_not_ready_due_before_poll_interval 是否改为等待 durable wait status RESOLVED

**已改为等待 durable truth。** 修改前（MiMo F-1 指出的问题）：

```python
# 旧代码：等待 proxy signal — adapter 内部计数
_wait_until(lambda: adapter.poll_count == 2)
```

修改后（`tests/host/test_wait_poller_runtime.py:685-688`）：

```python
# 新代码：等待 durable truth — DB 中的 wait record status
_wait_until(
    lambda: _read_wait(host._transaction_runner(), seeded.wait_id).status
    is WaitRecordStatus.RESOLVED
)
```

证据链：

- `_read_wait`（`tests/host/test_resolve_wait_command.py:914-928`）每次调用都执行 `transaction_runner.run_read(...)` 创建新的 SQLite 读事务，查询 `read_wait_record_by_id` 返回最新提交状态。不是缓存读取。
- `_wait_until`（`tests/host/test_wait_poller_runtime.py` 新增 `timeout_seconds` 参数，默认 1.0s）以 busy-loop 轮询 predicate，一旦 resolve 事务提交即检测到 `RESOLVED`。
- 等待条件与断言事实同源：都从 `_read_wait(...).status` 读取，不再把 `adapter.poll_count`（poll_wait 返回后的内部计数）误当成 resolve 提交完成信号。

**结论：成立。**

### 2. 是否仍保留 elapsed_seconds cadence 断言

**保留。** `tests/host/test_wait_poller_runtime.py:691-692`：

```python
elapsed_seconds = adapter.poll_started_at[1] - adapter.poll_started_at[0]
assert elapsed_seconds < 0.3
```

`poll_started_at` 由 `_SequenceAdapter.poll_wait()`（第 243 行新增 `self.poll_started_at.append(time.monotonic())`）在每次 poll 调用时记录时间戳。两次 poll 之间的实际间隔约为 `not_ready_observe_interval_seconds=0.01` + 线程调度开销。`< 0.3` 在 30 倍余量下足够宽松。

注意：第一个 `_wait_until(lambda: adapter.poll_count == 1)` 返回时 `poll_started_at[0]` 已写入（与 `poll_count` 递增在同一个 `poll_wait()` 调用内），第二个 `_wait_until` 返回时 `poll_started_at[1]` 已写入（second poll 先于 resolve）。两次读取均发生在各自时间戳写入之后，不存在索引越界风险。

**结论：成立。**

### 3. 目标测试重复运行 10 次是否可信

**独立验证通过。** 本轮执行：

```
=== Run 1-10 ===
1 passed in 0.33-0.34s (每次)
```

10/10 全部通过，每次耗时约 0.33s。Codex artifact 记录的 10/10 通过与本轮独立验证一致。

补充分析：修改前失败原因是测试线程在 resolve 事务提交前读到 `WAITING` 状态。修改后等待条件直接读 DB，线程调度不再影响断言正确性——即使 background thread 在 not_ready release 后被延迟调度，`_wait_until` 会持续等待直到 RESOLVED 提交。剩余的不确定性仅在于 `elapsed_seconds` 的绝对数值，但 0.3s 阈值对 0.01s 期望值有 30 倍余量，实际运行中 `elapsed_seconds` 约在 0.01-0.02s 量级。

**结论：可信。**

### 4. 受影响矩阵 / pyright / diff check 是否通过

**全部通过。**

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 受影响测试矩阵 | `pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_open_host_runtime.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_interactive_command.py -q` | **152 passed**, 3 warnings（edgar 依赖 deprecation，非本轮改动引入） |
| pyright | `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** |
| diff whitespace | `git diff --check` | **通过**（无输出） |

**结论：全部通过。**

## Findings

未发现实质性问题。

本轮修改仅涉及一个测试的等待条件（从 `adapter.poll_count == 2` 改为 `_read_wait(...).status is RESOLVED`），不触及生产代码，不回退 DS F-1 的生产修复。修改精准、最小化、有直接证据支撑。

## Open Questions

无。

## Residual Risk

- **`poll_started_at` 非线程安全访问**（沿用 MiMo Open Question 2）：background thread 写入 `list.append()`，test thread 读取索引。CPython GIL 下安全，但严格说是 data race。本轮不阻塞——影响面仅限测试，且 `elapsed_seconds` 断言有充足余量容忍微小计时偏差。
- **`elapsed_seconds < 0.3` 在极端 CI 负载下可能偶发失败**：如果 CI 机器线程调度延迟超过 0.3s（30 倍期望值），断言可能失败。当前 10 次运行中 `elapsed_seconds` 约在 0.01-0.02s，远低于阈值。classified as accepted for current test purpose。
- **真实 SEC / Fins 网络 smoke 未执行**：本轮 scope 为测试稳定性修复，不触达 Fins 下载或真实网络路径。classified as assigned to manual/real smoke validation。

## 结论

**Pass.**

MiMo F-1（`test_background_loop_uses_not_ready_due_before_poll_interval` ~60% 偶发失败）已关闭。修改将测试等待条件从 adapter 内部计数（proxy signal）改为 DB wait record status（durable truth），断言事实与等待条件同源。10 次独立重复运行全部通过，受影响测试矩阵 152 passed，pyright 0 errors，diff whitespace 通过。无新增 finding。
