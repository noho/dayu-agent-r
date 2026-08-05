# PR 190 F11/F12 PR-Review Fix Re-Review (DeepSeek)

## Scope

- Mode: current changes (worktree uncommitted fix)
- Branch: `codex/interactive-oracle`
- Exact base: `9fa3ff799506e66f995b4156dbb960c98c2f737e`
- Re-review date: 2026-08-06
- Output file: `docs/reviews/pr-190-f11-f12-pr-ds-rereview-20260806.md`
- Controller adjudication: `docs/reviews/pr-190-f11-f12-pr-review-adjudication-20260806.md`
- Fix artifact: `docs/reviews/pr-190-f11-f12-pr-review-fix-20260806.md`
- Previous DS review: `docs/reviews/pr-190-f11-f12-pr-ds-review-20260806.md`
- Included scope: `git diff 9fa3ff79..HEAD` 未提交修改（5 files, +319/-76）
  - `dayu/host/compact_structure.py`
  - `dayu/host/llm_compaction.py`
  - `tests/host/test_compaction_contract.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_tool_trace_analysis_rules.py`
- Excluded scope: 无
- Parallel review coverage: 无；主 reviewer 独立完成全部走读

## 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest -q tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py --cov=dayu.host.compact_structure` | 53 passed, coverage 89% (223 stmts, 25 missed) |
| `pytest -q tests/host/test_tool_trace_analysis_rules.py tests/host/test_tool_trace_analysis.py` | 32 passed |
| pyright (full repo: `dayu/ tests/ utils/`) | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | PASS |

## 逐项裁决复核

### MiMo-01 — force-answer 应移除 structured output

**裁决: rejected。** 无对应生产代码或测试修改。当前 `_agent_request_vnext` 仍原样传递 `structured_output` 参数，`run_prepared_compactor_proposal` 仍对 `finish_reason=LENGTH` raise `LLMCompactionProposalError`。与 design truth 同源，未引入降级路径。✓

### MiMo-02 — malformed compactor terminal 不应令 Tool Trace fail closed

**裁决: rejected。** 无对应修改。`_validated_prepared_response_identity` 仍对 run_id/attempt_id/provider/model mismatch fail closed。未新增降级语义。✓

### MiMo-03 — rejected attempt 的 successful response identity 缺 analysis owner test

**裁决: accepted。** 新增 `test_rejected_compactor_response_identity_projects_from_typed_owner_to_all_outputs`（`tests/host/test_tool_trace_analysis_rules.py:1566`）。

逐项验证：
- disposition 正确为 `ATTEMPT_REJECTED`（line 1622）✓
- typed report、JSON、Markdown 三路输出均从 `successful_response_identity` 投影（lines 1623–1660）✓
- 邻近 `source_event_payload` 携带 poison 值 `provider-neighbor-poison` / `model-neighbor-poison` / `request-neighbor-poison`（lines 1600–1604）✓
- 三路输出均不含 poison 值（lines 1665–1670）✓
- 证明 analysis owner 不从 config 或邻近事件推断 identity ✓

### MiMo-04 — parser 的 request 参数没有语义作用

**裁决: accepted。** `parse_conversation_compact_output_vnext` 签名改为仅接收 `final_answer: str`（`llm_compaction.py:797`）。

逐项验证：
- 旧 `request: CompactInputV3` 参数已移除 ✓
- 旧 `TypeError("request must be CompactInputV3")` 守卫已删除 ✓
- 唯一生产调用方 `run_prepared_compactor_proposal` 已同步为单参数调用（line 374）✓
- 所有测试调用方已同步迁移 ✓
- 无 wrapper、alias、兼容分支或旧签名测试残留 ✓
- request/source/cap acceptance 仍只在 `_validated_prepared_response_identity` 与 Context Governance accept barrier 中 ✓

### MiMo-05 / MiMo-06 — repair code/path 从异常字符串反推

**裁决: accepted and combined。** 新增 `CompactStructureParseError`，删除字符串反推逻辑。

逐项验证：

**(a) structure owner 直接产生 typed failure:**
- `CompactStructureParseError`（`compact_structure.py:35`）携带 `code: CompactValidationIssueCodeV3`、`json_path: str`、`message: str` ✓
- `__init__` 含完整类型/格式守卫（lines 60–69）✓
- 所有 14 处 validation rejection 分支均直接构造 `CompactStructureParseError` 并传入 exact code 与 path ✓
  - `BLANK_REQUIRED_TEXT`：`parse_compact_candidate_v3`（line 256）、`_required_text`（line 543）、`_required_text_tuple` item（line 604）与 empty array（line 617）✓
  - `INVALID_JSON`：`parse_compact_candidate_v3`（line 264）✓
  - `INVALID_ENUM_VALUE`：schema const check（line 272）、`_parse_intent` status enum（line 744）✓
  - `DUPLICATE_JSON_KEY`：`_strict_object_pairs`（line 469）✓
  - `INVALID_FIELD_TYPE`：`_exact_object`（line 494）、`_required_text`（line 537）、`_required_array`（line 568）、`_required_text_tuple` item（line 598）✓
  - `UNKNOWN_JSON_KEY`：`_exact_object`（line 504）✓
  - `MISSING_REQUIRED_KEY`：`_exact_object`（line 512）✓
  - `DUPLICATE_SOURCE_LABEL`：`_required_text_tuple`（line 610）✓
- 无残留 `raise ValueError(...)` 在 validation 路径中 ✓

**(b) llm_compaction 完全停止字符串反推:**
- `_structure_validation_report` 签名改为 `(error: CompactStructureParseError)`（line 817）✓
- 只读 `error.code`、`error.json_path`、`error.message` typed fields（lines 827–829）✓
- 旧 `code_by_prefix` dict 映射已删除 ✓
- 旧 `_structure_error_path` 函数（message partition 提取 path）已删除 ✓
- `json_path` 与 `message` 分别经 `_safe_outcome_text` 脱敏/截断（lines 828–829）✓
- `source_labels` 固定为空 tuple（line 830）——语义正确，structure 层不产生 label 语义 ✓

**(c) 新测试直接证明无字符串反推:**
- `test_structure_repair_report_projects_typed_failure_fields_without_message_inference`（`test_llm_compaction.py:405`）构造 code=`UNKNOWN_JSON_KEY` 但 message 前缀为 `invalid_enum_value:` 的 `CompactStructureParseError` ✓
- 断言 `issue.code is UNKNOWN_JSON_KEY`（line 423）——来自 typed field，不是 message prefix ✓
- 断言 `issue.json_path` 不含 `message-only-path`（line 425）——证明 path 来自 typed field，不是从 message suffix 提取 ✓
- 断言脱敏（`sk-path-secret-123` → `<redacted>`）与 240 字符边界 ✓

### MiMo-07 — bounded repair feedback 单 issue 零 labels 时抛 RuntimeError

**裁决: rejected as unreachable。** 无对应修改。`build_compact_repair_feedback_v3` 未变更。✓

### MiMo-08 — runtime / Engine structured-output enums 缺同步守护

**裁决: rejected as evidence-invalid。** 无对应修改。✓

### DS-01 — aggregate coverage 声称 90%，单 suite 实测 85%

**裁决: rejected as measurement mismatch。** 本 re-review 按 aggregate acceptance 指定命令运行 owner-suite union，得到 89%（223 stmts, 25 missed）——与 fix doc 记录的 88.79% 一致。两种口径均超过 80% 门槛。✓

### DS-02 — immutable descriptor defensive branches 未覆盖

**裁决: rejected。** 无对应修改。missed lines 仍为内部 `RuntimeError` 防御分支（lines 331, 339, 342, 348, 378, 394, 400, 429, 447, 453）与 `CompactStructureParseError.__init__` 类型守卫（lines 61–69），外部不可注入。✓

## 五项重点逐项复核

### 1) typed parse failure 所有权

**结论: PASS。**

`CompactStructureParseError` 由 `compact_structure.py`（structure owner）唯一定义并直接产生。所有 14 处 rejection 分支均携带稳定 `CompactValidationIssueCodeV3` 与自解释 JSON path。`llm_compaction.py::_structure_validation_report` 只读取 typed fields `error.code`、`error.json_path`、`error.message`，旧 `code_by_prefix` 映射与 `_structure_error_path` 字符串解析已完全删除。无任何从 message 反推 code/path 的残留路径。

### 2) parse_conversation_compact_output_vnext fresh signature

**结论: PASS。**

签名已收缩为 `(final_answer: str) -> CompactCandidateV3`。旧 `request: CompactInputV3` 参数已删除。唯一生产调用方（`run_prepared_compactor_proposal:374`）与全部测试调用方已同步。无 wrapper、alias、`hasattr`/`getattr` 守卫或兼容分支残留。`except CompactStructureParseError` 精确捕获 structure 层异常；`TypeError`（编程错误）正确向上传播。request/source/cap acceptance 仍唯一归属 `_validated_prepared_response_identity` 与 Context Governance accept barrier，parser 层不参与语义受理。

### 3) rejected + successful identity test 同源证明

**结论: PASS。**

`test_rejected_compactor_response_identity_projects_from_typed_owner_to_all_outputs` 构造 `ATTEMPT_REJECTED` disposition 并保留 typed resolver 的原始 `successful_response_identity`，同时在邻近 event payload 注入 poison 值。断言 typed report、JSON 序列化、Markdown 三路输出均使用 `successful_response_identity` 的实际 provider/model/request-id/runner identity，且 poison 值不出现在任何输出中。证明 analysis owner 仅从 typed resolver projection 消费 identity，不从邻近 config/event 推断。

### 4) strict parser、安全脱敏、bounded repair、prompt/schema/Host acceptance/Engine semantics 无漂移

**结论: PASS。**

- **strict parser**: 所有 validation 规则（exact keys、类型、enum、非空文本、duplicate key、唯一 label）语义不变；仅异常类型从 `ValueError` 升级为 `CompactStructureParseError`（`ValueError` 子类）并携带 typed fields ✓
- **安全脱敏**: `_structure_validation_report` 对 `json_path` 与 `message` 分别执行 `_safe_outcome_text`（`redact_sensitive_diagnostic_values` + `truncate_diagnostic_text` 240 字符上限）；新测试 `test_structure_repair_report_projects_typed_failure_fields_without_message_inference` 证明 secret 不会泄漏到序列化输出 ✓
- **bounded repair**: `_safe_outcome_text` 的 240 字符边界未变；`_structure_validation_report` 仍产出单 issue、空 labels 的 `CompactValidationReportV3`；`build_compact_repair_feedback_v3` 未修改 ✓
- **prompt/schema**: `compact_output_template_v3`、`compact_output_json_schema_v3`、`compact_output_prompt_rules_v3` 均未修改 ✓
- **Host acceptance**: `LLMCompactionValidationError` 封装不变；`parse_conversation_compact_output_vnext` 仍将 `CompactStructureParseError` 映射为 `LLMCompactionValidationError` ✓
- **Engine semantics**: `_agent_request_vnext`、`_structured_output_request_v3`、`_validated_prepared_response_identity` 均未修改 ✓

### 5) 中文 docstring、严格类型、无 Any/object、allowed scope 和测试

**结论: PASS。**

- **中文 docstring**: `CompactStructureParseError` 类与 `__init__` 含完整中文 docstring（参数、返回值、异常）；`_structure_validation_report` 含中文 docstring；所有新增/修改测试函数含中文 docstring ✓
- **严格类型**: 全 diff 无 `Any`、`object`、无类型参数、无类型返回值 ✓
- **allowed scope**: 仅修改 `dayu/host/compact_structure.py`、`dayu/host/llm_compaction.py` 及对应 direct owner tests；未触及其他模块、prompt、schema、README、design doc、oracle/scenario registry 或 immutable evidence ✓
- **测试**: 53 + 32 = 85 passed；pyright 0 errors；coverage 89% > 80% ✓

## Findings

未发现实质性问题。

### 附注：`_structure_validation_report` docstring 微调建议

- **入口/函数**: `_structure_validation_report`
- **文件(行号)**: `dayu/host/llm_compaction.py:817–823`
- **实际状态**: docstring 写 "structure parser 抛出的类型或值错误"，但 `error` 参数类型已收缩为 `CompactStructureParseError`（`ValueError` 子类），不再接受 `TypeError`
- **影响**: 无运行时影响——类型注解已精确约束；docstring 措辞与类型签名存在轻微不一致
- **严重程度**: 不计入 finding；仅为可选的措辞精化，不阻塞 merge

## Open Questions

无。

## Residual Risk

- **`CompactStructureParseError.__init__` 类型守卫未覆盖**（lines 61–69）：5 行 missed 均为防御性 `isinstance`/`startswith`/`strip` 检查，仅在编程错误构造时触发。正常路径通过 typed call sites 保证合法输入。风险极低。
- **`_template_value` / `_schema_value` / `_prompt_field_rule` 的 descriptor 不完整 `RuntimeError` 分支仍未覆盖**：与 DS-02 相同，这些分支在模块级 immutable literal descriptor 下不可达，不是本 fix 引入的新 gap。
- **未运行真实 provider**：三项修复均为 deterministic parser/projection contract 变更，不依赖 provider 行为。

## 结论

**PASS。** 三项 accepted 裁决（MiMo-03、MiMo-04、MiMo-05/06）均已正确实施，无 scope creep，无回归，无新增类型错误或测试失败。rejected 裁决（MiMo-01、MiMo-02、MiMo-07、MiMo-08、DS-01、DS-02）未被不当修改。strict parser 的 typed failure ownership、fresh parser contract、rejected identity 同源证明、安全脱敏边界、bounded repair contract 均通过直接代码与测试证据验证。
