# PR 190 Compactor LLM-facing aggregate deepreview acceptance

## Gate decision

- Gate：aggregate deepreview。
- Review range：`7cf1027c..212f22af`。
- Decision：**accept**；没有 correctness、stability、maintainability 或 semantic ownership finding 需要修复。
- MiMo artifact：`docs/reviews/pr-190-compactor-llm-facing-aggregate-mimo-review-20260803.md`。
- DeepSeek artifact：`docs/reviews/pr-190-compactor-llm-facing-aggregate-ds-review-20260803.md`。

## Finding adjudication

两路 review 均报告无 finding。总控不以结论一致替代证据，逐项裁决如下：

1. 不可信材料：accepted。renderer 用单一独占 marker 包围完整 typed input；system/user prompt 都把其中指令式文本限定为数据。四位置 canary 走 production renderer，且测试明确断言没有 production filter。
2. 自足 contract：accepted。prompt 当前消息内给出 input/output 字段、类型、必填性、允许值、八种 source kind 业务语义、coverage 规则和 label 同源完整示例；示例经 production strict parser 与 governance 接受。
3. repair boundary：accepted。durable `CompactRepairFeedbackV2` 保留 Host audit 字段；唯一 projector 只投影 `required_action` 与 issue 四字段，renderer 机械写入独占 marker。未从 raw mapping、artifact 或字符串重建。
4. Context Governance 与 caps：accepted。accept/reject 和 policy issue 是唯一 owner，item/字符反馈直接来自传入的同一 policy instance 与 estimator 结果；whole candidate 基于 immutable input 重产，不合并 patch。
5. contract expansion：accepted。diff 没有新增 output schema 字段、repair loop、材料 filter、自然语言 verifier 或 provider/model production semantics。
6. adversarial matrix：accepted。unknown/duplicate/coverage/caps、feedback truncation、四类 injection 材料、Mimo-first/DeepSeek-only test selector、非环境失败 fail closed 与 frozen registry 都有直接测试或 immutable evidence。
7. validation：MiMo 聚焦验证为 149 tests pass 且目标 pyright 为 0；DeepSeek 额外完成 Host suite `2362 passed, 8 deselected`。S4 aggregate 另有 `365 passed, 1 skipped` 和全仓 pyright `0 errors`。这些证据互补，不以任一路单一数字代替最终验证。

## Residual adjudication

1. **真实模型行为 `not_observed`：保留。** Mimo 与 DeepSeek 均精确分类为 `network_unavailable`，未收到非空 candidate。deterministic contract tests 不能替代真实 injection、strict parse、cap compliance 与 governance accept 观察。owner 是 S3 real-provider smoke 环境；网络和 credential 可用后重跑原 opt-in command。
2. **MiMo 提出的 previous-* source kind 未逐个 injection 参数化：不构成 finding。** trust boundary 的 owner 是包围完整 input JSON 的 marker，不按 source kind 分支；当前四个不同来源位置已覆盖 current/trace/evidence/answer，生产路径又明确不做过滤。穷举所有 source kind 不会增加 owner contract 证明，故不扩张测试矩阵；完整自然语言 evaluation 仍归 Issue 80。
3. **DeepSeek 提出的“确认 Service 同样 Mimo-first”：拒绝为 out-of-scope。** Mimo-first/DeepSeek-only 是本 work unit 真实验证的 test selector 约束，不是生产 provider selection contract。用户明确禁止修改 provider/model 选择语义；`LLMContextCompactor` 接收注入的 runner 是正确边界，不应把 smoke 偏好升级成产品语义。
4. **repair feedback 理论不可达的最终 `RuntimeError`：不构成 finding。** 单 issue message 有 240 字符上限，完整 feedback 有 8192 字符上限；review 未给出可达反例，防御性 fail-closed 不改变 LLM contract。

## Gate truth

- Prompt follow-up 原报告三项均在正确 owner boundary 修复。
- `docs/cli_ci_oracles.json` 与 `docs/cli_ci_scenarios.json` 保持不变。
- Aggregate gate 允许进入 existing draft PR 190 chain；不授权新建 PR、mark ready、approve、merge 或 force-push。
