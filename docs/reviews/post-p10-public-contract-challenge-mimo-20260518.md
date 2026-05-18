# Post-P10 Public Contract Challenge Review

**Reviewer**: MiMo (independent challenge)
**Date**: 2026-05-18
**Gate**: Post-P10 / P10.5 discussion
**Task type**: review / challenge
**Proposition**: P10.5 实施完后，后续 Service 只调用 Host public interface / contract 即可完成普通本地多轮会话闭环。

## 审查结论

**proposition 不成立**。当前 `dayu.host` public API 存在 4 项 blocking gap，使得 Service 无法仅通过 `dayu.host.__all__` 导出的接口完成"提交输入 → 等待执行 → 读取回答"的最小多轮闭环。这些 gap 必须在 P10.5 明确冻结，否则 P11+ 仍可合法修改接口，破坏"Service 只调 Host public interface / contract"的结论。

---

## Blocking Findings

### B1. 缺 final answer 内容读取 public facade

**严重度**: critical
**证据**: `dayu/host/api.py:1697-1709` (`TerminalResultSummary`)、`dayu/host/read_api.py:204-221` (`_event_view_from_row`)

`TerminalResultSummary` 只暴露 `status`、`summary_ref`、`summary_digest`，不暴露 summary payload 内容。`HostEventView` 只暴露 `payload_ref`、`payload_digest`，不暴露 inline payload。

`dayu/host/durable/payload.py:176` 的 `read_payload_descriptor` 和 `292` 的模块级 `read_payload_descriptor` 均不在 `dayu.host.__all__` 中，属于 durable 内部 API。

**影响**: Service 通过 `get_run()` 知道 Run `SUCCEEDED`，通过 `stream_run_events()` 知道有 terminal event，但无法通过 public API 读取"回答正文"。这是多轮会话闭环的硬 blocker：用户问了问题，系统执行完毕，但 Service 拿不到答案。

**P10.5 必须冻结**: 需要新增 public payload read facade，定义返回类型（`str`? `bytes`? `JsonValue`?）、错误语义（`NOT_FOUND`? `INVALID_STATE`?）、digest 校验行为，以及与 `TerminalResultSummary.summary_ref` 的对应关系。这个新 facade 会成为 Service 依赖的 stable contract，必须先 discussion。

### B2. 缺 Host local runtime / composition root

**严重度**: critical
**证据**: `dayu/host/command.py:242-246` (`create_host_command_handle` 显式拒绝 `local_execution`)、`dayu/host/dispatch.py:386-427` (`HostDispatchScheduler.__init__`)

`create_host_command_handle` 拒绝非空 `HostCommandHandleOptions.local_execution`，抛出 `ValueError` 并提示 "open HostDispatchScheduler explicitly"。`HostDispatchScheduler` 需要 `transaction_runner`、`event_log_store`、`local_execution`、`lane_controller`、`host_handle_id`、`active_registry`、`projection_catchup_port` 等 7 个参数，且 `open()` 是 async。

当前没有 `HostRuntime`、`HostLocalRuntime` 或其它 composition root 将 handle + scheduler + lifecycle 统一装配。测试 harness（如 `tests/host/test_phase5_local_execution_integration.py`）自行手工装配，但这些装配代码不在 `dayu.host` public 包中。

**影响**: Service 必须 import `dayu.host.dispatch.HostDispatchScheduler`（非 `__all__` 导出）、`dayu.host.durable.connection.open_host_durable_store`（durable 内部）、`dayu.host.durable.transaction.HostTransactionRunner`（durable 内部）等内部模块才能跑起来。这违反"只调 Host public interface / contract"的前提。

**P10.5 必须冻结**: 需要定义一个 public composition root（命名、构造参数、async context manager?、生命周期、关闭语义、错误语义、暴露方法）。这个 composition root 会成为 Service 的唯一入口，必须先 discussion。

### B3. command facade → scheduler wakeup 无 public 接线

**严重度**: critical
**证据**: `dayu/host/admission.py:353-366` (`NoopAdmissionWakeupPort`)、`dayu/host/admission.py:683` (`create_host_admission_service` 默认注入 no-op wakeup)、`dayu/host/command.py:228-268` (`create_host_command_handle` 不接受 wakeup port 参数)

`create_host_command_handle` 内部调用 `create_host_admission_service` 时未传 `wakeup_port`，默认使用 `NoopAdmissionWakeupPort`。这意味着 `start_run()` / `submit_followup()` / `resolve_wait()` 提交后，Run 进入 `ACCEPTED` / `QUEUED`，但 scheduler 不会被唤醒。

`HostDispatchScheduler.wake_dispatch()` (`dispatch.py:490`) 和 `wake_queue_promotion` 需要被显式调用，但 `HostCommandHandle` 没有暴露任何方法或参数让 Service 把 scheduler 的 wakeup 接到 command facade。

**影响**: Service 调用 `start_run()` 后 Run 停在 `ACCEPTED`，永远不会被 scheduler 拾起执行。这是多轮会话的硬 blocker。

**P10.5 必须冻结**: 需要明确 command facade 如何接收 scheduler wakeup：是 composition root 自动接线？还是 `HostCommandHandleOptions` 新增 wakeup port 参数？还是 composition root 内部构造 handle 时注入？无论哪种方案，wakeup 接线的 public contract 必须先 discussion。

### B4. 缺 Run terminal 等待 public API

**严重度**: high
**证据**: `dayu/host/read_api.py:37-87` (`get_session`、`get_run`、`run_snapshot_from_row`)、`dayu/host/__init__.py` (`__all__` 中无 `wait_for_terminal` 或类似函数)

当前 public API 只有 `get_run()` 返回瞬时 snapshot 和 `stream_run_events()` 补读事件。没有阻塞式等待 Run 进入终态的 public API。

**影响**: Service 必须自己写轮询循环 `while get_run(run_id).status not in TERMINAL: sleep(...)`。这不是 contract 层面的 blocker（轮询是合法模式），但会导致：
1. Service 代码不稳定：轮询间隔、超时、错误重试策略都由 Service 自行决定，不同 Service 实现不一致。
2. 与 `stream_run_events` 的 cursor 补读模式不协调：Service 需要同时维护轮询 cursor 和 terminal 等待逻辑。

**P10.5 必须冻结**: 至少明确"Service 等待终态"的推荐 public pattern。可以是：
- 新增 `await_terminal(host, run_id, timeout)` public API
- 或明确文档化"用 `get_run` 轮询"为 official pattern 并给出超时/错误建议
- 或 composition root 提供 terminal 等待辅助

无论哪种，这个 contract 的边界（超时语义、取消语义、错误码）必须在 P10.5 明确，否则 P11+ 可以随意新增等待 API 改变 Service 依赖。

---

## Non-blocking Findings

### N1. HostCommandHandle.close() 同步 vs HostDispatchScheduler.close() 异步生命周期不一致

**严重度**: medium
**证据**: `dayu/host/command.py:163` (`def close(self) -> None`)、`dayu/host/dispatch.py:1078` (`async def close(self) -> None`)

`HostCommandHandle.close()` 是同步方法，`HostDispatchScheduler.close()` 是异步方法。Service 需要分别处理两种关闭模式。如果 P10.5 引入 composition root，需要明确整体关闭语义是 sync 还是 async。

**P10.5 影响**: composition root 的关闭接口设计需要考虑这个问题，但不阻塞当前 public API 冻结。

### N2. submit_followup 默认 execution target 非公开

**严重度**: low
**证据**: `dayu/host/command.py:108` (`_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"`)、`dayu/host/README.md:57`

`submit_followup(queue)` 使用 Host facade 内部默认 `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET`，这不是 stable public contract。如果 P10.5 不明确，后续 policy provider 落地时可以合法修改默认值，改变 Service 行为。

**P10.5 影响**: 建议在 P10.5 明确"普通多轮 follow-up 沿用同一 execution target"的 contract，或明确"execution target resolution 由 P11+ 负责"。

### N3. HostEventView 不暴露 inline payload

**严重度**: low
**证据**: `dayu/host/read_api.py:204-221` (`_event_view_from_row` 只映射 `payload_ref` / `payload_digest`)、`dayu/host/api.py:1961-1996` (`HostEventView` 字段)

`stream_run_events()` 返回的 `HostEventView` 只有 `payload_ref` 和 `payload_digest`，没有 inline payload 内容。如果 B1 的 payload read facade 落地，这个问题自动解决；如果 B1 选择不同的方案（如 inline payload in event view），则 N3 的 contract 会随之变化。

**P10.5 影响**: 跟随 B1 的 decision。

### N4. dayu/host/README.md 语义与 P10 代码不一致

**严重度**: low
**证据**: `dayu/host/README.md:46` ("无 active Run 时 direct `RUNNING`") 对比 `dayu/host/admission.py` 中 P10 后 `ACCEPTED -> scheduler governance -> RUNNING` 语义

README 仍按旧语义描述 `start_run` 行为，但 P10 代码已改为先 `ACCEPTED` 再由 scheduler governance 创建 Attempt。`post-p10.md:132-135` 已记录两个相关测试失败。

**P10.5 影响**: P10.5 计划已包含"同步 public Run API 测试和 Host README"，此项属于 P10.5 已知范围。

---

## Gap 分析：哪些项如果不在 P10.5 明确，会导致 P11+ 仍能合法修改接口

| 项 | P10.5 不明确的后果 | 严重度 |
|---|---|---|
| final answer 读取 facade (B1) | P11+ 可以新增 `read_payload` / `read_terminal_answer` / `get_answer_content`，任意命名、任意返回类型、任意错误语义。Service 依赖的"读答案"接口不稳定。 | blocking |
| composition root (B2) | P11+ 可以新增 `HostRuntime` / `HostLocalRuntime` / `start_local_host`，任意命名、任意生命周期、任意关闭语义。Service 依赖的"打开 Host"入口不稳定。 | blocking |
| scheduler wakeup 接线 (B3) | P11+ 可以选择在 composition root 内部自动接线、或在 command handle options 新增 wakeup port、或在 command facade 新增 `attach_scheduler` 方法。Service 依赖的"提交后自动执行"行为不稳定。 | blocking |
| terminal 等待 pattern (B4) | P11+ 可以新增 `await_terminal` / `wait_for_run` / `poll_until_terminal`，或在 composition root 内置等待辅助，或明确轮询为 official pattern。Service 依赖的"等待结果"接口不稳定。 | blocking |
| execution target 默认值 (N2) | P11+ policy provider 落地时可以合法修改 follow-up 默认 execution target。 | non-blocking |

---

## Coverage Checklist

| 检查项 | 状态 | 说明 |
|---|---|---|
| `dayu.host.__all__` 是否包含 Service 完成多轮闭环所需的全部 public API | **gap** | 缺 payload read facade (B1)、composition root (B2)、terminal wait (B4) |
| `create_host_command_handle` 是否能启动本地执行 | **gap** | 显式拒绝 `local_execution`，需要 composition root (B2) |
| command facade 提交后是否自动唤醒 scheduler | **gap** | 默认 no-op wakeup (B3) |
| Service 能否通过 public API 读取 final answer 内容 | **gap** | 只有 ref/digest，无 read facade (B1) |
| Service 能否通过 public API 等待 Run 终态 | **gap** | 只有瞬时 snapshot 和 cursor 补读 (B4) |
| P10 后 ACCEPTED 语义是否在 README / 测试中统一 | **gap** | README 仍写旧语义 (N4)，post-p10.md 已记录 |
| `HostCommandHandle` 关闭语义是否稳定 | **ok** | 同步 `close()` 幂等，已在 `__all__` 导出 |
| `RunSnapshot` / `SessionSnapshot` 字段是否稳定 | **ok** | 字段已在 `__all__` 导出，语义在 README 有文档 |
| `HostApiErrorCode` 错误码集合是否稳定 | **ok** | 已在 `__all__` 导出，包含 `NOT_FOUND` / `INVALID_STATE` / `CONFLICT` / `IDEMPOTENCY_CONFLICT` / `PERMISSION_DENIED` / `UNSUPPORTED_OPERATION` / `INTERNAL_ERROR` |
| `HostToolingOptions` 工具输入边界是否稳定 | **ok** | 已在 `__all__` 导出，P10.5 可用 mock ToolBundle |
| `HostLocalExecutionOptions` 字段是否稳定 | **ok** | 已在 `__all__` 导出，但缺少 composition root 消费它 (B2) |
| `resolve_wait` public API 是否稳定 | **ok** | 已在 `__all__` 导出，outcome 类型已定义 |
| `cancel_run` / `cancel_session_runs` public API 是否稳定 | **ok** | 已在 `__all__` 导出 |

---

## 最终判定

**4 blocking / 4 non-blocking**。

P10.5 第一目标"冻结普通本地多轮会话的 Host public interface / contract"当前不成立。B1-B4 是 Service 完成最小多轮闭环的硬 blocker：Service 需要（1）打开 Host 并启动本地执行、（2）提交后自动执行、（3）等待执行完成、（4）读取回答内容。这四个环节的 public contract 均未冻结。

`post-p10.md` 的缺失清单（第 1、2、5 项）已经识别了 B2、B3、B1 对应的问题，但 P10.5 建议目标中没有明确要求冻结 B4（terminal 等待 pattern）的 public contract。建议在 P10.5 建议目标中补充 terminal 等待的 public contract 冻结要求。
