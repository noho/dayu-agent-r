# PR 190 F11/F12 MiMo Re-review (Post-fix)

## Gate

- Review base: `9fa3ff799506e66f995b4156dbb960c98c2f737e`
- Review scope: uncommitted workspace fix diff (5 files, +319/-76)
- Adjudication: `docs/reviews/pr-190-f11-f12-pr-review-adjudication-20260806.md`
- Fix artifact: `docs/reviews/pr-190-f11-f12-pr-review-fix-20260806.md`
- Previous MiMo review: `docs/reviews/pr-190-f11-f12-pr-mimo-review-20260806.md`
- Re-review date: 2026-08-06

## Scope

- Mode: Current Changes Mode (uncommitted fix relative to exact base)
- Included: `dayu/host/compact_structure.py`, `dayu/host/llm_compaction.py`, `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_tool_trace_analysis_rules.py`
- Excluded: prompts, JSON schema, Host acceptance, Memory, Engine, design, README, oracle/scenario registry, immutable evidence, prior review artifacts
- Parallel review coverage: 无

## 逐项复核：Controller Adjudication Verification

### MiMo-01 — force-answer 应移除 structured output

**Adjudication: rejected. Re-review: rejected 持平。**

本次 fix 未触及 `_AsyncAgent`、Engine runner 或 structured_output 传递路径。代码证据不变：`agent.py:1345` 原样透传 `structured_output`，当前配置不会触发。不修改生产代码。

### MiMo-02 — malformed compactor terminal 不应令 Tool Trace fail closed

**Adjudication: rejected. Re-review: rejected 持平。**

本次 fix 未触及 `tool_trace.py` 或 `tool_trace_analysis_input.py`。fail-closed 设计仍为 F11 acceptance 要求。

### MiMo-03 — rejected attempt 的 successful response identity 缺 analysis owner test

**Adjudication: accepted. Re-review: PASS — fix 正确实施。**

新增 `test_rejected_compactor_response_identity_projects_from_typed_owner_to_all_outputs`（`test_tool_trace_analysis_rules.py:1566-1670`）：

- 从 `_compactor_projection(record)` 取得 `accepted_response`，提取 `successful_response_identity`；
- `replace` disposition 为 `ATTEMPT_REJECTED`，保留同一 `successful_response_identity`；
- 邻近 `source_event_payload` 刻意写入冲突 `configured_provider`、`configured_model`、`provider_request_id`（poison values）；
- 断言 typed summary 的 `effective_provider`、`effective_model`、`runner_request_identity`、`provider_request_id_availability`、`provider_request_id` 全部等于 `successful_response_identity` 对应字段；
- 断言 JSON serialization 中 `disposition == "attempt_rejected"` 且 identity 字段等于 successful；
- 断言 Markdown 输出包含所有 successful identity 字段值；
- 断言 `rendered` 不包含任何 poison value。

**直接证据**：测试证明 analysis owner 从 resolver 的 typed `successful_response_identity` 投影，不从 config 或邻近 event 推断。typed/JSON/Markdown 三态同源。

### MiMo-04 — parser 的 request 参数没有语义作用

**Adjudication: accepted. Re-review: PASS — fix 正确实施。**

- `parse_conversation_compact_output_vnext` 签名从 `(request: CompactInputV3, final_answer: str)` 改为 `(final_answer: str)`（`llm_compaction.py:797-798`）；
- 函数体移除 `isinstance(request, CompactInputV3)` 类型检查，直接调用 `parse_compact_candidate_v3(final_answer)`；
- 生产调用方 `LLMContextCompactor.run_prepared_compactor_proposal`（`llm_compaction.py:374`）同步迁移为只传 `outcome.content`；
- 所有直接测试（`test_llm_compaction.py`）同步移除 `_compact_input()` 参数；
- `_compact_input()` helper 仅被 `_user_prompt_vnext` 相关测试使用，不再出现在 parser 测试路径；
- 未保留旧签名 wrapper、alias、兼容分支或旧签名测试。

### MiMo-05 / MiMo-06 — repair code/path 从异常字符串反推

**Adjudication: accepted and combined. Re-review: PASS — fix 正确实施。**

**compact_structure.py 侧**：

- 新增 `CompactStructureParseError(ValueError)`（`compact_structure.py:35-73`），携带 typed 字段：
  - `code: CompactValidationIssueCodeV3`
  - `json_path: str`（以 `$` 开头，构造函数校验）
  - `message: str`（非空，构造函数校验）
- 所有 `raise ValueError(...)` 替换为 `raise CompactStructureParseError(code=..., json_path=..., message=...)`；
- `code` 由 `CompactValidationIssueCodeV3` enum 成员直接赋值，不从字符串前缀解析；
- `json_path` 由 parser 在校验点直接构造（如 `$.forward_intents[0].status`），不从 message 文本提取；
- `CompactStructureParseError` 进入 `__all__`（`compact_structure.py:800`）。

**llm_compaction.py 侧**：

- `_structure_validation_report` 参数类型从 `TypeError | ValueError` 改为 `CompactStructureParseError`（`llm_compaction.py:817-832`）；
- 函数体删除 `code_by_prefix` dict、`message.partition(":")[0]` 前缀解析、`_structure_error_path` 函数；
- 直接读取 `error.code`、`_safe_outcome_text(error.json_path)`、`_safe_outcome_text(error.message)`；
- `CompactValidationIssueCodeV3` 从 `llm_compaction.py` import 中移除（`llm_compaction.py:60` diff 删除行）；
- `_structure_error_path` 完全删除，grep 确认无残留。

**直接证据**：`_structure_validation_report` 不做任何字符串推断。code 来自 typed enum field，path 来自 typed field，message 来自 typed field。脱敏（`_safe_outcome_text`）仅应用于 json_path 和 message 的显示文本，不影响 code 或 path 语义。

### MiMo-07 — bounded repair feedback 可能在单 issue、零 labels 时抛 RuntimeError

**Adjudication: rejected as unreachable. Re-review: rejected 持平。**

本次 fix 未触及 `context_governance.py::build_compact_repair_feedback_v3`。controller 裁决的不可达性论证仍成立。

### MiMo-08 — runtime / Engine structured-output enums 缺同步守护

**Adjudication: rejected as evidence-invalid. Re-review: rejected 持平。**

本次 fix 未触及 runtime 或 Engine enum。现有 owner test `test_structured_output_capability_enums_map_mechanically_by_value` 仍守护。

### DS-01 — aggregate coverage 声称 90%，单 suite 实测 85%

**Adjudication: rejected. Re-review: rejected 持平。**

本次 fix 不改变 measurement 口径。实测 `compact_structure.py` 为 223 statements、25 missed、88.79%（终端显示 89%），通过 `>=80%` 门槛。

### DS-02 — immutable descriptor defensive branches 未覆盖

**Adjudication: rejected. Re-review: rejected 持平。**

本次 fix 未改变 descriptor 构造路径。`CompactStructureParseError` 构造函数中的 `TypeError`/`ValueError` 守卫（`compact_structure.py:60-69`）对应 DS-02 裁决的"模块内部 immutable literal 被错误构造时 fail fast"分支，外部不可注入。

## 五项重点审查

### 1. Typed parse failure 由 compact_structure owner 直接提供 code/path/message

**PASS。**

`CompactStructureParseError.__init__` 要求 `code: CompactValidationIssueCodeV3`、`json_path: str`（`$` 开头）、`message: str`（非空）。所有 parser rejection 分支直接构造 typed instance，不编码字符串。`llm_compaction.py::_structure_validation_report` 直接读取 typed fields，不解析字符串。

### 2. parse_conversation_compact_output_vnext fresh signature

**PASS。**

签名 `(final_answer: str) -> CompactCandidateV3`，无 wrapper/alias/兼容分支。`request`/`source`/`cap` acceptance 仍在 `context_governance.py::accept_compact_candidate_v3`（Context Governance owner）。

### 3. rejected + successful identity test 证明 typed/JSON/Markdown 同源

**PASS。**

测试构造 `ATTEMPT_REJECTED` disposition 但保留 `successful_response_identity`，注入 poison values 到邻近 payload。断言 typed summary、JSON serialization、Markdown 输出均来自 resolver 的 typed identity，不含 poison values。证明 analysis owner 不从邻近数据推断。

### 4. strict parser、安全脱敏、bounded repair、prompt/schema/Host acceptance/Engine semantics 无漂移

**PASS。**

- strict parser：`parse_compact_candidate_v3` 行为不变，只是异常类型从 `ValueError` 改为 `CompactStructureParseError`；
- 安全脱敏：`_safe_outcome_text` 对 `json_path` 和 `message` 应用 `redact_sensitive_diagnostic_values` + 240 字符截断；
- bounded repair：`build_compact_repair_feedback_v3` 未改动；
- prompt/schema/Host acceptance/Engine semantics：未触及。

### 5. 中文 docstring、严格类型、无 Any/object、allowed scope 和测试

**PASS。**

- `CompactStructureParseError` 及其 `__init__` 提供完整中文 docstring，含参数、返回值、异常说明；
- 所有修改函数的 docstring 更新了 `:raises` 说明（`ValueError` → `CompactStructureParseError`）；
- 无 `Any`、`object` 类型使用；
- pyright 全仓 `0 errors, 0 warnings, 0 informations`；
- ruff `All checks passed!`；
- 测试覆盖 88.79%，超过 80% 门槛。

## Findings

未发现实质性问题。

## Validation

| Check | Result |
|-------|--------|
| `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_tool_trace_analysis_rules.py` | 72 passed |
| `pytest ... --cov=dayu.host.compact_structure --cov-fail-under=80` | 88.79% (223 stmts, 25 missed) |
| `python -m pyright dayu/ tests/` | 0 errors, 0 warnings, 0 informations |
| `ruff check` (5 changed files) | All checks passed! |
| `git diff --check` | PASS |

## Open Questions

无。

## Residual Risk

- `CompactStructureParseError` 构造函数的 `TypeError`/`ValueError` 守卫（`compact_structure.py:60-69`）为模块内部 fail-fast 分支，外部不可达，与 DS-02 裁决一致，无需覆盖。
- Engine structured output 集成层面的端到端测试（MiMo-01 finding 1 的 residual）不在本 fix scope。

## Conclusion

**PASS。** 三项 accepted fix（MiMo-03、MiMo-04、MiMo-05/06）均已正确实施，未引入新缺陷。八项 rejected findings 持平，未被新证据推翻。生产代码、测试、pyright、ruff 全部通过。
