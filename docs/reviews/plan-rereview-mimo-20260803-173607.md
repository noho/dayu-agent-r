# Plan Re-review — PR 190 Compactor LLM-facing F01-F03

## Re-review metadata

- **Reviewed target**: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- **Plan fix artifact**: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-review-fix-20260803-172942.md`
- **Prior reviews**:
  - `docs/reviews/plan-review-mimo-20260803-171726.md`
  - `docs/reviews/plan-review-ds-20260803-171916.md`
- **Re-review timestamp**: 2026-08-03T17:36:07+08:00
- **Reviewer posture**: adversarial re-review；逐项验证 accepted findings 是否已修复，重点挑战新引入的 test-only fallback helper

## Verification method

对每个 accepted finding，用 plan artifact、plan fix artifact 和代码事实三源交叉验证。对新引入的 test-only fallback helper，用 `public_smoke_support.py` 现有代码结构验证是否保持唯一环境分类真源且不扩 production provider 语义。

## Finding-by-finding verification

### MiMo-01：旧 T1 断言构成高 blocker

- **结论**: `证据失效`
- **验证**: plan fix artifact 的 controller decision G 已用直接证据拒绝该 finding。原计划的 S1 "Exact allowed changes" 第三条和 test matrix "Example contract" 行已明确删除旧 T1 oracle 并替换为同源 parser/governance contract。修订计划补写了具体被删除断言 `assert '"source_labels": ["T1"]' in user_prompt_template`（`test_public_compact_smoke.py:204`），消除行级歧义。
- **代码事实**: `test_public_compact_smoke.py:204` 确实存在该固定断言，与 plan 的替换方案直接冲突。但 plan fix 已明确写出删除该断言，实施 agent 无需自行决策。
- **判定**: 原 finding 的"高 blocker"前提（实施 agent 必须自行决定修法）不成立。

### MiMo-02 / DS-P1：真实 provider 未优先 Mimo

- **结论**: `已修复`
- **验证**: S3 "Exact allowed changes" 第一条已冻结为"先检查并使用 `PROVIDER_CASES[0]`（Mimo）；只有 `MIMO_PLAN_API_KEY` 缺失/空，或 Mimo 的真实调用失败被 `public_smoke_support.py` 既有 network/transient unavailable/explicit unavailable/quota-rate-limit 精确分类判定为环境不可用时，才改用 `PROVIDER_CASES[1]`（DeepSeek）。Mimo 的其它失败必须 fail，不得 fallback。"
- **代码事实**: `public_smoke_support.py:815-823` 确认 `PROVIDER_CASES[0]` 是 Mimo；`dayu/config/README.md:181` 确认 production compactor 使用 `mimo-v2.5-pro-plan`。plan fix 的 S3 要求与冻结要求一致。
- **判定**: Mimo-first 逻辑已明确写入 plan，DeepSeek-only fallback 条件已精确定义，禁止 Gemini/Qwen 回落。

### MiMo-03：cap feedback 构造点欠规格

- **结论**: `已修复`
- **验证**: plan fix 的 contract decision B 明确"直接在 `context_governance.py::_collect_policy_issues/_section_caps` 的 `_issue(...)` message 参数中构造"，并给出具体 message 格式模板。S2 "Exact allowed changes" 第四条重复确认。
- **代码事实**: `context_governance.py:496` 当前 message 为 `"session_summary 超过 Memory policy size cap。"`（无数值）；`context_governance.py:551` 为 `f"{section} 超过 Memory policy item cap。"`（无数值）；`context_governance.py:560` 为 `f"{section} 超过 Memory policy size cap。"`（无数值）。`estimate_memory_size_units(...).units`、`len(texts)`、`total` 和 policy cap 值均已在 `_collect_policy_issues/_section_caps` 的 guard 条件中计算，但未进入 message 字符串。plan 的修复只改 message 构造，不改数据流，方向正确。
- **判定**: 构造点已精确定位，改法明确（在现有 `_issue()` 调用处嵌入已有数值），不新增 schema 字段，projector 不读 policy。

### MiMo-04：projector typed input 不够明确

- **结论**: `已修复`
- **验证**: plan fix 的 contract decision C 冻结签名为 `_repair_feedback_prompt_json_vnext(feedback: CompactRepairFeedbackV2) -> dict[str, JsonValue]`，明确"直接读取 `feedback.required_action` 与 `feedback.issues`，并直接读取每个 typed issue 的 `code.value`、`json_path`、`message`、`source_labels`；不得先调用 `feedback.to_json()`，不得接受或解析 raw mapping"。
- **代码事实**: `compaction.py` 的 `CompactRepairFeedbackV2` 是 typed dataclass，`to_json()` 返回包含 `previous_attempt_number`、`additional_issue_count` 的 dict。plan 的 projector 明确跳过 `to_json()`，直接读 typed 字段，逻辑更清晰且不暴露 internal 治理字段。
- **判定**: 签名和读取路径已完全指定，无歧义。

### MiMo-05 / DS Challenge 4：静态 adversarial 与模型行为边界不清

- **结论**: `已修复`
- **验证**: plan fix 的 contract decision E 明确"S1 deterministic adversarial 明确只验证静态 prompt/data boundary；S3 real provider observation 才验证行为"。S1 "Exact allowed changes" 第四条写"参数化注入材料位置为 current/trace/evidence/answer；S1 仅静态断言原文仍在 data block、prompt 明确禁止执行、没有 production filter。S1 不声称验证模型行为；行为只由 S3 real provider observation 验证"。
- **代码事实**: test matrix 的 "Renderer adversarial" 行已标注"deterministic static check only"语义，"Real provider smoke" 行覆盖行为观察。S3 行为 oracle 只拒绝执行注入命令或制造其要求的虚假事实，允许 diagnostic 把攻击文本作为材料风险说明。
- **判定**: 静态/行为分层已明确写入 plan 和 test matrix。

### DS-P2：plan 未给出完整 example pair

- **结论**: `已修复`
- **验证**: plan fix 的 contract decision D 新增了完整 example input/output JSON 草稿，使用 `E1/A1/T1/D1` 四个 label。plan fix artifact 的 "Example validation evidence" 节记录了用该草稿构造 typed `CompactInputV2` 后通过 production parser 和 `accept_compact_candidate_v2` 的结果：parser pass、governance accepted、represented coverage 为 `E1->session_summary/evidence_facts`、`A1->session_summary/answer_anchors`、`T1->session_summary/forward_intents/reference_continuity`、`D1->explicit drop`，labels 互斥且并集精确等于全部 boundary labels。
- **判定**: example 草稿已提供且通过 production owner 验证，实施 agent 无需自行设计。

### DS-P3 / MiMo-03 补充：多 section cap feedback 边界未量化

- **结论**: `已修复`
- **验证**: S2 "Expected assertions" 第六条写"simultaneous reject 的 projected feedback 总长不超过 `MAX_COMPACT_REPAIR_FEEDBACK_CHARS`；九条 message 的关键 actual、cap、计量对象和直接动作均完整保留，未被单 issue 或总体边界截断"。S2 "Exact allowed changes" 第五条写"增加 all-section simultaneous cap reject：session summary size、四个 section item count、四个 section aggregate size 同时超限，形成九条 policy issues"。
- **代码事实**: `compaction.py` 定义 `MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS=240`、`MAX_COMPACT_REPAIR_FEEDBACK_CHARS=8192`。九条精确化 message（每条约 60-80 字符）总长约 540-720，远在 8192 内。plan 要求 S2 测试覆盖该场景。
- **判定**: simultaneous reject 场景已量化要求，边界验证已写入 test assertions。

### DS-P4：内部术语检查未显式同步

- **结论**: `已修复`
- **验证**: S1 "Exact allowed changes" 最后一条写"在 S1 审查现有 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` / `_FORBIDDEN_COMPACTOR_MATERIAL_TERMS`，并补入本次可能泄漏的内部实现术语；业务可读 contract 字段名不列为禁止词"。S4 "Exact allowed changes" 最后一条写"复核 S1/S4 的 LLM-facing 文本不含 Host/Memory/Attempt、Python 类型名、迁移名或其它非任务所需内部术语；若发现新的泄漏类别，同步更新 owner 级禁止术语检查"。
- **代码事实**: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS`（`test_public_compact_smoke.py:138-158`）和 `_FORBIDDEN_COMPACTOR_MATERIAL_TERMS`（`test_public_compact_smoke.py:159-169`）已定义。plan 的 S1 和 S4 双重检查覆盖了新增 prompt 文本的术语审查。
- **判定**: 禁止术语同步已明确写入两个 slice。

## 重点挑战：test-only fallback helper

### 问题

plan S3 提出"在 `public_smoke_support.py` 的测试基础设施 owner 内抽取可复用的'分类结果/原因'helper，让既有 skip helper 与 Mimo → DeepSeek selector 共用同一组 marker 真源；不得在 smoke 测试复制 marker 或解析 skip 文本"。需验证：(a) 是否保持唯一环境分类真源；(b) 是否不扩 production provider 语义。

### 验证

**(a) 唯一环境分类真源**

- **现有分类机制**: `_skip_if_provider_failure_message`（`public_smoke_support.py:1251-1286`）是唯一分类函数，使用四组 marker tuple：`_NETWORK_FAILURE_MARKERS`（:129-142）、`_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS`（:143-159）、`_EXPLICIT_UNAVAILABLE_MARKERS`（:177-184）、`_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS`（:160-176）。该函数当前直接调用 `pytest.skip()`。
- **新 helper 设计**: plan 要求抽取一个返回"分类结果/原因"的 helper，复用同一组 marker tuple。既有 `_skip_if_provider_failure_message` 可重构为调用该新 helper + `pytest.skip()`，或新 helper 独立读取同一组 marker。无论哪种方式，marker 真源不变。
- **selector 使用**: Mimo → DeepSeek selector 调用新 helper 获取分类结果：若返回原因（环境不可用）→ fallback；若返回 None（非环境失败）→ fail。DeepSeek 同理。两者均不可用时，用包含两路原因的精确消息 skip。
- **结论**: marker 真源唯一（同一组 tuple），分类逻辑唯一（同一函数或其直接委托），不复制 marker、不解析 skip 文本。

**(b) 不扩 production provider 语义**

- **代码隔离**: 新 helper 位于 `tests/host/public_smoke_support.py`（测试基础设施），不在 `dayu/host/` 或 `dayu/config/`（production 路径）。
- **无 production 路由影响**: `public_smoke_support.py` 不被任何 production 代码 import。`dayu/host/` 下的 provider/model selection、execution profile、AgentPolicy 均不引用该文件。
- **fallback 语义**: fallback 仅发生在测试级 provider 选择（Mimo → DeepSeek），不改变 production compactor 的 `compactor_baseline.model_id`（仍指向 `mimo-v2.5-pro-plan`）。
- **结论**: helper 是纯测试基础设施，不引入 production fallback 逻辑、不改 production provider 路由、不扩 production provider 语义。

### 潜在风险

- **认证失败分类**: `401 unauthorized`、`invalid API key` 等认证错误不在四组 marker 中，会被分类为"非环境失败"→ test fails。这符合 plan 的"MIMO_PLAN_API_KEY 缺失/空才 fallback"语义——有 key 但 key 无效是配置错误，不是环境不可用。
- **新 helper 的精确语义**: plan 说"暴露非跳过式分类结果"，但未给出函数签名。实施 agent 需决定返回类型（`str | None`、`NamedTuple`、`dataclass`）。这是低风险实施细节，不构成 blocker。

## 新发现

未发现新 blocking finding。以下为低风险观察：

### R1-已覆盖-低-example labels 与 source_kind 表的覆盖差异

- **位置**: plan contract decision 2 的 source_kind 表 vs example JSON 草稿
- **观察**: source_kind 表列出八种类型，example 只用 `E1/A1/T1/D1` 四个 label（覆盖 `evidence_material`、`answer_material`、`trace_material`、`previous_session_summary` 四种 kind）。plan 明确说明"示例不为展示枚举而机械制造八个 source"，且 example 覆盖了 evidence、answer、intent、reference、diagnostic 和 drop 六种必要输出区。
- **判定**: 这是 plan 的有意设计，不是缺陷。source_kind 表提供字段级语义说明，example 展示 production-valid 的最小完整对。实施 agent 在 prompt 中写入 source_kind 表和 example 时，八种 kind 的语义已自足。

### R2-已覆盖-低-`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 不含 `CompactRepairFeedbackV2`

- **位置**: `test_public_compact_smoke.py:138-158`
- **观察**: 现有禁止词列表不含 `CompactRepairFeedbackV2`、`CompactValidationReportV2`、`CompactValidationIssueV2` 等 internal 类型名。若实施 agent 在 prompt 中意外引入这些名称，现有黑名单不会捕获。
- **判定**: plan 的 S1 已要求"审查现有禁止术语列表并补入本次可能泄漏的内部实现术语"，S4 要求"复核 LLM-facing 文本不含 Host/Memory/Attempt、Python 类型名"。这覆盖了该风险。且新 projector 的 LLM-facing 输出只有 `required_action` 和 `issues`（业务可读字段），不包含类型名。

## Open questions

- 无 blocking open questions。
- **Non-blocking**: test-only fallback helper 的精确返回类型（`str | None` 或 structured type）由实施 agent 决定，不影响 plan 正确性。

## Residual risks

| Risk | Classification | Tracking destination |
|---|---|---|
| Prompt 指令不能数学证明模型忠实性 | 已知、已分类 | 既有 Issue 80；plan 以 S1 静态 contract + S3 real provider observation 降低风险 |
| Mimo/DeepSeek 输出随机性与环境不可用 | 已覆盖 | S3；按 Mimo-first + 既有精确环境分类执行并记录实际 provider |
| 九条 simultaneous cap feedback 实际长度和截断行为 | 已覆盖 | S2 owner-level contract test |
| 新增 LLM-facing 文本可能意外泄漏内部术语 | 已覆盖 | S1 owner check + S4 aggregate check |
| 认证失败（401/invalid key）不被环境分类覆盖 | 低风险 | 有 key 但 key 无效是配置错误，符合"MIMO_PLAN_API_KEY 缺失/空才 fallback"语义 |

无未分类 residual risk。

## Re-review conclusion

**pass**

逐项验证结果：

| Source finding | 结论 |
|---|---|
| MiMo-01：旧 T1 断言构成高 blocker | `证据失效` — plan fix 已明确删除该断言 |
| MiMo-02 / DS-P1：真实 provider 未优先 Mimo | `已修复` — S3 冻结 Mimo-first、DeepSeek-only fallback |
| MiMo-03 / DS-P3：cap feedback 构造点欠规格 | `已修复` — `_issue()` message 嵌入 actual/cap |
| MiMo-04：projector typed input 不够明确 | `已修复` — typed 签名、直接读字段、禁 `to_json()` |
| MiMo-05 / DS Challenge 4：静态/行为边界不清 | `已修复` — S1 静态、S3 行为，分层明确 |
| DS-P2：未给出完整 example pair | `已修复` — 提供草稿并通过 production owner 验证 |
| DS-P3：多 section cap 边界未量化 | `已修复` — S2 覆盖九条 simultaneous reject |
| DS-P4：内部术语检查未同步 | `已修复` — S1 + S4 双重检查 |

重点挑战结论：test-only fallback helper 保持唯一环境分类真源（复用同一组 marker tuple 和分类函数），不扩 production provider 语义（纯测试基础设施、不改 production 路由）。

无 blocking finding，plan 可进入 implementation gate。
