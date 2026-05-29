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
- phase plan、implementation 或 fix 不得把 assistant final answer 自动升级为 `evidence_backed_fact`。
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

当前 work unit：Phase 15 Retention / Purge / Production Hardening。
当前状态：Phase 15 handoff implementation-ready plan 已生成，plan review / fix / re-review 已完成且 re-review 为 PASS；P15-S1
Purge Tombstone Schema And Durable Primitives、P15-S2 Delete Matrix Transaction Helper 与 P15-S3 Public Command Wiring And
Read-after-purge Semantics 均已通过 code review / controller validation，进入 accepted slice commit。
Accepted plan commit 为 `5fae495`；Accepted S1 commit 为 `f607655`；Accepted S2 commit 为 `dac3a85`。
Plan artifact 为 `docs/host/phase15-retention-purge-production-hardening-plan.md`。P15-S3 artifacts 为
`docs/reviews/phase15-s3-implementation-codex-20260529.md`、
`docs/reviews/phase15-s3-code-review-mimo-20260529.md`、
`docs/reviews/phase15-s3-code-review-ds-20260529.md` 与
`docs/reviews/phase15-s3-code-review-controller-adjudication-20260529.md`。Phase 13 Audit / Tool Trace / Outbox
Projections 已完成，最终 full-repo review re-review 为 PASS；过程证据、review artifacts、accepted commits 与 PR 69 记录见
`历史记录` 和 `docs/reviews/`。Phase 14 RemoteProxy / RemoteStub 暂不实现，已 deferred 到 GitHub Issue #73。
当前 gate：Phase 15 implementation Slice P15-S4。
下一步：派发 implementation specialist 实现 Slice P15-S4 Audit JSONL Retention And Tombstone Audit Record。P15 不以 Phase 14
completion 为进入前置；任何 remote-dependent smoke / hardening 项必须排除、改写为 local / multiprocess / recovery coverage，或继续归
Issue #73。

## Phase Map

Phase 按依赖关系推进：先实现被其它阶段依赖的公共契约、runtime 基础能力、durable store、EventLog 与状态机，再连接执行路径、工具治理、projection core、memory、context governance、ordinary local multi-turn public contract freeze 与 recovery。Audit、Tool Trace、Outbox 是独立 projection sinks，后置到核心治理路径稳定之后实现。Phase 14 RemoteProxy / RemoteStub 暂不实现并由 Issue #73 追踪，当前推进顺序从已完成的 Phase 13 直接进入 Phase 15。Phase 0 是 Engine cleanup 前置 work unit，只阻塞 Phase 10 Context Governance，不阻塞 Phase 1-9。每个 phase 开始时仍必须先和用户讨论并细化对应 `docs/host/design.md` 章节，再生成 handoff implementation-ready plan。

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
- `submit_followup(queue)` 使用 `accepted_run_id` + `accepted_run_status` 表达 accepted follow-up 结果；P10 后无 active / start-blocking Run 时返回新 `ACCEPTED` Run，不能把 accepted / running Run 塞进 `queued_run_id`。
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
- 不把 final_answer 自动升级为 evidence-backed fact。
- 不让 memory projection 写 EventLog。

关键设计问题：
- 已确认 memory view 分为 `pinned_state`、`evidence_backed_facts`、`working_assumptions`、`conversation_continuity` 四类；不得把
  tool-verified fact、assistant conclusion、用户说法和 episode summary 混成无结构字符串列表。
- 已确认 evidence-backed fact 只接受工具事实，并必须保留 fact summary、producer / tool name、`event_id` / `event_sequence`、
  tool result ref、digest / source ref，以及可选 evidence anchor / opaque subject refs。
- 已确认 RunInputBuilder memory 注入顺序为：用户目标与约束、已确认主体和口径、tool-verified facts、open questions /
  working assumptions、recent raw turns、episode summaries。
- 已确认预算策略必须克制：pinned / evidence-backed facts 不参与 history pool 竞争但有结构化尺寸上限与诊断；recent raw turns floor
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
- 实现 Host proactive context budget governance、Host-owned compactor port、compact event、compact artifact、P9 memory projection 对 accepted compact output 的消费、reactive Engine overflow recovery 与 RunInputBuilder compact provider。
- P10 完成后，多轮会话主体必须可工作：Host 能在预算压力下生成 accepted episode summary / pinned state patch candidate，经 canonical compact event / artifact 和 P9 memory projection 进入后续 RunInputBuilder memory messages；recent raw turns、older raw turns、episode summaries、pinned state 与 verified facts 必须共同形成可解释的多轮记忆闭环。

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
- 已确认 conservative estimator、provider-aware configured limits、safety margin 与 compact policy 的第一版默认值。

范围：
- 允许修改：Context Governance orchestrator、budget estimator、Host-owned compactor typed port、compaction scene adapter / fake compactor、compact artifact store、compact canonical events、P9 memory projection 对 compact canonical facts 的消费、RunInputBuilder CompactArtifactProvider、reactive overflow recovery path、production composition wiring。
- 禁止修改：Engine proactive compaction、memory snapshot / memory table direct write、audit / trace projection direct write。

不做：
- 不实现 provider-specific tokenizer adapter。
- 不实现长期 memory retrieval。
- 不做无限 compact retry。
- 不实现 public memory edit / reset / forget API。
- 不实现 Phase 11 startup crash recovery、positive orphan proof 或通用 `RECOVERING` recovery scan。
- 不实现 Phase 13 Audit / Tool Trace / Outbox sinks；P10 只记录可供后续 sinks 消费的 typed refs / diagnostics。

关键设计问题：
- 已确认多轮会话主体闭环的数据来源：按模型窗口触发 compaction、Host-owned compactor 输出 episode summary candidate 与 pinned state patch candidate、recent raw turns floor、older raw turns 与 episode summaries 共用 history pool、pinned state 独立于 history pool，并通过 canonical compact event / artifact + P9 memory projection 消费落到当前架构。
- 已确认 proactive 与 reactive 两条路径的 transaction / state transition。
- 已确认 compactor output schema：episode summary candidate、pinned state patch candidate、preserved fact refs、dropped / summarized ranges、quality check result 与 budget after compact。
- 已确认 accepted compact output 作为 canonical fact 被 P9 memory projection 消费，并明确 P10 不直接写 memory snapshot。
- 已确认 compact failure 的 Run terminal / recoverable policy。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: context budget policy / estimator / usage observation / threshold decisions。
- Slice 2: compactor typed contracts, fake compactor, quality check and compact artifact store。
- Slice 3: compact canonical events and P9 memory projection consumption of accepted episode summary / pinned state patch candidate。
- Slice 4: proactive pre-dispatch Context Governance orchestration and RunInputBuilder compact provider rebuild path。
- Slice 5: reactive Engine overflow -> validated compact -> `RECOVERING` -> new Attempt path。
- Slice 6: production composition wiring, multi-turn integration validation and docs sync。

验证要求：
- unit tests: threshold decisions、compactor output validation、quality check rejection、compact event payload validation、P9 projection materializes accepted episode summary / pinned state patch without direct memory writes、failure policy。
- integration tests: proactive compact before dispatch produces later Run memory messages with pinned state / episode summary; recent raw turns floor and older raw turns / episode summaries share the history pool; reactive overflow validates attempt / execution id and recovers with a new Attempt; compact failure fails Run without `LOST`。
- pyright: context governance modules 通过。
- docs: Host / Engine boundary docs 按触发规则同步。

退出条件：
- Host 能在 dispatch 前主动 compact，并能把 Engine overflow 当作 reactive fallback 恢复，不让 Engine 管理 Host context budget。
- 多轮会话主体闭环可验证：用户约束 / 目标、tool-verified facts、recent raw turns、older raw turns 与 accepted episode summaries 能在后续 Run 的 `AgentRunRequest.messages` 中按 P9/P10 policy 稳定出现；episode summary 与 pinned state patch 的来源可追溯到 compact canonical event / artifact；assistant final answer 仍不会自动成为 verified fact。
- P10 不留下无 owner 的“stable layer / history pool 只有结构没有来源”缺口；若 implementation 发现某项来源必须依赖长期 retrieval、public memory edit/reset、Phase 11 recovery、Phase 13 trace sink 或 Phase 15 retention，必须重新归属到对应后续 phase 并说明不阻塞多轮会话主体闭环的理由。

后续依赖：
- 后续 phase 可依赖的稳定契约：compact events、compact artifacts、context budget policy view、accepted episode summary / pinned state patch projection contract。
- 需要追踪到后续 phase 的事项：provider-specific tokenizer adapter、长期 retrieval、public memory edit / reset / forget API、Audit / Tool Trace sinks 是后续能力。

### Phase 10.5. Ordinary Local Multi-turn Public Contract Freeze

目标：
- 冻结普通本地多轮会话的 Host public interface / contract，查漏补缺生产接线和组件，确保后续真实生产系统 Service 调用 Host public interface / contract 即可完成多轮会话闭环。
- P10.5 自身必须把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实；真实 CLI / web / GUI 在 P11-P15 实施完毕后会通过 Service 使用 P10.5 冻结的 Host public interface / contract 接入，不能等到真实入口接入时再补一条新接线。后续 P11-P15 仅扩展 Host 能力，不改变普通多轮会话的生产接线。
- Public contract 面向 Codex / Claude Code 类调用方：打开 Host、取得 / 新建 / 读取 Session、提交 prompt、读取 / 订阅 Session 事件、在 HostEventStream 中观察 terminal final answer、关闭 Host；不得要求上层理解 scheduler、runner、tooling、memory catch-up、wakeup 或 `HostLocalRuntime` 装配细节。
- P10.5 冻结 async-only Host opener / handle；Service-facing 打开入口名称固定为 `open_host(options)`。不提供 Host 层同步 wrapper，不冻结同步 close / cancel / timeout / stream iteration 语义。CLI 或同步上层如需使用 Host，由 Service / CLI adapter 包装 async contract。
- `open_host(options)` 的 options 只承载打开 Host、驱动 Host -> Engine 本地运行所需的 construction-time 参数；每次 Run 会变化的参数不得塞进 options，必须进入对应 public request。
- Session acquisition 和 Run interaction 分离：`ensure_session(...)` / `create_session(...)` / `get_session(...)` 只负责取得 `SessionSnapshot`；拿到 `session_id` 后，第一条 prompt 与后续普通 prompt 都统一使用 `submit_followup(queue)`。`start_run(...)` 从 public namespace 移除，Host 内部 admission primitive 固定命名为 `_start_run(...)`。
- `create_host_command_handle(...)` 降为 Host 内部 / 低层测试 composition primitive，不作为 Service-facing 打开入口；`HostLocalRuntime` 与 `HostLocalExecutionOptions` 改为内部 contract / implementation type；scheduler / wakeup / dispatch control API 不暴露给 Service。
- Command mutation 与 event observation 分离：`submit_followup(...)`、`submit_followup(steer)`、`retry_run(...)`、`replay_run(...)` 不要求和 event loop 顺序绑定。设计已确定聊天主入口是 session-level live Host event stream；run-level EventLog 补读 / `HostEventView` 改为内部 diagnostic / detail / debug / drill-down 契约，不进入普通 Service-facing public contract。拿到 / attach Session 前发生的 terminal/final answer 通知由 Outbox 路径承接。Service 拿到 `session_id` 后，用客户端保存的 `last_seen_terminal_event_sequence` / `seen_terminal_event_ids` 去 Outbox 读离线 terminal/final answer 增量，同时或随后打开 `watch_session_events(session_id)`，并用 `terminal_event_id` / `event_sequence` / `run_id` 去重。
- 补齐 `submit_followup(steer)`、`retry_run(...)`、`replay_run(...)` 的本地 public 语义。当前它们只是 stable unsupported envelope；P10.5 后普通 agent session 的控制输入、失败重试和结构修复不应再没有 owner。
- memory catch-up 与 context overflow compact 属于 P10.5 查漏补缺范围。普通 Service 不能为了完成多轮闭环而手工装配 memory projection、compact artifact store、scheduler pre-start governance 或 dispatch internals；Host public opener / handle 必须提供明确 construction-time contract 来接收 / 配置 compactor、compactor execution baseline、budget policy、artifact root 和 memory catch-up。Compactor 的模型、温度、max tokens、provider 选择或 compact scene policy 是独立于 ordinary Run execution override 的 opener baseline。
- 明确薄 Service 只是最小 consumer 证明样例，不是 Host 特殊接口类型；P10.5 不得把测试专用或薄 Service 专用入口未经讨论变成 Host contract。
- 用 smoke 验证 public contract 冻结目标成立：no-tool multi-turn、mock-tool multi-turn、real-runner multi-turn、compact multi-turn 必须走同一 `open_host(options)` / public command / public read path。

对应设计章节：
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §12 Follow-up 与 Steer
- `docs/host/design.md` §21 Suspend / Resume / Retry / Replay
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §23 RunInputBuilder
- `docs/host/design.md` §24 Conversation Memory
- `docs/host/design.md` §25 Context Governance

前置条件：
- Phase 10 Context Governance / Compaction draft PR gate 已通过，且普通多轮会话主体能力已经落地到 Host 内部组件。
- `docs/host/post-p10.md` 已记录 P10.5 目标与任务清单、缺口清单、测试替身约束与 smoke coverage matrix。

进入条件：
- 已确认 P10.5 不考虑 Recovery，不迁移 `/Users/leo/workspace/dayu-agent` 的 web tools，不要求 Service / CLI / WeChat / GUI 真实入口改造，不要求业务工具发现 / 动态 ScenePrepare。
- 已确认若 P10.5 发现需要新增、删除或改变 `dayu.host` public API，必须先和用户讨论并更新 `docs/host/post-p10.md` 或 phase plan，不能由 implementation agent 直接改。
- 已确认真实 runner smoke 可参考 `dayu/config/llm_models.json` 写死 runner 参数，不实现 ConfigLoader；至少覆盖 mimo、ds/deepseek、gemini、qwen 四类配置。API key / 网络不可用时允许对对应 provider 显式 skip 并记录原因，但测试文件和 wiring 必须存在。mock runner smoke 已删除；runner test double 只能作为低层辅助测试，不能计入 P10.5 smoke success signal。mock tool 不得按 expected answer、run id、轮次或测试私有状态凑结果。
- 三路 plan-readiness review 已完成且 blocking count = 0；P10.5 可以进入 implementation-ready planning。plan 必须把 review 的 non-blocking / clarification 项转成可执行约束：smoke matrix 每项 owner / 测试名 / public-path 断言 / skip 规则、`open_host(options)` typed shape、per-run execution override field-level partial merge 语义、`HostEventStream` 术语收敛，以及 review artifact 到 slice / 测试 / 后续 owner 的映射。

范围：
- 允许修改：Host opener / public handle 与内部 composition root、public command facade 与 scheduler wakeup 接线、session-level live Host event stream、typed HostEvent terminal final answer view、memory catch-up 与 context overflow compact 的 public opener construction contract、compactor execution baseline 接线、`submit_followup(steer)`、`retry_run(...)`、`replay_run(...)` 本地语义、public Run API 状态语义测试与文档、普通本地多轮 smoke harness、mock tool 测试实现、runner test double 低层辅助测试、compact smoke、真实 runner smoke 的受控配置接线。
- 禁止修改：Recovery / startup scan / positive orphan proof / `RECOVERING` 通用恢复语义、RemoteProxy、业务工具发现 / 注册 / provider 配置、真实 Service / CLI / WeChat / GUI 接入、web tools 迁移、Engine 主动理解 Host memory / governance。

不做：
- 不实现 Phase 11 Recovery，不把 projection lag、memory lag 或 failed dispatch 解释成 recovery；`retry_run(...)` 对 `LOST` / `RECOVERING` 的恢复相关行为仍归 Phase 11。
- 不迁移旧仓库 web tools；核心 smoke 使用 no-tool 或 mock tool。
- 不实现 ConfigLoader；真实 runner 所需参数可以写死在 P10.5 受控代码或测试配置中。
- 不实现业务财报工具端到端、动态 ScenePrepare、真实 Service / CLI / WeChat / GUI 接入。
- 不实现 callback HTTP endpoint、callback auth / replay、wait poller 后台 loop、backoff / in-flight fencing 或 external job physical cancel / revoke；P10.5 只验证 `WAITING` 后由调用方 / tool adapter 通过 Host public `resolve_wait(...)` 提交已取得结果并恢复执行。
- 不实现 `purge_session(...)` destructive cleanup、purge tombstone、删除矩阵、payload / memory / projection / outbox / tool trace 清理、audit 查询或 retention hardening；这些继续归 Phase 15。P10.5 只要求 `close_session(...)` public contract 可用，并保留 purge public envelope / error boundary。
- 不实现 Outbox concrete read / drain API 或离线 terminal delivery smoke；P10.5 只冻结 attach / reconnect recipe、terminal identity 与去重要求。Phase 13 必须实现 Outbox read / drain API、OutboxSink terminal delivery queue projection 与离线 terminal 补读 smoke。
- 不为测试或薄 Service 增加未经讨论的专用 public API。
- 不定义 `wait_final_answer(...)`、public payload reader、`read_payload(ref)` 或 `get_run_result(...)`；不把 `stream_run_events(...)` / `HostEventView` 放进普通 Service-facing public contract；final answer 主路径只能是 terminal HostEvent。

关键设计问题：
- 必须确认 `open_host(options)` public handle 的 options shape、生命周期、错误语义，以及它如何内部复用或替代现有 `create_host_command_handle(...)`。关闭语义不得重开讨论，必须按 `docs/host/design.md` 已定的 `close_session` 与 Host graceful shutdown 语义接入。`HostLocalRuntime` / `HostLocalExecutionOptions` 只能作为内部 contract，不得要求业务上层理解。
- P10.5 已确认 Host opener close shutdown order 是 implementation requirement：先关闭 public gate 并拒绝新 API；停止 scheduler / promotion / background supervisor；关闭 session live watch fanout；通过 active worker registry 传播 lifecycle cancel，使 Host 注入 Engine 的 cancellation token 可见并通知 `LocalWorkerHandle.on_cancel(reason)` hook；随后关闭或取消当前 handle 持有的 active worker task、lane wait、worker stream consumer task；flush / close projection catch-up 与本地 runtime resources；最后关闭 durable store。全程不得写 `RUN_CANCELLED` / `RUN_FAILED` 或其它 terminal fact 来伪装用户意图。
- 必须确认 public command accepted / queued / resolve-wait 后如何在 `open_host(options)` 内部唤醒 scheduler，确保 Service 不需要也不能读取内部 dispatch row、调用 scheduler / wakeup / dispatch control API 或调用 `dayu.host.dispatch` 私有入口。
- 必须按 `docs/host/design.md` 已定 contract 落地并验证 session-level live Host event stream：在线 / 已 attach 客户端通过 `watch_session_events(session_id)` live watch 观察 typed `HostEvent`，支持多客户端打开同一 Session、queue、steer、retry / replay；run-level `stream_run_events(...)` / `HostEventView` 只作为内部 diagnostic / detail / debug / drill-down 契约，不作为聊天主入口，也不进入普通 Service-facing public contract。P13 Audit / Tool Trace / Outbox 不依赖 `HostEventView`，只消费 committed EventLog / typed projection input view。`watch_session_events` 不接收 cursor，不承担离线补读；拿到 / attach Session 前发生的 terminal/final answer 通知由 Outbox 承接。
- P10.5 已确认多客户端写入策略：同一 Session 不引入 client ownership、session write lock 或 attach token。多个客户端可同时 `watch_session_events(session_id)`，也可同时提交 `submit_followup(queue)` / cancel / retry / replay 等 public command；写入顺序、幂等和冲突处理只能由 Host durable admission transaction、`client_request_id`、Run 状态 precondition、`event_sequence` 与 scheduler governance 决定。P10.5 smoke 必须覆盖多个 watcher 独立观察同一 Session，以及两个不同 `client_request_id` 的 queued prompts 按 durable accepted order 后续执行；相同 `(session_id, client_request_id)` 重放不得重复创建 Run。
- P10.5 已确认 Outbox 裁剪：只冻结 attach / reconnect recipe、terminal identity 与去重要求；P10.5 不提供 Outbox concrete read / drain API，不把离线 terminal 补读计入 smoke coverage。Phase 13 必须补 concrete Outbox read / drain API、OutboxSink terminal delivery queue projection、terminal item idempotency 与离线 terminal delivery smoke，证明 Outbox drain 与随后 / 并发 live watch attach 不漏投、不重复展示同一 terminal answer。
- P10.5 已确认 `submit_followup(queue)` request / response contract：第一条 prompt 和后续普通 prompt 使用同一个 `SubmitFollowupRequest` shape，不为首轮增加专用字段；`FollowupSnapshot` 以 `accepted_run_id`、`accepted_run_status` 和 command commit event sequence / durable read watermark 表达 command commit 后 durable 状态；该 watermark 不是 `watch_session_events` 的 cursor。无 active / start-blocking Run 时返回 `ACCEPTED`，有 active / start-blocking Run 时通常返回 `QUEUED`，随后由 scheduler governance 推进到 `RUNNING` / terminal；`queued_run_id` 不进入普通 Service-facing 主 contract。`start_run(...)` 的既有测试、README 和包根导出必须同步调整为内部 `_start_run(...)` 边界。
- P10.5 已确认 per-run tool selection contract：Host opener / construction options 注入全量业务 `ToolBundle`；`SubmitFollowupRequest.tool_names` 只选择本次 Run 的业务工具名，不携带 raw `ToolBundle`、`ToolDefinition`、callable binding 或 discovery adapter。`None` / 省略表示全部业务工具，空集合表示禁用业务工具，非空集合表示指定子集。Host admission 必须校验工具名并冻结本次 effective tool set。
- P10.5 已确认 memory catch-up / compactor / compactor execution baseline / budget policy / compact artifact root 的 Host opener construction contract。Compactor 共享 Host runtime / durable / memory / artifact 环境，但不共享每个 ordinary Run 的 `runner_spec` / `runner_options` / `agent_policy` / `tool_names` override；P10.5 必须验证 ordinary Service 只通过 public opener / handle 即可跑通 compact 后的多轮 continuity。P10.5 compact smoke 必须接入真实 compactor adapter；mock / test-double compactor 只能用于低层单元测试或辅助回归，不能作为 compact success signal，也不得绕过 canonical compact event、artifact 写入、memory projection consumption 和下一轮 RunInputBuilder 注入。
- P10.5 已确认长事务裁剪：`WAITING` / wait record / `resolve_wait(...)` public resume path 纳入 public contract freeze 与 smoke；生产级 callback endpoint、callback auth / replay、poller 后台 loop、backoff / in-flight fencing、external job physical cancel / revoke 不纳入 P10.5。P10.5 必须验证 Run 进入 `WAITING` 后，调用方只通过 Host public `resolve_wait(...)` 提交 poll / callback / manual 已取得结果，Host 内部 wake scheduler / dispatch 并最终通过 `watch_session_events(...)` 产出 terminal HostEvent。
- P10.5 已确认 Session cleanup 裁剪：只要求 `close_session(...)` public contract 可用并纳入 smoke；`purge_session(...)` destructive cleanup 继续归 Phase 15。P10.5 必须验证 `close_session(...)`、Host opener close 与 cancel 是三个不同动作：`close_session(...)` 只关闭 Session 新输入入口，不停止本地 runtime，不删除事实；Host opener close 只关闭当前 handle 的本地 runtime，不把 Session 改成 `CLOSED`，不写用户 cancel facts，已 accepted 但未 terminal 的 Run 由后续 startup recovery 基于 `STOPPED` lifecycle proof 或 stale `STOPPING` owner 的进程证据接管；cancel 才表达用户停止 Run 的治理意图。Session closed 后读取 / live watch 既有事实仍可用，新 `submit_followup(...)` 返回明确 invalid-state / typed error。Recommended Service policy 是用户意图为“结束会话并停止当前工作”时，Service 显式先调用 `cancel_session_runs(...)`，确认 cancel 可见后再 `close_session(...)`；Host 不在 `close_session(...)` 内自动 cancel。`purge_session(...)` 在 P10.5 可保持 unsupported / deferred 或 precondition error，但必须有清晰 public envelope / closed-handle guard，不能被当作 archive / close / cancel 使用。
- P10.5 已确认 HostEventStream typed `HostEvent` terminal contract：普通 Service 通过 `watch_session_events(...)` 观察 terminal HostEvent 并展示 final answer，不直接查询 EventLog / payload 内部表；raw `EngineEvent` 不进入 Service-facing public API，`HostEventView` 改为 Host 内部 run-level diagnostic / detail DTO，不从 `dayu.host` public namespace 导出。P10.5 不定义 `wait_final_answer(...)` public API；final answer 主路径只能是 terminal HostEvent。第一版 terminal final answer view 字段固定为 `content`、`filtered`、`degraded`、`finish_reason` 与 terminal status；超时、取消、错误和 terminal 判断语义随 `watch_session_events(...)` / HostEventStream lifecycle 一并落地。
- P10.5 已确认 per-run execution override 是 field-level partial merge，不是 all-or-nothing profile。`SubmitFollowupRequest.runner_spec`、`runner_options`、`agent_policy` 各字段省略时使用 `open_host(options)` baseline；字段出现时使用该字段的完整 typed value。plan / implementation 不得接受 patch dict、无结构 policy override、extra payload 或 profile registry lookup。
- `steer`、`retry`、`replay` 的语义不作为 P10.5 开放设计问题重开；必须按 `docs/host/design.md` 已有定义落地本地语义、状态迁移、terminal race、idempotency 与 smoke。P10.5 的 phase-scope 裁剪只有：Recovery 专属 `LOST` / `RECOVERING` retry / cancel / recovery 处理不进入本 phase，继续归 Phase 11；不新增 `interrupt_*` public API，UI interrupt 文案只能映射到 `cancel_run(...)` 或 `submit_followup(steer)`。
- P10.5 已确认 smoke 覆盖矩阵：real-runner no-tool multi-turn、mock-tool wiring、real-runner matrix、compact、WAITING resume、steer / retry / replay、cancel、`close_session(...)` public contract。mock runner smoke 已删除；对本轮不覆盖但接受的项必须有 owner 和后续 destination。
- 若改变 public interface / contract，先和用户讨论并写回 `docs/host/post-p10.md` 或对应 phase plan。

交付物：
- phase design refinement / P10.5 discussion artifact
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: async Host opener / public handle、内部 composition root 与 public command -> scheduler wakeup 接线。
- Slice 2: session-level live Host event stream、typed HostEvent、terminal final answer view、public Run API 状态语义测试与 Host README 同步。
- Slice 3: 按 `docs/host/design.md` 已有定义实现 `submit_followup(steer)` 本地语义、terminal race、cancel / dispatch 接线与 tests；不新增 interrupt public API。
- Slice 4: 按 `docs/host/design.md` 已有定义实现 `retry_run(...)` / `replay_run(...)` 本地语义、source Run 关联、retry policy tool fact reuse、no-tool replay policy 与 tests；`LOST` / `RECOVERING` retry 归 Phase 11。
- Slice 5: real-runner no-tool / mock-tool wiring / cancel smoke，覆盖 `docs/host/post-p10.md` 的 S1 / S2 / S5 coverage matrix 与测试替身约束，并覆盖 steer / retry / replay / cancel smoke；mock runner 不计入 smoke success signal。
- Slice 6: real-runner matrix smoke，使用硬编码 runner 参数并走同一 runtime / public command / public read path；至少覆盖 mimo、ds/deepseek、gemini、qwen 四类配置，环境不可用时对对应 provider 明确 skip 并记录原因。

Plan 必须额外收口的 readiness review checklist：
- 建立 S1-S5 与验证要求的统一 coverage table，明确每项 owner slice、测试名 / smoke 名、public-path 断言、skip 条件和后续 owner；不能只写“按 post-p10 覆盖”。
- 在 Slice 1 中落定 `open_host(options)` 的 typed options shape，不能把 construction-time 依赖留成无结构 dict、service locator 或测试 harness。
- 在 Slice 1 / Slice 5 / Slice 6 中覆盖 per-run `runner_spec` / `runner_options` / `agent_policy` field-level partial merge 与 effective config freeze；同一 Session 不同 Run 切换模型或参数必须通过 public request 证明。
- 在 Slice 2 中把 `watch_session_events(session_id) -> AsyncIterator[HostEvent]` 写成唯一普通 Service-facing 事件入口；`HostEventStream` 若保留，只能作为内部实现或类型别名，不能成为新的 public handle。
- 在 plan 文档中逐条引用三份 plan-readiness review artifact，并说明每个 non-blocking / clarification 的处理位置。

验证要求：
- unit tests: public contract validation、Host opener lifecycle、per-run tool_names selector validation / effective tool set freeze、session-level live watch lifecycle / fanout / filter semantics、typed HostEvent 与 terminal final answer view、public Run API `ACCEPTED -> scheduler governance -> RUNNING / terminal` 状态语义、steer / retry / replay request validation、idempotency、状态迁移与错误语义。
- integration tests: real-runner no-tool multi-turn smoke、mock-tool wiring smoke、real-runner matrix smoke、真实 compactor compact smoke、WAITING -> public `resolve_wait(...)` resume smoke、steer / retry / replay local smoke、cancel smoke、`close_session(...)` public contract smoke。
- smoke 覆盖：必须按 `docs/host/post-p10.md` 的 Smoke Coverage Matrix 标注 covered / not covered but accepted / blocking gap。
- pyright: 受影响 Host / tests 通过，且不新增或扩散类型错误。
- docs: `dayu/host/README.md`、`tests/README.md` 及必要的 `docs/host/post-p10.md` / phase plan 同步。

退出条件：
- 普通 Service 只调用 Host public interface / contract，即可完成普通本地多轮会话闭环：打开 Host、创建 / 取得 / 读取 session、通过 session-level live Host event stream 读取 / 订阅 typed HostEvent、通过 `submit_followup(queue)` 提交第一条与后续普通 prompt、在 terminal HostEvent 中观察 final answer、关闭 Host。
- `submit_followup(steer)`、`retry_run(...)`、`replay_run(...)` 不再是普通本地语义下的 stable unsupported；它们的本地状态迁移、dispatch 接线、read / event 可见性和 smoke 已覆盖。Recovery-only 状态仍按 Phase 11 owner 处理。
- real-runner no-tool、mock-tool wiring、real-runner matrix 与 cancel smoke 均使用同一 `open_host(options)` / public command / public read path；不得手工调用 scheduler internals、读取 dispatch row、直接查询 durable 内部表取得 answer / cancel result，或让 runner test double / mock tool 凑 expected answer。mock runner smoke 不进入 P10.5 success signal。
- P10.5 对普通本地多轮会话 public interface / contract 的冻结结论已写入 `docs/host/post-p10.md` 或 phase closeout；任何未冻结项都有明确 owner 和后续 destination。
- P10.5 已经把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实；真实 CLI / web / GUI 后续通过 Service 接入时，不需要绕过、替换或重写 P10.5 冻结的 Host public interface / contract。
- P11 Recovery 可以在不破坏 P10.5 已冻结普通本地多轮 public contract 的前提下继续实施；若 P11 必须改变 public API 或核心契约，必须先回到用户讨论。
- P11-P15 完成后，真实 CLI / web / GUI 接入不得要求重写 P10.5 已冻结的普通多轮生产接线；这些后续 phase 只能在该 public contract 上扩展 Recovery、ToolsDiscovery / ScenePrepare、Audit / Tool Trace / Outbox、RemoteProxy 与 Retention / Purge 能力。

后续依赖：
- 后续 phase 可依赖的稳定契约：普通本地多轮 Host public interface / contract、`open_host(options)` / public handle、internal composition root、command -> scheduler 内部接线、session-level live Host event stream、typed HostEvent terminal final answer view、steer / retry / replay 本地语义、no-tool / mock-tool / real-runner smoke coverage baseline。
- 需要追踪到后续 phase 的事项：Recovery / startup crash recovery / positive orphan proof 归 Phase 11；ToolsDiscovery / ScenePrepare 归 Phase 12；Audit / Tool Trace / Outbox 归 Phase 13；RemoteProxy 归 Phase 14；Retention / Purge production hardening 归 Phase 15。

### Phase 11. Host Lifecycle / Recovery / Multi-process Hardening

目标：
- 实现 Host startup recovery scan、positive orphan proof、prompt accepted but answer not returned 的恢复语义、graceful shutdown 与多进程一致性硬化。P11 明确拥有“未被 LLM 响应的 prompt，崩溃退出重进恢复”：已 durable accepted 的 prompt 或已启动但未 terminal 的 Run，在 Host 重启后必须通过 recovery scan / positive orphan proof / recovery dispatch 继续，或按 policy 给出确定 terminal。

对应设计章节：
- `docs/host/design.md` §27 Host Lifecycle / Recovery
- `docs/host/design.md` §27.1 已接受 Prompt 的恢复语义
- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §17 WorkerProxy / EngineWorker

前置条件：
- Phase 10.5 ordinary local multi-turn public contract freeze 已完成；P11 不得破坏 P10.5 已冻结的普通本地多轮 Host public interface / contract，若 Recovery 必须新增或调整 public API / 核心契约，必须先回到用户讨论。
- Core Host Public Interface Freeze 已生效：P11 及后续返工不得修改、删除或重定义现有 `open_host(options)`、`OpenHostOptions` 现有字段、`Host` public handle 方法、public request / response dataclass 字段、`watch_session_events(session_id)` live-only 语义、`HostEvent` terminal final answer view，也不得重新公开 `start_run`、`create_host_command_handle`、`stream_run_events` 等低层入口。
- P10.5 不证明 crash recovery，但已经冻结 Service 调用方式；P11 必须在同一 `open_host(...)` / session acquisition / `watch_session_events(...)` / public command contract 上补 recovery，不能要求真实 Service 改走另一套恢复入口。
- Phase 5 dispatch record / LocalProxy 已完成。
- Phase 2 host instance liveness foundation 已完成。
- Phase 3 state transition / admission 已完成。

进入条件：
- 已确认 positive orphan proof 的本机 pid / process_start_token / heartbeat 判定实现策略；第一版 baseline 记录在 `docs/host/design.md` §27 与本文档当前状态。

范围：
- 允许修改：startup recovery scan、host instance heartbeat、orphan classifier、RECOVERING dispatch、shutdown policy、multi-process tests。
- 禁止修改：远端 takeover、lease / fencing 系统、旧 Attempt resume。

不做：
- 不保证 exactly-once 远程物理执行。
- 不强杀远程执行环境。
- 不从 projection 或 memory 恢复 Run truth。

关键设计问题：
- 已确认 `RUNNING` / `CANCELLING` / `RECOVERING` / `WAITING` / `QUEUED` startup 分类。
- 已确认 suspect owner 不被误杀的 diagnostic path。
- 已确认 repeated recovery 上限与 LOST / FAILED 收口 policy。

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

状态：
- P12 completed。所有 slices、aggregate deepreview、aggregate fixes 与 aggregate re-review 已完成；当前进入 `ready-to-open-draft-PR`。

目标：
- 实现独立于 Host 的工具发现 / 注册、场景准备与配置加载 runtime assembly 边界，让业务工具集合、scene inputs 与 execution config 能在 Host construction / Service request envelope 前被 typed 组装，不让 Host import 具体业务工具、扫描业务包、读取应用配置文件或拼接财报场景 prompt。

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
- Core Host Public Interface Freeze 已生效：P12 只能实现 Host 外部 runtime / Service assembly 能力，不得修改、删除或重定义现有 `dayu.host` public exports、`open_host(options)`、`OpenHostOptions` 现有字段、`Host` public handle 方法、public request / response dataclass 字段或 `watch_session_events(session_id)` live-only 语义。

进入条件：
- 确认 ToolsDiscovery / ScenePrepare 仍是 Host 外部装配能力，不拥有 Session / Run / Attempt / EventLog truth。
- 确认具体财报业务工具 provider、财报 prompt 文案、财报 scene manifest 内容属于 Service / Fins / 配置边界，不写入 `dayu.runtime`。
- 确认是否需要把 ToolsDiscovery / ScenePrepare 放入 `dayu.runtime`；若放入，只能依赖标准库与 `dayu.contracts`，不得 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 或具体业务工具包。

范围：
- 允许修改：ToolsDiscovery typed provider protocol、tool provider aggregation、`ToolBundle` validation / source refs assembly、ScenePrepare typed manifest assembly helper、scene input typed output、ConfigLoader typed config loading / validation、旧项目 scene manifest 与其引用的 prompt fragment assets 按新 schema 迁移到当前项目配置资产目录、import boundary tests、相关 README。
- 禁止修改：Host durable state machine、Host command path、Host 公开接口、Engine execution path、ToolRuntime accept barrier、具体业务财报工具实现、财报仓储实现。

不做：
- 不实现 Audit / Tool Trace / Outbox projection；该能力在 Phase 13。
- 不实现业务财报工具扫描硬编码清单。
- 不把财报 prompt 文案、prompt fragment 内容、task prompts、业务 prompt 模板或 Fins storage 访问逻辑放入 `dayu.runtime`；旧项目迁移范围只包含 scene manifest 以及这些 manifest 直接引用的 prompt fragment assets，并且只能作为当前项目配置资产进入 `dayu/config/prompts` 或等价配置目录。
- 不让 ConfigLoader import Host、Engine、Service、UI、Fins 或具体业务工具包；ConfigLoader 只负责原样读取 / overlay / 校验 typed config，不构造 Host、不创建 provider client、不解释或保护 provider secret。
- 不让 per-run request 携带 raw `ToolBundle` 或 callable binding。
- 不把 `open_host(options)` 的 construction-time inputs 伪装成 per-run override；durable store / artifact roots、SQLite / lane 参数、worker factory、ordinary baseline、`HostToolingOptions`、context budget、compactor baseline、memory projection 与 truncation manager 开关只能在 Host 外部装配时确定。
- 不新增、不删除、不重命名、不重塑 Host public command、Host handle method、Host opener option、Host request / response dataclass field 或 `dayu.host` public exports；ToolsDiscovery / ScenePrepare / ConfigLoader 的 typed output 必须通过现有 `HostToolingOptions`、`SubmitFollowupRequest` 显式字段或 Host 外部 Service envelope 承接，不能把装配过程塞入 Host 状态机。

关键设计问题：
- 必须确认 ToolsDiscovery provider protocol 的最小 typed shape：provider identity、version / digest source refs、`ToolDefinition` collection output、duplicate name handling、reserved framework tool name conflict handling。
- 必须确认 ScenePrepare 的 typed scene input output shape，以及它如何进入 Service / Host request envelope 而不变成 Host 状态机语义。
- 必须按新 schema 重塑 ConfigLoader，不沿用旧 `llm_models.json` / `run.json` 的混合职责；配置视图拆分为 `models.json`、`execution_profiles.json`、`host_runtime.json` 与 `tool_discovery.json`，并支持包内默认配置 + workspace 覆盖配置的 typed loading / validation；新 schema 落地后必须删除旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json`，不保留兼容读取路径。
- 必须实现 ConfigLoader overlay 规则：顶层 map 按 id 合并，同 id 记录由 workspace 整条替换，不做隐式 deep merge；需要复用时用单继承 `extends`，继承解析后得到完整 typed record；ConfigLoader 不解析 env、不替换 secret、不脱敏，只原样读取配置值。
- 必须确认 `tool_selection` 第一版只支持 `mode=all|none|select`，其中 `select` 只支持 `tool_names` 与 `tool_tags_any` 并集选择；未知 tool name 报错，tag 无匹配默认报错，只有显式 `allow_empty=true` 时允许空选择。
- 必须确认 runtime assembly override 边界：override 合并由 Service / composition root 执行，优先级为未来 UI 显式输入 > scene manifest hints > ConfigLoader typed config view > 代码默认值；当前允许的 per-run override 仅为 `SubmitFollowupRequest.system_prompt`、`tool_names`、`runner_spec`、`runner_options` 与 `agent_policy`，其中 runner / agent override 必须映射为完整 typed value。
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
- Slice 3: ConfigLoader typed config loading / validation, new config asset migration, removal of legacy `llm_models.json` / `run.json`, and execution config mapping boundary。
- Slice 4: ScenePrepare typed manifest assembly helper and scene input output。
- Slice 5: migrate legacy `dayu-agent` scene manifest and referenced prompt fragment assets into current config assets using the new ScenePrepare schema。
- Slice 6: import boundary tests and README sync。

验证要求：
- unit tests: provider aggregation、duplicate tool names、reserved framework tool conflicts、source refs / digest stability、scene manifest assembly、invalid manifest errors。
- unit tests: ConfigLoader 能加载 / 校验 `models.json`、`execution_profiles.json`、`host_runtime.json` 与 `tool_discovery.json` 的 typed config，覆盖 workspace 整条替换、单继承 `extends`、非法 deep partial、非法缺字段与非法 secret / env 原样值类型。
- unit tests: ScenePrepare / Service mapping helper 能把 `mode=all|none|select` 的 `tool_selection` 映射为 `SubmitFollowupRequest.tool_names` 语义；覆盖 explicit names、tag-based selection、names + tags 并集、未知 name、tag 无匹配和 `allow_empty=true`。
- import boundary tests: runtime assembly modules 与 ConfigLoader 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 或具体业务工具包。
- integration tests: 可使用 fake providers / fake scene manifests；迁移后的真实 scene assets 必须能被 ScenePrepare 新 schema parser 校验 / assembly，但不得要求真实财报工具扫描、Fins storage 或外部模型调用。
- pyright: runtime assembly / affected contracts 通过。
- docs: `dayu/README.md` 与受影响包 README 按职责同步。

退出条件：
- 外部装配方可以通过 typed provider / manifest assembly 得到业务 `ToolBundle`、`ToolBundleSourceRef` 与 typed scene inputs，并把它们交给 Host construction / request envelope，而无需 Host import 业务工具或拼 scene prompt。
- Service 可以通过 ConfigLoader 加载 `models.json`、`execution_profiles.json`、`host_runtime.json` 与 `tool_discovery.json` 的 typed config，并将 ScenePrepare 输出的 `model_hints` / `runtime_hints` 显式映射为 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 或其它现有 typed input；映射失败必须在调用 Host 前失败。
- 旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json` 已删除；P12 不提供旧配置文件兼容读取、兼容测试或兼容 wrapper。
- Scene manifest 的 `tool_selection` 只通过 names / tags 选择 construction-time `ToolBundle` 子集，不替换 bundle，不引入 raw callable binding，并能稳定映射为 `SubmitFollowupRequest.tool_names`。
- Service 可以在 Host 外部按未来 UI 显式输入 > scene manifest hints > ConfigLoader typed config view > 代码默认值的顺序完成 assembly override，并且只通过现有 `SubmitFollowupRequest` per-run override 字段或 `open_host(options)` construction-time typed inputs 调用 Host。
- 旧项目 `dayu-agent` 的 scene manifest 与其直接引用的 prompt fragment assets 已按新 schema 迁移到当前项目配置资产目录；迁移结果通过新 ScenePrepare parser / assembly 测试，且 task prompts、contract files、workflow 产物与业务内容不进入 `dayu.runtime`。
- Runtime assembly 边界不持有 Host truth，不参与 Run / Attempt lifecycle，不决定 EventLog / ToolRuntime accept barrier。

后续依赖：
- 后续 phase 可依赖的稳定契约：business `ToolBundle` discovery boundary、scene input assembly boundary、source refs / digest assembly。
- 需要追踪到后续 phase 的事项：具体财报工具 provider、财报 scene manifest 内容、财报 prompt 文案仍属于 Service / Fins / 配置 work unit，不属于 runtime assembly phase。

### Phase 12.1. Runtime Assembly Schema / Public Contract Correction Follow-up

状态：
- design refinement in progress。进入 implementation 前必须完成本条目更新、handoff implementation-ready plan、plan review 与用户确认；implementation / fix / review 必须按 `$init-agents` 路由派发，不由 controller 直接执行。

目标：
- 纠正 Phase 12 runtime assembly 在真实 Service-like smoke 装配验证中暴露出的 schema / public contract mismatch，使 ConfigLoader、ScenePrepare、ToolsDiscovery 与 adapter/helper 能在不写脚本业务默认值的前提下装配 `open_host(options)` 与 per-run typed input。
- 保持 Host command / handle / opener 字段和 public request / response 方法不变；只在必要处修正 Host public policy dataclass、ToolTruncateSpec declaration/effective boundary 与 runtime config / scene schema。

对应设计章节：
- `docs/host/design.md` §3 dayu.runtime
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `docs/host/design.md` §24 Context Governance
- `docs/host/design.md` §25 Memory Projection

前置条件：
- Phase 12 已完成并达到 draft-PR-pass，用户报告 PR 67 已 merge。
- `docs/host/runtime-assembly-followup-discussion.md` 中的稳定裁决已写回 `docs/host/design.md`；该讨论稿不作为 implementation agent 的设计真源。
- 当前工作区中既有 `README.md`、`utils/smoke_host_public_multiturn.py` 等未提交改动必须在 plan 中先识别来源和归属；不得盲目基于半成品实现继续堆叠。

进入条件：
- `docs/host/design.md` 不再保留已废弃 scene/config 语义，例如 `conversation` 字段、泛化 `runtime` block、`model.default_name`、`model.temperature_profile`、`runner_options_profiles`、`runner_hints`、`agent_hints`、旧 `context_budget` / `memory_projection` / `truncation` schema。
- 本条目明确允许修改的 public contract 范围和禁止修改的 Host public surface。
- handoff plan 必须逐项对照 Host public contracts，确认 config / scene 是否足以装配 `open_host(options)` 与 per-run typed input。

范围：
- 允许修改：`dayu.runtime` location resolver、ConfigLoader schema / typed view / validation、default config assets、ScenePrepare schema / typed output、scene manifest assets、prompt fragment assets、ToolsDiscovery integration points、Host public `ContextBudgetPolicy` / `MemoryProjectionPolicy` typed shape、`ToolTruncateSpec` declaration/effective semantics、Engine provider extension adapter/helper、runtime assembly adapter/helper、`utils/smoke_host_public_multiturn.py`、相关 tests 与 README。
- 禁止修改：Host durable state machine、Host command path、Host handle method、`open_host(options)` 字段名、public request / response dataclass 字段名、`dayu.host` public exports、Engine execution loop 行为边界、ToolRuntime accept barrier、具体财报业务工具实现、Fins storage。

不做：
- 不实现真实 Service / CLI / Web / GUI workflow 接入。
- 不实现 Skill workflow orchestration、artifact store、parser/replay/retry/stop policy。
- 不保留旧 schema 兼容读取、兼容 wrapper 或兼容测试。
- 不让 ConfigLoader / ScenePrepare / ToolsDiscovery import Host、Engine、Service、UI、Fins 或具体业务工具包。
- 不让 scene manifest 表达 workflow stage graph、conversation lifecycle、Host runtime deployment、lane、SQLite、artifact root、memory / context policy 或 worker backend。

关键设计问题：
- Config catalog record id 必须由 map key 提供，record 内不得重复 id；`extends` 引用 map key。
- override 必须是 typed allowlist，优先级为 UI / Run override > scene typed override > execution profile baseline > code default；未知 override fail fast。
- runtime location resolver 位于 `dayu.runtime`，负责 workspace config / package default 路径选择；ConfigLoader / ScenePrepare 不内置 fallback。
- `runtime_lanes.json` 独立于 `host_runtime.json`；`host_runtime.json` 只保留 `host_execution_lane_name` 与 `worker_backend` 等 Host runtime profile 字段。
- `execution_profiles.json` 使用 `default_execution_profile_id`、`execution_profiles`、`run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy` 与 `agent_policy_profiles`。
- `models.json.models[*].runtime_hints.runner_option_hints` 是 RunnerCallOptions hint 真源；execution profile 只保存 semantic `runner_option_hint_id`。
- Host public `ContextBudgetPolicy` 与 `MemoryProjectionPolicy` 改为 `context_window_size` + ratio/floor/cap 模型；`context_window_size` 由 Service 从 effective model config 读取后直接放入 typed policy。
- `ToolTruncateSpec` 支持声明态缺省 limit / ttl，由 assembly 根据 `tool_truncation_policy` 补齐 effective spec；`fetch_more` 名称不在 config 中配置。
- `AgentPolicy` profile 一比一对齐 Engine / Host public fields；`fallback_mode` 使用 `force_answer` / `raise_error`，`fallback_prompt` 使用已裁决中文文本。
- Scene manifest 删除 `conversation` 字段和泛化 `runtime` block；`model.default_name` 改为 `model.default_model_id`，`model.temperature_profile` 改为 `model.runner_option_hint_id`；scene-level AgentPolicy override 使用顶层 typed `agent_policy` block。
- 旧项目模型目录必须全量迁移到新 `models.json`，provider extension DSL 由 Engine 侧 helper 映射为 Engine typed provider request extension。
- 最终验证 smoke 必须新增并默认使用 dedicated ordinary scene `smoke_host_public_multiturn`，不写 special case，不用脚本业务默认值遮住 schema / contract 缺口。

交付物：
- updated `docs/host/design.md`
- updated `docs/host/implementation-control.md`
- handoff implementation-ready plan
- plan review / fix / re-review artifacts
- implementation slices
- focused tests、integration smoke、pyright
- README sync

建议 slice 切分：
- Slice 1: Host public policy contracts and tool truncate declaration/effective boundary。
- Slice 2: Config schema correction, runtime location resolver, default config asset migration, full model catalog migration, legacy config deletion。
- Slice 3: ScenePrepare schema correction and scene asset migration, including `agent_policy`, `model.default_model_id`, `model.runner_option_hint_id`, removal of `conversation` / `runtime` / `prompt_mt`。
- Slice 4: Runtime assembly adapter/helper and Engine provider extension helper, keeping `dayu.runtime` import boundary clean。
- Slice 5: Rewrite `utils/smoke_host_public_multiturn.py` as Service-like final validation using dedicated smoke scene, ConfigLoader, ScenePrepare and ToolsDiscovery。
- Slice 6: README sync, import boundary tests, aggregate validation hardening。

验证要求：
- unit tests: ConfigLoader new schema validation, map-key ids, single `extends`, workspace whole-record overlay, runtime lanes, worker backend, fallback prompt/mode, agent policy fields, runner option hint resolution prerequisites。
- unit tests: ScenePrepare new manifest schema, no `conversation`, no raw `runtime` block, `model.default_model_id`, `model.runner_option_hint_id`, top-level `agent_policy` allowlist, names/tags tool selection, dedicated smoke scene assembly。
- unit tests: Host public `ContextBudgetPolicy` and `MemoryProjectionPolicy` ratio/floor/cap validation and threshold/budget derivation; `ToolTruncateSpec` declaration/effective default filling。
- unit tests: Engine provider extension DSL helper maps supported provider extensions and fails closed on unknown extensions。
- integration / smoke: `utils/smoke_host_public_multiturn.py` runtime path does not write business defaults, uses dedicated smoke scene, emits assembly diagnostics, and fails fast on missing config / contract mapping。
- import boundary tests: `dayu.runtime` modules do not import Host、Engine、Service、UI、Fins 或具体业务工具包。
- pyright: affected packages and tests pass with no new or expanded errors。
- docs: `dayu/config/README.md`、`dayu/host/README.md`、`dayu/engine/README.md`、root `README.md`、`tests/README.md` 按触发规则同步。

退出条件：
- Service-like assembly can derive `OpenHostOptions` and per-run `SubmitFollowupRequest` typed inputs from ConfigLoader、ScenePrepare、ToolsDiscovery、explicit CLI/UI override and stable code defaults only。
- `utils/smoke_host_public_multiturn.py` rewritten final validation path runs through dedicated smoke scene and reports assembly diagnostics instead of hiding schema / contract gaps。
- Old config files and old scene schema fields are removed without compatibility readers.
- Host public command / handle / opener field surface remains unchanged; accepted public contract changes are limited to policy dataclass / truncate spec typed shape.
- Aggregate deepreview from at least two review Agents PASS; control_doc records all residual risks with owners.
- User authorization applies: once `ready-to-open-draft-PR` is reached, controller may automatically enter draft PR gate and proceed to `draft-PR-pass`.

后续依赖：
- 后续 Service / UI / workflow integration can rely on runtime assembly helpers and smoke diagnostics as the production assembly reference.
- Real financial tool provider, financial scene content and workflow orchestration remain separate Service / Fins / UI work units.

### Phase 12.3. Config Schema / Usage Governance Follow-up

状态：
- completed；当前已进入 `ready-to-open-draft-PR`。Plan、implementation slices、review / re-review、aggregate validation 与总控裁决均已完成；accepted Slice 4 local commit hash 为 `7c32cfc`。

目标：
- 收口 P12.1 / P12.2 后继续暴露的 config schema 与 usage governance 小闭环，使默认配置更朴素、Service assembly 更薄、Context Governance 能消费 Engine 已上报的 usage observation。
- 保持 `dayu.runtime` import boundary；ConfigLoader 仍只读取 / 校验配置，不 import Host / Engine / Service / UI / Fins。
- 不把 usage 采集做成 config override；usage 是 provider capability 驱动的观测信号，不是 scene / Service 业务风格参数。

对应设计章节：
- `docs/host/design.md` §3 dayu.runtime
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §24 Context Governance

前置条件：
- Phase 12.1 runtime assembly schema / public contract correction 已完成。
- Phase 12.2 service assembly helper follow-up 已完成并 accepted local commit。
- `docs/host/config-schema-followup-discussion.md` 中 4 项裁决已收口：AgentPolicy 直接嵌入 execution profile、删除默认 `max_tokens`、usage post-call observation 消费、execution profile 按场景显式分档。

范围：
- 允许修改：`docs/host/design.md`、本文档、`dayu/config/*.json`、`dayu/config/README.md`、`dayu/runtime/config_loader.py`、`dayu/runtime/assembly.py`、`dayu/service/host_assembly.py`、Host Context Governance usage observation 消费相关模块、Engine / Host usage tests、Service assembly tests、runtime config tests、README。
- 禁止修改：Host durable state machine、Host command / handle public method、`open_host(options)` 字段名、`SubmitFollowupRequest` public 字段名、Engine Agent loop 状态机、Runner usage event contract、ToolRuntime accept barrier、具体财报业务工具与 Fins storage。

不做：
- 不实现真实 Service / CLI / Web / GUI workflow 接入。
- 不让 ConfigLoader 解析 secret、创建 provider client 或 import Engine provider extension typed union。
- 不引入 `usage_enabled` / `collect_usage` / `include_usage` 这类 config override。
- 不引入独立 `supports_usage` 字段；流式 usage capability 继续由 `models.json.supports_stream_usage` 表达，非流式响应如果 provider 返回 `usage`，Engine 默认读取。
- 不用 post-call usage 回头修改当前已经完成的 dispatch decision。

关键设计问题：
- `execution_profiles.json` 删除顶层 `agent_policy_profiles` catalog，删除 `execution_profiles[*].agent_policy_profile_id`，每个 execution profile 直接内嵌完整 `agent_policy` block。
- `models.json.runtime_hints.runner_option_hints` 删除默认 `max_tokens`；ConfigLoader runner option hint schema 与 Service assembly 默认 RunnerCallOptions 装配路径同步删除该来源。
- `RunnerCallOptions.max_tokens` 若 public contract 暂保留，只能作为明确 per-run / provider adapter override，不得来自默认 config。
- OpenAI-compatible payload 不应把默认通用 config 字段等同为 Chat Completions `max_tokens`；后续如确需限制输出，应按具体 provider API 字段单独设计。
- Engine 继续只负责如实上报 usage；Runner usage -> Engine `usage_reported` 现有事件链保持。
- Host ingest 继续 durable 化 `usage_reported`，并补齐后续消费所需的 attempt / execution context、估算 digest、policy ref 等关联信息。
- Context Governance 主动消费 usage，但 usage 是 post-call observation，只用于估算器校准、diagnostic 与后续 Run / 后续 compaction 治理参考。
- 当前 Run admission 仍由 pre-dispatch estimator、provider context overflow 与 reactive compaction 负责；usage 缺失、provider 不支持 usage 或 usage 字段格式异常都不得导致 Run 失败。
- `execution_profiles.json` 支持按场景显式分档，例如 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`；Service 显式选择 profile，helper 只做兼容性校验和 diagnostic，不根据 `models.context_window_tokens` 隐式切换 profile。

交付物：
- updated `docs/host/design.md`
- updated `docs/host/implementation-control.md`
- handoff implementation-ready plan
- plan review / fix / re-review artifacts
- implementation slices
- focused tests、pyright、README sync

建议 slice 切分：
- Slice 1: Config schema cleanup，内嵌 `agent_policy`、删除默认 `max_tokens`、更新 ConfigLoader typed schema / default config / README / Service assembly。
- Slice 2: Host Context Governance usage observation consumer，补 durable usage association、post-call diagnostic / calibration path 与 focused Host tests。
- Slice 3: Execution profile scene/window class split 与 assembly compatibility diagnostics，确保 Service helper 显式选择 profile、不自动切换。
- Slice 4: Aggregate validation、runtime / service / host tests、pyright、README sync 与 deepreview。

验证要求：
- unit tests: ConfigLoader 拒绝旧 `agent_policy_profiles` / `agent_policy_profile_id` 与 runner option hint `max_tokens`，默认配置可加载。
- unit tests: Service assembly 从 execution profile 内嵌 `agent_policy` 生成完整 Engine `AgentPolicy`，默认 RunnerCallOptions 不携带 `max_tokens`。
- unit tests: Engine usage 上报链保持不变；stream usage 只由 `supports_stream_usage` + `stream=True` 触发 `stream_options.include_usage=true`。
- unit tests: Host ingest / Context Governance 能把 usage 作为 post-call observation 消费，且不改变当前已完成的 dispatch decision。
- unit tests: execution profile compatibility diagnostic 覆盖 profile window class / min context window 与 effective model context window 不匹配场景。
- pyright: affected runtime / service / host / engine tests pass with no new or expanded errors。
- docs: `dayu/config/README.md`、`dayu/host/README.md`、`dayu/engine/README.md`、root `README.md`、`tests/README.md` 按触发规则同步。

退出条件：
- 默认 config 不再含 `agent_policy_profiles` / `agent_policy_profile_id` / runner option hint `max_tokens`。
- ConfigLoader、Service assembly helper 与 smoke-like tests 均只依赖新 schema，不保留旧 schema 兼容读取。
- usage 采集无 config override；`supports_stream_usage` 能完整表达流式 usage 请求 capability。
- Host Context Governance 已能消费 durable usage observation 作为后续治理参考，且不回改当前 dispatch decision。
- Aggregate deepreview from at least two review Agents PASS；control_doc records residual risks with owners.
- User authorization applies: once `ready-to-open-draft-PR` is reached, controller may automatically enter draft PR gate and proceed to `draft-PR-pass`.

后续依赖：
- 真实 Service / UI / workflow integration 继续负责根据业务场景显式选择 execution profile。
- 更细 provider-specific 输出 token 限制若未来需要，必须作为独立 provider adapter / public contract 设计，不回到默认 config `max_tokens`。

### Phase 12.5. Conversation Memory Optimization

状态：
- implementation-ready plan accepted；准备进入 implementation Slice 1 handoff。`evidence_backed_facts`、accepted evidence envelope 与
  compaction-gated extraction、recent_raw_turns_floor、minimum preserve 与 no-fallback-facts 稳定裁决已写回
  `docs/host/design.md`。Accepted design checkpoint 为 `9cfca70`。Planning handoff artifact 为
  `docs/reviews/phase12-5-plan-handoff-controller-20260522.md`。Accepted plan artifact 为
  `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`；plan review artifacts 为
  `docs/reviews/phase12-5-plan-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-plan-review-ds-20260522.md`、
  `docs/reviews/phase12-5-plan-review-controller-adjudication-20260522.md`；plan re-review artifacts 为
  `docs/reviews/phase12-5-plan-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-plan-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-plan-rereview-controller-adjudication-20260522.md`。Accepted plan local commit 为 `793f2c8`。
  Slice 1 `Contract Rename And Config Schema` implementation / code review / fix / re-review 已 PASS；review artifacts 为
  `docs/reviews/phase12-5-slice1-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice1-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice1-code-review-controller-adjudication-20260522.md`、
  `docs/reviews/phase12-5-slice1-code-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice1-code-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-slice1-code-rereview-controller-adjudication-20260522.md`。Slice 1 validation:
  `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_run_input_builder.py` PASS
  (74 passed)；targeted pyright PASS (0 errors)。
  Slice 2 `Accepted Evidence Envelope In Tool Accept Path` implementation / code review PASS；review artifacts 为
  `docs/reviews/phase12-5-slice2-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice2-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice2-code-review-controller-adjudication-20260522.md`。Slice 2 validation:
  `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_memory_projection.py` PASS (47 passed)；targeted pyright
  PASS (0 errors)。Deferred finding S2-D1：compact summary fact-ref test coverage 因 direct tool-result fact projection 被关闭而弱化，
  必须在 Slice 5 `Memory Projection Materialization` 恢复覆盖。
  Slice 3 `Compaction Structured Candidate Contract And Accept Barrier` implementation / code review / targeted repair / re-review
  已 PASS；review artifacts 为 `docs/reviews/phase12-5-slice3-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice3-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice3-code-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice3-code-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-slice3-code-rereview-controller-adjudication-20260522.md`。Slice 3 validation:
  `pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py`
  PASS (52 passed)；targeted pyright PASS (0 errors)。Deferred findings：candidate JSON helper duplication 由 Slice 7 /
  aggregate polish 处理；compact artifact v1 read-path fail-closed guard 由 Slice 5 `Memory Projection Materialization` 处理。
  Slice 4 `LLM Compactor Structured JSON Rewrite` implementation / code review / targeted repair / re-review 已 PASS；review
  artifacts 为 `docs/reviews/phase12-5-slice4-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice4-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice4-code-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice4-code-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-slice4-code-rereview-controller-adjudication-20260522.md`。Slice 4 validation:
  `pytest tests/host/test_llm_compaction.py` PASS (14 passed)；targeted pyright PASS (0 errors)；`compaction_budget.py`
  stale helper 已删除且无导入 / 调用残留。Deferred findings：empty candidate list 与 invalid enum 的 LLM 层专项测试暂缓，底层
  constructor / contract 行为已由 Slice 3 覆盖。
  Slice 5 `Memory Projection Materialization` implementation / code review / targeted repair / re-review 已 PASS；review artifacts
  为 `docs/reviews/phase12-5-slice5-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice5-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice5-code-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice5-code-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-slice5-code-rereview-controller-adjudication-20260522.md`。Slice 5 validation:
  `pytest tests/host/test_memory_projection.py` PASS (47 passed)；targeted pyright PASS (0 errors)。Deferred findings：
  durable snapshot read path 的额外 item-kind SQL validation query 暂留为防御性 residual；future schema relaxations 必须继续保持
  `validate_context_compacted_payload` 与 typed constructor validation 对齐。
  Slice 6 `RunInputBuilder Rendering And Compaction Request Wiring` implementation / code review / targeted repair / re-review
  已 PASS；review artifacts 为 `docs/reviews/phase12-5-slice6-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice6-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice6-code-rereview-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice6-code-rereview-ds-20260522.md`、
  `docs/reviews/phase12-5-slice6-code-rereview-controller-adjudication-20260522.md`。Slice 6 validation:
  `pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py` PASS (48 passed)；targeted pyright PASS
  (0 errors)。Deferred findings：bounded EventLog read 目前以 `start_event_sequence=1` 作为 session 起点保守读取并按 session
  过滤，Slice 7 / aggregate review 需决定是否派生 session min sequence；no-compaction / post-compaction follow-up 端到端 smoke 仍归
  Slice 7。
  Slice 7 `Integration Smoke, README Sync, Aggregate Validation` implementation / code review PASS；review artifacts 为
  `docs/reviews/phase12-5-slice7-code-review-mimo-20260522.md`、
  `docs/reviews/phase12-5-slice7-code-review-ds-20260522.md`、
  `docs/reviews/phase12-5-slice7-code-review-controller-adjudication-20260522.md`。Slice 7 validation:
  `pytest tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py`
  PASS (221 passed)；full pyright PASS (0 errors)。旧 `verified_*` / `tool_fact_refs` 扫描结论：active production path
  无旧 public contract 使用，剩余命中均为 fail-closed guard、fail-closed tests、当前 `preserved_fact_refs` payload 容器名或历史
  docs / review artifacts。Residual risks：public-path no-compaction continuity smoke 尚未新增；`compaction_evidence.py`
  使用 session-filtered `start_event_sequence=1` 保守读取；candidate JSON helper duplication 暂不阻塞。Owner：aggregate
  deepreview 决定是否在 draft PR 前补强，否则转后续 public smoke / performance hardening / cleanup work unit。
  Aggregate deepreview 初审：MiMo PASS with findings，artifact 为
  `docs/reviews/phase12-5-aggregate-deepreview-mimo-20260523.md`；DS NOT ready，artifact 为
  `docs/reviews/phase12-5-aggregate-deepreview-ds-20260522.md`，阻断项为 LLM compactor 未接收 evidence 内容、projection lag
  误杀 Run、FakeCompactor false positive、catch-up failure 静默忽略与 `EvidenceBackedFactView.claim_text` 长度防线缺失。
  Targeted aggregate repair 已完成（该证据输入方案后续已被 post-draft raw evidence compaction fix 取代）；
  dispatch 对 catch-up
  failure 与 `SNAPSHOT_LAG_OVER_THRESHOLD` 执行 rebuild / retry 且不 terminal closeout；`EvidenceBackedFactView` 增加
  claim_text 长度校验；`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` 已同步。Aggregate re-review PASS；
  artifacts 为 `docs/reviews/phase12-5-aggregate-rereview-mimo-20260523.md`、
  `docs/reviews/phase12-5-aggregate-rereview-ds-20260523.md`、
  `docs/reviews/phase12-5-aggregate-rereview-controller-adjudication-20260523.md`。Aggregate repair validation:
  `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_executor.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py`
  PASS (260 passed)；full pyright PASS (0 errors)；`git diff --check` PASS。P12.5 exit condition satisfied；ready-to-open-draft-PR。
  Draft PR gate：PR 68 (`https://github.com/noho/dayu-agent-r/pull/68`) 已创建为 draft，branch 已 push 到
  `origin/feat/phase-12-5-conversation-memory-optimize`，GitHub reported mergeable，status checks reported none。PR review artifacts
  为 `docs/reviews/pr-68-review-20260523-024713.md`、
  `docs/reviews/pr-68-review-ds-20260523.md`、
  `docs/reviews/pr-68-review-controller-adjudication-20260523.md`。PR-level review PASS；DS 中等严重度 finding
  `compactor prompt accepted evidence envelopes aggregate token guard` 后续并入 raw evidence prompt budget residual。
  P12.5 draft PR gate PASS；draft-PR-pass。
  Post-draft cancellation hardening：用户指出 compaction LLM call 不能接 `_NeverCancelledToken`，controller 裁决该动机成立。
  当前 PR fix 删除生产 `_NeverCancelledToken`，把 `CancellationToken` 显式贯穿 `ContextCompactor.compact(...)` 与
  `run_compaction_operation(...)`；proactive compaction 使用 durable Run 状态观察 token，reactive compaction 复用 Engine envelope
  token。Validation：`pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_artifact_store.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_phase5_local_execution_integration.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_phase7_waiting_integration.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_recovery_dispatch.py tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_logging.py -q` PASS
  (273 passed)；`python -m pyright dayu tests` PASS (0 errors)；`git diff --check` PASS。PR 68 回到 draft-PR-pass。
  Post-draft raw evidence compaction fix：用户指出 `result_preview` 作为 extraction primary input 会丢失“管理层讨论与分析”
  等长章节内容，controller 裁决该问题成立。设计真源已改为：Host 在 `TOOL_RESULT_ACCEPTED` 生成 canonical `evidence_id`；
  compactor input 必须使用 compact range raw tool result / raw transcript 作为事实抽取材料，并把 evidence id 标注到对应 raw 内容旁边；
  `result_preview` 概念必须删除。Implementation fix 已删除 active `result_preview` contract，新增 `CompactRawContextItem`
  / `compact_raw_context_items`，ToolRuntime 在 `TOOL_RESULT_ACCEPTED` 写入完整 `raw_tool_outcome`，compaction evidence helper
  从 compact input range 收集 tool result / user input / assistant conclusion raw context，LLM compactor prompt 使用
  `compact_raw_context` 与 Host-minted evidence refs。Review artifacts 为
  `docs/reviews/pr-68-postdraft-raw-evidence-review-mimo-20260523.md`、
  `docs/reviews/pr-68-postdraft-raw-evidence-review-ds-20260523.md`、
  `docs/reviews/pr-68-postdraft-raw-evidence-controller-adjudication-20260523.md`。MiMo PASS no findings；DS PASS，F3
  / F4 覆盖缺口已在本 gate 补测试，F1 raw evidence aggregate prompt budget 后续裁决为不引入 prompt budget guard，
  改由 reactive recovery dispatch / Engine overflow 闭环和 `max_reactive_compactions_per_run` 上限治理；F2 多 evidence
  id item-level 标注与 F5 EventLog 顺序显式化均不阻塞当前 V1。Validation：
  `pytest tests/host/test_compaction_operation.py -q` PASS (18 passed)；
  `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
  PASS (262 passed)；`pyright dayu tests` PASS (0 errors)；`git diff --check` PASS。当前 gate 回到 draft-PR-pass。
  Post-draft compactor scene prompt fix：用户指出 compact 所需 system prompt / user prompt 不应硬编码在 Host 代码中，
  controller 裁决该问题成立。最终边界为：Service / composition root 按 `compactor_baseline.scene_id` 使用 compactor scene 的两个 ordered
  fragments 装配 compactor system prompt 与 user prompt template；Host public typed boundary 通过 `CompactorRunnerBaseline`
  接收这两个 prompt 字段，并只负责把 typed `CompactionRequest` 渲染到 `<<compaction_request>>` 占位符。Compactor runner
  options 不随普通 Run override 复用，继续通过 execution profile 的
  `compactor_baseline.runner_option_hint_id=conversation_compaction` 从 `models.json.runtime_hints.runner_option_hints` 读取
  temperature / top_p / stream，`max_tokens` 保持无 cap。Fix 同时补强 quality gate：`open_questions_retained=false`
  现在会作为 `open_questions_missing` rejection reason，避免 accepted compact 到 canonical payload 校验阶段才失败。Re-review
  artifacts 为 `docs/reviews/pr-68-postdraft-compactor-scene-prompt-rereview-mimo-20260523.md` 与
  `docs/reviews/pr-68-postdraft-compactor-scene-prompt-rereview-ds-20260523.md`；两份 verdict 均为 PASS。DS 非阻断观察的
  compactor scene fragment count fail-fast 单测已补齐。Validation：
  `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/service/test_host_assembly.py -q`
  PASS (49 passed)；`pytest tests/host/test_public_compact_smoke.py -q` PASS (1 passed)；
  `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/service/test_host_assembly.py tests/runtime/test_scene_assets_migration.py tests/host/test_open_host_runtime.py tests/host/test_public_open_host_options.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  PASS (359 passed)；`pyright dayu tests` PASS (0 errors)；`git diff --check` PASS。Accepted fix commit 为 `1a3017f`，
  已 push 到 PR 68 branch；GitHub 当前 reported no checks。当前 gate 回到 draft-PR-pass。
  Post-draft compactor baseline scene id fix：用户指出 Service 仍硬编码 compactor scene 名，controller 裁决该问题成立。
  Fix 将 `scene_id` 纳入 `execution_profiles.json.compactor_baseline` 必填 schema；默认 profiles 显式声明
  `scene_id=conversation_compaction`；Service assembly 改为从选中的 execution profile 读取
  `compactor_baseline.scene_id` 调用 ScenePrepare，不再持有 compactor scene 名常量。Runner options 仍由
  `compactor_baseline.runner_option_hint_id` 独立选择，不与 ordinary Run options 复用。Review artifacts 为
  `docs/reviews/pr-68-postdraft-compactor-baseline-scene-id-rereview-mimo-20260523.md` 与
  `docs/reviews/pr-68-postdraft-compactor-baseline-scene-id-rereview-ds-20260523.md`；两份 verdict 均为 PASS。Validation：
  `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_public_compact_smoke.py -q`
  PASS (46 passed)；
  `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/service/test_host_assembly.py tests/runtime/test_scene_assets_migration.py tests/host/test_open_host_runtime.py tests/host/test_public_open_host_options.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  PASS (361 passed)；`pyright dayu tests` PASS (0 errors)；`git diff --check` PASS。当前 gate 回到 draft-PR-pass。

目标：
- 从买方财报分析 Agent 的第一性原理优化 Conversation Memory，使同一 session 内已由工具确认的关键财务事实能跨轮、
  跨 compaction 稳定复用，不依赖 assistant final answer、episode summary 或 raw turns 侥幸保留。
- 明确 pinned_state、evidence_backed_facts、derived analysis state 与 interaction continuity 的职责边界。
- 让 memory 最低语义能通过旧项目 `conversation_memory_test.md` 中测试 prompt 反推的验收：主体 / 口径不漂移、最近追问
  指代连续、长输入 minimum preserve、compaction 后 confirmed facts 不漂移、长会话口径约束稳定。

对应设计章节：
- `docs/host/design.md` §24 Conversation Memory
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §18 ToolRuntime / TruncationManager
- `docs/host/design.md` §20 RunInputBuilder

前置条件：
- Phase 12 runtime assembly / config governance 已完成并 merge。
- `docs/host/conversation-memory-first-principles-discussion.md` 已记录第一性原理讨论、旧项目测试 prompt 反推的最低验收语义
  与已裁决问题；该讨论稿不是设计真源。
- P12.5 design discussion 必须先裁决 evidence_backed_fact contract、recent raw turns 语义、minimum preserve 与
  compact summary / evidence_backed_fact 的边界，再进入 plan gate。

进入条件：
- `docs/host/design.md` 已写入 P12.5 稳定裁决，不保留讨论痕迹。
- 明确 Host 将旧 `VerifiedFactView` 迁移为 `EvidenceBackedFactView` 或等价 typed view，并扩展 projection payload contract / RunInputBuilder memory rendering。
- 明确 ToolRuntime / tool result accept path 如何记录 accepted evidence envelope；tool provider 不负责直接生成 memory facts，Host 不理解 evidence locator 语义。
- 明确 P12.5 需要新增 smoke / integration 测试覆盖财报事实跨轮复用、post-compaction fact reuse 与 minimum preserve。

范围：
- 允许修改：`docs/host/design.md`、本文档、Host Conversation Memory typed contracts、memory projection、RunInputBuilder
  memory rendering、Context Governance compact memory refs / preservation validation、ToolRuntime accepted tool fact payload contract、
  focused Host tests、public smoke / memory smoke、相关 README。
- 禁止修改：Engine Agent loop、Runner provider contract、runtime ConfigLoader / ScenePrepare / ToolsDiscovery schema、真实财报工具实现、
  Fins storage、Service / UI workflow、Host command / handle public method、`open_host(options)` 字段名、`SubmitFollowupRequest`
  public 字段名。

不做：
- 不实现 long-term cross-session retrieval、投资研究知识库、向量索引、公共 memory edit / forget API。
- 不把完整 tool result payload 原样塞进 memory；关键 claim 必须通过 `claim_text + accepted evidence_refs` contract 进入 `evidence_backed_facts`。
- 不让 episode summary 成为事实真源；episode summary 只能导航、引用或保留 evidence_backed_fact refs / evidence refs。
- 不让 assistant final answer 自动升级为 `evidence_backed_fact`。
- 不让 Host 解释“收入”“毛利”“净息差”等财报业务语义；Host 只保存业务中立 structured fact、opaque refs 与 provenance。

关键设计裁决：
- 旧 `verified_facts` 改名 / 迁移为 `evidence_backed_facts` 或等价 typed view；定义冻结为 `claim_text + accepted evidence_refs`，而不是 Host 理解 source / locator。
- Tool result accept path 形成 accepted evidence envelope；tool provider 不直接决定最终 memory facts。
- 缺少可投影 `evidence_backed_fact` 时，只能生成 diagnostic / repair outcome 并保留 accepted evidence refs，不得继续生成 neutral fallback fact。
- `recent_raw_turns_floor` 已裁决保留名称；语义是最近 raw turns 的最低保留数量，用于交互连续性，不承担 financial fact retention 或跨 compact 完整 tool transcript 保真。
- RunInputBuilder 渲染 `evidence_backed_facts` 时必须包含 `claim_text` 与 `evidence_refs`，不能只有 digest / ref。
- minimum preserve 已裁决为 compact structured output 中的 bounded continuity item，用于保护指代解析；不保留整段长 user input，不承担事实真源职责。

交付物：
- updated `docs/host/design.md`
- updated `docs/host/implementation-control.md`
- handoff implementation-ready plan
- plan review / fix / re-review artifacts
- implementation slices
- focused tests、integration smoke、pyright、README sync

建议 slice 切分：
- Slice 1: Contract Rename And Config Schema。
- Slice 2: Accepted Evidence Envelope In Tool Accept Path。
- Slice 3: Compaction Structured Candidate Contract And Accept Barrier。
- Slice 4: LLM Compactor Structured JSON Rewrite。
- Slice 5: Memory Projection Materialization。
- Slice 6: RunInputBuilder Rendering And Compaction Request Wiring。
- Slice 7: Integration Smoke, README Sync, Aggregate Validation。

验证要求：
- unit tests: accepted evidence envelope 能被 `evidence_backed_fact_candidates` 引用，Host accept barrier 只校验 `claim_text + evidence_refs` 通用 contract，不解析 source / locator。
- unit tests: RunInputBuilder memory block 渲染 `evidence_backed_facts` 时包含 `claim_text` 与 `evidence_refs`，不能只有 digest / ref。
- unit tests: recent continuity 保底覆盖最近追问指代，但不被当作 `evidence_backed_fact` 真源。
- unit tests: minimum preserve item candidate 只作为 continuity item materialize，Host 校验 item text / source refs / reason / 数量上限，且不生成 `evidence_backed_fact`。
- integration tests: no-compaction 短链路中，Run 1 查收入 / 毛利后 Run 2 问毛利率，后续 Run 能基于 recent raw turns / available context 稳定回答。
- integration tests: post-compaction 中，同一 session 先查收入 / 毛利，触发 compact 后同一次 structured compact proposal 生成 `evidence_backed_fact_candidates`，后续 Run 能基于 `evidence_backed_facts` 稳定回答毛利率。
- integration tests: 长 user input 提炼三个因素并触发 compact 后，下一轮追问“第二个因素”能基于 minimum preserve item 正确解析，不依赖完整原文保留。
- integration tests: compaction 后 confirmed facts 不漂移；episode summary 只能引用 `evidence_backed_facts` / evidence refs，不能替代 facts。
- pyright: affected host / tests pass with no new or expanded errors。
- docs: `dayu/host/README.md`、`dayu/README.md`、`tests/README.md` 按触发规则同步。

退出条件：
- Conversation Memory 的设计真源明确区分 Task State、Evidence-backed Facts、Derived Analysis State 与 Interaction
  Continuity。
- compact 覆盖范围内的历史工具证据 claim 可通过 `claim_text + accepted evidence_refs` contract 进入 stable `evidence_backed_facts`，跨 compaction 稳定可见。
- recent raw turns 只承担交互连续性保底，不承担财务事实保真。
- minimum preserve 对长 user input 后追问有可验证路径：compact output 产出 bounded continuity item，后续 RunInputBuilder 注入该 item 以解析指代。
- Aggregate deepreview from at least two review Agents PASS；control_doc records residual risks with owners.

后续依赖：
- 真实财报工具需要保证 tool result accept path 可形成 accepted evidence envelope；该接入归后续 Fins / tool provider work unit。
- long-term retrieval、cross-session research memory、public memory edit / reset / forget API 仍归后续独立 phase。

### Phase 12.6. Conversation Memory Redesign From First-Principles Discussion

状态：
- design discussion entry。P12.6 从 `docs/host/conversation-memory-compact-io-first-principles-discussion.md` 开始重新设计
  Conversation Memory。该讨论稿只作为 phase discussion 输入，不作为 implementation agent 的设计真源；进入 plan gate 前必须把稳定裁决写回
  `docs/host/design.md`。

目标：
- 以买方财报分析 Agent 的第一性原理重新设计 Conversation Memory，使 memory / compaction I/O 边界回到可解释、可审计、
  可长期稳定的结构，而不是在 P12.5 既有实现上继续局部补丁。
- 继承旧 `dayu-agent` Conversation Memory 已验证的稳定骨架：`pinned_state` materialized current state、recent raw turns
  floor、older prefix compaction、独立 compaction JSON payload、bounded episode rendering，以及避免 current user / raw turn /
  tool result 重复进入 compactor prompt。
- 在上述骨架上补齐 P12.5 需要但旧实现没有的通用 `evidence_backed_facts`：LLM-facing evidence block 使用可读 query /
  result / source locator 与 prompt-local evidence label；Host 内部把 label 映射回 EventLog canonical provenance。
- 修复当前 P12.5 smoke 暴露出的根因：compactor input 不得从 Session 起点 dump EventLog，不得把 Host provenance key 作为
  LLM 主要语义输入，不得重复渲染当前长输入或 raw evidence。

对应设计章节：
- `docs/host/design.md` §24 Conversation Memory
- `docs/host/design.md` §25 Context Governance
- `docs/host/design.md` §18 ToolRuntime / TruncationManager
- `docs/host/design.md` §20 RunInputBuilder
- `docs/host/design.md` §23 RunInputBuilder

前置条件：
- P12.5 已达到 draft-PR-pass，且已确认 bounded `result_preview` / EventLog range dump / Host provenance key 渲染等方向不足以作为最终
  Conversation Memory 设计。
- `docs/host/conversation-memory-compact-io-first-principles-discussion.md` 已记录当前第一性原理讨论、两轮 compact I/O 推演、
  旧 `dayu-agent` memory baseline 对照、long-session structured memory bloat 风险与 provisional JSON 输出草案。
- 旧 `dayu-agent` 的 `dayu/host/conversation_memory.py` 与 `docs/conversation_memory_test.md` 作为行为 baseline 参考；不得直接
  当成当前仓库实现方案照搬。

进入条件：
- P12.6 design discussion 必须先裁决 Conversation Memory 的最终结构、compact material pack schema、stable layer / history pool
  ownership、fact extraction / evidence provenance 边界、proactive / reactive compaction I/O、long-session consolidation /
  retention 策略。
- 若 discussion 改变 P12.5 已写入 `docs/host/design.md` 的结构或术语，必须先更新 `docs/host/design.md`，再进入
  handoff implementation-ready plan。
- 必须明确哪些 P12.5 代码作为可复用实现，哪些必须重写或删除；不得默认沿用当前实现路径。

范围：
- 允许修改：`docs/host/design.md`、本文档、Conversation Memory typed contracts、memory projection、compact material builder、
  compaction request / response contract、LLM compactor prompt / JSON schema、Context Governance compaction orchestration、
  RunInputBuilder memory rendering、ToolRuntime accepted tool result evidence projection、focused Host tests、public memory /
  compact smoke、相关 README。
- 禁止修改：Engine Agent loop、Runner provider contract、ConfigLoader / ScenePrepare schema、真实财报工具实现、Fins storage、
  Service / UI workflow、Host command / handle public method、`open_host(options)` 字段名、`SubmitFollowupRequest` public 字段名。

不做：
- 不实现 long-term cross-session retrieval、投资研究知识库、向量索引、公共 memory edit / reset / forget API。
- 不让 episode summary、assistant final answer 或 raw recent turns 自动升级为 `evidence_backed_fact`。
- 不把 Host internal `event_id`、payload ref、digest、cursor、policy、artifact descriptor 当作 LLM 的主要语义输入。
- 不把完整 EventLog range 或 Host ledger wrapper 塞进 compactor prompt。
- 不让 tool provider 生成 memory facts；tool provider / ToolRuntime 只产生 accepted tool result，fact extraction 由 Host-governed
  LLM compactor / extractor 完成。
- 不依赖不准 token 估算作为 reactive recovery 成败证明；reactive compact 必须通过 bounded pass + recovery dispatch / provider
  overflow 闭环 fail closed。

关键设计问题：
- 必须确定新的 Conversation Memory 树：`pinned_state`、`evidence_backed_facts`、`working_assumptions`、`open_questions`、
  conversation continuity、recent raw turns floor、older raw turns、episode summaries 的 ownership、rendering 与 retention。
- 必须决定旧 `confirmed_facts` 与新 `evidence_backed_facts` 的关系：旧字段只能作为前身 / summary view，不能替代
  evidence-backed stable facts。
- 必须确定 compact material pack 的输入边界：普通 compaction run messages 只能是 compactor system prompt + user material pack；
  material pack 必须由去重后的 stable input、history input、accepted tool evidence blocks 与 current input anchor 组成。
- 必须确定 accepted evidence 最小语义：canonical truth 是 `TOOL_RESULT_ACCEPTED`；LLM 看到的是 prompt-local evidence block；
  Host accept barrier 只校验 candidate 引用了存在的 prompt-local evidence labels，并映射回 canonical provenance。
- 必须确定 proactive compact 的安全条件：在 `soft_threshold_context_ratio` 触发时，compactor input 不得显著大于 ordinary
  run input material，不允许通过重复 current input / raw evidence 造成 provider 超窗。
- 必须确定 reactive compact 的分段语义：provider overflow 后冻结 ordinary input material list，优先压缩 older prefix，
  保留 recent raw turns 与 current input anchor；必要时多 pass，超过 policy 上限 fail closed。
- 必须确定长会话 structured memory 不可 append-only：`pinned_state` 是 materialized current state；assumptions / open
  questions 需要 merge / resolve / expire；episode summaries 需要 rollup；`evidence_backed_facts` 需要 bounded working set。
- 必须确定 P12.6 smoke success signal：至少覆盖 no-compaction recent raw turns continuity、post-compaction evidence-backed fact
  reuse、长 user input minimum preserve、长章节 tool result extraction 不依赖 preview、长期多次 compact 后 memory bounded。

交付物：
- updated `docs/host/design.md`
- updated `docs/host/implementation-control.md`
- handoff implementation-ready plan
- plan review / fix / re-review artifacts
- implementation slices
- focused tests、integration smoke、pyright、README sync

建议 slice 切分：
- Slice 1: Design Truth Rewrite And Contract Pruning，删除 / 替换 P12.5 中不符合讨论稿裁决的概念与契约。
- Slice 2: Compact Material Pack Builder，按 stable / history / evidence / current input anchor 生成去重 JSON payload。
- Slice 3: LLM Compactor JSON Schema And Accept Barrier，产出 episode summary、pinned patch、evidence-backed fact candidates、
  working assumption / open question candidates 与 minimum preserve items。
- Slice 4: Memory Projection Redesign，物化 materialized pinned state、bounded evidence-backed facts working set、bounded
  assumptions / open questions、episode summary rollup 与 recent continuity。
- Slice 5: Context Governance Proactive / Reactive Compaction Wiring，修复主动 compact duplication，落地 reactive segmented
  compact / recovery dispatch fail-closed。
- Slice 6: RunInputBuilder Rendering And Public Smoke，验证 compact 前后 continuity / facts / minimum preserve / long-session boundedness。
- Slice 7: README Sync, Aggregate Validation And Deepreview。

验证要求：
- unit tests: compact material pack 不包含 EventLog ledger wrapper，不重复 current input，不重复同一 raw tool result，且 prompt-local
  evidence labels 可映射到 canonical `TOOL_RESULT_ACCEPTED` refs。
- unit tests: LLM compactor accept barrier 拒绝无 evidence refs 的 `evidence_backed_fact_candidates`，拒绝引用不存在 label，
  拒绝 episode summary 冒充 evidence-backed fact。
- unit tests: memory projection 不向 LLM 渲染 pinned patch log，不 append-only 渲染 assumptions / open questions /
  evidence-backed facts / episode summaries，working set 受 policy 约束。
- integration tests: Run 1 工具返回收入 / 毛利，Run 2 问毛利率；未 compact 时靠 recent raw turns / available context 成功。
- integration tests: 两轮完成后触发 compact，后续 Run 能基于 `evidence_backed_facts` 稳定复用已确认财务事实，不重新依赖旧 raw turns。
- integration tests: 长 user input compact 后，下一轮“第二个因素”可通过 minimum preserve item 正确解析，不保留完整原文。
- integration tests: 长章节 tool result 进入 compact material pack 时不使用 `result_preview`，fact extraction 基于 raw accepted evidence block。
- integration tests: reactive provider overflow path 能通过分段 compact / recovery dispatch 收敛；超过 `max_reactive_compactions_per_run`
  后 fail closed。
- smoke: `utils/smoke_host_public_multiturn.py` 或 P12.6 专用 smoke 覆盖 proactive compact 不因重复 prompt 超窗失败。
- pyright: affected host / tests pass with no new or expanded errors。
- docs: `dayu/host/README.md`、`dayu/README.md`、`dayu/config/README.md`、`tests/README.md` 按触发规则同步。

退出条件：
- `docs/host/design.md` 已完成 Conversation Memory / Context Governance 相关章节重写，并与讨论稿稳定裁决一致。
- Compactor input / output 边界不再依赖 EventLog range dump、Host ledger wrapper、`result_preview` 或 Host provenance key 作为
  LLM 语义输入。
- Conversation Memory 能在 compact 前、compact 后、长 user input、长 tool result 与长会话多次 compact 场景下保持 bounded、
  evidence-backed、可审计且可解释。
- P12.6 smoke / integration tests 覆盖成功信号，affected tests、full pyright 与 `git diff --check` PASS。
- Aggregate deepreview from at least two review Agents PASS；control_doc records residual risks with owners。
- User authorization applies: once `ready-to-open-draft-PR` is reached, controller may automatically enter draft PR gate and proceed to
  `draft-PR-pass`。

后续依赖：
- 真实财报工具需要保证 tool result accept path 提供足够可读 raw evidence / source locator；具体财报工具质量归后续 Fins /
  tool provider work unit。
- long-term retrieval、cross-session research memory、public memory edit / reset / forget API 仍归后续独立 phase。
- 大 session rebuild performance 可作为 P12.6 后续 hardening owner 或另立 production hardening work unit，但不得阻塞 P12.6
  的 compact I/O 与 memory semantics 正确性。

### Phase 13. Audit / Tool Trace / Outbox Projections

目标：
- 在已稳定的 EventLog consumer framework 上实现 LogAuditSink、tool trace hot / cold storage、Outbox terminal delivery queue projection，以及 concrete Outbox read / drain API 与离线 terminal delivery smoke。

对应设计章节：
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §14.1 Tool Trace Hot / Cold Storage
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

前置条件：
- Phase 8 Projection Core / Host Event Stream / Minimal Read Model 已完成。
- Phase 6 ToolRuntime diagnostic refs 已完成。
- Core Host Public Interface Freeze 已生效：P13 不得修改、删除或重定义现有 `open_host(options)`、`OpenHostOptions` 现有字段、`Host` public handle 方法、public request / response dataclass 字段、`watch_session_events(session_id)` live-only 语义或 `HostEvent` terminal final answer view。

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
- 不把 Outbox 合并进 `watch_session_events(...)`，不为 live watch 增加 cursor / replay 参数，不把 Outbox 变成完整 timeline / progress / reasoning 补读接口。

关键设计问题：
- 必须确认 tool trace hot JSON 与 cold JSONL 的最小字段，以及 provider request id / operation context refs 的查询口径。
- 必须确认 Outbox item identity、UI / Service seen cursor 推荐语义、concrete Outbox read / drain API shape，以及 Outbox drain 与随后 / 并发 session live watch attach 的去重 / 防漏窗口。
- Outbox read / drain API 是 Core Host Public Interface Freeze 之后唯一已知允许的 additive public extension；必须先经 design / plan gate 明确 shape、幂等、cursor / watermark、dedupe 与 Service ownership，且不得改变既有 Host core public contract。
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
- Slice 3: OutboxSink, terminal delivery queue projection, concrete read / drain API, offline terminal delivery smoke。

验证要求：
- unit tests: sink checkpoint idempotency、sink retry、audit / trace / outbox projection rebuild、outbox item idempotency、read / drain cursor and dedupe semantics。
- integration tests: terminal EventLog -> audit / tool trace / outbox；sink failure 不影响 Run terminal；离线 terminal 补读后再 attach `watch_session_events(...)` 不漏投、不重复展示同一 terminal answer。
- pyright: projection sink modules 通过。
- docs: Host README / tool trace analysis docs 按触发规则同步。

退出条件：
- Audit、Tool Trace、Outbox 均能从 committed EventLog 独立追平；任一 sink 失败只造成 projection lag 或 sink-local error，不影响 Host command path。Service 可通过 concrete Outbox read / drain API 补读离线 terminal/final answer 增量，并用 terminal identity 与 session live watch 去重。

后续依赖：
- 后续 phase 可依赖的稳定契约：audit JSONL、tool trace hot / cold、outbox terminal delivery queue、concrete Outbox read / drain API 与离线 terminal delivery smoke baseline。
- 需要追踪到后续 phase 的事项：Service / UI channel delivery、外部 audit 系统和长期归档策略不属于本 phase。

### Phase 14. RemoteProxy / RemoteStub

目标：
- 在 LocalProxy 语义基准上实现 RemoteProxy / RemoteStub transport substitution，保持 Host 治理真源、execution_id late event rejection 与 tool fact accept ack。

当前状态：
- 暂不实现；deferred 到 GitHub Issue #73。Phase 15 不等待本 phase 完成。

对应设计章节：
- `docs/host/design.md` §17 WorkerProxy / EngineWorker
- `docs/host/design.md` §18 ToolRuntime
- `docs/host/design.md` §27 Host Lifecycle / Recovery

前置条件：
- Phase 5 LocalProxy semantic baseline 已完成。
- Phase 6 ToolRuntime accept barrier 已完成。
- Phase 11 recovery 与 positive orphan proof 已完成。
- Core Host Public Interface Freeze 已生效：P14 只能替换 Host 内部 worker transport，不得修改、删除或重定义现有 `open_host(options)`、`OpenHostOptions` 现有字段、`Host` public handle 方法、public request / response dataclass 字段、`watch_session_events(session_id)` live-only 语义或 `HostEvent` terminal final answer view。

进入条件：
- 确认 remote phase 只定义并实现 transport，不改变 design 的 remote semantic contract。

范围：
- 允许修改：RemoteProxy、RemoteStub、remote event identity mapping、remote cancellation propagation、remote tool accept ack transport。
- 禁止修改：Host 状态 ownership、EventLog append ownership、Attempt takeover 语义、wire protocol 污染设计文档。

不做：
- 不实现远端 worker 自治恢复。
- 不保证 exactly-once 远程物理执行。
- 不引入远端 lease / fencing owner。
- 不新增 remote 专用 Host public command、remote 专用 Service-facing handle method 或 remote 专用 `OpenHostOptions` 必填字段；remote provider / endpoint / transport 装配必须通过既有 construction-time baseline、worker factory 或内部 composition contract 承接，若发现确需 public extension 必须先回到用户讨论。

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
- Phase 8 projection core、Phase 11 recovery、Phase 13 Audit / Tool Trace / Outbox 已完成。
- Phase 14 RemoteProxy / RemoteStub 已明确 deferred 到 Issue #73；P15 不以 remote completion 为进入前置。
- Core Host Public Interface Freeze 已生效：P15 不得修改、删除或重定义现有 `open_host(options)`、`OpenHostOptions` 现有字段、`Host` public handle 方法、public request / response dataclass 字段、`watch_session_events(session_id)` live-only 语义或 `HostEvent` terminal final answer view。

进入条件：
- 确认第一版 release / PR 前必须关闭的 residual risk 与可接受 non-goals。
- 先区分 release-blocking 与 follow-up items；如 projection rebuild tooling、stress / smoke tests 或 docs closeout scope 过大，必须拆出独立 phase 或后续 work unit。
- 必须复核 Phase 4 已冻结的 `purge_session` public signature / `PurgeSessionResult` / idempotency contract；如需变更，先回到 Public API contract 讨论。
- 必须复核 P13 additive Outbox read / drain API 是否已独立冻结；P15 只能验证和硬化，不得借 production closeout 重塑 Outbox 或 Host core public surface。

范围：
- 允许修改：`purge_session` command implementation、purge delete ranges、shared artifact ref check、projection rebuild tooling、audit tombstone query support、stress / smoke tests、README sync。
- 禁止修改：新增 archive_session、长期 memory API、重型消息系统、服务化 DB。

不做：
- 不实现 archive_session。
- 不实现长期 retention policy UI。
- 不把第一版 non-goals 偷偷变成实现目标。
- 不新增 `archive_session`、长期 memory edit / reset / forget、public payload reader、`wait_final_answer(...)`、`get_run_result(...)` 或其它绕过 terminal `HostEvent` / Outbox terminal item 的 Service-facing捷径。

关键设计问题：
- 必须确认 purge 对 EventLog / payload / projection / outbox / tool trace hot data / audit JSONL 的最终清理矩阵。
- 必须确认第一版 residual risks 的接受、后续 issue 或当前修复归属。
- 必须确认 purge / tombstone / projection rebuild slices 的 release-blocking 范围；remote-dependent smoke 不进入当前 P15 scope，继续归 Issue #73。

交付物：
- phase design refinement
- handoff implementation-ready plan
- implementation slices
- tests
- docs update

建议 slice 切分：
- Slice 1: purge delete matrix and tombstone audit。
- Slice 2: projection rebuild / consistency checks。
- Slice 3: multi-process / recovery production smoke；remote-dependent smoke deferred 到 Issue #73。
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

本区只保留仍未完成且带明确 owner / destination 的项目。已完成 phase 的过程流水、已接受 review finding、已修复或已明确不修复的条目不再保留在本区；对应证据见 `历史记录` 与 `docs/reviews/` artifacts。

#### Phase 12.5 Conversation Memory design tracking

Owner / destination：Phase 12.5 design discussion / plan gate。

- evidence_backed_fact contract：已裁决旧 `verified_facts` 应迁移为 `evidence_backed_facts` 或等价 typed view；最小 contract 是 `claim_text + accepted evidence_refs`，Host 不理解 source / locator 语义。
- accepted evidence envelope：已裁决 tool provider 不直接生成最终 memory facts；ToolRuntime / tool result accept path 负责记录 accepted evidence envelope，至少保证每个 accepted tool result 有稳定 evidence id。
- recent raw turns 语义：已裁决保留 `recent_raw_turns_floor` 名称；其职责是最近 raw turns 的最低保留数量，聚焦交互连续性，而非财务事实保真。
- minimum preserve：已裁决为 compact structured output 中的 bounded continuity item；保护指代解析，不保留整段长输入，不承担事实真源职责。
- no fallback facts：已裁决缺少可接受 `evidence_backed_fact` candidate 时只记录 diagnostic / repair outcome，不合成 neutral fallback fact。
- compaction 后 confirmed facts 不漂移：已裁决 compact 同一次 structured JSON proposal 生成 episode summary candidate、pinned state patch candidate 与 `evidence_backed_fact_candidates`；episode summary 不得替代事实真源。
- 财报工具接入后续：P12.5 可冻结 accepted evidence envelope contract；真实财报工具保证 tool result accept path 可形成 evidence envelope 的迁移 owner 为后续 Fins / tool provider work unit，除非用户明确扩大 P12.5 scope。

#### Service / UI / workflow integration tracking

Owner / destination：后续 Service / UI / workflow integration work unit。

- 真实 Service / CLI / Web / GUI 接入 ScenePrepare + ConfigLoader + ToolsDiscovery，并映射到 `open_host(options)` / `SubmitFollowupRequest`。
- Service 在 Host 外部完成 override 优先级合并、runner / agent typed mapping、tool bundle 子集选择、prompt 注入、artifact/parser/retry/replay/stop policy。
- Service 若需要 model allow-list、旧 runtime budget mapping 或 scene-specific profile enforcement，必须通过 ConfigLoader typed profile 与 Service mapping 实现，不得回退为 manifest raw patch。
- Service / UI contract tests 必须证明不绕过 Host public API。

#### Fins / financial tool provider tracking

Owner / destination：后续 Fins / tool provider work unit。

- 真实财报工具 provider 接入 P12 ToolsDiscovery 输出，保持工具包显式 provider callable / entry point，不让 Host 扫描业务工具。
- P12.5 若冻结 accepted evidence envelope / evidence_backed_fact contract，财报工具需保证 tool result accept path 可形成 accepted evidence envelope；最终 `evidence_backed_facts` 由 Host-governed compact extraction 生成。
- 财报仓储仍由 `dayu.fins.storage` 协议 owner 负责；Host memory 不保存财报原文，不解释财报业务语义。

#### Phase 14 RemoteProxy tracking

Owner / destination：GitHub Issue #73；未来重新进入 Phase 14 design / plan gate。

- 远程执行只传输 immutable attempt snapshot 与 EngineEvent stream；RemoteStub 不拥有 Host durable truth。
- 远程 worker disconnect、late event、duplicate event、cancel propagation、tool accept ack over remote 与 remote wire protocol 细节均归 Phase 14。
- exactly-once 物理执行仍为第一版非目标；Host 只保证 durable event identity、stale execution rejection 与 diagnostic。

#### Phase 15 Retention / Purge / Production Hardening tracking

Owner / destination：Phase 15 Retention / Purge / Production Hardening，或在 P15 前拆出独立 hardening PR。

- P15-S4 audit fail-before-success：P15-S3 已接通 public purge，但 tombstone 暂无 audit JSONL ref/digest；S4 必须保证 public
  `purge_session` 成功返回前已经追加 purge tombstone audit JSONL line，并把 ref/digest 纳入 tombstone，禁止留下 audit-pending
  successful tombstone 路径。
- `purge_session` destructive cleanup、audit tombstone、payload / memory / projection / outbox / tool trace 清理、projection rebuild tooling 与 retention matrix。
- startup / recovery / crash E2E 压测、watch 轮询性能、SQLite 多进程写入压力、schema bootstrap / DDL 原子性、after-commit 多错误聚合、projection catch-up 批处理与 heavy sink runner。
- dispatch / recovery production hardening：dispatch owner 写入时机与 owner id 真源已由 PR 68 post-draft fullrepo B1 / B2 fix 修复；剩余项为 liveness proof 压测、promotion deferred result 语义、startup timeout closeout diagnostic 字段、recovery orphan proof 覆盖、`ActiveWorkerRegistry` asyncio path 同步原语、`cancel_all` 快照窗口与 scheduler close task-cancel defense-in-depth 验证，以及 worker startup / fatal stream 事件序列与 cancel / closeout diagnostic 矩阵。
- Host governance terminal taxonomy：当前设计明确 hard threshold / compact failure 使用 attempt-free `RUN_FAILED`，EventLog reason / payload 区分 `pre_dispatch_context_governance`；`RunStatus.REJECTED` 或 `rejected_by_governance` 属于后续 schema / state-machine design gate，不作为 PR 68 blocking fix。
- scheduler close / recovery residual：scheduler close 不 drain 剩余 dispatch queue、`WAITING` startup recovery 当前仅 diagnostic、normal close 与 orphan recovery 的更多崩溃点 E2E 均归 Phase 15 / lifecycle hardening。
- active cancel observability：`LocalWorkerHandle.on_cancel` 是 Host lifecycle cancellation token 之后的 best-effort hook；`_propagate_active_worker_cancel` 异常日志补充 `exc_info` / message、active cancel watchdog 与 post-cancel timeout policy 归 Phase 15 / lifecycle hardening。
- durable production hardening：幂等写入 / EventLog append 并发唯一键冲突分类、`ensure_session` 幂等语义、projection checkpoint CAS、memory snapshot CAS、WAL checkpoint 策略、rollback failure diagnostic、read/write busy retry 策略拆分、SQLite read connection stale-read 语义与关键 durable CAS / state / liveness direct unit tests。
- Context Governance production hardening：真实异步 / production LLM compactor adapter、provider-specific tokenizer / sizing、compact failure 用户可见策略矩阵、proactive / reactive compact failure E2E、post-compact budget estimate 与 compaction semantic repair retry 默认策略。
- Context Governance reactive overflow hardening：不引入 raw evidence aggregate prompt budget guard，不让不准 token 估算阻断 reactive recovery；reactive path 通过真实 recovery dispatch / Engine overflow 闭环最多执行 `max_reactive_compactions_per_run` 次 compact，默认上限为 2，超过上限后 fail closed。
- runtime lane production hardening：close/acquire race、stale claim cleanup 压测、heartbeat / TTL 配置校验、runtime log import side effect，以及 shielded wait / indefinite wait 取消与超时矩阵。
- ConfigLoader production hardening：`extends` 递归深度、循环诊断、project path policy 文档与 schema validation error taxonomy。
- contracts strict validation、redaction / sensitive error taxonomy、Engine / compaction redaction helper consistency、README/docs correctness cleanup。

#### ToolRuntime hardening tracking

Owner / destination：后续 ToolRuntime hardening work unit；若影响 memory fact contract，则先进入 P12.5 design gate。

- `TruncationManager` / `fetch_more` cursor lifecycle：oversized visible portion、cursor 不丢失、TTL 清理、run-scoped `scope_token`、`text_lines` / `list_items` / `binary_bytes` 边界。
- `TruncationManager` / `fetch_more` cursor storage cap：cursor dict 增长上限、TTL 清理压测与 overflow diagnostic。
- duplicate governance concurrency：同一 Run 内同工具同 normalized arguments 并发调用只执行一次，第二个调用复用或按 policy 阻断，且不引入死锁。
- duplicate governance key scope：attempt_id / attempt boundary 是否进入 duplicate key 需独立裁决，不能让跨 Attempt 重试误用旧治理记录。
- ToolRuntime diagnostic matrix：ordinary accept failure、duplicate / reuse / governed failure、awaiting timeout 与非 awaiting failure 的 diagnostic refs 传播一致性。
- ToolRuntime cross-Attempt production semantics：run-local duplicate governance 是否跨 Attempt 复用、ToolRuntime 状态是否应从 worker-local 拆出为 per-Attempt durable / runtime owner、hot-path payload digest 省略导致的额外 resolution round-trip，均归后续 ToolRuntime hardening；若影响 memory fact contract，先进入 P12.5 / conversation memory design gate。
- `ToolFactAcceptCandidate` / accept candidate 结构清理：只允许机械拆分和 focused tests；若改变工具治理语义，必须重新进入 ToolRuntime design gate。

#### Wait adapter hardening tracking

Owner / destination：后续 wait adapter / Phase 7 follow-up / Phase 15 production polling scale work unit。

- Callback endpoint / auth / replay、poller 后台 loop、backoff、in-flight fencing、adapter retry、`LIMIT` / `CANCELLED` abandon 退避。
- External job physical cancel / revoke / abandon 为 best-effort adapter 能力，不影响 Host EventLog 和 Run 终态。
- waiting iteration_id / digest 语义、`resolve_semantic_digest is None` defensive handling、idempotent replay error taxonomy、late result diagnostic / ack state hardening 均需独立 schema / contract gate。

#### Engine runner / provider hardening tracking

Owner / destination：后续 Engine runner / provider abstraction hardening work unit。

- OpenAI streaming tool call aggregator index fragmentation、provider delta normalization、partial delta retry taxonomy、stream idle heartbeat / timeout validation 与 non-stream / stream error object consistency。
- SSE fatal tool-call partial completion event contract、context overflow error-body read failure 分类与 provider error diagnostic safety。
- runner event contract cleanup：`PartialToolCallSummary` export 路径收敛与其它非行为性 re-export 清理。
- Provider-specific state neutralization，例如 Gemini provider state 合约是否需要统一为 provider-neutral tagged structure。
- Engine import boundary automation：明确允许的 runtime / contracts import 白名单，防止 Engine 反向理解 Host memory / governance。
- Engine runner injection / provider abstraction cleanup 不得让 Engine 理解 Host memory、governance 或 durable state。
- SSE / tool call aggregation cleanup：`_ChunkAggregationKind` 仍为轻量值对象而非枚举、未知 `finish_reason` fallback 为 STOP、OpenAI-compatible provider delta / finalization diagnostics 继续归 Engine runner hardening；不得把 Host governance 语义下沉到 Engine。

#### Durable / layering cleanup tracking

Owner / destination：后续 Host durable layering cleanup work unit；若触及 public contract，先回到 design gate。

- durable layer dependency cleanup：拆分 row primitive、public type owner 与 import boundary tests，确保 durable 层不反向依赖上层业务模块。
- durable bootstrap、schema CHECK hardening、terminal CAS null-check 一致性、session lifecycle observability 与 close-session active Run 可观测性。
- import boundary helper consolidation：保持 Engine / Host / runtime / contracts 边界测试可读、单一 helper 真源与反向依赖禁止。
- validation / JSON / redaction helper cleanup：在不改变业务语义的前提下收敛 `_require_non_empty_text`、Host JSON serialization helper、secret redaction helper 与 token estimate helper 的重复实现。
- weak typing / boundary automation：当前 `tests/service/test_weak_typing_guard.py` 主要覆盖 Service；是否新增 `dayu.host/` weak typing guard、Engine / Host import allow-list 自动化、review-time helper 清单检查，归后续 test / architecture hardening。

#### Conversation Memory / Compaction hardening tracking

Owner / destination：后续 Conversation Memory / Context Governance hardening work unit；若改变 P12.5 stable contract，先回到 design gate。

- `working_assumptions` 生产者语义：若保留该 snapshot 字段，必须明确由哪些 compact / user / diagnostic event 生成；若不保留，需通过 schema gate 删除。
- fact-candidate-only validation failure：`CONTEXT_COMPACTED` 中 fact candidates 非法但其它 compact output 合法时，是否 partial materialize、fail compact 或写审计 diagnostic，需独立语义裁决。
- raw assistant continuity：`RAW_ASSISTANT_TURN` 与 `ASSISTANT_CONCLUSION` 的职责、floor 保护和后续 Run continuity 语义需要统一。
- LLM compaction proposal parsing：消除 `_parse_proposal` unchecked cast，保持 JSON structured output 到 typed proposal 的 fail-closed validation。
- `_payload_with_terminal_summary` text policy divergence：`durable/memory.py` 与 `run_input.py` 的 terminal summary text policy 仍有双实现分歧，后续应统一 helper 或明确差异；改变 memory replay 行为前需 focused tests。
- `OpaqueEvidenceRef` / evidence validation hardening：`OpaqueEvidenceRef.__post_init__` 未直接强制 Host-neutral kind allowlist，`EvidenceBackedFactCandidate.__post_init__` 对 `evidence_refs` 格式依赖后续 quality / payload validator 防线；归 Conversation Memory / Context Governance hardening。
- pinned state / confirmed subjects cleanup：`PinnedStateView.confirmed_subjects` 去重 / 校验策略、`open_questions` docstring 与实际 normalized de-dup 行为、`working_assumptions` 生产者语义需统一，若改变 stable memory contract 需设计 gate。
- compaction material readability / chunking：`_readable_query_text` 目前主要提供 tool_call_id，query 参数可读性、evidence chunking record 边界感知、source_refs / locator_refs richer projection 归后续 compaction material hardening。
- public smoke maintenance：`utils/smoke_host_public_conversation_memory.py` 的 `_compact_pressure_reserve_tokens` 死分支、pressure padding 重复计算、manual smoke LLM 格式漂移风险与真实 Fins 路径未覆盖，归后续 public smoke / performance hardening；`smoke_host_public_conversation_memory` 已纳入 scene asset migration inventory。
- public memory scenario smoke residuals：`utils/smoke_host_public_conversation_memory_scenarios.py` 只通过 public answer 间接验证 conversation memory 语义，不读取 durable DB / EventLog / memory 表 / compact payload；`--suite all --pressure-mode off` 已通过；`_PROVIDER_IMPORT_DISPLAY_PATH` 继承 `__main__` display path pattern，若未来改为解析 import path 的 discovery 模式，需与既有 `smoke_host_public_multiturn.py` 一并统一。

## 历史记录

### 2026-05-29 Phase 15 design discussion completed

用户要求按 `$phaseflow` 推进 Phase 15，并授权到达 `ready-to-open-draft-PR` 后自动进入 draft PR gate。Controller 从 clean
`main` 创建工作分支 `feat/host-phase15-retention-purge-hardening`。Phase 15 design discussion 已完成，artifact 为
`docs/reviews/phase15-design-discussion-controller-20260529.md`。结论：`docs/host/design.md` 已足以支撑进入 plan，
无需先修改设计真源；P15 plan 必须在冻结 public API envelope 内实现 `purge_session` destructive cleanup、purge tombstone、
audit JSONL retention、projection cleanup / rebuild confidence 与 local production hardening，remote-dependent smoke 继续归
Issue #73。

Planning specialist AgentCodex 已生成 handoff implementation-ready plan：
`docs/host/phase15-retention-purge-production-hardening-plan.md`。Plan review artifacts 为
`docs/reviews/phase15-plan-review-mimo-20260529.md` 与 `docs/reviews/phase15-plan-review-ds-20260529.md`。Controller
adjudication artifact 为 `docs/reviews/phase15-plan-review-controller-adjudication-20260529.md`，裁决接受 8 个 plan
clarity / FK / idempotency / audit / projection reset finding 并进入 plan fix。Plan fix artifact 为
`docs/reviews/phase15-plan-fix-codex-20260529.md`。Plan re-review artifacts 为
`docs/reviews/phase15-plan-rereview-mimo-20260529.md` 与 `docs/reviews/phase15-plan-rereview-ds-20260529.md`，两份 re-review
均确认 ADJ-001 到 ADJ-008 全部已修复、无新 blocker，plan 现为 code-generation-ready。Accepted plan commit 为
`5fae495`。

Slice P15-S1 Purge Tombstone Schema And Durable Primitives implementation 已完成。Implementation artifact 为
`docs/reviews/phase15-s1-implementation-codex-20260529.md`。Code review artifacts 为
`docs/reviews/phase15-s1-code-review-mimo-20260529.md` 与 `docs/reviews/phase15-s1-code-review-ds-20260529.md`；MiMo 为
PASS / 0 findings，DS finding 经 Controller adjudication artifact
`docs/reviews/phase15-s1-code-review-controller-adjudication-20260529.md` 裁决接受 2 项。Fix artifact 为
`docs/reviews/phase15-s1-fix-codex-20260529.md`。Re-review artifacts 为
`docs/reviews/phase15-s1-rereview-mimo-20260529.md` 与 `docs/reviews/phase15-s1-rereview-ds-20260529.md`，两份 re-review
均确认 S1-ADJ-001 / S1-ADJ-002 已修复且无新 blocker。Controller 本地验证：
`pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py tests/host/test_weak_typing_guard.py -q` 为
31 passed；`python -m pyright dayu/host/durable/schema.py dayu/host/durable/purge.py tests/host/test_durable_schema.py
tests/host/test_purge_session.py` 为 0 errors。README 检查结论：S1 未接 public `purge_session`，现有
`dayu/host/README.md` structured unsupported 描述仍正确；`tests/README.md` 无需机械更新。Accepted S1 commit 为
`f607655`。

Slice P15-S2 Delete Matrix Transaction Helper implementation 已完成。Implementation artifact 为
`docs/reviews/phase15-s2-implementation-codex-20260529.md`。Code review artifacts 为
`docs/reviews/phase15-s2-code-review-mimo-20260529.md` 与 `docs/reviews/phase15-s2-code-review-ds-20260529.md`；Controller
adjudication artifact 为 `docs/reviews/phase15-s2-code-review-controller-adjudication-20260529.md`，裁决接受 5 项
projection reset / maintainability / regression-test finding，拒绝 2 项非阻塞 test expansion。Fix artifact 为
`docs/reviews/phase15-s2-fix-codex-20260529.md`。Re-review artifacts 为
`docs/reviews/phase15-s2-rereview-mimo-20260529.md` 与 `docs/reviews/phase15-s2-rereview-ds-20260529.md`，两份 re-review
均确认 S2-ADJ-001 到 S2-ADJ-005 已修复且无新 blocker。Controller 本地验证：
`pytest tests/host/test_purge_session.py tests/host/test_payload_store.py tests/host/test_projection_read_model.py
tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q` 为
112 passed；`python -m pyright dayu/host/durable/purge.py dayu/host/durable/payload.py dayu/host/durable/read_model.py
dayu/host/durable/memory.py dayu/host/durable/tool_trace.py dayu/host/durable/outbox.py dayu/host/durable/audit.py tests/host`
为 0 errors。README 检查结论：S2 仍只新增 internal durable transaction helper，public `purge_session` 尚未接线，
README 暂不更新。Accepted S2 commit 为 `dac3a85`。

Slice P15-S3 Public Command Wiring And Read-after-purge Semantics implementation 已完成。Implementation artifact 为
`docs/reviews/phase15-s3-implementation-codex-20260529.md`。Code review artifacts 为
`docs/reviews/phase15-s3-code-review-mimo-20260529.md` 与
`docs/reviews/phase15-s3-code-review-ds-20260529.md`；MiMo PASS / 0 findings，DS 为 PASS / 0 blocking findings。
Controller adjudication artifact 为 `docs/reviews/phase15-s3-code-review-controller-adjudication-20260529.md`，裁决无需
S3 fix pass；DS audit fail-before-success observation 接受为 S4 handoff risk。Controller 本地验证：
`pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py
tests/host/test_open_host_runtime.py tests/host/test_purge_session.py -q` 为 69 passed；`python -m pyright
dayu/host/command.py dayu/host/open_host.py dayu/host/read_api.py tests/host` 为 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。README 检查结论：S3 已让包根 `purge_session` 从 structured unsupported 变为可用，已同步
`dayu/host/README.md` 与 `tests/README.md` 的当前事实。Accepted S3 commit 将在本条记录提交后由 git commit 记录。

### 2026-05-29 PR 68 merged and Phase 13 started

用户确认 PR 68 已 merge，并要求进入 Phase 13。Controller 已核验 PR 68 state 为 `MERGED`，merge commit 为
`b9bd625`，本地 `main` clean 且包含该 merge commit。Phase 12.5 / 12.6 conversation memory、compaction
continuity、public memory smoke 与 public memory scenario smoke 的 draft PR gate 工作已归档为完成；PR 68 post-draft
fullrepo residuals 与 scenario-smoke residuals 继续以 `Open Questions 与风险追踪` 中已分配 owner 的条目为准。

Controller 已从 clean `main` 创建工作分支 `feat/phase-13-audit-trace-outbox`。当前 gate 切换为 Phase 13 discussion /
design refinement；尚未进入 plan、implementation 或 review gate。Phase 13 必须先确认 Audit / Tool Trace / Outbox 只是
projection / sink，不参与 Host command path 成功条件，不反向成为 recovery、resume、memory 或 Run 状态迁移真源。

用户随后确认 Phase 13 design discussion 裁决：Audit / Tool Trace / Outbox 保持 projection / sink；Outbox 只补离线
terminal / final answer notification，不补完整 timeline，不改变 `watch_session_events(...)` live-only 语义；Outbox
read / drain API 作为唯一 additive public extension 进入 Phase 13 plan；LogAuditSink 第一版为 append-only JSONL；
Tool Trace 第一版为 hot JSON projection + cold JSONL writer。Controller adjudication artifact 为
`docs/reviews/phase13-design-discussion-controller-adjudication-20260529.md`。当前 gate 进入 Phase 13 handoff
implementation-ready plan。

Planning specialist AgentCodex 已生成 handoff implementation-ready plan：
`docs/host/phase13-audit-tool-trace-outbox-plan.md`。Plan 声明 blocking open questions 为 None，建议 slices 为：
LogAuditSink JSONL、Tool Trace hot JSON / cold JSONL、OutboxSink durable projection、Public Outbox read / drain API
and offline smoke。Controller 已将当前 gate 推进为 Phase 13 plan review；待 AgentMiMo 与 AgentDS 双路 review。

Phase 13 plan review 已完成。MiMo artifact 为 `docs/reviews/phase13-plan-review-mimo-20260529.md`，verdict 为
PASS with recommended findings；DS artifact 为 `docs/reviews/phase13-plan-review-ds-20260529.md`，verdict 为
CONDITIONAL PASS with one blocking finding。Controller adjudication artifact 为
`docs/reviews/phase13-plan-review-controller-adjudication-20260529.md`。当前 gate 回到 Phase 13 plan fix；
accepted blocking finding 为 `read_outbox_terminal_items` side-effect boundary 自相矛盾。Accepted plan clarifications
包括 Outbox dedupe / idempotency key 边界、purge / retention Phase 15 owner、tool trace diagnostic whitelist、audit marker
table naming、RUN_LOST skip 语义、tool trace query helper pagination 与 projection-lag anti-leak test。

Planning specialist 已修复 plan 并输出 fix artifact：`docs/reviews/phase13-plan-fix-codex-20260529.md`。Fix 修改
`docs/host/phase13-audit-tool-trace-outbox-plan.md`，覆盖全部 accepted findings；`git diff --check` passed。
当前 gate 进入 Phase 13 plan re-review。

Phase 13 plan re-review 已通过。MiMo re-review artifact 为
`docs/reviews/phase13-plan-rereview-mimo-20260529.md`；DS re-review artifact 为
`docs/reviews/phase13-plan-rereview-ds-20260529.md`。两者均确认 accepted findings fixed，verdict PASS。
Controller re-review adjudication artifact 为
`docs/reviews/phase13-plan-rereview-controller-adjudication-20260529.md`。当前 gate 进入 accepted plan commit。

Accepted plan local commit 已创建：`9e79f5e` (`gateflow: accept plan for phase 13 projections`)。当前 gate 进入
Phase 13 implementation，下一步派发 Slice 1 `LogAuditSink JSONL` implementation。

Phase 13 Slice 1 `LogAuditSink JSONL` implementation 已完成。Implementation artifact 为
`docs/reviews/phase13-slice1-implementation-codex-20260529.md`。Changed files:
`dayu/host/audit.py`、`dayu/host/durable/audit.py`、`dayu/host/durable/schema.py`、`dayu/host/open_host.py`、
`tests/host/test_audit_sink.py`、`tests/host/test_durable_schema.py`。Validation: focused pytest 22 passed；
`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。当前 gate 进入 Slice 1 code review。

Phase 13 Slice 1 code review 已完成。MiMo artifact 为
`docs/reviews/phase13-slice1-code-review-mimo-20260529.md`；DS artifact 为
`docs/reviews/phase13-slice1-code-review-ds-20260529.md`。两路 verdict 均为 PASS，无 blocking findings。
Controller adjudication artifact 为
`docs/reviews/phase13-slice1-code-review-controller-adjudication-20260529.md`。MiMo P3 与 DS Minor findings 均裁决为
non-blocking residual / later hardening，不要求当前 fix pass。当前 gate 进入 accepted Slice 1 commit。

Accepted Slice 1 commit 已创建：`7432f02` (`gateflow: accept phase 13 slice 1`)。当前 gate 进入 Phase 13
Slice 2 `Tool Trace Hot JSON / Cold JSONL` implementation。

Phase 13 Slice 2 `Tool Trace Hot JSON / Cold JSONL` implementation 已完成。Implementation artifact 为
`docs/reviews/phase13-slice2-implementation-codex-20260529.md`。Changed files:
`dayu/host/tool_trace.py`、`dayu/host/durable/tool_trace.py`、`dayu/host/durable/schema.py`、`dayu/host/open_host.py`、
`tests/host/test_tool_trace_projection.py`、`tests/host/test_tool_trace_queries.py`、`tests/host/test_durable_schema.py`。
Validation: focused pytest 25 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。
当前 gate 进入 Slice 2 code review。

Phase 13 Slice 2 code review 已完成。MiMo artifact 为
`docs/reviews/phase13-slice2-code-review-mimo-20260529.md`；DS artifact 为
`docs/reviews/phase13-slice2-code-review-ds-20260529.md`。两路 verdict 均为 PASS，无 blocking findings。
Controller adjudication artifact 为
`docs/reviews/phase13-slice2-code-review-controller-adjudication-20260529.md`。低优先级 findings 均裁决为
non-blocking residual / later hardening，不要求当前 fix pass。当前 gate 进入 accepted Slice 2 commit。

Accepted Slice 2 commit 已创建：`0a675a5` (`gateflow: accept phase 13 slice 2`)。当前 gate 进入 Phase 13
Slice 3 `OutboxSink Durable Projection` implementation。当前 committed Host schema version 为 12；Slice 3 如新增
outbox durable tables，必须 fresh schema bump 到 13。

Phase 13 Slice 3 `OutboxSink Durable Projection` implementation 已完成。Implementation artifact 为
`docs/reviews/phase13-slice3-implementation-codex-20260529.md`。Changed files:
`dayu/host/outbox.py`、`dayu/host/durable/outbox.py`、`dayu/host/durable/schema.py`、
`tests/host/test_outbox_projection.py`、`tests/host/test_outbox_durable.py`、`tests/host/test_durable_schema.py`。
Validation: focused pytest 26 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。
当前 gate 进入 Slice 3 code review。

AgentMiMo Slice 3 code review 已完成。Artifact 为
`docs/reviews/phase13-slice3-code-review-mimo-20260529.md`。Verdict PASS，无 blocking findings；
两个 nonblocking findings（`event_sequence` 外键冗余、边界常量测试缺失）不阻塞。下一步：AgentDS code review。

AgentDS Slice 3 code review 已完成。Artifact 为
`docs/reviews/phase13-slice3-code-review-ds-20260529.md`。Verdict PASS，无 blocking findings；两个 advisory
observations（catch-up helper 循环冗余、seen ids 较多时 scan limit 浪费）不阻塞。Controller adjudication artifact 为
`docs/reviews/phase13-slice3-code-review-controller-adjudication-20260529.md`。当前 gate 进入 accepted Slice 3 commit。

Accepted Slice 3 commit 已创建：`1a37946` (`gateflow: accept phase 13 slice 3`)。当前 gate 进入 Phase 13
Slice 4 `Public Outbox Read / Drain API And Offline Smoke` implementation。Slice 4 必须只接 additive public read/drain
API 与 offline smoke，不得引入 `OpenHostOptions` 字段、`wait_final_answer`、`get_run_result`、payload reader 或 timeline
replay API。

Phase 13 Slice 4 `Public Outbox Read / Drain API And Offline Smoke` implementation 已完成。Implementation artifact 为
`docs/reviews/phase13-slice4-implementation-codex-20260529.md`。Changed files:
`dayu/host/api.py`、`dayu/host/__init__.py`、`dayu/host/open_host.py`、`dayu/host/read_api.py`、
`tests/host/test_public_outbox_api.py`、`tests/host/test_public_offline_outbox_smoke.py`、
`tests/host/test_package_exports.py`、`tests/host/test_open_host_runtime.py`、`dayu/host/README.md`。
Validation: focused pytest 23 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check` passed。
当前 gate 进入 Slice 4 code review。

AgentMiMo 与 AgentDS Slice 4 code review 已完成。Artifacts 为
`docs/reviews/phase13-slice4-code-review-mimo-20260529.md` 与
`docs/reviews/phase13-slice4-code-review-ds-20260529.md`。Verdict 均为 PASS，无 blocking findings。Controller
adjudication artifact 为 `docs/reviews/phase13-slice4-code-review-controller-adjudication-20260529.md`。低优先级
observations 均裁决为 non-blocking residual / test-hardening，不要求当前 fix pass。当前 gate 进入 accepted
Slice 4 commit。

Accepted Slice 4 commit 已创建：`1d9e732` (`gateflow: accept phase 13 slice 4`)。Phase 13 aggregate validation
已通过：plan-listed pytest 96 passed；`python -m pyright dayu/host tests/host` 0 errors；`git diff --check`
passed。当前 gate 进入 Phase 13 aggregate deepreview。Aggregate review 必须由 AgentMiMo 与 AgentDS 独立完成；
通过并裁决后，Phase 13 才能进入 `ready-to-open-draft-PR`。

Phase 13 AgentMiMo aggregate deepreview 已完成。Review artifact 为
`docs/reviews/phase13-aggregate-deepreview-mimo-20260529.md`。Verdict：PASS with 1 BLOCKING finding。
四 slice 完整实现 plan，架构边界正确（Audit/Tool Trace/Outbox 均为 projection/sink，不反向成为 truth），
schema version 自洽，projection checkpoint/failure/idempotency 遵循框架约定，Outbox public read/drain 是唯一
additive public extension，watch_session_events 仍为 live-only，类型安全通过 pyright。
Blocking finding F001：`read_api.py` 违反 import 边界，直接导入 `dayu.host.durable.projection` 读取 Outbox
projection state；修复方案为将 projection state 读取下沉到 `durable/outbox.py` helper。
AgentDS aggregate deepreview 已完成。Review artifact 为
`docs/reviews/phase13-aggregate-deepreview-ds-20260529.md`。Verdict：PASS，无 blocking findings。Controller 复现
AgentMiMo F001：`tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth`
失败，原因是 `dayu/host/read_api.py` 直接导入 `dayu.host.durable.projection`。Controller adjudication artifact 为
`docs/reviews/phase13-aggregate-deepreview-controller-adjudication-20260529.md`，裁决 F001 为 accepted blocking。
当前 gate：Phase 13 aggregate fix；下一步派发 AgentCodex 将 projection state 查询下沉到 `dayu/host/durable/outbox.py`，
并移除 `read_api.py` 对 `dayu.host.durable.projection` 的直接依赖。

Phase 13 aggregate fix 已完成。Fix artifact 为 `docs/reviews/phase13-aggregate-fix-codex-20260529.md`。
Changed files: `dayu/host/durable/outbox.py`、`dayu/host/read_api.py`。Validation: import-boundary + public outbox +
durable outbox focused tests 10 passed；aggregate host suite with import boundary 108 passed；`python -m pyright
dayu/host tests/host` 0 errors；`git diff --check` passed。当前 gate 进入 Phase 13 aggregate re-review；必须由
AgentMiMo 与 AgentDS 确认 F001 fixed 后，才能进入 `ready-to-open-draft-PR`。

Phase 13 aggregate re-review 已完成。Re-review artifacts 为
`docs/reviews/phase13-aggregate-rereview-mimo-20260529.md` 与
`docs/reviews/phase13-aggregate-rereview-ds-20260529.md`。两路 verdict 均为 PASS，F001 fixed，无新增 blocking
findings。Controller re-review adjudication artifact 为
`docs/reviews/phase13-aggregate-rereview-controller-adjudication-20260529.md`。当前 gate：Phase 13
`ready-to-open-draft-PR`。

Accepted aggregate review commit 已创建：`85c3358` (`gateflow: accept phase 13 aggregate review`)。Phase 13
plan、implementation slices、slice reviews、aggregate validation、aggregate deepreview、aggregate fix 与 aggregate re-review
均已完成。当前 gate：`ready-to-open-draft-PR`。Residual risks / owners：JSONL 与 SQLite checkpoint 跨介质
exactly-once 归 Phase 15；Outbox drain 非 channel delivery success 归 Service / channel adapter owner；purge tombstone
audit record、outbox cleanup、tool trace cleanup、projection cleanup 归 Phase 15；external audit、long-term archival、heavy
sink runner / batch transaction hardening 归 Phase 15+ production hardening。用户已授权到达 `ready-to-open-draft-PR`
后自动进入 draft PR gate 并推进到 `draft-PR-pass`。

PR 69 draft PR gate 已完成。PR URL: `https://github.com/noho/dayu-agent-r/pull/69`。PR created as draft，branch
`feat/phase-13-audit-trace-outbox` pushed to `github` remote；GitHub reported no checks on branch。PR review artifacts:
`docs/reviews/pr-69-review-mimo-20260529.md`、`docs/reviews/pr-69-review-ds-20260529.md`、
`docs/reviews/pr-69-review-controller-adjudication-20260529.md`。Accepted PR review fix artifact:
`docs/reviews/pr-69-fix-codex-20260529.md`；fix re-review artifacts:
`docs/reviews/pr-69-fix-rereview-mimo-20260529.md`、`docs/reviews/pr-69-fix-rereview-ds-20260529.md`、
`docs/reviews/pr-69-fix-rereview-controller-adjudication-20260529.md`。Accepted PR review fix commit 为 `27b4c0c`。
Final validation：tool trace focused tests 6 passed；aggregate host suite 108 passed；`python -m pyright dayu/host tests/host`
0 errors；`git diff --check` clean；`git diff --check main...HEAD` clean。当前 gate：draft-PR-pass。

### 2026-05-24 P12.6 Slice 1 code re-review passed

P12.6 Slice 1 `Design Truth Rewrite And Contract Pruning` 已完成 retry implementation、code review、targeted fix 与双路
code re-review。Implementation artifact 为 `docs/reviews/p12-6-slice1-implementation-codex-r2-20260524.md`；code review
artifacts 为 `docs/reviews/p12-6-slice1-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice1-code-review-ds-20260524.md`；controller code review adjudication artifact 为
`docs/reviews/p12-6-slice1-code-review-controller-adjudication-20260524.md`；targeted fix artifact 为
`docs/reviews/p12-6-slice1-fix-codex-20260524.md`；code re-review artifacts 为
`docs/reviews/p12-6-slice1-code-rereview-mimo-20260524.md` 与
`docs/reviews/p12-6-slice1-code-rereview-ds-20260524.md`。

Controller 裁决：D-F1 / D-F2 / D-F3 / M-F3 均已修复；MiMo 早前 M-F1 / M-F2 属于 wrong-base finding，不在当前
workspace diff 中。两路 code re-review verdict 均为 PASS。Controller acceptance validation：affected Host pytest 262
passed；`python -m pyright dayu tests` 0 errors；`git diff --check` pass；README 触发项已同步。DS 记录 `tests/host/` 全量存在一个既有失败
`tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity`，该文件不在当前
workspace diff 中，不阻塞 Slice 1 acceptance。后续 gate 需要创建 accepted slice commit。

### 2026-05-24 P12.6 Slice 2 code re-review passed

P12.6 Slice 2 `Deterministic Segment Selection / Material Pack Builder` 已完成 implementation、code review、targeted fix 与双路
code re-review。Implementation artifact 为 `docs/reviews/p12-6-slice2-implementation-codex-20260524.md`；code review artifacts
为 `docs/reviews/p12-6-slice2-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice2-code-review-ds-20260524.md`；controller adjudication artifact 为
`docs/reviews/p12-6-slice2-code-review-controller-adjudication-20260524.md`；targeted fix artifact 为
`docs/reviews/p12-6-slice2-fix-codex-20260524.md`；code re-review artifacts 为
`docs/reviews/p12-6-slice2-code-rereview-mimo-20260524.md` 与
`docs/reviews/p12-6-slice2-code-rereview-ds-20260524.md`。

Controller 裁决：fragile memory material kind string prefix matching、undocumented inline repair threshold drift 和
`excluded_reason_codes` key type semantics 均已修复；continuity / compact material block `event_sequence=None` deferred 到
Slice 5 wiring；snapshot text escaping / stable kind ordering 记录为 non-blocking residual。两路 code re-review verdict 均为
PASS。Controller validation：focused pytest 93 passed；targeted pyright 0 errors；`python -m pyright dayu tests` 0 errors；
`git diff --check` pass；README 触发项已同步。后续 gate 需要创建 accepted slice commit。

### 2026-05-24 P12.6 Slice 3 code review passed

P12.6 Slice 3 `Raw Evidence Reader And Prompt-local Label Mapping Hardening` 已完成 implementation 与双路 code review。Implementation
artifact 为 `docs/reviews/p12-6-slice3-implementation-codex-20260524.md`；code review artifacts 为
`docs/reviews/p12-6-slice3-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice3-code-review-ds-20260524.md`。

Controller 裁决：两路 verdict 均 PASS；DS 的 RunInputMaterialBlock artifact/source locator provenance 扩展、旧 range-based
collector removal、artifact descriptor raw evidence reconstruction 均记录为后续 owner，不阻塞 Slice 3。Controller validation：
focused pytest 48 passed；targeted pyright 0 errors；`python -m pyright dayu tests` 0 errors；`git diff --check` pass；README
触发项已检查且无需更新。后续 gate 需要创建 accepted slice commit。

### 2026-05-24 P12.6 Slice 4 code review passed

P12.6 Slice 4 `LLM Compactor JSON Schema And Accept Barrier Hardening` 已完成 implementation 与双路 code review。Implementation
artifact 为 `docs/reviews/p12-6-slice4-implementation-codex-20260524.md`；code review artifacts 为
`docs/reviews/p12-6-slice4-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice4-code-review-ds-20260524.md`。

Controller 裁决：两路 verdict 均 PASS；`memory_snapshot_cursor` preservation evidence wiring、real provider
`preservation_evidence` compliance 与 durable operation multi-pass 归 Slice 5 / Slice 7，不阻塞 Slice 4。Controller validation：
focused pytest 49 passed；targeted pyright 0 errors；`python -m pyright dayu tests` 0 errors；`git diff --check` pass；README
触发项已检查且无需更新。后续 gate 需要创建 accepted slice commit。

### 2026-05-24 P12.6 Slice 5 code re-review passed

P12.6 Slice 5 `Proactive / Reactive Context Governance Wiring` 已完成 implementation、code review、targeted fix 与双路
code re-review。Implementation artifact 为 `docs/reviews/p12-6-slice5-implementation-codex-20260524.md`；code review artifacts
为 `docs/reviews/p12-6-slice5-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice5-code-review-ds-20260524.md`；controller adjudication artifact 为
`docs/reviews/p12-6-slice5-code-review-controller-adjudication-20260524.md`；targeted fix artifact 为
`docs/reviews/p12-6-slice5-fix-codex-20260524.md`；code re-review artifacts 为
`docs/reviews/p12-6-slice5-code-rereview-mimo-20260524.md` 与
`docs/reviews/p12-6-slice5-code-rereview-ds-20260524.md`。

Controller 裁决：duplicate selected-material source refs helper、lossy multi-pass summary / pinned patch merge、indirect
zero-budget single-block reactive pass selection 与 frozen material list README semantics 均已修复。旧 range collector 删除 deferred 到
Slice 7；proactive pre-dispatch material view current-input-only 归 Slice 6 / later wiring。Controller validation：focused pytest 140
passed；targeted pyright 0 errors；`python -m pyright dayu tests` 0 errors；`git diff --check` pass；README 触发项已同步。后续 gate
需要创建 accepted slice commit。

### 2026-05-24 P12.6 Slice 6 code review passed

P12.6 Slice 6 `Memory Projection Consolidation 与 RunInputBuilder Rendering` 已完成 implementation 与双路 code review。
Implementation artifact 为 `docs/reviews/p12-6-slice6-implementation-codex-20260524.md`；code review artifacts 为
`docs/reviews/p12-6-slice6-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice6-code-review-ds-20260524.md`；controller adjudication artifact 为
`docs/reviews/p12-6-slice6-code-review-controller-adjudication-20260524.md`。

Controller 裁决：两路 verdict 均 PASS；MiMo 的 episode summary cap 常量命名与 fact `candidate_id` cover-ref
观察项均为低严重度、非阻塞，不进入 targeted fix gate。Slice 6 已实现 compact 后 fact dedupe、bounded fact working set、bounded
recent episode summaries、minimum preserve coverage expiry 与 RunInputBuilder fact rendering 语义。Controller validation：focused
pytest 91 passed；`python -m pyright dayu tests` 0 errors；`git diff --check` pass；README 触发项已同步。后续 gate 需要创建
accepted slice commit。

### 2026-05-24 P12.6 Slice 7 cleanup re-review passed

P12.6 Slice 7 `Public Compact Smoke、README 同步与最终验证` 已完成 implementation、targeted production fix、code review、
review cleanup 与双路 cleanup re-review。Implementation artifact 为
`docs/reviews/p12-6-slice7-implementation-codex-20260524.md`；targeted fix artifact 为
`docs/reviews/p12-6-slice7-fix-codex-20260524.md`；code review artifacts 为
`docs/reviews/p12-6-slice7-code-review-mimo-20260524.md` 与
`docs/reviews/p12-6-slice7-code-review-ds-20260524.md`；cleanup artifact 为
`docs/reviews/p12-6-slice7-cleanup-codex-20260524.md`；cleanup re-review artifacts 为
`docs/reviews/p12-6-slice7-cleanup-rereview-mimo-20260524.md` 与
`docs/reviews/p12-6-slice7-cleanup-rereview-ds-20260524.md`；controller adjudication artifact 为
`docs/reviews/p12-6-slice7-cleanup-rereview-controller-adjudication-20260524.md`。

Controller 裁决：public opener accepted tool evidence 未进入 compactor `evidence_input` 的 stop-condition gap 已修复；
proactive pre-start material 现在补入当前输入 cursor 之前、当前 Session 内、未被 stable fact / compact artifact 表示的 bounded
accepted tool evidence。MiMo F1/F2 与 DS Finding 1 已通过 cleanup 修复；两路 cleanup re-review 均 PASS，未发现 blocking /
high / medium 新问题。Controller validation：public smoke 5 passed / 1 skipped；specified host suite 292 passed / 1 skipped；
`python -m pyright dayu/ tests/` 0 errors；`git diff --check` pass；README 触发项已同步。后续 gate 需要创建 accepted slice commit。

### 2026-05-22 Phase 12 runtime assembly and config governance completed

Phase 12 / 12.1 / 12.2 / 12.3 runtime assembly、Service assembly helper、config schema 与 usage governance
闭环已完成。PR 67 `https://github.com/noho/dayu-agent-r/pull/67` 已达到 `draft-PR-pass` 并由用户 merge。

完成范围：

- P12 完成 ToolsDiscovery、ConfigLoader、ScenePrepare、legacy scene assets migration、runtime import boundary、
  README sync、aggregate deepreview、aggregate fix 与 aggregate re-review。
- P12.1 完成 runtime assembly schema / public contract correction，使 ConfigLoader、ScenePrepare、ToolsDiscovery 与
  smoke 装配路径能按真实 Service-like assembly 映射到 `open_host(options)` 与 per-run typed input。
- P12.2 完成正式 `dayu.service.host_assembly` helper、ScenePrepare `system_prompt` 输出、host runtime tuning 字段与
  smoke-local adapter 到 Service assembly helper 的升级。
- P12.3 完成 config schema cleanup、内嵌 `agent_policy`、删除默认 runner option hint `max_tokens`、usage post-call
  observation consumption、execution profile scene/window class split、aggregate validation 与 README sync。

关键 artifacts：

- P12 plan / implementation / review artifacts：`docs/host/phase12-runtime-assembly-plan.md` 与
  `docs/reviews/phase12-*`。
- P12.1 plan / implementation / review artifacts：`docs/host/phase12-1-runtime-assembly-correction-plan.md` 与
  `docs/reviews/phase12-1-*`。
- P12.2 plan / implementation / review artifacts：`docs/reviews/phase12-2-*`。
- P12.3 plan / implementation / review artifacts：`docs/host/phase12-3-config-usage-governance-plan.md` 与
  `docs/reviews/phase12-3-*`。
- PR 67 post-push review artifacts：`docs/reviews/pr-67-phase12-3-post-push-review-mimo-20260522.md`、
  `docs/reviews/pr-67-phase12-3-post-push-review-ds-20260522.md` 与
  `docs/reviews/pr-67-phase12-3-post-push-review-controller-adjudication-20260522.md`。

最终 gate 结论：P12 completed。后续入口已切换为 P12.5 Conversation Memory Optimization；相关待裁决事项不得继续放在
`当前状态`，必须进入 Phase Map 或 `Open Questions 与风险追踪`。

### 2026-05-18 Phase 10 draft PR gate passed

Phase 10 Context Governance / Compaction draft PR gate 已完成。Branch
`feat/host-phase10-context-governance` 已 push 到 GitHub，draft PR 61 已创建：
`https://github.com/noho/dayu-agent-r/pull/61`，title 为 `feat(host): add Phase 10 context governance`，head branch 为
`feat/host-phase10-context-governance`，base branch 为 `main`。PR state 为 open draft；
`mergeStateStatus=CLEAN`，`mergeable=MERGEABLE`。GitHub checks 当前返回 no checks reported on the branch。

PR review artifacts 为 `docs/reviews/pr-61-review-phase10-mimo-20260518.md` 与
`docs/reviews/pr-61-review-phase10-ds-20260518.md`；两份 review 均 PASS，0 blocking / high / medium finding。
Controller PR review adjudication artifact 为 `docs/reviews/pr-61-review-controller-adjudication-20260518.md`。
Accepted PR review commit 为 `be03578`。PR body 已补充 PR-level review artifact 链接。PR gate validation 继承
aggregate gate：focused pytest 81 passed + 180 passed；`pyright` 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。当前 gate 为 `draft-PR-pass`。后续 merge、mark ready for review、request reviewers、
approve、delete branch 或对外 comment 仍需用户额外授权。

### 2026-05-18 Phase 10 aggregate deepreview accepted

Phase 10 aggregate deepreview 已完成。Aggregate review artifacts 为
`docs/reviews/phase10-aggregate-deepreview-mimo-20260518.md` 与
`docs/reviews/phase10-aggregate-deepreview-ds-20260518.md`。AgentMiMo verdict 为 PASS，明确 Phase 10 已可进入
`ready-to-open-draft-PR`；AgentDS verdict 为 PASS / Ready for draft PR，提出 3 个 LOW 与若干 INFO / residual。

Controller 裁决：AG1 / AG2 / AG3 均接受为 non-blocking residual，不作为 PR 前 fix。AG1 不影响当前 worker stream
停止，因为 scheduler 同时检查 `terminal_closeout or stop_worker_stream`；AG2 是同事务 defensive ordering cleanup；
AG3 是预算压力下的可读性降级，不影响 Host truth。Controller aggregate adjudication artifact 为
`docs/reviews/phase10-aggregate-deepreview-controller-adjudication-20260518.md`。

Phase 10 达成：Host-owned `ContextBudgetPolicy`、proactive pre-start compaction、reactive overflow recovery、
canonical compact event / artifact、P9 memory projection consumption、RunInputBuilder compact / memory provider、
production composition wiring，以及 multi-turn proactive compact -> memory projection -> subsequent Engine request
aggregate validation。

Validation：S6 后 controller focused validation 为 81 passed + 180 passed；`pyright` 0 errors / 0 warnings /
0 informations；`git diff --check` clean。AgentMiMo aggregate review 另行复现 261 passed、pyright 0、diff check clean。
当前 gate 进入 `ready-to-open-draft-PR`。Aggregate review commit 在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 S6 Production Composition / Multi-turn Integration accepted

Phase 10 S6 Production Composition Wiring / Multi-turn Integration / Docs Sync 已完成。Implementation artifact 为
`docs/reviews/phase10-s6-production-composition-integration-implementation-20260518.md`。Initial code review artifacts
为 `docs/reviews/phase10-s6-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s6-code-review-ds-20260518.md`。

Controller 裁决：AgentMiMo review 为 PASS；AgentDS review 为 PASS_WITH_RESIDUAL，但提出两个 medium finding。
Controller 接受 DS F2 / F4 为当前 slice fix item：`HostCommandHandleOptions.context_window_size` 与
`reserved_output_tokens` 必须是 composition root 显式 typed input，不得有 production 默认值；Phase 10 必须补一个
multi-turn aggregate integration test 串起 proactive compact、memory projection catch-up 与 subsequent Engine request。
Controller 接受 DS F1 / F3 为 residual：composition helper 不由同步 command factory 隐式调用，production helper 不默认注入
fake compactor。Fix artifact 为 `docs/reviews/phase10-s6-review-fix-codex-20260518.md`。

Re-review artifacts 为 `docs/reviews/phase10-s6-code-rereview-mimo-20260518.md` 与
`docs/reviews/phase10-s6-code-rereview-ds-20260518.md`；两份 re-review 均 PASS，remaining blocking / high /
medium findings 为 0。Controller adjudication artifact 为
`docs/reviews/phase10-s6-code-review-controller-adjudication-20260518.md`。

S6 交付：`HostCommandHandleOptions` 新增必填 `context_window_size` 与 `reserved_output_tokens`，可选
hard threshold / minimum protection tokens；`compose_host_local_execution_options(...)` 从 command options 构造 typed
`ContextBudgetPolicy` 并注入 compact artifact root，保持 memory projection policy 与 context budget policy 分离；
新增 multi-turn aggregate integration 覆盖 follow-up under budget raw turn、soft threshold proactive compact、
`CONTEXT_COMPACTED` pre-start ordering、compact artifact provider 与 subsequent Run memory 注入。

Validation：`pytest tests/host/test_public_contracts.py tests/host/test_phase5_local_execution_integration.py
tests/host/test_dispatch_scheduler.py -q` 81 passed；`pytest tests/host/test_context_budget.py
tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_context_compact_events.py
tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py
tests/host/test_run_attempt_transitions.py -q` 180 passed；`pyright` 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。当前 gate 进入 Phase 10 aggregate deepreview。Accepted slice commit 在本条记录提交后由
git commit 记录。

### 2026-05-18 Phase 10 S5 Reactive Overflow Recovery accepted

Phase 10 S5 Reactive Engine Overflow Recovery 已完成。Implementation artifact 为
`docs/reviews/phase10-s5-reactive-overflow-recovery-implementation-20260518.md`。Code review artifacts 为
`docs/reviews/phase10-s5-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s5-code-review-ds-20260518.md`。

Controller 裁决：AgentMiMo review 为 PASS，AgentDS review 为 ACCEPTED_WITH_RESIDUAL。Controller 接受
MiMo low doc finding 并已修正 implementation artifact 测试计数；DS 的 worker accept -> recovery 覆盖 finding
裁决为 rejected-with-evidence，因为 scheduler integration 测试实际覆盖 worker accept 后的 Engine event recovery
路径；DS 的 orchestration method length 接受为 residual 并写入追踪区。Controller adjudication artifact 为
`docs/reviews/phase10-s5-code-review-controller-adjudication-20260518.md`。

S5 交付：`EngineEventIngestor` 将 Engine `context_compaction_requested` 映射为
`CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`，使用 Host estimator / policy 而不是 Engine
`budget_state` 作为预算真源；旧 Attempt 关闭为 `ATTEMPT_FAILED`，Run 写入 `RUN_RECOVERING`；compact accepted
后写 compact artifact / `CONTEXT_COMPACTED`，追平 P9 memory projection，再创建新的 Attempt / execution /
dispatch record 并写 `RUN_STARTED(start_reason=recovery)`、`ATTEMPT_STARTED`；compact failure、count 上限、
count 损坏、compactor 缺失、quality rejected 或 compact 后 hard threshold 均从 `RECOVERING` 收口 `FAILED`，
不写 `LOST`。新增 `EngineIngestResult.stop_worker_stream`，使 recovery accepted 能停止旧 worker stream、释放
lane / handle，但不清理同 Run duplicate governance registry，也不触发 queued promotion。

Validation：`pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py
tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py -q` 104 passed；
`pyright` 0 errors / 0 warnings / 0 informations；`git diff --check` clean。当前 gate 进入 Phase 10 S6
Production Composition Wiring / Multi-turn Integration Validation / Docs Sync implementation。Accepted slice commit
在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 S4 Proactive Context Governance accepted

Phase 10 S4 Proactive Pre-dispatch Context Governance / RunInputBuilder Compact Provider 已完成。Implementation artifact 为
`docs/reviews/phase10-s4-proactive-context-governance-implementation-20260518.md`。Code review artifacts 为
`docs/reviews/phase10-s4-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s4-code-review-ds-20260518.md`。

Controller 裁决：AgentMiMo review 为 PASS，AgentDS review 为 ACCEPTED_WITH_RESIDUAL。Controller 接受 3 个
residual：compactor / artifact write 位于 SQLite write transaction 内、budget estimate 只覆盖当前 prompt、
`promote_next_queued_run` legacy helper 表面仍存在。上述 residual 已写入追踪区，不阻塞 S4 accepted。
Controller adjudication artifact 为
`docs/reviews/phase10-s4-code-review-controller-adjudication-20260518.md`。

S4 交付：新增 `RunStatus.ACCEPTED` 与 schema v9，admission `start_run` 先创建 accepted Run 且不创建 Attempt；
scheduler `wake_queue_promotion` 成为 production pre-start governance gate；soft threshold 触发 proactive compact，
hard threshold / compact failure 以 attempt-free `RUN_FAILED` 收口；compact accepted 后先 catch up P9 memory projection，
再创建 `RUN_STARTED` / `ATTEMPT_STARTED` / dispatch record。RunInputBuilder production path 注入
`DurableCompactArtifactProvider`，只向 Engine 暴露 compact artifact ref / digest、compacted event refs、preserved fact refs
与 bounded episode summary。

Validation：`pytest tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py
tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py
tests/host/test_run_input_builder.py -q` 124 passed；`pyright` 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。当前 gate 进入 Phase 10 S5 Reactive Engine Overflow Recovery implementation。
Accepted slice commit 在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 S3 Canonical Compact Events accepted

Phase 10 S3 Compact Canonical Events / P9 Memory Projection Consumption 已完成。Implementation artifact 为
`docs/reviews/phase10-s3-context-events-memory-projection-implementation-20260518.md`。Code review artifacts 为
`docs/reviews/phase10-s3-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s3-code-review-ds-20260518.md`。

Controller 裁决：AgentMiMo review 为 PASS，AgentDS review 为 PASS with accepted medium hardening item。Controller
接受 DS M1 为当前 slice fix item：`CONTEXT_COMPACTED` validator 必须拒绝非空
`episode_summary_candidate.proposed_verified_fact_refs`，防止 accepted compact summary 在 canonical payload 层
携带“新建 verified fact”提议；同时前置补强 replace patch value validator。Fix artifact 为
`docs/reviews/phase10-s3-code-review-fix-codex-20260518.md`。Re-review artifacts 为
`docs/reviews/phase10-s3-code-rereview-mimo-20260518.md` 与
`docs/reviews/phase10-s3-code-rereview-ds-20260518.md`；两份 re-review 均 PASS，remaining blocking / high /
medium findings 为 0。Controller adjudication artifact 为
`docs/reviews/phase10-s3-code-review-controller-adjudication-20260518.md`。

S3 交付：新增 `dayu.host.context_events` 作为 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED` 与
`CONTEXT_COMPACTION_FAILED` payload builder / validator 真源；P9 memory projection 改为消费 accepted
`CONTEXT_COMPACTED`，episode summary 只物化为 assumption continuity item，pinned state patch candidate 按
missing / clear / replace 三态更新，verified facts 仍只来自 `TOOL_RESULT_ACCEPTED`。Production memory consumer /
RunInputBuilder inline delta filter 纳入 `CONTEXT_COMPACTED`，不消费 `CONTEXT_COMPACTION_FAILED`。

Validation：`pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py
tests/host/test_run_input_builder.py -q` 79 passed；`pyright` 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。当前 gate 进入 Phase 10 S4 Proactive Context Governance Orchestration implementation。
Accepted slice commit 在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 S2 Compaction Contracts accepted

Phase 10 S2 Compactor Contracts / Fake Compactor / Quality Check / Artifact Store 已完成。Implementation
artifact 为 `docs/reviews/phase10-s2-compaction-contracts-implementation-20260518.md`。Code review artifacts 为
`docs/reviews/phase10-s2-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s2-code-review-ds-20260518.md`。

Controller 裁决：AgentMiMo review 为 PASS，AgentDS review 为 CHANGES_REQUESTED。Controller 接受 DS B1、
M1、M2 与 residual R2 为当前 slice fix items：`CompactionRequest.__post_init__` 必须先校验
`CurrentMessageSummary` 类型再访问属性；非法 current-message-summary 类型、`CompactQualityCheckResult`
accepted/rejected invariant 必须有直测；reactive compaction request 必须携带非空 `attempt_id` 与
`execution_id`，proactive compact 可省略。Fix artifact 为
`docs/reviews/phase10-s2-code-review-fix-codex-20260518.md`。Re-review artifacts 为
`docs/reviews/phase10-s2-code-rereview-mimo-20260518.md` 与
`docs/reviews/phase10-s2-code-rereview-ds-20260518.md`；两份 re-review 均 PASS，remaining blocking / high
findings 为 0。Controller adjudication artifact 为
`docs/reviews/phase10-s2-code-review-controller-adjudication-20260518.md`。

S2 交付：新增 Host typed compactor contract、deterministic fake compactor、quality checker、compact artifact
store 与 focused tests。Quality checker 拒绝丢失当前用户输入、丢失 accepted tool fact refs、summary 伪造
verified fact、缺 preservation evidence、evidence anchor 未保留、pinned patch 三态非法或引用未知 evidence。
Compact artifact store 只写 canonical JSON artifact 与 payload descriptor，不写 EventLog；fake compactor 只允许
测试 / 本地开发显式注入。README 同步：`dayu/host/README.md` 与 `tests/README.md` 已记录当前实现事实与测试入口。

Validation：`pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q` 17 passed；
`pyright` 0 errors / 0 warnings / 0 informations；`git diff --check` clean。当前 gate 进入 Phase 10 S3 Canonical
Compact Events And P9 Memory Projection Consumption implementation。Accepted slice commit 在本条记录提交后由 git
commit 记录。

### 2026-05-18 Phase 10 S1 Context Budget Policy accepted

Phase 10 S1 Context Budget Policy / Estimator / Usage Observation 已完成。Implementation artifact 为
`docs/reviews/phase10-s1-context-budget-implementation-20260518.md`。Code review artifacts 为
`docs/reviews/phase10-s1-code-review-mimo-20260518.md` 与
`docs/reviews/phase10-s1-code-review-ds-20260518.md`。

Controller 裁决：两份 initial review 均为 PASS，但接受 DS H1 与 MiMo/DS M1/M3、DS M2 作为当前 slice fix
items：`dayu.host.durable.event_log` 不得导入 context policy 语义；重复整数 validation helper 必须收敛到
Host 层共享校验真源；soft threshold ratio 不得与默认 safety margin 形成双真源；EventLog payload filter
fail-closed 边界必须有测试覆盖。Fix artifact 为
`docs/reviews/phase10-s1-code-review-fix-codex-20260518.md`。Re-review artifacts 为
`docs/reviews/phase10-s1-code-rereview-mimo-20260518.md` 与
`docs/reviews/phase10-s1-code-rereview-ds-20260518.md`；两份 re-review 均 PASS，remaining blocking / high /
medium findings 为 0。Controller adjudication artifact 为
`docs/reviews/phase10-s1-code-review-controller-adjudication-20260518.md`。

S1 交付：新增 Host context budget typed policy / static provider、conservative estimator、usage observation
typed model、`HostLocalExecutionOptions.context_budget_policy` typed 接收点，以及 durable-neutral
`EventPayloadTextEqualsFilter` + transaction-scoped committed fact count helper。预算真源仍只来自 Host typed policy；
`USAGE_REPORTED` payload 未扩展，provider overflow `budget_state=None` 不成为 Host budget truth。README 同步：
`dayu/host/README.md` 已记录当前 Host local execution options context budget policy typed 边界与 EventLog
committed fact 统计能力。

Validation：`pytest tests/host/test_context_budget.py tests/host/test_public_contracts.py tests/host/test_engine_ingest_mapping.py -q`
81 passed；`pyright` 0 errors / 0 warnings / 0 informations；`git diff --check` clean。当前 gate 进入 Phase 10
S2 Compactor Contracts / Fake Compactor / Quality Check / Artifact Store implementation。Accepted slice commit 在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 implementation-ready plan accepted

Phase 10 Context Governance / Compaction implementation-ready handoff plan 已写入
`docs/host/phase10-context-governance-plan.md`。Initial plan review artifacts 为
`docs/reviews/phase10-plan-review-mimo-20260518.md` 与
`docs/reviews/phase10-plan-review-ds-20260518.md`。AgentMiMo verdict 为 CHANGES_REQUESTED，blocking
findings B1 / B2 / B3 分别覆盖 `RunStatus.ACCEPTED` cancel path、queued promotion governance bypass 与
`CONTEXT_COMPACTED` memory projection parsing specificity；AgentDS verdict 为 PASS，但提出 pre-start governance
wakeup、`ACCEPTED` 与 `ATTACH_ACTIVE` 交互、queued promotion transition 的 high-severity plan clarifications。

Plan fix artifact 为 `docs/reviews/phase10-plan-fix-codex-20260518.md`。Fix 后的 re-review artifacts 为
`docs/reviews/phase10-plan-rereview-mimo-20260518.md` 与
`docs/reviews/phase10-plan-rereview-ds-20260518.md`；两份 re-review 均 PASS，remaining blocking / high findings
为 0。Controller adjudication artifact 为
`docs/reviews/phase10-plan-review-controller-adjudication-20260518.md`。Controller 接受 DS re-review 的
non-blocking medium finding 作为 Slice 4 implementation action：实现必须显式解决 concurrent `ACCEPTED`
Run guard，可选 fresh-schema partial uniqueness guard 或等价 fail-safe；同时 Slice 4 应先定义
`StartGovernanceCandidate` typed contract，并裁决旧 combined start helper 的生产路径移除方式。

Phase 10 plan gate 已接受，当前 gate 进入 Phase 10 implementation。Plan gate validation：`git diff --check`
clean。Accepted plan commit 在本条记录提交后由 git commit 记录。

### 2026-05-18 Phase 10 design discussion accepted

Phase 10 Context Governance / Compaction design discussion 已完成。已确认 policy 默认值、`context_window_size` /
`reserved_output_tokens` 输入来源、usage observation 边界、proactive / reactive compact failure policy、P9 / P10
单向配合边界，以及多轮会话主体闭环的数据来源。P10 第一版必须包含 Host-owned typed compactor port、episode summary
candidate、pinned state patch candidate、canonical compact event / artifact、P9 memory projection consumption、
RunInputBuilder compact provider 与 production composition wiring。当前 gate 进入 Phase 10 implementation-ready handoff plan。

### 2026-05-18 P9.5 merged and Phase 10 opened

P9.5 Draft PR 60 `https://github.com/noho/dayu-agent-r/pull/60` 已合并，merge commit 为 `f131fb8`。
当前 Host phase 工作入口进入 Phase 10 Context Governance / Compaction design discussion / design refinement。
Phase 10 必须先确认 conservative estimator、provider-aware configured limits、safety margin、compact policy 默认值、
proactive / reactive transaction 与 state transition、compact artifact quality check，以及 compact failure policy；
确认后才允许生成 implementation-ready handoff plan。
已确认的 Phase 10 discussion decision：`reserved_output_tokens` 由 Service / composition root 作为 Host context policy
显式 typed input 传入，并与 `context_window_size` 一起由 policy provider 提供；Host 不从 Engine、per-run metadata 或
extra payload 读取预算参数。Runner usage 只作为 post-call observation / diagnostics / calibration 输入，不替代 pre-dispatch
estimator。
补充确认的 policy decision：默认 safety margin 为 20%；soft threshold 为输入预算的 80%；hard threshold 由 policy provider
显式给出或按输入预算扣除 policy 定义的最小保护余量后计算；每个 Run 的 proactive trigger 第一版最多 compact 一次；
reactive trigger 每次 Engine overflow 最多启动一个 compact operation，但同一 Run 可在 `max_reactive_compactions_per_run`
范围内多次 reactive compact，默认上限为 2；proactive compact failure 让 Run 在 dispatch 前 `FAILED` 且不创建 Attempt；
reactive compact failure 或 reactive 次数耗尽在当前 Attempt 关闭后让 Run `FAILED`；`LOST` 保留给 Phase 11 recovery owner；
usage 第一版只记录 diagnostics / calibration observation，不自动动态调参。
P9 / P10 配合边界：P9 Conversation Memory 只提供 EventLog read model、snapshot cursor、policy digest 与 diagnostics；
P10 Context Governance 可读取 memory snapshot 做预算和 compact，但不得直接写 memory snapshot，不得让 compact summary
替代 verified fact / evidence anchor，不得把 memory projection lag 当作 Run recovery。
补充的 discussion decision：P10 第一版必须包含 Host-owned typed compactor port，允许调用 LLM compaction scene
生成 episode summary candidate 与 pinned state patch candidate；LLM 只作为候选提案者，Host 做质量检查与
canonical compact event / artifact accept，P9 memory projection 后续消费已提交 facts 物化 memory view。Phase 10 plan
不得只实现 budget 裁剪而不定义 stable layer / history pool 的新数据来源。

### 2026-05-18 P9.5 completed

P9.5 Pre-P10 Cross-Repository Hardening PR 已完成。P9.5 已完成 design discussion、implementation-ready plan、
S1-S18 implementation / review / accepted commits、aggregate deepreview、accepted aggregate fixes、draft PR create、
PR review 与 `draft-PR-pass`。Draft PR 为 PR 60：
`https://github.com/noho/dayu-agent-r/pull/60`。PR 仍为 draft；mark ready for review、merge、request reviewers、
approve、delete branch 或对外 comment 仍需用户额外授权。当前 gate 为 `P9.5 completed`，后续入口为用户手工
review / merge decision。

### 2026-05-17 P9.5 draft PR gate passed

P9.5 draft PR gate 已完成。Branch `p9.5-pre-p10-hardening` 已 push 到 GitHub，draft PR 60 已创建：
`https://github.com/noho/dayu-agent-r/pull/60`，title 为 `P9.5 Pre-P10 cross-repository hardening`，head branch 为
`p9.5-pre-p10-hardening`，base branch 为 `main`。PR state 为 open draft；`mergeStateStatus=CLEAN`，`mergeable=MERGEABLE`。
GitHub checks 当前返回 no checks reported on the branch。

PR review artifacts 为 `docs/reviews/pr-60-review-p9-5-mimo-20260517.md` 与
`docs/reviews/pr-60-review-p9-5-ds-20260517.md`；两份 review 均 PASS，0 blocking / high / medium / low finding。
Controller PR review adjudication artifact 为 `docs/reviews/pr-60-review-controller-adjudication-20260517.md`。Accepted PR
review commit 为 `7f9bf67`。PR gate validation 继承 aggregate gate：`pytest -q` 1068 passed；
`python -m pyright dayu tests` 0 errors / 0 warnings / 0 informations；`git diff --check` clean。当前 gate 为
`draft-PR-pass`。后续 merge、mark ready for review、request reviewers、approve、delete branch 或对外 comment 仍需用户额外授权。

### 2026-05-17 P9.5 aggregate deepreview accepted

P9.5 aggregate deepreview 已完成。Aggregate deepreview artifacts 为
`docs/reviews/p9-5-aggregate-deepreview-mimo-20260517.md` 与
`docs/reviews/p9-5-aggregate-deepreview-ds-20260517.md`。MiMo F1 / F2 / F3 已由 controller 裁决为
accepted fix items：EventLog canonical inline payload 阈值必须从 durable store policy 显式注入，不得在 EventLog
primitive 中硬编码默认值；dispatch waiting / worker accepted CAS 需要补齐 `cancelled_event_sequence IS NULL`；
TruncationManager 截断后仍超限或替换失败时必须清理未返回 cursor。F4 裁决为 rejected-as-current-fix，因
`fetch_more` 当前必须先 materialize continuation 才能按 canonical tool outcome 计算 inline size，且 request limit
已有上界；F5 / F6 / F7 均不构成当前 blocker。

Accepted-finding fix re-review artifacts 为
`docs/reviews/p9-5-aggregate-fix-rereview-mimo-20260517.md` 与
`docs/reviews/p9-5-aggregate-fix-rereview-ds-20260517.md`；两份 re-review 均 PASS，0 blocking / high / medium /
low finding。Controller aggregate adjudication artifact 为
`docs/reviews/p9-5-aggregate-deepreview-controller-adjudication-20260517.md`。Controller validation：
`pytest tests/host/test_event_log_store.py tests/host/test_durable_transaction.py tests/host/test_toolruntime_executor.py tests/host/test_run_attempt_transitions.py -q`
77 passed；`pytest -q` 1068 passed；`python -m pyright dayu tests` 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。Accepted aggregate deepreview commit 为 `392f914`。当前 gate 为 `ready-to-open-draft-PR`。

### 2026-05-17 P9.5 S18 Aggregate Validation And Readiness Evidence accepted

P9.5 S18 Aggregate Validation And Readiness Evidence 已完成。Readiness implementation artifact 为
`docs/reviews/p9-5-s18-aggregate-validation-readiness-implementation-20260517.md`。Readiness review /
re-review / controller adjudication artifacts 为 `docs/reviews/p9-5-s18-readiness-review-mimo-20260517.md`、
`docs/reviews/p9-5-s18-readiness-review-ds-20260517.md`、
`docs/reviews/p9-5-s18-readiness-re-review-ds-20260517.md` 与
`docs/reviews/p9-5-s18-readiness-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo readiness review 为 PASS；AgentDS readiness review 为 PASS with one
non-blocking finding。DS F3 指出 readiness artifact 曾将 `minimal read model single-consumer reset contract`
误映射为 S2，controller 接受并修正为 S6，DS re-review 确认 fixed。S18 aggregate validation 通过：
`pytest -q` 为 1066 passed；`python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。S18 readiness artifact 已将 P9.5 tracking items 映射为 fixed、明确不修且有原因，
或重新归属到具体 P10+ owner；generic default memory catch-up 仍明确不属于 P9.5，因为需要 snapshot history /
cursor coverage 语义。Accepted slice commit 为 `79db0e1`。当前 gate 为 P9.5 aggregate deepreview。

### 2026-05-17 P9.5 S17 Documentation And Control Tracking accepted

P9.5 S17 Documentation And Control Tracking 已完成。Implementation artifact 为
`docs/reviews/p9-5-s17-documentation-control-tracking-implementation-20260517.md`。Documentation review /
re-review / controller adjudication artifacts 为 `docs/reviews/p9-5-s17-doc-review-mimo-20260517.md`、
`docs/reviews/p9-5-s17-doc-re-review-mimo-20260517.md`、
`docs/reviews/p9-5-s17-doc-review-ds-20260517.md` 与
`docs/reviews/p9-5-s17-doc-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentDS review 为 PASS，0 blocking findings；AgentMiMo 的 LOW precision finding 被接受并
修复，`tests/README.md` 已将 Engine import boundary 从独立 `memory` 项校准为 `Host（含 memory）`，
re-review 确认 fixed。S17 只做稳定文档校准：`dayu/README.md` 与 `docs/design.md` 补齐 `tool_schemas`
和 ToolRuntime `tool_executor` 必须来自同一个 attempt-local effective `ToolBundle`；`dayu/engine/README.md`
明确当前函数式入口通过私有默认 OpenAI-compatible Runner 装配点创建 Runner，该装配点不是 public factory /
registry / runner selection extension；`dayu/host/README.md` 将 projection catch-up failure 描述校准为
projection-local `WARNING` + `error_type`，不再写 logger exception；`tests/README.md` 同步 runtime /
contracts / engine / host import-boundary guard 当前事实，包括 Host business tool scanner 禁止与 `fetch_more`
ToolRuntime / tooling owner guard。S17 未更新 `docs/host/design.md`，因为 Host 专题设计已有对应设计目标且
本轮未改变语义；未在 README 中写过程流水、未来承诺或实现细节。验证通过：`git diff --check` clean；
AgentDS 额外 `python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations。Accepted slice
commit 为 `e50dee4`。当前 gate 为 P9.5 S18 Aggregate Validation And Readiness Evidence implementation。

### 2026-05-17 P9.5 S16 Contract Ownership Audit And Import/Public Surface Fixes accepted

P9.5 S16 Contract Ownership Audit And Import/Public Surface Fixes 已完成。Implementation artifact 为
`docs/reviews/p9-5-s16-contract-ownership-audit-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s16-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s16-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s16-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 PASS，0 blocking findings。S16 作为
Contract Ownership audit / guardrail slice 被接受为 test-only 变更；未发现需要移动 public contract、修改
生产代码或创建兼容 wrapper 的直接违规。新增测试明确防止 `dayu.contracts` 反向依赖 `dayu.runtime`；
Engine 直接导入 `dayu.contracts.tool_declaration`、`ToolDefinition`、`ToolBundle` 或 `ToolCallable`；
Host 使用 `importlib` / `pkgutil` 扫描业务工具模块；以及 `fetch_more` 字符串出现在 ToolRuntime owner
之外。`fetch_more` 行为测试补充验证 ToolRuntime factory 每次创建 attempt-local `EffectiveToolBundle` 与
独立 `FetchMoreToolCallable`，且不污染业务 `ToolBundle`。Public exports 未变更，`dayu.engine.__all__` /
`dayu.host.__all__` 既有白名单测试仍是公共表面真源。README 未更新：本次只补既有 Contract Ownership
规则的测试 guard，不改变 API、分层、ToolRuntime/fetch_more 行为或测试运行约定。验证通过：S16 baseline
targeted tests 为 71 passed；S16 targeted tests 为 77 passed；AgentDS 额外 `pytest tests/host -q` 为
562 passed；`python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `f1f903d`。当前 gate 为 P9.5 S17 Documentation And Control Tracking
implementation。

### 2026-05-17 P9.5 S15 Engine / Host Necessary Logs By Level accepted

P9.5 S15 Engine / Host Necessary Logs By Level 已完成。Implementation artifact 为
`docs/reviews/p9-5-s15-necessary-logs-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s15-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s15-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s15-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentDS review 为 PASS，0 blocking findings；AgentMiMo 的 Engine / dispatch scope gap
finding 不作为 blocking 接受。S15 plan 明确要求先审计现有日志并只补必要日志，Engine agent 与 OpenAI
runner 已有 run / iteration / runner call / tool loop / terminal、provider protocol、idle / cancellation 等
日志覆盖，当前没有直接证据表明还存在必要缺口；机械修改 Engine 会增加日志噪音与敏感字段回归面。Host
侧补齐 public command accepted / committed、admission committed、EngineEvent ingest accepted / committed、
LocalProxy accept / event stream opened / close、ToolRuntime accept barrier、awaiting accept、resolve_wait、
memory projection catch-up / repair 等已实现路径日志；projection catch-up failure 从 error/exception 语义校准为
recoverable `WARNING`，只记录 `error_type`，不输出 exception message 或 traceback。新增 caplog 测试覆盖
command、LocalProxy、memory catch-up、resolve_wait、ToolRuntime accept 与 projection catch-up warning 级别 /
字段 / 脱敏。S15 未新增 audit / tool trace / outbox sink，日志仍不作为 truth、public API、projection
checkpoint 或恢复输入。README 未更新：现有 `dayu/README.md` 日志级别语义、字段词汇、脱敏与“日志非真源”
说明仍准确，本次只实现既有规则。验证通过：5 条 logging focused tests passed；293 条
Engine/Host logging / diagnostics / dispatch / ingest / projection / toolruntime 选择集 passed；163 条 touched
Host subset passed；`pytest tests/host` 为 559 passed；`python -m pyright dayu tests` 为 0 errors /
0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit 为 `743bd30`。当前 gate 为
P9.5 S16 Contract Ownership Audit And Import/Public Surface Fixes implementation。

### 2026-05-17 P9.5 S14 P9 Memory Cleanup And Production Catch-Up Wiring accepted

P9.5 S14 P9 Memory Cleanup And Production Catch-Up Wiring 已完成。Implementation artifact 为
`docs/reviews/p9-5-s14-memory-cleanup-catchup-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s14-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s14-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s14-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 PASS，0 blocking findings。S14 保持
`current_goal` first-write-wins 生产实现不变，只补多输入与 inline-delta targeted tests；删除 unused legacy
`read_run_input_continuity_events(...)` / `EventLogStore.read_run_input_continuity_events(...)`，未保留兼容 wrapper
或 re-export；`DurableSessionContinuityProvider` 仍只保留 resume-specific continuity，不发射 historical raw turns。
S14 补齐 preview / reasoning / display-only event exclusion、memory import-boundary automation，以及显式 concrete
catch-up port 对 start_run user input、ToolRuntime accepted tool fact、`resolve_wait` committed tool fact 的端到端测试。
实现还修复了无 `payload_ref` 工具事实写 durable memory item 时误写 `payload_digest` 导致 schema CHECK 失败的
root cause。Controller 复核时曾发现 generic concrete catch-up 默认接入 command handle / scheduler 会在 queued
future input 场景把 latest-only snapshot 推过当前 dispatch cursor，触发 S14 stop condition；最终裁决为不默认接入
generic post-commit catch-up，仅保留显式注入与 dispatch worker 前 cursor-bound catch-up。验证通过：S14 targeted
tests 为 7 passed / 12 passed / 59 passed；regression tests 为 3 passed；`pytest tests/host` 为 554 passed；
`python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations；`git diff --check` clean。
Accepted slice commit 为 `4b7d1a5`。当前 gate 为 P9.5 S15 Engine / Host Necessary Logs By Level implementation。

### 2026-05-17 P9.5 S13 Message / Tool Result Size Governance accepted

P9.5 S13 Message / Tool Result Size Governance 已完成。Implementation artifact 为
`docs/reviews/p9-5-s13-message-tool-result-size-governance-implementation-20260517.md`。Code review /
re-review / controller adjudication artifacts 为 `docs/reviews/p9-5-s13-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s13-code-review-ds-20260517.md`、
`docs/reviews/p9-5-s13-code-re-review-ds-20260517.md` 与
`docs/reviews/p9-5-s13-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 PASS，0 blocking findings。Controller 接受 DS O1/O4 为
S13 内应修复问题：Engine per-iteration inline guard 必须有 run loop 集成测试；Assistant tool call arguments 也是
回送 Runner 的 inline message 边界。Fix 已将 Assistant tool call id / name / arguments JSON / Gemini provider_state
signature 纳入 `_message_inline_texts(...)`，并补 `test_oversized_assistant_tool_call_arguments_require_context_boundary`
与 `test_oversized_tool_message_fails_before_next_runner_call`。DS re-review 确认 O1/O4 fixed，0 new blocking。
不阻塞项包括 Engine / Host inline 阈值暂独立定义、defensive failure 不 emit `CONTEXT_COMPACTION_REQUESTED`、
oversized `fetch_more` continuation 失败时 cursor 保留到 TTL、ToolRuntime truncation path 与总 outcome path 双重大小检查。
S13 未新增 public error taxonomy，未实现 P10 proactive compaction，未改变 Host / Engine 分层。本地验证通过：
S13 targeted tests 为 115 passed；`pytest tests/host tests/engine` 为 913 passed；`python -m pyright dayu tests`
为 0 errors / 0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit 为 `8b3718d`。
当前 gate 为 P9.5 S14 P9 Memory Cleanup And Production Catch-Up Wiring implementation。

### 2026-05-17 P9.5 S12 ToolRuntime Truncation / Duplicate Defensive Hardening accepted

P9.5 S12 ToolRuntime Truncation / Duplicate Defensive Hardening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s12-toolruntime-truncation-duplicate-hardening-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s12-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s12-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s12-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings。实现补齐 `text_lines`、
`list_items`、`binary_bytes`、used cursor 与 invalid limit 的 truncation / `fetch_more` focused tests，
收紧 `ToolFactAcceptCandidate` 对 ordinary result facts、plain governed error、duplicate governed outcome 与 `REUSE`
fact 的 policy kind、prior refs、reason 和 message 一致性校验，并确认 `TruncationManager` 初始化是 run-scoped
轻量对象，无 Phase 15 production scale reassignment 需求。MiMo residual risks 与 DS observation 均裁决为 non-blocking：
truncation cursor 仍是 memory / run-scoped / ToolRuntime-local capability；duplicate registry 仍是同进程 run-local
memory；`ToolPolicyDecisionKind` 与 `DuplicateDecisionKind` 的 value 对齐可在 S16 Contract Ownership audit 中复核。
本地验证通过：S12 targeted tests 为 60 passed；`pytest tests/host/test_toolruntime_*.py tests/host/test_phase6_toolruntime_integration.py`
为 67 passed；`pytest tests/host` 为 544 passed；`python -m pyright dayu/host tests/host` 为 0 errors /
0 warnings / 0 informations；`python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。Accepted slice commit 为 `df8d636`。当前 gate 为 P9.5 S13 Message / Tool Result
Size Governance implementation。

### 2026-05-17 P9.5 S11 ToolRuntime Boundary Cleanup accepted

P9.5 S11 ToolRuntime Boundary Cleanup 已完成。Implementation artifact 为
`docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-implementation-20260517.md`。Code review / fix /
re-review / controller adjudication artifacts 为 `docs/reviews/p9-5-s11-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s11-code-review-ds-20260517.md`、
`docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-fix-20260517.md`、
`docs/reviews/p9-5-s11-code-re-review-ds-20260517.md` 与
`docs/reviews/p9-5-s11-code-review-controller-adjudication-20260517.md`。

Controller 裁决：S11 只把 ToolRuntime effective schema projection / digest helper 抽到私有
`dayu.host.tool_runtime_schema_projection`，保留 `ToolRuntimeHandle`、factory、accept barrier、EventLog facts、
duplicate semantics、truncation cursor scope、diagnostics 与 `dayu.host.tool_runtime` public `__all__` 不变。
该取舍避免 compatibility re-export、test-only private re-export、facade、lazy import seam、public API 变化、
ToolRuntime 下沉到 `contracts` / `runtime` 或 Engine 拥有工具声明 / 执行治理。AgentMiMo review 为 0 blocking；
AgentDS review 接受 1 个 LOW finding：Engine tool ownership import-boundary 测试未覆盖
`from dayu.contracts.tool_declaration import *`。Fix 已将该 star import 窄范围展开为 `ToolBundle` /
`ToolDefinition` 违规并补合成源码测试，AgentDS re-review 确认 fixed，0 blocking。本地验证通过：S11
targeted tests 为 46 passed；`pytest tests/host/test_toolruntime_*.py` 为 55 passed；`pytest tests/host tests/engine`
为 897 passed；`python -m pyright dayu tests` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `f026a53`。当前 gate 为 P9.5 S12 ToolRuntime Truncation / Duplicate
Defensive Hardening implementation。

### 2026-05-17 P9.5 S10 Host Dispatch Lifecycle / RunInputBuilder Non-Recovery Cleanup accepted

P9.5 S10 Host Dispatch Lifecycle / RunInputBuilder Non-Recovery Cleanup 已完成。Implementation artifact 为
`docs/reviews/p9-5-s10-dispatch-runinput-non-recovery-cleanup-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s10-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s10-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s10-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings。两份 review 均确认 S10
未引入 Phase 11 recovery、`RECOVERING` dispatch、startup recovery scan、orphan proof、RemoteProxy 或状态机语义变更。
实现覆盖 `_drain_loop` 空队列 / close / 异常退出可观测性、lane acquire 后 pre-accept cancel race 的 lane release
与 no-worker-call、worker stream exception 后 active registry 注销 / worker handle close / lane token release、
RunInputBuilder stale snapshot identity fail-closed，以及 late `resolve_wait` rejection 不触发 projection catch-up、
不创建 resume Attempt、不追加 resume facts。MiMo 与 DS 的 info / low findings 均裁决为 non-goal、non-blocking
或后续 owner 风险：`_drain_loop` 异常退出后的重启 / watchdog / startup recovery scan 归 Phase 11 lifecycle /
recovery owner；late rejection 后 read model 即时刷新通过后续成功 command 或显式 repair / catch-up 处理；测试 helper
复用与其它 late rejection reason 的更细专项测试归后续 wait / test hardening owner。本地验证通过：S10 targeted
tests 为 65 passed；`pytest tests/host` 为 532 passed；`python -m pyright dayu/host tests/host` 为
0 errors / 0 warnings / 0 informations；`python -m pyright dayu tests` 为 0 errors / 0 warnings /
0 informations；`git diff --check` clean。Accepted slice commit 为 `c32b370`。当前 gate 为 P9.5 S11
ToolRuntime Boundary Cleanup implementation。

### 2026-05-17 P9.5 S9 Runtime Lane Hardening accepted

P9.5 S9 Runtime Lane Hardening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s9-runtime-lane-hardening-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s9-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s9-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s9-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings。两份 review 均确认
`Task.cancel()` 透传、`CancellationToken` 返回 `LaneAcquireCancelled`、取消优先于 timeout、repeated outer
cancellation 不打断已插入 claim cleanup，untracked release failure 通过 warning / `RuntimeLaneError`
暴露，`LaneController.close(reason=...)` 保持 best-effort release 且不引入 Host truth。MiMo info
observation 与 DS residual risks 均裁决为 non-goal 或未来扩展风险，不需要 S9 fix。本地验证通过：S9
targeted tests 为 31 passed；`pytest tests/runtime` 为 93 passed；`python -m pyright dayu/runtime tests/runtime`
为 0 errors / 0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit
为 `d40a3cc`。当前 gate 为 P9.5 S10 Host Dispatch Lifecycle / RunInputBuilder Non-Recovery Cleanup
implementation。

### 2026-05-17 P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening accepted

P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s8-engine-wait-confirmation-matching-ref-implementation-20260517.md`。Code review /
controller adjudication artifacts 为 `docs/reviews/p9-5-s8-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s8-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s8-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings。两份 review 均确认
`TOOL_AWAITING` / `RUN_SUSPENDED` 只在 Host durable accepted wait record、canonical refs、envelope
identity 与 Engine awaiting record 匹配时记为 diagnostic confirmation；缺失或不匹配只 diagnostic /
rejection，不创建 wait record、不推进 Run `WAITING`、不关闭 Attempt、不追加 canonical tool fact。MiMo
info observations 与 DS residual risks 均裁决为后续语义扩展风险，不需要 S8 fix。本地验证通过：S8
targeted tests 为 38 passed；`pytest tests/host` 为 527 passed；`python -m pyright dayu/host tests/host`
为 0 errors / 0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit
为 `31a1ee5`。当前 gate 为 P9.5 S9 Runtime Lane Hardening implementation。

### 2026-05-17 P9.5 S7 LocalProxy Close / Events Race accepted

P9.5 S7 LocalProxy Close / Events Race 已完成。Implementation artifact 为
`docs/reviews/p9-5-s7-local-proxy-close-events-implementation-20260517.md`。Code review / fix /
re-review / controller adjudication artifacts 为 `docs/reviews/p9-5-s7-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s7-code-review-ds-20260517.md`、`docs/reviews/p9-5-s7-fix-20260517.md`、
`docs/reviews/p9-5-s7-code-re-review-mimo-20260517.md`、
`docs/reviews/p9-5-s7-code-re-review-ds-20260517.md` 与
`docs/reviews/p9-5-s7-code-re-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS 初审均为 0 blocking findings。AgentMiMo F1 指出 active
`anext()` task 在极窄竞争窗口以非取消异常完成时可能跳过底层 Engine generator `aclose()`，被接受为
resource-boundary hardening fix；修复后 AgentMiMo / AgentDS re-review 均确认 fixed 且无新 blocking finding。
本地验证通过：S7 targeted tests 为 49 passed；`pytest tests/host` 为 521 passed；
`python -m pyright dayu/host tests/host` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `2f8cf91`。当前 gate 为 P9.5 S8 Engine Wait Confirmation Matching-Ref
Hardening implementation。

### 2026-05-17 P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract accepted

P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract 已完成。Implementation artifact 为
`docs/reviews/p9-5-s6-read-api-enum-reset-implementation-20260517.md`。Code review / controller adjudication
artifacts 为 `docs/reviews/p9-5-s6-code-review-mimo-20260517.md` 与
`docs/reviews/p9-5-s6-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo review 为 0 blocking findings；F1 enum 双重防御、F2 timeline kind closed set
同步、F3 terminal Run status closed set 同步均裁决为 info observation，无需 fix。AgentDS 在 S6 review
中压缩后跑偏到旧 S2 上下文，窄 prompt 重试后仍未产出 artifact，裁决记录为 reviewer unavailable 而不继续阻塞流程。
本地验证通过：`pytest tests/host` 为 517 passed；`python -m pyright dayu/host tests/host` 为 0 errors /
0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit 为 `39d3582`。当前 gate 为
P9.5 S7 LocalProxy Close / Events Race implementation。

### 2026-05-17 P9.5 S5 Schema CHECK Hardening accepted

P9.5 S5 Schema CHECK Hardening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s5-schema-check-hardening-implementation-20260517.md`。Code review / controller
adjudication artifacts 为 `docs/reviews/p9-5-s5-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s5-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s5-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings；MiMo 两个 info observation 均裁决为
S5 预期结果或分层正确性，无需 fix。本地验证通过：`pytest tests/host` 为 502 passed；
`python -m pyright dayu/host tests/host` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `12f90c6`。当前 gate 为 P9.5 S6 Read API Enum Mapping And Minimal Read Model
Reset Contract implementation。

### 2026-05-17 P9.5 S4 Host Durable Helper API Tightening accepted

P9.5 S4 Host Durable Helper API Tightening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s4-host-durable-helper-tightening-implementation-20260517.md`。Code review / fix /
controller adjudication artifacts 为 `docs/reviews/p9-5-s4-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s4-code-review-ds-20260517.md`、
`docs/reviews/p9-5-s4-fix-20260517.md` 与
`docs/reviews/p9-5-s4-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS review 均为 0 blocking findings；AgentDS F1 / AgentMiMo F1
关于 Python 前置检查与 SQL CAS 双重检查意图说明不足被接受为 low documentation fix，并已通过
`docs/reviews/p9-5-s4-fix-20260517.md` 关闭。本地验证通过：
`pytest tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_resolve_wait_command.py
tests/host/test_public_cancel_session_runs.py tests/host/test_run_input_builder.py tests/host/test_phase6_toolruntime_integration.py
tests/host/test_toolruntime_accept_barrier.py` 为 103 passed；`pytest tests/host` 为 500 passed；
`python -m pyright dayu/host tests/host` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `e5e13e4`。当前 gate 为 P9.5 S5 Schema CHECK Hardening implementation。

### 2026-05-17 P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation accepted

P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation 已完成。Implementation artifact 为
`docs/reviews/p9-5-s3-host-public-error-command-handle-implementation-20260517.md`。Code review / controller
adjudication artifacts 为 `docs/reviews/p9-5-s3-code-review-mimo-20260517.md` 与
`docs/reviews/p9-5-s3-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo review 为 0 blocking findings；F1 `_run_read` / `_run_write` 双层 durable error
转换、F2 `resolve_wait` closed guard 风格、F3 generic durable subtype fallback 均为 info observation，无需当前
slice fix。AgentDS 在两次 S3 review dispatch 与一次窄 prompt 后仍未产出 artifact，裁决记录为 reviewer unavailable
而不继续阻塞流程。本地验证通过：`pytest tests/host/test_command_handle.py tests/host/test_package_exports.py
tests/host/test_public_contracts.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py` 为
69 passed；`python -m pyright dayu/host tests/host` 为 0 errors / 0 warnings / 0 informations；`git diff --check`
clean。Accepted slice commit 为 `02a75ec`。当前 gate 为 P9.5 S4 Host Durable Helper API Tightening implementation。

### 2026-05-17 P9.5 S2 Engine / OpenAI Runner / Parser Hardening accepted

P9.5 S2 Engine / OpenAI Runner / Parser Hardening 已完成。Implementation artifact 为
`docs/reviews/p9-5-s2-engine-openai-runner-parser-implementation-20260517.md`。Code review / fix / re-review
artifacts 为 `docs/reviews/p9-5-s2-code-review-ds-20260517.md`、
`docs/reviews/p9-5-s2-code-review-controller-adjudication-20260517.md`、
`docs/reviews/p9-5-s2-fix-20260517.md`、
`docs/reviews/p9-5-s2-code-re-review-mimo-20260517.md`、
`docs/reviews/p9-5-s2-code-re-review-ds-20260517.md` 与
`docs/reviews/p9-5-s2-code-re-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentDS 初审为 0 blocking findings，但 F1 `_OpenAIUsage` dead code、F2 bool index in
`_coerce_tool_call_delta` 与 F3 bool index in `ToolCallAggregator._resolve_index` 被 controller 接受为 required fix。
Fix 后 AgentMiMo / AgentDS re-review 均确认 fixed，new blockers 为 0。本地验证通过：
`pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_engine_event_contract.py`
为 229 passed；`python -m pyright dayu/engine tests/engine` 为 0 errors / 0 warnings / 0 informations；
`git diff --check` clean。Accepted slice commit 为 `5fd28be`。当前 gate 为 P9.5 S3 Host Public Error Taxonomy
And Command Handle Encapsulation implementation。

### 2026-05-17 P9.5 S1 Engine Runner Protocol Decoupling accepted

P9.5 S1 Engine Runner Protocol Decoupling 已完成。Implementation artifact 为
`docs/reviews/p9-5-s1-engine-runner-protocol-implementation-20260517.md`。Code review artifacts 为
`docs/reviews/p9-5-s1-code-review-mimo-20260517.md`、
`docs/reviews/p9-5-s1-code-review-ds-20260517.md` 与
`docs/reviews/p9-5-s1-code-review-controller-adjudication-20260517.md`。

Controller 裁决：AgentMiMo 与 AgentDS 均为 0 blocking findings；非阻塞 observations 均裁决为不需要当前 slice fix。
本地验证通过：`pytest tests/engine/test_protocols_surface.py tests/engine/test_agent_phase2.py
tests/engine/test_agent_phase3_tool_call.py` 为 66 passed；`python -m pyright dayu/engine tests/engine` 为 0 errors /
0 warnings / 0 informations；`git diff --check` clean。Accepted slice commit 为 `e89969a`。当前 gate 为
P9.5 S2 Engine / OpenAI Runner / Parser Hardening implementation。

### 2026-05-17 P9.5 implementation-ready plan accepted

P9.5 Pre-P10 Cross-Repository Hardening PR implementation-ready handoff plan 已生成并通过双路 plan review、controller
adjudication、plan fix 与双路 re-review。Plan artifact 为 `docs/host/p9-5-pre-p10-hardening-plan.md`。

Plan review artifacts：
- AgentMiMo：`docs/reviews/p9-5-plan-review-mimo-20260517.md`
- AgentDS：`docs/reviews/p9-5-plan-review-ds-20260517.md`
- Controller adjudication：`docs/reviews/p9-5-plan-review-controller-adjudication-20260517.md`

Plan re-review artifacts：
- AgentMiMo：`docs/reviews/p9-5-plan-re-review-mimo-20260517.md`
- AgentDS：`docs/reviews/p9-5-plan-re-review-ds-20260517.md`
- Controller adjudication：`docs/reviews/p9-5-plan-re-review-controller-adjudication-20260517.md`

Controller 裁决：AgentDS F1 / F2 作为 required plan fix 接受并已修复；其余 accepted non-blocking guidance 已写回
plan。两份 re-review 均确认 accepted findings fixed，new blockers 为 0。Accepted plan commit 为 `ed72437`。

S0 Controller Preflight And Scope Lock 已完成，artifact 为
`docs/reviews/p9-5-s0-controller-preflight-implementation-20260517.md`。S0 验证结果：当前分支为
`p9.5-pre-p10-hardening`，worktree clean，`source .venv/bin/activate && python -m pyright dayu tests` 为
0 errors / 0 warnings / 0 informations。当前 gate 为 P9.5 S1 Engine Runner Protocol Decoupling implementation。

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
不是聊天记录压缩器；memory view 分为 `pinned_state`、`evidence_backed_facts`、`working_assumptions`、
`conversation_continuity`；evidence-backed facts 只接受工具事实并保留 evidence / provenance refs；RunInputBuilder 注入顺序按财报分析优先级固定；
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
