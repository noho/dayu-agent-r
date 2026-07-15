# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Code Review — AgentMiMo

## 0. Gate identity 与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| review scope | baseline → working tree 全部 R03-S2 production/tests/README diff |
| implementation artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md` |
| controller validation | `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md`（verdict `PASS / READY_FOR_DUAL_CODE_REVIEW`） |
| output file | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-mimo.md` |
| verdict | **PASS，1 个 blocking finding** |

R03-S2 的动机与 owner boundary 成立：下游字段名 blacklist 和 readable redaction 的删除正确，没有新增 replacement normalization；三个 producer schema 缺口在各自 owner 修复；Engine provider diagnostic 安全脱敏 owner 保留完整。发现 1 个 semantic ownership drift 需要修复。

## 1. 审查依据

按指定优先级完整读取：

1. `AGENTS.md` — 架构硬约束、LLM-facing 文本约束、语义所有权约束
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 3/4 权威裁决：删除下游 blacklist repair，不新增 normalization；producer owner 自足
3. design truths（`docs/host/design.md` 等）— Host Tool Trace 投影边界、opaque ref 内部保留
4. accepted plan §7-10, §11, §13-16 — S2 精确 allowlist、删除项、验证要求
5. plan fix `R03-PLAN-F06/F07` — descriptor ref/digest 不进入 readable summary；runtime docstring only change
6. implementation artifact — 逐文件 disposition、114 constructor inventory、37 prompt inventory
7. controller validation — 独立验证 pass
8. `git diff fe497da3` — 全部 16 changed files

## 2. Findings

### S2-CR-F01-未修复-中-tool_trace-query-state-泄漏内部投影状态

- **入口/函数**: `dayu/host/tool_trace.py::_tool_request_summary_from_tool_result`、`dayu/host/tool_trace.py::_tool_request_summary_from_payload`
- **文件(行号)**: `dayu/host/tool_trace.py`（readable summary dict 中的 `"query_state"` 字段）
- **输入场景**: 任何 Tool Trace readable summary 构造
- **实际分支**: `_tool_request_summary_from_tool_result` 和 `_tool_request_summary_from_payload` 均在 readable summary dict 中输出 `"query_state": projection.query.state.value`
- **预期行为**: 按 `AGENTS.md` LLM-facing 文本约束，readable summary 不得暴露内部治理标识、系统状态或 Host/Engine 实现术语；`AcceptedToolResultQueryState` 是 Host 内部投影状态枚举（`semantic_query` / `arguments_summary`），不是业务事实
- **实际行为**: `query_state` 字段以 `"semantic_query"` 或 `"arguments_summary"` 值进入 Tool Trace readable summary，该 summary 直接进入 LLM 上下文（cold JSONL 和 hot row 的 `trace_summary`）
- **直接证据**: `dayu/host/tool_trace.py` 的 `_tool_request_summary_from_tool_result` 返回 dict 包含 `"query_state": projection.query.state.value`；`_tool_request_summary_from_payload` 同样包含此字段；`tests/host/test_tool_trace_projection.py` 多处断言 `request_summary["query_state"]` 存在
- **影响**: LLM 可见内部投影状态枚举值，违反 LLM-facing 文本约束中"不得把系统状态、调度状态、Host / Engine 内部治理信息伪装成财报事实、业务事实或用户可见结论"的要求
- **建议改法和验证点**: 从两个 `_tool_request_summary_*` 函数的返回 dict 中删除 `"query_state"` 字段；更新 `tests/host/test_tool_trace_projection.py` 中所有 `request_summary["query_state"]` 断言为 absence assertion；内部 diagnostic 如需此信息可保留在 hot row 的 internal fields，不进入 readable summary
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 中 — 不影响功能正确性，但违反 LLM-facing 文本约束的语义所有权规则

## 3. Adversarial Failure Pass 结果

### 3.1 删除安全性

- `_contains_unsafe_argument_key` 删除：正确。该函数用字段名猜测安全性，会产生 false positive（`file_path`、`scope_token`、`password_policy_name` 被误杀）和 false negative（`credential`、`cookie`、`auth` 未覆盖）。按 Topic 3 裁决，正确动作是删除，不是扩充。
- `_redacted_json` 删除：正确。Tool Trace readable 不应对 exact args 做字段名级脱敏。
- `dayu.runtime.json_redaction` 删除：正确。唯一调用方已从 Tool Trace 删除；`dayu/runtime/diagnostic_text.py::redact_sensitive_diagnostic_values`（运行期诊断文本脱敏）和 `dayu/engine/runners/openai/diagnostic_payload.py::_SENSITIVE_KEY_FRAGMENTS`（Engine provider diagnostic 安全脱敏）均保留且无 diff。
- `_descriptor_arguments_summary` 删除：正确。该函数输出 descriptor ref/digest 到 readable summary，按 plan §11.3 item 8 和 `R03-PLAN-F06` 应删除。descriptor strict row resolution 属 S3。
- `LIMITED_SIGNAL` enum 值删除：正确。该状态只由已删除的 `_limited_query` 产生，删除后无调用方。

### 3.2 Producer schema 自足性

- `fetch_more` tool/parameter descriptions：中文、自足、明确 cursor/scope_token 为引用标签而非业务事实。符合 LLM-facing 文本约束。
- `fetch_web_page.url` description：自足说明完整 http/https URL 及优先复用 search_web 结果。
- Fins `ticker` / `document_id` descriptions：模块级私有 helper，九个 ticker 共用、八个 document_id 共用；自足说明业务约束。符合编码硬约束"优先使用模块级私有辅助函数"。
- 三个 producer schema 均未改变工具名、参数名、enum、required、result 或 citation shape。

### 3.3 安全保留

- `dayu/runtime/diagnostic_text.py::redact_sensitive_diagnostic_values`：无 diff，保留运行期诊断文本脱敏
- `dayu/engine/runners/openai/diagnostic_payload.py::_SENSITIVE_KEY_FRAGMENTS`：无 diff，保留 Engine provider diagnostic 独立安全脱敏 owner
- `dayu/host/llm_compaction.py` 和 `dayu/host/compaction_operation.py` 中的 `redact_sensitive_diagnostic_values` 调用：无 diff，保留 compaction 阶段的诊断脱敏
- 结论：Engine provider diagnostic 的独立安全脱敏 owner 完整保留，未被误删

### 3.4 Semantic Ownership Drift

- `query_state` 字段（S2-CR-F01）：已记录为 blocking finding
- 其它 drift：未发现。accepted-result projection 的 opaque source kind/filter（`_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text`）按 plan 正确保留在 S3 scope，未在 S2 越界删除

### 3.5 过度耦合

- 未发现。S2 只删除 blacklist/redaction 和修复 producer schema，不引入新的跨层依赖
- Fins ticker/document_id helper 是模块内私有函数，不跨层暴露
- `fetch_more` schema 改动在 Host framework tool producer 内，不穿透到 Engine/Service

### 3.6 测试 Owner Contract

- `test_projection_mechanically_displays_legal_business_argument_names`：正确断言合法业务字段（`file_path`、`password_policy_name`、`scope_token`）的 canonical JSON 可见性；不再断言 blacklist 行为
- `test_projection_consumer_mechanically_displays_legal_business_argument_names`：Memory 投影断言同一三个合法业务字段机械可见
- `test_wait_resolution_tool_trace_summarizes_request_and_result_details`：Tool Trace 断言 exact args、无 `<redacted>`、合法业务字段值可见
- `test_tool_trace_does_not_inline_large_tool_call_arguments`：断言 descriptor ref/digest 不进入 readable summary，normalized digest 仍在 internal row
- `test_fetch_more_schema_explains_continuation_reference_labels`：断言 tool/parameter descriptions 的 exact contract
- `test_web_tool_display_and_description_stay_at_declaration_boundary`：断言 `url` description
- `test_fins_read_tool_schemas_do_not_expose_execution_context`：断言 shared ticker/document_id schema
- 结论：测试断言 owner 级 contract 行为，没有 fixture 迫使生产保留兼容分支

## 4. Rejected / No-fix Observations

| ID | 观察 | 裁决 | 理由 |
| --- | --- | --- | --- |
| OBS-01 | Web default Ruff 14 项 | rejected / no-fix | Controller 已证明与 baseline `fe497da3` 同源；本 diff 仅因 URL schema 插入四行导致行号平移，零新增/扩散。用户禁止借 schema-only S2 修改无关代码 |
| OBS-02 | `_INTERNAL_SOURCE_REF_KINDS` 仍存在于 `accepted_result_projection.py` | no-fix / deferred S3 | accepted plan 明确把 opaque source owner 放在 S3；S2 不越界删除 |
| OBS-03 | descriptor strict row resolution 未实现 | no-fix / deferred S3 | accepted plan §11.3 item 8 和 `R03-PLAN-F06` 明确放在 S3；S2 只关闭 readable ref/digest placeholder |
| OBS-04 | `query_state` 在 `test_tool_trace_queries.py` 的 runner reconstruction 路径 | no-fix / owner 不同 | runner reconstruction 的 `limited_signal` typed diagnostic 是独立的 internal query diagnostic，不是 accepted arguments blacklist 语义 |

## 5. Retained Security

| 安全 owner | 文件 | 状态 |
| --- | --- | --- |
| 运行期诊断文本脱敏 | `dayu/runtime/diagnostic_text.py` | 无 diff，保留 |
| Engine provider diagnostic 安全脱敏 | `dayu/engine/runners/openai/diagnostic_payload.py` | 无 diff，保留独立 `_SENSITIVE_KEY_FRAGMENTS` |
| Compaction 阶段诊断脱敏 | `dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py` | 无 diff，保留 `redact_sensitive_diagnostic_values` 调用 |
| Web diagnostic 安全投影 | `dayu/tools/web/web_diagnostics.py` | 无 diff，保留 |
| Host durable filelock | `dayu/host/tool_trace.py::file_lock` | 无 diff，保留 |

## 6. Deferred Boundaries

| 项目 | owner | slice |
| --- | --- | --- |
| opaque source guessing / internal refs propagation | `accepted_result_projection.py::_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` | R03-S3 |
| descriptor strict row resolution + exact readable args/query | `tool_trace.py` TOOL_CALL_REQUESTED readable projection | R03-S3 |
| R03 public Doc/Web/Fins smoke | aggregate hard gate | aggregate |
| Issue #177 / #178 | 既有 issue owner | 不进入 R03 |
| unified tool authorization framework | 不实施 | 不进入 R03 |

## 7. 验证命令

以下关键命令可独立复跑：

```bash
source .venv/bin/activate

# S2 精确测试矩阵
pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_toolruntime_truncation_fetch_more.py \
  tests/tools/web/test_web_tools_provider.py \
  tests/fins/test_fins_storage_provider.py -q
# 预期：519 passed, 1 skipped, 3 warnings

# no-diff 回归
pytest \
  tests/tools/test_doc_tools_provider.py \
  tests/tools/test_combined_tools_acceptance.py \
  tests/runtime/test_import_boundary.py \
  tests/runtime/test_scene_assets_migration.py \
  tests/engine/runners/openai/test_payload_build.py \
  tests/engine/test_agent_phase3_tool_call.py -q
# 预期：171 passed, 3 warnings

# pyright
python -m pyright dayu/ tests/ utils/
# 预期：0 errors

# source gates
grep -rn 'llm_safe_replay_arguments\|arguments_summary_unsafe\|unsafe_argument\|safe_arguments\|accepted_arguments_source_digest' dayu/host dayu/runtime tests/host --include='*.py'
# 预期：零命中（除 S1 absence assertion）

grep -rn 'redact_sensitive_json_fields\|json_redaction\|_SENSITIVE_KEY_FRAGMENTS\|JSON_REDACTION_MARKER' dayu/host dayu/runtime tests/host --include='*.py'
# 预期：零命中
```

## 8. README 职责

- `dayu/host/README.md`：Tool Trace "脱敏"改为 exact canonical/bounded 与 descriptor internal/readable 分界。命中 Host README 职责。正确。
- `tests/README.md`：Memory/Tool Trace/Web/Fins schema 测试事实更新。命中 tests README 职责。正确。
- 根 `README.md`：安装、CLI、输出通道、日志、workspace 与用户工作流均未变。no-diff 正确。
- `dayu/README.md`：分层/装配关系未变。no-diff 正确。
- `dayu/fins/README.md`：仅 LLM-facing parameter descriptions，不改变 Fins 存储/业务开发接口。no-diff 正确。

## 9. 最终裁决

| 项目 | 值 |
| --- | --- |
| verdict | **PASS**，1 个 blocking finding（S2-CR-F01） |
| finding 数 | 1 |
| blocking questions | 无 |
| rejected observations | 4（OBS-01 至 OBS-04） |
| retained security | 5 个独立安全 owner 完整保留 |
| deferred boundaries | 5 项正确分配至 S3/aggregate/既有 issue |

S2-CR-F01（`query_state` 泄漏内部投影状态）是唯一的 blocking finding。修复风险低：从两个 `_tool_request_summary_*` 函数返回 dict 中删除 `"query_state"` 字段，更新对应测试断言为 absence assertion。修复后需完整 re-review。
