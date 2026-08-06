# PR 190 F13 EvidenceFact provenance 实施计划

## Gate metadata

- gate: `plan`
- work unit: F13，修复 rolling compaction EvidenceFact provenance 丢失与无证据事实污染
- branch / PR: `codex/interactive-oracle` / existing draft PR 190
- plan base: `ab1207f12706c07da7eca847bde27fe96fc727c5`
- Goal Confirmation: `docs/gateflow/pr-190-f13-evidence-provenance-goal-confirmation-20260806.md`，用户已于 2026-08-06 确认
- status: `accepted`
- final review decision: AgentMiMo 与 AgentDS 最终窄 re-review 均为 `accepted`，无 unresolved blocking/high/medium finding
- current gate / next entry point: accepted plan commit 后进入 `S0 — 设计真源切到 v4`
- blocking open questions: 无
- artifact path: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`

## Outcome first

本 work unit 采用 fresh compact v4，把“LLM proposal”与“Host accepted replacement”显式分开：

1. LLM 对旧 EvidenceFact 只返回 retain label；没有提交旧 claim 的字段路径。
2. Host 从 immutable boundary 原子复制旧 claim 与旧 canonical evidence refs；本轮新 fact 只允许选择真实 `evidence_material`。
3. Context Governance 构造唯一 `CompactAcceptedReplacementV4`，其中每条 `CompactAcceptedEvidenceFactV4` 自包含 claim、本轮 selection、context 与非空 canonical evidence refs。
4. caps、artifact、canonical terminal、Memory、RunInput/reconnect、rolling material 与 public Tool Trace 都读取同一个 accepted replacement；flat refs 只保留为 replacement 的 deterministic union projection。
5. 任一原子绑定、non-empty provenance、boundary membership 或 union 等式失败，都在 durable accept 前 typed reject，继续走既有 bounded repair / exhaustion / deterministic fallback / single-terminal 状态机。

这是一条 Host owner root-cause 修复，不增加 entailment heuristic、drop ledger、兼容 reader、旧 schema alias、第二 provenance service 或下游补偿。

## Direct evidence and owner alignment

### 已确认的失败链

- immutable artifact `b2bcad...4b39` 中 21.7% claim 选择 previous label P2，但 P2 是招商银行净息差事实；artifact 接受后 `accepted_evidence_mapping_refs=[]`。
- sequence 246 canonical compact terminal 与 Memory 把 21.7% 作为 evidence-backed fact 持久化，同时 refs 为空；reconnect 继续读取同一污染。
- `compact_material.py` rolling projection 只携带 previous compact event ref；`compact_payload.py` 只从 current evidence 的 singular accepted id 生成 flat refs；`context_governance.py` 不做 per-fact non-empty/binding barrier；`memory.py` 把同一个 flat union 赋给所有 facts。

### 唯一语义 owner

- LLM exact output shape：`dayu.host.compact_structure`。
- compact input/proposal/accepted replacement/fact atom：`dayu.host.compaction`。
- proposal -> accepted replacement：`dayu.host.context_governance`。
- rolling prior atom materialization：`dayu.host.compact_material`。
- canonical artifact/terminal serialization 与 strict reconstruction：`dayu.host.compact_payload` + 既有 context terminal owner。
- Memory/reconnect/RunInput：accepted replacement 的 read-model consumers。
- Tool Trace：canonical terminal 的 typed public projection consumer。
- Engine：通用 Runner transport，不拥有 compact 业务语义，本 work unit 不修改。

## Frozen v4 contracts

### 1. Host-internal immutable source boundary

`CompactInputV4` 与 `CompactSourceBoundaryEntryV4` 替换 v3；不保留 v3 alias、re-export、reader 或 dual path。

`CompactSourceBoundaryEntryV4` 固定字段：

- `source_label: str`
- `source_kind: CompactSourceKindV4`
- `source_refs: tuple[str, ...]`
- `canonical_evidence_refs: tuple[str, ...]`
- `readable_text: str`

不变量：

- `PREVIOUS_EVIDENCE_FACT` 与 `EVIDENCE_MATERIAL` 的 `canonical_evidence_refs` 必须非空且唯一。
- 其它 source kind 的 `canonical_evidence_refs` 必须为空。
- `source_refs` 继续是非空 immutable source refs；不能把 prior compact event ref 当成 evidence ref。
- `to_json()` 投影给 LLM 时省略 `source_refs` 与 `canonical_evidence_refs`；模型只看到业务文本、kind 和本地 label。
- artifact/canonical terminal 的 internal boundary snapshot 必须持久化两类 refs，strict reader 重验上述 kind/ref 不变量。

`dayu.host.compaction.PromptLocalProvenanceEntry` 以唯一字段
`canonical_evidence_refs: tuple[str, ...]` **替换**旧
`accepted_evidence_id: str | None`；material-pack 建成后不存在两个可供消费者选择的
canonical evidence 字段：

- current evidence material producer 从上游 accepted evidence atom 的 canonical id 机械形成单元素 tuple；旧 singular 字段不进入 `PromptLocalProvenanceEntry`，下游也不得继续读取它。
- previous evidence fact 从前一 accepted replacement 的对应 fact atom 原样携带。
- ordinary trace/answer/summary/intent/reference entry 固定为空。

`compact_material.py` 是上述 typed entry 的生产者；`compaction.py` 继续拥有 material-pack
typed contract。它与 durable `CompactSourceBoundaryEntryV4` 不是两个 provenance 真源：前者是构造期
label mapping，后者是同一 mapping 进入 immutable request/terminal 的 snapshot。boundary constructor
必须逐项机械复制并校验等式。

source boundary constructor 对 `PREVIOUS_EVIDENCE_FACT` 或 `EVIDENCE_MATERIAL` 的
`canonical_evidence_refs=()` 必须 typed fail closed，不能丢弃该 entry 后继续 compact，也不能把
compact event ref 填作 evidence ref。

`CompactionRequest.canonical_evidence_refs` 改为当前 immutable source boundary 所有 `canonical_evidence_refs` 的 boundary-order unique union；artifact `input_snapshot_refs.canonical_evidence_refs` 与 request digest 由此同源覆盖 current + retained-eligible prior provenance。

该 request union 表示“可选 evidence boundary”，允许包含最终被省略的 prior fact refs；accepted
aggregate 表示“实际 retained/new facts 的 refs”，因此正确不变量是 accepted aggregate 为 request
union 的有序子集，而不是二者恒等。accepted aggregate 自身必须 exact 等于 replacement 中逐 fact
refs 的 ordered unique union。

### 2. LLM proposal v4

input/output schema literals 固定为：

- `dayu.context_compaction.input.v4`
- `dayu.context_compaction.output.v4`

`CompactCandidateV4` 是 LLM proposal，不是 durable Memory replacement。root exact keys 固定为七项：

- `schema`
- `session_summary`
- `retained_previous_evidence_fact_labels`
- `evidence_facts`
- `answer_anchors`
- `forward_intents`
- `reference_continuity`

规则：

- `retained_previous_evidence_fact_labels` 必填，类型为唯一字符串数组，只能引用 `previous_evidence_fact`；Host 按 source boundary 顺序 canonicalize。空数组表示省略所有旧 facts。
- `evidence_facts` 只表达本轮新 facts；每项 `support_labels` 必须非空且只能引用 `evidence_material`。
- `context_labels` 可空，只能引用 `trace_material` 或 `answer_material`，永不贡献 canonical evidence provenance。
- 旧 v3 proposal、缺少 selector、额外 root key、把 previous fact 放入新 fact support 的输出全部 strict reject。
- 其它四类业务语义及 nullable `session_summary` 保持已确认语义；用户/assistant correction 可由这些非 evidence section 表达，但不能进入新 EvidenceFact。

`compact_structure.py` 的 immutable descriptor 继续是 template、JSON Schema、strict parser 的单一 structure owner；schema 名、digest、initial/repair template 必须同步前移到 v4。prompt 必须自足解释七字段的类型、必填性、允许 kind、retain/omit 含义、caps 对最终 combined facts 计数，并给最小完整 JSON 示例；还必须给一个数值化 combined-cap 示例，例如“fact cap 为 5、retain 2 条时最多新增 3 条”。不暴露 event id、digest、payload ref 或 Host provenance 校验职责。

### 3. Host accepted replacement v4

新增 `CompactAcceptedEvidenceFactV4`，固定字段：

- `claim: str`
- `selection_labels: tuple[str, ...]`
- `context_labels: tuple[str, ...]`
- `canonical_evidence_refs: tuple[str, ...]`

该 frozen/slots dataclass 无默认值；`__post_init__` 必须验证：`claim` 为非空字符串，
`selection_labels` 为非空唯一字符串 tuple，`context_labels` 为可空但唯一的字符串 tuple，
`canonical_evidence_refs` 为非空唯一字符串 tuple。kind、claim、refs 与 boundary 的业务绑定由
Context Governance 和 durable strict binding validator 负责，不能塞入 dataclass 做 repository lookup。

新增 `CompactAcceptedReplacementV4`，固定保存五类最终 Memory 语义：

- `session_summary`
- `evidence_facts: tuple[CompactAcceptedEvidenceFactV4, ...]`
- `answer_anchors`
- `forward_intents`
- `reference_continuity`

该 frozen/slots dataclass 同样无默认值；`__post_init__` 只验证五区 child 类型与 tuple shape。
它不自行读取 proposal/boundary，避免 domain DTO 反向依赖 governance。proposal/replacement/boundary
的 exact binding 由唯一 governance validator 完成并由 durable parser 复用。

`CompactAcceptedTruthV4` 由 governance 私有 permit 构造，包含：

- `proposal: CompactCandidateV4`
- `replacement: CompactAcceptedReplacementV4`
- immutable `source_boundary`
- represented / omitted coverage
- policy usage audit
- current input ref

Host 构造顺序固定为：

1. strict parse proposal。initial 或任一 repair proposal 都必须从本步骤重新执行完整 1-6 链，repair 不复用前次展开或 refs。
2. 校验所有 labels/kinds/重复 label。
3. 按 boundary 顺序展开 retain selector。每个 selected previous entry 生成一个 accepted fact：claim 必须直接复制该 entry 的 `readable_text`，`selection_labels=(previous_label,)`，`context_labels=()`，refs 直接复制该 entry 的非空 `canonical_evidence_refs`。
4. 按 proposal 顺序展开 new facts。claim 来自 proposal；selection 是该 fact 自己 canonicalized `support_labels`；refs 必须精确等于这些 evidence entries 的 boundary-order unique union；context 只保留 canonicalized context labels。
5. 将 retained atoms 放在 new atoms 之前；只对 combined accepted facts 做 exact whitespace-canonical duplicate 检查、information check、item/char caps 与 policy usage audit。`evidence_facts=[]` 且 retain selector 非空是合法 retain-only proposal；empty/low-information 不能在 new-facts-only 层提前拒绝。不得做关键词、数字、相似度、subject 或自然语言 entailment 判断。
6. 与 proposal 的其它四类 section 合成 final replacement，再派生 represented/omitted coverage。

逐 fact strict binding：

- retained atom：selection 必须恰好一个 `PREVIOUS_EVIDENCE_FACT`；claim 与 boundary readable text exact 相等；refs 与该 boundary entry exact 相等；context 为空。
- new atom：全部 selection 必须是 `EVIDENCE_MATERIAL`；refs exact 等于 selected entries 的 union；不得选择 previous fact。
- 每条 refs 必须非空、唯一、属于当前 immutable boundary 的对应 selected entries；不能从 operation-level aggregate、event adjacency、ordinal 或字符串反推。
- replacement aggregate evidence refs 必须 exact 等于逐 fact refs 按 fact/entry 顺序的 unique union；它只是验证过的 projection，不是写入事实的 owner。

多 source new fact 的 refs 构造公式固定为：
`ordered_unique_union(boundary[label].canonical_evidence_refs for label in fact.selection_labels)`；
不得直接复制任意单个 boundary entry，也不得读取 request/operation aggregate。

`CompactAcceptedReplacementV4` 是 Memory、rolling、ordinary business text、policy usage 和 public provenance 的唯一消费对象。proposal 只保留模型输出与 accepted-response identity 的审计绑定；consumer 不得把 `proposal.evidence_facts` 当成最终完整 replacement。

### 4. Fresh persistence and canonical reconstruction

- compact artifact schema version 从 `4` 前移到 `5`。
- canonical artifact/`CONTEXT_COMPACTED` semantic payload 持久化：
  - `accepted_proposal` + digest；
  - `accepted_replacement`；
  - 含 internal evidence refs 的 source boundary；
  - represented/omitted/policy audit；
  - `accepted_evidence_mapping_refs`，严格等于 replacement per-fact refs union；
  - 既有 proposal manifest / successful response identity / single terminal binding。
- 删除旧 `accepted_candidate` durable key 与 v3/schema-4 reader；不保留兼容 alias、migration shim 或 loose parser。
- strict payload parser 必须重验 proposal/replacement/boundary/coverage/policy/aggregate 所有绑定，产出唯一 `ContextCompactedSemanticPayload` typed view。
- strict payload parser 还必须验证 accepted aggregate 是 request boundary evidence union 的有序子集；不得错误要求 output aggregate 等于全部可用 input refs，因为 omit 合法缩小集合。
- rejected attempts 只写既有 diagnostic/rejected terminal；不写 accepted artifact/replacement。repair exhaustion 只写既有 failed terminal和fallback；stale/late commit 继续由既有 terminal owner返回 no-op，不产生第二 terminal。

### 5. Rolling, Memory, reconnect and public Tool Trace

- `compact_material.py` 从 previous typed `accepted_replacement.evidence_facts` 构造 previous blocks；每个 block 的 readable claim 与 provenance entry refs 来自同一个 fact atom，不能分别读取 flat fields。
- rolling material block 的 `canonical_source_refs` 继续保存 previous compact EventLog ref（来源标识）；同一 block/provenance entry 的 `canonical_evidence_refs` 保存该 accepted fact atom 的逐 fact evidence refs（证据标识）。material-pack boundary constructor 只能从后者构造 `PREVIOUS_EVIDENCE_FACT.canonical_evidence_refs`，不得从前者替代或推断。
- Memory 五区替换从 `accepted_replacement` 读取；`memory.py` 的 accepted-event fact projection 必须逐 atom 构造 `EvidenceBackedFactView`，每条 item 使用该 atom 自己的 refs，不再把 aggregate union 赋给所有 facts。
- reconnect 先经 `parse_context_compacted_semantic_payload` strict 恢复 accepted replacement，再复用同一 Memory fact projection；`run_input.py` 的 artifact view 可以携带 aggregate 作为整体 represented refs，但不得用它重建逐 fact refs。failed/rejected candidate 无读取入口。
- reactive multi-pass aggregation必须聚合 accepted replacements；事实 refs 随 atom移动，不能退回 proposal facts 或 flat refs。
- `dayu.host.durable.tool_trace` 新增 public frozen type `ResolvedCompactorEvidenceFact(claim, canonical_evidence_refs)`；resolver 在 accepted terminal 分支调用同一个 strict compact semantic parser，并机械投影 replacement facts。
- `ResolvedCompactorResponseIdentity` 新增 `accepted_evidence_facts: tuple[ResolvedCompactorEvidenceFact, ...]`，是 public resolver 的唯一 provenance projection；accepted 可因最终无 facts而为空，attempt-rejected 必须为空。
- `ToolTraceCompactorResponseSummary` 复用同一个 `ResolvedCompactorEvidenceFact` tuple 并只做 exact pass-through，不定义第二 fact summary。`tool_trace_analysis.py` 的 JSON/Markdown renderer 只从该 summary 渲染 claim+refs。
- Tool Trace 不新增 provenance ledger，不读取 artifact raw JSON 做第二套解释；terminal binding、provider/model identity 与 stale/late single-terminal语义保持不变。

## State machine preservation

```text
immutable v4 input + evidence-boundary refs
        |
        v
LLM proposal (retain labels + current-evidence new facts)
        |
        v
strict parser -> Host atomic expansion -> per-fact binding -> combined caps
        |                                      |
        | accepted                             | rejected
        v                                      v
one accepted replacement                 bounded repair
        |                                      |
artifact + one terminal                       +-- accepted -> same accept path
        |                                      +-- exhausted -> one failed terminal
Memory/RunInput/Trace                                      -> existing fallback
```

late/stale response 在 terminal commit owner 前后均不得绕过 exact operation/attempt/boundary binding，也不得创建第二 canonical terminal。

## Implementation slices

### S0 — 设计真源切到 v4

Objective：先删除与 Goal Confirmation 冲突的 v3 normative contract，写入上述 v4 owner、accepted replacement 与状态机；代码保持不变。

Allowed files：

- `docs/host/design.md`
- `docs/engine/design.md`（只做 truth check；Engine owner 未变化时不改）
- S0 gate/review artifacts

Host design exact edits：

1. 用 `CompactInputV4`/`CompactCandidateV4` 七字段 exact shape 替换 v3 I/O，并写明 retain-only 合法、new fact 只选 current evidence。
2. 定义 source boundary 的 Host-internal evidence refs、previous atom 构造来源与 LLM projection 省略规则。
3. 定义 `CompactAcceptedEvidenceFactV4`、`CompactAcceptedReplacementV4`、proposal audit-only 与逐 fact binding/aggregate subset 等式。
4. 把 artifact前移为schema 5，并写明canonical terminal strict parser、rolling、Memory/reconnect、RunInput、Tool Trace从replacement投影。
5. 保留repair/fallback/stale/late/single-terminal state machine，补每次repair重新执行完整binding且rejected/failed无accepted materialization。
6. 更新owner tests/真实provider observation/Oracle formal scenario边界。

必须删除“previous_evidence_fact 可作为自由新 claim support”和 event-level refs 作为 fact provenance 的规范文字；不得只追加 v4 后仍保留冲突 v3 真源。

Validation：terminology/reference scan、`git diff --check`、两路 semantic-owner review。完成信号是设计明确 Engine 不参与 compact 业务修复，且代码 slice 无需自行发明字段或 ownership。

### S1 — 原子 Host compact v4 纵向切换

Objective：一次完成 structure、input boundary、acceptance、persistence、rolling、Memory/reconnect 与 repair/fallback paths，避免 accepted checkpoint 存在 v3/v4 双 owner。

Allowed production/config files：

- `dayu/host/compaction.py`
- `dayu/host/compact_structure.py`
- `dayu/host/context_governance.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_payload.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`

Allowed tests/helpers：

- `tests/host/fake_compaction.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_compact_smoke.py`

Required migration order inside the slice：

1. 定义 v4 input/proposal/accepted fact/replacement/truth，删除 v3 symbols/exports。
2. 同步 structure template/schema/parser 与 initial/repair prompt。
3. 把 provenance refs 写入 material provenance -> source boundary；实现 governance atomic expansion/binding/caps。
4. 切换 artifact/terminal strict payload 与 aggregate union validation，artifact schema=5。
5. 切换 rolling、multi-pass、Memory、RunInput/reconnect consumers到 replacement。
6. 同步所有 production call sites、fake 与 owner tests；全仓 `rg` 不得残留 v3 compact contract、旧 durable key或 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取。若其它上游 typed accepted-evidence atom仍合法使用 singular `accepted_evidence_id`，必须逐处确认其不是 material-pack 下游读路径并在checkpoint artifact记录；历史 evidence 文档除外。

S1 保持一个 accepted commit，因为删掉 v3 后，core 与 durable/read-model consumers 必须在同一
checkpoint 完整切换；把 S1a/S1b 分成可提交 slices 会制造编译不完整 checkpoint或短暂 v3/v4 双
owner，违反本任务 fresh-schema 边界。为控制大 diff，S1 内增加三个**不提交**的强制验证/审查
checkpoint：

- C1（步骤1-2）：只审 v4 dataclass不变量、descriptor/template/schema/parser exact同源与prompt；运行 contract/LLM focused tests。
- C2（步骤3-4）：只审 material->boundary->governance->replacement->payload binding；运行 provenance、artifact、terminal focused tests，并手工复算一个 retained+two-source-new 例子的逐 fact refs。
- C3（步骤5-6）：只审 rolling/multi-pass/Memory/reconnect/RunInput与所有call sites；运行 projection/integration tests和 residue scan。

每个checkpoint由Controller在 `docs/gateflow/pr-190-f13-s1-cN-checkpoint-<timestamp>.md`
持久化审阅范围、base/worktree diff identity、两路reviewer结论、命令与关键验证结果，并让两路reviewer
按该cluster做增量检查。checkpoint通过后，若后续步骤修改其覆盖文件或owner contract，该checkpoint
立即失效，必须基于新diff重跑相同focused validation与两路增量review并写新artifact；旧artifact保留为
superseded evidence，不能覆盖。C1-C3当前版本全部通过后才进入S1正式两路code review与单一accepted
commit。任一中间态不声称可部署或可提交。

Mandatory S1 owner tests：

1. previous fact retain 后 claim/refs exact 保留，boundary label可变化但 atom同源。
2. v4 从结构上无“改写 previous claim并借旧provenance”路径；把 previous label 塞入 new fact support strict reject。
3. 用不相关 previous fact支持新 claim无法进入 replacement/Memory。
4. previous/current fact任一最终 refs为空、selection/ref union错配或refs越界时typed reject/strict payload reject。
5. 用户/assistant correction无 evidence material时，只能形成非 evidence section；伪造 EvidenceFact reject。
6. current真实 evidence material可接受，并把对应 canonical id逐 fact持久化。
7. rolling与cap repair后保留 provenance；caps按 retained+new combined facts计算。
8. repair exhaustion/fallback无 accepted artifact/Memory污染。
9. stale/late result不产生第二 terminal。
10. accepted artifact/EventLog/Memory/RunInput的claim+refs exact同源；多 fact不共享无关 union refs。
11. reconnect只读取canonical accepted replacement。
12. retain-only（new facts为空）按combined output成功接受；retained+new exact duplicate按combined规则拒绝。
13. previous fact被omit后，claim恰好相同但选择current evidence的新fact可按current provenance接受；不得新增相似度/subject heuristic误拒绝。
14. 多source new fact逐entry union完整，且不得等于任一单entry或无关fact aggregate；request available union可为accepted aggregate真超集。
15. previous/current boundary evidence refs为空时，material/boundary construction typed fail closed。

Slice validation：受影响 owner tests；目标文件 Ruff；目标 pyright（最终仍跑完整 pyright）；compileall；JSON Schema/template/prompt JSON 校验；`git diff --check`。达到 targeted coverage >=80% 或记录可核验的现有文件级例外。

### S2 — public Tool Trace 同源投影、README 与 integration

Prerequisite：S1 accepted commit。

Allowed production files：

- `dayu/host/durable/tool_trace.py`
- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- 如 typed dataset plumbing 确实需要，`dayu/host/tool_trace_analysis_input.py`

Allowed tests/docs：

- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`
- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- S2 gate/review artifacts

Owner tests：accepted resolver与analysis summary逐 fact claim/refs与canonical terminal一致；rejected response facts为空；malformed accepted replacement/aggregate/boundary fail closed；JSON/Markdown同源；不泄漏selection label、raw payload、credential或prompt；现有 provider/model/response identity binding不回归。

README 只按各自 `Agent更新约束` 更新职责范围内的 v4 contract、prompt或测试入口；根 README、`dayu/README.md` 与 Engine README只做truth check，没有用户入口、分层或Engine语义变化时不改。

### S3 — implementation validation 与真实 provider observation

Prerequisite：S0-S2 accepted commits与aggregate deepreview accepted。

Test validation：

- 全部受影响 Host tests及必要 integration/E2E。
- 完整 `pyright`，不允许新增/扩散错误。
- changed-file Ruff、`compileall`、JSON校验、`git diff --check`。
- README/design truth scan与全仓旧 v3/old key residue scan。

真实运行：

- provider-independent coverage先用 Mimo plan；Mimo不可用时用 DeepSeek。
- 使用实际 provider configuration 与生产 Host compactor path，记录真实 argv/env（敏感值只记availability）、input、stdout/stderr/exit code、provider/model/request identity、artifact/EventLog/Memory/Tool Trace/SQLite变更和immutable digests。
- 可以运行 production `dayu-cli interactive` 形成 post-fix observation，但不得把它称为 Oracle formal scenario acceptance；不使用 `MockFinanceMemoryTool`、`get_mock_finance_memory_fact`、fake provider/tool 或直接Host smoke替代formal CLI evidence。
- 失败运行保留在独立新目录，不覆盖或包装成PASS。

## Review and Gateflow execution

- plan gate：AgentMiMo + AgentDS 独立 `planreview`，Controller逐finding裁决；修复后由原reviewers re-review，accepted plan单独commit。
- S0/S1/S2：每slice implementation artifact -> 两路code review -> fix -> 原reviewer re-review -> accepted slice commit。任一 blocking/high finding 未关闭不得进入下一slice。
- aggregate：按 `$deepreview --base <accepted-plan-commit>` 做两路语义 owner/过度设计/adversarial review；fix/re-review/accepted deepreview commit。
- existing PR 190：只push当前branch；`create draft PR` gate记为pre-existing/no-op。随后对PR 190最终diff做PR review/fix/re-review/commit/push；不创建新PR、不merge/mark ready/approve/request reviewers/rebase/force-push/deletebranch。

两路review每次都必须明确检查：

- semantic owner是否唯一，proposal/replacement是否出现双真源；
- per-fact refs与boundary entry exact mapping，是否仍存在flat union反向写fact；
- previous atom是否能被模型改写或跨fact借provenance；
- repair/fallback/stale/late/single terminal是否保持无污染；
- Tool Trace/Memory/artifact是否真的来自strict terminal，而不是raw/display补偿；
- schema/prompt是否自足且未泄漏Host治理术语；
- 是否引入兼容层、heuristic、drop ledger、god object/function或无必要跨层耦合；
- 真实运行是否把test/Host smoke/fake误写成formal interactive evidence。

## Completion evidence matrix

| 业务语义 | owner test | Host/integration observation | 真实 provider observation | Oracle formal scenario |
|---|---|---|---|---|
| previous atom claim/refs原样保留 | 必须 | 必须 | 必须观察至少一次rolling | 后续Oracle重跑 |
| 无current evidence的新fact拒绝 | 必须 | 必须 | 尽可能观察repair/fallback | 后续Oracle重跑 |
| 多fact per-entry mapping/aggregate等式 | 必须 | 必须 | 可由真实compact artifact核对 | 后续Oracle重跑 |
| repair exhaustion/fallback无污染 | 必须 | 必须 | 真实provider可控时观察 | 后续Oracle重跑 |
| stale/late single terminal | 必须 | 必须 | 不要求人为制造provider竞态 | 后续Oracle重跑 |
| artifact/EventLog/Memory/Trace/reconnect同源 | 必须 | 必须 | 必须核对真实accepted run | 后续Oracle重跑 |

测试通过不能写成真实行为通过；Host smoke不能写成interactive CLI scenario；只有provider、tool、corpus、入口均核实后才可声明未使用mock/fake。

## Validation commands

计划内固定使用仓库 `.venv`，具体测试文件可按slice缩小，但final至少执行：

```bash
source .venv/bin/activate
pytest <all affected owner/integration tests>
pyright
ruff check <all changed Python files>
python -m compileall dayu tests
python -m json.tool <each changed JSON artifact/schema file>
git diff --check
```

真实provider/CLI命令不在plan中猜测；S3先从现有production CLI help、provider config和既有interactive harness读取精确argv，再把实际命令、环境与证据入口写入immutable observation artifact。Oracle下一步命令必须在final closeout给出可复制的精确版本。

## Residual risks

- fresh v4/schema-5不兼容读取旧 compact payload/session；这是已确认的新schema边界，不增加migration、dual reader、静默省略或“旧数据fallback”。strict reader遇到schema-4 compact必须fail closed并保留原durable数据；本work unit的实现验证与后续formal scenario必须新建workspace/session。旧workspace的升级/迁移与用户工作流不在本work unit承诺内。
- schema横切Host多个consumer，S1较大；以“单一atomic contract migration”控制风险，不拆成可提交的v3/v4双路径。
- 真实provider输出仍可能经repair/fallback失败；正确性标准是fail closed且不污染，不以模型总能生成accepted proposal为前提。
- natural-language support关系仍不可程序判定；本修复只封闭可确定的label kind、atomic retention、per-entry provenance与non-empty barrier，不声称解决entailment。
- 三条formal replacement scenarios继续为`assigned to later Oracle adjudication`，在本work unit final closeout保持unadjudicated。

## Plan review resolution summary

- AgentDS review：`docs/reviews/plan-review-20260806-141818.md`，结论 `pass-with-risks`。
- AgentMiMo review：`docs/reviews/plan-review-20260806-142113.md`，结论 `pass-with-risks`。
- accepted fixes：retain-only combined check、Tool Trace typed owner、PromptLocalProvenanceEntry clean replacement、per-role union公式、reconnect逐fact路径、boundary fail-closed、combined-cap例子、exact dataclass不变量、repair全链重验、S1 C1-C3中间验证、额外owner tests。
- rejected-with-reason：
  - “request available evidence union 必须等于 accepted aggregate”被拒绝；合法omit会使request union为真超集，正确关系是accepted aggregate exact等于逐fact union且属于request boundary。
  - “schema-4 rolling 时静默省略旧facts并走fallback”被拒绝；这会形成未确认的兼容/数据丢失语义。fresh schema只允许strict fail closed，新workspace另行验证。
  - “把S1拆成可提交S1a/S1b”被拒绝；删v3后的跨consumer切换无法形成两个都完整、无双owner的accepted checkpoint。采用同一未提交slice内C1-C3 focused validation/review，再做一次完整slice review/commit。
