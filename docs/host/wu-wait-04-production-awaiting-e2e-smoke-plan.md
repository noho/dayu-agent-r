# WU-WAIT-04 UI / Service Production-grade Awaiting E2E Smoke Plan

## Goal / Motivation / Success Signal

目标是增加一条 production-grade public E2E smoke，冻结 UI / Service 正常接入 Host wait governance 的生产工作流。

动机成立。前置 #89 / #90 / #92、WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 已完成，Host 已具备 callback typed boundary、production poller runtime、external job lifecycle abandon 与 cancel hardening；现在缺的是一条不依赖内部 durable row、dispatch row、ToolRuntime internals 或 EngineEvent 的 public workflow smoke，证明 UI / Service 真实入口能观察 `WAITING` 并在生产 wait resolution 后收到同一 Run 的 terminal event / outbox item。

成功信号：

- smoke 通过 `open_host` 装配、`ensure_session`、`submit_followup(queue)`、`accepted_run_id`、`watch_session_events`、`get_run` 与 `read_outbox_terminal_items` 验证完整路径。
- `on_activity` 必须观察到 `EntrypointActivityStatus.WAITING`，证明 Service activity 投影可展示等待态；`get_run(accepted_run_id).status == RunStatus.WAITING` 是额外 public snapshot 断言。
- wait resolution 必须由 production poller 或 callback boundary 触发；本计划选择 production poller，因为 callback endpoint 当前没有 ordinary UI / Service 可用的 public wait id discovery contract。
- 同一个 live watcher 在 `WAITING` 后继续收到恢复后的 terminal `HostEvent`。
- offline / reconnect 补读场景通过 public `host.read_outbox_terminal_items` 证明 terminal item 可补读。
- 测试不读取 durable wait row、dispatch row、scheduler internals、ToolRuntime internals、EngineEvent、wait record mutation helper，不使用测试私有 durable wait id 桥接，不调用 manual resolve 伪造验收。

## Non-goals / Scope Boundary

- 不重新实现 callback endpoint、production poller loop、backoff、fencing 或 external job physical cancel / revoke / abandon。
- 不新增 UI 专用 Host 分支。
- 不把 wait record list/query 提升为普通 UI 必需契约。
- 不改变 Engine public awaiting model。
- 不把 `resolve_wait` 从 Host adapter/internal command path 变成普通 UI 流程依赖。
- 不用 `tests/host/public_smoke_support.py` 中读取 durable wait id 的 helper 作为 production-grade 验收。

## Design Document Alignment

- `docs/host/design.md` 规定 Host 是 Session / Run / Attempt / EventLog / wait governance 真源，UI / Service 通过 `watch_session_events(session_id)` 和 outbox terminal queue 观察结果。
- `docs/host/design.md` 规定 `resolve_wait` 是 poll / callback / manual 的共同治理入口；poller 和 callback 只能触发该 pipeline，不得直接写 Run / Attempt / EventLog。
- `docs/host/design.md` 规定 production poller 由 `open_host` composition root 在显式配置 poll adapter registry 与 wait poller policy 后启动，默认不启动。
- `docs/host/design.md` 规定 `resolve_wait` 是 Host 内部 / adapter API；普通 Service-facing path 不应依赖内部 wait record 查询。
- `docs/engine/design.md` 规定 Engine 只负责单次 run 的 `EngineEvent stream`，不拥有 wait record、poller、Session / Run 生命周期或 durable truth。本 WU 不改变 Engine awaiting model。
- `docs/host/issues-implementation-control.md` 对 WU-WAIT-04 的验收要求是 public watcher 观察 `WAITING`、production wait resolution、terminal event、outbox 补读，并禁止 manual resolve / 测试私有 durable wait id。

## First-principles Judgment and Direct Code Evidence

第一性原理判断：

- 如果 smoke 读取 durable wait row 再调用 `host.resolve_wait(wait_id, source=MANUAL)`，它只能证明 Host command path 可用，不能证明 UI / Service 能通过生产 poller / callback 接入 wait governance。
- 如果 smoke 只断言内部 wait record mutation、dispatch row 或 EngineEvent，它验证的是实现细节，不是 public workflow。
- 如果 Service assembly 默认无法启动 production poller，smoke 不应绕过到 internal test hook；应把缺口定义为最小 public assembly requirement。

直接代码证据：

- `dayu/service/entrypoint_runtime.py` 的 `submit_entrypoint_turn_and_wait` 在 submit 前调用 `_attach_watcher(host, session_id)`，提交后通过 `on_run_accepted(followup.accepted_run_id)` 暴露 accepted run，并在 `_wait_for_terminal` 中用 live watcher queue 与 `host.get_run(run_id)` 轮询等待终态。
- `dayu/service/entrypoint_runtime.py` 的 submit 路径设置 `allow_outbox_terminal_fallback=False`，说明 live watcher 验证与 offline / reconnect outbox 验证必须拆成不同断言；startup reconnect 才通过 `_read_session_outbox_terminal_backfill` 读取 public outbox terminal items。
- `dayu/service/host_assembly.py` 当前能为 Fins awaiting providers 构造 `wait_adapter_registry` 与 `wait_activation_registry`，但没有构造或传入 `HostToolingOptions.wait_poll_adapter_registry`。
- `dayu/service/host_assembly.py` 当前 `compose_open_host_options` 没有任何字段把 `WaitPollerRuntimePolicy` 写入 `OpenHostOptions.wait_poller_policy`，因此 Service production assembly 默认无法启动 production poller。
- `dayu/host/api.py` 的 `OpenHostOptions.wait_poller_policy` 是 public opener contract；`None` 表示不启动 background poller。
- `dayu/host/open_host.py` 的 `_enabled_wait_poller_configuration` 要求启用 poller 时必须存在 `HostToolingOptions.wait_poll_adapter_registry`，否则以 `HostApiError(INVALID_STATE)` fail fast。
- `dayu/host/open_host.py` 的 `_wait_poller_supervisor_from_open_host_options` 从 public opener options 构造 `WaitPollerSupervisor`，poller 通过 command handle 调用 `resolve_wait`，并在 Host close 时关闭。
- `dayu/host/wait_adapter.py` 的 `WaitPoller.poll_once` 先 claim eligible wait record，再调用 adapter；ready / lost 结果只通过 `_resolve_claimed_wait` 进入 `resolve_wait`。
- `dayu/host/wait_callback.py` 与 `dayu/service/wait_callback_endpoint.py` 已提供 framework-neutral callback envelope / endpoint mapper，但 ordinary UI / Service path 当前没有 public wait id discovery；因此 callback 不适合作为本 smoke 的首选 production resolution path。
- `tests/host/public_smoke_support.py` 的 `wait_for_public_waiting_run` 先用 public `get_run` 观察 `WAITING`，随后用 `_active_wait_id` 通过 `open_host_durable_store` 与 `read_active_wait_records_for_run` 读取 wait id；该 helper 明确是测试桥接，不能作为本 WU production-grade 验收。
- `tests/host/test_public_resolve_wait_resume.py` 使用上述 helper 后调用 `host.resolve_wait(... completed_wait_request(...))`，且 `completed_wait_request` 使用 `WaitResolutionSource.MANUAL`；这是已有 public resolve command 覆盖，不是本 WU 所需 production poller / callback smoke。
- `tests/service/test_entrypoint_runtime_interactive_path.py` 已有 Service entrypoint submit helper 的 fake Host 集成测试，可复用其 request / activity 断言思路，但不能复用 fake Host 作为 E2E production wait resolution 验收。

## Affected Files / Modules

Plan gate 只创建本文件。

后续 implementation 允许触及的候选文件：

- `dayu/service/host_assembly.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `tests/service/test_host_assembly.py`
- 新增 `tests/service/test_entrypoint_runtime_awaiting_smoke.py`
- 如需要提取 pure public fixtures，可新增 `tests/service/awaiting_smoke_support.py`；不得从 `tests/host/public_smoke_support.py` 导入会读取 durable wait id 的 helper。
- README 只在触发规则确认属于职责范围后更新；见 Docs / README Decision。

## Public Contract Constraints

允许使用的 public contracts：

- `open_host(options)`
- `OpenHostOptions.wait_poller_policy`
- `HostToolingOptions.wait_adapter_registry`
- `HostToolingOptions.wait_activation_registry`
- `HostToolingOptions.wait_poll_adapter_registry`
- `WaitPollerRuntimePolicy`
- production `WaitPollAdapterRegistry` / adapter boundary
- `ensure_session`
- `submit_followup` / Service `submit_entrypoint_turn_and_wait`
- `get_run`
- `watch_session_events`
- `read_outbox_terminal_items`
- Service `prepare_entrypoint_runtime` / `compose_open_host_options` / `ServiceAssemblyOverrides`
- Service wait callback endpoint mapper only for focused existing tests；本 WU 主 smoke 不依赖 callback。

禁止使用的 internal paths / fake 验收：

- durable wait row 查询，包括 `open_host_durable_store`、`read_active_wait_records_for_run`、`read_wait_record_by_id`。
- dispatch row、scheduler internals、ToolRuntime internals、EngineEvent 直接断言。
- wait record mutation helper。
- 测试私有 durable wait id 桥接。
- `host.resolve_wait(... source=MANUAL ...)` 作为本 WU production-grade smoke 的恢复方式。
- run-scoped internal EventLog 补读。
- 为 UI 新增 Host 分支或把 wait record list/query 变成普通 UI contract。

## Contract / Schema / State-machine / Public-interface Changes

Host public API 无需变更。

Engine public awaiting model 无需变更。

Durable schema 无需变更。

State machine 无需变更。

当前 public contracts 对 production poller smoke 的最小缺口在 Service / Fins assembly：

- `ServiceAssemblyOverrides` 需要一个显式、typed 的 opt-in 字段，例如 `wait_poller_policy: WaitPollerRuntimePolicy | None = None`，使 Service production assembly 能把 public poller policy 传入 `OpenHostOptions.wait_poller_policy`。
- Fins awaiting assembly 需要把已有 `FinsIngestionWaitPollAdapter` 装配为 `WaitPollAdapterRegistry` 并传入 `HostToolingOptions.wait_poll_adapter_registry`；当前只装配了 wait binding registry 与 activation registry。
- 该变更不新增 Host command，不新增 wait record query，不改变默认行为；默认仍不启动 poller。
- `dayu/service/host_assembly.py` 的 `_tooling_options_from_discovery` 必须显式构造并赋值 `wait_poll_adapter_registry`：先用与 `wait_adapter_registry` / `wait_activation_registry` 相同的 provider config、`available_tool_names` 和 Fins awaiting registry input 判断是否存在启用且已绑定到当前 `ToolBundle` 的 Fins awaiting tool；若没有该输入，结果必须为 `None`；若有该输入，则要求 `fins_awaiting_runtime is not None` 且为 ingestion runtime，调用 `build_fins_wait_poll_adapter_registry(runtime=fins_awaiting_runtime, tool_names=registry_inputs.tool_names)`，并把结果传入 `HostToolingOptions(wait_poll_adapter_registry=...)`。该 poll adapter registry 必须与 awaiting tool callable、wait binding registry 和 activation registry 共享同一个 Fins awaiting runtime，禁止另建 runtime。

如果 implementation 发现上述最小 assembly gap 不足以通过 public contracts 完成 production poller resolution，必须停止并在 implementation report 中标为 blocked，不能退回 durable wait id / manual resolve。

## Implementation Decisions

- 选择 production poller path，不选择 callback path。原因是 callback endpoint 需要 `wait_id`，当前普通 UI / Service public event/activity 不暴露 wait id；强行从 durable row 或 internal event payload 拿 wait id 会违反本 WU 红线。
- Service poller opt-in 采用 typed override，不在本 WU 增加 runtime config schema。原因是当前目标是 smoke / public workflow validation；配置产品化可以后续独立处理，当前最小需求是让 Service assembly 有 public typed path 启动已有 poller。
- Fins poll adapter registry 使用现有 `FinsIngestionWaitPollAdapter`，不重新实现 poller loop、backoff、fencing 或 external job lifecycle。
- E2E smoke 使用 deterministic awaiting tool / worker / poll adapter 只作为 production adapter 替身，并通过 public HostToolingOptions 注册；测试主体只观察 public Host / Service contracts，不读取 durable wait row。
- Live watcher 验证与 outbox reconnect 验证分开断言，避免把 submit path 的 outbox fallback 当作 final answer 主展示路径。
- S1 是 production assembly slice，目标是让真实 Service/Fins 装配能得到 poller policy 与 poll adapter registry；S2 是 public workflow smoke slice，可直接组装 public `OpenHostOptions` 和 deterministic public poller contract，不需要依赖 S1 的 Service assembly helper，但必须验证与 S1 相同的 public poller contract：`WaitPollerRuntimePolicy` + `HostToolingOptions.wait_poll_adapter_registry` + common `resolve_wait` pipeline。

## Small Implementation Slices

### S1 - Service production poller assembly gap

Objective:

补齐 Service/Fins public assembly 中启动 production poller 所需的最小 typed path。

Allowed files:

- `dayu/service/host_assembly.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `tests/service/test_host_assembly.py`

Exact changes:

- 在 `ServiceAssemblyOverrides` 增加 `wait_poller_policy: WaitPollerRuntimePolicy | None = None`，docstring 明确这是 Service assembly 显式启用 production wait poller 的 typed opt-in，默认不启动。
- `compose_open_host_options` / `_compose_options` 将 override 传入 `OpenHostOptions.wait_poller_policy`。
- 在 Fins wait adapter module 增加最小 builder，例如 `build_fins_wait_poll_adapter_registry(runtime, tool_names) -> WaitPollAdapterRegistry`，复用现有 `FinsIngestionWaitPollAdapter(runtime=runtime)` 与 stable adapter key；`tool_names` 只用于复用现有 Fins awaiting 工具名校验和 adapter key 覆盖检查，builder 只做装配，不新增 poller 逻辑。
- `dayu/service/host_assembly.py` 增加与 `_fins_wait_activation_registry_from_provider_configs` 同源的数据流，例如 `_fins_wait_poll_adapter_registry_from_provider_configs(...)`：调用 `_fins_awaiting_registry_inputs_from_provider_configs(provider_configs, available_tool_names=...)`；输入为 `None` 时返回 `None`；输入非 `None` 时要求 `fins_awaiting_runtime is not None` 且是 ingestion runtime，否则 fail fast；随后用同一个 `fins_awaiting_runtime` 构造 poll registry。
- `_tooling_options_from_discovery` 必须把上一步结果赋给局部变量 `wait_poll_adapter_registry`，并在 `HostToolingOptions(...)` 中显式传入 `wait_poll_adapter_registry=wait_poll_adapter_registry`。当 Fins awaiting runtime 与 awaiting tool bindings 同时存在时该字段非 `None`；否则必须是 `None`。
- 更新 `tests/service/test_host_assembly.py`：断言默认 `wait_poller_policy is None`；显式 override 会进入 `OpenHostOptions`；启用 Fins awaiting providers 且发现对应 awaiting tools 时 `HostToolingOptions.wait_poll_adapter_registry` 非 `None`，并与 binding / activation registry 同时存在；无 awaiting provider、provider disabled 或发现结果不包含 awaiting tool binding 时不装配 poll registry，字段为 `None`。

Tests:

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
- `source .venv/bin/activate && pyright`

Completion signal:

- Service assembly 可仅通过 public typed inputs 得到包含 `wait_poller_policy` 与 `wait_poll_adapter_registry` 的 `OpenHostOptions`。

Stop condition:

- 如果需要暴露 wait record query、把 wait id 投影给 ordinary UI，或要求测试读 durable row，停止并标为 blocked。

### S2 - Public-only entrypoint awaiting E2E smoke

Objective:

增加 production-grade public E2E smoke，验证 UI / Service entrypoint 在 production poller resolution 下从 `WAITING` 走到 terminal live event，并通过 outbox 补读 terminal item。

Allowed files:

- 新增 `tests/service/test_entrypoint_runtime_awaiting_smoke.py`
- 如需要，新增 `tests/service/awaiting_smoke_support.py`
- 必要时更新 `tests/service/test_host_assembly.py` 中共享 helper；不得修改生产代码。

Exact changes:

- 构造 public `OpenHostOptions`：包含 deterministic worker factory、business awaiting tool bundle、wait binding registry、wait poll adapter registry、`WaitPollerRuntimePolicy(enabled=True, poll_interval_seconds=...)` 使用短测试值但不改变生产默认。S2 可直接组装这些 public options，不必通过 `compose_open_host_options`，但 smoke 必须证明 production poller 只通过 public `wait_poll_adapter_registry` 解锁恢复。
- deterministic worker 第一次 dispatch 通过真实 public tool-calling path 产生 awaiting outcome；resume 后第二次 dispatch 产出 final answer。测试不得直接断言 EngineEvent。
- poll adapter 通过 production `WaitPollAdapterRegistry` 注册。deterministic adapter 实例必须持有测试控制的同步门控，例如 `asyncio.Event` / gate：gate 未打开时每次 `poll_wait` 返回 `WaitPollNotReady`；测试通过 public activity callback 和/或 `get_run` 观察到 `WAITING` 后才打开 gate；gate 打开后下一次 `poll_wait` 返回 `WaitPollReady(ResolveWaitCompletedOutcome(...))`，让 background poller 调用 common `resolve_wait` pipeline。禁止使用简单无约束的 NotReady-then-Ready 计数器作为唯一同步，因为它可能在 public WAITING 观察前提前 resolve。
- deterministic adapter 的状态必须是 smoke 生命周期内的实例状态或显式测试 fixture 状态，不得使用模块级全局计数器；adapter 可以实现 public `WaitPollAdapter` protocol 并消费 Host 传入的 wait snapshot，但 smoke 的断言路径不得读取 durable rows、不得导入 durable helper、不得用 wait id 桥接。
- 用 `open_host(options)` 打开 Host，`ensure_session` 创建 session，调用 Service `submit_entrypoint_turn_and_wait`，通过 `on_run_accepted` 记录 `accepted_run_id`。
- `on_activity` 必须收集并断言至少一次 `EntrypointActivityStatus.WAITING`；测试同时用 `host.get_run(accepted_run_id)` 断言 public snapshot 曾观察到 `RunStatus.WAITING`。建议 `on_activity` 在看到 waiting activity 后设置 `waiting_activity_seen` event，测试再确认 `get_run(...).status == RunStatus.WAITING`，最后打开 poll adapter gate。
- 断言 `submit_entrypoint_turn_and_wait` 返回 `EntrypointTerminalSource.LIVE_EVENT`、同一 `accepted_run_id`、terminal status succeeded、final answer 非空。
- outbox 补读子测试使用具体 public Host API：terminal 后调用 `host.read_outbox_terminal_items(ReadOutboxTerminalItemsRequest(session_id=session_id, after=OutboxTerminalCursor(event_sequence=0), limit=...))`，断言 batch 中存在同一 `accepted_run_id` 的 terminal item，并按 `terminal_event_id` / `event_sequence` 去重。不要引用不存在的 reconnect helper；只有刻意测试 Service startup reconnect 语义时才可另用实际存在的 `startup_reconnect_entrypoint_session`，本 smoke 首选直接 public outbox read。
- 增加 forbidden-path import / grep guard 作为验证说明：测试文件不得 import `dayu.host.durable` 或 `dayu.host.tool_runtime`，不得出现 `open_host_durable_store`、`read_active_wait_records_for_run`、`read_wait_record_by_id`、`ResolveWaitRequest`、`WaitResolutionSource.MANUAL`、`resolve_wait(`、`EngineEvent`、dispatch row / scheduler internals / ToolRuntime internals。测试源码的注释和 docstring 应避免写入这些 forbidden names；若 implementation report 中出现 grep 命中，必须逐条解释是否为 benign match，不能把 benign match 当作已通过证明。

Tests:

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
- `source .venv/bin/activate && pyright`
- `rg -n "from dayu\\.host\\.durable|import dayu\\.host\\.durable|from dayu\\.host\\.tool_runtime|import dayu\\.host\\.tool_runtime|open_host_durable_store|read_active_wait_records_for_run|read_wait_record_by_id|ResolveWaitRequest|WaitResolutionSource\\.MANUAL|resolve_wait\\(|ToolRuntime|EngineEvent|dispatch row|scheduler" tests/service/test_entrypoint_runtime_awaiting_smoke.py` should return no matches. 若出现仅来自注释 / docstring 的 benign match，implementation report 必须解释，但测试源码应主动避免这些文字。

Completion signal:

- E2E smoke fails if production poller is not assembled, if Run never reaches `WAITING`, if terminal event only appears through manual resolve, or if outbox terminal item is missing.

Stop condition:

- 如果 public contracts 无法让 production poller/callback 完成 wait resolution，不允许改用 durable wait id 或 manual resolve；标为 blocked，并说明缺少的最小 public contract。

## Tests / Validation Commands and Expected Assertions

Plan gate validation:

- `git diff --check -- docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md docs/reviews/wu-wait-04-plan-fix-codex.md`

Implementation validation:

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
- `source .venv/bin/activate && pyright`
- forbidden-path grep listed in S2。

Expected assertions:

- Service assembly default does not start poller.
- Explicit Service override sets `OpenHostOptions.wait_poller_policy`.
- Fins awaiting assembly provides binding registry, activation registry and poll adapter registry when enabled.
- E2E smoke records `accepted_run_id`.
- `get_run(accepted_run_id)` observes `RunStatus.WAITING` before terminal.
- Activity projection includes waiting status for UI display.
- Production poller resolves wait; test does not call `resolve_wait` directly.
- Same Run reaches `HostTerminalStatus.SUCCEEDED` through live watcher.
- Outbox terminal read can backfill the same Run terminal item without duplicate display.
- Smoke assertion path never reads durable wait rows, never imports durable helpers, never reads dispatch rows, never inspects scheduler internals, never inspects ToolRuntime internals, never asserts EngineEvent, never mutates wait records, and never uses manual resolve.

## Docs / README Decision

Plan gate 只创建 plan artifact，不更新 README、design doc 或 control doc。

Implementation gate 会修改 `dayu/service/`、`dayu/fins/` 和 `tests/`，因此必须先检查：

- `dayu/fins/README.md`
- `tests/README.md`

只有当实际变更属于目标 README 的职责范围与目标读者时才更新。若仅新增 Service smoke 且不改变用户可见 CLI / Web / WeChat 工作流、命令参数或默认输出通道，根目录 `README.md` 预计无需更新。若 Service assembly public override 被视为开发者可见 contract，需要按 README 内约束判断是否同步。

## Risks / Open Questions and Residual Risk Classification

- Risk R1, medium: Service assembly 当前缺少 poller policy 与 poll adapter registry wiring。S1 直接处理；未处理前 S2 必然不能代表 production poller path。
- Risk R2, medium: test-only deterministic adapter 可能被误解为生产 Fins adapter 验收。缓解：S1 单独验证 Fins assembly registry，S2 只验证 public workflow 与 production poller runtime，不声称覆盖真实 Fins ingestion 业务结果。
- Risk R3, low: poller background timing 可能导致测试 flake。缓解：deterministic adapter 用测试 gate 在 public `WAITING` activity 与 `get_run` snapshot 被观察前持续返回 not-ready；观察完成后才允许 ready。
- Risk R4, low: forbidden grep 可能因注释文字误报或漏掉别名。缓解：用 import-oriented pattern 覆盖 `dayu.host.durable` 等 durable module import，测试源码避免在注释 / docstring 写 forbidden names，implementation report 解释任何 benign match。
- Risk R5, low: `WaitPollAdapter` protocol 的参数类型可能暴露 durable row typed name。缓解：smoke 的 assertion path 不得读取 durable row 或导入 durable helper；若严格 typing 需要 public type alias/export 或 protocol-compatible adapter signature，implementation 必须选择最小、保持 public contract 的方案并通过 pyright，不得以此授权 durable store query、internal wait mutation 或测试私有 wait id bridging。

Open questions:

- 是否要在后续独立 work unit 把 wait poller enablement 纳入 runtime config schema，而不是只通过 Service override opt-in。本 WU 不处理。
- 是否需要 ordinary UI / Service callback wait id discovery contract。当前设计不需要；callback 产品化可以作为独立 design gate。

Residual risk classification:

- 当前 plan decision 为 ready-with-minimal-public-contract-implementation-requirement，不是 blocked。
- 若 implementation 证明 S1 的最小 Service/Fins assembly gap 不足以让 production poller 通过 public contracts 完成 resolution，则 residual risk 升级为 blocking，并停止 S2。

## Completion Report Format

Implementation / closeout 必须按以下格式汇报：

- artifact path
- plan decision: ready / blocked
- proposed slice count and rationale
- public-contract-only enforcement summary
- validations run
- open questions / blockers

## Why This Is Not Over-designed

- 只补 Service production poller assembly 的最小缺口，不新增 Host command、durable schema、状态机或 Engine contract。
- 只选 production poller 一条 resolution path，不同时实现 callback E2E。
- 只切 2 个 slices：S1 是 production assembly contract，S2 是 public workflow smoke；两者逻辑上互补，S2 可直接组装 public opener options，但必须验证同一 public poller contract。
- 不把 wait record list/query 公开给 UI，也不把测试桥接变成产品 contract。
