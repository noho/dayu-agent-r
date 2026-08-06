# PR 190 F13 EvidenceFact provenance Goal Confirmation

## Gate metadata

- gate: `goal confirmation`
- work unit: F13，修复 rolling compaction 中 EvidenceFact provenance 丢失及无证据事实污染正式 Conversation Memory
- design inputs: `docs/host/design.md`、`docs/engine/design.md`
- status: `confirmed`
- confirmation: 用户于 2026-08-06 明确回复“确认”
- current gate / next entry point: `plan`
- changed production files: 无
- artifact path: `docs/gateflow/pr-190-f13-evidence-provenance-goal-confirmation-20260806.md`

## Preflight

执行并复核了 branch、工作树、Git operation、远端、PR 与 main ancestry：

- 当前 branch：`codex/interactive-oracle`，不是 protected trunk。
- 工作树：干净；`MERGE_HEAD`、`REBASE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD` 均不存在。
- local HEAD 与 `github/codex/interactive-oracle` 均为 `ab1207f12706c07da7eca847bde27fe96fc727c5`。
- local `main` 与 `github/main` 均为 `113ea34d47b95812d79aa31705949bbb46bc6061`。
- `github/main` 是当前 HEAD 的 ancestor；`main...HEAD` 为 behind 0 / ahead 79，当前分支无需 rebase，且可从 main fast-forward 到当前 HEAD。
- PR 190：OPEN、draft、head `codex/interactive-oracle`、base `main`、`MERGEABLE/CLEAN`，URL 为 `https://github.com/noho/dayu-agent-r/pull/190`。
- 本 work unit 只向既有 PR 190 push；不创建新 PR，不 merge、mark ready、approve、request reviewers、rebase/force-push 或删除 branch。

## First-principles judgment

问题成立，严重性为高，不是 prompt 表述不够严谨或测试夹具偶然行为。

EvidenceFact 的业务承诺是“claim 已绑定 canonical accepted evidence”。只要 Host 能提交一个 `canonical_evidence_refs=()` 的 EvidenceFact，或把多条 fact 绑定到 compact event 级共享 refs，Conversation Memory 就不能再区分证据事实与普通对话陈述。该错误会跨 rolling compact 和 reconnect 延续，因此会污染后续 LLM 输入和审计结论。

程序可以确定性判断并必须 fail closed 的部分包括：source kind、label 是否存在、每条 fact 的 label-to-provenance mapping、mapping 是否非空、旧 fact 是否原子保留、per-fact refs 是否属于对应 immutable boundary entry，以及 durable projections 是否来自同一 accepted truth。自然语言 entailment 不可由本 work unit 的程序可靠判断，因此不引入关键词、数字匹配、模型自评或第二次 LLM 裁决。

## Direct artifact evidence

用户给出的 immutable artifact：

`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY/evidence/05-deepseek-replacement-constrained/compact-artifacts/sha256/b2/b2bcad92512a5c660624194185d0fb5945de35b112c24310b6cef158220e4b39`

其 SHA-256 与文件名一致。artifact 中：

- accepted claim 为“当前唯一有效毛利率为21.7%，旧口径18.2%已失效。”；
- `support_labels=["P2"]`；
- P2 是“招商银行 2024H1 净息差1.88%……不良率0.94%”的 previous EvidenceFact；
- `accepted_evidence_mapping_refs=[]`；
- `input_snapshot_refs.canonical_evidence_refs=[]`；
- `input_snapshot_refs.evidence_backed_fact_refs=[]`。

同一 immutable evidence bundle 证明了传播链：

- `compact-eventlog.json` 的首次 accepted compact（sequence 144）把招商银行 fact 绑定到一个 canonical evidence ref；rolling compact（sequence 246）接受 21.7% claim，但 mapping refs 为空。
- `05-deepseek-replacement-constrained/memory.json` 把 21.7% 写为 `derived_from_evidence`，同时 `evidence_refs=[]`、`provenance.source_refs=[]`。
- `07-deepseek-reconnect/memory.json` 仍读取相同 latest compact event、相同 21.7% claim 与空 refs，证明污染跨 reconnect 持续。
- public Tool Trace 把 sequence 246 compact terminal 公开为 `accepted`；当前 response summary 没有投影 accepted fact provenance，因此无法与 Memory/artifact 做同源验收。

这些是既有真实 CLI evidence 的 post-hoc root-cause 证据，不把它重新裁决为 formal scenario acceptance。

## Direct code evidence and semantic owners

1. `dayu/host/compact_material.py:2244-2294`：rolling builder 只从 prior accepted candidate 读取 claim；previous fact block 的 `canonical_source_refs` 只有 prior compact event id，没有读取或携带该 fact 的 canonical accepted evidence refs。
2. `dayu/host/compaction.py:116-120` 与 `dayu/host/context_governance.py:232-246`：`previous_evidence_fact` 被允许作为自由生成 `claim` 的 `support_labels`；accept barrier 只校验 label existence/source kind，没有把旧 claim 作为 Host-owned atomic value。
3. `dayu/host/compact_payload.py:616-635`：mapping helper 把所有 facts 的 support labels 扁平聚合，并只收集 provenance entry 上非空的 singular `accepted_evidence_id`；previous fact entry 没有该字段，因此可得到空 tuple。
4. `dayu/host/context_governance.py:90-147`：唯一 accept owner 在 schema、label/kind、coverage、information、duplicate 与 caps 校验后即可构造 accepted truth，没有逐 fact 非空 canonical evidence provenance barrier。
5. `dayu/host/memory.py:1737-1766`：Memory 把 compact event 级 flat `accepted_evidence_mapping_refs` 赋给每一条 fact；这既允许空 refs，也会让多个 facts 共享 union refs，形成跨 entry provenance 错配。
6. `dayu/host/memory.py:2943-2952`：名为 `_require_non_empty_items` 的 helper 只检查 tuple 中已有元素不为空，并不要求 tuple 本身非空。
7. `dayu/config/prompts/scenes/conversation_compaction_user.md:35` 与 `docs/host/design.md:3361-3408`：现行 LLM/output contract 明确允许模型为新 claim 引用 `previous_evidence_fact`。因此根因同时存在于 contract、Host accept truth 与 rolling material projection，不能只靠 prompt 加一句警告修复。
8. `docs/engine/design.md:556-579`：Engine 不拥有 compact schema、五类 memory、coverage、repair 或 artifact；本 work unit 不应修改 Engine 语义。

唯一 owner 边界裁决：

- LLM output exact shape：`dayu.host.compact_structure`。
- compact domain types、Host-owned accepted EvidenceFact atom：`dayu.host.compaction`。
- proposal 到 accepted truth 的强约束：`dayu.host.context_governance`。
- prior accepted fact/provenance 到 rolling material 的重建：`dayu.host.compact_material`，输入真源为 canonical compact payload/artifact owner。
- durable artifact/EventLog semantic payload 的写入和严格读取：`dayu.host.compact_payload` 与既有 compact terminal owner。
- Memory/reconnect：只消费 committed accepted per-fact truth，不补偿、不重算。
- Tool Trace：从同一 canonical accepted terminal 的 typed semantic view 投影，不另建 provenance 账本。
- Engine：保持中立，不进入修复范围。

## Confirmed goal

本 work unit 的目标固定为：

1. Host accepted truth 中每条 EvidenceFact 都是原子业务事实，至少包含原 claim、当前 proposal source-label binding 与非空 per-fact canonical accepted evidence refs。
2. rolling input 内的 previous EvidenceFact 携带 Host-internal per-fact provenance；LLM 只能显式选择保留哪些旧 facts，未选择即省略，不能提交旧 fact 的改写 claim。
3. LLM 新生成的 EvidenceFact 只能引用本轮真实 `evidence_material`；Host 按该 fact 自己的 support labels 精确解析 refs，不能使用 compact event 级 union 替代 per-fact mapping。
4. Host 在 policy/caps、artifact 与 durable terminal 之前展开 retained atoms 与 new facts，并逐 fact 验证 non-empty、boundary membership、claim/selected-entry 原子绑定及 exact duplicate/cap contract。typed reject 进入既有 bounded repair；耗尽进入既有 deterministic fallback。
5. 用户输入、assistant answer、answer anchor、session summary、普通 trace/context 中的修正，没有当前 evidence material 时不得形成新 EvidenceFact；它仍可按五类 Memory 的既有非 evidence 语义进入适当 section。
6. rejected/failed/stale/late candidate 不形成 accepted artifact、Memory 或第二 canonical terminal；tier 4/5 fallback 不物化 Memory。
7. accepted artifact、EventLog、audit、Memory、RunInput/reconnect 与 public Tool Trace 从同一 per-fact accepted truth 投影；flat aggregate refs 如因现有 public/diagnostic contract继续存在，只能是 per-fact refs 的确定性 union，并由 strict parser 校验等式，不能成为第二真源。
8. owner tests 与 integration 覆盖首次 compact、rolling keep/omit/new fact、cap repair、repair exhaustion/fallback、stale/late、reconnect 与各 projection 的同源性；实现验证另使用真实 provider，formal interactive scenarios 仍由 Oracle 总控独立运行和裁决。

## Minimal correct contract boundary

现有 v3 output 无法表达“保留旧 fact，但不让模型重写 fact”，因此确认后按 fresh schema 变更处理：

- 新 output schema 增加 required `retained_previous_evidence_fact_labels: list[str]`；只允许 `previous_evidence_fact` labels，Host 按 immutable boundary 顺序 canonicalize。未列出的 previous facts 被省略，不新增 drop ledger/reason。
- `evidence_facts` 只表达本轮从 `evidence_material` 形成的新 facts；其 `support_labels` 不再允许 `previous_evidence_fact`。
- Context Governance 先用 Host-owned prior atoms 原样展开 retained facts，再与 new facts 组成最终 replacement；retained claim 与 refs 不能由模型提供或改写，combined result 才接受 duplicate、information 与真实 caps 校验。
- durable accepted truth 使用 self-contained per-fact typed provenance，不依赖 fact ordinal、flat union、event 时间顺序或字符串反推。artifact schema 随 breaking durable shape 前移；不读旧 compact schema/artifact，不增加 alias、dual reader 或 migration shim。
- prompt、concrete template、JSON Schema 与 strict parser 从同一 output structure owner 更新；prompt 自足说明 selector、新 fact、字段类型、必填性、允许 source kinds、caps 计数和最小示例。

这个边界是最小正确方案：只新增旧 fact retention selector 与 per-fact accepted truth，不引入 entailment engine、drop ledger、provenance service、第二次模型裁决、长期检索、旧 schema 兼容或 UI fallback。

## Success signals

- 合法旧 EvidenceFact 被保留时，claim 与 canonical evidence refs 原样跨 rolling compact；模型没有可提交改写 claim 的字段路径。
- 任一新 fact 无当前 evidence material、任一 retained atom 无 prior non-empty refs、或任一 fact 最终 refs 为空时，accept owner typed reject。
- 多 fact 场景每条只得到自己 support labels 对应 refs；aggregate refs 等于 per-fact refs 的确定性 union。
- repair/fallback/stale/late/reconnect 保持既有单 terminal 与无污染不变量。
- Memory、accepted artifact、canonical EventLog/audit 与 Tool Trace 对同一 claim 给出相同 refs；reconnect 只重建 canonical accepted Memory。
- 真实 provider validation 只报告 observed behavior，不替 Oracle 接受 formal replacement scenarios。

## Non-goals

- 不判断自然语言 entailment，不做关键词/数字/相似度匹配或模型自评。
- 不新增 drop ledger、兼容 alias、loose parser、下游 fallback 或展示层修正。
- 不修改 F01-F12、download/process、已经由用户接受的 init/prompt/interactive Oracle 语义。
- 不把三条 replacement scenarios 标为 accepted，不替用户或 Oracle 裁决。
- 不修改 Engine compaction ownership，不新增跨层依赖。

## Agent review adjudication

- AgentMiMo 与 AgentDS 的只读复核都确认了 previous fact provenance 丢失、flat refs 与 accept barrier 空洞的直接代码路径。
- 两路初版建议均倾向“要求每个 fact 至少含一个当前 `evidence_material` label”。该建议被 AgentController 以 `rejected-with-reason` 裁决：它会让没有重复展开 raw evidence 的 rolling compact 无法保留合法旧 fact，仍未消除模型重写旧 claim，也没有解决多 fact 共享 union refs。
- follow-up 中，AgentMiMo 建议保留自由 claim schema、允许 prior-only fact 的 resolved refs 为空；AgentDS 建议按 `previous_evidence_fact` label 递归解析 prior refs。两者均被 `rejected-with-reason`：前者直接违反每条 accepted EvidenceFact 必须有非空 provenance，后者虽可恢复 refs，却仍允许模型改写 claim 后借用同一 prior atom 的 refs，保留 provenance laundering 的核心路径。
- 接受的方向是显式 retain selector + Host atomic projection + per-fact non-empty provenance；两路调研仅作为 Goal Confirmation evidence，不构成 plan/code review gate。

## Validation at this gate

- 只读 Git/PR/main preflight：通过。
- immutable artifact SHA-256、accepted candidate/source boundary/mapping：已核对。
- EventLog sequence 144/246、05 Memory 与 07 reconnect Memory：已核对。
- Host/Engine design ownership、compact source/accept/payload/Memory/prompt 直接调用链：已核对。
- 未运行 tests、Host smoke 或真实 CLI；本 gate 不把任何行为写成已修复。

## Docs decision

实现会触及 Host contract 与 `dayu/config/prompts`，因此后续必须按 README 约束检查并按需更新：

- `docs/host/design.md`：必须更新，当前 v3 contract 本身允许 provenance laundering。
- `docs/engine/design.md`：预计无需更新，Engine ownership 不变；实现后再次 truth check。
- `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`：先读取各自更新约束，再按职责范围决定。
- 根 README 与 `dayu/README.md`：当前预计无用户入口或分层变化；实现后按触发规则复核。

## Residual risks and open questions

- Goal Confirmation 已由用户确认；后续 gate 只能在本 artifact 固定的语义边界内细化实现，不能回退到自由改写旧 fact、flat union 真源或下游补偿。
- per-fact public projection 的最终字段名、schema literal/version 与 slice 划分在 plan gate 固化，但不得偏离本 artifact 已确认的 retain selector、Host atomic projection、per-fact non-empty refs 与 fresh-schema 边界。
- Oracle formal interactive replacement scenarios 继续由 Oracle 总控拥有，分类为 `assigned to later Oracle adjudication`，不是本 work unit 的实现通过条件。
