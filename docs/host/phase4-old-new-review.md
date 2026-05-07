# Host P4 OLD/NEW + 最佳实践专项 Plan Review

## 结论

未通过，需先修 plan 后再进入实施。

`docs/host/phase4-plan.md` 的整体方向正确：context overflow / compact 归 Host，Engine 只暴露强类型 overflow / compaction-required 事实；compact 输入限定在 canonical EventLog、ConversationMemory snapshot 与 RunInputBuilder 可消费事实；reasoning / preview / delta / display timeline 明确排除；失败收口、retry 上限、EventLog 事实、README / smoke / review gate 也都有规划。

但对照 OLD 可靠语义后，还有两个实施时很容易漏掉的边界没有写成足够硬的验收条件。

## Findings

### Finding 1 - [已修复，待复查][中] Engine overflow 识别缺少 OLD provider 信号回归矩阵

**证据**

- OLD `../dayu-agent/dayu/engine/async_openai_runner.py` 的 `_detect_context_overflow()` 不只识别 OpenAI 标准 `context_length_exceeded`，还覆盖多个 provider 文本信号，例如 `maximum context length is`、`total message token length exceed model limit`、`model's maximum context length`、`range of input length should be`、`model requires more context`。
- P4 plan 已要求 Host 不猜普通错误文本，overflow trigger 只能来自 Engine / Runner 强类型事实，这是正确的 NEW 分层。
- 但测试清单只写了“覆盖 provider context overflow 识别只产出强类型事实”，没有明确要求把 OLD 多 provider 信号作为 Engine classifier 的回归用例。

**风险**

实施 Agent 可能只支持 `context_length_exceeded`，导致非 OpenAI 标准格式的真实上下文超限被归类为普通 client error。这样 Host compact 根本不会启动，P4 表面符合分层，实际丢掉 OLD 最核心的可靠触发语义。

**建议**

在 plan 的 Engine 协作测试清单中增加明确矩阵：

- JSON error code：`context_length_exceeded`。
- OLD 已支持的 provider 文本信号：至少覆盖 `maximum context length is`、`total message token length exceed model limit`、`model's maximum context length`、`range of input length should be`、`model requires more context`。
- 负例：普通 400 / 普通 client error 不得触发 compact。
- 所有正例只产出强类型 `CONTEXT_COMPACTION_REQUESTED` 或等价 compaction-required fact，不在 Engine 内 compact / retry。

**修复说明**

已在 `docs/host/phase4-plan.md` 补充 Engine / Runner classifier / adapter 边界要求，明确 P4
不是 Host 侧字符串硬编码；新增 OLD 多 provider context overflow 信号回归矩阵，覆盖 OpenAI 结构化
`context_length_exceeded`、OpenAI message fallback、Anthropic / 兼容网关 message fallback、本地或未知
provider message fallback，以及普通 400 / 普通 client error / 非 overflow message 负例。相关要求已同步补入
Engine overflow 输入契约、文件级改动清单、测试清单、review gate 与停止条件。

### Finding 2 - [已修复，待复查][中] compact 完成缺少“非空收益 / no-op 不重试”的硬后置条件

**证据**

- OLD `async_agent._compact_messages()` 返回 `(messages, actually_compacted)`；context overflow 分支只有 `actually_compacted=True` 才增加 compaction count 并 retry。若还有配额但消息已压不动，OLD 直接进入 `context_overflow_exhausted` 收口。
- P4 plan 要求 `context_compact_completed` 记录“估算大小变化”，也要求 retry 有上限，但没有明确写：compact 后必须产生可度量缩减，或至少改变 RunInput 的可消费结构；no-op compact 必须进入 failed / exhausted，不能启动下一次 internal attempt。

**风险**

deterministic compact 很可能在 pinned_state、当前问题、证据锚点、最近 raw turns 都必须保留时压不动。如果 plan 不把 no-op 判为失败，实施可能 append `context_compact_completed` 后启动一次必然失败的 retry，浪费 attempt，甚至让事件语义误导后续 P6 projection：看起来 compact 成功，实际上没有降低上下文压力。

**建议**

在 Host compact event 契约与测试清单中补充：

- `context_compact_completed` 必须包含 `before_estimated_size`、`after_estimated_size`、`reduced` 或等价强类型字段。
- `after_estimated_size >= before_estimated_size` 且 RunInput 事实选择没有发生有效降级时，必须产生 `context_compact_failed` 或 `context_compaction_exhausted`，不得 append retrying。
- 测试覆盖“全部关键事实都不可降级导致 no-op compact”的路径，确认 Host-owned terminal failure 收口。

**修复说明**

已在 `docs/host/phase4-plan.md` 补充 compact 成功硬后置条件：`context_compact_completed` 只有在
compacted RunInput 的 token / char 估算严格变短、`reduced=True` 且当前用户问题、pinned_state、
evidence anchors、source cursor 与必要 tool facts 保真时才能产生；no-op、变长或需要牺牲必保事实才能变短时，
必须产生 `context_compact_failed` / exhausted 等价事实并以 Host-owned `RUN_FAILED` terminal 收口，不得
append `context_attempt_retrying`。相关要求已同步补入目标、契约、状态机、不可接受临时实现、测试清单、
review gate、停止条件与风险。

## OLD 语义继承核对

| OLD 可靠语义 | P4 plan 状态 | 结论 |
| --- | --- | --- |
| provider context overflow 识别后进入 compact 路径 | 已补 OLD 多 provider 信号测试矩阵与 classifier / adapter 边界 | 已修复，待复查 |
| context overflow compact 有 retry 上限，压不动时失败收口 | 已补 compact 有效缩减硬后置条件与 no-op 失败收口 | 已修复，待复查 |
| 保留 system / 任务目标 / 最近尾部 | NEW 中对应为 pinned_state / stable frame / current user / recent raw turns | 已承接 |
| assistant(tool_calls) + tool result 不拆散 | NEW 不应迁回 raw tool message 组；应保留 tool_call_id、tool fact、evidence anchor 的等价关联 | 已承接，code review gate 需继续检查 |
| 工具结果摘要进入 compact | NEW 限定为 canonical tool facts / evidence anchors / cursor fingerprint / has_more 等中性摘要 | 已承接 |
| pinned_state 全量保留，summary / recall 可降级 | plan 明确 stable layer 与可解释降级 | 已承接 |
| 当前用户问题保留 | plan 明确当前 `USER_INPUT_ACCEPTED` 是 compact 必保项 | 已承接 |
| reasoning / preview / delta 不进入运行态上下文 | plan 多处硬性禁止 | 已承接 |

## 财报分析保真核对

P4 plan 对财报分析关键事实的保护总体到位：pinned_state、stable facts、verified claims、assumptions、tool facts、evidence anchors、source event cursor、tool_call_id、source_ref / chunk_ref / fingerprint、当前问题都被列为 compact 必保或优先保留项。计划也明确 Host 不解释公司、期间、口径、单位、准则或 XBRL fact，只保留 fins / tool facts 提供的 opaque references，这符合 Host 层中立边界。

后续 code review 需要重点确认：证据锚点不能被自然语言摘要替代；source cursor / anchor id 不能只存在 trace 中而不进入 compact 后 RunInput 的可追溯文本；scope token 和 cursor 原文不得泄漏。

新增后续复审关注点：Host Memory system block、Tool Facts、Evidence Anchors 与 compact 后 tool fact
summaries 只能作为 internal grounding / verification context。code review 与 smoke 必须确认 final answer
不会原样 echo `Host Memory`、`Tool Facts`、`Evidence Anchors`、`历史工具摘要`、tool args、tool result repr、
cursor fingerprint、source event cursor、scope token 或 raw EventLog metadata；允许输出的是面向用户的证据
与出处，而不是 Host 内部标题 / 字段 / 治理元数据。

## Review Gate 建议

现有 review gate 基本充分，但建议把以下两项显式加入 P4 review gate / smoke：

- Engine overflow classifier parity gate：对照 OLD provider overflow 信号逐项测试。
- Compact effectiveness gate：每次 `context_attempt_retrying` 前必须证明 compact 后 RunInput 估算确实变短且必保事实保真；no-op / 变长 / 保真失败必须失败收口。
- Internal memory non-echo gate：测试不能只检查 Host Memory / compact memory 已注入，还必须覆盖 final answer /
  fake model 不 echo 内部 section heading、tool metadata、cursor / scope / raw EventLog 元数据。

## 本次验证

- 已用 `rg` 对 NEW / OLD 搜索 `compact`、`overflow`、`context_length`、`summar`、`conversation_memory`、`retry`、`attempt`。
- 已阅读 `docs/host/phase4-plan.md`。
- 已对照 OLD `async_agent._compact_messages`、OLD `async_openai_runner._detect_context_overflow`、OLD `conversation_memory` compaction / pinned_state / episode summary 相关实现。
- 本轮只做 plan review，未运行测试，未修改生产代码。

## 复审结论

复审通过，无 findings。

本次复审确认两个中等 finding 已被真实修复，不是只在 review 文档中标记状态：

- Engine overflow 识别已在 `docs/host/phase4-plan.md` 中明确落到 Engine / Runner classifier 或 provider adapter
  边界，Host 只消费强类型 overflow / compaction-required 事实；计划要求结构化错误优先，message fallback
  仅限 Engine classifier 内受控信号集合，并补齐 OpenAI、Anthropic / 兼容网关、本地或未知 provider 的 OLD
  多 provider 信号回归矩阵与普通 client error 负例误判保护。
- compact 完成已在 plan 中明确为 retry 的硬前置事实：compacted RunInput 必须在 token / char 估算上严格变短，
  且当前用户问题、pinned_state、evidence anchors、source cursor 与必要 tool facts 保真；no-op、变长、
  或必须牺牲必保事实才能变短时，不得 append `context_compact_completed` / `context_attempt_retrying`，
  必须以 `context_compact_failed` / exhausted 等价事实和 Host-owned `RUN_FAILED` terminal 收口并记录原因。

同步性核对通过：

- 契约章节已包含 Engine overflow 输入契约、Host compact event 契约和 Compact 输入保真契约。
- 状态机章节已列出成功 retry、compact failed、no-op / 变长 / 保真失败、上限耗尽等路径。
- 测试清单已覆盖 provider overflow classifier 矩阵、结构化错误优先、message fallback 边界、负例误判保护、
  compact 严格变短、no-op 不 retry、必保事实不可牺牲、source cursor / anchor id 可追溯。
- review gate 已加入 Engine overflow classifier parity gate 与 Compact effectiveness gate。
- 停止条件已覆盖无法在 Engine / Runner 边界识别 OLD 多 provider overflow、只能靠 Host 猜 provider message、
  compact 无法变短、或为了变短必须牺牲必保事实等迁移阻断条件。

剩余迁移风险已在 plan 风险章节表达，未发现会阻断迁移 Agent 实施的新 plan 漏洞。
