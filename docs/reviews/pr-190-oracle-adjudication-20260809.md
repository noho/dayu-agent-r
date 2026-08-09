# PR 190 Oracle 裁决记录（2026-08-09）

## 裁决范围

本记录只冻结 `interactive.interactive.g06.cap-constrained-memory-replacement@1`，不替用户裁决其它 scenario。

## 复合观察证据

### Cap、repair、fallback 与 durable replacement

- 报告：`docs/reviews/pr-190-interactive-cap-constrained-memory-observed-20260808.md`
- SHA-256：`54ca13f273402915f1657a95b0d3e50c2ba79ae84b4545ea7ace8e2d09376dce`
- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/interactive-cap-gap-r2-20260808-JdukC2`
- 观察：真实MiMo、production CLI/tools/AAPL corpus；真实output caps进入initial request；同一operation五次candidate rejection后budget exhausted并执行deterministic fallback；另一operation先产生invalid JSON，再由bounded whole-candidate repair形成accepted replacement；represented/omitted、artifact、Memory、RunInput与reconnect同源。
- 实现finding：fallback主Run曾使用实际RunnerInput之外的内容生成未经支持的风险，因此该报告不能单独证明最终conformance。

### G06 post-fix fallback grounding

- 报告：`docs/reviews/pr-190-g06-fallback-grounding-postfix-observed-20260809.md`
- SHA-256：`f4cefda475ebc0c6bf9b31d0b7a11cf12116eda4a7bd6d18236b648d19a881d4`
- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/g06-postfix-r2-20260809-rFNfAA`
- 目标 Run：`run-aee8f674157c4555b5a2cf4cbc0e308b`
- 观察：真实MiMo、production interactive/tools/AAPL corpus；compactor candidate因`source_kind_mismatch`被拒绝，attempt budget耗尽后只有一个canonical failure并进入deterministic recent-window fallback；实际fallback RunnerInput包含自解释grounding边界，不含被询问的研发费用数值；final answer明确当前材料不足、无法回答，并请求检索或提供材料；Run succeeded、process exit 0。

两份证据组合的理由：前一run覆盖未被G06修改的cap、repair、fallback lifecycle与durable replacement链；后一run在最终实现HEAD上覆盖G06唯一改变的fallback RunnerInput/final-answer grounding行为。

## 用户裁决

- 日期：2026-08-09
- 原文：`裁决：正确。`
- 决定：`accepted`
- 适用 scenario：`interactive.interactive.g06.cap-constrained-memory-replacement@1`

冻结语义：

1. Host拥有compactor output cap、strict acceptance、bounded repair、budget-exhausted fallback及durable truth。
2. fallback继续主Run时，实际RunnerInput必须明确可用证据边界；缺失历史、先前assistant文本与模型常识不自动成为证据。
3. 当前材料不足且本Run不能或未获授权检索时，final answer必须明确无法据此回答，并提示用户提供材料或授权检索；不得补写未经支持的事实、结论或风险。

## `session_summary=null` 补充裁决

- 观察报告：`docs/reviews/pr-190-interactive-summary-null-observed-20260809.md`
- SHA-256：`b561e01a4b31ae9267479a70c72a388079299e3111d1be80f7463edd575de5db`
- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX`
- 日期：2026-08-09
- 原文：`裁决：正确。`
- 决定：`accepted`
- 适用 scenario：`interactive.interactive.g06.summary-null@1`

冻结语义：已有非空session summary时，真实compactor返回并被Host接受的`session_summary=null`只清除旧摘要；同一accepted replacement中的其它Semantic Memory保留；post-compact Run与跨进程reconnect消费同一状态。
