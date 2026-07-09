# WU-SEMANTIC-OWNERSHIP-01 P1-C Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-C`
- Gate: plan review fix only
- Fix basis: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-review-controller-adjudication.md`
- Updated plan: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- Updated delivery: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-codex.md`
- Constraint: 只修复 plan，不实现代码，不运行 implementation tests。

## Motivation Check

Controller 的 `fix-required` 判断成立。核心问题不是 plan 结构错误，而是 accepted findings 中若干路径需要从“实现时再发现”提升为显式 plan contract，尤其是 `run_input.py` memory `evidence_kind=...` 已确认进入 `SystemMessage`，不应继续作为条件性审计项。

## Accepted Finding Fixes

| Finding | Plan fix |
|---|---|
| `P1C-PLAN-F01` | S1 将 `dayu/host/run_input.py` 中 `_memory_evidence_fact_message()` 与 fallback codec 的 `evidence_kind=...` 渲染列为确定性 LLM-facing cleanup；要求删除或改为业务可读文本；`tests/host/test_run_input_builder.py` 必须覆盖这两条 rendering path。 |
| `P1C-PLAN-F02` | S0 duplicate classification 扩展到 `REUSE` / `HINT` / `HARD_STOP` / `REQUIRE_JUSTIFICATION` / `DURABLE_MISSING` 进入 `ToolFailedOutcome` 的路径，并要求区分合法 LLM-facing 行为指导与治理泄漏。 |
| `P1C-PLAN-F03` | S0 增加“等待工具结果返回” litmus test：删除后是否导致模型误判工具同步或编造结果；若错误/失败语义可由 `error`、message 或 outcome type 表达，则治理词应删除。 |
| `P1C-PLAN-F04` | S2 显式纳入 `ToolBusinessCancelled` optional fallback / docstring 清理，并要求审计 Doc/Web cancellation message 中的“宿主取消”和 Doc/Web/Fins hint 中的“后续调度”。 |
| `P1C-PLAN-F05` | S1 要求 implementation 先选择并记录 evidence kind Host derivation 策略，列出按 material kind、Host metadata 预标注、业务可读 source/type mapping 三个候选；旧 compact artifacts 按全新 schema 起库处理，不新增兼容读取。 |
| `P1C-PLAN-F06` | S2 要求 Fins / Doc / Web cancellation hint 改写保持一致；可优先共享层中立中性 helper/constant，但不得引入 Host governance 文案；不抽取时必须在 implementation artifact 做一致性审计。 |
| `P1C-PLAN-F07` | S3 与 validation commands 增加 P1-A accepted-result projection contract preservation scan，确认 P1-C consumers 不重新推导 query/status/source/result。 |

## Owner Boundary Impact

- `run_input.py` memory rendering owner：RunInputBuilder projection boundary。因为输出是 `SystemMessage`，S1 必须在投影边界清理，不能在测试夹具或下游消费者掩盖。
- Duplicate governance owner：policy message 首次产生于 `dayu.host.tool_duplicate_governance`，但 `ToolRuntime` 可将非 allow decision 投影为 `ToolFailedOutcome`；S0 必须按路径分类，合法行为指导可保留，治理词才改写。
- Cancellation wording owner：工具 callable / runtime outcome construction boundary。runtime 不拥有 Host-governance LLM-facing 默认文案；Doc/Web/Fins caller 必须提供一致业务可读取消说明。
- Compaction evidence kind owner：Host compaction material / parser boundary。LLM 不再选择内部 evidence pipeline enum；Host derivation 策略必须有可靠输入信号。

## Validation

本次只修改文档，因此按用户要求只运行：

```bash
git diff --check
```

结果：通过，无输出。

## Residual Risk

- implementation 仍需用代码路径确认 duplicate message 的最终投影位置；本 plan fix 只要求分类范围完整，不提前改行为。
- evidence kind derivation 的最终策略仍需 implementation 基于当前 material structure 选择并记录理由。
- 若 implementation 发现旧 compact artifacts 必须兼容读取，应停止并回到 controller 裁决，不能在 P1-C 里加兼容分支。
