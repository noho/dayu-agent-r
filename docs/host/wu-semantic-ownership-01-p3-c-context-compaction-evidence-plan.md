# WU-SEMANTIC-OWNERSHIP-01 P3-C Context Compaction / Evidence Plan

## 1. Gate、目标与成功信号

Work unit：`WU-SEMANTIC-OWNERSHIP-01 P3-C - Context compaction payload, evidence text, and LLM-safe projection contract`。

当前 gate：final plan micro-fix。本 artifact 保持首轮 `P3-C-PF-01` 至 `P3-C-PF-06`、
三个相关 residual observations、`P3-C-RR-PF-01` 至 `P3-C-RR-PF-05` 与 controller
coverage follow-up 的既有 closure，并吸收
`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-controller-adjudication.md`
裁决的 `P3-C-RR2-PF-01`，只把原 plan 修到
code-generation-ready；不修改生产代码、测试、control doc、design 真源、README 或
既有 reviewer artifacts，不运行 final plan re-review，不 commit、不 push、不创建 PR，也不
进入 implementation。

目标分为两个独立但同属 P3-C 的 owner closure：

1. accepted `CONTEXT_COMPACTED` payload 由一个严格 typed read contract 解析为 `ConversationCompactOutputVNext`；session summary、evidence-backed facts、answer anchors、forward intents、reference continuity items 只由该 contract 解释。Conversation Memory、下一次 compact 的 previous view、ordinary RunInput 只能消费它或由它物化的 typed projection，不能各自读取 JSON 字段、编码成字符串再反解析，或从 raw compact artifact 重建业务语义。
2. accepted tool result 的 LLM-facing tool/query/source/result material 与 unavailable 文案由 accepted-result projection owner 统一产生并统一渲染。Conversation Memory、compact material、ordinary/fallback RunInput 消费同一个 typed LLM material；envelope producer mismatch 使用 typed exception，不比较 `str(exc)`。

辅助收口：

- post-compact budget 估算确认是纯函数后归 `dayu.host.context_budget`；`compaction_operation` 只编排 proposal、quality gate、budget gate 与 retry。
- accepted compact read boundary 对 `ForwardIntentTypeVNext`、`ForwardIntentStatusVNext`、`ReferenceContinuityReasonVNext` 严格构造；非法值拒绝，不写 `unknown`、不跳过单项、不兼容旧 shape。
- 错误输入 fail closed；测试从私有 renderer / 手写弱 shape 迁到 owner contract 与真实 producer path。

成功信号：

- 生产代码中只有 compact payload owner 读取 persisted `accepted_candidate` 的五类业务字段；`memory.py`、`compact_material.py`、`run_input.py` 不再定义重叠 candidate 字段常量或 mapping parser。
- accepted candidate 在 producer、EventLog payload validator、memory projection、previous compacted view 和 ordinary RunInput 间保持 typed enum、完整 anchor children、完整 fact/intention/reference 文本；不再把 typed intent/reference 编码成私有字符串后反解析。
- ordinary RunInput 中 accepted compact 语义只来自 Conversation Memory projection；compact artifact provider 只提供 provenance/ref 与 represented evidence，不再生成第二份 `Accepted compacted conversation view` LLM message。
- `CompactArtifactView` 与 protected-raw-tail 使用的窄 structural protocol 都不再暴露
  `messages`；`build_run_input_material_blocks()` 不再把 compact artifact 投影成 material
  block，但 compact event/artifact/evidence provenance 仍供一致性校验、raw-tail selection、
  evidence 去重与 manifest/audit 使用。
- compact input 的 `previous_compacted_view` 与普通 RunInput 的五类 memory section 都从同一个 typed accepted candidate 派生；fallback/degrade 只 whole-item/whole-section keep-drop，不改写 item。
- memory、compact pipeline、run input 对同一 accepted evidence 产生逐字相同的四字段业务可读文本；无 `tool_call_id`、EventLog id、payload/artifact ref、digest、cursor、Host/Engine 治理术语。
- producer event ref mismatch 只能通过 typed exception 分支识别；生产代码不存在 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`。
- post-compact budget helper 可在不运行 operation loop 的情况下独立测试，且只统计后续真正投影给 LLM 的 candidate 业务文本、current input 与固定 message overhead；candidate diagnostics、labels、refs、digests 不计入。
- `llm_compaction.py` 中三个无消费点的 `_POST_COMPACT_*` 历史常量被原地删除；它们不再
  被描述为 proposal-budget owner，也不移动、re-export 或保留为第二 owner。
- 受影响测试、逐文件 coverage >= 80%、pyright、README decision、source scans 与 propagation audit 通过。

## 2. 设计真源与总控对齐

本 plan 对齐：

- `docs/host/design.md` 第 23-25 节：RunInputBuilder 是 memory/EventLog/Service 输入进入 Engine 的唯一运行态入口；ordinary input 只能有一条 system envelope；accepted evidence 必须业务可读且不泄漏内部 refs；compact input、ordinary input、fallback input 共享同一 material selection/rendering 语义；`ConversationCompactOutputVNext` 的枚举、字段与 source-label 规则是严格 contract；Conversation Memory 只物化 accepted compact；Context Governance 只编排 typed compactor、budget estimator 和 RunInputBuilder。
- `docs/engine/design.md` 第 1、4、14、15 节：Engine 只消费完整 `AgentRunRequest.messages` 并执行单次 run；不拥有 Host compact、budget、memory、持久化或 LLM-facing Host projection。
- `docs/host/issues-implementation-control.md`：P3-B 已完成，当前 next gate 是 P3-C plan；任何 review finding 都要基于当前代码重新裁决。
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`：P3-C owner 是 accepted compact payload 与 accepted tool evidence projection，memory/compact/run input 消费同一 contract。

当前 design 真源已经明确目标 schema、枚举、LLM-facing 禁止项、fallback/degrade 与 owner boundary，不需要先修改 design 文档。实现不得通过改 design 来为现有弱解析、重复 renderer 或旧 fixture 正名。

## 3. 当前代码直接证据与 first-principles judgment

### 3.1 动机成立，但 review 证据已被近期提交部分修复

P1-A accepted commit `2a841134` 已新增 `dayu.host.accepted_result_projection.AcceptedToolResultProjection`，统一读取 accepted envelope、request atom、raw outcome、query/status/source/result，并迁移 Tool Trace、Durable Memory、CompactMaterial 与 RunInput 的多数事实读取。P2-D accepted commit `abd44b67` 又收紧了 query/source 投影与 tests。因此旧 review 中“memory 与 compact material 都独立回读 request atom / source refs”的部分已经过期。

仍然存在的真实 drift 是最终 LLM text owner 没有收敛：

- `memory._accepted_evidence_readable_text` 输出中文 `工具/查询/来源/结果`。
- `compact_pipeline._accepted_tool_evidence_content` 输出 `Accepted tool evidence` + `tool_name/query/source/result`，query fallback 来自 projection owner。
- `run_input._accepted_tool_evidence_content` 又输出一份相同英文 shape，但仍有自己的英文 unavailable query 文案。

三者消费的 query/source/result 已大体同源，但最后一公里 renderer 和 fallback 仍是三个事实 owner。P3-C 不重做 P1-A 的 envelope/request/status projection，而是在其 typed projection 上补齐唯一 LLM material + renderer。

### 3.2 compact payload 已有局部 helper，但不是五类语义 read contract

`dayu/host/compact_payload.py` 当前只集中读取 `accepted_evidence_mapping_refs`、fact evidence labels，并构造 compact artifact JSON/ref/metadata。它没有把 persisted `accepted_candidate` 解析回 `ConversationCompactOutputVNext`。

当前五类语义仍有三条独立 read path：

- `memory.py` 定义一整套 `_PAYLOAD_FIELD_*`，`_accepted_candidate_mapping()` 后由五个 helper 分别解析 summary/fact/anchor/intent/reference；`ForwardIntent.intent_type/status` 与 `ReferenceContinuityItem.reason` 仍是裸 `str`。
- `compact_material.py` 再定义同一组字段，把 accepted candidate 转成 `RunInputMaterialBlock.text`；intent/reference 随后由 `_parse_previous_forward_intent_text()` / `_parse_previous_reference_continuity_text()` 从私有字符串反解析，answer anchor previous view 还只保留 title 并合成一个同名 child，丢失原 `anchor_items`。
- `run_input.py` 第三次定义 candidate 字段并由 `_vnext_compact_candidate_semantic_lines()` 直接把 raw payload 渲染成 LLM 文本；该 renderer 会输出 evidence/source labels，并可绕过 producer 已有 enum contract。

`context_events.validate_context_compacted_payload()` 只验证 candidate 顶层 schema、digest 和 list/object 基础形状；它没有严格构造 nested typed candidate。真实 producer 使用 `ConversationCompactOutputVNext.to_json()`，所以正常写路径安全；但 persisted read、损坏 payload、直接 fixture 与 recomputed digest 路径仍可把非法 enum/弱 shape 送入下游。这是 read-boundary ownership drift，不是 LLM proposal parser 缺陷。

### 3.3 enum finding 范围需要纠正

`llm_compaction.parse_conversation_compact_output_vnext()` 已在 LLM proposal ingress 严格构造 `ForwardIntentTypeVNext`、`ForwardIntentStatusVNext`、`ReferenceContinuityReasonVNext`，非法值会产生带字段路径的 proposal error。因此 AgentDS 16 不能表述为“LLM 非法 enum 会直接被 accepted”。

仍成立的缺口是 accepted persisted payload read side：memory 接受裸字符串，run input 直接显示裸字符串，compact material 先接受再在更下游字符串 parser 中转换。正确修复是 persisted accepted projection boundary 一次严格转换，所有消费者只收 enum；不增加 `UNKNOWN`，不在每个消费者各自 try/except。

### 3.4 ordinary RunInput 当前有两个 accepted compact renderer

production dispatch 同时装配 `DurableMemorySnapshotProvider` 和 `DurableCompactArtifactProvider`。前者把 accepted compact 物化成五类 memory sections；后者又通过 `_compact_artifact_message_content()` 从同一 `CONTEXT_COMPACTED` raw payload 生成 `Accepted compacted conversation view` system message。`RunInputBuilder.build()` 在无 fallback 时拼接 `memory.messages + compact.messages + protected raw tail + continuity`。

这两条 renderer 不是同根，且同时进入 ordinary input。设计真源要求 ordinary accepted compact 语义来自 Conversation Memory snapshot；compact artifact/ref 是 provenance/input reconstruction，不是第二份 LLM material。P3-C 应删除 direct compact artifact LLM renderer，而不是只让两份 renderer 调同一个 parser 后继续重复展示。

### 3.5 compact_pipeline 与 run_input 的 evidence renderer 不是同根

两者都有同名私有 `_accepted_tool_evidence_content()`，接受相同 `RunInputMaterialBlock`，分别服务 ordinary protected raw tail 与 fallback material。它们格式接近但 fallback 不同；Conversation Memory 还有第三种格式。正确边界是：accepted-result projection 产生一个窄 typed LLM material，唯一 renderer 接收该类型；compact pipeline 与 run input 只决定 section/role，不决定字段名称、fallback 或字段顺序。

### 3.6 budget estimator 确认为 pure，但 candidate traversal 不应塞入 context_budget

`compaction_operation._budget_after_compact_candidate()` 只遍历 typed candidate 与 current input，调用 `estimate_budget_text_tokens()` 并加固定 message overhead；不读 transaction、EventLog、provider、policy registry、operation state，也不产生副作用。它是 pure estimator，应归 `context_budget`。

但 `compaction.py` 已依赖 `context_budget.BudgetEstimate`；让 `context_budget` import `ConversationCompactOutputVNext` 会形成反向依赖。正确拆分是：compact payload/candidate owner 提供后续 LLM projection 的业务文本 tuple；`context_budget.estimate_post_compact_budget(...)` 只接受直接文本参数并估算；operation 组合两者并裁决。不得用 callback/factory/profile 规避依赖。

当前 estimator 还统计 candidate diagnostics 的 code/text，而 diagnostics 不进入五类 semantic memory 或 ordinary RunInput。这会让非 LLM-facing internal diagnostic 改变 budget gate；迁移时必须排除。

### 3.7 Plan re-review 的新增直接代码证据

- `compact_pipeline.py` 的 `CompactPipelineCompactArtifactView` 当前声明 `messages`、
  `compact_artifact_ref`、`compact_artifact_digest`、`represented_evidence_refs`；但
  protected-raw-tail path 通过该 protocol 实际只读取 artifact ref/digest。若只从 concrete
  `CompactArtifactView` 删除 `messages`，它将不再满足该 protocol，pyright 会暴露
  structural subtype 断裂。
- `run_input.py:2519` 的 `build_run_input_material_blocks()` 仍遍历
  `compact.messages` 并生成 `SESSION_SUMMARY` material block；这与 ordinary accepted compact
  只从 memory projection 进入 LLM material 的 owner boundary 冲突，不能只删除
  `RunInputBuilder.build()` 的 `*compact.messages`。
- `CompactEvidenceBlock` 的 component 字段名是
  `readable_tool_name/readable_query_text/raw_result_text/readable_source_text`，而 typed
  material 使用 `tool_name/query_text/result_text/source_text`；
  `EvidenceReadableItemVNext` 又使用 `response_text`。若 plan 不固定 no-rename value mapping，
  implementation 可能错误重命名 contract 或把四字段 renderer 全文写进结果分量。
- `_previous_compacted_view_vnext()` 与五个 `_previous_compacted_*_vnext()` helper 当前均存在；
  原 source scan 没有覆盖该函数族，删除主调用但遗漏 dead string-round-trip helper 时不会
  fail acceptance。
- 对 `llm_compaction.py` 的精确 `rg` 证明
  `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、`_POST_COMPACT_BASE_MESSAGE_COUNT`、
  `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 都只有定义、没有消费点。把其中任一项描述为
  当前 proposal-budget owner 都是 false owner attribution。

## 4. Source finding dispositions

| Finding | 裁决 | 当前代码理由 | P3-C 动作 |
|---|---|---|---|
| AgentDS 6 | accepted，current-code scope corrected | P1-A 已统一事实读取，但 memory/compact pipeline/run input 仍有三套 LLM renderer | 建唯一 typed LLM evidence material + renderer，迁移三条路径 |
| AgentDS 14 | accepted | `_budget_after_compact_candidate` 无副作用，operation 仍拥有纯估算与 candidate traversal | candidate owner 提供业务文本；context_budget 估算；operation 只编排 |
| AgentDS 16 | accepted，current-code scope corrected | LLM proposal ingress 已严格；persisted accepted read side仍为 raw string/下游转换 | accepted payload parser 严格构造 enum；snapshot codec 保存/恢复 enum value |
| AgentDS 22 | rejected-with-reason | `_USER_INPUT_TEXT_UNAVAILABLE` 只用于 `USER_INPUT_ACCEPTED` 文本缺失；它与 accepted evidence query unavailable 是不同业务事实 | 不删除、不合并；renderer 只拥有 accepted evidence unavailable 文案 |
| AgentMiMo DS-1 | accepted | `compact_payload.py` 尚未拥有五类 candidate parser；memory/compact material/run input仍重复 | 新增唯一 typed persisted payload read contract并迁移消费者 |
| AgentMiMo DS-5 | accepted，partially fixed by P1-A | typed query/source/result 已同源，但 final text assembly 仍重复 | 同 AgentDS 6 |
| AgentMiMo DS-6 | accepted，scope expanded to all current matches | accepted_result_projection、compact_material、run_input 都比较 mismatch 字符串；durable memory还重复打开 envelope | typed mismatch exception；下游只消费 projection，不再二次 parse envelope |
| AgentMiMo DS-7 | accepted only for P3-C typed evidence boundary | accepted_result_projection 的 lenient `_optional_text` 会把错误类型降为缺失；outbox/tool_trace/admission 等其它 accessor 有各自 owner | accepted-result 字段改用 strict shared payload accessor；不横扫其它模块 |
| AgentMiMo DS-8 | rejected-with-reason for P3-C | accepted-result `result_details_text` 与 Tool Trace hot/cold bounded display 是不同 projection 层；重复 suffix 不构成同一业务事实，且 Tool Trace 再次施加自己的 caps | 不改 `tool_trace.py`，不创建全局 truncation helper；只用回归测试证明 trace 语义未漂移 |

汇总：accepted 7（其中 4 个 current-scope corrected/narrowed），rejected 2，deferred 0，needs-more-evidence 0。blocking questions：0。

### 4.1 Plan-review fix closure

- `P3-C-PF-01`：6.3 固定 blocks/readable-view exact invariant、pack validation、单一
  tier2/tier3 pair-transform helper 与 durable `HostDurableError` owner。
- `P3-C-PF-02`：6.4 固定 event-id exact equality、五格 `None`/equal/mismatch
  matrix、`MemoryProjectionRepairRequired`，并点名 provider message 生成与 builder
  `*compact.messages` 删除路径。
- `P3-C-PF-03`：6.6 固定 `RunInputMaterialBlock` 完整 typed evidence contract、
  evidence/non-evidence invariant、shared-renderer text equality 与同 slice 原子迁移。
- `P3-C-PF-04`：6.5 将固定 count `2` 推导为 one-system envelope + current-input
  user message，保留 owner constant、禁止 caller override，并增加 drift test。
- `P3-C-PF-05`：7.1、S2 与 9 节列出 no-compact/equal/三种 mismatch 命名测试，
  同时纳入 focused 与 aggregate validation。
- `P3-C-PF-06`：S3 点名删除 `compact_material.py` 的 envelope 二次解析和
  `str(exc)` catch，只消费 `AcceptedToolResultProjection.llm_material`。
- residual observations：S2 明确删除失去消费者的 `_snapshot_*` string-wire helpers、
  `compact_material.py` / `run_input.py` 的重复 candidate 常量/parser；6.5 区分
  `compaction_operation` ordinary post-compact count 与 `llm_compaction` 中无消费点的历史
  常量，不因同名同值虚构第二 owner。

### 4.2 Plan re-review second-fix closure

- `P3-C-RR-PF-01`：6.4 与 S2 同步删除
  `CompactPipelineCompactArtifactView.messages`，并把 protocol 收窄为 protected-raw-tail
  selection 实际消费的 artifact ref/digest；concrete `CompactArtifactView` 保持其 structural
  subtype，额外 provenance 字段继续由其它直接消费者使用。
- `P3-C-RR-PF-02`：6.4 与 S2 显式删除
  `build_run_input_material_blocks()` 中整个 `compact.messages` loop、局部 compact source ref
  和失去用途的函数参数/call-site 传参；provenance 仍走 typed compact view 的校验、raw-tail、
  evidence 去重和 manifest/audit 路径，不生成 LLM material block。
- `P3-C-RR-PF-03`：6.6 固定 typed material 到 `CompactEvidenceBlock` /
  `EvidenceReadableItemVNext` 的 exact no-rename value mapping；`block.text` 继续等于唯一四字段
  renderer 输出，永不作为 component field 的解析来源。
- `P3-C-RR-PF-04`：9 节新增 `_previous_compacted_*_vnext`（含主
  `_previous_compacted_view_vnext`）零匹配 scan，作为 S2 hard acceptance criterion。
- `P3-C-RR-PF-05`：6.5 与 S2 纠正 false owner attribution，将 `llm_compaction.py` 加入 S2
  allowed files，仅原地删除三个无消费点的 `_POST_COMPACT_*` 常量；不移动、不 re-export、
  不保留第二 owner，并以零匹配 scan 验证。

### 4.3 Final plan micro-fix closure

- `P3-C-RR2-PF-01`：6.4 与 S2 明确 `_compact_material_source_ref()` 只有
  `build_run_input_material_blocks()` 的 `compact.messages` loop 一个调用者，必须随该 loop
  在同一变更中删除；9 节增加该符号在 `run_input.py` 的零匹配 hard acceptance scan。
  `_run_input_message_content()` 仍被 memory、continuity 与 material-kind 路径调用，必须保留，
  本 fix 不扩成无关 helper cleanup。

## 5. 语义 owner boundary

| 语义事实 | 首次产生 | 校验 owner | 持久化真源 | typed projection owner | 消费者 |
|---|---|---|---|---|---|
| compact candidate 五类业务语义 | LLM compactor proposal，经 Host accept barrier 形成 `ConversationCompactOutputVNext` | proposal ingress 校验 source labels/quality；persisted read 由 `compact_payload` 严格重建 typed candidate并校验 digest | `CONTEXT_COMPACTED.accepted_candidate` + digest；compact artifact仅作 provenance/audit | `ContextCompactedSemanticPayload`（窄 read view） | Conversation Memory、previous compacted view、RunInput provenance、budget text projection |
| forward intent type/status、reference reason | LLM candidate | `ForwardIntent*VNext` / `ReferenceContinuityReasonVNext` constructor | accepted candidate JSON enum values；memory snapshot保存 `.value` | 同一 accepted payload parser | memory view、compact readable view、RunInput section renderer |
| accepted compact ordinary LLM material | accepted candidate 经 memory projection | memory policy cap/floor + snapshot codec | Conversation Memory snapshot是派生 read model | Conversation Memory section renderer | ordinary RunInputBuilder；compact artifact provider不再渲染第二份 |
| accepted compact next-compactor previous view | accepted candidate | compact material whole-item/section selection + typed view/block consistency | material pack/manifest为派生物；EventLog仍是真源 | compact material typed previous-view projector | `ConversationCompactInputVNext.previous_compacted_view` |
| post-compact budget | accepted candidate业务文本 + current input | `context_budget` pure estimator | EventLog只持久化估算结果/diagnostic，不持久化第二份文本事实 | candidate业务文本 helper + budget estimator | compaction operation budget gate |
| accepted evidence durable facts | ToolRuntime/accept barrier 的 request atom、envelope、raw outcome | `evidence.py` envelope codec + `accepted_result_projection` identity/digest/status/query/source projection | `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、payload descriptor | `AcceptedToolResultProjection` + `AcceptedToolEvidenceLLMMaterial` | memory、compact material、RunInput；Tool Trace只消费事实字段并保留本地 display caps |
| accepted evidence LLM 文本 | typed LLM material | material dataclass非空校验；唯一 renderer固定字段、顺序、fallback | memory/runner input projection只是派生记录 | `render_accepted_tool_evidence_for_llm` | memory recent evidence、ordinary protected tail、fallback RunInput |

修复只落在 fact validator、typed projection owner 与直接消费者。UI/Service/Engine/Fins 不参与；不把 Host refs/digests 搬进 LLM material，也不让 trace/read API 反向成为 truth。

## 6. Contract / API decisions

### 6.1 唯一 persisted compact semantic read contract

在 `dayu/host/compact_payload.py` 新增窄类型与函数：

```python
@dataclass(frozen=True, slots=True)
class ContextCompactedSemanticPayload:
    accepted_candidate: ConversationCompactOutputVNext
    accepted_candidate_digest: str
    accepted_evidence_mapping_refs: tuple[str, ...]
    compact_artifact_ref: str


def parse_context_compacted_semantic_payload(
    payload: Mapping[str, JsonValue],
) -> ContextCompactedSemanticPayload:
    ...


def accepted_compact_business_texts(
    candidate: ConversationCompactOutputVNext,
) -> tuple[str, ...]:
    ...
```

`ContextCompactedSemanticPayload` 只包含当前三个消费者共同需要的 semantic candidate、digest、evidence coverage refs、artifact ref；operation id、proposal manifest、quality diagnostic、policy、budget 等治理字段继续由 `context_events` owner 处理。不得扩成 compact payload 全字段 God dataclass，也不得新增 builder/factory/registry。

parser 固定行为：

- 要求 current persisted `conversation_compact_output_v1` shape；五个 semantic fields 和 diagnostics 必须存在且类型正确。
- persisted fact 必须带 Host-owned `evidence_kind`，并严格构造 `FactEvidenceKindVNext`；不把 LLM wire proposal shape 与 persisted accepted shape混成兼容 parser。
- 严格构造 summary/fact/anchor child/intent/reference/diagnostic dataclass；未知 enum、空 required text、空 required labels、负 ordinal、错误 list/object/type 全部 `ValueError`。
- 校验 `accepted_candidate_digest == candidate.digest()`；不重算后继续接受 mismatch。
- 不读旧 alias、不兼容缺字段旧 shape、不跳过 invalid item、不输出 unknown/sentinel。

`context_events.validate_context_compacted_payload()` 保留 compact canonical event governance fields owner，但 candidate shape/digest/enum validation 委托该 parser；它不得继续维护第二套 `_validate_vnext_candidate_payload()` nested shape truth。

`accepted_compact_business_texts()` 只按稳定顺序返回：summary text；每个 fact claim；每个 anchor title 后跟其 child display text；每个 intent text；每个 reference text。它不返回 schema name、enum value、source/evidence labels、diagnostics、refs/digests/cursor。

### 6.2 Memory projection contract

`MemoryProjectionEvent` 新增：

```python
compacted_semantics: ContextCompactedSemanticPayload | None
```

事件不再让 `memory.py` 从 raw payload 解析 candidate。`durable.memory` / RunInput inline-repair event adapter 在 `CONTEXT_COMPACTED` 边界调用唯一 parser；`project_conversation_memory_event()` 要求 compacted event 必须有 typed semantics，非 compact event必须为 `None`。

Memory item 类型收紧：

```python
ForwardIntent.intent_type: ForwardIntentTypeVNext
ForwardIntent.status: ForwardIntentStatusVNext
ReferenceContinuityItem.reason: ReferenceContinuityReasonVNext
```

snapshot JSON 与 item table JSON 写 `.value`；read boundary用 enum constructor恢复。非法 snapshot enum 按现有 damaged snapshot / repair path fail closed，不增加旧值兼容或 `unknown` fallback。

memory projector 从 typed candidate 直接映射：保留完整 anchor children；fact evidence refs 继续来自 `accepted_evidence_mapping_refs`；policy cap/drop diagnostics不改变 candidate；source labels只保存为内部 source refs，不作为普通 LLM 业务文本。

### 6.3 Typed previous compacted view，不再 string round-trip

在 `compaction.py` / `compact_material.py` 保持两层小契约：

- `CompactMaterialBlock` 只用于 selection/provenance/size；其 `text` 必须是完整业务可读 item 文本，不是可被代码反解析的私有 wire format。
- `CompactReadableViewVNext` 保存真正交给下一次 compactor 的 typed previous view。
- `CompactMaterialPack` 同时携带 `previous_compacted_view` blocks 与 `previous_compacted_readable_view: CompactReadableViewVNext | None`，并校验 summary presence、item source labels、block kind/label coverage一一对应。typed readable view不是第二个 truth，它与 blocks 在同一个 projector 中从 `ContextCompactedSemanticPayload.accepted_candidate` 原子派生。

`CompactMaterialPack` 的 exact invariant 固定如下，并由其 `__post_init__` 在 pack
首次形成时校验；`PreDispatchCompactMaterialView` 与
`CompactPipelineSourceSnapshot` 只能传递已经通过该校验的 pair：

1. `previous_compacted_view == ()` 当且仅当
   `previous_compacted_readable_view is None`；不得用“空 typed view + 空 blocks”或
   “有 blocks + None view”表达同一状态。
2. blocks 只允许
   `SESSION_SUMMARY / EVIDENCE_BACKED_FACT / ANSWER_ANCHOR / FORWARD_INTENT /
   REFERENCE_CONTINUITY`，且 `section` 必须全部为
   `PREVIOUS_COMPACTED_VIEW`；summary block 最多一个。
3. summary block 的 presence 与 typed `session_summary` presence 完全相同；存在时
   `block.text == readable_view.session_summary`。
4. 对 facts、anchors、intents、references 分别按 tuple 顺序比较：对应 kind 的
   block 数量必须等于 typed section item 数量，且每一位置
   `block.block_label == item.source_label`；同一 label 不得跨 kind、重复或漏项。
   facts/intents/references 的 `block.text` 分别等于 typed item 的
   `claim_text/text/text`。anchor block 与 typed anchor 一一对应，typed anchor 必须
   保留完整 `anchor_title`、全部 `anchor_items` 及每个 ordinal；block 的业务文本由
   同一个 pair projector 从该完整 typed anchor 产生，不能再从 text 反解析 children。
5. blocks 与 typed view 都必须由同一次
   `ContextCompactedSemanticPayload.accepted_candidate` pair projection 原子产生；任何
   consumer 都不得单独重建或补齐另一侧。

唯一过滤入口固定为一个 pair-transform helper；计划签名为：

```python
def transform_previous_compacted_view_pair_for_recovery(
    *,
    blocks: tuple[CompactMaterialBlock, ...],
    readable_view: CompactReadableViewVNext | None,
    retained_block_labels: frozenset[PromptLocalMaterialLabel],
) -> tuple[tuple[CompactMaterialBlock, ...], CompactReadableViewVNext | None]:
    ...
```

tier 2 先按设计固定的 section/item 顺序得到 `retained_block_labels`，再只调用该
helper；tier 3 以空 label set 调用同一个 helper。helper 在一次遍历中同时过滤 blocks
和 typed sections，过滤完成后重新执行上述 invariant；禁止分别实现
`filter_blocks()` / `filter_readable_view()`，也禁止在 caller 侧手工清空其中一边。
tier 1 原样传递已验证 pair。

失败分类固定为：leaf typed contract 的直接错误类型仍由其 constructor 以
`TypeError` / `ValueError` 拒绝；一旦 pair 来自已持久化
`CONTEXT_COMPACTED`，任何 presence/count/kind/label/text/anchor-child invariant
mismatch 都表示 durable semantic projection 损坏，由 pack validation / EventLog-backed
adapter 抛 `HostDurableError`，不得降级为空 view、跳过单项或进入下一次 compactor。

`conversation_compact_input_vnext_from_material_pack()` 直接使用
`previous_compacted_readable_view`。删除 `_parse_previous_forward_intent_text()`、
`_parse_previous_reference_continuity_text()`、`_previous_compacted_*_vnext()` 这组从
block text 重建 typed view 的 helpers；S2 中 `_previous_blocks_from_snapshot()` 与
`_snapshot_summary_text()`、`_snapshot_fact_texts()`、
`_snapshot_answer_anchor_texts()`、`_snapshot_forward_intent_texts()`、
`_snapshot_reference_continuity_texts()` 及其仅供 string-wire 使用的
`_PREVIOUS_*` 格式常量若在 typed pair projector 迁移后失去最后消费者，必须在同一
slice 删除，不留 dead serializer。

每个新 prompt-local `source_label` 只作为当前 compactor invocation 的 opaque citation handle；old candidate labels不直接复用。普通 RunInput 不渲染 evidence/source labels。

### 6.4 Ordinary RunInput 只消费 Memory 的 accepted compact projection

`CompactArtifactView` 收窄为 provenance view：

```python
@dataclass(frozen=True, slots=True)
class CompactArtifactView:
    compaction_event_ref: str | None
    compact_artifact_ref: str | None
    compact_artifact_digest: str | None
    represented_evidence_refs: tuple[str, ...]
```

删除 `messages`，不保留空 tuple compatibility 字段。`DurableCompactArtifactProvider`
通过 typed compact payload 读取 event/artifact/evidence refs；
`_load_compact_artifact_tx()` 必须删除 `_compact_artifact_message_content()` 调用、
`SystemMessage` 构造和 `messages=` 赋值，只返回上述 provenance view。

`compact_pipeline.py` 的 `CompactPipelineCompactArtifactView` 同步删除 `messages`，且该
protocol 只保留 protected-raw-tail selection 实际通过它消费的
`compact_artifact_ref` / `compact_artifact_digest` 两个 provenance property；
`represented_evidence_refs` 继续保留在 concrete `CompactArtifactView`，供 accepted evidence
去重等直接消费者使用，但不进入这个 raw-tail protocol。`CompactArtifactView` 允许拥有
`compaction_event_ref`、represented refs 等额外字段，并继续以 structural subtyping 满足该
窄 protocol；不得增加 adapter/facade，也不得把 protocol 扩成通用 compact bag。pyright 与
focused protocol consumer tests 必须证明该 structural subtype 仍成立。

`MemorySnapshotView` 增加 `latest_compaction_event_ref: str | None`，值直接复制 typed
snapshot 的同名字段；`CompactArtifactView.compaction_event_ref` 直接使用最新 accepted
`CONTEXT_COMPACTED` row 的 `event_id`。两者的 equality 只定义为 event-id 字符串精确
相等，不比较 artifact ref/digest、cursor、sequence 或对象 identity，也不做 alias /
normalization。ordinary build 在取得两个 provider view 后、读取 protected raw tail 和
装配 messages 前执行一次 pair check：

| compact ref | memory latest ref | 结果 |
|---|---|---|
| `None` | `None` | no-compact；正常继续 |
| 非 `None` | 同一 event-id 字符串 | memory 已覆盖最新 accepted compact；正常继续 |
| 非 `None` | `None` | snapshot 缺 latest compact；抛 `MemoryProjectionRepairRequired` |
| `None` | 非 `None` | provider views 不可能同源；抛 `MemoryProjectionRepairRequired` |
| 非 `None` | 不同非 `None` event id | snapshot stale/superseded 或 provider views 不同源；抛 `MemoryProjectionRepairRequired` |

后三类统一复用现有
`MemoryProjectionRepairRequired(MemoryRepairRequest(...))`，reason 为
`MemoryRepairReason.SNAPSHOT_DAMAGED`，required sequence 来自
`_required_memory_event_sequence(current_facts)`，policy digest 来自 production memory
view；由现有 RunInput build caller 的 required catch-up/rebuild/inline-repair 流程处理。
不得新增异常类型、caller override、direct compact renderer 或 fallback message。若
production memory view 在 mismatch 时连构造 repair request 所需的 policy/cursor
metadata 都缺失，这是 provider contract 损坏，按现有 `HostDurableError` 收口，不能以
no-op memory 继续 dispatch。

`RunInputBuilder.build()` 的 ordinary `bounded_context_messages` 明确删除
`*compact.messages`，只装配 `*memory.messages +
*protected_recent_raw_tail.messages + *continuity.messages`；current input 仍在后续
`_current_user_tail_messages` 进入。删除 `_compact_artifact_message_content()`、
`_vnext_compact_candidate_semantic_lines()`、其 candidate nested mapping parsers，以及
`run_input.py` 中仅被这条 raw renderer 消费的
`_PAYLOAD_FIELD_SESSION_SUMMARY / EVIDENCE_BACKED_FACTS / ANSWER_ANCHORS /
FORWARD_INTENTS / REFERENCE_CONTINUITY_ITEMS` 和相关 nested candidate 字段常量。
`compact_material.py` 中重复读取 accepted candidate 的 `_candidate_*` mapping parsers 与
对应 candidate 字段常量也由 typed pair projector 取代并在 S2 删除；artifact/ref 等非
candidate governance 字段常量保留在各自真实 owner。

`build_run_input_material_blocks()` 中从 `compact_source_ref = ...` 开始、遍历
`compact.messages` 并构造 `block_id="compact:*"` / `SESSION_SUMMARY` block 的整个 loop 必须
删除，不保留空迭代、占位 block 或 adapter。`_compact_material_source_ref()` 的唯一调用者
就是该 loop，必须与 loop 在同一变更中删除函数定义；不得留下 dead helper。loop 删除后
`compact` 参数不再有 material 职责，因此同步从该函数签名与 call sites 删除；compact provenance 仍由
`RunInputBuilder` 持有的 typed `CompactArtifactView` 供 event-ref equality、protected raw-tail
selection、accepted evidence represented-ref 去重、runner-call manifest 与 audit 使用，绝不
再通过该 helper 生成 LLM-facing material block。`_run_input_message_content()` 仍服务 memory、
continuity 与 material-kind 等其它调用者，必须保留；不得借此清理不相关 helper。

这不是删除 compact 语义：production dispatch 已在 build 前 required catch-up，并同时提供 Durable Memory。旧的“no-op memory + durable compact messages”测试装配不是生产 owner path，必须迁到 memory projection；不得保留 compatibility renderer。

### 6.5 Post-compact budget API

在 `context_budget.py` 新增直接参数接口：

```python
POST_COMPACT_BASE_MESSAGE_COUNT = 2


def estimate_post_compact_budget(
    *,
    compacted_business_texts: tuple[str, ...],
    current_input_text: str,
) -> int:
    ...
```

函数严格校验 tuple/text，逐文本调用现有 conservative estimator，并加入由本模块拥有的固定 message overhead。`compaction_operation` 调用 `accepted_compact_business_texts(candidate)` 与该函数；删除本地 `_budget_after_compact_candidate()`、`_candidate_text_fragments()` 和 `_POST_COMPACT_BASE_MESSAGE_COUNT`。

`POST_COMPACT_BASE_MESSAGE_COUNT = 2` 不是经验魔法数：ordinary post-compact dispatch
遵守 design 第 23 节 one-system-message contract，所有 system-scoped compact/memory
材料先合并为一条 system envelope，再追加当前 `USER_INPUT_ACCEPTED` 的一条 user
message，因此固定 overhead 为 `1 + 1 = 2`。该值由 `context_budget` 的
post-compact ordinary dispatch estimator 拥有，函数不接受 caller override；允许 caller
覆盖会让相同 ordinary message contract 得出不同预算。常量旁必须有该推导注释，测试
必须同时断言 one-system envelope + current-input user 的两消息形态与 overhead，未来
message contract 改变时以 drift test 迫使 owner 同步修改。

`dayu.host.llm_compaction` 当前定义的
`_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、`_POST_COMPACT_BASE_MESSAGE_COUNT` 与
`_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 均无任何消费点，不拥有当前 proposal-budget
或 ordinary post-compact budget 语义。S2 把 `llm_compaction.py` 纳入 allowed files，仅原地
删除这三个 dead constant 定义；不移动、合并、re-export、保留 alias，亦不让其复用
`context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`。真正迁移的预算事实仍只有
`compaction_operation._POST_COMPACT_BASE_MESSAGE_COUNT` 到
`context_budget.POST_COMPACT_BASE_MESSAGE_COUNT` 的 ordinary post-compact dispatch owner
转移；相似名字不能替代直接消费证据。

### 6.6 Accepted evidence typed LLM material 与唯一 renderer

在 `accepted_result_projection.py` 增加窄类型：

```python
@dataclass(frozen=True, slots=True)
class AcceptedToolEvidenceLLMMaterial:
    tool_name: str
    query_text: str
    source_text: str
    result_text: str


def render_accepted_tool_evidence_for_llm(
    material: AcceptedToolEvidenceLLMMaterial | None,
) -> str:
    ...
```

`AcceptedToolResultProjection` 新增 `llm_material: AcceptedToolEvidenceLLMMaterial | None`、`tool_call_requested_event_ref: str | None`、`source_locator_refs: tuple[OpaqueEvidenceRef, ...]`，让 compact material 不再二次打开 envelope。Tool Trace现有 status/raw outcome/result details/request arguments字段保留，不改其 display caps。

唯一正常 renderer 文本固定为四行，字段顺序不可由消费者改变：

```text
工具名称：<tool_name>
查询语义：<query_text>
业务来源：<source_text>
工具结果：<result_text>
```

query/source unavailable 分别继续由 projection owner 的业务中性常量填充；`material is None` 时 renderer 返回一个 projection-owned、无内部 ref 的整体 unavailable 文本。不得写“结果已接受”这类只有 Host 治理含义、没有业务信息的占位；不得在 consumer 内再决定 fallback。

`MemoryProjectionEvent` 用
`accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None` 取代四个松散 evidence
text fields。`RunInputMaterialBlock` 在同一 slice 原子改成下列完整 evidence contract：

```python
accepted_evidence_id: str | None
tool_result_event_ref: str | None
tool_call_event_ref: str | None
payload_refs: tuple[str, ...]
artifact_refs: tuple[str, ...]
source_locator_refs: tuple[OpaqueEvidenceRef, ...]
accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None
```

删除 `readable_tool_name`、`readable_query_text`、`readable_source_text`，不允许新旧字段
并存的中间 contract 跨出 S3。invariant 固定为：

- evidence block 必须同时满足
  `section is EVIDENCE_MATERIAL` 与 `kind is ACCEPTED_TOOL_EVIDENCE`；上述三个 identity
  ref 和 `accepted_tool_evidence` 必须非空，payload/artifact provenance 按既有规则至少
  有一条，`source_locator_refs` 保持 typed tuple；`text` 必须逐字等于
  `render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`。
- non-evidence block 的 `accepted_tool_evidence`、三个 evidence identity ref 必须为
  `None`，payload/artifact/source-locator evidence provenance 必须为空；不得携带“暂时未
  使用”的 evidence god-bag。
- `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 从
  `accepted_tool_evidence.tool_name/query_text/source_text/result_text` 构造；不能把已经
  render 的 `block.text` 再 parse 成字段，也不能把四行 renderer 全文误当
  `response_text`。

字段名保持现有 public/internal contract，不做 rename；exact value mapping 固定为：

| Target field | Typed material source |
|---|---|
| `CompactEvidenceBlock.readable_tool_name` | `material.tool_name` |
| `CompactEvidenceBlock.readable_query_text` | `material.query_text` |
| `CompactEvidenceBlock.raw_result_text` | `material.result_text` |
| `CompactEvidenceBlock.readable_source_text` | `material.source_text` |
| `EvidenceReadableItemVNext.response_text` | `material.result_text` |

`RunInputMaterialBlock.text` / 下文简称的 `block.text` 仍逐字等于
`render_accepted_tool_evidence_for_llm(material)` 的四字段 renderer 输出；它不是上述任一
component field 的值来源，也不得被 parse。`CompactEvidenceBlock.raw_result_text` 与
`EvidenceReadableItemVNext.response_text` 都保持纯 `result_text` 分量。

迁移顺序在 S3 单次 implementation/review closure 内固定为：先定义 typed material 与唯一
renderer，并让 `AcceptedToolResultProjection` 产出它；再原子修改
`RunInputMaterialBlock` constructor/factory、`MemoryProjectionEvent` 及所有 producer /
consumer；最后删除三个 loose fields、三套 private renderers 与旧 fixture 参数。任何一次
slice checkpoint 都不得留下可被 production import 的新旧双字段 contract。

consumer 规则：

- Conversation Memory：`TOOL_RESULT_ACCEPTED` 总是调用唯一 renderer；material缺失时使用 owner-owned整体 unavailable文本，不从 payload/envelope重建。
- compact material：envelope缺失保持当前“不生成可引用 evidence block”；envelope存在但 typed LLM material缺失视为 accepted fact损坏并 `HostDurableError`，不把 unavailable占位变成可生成 fact 的 evidence。
- compact pipeline / run input：只用 typed block 调 renderer；各自只负责 system section/role routing。

### 6.7 Typed envelope mismatch 与 strict payload accessor

在 `evidence.py` 用专用异常替代字符串 protocol：

```python
class AcceptedEvidenceProducerEventRefMismatchError(ValueError):
    expected_event_ref: str
    observed_event_ref: str
```

`accepted_evidence_envelope_from_payload()` 在 mismatch 时抛该类型；删除 `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 作为控制流常量。`accepted_result_projection` 只按异常类型转换为 `HostDurableError`；compact material、durable memory、run input 不再重复 parse envelope，因此不再有自己的 mismatch catch。

`accepted_result_projection` 的 tool name、tool call id、resolution kind、tool fact kind 读取改用 `_event_payload.optional_payload_text()`；字段不存在/null仍为 optional，字段存在但类型错误/空白则 fail closed。P3-C 不改变 status fallback 优先级或 P3-E tool status owner。

## 7. Behavior matrices

### 7.1 Compact payload / memory / RunInput

| 输入场景 | typed read | Memory | next compact | ordinary RunInput | budget |
|---|---|---|---|---|---|
| valid current persisted candidate | 返回完整 typed payload | 物化五类 view | 完整 typed previous view | 只渲染 memory sections一次 | 统计五类业务文本 + current input |
| summary null、其它 lists empty | 合法 | empty summary/sections | previous view可为空 | 不渲染空 section | 只统计 current input/overhead |
| valid anchor含多个 children/ordinal | 保留完整 tuple | snapshot保留 children | next compact保留全部 children | Prior Answer Anchors保留全部 children | title与每个 child都计入 |
| invalid intent type/status/reference reason | enum constructor拒绝 | 不写 snapshot/checkpoint | 不构造 material pack | 不 dispatch | 不估算/不接受 |
| candidate list/object/text/ordinal类型非法 | 拒绝 | fail closed | fail closed | fail closed | 无结果 |
| candidate digest mismatch | 拒绝 | fail closed | fail closed | fail closed | 无结果 |
| old alias/缺 current required field | 拒绝 | 不兼容、不修补 | 不兼容 | 不兼容 | 无结果 |
| memory snapshot持有非法 enum | snapshot read fail closed并走现有 repair/rebuild | 不返回半合法 view | 不受 snapshot作为 compact truth影响 | required path repair，不能继续 dispatch | 无静默 fallback |
| tier 2 whole-section/item degrade | typed view与blocks同步过滤 | 不改 snapshot | 只保留完整 selected typed items | 不适用 | 只统计该 proposal accepted output |
| compact ref与memory latest ref均为`None` | no-compact provenance | no-compact snapshot | 无 previous compact | 正常继续，不触发repair | 不适用 |
| compact ref与memory latest ref为同一非空event id | typed compact provenance可读 | snapshot覆盖同一compact | EventLog compact builder仍可工作 | 正常继续，只渲染memory | 不适用 |
| compact ref非空、memory latest ref为`None` | compact provenance可读 | snapshot缺latest compact | EventLog compact builder仍可工作 | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)`；不用direct renderer顶替 | 不适用 |
| compact ref为`None`、memory latest ref非空 | provider views不同源 | snapshot不可用于本次build | 不构造previous compact | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)` | 不适用 |
| 两个ref均非空但event id不相等 | compact provenance可读 | snapshot stale/superseded或不同源 | EventLog compact builder仍可工作 | `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)` | 不适用 |
| candidate含超长 diagnostic | typed candidate仍可校验 | diagnostics不物化为五类业务事实 | 不进入 readable previous view | 不进入 ordinary input | diagnostic不计入 post-compact budget |

### 7.2 Accepted evidence

| 输入场景 | projection | Memory renderer | compact material | ordinary/fallback RunInput |
|---|---|---|---|---|
| valid envelope + semantic query + source + result | 完整 `AcceptedToolEvidenceLLMMaterial` | 四行固定文本 | 构造 evidence block | 与 Memory逐字相同 |
| query unavailable但 args/request不可安全展示 | projection-owned query fallback | 同一四行文本 | fallback作为query字段，不泄漏digest | 同一文本 |
| source locator均内部或缺失 | projection-owned source fallback | 同一四行文本 | source字段仍业务中性自解释 | 同一文本 |
| envelope缺失 | 保留现有 typed diagnostic，不新增legacy branch | material可构造则统一渲染，否则整体 unavailable | 不生成可引用 evidence block | 无 block则不伪造 |
| envelope存在但 tool name/result不可读 | `llm_material=None` + diagnostic | 整体 unavailable | fail closed，不能作为fact evidence | 不产生accepted block |
| producer event ref mismatch | typed mismatch exception -> `HostDurableError` | 不写 snapshot | 不构造block | 不 dispatch |
| optional payload field存在但错误类型/空白 | strict accessor `HostDurableError` | 不把错误当missing | fail closed | fail closed |
| failed/cancelled/governed_error/lost status | status仍由P1-A/P3-E现有规则处理 | renderer只表达query/source/result，不重建status | 不改变status owner | resume guidance/status展示保持现有owner |
| result很长 | typed `result_text`保持完整 | selection/cap按whole item处理 | chunk/keep-drop/fail closed由compact policy负责 | 不在shared renderer静默截断 |

## 8. Implementation slices

计划采用 3 个 slice。S1 先关闭 durable accepted compact -> memory projection；S2 在其上关闭 previous compact/run input/budget 的高风险选择与 fallback 路径；S3 独立关闭 evidence renderer/envelope error。这样每个 slice 都有 producer-validator-persistence-projection-consumer闭环，不按文件机械拆分；把 S1+S2 合并会把 snapshot codec、fallback/degrade、ordinary input去重与budget gate放进一次 review，失败面过大。

### S1. Accepted compact typed payload -> Conversation Memory closure

Objective：建立唯一 persisted accepted candidate parser，并让 Conversation Memory/snapshot codec只消费 typed candidate与enum。

Prerequisites：P3-B accepted commits存在；当前 design/control不变。

Allowed production files：

- `dayu/host/compact_payload.py`
- `dayu/host/context_events.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/run_input.py`（仅 MemoryProjectionEvent adapter 与 enum value renderer）

Allowed tests/docs：

- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `dayu/host/README.md`（最终 README gate统一更新，可在S3完成）
- `tests/README.md`（仅命中其当前测试分层职责时）

Exact changes：

1. 实现 `ContextCompactedSemanticPayload` parser与 candidate business texts helper；`context_events` 委托 nested candidate validation。
2. `MemoryProjectionEvent` 增加 typed compact field；durable memory与inline repair adapter在event boundary parse一次。
3. memory五类 helper改为接收 typed candidate，不接收payload mapping；删除candidate字段常量、`_accepted_candidate_mapping`与nested mapping accessors。
4. 收紧 ForwardIntent/Reference enum字段；snapshot/table JSON显式写 `.value`，read严格恢复enum。
5. 迁移 fixture：所有 accepted compact event用`build_context_compacted_payload()` + typed candidate构造；非法shape测试只在parser owner测试，不再直接调用下游私有helper。

Tests/assertions：

- roundtrip所有五类candidate、多个anchor children、enum identity、digest/ref。
- invalid/missing/wrong type/old shape/invalid enum/digest mismatch全部owner fail closed，memory checkpoint/snapshot不推进。
- valid compact event只parse一次并物化完整snapshot；snapshot JSON roundtrip保留enum和children。
- invalid snapshot enum按damaged snapshot分类，不写unknown。
- existing empty compact、fact cap/drop、merge、inline repair、rebuild tests保持通过。

Completion signal：Memory路径不再读取raw accepted candidate fields；S1 propagation audit从typed producer到snapshot/RunInput memory sections通过。

Stop conditions：若current persisted producer shape与`ConversationCompactOutputVNext.to_json()`不一致，或合法production event缺少 `evidence_kind`，停止并回到design/producer裁决；不得加兼容parser。

### S2. Typed previous view -> compact pipeline / ordinary RunInput / budget closure

Objective：消除compact material string round-trip和ordinary compact第二renderer，把pure budget归owner。

Prerequisites：S1 accepted commit；typed compact parser与enum snapshot contract稳定。

Allowed production files：

- `dayu/host/compaction.py`
- `dayu/host/compact_payload.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/run_input.py`
- `dayu/host/context_budget.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/llm_compaction.py`（仅删除 6.5 指定的三个 dead constants）

Allowed tests/docs：

- `tests/host/test_compaction_contract.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_compact_smoke.py`
- `dayu/host/README.md`
- `tests/README.md`（仅按职责需要）

Exact changes：

1. accepted compact material projector 从
   `ContextCompactedSemanticPayload.accepted_candidate` 一次产生 selection blocks 与
   `CompactReadableViewVNext`；保留完整 fact、anchor title/children/ordinal、typed
   intent/reference，按 6.3 exact invariant 在 `CompactMaterialPack.__post_init__` 校验。
2. material pack/source snapshot 携带已验证 typed pair；normal/tier1 原样传，tier2/tier3
   只调用 `transform_previous_compacted_view_pair_for_recovery(...)`，不得分别过滤。pair
   mismatch 从 durable path 抛 `HostDurableError`。
3. 删除 `_parse_previous_forward_intent_text()`、
   `_parse_previous_reference_continuity_text()`、`_previous_compacted_*_vnext()`、
   `_previous_blocks_from_snapshot()`、迁移后无消费者的 `_snapshot_*_texts()` 与其
   `_PREVIOUS_*` string-wire 常量；block text 不再充当隐式 wire schema。
4. 删除 `compact_material.py` 的 `_candidate_session_summary_text()`、
   `_candidate_facts_texts()`、`_candidate_answer_anchor_texts()`、
   `_candidate_forward_intent_texts()`、`_candidate_reference_continuity_texts()` 及其重复
   candidate 字段常量；所有 accepted candidate 读取改走 `compact_payload` typed parser。
5. `CompactArtifactView` 删除 `messages` 且增加 `compaction_event_ref`；
   `DurableCompactArtifactProvider._load_compact_artifact_tx()` 删除
   `_compact_artifact_message_content()` 调用、`SystemMessage` 构造和 `messages=`；
   `compact_pipeline.py` 的 `CompactPipelineCompactArtifactView` 同步删除 `messages` 与
   raw-tail path 不消费的 `represented_evidence_refs`，只保留 artifact ref/digest 两个窄
   provenance property；`CompactArtifactView` 保持 structural subtype，不加 adapter；
   `MemorySnapshotView` 暴露 latest ref；ordinary build 按 6.4 equality/repair matrix 校验。
6. `RunInputBuilder.build()` 删除 `*compact.messages`；ordinary bounded context 只拼 memory、
   protected raw tail、continuity，accepted compact 只渲染 memory 一次。删除
   `build_run_input_material_blocks()` 中从 compact source ref 到 `compact.messages` 迭代及
   loop body 的整个分支，并随这个唯一调用者 loop 一起删除
   `_compact_material_source_ref()` 函数定义；从该 helper 签名/call sites 删除失去 material
   职责的 `compact` 参数。`_run_input_message_content()` 仍有 memory、continuity 与
   material-kind 调用者，明确保留，不做无关 helper cleanup。provenance 继续由 builder 的
   typed compact view 供 equality/raw-tail/evidence 去重/manifest 使用，不创建 compact
   material block。删除
   `_compact_artifact_message_content()`、`_vnext_compact_candidate_semantic_lines()`、
   nested candidate mapping/list parser 与 `run_input.py` 重复 candidate 字段常量；测试从
   no-op memory + compact renderer 迁到 production required memory catch-up path，不保留空
   messages compatibility 字段。
7. 新增 `estimate_post_compact_budget()`；operation 只传 candidate business texts/current
   input 并比较 threshold；diagnostics 不参与。`2` 按 one-system envelope + current user
   message 推导，保留 owner constant 且无 caller override；只把
   `compaction_operation` 同名常量的真实消费语义迁入 `context_budget`。同时仅在
   `llm_compaction.py` 原地删除无消费点的 `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、
   `_POST_COMPACT_BASE_MESSAGE_COUNT`、`_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT`；不移动、
   re-export、alias 或保留第二 owner。

Tests/assertions：

- next compact input previous view与accepted candidate逐字段一致，old prompt-local labels被替换为本次opaque labels，internal refs不进入LLM JSON。
- tier2 blocks/readable view 按 kind/count/order/label/text exact invariant 保持同集合；tier3
  二者同时变为 `()/None`；任一边独立变化均由 pack/helper 以 durable
  `HostDurableError` fail closed。
- ordinary public path只有一个system envelope；summary/fact/anchor/intent/reference各出现一次；不存在`Accepted compacted conversation view`、evidence/source labels、raw artifact JSON。
- `CompactPipelineCompactArtifactView` 只声明 artifact ref/digest，concrete
  `CompactArtifactView` 通过 structural typing；`build_run_input_material_blocks()` 的结果不含
  `compact:*` block，但 raw-tail selection、represented evidence 去重与 manifest 仍能读取
  concrete compact provenance。
- `None/None` no-compact 与 equal non-None event id 正常；compact-only、memory-only、两个
  non-None mismatch 均抛 `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED)`，由既有
  required catch-up/rebuild path 处理。
- post-compact estimator独立unit tests覆盖empty/all sections/current input/overhead/diagnostics excluded；operation proactive hard threshold与reactive non-authoritative语义不变。
- `llm_compaction.py` 三个指定 `_POST_COMPACT_*` constant 零匹配，且没有移动、re-export
  或替代 alias；`context_budget.POST_COMPACT_BASE_MESSAGE_COUNT` 仍是唯一有消费语义的
  ordinary post-compact owner；`tests/host/test_llm_compaction.py` 进入 S2 focused 与
  aggregate matrix，并对 `dayu.host.llm_compaction` 执行 aggregate coverage collection 和
  单文件 `--fail-under=80`。
- public compact smoke证明accepted compact -> memory projection -> ordinary post-compact dispatch与下一次compact均同源。

Completion signal：`compact_material.py`与`run_input.py`不再独立parse accepted candidate；operation无pure estimator实现；ordinary input无duplicate compact message。

Stop conditions：如果fallback/degrade必须改写semantic item才能保持预算，或production dispatch不能保证memory required catch-up，停止回design裁决；不得恢复direct compact renderer或字段级截断。

### S3. Accepted evidence typed LLM material / renderer / typed mismatch closure

Objective：在P1-A typed projection之上统一最终LLM evidence文本，移除重复envelope解析和字符串错误协议。

Prerequisites：S2 accepted commit；RunInput evidence block/section routing稳定。

Allowed production files：

- `dayu/host/evidence.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/run_input.py`

Allowed tests/docs：

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_tool_trace_projection.py`（只做unchanged-consumer regression）
- `tests/host/test_public_compact_smoke.py`
- `dayu/host/README.md`
- `tests/README.md`（仅按职责需要）

Exact changes：

1. 新增typed mismatch exception，删除string control-flow constant与所有`str(exc)`比较。
2. AcceptedToolResultProjection增加narrow LLM material、request event ref、source locators；strict shared payload accessor替代lenient evidence字段accessor。
3. durable memory、run input inline repair、compact material不再二次打开envelope；全部消费projection。明确删除 `compact_material.py` 中 `accepted_evidence_envelope_from_payload()` 调用及 `if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block；evidence block 只从 `AcceptedToolResultProjection` 的 typed LLM material 构造。
4. `MemoryProjectionEvent` / `RunInputMaterialBlock` 按 6.6 完整 evidence contract 原子迁移；evidence block text 等于 shared renderer，non-evidence block 不携带 evidence 字段；删除三个 loose readable fields 与三套 private renderers，不保留 dual-field intermediate contract。
5. 按 6.6 no-rename mapping 构造 `CompactEvidenceBlock` 与
   `EvidenceReadableItemVNext`；component fields 只取 typed material 对应分量，绝不解析
   `block.text`，也不重命名既有 target fields。memory/compact pipeline/run input统一调用唯一
   renderer；section routing/caps仍归各消费者policy，不移入renderer。
6. 不改`tool_trace.py`，不抽全局bounded text helper，不触及tool status P3-E。

Tests/assertions：

- same durable accepted result通过memory、ordinary protected tail、fallback RunInput得到逐字相同四行文本。
- `CompactEvidenceBlock` 四个 component fields 与 `EvidenceReadableItemVNext.response_text`
  逐项断言 6.6 exact mapping；另断言 `block.text` 是完整四字段 renderer，而
  `raw_result_text/response_text` 只等于 `material.result_text`。
- query/source unavailable使用owner常量；material missing使用owner整体fallback；任何输出不含internal id/ref/digest/wait/poll/runtime术语。
- producer mismatch断言专用exception type/expected/observed fields；上层断言HostDurableError cause chain。
- malformed optional payload text fail closed；absent/null optional按现有contract处理。
- envelope absent、missing result/tool、failed/cancelled/wait-resolution行为符合7.2矩阵。
- Tool Trace regression只证明query/status/source/result truth仍来自projection，现有trace caps/suffix不变；production file diff不得包含`tool_trace.py`。

Completion signal：source scans只剩projection owner的renderer/fallback；所有accepted evidence LLM consumers无字段格式化与envelope parse。

Stop conditions：若直接import projection types造成Host bootstrap cycle且不能通过窄leaf contract在Host层内解决，停止并记录import graph；不得用lazy import、`Any`、`object`或胶水facade逃避。

## 9. Tests、coverage、pyright 与 validation

每个 slice 先跑其 focused tests。S2 的 event-ref safety boundary 必须在
`tests/host/test_run_input_builder.py` 使用以下命名测试，名称本身区分 no-compact、equal
与三种 mismatch，禁止用一个参数化“mismatch”名字掩盖缺失 case：

- `test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`
- `test_matching_compact_and_memory_compaction_event_refs_build_once`
- `test_compact_event_without_memory_compaction_ref_requires_repair`
- `test_memory_compaction_ref_without_compact_event_requires_repair`
- `test_mismatched_compact_and_memory_compaction_event_refs_require_repair`

后三个测试都断言 exception type、`MemoryRepairReason.SNAPSHOT_DAMAGED`，且
`RunInputBuilder` 未读取 protected raw tail、未记录 manifest、未 dispatch；equal case 断言
`DurableCompactArtifactProvider` 不生成 message、ordinary system envelope 中五类 compact
业务内容只来自 memory 且各出现一次。上述文件必须同时进入 S2 focused command和 S3 后
aggregate affected matrix。S2 focused validation 固定为：

```bash
source .venv/bin/activate
python -m pytest tests/host/test_run_input_builder.py -q
python -m pytest tests/host/test_llm_compaction.py -q
```

`test_llm_compaction.py` 是仓库现有、直接 import `dayu.host.llm_compaction` 并覆盖 parser、
safe outcome、prepared proposal input 与 runner call 的 owner test；不能仅依赖
`test_public_compact_smoke.py` 对 `_run_agent_request` 的局部触达证明该实际修改模块达到
80%。focused pass 不能代替 aggregate pass。S3 后运行：

```bash
source .venv/bin/activate
python -m pytest \
  tests/host/test_context_compact_events.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_context_budget.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compact_material.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_memory_projection.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_public_compact_smoke.py -q
```

逐文件 coverage（每个修改模块目标 >= 80%，不以aggregate数字掩盖单文件不足）：

```bash
source .venv/bin/activate
python -m coverage erase
python -m pytest <上述 affected matrix> \
  --cov=dayu.host.compact_payload \
  --cov=dayu.host.context_events \
  --cov=dayu.host.memory \
  --cov=dayu.host.durable.memory \
  --cov=dayu.host.compaction \
  --cov=dayu.host.compact_material \
  --cov=dayu.host.compact_pipeline \
  --cov=dayu.host.run_input \
  --cov=dayu.host.context_budget \
  --cov=dayu.host.compaction_operation \
  --cov=dayu.host.llm_compaction \
  --cov=dayu.host.evidence \
  --cov=dayu.host.accepted_result_projection \
  --cov-report=
python -m coverage report --include='dayu/host/compact_payload.py' --fail-under=80
python -m coverage report --include='dayu/host/llm_compaction.py' --fail-under=80
# 对上述每个实际修改的 production 文件分别执行同一 report 命令。
```

类型/边界：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
python -c 'import dayu.host; import dayu.host.memory; import dayu.host.compact_material; import dayu.host.run_input'
python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Source scans：

```bash
rg -n '_accepted_candidate_mapping|_vnext_compact_candidate_semantic_lines|_parse_previous_forward_intent_text|_parse_previous_reference_continuity_text' dayu/host
rg -n '_previous_blocks_from_snapshot|_snapshot_(summary_text|fact_texts|answer_anchor_texts|forward_intent_texts|reference_continuity_texts)|_candidate_(session_summary_text|facts_texts|answer_anchor_texts|forward_intent_texts|reference_continuity_texts)' dayu/host/compact_material.py
rg -n 'def _previous_compacted_(view|session_summary|fact_material|answer_anchors|forward_intents|references)_vnext' dayu/host/compact_material.py
rg -n 'str\(exc\).*ACCEPTED_EVIDENCE|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host
rg -n 'def _accepted_tool_evidence_content|def _accepted_evidence_readable_text' dayu/host
rg -n '_PAYLOAD_FIELD_(SESSION_SUMMARY|EVIDENCE_BACKED_FACTS|ANSWER_ANCHORS|FORWARD_INTENTS|REFERENCE_CONTINUITY_ITEMS)' dayu/host/memory.py dayu/host/compact_material.py dayu/host/run_input.py
rg -n 'compact\.messages|messages=.*CompactArtifactView|_compact_artifact_message_content' dayu/host/run_input.py
rg -n '_compact_material_source_ref' dayu/host/run_input.py
sed -n '/^class CompactPipelineCompactArtifactView/,/^class CompactPipelineAttemptDispatchSnapshot/p' dayu/host/compact_pipeline.py | rg -n 'def (messages|represented_evidence_refs)'
sed -n '/^class CompactPipelineCompactArtifactView/,/^class CompactPipelineAttemptDispatchSnapshot/p' dayu/host/compact_pipeline.py | rg -n 'def compact_artifact_(ref|digest)'
rg -n 'accepted_evidence_envelope_from_payload|str\(exc\)' dayu/host/compact_material.py
rg -n '_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE|BASE_MESSAGE_COUNT|TOOL_SCHEMA_OVERHEAD_COUNT)' dayu/host/llm_compaction.py
git diff -- dayu/host/tool_trace.py
git diff --check
```

预期：ownership/dead-code scans 无生产匹配（字段常量只允许留在 LLM proposal parser、
canonical event producer/validator、唯一 compact payload parser 等真实 owner）；protocol 的
第一个 scoped scan 零匹配，第二个 scoped scan 只匹配 ref/digest 两个 property，且 pyright
证明 concrete `CompactArtifactView` 仍为 structural subtype；
`_compact_material_source_ref` scan 是零匹配 hard acceptance gate；
`_run_input_message_content()` 因仍有其它调用者而保留，不属于 dead-code scan 或本次清理范围；
`compact_material.py` 不再 import/call `accepted_evidence_envelope_from_payload`；
`tool_trace.py` diff 为空；whitespace 检查通过。另加 source assertion：
`compaction_operation.py` 不再定义 `_POST_COMPACT_BASE_MESSAGE_COUNT`，
`context_budget.py` 只定义 ordinary post-compact owner 常量，
`llm_compaction.py` 的三个指定 dead constants 全部零匹配且不得 import/re-export/alias
`context_budget` owner。

## 10. Propagation audit

### 10.1 Compact semantic fact

```text
LLM proposal JSON
  -> llm_compaction strict proposal parser
  -> ConversationCompactOutputVNext
  -> Host quality/source-label accept barrier
  -> context_events.build_context_compacted_payload
  -> EventLog CONTEXT_COMPACTED + candidate digest/artifact refs
  -> compact_payload.parse_context_compacted_semantic_payload
     -> durable memory event adapter -> Conversation Memory snapshot
        -> RunInput memory sections -> Engine AgentRunRequest.messages
     -> EventLog-backed compact material -> typed previous readable view
        -> next ConversationCompactInputVNext
     -> accepted_compact_business_texts -> context_budget estimator
        -> compaction operation budget gate
```

Audit assertions：candidate digest与typed candidate一致；五类item数量/文本/enum/anchor children一致；snapshot source refs与compact event一致；next compact使用新的prompt-local labels；ordinary input不出现第二份compact artifact renderer；`CompactPipelineCompactArtifactView` 只投影 raw-tail 需要的 artifact ref/digest，concrete view 的 event/artifact/evidence provenance 继续供 equality、selection、去重与 audit 使用；`build_run_input_material_blocks()` 不从 compact provenance 生成 material block；manifest/input projection记录的最终messages与实际Engine input同源。

### 10.2 Accepted evidence fact

```text
ToolRuntime / wait-resolution accept barrier
  -> TOOL_CALL_REQUESTED request atom
  -> TOOL_RESULT_ACCEPTED envelope + raw outcome + refs/digests
  -> accepted_result_projection identity/digest/query/source/result validation
  -> AcceptedToolEvidenceLLMMaterial
     -> durable MemoryProjectionEvent -> snapshot recent evidence
        -> ordinary RunInput system section
     -> EventLog compact material block
        -> ConversationCompactInputVNext.evidence_material
     -> ordinary protected raw tail / tier4-5 fallback block
        -> shared renderer -> RunInput system section
  -> Tool Trace consumes same projection facts, then applies trace-only display caps
```

Audit assertions：同一 tool/query/source/result文本在memory/compact/fallback同源；typed material 到 `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 严格使用 6.6 no-rename mapping，四字段 renderer 全文只进入 `block.text`，结果分量只进入 `raw_result_text/response_text`；envelope mismatch fail closed；rendered LLM text无internal refs；Tool Trace的bounded display不反向改变LLM material；status继续由P3-E owner处理。

## 11. README / docs decision

实现前已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。本 WU 会改变 Host 内部稳定 owner contract与RunInput装配事实，因此最终实现应更新该 README：

- Conversation Memory条目说明 accepted compact candidate在单一typed read boundary解析，enum非法fail closed。
- RunInputBuilder条目说明compact artifact provider只提供provenance，accepted compact LLM material只来自memory snapshot。
- accepted result条目说明query/source/result typed projection之上还有唯一LLM evidence renderer；Tool Trace truncation仍是trace-only display。
- context budget条目说明post-compact pure estimator归context budget，operation只编排。

`tests/README.md` 只有在新增测试文件/测试分层或常用命令职责变化时更新；若只扩展现有文件，不机械同步。根README、`dayu/README.md`、Engine README不更新：用户入口、安装/CLI、分层方向与Engine contract均不变。`docs/host/design.md` / `docs/engine/design.md` 不更新：当前设计已覆盖目标行为；若实现发现必须改变schema、fallback状态机或层边界，触发stop condition而不是顺手改设计。

## 12. Non-goals、不过度设计与 residual risks

Non-goals：

- 不做 schema migration、旧库/旧candidate兼容、旧shape alias、unknown fallback。
- 不处理 P3-J EventLog全局taxonomy/DDL，P3-E tool status，P3-J/P3-E范围不能借P3-C进入。
- 不横扫 `tool_trace.py` accessor/truncation，也不统一全仓 `_bounded_text` / suffix。
- 不改变 ToolRuntime/wait callback/status production contract，不改Fins。
- 不做全局trace truncation、全局payload accessor重构、renderer registry、generic projection framework。
- 不修改UI/Service/Engine层，不新增public API/export，除非Host内部 import-boundary test明确要求包内导出。
- 不做plan review、code review、deepreview、commit/push/PR/control更新于本gate。

不过度设计说明：

- 只新增两个窄typed value（compact semantic payload、accepted evidence LLM material）和一个专用异常；不新增God dataclass/builder、callback、factory、profile、query object或service locator。
- compact payload治理metadata仍归context_events，candidate业务语义归compact payload parser，selection/rendering归compact material，budget归context_budget；不把它们合并进共享“context everything”模块。
- evidence projector继续拥有事实，renderer只拥有最终文本；Tool Trace保留自己的display policy，避免共享helper吞并所有消费者职责。
- 三个slice分别关闭可验证传播路径；不为未来provider tokenizer、retrieval、schema upgrade预留抽象。

Residual risks 分类：

- fixed in S1：persisted candidate weak parsing、enum drift、memory snapshot弱类型。
- fixed in S2：compact string round-trip/anchor loss、ordinary duplicate compact renderer、
  compact protocol structural subtype/非 material provenance、pure budget misplaced/diagnostic
  overcount、`llm_compaction` 三个 false-owner dead constants。
- fixed in S3：evidence renderer/fallback drift、string exception protocol、accepted-result lenient payload text。
- assigned to P3-E：accepted tool status fallback/raw outcome reconstruction。
- assigned to P3-J：全局EventLog schema/taxonomy/DDL closed-set。
- rejected as non-defect：Tool Trace与accepted projection各自bounded display/truncation helper相似。

## 13. Stop conditions 与 blocking questions

立即停止 implementation并回controller/user裁决的条件：

- production `CONTEXT_COMPACTED` persisted shape不是`ConversationCompactOutputVNext.to_json()`且需要兼容分支才能读取。
- 需要改变`conversation_compact_output_v1` schema、memory snapshot schema version或SQLite DDL/migration。
- 删除compact direct renderer后production dispatch无法通过required memory catch-up拿到同一accepted compact，且修复需要改变dispatch状态机。
- tier2 degrade无法在不改写/截断semantic item的前提下保持blocks与typed readable view一致。
- shared evidence type引发无法通过正常Host依赖分层解决的import cycle；禁止lazy import/glue facade绕过。
- accepted evidence renderer需要tool status/P3-E或全局Tool Trace truncation变化才能正确。
- 任何测试只能依赖旧shape/非法enum/手写consumer private helper通过。
- pyright出现新增/扩散错误，或任一实际修改production文件coverage低于80%且无法在当前owner测试补齐。

Blocking questions：无。当前代码、两份 plan re-review 与 controller adjudication 的证据
足以直接进入 final parallel plan re-review；本轮按用户要求停在 final plan micro-fix artifact。

## 14. Completion report / handoff format

每个implementation slice完成报告必须包含：

1. slice id与allowed files实际变更清单。
2. owner contract/API最终签名与任何plan偏差。
3. source findings状态：accepted finding对应fix/re-review状态；rejected finding保持原因。
4. producer/validator/persistence/projection/LLM-visible propagation audit结果。
5. focused tests、aggregate tests、逐文件coverage、pyright、import/weak typing/source scans、README decision、`git diff --check`。
6. residual risk与owner；不得留unclassified risk。
7. next Gate Order entry point。

Plan gate handoff：

- artifact：`docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- decision：`ready-for-final-plan-rereview`
- slice count：3
- finding dispositions：accepted 7 / rejected 2 / deferred 0 / needs-more-evidence 0
- second-fix finding status：`P3-C-RR-PF-01` 至 `P3-C-RR-PF-05` 均 fixed in plan
- final micro-fix finding status：`P3-C-RR2-PF-01` fixed in plan；controller coverage follow-up
  与所有前序 closure 保持不变
- blocking questions：0
- next entry point：P3-C final parallel plan re-review（AgentMiMo + AgentDS；当前请求禁止执行）
