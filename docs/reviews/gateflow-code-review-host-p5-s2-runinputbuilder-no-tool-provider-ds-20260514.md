# Host Phase 5 P5-S2 RunInputBuilder And No-tool Provider Boundary 代码审查报告

- **审查对象**: Host Phase 5 P5-S2 未提交实现 diff
- **审查分支**: `feat/host-phase5-local-dispatch`
- **审查日期**: 2026-05-15
- **审查角色**: 独立代码审查员 (review only, no production changes)
- **设计真源**: `docs/host/design.md` §23, `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S2/§3.4

## 审查范围

已审查文件:

| 文件 | 状态 | 说明 |
|---|---|---|
| `dayu/host/run_input.py` | 新增 | RunInputBuilder + typed providers + NoToolExecutor |
| `dayu/host/api.py` | 修改 | 新增 `AttemptDispatchSnapshot` |
| `dayu/host/durable/event_log.py` | 修改 | 新增 `read_run_input_continuity_events` |
| `dayu/host/__init__.py` | 修改 | 导出 `AttemptDispatchSnapshot` |
| `tests/host/test_run_input_builder.py` | 新增 | 5 个测试 |
| `tests/host/test_package_exports.py` | 修改 | 导出白名单更新 |

未改动文件确认:
- `dayu/host/durable/state.py` — P5-S2 未触碰 ✓
- `dayu/host/durable/run_transition.py` — P5-S2 未触碰 ✓
- `tests/host/test_weak_typing_guard.py` — P5-S2 未触碰 ✓

## 结论摘要

**未发现阻塞性 (blocking) 问题。接受此 slice。**

发现 1 个 Medium 建议项和 2 个 Low 建议项，均为非阻塞性。

---

## 逐项审查

### 1. `AttemptDispatchSnapshot` — api.py

**设计要求** (§3.4): 只承载 durable identity refs、dispatch refs、policy snapshot ref 与 cancellation token。

**实现**:
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

**审查结果**: 正确。
- 仅承载 identity refs + dispatch refs + policy ref + cancellation token ✓
- `runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 均未混入 ✓
- `__post_init__` 对 7 个文本字段做非空校验 ✓
- `cancellation_token` 类型为 `CancellationToken` Protocol（非具体实现） ✓
- 已在 `dayu.host.api.__all__` 和 `dayu.host.__all__` 中导出 ✓
- 测试 `test_package_exports.py` 白名单已同步更新 ✓

### 2. 当前 Run Fact Provider — `DurableCurrentRunFactProvider`

**设计要求**: 当前 prompt 只能来自 durable `USER_INPUT_ACCEPTED.payload_json.display_text`，不能读取 UI 临时状态。

**实现** (`run_input.py:293-385`):
1. `read_run_by_id` → Run row
2. `read_attempt_by_id` → Attempt row
3. `read_dispatch_record_by_attempt_id` → Dispatch record row
4. `_validate_snapshot_rows` — 交叉校验 5 个 identity 维度
5. `run.input_event_id` → `read_event_by_id` → `_require_event(USER_INPUT_ACCEPTED)` ✓
6. `run.accepted_event_id` → `read_event_by_id` → `_require_event(RUN_ACCEPTED)` ✓
7. `run.started_event_id` → `read_event_by_id` → `_require_event(RUN_STARTED)` ✓
8. `_payload_object` → `json.loads(event.payload_json)` → `_required_payload_text(display_text)` ✓

**审查结果**: 正确。
- user_prompt 完全来自 durable `USER_INPUT_ACCEPTED.payload_json.display_text` ✓
- 测试 `test_current_user_message_comes_from_durable_user_input` 证明 transient prompt mutation 不影响 builder 输出 ✓
- payload 解析包含多层防御: JSONDecodeError → Mapping check → field type check ✓
- 事件 scope 校验 (`_validate_current_event_scope`) 确保事件归属正确 ✓

### 3. Session Continuity Provider — `DurableSessionContinuityProvider`

**设计要求**: 只读 canonical facts，按 `event_sequence` 稳定排序，不消费 preview/diagnostic/projection_signal。

**实现** (`run_input.py:388-443`):

SQL 查询 (`event_log.py:419-478`):
```sql
WHERE session_id = ?
  AND event_class = ?          -- 'canonical_fact' 排除 preview/diagnostic/projection_signal
  AND event_sequence < ?       -- 当前 Attempt 边界之前
  AND event_type IN (?, ?, ?, ?, ?)  -- 白名单 5 种类型
ORDER BY event_sequence ASC    -- 全局稳定排序
```

白名单: `USER_INPUT_ACCEPTED`, `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST`

Python 层过滤:
- `event.run_id == snapshot.run_id` → skip（当前 Run 自己的事件由 CurrentRunFacts 处理）

**审查结果**: 正确。
- `event_class = 'canonical_fact'` 排除 preview / diagnostic / projection_signal ✓
- `event_sequence < before_event_sequence` 排除当前 Attempt 及之后的事件 ✓
- `ORDER BY event_sequence ASC` 稳定排序 ✓
- 当前 Run 事件通过 `run_id` 过滤排除 ✓
- 测试 `test_continuity_uses_event_sequence_and_ignores_non_canonical` 证明:
  - projection_signal 事件被忽略 ✓
  - preview 事件被忽略 ✓
  - 输出按 event_sequence 排序 ✓

### 4. Continuity 事件投影 — `_continuity_message_from_event`

**实现** (`run_input.py:886-912`):

| Event Type | 投影 |
|---|---|
| `USER_INPUT_ACCEPTED` | `UserMessage(content=display_text)` |
| `RUN_SUCCEEDED` | `AssistantMessage(content=final_answer\|content\|summary_text)` |
| `RUN_FAILED` | `None` |
| `RUN_CANCELLED` | `None` |
| `RUN_LOST` | `None` |

**审查结果**: 正确。RUN_FAILED / RUN_CANCELLED / RUN_LOST 在 Phase 5 no-tool 场景下无有效 assistant 输出可投影，返回 None 符合预期。这些事件仍在 SQL 白名单中是因为:
1. 它们是 Session canonical fact 完整集合的一部分
2. 后续 Phase（如错误恢复 / 重试）可能需要它们的投影
3. SQL 层与投影层分离: SQL 负责"哪些事实相关"，投影负责"如何映射为 message"

### 5. No-tool 约束验证

**三道防线**:

| 防线 | 位置 | 检查 |
|---|---|---|
| PolicySnapshot | `run_input.py:155-165` | `allow_tool_calls` 必须为 `False` |
| NoopToolSchemaSnapshotProvider | `run_input.py:484-498` | `tool_schemas=()`, `disable_tools=True` |
| `_validate_no_tool_snapshot` | `run_input.py:936-952` | 三重校验 |

**审查结果**: 正确。
- `disable_tools=True` ✓
- `tool_schemas=()` ✓
- `allow_tool_calls=False` ✓
- 测试 `test_no_tool_request_fields_are_disabled` 覆盖全部三项 ✓

### 6. NoToolExecutor — run_input.py:501-526

**设计要求**: 若 Engine 仍发出工具调用，每个 call 返回 `ToolCancelledOutcome(reason=host_cancelled)`。

**实现**:
```python
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

**审查结果**: 正确。
- 与输入 `calls` 严格双射（每个 call 对应一个 record） ✓
- 每个 outcome 都是 `ToolCancelledOutcome(reason=host_cancelled)` ✓
- 不实现任何业务工具或 `fetch_more` ✓
- `NoToolExecutorProvider.load_tool_executor` 始终返回同一实例 ✓

### 7. AgentRunRequest 构造 — `RunInputBuilder.build()`

**message 顺序** (`run_input.py:685-696`):
```python
messages = (
    *scene_parameter_provider.build_scene_messages(...),  # system scene
    *memory.messages,                                      # (empty in P5)
    *compact.messages,                                     # (empty in P5)
    *continuity.messages,                                  # session history
    UserMessage(content=current_facts.user_prompt),        # current user
)
```

**审查结果**: 正确。
- System scene → memory → compact → continuity → current user ✓
- 与 plan §3.4 消息顺序一致 ✓
- `disable_tools=tool_snapshot.disable_tools` (=True) ✓
- `tool_schemas=tool_snapshot.tool_schemas` (=()) ✓
- `tool_executor=NoToolExecutor` ✓
- `cancellation_token=attempt_snapshot.cancellation_token` ✓

### 8. 确定性构建

**测试**: `test_build_is_deterministic_for_same_eventlog_and_policy`

两次 `build()` 调用产生的 messages 完全一致（按 message content 逐条比较）。

**审查结果**: 正确。所有 providers 从同一 durable store / policy snapshot 读取，无外部状态依赖。

### 9. Noop Provider 边界

| Provider | 输出 | 是否创建 durable rows |
|---|---|---|
| `NoopMemorySnapshotProvider` | `messages=()`, `cursor=None` | 否 |
| `NoopCompactArtifactProvider` | `messages=()`, `ref=None`, `digest=None` | 否 |
| `NoopToolSchemaSnapshotProvider` | `tool_schemas=()`, `disable_tools=True` | 否 |

**测试**: `test_noop_providers_do_not_create_durable_rows` — build 前后 event_log / payload_descriptors / host_sqlite_payloads 的 row 数不变 ✓

### 10. 越界检查

| 禁止实现项 | 状态 |
|---|---|
| Scheduler | 未实现 ✓ |
| LocalProxy | 未实现 ✓ |
| WorkerProxy | 未实现 ✓ |
| Engine dispatch | 未实现 ✓ |
| EngineEvent ingest | 未实现 ✓ |
| ToolRuntime | 未实现 ✓ |
| 真实 tool execution | 未实现 ✓ |
| Engine 文件修改 | 未修改 ✓ |
| UI / Service transient 状态读取 | 未读取 ✓ |
| 弱类型 (Any/object/无类型) | 无 ✓ |

---

## 发现项

### M1 (Medium) — `_continuity_message_from_event` 对 RUN_FAILED / RUN_CANCELLED / RUN_LOST 返回 None，但 SQL 仍查询并加载这些事件

**文件**: `dayu/host/run_input.py:886-912`, `dayu/host/durable/event_log.py:419-478`

**证据**:
```python
# event_log.py — SQL 白名单包含 5 种 event type
_RUN_INPUT_CONTINUITY_EVENT_TYPES = (
    "USER_INPUT_ACCEPTED", "RUN_SUCCEEDED", "RUN_FAILED",
    "RUN_CANCELLED", "RUN_LOST",
)

# run_input.py — 投影返回 None 给其中 3 种
if event.event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
    return UserMessage(...)
if event.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
    ...
    return AssistantMessage(...)
return None  # RUN_FAILED, RUN_CANCELLED, RUN_LOST 落在此处
```

RUN_FAILED / RUN_CANCELLED / RUN_LOST 事件被 SQL 查询加载、遍历、调用 `_payload_object` 做 JSON 解析，最后在 `_continuity_message_from_event` 中返回 None 被丢弃。

**影响**: 当 Session 历史中包含大量 RUN_FAILED / RUN_CANCELLED / RUN_LOST 事件时，存在无效的 payload JSON 解析开销。无正确性问题——这些事件不会被错误地投影为 message。

**建议**: 要么 (a) Phase 5 从 SQL 白名单中移除这三种类型（当前无投影需求），后续 Phase 需要时再加回；要么 (b) 在 `_continuity_message_from_event` 开头做快速短路，避免 payload JSON 解析。方案 (a) 更干净，但需一致更新 `_RUN_INPUT_CONTINUITY_EVENT_TYPES` 和对应的模块级常量。

**是否阻塞**: 否。当前无正确性问题，SQL 层的完整白名单为后续 Phase 预留了扩展空间，且投影短路已在函数尾部（不提前解析 payload 是一个独立优化）。

### L1 (Low) — `PolicySnapshot.__post_init__` 与 `AttemptDispatchSnapshot.__post_init__` 的空值校验风格不一致

**文件**: `dayu/host/api.py:273`, `dayu/host/run_input.py:155-165`

**证据**:
- `AttemptDispatchSnapshot.__post_init__` 使用 `_require_non_empty(field, field_name=...)` — 只检查空字符串
- `PolicySnapshot.__post_init__` 使用 `self.policy_snapshot_ref.strip() == ""` — 检查空字符串和纯空白字符串

**影响**: 极低。纯空白 `policy_snapshot_ref` 在正常流程中不会产生。

**建议**: 统一使用 `_require_non_empty` helper 或将 `.strip()` 检查加入 `_require_non_empty`。

**是否阻塞**: 否。

### L2 (Low) — `_NeverCancelledToken` 未显式声明实现 `CancellationToken` Protocol

**文件**: `tests/host/test_run_input_builder.py:72-97`

**证据**: 测试 token `_NeverCancelledToken` 通过结构子类型满足 `CancellationToken` Protocol（三个方法签名均匹配），但未显式继承该 Protocol。

**影响**: 仅在测试中使用，且 `CancellationToken` 是 `@runtime_checkable` Protocol，`isinstance(token, CancellationToken)` 在运行时返回 `True`。无实际功能影响。

**建议**: 可以添加 `class _NeverCancelledToken(CancellationToken)` 使意图更明确。

**是否阻塞**: 否。

---

## 架构约束检查

- [x] 分层架构: `run_input.py` 依赖 `dayu.host.api` / `dayu.host.durable.*` / `dayu.engine.contracts.*` / `dayu.contracts.*`，无反向依赖
- [x] Engine 不 import Host 类型 ✓
- [x] 无 `Any` / `object` / 无类型签名: 所有函数参数和返回值均有完整类型注解
- [x] 中文 docstring: 所有新增类和函数均有完整中文 docstring，含参数、返回值、异常
- [x] 无胶水 seam / lazy import / hasattr-getattr 滥用
- [x] 无 God object: `RunInputBuilder` 通过 8 个 typed Protocol 委托而非内聚所有逻辑
- [x] 无兼容性代码: 全部为 fresh 实现
- [x] `dayu/host/durable/state.py` P5-S2 未改动 ✓
- [x] `test_weak_typing_guard.py` P5-S2 未改动 ✓

## 计划对标检查

| 需求 | 状态 |
|---|---|
| 当前用户消息只来自 durable `USER_INPUT_ACCEPTED` | ✓ |
| continuity 只读 canonical facts，按 `event_sequence` 排序 | ✓ |
| 不接受 preview / diagnostic / projection_signal 事件 | ✓ |
| `AttemptDispatchSnapshot` 只承载 identity/refs/cancellation token | ✓ |
| no-tool request: `disable_tools=True` | ✓ |
| no-tool request: `tool_schemas=()` | ✓ |
| no-tool request: `allow_tool_calls=False` | ✓ |
| `NoToolExecutor` 只作为防线 | ✓ |
| 不实现 scheduler / LocalProxy / ToolRuntime / Engine ingest | ✓ |
| 稳定确定性构建 | ✓ |

## 验证结果

```
11 passed in 0.22s
pyright: 0 errors, 0 warnings, 0 informations
git diff --check: no whitespace errors
```

## 裁决

**接受此 slice。** 无阻塞性发现。1 个 Medium (RUN_FAILED/CANCELLED/LOST 事件的 SQL 查询+解析开销但无投影) 和 2 个 Low 建议项均为非阻塞性改进机会。核心实现——durable 当前 prompt 读取、canonical continuity 投影、no-tool 约束和 NoToolExecutor 防线——均正确且通过了所有计划要求的测试。
