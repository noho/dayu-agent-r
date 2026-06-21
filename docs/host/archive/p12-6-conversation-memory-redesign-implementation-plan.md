# Phase 12.6 Conversation Memory Redesign 实施计划

状态：PLAN_FIX_READY
阻塞问题：0  
当前 gate：P12.6 Slice 1 plan-fix ready for re-review
规划角色：role-scoped planning specialist  
计划真源：`docs/host/implementation-control.md` 当前状态与 Phase 12.6、`docs/host/design.md` §1 / §24 / §25  
review 真源：`docs/reviews/p12-6-design-refinement-controller-20260524.md`、`docs/reviews/p12-6-design-review-controller-adjudication-20260524.md`、`docs/reviews/p12-6-design-rereview-mimo-20260524.md`、`docs/reviews/p12-6-design-rereview-ds-20260524.md`  
plan-fix 真源：`docs/reviews/p12-6-slice1-stop-controller-adjudication-20260524.md` 的 accepted finding S1-PF1
讨论输入：`docs/host/conversation-memory-compact-io-first-principles-discussion.md` 仅作为背景输入，不替代 `docs/host/design.md`。

## 1. 目标与动机判断

P12.6 的动机成立，且严重性没有被高估。根因不是 token 阈值偏小，也不是 reactive recovery 估算不准，而是当前 compaction I/O 仍允许把 EventLog range、Host provenance metadata、当前长输入和 raw evidence 混在同一个 LLM-facing request 中渲染，导致 compactor prompt 可能比触发 compact 的 ordinary input 更大，并诱导 LLM 把 Host ledger key 当作语义输入。

本 phase 的目标是把 Conversation Memory 与 Context Compaction 收口到 `docs/host/design.md` 已裁决的结构：

- Conversation Memory 是 EventLog read model，不是事实真源。
- Compactor 输入是 compact material pack，不是从 Session 起点重放 EventLog ledger。
- LLM 看到 stable / history / evidence / current input anchor 的去重可读材料和 prompt-local labels。
- Host 内部维护 prompt-local label 到 canonical `TOOL_RESULT_ACCEPTED`、payload / artifact / locator refs 的 provenance map。
- `evidence_backed_facts` 只能来自 accepted compact output 的 fact candidates，且必须引用 accepted evidence。
- proactive compact 的 material pack 不得显著大于 ordinary run input material。
- reactive compact 使用同一个 operation 内的 bounded multi-pass transient output，最终只提交一个 merged `CONTEXT_COMPACTED` 或一个 `CONTEXT_COMPACTION_FAILED`。

## 2. 直接证据

- `docs/host/implementation-control.md` 当前状态：P12.6 design re-review PASS，进入 handoff implementation-ready plan gate。
- `docs/host/implementation-control.md` Phase 12.6：明确禁止 EventLog range dump、Host provenance key 作为 LLM 主要语义输入、`result_preview` 路径和 current input / raw evidence 重复渲染。
- `docs/host/design.md` §1：Host 是 Session / Run / Attempt / EventLog / memory / tool governance 的治理真源；Engine 只执行单次 `AgentRunRequest`；工具事实、证据锚点和审计链必须可追溯。
- `docs/host/design.md` §24：Conversation Memory 结构固定为 stable layer 与 history pool；accepted evidence envelope 是 provenance anchor，不是 evidence 内容容器；LLM extractor 必须读取 raw tool result / raw transcript。
- `docs/host/design.md` §24：V1 consolidation 由 memory projection policy 与 RunInputBuilder / compactor input bounded selection 执行，不新增 `memory_retention_candidate`。
- `docs/host/design.md` §25：material pack 至少包含 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor`，且 section mapping 必须一对一。
- `docs/host/design.md` §25：segment selection 给定 input cursor、memory snapshot cursor、policy 与 ordinary input material list 必须确定性输出 block ids。
- `docs/host/design.md` §25：material pack build 前必须校验 memory snapshot cursor，失败走 catch-up / rebuild / inline delta repair 或 compaction / pre-dispatch failure，不得让 Run 进入 `RECOVERING`。
- `docs/host/design.md` §25：reactive multi-pass 是同一 compaction operation 内的 material block batch processing；中间产物只能是 transient artifact / diagnostic artifact。
- `docs/reviews/p12-6-design-review-controller-adjudication-20260524.md`：七个 accepted findings 已写回设计，四个 deferred items 必须在 plan 中决策。
- 两份 re-review 均 PASS，但残余观察要求 planning 固定确定性 segment rule、single evidence block 超预算处理和 V1 bounded working set 策略。
- 当前代码证据：`dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py` 构造 `CompactionRequest` 时仍从 `start_event_sequence=1` 读取 bounded range，实际是 Session 起点 range。
- 当前代码证据：`dayu/host/llm_compaction.py` 的 prompt block 会渲染 `input_event_refs`、`accepted_evidence_envelopes`、payload digest、event refs、policy-like refs 和 `compact_raw_context`，未形成 §25 要求的 material pack section ownership。
- 当前 plan-fix 证据：`docs/reviews/p12-6-slice1-stop-controller-adjudication-20260524.md` 已裁决 Slice 1 停止有效；旧 `CompactionRequest` 字段的直接生产构造 / 消费点包括 `dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/compaction_evidence.py`。删除旧字段的首个实现切片必须把这些文件纳入同一个 compile-safe ownership boundary，不能用 deprecated alias、compat wrapper、old-field default 或 test-only compatibility 过渡。

## 3. 范围

### 3.1 范围内

- 重构 Host internal compaction typed contracts，使 `CompactionRequest` 以 material pack 为主，内部 provenance map 与 LLM-facing material 分离。
- 新增或重构 compact material list / material pack builder，覆盖 stable input、history input、evidence input、current input anchor。
- 固定 deterministic segment selection 规则，并提供 trace / test 可断言的 block ids。
- 从 accepted `TOOL_RESULT_ACCEPTED` canonical fact 引用的 digest-checked raw payload / raw result descriptor 读取 raw evidence 内容。
- 修改 LLM compactor prompt rendering：只渲染 material pack，不渲染 EventLog ledger wrapper、accepted evidence envelope metadata、payload ref / digest / cursor / event id 等 Host provenance key 作为语义主体。
- 修改 compactor JSON parsing / accept barrier：LLM 输出引用 prompt-local labels，Host 解析后映射为 canonical accepted evidence refs / source refs，再进入 `CompactionCandidate` 与 `CONTEXT_COMPACTED`。
- 修改 Context Governance proactive / reactive request 构造，使用 selected segment 和 material pack，不再从 Session 起点读取。
- 实现 compaction memory snapshot cursor 校验：material pack build 前缺失 / 滞后 / 损坏时先 catch-up / rebuild / inline delta repair；失败 fail closed，不把 lag 当 Run recovery。
- 实现 reactive multi-pass：同一 operation 内分段处理过大的 material pack 或 evidence block，中间 output 仅为 transient artifact，最终一次性提交 merged compacted event 或 failed event。
- 修改 memory projection / RunInputBuilder bounded selection，落实 V1 consolidation owner、bounded evidence-backed facts working set 与 bounded episode summaries。
- 更新 focused Host tests、public compact smoke、README trigger 文档。

### 3.2 不做

- 不修改 Engine Agent loop、Runner provider contract、Engine context overflow event contract。
- 不修改 Fins、真实财报工具实现、财报文档仓储、Tool provider 业务语义。
- 不修改 ConfigLoader / ScenePrepare schema。
- 不修改 Service / UI workflow。
- 不修改 Host public handle 方法名、`open_host(options)` 字段名、`SubmitFollowupRequest` public 字段名。
- 不新增 public memory edit / reset / forget API。
- 不实现 cross-session long-term retrieval、向量索引、投资研究知识库。
- 不把 assistant final answer、episode summary、用户输入、raw recent turns 或 working assumption 自动升级为 `evidence_backed_fact`。
- 不通过 `extra payload`、`Any`、`object`、lazy glue seam、callback / factory escape hatch 绕开 typed contract。
- 不让 Host import business tools，不让 Engine / Fins 理解 Host memory / context governance。
- 不保留旧 CompactionRequest 字段的兼容 wrapper / re-export；按全新设计修改 tests。

## 4. 分层与编码护栏

- 依赖方向保持 `UI -> Service -> Host -> Engine`。
- `dayu.host` 不得 import `dayu.service` / `dayu.ui` / `dayu.fins` / 具体业务工具模块。
- Host 可在既有 LocalProxy / LLM compaction typed port 边界依赖 Engine public contracts，但不得要求 Engine 理解 material pack、memory snapshot、Host provenance 或 semantic repair。
- ToolRuntime 仍只负责 accepted tool result / truncation / fetch_more / duplicate governance；fact extraction 属于 Host-governed compactor。
- 所有新增 / 修改函数必须有完整中文 docstring，至少包含参数、返回值、异常。
- 所有新增签名必须严格类型化，禁止 `Any`、`object`、无类型参数、无类型返回值和裸容器。
- 使用 `hasattr` / `getattr` 必须先证明 typed contract 无法表达；默认不得使用。
- 禁止魔法数字和魔法字符串；新增限制值必须是模块级私有常量，事件 / JSON schema 字段名可使用模块级常量或 schema 内字面量。

## 5. Public Surface 禁止修改清单

Implementation Agent 不得修改以下 public surface：

- `dayu.host.api.Host` public method shape。
- `OpenHostOptions` 字段名、字段数量与字段语义。
- `SubmitFollowupRequest` 字段名、字段数量与字段语义。
- `open_host(options)` 用户可见入口。
- Engine public contracts 与 Engine event schema。
- ConfigLoader / ScenePrepare public schema。
- Fins storage / tools public contract。

若实现某个 slice 似乎必须修改上述 surface，立即停止并报告 Controller，不能自行扩 scope。

## 6. Implementation Decisions

### 6.1 CompactionRequest shape

采用 material-pack-oriented contract，替换当前以 `input_event_refs`、`accepted_evidence_envelopes`、`compact_raw_context_items` 为 LLM prompt 主体的形状。

新增或重构在 `dayu/host/compaction.py` 中的 typed contracts：

- `CompactMaterialSection`：`STABLE_INPUT`、`HISTORY_INPUT`、`EVIDENCE_INPUT`、`CURRENT_INPUT_ANCHOR`。
- `CompactMaterialBlockKind`：`PINNED_STATE`、`EVIDENCE_BACKED_FACT`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`EPISODE_SUMMARY`、`ACCEPTED_TOOL_EVIDENCE`、`CURRENT_INPUT_ANCHOR`。
- `PromptLocalMaterialLabel` 可保留为 `str` type alias，但构造必须通过私有 helper，格式由模块级常量控制。
- `CompactMaterialBlock`：包含 prompt-local `block_label`、section、kind、bounded readable text、size units、source labels、canonical source refs 内部字段。
- `CompactEvidenceBlock`：包含 prompt-local evidence label、readable tool name、readable query text、raw result text 或分段 text、readable source / locator text。
- `CurrentInputAnchor`：包含 prompt-local label、bounded anchor text、truncated flag、source refs 内部映射；digest 只进入 internal mapping / artifact metadata，不作为 LLM 主要语义文本。
- `PromptLocalProvenanceEntry`：canonical provenance entry 的唯一形状；包含 prompt-local label、section、kind、canonical source refs、source EventLog refs、content digest、accepted evidence id（仅 evidence entry 必填）、tool result / tool call event refs（仅 evidence entry 必填）、payload / artifact refs、source locator refs、chunk parent label 与 chunk ordinal。非 evidence entry 的 evidence-only 字段必须为空，不能用 untyped bag 承载。
- `PromptLocalEvidenceMap`：`dict[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]` 的 evidence-only typed view，key 只能是 `E` section label 或 evidence chunk label；每个 entry 必须有 accepted evidence id、tool result event ref、tool call event ref 与 digest-checked payload / artifact ref。它不是第二份真源，只能从 `CompactMaterialPack.provenance_map` 派生或与其中同 key entry 共用同一 immutable value。
- `CompactMaterialPack`：包含 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor` 与 internal `provenance_map`；`provenance_map` 是所有 prompt-local labels 到 `PromptLocalProvenanceEntry` 的完整映射，`PromptLocalEvidenceMap` 是其中 evidence labels 的受限子集。
- `CompactSegmentSelection`：包含 selected block ids、excluded protected ids、trigger source、input cursor、memory snapshot cursor、policy digest 和 deterministic reason codes。
- `CompactionRequest`：保留 operation / trigger / session / run / attempt / execution / budget 字段，但 LLM-facing input 改为 `material_pack` 与 `segment_selection`。

删除或降级为内部迁移对象的旧字段：

- `CurrentMessageSummary` 不再作为 LLM prompt section；由 `CurrentInputAnchor` 替代。
- `CompactRawContextItem` 不再混合承载 user / assistant / tool result；分拆到 history material block 与 evidence material block。
- `accepted_evidence_envelopes` 不再进入 LLM prompt；仅进入 internal provenance map / accept barrier。
- `input_event_refs` 不再作为 LLM prompt 主体；只作为 internal mapping / artifact / quality gate 输入。

### 6.2 Prompt-local label 与 canonical provenance

LLM-facing prompt 只允许引用 prompt-local labels：

- current input anchor label：`C1`。
- history labels：`H1`、`H2`。
- evidence labels：`E1`、`E1.1`、`E1.2`。
- stable labels：`S1`、`S2`。

Prompt-local label 生成 owner 固定为 `dayu/host/compact_material.py` 的模块级私有 helper，不得在 parser、prompt renderer 或 tests 中重复手写规则。若最终文件名选择 `dayu/host/compaction_material.py`，同一 owner 规则随文件名迁移。

Label 生成算法：

- section prefix 使用共享常量映射：`CURRENT_INPUT_ANCHOR -> C`、`HISTORY_INPUT -> H`、`EVIDENCE_INPUT -> E`、`STABLE_INPUT -> S`。
- 普通 block label 格式为 `{section_prefix}{ordinal}`；`ordinal` 从 `1` 开始，在同一 section 内按 deterministic material block order 递增。
- evidence chunk label 格式为 `{section_prefix}{ordinal}.{chunk_ordinal}`；`chunk_ordinal` 从 `1` 开始，只在单个 evidence block 被拆分时使用，所有 chunks 共享同一个 canonical accepted evidence id。
- current input anchor V1 只能生成 `C1`；若实现需要第二个 current anchor，必须停下报告 Controller。
- parser validation 必须复用同一组模块级共享常量和私有 parse / validate helper 校验 label 格式、section membership、chunk parent 与 ordinal，不得另写不一致的 regex / magic string。

Canonical provenance map 内部保存：

```text
E1 -> TOOL_RESULT_ACCEPTED event -> TOOL_CALL_REQUESTED event -> payload / artifact / source locator refs
H1 -> USER_INPUT_ACCEPTED or RUN_SUCCEEDED event
C1 -> current USER_INPUT_ACCEPTED event
S1 -> memory snapshot item / inline delta repair source
```

LLM output schema 中的 `evidence_refs`、`source_refs`、`preservation_refs` 使用 prompt-local labels。`LLMContextCompactor` 解析后必须把这些 labels 映射为当前代码内部使用的 canonical accepted evidence refs / input refs，再构造 `CompactionCandidate`。引用未知 label、跨 section label、重复 canonical content 或 label 指向非本次 material pack 时 fail closed。

### 6.3 Segment selection 确定性规则

新增 `dayu/host/compact_material.py`，作为 material list、segment selection 和 material pack builder 的 Host internal owner。若 reviewer 认为文件名不合适，可放入 `dayu/host/compaction_material.py`，但不得塞进 `llm_compaction.py`。

确定性输入：

- trigger source。
- input cursor：当前 ordinary input material list 的最大 EventLog cursor。
- memory snapshot cursor。
- context / memory policy digest。
- ordinary input material list 或 reactive overflow material list。

Material list 排序固定为：

```text
(event_sequence, event_sub_index, block_kind_order, stable_block_id)
```

`block_kind_order` 是模块级常量，顺序为 stable、history、evidence、current anchor。没有 event sequence 的 stable memory block 使用 memory snapshot cursor 与 stable block ordinal 生成稳定排序键。

Proactive selection：

- 上界：当前待 dispatch ordinary input 中，排除 `current_input_anchor`、protected recent raw turns floor 和 stable input 后的 history / evidence material。
- 下界：从最旧且尚未被 accepted compact output 充分代表的 material block 开始。
- “充分代表”精确定义：一个 history / evidence block 的 canonical source refs 全部被已提交 `CONTEXT_COMPACTED` 的 `summarized_ranges` / `dropped_ranges` 覆盖，或对应 accepted evidence 已有通过 memory projection materialized 的 evidence-backed fact 且该 fact extraction event sequence 不早于该 evidence block event sequence。满足则不重新展开 raw content。
- 选择策略：按排序键选择 older prefix，直到估算的 post-compact ordinary input 可低于 soft threshold；若无法证明，至少选择最旧的一个非 protected block；若 material pack 仍超过 compactor hard budget，进入 bounded repair / failure，不盲打 provider。

Reactive selection：

- 输入来自冻结的 overflow ordinary input material list，不从当前 EventLog 重新扫描生成另一套语义列表。
- 优先选择 older prefix；suffix 中 current input anchor 与 protected recent raw turns 必须保留到后续 pass 或 recovery dispatch。
- 若完整 selected segment 超过 compactor budget，按 material block 分段 multi-pass。
- 若单个 evidence block 超过 compactor budget，在同一 canonical evidence provenance 下按 deterministic chunk size 分为 `E1.1`、`E1.2` 等 evidence-block 内部分段；chunk size 用模块级常量和 policy budget 派生，禁止写魔法数字。

输出必须包含：

- selected block ids。
- 每个 block 的 section owner。
- excluded reason：`protected_current_input`、`protected_recent_raw_floor`、`already_represented`、`budget_limit`、`not_in_segment`。
- deterministic digest，供 tests / trace / audit 断言。

### 6.4 Material pack section 一对一映射

Material pack builder 必须强制同一 canonical content 只能进入一个 LLM-facing section：

- `stable_input`：只来自 memory snapshot bounded stable layer view 与 policy 允许的 inline delta repair view。
- `history_input`：只渲染 user / assistant continuity、non-evidence raw turns、segment-generated episode summaries 和 policy-bounded recent episode summaries。
- `evidence_input`：只渲染 accepted tool evidence blocks；raw result 内容来自 digest-checked payload / raw result descriptor。
- `current_input_anchor`：只来自当前 `USER_INPUT_ACCEPTED` 的 bounded anchor；同一 current payload 不得再作为 history raw turn 渲染。

Builder 必须有重复内容防线：以 canonical source ref set + content digest 构造 internal dedupe key；同一 key 进入第二个 section 时抛出 typed Host durable / compaction error。

### 6.5 Raw evidence 读取路径

`dayu/host/compaction_evidence.py` 改为 evidence material collector，不再按 Session 起点 EventLog range 返回混合 raw context。

读取路径固定为：

```text
selected evidence material block
  -> TOOL_RESULT_ACCEPTED canonical fact
  -> event payload / payload descriptor
  -> digest-checked raw_tool_outcome or raw result descriptor
  -> readable evidence block text
```

Accepted evidence envelope 只提供 canonical evidence id、tool/query/provenance/source locator metadata，不提供 claim 语义内容，不提供 `result_preview`。若 raw payload 缺失、descriptor digest 不匹配、payload 不是 JSON object 或 raw result 无法形成 bounded readable block，fail closed 并记录 diagnostic；不得回退到 envelope preview、digest、artifact ref 或 EventLog id。

### 6.6 Snapshot cursor 校验

Material pack build 前必须校验 memory snapshot cursor：

- `stable_input` 需要的 memory snapshot cursor 必须覆盖 selected segment 所需 EventLog cursor。
- cursor 滞后且 delta 在 `MemoryProjectionPolicy.max_lag_events_for_inline_delta` 内时，可用现有 inline delta repair view，并记录 diagnostic。
- cursor 缺失、损坏或 lag 超过 policy 时，dispatch / ingest owner 必须先调用 memory projection catch-up / rebuild。
- catch-up / rebuild 失败：proactive path 写 compaction failure / pre-dispatch failure，Run 进入 `FAILED`，不得创建 Attempt；reactive path 按 compact failure 收口 Run 为 `FAILED`，不得进入 `LOST`。
- memory projection lag 不得把 Run 推入 `RECOVERING`；`RECOVERING` 只属于 reactive Engine overflow recovery。

### 6.7 Reactive multi-pass durable 语义

`run_compaction_operation(...)` 需要支持 multi-pass operation：

- 一个 `CONTEXT_COMPACTION_REQUESTED` 对应一个 operation id。
- multi-pass 不追加新的 requested event，不单独消耗 `max_reactive_compactions_per_run`。
- 每个 pass 的外部 LLM proposal 消耗 `max_compaction_attempts_per_operation` 总预算。
- pass output 只写 transient operation artifact / diagnostic artifact，不写 `CONTEXT_COMPACTED`。
- 所有 required passes 通过 quality / budget gate 后，Host merge 成一个 `CompactionCandidate` 并只提交一个 `CONTEXT_COMPACTED`。
- 任一 pass 失败且 repair budget 耗尽，整个 operation 提交一个 `CONTEXT_COMPACTION_FAILED`。
- memory projection 不得消费中间 pass output。

### 6.8 V1 consolidation owner

V1 consolidation 不新增 retention-intent schema，不要求 compactor 输出 `memory_retention_candidate`。Owner 固定为：

- memory projection policy：决定 materialized pinned state、bounded evidence-backed fact snapshot、working assumptions、open questions、episode summaries、minimum preserve items 的可见 working set。
- RunInputBuilder / compactor input bounded selection：决定 ordinary Run 与 compactor 实际看到的 bounded subset。

V1 规则：

- `pinned_state` 物化当前值，不渲染 patch log。
- `working_assumptions` / `open_questions` 按 normalized text 去重；accepted pinned patch replace / clear 直接物化当前状态；超出 policy top-K / size budget 时保留较新且与 current goal / subject 相关的项。
- `evidence_backed_facts` durable projection 可保存历史项，但 snapshot / RunInputBuilder / compactor input 只选择 bounded working set。排序优先级：pinned subject match、current goal keyword overlap、recent user reference、newer extraction event sequence、policy top-K。
- `episode summaries` 进入 history pool 后只保留 segment-generated summary 与 policy-bounded recent summaries；更旧 summaries 只保留 artifact / EventLog refs，不渲染全文。
- `minimum_preserve_items` 是短寿命 continuity；若 source refs 已被 stable fact 或 episode summary 覆盖，下一次 snapshot selection 应降级或排除。

## 7. 受影响文件与模块

Implementation slices 可修改以下文件或同目录紧邻测试。超出列表必须先停下报告 Controller。

Host source：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py` 或 `dayu/host/compaction_material.py`（新增）
- `dayu/host/compaction_evidence.py`
- `dayu/host/evidence.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/context_budget.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/memory_repair.py`
- `dayu/host/payload_resolution.py`（仅当需要复用 digest-checked raw payload helper）

Prompt asset：

- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`

测试：

- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/fake_compaction.py`
- 必要时新增 `tests/host/test_compact_material.py`

按触发规则判断 README：

- `dayu/host/README.md`
- `tests/README.md`
- `dayu/config/README.md` 仅当 prompt asset 职责或配置入口说明实际变化时更新；单纯 JSON schema 不变则不改。
- `dayu/README.md` 仅当稳定术语或分层边界变化时更新；本 phase 预期不需要。

禁止修改：

- `dayu/engine/**`
- `dayu/fins/**`
- `dayu/runtime/config_loader.py`
- ScenePrepare owner 文件
- `dayu/host/api.py` public request / handle fields
- `dayu/host/open_host.py` public options fields
- `dayu/service/**`，除非 Controller 后续明确授权 Service assembly 改动。

## 8. 实施切片

### 8.0 切片依赖图

实施必须按以下依赖图推进；除明确标注可并行的路径外，不得跳过依赖 slice 直接落地后续 slice。

```text
Slice 1 Material Pack 契约删除边界 / Direct Consumers Migration
  -> Slice 2 Segment Selection / Material Pack Builder
      -> Slice 3 Raw Evidence Reader / Prompt-local Evidence Map Hardening
          -> Slice 4 LLM JSON Schema / Parser / Accept Barrier Hardening
              -> Slice 5 Context Governance Proactive / Reactive Wiring
  -> Slice 6 Memory Projection Consolidation / RunInputBuilder Rendering

Slice 7 Public Smoke / README Sync / Final Verification depends on Slice 1-6.
```

依赖说明：

- Slice 1 是删除旧 `CompactionRequest` 字段的最小 compile-safe boundary，必须在同一 accepted checkpoint 内迁移所有当前直接生产构造 / 消费点：`dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/compaction_evidence.py`，以及原 Slice 1 已授权的 contract / event / artifact / tests。Slice 1 完成后，生产代码和 Slice 1 测试中不得再引用 `CurrentMessageSummary`、`CompactRawContextItem`、`input_event_refs`、`accepted_evidence_envelopes`、`compact_raw_context_items` 作为 `CompactionRequest` 字段。
- Slice 2 依赖 Slice 1 的 `CompactMaterialPack`、`CompactSegmentSelection`、`PromptLocalProvenanceEntry`、prompt-local label helper 与 compile-safe direct consumer migration；Slice 2 负责把 Slice 1 的初始 material construction 收敛为完整 deterministic segment selection / builder。
- Slice 3 依赖 Slice 2 的 selected evidence material block 与 prompt-local label helper，并强化 digest-checked raw evidence path、large evidence chunking 与 `PromptLocalEvidenceMap` evidence-only view；不得恢复 accepted envelope preview 或 old raw context carrier。
- Slice 4 依赖 Slice 1-3 的 material pack、provenance map、evidence map 与 label parse / validate helper；Slice 4 只做 schema / parser / accept barrier 深化，不再承担旧 request 字段删除。
- Slice 5 依赖 Slice 1-4 的 request shape、builder、raw evidence path、parser 和 quality gate；Slice 5 只做 proactive / reactive governance 接线与 multi-pass durable 语义，不再承担 `dispatch.py` / `engine_ingest.py` 的旧字段构造迁移。
- Slice 6 只依赖 Slice 1-2 的 contracts / material block view，可在 Slice 3-5 之后实施以降低 review 分叉。
- Slice 7 只能在前六个 slice 验证通过后执行。

### Slice 1. Material Pack 契约删除边界与 Direct Consumers Migration

目标：建立 material-pack-oriented typed contracts，并在同一 compile-safe checkpoint 内删除旧 LLM-facing ledger / envelope prompt 契约及其所有当前直接生产构造 / 消费点。

依赖：无。Slice 1 是后续所有 slice 的 contract root，也是删除旧 `CompactionRequest` 字段的唯一首个实现边界。若实施者发现删除旧字段需要修改本 slice 未列出的生产直接消费者，必须停下报告 Controller；不得通过 deprecated alias、compat wrapper、old-field default、test-only compatibility 或派生旧属性继续推进。

允许修改文件：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py` 或 `dayu/host/compaction_material.py`（新增，承载 label helper、初始 material pack construction 与 one-section guard；Slice 2 在同一 owner 内补齐完整 deterministic builder）
- `dayu/host/compaction_evidence.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`（仅限消除旧 request shape 传递与 fake / operation fixture 的 compile break）
- `dayu/host/context_events.py`
- `dayu/host/compact_artifact.py`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`（仅限把旧 request refs 文案改为 prompt-local material labels；不得改 ConfigLoader / ScenePrepare schema）
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/fake_compaction.py`

具体修改：

- 新增 §6.1 中列出的 dataclass / enum / type alias。
- 删除 `CompactionRequest` 上的旧字段：`input_event_refs`、`current_message_summary`、`accepted_evidence_envelopes`、`compact_raw_context_items`。删除 `CurrentMessageSummary` 与 `CompactRawContextItem` 作为 public / exported Host compaction contract 的使用；若部分同名私有迁移对象看似必要，必须改名并证明不进入 request / prompt / tests compatibility boundary。
- `CompactionRequest.to_json()` 保留 internal artifact 需要的 canonical refs，但 JSON 中必须区分 `material_pack` 与 `provenance_map`。
- `CompactionRequest.llm_material_json()` 或等价 helper 只返回 LLM-facing material pack，不含 EventLog ids、payload refs、digests、cursor、accepted envelope metadata。
- 新增或迁入 prompt-local label helper，所有 direct consumers 只能通过 helper 构造 / 校验 `S*`、`H*`、`E*`、`C1` labels；parser、prompt renderer、tests 不得手写另一套 label 规则。
- 新增 Slice 1 初始 material pack construction：从当前已可获得的 run input / accepted evidence / current input 信息构造 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor` 的 typed empty-or-bounded sections。该 construction 只为完成旧 request 删除和直接消费者迁移，不得引入 public API，也不得读取或渲染 Session 起点 EventLog ledger wrapper；完整 deterministic segment selection、already-represented 判断和 snapshot cursor repair 在 Slice 2 落地。
- `dayu/host/compaction_evidence.py` 从返回 `accepted_evidence_envelopes` + `compact_raw_context_items` 的旧 request helper，迁移为 evidence / history material collector：输出 prompt-local material blocks 与 internal provenance entries。Slice 1 不允许从 accepted envelope 读取或生成 `result_preview`，也不允许把 payload ref、digest、event id、cursor 作为 LLM semantic text。
- `dayu/host/dispatch.py` 和 `dayu/host/engine_ingest.py` 必须在本 slice 改为构造新 `CompactionRequest(material_pack=..., segment_selection=...)`；不得继续传入或保存旧字段，也不得通过 pending record / fixture 暗藏旧字段。
- `dayu/host/llm_compaction.py` 必须在本 slice 改为渲染 material pack sections，并把 parser / repair / preservation evidence 中对 request old refs 的校验改为 prompt-local label -> canonical provenance map 校验；不得继续渲染 `accepted_evidence_envelopes:`、`compact_raw_context:`、`input_event_refs:`、`current_user_input_ref:` 或 raw Host provenance key。
- `dayu/host/context_governance.py` 必须在本 slice 改为使用 material labels 与 provenance map 做 preservation / fact / source validation；不得读取 `request.current_message_summary` 或 `request.input_event_refs`。
- `dayu/config/prompts/scenes/conversation_compaction_user.md` 必须在本 slice 把输出 schema 文案从 `input_event_refs` / `accepted_evidence_refs` 改为 prompt-local `material_labels` / `evidence_labels`。这只是 prompt asset 同步，不修改 ConfigLoader / ScenePrepare schema。
- `CompactionCandidate` 可继续承载 canonical refs，但新增 parser-side label mapping 注释和 docstring，说明 LLM 不直接生成 canonical refs。
- `build_context_compacted_payload(...)` 增加 accepted evidence label mapping refs 或 material pack digest refs；不把 raw material pack 全量塞入 EventLog payload。
- `CompactArtifactWriteRequest` artifact 写入同时保存 material pack digest、segment selection digest、transient pass diagnostics refs。
- 删除旧 old-key validator 分支中仅服务兼容的字段接受逻辑；测试改为 fail closed。
- Slice 1 必须同步迁移所有现有直接构造或断言旧 `CompactionRequest` 字段的测试引用，包括 `input_event_refs`、`accepted_evidence_envelopes`、`compact_raw_context_items`、旧 `CurrentMessageSummary` prompt section、旧 `CompactRawContextItem` 混合载体、旧 prompt asset refs 与旧 result preview / tool fact refs。不得保留 deprecated alias、compat wrapper、old-field default 或 test-only 兼容路径。
- 已知需要在 Slice 1 一并迁移的现有测试边界包括 contract、LLM prompt/parser、compaction operation、dispatch scheduler、engine ingest mapping、compact artifact store、context compact event、memory projection、run input builder 与 fake compactor。若实施时 `rg` 发现同一旧字段还存在于 §7 主清单内其他测试文件，必须在 Slice 1 同步迁移；若出现在 §7 外文件，立即停下报告 Controller。

测试：

- `test_compaction_request_llm_material_excludes_host_provenance_keys`：断言 LLM material JSON / prompt block 不含 `event_id`、`payload_ref`、`payload_digest`、`outcome_digest`、`input_event_refs`、`accepted_evidence_envelopes`。
- `test_compaction_request_material_pack_has_one_section_per_block`：同一 canonical source key 进入两个 section 时构造失败。
- `test_slice1_direct_consumers_construct_only_material_pack_request`：覆盖 `dispatch.py` / `engine_ingest.py` 的 request construction path，断言生成的新 request 只含 `material_pack` 与 `segment_selection`，不含 old fields。
- `test_context_governance_validates_prompt_local_labels_not_input_event_refs`：覆盖 quality / preservation validation，不再读取 old request refs。
- `test_llm_prompt_asset_uses_material_labels_not_input_event_refs`：断言 prompt asset 不要求 `input_event_refs`、`accepted_evidence_refs` 或 `preserved_input_event_refs`。
- `test_context_compacted_payload_records_mapping_refs_not_raw_prompt`：EventLog payload 只记录 mapping / artifact refs，不记录完整 prompt。
- `test_old_result_preview_or_old_tool_fact_keys_fail_closed`：旧 `result_preview`、`accepted_tool_fact_refs`、`verified_fact_refs` 不被兼容接受。
- `test_no_old_compaction_request_fields_remain_in_slice1_boundary`：用 focused contract / import assertions 覆盖 `CompactionRequest`、fake compactor 与 direct production consumers，防止旧字段通过 alias / default / derived property 回流。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py -q
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
python -m pyright dayu/host/compaction.py dayu/host/compact_material.py dayu/host/compaction_evidence.py dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_events.py dayu/host/compact_artifact.py tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/fake_compaction.py
rg -n "accepted_evidence_envelopes|compact_raw_context_items|current_message_summary|CurrentMessageSummary|CompactRawContextItem|compact_raw_context|accepted_evidence_refs|preserved_input_event_refs" dayu/host/compaction.py dayu/host/compact_material.py dayu/host/compaction_evidence.py dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/config/prompts/scenes/conversation_compaction_user.md
```

`rg` 命令必须返回 no matches；若实现选择 `dayu/host/compaction_material.py` 作为 owner，则上述 `dayu/host/compact_material.py` 路径统一替换为实际文件名。

停止条件：

- 需要修改 Host public API / `OpenHostOptions` / `SubmitFollowupRequest`。
- 需要兼容旧 request shape。
- 需要把 untyped JSON bag 作为 contract 主体。
- 发现 §7 外生产文件仍直接构造 / 消费旧 `CompactionRequest` 字段。
- 为了让 Slice 1 编译通过而需要恢复 EventLog ledger dump、`result_preview`、Host provenance key 作为 LLM semantic input，或需要新增 public API。

### Slice 2. 确定性 Segment Selection 与 Material Pack Builder

目标：把 Slice 1 的初始 material construction 收敛为完整 compact material list、deterministic segment selection、one-to-one section mapping、snapshot cursor validation entrypoint。

依赖：Slice 1 的 material-pack-oriented typed contracts、`PromptLocalProvenanceEntry`、`CompactionRequest` 新形状与旧字段测试迁移完成。

允许修改文件：

- `dayu/host/compact_material.py` 或 `dayu/host/compaction_material.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/memory_repair.py`
- `dayu/host/compaction.py`
- `tests/host/test_compact_material.py`（新增）
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`

具体修改：

- 新增 `RunInputMaterialBlock` internal typed view，RunInputBuilder 和 compact builder 共用同一 ordinary input material list source，避免 ordinary input 与 compactor input 两套去重语义漂移。
- 实现 `select_compact_segment(...)`，按 §6.3 deterministic rules 输出 `CompactSegmentSelection`。
- 实现 `build_compact_material_pack(...)`，从 selected segment、memory snapshot view、inline delta repair view、accepted evidence collector 和 current input 构造 material pack。
- 当前输入 anchor 规则：如果当前 display text 小于等于 `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS`，anchor text 使用完整 normalized text；否则使用 bounded prefix text 和 truncated marker，full digest 只进入 internal mapping。
- 实现 duplicate section owner guard。
- 实现 memory snapshot cursor check helper：返回 ready snapshot、inline repair view 或 typed repair-required error。
- `RunInputBuilder` 保持现有 public behavior，但内部 material block construction 需要可被 tests 验证；不得把 material builder 变成 public API。

测试：

- `test_segment_selection_is_deterministic_for_same_inputs`：相同 cursor / snapshot / policy / material list 输出相同 block ids 和 digest。
- `test_proactive_segment_excludes_current_anchor_and_recent_raw_floor`。
- `test_reactive_segment_uses_frozen_overflow_material_list`。
- `test_already_represented_blocks_are_not_reexpanded`。
- `test_material_pack_one_to_one_section_mapping_rejects_duplicate_content`。
- `test_current_input_anchor_does_not_duplicate_history_raw_turn`。
- `test_snapshot_cursor_lag_requires_catchup_or_inline_delta`。
- `test_snapshot_lag_failure_does_not_request_run_recovery`。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
```

停止条件：

- material block construction 需要修改 Engine。
- segment selection cannot be deterministic without new public policy fields.
- current input anchor 需要在 dispatch 前调用 LLM summarization。

### Slice 3. Raw Evidence Reader 与 Prompt-local Label Mapping Hardening

目标：在 Slice 1 已删除旧 request carrier 的基础上，补齐 digest-checked raw evidence reader、large evidence chunking 和 evidence-only prompt-local provenance view。

依赖：Slice 1 的 `PromptLocalEvidenceMap` / `provenance_map` contract，Slice 2 的 selected evidence material block、label helper 与 material pack builder。

允许修改文件：

- `dayu/host/compaction_evidence.py`
- `dayu/host/evidence.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/compact_material.py` 或 `dayu/host/compaction_material.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_compact_material.py`

具体修改：

- 将 Slice 1 的初始 evidence material collector 收敛为按 selected evidence block refs 读取，而不是 `start_event_sequence=1` 到 current input。
- raw evidence text 必须来自 `TOOL_RESULT_ACCEPTED` canonical fact 引用的 payload / descriptor，并校验 digest。
- accepted evidence envelope 只用于建立 canonical mapping 和 readable query / source locator metadata，不再作为 result content 或 LLM semantic body。
- 不读取、不生成、不回退 `result_preview`。
- 单 evidence block 超预算时，按 deterministic evidence chunks 输出 `E1.1` / `E1.2`，internal mapping 指向同一个 canonical evidence id，并保留 chunk ordinal。
- 建立 `PromptLocalEvidenceMap`：LLM label 到 canonical accepted evidence id、tool result event、tool call event、payload / artifact refs。

测试：

- `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview`。
- `test_missing_or_digest_mismatch_raw_evidence_fails_closed`。
- `test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence`。
- `test_single_large_evidence_block_is_chunked_under_same_provenance`。
- `test_no_result_preview_field_is_read_or_rendered`。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_operation.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py -q
python -m pyright dayu/host/compaction_evidence.py dayu/host/evidence.py dayu/host/payload_resolution.py dayu/host/compact_material.py tests/host/test_compaction_operation.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py
```

停止条件：

- raw evidence can only be recovered by importing Fins or concrete business tools.
- implementation 需要在 Host 内解析财报业务 locator semantics。
- descriptor path lacks enough data to reconstruct raw accepted evidence; report Controller for design/storage裁决。

### Slice 4. LLM Compactor JSON Schema 与 Accept Barrier Hardening

目标：在 Slice 1 已迁移 prompt renderer / direct parser references 的基础上，完整收紧 LLM JSON schema、parser label mapping 与 quality gate 越权拒绝规则。

依赖：Slice 1 的 request / candidate contract，Slice 2 的 material pack builder，Slice 3 的 raw evidence path、`PromptLocalEvidenceMap` 与 label parse / validate helper。

允许修改文件：

- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`

具体修改：

- `_compaction_request_prompt_block(...)` 必须保持只渲染四个 material pack sections；若 Slice 2 / 3 新增 block kind 或 chunk label，prompt renderer 只能消费 material pack typed view，不得读取 EventLog / envelope helper。
- prompt 中继续不得出现 `accepted_evidence_envelopes:`、`compact_raw_context:`、`input_event_refs:`、payload digest、event id、cursor、policy snapshot 等 Host ledger字段。
- JSON schema 要求 LLM 输出 `episode_summary_candidate`、`pinned_state_patch_candidate`、`evidence_backed_fact_candidates`、`minimum_preserve_item_candidates`、`preservation_evidence`，其中 refs 使用 prompt-local labels。
- parser 映射 labels 到 canonical refs 后再构造 `CompactionCandidate`。
- quality checker 新增或调整检查：fact candidate 必须引用 evidence labels；minimum preserve source refs 必须引用 material labels；episode summary 不得把 evidence label 直接升级成 fact ref。
- `finish_reason=length`、非 final answer、空 summary、未知 label、label section mismatch、fact 无 evidence label、source label 不在 material pack 均 fail closed。

测试：

- `test_prompt_renders_material_pack_without_ledger_dump`。
- `test_prompt_does_not_render_accepted_evidence_envelope_metadata`。
- `test_parser_maps_prompt_local_evidence_label_to_canonical_ref`。
- `test_parser_rejects_unknown_or_cross_section_labels`。
- `test_fact_candidate_without_evidence_label_rejected`。
- `test_minimum_preserve_source_refs_must_be_material_labels`。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q
python -m pyright dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/compaction.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py
```

停止条件：

- prompt schema change 需要 ConfigLoader / ScenePrepare schema migration。
- parser cannot map labels without exposing canonical Host refs to LLM.

### Slice 5. Proactive / Reactive Context Governance 接线

目标：在 dispatch / engine ingest 已使用 material pack request 的前提下，完成 proactive / reactive governance 接线与 reactive multi-pass single-operation durable semantics。

依赖：Slice 1-4 全部完成；特别依赖 builder output、evidence map、prompt parser canonical mapping 与 quality gate。

允许修改文件：

- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_budget.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_artifact.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_budget.py`

具体修改：

- Proactive `_maybe_start_compaction...` 保持 Slice 1 的新 request shape，并从 Slice 2 builder 提供的 RunInputBuilder ordinary material list 生成 selected segment 和 material pack；不得恢复 Session 起点 range collector。
- Reactive `_start_reactive_context_recovery(...)` 冻结 overflow ordinary input material list；pending record 保存冻结 list digest / refs。
- `_reactive_compaction_request(...)` 使用冻结 material list 和 selected segment 构造 request；不得恢复 old-field pending record 或 old request constructor。
- `run_compaction_operation(...)` 支持 pass queue：单 pass 复用现有语义；multi-pass 依次调用 compactor，所有 pass 成功后 merge candidate。
- attempt budget 是 operation 总 LLM proposal 上限，不是每 pass 重置。
- proactive compact 后估算仍可作为 hard threshold gate；reactive compact 后不以估算阻断 recovery dispatch。
- stale / cancelled / session closed / execution replaced / cursor mismatch 时丢弃 proposal，不写 `CONTEXT_COMPACTED`。
- reactive failure 写一个 final failed event，Run `FAILED`；不得 `LOST`，不得无限 retry。

测试：

- `test_proactive_compaction_uses_selected_material_not_session_start_range`。
- `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`。
- `test_reactive_freezes_overflow_material_list_before_compaction`。
- `test_reactive_multi_pass_commits_single_merged_context_compacted`。
- `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event`。
- `test_reactive_passes_share_operation_attempt_budget`。
- `test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run`。
- `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py -q
python -m pyright dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_budget.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py
```

停止条件：

- reactive multi-pass 需要修改 Engine runner retry。
- failure handling 需要新增 Run / Attempt state。
- operation transient artifact 需要超出现有 artifact store 语义的 durable schema change。

### Slice 6. Memory Projection Consolidation 与 RunInputBuilder Rendering

目标：落实 Conversation Memory V1 consolidation owner，确保 compact 后 facts / minimum preserve / summaries bounded 注入。

依赖：Slice 1 的 compact output / provenance contract 与 Slice 2 的 shared material block view。为降低 review 分叉，默认在 Slice 5 后实施。

允许修改文件：

- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/memory_repair.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`

具体修改：

- `project_conversation_memory_event(...)` 对 accepted `CONTEXT_COMPACTED` 的处理按 §6.8 物化 current pinned state、evidence-backed facts、minimum preserve items、episode summaries。
- evidence-backed facts dedupe key：normalized `claim_text` + sorted canonical evidence refs + evidence kind；重复时保留较新 extraction event sequence，并记录 superseded diagnostic。
- snapshot selection 使用 policy bounded working set；不把 durable historical all facts 全量渲染给 RunInputBuilder 或 compactor。
- episode summaries selection 只保留 policy-bounded recent summaries；older summary 只保留 refs / diagnostics。
- RunInputBuilder memory rendering 顺序保持 design §24：目标 / 约束、主体 / 口径、evidence-backed facts、open questions / assumptions、recent raw turns、episode summaries。
- stable fact block 必须包含 `claim_text` 与 `evidence_refs`；不得退化为 digest-only。
- minimum preserve item 在 continuity block 中渲染 label / text / source refs / preserve reason，不进入 stable facts。

测试：

- `test_memory_projection_materializes_pinned_state_current_value_not_patch_log`。
- `test_evidence_backed_fact_working_set_is_bounded_and_deterministic`。
- `test_episode_summaries_are_policy_bounded_not_append_only_rendered`。
- `test_minimum_preserve_expires_when_covered_by_stable_or_summary`。
- `test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only`。
- `test_no_compaction_recent_raw_turns_continuity_still_works`。
- `test_final_answer_user_input_summary_do_not_become_evidence_backed_fact`。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
python -m pyright dayu/host/memory.py dayu/host/run_input.py dayu/host/memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py
```

停止条件：

- bounded working set 需要 Host 内业务特定财务排序。
- memory projection 需要写 EventLog，或 Context Governance 需要直接写 memory snapshot。

### Slice 7. Public Compact Smoke、README 同步与最终验证

目标：用 public path 验证 P12.6 success signals，并同步当前实现文档。

依赖：Slice 1-6 全部完成并通过各自验证。

允许修改文件：

- `tests/host/test_public_compact_smoke.py`
- `tests/host/fake_compaction.py`
- `dayu/host/README.md`
- `tests/README.md`
- `dayu/config/README.md` 仅当 prompt asset 说明过期
- `dayu/README.md` 仅当术语 / 分层说明实际变化

具体修改：

- 添加 P12.6 public smoke：
  - no-compaction recent raw turns continuity。
  - post-compaction evidence-backed fact reuse。
  - 长 user input compact 后下一轮“第二个因素”通过 minimum preserve 解析。
  - 长章节 tool result extraction 不依赖 preview，基于 raw accepted evidence block。
  - 长会话多次 compact 后 memory / compactor input bounded。
  - proactive compact 不因 duplicate prompt 超窗失败。
- fake compactor 使用 material labels 输出 JSON，不生成 canonical Host refs。
- README 只同步当前代码事实，不写未来计划，不写过程状态。

验证：

```bash
source .venv/bin/activate
pytest tests/host/test_public_compact_smoke.py -q
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_compact_smoke.py -q
python -m pyright dayu/ tests/
git diff --check
```

停止条件：

- public smoke 需要真实 provider 网络才能通过；mock / fake compactor path 必须足以覆盖 deterministic success signal，real provider 只可作为 optional smoke。
- README update 需要写尚未实现的未来设计。

## 9. Review Gates

Implementation Agent completion 后必须交付 completion report artifact，Controller 再派 review。

必需 gate：

- Slice implementation review：至少一名 reviewer 检查 code / tests / README 是否满足本 plan。
- Aggregate deepreview：ready-to-open-draft-PR 前至少两份独立 review，优先 AgentMiMo + AgentDS 或 AgentGLM。
- Accepted findings fix / re-review：所有 accepted findings 修复后再进入 readiness。
- Controller adjudication：每个 accepted / rejected / deferred / needs-more-evidence finding 必须说明与 `docs/host/design.md` §1 / §24 / §25 的关系。

Reviewer 必须重点检查：

- 是否仍有 EventLog ledger dump 或 Session 起点 range collector 进入 compactor prompt。
- 是否仍有 `result_preview` 读取或生成。
- 是否把 event id、payload ref、digest、cursor、policy、artifact descriptor 当作 LLM semantic input。
- 是否存在 current input / raw tool result 跨 section 重复渲染。
- segment selection 是否 deterministic。
- snapshot cursor lag 是否被错误映射为 Run recovery。
- reactive multi-pass 是否提交 partial compacted event。
- Host 是否 import business tools / Fins / Service / UI。
- 是否新增 `Any` / `object` / extra payload / lazy seam。

## 10. Completion Report 格式

Implementation Agent 最终报告必须使用以下格式：

```md
## P12.6 Implementation Completion Report

### 摘要
- ...

### 已完成切片
- Slice 1: ...
- Slice 2: ...

### 修改文件
- ...

### 契约 / Schema / 状态机变更
- ...

### 新增或更新测试
- ...

### 验证
- `pytest ...`: pass/fail with key counts
- `python -m pyright dayu/ tests/`: pass/fail
- `git diff --check`: pass/fail

### README 同步
- `dayu/host/README.md`: updated / not needed because ...
- `tests/README.md`: updated / not needed because ...
- other README: updated / not needed because ...

### Plan Requirements Checklist
- deterministic segment selection: done / not done
- one-to-one material pack sections: done / not done
- raw evidence path: done / not done
- snapshot cursor validation: done / not done
- reactive multi-pass single operation: done / not done
- V1 consolidation owner: done / not done
- bounded evidence / episode working set: done / not done
- no ledger dump / result_preview / Host provenance semantic input: done / not done

### 剩余风险
- ...

### 触发的停止条件
- 无 / ...
```

## 11. 风险与 Open Questions

阻塞 open questions：无。

剩余风险：

- 大 session rebuild performance 仍可能需要后续 hardening；本 phase 只要求语义正确、bounded、可测试，不把性能优化作为 blocker。
- Prompt-local label 到 canonical provenance 的 mapping 会扩大 Host internal artifact / diagnostic 面；review 必须确认未把 raw prompt 或敏感 provider payload 写入 EventLog。
- V1 relevance strategy 使用 Host-neutral text overlap / recency / subject refs，不能理解财报业务语义；后续真实财报工具与 retrieval owner 仍需提供更高质量 source locator / retrieval 能力。
- Reactive multi-pass 会消耗有限 LLM proposal budget；预算耗尽 fail closed 是设计选择，不应被实现改成无限 retry。
