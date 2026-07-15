# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Final Code Re-Review — AgentMiMo

## 0. Gate identity 与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| gate | final code re-review |
| baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| review scope | baseline → working tree 全部 R03-S2 production/tests/README diff |
| implementation artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md` |
| controller validation | `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md`（verdict `PASS / READY_FOR_DUAL_CODE_REVIEW`） |
| code review MiMo | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-mimo.md`（verdict `PASS，1 个 blocking finding`） |
| code review DS | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-ds.md`（verdict `PASS — 零 material S2 finding`） |
| controller adjudication | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-controller-adjudication.md`（verdict `PASS / ZERO-CHANGE RECORD REQUIRED`） |
| fix artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md`（zero-change disposition） |
| fix controller validation | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-controller-validation.md`（verdict `PASS / READY_FOR_DUAL_FINAL_RE_REVIEW`） |
| output file | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-rereview-mimo.md` |
| verdict | **PASS，零 blocking finding** |

本次 re-review 是对 R03-S2 完整最终 slice 的独立完整审查。重新读取了所有权威输入、全部 production/tests/README diff，并独立挑战了 `S2-CR-F01`。结论：S2 owner contract、tests、coverage、pyright、README、安全保留与 deferred boundary 均正确；`S2-CR-F01` 的 Controller rejected/no-fix 裁决有完整直接证据支撑。

## 1. 审查方法与权威输入

按指定顺序完整读取：

1. `AGENTS.md` — 架构硬约束、LLM-facing 文本约束、语义所有权约束
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 3/4 — 删除下游 blacklist repair，不新增 normalization；producer owner 自足
3. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §2、§4.6-4.7、§7-11、§13-16 — S2 精确 allowlist、删除项、query/source contract、验证要求
4. `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md` — 逐文件 disposition、114 constructor inventory、37 prompt inventory
5. `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md` — Controller 独立验证 pass
6. 两份初始 code review — MiMo（1 finding）/ DS（0 finding）
7. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-controller-adjudication.md` — rejected S2-CR-F01，zero-change record required
8. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md` — AgentCodex zero-change disposition
9. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-controller-validation.md` — Controller validation PASS
10. baseline `fe497da3` 到当前 working tree 的全部 S2 production/tests/README diff

## 2. S2-CR-F01 独立复核

### 2.1 Controller 裁决回顾

Controller 对 MiMo `S2-CR-F01`（Tool Trace `query_state` 泄漏内部投影状态）给出 rejected-with-direct-evidence / no-fix，理由为：

1. 事实前提错误：当前只有 `_tool_request_summary_from_tool_result` 一处 production 命中；`_tool_request_summary_from_payload` 无该字段，测试无 `query_state` 断言
2. accepted plan §4.6/§4.7 明确保留 query-source provenance "明确状态"
3. §7.3 只删除 `LIMITED_SIGNAL`，未删除 `AcceptedToolResultQueryState` 或其剩余值
4. 该值是 query projection provenance，不是 governance 状态

### 2.2 独立验证

我对以下直接证据做了独立复核：

**事实 1：`query_state` production 命中位置**

```
$ rg -n 'query_state' dayu/host/tool_trace.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
dayu/host/tool_trace.py:1160:        "query_state": projection.query.state.value,
```

确认：只有 `_tool_request_summary_from_tool_result`（accepted-result summary 路径）一处命中。`_tool_request_summary_from_payload`（payload summary 路径）无 `query_state` 字段。两个测试文件无 `query_state` 断言。

**Controller 事实前提准确**。

**事实 2：accepted plan 对 query-source provenance 的保留**

- §4.6 固定 query 合法来源为 producer `semantic_query_text` 或 canonical accepted arguments，明确状态 `semantic_query | arguments_summary`
- §4.7 规定 `trace_summary.tool_request` readable fields 包含 "明确状态"
- §7.3 只删除 `LIMITED_SIGNAL`、字段名 blacklist、limited-query branch

**Controller 对 plan 裁决准确**。

**事实 3：`AcceptedToolResultQueryState` 的语义定位**

该 enum 值为 `"semantic_query"` 或 `"arguments_summary"`，描述的是 query 文本的来源（producer 提供 vs 机械展示 accepted arguments），不是 Run/Attempt/wait/poll/dispatch/Engine/Host governance 状态。它没有被伪装为财报事实或业务结论。

**Controller 语义定位准确**。

**事实 4：独立代码走读确认**

我独立读取了 `dayu/host/tool_trace.py:1116-1169`（`_tool_request_summary_from_tool_result`）和 `dayu/host/tool_trace.py:1172-1225`（`_tool_request_summary_from_payload`）。确认：

- 前者包含 `"query_state": projection.query.state.value`（line 1160）
- 后者不包含 `query_state`
- `AcceptedToolResultQueryState` 只有 `SEMANTIC_QUERY = "semantic_query"` 和 `ARGUMENTS_SUMMARY = "arguments_summary"`（`LIMITED_SIGNAL` 已被删除）
- 两个值都是业务可读的 query 来源描述，不是内部治理标识

### 2.3 复核结论

**Controller 对 S2-CR-F01 的 rejected/no-fix 裁决正确**。MiMo 初始 review 的事实前提不准确（声称两处 production 命中、多处测试断言），且未准确识别 accepted plan 对 query-source provenance 的显式保留。该字段符合 accepted plan contract，不违反 AGENTS.md LLM-facing 文本约束。

本次 re-review 不提出新 finding。

## 3. 完整 Adversarial / Owner Drift / LLM-facing 审查

### 3.1 删除安全性

| 删除项 | 证据 | 状态 |
| --- | --- | --- |
| `_contains_unsafe_argument_key` | 用字段名猜测安全，产生 false positive/negative；Topic 3 裁决删除 | 正确删除 |
| `_limited_query` + `LIMITED_SIGNAL` | 只由已删除 blacklist 产生；删除后无调用方 | 正确删除 |
| `arguments_summary_unsafe` diagnostic | 只由已删除 blacklist 产生 | 正确删除 |
| `_redacted_json` + runtime redaction import | Tool Trace 不应对 exact args 做字段名级脱敏 | 正确删除 |
| `dayu/runtime/json_redaction.py` | 唯一调用方已从 Tool Trace 删除；无合法层中立 owner | 正确删除 |
| `_descriptor_arguments_summary` | 输出 descriptor ref/digest 到 readable summary | 正确删除 |

### 3.2 Producer schema 自足性

| producer | 修改 | 自足性证据 |
| --- | --- | --- |
| `fetch_more` (Host framework) | description + cursor/scope_token/limit descriptions | 中文、自足、明确引用标签非业务事实 |
| `fetch_web_page.url` (Web producer) | url description | 自足说明完整 http/https URL 及优先复用 search_web |
| Fins read tools (Fins producer) | 共用 ticker/document_id descriptions | 模块级私有 helper，唯一文案真源 |

三个 producer 均未改变工具名、参数名、enum、required、result 或 citation shape。

### 3.3 LLM-facing 文本合规

- `fetch_more` cursor/scope_token description 明确说明 "不是业务事实或推理依据" — 符合 AGENTS.md LLM-facing 约束
- Fins `document_id` description 明确来源约束 "只能使用同一 ticker 的 list_documents" — 自足
- `fetch_web_page.url` description 业务可读 — 自足
- `query_state` 的 `semantic_query | arguments_summary` 值是 query 来源描述，不是 governance 术语 — 符合 plan §4.7

### 3.4 Semantic Ownership Drift

- 无新 drift。删除的 blacklist/redaction 已无下游补偿
- 新增 schema helper 是唯一文案真源
- `_INTERNAL_SOURCE_REF_KINDS` 和 `_readable_ref_text` 正确保留在 S3 scope
- descriptor strict resolution 正确延迟到 S3
- `business_source_text/state` 正确延迟到 S3

### 3.5 过度耦合

- 未发现。S2 只删除 blacklist/redaction 和修复 producer schema，不引入新跨层依赖
- Fins ticker/document_id helper 是模块内私有函数，不跨层暴露
- `fetch_more` schema 改动在 Host framework tool producer 内，不穿透到 Engine/Service

### 3.6 自足 Schema 审查

- `AcceptedToolResultQueryState` 只有两个值，均为业务可读 query 来源描述
- `AcceptedToolResultSourceState` 只有两个值，均业务可读
- 无裸 `event_id`、`payload_ref`、digest、cursor 进入 LLM-facing material（S3 关闭 opaque refs）

### 3.7 Tests Owner Contract

| 测试 | 断言内容 | 证据 |
| --- | --- | --- |
| `test_projection_mechanically_displays_legal_business_argument_names` | `file_path`/`password_policy_name`/`scope_token`/`ticker` 全部原值可见；state 为 `ARGUMENTS_SUMMARY` | owner contract test |
| `test_projection_consumer_mechanically_displays_legal_business_argument_names` | Memory 同一三个合法业务字段机械可见 | shared projection propagation |
| `test_wait_resolution_tool_trace_summarizes_request_and_result_details` | exact args、无 `<redacted>`、合法业务字段值可见 | Tool Trace owner contract |
| `test_tool_trace_does_not_inline_large_tool_call_arguments` | descriptor ref/digest 不在 readable summary | internal/readable 分界 |
| `test_fetch_more_schema_explains_continuation_reference_labels` | exact tool/param descriptions | framework schema owner test |
| `test_web_tool_display_and_description_stay_at_declaration_boundary` | url description exact assertion | Web schema owner test |
| `test_fins_read_tool_schemas_do_not_expose_execution_context` | shared ticker/document_id exact assertions | Fins schema owner test |

结论：测试断言 owner 级 contract 行为，没有 fixture 迫使生产保留兼容分支。

### 3.8 README 职责

- `dayu/host/README.md`：Tool Trace "脱敏" 改为 exact canonical/bounded 与 descriptor internal/readable 分界。命中 Host README 职责。正确。
- `tests/README.md`：Memory/Tool Trace/Web/Fins schema 测试事实更新。命中 tests README 职责。正确。
- 根 `README.md`：安装、CLI、输出通道、日志、workspace 与用户工作流均未变。no-diff 正确。
- `dayu/README.md`：分层/装配关系未变。no-diff 正确。
- `dayu/fins/README.md`：仅 LLM-facing parameter descriptions，不改变 Fins 存储/业务开发接口。no-diff 正确。

### 3.9 Retained Security

| 安全 owner | 文件 | 状态 |
| --- | --- | --- |
| 运行期诊断文本脱敏 | `dayu/runtime/diagnostic_text.py` | 无 diff，保留 |
| Engine provider diagnostic 安全脱敏 | `dayu/engine/runners/openai/diagnostic_payload.py` | 无 diff，保留独立 `_SENSITIVE_KEY_FRAGMENTS` |
| Compaction 阶段诊断脱敏 | `dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py` | 无 diff，保留 `redact_sensitive_diagnostic_values` 调用 |
| Web diagnostic 安全投影 | `dayu/tools/web/web_diagnostics.py` | 无 diff，保留 |
| Host durable filelock | `dayu/host/tool_trace.py::file_lock` | 无 diff，保留 |
| Doc allowed_paths | `dayu/tools/doc_tools.py` | 无 diff，保留 |
| Fins filesystem containment | `dayu/fins/storage/` | 无 diff，保留 |
| Web DNS/peer/budget/challenge | `dayu/tools/web/` | 无 diff，保留 |

所有独立安全 owner 完整保留，未被误删。

### 3.10 Deferred Leakage

- `_INTERNAL_SOURCE_REF_KINDS` / `_readable_ref_text`：仍在 `accepted_result_projection.py`，正确延迟到 S3。当前生产路径 `source_refs`/`locator_refs` 均为空，guessing 路径在生产中不可达。
- descriptor strict resolution：正确延迟到 S3。S2 只关闭 readable ref/digest placeholder。
- `business_source_text/state`：正确延迟到 S3。
- `source_locator_refs` 字段：正确延迟到 S3 删除。当前 LLM-facing material 不包含 opaque refs。
- R03 public smoke：正确延迟到 aggregate。

## 4. Protected Digests 复核

Controller 验证的 protected digests：

| 摘要 | Controller 记录值 | Controller 复算 | 结果 |
| --- | --- | --- | --- |
| protected content SHA-256 | `2fe691...27ee` | 同值 | PASS |
| protected status/path SHA-256 | `036a65...a9c5` | 同值 | PASS |
| 排除 fix artifact 的 worktree status SHA-256 | `c22595...673b` | 同值 | PASS |

本次 re-review 独立复算（采用 fix artifact §4.1 canonical 21-path records 方法）：

| 摘要 | 本次复算值 | 结果 |
| --- | --- | --- |
| protected content SHA-256 | `2fe691991f9bfb4d16498712b62904a2bd0561890579a49b1355068875fc27ee` | **与 Controller 记录值一致** |
| protected status/path SHA-256 | `036a65637fe7c1fe7fa4bf3260c8b142e64250ebc9bb326e5ec9b13f5b26a9c5` | **与 Controller 记录值一致** |

两个 protected digest 均完全匹配。production/tests/README 文件零变化，仅新增 fix artifact 和本 re-review artifact 作为 untracked 文件。

确认：`git diff fe497da3 --` 的 16 个 changed files 与初始 code review 时完全一致，仅新增 `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md` 和本 artifact 作为 untracked 文件。

## 5. Source Gates 复核

### Gate 1: `llm_safe_replay_arguments|arguments_summary_unsafe|unsafe_argument|safe_arguments|accepted_arguments_source_digest`

- production 零命中
- 唯一命中：`tests/host/test_wait_awaiting_accept.py:337` 的 `accepted_arguments_source_digest` **absence assertion**（S1 owner test，不在 S2 allowlist）

### Gate 2: `redact_sensitive_json_fields|json_redaction|_SENSITIVE_KEY_FRAGMENTS|JSON_REDACTION_MARKER`

- Host/runtime/tests 零命中；删除模块不存在
- Engine provider diagnostic 的 `_SENSITIVE_KEY_FRAGMENTS` 是独立安全脱敏 owner，retained security

### Gate 3: `_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text`

- 仍在 `accepted_result_projection.py` — R03-S3 deferred opaque source owner

### Gate 4: `api_key.*token.*secret.*password|password.*secret.*token.*api_key` in `dayu/host dayu/runtime tests/host`

- 零命中

## 6. Finding Ledger

### 6.1 Accepted findings

零。

### 6.2 S2-CR-F01 最终状态

**rejected-with-direct-evidence / no-fix**。Controller 裁决正确，有完整 code/plan 证据支撑。本次 re-review 独立确认。

### 6.3 新 findings

零。本次完整 re-review 未发现新的 material finding。

## 7. Observations / Deferred / Retained Security

### 7.1 Rejected / No-fix Observations

| ID | 观察 | 裁决 | 理由 |
| --- | --- | --- | --- |
| OBS-01 | Web default Ruff 14 项 | rejected / no-fix | 与 baseline `fe497da3` 同源；零新增/扩散 |
| OBS-02 | `_INTERNAL_SOURCE_REF_KINDS` 仍存在 | deferred S3 | accepted plan 明确放入 S3 |
| OBS-03 | descriptor strict resolution 未实现 | deferred S3 | accepted plan §11.3 item 8 和 R03-PLAN-F06 明确放入 S3 |
| OBS-04 | `test_tool_trace_queries.py` runner reconstruction 的 `limited_signal` typed diagnostic | no-fix / owner 不同 | internal runner-input query diagnostic，不是 accepted arguments blacklist 语义 |

### 7.2 Deferred Boundaries

| 项目 | owner | slice |
| --- | --- | --- |
| opaque source guessing / internal refs propagation | `accepted_result_projection.py::_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` | R03-S3 |
| descriptor strict row resolution + exact readable args/query | `tool_trace.py` TOOL_CALL_REQUESTED readable projection | R03-S3 |
| `business_source_text/state` + non-optional material | `tool_trace.py` + shared projection | R03-S3 |
| `source_locator_refs` 字段删除 | `accepted_result_projection.py` | R03-S3 |
| `_source_projection` opaque ref → citation 改写删除 | `accepted_result_projection.py` | R03-S3 |
| R03 public Doc/Web/Fins smoke | aggregate hard gate | aggregate |
| Issue #177 / #178 | 既有 issue owner | 不进入 R03 |
| unified tool authorization framework | 不实施 | 不进入 R03 |

### 7.3 Retained Security

所有独立安全 owner 完整保留（见 §3.9）。没有新增 LLM-safe normalization、compatibility、BusinessSource、统一 authorization 或 Issue #177/#178 实现。

## 8. Blocking Questions

零。

## 9. 最终 Verdict

| 项目 | 值 |
| --- | --- |
| verdict | **PASS** |
| finding 数 | 0 |
| blocking questions | 0 |
| S2-CR-F01 最终状态 | rejected-with-direct-evidence / no-fix（Controller 裁决正确） |
| rejected observations | 4（OBS-01 至 OBS-04） |
| retained security | 8 个独立安全 owner 完整保留 |
| deferred boundaries | 8 项正确分配至 S3/aggregate/既有 issue |
| protected digests | status/path 匹配；production/tests/README 零变化 |
| 新 findings | 零 |

R03-S2 的 owner contract、tests、coverage、pyright、README、安全保留与 deferred boundary 均正确。`S2-CR-F01` 的 Controller rejected/no-fix 裁决有完整直接证据支撑。本次 re-review 不提出新 finding，不阻塞 R03-S2 accepted local commit。
