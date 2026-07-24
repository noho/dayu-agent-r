# WU-CTX-01 code-generation-ready implementation plan（AgentCodex）

## 0. Plan gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- Issue：GitHub Issue #20。
- 类型：architecture-sensitive issue / public-contract change。
- 当前 gate：`Slice 1 first-call producer plan review fix`；本 artifact只落实
  Controller第三次计划评审§5：exact source policy strict load、wait resume闭集、
  direct promotion整条旁路删除、5-stage/source-refs/test closure、planned/committed
  wait identity、Engine limited manifest与三slice边界；不进入re-review、
  implementation、commit、push、PR或merge。
- 设计真源：`docs/host/design.md` §25 `Context Governance`，唯一设计入口为
  `Usage-Anchored Adaptive Context Sizing`。
- 控制真源：`docs/host/issues-implementation-control.md` 的 `Slice 切分原则` 与
  `WU-CTX-01 Usage-Anchored Adaptive Context Sizing` 全节。
- goal confirmation：
  `docs/reviews/wu-ctx-01-goal-confirmation-controller.md`，decision=`pass`，
  blocking open questions=`None`。
- 原 plan finding 裁决真源：
  `docs/reviews/wu-ctx-01-plan-review-controller-adjudication.md`；
  第一次 amendment 裁决唯一真源：
  `docs/reviews/wu-ctx-01-slice-1-stop-controller-adjudication.md`，
  第二次 amendment 裁决唯一真源：
  `docs/reviews/wu-ctx-01-slice-1-reactive-stop-controller-adjudication.md`，
  第三次 amendment 裁决唯一真源：
  `docs/reviews/wu-ctx-01-slice-1-attempt-producer-stop-controller-adjudication.md`，
  本轮plan review裁决唯一真源：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-review-controller-adjudication.md`，
  decision=`needs-fix`。两路 review只提供证据，不得覆盖Controller对全部
  first-call producer、第五stage、source replay、steer/wait candidate语义、scope与
  partial implementation的裁决。
- 代码基线：branch=`feat/wu-ctx-01`，
  HEAD=`5afe71fefa2486ff0e0d9b2026fee23685d48c2e`。
- preflight：当前不是 protected branch。worktree 已有大量 Slice 1 partial
  production/tests、Controller control doc 与 stop artifacts；它们必须原样保留，
  本 gate 不继续编辑。
- 本 amendment gate 允许写入仅为：
  `docs/host/design.md`、`docs/reviews/wu-ctx-01-plan-codex.md` 与
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-amendment-codex.md`。
- amendment completion status：`fixed / pending directed re-review`。accepted findings已通过pending producer
  / strict consumer双向穷举、closed `CONTINUATION`、5-stage/15-cell total function、
  startup strict replay、steer新input、wait pre-start continuity、neutral manifest
  identity signature与producer-local transaction编排收敛；前两次 amendment 的compact
  typed boundary、Conversation Memory projection、`REACTIVE_POST_COMPACT`与reactive
  recovery ordering继续有效。当前partial
  implementation仍为`not accepted`，必须等
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
   - 每个 dispatch-relevant ordinary / proactive post-compact / reactive accepted
     post-compact / dispatch-fallback / active-run continuation 候选输入先提交 canonical
     `CONTEXT_BUDGET_EVALUATED`，再执行该 decision
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
  `ORDINARY`、`POST_COMPACT`与`DISPATCH_FALLBACK`的hard都禁止dispatch并由各自
  合法owner显式fail closed；
  `REACTIVE_POST_COMPACT` normal/soft/hard全部允许recovery dispatch，且soft/hard
  pressure不改写；`CONTINUATION` normal/soft/hard全部允许已有lifecycle前进且
  pressure不改写。reactive accepted compact后不得因estimate hard追加
  `CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`或`RUN_LOST`。
- initial/queued、post-compact/fallback、reactive、startup、running/waiting steer与
  wait resume构成pending producer全集；每个新Attempt在start前有matching manifest，
  worker只strict消费。startup仅strict replay source，steer使用新
  `USER_INPUT_ACCEPTED`及新digest，wait resume在start前复用RunInput既有accepted-result
  continuity owner。
- reactive accepted compact在创建recovery Attempt前完成memory exact catch-up、
  identity-free candidate freeze、`REACTIVE_POST_COMPACT` conservative sizing、
  identity allocation和manifest写入；actual recovery request按同一
  attempt/execution读取该manifest及digest-verified candidate，不得二次assembly。
- recovery start前置条件miss或CAS/integrity failure使本事务candidate
  payload/manifest/fact/start rows整体rollback；已提交accepted compact保持不变，
  本调用不wake且不写矛盾terminal facts。没有并发winner时Run留在`RECOVERING`等待
  reconciliation；存在winner时只信任winner committed state。
- reactive hard + allow的反例必须继续真实dispatch；若provider再次overflow，在
  `max_reactive_compactions_per_run`内进入下一条existing reactive operation，超过上限
  才走真实`CONTEXT_COMPACTION_FAILED`与既有fallback/failure收口。
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
| `dayu/host/context_budget.py::ContextSizingResult` / `_pressure_and_decision` | partial implementation已有reactive第四stage，但startup/steer/wait/Engine continuation仍机械落入`ORDINARY`或完全未sizing。 | pressure与action拆开判定并扩为5-stage/15-cell；`REACTIVE_POST_COMPACT`与`CONTINUATION`三种pressure都allow，pressure仍按阈值如实保留。 |
| `dayu/host/compact_payload.py::ContextCompactedSemanticPayload` / `source_boundary_refs` | producer确定性写第一个`request.current_input_ref`与后续去重material/evidence/fact refs，但strict semantic parser没有读取 persisted `source_boundary_refs`。 | compact payload是唯一typed read owner；parser校验非空、非空字符串、全局唯一并投影`current_input_ref`与`compacted_source_refs`，consumer不得索引raw list。 |
| `dayu/host/memory.py::project_conversation_memory_event` | `CONTEXT_COMPACTED`更新summary/facts/anchors/intents/reference continuity与latest compact ref，却没有移除已被accepted compact覆盖的`selected_recent_window`；`recent_evidence_items`随后仍从错误window派生。 | Conversation Memory projection按typed covered refs移除covered older raw，保留current input与未covered protected raw；rebuild/incremental/repair/persisted snapshot统一复用该owner rule。 |
| `dayu/host/run_input.py::_memory_messages`与protected raw-tail assembly | 无条件渲染snapshot selected recent；既有raw-tail path已有source ref/content digest dedupe。 | 不在RunInput新增coverage filter；只消费修正后的typed memory view并保留现有raw-tail dedupe。 |
| `dayu/host/dispatch.py::_run_pre_start_governance` | pre-start 只用 `PreDispatchCompactMaterialView.budget_fragments` 估算；allow 时直接写 `RUN_STARTED/ATTEMPT_STARTED`，没有 canonical budget fact。 | pre-start 必须先从与实际 Runner input 同源的 complete candidate 构造 typed sizing result；fact append 与后续 transition 同事务有序提交。 |
| `dayu/host/run_input.py::RunInputBuilder.build` | actual messages、tool schema 与 `RUNNER_CALL_INPUT_ASSEMBLED` 目前在 Run/Attempt 已启动后才构造/记录。 | 将“纯候选组装/投影”与“Attempt runtime handle/AgentRunRequest 构造”分离；前者可在 start 前冻结，后者必须验证并消费同一个 candidate digest，不能再次自由组装另一份输入。 |
| `dayu/host/durable/run_transition.py::StartGovernedRunInput` 与 `start_governed_run_with_starting_attempt_in_transaction` | transition 已要求调用方提供 `attempt_id`、`execution_id`、`dispatch_record_id` 与两个 start event id，并用这些精确值创建 Run/Attempt/dispatch rows；transition 自身不生成 identity。 | existing governed transition的typed input与row-write语义不改；`dispatch.py`只在allow后构造一次typed `StartGovernedRunInput`，manifest与transition共同消费其中同一identity。`run_transition.py`文件仍允许并要求删除legacy direct promotion transition及其专属类型/helper。 |
| `dayu/host/durable/transaction.py::HostTransactionRunner.run_write` | transaction body正常返回即commit；任意异常会rollback并透传。 | CAS miss不得返回普通 `None`；`dispatch.py` transaction body必须抛出私有 `_StartCandidateCasMissRollback`，在 `run_write` 外捕获并转成无dispatch结果。不得修改通用 transaction runner或引入rollback sentinel返回协议。 |
| `dayu/host/_runner_call_manifest.py` 与 `RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` | manifest v1 有完整 projection/ref lineage，但没有 estimator id/version、`E_anchor`、context window 或 request semantics contract。 | manifest schema 直接切到 v2；complete ordinary manifest 必须有严格 typed sizing snapshot，v1 不兼容读取。 |
| `dayu/host/engine_ingest.py::_estimate_usage_observation_input` | 从 `USER_INPUT_ACCEPTED.display_text` 重建估算；不是实际完整 runner input。 | 删除该重建路径。usage diagnostic/pairing 只能解析 accepted iteration link 指向的 digest-verified complete manifest。 |
| `dayu/host/engine_ingest.py::_execute_reactive_compaction` / `_complete_reactive_recovery` / `_StartReactiveRecoveryOperation` | accepted branch先在一笔事务提交`CONTEXT_COMPACTED`，随后memory catch-up失败只告警，另起事务直接调用recovery start；当前没有freeze candidate或写manifest。 | accepted compact后必须先exact catch-up；start事务内按`REACTIVE_POST_COMPACT`冻结candidate、估算、写manifest，再调用existing recovery start。catch-up失败不得继续start。 |
| `dayu/host/dispatch.py::_build_frozen_run_input` 与 `dayu/host/run_input.py::load_prepared_runner_call_candidate` | actual dispatch已按Attempt/execution查找pre-start manifest，再读取digest-verified prepared candidate构造`AgentRunRequest`；缺manifest会fail closed。 | reactive recovery无需新wakeup payload或第二套request builder；只需在Attempt start前写同源manifest，actual request继续复用existing strict loader。 |
| `dayu/host/durable/run_transition.py::StartRecoveryRunInput` / `start_recovery_run_with_starting_attempt_in_transaction` | existing transition由caller提供新Attempt/execution/dispatch identities，并在`RECOVERING`前置条件下原样创建start facts与rows。 | recovery start contract保持；`run_transition.py`只允许删除legacy direct queue-promotion旁路及其专属类型/helper，不改变governed/recovery/wait transition语义。 |
| `dayu/host/durable/run_transition.py::FailRecoveringRunInput` / `fail_recovering_run_in_transaction` | typed input必填`context_compaction_failed_event_id`，`RUN_FAILED` payload也承诺该真实failed fact；`RUN_LOST`属于startup orphan owner。 | 只用于真实reactive compact/fallback failure；accepted compact estimate hard不得伪造failed ref、追加矛盾failed fact或改用lost。 |
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
| 对 `DispatchRecordStatus.PENDING` / `insert_dispatch_record` / durable row constructor 的反向审计 | production pending row只能由governed start、recovery start、wait resume、steer manual row与legacy direct promotion产生；`create_running_run_with_starting_attempt_in_transaction`没有production caller。scheduler ordinary owner已同时选择`ACCEPTED`与无active时最早`QUEUED`，因此queue promotion无需第二条direct start路径。 | 每个真实pending producer都必须在自己的transaction内先写matching manifest；彻底删除admission method/operation、durable direct transition、state row mutation及专属types/helpers/tests，queued production统一进入scheduler ordinary governance；`run_transition.py`允许且要求出现删除diff。 |
| `dayu/host/dispatch.py::_build_frozen_run_input` | worker对所有pending dispatch无条件按current `run_id/attempt_id/execution_id`调用`load_prepared_runner_call_candidate`；不存在producer-kind fallback。 | strict worker contract保持；禁止worker二次assembly、source-attempt fallback或current-config重选。 |
| `dayu/host/recovery.py::_start_recovery_dispatch_or_ready` | startup/orphan recovery直接调用recovery start transition，未读取source manifest且未写new Attempt manifest。 | startup recovery只能strict replay source prepared candidate/sizing；missing/mismatch由startup LOST/unrecoverable owner收口，合法路径manifest-before-start。 |
| `dayu/host/admission.py::_create_steer_attempt_result` | running/waiting steer已先append新`USER_INPUT_ACCEPTED`，随后直接写`RUN_STARTED`/`ATTEMPT_STARTED`/pending row；candidate与input digest尚未冻结。 | steer必须用新input event和新digest组装新candidate，不能复制source candidate；manifest/sizing在start facts之前。 |
| `dayu/host/waiting.py::_resolve_resume` + `run_input.py::_resume_wait_messages_from_current_start` | waiting transition在单一调用中append resolution/tool-result/start facts；既有continuity owner依赖已写`RUN_STARTED.tool_result_event_ref`，因此当前只能在start后重建。 | waiting owner在调用unchanged transition前，以deterministic event plan、strict request atom和planned accepted result调用同一RunInput continuity helper并冻结candidate；禁止复制tool-result projection或依赖start payload。 |
| `engine_ingest.py::_continuation_frozen_sources` / `_continuation_sizing_snapshot` | Engine `iteration_index>0` manifest从首个manifest手工解析tool-schema JSON，并把stage机械写为`ORDINARY`。 | 改为共享strict source loader，复用frozen policy/tools/disable-tools/mode/request semantics；stage=`CONTINUATION`，不得触发ordinary soft compact/hard block。 |

Root cause 的逻辑/数据真源是：**完整 runner-call candidate、conservative
estimate、iteration link 与 usage observation 尚未形成一个可校验的 durable
lineage contract；同时 accepted compact 的 persisted coverage尚未进入Conversation
Memory typed projection，且stage/action闭集既缺reactive专属语义，也缺active-run
continuation语义；accepted plan只修了ordinary/reactive producer，没有从pending row与
strict worker双向闭合startup recovery、steer、wait resume**。
display text、post-compact size不下降与accepted Run无dispatch都只是这些owner缺口的
下游表现。修复必须建立owner级contract，不能在RunInput、read API、Service、UI、
fixture或单入口用fallback shim补救。

## 3. Scope boundary、non-goals 与不过度设计说明

### 3.1 In scope

- complete ordinary/proactive-post-compact/reactive-post-compact/dispatch-fallback/
  active-run-continuation candidate 的单一 typed assembly 与digest-verified
  projection。
- accepted compact `source_boundary_refs` 的strict typed read boundary，以及
  Conversation Memory对covered raw/post-compact delta的唯一projection rule。
- conservative estimator stable identity/version 与 complete candidate adapter。
- runner-call manifest v2 sizing snapshot、accepted iteration link 与 usage
  observation direct pairing。
- Host-only compatible anchor resolver、signed-delta predictor、closed fallback
  reasons。
- proactive、hard block、post-compact、reactive recovery 与 tier 4/5
  dispatch-fallback 的统一 sizing result。
- startup exact replay、running/waiting steer、wait resume与Engine within-Attempt
  continuation的manifest-before-new-Attempt / observed-continuation sizing contract。
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
- 用accepted compact后的conservative hard estimate追加
  `CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`、`RUN_LOST`，或修改
  `run_transition.py`新增context-hard terminal transition。
- 为reactive recovery另建request builder、把candidate塞入wakeup DTO，或在Attempt
  start后重新assembly；actual request必须继续走existing manifest/candidate loader。
- startup recovery从current config/raw EventLog/memory重建source request；steer复制
  source candidate；wait resume在`RUN_STARTED`后才重建continuity；active-run
  continuation复用ordinary soft/hard lifecycle action。
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
| predicted tokens/threshold/pressure/stage-aware action | `dayu.host.context_budget` 的 `ContextSizingResult` | anchored或fallback只产生一个typed result；pressure纯阈值派生，budget decision由5-stage/15-cell total function派生 | context events/read API/Service/UI重算；把post-compact soft、reactive/continuation hard改写成normal；用reactive/continuation hard触发failure |
| reactive accepted recovery candidate/start | `dayu.host.engine_ingest` transaction orchestration + `dayu.host.run_input` candidate/manifest owner | accepted compact后exact memory catch-up；同一start transaction冻结candidate、写manifest、调用unchanged recovery transition；actual request strict load | catch-up失败仍start；Attempt-before-manifest；第二次assembly；accepted后补failed/lost facts |
| active-run continuation stage/action | `dayu.host.context_budget` + 显式producer reason | startup/steer/wait/Engine continuation五阶段total function；三pressure allow且保留真实pressure | 机械复用ordinary soft compact/hard block；从pressure/kind字符串反推stage |
| startup recovery exact request | `dayu.host.run_input` strict prepared source + `dayu.host.recovery` transaction orchestration | source candidate/sizing唯一strict read；new manifest绑定new identity；existing startup LOST owner处理source corruption | current config重选、raw EventLog重建、worker source fallback |
| steer candidate | `dayu.host.admission` acceptance transaction + `dayu.host.run_input` candidate owner | 新`USER_INPUT_ACCEPTED`、new digest、current memory/compact与new input同事务manifest-before-start | 复制old candidate、沿用old input digest、start后补manifest |
| wait resume continuity | `dayu.host.run_input` accepted-result/resume projection owner + `dayu.host.waiting` transaction orchestration | planned strict accepted result在start前形成exact continuity/candidate；committed reader委托同helper | waiting复制result parser；依赖RUN_STARTED后重建；tool result重复 |
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
    tool_execution_mode: ToolExecutionMode
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

`tool_execution_mode`必须进入candidate projection与`input_snapshot_digest`。reactive
recovery不得从当前local config重选policy/tools/mode；它在start transaction内通过
source Attempt/execution的strict manifest读取overflowed prepared candidate，并复用
其中frozen `policy_snapshot/tool_schemas/disable_tools/tool_execution_mode`来重建compact
后的candidate。`run_input.py`提供transaction-local strict loader供existing public
loader与engine ingest共同复用，禁止engine ingest复制manifest/payload parsing。

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
| `sizing_stage` | closed `ordinary/post_compact/reactive_post_compact/dispatch_fallback/continuation` or `null` | yes | runner-call candidate的治理阶段；compactor proposal为null |
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
- ordinary `status=unavailable`仍必须保留closed `sizing_stage`，其它value字段不得被
  anchor resolver部分信任；
- `status=not_applicable` 仅允许 `compactor_proposal`，`sizing_stage`与其它
  value字段全部为null；
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

reactive accepted compact 使用同一manifest contract，但顺序独立冻结为：

```text
CONTEXT_COMPACTED already committed
-> Conversation Memory reaches exact compacted event sequence
-> BEGIN IMMEDIATE
   re-read RECOVERING Run + terminal source Attempt
   -> strict-load source Attempt prepared candidate
   -> reuse frozen policy/tool schemas/tool execution mode
   -> freeze identity-free complete candidate
   -> conservative sizing(stage=REACTIVE_POST_COMPACT)
   -> allocate one StartRecoveryRunInput identity set
   -> write prepared candidate payload
   -> append RUNNER_CALL_INPUT_ASSEMBLED(
        sizing_snapshot.sizing_stage=reactive_post_compact
      )
   -> Slice 2 only: append CONTEXT_BUDGET_EVALUATED
   -> call existing start_recovery_run_with_starting_attempt_in_transaction
   -> RUN_STARTED(start_reason=recovery)
   -> ATTEMPT_STARTED + dispatch row
   -> COMMIT
```

actual recovery request继续由existing
`load_prepared_runner_call_candidate(attempt_id, execution_id)`读取上述manifest和
candidate；不得扩充`PendingDispatchRecord`传递第二份candidate，也不得在worker侧
rebuild。catch-up未达到目标、candidate/manifest失败、start precondition miss或CAS
lost时不得wake；当前start transaction全部新增写入rollback，前一事务已提交的accepted
compact保持不变。

`dayu/host/durable/run_transition.py`中的`StartGovernedRunInput`部分不修改：该现有
typed interface的字段
`run_id/expected_status/run_started_event_id/attempt_started_event_id/attempt_id/
execution_id/dispatch_record_id/occurred_at/actor/source/start_reason/worker_kind/
owner_host_instance_id` 全部由 caller提供，transition已原样消费并创建对应rows。
该文件仍允许并要求删除legacy direct promotion transition及其专属类型/helper，不得
把本段的governed-start语义约束解释为文件级零diff。
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

#### 5.3.1 First-call producer controlling contract（含Controller plan-review fix）

本节以第三次amendment为基础并已落实本轮Controller §5；它是§5.3中start/manifest
producer contract的控制性增量。与本节
冲突的旧“只有governed/recovery两种start input”“continuation等于ordinary stage”或
“startup/steer/wait只做ordering test”描述一律由本节取代。

**Pending producer / strict consumer双向总表**

| path | logical candidate | candidate / frozen execution source | stage / Slice 1 action | transaction owner 与顺序 | replay / CAS / rollback |
| --- | --- | --- | --- | --- | --- |
| initial accepted ordinary | 新candidate | current `USER_INPUT_ACCEPTED` strict effective execution/tool facts + current memory/compact/current input | `ORDINARY`；normal allow、soft proactive、hard unstarted fail | `dispatch.py` scheduler：candidate/sizing；allow时manifest -> governed `RUN_STARTED` -> `ATTEMPT_STARTED` -> pending row | deterministic governance；precondition miss private rollback；low-level CAS error传播 |
| queued promotion | 与queued Run input对应的新candidate | 与initial相同；`_read_startable_run`选择无active时最早queued | `ORDINARY`同上 | 与initial完全相同，仅`start_reason=queue_promotion`；删除admission direct promotion pending旁路 | 同上；promotion wake只唤醒scheduler governance |
| proactive accepted compact | compact后新candidate | frozen input execution + accepted compact/memory exact truth | `POST_COMPACT`；normal/soft allow、hard unstarted fail | `dispatch.py`：catch-up -> candidate/sizing -> manifest -> governed start | existing operation replay；start miss整笔rollback |
| proactive/reactive真实failed tier 4/5 | fallback新candidate | frozen input execution +真实`CONTEXT_COMPACTION_FAILED` + fallback view | `DISPATCH_FALLBACK`；normal/soft allow、hardexisting合法failure owner | `dispatch.py`或`engine_ingest.py`owner-local manifest-before-start | failed outcome identity重放；CAS rollback；不得伪造failed fact |
| reactive accepted compact | compact后新candidate | source strict candidate的policy/tools/mode + exact compacted memory truth | `REACTIVE_POST_COMPACT`；三pressure allow | `engine_ingest.py`：accepted fact已commit -> catch-up -> new candidate/manifest -> recovery start | matching outcome重入；winner duplicate不wake；start transaction rollback |
| startup/orphan recovery | **不变**，exact logical replay | source Run当前`input_event_id`的exact `USER_INPUT_ACCEPTED`先重建typed policy，再strict-load source Attempt/execution candidate + sizing | `CONTINUATION`；三pressure allow；Slice 1只复用sizing atoms并重绑定stage，不要求fact | `recovery.py`：source strict read -> new manifest -> recovery `RUN_STARTED` -> `ATTEMPT_STARTED` -> pending row | source invalid由startup LOST owner收口；valid CAS miss使整page transaction rollback，page不wake |
| running steer | **变化**，加入新用户输入 | 新`USER_INPUT_ACCEPTED` durable effective facts + current memory/compact +新input | `CONTINUATION`；三pressure allow | `admission.py`：append new input -> direct strict parse同一payload -> steer/old Attempt close facts -> candidate/manifest -> steer starts -> pending row | idempotent key只复用同一new input/manifest；任一失败整笔rollback，旧Attempt不被半关闭 |
| waiting steer | **变化**，加入新用户输入 | 与running steer相同；旧wait cancellation仍由waiting state owner | `CONTINUATION`；三pressure allow | `admission.py`：new input -> steer/wait cancellation -> candidate/manifest -> starts -> pending row | 同上；无孤立wait cancellation或manifest |
| wait completed/cancelled resume | **变化**，加入accepted tool result continuity | source Attempt strict candidate的policy/tools/mode + run_input唯一`user -> assistant(tool_call) -> tool(result)`投影 | `CONTINUATION`；三pressure allow | `waiting.py`在调用unchanged transition前：planned continuity -> candidate/manifest；transition再写`RESUME_REQUESTED` -> `TOOL_RESULT_ACCEPTED` -> `RUN_STARTED` -> `ATTEMPT_STARTED` -> pending row | resolution digest/event ids稳定；same key不重复result/manifest/wake；transition miss整笔rollback |
| Engine within-Attempt continuation | **变化**，Engine已加入assistant/tool result等messages | accepted complete `IterationStartedData.input_projection` + same Attempt strict source的policy/tools/mode/request semantics | `CONTINUATION`；三pressure allow；真实call已由Engine发起 | `engine_ingest.py`：existing limited-manifest writer；Slice 1不构造prepared candidate、不调用pre-start recorder；Slice 2为manifest -> budget fact -> link/preview | same iteration deterministic duplicate；source/projection缺失写unavailable barrier，不从current config修补 |

worker consumer对上述所有**新Attempt**只有一个入口：
`dispatch.py::_build_frozen_run_input`按current
`run_id/attempt_id/execution_id` strict-load new manifest/candidate。startup不得从
source Attempt在worker侧fallback，steer/wait不得由worker重新组装，Engine continuation
不是新pending dispatch，因此不经过worker first-call loader。

**第五stage的第一性原理裁决**

`CONTINUATION`必须新增。四类eligible path都已有active-run lifecycle truth：
startup replay必须重发原logical request，steer已关闭/替换旧Attempt，wait resume已接受
工具结果，Engine continuation已经由同一Attempt内部循环发起。若机械使用
`ORDINARY`：

- soft会要求再创建一次proactive operation，但这些path没有“尚未启动Run/input
  snapshot”owner，且会与wait/steer/recovery状态机冲突；
- hard会要求调用`FailUnstartedRunInput`，但Run已经有旧Attempt或正在同Attempt内部
  执行，owner前置条件不成立；改用其它terminal transition又会伪造compact failure、
  user failure或startup lost。

因此pressure仍由同一threshold函数真实计算，action扩为完整5-stage/15-cell total
function：

```text
pressure(predicted):
  predicted >= hard -> hard_threshold_exceeded
  predicted >= soft -> soft_threshold_exceeded
  else              -> normal

action(stage, pressure):
  ORDINARY:              normal=ALLOW  soft=COMPACT  hard=BLOCK
  POST_COMPACT:          normal=ALLOW  soft=ALLOW    hard=BLOCK
  DISPATCH_FALLBACK:     normal=ALLOW  soft=ALLOW    hard=BLOCK
  REACTIVE_POST_COMPACT: normal=ALLOW  soft=ALLOW    hard=ALLOW
  CONTINUATION:          normal=ALLOW  soft=ALLOW    hard=ALLOW
```

production实现必须显式穷举五个stage和三种pressure，不能靠generic/default
fall-through恰好得到表中action；Python 3.11实现用closed `match`或等价显式分支，
穷尽后对不可能值使用`assert_never`/明确异常fail closed。owner tests除15个合法cell
外，还要覆盖unknown stage/value不能静默映射。

`CONTINUATION` eligibility是startup exact replay、running/waiting steer、wait resume、
Engine `iteration_index>0`四类闭集。优先级固定为：真实failed fallback >
reactive accepted compact > proactive accepted compact > explicit continuation producer >
unstarted ordinary。stage由producer显式传入，禁止从pressure、manifest kind、Attempt
是否存在或start reason字符串反推。continuation real provider overflow仍由Engine
`context_compaction_requested`与existing reactive compact/recovery state machine
拥有；continuation sizing不得写`CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`或
`RUN_LOST`，startup source本身损坏例外地由startup recovery existing LOST owner基于
unrecoverable durable facts收口。

**Shared RunInput owner contract 与exact signatures**

manifest recorder移除对
`StartGovernedRunInput | StartRecoveryRunInput`偶然union的依赖，固定为朴素direct
identity参数：

```python
def record_prepared_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    payload_store: PayloadStore,
    *,
    run: RunRow,
    attempt_id: str,
    execution_id: str,
    occurred_at: datetime,
    candidate: PreparedRunnerCallCandidate,
    sizing_snapshot: RunnerCallSizingSnapshot,
) -> EventLogRow:
    ...
```

helper只校验direct identity、写candidate/projection/tool-schema descriptor/manifest；
producer继续唯一拥有start input、dispatch id、event ids与transition调用。内部
`_prepared_runner_call_projection_body`、
`_write_prepared_tool_schema_snapshot_payload`、
`_prepared_runner_call_manifest_body`也改收`attempt_id/execution_id`，不引入新的
start union、callback、factory或service locator。

source candidate/sizing transaction-local strict read只有一个实现：

```python
@dataclass(frozen=True, slots=True)
class PreparedRunnerCallSource:
    manifest_event: EventLogRow
    manifest: RunnerCallInputManifest
    candidate: PreparedRunnerCallCandidate

def load_run_input_policy_snapshot_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
) -> PolicySnapshot:
    ...

def load_prepared_runner_call_source_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> PreparedRunnerCallSource:
    ...
```

`load_run_input_policy_snapshot_in_transaction`先用`run.input_event_id`精确读取
`USER_INPUT_ACCEPTED`，严格校验event的type、Session、Run和identity，再从其
`effective_execution_config`调用共享
`_execution_config_projection.effective_execution_snapshot_from_json`，构造typed
`PolicySnapshot`。它不得读取current opener policy/current config，也不得从candidate
只保存的policy ref/digest反向构造policy。

`load_prepared_runner_call_source_in_transaction`先读取并校验`RunRow`与上述source input
policy，再strict-load manifest/candidate/tool-schema descriptors，并逐项校验candidate
policy ref/digest、manifest sizing policy ref/digest、request-semantics digest与typed
policy一致。startup、wait和Engine frozen-source consumer只调用这个strict超集，不复制
manifest/hot/payload/tool-schema/policy parser；Engine可把closed source failure映射为
limited/unavailable reason，但不得自行raw-parse manifest补齐。

existing worker
`load_prepared_runner_call_candidate_in_transaction(..., policy_snapshot=caller_policy)`
与public loader保留现有caller参数以校验Attempt-frozen dispatch truth，但实现必须先委托
同一strict source helper，再额外比较caller policy的typed equality、
`policy_snapshot_ref`、policy digest与request-semantics digest，最后只返回
`.candidate`。caller/source不一致即Host input integrity fail closed；禁止caller policy
参与source重建。

pre-start candidate core签名固定显式接收本次current input与continuity：

```python
def prepare_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_input_event: EventLogRow,
    continuity: SessionContinuityView,
    policy_snapshot: PolicySnapshot,
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    memory_projection_policy: MemoryProjectionPolicy,
) -> PreparedRunnerCallCandidate:
    ...
```

ordinary/post-compact/reactive传`run.input_event_id`对应event与empty continuity；
steer传刚append的新input event；wait传原input event与下述resume continuity。
`SessionContinuityView`增加必填`source_refs: tuple[str, ...]`，candidate digest/source
refs必须覆盖continuity refs。实现前以
`rg -n "SessionContinuityView\\(" dayu/host tests/host`审计全部construction site；
当前`run_input.py`三个production site及
`test_run_input_builder.py`、`test_tool_trace_queries.py`的construction site都必须更新，
ordinary/empty continuity显式传`source_refs=()`，新增producer显式传exact refs。字段不
增加默认值，不用compat补旧callsite。

wait continuity owner收敛为：

```python
def project_wait_resume_continuity(
    *,
    user_prompt: str,
    accepted_result: AcceptedToolResultProjection,
    source_refs: tuple[str, ...],
) -> SessionContinuityView:
    ...
```

`accepted_result_projection.py`继续是accepted result strict projection owner：为planned
payload暴露一个owner-level入口，接收deterministic event id与
`_tool_result_resolution_payload`已生成的exact payload，和committed
`project_accepted_tool_result(...)`委托同一strict core。RunInput helper只消费typed
`AcceptedToolResultProjection`，严格要求status为completed或cancelled、tool identity与
request arguments/raw outcome完整，再投影唯一
`user -> assistant(tool_call) -> tool(result)`消息；不得loose-parse任意mapping，不得
重新生成resolution fact。

waiting producer先只为completed/cancelled构造一次planned payload，通过共享strict
projection得到typed view，并把
`source_refs=(tool_call_requested_event_id, event_plan.tool_result_event_id)`传给helper。
existing `_resume_wait_messages_from_current_start`读取committed result后也委托相同strict
projection与helper。planned source ref中的`event_plan.tool_result_event_id`必须就是
transition随后提交的canonical row id；两条path必须产生相同messages、source refs与
candidate input digest。failed/lost不调用continuity helper，不写candidate/manifest，也
不创建new Attempt。

**Producer exact ordering**

```text
ordinary / queued allow:
  candidate -> sizing -> manifest -> RUN_STARTED -> ATTEMPT_STARTED -> pending row

startup exact replay:
  strict source candidate+sizing
  -> new manifest(stage=continuation, same candidate/sizing atoms)
  -> RUN_STARTED(recovery) -> ATTEMPT_STARTED -> pending row

running steer:
  USER_INPUT_ACCEPTED(new digest) -> STEER_REQUESTED -> ATTEMPT_STEERED
  -> candidate(new input) -> manifest(continuation)
  -> RUN_STARTED(steer) -> ATTEMPT_STARTED -> pending row

waiting steer:
  USER_INPUT_ACCEPTED(new digest) -> STEER_REQUESTED -> cancel active wait rows
  -> candidate(new input) -> manifest(continuation)
  -> RUN_STARTED(steer) -> ATTEMPT_STARTED -> pending row

wait resume:
  validate wait/request atom + freeze planned accepted-result continuity
  -> candidate -> manifest(continuation)
  -> existing transition appends RESUME_REQUESTED -> TOOL_RESULT_ACCEPTED
  -> RUN_STARTED(resume) -> ATTEMPT_STARTED -> pending row

Engine iteration_index > 0:
  accept complete observed projection
  -> continuation manifest
  -> Slice 2: CONTEXT_BUDGET_EVALUATED(stage=continuation)
  -> RUNNER_CALL_INPUT_ITERATION_LINKED / ITERATION_STARTED preview
```

wait manifest可显式引用deterministic planned tool-result event id；
`event_plan.tool_result_event_id`与transition实际append后返回的committed
`TOOL_RESULT_ACCEPTED.event_id`必须逐字相等。manifest、后续canonical result与start
rows在同一transaction全有或全无；planned path不得声称future event sequence，也不得
把planned payload单独持久化为第二个result truth。owner test必须用同一planned/
committed fixture断言continuity messages、source refs与candidate input digest完全相同。

**Failure matrix**

| failure | owner behavior |
| --- | --- |
| startup source manifest/candidate/sizing/effective policy missing、mismatch、`not_applicable` | 不创建new manifest/Attempt；active orphan按`recoverable=False`进入existing startup `RUN_LOST`，already `RECOVERING`用existing startup recovering-lost transition与structured reason收口 |
| startup source complete/unavailable合法 | exact candidate replay；complete数值复用并stage重绑定continuation，unavailable reason保留；不重估、不读取current config |
| startup transition precondition/CAS miss aftermanifest preparation | 抛owner-local rollback error使当前recovery page transaction整体rollback；该page零wake、零new manifest/rows，先前committed pages不回滚 |
| steer effective execution/tool facts非法或candidate/manifest失败 | 整个admission transaction rollback；新input/steer/旧Attempt close/wait cancellation均不残留 |
| steer run/attempt CAS race | 同上；worker cancel只在commit后传播 |
| wait request atom/result projection非法 | transition前fail closed；wait保持WAITING，零manifest/result/start |
| wait transition precondition/CAS miss | candidate payload/manifest随transaction rollback；wait仍由winner committed truth决定，零重复tool result |
| wait same idempotency key replay | strict比较resolution digest，返回existing result；不重写manifest、不重复wake；不同digest conflict |
| wait failed / lost outcome | 保持existing terminal failure/lost owner；零continuation manifest、零new Attempt、零pending dispatch；不得进入resume projection |
| continuation complete projection但frozen source mismatch | strict unavailable manifest + lineage barrier；不得current-config重建；actual Engine call的真实overflow仍走reactive owner |
| any new Attempt worker strict load mismatch | Host input integrity fail closed；禁止consumer fallback或二次assembly |

**Composition wiring**

`open_host.py`只把已有construction truth
`ordinary_run_baseline/tooling_options/context_budget_policy/
memory_projection_policy/enable_truncation_manager/host_instance_id`逐项传入execution
`HostAdmissionService`、startup recovery scanner与waiting service；`command.py`
不在`HostCommandHandle`复制这些字段，只在构造waiting/recovery producer时从其唯一
`_admission_service`读取并逐项传入。
不新增public option、per-run bag、callback seam或service locator。initial start也必须在
admission时写strict effective execution/tool facts；retry/replay必须复用source facts，
缺失即fail closed，不用opener current baseline补旧数据。tool schemas仍由共享builder按
durable selected names/digests重建并核验，不在admission/recovery/waiting复制schema
JSON。

internal composition target signature固定为给existing dataclass/constructor增加以下
**直接字段**，不新增`ProducerContext/Profile/Dependencies` bag：

```python
@dataclass(frozen=True, slots=True)
class HostAdmissionService:
    transaction_runner: HostTransactionRunner
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore
    payload_store: PayloadStore
    clock: AdmissionClock
    id_factory: AdmissionIdFactory
    wakeup_port: AdmissionWakeupPort
    terminal_post_commit_port: TerminalPostCommitPort
    projection_catchup_port: ProjectionCatchupPort
    ordinary_run_baseline: OrdinaryRunExecutionBaseline | None
    tooling_options: HostToolingOptions | None
    context_budget_policy: ContextBudgetPolicy | None
    memory_projection_policy: MemoryProjectionPolicy
    enable_truncation_manager: bool
    owner_host_instance_id: str | None
```

execution opener必须逐项传non-`None` baseline及真实options；admin-only handle显式传
`None` baseline/policy与`owner_host_instance_id=None`，任何需要创建Attempt的命令在
该scope fail closed。`create_host_admission_service(...)`同步暴露同名keyword-only
参数并由所有callsite显式传入；production execution/wait-poller factory不得依赖
factory默认值。

```python
class DefaultHostResolveWaitService:
    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        terminal_post_commit_port: TerminalPostCommitPort,
        event_log_store: EventLogStore,
        idempotency_store: IdempotencyStore,
        payload_store: PayloadStore,
        memory_projection_policy: MemoryProjectionPolicy,
        projection_catchup_port: ProjectionCatchupPort | None,
    ) -> None:
        ...
```

wait producer的policy/tools/mode和sizing policy identity只从strict source manifest /
candidate取得，不向该constructor传current baseline/tooling/context policy。

```python
@dataclass(frozen=True, slots=True)
class SessionAttachmentRecoveryScanner:
    session_id: str
    transaction_runner: HostTransactionRunner
    event_log_store: EventLogStore
    payload_store: PayloadStore
    terminal_post_commit_port: TerminalPostCommitPort
    process_probe: ProcessLivenessProbe
    dispatch_wakeup_port: AdmissionWakeupPort | None
    recovery_owner_host_instance_id: str | None
    defer_accepted_cancel_to_watchdog: bool
    batch_size: int
```

startup replay也不接收current baseline/tooling/context policy；全部execution/sizing
source来自strict prepared source。`open_host.py::_ExecutionCommandHandleFactory`、
`_WaitPollerFactory`与`_SessionAttachmentRecoveryActorOperation`逐项完成上述装配；
`command.py`三个resolve入口共用一个私有模块级
`_resolve_wait_service(host: HostCommandHandle) -> DefaultHostResolveWaitService`
constructor helper，helper只做direct field wiring，不透传业务调用。

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
    REACTIVE_POST_COMPACT = "reactive_post_compact"
    DISPATCH_FALLBACK = "dispatch_fallback"
    CONTINUATION = "continuation"
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
  POST_COMPACT:
    normal -> ALLOW_DISPATCH
    soft   -> ALLOW_DISPATCH
    hard   -> BLOCK_HARD_THRESHOLD
  DISPATCH_FALLBACK:
    normal -> ALLOW_DISPATCH
    soft   -> ALLOW_DISPATCH
    hard   -> BLOCK_HARD_THRESHOLD
  REACTIVE_POST_COMPACT:
    normal -> ALLOW_DISPATCH
    soft   -> ALLOW_DISPATCH
    hard   -> ALLOW_DISPATCH
  CONTINUATION:
    normal -> ALLOW_DISPATCH
    soft   -> ALLOW_DISPATCH
    hard   -> ALLOW_DISPATCH
```

因此`ContextSizingResult.__post_init__`必须先仅由predicted/thresholds复核
`pressure_level`，再由`stage + pressure_level`复核`budget_decision`。
`_pressure_and_decision`及constructor复核必须显式穷举五个stage，不得让
`POST_COMPACT`、`DISPATCH_FALLBACK`或`CONTINUATION`依赖default `else`；合法枚举之外
的value用`assert_never`或明确异常fail closed。15-cell owner test与unknown反例共同
证明total function，而不是仅凭当前输出巧合正确。
`POST_COMPACT` / `DISPATCH_FALLBACK` soft的pressure不得降为normal；public fact/view
继续报告soft pressure，但Host允许dispatch。`REACTIVE_POST_COMPACT`与
`CONTINUATION`的soft/hard也不得降为normal，三种pressure都必须allow；ratio与
threshold仍由`ContextBudgetPolicy`派生，不因usage或stage变化。

第四stage只允许用于以下完整conjunction：trigger source为reactive、同operation已提交
accepted `CONTEXT_COMPACTED`、Conversation Memory已覆盖该event sequence、Run仍为
`RECOVERING`、source Attempt已terminal、recovery Attempt尚未创建。proactive accepted
compact继续使用`POST_COMPACT`；真实compact failure后的tier 4/5继续使用
`DISPATCH_FALLBACK`。stage不得由pressure、runner-call kind字符串或是否存在Attempt
反推。

第五stage `CONTINUATION`只允许§5.3.1四类active-run producer。startup replay即使
source manifest原stage为ordinary/reactive-post-compact/fallback，也按本次真实
producer reason重绑定为continuation；reactive accepted compact与真实failed fallback
因已有更具体lifecycle truth不得被continuation覆盖。

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
| `sizing_stage` | closed enum | no | ordinary/post-compact/reactive-post-compact/dispatch-fallback/continuation |
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
  -> RUN_STARTED / ATTEMPT_STARTED

reactive accepted post-compact allow:
  new candidate/manifest
  -> CONTEXT_BUDGET_EVALUATED(stage=reactive_post_compact)
  -> RUN_STARTED(start_reason=recovery) / ATTEMPT_STARTED

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

reactive recovery start使用等价但owner-local的private rollback signal：
`_ReactiveRecoveryStartCasMissRollback`只定义在`engine_ingest.py`。start事务先读取
Run=`RECOVERING`、`current_attempt_id=source_attempt_id`且source Attempt terminal，
然后freeze candidate、写payload/manifest（Slice 2再写fact）并调用existing recovery
start transition。transition返回`NOT_FOUND|INVALID_STATE`或`UPDATED`却缺/错
Run/Attempt/dispatch rows时抛该private signal；`run_write`外只把它收敛为“不wake、
保留此前accepted compact结果”；若存在并发winner，以winner committed state为真源，
否则后续reconciliation重试同一accepted outcome。底层CAS lost与digest/integrity
错误继续以`HostDurableError`传播。两类失败都必须在新transaction验证prepared
candidate payload descriptor、manifest、budget fact、`RUN_STARTED`、
`ATTEMPT_STARTED`、Attempt和dispatch row零孤立写入；不得回滚更早已提交的
`CONTEXT_COMPACTED`，不得post-commit猜测winner，也不得补写failed/lost terminal fact。

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
  covered older raw，再freeze exact candidate；reactive accepted compact使用
  `REACTIVE_POST_COMPACT`且即使fallback prediction为hard也allow recovery dispatch。
  该call后出现新的合法paired usage，后续candidate才可anchor。
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
| proactive post-compact hard pressure | 同transaction写未启动Run failure transition；不得普通返回`None`留下accepted Run |
| reactive accepted post-compact normal/soft/hard | 全部允许recovery dispatch；如实保留pressure；不得追加`CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`或`RUN_LOST` |
| dispatch-fallback hard pressure | 沿既有compaction-failed/fallback failure policy写显式Run failure；不得dispatch或静默停留 |
| reactive accepted compact后memory catch-up/candidate/start CAS失败 | 本调用不创建/不wake Attempt；start事务零孤立manifest/fact/rows；保留accepted compact；无winner时保持`RECOVERING`重试，有winner时只信任winner committed state |
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
  -> proactive accepted: rebuild POST_COMPACT exact candidate
  -> normal or soft: dispatch with original pressure preserved
  -> hard: explicit terminal Run failure

reactive accepted compact
  -> memory projection reaches exact CONTEXT_COMPACTED sequence
  -> rebuild REACTIVE_POST_COMPACT exact candidate before recovery start
  -> normal / soft / hard: allow recovery dispatch with original pressure preserved
  -> same transaction: candidate payload -> manifest -> recovery start
  -> actual request loads the same manifest/candidate
  -> real next overflow: start next existing bounded reactive operation when budget remains

real compact failed + tier 4/5 selected
  -> build DISPATCH_FALLBACK exact candidate
  -> normal or soft: dispatch with original pressure preserved
  -> hard: existing fallback/failure policy consumes the real
     CONTEXT_COMPACTION_FAILED and terminally fails the Run

active-run continuation
  -> startup: exact source input policy -> strict replay source candidate/sizing atoms
  -> steer: append and strict-parse the same new USER_INPUT_ACCEPTED payload
  -> wait completed/cancelled: include typed planned accepted-result continuity
     before start; failed/lost stay terminal with no manifest/new Attempt
  -> Engine iteration > 0: include accepted complete observed projection in the
     existing limited manifest path; do not call pre-start candidate recorder
  -> build CONTINUATION sizing atoms
  -> normal / soft / hard: allow existing lifecycle to proceed
  -> real provider overflow: Engine emits context_compaction_requested and existing
     reactive compaction/recovery owner decides the next action
```

Slice 1尚未写也不要求读取`CONTEXT_BUDGET_EVALUATED`，只冻结candidate、canonical
sizing atoms与stage action；terminal behavior必须先完整成立。Slice 2才从matching
source manifest/fact读取startup atoms，以new Attempt与`CONTINUATION`重新派生action并
写新fact，不能复用source fact identity。实现应把post-compact/fallback helper的结果
收敛为closed outcome：
`pending dispatch`或`terminal notice`；不得继续用`PendingDispatchRecord | None`让
hard与CAS/precondition miss共享模糊`None`。proactive `POST_COMPACT` hard在当前write
transaction复用`fail_unstarted_run_in_transaction`；`DISPATCH_FALLBACK` hard必须先
证明真实`CONTEXT_COMPACTION_FAILED`，proactive caller复用unstarted failure owner，
reactive caller复用existing`fail_recovering_run_in_transaction`。transaction commit后
由现有notifier交付。`POST_COMPACT` hard不得为已经accepted的同一operation再追加一条
矛盾`CONTEXT_COMPACTION_FAILED`；Slice 2再在这些transition之前插入同一个sizing
result的canonical budget fact。

reactive accepted branch不得复用上述`POST_COMPACT` hard terminal outcome；它必须
产生`REACTIVE_POST_COMPACT` sizing result并无条件进入allow recovery start。accepted
compact后任何normal/soft/hard estimate都不能调用
`fail_recovering_run_in_transaction`，因为该owner只接受真实
`CONTEXT_COMPACTION_FAILED`。若新的recovery dispatch再次收到provider overflow，
existing `max_reactive_compactions_per_run`计数与状态机决定是否创建下一条reactive
operation；超过上限后才写真实failed fact并可选tier 4/5，fallback hard再由existing
recovering failure transition收口。整个路径不得写`RUN_LOST`。

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
  - complete candidate preparation、exact input policy strict load、source
    projection/digest、actual request复用、manifest v2 producer。
- `dayu/host/accepted_result_projection.py`
  - planned与committed accepted-result共用的strict projection core；只向RunInput
    暴露typed projection，不把raw payload parsing下放。
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
    accepted candidate/manifest-before-recovery-start、Slice 2 fallback fact ordering、
    Slice 1 within-Attempt limited manifest / Slice 2 fact、start transaction rollback与
    Slice 3 anchored sizing consumption。
- `dayu/host/admission.py`
  - initial durable effective execution/tools/mode freeze；running/waiting steer
    new-input candidate/manifest/fact/start transaction；删除direct queue promotion
    method/operation/result types。
- `dayu/host/recovery.py`
  - startup/orphan strict source replay、Slice 1 continuation manifest-before-start、
    Slice 2 new fact-before-start、source-invalid LOST与page transaction rollback/wake
    boundary。
- `dayu/host/waiting.py`
  - completed/cancelled planned accepted-result continuity、Slice 1 continuation
    manifest-before-existing resume transition、Slice 2 new fact；failed/lost保持terminal；
    不拥有parser/digest。
- `dayu/host/command.py`
  - 仅保存/传递steer与wait需要的Host internal typed construction truth。
- `dayu/host/open_host.py`
  - 仅把现有baseline/tooling/policy/memory configuration显式装配给producer services。
- `dayu/host/context_anchor.py`（新增）
  - durable anchor resolver与compatibility/lineage barriers。
- `dayu/host/context_events.py`
  - canonical fact schema/build/parse。
- `dayu/host/lifecycle_events.py`
  - context governance event type闭集。
- `dayu/host/durable/schema.py`
  - manifest v2 constant与全新数据库event-type DDL真源。
- `dayu/host/durable/state.py`
  - 删除仅服务legacy direct queue promotion的row mutation；ordinary scheduler使用
    existing governed start state owner。
- `dayu/host/durable/run_transition.py`
  - 删除`PromoteQueuedRunInput`、`PromotionResult`/`PromotionSkipReason`、
    `promote_queued_run_in_transaction`及其专属validation/event/row helpers；其余
    governed/recovery/wait transitions不改语义。
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

`dayu/host/durable/run_transition.py`原“零diff”承诺由本amendment撤销，只允许上述
legacy direct promotion整条旁路的删除diff。existing `StartGovernedRunInput`继续满足
caller-generated identity contract；reactive recovery继续直接复用existing
`StartRecoveryRunInput` / `start_recovery_run_with_starting_attempt_in_transaction`，
真实failed fallback继续复用existing
`FailRecoveringRunInput` / `fail_recovering_run_in_transaction`。若implementation除
删除promotion专属符号外还必须改变其它typed input或transition写入语义，立即stop并回
Controller。

### 7.2 Service/UI boundary

- `dayu/service/entrypoint_runtime.py`
  - `EntrypointContextUsage`、kind、activity字段与typed mapper。
- `dayu/cli/activity.py`不修改；只运行/补充测试证明旧formatter不回归。

### 7.3 Tests

- `tests/host/test_context_budget.py`
- `tests/host/test_context_anchor.py`（新增）
- `tests/host/test_context_budget_evaluated.py`（新增）
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_command_handle.py`
- `tests/host/public_smoke_support.py`
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_public_host_event.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_tool_trace_projection.py`（仅manifest/schema fixture同步）
- `tests/host/test_tool_trace_queries.py`
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
| `context_budget.py` | `ContextSizingStage`、pressure/action total function、result invariant | closed enum新增`REACTIVE_POST_COMPACT`与`CONTINUATION`；显式穷举15个cell并对unknown fail closed，不允许generic fall-through或下游改写pressure。 |
| `_runner_call_manifest.py` | manifest/hot strict schema owner | 直接切v2；strict sizing snapshot接受五stage；recorder改为朴素direct identity参数；unknown stage fail closed。 |
| `run_input.py` | candidate/parser/digest/continuity、runner-call index、actual request复核、memory/raw-tail dedupe | 先由source Run exact input event重建typed policy，再strict-load source；所有producer调用同一explicit-input preparation；wait pre/post-start只消费typed accepted-result projection；`SessionContinuityView.source_refs`全construction-site显式传参；actual request不二次写manifest；不新增compact coverage filter。 |
| `accepted_result_projection.py` | accepted tool result strict projection | planned deterministic event id/payload与committed event row共用strict core，向RunInput交付typed projection；不复制LLM-facing格式化规则。 |
| `engine_ingest.py` | Engine continuation producer、prepared manifest lookup/link、usage pairing、reactive recovery start | reactive accepted先exact catch-up，再在start transaction freeze candidate并写manifest；within-Attempt iteration使用`CONTINUATION` limited manifest且不调用pre-start recorder。manifest/start同时commit，actual request按exact identity读取。真实failed fallback保持existing failure owner。 |
| `admission.py` | initial durable effective facts、running/waiting steer与legacy direct queue promotion | initial input冻结baseline/tools/mode；steer append event后strict parse同一payload并先freeze continuation manifest；删除direct promotion method/operation/types，queue统一由scheduler ordinary governance拥有。 |
| `recovery.py` | startup/orphan recovery pending producer | 只能strict replay source candidate+sizing并在start前写continuation manifest；source invalid走existing startup LOST/unrecoverable owner；page transaction CAS失败全回滚。 |
| `waiting.py` | wait resolution/result与resume pending producer | 仅completed/cancelled在transition前通过typed strict projection冻结continuity/candidate/manifest；planned/committed result event id相同；failed/lost保持terminal且零manifest/new Attempt。 |
| `command.py` / `open_host.py` | Host internal construction truth与service wiring | 仅显式传递现有typed baseline/tooling/policy/memory配置；不新增public option、bag、callback或parser。 |
| `compaction_operation.py` | compactor producer | proposal路径保持自身call前manifest时序，`sizing_snapshot=not_applicable`。 |
| `proactive_compaction.py` | compactor manifest reader | 现有kind filter继续忽略ordinary manifest；增加ordinary-before-start反例。 |
| `tool_trace.py` / `durable/tool_trace.py` | manifest projection与reconstruction query | 可以先于RUN_STARTED投影同一event；不得要求run-start trace先存在，不改correlation/public readable semantics。 |
| `lifecycle_events.py` / `durable/schema.py` | event closed set/DDL | v2与新budget fact全新起库；不编码相对顺序。 |
| `context_events.py` / `read_api.py` / Service activity callback | canonical stage parser与通用EventLog public sequence | payload stage闭集扩为五值；raw Host progress stream可先看到activity=None的manifest，再看到context usage与RUN_STARTED；projector保留hard pressure但不公开重算action。Service仍丢弃activity=None，只交付typed context usage与run lifecycle。 |
| projection runner / memory / audit / outbox | 按cursor顺序扫描并以class/type filter选择 | generic checkpoint必须跨过新前置event；memory/audit无新业务投影，outbox只消费terminal filter，不把manifest当terminal。 |
| recovery / dispatch / admission / waiting scan | Run/Attempt/dispatch/wait state rows及canonical lifecycle refs | 每个pending producer均manifest-before-start；manifest/start/fact同transaction，crash后只可能全有或全无；recovery不得把manifest当started truth。CAS miss/rollback、idempotent replay与restart tests证明零孤立event。 |
| terminal/lifecycle consumers | `started_event_id/sequence`精确指向RUN_STARTED/ATTEMPT_STARTED；terminal按typed set | 前置event只改变全局sequence间隔，不改变row refs或terminal truth；禁止“前一条event就是start”的位置假设。 |
| `durable/state.py` / `run_transition.py` | ordinary/recovery/wait transitions与legacy direct promotion bypass | 删除promotion专属row mutation、request/result/validation/event/row helpers；保留governed/recovery/wait transition语义，scheduler ordinary governance是queued start唯一owner。 |

直接命中tests为
`test_run_input_builder.py`、`test_engine_ingest_mapping.py`、
`test_dispatch_scheduler.py`、`test_lifecycle_events.py`、
`test_tool_trace_projection.py`、`test_tool_trace_queries.py`；通用ordering/regression
tests补充 `test_watch_session_events.py`、`test_projection_runner.py`、
`test_recovery_scan.py`、`test_run_attempt_transitions.py`、
`test_state_schema.py`、`test_admission_multiprocess.py`与
`test_outbox_projection.py`。direct promotion专属断言、fixture、imports必须删除；
替代断言集中到scheduler ordinary queued governance与wake-only行为。Tool Trace只允许v2 schema/order适配，不允许借机实施
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
5-stage/15-cell action和manifest v2 direct pairing；穷举每个pending producer并在
新Attempt前冻结exact candidate/manifest，由strict worker消费。所有当前
dispatch-relevant sizing仍先保持`conservative_fallback`，不实现canonical
context-budget fact或public view。

**Expected outcome**

- ordinary/queue promotion、proactive post-compact/fallback、reactive recovery、
  startup recovery、running/waiting steer、wait resume与actual Runner request使用
  同一candidate projection/digest；Engine within-Attempt iteration也写同schema的
  `CONTINUATION` manifest。
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
  soft保留soft pressure但允许dispatch；其hard走各自合法failure owner。
  `REACTIVE_POST_COMPACT` normal/soft/hard均保留真实pressure并允许recovery dispatch。
- `CONTINUATION` normal/soft/hard均保留真实pressure并允许已有active-run lifecycle
  前进；真正provider overflow继续由Engine reactive compaction owner处理。
- reactive accepted compact后memory必须exact catch-up；同一start transaction按
  candidate payload -> manifest -> recovery start排序，actual worker用existing strict
  loader读取同一candidate。rollback零孤立manifest/Attempt，accepted compact不被
  contradictory terminal facts污染。
- startup只strict replay source；steer必须包含新input与digest；wait resume必须在
  transition前用既有accepted-result continuity owner冻结，禁止worker或start后首次
  重建；failed/lost wait保持terminal且零manifest/new Attempt。
- Slice 1只冻结candidate与conservative sizing atoms；所有continuation路径均不要求、
  不读取也不追加`CONTEXT_BUDGET_EVALUATED`。

**Allowed production files**

- `dayu/host/context_budget.py`
- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`
- `dayu/host/_runner_call_manifest.py`
- `dayu/host/run_input.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/proactive_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/admission.py`
- `dayu/host/recovery.py`
- `dayu/host/waiting.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`

`dayu/host/durable/state.py`与`run_transition.py`只允许删除legacy direct queue
promotion专属row mutation/transition/types/helpers/tests依赖；governed/recovery/wait
contracts不得改变。

**Allowed tests**

- `tests/host/test_context_budget.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_command_handle.py`
- `tests/host/public_smoke_support.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_state_schema.py`
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
   complete candidate adapter，不改公式常量；pressure纯阈值派生，action必须显式
   穷举5-stage/15-cell，unknown value fail closed，不能依赖default fall-through。新增closed
   `REACTIVE_POST_COMPACT="reactive_post_compact"`与
   `CONTINUATION="continuation"`。
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
8. ordinary soft进入唯一proactive operation；proactive post-compact/fallback soft
   直接进入allow start且pressure保持soft。`POST_COMPACT` hard复用既有unstarted Run
   failure transition；真实`CONTEXT_COMPACTION_FAILED`后的`DISPATCH_FALLBACK` hard
   复用existing fallback/recovering failure owner。不得返回ambiguous `None`或启动
   第二次proactive operation。
9. reactive accepted `CONTEXT_COMPACTED`提交后先要求Conversation Memory exact覆盖
   compacted event sequence；失败时不得继续start。新的recovery start transaction
   重验Run=`RECOVERING`/source Attempt terminal，通过`run_input.py`
   transaction-local strict loader读取source Attempt frozen candidate，复用其
   policy/tool schemas/disable-tools/tool-execution-mode，冻结compact后的complete
   candidate并构造`REACTIVE_POST_COMPACT` sizing；normal/soft/hard全部allow。禁止读取
   当前local config重选。
10. reactive allow后才分配一次`StartRecoveryRunInput` identities，按prepared
    candidate payload -> runner-call manifest -> existing recovery start transition
    排序提交。actual request按新Attempt/execution通过existing strict loader读取同一
    manifest/candidate；不得扩充wakeup DTO或二次assembly。
11. reactive start `NOT_FOUND|INVALID_STATE`或rows不完整抛owner-local private rollback
    signal，caller不wake并保留accepted result供reconciliation；low-level CAS lost与
    digest/integrity错误传播`HostDurableError`。本start transaction两类失败均零孤立
    payload/manifest/Attempt/dispatch；不得写`CONTEXT_COMPACTION_FAILED`、
    `RUN_FAILED`或`RUN_LOST`。
12. reactive Engine candidate duplicate/replay按deterministic operation/event identity
    读取committed outcome：matching accepted compact + Run仍`RECOVERING` + 无recovery
    Attempt时重入exact catch-up/start流程，不再调用compactor或追加accepted fact；
    并发winner已start时只duplicate ack且不重复wake；matching真实failed outcome只恢复
    existing fallback/failure分支。
13. manifest直接切v2；§5.3.1双向表中的全部producer写strict
    `sizing_snapshot`并接受五stage；recorder按direct
    `attempt_id/execution_id`签名，不依赖start input union。continuation只从
    accepted Engine input projection、首个complete manifest的selected-tool descriptor
    与RunInput strict source取得的policy/request semantics重建，crash缺源写closed
    unavailable；Engine continuation继续使用limited-manifest writer，禁止调用
    pre-start candidate recorder。
14. usage ingest通过accepted link读取manifest sizing snapshot，删除
   `_estimate_usage_observation_input`和`display_text` estimate。
15. ordinary allow start precondition miss抛private rollback exception并由`run_write`外caller转为
   无dispatch；低层CAS_LOST沿existing HostDurableError传播；两者都零孤立manifest。
16. 按§7.4适配全部direct manifest/stage consumers并验证public/recovery/projection/Tool
   Trace/terminal ordering；不改变Issue #119 correlation。
17. `supports_stream_usage`不进入usage availability分支；不增加anchor selection、
    signed-delta公式或public activity。
18. initial admission把实际baseline/tools/mode写入
    `USER_INPUT_ACCEPTED.effective_execution_config`与selected-tool facts；retry、
    recovery与resume只strict读取durable source，不用opener/current config fallback。
19. 彻底删除`HostAdmissionService.promote_next_queued_run`、
    `_PromoteNextQueuedRunOperation`、admission/durable promotion result/skip/input
    types、`promote_queued_run_in_transaction`、`promote_queued_run_row`及其专属
    validation/event/row helper与exports；删除
    `test_admission_queue.py`、`test_admission_multiprocess.py`、
    `test_run_attempt_transitions.py`、`test_state_schema.py`中仅证明该旁路的
    cases/imports/fixtures。queued Run只由scheduler `_read_startable_run`按
    `ORDINARY`统一治理；terminal/recovery `wake_queue_promotion`只唤醒scheduler。
20. startup recovery先由RunInput helper从source Run当前`input_event_id`的exact
    `USER_INPUT_ACCEPTED.effective_execution_config`经共享strict parser重建policy，再
    strict-load source candidate+sizing；valid source按
    manifest(continuation) -> existing recovery transition排序；source invalid按existing
    LOST/unrecoverable owner收口，page transaction rollback与wake边界按§5.3.1。
21. running/waiting steer在同一admission transaction先写新
    `USER_INPUT_ACCEPTED`及新digest，直接strict parse刚append的同一payload，再关闭旧
    Attempt/取消wait，随后用新input freeze candidate、continuation sizing与manifest，
    最后写start/pending；任一失败全回滚。
22. wait resume只覆盖completed/cancelled。在existing transition前用deterministic
    event plan、strict request atom与共享accepted-result strict projection调用
    `project_wait_resume_continuity`；candidate/manifest先写，unchanged transition再写
    resolution/result/start，committed event id必须等于planned id。post-start reader
    委托同一projection/helper，不复制parser或格式化规则；failed/lost保持existing
    terminal owner且零manifest/new Attempt。
23. Engine `iteration_index>0`使用首个strict source与accepted input projection构造
    `CONTINUATION` manifest；source/projection不完整写closed unavailable lineage
    barrier，禁止current-config重选。
24. `command.py/open_host.py`只做internal typed逐项装配；不扩public option、
    Service/UI、Engine production或Issue #119。
25. `SessionContinuityView.source_refs`不设默认值；审计并更新全部production/test
    construction site，ordinary显式传`()`，wait传exact request/result refs。

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
- stage matrix精确覆盖15个组合：ordinary normal/soft/hard分别
  allow/compact/block；post-compact与dispatch-fallback normal/soft/hard分别
  allow/allow/block；reactive-post-compact normal/soft/hard均allow。所有soft/hard
  pressure值不改写；continuation normal/soft/hard也均allow，且不创建proactive
  operation或unstarted terminal；实现显式穷举五stage，unknown值fail closed且不能
  落入generic branch；proactive post-compact hard产生未启动Run terminal fact；
  dispatch-fallback hard消费真实failed fact并产生合法Run terminal fact；
  reactive hard创建recovery Attempt且零`CONTEXT_COMPACTION_FAILED`/`RUN_FAILED`/
  `RUN_LOST`。同一snapshot只有一条proactive request。
- reactive accepted owner test冻结顺序：
  `CONTEXT_COMPACTED` commit -> exact memory catch-up -> candidate payload ->
  manifest -> recovery `RUN_STARTED` -> `ATTEMPT_STARTED`；manifest在Attempt start前
  已存在并绑定同一attempt/execution，worker strict loader得到与sizing完全同一
  candidate。
- source Run current input event缺失、type/Session/Run identity错误、
  `effective_execution_config`缺失/strict parse失败，或source Attempt
  manifest/candidate policy ref/digest/request-semantics mismatch、
  `tool_execution_mode`非法时fail closed且不start；合法路径从exact input fact重建typed
  policy并精确复用source frozen policy/tool schema/mode，修改current local config不
  改变candidate。existing worker loader额外拒绝caller policy identity mismatch。
- pending producer双向契约逐项覆盖：每个新Attempt pending row在同事务更早存在matching
  manifest，worker strict loader不含producer-kind fallback；admission direct promotion
  method、durable transition、专属types/helpers/exports均不存在，
  `create_running_run_with_starting_attempt_in_transaction`继续无production caller。
  earliest queued由scheduler ordinary governance pickup并完成candidate/sizing/
  manifest/start；terminal/recovery wake本身零state transition。
- startup strict replay source invalid/not-applicable时零new Attempt并由existing LOST
  owner收口；valid replay复用logical candidate/sizing atoms，只把stage重绑定为
  continuation，不重新解析current config或重新估算。
- running/waiting steer candidate包含本次新`USER_INPUT_ACCEPTED` ref/content，digest与旧
  source不同；失败时新input、旧Attempt close、wait cancellation、manifest/start全部
  回滚。
- wait completed/cancelled分别冻结唯一
  `user -> assistant(tool_call) -> tool(result)`continuity；planned result event id与
  committed canonical id相同，pre-start candidate与committed start后reader产出相同
  messages/source refs/candidate digest；不得依赖`RUN_STARTED`后才首次重建。
  failed/lost分别断言existing terminal status/fact、零manifest、零new Attempt与零pending
  dispatch。
- Engine `iteration_index=0`链接pre-start manifest，`iteration_index>0`写
  `CONTINUATION` limited manifest；complete source经共享strict loader精确复用
  policy/tools/mode/request semantics，任一缺源closed unavailable且不回退current
  config；该path不调用pre-start candidate recorder。
- `SessionContinuityView`全部construction site显式传`source_refs`；ordinary/empty为
  `()`，candidate digest覆盖wait continuity refs，无default/compat分支。
- catch-up failure断言不wake、accepted compact保持、Run仍为`RECOVERING`；
  start precondition miss与low-level CAS lost分别断言本调用不wake、start transaction
  零孤立candidate payload/manifest/Attempt/dispatch、零矛盾terminal facts，并用
  并发winner/no-winner两类fixture冻结committed state owner。
- reactive hard recovery真实再次overflow时，在remaining
  `max_reactive_compactions_per_run`预算内追加下一条reactive request；超过上限才写
  真实`CONTEXT_COMPACTION_FAILED`并进入tier 4/5。fallback hard使用existing
  `fail_recovering_run_in_transaction`，不得lost。
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
  tests/host/test_accepted_result_projection.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_admission_queue.py \
  tests/host/test_admission_multiprocess.py \
  tests/host/test_public_steer.py \
  tests/host/test_public_resolve_wait_resume.py \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_open_host_runtime.py \
  tests/host/test_command_handle.py \
  tests/host/test_durable_schema.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_projection_runner.py \
  tests/host/test_recovery_scan.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_state_schema.py \
  tests/host/test_outbox_projection.py
python -m pyright dayu/ tests/ utils/
```

随后必须运行`pytest tests/host -q`作为Slice 1 full Host gate；focused通过不能替代
full Host。full Host失败必须修复或stop，不得只把失败测试移出allowlist。

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
- 除删除legacy direct promotion专属符号外，必须修改
  `dayu/host/durable/run_transition.py`其它transition或通用transaction runner才能消费
  同一identity/保证rollback；
- production证据表明compact coverage不能由`compact_payload` typed boundary与
  Conversation Memory projection唯一拥有，或必须在RunInput再建第二套filter；
- protected recent raw是否被selected compact覆盖无法从typed canonical refs唯一判断；
- proactive post-compact/真实failed fallback hard无法通过既有Run failure owner显式
  收口，或需要第二次proactive operation；
- reactive accepted recovery无法在Attempt start前完成exact candidate/manifest，
  actual request无法消费同一candidate，或实现需要修改`run_transition.py`；
- reactive accepted hard必须写compact-failed/run-failed/run-lost才能继续，或再次
  overflow无法复用existing bounded reactive loop；
- 任一pending first-call producer无法在start前写matching manifest、worker需要
  fallback/current-config assembly、startup不能strict replay、steer不能使用新input
  digest，或wait continuity只能在`RUN_STARTED`后重建；
- `CONTINUATION`任一eligible path必须机械执行ordinary proactive compact/unstarted
  hard block，或真实overflow无法继续由Engine reactive owner处理；
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
- `dayu/host/admission.py`
- `dayu/host/recovery.py`
- `dayu/host/waiting.py`
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
- `tests/host/test_recovery_scan.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_public_session_attachment.py`
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
3. ordinary、proactive post-compact、reactive accepted post-compact、tier fallback、
   startup exact replay、running/waiting steer、wait completed/cancelled resume与
   Engine within-Attempt
   continuation都先append fact，再写driven transition/link；同transaction。
   `REACTIVE_POST_COMPACT` fact无论normal/soft/hard都记录真实pressure与
   `ALLOW_DISPATCH`，然后启动recovery；`CONTINUATION` fact三种pressure也都记录
   `ALLOW_DISPATCH`。
4. 复用§5.6唯一rollback方案：start precondition miss抛private rollback exception并
   由caller转成无dispatch；low-level CAS lost沿existing durable error传播；两者使
   同transaction内projection/manifest/fact整体rollback，不得留下孤立truth。
5. duplicate watch/reconciliation复用既有fact；同identity矛盾结果fail closed。
6. internal compactor proposal sizing和仅到达的历史usage不写fact。
7. 新增Host public DTO/kind/invariants与strict read projection。
8. 新增Service同形DTO/kind/invariants和exhaustive typed mapper；callback不改。
9. raw `USAGE_REPORTED`保持`activity=None`；CLI production不改。
10. startup从strict source manifest及matching source budget fact复用canonical estimate/
    thresholds atoms，以`CONTINUATION`重新派生pressure/action并为new Attempt追加新fact；
    新fact identity绑定new Attempt/candidate，绝不复用source fact identity。complete
    source fact missing/mismatch属于unrecoverable source，不允许重新估算。unavailable
    source manifest不写budget fact。Slice 1不要求source fact存在。
11. steer/wait在start前从已冻结candidate计算continuation result，ordering为
    manifest -> fact -> lifecycle transition；wait仅completed/cancelled进入该路径，
    transition内部resolution/result顺序保持不变，failed/lost仍零fact/manifest/new
    Attempt。Engine `iteration_index>0`在同一ingest transaction按limited manifest ->
    fact -> link/preview写入。

**Owner-level assertions**

- **policy存在但usage缺失**时conservative fact成立、typed context usage可用且method
  为fallback；policy缺失时不调用sizing、不产生fact/activity，Run保持既有
  allow-without-budget / no-budget governance path。
- ordinary/post-compact/reactive-post-compact/fallback/continuation各有独立identity。
- exact event order先fact后compact/start/attempt。
- CAS precondition miss与low-level CAS lost后，EventLog中零
  `RUNNER_CALL_INPUT_ASSEMBLED`/`CONTEXT_BUDGET_EVALUATED`孤立truth，payload/state
  同样零残留；正常allow只消费一套identity。
- repeated governance只一条fact；矛盾result被拒绝。
- normal/soft/hard、basis points >10000不clamp。
- canonical fact同时保存真实`pressure_level`与stage-aware`budget_decision`：
  post-compact/fallback soft的public pressure仍为soft且fact-before-dispatch；
  其hard fact-before-terminal failure，零silent accepted Run、零第二次proactive
  request；reactive-post-compact hard的public pressure仍为hard但decision为allow，
  fact-before-recovery-start且零failed/lost terminal fact。
- canonical parser、manifest strict parser、Host read projector与Service mapper都接受
  第五stage；public DTO继续只公开既定七字段，不从hard pressure重算block action。
- startup、steer、completed/cancelled wait、Engine continuation均满足manifest -> fact ->
  start/link；startup new fact identity与source fact不同；
  continuation hard公开真实hard pressure与allow decision，零proactive request、零
  unstarted/compact-failed terminal fact。
- failed/lost wait保持Slice 1 terminal owner，零budget fact、零manifest、零new Attempt。
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
  tests/host/test_recovery_scan.py \
  tests/host/test_public_steer.py \
  tests/host/test_public_resolve_wait_resume.py \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_lifecycle_events.py \
  tests/host/test_durable_schema.py \
  tests/host/test_host_activity_event_projection.py \
  tests/host/test_public_host_event.py \
  tests/host/test_public_contracts.py \
  tests/host/test_package_exports.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_projection_runner.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_outbox_projection.py \
  tests/service/test_entrypoint_runtime.py \
  tests/cli/test_activity_renderer.py
python -m pyright dayu/ tests/ utils/
```

随后必须运行`pytest tests/host -q`；再运行上列Service/CLI affected tests。任何Host
回归均阻断Slice 2 completion。

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
- `dayu/host/admission.py`
- `dayu/host/recovery.py`
- `dayu/host/waiting.py`

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
- `tests/host/test_recovery_scan.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_phase7_waiting_integration.py`
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
5. 只有lineage完整的eligible complete
   ordinary/post-compact/reactive-post-compact/fallback/continuation candidate才调用
   anchor resolver；accepted compact immediate candidate（包括
   `REACTIVE_POST_COMPACT`）固定使用完整conservative fallback，不解析旧anchor。
   startup exact replay固定复用source canonical sizing/fact atoms且绝不复用source
   fact identity，不重新resolve anchor；steer、wait
   completed/cancelled resume与complete Engine continuation可在同一transaction对新
   candidate解析compatible anchor，任何gap统一fallback。
6. public fact/view继续只消费result；不新增anchor refs到public DTO。
7. accepted compact immediate candidate强制fallback；新successful ordinary/continuation usage与
   completion后才刷新。`REACTIVE_POST_COMPACT`即使fallback prediction为hard仍由
   stage action allow recovery dispatch；`CONTINUATION` hard同样allow既有lifecycle
   前进，真实provider overflow仍由Engine reactive owner处理。
8. supports flag只作为request semantics snapshot，不作为presence判断。
9. README只同步当前已实现owner/contract/validation入口，不写WU过程。

**Formula/integration assertions**

- positive delta：`U=6200,Ea=6000,Ec=6500 => P=6700`。
- negative delta：`U=6200,Ea=7000,Ec=6000 => P=5200`，不clamp delta。
- `context_window=10000,soft=6500,U=6200,Ea=6000,Ec=6300`在当前dispatch前
  soft compact。
- no usage、invalid、ambiguous、link missing/mismatch均
  `predicted == exact conservative E_current`且Run不因usage失败；fallback继续调用
  Slice 1/2同一complete-candidate conservative estimator，禁止回退到display-text、
  subset或更弱算法，因此绝不劣于当前算法。
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

随后必须运行`pytest tests/host -q`，并在whole-WU closeout运行§9.2全部affected与
项目标准suite。

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
| manifest v2 | exact fields、closed states、pending producer与strict consumer双向全集、v1/unknown/partial拒绝、hot/descriptor/digest graph；continuation四类frozen source与closed unavailable |
| direct pairing | unique accepted link；same iteration；missing/mismatch/ambiguous；无request id/time/display text |
| anchor | 同transaction snapshot；positive/negative delta；tool loop；older anchor through completed missing-usage calls；usage-before-failure/crash-gap/terminal barriers；all compatibility dimensions |
| policy/action | policy present + usage absent产生conservative fact；policy none保持no-budget/no-fact；fixed ratios/thresholds；>= comparison；显式穷举15-cell stage matrix与unknown fail closed；soft/hard pressure与action分离；reactive/continuation hard allow；其它hard由合法owner terminal；over-100 utilization no clamp |
| candidate stages | ordinary/proactive-post-compact/reactive-post-compact/dispatch-fallback/continuation；eligible path与priority反例；internal compactor excluded |
| compact size effect | covered material存在时exact size真实下降；无covered material时不丢current/protected raw、不伪造下降；memory/raw-tail source+digest去重 |
| first-call producer | initial/queued、post-compact/fallback、reactive、startup、running/waiting steer、wait completed/cancelled resume全部manifest-before-start；worker strict load无fallback；source policy来自exact input fact；steer新input/digest；wait planned/committed id与digest相同；failed/lost零manifest/new Attempt；Engine limited path不调用pre-start recorder |
| durability | allow后identity allocation/consumption；ordinary soft/hard零manifest/Attempt identity；所有producer precondition miss/CAS lost整笔rollback；startup strict replay、reactive manifest-before-start/actual request pairing；fact identity/idempotency/conflict/order；startup new fact不复用source identity；direct promotion符号全删、queued只由scheduler ordinary governance启动；replay/recovery determinism |
| Host public | kind/view/invariants；anchored/fallback；normal/soft/hard；policy unavailable；raw usage hidden |
| Service | exact field pass-through；enum exhaustiveness；callback delivery |
| CLI regression | optional context usage不破坏existing formatter；不新增具体display |
| layering | Engine无Host import；Service无durable import；无weak typing/glue |
| ordering consumers | public stream/activity、generic projection checkpoint、recovery scan、Tool Trace query、outbox terminal filter、lifecycle exact refs；reactive accepted零矛盾terminal facts与next-overflow bounded loop |

### 9.2 Required command sequence

每个slice代码修改后：

```bash
source .venv/bin/activate
pytest <该 slice focused tests> -q
pytest tests/host -q
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
rg -n "ContextSizingStage|REACTIVE_POST_COMPACT|reactive_post_compact" \
  dayu/host tests/host dayu/host/README.md tests/README.md
rg -n "CONTINUATION|continuation" \
  dayu/host tests/host dayu/host/README.md tests/README.md
rg -l "RUNNER_CALL_INPUT_ASSEMBLED|RUNNER_CALL_INPUT_ITERATION_LINKED" \
  dayu tests | sort
rg -n "insert_dispatch_record|DispatchRecordStatus\\.PENDING|create_.*starting_attempt" \
  dayu/host tests/host
if rg -n "promote_next_queued_run|promote_queued_run_in_transaction|promote_queued_run_row|PromoteQueuedRunInput|PromotionSkipReason" \
  dayu/host tests/host; then
  exit 1
fi
rg -n "SessionContinuityView\\(" dayu/host tests/host
git diff --check
```

预期为：display-text estimator零命中；source-boundary grep只显示
`compact_payload` raw owner、`memory` typed consumer与`run_input`既有current-input /
raw-tail dedupe，若出现RunInput读取raw `source_boundary_refs`立即失败；manifest v1
零命中；changed owner新增weak-typing零命中；Engine→Host反向依赖零命中；Service
durable依赖零命中。context contract grep与manifest consumer grep必须命中§7.4完整
producer/consumer/tests/docs并由implementation artifact逐项对账；
stage audit必须证明enum、manifest strict schema、canonical payload parser、Host
projector、Service mapper与显式穷举的15-cell tests全覆盖五个stage，unknown fail
closed，且reactive/continuation accepted hard路径没有
compact-failed/run-failed/run-lost写入；promotion grep必须零命中，
`SessionContinuityView` construction-site audit逐项确认显式`source_refs`；最后
`diff --check`通过。

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
| post-compact/fallback soft若继续沿ordinary action会重复compact或静默不dispatch | fixed in Slice 1；ContextSizingResult/dispatch owner | 15-cell stage matrix；soft允许dispatch并保留pressure；同snapshot operation count=1 |
| proactive post-compact/fallback hard普通返回`None`会留下accepted Run | fixed in Slice 1；Host lifecycle owner | closed dispatch/terminal outcome；分别复用unstarted或真实compact-failed owner |
| reactive accepted hard若沿POST_COMPACT block会伪造failure或不启动recovery | fixed in Slice 1；ContextSizingResult/engine ingest owner | fourth stage三pressure均allow；零矛盾terminal facts；真实next overflow进入bounded loop |
| reactive recovery Attempt在manifest前创建会使worker strict loader fail closed | fixed in Slice 1；engine ingest/run input owner | exact catch-up；candidate/manifest-before-start；actual request digest pairing；CAS整笔rollback |
| startup/steer/wait pending producer绕过manifest使strict worker fail closed | fixed in third amendment；各producer transaction + RunInput owner | startup strict replay；steer新input/digest；wait pre-start continuity；全部manifest-before-start且worker零fallback |
| active-run continuation机械复用ordinary会产生无owner的proactive compact或非法unstarted block | fixed in third amendment；Context Governance owner | closed `CONTINUATION`与15-cell total function；三pressure allow，真实overflow仍归Engine reactive owner |
| recorder依赖两类start input union导致新增producer被迫伪装transition类型 | fixed in third amendment；manifest recorder owner | 朴素direct attempt/execution identity签名；start input仍由各transaction producer拥有 |
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
| CTRL-PR-001（历史） | fixed / superseded only for promotion deletion | `StartGovernedRunInput`与其它transition语义仍不改；本轮Controller要求删除legacy direct promotion，因此撤销`run_transition.py`文件级零diff承诺，仅允许promotion专属删除diff。 |
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
| Slice 1 accepted blocker：pressure/action非stage-aware | fixed in first amendment | §1.3、§4、§5.5、§6.4-§6.5、§8.2-§8.3、§9：stage-aware action foundation继续保留。 |
| Slice 1 scope / verification reopening | fixed in amendment | §0、§7、§8.2、§11-§12：新增compact payload、memory与owner tests；partial implementation保持not accepted，双路re-review前不恢复。 |
| Slice 1 second accepted blocker：proactive/reactive accepted post-compact错误合并 | fixed in second amendment | §1.3、§2、§5.3、§5.5、§6.3-§6.5、§7.4、§8.2-§8.4、§9：第二次amendment引入closed `REACTIVE_POST_COMPACT`；第三次amendment将其与`CONTINUATION`共同纳入15-cell action，reactive hard仍allow且保留pressure。 |
| Slice 1 second accepted blocker：recovery start早于candidate/manifest | fixed in second amendment | §2、§5.3、§5.6、§6.5、§7.4、§8.2、§9：exact catch-up、candidate/manifest-before-start、actual request同源、CAS rollback与零矛盾terminal facts。 |
| Slice 1 third accepted blocker：first-call producer未双向闭包 | fixed in third amendment | §2、§5.3.1、§7.4、§8.2-§8.4、§9：穷举pending producer与strict consumer；startup/steer/wait/Engine continuation均有exact source、ordering、rollback与owner tests。 |
| Slice 1 third accepted blocker：active-run continuation stage缺失 | fixed in third amendment | §5.3.1、§5.5、§6.4-§6.5、§8.2-§9：新增closed `CONTINUATION`，形成5-stage/15-cell total function并保持真实overflow owner。 |
| Slice 1 third accepted blocker：candidate recorder union偶然耦合 | fixed in third amendment | §5.3.1、§8.2：recorder改direct identities；RunInput继续唯一拥有parser/digest/continuity，各producer只编排transaction。 |
| CTRL-PR-01 failed wait resume eligibility | fixed in fourth plan fix | §5.3.1、§6.5、§8.2-§9：resume闭集仅completed/cancelled；failed/lost保持existing terminal owner并断言零manifest/new Attempt/pending。 |
| CTRL-PR-02 source policy strict-load循环 | fixed in fourth plan fix | §5.3.1、§7.4、§8.2：source Run exact input event经共享parser先重建typed policy；startup/wait/Engine共用strict source loader；worker委托后额外校验caller policy identity。 |
| CTRL-PR-03 direct queue promotion bypass | fixed in fourth plan fix | §2、§7.1、§7.4、§8.2、§9.4：删除admission/durable整条旁路、专属state mutation/types/helpers/tests；scheduler ordinary governance唯一启动owner，wake只唤醒；允许`run_transition.py`删除diff。 |
| CTRL-PR-04 Slice sizing/fact/anchor混淆 | fixed in fourth plan fix | §5.3.1、§6.5、§8.1-§8.4：Slice 1只candidate/sizing atoms；Slice 2追加new fact且startup不复用source fact identity；Slice 3才对eligible complete candidate启用anchor并保留conservative fallback。 |
| MiMo-03 / MiMo-04 clarification | fixed in fourth plan fix | steer append后strict parse同一payload；wait planned/committed event id逐字相等且projection/candidate digest同源。 |
| DS-PR-001 / 002 / 004 / 006 / 008 | fixed in fourth plan fix | 5-stage显式穷举；`source_refs`全construction-site审计且无默认；test lists去重；wait只消费typed accepted-result projection；source helper成为旧loader严格超集。 |

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
    closed stage为ordinary/post-compact/reactive-post-compact/dispatch-fallback/
    continuation，15-cell显式穷举且unknown fail closed；
    post-compact/fallback soft允许dispatch且不改写pressure，其hard由合法failure owner
    收口；reactive-post-compact三种pressure都allow recovery且不改写pressure，同snapshot
    不启动第二次proactive operation；continuation三种pressure也allow，provider真实
    overflow仍由Engine reactive owner处理；
  - Engine ingest在reactive accepted compact后先exact catch-up，再在recovery start
    transaction冻结candidate、写manifest并调用unchanged recovery transition；actual
    request读取同一candidate，rollback零孤立写入，accepted branch零failed/lost事实；
  - startup从source Run exact input fact重建typed policy后strict replay；running/waiting
    steer append后strict parse同一新input payload；wait只让completed/cancelled复用typed
    accepted-result continuity owner并在start前freeze，failed/lost保持terminal；worker先
    委托shared source loader再校验caller policy；
  - Engine continuation使用existing limited-manifest writer，不构造prepared candidate、
    不调用pre-start recorder；
  - queued Run只由scheduler ordinary governance启动；admission/durable direct promotion
    path与专属tests彻底删除，terminal/recovery wake只唤醒；
  - manifest recorder接收direct attempt/execution identity，不再依赖start-input union；
    `run_transition.py`只允许promotion专属删除diff；
  - Slice 1只冻结candidate/sizing atoms，Slice 2追加new fact且不复用source identity，
    Slice 3才对eligible complete candidate使用anchor；usage缺失继续同一conservative
    estimator；
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
