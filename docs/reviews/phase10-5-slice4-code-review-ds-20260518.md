# P10.5 Slice 4 Code Review — AgentDS

## Gate

P10.5 Slice 4 code review。只审查，不改代码，不 commit/push/PR。

## 结论：PASS（0 blocking）

**blocking count: 0**。所有 7 个审查点均通过或仅存在非阻塞观察。

---

## 审查输入

- 设计真源：`docs/host/design.md`（§11 尤其 §11 中 `watch_session_events`、`HostEvent`、`HostEventView`、`stream_run_events` 边界）
- 总控文档：`docs/host/implementation-control.md`
- accepted plan：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`，Slice 4 section
- implementation artifact：`docs/reviews/phase10-5-slice4-implementation-codex-20260518.md`
- 当前 uncommitted diff

---

## 审查结果（按审查点）

### 1. `watch_session_events(session_id)` 是否满足 `AsyncIterator[HostEvent]` contract

**通过**。

- `Host` Protocol（`dayu/host/api.py:2799`）声明 `watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]`，返回类型为普通 `AsyncIterator[HostEvent]`，非 context manager 或 subscription handle。
- `_PublicHostHandle`（`dayu/host/open_host.py:303`）实现：fail-fast 校验 `_raise_if_closed()` + `_session_live_event_start_cursor()` 在同步调用时完成 handle 生命周期与 Session 存在性校验；异步迭代器 `_watch_session_events_after` 随后惰性产出事件。
- plan 写 `events = host.watch_session_events(...)` 的普通 async iterator 形态已满足。

### 2. Polling EventLog projection vs "live fanout from committed EventLog / ingest path"

**裁决：非 blocking，P10.5 可接受的 live watch 实现。**

关键证据链：

1. Plan Slice 4 section 原文："Build live fanout from committed EventLog / ingest path." — 使用 "/"（斜杠），表达 "committed EventLog" 或 "ingest path" 任一均可。
2. 设计真源 `design.md:1171`："`HostEvent` ... 它由 committed EventLog / Host ingest result 派生" — 设计真源以 committed EventLog 为源，不是 ingest callback push。
3. 设计真源 `design.md:911`："Phase 13 的 Audit / Tool Trace / Outbox 与 `watch_session_events` 一样消费 committed EventLog / typed projection input view" — 明确 `watch_session_events` 消费 committed EventLog。
4. 当前实现：`_watch_session_events_after`（`open_host.py:319`）通过 `_read_session_host_events_after`（`read_api.py:107`）读取 `read_events_after(...)` 的 committed EventLog rows，轮询间隔 0.02s。这是 "live watch from committed EventLog projection"。
5. 若要实现 push-from-ingest，需要 EventLog commit hook → notify → watcher queue 的完整 pub/sub 机制。这是非平凡的架构变更，且不改变对外 contract（仍是 `AsyncIterator[HostEvent]`）。P10.5 scope 不要求此优化。
6. Implementation artifact 已明确声明此实现路径："watch_session_events 当前是 live watch + polling EventLog projection"。

**结论**：当前实现使用了 plan 允许的 "committed EventLog" 路径。push-from-ingest 可作为未来内部优化，不影响对外 contract。

### 3. Terminal SUCCEEDED 的 final_answer 暴露与 FAILED/CANCELLED 的 typed display-safe 字段

**通过**。

**SUCCEEDED**：
- `_succeeded_host_event`（`read_api.py:439`）从 terminal summary payload descriptor 内联构造 `HostFinalAnswerView(content, filtered, degraded, finish_reason, terminal_status=SUCCEEDED)`。
- `HostFinalAnswerView`（`api.py:2442`）的 `__post_init__` 强制 `terminal_status == HostTerminalStatus.SUCCEEDED`，阻止非成功状态使用 final answer 视图。
- `_validate_host_event_terminal_payload`（`api.py:2541`）在 `HostEvent` 构造期强制 `kind=SUCCEEDED` 必须内联 `final_answer`，防止空 final answer。

**FAILED**：
- `_failed_host_event`（`read_api.py:504`）设置 `kind=FAILED`、`terminal_status=FAILED`、`error_message=...`、`final_answer=None`。
- `error_message` 来自 EventLog inline payload 的 `message` 字段（可选），展示安全。

**CANCELLED**：
- `_cancelled_host_event`（`read_api.py:531`）设置 `kind=CANCELLED`、`terminal_status=CANCELLED`、`cancel_reason=...`、`final_answer=None`。
- `cancel_reason` 来自 EventLog inline payload 的 `reason` 字段（可选），展示安全。

`_validate_host_event_terminal_payload` 覆盖了所有非法组合：PROGRESS 不能带 terminal payload；FAILED/CANCELLED 不能带 final_answer。

### 4. HostEventView / HostEventStream / stream_run_events 从包根移除，内部 diagnostic 仍可用

**通过**。

包根移除验证：
- `dayu/host/__init__.py` 不再 import `HostEventView`、`HostEventStream`、`stream_run_events`。
- `dayu/host/__init__.py.__all__` 不包含这三个名字。
- `tests/host/test_public_host_event.py::test_internal_event_view_and_run_stream_are_not_host_root_exports` 断言 `vars(host)` 不含这些名字。
- `tests/host/test_package_exports.py::test_removed_low_level_symbols_are_not_service_facing_all_exports` 断言 `host.__all__` 不含这些名字。

内部 diagnostic 路径仍可用：
- `dayu.host.api.HostEventView`、`dayu.host.api.HostEventStream` 保留在 `api.__all__`（`api.py:2858-2859`），供内部 diagnostic 代码显式导入。
- `dayu.host.read_api.stream_run_events` 保留在 `read_api.__all__`（`read_api.py:722`）。
- 迁移测试导入路径：
  - `test_public_event_stream.py`：改为 `from dayu.host.api import HostEventView`、`from dayu.host.read_api import stream_run_events`
  - `test_public_contracts.py`：改为 `from dayu.host.api import HostEventStream, HostEventView`
  - `test_command_handle.py`：改为 `from dayu.host.read_api import stream_run_events`
- `test_package_exports.py` 的 `EXPECTED_API_EXPORTS` 仍包含 `HostEventStream`/`HostEventView`（`api.__all__` 内部类型），但 `ROOT_INTERNAL_API_NAMES` 排除它们出 `host.__all__`。`FORBIDDEN_HOST_ROOT_EXPORTS` 强制它们不在 `vars(host)` 中。

### 5. Watch 生命周期：handle closed、missing session、Session CLOSED、consumer early cancel、terminal 不结束 iterator

**通过**。逐一核验：

| 场景 | 行为 | 实现位置 | 结果 |
|------|------|----------|------|
| handle closed 后新 watch | `HostClosedError` | `open_host.py:312` `_raise_if_closed()` | 测试覆盖：`test_watch_lifecycle_errors_and_closed_session_watch` |
| missing session | `HostApiError(NOT_FOUND)` | `read_api.py:235` `_require_session_exists` | 同上测试覆盖 |
| Session CLOSED | 允许 watch，不抛错 | 只校验 Session 存在，不校验 status | 同上测试覆盖（close_session 后仍可 watch） |
| consumer early cancel | 关闭本次订阅，不取消 Run、不写 EventLog | `open_host.py:332-356` poll loop 被 cancel 中断 | `test_consumer_early_cancel_does_not_cancel_run_or_write_eventlog` |
| terminal 不结束 iterator | iterator 继续产出后续 terminal | `open_host.py:332-343` while loop 持续轮询 | `test_two_watchers_observe_same_terminal_event_and_iterator_continues` |
| Host close 对已打开 watcher | poll loop 检测 `self._closed` 并自然退出 | `open_host.py:332` `while not self._closed` | close 不写 cancel/failed facts |

### 6. 是否意外实现 Outbox、wait_final_answer、public payload reader、Slice 5 commands、schema change 或破坏层级边界

**通过**。未发现越界实现。

- **Outbox**：未实现。`watch_session_events` 不做离线补读。`OutboxSummary` 类型存在于 `api.py` 但仅为类型预备，无不涉及实现。
- **wait_final_answer**：未实现。Host Protocol 不含此方法。
- **public payload reader / read_payload / get_run_result**：未新增。`_host_event_from_row` 使用 `read_payload_descriptor` 和 `TABLE_SQLITE_PAYLOADS` 是内部 projection，不暴露给 Service。
- **Slice 5 commands**：retry/replay/resolve_wait/steer/cancel 的 public facade 实现不在此 slice 范围内。测试使用 `cancel_run` 仅作为 CANCELLED terminal event 的 source，不测试 cancel 路径本身。
- **schema change**：无 durable schema 变更。无新表、新列、新索引。
- **层级边界**：
  - `dayu.host.read_api` 依赖 `dayu.host.durable.event_log`、`dayu.host.durable.payload`、`dayu.host.durable.state` — 均在 Host 内部，合法。
  - `dayu.host.open_host` 依赖 `dayu.host.command`、`dayu.host.dispatch`、`dayu.host.durable` — 标准 composition root 依赖，合法。
  - 未发现 Engine → Host、Service → Host internals 的反向依赖。

### 7. 测试和 README 覆盖/同步

**通过**。

测试覆盖：
- `tests/host/test_watch_session_events.py`：4 个测试，覆盖 double watcher dedup、terminal 不结束 iterator、consumer cancel 不写 EventLog、FAILED/CANCELLED typed status、handle close / missing Session / Session CLOSED。
- `tests/host/test_public_host_event.py`：3 个测试，覆盖包根不导出诊断符号、SUCCEEDED 强制 final_answer、FAILED/CANCELLED 拒绝 final_answer。
- 迁移测试：`test_public_event_stream.py`、`test_public_contracts.py`、`test_command_handle.py` 改为内部模块路径导入；`test_public_event_stream.py` 修复固定 26 个无关 Run 的旧假设为自适应 `HOST_EVENT_STREAM_DEFAULT_LIMIT`。

README 同步：
- `dayu/host/README.md`：已更新 watch_session_events 入口、terminal event 形态、内部 diagnostic 路径降级说明。与当前代码一致。
- `tests/README.md`：新增 Slice 4 focused test 命令（line 51）。

---

## 验证结果

```text
# Slice 4 focused tests
$ source .venv/bin/activate && pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q
7 passed in 0.37s

# pyright
$ source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

# 扩展受影响的测试
$ source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_public_event_stream.py tests/host/test_public_contracts.py tests/host/test_command_handle.py -q
74 passed in 0.54s
```

---

## Findings 清单（按严重度）

### Blocking（0）

无。

### Non-blocking observations

**F1 (Medium-Low) — Polling vs push-based fanout**

如审查点 2 详述：当前实现使用 polling EventLog projection，非 push-based ingest fanout。Plan 文本的 "committed EventLog / ingest path" 以 "/" 允许 committed EventLog 路径。设计真源 `design.md:1171` 同样使用 "committed EventLog" 作为派生源。P10.5 不要求 push-based fanout，且该内部实现差异不改变 `AsyncIterator[HostEvent]` 对外 contract。**无需修改**。

**F2 (Low) — HostLocalExecutionOptions 仍在 `vars(host)` 中**

`dayu/host/__init__.py:47` 仍在 import `HostLocalExecutionOptions`，使其可被 `from dayu.host import HostLocalExecutionOptions` 获取（虽然不在 `host.__all__` 中）。Plan 要求 "HostLocalExecutionOptions 降级为内部 implementation contract；Service 不理解这些名字"。此为 Slice 1 遗留状态，非 Slice 4 引入。Slice 4 的 `test_public_host_event.py` 不检查该名字（仅检查 HostEventView/HostEventStream/stream_run_events）。**不阻塞**，可由后续 slice 或独立清理 PR 处理。

**F3 (Info) — 内部 batch size 与 public limit 不一致**

`_SESSION_WATCH_BATCH_LIMIT = 64`（`read_api.py:49`）与 `HOST_EVENT_STREAM_DEFAULT_LIMIT = 100`（`api.py:48`）不同。这是有意设计：session live watch poll 使用较轻的批次大小以保持低延迟；run-level `stream_run_events` 使用较大的默认扫描窗口。两者语义不冲突。**无需修改**。

**F4 (Info) — 下一个 follow-up terminal 的 watch 延迟**

在 `test_two_watchers_observe_same_terminal_event_and_iterator_continues` 测试中，第二个 follow-up 的 terminal 在第 313 行被 `_next_terminal` 以 2s timeout 等待。这是在测试中显式等待，不代表生产路径。生产路径中 poll interval 为 0.02s，延迟可忽略。**无需修改**。

---

## 残余风险

1. **离线 terminal 补读缺口**（已知风险）: `watch_session_events` 从 attach 时最新 EventLog cursor 开始，attach 前提交的 terminal 不会被补读。需 Phase 13 Outbox 路径去重补投。Implementation artifact 已记录。

2. **Host close 对已打开 watcher 无 cancel 事实**（已知风险）: `_watch_session_events_after` 检测到 `self._closed` 后自然退出，不写 cancel/failed facts。符合 plan 设计。Implementation artifact 已记录。

3. **多 watcher 并发读 EventLog**（新风险，低严重度）: 每个 watcher 独立在 poll loop 中读取 EventLog。在 WAL 模式下读不阻塞写，但大量 watcher（如 >50）时 SQLite 读压力可能成为瓶颈。当前 P10.5 预期 watcher 数量极少（每 Session 1-2 个），不构成实际风险。若未来需要大规模 fanout，可引入 push-based notify 或 read replica。

4. **测试未覆盖 RUN_SUCCEEDED EventLog row 缺少 terminal summary payload descriptor 的场景**（新风险，低严重度）: `_succeeded_host_event` 假设 terminal summary payload descriptor 存在且合法；若 EventLog 中有 malformed terminal row，会抛 `HostDurableError` 导致 watch iterator 崩溃。这在生产中是 "should never happen" 场景（terminal summary 由 EngineEventIngestor 在 terminal closeout 时同期写入）。不阻塞 P10.5。

---

## 附：Contract 一致性矩阵

| Plan requirement | Implementation location | Status |
|---|---|---|
| `watch_session_events(session_id) -> AsyncIterator[HostEvent]` | `api.py:2799`, `open_host.py:303` | ✓ |
| Handle closed → HostClosedError | `open_host.py:312` | ✓ |
| Missing session → NOT_FOUND | `read_api.py:235` | ✓ |
| Terminal SUCCEEDED inline HostFinalAnswerView | `read_api.py:439-501` | ✓ |
| FAILED typed terminal_status + error_message | `read_api.py:504-528` | ✓ |
| CANCELLED typed terminal_status + cancel_reason | `read_api.py:531-555` | ✓ |
| Terminal 不结束 iterator | `open_host.py:332` while loop | ✓ |
| Consumer cancel 不取消 Run / 不写 EventLog | `open_host.py` poll loop + test evidence | ✓ |
| HostEventView/HostEventStream/stream_run_events 非包根导出 | `__init__.py`, tests | ✓ |
| 内部 diagnostic 路径仍可用 | `api.py`, `read_api.py`, migrated test imports | ✓ |
| 无 Outbox / wait_final_answer / public payload reader | Confirmed absent | ✓ |
| 无 Slice 5 commands | Confirmed absent | ✓ |
| 无 schema change | Confirmed absent | ✓ |
| 无层级边界破坏 | Import graph checked | ✓ |
| README sync | `dayu/host/README.md`, `tests/README.md` | ✓ |
