# PR 190 Compactor LLM-facing F01-F03 plan review fix

## Gate metadata

- Gate: `plan review fix`
- Work unit: 修复 PR 190 的 Compactor LLM-facing prompt review findings F01-F03
- Branch: `codex/interactive-oracle`
- Timestamp: `2026-08-03T17:29:42+08:00`
- Reviewed plan: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- Review artifacts:
  - `docs/reviews/plan-review-mimo-20260803-171726.md`
  - `docs/reviews/plan-review-ds-20260803-171916.md`
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-review-fix-20260803-172942.md`
- Completion status: `plan-review-fix-complete`，等待独立 plan re-review
- Next entry point: `plan re-review`

## Scope

本 gate 完整读取两路 plan review artifact，只修改 plan artifact 并新增本 durable fix artifact。未修改生产代码、测试、
prompt asset、README、publication manifest 或既有 review artifacts；未进入 implementation、commit 或 PR 操作。

## First-principles decision

修计划的动机成立。两路 review 未推翻原计划的 owner boundary，但证明原计划仍有几处会迫使 implementation Agent
自行选择 provider、发明 example、猜 cap message 构造点或混淆静态测试与行为观察。正确修复是把这些决定写回各自
owner 和 slice contract，而不是在 projector、parser、fixture 或下游增加 fallback。

## Controller decisions A-H

| Item | Decision | Plan fix |
|---|---|---|
| A | `accepted` | S3 冻结为先检查并使用 `PROVIDER_CASES[0]` Mimo；仅当 `MIMO_PLAN_API_KEY` 缺失/空或 Mimo 被既有精确环境分类判定不可用时，才使用 `PROVIDER_CASES[1]` DeepSeek。两者均不可用时精确 skip，不得回落 Gemini/Qwen；implementation artifact 必须记录实际 provider 与 fallback/skip 原因。 |
| B | `accepted` | 明确直接在 `context_governance.py::_collect_policy_issues/_section_caps` 的 `_issue(...)` message 构造点嵌入 actual、cap、计量对象和直接缩减动作。原数据流已有 actual/cap，当前缺陷只是 message 没有；projector 不读 policy、不读 candidate、不重算。 |
| C | `accepted` | projector 签名冻结为 `_repair_feedback_prompt_json_vnext(feedback: CompactRepairFeedbackV2) -> dict[str, JsonValue]`，直接读取 typed feedback/issue 字段，不调用 `to_json()`，不接受 raw mapping。 |
| D | `accepted` | plan 内新增紧凑、完整、同源、production-valid 的 example input/output JSON 草稿。字段说明逐项覆盖八种 `source_kind`，示例仅使用 `E1/A1/T1/D1`，覆盖 evidence、answer、intent、reference、diagnostic 和 explicit drop，不机械展示全部 source kind。 |
| E | `accepted` | S1 deterministic adversarial 明确只验证静态 prompt/data boundary；S3 real provider observation 才验证行为。行为 oracle 只拒绝执行注入命令或制造其要求的虚假事实，允许 diagnostic 把攻击文本作为材料风险说明。 |
| F | `accepted` | S2 新增 summary size 加四个 section item/size 同时超限的九 issue case，验证 projected feedback 总长仍有界且 actual/cap/计量对象/action 未被截断；内部术语检查写入 S1 与 S4。 |
| G | `rejected-with-reason` | “旧 T1 固定断言是未规划的高 blocker”这一结论不成立：原计划的 affected test、S1 与 test matrix 已明确删除固定未定义 T1 oracle，并替换为同源 production parser/governance contract。为消除行级歧义，修订计划仍明确写出删除 `assert '\"source_labels\": [\"T1\"]' in user_prompt_template`，且禁止换成另一条固定 label 字符串断言。 |
| H | `accepted` | metadata 不再写“用户要求暂停”，改为“总控按 gate 拆分派发”；current gate 为 plan review fix complete，next entry point 为 `plan re-review`。 |

## Review finding adjudication

| Source finding | Decision | Fix/re-review status | Evidence |
|---|---|---|---|
| MiMo-01：旧 T1 断言构成高 blocker | `rejected-with-reason` | `证据失效` | 原计划已指定删除旧 oracle 并用同源 parser/governance contract 替换，故“实施必须自行决定修法”的高 blocker 前提不成立；修订计划补写具体被删除断言，消除剩余表述歧义。 |
| MiMo-02 / DS-P1：真实 provider 未优先 Mimo | `accepted` | `已修复` | S3 已冻结 Mimo-first、DeepSeek-only fallback、两路均不可用精确 skip、禁止 Gemini/Qwen fallback，并要求 artifact 记录实际 provider。 |
| MiMo-03：cap feedback 构造点欠规格 | `accepted` | `已修复` | Contract decision 4 与 S2 已明确在 `_collect_policy_issues/_section_caps` 直接构造 message；无 schema 扩张，无 projector 重算。 |
| MiMo-04：projector typed input 不够明确 | `accepted` | `已修复` | 已写出完整 typed 签名和逐字段读取路径，并明确禁止 `to_json()`/raw mapping。 |
| MiMo-05：静态 adversarial 与模型行为边界不清 | `accepted` | `已修复` | S1/test matrix 只承诺静态边界；S3 承诺 real provider 行为观察，并收窄 oracle。 |
| DS-P2：plan 未给出完整 example pair | `accepted` | `已修复` | plan 已写入四 label 完整 pair，并在本 gate 用 production parser/governance 验证。 |
| DS-P3：多 section cap feedback 边界未量化 | `accepted` | `已修复` | S2 已要求九 issue simultaneous reject、总长边界与每条关键信息未截断断言。 |
| DS-P4：内部术语检查未显式同步 | `accepted` | `已修复` | S1 增加禁止术语 owner 检查，S4 增加文档/LLM-facing 术语复核。 |

## Example validation evidence

使用 plan 中同一份 JSON 草稿构造 typed `CompactInputV2`，并调用现有 production owner：

1. `parse_conversation_compact_output_vnext(request, raw_output)`：通过；
2. `accept_compact_candidate_v2(request, candidate, default_memory_projection_policy())`：返回 `CompactAcceptedTruthV2`；
3. represented coverage：`E1 -> session_summary/evidence_facts`、`A1 -> session_summary/answer_anchors`、
   `T1 -> session_summary/forward_intents/reference_continuity`；
4. explicit drop：`D1 -> redundant`；
5. represented labels 与 drop labels 互斥，并集精确等于 input 的全部 boundary labels。

这项验证只证明 example 的静态 production contract，不冒充真实 provider 行为证据。

## Changed files

- `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-review-fix-20260803-172942.md`

## Validation

- 两路 review artifact：已完整读取并逐项裁决。
- Production parser + Context Governance example validation：通过。
- `git diff --check`：通过，无 whitespace error。
- Tests/pyright/real provider smoke：未运行；本 gate 未修改生产代码或测试，且不得进入 implementation。

## Documentation decision

本 gate 只更新 plan 并新增其 fix artifact。README/design 的职责事实尚未发生变化，不在 plan-fix gate 提前写入未来实现；
既有 review artifacts 必须原样保留。

## Residual risks and uncovered areas

| Risk | Classification | Owner/destination |
|---|---|---|
| Prompt 指令不能数学证明模型忠实性 | `tracked by existing issue` | 既有 Issue 80；当前 approved plan 以 S1 静态 contract 与 S3 real provider observation 降低风险。 |
| Mimo/DeepSeek 输出随机性与环境不可用 | `covered by later approved slice` | S3；按 Mimo-first 与既有精确环境分类执行并记录实际 provider。 |
| 九条 simultaneous cap feedback 的实际长度和截断行为尚未由实现测试执行 | `covered by later approved slice` | S2 owner-level contract test。 |
| 新增 LLM-facing 文本可能意外泄漏内部术语 | `covered by later approved slice` | S1 owner check + S4 aggregate check。 |

无未分类 residual risk，无 blocking open question。

## Completion decision

- Fix gate decision: `pass`
- Accepted findings: 已全部写回 plan，并标记为 `已修复`。
- Rejected finding: MiMo-01 的“高 blocker”结论按直接证据标记 `rejected-with-reason` / `证据失效`；其有价值的行级澄清已纳入 plan。
- Dispatch state: 总控按 gate 拆分派发，本次不继续执行 re-review。
- Next entry point: `plan re-review`
