# P1-P7 Design Conformance Fix Review — AgentMiMo

日期：2026-05-16
分支：`fix/host-p1-p7-awaiting-production-wiring`
Base：`main` merge commit `c39de2e`
Fix target：C-P1P7-001，P7 awaiting production wiring 未接入 `HostDispatchScheduler`
Controller adjudication：`docs/reviews/p1-p7-design-conformance-controller-adjudication-20260516.md`
Codex fix 说明：`docs/reviews/p1-p7-design-conformance-fix-awaiting-production-wiring-20260516.md`

## Verdict

**PASS**

C-P1P7-001 已正确修复。生产 `HostDispatchScheduler` 的 tool-enabled 构造路径已接入 `DefaultHostToolAwaitingAcceptPort` 与 `WaitAdapterRegistry`，使 production local dispatch 的 `ToolAwaitingOutcome` 能进入 `WAITING` / `SUSPENDED` / active wait，并支持 `resolve_wait` resume。无 blocking finding。

## 审查范围

本轮 diff 变更文件：
- `dayu/host/tooling.py`：`HostToolingOptions` 新增 `wait_adapter_registry` 字段
- `dayu/host/dispatch.py`：`_run_input_builder_for_dispatch` 注入 awaiting accept port 与 registry
- `tests/host/test_phase7_waiting_integration.py`：新增 scheduler-level integration test
- `dayu/host/README.md`、`tests/README.md`、`docs/host/implementation-control.md`：文档同步

## 逐项检查结果

### 1. Host 强约束架构合规

**PASS。**

- `WaitAdapterRegistry`（`dayu/host/wait_adapter.py`）与 `DefaultHostToolAwaitingAcceptPort`（`dayu/host/waiting.py`）均为 Host 层内对象，不涉及 `dayu.runtime` 或 `dayu.engine`。
- `ToolRuntimeBuildRequest`（`dayu/host/tool_runtime.py`）是 Host 内部 typed boundary，不进入 `dayu.host.api`，不进入 per-run request，不进入 durable row。
- `wait_adapter_registry` 只存在于 composition/runtime 层，不进入 durable wait record。Fix 说明与实现一致。
- 未发现治理状态或 Engine 协议泄漏到 `dayu.runtime` 或 Engine。

### 2. `tooling.py` 新增 `wait_adapter_registry` 风险

**PASS。**

- `WaitAdapterRegistry` 通过 `TYPE_CHECKING` guard 导入（`tooling.py:23-24`），运行时无 import cycle。
- 依赖链分析：`tooling.py` 运行时只依赖 `dayu.contracts` + `dayu.host._public_validation`。`wait_adapter.py` 运行时依赖 `dayu.host.api` + `dayu.host.durable.*`。`api.py` 运行时导入 `tooling`。若 `tooling` 运行时导入 `wait_adapter`，则 `tooling -> wait_adapter -> api -> tooling` 形成循环。`TYPE_CHECKING` guard 正确阻断此路径。
- pyright 通过（0 errors），运行时 import 验证通过。
- 字段默认 `None`，向后兼容：未配置时 `ToolRuntime` 走已有受治理 awaiting configuration failure 路径。

### 3. 生产 scheduler 构造路径接线

**PASS。**

- `dispatch.py:734-738`：`_run_input_builder_for_dispatch` 在 tool-enabled production path 注入：
  - `awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(transaction_runner=..., event_log_store=...)`
  - `wait_adapter_registry=tooling_options.wait_adapter_registry`
- 这是 `HostDispatchScheduler` 的**唯一** tool-enabled `ToolRuntime` 构造路径（`dispatch.py:689-746`），不只修了 direct test 路径。
- 未配置 `tooling_options` 或 `allow_tool_calls=False` 时仍走 no-tool builder（`dispatch.py:699-707`），行为不变。
- `wait_adapter_registry=None` 时，`ToolRuntimeBuildRequest.wait_adapter_registry=None`，`ToolRuntime` 走受治理错误路径，与 controller adjudication 要求的 graceful degradation 一致。

### 4. Integration test 覆盖验证

**PASS。**

新测试 `test_scheduler_awaiting_tool_enters_waiting_and_manual_resolve_resumes`（`test_phase7_waiting_integration.py:351-434`）覆盖链路：

```text
public ensure_session
  -> public start_run (admission -> RUNNING -> pending dispatch)
  -> _pending_dispatch_from_started_run (durable dispatch record)
  -> scheduler.wake_dispatch(pending)
  -> scheduler.drain_once() (lane acquire -> durable recheck -> dispatching -> worker accept)
  -> factory.accepted_requests[0] (production ToolRuntime wiring)
  -> request.tool_executor.execute(awaiting_tool_request) (ToolAwaitingOutcome)
  -> assert Run=WAITING, Attempt=SUSPENDED, wait=WAITING
  -> resolve_wait(manual)
  -> assert Run=RUNNING, new Attempt dispatched, resume dispatch record
```

关键断言：
- `tool.call_count == 1`：业务工具确实被调用
- `run_before_resolve.status is RunStatus.WAITING`：Run 进入 WAITING
- `attempt_before_resolve is AttemptStatus.SUSPENDED`：Attempt 进入 SUSPENDED
- `wait.status is WaitRecordStatus.WAITING`：active wait record 已创建
- `wait.external_job_ref.external_job_id == _RESUME_TOKEN`：external job ref 正确
- `resolved.status is RunStatus.RUNNING`：resolve_wait resume 成功
- `resolved.current_attempt_id != pending.attempt_id`：新 Attempt 已创建
- `resume_dispatch.worker_kind is WorkerKind.LOCAL`：resume dispatch 正确

**无伪覆盖。** 测试只 mock 了 `_CapturingWorkerFactory`（fake worker），这是可接受的测试隔离——scheduler 本身走的是 production `HostDispatchScheduler.open` + `_run_input_builder_for_dispatch` + `DefaultToolRuntimeFactory` 路径。awaiting 工具通过 `ToolRuntime.tool_executor.execute` 调用，不绕过 ToolRuntime accept barrier。

### 5. Scope creep 检查

**PASS。**

- 未引入 callback endpoint、poller 后台循环、recovery scan、remote worker、external job physical cancel / revoke。
- 未引入 design.md 未定义的新设计概念。
- 变更最小化：2 个生产文件 + 1 个测试文件 + 3 个文档文件。

### 6. 文档与 implementation-control 准确性

**PASS。**

- `dayu/host/README.md`：准确描述 `HostToolingOptions.wait_adapter_registry` 启用 awaiting production path 的事实，不把未来 phase 写成已完成。
- `tests/README.md`：准确记录真实 scheduler awaiting production wiring 测试覆盖。
- `docs/host/implementation-control.md:403-410`：准确记录 fix gate 状态、修复方向与 non-goals。

### 7. 验证命令

已独立运行验证：

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_phase7_waiting_integration.py -v` | 3 passed |
| `pytest tests/host -q` | 392 passed |
| `python -m pyright dayu/host/tooling.py dayu/host/dispatch.py` | 0 errors |
| `python -m pyright dayu/ tests/ utils/` | 0 errors |
| import cycle 验证 | 通过 |

## Findings

### Low

#### L1 — `wait_adapter_registry` 语义边界 docstring 可补充 transaction 外引用约束

- 文件：`dayu/host/tooling.py:131-132`
- 现有 docstring："仅用于本地 ToolRuntime awaiting production wiring，不进入 durable row 或 per-run request。"
- 建议：可补充 "adapter 调用发生在 Host transaction 外" 的约束说明，与 `wait_adapter.py` 模块 docstring 中的 poller 设计一致。当前不影响正确性，因为 `WaitAdapterRegistry` 的调用方（ToolRuntime）已遵循该约束。
- 影响：无功能影响，仅文档完整性。

### Info

#### I1 — 已有 direct ToolRuntime 测试保留合理

- 文件：`tests/host/test_phase7_waiting_integration.py:275-347`
- `test_local_awaiting_tool_manual_resolve_resumes_run` 直接构造 `ToolRuntimeBuildRequest`，绕过 scheduler。该测试在 fix 前已存在，保留为 lower-level 路径覆盖是合理的——它验证 `ToolRuntime` + `DefaultHostToolFactAcceptPort` + `DefaultHostToolAwaitingAcceptPort` 的单元级行为，不与新 scheduler test 重复。

#### I2 — `_HoldingWorkerHandle.events()` 的 `if False: yield` 模式

- 文件：`tests/host/test_phase7_waiting_integration.py:195-196`
- 这是让 async generator 保持打开直到 `_closed` event 的惯用 Python 模式，语义正确。不是伪覆盖。

## Residual Risks

1. **本 fix 不实现 callback endpoint、poller 后台循环、recovery scan、remote worker、external job physical cancel / revoke。** 这些是后续 phase 的职责。
2. **`create_host_command_handle(..., local_execution=...)` 仍不消费 `local_execution`。** scheduler lifecycle wiring 仍需后续 composition gate 处理。这不影响 C-P1P7-001 的修复完整性。
3. **Poller retry 幂等 digest、in-flight fencing、Engine accepted refs 强校验、manual audit projection** 仍沿用 Phase 7 accepted residual owners。
4. **`WaitAdapterRegistry` 的多进程安全边界**：当前 `HostToolingOptions` 是 construction-scope 输入，不跨进程传递。多进程场景下每个 Host 进程自行构造 registry，不共享状态。这是当前设计的正确行为。

## C-P1P7-001 关闭建议

**建议关闭 C-P1P7-001。** 修复已满足 controller adjudication 的全部 required fix direction：

- [x] Host local execution composition 引入明确的 wait adapter registry wiring
- [x] `HostDispatchScheduler._run_input_builder_for_dispatch` 构造 `ToolRuntimeBuildRequest` 时注入 `DefaultHostToolAwaitingAcceptPort` 与 `WaitAdapterRegistry`
- [x] 真实 scheduler-level integration test 覆盖 public start -> scheduler drain -> production ToolRuntime executor -> ToolAwaitingOutcome -> WAITING / SUSPENDED -> resolve_wait resume
- [x] 更新 README / 总控状态
