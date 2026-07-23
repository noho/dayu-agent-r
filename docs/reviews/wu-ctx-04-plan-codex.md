# WU-CTX-04 code-generation-ready implementation plan（AgentCodex）

## 0. Plan gate metadata

- Work unit：`WU-CTX-04 Per-Session Attachment Ownership and Proactive Governance Single-operation Boundary`
- Issue：GitHub Issue #112；Issue 正文仅作为历史输入，不作为本计划的 scope 或设计真源。
- 类型：architecture-sensitive issue work unit。
- 当前 gate：second targeted plan fix；本产物只修正总控在 re-review 后接受的 `PRR-001` 与 `PRR-002`，不实施代码、不修改 design/control/README/生产代码/测试，也不重新打开首轮已闭合 finding。
- 设计真源：`docs/host/design.md`，重点为 Section 9 `Session attachment access ownership`、Section 25 `Context Governance`、Section 27 `Host Lifecycle / Recovery` 及 cancel contract。
- 控制真源：`docs/host/issues-implementation-control.md` 的 Slice 切分原则和 WU-CTX-04 全节。
- 代码基线：branch `feat/wu-ctx-04`，HEAD `974f9e1686f6e26f96830cd3478edc9d0d686c45`。
- preflight：分支不是受保护分支；第二轮fix开始时已有总控修改的`docs/host/issues-implementation-control.md`及首轮/re-review相关未跟踪artifacts，均视为既存状态并以起始hash保护，不纳入本agent changed files。
- goal confirmation：控制文档已记录用户于 2026-07-22 确认目标、非目标、scope boundary 与验收信号；没有重新打开 goal confirmation。
- 本轮允许写入：修订本文件，并新建 `docs/reviews/wu-ctx-04-plan-re-review-fix-codex.md` 记录第二轮 finding 映射；首轮 fix artifact `docs/reviews/wu-ctx-04-plan-fix-codex.md` 保持不变，除此以外不写入。

## 1. Goal、motivation 与 success signal

### 1.1 Goal

建立一个 public、显式可关闭、mode 在 attachment 生命周期内不可变的 `HostSessionAttachment`。Host Session attachment registry 是 `READ_WRITE` / `READ_ONLY` access truth 的唯一 owner；strict-native per-Session mutex 只负责共享同一 durable store 的多个 opener 之间的机械互斥。所有用户发起的 Session mutation、target-Session recovery、accepted wake、pre-start governance、proactive compaction、queue promotion 与新 Attempt/new dispatch 创建都必须消费同一 registry access truth。

同时完成三个同源收敛：

1. `open_host(...)` 只打开 runtime，不再 workspace-wide startup recovery；fresh `READ_WRITE` attach 在返回前执行 target-Session bounded recovery，`READ_ONLY` attach 不推进治理。
2. 删除 `max_proactive_compactions_per_run` 全配置面，把同一 Run/input snapshot 最多一个 proactive durable operation 及 incomplete-operation recovery 固化为 Host 状态机；恢复必须复用原 operation id、原 input cursor 与剩余 semantic attempt budget。
3. cancel 只复用 attachment access truth；durable cancel commit 后，`dispatch_record.owner_host_instance_id` 对应的 Attempt execution scheduler 在有界轮询内把取消作用到自己的 local worker，caller registry 命中仅为低延迟 fast path。

### 1.2 Motivation

当前问题不是“SQLite 缺少事务锁”，也不是“单个 scheduler 内 promotion 队列不串行”。SQLite 已拥有 durable transaction/CAS，单个 `HostDispatchScheduler` 也以一个 `_promotion_drain_task` 串行消费 promotion；真正缺失的是跨 `open_host(...)` opener 的 Session 级新工作资格 owner。该 owner 缺失后，workspace-wide startup recovery 和另一个 opener 的 accepted replay wake 可以让两个 scheduler 对同一 Session、同一 Run/input snapshot 分别进入事务外 proactive compaction；现有可配置 count 又把本应唯一的 operation 错建模为 operator policy。

单纯把 count 改为 1 会把 loser 错误收口为 `proactive_compact_limit_reached`；只加进程内锁覆盖不了第二个 opener；workspace-wide single writer 会错误阻塞不同 Session 并行；EventLog lock、lease/fence 或 proxy 都在解决不存在的远端 owner/takeover 问题。因此必须在 Host registry 的 Session access owner boundary 修复。

### 1.3 Success signal

完成实现 gate 后必须同时成立：

- 两个真实 public `open_host` 共享同一 SQLite、attach 同一 Session：只有一个 `READ_WRITE`，另一个 `READ_ONLY`；不同 Session 可同时 `READ_WRITE`。
- 同一 public Host handle 对同一 Session 同时只能有一个 live attachment（不区分 RW/RO）；重复 attach 在任何 native acquire 前以 typed conflict 失败。共享同一 runtime 的 lifecycle owner 复用这个唯一 attachment；需要独立竞争的 caller 必须独立 `open_host(...)`。
- `READ_ONLY` opener 的 submit/steer/retry/replay/cancel/session close/Outbox drain 在 actor write、EventLog append、scheduler wake 与 provider call之前收到 typed rejection；durable read、Outbox read和 event observation仍可用。
- detach 先关闭新命令入口并 drain 已进入 actor 的 mutation 和尚未形成 stable Attempt owner 的 pre-start work；existing Attempt 继续由原 execution owner 管理；mutex 最后释放。
- Host close 使用独立于单 attachment close 的强顺序：在所有 attachment mutex 仍持有时完成 scheduler lifecycle close、active worker token/`on_cancel(...)` 传播、本地 worker/task/lane 清理与 host instance `STOPPING -> STOPPED` 收口；只有该 barrier 完成后才释放 mutex/attachment record。scheduler close 前的第二 opener 只能得到 `READ_ONLY`，release 后的 fresh `READ_WRITE` 必须在同一次 target recovery 看到旧 owner `STOPPED` 并推进恢复。
- 旧 `READ_ONLY` attachment 永不升级；close 后 fresh attach 才重新竞争，且并发 fresh attach 仍只有一个 `READ_WRITE`。
- `open_host` 本身不恢复任何 Session；fresh `READ_WRITE` attach 只扫描目标 Session，fixed now、fixed target watermark、64-row keyset pages、page commit 后 wake；任一失败不返回 writable attachment。
- 重复 accepted wake、startup overlap 和重复 public admission replay 对同一 Run/input snapshot最多形成一个 proactive request/operation/provider execution chain。
- incomplete proactive operation 在进程 crash 后以原 operation id 恢复剩余 attempts，或以同一 operation id 确定性 fail/fallback；不追加第二个 request，不产生 count-limit failure。
- B fresh `READ_WRITE` 可 cancel A 提交且仍由 A worker 执行的 Run；A scheduler 在 `dispatch_poll_interval_seconds` 的一个轮询周期加一次 durable retry 上界内观察 cancel truth 并传播到 worker。
- partial allocation、attach caller cancellation、attachment repeated/concurrent close、Host close 和 opener process exit 均不泄漏 mutex/eligibility。
- production interval loop 与测试直接调用同一个 one-shot owned-session reconciliation step；确定性测试不以 wall-clock sleep 证明 liveness。
- strict-native backend 不支持或系统调用错误时 fail closed；busy 只有 `READ_ONLY` 这一种解释，不存在 soft fallback。
- 旧配置字段被 packaged/workspace strict schema 拒绝，生产代码、配置、活跃测试和 README 中 stale grep 为零；reactive count 和 per-operation semantic attempt budget 行为不变。
- reactive request 同步写入与 request event id 同源的 operation id 和同一 policy snapshot 的 semantic attempt 上界；`engine_ingest` 的首次 reactive operation 只机械适配为 `first_attempt_number=1`、`max_attempt_number=<同一 snapshot>`，既有 reactive count、overflow、recovery 与 fallback 行为不变。
- 所有修改/新增函数具备完整中文 docstring，pyright 全量通过；每个受影响生产 `.py` 文件覆盖率 `>=80%`。

## 2. First-principles judgment 与直接代码证据

### 2.1 判断结论

动机成立，且 architecture-sensitive 严重性没有被高估。当前 durable CAS 能限制部分最终状态竞争，但不能阻止两个 scheduler 在短事务之间各自启动外部 compactor/provider side effect；因此“最终某次 CAS 失败”不能替代 operation 唯一性。access truth、外部副作用准入与恢复入口分散，属于 owner boundary 缺失，而不是一个局部条件判断错误。

Issue #112 的历史正文不应用来推导当前方案。设计文档、控制文档和以下最新代码共同给出直接证据：

| 直接代码证据 | 当前事实 | 对计划的约束 |
| --- | --- | --- |
| `dayu/host/open_host.py::_OpenHostContextManager.__aenter__` | 每个 opener 都建立自己的 scheduler，立即调用全局 `tick_active_cancel_watchdog(...)`，随后通过 `_StartupRecoveryActorOperation` 执行 workspace-wide recovery。 | `open_host` 必须删除这两个 workspace-wide startup side effect；恢复只能由 fresh RW attachment 触发。 |
| `dayu/host/open_host.py::_PublicHostHandle` | public `Host` 没有 `attach_session` 或 registry；submit/retry/replay 走 `_invoke_new_work`，cancel/session close直接 actor call。 | 新 access truth 必须进入 public handle 的所有 Session mutation call path，不能只修 submit。 |
| `dayu/host/open_host.py::_PublicHostHandle._close_owned_resources` | 当前 Host close 是 health gate → wait poller → actor drain → `scheduler.close()` →其余 owner；未来插入 attachment registry 时，如果在 scheduler 前释放 mutex，会让 fresh attach 的 one-shot recovery看见旧owner仍在运行。 | Host-close 专用 registry release 必须后移到完整 scheduler lifecycle close 之后；单 attachment close顺序不变。 |
| `dayu/host/_durable_actor.py::DurableActor.call/submit` | `call()` shield caller cancellation；caller 被取消后 actor Future 仍继续 commit/after-commit wake。 | attachment command lease必须绑定底层 actor Future；attach recovery 被取消时也必须等底层 Future 收口后才能释放 mutex。 |
| `dayu/host/dispatch.py::HostDispatchScheduler.wake_queue_promotion/run_queue_promotion` | 每个 scheduler 有自己的 promotion queue；`run_queue_promotion` 无 Session eligibility 依赖，直接进入 `_run_pre_start_governance` 并可创建 Attempt。 | gate 必须在 wake 接受和实际执行两处复核；所有 pre-start/new Attempt 创建都必须持有 registry work lease。 |
| `dayu/host/dispatch.py::_promotion_drain_loop` | 同一个 scheduler 内部串行 await promotion。 | mutex+registry排除跨 opener eligible scheduler 后，不再新增 compaction fence/operation mutex。 |
| `dayu/host/dispatch.py::HostDispatchScheduler.close` | close 入口才标记 host instance `STOPPING`，随后停止 heartbeat/drain/promotion/watchdog、`active_registry.cancel_all(...)` 传播 token 与 `LocalWorkerHandle.on_cancel(...)`、取消 active tasks、关闭 handle/lane，末尾才标记 `STOPPED`；当前普通 cleanup 异常还会把 `_close_cleanup_done` 标为真。 | 该方法的成功完成必须成为 Host unlock barrier；mandatory cleanup/`STOPPED` 未完成时不得把 scheduler 或 attachment 宣称安全关闭，必须保留 mutex/record并允许重试。 |
| `dayu/host/dispatch.py::_run_pre_start_governance` | 先 count proactive request，再按 `policy.max_proactive_compactions_per_run` 判限；已有 request 时可走 `proactive_compact_limit_reached`。 | 删除 count helper、limit branch和配置字段；改为读取 typed durable operation phase。 |
| `dayu/host/dispatch.py::_execute_proactive_compaction` | root call 使用 policy attempt budget，但 tier 1-3 各自再次以 `max_attempts=1` 调用，实际没有共享同一 operation 总预算。 | 用全局 attempt number/upper bound贯穿 root与tier；恢复也消费同一 frozen budget。 |
| `dayu/host/compaction_operation.py::run_compaction_operation` | proposal attempt 永远从 1 开始；manifest 在 provider call 前 durable 写入。 | 增加显式 first/max attempt number；prepared manifest保守消耗 crash 前的 attempt，不能从 1 重放。 |
| `dayu/host/engine_ingest.py::_start_reactive_context_recovery/_append_reactive_compaction_requested_event/_execute_reactive_compaction` | reactive request由同一 transaction创建并把 policy 存入 pending，但 requested payload尚无operation id/frozen attempt budget；事务外执行仍调用 `run_compaction_operation(max_attempts=...)`，且从 ingestor policy再次读取预算。 | `engine_ingest.py` 必须纳入 Slice 2；只预生成request event/operation id、写入pending policy同源budget snapshot，并机械传required first/max range，不改count/overflow/recovery/fallback。 |
| `dayu/host/llm_compaction.py::LLMContextCompactor.run_prepared_compactor_proposal` | `_run_agent_request(..., timeout_seconds=RunnerSpec.default_timeout_seconds)` 以 `asyncio.wait_for` 包住完整 agent request；timeout后写入本attempt cancellation token。 | 首轮plan的pre-start有界等待证据有效；`DS-RRN-01`不保留为风险，仍保留“发现其它绕过路径则阻塞”的实施守卫。 |
| `dayu/host/context_events.py::build_context_compaction_requested_payload` | requested payload没有显式 operation id和 frozen semantic attempt budget；operation id仅由调用方约定为 request event id。 | request schema必须自足记录 `operation_id` 和 `max_compaction_attempts_per_operation` snapshot，并验证 event id同源。 |
| `dayu/host/_runner_call_manifest.py::RunnerCallCompactorIdentity` | 已 durable 保存 operation id、attempt number、request digest和input projection ref，并有严格 typed parser。 | 复用现有 manifest truth恢复已消耗 attempt，不新增 retry-count table/字段。 |
| `dayu/host/recovery.py::StartupRecoveryScanner` | 读取全 workspace non-terminal watermark/page；ACCEPTED/QUEUED产生当前 opener wake。 | scanner改名并强制 `session_id`；durable state query也必须 target scoped。 |
| `dayu/host/recovery_process.py::classify_orphan_candidate` | owner status为`STOPPED`时无需process probe即可返回positive orphan proof；`STOPPING`且heartbeat新鲜时仍判定live。 | Host close必须在unlock前完成`STOPPED`，否则fresh target recovery不能安全推进旧Attempt；classifier本身无需修改。 |
| `dayu/host/durable/state.py::read_non_terminal_run_upper_watermark/read_non_terminal_runs_keyset_page` | 两个 query均没有 Session filter；现有 `host_runs_session_status`/FIFO indexes已支持 Session scoped读取。 | 只改 query contract，不增加 durable table/index或 migration。 |
| `dayu/host/command.py::_propagate_active_cancel_targets` | durable cancel之后只调用 caller的 local `active_registry.cancel(...)`；miss被忽略。 | caller fast path保留，但 execution owner scheduler必须独立轮询 durable cancel link并传播。 |
| `dayu/host/dispatch.py::ActiveWorkerRegistry` | registry只有 register/unregister/cancel/cancel_all，没有 typed snapshot。 | 增加只读 exact identity snapshot，供 owner scheduler bounded reconcile；不暴露 worker handle。 |
| `dayu/host/dispatch.py::tick_active_cancel_watchdog` | 当前扫描全 workspace `CANCELLING`；watchdog loop周期性全局执行。 | 替换为 target-session attach/caller tick与exact locally-owned worker tick；取消无 attachment 的 workspace-wide推进。 |
| `dayu/runtime/filelock.py` | 基于第三方 `filelock.FileLock`，服务普通文件短临界区并带其 fallback语义。 | 不复用/扩写为 attachment mutex；新增 stdlib-only strict-native primitive。 |
| `dayu/runtime/config_loader.py::ContextBudgetConfig`、`dayu/host/context_policy.py::ContextBudgetPolicy`、`dayu/service/host_assembly.py`、`dayu/config/execution_profiles.json` | operation count贯穿 config→typed config→Host policy→assembly，四个 packaged profile值为 2，而 Host fallback为 1。 | 删除完整字段链，不做 alias/default/compat parser。 |
| `dayu/service/entrypoint_runtime.py` 与 `dayu/cli/session_execution.py` | watcher在 submit/cancel前打开，但 watcher不拥有写权限；prompt/interactive目前没有 attachment生命周期。 | watcher保持 observation owner；CLI execution lifecycle显式持有 attachment，Service不代理或重新推断access。 |

### 2.2 Root cause 同源结论

root cause 的逻辑与数据同源于：每个 execution-capable opener各有 scheduler，但没有 Host-owned per-Session eligibility registry；proactive uniqueness又被 count policy替代。mutex本身不是 root owner，它只让两个 registry实例对同一 canonical store/session key得到互斥的机械结果。所有授权判断必须来自 registry的 live record，而不是文件是否存在、Run origin、watcher、日志、时间戳或 scheduler-local偶然状态。

## 3. Scope boundary 与 non-goals

### 3.1 In scope

- public `HostSessionAttachment`、不可变 mode、typed mutation rejection、显式 `aclose()`。
- Host-owned attachment registry、per-attachment lifecycle、command/work lease与Host close清理。
- layer-neutral strict-native per-Session mutex primitive与Host canonical key派生。
- 所有 public Session mutation gate；Run-id mutation先做immutable Run→Session read，再gate。
- scheduler accepted wake、periodic reconciliation、pre-start governance、promotion和新 Attempt/new dispatch eligibility。
- fresh RW target-session recovery、target cancel tick、bounded pagination和失败清理。
- proactive operation typed state reader、request schema snapshot、same-operation crash resume/fail/fallback。
- `dayu/host/engine_ingest.py` reactive request新schema与 `run_compaction_operation` required first/max attempt range机械适配；预算来自 request时同一policy snapshot。
- 删除 proactive operation count的 config/public/assembly/test/docs 全链。
- execution owner cancellation reconcile与caller fast path。
- CLI prompt/interactive及headless/script/test harness direct Host caller attachment生命周期、Service不代持/不推断、Host/UI docs与测试矩阵。

### 3.2 Explicit non-goals

- 不建立 workspace-wide single writer，不把第二个 `open_host` 整体设为 read-only。
- 不做 existing RO attachment自动 promotion、leader election、通知或live handoff。
- 不引入 lease、TTL、heartbeat takeover、generation、epoch或fence。
- 不把mutex作为EventLog lock、durable owner、orphan proof或Attempt takeover proof。
- 不持久化/转发transient delta，不做跨进程command/event proxy。
- 不修改compact artifact内容寻址/不可变存储语义。
- 不在dispatch或engine_ingest单侧添加仅覆盖一个进程的普通lock。
- 不增加新的proactive operation count、retry-count table或替代配置。
- 不改写reactive compaction pipeline；只在 `engine_ingest.py` 的request producer与唯一 `run_compaction_operation` caller完成新required schema/signature机械适配，并保留既有operation count、overflow、recovery、fallback与dispatch语义。
- 不改变 `resolve_wait`、terminal ingest、existing Attempt execution、wait continuation等durable continuation的attachment授权。
- 不用 `dayu.runtime.filelock` 或 marker存在性冒充strict-native mutex。
- 不给 `open_host_admin` 的纯durable管理命令套Session attachment；其既有closed-session/purge前置仍由admin contract拥有。

## 4. Design alignment 与 semantic owners

| 语义 | 唯一 owner | 产生/校验/释放边界 | 禁止的下游补偿 |
| --- | --- | --- | --- |
| attachment mode与liveness | `HostSessionAttachmentRegistry` | native acquire结果进入pending record；RW recovery成功后activate；单attachment drain后release；Host close只消费scheduler lifecycle成功barrier后release | public facade、CLI、watcher、scheduler不得从文件/事件/origin反推 |
| 跨opener机械互斥 | `dayu.runtime.native_mutex` | canonical lock path上的nonblocking native OS lock；handle close/process exit释放 | runtime不得知道Session/Host；Host不得把token写durable state |
| user mutation authorization | registry mutation lease | actor submit前检查live ACTIVE RW；lease绑定actor Future | command函数内部fallback、默认允许、RO后置回滚均禁止 |
| new Session work eligibility | 同一registry work lease | wake先筛选，实际governance再次持lease；stable Attempt创建后才可释放 | scheduler-local bool/in-memory lock不得成为第二真源 |
| Host execution owner quiescence | `HostDispatchScheduler.close` + host instance liveness owner | mutex仍持有时停止background/promotion、传播worker lifecycle cancel、关闭task/handle/lane并提交`STOPPING -> STOPPED`；成功结果授权registry release | registry不得从`_closed`、日志或部分cleanup推断scheduler已停止；cleanup失败不得release |
| Run/Attempt durable truth | SQLite state/EventLog/transition owner | 原有transaction/CAS/state machine | mutex availability不得替代positive orphan proof或takeover |
| target recovery classification | attachment recovery scanner + durable state owner | RW attach后、return前、target-only fixed-watermark scan | projection/memory/outbox/watcher不得参与分类 |
| proactive operation identity/phase | Host context event contract + `proactive_compaction` typed reader | request event id与payload operation id同源；terminal与manifest严格归并 | count helper、字符串grep、第二request或downstream fallback禁止 |
| semantic attempt budget | request时冻结的 `max_compaction_attempts_per_operation` + proposal manifest attempts | manifest在call前占用全局attempt number；root/tier/recovery共享上界 | Runner transport `max_retries`不得计入；不能每tier重置 |
| cancel acceptance | 原有Host command transaction | live RW gate后按既有幂等/CAS写durable cancel | 不比较originating/admitting opener |
| physical cancel propagation | exact Attempt execution owner scheduler | local worker snapshot对durable cancel truth周期reconcile | caller registry命中、watchdog closeout不能作为correctness前提 |
| observation与transient delta | Session Event Delivery/Outbox各自owner | watcher不授予access；跨opener只读durable reconciliation | 不把watch称作attachment owner，不转发transient delta |

`dayu.runtime` 只依赖stdlib和更低层公共契约，不import Host/Engine/Service/UI/Fins。Host传给runtime的只有lock path；canonical store identity和Session key派生属于Host registry。该边界保证mutex不是业务 owner。

## 5. Target public contract、interfaces 与 schemas

### 5.1 Public Host API

在 `dayu/host/api.py` 定义并由 `dayu/host/__init__.py` 正式导出：

```python
class HostSessionAccessMode(StrEnum):
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"

class HostSessionMutationRejectionReason(StrEnum):
    ATTACHMENT_REQUIRED = "attachment_required"
    READ_ONLY = "read_only"
    ATTACHMENT_CLOSING = "attachment_closing"

class HostSessionAttachmentConflictReason(StrEnum):
    ALREADY_ATTACHED = "already_attached"

@dataclass(frozen=True, slots=True)
class HostSessionMutationErrorDetail:
    kind: Literal["session_mutation_access"]
    session_id: str
    reason: HostSessionMutationRejectionReason
    required_mode: HostSessionAccessMode
    actual_mode: HostSessionAccessMode | None

@dataclass(frozen=True, slots=True)
class HostSessionAttachmentConflictDetail:
    kind: Literal["session_attachment_conflict"]
    session_id: str
    reason: HostSessionAttachmentConflictReason

class HostSessionAttachment(Protocol):
    @property
    def session_id(self) -> str: ...

    @property
    def access_mode(self) -> HostSessionAccessMode: ...

    async def aclose(self) -> None: ...
```

两个 detail 都加入 `HostApiErrorDetail` closed union。mutation access 拒绝统一使用既有 `HostApiErrorCode.PERMISSION_DENIED`、`retryable=False`；重复 attachment 使用 `HostApiErrorCode.CONFLICT`、`retryable=False` 与精确 `HostSessionAttachmentConflictDetail`，二者均提供业务可读 message。`Host` Protocol新增：

```python
async def attach_session(self, session_id: str) -> HostSessionAttachment: ...
```

不把attachment对象传入每个command；capability是“当前Host handle对该Session是否存在live ACTIVE RW attachment”。这使调用方不能伪造attachment/mode，access truth仍只由registry产生。

同一 public Host handle 与同一 Session 在 `RECOVERING | ACTIVE | CLOSING` 的全集上只能有一个 live public attachment record，不区分该 record 是 RW 还是 RO。`attach_session(session_id)` 必须先在 registry 内原子检查该 key；若已有 live record，立即返回上述 typed conflict，且不得调用 `try_acquire_strict_native_mutex`、不得创建第二个 RO/RW 对象、不得重跑 recovery。只有原 attachment 完成 `CLOSED` 并从 live index 移除后，fresh attach 才能重新竞争。共享同一 Host runtime 的 UI/Service 组合、脚本 helper 或测试 helper 必须由一个明确 lifecycle owner 持有并复用这一个 attachment；若两个独立 caller 要表达真实竞争，必须各自使用独立 `open_host(...)` handle。RO对象本身不授予mutation权限，也不在原对象上升级。

### 5.2 Mutation classification

必须gate：

- `submit_followup`（queue和steer）
- `retry_run`
- `replay_run`
- `cancel_run`
- `cancel_session_runs`
- `close_session`
- `drain_outbox_terminal_items`（它会改变delivery durable state，不属于RO read）

不gate：

- `ensure_session` / `create_session`：attachment建立前的Session allocation/slot binding owner。
- `get_session` / `get_run` / `read_outbox_terminal_items` / `watch_session_events`：read/observation。
- `resolve_wait`：已存在durable wait的background continuation，不是UI新Session mutation。
- Engine terminal ingest、wait poll、projection/outbox producer、existing Attempt continuation：沿用各自durable owner。
- HostAdmin命令：保持独立admin contract。

Run-id mutation先通过actor执行只读 `_read_run_session_id(...)`，得到immutable `Run.session_id`；再向registry申请mutation lease，最后submit真正mutation Future。只读解析失败返回既有NOT_FOUND/typed error；不得把run id、origin opener或caller registry当授权依据。

### 5.3 Strict-native runtime primitive

新增 `dayu/runtime/native_mutex.py`：

- `StrictNativeMutexUnavailableError(RuntimeError)`：unsupported platform/backend、open/truncate/native syscall或release错误；绝不降级。
- `StrictNativeMutexHandle`：持有唯一OS handle/file descriptor，`close()`幂等；class/module/function均有完整中文docstring。
- `try_acquire_strict_native_mutex(path: Path) -> StrictNativeMutexHandle | None`：
  - POSIX：独立open file description + `fcntl.flock(fd, LOCK_EX | LOCK_NB)`。
  - Windows：确保lock file至少1 byte，使用 `msvcrt.locking(..., LK_NBLCK, 1)`，handle生命周期覆盖锁生命周期。
  - 只有明确的“would block/lock violation”映射为 `None`；其它errno/OS error均raise unavailable。
  - 任一partial allocation失败先关闭已分配fd/handle；lock file存在不代表owner，永不读取marker内容。
  - process exit依赖OS释放native handle，不写TTL/heartbeat/epoch。

`dayu/runtime/__init__.py` 只更新层中立能力概览，不从包根re-export符号。runtime import-boundary测试必须显式覆盖新模块。

Host registry使用已经打开且存在的SQLite真实路径：`db_path.resolve(strict=True)` 加 `os.path.normcase(...)` 作为canonical store identity；mutex目录位于resolved DB同目录的私有固定子目录，文件名为 `sha256(canonical_store_identity + "\0" + session_id)`，不暴露raw Session id。runtime只看到最终 `Path`。

### 5.4 Attachment registry 与 lifecycle state machine

新增 `dayu/host/session_attachment.py`，核心类型：

- `HostSessionAttachmentRegistry`：唯一access owner，仅在opener event loop使用。
- `_HostSessionAttachmentImpl`：public Protocol的内部实现，property只读。
- `_AttachmentAllocation`：attach factory的短生命周期resource token；不是public builder。
- `_AttachmentLifecycleState = RECOVERING | ACTIVE | CLOSING | CLOSED`。
- `SessionWorkLease`：registry计数lease，支持幂等 `release()` 与 `release_when_done(future)`。
- `SessionNewWorkAccessPort`：scheduler只读消费的窄typed protocol；production唯一实现为registry，测试fake必须显式传入，scheduler没有默认allow-all。

状态迁移：

```text
validate Session exists (durable read; no mutex yet)
  -> registry preflight: existing live record -> typed CONFLICT (stop; no native acquire)
  -> native try_acquire
       busy -> create ACTIVE READ_ONLY record -> successful return
       acquired -> create RECOVERING READ_WRITE allocation
           -> target cancel tick + target recovery pages + commit-after wakes
              success -> ACTIVE -> successful return
              failure/caller cancellation -> CLOSING -> drain -> release native handle -> CLOSED -> raise

ACTIVE READ_WRITE
  -> attachment aclose marks CLOSING atomically
  -> close new-work gate: reject attach/mutation/wake/new work leases
  -> await this attachment's actor-bound mutation leases
  -> await this attachment's pre-start/new-work leases
  -> release native mutex
  -> CLOSED

Host close
  -> marks every live attachment CLOSING and closes all new-work gates
  -> drains actor/mutation/pre-start leases but keeps every native mutex held
  -> completes scheduler lifecycle close and durable owner STOPPED proof
  -> only then releases native mutexes and removes attachment records
```

关键决策：

- RECOVERING record不向public mutation gate暴露RW；只允许本次target recovery产生的scheduler reconciliation消费new-work lease。
- mode值在对象构造时冻结；RO owner释放后registry不改对象字段、不发promotion通知。
- repeated/concurrent `aclose()`共享一个内部close task；caller取消只取消等待，close task继续并由Host close可join，防止mutex泄漏。
- attachment close不是`close_session`、不写EventLog、不cancel Run。
- existing stable Attempt/dispatch不计入attachment work lease；因此detach不等待其terminal。lease覆盖到Attempt+dispatch record在同一事务稳定创建或pre-start operation terminal/fallback完成为止。
- 单个 attachment close 不关闭整个 durable actor；它在 registry 原子进入 `CLOSING` 后依次等待本 attachment 已接受且绑定底层 actor Future 的 mutation lease、再等待本 attachment 已开始的 pre-start/new-work lease。scheduler 和 actor 在这两段 drain 期间保持可用；native mutex 只在两类 lease 都归零后释放，最后标记 `CLOSED` 并从 live index 删除。
- Host close是专用的全handle关闭协议，不复用“单 attachment drain后立即release”的末段。顺序固定且不得交换：① health gate `begin_closing` 与 registry `begin_host_close` 共同关闭所有 public/new-work入口（含attach、mutation、wake、periodic one-shot新lease），把live attachment置为`CLOSING`；② 停止wait poller，阻止新的background continuation source；③ `durable_actor.stop_and_drain()`，使此前接受的command、commit与after-commit wake bridge在scheduler仍存活时收口；④ registry等待全部attachment的actor-bound mutation与pre-start/new-work lease归零，但继续持有每个RW native mutex且不删除record；⑤ 在mutex仍持有时完成`HostDispatchScheduler.close()` lifecycle barrier：先停止promotion、dispatch drain、heartbeat、cancel watchdog及其它background supervisor，不再启动新Attempt；把当前host instance收口到`STOPPING`；调用`active_registry.cancel_all(...)`使Host注入Engine的cancellation token可见并调用每个`LocalWorkerHandle.on_cancel(reason)`；取消并await active worker/local task，关闭残余worker handle与local task lane；最后把host instance durable收口为`STOPPED`；⑥ 只有步骤⑤完整成功后，registry才关闭native mutex、把attachment标记`CLOSED`并从live index删除；⑦ 再按既有顺序关闭terminal coordinator、delivery/projection、actor handle、executor与store。该顺序保证release后的fresh RW在自己的同一次target recovery中把旧owner的`STOPPED`作为positive orphan proof，不依赖第二次reattach或periodic queued/accepted reconciliation。
- scheduler lifecycle close的“成功”是上述mandatory quiescence与`STOPPED`收口均完成，不是仅设置`_closed`或进入`STOPPING`。`LocalWorkerHandle.on_cancel(...)`仍是best-effort hook：hook抛错可记录diagnostic并继续，但token传播、active task/handle/lane清理与`STOPPED`不得跳过。任一mandatory cleanup或durable `STOPPED`收口异常时，Host close必须继续尝试当前阶段可安全执行的清理，保留首个错误并允许重复close从未完成阶段重试；在barrier未完成期间health gate与attachment保持`CLOSING`、native mutex/record保持持有，不得执行registry release或后续owner关闭，不得记录`close_done`/调用`mark_closed()`，也不得把scheduler的`_close_cleanup_done`标真。只有进程退出时才由OS释放残留mutex，后续fresh owner仍走heartbeat stale + pid/identity proof，不能把异常cleanup伪装成正常`STOPPED` close。

关闭等待只复用既有 Runner/provider 有界边界，不新增 attachment/Host 默认 timeout，也没有 force unlock：

- `LLMContextCompactor.run_prepared_compactor_proposal` 已用 `asyncio.wait_for(..., timeout=RunnerSpec.default_timeout_seconds)` 包住完整 `run_agent_and_wait`；`RunnerSpec.default_timeout_seconds` 必须为正，timeout 会先请求 Runner cancellation，再以 typed proposal failure 交回 Host。
- provider transport 还受 Runner provider 的 HTTP total timeout 约束；stream idle timeout 只在显式配置时额外生效。计划不把 transport retry/idle timeout误写成 attachment owner。
- `run_compaction_operation` 的 semantic proposal 是串行且最多 `max_compaction_attempts_per_operation` 次；合并后的 Slice 2 要让 root、repair 与 tier 共用 request 时冻结的同一剩余 budget。因此一个已持 lease 的 proactive provider 链等待上界来自“剩余 semantic attempts × 既有 `RunnerSpec.default_timeout_seconds`”，外加既有有限 durable/artifact 收口开销，而不是新造 detach timeout。
- 若实施时发现任何 pre-start provider call 绕过 `LLMContextCompactor` 的上述 timeout owner，必须作为本 slice blocker 回 plan/review，不得以 force unlock、后台遗留 task 或新默认 timeout 掩盖。

### 5.5 Scheduler eligibility、periodic owned-session reconciliation 与 stable-owner boundary

`HostDispatchScheduler.open(...)` 新增必填 `session_new_work_access: SessionNewWorkAccessPort`。没有兼容默认值。

精确入口规则：

1. `wake_queue_promotion(session_id)` 先同步检查registry是否仍可接受该Session新工作；无资格时直接丢弃wake并记录不含业务数据的debug diagnostic，不入队。
2. `_promotion_drain_loop` 取出Session后再次申请 `SessionWorkLease`；close/wake race导致无lease时skip。
3. `run_queue_promotion(session_id)` 本身也必须申请lease，防止测试/内部direct call绕过；实际逻辑下沉为只接受lease的私有 `_run_queue_promotion_with_lease(...)`。
4. `_run_pre_start_governance(...)` 只可从持lease的私有call path调用；lease覆盖事务外proactive compactor与post-compact start。
5. Attempt/dispatch record同事务创建成功后，`wake_dispatch(PendingDispatchRecord)`属于已建立stable execution owner的continuation，不再要求attachment；这样detach不杀死existing Attempt。
6. terminal producer触发旧scheduler promotion时，旧registry无RW会drop。当前RW opener通过下面的bounded periodic reconciliation推进queued work。

新增 production/test 共用的唯一一次性 step：

```python
async def reconcile_owned_sessions_once(
    self,
    *,
    fixed_now: datetime,
) -> OwnedSessionReconciliationResult: ...
```

`OwnedSessionReconciliationResult` 是严格 typed、不可变的诊断结果，只返回本次 ACTIVE RW Session 快照数、成功取得 work lease 数、投递/跳过计数，不携带业务 payload。step 在入口取得 registry 的 ACTIVE RW Session id 稳定快照；逐 Session 重新申请 work lease，并只做 target-scoped queued promotion/accepted reconciliation。`fixed_now` 由调用方显式传入，使同一次查询/判定不漂移；registry 进入 closing 后不会出现在新快照，snapshot 后 close race 则由 lease acquire fail closed。

production scheduler 的 `_owned_session_reconciliation_loop` 每次只做两件事：等待既有 `dispatch_poll_interval_seconds`，然后以一次 UTC now 调用 `reconcile_owned_sessions_once(...)`；loop 不复制任何 query、过滤、promotion 或统计逻辑，也没有第二套 test-only reconciliation。unit/integration test 直接调用这个 one-shot step，并用显式 barrier、counter 与 fixed now 断言结果；不得用真实 `asyncio.sleep` 或“多等几个 interval”碰运气。loop wiring 只断言配置 interval 被用于下一次迭代且随后调用同一 step，不做 wall-clock 精度测试。

该机制不是workspace scan、leader election或proxy。它解决以下必要liveness：A detach后existing Attempt仍在A结束；B持RW且新输入已QUEUED；A terminal不能跨进程通知B，B必须在一个poll interval内从durable truth发现active slot已空并promotion。实际测试通过直接触发一次 step 证明语义，通过loop wiring证明production cadence；registry closing后旧scheduler不得推进下一Run。

### 5.6 Attachment-aware target recovery

删除startup语义命名，不做兼容re-export/wrapper：

- `StartupRecoveryPolicy` → `SessionAttachmentRecoveryPolicy`
- `StartupRecoveryScanner` → `SessionAttachmentRecoveryScanner`
- 对应result/classifier/helper按职责改为 `SessionAttachmentRecovery*`
- `_StartupRecoveryActorOperation` → `_SessionAttachmentRecoveryActorOperation(session_id, fixed_now, ...)`

`dayu/host/durable/state.py` 将全局query替换为：

- `read_non_terminal_run_upper_watermark_for_session(transaction, session_id)`
- `read_non_terminal_runs_for_session_keyset_page(transaction, session_id, upper_watermark, after_key, limit)`
- `read_cancelling_runs_for_session(transaction, session_id)`
- execution-owner cancel所需exact identities query（见 5.8）

不保留旧全局query只为测试兼容。现有 `(session_id,status)` 与queue FIFO indexes足够，不改schema/table/index。

`_PublicHostHandle.attach_session` call path：

```text
health/open check
  -> actor read Session existence
  -> registry allocate/native nonblocking acquire
  -> RO: publish immutable RO and return (no watchdog/recovery/wake)
  -> RW RECOVERING:
       fixed_now = one UTC instant
       scheduler.tick_active_cancel_watchdog_for_session(session_id, fixed_now)
       recovery_future = durable_actor.submit(target scanner operation)
       await shield(recovery_future)
       registry.activate(allocation)
       return immutable RW
```

若caller在`recovery_future`后取消，底层actor仍会继续；factory必须shield等待它成功/失败，再close allocation、drain scheduler work leases、释放mutex，最后重新抛`CancelledError`。不能在actor Future仍可能commit/wake时抢先释放。

scanner固定：target Session；一次fixed now；开始时固定target upper watermark；`(accepted_event_sequence, run_id)` keyset；page size 64；每page单独write transaction；page commit后才wake；rollback page不wake；前页commit不回滚；新高水位Run留给下一轮。任一page、cursor invariant、wake bridge失败都close allocation并使attach失败，不返回表面RW。

mutex acquire只证明live attachment空位，不参与旧Attempt positive orphan proof。旧Attempt仍严格使用dispatch owner host instance、heartbeat、pid/start token与CAS recheck；不takeover。

### 5.7 Proactive single-operation event/schema/state machine

`CONTEXT_COMPACTION_REQUESTED` schema增加两个必填typed字段：

- `operation_id: str`，必须等于该request EventLog `event_id`。
- `max_compaction_attempts_per_operation: int`，request时冻结，正整数；恢复不读取新的profile值替换它。

现有 `input_snapshot_cursor`、`frozen_material_list_digest`、`frozen_material_refs` 继续作为重建边界；proactive producer也必须填充可验证的frozen material digest/refs。validator升级为当前shape的strict field/type/cross-field校验，不读取旧shape。reactive producer位于`dayu/host/engine_ingest.py::_append_reactive_compaction_requested_event(...)`：它必须先生成最终request `event_id`，将该值同时作为payload `operation_id`，并把`_start_reactive_context_recovery(...)`当前取得且写入`_ReactiveCompactPending.policy`的同一policy snapshot中的`max_compaction_attempts_per_operation`写入request。禁止在事务外执行阶段重新读取可变化的ingestor policy来产生不同budget。除此之外不改reactive operation count、overflow closeout、`RECOVERING` transition、stale-result gate、fallback decision或recovery dispatch。

新增 `dayu/host/proactive_compaction.py`，只拥有proactive durable operation projection，不承载generic governance God object：

- `ProactiveCompactionOperationPhase = ABSENT | INCOMPLETE | COMPACTED | FAILED | INVALID`
- `ProactiveCompactionOperationState`：run/session/input cursor、operation id、frozen budget、prepared attempt numbers、rejected attempts、terminal event与next attempt number。
- `read_proactive_compaction_operation_state(transaction, event_log_store, run)`：从该Run相关的requested/rejected/compacted/failed和compactor `RUNNER_CALL_INPUT_ASSEMBLED` hot payload读取并调用既有strict parsers。
- `build_proactive_compaction_resume_decision(...)`：返回 `CREATE_NEW`、`RESUME_EXISTING`、`USE_COMPACTED`、`USE_FAILED_FALLBACK` 或 `FAIL_EXISTING_OPERATION` typed decision。

为避免在semantic module直接复制SQL，`dayu/host/durable/event_log.py` 增加一个generic、bounded、run-id + closed event-types + keyset的typed read primitive；它不知道proactive语义。operation reader负责业务归并与校验。

状态不变量：

```text
ABSENT + budget says COMPACT
  -> pre-generate event/operation id
  -> append exactly one REQUESTED(operation_id == event_id, input cursor, frozen budget)
  -> INCOMPLETE

INCOMPLETE
  -> never append another REQUESTED
  -> validate every proposal manifest belongs to same run/session/op/cursor
  -> prepared manifest attempt N consumes N before provider call
  -> next_attempt = max(prepared attempt)+1 (or 1)
  -> remaining = frozen max - prepared count
  -> rebuild same frozen request/tier decision and continue same operation
  -> no remaining/invalid rebuild: append FAILED with same operation id and run existing fallback/fail-close

INCOMPLETE + accepted candidate commit
  -> exactly one COMPACTED(same op)

INCOMPLETE + exhausted/unrepairable
  -> exactly one FAILED(same op)

COMPACTED/FAILED
  -> duplicate wake only reconciles existing terminal operation; never provider call/new request
```

manifest校验必须要求attempt number从1连续、唯一且不超过frozen max；相同number冲突digest、terminal与manifest不匹配、多request/multi-terminal或无法重建frozen material均为INVALID。只要至少存在request row，确定性fail使用最早request event id作为已有operation id；不发明第二operation。fresh schema不提供旧事件兼容读取。

`run_compaction_operation(...)` 将模糊的“每次调用从1计数”改为两个无默认值的required keyword：`first_attempt_number` 与 `max_attempt_number`；删除旧`max_attempts`参数，不保留alias/兼容default。ordinary首次调用传1和当前operation policy max；proactive resume传durable next和frozen max。`engine_ingest.py::_execute_reactive_compaction(...)`对每个新reactive operation只做机械适配：传`first_attempt_number=1`，并传`max_attempt_number=pending.policy.max_compaction_attempts_per_operation`，该值必须等于同一request payload冻结的budget，不得重新读取`self._context_budget_policy`。root repair与tier 1-3每次都从前一结果的next number继续，共享同一max；删除 `_renumber_compaction_rejected_attempts` 及tier `max_attempts=1`重置。生产代码与测试中所有required-signature call sites必须一次性迁移，禁止为遗漏caller增加兼容入口。Runner `max_retries`仍只在单次proposal call内部处理transport retry，不写入Host semantic attempt count。

`_run_pre_start_governance` 不再count：

- ABSENT：prepare新operation。
- INCOMPLETE：重建 `_GovernanceCompactPending` 并resume同一operation。
- COMPACTED：复用其event sequence进入post-compact start。
- FAILED：复用已持久化fallback/terminal decision，不重新compact。
- INVALID：同一operation确定性failed/fallback；无法安全dispatch则按现有governance failure收口。

### 5.8 Cancel access truth 与 Attempt execution owner reconcile

public cancel先走5.2的RW mutation lease，随后复用原有idempotency/CAS transaction；不增加origin opener字段或分支。`ActiveCancelMessage` 增加 `session_id`，使after-commit target watchdog wake无需二次猜测。

`dayu/host/durable/state.py` 定义层内可复用的 `AttemptExecutionIdentity` frozen typed dataclass，字段恰为 `(session_id, run_id, attempt_id, execution_id)`；`ActiveWorkerRegistry.snapshot_identities() -> tuple[AttemptExecutionIdentity, ...]` 只返回该 identity，不返回handle/token。register时保存session id。这样 durable query 不反向依赖 scheduler/registry 实现。

`dayu/host/durable/state.py` 只拥有exact Run/Attempt/dispatch SQL join与typed candidate row；`dayu/host/durable/run_transition.py` 继续作为 `CANCEL_REQUESTED` canonical fact语义owner，组合candidate与EventLog strict validator并对scheduler公开以下typed query。它不复用当前仅按 `Run.status=CANCELLING` 的 `read_cancelling_runs(...)`，也不复用遇到错链返回 `None` 的宽松 helper：

```python
@dataclass(frozen=True, slots=True)
class OwnedAttemptCancelTarget:
    identity: AttemptExecutionIdentity
    cancel_request_event_id: str

def read_exact_owned_attempt_cancel_targets(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    owner_host_instance_id: str,
    identities: tuple[AttemptExecutionIdentity, ...],
) -> tuple[OwnedAttemptCancelTarget, ...]: ...
```

输入 identities 必须字段非空且 tuple 内 identity 唯一；空 tuple 直接返回空结果。实现以输入 tuple 为有界集合，在同一 read transaction 中精确 join：`host_runs.session_id/run_id/current_attempt_id`、`host_attempts.run_id/attempt_id/execution_id`、`host_attempt_dispatch_records.run_id/attempt_id/execution_id/owner_host_instance_id`。不得用 Run 当前状态作为筛选条件，因此 caller watchdog 已把 Run 写成 `CANCELLED` 后，stable cancel control truth 仍可读。只有四元 identity 全等、Attempt 是 Run 的 current Attempt、dispatch owner 等于传入 scheduler host instance 且 `Run.cancel_request_event_id` 非空时才形成候选。

每个候选必须由run-transition owner按 `cancel_request_event_id` 精确读取 linked EventLog row，并严格验证：event id精确相等、`EventClass.CANONICAL_FACT`、event type精确为`CANCEL_REQUESTED`、`session_id/run_id`与identity精确相等、`attempt_id/execution_id/payload_ref/payload_digest`均为`None`。新增的typed payload validator必须strict parse当前producer的exact六字段shape：`run_id`与identity相等，`client_request_id`与event列相等，`reason`为非空文本，`mode`为合法cancel mode，`target_status_at_accept`为合法Run status，`call_context_digest`为合法Host digest；EventLog row decoder的`event_body_digest`完整性校验仍必须通过。禁止把不存在的“既有validator”当作证据，也不兼容旧shape。link缺行、错class/type、错Session/Run、payload/row digest非法都抛durable invariant error，禁止静默当作“未取消”。本地snapshot已过期（Run current Attempt变化、Attempt execution变化、dispatch owner变化、record不存在或没有cancel link）则从结果过滤，不报错也绝不匹配新worker。输出按输入identity顺序稳定排列；不返回Run/Attempt/dispatch raw rows，防止调用方二次推断。

scheduler每个`dispatch_poll_interval_seconds`执行：

1. snapshot当前local workers。
2. 一个bounded read transaction调用上述 exact query；即使Run已被另一scheduler watchdog置为`CANCELLED`，durable cancel link仍须可读。
3. 只接受dispatch owner等于本scheduler host instance且identity完全相同的target。
4. transaction外调用local registry `cancel(message)`；miss仅表示worker已收口。
5. 对exact owned targets运行既有watchdog closeout supervisor；下一poll重复直到worker unregister/terminal。registry cancel message必须从 `OwnedAttemptCancelTarget.identity` 与已验证 `cancel_request_event_id` 构造，不再查“最新 cancelling Run”。

caller `_propagate_active_cancel_targets` 保留立即 `active_registry.cancel` fast path，并把涉及的Session投递到当前RW registry授权的target watchdog queue。watchdog不再周期性workspace-wide扫描：

- fresh RW attach先执行 `tick_active_cancel_watchdog_for_session(...)`；
- live RW caller可对刚commit cancel的target Session执行bounded tick；
- execution owner可对snapshot exact identities执行tick，即使它已detach，因为这是existing Attempt continuation。

这三条都读取同一durable cancel truth。watchdog负责durable closeout，不能代替owner把token/hook作用到worker；owner reconcile也不授予caller takeover。

### 5.9 UI / Service lifecycle

`dayu/cli/session_execution.py` 是prompt/interactive持有Host Session资源的现有UI lifecycle owner：

- prompt：选定/创建Session后、启动watch/submit前attach；持有至terminal wait/cancel cleanup完成；finally shield `attachment.aclose()`。
- interactive：startup reconnect前attach；同一个attachment覆盖reconnect、所有turn与Esc cancel；退出REPL时在watcher/display task收口后close attachment。
- typed RO rejection保持Host detail；CLI只做用户可读渲染，不重新判断mutex或mode，不自动fresh attach/promotion。

`dayu.service.entrypoint_runtime` 继续只编排watch/read/submit/cancel，不接收一个无实际用途的attachment参数，也不创建兼容wrapper。Service调用发生时，UI已持有attachment；真实授权仍由Host在每次command前校验。Service README将原“watcher attach”措辞改为“subscription/open watcher”，明确watch不授予写权限。

CLI 之外的 headless、一次性 script、production bootstrap、smoke 与 test harness 若直接调用 public Host mutation，同样是 attachment lifecycle caller，不能假设 Service 代持。它们必须在明确 Session 后由自己的 lifecycle owner 执行一次 `attach_session`，在 mutation、相关 terminal/cancel cleanup 与 watcher关闭期间复用该唯一对象，并在 `finally` 中 shield `aclose()`；同一 Host handle 内的 helper 只能接收/复用 owner 已持有的 attachment 生命周期，禁止自行重复 attach。若要验证跨opener竞争，harness 必须创建两个独立 `open_host(...)` context。

Service 不新增 attachment 参数、不缓存 attachment、不从 watcher、Session id、Host handle 或 mutation 类型推断 attachment 存在，也不替 direct caller 自动 attach。测试必须同时证明：(a) headless/direct Host caller 未 attach 时在 actor write、wake、provider 前得到 typed `ATTACHMENT_REQUIRED`；(b)显式持有 RW attachment 后同一 public mutation 成功；(c)显式 RO attachment得到 typed `READ_ONLY`；(d)同 handle helper 重复 attach 得到 typed attachment conflict且 native acquire计数不增加。fake Host 只在其所模拟的真实 UI lifecycle 需要 attach 时实现相同显式 contract，不能给所有 Service fake 加隐式 allow-all。

## 6. Affected production modules and files

计划内允许修改的生产/配置文件全集如下；implementation若发现必须超出此表，停止当前slice并回plan gate，不得自行扩scope：

| 文件 | 精确变化 |
| --- | --- |
| `dayu/runtime/native_mutex.py`（new） | strict-native nonblocking mutex与cleanup owner。 |
| `dayu/runtime/__init__.py` | runtime能力概览加入native mutex；不re-export。 |
| `dayu/host/api.py` | public mode/attachment/error detail与`Host.attach_session`。 |
| `dayu/host/__init__.py` | 导出新public contracts。 |
| `dayu/host/session_attachment.py`（new） | registry、allocation、attachment实现、mutation/work leases和scheduler access port。 |
| `dayu/host/open_host.py` | registry装配、public attach/mutation gate、target recovery factory、Host-close专用scheduler-before-unlock顺序、删除startup scan/tick。 |
| `dayu/host/dispatch.py` | mandatory eligibility、owned-session reconcile、proactive state consumption、Host-close lifecycle quiescence/STOPPED barrier、attempt owner cancel reconcile、scoped watchdog。 |
| `dayu/host/recovery.py` | target-session scanner/命名、fixed target pagination；无compat wrappers。 |
| `dayu/host/durable/state.py` | target-session recovery/watchdog query与exact owner cancel query。 |
| `dayu/host/durable/run_transition.py` | exact cancel candidate的linked `CANCEL_REQUESTED` strict event/payload validation与typed target projection。 |
| `dayu/host/durable/event_log.py` | bounded generic run/events keyset read primitive。 |
| `dayu/host/context_events.py` | requested operation id与frozen attempt budget schema/validator。 |
| `dayu/host/proactive_compaction.py`（new） | proactive durable operation state/decision owner。 |
| `dayu/host/compaction_operation.py` | global semantic attempt number范围与manifest连续性。 |
| `dayu/host/engine_ingest.py` | 仅机械适配reactive requested新schema与required first/max attempt range；budget与pending policy snapshot同源，不改reactive count/overflow/recovery/fallback。 |
| `dayu/host/context_policy.py` | 删除proactive operation count field/default/validation/export。 |
| `dayu/runtime/config_loader.py` | 删除typed config field和allowed/required parser field；旧字段变unknown并拒绝。 |
| `dayu/config/execution_profiles.json` | 四个profile删除旧字段。 |
| `dayu/service/host_assembly.py` | 删除旧field projection；不增加attachment facade。 |
| `dayu/cli/session_execution.py` | prompt/interactive attachment持有与cleanup。 |
| `utils/smoke_host_public_awaiting_entrypoint.py`、`utils/smoke_host_public_r03_semantic_ownership.py`、`utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py` | direct/headless public Host mutation caller显式持有唯一attachment；不经Service代持。 |

明确不修改 `dayu/engine/**`、`dayu/fins/**`、prompt/tool schema、durable schema/table/index、design_doc、control_doc。

## 7. Small implementation slices

本WU使用3个slice，位于控制文档“中型跨contract/provider/projection默认3至5”范围内。原计划的 Slice 2（公开 attachment/recovery）与 Slice 3（proactive durable operation）合并为新的 Slice 2；原因不是实现便利，而是不存在可发布的语义稳定 checkpoint：

- strict-native OS handle/partial allocation/process-exit是资源安全失败模型，不能与SQLite recovery transaction一起回滚；Slice 1明确为contract-only，不对外启用半成品API。
- attachment/scheduler/recovery是一个不可拆的access闭环；若把gate与target recovery分开，对外RW attachment会在错误startup/recovery语义下成功返回。
- 当前代码在已有 incomplete proactive `REQUESTED` 被 fresh RW target recovery/wake 后，仍会按旧 count/limit path 判断，可能产生第二次 operation或错误 `proactive_compact_limit_reached`。因此单独落地 public attachment/recovery 会主动暴露已知 crash 反例，不能称为“attachment ownership可生产使用”。
- 不允许用临时兼容分支、跳过 recovery、xfail 或测试 fixture 掩盖这个边界；attachment/recovery 与 typed proactive resume 必须在同一 PR 的同一 release/merge unit 中完成，只允许实现过程中的内部未发布 checkpoint，不能单独 merge、部署、tag 或作为可交付 handoff。
- cancel要求在已经detach的old execution owner上继续传播，是有意绕开“新Session工作gate”的existing-owner例外；与普通mutation合并会掩盖其独立race matrix。

新的 Slice 2 内部按“attachment gate/target recovery → proactive projection/resume → boundary tests”排序，但只有三者共同通过才有 completion signal。没有第四个slice，因为CLI/docs/全量验证可在cancel闭环后作为同一final integration收口；单独拆成docs-only slice不会增加可回滚语义。

### Slice 1 — Strict-native primitive 与 registry contract（explicit contract-only）

**稳定 handoff**：建立并单测层中立native mutex、Host registry生命周期和lease contract，但不修改`Host` Protocol、不export public attachment、不把registry装入`open_host`。现有production行为不变，因此不会形成可被用户调用的半成品。

**Allowed files**

- `dayu/runtime/native_mutex.py`（new）
- `dayu/runtime/__init__.py`
- `dayu/host/session_attachment.py`（new，类型暂保持Host internal）
- `dayu/host/api.py`（只增加registry内部需要的mode/error value types；不加入`Host` Protocol/包根export）
- `tests/runtime/test_native_mutex.py`（new）
- `tests/runtime/test_import_boundary.py`
- `tests/host/test_session_attachment_registry.py`（new）

**Prerequisites**

- baseline `974f9e16`；控制文档既存修改不动。
- 明确当前支持平台的native backend：POSIX `flock`、Windows `msvcrt.locking`；unsupported fail closed。

**Exact changes**

1. 实现native primitive、busy errno白名单、unavailable错误、idempotent close与partial FD cleanup。
2. Host派生canonical mutex path；runtime不接收Session/business字段。
3. 实现registry pending/active/closing/closed、同一registry/Session最多一个live record、重复attach在native acquire前typed conflict、RO immutable、mutation/work lease计数和concurrent close共享task。
4. 实现Host-close批量mark/drain/release；不写durable fact。
5. 所有新增模块/类/函数写完整中文docstring，无`Any/object/getattr/hasattr`逃逸。

**Non-goals**

- 不改public Host call path、scheduler或recovery。
- 不用普通filelock，不增加workspace配置项。

**Tests / expected assertions**

- 同key第一个handle acquired、第二个busy；close后fresh acquire成功；不同key同时成功。
- subprocess持锁后正常close与被kill/process exit两种路径均可reacquire；lock file仍存在不影响结果。
- unsupported backend、unexpected errno、open/truncate失败raise unavailable且无soft fallback。
- partial allocation关闭FD；handle repeated close幂等。
- registry同一Host handle/Session只一个live attachment；RW/RO重复attach都在native acquire前typed conflict；不同Session独立、RO mode不变、close/fresh reattach、concurrent close幂等。
- mutation/work lease阻止mutex提前释放；caller取消close等待时后台cleanup继续。
- runtime import scan覆盖`native_mutex.py`且无Host/Engine/Service/UI/Fins依赖。

**Completion signal**

- 新contract单测与runtime全套通过；现有Host API/行为无变化；pyright对本slice通过。

### Slice 2 — Public attachment、target recovery 与 proactive single-operation 原子闭环

**唯一稳定 handoff**：一次性公开并装配attachment，所有user mutation与scheduler new work消费同一registry；移除workspace startup recovery；RW attach完成target recovery后才return；同时把被target recovery唤醒的incomplete proactive operation切到typed same-operation resume。原 Slice 2 的attachment-only状态是明确不可发布的内部checkpoint：不得单独merge、部署、tag或宣告完成。只有本slice全部boundary tests通过后才可交付，且必须在同一PR完成，不保留临时兼容或旧count fallback。

**Allowed production files**

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/session_attachment.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/recovery.py`
- `dayu/host/durable/state.py`
- `dayu/cli/session_execution.py`
- `dayu/host/proactive_compaction.py`（new）
- `dayu/host/context_events.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/engine_ingest.py`（仅reactive request schema与required attempt-range机械适配）
- `dayu/host/context_policy.py`
- `dayu/host/durable/event_log.py`
- `dayu/runtime/config_loader.py`
- `dayu/config/execution_profiles.json`
- `dayu/service/host_assembly.py`
- `utils/smoke_host_public_awaiting_entrypoint.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

**Allowed test/support files**

- `tests/host/fake_session_access.py`（new；scheduler unit tests显式使用，无production default）
- `tests/host/public_smoke_support.py`
- `tests/host/stress_support.py`
- `tests/host/recovery_support.py`
- `tests/host/test_public_session_attachment.py`（new）
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_public_outbox_api.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/host/test_transient_delta_stress.py`
- `tests/host/test_host_production_stress.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/cli/test_transient_delivery_interruption_path.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/host/test_proactive_compaction_operation.py`（new）
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_context_policy.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_public_real_runner_matrix_smoke.py`
- `tests/host/test_purge_session.py`

只允许修改上述现有public-open-host测试中实际调用mutation或因`Host` Protocol新增方法而需要更新的fixture；不得趁机改业务断言。

**Prerequisites**

- Slice 1通过。
- recovery现有positive orphan proof测试矩阵保持真源，不把mutex加入分类输入。

**Exact changes**

1. 完成public types/export/`Host.attach_session`，`_PublicHostHandle`持registry。
2. 新增 `_invoke_session_mutation`：同时取得health admission与registry mutation lease，lease绑定actor Future；Run-id API先typed read session id。
3. gate 5.2列出的全部mutation，特别覆盖cancel/session close/Outbox drain；read/resolve_wait不gate。
4. scheduler构造强制注入access port；wake、actual promotion、pre-start、new Attempt创建持work lease；existing dispatch continuation不gate。
5. 加ACTIVE RW Session bounded periodic reconcile，保证old owner terminal后current owner promotion。
6. 删除`open_host`全局recovery/watchdog tick；scanner/state query改target-only命名与参数。
7. 实现RW attach fixed-now target watchdog→target recovery→activate；RO无副作用；所有failure/cancellation路径先drain再release。
8. 调整Host close专用顺序：actor/pre-start收口后继续持mutex，完整完成scheduler promotion/background/active worker/task/lane与host instance `STOPPING -> STOPPED` lifecycle close，最后才release mutex/attachment record；单attachment close不变。
9. CLI prompt/interactive在UI lifecycle持attachment；Service helper不接管truth、不加透传facade。
10. 同一Host handle/Session重复attach在native acquire前typed conflict；共享runtime helper复用唯一attachment，真实竞争只用独立`open_host`。
11. periodic loop只按interval调用production/test共用的 `reconcile_owned_sessions_once(fixed_now=...)`；测试直接触发step，不sleep。
12. 按5.4精确落实Host/attachment close顺序，并用既有Runner timeout与provider barrier证明等待有界；scheduler mandatory cleanup/`STOPPED`异常时保留`CLOSING` record与mutex、允许close重试，禁止force unlock和新默认timeout。
13. request schema增加operation id与frozen semantic budget；增加bounded generic run-event read与proactive typed state/decision owner。
14. `_run_pre_start_governance`以phase decision替代count；`run_compaction_operation`接受required global attempt range，root/tier/recovery共享budget，INVALID/incomplete exhausted用原operation id收口，并迁移所有生产/测试required-signature call sites。
15. 在`engine_ingest.py`只机械适配reactive request新schema与attempt range：request event id即operation id；request/pending/execute共用同一policy budget snapshot；首次传`first_attempt_number=1`，不改count/overflow/recovery/fallback。
16. 删除旧proactive count配置全链且不保留alias/default；保留reactive count与single-operation attempt budget。
17. 迁移所有direct/headless/script/test harness mutation caller的显式attachment lifecycle；Service不代持、不推断。

**Non-goals**

- 不增加durable table/index/count字段、operation mutex或EventLog lock；不改reactive多次overflow state machine。
- 本slice不改cross-opener physical cancel owner reconcile；public cancel access gate先完成，Slice 3补execution-owner副作用。

**Tests / expected assertions**

- 两个真实public opener、同DB同Session：A RW/B RO；B submit/steer/cancel/retry/replay/close/drain均typed `PERMISSION_DENIED`，detail reason/mode/session精确，且event count/provider calls/wake count均为0增量。
- B仍可`get_*`/read Outbox/watch durable progress；A的live transient delta不出现在B，B通过periodic durable reconciliation看到progress/terminal。
- 同workspace不同Session，A/B同时RW并行submit，各自只有一个Run/Attempt。
- A close RW后B原RO仍RO；B close/fresh attach成为RW；并发fresh attach只有一个RW。
- attachment close在actor mutation Future结束前不释放；caller cancellation不泄漏；repeated/concurrent close和Host close最终可fresh reacquire。
- proactive provider被gate阻塞时detach等待它cancel/drain；mutex释放前第二opener仍RO。
- A有stable active Attempt后detach，Attempt继续；B fresh RW提交进入QUEUED；A terminal后A不promotion，B在poll bound内promotion且不takeover旧Attempt。
- 单独`open_host`不改任何Run、不wake；RO attach不恢复；RW attach只读取目标Session，另一Session event/status不变。
- target recovery保持fixed now、fixed watermark、64 page、keyset tie、commit-after-wake、rollback-no-wake和rerun convergence。
- attach recovery第二page/wake failure：前页commit保留，attachment factory失败，mutex可被fresh attach重新获得，不返回RW对象。
- attach factory在actor recovery排队后被取消：等底层Future收口再release，无commit-after-release窗口。
- opener crash mutex由OS释放；fresh owner仍需positive orphan proof，live旧owner不被误杀。
- 所有原public mutation测试显式attach；watcher-only测试证明watch不授权。
- 同一Host handle的RW与RO分别重复attach都返回typed `CONFLICT/already_attached`，native acquire probe为0增量；close完成后fresh attach才重新竞争。共享runtime helper只收到/复用一个attachment对象。
- attachment close顺序用barrier逐项证明：close gate后新mutation/wake/lease拒绝；actor Future未完成时native mutex仍busy；actor完成但pre-start provider barrier未释放时仍busy；释放provider后mutex才可fresh acquire。单attachment close仍不关scheduler，existing stable Attempt继续。
- Host close使用确定性双openerbarrier证明专用顺序：A进入close并完成actor/pre-start drain、但scheduler lifecycle close尚未完成时，B对同Session的fresh attach只能得到RO；此时A的mutex/attachment record仍持有。scheduler lifecycle barrier内必须先让active worker cancellation token和`LocalWorkerHandle.on_cancel(...)`调用可观察，再取消/await worker/task、关闭handle/lane并durable标记old owner `STOPPED`。barrier完成后A才release；B关闭原RO并fresh attach，在这一次target recovery中必须读取old owner `STOPPED`、推进recoverable旧Attempt到`LOST`/Run到`RECOVERING`并创建新Attempt/dispatch，不调用第二次attach、不等待periodic reconcile。
- scheduler mandatory cleanup或`STOPPED`写入注入异常时，close返回错误但Host health/attachment保持`CLOSING`、mutex仍busy、第二opener仍只能RO，`close_done`/`mark_closed`/`_close_cleanup_done`均不可宣称成功，后续owner尚未关闭；重复close补完quiescence与`STOPPED`后才release并继续其余owner。更新当前“普通cleanup异常即`_close_cleanup_done=True`”的偶然测试，不保留该行为。best-effort `on_cancel` hook抛错不阻断token与其余mandatory cleanup，但必须证明hook已在unlock前被调用。
- provider不返回时使用测试Runner的既有极短 `RunnerSpec.default_timeout_seconds` 触发真实compactor timeout，operation按既有attempt budget收口后close完成；没有force unlock、没有新增detach/Host timeout配置，调用次数不超过remaining semantic budget。
- `reconcile_owned_sessions_once(fixed_now=...)` 直接调用一次即可推进目标Session且不扫描RO/closing/其它Session；重复调用幂等。loop wiring用可控迭代/事件立即触发，断言interval后只调用同一step，全套测试无wall-clock sleep。
- 已有INCOMPLETE request + manifests/rejections时，fresh RW target recovery与accepted replay overlap只能恢复原operation/cursor/remaining budget；request count exact 1、provider chain exact 1，不出现limit failure。
- crash在manifest commit后/provider result前与crash在rejected event后都由fresh RW以原operation继续；prepared attempt保守计入budget；无remaining budget则同operation FAILED/fallback且provider 0调用。
- normal wake、重复accepted wake与two-opener overlap均request exact 1、compacted terminal exact 1；malformed/mismatched/multi-terminal fail closed且不追加第二request。
- root+semantic repair+tier的attempt number全局连续且总数不超过frozen max；`run_compaction_operation`所有生产与测试caller显式传required first/max参数，不存在旧`max_attempts`兼容路径。
- reactive requested payload精确断言`operation_id == request event_id`、`max_compaction_attempts_per_operation == pending.policy.max_compaction_attempts_per_operation`；执行spy精确观察`first_attempt_number=1`和相同`max_attempt_number`。既有一次/二次reactive count、重复overflow上限、stale-result gate、fallback dispatch与fallback fail-closed断言不回归；Runner transport retry语义不变；旧config field严格拒绝且active stale grep为零。
- direct/headless Host harness覆盖未attach拒绝、显式RW成功、显式RO拒绝；五个`utils/smoke_host_public_*` direct caller和CLI caller由各自lifecycle owner持有/关闭attachment，Service tests证明Service未新增attach调用或attachment状态。

**`open_host` fixture/helper 迁移清单（本slice必须逐项打勾）**

- shared option/helper：`tests/host/public_smoke_support.py::open_host_options`、`tests/host/stress_support.py::build_stress_open_host_options`、`tests/host/recovery_support.py::recovery_open_host_options` 仍只构造options，不隐式attach；后者所有真正open/mutation helper在Session确定后显式持有attachment。
- runtime/recovery direct contexts：`test_open_host_runtime.py`、`test_recovery_multiprocess.py`、`recovery_support.py`、`test_host_production_stress.py`。
- public mutation smoke：`test_submit_followup_public_contract.py`、`test_public_steer.py`、`test_public_retry_replay.py`、`test_public_cancel_smoke.py`、`test_public_compact_smoke.py`、`test_public_open_host_multiturn_smoke.py`、`test_public_lifecycle_smoke.py`、`test_public_offline_outbox_smoke.py`、`test_public_outbox_api.py`、`test_public_resolve_wait_resume.py`、`test_public_tool_wiring_smoke.py`、`test_public_real_runner_matrix_smoke.py`。
- broader Host integration：`test_effective_execution_config.py`、`test_host_activity_event_projection.py`、`test_per_run_tool_selection.py`、`test_transient_delta_stress.py`、`test_watch_session_events.py`、`test_purge_session.py`；其中纯read/open/options case明确标为无需attach，不能为通过测试给read path伪造attachment。
- CLI/Service fake与真实Host harness：`tests/cli/test_prompt_command.py`、`test_interactive_command.py`、`test_session_command.py`、`test_transient_delivery_interruption_path.py` 由UI fake表达attach/aclose；`tests/service/test_entrypoint_runtime*.py` 保持Service不attach，只更新Protocol fake所需的显式测试形状，不加allow-all fallback。
- utils direct scripts：`smoke_host_public_awaiting_entrypoint.py`、`smoke_host_public_r03_semantic_ownership.py`、`smoke_host_public_conversation_memory.py`、`smoke_host_public_conversation_memory_scenarios.py`、`smoke_host_public_multiturn.py`。

完成断言：对上述清单运行 `rg` 枚举所有 `open_host(` context 与七类public mutation调用；每个mutation site必须可追溯到同一词法/对象lifecycle中更早的一次显式attach和finally/shield close，或被测试明确断言为`ATTACHMENT_REQUIRED/READ_ONLY`；helper不得自行重复attach，Service文件中attachment ownership grep为零。review逐项核对清单后才允许本slice完成，禁止只依赖pyright或抽样测试宣告迁移结束。

**Completion signal**

- public attachment、target recovery、incomplete proactive crash boundary与config deletion必须作为一个测试/评审checkpoint共同通过；无`StartupRecovery*`生产符号，单独open_host零Session治理副作用，旧count stale grep为零，fixture/helper清单完成，pyright对本slice通过。attachment-only内部checkpoint不可发布，也不是handoff。

#### Slice 2 内部 proactive 子步骤（非独立slice、非handoff）

本子步骤把proactive uniqueness从配置count迁到typed durable operation状态机；正常重复wake、graceful detach和process crash均共享同一operation truth，旧字段被严格拒绝。它与上面的attachment/recovery子步骤同属一个Slice 2、同一PR和同一completion signal；以下allowed files/tests是Slice 2全集中的职责分组，不构成可单独发布的checkpoint。

**Allowed production/config files**

- `dayu/host/proactive_compaction.py`（new）
- `dayu/host/dispatch.py`
- `dayu/host/context_events.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/engine_ingest.py`（仅reactive request/attempt-range机械适配）
- `dayu/host/context_policy.py`
- `dayu/host/durable/event_log.py`
- `dayu/runtime/config_loader.py`
- `dayu/config/execution_profiles.json`
- `dayu/service/host_assembly.py`

**Allowed tests**

- `tests/host/test_proactive_compaction_operation.py`（new）
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_context_policy.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`

**内部顺序前置（不是handoff）**

- Slice 2同一working tree中的attachment子步骤已保证同Session仅一个eligible scheduler，graceful detach能drain pre-start，crash后由fresh RW target recovery唤醒；在proactive子步骤和boundary tests完成前不得发布该状态。
- 不改变reactive pipeline owner；任何reactive改动仅限`engine_ingest.py`新request字段与required attempt API参数适配，且request/pending/execute共用同一policy budget snapshot。

**Exact changes**

1. request schema增加operation id与frozen semantic budget；proactive填frozen material refs/digest并校验event id同源。
2. 增加bounded generic run-event read与proactive typed state/decision owner。
3. `_run_pre_start_governance`以phase decision替代count；删除count unreadable/limit reached分支和helper。
4. `run_compaction_operation`删除旧`max_attempts`并接受无默认值的required global attempt range；proposal manifest/rejected/accepted number全局连续；全仓生产与测试call sites一次迁移。
5. root与tier 1-3共享同一budget；crash prepared manifest保守占用attempt；resume不从1开始。
6. INVALID/incomplete exhausted均用原operation id走一次deterministic failed/fallback，不能新request。
7. 删除Host policy/config loader/Service assembly/四个profile中的旧字段、常量、docstring、exports和旧测试输入；不保留alias/default。
8. `engine_ingest.py`预生成reactive request/operation id，写入pending policy同源frozen attempt budget，并以`first_attempt_number=1`/同一snapshot max调用operation；保留并回归`max_reactive_compactions_per_run`、overflow/recovery/fallback与Runner retry。

**Non-goals**

- 不增加durable table/index/count字段、operation mutex或EventLog lock。
- 不改reactive多次overflow state machine、不把crash恢复建模为第二operation。

**Tests / expected assertions**

- 同Run/input snapshot的normal wake、重复accepted replay wake、public two-opener startup overlap：request count exact 1，provider operation chain exact 1，compacted exact 1，无limit failure。
- 已有INCOMPLETE request + manifests/rejections：state reader返回原operation/cursor、next attempt和精确remaining budget。
- crash在manifest commit后/provider result前：fresh RW以同operation从N+1继续；prepared attempt计入budget。
- crash在rejected event后：恢复遵循last next-policy decision与frozen material；request digest/refs可验证。
- 无remaining budget：同operation FAILED/fallback，attempt_count/exhausted精确；不调用provider。
- malformed/mismatched/multi-terminal state：fail closed，不追加第二request；fallback不能安全构造时Run按现有governance failure终结。
- root+semantic repair+tier 1-3的proposal attempt number全局连续且总数不超过frozen max；Runner transport retry不增加这些numbers。
- `test_compaction_operation.py`与`test_compaction_cancellation_scope.py`的所有direct call显式传required first/max range，并继续覆盖attempt child timeout、parent cancel、outer task cancel与manifest post-write recheck，不因signature迁移改变取消scope。
- COMPACTED/FAILED后的重复wake不调用provider、不新增terminal event，正常start/fallback幂等。
- `test_engine_ingest_mapping.py`断言reactive requested新shape、`operation_id == request event_id`、frozen max与执行first/max精确同源；reactive repeated overflow仍由`max_reactive_compactions_per_run`收敛，count-limit、第二operation、stale result、fallback dispatch/fail-closed与operation attempt budget测试不回归。
- default与workspace config加载成功且typed policy无旧字段；包含旧字段的packaged-shape fixture和workspace overlay均unknown-field rejection。
- exact stale grep在`dayu/`、`tests/`和根README零命中；design/control/archive不在删除范围。

**内部完成检查（不能独立宣告Slice完成）**

- 删除 `proactive_compact_limit_reached` 与旧字段的active-code grep；incomplete crash public回归通过；reactive/attempt budget focused tests通过。最终仍必须满足上文Slice 2的联合completion signal。

### Slice 3 — Execution-owner cancel reconcile、product/docs integration 与 final verification

**稳定 handoff**：cancel完成跨opener物理传播闭环；全部README按已实现代码更新；执行full regression、per-file coverage和pyright，形成implementation completion report所需证据。

**Allowed production files**

- `dayu/host/dispatch.py`
- `dayu/host/command.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/open_host.py`
- `dayu/host/session_attachment.py`
- `dayu/cli/session_execution.py`（仅cancel/cleanup integration correction）

**Allowed tests**

- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_transient_delivery_interruption_path.py`

**Allowed documentation files**

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`

**Prerequisites**

- Slices 1-2全部focused tests通过。
- README更新前再次核对各README的`Agent更新约束`与最终代码；文档只写已实现事实。

**Exact changes**

1. `AttemptExecutionIdentity`/candidate SQL落在state owner，`OwnedAttemptCancelTarget`与5.8 linked-event strict query落在run-transition cancel owner；Active registry加入exact identity snapshot；owner scheduler durable reconcile、token/hook传播、exact watchdog closeout。
2. caller fast path携带session id并触发RW target-scoped watchdog；删除workspace-wide periodic cancelling scan/query。
3. 保证Run即使先被caller watchdog持久化为CANCELLED，owner仍从durable cancel link读取并传播；terminal status不能抹掉control truth。
4. 覆盖detach old owner例外：old scheduler只可管理自己已stable Attempt，不能promotion/new governance。
5. 按Section 9更新README，随后执行完整验证；不修改design/control。

**Non-goals**

- 不做IPC、proxy、origin字段、takeover、fence。
- 不把owner reconcile泛化为workspace-wide control bus。

**Tests / expected assertions**

- A RW提交active Run并detach；B fresh RW cancel；B registry miss不影响durable acceptance；A owner scheduler在poll bound内调用local token与handle cancel hook。
- caller watchdog先把Run置CANCELLED的race下，A仍传播physical cancel；之后重复poll幂等。
- A worker先terminal后，只要四元identity与dispatch owner仍精确且cancel link有效，typed query仍返回target并传播；Run terminal status不是filter。
- A worker先unregister或identity/current attempt/execution/dispatch owner变更时，stale identity被过滤，reconcile不误cancel新Attempt/新execution。
- exact query返回值精确包含四元identity和`cancel_request_event_id`；linked row缺失、非canonical、非`CANCEL_REQUESTED`、Session/Run错链或typed payload/digest非法均抛durable invariant error，不静默跳过。
- cancel session多个Run只传播exact active targets；queued/recovering保持既有durable语义。
- B RO cancel在任何durable fact/wake前typed拒绝；fresh RW cancel复用相同public API与idempotency，不读取origin。
- fresh RW target attach先收口accepted cancellation；RO/unattached opener不扫描其它Session。
- Host/attachment concurrent close期间owner reconcile、watchdog和registry清理无deadlock/lease leak；fresh reacquire成功。
- 既有non-cooperative worker watchdog、late result fence、lane release、queued promotion测试不回归。

**Completion signal**

- focused cancel/attachment matrix、全量pytest、全量pyright、stale grep、每文件覆盖率与README audit全部通过；只剩明确记录的环境残余风险。

## 8. Required validation commands

所有实现验证均从仓库根目录执行，且每组先激活Python 3.11 venv。

### 8.1 Slice 1

```bash
source .venv/bin/activate
pytest tests/runtime/test_native_mutex.py tests/runtime/test_import_boundary.py \
  tests/host/test_session_attachment_registry.py -q
python -m pyright dayu/runtime/native_mutex.py dayu/host/session_attachment.py \
  tests/runtime/test_native_mutex.py tests/host/test_session_attachment_registry.py
```

### 8.2 Slice 2 attachment/recovery/direct-caller matrix

```bash
source .venv/bin/activate
pytest tests/host/test_public_session_attachment.py \
  tests/host/test_public_contracts.py tests/host/test_package_exports.py \
  tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py \
  tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py \
  tests/host/test_recovery_multiprocess.py tests/host/test_state_schema.py \
  tests/host/test_submit_followup_public_contract.py \
  tests/host/test_public_steer.py tests/host/test_public_retry_replay.py \
  tests/host/test_public_cancel_smoke.py tests/host/test_public_compact_smoke.py \
  tests/host/test_public_open_host_multiturn_smoke.py \
  tests/host/test_public_lifecycle_smoke.py \
  tests/host/test_public_offline_outbox_smoke.py \
  tests/host/test_public_outbox_api.py tests/host/test_public_tool_wiring_smoke.py \
  tests/host/test_public_resolve_wait_resume.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_public_real_runner_matrix_smoke.py \
  tests/host/test_effective_execution_config.py \
  tests/host/test_host_activity_event_projection.py \
  tests/host/test_per_run_tool_selection.py \
  tests/host/test_transient_delta_stress.py \
  tests/host/test_host_production_stress.py tests/host/test_purge_session.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py \
  tests/cli/test_transient_delivery_interruption_path.py \
  tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
rg -n "open_host\(|\.(submit_followup|retry_run|replay_run|cancel_run|cancel_session_runs|close_session|drain_outbox_terminal_items)\(" \
  tests/host tests/cli tests/service utils
rg -n "attach_session|HostSessionAttachment" tests/service dayu/service
python -m pyright dayu/ tests/ utils/
```

第一组 `rg` 是完整迁移审计输入，不要求零输出；review必须把每个mutation命中逐项归类为“同lifecycle已有显式attach+close”或“故意断言typed拒绝”，并与本计划Slice 2迁移清单互证。第二组只允许Service Protocol/type引用和“Service不拥有attachment”的负向断言，不允许Service调用、缓存或推断attachment。

### 8.3 Slice 2 proactive/crash与reactive机械适配边界（与8.2同一completion checkpoint）

```bash
source .venv/bin/activate
pytest tests/host/test_proactive_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py \
  tests/host/test_compaction_cancellation_scope.py \
  tests/host/test_context_compact_events.py tests/host/test_context_policy.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_event_log_store.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_recovery_multiprocess.py \
  tests/runtime/test_config_loader.py tests/service/test_host_assembly.py -q
rg -n "run_compaction_operation\(" dayu tests
rg -n "max_proactive_compactions_per_run|DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN|proactive_compact_limit_reached" \
  dayu tests README.md
python -m pyright dayu/ tests/ utils/
```

第一组`rg`是required-signature迁移审计输入，不要求零输出；review必须逐项确认production `dispatch.py`/`engine_ingest.py`与`test_compaction_operation.py`/`test_compaction_cancellation_scope.py`等所有direct caller均显式传`first_attempt_number`和`max_attempt_number`，没有兼容default。第二组stale-field `rg`预期无输出并以1退出；design/control/archive包含设计裁决或历史说明，不属于stale active surface，不纳入该命令。

### 8.4 Slice 3 focused cancel

```bash
source .venv/bin/activate
pytest tests/host/test_active_cancel_dispatch.py \
  tests/host/test_public_cancel_smoke.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_open_host_runtime.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  tests/cli/test_transient_delivery_interruption_path.py -q
python -m pyright dayu/ tests/ utils/
```

### 8.5 Full regression

```bash
source .venv/bin/activate
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools \
  tests/host tests/runtime tests/service tests/engine -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

### 8.6 Per-file coverage `>=80%`

先用完整受影响测试面生成coverage data，再对相对baseline所有modified production Python文件逐文件fail-under；不得只看aggregate：

```bash
source .venv/bin/activate
python -m coverage erase
pytest tests/host tests/runtime tests/service tests/cli \
  --cov=dayu --cov-report=
for file in $(git diff --name-only 974f9e1686f6e26f96830cd3478edc9d0d686c45 -- 'dayu/**/*.py'); do
  python -m coverage report --include="$file" --fail-under=80
done
```

若某个changed production `.py`低于80%，必须补owner contract测试，不得用pragma、omit或降低阈值绕过。`dayu/render/`与`utils/`本WU不修改。

### 8.7 Final invariant greps

```bash
rg -n "StartupRecovery|read_non_terminal_runs\(|read_cancelling_runs\(" dayu tests
rg -n "max_proactive_compactions_per_run|DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN|proactive_compact_limit_reached" \
  dayu tests README.md
rg -n "from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)" \
  dayu/runtime/native_mutex.py
```

三组均预期无production stale命中；若测试名称/断言需要描述已删除旧shape，允许测试函数名使用业务化“unknown proactive operation count field”，不保留精确旧字段文本，旧字段输入可由分段字符串构造以同时维持stale grep和strict rejection证据。

## 9. README / docs decision

实现完成后按各README自身约束更新，不在本plan gate修改：

- `dayu/host/README.md`：必须更新。属于Host public contract、attachment registry、target recovery、scheduler eligibility、proactive operation与cancel owner机制。
- `dayu/README.md`：必须更新。属于UI→Service→Host跨层attachment lifecycle与`dayu.runtime` layer-neutral native primitive边界。
- `dayu/config/README.md`：必须更新。移除proactive operation count配置说明，明确operator可配的是reactive operation上限和单operation semantic attempt budget；不在README保留旧字段名。
- `dayu/service/README.md`：必须更新。明确watcher是subscription而非attachment；UI持有attachment，Service不产生access truth。
- `tests/README.md`：必须更新。记录public same/different Session、target recovery、native mutex、incomplete operation与cross-opener cancel测试层级和命令。
- 根 `README.md`：需要更新。两个CLI进程选择同一Session时typed read-only是用户可见入口/排障变化；只写用户如何退出旧owner、关闭后fresh进入，不写registry/mutex/状态机内部术语。
- `dayu/runtime/__init__.py`：作为package概览同步native mutex；仓库没有独立`dayu/runtime/README.md`。
- `docs/host/design.md`：不改，已是设计真源。
- `docs/host/issues-implementation-control.md`：不由implementation agent改；仅总控在后续gate按自己的owner更新。
- archive文档：不改，不做机械stale清理。

所有README只在对应代码落地并验证后描述current behavior，不写work unit过程、未来计划或文件流水账。

## 10. Error handling 与 invariants checklist

Implementation/review必须逐项核对：

- mutex busy与mutex unavailable是两个closed outcome：前者RO，后者attach error；禁止把任意异常吞成RO。
- Session不存在在mutex分配前返回NOT_FOUND；不留下lock file handle/registry record。
- 同一Host handle/Session已有RECOVERING/ACTIVE/CLOSING record时，重复attach在任何native acquire前typed conflict；共享runtime只复用唯一对象，独立竞争只由独立open_host表达。
- public mutation rejection发生在actor mutation Future创建前；Run-id解析只允许read。
- registry ACTIVE RW是唯一public permission truth；RECOVERING/CLOSING都拒绝user mutation。
- lease跟随底层Future/task，而非caller awaiter；caller cancellation不释放资源。
- 单attachment release顺序永远是new-work gate→本attachment actor-bound mutation drain→pre-start work lease drain→native close，且不关闭scheduler/existing stable Attempt；Host close专用顺序严格为public/new-work gate→wait poller stop→actor全局drain→全部attachment mutation/pre-start drain但保持mutex→scheduler lifecycle close（background/promotion stop、token/hook传播、active worker/task/handle/lane清理、host instance `STOPPING -> STOPPED`）→native close/attachment record删除→其余owner。
- scheduler lifecycle close的mandatory cleanup与durable `STOPPED`未完成时，attachment保持`CLOSING`且mutex/record不释放；close可重试，cleanup异常不得通过`_close_cleanup_done`、best-effort日志或继续关闭下游owner伪装成旧execution owner已安全quiesce。
- close不得force unlock或引入新默认timeout；pre-start provider必须复用既有Runner/provider timeout与frozen attempt budget。
- stable Attempt/execution continuation不依赖attachment；任何新Attempt创建都依赖work lease。
- old scheduler detach后不能promotion；current owner必须有bounded durable reconciliation保证liveness。
- target recovery所有SQL都显式包含session id；没有默认None代表全workspace的兼容分支。
- recovery fixed watermark之后的新Run不延长attach scan；留给active RW periodic reconciliation。
- production periodic loop只按interval调用production/test共用one-shot reconciliation；测试direct-call one-shot且不sleep。
- page wake只在commit后；失败attach不返回RW。
- mutex可获取不参与orphan classifier。
- proactive operation id与request event id同源；每Run/input最多一条request。
- prepared proposal manifest先于provider call，因此crash恢复保守消耗attempt；不重复attempt number。
- root/repair/tier共享frozen semantic budget；Runner transport retry不进入该count。
- incomplete/invalid状态只允许同operation terminal/fallback；不能产生第二request。
- reactive producer以request event id写operation id，并从同一pending policy snapshot冻结request max；`engine_ingest`只传required `first_attempt_number=1`与同源`max_attempt_number`，reactive operation count/overflow/recovery/fallback pipeline保持原owner和验收。
- cancel authorization不读取origin；physical propagation只检查current exact dispatch owner identity。
- watchdog durable closeout即使先完成，也不能让owner失去durable cancel link。
- terminal Run上的exact cancel query不按status过滤；返回四元identity+cancel_request_event_id，linked CANCEL_REQUESTED错链/坏payload fail closed，stale identity只过滤不误配。
- direct/headless/script/test harness public mutation caller显式拥有attachment lifecycle；Service不代持、不推断。
- cross-opener observer无transient delta是预期contract，不增加持久化或proxy。
- 所有new/modified签名强类型；无`Any`、`object`、loose payload、`getattr/hasattr` fallback、lazy import或compat re-export/wrapper。

## 11. Risks、open questions 与 rollback boundaries

### 11.1 Blocking questions

无。design/control已经裁决public shape、owner、recovery入口、cancel语义、配置删除和non-goals；最新代码没有出现需要猜测的architecture/contract/scope缺口。

### 11.2 Residual risks

1. **跨平台native syscall差异**：当前本地只能实际运行当前OS backend；Windows backend必须在受支持Windows环境执行同一`tests/runtime/test_native_mutex.py`。unsupported或不可识别errno一律fail closed，避免伪安全。
2. **detach latency**：graceful detach必须等待已经开始的provider call按既有 `RunnerSpec.default_timeout_seconds`、provider transport timeout与冻结的剩余semantic attempt budget收口，不能为了缩短等待提前unlock。该延迟是安全选择，不新增detach/Host默认timeout或force unlock；若实施发现绕过既有bound的provider path，本Slice阻塞而不是降级。
3. **crash时provider结果不可恢复**：manifest已提交但provider结果未写durable时，恢复会保守消耗该attempt并在剩余budget内发下一proposal；可能重复外部计算，但不会创建第二durable operation或重复attempt number。没有provider级idempotency证据，因此不承诺外部call exactly-once。
4. **poll-based cross-opener liveness**：无proxy/notification条件下，current RW scheduler推进old owner terminal后的queue最多等待一个dispatch poll interval；语义测试直接调用production one-shot step，loop wiring用可控迭代，不依赖wall-clock sleep。
5. **fresh schema boundary**：requested event shape与config shape按全新schema处理，不兼容旧DB/旧workspace config；旧config明确拒绝。若未来要求upgrade，必须另开migration WU，不能在本实现加入兼容parser。
6. **MIMO-003（延期到implementation review）**：本plan fix不因行数或方法数预判 owner 模块“注定过度复杂”，也不为此扩scope；合并后Slice 2与Slice 3的implementation review必须按实际diff检查`dispatch.py`、`open_host.py`、`session_attachment.py`的职责分布、private helper边界、constructor dependency与semantic ownership drift。只有直接代码证据成立时才提出拆分finding。

### 11.3 Slice rollback

- Slice 1可独立回滚新增primitive/registry，无public行为。
- Slice 2作为attachment+gate+recovery+proactive typed operation/config删除的单一release unit整体回滚；不能只回滚recovery、scheduler gate或resume reader中的一部分，也不存在可发布的attachment-only rollback点。
- Slice 3 cancel reconcile可独立回滚到durable-only caller fast path，但WU不能宣告完成；README必须随实际代码回滚。

## 12. Why this is not over-designed

- 只新增一个stdlib layer-neutral native primitive、一个Host registry owner和一个proactive typed projection owner；没有新service、daemon、DB table、IPC或distributed coordination system。
- 复用现有SQLite transaction/CAS、EventLog canonical facts、dispatch owner host instance、positive orphan proof、proposal manifests、watchdog和scheduler poll interval。
- mutex只提供机械互斥，业务语义仍在Host registry；没有把文件锁升级成durable truth。
- 不增加fence/lease/TTL/leader/proxy，因为同Session live RW唯一性与existing Attempt owner已足够表达第一版需求。
- 不修改`dayu/engine/**`或transient delivery；reactive只在Host `engine_ingest.py`机械适配required request schema/attempt range，既有count、overflow、recovery与fallback状态机不变。
- 删除一个无owner配置面，状态机比可调count更小；attempt恢复复用既有manifest而不是增加retry ledger。
- Service不增加透传facade，UI只在现有session execution lifecycle多持有一个public resource。

## 13. Implementation completion report format

后续implementation gate完成时必须按以下格式报告：

```text
status: complete | blocked
work unit: WU-CTX-04
slices completed: 3/3（逐slice列出completion signal；Slice 2必须报告attachment/recovery/proactive联合checkpoint）
changed files:
  - <path>: <owner-level change>
public contract/schema/state machine:
  - <exact contract changes>
key direct evidence:
  - <before/after function or invariant>
validation:
  - focused tests: <commands + pass counts>
  - full tests: <command + pass count>
  - pyright: <command + zero errors>
  - per-file coverage: <each changed production file percentage, all >=80%>
  - stale greps: <zero active-surface matches>
  - git diff --check: pass
README/docs:
  - <each trigger and decision>
blocking questions: none | <exact blocker>
residual risks:
  - <platform/operational risks only>
```

不得用“测试大致通过”“覆盖率整体足够”替代精确命令、pass count和逐文件coverage；不得把design/control总控既存改动归为implementation changed files。

## 14. Plan artifact self-check

- [x] goal/motivation/success signal
- [x] non-goals/scope boundary
- [x] design alignment、first-principles判断和直接代码证据
- [x] semantic owners
- [x] affected files/modules
- [x] public contract/schema/state machine/interface changes
- [x] exact functions/classes/types/call paths/data flow/state transitions/error handling/invariants
- [x] 3个slice的依据、allowed files、prerequisites、exact changes、non-goals、tests/assertions、completion signal；原Slice 2/3因无稳定checkpoint已合并
- [x] same/different Session public regression、RO pre-write rejection、detach/drain/re-attach
- [x] Host-close scheduler-before-unlock barrier、pre-unlock token/hook、same-attach target recovery读取old owner STOPPED与cleanup异常不误release
- [x] target recovery、duplicate accepted wake、incomplete proactive crash recovery
- [x] `engine_ingest.py` reactive新request shape、同源policy attempt snapshot、required first/max call sites与count/overflow/fallback不回归
- [x] cross-opener cancel、partial allocation/cancellation/concurrent close cleanup
- [x] strict-native fail-closed/process-exit release
- [x] old config schema rejection、stale grep、full pyright、per-file coverage target
- [x] README/docs decision、risks/open questions、completion report format
- [x] over-design explanation
