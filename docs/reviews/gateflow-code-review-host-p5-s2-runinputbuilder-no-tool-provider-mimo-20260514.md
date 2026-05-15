# Code Review: Host Phase 5 P5-S2 RunInputBuilder And No-tool Provider Boundary

- gate: Host Phase 5 P5-S2 code review
- reviewer role: independent code reviewer
- review date: 2026-05-15
- diff base: current uncommitted changes vs HEAD
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`, slice P5-S2 / §3.4
- design doc: `docs/host/design.md` §23

## Review Scope

Production files:

- `dayu/host/run_input.py` (new)
- `dayu/host/api.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/__init__.py`

Test files:

- `tests/host/test_run_input_builder.py` (new)
- `tests/host/test_package_exports.py`

## Validation Reconfirmed

```
pytest tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q => 11 passed
python -m pyright dayu/host tests/host => 0 errors, 0 warnings, 0 informations
git diff --check => passed
```

## Findings

### F1 — 当前 prompt 只来自 durable USER_INPUT_ACCEPTED

**Status**: CORRECT

**Evidence**:

`DurableCurrentRunFactProvider._load_current_run_facts_tx` (run_input.py:322-385)：

```python
user_input_event = _require_event(
    self._event_log_store.read_event_by_id(transaction, run.input_event_id),
    expected_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
)
# ...
user_prompt=_required_payload_text(payload, field_name=_PAYLOAD_FIELD_DISPLAY_TEXT),
```

prompt 来源链：`RunRow.input_event_id` → `EventLog.read_event_by_id` → 校验 `event_class == CANONICAL_FACT` + `event_type == USER_INPUT_ACCEPTED` → `payload_json.display_text`。

测试 `test_current_user_message_comes_from_durable_user_input` (test_run_input_builder.py:100-114) 直接验证：写入 durable 后修改原始 dict 的 `display_text`，build 输出仍为 durable 值 `"durable prompt"`，不受 transient mutation 影响。

**Verdict**: 与 design §23 "`USER_INPUT_ACCEPTED` 是当前用户 prompt 进入 RunInputBuilder 的唯一事实入口"完全一致。

---

### F2 — Continuity 只读 canonical facts 且稳定排序

**Status**: CORRECT

**Evidence**:

`read_run_input_continuity_events` (event_log.py:416-483)：

```sql
WHERE session_id = ?
  AND event_class = ?               -- CANONICAL_FACT
  AND event_sequence < ?            -- 当前 Attempt 边界
  AND event_type IN (?, ?, ?, ?, ?) -- USER_INPUT_ACCEPTED, RUN_SUCCEEDED,
                                     -- RUN_FAILED, RUN_CANCELLED, RUN_LOST
ORDER BY event_sequence ASC
```

过滤维度：

- `event_class = CANONICAL_FACT`：排除 preview、diagnostic、projection_signal。
- `event_sequence < before_event_sequence`：只读当前 Attempt 之前的事件。
- `event_type IN (...)`：白名单只含 continuity 相关的五种事件类型。
- `ORDER BY event_sequence ASC`：按全局顺序稳定排序。

`DurableSessionContinuityProvider._load_session_continuity_tx` (run_input.py:417-443) 进一步过滤：

```python
for event in events:
    if event.run_id == snapshot.run_id:
        continue  # 排除当前 Run 自身的事件
    message = _continuity_message_from_event(event)
```

`_continuity_message_from_event` (run_input.py:886-912) 只投影两种事件：
- `USER_INPUT_ACCEPTED` → `UserMessage(content=display_text)`
- `RUN_SUCCEEDED` → `AssistantMessage(content=final_answer/content/summary_text)`

`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` 返回 `None`，不进入 messages。

测试 `test_continuity_uses_event_sequence_and_ignores_non_canonical` (test_run_input_builder.py:145-201) 验证：
- 插入 projection_signal 和 preview 事件后，build 输出不含这些事件的内容。
- continuity messages 按 `event_sequence` 排序：`"first question"`, `"first answer"`, `"second question"`。

**Verdict**: 与 design §23 "不应进入 messages: audit-only facts, usage-only facts, stream fanout 状态, raw preview delta" 和 plan §3.4 "continuity provider 按 event_sequence 排序，不消费 preview / usage / audit-only events"完全一致。

---

### F3 — Provider 均为 typed Protocol 且无 Any/object

**Status**: CORRECT

**Evidence**:

`run_input.py` 定义了八个 typed Protocol：

| Protocol | 返回类型 |
|---|---|
| `CurrentRunFactProvider` | `CurrentRunFacts` |
| `SessionContinuityProvider` | `SessionContinuityView` |
| `MemorySnapshotProvider` | `MemorySnapshotView` |
| `CompactArtifactProvider` | `CompactArtifactView` |
| `ToolSchemaSnapshotProvider` | `ToolSchemaSnapshot` |
| `ToolExecutorProvider` | `ToolExecutor` |
| `SceneParameterProvider` | `tuple[SystemMessage, ...]` |
| `PolicySnapshotProvider` | `PolicySnapshot` |

所有 dataclass 字段强类型，无 `Any` / `object`。`JsonValue` 来自 `dayu.contracts.json_value`，是项目的 typed JSON union。

`cast` 使用（run_input.py:820-825）：
```python
value = cast(JsonValue, json.loads(event.payload_json))
# ...
return cast(Mapping[str, JsonValue], value)
```
`json.loads` 返回 `Any`，`cast` 用于在 `isinstance(value, Mapping)` 检查后窄化类型，非弱类型逃逸。

弱类型守卫测试通过（11 passed 包含 `test_weak_typing_guard.py`）。

**Verdict**: 符合编码硬约束 "禁止使用 `object`、`Any`、无类型参数"。

---

### F4 — AttemptDispatchSnapshot 只承载 durable refs / policy ref / cancellation token

**Status**: CORRECT

**Evidence**:

`api.py:AttemptDispatchSnapshot` (api.py:253-306)：

```python
@dataclass(frozen=True, slots=True)
class AttemptDispatchSnapshot:
    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    execution_target: str
    policy_snapshot_ref: str
    cancellation_token: CancellationToken
```

字段分析：
- `session_id` / `run_id` / `attempt_id` / `execution_id` / `dispatch_record_id`：durable identity refs ✓
- `execution_target`：durable Run row 字段 ✓
- `policy_snapshot_ref`：policy snapshot 引用 ✓
- `cancellation_token`：Host 注入的取消观察 token ✓

不含 `runner_spec` / `runner_options` / `agent_policy` / `tool_schemas` / `tool_executor` — 这些由 providers 在 `build()` 时注入。

`__post_init__` 校验所有必填文本字段非空。`CancellationToken` 是 `dayu.contracts.cancellation` 的 Protocol，不是具体实现类。

**Verdict**: 与 plan §3.4 "AttemptDispatchSnapshot 只携带 durable identity refs、dispatch refs、policy snapshot refs 和 cancellation token"完全一致。

---

### F5 — No-tool request 满足 disable_tools / tool_schemas / allow_tool_calls

**Status**: CORRECT

**Evidence**:

`RunInputBuilder.build` (run_input.py:658-710)：

```python
return AgentRunRequest(
    # ...
    disable_tools=tool_snapshot.disable_tools,
    tool_schemas=tool_snapshot.tool_schemas,
    tool_executor=self._tool_executor_provider.load_tool_executor(...),
    # ...
)
```

`_validate_no_tool_snapshot` (run_input.py:936-952) 在 build 时强制校验：

```python
if not tool_snapshot.disable_tools:
    raise HostDurableError("RunInputBuilder requires disable_tools=True")
if tool_snapshot.tool_schemas:
    raise HostDurableError("RunInputBuilder no-tool schema snapshot must be empty")
if policy_snapshot.agent_policy.allow_tool_calls:
    raise HostDurableError("RunInputBuilder requires allow_tool_calls=False")
```

`NoopToolSchemaSnapshotProvider` 返回 `ToolSchemaSnapshot(tool_schemas=(), disable_tools=True)`。
`PolicySnapshot.__post_init__` 校验 `agent_policy.allow_tool_calls` 必须为 `False`。

测试 `test_no_tool_request_fields_are_disabled` (test_run_input_builder.py:221-237)：

```python
assert request.disable_tools is True
assert request.tool_schemas == ()
assert request.agent_policy.allow_tool_calls is False
assert isinstance(request.tool_executor, NoToolExecutor)
```

**Verdict**: 三重防线（provider 返回 → PolicySnapshot 构造校验 → build 时 snapshot 校验）确保 no-tool 约束不可绕过。

---

### F6 — NoToolExecutor 只是防线

**Status**: CORRECT

**Evidence**:

`NoToolExecutor` (run_input.py:501-526)：

```python
class NoToolExecutor:
    async def execute(self, request: BatchToolExecutionRequest) -> BatchToolExecutionOutcome:
        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolCancelledOutcome(
                        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
                        message=_NO_TOOL_CANCEL_MESSAGE,
                        hint=None,
                        meta=None,
                    ),
                )
                for call in request.calls
            )
        )
```

行为：对每个 tool call 返回 `ToolCancelledOutcome(reason=host_cancelled, message="tools are disabled for this attempt")`。

不注册业务工具，不创建 durable rows，不触发 fetch_more。纯防御性 executor。

**Verdict**: 与 plan §3.4 "`NoToolExecutor` 只作为 no-tool 防线；不得注册业务工具或 `fetch_more`"一致。

---

### F7 — 未越界实现 scheduler / LocalProxy / ToolRuntime / Engine ingest

**Status**: CORRECT

**Evidence**:

| 非目标项 | 遵守情况 |
|---|---|
| 不实现 scheduler | ✓ `run_input.py` 无 dispatch / lane / scheduler 逻辑 |
| 不实现 LocalProxy / WorkerProxy | ✓ 无 worker / proxy / event candidate 逻辑 |
| 不实现 ToolRuntime | ✓ `NoToolExecutor` 只是防线，无 real tool dispatch |
| 不实现 Engine ingest | ✓ 无 EngineEvent mapping / terminal closeout |
| 不实现 Memory projection | ✓ `NoopMemorySnapshotProvider` 返回空 |
| 不实现 Context Governance | ✓ 无 compaction / budget 逻辑 |
| 不修改 Engine contract | ✓ 未修改 `dayu/engine/` |

`run_input.py` 模块 docstring 明确声明边界："不读取 UI / Service 临时状态，不实现 scheduler、LocalProxy、ToolRuntime、Memory projection 或 Context Governance"。

**Verdict**: 与 plan 非目标完全一致。

---

### F8 — Messages 构造顺序

**Status**: CORRECT (Phase 5 subset)

**Evidence**:

`RunInputBuilder.build` (run_input.py:685-696)：

```python
messages = (
    *self._scene_parameter_provider.build_scene_messages(...),  # 1. system scene
    *memory.messages,                                           # 2. memory (empty)
    *compact.messages,                                          # 3. compact (empty)
    *continuity.messages,                                       # 4. continuity
    UserMessage(role=AgentMessageRole.USER, content=current_facts.user_prompt),  # 5. current input
)
```

与 plan §3.4 messages 稳定顺序对比：

| Plan 顺序 | 实现 | 匹配 |
|---|---|---|
| 1. system scene / execution target / policy | `build_scene_messages` | ✓ |
| 2. noop memory stable layer (Phase 5 为空) | `memory.messages` (empty) | ✓ |
| 3. 同 Session canonical continuity | `continuity.messages` | ✓ |
| 4. 当前 USER_INPUT_ACCEPTED | `UserMessage(...)` | ✓ |

与 design §23 完整顺序对比（Phase 5 子集）：

| Design 顺序 | Phase 5 实现 |
|---|---|
| 1. system / scene | ✓ `build_scene_messages` |
| 2. memory stable layer | ✓ empty |
| 3. canonical facts (event_sequence) | ✓ continuity |
| 4. replay / retry / steer | Phase 5 无此需求 |
| 5. tool schema / policy | Phase 5 noop |

**Verdict**: Phase 5 子集正确。`test_continuity_uses_event_sequence_and_ignores_non_canonical` 验证完整 messages 序列为 `(system, "first question", "first answer", "second question", "current question")`。

---

### F9 — DurableEventLog reader 窄化

**Status**: CORRECT

**Evidence**:

`read_run_input_continuity_events` (event_log.py:416-483) 是 `EventLogStore` 的新增方法，只返回 RunInputBuilder continuity 白名单事件。

SQL 过滤：`event_class = CANONICAL_FACT` + `event_type IN (USER_INPUT_ACCEPTED, RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, RUN_LOST)`。

与 `read_events_after` 等通用 reader 分离，不暴露全量 EventLog 给 RunInputBuilder。

**Verdict**: 与 design §23 "每类输入必须有稳定 provider contract" 和 plan "新增窄 reader"一致。

---

### F10 — 测试覆盖度评估

**Status**: CORRECT

**Evidence**:

| Plan 测试要求 | 测试函数 | 状态 |
|---|---|---|
| 当前用户消息只来自 durable USER_INPUT_ACCEPTED | `test_current_user_message_comes_from_durable_user_input` | ✓ |
| 同一 EventLog + policy snapshot 多次 build 输出稳定 | `test_build_is_deterministic_for_same_eventlog_and_policy` | ✓ |
| continuity 按 event_sequence 排序，不消费非 canonical | `test_continuity_uses_event_sequence_and_ignores_non_canonical` | ✓ |
| noop memory / compact / tool schema provider 不创建 durable rows | `test_noop_providers_do_not_create_durable_rows` | ✓ |
| no-tool request: disable_tools=True / tool_schemas=() / allow_tool_calls=False | `test_no_tool_request_fields_are_disabled` | ✓ |
| package/API export 更新 | `test_package_exports.py` | ✓ |

额外覆盖：弱类型守卫测试通过。

**Verdict**: plan P5-S2 所有测试要求均已覆盖。

---

### F11 — `dayu.host` 包导出

**Status**: CORRECT

**Evidence**:

`__init__.py` 新增 `AttemptDispatchSnapshot` 导出。`api.py` 的 `__all__` 同步更新。

`run_input.py` 的 `__all__` 只导出 Protocol、view dataclass、provider 实现和工厂函数，不导出内部 helper（`_validate_snapshot_rows`、`_require_event` 等）。

**Verdict**: 导出边界清晰。

---

## Summary

| Finding | Verdict | Blocks? |
|---|---|---|
| F1 — prompt 只来自 durable USER_INPUT_ACCEPTED | CORRECT | No |
| F2 — continuity 只读 canonical + 稳定排序 | CORRECT | No |
| F3 — typed Protocol 无 Any/object | CORRECT | No |
| F4 — AttemptDispatchSnapshot 只承载 refs | CORRECT | No |
| F5 — no-tool request 三重防线 | CORRECT | No |
| F6 — NoToolExecutor 只是防线 | CORRECT | No |
| F7 — 未越界实现 | CORRECT | No |
| F8 — messages 构造顺序 | CORRECT | No |
| F9 — EventLog reader 窄化 | CORRECT | No |
| F10 — 测试覆盖度 | CORRECT | No |
| F11 — 包导出边界 | CORRECT | No |

## Verdict

**No blocking findings. No nonblocking findings. Slice P5-S2 可以接受。**

实现与 plan P5-S2 / §3.4 和 design §23 完全对齐：

- 当前 prompt 只来自 durable `USER_INPUT_ACCEPTED.payload_json.display_text`，经 `RunRow.input_event_id` → `EventLog.read_event_by_id` → canonical + type 校验链。
- Continuity 通过窄化 EventLog reader 读取五种 canonical event types，按 `event_sequence ASC` 排序，排除 preview / projection_signal / diagnostic，排除当前 Run 自身事件，只投影 `USER_INPUT_ACCEPTED` 和 `RUN_SUCCEEDED`。
- 八个 typed Protocol 定义清晰，所有 dataclass 字段强类型，`cast` 仅用于 `json.loads` 返回值窄化。
- `AttemptDispatchSnapshot` 只含 durable identity refs、dispatch refs、`policy_snapshot_ref` 和 `CancellationToken`。
- No-tool 约束三重防线：`NoopToolSchemaSnapshotProvider` 返回空 + `PolicySnapshot.__post_init__` 校验 + `_validate_no_tool_snapshot` build 时校验。
- `NoToolExecutor` 纯防御，返回 `ToolCancelledOutcome`。
- Messages 构造顺序：scene → memory(empty) → compact(empty) → continuity → current user input。
- 未越界实现 scheduler / LocalProxy / ToolRuntime / Engine ingest / Memory / Context Governance。
- 11 tests 覆盖 plan 全部测试要求，pyright 0 errors，弱类型守卫通过。
