# Phase 10.5 Ordinary Local Multi-turn Public Contract Freeze Handoff Plan

## Gate

当前 gate：Phase 10.5 handoff implementation-ready plan generation。

本 artifact 只供 implementation agent 使用：不实现代码、不修改 `dayu/` 源码、不修改 tests、不修改 README、不提交、不 push、不进入 implementation gate。

## Goal / Motivation

目标是冻结普通本地多轮会话的 Host public interface / contract，并补齐生产接线，使未来真实生产系统 Service 只调用 Host public contract 即可完成普通本地多轮闭环：

```text
async with open_host(options) as host:
  session = await host.ensure_session(...) / create_session(...) / get_session(...)
  events = host.watch_session_events(session.session_id)
  await host.submit_followup(session.session_id, SubmitFollowupRequest(...))
  # final answer 只从 terminal HostEvent 展示
```

动机成立。`docs/host/post-p10.md` 明确记录：Phase 10 后 Host 内部多轮主体能力基本存在，但调用方若要让 Run 真正执行，仍需手工装配 `HostDispatchScheduler`、durable store、`ActiveWorkerRegistry`、local execution / worker factory / tooling / compactor，并显式唤醒 scheduler。这不是稳定 Host public runtime，而是把 Host 内部接线泄漏给 Service。

本计划的第一性原理判断：P10.5 不是“补 smoke 测试”，而是把普通本地多轮的生产接线降到一个 typed `open_host(options)` construction contract 与一个 async public handle。Smoke 只是证明这条接线没有绕过 public path。

## Non-goals

- 不实现 Phase 11 Recovery、startup scan、positive orphan proof、`RECOVERING` 通用恢复、crash recovery smoke、active cancel watchdog 或 stuck `CANCELLING` hardening。
- 不实现 RemoteProxy / RemoteStub，不让远端拥有 Host 状态，不让 RemoteStub / EngineWorker append EventLog 或更新 Run / Attempt。
- 不实现 ToolsDiscovery / ScenePrepare 具体 adapter、manifest schema、provider 注册生命周期、业务工具扫描或真实财报工具接入。
- 不实现 Outbox concrete read / drain API、OutboxSink terminal delivery queue、离线 terminal delivery smoke、Audit / Tool Trace concrete projection。
- 不实现 `purge_session(...)` destructive cleanup、purge tombstone、删除矩阵、payload / memory / projection / outbox / tool trace 清理、retention hardening。
- 不迁移 `/Users/leo/workspace/dayu-agent` 的 web tools。
- 不实现 ConfigLoader；真实 runner smoke 可使用受控硬编码 runner 参数。
- 不实现真实 Service / CLI / WeChat / GUI 接入；薄 Service 只是最小 consumer proof，不是 Host 特殊接口类型。
- 不定义 `wait_final_answer(...)`、public payload reader、`read_payload(ref)` 或 `get_run_result(...)`。
- 不把 projection / timeline / audit / trace / outbox / memory snapshot 当 truth。

## Scope Boundary

允许修改范围由后续 implementation gate 执行，本计划只规定边界：

- Host public opener / async handle / typed construction options。
- Host internal composition root：command handle、durable store、scheduler、active registry、local execution、ToolRuntime、memory catch-up、context compactor、stream fanout 与 after-commit wakeup 接线。
- Public request / snapshot / event 类型：`SubmitFollowupRequest` 的 typed fields、per-run tool selector、per-run execution override、typed `HostEvent` terminal final answer view。
- Public commands：`submit_followup(queue/steer)`、`retry_run(...)`、`replay_run(...)`、`resolve_wait(...)`、`cancel_run(...)`、`cancel_session_runs(...)`、`close_session(...)` 在 public opener 下的本地接线与可观察性。
- Package exports 与 docs：把 Service-facing namespace 收敛到 P10.5 冻结 contract。
- Tests / smoke：所有主证明必须走 `open_host(options)`、public command、`watch_session_events(session_id) -> AsyncIterator[HostEvent]`、terminal HostEvent final answer path。

禁止越界：

- Engine 不得理解 Host 状态、memory、guidance、steer、fetch_more 或 tool governance。
- Service 不得手工装配 scheduler、dispatch internals、durable store、active registry、memory catch-up 或 compact artifact store。
- EngineEvent `tool_awaiting` / `run_suspended` 不得创建 wait record、推进 `WAITING` 或关闭 Attempt；ToolRuntime Host accept path 是 canonical owner。
- Replay 不得暴露 tool schemas 或执行工具；ToolRuntime 拒绝只是 defense-in-depth。

## Direct Evidence

- `docs/host/design.md` §2：固定依赖方向 `UI -> Service -> Host -> Engine`，Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 真源，Engine 只执行单次 `AgentRunRequest`。
- `docs/host/design.md` §10.1：Host handle 是 composition root / handle，不是 god object；command path 与 background runtime 分 facet；内部新 Run admission primitive 固定为 `_start_run`，不进入 Service-facing public API。
- `docs/host/design.md` §10.1：Host construction 接收全量 business `ToolBundle`；`SubmitFollowupRequest.tool_names` 是 per-run business tool selector；`None=all`，空集合=禁用业务工具，非空集合=子集；admission 必须校验并冻结 effective tool names / digest。
- `docs/host/design.md` §11：Service-facing opener 固定为 async `open_host(options)`；public handle 提供 Session / Run command、`watch_session_events(session_id) -> AsyncIterator[HostEvent]`、terminal final answer view 和 handle close lifecycle。
- `docs/host/design.md` §11：`open_host(options)` construction-time options 承载 durable store、payload / artifact roots、runner / worker factory、全量 ToolBundle、ToolRuntime policy、ContextCompactor、context budget policy、memory catch-up、stream fanout / background supervisor 端口与运行目录；不得引入 ConfigLoader、全局配置或 service locator。
- `docs/host/design.md` §11：per-run `runner_spec`、`runner_options`、`agent_policy` 是 field-level partial merge；字段省略使用 opener baseline，字段出现使用完整 typed value；不得接受 patch dict、extra payload 或 profile registry lookup。
- `docs/host/design.md` §11：LLM compactor 使用独立 construction-time baseline，不受 ordinary Run override、`tool_names` 或 `system_prompt` 影响。
- `docs/host/design.md` §11：`HostEvent` 是 Host-owned typed event；terminal `SUCCEEDED` 必须 inline final answer view，字段为 `content`、`filtered`、`degraded`、`finish_reason` 与 terminal status；`HostEventView` 是内部 diagnostic DTO。
- `docs/host/design.md` §21：`resolve_wait` 是短事务 command，`WAITING -> resolve_wait -> resume` 创建新 Attempt；retry / replay 是函数式 public control API，创建关联新 Run，不重开源 Run。
- `docs/host/implementation-control.md` Phase 10.5：当前 gate 已进入 handoff implementation-ready plan generation；P10.5 必须冻结 ordinary local multi-turn public contract，补齐 `open_host(options)`、live watch、steer / retry / replay、memory catch-up / compact opener contract 与 smoke。
- `docs/host/post-p10.md`：明确 Phase 10 后缺的是稳定 public runtime / composition root，而不是内部多轮能力；S1-S5 smoke matrix 和 G6-G11 gap tracking 均要求 public path 验证。
- `docs/reviews/post-p10-5-plan-readiness-review-mimo-20260518.md`：0 blocking；要求统一 smoke coverage table、`OpenHostOptions` typed dataclass、`HostClosedError` 类型选择记录、S5 / WAITING resume checklist。
- `docs/reviews/post-p10-5-plan-readiness-review-ds-20260518.md`：0 blocking；要求 plan 明确 `OpenHostOptions`、terminal `HostEvent` typed view、field-level partial merge、compactor baseline typed shape 与 provider skip 规则。
- `docs/reviews/post-p10-5-plan-readiness-review-codex-20260518.md`：0 blocking；要求把 S4 compact、WAITING resume、multi-client watch、`close_session` 边界分配到 slice / tests，并把 `HostEventStream` 收敛为非 Service-facing handle 语义。

## Public Contract Change List

P10.5 implementation 必须把 Service-facing public contract 冻结为：

- 新增 `open_host(options)`：async context manager，`async with open_host(options) as host:`。
- 新增 Host public handle：只暴露普通 Service 需要的方法，不暴露 store、scheduler、registry、dispatch row、wakeup port 或 ToolRuntime internals。
- `submit_followup(queue)`：第一条 prompt 与后续普通 prompt 的唯一 Service-facing entry；不再用 `start_run(...)`。
- `submit_followup(steer)`：落地本地 steer 语义；active Run precondition，不创建新 Run，同一 Run 新 Attempt。
- `retry_run(...)`：落地普通本地 `FAILED` retry，创建关联新 Run；`LOST` / `RECOVERING` retry 归 Phase 11。
- `replay_run(...)`：落地 `SUCCEEDED` structure replay，no-tool，不改写源 Run EventLog truth。
- `resolve_wait(...)`：作为 WAITING public resume path，接收 poll / callback / manual 已取得结果；不等待外部 job、不轮询、不长阻塞。
- `close_session(...)`：只关闭 Session 新输入入口；不 cancel、不 purge、不关闭 opener runtime。
- `watch_session_events(session_id) -> AsyncIterator[HostEvent]`：唯一普通 Service-facing 事件入口；terminal final answer 只能从 terminal `HostEvent` typed view 展示。
- `start_run(...)` 降级为内部 `_start_run(...)` admission primitive；不从 `dayu.host` public namespace 导出，不进入 README ordinary Service recipe。
- `create_host_command_handle(...)` 降级为 Host 内部 / 低层测试 composition primitive；普通 Service 只用 `open_host(options)`。
- `HostLocalRuntime`、`HostLocalExecutionOptions` 降级为内部 implementation contract；Service 不理解这些名字。
- `HostEventView` / run-level stream 降级为 diagnostic / internal；`stream_run_events(...)` 不进入 ordinary Service-facing public contract。
- `HostEventStream` 若保留，只能是内部实现或返回类型别名 / Protocol；不能成为 Service 必须理解的 context manager、subscription handle 或第二套 public stream contract。

## Typed Options Shape

Slice 1 必须定义 concrete typed construction contract。建议放在 `dayu/host/api.py` 或新的 public `dayu/host/open_host.py` 中，并从 `dayu.host` 包根导出 `OpenHostOptions`、`Host` / `HostHandle`、`open_host`、`HostClosedError`、`HostEvent` 相关 public 类型。

禁止使用无结构 `dict`、`object`、`Any`、service locator、extra payload、profile registry lookup 或模块级 singleton 承载 required fields。

建议 typed shape：

```text
@dataclass(frozen=True, slots=True)
OrdinaryRunExecutionBaseline
  runner_spec: RunnerSpec
  runner_options: RunnerCallOptions
  agent_policy: AgentPolicy

@dataclass(frozen=True, slots=True)
CompactorExecutionBaseline
  context_compactor: ContextCompactor | None
  compactor_runner_spec: RunnerSpec | None
  compactor_runner_options: RunnerCallOptions | None
  compactor_policy_ref: str | None
  compact_artifact_root: Path
  compact_artifact_create_parent_dirs: bool = True

@dataclass(frozen=True, slots=True)
OpenHostOptions
  host_handle_id: str | None
  db_path: Path
  artifact_root: Path
  create_parent_dirs: bool
  sqlite_busy_timeout_seconds: float
  sqlite_write_busy_retry_count: int
  sqlite_write_retry_initial_delay_seconds: float
  sqlite_write_retry_backoff_multiplier: float
  sqlite_write_retry_max_delay_seconds: float
  payload_inline_threshold_bytes: int
  lane_db_path: Path
  lane_name: str
  lane_capacity: int
  lane_default_timeout_seconds: float | None
  lane_claim_ttl_seconds: float
  lane_heartbeat_interval_seconds: float
  worker_startup_timeout_seconds: float
  dispatch_poll_interval_seconds: float
  ordinary_run_baseline: OrdinaryRunExecutionBaseline
  worker_factory: LocalEngineWorkerFactory
  tooling_options: HostToolingOptions | None
  context_budget_policy: ContextBudgetPolicy | None
  compactor_baseline: CompactorExecutionBaseline | None
  memory_projection_policy: MemoryProjectionPolicy
  memory_projection_catchup_batch_size: int
  enable_truncation_manager: bool
```

`HostToolingOptions` 复用当前代码库已有 typed shape，作为 construction-time 全量业务工具与 ToolRuntime governance 配置入口。若现有类型尚未显式承载 ToolRuntime policy 所需 typed fields，Slice 1 负责在该 typed shape 上补齐字段；不得改用 `extra payload`、service locator、profile lookup 或无结构 `dict` 传递 policy。

Implementation 可把字段名微调为更贴合现有 `HostCommandHandleOptions` / `HostLocalExecutionOptions`，但不得改变边界：

- durable store / payload / artifact roots 必须是 construction-time typed fields。
- worker factory、runner baseline、agent baseline、tooling options、context budget policy、compactor baseline、memory catch-up 都必须可显式传入。
- scheduler、wakeup、active worker registry、dispatch control、stream fanout supervisor 由 `open_host` 内部创建或连接，不作为 Service-facing options 暴露。
- 每 Run 可变项不进入 `OpenHostOptions`；只能进入 typed request。

`HostClosedError` 决策：新增 public standalone lifecycle exception class，例如 `HostClosedError(Exception)` 或项目内更窄的 lifecycle base class；不要把 handle closed 映射为 command-level `HostApiErrorCode.INVALID_STATE`，避免与 Session `CLOSED`、not found、purged、retry precondition failed 混淆。若 implementation 认为必须新增 `HostApiErrorCode.HOST_CLOSED`，立即停下交 Controller 更新设计真源。

## Per-run Effective Config Freeze

`SubmitFollowupRequest` 必须新增或迁移到以下 typed fields：

```text
system_prompt: str | None
user_prompt: str
tool_names: frozenset[str] | None
runner_spec: RunnerSpec | None
runner_options: RunnerCallOptions | None
agent_policy: AgentPolicy | None
```

Field-level partial merge 语义固定：

- `runner_spec is None` 使用 `open_host(options).ordinary_run_baseline.runner_spec`；出现则使用该完整 `RunnerSpec`。
- `runner_options is None` 使用 opener baseline；出现则使用该完整 `RunnerCallOptions`。
- `agent_policy is None` 使用 opener baseline；出现则使用该完整 `AgentPolicy`。
- 三个字段不要求 all-or-nothing。
- 单个出现的 override 必须是完整 typed value；不得是 patch dict、partial dataclass、extra payload 或 profile id。
- admission / dispatch 必须把本 Run effective config freeze 到 Run / Attempt 可解释 snapshot、source refs 或 diagnostic refs；同一 Session 不同 Run 切换模型或参数必须可由 public request 证明。
- retry 默认复用源 Run effective config refs，除非 retry policy 显式创建新的 typed config decision；replay 默认复用源 Run执行 baseline但强制 no-tool。

## Per-run Tool Selection

`SubmitFollowupRequest.tool_names` 语义固定：

- `None` 或字段省略：允许使用 construction-time 全量业务工具。
- 空集合：禁用本次 Run 的全部业务工具；framework tools 仍由 framework policy 决定。
- 非空集合：只允许列出的业务工具名。
- admission 必须校验所有 tool name 均存在于 construction-time `HostToolingOptions.business_tool_bundle`。
- admission / dispatch 必须冻结 resolved effective business tool names、schema digest 和 source refs。
- `tool_names` 不得携带 raw `ToolBundle`、`ToolDefinition`、callable、schema fragment、逗号分隔字符串、自然语言描述或 discovery adapter。

## Session-level Live Event Stream

`watch_session_events(session_id) -> AsyncIterator[HostEvent]` 是唯一普通 Service-facing 事件入口。

Public `HostEvent` 第一版只需冻结：

- common fields：`event_id`、`event_sequence`、`session_id`、`run_id | None`、typed kind、dedupe identity。
- terminal view：`terminal_status`、`final_answer: HostFinalAnswerView | None`、error / cancel typed display fields。
- `HostFinalAnswerView` fields：`content`、`filtered`、`degraded`、`finish_reason`、`terminal_status`。

Implementation 必须至少覆盖 `SUCCEEDED`、`FAILED`、`CANCELLED` terminal kind，以及一个 non-terminal displayable event 或 progress event 作为接线证明。其它 tool / thinking / content delta kind 可以在同一 typed union 中自然扩展，但 P10.5 smoke 不要求全部 display kind。

Iterator lifecycle：

- `watch_session_events` 是 live watch，不接收 cursor，不负责离线补读。
- terminal event 不自动结束 iterator；同一 Session 后续 queue / retry / replay / follow-up 仍可继续产出事件。
- consumer cancel / early close 只关闭本次 watch，不写 EventLog、不 cancel Run、不影响其它 watcher。
- Host handle close 后新开 watch 抛 `HostClosedError`；已打开 watcher 正常结束或抛 lifecycle termination，不写 cancel facts。
- Session `CLOSED` 仍允许 watch 和 read；purged / not found 返回 typed not-found / gone。

## Close / Cancel Boundary

- `close_session(...)`：Session governance fact；只关闭新输入入口。已有 non-terminal Run 继续按状态机完成；已 accepted queued Run 继续 promotion；`WAITING` Run 可通过 `resolve_wait` 继续；读取和 watch 仍可用。
- Host opener `close()` / `__aexit__`：当前 handle lifecycle；关闭本地 runtime，不把 Session 改成 `CLOSED`，不写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED` 或伪装用户意图的 terminal fact。
- `cancel_run(...)` / `cancel_session_runs(...)`：用户停止 Run 的治理意图；必须写 canonical cancel facts，并通过 public event / read path 可见。
- Recommended Service policy：若用户意图是“结束会话并停止当前工作”，Service 应先显式 `cancel_session_runs(...)`，确认 cancel 可见后再 `close_session(...)`。

## WAITING Resume Path

P10.5 必须验证：

```text
Run WAITING
  -> public resolve_wait(wait_id, ResolveWaitRequest(...))
  -> short durable transaction appends RESUME_REQUESTED + tool terminal/result fact
  -> creates new Attempt / dispatch record
  -> after-commit wakeup
  -> scheduler dispatch
  -> watch_session_events terminal HostEvent
```

`resolve_wait(...)` 不实现 callback endpoint、callback auth / replay、poller loop、backoff / in-flight fencing 或 external job physical cancel / revoke。poll / callback / manual adapter 只负责拿到结果后调用同一个 public command。

## Memory Catch-up And Compact Opener Contract

`open_host(options)` 必须接入 memory catch-up、context budget policy、compact artifact root 和 compactor baseline，普通 Service 不得手工装配这些内部件。

`compactor_baseline=None` 语义固定为 fail-closed：Host 没有可用 compaction 能力，不得隐式创建 fake compactor、不得静默忽略 context budget policy、不得把 ordinary Run override 当 compactor 配置使用。若当前 Run 在预算压力下需要 compaction 才能继续，必须以 typed budget / compaction-unavailable failure 结束该 Run 或拒绝该执行路径；短上下文本身未触发预算压力时可以正常运行。

S4 compact smoke 边界：

- Host production opener 不得隐式默认 fake compactor。
- Smoke 必须显式传入真实 LLM-backed `ContextCompactor` adapter；该 adapter 可以作为 tests smoke support 存在，但必须真实调用 runner / provider，不读取 expected answer、run id、轮次或测试私有答案。
- Compactor execution baseline 独立于 ordinary Run override；`SubmitFollowupRequest.runner_spec` / `runner_options` / `agent_policy` / `tool_names` / `system_prompt` 不影响 compactor。
- 必须覆盖 `CONTEXT_COMPACTION_REQUESTED`、compact artifact、`CONTEXT_COMPACTED`、memory projection consumption 与 subsequent RunInputBuilder continuity marker。
- 若 provider / API key / 网络不可用，真实 compactor smoke 可以显式 skip；skip 必须报告 secret ref / provider / network reason，且不能让 mock compactor替代 P10.5 compact success signal。

## Readiness Review Closure

| Review item | Source | Plan resolution | Owner |
| --- | --- | --- | --- |
| Smoke naming / owner gap | MiMo F1, Codex F1 | 本计划下方统一 coverage table 把 S1-S5、WAITING、steer / retry / replay、multi-client watch、close boundary 全部分配到 slice / tests。 | Plan + Slice 5 / Slice 6 |
| `OpenHostOptions` typed shape | MiMo F2, DS F1 | Slice 1 必须定义 `OpenHostOptions`、ordinary baseline、compactor baseline；禁止 dict / service locator。 | Slice 1 |
| `HostClosedError` identity | MiMo F3 | Plan 指定 standalone lifecycle exception；若需新 error code，交 Controller。 | Slice 1 |
| S5 / WAITING checklist | MiMo F4, Codex F1 | Coverage table 拆出 cancel accepted/queued/pre-dispatch/active/session-scope/read path/close boundary，以及 WAITING resume public path。 | Slice 5 |
| HostEvent typed shape | DS F2, Codex F2 | Slice 4 冻结 terminal `SUCCEEDED` / `FAILED` / `CANCELLED` typed view，`HostEventStream` 只作 internal/type alias。 | Slice 4 |
| Per-run partial merge | DS F3 | Plan 明确 field-level partial merge，不采用 all-or-nothing。 | Slice 3 / Slice 6 |
| Followup watermark | DS F4 | 沿用 `FollowupSnapshot` 当前字段或新增 command commit sequence；必须声明不是 watch cursor。 | Slice 2 |
| Compactor typed options | DS F5 | Plan 指定 `CompactorExecutionBaseline` sub-object；不受 ordinary override 影响；Slice 2 负责把 opener typed fields 映射到内部 compactor wiring。 | Slice 1 / Slice 2 / Slice 6 |
| ToolRuntime policy typed shape | DS C2 | 复用 `HostToolingOptions` typed shape；若缺少 ToolRuntime policy typed fields，由 Slice 1 补齐，禁止 extra payload / service locator。 | Slice 1 |
| Gate state sync | DS F6, post-p10 checklist | 本轮只生成 plan artifact；implementation-control 状态由 Controller 后续 gate bookkeeping 更新。 | Controller |

## Unified Coverage Table

| Coverage | Owner slice | Test / smoke name | Public-path assertions | Skip condition | Follow-up owner |
| --- | --- | --- | --- | --- | --- |
| S1 real-runner no-tool multi-turn | Slice 6 | `tests/host/test_public_open_host_multiturn_smoke.py::test_real_runner_no_tool_two_turn_public_path` | `open_host`、`submit_followup(queue)`、pre-start governance allow、LocalProxy / real runner、memory catch-up、terminal `HostEvent.final_answer.content`；不读 internal EventLog / payload table。 | Provider secret / network unavailable：explicit skip with provider and secret ref。 | None if at least configured provider executes；all skipped risk reported to Controller。 |
| S1 multi-client watch / queue idempotency | Slice 3 + Slice 4 + Slice 6 | `test_two_watchers_observe_same_terminal_event`; `test_concurrent_queue_uses_client_request_id_idempotency` | 两个 watcher 独立观察同一 terminal event；两个不同 `client_request_id` 按 durable accepted order queue；同一 `(session_id, client_request_id)` 重放不重复建 Run。 | No provider skip for deterministic local runner support; real runner variant may skip by provider。 | None |
| S1 per-run execution override | Slice 3 + Slice 6 | `test_submit_followup_field_level_execution_override_freezes_effective_config` | 只传 `runner_options` 时 runner spec / policy 来自 opener baseline；只传 `runner_spec` 时其它字段来自 baseline；effective config freeze 可读 / 可诊断。 | None for unit/integration; real provider execution may skip。 | None |
| S1 WAITING public resume | Slice 5 | `tests/host/test_public_resolve_wait_resume.py::test_resolve_wait_resumes_through_open_host_and_terminal_event` | Run 进入 `WAITING` 后只调用 public `resolve_wait`；after-commit wakeup 自动 dispatch；terminal HostEvent 可见。 | None for mock waiting tool path。 | Callback / poller loop to later production integration owner。 |
| S1 steer / retry / replay controls | Slice 5 | `test_steer_running_run_creates_new_attempt_public_path`; `test_retry_failed_run_creates_related_run_public_path`; `test_replay_succeeded_run_no_tool_public_path` | 全部通过 public handle；事件 / `get_run` 可见；retry/replay source relation 正确；replay no-tool。 | None for deterministic local harness。 | `LOST` / `RECOVERING` variants to Phase 11。 |
| S2 mock-tool wiring | Slice 3 + Slice 6 | `tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_fact_enters_memory_and_next_run_input`; `test_tool_names_subset_and_empty_freeze` | ToolBundle 来自 opener；`tool_names` subset / empty semantics；ToolExecutor path；Host accept barrier；tool fact enters memory and next RunInputBuilder。Mock tool 只按参数机械返回。 | None。 | Real business tools to Phase 12 / Service integration。 |
| S3 real-runner matrix | Slice 6 | `tests/host/test_public_real_runner_matrix_smoke.py::{mimo,deepseek,gemini,qwen}` | 四类 runner 参数均走同一 `open_host` / `submit_followup` / `watch_session_events` terminal path；two-turn answer 非空或包含稳定 marker。 | Provider API key / endpoint / network unavailable per provider；must report reason。 | If all skipped, Controller decides residual acceptance。 |
| S4 compact real compactor | Slice 1 + Slice 2 + Slice 6 | `tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity` | small budget triggers proactive compact；real compactor adapter；canonical compact events and artifact；memory projection consumption；next run continuity marker；Slice 2 opener-to-internal compactor wiring 被覆盖。 | Compactor provider secret / network unavailable; explicit skip. Mock compactor cannot replace success signal。 | Provider-specific compactor hardening later if needed。 |
| S5 cancel accepted / queued / pre-dispatch | Slice 5 | `tests/host/test_public_cancel_smoke.py::test_cancel_accepted_and_queued_runs_public_path`; `test_pre_dispatch_cancel_visible_in_watch` | public cancel commands only；no internal dispatch row edits；`get_run` and `watch_session_events` see cancel。 | None。 | Active cancel watchdog to Phase 11。 |
| S5 active / session-scope cancel visibility | Slice 5 + Slice 6 | `test_active_cancel_emits_public_cancel_event`; `test_cancel_session_runs_scoped_to_session` | Shared active registry under opener；cancel event visible；session-scope cancel does not affect other Session。 | Long-running real runner active cancel may skip provider-specific assertion; deterministic worker path required。 | Phase 11 owns stuck active worker timeout。 |
| S5 close boundary | Slice 2 + Slice 5 | `tests/host/test_public_lifecycle_smoke.py::test_close_session_opener_close_and_cancel_are_distinct` | `close_session` rejects new input but keeps read/watch; opener close raises `HostClosedError` and writes no cancel facts; cancel writes cancel facts。 | None。 | Purge destructive cleanup to Phase 15。 |

## Implementation Slices

Slice dependency / sequencing 固定为：

```text
Slice 1 -> Slice 2 -> {Slice 3, Slice 4} -> Slice 5 -> Slice 6
```

- Slice 1 先冻结 public typed surface 和 package export boundary。
- Slice 2 只负责 production composition root、public async handle delegation、runtime lifecycle、after-commit wakeup、memory catch-up 与 compactor wiring。Slice 2 stop condition 可以使用当时代码库已有的 request shape 验证 `submit_followup(queue)` runtime wakeup，不要求提前迁移 `SubmitFollowupRequest` typed fields。
- Slice 3 再迁移 ordinary prompt request contract 到 `SubmitFollowupRequest` typed fields，并补齐 per-run effective config / tool set freeze。
- Slice 4 可在 Slice 2 runtime 与 Slice 3 request contract 就位后完成 session-level live `HostEvent` public stream；Slice 3 与 Slice 4 可按实现便利并行推进，但最终都必须在 Slice 5 前收敛。
- Slice 5 才实现 steer / retry / replay / resolve_wait / cancel public controls；Slice 2 不得为了预留 wakeup 而提前实现 steer、retry 或 replay 语义。
- Slice 6 只做 public-path smoke matrix、真实 runner / compactor validation、必要的窄修复和文档同步。

### Slice 1. Public Opener Types, Export Boundary And Options

Objective:
- Define `open_host(options)` public contract surface, `OpenHostOptions`, ordinary execution baseline, compactor execution baseline, public `HostEvent` terminal types, `HostClosedError`, and package export changes.

Allowed files / modules:
- `dayu/host/api.py`
- `dayu/host/__init__.py`
- New `dayu/host/open_host.py` or equivalent public opener module
- Narrow public validation helper modules under `dayu/host/`
- Tests under `tests/host/test_public_open_host_options.py`, `tests/host/test_package_exports.py`

Exact allowed changes:
- Add frozen slots dataclasses with full Chinese docstrings for `OpenHostOptions`, `OrdinaryRunExecutionBaseline`, `CompactorExecutionBaseline` or equivalent typed names.
- Ensure `HostToolingOptions` remains the typed construction-time tooling policy shape; if existing fields do not cover ToolRuntime policy, add explicit typed fields there instead of `extra payload` / service locator.
- Add public `HostClosedError` lifecycle exception.
- Add `Host` / `HostHandle` Protocol or concrete public handle type with async methods only.
- Add `open_host(options)` async context manager signature; implementation may be minimal but must validate options and route to Slice 2 composition root.
- Remove `start_run`, `create_host_command_handle`, `HostLocalExecutionOptions`, `HostEventView`, run-level `stream_run_events` from ordinary Service-facing package root exports. If low-level tests still need them, import from internal module path, not `dayu.host`.
- Keep `_start_run` internal; do not add compatibility re-export.

Non-goals:
- Do not implement scheduler runtime in this slice beyond typed construction path.
- Do not change Engine contracts.
- Do not introduce ConfigLoader or environment-derived defaults for required paths / runner fields.

State transitions / data flow:
- None beyond handle closed gate semantics.

Tests:
- Options validation rejects wrong Path / bool / numeric values, missing required runner / worker / compact root fields, and per-run fields incorrectly placed in options.
- Package export tests assert removed Service-facing symbols are no longer in `dayu.host.__all__`.
- Closed handle public methods raise `HostClosedError`, not command-level `INVALID_STATE`.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- Public type surface is frozen enough for Slice 2 to implement runtime without adding new Service-facing construction fields.

### Slice 2. Production Composition Root, Handle Lifecycle And Command Wakeup

Objective:
- Implement `open_host(options)` production wiring so Service no longer assembles command handle, scheduler, durable store, active registry, memory catch-up, ToolRuntime, compactor, stream fanout, or wakeup internals.

Allowed files / modules:
- `dayu/host/open_host.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/api.py`
- `dayu/host/read_api.py` only for public handle delegation if needed
- Existing internal runtime / scheduler modules under `dayu/host/`
- Tests under `tests/host/test_open_host_runtime.py`, `tests/host/test_public_lifecycle_smoke.py`

Exact allowed changes:
- Build internal `HostCommandHandleOptions` and internal `HostLocalExecutionOptions` from `OpenHostOptions`; these remain internal implementation details.
- Public async handle delegation ownership is Slice 2: `ensure_session`、`create_session`、`get_session`、`get_run` must be exposed as async wrapper / delegation methods on the public handle, with handle-open validation and no Service access to the internal command handle.
- Public handle wrapper / delegation for later public commands belongs to this same facade: `submit_followup`、`resolve_wait`、`retry_run`、`replay_run`、`cancel_run`、`cancel_session_runs`、`close_session` may delegate to internal command primitives, while Slice 3 / Slice 5 own the command semantics they introduce or complete.
- Create a shared `ActiveWorkerRegistry` for command handle and scheduler.
- Wire after-commit wakeup from mutating commands to scheduler / background supervisor.
- Wire memory projection catch-up and compactor baseline into dispatch path through existing `HostLocalExecutionOptions` or refined internal equivalent.
- Map `OpenHostOptions.compactor_baseline` to internal compactor fields: `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy_ref`、`compact_artifact_root` and compact artifact directory creation policy. If `compactor_baseline is None`, propagate the fail-closed "no compaction capability" state; do not install fake defaults.
- Implement idempotent `host.close()` and async context manager `__aexit__` with shutdown order: close public gate, stop scheduler / promotion / supervisor, close live watch fanout, cancel / close active worker tasks and lane waits, flush projection catch-up, close durable store.
- Do not write cancel / failed terminal facts during opener close unless a genuine terminal event has already been accepted by normal ingest.

Non-goals:
- Do not implement Recovery for active work left behind after opener close.
- Do not expose scheduler wakeup or dispatch control on public handle.
- Do not implement steer / retry / replay semantics or their special wakeup paths in this slice; Slice 2 proves only queue request wakeup using the current request shape.
- Do not implement Outbox drain.

State transitions / data flow:
- Mutating command -> durable transaction -> commit -> internal after-commit wakeup -> scheduler observes accepted / queued / resume / retry / replay work -> dispatch.
- Opener close affects only local runtime lifecycle, not Session / Run governance facts.

Tests:
- Public `submit_followup(queue)` through handle auto-wakes scheduler without test calling scheduler internals.
- `close_session != host.close != cancel`: closing Session does not stop runtime; opener close does not close Session; cancel writes cancel facts.
- Handle close is idempotent and post-close APIs raise `HostClosedError`.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- A deterministic no-tool local worker can complete one public `submit_followup(queue)` through `open_host` without manual scheduler wakeup.

### Slice 3. Public Request Contract, Effective Config And Tool Set Freeze

Objective:
- Migrate ordinary prompt request shape to `SubmitFollowupRequest` fields required by P10.5 and freeze per-run effective runner config / tool set at admission / dispatch boundaries.

Allowed files / modules:
- `dayu/host/api.py`
- `dayu/host/admission.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/schema.py` only if fresh-schema fields / refs are required
- `dayu/host/tool_runtime.py` / effective bundle builder modules only for selector wiring
- `dayu/host/run_input.py` only for consuming frozen refs
- Tests under `tests/host/test_submit_followup_public_contract.py`, `tests/host/test_per_run_tool_selection.py`, `tests/host/test_effective_execution_config.py`

Exact allowed changes:
- Add `system_prompt`, `user_prompt`, `tool_names`, optional `runner_spec`, `runner_options`, `agent_policy` to `SubmitFollowupRequest`, or replace old `HostInput` usage while preserving strict typed envelope semantics.
- Keep first prompt and follow-up prompt on the same `submit_followup(queue)` request path.
- Validate `tool_names` and freeze resolved effective business tool names / schema digest / source refs.
- Resolve field-level partial merge for runner spec / options / agent policy and freeze effective config refs.
- Ensure `FollowupSnapshot` exposes `accepted_run_id`, `accepted_run_status`, and command commit sequence / watermark; watermark is not watch cursor.
- Update low-level tests that previously used `start_run` to import internal `_start_run` only where they explicitly test admission primitive.

Non-goals:
- Do not accept raw `ToolBundle` in requests.
- Do not introduce profile registry or patch dict override.
- Do not preserve old request shape by compatibility wrapper; update tests to new boundary.

State transitions / data flow:
- `submit_followup(queue)` on open Session creates `ACCEPTED` or `QUEUED` Run with `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / optional `RUN_QUEUED`, freezes effective config and tool view refs, then commits and wakes scheduler.
- Unknown tool name fails before durable canonical facts.

Tests:
- `None=all`, empty=frozenset disables business tools, non-empty subset filters schema; unknown tool rejected.
- Field-level partial merge cases for each override field.
- Idempotent repeated `(session_id, client_request_id)` returns same accepted Run and same effective refs.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- Public request can express ordinary prompt, steer target, per-run tool subset, and field-level execution override without metadata / extra payload.

### Slice 4. Session-level Live Host Events And Terminal Final Answer View

Objective:
- Implement `watch_session_events(session_id) -> AsyncIterator[HostEvent]` as the ordinary Service event entry and demote run-level stream / `HostEventView` to internal diagnostic use.

Allowed files / modules:
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/read_api.py`
- `dayu/host/engine_ingest.py` only for terminal payload mapping if needed
- `dayu/host/durable/event_log.py` / payload reader internals only as source for projection, not public API
- Tests under `tests/host/test_watch_session_events.py`, `tests/host/test_public_host_event.py`

Exact allowed changes:
- Add `HostEvent`, `HostFinalAnswerView`, terminal event kind types with strict dataclasses / enums and Chinese docstrings.
- Build live fanout from committed EventLog / ingest path. The public event must be Host-owned typed view, not raw EngineEvent and not `HostEventView`.
- `watch_session_events` validates handle open, session existence / gone, and allows `Session CLOSED`.
- Terminal `SUCCEEDED` event contains inline final answer view; failed / cancelled terminal events contain typed terminal status and display-safe fields.
- Remove ordinary public docs / exports for `HostEventView` and `stream_run_events`; internal tests may still use internal import.
- If existing `HostEventStream` is present in `dayu.host` public exports, remove it from the Service-facing namespace. If retained at all, it may only be an internal type alias / Protocol equivalent to `AsyncIterator[HostEvent]`; it must not be a Service-facing context manager, subscription handle, or second public stream contract.

Non-goals:
- Do not implement Outbox concrete offline catch-up.
- Do not make terminal event end the iterator.
- Do not add `wait_final_answer`.

State transitions / data flow:
- EngineEvent ingest / terminal closeout -> canonical EventLog terminal facts -> live fanout maps to typed `HostEvent` -> Service renders final answer from terminal event.

Tests:
- Two watchers observe same terminal event and dedupe identity.
- Consumer early cancel does not cancel Run or write EventLog.
- `HostEventView` is not exported from `dayu.host`.
- Final answer smoke cannot read internal payload table.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- S1 can consume final answer exclusively through `watch_session_events`.

### Slice 5. Public Control Commands: Steer, Retry, Replay, Resolve Wait, Cancel

Objective:
- Make ordinary local control commands no longer stable unsupported under public opener, while keeping Recovery-only variants deferred.

Allowed files / modules:
- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/schema.py` only for fresh source relation / replay / retry refs if missing
- `dayu/host/dispatch.py`
- `dayu/host/run_input.py`
- `dayu/host/tool_runtime.py` only for replay no-tool defense / wait result reuse
- Tests under `tests/host/test_public_steer.py`, `tests/host/test_public_retry_replay.py`, `tests/host/test_public_resolve_wait_resume.py`, `tests/host/test_public_cancel_smoke.py`

Exact allowed changes:
- Implement `submit_followup(steer)` for active `RUNNING` / `WAITING` as design.md defines: same Run, new Attempt, terminal race handled by durable transaction order.
- Implement ordinary local `FAILED` retry: source Run immutable, associated new Run, new Attempt / execution id, idempotency by `(source_run_id, client_request_id)`, policy limit.
- Implement `SUCCEEDED` structure replay: associated new Run, no-tool request, repair instruction / rejected candidate context, no new tool facts, source EventLog truth unchanged.
- Ensure `resolve_wait(...)` under `open_host` wakes scheduler and resumes through new Attempt.
- Verify existing cancel commands under shared active registry and public event path; fill missing public opener wiring, not recovery watchdog.

Non-goals:
- Do not implement `LOST` / `RECOVERING` retry, startup recovery, positive orphan proof or stuck cancel watchdog.
- Do not create `interrupt_*` API.
- Do not execute tools during replay.
- Do not implement callback HTTP endpoint / poller loop.

State transitions / data flow:
- `steer RUNNING` -> append `STEER_REQUESTED`, close current Attempt as `STEERED`, create new Attempt / dispatch record, wake scheduler.
- `steer WAITING` -> append `STEER_REQUESTED`, cancel active wait record with reason `steered`, create new Attempt / dispatch record.
- `retry FAILED` -> append retry requested / source relation facts, create associated `ACCEPTED` Run, dispatch through same scheduler path.
- `replay SUCCEEDED` -> append replay requested / source relation facts, create associated `ACCEPTED` Run, build no-tool repair request.
- `resolve_wait WAITING` -> append `RESUME_REQUESTED` + tool terminal / result fact, create new Attempt / dispatch record.
- cancel paths remain governed by canonical cancel facts and public visibility.

Tests:
- Terminal race tests for steer vs terminal.
- Retry idempotency conflict and successful related Run dispatch.
- Replay no-tool schema assertion and source Run immutable assertion.
- WAITING resume public path.
- Cancel accepted / queued / pre-dispatch / active visibility / session-scope / close boundary.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_retry_replay.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_cancel_smoke.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- G6 / G7 / G8 / G9 / S5 local public control paths work through `open_host` and `watch_session_events` without dispatch internals.

### Slice 6. Public-path Smoke Matrix, Real Runner Matrix, Real Compactor Smoke And Docs

Objective:
- Prove P10.5 success signal across S1-S5 and synchronize Host / tests docs after implementation passes.

Allowed files / modules:
- Smoke tests under `tests/host/`
- Test support under `tests/host/` only, including real-runner and real-compactor smoke helpers
- Narrow `dayu/host` fixes only if smoke exposes public path bugs owned by Slice 1-5
- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/post-p10.md` only for phase closeout / final coverage status if Controller requests

Exact allowed changes:
- Add S1 real-runner no-tool two-turn smoke.
- Add S2 mock-tool wiring smoke with deterministic mock tool and no mock runner success signal.
- Add S3 provider matrix smoke for mimo、ds/deepseek、gemini、qwen using hardcoded runner parameters from `dayu/config/llm_models.json` or equivalent controlled test config.
- Add S4 compact smoke using explicit real compactor adapter, not `FakeContextCompactor`.
- Add S5 cancel and close boundary smoke.
- Add validation reporting / pytest skip reasons for provider and compactor unavailable cases.
- Update README only after tests pass and only in their fixed responsibilities.

Non-goals:
- Do not hide real runner failures behind broad skip if required env exists.
- Do not let mock runner / runner test double count as P10.5 success signal.
- Do not write future design in README.

State transitions / data flow:
- All smoke runs must enter through `open_host(options)`, use public handle methods, observe terminal through `watch_session_events`, and avoid internal durable table reads for correctness assertions.

Tests:
- See unified coverage table.

Validation commands:
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_public_cancel_smoke.py -q`
- `source .venv/bin/activate && pytest tests/host/test_public_real_runner_matrix_smoke.py -q`
- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

Stop condition:
- Coverage table can be marked covered / not covered but accepted with evidence; no blocking gap remains for P10.5 exit.

## Docs Decision

Implementation completion must update docs after tests / pyright pass:

- `dayu/host/README.md`：Host developer manual public contract, `open_host(options)`, public handle methods, live watch, terminal final answer view, close / cancel / close_session boundary, internal demotion of `start_run` / `create_host_command_handle` / `HostEventView` / run-level stream.
- `tests/README.md`：P10.5 public-path smoke layers, real-runner skip rules, mock-tool vs mock-runner boundary, compact smoke provider gating.
- `docs/host/post-p10.md`：only if Controller requests phase closeout / coverage status or if implementation discovers a public contract issue that must be written back. Do not mechanically rewrite discussion history.

Root `README.md` is not triggered unless implementation changes project-level user commands, CLI entrypoints, config entrypoints, trace/render entrypoints or public usage workflows outside Host developer docs.

## Validation

Every implementation slice must run affected tests and pyright after `source .venv/bin/activate`:

```bash
source .venv/bin/activate && pytest <affected-tests> -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Final P10.5 validation:

```bash
source .venv/bin/activate && pytest tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Smoke skip rules:

- S3 provider smoke may skip per provider only when required API key / secret ref / endpoint / network is unavailable; skip reason must name provider and missing env / network condition.
- S4 real compactor smoke may skip only when compactor provider secret / endpoint / network is unavailable; mock / fake compactor cannot replace success signal.
- S1 / S2 / S5 deterministic public-path tests must not be skipped for provider unavailability.
- If all real-runner providers or the real compactor are skipped in a validation run, final report must flag residual risk and owner for Controller acceptance.

## Blocking Questions For Controller

当前没有必须阻塞 implementation-ready plan 的 material open question。

Implementation agent 必须停下并交 Controller 裁决的触发条件：

- 需要新增或改变本计划未列出的 Service-facing public API。
- 需要新增 `HostApiErrorCode` 或改变 closed-handle error public contract。
- 需要改变 Run / Attempt / EventLog 状态机、fresh schema、持久化 truth 表达或 terminal final answer path。
- 需要让 Engine 理解 Host 状态或让 Service 手工装配 Host internals。
- 真实 compactor adapter 必须放入 production `dayu.host` provider-specific module 才能完成 smoke，且该选择会改变 Host 与 Engine / provider 的依赖边界。
- S3 / S4 在目标环境长期全部 skip，导致 P10.5 success signal无法提供真实 runner / compactor 证据。

## Residual Risks And Owners

- Real runner matrix 依赖外部 provider secret / network。Owner：Slice 6 validation；若全 skip，Controller 决定是否接受 residual risk。
- Real compactor smoke 依赖真实 compactor adapter / provider。Owner：Slice 6；如果只能使用 fake compactor，不能认定 S4 covered。
- Active worker cancel watchdog、stuck `CANCELLING`、crash recovery、positive orphan proof。Owner：Phase 11。
- ToolsDiscovery / ScenePrepare、真实业务工具注册和动态场景。Owner：Phase 12。
- Outbox concrete read / drain、offline terminal delivery、Audit / Tool Trace。Owner：Phase 13。
- RemoteProxy / remote execution。Owner：Phase 14。
- Purge / retention destructive cleanup。Owner：Phase 15。
