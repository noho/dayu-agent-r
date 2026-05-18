# Post-P10 Wiring & Smoke Challenge Review

**日期**: 2026-05-18
**审阅者**: Phaseflow Independent Challenge Reviewer
**命题**: P10.5 实施完后，后续 Service 只调用 Host public interface / contract 即可完成普通本地多轮会话闭环。

**结论**: 命题在当前代码状态下**不成立**。存在 5 个 blocking 缺口和 5 个 non-blocking 缺口。

---

## Blocking Findings

按严重度降序排列。

### B1. 缺少稳定 Host runtime / composition root

`create_host_command_handle()` 明确拒绝 `local_execution` 非 None，Service 无法通过 public API 启动本地执行。

证据：
- `dayu/host/command.py:242-246` — `create_host_command_handle()` 在 `options.local_execution is not None` 时直接 `raise ValueError`，提示调用方"open HostDispatchScheduler explicitly"。
- `dayu/host/command.py:111-112` — `HostCommandHandle` 只持有 `durable_store`、`admission_service`、`active_registry`，不持有 scheduler、lane controller、projection catch-up 端口。
- 当前要跑起来，调用方必须手工导入 `dayu.host.dispatch.HostDispatchScheduler`，打开同 DB 的 `open_host_durable_store`，构造 `HostLocalExecutionOptions`，调用 `HostDispatchScheduler.open()`，再手动调用 `wake_queue_promotion()` 和 `drain_once()`。这条路径仅存在于 `tests/host/test_phase5_local_execution_integration.py`。Service 程序员不能通过 public API 完成此装配。

影响：p10 缺失清单 #1 未解决。命题直接失败——没有 composition root，Service 无法"只调用 Host public interface / contract"就跑起来。

### B2. Public command facade 与 scheduler wakeup 没有公共接线

`start_run` / `submit_followup` 提交后，Run 进入 `ACCEPTED` / `QUEUED`，但 admission service 的 wakeup port 是 no-op，scheduler 永远不会被唤醒。

证据：
- `dayu/host/admission.py:683` — `create_host_admission_service()` 默认 `wakeup_port=NoopAdmissionWakeupPort()`。
- `dayu/host/command.py:253-255` — `create_host_command_handle()` 调用 `create_host_admission_service()` 时未传 `wakeup_port`，使用默认 no-op。
- `dayu/host/admission.py:457-458` — `start_run()` 在 commit 后调用 `_wake_dispatch_if_needed` 和 `_wake_start_governance_if_needed`，写入 no-op port。
- `dayu/host/admission.py:493-494` — `submit_followup_queue()` 同样。
- `dayu/host/admission.py:353-358` — `NoopAdmissionWakeupPort` 的 `wake_dispatch` 和 `wake_queue_promotion` 都是空实现。
- 唯一的例外是 `dayu/host/command.py:671-673` — `resolve_wait()` 中直接调用 `host._admission_service.wakeup_port.wake_dispatch()`，但这个 wakeup_port 仍然是 no-op。

影响：p10 缺失清单 #2 未解决。"提交后自动开工"的铃没有接到工人那里。

### B3. 缺少 public final answer read path

`RunSnapshot.terminal_result_summary` 有 `summary_ref` / `summary_digest`，`HostEventView` 有 `payload_ref` / `payload_digest`，但 public API 没有 payload 读取函数。

证据：
- `dayu/host/api.py:1706-1709` — `TerminalResultSummary` 只包含 `status`、`summary_ref`、`summary_digest`，不包含 inline payload。
- `dayu/host/api.py:1977-1984` — `HostEventView` 只包含 `payload_ref` / `payload_digest`，不包含 inline payload。
- `dayu/host/read_api.py:36-88` — `get_run` 返回 `RunSnapshot`，`get_session` 返回 `SessionSnapshot`，`stream_run_events` 返回 `HostEventStream`。三者都不提供 payload 内容。
- `dayu/host/durable/payload.py:292` — `read_payload_descriptor()` 存在，但它是 durable 层内部函数，未在 `dayu/host/__init__.py` 中导出。
- `dayu/host/__init__.py:1-188` — `__all__` 列表中无任何 payload read 函数。
- `dayu/host/engine_ingest.py:1968-2005` — `_write_terminal_summary()` 会写入 final answer payload，但读取路径只在 durable 内部。

影响：p10 缺失清单 #5 未解决。Service 可以知道 Run "SUCCEEDED"，但没有稳定 public 方法读取"回答正文"。

### B4. S1/S2/S3/S4 mock smoke 测试不存在

仓库中不存在任何通过 public API 完成多轮会话闭环的 smoke 测试。

证据：
- `tests/host/` 目录下 55 个测试文件，无一包含 `multi_turn`、`second_turn`、`continuity` 等关键词的**端到端多轮 smoke**。
- `tests/host/test_dispatch_scheduler.py:2085` — `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 是最接近的多轮测试，但它是 scheduler 层测试，直接操作 durable store，不通过 public API。
- `tests/host/test_phase5_local_execution_integration.py` — 所有"集成"测试都直接 `import HostDispatchScheduler`，手工 `open_host_durable_store`，手工调用 `scheduler.wake_queue_promotion()` + `scheduler.drain_once()`，并通过 `sqlite3.connect(db_path)` 直接读取 durable 内部表校验状态。
- `tests/host/test_public_run_api.py` — `start_run` / `submit_followup` 测试只验证 admission 阶段的 `RunSnapshot` 返回，不触发实际执行（因为没有 scheduler）。
- `tests/host/test_public_run_api.py:132-133` — post-p10.md 注明 `test_start_run_direct_running_and_attach_active` 和 `test_submit_followup_queue_active_and_no_active` 已**失败**，因为 P10 后语义从 `RUNNING` 变为 `ACCEPTED`。

影响：Smoke Coverage Matrix 中 S1/S2/S3/S4 四类 smoke **全部未覆盖**。命题的第二目标（用 smoke 验证第一目标成立）无支撑。

### B5. 现有测试绕过 public API 读取内部状态，违反防作弊约束

`test_phase5_local_execution_integration.py` 中的测试通过 `sqlite3.connect` 直接查询 durable 内部表。

证据：
- `tests/host/test_phase5_local_execution_integration.py:1242-1261` — `_refs()` 函数通过 `sqlite3.connect` 直接 JOIN `host_runs`、`host_attempts`、`host_attempt_dispatch_records` 表读取 Attempt/execution/dispatch id。
- `tests/host/test_phase5_local_execution_integration.py:1281-1295` — `_run_status()` 通过 `sqlite3.connect` 直接查询 `host_runs` 表。
- `tests/host/test_phase5_local_execution_integration.py:1298-1312` — `_attempt_status()` 同样。
- `tests/host/test_phase5_local_execution_integration.py:1315-1329` — `_event_type_count()` 直接查询 `event_log` 表。
- `tests/host/test_phase5_local_execution_integration.py:1332-1348` — `_wait_for_run_status()` 轮询 `sqlite3.connect` 而不是通过 `get_run()` public read path。

这些做法违反 post-p10.md:124 "任何 smoke 如果绕过 Host local runtime、直接操作 scheduler internals、直接查询 durable 内部表取得 final answer……都不能计入本矩阵覆盖"。

---

## Non-Blocking Findings

按严重度降序排列。

### N1. `compose_host_local_execution_options` 不完整

`compose_host_local_execution_options()` 只补充 context budget policy，不是完整的 composition root。

证据：
- `dayu/host/command.py:274-302` — 函数只做 `replace(options.local_execution, context_budget_policy=...)`，不创建 scheduler、不打开 lane、不连线 wakeup ports、不启动 drain loop。
- 即使 Service 能通过某种方式调用此函数，它拿到的仍是 `HostLocalExecutionOptions`，不是可运行的 runtime。

影响：这个 helper 是朝正确方向的一步，但远不足以让 Service "开箱即用"。它属于 composition root 的一部分，但不是 composition root。

### N2. Projection catch-up port 在 command handle 侧是 no-op

`create_host_admission_service()` 的 `projection_catchup_port` 默认为 `NoopProjectionCatchupPort()`。

证据：
- `dayu/host/admission.py:684-688` — `projection_catchup_port` 默认 `NoopProjectionCatchupPort()`。
- `dayu/host/admission.py:268-276` — `NoopProjectionCatchupPort.catch_up_projection()` 是空实现。
- Scheduler 在 `dispatch.py:514` 的 `wake_queue_promotion` 中会调用 `catch_up_projection_best_effort(self._projection_catchup_port)`，但 command handle 的 admission service 侧不会。

影响：如果 composition root 不覆写此端口，admission commit 后的 projection catch-up（影响 memory / read model）不会自动发生。但 composition root 可以注入真实的 `ProjectionCatchupPort`，所以属于 wiring gap 而非独立缺口。

### N3. Follow-up execution target 是硬编码默认值

`submit_followup` 没有让 Service 指定 execution target 的字段。

证据：
- `dayu/host/command.py:108` — `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"`。
- `dayu/host/command.py:472-474` — `submit_followup` 在构造 `SubmitFollowupQueueAdmissionInput` 时写死此 target。
- `dayu/host/api.py:1528-1580` — `SubmitFollowupRequest` 没有 `execution_target` 字段。

影响：第一轮可以通过 `StartRunRequest.execution_target` 指定执行目标，但 follow-up 无法指定。对于普通多轮场景，通常 follow-up 应沿用同一执行目标，当前是硬编码默认值而非沿袭。

### N4. Public Run API 状态语义与部分测试/README 不一致

P10 后 Run 先进入 `ACCEPTED`，但旧测试仍期待 `RUNNING`。

证据：
- `dayu/host/api.py:275` — `RunStatus.ACCEPTED = "accepted"` 已定义。
- `tests/host/test_public_run_api.py:544-545` — `test_submit_followup_queue_active_and_no_active` 的 docstring 仍写"无 active 时直接 running"，实际 P10 代码返回 `ACCEPTED`。
- `tests/host/test_public_run_api.py:132-133` — post-p10.md 已记录该测试和 `test_start_run_direct_running_and_attach_active` 失败。

影响：p10 缺失清单 #3 未解决。这会导致 Service 调用方对 `start_run`/`submit_followup` 返回状态的预期错误。

### N5. `StartRunRequest` 缺少 `execution_target` 以外的 policy 传递字段

`StartRunRequest` 有 `execution_target` 和 `queue_policy`，但没有 scene context、system prompt 等 policy 传递字段。

证据：
- `dayu/host/api.py:1416-1457` — `StartRunRequest` 字段只有 `context`、`session_id`、`client_request_id`、`input`、`execution_target`、`queue_policy`。
- `dayu/host/run_input.py` — `RunInputBuilder` 的 `build()` 方法不接收 scene context / system prompt 作为参数。
- 当前 system prompt 来源是 `PolicySnapshot.runner_spec` + `PolicySnapshot.agent_policy`，都是 composition root 注入的固定值，无法 per-run 变化。

影响：对于普通多轮场景，如果 Service 需要传递 scene 信息（如"请分析这份财报的盈利能力"），当前 `HostInput.display_text` 可以承载部分信息，但 system prompt 级 scene 注入没有 per-run 传递路径。这是一个 Service 接入时需要讨论的 public API 缺口，按 post-p10.md:31-32 的护栏，需要用户讨论确认。

---

## Smoke Coverage Matrix 状态

| Smoke | 覆盖状态 | 证据 |
|-------|---------|------|
| S1 no-tool multi-turn | blocking gap | 无测试存在 |
| S2 mock-tool multi-turn | blocking gap | 无测试存在 |
| S3 real-runner multi-turn | blocking gap | 无测试存在 |
| S4 compact smoke | blocking gap | 无测试存在 |

四项 smoke 均未覆盖。不存在可以通过 public API 完成的端到端多轮测试。

---

## 组件边界检查

| 组件边界 | 状态 | 说明 |
|---------|------|------|
| composition root | **blocking gap** | B1，不存在 |
| scheduler lifecycle | **blocking gap** | B2，无 public wakeup wiring |
| worker task supervision | 代码就绪，无 public 接线 | `dispatch.py` 的 `_consume_worker_events` + `ActiveWorkerRegistry` 已实现，但只能通过 scheduler 访问 |
| projection catch-up | non-blocking | N2，command handle 侧 no-op |
| memory consistency | 代码就绪，无 public 接线 | `dispatch.py:_catch_up_memory_projection_before_worker` + `memory_repair.py:catch_up_conversation_memory_projection` 已实现 |
| ToolRuntime accept barrier | 代码就绪，无 public 接线 | `tool_runtime.py:DefaultHostToolFactAcceptPort` 已实现，通过 `_run_input_builder_for_dispatch` 注入 |
| RunInputBuilder provider | 代码就绪，无 public 接线 | `run_input.py` 的 `DurableMemorySnapshotProvider` + `DurableCompactArtifactProvider` 已实现 |
| Context Governance allow/compact path | 代码就绪，无 public 接线 | `dispatch.py:_run_pre_start_governance` 已实现 proactive + reactive governance |
| terminal closeout | 代码就绪，无 public 接线 | `engine_ingest.py` terminal closeout + summary write 已实现，但无 public read path (B3) |
| queue promotion | 代码就绪，无 public 接线 | `dispatch.py:wake_queue_promotion` → `_run_pre_start_governance` → `_read_startable_run` 已实现 |
| final answer public read | **blocking gap** | B3 |

---

## 对命题的最终判断

**命题不成立。** 不考虑 Recovery，当前代码的 Host 内部多轮能力（Session/Run/Attempt/EventLog、admission、queue、dispatch、ToolRuntime accept barrier、memory projection、Context Governance）已落地在 `dayu/host` 内部模块中，但缺失以下关键组件才能让 Service "只调用 Host public interface / contract 即可完成普通本地多轮会话闭环"：

1. **稳定的 composition root**（B1）
2. **Public command → scheduler wakeup wiring**（B2）
3. **Public final answer read path**（B3）
4. **Mock smoke 证明**（B4）

这四个缺口中，B1 是根因——没有 composition root，B2/B3/B4 都无法从 Service 视角验证。B2 和 B3 是 B1 成立后的直接受益者。

non-blocking 的 N1-N5 不影响命题的 blocking 判断，但 N4 和 N5 是 public API 语义一致性缺口，需在 P10.5 implementation 中讨论。

---

## 风险提示

- 本文档只标记缺口，不提出具体 API 设计。任何涉及 public API 的新增或修改（composition root 接口、payload read 接口、follow-up execution target 字段等）必须按 post-p10.md:31-32 要求先与用户讨论确认。
- 本 review 不检查 Recovery、RemoteProxy、真实 web tools、ConfigLoader、真实 compactor adapter、callback/poller 生产后台循环——这些已明确在 post-p10.md 的"暂不考虑"列表中。
