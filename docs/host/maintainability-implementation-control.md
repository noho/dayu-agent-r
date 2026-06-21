# Maintainability Implementation Control

## 文档职责

本文档是后续维护性治理的实施总控文档，专门处理 God Function、God Object、God Module scale risk 和相关结构性可维护性问题。

本文档只承担实施编排职责：记录维护性 work unit 的范围、当前状态、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。本文档不替代设计真源，不承载新的架构决策，不作为实现细节说明书。

维护性治理的核心目标是降低代码理解、修改、测试和 review 成本；默认不改变业务行为、公共接口、durable schema、EventLog 语义、状态机或跨层契约。若某个拆分必须改变这些边界，必须先进入设计讨论并同步对应设计真源，不能以“清理代码”为名顺手改架构。

## 设计目标

维护性治理必须始终服务于以下目标：

- 保持生产级通用 Agent 的行为稳定，并保留买方财报分析能力。
- 保持“宿主强约束下的 LLM in the loop”架构不变。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界，禁止反向依赖和跨层泄漏实现细节。
- 拆分 God Function / God Object 时，只沿真实职责边界切分，不制造胶水 seam、兼容 wrapper、god config bag 或无语义 owner 的 helper。
- 每个 work unit 必须能用现有测试、补充测试和 pyright 验证行为不变。
- 优先拆高风险、改动频率高、review 成本高的核心路径；不为了行数指标做机械拆分。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。

## 真源层级

维护性治理遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源

docs/host/design.md
  -> Host 架构真源
  -> 维护 Host dispatch、ingest、ToolRuntime、durable state、admission 等模块时必须同步核对

docs/engine/design.md
  -> Engine 架构真源
  -> 维护 Agent、Runner、provider parser / serializer、tool-calling contract 时必须同步核对

docs/reviews/repo-review-20260531-165918.md
  -> 本轮维护性治理的 review finding 来源之一
  -> 其中 God Function finding 和模块规模 residual risk 是本文档的主要输入

GitHub Issue #33
  -> LocalRunHarness God Object 旧追踪项
  -> 当前 `LocalRunHarness` 已不存在，但其底层风险迁移为当前 Host dispatch / ingest orchestration 大对象治理

docs/host/maintainability-implementation-control.md
  -> 维护性治理实施编排文档
```

本文档不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`ToolRuntime`、`Conversation Memory`、provider tool-calling 等稳定术语。若拆分时发现术语或 ownership 不清，应先讨论并同步设计真源。

## Phaseflow 调用约定

本文档可以作为 `$phaseflow` 的 `control_doc` 使用。因为维护性治理同时覆盖 Host 与 Engine，启动时应按当前 work unit 选择主 `design_doc`：

- Host 相关 work unit，例如 `WU-MAINT-03`、`WU-MAINT-04`、`WU-MAINT-06` 中涉及 Host 模块的部分，使用 `docs/host/design.md` 作为主 `design_doc`。
- Engine 相关 work unit，例如 `WU-MAINT-01`、`WU-MAINT-02`，使用 `docs/engine/design.md` 作为主 `design_doc`。
- `WU-MAINT-00` 是 inventory / controller work，默认使用 `docs/host/design.md` 启动，并在刷新指标时同时核对 `docs/engine/design.md`。

示例：

```text
$phaseflow design_doc=docs/host/design.md control_doc=docs/host/maintainability-implementation-control.md
```

若当前 work unit 跨 Host / Engine 边界，controller 必须读取两个设计真源；主 `design_doc` 只决定 phaseflow 的启动锚点，不排除另一个设计文档作为约束来源。

## 工作流

维护性 work unit 采用以下工作流：

```text
finish issue-backed implementation backlog
  -> read maintainability-implementation-control.md
  -> select one work unit
  -> refresh code metrics and inspect current code/tests
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update design truth first if ownership or public contract changes are needed
  -> generate behavior-preserving code-generation-ready plan
  -> review plan
  -> user confirmation
  -> implement in small slices
  -> verify affected tests, broader regression tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须重新核对当前代码，因为维护性治理很容易被前置 issue 的实现改变目标形态。

plan 必须基于：

- 当前设计真源；
- 本文档中对应 work unit 的状态、目标、非目标和验收信号；
- 当前代码和测试的直接证据；
- 最新 review / deepreview artifact。

plan 不得从旧代码路径、旧类名、旧 review finding 或行数指标直接推导实现方案。
plan 必须避免过度设计；只能解决由当前代码、测试、设计真源和最新 review artifact 直接支撑的维护性风险，不得把局部拆分扩大成通用框架、平台化能力或未来阶段能力。

## 仓库发布约定

维护性治理相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners 和 next entry point。进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

- 每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。
- slice 切分的初始出发点成立：单个 slice 太大时，implementation agent 容易因为上下文过长、局部约束丢失或跨边界状态过多而实现漂移。
- slice 必须控制模型一次实施和 reviewer 一次审查能够稳定承载的上下文规模。
- “上下文规模”不得粗暴等同于文件数、模块数、代码行数或 owner 数；更可靠的切分依据是语义闭环、依赖顺序、失败 / 回滚风险和验证矩阵。
- slice 必须满足模型上下文窗口与 review 可承载复杂度：implementation agent 能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 能在一个上下文中有效审查。
- slice 必须沿稳定代码依赖边界切分：公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界。
- slice 必须形成可独立验证的行为闭环：大到能形成可测试语义，小到能一次实现、一次验证、一次 review。
- 除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。
- slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理；好的 slice 必须有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。
- 不得按模块数量、文件数量或 reviewer ownership 机械拆分。对代码量较小、语义上属于同一个 contract cleanup / config cleanup / schema cleanup 的 work unit，即使会同时触及配置、runtime、Service composition、provider、scene manifest、测试和 README，也应优先合并为少量可验证闭环 slices，而不是每个模块单独切片。
- 只有当某部分存在独立失败 / 回滚风险、需要独立设计裁决、会阻塞后续代码导入，或 review 上下文确实无法承载时，才继续拆分。
- 小型跨模块 cleanup 的默认切分上限是 3 个 implementation slices：
  - contract / config / composition slice：稳定公共语义、typed config、composition root effective config、旧字段拒绝与基础测试；
  - provider / behavior slice：业务 provider 行为、tool schema、存储 / 权限边界、provider 投影测试；
  - scene / docs / final validation slice：默认 scene 暴露面、README / design 同步、stale-field grep、pyright 与受影响测试矩阵。
- 默认 slice budget：
  - 小型同一语义 cleanup：1-3 个 implementation slices。
  - 中型跨 contract / provider / projection work：3-5 个 implementation slices。
  - 超过 5 个 implementation slices：必须有明确证据表明单个 implementation agent / reviewer 的上下文容量无法稳定承载，或存在必须隔离的 schema、状态机、持久化、外部依赖、回滚风险。
- 如果 plan 提出超过 3 个 implementation slices，必须显式说明为什么不能按上述闭环合并；仅以“涉及多个文件 / 多个模块 / 多个 owner”为理由不充分。
- 总控裁决时必须评估 gate 成本：每增加一个 slice 都会增加 implementation artifact、双路 review、controller 裁决、测试复跑和 accepted commit 成本；当流程成本明显超过实现风险时，应倾向合并 slice。
- 如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。
- 如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。
- 维护性 slice 必须比 feature slice 更保守：每个 slice 默认行为不变；除非 work unit 明确包含行为修复，否则不得混入 correctness fix。
- 维护性 slice 应优先提取纯函数、typed value object、私有 helper、职责明确的 collaborator。
- 维护性 slice 拆核心循环或调度路径前，必须先补 characterization tests。
- 维护性 slice 拆分后必须能解释新 owner 的职责；不接受只为缩短函数而增加的透传层。
- 维护性 slice 不应同时拆 Engine 核心循环、Host dispatch、durable schema 和 ToolRuntime。
- 如果某个函数需要跨多次 slice 才能拆完，每次 slice 都必须保持可运行、可 review、可回滚。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | maintainability cleanup backlog |
| gate | blocked-by-issue-backlog |
| implementation status | not-started |
| active work unit | none selected |
| default next work unit | WU-MAINT-00 |
| next entry point | 等 issue-backed backlog 全部实施完毕后，先刷新代码指标与 review finding，再讨论 WU-MAINT-00 |
| design source | `docs/host/design.md`、`docs/engine/design.md`，按触及层级核对 |
| source review artifact | `docs/reviews/repo-review-20260531-165918.md`; `docs/reviews/repo-review-20260604-220925.md`; `docs/reviews/repo-review-20260604-220415.md`; `docs/reviews/repo-review-20260604-controller-adjudication.md` |
| related GitHub Issue | #33 |
| plan artifacts | none |
| implementation commits | none |
| review artifacts | none |
| draft PR status | not-started |
| blocking open questions | 等 issue-backed backlog 完成后，重新确认哪些 God Function / God Object 仍存在 |

状态约定：

- `blocked-by-issue-backlog`：必须等待 issue-backed backlog 全部完成后才能进入 discussion。
- `discussion-ready`：已具备讨论和代码核对入口，但还未形成 code-generation-ready plan。
- `planning`：正在形成或 review code-generation-ready plan。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。
- `obsolete`：代码已变化，原 work unit 不再成立。

## 推进规则

- 所有 issue-backed work units 完成前，不启动本文档中的 implementation gate。
- 每个 work unit 开始前必须重新跑代码规模 / AST 指标，避免按旧 review finding 实施过期目标。
- 先补测试保护行为，再做拆分。
- 拆分默认不改公共行为；如果发现必须改行为，应转为普通 issue / feature / bugfix 流程。
- 不以行数为唯一目标；行数只是风险信号，真实目标是职责清晰、测试可控、review 成本下降。
- 每个 work unit 完成后必须记录剩余 God Function / God Object / module scale risk 的 owner。

## Residual Risk / 遗留问题追踪

本章节专门追踪维护性治理过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问和后续 owner。

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 | 记录 |
|---|---|---|---|---|---|---|
| RR-MAINT-01 | repo review 20260531; repo review 20260604 | module scale risk | deferred-with-owner | 本文档 WU-MAINT-06 | WU-MAINT-06 重新评估 | `dayu/host/durable/run_transition.py`、`dayu/host/tool_runtime.py`、`dayu/host/durable/state.py`、`dayu/host/admission.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/runtime/config_loader.py`、`dayu/runtime/scene_prepare.py`、`dayu/service/host_assembly.py` 等模块规模极高；20260604 full repo review 已再次确认该风险。先不在 WU-CM-01 PR closeout 中处理。 |
| RR-MAINT-02 | GitHub Issue #33 | God Object risk | deferred-with-owner | 本文档 WU-MAINT-03 / WU-MAINT-04 | issue backlog 完成后刷新代码事实 | `LocalRunHarness` 已不存在，但当前 Host dispatch / ingest orchestration 大对象仍需后续治理。 |
| RR-MAINT-03 | `docs/reviews/repo-review-20260531-223418.md` | God Object risk | deferred-with-owner | 本文档 WU-MAINT-07 | WU-MAINT-00 刷新后确认拆分边界 | `_AsyncAgent` 约 1900 行且承担 Runner 迭代、工具批量执行、fallback、取消观察、延续逻辑、事件分发和终态决策；不并入当前 audit 修复批次，进入 Engine maintainability work unit。 |

## 当前 Work Units

| Work Unit | 主题 | 当前定位 |
|---|---|---|
| WU-MAINT-00 | Refresh maintainability inventory | 入口 work unit；重新生成 God Function / God Object / module scale 指标，裁决过期项 |
| WU-MAINT-01 | Engine Agent core loop decomposition | 拆 `_AsyncAgent.run_messages()`、`_consume_runner_event()`、`_execute_tool_batch()` 等 Engine 核心循环 |
| WU-MAINT-02 | OpenAI runner request / response path decomposition | 拆 `AsyncOpenAIRunner._call_impl()` 及相关 provider request / response 组织逻辑 |
| WU-MAINT-03 | Host dispatch scheduler orchestration decomposition | 承接 #33 当前化；拆 `HostDispatchScheduler` 中 queue promotion、pre-start governance、worker lifecycle、lane / dispatch 协调职责 |
| WU-MAINT-04 | EngineEvent ingestor orchestration decomposition | 拆 `EngineEventIngestor` 中 terminal closeout、reactive compaction、wait confirmation、diagnostic payload 等职责 |
| WU-MAINT-05 | Focused long-function cleanup batch | 拆 `run_compaction_operation()`、`project_conversation_memory_event()`、`merge_agent_policy_config()`、`_build_purge_precondition_digest()`、`_create_steer_attempt_result()` |
| WU-MAINT-06 | God module scale assessment | 评估并规划超大模块拆分时机，不直接机械拆文件 |
| WU-MAINT-07 | Engine `_AsyncAgent` responsibility decomposition | 拆分 `_AsyncAgent` 的 Runner 迭代、工具执行、fallback、终态决策和取消观察职责 |

## WU-MAINT-00 Refresh Maintainability Inventory

### 状态

`blocked-by-issue-backlog`。等 issue-backed backlog 全部完成后再启动。

### 目标

- 重新扫描当前代码中的超长函数、超大类、超大模块和高耦合 orchestration object。
- 对照 `docs/reviews/repo-review-20260531-165918.md`，标记仍存在、已消失、已被前置 issue 吸收或需要改写的 finding。
- 更新本文档 work unit 顺序、范围和进入条件。
- 更新 GitHub Issue #33 的当前化描述，说明 `LocalRunHarness` 已不存在，后续治理转向当前 Host dispatch / ingest orchestration。

### 非目标

- 不直接重构代码。
- 不关闭任何现有测试缺口。
- 不把普通 correctness bug 混入维护性治理。

### 验收信号

- 有新的 metrics / inventory artifact。
- 本文档 work unit 和 #33 均基于当前代码事实更新。
- 所有过期项有明确关闭依据，仍有效项有明确 owner。

## WU-MAINT-01 Engine Agent Core Loop Decomposition

### 状态

`blocked-by-issue-backlog`。需等待 issue-backed backlog 完成，并等待 WU-MAINT-00 刷新后确认仍有效。

### 目标

- 拆分 Engine Agent 核心循环中的超长函数，优先关注 `_AsyncAgent.run_messages()`、`_consume_runner_event()`、`_execute_tool_batch()`。
- 保持 Agent / Runner / ToolExecutor contract 不变。
- 先补 characterization tests，覆盖普通 final answer、tool call、tool result、length continuation、force answer、cancel、provider protocol error 等核心路径。

### 非目标

- 不改变 provider protocol。
- 不改变 Host / Engine 边界。
- 不改 tool-calling 语义。

### 验收信号

- 核心循环拆分后行为测试保持通过。
- 新 helper / collaborator 有明确职责，不是透传 wrapper。
- pyright 不新增或扩散类型错误。

## WU-MAINT-02 OpenAI Runner Request / Response Path Decomposition

### 状态

`blocked-by-issue-backlog`。需等待 WU-MAINT-00 刷新后确认仍有效。

### 目标

- 拆分 `AsyncOpenAIRunner._call_impl()` 的 request preparation、HTTP call、SSE / JSON response classification、error body handling、retry / diagnostic 映射职责。
- 保持 OpenAI-compatible Runner public contract 与 parser contract 不变。

### 非目标

- 不引入新的 provider abstraction。
- 不改变 provider-specific reasoning / tool state policy；若相关 issue 尚未完成，必须等待。

### 验收信号

- 现有 OpenAI runner parser / payload / retry / cancellation 测试通过。
- 拆分后的职责边界能从函数名和参数直接读出。

## WU-MAINT-03 Host Dispatch Scheduler Orchestration Decomposition

### 状态

`blocked-by-issue-backlog`。这是 GitHub Issue #33 的当前化主要承接项之一。

### 目标

- 将 `HostDispatchScheduler` 中的 queue promotion、pre-start context governance、proactive compaction、lane acquire / release、worker startup、worker event consumption、close cleanup 等职责按 owner 拆开。
- 保持 Host public interface、durable schema、EventLog 语义和 Run / Attempt 状态机不变。
- 先保护现有 dispatch / cancel / recovery / wait / compaction 路径测试，再拆核心路径。

### 非目标

- 不把 dispatch 改成新的后台框架。
- 不把 projection、tool runtime、recovery truth 合并进 scheduler。
- 不在本条内实现新的 watchdog feature。

### 验收信号

- `HostDispatchScheduler` 只保留 scheduler orchestration 与薄协调。
- pre-start governance、worker lifecycle、lane dispatch guard 等职责有清晰 owner。
- 核心 Host dispatch、cancel、queue、wait、compact、recovery 相关测试通过。

## WU-MAINT-04 EngineEvent Ingestor Orchestration Decomposition

### 状态

`blocked-by-issue-backlog`。这是 GitHub Issue #33 的当前化承接项之一。

### 目标

- 拆分 `EngineEventIngestor` 中的 EngineEvent 分类、terminal closeout、reactive compaction、wait confirmation、provider diagnostic payload、terminal summary payload 写入等职责。
- 保持 EngineEvent ingest 作为 Host-owned state transition boundary 的语义不变。

### 非目标

- 不让 Engine 直接写 Host durable state。
- 不改变 stale execution id、late terminal、duplicate terminal、wait confirmation 的治理语义。
- 不改变 reactive compaction policy。

### 验收信号

- 每类 EngineEvent 映射仍有明确测试。
- terminal closeout 与 reactive recovery 仍能独立推理。
- pyright 不新增或扩散类型错误。

## WU-MAINT-05 Focused Long-function Cleanup Batch

### 状态

`blocked-by-issue-backlog`。需等待 WU-MAINT-00 刷新后确认列表。

### 目标

- 处理 review 中剩余的局部长函数：`run_compaction_operation()`、`project_conversation_memory_event()`、`merge_agent_policy_config()`、`_build_purge_precondition_digest()`、`_create_steer_attempt_result()`。
- 每个函数按现有语义边界提取私有 helper 或 typed value，不跨模块抢 ownership。

### 非目标

- 不一次性重写 compaction、memory、runtime assembly、purge 或 admission。
- 不修改 schema、public API 或状态机。

### 验收信号

- 每个拆分点有 targeted tests 或现有测试覆盖说明。
- 拆分后的函数职责更窄，行为保持不变。

## WU-MAINT-06 God Module Scale Assessment

### 状态

`blocked-by-issue-backlog`。只做评估和规划，不默认立即拆模块。

### 目标

- 评估 `dayu/host/durable/run_transition.py`、`dayu/host/tool_runtime.py`、`dayu/host/durable/state.py`、`dayu/host/admission.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/runtime/config_loader.py`、`dayu/runtime/scene_prepare.py`、`dayu/service/host_assembly.py` 等超大模块的真实内聚边界。
- 判断是否需要拆分为多个语义 owner 模块，或只通过前面 work units 的类 / 函数拆分降低风险。
- 若需要拆模块，给出独立 code-generation-ready plan。

### 非目标

- 不按行数机械拆文件。
- 不做兼容 re-export。
- 不引入循环依赖或反向依赖。

### 验收信号

- 有明确的模块 ownership 评估结果。
- 需要拆分的模块有独立后续 work unit 或 issue owner。
- 不需要拆分的模块有保留理由和后续观察指标。

## WU-MAINT-07 Engine `_AsyncAgent` Responsibility Decomposition

### 状态

`blocked-by-issue-backlog`。需等待 WU-MAINT-00 刷新后确认当前 `_AsyncAgent` 的真实职责边界和测试保护面。

### 目标

- 拆分 `_AsyncAgent` 中 Runner 迭代、工具批量执行、fallback 模式、终态决策、取消观察和事件分发等职责。
- 保持 Agent / Runner / ToolExecutor public contract、EngineEvent 语义和 Host / Engine 边界不变。
- 先补或确认 characterization tests，再按职责 owner 小步拆分。

### 非目标

- 不借维护性拆分改变 provider protocol、tool-calling contract 或 Host durable state。
- 不引入通用框架、平台化调度器或只做透传的胶水 collaborator。
- 不与 HTTP 实时观测、duplicate governance、context compaction 等 correctness / feature work 混在同一 work unit。

### 验收信号

- `_AsyncAgent` 不再同时承担工具执行、fallback、终态决策和 Runner 事件消费的主要实现细节。
- 新 owner 的职责能从名称、构造参数和测试边界直接读出。
- Engine agent / runner / cancellation / tool execution 相关测试通过，pyright 不新增或扩散类型错误。
