# WU-CLI-SMOKE-01-R1 Slice 2 Code Review（AgentDS）

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-cli-smoke-01-r1`
- Base: `70ccda60`（accepted Slice 1 commit）
- Review target: 工作树相对 base 的 Slice 2 变更
- Output file: `docs/reviews/wu-cli-smoke-01-r1-slice2-code-review-ds.md`
- Included scope:
  - 新增：`tests/host/transient_stream_support.py`、`tests/host/test_transient_delta_stress.py`、`tests/cli/test_transient_slow_consumer_path.py`
  - 修改：`tests/host/test_transient_delta.py`、`tests/host/test_watch_session_events.py`
  - 修改：`dayu/README.md`、`dayu/host/README.md`、`dayu/service/README.md`、`tests/README.md`
  - 实施 artifact：`docs/reviews/wu-cli-smoke-01-r1-slice2-implementation-codex.md`
- Excluded scope:
  - controller-owned `docs/host/issues-implementation-control.md` 与 `docs/phaseflow-umbrella-optimization-control.md`（pre-existing 未提交修改，本 review 只读不评）
  - 生产 Python 代码（Slice 2 无修改）
- Parallel review coverage: 无（本 review 由主 reviewer 逐文件走读全部变更）

## 实现 artifact 结论验证

Codex implementation artifact 声明的核心结论是：**无生产 correctness defect，因此不做补偿性修复**。本 review 对每条声明做了独立证据复核：

| 声明 | 复核结论 |
|------|---------|
| stress 经真实 `open_host`/Host ingest 各发布 ≥1000 条三类 delta，EventLog 零 row | **成立**（见 §1） |
| durable Run/Attempt/terminal/final/outbox 同源 | **成立**（见 §1） |
| capacity 256 慢 watcher overflow 确定、快 watcher/terminal/Run 不受影响 | **成立**（见 §2） |
| typed error 原样（UNAVAILABLE/retryable/slow_consumer） | **成立**（见 §2） |
| publish-before-wait、wait-before-publish、drain-clear-publish、overflow/close wakeup barriers 真正确定 | **成立**（见 §3） |
| E2E 真实走 Host→Service→CLI，DS-F02 闭环 | **成立**（见 §4） |
| `cast(Host, probe)` 未掩盖生产语义 | **成立**（见 §4，非阻塞 finding F-1） |
| attach/no replay/first delta、cancel/aclose/missing/durable read failure/Host close cleanup 完整 | **成立**（见 §5） |
| `transient_stream_support.py` 非 God helper | **成立**（见 §6） |
| `_PublicHostHandle` / hub probe 与 SQLite corruption 是合理 owner-level 测试边界 | **成立**（见 §7） |
| 四份 README 只描述当前实现且职责准确 | **成立**（见 §8） |
| 无本 Slice 应修的真实 production defect 被测试绕开 | **成立**（见 §9） |

---

## Findings

### 未发现阻塞级 (blocking) 实质性问题

经逐路径走读全部生产代码（`dayu/host/transient_delta.py`、`dayu/host/open_host.py:_PublicHostHandle`、`dayu/service/entrypoint_runtime.py`、`dayu/cli/thinking.py`）与全部 Slice 2 测试/README 变更，未发现 correctness、stability、semantic ownership drift、contract violation、resource leak、task leak、死锁、数据损坏、或架构约束违反。

以下 findings 按严重度排列；所有非阻塞项均附带直接证据与修复建议。

---

### F-1-非阻塞-[低]-E2E 测试 `cast(Host, probe)` 在生产 `Host` Protocol 上做局部实现替换

- **入口/函数**: `test_real_transient_slow_consumer_falls_back_once_with_original_typed_error` → `submit_entrypoint_turn_and_wait(cast(Host, probe), ...)`
- **文件(行号)**: `tests/cli/test_transient_slow_consumer_path.py:289`
- **输入场景**: E2E 慢消费者路径需要阻塞 Service 的首次 `get_run` 以制造 relay 满→overflow 链
- **实际分支**: `_SlowConsumerHostProbe` 只实现 `watch_session_events`、`submit_followup`、`get_run`、`read_outbox_terminal_items` 四个方法，其余 `Host` Protocol 方法（`cancel_run`、`close_session`、`purge_session`、`ensure_session`、`get_session` 等约 15+ 方法）均未实现
- **预期行为**: 测试 probe 应对未使用方法提供明确的 `raise NotImplementedError` 或至少显式声明局部实现意图
- **实际行为**: `cast(Host, probe)` 在类型层面静默绕过，运行时若 submit path 未来新增对 probe 未实现方法的调用，会在测试中产生 `AttributeError` 而非明确的"此 probe 不支持该操作"诊断
- **直接证据**:
  - `_SlowConsumerHostProbe` 类定义（行 129-227）：只声明了 4 个方法
  - `cast(Host, probe)` 调用（行 289）
  - 对比：生产 `entrypoint_runtime.py:_attach_watcher` 使用 `cast(ClosableHostSessionEventIterator, ...)`（行 1007-1010），但该 cast 目标是 Protocol 而非完整 Host 接口，且生产代码明确知道需要哪个窄接口
- **影响**: 低。当前 submit path 确实只使用 probe 实现的 4 个方法；但若未来 `submit_entrypoint_turn_and_wait` 增加对 `Host` 其他方法的调用（如 `cancel_run`、`close_session`），测试会在运行时静默失败而非在类型检查时捕获
- **建议改法和验证点**:
  1. 给 `_SlowConsumerHostProbe` 未实现的方法加 `raise NotImplementedError` 桩（约 15 个方法），或
  2. 在 `cast` 处加注释说明这 4 个方法是 submit path 的闭集，且 probe 的其余 `Host` 方法可通过 `__getattr__` 委托给 `self._host`
  3. 两种方案均可；不接受"这是测试所以没关系"的论点
- **修复风险（低）**: 方案 1 需要随 `Host` Protocol 变更同步维护桩方法；方案 2 是更务实的自文档化修复
- **严重程度（低）**: 当前行为正确，只是可维护性弱信号

---

### F-2-非阻塞-[低]-E2E 测试 `asyncio.sleep(0.05)` 作为稳定性断言

- **入口/函数**: `test_real_transient_slow_consumer_falls_back_once_with_original_typed_error`
- **文件(行号)**: `tests/cli/test_transient_slow_consumer_path.py:322`
- **输入场景**: 验证 Host subscription overflow 后 Service relay 不再交付新 item
- **实际分支**: `_wait_for_yielded_count` 先通过确定性轮询（`for _attempt in range(1_000)`）到达精确 `blocked_yield_count`，然后用 `asyncio.sleep(0.05)` 做补充稳定性检查
- **预期行为**: barrier 验证应完全确定
- **实际行为**: `asyncio.sleep(0.05)` 是时间依赖的弱检查；理论上 0.05s 内 relay 可能恰好完成一次 drain-cycle 并交付新 item，使断言因调度时机而偶发失败
- **直接证据**:
  - `await asyncio.sleep(0.05)`（行 322）
  - `assert probe.yielded_count == yielded_before_probe`（行 325）
  - 主 barrier `_wait_for_yielded_count` 是确定性的（行 414-432），该 sleep 只是补充验证
- **影响**: 极低。主 barrier 已是确定性的；sleep 是附加的 sanity check。在极端调度下（如 CI 极度拥塞）理论上有 0.05s 内 relay 产生新 item 的可能，但 Service `get_run` 仍被阻塞，drain loop 不会前进，因此实际不可能
- **建议改法和验证点**: 可将 sleep 替换为第二轮 `_wait_for_yielded_count(probe, blocked_yield_count)` 复用确定轮询（超时设 0.5s），消除对时间的隐性依赖。或保留现状并接受其极低风险
- **修复风险（低）**: 替换为确定性轮询无风险
- **严重程度（低）**: 不影响 correctness 证明

---

## 九项 adversarial 核验逐项证据

### 1. Stress 真实经 open_host / Host ingest、零 EventLog rows、durable 同源

**证据链**（`tests/host/test_transient_delta_stress.py`）：

- 入口：`open_host(options)`（行 78）→ 真实 production composition root（`dayu/host/open_host.py:1531`）→ `_PublicHostHandle` + `HostTransientDeltaHub` + scheduler + durable actor 全链路
- Worker：`TransientStreamWorkerFactory` → `_TransientStreamWorker.accept()` → `_TransientStreamHandle.events()`（`transient_stream_support.py:237-264`）→ 产生真实 `EngineEvent` 实例 → Host ingest → `HostTransientDeltaHub.publish()`（`transient_delta.py:434-464`）
- 三类 delta 各 1,000：`_DELTA_COUNT_PER_TYPE = 1_000`（行 38）
- Fast watcher 通过真实 `HostSessionEvent` → `HostTransientDelta` 穷举类型计数（`_collect_until_terminal`，行 143-178），结果严格 `== expected_counts`（行 105）
- EventLog 零 row（行 121-124）：
  ```python
  assert event_log_type_count(options.db_path, EngineEventType.CONTENT_DELTA.value) == 0
  assert event_log_type_count(options.db_path, EngineEventType.REASONING_DELTA.value) == 0
  assert event_log_type_count(options.db_path, EngineEventType.TOOL_CALL_DELTA.value) == 0
  ```
- Durable Run/Attempt/terminal/final/Outbox 同源（行 126-140）：
  - `durable.run_terminal_event_id == terminal.event_id`（行 135）
  - `durable.run_terminal_event_sequence == terminal.event_sequence`（行 136）
  - `durable.terminal_event_id == terminal.event_id`（行 137）
  - `matching_outbox[0].terminal_event_id == terminal.event_id`（行 117）
  - `matching_outbox[0].final_answer == terminal.final_answer`（行 119）
  - `run.status is RunStatus.SUCCEEDED`（行 109）
- `event_log_type_count` 经 `sqlite3.connect` 直接读生产 `TABLE_EVENT_LOG`（`transient_stream_support.py:307-324`）
- `read_transient_durable_snapshot` 从 `TABLE_HOST_RUNS`、`TABLE_HOST_ATTEMPTS`、`TABLE_EVENT_LOG` 三张 owner table 读取同源快照（行 327-410），对 row 缺失、数量错误、字段类型非法均 `raise AssertionError`

**结论：PASS。** 3×1,000 delta 经完整 production Host ingest→hub.publish→subscription→watcher→EventLog/durable table 全链路证明三类 EventLog row 均为 0，durable facts 保持一致。

---

### 2. Capacity 256 慢 watcher overflow 确定性、快 watcher/terminal/Run 不受影响、typed error 原样

**证据链**（`tests/host/test_watch_session_events.py:test_capacity_slow_watcher_overflow_does_not_block_fast_watcher_or_terminal`）：

- 入口：`open_host(options)`（行 568）→ 完整 production path
- 慢 watcher：未消费，258 条 delta（86+86+86）到达后 queue 满 → `put_nowait` 触发 `QueueFull` → `_overflowed = True` + `_hub._detach(self)`（`transient_delta.py:329-336`）
- 慢 watcher 前缀精确 256（行 601）：`assert len(slow_prefix) == 256`
- 慢 watcher 的 `HostApiError` 精确匹配 contract（行 609-616）：
  ```python
  assert overflow.code is HostApiErrorCode.UNAVAILABLE
  assert overflow.retryable is True
  assert overflow.detail == HostUnavailableDetail(
      component="session_live_stream", reason_code="slow_consumer"
  )
  ```
- 快 watcher：接收全部 258 条 mixed delta（行 602）：`assert fast_counts == expected_counts`
- 快 watcher terminal：SUCCEEDED + final answer（行 603-605）
- Run 状态：`run.status is RunStatus.SUCCEEDED`（行 607）
- Worker cancel：`factory.cancel_reasons == []`（行 608）
- EventLog 三类 zero-row（行 618-620）
- Durable snapshot 同源（行 626-629）

**溢出机制的精确时序**：
- `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256`（`transient_delta.py:26`）
- `HostTransientDeltaSubscription._offer` 内 `put_nowait` → `QueueFull` → detach（行 329-336）
- Merge loop `_watch_session_events_after` 在每次 `drain_nowait()` 后检查 `overflow_error()`（行 987-989、1002-1004、1014-1016）
- Overflow 后的 `drain_nowait()` 排空已接受的连续前缀（256 items），然后 `overflow_error()` 返回错误 → raise

**结论：PASS。** 慢 watcher 在精确 256 条前缀后以原 `HostApiError(UNAVAILABLE/retryable/slow_consumer)` 结束；快 watcher 收到全部 258 条 + terminal；Run 保持 succeeded；三类 EventLog row 为 0。

---

### 3. 四类 deterministic barriers

**证据链**（`tests/host/test_transient_delta.py`）：

**3a. publish-before-wait（`test_subscription_publish_before_wait_is_level_triggered`）**
- 先 publish → `_offer` 内 `_ready.set()`（`transient_delta.py:336`）
- 后 `wait_ready(0.1)` → `_is_ready()` 检查 queue 非空 → 即时返回 True（行 273-274）
- 证明：level-triggered readiness 不依赖事件到达顺序

**3b. wait-before-publish（`test_subscription_wait_before_publish_wakes_at_barrier`）**
- `_WaitEnteredEvent` 证明 waiter 已进入 `asyncio.Event.wait()` 后 publish（行 62-67）
- `controlled_event.wait_entered.wait()` 完成 → publish → waiter 被 `_ready.set()` 唤醒
- 确定性证明：publish 的 set 必定发生在 waiter 的 wait 已进入之后

**3c. drain-clear-publish 交界（`test_subscription_drain_clear_publish_intersection_rechecks_owner_state`）**
- `_PublishOnClearEvent.clear()` 在首次 clear 时先 publish（触发 `_ready.set()`），再执行真实 `super().clear()`（行 57-60）
- 这模拟最不利交错：publish 的 set 被随后的 clear 清除
- `_refresh_readiness()` 在 clear 后调用（由 `drain_nowait` → `_refresh_readiness` 行 257），`_is_ready()` 返回 True → 重新 `_ready.set()`（行 367-372）
- 证明：owner state recheck 修复 clear 覆盖 set 的竞态

**3d. overflow/close wakeup（`test_subscription_overflow_and_close_states_remain_ready`）**
- overflow：`_TRANSIENT_WATCH_BUFFER_CAPACITY + 1` 条 publish 后 drain → `overflow_error() is not None` → `wait_ready(0.1)` 立即返回 True（`_is_ready()` 检查 `_overflowed`）
- close：`_WaitEnteredEvent` 证明 waiter 在 waiting → `hub.close()` → `_close_from_hub` 调用 `_ready.set()`（行 349）→ waiter 被唤醒

**结论：PASS。** 四类 barrier 均为真正确定性验证（Event 线性化点 + owner state recheck），无 sleep-based 偶然。

---

### 4. DS-F02 闭环：真实 Host→Service→CLI，非 wrapper/cast/fake 掩盖

**证据链**（`tests/cli/test_transient_slow_consumer_path.py`）：

**全链路追踪：**

1. **Engine worker → Host ingest → publish**：
   - `TransientStreamWorkerFactory` 产生 `EngineEvent`（`transient_stream_support.py:237-264`）
   - Host ingest 在 durable transaction 成功后调用 `HostTransientDeltaHub.publish()`（`transient_delta.py:434-464`）
   - 证据：test 使用 `open_host(options)` + `factory`（行 284），与 stress test 同路径

2. **Host public subscription → typed merge**：
   - `_SlowConsumerHostProbe.watch_session_events()` 包装真实 `_PublicHostHandle.watch_session_events()`（行 155-169）
   - 返回 `_ObservedHostSessionEventIterator`：只记录观测，原样透传真实 `HostSessionEvent`（行 72-127）
   - 证据：所有 item 均为真实 Host iterator 产出

3. **Service bounded relay → backpressure**：
   - `submit_entrypoint_turn_and_wait`（行 287-306）→ 内部 `_create_watch_and_wait_runtime`（`entrypoint_runtime.py:1013-1033`）
   - `queue = asyncio.Queue(maxsize=256)` → `_drain_host_events(watcher, queue)` → `await queue.put(event)`（行 1050）
   - 证据：使用真实 production `submit_entrypoint_turn_and_wait`，非 mock

4. **CLI renderer**：
   - `CliThinkingRenderer`（行 275-281）→ 真实 `record()` 路径（`cli/thinking.py:87-117`）
   - `render_prompt_terminal_result`（行 378-382）→ 真实 CLI output 路径

5. **Overflow → Outbox fallback**：
   - Service relay 满 256 → `await queue.put` 阻塞（行 1050）
   - Host iterator 暂停 → Host subscription 继续接收 → overflow（`_offer` 行 329-336）
   - Merge loop 检测 overflow → raise `HostApiError`（行 987-989）
   - Drain task 捕获 → `await queue.put(_WatcherFailure(error=exc))`（行 1054）
   - Service `_drain_available_watcher_items` 处理 `_WatcherFailure`（行 1181-1188）
   - `_record_watcher_failure` 保存消息（行 1514-1530）
   - `_should_read_outbox_terminal` 因 `watcher_failure_message is not None` 返回 True（行 1154）
   - Outbox read 返回 terminal（行 1130-1137）

6. **Typed error identity 保持**（行 354-360）：
   ```python
   assert overflow.code is HostApiErrorCode.UNAVAILABLE
   assert overflow.retryable is True
   assert overflow.detail == HostUnavailableDetail(
       component="session_live_stream", reason_code="slow_consumer"
   )
   ```

7. **Terminal/Outbox 同 identity**：
   - `matching_outbox[0].terminal_event_id == terminal.terminal_event_id`（行 368）
   - `durable.run_terminal_event_id == terminal.terminal_event_id`（行 371）

8. **CLI 只展示一次**（行 383-388）：
   - `stdout.getvalue().count(_FINAL_ANSWER) == 1`
   - `thinking_stderr.getvalue().count("Thinking:") == 1`

**`cast(Host, probe)` 评估**：
- `_SlowConsumerHostProbe` 未实现完整 `Host` Protocol（只实现了 submit path 需要的 4 个方法）
- 但 submit path 确实只调用 `watch_session_events`、`submit_followup`、`get_run`、`read_outbox_terminal_items`，probe 对这些方法全部转发到真实 `self._host`
- `get_run` 的阻塞是唯一注入点，通过 `asyncio.Event` 控制，不改变返回值的语义
- 此模式与生产 `entrypoint_runtime.py:_attach_watcher` 的 `cast(ClosableHostSessionEventIterator, host.watch_session_events(...))`（行 1007-1010）一致：都是对已知返回类型做窄接口 cast
- 差异：probe 的 cast 目标是完整 `Host` Protocol 而非窄 Protocol，范围更宽。见 F-1

**结论：PASS。** DS-F02 六步全链路闭环，无 fake/mock 替代真实 Host ingest、Host subscription、Service bounded relay 或 CLI renderer。`cast(Host, probe)` 是窄接口测试探针，不掩盖生产语义。

---

### 5. Attach/no replay/first delta、cancel/aclose/missing/durable read failure/Host close cleanup

**证据链**（`tests/host/test_watch_session_events.py` + `tests/host/test_transient_delta.py`）：

| 场景 | 测试 | 断言 |
|------|------|------|
| attach 前 delta 不 replay | `test_watch_does_not_replay_pre_attach_transient_and_keeps_first_post_attach_delta`（行 718-755） | `first_post_attach_delta.run_id == second.accepted_run_id`、`!= first.accepted_run_id` |
| attach 后首个 delta 不丢 | 同上 | `first_post_attach_delta.run_id == second.accepted_run_id`、terminal 同 Run |
| never-started `aclose()` | `test_watch_never_started_first_cancel_missing_and_host_close_cleanup`（行 658-714） | `_subscription_count` 从 1 → 0（行 669-671） |
| missing Session → NOT_FOUND | 同上 | `missing_exc.value.code is HostApiErrorCode.NOT_FOUND`、`retryable is False`（行 676-678）、subscription count 回 0（行 679） |
| 首次 `__anext__` cancel | 同上 | `first_next.cancel()` → subscription count 回 0（行 681-687） |
| started terminal 后 `aclose()` | 同上 | terminal received → `aclose()` → subscription count 回 0（行 689-696） |
| Host close → 正常结束 | 同上 | `await host.close()` → watcher `StopAsyncIteration`（行 698-705）、subscription count 回 0（行 706） |
| closed handle → `HostClosedError` | 同上 | `pytest.raises(HostClosedError)`（行 707-708） |
| 后续 iteration cancel 不取消 Run | `test_watch_cancel_after_first_delta_detaches_without_cancelling_run`（行 718-755） | cancel 后 Run 保持 RUNNING（行 747-750）、`factory.cancel_reasons == []`（行 751）、terminal 后 Run SUCCEEDED（行 754-756） |
| 首次 durable failure → public error + detach | `test_watch_first_and_subsequent_durable_failures_are_public_and_detach`（行 758-820） | `HostApiError(INTERNAL_ERROR/retryable=False)`（行 795） + subscription count 回 0（行 796） |
| transient 后 durable failure → public error + detach | 同上（subsequent 路径） | while 循环消费合法 progress prefix 直到 corrupt row（行 820-828）→ typed error（行 836-837） + subscription count 回 0（行 838） |
| 早期 cancel 不取消 Run | `test_consumer_early_cancel_does_not_cancel_run_or_write_eventlog`（已有，行 531-655） | Run 保持 SUCCEEDED（行 655） |
| drain_nowait 拒绝 terminal fence 后同 Run delta | `test_subscription_terminal_fence_detach_and_hub_close_are_local`（已有，行 191-215） | `mark_run_terminal` 后同 Run delta 被 `drain_nowait` 过滤 |

**Durable failure 测试修正说明**：
- subsequent 路径（行 800-838）：先消费合法 transient delta（`await _next_transient(watcher)`），再等待 Run terminal（`await _wait_run_terminal`）
- 然后 corruption 注入 + 消费合法 durable progress prefix（`while True: event = await anext(watcher)`）直到 corrupt row 触发异常
- 这正确处理了 durable read 在 corrupt row 之前的合法 progress prefix
- 实施期间"误判为必须立刻抛错"的 bug 已修正：原测试错误要求 transient 后下一项立刻是 corrupt terminal，忽略了合法 durable progress prefix

**Cleanup 幂等性保障**（`dayu/host/open_host.py`）：
- `_ClosableHostSessionEventIterator.aclose()`（行 1269-1283）：`_closed` flag 防重入，`finally` 块保证 subscription.close() 必执行
- `__anext__` 的 `except BaseException` 路径也调用 `self.aclose()`（行 1265-1267）
- Subscription `close()` 幂等（`transient_delta.py:307-319`）：`if self._closed: return`

**结论：PASS。** 全部 attach/cancel/aclose/missing/durable failure/Host close 路径覆盖，subscription count 精确验证，无悬挂。

---

### 6. `transient_stream_support.py` 572 行是否 God helper

**逐类分析**：

| 符号 | 行数（含 docstring） | 职责 |
|------|---------------------|------|
| `TransientStreamCounts` | 52 | 三类 delta 计数的 frozen dataclass + validation |
| `TransientDurableSnapshot` | 28 | Owner table 快照的 frozen dataclass |
| `TransientStreamWorkerFactory` | 61 | 创建可控 worker 的 factory |
| `_TransientStreamWorker` | 29 | 薄 accept wrapper |
| `_TransientStreamHandle` | 60 | EngineEvent stream generator |
| `transient_stream_open_host_options` | 19 | OpenHostOptions 便利构造 |
| `event_log_type_count` | 15 | EventLog row 计数 SQL 查询 |
| `read_transient_durable_snapshot` | 86 | 三张 owner table 同源快照读取 |
| `_content_delta_event` | 16 | content EngineEvent 构造 |
| `_reasoning_delta_event` | 16 | reasoning EngineEvent 构造 |
| `_tool_call_delta_event` | 23 | tool-call EngineEvent 构造 |
| `_final_answer_event` | 19 | final answer EngineEvent 构造 |
| `_required_int_cell` / `_required_int` / `_required_str` | 43 | SQLite cell 类型安全校验 |

- **职责收敛**：每个类/函数单一职责；无 God object/function/dataclass
- **无重复**：EngineEvent 构造函数按类型分为 4 个独立 helper，无复制粘贴
- **类型严格**：全部签名使用具体类型；`_SQLiteCell` TypeAlias 明确声明允许的 SQLite cell 类型；无 `Any`、`object`、`hasattr`/`getattr`
- **不推导业务状态**：factory 只创建 worker 和观测状态；SQL reader 只从 owner table 读取，不构造新的业务语义
- **不绕过 Host public contract**：worker 实现 `LocalEngineWorker` Protocol → Host dispatch → ingest → publish 全链路；factory 的 `create_worker` 签名与生产 contract 一致
- **docstring 完整**：所有 public 和 private 函数均有中文 docstring，含参数/返回值/异常
- **572 行计数说明**：约 200+ 行为 docstring 与空行；实际逻辑代码约 350 行

**结论：PASS。** 不是 God helper。职责按 factory/dataclass/SQL reader/event constructor 明确分离，无过度设计或重复。

---

### 7. `_PublicHostHandle` / hub probe 与 SQLite corruption 测试边界

**`_subscription_count` 评估**（`test_watch_session_events.py:1211-1223`）：

- 访问路径：`host._transient_delta_hub.subscription_count(session_id)`
- owner 分析：subscription count 的生命周期 owner 是 `HostTransientDeltaHub`，它是 `_PublicHostHandle` 的内部组件；Hub 不通过 `Host` Protocol 暴露 subscription count
- 测试需求：验证 detach/cleanup 后 subscription 确实被回收 —— 这无法通过 `Host` public API 观察
- 防护：`isinstance(host, _PublicHostHandle)` 断言（行 1222-1223），非 production handle 时 fail fast
- 判定：**合理**。这是验证内部 lifecycle contract 所需的白盒边界；`isinstance` guard 防止测试被 fake/mock 静默通过

**`_replace_event_payload` 评估**（`test_watch_session_events.py:1231-1260`）：

- 操作：直接 `sqlite3.connect` → `UPDATE TABLE_EVENT_LOG SET payload_json` → 写入畸形 JSON
- 目的：注入 durable corruption 以验证 Host read path 的 public error mapping
- 恢复：每次注入后调用第二次 `_replace_event_payload` 恢复原始 payload（行 780-782、816-819）
- 判定：**合理**。SQLite corruption 无法通过 Host public API 制造；测试在受控 tmp_path 内操作，注入后恢复；断言的是 Host 对 corruption 的 public error 行为（`INTERNAL_ERROR/retryable=False`），不是 SQLite 内部状态
- 风险：若恢复失败（test crash/abort），不影响生产数据（tmp_path）

**结论：PASS。** 两个探针均为必要的 owner-level testing boundary；有适当的 guard 和恢复机制。

---

### 8. 四份 README 职责准确性

**`dayu/host/README.md`**（diff 行 43-128）：
- 记录 `watch_session_events` 同步 attach 语义 ✓
- 记录 `HostSessionEvent` = `HostEvent | HostTransientDelta` 联合 ✓
- 记录容量 256、慢消费者 typed overflow 与隔离 ✓
- 记录 terminal fence、detach/close 语义 ✓
- 记录三类 delta 零 EventLog row ✓
- 删除旧 thinking 术语，替换为 transient delta 描述 ✓
- 新增 `transient_delta` 模块到目录树 ✓
- 稳定边界描述从 `HostEvent view` 改为 `HostSessionEvent live view` ✓
- Stream 术语增加 `Host transient delta stream` 与 `Host session live stream` ✓

**`dayu/README.md`**（diff 行 1-42）：
- Service 装配增加"有界 relay 消费 durable/transient"描述 ✓
- 投递与派生视图增加三类 delta live-only 边界说明 ✓
- 核心术语增加 `HostTransientDelta`、`HostSessionEvent` ✓
- Host public contract 增加 `HostTransientDelta`、`HostSessionEvent` 到类型列表 ✓
- 范围准确：只描述跨层边界，不侵入 Host/Service 内部实现细节 ✓

**`dayu/service/README.md`**（diff 行 129-141）：
- 记录容量 256 有界 relay ✓
- 记录 `await queue.put` 背压链 ✓
- 记录 typed overflow → `_WatcherFailure` → Outbox fallback ✓
- 记录 content/tool-call delta 被忽略 ✓
- 术语从 `HostEvent activity/thinking` 改为 `HostSessionEvent` 联合 ✓

**`tests/README.md`**（diff 行 142-191）：
- 增加 transient delta stress 的 `-m stress` 运行命令 ✓
- 增加 `test_transient_delta.py` + `test_watch_session_events.py` 联合运行命令 ✓
- 更新 public run/wait/event API 覆盖说明，增加 transient delta 相关条目 ✓
- 增加 transient Host→Service→CLI regression 说明 ✓
- 增加 transient delta stress 独立条目 ✓

**结论：PASS。** 四份 README 只描述当前已实现行为，职责边界准确，未出现超前描述或承诺未实现功能。

---

### 9. 是否有本 Slice 应修的真实 production defect 被测试绕开

**逐项排查**：

| 潜在风险 | 排查结果 |
|---------|---------|
| overflow 后 drain task 的 `await queue.put(_WatcherFailure(...))` 也因 queue 满而阻塞 | **非 defect**。Service drain loop 恢复消费后 queue 有空位，`put` 解除阻塞。这是确定的背压传导，不是死锁。 |
| 多 watcher 并发 attach/detach 的 hub subscription dict 竞态 | **非 concern**。hub 所有操作在 opener event loop 线程同步执行（`publish`、`subscribe`、`_detach`、`close` 均无 `await`），无并发写入。 |
| Host close 与 watcher iteration 并发时可能的 double-close | **已有防护**。`HostTransientDeltaSubscription.close()` 幂等（`if self._closed: return`）；`_ClosableHostSessionEventIterator.aclose()` 幂等（`if self._closed: return`）。 |
| `_ready` Event 在 overflow 后被 detach 的 subscription 上仍被 set | **正确行为**。`_ready.set()` 在 `_offer` 末尾无条件执行（行 336），即使已 detach。这确保 merge loop 的 `wait_ready` 被唤醒以检测 overflow。 |
| `transient_stream_support.py` 中 `_content_delta_event` 的 `delta=""` 空字符串是否产生无效 `HostTransientDelta` | **非 defect**。`HostContentDelta.text_delta` 在 `__post_init__` 中允许空字符串（plan §4.1："保留 Engine contract 的原始字符串，包括空串/空白"）。 |
| E2E 测试使用的 `thinking_stderr` 和 `terminal_stderr` 是否验证了完整的 `--no-thinking` 路径 | **非本 Slice 范围**。`--no-thinking` 由既有 CLI test suites 覆盖（`test_prompt_command.py`、`test_interactive_command.py`），不在 Slice 2 变更内。 |
| 生产代码 `_watch_session_events_after` 的 merge loop 在 `len(batch.events) == 0` 时用 `wait_ready` 等待，是否有遗漏 terminal 的风险 | **已有防护**。`wait_ready` 超时后返回 `_is_ready()` 结果（行 282），然后循环回到 while 条件检查 health_gate 并读下一批 durable batch。terminal 由 durable actor 的 EventLog append 保证最终可见。 |
| `_SESSION_WATCH_POLL_INTERVAL_SECONDS` 的值是否可能导致 delta 交付延迟 | **非 concern**。poll interval 只影响空 durable batch 时的等待；delta 到达会通过 `_ready.set()` 立即唤醒 `wait_ready`。 |

**结论：PASS。** 经 adversarial 排查，未发现被测试绕开的 production correctness defect。

---

## 与 accepted plan §9 Required validation 对照

Slice 2 对 plan §9 全部验证命令的执行结果（来自 implementation artifact §Validation 命令与结果）：

| 命令 | 结果 |
|------|------|
| `test_transient_delta.py --cov=dayu.host.transient_delta --cov-fail-under=80` | 9 passed, coverage 91% |
| Host focused suites（10 files） | 295 passed |
| Service focused suites（3 files） | 51 passed |
| CLI focused suites（5 files） | 109 passed |
| 全量 `tests/host tests/service tests/cli` | 2816 passed, 8 skipped, 6 deselected |
| `-m stress test_transient_delta_stress.py` | 1 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| 静态 grep（4 条） | 第 1、3、4 条零命中；第 2 条仅命中统一 transient classification |

---

## Open Questions

- 无。

---

## Residual Risk

以下风险在 accepted plan §12.2 中已明确接受，本 Slice 测试未试图消除：

1. **overflow/detach/断线/Host close/崩溃/重启后 transient delta 永久丢失**：live-only contract 的明确边界，非 data loss defect。
2. **容量 256 是内部固定值，无生产负载调优数据**：本 Slice 只证明 boundedness 和隔离；plan 明确不暴露为 public knob。
3. **durable event 与 transient delta 无跨域总序**：只承诺各自内序及同 Run terminal fence。
4. **E2E 使用可控 LocalEngineWorker，非真实外部 LLM provider**：Host publisher/subscription、Service relay/fallback、SQLite durable store/Outbox 和 CLI renderer 均为 production path。

新增残余风险（本 review 识别）：

5. **F-1（低）**：`cast(Host, probe)` 的窄接口实现，若 submit path 未来扩展可能产生运行时 `AttributeError`。
6. **F-2（极低）**：`asyncio.sleep(0.05)` 作为稳定性补充断言，在极端调度下理论上有微弱不确定性。

---

## Final Verdict

**PASS.** Slice 2 全部 9 项 adversarial 核验通过。未发现要求 blocking 或需要立即修复的 production correctness、stability、semantic ownership drift、contract violation 或架构约束违反。两项非阻塞 findings（F-1、F-2）为低严重度可维护性建议。

所有测试均沿真实 production 代码路径验证：Host ingest → hub.publish → subscription → merge loop → Service bounded relay → CLI renderer。deterministic barriers 覆盖四类 wakeup 交错。stress 证明 3×1,000 delta 零 EventLog row 且 durable facts 同源。lifecycle cleanup 覆盖全部 attach/detach/cancel/error/close 路径。README 准确反映当前实现。
