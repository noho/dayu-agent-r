# WU-SEMANTIC-OWNERSHIP-01 / P2-E Implementation Review - AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p2-e-implementation-review-ds.md`
- Included scope: 未提交 diff 中的 6 个测试文件变更
- Excluded scope: 未跟踪的 `docs/reviews/` 下 new artifacts（不在 diff 范围内）
- Parallel review coverage: 无

## Diff Summary

| 文件 | 变更性质 |
|---|---|
| `tests/engine/runners/openai/test_stream_idle.py` | 提取 `_heartbeat_runner()` helper；正向测试改为 `STREAM_DEBUG_LOG_LEVEL` 捕获；新增普通 `logging.DEBUG` 负向非捕获测试 |
| `tests/engine/test_engine_event_contract.py` | `IterationStartedData` 字段快照纳入 `input_projection` |
| `tests/engine/test_package_exports.py` | `EXPECTED_EXPORTS` 纳入 `RunnerInputMessageProjection`、`RunnerInputToolCallProjection` |
| `tests/host/test_package_exports.py` | `EXPECTED_API_EXPORTS` 纳入 `HostThinkingView` |
| `tests/host/test_phase7_waiting_integration.py` | 旧英文 fallback guidance 断言替换为 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage` 协议闭环断言，含 `tool_call_id` identity closure |
| `tests/host/test_purge_session.py` | `_insert_event` 新增 `event_type` 参数；新增 `_insert_cancel_request_event_if_needed` helper；`_insert_run_row` 写入 `cancel_request_event_id` |

生产代码未修改。所有变更只涉及测试断言与测试 fixture。

## Production Contract Alignment Evidence

### Stream heartbeat level

- `dayu/runtime/log_levels.py:16`: `STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1`（即整数值 9），`DEBUG_LOG_LEVEL = logging.DEBUG`（即整数值 10）。
- `dayu/engine/runners/openai/runner.py:968-969`: heartbeat 日志以 `STREAM_DEBUG_LOG_LEVEL, "runner.stream_idle.heartbeat ..."` 发出。
- 正向测试用 `caplog.at_level(STREAM_DEBUG_LOG_LEVEL)`（level 9），可捕获 heartbeat；负向测试用 `caplog.at_level(logging.DEBUG)`（level 10），不可捕获 heartbeat。

### Engine `input_projection` / projection exports

- `dayu/engine/contracts/engine_events.py:112`: `IterationStartedData.input_projection: tuple[RunnerInputMessageProjection, ...]`。
- `dayu/engine/__init__.py:80-81, 169-170`: `RunnerInputMessageProjection` 与 `RunnerInputToolCallProjection` 在包根 `__all__` 中。
- `docs/engine/design.md` §2 明确这两个类型是包根公共契约导出。

### Host `HostThinkingView` export

- `dayu/host/api.py:2649`: `class HostThinkingView` 定义。
- `dayu/host/api.py:3565`: `"HostThinkingView"` 在 `api.__all__` 中。
- `dayu/host/__init__.py:200`: `"HostThinkingView"` 在包根 `__all__` 中。
- `dayu/host/read_api.py:1110`: `_thinking_from_row` 返回 `HostThinkingView | None`。

### Purge `cancel_request_event_id` durable invariant

- `dayu/host/durable/schema.py:484, 506, 539`: `cancel_request_event_id TEXT NULL` 列，外键引用 `event_log`，CHECK 约束要求 `cancelling`/`cancelled` 状态时 `cancel_request_event_id IS NOT NULL`。
- `dayu/host/durable/state.py:270`: `RunRow.cancel_request_event_id: str | None`。
- 生产 `dayu/host/durable/run_transition.py` 中 cancel transition 始终写入 typed `cancel_request_event_id`。

## Review Focus Findings

### 1. 生产代码无变更

确认 diff 中无 `dayu/` 下生产代码变更。所有变更均为测试文件。不通过。

### 2. Stream heartbeat 正负语义

**入口/函数**: `test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`（正向）、`test_idle_heartbeat_is_not_captured_at_normal_debug`（负向）

**审查结论：通过，无发现。**

证据链：
- 两个测试共用 `_heartbeat_runner()` helper（`delay_seconds=0.06`、`stream_idle_heartbeat_seconds=0.02`），确保等价 idle 条件下的 heartbeat 本应产生。
- 正向测试用 `STREAM_DEBUG_LOG_LEVEL`（整数值 9）捕获，断言 `stream_idle.heartbeat` 可见且无 HTTP 错误、stream 正常完成。
- 负向测试用 `logging.DEBUG`（整数值 10）捕获，断言 `stream_idle.heartbeat` 不可见，同时断言 stream 正常完成（`events[-1].type is RunnerEventType.RUNNER_DONE`），排除了 heartbeat 从未有机会产生的假通过场景。
- 生产 runner 日志发出级别（9）低于普通 DEBUG（10），负向断言语义正确。

### 3. Engine/Host export 与 event snapshot 对齐

**入口/函数**: `test_iteration_started_runner_input_signal_fields_are_locked`、`test_engine_all_matches_expected_set`、`test_host_all_matches_current_public_contracts`、`test_api_all_stays_request_snapshot_boundary`

**审查结论：通过，无发现。**

- `input_projection` 已在 `docs/engine/design.md` §14 记录为 `IterationStartedData` 字段，且在 production `engine_events.py:112` 存在。
- `RunnerInputMessageProjection` / `RunnerInputToolCallProjection` 已在 `docs/engine/design.md` §2 列为包根导出。
- `HostThinkingView` 已在 `dayu/host/api.py` 定义且在 `api.__all__` 与包根 `__all__` 中导出。
- 变更均为测试快照对已接受 production contract 的对齐，不是 production drift。

### 4. Wait-resume 协议闭环

**入口/函数**: `test_local_awaiting_tool_manual_resolve_resumes_run`

**审查结论：通过，无发现。**

具体断言分析：

```python
protocol_messages = resume_request.messages[-3:]
user_message, assistant_message, tool_message = protocol_messages
```

- 测试诊断确认 `resume_request.messages` 为 `[SystemMessage, UserMessage, AssistantMessage(tool_call), ToolMessage]`。取最后 3 条消息聚焦工具协议闭环是可接受的——SystemMessage 是 Engine 级前缀，不属于工具调用协议语义；测试不要求模型理解 SystemMessage。
- `assistant_tool_call.id == batch.calls[0].tool_call_id`：AssistantToolCall 的 id 与原 awaiting `tool_call_id` identity 闭合。
- `assistant_tool_call.name == _TOOL_NAME`：工具名一致。
- `assistant_tool_call.arguments == {"ticker": "DAYU"}`：参数一致。
- `tool_message.tool_call_id == assistant_tool_call.id`：ToolMessage 与 AssistantToolCall 的 id 闭合。
- `tool_content["answer"] == 42`：业务结果来自 `_completed_request` 的 resolved tool outcome。

协议闭环完整覆盖 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage` 链路和 `tool_call_id` identity closure。不再断言旧英文 fallback guidance。

SystemMessage 前缀处理：测试明确只提取最后 3 条消息做协议断言。SystemMessage 存在但不影响工具协议闭环验证。若需验证 SystemMessage 不含有害内容，应在 Engine runner input projection 快照测试中覆盖，不在本 wait-resume integration 测试范围内。

### 5. Purge fixture CANCEL_REQUESTED 语义

**入口/函数**: `_insert_cancel_request_event_if_needed`、`_insert_run_row`

**审查结论：通过，无发现。**

- `_insert_cancel_request_event_if_needed` 仅在 `status in (cancelling, cancelled)` 时写入 CANCEL_REQUESTED EventLog 行：`if status not in (_RUN_STATUS_CANCELLING, _RUN_STATUS_CANCELLED): return None`。
- EventLog 行使用专用 `event_type=_EVENT_TYPE_CANCEL_REQUESTED`（`"CANCEL_REQUESTED"`），`event_id` 使用 `f"event-{run_id}-cancel-requested"` 前缀，不复用无关 event。
- `_NON_TERMINAL_RUN_STATUSES` 不包含 `cancelled`，仅包含 `cancelling`。`cancelled` 是 terminal 状态。helper 同时处理两个 status 是防御性实现——若未来测试需要对 `cancelled` Run 使用 `_insert_run_row`，同样获得合法 `cancel_request_event_id`。
- `_SeedClosedSessionMatrixOperation` 对 `run_status != SUCCEEDED` 路径只调用 `_insert_run_row` 一次（for parent run），不插入 attempt / dispatch / wait / read-model 等 rows。对 `cancelling` parametrize 用例，额外 CANCEL_REQUESTED 行仅存在于 seed transaction 中，不在 purge 删除矩阵范围内（seed 不属于 purge 事务）。purge 拒收非终态 Run 的事务性是独立的。
- 生产 durable schema CHECK 约束 `cancel_request_event_id IS NOT NULL` 对应 `cancelling`/`cancelled` 状态的要求已通过 fixture 满足，未放宽 schema。

### 6. README/doc 触发

**审查结论：通过，无发现。需更新 README 的触发条件不成立。**

- 变更均为 `tests/` 下文件，按 AGENTS.md 触发规则应检查 `tests/README.md`。
- 本次变更不引入新测试类别、新测试命令或新维护约定；仅对齐现有测试断言与 fixture 到已记录的生产契约。无需更新 `tests/README.md`。
- 生产代码未变更。`dayu/engine/`、`dayu/host/` 均未修改。`dayu/engine/README.md` 与 `dayu/host/README.md` 触发条件不成立。

### 7. AGENTS.md 合规

**审查结论：通过，无发现。**

- 所有新增函数（`_heartbeat_runner`、`test_idle_heartbeat_is_not_captured_at_normal_debug`、`_insert_cancel_request_event_if_needed`）均提供完整中文 docstring，含参数、返回值、异常说明。
- `_insert_event` 新增 `event_type` 参数，docstring 同步更新 `:param event_type: EventLog 事件类型。`。
- 未引入 `Any`、`object`、无类型参数或返回值。
- 未使用 `hasattr`/`getattr` 绕过类型边界。
- 未引入下游 masking——所有变更均在上游测试 owner boundary 内（测试断言/fixture 对齐生产契约），不存在下游 fallback、兼容 shim 或特例分支。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- Wait-resume 协议闭环断言仅覆盖本地 integration fixture 路径，未覆盖真实 provider 恢复场景。该风险已由 `docs/reviews/wu-semantic-ownership-01-p2-e-implementation-codex.md` 归入已有 smoke / real-environment validation owners，当前 P2-E 范围内无新增风险。
- `_heartbeat_runner()` helper 的 `delay_seconds=0.06` 在极端慢速 CI 环境中理论上可能不足以触发 heartbeat（若实际 sleep 远长于 0.02s heartbeat 间隔则无影响；但若 stream 在第一次 readany delay 前已完成则 heartbeat 永不触发）。当前正向测试已充分覆盖 heartbeat 生产逻辑，负向测试依赖正向测试证明同条件下 heartbeat 本应产生。该风险为测试时序风险，不归入 P2-E scope。
- Broad matrix 中的 `edgar` 依赖 deprecation warning 与 P2-E 无关，归入已有外部依赖追踪。

## Verdict

**P2-E implementation review: PASS.**

7 个 broad-suite failure 的修复均落在正确的 owner boundary（测试断言/fixture 对齐已接受生产契约），生产代码无变更，stream heartbeat 正负语义完整，Engine/Host export snapshot 对齐已有设计真源，wait-resume 协议闭环断言覆盖 `tool_call_id` identity closure 与业务结果，purge fixture 专用 CANCEL_REQUESTED EventLog 行仅对 cancelling/cancelled 状态写入、不污染 succeeded 矩阵计数、不复用无关事件、不放宽 durable schema。无 README 更新需求，AGENTS.md 合规。
