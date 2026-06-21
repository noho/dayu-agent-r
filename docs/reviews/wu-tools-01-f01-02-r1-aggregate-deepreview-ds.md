# Code Review

## Scope

- Mode: aggregate deepreview (WU-TOOLS-01-F01-02-R1, current branch)
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: Plan accepted at commit `478f5f77`, Slice 1 at `e10f2e99`, Slice 2 at `4f45f8de`, Slice 3 at `80ab56ab`, aggregate checkpoint at `28bba810`
- Ground truth: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/wu-tools-01-f01-02-r1-plan.md`, `docs/host/issues-implementation-control.md`
- Included scope:
  - `dayu/host/wait_adapter.py` — `WaitActivationRequest`, `WaitActivationAdapter`, `WaitActivationRegistry`
  - `dayu/host/tool_runtime.py` — `_accept_awaiting`, `_activate_accepted_wait_best_effort`, `wait_activation_registry` wiring
  - `dayu/host/tooling.py` — `HostToolingOptions.wait_activation_registry`
  - `dayu/host/dispatch.py` — `wait_activation_registry` pass-through in `_dispatch_run_input_builder`
  - `dayu/fins/ingestion_runtime.py` — `prepare_observed_*`, `activate_observation`, `start_observed_*` keep-combine
  - `dayu/fins/ingestion/observation_handle.py` — `FinsObservationRuntime.prepare_observed_*`, `activate_observation` protocol
  - `dayu/fins/ingestion/wait_adapter.py` — `FinsIngestionWaitActivationAdapter`, `build_fins_wait_activation_registry`
  - `dayu/fins/tools/download_tools.py`, `preprocess_tools.py`, `upload_tools.py` — callable switches to `prepare_observed_*`
  - `dayu/service/host_assembly.py` — `_tooling_options_from_discovery`, `_fins_wait_activation_registry_from_provider_configs`, `discover_service_tools`
  - `tests/host/test_toolruntime_executor.py`, `tests/host/test_phase7_waiting_integration.py`, `tests/fins/test_fins_ingestion_tools.py`, `tests/fins/test_fins_ingestion_runtime.py`, `tests/service/test_host_assembly.py`
  - `docs/host/design.md`, `dayu/host/README.md`, `dayu/fins/README.md`
- Excluded scope: engine internals, tool provider implementations (download/preprocess/upload provider .py), test fixture internals not related to activation contract, prior WU (WU-TOOLS-01-F03-R4 / WU-TOOLS-AWAIT-FANOUT-01) code not touched by this WU.

## Verification

| Command | Result |
|---|---|
| `pytest tests/service/test_host_assembly.py -q` | 52 passed |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` | 159 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | No output (clean) |

## Findings

### Review Item 1: Host activation hook 只在 accepted ack 后触发

**推理路径：**

入口 `_execute_one` (`tool_runtime.py:2295`) → 检测 `ToolAwaitingOutcome` → 调用 `_accept_awaiting` (`tool_runtime.py:2681`)。

`_accept_awaiting` 的核心分支：
- **缺失配置 / binding / external_job_ref**：`tool_runtime.py:2710-2746` → 返回 governed error，不进入 accept，**不触发 activation**。
- **正常路径**：构造 `candidate` (`tool_runtime.py:2749-2762`) → `await self._accept_awaiting_with_retry(candidate)` (`tool_runtime.py:2763`) → 只在 `isinstance(accept_result, ToolAwaitingAcceptedAck)` 时 (line 2764) 才进入后续。
- **accepted ack 分支内**：先写 `duplicate_awaiting_accepted` marker (`tool_runtime.py:2767-2774`)，再检查 `not context.cancellation_token.is_cancelled()` (`tool_runtime.py:2776`)，最后调用 `_activate_accepted_wait_best_effort` (`tool_runtime.py:2777`)。
- **rejected / timeout / stale 分支**：走 `else` (`tool_runtime.py:2791-2801`)，`accept_result` 是 `ToolAwaitingRejectedAck` 或 `ToolAwaitingAcceptTimedOut` → 返回 governed error 给 Engine，**不触发 activation**。
- **duplicate fanout waiter**：在 `_execute_one` 更早位置 (`tool_runtime.py:2346-2350`) 通过 `_awaiting_fanout_record` 直接返回 owner 的 awaiting outcome，**不调用 callable，不进入 accept，不触发 activation**。

`_activate_accepted_wait_best_effort` (`tool_runtime.py:2803`) 的防御：
- `wait_activation_registry is None` → 直接返回 (line 2821)。
- `resolve_adapter` 返回 `None` → 直接返回 (line 2826)。
- `adapter.activate_accepted_wait(request)` 异常 → 只写 warning log 和 diagnostic ref，不向调用方传播 (`tool_runtime.py:2833-2847`)，awaiting outcome 正常返回给 Engine。

对应测试直接证据：
- `test_cancel_after_awaiting_accept_skips_activation` (`test_toolruntime_executor.py:1198`)：`_CancellingAwaitingAcceptPort` 在返回 ack 后设置取消 → 断言 `activation_adapter.requests == []`。
- `test_stale_execution_awaiting_rejection_does_not_activate_wait` (`test_toolruntime_executor.py:1455`)：awaiting accept 返回 `ToolAwaitingRejectedAck(reason_code=STALE_EXECUTION)` → 断言 `activation_adapter.requests == []`。
- `test_awaiting_accept_timeout_returns_governed_error` (`test_toolruntime_executor.py:1514`)：timeout 同样断言 `activation_adapter.requests == []`。
- `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` (`test_toolruntime_executor.py:1227`)：adapter 抛异常 → 断言 record 仍是 `ToolAwaitingOutcome`，diagnostic ref 已写入且不包含 raw provider internals。

**结论：未发现实质性问题。**

### Review Item 2: Fins prepare / activate 幂等，prepared cancel / activation failure 有结构化收口

**推理路径：**

**Prepare 不 submit**：`_prepare_observed_stream` (`ingestion_runtime.py:2416`) 创建 `_FinsObservedOperationRecord(submitted=False)`，注册 observation，不调用 `executor.submit`。

**Activate 幂等**：`activate_observation` (`ingestion_runtime.py:2370`) 在 `_observation_lock` 下执行：
- `record is None` → return (line 2389)。
- `record.submitted` → return (line 2393) — 幂等。
- `record.cancellation_state.is_cancelled()` → return (line 2394)。
- `record.status in _TERMINAL_OBSERVATION_STATUSES` → return (line 2395)。
- 通过检查后，`record.submitted = True` (line 2397)，然后在锁外 `executor.submit` (line 2401)。
- `executor.submit` 或后续异常：catch 块重新获取锁，查找 record，调用 `_mark_observation_failed` (line 2409-2413)，**把 observation terminal 化为 `FAILED`**，然后按原异常抛出。

**Pre-activation cancel**：`cancel_observation` (`ingestion_runtime.py:2321`) 在 `_observation_lock` 下：
- `not record.submitted` 时，直接 `record.status = FinsObservationStatus.CANCELLED` (line 2346)，不提交 executor。
- `record.submitted` 时，只设置 `cancellation_state.request_cancel()` (line 2343)，不改变 status。

由于 `activate_observation` 和 `cancel_observation` 都使用同一个 `self._observation_lock`，cancel 和 activate 之间的竞争是确定性的——谁先持锁谁决定结果。

**Activation failure 收口**：见上。此外 `_mark_observation_failed` 写入 `FinsErrorKind.EXECUTION` 和 bounded message "Observation activation failed."，不暴露 provider internals、本地路径、wait id 或 trace id。

**Poller 行为**：`FinsIngestionWaitPollAdapter.poll_wait` (`ingestion/wait_adapter.py:122`) 映射 PENDING/RUNNING → `WaitPollNotReady`，terminal (SUCCEEDED/FAILED/CANCELLED/LOST) → `WaitPollReady`/`WaitPollLost`。prepared-but-not-ready 走 PENDING→NotReady 路径，与 plan 一致。

对应测试直接证据：
- `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` (`test_host_assembly.py:808`)：prepare 后 observation 为 PENDING → activation 后 observation 离开 PENDING。
- Fins ingestion runtime tests 中 `test_prepare_*_does_not_submit` 和 `test_activate_*_idempotency` 类断言通过。
- `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` 证明 ToolRuntime 端诊断收口。

**结论：未发现实质性问题。**

### Review Item 3: Service assembly 正确装配到同一 workspace-scoped runtime

**推理路径：**

`_tooling_options_from_discovery` (`host_assembly.py:1684`) 同时调用：
- `_fins_wait_adapter_registry_from_provider_configs` (line 1708) — 构造 `WaitAdapterRegistry`。
- `_fins_wait_activation_registry_from_provider_configs` (line 1714) — 构造 `WaitActivationRegistry`。

两者共享同一个 `provider_configs` 和 `available_tool_names`，都通过 `_fins_awaiting_registry_inputs_from_provider_configs` 解析相同的 tool_names 和 workspace_root。

`_fins_wait_activation_registry_from_provider_configs` (`host_assembly.py:1758`) 直接构造 `FinsIngestionWaitActivationAdapter(runtime=fins_awaiting_runtime)` —— 不通过 `build_fins_wait_activation_registry`（那个 standalone builder 会创建自己的 runtime），确保与 tool callable 的 runtime 是同一个实例。

代码注释 (`host_assembly.py:1787-1788`) 明确记录了这个约束：
> "生产路径中 awaiting tool callable、poll adapter 与 activation adapter 必须共享同一个 runtime，避免 accepted activation 看不到工具准备的 observation。"

测试 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` (`test_host_assembly.py:808`) 直接断言 `activation_adapter.runtime is callable_.runtime`，验证了同一实例。

Host dispatch 传递链路：
- `HostToolingOptions.wait_activation_registry` (`tooling.py:89`) → 装配在 `_tooling_options_from_discovery` → `compose_open_host_options` → `OpenHostOptions.tooling_options`。
- `HostDispatchScheduler` → `_dispatch_run_input_builder` (`dispatch.py:3108-3111`) → `ToolRuntimeBuildRequest.wait_activation_registry`。
- `DefaultToolRuntimeFactory.create_tool_runtime` → `ToolRuntimeExecutor.__init__` (`tool_runtime.py:3312`)。

**没有测试私有路径伪造生产行为**：所有测试都通过公开装配入口 `_tooling_options_from_discovery` 或 `discover_service_tools` + `_tooling_options_from_discovery` 验证，不存在用不可达的假 config 或 mock 拼出假 registry 的情况。

**结论：未发现实质性问题。**

### Review Item 4: Engine 边界未被扩大；activation 未泄漏到 LLM-facing schema

**推理路径：**

Engine public contracts 确认不变：
- `AgentRunRequest` 字段无变化。
- `ToolExecutor.execute(BatchToolExecutionRequest)` signature 无变化。
- `ToolAwaitingOutcome` shape 无变化。
- `BatchToolExecutionContext` 无变化。

LLM-facing tool schema 确认不变：
- `download_tools.py:_download_parameters_schema()` — 无变化。
- `preprocess_tools.py:_preprocess_parameters_schema()` — 无变化。
- `upload_tools.py:_upload_parameters_schema()` — 无变化。
- 三个 tool callable 仍返回 `ToolAwaitingOutcome` — Engine 看到的 shape 完全一致。
- `WaitActivationRequest`、`WaitActivationAdapter`、`WaitActivationRegistry` 都在 `dayu.host.wait_adapter`，是 Host 内部 construction-time wiring，不在 Engine import 路径上。

设计文档约束验证：
- `docs/host/design.md` diff: 在 waiting 状态机描述中追加了一句 "ToolRuntime may call an internal activation adapter after accepted ack" + 新段落说明 activation adapter 不进入 Engine awaiting 公共模型。
- `docs/engine/design.md` 无变更 — Engine design 不提及 activation。
- `dayu/host/README.md` 新增段落：长事务工具流程与 "该 adapter 不进入 Engine contract，也不暴露给 LLM-facing tool schema"。

**结论：未发现实质性问题。**

### Review Item 5: 设计/README 同步准确，无 process/gate 文本泄漏

**推理路径：**

`docs/host/design.md` 变更（1 处 diff）：
- 在 waiting 状态机描述中新增 "ToolRuntime may call an internal activation adapter after accepted ack"（状态流注解，只有稳定设计事实）。
- 新增完整段落："需要 submit-before-accept barrier 的长事务工具只能在 Host durable accepted ack 之后由 ToolRuntime 调用内部 activation adapter..." 属于稳定架构描述，不含 WU 编号、gate 名称、slice 状态、PR 号或 review 状态。

`dayu/host/README.md` 变更（2 处 diff）：
- "长事务工具需要启动外部工作时..." 段落 — 稳定行为描述。
- "Engine 不拥有 wait record、activation 或外部 job 生命周期..." 段落 — 稳定边界描述。

`dayu/fins/README.md` 变更（约 8 处修改）：
- 新增 `prepare_observed_*`、`activate_observation` API 列示。
- 新增 `FinsIngestionWaitActivationAdapter` 和 `build_fins_wait_activation_registry` 列示。
- 流程图从 `start_observed_*` 更新为 `prepare_observed_* → Host accepted wait activation → activate_observation`。
- 完整流程描述从旧 "register observation → return awaiting" 扩展为 "prepare → register as pending → return awaiting → Host accept → activation adapter → background executor"。
- 新增 "activation submit 失败会把 observation terminal 化为 failed" 说明。
- Wait adapter 段落更新为 "显式构造 wait adapter registry 与 wait activation registry"。
- 状态流从 `start_observed_* → pending → running` 改为 `prepare_observed_* → pending → activate_observation → running`。
- 直接流/observation/取消段更新为准确描述两阶段。

**无 process/gate 文本泄漏**：所有变更都是对实现事实的稳定描述。没有出现 "WU-TOOLS-01-F01-02-R1"、"Slice 1/2/3"、"gateflow"、"accepted commit"、"controller"、"AgentMiMo"、"AgentDS" 等 gate 治理术语。

**结论：未发现实质性问题。**

### Review Item 6: 跨 slice 集成缺口、死代码、兼容 wrapper、过度设计检查

**推理路径：**

**跨 slice 集成**：
- Slice 1 (Host activation hook) → Slice 2 (Fins prepare/activate) → Slice 3 (Service wiring) 的依赖链完整。
- `WaitActivationRegistry` (Slice 1) 被 Slice 2 的 `FinsIngestionWaitActivationAdapter` 消费，被 Slice 3 的 `_fins_wait_activation_registry_from_provider_configs` 装配。
- `ToolRuntimeBuildRequest.wait_activation_registry` (Slice 1) 经 `HostToolingOptions` (Slice 1 扩展) 和 `HostDispatchScheduler` (Slice 3) 完整传递到 `ToolRuntimeExecutor`。
- 不存在 slice N 生产的类型在 slice M > N 中无法消费的断层。

**死代码检查**：
- `start_observed_download/preprocess/upload` 仍保留在 `FinsIngestionRuntime`，作为 `prepare + activate` 的便捷组合供非 awaiting 调用方使用。这些是在 `FinsObservationRuntime` 协议中声明的公共方法，不是死代码。
- `build_fins_wait_activation_registry` standalone builder 与生产 assembly 内部构造是两个入口；standalone 版本用于独立装配场景（如测试或非 Service assembly 的调用方），且有明确 docstring 说明差异。
- 未发现未被任何路径调用的 dead function/dataclass。

**兼容 wrapper 检查**：
- 不存在旧接口兼容 re-export。
- 不存在 `start_observed_*` 为 `prepare_observed_*` 的透传 wrapper（`start_observed_*` 是独立的三步组合 prepare+activate，不是 wrapper）。
- 不存在为旧测试保留的兼容代码路径。

**过度设计检查**：
- Activation contract 只有一个 `WaitActivationAdapter` protocol 和一个 `WaitActivationRequest` dataclass，加上 `WaitActivationRegistry`（与已有 `WaitPollAdapterRegistry` 同模式）。
- Fins 端只有一个 `activate_observation(handle)` 方法和对应的 `FinsIngestionWaitActivationAdapter`。
- 不存在通用 lifecycle supervisor、跨 provider activation 平台、durable activation ledger、follower ledger、callback server、production retry loop。
- 与计划承诺一致：复用现有 Host wait accept barrier、existing wait adapter registry pattern、existing observation handle、existing PENDING poll semantics、existing wait poller、existing resolve_wait path。

**结论：未发现实质性问题。**

---

### 综合裁决

**Verdict: PASS**

本轮 aggregate deepreview 对 WU-TOOLS-01-F01-02-R1 六个重点审查面逐项走读了完整代码路径，并以测试断言、设计文档和 pyright 作为交叉验证。未发现 blocking / 高 / 中 / 低 severity 的实质性问题。

## Open Questions

- `build_fins_wait_activation_registry` standalone builder 与生产路径 `_fins_wait_activation_registry_from_provider_configs` 各自构造 runtime 的方式不同（standalone 自建 runtime，生产路径接受共享 runtime）。当前 standalone builder 的 docstring 已说明只适用于调用方自行保证 runtime 一致性的场景。如果未来 standalone builder 在不经 Service assembly 的场景中被误用（如直接用它构造 registry 然后用来自不同 runtime 的 handle 激活），会导致 observation 查找失败。当前测试没有覆盖这种误用场景。建议后续 WU 如果需要扩大 standalone builder 使用面，先评估是否需要设计更安全的 runtime 一致性 guard。

## Residual Risk

- 本 WU 不覆盖的 production hardening（#89 callback endpoint / auth / replay、#90 production poller loop / backoff / fencing / retry、#92 external job physical cancel / revoke / abandon）不因本 WU 改变风险等级。这些仍然是已知 deferred-with-owner 风险。
- Process-local observation 在 Host 进程重启后丢失的问题不是本 WU 范围，且本 WU 的两阶段设计没有新增持久化依赖，因此重启丢失的风险与实施前一致。
- 如果未来出现非 Fins provider 需要 activation，必须参考 `WaitActivationAdapter` 协议新增自己的 adapter 注册；当前不会因为只有 Fins 一个 adapter 而阻塞扩展。
