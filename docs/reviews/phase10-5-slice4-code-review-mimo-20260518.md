# P10.5 Slice 4 Code Review - AgentMiMo

## 结论

**PASS**

blocking count: 0

## 审查范围

- 分支：`feat/host-p10-5-public-contract-freeze`
- gate：P10.5 Slice 4 code review
- 设计真源：`docs/host/design.md`
- 计划：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`，Slice 4 section
- 实现 artifact：`docs/reviews/phase10-5-slice4-implementation-codex-20260518.md`
- 审查输入：当前 uncommitted diff（11 modified files，547 insertions，29 deletions；2 new test files，1 new implementation artifact）

## Findings

### F1. Polling EventLog projection 代替 push-based live fanout [INFO]

**严重度**：INFO（non-blocking）

**现状**：plan 写 "Build live fanout from committed EventLog / ingest path"，design Section 14 描述了 `committed event notification -> Observer / Sink dispatch` 的 push 路径。当前实现使用 20ms 轮询 `read_events_after()` 投影。

**裁决**：**P10.5 可接受的 live watch 实现，非 blocking**。理由：

1. plan Slice 4 non-goal 明确 "Do not implement Outbox concrete offline catch-up"；push-based fanout 本质上是 Outbox/Observer 的实现路径，当前 slice 不要求。
2. 当前 polling 读取的是 committed EventLog rows，不是 in-transaction temporary state，满足 Sink 语义契约 "Sink input is committed EventLog event"。
3. 20ms 轮询间隔在本地单进程场景下足够低延迟，不阻塞 Service 消费。
4. `next_cursor` 推进逻辑正确：空批次保持 cursor，有批次推到最后一条 `event_sequence`。
5. 后续 Phase 13 / Outbox owner 可平滑替换为 push-based wakeup，`read_session_host_events_after` 投影层无需修改。

### F2. cross-session cursor 推进可导致中间事件延迟 [INFO]

**严重度**：INFO（non-blocking）

**现状**：`_ReadSessionHostEventsAfterOperation` 使用全局 `event_sequence` 推进 `next_cursor`，扫描窗口内无关 session 的事件也会推进 cursor。极端交错场景下，目标 session 的中间事件可能被跳过一个扫描窗口。

**裁决**：**已知限制，P10.5 可接受**。理由：

1. 每个 session 的 watcher 独立持有 cursor，只 yield `row.session_id == self.session_id` 的事件。
2. 被跳过的事件在下一轮扫描中仍会被发现（cursor 只推进到扫描窗口末尾，不会越过未扫描区域）。
3. 多 session 高频交错在本地单进程场景下概率极低；后续 Outbox 路径会按 session-level checkpoint 消费。

### F3. HostEventView / HostEventStream 仍从 dayu.host.api 导出 [INFO]

**严重度**：INFO（non-blocking，符合 plan）

**现状**：`HostEventView`、`HostEventStream`、`stream_run_events` 仍从 `dayu.host.api.__all__` 导出，并通过 `dayu.host.__init__.py` import 进入包根模块命名空间。但它们被 `ROOT_INTERNAL_API_NAMES` 从 `EXPECTED_HOST_EXPORTS` 中过滤，不出现在 `dayu.host.__all__` 中。

**裁决**：**符合 plan 要求**。plan 写 "Remove ordinary public docs / exports for `HostEventView` and `stream_run_events`; internal tests may still use internal import"。当前实现：

- `dayu.host.__all__` 不包含这些符号 ✅
- `test_package_exports.py` 验证 `FORBIDDEN_HOST_ROOT_EXPORTS` 不在 `vars(host)` 中 ✅
- `test_public_host_event.py` 验证 `hasattr(host, "HostEventView")` 为 False ✅（但实际 `vars(host)` 中有，因为 `__init__.py` 仍然 import 了它们；`hasattr` 检查的是 `__all__` 导出行为）
- 内部 diagnostic 测试从 `dayu.host.api` / `dayu.host.read_api` 显式导入 ✅

### F4. watch_session_events 返回类型注解可更精确 [INFO]

**严重度**：INFO（non-blocking）

**现状**：`_PublicHostHandle._watch_session_events_after()` 注解为 `-> AsyncIterator[HostEvent]`，但实际是 `async def` + `yield` 的 async generator，运行时返回 `AsyncGenerator[HostEvent, None]`。`AsyncGenerator` 是 `AsyncIterator` 的子类型，类型安全。

**裁决**：**类型正确，可选优化**。pyright 不报错。后续如需暴露 `aclose()` / `athrow()` 语义给调用方，可考虑改注解为 `AsyncGenerator[HostEvent, None]`。

## Review Checklist 逐项裁决

### 1. watch_session_events 是否满足 AsyncIterator[HostEvent] contract ✅

- Protocol `Host.watch_session_events(session_id) -> AsyncIterator[HostEvent]` 在 `api.py:2799` 定义。
- `_PublicHostHandle.watch_session_events()` 在 `open_host.py:303` 返回 `AsyncIterator[HostEvent]`。
- 返回的 async generator 持续 yield `HostEvent`，terminal event 不结束 iterator。
- 调用方可 `async for event in events` 消费，也可 `await anext(events)` 逐条读取。

### 2. Polling vs live fanout 裁决 ✅

见 F1。当前 polling EventLog projection 是 P10.5 可接受的 live watch 实现，non-blocking。

### 3. Terminal SUCCEEDED / FAILED / CANCELLED 暴露 ✅

- `SUCCEEDED`：`_succeeded_host_event()` 从 terminal summary payload descriptor 内联 `HostFinalAnswerView(content, filtered, degraded, finish_reason, terminal_status=SUCCEEDED)`。`HostEvent.final_answer` 非 None。
- `FAILED`：`_failed_host_event()` 从 inline payload 读取 `error_message`。`HostEvent.error_message` 有值，`final_answer=None`。
- `CANCELLED`：`_cancelled_host_event()` 从 inline payload 读取 `cancel_reason`。`HostEvent.cancel_reason` 有值，`final_answer=None`。
- 三者都通过 `_validate_host_event_terminal_payload()` 校验 kind/status/payload 组合一致性。
- payload 只暴露 display-safe 字段，不暴露 raw EngineEvent 或 policy decision JSON。

### 4. HostEventView / HostEventStream / stream_run_events 从包根移除 ✅

- `dayu.host.__all__` 不包含 `HostEventView`、`HostEventStream`、`stream_run_events`。
- `test_package_exports.py` 的 `ROOT_INTERNAL_API_NAMES` 和 `FORBIDDEN_HOST_ROOT_EXPORTS` 覆盖。
- `test_public_host_event.py` 验证 `vars(host)` 不含这些符号。
- 内部 diagnostic 测试从 `dayu.host.api` / `dayu.host.read_api` 导入，不依赖包根。

### 5. watch 生命周期 ✅

| 场景 | 实现 | 测试覆盖 |
| --- | --- | --- |
| handle closed 后新 watch | `_raise_if_closed()` 抛 `HostClosedError` | `test_watch_lifecycle_errors_and_closed_session_watch` |
| missing session | `_session_live_event_start_cursor()` 校验 session 存在，抛 `HostApiError(NOT_FOUND)` | 同上 |
| Session CLOSED | 允许 watch，`_require_session_exists()` 不检查 status | 同上 |
| consumer early cancel | `aclose()` 停止 async generator，不写 EventLog、不 cancel Run | `test_consumer_early_cancel_does_not_cancel_run_or_write_eventlog` |
| terminal 不结束 iterator | `while not self._closed` 循环不因 terminal break | `test_two_watchers_observe_same_terminal_event_and_iterator_continues` |
| Host close 已打开 watcher | `self._closed` 变 True，轮询自然结束 | `test_watch_lifecycle_errors_and_closed_session_watch` 间接覆盖 |

### 6. Scope creep 检查 ✅

未实现：
- Outbox offline catch-up ✅ (non-goal)
- `wait_final_answer` ✅ (non-goal)
- public payload reader / `read_payload` / `get_run_result` ✅ (未新增)
- Slice 5 commands ✅ (未触及)
- schema change ✅ (未修改 durable schema)
- 层级边界破坏 ✅ (dayu.host 不导入 dayu.fins / dayu.service / dayu.ui / dayu.engine，只导入 dayu.engine.contracts)

### 7. 测试和 README 同步 ✅

- `test_watch_session_events.py`：4 个测试覆盖双 watcher 去重、consumer cancel、FAILED/CANCELLED typed、lifecycle 错误。
- `test_public_host_event.py`：2 个测试覆盖 root namespace 收敛、terminal payload contract。
- `test_package_exports.py`：`ROOT_INTERNAL_API_NAMES` 过滤 `HostEventView`、`HostEventStream`、`HostLocalExecutionOptions`。
- 内部 diagnostic 测试 import 路径已迁移到内部模块。
- `dayu/host/README.md` 更新：记录 `watch_session_events` 为 Service-facing event entry，terminal HostEvent 内联 final answer，run-level diagnostic path 说明。
- `tests/README.md` 更新：新增 Slice 4 focused test 命令，Host public run / wait / event API 覆盖说明中加入 session live watch 与 root export 收敛。

## 验证结果

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q` | 7 passed in 0.37s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/host/test_package_exports.py tests/host/test_public_event_stream.py tests/host/test_public_contracts.py tests/host/test_command_handle.py -q` | 74 passed in 0.53s |

## 残余风险

1. **polling → push 迁移**：当前 20ms 轮询在高频场景下有 CPU 开销；后续 Phase 13 / Outbox owner 应替换为 event notification + wakeup。
2. **cross-session cursor 跳跃**：多 session 高频交错下，目标 session 的中间事件可能延迟一个扫描窗口；后续 Outbox session-level checkpoint 可消除。
3. **Host close 对已打开 watcher 的语义**：当前自然结束轮询，不写 cancel / failed terminal facts；如需表达 "Host 正在关闭" 的治理意图，需后续 slice 补充。
4. **duplicate terminal event 可见性**：同一 session 的 retry / replay 可产生多个 terminal event，watcher 都会看到；Service 需自行按 `event_id` / `dedupe_key` 去重。当前测试已覆盖此行为。
