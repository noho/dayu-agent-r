# P6 Durable EventLog Code Review

**审查日期**: 2026-05-08
**审查范围**: 当前 branch `migration/host-p6-durable-eventlog` 的 uncommitted diff（tracked 修改 + untracked 新文件）
**结论**: **不通过**

---

## 结论说明

P6 的存储层基础设施（`DurableRunEventStore`、`HostStorageTransaction`、`ProjectionStore`、`RunEventSerializer`、`RunStateStore`）设计合理、类型完备、测试覆盖关键路径。但 **真实 run path（`LocalRunHarness.start_run` -> `_run_to_store` -> terminal）并未进入 `ProjectionCoordinator` 路径**，而是继续使用 `_project_run_events()` 直接投影到 memory store。这导致：

1. ProjectionCoordinator / observer checkpoint / retry / lag 在主路径中完全缺席。
2. `build_durable_harness` 装配的 `memory_store` 与 `LocalRunHarness` 内部默认 `memory_store` 是两个不同实例，形成 split-brain。
3. terminal snapshot / `RunResult` 持久化未在同一事务中完成。
4. `AttemptStateStore` 未进入主路径。

这些问题使得 P6 的 durable 路径实际仍以 P5 的方式运行，设计文档 `docs/host/design.md` 第 9 节描述的目标路径未达成。

---

## Findings

### F-01: LocalRunHarness 绕过 ProjectionCoordinator，直接投影 memory

**严重级别**: HIGH

**证据**:

`_run_harness.py:512-513`：terminal 后直接调用 `_project_run_events()`：

```python
finally:
    if terminal_seen:
        await self._project_run_events(request.run_id)
```

`_run_harness.py:937-955`：`_project_run_events` 直接 `list_events` + `memory_store.project_run_events()`：

```python
async def _project_run_events(self, run_id: str) -> None:
    events = await self.event_store.list_events(run_id=run_id, after=None)
    await self.memory_store.project_run_events(events)
```

`coordinator.drain()` 在整个代码库中仅被 `utils/smoke_host_p6_durable_eventlog.py:115` 调用。

**影响**:

- `ProjectionCoordinator` 的 checkpoint 推进、retry / lag 跟踪、observer dispatch 在真实 run path 中完全不生效。
- `MemoryProjectionObserver`（required projection）从未被主路径触发。
- timeline / audit observer 从未被主路径触发。
- P6 设计文档 `docs/host/design.md` 第 9.0 节的目标路径（`ProjectionCoordinator drains durable EventLog`）未达成。
- 故障恢复时 checkpoint 不可用，因为从未写入过。

**建议**:

在 `_run_to_store` 的 `finally` 块中，当 `terminal_seen` 时调用 `coordinator.drain()` 而非 `_project_run_events()`。或者将 `ProjectionCoordinator` 注入 `LocalRunHarness`，由 harness 在 terminal 后显式触发 drain。需要考虑 `coordinator` 参数的可选性以保持 `InMemoryRunEventStore` 路径的兼容。

---

### F-02: build_durable_harness 装配的 memory_store 与 LocalRunHarness 内部 memory_store 不一致

**严重级别**: HIGH

**证据**:

`_durable_harness.py:91-94`：创建 `actual_memory` 并传给 observer：

```python
actual_memory: ConversationMemoryStore = (
    memory_store if memory_store is not None else InMemoryConversationMemoryStore()
)
memory_observer = MemoryProjectionObserver(memory_store=actual_memory)
```

`_durable_harness.py:113-119`：`LocalRunHarness(...)` 未接收 `memory_store=actual_memory`：

```python
harness = LocalRunHarness(
    proxy=LocalProxy(worker=EngineWorker(ToolRuntimeToolExecutor(runtime))),
    event_store=event_store,
    tool_runtime=runtime,
)
```

`_run_harness.py:226-228`：`LocalRunHarness.memory_store` 默认为新的 `InMemoryConversationMemoryStore`：

```python
memory_store: ConversationMemoryStore = field(
    default_factory=InMemoryConversationMemoryStore
)
```

**影响**:

- `LocalRunHarness._project_run_events()` 写入 harness 自己的默认 memory store。
- `MemoryProjectionObserver` 读写 `actual_memory`。
- 两个 memory store 是不同实例，形成 split-brain：harness 写入的数据 observer 看不到，observer 写入的数据 harness 看不到。
- `bundle.memory_store` 返回 `actual_memory`，但 harness 内部用的是另一个。

**建议**:

`build_durable_harness` 创建 `LocalRunHarness` 时必须传入 `memory_store=actual_memory`。

---

### F-03: terminal snapshot / RunResult 未在同一事务写入

**严重级别**: HIGH

**证据**:

`_durable_event_store.py:329-344`：`_upsert_run_state` 在 terminal 时更新 `host_runs.state`、`terminal_sequence`、`terminal_event_position`，但不写 `result_payload`：

```python
if is_terminal:
    terminal_state = _terminal_state_for_event_type(draft.type)
    tx.execute(
        "UPDATE host_runs SET state = ?, updated_at = ?,
            terminal_sequence = ?, terminal_event_position = ?
        WHERE run_id = ?",
        (terminal_state.value, now_iso, sequence, event_position, draft.run_id),
    )
```

`_run_state_store.py:85-105`：`write_terminal_result()` 写入 `result_payload`，但在整个代码库中无调用者。

`_run_harness.py:447-461`：terminal 后只做内存推导 `terminal_result_from_event(stored_event)`，不调用 `write_terminal_result`。

**影响**:

- `host_runs.result_payload` 始终为 NULL。
- `RunStateStore.get_terminal_result()` 始终返回 None。
- 设计要求 terminal event、Run state、RunResult snapshot 同事务写入，当前只有 event + state，没有 result snapshot。
- startup recovery 和 projection rebuild 无法从 durable store 恢复 `RunResult`。

**建议**:

`DurableRunEventStore._append_in_transaction` 中，当 `is_terminal` 时，应同时调用 `RunStateStore.write_terminal_result()` 或等价逻辑，将 `RunResult` 持久化到 `result_payload`。需要将 `terminal_result_from_event` 的推导结果传入事务。

---

### F-04: smoke 未覆盖真实 run path

**严重级别**: MEDIUM

**证据**:

`utils/smoke_host_p6_durable_eventlog.py:76-115`：手工构造 `RunEventDraft`，直接调用 `bundle.event_store.append()` + `bundle.coordinator.drain()`。

未覆盖路径：`LocalRunHarness.start_run()` -> `_run_to_store()` -> `proxy.stream_engine_events()` -> `translate_engine_event()` -> `event_store.append()` -> terminal -> `_project_run_events()`。

**影响**:

- smoke 通过只证明存储层和 coordinator 能独立工作，不证明真实 run path 按 design 路径走。
- 当前真实 run path 仍绕过 ProjectionCoordinator（见 F-01），smoke 无法暴露此问题。

**建议**:

补充一个 smoke 或集成测试，覆盖 `build_durable_harness` -> `harness.start_run()` -> Engine event stream -> terminal -> memory projection 的完整路径。可以在 smoke 中用 mock Engine worker 返回预定义事件流。

---

### F-05: AttemptStateStore 未进入主路径

**严重级别**: MEDIUM

**证据**:

`_run_state_store.py:129-267`：`AttemptStateStore` 定义了 `create`、`update_state`、`get`、`list_for_run` 方法。

`grep -rn 'AttemptStateStore' dayu/host/_run_harness.py dayu/host/_durable_event_store.py dayu/host/_durable_harness.py`：无结果。

`AttemptStateStore` 仅在 `test_phase6_run_state_store.py` 中被测试。

**影响**:

- `host_attempts` 表虽然在 schema 中定义，但主路径从不写入。
- 设计要求 Run/Attempt 最小持久状态，当前只有 Run 状态，Attempt 状态完全缺失。
- context compact retry 的 attempt 序列无法从 durable store 恢复。

**建议**:

判断是否属于 P6 必做项。`phase6-plan.md` 4.3 节写的是 "Run / Attempt 最小持久状态"，应确认 Attempt 是否必须在 P6 主路径中维护。如果是，需要在 `_run_to_store` 的 attempt 开始和结束时调用 `AttemptStateStore.create` / `update_state`。

---

### F-06: `_run_event_serializer.py` 处理 P7 tool cursor 事件类型

**严重级别**: LOW

**证据**:

`_run_event_serializer.py:393-457` 和 `655-726`：encode/decode 处理 `ToolResultTruncatedData`、`ToolCursorIssuedData`、`ToolFetchMoreRequestedData`、`ToolFetchMoreCompletedData`、`ToolFetchMoreFailedData`、`ToolCursorExpiredData`、`ToolCursorDeniedData`。

**影响**:

这些事件类型已在 `RunEventType` 枚举中定义，serializer 只是为已有类型提供序列化支持。这不构成"偷做 P7 tool trace schema"——P7 的核心是 tool trace projection / sink，不是事件序列化。但代码审查应确认这些事件类型确实在 P1-P5 中已定义，而非 P6 新增。

**建议**:

确认这些 `RunEventType` 枚举值的引入时间。如果确实在 P1-P5 中已存在，则 serializer 覆盖它们是正确的。无需修改。

---

### F-07: `extended_state_from_run_state` 缺少 wildcard match

**严重级别**: LOW

**证据**:

`_internal_contracts.py:112-133`：`match state` 没有 `_` catch-all。docstring 声明 `:raises ValueError: 出现未知 RunState 时抛出`，但实际隐式返回 `None`。

```python
def extended_state_from_run_state(state: RunState) -> ExtendedRunState:
    match state:
        case RunState.CREATED: ...
        case RunState.RUNNING: ...
        case RunState.SUCCEEDED: ...
        case RunState.FAILED: ...
        case RunState.CANCELLED: ...
        case RunState.SUSPENDED: ...
    # 无 wildcard -> 隐式 return None
```

**影响**:

若 `RunState` 新增变体，函数静默返回 `None`，违反 `:raises ValueError` 契约。类型签名 `-> ExtendedRunState` 也不允许 `None`，但 Python 运行时不阻止。

**建议**:

添加 `_` case 抛出 `ValueError`。

---

### F-08: `_must_str` / `_must_bool` 重复定义

**严重级别**: LOW

**证据**:

`_run_event_serializer.py:1122-1140` 和 `_run_state_store.py:435-460` 包含相同的 `_must_str` 和 `_must_bool` 辅助函数。

**影响**:

违反编码硬约束 "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。

**建议**:

抽取到 `dayu.host._internal_utils` 或类似公共模块。

---

### F-09: `_encode_fields` / `_decode_fields` 为 god function

**严重级别**: LOW

**证据**:

`_run_event_serializer.py:223-458`（~235 行 if/elif 链）和 `461-726`（~265 行 if/elif 链）。

**影响**:

可维护性较低，但每个分支只有几行，逻辑清晰。当前规模可控。

**建议**:

后续可考虑 dispatch table 模式，但不阻塞 P6。

---

### F-10: 生产代码使用 bare assert

**严重级别**: LOW

**证据**:

`_event_observer.py:201` 和 `_event_observer.py:243`：

```python
assert refreshed is not None
```

**影响**:

`assert` 在 `python -O` 模式下被移除。如果 `projection_store.get` 因并发或数据损坏返回 `None`，将导致后续代码以 `None` 继续执行而非抛出明确异常。

**建议**:

替换为 `if refreshed is None: raise RuntimeError(...)` 或等价的显式错误处理。

---

### F-11: `_durable_event_store.py` 整合了 4 张表的 schema DDL

**严重级别**: LOW

**证据**:

`_durable_event_store.py:66-133`：`_SCHEMA_STATEMENTS` 包含 `host_run_events`、`host_runs`、`host_attempts`、`host_projection_checkpoints` 四张表的 DDL。

**影响**:

`host_runs` 和 `host_attempts` 的 owner 是 `RunStateStore` / `AttemptStateStore`；`host_projection_checkpoints` 的 owner 是 `ProjectionStore`。DDL 集中在 event store 模块中，增加了表定义与表 owner 之间的隐式耦合。

**建议**:

将 DDL 分散到各自的 store 模块中，由 `ensure_host_schema` 统一收集。不阻塞 P6。

---

### F-12: `dayu.engine` 类型导入到 `dayu.host` 层

**严重级别**: LOW

**证据**:

`_run_state_store.py:18`：`from dayu.engine import FinishReason, RunResumeHint`
`_run_event_serializer.py:29-62`：大量 `from dayu.engine.contracts.*` 导入

**影响**:

Host 层对 Engine 层的类型形成直接依赖。如果 Engine 类型签名变化，Host 的序列化和状态存储会直接受影响。这不违反架构硬约束（约束禁止的是 `dayu.runtime` import `dayu.engine`，不是 `dayu.host` import `dayu.engine`），但增加了层间耦合。

**建议**:

P6 范围内可接受——Host 需要知道 Engine 事件类型才能序列化。但应在后续 phase 中考虑是否将 `RunResult` 等共享类型下沉到 `dayu.contracts`。

---

## Residual Risks / Test Gaps

### R-01: projection checkpoint 幂等重放测试缺失

当前测试验证了 checkpoint 不允许倒退（`test_projection_store_advance_regression_rejected`），但没有显式测试"drain 相同事件两次产生相同 checkpoint"的幂等语义。

### R-02: RunStateStore 非成功终态转换测试缺失

`test_phase6_run_state_store.py` 只测试了 `SUCCEEDED`（via `FINAL_ANSWER`）。`RUN_FAILED`、`CANCELLED`、`SUSPENDED` 的 state 转换未在 `RunStateStore` 层面测试。

### R-03: `ProjectionStore.ensure` upsert 幂等测试缺失

没有测试对同一 observer 调用两次 `ensure` 的行为（应为幂等 upsert）。

### R-04: 多 observer 不同 lag 测试缺失

当前测试只验证单个 observer 的 lag 计算，没有测试多个 observer 持有不同 `last_success_position` 时的 lag 差异。

### R-05: memory rebuild 多 run 交错测试缺失

`test_phase6_memory_rebuild.py` 每个测试只涉及单个 run。同一 session 下两个 run 交错的场景未覆盖。

### R-06: serializer `RunSuspendedData` round-trip 测试缺失

`test_phase6_run_event_serializer.py` 覆盖了 `ContentDeltaData`、`FinalAnswerData`、`RunFailedData`、`RunCancelledData`、`UserInputAcceptedData`，但没有 `RunSuspendedData` 的 round-trip 测试。

### R-07: `_run_to_store` 中 `result_payload` 持久化的故障注入缺失

没有测试验证 terminal event append 成功但 `result_payload` 写入失败时的回滚行为（当前因为 `result_payload` 根本不在事务中，所以这个场景不存在——但这也正是 F-03 的问题所在）。

---

## 审查通过项

以下方面审查通过，无阻断问题：

1. **P6 范围边界**: 未发现 P8（attempt lease/fencing）、P9（lifecycle/admission）、P10（ToolRegistry）、P10.5（web tools）、P11（validation）的偷做实现。P7 tool cursor 事件的序列化是为已有枚举类型提供支持，不构成 P7 tool trace schema 实现。
2. **类型完备性**: 所有新文件无 `Any`、`object`、无类型参数或无类型返回值。
3. **中文 docstring**: 所有公开和私有函数/类均有中文 docstring，包含 `:param` / `:returns` / `:raises`。
4. **事务边界设计**: `HostStorageTransaction` + `BEGIN IMMEDIATE` + WAL + post-commit hook 模式正确。`ProjectionCoordinator.run_once` 的 sink-then-advance 在同一事务中完成。
5. **serializer 封闭注册表**: `_DATA_CLASS_BY_TYPE` 提供封闭 type↔data 映射，`schema_version` 校验、unknown type fail-fast、type_name 匹配校验均正确。
6. **terminal guard**: `DurableRunEventStore.append` 在 terminal 后正确拒绝后续 append。
7. **per-run cursor vs global event position**: 设计正确区分了 public `RunEventCursor`（per-run）和 internal `GlobalEventPosition`（全局单调），后者不泄漏给普通调用方。
8. **checkpoint 不允许倒退**: `ProjectionStore.advance_success` 正确实现了 regression check。
9. **SQLite WAL + BEGIN IMMEDIATE**: 足以覆盖 P6 单进程写入场景。文档正确声明了"未提供跨进程 lease / fencing 与多进程恢复"。
10. **`StartRunRequest` 注释修正**: P7 -> P9 已修正（`contracts.py:511`）。
11. **README 同步**: `dayu/host/README.md` 和 `tests/README.md` 已更新，内容与当前代码一致。
12. **smoke 脚本安全**: 无 scope token 泄漏，无大 payload 打印（硬编码短字符串），`finally` 中正确释放资源。
