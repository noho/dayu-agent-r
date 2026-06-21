# Code Review

## Scope

- Mode: PR review
- PR: https://github.com/noho/dayu-agent-r/pull/162
- Title: WU-TOOLS-01-F01-02-R1 two-phase Fins activation
- Author: noho
- Head branch: `phase/wu-tools-01-f01-02-r1`
- Base branch: `main`
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-pr-review-ds.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`
- Plan: `docs/host/wu-tools-01-f01-02-r1-plan.md`
- Aggregate controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-controller-adjudication.md`

Included scope:

- `dayu/host/wait_adapter.py` — `WaitActivationRequest`, `WaitActivationAdapter`, `WaitActivationRegistry`
- `dayu/host/tool_runtime.py` — `_accept_awaiting`, `_activate_accepted_wait_best_effort`, `wait_activation_registry` wiring
- `dayu/host/tooling.py` — `HostToolingOptions.wait_activation_registry`
- `dayu/host/dispatch.py` — `wait_activation_registry` pass-through
- `dayu/fins/ingestion/observation_handle.py` — `FinsObservationRuntime` prepare/activate protocol
- `dayu/fins/ingestion_runtime.py` — `prepare_observed_*`, `activate_observation`, `_prepare_observed_stream`, `_mark_observation_failed`, `_observation_cancelled_result`
- `dayu/fins/ingestion/wait_adapter.py` — `FinsIngestionWaitActivationAdapter`, `build_fins_wait_activation_registry`
- `dayu/fins/tools/download_tools.py`, `preprocess_tools.py`, `upload_tools.py` — callable switches to `prepare_observed_*`
- `dayu/service/host_assembly.py` — `_FinsAwaitingProviderCallable`, `_DisabledProviderCallable`, `_tool_discovery_bindings`, `_shared_fins_awaiting_runtime_from_provider_configs`, `_fins_wait_activation_registry_from_provider_configs`, `_tooling_options_from_discovery`
- `tests/host/test_toolruntime_executor.py`, `tests/host/test_phase7_waiting_integration.py`, `tests/fins/test_fins_ingestion_tools.py`, `tests/fins/test_fins_ingestion_runtime.py`, `tests/service/test_host_assembly.py`
- `docs/host/design.md`, `dayu/host/README.md`, `dayu/fins/README.md`, `docs/host/issues-implementation-control.md`

Excluded scope: Engine public contracts, LLM-facing tool schema internals, tool provider `.py` files not directly related to activation, pre-existing code paths not touched by this WU.

## Verification

Independent reproduction of PR validation claims:

| 命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q` | 103 passed, 3 warnings |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` | 159 passed, 3 warnings |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check main...HEAD` | No output (clean) |

All warnings originate from upstream `edgar` library deprecation notices, unrelated to this WU.

## Findings

### 1. Host activation hook 只在 accepted ack 后触发

**推理路径：**

入口 `_execute_one` (`tool_runtime.py:2295`) → 检测 `ToolAwaitingOutcome` → 调用 `_accept_awaiting` (`tool_runtime.py:2681`)。

`_accept_awaiting` 的分支覆盖：

- **缺失 binding / external_job_ref**：`tool_runtime.py:2710-2747` → 返回 governed error，不进入 accept，**不触发 activation**。
- **rejected / timeout / stale execution**：`accept_result` 是 `ToolAwaitingRejectedAck` 或 `ToolAwaitingAcceptTimedOut`，走 `else` 分支 (`tool_runtime.py:2791-2801`)，返回 governed error 给 Engine，**不触发 activation**。
- **duplicate fanout waiter**：`tool_runtime.py:2346-2350` 通过 `_awaiting_fanout_record` 直接返回 owner 的 awaiting outcome，**不调用 callable，不进入 accept，不触发 activation**。
- **accepted ack 路径**：只在 `isinstance(accept_result, ToolAwaitingAcceptedAck)` 时 (`tool_runtime.py:2764`) 进入后续：先写 `duplicate_awaiting_accepted` marker → 检查 `not context.cancellation_token.is_cancelled()` (`tool_runtime.py:2776`) → 调用 `_activate_accepted_wait_best_effort` (`tool_runtime.py:2777`)。
- **post-accept cancellation**：`is_cancelled()` 为 `True` 时跳过 activation (`tool_runtime.py:2776`)，prepared observation 保持非启动状态，后续由 Fins adapter cancel/abandon 收口。

`_activate_accepted_wait_best_effort` 的防御：
- `wait_activation_registry is None` → 直接返回 (line 2821)。
- adapter key 未注册 → 直接返回 (line 2826)。
- adapter 异常 → 只写 warning log 和 diagnostic ref，不向调用方传播 (`tool_runtime.py:2833-2847`)，awaiting outcome 正常返回 Engine。

对应测试直接证据：
- `test_awaiting_outcome_triggers_activation` — accepted ack 后断言 activation adapter 收到请求。
- `test_cancel_after_awaiting_accept_skips_activation` (`test_toolruntime_executor.py:1198`) — 取消 token 已设置 → `activation_adapter.requests == []`。
- `test_stale_execution_awaiting_rejection_does_not_activate_wait` (`test_toolruntime_executor.py:1455`) — stale execution rejected → `activation_adapter.requests == []`。
- `test_awaiting_accept_timeout_returns_governed_error` — timeout → `activation_adapter.requests == []`。
- `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` (`test_toolruntime_executor.py:1227`) — adapter 抛异常 → record 仍是 `ToolAwaitingOutcome`，diagnostic ref 已写入且不含 raw provider internals。

**结论：未发现实质性问题。**

### 2. Fins prepare / activate 幂等，prepared cancel / activation failure 有结构化收口

**推理路径：**

**Prepare 不 submit**：`_prepare_observed_stream` (`ingestion_runtime.py:2416`) 创建 `_FinsObservedOperationRecord(submitted=False)`，注册 observation 到 `self._observations`，**不调用 `executor.submit`**。与旧 `_start_observed_stream` 相比，移除了 `try: self.executor.submit(...) except: self._observations.pop(...)` 块。

**Activate 幂等**：`activate_observation` (`ingestion_runtime.py:2370`) 在 `self._observation_lock` 下执行完整检查链：
- `record is None` → return (line 2389) — handle 不存在时无操作。
- `record.submitted` → return (line 2393) — 已提交，幂等吸收。
- `record.cancellation_state.is_cancelled()` → return (line 2394) — 已取消，不提交。
- `record.status in _TERMINAL_OBSERVATION_STATUSES` → return (line 2395) — 已终态，不提交。
- 通过全部检查后 `record.submitted = True` (line 2398)，锁外 `executor.submit` (line 2401)。

**Activation 失败收口**：`try/except` 包裹整个 activation 体。任何异常（包括 `executor.submit` 失败、lock 外异常）都会被 catch 块捕获 (`ingestion_runtime.py:2405-2414`)：重新获取 `_observation_lock`，查找 record，调用 `_mark_observation_failed` 写入 `FinsObservationStatus.FAILED`、`FinsErrorKind.EXECUTION` 和 bounded message `"Observation activation failed."`，不暴露 provider internals、本地路径、wait id 或 trace id。然后按原异常 raise，让 ToolRuntime 的 safety net catch 写 diagnostic。

**Pre-activation cancel**：`cancel_observation` (`ingestion_runtime.py:2321`) 在 `_observation_lock` 下：
- `not record.submitted` 时，直接写入 `status=CANCELLED` 并构造 `_observation_cancelled_result` (line 2346-2348)，不提交 executor。
- `record.submitted` 时，只设置 `cancellation_state.request_cancel()` (line 2343)，不改变 status。

**Lock 一致性**：`activate_observation` 和 `cancel_observation` 都使用 `self._observation_lock`，cancel-vs-activate 竞争由锁的获取顺序决定——先持锁者决定结果，不是时序依赖。

**Poller 行为**：`FinsIngestionWaitPollAdapter.poll_wait` (`ingestion/wait_adapter.py:122`) 映射 `PENDING/RUNNING → WaitPollNotReady`，terminal (`SUCCEEDED/FAILED/CANCELLED/LOST`) → `WaitPollReady`/`WaitPollLost`。prepared-but-not-active 走 PENDING→NotReady 路径，与 plan 一致。

**结论：未发现实质性问题。**

### 3. Service assembly 共享 runtime 一致性

**推理路径：**

`discover_service_tools` (`host_assembly.py:460`) 调用 `_shared_fins_awaiting_runtime_from_provider_configs` 创建单一 `FinsIngestionRuntime`，然后通过 `_tool_discovery_bindings` 将该 runtime 传递给每个 Fins awaiting provider 的 `_FinsAwaitingProviderCallable`。

`_tooling_options_from_discovery` (`host_assembly.py:1684`) 同时构造：
- `_fins_wait_adapter_registry_from_provider_configs` → 返回 `WaitAdapterRegistry`（元数据 binding）。
- `_fins_wait_activation_registry_from_provider_configs` → 返回 `WaitActivationRegistry`，直接使用 `fins_awaiting_runtime` 参数构造 `FinsIngestionWaitActivationAdapter(runtime=fins_awaiting_runtime)`。

两个 registry 通过 `_fins_awaiting_registry_inputs_from_provider_configs` 共享相同的 tool_names 解析逻辑，但 activation registry 额外接收共享 runtime 实例。

测试 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` (`test_host_assembly.py:808`) 直接断言 `activation_adapter.runtime is callable_.runtime`，验证同一实例。

Host dispatch 传递链路完整：
- `HostToolingOptions.wait_activation_registry` → `HostDispatchScheduler._run_input_builder_for_dispatch` → `ToolRuntimeBuildRequest.wait_activation_registry` → `DefaultToolRuntimeFactory.create_tool_runtime` → `ToolRuntimeExecutor.__init__`。

**结论：未发现实质性问题。**

### 4. Engine 边界未被扩大，LLM-facing schema 未被修改

**推理路径：**

- `AgentRunRequest` 字段无变化。
- `ToolExecutor.execute(BatchToolExecutionRequest)` signature 无变化。
- `ToolAwaitingOutcome` shape 无变化。
- `BatchToolExecutionContext` 无变化。
- `download_tools.py`, `preprocess_tools.py`, `upload_tools.py` 的 `_*_parameters_schema()` 函数无变化。
- 三个工具 callable 仍返回 `ToolAwaitingOutcome` —— Engine 看到的 shape 完全一致。
- `WaitActivationRequest`, `WaitActivationAdapter`, `WaitActivationRegistry` 都在 `dayu.host.wait_adapter`，是 Host 内部 construction-time wiring，不在 Engine import 路径上。
- `docs/engine/design.md` 无变更。

**结论：未发现实质性问题。**

### 5. 设计/README 同步准确，无 process/gate 文本泄漏

**推理路径：**

- `docs/host/design.md` 变更限于 waiting 状态机描述中新增一句 "ToolRuntime may call an internal activation adapter after accepted ack" 和一个新段落说明 "需要 submit-before-accept barrier 的长事务工具只能在 Host durable accepted ack 之后由 ToolRuntime 调用内部 activation adapter"。均为稳定架构描述。
- `dayu/host/README.md` 新增两个段落：ToolRuntime activation hook 位置和 Engine non-ownership。均为稳定行为/边界描述。
- `dayu/fins/README.md` 新增 prepare/activate API、状态流更新、wait adapter 说明更新。均为对实现事实的准确描述。
- `docs/host/issues-implementation-control.md` 正常更新：WU 状态从 aggregate-deepreview 推进到 review gate，WU-TOOLS-AWAIT-FANOUT-01 标记为 completed。
- 静态搜索确认：`docs/host/design.md`、`dayu/host/README.md`、`dayu/fins/README.md` 中不含 WU 编号、gate 名称、slice 编号、Agent 名称或 gate 治理术语。

**结论：未发现实质性问题。**

### 6. 无死代码、兼容 wrapper 或过度设计

**推理路径：**

- `start_observed_download/preprocess/upload` 保留为 `prepare + activate` 的便捷组合，用于非 awaiting 调用方（如 direct stream 路径）。这些是 `FinsObservationRuntime` 协议声明的公共方法，不是死代码。
- 不存在旧接口兼容 re-export 或透传 wrapper。
- `FinsIngestionWaitActivationAdapter.from_workspace_root` 已在 AGG-F01 fix 中删除。仅 `FinsIngestionWaitPollAdapter.from_workspace_root`（poll adapter 的预存方法）保留。
- `_DisabledProviderCallable` 是 `ToolsDiscoveryProviderBinding` 的类型安全 sentinel，`discover_from_bindings` 在调用前跳过 disabled spec（`runtime/tools_discovery.py:234`），哨兵不会被实际调用。
- 新增类型控制在最小范围：一个 `WaitActivationAdapter` Protocol + 一个 `WaitActivationRequest` dataclass + 一个 `WaitActivationRegistry`（与已有 `WaitPollAdapterRegistry` 同模式）。无 lifecycle supervisor、durable activation ledger、callback server 或跨 provider 平台。

**结论：未发现实质性问题。**

### 7. PR 级别检查

**推理路径：**

- PR body 使用 `Refs #129.`，不包含 `closes`、`fixes`、`resolves` 等自动 close issue 关键词——确认不会自动关闭 GitHub Issue #129。
- 早产 final closeout artifact `docs/reviews/wu-tools-01-f01-02-r1-final-closeout.md` 存在，但 control doc (`issues-implementation-control.md:1653`) 已正确标记为 premature："Premature final closeout artifact ... 已存在但不得视为 final-closeout-pass 依据；create draft PR 后 Gate Order 仍需 PR review"。当前 gate 已纠正为 `review`，与实际情况一致。
- PR 包含 12 个 commit，对应完整 Gateflow 历史：plan → slice 1/2/3 implementation/review/fix → aggregate deepreview → draft PR。PR diff 覆盖完整实现，不遗漏 slice。
- issue status comments 已从 #111 切换到 #129 作为 active work unit，WU-TOOLS-AWAIT-FANOUT-01 状态更新为 `completed`。

**结论：未发现实质性问题。**

---

### 综合裁决

**Verdict: PASS**

对 WU-TOOLS-01-F01-02-R1 的完整 PR diff 按六个审查重点逐项走读了完整代码路径，并以测试断言、设计文档和 pyright 作为交叉验证。未发现 blocking、高、中、低 severity 的实质性问题。

实现完整覆盖 Plan §7 全部 implementation decisions：
- Host activation hook 只在 accepted ack 后触发，且 cancel-first、rejected、timeout、stale、fanout waiter、missing adapter 路径均不触发。
- Fins prepare 不 submit executor；activate 在 observation lock 下幂等检查 submitted/cancelled/terminal 后再 submit；activation 失败写入 terminal FAILED 且 message bounded。
- cancel 和 activate 共享 `self._observation_lock`，cancel-vs-activate 竞争由锁顺序决定。
- Service assembly 确保 tool callable、poll adapter、activation adapter 共享同一 `FinsIngestionRuntime` 实例。
- Engine public contract、LLM-facing tool schema 未变。
- 设计/README 同步准确，无 process/gate 文本泄漏。

## Open Questions

无。

## Residual Risk

- Production poller loop、poll adapter instance scheduling、retry/backoff/fencing、process-restart behavior 仍归属于 GitHub Issue #90。
- Callback endpoint / auth / replay 仍归属于 GitHub Issue #89。
- External job physical cancel / revoke / abandon 仍归属于 GitHub Issue #92。
- Process-local observation 在 Host 进程重启后丢失的风险与本 WU 实施前一致——两阶段设计未新增持久化依赖。
- 如果未来非 Fins provider 需要 activation，必须参考 `WaitActivationAdapter` 协议新增自己的 adapter 注册；当前不会因为只有 Fins 一个 adapter 而阻塞扩展。
- 早产 final closeout artifact `docs/reviews/wu-tools-01-f01-02-r1-final-closeout.md` 仍在磁盘上，但 control doc 已正确标记为 premature。PR review gate 通过后的下一步是 draft-PR-pass gate，不应直接进入 final closeout gate。
