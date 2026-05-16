# P1-P7 Design Conformance Fix Review — AgentDS Targeted Re-review

日期：2026-05-16
Branch: `fix/host-p1-p7-awaiting-production-wiring`
Review scope：C-P1P7-001 修复定向复审
Design truth: `docs/host/design.md`
Controller adjudication: `docs/reviews/p1-p7-design-conformance-controller-adjudication-20260516.md`
Fix artifact: `docs/reviews/p1-p7-design-conformance-fix-awaiting-production-wiring-20260516.md`

## Verdict: PASS

C-P1P7-001 已修复。`HostDispatchScheduler` production path 现在正确接入 Host awaiting accept port 与 wait_adapter_registry，使生产本地 dispatch 的 `ToolAwaitingOutcome` 可进入 `WAITING` / `SUSPENDED` / active wait record，并通过 `resolve_wait` resume。未引入新 blocking finding。

---

## Findings

### Blocking: 无

### High: 无

### Medium: 无

### Low

#### L-P1P7-001 — 新集成测试的生产 ToolRuntime 执行路径完整，但未经过 Engine agent loop 闭环

- 文件：`tests/host/test_phase7_waiting_integration.py:351-434`
- 严重性：Low
- 证据：

  新测试 `test_scheduler_awaiting_tool_enters_waiting_and_manual_resume_resumes` 覆盖链路：
  1. `ensure_session` / `start_run` (public facade)
  2. `HostDispatchScheduler.open()` + `wake_dispatch` + `drain_once` (production scheduler)
  3. `_CapturingWorker.accept()` 捕获 `AgentRunRequest`（含 production ToolRuntime executor）
  4. 测试直接调用 `request.tool_executor.execute(...)` 触发 awaiting accept path
  5. 断言 `RunStatus.WAITING` / `AttemptStatus.SUSPENDED` / `WaitRecordStatus.WAITING` / `external_job_ref`
  6. `resolve_wait` → `RunStatus.RUNNING` / 新 `current_attempt_id` / resume dispatch record

  `tool_executor` 是 scheduler 通过 `create_tool_enabled_run_input_builder` 注入的 production `ToolRuntimeExecutor`，其 `_awaiting_accept_port` 和 `_wait_adapter_registry` 均来自 scheduler 的 `_run_input_builder_for_dispatch` 构造路径（dispatch.py:734-738）。测试未走 Engine agent loop 调用 `tool_executor.execute()`，而是测试直接调用。这属于 Host wiring 测试的合理模式（Engine 行为由 Engine 测试覆盖），但仍与"Engine 发出 tool call → ToolRuntime 执行 → awaiting"的完整运行时闭环有差异。

- 影响：测试不排除未来 Engine 侧 `tool_executor` 传播路径变更导致的回归，但不影响当前 Host 生产 wiring 正确性判断。
- 建议：后续 phase 可补 Engine → ToolRuntime → awaiting 的端到端集成测试；当前测试对 C-P1P7-001 修复的验证充分。

#### L-P1P7-002 — 新测试在 scheduler close 时原始 SUSPENDED Attempt 的 `_consume_worker_events` 清理路径依赖 clean EOF closeout 的已有容错

- 文件：`tests/host/test_phase7_waiting_integration.py:351-434`；`dayu/host/dispatch.py:916-1019`
- 严重性：Low
- 证据：

  测试在 `resolve_wait` 之后才 `await scheduler.close()`。此时原始 Attempt 已 `SUSPENDED`，Run 已恢复为 `RUNNING`（新 Attempt）。scheduler close 触发 `_consume_worker_events` 的 finally 路径，`_HoldingWorkerHandle` close 后 `events()` 抛出 `StopAsyncIteration`，`close_clean_eof` 会在非 `RUNNING` / 非 `STARTING` Attempt 上执行。`EngineEventIngestor.close_clean_eof` 的已有实现对非可关闭状态应有容错处理（写 diagnostic 或 skip）。

- 影响：取决于 `close_clean_eof` 对 `SUSPENDED` Attempt 的实际容错行为。当前 392 测试全通过，表明已有实现正确处理此边界。风险来自未来 `close_clean_eof` 收紧状态前置条件时测试可能误报。
- 建议：可在测试 finally 中显式先 close worker handle 再 close scheduler，或直接依赖 expected-pass 验证；当前非阻塞。

### Info

#### I-P1P7-001 — `TYPE_CHECKING` import 边界正确，无 import cycle

- 文件：`dayu/host/tooling.py:23-24`
- 证据：

  `tooling.py` 对 `WaitAdapterRegistry` 使用 `TYPE_CHECKING` 守卫导入。运行时导入链为：
  `dispatch.py` → `waiting.py` → `wait_adapter.py` → `api.py` → `tooling.py`
  `tooling.py` 的 TYPE_CHECKING 块在运行时被跳过 → 无循环。

  `wait_adapter.py` 只依赖 `dayu.host.api`、`dayu.host.durable.codec`、`dayu.host.durable.state`、`dayu.host.durable.transaction`，均不反向依赖 `tooling.py`。

  `wait_adapter_registry: WaitAdapterRegistry | None` 字段使用 `TYPE_CHECKING` 时的 forward reference 语义，pyright 0 errors 确认类型解析正确。

#### I-P1P7-002 — production dispatch wiring 接入点正确

- 文件：`dayu/host/dispatch.py:731-738`
- 证据：

  `_run_input_builder_for_dispatch` 在 tool-enabled 分支中新增两行注入：
  - `awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(transaction_runner=..., event_log_store=...)` (line 734-737)
  - `wait_adapter_registry=tooling_options.wait_adapter_registry` (line 738)

  `DefaultHostToolAwaitingAcceptPort` 使用与 `DefaultHostToolFactAcceptPort` 相同的 `transaction_runner` 和 `event_log_store`，共享同一 durable transaction 边界。

  当 `tooling_options.wait_adapter_registry` 为 `None`（默认值）时，`ToolRuntimeExecutor._accept_awaiting` 中的 `self._wait_adapter_registry is None` 检查（tool_runtime.py:2451）命中，返回 `_awaiting_configuration_failure()`，保持向后兼容。

#### I-P1P7-003 — `wait_adapter_registry` 字段层级正确

- 文件：`dayu/host/tooling.py:131-140`
- 证据：

  `wait_adapter_registry` 位于 `HostToolingOptions`（Host construction / composition root 输入），与 `business_tool_bundle`、`source_refs`、`framework_tool_policy` 同层。不进入 `StartRunRequest`、`SubmitFollowupRequest`、per-run request 或 durable wait record。adapter 对象只存在于 composition/runtime 层，符合 design.md §20 wait record 约束（"wait record 只保存 adapter key / policy ref / external job refs，不保存进程内 adapter 对象"）。

#### I-P1P7-004 — 无 scope creep

- 本轮 diff 未引入以下 design.md 未定义或明确标记为 non-goal 的能力：
  - callback HTTP endpoint / 认证 / 重放防护
  - poller 后台调度循环
  - recovery scan
  - remote worker / remote wait resume
  - external job physical cancel / revoke
  - durable duplicate ledger / durable tool trace projection
  - steer / `RunStartReason.steer` / `RunStartReason.recovery`
  - 新 EventLog event type
  - 新 durable table

#### I-P1P7-005 — 文档更新准确

- `dayu/host/README.md:107`：新增一句描述 scheduler tool-enabled wiring 中 `wait_adapter_registry` 的作用，准确反映当前实现。
- `docs/host/implementation-control.md:403-413`：新增 fix gate 记录，正确标注 scope（"不实现 callback endpoint、poller 后台循环、recovery scan、remote worker 或 external job physical cancel"），不把 future phase 写成已完成。
- `tests/README.md:106`：在 durable foundation 测试覆盖列表中加入"真实 scheduler awaiting production wiring"，与新增测试对应。

#### I-P1P7-006 — 新增 `HostToolingOptions` docstring 完整

- 文件：`dayu/host/tooling.py:131-132`
- `wait_adapter_registry` 参数的 docstring 明确标注 "仅用于本地 ToolRuntime awaiting production wiring，不进入 durable row 或 per-run request"，符合项目编码规范。

---

## Residual Risks

1. **Engine agent loop 未闭环**：新集成测试直接调用 production `tool_executor.execute()`，未经过 Engine `run_agent_messages` → tool call → ToolRuntime → awaiting 的完整闭环。这不影响 Host wiring 正确性，但 Engine 集成层面的 awaiting 端到端行为仍无覆盖。

2. **`_consume_worker_events` + `SUSPENDED` Attempt 清理**：scheduler close 时原始 `SUSPENDED` Attempt 的 `close_clean_eof` 路径依赖 `EngineEventIngestor` 的已有容错。当前 392 测试通过，但此路径未成为显式测试目标。

3. **`wait_adapter_registry` 为 None 时的配置失败**：当 `HostToolingOptions.wait_adapter_registry` 为 None 时，ToolRuntime 返回 `_awaiting_configuration_failure()`。该路径在已有 `test_toolruntime_executor.py` 中覆盖（awaiting missing adapter），但在 production scheduler 路径下无独立测试。

4. **Poller retry 幂等 digest、in-flight fencing、Engine accepted refs 强校验、manual audit projection**：沿用 Phase 7 accepted residual owners，不在本轮 fix 范围。

---

## C-P1P7-001 关闭建议

**可关闭。** `HostDispatchScheduler._run_input_builder_for_dispatch` 在 tool-enabled production path 中已注入 `DefaultHostToolAwaitingAcceptPort` 与 `wait_adapter_registry`。新 scheduler-level integration test 验证了 public start → scheduler drain → production ToolRuntime executor → `ToolAwaitingOutcome` → `WAITING` / `SUSPENDED` → `resolve_wait` resume 的关键链路。adapter object 不进入 durable row 或 per-run request，符合 design.md 架构约束。无新 blocking finding。
