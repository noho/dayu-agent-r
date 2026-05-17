# Host 实施总控

## 文档职责

本文档是 Host 设计与实施的总控文档，负责记录实施工作流、phase 编排、phase 进入 / 退出条件、交付物和验证要求。

本文档不承载新的架构决策，不替代设计文档，不作为实现细节说明书。

## 设计目标

Host 设计与实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- 支持单机多客户端 / 多进程。
- 支持本地 Engine 和远程 Engine 并列执行。

任何 phase plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项设计或实现选择削弱这些目标，应停下来修正 `docs/host/design.md` 后再继续。

## 真源层级

Host 后续计划与实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、远程执行和关键治理路径

docs/host/implementation-control.md
  -> 实施编排文档
  -> 只记录 phases、依赖、进入 / 退出条件、交付物和验证要求
```

术语真源是 `dayu/README.md` 的术语表。phase discussion、phase plan、implementation、review、fix 与 re-review
必须使用该术语表中的定义；不得由 planning / implementation agent 自行重解释 `Session`、`Run`、`Attempt`、
`EventLog`、`USER_INPUT_ACCEPTED`、`EngineEvent stream`、`Host event stream`、`TruncationManager`、
`scope_token` 等术语。若发现术语缺失、冲突或不足以指导实施，应先和用户讨论，并同步更新 `dayu/README.md`
及对应设计文档，再继续推进。

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到 `docs/host/design.md`，再更新本文档的 phase 编排。

## 工作流

Host 实施采用以下工作流：

```text
draft design checkpoint
  -> update implementation-control.md phases
  -> select one phase
  -> discuss and refine the corresponding docs/host/design.md section with the user
  -> update docs/host/design.md if the phase discussion changes architecture
  -> generate handoff implementation-ready plan for that phase
  -> review plan
  -> user confirmation
  -> implement phase
  -> verify
  -> update related docs
```

每个 phase 单独生成 handoff implementation-ready plan。phase plan 必须基于：

- `docs/host/design.md`
- 本文档中对应 phase 的范围、依赖和退出条件

phase plan 不得从旧设计稿、旧代码路径或非真源文档推导架构边界。

phase plan 文档必须放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation、code review、
fix、code re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 phase 的第一步必须是和用户讨论并细化 `docs/host/design.md` 中的对应章节。该讨论属于 `$gateflow` 的 feature
discussion / requirement clarification 阶段，必须在进入 plan gate 前完成。

phase discussion 至少需要确认：

- phase 目标与 success signal；
- 本 phase 是否服务于总控设计目标；
- 对应 `docs/host/design.md` 章节是否足够具体；
- 本 phase 的 scope boundary、non-goals 与 stop conditions；
- 是否存在会阻塞 handoff implementation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。

如果 discussion 发现 `docs/host/design.md` 对应章节不足以支撑直接写 plan，应先更新 `docs/host/design.md`，再进入该 phase 的 plan。

## 仓库发布约定

Host 设计与实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

## Slice 切分原则

每个 phase 内的 implementation slices 在该 phase discussion / phase plan 阶段再具体确定；总控阶段不预先替各 phase 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界或 projection 边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令和后续 slice 可依赖的稳定交付物。

如果一个 phase 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 phase plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，phase plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## Phase 条目模板

Phase Map 中每个 phase 必须使用统一条目格式。模板如下：

```md
### Phase N. 名称

目标：
- ...

对应设计章节：
- `docs/host/design.md` §...

前置条件：
- ...

进入条件：
- ...

范围：
- 允许修改：
- 禁止修改：

不做：
- ...

关键设计问题：
- 必须在 phase discussion 中确认：
- 若改变架构，先写回 `docs/host/design.md`：

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: ...
- Slice 2: ...

验证要求：
- unit tests:
- integration tests:
- pyright:
- docs:

退出条件：
- ...

后续依赖：
- 后续 phase 可依赖的稳定契约：
- 需要追踪到后续 phase 的事项：
```

字段含义：

- 目标：该 phase 完成后系统新增或稳定下来的能力。
- 对应设计章节：phase plan 的架构依据，只能引用 `docs/host/design.md` 和本文档，不得引用旧讨论稿。
- 前置条件：必须已经完成的 phase、前置修正或外部确认。
- 进入条件：开始该 phase discussion / plan 前必须满足的状态，例如设计章节已细化、无 blocking open question。
- 范围：允许修改和禁止修改的模块 / 文件 / 层级；用于防止 scope creep。
- 不做：明确排除的能力、兼容性、性能优化、远程能力或后续 phase 内容。
- 关键设计问题：phase 第一步必须和用户讨论确认的问题；若结果改变架构，先写回 `docs/host/design.md`。
- 交付物：该 phase 需要产出的设计细化、plan、代码、测试和文档。
- 建议 slice 切分：总控给初始建议，最终 slices 在 phase discussion / phase plan 中确定。
- 验证要求：该 phase 必须通过的测试、pyright、文档同步和必要的手工验证。
- 退出条件：phase 可以被认定完成的客观条件。
- 后续依赖：后续 phase 可以依赖的稳定契约，以及必须转交到后续 phase 的 tracking items。

## 强制约束

以下约束均来自 `docs/host/design.md` 与 `dayu/README.md` 的终态设计语义；本文档只作为实施护栏重复列出，不引入新的架构决策。

- Host 后续每个复杂 work unit、phase plan、public contract change、schema / storage change、state-machine change
  和 architecture-sensitive task 都必须遵循 `$gateflow` 工作流。
- `docs/host/design.md` 只写终态架构语义，不写 review 过程、用户确认过程、历史讨论、迁移痕迹、上一版对比或临时 open question。流程约束、裁决记录和追踪项分别写入本文档或 `docs/reviews/`。
- phase plan、implementation 或 fix 过程中如果需要修改 Engine 代码，必须立即停下来向用户确认。未经用户明确确认，
  不得把 Engine 代码修改夹带进 Host phase。
- phase plan、implementation 或 fix 不得让 Engine 理解 Host 状态、memory、guidance、steer、fetch_more 或 tool governance。
- phase plan、implementation 或 fix 不得让 EngineEvent `tool_awaiting` / `run_suspended` 创建 wait record、推进 Run
  `WAITING` 或关闭 Attempt；Tool Awaiting canonical owner 是 ToolRuntime Host accept path。
- phase plan、implementation 或 fix 不得把 Engine provider overflow / `context_compaction_requested` 当作 proactive
  context governance；proactive compaction 属于 Host Context Governance，Engine overflow 只是 reactive fallback。
- phase plan、implementation 或 fix 不得把 projection / timeline / audit / trace / outbox 当事实真源。
- phase plan、implementation 或 fix 不得把旧 Attempt resume / takeover 作为实现方案。
- phase plan、implementation 或 fix 不得让 RemoteStub / EngineWorker append EventLog、关闭 Attempt、更新 Run。
- phase plan、implementation 或 fix 不得引入重 lease / fencing 系统替代 admission + SQLite transaction + CAS。
- phase plan、implementation 或 fix 不得把 lane token、`dispatching`、`dispatcher_instance_id` 当作 Host truth、
  lease / fencing token 或 Attempt owner；lane 只能表达资源容量，不能替代 admission、事务、CAS 或 EventLog ordering。
- phase plan、implementation 或 fix 不得让远端 sequence、内存 notification 或 projection checkpoint 替代 Host 分配的全局 `event_sequence`。
- phase plan、implementation 或 fix 不得把 assistant final answer 自动升级为 verified fact。
- phase plan、implementation 或 fix 不得让 `fetch_more` 走 Host / Engine 特化分支。
- phase plan、implementation 或 fix 不得让 Host 包 import 具体业务工具模块、扫描业务工具或在 per-run request /
  metadata 中塞 raw `ToolBundle`；业务 `ToolBundle` 由外部装配作为 Host construction / composition root 输入。
- phase plan、implementation 或 fix 不得让 replay Attempt 暴露 tool schemas 或执行工具；Replay 是 no-tool 结构修复，
  ToolRuntime 拒绝 tool call 只是 defense-in-depth。
- phase plan、implementation 或 fix 不得把 `resolve_wait` 实现成长阻塞等待、轮询或持有外部 job 的循环；它只接收
  poll / callback / manual 已带回的结果，并通过短事务纳入 Host governance。
- phase plan、implementation 或 fix 不得把 memory projection lag 当作 Run recovery，也不得因此把 Run 推入
  `RECOVERING`。
- phase plan、implementation 或 fix 不得让 `purge_session` 删除 append-only audit JSONL；purge 必须保留 tombstone /
  audit record，并让 audit 查询能识别源 EventLog facts 已被 purge。
- phase plan、implementation 或 fix 不得把语义级重复工具调用治理放进 Engine；它属于 Host / ToolRuntime。
- phase plan、implementation 或 fix 不得让 sink 失败影响 EventLog append 或 Run terminal。
- phase 讨论、plan、implementation、review、fix 或 re-review 过程中出现 material open question 时，必须停下来和用户讨论；
  不得让 planning / implementation agent 自行选择会影响架构、公共接口、状态机、schema、持久化、并发、恢复、测试期望或用户可见行为的方案。
- 每个 phase 产生的潜在影响、未覆盖项、deferred risk、后续 phase 依赖和明确不做项，必须回写到本文档的追踪区；
  不得只保留在对话、临时 artifact 或 phase plan 中。

## 当前状态

约束：本节只保留当前 gate 结论；phase 过程流水必须归档到 `历史记录`，仍需追踪的风险或后续 owner 必须写入 `Open Questions 与风险追踪` 的 `追踪区`。

当前 work unit：P9.5 Pre-P10 Cross-Repository Hardening PR。
当前 gate：P9.5 design discussion accepted。
下一 gate：P9.5 implementation-ready handoff plan。

## Phase Map

Phase 按依赖关系推进：先实现被其它阶段依赖的公共契约、runtime 基础能力、durable store、EventLog 与状态机，再连接执行路径、工具治理、projection core、memory、context governance、recovery 与 remote。Audit、Tool Trace、Outbox 是独立 projection sinks，后置到核心治理路径稳定之后实现。Phase 0 是 Engine cleanup 前置 work unit，只阻塞 Phase 10 Context Governance，不阻塞 Phase 1-9。每个 phase 开始时仍必须先和用户讨论并细化对应 `docs/host/design.md` 章节，再生成 handoff implementation-ready plan。

### Phase 0. Engine Context Compaction Event 语义前置

目标：
- 清理 Engine context overflow / compaction event 语义，避免 Host implementation agent 把 Engine reactive fallback 误解为 proactive context governance。
- 本 phase 只阻塞 Phase 10 Context Governance / Compaction；不阻塞 Phase 1-9 的 Host foundational work。

对应设计章节：
- `dayu/engine/README.md`
- `docs/engine/design.md`
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §25.1 Compact Event 响应路径
- `docs/host/implementation-control.md` 追踪区 `Engine Context Compaction Event 语义前置`

前置条件：
- 用户明确确认允许修改 Engine 代码。

进入条件：
- 明确本 phase 只修正 Engine contract / README / tests，不把 context budget governance 放进 Engine。

范围：
- 允许修改：Engine context overflow event contract、Engine README、Engine design docs、相关 Engine tests。
- 禁止修改：Host 实施代码、Host compaction policy、Host recovery state machine。

不做：
- 不实现 Host Context Governance。
- 不实现 provider-specific tokenizer。
- 不做 Engine proactive compaction。

关键设计问题：
- 必须确认 `budget_state` unknown / optional 的最终表达。
- 若改变 EngineEvent 公共契约，先写回相关 Engine 文档。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Engine contract / dataclass / tests cleanup。
- Slice 2: Engine README / docs/engine/design.md / dayu/README.md 同步。

验证要求：
- unit tests: Engine context overflow event contract tests。
- integration tests: 现有 Engine context overflow 路径不回归。
- pyright: 全量或受影响包通过。
- docs: Engine README 与 design docs 同步。

退出条件：
- Engine overflow event 明确表达 reactive fallback 与 unknown budget，provider overflow path 使用 `budget_state=None`。

后续依赖：
- 后续 phase 可依赖的稳定契约：Engine 只发出 reactive overflow signal，不做 Host proactive compaction。
- 需要追踪到后续 phase 的事项：Phase 10. Context Governance / Compaction 必须使用 Host estimator / policy 自主判断 budget。

### Phase 1. 公共契约与 runtime 基础设施

目标：
- 建立 Host 后续实现依赖的稳定类型、公共 request / snapshot / enum、`dayu.runtime` 基础能力与外部工具 / 场景装配边界。

对应设计章节：
- `docs/host/design.md` §3 dayu.runtime
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `dayu/README.md` 术语约定与 Runtime

前置条件：
- `dayu/README.md` 术语真源已覆盖本 phase 引入的命名。

进入条件：
- 确认哪些类型属于 `dayu.contracts`，哪些类型留在 `dayu.host` 内部。
- 确认 Host 公共 API 类型放在 `dayu.host` 公共命名空间，`dayu.contracts` 只保留 Host / Engine / ToolRuntime 共同理解的层间协作契约。
- 确认 ToolsDiscovery / ScenePrepare 在本 phase 只固定边界并后置具体实现，不作为 Phase 1 implementation slice。
- 确认 `docs/host/design.md` §3.1 / §3.2 已细化 `dayu.runtime.lane` 与 `dayu.runtime.filelock` 的 public API shape、生命周期、错误语义、non-goals、import boundary 和测试点。

范围：
- 允许修改：公共契约、Host request / snapshot / error typing、Host construction typed options 中的 `ToolBundle` 输入边界、`dayu.runtime.lane`、`dayu.runtime.filelock`、ToolsDiscovery / ScenePrepare 的层中立责任边界说明。
- 禁止修改：Host durable state machine、Engine 执行路径、业务财报工具实现。

不做：
- 不实现 Host SQLite durable store / EventLog store；`dayu.runtime.lane` 的独立 SQLite lane DB 只用于 runtime capacity coordination。
- 不实现 Host command path。
- 不实现业务工具扫描或财报场景 prompt。
- 不实现 ToolsDiscovery / ScenePrepare 具体 adapter、manifest schema、provider 注册生命周期或业务装配代码。

关键设计问题：
- 必须确认 Host API 类型放置位置与 import 边界。
- 必须确认 `ToolBundle` 作为 Host construction input 的 typed options 形状。
- 必须确认 `dayu.runtime.lane` 第一版是 cross-process named semaphore / capacity guard primitive，使用独立 runtime SQLite lane coordinator 表达跨进程 capacity claim；采用 claim token acquire / release / heartbeat 生命周期；等待 acquire 可取消，持有 claim token 时由 owner task 在 cancel / shutdown 的 `finally` 或 context helper 中 release；不承诺 FIFO、公平性、分布式跨机器容量、lease / fencing、Attempt owner、Attempt takeover 或 recovery proof。
- 必须确认 `dayu.runtime.filelock` 第一版只提供同步 wrapper；第三方 `filelock.FileLock` 只能由 `dayu.runtime.filelock` 直接导入；timeout、路径、parent directory、release、stale lock、reentrancy 和错误语义必须按 `docs/host/design.md` §3.2 实施。
- 若 runtime helper 需要第三方依赖，必须确认它仍满足 `dayu.runtime` 层中立约束；`filelock` 依赖只能封装在 `dayu.runtime.filelock`。
- 必须按 slice 分别确认 public typing、runtime infra、ToolBundle construction input。ToolsDiscovery / ScenePrepare 只作为后续 Phase 12 的 boundary constraint；Phase 1 不实现它们，Phase 12 必须补齐 typed manifest / provider contract。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Host API request / snapshot / error / status 类型。
- Slice 2A: `dayu.runtime.lane` cross-process named semaphore / capacity guard primitive、`LaneConfig`、`SQLiteLaneCoordinatorConfig`、`LaneOwner`、`LaneController`、`LaneClaimToken`、acquire outcome、claim TTL / heartbeat、stale claim cleanup、cancel / timeout / close 语义、multi-process capacity tests 与 import boundary tests。
- Slice 2B: `dayu.runtime.filelock` sync wrapper、`RuntimeFileLockOptions`、`RuntimeFileLock`、`RuntimeFileLockToken`、timeout / parent directory / release / third-party error wrapping 语义与 import boundary tests。
- Slice 3: Host construction `ToolBundle` typed options、tool bundle source refs、framework tool reserved-name policy view。
- Deferred Slice: ToolsDiscovery / ScenePrepare 具体 typed interface 与 adapter 实现；不进入 Phase 1 implementation-ready plan。用户指定 deferred destination 为 P12；Phase Map 已重排为 Phase 12 ToolsDiscovery / ScenePrepare，原 Audit / Tool Trace / Outbox Projections 后移到 Phase 13。

验证要求：
- unit tests: contract validation、runtime lane / filelock behavior。
- lane unit tests 必须覆盖：重复 lane name / 非正 capacity / 非法 TTL 配置错误、未知 lane acquire 错误、独立 runtime SQLite lane DB 初始化、成功 acquire / heartbeat / release、重复 release 不影响其它 claim、`timeout_seconds=0` non-blocking acquire、正 timeout 返回 timed out、等待 acquire 被 `CancellationToken` 取消返回 cancelled、外层 `asyncio.Task.cancel()` 透传、`LaneController.close()` 取消 pending acquire 并 best-effort release 当前 controller tokens、不承诺 acquire ordering。
- lane multi-process tests 必须覆盖：多个独立 Python 进程共享同一 lane DB 时 successful claims 总数不超过 capacity；capacity 满时另一个进程 non-blocking acquire timed out；正常 release 后其它进程可 acquire；持有 claim 的进程崩溃或停止 heartbeat 后，TTL 过期并清理 stale claim 后其它进程可 acquire。
- filelock unit tests 必须覆盖：parent directory creation、`create_parent_dirs=False` 缺 parent 时错误、context manager release、重复 release 幂等、timeout / non-blocking acquire 错误包装、第三方 `filelock` import 不散落到 Host / Service / Fins / Engine、wrapper 不用于 SQLite / EventLog truth 的文档边界。
- integration tests: runtime lane multi-process capacity / stale claim cleanup；Host integration tests 无。
- pyright: 相关包无新增错误。
- docs: `dayu/README.md` 与受影响包 README 同步。

退出条件：
- typed contracts 存在且从 `dayu.host` 公共命名空间可导入：Host handle / command facet type、`HostCallContext`、`OperationContext`、Host request 类型、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventStream`、Session / Run / Attempt status enum、Host API error code、stream cursor 类型。
- Host construction typed contracts 存在且从 `dayu.host` 公共命名空间可导入：`HostToolingOptions`、`ToolBundleSourceRef`、`ToolBundleSourceKind`、`FrameworkToolName`、`FrameworkToolPolicyView`。`ToolBundleSourceKind` 与 `FrameworkToolName` 必须使用 Python 3.11 `enum.StrEnum`，不得使用普通 `str` 常量或 `typing.Literal`。
- `FrameworkToolPolicyView` 是 frozen dataclass 风格类型，至少包含 `reserved_framework_tool_names: frozenset[FrameworkToolName]` 与 `enabled_framework_tools: frozenset[FrameworkToolName]`；Phase 1 只定义 construction-time framework-tool policy view，不实现 ToolRuntime 注入或完整 `ToolGovernancePolicyView`。
- `dayu.runtime.lane` 存在并实现 `LaneConfig`、`SQLiteLaneCoordinatorConfig`、`LaneOwner`、`LaneController`、`LaneClaimToken`、`LaneAcquireOutcome`；满足 cross-process runtime capacity claim、独立 runtime SQLite lane DB、可取消 acquire、timeout、close pending acquire、claim TTL / heartbeat、stale claim cleanup、幂等 release、无 FIFO / fairness guarantee、无 Host truth / lease / fencing / Attempt owner / Attempt takeover / recovery proof 语义。
- `dayu.runtime.filelock` 存在并实现同步 `file_lock(...)` wrapper、`RuntimeFileLockOptions`、`RuntimeFileLock`、`RuntimeFileLockToken`；满足 parent directory、timeout、第三方 timeout error wrapping、幂等 release、无 stale lock takeover、无 reentrancy guarantee、无 SQLite / EventLog / Host truth 语义。
- `dayu.runtime.lane` 与 `dayu.runtime.filelock` 满足层中立 import boundary；`dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- unit tests 覆盖 Host public contract validation、`ToolBundle` construction input validation、reserved framework tool name 冲突、`dayu.runtime.lane` 设计要求、`dayu.runtime.filelock` 设计要求；multi-process tests 覆盖 runtime lane DB capacity invariant 与 stale claim cleanup。
- pyright 在相关包上通过，且不新增、不扩散类型错误。
- docs 按 README 触发规则同步：`dayu/README.md`、受影响包 README、`tests/README.md` 只在职责范围内更新。
- 明确 non-goals 仍未实现且测试不期待这些能力：Host SQLite durable store / EventLog store、Host command path、Engine 执行路径、ToolRuntime policy resolution / framework tool 注入、ToolsDiscovery / ScenePrepare 具体 adapter、manifest schema、业务工具扫描、财报场景 prompt。

后续依赖：
- 后续 phase 可依赖的稳定契约：Host public typing、runtime helper、ToolBundle construction input。
- 需要追踪到后续 phase 的事项：具体 Host store / command path 不在本 phase 落地；RunInputBuilder typed input provider protocols 在 Phase 5 建立，不在本 phase 落地，Phase 5 必须保持与本 phase 公共类型风格和 import boundary 一致；ToolsDiscovery / ScenePrepare 具体 adapter 与 manifest / provider typed contract 按用户要求 deferred destination 标记为 Phase 12，不能夹带进 Phase 1。

### Phase 2. Durable Store / EventLog / Payload Foundation

目标：
- 建立 SQLite durable truth、EventLog append primitive、payload descriptor、idempotency record、host instance liveness 与事务边界。

对应设计章节：
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §13 EventLog
- `docs/host/design.md` §13.1 Payload 存储
- `docs/host/design.md` §27 Host Lifecycle / Recovery

前置条件：
- Phase 1 公共类型与 runtime helper 已完成。

进入条件：
- 确认第一版 SQLite schema convention、transaction runner、WAL / busy timeout、retry policy、payload threshold 与 artifact 目录注入方式；确认形式为用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 schema / typed contract / test matrix。

范围：
- 允许修改：SQLite connection / transaction runner / WAL / busy timeout、schema bootstrap convention、EventLog table 与 appender / reader、payload table / descriptor table、idempotency table、host instance liveness foundation。
- 禁止修改：WorkerProxy、ToolRuntime、Projection、Memory、Remote transport。

不做：
- 不实现完整 Host API。
- 不 dispatch Engine。
- 不实现 projection sink。

关键设计问题：
- 必须确认 EventLog row、canonical event identity、event_sequence、payload descriptor 的 typed contract。
- 必须确认 SQLite 多进程写入配置和测试策略。

已确认的 Phase 2 durable foundation 决策：
- SQLite schema convention：第一版使用单个 Host SQLite durable DB；fresh bootstrap 创建 schema 并设置 / 校验 `PRAGMA user_version`；durable ids 使用 TEXT；durable timestamp 使用 UTC ISO-8601 TEXT，固定微秒精度并使用 `Z` 后缀；结构化 JSON 使用 canonical JSON TEXT；唯一性用显式 unique index / primary key 表达；启用 foreign keys；不做旧库兼容读取、兼容迁移或旧 schema fallback。
- Transaction runner：Host write transaction 是短事务，使用 `BEGIN IMMEDIATE`；连接启用 WAL、明确 busy timeout 与 `foreign_keys=ON`；只对 SQLite busy / locked 类短事务失败做有限 retry；唯一约束冲突、外键错误、schema mismatch、digest mismatch、idempotency conflict、CAS precondition failed 不 retry；after-commit wakeup 只在 commit 成功后触发。
- EventLog / idempotency：`event_sequence` 是 Host durable store 分配的全局 INTEGER cursor；`event_id` 是 TEXT ledger identity 并全局唯一，所有 event class 都必须有 ledger identity；idempotency primitive 以 `(scope_kind, scope_id, idempotency_key)` 唯一绑定 `semantic_input_digest` 与 result ref，同 key 不同 digest 返回 `idempotency_conflict`。
- Payload foundation：Phase 2 只支持 `sqlite_payload` 与本地 `artifact_ref` 最小 descriptor；Host composition root 注入 `payload_inline_threshold_bytes` 与 artifact root；大 payload 必须先 durable 写入 artifact root、digest verify、atomic rename，再在 SQLite transaction 中写 descriptor 与 EventLog。
- Host instance liveness：Phase 2 只实现 register current instance、heartbeat current instance、mark stopping / stopped best-effort、read instance row；不实现 positive orphan proof classifier，不读取 dispatch record，不引入 lease / fencing / Attempt takeover。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: SQLite schema convention / migration-free fresh DB bootstrap / transaction runner。
- Slice 2: EventLog append / read / event_sequence / idempotency primitive。
- Slice 3: payload descriptor / host instance liveness / diagnostics foundation。

验证要求：
- unit tests: transaction atomicity、event_sequence monotonicity、idempotency conflict。
- integration tests: SQLite WAL / busy timeout / concurrent append smoke。
- pyright: Host store 模块通过。
- docs: Host README 或开发说明按触发规则同步。

退出条件：
- 后续 phase 能在一个事务内 append canonical facts、更新 state indexes，并可用 EventLog cursor 补读；后续 phase 增加的 tables 必须遵守本 phase 的 schema convention、transaction discipline 与全新 schema 起库约束。

后续依赖：
- 后续 phase 可依赖的稳定契约：SQLite durable truth、schema convention、EventLog append / read、payload descriptor、idempotency primitive、host instance liveness。
- 需要追踪到后续 phase 的事项：Session / Run / Attempt tables 由 Phase 3 拥有，wait record table 由 Phase 7 拥有，projection / memory / context / audit / trace / outbox / purge tombstone tables 由各自 phase 拥有；projection 与 recovery 只消费本 phase 提供的 durable primitives。

### Phase 3. Session / Run / Attempt 状态机与 Admission

目标：
- 实现 Session slot、Session lifecycle、Run / Attempt lifecycle、admission、durable queue、promotion 与 CAS-style state transition。

对应设计章节：
- `docs/host/design.md` §5 Session 生命周期
- `docs/host/design.md` §6 Session Slot
- `docs/host/design.md` §7 Run 生命周期
- `docs/host/design.md` §8 Attempt 生命周期
- `docs/host/design.md` §9 Admission 与多进程并发
- `docs/host/design.md` §9.1 状态迁移契约
- `docs/host/design.md` §10 Durable Store

前置条件：
- Phase 2 durable store 与 EventLog foundation 已完成。

进入条件：
- Phase 3 design refinement 的 BQ1 / BQ2 / BQ3 已由 controller 裁决并经用户确认。
- `docs/host/design.md` 已写回 Phase 3 owned transition subset 与 durable state / index contract。
- 当前状态仍是 design fix / write-back；完成 design re-review 且无 blocking question 后，才允许进入 plan gate。

范围：
- 允许修改：Session / Session slot tables、Run / Attempt tables、minimal dispatch record row、active index、queue index、transition service、admission service、promotion service。
- 禁止修改：Engine dispatch、ToolRuntime、Projection、Remote transport、dispatch scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy。

不做：
- 不启动 Engine。
- 不实现 public API 全量 facade。
- 不实现 recovery scan。
- 不实现 EngineEvent ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction。
- 不把 dispatch record 推进到 `dispatching`，不 append `ATTEMPT_RUNNING`。

关键设计问题：
- 已确认 Phase 3 创建 minimal dispatch intent / dispatch record row，但只写 `pending` / `cancelled`；scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch 与 `ATTEMPT_RUNNING` 属于 Phase 5 或后续。
- 已确认 Phase 3 必须补齐 durable state / index / CAS / idempotency contract；active Run invariant 第一版优先采用 SQLite partial unique index on active Run statuses。
- 已确认 Phase 3 只覆盖 Session lifecycle、start / follow-up admission、queue promotion、cancel queued、cancel pre-dispatch starting、internal terminal closeout helper、terminal / cancel 后 promotion trigger；跨 phase matrix 行只作为 future-owner references。
- 若 plan agent 发现 operation idempotency scope / digest / result ref、CAS preconditions 或 dispatch record row contract 仍不足以直接实现，必须停下交给 controller，不得自行选择。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Session / slot lifecycle 与 idempotency。
- Slice 2: Run / Attempt transition service 与 CAS tests。
- Slice 3: admission / durable queue / promotion。

验证要求：
- unit tests: state transition matrix。
- integration tests: 同 Session 并发 start / follow-up / queue promotion。
- multi-process tests: 同 slot 并发 `ensure_session` 返回同一 Session 且不产生调用方可见孤儿 Session；同 Session 并发 start / follow-up 至多一个 active Run；重复 `(session_id, client_request_id)` 返回同一 Run，digest 不同则结构化冲突；active Run 存在时 follow-up queue 生成按 accepted `event_sequence` FIFO 的 durable queued Run；terminal / cancel 释放 active slot 后只 promotion 一个 queued Run；cancel queued 与 promotion 遵循 first-committer-wins；cancel pre-dispatch starting 将 dispatch record 标记为 `cancelled` 且不 dispatch；EventLog `event_sequence` 跨进程全局单调。
- pyright: Host state 模块通过。
- docs: Host README 按触发规则同步。

退出条件：
- Host 可以在不启动 Engine 的情况下正确接受、排队、启动、取消 queued / pre-dispatch starting，并通过内部 terminal closeout helper 收口 Run / Attempt state indexes 与触发 promotion。
- Phase 3 implementation artifact 必须明确未实现 Engine dispatch、WorkerProxy、LocalProxy、RemoteProxy、EngineEvent ingest、Tool awaiting、recovery，并把它们转交给对应后续 phase。

后续依赖：
- 后续 phase 可依赖的稳定契约：Session / slot lifecycle、active Run admission、durable queue、promotion、CAS transition service、Attempt STARTING + dispatch record pending startup truth。
- 需要追踪到后续 phase 的事项：Phase 5 owns scheduler、lane acquire、WorkerProxy / LocalProxy、Engine dispatch、dispatch record `dispatching` 与 `ATTEMPT_RUNNING`；Phase 11 owns recovery scan、positive orphan proof、RECOVERING dispatch；其它 cross-phase matrix rows 由对应 phase owner 接入。

### Phase 4. Host Public API Command Path

目标：
- 落地不依赖执行、等待或投影清理的函数式 Host command path、HostCallContext、OperationContext、幂等语义、snapshot 读取与 command path / background runtime facet 分离。

对应设计章节：
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §12 Follow-up 与 Steer
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 3 状态机、admission 与 durable store 已完成。

进入条件：
- 确认 API request / response / error shape 已足够实现多入口稳定边界。

范围：
- 允许修改：Host handle / factory、public API functions、HostCallContext validation、idempotency handling、SessionSnapshot / RunSnapshot / FollowupSnapshot / PurgeSessionResult。
- 禁止修改：Engine dispatch、ToolRuntime、Projection worker、Remote transport。
- 完整实现：`ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、`submit_followup(queue)`、`get_run`、`stream_run_events`、queued / pre-dispatch `cancel_run`。
- 子集实现：`cancel_session_runs` 只覆盖 queued / pre-dispatch `STARTING`；dispatching / active worker、`WAITING`、`RECOVERING` cancel 必须追踪到 Phase 5 / 7 / 11。
- stable unsupported / deferred：`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、active dispatch cancel、wait / recovery cancel。

不做：
- 不实现 Engine execution。
- 不实现 UI / Service channel delivery。
- 不实现 wait adapter。
- 不实现 `resolve_wait` 的等待结果治理语义；该能力在 Phase 7 落地。
- 不实现 `purge_session` 的 destructive cleanup；该能力在 Phase 15 落地。
- 不实现 `submit_followup(steer)` 的 Attempt switching；Phase 4 只冻结 envelope、validation、`HostApiError` / typed detail contract，并通过 `HostApiErrorCode.UNSUPPORTED_OPERATION` 暴露 stable unsupported。
- 不实现 dispatching / active worker、`WAITING`、`RECOVERING` 的完整 cancel；不得把 Phase 4 queued / pre-dispatch cancel 子集写成最终语义。

关键设计问题：
- `submit_followup(queue)` 使用 `accepted_run_id` + `accepted_run_status` 表达 accepted follow-up 结果；无 active Run 时可直接返回新 `RUNNING` Run，不能把 running Run 塞进 `queued_run_id`。
- `HostApiErrorCode` 必须包含 `UNSUPPORTED_OPERATION`；`HostApiError.detail` 是受限 typed detail union，至少包含 steer conflict detail，禁止无结构 extra payload / god bag。
- `submit_followup(steer)` Phase 4 只冻结 public envelope、validation 与 error/detail contract；完整 steer owner 后续 phase。
- `stream_run_events` 以全局 EventLog cursor 为 truth，固定 public `limit`、默认 / 最大 limit、run 过滤、empty result `next_cursor` 与 `HostEventView` 映射；Phase 4 不引入 projection truth。
- `attach_active` 第一版不新增 canonical EventLog fact；返回当前 active `RunSnapshot`，幂等记录可解释 request，audit/read-model 由后续 projection 基于 refs 表达。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: Host handle / typed options / policy views / context validation。
- Slice 2: session APIs 与 snapshots。
- Slice 3: run / follow-up queue / queued and pre-dispatch cancel command path backed by state machine。
- Slice 4: read APIs / EventLog stream cursor / deferred facade stable unsupported。

验证要求：
- unit tests: API idempotency、context validation、error classification。
- integration tests: multi-client style repeated calls and retry after timeout。
- pyright: Host public API 模块通过。
- docs: dayu/README.md / Host README 按触发规则同步。

退出条件：
- 多入口可以通过稳定函数式 API 操作 Host durable state；尚未支持真实 Engine execution 的接口必须以明确状态或受控 fake dispatch 测试。

后续依赖：
- 后续 phase 可依赖的稳定契约：public command path、Host handle、typed options、snapshot shape、API idempotency、read API shape（`get_run` / `get_session` / `stream_run_events` 的 snapshot 与 cursor contract）。
- 需要追踪到后续 phase 的事项：执行、projection、memory、remote 后续接入不得绕过 public command path；Phase 8 依赖本 phase 的 read API shape 与 snapshot / stream cursor contract；`resolve_wait` public signature / request envelope 在本 phase 稳定，等待结果治理语义在 Phase 7 落地；`purge_session` public signature / `PurgeSessionResult` / idempotency contract 在本 phase 稳定，destructive cleanup 在 Phase 15 落地；Phase 5 必须补齐 dispatching / active worker cancel propagation；Phase 7 必须补齐 `WAITING` cancel / wait record cancel；Phase 11 必须补齐 `RECOVERING` cancel / recovery dispatch cancellation。

### Phase 5. RunInputBuilder 与本地执行 Dispatch

目标：
- 连接 RunInputBuilder、Attempt dispatch record、LLM lane、LocalProxy / EngineWorker、EngineEvent ingest 与 terminal 收口，形成本地 Engine 执行闭环。

对应设计章节：
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/design.md` §13.4 EngineEvent 映射
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 4 public command path 已完成。
- Phase 1 runtime lane 已完成。

进入条件：
- 确认第一版 LocalProxy 与 EngineWorker 的 adapter 边界，以及 RunInputBuilder typed provider 最小集合。

范围：
- 允许修改：RunInputBuilder provider protocols、attempt snapshot、dispatch scheduler、LocalProxy adapter、EngineEvent ingest、cancel propagation。
- 禁止修改：Remote wire protocol、ToolRuntime advanced governance、Memory projection、Context Governance。

不做：
- 不实现 RemoteProxy。
- 不实现 full ToolRuntime governance；可使用最小 ToolExecutor / no-tool 或 fake tool path 支撑本地执行闭环。
- 不实现 Observer / Sink。

关键设计问题：
- 必须确认 `AgentRunRequest.messages` 由 canonical facts 重建，不读取 UI 临时文本。
- 必须确认 lane acquire 后 recheck / dispatching / ATTEMPT_RUNNING 的精确 transaction 边界。
- 必须确认 EngineEvent terminal / non-terminal / stream EOF 的 Host 收口规则。
- 已确认 Engine 公共 `EngineEvent` 契约不携带 Host Attempt identity；`attempt_id + execution_id` 由 Host-owned LocalProxy / EngineWorker envelope 绑定并在 Host ingest 边界校验。
- 已确认 Phase 5 fresh schema / typed enum 必须扩展 dispatch record 状态到至少 `pending`、`waiting_for_lane`、`dispatching`、`cancelled`；这些状态只表达 dispatch 诊断与重复派发抑制，不表达 lease / fencing / Attempt owner。
- 已确认 Phase 5 不实现 ToolRuntime governance、wait record 或 `resolve_wait`；`tool_awaiting` / `run_suspended` 不得在本 phase 创建 `WAITING` canonical truth。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: RunInputBuilder typed providers and deterministic messages。
- Slice 2: dispatch scheduler / lane / dispatch record / LocalProxy。
- Slice 3: EngineEvent ingest mapping and terminal closeout。
- Slice 4: cancel propagation and stream EOF failure handling。

验证要求：
- unit tests: RunInputBuilder determinism、EngineEvent mapping、dispatch recheck。
- integration tests: local Engine fake end-to-end run success / failure / cancel。
- pyright: Host execution modules 通过。
- docs: Host README / Engine boundary docs 按触发规则同步。

退出条件：
- 一个已 accepted 的 prompt 能通过本地 Engine path 产生 terminal EventLog fact 与 RunSnapshot terminal result。

后续依赖：
- 后续 phase 可依赖的稳定契约：attempt snapshot、LocalProxy semantic baseline、EngineEvent ingest、dispatch lane semantics。
- 需要追踪到后续 phase 的事项：RemoteProxy 必须保持与 LocalProxy 等价语义。

### Phase 6. ToolRuntime / Truncation / fetch_more / Duplicate Governance

目标：
- 落地 Host-owned ToolRuntime、effective ToolBundle、Host accept barrier、TruncationManager、`fetch_more` 与同 Run 语义级重复工具调用治理。

对应设计章节：
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `docs/host/design.md` §18.2 ToolRuntime Boundary
- `docs/host/design.md` §18.3 语义级重复工具调用治理
- `docs/host/design.md` §19 TruncationManager / fetch_more

前置条件：
- Phase 5 本地执行闭环已完成。
- Phase 2 payload descriptor 与 EventLog append primitive 已完成。

进入条件：
- 确认 ToolRuntime ports、accept idempotency key、effective ToolBundle 与 run-scoped truncation / `fetch_more` 的最小 typed contract；确认形式为用户确认，或 `docs/host/design.md` 对应章节已细化到可直接生成 typed contract / test matrix。

范围：
- 允许修改：ToolRuntime factory、ToolExecutor wrapper、effective ToolBundle、tool fact accept path、TruncationManager、fetch_more framework tool、duplicate index、tool trace diagnostic emitter interface。
- 禁止修改：Engine 工具协议语义、Remote wire protocol、业务工具实现。

不做：
- 不实现长期 memory retrieval。
- 不实现 Remote transport。
- 不做跨 Run / 跨 Session 重复工具治理。

关键设计问题：
- 必须确认工具事实 accepted ack 失败 / timeout 的默认治理动作。
- 必须确认 truncation cursor / `scope_token` 的 run-scoped 边界、失效条件与错误 envelope；Phase 6 不实现 durable cursor descriptor / recovery 续读。
- 必须确认 replay no-tool 防线如何从 RunInputBuilder 与 ToolRuntime 双层执行。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: ToolRuntime ports / effective ToolBundle / schema projection。
- Slice 2: Host accept barrier and tool canonical fact append。
- Slice 3: TruncationManager / fetch_more / run-scoped cursor contract。
- Slice 4: run-local duplicate governance and tool trace diagnostic emitter。

验证要求：
- unit tests: ToolBundle validation、accept idempotency、duplicate policy、truncation scope validation。
- integration tests: fake tool execution through Engine, accepted ack retry, fetch_more normal tool path。
- pyright: ToolRuntime 模块通过。
- docs: dayu/README.md / Host README 工具边界同步。

退出条件：
- Engine 只能通过 Host-governed ToolExecutor 使用工具；LLM 不会消费未 durable accepted 的工具事实。

后续依赖：
- 后续 phase 可依赖的稳定契约：ToolRuntime accept barrier、effective ToolBundle、fetch_more 普通工具路径、tool diagnostic refs。
- 需要追踪到后续 phase 的事项：RemoteProxy 必须支持等价 tool fact accept ack 语义。

### Phase 7. Tool Awaiting / resolve_wait / Wait Adapter

目标：
- 实现长事务等待进入 Host 的 canonical path、wait record、`resolve_wait`、poll / manual adapter 最小能力与 WAITING resume。

对应设计章节：
- `docs/host/design.md` §20 Tool Awaiting / Wait Record
- `docs/host/design.md` §21 Suspend / Resume / Retry / Replay
- `docs/host/design.md` §22 Cancel

前置条件：
- Phase 6 ToolRuntime accept barrier 已完成。
- Phase 5 dispatch / resume attempt creation path 已完成。

进入条件：
- 已确认第一版实现 internal / manual resolve + poll adapter，callback 只预留 adapter contract；已确认 Phase 4 冻结的
  `ResolveWaitRequest.outcome_ref` 需要在 Phase 7 改为强类型等待结果 envelope，至少区分 completed / failed /
  cancelled / lost。

范围：
- 允许修改：wait record table / store、wait adapter durable refs、ToolAwaitingOutcome accept path、resolve_wait command、wait poller background adapter、WAITING cancel / steer / resume。
- 禁止修改：外部系统专属 callback 服务、复杂 job reconcile、强制外部 job cancel。

不做：
- 不保证外部 job physical cancel。
- 不实现 callback 认证入口完整产品化。
- 不实现远端 worker 自治 resume。

关键设计问题：
- 已确认 wait record 必须落地为 Host typed durable model，字段至少覆盖 `wait_id`、`run_id`、`attempt_id`、
  `tool_call_id`、`tool_name`、`adapter_key`、`await_kind`、`resume_token`、`snapshot_ref`、`external_job_id`、
  `idempotency_key`、deadline / expiry、status 与 created / updated event refs。
- 已确认 `resolve_wait` 是非阻塞短事务 command；结果未到应由 poll / callback / manual 入口避免调用，或返回
  `outcome_not_ready`、`invalid_state`、`wait_not_found` 等结构化拒绝。
- 已确认 `WAITING` cancel 后 active wait record 标记 `cancelled`，Run 进入 `CANCELLED`，不创建 resume Attempt；迟到
  poll / callback / manual result 只能进入 diagnostic / tool trace，不得追加 canonical tool result。
- 已确认迟到等待结果不能静默丢弃；Phase 7 必须至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event，作为后续
  tool trace / projection 的输入，不要求本 phase 实现完整 tool trace 投影。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: wait record durable model and ToolAwaiting accept path。
- Slice 2: resolve_wait command path and resume attempt creation。
- Slice 3: poll / manual adapter and WAITING cancel / late result handling。

验证要求：
- unit tests: wait record state machine、resolve_wait idempotency、late result rejection、cancel-vs-resolve first-committer-wins、
  poll adapter observes cancelled wait and stops / abandons observation、late result writes diagnostic EventLog event。
- integration tests: awaiting -> resolve -> resumed local run。
- pyright: wait adapter modules 通过。
- docs: Host README wait / resume 语义同步。

退出条件：
- 长事务工具可以让 Run 进入 WAITING，并由统一 `resolve_wait` 创建新 Attempt 继续。
- `ResolveWaitRequest.outcome_ref` 已被 typed outcome envelope 替代；`observed_at` 类型或解析策略、lost outcome 与
  wait record lost 状态区别、`adapter_key` 来源、`snapshot_ref` / `external_job_id` typed ref 约束均在 plan 与实现中明确。

后续依赖：
- 后续 phase 可依赖的稳定契约：wait record、resolve_wait pipeline、wait poller background runtime。
- 需要追踪到后续 phase 的事项：callback adapter、外部 job cancel / revoke 属于后续能力。

### Phase 8. Projection Core / Host Event Stream / Minimal Read Model

状态：
- P8 completed。PR 58 已达到 `draft-PR-pass`，后续 merge 由用户手工执行。

目标：
- 实现 committed EventLog 消费基础、projection checkpoint、Host event stream cursor 与最小 RunResult / Session timeline read model，为 Memory、Recovery 和后续 projection sinks 提供稳定基座。

对应设计章节：
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

前置条件：
- Phase 2 EventLog foundation 已完成。
- Phase 4 public read APIs 已完成。

进入条件：
- 确认 projection runner、checkpoint、Host event stream 与最小 read model 的边界；Audit、Tool Trace、Outbox 只预留 consumer contract，不在本 phase 落地。

范围：
- 允许修改：projection runner、checkpoint store、typed consumer contract、stream fanout 基础、Host event stream、timeline / RunResult 最小 read model。
- 禁止修改：command path 状态机、Run / Attempt governance state、UI / Service channel delivery。

不做：
- 不实现 `LogAuditSink(JSONL)`。
- 不实现 tool trace hot JSON / cold JSONL。
- 不实现 OutboxSink。
- 不实现外部 audit 系统。
- 不保证 channel delivery exactly-once。
- 不让 terminal transaction 同步写 outbox 表。

关键设计问题：
- 必须确认 projection runner 的 typed consumer contract、checkpoint、幂等键和失败处理。
- 必须确认 Host event stream 只从 EventLog `event_sequence` cursor 补读，不触发执行。
- 必须确认最小 RunResult / Session timeline read model 损坏后可由 EventLog 重建。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: projection runner / checkpoint / typed consumer contracts。
- Slice 2: Host event stream from EventLog `event_sequence` cursor。
- Slice 3: minimal Session timeline / RunResult read model and rebuild path。

验证要求：
- unit tests: checkpoint idempotency、consumer replay、projection rebuild。
- integration tests: terminal EventLog -> Host event stream / minimal timeline / RunResult。
- pyright: projection modules 通过。
- docs: Host README read model / event stream 边界按触发规则同步。

退出条件：
- Projection lag 或 core projection failure 不影响 EventLog append、Run terminal、resume 或 memory truth；Memory phase 可以复用 checkpoint / consumer framework。

后续依赖：
- 后续 phase 可依赖的稳定契约：EventLog replay consumers、projection checkpoint、Host event stream cursor、minimal read model。
- 需要追踪到后续 phase 的事项：Audit / Tool Trace / Outbox 作为独立 projection sinks 后置；Service / UI channel delivery 不属于 Host truth。

### Phase 9. Conversation Memory / Session Memory Projection

状态：
- P9 phase discussion / design refinement 已完成。用户确认 P9 的核心定位是“财报分析工作台状态投影”，不是聊天记录压缩器。
- P9 handoff implementation-ready plan 已完成双路 review、fix、双路 re-review 与 controller adjudication，verdict 为 PASS。
- P9-S1 `Durable Memory Contracts and Schema` completed；accepted slice commit 为 `f221aeb`。
- P9-S2 `Projection Consumer and Stable Layer Builder` completed；accepted slice commit 为 `4f35da6`。
- P9-S3 `RunInputBuilder MemorySnapshotProvider and Lag Fallback` completed；accepted slice commit 为 `b416d37`。
- P9-S4 `Projection Repair / Rebuild Entry and Diagnostics` completed；accepted slice commit 为 `1d30725`。
- P9 aggregate deepreview completed；verdict 为 PASS；accepted deepreview commit 为 `cc05f79`。
- P9 draft PR created：PR 59 https://github.com/noho/dayu-agent-r/pull/59；PR review gate completed，verdict 为 PASS；
  accepted PR review commit 为 `67458cb`。
- P9 all-repository follow-up review 已由 AgentMiMo 与 AgentDS 执行，初审发现若干跨仓 correctness / observability hardening；
  controller 已接受其中低风险项并完成 fix / validation。最新 DS follow-up finding 中，SSE 已产出事件后的 retry、SSE tool-call
  final finish parity 与 runtime file lock release failure cleanup 已修复；minimal read model reset contract 作为
  single-consumer ownership clarification deferred。最终 AgentMiMo / AgentDS re-review 均 PASS。Controller adjudication artifact 为
  `docs/reviews/p9-all-repo-review-controller-adjudication-20260517.md`。

目标：
- 实现 session-level Conversation Memory projection、stable layer、history pool、snapshot cursor、RunInputBuilder memory provider 与 projection repair path。

对应设计章节：
- `docs/host/design.md` §24 Conversation Memory
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/design.md` §26 Evidence / Retrieval / Long-term Memory

前置条件：
- Phase 8 projection runner 已完成。
- Phase 5 RunInputBuilder provider boundary 已完成。

进入条件：
- 确认第一版只做 session memory，不做长期 memory public edit / reset / forget API。
- 已确认 P9 只做 session-level memory projection，不实现长期 retrieval index、业务 signal ledger、signal-to-outcome verification、
  public memory edit / reset / forget API 或原始证据仓储。
- 已确认 P9 必须为后续跨多年弱信号归因召回预留 Host 中立 evidence anchor、claim status、provenance 与 trace included /
  excluded reason 边界，但不得把财报业务语义塞入 Host。

范围：
- 允许修改：memory projection、memory snapshot store、stable layer / history pool policy、RunInputBuilder MemorySnapshotProvider、memory lag diagnostic / repair path。
- 禁止修改：长期 memory retrieval、业务领域 evidence store、EventLog canonical fact semantics。

不做：
- 不实现跨多年长期记忆。
- 不把 final_answer 自动升级为 verified fact。
- 不让 memory projection 写 EventLog。

关键设计问题：
- 已确认 memory view 分为 `pinned_state`、`verified_facts`、`working_assumptions`、`conversation_continuity` 四类；不得把
  tool-verified fact、assistant conclusion、用户说法和 episode summary 混成无结构字符串列表。
- 已确认 verified fact 只接受工具事实，并必须保留 fact summary、producer / tool name、`event_id` / `event_sequence`、
  tool result ref、digest / source ref，以及可选 evidence anchor / opaque subject refs。
- 已确认 RunInputBuilder memory 注入顺序为：用户目标与约束、已确认主体和口径、tool-verified facts、open questions /
  working assumptions、recent raw turns、episode summaries。
- 已确认预算策略必须克制：pinned / verified facts 不参与 history pool 竞争但有结构化尺寸上限与诊断；recent raw turns floor
  是下限不是上限；older raw turns 与 episode summaries 共用单一 history pool；超预算时先降级 summary / older raw turns。
- 已确认 projection lag 必须显式可观测：小 delta 可由 EventLog 补齐并记录 diagnostic；缺失、损坏或超阈值进入 projection repair /
  context governance path；不得触发 Run recovery。
- 已确认 P9 不实现 LLM compaction 写 truth。LLM 产出的 pinned patch、episode summary 或 conclusion 默认只能成为 candidate /
  assumption / continuity view；proactive compaction 编排归 Phase 10 Context Governance。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: memory projection data model and checkpoint。
- Slice 2: stable layer / history pool builder。
- Slice 3: RunInputBuilder MemorySnapshotProvider and lag fallback。
- Slice 4: projection repair / rebuild entry and after-commit catch-up wiring。

验证要求：
- unit tests: final_answer not verified fact、tool facts verified、snapshot cursor coverage。
- integration tests: multi-run continuity with memory projection rebuild。
- anti-hallucination tests: 用户输入只进入约束或 assumption，不进入 verified facts；episode summary 不能替代 evidence anchor；
  memory snapshot rebuild 后 provenance 不丢；projection lag 不改变 Run 状态；同一 EventLog + 同一 policy 生成稳定 messages；
  recent turns floor 在预算低时仍保持追问连续性。
- pyright: memory modules 通过。
- docs: Host README / dayu/README.md 按触发规则同步。

退出条件：
- RunInputBuilder 可以稳定消费 memory snapshot；projection lag 不改变同一 EventLog + policy 下的 messages。

后续依赖：
- 后续 phase 可依赖的稳定契约：memory snapshot cursor、stable layer input provider、projection repair semantics。
- 需要追踪到后续 phase 的事项：长期 memory / query-time retrieval、业务 signal ledger、signal-to-outcome verification 后续单独设计；
  P9 只预留 Host 中立 evidence anchor / claim status / provenance / trace 边界。
- P9 all-repository follow-up 已明确 defer 的非 P9 blocking 架构债：Engine runner protocol decoupling、minimal read model
  single-consumer reset contract、Phase 11 RECOVERING 流程测试、Host durable/API error taxonomy、ToolRuntime / memory 模块拆分、
  LocalProxy close/events race、read API enum mapping、lane heartbeat/shield hardening 与消息 / 工具结果大小治理。

#### Phase 9 all-repository follow-up 追踪

结论：

- All-repository review artifacts 为 `docs/reviews/repo-review-20260517-1402.md`、
  `docs/reviews/repo-review-20260517-1411.md`、`docs/reviews/repo-review-20260517-1435.md`、
  `docs/reviews/repo-review-20260517-1434.md`、`docs/reviews/repo-review-20260517-1503.md` 与
  `docs/reviews/repo-review-20260517-1507.md`；DS follow-up artifact 为
  `docs/reviews/repo-review-ds-20260517-1521.md`。Final re-review artifacts 为
  `docs/reviews/repo-review-final-mimo-20260517.md` 与 `docs/reviews/repo-review-final-ds-20260517.md`，两者均 PASS。
- Controller adjudication artifact 为 `docs/reviews/p9-all-repo-review-controller-adjudication-20260517.md`。
- Controller 接受并修复 projection checkpoint CAS、non-stream / SSE tool call parity、tool call content fallback、timeout
  elapsed 统计、active worker / wait adapter / readany / startup closeout 日志、unsupported memory event diagnostic reason、
  EventLog run/type index、runtime weak typing guard、RunnerSpec 边界校验、BatchToolExecutionOutcome record identity 校验与
  malformed SSE usage 非终止处理、dispatch durable retry exhausted 非终态重排、SSE 已产出事件后的 retriable read failure 禁止跨
  attempt retry、SSE tool-call final finish 强制 `TOOL_CALLS`，以及 runtime file lock release failure 后清理 active token。
- Accepted all-repository follow-up commit 为 `6e12641`。

验证：

- `pytest -q`：966 passed。
- `pyright dayu tests`：0 errors。
- `git diff --check`：通过。

追踪项：

- Engine runner protocol decoupling、minimal read model single-consumer reset contract、RECOVERING 状态机、durable/API error taxonomy、Command
  handle internal service encapsulation / lifecycle guard、LocalProxy race、read API enum mapping、ToolRuntime / memory 模块拆分、lane hardening 与消息 / 工具结果大小上限
  均为后续 owned work，不阻塞 P9。其中除 RECOVERING 状态机归 Phase 11 外，其余不依赖 P10+ phase owner 的项目纳入 P9.5
  Pre-P10 Cross-Repository Hardening PR。

### Phase 9.5. Pre-P10 Cross-Repository Hardening PR

状态：
- design discussion accepted；下一步必须生成 implementation-ready handoff plan，并经双路 plan review / controller
  adjudication 通过后才可进入 implementation。P9.5 必须在 Phase 10 Context Governance / Compaction 前完成或显式裁决
  剩余项不阻塞 P10。

目标：
- 收口当前 `Open Questions 与风险追踪` 中不依赖 P10+ phase owner 的跨仓 hardening、cleanup 与 public contract repair。
- 降低 Phase 10 前的基础设施噪音，避免 Context Governance 开始时继续携带 Engine / Host public contract / durable helper /
  read API / LocalProxy / runtime lane 的已知非阻塞债。
- 按 `dayu/README.md` “日志级别语义”，为 Engine 与 Host P1-P9 已实现路径补充必要 log，并校准日志级别、字段、脱敏和
  invariant 诊断边界。
- 按 `dayu/README.md` “Contract Ownership”，检查 Engine / Host / runtime / contracts 已实现类型、事件、stream、projection、
  ToolRuntime 与 ToolBundle 等 contract 归属是否正确。

对应设计章节：
- `docs/host/design.md` §4 Run / Attempt 状态模型
- `docs/host/design.md` §10 Durable Store / Transaction / State Index
- `docs/host/design.md` §12 Command Path / Background Runtime / Policy Provider
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox
- `docs/host/design.md` §17 Host Dispatch / WorkerProxy / LocalProxy
- `docs/host/design.md` §18 ToolRuntime Boundary
- `docs/host/design.md` §24 Conversation Memory
- `dayu/engine/README.md` 与 Engine runner / contracts 文档

前置条件：
- P9 已完成并通过 all-repository follow-up fix / re-review。
- 用户确认 P9.5 不改变 P10 / P11 / P12 / P13 / P14 / P15 的语义 owner，只清理不依赖这些 owner 的当前追踪项。

范围：
- 允许修改：Engine runner protocol 边界、minimal read model single-consumer reset contract、durable / public API error taxonomy、
  Command handle internal service encapsulation / lifecycle guard、LocalProxy close / events race、read API enum mapping、
  ToolRuntime / memory 模块拆分、runtime lane hardening、message / tool result size governance、Host durable helper API tightening、
  schema CHECK hardening、Engine / OpenAI runner / parser hardening、TruncationManager initialization cost review、
  late `resolve_wait` redundant catch-up cleanup、production memory projection catch-up composition wiring 中不触及 snapshot history
  保留模型的部分、memory import boundary / preview facts / catch-up end-to-end targeted tests、Engine / Host P1-P9 已实现路径按
  日志级别语义补必要 log、Contract Ownership conformance audit、相关 README 与测试。
- 禁止修改：Context Governance / compact provider、RECOVERING recovery scan / dispatch、RemoteProxy / RemoteStub、Audit / Tool Trace /
  Outbox concrete sinks、ToolsDiscovery / ScenePrepare manifest provider、长期 memory / query-time retrieval、external job physical
  cancel / callback 产品化、purge / retention production hardening。

不做：
- 不实现 Phase 10 Context Governance。
- 不实现 Phase 11 RECOVERING / positive orphan proof / active cancel watchdog。
- 不实现 Phase 12 ToolsDiscovery / ScenePrepare。
- 不实现 Phase 13 Audit / Tool Trace / Outbox sinks。
- 不实现 Phase 14 RemoteProxy。
- 不实现 Phase 15 purge / retention / production scale。
- 不处理本轮已裁决排除项：Conversation Memory snapshot history、`cancel_active_wait_records_for_run` TOCTOU、
  session cancel replay 多 active worker 幂等、Gemini provider state 合约、Runner usage-only / tool-call-delta retry 粒度、
  `RECOVERING` Run。

P9.5 收口清单：
- Engine runner protocol decoupling：解除 Engine Agent 主链路对具体 OpenAI runner 类型的直接依赖，使 `_AsyncAgent` 只接收并消费
  `AsyncRunner` protocol；`run_agent_messages` 默认 public entry 仍可通过私有 helper 集中装配当前默认 OpenAI-compatible
  runner。该 helper 只表达当前默认 runner 装配边界，不是扩展点；不引入 runner factory / registry / provider selection
  contract，也不得以“方便未来扩展”为理由增加胶水 seam。
- minimal read model single-consumer reset contract：确认 `host_run_results` 与 `host_session_timeline_items` 是
  `host.minimal-read-model` 固定 consumer 独占的 read model 表；reset 全表后从 EventLog replay 是合法 repair / rebuild
  手段。P9.5 不引入 multi-consumer schema；只有未来真实出现第二个 minimal read model consumer 且必须共享同一物理表时，
  才单独设计 consumer isolation。
- durable / public API error taxonomy：梳理并收敛现有 durable error 到 public `HostApiError` 的翻译边界，确保 not found、
  invalid state、conflict、idempotency conflict、unsupported operation、internal error 与 `retryable` 语义在不同 public facade
  中一致；`detail` 仍只能使用 typed detail union，不引入无结构 payload 或新的复杂错误系统。
- Command handle internal service encapsulation / lifecycle guard：确认 `HostCommandHandle` 内部持有的 durable store、
  admission service 与 active registry 只是私有实现细节；`dayu.host` public exports、Service / UI 调用方和测试不得取得或依赖
  internal service，也不得绕过 handle close 写 durable truth。补 public export / import boundary / facade behavior tests，优先用
  public facade 行为验证，减少对白盒 `_xxx` 私有字段的依赖。
- LocalProxy close / events race：这是本地执行路径必须收口的 correctness 边界；补齐 worker handle close 后禁止重读
  `events()`、Engine event stream clean EOF without terminal、event stream exception / worker crash、terminal accepted 后 late event、
  scheduler close / active task cleanup、worker handle / lane token / active registry 释放，以及 close 与 event consumption 并发的
  targeted race tests 与必要修复。不得引入 RemoteProxy、exactly-once 或 Phase 11 recovery 语义。
- read API enum mapping：梳理 durable row enum、public API enum 与 read/event view enum 或文本的映射位置，确保
  `get_run()`、`get_session()`、`stream_run_events()` 与 minimal read model 对同一状态 / event type 的展示一致；映射应有单一真源
  或受控 helper，未知值必须 fail closed，不能静默降级为其它状态。补全当前 Run / Attempt / Session / event type 映射测试；不改变
  状态机、不新增状态、不改 EventLog facts、不把 read model 升级为 truth。
- ToolRuntime / memory module boundary cleanup：按既有职责把过大的聚合模块拆到清晰边界，例如 ToolRuntime 的
  effective bundle / schema projection、Host accept barrier、duplicate governance、truncation / `fetch_more`、diagnostics，以及
  Memory 的 contracts、projection builder、budgeting、serialization / codec、durable repository；只做 ownership 与 import
  boundary cleanup，不改变 ToolRuntime accept barrier、EventLog facts、memory snapshot 语义、projection truth 或状态机。
- ToolRuntime truncation / duplicate defensive hardening：补齐 truncation 多类型边界测试、duplicate governed error 防御性校验与
  不依赖 durable duplicate ledger 的本地治理测试。覆盖 `text_lines`、`list_items`、`binary_bytes` 等 truncation targeted
  tests，补 `fetch_more` cursor / `scope_token` / digest / expired / missing guard tests；收紧 `ToolFactAcceptCandidate`
  对 `GOVERNED_ERROR` / duplicate governed outcome 的 validation，补 duplicate `allow` / `reuse` / `hint` /
  `require_justification` / `hard_stop` focused tests，确认 `reuse` 不伪造新工具事实也不重复调用 business callable。
  复核 TruncationManager 默认启用时的初始化成本，若发现 production scale policy 问题再转交 Phase 15。不得新增 durable
  cursor table，不让 `fetch_more` 变成 Host / Engine 特化分支，不实现 durable duplicate ledger，不改变 duplicate policy 默认值，
  不落地 Tool Trace projection。
- Engine wait confirmation matching-ref hardening：收紧 Engine awaiting / confirmation event 与 Host accepted refs 的匹配契约；
  Engine `tool_awaiting` / `run_suspended` 只能确认 ToolRuntime Host accept path 已接受的 awaiting refs，不能创建 wait
  record、关闭 Attempt 或推进 Run `WAITING`。补 accepted refs 缺失、错 run、错 attempt、错 `execution_id`、旧 Attempt late
  confirmation 的 mismatch tests；不匹配只能 diagnostic / reject，不能进入 canonical owner 路径。保持 LocalProxy 与未来
  RemoteProxy 语义一致；不引入 callback endpoint、poller 后台循环、external job physical cancel 或 RemoteProxy wire protocol。
- runtime lane hardening：处理 `dayu.runtime.lane` 作为层中立资源容量 primitive 的稳定性问题，包括 acquire cancellation
  precision、heartbeat / token lost、release failure / repeated release 诊断、supervisor shutdown 时等待 acquire 或已持有 token 的
  清理，以及 repeated outer cancellation、untracked release failure、idle scheduler sleeping task 的 targeted tests / fix。lane
  token 仍只表示 runtime capacity claim，不得进入 EventLog、Attempt owner、dispatch truth、Host admission、Run / Attempt 状态机或
  recovery 判断；不引入 lease / fencing / takeover 语义。
- Host dispatch lifecycle / RunInputBuilder non-recovery cleanup：收口 scheduler lane 竞争测试、`_drain_loop` 可观测性、
  RunInputBuilder optimistic TOCTOU、late `resolve_wait` rejection 额外触发 catch-up 的低风险冗余与
  `_consume_worker_events` cleanup 等不需要 Phase 11 recovery 语义的 hardening。补 targeted tests 覆盖 durable recheck /
  lane release / dispatch requeue、drain loop 空队列 / sleep / 异常退出可观测性、worker event consumption 异常路径下的
  worker handle close / lane token release / active registry 注销、RunInputBuilder stale snapshot fail-closed，以及 late
  `resolve_wait` rejection redundant catch-up cleanup。不得夹带 Phase 11 recovery、`RECOVERING` dispatch、orphan proof、
  RemoteProxy 或状态机语义变更。
- message / tool result size governance：梳理 Host / Engine 边界已有大小常量、默认值与最大值，明确大消息、大工具结果、
  大 payload 必须外移到 payload / artifact / ref / digest，而不是塞进 EventLog canonical fact 或无界 Engine messages。
  超限必须产生结构化诊断或明确 public error，不能静默丢内容；补 message size / tool result size targeted tests，并确认
  truncation / `fetch_more` 不绕过该治理。不得实现 Phase 10 Context Governance、provider-specific tokenizer、proactive
  compaction、memory snapshot history 或业务规则。
- Host durable helper API tightening：收紧 `accept_worker_running_in_transaction` diagnostic payload、`mark_dispatching_after_lane_row`
  等 helper 能力宽于生产路径的问题。明确底层 helper 只能服务 scheduler / transition owner 的真实路径，不能被测试或后续代码用来
  绕过 lane wait、durable recheck、dispatch record 状态校验、execution_id 校验或 cancel race；状态不满足时必须 fail
  closed。补 helper diagnostic payload、production-path invariant tests，并减少直接用 helper 构造不真实状态的白盒测试。不把
  helper 提升为 public API，不为旧测试保留宽松 wrapper。
- schema CHECK hardening：把 SQLite schema 作为 Host durable truth 的最后结构防线，梳理当前 CHECK / FK / index 是否覆盖
  enum/status、ref/digest 成对字段、dispatch record、projection checkpoint / failure、minimal read model、memory rows、wait
  records、payload descriptors 等不变量。补不依赖后续 phase 的 CHECK / invariant 与 targeted durable schema tests，直接插入非法
  row 验证 SQLite 拒绝，并确保 Python validation 与 DB CHECK 一致。不做旧库兼容 migration，不新增 P10 / P11 / P13 /
  P15 状态或表，不改业务语义。
- Engine / OpenAI runner / parser hardening：收口不涉及 P10 语义的 OpenAI-compatible runner / parser correctness 与
  observability findings，包括 SSE / non-stream parser 边界、provider protocol error / context overflow 分类、tool call
  aggregation、finish reason parity、Engine event stream 不泄漏 log record、metadata 不承载契约事实，以及 run-scoped Runner
  生命周期测试。不做 runner factory / registry，不重开 usage-only / partial tool-call-delta retry 粒度，不做 proactive context
  governance，不把 Host 状态、memory 或 tool governance 放进 Engine，不引入 provider-specific public state 新合约。
- Engine / Host necessary log by level semantics：按照 `dayu/README.md` “日志级别语义”，为 Engine 与 Host P1-P9
  已实现路径补必要 log，并校准已有 log 的级别、字段命名、脱敏和 invariant 诊断。覆盖 Engine / Runner、Host command
  path、dispatch / LocalProxy、EngineEvent ingest、ToolRuntime accept barrier、wait resolve / late rejection、projection catch-up /
  repair、memory catch-up 等已实现路径；日志只记录 typed ids、refs、digest、cursor、policy / diagnostic refs，不记录完整
  prompt、完整工具参数 / 结果、delta 全量、财报原文、authorization claims 原文或大 payload。补 logging targeted tests /
  caplog tests，确认 `VERBOSE` 只表达执行骨架、`DEBUG` 表达受控细节、`WARN` 表达可恢复异常、`ERROR` 表达本次操作失败、
  `CRITICAL` 表达 invariant / contract 破坏。该任务只补必要 log，不建设新的 observability 平台；不得把日志升级为
  EventLog truth、audit、tool trace、projection checkpoint 或 UI 输出；不得提前实现 P10+ 未落地路径。
- Contract Ownership conformance audit：按照 `dayu/README.md` “Contract Ownership” 检查 P1-P9 已实现的 Engine /
  Host / runtime / contracts 类型、事件、stream、projection、ToolRuntime、ToolBundle、RunSnapshot / SessionSnapshot、
  EventLog / Host event stream、RunnerEvent / EngineEvent 等 contract 归属是否正确。重点检查 Host 私有治理状态是否误放进
  `dayu.contracts`、Engine 是否理解 Host 状态、Host 是否把 projection / read model 当 truth、runtime 是否承载业务或 Host
  治理语义、ToolRuntime / ToolBundle 边界是否被 Service / UI 或 Engine 误拥有。按照 `docs/design.md` “工具定义与执行边界”
  增加专项检查：Engine 不得 import / 持有 / 分支判断 `@tool`、`ToolDefinition`、`ToolBundle`、`ToolCallable`、
  ToolRuntime 或具体工具实现；Host 不得扫描业务工具模块或在 per-run request / metadata 中塞 raw `ToolBundle`；
  `fetch_more` 只能由 ToolRuntime factory 注入 attempt-local effective `ToolBundle`。补 import boundary / public export /
  package surface tests；发现归属错误时按当前设计真源移动到正确层，不做兼容 re-export / wrapper。不得借该 audit 引入未来
  P10+ contracts 或重写 public API。
- P9 memory cleanup / test hardening：只收口 `current_goal` first-write-wins、legacy `SessionContinuityProvider` 参数、
  preview facts exclusion 专项测试、memory import boundary 自动化测试、catch-up end-to-end 专项测试、optional JSON helper
  wording、empty snapshot 双实例构造与 cast 注释等不涉及 snapshot history 保留模型的 cleanup / tests。确认 legacy
  `SessionContinuityProvider` 不绕过 memory history pool budget，preview / reasoning / display-only events 不进入 memory，
  memory import boundary 不依赖上层或业务模块，catch-up concrete wiring 能端到端追平。不得修 Conversation Memory snapshot
  history，不实现长期 retrieval index、public memory edit / reset / forget，不让 final answer 升级为 verified fact，不让 Host
  import `dayu.fins`。
- production memory projection catch-up composition wiring：补齐 command / admission / scheduler composition 中不改变 snapshot
  history 保留模型的 concrete catch-up port 注入；梳理 production command handle、admission service 与 scheduler worker accept
  前使用 no-op 还是 concrete memory catch-up port，并明确 test / dev no-op 边界。补 end-to-end tests 覆盖用户输入、tool
  fact、`resolve_wait` 等提交后 memory projection 被 catch up；catch-up 失败只记录 projection-local failure / logger，不回滚
  已提交 command，不修改 Run / Attempt / EventLog。snapshot history 本身仍按单独 PR 裁决处理；不引入跨 cursor snapshot
  retention，不把 projection lag 变成 Run recovery，不实现 P10 Context Governance 或 heavy sink / batch runner。

验证要求：
- `pytest -q`。
- `python -m pyright dayu tests`。
- `git diff --check`。
- 覆盖每个 P9.5 收口项的 targeted tests；不能只靠全量测试偶然覆盖。

退出条件：
- P9.5 收口清单全部完成、显式裁决为不修复，或重新归属到 P10+ phase owner且写明依赖理由。
- P10 开始前，追踪区不得再存在“无 owner / 后续 hardening”但实际不依赖 P10+ 的项目。

### Phase 10. Context Governance / Compaction

目标：
- 实现 Host proactive context budget governance、compact event、compacted artifact、reactive Engine overflow recovery 与 RunInputBuilder compact provider。

对应设计章节：
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §25.1 Compact Event 响应路径
- `docs/host/design.md` §23 RunInputBuilder

前置条件：
- Phase 0 Engine context compaction event cleanup 已完成；Phase 10 不消费 Engine overflow event 作为真实 Host budget，必须使用 Host estimator / policy。
- Phase 9 memory projection 已完成。
- Phase 5 dispatch / reactive failure closeout 已完成。
- Phase 6 ToolRuntime / tool fact accept barrier / run-scoped truncation / `fetch_more` contract 已完成。

进入条件：
- 确认 conservative estimator、provider-aware configured limits、safety margin 与 compact policy 的第一版默认值。

范围：
- 允许修改：Context Governance orchestrator、budget estimator、compact artifact store、compact canonical events、RunInputBuilder CompactArtifactProvider、reactive overflow recovery path。
- 禁止修改：Engine proactive compaction、memory projection direct write、audit / trace projection direct write。

不做：
- 不实现 provider-specific tokenizer adapter。
- 不实现长期 memory retrieval。
- 不做无限 compact retry。

关键设计问题：
- 必须确认 proactive 与 reactive 两条路径的 transaction / state transition。
- 必须确认 compacted snapshot 的质量检查、保留事实 refs 与 dropped / summarized ranges。
- 必须确认 compact failure 的 Run terminal / recoverable policy。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: budget estimator / policy view / proactive trigger。
- Slice 2: compact artifact and canonical events。
- Slice 3: reactive Engine overflow -> RECOVERING -> new Attempt path。
- Slice 4: RunInputBuilder compact provider and failure handling。

验证要求：
- unit tests: threshold decisions、compact event payload validation、failure policy。
- integration tests: proactive compact before dispatch and reactive overflow recovery。
- pyright: context governance modules 通过。
- docs: Host / Engine boundary docs 按触发规则同步。

退出条件：
- Host 能在 dispatch 前主动 compact，并能把 Engine overflow 当作 reactive fallback 恢复，不让 Engine 管理 Host context budget。

后续依赖：
- 后续 phase 可依赖的稳定契约：compact events、compact artifacts、context budget policy view。
- 需要追踪到后续 phase 的事项：provider-specific tokenizer adapter 是后续能力。

### Phase 11. Host Lifecycle / Recovery / Multi-process Hardening

目标：
- 实现 Host startup recovery scan、positive orphan proof、prompt accepted but answer not returned 的恢复语义、graceful shutdown 与多进程一致性硬化。

对应设计章节：
- `docs/host/design.md` §27 Host Lifecycle / Recovery
- `docs/host/design.md` §27.1 已接受 Prompt 的恢复语义
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §17 WorkerProxy / EngineWorker

前置条件：
- Phase 5 dispatch record / LocalProxy 已完成。
- Phase 2 host instance liveness foundation 已完成。
- Phase 3 state transition / admission 已完成。

进入条件：
- 确认 positive orphan proof 的本机 pid / process_start_token / heartbeat 判定实现策略。

范围：
- 允许修改：startup recovery scan、host instance heartbeat、orphan classifier、RECOVERING dispatch、shutdown policy、multi-process tests。
- 禁止修改：远端 takeover、lease / fencing 系统、旧 Attempt resume。

不做：
- 不保证 exactly-once 远程物理执行。
- 不强杀远程执行环境。
- 不从 projection 或 memory 恢复 Run truth。

关键设计问题：
- 必须确认 `RUNNING` / `CANCELLING` / `RECOVERING` / `WAITING` / `QUEUED` startup 分类。
- 必须确认 suspect owner 不被误杀的 diagnostic path。
- 必须确认 repeated recovery 上限与 LOST / FAILED 收口 policy。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: host instance heartbeat and positive orphan proof。
- Slice 2: recovery scan classification and CAS closeout。
- Slice 3: RECOVERING dispatch and prompt accepted recovery integration。
- Slice 4: graceful shutdown and multi-process race tests。

验证要求：
- unit tests: orphan proof classifier、state classification。
- integration tests: crash after USER_INPUT_ACCEPTED before final answer, restart produces answer; live second process not harmed; projection runner stopped or lagging 时仍能仅凭 EventLog / state indexes 完成 recovery。
- pyright: recovery modules 通过。
- docs: Host README recovery 语义同步。

退出条件：
- 已 durable accepted 的 prompt 在 Host 崩溃 / 重启后可通过新 Attempt 继续并最终产出 answer，且不会误杀仍存活 Host 进程的 active Attempt。

后续依赖：
- 后续 phase 可依赖的稳定契约：startup recovery、positive orphan proof、RECOVERING dispatch。
- 需要追踪到后续 phase 的事项：远端 orphan execution 仍按 RemoteProxy phase 和 exactly-once 非目标治理。

### Phase 12. ToolsDiscovery / ScenePrepare

目标：
- 实现独立于 Host 的工具发现 / 注册与场景准备 runtime assembly 边界，让业务工具集合与 scene inputs 能在 Host construction / Service request envelope 前被 typed 组装，不让 Host import 具体业务工具、扫描业务包或拼接财报场景 prompt。

对应设计章节：
- `docs/host/design.md` §3 dayu.runtime
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `dayu/README.md` 术语约定与 Runtime

前置条件：
- Phase 1 Host public typing、`HostToolingOptions`、`ToolBundleSourceRef`、`ToolBundleSourceKind` 与 `FrameworkToolPolicyView` 已完成。
- Phase 4 Host public API command path 已完成。
- Phase 6 ToolRuntime / effective ToolBundle / framework tool policy 已完成。

进入条件：
- 确认 ToolsDiscovery / ScenePrepare 仍是 Host 外部装配能力，不拥有 Session / Run / Attempt / EventLog truth。
- 确认具体财报业务工具 provider、财报 prompt 文案、财报 scene manifest 内容属于 Service / Fins / 配置边界，不写入 `dayu.runtime`。
- 确认是否需要把 ToolsDiscovery / ScenePrepare 放入 `dayu.runtime`；若放入，只能依赖标准库与 `dayu.contracts`，不得 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 或具体业务工具包。

范围：
- 允许修改：ToolsDiscovery typed provider protocol、tool provider aggregation、`ToolBundle` validation / source refs assembly、ScenePrepare typed manifest assembly helper、scene input typed output、import boundary tests、相关 README。
- 禁止修改：Host durable state machine、Host command path、Engine execution path、ToolRuntime accept barrier、具体业务财报工具实现、财报仓储实现。

不做：
- 不实现 Audit / Tool Trace / Outbox projection；该能力在 Phase 13。
- 不实现业务财报工具扫描硬编码清单。
- 不把财报 prompt 文案、业务 scene manifest 内容或 Fins storage 访问逻辑放入 `dayu.runtime`。
- 不让 per-run request 携带 raw `ToolBundle` 或 callable binding。

关键设计问题：
- 必须确认 ToolsDiscovery provider protocol 的最小 typed shape：provider identity、version / digest source refs、`ToolDefinition` collection output、duplicate name handling、reserved framework tool name conflict handling。
- 必须确认 ScenePrepare 的 typed scene input output shape，以及它如何进入 Service / Host request envelope 而不变成 Host 状态机语义。
- 必须确认 ToolsDiscovery / ScenePrepare 的 import boundary tests，防止 runtime import 具体业务工具、Fins、Host、Engine、Service 或 UI。
- 必须确认 source refs / digest 与 Phase 1 `HostToolingOptions`、Attempt snapshot refs 和 audit / diagnostic refs 的衔接方式。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: ToolsDiscovery provider protocol and ToolBundle aggregation。
- Slice 2: ToolBundle source refs / digest assembly and reserved framework tool name validation。
- Slice 3: ScenePrepare typed manifest assembly helper and scene input output。
- Slice 4: import boundary tests and README sync。

验证要求：
- unit tests: provider aggregation、duplicate tool names、reserved framework tool conflicts、source refs / digest stability、scene manifest assembly、invalid manifest errors。
- import boundary tests: runtime assembly modules 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 或具体业务工具包。
- integration tests: 可使用 fake providers / fake scene manifests；不依赖真实财报工具扫描或财报 prompt 文案。
- pyright: runtime assembly / affected contracts 通过。
- docs: `dayu/README.md` 与受影响包 README 按职责同步。

退出条件：
- 外部装配方可以通过 typed provider / manifest assembly 得到业务 `ToolBundle`、`ToolBundleSourceRef` 与 typed scene inputs，并把它们交给 Host construction / request envelope，而无需 Host import 业务工具或拼 scene prompt。
- Runtime assembly 边界不持有 Host truth，不参与 Run / Attempt lifecycle，不决定 EventLog / ToolRuntime accept barrier。

后续依赖：
- 后续 phase 可依赖的稳定契约：business `ToolBundle` discovery boundary、scene input assembly boundary、source refs / digest assembly。
- 需要追踪到后续 phase 的事项：具体财报工具 provider、财报 scene manifest 内容、财报 prompt 文案仍属于 Service / Fins / 配置 work unit，不属于 runtime assembly phase。

### Phase 13. Audit / Tool Trace / Outbox Projections

目标：
- 在已稳定的 EventLog consumer framework 上实现 LogAuditSink、tool trace hot / cold storage 与 Outbox terminal delivery queue projection。

对应设计章节：
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §14.1 Tool Trace Hot / Cold Storage
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

前置条件：
- Phase 8 Projection Core / Host Event Stream / Minimal Read Model 已完成。
- Phase 6 ToolRuntime diagnostic refs 已完成。

进入条件：
- 确认 Audit、Tool Trace、Outbox 只是 projection / sink，不参与 Host command path 成功条件，不反向成为恢复、resume、memory 或 Run 状态迁移真源。

范围：
- 允许修改：LogAuditSink(JSONL)、tool trace hot JSON projection、tool trace cold JSONL writer、OutboxSink、sink-local retry / error state、相关 read / analyze support。
- 禁止修改：EventLog append 语义、Run / Attempt governance state、terminal transaction、UI / Service channel delivery 状态。

不做：
- 不实现外部 audit 系统。
- 不保证 channel delivery exactly-once。
- 不让 terminal transaction 同步写 outbox 表。
- 不把 tool trace JSONL 当作恢复、resume、memory 或 Run 状态迁移真源。

关键设计问题：
- 必须确认 tool trace hot JSON 与 cold JSONL 的最小字段，以及 provider request id / operation context refs 的查询口径。
- 必须确认 Outbox item identity 与 UI / Service seen cursor 推荐语义。
- 必须确认 LogAuditSink 路径注入、append-only JSONL、sink failure 和 purge tombstone 查询语义。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: LogAuditSink and audit JSONL。
- Slice 2: tool trace hot JSON / cold JSONL。
- Slice 3: OutboxSink and terminal delivery queue projection。

验证要求：
- unit tests: sink checkpoint idempotency、sink retry、audit / trace / outbox projection rebuild。
- integration tests: terminal EventLog -> audit / tool trace / outbox；sink failure 不影响 Run terminal。
- pyright: projection sink modules 通过。
- docs: Host README / tool trace analysis docs 按触发规则同步。

退出条件：
- Audit、Tool Trace、Outbox 均能从 committed EventLog 独立追平；任一 sink 失败只造成 projection lag 或 sink-local error，不影响 Host command path。

后续依赖：
- 后续 phase 可依赖的稳定契约：audit JSONL、tool trace hot / cold、outbox terminal delivery queue。
- 需要追踪到后续 phase 的事项：Service / UI channel delivery、外部 audit 系统和长期归档策略不属于本 phase。

### Phase 14. RemoteProxy / RemoteStub

目标：
- 在 LocalProxy 语义基准上实现 RemoteProxy / RemoteStub transport substitution，保持 Host 治理真源、execution_id late event rejection 与 tool fact accept ack。

对应设计章节：
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §27 Host Lifecycle / Recovery

前置条件：
- Phase 5 LocalProxy semantic baseline 已完成。
- Phase 6 ToolRuntime accept barrier 已完成。
- Phase 11 recovery 与 positive orphan proof 已完成。

进入条件：
- 确认 remote phase 只定义并实现 transport，不改变 design 的 remote semantic contract。

范围：
- 允许修改：RemoteProxy、RemoteStub、remote event identity mapping、remote cancellation propagation、remote tool accept ack transport。
- 禁止修改：Host 状态 ownership、EventLog append ownership、Attempt takeover 语义、wire protocol 污染设计文档。

不做：
- 不实现远端 worker 自治恢复。
- 不保证 exactly-once 远程物理执行。
- 不引入远端 lease / fencing owner。

关键设计问题：
- 必须确认 remote event id / ordering hint / retry / ack 的 typed transport contract。
- 必须确认 stale execution_id、late terminal、late tool result 和 connection drop 的诊断路径。
- 必须确认 RemoteStub 不拥有 Host durable truth 的测试边界。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: RemoteProxy / RemoteStub transport skeleton and attempt snapshot serialization。
- Slice 2: remote EngineEvent ingest / late event rejection。
- Slice 3: remote cancel and connection failure closeout。
- Slice 4: remote tool fact accept ack path。

验证要求：
- unit tests: event identity mapping、stale execution_id rejection、ack idempotency。
- integration tests: remote fake worker success / cancel / disconnect / late event / duplicate event。
- pyright: remote modules 通过。
- docs: Host README remote boundary 同步。

退出条件：
- 本地与远程 EngineWorker 在 Host 视角下共享同一治理语义；远端只执行并回传事件，不拥有 Host state owner。

后续依赖：
- 后续 phase 可依赖的稳定契约：Remote transport substitution、tool accept ack over remote、late event diagnostic。
- 需要追踪到后续 phase 的事项：远程 wire protocol 细节可以独立演进，但不能改变 semantic contract。

### Phase 15. Retention / Purge / Production Hardening

目标：
- 收口第一版生产化要求：`purge_session` destructive cleanup、audit tombstone、projection rebuild 验证、性能 / 并发 smoke、docs 与 residual risk 归档。

对应设计章节：
- `docs/host/design.md` §5 Session 生命周期
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §28 第一版 Non-goals

前置条件：
- Phase 8 projection core、Phase 11 recovery、Phase 13 Audit / Tool Trace / Outbox、Phase 14 remote 已完成。

进入条件：
- 确认第一版 release / PR 前必须关闭的 residual risk 与可接受 non-goals。
- 先区分 release-blocking 与 follow-up items；如 projection rebuild tooling、stress / smoke tests 或 docs closeout scope 过大，必须拆出独立 phase 或后续 work unit。
- 必须复核 Phase 4 已冻结的 `purge_session` public signature / `PurgeSessionResult` / idempotency contract；如需变更，先回到 Public API contract 讨论。

范围：
- 允许修改：`purge_session` command implementation、purge delete ranges、shared artifact ref check、projection rebuild tooling、audit tombstone query support、stress / smoke tests、README sync。
- 禁止修改：新增 archive_session、长期 memory API、重型消息系统、服务化 DB。

不做：
- 不实现 archive_session。
- 不实现长期 retention policy UI。
- 不把第一版 non-goals 偷偷变成实现目标。

关键设计问题：
- 必须确认 purge 对 EventLog / payload / projection / outbox / tool trace hot data / audit JSONL 的最终清理矩阵。
- 必须确认第一版 residual risks 的接受、后续 issue 或当前修复归属。
- 必须确认 purge / tombstone / projection rebuild slices 是否可以在 Remote smoke 之前独立完成；remote smoke / release closeout slice 依赖 Phase 14。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: purge delete matrix and tombstone audit。
- Slice 2: projection rebuild / consistency checks。
- Slice 3: multi-process / remote / recovery production smoke。
- Slice 4: README / docs / residual risk closeout。

验证要求：
- unit tests: purge precondition and tombstone behavior。
- integration tests: purge after terminal runs, projection rebuild, audit JSONL retention。
- integration tests: crash after `USER_INPUT_ACCEPTED` + old attempt events, recovery scan creates new attempt, new attempt reaches terminal, projection rebuild from EventLog verifies old attempt facts、new attempt facts、terminal result、outbox / audit / trace projections as applicable。
- pyright: full project or affected packages。
- docs: all triggered README updates complete。

退出条件：
- 第一版 Host design 的核心目标可通过测试和文档说明支撑，剩余 non-goals 与 deferred risks 均有明确追踪归属。

后续依赖：
- 后续 phase 可依赖的稳定契约：purge semantics、production smoke baseline、residual risk registry。
- 需要追踪到后续 phase 的事项：archive_session、provider-specific tokenizer、长期 memory、remote wire protocol evolution。

## Open Questions 与风险追踪

总控文档负责追踪跨 phase 的 open questions、潜在影响和未覆盖项。

追踪规则：

- `blocking` open question 必须在对应 phase 的 plan review 通过前解决，并写回 `docs/host/design.md` 或 phase plan。
- `non-blocking` open question 必须写明 working assumption、风险、触发回看条件和归属 phase。
- implementation 中发现的新 open question，如果会影响设计边界或用户可见行为，必须停下交给用户讨论。
- residual risk 和 uncovered area 必须分类为：当前 phase 修复、后续 phase 覆盖、后续 work unit、用户明确接受、或需要新跟踪项。
- 任何 deferred 项都必须有 owner / destination；没有 destination 时不能关闭对应 phase。

### 追踪区

#### P9.5 Pre-P10 Cross-Repository Hardening PR 归属追踪

背景决议：

- P9 已完成；P10 Context Governance 开始前，先新增一个 P9.5 PR 收口当前追踪区中不依赖 P10+ phase owner 的
  hardening / cleanup。
- P9.5 不接收刚才已重新裁决的排除项：Conversation Memory snapshot history、`cancel_active_wait_records_for_run`
  TOCTOU、session cancel replay 多 active worker 幂等、Gemini provider state 合约、Runner usage-only / tool-call-delta
  retry 粒度、`RECOVERING` Run。

归属到 P9.5 的追踪项：

- Engine runner protocol decoupling。
- minimal read model single-consumer reset contract；不引入 multi-consumer schema。
- durable / public API error taxonomy。
- Command handle internal service encapsulation / lifecycle guard；补 public export / import boundary / facade behavior tests，防止
  Service / UI 或测试越过 `HostCommandHandle` 直接依赖 internal service。
- LocalProxy close / events race。
- read API enum mapping。
- ToolRuntime / memory module boundary cleanup；只拆分既有职责和 import boundary，不改变工具治理、memory snapshot、
  EventLog facts、projection truth 或状态机。
- ToolRuntime truncation / duplicate defensive validation 与 focused test hardening。
- TruncationManager initialization cost review：基于当前初始化路径的直接证据复核默认 `enable_truncation_manager=True`
  是否存在 hot path 重初始化成本；轻对象则裁决为不修，真实 production scale policy 问题转交 Phase 15。不得引入全局
  TruncationManager singleton、durable cursor table、跨 Run cursor 复用或 Host / Engine `fetch_more` 特化分支。
- Engine wait confirmation matching-ref contract hardening。
- runtime lane hardening。
- Host dispatch lifecycle / RunInputBuilder non-recovery cleanup 与 targeted tests。
- late `resolve_wait` rejection redundant catch-up cleanup / tests：确认 late wait result rejection 不写 canonical tool fact、
  不推进 Run、不创建 Attempt，只保留 diagnostic / rejection 可观测性；检查 rejection 后是否额外触发 projection catch-up，能轻量
  抑制则抑制，复杂度过高则用测试和注释明确为低风险冗余。不得改变 `resolve_wait` first-committer-wins、`WAITING`
  cancel / resolve 竞态规则，不实现 callback / poller 后台循环、external job cancel，也不得把 late result 变成 canonical fact。
- message / tool result size governance。
- Host durable helper API tightening。
- schema CHECK hardening。
- Engine / OpenAI runner / parser hardening。
- Engine / Host P1-P9 implemented-path necessary log under `dayu/README.md` level semantics。
- Contract Ownership conformance audit under `dayu/README.md` Contract Ownership。
- P9 memory 代码中不涉及 snapshot history 的 Host cleanup / test hardening。
- P9 memory import boundary、preview facts exclusion、catch-up end-to-end、optional JSON helper wording、empty snapshot 双实例构造与
  cast 注释 cleanup / tests。
- production memory projection catch-up composition wiring 中不触及 snapshot history 保留模型的部分。
- God module / class cleanup 与 broader test hardening 中不依赖 P10+ owner 的部分：不得作为独立大 slice 或无限重构口袋；
  只能接收已归属到上述具体 P9.5 条目的 cleanup，并为每个 cleanup 标明 owner（ToolRuntime、memory、dispatch、Engine
  runner、read API、durable helper 等）。只允许机械拆分、import boundary、测试整理、命名 / 注释清晰化与 focused tests；
  若发现需要改 public contract、状态机、ToolRuntime / memory 语义、P10+ owner 能力或跨模块大重构，必须停下并重新归属。
  P9.5 结束前不得保留无 owner 的 broader hardening 表述。

退出规则：

- P9.5 结束时，上述项目必须已修复、明确裁决为不修复，或因发现真实 P10+ 依赖而重新归属到具体后续 phase owner。
- 不允许继续保留“后续 hardening”这类无明确 owner / destination 的追踪表述。

#### 2026-05-17 全仓 Review Fix Gate 残余风险追踪

背景决议：

- 2026-05-17 全仓 review fix gate 已由 AgentCodex 修复，并经 AgentMiMo / AgentDS re-review PASS。
- 本轮修复 artifact 为 `docs/reviews/repo-review-fix-agentcodex-20260517.md`；re-review artifact 为
  `docs/reviews/repo-review-fix-rereview-mimo-20260517.md` 与
  `docs/reviews/repo-review-fix-rereview-ds-20260517.md`。
- 用户明确要求本轮不修改 `dayu/engine/agent.py` 的 `AsyncOpenAIRunner` 直接装配问题。

追踪项：

- Conversation Memory snapshot history：当前 dispatch 按 Attempt cursor 做 bounded catch-up，并用
  at-or-before snapshot 读取阻止 queued future input 泄漏。残余风险是 snapshot 表仍按 session / consumer / policy 保留
  latest snapshot；若其它 composition root 在 dispatch 前把同一 consumer catch-up 到 future cursor，旧 cursor snapshot
  可能已不可读。裁决为单独 PR 修复；触发条件为新增 dispatch 外 memory catch-up composition root、需要多 cursor snapshot
  保留，或需要跨 worker projection lifecycle owner。
- `cancel_active_wait_records_for_run` TOCTOU：裁决为不修复当前 finding。`WAITING` cancel / resolve 属于 Phase 7 已完成能力，
  当前设计要求同一 Run 同时只有一个 active wait record，Host 写事务是短事务且 CAS / first-committer-wins 是治理边界；
  原 finding 的“多 active wait + 读后被其它 writer 抢先 resolve”复现场景不符合当前不变量。若后续放宽 active wait record
  invariant，必须重新进入 Phase 7 wait cancel contract design。
- session cancel replay 多 active worker 幂等：裁决为不修复当前 finding。设计真源要求同一个 Session 同时最多一个 active
  Run，当前 session cancel replay 不需要支持多 active worker truth。若后续设计允许同一 Session 多 active Run / 多 worker
  并行，必须先重写 admission invariant 与 session cancel replay contract。
- Gemini provider state 合约：`GeminiToolCallState` 仍是 provider-specific public contract。裁决为单独 PR 修复，归属
  Engine provider abstraction / contracts neutralization work unit；触发条件为新增非 Gemini provider-specific tool-call
  continuation state，或决定把 provider state 统一为 provider-neutral tagged structure。
- Runner usage-only / tool-call-delta retry 粒度：裁决为不修复当前 finding。此前 re-review 已接受“任意已 yield
  RunnerEvent 后不跨 attempt retry”作为当前一致性边界；细分 usage-only / partial delta 可重试性必须先定义调用方可见事件、
  审计、成本记录与重放安全契约，不能作为局部 retry tweak。
- `RECOVERING` Run：该状态由 Phase 11 recovery owner 接入，当前 P9 生产转换代码尚不写入；本轮不围绕未接入状态增加分支。裁决为归到后续 phase owner；
  destination 为
  Phase 11 recovery dispatch；触发条件为实现 `RECOVERING` 入边 / 出边转换、startup recovery scan 或 recovery dispatch。

#### Engine Runner Protocol 解耦追踪

背景决议：

- 2026-05-17 全仓 review fix gate 中，用户明确要求本轮不修改 “Engine Agent 硬编码依赖 `AsyncOpenAIRunner`，违反 Protocol 解耦约束” 这一项代码。
- 本轮不改 `dayu/engine/agent.py`，不引入 runner factory / registry，不改变 Engine public entry 或 Host 调用方式。
- 用户在 P9.5 discussion 前确认：P9.5 不做 runner factory；只做 Engine Agent 主链路对 `AsyncRunner` protocol 的解耦。

追踪项：

- destination：P9.5 Pre-P10 Cross-Repository Hardening PR。
- 触发条件：需要在 Engine Agent 主链路测试中注入 `AsyncRunner` protocol 实现，或新增非 OpenAI-compatible 原生 runner 时发现当前主链路仍绑定具体 OpenAI runner。
- 后续处理要求：先明确 `_AsyncAgent` 如何只消费 `AsyncRunner` protocol，以及 `run_agent_messages` 默认 public entry 如何通过
  私有 helper 装配当前默认 OpenAI-compatible runner；该 helper 不是扩展点。不得引入 runner factory / registry、lazy import、
  兼容 wrapper 或 metadata bag 作为解耦替代品。

#### Engine Context Compaction Event 语义前置

背景决议：

- Engine 只在 provider 返回 `context_length_exceeded` 后 emit `context_compaction_requested`；这属于 reactive fallback，不是生产级 proactive context governance。
- P0-S1 已将 `ContextCompactionRequestedData.budget_state` 改为 `ContextBudgetSnapshot | None`；provider overflow path 使用 `None` 表示预算未知 / 未上报，不再使用零值快照作为 unknown sentinel。
- `ContextBudgetSnapshot` 仍只表示真实、可解释的 token snapshot；数值为零仍是普通真实快照，不得被解释为 unknown。
- Host 生产级治理应由 Context Governance 基于 provider-aware budget policy 主动判断 soft / hard threshold；provider overflow 只能作为最后防线。

前置实施步骤：

- P0-S1 Engine contract cleanup 已完成并提交为 `ad6d116`。
- P0-S2 同步 Engine README、Engine design docs、项目级术语和本追踪区，使后续 Host implementation agent 不会把 Engine reactive fallback 误解为 proactive context governance。
- P0 不把 budget governance 放进 Engine；Engine 不做 proactive threshold compaction，不做 compact / retry，不计算 Host budget，不提供 provider-aware tokenizer 或 Host budget policy。
- P0 保留 `usage_reported`、`iteration_completed`、provider request id 和 overflow reason，供 Host Context Governance 诊断与追踪。

追踪项：

- Phase 10 owns Context Governance semantic interpretation：当 Engine overflow budget unknown 时，必须使用 Host estimator / policy 生成 before / after budget refs，并决策 compact / recovery。
- Phase 10. Context Governance / Compaction 的测试设计必须覆盖：Engine overflow event 中预算 unknown 时，Host 仍使用自身 budget estimator 进行 compact 诊断与恢复决策。

#### External Job Cancel Adapter 能力追踪

背景决议：

- `WAITING` Run 被 `cancel_run` 命中时，Host 第一版负责 durable 状态收口：append `CANCEL_REQUESTED`，标记 active wait record 为 cancelled，append `RUN_CANCELLED`，并释放 Session active slot。
- 外部 job 的实际取消属于对应 wait adapter / tool adapter 的 best-effort 能力，不作为 Host 第一版保证。

追踪项：

- 后续 callback / poller adapter owner 若实现外部 job cancel / revoke / abandon，必须保持 best-effort 语义，不得影响 Host EventLog 和 Run 终态的正确性。
- 后续 callback / poller adapter owner 必须保持迟到结果治理：外部 job 在 Host 已取消 Run 后仍回调或被 poll 到结果时，结果不得进入 canonical EventLog，只能进入 diagnostic / tool trace。

#### Tool Trace / Provider Request 排错追踪

背景核实：

- OpenAI API reference 的 Debugging requests 说明 `x-request-id` 是每次 API request 的唯一标识，并建议生产环境记录 request id，便于和 OpenAI support 排障。
- 同一官方章节说明调用方可显式提供 `X-Client-Request-Id`；当 timeout / network issue 导致拿不到 `X-Request-Id` response header 时，可用该值让 OpenAI support 查询是否收到请求以及收到时间。
- 当前 Engine 已把 provider response header 的 `x-request-id` 提取为 `provider_request_id`，并在 Runner / Engine 错误与终态链路中显式透传：`RunnerHTTPErrorData`、`RunnerProtocolErrorData`、`RunnerDoneData`、`ProviderProtocolErrorData`、`RunFailedData`、`EngineRunOutcomeFailed` 等字段已覆盖；相关测试也覆盖了 HTTP error、protocol error、iteration completed、run failed 的透传。

追踪项：

- 不修改 `docs/host/design.md`；这不是 Host 架构边界新决策，而是 tool trace / analyze 工具排障能力需求。
- Phase 13. Audit / Tool Trace / Outbox Projections 实现 tool trace 与后续 `utils/analyze_tool_trace.py` 时，必须把 `provider_request_id` 纳入热 JSON projection 与冷 JSONL，便于按 OpenAI `x-request-id` 排查 provider 错误、超时、协议错误和重试耗尽。
- 后续 Host 外部 Service / provider adapter work unit 若为 OpenAI-compatible request 注入 `X-Client-Request-Id`，Phase 13 tool trace 也必须记录对应 client-side request id，并与 `provider_request_id`、`run_id`、`attempt_id`、`execution_id`、`event_sequence` 一起可查询。
- 对 timeout / network error 且 `provider_request_id=None` 的场景，analyze 工具应提示优先查看 client-side request id / `X-Client-Request-Id`、网络错误类型、attempt 次数和 retry history。

#### SQLite 多进程写入正确性验证

结论：

- 第一版继续使用 SQLite durable store 作为单机多进程 Host 真源。
- 不提前引入服务化数据库、消息队列、分库或重型写入架构。
- 正确性依赖 WAL、明确 busy timeout、短事务、显式重试、唯一约束和 CAS-style state transition。
- 该项重点是验证写竞争不会破坏状态机和 EventLog 真源；性能容量只有在压测或生产观察证明明显后才升级为容量治理问题。

追踪项：

- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening owns SQLite 多进程 busy / retry 策略、startup recovery scan 与容量 hardening；在压测或生产观察证明需要前，不得把 SQLite 写竞争作为引入服务化 DB 或消息队列的默认理由。

#### Phase 3 Dispatch Intent / State Index 决策追踪

背景决议：

- Phase 3 design refinement review 提出的 BQ1 / BQ2 / BQ3 已由 controller 裁决为 accepted，并经用户确认进入 design fix / write-back。
- Phase 3 创建 minimal dispatch intent / dispatch record row，作为 `ATTEMPT_STARTED` startup truth 的一部分；Phase 3 只写 `pending` 与 `cancelled`。
- active Run invariant 第一版优先采用 SQLite partial unique index on active Run statuses，让 active truth 跟随 `runs.status`。
- queue FIFO truth 是 queued Run 的 accepted `event_sequence`，不是内存队列或 after-commit wakeup 顺序。
- operation idempotency 的 scope、digest、result refs 必须在 Phase 3 plan / implementation 前按 operation 固定。

追踪项：

- Phase 4 repo-review follow-up 已修复 admission-backed public facade 关闭 handle 后绕过 lifecycle guard 的问题；`retry_run`、`replay_run`、`resolve_wait`、`purge_session` 当前仍是 stable unsupported deferred facade，不接触 admission service 或 durable store。该 residual risk 由本总控追踪区持有：当前不作为 Phase 4 follow-up fix scope；若后续公共契约要求所有 deferred facade 在 closed handle 后也优先返回 `HostApiErrorCode.INVALID_STATE`，必须作为新的 Host public API contract work unit 进入独立 Gateflow，并由对应 deferred capability owner 先回写 `docs/host/design.md` 与 phase plan。
- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening owns terminal closeout 后 queue promotion wakeup failure 的诊断、重试、扫描与恢复。
- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening owns dispatch record recovery join、positive orphan proof、RECOVERING dispatch、startup recovery scan 与多进程 hardening。
- Steer、retry / replay、context compaction 分别由其对应 phase plan 接入，不得回退到 Phase 3 dispatch primitive 中补实现。

#### Phase 1 Runtime Lane 风险追踪

结论：

- Phase 1 runtime lane 是 cross-process runtime capacity coordinator，不是 Host durable truth、lease / fencing、Attempt owner、EventLog ordering、admission 或 recovery proof。
- Phase 1 plan review loop 已确认 runtime lane 使用独立 SQLite runtime lane DB，且 successful acquire 的 stale cleanup、active count 与 insert 必须在同一个 SQLite transaction 内完成。
- runtime lane 的 residual risks 属于 Phase 1 implementation validation 与 Phase 11 multi-process hardening 观察项，不阻塞 Phase 1 plan 进入用户确认。

追踪项：

- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening 可基于 Phase 1 lane DB 行为补充压力测试和长期残留 DB cleanup 策略，但不得把 lane token 升级为 Host truth。

#### Remote 物理执行 exactly-once 非目标

结论：

- 第一版不保证 exactly-once 远程物理执行。
- Host 只保证 canonical EventLog、Run / Attempt 状态和 Tool fact accept 的治理正确性。
- 远端 worker 在 Host 崩溃、断连或超时后可能继续执行旧 attempt；Host 必须通过 `execution_id` 和 active Attempt 校验拒绝迟到 terminal / tool fact。
- 外部副作用必须依赖工具级 idempotency key、tool policy、adapter best-effort cancel 和诊断追踪降低风险；不能依赖 Host lease / fencing 兜底。

追踪项：

- Phase 14. RemoteProxy / RemoteStub 必须测试旧 `execution_id` 的迟到 Engine event、迟到 tool result、迟到 terminal 只能进入 diagnostic / trace，不能污染 canonical EventLog。
- Phase 12 tool policy provider 与 adapter hardening owner 必须保持外部副作用工具的 idempotency key、side-effect policy 与 best-effort cancel / revoke 边界。
- Phase 14. RemoteProxy / RemoteStub 不得引入远端 takeover attempt、远端 append EventLog 或远端更新 Run 状态。

#### Session Purge / Archive 追踪

结论：

- 第一版提供 `purge_session`，用于清理已关闭且所有 Run 已终态的 Session 的 Host 本地数据。
- `purge_session` 是 destructive purge，不是 close、cancel、archive、memory forget 或 UI hide。
- `purge_session` 必须保留最小 purge tombstone / audit record；purge 后不再支持恢复、resume、retry、replay、timeline 补读或 final answer 找回。
- `archive_session` 不进入第一版。archive 的语义是把冷 Session 移到 archive storage，保留可审计、可查询、可按需恢复的只读档案；archive 不删除事实。

追踪项：

- Phase 15. Retention / Purge / Production Hardening 必须细化 `purge_session` 删除范围、tombstone 存储位置和 destructive cleanup 语义。
- Phase 15. Retention / Purge / Production Hardening 必须定义共享 cold artifact 的引用计数或 ref 检查，防止 purge 删除仍被其它 Session 引用的 artifact。
- 后续单独追踪 `archive_session` 的需求和边界；不得用 `purge_session` 模拟 archive。

#### Host 跨层测试策略追踪

结论：

- Host 测试不能只依赖端到端路径。
- 每个 phase 的 handoff implementation-ready plan 必须包含与该 phase 边界匹配的验证策略。
- 跨层集成测试用于验证路径组合，不替代状态机、事务、adapter、projection、recovery 的分层测试。

追踪项：

- Phase 13. Audit / Tool Trace / Outbox Projections 必须提供 Outbox、audit、usage、tool trace 的幂等追平测试。
- Phase 14. RemoteProxy / RemoteStub 必须提供迟到事件、断连、重发和 accept ack 测试。
- Phase 11. Host Lifecycle / Recovery / Multi-process Hardening 必须提供 Host restart、positive orphan proof、LOST / RECOVERABLE_LOST、prompt 已 accepted 但 answer 未返回的恢复测试。

#### Phase 2 Aggregate Deepreview 追踪

结论：

- Phase 2 Durable Store / EventLog / Payload Foundation 的 aggregate deepreview 已完成；controller 接受的 `AGG-F1` 至 `AGG-F7` 均已修复并通过 AgentMiMo / AgentDS aggregate re-review，未留下 accepted finding。
- SQLite durable store、transaction runner、EventLog、idempotency、payload descriptor、local artifact helper 与 host instance liveness 均位于 `dayu.host.durable` 内，未污染 Engine / Fins / Service / UI / runtime。
- aggregate fix 只涉及 Host durable 内部正确性与诊断行为，不改变公共 API、CLI、配置、README 中的用户工作流或架构边界；因此无需额外 README 修改。

追踪项：

- Phase 11 Host Lifecycle / Recovery / Multi-process Hardening 不得把 Phase 2 `host_instances` liveness row 解释为 lease、fencing、owner、takeover 或 positive orphan proof；Phase 11 只能在 dispatch record、pid / process_start_token / boot id 与 heartbeat 等 durable facts 共同满足 positive orphan proof 后推进 recovery。
- `heartbeat_current_instance` / repeated `register_current_instance` 当前可把同一当前 instance row 从 `stopping` 刷回 `running`；owner 为 Phase 11 Host Lifecycle / Recovery / Multi-process Hardening。Phase 11 若引入严格 lifecycle 解释，必须先决定是否收紧该 transition，并补充状态回退测试。
- `SQLitePayloadWriteRequest.payload_json=None` 在 `canonical_json` 格式下表示合法 JSON `null`；后续对应 public command 或 tool accept contract work unit 若不允许隐式 null，必须在对应构造边界显式收紧，而不是修改 Phase 2 durable primitive。
- Artifact orphan cleanup owner 为 Phase 15 Retention / Purge / Production Hardening。Phase 2 只保证 rollback 后 orphan 文件不是 accepted fact；Phase 15 必须决定 orphan cleanup 是 manual diagnostic、startup diagnostic 还是 background cleanup，并补测试 / 文档。
- Artifact directory fsync failure 当前仍作为结构化 durable write error 暴露，不为平台兼容而吞掉；这是 aggregate adjudication 明确拒绝的修复方向，不安排为后续实现项。若 Phase 15 production hardening 后续要改变平台兼容策略，必须重新做 design discussion。

#### UI / Service Outbox 去重边界追踪

结论：

- 在线 / 已 attach 客户端通过 Host event stream、Session timeline、RunSnapshot 或 read model 读取 final answer。
- Outbox 只提供离线 / 外部渠道的 terminal 增量，不提供完整聊天记录或中间过程回放。
- 在线阅读路径和 Outbox 离线投递路径必须共享同一个 terminal identity。
- per-client 的 seen cursor、delivery ledger、read ack 和 channel 投递状态属于 UI / Service / channel adapter，不属于 Host truth。

追踪项：

- Phase 13. Audit / Tool Trace / Outbox Projections 必须保证 outbox item 携带稳定 `terminal_event_id`、`event_sequence`、`run_id`、`result_digest` 和幂等 item key。
- Host 外部 Service / UI 后续 work unit 必须定义 `last_seen_terminal_event_sequence` 或 `seen_terminal_event_ids` 的持久化位置和更新时机。
- Host 外部 Service / UI 后续 work unit 必须覆盖：客户端在线已展示 final answer 后离线重连，从 Outbox 读取增量时不会重复显示同一 terminal answer。
- Host 外部 UI 显示聊天记录必须按 terminal identity upsert / dedupe，不得按 final answer 文本内容去重。

#### PR 54 / P1-P5 corrected review 残余风险追踪

结论：

- PR 54 已完成 Phase 5 aggregate review、PR review fixes、追加并行 review、全仓 review、P5-only design conformance review 与 P1-P5 corrected design conformance review。
- P1-P5 corrected design conformance review 已确认当前全部代码 snapshot 未发现 blocking 设计偏离。
- PR 54 当前不需要进入新的 fix gate；draft PR 仍处于 review-ready 状态。

追踪项：

- `accept_worker_running_in_transaction` 诊断 payload 弱于 scheduler 生产路径；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- `mark_dispatching_after_lane_row` 底层 helper 能力宽于生产 scheduler 路径；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- terminal closeout 后 queue promotion wakeup failure 的诊断 / 抑制策略；owner 为 Phase 11. Host Lifecycle / Recovery / Multi-process Hardening。
- active cancel watchdog、stuck `CANCELLING` 与 orphan recovery；owner 为 Phase 11. Host Lifecycle / Recovery / Multi-process Hardening。
- RemoteProxy 语义与远端迟到事件治理；owner 为 Phase 14. RemoteProxy / RemoteStub。
- Memory、Context Governance 与 compact artifact 真实 provider 接线；owner 分别为 Phase 9. Memory 与 Phase 10. Context Governance / Compaction。
- runtime lane repeated outer cancellation、untracked release failure 与 idle scheduler sleeping task；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- Engine runner injection / provider abstraction design；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- God module / class cleanup 与 broader test hardening；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR 中不依赖 P10+ owner 的部分。

#### Phase 6 P6-S4 Truncation / fetch_more 残余风险追踪

结论：

- P6-S4 已落地 ToolRuntime-local `TruncationManager`、run-scoped opaque cursor / `scope_token` 校验、`fetch_more`
  普通 framework tool 注入，以及 `fetch_more` 通过 ToolRuntimeExecutor / accept barrier / EventLog 的普通工具事实路径。
- P6-S4 不引入 durable cursor table、recovery 续读、Engine / Host 特化分支或跨 Run 续读语义；`truncate` / `fetch_more`
  只发生在同一个 Run 内。
- P6-S4 review 未留下 blocking finding；limit 分页测试已补齐。

追踪项：

- `TruncationManager` cursor 仍为内存、ToolRuntime-local、单 Run 生命周期；Phase 11 recovery 不得把 P6-S4 cursor 解释为可恢复 durable truth。
- 当前测试允许 white-box 篡改 `_cursors` 验证 corrupt / mismatch 防御；若后续 cursor 存储结构迁移，owner 为对应迁移 slice 同步调整测试边界。
- 当前覆盖以 `text_chars` 为主；`text_lines`、`list_items`、`binary_bytes` 的更细粒度边界 hardening 归 P9.5 Pre-P10 Cross-Repository Hardening PR，不阻塞 P6-S5。

#### Phase 6 P6-S5 Duplicate Governance / Diagnostics 残余风险追踪

结论：

- P6-S5 已落地 run-local duplicate governance matrix：`allow`、`reuse`、`hint`、
  `require_justification` 与 `hard_stop`。
- duplicate key 排除 `index_in_iteration`；同 iteration 内同工具同 normalized arguments 仍进入 duplicate governance。
- `reuse` 不调用业务 callable，不追加第二个 `TOOL_RESULT_ACCEPTED`，而是通过 `TOOL_CALL_GOVERNED` 引用 prior accepted refs 后把 prior outcome 返回给 Engine。
- diagnostic emitter 当前只产生 typed diagnostic refs，不写 durable trace projection。
- DS-F1 至 DS-F4 accepted findings 已修复并通过 re-review；P6-S5 review 没有剩余 blocking finding。

追踪项：

- 默认 duplicate policy 仍为 `allow`；生产 policy provider resolution owner 为 Phase 12 ToolsDiscovery / ScenePrepare / ToolRuntime policy provider work。
- `semantic_duplicate_key_argument_name` 是 Host 内部 policy 字段且默认关闭；后续 policy provider 若启用它，必须补 dedicated tests 并明确其与 normalized arguments digest 的关系。
- `ToolFactAcceptCandidate` 对 `GOVERNED_ERROR` 的 duplicate defensive validation 仍可更严格；owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- `ToolTraceDiagnosticEmitter` typed refs 不等于 durable tool trace；durable trace projection 由 Phase 13 Audit / Tool Trace / Outbox Projections 接收。
- Durable duplicate ledger 不属于 P6；若后续需要跨进程 / crash 后恢复 duplicate index，owner 为 Phase 13 tool trace / projection owner 或单独 duplicate ledger design PR。

#### Phase 6 P6-S6 Integration / Scheduler Wiring 残余风险追踪

结论：

- P6-S6 已按 Phase 6 退出目标扩展 scope，关闭真实 `HostDispatchScheduler` 固定 no-tool RunInputBuilder 的缺口。
- 本地 scheduler 在 `HostLocalExecutionOptions.tooling_options` 非空且 `AgentPolicy.allow_tool_calls=True` 时，为当前 Attempt 构造 ToolRuntime handle，并通过 tool-enabled RunInputBuilder 把同源 schema / executor 交给 worker。
- tooling 缺失或 policy 禁用工具时，scheduler 仍保持 no-tool builder 行为。
- 新增测试覆盖真实 scheduler path：dispatch -> worker accepted request -> captured `ToolExecutor.execute` -> Host accept barrier -> `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` canonical facts。
- P6-S6 review 没有 blocking finding。

追踪项：

- `tooling_options` 当前是 construction-time 单 bundle 输入；多 profile / per-scene tool profile 仍归 Phase 12 ToolsDiscovery / ScenePrepare 或后续 policy provider owner。
- `policy_snapshot_digest` 当前是本地 policy snapshot 的诊断 digest，不是 durable attempt tool snapshot；attempt tool snapshot durability 仍归 Phase 12 ToolsDiscovery / ScenePrepare / ToolRuntime policy provider owner。
- duplicate governance 的裁决为 Run-local 语义：同一个 Run 因 `WAITING -> resolve_wait -> resume`、steer 或 recovery 创建新 Attempt 时，正常同进程生命周期内必须共享该 Run 的 duplicate memory。P6 不要求 durable duplicate ledger，也不要求 Host 崩溃 / 重启后恢复内存 index；崩溃恢复后的重复风险由 RunInputBuilder 的 accepted facts 重建兜底。Phase 7 / steer / recovery owner 不再重新裁决“是否需要 Run-local”，只按各自路径复用该语义。
- `WAITING -> resolve_wait -> resume` 是新的 LLM request。Host 不能要求无状态模型天然记住上一 Attempt 已经发过某个 tool call；resume RunInputBuilder 必须把已 accepted 的等待结果、工具事实、governance guidance 与必要上下文放回 messages。若模型仍重复发起同一个语义工具调用，Run-local duplicate governance 负责复用、提示、要求说明或阻断。
- `enable_truncation_manager=True` 是本地 tool-enabled scheduler 默认值；TruncationManager 初始化成本复核归 P9.5 Pre-P10 Cross-Repository Hardening PR，若发现需要 production scale policy 再转交 Phase 15。

#### Phase 7 Tool Awaiting / resolve_wait / Wait Adapter 残余风险追踪

结论：

- Phase 7 已落地 typed wait outcome envelope、durable wait record、ToolRuntime awaiting accept、`resolve_wait` resume / terminal closeout、`WAITING` cancel、late diagnostic、poller 与 EngineEvent confirmation boundary。
- Phase 7 不实现 callback endpoint、poller 后台循环、external job physical cancel / revoke、durable duplicate ledger 或 durable tool trace projection。

追踪项：

- Callback endpoint / auth / replay owner 为 callback adapter work unit。
- Poller 后台 loop、backoff、in-flight fencing、adapter retry、`LIMIT` / `CANCELLED` abandon 退避 owner 为 Phase 15. Retention / Purge / Production Hardening 或后续 production polling scale work unit。
- `WAITING` recovery observation、awaiting accepted ack 当前状态重校验与 scheduler close active Run reconciliation owner 为 Phase 11. Host Lifecycle / Recovery / Multi-process Hardening。
- Engine matching-ref 强校验 owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- External job physical cancel / revoke owner 为 adapter hardening work unit。
- Durable duplicate ledger owner 为单独 duplicate ledger design PR；durable tool trace projection owner 为 Phase 13. Audit / Tool Trace / Outbox Projections。

#### Phase 8 Projection Core / Host Event Stream / Minimal Read Model 残余风险追踪

结论：

- Phase 8 已落地 committed EventLog consumer framework、projection checkpoint / failure store、typed consumer contract、Host EventLog-backed event stream cursor truth regression coverage、minimal RunResult / Session timeline read model、internal repair helper 与 rebuild tests。
- Phase 8 不实现 Audit / Tool Trace / Outbox concrete sinks，不实现 automatic after-commit projection catch-up，不把 projection/read model 升级为治理真源。

追踪项：

- Automatic after-commit projection catch-up 已由 P9-S4 以 injectable `ProjectionCatchupPort` 与 best-effort post-commit hooks
  落地；production composition root concrete port 注入中不触及 snapshot history 保留模型的部分归 P9.5 Pre-P10 Cross-Repository
  Hardening PR。
- Heavy sink / batch-transaction runner owner 为 Phase 13. Audit / Tool Trace / Outbox Projections 与 Phase 15. Retention / Purge / Production Hardening。
- Per-session repair filter owner 为 Phase 15. Retention / Purge / Production Hardening。
- RunResult summary refs 接入 public `RunSnapshot` owner 为 Phase 9 / Phase 15 或后续 public read enhancement work unit。
- Audit / Tool Trace / Outbox concrete sinks owner 为 Phase 13. Audit / Tool Trace / Outbox Projections。
- Engine / OpenAI runner / parser findings owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。
- Schema CHECK hardening owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR。

#### Phase 9 Conversation Memory / Session Memory Projection design refinement 追踪

结论：

- P9 的核心定位是“财报分析工作台状态投影”，不是聊天记录压缩器。
- P9 memory view 必须明确区分 `pinned_state`、`verified_facts`、`working_assumptions` 与
  `conversation_continuity`；不得把工具事实、assistant conclusion、用户说法和 episode summary 混成无结构字符串列表。
- P9 必须为后续跨多年弱信号归因召回预留 Host 中立 evidence anchor、claim status、provenance 与 trace included /
  excluded reason 边界；长期 retrieval index、业务 signal ledger、signal-to-outcome verification 与 public memory edit / reset /
  forget API 不进入 P9。
- P9 不实现 LLM compaction 写 truth；LLM 产出的 pinned patch、episode summary 或 conclusion 默认只能成为 candidate /
  assumption / continuity view。proactive compaction 编排归 Phase 10 Context Governance。

追踪项：

- P9 plan 必须把 memory snapshot schema、claim status、provenance refs、snapshot cursor、policy digest、included / excluded reason、
  lag threshold 与 repair trigger 落成可实现的 typed contract 与测试矩阵。
- P9 plan 必须保持 Host 业务中立，不得让 Host import `dayu.fins`、不得保存网页新闻 / 公告 / 研报摘录 / 财报 chunk 原文、
  不得把 company / business-line / technology release 等财报业务语义写进 Host memory schema。
- Issue 39 owner 后续实现 query-time retrieval 与 signal-to-outcome verification 时，必须复用 P9 的中立 anchor / claim /
  provenance / trace 边界；若发现边界不足，先回写 `docs/host/design.md` 再实施。

#### Phase 9 plan gate 追踪

结论：

- P9 handoff implementation-ready plan artifact 为 `docs/host/phase9-conversation-memory-plan.md`。
- Plan review artifacts 为 `docs/reviews/p9-plan-review-mimo-20260516.md` 与
  `docs/reviews/p9-plan-review-ds-20260516.md`。
- Plan re-review artifacts 为 `docs/reviews/p9-plan-rereview-mimo-20260516.md` 与
  `docs/reviews/p9-plan-rereview-ds-20260516.md`。
- Controller adjudication artifact 为 `docs/reviews/p9-plan-review-controller-adjudication-20260516.md`。
- Re-review verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- Accepted plan commit 为 `469baaa`。

追踪项：

- 当前无 accepted blocking plan finding。
- P9 implementation 必须按 accepted plan 的 slice 顺序推进；若 implementation agent 发现现有 `TOOL_RESULT_ACCEPTED` 无法提供任何可审计
  summary / ref / digest 组合、repair-required 无法在不修改 Run 状态机的情况下表达、Memory provider 接入需要修改 Engine message
  contract，或必须让 Host 理解财报业务 subject 类型，必须停回 design / control gate。

#### Phase 9 Slice 1 Durable Memory Contracts and Schema 追踪

结论：

- P9-S1 implementation 已完成，交付 memory typed contracts、schema v6 memory projection tables、transaction-scoped durable
  read / write primitive 与 focused tests。
- Code review artifacts 为 `docs/reviews/p9-s1-code-review-mimo-20260517.md` 与
  `docs/reviews/p9-s1-code-review-ds-20260517.md`。
- Code re-review artifacts 为 `docs/reviews/p9-s1-code-rereview-mimo-20260517.md` 与
  `docs/reviews/p9-s1-code-rereview-ds-20260517.md`。
- Controller adjudication artifact 为 `docs/reviews/p9-s1-code-review-controller-adjudication-20260517.md`。
- Re-review verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- Accepted slice commit 为 `f221aeb`。

验证：

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py`：21 passed。
- `pytest tests/host/test_weak_typing_guard.py`：1 passed。
- `pyright dayu/host tests/host`：0 errors。
- `git diff --check`：通过。

追踪项：

- DS C1 non-TOOL `producer_name` 语义精度由 P9-S2 projection consumer / stable layer owner 处理；当前 fallback
  不产生 false tool provenance，不阻塞 S1。
- MiMo N1 included / excluded reason 命名稳定性由 P9-S2 在下游 rendering / trace consumer 固化前复核。
- MiMo N3 `MemoryDiagnostic.recorded_at` optional type surface、DS C3 optional JSON helper wording、DS S3 empty snapshot 双实例构造、
  DS T1 cast 注释属于 P9.5 Pre-P10 Cross-Repository Hardening PR 的 Host cleanup / test hardening，不阻塞 P9。
- DS A1 snapshot upsert 并发 guard 由 P9-S2 / P9-S4 在 projection writer concurrency 与 repair 语义明确后裁决。

#### Phase 9 Slice 2 Projection Consumer and Stable Layer Builder 追踪

结论：

- P9-S2 implementation 已完成，交付 `ConversationMemoryProjectionConsumer`、EventLog-to-memory pure builder、verified fact
  extraction、working assumption / continuity classification、history pool budget 选择与 ProjectionRunner integration tests。
- Code review artifacts 为 `docs/reviews/p9-s2-code-review-mimo-20260517-0905.md` 与
  `docs/reviews/p9-s2-code-review-ds-20260517.md`。
- Code re-review artifacts 为 `docs/reviews/p9-s2-code-rereview-mimo-20260517.md` 与
  `docs/reviews/p9-s2-code-rereview-ds-20260517.md`。
- Controller adjudication artifact 为 `docs/reviews/p9-s2-code-review-controller-adjudication-20260517.md`。
- Re-review verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- Accepted slice commit 为 `4f35da6`。

验证：

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py`：35 passed。
- `pytest tests/host/test_weak_typing_guard.py`：1 passed。
- `pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py`：0 errors。
- `git diff --check`：通过。

追踪项：

- Slice 3 必须确保 `RunInputBuilder` 按 P9 固定顺序消费 memory stable layer，且 legacy `SessionContinuityProvider`
  不再注入未经过 memory history pool 预算的 historical raw turns。S3 已完成。
- Unsupported event type 初版曾复用通用 diagnostic reason；P9 all-repository follow-up 已新增独立
  `unsupported_event_type` reason，并随 schema v7 落地。
- `stable_layer_size_units` 在 S2 仍未消费；S3 memory message renderer 必须裁决该上限如何约束 rendered stable layer。
  S3 已裁决为：stable memory blocks 按 P9 优先级消费该 cap，超预算 block 记录 transient
  `BUDGET_LIMIT_REACHED` diagnostic；recent raw turns、episode summaries 与当前 prompt 不进入 stable layer cap。

#### Phase 9 Slice 4 Projection Repair / Rebuild Entry and Diagnostics 追踪

结论：

- P9-S4 implementation 已完成，交付 `dayu.host.memory_repair` rebuild / catch-up entry、consumer-scoped memory projection
  reset、通用 `ProjectionCatchupPort` / no-op port / best-effort helper，以及 start / follow-up / terminal closeout /
  scheduler promotion / ToolRuntime tool fact accept / resolve_wait after-commit catch-up wiring。
- Code review artifacts 为 `docs/reviews/p9-s4-code-review-mimo-20260517.md` 与
  `docs/reviews/p9-s4-code-review-ds-20260517.md`。
- Code re-review artifacts 为 `docs/reviews/p9-s4-code-rereview-mimo-20260517.md` 与
  `docs/reviews/p9-s4-code-rereview-ds-20260517.md`。
- Controller adjudication artifact 为 `docs/reviews/p9-s4-code-review-controller-adjudication-20260517.md`。
- Re-review verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- Accepted slice commit 为 `1d30725`。

验证：

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py`：129 passed。
- `pyright dayu/host tests/host`：0 errors。
- `git diff --check`：通过。

追踪项：

- P9-S4 不把 catch-up failure 升级为 Run recovery，也不让 catch-up failure 回滚已提交 command / accept result；失败通过
  `dayu.host.projection` logger 和 projection-local failure row 观测。
- 默认 command handle / admission service 使用 no-op catch-up port；production concrete memory catch-up port 注入中不触及 snapshot
  history 保留模型的部分归 P9.5 Pre-P10 Cross-Repository Hardening PR，不阻塞 P9。
- Late `resolve_wait` rejection 可能额外触发一次 catch-up；当前只产生低风险冗余，不改变 EventLog、Run 状态或 projection
  truth，归 P9.5 Pre-P10 Cross-Repository Hardening PR。
- Heavy sink / batch runner、per-session repair filter 与 Audit / Tool Trace / Outbox concrete sinks 仍归 Phase 13 / Phase 15。

#### Phase 9 aggregate deepreview 追踪

结论：

- P9 aggregate deepreview 已完成，review 范围为 `f27ce8a..1b19b35` 的 Phase 9 plan、implementation、docs 与历史 slice
  裁决。
- Aggregate review artifacts 为 `docs/reviews/p9-aggregate-deepreview-mimo-20260517.md` 与
  `docs/reviews/p9-aggregate-deepreview-ds-20260517.md`。
- Controller adjudication artifact 为 `docs/reviews/p9-aggregate-deepreview-controller-adjudication-20260517.md`。
- Verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- Accepted deepreview commit 为 `cc05f79`。

验证：

- P9-S4 final validation：129 focused Host tests passed；`pyright dayu/host tests/host` 0 errors；`git diff --check` 通过。
- AgentMiMo 额外验证：memory / run_input / durable schema subset 63 passed；memory / run_input / projection pyright subset 0 errors。
- AgentDS 额外验证：手动验证 memory import boundary 与 weak typing discipline，无 blocking finding。

追踪项：

- `MemoryIncludedReason` / `MemoryExcludedReason` 粒度低于 plan 规格与 per-item excluded reason 精度，owner 为
  Phase 10 Context Governance / Phase 13 Tool Trace / memory reason schema owner；unsupported event diagnostic reason 已在 all-repository follow-up 修复。
- `WorkingAssumptionView` 暂无主动数据填充路径，owner 为 Phase 10 proactive compaction / issue 39 retrieval。
- `current_goal` first-write-wins、`SessionContinuityProvider` snapshot 参数清理、preview facts exclusion 专项测试、memory import
  boundary 自动化测试与 catch-up end-to-end 专项测试，owner 为 P9.5 Pre-P10 Cross-Repository Hardening PR；若实施中触及
  Conversation Memory snapshot history 保留模型，则该子项必须转交前述单独 PR。
- production concrete memory catch-up port 注入中不触及 snapshot history 保留模型的部分，owner 为 P9.5 Pre-P10 Cross-Repository
  Hardening PR。
- Synchronous best-effort catch-up 的 batch 化与性能治理，owner 为 Phase 13 / Phase 15。

#### Phase 9 draft PR gate 追踪

结论：

- Draft PR 已创建：PR 59 https://github.com/noho/dayu-agent-r/pull/59。
- PR review artifacts 为 `docs/reviews/p9-pr-review-mimo-20260517.md` 与
  `docs/reviews/p9-pr-review-ds-20260517.md`。
- Controller PR review adjudication artifact 为 `docs/reviews/p9-pr-review-controller-adjudication-20260517.md`。
- Verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。
- GitHub 当前未上报 checks；本地 final validation 与 PR review gate 均通过。
- Accepted PR review commit 为 `67458cb`。

追踪项：

- PR 59 仍为 draft。mark ready for review、merge、request reviewers、delete branch 或对外 comment 需额外授权。
- 当前无 PR review blocking fix。

## 历史记录

### 2026-05-17 P9.5 design discussion accepted

P9.5 Pre-P10 Cross-Repository Hardening PR design discussion 已完成，设计讨论结果已写入 `dayu/README.md`、
`docs/design.md` 与本文档。已确认的 P9.5 scope 包含 Engine runner protocol decoupling、minimal read model
single-consumer reset contract、durable / public API error taxonomy、Command handle internal service encapsulation /
lifecycle guard、LocalProxy close / events race、read API enum mapping、ToolRuntime / memory boundary cleanup、runtime
lane hardening、message / tool result size governance、Host durable helper API tightening、schema CHECK hardening、Engine /
OpenAI runner / parser hardening、Engine / Host necessary log by level semantics、Contract Ownership conformance audit、
P9 memory cleanup / test hardening，以及不触及 snapshot history 保留模型的 production memory projection catch-up
composition wiring。

用户已确认关键裁决：Engine runner 不做 factory / registry，只做 Agent 主链路消费 `AsyncRunner` protocol；minimal read
model 维持 single-consumer reset contract，不引入 multi-consumer schema；Command handle 内部 service 不暴露给 Service /
UI 或测试；工具定义与执行边界按 `docs/design.md` 写入 Contract Ownership audit 检查点。

当前 gate 为 P9.5 accepted design discussion commit；commit 后进入 P9.5 implementation-ready handoff plan。plan 必须先经
AgentMiMo / AgentDS 双路 plan review 与 controller adjudication 通过，才可派发 implementation。

### 2026-05-17 P9 draft PR review accepted

P9 draft PR 已创建：PR 59 https://github.com/noho/dayu-agent-r/pull/59。PR review gate 已完成：
AgentMiMo artifact 为 `docs/reviews/p9-pr-review-mimo-20260517.md`，AgentDS artifact 为
`docs/reviews/p9-pr-review-ds-20260517.md`。Controller adjudication artifact 为
`docs/reviews/p9-pr-review-controller-adjudication-20260517.md`。

Verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。PR review 未发现 release-blocking issue；
当前 GitHub 未上报 checks。

Accepted PR review commit 为 `67458cb`。当前 gate 为 draft-PR-pass。

### 2026-05-17 P9 aggregate deepreview accepted

P9 aggregate deepreview 已完成。AgentMiMo artifact 为
`docs/reviews/p9-aggregate-deepreview-mimo-20260517.md`，AgentDS artifact 为
`docs/reviews/p9-aggregate-deepreview-ds-20260517.md`。Controller adjudication artifact 为
`docs/reviews/p9-aggregate-deepreview-controller-adjudication-20260517.md`。

Verdict：AgentMiMo PASS，AgentDS PASS，remaining blocking findings 为 0。Controller 接受 aggregate deepreview 为
Phase 9 exit gate；non-blocking findings 已写入 Phase 9 aggregate deepreview 追踪项并分配 owner。当前 gate 为
draft PR gate；用户已授权 push、创建 draft PR 并继续推进 PR review。

Accepted deepreview commit 为 `cc05f79`。

### 2026-05-17 P9-S4 code review accepted

P9-S4 `Projection Repair / Rebuild Entry and Diagnostics` implementation 已完成。实现范围包含 memory projection rebuild /
catch-up service、consumer-scoped reset、ProjectionRunner-backed catch-up、projection-local failure recording、after-commit
best-effort catch-up hooks，以及 command / scheduler / ToolRuntime / resolve_wait 接线。

双路 code review artifacts 为 `docs/reviews/p9-s4-code-review-mimo-20260517.md` 与
`docs/reviews/p9-s4-code-review-ds-20260517.md`。双路 re-review artifacts 为
`docs/reviews/p9-s4-code-rereview-mimo-20260517.md` 与
`docs/reviews/p9-s4-code-rereview-ds-20260517.md`。Controller adjudication artifact 为
`docs/reviews/p9-s4-code-review-controller-adjudication-20260517.md`。Re-review verdict：AgentMiMo PASS，AgentDS
PASS，remaining blocking findings 为 0。

Controller 接受并修复 resolve_wait hook、ToolRuntime tool fact accept hook、catch-up failure logging 与
`ProjectionCatchupPort` ownership 迁移；接受 consumer-scoped reset 清理同 consumer 全部 policy snapshot，因为 projection
checkpoint 是 consumer-scoped。Controller defer late rejection extra catch-up、future duplicate hook cleanup 与 synchronous
best-effort catch-up 性能优化，均不阻塞 P9。

验证：

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py`：129 passed。
- `pyright dayu/host tests/host`：0 errors。
- `git diff --check`：通过。

Accepted slice commit 为 `1d30725`。当前 gate 为 P9 aggregate deepreview。

### 2026-05-17 P9-S3 code review accepted

P9-S3 `RunInputBuilder MemorySnapshotProvider and Lag Fallback` implementation 已完成。实现范围包含
`DurableMemorySnapshotProvider`、`MemoryProjectionRepairRequired`、RunInputBuilder memory snapshot 渲染、small-lag inline
delta fallback、missing / damaged / over-threshold / ahead-of-required repair-required 路径，以及 legacy
`DurableSessionContinuityProvider` 收敛为 resume-specific continuity。

双路 code review artifacts 为 `docs/reviews/p9-s3-code-review-mimo-20260517.md` 与
`docs/reviews/p9-s3-code-review-ds-20260517.md`。双路 re-review artifacts 为
`docs/reviews/p9-s3-code-rereview-mimo-20260517.md` 与
`docs/reviews/p9-s3-code-rereview-ds-20260517.md`。Controller adjudication artifact 为
`docs/reviews/p9-s3-code-review-controller-adjudication-20260517.md`。Re-review verdict：AgentMiMo PASS，AgentDS
PASS，remaining blocking findings 为 0。

Controller 接受并修复 snapshot ahead-of-required repair、stable layer budget consumption、当前 prompt event-id-only 去重、
episode summary event 常量、covered snapshot cursor 测试一致性，以及 inline delta + stable budget 交叉测试。DS 关于生产
required cursor 改为 Run started boundary 的建议不接受；P9 plan 明确规定使用
`current_facts.attempt.started_event_sequence - 1`，以允许 resume / steer / recovery 新 Attempt 前 committed facts 进入
memory。

验证：

- `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_weak_typing_guard.py`：49 passed。
- `pyright dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py tests/host`：0 errors。
- `git diff --check`：通过。

Accepted slice commit 为 `b416d37`。当前 gate 为 P9-S4 `Projection Repair / Rebuild Entry and Diagnostics` implementation。

### 2026-05-17 P9-S2 code review accepted

P9-S2 `Projection Consumer and Stable Layer Builder` implementation 已完成。实现范围包含 `dayu.host.memory` 中的
`MemoryProjectionEvent`、EventLog-to-memory snapshot builder、verified fact extraction、history pool policy；以及
`dayu.host.durable.memory` 中的 `ConversationMemoryProjectionConsumer`。双路 code review 已完成：AgentMiMo 初审 verdict 为
PASS，提出 1 个 medium 与 2 个 low findings；AgentDS 初审 verdict 为 PASS，提出 3 个 medium 与 1 个 low finding。Controller
接受 assistant conclusion budget、`recent_raw_turns_floor=0`、missing `tool_name` provenance、malformed `source_refs` 与
unknown event type diagnostic 五项修复。Fix 后双路 re-review 均 PASS，remaining blocking findings 为 0。Controller
adjudication artifact 为 `docs/reviews/p9-s2-code-review-controller-adjudication-20260517.md`。Accepted slice commit 为 `4f35da6`。
当前 gate 为 P9-S3 `RunInputBuilder MemorySnapshotProvider and Lag Fallback` implementation。

### 2026-05-17 P9-S1 code review accepted

P9-S1 `Durable Memory Contracts and Schema` implementation 已完成。实现范围包含 `dayu.host.memory` typed contracts、
`dayu.host.durable.memory` transaction-scoped memory snapshot / diagnostic read-write primitive、schema v6 memory projection
tables 与 focused tests。双路 code review 已完成：AgentMiMo 初审 verdict 为 CONDITIONAL PASS，提出 1 个 blocking 与 3 个
non-blocking findings；AgentDS 初审 verdict 为 PASS with findings，提出 0 个 blocking、3 个 medium、3 个 low 与 2 个 info
findings。Controller 接受 MiMo B1 / DS C2 digest deterministic fix 与 MiMo N2 reserved claim status test coverage fix，defer
non-blocking producer name precision、reason naming、diagnostic timestamp type surface 与 hardening items 到 P9-S2 / P9-S4 或 P9.5
Pre-P10 Cross-Repository Hardening PR。Fix 后双路 re-review 均 PASS，remaining blocking findings 为 0。Controller adjudication artifact 为
`docs/reviews/p9-s1-code-review-controller-adjudication-20260517.md`。Accepted slice commit 为 `f221aeb`。当前 gate 为
P9-S2 `Projection Consumer and Stable Layer Builder` implementation。

### 2026-05-16 P9 plan accepted

P9 handoff implementation-ready plan 已生成于 `docs/host/phase9-conversation-memory-plan.md`。双路 plan review 已完成：
AgentMiMo 初审 verdict 为 PASS with findings，提出 2 个 blocking、5 个 medium、3 个 low findings；AgentDS 初审 verdict 为 PASS，
提出 0 个 blocking、2 个 medium、3 个 low、1 个 info finding。Controller 裁决接受 provider 接线、`MemorySnapshotView` shape、
claim status lifecycle、`RUN_SUCCEEDED` continuity、`required_event_sequence`、`open_questions` placement、history pool 算法、
Host-neutral ref、`TOOL_RESULT_ACCEPTED` mapping、diagnostic/failure 分工与 digest canonicalization 等修正项；拒绝固定 40 / 60
magic budget split 和业务词 blocklist 作为修复方式。Planning agent 已修正 plan。双路 re-review 均 PASS，remaining blocking findings 为
0。Controller adjudication artifact 为 `docs/reviews/p9-plan-review-controller-adjudication-20260516.md`。当前 gate 为等待用户确认进入
P9 implementation。Accepted plan commit 为 `469baaa`。

### 2026-05-16 P9 design refinement

Controller 按 `$phaseflow` 启动 P9。总控文档识别当前状态为 P8 completed / draft-PR-pass，下一 work unit 为 Phase 9
`Conversation Memory / Session Memory Projection`。用户确认 P9 phase discussion 裁决：P9 是“财报分析工作台状态投影”，
不是聊天记录压缩器；memory view 分为 `pinned_state`、`verified_facts`、`working_assumptions`、
`conversation_continuity`；verified facts 只接受工具事实并保留 evidence / provenance refs；RunInputBuilder 注入顺序按财报分析优先级固定；
预算策略保持克制；projection lag 必须显式可观测且不得触发 Run recovery；P9 不实现 LLM compaction 写 truth；测试重点围绕反幻觉与
EventLog 可重建。用户同时确认参考 issue 39 的未来长期证据召回目标，但 P9 只预留 Host 中立 evidence anchor / claim status /
provenance / trace included-excluded 边界，不实现长期 retrieval、业务 signal ledger 或 signal-to-outcome verification。`docs/host/design.md`
§24 与本文档 Phase 9 条目已写回上述裁决。当前 gate 为 P9 handoff implementation-ready plan，下一步派发 planning agent。

### 2026-05-16 P8 完成前滚动状态归档

Phase 5 `RunInputBuilder 与本地执行 Dispatch` 已完成。PR 54
`Host Phase 5 RunInputBuilder and local dispatch` 已完成 Phase 5 aggregate review、PR review fix、追加并行 review、全仓 review
与 P1-P5 corrected design conformance review；最近一次 corrected gate 的 AgentMiMo、AgentDS、AgentCodex 三路 verdict 均为
PASS，blocking design deviation 为 0。Controller adjudication artifact 为
`docs/reviews/p1-p5-design-conformance-review-controller-adjudication-20260515.md`。

当前不处于 implementation / fix gate；没有 accepted blocking finding 待修。用户手工 merge PR 54 后，下一步按 `$phaseflow`
推进 Phase 6 `ToolRuntime / Truncation / fetch_more / Duplicate Governance`。Phase 6 design discussion 输入 artifact 为
`docs/reviews/host-phase6-design-discussion-codex-20260515.md`，controller 裁决 artifact 为
`docs/reviews/host-phase6-design-discussion-controller-adjudication-20260515.md`；裁决后的 design write-back 已同步到
`docs/host/design.md` 与本文档。Phase 6 handoff implementation-ready plan 为
`docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`；plan review artifacts 为
`docs/reviews/host-phase6-plan-review-mimo-20260515.md` 与
`docs/reviews/host-phase6-plan-review-ds-20260515.md`；controller plan review adjudication artifact 为
`docs/reviews/host-phase6-plan-review-controller-adjudication-20260515.md`。Plan fix 后，plan re-review artifacts 为
`docs/reviews/host-phase6-plan-re-review-mimo-20260515.md` 与
`docs/reviews/host-phase6-plan-re-review-ds-20260515.md`；controller plan re-review adjudication artifact 为
`docs/reviews/host-phase6-plan-re-review-controller-adjudication-20260515.md`。两路 re-review 均 PASS，blocking count 为 0。
Phase 6 accepted plan commits 为 `04517f5` / `a5863ce`。P6-S1
`Effective ToolBundle And RunInputBuilder Wiring` 已完成 implementation、双路 code review 与 controller adjudication，
accepted checkpoint commit 为 `b49ba56`。P6-S1 artifacts 为
`docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md`、
`docs/reviews/host-phase6-code-review-s1-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s1-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s1-controller-adjudication-20260515.md`。P6-S2
`Host Accept Barrier And Tool Canonical Facts` 已完成 implementation、双路 code review 与 controller adjudication，
accepted checkpoint commit 为 `54184e6`。P6-S2 artifacts 为
`docs/reviews/host-phase6-implementation-s2-accept-barrier-20260515.md`、
`docs/reviews/host-phase6-code-review-s2-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s2-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s2-controller-adjudication-20260515.md`。P6-S3
`ToolExecutor Wrapper, Ack Retry, Side-effect Policy, Awaiting Guard` 已完成 implementation、双路 code review 与 controller
adjudication，accepted checkpoint commit 为 `de7a4ae`。P6-S3 artifacts 为
`docs/reviews/host-phase6-implementation-s3-executor-wrapper-20260515.md`、
`docs/reviews/host-phase6-code-review-s3-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s3-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s3-controller-adjudication-20260515.md`。P6-S4
`TruncationManager And fetch_more Normal Tool Path` 已完成 implementation、双路 code review 与 controller adjudication，
accepted checkpoint commit 为 `28adf70`。P6-S4 artifacts 为
`docs/reviews/host-phase6-implementation-s4-truncation-fetch-more-20260515.md`、
`docs/reviews/host-phase6-code-review-s4-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s4-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s4-controller-adjudication-20260515.md`；验证为
`pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q`
15 passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check` clean。P6-S5
`Duplicate Governance And Diagnostic Emitter` 已完成 implementation、双路 code review、accepted finding fix、DS re-review 与
controller adjudication，accepted checkpoint commit 为 `31ab68d`。P6-S5 artifacts 为
`docs/reviews/host-phase6-implementation-s5-duplicate-governance-20260515.md`、
`docs/reviews/host-phase6-code-review-s5-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s5-ds-20260515.md`、
`docs/reviews/host-phase6-fix-s5-duplicate-governance-20260515.md`、
`docs/reviews/host-phase6-code-re-review-s5-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s5-controller-adjudication-20260515.md`；验证为
`pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q`
24 passed、P6 ToolRuntime 相关 46 tests passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check` clean。P6-S6
`Integration, Scheduler Wiring, And Gate Validation` 已完成 implementation、双路 code review 与 controller adjudication，
accepted checkpoint commit 为 `53ff69f`。P6-S6 artifacts 为
`docs/reviews/host-phase6-implementation-s6-integration-gate-20260515.md`、
`docs/reviews/host-phase6-code-review-s6-mimo-20260515.md`、
`docs/reviews/host-phase6-code-review-s6-ds-20260515.md` 与
`docs/reviews/host-phase6-code-review-s6-controller-adjudication-20260515.md`；验证为
`pytest tests/host -q` 348 passed、`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check` clean。Phase 6
aggregate review 已完成，初次 aggregate review artifacts 为
`docs/reviews/host-phase6-aggregate-review-mimo-20260515.md`、
`docs/reviews/host-phase6-aggregate-review-ds-20260515.md` 与
`docs/reviews/host-phase6-aggregate-review-controller-adjudication-20260515.md`；两路 review 均接受 P6-AGG-F1：
Run-local duplicate governance index 仍跟随 ToolRuntime 实例生命周期，不满足 P6 exit standard。P6-AGG-F1 已通过
`docs/reviews/host-phase6-aggregate-fix-run-local-duplicate-governance-20260515.md` 修复，并由
`docs/reviews/host-phase6-aggregate-re-review-mimo-20260515.md`、
`docs/reviews/host-phase6-aggregate-re-review-ds-20260515.md` 与
`docs/reviews/host-phase6-aggregate-re-review-controller-adjudication-20260515.md` 确认 PASS。Phase 6 accepted aggregate
review commit 为 `8f73821`；验证为 `pytest tests/host -q` 349 passed、
`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check` clean。Phase 6 PR 已创建为
https://github.com/noho/dayu-agent-r/pull/55；当前 gate 为 PR 55 deepreview。需要继续追踪的
non-blocking hardening、deferred capability 与后续 phase owner 已写入 `Open Questions 与风险追踪` 的
`PR 54 / P1-P5 corrected review 残余风险追踪`、P6-S1 controller adjudication residual risks、P6-S2 controller
adjudication residual risks、P6-S3 controller adjudication residual risks、P6-S4 controller adjudication residual risks，以及
P6-S5 / P6-S6 controller adjudication residual risks。P6-S3 遗留的真实 `HostDispatchScheduler` no-tool composition wiring 已由 P6-S6 关闭；
PR 55 创建后按用户指令安排 AgentMiMo 与 AgentDS 执行 `/deepreview PR 55`。PR review artifacts 为
`docs/reviews/pr-55-deepreview-mimo-20260515.md` 与
`docs/reviews/pr-55-deepreview-ds-20260515.md`；controller adjudication 为
`docs/reviews/pr-55-deepreview-controller-adjudication-20260515.md`。AgentMiMo PASS；AgentDS PASS 但提出 PR55-DS-1
中严重度 finding，controller 裁决为 accepted 并由
`docs/reviews/pr-55-fix-accept-retry-exhausted-20260515.md` 修复，fix commit 为 `c79d6b8`。PR 55 re-review artifacts 为
`docs/reviews/pr-55-re-review-mimo-20260515.md` 与
`docs/reviews/pr-55-re-review-ds-20260515.md`，两路均 PASS；验证为 `pytest tests/host -q` 350 passed、
`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check` clean。Phase 6 状态为 completed；PR 55 已由用户手工
merge。Phase 7 `Tool Awaiting / resolve_wait / Wait Adapter` design discussion、design write-back、双路 design re-review、
accepted design findings fix 与双路 design fix re-review 已完成。Artifacts 为
`docs/reviews/host-phase7-design-discussion-codex-20260516.md`、
`docs/reviews/host-phase7-design-re-review-mimo-20260516.md`、
`docs/reviews/host-phase7-design-re-review-ds-20260516.md`、
`docs/reviews/host-phase7-design-re-review-controller-adjudication-20260516.md`、
`docs/reviews/host-phase7-design-fix-re-review-mimo-20260516.md`、
`docs/reviews/host-phase7-design-fix-re-review-ds-20260516.md` 与
`docs/reviews/host-phase7-design-fix-re-review-controller-adjudication-20260516.md`。当前 gate 为 Phase 7
handoff implementation-ready plan。Phase 7 handoff implementation-ready plan 已写入
`docs/host/phase7-tool-awaiting-resolve-wait-plan.md`。Plan review artifacts 为
`docs/reviews/host-phase7-plan-review-mimo-20260516.md` 与
`docs/reviews/host-phase7-plan-review-ds-20260516.md`；controller plan review adjudication artifact 为
`docs/reviews/host-phase7-plan-review-controller-adjudication-20260516.md`。Plan fix artifact 为
`docs/reviews/host-phase7-plan-fix-codex-20260516.md`。Plan re-review artifacts 为
`docs/reviews/host-phase7-plan-re-review-mimo-20260516.md` 与
`docs/reviews/host-phase7-plan-re-review-ds-20260516.md`；controller plan re-review adjudication artifact 为
`docs/reviews/host-phase7-plan-re-review-controller-adjudication-20260516.md`。两路 re-review 均 PASS，blocking count 为 0。
Phase 7 accepted plan commit 为 `d017fd7`。
P7-S1 `Public Contracts And Durable Wait Record` 已完成 implementation、双路 code review、accepted finding fix、双路 code
re-review 与 controller adjudication，accepted checkpoint commit 为 `aaa107a`。P7-S1 artifacts 为
`docs/reviews/host-phase7-s1-controller-decision-test-ownership-20260516.md`、
`docs/reviews/host-phase7-implementation-s1-public-contracts-wait-record-20260516.md`、
`docs/reviews/host-phase7-code-review-s1-mimo-20260516.md`、
`docs/reviews/host-phase7-code-review-s1-ds-20260516.md`、
`docs/reviews/host-phase7-code-review-s1-controller-adjudication-20260516.md`、
`docs/reviews/host-phase7-fix-s1-public-contracts-wait-record-20260516.md`、
`docs/reviews/host-phase7-code-re-review-s1-mimo-20260516.md`、
`docs/reviews/host-phase7-code-re-review-s1-ds-20260516.md` 与
`docs/reviews/host-phase7-code-re-review-s1-controller-adjudication-20260516.md`。验证为
`pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_public_run_api.py -q`
84 passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check` clean。
P7-S2 `ToolRuntime Awaiting Accept Path` 已完成 implementation、双路 code review、accepted finding fix、双路 code
re-review 与 controller adjudication，accepted checkpoint commit 为 `42f972a`。P7-S2 artifacts 为
`docs/reviews/host-phase7-implementation-s2-tool-awaiting-accept-20260516.md`、
`docs/reviews/host-phase7-code-review-s2-mimo-20260516.md`、
`docs/reviews/host-phase7-code-review-s2-ds-20260516.md`、
`docs/reviews/host-phase7-fix-s2-tool-awaiting-accept-20260516.md`、
`docs/reviews/host-phase7-code-re-review-s2-mimo-20260516.md`、
`docs/reviews/host-phase7-code-re-review-s2-ds-20260516.md` 与
`docs/reviews/host-phase7-code-re-review-s2-controller-adjudication-20260516.md`。验证为
`pytest tests/host -q` 374 passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check`
clean。P7-S3 `resolve_wait Command And Resume Attempt` 已完成 implementation、MiMo code review、controller accepted finding fix、MiMo
re-review、DS current-version code review 与 controller adjudication，accepted slice commit 为 `4712101`。P7-S3 artifacts 为
`docs/reviews/host-phase7-implementation-s3-resolve-wait-resume-20260516.md`、
`docs/reviews/host-phase7-code-review-s3-mimo-20260516.md`、
`docs/reviews/host-phase7-fix-s3-resolve-wait-resume-20260516.md`、
`docs/reviews/host-phase7-code-re-review-s3-mimo-20260516.md`、
`docs/reviews/host-phase7-code-review-s3-ds-20260516.md` 与
`docs/reviews/host-phase7-code-re-review-s3-controller-adjudication-20260516.md`。验证为
`pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q`
64 passed、`pytest tests/host -q` 381 passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check`
clean。P7-S4 `WAITING Cancel, Late Result Diagnostic, Poll / Manual Adapter, EngineEvent Confirmation` 已完成
implementation、双路 code review 与 controller adjudication，accepted slice commit 为 `3ccddbf`。P7-S4 artifacts 为
`docs/reviews/host-phase7-implementation-s4-wait-cancel-late-poll-20260516.md`、
`docs/reviews/host-phase7-code-review-s4-mimo-20260516.md`、
`docs/reviews/host-phase7-code-review-s4-ds-20260516.md` 与
`docs/reviews/host-phase7-code-review-s4-controller-adjudication-20260516.md`。验证为
`pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`
42 passed、`pytest tests/host -q` 388 passed、`python -m pyright dayu/host tests/host` 0 errors、`git diff --check`
clean。P7-S4 residual risks：Engine contract 当前不携带 Host accepted wait refs，P7-S4 只能做 diagnostic /
idempotent confirmation，不能验证 Engine awaiting event 与 Host accepted wait refs 完全匹配；Poller 仍是最小单轮
`poll_once()`，不包含后台调度循环、退避、并发 in-flight fencing 或 adapter 错误重试治理；`WAITING` Run + 非
`SUSPENDED` Attempt 的防御性 internal invariant error 与 late result typed public error detail 归 P9.5 Pre-P10
Cross-Repository Hardening PR；poller retry 外部化后的幂等 digest 策略归 Phase 15 / production polling scale owner。当前 gate 为 P7-S5 `Integration, Docs, Gate Validation`
implementation。P7-S5 `Integration, Docs, Gate Validation` 已完成 implementation、双路 aggregate review 与 controller
adjudication，accepted slice commit 为 `c974acf`。P7-S5 / aggregate artifacts 为
`docs/reviews/host-phase7-implementation-s5-integration-docs-gate-validation-20260516.md`、
`docs/reviews/host-phase7-aggregate-review-s5-mimo-20260516.md`、
`docs/reviews/host-phase7-aggregate-review-s5-ds-20260516.md` 与
`docs/reviews/host-phase7-aggregate-review-s5-controller-adjudication-20260516.md`。验证为 `pytest tests/host -q`
389 passed、`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check` clean。Phase 7 aggregate exit
accepted：typed wait outcome envelope、durable wait record、ToolRuntime awaiting accept、`resolve_wait` resume / terminal
closeout、`WAITING` cancel、late diagnostic、poller 与 EngineEvent confirmation boundary 均已落地。Phase 7 remaining
risks / owners：callback endpoint / auth / replay 归 callback adapter owner；poller 后台 loop / backoff /
in-flight fencing / adapter retry 归 Phase 15 / production polling scale owner；`WAITING` recovery observation 归 Phase 11；
Engine matching-ref 强校验归 P9.5 Pre-P10 Cross-Repository Hardening PR；external job physical cancel / revoke 归 adapter hardening owner；
durable duplicate ledger 与 durable tool trace projection 分别归单独 duplicate ledger design PR / Phase 13 projection or tool trace owner。
当前 gate 为 Phase 7 ready-to-open-draft-PR。Phase 7 draft PR 已创建：PR 56
`https://github.com/noho/dayu-agent-r/pull/56`，title 为 `Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter`，
head branch 为 `feat/host-phase7-tool-awaiting-resolve-wait`，PR 当前保持 draft。PR 56 deepreview artifacts 为
`docs/reviews/pr-56-deepreview-mimo-20260516.md` 与 `docs/reviews/pr-56-deepreview-ds-20260516.md`。MiMo review
PASS，无 blocking finding；DS review PASS，提出 6 个 Low 与 2 个 Info finding。Controller 接受 F1 digest 校验一致性与
F2 `WaitPollLost` 测试缺口为当前 PR fix，fix artifact 为
`docs/reviews/pr-56-fix-digest-and-poll-lost-20260516.md`，fix commit 为 `dd32948`。PR 56 fix re-review artifacts
为 `docs/reviews/pr-56-fix-re-review-mimo-20260516.md`、
`docs/reviews/pr-56-fix-re-review-ds-20260516.md` 与
`docs/reviews/pr-56-fix-re-review-controller-adjudication-20260516.md`；两份 re-review 均确认 F1 / F2 fixed、
无回归。Fix validation：`pytest tests/host/test_wait_awaiting_accept.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py -q`
15 passed、`pytest tests/host -q` 391 passed、`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check`
clean。F3 cross-test helper import coupling deferred 到 P9.5 Pre-P10 Cross-Repository Hardening PR；F4-F8 低/信息性 hardening 建议均 deferred。
PR 56 deepreview / fix / re-review gate 已完成并通过。

P1-P7 design conformance follow-up fix gate：Controller adjudication artifact
`docs/reviews/p1-p7-design-conformance-controller-adjudication-20260516.md` 接受 blocking finding
C-P1P7-001：P7 awaiting production wiring 未接入 `HostDispatchScheduler`。当前 fix gate 在分支
`fix/host-p1-p7-awaiting-production-wiring` 修复该 production wiring：`HostToolingOptions` 承载 construction-scope
`wait_adapter_registry`，`HostDispatchScheduler` 在 tool-enabled production path 构造 `ToolRuntimeBuildRequest` 时注入
`DefaultHostToolAwaitingAcceptPort` 与该 registry；adapter object 仍不进入 per-run request 或 durable wait row。Fix artifact 为
`docs/reviews/p1-p7-design-conformance-fix-awaiting-production-wiring-20260516.md`。验证结果以该 artifact 为准；本 fix
不实现 callback endpoint、poller 后台循环、recovery scan、remote worker 或 external job physical cancel。
Controller fix adjudication artifact 为
`docs/reviews/p1-p7-design-conformance-fix-controller-adjudication-20260516.md`，MiMo / DS fix re-review 均 PASS；
本地 accepted fix checkpoint commit 为 `d03e064`。
随后用户明确决定 `fetch_more` cursor 只存在内存，其它 review findings 改按当前 `docs/host/design.md` 的设计目标与最佳实践裁决。
Controller decision artifact 为 `docs/reviews/p1-p7-design-goals-controller-decision-20260516.md`，Codex fix artifact 为
`docs/reviews/p1-p7-design-goals-fix-codex-20260516.md`，MiMo / DS fix review artifact 为
`docs/reviews/p1-p7-design-goals-fix-review-mimo-20260516.md` 与
`docs/reviews/p1-p7-design-goals-fix-review-ds-20260516.md`，final adjudication artifact 为
`docs/reviews/p1-p7-design-goals-fix-controller-adjudication-20260516.md`。本地 accepted design-goals fix checkpoint commit 为
`86bcc5a`。随后用户要求按 `$gateflow` 对当前仓库执行双路全仓 deepreview，AgentMiMo 与 AgentDS review artifacts 为
`docs/reviews/repo-review-20260516-1557.md` 与 `docs/reviews/repo-review-20260516-1551.md`；controller adjudication artifact 为
`docs/reviews/gateflow-deepreview-controller-adjudication-20260516-1619.md`。Controller 接受 DS-1、DS-2、DS-4、DS-5、
DS-6、DS-18 与 MiMo-2，AgentCodex fix artifact 为
`docs/reviews/gateflow-deepreview-fix-agentcodex-20260516.md`，MiMo / DS fix re-review artifacts 为
`docs/reviews/gateflow-deepreview-fix-re-review-mimo-20260516.md` 与
`docs/reviews/gateflow-deepreview-fix-re-review-ds-20260516.md`；两路 re-review 均 PASS。验证为
`pytest tests/contracts/test_tool_schema.py tests/contracts/test_tool_declaration.py tests/host/test_durable_transaction.py tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_phase6_toolruntime_integration.py`
69 passed、`python -m pyright` 0 errors、`git diff --check` clean。本地 accepted deepreview checkpoint commit 为
`52bba89`。Phase 7 状态为 completed。Phase 8 `Projection Core / Host Event Stream / Minimal Read Model` design
discussion 已完成，输入 artifact 为 `docs/reviews/host-phase8-design-discussion-codex-20260516.md`，controller
adjudication artifact 为 `docs/reviews/host-phase8-design-discussion-controller-adjudication-20260516.md`。Controller
裁决为 PASS：Phase 8 动机成立，`docs/host/design.md` §14 / §16 与本文档 Phase 8 条目已足够进入 handoff
implementation-ready plan，无 blocking open question，无必须先写回 design / control 的 design gap。Phase 8 handoff
implementation-ready plan 已写入 `docs/host/phase8-projection-core-event-stream-plan.md`。Plan review artifacts 为
`docs/reviews/host-phase8-plan-review-mimo-20260516.md` 与 `docs/reviews/host-phase8-plan-review-ds-20260516.md`；
controller plan review adjudication artifact 为
`docs/reviews/host-phase8-plan-review-controller-adjudication-20260516.md`。Accepted plan findings 已由
`docs/reviews/host-phase8-plan-fix-codex-20260516.md` 修复。Plan re-review artifacts 为
`docs/reviews/host-phase8-plan-re-review-mimo-20260516.md` 与
`docs/reviews/host-phase8-plan-re-review-ds-20260516.md`；controller plan re-review adjudication artifact 为
`docs/reviews/host-phase8-plan-re-review-controller-adjudication-20260516.md`。两路 re-review 均 PASS，blocking count 为
0。Phase 8 accepted plan commit 为 `b85fd8e`。P8-S1 `Projection Runner / Checkpoint / Typed Consumer Contracts` 已完成
implementation、双路 code review、accepted finding fix、双路 code re-review 与 controller adjudication。P8-S1 artifacts 为
`docs/reviews/host-phase8-implementation-s1-projection-runner-20260516.md`、
`docs/reviews/host-phase8-code-review-s1-mimo-20260516.md`、
`docs/reviews/host-phase8-code-review-s1-ds-20260516.md`、
`docs/reviews/host-phase8-code-review-s1-controller-adjudication-20260516.md`、
`docs/reviews/host-phase8-fix-s1-projection-runner-20260516.md`、
`docs/reviews/host-phase8-code-re-review-s1-mimo-20260516.md`、
`docs/reviews/host-phase8-code-re-review-s1-ds-20260516.md` 与
`docs/reviews/host-phase8-code-re-review-s1-controller-adjudication-20260516.md`。两路 re-review 均 PASS，blocking count 为
0。P8-S1 accepted slice commit 为 `80c12a2`。P8-S2 `Host Event Stream Cursor Truth` 已完成 implementation、双路 code
review 与 controller adjudication。P8-S2 artifacts 为
`docs/reviews/host-phase8-implementation-s2-event-stream-cursor-20260516.md`、
`docs/reviews/host-phase8-code-review-s2-mimo-20260516.md`、
`docs/reviews/host-phase8-code-review-s2-ds-20260516.md` 与
`docs/reviews/host-phase8-code-review-s2-controller-adjudication-20260516.md`。两路 review 均 PASS，blocking count 为 0。
P8-S2 accepted slice commit 为 `c891792`。P8-S3 `Minimal RunResult / Session Timeline Read Model / Repair` 已完成
implementation、双路 code review、accepted finding fix、双路 code re-review 与 controller adjudication。P8-S3 artifacts 为
`docs/reviews/host-phase8-implementation-s3-read-model-repair-20260516.md`、
`docs/reviews/host-phase8-code-review-s3-mimo-20260516.md`、
`docs/reviews/host-phase8-code-review-s3-ds-20260516.md`、
`docs/reviews/host-phase8-code-review-s3-controller-adjudication-20260516.md`、
`docs/reviews/host-phase8-fix-s3-read-model-repair-20260516.md`、
`docs/reviews/host-phase8-code-re-review-s3-mimo-20260516.md`、
`docs/reviews/host-phase8-code-re-review-s3-ds-20260516.md` 与
`docs/reviews/host-phase8-code-re-review-s3-controller-adjudication-20260516.md`。两路 re-review 均 PASS，blocking count 为
0。P8-S3 accepted slice commit 为 `d31803d`。Phase 8 aggregate review 已完成，aggregate review artifacts 为
`docs/reviews/host-phase8-aggregate-review-mimo-20260516.md`、
`docs/reviews/host-phase8-aggregate-review-ds-20260516.md` 与
`docs/reviews/host-phase8-aggregate-review-controller-adjudication-20260516.md`。Accepted aggregate findings 已由
`docs/reviews/host-phase8-aggregate-fix-20260516.md` 修复。Aggregate re-review artifacts 为
`docs/reviews/host-phase8-aggregate-re-review-mimo-20260516.md`、
`docs/reviews/host-phase8-aggregate-re-review-ds-20260516.md` 与
`docs/reviews/host-phase8-aggregate-re-review-controller-adjudication-20260516.md`。两路 re-review 均 PASS，blocking count 为
0。Phase 8 accepted deepreview commit 为 `5b2b92e`。Ready validation 期间发现 dispatch ToolRuntime wiring
测试夹具未保持 worker stream 打开，已通过
`docs/reviews/host-phase8-readiness-validation-fix-20260516.md` 修复，修复提交为 `57975fe`。最终验证为
`pytest tests/host -q` 435 passed、`python -m pyright dayu/ tests/ utils/` 0 errors、`git diff --check`
clean。追加全仓 deepreview 闭环 artifacts 为 `docs/reviews/repo-review-20260516-2105.md`、
`docs/reviews/repo-review-20260516-2059.md`、
`docs/reviews/repo-review-controller-adjudication-20260516-2109.md`、
`docs/reviews/repo-review-fix-codex-20260516.md`、
`docs/reviews/repo-review-fix-re-review-mimo-20260516.md`、
`docs/reviews/repo-review-fix-re-review-ds-20260516.md` 与
`docs/reviews/repo-review-fix-re-review-controller-adjudication-20260516-2130.md`。Controller accepted
DR-ALL-A1 至 DR-ALL-A5 已修复，MiMo / DS re-review 均 PASS；accepted full-repo deepreview loop commit 为
`3d60fdd`。Phase 8 draft PR 已创建：PR 58
`https://github.com/noho/dayu-agent-r/pull/58`。PR 58 review artifacts 为
`docs/reviews/pr-58-review-mimo-20260516.md`、`docs/reviews/pr-58-review-ds-20260516.md` 与
`docs/reviews/pr-58-review-controller-adjudication-20260516.md`。Accepted PR finding PR58-F1 已由
`docs/reviews/pr-58-fix-codex-20260516.md` 修复，并由
`docs/reviews/pr-58-fix-re-review-ds-20260516.md` 与
`docs/reviews/pr-58-fix-re-review-controller-adjudication-20260516.md` 确认 PASS；accepted PR review commit 为
`a6cc2aa`，已 push 到 PR 58。当前 gate 为 draft-PR-pass。Phase 8 状态为 completed。Phase 8 exit accepted：committed EventLog
consumer framework、projection checkpoint / failure store、typed consumer contract、Host EventLog-backed event stream cursor
truth regression coverage、minimal RunResult / Session timeline read model、internal repair helper 与 rebuild tests 均已落地。
Phase 8 remaining risks / owners：automatic after-commit projection catch-up 归 Phase 9 owner；heavy sink /
batch-transaction runner 归 Phase 13 / Phase 15 owner；per-session repair filter 归 Phase 15 owner；RunResult summary refs
接入 public `RunSnapshot` 归 Phase 9 / Phase 15 或后续 public read enhancement owner；Audit / Tool Trace / Outbox
concrete sinks 归 Phase 13 owner；Engine / OpenAI runner / parser findings 与 schema CHECK hardening 归 P9.5 Pre-P10
Cross-Repository Hardening PR；scheduler close active Run reconciliation 归 Phase 11 recovery owner；awaiting
accepted ack 当前状态重校验归 Phase 7 / Phase 11 wait lifecycle hardening owner；poller LIMIT / CANCELLED abandon 退避归
Phase 15 / production polling scale owner。

P0：Engine Context Compaction Event 语义前置已完成 implementation 与 review loop；P0-S1 accepted slice commit 为 `ad6d116`，P0-S2 accepted slice commit 为 `6f6e716`。P0 后续状态进入 push / PR 路径，不再是当前 Host phase design gate。

Phase 4：Host Public API Command Path implementation 已完成。Phase 3 已通过 PR 50
`Host Phase 3 admission state machine` merge 到 `main`，merge commit 为
`d9c2ca9dd0d9b88b99dae96d972457a493f98f60`，merged at `2026-05-14T08:35:49Z`。
Phase 4 design readiness artifact 为 `docs/reviews/gateflow-phase-design-host-p4-codex-20260514.md`，controller
adjudication artifact 为 `docs/reviews/gateflow-phase-design-host-p4-controller-adjudication-20260514.md`。用户已确认：
新增 `HostApiErrorCode.UNSUPPORTED_OPERATION`，用于表达 public envelope 已冻结但完整语义由后续 phase 落地；
`cancel_session_runs` 在 Phase 4 实现 Phase 1-3 可闭环子集，即 queued / pre-dispatch `STARTING` cancel。
dispatching / active worker、`WAITING`、`RECOVERING` cancel 明确 deferred 到 Phase 5 / 7 / 11，不能让 Phase 4 子集成为最终语义。
design fix artifact 为 `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`。AgentMiMo 与 AgentDS 的
design fix re-review artifacts 分别为 `docs/reviews/gateflow-phase-design-re-review-host-p4-mimo-20260514.md`
与 `docs/reviews/gateflow-phase-design-re-review-host-p4-ds-20260514.md`；controller re-review adjudication artifact 为
`docs/reviews/gateflow-phase-design-re-review-host-p4-controller-adjudication-20260514.md`。两份 re-review 均为
accepted / no blocking finding。Phase 4 plan 已写入 `docs/host/phase4-public-api-command-path-plan.md`；plan review
artifacts 为 `docs/reviews/gateflow-plan-review-host-p4-public-api-command-path-mimo-20260514.md` 与
`docs/reviews/gateflow-plan-review-host-p4-public-api-command-path-ds-20260514.md`；controller plan review
adjudication artifact 为 `docs/reviews/gateflow-plan-review-host-p4-public-api-command-path-controller-adjudication-20260514.md`。
两份 plan review 均为 accepted / no blocking finding。Phase 4 accepted plan commit 为 `e004031`。
P4-S1 Public Types, Error Detail, Handle Options And Constants implementation artifact 为
`docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`。AgentMiMo 与 AgentDS 的 code review
artifacts 分别为 `docs/reviews/gateflow-code-review-host-p4-s1-public-types-mimo-20260514.md` 与
`docs/reviews/gateflow-code-review-host-p4-s1-public-types-ds-20260514.md`；controller adjudication artifact 为
`docs/reviews/gateflow-code-review-host-p4-s1-public-types-controller-adjudication-20260514.md`。两份 code review
均为 accepted / no blocking finding，controller 裁决 P4-S1 可进入 accepted slice commit。P4-S1 validation：
`pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q` 30 passed，
`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P4-S1 accepted slice commit 为
`b1e6eec`。
P4-S2 Session Public APIs And Snapshots implementation artifact 为
`docs/reviews/gateflow-implementation-host-p4-s2-session-public-api-20260514.md`。AgentMiMo 与 AgentDS 的 code
review artifacts 分别为 `docs/reviews/gateflow-code-review-host-p4-s2-session-public-api-mimo-20260514.md`
与 `docs/reviews/gateflow-code-review-host-p4-s2-session-public-api-ds-20260514.md`；controller adjudication artifact
为 `docs/reviews/gateflow-code-review-host-p4-s2-session-public-api-controller-adjudication-20260514.md`。两份 code
review 均为 accepted / no blocking finding。DS 的 metadata finding 已裁决为 accepted-as-doc-fixed：当前
`create_session` public facade 不持久化 metadata；若后续 phase 要承诺 metadata persistence，必须先回到设计与 plan。
P4-S2 validation：`pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q`
19 passed，`pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
8 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P4-S2 accepted slice commit 为
`190d905`。当前 gate 为 Phase 4 implementation，下一步进入 P4-S3 Run Admission, Follow-up Queue, Cancel Run And
Cancel Session Runs Subset implementation。
P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset implementation artifact 为
`docs/reviews/gateflow-implementation-host-p4-s3-run-followup-cancel-20260514.md`。首次 implementation 越界包含
P4-S4 `get_run` / `stream_run_events` 内容，已在 review 前完成 scope correction；最终 diff 不实现或导出 P4-S4
read/event stream 能力。AgentMiMo 与 AgentDS 的 code review artifacts 分别为
`docs/reviews/gateflow-code-review-host-p4-s3-run-followup-cancel-mimo-20260514.md` 与
`docs/reviews/gateflow-code-review-host-p4-s3-run-followup-cancel-ds-20260514.md`；controller adjudication artifact 为
`docs/reviews/gateflow-code-review-host-p4-s3-run-followup-cancel-controller-adjudication-20260514.md`。两份 code review
均为 accepted / no blocking finding。P4-S3 validation：`pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q`
37 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed；reviewer 额外验证
`pytest tests/host/test_package_exports.py -q` 5 passed 与 `pytest tests/host -q` 191 passed。当前 gate 为 P4-S3 accepted
slice commit；P4-S3 accepted slice commit 为 `af61fe9`。commit 后进入 P4-S4 Read APIs, Event Stream And Deferred Facade Behavior implementation。P4-S3 留下
明确后续 owner：public `submit_followup(queue)` 的默认 execution target 必须由后续 policy provider / execution
target resolution owner 替换；完整 session-scope cancel 必须继续由 Phase 5 / 7 / 11 分别补齐 dispatching /
active worker、`WAITING`、`RECOVERING`，不得把 Phase 4 queued / pre-dispatch `STARTING` 子集写成最终语义。
P4-S4 Read APIs, Event Stream And Deferred Facade Behavior implementation artifact 为
`docs/reviews/gateflow-implementation-host-p4-s4-read-stream-deferred-20260514.md`。AgentMiMo code review artifact 为
`docs/reviews/gateflow-code-review-host-p4-s4-read-stream-deferred-mimo-20260514.md`，其中提出 blocking finding：
`stream_run_events` 必须先校验 Run 存在，再校验 limit；AgentDS code review artifact 为
`docs/reviews/gateflow-code-review-host-p4-s4-read-stream-deferred-ds-20260514.md`，独立识别同一问题并提出 default
limit 测试鲁棒性 finding。Fix 已完成并通过 re-review；AgentMiMo 与 AgentDS 的 re-review artifacts 分别为
`docs/reviews/gateflow-code-re-review-host-p4-s4-read-stream-deferred-mimo-20260514.md` 与
`docs/reviews/gateflow-code-re-review-host-p4-s4-read-stream-deferred-ds-20260514.md`；controller re-review adjudication
artifact 为 `docs/reviews/gateflow-code-re-review-host-p4-s4-read-stream-deferred-controller-adjudication-20260514.md`。
两份 re-review 均确认 fixed / no blocking finding。P4-S4 validation：`pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q`
201 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P4-S4 accepted slice commit 为
`34b1207`。Phase 4 aggregate deepreview artifacts 为
`docs/reviews/gateflow-aggregate-deepreview-host-p4-public-api-command-path-mimo-20260514.md` 与
`docs/reviews/gateflow-aggregate-deepreview-host-p4-public-api-command-path-ds-20260514.md`；两份 review 均无
blocking finding。MiMo F-1 已通过
`docs/reviews/gateflow-aggregate-fix-host-p4-public-api-command-path-20260514.md` 修复，明确补强 `cancel_run` 对
Phase 5 / 7 / 11 deferred cancel owner 的提醒；aggregate re-review artifacts 为
`docs/reviews/gateflow-aggregate-re-review-host-p4-public-api-command-path-mimo-20260514.md` 与
`docs/reviews/gateflow-aggregate-re-review-host-p4-public-api-command-path-ds-20260514.md`；controller aggregate
re-review adjudication artifact 为
`docs/reviews/gateflow-aggregate-re-review-host-p4-public-api-command-path-controller-adjudication-20260514.md`。
两份 re-review 均确认 fixed / no blocking finding。Aggregate fix validation：`pytest tests/host -q` 201 passed，
`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。Phase 4 accepted deepreview commit 为
`f8e7538`。Phase 4 状态为 completed；ready-to-create-PR 已执行，PR 51
`https://github.com/noho/dayu-agent-r/pull/51` 已创建，title 为 `Host Phase 4 public API command path`，
base 为 `main`，head 为 `docs/host-phase4-control-state`，并已 merge 到 `main`，merge commit 为
`d9feaaf09b22bf099eb76b5d04f7c0438f67faf8`。PR readiness：所有 Phase 4 plan slice、code review、fix、re-review、aggregate deepreview、
aggregate fix、aggregate re-review 与 accepted local commit 均已完成并记录 artifact / commit hash；工作区检查为 clean；
剩余风险均已有后续 owner。后续 Phase 5 / 7 / 11 必须继续补齐
dispatching / active worker、`WAITING`、`RECOVERING` 的 per-run 与 session-scope cancel，不得把 Phase 4 queued /
pre-dispatch `STARTING` 子集写成最终语义。

当前 Host phase 工作入口为 Phase 5. RunInputBuilder / LocalProxy / EngineEvent Ingest。Phase 4 PR 51 merge 后的 public
API bug fix work unit 已完成：review artifact 为 `docs/reviews/code-review-20260514-2235.md`，fix artifact 为
`docs/reviews/gateflow-aggregate-fix-review-findings-20260514.md`，re-review artifact 为
`docs/reviews/gateflow-aggregate-re-review-review-findings-ds-20260514.md`，accepted fix commit 为 `fc7f55b`。本次
bug fix 已修复 admission-backed public facade 关闭 handle 后绕过 lifecycle guard，以及 command path / read path
terminal `RunSnapshot` 语义不一致；验证为
`pytest tests/host/test_command_handle.py tests/host/test_public_run_api.py` 16 passed，
`pyright dayu/host tests/host` 0 errors，`git diff --check` passed。Residual risk 已写入本文档追踪区并带 owner /
destination。Phase 5 进入前必须先做 phase discussion / design refinement，确认 RunInputBuilder typed provider、
lane acquire 后 recheck / dispatching / `ATTEMPT_RUNNING` transaction 边界，以及 EngineEvent terminal /
non-terminal / stream EOF 收口规则。

Phase 5 design discussion 已确认以下 design refinement 决策，并写入
`docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md` 与 `docs/host/design.md`：Engine 公共
`EngineEvent` 契约保持 Host-agnostic，`attempt_id + execution_id` 由 Host-owned LocalProxy / EngineWorker
envelope 绑定并在 Host ingest 边界校验；Phase 5 fresh schema / typed enum 必须扩展 dispatch record 状态到至少
`pending`、`waiting_for_lane`、`dispatching`、`cancelled`；Phase 5 只允许 no-tool 或最小 fake ToolExecutor 支撑本地
Engine 执行闭环，不实现 ToolRuntime governance、wait record 或 `resolve_wait`，`tool_awaiting` / `run_suspended`
不得在本 phase 创建 `WAITING` canonical truth。当前 gate 为 Phase 5 design re-review；需要 AgentMiMo 与 AgentDS
独立 review 后由 controller 裁决，blocking finding 修复并 re-review 通过后才进入 Phase 5 plan gate。
Phase 5 design re-review artifacts 为 `docs/reviews/gateflow-phase-design-re-review-host-p5-mimo-20260514.md` 与
`docs/reviews/gateflow-phase-design-re-review-host-p5-ds-20260514.md`。Controller adjudication artifact 为
`docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md`：AgentMiMo 无 blocking
finding；AgentDS F1 / F2 已裁决为 accepted-blocking，分别要求补齐本地执行异常 terminal closeout 判定表，以及
`dispatching + Attempt STARTING` 且 WorkerProxy 尚未 accepted 窗口内的 cancel / lane token owner 语义。
Design fix artifact 为 `docs/reviews/gateflow-phase-design-fix-host-p5-codex-20260514.md`；fix 已写回
`docs/host/design.md` §17 / §22。当前 gate 为 Phase 5 design fix re-review；F1 / F2 经 re-review 确认 fixed 后才可进入
Phase 5 plan gate。DS F3-F6 与 MiMo observation findings 已裁决为 plan-gate 检查项，不阻塞 design fix re-review。
Phase 5 design fix re-review 已由 AgentMiMo 与 AgentDS 完成，artifacts 分别为
`docs/reviews/gateflow-phase-design-fix-re-review-host-p5-mimo-20260514.md` 与
`docs/reviews/gateflow-phase-design-fix-re-review-host-p5-ds-20260514.md`；两者均确认 DS F1 / F2 fixed，且无新
blocking finding。Controller fix re-review adjudication artifact 为
`docs/reviews/gateflow-phase-design-fix-re-review-host-p5-controller-adjudication-20260514.md`。当前 gate 为 Phase 5
handoff implementation-ready plan；plan 必须把 DS F3-F6 与 MiMo observations 作为 plan review 检查项显式覆盖。
Phase 5 handoff implementation-ready plan 已写入
`docs/host/phase5-runinputbuilder-local-dispatch-plan.md`。Plan review artifacts 为
`docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-mimo-20260514.md` 与
`docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-ds-20260514.md`；两份 review 均无 blocking
finding。Controller plan review adjudication artifact 为
`docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-controller-adjudication-20260514.md`，已裁决
MiMo F001-F006 与 DS F-N1 / F-N2 为 plan-fix items。Plan fix artifact 为
`docs/reviews/gateflow-plan-fix-host-p5-runinputbuilder-local-dispatch-codex-20260514.md`。Plan fix re-review artifacts 为
`docs/reviews/gateflow-plan-re-review-host-p5-runinputbuilder-local-dispatch-mimo-20260514.md` 与
`docs/reviews/gateflow-plan-re-review-host-p5-runinputbuilder-local-dispatch-ds-20260514.md`；两者均确认所有 plan findings
fixed、无新 blocker。Controller plan re-review adjudication artifact 为
`docs/reviews/gateflow-plan-re-review-host-p5-runinputbuilder-local-dispatch-controller-adjudication-20260514.md`。Phase 5
accepted plan commit 为 `bacc4e7`。
P5-S1 Dispatch Schema And Transition Primitives 已完成 implementation、code review、accepted fix 与 code re-review。
Implementation artifact 为 `docs/reviews/gateflow-implementation-host-p5-s1-dispatch-schema-transitions-20260514.md`；code review
artifacts 为 `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md` 与
`docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md`。DS M1 / MiMo F2 已由
`docs/reviews/gateflow-fix-host-p5-s1-dispatch-schema-transitions-20260514.md` 修复，并由
`docs/reviews/gateflow-code-re-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md` 与
`docs/reviews/gateflow-code-re-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md` 确认 fixed / no new blocker。
Controller re-review adjudication artifact 为
`docs/reviews/gateflow-code-re-review-host-p5-s1-dispatch-schema-transitions-controller-adjudication-20260514.md`。P5-S1 validation：
`pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q`
34 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P5-S1 accepted slice commit 为
`8ad5f10`。P5-S1 residual risk：`ATTEMPT_RUNNING` payload 的 `local_worker_id`、`worker_accepted_at`、`lane_name`
与 `lane_claim_id` 由 P5-S3 LocalProxy / scheduler 接入时补齐。
P5-S2 RunInputBuilder And No-tool Provider Boundary 已完成 implementation 与 code review。Implementation artifact 为
`docs/reviews/gateflow-implementation-host-p5-s2-runinputbuilder-no-tool-provider-20260514.md`；code review artifacts 为
`docs/reviews/gateflow-code-review-host-p5-s2-runinputbuilder-no-tool-provider-mimo-20260514.md` 与
`docs/reviews/gateflow-code-review-host-p5-s2-runinputbuilder-no-tool-provider-ds-20260514.md`。两份 review 均无
blocking finding；Controller adjudication artifact 为
`docs/reviews/gateflow-code-review-host-p5-s2-runinputbuilder-no-tool-provider-controller-adjudication-20260514.md`。P5-S2 validation：
`pytest tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q`
11 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P5-S2 accepted slice commit 为
`411e01e`。P5-S2 residual risks：artifact-backed current prompt loading 未实现，当前 builder 要求 durable `display_text`；
Memory / compact / ToolRuntime real providers 分别由 Phase 9 / 10 / 6 接入；LocalProxy / scheduler 创建真实
`AttemptDispatchSnapshot` 属于 P5-S3。
P5-S3 Dispatch Scheduler, Lane And LocalProxy 已完成 implementation、code review、controller 裁决、README / tests README
同步与 accepted slice commit。Implementation artifact 为
`docs/reviews/gateflow-implementation-host-p5-s3-dispatch-scheduler-localproxy-20260514.md`；code review artifacts 为
`docs/reviews/gateflow-code-review-host-p5-s3-dispatch-scheduler-localproxy-mimo-20260515.md` 与
`docs/reviews/gateflow-code-review-host-p5-s3-dispatch-scheduler-localproxy-ds-20260514.md`；controller adjudication artifact 为
`docs/reviews/gateflow-code-review-host-p5-s3-dispatch-scheduler-localproxy-controller-adjudication-20260514.md`。两份 review
均无 blocking finding，Controller 裁决接受此 slice。P5-S3 validation：
`pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q`
27 passed；`pytest tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q` 6 passed；`python -m pyright dayu/host tests/host`
0 errors；`git diff --check` passed。P5-S3 accepted slice commit 为 `659a8e4`。P5-S3 residual risks：
`HostCommandHandleOptions.local_execution` 已 typed 且默认为 no-op，但 command-handle scheduler lifecycle wiring 尚未接入；
`_NeverCancelledToken` 仍是 P5-S3 占位，run-local cancellation token propagation 属于 P5-S5；scheduler close pending acquire /
active worker cancel 覆盖需随 P5-S5 或 lifecycle wiring scope 补齐；`_consume_worker_events` 当前只 drain / release lane，EngineEvent
ingest mapping 和 terminal closeout 属于 P5-S4。
P5-S4 EngineEvent Ingest Mapping And Terminal Closeout 已完成 implementation、code review、blocking fix、code re-review、
controller 裁决、README / tests README 同步与 accepted slice commit。Implementation artifact 为
`docs/reviews/gateflow-implementation-host-p5-s4-engine-event-ingest-20260515.md`；code review artifacts 为
`docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-mimo-20260515.md` 与
`docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-ds-20260515.md`。MiMo B1 已裁决为 accepted blocking：
duplicate terminal replay 必须重试 queue promotion wakeup；fix artifact 为
`docs/reviews/gateflow-fix-host-p5-s4-engine-event-ingest-20260515.md`。Code re-review artifacts 为
`docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-mimo-20260515.md` 与
`docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-ds-20260515.md`；两者均确认 B1 fixed 且无新 blocker。
Controller re-review adjudication artifact 为
`docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-controller-adjudication-20260515.md`。P5-S4 validation：
`pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py tests/host/test_weak_typing_guard.py -q`
11 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。P5-S4 accepted slice commit 为
`ab256d1`。P5-S4 controlled scope expansion：`dayu/host/durable/state.py` 新增 `cancel_cancelling_run_row` 与
`cancel_running_attempt_row`，虽不在原 P5-S4 allowed files，但经 MiMo、DS 与 controller 裁决为正确 durable state row CAS
ownership，优于在 `run_transition.py` 直接写 SQL。P5-S4 residual risks：preview、unsupported waiting、provider protocol
error、terminal-late 与 run_cancelled-without-active-cancel 负例可由后续测试 hardening 补齐。
P5-S5 Active Cancel And Session-scope Cancel 已完成 implementation、code review、accepted fix、code re-review、controller
裁决、README / tests README 同步与 accepted slice commit。Implementation artifact 为
`docs/reviews/gateflow-implementation-host-p5-s5-active-cancel-session-scope-20260515.md`；code review artifacts 为
`docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md` 与
`docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`。DS Finding 1 与 MiMo F2 已裁决为
accepted fix items：测试不得以非法裸 SQL 组合伪造 active worker，scheduler 连接 `EngineEventIngestor` 时必须提供实际
queue promotion wakeup port；fix artifact 为
`docs/reviews/gateflow-fix-host-p5-s5-active-cancel-session-scope-20260515.md`。Code re-review artifacts 为
`docs/reviews/gateflow-code-re-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md` 与
`docs/reviews/gateflow-code-re-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`；两者均 PASS 且无 blocking
finding。Controller re-review adjudication artifact 为
`docs/reviews/gateflow-code-re-review-host-p5-s5-active-cancel-session-scope-controller-adjudication-20260515.md`。P5-S5
validation：`pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`
22 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。P5-S5 accepted slice commit 为
`cdde31d`。P5-S5 residual risks：active cancel watchdog 仍未实现，worker 收到 cancel 后若长期不产出 terminal，Run 可能停留在
`CANCELLING`；session cancel replay 的 active target truth 仍锚定首个 active cancel event，当前单 active Run invariant 下非
blocking，若未来扩展多 active 语义必须重设 replay target truth；`cancel_run` 幂等重放不重传播 active cancel target，留给后续
lifecycle / recovery hardening；terminal 后 queue promotion wakeup 失败目前会浮出 worker event task，`finally` 仍负责 unregister /
close / release lane，后续可补 diagnostic suppression。
P5-S6 Integration, Docs And Validation Closeout 已完成 implementation、code review、controller 裁决、README / tests README
同步与 accepted slice commit。Implementation artifact 为
`docs/reviews/gateflow-implementation-host-p5-s6-integration-docs-validation-20260515.md`。P5-S6 controlled scope expansions：
`dayu/host/dispatch.py` 纳入本 slice，用于修复 scheduler worker stream clean EOF / stream exception 未调用
`EngineEventIngestor.close_clean_eof` / `close_worker_lost` 的真实生产缺口；`tests/host/test_admission_queue.py`、
`tests/host/test_durable_schema.py`、`tests/host/test_run_attempt_transitions.py` 纳入本 slice，用于把 Phase 3-era 断言迁移到
Phase 5 accepted truth，而不是在生产代码中保留兼容逻辑。Code review artifacts 为
`docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-mimo-20260515.md` 与
`docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-ds-20260515.md`；两者均 PASS 且无 blocking
finding。Controller adjudication artifact 为
`docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-controller-adjudication-20260515.md`。P5-S6 validation：
`pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_import_boundary.py -q` 14 passed；controlled expansion
targeted tests 4 passed；`pytest tests/host tests/runtime -q` 334 passed；`python -m pyright dayu/host tests/host` 0 errors；
`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` passed。P5-S6 accepted slice commit 为 `2a1e0db`。
P5-S6 residual risks：真实 provider runner 的外部网络 / provider API smoke 不属于 Phase 5 必测；active cancel watchdog 和
post-cancel timeout policy 归 Phase 11 lifecycle / recovery owner；ToolRuntime / `fetch_more` 归 Phase 6，`WAITING` /
`resolve_wait` 归 Phase 7，Memory 归 Phase 9，Context Governance 归 Phase 10，Recovery 归 Phase 11，Observer / Sink
归 Phase 13，RemoteProxy 归 Phase 14。
Phase 5 aggregate deepreview 已完成。Aggregate deepreview artifacts 为
`docs/reviews/gateflow-aggregate-deepreview-host-p5-local-dispatch-mimo-20260515.md` 与
`docs/reviews/gateflow-aggregate-deepreview-host-p5-local-dispatch-ds-20260515.md`；两份独立 review 均 PASS 且无
blocking finding。Controller aggregate adjudication artifact 为
`docs/reviews/gateflow-aggregate-deepreview-host-p5-local-dispatch-controller-adjudication-20260515.md`。Controller aggregate
validation baseline：`pytest tests/host tests/runtime -q` 334 passed；`python -m pyright dayu/host tests/host` 0 errors；
`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` passed。Phase 5 accepted aggregate review commit 为
`ae86a0a`。Phase 5 状态为 completed；ready-to-create-PR 已执行，PR 54
`https://github.com/noho/dayu-agent-r/pull/54` 已创建为 draft PR，title 为 `Host Phase 5 RunInputBuilder and local dispatch`，
head branch 为 `feat/host-phase5-local-dispatch`，base branch 为 `main`。PR readiness：所有 Phase 5 design refinement、
plan、6 个 implementation slices、code review、fix / re-review、aggregate deepreview、controller 裁决、accepted local commits、
branch push 与 draft PR create 均已完成并记录 artifact / commit hash / PR URL；工作区检查为 clean；剩余风险均已有后续
owner。后续 Phase 6 / 7 / 9 / 10 / 11 / 13 / 14 以及集成环境验证必须继续接收各自 deferred 项。
PR 54 手工 review gate 已打开。当前可见手工 review artifacts 为
`docs/reviews/pr-54-review-20260515-1056.md` 与 `docs/reviews/pr-54-review-20260515-1102.md`；用户说明共有 3 份手工
review，但 GitHub PR API / thread-aware fetch 与本地文件搜索当前只发现 2 份，第三份暂记为 missing evidence，后续出现时必须追加处理。
Controller PR review adjudication artifact 为 `docs/reviews/pr-54-review-controller-adjudication-20260515.md`。裁决结论：
PR 54 退出 ready 状态并进入 PR review fix gate；dispatch / lane / worker lifecycle、Engine ingest idempotency、
RunInputBuilder message semantics、Phase 5 supported integration tests 与 `HostCommandHandleOptions.local_execution` root-cause
decision 均为当前 gate 必须处理的 accepted items；schema v2 -> v3 旧库迁移按 fresh schema 约束 rejected；active cancel watchdog、
default worker hard cancel、retry / replay failure-context projection 等仍保留后续 owner。当前 gate 为 PR 54 review fix。
PR 54 review fix 已完成。Fix artifact 为
`docs/reviews/pr-54-review-fix-host-p5-local-dispatch-codex-20260515.md`，accepted fix commit 为 `310c812`。Re-review
artifacts 为 `docs/reviews/pr-54-review-fix-re-review-host-p5-local-dispatch-mimo-20260515.md` 与
`docs/reviews/pr-54-review-fix-re-review-host-p5-local-dispatch-ds-20260515.md`；两份 re-review 均 PASS 且无 blocking
finding。Controller re-review adjudication artifact 为
`docs/reviews/pr-54-review-fix-re-review-controller-adjudication-20260515.md`。Controller validation：`pytest tests/host/test_public_contracts.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py -q`
103 passed；`pytest tests/host tests/runtime -q` 356 passed；`python -m pyright dayu/host tests/host` 0 errors；
`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` passed。当前 PR 54 review gate 状态为 accepted；
PR 54 draft branch 已 push，current gate 为 PR 54 draft review-ready。剩余风险均有 owner：active cancel watchdog、pre-registration cancel
retry / watchdog 与 durable-unavailable recovery 归 Phase 11；ToolRuntime canonical tool facts 归 Phase 6；RunInputBuilder
读事务一致性与 recoverable RUN_FAILED diagnostic 顺序为后续 cleanup，不阻塞当前 PR。
PR 54 追加本地并行 review gate 已完成。新增 review artifacts 为
`docs/reviews/pr-54-review-20260515-1221.md` 与 `docs/reviews/pr-54-review-20260515-1224.md`；Controller additional
adjudication artifact 为 `docs/reviews/pr-54-review-additional-controller-adjudication-20260515.md`。裁决结论：A1-A10
accepted current fix，覆盖 `_consume_worker_events` pre-event 资源释放、preview event data 类型校验、RunInputBuilder
dispatchable 状态校验、`AttemptDispatchSnapshot` cancellation token 校验、active Run terminal CAS-lost 分类、terminal input
异常契约、scheduler close handle ownership、Default LocalProxy close 语义、LocalProxy 真实 Engine 边界错误路径测试，以及 Host
import boundary 禁止 `dayu.config`。Fix artifact 为
`docs/reviews/pr-54-review-additional-fix-host-p5-local-dispatch-codex-20260515.md`，accepted additional fix commit 为
`e302862`。Re-review artifacts 为
`docs/reviews/pr-54-review-additional-fix-re-review-host-p5-local-dispatch-mimo-20260515.md` 与
`docs/reviews/pr-54-review-additional-fix-re-review-host-p5-local-dispatch-ds-20260515.md`；两份 re-review 均 PASS 且无
blocking finding。Controller final adjudication artifact 为
`docs/reviews/pr-54-review-additional-fix-re-review-controller-adjudication-20260515.md`。Controller validation：
`pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_run_attempt_transitions.py -q`
107 passed；`pytest tests/host tests/runtime -q` 375 passed；`python -m pyright dayu/ tests/ utils/` 0 errors；
`git diff --check` passed。当前 PR 54 additional review gate 状态为 accepted；PR 54 draft branch 已 push，current gate 为
PR 54 draft review-ready。剩余风险均有 owner：active cancel watchdog / post-cancel timeout 与 multi-scheduler cancel port 归 Phase 11；
RemoteProxy 语义归 Phase 14；scheduler 并发 lane 竞争测试、`_drain_loop` 可观测性、RunInputBuilder optimistic TOCTOU 与
`_consume_worker_events` cleanup helper 防御性强化归 P9.5 Pre-P10 Cross-Repository Hardening PR，不阻塞当前 PR。
PR 54 全仓并行 review gate 已完成。Full-repo review artifacts 为
`docs/reviews/repo-review-20260515-1338.md` 与 `docs/reviews/repo-review-20260515-1346.md`；Controller adjudication artifact 为
`docs/reviews/repo-review-controller-adjudication-20260515.md`。裁决结论：只接受当前 PR 可安全修复且不重排 phase 边界的
A1-A10，包括 runtime lane shielded cancellation / release 一致性、dispatch drain loop empty / sleep wakeup race、
`BatchToolExecutionRequest` duplicate `tool_call_id` 拒绝、`is_retriable` `assert_never` 穷尽守卫、`ToolCancelledOutcome.hint`
空白拒绝、`wait_for_or_cancel` docstring 修正、`_HostCancellationToken` 显式实现 `CancellationToken` Protocol、Host EventLog
payload helper 抽取、Host public validation helper 抽取与 `run_input.py` dead import cleanup。Fix artifact 为
`docs/reviews/repo-review-fix-host-p5-full-repo-codex-20260515.md`，accepted full-repo fix commit 为 `4527585`。
Re-review artifacts 为 `docs/reviews/repo-review-fix-re-review-host-p5-full-repo-mimo-20260515.md` 与
`docs/reviews/repo-review-fix-re-review-host-p5-full-repo-ds-20260515.md`；两份 re-review 均 PASS 且无 blocking finding。
Controller final adjudication artifact 为 `docs/reviews/repo-review-fix-re-review-controller-adjudication-20260515.md`。
Controller validation：受影响测试 126 passed；`pytest tests/host tests/runtime tests/contracts tests/engine -q` 741 passed；
`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` passed。当前 full-repo review gate 状态为 accepted；
PR 54 draft branch 已 push，current gate 为 PR 54 draft review-ready。剩余风险均有 owner：runtime lane repeated outer cancellation
与 untracked release failure、idle scheduler sleeping task、Engine runner injection、God module/class cleanup 与 broader test
hardening 中不依赖 P10+ owner 的部分归 P9.5 Pre-P10 Cross-Repository Hardening PR；active cancel watchdog 归 Phase 11；
RemoteProxy 归 Phase 14。
P5 design conformance review gate 已完成。用户要求 AgentMiMo、AgentDS、AgentCodex 三路同时审查 P5 实现是否偏离
`docs/host/design.md`、边界是否清晰、生产接线是否正确以及后续 phase 接线是否按设计预留。Review artifacts 为
`docs/reviews/p5-design-conformance-review-mimo-20260515.md`、
`docs/reviews/p5-design-conformance-review-ds-20260515.md` 与
`docs/reviews/p5-design-conformance-review-codex-20260515.md`；三路 verdict 均 PASS，blocking design deviations 为 0。
Controller adjudication artifact 为
`docs/reviews/p5-design-conformance-review-controller-adjudication-20260515.md`。Controller 裁决：P5 design conformance gate
通过；Host 强治理真源、LocalProxy envelope、EngineEvent boundary、dispatch record 非 owner truth、RunInputBuilder typed provider
boundary、runtime 层中立、生产 scheduler / lane / LocalProxy / ingest / queue promotion 接线与后续 phase stub/no-op/fail-fast
路径均符合设计。非阻断 hardening items：`accept_worker_running_in_transaction` 这条非生产 durable helper 的 `ATTEMPT_RUNNING`
payload diagnostics 弱于 scheduler 生产路径，以及 `mark_dispatching_after_lane_row` 底层 helper 能力宽于生产 scheduler 路径，
owner 均为 P9.5 Pre-P10 Cross-Repository Hardening PR。其它 residual risk 维持既有 owner：terminal promotion
wakeup failure 归 Phase 11，active cancel watchdog 归 Phase 11，RemoteProxy 归 Phase 14；不涉及 lifecycle / recovery owner 的
composition cleanup 归 P9.5 Pre-P10 Cross-Repository Hardening PR。本 gate 不要求当前 blocker fix，PR 54 仍为 draft review-ready。

P1-P5 corrected design conformance review gate 已完成。用户澄清上一轮应审查的是“实现到 P5 后，P1-P5 当前全部代码
snapshot 是否偏离设计”，因此上一段 P5-only review 只作为子集证据，不作为 P1-P5 全量结论。Corrected review artifacts 为
`docs/reviews/p1-p5-design-conformance-review-mimo-20260515.md`、
`docs/reviews/p1-p5-design-conformance-review-ds-20260515.md` 与
`docs/reviews/p1-p5-design-conformance-review-codex-20260515.md`；三路 verdict 均 PASS，blocking design deviation 均为 0。
Controller adjudication artifact 为
`docs/reviews/p1-p5-design-conformance-review-controller-adjudication-20260515.md`。Controller 裁决：P1 public contract /
runtime boundary、P2 durable store / EventLog、P3 session / run / attempt / admission、P4 public API command path、P5
RunInputBuilder / local dispatch / local proxy / Engine ingest / cancel、跨 phase 分层、生产接线与后续 phase 预留均未发现
blocking 设计偏离；PR 54 不需要进入新的 fix gate，仍为 draft review-ready。Non-blocking hardening / cleanup 均已有 owner：
`accept_worker_running_in_transaction` 诊断 payload 弱于 scheduler 生产路径与
`mark_dispatching_after_lane_row` 底层 helper 能力宽于生产 scheduler 路径归 P9.5 Pre-P10 Cross-Repository Hardening PR；
active worker registry composition root 边界已由 P1-P7 design-goals fix 关闭；compact
artifact message slot 与 plan 摘要顺序不完全一致归 Phase 10 / RunInputBuilder documentation cleanup。其它 residual risk 维持既有
owner：terminal promotion wakeup failure 归 Phase 11，active cancel watchdog / stuck `CANCELLING` /
orphan recovery 归 Phase 11，RemoteProxy 归 Phase 14，ToolRuntime / `fetch_more` 归 Phase 6，WAITING / `resolve_wait` 归
Phase 7，Memory / Context Governance / compact artifact 分别归 Phase 9 / Phase 10。

历史状态：Phase 1 公共契约与 runtime 基础设施已完成并 merge；Phase 2 Durable Store / EventLog / Payload Foundation 已完成 plan、3 个 implementation slices、aggregate deepreview、aggregate fix、aggregate re-review 与 accepted deepreview commit，本 phase 状态为 completed。Phase 1 design refinement 已写入 `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`，controller-accepted design fix 已写入 `docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`。用户反馈后的 design fixes 已写入 `docs/reviews/gateflow-phase-design-user-feedback-fix-host-p1-codex-20260513.md` 与 `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`。AgentMiMo 与 AgentDS 的 phase design re-review 均确认 accepted findings 已修复且 new blocker 为 0；round2 re-review 进一步确认 lane 已改为 cross-process runtime capacity guard，Phase Map 已重排为 P12 ToolsDiscovery / ScenePrepare、P13 Audit / Tool Trace / Outbox、P14 RemoteProxy、P15 Retention / Purge。Phase 1 plan 已写入 `docs/host/phase1-public-contract-runtime-plan.md`；plan review、controller adjudication、plan fix 与 plan re-review artifacts 已写入 `docs/reviews/`。AgentMiMo 与 AgentDS 的 plan re-review 均确认 finding 数量为 0、blocking finding 数量为 0。用户已确认 Phase 1 plan；accepted plan commit 为 `34b1b41`。Phase 1 Slice 1 accepted slice commit 为 `66d8dc3`，Slice 2 accepted slice commit 为 `27e0d8b`，Slice 3 accepted slice commit 为 `e23e3e4`，Slice 4 accepted slice commit 为 `0393a22`。

Phase 1 implementation 收口验证：

- `source .venv/bin/activate && pytest tests/host tests/runtime -q`：102 passed。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。

Phase 1 plan gate 通过证据：`docs/host/design.md`、`docs/host/implementation-control.md` 与 `dayu/README.md` 对 Host public typing、`ToolBundle` construction input、cross-process `dayu.runtime.lane`、`dayu.runtime.filelock`、ToolsDiscovery / ScenePrepare 的 Phase 12 destination 保持一致；AgentMiMo 与 AgentDS 的 Phase 1 design review accepted findings 已有 fix artifact 与 re-review artifact 记录；用户已确认进入 phase plan；`docs/host/phase1-public-contract-runtime-plan.md` 已生成；AgentMiMo 与 AgentDS 已完成 plan review、fix 后 re-review 并确认无剩余 finding。

Phase 2 design refinement 状态：`docs/reviews/gateflow-phase-design-host-p2-codex-20260514.md` 提出的 5 个 blocking questions 已按 controller-accepted A 决策写回设计真源与本文档，fix artifact 为 `docs/reviews/gateflow-phase-design-fix-host-p2-codex-20260514.md`。AgentMiMo 与 AgentDS 的 design fix re-review artifacts 分别为 `docs/reviews/gateflow-phase-design-re-review-host-p2-mimo-20260514.md` 与 `docs/reviews/gateflow-phase-design-re-review-host-p2-ds-20260514.md`；controller adjudication artifact 为 `docs/reviews/gateflow-phase-design-re-review-host-p2-controller-adjudication-20260514.md`。Phase 2 plan 已写入 `docs/host/phase2-durable-store-eventlog-plan.md`；plan review artifacts 为 `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-mimo-20260514.md` 与 `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`，plan fix artifact 为 `docs/reviews/gateflow-plan-fix-host-p2-durable-store-eventlog-codex-20260514.md`。AgentMiMo 与 AgentDS 的 plan re-review artifacts 分别为 `docs/reviews/gateflow-plan-re-review-host-p2-durable-store-eventlog-mimo-20260514.md` 与 `docs/reviews/gateflow-plan-re-review-host-p2-durable-store-eventlog-ds-20260514.md`；controller adjudication artifact 为 `docs/reviews/gateflow-plan-re-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`。Phase 2 accepted plan commit 为 `83c6ad6`。Slice 1 implementation artifact 为 `docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`，controller implementation decision artifact 为 `docs/reviews/gateflow-implementation-decision-host-p2-s1-sqlite-payload-table-name-20260514.md`。AgentMiMo 与 AgentDS 的 Slice 1 code review artifacts 分别为 `docs/reviews/gateflow-code-review-host-p2-s1-durable-schema-transaction-mimo-20260514.md` 与 `docs/reviews/gateflow-code-review-host-p2-s1-durable-schema-transaction-ds-20260514.md`；controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p2-s1-durable-schema-transaction-controller-adjudication-20260514.md`。Slice 1 validation：durable schema / transaction tests 15 passed，Host export / import boundary / weak typing guard tests 7 passed，`python -m pyright dayu/host tests/host` 0 errors；accepted Slice 1 commit 为 `be5dbdc`。Slice 2 implementation artifact 为 `docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`；code review artifacts 为 `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md` 与 `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`；controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-controller-adjudication-20260514.md`；fix artifact 为 `docs/reviews/gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md`；code re-review artifacts 为 `docs/reviews/gateflow-code-re-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md` 与 `docs/reviews/gateflow-code-re-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p2-s2-eventlog-idempotency-controller-adjudication-20260514.md`。Slice 2 validation：EventLog / Idempotency tests 19 passed，多进程 EventLog smoke 1 passed，durable schema / transaction tests 15 passed，Host export / import boundary / weak typing guard tests 7 passed，`python -m pyright dayu/host tests/host` 0 errors。Phase 2 accepted Slice 2 commit 已创建；具体 hash 由当前 git commit 记录。Slice 3 implementation artifact 为 `docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`；code review artifacts 为 `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md` 与 `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`；controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-controller-adjudication-20260514.md`；fix artifact 为 `docs/reviews/gateflow-fix-host-p2-s3-payload-artifact-liveness-20260514.md`；code re-review artifacts 为 `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md` 与 `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-controller-adjudication-20260514.md`。Slice 3 validation：payload / artifact / liveness tests 27 passed，EventLog / idempotency / multiprocess tests 20 passed，Host tests 94 passed，`python -m pyright dayu/host tests/host` 0 errors。Phase 2 accepted Slice 3 commit 已创建；具体 hash 由当前 git commit 记录。Aggregate deepreview artifacts 为 `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md` 与 `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md`；controller aggregate adjudication artifact 为 `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`；aggregate fix artifact 为 `docs/reviews/gateflow-aggregate-fix-host-p2-durable-store-eventlog-20260514.md`；aggregate re-review artifacts 为 `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-mimo-20260514.md` 与 `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-ds-20260514.md`；controller aggregate re-review adjudication artifact 为 `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`。Aggregate fix validation：Host tests 101 passed，runtime import/lane/filelock tests 29 passed，`python -m pyright dayu/host tests/host` 0 errors，`python -m pyright dayu/ tests/ utils/` 0 errors。Phase 2 accepted deepreview commit 已创建；具体 hash 由当前 git commit 记录。Phase 2 状态为 completed，后续工作入口为 Phase 3 design discussion / plan gate。

Phase 3 design refinement 状态：`docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md` 提出的 BQ1 / BQ2 / BQ3 已由 controller 在 `docs/reviews/gateflow-phase-design-host-p3-controller-adjudication-20260514.md` 中裁决为 accepted，并已获得用户确认。Design fix artifact 为 `docs/reviews/gateflow-phase-design-fix-host-p3-codex-20260514.md`。AgentMiMo design fix re-review artifact 为 `docs/reviews/gateflow-phase-design-re-review-host-p3-mimo-20260514.md`；其提出的 F1 已通过 `docs/reviews/gateflow-phase-design-additional-fix-host-p3-f1-codex-20260514.md` 修复，并由 `docs/reviews/gateflow-phase-design-additional-re-review-host-p3-f1-mimo-20260514.md` 确认 fixed。Controller design re-review adjudication artifact 为 `docs/reviews/gateflow-phase-design-re-review-host-p3-controller-adjudication-20260514.md`。

Phase 3 plan gate 状态：Phase 3 plan 已写入 `docs/host/phase3-session-run-attempt-admission-plan.md`。AgentMiMo plan review artifact 为 `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`。Plan fix artifact 为 `docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`。AgentMiMo plan re-review artifact 为 `docs/reviews/gateflow-plan-re-review-host-p3-session-run-attempt-admission-mimo-20260514.md`；controller re-review adjudication artifact 为 `docs/reviews/gateflow-plan-re-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`。F1 / F2 / F3 均已确认 fixed，blocking finding 为 0。当前 gate 为 accepted plan commit；commit 后进入 Phase 3 implementation gate。

Phase 3 Slice P3-S1 状态：P3-S1 Schema And Row Codecs implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s1-schema-row-codecs-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-controller-adjudication-20260514.md`。Accepted finding P3S1-MIMO-001 已通过 `docs/reviews/gateflow-fix-host-p3-s1-schema-row-codecs-20260514.md` 修复，并由 `docs/reviews/gateflow-code-re-review-host-p3-s1-schema-row-codecs-mimo-20260514.md` 确认 fixed；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p3-s1-schema-row-codecs-controller-adjudication-20260514.md`。P3S1-MIMO-002 已裁决为 rejected-with-reason。当前 gate 为 P3-S1 accepted slice commit；commit 后进入 P3-S2 Session And Slot Lifecycle implementation。

Phase 3 Slice P3-S2 状态：P3-S2 Session And Slot Lifecycle implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s2-session-lifecycle-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s2-session-lifecycle-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s2-session-lifecycle-controller-adjudication-20260514.md`。F001 与 F002 已裁决为 rejected-with-reason；F003 已通过 `docs/reviews/gateflow-fix-host-p3-s2-session-lifecycle-20260514.md` 修复，并由 `docs/reviews/gateflow-code-re-review-host-p3-s2-session-lifecycle-mimo-20260514.md` 确认 fixed；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p3-s2-session-lifecycle-controller-adjudication-20260514.md`。当前 gate 为 P3-S2 accepted slice commit；commit 后进入 P3-S3 Run And Attempt Transition Primitives implementation。

Phase 3 Slice P3-S3 状态：P3-S3 Run / Attempt Transition Primitives implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s3-run-attempt-transitions-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md`。Controller code review adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`，其中新增并接受 blocking finding P3S3-C-001。P3S3-C-001 已通过 `docs/reviews/gateflow-fix-host-p3-s3-run-attempt-transitions-20260514.md` 修复，并由 `docs/reviews/gateflow-code-re-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md` 确认 fixed；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`。当前 gate 为 P3-S3 accepted slice commit；commit 后进入 P3-S4 Admission And Queue Promotion implementation。

Phase 3 Slice P3-S4 状态：P3-S4 Admission And Queue Promotion implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s4-admission-queue-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`。Accepted finding P3S4-C-001 已通过 `docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md` 修复，并由 `docs/reviews/gateflow-code-re-review-host-p3-s4-admission-queue-mimo-20260514.md` 确认 fixed；controller re-review adjudication artifact 为 `docs/reviews/gateflow-code-re-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`。当前 gate 为 P3-S4 accepted slice commit；commit 后进入 P3-S5 Cancel And Terminal Closeout Orchestration implementation。

Phase 3 Slice P3-S5 状态：P3-S5 Cancel And Terminal Closeout Orchestration implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s5-cancel-terminal-closeout-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s5-cancel-terminal-closeout-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s5-cancel-terminal-closeout-controller-adjudication-20260514.md`。Review 无 blocking finding，info observation F1 已裁决为 accepted-as-non-issue，F2 deferred 到 Phase 5 / later dispatching cancel owner。当前 gate 为 P3-S5 accepted slice commit；commit 后进入 P3-S6 Multiprocess Tests And Documentation Sync。

Phase 3 Slice P3-S6 状态：P3-S6 Multiprocess Tests And Documentation Sync implementation artifact 为 `docs/reviews/gateflow-implementation-host-p3-s6-multiprocess-docs-20260514.md`。AgentMiMo code review artifact 为 `docs/reviews/gateflow-code-review-host-p3-s6-multiprocess-docs-mimo-20260514.md`，controller adjudication artifact 为 `docs/reviews/gateflow-code-review-host-p3-s6-multiprocess-docs-controller-adjudication-20260514.md`。Review 无 blocking finding。NB-1 已裁决为 rejected-as-current-slice-action；NB-2 已裁决为 accepted-as-deferred-risk，并转交 Phase 4 public API owner 覆盖 API 级 queued cancel / promotion race。P3-S6 validation：`pytest tests/host/test_admission_multiprocess.py tests/host -q` 157 passed，`python -m pyright dayu/host tests/host` 0 errors，`git diff --check` passed。P3-S6 accepted slice commit 为 `49fc1d5`。

Phase 3 aggregate deepreview 状态：Aggregate deepreview 已由 AgentMiMo 与 AgentDS 同时执行，artifacts 分别为 `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-mimo-20260514.md` 与 `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-ds-20260514.md`。AgentMiMo 无 blocking finding。AgentDS 的 N-1 / N-2 已由 controller 接受为 aggregate fix，fix artifact 为 `docs/reviews/gateflow-aggregate-fix-host-p3-session-run-attempt-admission-20260514.md`。Aggregate re-review 已由 AgentMiMo 与 AgentDS 同时执行，artifacts 分别为 `docs/reviews/gateflow-aggregate-re-review-host-p3-session-run-attempt-admission-mimo-20260514.md` 与 `docs/reviews/gateflow-aggregate-re-review-host-p3-session-run-attempt-admission-ds-20260514.md`；两者均确认 fixed / no blocking findings。Controller aggregate adjudication artifact 为 `docs/reviews/gateflow-aggregate-re-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`。Phase 3 已完成 ready-to-create-PR、PR create 与 PR merge，PR 50 merge commit 为 `d9c2ca9dd0d9b88b99dae96d972457a493f98f60`。所有追踪项均已带明确 owner；后续工作入口为 Phase 4 design discussion / design refinement。
