# Host P1-P7 设计一致性深度 Review（Codex）

- 日期：2026-05-16
- 基线：`main`，`HEAD=c39de2e`
- 设计真源：`docs/host/design.md`
- 总控参考：`docs/host/implementation-control.md`
- 审查性质：已合并代码相对设计真源的专项一致性 review，不是 PR diff review
- 修改范围：仅创建本 artifact，未修改生产代码
- 并行审查：未使用子代理；本次用户要求独立 reviewer，且未授权 sub-agent

## 结论

**FAIL。**

P1-P7 的 Host durable foundation、public contracts、cancel、resolve_wait、EngineEvent confirmation、runtime/import boundary 大体保持在设计边界内；但发现 1 个 blocking 级设计偏离：**P7 awaiting accept path 没有接入真实本地 dispatch scheduler 的生产 ToolRuntime 构造路径**。这会导致 P7 直接 ToolRuntime 集成测试可通过，但经 `HostDispatchScheduler` 运行的本地工具无法把 `ToolAwaitingOutcome` 持久化为 `WAITING` Run。

## P1-P7 Repository Map

### 公共契约与包边界

- `dayu/host/api.py`：Host public dataclass / enum / error / snapshot / wait outcome envelope / local execution options。
- `dayu/host/__init__.py`：公开导出白名单；`tests/host/test_package_exports.py` 锁定包根和 `api` 导出。
- `dayu/host/tooling.py`：Host construction 期 business tool bundle 输入，不进入 per-run request。
- `tests/host/test_import_boundary.py`：守卫 Host 不依赖 Config / Fins / Service / UI，Engine 不依赖 Host，Host 仅在允许模块依赖 Engine。
- `tests/runtime/test_import_boundary.py`：守卫 `dayu.runtime` 不依赖业务层。

### Durable truth 与状态机

- `dayu/host/durable/schema.py`、`state.py`、`run_transition.py`：Session / Run / Attempt / Dispatch / EventLog / WaitRecord 的 schema、row codec、CAS、状态迁移。
- `dayu/host/durable/event_log.py`、`idempotency.py`、`payload_descriptor.py`：EventLog、幂等、payload descriptor primitives。
- `dayu/host/admission.py`：start / followup / cancel / queued promotion / dispatch wake result。

### 真实入口与执行链路

- Public command facade：`dayu/host/command.py` 中的 `create_host_command_handle`、`start_run`、`cancel_run`、`cancel_session_runs`、`resolve_wait`。
- 本地调度入口：`dayu/host/dispatch.py` 中的 `HostDispatchScheduler`，负责 pending dispatch -> lane -> LocalProxy / EngineWorker。
- 本地 Engine 边界：`dayu/host/local_proxy.py`、`dayu/host/run_input.py`。
- EngineEvent ingest：`dayu/host/engine_ingest.py`，负责 Engine terminal / diagnostic / awaiting confirmation 映射。

### ToolRuntime 与等待链路

- `dayu/host/tool_runtime.py`：ToolRuntime accept barrier、duplicate governance、truncation、awaiting accept path。
- `dayu/host/waiting.py`：awaiting accept service、`resolve_wait`、late result diagnostic、resume / failed / lost closeout。
- `dayu/host/wait_adapter.py`：wait adapter registry 与最小 `poll_once()` poller。
- `_event_payload.py`：EventLog payload 构造。

## 走读路径

### Start / Dispatch / Engine

设计要求 Host 是 Agent / AsyncAgent / AsyncOpenAIRunner 生命周期治理真源。真实路径为：

`command.start_run` -> `HostAdmissionService.start_run` -> durable Run / Attempt / Dispatch -> `HostDispatchScheduler` -> `RunInputBuilder` -> `LocalProxy` -> Engine runner -> `EngineEventIngestor`

该路径整体保持 Host durable truth 在上，EngineEvent ingest 只能提交 Host-owned candidate，不直接拥有 Host 状态。

### Tool Awaiting / Resolve Wait

设计要求：

`ToolExecutor returns ToolAwaitingOutcome` -> `ToolRuntime submits awaiting candidate` -> Host transaction append `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` -> create active wait record -> `resolve_wait` 统一 resume / failed / lost / late diagnostic。

当前 direct ToolRuntime path 具备这条链路；但真实 `HostDispatchScheduler` 构造 ToolRuntime 时没有传入 awaiting accept port 与 wait adapter registry，见 Finding C01。

### Cancel / Late Result

设计要求 `WAITING` cancel 标记 active wait records 为 `cancelled`，Run 收口 `CANCELLED`，late result 只写 diagnostic。当前代码路径在 `admission.py` / `waiting.py` / `command.py` 中以 durable transition 收口；未发现跨层改写或 Engine 反向持有状态。

### Engine Awaiting Confirmation

设计要求 Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 不能创建 wait record、不能把 Run 推入 `WAITING`、不能追加第二份 canonical facts。当前 `engine_ingest.py` 对这两类事件仅写 diagnostic confirmation，不改变 Host wait 状态，方向正确。

## Findings

### C01 - Blocking / High - 本地 dispatch 生产路径没有接入 P7 awaiting accept port 与 wait adapter registry

**Severity：High**

**Blocking：Yes**

**What can go wrong**

真实本地执行经 `HostDispatchScheduler` 运行时，业务工具如果返回 `ToolAwaitingOutcome`，不会进入 Host awaiting accept path，不会创建 `host_wait_records`，不会把 Run 推进到 `WAITING` / Attempt 推进到 `SUSPENDED`。`ToolRuntimeExecutor` 会把它转成 governed tool failure，后续 Engine 看到的是失败工具结果，而不是可恢复等待。

这使 P7 的核心能力在生产 dispatch entry 上不可用：直接构造 ToolRuntime 的测试可以证明 internal helper 正确，但不能证明 scheduler / local execution 的生产接线正确。

**Evidence**

设计真源要求 ToolRuntime Host accept path 是 awaiting canonical owner：

- `docs/host/design.md:2004-2019`：`ToolExecutor returns ToolAwaitingOutcome -> ToolRuntime submits awaiting candidate -> Host appends TOOL_AWAITING / RUN_WAITING / ATTEMPT_SUSPENDED -> Host creates active wait record`。
- `docs/host/design.md:2058-2087`：poll / callback / manual 结果统一进入 `resolve_wait`，resume 时创建新 Attempt 并从 canonical facts 重建 messages。
- `docs/host/design.md:2098`：adapter registry / lookup 由 Host composition root 提供 typed adapter binding。
- `docs/host/phase7-tool-awaiting-resolve-wait-plan.md:695-704`：P7-S5 要求 integration test 覆盖 local awaiting tool -> WAITING -> manual/poll resolve -> resumed run。

真实 scheduler 构造 ToolRuntime 的代码没有传 awaiting 相关依赖：

- `dayu/host/dispatch.py:688-740`：`HostDispatchScheduler._run_input_builder_for_dispatch` 只传：
  - `accept_port=DefaultHostToolFactAcceptPort(...)`
  - `duplicate_governance_registry=...`
  - 没有传 `awaiting_accept_port`
  - 没有传 `wait_adapter_registry`

ToolRuntime 对缺失依赖的行为是受治理失败，不是 waiting：

- `dayu/host/tool_runtime.py:2420-2456`：`_accept_awaiting` 在 `_awaiting_accept_port is None or _wait_adapter_registry is None` 时返回 `_awaiting_configuration_failure()`。
- `dayu/host/tool_runtime.py:2504-2522`：该 failure 的诊断消息是 `"ToolAwaitingOutcome has no Host wait adapter binding"`，返回 governed failure outcome。

当前 public/local execution options 没有可供 scheduler 注入 wait registry 的字段：

- `dayu/host/api.py:668-703`：`HostLocalExecutionOptions` 只包含 lane、runner、agent policy、worker factory、`tooling_options`、truncation 开关。
- `dayu/host/tooling.py:120-133`：`HostToolingOptions` 只包含 `business_tool_bundle`、`source_refs`、`framework_tool_policy`。

现有 P7 集成测试绕过了生产 scheduler：

- `tests/host/test_phase7_waiting_integration.py:143-178`：测试直接用 `DefaultToolRuntimeFactory(...).create_tool_runtime(...)` 并手工传入 `DefaultHostToolAwaitingAcceptPort(...)` 与 `_wait_adapter_registry()`。
- 同一测试随后直接执行 `tool_runtime.tool_executor`，不是通过 `HostDispatchScheduler._run_input_builder_for_dispatch` 或真实 dispatch loop。

**建议修复**

在 Host 本地执行 composition root 中引入强类型 awaiting wiring，而不是让测试手工拼 ToolRuntime：

1. 为本地 Host composition 增加明确的 wait adapter registry / awaiting accept port 装配输入；位置应遵守分层，不把 adapter 对象写入 durable row，也不放进 per-run request。
2. `HostDispatchScheduler._run_input_builder_for_dispatch` 构造 `ToolRuntimeBuildRequest` 时传入：
   - `awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(transaction_runner=...)`
   - `wait_adapter_registry=<Host composition root provided registry>`
3. 补一条真实 scheduler 级 integration test：`HostDispatchScheduler` + business tool 返回 `ToolAwaitingOutcome` -> Run durable status 为 `WAITING`、Attempt 为 `SUSPENDED`、active wait record 存在 -> manual/poll `resolve_wait` -> resume dispatch record 创建。
4. 更新 `dayu/host/README.md` 中“当前已实现”的措辞，区分 direct ToolRuntime helper 与真实 local dispatch wiring，避免文档宣称生产闭环已经覆盖。

**Root cause**

P7 的等待能力实现集中在 ToolRuntime / waiting service，但没有把 typed adapter binding 作为本地 dispatch scheduler 的 composition dependency。测试覆盖了下层 helper 组合，没有覆盖生产 entry 组合，因此漏掉了 wiring 断点。

## Deferred / Non-blocking Residual Risks

### R01 - Poller 幂等键与 retry digest 策略仍是后续 hardening，不作为本次 blocking

**Severity：Medium**

**Blocking：No，已在总控中登记后续 owner。**

**What can go wrong**

两个 poller 实例或同一 wait 的重复 poll 在同一个 wait 已被第一轮 resolve 后，再以相同 poll 幂等键但不同 `observed_at` 提交相同 outcome，可能被判成 `IDEMPOTENCY_CONFLICT`，而不是稳定重放 / no-op。这样会把 benign duplicate poll delivery 暴露为冲突。

**Evidence**

- `docs/host/phase7-tool-awaiting-resolve-wait-plan.md:416-419`：poller 应维护 in-process in-flight set；ready / lost 的幂等键应由 adapter key、wait id、external job id / provider status version 派生。
- `dayu/host/wait_adapter.py:358-365`：`poll_once()` 使用 `_poll_idempotency_key(record)` 和 `observed_at=self._clock.now()` 调 `resolve_wait`。
- `dayu/host/wait_adapter.py:392-405`：`_poll_idempotency_key` 只包含 `source` 与 `wait_id`，不包含 adapter key、external job id 或 provider status version。
- `dayu/host/waiting.py:1085-1101`：`_wait_resolution_digest` 把 `observed_at` 纳入 semantic digest。
- `dayu/host/waiting.py:682-691`：同 `(wait_id, idempotency_key)` 已有记录但 semantic digest 不同会返回 `IDEMPOTENCY_CONFLICT`。
- `docs/host/implementation-control.md:372-387` 已明确把 poller background loop / backoff / in-flight fencing / adapter retry、poller retry 外部化后的幂等 digest 策略列为 Phase 7 accepted residual risk / later owner。

**建议修复**

保留为后续 poller runtime hardening：引入 wait-id in-flight fencing、把 poll 幂等键和 semantic digest 与 provider status version / external job ref 对齐，并定义 duplicate poll 的稳定 replay 语义。

### R02 - Engine awaiting confirmation 目前不能做 accepted refs 强匹配

**Severity：Low / Medium**

**Blocking：No，当前行为未越权创建状态，强匹配已登记为后续 Engine contract 演进。**

**What can go wrong**

Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 当前只能按 Run=`WAITING` 且 Attempt=`SUSPENDED` 认定为 confirmation diagnostic，无法校验事件是否携带并匹配 Host accepted refs。若未来 Engine contract 加入 refs 前没有同步 Host ingest 校验，diagnostic 可能过于宽松。

**Evidence**

- `docs/host/design.md:2015-2021`：Engine may emit awaiting / suspended with accepted refs only for diagnostic / idempotent confirmation。
- `dayu/host/engine_ingest.py:721-773`：`_confirm_waiting_engine_event` 仅根据 `context.run.status is WAITING` 且 `context.attempt.status is SUSPENDED` 选择 reason，并写 diagnostic，不改变 Host state。
- `docs/host/implementation-control.md:384-386`：Engine matching-ref 强校验归后续 Engine contract 演进。

**建议修复**

后续 Engine contract 演进时，把 Host accepted event refs / wait refs 纳入 Engine awaiting confirmation payload，并在 `EngineEventIngestor` 中校验同一 Run / Attempt / wait identity。当前不要让 EngineEvent ingest 拥有创建 wait state 的能力。

### R03 - Manual resolve audit projection 仍未实现

**Severity：Low**

**Blocking：No，当前不影响 Host durable correctness；属于后续 audit / projection 能力。**

**What can go wrong**

`source=manual` 的 resolve_wait 已走同一 durable pipeline，但没有单独 audit projection。若产品化暴露 manual operator 入口，缺少审计投影会削弱操作追踪。

**Evidence**

- `docs/host/design.md:2103`：manual resolve 只能由受控入口触发，并必须写 audit projection。
- `docs/host/implementation-control.md:386-387`：durable tool trace projection / projection owner 为后续 owner；当前 Phase 7 已接受的是 durable wait / late diagnostic 基础能力。

**建议修复**

在 manual resolve 对外产品化前补 audit projection，不要把 audit payload 塞进 `ResolveWaitRequest` extra bag；应消费 durable event / diagnostic 或专门 projection。

## 架构边界审查

### 已守住的边界

- Host 没有发现对 `dayu.service` / `dayu.ui` / `dayu.fins` 的直接依赖；`tests/host/test_import_boundary.py:112-122` 有自动守卫。
- Host 对 Engine 的依赖被限制在允许边界模块；`tests/host/test_import_boundary.py:125-137` 有自动守卫。
- Engine 不依赖 Host；`tests/host/test_import_boundary.py:156-169` 有自动守卫。
- `dayu.runtime` 不依赖 Host / Engine / Service / UI / Fins；`tests/runtime/test_import_boundary.py:77-87` 有自动守卫。
- Host per-run command request 不携带 `ToolBundle`；`tests/host/test_import_boundary.py:172-190` 有自动守卫。
- Engine awaiting / suspended event 没有被 Host 当作 canonical state creation path；`dayu/host/engine_ingest.py:721-773` 只写 diagnostic。

### 未发现的问题

- 未发现 UI -> Service -> Host -> Engine 方向上的反向 import。
- 未发现 `dayu.runtime` 承载 Host governance state 或 Engine protocol state。
- 未发现财报存取绕过 `dayu.fins.storage` 的 Host 直接路径；Host 当前也不依赖 Fins。
- 未发现新的公共契约直接泄漏 durable row 类型到 `dayu.host.api` 包根 contract。

## Coverage Gaps

- 缺少通过 `HostDispatchScheduler` 的 P7 waiting integration：这是 C01 的测试根因。
- Poller 缺少 duplicate / concurrent poll 的 deterministic replay 测试；总控已列为后续 hardening。
- Engine awaiting confirmation 缺少 accepted refs match 测试；当前 Engine contract 尚不携带 refs，总控已列为后续 contract 演进。
- Manual resolve 缺少 audit projection 测试；当前 audit projection 尚未进入 P1-P7 实现范围。

## Suggested Gate Action

P1-P7 当前代码不应以“local awaiting tool -> WAITING -> resume 已在生产本地 dispatch 入口闭环”为结论放行。建议先修复 C01，并用真实 scheduler integration test 证明 P7 waiting path 通过生产入口可达，再重新执行 Host aggregate validation。
