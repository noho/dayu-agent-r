# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Fix Controller Validation

## 1. Verdict

- plan：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`。
- fix artifact：`docs/reviews/wu-semantic-ownership-01-r03-plan-fix-codex.md`。
- verdict：**READY_FOR_DUAL_PLAN_RE_REVIEW**。

Controller 已重读全部修订 contract 与 fix ledger，并以当前 EventLog append、accepted outcome codec、projection、Tool Trace 和四消费者代码独立核对。`R03-PLAN-F01..F08` 均在 owner-correct plan 位置有可实施规格；这只授权 re-review，不授权 implementation。

## 2. Independent checks

- F01：明确先 `append_event(...).row` 取得真实 sequence，再构造 `TOOL_AWAITING` ref；same transaction rollback、idempotent existing row与不同 body conflict均有直接测试要求。
- F02：`_source_projection` 明确只接收 digest-check 的 `raw_outcome`；JSONPath 与现有 `accepted_tool_outcome_json` 完全一致，Host机械渲染整个 citation object，不枚举 Fins keys。
- F03/F04：Tool Trace 复用现有 source projection的 text/state；RunInput/Memory/Compact/LLM-ready Trace 缺 canonical material一律 `HostDurableError`，无 skip/fallback/limited branch。
- F05/F06：ordinary/awaiting identity digest均从 typed candidate原样映射；request-event readable Trace 用 strict atom resolver覆盖 inline/descriptor，不输出内部 placeholder或 ref/digest。
- F07/F08：runtime package只删 docstring module item且保留单文件 coverage；`eventlogg` typo、旧 safe-display 文案和 `render(None)` assertions均进入负例/替换矩阵。
- rejected items保持：真实 Doc/Web/Fins smoke仍是 hard gate；Host不枚举 citation keys；runtime coverage未豁免；slice仍恰为 `3`。
- inventory保持 37 个 prompt assets、114 个 constructor paths、R01 30 rows；fix ledger 唯一 ID count为 8。
- plan/fix whitespace checks无 diagnostic；工作区仍无 production、tests、README 或 design truth diff。

## 3. Handoff

AgentMiMo 与 AgentDS 必须对**完整修订计划**分别重新执行 `/planreview`，逐项确认 F01-F08，且重新挑战是否引入新 gap。两路都通过并经 Controller 裁决前，不得进入 implementation、commit 或 push。
