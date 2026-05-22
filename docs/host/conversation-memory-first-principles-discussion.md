# Conversation Memory 第一性原理讨论稿

本文是讨论稿，不是 Host 设计真源。稳定设计仍以 `docs/host/design.md` 为准。

## 问题背景

在 smoke 中，模型对 `DAYU_MEMORY_ALPHA` 的回答不稳定：有时认为能看到，有时说明只在用户目标或 episode summary 中看到，`evidence_backed_facts` 中没有明文。这暴露出一个更重要的问题：

如果第一轮用户询问“茅台 2024 年收入、毛利”，工具返回了收入和毛利；第二、三轮继续其它问题；第四轮用户再问“毛利率”，Agent 是否一定能从 Memory 中稳定拿回第一轮工具确认的收入和毛利？

这个问题不能只从现有实现解释。需要从买方财报分析 Agent 的第一性原理重新判断 Memory 的最优设计。

## 第一性原理

财报 Agent 的 Memory 核心目标不是保存聊天记录，也不是保存摘要，而是让下一轮分析能稳定恢复研究状态。

下一轮分析为了正确工作，至少需要稳定拿回四类状态：

1. 任务状态：当前研究对象、期间、口径、用户目标、约束和未完成问题。
2. 证据支撑事实：绑定到 accepted evidence 的可复用 claim，包括财务指标、表格行列、引用位置、计算口径、单位、期间、来源和证据链。
3. 分析产物：已经形成但不等同于原始事实的结论、假设、比较、推理链和待验证判断。
4. 交互连续性：用户刚刚怎么问、Agent 刚刚怎么答，用来理解“它”“刚才那个”“继续算”等省略语。

其中，买方财报分析最核心的是 `evidence_backed_facts`。第四轮问毛利率时，Agent 不应依赖 raw turns、assistant final answer、episode summary 或模型自身记忆，而应稳定读到第一轮工具证据支撑的收入和毛利 claim。

## 当前设计的风险

`docs/host/design.md` 中的 Conversation Memory 方向基本正确：

- `assistant final_answer` 不能自动升级为 `evidence_backed_fact`。
- `evidence_backed_facts` 只能来自已接受工具证据。
- Memory 是 EventLog read model，不是事实真源。
- `episode summary` 只能做导航，不能替代 evidence anchor。
- stable layer 优先于 history pool。

但当前设计还不是财报 Agent 的最优设计，主要缺口是：没有明确 `evidence_backed_fact` 的定义和生成边界，导致实现可能无法把关键业务 claim 以 Memory 可投影、可渲染、可计算、可追溯的形式进入 stable layer。

“工具结果即事实”这个表述过粗。更准确的定义应是：`evidence_backed_fact` 表示“一个可复用 claim 绑定到了 accepted evidence”。不是所有 tool result payload 都应该完整变成 fact；tool provider 也不应承担判断长文档中哪些内容进入 Memory 的职责。否则实现很容易退化为只保留：

```text
tool_name=...; outcome_digest=...; payload_ref=...; digest_ref=...
```

这对审计有价值，但对第四轮计算毛利率没有直接帮助，因为模型拿不到“来源在某处说了收入和毛利是多少”的可复用 claim 明文。

## recent raw turns 的边界

`recent_raw_turns_floor` 容易让人理解为“最近几轮完整 raw transcript 会保底回灌”。如果按这个名字理解，用户会自然期待最近几轮里的 tool result 原文也可见。

但从财报 Agent 最优设计看，recent raw turns 不应该承担财务事实保真职责。它只应该服务交互连续性，例如理解省略语、追问对象和刚才回答的上下文。

关键财务事实必须进入 stable `evidence_backed_facts`，而不是依赖：

- 最近 raw turns 是否还在；
- assistant final answer 是否写全；
- episode summary 是否保留；
- compact 是否正确概括；
- history pool 预算是否足够。

因此，即使保留 `recent_raw_turns_floor`，也需要明确它不是 financial fact retention 机制。

## 建议设计方向

Conversation Memory 的最优结构应从“财报研究状态”出发，而不是从“聊天记录压缩”出发：

```text
Financial Research Memory
  -> Task State
  -> Evidence-backed Facts
  -> Derived Analysis State
  -> Interaction Continuity
```

Host 仍然不应理解财报业务语义，例如“收入”“毛利”“毛利率”。但 Host 应支持业务中立的 structured `evidence_backed_fact` 容器，让 Conversation Memory 能把已接受工具证据绑定到可复用 claim。

`evidence_backed_fact` 的核心不是“Host 证明了世界事实为真”，也不是“Host 理解证据来源长什么样”，而是“这个 claim 绑定到了某个已接受 evidence，因此不是模型幻想”。Web tool 正常返回 URL 内容、Fins tool 的 `read_section` 正常返回年报章节、表格工具返回 row / cell、数据库工具返回 record，这些来源形状都属于 tool / provider 私有语义。Host 只需要知道它们已经形成 accepted evidence envelope，不需要理解 URL、章节、chunk、span、row、cell 或其它 locator。

建议生成路径：

```text
accepted tool result / evidence artifact
  -> accepted evidence envelope（evidence_id + opaque descriptor / artifact refs）
  -> Host-governed Memory Extraction Operation
  -> Host accept barrier 校验 claim_text + accepted evidence_refs
  -> evidence_backed_facts projection
  -> RunInputBuilder 渲染可读 claim 与 evidence refs
```

其中，Memory Extraction Operation 是 Host-governed LLM extractor。它可以参考 pinned_state patch / compact 的做法，由 LLM
在 Host governance 下基于 tool query + bounded tool result / artifact 摘要生成候选 claim；LLM 只生成 candidate，不能直接写
memory，不能绕过 evidence refs，也不能从 assistant final answer、episode summary 或无锚点文本中生成
`evidence_backed_fact`。

LLM extractor 必须返回 Host 定义的结构化 JSON candidate，而不是 plain summary。当前 compactor 如果只让 LLM 返回一段文本，再由
代码塞进 pinned state patch，表达力不足；P12.5 应把该机制升级为 typed candidate 输出。一个 extraction candidate JSON
可表达为类似结构：

```json
{
  "pinned_state_patch_candidate": {
    "current_goal": {
      "operation": "replace",
      "value": "分析贵州茅台 2024 年收入、毛利与毛利率。",
      "evidence_refs": ["event:user-input:1"]
    },
    "confirmed_subjects": {
      "operation": "replace",
      "value": ["贵州茅台", "2024"],
      "evidence_refs": ["event:user-input:1", "event:tool-result:2"]
    },
    "user_constraints": {
      "operation": "missing",
      "value": null,
      "evidence_refs": []
    },
    "open_questions": {
      "operation": "replace",
      "value": ["计算 2024 年毛利率。"],
      "evidence_refs": ["event:user-input:3"]
    }
  },
  "evidence_backed_fact_candidates": [
    {
      "claim_text": "贵州茅台 2024 年营业收入为 1740 亿元。",
      "evidence_kind": "observed_value",
      "evidence_refs": ["evidence:event-2:item-1"],
      "attributes": {
        "subject": "贵州茅台",
        "period": "2024",
        "metric": "revenue",
        "value": "174000000000",
        "unit": "CNY",
        "scale": "yuan"
      }
    },
    {
      "claim_text": "贵州茅台 2024 年毛利为 1580 亿元。",
      "evidence_kind": "observed_value",
      "evidence_refs": ["evidence:event-2:item-2"],
      "attributes": {
        "subject": "贵州茅台",
        "period": "2024",
        "metric": "gross_profit",
        "value": "158000000000",
        "unit": "CNY",
        "scale": "yuan"
      }
    }
  ],
  "working_assumption_candidates": [],
  "minimum_preserve_item_candidates": [
    {
      "item_id": "factor-2",
      "label": "第二个因素",
      "text": "第二个因素的最小可追问上下文。",
      "source_refs": ["event:user-input:1", "event:assistant-answer:1"],
      "preserve_reason": "needed_for_recent_reference"
    }
  ],
  "continuity_notes": []
}
```

该 JSON 是 Host contract，不是 provider 自由格式。未知字段、缺必填字段、字段类型不匹配、`evidence_refs` 为空或引用不存在的
accepted evidence，都必须 fail fast 或进入 bounded repair / diagnostic，不能静默降级为 fact。缺少可接受
`evidence_backed_fact` candidate 时，Host 只能记录 diagnostic / repair outcome 并保留 accepted evidence refs，不得合成 neutral
fallback fact。provider 支持 structured output 时应优先使用；不支持时也必须要求纯 JSON，并由 Host 严格解析、校验和拒绝非法
candidate。

Host accept barrier 只校验通用 contract：

- `claim_text` 非空、长度受限。
- `evidence_kind` 是允许枚举。
- `evidence_refs` 非空，且每个 ref 都指向本次 compact input 或已提交 EventLog 中的 accepted evidence envelope。
- candidate 不能引用 assistant final answer、episode summary、user input 或 working assumption 作为 evidence。
- `attributes` 是可选 opaque key-value，用于渲染和后续计算辅助；Host 不理解其业务含义。
- `minimum_preserve_item_candidates` 只作为 continuity items 接受，Host 校验 item text 非空且长度受限、source refs 指向 compact input、
  preserve reason 属于允许枚举、item 数量受 policy 限制；它们不能产生 `evidence_backed_fact`。

Host 不校验 evidence 的业务形状，不解析 locator，不证明 excerpt 是否逐字覆盖 claim，不理解 metric / subject / period。证据来源细节由
accepted evidence envelope / artifact 承载；如果 UI / audit 需要展示证据细节，再通过 evidence id 回查对应 tool query、tool result、
payload ref、source descriptor 或 provider 私有 locator。

Memory Extraction Operation 不应设计成每个 `TOOL_RESULT_ACCEPTED` 后立刻同步执行的 eager extraction；这会让普通工具路径背负
不必要的 LLM 调用成本，也会阻塞正常 Run。P12.5 第一版采用 compaction-gated extraction：

- compact 前不阻塞普通 Run 做 extraction；短链路追问继续依赖 recent raw turns / older raw turns / 已有 memory。
- `TOOL_RESULT_ACCEPTED` 后记录 accepted evidence / artifact / refs，供后续 compact 使用，不要求同步 LLM extraction。
- 正常 compact 时，复用同一次 LLM structured JSON 调用，同时生成 episode summary candidate、pinned state patch candidate、
  `evidence_backed_fact_candidates`、minimum preserve item candidates 与 preservation / diagnostic 信息；正常路径不额外增加第二次 LLM 调用。
- bounded repair 只有在 JSON parse、schema、evidence refs、quality check 或 preservation decision 失败时才触发；repair 属于失败修复路径，
  不是正常路径固定成本。
- 每次 compact 只把其覆盖范围内的历史 raw evidence 转化为 stable facts / continuity summary；compact 后新产生的 user input、
  assistant answer、tool result 继续作为新的 raw turns / accepted evidence 进入 memory pipeline，并在后续 compact 中按同一规则处理。

因此，compact 前 raw turns 继续承担短链路追问连续性；compact 时“顺手”抽取 `evidence_backed_fact_candidates`；compact 后，
本次 compact 覆盖范围内的历史 evidence-backed claims 不再依赖 compact 前 raw turns 或 episode summary 复原，而是通过 accepted
`evidence_backed_facts` 进入 stable memory。`evidence_backed_facts` 不是 raw turns 的别名，也不是 episode summary 的派生事实。

这意味着 pinned state patch 和 `evidence_backed_fact_candidates` 可以在同一轮 LLM 调用中生成，因为它们共享任务语境；但二者的接受规则不同。
`pinned_state_patch_candidate` 可以来自用户目标、约束、当前任务语境和 evidence；`evidence_backed_fact_candidates` 只能来自 accepted
tool evidence，并且每条必须带 `claim_text`、`evidence_refs` 和 evidence kind。

Minimum preserve 是同一 structured compact output 中的 continuity 机制。它保护“第二个因素”“这个数”“刚才那部分”等指代解析所需的
最小上下文，不保留整段长 user input，也不承担事实真源职责。对用户粘贴长文本并要求提炼三个因素的场景，compact 后应保留有序
extracted items 中能解析“第二个因素”的 bounded item；后续 RunInputBuilder 注入该 continuity item，而不是依赖完整原文仍在。

Host 的职责不是解释这些字段，而是：

- 持久化 source claim 与 provenance。
- 保留 event / tool / digest / evidence refs。
- 在预算内稳定注入 `evidence_backed_facts`。
- 对被排除或降级的 fact 产生日志、diagnostic 和 trace。
- 确保 compact summary、assistant conclusion 和 user claim 不能冒充 `evidence_backed_fact`。
- 保证 LLM extractor 调用发生在 Host governance operation 内，输出只作为 candidate，经 accept barrier 后才进入 EventLog /
  Conversation Memory projection。

## 已裁决问题

1. 旧 `verified_facts` 全量改名 / 迁移为 `evidence_backed_facts` 或等价 typed view，并把定义冻结为“可复用 claim 绑定到 accepted evidence”。
2. Tool result contract 只要求提供可审计 accepted evidence envelope，不要求 tool provider 直接生成最终 memory fact。
3. Host-governed Memory Extraction Operation 使用 LLM extractor 生成 typed JSON candidate，并允许与 pinned state patch 在同一轮 LLM 调用中生成。
4. Extraction 运行时机采用 compaction-gated extraction：compact 前不阻塞普通 Run；`TOOL_RESULT_ACCEPTED` 后只记录 evidence /
   artifact / refs；正常 compact 的同一次 structured JSON 调用额外生成 `evidence_backed_fact_candidates`；repair 只在质量失败时触发。
5. LLM extractor JSON schema、parse failure、schema failure、evidence ref mismatch、minimum preserve item validation、bounded repair 与 diagnostic
   语义由 Host accept barrier 冻结；无可接受 fact candidate 时只记录 diagnostic / repair outcome，不合成 neutral fallback fact。
6. `recent_raw_turns_floor` 保留命名并重新定义为最近 raw turns 的最低保留数量；它服务交互连续性，不表达完整 raw tool transcript 保底。
7. RunInputBuilder 渲染 `evidence_backed_facts` 时必须包含 `claim_text` 与 `evidence_refs`，不能只有 digest / ref；source / locator
   细节通过 evidence id 回查 accepted evidence envelope。

## 旧项目测试 Prompt 反推的最低验收语义

旧项目 `dayu-agent/docs/conversation_memory_test.md` 中的测试 prompt 不应被当作实现约束，但可以作为财报 Agent Conversation Memory 的最低验收语义。

### pinned_state 演进与抗漂移

测试语义：

- 用户先分析贵州茅台 2024 半年报营收增长结构。
- 指定百万元口径和产品系列拆分。
- 后续询问茅台酒 / 系列酒同比增速、毛利率、销量。
- 中途切换到五粮液 2024 半年报，要求同样口径。
- 再回到茅台确认前面给出的同比增速。

最低要求：

- Memory 必须稳定区分主体、期间和口径。
- `pinned_state` 必须能表达当前主体切换，同时不丢失同 session 内已确认过的历史主体事实。
- 回到茅台时，Agent 必须拿出与前序工具确认一致的数值，不能重新编数，也不能把五粮液事实混入茅台。

### 追问连续性

测试语义：

- 用户询问宁德时代现金流量表关键数据。
- 后续使用“这个数”“这部分支出”等代词追问。

最低要求：

- 最近 1-2 轮交互必须在预算紧张时仍可用于指代解析。
- `recent_raw_turns_floor` 或等价机制必须承担最近交互连续性的保底职责。
- 这里保底的是追问语境，不是财务事实的最终持久载体。

### 单轮极长输入后的 minimum preserve

测试语义：

- 用户粘贴 8000-15000 字官方披露原文片段。
- 要求提炼影响毛利率的三个因素。
- 下一轮追问“第二个因素”。

最低要求：

- 单轮 user input 很长时，Context Governance / Memory 必须保住当前追问所需的最小上下文。
- “第二个因素”这类指代不能因为预算裁剪或 compaction 丢失。
- assistant 可降级为摘要，但当前追问依赖的 extracted items 必须以 bounded continuity item 保真；不要求保留完整长 user input。

### compaction 后 confirmed facts 不漂移

测试语义：

- 用户围绕招商银行 2024 半年报息差数据连续追问。
- 中途触发 compaction。
- 后续回到息差讨论，要求确认净息差具体数值，并检查是否和第 2 轮一致。

最低要求：

- 工具确认过的关键财务事实必须跨 compaction 稳定保留。
- 第 12 / 13 轮不能因为 compact summary 改写、遗漏或模型再生成而数值漂移。
- 最佳设计中，事实真源应是 `evidence_backed_facts`；episode summary 只做导航和 fact ref 引用，不应替代 `evidence_backed_fact`。
- 后续轮次可以基于 Memory 中的 `evidence_backed_facts` 回答，无需重复调用工具，除非用户要求重新验证或 fact 已被 policy 明确排除。

### 长会话稳定性

测试语义：

- 同一家公司围绕营收、毛利、费用、利润、资产、负债、现金流、估值、同行对比连续 25-30 轮。
- 每隔若干轮触发 compaction。
- 最后询问本次对话定下了哪些口径约束。

最低要求：

- `pinned_state` 中主体、期间、用户约束不能漂移或重复污染。
- `evidence_backed_facts` 随会话增长必须有预算策略和诊断，不能静默丢失关键事实。
- episode 数量增长后，history pool 可裁剪，但 stable facts 和口径约束必须优先保留。

## 验收结论

Conversation Memory 至少应满足上述测试 prompt 的语义。旧项目中“episode_summary.confirmed_facts”可作为测试目标描述，但在 dayu-agent-r 的最佳设计中，confirmed facts 不应由 episode summary 承载事实真源；episode summary 应引用或导航到 `evidence_backed_facts`。

因此，后续设计裁决应保证：

- pinned_state 单调演进，不漂移。
- 最近 raw turns 真正保底，用于代词和追问连续性。
- 长 user input 有 minimum preserve 语义。
- 工具证据支撑的财务 claim 进入 stable `evidence_backed_facts`。
- compaction 不能让 confirmed facts 退化成普通摘要。
- 被裁剪、降级、无法注入的 memory item 必须可诊断。
- 同一 session 内，后续轮次必须能稳定复用已验证事实，除非用户明确要求重新验证。

## 暂定结论

当前 Conversation Memory 设计不是错误方向，但不是财报 Agent 的最优设计。最优设计必须以 `evidence_backed_facts` 为中心，而不是以 raw turns / summaries 为中心。

`DAYU_MEMORY_ALPHA` smoke 暴露的问题有效：如果 accepted evidence 中的关键 claim 没有明确 Memory extraction / projection contract，就不能保证跨轮稳定可见。后续设计应补强 `evidence_backed_facts` contract，并让 smoke 用财报事实风格的 source claim 验证跨 run 可见性。
