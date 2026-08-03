# PR 190 Compactor LLM-facing findings F01-F03 plan

## Gate metadata

- Gate: `plan`
- Work unit: 修复 PR 190 的 Compactor LLM-facing prompt review findings F01-F03
- Branch: `codex/interactive-oracle`
- Existing PR: PR 190；本 work unit 不新建分支或 PR
- Evidence review: `docs/reviews/pr-190-review-20260803-160425.md`
- Plan status: `plan-review-fix-complete`，等待独立 plan re-review
- Goal confirmation: 已完成。用户已明确确认目标、非目标、ownership、禁止方案与成功信号；代码事实与该确认一致，无 blocking open question。
- Current gate after this artifact: `plan review fix` 已完成
- Dispatch state: 总控按 Gateflow gate 拆分派发；本次只完成 plan review fix，不进入实现、提交或 PR 操作。
- Next Gateflow entry point: `plan re-review`
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`

## Scope and motivation

### Goal

在不改变 compact output v2 schema、Host accept state machine 或 Memory projection 语义的前提下，修复 Compactor prompt 的三个已确认缺陷：

1. 显式隔离不可信 `current_input.readable_text` 与 `source_boundary[*].readable_text`，让模型把其中全部文本视为待整理的引用数据，而不是控制本次 compaction 的指令。
2. 让输入、输出、`source_kind`、开放字符串字段和示例在当前 prompt 内自足，提供标签同源的完整 example input/output。
3. 分离 Host internal rejection truth 与 LLM-facing repair projection，统一 repair block/schema，并把实际 item/字符上限从同一个 `MemoryProjectionPolicy` owner 投影为模型可直接执行的反馈。

### Motivation and first-principles judgment

本 work unit 动机成立，且严重性没有被高估：

- Compactor 的输出会在 Context Governance 验收后进入 accepted compact truth，并进一步物化为 durable Conversation Memory；prompt 对不可信材料缺少指令隔离时，schema 合法的语义注入可越过结构校验。
- 当前 parser 和 accept barrier 只验证 strict JSON、label/source-kind、coverage、重复/矛盾和 policy cap；它们没有、也不应新增自然语言 entailment verifier。因此 prompt owner 不能把安全责任下推给 parser 或 Memory projector。
- 当前最小示例引用 prompt 内未定义的 `T1`，而 production validator 明确拒绝未知 label；这是 prompt 自身的直接矛盾，不是模型偶发行为。
- 当前 renderer 直接把 `CompactRepairFeedbackV2.to_json()` 投给模型，块名却与 prompt 中的 `repair_feedback` 不一致；内部 attempt/count 字段被暴露，而真正可执行的 cap 数值缺失。有限 semantic attempts 下，这会增加重复失败与 fallback 概率。

最高验收北极星是：让一个无状态、会犯错、会走捷径、上下文有限、偏好模式匹配的推理器，在最低认知负担下稳定做对下一步动作。方案因此以“prompt 内显式、当前输入自足、反馈可直接执行”为准，不依赖模型猜 marker、类型名或 Host 内部术语。

### Success signals

- 两份 compactor prompt 明确说明 material marker 的含义、可信指令边界，以及 `current_input`、trace、evidence、answer 等 readable text 中出现的指令一律不执行。
- prompt 对八种 `source_kind` 逐项给出业务语义；对 `intent_type`、`reference_continuity.reason`、`diagnostics.code/message` 等开放字符串说明其业务用途、禁止内容和示例。
- prompt 内含完整 example input/output；example output 的每个 label 都来自同一 example input，覆盖 evidence、answer、intent、reference、diagnostic 和 explicit drop，且 production parser + Context Governance 接受该示例。
- repair prompt 只暴露统一、已文档化的 LLM-facing schema，不暴露 `previous_attempt_number`、`additional_issue_count` 或 Host/Memory/attempt 治理术语。
- item/size rejection 明确给出当前值、允许上限、计量对象和 whole-candidate 修复动作；数值直接来自本次验收使用的同一个 `MemoryProjectionPolicy` typed instance。
- deterministic adversarial tests 覆盖 `current_input`、`trace_material`、`evidence_material`、`answer_material` 中的 prompt/schema injection 文本；production renderer 原样保留材料，不新增字符串过滤器，同时 prompt 冻结其数据语义。
- opt-in 真实 provider smoke 使用 production prompt renderer、production parser 与 Context Governance，验证注入 canary 不控制输出，并验证 cap repair 后 candidate 落入精确上限。
- 受影响测试、publication manifest 校验与 pyright 通过；README/design 与实际 owner boundary 同步。

## Non-goals and scope boundary

### In scope

- Compactor system/user prompt 的 trust boundary、自足 schema、完整示例和 repair 说明。
- Host internal rejection report 到 LLM-facing repair JSON 的唯一 projection helper。
- Context Governance 已有 policy rejection message 的精确、业务可执行表述。
- Prompt contract、production parser/accept contract、prompt-injection adversarial、真实 provider smoke 测试。
- 因 package prompt asset 变更而必须同步的 frozen workspace publication hashes。
- 与当前稳定行为直接相关的 config/Host/tests README 和 Host design decision。

### Explicit non-goals

- 不扩张或重命名 `dayu.context_compaction.output.v2` 的任何字段，不新增 compact candidate 字段。
- 不添加旧 schema reader、兼容 alias、兼容 wrapper、loose parsing 或 fallback 字段。
- 不在 parser、Memory projector、RunInput、UI、Service、测试 fixture 或单一调用入口补偿错误语义。
- 不新增自然语言 entailment/provenance verifier，不让 Host 猜测候选文本是否蕴含于材料。
- 不新增 production 字符串过滤器、注入关键词黑名单或材料改写；不可信原文仍原样进入明确标注的数据块。
- 不新增 semantic repair loop，不改变 operation attempt budget、retry 次数、fallback tier、terminal state 或 durable event schema。
- 不修改 conversation compaction manifest、execution profile、provider/model selection、AgentPolicy、Memory cap 配置或 Memory estimator。
- 不修改 Conversation Memory、UI、CLI 行为，不处理 PR 190 其它 findings。

### Why this is not overdesigned

方案只改三个真正的 owner boundary：prompt asset、单次 proposal renderer、Context Governance policy reject 文本。它复用现有 strict output schema、typed feedback、`MemoryProjectionPolicy` 和 `estimate_memory_size_units`；不引入新的 verifier、policy 类型、state machine、repair loop、schema 版本或下游补偿。唯一新增的 production helper 是一个模块级、单向、纯 LLM-facing projection helper，用于消除当前 `to_json()` 直投造成的语义混合。

## Evidence read and direct findings

本 plan 已完整阅读根 `AGENTS.md`、review artifact、两份 compactor prompt、`conversation_compaction.json` manifest、`execution_profiles.json`、`dayu/host/llm_compaction.py`、`dayu/host/compaction.py`、`dayu/host/context_governance.py`，并核对相关 Host/config/tests README、`docs/host/design.md`、`docs/design.md`、prompt/parser/governance/public smoke tests与 frozen publication manifest。

| Evidence | Direct fact | Plan consequence |
|---|---|---|
| `conversation_compaction.md` | 仅写“依据 source_boundary”，没有定义 `UNTRUSTED_COMPACTION_MATERIAL_JSON_*` 或材料内指令的信任语义 | F01 必须在 prompt owner 修复 |
| `conversation_compaction_user.md` | 八种 `source_kind` 只有字面量；开放字符串只要求非空；最小输出示例引用未定义 `T1` | F02 必须补业务语义和同源 example pair |
| `llm_compaction.py::_compaction_request_prompt_block_vnext` | renderer 原样 JSON 序列化后只加未解释 marker | 保留原文与 marker；由 prompt 明确解释，不过滤文本 |
| `llm_compaction.py::_user_prompt_vnext` | `PREVIOUS_VALIDATION_REPORT_JSON` + `repair_feedback.to_json()` 直接投给模型 | 新增唯一 repair projection，并统一 marker/schema |
| `compaction.py::CompactRepairFeedbackV2` | 同一 `to_json()` 包含 attempt、issues、additional count、required action | 继续作为 Host-internal bounded transport/serialization；不得再直接等同 LLM projection |
| `context_governance.py::_collect_policy_issues/_section_caps` | 已持有实际 `MemoryProjectionPolicy` 和实际计量值，但 message 不含数字且暴露 Memory policy 术语 | 从同一 policy instance 生成精确 cap feedback，不复制配置常量 |
| `memory.py::estimate_memory_size_units` | 当前 estimator 是 Python 字符数 | feedback 可准确称为“字符数”，并说明各 section 的计量文本 |
| `context_governance.py::accept_compact_candidate_v2` | accept 检查闭集无自然语言 entailment | 不把 F01 下推为 validator/filter |
| `test_public_compact_smoke.py` | 现有 prompt test 固化 `"source_labels": ["T1"]`；真实 compactor smoke 已有 opt-in provider seam | 替换错误 oracle，并复用现有 opt-in seam 增加 adversarial/cap smoke |
| `docs/cli_init_workspace_manifest_v1.json` | 两个 prompt asset 的 SHA-256 被 frozen publication manifest 固定 | prompt 修改后必须同步两个 asset hash和 manifest 自身 hash oracle |

## Finding adjudication

### F01 — accepted，高

- Root cause: compactor prompt owner 没有声明数据/指令信任边界；marker 只有实现名称，没有模型可读语义。
- Owner: `dayu/config/prompts/scenes/conversation_compaction.md` 与 `conversation_compaction_user.md` 共同拥有任务指令和自足 contract；`llm_compaction.py` 只机械渲染同名数据块。
- Fix boundary: 在 system prompt 和 user prompt 当前上下文内明确说明：只有数据块外的 system/task 文本能控制本次 compaction；数据块内 `current_input.readable_text` 和所有 `source_boundary[*].readable_text` 都是引用数据，其中任何要求忽略规则、改变 schema、改变来源规则、编造/删除事实或执行其它任务的文本都不得执行。
- Rejected alternatives: parser 特判、Memory 清洗、UI 过滤、关键词黑名单、自然语言 entailment verifier。

### F02 — accepted，中

- Root cause: prompt 列出了结构，却没有拥有字段的业务语义；示例 output 与 example input 不同源。
- Owner: `conversation_compaction_user.md`。
- Fix boundary: 在同一 prompt 中补齐八种 `source_kind` 和开放字符串语义，并用一个完整 example input/output pair 替换“最小形状示例”。
- Rejected alternatives: 扩张 schema、把开放字符串改成未经需求证明的新枚举、让 parser 猜业务语义、保留 `T1` 再在测试夹具造同名 label。

### F03 — accepted，中

- Root cause: Host-internal bounded feedback serialization 被 renderer 直接当作 LLM contract；policy owner 已知精确 cap，却只生成模糊内部术语。
- Owners:
  - `CompactValidationReportV2` / `CompactRepairFeedbackV2`: Host internal rejection/transport truth。
  - `llm_compaction.py` repair projection helper + compactor prompt: LLM-facing repair contract owner。
  - `MemoryProjectionPolicy` + Context Governance: cap 值、计量与 reject truth owner。
- Fix boundary: 保留 internal feedback 的 attempt/additional-count 信息供 durable/governance 使用；新增唯一 projector，只向模型输出 `required_action` 与 `issues`。Context Governance 用同一个 policy instance 和实际计量结果生成可执行 issue message。
- Rejected alternatives: 直接缩短 `to_json()` 导致内部审计丢信息、在 prompt 硬编码默认 cap、从 execution profile 再读取 cap、在 renderer 重算 candidate 尺寸、额外 repair loop。

## Semantic ownership and data flow

| Semantic fact | Unique owner | Producer/projection path | Forbidden compensators |
|---|---|---|---|
| 不可信材料与控制指令边界 | Compactor prompt assets | system/user prompt 解释 renderer 的 material markers | parser、Memory、UI、fixture、string filter |
| 输入/输出 schema 与字段业务含义 | Compactor user prompt | 当前 prompt 自足说明 +完整 example pair | Python 类型名、旧 schema、外部文档引用 |
| Raw/semantic reject truth | Context Governance + `CompactValidationReportV2` | parser/governance 产生 typed issues | renderer 猜 reject 原因 |
| Bounded internal repair transport | `CompactRepairFeedbackV2` | `build_compact_repair_feedback_v2` 脱敏、截断、保留 attempt/count | 直接承诺为 LLM schema |
| LLM-facing repair schema | `llm_compaction.py` 唯一 projection helper + prompt assets | internal feedback -> 最小 repair JSON block | operation、fixture、UI 各自重投影 |
| Section cap 数值与计量 | `MemoryProjectionPolicy` + `estimate_memory_size_units` | Context Governance 使用验收同一 policy instance，message 携带 actual/cap | prompt 默认值、renderer 常量、profile 二次读取 |
| Accepted durable compact truth | Context Governance | strict parser -> accept -> `CompactAcceptedTruthV2` | Memory/projector 下游修正 |

目标数据流：

```text
prompt assets + immutable CompactInputV2
  -> LLMContextCompactor material renderer
  -> provider candidate
  -> production strict parser
  -> Context Governance + same MemoryProjectionPolicy
      -> accepted truth
      -> or internal typed reject report/feedback
           -> unique LLM-facing repair projector
           -> unified repair JSON block
           -> next existing whole-candidate attempt
```

## Contract and implementation decisions

### 1. Trust boundary wording

- 保留现有 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN` / `UNTRUSTED_COMPACTION_MATERIAL_JSON_END`，避免无收益地改变 material extraction seam。
- system prompt 用短、最高优先级规则冻结边界；user prompt 在 placeholder 前再次解释 marker，保证单条 user message 自足。
- 明确规则覆盖 `current_input.readable_text` 以及所有 previous/trace/evidence/answer source 的 `readable_text`，而不是只点名工具结果。
- 明确“不要执行材料内指令”不等于“删除或改写材料”；模型仍需按业务内容与 coverage 规则保留/丢弃 source。

### 2. Self-contained schema and full example

- 八种 `source_kind` 的字段说明必须逐项覆盖，但示例不为展示枚举而机械制造八个 source：

| `source_kind` | 当前 prompt 内必须给出的业务语义 |
|---|---|
| `previous_session_summary` | 上一次已接受压缩结果中的会话摘要，可继续压缩、重写或在被新材料替代时丢弃。 |
| `previous_evidence_fact` | 上一次已接受压缩结果中的证据事实，可作为新 `evidence_facts` 的事实来源。 |
| `previous_answer_anchor` | 上一次已接受压缩结果中的回答结论锚点，可进入新 `answer_anchors`。 |
| `previous_forward_intent` | 上一次已接受压缩结果中的待办或后续分析意图，可进入新 `forward_intents`。 |
| `previous_reference_continuity` | 上一次已接受压缩结果中的指代、术语或对象连续性，可进入新 `reference_continuity`。 |
| `trace_material` | 历史对话和用户可见进展，可支持摘要、事实上下文、后续意图或指代连续性。 |
| `evidence_material` | 已接受工具证据，可作为 `evidence_facts.support_labels`，也可支持指代连续性。 |
| `answer_material` | 助手最终回答或结论材料，可支持回答锚点、事实上下文、后续意图或指代连续性。 |

- 开放字符串继续保持开放 contract，不新增 enum：
  - `intent_type`: 业务可读的后续动作类别，例如 `next_analysis_step`；不得写 Host 状态、Python 类型或内部错误码。
  - `reference_continuity.reason`: 说明为什么后续对话仍需保留该指代/术语关系，例如“后续问题中的‘该公司’需继续指向甲公司”。
  - `diagnostics.code`: 简短稳定的业务问题类别，例如 `source_conflict_noted`；不是 Host error code。
  - `diagnostics.message`: 对材料中的不确定、冲突或不可可靠整理之处作业务可读说明；不得代替 coverage。
- 完整 example pair 只使用四个 boundary labels：`E1` 支撑 evidence，`A1` 支撑 answer，`T1` 支撑 intent/reference，`D1` 展示 explicit drop；diagnostic 只引用 `E1/A1`，不参与 represented coverage。它展示全部必要输出区，但不追求在示例中逐一演示八种 `source_kind`。
- example output 同时展示 session summary、evidence fact、answer anchor、forward intent、reference continuity、diagnostic 和 drop；所有 label 只来自同一个 example input，并明确 example labels 仅用于示范、真实请求必须使用真实 boundary labels。
- 示例不改变 production output schema，也不引入可选字段或别名。

已验证的 production-valid example input JSON 草稿：

```json
{
  "schema": "dayu.context_compaction.input.v2",
  "current_input": {
    "readable_text": "继续比较甲公司收入增长与盈利质量。"
  },
  "source_boundary": [
    {
      "source_label": "E1",
      "source_kind": "evidence_material",
      "readable_text": "工具证据：甲公司2025年收入100亿元，同比增长10%。"
    },
    {
      "source_label": "A1",
      "source_kind": "answer_material",
      "readable_text": "上一回答结论：收入增长，但需继续核对利润率。"
    },
    {
      "source_label": "T1",
      "source_kind": "trace_material",
      "readable_text": "用户可见进展：下一步比较毛利率；“该公司”指甲公司。"
    },
    {
      "source_label": "D1",
      "source_kind": "previous_session_summary",
      "readable_text": "已被上述新材料完整替代的旧摘要。"
    }
  ]
}
```

与上方输入同源的 production-valid example output JSON 草稿：

```json
{
  "schema": "dayu.context_compaction.output.v2",
  "session_summary": {
    "text": "正在分析甲公司收入增长与盈利质量。",
    "source_labels": ["E1", "A1", "T1"]
  },
  "evidence_facts": [
    {
      "claim": "甲公司2025年收入100亿元，同比增长10%。",
      "support_labels": ["E1"],
      "context_labels": []
    }
  ],
  "answer_anchors": [
    {
      "title": "当前结论",
      "detail": "收入增长，利润率仍待核对。",
      "source_labels": ["A1"]
    }
  ],
  "forward_intents": [
    {
      "intent_type": "next_analysis_step",
      "text": "比较甲公司毛利率。",
      "status": "open",
      "source_labels": ["T1"]
    }
  ],
  "reference_continuity": [
    {
      "text": "“该公司”指甲公司。",
      "reason": "后续问题沿用该简称。",
      "source_labels": ["T1"]
    }
  ],
  "diagnostics": [
    {
      "code": "source_conflict_noted",
      "message": "收入增长已有证据，利润率仍待核对。",
      "source_labels": ["E1", "A1"]
    }
  ],
  "explicitly_dropped_sources": [
    {
      "source_label": "D1",
      "reason": "redundant"
    }
  ]
}
```

Plan-fix gate 已把上方 LLM-facing input 草稿构造成对应 `CompactInputV2` typed input，并执行现有
`parse_conversation_compact_output_vnext` 与 `accept_compact_candidate_v2`。结果为 parser 通过、governance accepted；
`E1/A1/T1` 形成 represented coverage，`D1` 形成 explicit drop，二者互斥且并集精确等于全部 boundary labels。

### 3. Unified repair projection

- 在 `llm_compaction.py` 增加模块级私有纯函数，签名明确为
  `_repair_feedback_prompt_json_vnext(feedback: CompactRepairFeedbackV2) -> dict[str, JsonValue]`。函数直接读取
  `feedback.required_action` 与 `feedback.issues`，并直接读取每个 typed issue 的 `code.value`、`json_path`、
  `message`、`source_labels`；不得先调用 `feedback.to_json()`，不得接受或解析 raw mapping。函数只投影：
  - `required_action`: 非空字符串，要求从同一输入重建一个完整 JSON object，不复制、拼接、补写前次输出。
  - `issues`: 非空 array；每项精确包含 `code`、`json_path`、`message`、`source_labels`。
- `_user_prompt_vnext` 只调用该 helper，并用统一 `REPAIR_FEEDBACK_JSON_BEGIN` / `REPAIR_FEEDBACK_JSON_END` 包裹 JSON。
- user prompt 对 marker、顶层字段、issue 四字段的类型/含义/必填性，以及 whole-candidate 动作作完整说明。
- `previous_attempt_number`、`additional_issue_count` 保留在 Host internal feedback/durable projection，但不进入 LLM-facing repair block；`CompactRepairFeedbackV2.to_json()` 的 docstring 改为明确 internal serialization，防止再次被误用。
- 不在 projector 中读取 profile、policy 或 candidate；它只投影 owner 已生成的 bounded typed feedback。

### 4. Exact policy feedback

- 直接在 `context_governance.py::_collect_policy_issues` 的 `_issue(...)` message 参数中构造
  `session_summary.text 当前 {actual} 个字符，上限 {cap} 个字符；请直接缩减 session_summary.text 到不超过 {cap} 个字符。`。
  `actual` 来自本次已计算的 `estimate_memory_size_units(...).units`，`cap` 来自同一个
  `policy.session_summary_char_cap`。
- 直接在 `context_governance.py::_section_caps` 的 `_issue(...)` message 参数中构造四个 section 的 item reject：
  `{section} 当前 {actual} 项，上限 {cap} 项；请直接删减或合并该 section，保留不超过 {cap} 项。`。
  `actual` 是 `len(texts)`，`cap` 是调用方从同一个 policy instance 传入的 item cap。
- 四个 section 的 aggregate size reject写明当前字符数、size cap 与计量对象：
  - evidence facts: 各 `claim` 字符数之和；
  - answer anchors: 每项 `title + "\\n" + detail` 的字符数之和；
  - forward intents: 各 `text` 字符数之和；
  - reference continuity: 各 `text` 字符数之和。
- 直接在 `_section_caps` 构造 aggregate size reject message：
  `{section} 的{计量对象}当前合计 {actual} 个字符，上限 {cap} 个字符；请直接缩减该 section 的文本总量到不超过 {cap} 个字符。`。
- message 使用“字符数/项数”和直接缩减动作，不出现 `Memory policy`、Host、Attempt 或内部类型名。
- 原数据流已经持有 policy cap，并已经计算或可以在原判断点命名 `actual`；缺陷是当前 message 没有携带这些值。
  修复只改 owner 处的 message 构造，不新增 issue/schema 字段。projector 不读取 policy、不读取 candidate、不重算 actual/cap。

## Affected files and modules

### Production/prompt files

| File | Planned change |
|---|---|
| `dayu/config/prompts/scenes/conversation_compaction.md` | 增加最高优先级材料信任边界和统一 repair 行为 |
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | 自足输入/输出语义、八种 source kind、开放字符串、完整 example pair、统一 repair schema |
| `dayu/host/llm_compaction.py` | 新增唯一 LLM repair projector；统一 repair markers；停止直投 `feedback.to_json()` |
| `dayu/host/compaction.py` | 仅澄清 `CompactRepairFeedbackV2`/`to_json()` 是 Host-internal bounded transport/serialization；不改 compact output schema |
| `dayu/host/context_governance.py` | 从同一 Memory policy/estimator 生成精确 actual/cap 与计量说明 |

### Tests and publication oracle

| File | Planned change |
|---|---|
| `tests/host/test_llm_compaction.py` | renderer/trust/repair-schema/adversarial 文本与 prompt example production-parser contract |
| `tests/host/test_compaction_contract.py` | owner-level exact cap feedback assertions，覆盖 == cap 与 +1 及实际数值投影 |
| `tests/host/test_public_compact_smoke.py` | 删除固定未定义 `T1` oracle；加入完整 example contract 与 opt-in real-provider injection/cap smoke |
| `tests/host/public_smoke_support.py` | 复用既有精确环境失败分类，为 Mimo -> DeepSeek 测试级 fallback 暴露非跳过式分类结果；不改 production provider 路由 |
| `docs/cli_init_workspace_manifest_v1.json` | 更新两个 prompt asset 的真实 SHA-256 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 更新 frozen manifest 自身 SHA-256 常量 |

### Documentation

| File | Planned change |
|---|---|
| `docs/host/design.md` | 写回 internal rejection truth / LLM repair projection 分离、policy-derived cap、prompt trust boundary 决策 |
| `dayu/config/README.md` | 更新当前 compactor prompt asset contract；该 README 无独立 Agent 更新约束，按根触发规则只写 config/prompt 当前职责 |
| `dayu/host/README.md` | 更新已实现 Host compactor renderer/repair owner boundary；遵守其“不写未来计划/测试清单”约束 |
| `tests/README.md` | 更新已存在测试覆盖与 opt-in real smoke 命令，不写实现流水账 |

### Inspected but intentionally unchanged

- `dayu/config/prompts/manifests/conversation_compaction.json`: scene routing、AgentPolicy 和 tool disable 与 findings 无关。
- `dayu/config/execution_profiles.json`: Memory caps 保持唯一配置真源，不把 cap 复制到 prompt。
- `dayu/host/compaction_operation.py`: 现有 whole-candidate attempt loop 与 budget 不变。
- `dayu/host/memory.py` 及 Memory projector: estimator/policy 已是正确 owner，不做下游补偿。
- root `README.md`: 无安装、入口、命令或最终用户 workflow 变化。
- `dayu/README.md`: 无分层或装配关系变化。
- UI/Service/Engine/Fins: 不在本 work unit owner boundary。
- `docs/reviews/pr-190-review-20260803-160425.md`: 用户确认 ownership 的未跟踪 evidence artifact，原样保留，不改写、不删除。

## Implementation slices

### Slice S1 — Prompt trust boundary and self-contained contract

- Objective: 闭合 F01 与 F02 的 prompt owner 缺陷。
- Expected outcome: 两份 prompt 明确 data/instruction boundary；user prompt 含完整、production-valid example input/output 与自解释字段语义。
- Allowed files:
  - `dayu/config/prompts/scenes/conversation_compaction.md`
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_public_compact_smoke.py`
- Prerequisite: 无；保留当前 v2 schema 和 material markers。
- Exact allowed changes:
  - 增加本文“Trust boundary wording”规则。
  - 按本文固定的八种 source kind 业务含义和 open string 语义改写 schema 说明。
  - 用本文已通过 production owner 验证的 `E1/A1/T1/D1` 完整 example pair 替换当前 `T1` 最小形状示例。
  - 在 `test_default_compactor_prompt_is_llm_facing_and_self_contained` 中明确删除旧固定断言
    `assert '\"source_labels\": [\"T1\"]' in user_prompt_template`；不以另一条固定 label 字符串断言替代。
  - 测试从 prompt 提取 example JSON；构造同源 typed `CompactInputV2`，用 production parser 解析 output，再由 Context Governance 接受。
  - 参数化注入材料位置为 current/trace/evidence/answer；S1 仅静态断言原文仍在 data block、prompt 明确禁止执行、没有 production filter。S1 不声称验证模型行为；行为只由 S3 real provider observation 验证。
  - 在 S1 审查现有 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` / `_FORBIDDEN_COMPACTOR_MATERIAL_TERMS`，并补入本次可能泄漏的内部实现术语；业务可读 contract 字段名不列为禁止词。
- Non-goals: 不改 parser、candidate dataclass、source-kind enum、accept barrier、Memory。
- Validation:
  - `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q`
  - `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -k 'default_compactor_prompt or prompt_contract or prompt_example or adversarial'`
- Completion signal: F01/F02 对应 deterministic owner contract 全绿，example output 被 production parser/governance 接受。
- Stop condition: example 无法在不改变 output schema 的前提下通过 production owner，或 source kind 的业务所有权出现新冲突。

### Slice S2 — Internal rejection truth and LLM repair projection

- Objective: 闭合 F03，保持内部 truth 完整，同时把 LLM-facing schema 收窄且可执行。
- Expected outcome: renderer 不再直投 internal `to_json()`；repair block 名称/schema/prompt 完全一致；cap feedback 含同源 exact values。
- Allowed files:
  - `dayu/host/llm_compaction.py`
  - `dayu/host/compaction.py`
  - `dayu/host/context_governance.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_compaction_contract.py`
- Prerequisite: S1 的 prompt repair section 已定义统一 marker/schema。
- Exact allowed changes:
  - 新增一个模块级私有纯 projector，并由 `_user_prompt_vnext` 唯一调用；签名和字段读取严格按本文“Unified repair projection”，不经过 `to_json()` 或 raw mapping。
  - repair block 只含 `required_action` 和 `issues`；issue exact keys 固定为 `code/json_path/message/source_labels`。
  - internal attempt/count 保留，但测试明确断言不出现在 LLM prompt。
  - 直接修改 `_collect_policy_issues/_section_caps` 的 `_issue(...)` message 构造，按本文“Exact policy feedback”嵌入 actual、cap、计量对象和直接缩减动作；不新增 schema 字段。
  - 保留现有脱敏、单 issue 上限、issue count 上限和总体 feedback 上限；验证实际 projected block 同样不越界。
  - 增加 all-section simultaneous cap reject：session summary size、四个 section item count、四个 section aggregate size 同时超限，形成九条 policy issues，再经 internal bounded feedback 和 typed projector 投影。
- Call path: candidate -> `accept_compact_candidate_v2` -> `CompactValidationReportV2` -> `build_compact_repair_feedback_v2` -> private LLM repair projector -> `_user_prompt_vnext`。
- Error handling/invariants:
  - projector 只接收 typed feedback，不接受 raw mapping。
  - renderer 不读取 policy，不重算 cap。
  - internal feedback 仍可进入 private projection artifact/audit；LLM block 不暴露治理字段。
  - repair 仍是现有 whole-candidate attempt；无新增 loop/state transition。
- Non-goals: 不改 durable event schema、不改 attempt budget、不移动 Context Governance accept ownership。
- Validation:
  - `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q`
- Expected assertions:
  - repair markers 唯一配对且 JSON 可解析；exact keys 与 prompt 描述一致。
  - secret probes 不回流；projected feedback 不超过现有总长 cap。
  - `previous_attempt_number`、`additional_issue_count`、`Memory policy`、Host/Attempt 类型术语不在 LLM block。
  - item cap 在 `== cap` 接受、`cap + 1` 拒绝；反馈包含真实 count/cap。
  - size cap 在 `== cap` 接受、`cap + 1` 拒绝；反馈包含真实 char count/cap 和计量字段。
  - simultaneous reject 的 projected feedback 总长不超过 `MAX_COMPACT_REPAIR_FEEDBACK_CHARS`；九条 message 的关键 actual、cap、计量对象和直接动作均完整保留，未被单 issue 或总体边界截断。
- Completion signal: F03 owner-level contract 和 renderer contract 全绿。
- Stop condition: 实际 projected block 无法在现有 bounded feedback 限制内自足，或需要修改 output schema/attempt state machine 才能完成。

### Slice S3 — Real provider adversarial smoke and publication oracle

- Objective: 用真实 provider 验证 prompt 控制面，并同步 package publication 真值。
- Expected outcome: opt-in real provider 对 current/trace/evidence/answer injection 只按数据处理；带 exact cap repair feedback 的 candidate 通过 production parser/governance且落入 cap。
- Allowed files:
  - `tests/host/test_public_compact_smoke.py`
  - `tests/host/public_smoke_support.py`
  - `docs/cli_init_workspace_manifest_v1.json`
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`
- Prerequisites: S1/S2 完成；production prompt/renderer/cap feedback 已稳定。
- Exact allowed changes:
  - 复用现有 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1`，先检查并使用 `PROVIDER_CASES[0]`（Mimo）。
  - 只有 `MIMO_PLAN_API_KEY` 缺失/空，或 Mimo 的真实调用失败被 `public_smoke_support.py` 既有 network/transient unavailable/explicit unavailable/quota-rate-limit 精确分类判定为环境不可用时，才改用 `PROVIDER_CASES[1]`（DeepSeek）。Mimo 的其它失败必须 fail，不得 fallback。
  - DeepSeek credential 也缺失/空，或 DeepSeek 也被同一既有精确分类判定为环境不可用时，按包含两路原因的精确消息 skip；不得继续回落到 `PROVIDER_CASES[2]` Gemini 或 `PROVIDER_CASES[3]` Qwen。
  - 若既有 skip helper 当前以 `pytest.skip` 作为控制流，则只在 `public_smoke_support.py` 的测试基础设施 owner 内抽取可复用的“分类结果/原因”helper，让既有 skip helper 与 Mimo -> DeepSeek selector 共用同一组 marker 真源；不得在 smoke 测试复制 marker 或解析 skip 文本。
  - 构造单个 typed input，同时放入 current、trace、evidence、answer 四类不同 injection canary；业务内容仍足以形成合法 candidate。
  - 由 production Context Governance 对一个确定性超 cap candidate 产生 real repair feedback，再用 production prompt renderer 发起一次真实 provider proposal；不新增 operation repair loop。
  - raw final 必须经 `parse_conversation_compact_output_vnext`，随后经使用同一 test policy instance 的 `accept_compact_candidate_v2`；断言 accepted、item/size 不超过反馈 cap。
  - 行为 oracle 只断言注入命令没有被执行，且候选没有制造注入命令要求的虚假事实或 schema 变更。允许模型把攻击文本作为材料风险写入业务可读 diagnostic；不得用“攻击文本任何片段均不得出现在输出”作为 oracle。
  - canary 检查仅是 smoke oracle，不进入 production 字符串过滤。
  - S3 implementation artifact 必须记录实际 provider（Mimo 或 DeepSeek）以及发生 fallback/skip 时的精确环境分类；pass/skip 报告不得只写“real provider”。
  - 重新计算两个 prompt asset SHA-256，更新 frozen publication manifest；再计算 manifest SHA-256，更新测试常量。
- Non-goals: 不让 nondeterministic provider smoke替代 deterministic contract tests；不扩到四 provider matrix。
- Validation:
  - `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q`
  - credential 可用时：`source .venv/bin/activate && DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py -q -k 'real_compactor'`
- Completion signal: deterministic publication checks通过；真实 provider smoke 优先在 Mimo 通过，或按上述唯一条件在 DeepSeek 通过；两者都不可用时仅因既有精确 credential/network/quota 分类 skip，并在实现 artifact 中记录实际 provider/两路不可用原因。
- Stop condition: provider 返回表明 prompt contract 仍不自足，或真实输出只有通过 production filter/verifier/schema 扩张才能接受。

### Slice S4 — Documentation and aggregate validation

- Objective: 写回稳定 owner decision 并完成受影响验证。
- Expected outcome: design/README 描述与已实现代码一致，所有 focused tests 和 pyright 通过。
- Allowed files:
  - `docs/host/design.md`
  - `dayu/config/README.md`
  - `dayu/host/README.md`
  - `tests/README.md`
- Prerequisites: S1-S3 implementation/review accepted。
- Exact allowed changes:
  - design 固定 trust boundary、internal truth/LLM projection 分离与 Memory-policy-derived cap；不写 work-unit 过程。
  - config README 说明当前 packaged prompt 的 self-contained material/repair contract。
  - Host README 说明当前 renderer/projector owner boundary，不列测试命令或未来计划。
  - tests README 说明新增 deterministic + opt-in real smoke 覆盖和真实运行命令。
  - 复核 S1/S4 的 LLM-facing 文本不含 Host/Memory/Attempt、Python 类型名、迁移名或其它非任务所需内部术语；若发现新的泄漏类别，同步更新 owner 级禁止术语检查。
- Non-goals: 不更新 root README/dayu README，不写 PR/finding 流水账。
- Validation:
  - `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_public_compact_smoke.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- Coverage expectation: 修改过的 Python production 文件以 targeted coverage 检查为准，单文件目标不低于 80%；prompt/README/design/JSON 不适用 Python 单文件覆盖率。
- Completion signal: docs decision 完成、focused regression 与 pyright 无新增/扩散错误、diff 无 whitespace error。
- Stop condition: validation failure 暴露 schema/owner/state-machine 变更需求，必须回到 plan 裁决，不用兼容分支绕过。

## Test matrix and expected assertions

| Layer | Test | Expected assertion |
|---|---|---|
| Prompt contract | prompt assets static checks | marker 语义、trust boundary、八种 source kind、open-string 业务说明、repair exact schema 全部存在且无内部术语 |
| Example contract | prompt example extraction + production parser/governance | output JSON exact v2；全部 label 来自 example input；coverage exact partition；candidate accepted |
| Renderer adversarial | current/trace/evidence/answer 参数化 canaries | 仅验证静态 prompt/data boundary：原文不被 production 过滤；全部位于 untrusted block；控制规则位于 block 外并明确禁止执行；不声称验证模型行为 |
| Repair projector | internal feedback -> rendered prompt | block exact keys；不含 attempt/additional count；required action whole-candidate；脱敏/有界 |
| Policy owner | each section item/size + summary size；all-section simultaneous reject | `== cap` accepted，`+1` rejected；message actual/cap 与传入 policy instance 完全一致；九条同时拒绝仍完整、有界且保留 action |
| Parser regression | existing strict parser matrix | duplicate/unknown/missing/type/enum/blank 继续 fail closed；不接受 alias/旧 schema |
| Public/default smoke | default prompt/material tests | 删除 `assert '\"source_labels\": [\"T1\"]' in user_prompt_template`；改由同源 example extraction + parser/governance contract 验证；默认装配仍从 manifest/profile 读取真实 assets |
| Real provider smoke | opt-in Mimo-first、DeepSeek-only fallback | 行为观察确认注入命令未执行且未制造其要求的虚假事实；允许 diagnostic 说明材料风险；repair 后 parsed candidate accepted 且落入 cap；artifact 记录实际 provider |
| Publication | frozen manifest tests | 两个 prompt hash、manifest hash 与 production publication tree 同源 |
| Type/static | pyright + diff check | 无新增或扩散类型错误；无 whitespace error |

## Validation commands

Implementation 完成后按顺序执行：

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q
pytest tests/host/test_public_compact_smoke.py -q
pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

有真实 provider credential 时追加：

```bash
source .venv/bin/activate
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py -q -k 'real_compactor'
```

若修改过的 production Python 文件需要单文件覆盖率证据：

```bash
source .venv/bin/activate
coverage erase
coverage run -m pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py
coverage report --include='dayu/host/llm_compaction.py,dayu/host/compaction.py,dayu/host/context_governance.py'
```

## Documentation decision

- `docs/host/design.md`: 必须更新。现有设计只允许 Host-neutral validation 摘要，但没有固定 internal report 与 LLM projection 分离，也没有规定 cap 数值从 policy owner 进入 feedback。
- `dayu/config/README.md`: 必须更新。prompt asset 的当前稳定 contract 从“schema/示例”提升为显式 untrusted data boundary、完整 example pair 和统一 repair block。
- `dayu/host/README.md`: 必须更新。`dayu/host` renderer/projector 与 Context Governance 的当前稳定 owner boundary 发生变化。
- `tests/README.md`: 必须更新。测试覆盖新增 prompt injection、production example parser 与 opt-in real cap repair smoke。
- root `README.md`: 不更新，无用户可见安装/CLI/workflow/排障变化。
- `dayu/README.md`: 不更新，无层级、依赖方向或装配关系变化。
- `docs/design.md`: 不更新；仓库级分层原则未变化，Host 专题 design 已是正确决策位置。

## Risks, residual risks, and uncovered areas

| Risk | Classification | Mitigation/owner |
|---|---|---|
| Prompt instruction不能数学证明自然语言忠实性 | assigned to later work unit / existing evaluation scope | 当前以 explicit trust boundary + deterministic static contract + S3 real provider behavior observation 降低风险；完整 Conversation Memory eval 仍由既有 Issue 80 owner |
| 真实 provider 输出存在随机性或 credential/network/quota 不可用 | requiring explicit environment evidence at implementation | Mimo-first；仅按既有精确环境分类 fallback 到 DeepSeek；两者均不可用才精确 skip；不得用 fake 结果冒充 real smoke。若非环境原因失败，阻断关闭 |
| 完整 example 增加 prompt token 数 | fixed in current slices | 保持单一紧凑 example pair；S1 测量 rendered prompt，public bounded smoke验证无明显膨胀 |
| Cap 字符数对多字节字符的直觉可能与 token 不同 | fixed in current slices | 明确它是与现有 owner 同源的字符数，不称 token；不更换 estimator |
| Internal feedback 仍保留 attempt/count 字段 | fixed in current slices | 唯一 LLM projector exact-key 丢弃它们；tests 同时断言 internal 保留、LLM 不可见 |
| 测试 canary 可能被模型作为“检测到注入”的 diagnostic 引用 | fixed in current slices | 允许模型把攻击文本作为材料风险说明；oracle 只拒绝执行注入命令或制造其要求的虚假事实，不用全字符串禁见规则误报 |
| PR 190 其它代码与本 work unit 同 branch，工作树范围很大 | covered by Gateflow checkpoint discipline in later gates | 每个 slice 只 stage approved files；plan-only 本轮不提交；未跟踪 review artifact 保留 |

当前无 unclassified residual risk。

## Open questions

- Blocking open questions: 无。
- Non-blocking implementation choice: 无。真实 provider 选择已冻结为 `PROVIDER_CASES[0]` Mimo-first、仅按既有精确环境不可用分类 fallback 到 `PROVIDER_CASES[1]` DeepSeek；不得扩成 provider matrix 或回落 Gemini/Qwen。

## Completion report format for later implementation

后续 implementation/final closeout 应只基于实际证据报告：

1. 改了什么：按 F01/F02/F03 和 owner boundary 列出 prompt、repair projection、policy feedback、tests/docs/publication hash。
2. 验证了什么：列出 focused pytest、publication checks、pyright、coverage、真实 provider smoke 的 pass/精确 skip。
3. Finding status：逐项 `已修复` / `部分修复` / `未修复` / `证据失效`，不得只写“已处理”。
4. 剩余风险：每项给 owner/destination；没有则明确“无未分类 residual risk”。
5. 明确未做：未扩 output schema、未加 alias/verifier/filter/repair loop、未改 Memory/UI。

## Gate decision

- Decision: `plan-review-fix-complete`，尚未通过 re-review
- Evidence completeness: 满足 goal/motivation/success、non-goals、direct code evidence、ownership、affected files、contract decisions、implementation slices、tests/commands、docs decision、risks/open questions 与 completion report format。
- Validation performed in this gate: 完整读取两路 plan review artifact；用现有 production parser 与 `accept_compact_candidate_v2` 验证本文 example pair，结果为 parser pass、governance accepted、coverage exact partition；未运行实现测试、pyright或真实 provider smoke，因为本 gate 不修改 production/test code。
- Changed files in this gate: 本 plan artifact 与对应 durable plan review fix artifact。
- Preserved review artifacts: `docs/reviews/pr-190-review-20260803-160425.md`、`docs/reviews/plan-review-mimo-20260803-171726.md`、`docs/reviews/plan-review-ds-20260803-171916.md` 均原样保留。
- Dispatch state: 总控按 gate 拆分派发，本次在 fix gate 结束。
- Next entry point: `plan re-review`。
