# WU-CTX-01 code-generation-ready implementation plan（AgentCodex）

## 0. Plan gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- Issue：GitHub Issue #20。
- 类型：architecture-sensitive issue / public-contract change。
- 当前 gate：`plan amendment`；本 artifact 只修复 Slice 1 stop condition 的
  Controller accepted blocker，不进入 re-review、implementation、commit、push、PR
  或 merge。
- 设计真源：`docs/host/design.md` §25 `Context Governance`，唯一设计入口为
  `Usage-Anchored Adaptive Context Sizing`。
- 控制真源：`docs/host/issues-implementation-control.md` 的 `Slice 切分原则` 与
  `WU-CTX-01 Usage-Anchored Adaptive Context Sizing` 全节。
- goal confirmation：
  `docs/reviews/wu-ctx-01-goal-confirmation-controller.md`，decision=`pass`，
  blocking open questions=`None`。
- 原 plan finding 裁决真源：
  `docs/reviews/wu-ctx-01-plan-review-controller-adjudication.md`；
  本次 amendment 裁决唯一真源：
  `docs/reviews/wu-ctx-01-slice-1-stop-controller-adjudication.md`，
  decision=`accepted blocker / reopen plan`。两路 review 只提供证据，不得覆盖
  Controller 对 owner、stage action、scope 与 partial implementation 的裁决。
- 代码基线：branch=`feat/wu-ctx-01`，
  HEAD=`5afe71fefa2486ff0e0d9b2026fee23685d48c2e`。
- preflight：当前不是 protected branch。worktree 已有大量 Slice 1 partial
  production/tests、Controller control doc 与 stop artifacts；它们必须原样保留，
  本 gate 不继续编辑。
- 本 amendment gate 允许写入仅为：
  `docs/host/design.md`、`docs/reviews/wu-ctx-01-plan-codex.md` 与
  `docs/reviews/wu-ctx-01-slice-1-plan-amendment-codex.md`。
- amendment completion status：`complete`。accepted blocker 已在 compact payload
  typed source boundary、Conversation Memory projection 与 stage-aware sizing action
  owner处收敛；当前 partial implementation仍为`not accepted`，必须等
  AgentMiMo / AgentDS双路plan re-review通过后才可恢复。

## 1. Goal、motivation 与 success signal

### 1.1 Goal

本 Work Unit 同时交付两个独立修改：

1. **provider-neutral usage-anchored adaptive sizing**
   - 对有直接、完整、兼容 lineage 的成功 ordinary runner call，冻结
     `U_anchor`、`E_anchor`，并对当前完整候选输入计算 `E_current`。
   - 预算预测固定为：

     ```text
     delta = E_current - E_anchor
     P_current = U_anchor + delta
     ```

   - `delta` 保留正负，不 clamp 为零。
   - usage 缺失、非法、歧义、pairing 不唯一、manifest/link 不完整或任一
     compatibility / lineage 条件不成立时，对**当前完整候选输入**调用同一个
     conservative estimator；Run 不因 usage 缺失或 usage 不可用失败。

2. **durable context-budget fact 与 typed public projection**
   - 每个 dispatch-relevant ordinary / post-compact / dispatch-fallback
     候选输入先提交 canonical `CONTEXT_BUDGET_EVALUATED`，再执行该 decision
     驱动的 compact、dispatch 或 fail-closed transition。
   - Host 从同一个 `ContextSizingResult` 投影
     `HostActivityKind.CONTEXT_USAGE` 与 `HostContextUsageView`。
   - Service 只把该 typed view 无重算映射为 `EntrypointContextUsage`，并沿既有
     activity callback 交付。

两项修改只共享 Host-owned exact candidate sizing result。canonical fact
不是 anchor 算法的附属事件：即使没有任何 usage、所有结果均为
`conservative_fallback`，fact、idempotency、event ordering 与 public
projection 仍必须完整成立。

Slice 1 对 compact source boundary 与 Conversation Memory projection 的修正不是第三项
产品修改；它是 complete candidate foundation 满足既有 compact/delta design truth
的前置 owner 修复。accepted compact 后，exact candidate只能包含 latest accepted
semantic view、真正的 post-compact delta、未被本次 selected compact覆盖的 protected
raw tail与current input，不能继续携带已被 compact覆盖的旧 raw。

### 1.2 Motivation 与第一性原理判断

动机成立，且 architecture-sensitive 严重性没有被高估。

Host 必须在下一候选完整输入 dispatch 前做预算判断；provider usage 只能在
response 后成为历史 observation，不能替代当前输入 sizing，更不能回写已发生
decision。usage 的唯一合理用途是校正同一 estimator 对历史完整输入的误差基线，
再把 estimator 对完整输入变化的 signed delta 加到历史真实 usage 上。

局部把 `_estimate_usage_observation_input(...)` 从 `display_text` 改成“更多文本”
仍不成立：pre-dispatch、post-compact、fallback、actual runner manifest 与 usage
pairing 必须消费同一 complete candidate snapshot，否则会形成多个估算真源。
正确修复边界是：

- RunInput / runner-call manifest owner 冻结完整候选输入和 estimator snapshot；
- Engine 只产生合法 normalized usage；
- Host ingest 只做 iteration-scoped direct pairing；
- Context Governance 选择 anchor、计算 prediction、threshold 与 pressure；
- canonical fact、公有 Host view 和 Service view只消费同一 sizing result。

### 1.3 Success signals

- compatible anchor 的正、负 delta 都精确按固定公式计算。
- `U_anchor / context_window_size = 62%`，下一输入 signed delta 使
  `P_current` 达到 65% soft threshold 时，在该候选 dispatch 前 proactive
  compact。
- 无 usage、nullable usage、非法 usage、重复/冲突 usage、link 缺失、manifest
  mismatch、lineage gap 时，当前预测严格等于对当前完整 candidate 调用既有
  conservative estimator 的结果，且不因 usage 问题失败 Run。
- 一次或多次合法的 usage 缺失不会自动丢弃较旧 compatible anchor；所有中间
  input manifests/links/accepted iteration completions完整且无compact boundary时
  允许累计到当前
  `E_current - E_anchor`。非法/歧义 usage 或任何 lineage gap 是 barrier，必须
  fallback。
- provider、model、context window、estimator id/version、request serialization
  semantics 变化，或 accepted compact，均使旧 anchor 对当前 candidate 不兼容。
- compactor proposal usage、reactive overflow、另一个 post-compact request 的
  usage 都不能成为失败 ordinary input 的伪 calibration sample。
- `CONTEXT_BUDGET_EVALUATED` 在 EventLog 中严格早于其驱动的
  `CONTEXT_COMPACTION_REQUESTED`、`RUN_STARTED` 或 `ATTEMPT_STARTED`。
- pre-start sizing 只消费不带 Attempt/execution identity 的完整 candidate，不依赖
  runner-call manifest。只有 decision=`ALLOW_DISPATCH` 后，才在同一 write
  transaction 分配并实际消费 Attempt/execution/dispatch identities，再按
  manifest、budget fact、Run/Attempt start 顺序提交；ordinary soft/hard candidate
  不写runner-call manifest，也不分配durable Attempt identity。
- start precondition/CAS miss 使同一 transaction 中新写的 projection、manifest 与
  budget fact全部 rollback；precondition miss由调用方把private rollback信号收敛为
  “本轮无dispatch”，低层CAS lost保持既有durable error传播；两者EventLog均零孤立
  manifest/fact。
- 同一 Run/candidate/stage/policy/estimator identity 在 replay/reconciliation
  中最多形成一个 context-budget truth；相同 identity 的矛盾结果 fail closed。
- public anchored `predicted_input_tokens == P_current`；fallback
  `predicted_input_tokens == conservative estimate`。
- `utilization_basis_points =
  floor(predicted_input_tokens * 10000 / context_window_size)`，不 clamp，允许
  大于 `10000`。
- public pressure 与实际 compact/dispatch decision 同源；Service 不重算任何
  token、ratio、threshold、basis points 或 pressure。
- `pressure_level`只由prediction与soft/hard thresholds决定；`budget_decision`还消费
  `ContextSizingStage`。`ORDINARY` soft触发唯一 proactive operation；
  `POST_COMPACT` / `DISPATCH_FALLBACK` soft如实保留soft pressure但允许dispatch；
  三个stage的hard都禁止dispatch并显式fail closed，不留下silent accepted Run。
- accepted compact的typed source boundary严格区分第一个`current_input_ref`与其余
  `compacted_source_refs`；memory projection删除covered older raw、保留current
  input、保留未covered protected raw，并让后续新material自然成为post-compact
  delta。rebuild、incremental、inline repair与persisted reload结果一致。
- memory selected recent与ordinary protected raw tail继续按canonical source ref与
  content digest同源去重；确有covered material时post-compact exact conservative
  size下降，没有covered material时不得通过丢current input或protected raw伪造下降。
- raw `USAGE_REPORTED` 继续没有 public activity；UI 不需要 EventLog reader。
- anchor eligibility 只由同一 attempt/execution/iteration 的 complete ordinary
  manifest、accepted link、唯一合法 usage 与 durable accepted
  `ITERATION_COMPLETED` preview共同证明；Run terminal fact本身不替代 iteration
  completion。tool loop、usage先到后失败、crash gap与terminal Run反例均
  deterministic fallback/barrier。
- 所有 changed production Python 文件 line coverage `>=80%`，完整 pyright
  零错误，受影响与最终完整测试矩阵通过。

## 2. Direct code evidence 与 root cause

| 直接证据 | 当前事实 | 对实现的约束 |
| --- | --- | --- |
| `dayu/host/context_budget.py::estimate_context_budget` | conservative estimator 按 message text、canonical JSON bytes、message overhead 与 tool-schema overhead 估算；`estimator_digest` 是具体输入 digest，不是稳定 estimator identity/version。 | 保留现有估算公式与常量；新增显式 estimator id/version 和 exact-candidate adapter，不引入 tokenizer、动态 ratio 或 correction model。 |
| `dayu/host/context_budget.py::ContextSizingResult` / `_pressure_and_decision` | 当前 partial implementation按prediction同时固定pressure与action；soft在所有stage都映射`COMPACT_SOFT_THRESHOLD`。 | pressure与action拆开判定：pressure仍纯阈值比较，action必须消费stage；post-compact/fallback soft允许dispatch，hard显式fail closed。 |
| `dayu/host/compact_payload.py::ContextCompactedSemanticPayload` / `source_boundary_refs` | producer确定性写第一个`request.current_input_ref`与后续去重material/evidence/fact refs，但strict semantic parser没有读取 persisted `source_boundary_refs`。 | compact payload是唯一typed read owner；parser校验非空、非空字符串、全局唯一并投影`current_input_ref`与`compacted_source_refs`，consumer不得索引raw list。 |
| `dayu/host/memory.py::project_conversation_memory_event` | `CONTEXT_COMPACTED`更新summary/facts/anchors/intents/reference continuity与latest compact ref，却没有移除已被accepted compact覆盖的`selected_recent_window`；`recent_evidence_items`随后仍从错误window派生。 | Conversation Memory projection按typed covered refs移除covered older raw，保留current input与未covered protected raw；rebuild/incremental/repair/persisted snapshot统一复用该owner rule。 |
| `dayu/host/run_input.py::_memory_messages`与protected raw-tail assembly | 无条件渲染snapshot selected recent；既有raw-tail path已有source ref/content digest dedupe。 | 不在RunInput新增coverage filter；只消费修正后的typed memory view并保留现有raw-tail dedupe。 |
| `dayu/host/dispatch.py::_run_pre_start_governance` | pre-start 只用 `PreDispatchCompactMaterialView.budget_fragments` 估算；allow 时直接写 `RUN_STARTED/ATTEMPT_STARTED`，没有 canonical budget fact。 | pre-start 必须先从与实际 Runner input 同源的 complete candidate 构造 typed sizing result；fact append 与后续 transition 同事务有序提交。 |
| `dayu/host/run_input.py::RunInputBuilder.build` | actual messages、tool schema 与 `RUNNER_CALL_INPUT_ASSEMBLED` 目前在 Run/Attempt 已启动后才构造/记录。 | 将“纯候选组装/投影”与“Attempt runtime handle/AgentRunRequest 构造”分离；前者可在 start 前冻结，后者必须验证并消费同一个 candidate digest，不能再次自由组装另一份输入。 |
| `dayu/host/durable/run_transition.py::StartGovernedRunInput` 与 `start_governed_run_with_starting_attempt_in_transaction` | transition 已要求调用方提供 `attempt_id`、`execution_id`、`dispatch_record_id` 与两个 start event id，并用这些精确值创建 Run/Attempt/dispatch rows；transition 自身不生成 identity。 | 不修改 durable transition owner。`dispatch.py` 只在 allow 后构造一次 typed `StartGovernedRunInput`，manifest与transition共同消费其中同一 identity。 |
| `dayu/host/durable/transaction.py::HostTransactionRunner.run_write` | transaction body正常返回即commit；任意异常会rollback并透传。 | CAS miss不得返回普通 `None`；`dispatch.py` transaction body必须抛出私有 `_StartCandidateCasMissRollback`，在 `run_write` 外捕获并转成无dispatch结果。不得修改通用 transaction runner或引入rollback sentinel返回协议。 |
| `dayu/host/_runner_call_manifest.py` 与 `RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` | manifest v1 有完整 projection/ref lineage，但没有 estimator id/version、`E_anchor`、context window 或 request semantics contract。 | manifest schema 直接切到 v2；complete ordinary manifest 必须有严格 typed sizing snapshot，v1 不兼容读取。 |
| `dayu/host/engine_ingest.py::_estimate_usage_observation_input` | 从 `USER_INPUT_ACCEPTED.display_text` 重建估算；不是实际完整 runner input。 | 删除该重建路径。usage diagnostic/pairing 只能解析 accepted iteration link 指向的 digest-verified complete manifest。 |
| `dayu/host/engine_ingest.py::_runner_call_iteration_link_payload` | accepted link 已冻结 manifest event/ref/digest、iteration id/index、Engine message count/role digest 和 serializer schema。 | 该 link 是 iteration pairing 的唯一入口；禁止 request id、时间戳或 display text 推断。 |
| `dayu/host/lifecycle_events.py::HostPreviewEventType.ITERATION_COMPLETED` 与 `engine_ingest.py::_preview_payload` | accepted Engine `iteration_completed` 已作为 durable preview保存 exact attempt/execution、iteration id与finish reason；它不是 canonical completion fact。 | 复用该现有 durable accepted Engine evidence作为 runner-call completion barrier，不新增 iteration completion canonical fact/state machine，也不从 Run terminal状态反推。 |
| `dayu/engine/runners/openai/usage.py::coerce_usage` | provider usage 三字段只有在 non-bool、non-negative int 时才归一；缺失/非法返回 `None`。 | Engine production behavior 已符合 owner；不新增 Engine→Host 依赖。Host 仍须防御 injected/corrupt observation，但不能把 `supports_stream_usage` 当 presence predicate。 |
| `dayu/engine/runners/openai/payload.py` | `supports_stream_usage` 只决定 stream request 是否写 `include_usage=True`。 | 保持不变；anchor eligibility 只看实际合法 durable usage。 |
| `dayu/host/context_fallback.py::estimate_recent_window_fallback_budget`、`compaction_operation.py::estimate_post_compact_budget`、reactive ingest sizing | fallback、post-compact、reactive 各自使用不同粒度 helper。 | 所有 dispatch-relevant candidate 统一先形成 complete candidate snapshot，再由唯一 sizing owner计算；internal compactor proposal sizing不产生 public activity。 |
| `dayu/host/lifecycle_events.py` / `durable/schema.py` | event type closed set中没有 `CONTEXT_BUDGET_EVALUATED`。 | 新 canonical fact 加入 Host Context Governance event type 真源；按全新数据库 schema 更新，不写 migration/兼容 branch。 |
| `dayu/host/read_api.py::_activity_from_row` | public activity 是显式 allowlist；raw `USAGE_REPORTED` 不在 allowlist。 | 只将 `CONTEXT_BUDGET_EVALUATED` 加入 public activity；继续拒绝 raw usage public projection。 |
| `dayu/host/api.py::HostActivityView` | 当前无 context-usage typed payload。 | 增加可选 `HostContextUsageView`；缺 policy/非 context activity 时为 `None`，不是下游 fallback。 |
| `dayu/service/entrypoint_runtime.py::_entrypoint_activity_from_host_event` | Service 映射 kind/status/severity/counts，但无 context usage。 | 新增同形 typed `EntrypointContextUsage`，逐字段复制与 closed-enum 映射；不接受 raw payload/ref。 |
| 对 `RUNNER_CALL_INPUT_ASSEMBLED` 的 production grep audit | 直接 producer/consumer全集为 `_runner_call_manifest.py`、`run_input.py`、`engine_ingest.py`、`compaction_operation.py`、`proactive_compaction.py`、`tool_trace.py`、`durable/tool_trace.py`、`lifecycle_events.py`、`durable/schema.py`；`read_api.py` 通过通用 EventLog stream观察顺序。 | manifest-before-start 的 schema、link、Tool Trace、public stream与proactive compactor kind filter必须进入 Slice 1 allowed scope/回归矩阵；不得假设只有 RunInput producer受影响。 |

Root cause 的逻辑/数据真源是：**完整 runner-call candidate、conservative
estimate、iteration link 与 usage observation 尚未形成一个可校验的 durable
lineage contract；同时 accepted compact 的 persisted coverage尚未进入Conversation
Memory typed projection，且pressure被错误地当成stage-independent action**。
display text、post-compact size不下降与accepted Run无dispatch都只是这些owner缺口的
下游表现。修复必须建立owner级contract，不能在RunInput、read API、Service、UI、
fixture或单入口用fallback shim补救。

## 3. Scope boundary、non-goals 与不过度设计说明

### 3.1 In scope

- complete ordinary/post-compact/dispatch-fallback candidate 的单一 typed assembly
  与 digest-verified projection。
- accepted compact `source_boundary_refs` 的strict typed read boundary，以及
  Conversation Memory对covered raw/post-compact delta的唯一projection rule。
- conservative estimator stable identity/version 与 complete candidate adapter。
- runner-call manifest v2 sizing snapshot、accepted iteration link 与 usage
  observation direct pairing。
- Host-only compatible anchor resolver、signed-delta predictor、closed fallback
  reasons。
- proactive、hard block、post-compact、reactive recovery 与 tier 4/5
  dispatch-fallback 的统一 sizing result。
- canonical `CONTEXT_BUDGET_EVALUATED` payload builder/parser、deterministic event
  identity、append ordering、replay/recovery。
- `HostContextUsageView`、`EntrypointContextUsage` 和 existing callback delivery。
- owner tests、integration tests、schema tests、import-boundary tests、coverage、
  pyright 与 README audit。

### 3.2 Explicit non-goals

- provider tokenizer、provider/model count adapter、remote count endpoint、tokenizer
  download/version management。
- provider live probe 或凭据依赖的 required validation。
- provider-name branch。
- global/cross-model correction factor、moving average、dynamic ratio、billing-grade
  accuracy。
- Engine 理解 context window、soft/hard policy、pressure 或 compact state。
- metadata、extra payload、request id、timestamp、display text、日志或偶然 event
  顺序推断 pairing。
- 在`run_input.py`下游过滤compact-covered recent items、consumer索引raw
  `source_boundary_refs`、按ref前缀/sequence/time猜coverage、或为同一snapshot启动
  第二次proactive operation。
- 改动 WU-OBS-00B / Issue #119 analyzer correlation owner；不新增
  `client_correlation_id` / `provider_request_id` correlation contract。
- 把 compactor proposal usage 或 provider overflow 当 calibration sample。
- UI 文案、百分比格式、颜色、进度条、历史曲线。
- 新 durable anchor table、learned model、background scheduler、remote state 或
  migration framework。

### 3.3 为什么不是过度设计

计划只增加一个 Host-private anchor resolver、一个共享 typed sizing result、一个
设计明确要求的 canonical fact/public DTO，并在既有compact typed payload与memory
projection owner上补齐coverage字段和过滤规则。现有 EventLog、payload descriptor、
manifest、accepted link、usage signal、activity callback、memory snapshot与context
policy全部复用；不增加 tokenizer、provider adapter、表、后台任务、第二套raw-history
index或UI。manifest schema cutover是冻结direct pairing contract的必要最小改动；
exact candidate assembly与memory boundary修正是避免多个输入/coverage真源的owner
修复，不是为未来扩展预建框架。

## 4. Semantic owner decisions

| 语义 | 唯一 owner | 产生/校验/持久化/投影边界 | 明确禁止 |
| --- | --- | --- | --- |
| complete candidate messages/tool schemas/source watermark/digest | `dayu.host.run_input` candidate assembly owner | pre-start 或 recovery dispatch 前构造 digest-verified projection；actual `AgentRunRequest` 只消费并复核 | dispatch/ingest/fallback 各自拼文本 |
| accepted compact source coverage roles | `dayu.host.compact_payload` typed source boundary | producer持久化`source_boundary_refs`；strict parser唯一拆分`current_input_ref`与`compacted_source_refs` | consumer索引raw list、按ref形态/顺序以外隐式规则或时间猜角色 |
| selected recent post-compact delta | `dayu.host.memory` Conversation Memory projection | accepted compact时按typed covered refs更新selected window；recent evidence、incremental/rebuild/repair/persisted snapshot同源 | RunInput下游临时filter、删除current input、跨boundary补满protected floor |
| conservative formula/constants | `dayu.host.context_budget` | exact candidate adapter调用既有 estimator | provider/tokenizer 专用估算 |
| estimator identity/version | `dayu.host.context_budget` module constants + typed `ContextEstimatorContract` | manifest/fact写入并严格比较 | 用具体 `estimator_digest` 冒充 version |
| runner request serialization compatibility | runner-call manifest owner | 从 serializer schema、sanitized typed Runner request semantics 计算 digest | provider name分支；包含 secret/header值 |
| actual usage legality | Engine Runner/parser | 只对实际出现且合法的 usage emit normalized observation | Host按 capability猜 usage |
| manifest↔iteration↔usage pairing | Host Engine ingest + manifest parser | accepted link唯一定位 complete manifest；usage signal durable保存 pairing refs/status | request id、时间戳、display text |
| compatible anchor选择与 lineage barrier | 新 `dayu.host.context_anchor` | 仅通过调用方显式传入的同一个 `HostTransaction` + `EventLogStore`，从该 consistent snapshot中的 committed manifests、links、usage、durable accepted iteration-completed preview与accepted compact boundary重建 | 自开transaction、跨transaction分页、模块可变状态/singleton/cache、Service/UI durable访问、projection copy、summary、日志、旧测试fixture |
| predicted tokens/threshold/pressure/stage-aware action | `dayu.host.context_budget` 的 `ContextSizingResult` | anchored或fallback只产生一个typed result；pressure纯阈值派生，budget decision由stage+pressure派生 | context events/read API/Service/UI重算；把post-compact soft改写成normal |
| context-budget durable truth | `dayu.host.context_events` + dispatch/ingest transaction owner | deterministic canonical fact append | 把 fact 作为 usage event副作用 |
| public context usage | `HostContextUsageView` | Host从 canonical fact严格投影 | 暴露 anchor refs/raw usage/policy internal refs |
| Service activity DTO | `dayu.service.entrypoint_runtime` | typed closed mapping逐字段透传 | basis points/percentage/pressure重算 |
| concrete display formatting | UI/CLI（后续 work） | 本 WU 不实现 | Host/Service生成“62%”展示文案 |

## 5. Target contracts、schemas 与 algorithms

### 5.1 Estimator 与 complete candidate contract

在 `dayu/host/context_budget.py` 冻结：

```python
CONTEXT_ESTIMATOR_ID = "dayu.host.conservative_context_budget"
CONTEXT_ESTIMATOR_VERSION = "1"
MAX_CONTEXT_TOKEN_COUNT = 2**63 - 1

@dataclass(frozen=True, slots=True)
class ContextEstimatorContract:
    estimator_id: str
    estimator_version: str
```

版本 `1` 是本次首次冻结的 contract version；它不为历史 unversioned digest
提供兼容别名。`estimate_context_budget(...)` 的 chars/CJK/JSON/message/tool-schema
公式和既有常量不变。

`dayu/host/run_input.py` 增加唯一exact type：

```python
@dataclass(frozen=True, slots=True)
class PreparedRunnerCallCandidate:
    session_id: str
    run_id: str
    candidate_input_cursor: int
    candidate_input_projection_ref: str
    candidate_input_projection_digest: str
    input_snapshot_digest: str
    messages: tuple[AgentMessage, ...]
    tool_schemas: tuple[ToolSchema, ...]
    disable_tools: bool
    policy_snapshot: PolicySnapshot
    source_cursor_refs: tuple[str, ...]
    memory_snapshot_cursor_ref: str | None
    compact_artifact_refs: tuple[str, ...]
    context_fallback_decision_ref: str | None
    request_semantics_digest: str
```

`candidate_input_cursor`是本次组装读取的最大committed source watermark；
`input_snapshot_digest`覆盖messages projection、selected tool schema snapshot、
engine policy snapshot与request-semantics digest。Context budget policy由sizing
caller显式传入，不属于logical input candidate。refs只供manifest/fact与internal
recovery，public view不暴露。

candidate preparation 必须复用 RunInputBuilder 当前 normalization、memory、
protected raw tail、continuity、current user tail、scene 与 tool selection 规则。
Attempt runtime-only 的 cancellation token、tool executor handle 与 worker handle
不进入 candidate digest。

现有 memory projection catch-up / lag repair 必须移动到 candidate freeze 之前完成；
不得先冻结旧 memory candidate，再在 `RUN_STARTED` 后修复并组装另一份 request。
tool-enabled path同样先从 admission冻结的 effective bundle 产生 selected tool-schema
snapshot，Attempt-scoped `ToolRuntime` / executor handle仍在start后按同一snapshot创建，
不能为了pre-start sizing提前执行或授权工具。

`AgentRunRequest` 构造阶段必须读取该 frozen candidate，复核：

- Run/session/policy identity；
- candidate projection descriptor digest；
- normalized messages/tool schemas的重新 digest；
- current Attempt 仍允许 dispatch。

任一 mismatch 是 input integrity failure，fail closed；禁止静默重新 assemble
另一份 request。

`PreparedRunnerCallCandidate` 不包含、预留或分配 Attempt/execution/dispatch
identity，也不依赖 `RUNNER_CALL_INPUT_ASSEMBLED`。它只拥有完整 logical input、
policy/request semantics和source watermark，足以计算 `E_current` 与 sizing
decision。Attempt-scoped identity 是 allow decision 之后的 start owner输入，不是
sizing输入，从而消除 candidate -> manifest -> identity -> decision 的循环依赖。

complete candidate 到 `BudgetEstimateInput` 的 adapter 固定：

- 每条实际 message 的业务文本作为一个 `BudgetTextFragment`，每条仍使用既有
  message overhead；
- assistant tool calls、tool message identity、reasoning/provider-neutral structured
  atoms只以 canonical JSON fragment计入，不能重复计算已进入 text fragment 的
  content；
- selected tool schema逐项作为既有 `tool_schema_fragments`；
- digest必须包含 `input_snapshot_digest`，不能只依赖 fragment label。

因此 fallback 是“对当前完整 candidate 使用既有 estimator”，不是继续使用
`USER_INPUT_ACCEPTED.display_text` 或 compact material subset。

这里保持不变的是 estimator 的 chars/CJK/canonical JSON/message overhead/tool
schema overhead **公式与常量**，以及“无 compatible usage 时使用 conservative
fallback”的治理语义；不承诺新 token 数与旧
`material_view.budget_fragments` subset逐值相等。complete candidate新增覆盖system /
scene messages、完整normalized messages、只计一次的structured atoms、memory /
compact / fallback material与selected tool schemas，故同一严格subset fixture的新估算
必须不小于旧subset估算，并允许因此跨过soft/hard threshold；这属于修复不低估，不是
anchor算法回归。

### 5.2 Request serialization semantics

`request_semantics_digest` 由 Host 从 typed inputs确定性计算，canonical object字段
固定为：

- `RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION`
- runner-call input projection schema version
- `RunnerCallOptions`
- `RunnerSpec.provider_request` 的 canonical typed projection
- `supports_tool_calling`、`supports_streaming`、`supports_stream_usage`
- `client_correlation_policy`

provider/model分别作为显式 compatibility字段。digest不得包含 endpoint、
API key ref/value、header value、timeout、retry/backoff或 provider response。
`supports_stream_usage` 出现在 request semantics snapshot只表示 request shape
可能变化；**它不参与 usage presence判断**。

### 5.3 Runner-call manifest schema v2

`RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` 直接改为
`runner_call_input_manifest.v2`。所有 producer（ordinary、Engine continuation、
compactor proposal）一次性写新 schema；parser只接受 v2。

manifest新增必填对象 `sizing_snapshot`，shape固定：

| field | type | required | semantics |
| --- | --- | ---: | --- |
| `status` | enum `complete/unavailable/not_applicable` | yes | estimator snapshot是否可用于ordinary anchor |
| `reason` | closed string or `null` | yes | 非complete原因；complete必须null |
| `estimator_id` | `str|null` | yes | complete时等于 frozen id |
| `estimator_version` | `str|null` | yes | complete时等于 frozen version |
| `estimator_digest` | sha256 digest or `null` | yes | complete candidate specific estimate digest |
| `conservative_input_tokens` | `int|null` | yes | `E_anchor` candidate；complete时 `0..MAX` |
| `context_window_size` | `int|null` | yes | complete时正整数 |
| `provider` | `str|null` | yes | complete ordinary provider identity |
| `model` | `str|null` | yes | complete ordinary model identity |
| `request_semantics_digest` | sha256 digest or `null` | yes | complete request serialization contract |
| `input_snapshot_digest` | sha256 digest or `null` | yes | complete messages+tools snapshot |
| `policy_ref` | `str|null` | yes | frozen Host policy ref |
| `policy_snapshot_digest` | sha256 digest or `null` | yes | frozen context policy/window/ratio snapshot identity |

validation invariant：

- `status=complete` 时所有 nullable value字段必须非空且通过范围/digest校验；
- `status=not_applicable` 仅允许 `compactor_proposal`，value字段全部为null；
- `status=unavailable` 必须有 closed reason，value字段不得被 anchor resolver
  部分信任；closed reasons固定包含`context_policy_unavailable`及四个
  `continuation_*_unavailable`；
- complete ordinary manifest、hot payload、projection descriptor、tool schema
  descriptor与 sizing snapshot必须通过同一 manifest digest保护；
- old v1、缺字段、unknown字段、部分字段、错误 enum全部拒绝；不得 loose parse、
  `getattr/hasattr`、默认值或 compatibility branch。

ordinary pre-start 的线性时序固定为：

```text
BEGIN IMMEDIATE
  read startable Run + freeze complete identity-free candidate
  -> if context policy missing:
       construct one StartGovernedRunInput (allow_without_budget)
       -> append RUNNER_CALL_INPUT_ASSEMBLED(
            sizing_snapshot.status=unavailable,
            reason=context_policy_unavailable
          )
       -> call existing start transition with same_start_input
       -> commit
       (no sizing result/fact/activity)
  -> estimate E_current + resolve anchor + build ContextSizingResult
  -> if ordinary soft/hard:
       append CONTEXT_BUDGET_EVALUATED
       -> append compaction/fail-close transition
       -> commit
       (no runner-call manifest, no Attempt/execution/dispatch identity allocation)
  -> if allow:
       construct one StartGovernedRunInput (allocate identities now)
       -> finalize candidate projection/complete manifest with that input's
          attempt_id/execution_id
       -> append RUNNER_CALL_INPUT_ASSEMBLED
       -> append CONTEXT_BUDGET_EVALUATED
       -> call existing
          start_governed_run_with_starting_attempt_in_transaction(
              transaction, event_log_store, same_start_input
          )
       -> transition appends RUN_STARTED -> ATTEMPT_STARTED and inserts dispatch row
       -> commit
```

Slice 1 尚未引入 budget fact时，上述 allow sequence暂为
`manifest -> RUN_STARTED -> ATTEMPT_STARTED`，ordinary soft/hard仍不写manifest；Slice 2只在
同一transaction插入fact，不改变identity与start interface。actual
`AgentRunRequest`随后消费已start Attempt snapshot时，必须读取这个pre-start frozen
candidate/manifest并复核同一 attempt/execution/digest，不能重组第二份输入。

`dayu/host/durable/run_transition.py` **不修改**：其现有
`StartGovernedRunInput` 已是exact typed interface，字段
`run_id/expected_status/run_started_event_id/attempt_started_event_id/attempt_id/
execution_id/dispatch_record_id/occurred_at/actor/source/start_reason/worker_kind/
owner_host_instance_id` 全部由 caller提供，transition已原样消费并创建对应rows。
Slice 1在 `dispatch.py` 新增私有
`_new_governed_start_input(run: RunRow, occurred_at: datetime) ->
StartGovernedRunInput`，并定义closed tagged union：

```python
@dataclass(frozen=True, slots=True)
class BudgetedDispatchStart:
    start_input: StartGovernedRunInput
    sizing: ContextSizingResult

@dataclass(frozen=True, slots=True)
class NoBudgetDispatchStart:
    start_input: StartGovernedRunInput

DispatchStartPlan: TypeAlias = BudgetedDispatchStart | NoBudgetDispatchStart

def _commit_dispatch_candidate_in_transaction(
    transaction: HostTransaction,
    run: RunRow,
    candidate: PreparedRunnerCallCandidate,
    plan: DispatchStartPlan,
) -> PendingDispatchRecord:
    ...
```

该helper是manifest/start顺序的唯一owner；`BudgetedDispatchStart`写complete sizing
snapshot，Slice 1已生成method固定为conservative的真实result但尚不持久化fact；
Slice 2只为该variant加入fact append。`NoBudgetDispatchStart`只写
`context_policy_unavailable` manifest再start，永不写fact/activity。不得使用
`ContextSizingResult | None`、extra payload或兼容分支表达两种语义。

Engine continuation的唯一 frozen source固定为：

- current messages projection：只来自当前 accepted
  `IterationStartedData.input_projection`，Host在同一ingest transaction写入并校验的
  projection descriptor；不得从tool events、memory或当前RunInput重组；
- selected tool schema：只来自同一 attempt/execution 首个complete pre-start
  manifest引用的selected-tool-schema descriptor/ref/digest；continuation不得重新
  调用当前 tool selection；
- context policy：只来自该pre-start manifest strict `sizing_snapshot`中的
  `policy_ref/policy_snapshot_digest/context_window_size`；不得读取当前local context
  policy覆盖它；
- request semantics：只来自该pre-start manifest strict
  `request_semantics_digest/provider/model/estimator_id/estimator_version`；
  continuation只复制并验证这些frozen compatibility atoms，不从当前effective config
  重算；
- continuation identity/lineage：当前 accepted iteration link加上述三个
  digest-verified来源。

projection、selected schema、context policy与request semantics四项全部可直接重建时，
continuation v2 manifest才可
`sizing_snapshot.status=complete`；任一ref缺失、digest不匹配、projection为空/不完整
或crash使来源不可读时，必须写 `status=unavailable`，reason按唯一失败边界从
`continuation_projection_unavailable`、`continuation_tool_schema_unavailable`、
`continuation_policy_unavailable`、`continuation_request_semantics_unavailable`
四个closed enum中选择；多项同时失败时按上述顺序取第一个。anchor resolver对当前
candidate执行完整conservative fallback。不得从当前effective config重选或把limited
signal升级成complete。

### 5.4 Usage pairing 与 anchor resolver

新增 `dayu/host/context_anchor.py`，只承载 Host-private durable anchor读取与
compatibility判定；不进入 Host public API。

typed transaction interface固定为：

```python
@dataclass(frozen=True, slots=True)
class ContextAnchorQuery:
    session_id: str
    current_run_id: str
    candidate_input_cursor: int
    candidate_input_digest: str
    provider: str
    model: str
    context_window_size: int
    estimator_contract: ContextEstimatorContract
    request_semantics_digest: str

@dataclass(frozen=True, slots=True)
class CompatibleContextAnchor:
    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    iteration_link_event_id: str
    usage_event_id: str
    usage_observation_digest: str
    iteration_completed_event_id: str
    usage_anchor_tokens: int
    conservative_anchor_tokens: int

@dataclass(frozen=True, slots=True)
class ContextAnchorResolution:
    anchor: CompatibleContextAnchor | None
    fallback_reason: ContextSizingFallbackReason | None

def resolve_context_anchor(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    query: ContextAnchorQuery,
) -> ContextAnchorResolution:
    ...
```

`ContextAnchorResolution`要求两个字段恰有一个非空；resolver只选择/验证anchor，不计算
`E_current`、signed delta、threshold或pressure。`context_budget.py`使用该typed
resolution与当前estimate构造唯一`ContextSizingResult`，避免durable reader反向拥有
预算公式。

调用方在冻结current candidate并计算 `E_current` 的同一个 `BEGIN IMMEDIATE`
transaction内调用resolver；resolver用传入的同一 `HostTransaction` 完成全部keyset
pages、latest accepted compact boundary与manifest/link/usage/completion读取，不得
内部调用 `run_read/run_write`，不得跨transaction分页。`EventLogStore` 是显式传入的
stateless primitive；模块不得持有mutable singleton、cache、connection或隐式store。
Service/UI不得import该模块或接收transaction/store。

Host ingest处理实际 `USAGE_REPORTED` 时：

1. 按 exact `session_id/run_id/attempt_id/execution_id/iteration_id` 查找唯一
   `RUNNER_CALL_INPUT_ITERATION_LINKED`。
2. link必须 `validation_status=complete`，并通过 manifest event id/ref/digest读取
   v2 manifest。
3. manifest必须是 eligible ordinary kind、`sizing_snapshot.status=complete`、
   非 compactor identity。
4. usage observation字段必须为Engine normalized合法值。
5. pairing结果以 strict nested object写入同一 durable `USAGE_REPORTED`
   projection signal：记录 pairing status/reason、manifest event/ref/digest、
   accepted link event id、input snapshot digest与 observation digest。
6. `provider_request_id`可继续作为内部诊断字段，但不进入任何 pairing predicate。

删除 `_estimate_usage_observation_input(...)` 与 display-text estimator路径。既有
usage diagnostic若保留，只能使用 manifest中同iteration的 `E_anchor`，且不能成为
预算decision或 public activity。

successful ordinary runner-call anchor eligibility是以下现有 durable evidence的
**全 conjunction**，缺一不可：

1. exact identity上的 `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact为strict v2
   complete manifest，kind只能是
   `initial_user_dispatch|followup_user_dispatch|post_compaction_dispatch|
   tool_result_continuation`，不得是compactor proposal；
2. 同一 `attempt_id/execution_id/iteration_id` 恰有一个accepted
   `RUNNER_CALL_INPUT_ITERATION_LINKED`，其manifest event/ref/digest与#1一致；
3. 同一identity/iteration恰有一个strict-valid、pairing status complete的
   `USAGE_REPORTED`，且 `prompt_tokens` 合法；
4. 同一identity/iteration恰有一个Host已durable接受的
   `ITERATION_COMPLETED` preview，event sequence晚于link与usage，finish reason只能
   为 `stop|length|tool_calls`。

第4项复用已有 accepted Engine event durable evidence；不把preview升级为canonical
business fact，不新增completion event/table/state machine。`RUN_SUCCEEDED`、
`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` 或 Attempt terminal都不能单独替代#4，也
不能把usage先到但runner随后失败的调用“补成成功”。

resolver按 session event sequence倒序、固定页大小 keyset扫描，遇到 latest accepted
`CONTEXT_COMPACTED` boundary即停止；不得设置会让长会话误判的任意总条数 cap。扫描规则：

- 最近期满足上述四项、兼容且lineage complete的ordinary call成为anchor；
- tool loop逐iteration判断：`finish_reason=tool_calls` 的已完成iteration可anchor；
  后续continuation必须有自己的complete manifest/link/completion。中间call完全没有
  usage时，只有其manifest/link/completion/input lineage都complete才可继续向旧
  compatible anchor查找；
- 中间出现非法/重复/冲突 usage、ambiguous pairing、manifest/link mismatch或
  incomplete lineage时形成 barrier，当前整体fallback，不越过barrier寻找更旧anchor；
- usage已写但尚无`ITERATION_COMPLETED`时为in-flight/crash gap barrier；Run随后
  failed/cancelled/lost仍是barrier，不从terminal status重建completion。Run已
  succeeded也只有存在exact completion row的最后runner call可用；
- 已有direct completion的较早call不会仅因所属Run后来在工具执行或更晚iteration失败
  而改写为“未完成”；但从它到current candidate之间任一更晚incomplete/failed runner
  call仍形成barrier；
- compactor proposal、reactive overflow和未形成当前candidate的历史usage跳过或拒绝，
  但绝不产出public activity。

compatible必须全部相等：

- provider；
- model；
- context window；
- estimator id/version；
- request semantics digest；
- eligible ordinary call semantics；
- accepted compact baseline；
- digest-verified complete input lineage。

### 5.5 Sizing result、formula 与 fallback reasons

`dayu/host/context_budget.py` 增加：

```python
class ContextEstimateMethod(StrEnum):
    USAGE_ANCHORED = "usage_anchored"
    CONSERVATIVE_FALLBACK = "conservative_fallback"

class ContextPressureLevel(StrEnum):
    NORMAL = "normal"
    SOFT_THRESHOLD_EXCEEDED = "soft_threshold_exceeded"
    HARD_THRESHOLD_EXCEEDED = "hard_threshold_exceeded"

class ContextSizingStage(StrEnum):
    ORDINARY = "ordinary"
    POST_COMPACT = "post_compact"
    DISPATCH_FALLBACK = "dispatch_fallback"
```

另定义 internal closed `ContextSizingFallbackReason`，成员固定为：

- `usage_missing`
- `usage_invalid`
- `usage_ambiguous`
- `iteration_incomplete`
- `iteration_completion_ambiguous`
- `iteration_finish_reason_ineligible`
- `iteration_link_missing`
- `iteration_link_invalid`
- `manifest_incomplete`
- `manifest_mismatch`
- `continuation_projection_unavailable`
- `continuation_tool_schema_unavailable`
- `continuation_policy_unavailable`
- `continuation_request_semantics_unavailable`
- `runner_call_kind_ineligible`
- `provider_mismatch`
- `model_mismatch`
- `context_window_mismatch`
- `estimator_contract_mismatch`
- `request_semantics_mismatch`
- `accepted_compact_invalidated`
- `lineage_gap`
- `anchor_value_invalid`
- `prediction_non_positive`
- `arithmetic_range_invalid`

`ContextSizingResult`是单一 sizing truth，exact type固定为：

```python
@dataclass(frozen=True, slots=True)
class ContextAnchorDiagnostic:
    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    iteration_link_event_id: str
    usage_event_id: str
    usage_observation_digest: str
    iteration_completed_event_id: str
    usage_anchor_tokens: int
    conservative_anchor_tokens: int
    conservative_current_tokens: int
    signed_delta_tokens: int
    predicted_input_tokens: int

@dataclass(frozen=True, slots=True)
class ContextSizingResult:
    stage: ContextSizingStage
    candidate_input_cursor: int
    candidate_input_projection_ref: str
    candidate_input_digest: str
    estimator_contract: ContextEstimatorContract
    estimator_digest: str
    conservative_input_tokens: int
    estimate_method: ContextEstimateMethod
    predicted_input_tokens: int
    context_window_size: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    utilization_basis_points: int
    pressure_level: ContextPressureLevel
    budget_decision: ContextBudgetDecision
    policy_ref: str
    policy_snapshot_digest: str
    anchor_diagnostic: ContextAnchorDiagnostic | None
    fallback_reason: ContextSizingFallbackReason | None
```

anchored diagnostic只写Host internal canonical diagnostic，不进入public view；
anchored method要求diagnostic非空且fallback reason为空，fallback method要求diagnostic
为空且fallback reason非空。

算法：

```text
signed_delta = E_current - E_anchor
P_current = U_anchor + signed_delta
```

`U_anchor/E_anchor/E_current`必须为 strict int（bool拒绝）且在
`0..MAX_CONTEXT_TOKEN_COUNT`；signed delta必须在有符号范围内；
`P_current`必须在 `1..MAX_CONTEXT_TOKEN_COUNT`。任一 anchor字段或运算结果非法，
method变为 `conservative_fallback`，predicted tokens严格取 `E_current`。

当前 complete candidate本身无法组装、digest验证失败或 conservative estimator
失败不是“usage缺失”；这是 Host input integrity/governance failure，按既有
fail-closed边界收口。只有历史 usage/anchor不可用必须无失败地fallback。

pressure与action contract固定为：

```text
pressure(predicted):
  predicted >= hard -> hard_threshold_exceeded
  predicted >= soft -> soft_threshold_exceeded
  else              -> normal

action(stage, pressure):
  ORDINARY:
    normal -> ALLOW_DISPATCH
    soft   -> COMPACT_SOFT_THRESHOLD
    hard   -> BLOCK_HARD_THRESHOLD
  POST_COMPACT | DISPATCH_FALLBACK:
    normal -> ALLOW_DISPATCH
    soft   -> ALLOW_DISPATCH
    hard   -> BLOCK_HARD_THRESHOLD
```

因此`ContextSizingResult.__post_init__`必须先仅由predicted/thresholds复核
`pressure_level`，再由`stage + pressure_level`复核`budget_decision`。
`POST_COMPACT` / `DISPATCH_FALLBACK` soft的pressure不得降为normal；public fact/view
继续报告soft pressure，但Host允许dispatch。ratio与threshold仍由
`ContextBudgetPolicy`派生，不因usage或stage变化。

### 5.6 `CONTEXT_BUDGET_EVALUATED` canonical schema

在 `dayu/host/context_events.py` 定义 constant、strict builder/parser与typed payload。
payload schema version固定为 `context_budget_evaluated.v1`，required fields：

| field | type | public? | semantics |
| --- | --- | ---: | --- |
| `schema_version` | fixed string | no | payload schema |
| `decision_id` | sha256-derived stable id | no | 与event id同源 |
| `run_id` | non-empty string | no | owning Host Run |
| `candidate_input_cursor` | non-negative int | no | source watermark |
| `candidate_input_projection_ref` | internal ref | no | exact candidate descriptor |
| `candidate_input_digest` | sha256 digest | no | complete candidate identity |
| `sizing_stage` | closed enum | no | ordinary/post-compact/dispatch-fallback |
| `policy_ref` | non-empty string | no | policy identity |
| `policy_snapshot_digest` | sha256 digest | no | frozen ratio/window snapshot |
| `estimator_id` | non-empty string | no | estimator identity |
| `estimator_version` | non-empty string | no | estimator version |
| `estimator_digest` | sha256 digest | no | current complete estimate |
| `conservative_input_tokens` | non-negative int | no | `E_current` |
| `estimate_method` | closed enum | yes | anchored/fallback |
| `predicted_input_tokens` | non-negative int | yes | actual decision basis |
| `context_window_size` | positive int | yes | same policy snapshot |
| `utilization_basis_points` | non-negative int | yes | unclamped |
| `soft_threshold_tokens` | positive int | yes | ratio-derived |
| `hard_threshold_tokens` | positive int | yes | ratio-derived |
| `pressure_level` | closed enum | yes | actual decision pressure |
| `budget_decision` | closed enum | no | exact governance action |
| `fallback_reason` | closed enum or null | no | anchored时null |
| `anchor_diagnostic` | strict object or null | no | Host-only refs/values |

public列表示可以投影进 `HostContextUsageView`，不是直接把payload交给UI。

stable identity输入固定为：

```text
run_id
+ candidate_input_cursor
+ candidate_input_digest
+ sizing_stage
+ policy_snapshot_digest
+ estimator_id
+ estimator_version
```

event id固定从该canonical identity digest派生。append helper先按deterministic
event id读取：

- 已存在且payload/identity/result一致：返回既有row，不追加；
- 已存在但任一结果矛盾：identity conflict，fail closed；
- 不存在：append一次。

不使用当前时间、random UUID、request id或watch次数构造identity。首次append的
`occurred_at`不参与重算identity；replay直接复用既有row。

event ordering / atomicity：

```text
ordinary allow:
  RUNNER_CALL_INPUT_ASSEMBLED
  -> CONTEXT_BUDGET_EVALUATED
  -> RUN_STARTED
  -> ATTEMPT_STARTED

ordinary soft/hard:
  CONTEXT_BUDGET_EVALUATED
  -> CONTEXT_COMPACTION_REQUESTED or fail-closed facts

post-compact allow:
  new candidate/manifest
  -> CONTEXT_BUDGET_EVALUATED(stage=post_compact)
  -> RUN_STARTED / ATTEMPT_STARTED (or recovery ATTEMPT_STARTED)

dispatch fallback:
  new fallback candidate/manifest
  -> CONTEXT_BUDGET_EVALUATED(stage=dispatch_fallback)
  -> RUN_STARTED / ATTEMPT_STARTED
```

fact append与它驱动的下一canonical transition必须在同一Host transaction。
fact append失败时不得compact/dispatch；usage缺失在同一consistent snapshot内、fact
append前收敛为合法conservative result，因此不触发失败。

CAS/precondition/rollback方案只允许以下一个：

1. `_operation(transaction)`先读取startable Run、冻结candidate、计算sizing；
2. allow后构造唯一 `StartGovernedRunInput`，写candidate projection、manifest、fact，
   再调用existing durable transition；
3. transition正常返回 `UPDATED` 时，验证returned Run/Attempt/dispatch record的
   `attempt_id/execution_id/dispatch_record_id`与同一start input完全相等，正常返回
   `PendingDispatchRecord`，`run_write` commit；
4. transition在前置read检查返回 `NOT_FOUND|INVALID_STATE` 或 `UPDATED` 却缺完整rows时，
   `_commit_dispatch_candidate_in_transaction`抛出仅定义在 `dispatch.py` 的私有
   `_StartCandidateCasMissRollback(Exception)`；`HostTransactionRunner.run_write`
   按现有“异常即rollback”语义回滚projection payload row、manifest、fact、start
   facts与state rows；
5. `_run_pre_start_governance` 只在 `run_write` 调用外捕获该私有异常，记录debug并
   返回 `_GovernanceStageResult(pending_dispatch=None, compact_accepted=None)`；
   其它异常不吞掉，继续按既有failure boundary传播。前置检查通过后底层Run row CAS
   返回`CAS_LOST`时，现有 `_require_run_mutation_updated` 已抛
   `HostDurableError`；它同样使整笔transaction rollback，并继续向调用方传播为durable
   concurrency/integrity failure，不转换为普通“无dispatch”。

不得修改 `HostTransactionRunner`、不得让transition抛业务无关异常、不得以特殊正常
返回值请求rollback。测试分别注入precondition `INVALID_STATE`与低层`CAS_LOST`：
两者都必须在新transaction断言 candidate projection payload、
`RUNNER_CALL_INPUT_ASSEMBLED`、`CONTEXT_BUDGET_EVALUATED`、`RUN_STARTED`、
`ATTEMPT_STARTED`与dispatch/Attempt rows均为零；前者caller正常得到“本轮无dispatch”，
后者caller收到既有`HostDurableError`。相反，已存在同identity且一致的fact只表示幂等
复用，仍须在同transaction重新验证当前Run state后才能继续transition。

policy缺失时没有合法 sizing result，不产生伪造 fact；existing Run行为保持
“budget governance unavailable”。public activity中的 `context_usage` 为 `None`。

### 5.7 Host 与 Service public projection

在 `dayu/host/api.py` 定义并从 `dayu.host` 导出：

```python
@dataclass(frozen=True, slots=True)
class HostContextUsageView:
    predicted_input_tokens: int
    context_window_size: int
    utilization_basis_points: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    estimate_method: ContextEstimateMethod
    pressure_level: ContextPressureLevel
```

- `HostActivityKind` 新增 `CONTEXT_USAGE = "context_usage"`。
- `HostActivityView` 新增
  `context_usage: HostContextUsageView | None = None`。
- invariant：kind为`CONTEXT_USAGE`时`context_usage`必须非空，tool/count字段为空；
  其它kind的`context_usage`必须为`None`。
- `read_api`只对strict-valid canonical `CONTEXT_BUDGET_EVALUATED`产生：
  - kind=`CONTEXT_USAGE`
  - status=`INFO`
  - severity=`INFO`
  - title=`上下文预算已评估`
  - summary=`None`
  - typed context usage来自payload public subset
- Host不格式化“62%”，不根据pressure选择颜色/文案。
- malformed canonical payload fail closed为Host durable/public projection错误；
  禁止返回部分view或从其它事件重算。

在 `dayu/service/entrypoint_runtime.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class EntrypointContextUsage:
    predicted_input_tokens: int
    context_window_size: int
    utilization_basis_points: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    estimate_method: EntrypointContextEstimateMethod
    pressure_level: EntrypointContextPressureLevel
```

`EntrypointActivityKind`新增`CONTEXT_USAGE`；
`EntrypointActivity`新增
`context_usage: EntrypointContextUsage | None = None`并保持同样kind invariant。
Service使用exhaustive enum mapper和逐字段复制；不执行除类型构造外的算术。

CLI现有formatter继续只消费通用title/summary；本WU不增加具体context display。
测试必须证明新增optional typed字段不破坏既有formatter，而不是添加空分支或百分比
重算。

### 5.8 Compact source boundary 与 Conversation Memory projection contract

`dayu/host/compact_payload.py::source_boundary_refs(request)`的persisted producer
contract保持：

```text
source_boundary_refs =
  unique_in_order(
    request.current_input_ref,
    *request.material_source_refs,
    *request.canonical_evidence_refs,
    *request.evidence_backed_fact_refs,
  )
```

第一个ref只拥有current-input boundary角色，不表示被compact覆盖；去重后其余refs才是
accepted compact覆盖的canonical source refs。没有任何covered material时，
persisted list合法地只含current input。

`ContextCompactedSemanticPayload`的exact typed read contract扩充为：

```python
@dataclass(frozen=True, slots=True)
class ContextCompactedSemanticPayload:
    accepted_candidate: ConversationCompactOutputVNext
    accepted_candidate_digest: str
    accepted_evidence_mapping_refs: tuple[str, ...]
    compact_artifact_ref: str
    current_input_ref: str
    compacted_source_refs: tuple[str, ...]
```

`parse_context_compacted_semantic_payload(...)`是raw
`source_boundary_refs`的唯一reader：要求字段为list、至少一项、每项为非空`str`且全局
唯一；owner parser读取第一项为`current_input_ref`、其余为
`compacted_source_refs`。重复current ref、空ref、wrong type、空list或缺字段全部
fail closed；不新增旧payload compatibility reader。所有consumer只读取typed fields，
不得再次索引payload list。

`dayu/host/memory.py::project_conversation_memory_event`处理accepted compact时按以下
唯一顺序更新recent view：

1. 对每个既有`SelectedRecentWindowItem`构造其canonical source set：
   `item.event_id + item.source_refs`。
2. canonical source set命中`current_input_ref`时保留该item；current input在projection
   与后续RunInput raw-tail dedupe后只能渲染一次。
3. 否则，canonical source set与`compacted_source_refs`相交时删除该item。
4. 与covered refs不相交的item保留；这包括未被本次selected compact material覆盖的
   protected recent raw。
5. 对更新后的selected window执行既有bounded policy，再从它同源重建
   `recent_evidence_items`。
6. compact event之后到达的eligible user/assistant/evidence canonical facts按既有
   projection自然追加，成为新的post-compact delta。

full rebuild和incremental projection都必须调用同一个event projection函数；durable
memory catch-up、inline delta repair与snapshot reload不得复制coverage规则。
`run_input.py`不新增compact-aware filter，只继续消费snapshot并使用既有
`selected_recent_source_refs` / `selected_recent_content_digests`与ordinary protected
raw tail做source-ref/content-digest去重。

该contract允许真实收缩但禁止伪造收缩：当`compacted_source_refs`确实覆盖older raw
时，post-compact exact candidate的conservative size应下降；当tuple为空或未命中任何
selected item时，memory recent view不能因为accepted compact本身而删除current input或
protected raw，size也不得被测试夹具强行断言下降。

## 6. State、data flow、replay 与 recovery

### 6.1 Normal anchored flow

```text
prior complete ordinary candidate
  -> RUNNER_CALL_INPUT_ASSEMBLED(v2, E_anchor + identities)
  -> accepted RUNNER_CALL_INPUT_ITERATION_LINKED
  -> Engine emits legal USAGE_REPORTED(U_anchor)
  -> Host durable pairing refs
  -> accepted ITERATION_COMPLETED preview for exact identity/iteration
     with finish_reason stop|length|tool_calls

next complete candidate
  -> same BEGIN IMMEDIATE transaction:
     identity-free candidate assembly + estimator => E_current
  -> anchor resolver reads all pages in that same transaction snapshot
     and proves eligibility/compatibility/lineage
  -> ContextSizingResult(P_current, thresholds, pressure, decision)
  -> ordinary soft/hard: fact -> compact/block, with no manifest/Attempt identity
  -> allow: allocate start identity -> manifest -> fact -> start/attempt/dispatch
  -> HostContextUsageView
  -> EntrypointContextUsage
```

### 6.2 Missing usage flow

```text
no actual legal USAGE_REPORTED
  -> no synthetic observation
  -> resolver returns closed fallback reason
  -> ContextSizingResult.method=conservative_fallback
  -> predicted_input_tokens=E_current
  -> Run continues through the same fact/decision path
```

`supports_stream_usage=True`但provider不返回usage仍走该流程；
`supports_stream_usage=False`但provider实际返回合法usage仍允许pairing。

### 6.3 Replay/reconciliation

- all reads只信任committed EventLog、digest-verified payload descriptors、accepted
  iteration link、accepted iteration-completed preview与typed policy snapshot；
  resolver全部pages必须在调用方同一个Host transaction snapshot内。
- exact candidate projection与manifest mismatch时不得dispatch。
- same candidate重新治理时先查deterministic context-budget event id；一致则复用，
  不重新发activity truth。
- activity dedupe继续使用canonical event id。
- older anchor可跨无usage call，但每个中间iteration都必须有complete manifest/link；
  还必须有exact accepted iteration-completed evidence；lineage gap或crash gap立即
  fallback。
- accepted compact是hard anchor baseline barrier；immediate post-compact candidate
  只能conservative fallback。memory projection必须先按typed source boundary移除
  covered older raw，再freeze exact candidate；该call后出现新的合法paired usage，
  后续candidate才可anchor。
- reactive overflow只进入既有recovery state machine；它不写anchor correction。
- recovery不能从public view、Tool Trace、memory或usage diagnostic copy恢复anchor。
- terminal Run/Attempt状态不重建缺失的iteration completion；usage先到后failure、
  crash后无completion与terminal无completion均保持barrier。

### 6.4 Failure boundaries

| failure | required behavior |
| --- | --- |
| usage absent/nullable | conservative fallback；Run不失败 |
| usage field invalid/injected invalid | observation不可用；conservative fallback；Run不因usage失败 |
| multiple/conflicting usage or pairing | barrier + conservative fallback |
| manifest/link incomplete or mismatch | conservative fallback；不得猜pairing |
| compatibility mismatch | conservative fallback |
| anchor arithmetic invalid/non-positive | conservative fallback |
| current complete candidate cannot assemble/verify | Host input integrity fail closed；不是usage fallback |
| conservative estimator/current policy invalid | existing governance fail closed |
| fact identity conflict | fail closed，不执行矛盾decision |
| post-compact/fallback soft pressure | 保留soft pressure并允许dispatch；不得第二次proactive compact |
| post-compact hard pressure | 同transaction写显式Run failure transition；不得普通返回`None`留下accepted Run |
| dispatch-fallback hard pressure | 沿既有compaction-failed/fallback failure policy写显式Run failure；不得dispatch或静默停留 |
| public canonical payload corrupt | public projection fail closed，不下游重算 |
| Service enum出现未覆盖Host值 | assertion/error fail closed，不透传raw字符串 |

### 6.5 Post-compact / dispatch-fallback stage flow

同一Run/input snapshot的action flow固定为：

```text
ORDINARY exact candidate
  -> normal: dispatch
  -> soft: start or resume the one durable proactive operation
  -> hard: explicit fail closed

accepted compact
  -> compact payload typed boundary
  -> memory projection removes covered older raw
  -> rebuild POST_COMPACT exact candidate
  -> normal or soft: dispatch with original pressure preserved
  -> hard: explicit terminal Run failure

compact failed + tier 4/5 selected
  -> build DISPATCH_FALLBACK exact candidate
  -> normal or soft: dispatch with original pressure preserved
  -> hard: existing fallback/failure policy terminal Run failure
```

Slice 1尚未写`CONTEXT_BUDGET_EVALUATED`，但stage action与terminal behavior必须先完整
成立。实现应把post-compact/fallback helper的结果收敛为closed outcome：
`pending dispatch`或`terminal notice`；不得继续用`PendingDispatchRecord | None`让
hard与CAS/precondition miss共享模糊`None`。terminal outcome在当前write transaction内
复用`fail_unstarted_run_in_transaction`；transaction commit后由现有notifier交付。
`POST_COMPACT` hard不得为已经accepted的同一operation再追加一条矛盾
`CONTEXT_COMPACTION_FAILED`，但必须有Run terminal fact；`DISPATCH_FALLBACK` hard复用
此前已写/同事务将写的compact-failed diagnostic并追加Run terminal fact。Slice 2再在
这些transition之前插入同一个sizing result的canonical budget fact。

proactive projection中的existing operation identity仍是同一snapshot唯一operation
真源。post-compact/fallback soft直接dispatch，不回到ordinary soft branch；replay或
fresh attachment只能resume该operation或消费其terminal outcome，不能append第二条
`CONTEXT_COMPACTION_REQUESTED`。

## 7. Affected files/modules

以下是implementation允许触及的预计全集；实际某文件无需修改时不得机械修改。任何
新增production/test文件或越出该集合的改动都触发对应slice stop condition并回到
Controller裁决。

### 7.1 Host production

- `dayu/host/context_budget.py`
  - estimator identity/version、complete candidate adapter、sizing/result/enums、
    formula、range validation、basis points、pressure与stage-aware action唯一owner。
- `dayu/host/compact_payload.py`
  - persisted`source_boundary_refs` strict parser与
    `current_input_ref/compacted_source_refs` typed read owner。
- `dayu/host/memory.py`
  - accepted compact覆盖selected recent window、post-compact delta与recent evidence
    同源projection owner。
- `dayu/host/_runner_call_manifest.py`
  - manifest v2 sizing snapshot typed parser/graph validation。
- `dayu/host/run_input.py`
  - complete candidate preparation、projection/digest、actual request复用、
    manifest v2 producer。
- `dayu/host/dispatch.py`
  - pre-start/post-compact/fallback sizing与fact-before-transition ordering。
- `dayu/host/context_fallback.py`
  - fallback candidate走相同complete candidate + sizing contract。
- `dayu/host/compaction_operation.py`
  - post-compact candidate handoff；internal compactor proposal不产生public fact。
- `dayu/host/proactive_compaction.py`
  - direct manifest consumer；继续只按`runner_call_kind=compactor_proposal`
    读取proposal manifest，ordinary manifest前移不得污染operation projection。
- `dayu/host/engine_ingest.py`
  - direct manifest/link/usage pairing、删除display-text estimate、reactive
    post-compact/fallback fact ordering、anchored sizing consumption。
- `dayu/host/context_anchor.py`（新增）
  - durable anchor resolver与compatibility/lineage barriers。
- `dayu/host/context_events.py`
  - canonical fact schema/build/parse。
- `dayu/host/lifecycle_events.py`
  - context governance event type闭集。
- `dayu/host/durable/schema.py`
  - manifest v2 constant与全新数据库event-type DDL真源。
- `dayu/host/api.py`
  - public Host context usage DTO/kind/invariants。
- `dayu/host/read_api.py`
  - canonical fact→typed activity strict projection。
- `dayu/host/tool_trace.py`
  - direct canonical manifest consumer；若strict v2 typed parser需要字段适配，在shared
    parser结果上投影，不新增anchor/correlation语义。
- `dayu/host/durable/tool_trace.py`
  - Tool Trace runner-call reconstruction query消费strict parsed manifest；只做v2
    owner contract适配，不改变Issue #119 correlation owner。
- `dayu/host/__init__.py`
  - public Host type exports。

`dayu/host/durable/run_transition.py`明确**不修改**：existing
`StartGovernedRunInput`已满足caller-generated identity contract，Slice 1只补owner
tests。若implementation发现必须改变该typed input或transition写入语义，立即stop并
回Controller，不得把它悄悄加入allowed production。

### 7.2 Service/UI boundary

- `dayu/service/entrypoint_runtime.py`
  - `EntrypointContextUsage`、kind、activity字段与typed mapper。
- `dayu/cli/activity.py`不修改；只运行/补充测试证明旧formatter不回归。

### 7.3 Tests

- `tests/host/test_context_budget.py`
- `tests/host/test_context_anchor.py`（新增）
- `tests/host/test_context_budget_evaluated.py`（新增）
- `tests/host/test_run_input_builder.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_public_host_event.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_tool_trace_projection.py`（仅manifest/schema fixture同步）
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_outbox_projection.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_import_boundary.py`
- `tests/service/test_weak_typing_guard.py`
- `tests/cli/test_activity_renderer.py`

既有Engine tests只运行、不修改：

- `tests/engine/runners/openai/test_sse_usage_recorded.py`
- `tests/engine/runners/openai/test_sse_empty_choices_with_usage.py`
- `tests/engine/runners/openai/test_stream_usage_capability_gating.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/contracts/test_runner_events.py`

若Engine production行为确实不再满足“只emit合法actual usage”，需停止并重新裁决，
不得在本WU扩写Engine Host-budget语义。

### 7.4 Manifest/event/source-boundary consumer audit

`rg` 对 production/tests 的完整直接名称审计与通用ordering审计固定如下，Slice 1
implementation开始前再运行同一命令；出现新consumer必须先加入本表及对应allowed
scope，否则stop：

| consumer | 当前依赖 | owner/order影响与计划动作 |
| --- | --- | --- |
| `compact_payload.py` | accepted compact persisted semantic/source boundary parser | strict typed投影current input与covered refs；不参与manifest ordering。 |
| `memory.py` / `durable/memory.py` | compact event typed projection、incremental/rebuild/repair/snapshot persistence | 只在memory owner更新selected recent；durable adapter消费typed payload，不复制raw-list parsing。 |
| `_runner_call_manifest.py` | manifest/hot strict schema owner | 直接切v2；不依赖start顺序。 |
| `run_input.py` | ordinary producer、runner-call index、actual request复核、memory/raw-tail dedupe | producer前移到allow transaction；actual request不再二次写manifest；不新增compact coverage filter。 |
| `engine_ingest.py` | continuation producer、prepared manifest lookup/link、usage pairing | 同transaction commit后Run/Attempt/manifest同时可见；按exact identity找pre-start manifest，不依赖它晚于start。 |
| `compaction_operation.py` | compactor producer | proposal路径保持自身call前manifest时序，`sizing_snapshot=not_applicable`。 |
| `proactive_compaction.py` | compactor manifest reader | 现有kind filter继续忽略ordinary manifest；增加ordinary-before-start反例。 |
| `tool_trace.py` / `durable/tool_trace.py` | manifest projection与reconstruction query | 可以先于RUN_STARTED投影同一event；不得要求run-start trace先存在，不改correlation/public readable semantics。 |
| `lifecycle_events.py` / `durable/schema.py` | event closed set/DDL | v2与新budget fact全新起库；不编码相对顺序。 |
| `read_api.py` / Service activity callback | 通用EventLog public sequence | raw Host progress stream可先看到activity=None的manifest，再看到context usage与RUN_STARTED；Service仍丢弃activity=None，只交付typed context usage与run lifecycle。测试冻结此顺序。 |
| projection runner / memory / audit / outbox | 按cursor顺序扫描并以class/type filter选择 | generic checkpoint必须跨过新前置event；memory/audit无新业务投影，outbox只消费terminal filter，不把manifest当terminal。 |
| recovery / dispatch scan | Run/Attempt/dispatch state rows及canonical lifecycle refs | manifest/start/fact同transaction，crash后只可能全有或全无；recovery不得把manifest当started truth。CAS miss/rollback与restart tests证明零孤立event。 |
| terminal/lifecycle consumers | `started_event_id/sequence`精确指向RUN_STARTED/ATTEMPT_STARTED；terminal按typed set | 前置event只改变全局sequence间隔，不改变row refs或terminal truth；禁止“前一条event就是start”的位置假设。 |

直接命中tests为
`test_run_input_builder.py`、`test_engine_ingest_mapping.py`、
`test_dispatch_scheduler.py`、`test_lifecycle_events.py`、
`test_tool_trace_projection.py`、`test_tool_trace_queries.py`；通用ordering/regression
tests补充 `test_watch_session_events.py`、`test_projection_runner.py`、
`test_recovery_scan.py`、`test_run_attempt_transitions.py`、
`test_outbox_projection.py`。Tool Trace只允许v2 schema/order适配，不允许借机实施
Issue #119 analyzer；public/recovery/terminal如需production语义补偿而非上述已有typed
filter自然成立，必须stop并重新裁决。

## 8. Implementation slices

### 8.1 Slice count 与切分依据

计划固定 **3 slices**。切分依据不是文件/模块数量，而是三个可独立review和回滚的
语义闭环：

1. complete candidate + estimator/manifest/pairing contract：稳定所有后续修改依赖的
   数据真源，并隔离manifest全新schema切换风险；
2. conservative-only也成立的canonical fact + Host→Service public projection：
   独立证明durable/public修改不依赖usage anchor；
3. anchor selection + signed-delta integration：在前两者之上改变预测算法，且可单独
   回滚到conservative而不删除fact/public contract。

三者分别对应依赖顺序、schema回滚风险与验证矩阵，满足control doc的语义闭环原则；
没有超过3 slices，不因涉及多个owner机械拆分。

### 8.2 Slice 1 — Exact candidate、estimator identity 与 manifest pairing foundation

**Objective**

建立complete candidate单一真源，补齐accepted compact source-boundary →
Conversation Memory post-compact delta projection，冻结estimator contract、
stage-aware action和manifest v2 direct pairing；所有当前dispatch-relevant sizing
仍先保持`conservative_fallback`，不实现canonical context-budget fact或public view。

**Expected outcome**

- pre-start、post-compact、fallback、reactive recovery与actual Runner request使用同一
  candidate projection/digest。
- accepted compact后，selected recent window只保留post-compact delta与未被selected
  compact覆盖的protected raw；current input保留一次，covered older raw不再进入exact
  candidate。
- complete ordinary manifest durable保存可直接用作`E_anchor`的sizing snapshot。
- usage diagnostic不再从display text重建；只接受accepted link指向manifest。
- estimator公式/常量与无usage conservative fallback保持；输入从subset升级为complete
  candidate，token值与threshold decision允许安全地增大/跨阈值，不承诺逐值兼容。
- sizing不依赖manifest；只有allow后分配并由manifest/start transition实际消费同一
  identity。ordinary soft/hard不写manifest或durable Attempt identity。
- ordinary soft只启动同一snapshot唯一 proactive operation；post-compact/fallback
  soft保留soft pressure但允许dispatch；hard显式terminal fail closed。

**Allowed production files**

- `dayu/host/context_budget.py`
- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`
- `dayu/host/_runner_call_manifest.py`
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/proactive_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/schema.py`

`dayu/host/durable/run_transition.py`不修改；若existing
`StartGovernedRunInput`直接证据失效则stop。

**Allowed tests**

- `tests/host/test_context_budget.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_outbox_projection.py`

**Allowed docs / README trigger**

- `dayu/host/README.md`
- `tests/README.md`

Slice 1开始修改前必须先读这两个README自身的Agent更新约束。compact payload /
memory / context action是Host稳定owner contract，新增owner tests属于tests手册职责；
若其README职责判断要求同步，则在本slice更新，不延后用production兼容分支替代。根
README、`dayu/README.md`与Service README当前无Slice 1职责变化，audit后预期不修改。

**Exact changes**

1. 在`compact_payload.py`扩充strict semantic parser：raw
   `source_boundary_refs`必须非空、元素为非空str且唯一；第一个投影为
   `current_input_ref`，其余投影为`compacted_source_refs`。不写compat parser。
2. 在`memory.py`的accepted compact event owner按§5.8更新selected recent并同源重建
   recent evidence；incremental、rebuild、inline repair与persisted reload共享同一
   rule。`run_input.py`不得新增coverage filter。
3. 冻结estimator id/version/range与conservative `ContextSizingResult` contract；新增
   complete candidate adapter，不改公式常量；pressure纯阈值派生，action按stage
   派生。
4. 将RunInputBuilder的pure candidate assembly提取为可在Attempt start前调用的typed
   preparation；actual request只消费并验证frozen candidate。
5. 把existing memory catch-up/lag repair前移到candidate freeze前；tool schema
   selection与Attempt-scoped ToolRuntime handle构造分离，但二者消费同一frozen
   selected-tool snapshot。
6. 所有candidate stage都提供source watermark、projection ref/digest、tool schema
   digest、request semantics digest。
7. pre-start sizing先使用identity-free candidate；decision=allow后在同一transaction
   构造一个`StartGovernedRunInput`，manifest和existing durable transition消费其中
   同一attempt/execution identity。ordinary soft/hard不写manifest、不分配identity。
8. ordinary soft进入唯一proactive operation；post-compact/fallback soft直接进入
   allow start且pressure保持soft。post-compact/fallback hard返回closed terminal
   outcome，在同一transaction复用既有unstarted Run failure transition；不得返回
   ambiguous `None`或启动第二次proactive operation。
9. manifest直接切v2，三个producer写strict `sizing_snapshot`；continuation只从
   accepted Engine input projection、首个complete manifest的selected-tool descriptor
   与admission-frozen policy/request semantics重建，crash缺源写closed unavailable。
10. usage ingest通过accepted link读取manifest sizing snapshot，删除
   `_estimate_usage_observation_input`和`display_text` estimate。
11. allow start precondition miss抛private rollback exception并由`run_write`外caller转为
   无dispatch；低层CAS_LOST沿existing HostDurableError传播；两者都零孤立manifest。
12. 按§7.4适配全部direct manifest consumers并验证public/recovery/projection/Tool
   Trace/terminal ordering；不改变Issue #119 correlation。
13. `supports_stream_usage`不进入usage availability分支；不增加anchor selection、
    signed-delta公式或public activity。

**Owner-level assertions**

- complete candidate的messages/tool schemas与actual `AgentRunRequest` digest相等。
- compact payload parser接受`[current]`与`[current, *covered]`，并拒绝empty、
  duplicate、non-string、empty-string、missing field；所有consumer只读typed
  `current_input_ref/compacted_source_refs`。
- owner projection覆盖：covered older user/assistant/evidence raw删除；current input
  保留一次；未被selected compact覆盖的protected raw保留；compact后新delta保留；
  `recent_evidence_items`与更新后的selected window一致。
- 同一event序列的full rebuild、incremental projection、inline delta repair与persisted
  snapshot reload得到相同selected recent/diagnostic/digest结果。
- memory selected与ordinary protected raw tail按source ref和content digest去重；确有
  covered material时post-compact conservative size下降；无covered material时不删除
  current/protected raw、不伪造size下降。
- mixed中文/英文财报、JSON/table excerpt、tool facts/citations/memory/compact/tool
  schemas继续按既有estimator常量计入。
- 同一fixture中complete candidate严格包含旧subset时，新估算不小于旧subset；覆盖新增
  system/tool-schema/structured atoms导致soft/hard threshold crossing，且每个atom
  恰计一次、无遗漏/双计。
- v1 manifest、缺sizing snapshot、unknown/partial fields拒绝。
- compactor manifest为`not_applicable`；continuation四个frozen source逐项缺失均为
  对应closed unavailable，不能从当前config重选或伪装complete。
- context policy缺失的actual dispatch仍写同identity manifest，但
  `sizing_snapshot=unavailable(context_policy_unavailable)`；不生成sizing
  result/fact/activity。
- exact linked usage取得manifest `E_anchor`；missing/mismatch link只得到typed
  unavailable，不使用display text。
- allow path事件顺序为manifest→RUN_STARTED→ATTEMPT_STARTED并消费相同identity；
  ordinary soft/hard零manifest/Attempt identity；precondition miss与low-level CAS lost后
  EventLog/payload/state零孤立写入。
- stage matrix精确覆盖9个组合：ordinary normal/soft/hard分别allow/compact/block；
  post-compact与dispatch-fallback normal/soft/hard分别allow/allow/block。soft
  pressure值不改写；post-compact/fallback hard均产生Run terminal fact，零silent
  accepted Run；同一snapshot只有一条proactive request。
- Tool Trace correlation/public readable behavior无语义变化；public stream、
  projection checkpoint、recovery、outbox与terminal refs满足§7.4。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_context_budget.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py \
  tests/host/test_memory_repair.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_durable_schema.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_projection_runner.py \
  tests/host/test_recovery_scan.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_outbox_projection.py
python -m pyright dayu/ tests/ utils/
```

**Completion signal**

compact typed boundary→memory post-compact delta→candidate→stage-aware estimate/action
→allow identity→manifest→start transition→actual request→usage pairing形成不循环同源
闭环；所有预算仍为conservative method，但使用完整candidate；covered material产生
真实收缩、无covered material不伪造收缩；v2、consumer ordering、terminal与rollback
tests通过。

**Stop condition**

- 无法在`RUN_STARTED`前冻结与actual request严格同一的candidate；
- 必须读取display text/request id/timestamp才能pair；
- 必须修改Engine理解Host policy；
- 必须改Tool Trace analyzer/correlation production contract；
- 必须修改`dayu/host/durable/run_transition.py`或通用transaction runner才能消费同一
  identity/保证rollback；
- production证据表明compact coverage不能由`compact_payload` typed boundary与
  Conversation Memory projection唯一拥有，或必须在RunInput再建第二套filter；
- protected recent raw是否被selected compact覆盖无法从typed canonical refs唯一判断；
- post-compact/fallback hard无法通过既有Run failure owner显式收口，或需要第二次
  proactive operation；
- 任何allowed files外production修改。

### 8.3 Slice 2 — Independent canonical fact 与 Host→Service typed projection

**Prerequisite**

Slice 1 accepted；complete candidate和conservative `ContextSizingResult`可用。
本slice不依赖任何usage anchor。

**Objective**

仅用`conservative_fallback`先完整交付`CONTEXT_BUDGET_EVALUATED`、ordering、
idempotency、Host public activity与Service typed pass-through，证明durable fact不是
anchored算法附属事件。

**Allowed production files**

- `dayu/host/context_budget.py`
- `dayu/host/context_events.py`
- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/schema.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/__init__.py`
- `dayu/service/entrypoint_runtime.py`

**Allowed tests**

- `tests/host/test_context_budget.py`
- `tests/host/test_context_budget_evaluated.py`（新增）
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_public_host_event.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_import_boundary.py`
- `tests/service/test_weak_typing_guard.py`
- `tests/cli/test_activity_renderer.py`

**Allowed docs / README trigger**

- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`

修改前先读目标README自身约束；只同步本slice已经实现的canonical fact、Host public
view、Service typed pass-through与稳定验证入口。

**Exact changes**

1. 复用Slice 1的sizing stage/method/pressure/stage-aware action/result typed
   contract；本slice producer继续固定method为`conservative_fallback`，不导入anchor
   resolver。
2. 新增strict `CONTEXT_BUDGET_EVALUATED` schema、deterministic identity与append
   helper。
3. ordinary、post-compact、reactive post-compact、tier fallback与hard-block路径先
   append fact，再写driven transition；同transaction。
4. 复用§5.6唯一rollback方案：start precondition miss抛private rollback exception并
   由caller转成无dispatch；low-level CAS lost沿existing durable error传播；两者使
   同transaction内projection/manifest/fact整体rollback，不得留下孤立truth。
5. duplicate watch/reconciliation复用既有fact；同identity矛盾结果fail closed。
6. internal compactor proposal sizing和仅到达的历史usage不写fact。
7. 新增Host public DTO/kind/invariants与strict read projection。
8. 新增Service同形DTO/kind/invariants和exhaustive typed mapper；callback不改。
9. raw `USAGE_REPORTED`保持`activity=None`；CLI production不改。

**Owner-level assertions**

- **policy存在但usage缺失**时conservative fact成立、typed context usage可用且method
  为fallback；policy缺失时不调用sizing、不产生fact/activity，Run保持既有
  allow-without-budget / no-budget governance path。
- ordinary/post-compact/fallback各有独立identity。
- exact event order先fact后compact/start/attempt。
- CAS precondition miss与low-level CAS lost后，EventLog中零
  `RUNNER_CALL_INPUT_ASSEMBLED`/`CONTEXT_BUDGET_EVALUATED`孤立truth，payload/state
  同样零残留；正常allow只消费一套identity。
- repeated governance只一条fact；矛盾result被拒绝。
- normal/soft/hard、basis points >10000不clamp。
- canonical fact同时保存真实`pressure_level`与stage-aware`budget_decision`：
  post-compact/fallback soft的public pressure仍为soft且fact-before-dispatch；
  hard fact-before-terminal failure，零silent accepted Run、零第二次proactive request。
- policy missing时不伪造fact，context usage unavailable。
- Host activity只公开七个字段；不含raw usage、refs、delta、policy ref。
- Service字段逐一相等；通过monkeypatch使任一重算会产生不同值的测试证明无重算。
- callback收到typed context usage；CLI formatter不崩溃且不自行显示百分比。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_context_budget_evaluated.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_proactive_compaction_operation.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_lifecycle_events.py \
  tests/host/test_durable_schema.py \
  tests/host/test_host_activity_event_projection.py \
  tests/host/test_public_host_event.py \
  tests/host/test_public_contracts.py \
  tests/host/test_package_exports.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_projection_runner.py \
  tests/host/test_recovery_scan.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_outbox_projection.py \
  tests/service/test_entrypoint_runtime.py \
  tests/cli/test_activity_renderer.py
python -m pyright dayu/ tests/ utils/
```

**Completion signal**

在anchor代码尚不存在/不可用的情况下，fact、ordering、idempotency、Host public view、
Service callback已完整通过。

**Stop condition**

- fact必须依赖usage/anchor才能生成；
- public projection需要读取raw EventLog usage或重算；
- exact ordering无法在同transaction保证；
-需要UI production改动；
-需要compat event/schema reader；
-任何allowed files外production修改。

### 8.4 Slice 3 — Provider-neutral anchor resolver 与 adaptive sizing integration

**Prerequisites**

Slice 1、2 accepted。Slice 2的fact/public contract保持不变，只允许method/value从
同一result自然变为anchored。

**Objective**

建立durable compatible anchor resolver，并将signed-delta prediction接入所有
dispatch-relevant sizing stage；完成全Work Unit acceptance与docs。

**Allowed production files**

- `dayu/host/context_anchor.py`（新增）
- `dayu/host/context_budget.py`
- `dayu/host/_runner_call_manifest.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`

**Allowed tests**

- `tests/host/test_context_anchor.py`（新增）
- `tests/host/test_context_budget.py`
- `tests/host/test_context_budget_evaluated.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_import_boundary.py`

**Allowed docs**

- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`

**Exact changes**

1. 按§5.4 exact typed interface实现keyset anchor scan；全部pages与latest accepted
   compact boundary在调用方同一个`HostTransaction` consistent snapshot内读取，
   不自开transaction、无模块mutable state。
2. 以complete manifest + accepted link + unique valid usage + exact accepted
   iteration-completed preview的conjunction实现successful ordinary eligibility；
   terminal Run不替代completion。
3. 实现provider/model/window/estimator/request-semantics compatibility。
4. 实现signed delta与range validation；anchor问题统一返回closed fallback reason。
5. ordinary/post-compact/fallback/reactive paths都调用相同sizing entry point。
6. public fact/view继续只消费result；不新增anchor refs到public DTO。
7. accepted compact immediate candidate强制fallback；新successful ordinary usage与
   completion后才刷新。
8. supports flag只作为request semantics snapshot，不作为presence判断。
9. README只同步当前已实现owner/contract/validation入口，不写WU过程。

**Formula/integration assertions**

- positive delta：`U=6200,Ea=6000,Ec=6500 => P=6700`。
- negative delta：`U=6200,Ea=7000,Ec=6000 => P=5200`，不clamp delta。
- `context_window=10000,soft=6500,U=6200,Ea=6000,Ec=6300`在当前dispatch前
  soft compact。
- no usage、invalid、ambiguous、link missing/mismatch均
  `predicted == exact conservative E_current`且Run不因usage失败。
- tool loop覆盖initial `tool_calls` completion与complete continuation；older anchor跨
  多个missing-usage但manifest/link/completion complete的calls仍可用。
- usage先到后Runner failure、manifest/link/usage后crash无completion、terminal
  failed/cancelled/lost无completion、Run succeeded但last iteration completion缺失均
  barrier+fallback；不得用Run terminal补洞。任一lineage gap立即fallback。
-所有compatibility维度逐项反例。
- accepted compact invalidation与new anchor refresh。
- compactor/reactive overflow永不anchor。
- crash/replay对相同facts得到相同method/prediction/decision/fact id。
- continuation projection/tool schema/policy/request semantics四类来源逐项crash缺失时
  manifest写对应closed unavailable并fallback，不从当前effective config重建。
- `supports_stream_usage=False + actual usage`可anchor；
  `supports_stream_usage=True + no usage`fallback。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_context_anchor.py \
  tests/host/test_context_budget.py \
  tests/host/test_context_budget_evaluated.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_proactive_compaction_operation.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_recovery_dispatch.py \
  tests/engine/runners/openai/test_sse_usage_recorded.py \
  tests/engine/runners/openai/test_sse_empty_choices_with_usage.py \
  tests/engine/runners/openai/test_stream_usage_capability_gating.py \
  tests/engine/runners/openai/test_non_stream_response.py
python -m pyright dayu/ tests/ utils/
```

**Completion signal**

全部formula、fallback、compatibility、lineage、event ordering、public projection与
replay acceptance通过；README audit完成。

**Stop condition**

- 需要provider-name branch、tokenizer、remote count或dynamic ratio；
- 无法只靠manifest/link/usage/compact boundary证明lineage；
- 必须越过invalid/ambiguous/gap寻找更旧anchor；
- 必须侵入Issue #119 analyzer correlation owner；
- 必须把anchor internals暴露给Service/UI；
-任何allowed files外production或docs修改。

## 9. Test and validation matrix

### 9.1 Focused owner tests

| area | assertions |
| --- | --- |
| compact source boundary | strict typed current/covered roles；empty/duplicate/wrong-type拒绝；consumer不索引raw list；no compatibility |
| Conversation Memory | covered older raw删除；current input、uncovered protected raw、新delta保留；recent evidence同源；rebuild/incremental/repair/reload一致 |
| estimator | 既有CJK/Latin/JSON/tool-schema公式与常量；stable id/version；complete candidate全atom恰计一次；strict subset不低估与threshold crossing |
| manifest v2 | exact fields、closed states、all producers、v1/unknown/partial拒绝、hot/descriptor/digest graph；continuation四类frozen source与closed unavailable |
| direct pairing | unique accepted link；same iteration；missing/mismatch/ambiguous；无request id/time/display text |
| anchor | 同transaction snapshot；positive/negative delta；tool loop；older anchor through completed missing-usage calls；usage-before-failure/crash-gap/terminal barriers；all compatibility dimensions |
| policy/action | policy present + usage absent产生conservative fact；policy none保持no-budget/no-fact；fixed ratios/thresholds；>= comparison；9-cell stage matrix；soft pressure/action分离；hard terminal fail closed；over-100 utilization no clamp |
| candidate stages | ordinary/post-compact/dispatch-fallback；internal compactor excluded |
| compact size effect | covered material存在时exact size真实下降；无covered material时不丢current/protected raw、不伪造下降；memory/raw-tail source+digest去重 |
| durability | allow后identity allocation/consumption；ordinary soft/hard零manifest/Attempt identity；precondition miss与CAS lost整笔rollback；fact identity/idempotency/conflict/order；replay/recovery determinism |
| Host public | kind/view/invariants；anchored/fallback；normal/soft/hard；policy unavailable；raw usage hidden |
| Service | exact field pass-through；enum exhaustiveness；callback delivery |
| CLI regression | optional context usage不破坏existing formatter；不新增具体display |
| layering | Engine无Host import；Service无durable import；无weak typing/glue |
| ordering consumers | public stream/activity、generic projection checkpoint、recovery scan、Tool Trace query、outbox terminal filter、lifecycle exact refs |

### 9.2 Required command sequence

每个slice代码修改后：

```bash
source .venv/bin/activate
pytest <该 slice focused tests> -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

最终affected suites：

```bash
source .venv/bin/activate
pytest tests/host tests/service tests/engine tests/cli -q
```

最终项目标准suite：

```bash
source .venv/bin/activate
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools \
  tests/host tests/runtime tests/service tests/engine -q
```

完整pyright：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

### 9.3 Per-file coverage >=80%

每个slice从其accepted base创建独立coverage data，运行该slice focused + affected
integration tests，然后对**每个实际changed production Python file**单独执行
`--fail-under=80`，不能用aggregate掩盖单文件不足：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run --branch -m pytest <该 slice coverage tests> -q
for file in <该 slice 实际 changed production Python files>; do
  python -m coverage report --include="$file" --fail-under=80
done
```

若某changed production file低于80%，只能补owner-level行为测试；禁止pragma、omit、
fake-only execution、降低阈值或修改无关production代码padding coverage。

### 9.4 Static/source audits

```bash
rg -n "_estimate_usage_observation_input|USER_INPUT_ACCEPTED.*display_text" \
  dayu/host tests/host
rg -n "source_boundary_refs|current_input_ref|compacted_source_refs" \
  dayu/host/compact_payload.py dayu/host/memory.py dayu/host/run_input.py \
  tests/host/test_context_compact_events.py tests/host/test_memory_projection.py \
  tests/host/test_memory_repair.py
rg -n "runner_call_input_manifest\\.v1" dayu tests
rg -n "hasattr\\(|getattr\\(" \
  dayu/host/compact_payload.py dayu/host/memory.py dayu/host/run_input.py \
  dayu/host/context_budget.py dayu/host/context_anchor.py \
  dayu/host/context_events.py dayu/service/entrypoint_runtime.py
rg -n "from dayu\\.host|import dayu\\.host" dayu/engine
rg -n "dayu\\.host\\.durable" dayu/service
rg -n "CONTEXT_BUDGET_EVALUATED|CONTEXT_USAGE|HostContextUsageView|EntrypointContextUsage" \
  dayu tests dayu/host/README.md dayu/service/README.md tests/README.md
rg -l "RUNNER_CALL_INPUT_ASSEMBLED|RUNNER_CALL_INPUT_ITERATION_LINKED" \
  dayu tests | sort
git diff --exit-code -- dayu/host/durable/run_transition.py
git diff --check
```

预期为：display-text estimator零命中；source-boundary grep只显示
`compact_payload` raw owner、`memory` typed consumer与`run_input`既有current-input /
raw-tail dedupe，若出现RunInput读取raw `source_boundary_refs`立即失败；manifest v1
零命中；changed owner新增weak-typing零命中；Engine→Host反向依赖零命中；Service
durable依赖零命中。context contract grep与manifest consumer grep必须命中§7.4完整
producer/consumer/tests/docs并由implementation artifact逐项对账；
`run_transition.py`必须零diff；最后`diff --check`通过。

## 10. Schema cutover decision

- 本Work Unit按全新schema起库。
- `RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION`直接从v1切v2。
- EventLog DDL closed event set直接包含`CONTEXT_BUDGET_EVALUATED`。
- 不写旧manifest reader、旧event payload reader、migration、dual-write、alias、
  fallback parser、compat fixture或旧库测试。
- tests中的v1 fixture全部更新或改为strict rejection assertion；不得倒逼production
  兼容。
- 本计划不修改workspace migration/plugin，因为当前task明确要求全新起库且未要求兼容升级。

## 11. README trigger audit

每个slice修改Host/Service/tests前先读目标README自身的Agent更新约束，并在该slice
artifact记录audit；属于其职责的稳定contract应在同slice更新，不机械同步过程状态。
全WU完成时再做一次aggregate audit：

| README | decision | reason/content boundary |
| --- | --- | --- |
| `dayu/host/README.md` | update required | compact source-boundary / Conversation Memory delta owner、stage-aware action、manifest direct pairing、canonical fact/event ordering、public Host view均是稳定Host contract |
| `dayu/service/README.md` | update required | 新增`EntrypointContextUsage`与activity callback typed pass-through，明确Service不重算 |
| `tests/README.md` | update required | 新增compact payload、memory projection/repair、stage matrix与Context Governance focused test/coverage命令，属于现有测试手册职责 |
| `dayu/engine/README.md` | audit, no update expected | Engine production contract不改；既有usage normalize与supports gating语义保持 |
| `dayu/README.md` | audit, no update expected | `UI -> Service -> Host -> Engine`关系和assembly ownership不变 |
| root `README.md` | no update | 无用户可见CLI/Web/WeChat展示或workflow变化 |
| CLI README（不存在独立trigger） | no update | 具体UI展示是non-goal，CLI production不改 |

若实际implementation改变上述预期（例如修改Engine production或具体CLI output），必须
stop并重新做README/scope裁决，不能机械扩写。

## 12. Risks、open questions 与 residual risk classification

### 12.1 Blocking questions

None。设计与代码已直接确定owner、schema、formula、ordering、public fields与failure
boundary；本计划没有需要implementation agent自行发明的契约。

### 12.2 Residual risks

| risk | classification / owner | mitigation |
| --- | --- | --- |
| pre-start exact candidate refactor已暴露accepted compact后memory selected window仍含covered raw | fixed in Slice 1；compact payload + memory owner | typed current/covered boundary；owner projection删除covered raw；RunInput不补偿 |
| source boundary只含current input或covered refs未命中selected window时，测试可能错误要求size下降 | fixed in Slice 1 tests | 分离“确有covered material”和“无covered material”矩阵；后者禁止伪造下降 |
| protected raw同时由memory selected与ordinary raw tail提供造成双计 | fixed in Slice 1 | 复用source-ref与content-digest去重；owner integration test冻结 |
| post-compact/fallback soft若继续沿ordinary action会重复compact或静默不dispatch | fixed in Slice 1；ContextSizingResult/dispatch owner | 9-cell stage matrix；soft允许dispatch并保留pressure；同snapshot operation count=1 |
| post-compact/fallback hard普通返回`None`会留下accepted Run | fixed in Slice 1；Host lifecycle owner | closed dispatch/terminal outcome；同transaction显式Run failure |
| 当前worktree partial implementation尚未完成tests/type/coverage | not accepted；owned by resumed Slice 1 after plan re-review | amendment双路re-review pass前禁止继续implementation或commit |
| session历史较长时anchor scan成本 | fixed in Slice 3 | indexed session/event-sequence keyset paging；遇latest accepted compact boundary停止；不加任意总cap |
| usage合法但provider token口径与Host heuristic长期偏差 | accepted product property，属于本WU设计目标 | 只校正compatible anchor；不承诺billing-grade精确 |
| schema v2不读取旧workspace | explicitly accepted by project schema policy | 全新起库；no compat；README不伪装为可升级 |
| context usage activity增加事件数量 | fixed in Slice 2 | 每candidate deterministic id/dedupe；internal proposal不emit |
| provider返回prompt_tokens=0或极大值 | fixed in Slice 3 | strict range；P非正/越界fallback；public utilization不clamp |
| Tool Trace仍保存internal usage diagnostic | assigned to existing Issue #119 analyzer owner；本WU不改correlation | anchor resolver绝不消费Tool Trace/context_pressure/provider request id |
| concrete UI暂不展示typed usage | explicit non-goal，future UI owner | existing callback contract已准备；CLI regression确保不破坏 |
| live provider差异未probe | accepted non-blocking risk | provider-neutral contract tests + existing parser tests；usage absence guaranteed fallback |

没有unclassified residual risk。

## 13. Implementation completion report format

每个slice implementation artifact必须报告：

- `status: complete|blocked`
- slice id/name与allowed files核对
- changed files
- owner/contract changes
- event/state/data-flow changes
- exact tests与结果
-每个changed production file coverage结果
- full pyright结果
- README decision（Slice 3）
- findings/stop conditions
- residual risks及分类
- next entry point（只交给后续Gateflow Controller，不自行进入review）

整个implementation完成报告必须明确：

- 两个独立修改分别改了什么；
- 3 slices及切分依据；
- anchored与fallback owner决策；
- canonical fact ordering/idempotency；
- Host→Service无重算projection；
- schema full-new/no-compat decision；
-验证命令、测试数、逐文件coverage、full pyright；
- README实际更新；
- blocking questions（预期None）；
- remaining risks/owners；
- 未执行具体UI、live provider probe、Issue #119 analyzer work。

## 14. Plan review finding disposition

Controller adjudication是唯一finding裁决真源。accepted findings全部在本plan修复；
被Controller驳回的finding不采纳其建议，不借机扩大scope：

| finding | disposition | plan location / reason |
| --- | --- | --- |
| DS-01 | fixed | §5.1、§5.3、§8.2：sizing使用identity-free candidate；allow后同transaction分配并由manifest/start实际消费identity；ordinary soft/hard零manifest/Attempt identity。 |
| CTRL-PR-001 | fixed | §2、§5.3、§7.1、§8.2：明确不修改`run_transition.py`；existing `StartGovernedRunInput`为exact interface，补`test_run_attempt_transitions.py`与dispatch owner tests。 |
| DS-02 | fixed | §5.6、§8.2、§8.3：唯一private exception rollback方案，区分normal UPDATED、precondition miss caller handling与low-level CAS lost传播，并断言零孤立manifest/fact/payload/state。 |
| DS-03 | fixed | §5.4、§6、§8.4：以现有manifest/link/usage/accepted iteration-completed preview定义success与barrier，覆盖tool loop、usage-before-failure、crash gap、terminal Run，不新增completion truth。 |
| DS-04 | fixed | §5.1、§8.2、§9.1：只保持estimator公式/常量与fallback语义，不承诺旧subset token相等；增加范围扩大、不低估、threshold crossing验收。 |
| DS-05 | fixed | §4、§5.4、§8.4：显式`HostTransaction + EventLogStore + ContextAnchorQuery`接口；same snapshot全分页；无mutable state/Service/UI durable访问。 |
| DS-06 | fixed | §5.6、§8.3、§9.1：只在policy存在且usage缺失时产生conservative fact；policy none保持既有no-budget/no-fact路径。 |
| DS-07 | rejected-with-reason | 不采纳。§5.7已要求Service对kind/method/pressure closed enum做exhaustive fail-closed mapping；私有helper名称不是public contract，Controller判定无需固定。 |
| DS-08 | rejected-with-reason | 不采纳。`supports_stream_usage`改变request serialization shape，纳入digest只会保守失效并fallback，不以capability推断usage presence，符合design §25。 |
| MIMO-001 | fixed | §2、§7.1、§7.4、§8.2、§9.1：完整production/tests consumer audit，纳入public/recovery/projection/Tool Trace/terminal影响与allowed scope。 |
| MIMO-002 | rejected-with-reason | 不采纳。strict-native per-Session owner已成立，且§5.4冻结resolver在单一Host transaction snapshot内全分页；跨transaction并发反例不适用。 |
| MIMO-003 | fixed | §5.3、§8.2、§8.4：冻结continuation projection/selected schema/policy/request semantics唯一来源；四类crash缺源closed unavailable+fallback，禁止当前config重选。 |
| MIMO-004 | rejected-with-reason | 不采纳。manifest`sizing_snapshot`只冻结conservative contract，不包含后选anchored/fallback method；`input_snapshot_digest`与manifest digest职责已分别定义，method变化不会重写manifest。 |
| Slice 1 accepted blocker：compact coverage owner缺失 | fixed in amendment | §2、§4、§5.8、§6.3、§7、§8.2、§9：compact payload typed current/covered boundary + Conversation Memory唯一projection；禁止RunInput filter。 |
| Slice 1 accepted blocker：pressure/action非stage-aware | fixed in amendment | §1.3、§4、§5.5、§6.4-§6.5、§8.2-§8.3、§9：9-cell matrix；post-compact/fallback soft allow且保留pressure，hard terminal fail closed。 |
| Slice 1 scope / verification reopening | fixed in amendment | §0、§7、§8.2、§11-§12：新增compact payload、memory与owner tests；partial implementation保持not accepted，双路re-review前不恢复。 |

## 15. Plan gate completion

- status：`amendment complete / implementation not accepted`
- artifact：
  `docs/reviews/wu-ctx-01-plan-codex.md`
- slice count：`3`
- slice basis：共享complete-input/manifest contract、独立durable/public fact闭环、
  adaptive anchor算法闭环；按依赖、schema回滚风险与验证矩阵切分，不按文件切分。
- key owner decisions：
  - compact payload strict parser拥有persisted source boundary typed角色；
    Conversation Memory拥有covered raw removal与post-compact delta projection；
    RunInput不拥有coverage过滤；
  - Host RunInput/manifest拥有complete candidate与`E_anchor`；
  - sizing只消费identity-free candidate；Host dispatch在allow后生成一次
    `StartGovernedRunInput`，manifest与unchanged durable transition实际消费同一
    Attempt/execution identity；
  - Engine只拥有actual legal usage normalize；
  - Host ingest只拥有direct iteration pairing；accepted iteration-completed preview
    是successful runner-call所需的现有durable completion evidence，Run terminal不补洞；
  - Context Governance拥有anchor/prediction/threshold/pressure与stage-aware action；
    post-compact/fallback soft允许dispatch且不改写pressure，hard显式terminal
    fail closed，同snapshot不启动第二次proactive operation；
  - canonical fact与Host public view消费同一result；
  - Service只typed pass-through，UI不重算。
- validation plan：每slice focused tests + full pyright；最终Host/Service/Engine/CLI与
  project standard suites；每个changed production file line coverage `>=80%`；
  schema/import/stale-field/diff audits。
- blocking questions：`None`
- residual risks：均已分类，见§12.2。
- partial implementation：保留在worktree但仍为`not accepted`；focused tests、full
  pyright与coverage均不得沿用为通过证据。
- next entry point：只交回Controller进入AgentMiMo / AgentDS双路`plan re-review`；
  re-review pass并创建新的accepted-plan-amendment protected local commit后，才恢复
  Slice 1 implementation。
