# Conversation Memory 第一性原理讨论稿

本文是讨论稿，不是 Host 设计真源。稳定设计仍以 `docs/host/design.md` 为准。

## 问题背景

在 smoke 中，模型对 `DAYU_MEMORY_ALPHA` 的回答不稳定：有时认为能看到，有时说明只在用户目标或 episode summary 中看到，tool-verified facts 中没有明文。这暴露出一个更重要的问题：

如果第一轮用户询问“茅台 2024 年收入、毛利”，工具返回了收入和毛利；第二、三轮继续其它问题；第四轮用户再问“毛利率”，Agent 是否一定能从 Memory 中稳定拿回第一轮工具确认的收入和毛利？

这个问题不能只从现有实现解释。需要从买方财报分析 Agent 的第一性原理重新判断 Memory 的最优设计。

## 第一性原理

财报 Agent 的 Memory 核心目标不是保存聊天记录，也不是保存摘要，而是让下一轮分析能稳定恢复研究状态。

下一轮分析为了正确工作，至少需要稳定拿回四类状态：

1. 任务状态：当前研究对象、期间、口径、用户目标、约束和未完成问题。
2. 已验证事实：工具确认过的财务指标、表格行列、引用位置、计算口径、单位、期间、来源和证据链。
3. 分析产物：已经形成但不等同于原始事实的结论、假设、比较、推理链和待验证判断。
4. 交互连续性：用户刚刚怎么问、Agent 刚刚怎么答，用来理解“它”“刚才那个”“继续算”等省略语。

其中，买方财报分析最核心的是 evidence-backed facts。第四轮问毛利率时，Agent 不应依赖 raw turns、assistant final answer、episode summary 或模型自身记忆，而应稳定读到第一轮工具确认的收入和毛利。

## 当前设计的风险

`docs/host/design.md` 中的 Conversation Memory 方向基本正确：

- `assistant final_answer` 不能自动升级为 verified fact。
- `verified_facts` 只能来自工具事实。
- Memory 是 EventLog read model，不是事实真源。
- `episode summary` 只能做导航，不能替代 evidence anchor。
- stable layer 优先于 history pool。

但当前设计还不是财报 Agent 的最优设计，主要缺口是：没有强制工具返回的关键业务事实以 Memory 可投影、可渲染、可计算、可追溯的形式进入 verified facts。

“工具结果即事实”这个表述过粗。不是所有 tool result payload 都应该完整变成 fact，但工具返回的关键财务指标必须能稳定投影成 verified facts。否则实现很容易退化为只保留：

```text
tool_name=...; outcome_digest=...; payload_ref=...; digest_ref=...
```

这对审计有价值，但对第四轮计算毛利率没有直接帮助，因为模型拿不到收入和毛利明文。

## recent raw turns 的边界

`recent_raw_turns_floor` 容易让人理解为“最近几轮完整 raw transcript 会保底回灌”。如果按这个名字理解，用户会自然期待最近几轮里的 tool result 原文也可见。

但从财报 Agent 最优设计看，recent raw turns 不应该承担财务事实保真职责。它只应该服务交互连续性，例如理解省略语、追问对象和刚才回答的上下文。

关键财务事实必须进入 stable verified facts，而不是依赖：

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

Host 仍然不应理解财报业务语义，例如“收入”“毛利”“毛利率”。但 Host 应支持业务中立的 structured verified fact 容器，让财报工具把可复用事实交给 Memory。

工具返回的可复用财务事实应能表达为类似结构：

```json
{
  "memory_facts": [
    {
      "subject": "贵州茅台",
      "period": "2024",
      "metric": "revenue",
      "label": "营业收入",
      "value": "174000000000",
      "unit": "CNY",
      "scale": "yuan",
      "methodology": "annual_report_consolidated_income_statement",
      "source_ref": "opaque-source-ref",
      "evidence_ref": "opaque-evidence-ref"
    },
    {
      "subject": "贵州茅台",
      "period": "2024",
      "metric": "gross_profit",
      "label": "毛利",
      "value": "158000000000",
      "unit": "CNY",
      "scale": "yuan",
      "methodology": "annual_report_consolidated_income_statement",
      "source_ref": "opaque-source-ref",
      "evidence_ref": "opaque-evidence-ref"
    }
  ]
}
```

Host 的职责不是解释这些字段，而是：

- 持久化 fact 与 provenance。
- 保留 event / tool / digest / source ref。
- 在预算内稳定注入 verified facts。
- 对被排除或降级的 fact 产生日志、diagnostic 和 trace。
- 确保 compact summary、assistant conclusion 和 user claim 不能冒充 verified fact。

## 待裁决问题

1. 是否将 `verified_facts` 从单一 `fact_summary` 文本扩展为业务中立 structured fact 容器。
2. Tool result contract 是否要求可复用业务事实必须通过 `memory_facts` 或等价字段显式提供。
3. 缺少可投影 fact 时，Memory projection 应该只生成 diagnostic，还是继续生成 neutral fallback verified fact。
4. `recent_raw_turns_floor` 是否需要改名或重新定义，避免被误解为完整 raw tool transcript 保底。
5. RunInputBuilder 渲染 verified facts 时，是否必须包含可计算事实文本或结构化字段，而不能只有 digest / ref。

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
- assistant 可降级为摘要，但当前追问依赖的 user text / extracted items 必须保真。

### compaction 后 confirmed facts 不漂移

测试语义：

- 用户围绕招商银行 2024 半年报息差数据连续追问。
- 中途触发 compaction。
- 后续回到息差讨论，要求确认净息差具体数值，并检查是否和第 2 轮一致。

最低要求：

- 工具确认过的关键财务事实必须跨 compaction 稳定保留。
- 第 12 / 13 轮不能因为 compact summary 改写、遗漏或模型再生成而数值漂移。
- 最佳设计中，事实真源应是 tool-verified facts；episode summary 只做导航和 fact ref 引用，不应替代 verified fact。
- 后续轮次可以基于 Memory 中的 verified facts 回答，无需重复调用工具，除非用户要求重新验证或 fact 已被 policy 明确排除。

### 长会话稳定性

测试语义：

- 同一家公司围绕营收、毛利、费用、利润、资产、负债、现金流、估值、同行对比连续 25-30 轮。
- 每隔若干轮触发 compaction。
- 最后询问本次对话定下了哪些口径约束。

最低要求：

- `pinned_state` 中主体、期间、用户约束不能漂移或重复污染。
- verified facts 随会话增长必须有预算策略和诊断，不能静默丢失关键事实。
- episode 数量增长后，history pool 可裁剪，但 stable facts 和口径约束必须优先保留。

## 验收结论

Conversation Memory 至少应满足上述测试 prompt 的语义。旧项目中“episode_summary.confirmed_facts”可作为测试目标描述，但在 dayu-agent-r 的最佳设计中，confirmed facts 不应由 episode summary 承载事实真源；episode summary 应引用或导航到 tool-verified facts。

因此，后续设计裁决应保证：

- pinned_state 单调演进，不漂移。
- 最近 raw turns 真正保底，用于代词和追问连续性。
- 长 user input 有 minimum preserve 语义。
- 工具确认过的财务事实进入 stable verified facts。
- compaction 不能让 confirmed facts 退化成普通摘要。
- 被裁剪、降级、无法注入的 memory item 必须可诊断。
- 同一 session 内，后续轮次必须能稳定复用已验证事实，除非用户明确要求重新验证。

## 暂定结论

当前 Conversation Memory 设计不是错误方向，但不是财报 Agent 的最优设计。最优设计必须以 evidence-backed financial facts 为中心，而不是以 raw turns / summaries 为中心。

`DAYU_MEMORY_ALPHA` smoke 暴露的问题有效：如果 tool result 中的关键事实没有明确 Memory projection contract，就不能保证跨轮稳定可见。后续设计应补强 verified facts contract，并让 smoke 用财报事实风格的 memory facts 验证跨 run 可见性。
