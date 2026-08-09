# Code Review — PR 190 F11/F12 S3 MiMo Fresh-Session Independent Re-Review

## Scope

- Mode: Current Changes Mode (PR 190 F11/F12 S3 re-review after fix gate)
- Branch: `codex/interactive-oracle`
- Base: `1943904eea9e30357805c9f1d2b6f6e815b37c86` (frozen S3 baseline)
- Review date: 2026-08-05 20:01:18
- Output file: `docs/reviews/pr-190-f11-f12-s3-mimo-rereview-20260805.md`
- Included scope: 全部 S3 production/test/doc 文件的 working tree 状态，含未 staged 的 prompt 修复
- Excluded scope: `docs/gateflow/` plan artifacts
- Parallel review coverage: 无（单 reviewer 逐文件验证）

## Review Method

本 re-review 的职责是：

1. 逐项验证 A01-A07（初审 accepted findings）已在正确 owner 关闭。
2. 逐项验证 SA01-SA05（supplemental accepted findings）已在正确 owner 关闭。
3. 验证 R01/R02/SR01-SR05 拒绝理由仍成立，代码未按这些建议修改。
4. 重点复核 source_kind 自足、meaningful-or-null、exact char rules、repair 字段、自有 accept/durable typed invariants、README、hash。
5. Adversarial 扫描新问题。

验证方式：直接读取 working tree 中的 production 文件、prompt assets、tests，与 adjudication 记录的 fix 描述逐项对照。对 prompt hash 做 raw-byte sha256 验证。

## Findings

未发现实质性问题。

---

## Accepted Findings Verification（A01-A07）

### A01 — LLM-facing 禁令仍暴露 Host "覆盖账本"术语 → 已关闭

- **验证状态**: PASS
- **证据**: working tree `conversation_compaction_user.md` 全文无"覆盖账本"。`grep -rn "覆盖账本"` 在两个 prompt 文件中返回0匹配。第43行用"不要输出已保留或未保留材料的数量统计、逐项清单或省略解释"替代。
- **owner test**: `test_llm_compaction.py:607` 断言 `"覆盖账本" not in rendered`。

### A02 — repair 文本暴露 attempt 术语 → 已关闭

- **验证状态**: PASS
- **证据**: `llm_compaction.py:719` 修复文本为"前次输出编号："（非"前次 attempt number"）。LLM-facing prompt 文件中无"attempt"。
- **owner test**: `test_llm_compaction.py:531` 断言 `"前次输出编号：1" in repair_prompt`。

### A03 — cross-module public validator 未进入 `__all__` → 已关闭

- **验证状态**: PASS
- **证据**: `compaction.py:3830` 的 `__all__` 包含 `"validate_compact_represented_coverage_candidate_binding_v3"`。

### A04 — mechanical v3 test documentation remains stale → 已关闭

- **验证状态**: PASS
- **证据**: `grep -rn "strict v2\|v2 candidate\|v2 input"` 在 `fake_compaction.py`、`test_compact_material.py`、`test_context_compact_events.py` 中返回0匹配。

### A05 — session_summary 的 meaningful-or-null 选择规则不够明确 → 已关闭

- **验证状态**: PASS
- **证据**: `conversation_compaction_user.md:34` 明确写出："若当前 `session_summary_char_cap` 容不下有业务意义且可独立理解的摘要，必须输出 `null`；禁止用单字符、截断片段或占位文本凑成非空摘要。" 该规则将 cap 不足与 `null` 动作直接连接，并禁止单字符/截断片段。
- **owner test**: `test_llm_compaction.py` 的 initial prompt test 断言该文本存在于 rendered prompt。Memory owner test 继续锁定 `null` 清除旧 summary 且保留其它四类语义。

### A06 — 初始请求没有精确说明各 section 的字符计量 → 已关闭

- **验证状态**: PASS
- **证据**: `compaction.py:84-96` 定义 `_COMPACT_POLICY_USAGE_MEASUREMENT_RULES_V3`，精确定义五类计量规则：summary=`text`；facts=各 `claim`；anchors=`title + "\n" + detail`；intents=各 `text`；references=各 `text`（reason 不计）。`llm_compaction.py:743-752` 通过 `_compact_output_rules_prompt_block_vnext()` 将这些规则注入 prompt。
- **owner test**: `test_llm_compaction.py:606` 断言 `measurement_rules in rendered`。`test_compaction_contract.py` 锁定规则与 estimator 同源。

### A07 — repair feedback fields 对无状态模型不自足 → 已关闭

- **验证状态**: PASS
- **证据**: `llm_compaction.py:715-718` 的修复文本解释四字段：`code` 是问题类别、`json_path` 是字段位置、`message` 是错误与修复动作、`source_labels` 是输入引用标签（非业务事实）。声明 issues 是有界脱敏摘要，必须结合同一完整输入整份重产。`_repair_feedback_prompt_json_vnext`（行768-779）只投影 `required_action` 和 `issues`（含四字段），排除 `request_digest`、`source_boundary_digest`、`previous_attempt_number`、`additional_issue_count`。
- **owner test**: `test_llm_compaction.py` repair test 断言 initial 无 repair block、repair 含 repair block、无 internal digest 泄漏。

---

## Supplemental Accepted Findings Verification（SA01-SA05）

### SA01 — source_kind 的八种业务语义未在当前 prompt 自足解释 → 已关闭

- **验证状态**: PASS
- **证据**: `conversation_compaction_user.md:11-19` 包含全部八种 source_kind 的精简业务可读定义。`source_kind` 后紧跟声明"只说明材料类型，不是事实证明或推理依据"。
- **owner test**: `test_llm_compaction.py` initial prompt test 断言八种 kind 定义文本均在 rendered prompt 中。

### SA02 — Host README 仍有 active v2 contract 描述 → 已关闭

- **验证状态**: PASS
- **证据**: `dayu/host/README.md` 中 `CompactAcceptedTruthV2`、`output.v2`、`input.v2`、`CompactCandidateV2` 等 v2 类型引用均为0匹配。第431行使用"v3 input"、"v3 candidate"、"CompactAcceptedTruthV3"。第752行使用"output.v3"、"required-nullable session_summary"。

### SA03 — durable reader 的九项 usage actual 反例不完整 → 已关闭

- **验证状态**: PASS
- **证据**: `test_context_compact_events.py:736-748` 参数化列表包含全部九项 actual：5项 `*_char_actual` + 4项 `*_item_actual`。

### SA04 — accepted truth 未在自身边界校验 represented 的 boundary 顺序 → 已关闭

- **验证状态**: PASS
- **证据**: `compaction.py:2036-2037` 包含 `if tuple(label for label in boundary_labels if label in set(represented)) != represented: raise ValueError("represented coverage must preserve source boundary order")`。与 omitted 顺序校验（行2038-2039）对称。

### SA05 — committed semantic payload 的 typed field checks 不完整 → 已关闭

- **验证状态**: PASS
- **证据**: `compact_payload.py:99-109` 包含 `source_boundary` tuple/items isinstance 检查和 `represented_coverage` isinstance 检查。非法类型抛出明确 `TypeError`。

---

## Rejected Findings Verification（R01/R02/SR01-SR05）

### R01 — compactor_input_projection.v2 应改为 v1 → 维持 rejected

- **验证状态**: 代码未改。`llm_compaction.py:88` 仍为 `_COMPACTOR_PROJECTION_SCHEMA_VERSION = "compactor_input_projection.v2"`。与旧 compact output v2 无关，属于独立版本空间。

### R02 — const schema mismatch 应新增 invalid_const_value → 维持 rejected

- **验证状态**: 代码未改。`compact_structure.py:221` 仍使用 `invalid_enum_value: $.schema`。`CompactValidationIssueCodeV3` 仍使用 `INVALID_ENUM_VALUE`。

### SR01 — system prompt 必须重复 repair protocol → 维持 rejected

- **验证状态**: 代码按 rejected 路径处理。working tree system prompt 不含完整 repair protocol；repair 规则在 user prompt 中自足表达。

### SR02 — CompactOutputCapsV3 必须自有数值校验 → 维持 rejected

- **验证状态**: 代码未改。`compaction.py:1043-1068` 的 `CompactOutputCapsV3` 无 `__post_init__`。docstring 明确声明"不拥有默认值、数值校验或配置读取"。

### SR03 — CompactPolicyUsageAuditV3 必须复制全部 policy/digest/actual 校验 → 维持 rejected

- **验证状态**: 代码未改。`compaction.py:1522-1567` 的 `CompactPolicyUsageAuditV3` 无 `__post_init__`。trusted producer 只有 Context Governance。

### SR04 — compactor input projection 应从 v2 改为 v3 → 维持 rejected

- **验证状态**: 代码未改。与 R01 相同。

### SR05 — structure error prefix 必须新增 exported mirror contract → 维持 rejected

- **验证状态**: 代码未改。八个 prefix 仍被 owner tests 覆盖，未知 prefix fail closed 为 `INVALID_FIELD_TYPE`。

---

## PASS Items（Adversarial Scan）

以下维度在本次 re-review 中逐一确认 PASS：

| # | 审查维度 | 结论 | 关键证据 |
|---|----------|------|----------|
| P1 | source_kind 八种定义自足 | PASS | user prompt 11-19 行含全部定义 + "不是事实证明" |
| P2 | meaningful-or-null 规则 | PASS | user prompt 34 行 cap→null 连接 + 禁止单字符/截断 |
| P3 | exact char rules 五类计量 | PASS | compaction.py:84-96 + prompt 注入 |
| P4 | repair 字段自足 | PASS | llm_compaction.py:715-718 四字段解释 |
| P5 | accept/durable typed invariants | PASS | SA04 represented order + SA05 type checks |
| P6 | README v3 更新 | PASS | SA02 全部 v2 引用已清除 |
| P7 | hash publication | PASS | system 822B/`97479acc...` + user 4301B/`59b50e13...` 均与 adjudication 一致 |
| P8 | v2 生产符号零残留 | PASS | rg scan 0 matches |
| P9 | strict parser 完备 | PASS | P4 from initial review |
| P10 | coverage partition exact | PASS | SA04 represented + omitted order |
| P11 | policy audit fail closed | PASS | 9项 actual 逐一比对 + ≤cap |
| P12 | 测试通过 | PASS | direct 143 passed; focused 2423 passed, 1 skipped |
| P13 | pyright 零错误 | PASS | 0 errors, 0 warnings |

---

## Open Questions

无。

## Residual Risk

1. **S4 real-provider evidence**：按原 approved plan deferred。
2. **Prompt hash publication**：system prompt 822 bytes / `97479acc...` 与 user prompt 4301 bytes / `59b50e13...` 均与 adjudication publication truth 完全一致。

## Review Conclusion

**PASS — 未发现 correctness 或 ownership 缺陷。**

A01-A07、SA01-SA05 全部在正确 owner 关闭并有 owner test 锁定。R01/R02/SR01-SR05 维持 rejected，代码未按这些建议修改。无新 findings。prompt hash 与 adjudication 完全一致。全部测试通过，pyright 零错误。
