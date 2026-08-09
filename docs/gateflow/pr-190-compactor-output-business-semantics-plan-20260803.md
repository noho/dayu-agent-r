# PR 190 Compactor 输出业务语义补充计划

## Gate metadata

- Gate：`plan`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Branch：`codex/interactive-oracle`
- Existing PR：PR 190；本 work unit 不新建分支或 PR
- Goal confirmation：用户已确认，并冻结本计划中的纠正语义、owner、non-goals 与成功信号
- Plan status：`plan-review-fix-complete`，code-generation-ready，等待 re-review
- Current gate after this artifact：`re-review`
- Next entry point：`re-review`；通过后按 Gateflow 自动进入 accepted plan commit、implementation 及后续 gates，在没有 stop condition 时持续推进到 `final closeout pass`
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-plan-20260803.md`

## Durable inputs and preservation

以下文件是外部 durable input，只读引用并原样保留，不回写、不重排、不作为本计划 artifact 的一部分重建：

- `docs/reviews/pr-190-review-20260803-203709.md`，当前 SHA-256：`e7add55e6c95c783ca8d92c8f8d15b223836851e70cfd73a902f15207d0d9841`
- `docs/reviews/plan-review-20260803-212134.md`，当前 SHA-256：`1d592ae41f6ed42b8b0c2e30fe37ebfa96751347859d2b0bf8ddb07aad46ae02`

实现、review 与 closeout 都不得修改这两份历史 artifact；后续 gate 如需记录判断，应创建新的 artifact。

## Plan review controller adjudication

- AgentMiMo：无 finding，plan review pass。
- AgentDS F01（`forward_intents.status` / `reference_continuity.reason` 仍有 LLM-facing 语义缺口）：`deferred-with-owner`，owner 为后续独立 LLM-facing schema work unit；当前 work unit 不扩 scope。
- AgentDS F02（hash 更新步骤未额外声明 encoding）：`rejected-with-reason`；`sha256sum` 与 publication test 都读取最终 raw bytes，任何保存后的 bytes 漂移都会由测试 fail closed，不需要新增脚本、encoding 规则或流程。
- Controller conclusion：上述 finding 均不阻塞当前 plan；本次 follow-up 只纠正 Gateflow 推进与 checkpoint 权限元数据，不改变已冻结的字段语义、实现 slice 或验证范围。

## Goal, motivation, and success signal

### Goal

在唯一 LLM-facing 语义 owner `dayu/config/prompts/scenes/conversation_compaction_user.md` 中，为以下现有输出字段补齐简短、自足、业务可执行的含义：

- `session_summary`，包括 `text`、`source_labels` 与 `null` 的 replacement 语义；
- `evidence_facts`，包括 `claim`、`support_labels`、`context_labels` 的职责边界；
- `answer_anchors`，包括 `title`、`detail`、`source_labels` 的职责边界；
- `explicitly_dropped_sources.reason` 的 `superseded`、`redundant`、`out_of_scope`、`policy_limit` 四个允许值。

### Motivation and first-principles judgment

该 work unit 成立，且严重性评估合理。模型是这些文案的直接消费者；strict JSON parser 只能校验字段形状、引用 kind 与枚举值，不能替模型从英文名称推断业务分类。若 prompt 不定义字段和 reason 的含义，结构合法的 candidate 仍可能把同一材料分到不同语义区，或给 durable drop audit 写入不可唯一解释的原因。修复应发生在 prompt owner boundary，而不是在 parser、Context Governance、Memory 投影或下游消费者增加推断和补偿。

### Success signal

完成实现后同时满足：

1. fresh model 只读当前 user prompt，即可区分摘要、证据事实、既有回答锚点和四种 drop reason；
2. prompt 明确 `session_summary: null` 是完整 replacement 中不含摘要，candidate 被接受后当前摘要变为空并清除既有摘要；
3. prompt 明确 `evidence_facts.claim` 的直接支持既可来自 `evidence_material`，也可来自 `previous_evidence_fact`；
4. prompt 明确 `policy_limit` 只有当前 repair feedback 明示具体 cap 时才可使用，首次请求或无具体 cap 时禁止猜测；
5. owner-level deterministic tests 锁定上述业务语义，既有 production example 继续通过 strict parser 与 accept barrier；
6. packaged prompt 的 publication hash、冻结 manifest hash 与实际 bytes 同源；
7. focused tests、完整 pyright 与 diff check 通过，没有 Host contract、状态机或 Memory projection 行为变化。

## Non-goals and scope boundary

本 work unit 明确不做：

- 不改变 `CompactCandidateV2`、输入/输出 schema、字段必填性、字段类型、允许枚举或 source-kind 引用规则；
- 不修改 `dayu/host/compaction.py` 的 typed contract 或 strict parser；
- 不修改 `dayu/host/context_governance.py` 的 accept/reject barrier、repair feedback 生成、policy/estimator 或错误码；
- 不修改 `dayu/host/memory.py` 的完整 replacement 与 Memory 投影语义；
- 不增加 semantic verifier、fallback、loose parsing、兼容分支、默认值或下游重分类；
- 不修改 `dayu/config/prompts/scenes/conversation_compaction.md`、scene manifest、execution profile、provider/model selection 或运行状态机；
- 不修改 frozen oracle `docs/cli_ci_oracles.json`、frozen scenario `docs/cli_ci_scenarios.json` 或 `docs/cli_ci.md`；
- 不刷新 current-head inventory/readiness proof；readiness refresh 属于后续独立 work unit；
- 不运行或扩张 real-provider conformance smoke，不把 deterministic 文案测试表述为真实模型行为证据；
- 不补充 `forward_intents.status` 或 `reference_continuity.reason` 的业务语义；该缺口按 controller 裁决交由后续独立 LLM-facing schema work unit；
- 不修改 README、design 或已有 review artifact；README/design 触发判断见下文；
- 不在 gate 接受前 stage/commit/push 未接受的实现，也不把 unrelated dirty files 纳入 checkpoint；accepted plan gate 可 stage/commit/push 其 intended plan/review artifacts，后续 accepted checkpoint 同样只处理本 gate 的 intended artifacts。
- 不 merge、approve、mark ready、请求 reviewer、删除分支或发布未获授权的外部 comment。

## Direct code and test evidence

| Evidence | Direct fact | Plan consequence |
|---|---|---|
| `dayu/config/prompts/scenes/conversation_compaction_user.md:31-60` | 三个核心 section 主要只有 shape/source-kind 限制；四种 drop reason 只有枚举字面量 | 业务说明必须补在该 prompt owner 内 |
| `dayu/host/compaction.py:157-163` | `CompactDropReasonV2` 只定义四个闭集枚举 | 不改 enum/schema；prompt 解释现有值 |
| `tests/host/test_llm_compaction.py:329-374` | asset-owner 测试只检查 schema/source-kind/open-string 等片段存在 | 在同一 owner-level test 中补精确业务语义断言 |
| `tests/host/test_public_compact_smoke.py:268-333` | 默认装配路径会读取真实 packaged prompt，并把完整示例送入 production parser/governance | 加少量 assembled-path 语义哨兵；保留 example accept 证明 |
| `dayu/host/memory.py:1229-1255` | `CONTEXT_COMPACTED` 会整体替换五类语义投影 | `session_summary: null` 不能承诺保留旧摘要 |
| `dayu/host/memory.py:1720-1739` | accepted candidate 的 summary 为 `None` 时返回 empty summary view | prompt 必须说明 accepted 后摘要变为空 |
| `tests/host/test_memory_projection.py:1408-1442` | 既有回归明确锁定 “without summary clears prior session summary” | 不改该测试；focused validation 必须继续运行它 |
| 当前 prompt 的 `support_labels` contract | 支持 label 允许 `evidence_material` 和 `previous_evidence_fact` | `claim` 文案必须显式覆盖两种直接支持来源 |
| `dayu/host/context_governance.py:492-576` | 具体 item/字符 cap 只在 candidate 超限后进入 repair issue message | `policy_limit` 的可见依据只能是当前 repair feedback 中的具体 cap |
| `docs/cli_init_workspace_manifest_v1.json:40` | packaged user prompt bytes 由 `content_sha256` 冻结 | prompt 修改后只更新该 asset 条目的 digest |
| `tests/cli/test_smoke_cli_init_provider_matrix.py:92-97,725-748` | manifest 文件自身 digest 由 `FROZEN_MANIFEST_SHA256` 锁定 | asset digest 更新后重算并更新 manifest digest constant |

## Owner and contract decision

- 唯一语义 owner：`dayu/config/prompts/scenes/conversation_compaction_user.md`。它负责向无状态模型承诺各字段和 drop reason 的业务含义。
- `dayu/host/compaction.py` 继续独占 typed shape、枚举和 strict parse contract，不承担 LLM-facing 解释。
- `dayu/host/context_governance.py` 继续独占 candidate accept/reject、coverage 与 policy cap 验收，不新增语义分类器。
- `dayu/host/memory.py` 继续独占 accepted candidate 到当前 Memory view 的完整 replacement 投影。
- `docs/cli_init_workspace_manifest_v1.json` 与测试常量只是 prompt bytes 的派生 publication truth，不拥有业务语义。

不存在 public interface、typed schema、state machine 或 durable event schema 变更。唯一行为变化是模型收到的说明更自足；Host 对同一 JSON candidate 的解析、验收与投影保持完全不变。

## Exact LLM-facing wording semantics

实现必须在现有“输出必须完整且只含以下字段”章节就地补充以下语义。允许为中文流畅度做标点调整，但不得删减、反转或泛化这些判断条件，不得引入 Host、Python 类型名、内部治理 id 或迁移术语。

### `session_summary`

- `session_summary` object 的业务职责：保存后续对话仍需知道的整体任务背景、已完成进展、当前状态与关键约束的紧凑业务摘要；它是总体上下文，不应用来机械重复每条证据、既有回答或待办。
- `text`：可独立阅读的业务摘要，只能概括 `source_labels` 对应材料中已有的内容，不得加入材料没有的事实、结论或任务。
- `source_labels`：直接参与形成该摘要的 source 引用标签；每个标签仍只是本次请求内的引用标签，不是事实或推理依据。
- `null`：表示本次完整 replacement 不包含 session summary；candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要。它不影响同一 candidate 中其它四类业务语义项。

### `evidence_facts`

- `evidence_facts` 的业务职责：保存后续分析仍可能需要、且有 accepted evidence 直接支持的业务事实；它不是回答结论、推测、待办或仅有对话背景的描述。
- `claim`：可独立阅读的业务事实，必须由 `support_labels` 对应的 accepted `evidence_material` 或 `previous_evidence_fact` 直接支持；不得把 `trace_material` 或 `answer_material` 当作事实依据。
- `support_labels`：对 `claim` 提供直接事实支持的 source 引用标签，只能使用既有 schema 允许的 `evidence_material` 或 `previous_evidence_fact`。
- `context_labels`：只补充理解该事实所需的对话背景、限定条件或既有回答上下文，可为空；它不能直接支持 `claim`，也不能弥补缺失或不充分的 `support_labels`。

### `answer_anchors`

- `answer_anchors` 的业务职责：保存后续对话仍需沿用的既有回答、判断或结论锚点；它记录已经形成的回答语义，不把工具证据、未来动作或新推断伪装成既有结论。
- `title`：用于识别该既有回答或结论主题的简短业务标题。
- `detail`：可独立阅读的既有回答或结论内容，并保留继续对话所需的条件、边界或不确定性；只能整理 source 中已经表达的结论，不得发明新结论。
- `source_labels`：直接承载该既有回答或结论的 source 引用标签，只能使用既有 schema 允许的 `answer_material` 或 `previous_answer_anchor`。

### `explicitly_dropped_sources.reason`

四种 reason 必须分别定义，且定义保持可区分：

- `superseded`：该 source 的业务内容已被更新、更完整或更权威的 source 替代，继续保留旧内容会过时、冲突或误导；replacement 中保留的是替代后的当前内容。
- `redundant`：该 source 的内容仍然有效，但其必要信息已被其它 retained source 或业务语义项完整表达；丢弃它不会损失独立业务信息。不得用它掩盖冲突或尚未被表达的信息。
- `out_of_scope`：该 source 即使有效，也与当前输入、当前会话任务及可预见后续对话无关，不需要进入本次 replacement。不得仅因内容难以分类、存在冲突或依据不足就标记为 out of scope。
- `policy_limit`：该 source 的内容仍相关且原本应保留，但当前 repair feedback 已明确给出一个具体 cap，并且为使完整 replacement 落入该 cap 而必须舍弃它。首次请求、没有 repair feedback、或当前 feedback 没有明示具体 cap 时禁止猜测或使用 `policy_limit`；也不得用它隐藏冲突、无依据内容或分类困难。

实现不得把上述 reason 改写成脆弱的固定优先级状态机；它们是对 source 实际业务关系的互斥解释。现有 coverage 规则仍决定每个 source 必须恰好被保留或显式丢弃。

## Affected file boundary

### Files allowed to change in the implementation slice

| File | Exact allowed change |
|---|---|
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | 仅在现有 output schema 说明中加入上述字段和 reason 的业务语义；保留 schema、示例、marker、repair schema 与其它规则 |
| `tests/host/test_llm_compaction.py` | 扩充 packaged asset owner test，逐字段和逐 reason 锁定上述语义与三项冻结纠正 |
| `tests/host/test_public_compact_smoke.py` | 在默认真实装配路径增加最小语义哨兵，继续用现有完整示例证明 parser/governance 接受，不复制完整 owner test |
| `docs/cli_init_workspace_manifest_v1.json` | 只更新 `config/prompts/scenes/conversation_compaction_user.md` 条目的真实 SHA-256 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 只更新由最终 manifest bytes 计算得到的 `FROZEN_MANIFEST_SHA256` |
| 新的 implementation gate artifact（后续 gate 创建） | 记录真实 changed files、digest、validation、docs decision、residual risk 与 completion status |

### Inspected but intentionally unchanged

- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/memory.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compaction_contract.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/manifests/conversation_compaction.json`
- `dayu/config/execution_profiles.json`
- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/cli_ci.md`
- 所有 README、design 与现有 review artifact

如实现发现必须修改以上 intentional-unchanged 文件中的 contract、Host 行为或 schema，立即停止该 slice 并返回 plan gate；不得扩大范围或用兼容逻辑绕过。

## Single implementation slice

### Slice S1 — Compactor output business semantics

- Objective：在 prompt owner 一次性补齐三个核心输出 section 和四种 drop reason 的业务解释，并同步 owner tests 与派生 publication digest。
- Expected outcome：fresh model 不再依赖英文命名猜测分类；三项冻结纠正被 deterministic contract 锁定；Host 行为和 schema 零变化。
- Prerequisites：本 plan 通过 plan review；两份 durable review input 的 SHA-256 与本计划记录一致。
- Dependencies：无跨 slice 依赖；本 work unit 只有此一个 implementation slice。
- Allowed files：严格限于上一节“Files allowed to change”表。

#### Exact implementation sequence

1. 在 `conversation_compaction_user.md` 的现有字段定义旁就地加入“Exact LLM-facing wording semantics”，不移动或重写无关 trust boundary、input schema、coverage、repair feedback 与完整同源示例。
2. 在 `tests/host/test_llm_compaction.py::test_prompt_assets_are_self_contained_for_fresh_v2_contract` 中增加按 section 分组的业务语义断言：
   - `session_summary` 同时出现整体上下文职责、source 同源、完整 replacement、accepted 后变为空、清除既有摘要；
   - `claim` 同时出现 `evidence_material` 与 `previous_evidence_fact` 两种直接支持来源；
   - `context_labels` 明确不是 claim 的直接依据，不能弥补 support；
   - `answer_anchors.title/detail/source_labels` 分别覆盖主题、既有结论及条件/不确定性、两种允许来源；
   - 四个 reason 各有独立业务定义，`policy_limit` 同时锁定“当前 repair feedback”“具体 cap”“首次请求/无具体 cap 禁止猜测使用”；
   - 保留现有 source-kind、repair、forbidden internal term 与完整 example 断言。
3. 在 `tests/host/test_public_compact_smoke.py::test_default_compactor_prompt_is_llm_facing_and_self_contained` 中只增加 assembled user template 的关键哨兵：`session_summary: null` 清除语义、previous evidence 直接支持、无具体 cap 禁止 `policy_limit`，以及四个 reason 均被定义。继续执行现有 example extraction、production parse 与 accept assertions。
4. 运行 prompt/Memory focused tests。若失败，修正 prompt owner 或测试期望；不得修改 Host owner 来迁就文案。
5. 对最终 `conversation_compaction_user.md` bytes 计算 SHA-256，只替换 frozen publication manifest 中该 asset 的 `content_sha256`；不得改其它 asset entry、目录集合或 manifest schema。
6. 对最终 `docs/cli_init_workspace_manifest_v1.json` bytes 计算 SHA-256，只更新 `FROZEN_MANIFEST_SHA256`；随后运行 publication/config assembly tests证明两级 hash 同源。
7. 运行完整 pyright、diff check、status 与 durable input digest 检查并创建 implementation artifact。implementation slice 本身在 code review 接受前不 stage/commit/push；review/fix/re-review 通过后，由 accepted slice checkpoint 只对该 slice intended artifacts 执行 Gateflow 允许的 stage/commit/push。

#### Call path, data flow, and invariants

数据流保持：packaged user prompt template -> production renderer 插入同一 compact input/可选 repair feedback -> model 输出完整 JSON -> strict parser -> Context Governance accept barrier -> accepted compact truth -> Memory 完整 replacement 投影。

必须保持的不变量：

- renderer 不增加新数据或推断，只机械渲染现有 template；
- 首次请求没有 repair feedback，因此没有具体 cap 时模型不能使用 `policy_limit`；
- repair 请求中的具体 cap 继续由现有 Memory policy/estimator 经 Context Governance issue message 同源产生；prompt 不复制固定 cap 数字；
- `session_summary: null` 不改变其它四个 semantic section，但会清空当前摘要；
- `context_labels` 不升级为 evidence support；
- drop reason 语义只指导模型，不改变 Host 的 enum、coverage 或 accept state transition；
- prompt 文本不得包含内部类型名、Host/Engine 治理状态、历史迁移术语或暗示兼容行为。

#### Error handling and stop conditions

- 若完整示例不再通过 production parser/governance，先检查文案是否误改 JSON fence、schema 或 marker；不得放宽 parser。
- 若具体语义与现有 typed source-kind 或 Memory projection 冲突，停止并回到 plan gate，不做下游 fallback。
- 若实现需要新的字段、enum、cap 注入、semantic verifier、Host 分支、README/design 变更或 frozen oracle/scenario 变化，停止并报告 scope drift。
- 若两份 durable input 的 digest 变化，停止并查明外部所有权；不得覆盖。
- focused test、publication test、pyright 或 diff check 未通过时，slice 不得声明完成。

#### Completion signal

五个计划中的代码/测试/publication 文件形成唯一 intended diff；所有验证通过；README/design 判定仍为 no-change；两份 durable input digest 不变；没有 blocking finding 或未分类 residual risk。

## Owner-level test matrix

| Contract | Owner-level assertion | Regression evidence |
|---|---|---|
| `session_summary.text/source_labels` | prompt 明确总体上下文职责、业务可读、直接来源、不得发明 | `test_prompt_assets_are_self_contained_for_fresh_v2_contract` |
| `session_summary: null` | prompt 明确完整 replacement、accepted 后摘要为空并清除既有摘要 | owner prompt test + 既有 `test_accepted_compact_without_summary_clears_prior_session_summary` |
| `evidence_facts.claim` | 同一字段定义显式包含 `evidence_material` 和 `previous_evidence_fact` 的直接支持 | owner prompt test |
| `context_labels` | 只提供背景/限定，不能直接支持 claim 或弥补 support | owner prompt test |
| `answer_anchors` | title/detail/source_labels 分别锁定既有回答主题、结论及边界、合法来源 | owner prompt test |
| `superseded` | 新内容替代旧内容，保留旧内容会过时/冲突/误导 | owner prompt test |
| `redundant` | 信息仍有效但已完整表达，drop 不损失独立信息且不能掩盖冲突 | owner prompt test |
| `out_of_scope` | 与当前任务/可预见后续无关，不能因难分类/冲突/依据不足滥用 | owner prompt test |
| `policy_limit` | 仍相关、当前 repair feedback 明示具体 cap、为满足 cap 必须 drop；首次/无具体 cap 禁止 | owner prompt test + assembled prompt sentinel |
| Existing JSON contract | 完整同源示例继续被 production parser 解析并由 accept barrier 接受 | existing public compact smoke |
| Publication truth | asset digest、manifest digest 与 FIRST publication tree 一致 | existing CLI frozen manifest tests |

测试不尝试证明模型一定按语义分类，也不新增 Host semantic verifier。真实模型遵循度只能由后续 real Compactor conformance work unit 观察。

## Manifest and hash update procedure

实现必须在 prompt 文本最终稳定后执行，避免把中间 digest 写入真源：

```bash
source .venv/bin/activate
sha256sum dayu/config/prompts/scenes/conversation_compaction_user.md
sha256sum docs/cli_init_workspace_manifest_v1.json
```

更新规则：

1. 第一条 digest 写入 `docs/cli_init_workspace_manifest_v1.json` 中唯一的 `config/prompts/scenes/conversation_compaction_user.md` 条目。
2. 保存 manifest 后重新计算第二条 digest，写入 `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256`。
3. 用测试验证实际 package publication tree；不得手工更新其它 prompt hash，不得修改历史 gate/review artifact 中记录的旧 hash。

## README and design trigger decision

- `dayu/config/README.md`：实施会触及 `dayu/config/`，已按触发规则检查。当前 README 已明确 compactor user prompt 必须自足说明输出字段含义、类型、必填性和允许值；本 work unit 是兑现该既有职责，不改变 prompts 目录职责、装配、配置 schema 或用户工作流，因此不更新。
- `tests/README.md`：实施会强化现有 `test_llm_compaction.py` 与 `test_public_compact_smoke.py` 的同一 Compactor LLM-facing conformance 层，不新增测试层级、运行方式或维护规则；当前 README 已覆盖 self-contained prompt、production parser/governance example 与 replacement 语义，因此不更新。
- `dayu/host/README.md` 与 `docs/host/design.md`：Host typed contract、accept barrier、repair projection和 Memory state transition均不变，不触发更新。
- 根 `README.md`：安装、初始化、CLI/Web/WeChat 入口、参数、输出、日志、workspace 位置和最终用户工作流均不变，不触发更新。
- `dayu/README.md`：分层、依赖方向和装配方式均不变，不触发更新。
- 其它 design 文档：没有架构、public contract shape、schema 或状态机变化，不更新。

若实际实现越过以上判断，必须停止并返回 plan gate，不能机械同步文档后继续扩大 scope。

## Validation commands

实现完成后按顺序运行：

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py -q
pytest tests/host/test_public_compact_smoke.py -q -k 'default_compactor_prompt_is_llm_facing_and_self_contained'
pytest tests/host/test_memory_projection.py -q -k 'accepted_compact_without_summary_clears_prior_session_summary'
pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
git status --short
sha256sum docs/reviews/pr-190-review-20260803-203709.md docs/reviews/plan-review-20260803-212134.md
```

预期结果：

- 所有 pytest 通过；不得把 opt-in real compactor skip 计作本 work unit 的行为证明；
- pyright 为 `0 errors`，无新增、扩散、掩盖或绕过；
- `git diff --check` 无输出；
- status 只包含单 slice 允许文件、后续 gate artifact，以及用户拥有的两份 durable review input；
- 两份 durable input digest 与本计划记录完全一致；
- 只有 Markdown prompt asset 是 production asset，未修改 Python production 文件；Python 单文件覆盖率目标不适用于该 prompt，现有相关 Python owner tests 继续运行。

## Risks, residual risks, and uncovered areas

- 风险：文案过长会增加模型认知负担。缓解：只在现有字段旁加入完成当前分类所需的短定义，不复制 Host 规则或实现术语。
- 风险：四种 reason 仍由模型做业务判断，deterministic tests 只能证明 contract 自足。分类为 `assigned to later work unit`；owner 是后续 real Compactor conformance evidence work unit，不在本 work unit 冒充已验证。
- 风险：`policy_limit` 可能被模型在无 cap 时从名称猜测。当前 slice 通过显式禁止语句和 owner test 固定；分类为 `fixed in current slice`。
- 风险：`session_summary: null` 文案若与 replacement projection 相反会导致摘要丢失且解释不一致。当前 slice 以现有 Memory regression 为真源固定；分类为 `fixed in current slice`。
- 风险：prompt bytes 变化导致 workspace publication manifest 漂移。当前 slice 通过两级真实 SHA-256 与 publication tests 固定；分类为 `fixed in current slice`。
- Uncovered area：frozen oracle/scenario 的 current-head readiness refresh。分类为 `assigned to later work unit`，owner 是独立 readiness refresh，不阻塞本 slice。
- Uncovered area：真实 provider 对字段分类与 repair cap 的稳定遵循度。分类为 `assigned to later work unit`，owner 是 real Compactor conformance evidence work unit。
- Uncovered area：`forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义。Controller 已将 AgentDS F01 裁决为 `deferred-with-owner`；owner 是后续独立 LLM-facing schema work unit，不阻塞本 slice。
- AgentDS F02 的 encoding concern 已由 Controller `rejected-with-reason`：两级 hash 命令和 publication test 均读取最终 raw bytes并 fail closed，不构成 residual risk，也不新增流程。

没有未分类 residual risk，没有需要用户裁决的新 issue，也没有 blocking open question。

## Why this is not over-designed

缺口是单一 LLM-facing 文本 owner 未解释现有 schema 语义。计划只修改该 owner、两个既有 owner/public-path tests，以及 prompt bytes 必然派生的两级 publication digest；不新增类型、模块、helper、schema、状态机、verifier、配置或兼容层。一个 implementation slice 足以完成实现和一次 review，继续拆分会人为制造中间 hash 漂移，扩张到 Host 或 readiness proof 则会跨越真实 owner boundary。

## Completion report format

后续 implementation artifact 和最终实现回报必须明确记录：

1. 改了什么：prompt 中新增的字段/reason 语义、owner tests、asset hash 与 manifest hash；
2. 验证了什么：逐条列出 focused pytest、publication tests、pyright、diff check 与 durable input digest；
3. README/design decision：逐个说明 no-change 理由；
4. 风险与未覆盖项：真实 provider conformance 与 readiness refresh 的后续 owner；
5. Gate state：implementation 完成后进入 `code review`；implementation slice 在 code review 接受前不得 stage/commit/push，接受后进入 accepted slice checkpoint，并继续按 Gateflow 自动推进，不能跳过 gate 或提前宣称 work unit 完成。

本 plan 的 re-review 通过后，自动进入 accepted plan commit；该 checkpoint 可 stage/commit/push 当前 plan gate 的 intended artifacts。此后在没有 Gateflow stop condition 时持续推进，直至 `final closeout pass`。
