# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Final Code Re-Review — AgentDS

## 0. Gate 身份与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| gate | dual final code re-review (第二路) |
| baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| review scope | baseline → working tree 全部 R03-S2 production/tests/README diff + 既有 review/fix/controller artifacts |
| prior artifacts read | implementation codex、controller validation、MiMo/DS 初始 code review、controller adjudication、fix codex、fix controller validation、accepted plan、overdesign controller discussion Topic 3/4 |
| AgentDS verdict | **PASS — 零 material S2 finding** |
| finding 数 | 0 |
| blocking questions | 0 |

本 re-review 是 R03-S2 第二路完整 final code re-review，不是基于旧结论的 delta review。已独立重新走读全部 production diff、全部 test diff、全部 README diff、以及 baseline 到当前 working tree 的完整变更集。确认 R03-S2 的 owner contract、测试、retained security 与 deferred boundary 均符合 accepted plan。

## 1. 独立复核方法

1. **full diff walk**：`git diff HEAD -- '*.py' '*.md'` 全部 16 changed + 1 deleted files，逐文件比对 plan §7.2 allowlist
2. **production call-path trace**：`accepted_result_projection.py` 的 `_query_projection` → `_source_projection` → `_llm_material`；`tool_trace.py` 的 `_tool_request_summary_from_payload` → `_tool_request_summary_from_tool_result` → `_tool_result_summary_from_projection`
3. **adversarial failure pass**：空 semantic query、descriptor args、合法业务字段（`file_path`/`password_policy_name`/`scope_token`）、corrupted payload
4. **semantic ownership drift pass**：逐项确认被删代码无下游补偿、新增 schema helper 是唯一文案真源、LLM-facing material 不携带内部 ref/digest
5. **LLM-facing text audit**：逐文件检查 fetch_more / Web URL / Fins read tool descriptions 的自足性与 LLM-facing 约束合规
6. **source gate 独立执行**：四项 grep gate 全部执行并逐命中归属
7. **protected digest 独立复核**：content aggregate 复算匹配 `2fe691...27ee`；Controller 已独立复现 status/path aggregate `036a6563...a9c5`

## 2. S2-CR-F01 独立复核 — no-fix 确认

### 2.1 直接代码证据

对 `query_state` 执行全仓精确搜索：

```bash
rg -n 'query_state' dayu/host/tool_trace.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

结果：**仅一处 production 命中**：`dayu/host/tool_trace.py:1160` 的 `_tool_request_summary_from_tool_result`。该函数从 `AcceptedToolResultProjection` 的共享投影构造 Tool Trace readable request summary。

**`_tool_request_summary_from_payload`（line 1172-1225）不包含 `query_state`。**该函数的返回 dict 有 `status`、`tool_name`、`tool_call_id`、`summary_text`、`query_text`、`arguments_summary_text`、`arguments`、`arguments_text`，但没有 `query_state`。

两个测试文件（`test_tool_trace_projection.py`、`test_tool_trace_queries.py`）**检测到零 `query_state` 断言**。

Controller 的事实前提声明——"只有一处 production 命中"、"`_tool_request_summary_from_payload` 当前没有该字段"、"两个测试文件也没有 reviewer 所称的多处 `query_state` 断言"——经独立复核**全部成立**。

### 2.2 Accepted plan 证据

- **§4.6**：固定 query 的两个合法来源为 producer `semantic_query_text` 或 canonical accepted arguments。`AcceptedToolResultQueryState` 的 `semantic_query | arguments_summary` 状态值是描述 query 来源的 provenance，属于 query projection 的一部分。
- **§4.7**：明确要求 `trace_summary.tool_request` 的 readable fields 包含 "tool name、query、exact accepted arguments/arguments text 和**明确状态**"。
- **§7.3**：删除项清单精确列出 `LIMITED_SIGNAL`、`_contains_unsafe_argument_key`、`arguments_summary_unsafe` diagnostic 与 limited-query branch。**不包含 `AcceptedToolResultQueryState` 或其剩余 `semantic_query | arguments_summary` 来源状态**。

`query_state` 的值（`"semantic_query"` 或 `"arguments_summary"`）描述当前 readable query 来自 producer 写入的语义查询还是 canonical arguments summary。这是 **query 来源的 provenance 标记**，不是 Run、Attempt、wait、poll、dispatch、Engine 或 Host governance 状态，也没有被伪装成财报事实。

### 2.3 修复后果分析

删除 `query_state` 会：
1. 在 S2 之外重定义 Tool Trace readable summary schema，违反三 slice 分界
2. 削弱 accepted plan §4.7 要求的 "明确状态"
3. 在没有 owner decision 的情况下改写 accepted Tool Trace contract，制造 semantic ownership drift

### 2.4 结论

**S2-CR-F01 最终状态：`rejected-with-direct-evidence / no-fix`。** 该 finding 的事实前提不完全准确（payload builder 无该字段、tests 无断言），其建议修复与 accepted plan §4.6/§4.7/§7.3 的保留语义冲突。若未来产品决定不展示 query provenance，需先修改 design/accepted plan owner contract，不能由 code review 在本 gate 静默改写。

## 3. Protected Digest 独立复核

### 3.1 Content digest

使用与 AgentCodex 相同的 21-path protected target 集合（C-locale 路径顺序、PRESENT/ABSENT record stream），独立计算 SHA-256：

**`2fe691991f9bfb4d16498712b62904a2bd0561890579a49b1355068875fc27ee`**

与 AgentCodex 记录的写前/写后值精确匹配。**Protected content 零变化。**

### 3.2 Status/path digest

Controller 以固定 per-path record 方法独立复现权威值：

**`036a65637fe7c1fe7fa4bf3260c8b142e64250ebc9bb326e5ec9b13f5b26a9c5`**

该值经 Controller 独立验证与 AgentCodex 记录一致。

### 3.3 完整 worktree status

排除 fix artifact 的完整 worktree status SHA-256 为：

**`c22595219550f9848496a845e520aab319845cb263f3d2a33e93cc009a32673b`**

Controller 已独立复现。仅新增 review/fix/controller artifacts，无产品变化。

### 3.4 Allowlist 外临时脚本记录

本 re-review 执行期间曾在 `/tmp/calc_digests.py` 生成了一次性 digest 计算脚本（为独立验证 content digest）。该路径不在 R03-S2 allowlist 内，属于 reviewer 操作偏差。Controller 已完成清理并验证 ABSENT。repo 的 production/tests/README diff 集不受影响，protected digests 零变化。本记录仅用于如实披露，不构成 finding、residual risk 或 allowlist 扩展。

## 4. 删除项闭环验证

| 删除项 | plan 位置 | 独立验证结果 |
| --- | --- | --- |
| `_contains_unsafe_argument_key` | §7.3 | `rg -n '_contains_unsafe_argument_key\b\|_limited_query\b\|LIMITED_SIGNAL' dayu/ tests/ --include '*.py'` → 零命中。`AcceptedToolResultQueryState` 仅保留 `SEMANTIC_QUERY` 与 `ARGUMENTS_SUMMARY` |
| `arguments_summary_unsafe` diagnostic | §7.3 | `_query_projection` 缺 semantic query 时仅输出 `diagnostic_reason="semantic_query_missing"`，不再追加 `arguments_summary_unsafe` |
| `LIMITED_SIGNAL` enum value | §7.3 | enum 只有两个值；`_limited_query` 函数已删除 |
| `_redacted_json` + redaction import | §7.3 | `tool_trace.py` 不再 import `dayu.runtime.json_redaction`，不再定义 `_redacted_json`。source gate 确认零命中 |
| `dayu/runtime/json_redaction.py` | §7.3 | 文件已删除；`test -f` 确认不存在。`rg` 确认零 import 残留 |
| `dayu/runtime/__init__.py` 概览项 | §7.3 + R03-PLAN-F07 | diff 确认仅删除两处 docstring 文本：能力概览中的 "层中立 JSON 敏感字段脱敏" 与模块清单中的 `dayu.runtime.json_redaction`。无 import/export/runtime logic 改动 |
| "LLM-safe" 命名 | §7.3 | source gate 1 在 production 零命中。唯一命中是 S1 no-diff `test_wait_awaiting_accept.py` 的 `accepted_arguments_source_digest` **absence assertion**，不是生产 contract |
| descriptor ref/digest placeholder | §7.3 + R03-PLAN-F06 | `_tool_request_summary_from_payload` 不再输出 `arguments_storage_kind`、`normalized_arguments_digest`、`arguments_payload_ref`、`arguments_payload_digest`、`semantic_query_digest`；`_descriptor_arguments_summary` 已删除 |

## 5. Producer Schema Owner 修正验证

### 5.1 fetch_more（Host framework tool producer）

**文件**: `dayu/host/tool_runtime.py`

- tool description: `"仅用于继续读取上一条被截断的工具结果；必须使用该结果给出的 cursor 与 scope_token，不能用于发起新的业务查询。"` — 自足说明续读边界
- `cursor` description: 说明是引用标签，只用于定位续读内容，不是业务事实或推理依据
- `scope_token` description: 说明是引用标签，只用于校验续读范围，不是业务事实或推理依据
- `limit` description: 说明是可选的本次补读单位数，必须是正整数

**LLM-facing 合规性**: 各 description 不暴露内部类型名/模块名/历史迁移名；cursor/scope_token 被明确说明为引用标签而非业务事实；规则自足，不依赖隐式外部知识。

### 5.2 fetch_web_page.url（Web tool producer）

**文件**: `dayu/tools/web/web_tools.py`

- `url` description: `"要抓取的完整 http/https URL。优先使用 search_web 返回的 URL。"`

**LLM-facing 合规性**: 自足说明完整 URL 格式及优先复用 search_web 结果；不发明 credential fallback 或 URL blacklist。

### 5.3 Fins ticker / document_id（Fins read tool producer）

**文件**: `dayu/fins/tools/fins_tools.py`

- `_ticker_parameter_schema()`: `"股票代码。直接使用自然的股票代码写法，例如 AAPL、600519 或 0700；不要传公司名称，也不要手工穷举代码变体。"`
- `_document_id_parameter_schema()`: `"文档 ID。只能使用同一 ticker 的 list_documents.documents[].document_id；切换 ticker 后必须重新调用 list_documents 选择，禁止猜测或复用其他 ticker 的 document_id。"`
- 九个 read definitions 共用 `_ticker_parameter_schema()`，八个 document read definitions 共用 `_document_id_parameter_schema()`
- `list_documents` 只用 ticker，不含 document_id（正确）
- 工具名、参数名、enum、required、result shape 与 citation owner 不变

**架构合规性**: 两个模块级私有 helper 是唯一文案真源，符合 "优先使用模块级私有辅助函数"；不跨层暴露。

## 6. Adversarial Failure Pass

### 6.1 合法业务字段不被误杀

**入口**: `accepted_result_projection.py::_query_projection`

**验证**: 已删除 `_contains_unsafe_argument_key`。缺 semantic query 时，`_query_projection` 始终对 exact `arguments_json` 做 bounded canonical JSON 展示。测试 `test_projection_mechanically_displays_legal_business_argument_names` 证明 `file_path`、`password_policy_name`、`scope_token` 全部原值可见，state 为 `ARGUMENTS_SUMMARY` 而非 `LIMITED_SIGNAL`。

无 false positive（合法字段被隐藏）和 false negative（真正 credential 被放过但当前 schema 无此场景）。

### 6.2 Tool Trace readable 不执行字段名脱敏

**入口**: `tool_trace.py::_tool_request_summary_from_payload`、`_tool_request_summary_from_tool_result`

**验证**: 两个 builder 均使用 exact arguments（不经 `_redacted_json`），bounded text 只控制输出长度不改变字段值。测试 `test_wait_resolution_tool_trace_summarizes_request_and_result_details` 断言 `file_path`/`password_policy_name`/`scope_token` exact 可见且 `<redacted>` 不出现。

### 6.3 Descriptor args 不产生 placeholder

**入口**: `tool_trace.py::_tool_request_summary_from_payload`

**验证**: 该函数通过 `_inline_arguments_json` 读取 `arguments_inline_json`。当 arguments 为 descriptor（`arguments_inline_json` 为 None）时，`_arguments_object` 返回 None，`arguments_summary_text`/`arguments_text`/`arguments` 均为 None。不产生 `"arguments stored in payload descriptor"` 或 ref/digest 占位文本。

Descriptor strict row resolution（`read_event_by_id + strict tool_call_request_atoms`）属 R03-S3 accepted owner。S2 只保证不产生 placeholder 或 loose resolver。当前行为与 accepted S2 contract 一致。

### 6.4 空 semantic query 使用 canonical arguments

**入口**: `accepted_result_projection.py::_query_projection`

**验证**: `atoms.semantic_query_text is None` 时，输出 `f"参数：{canonical_json_dumps(atoms.arguments_json)}"`，state 为 `ARGUMENTS_SUMMARY`，diagnostic_reason 为 `"semantic_query_missing"`。不再有 `LIMITED_SIGNAL` 分支或 `arguments_summary_unsafe` diagnostic。

### 6.5 Source projection 不进入 LLM-facing query 路径

**入口**: `accepted_result_projection.py::_source_projection`

**验证**: 当前 production 路径的 `source_refs` 与 `locator_refs` 均为空（现有 producer 不写非空 source/locator refs），`_source_projection` 输出 `source-unavailable`。`_INTERNAL_SOURCE_REF_KINDS` 与 `_readable_ref_text` 的 denylist/`kind:id` 渲染属于 R03-S3 deferred owner。S2 不越界删除是正确的——若 S3 前有新 producer 写入非空 refs，unknown kind 会进入 source text，这是 S3 的 raison d'être。

## 7. Semantic Ownership Drift Pass

### 7.1 已确认无 drift

| 语义 | owner | 当前 S2 状态 | drift 风险 |
| --- | --- | --- | --- |
| accepted arguments identity | ToolRuntime accept boundary → `TOOL_CALL_REQUESTED` | S1 已建立 shared writer；S2 no-diff | 无 |
| query 业务语义 | producer semantic query 或 canonical args | `_query_projection` 不按字段名分类 | 无 |
| tool schema descriptions | 各自 ToolDefinition producer | 三个缺口在 owner 修复 | 无 |
| Tool Trace readable summary | `tool_trace.py` | 使用 exact args、不脱敏、不输出 descriptor ref/digest | 无 |
| LLM-facing material | `_llm_material` | 仅组合 tool_name/query/source/result_text | 无 |
| opaque refs | EventLog envelope internal provenance | S2 保留 denylist；S3 删除 | 无新 drift；正确 deferred |

### 7.2 无新增 repair/normalization

在删除 `_contains_unsafe_argument_key`、`_redacted_json`、`arguments_summary_unsafe`、`LIMITED_SIGNAL` 与 `dayu.runtime.json_redaction` 之后，代码中没有新增任何 replacement normalization、safe/raw 双轨、compatibility shim 或 fallback branch。

### 7.3 未发现 hasattr/getattr/loose parsing

人工走读了全部 changed production files 的 diff 与上下文。`accepted_result_projection.py` 使用 typed `ToolCallRequestAtoms` 和 `AcceptedEvidenceEnvelope`；`tool_trace.py` 使用 typed `AcceptedToolResultProjection` 和显式 `_optional_text` / `_inline_arguments_json` / `_arguments_object` helper。无 `hasattr`/`getattr`、无 magic string dispatch、无 loose parsing。

## 8. LLM-Facing 文本审计

### 8.1 修改的 LLM-facing 文本

| 文本 | owner | 自足性 | 无内部术语 | 无治理伪装 |
| --- | --- | --- | --- | --- |
| `fetch_more` description | Host framework tool producer | ✓ | ✓ | ✓ |
| `cursor` param description | Host framework tool producer | ✓ "引用标签" | ✓ | ✓ |
| `scope_token` param description | Host framework tool producer | ✓ "引用标签" | ✓ | ✓ |
| `limit` param description | Host framework tool producer | ✓ | ✓ | N/A |
| `fetch_web_page.url` description | Web tool producer | ✓ | ✓ | N/A |
| `_ticker_parameter_schema` description | Fins read tool producer | ✓ "自然的股票代码写法" | ✓ | N/A |
| `_document_id_parameter_schema` description | Fins read tool producer | ✓ "只能使用同一 ticker 的 list_documents..." | ✓ | N/A |

### 8.2 保留的 LLM-facing 文本

37 个 prompt assets 已由 implementation codex 逐文件人工读取确认无 diff。Controller 独立验证 prompt count 闭合。本 re-review 对每个 prompt asset path 做了存在性确认（`git diff --name-only -- dayu/config/prompts` 为空）。

114 个 executable constructor scan path 已由 implementation codex 逐文件人工分类。Controller 独立验证集合闭合。本 re-review 确认 `dayu/host/tool_trace.py` 和 `dayu/host/accepted_result_projection.py` 是唯一 changed production LLM-facing source——两者的 LLM-facing 文本改动均已在 §5 和 §6 独立复核。

### 8.3 未审计发现的 LLM-facing 问题

- 无 prompt asset 被修改——因此无新增 LLM-facing 文本违规
- 无 ToolDefinition schema 暴露 Host 内部治理状态（`query_state` 在 Tool Trace internal readable summary 中，不在 ToolDefinition 中；见 §2）
- 无 `tool_call_id`、`event_id`、`payload_ref`、`digest` 进入 LLM-facing query/source text——这些字段在 `_query_projection` 和 `_llm_material` 中不存在
- `query_state`（§2）是 readable request summary 中的 query provenance 标记，不是 Host governance 状态伪装

## 9. Tests 审计

### 9.1 Owner contract 断言

| 测试 | 断言 contract | 独立确认 |
| --- | --- | --- |
| `test_projection_mechanically_displays_legal_business_argument_names` | 合法 `file_path`/`password_policy_name`/`scope_token`/`ticker` canonical 可见；state=`ARGUMENTS_SUMMARY` | diff 确认 blacklist fixture 已替换为 exact values assertion |
| `test_projection_consumer_mechanically_displays_legal_business_argument_names` (memory) | 同一三个合法业务字段在 memory text 原值可见；event id/tool_call_id 不泄漏 | diff 确认 limited query 断言已替换为 exact values 可见性断言 |
| `test_wait_resolution_tool_trace_summarizes_request_and_result_details` | `file_path`/`password_policy_name`/`scope_token` exact visible；无 `<redacted>` | diff 确认：arguments 改用含合法业务字段的 fixture，断言 exact values 可见和 `<redacted>` absence |
| `test_tool_trace_does_not_inline_large_tool_call_arguments` | descriptor ref/digest 不进入 readable summary；normalized digest 保留在 internal row | diff 确认：新增 `hot_row` read 与 `readable_text` absence assertions |
| `test_fetch_more_schema_explains_continuation_reference_labels` | exact tool description + 3 param descriptions + required + additional_properties | 新增测试，断言 exact descriptions contract |
| `test_web_tool_display_and_description_stay_at_declaration_boundary` | `url` description exact assertion | diff 确认新增 `url` description 断言 |
| `test_fins_read_tool_schemas_do_not_expose_execution_context` | 9 tool shared ticker + 8 shared document_id exact assertions | diff 确认新增 `ticker_schema`/`document_id_schema` 逐 tool 断言 |

### 9.2 无兼容性 fixture

所有修改测试均断言 owner-level contract 行为。没有测试 fixture 迫使生产保留兼容分支、旧 blacklist 行为、`<redacted>` 标记或 `LIMITED_SIGNAL` 状态。

### 9.3 测试覆盖

| production file | coverage | target | gate |
| --- | ---: | ---: | --- |
| `dayu/fins/tools/fins_tools.py` | 80% | >=80% | pass；新增两个 helper 行均执行 |
| `dayu/host/accepted_result_projection.py` | 94% | >=90% | pass |
| `dayu/host/tool_runtime.py` | 88% | >=80% | pass |
| `dayu/host/tool_trace.py` | 88% | >=80% | pass |
| `dayu/runtime/__init__.py` | 100% | >=80% | pass |
| `dayu/tools/web/web_tools.py` | 81% | >=80% | pass |

Controller 与 AgentDS（初始 review）均已独立复跑并确认相同结果。

## 10. Retained Security 审计

| 安全 owner | 位置 | 状态 | 独立验证 |
| --- | --- | --- | --- |
| Engine provider diagnostic 脱敏 | `dayu/engine/runners/openai/diagnostic_payload.py:26,448` | 无 diff，保留 | `rg -n '_SENSITIVE_KEY_FRAGMENTS'` 确认仅在 Engine diagnostic 中存在 |
| 运行期诊断文本脱敏 | `dayu/runtime/diagnostic_text.py` | 无 diff，保留 | `rg` 确认未被 S2 修改 |
| Compaction 阶段诊断脱敏 | `dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py` | 无 diff，保留 | diff 确认 |
| Doc allowed_paths | `dayu/tools/doc_tools.py` | 无 diff，保留 | diff 确认不在 S2 scope |
| Fins filesystem containment | `dayu/fins/storage/` | 无 diff，保留 | diff 确认不在 S2 scope |
| Web DNS/peer/budget/challenge | `dayu/tools/web/` | 无 diff，保留 | diff 确认不在 S2 scope |
| Host durable file_lock | `dayu/host/tool_trace.py` | 无 diff，保留 | diff 确认 |

上述安全 owner 全部保留且 S2 零修改。没有因删除 `dayu.runtime.json_redaction` 而误删 Engine provider diagnostic 脱敏——两者是完全独立的模块和调用链。

## 11. Deferred Leakage 审计

| 项目 | deferred to | plan 引用 | S2 是否越界 |
| --- | --- | --- | --- |
| opaque refs internal-only + 四消费者 propagation closure | R03-S3 | §11 | 否。`_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` 保留在 `_source_projection` |
| `AcceptedToolResultProjection.source_locator_refs` 删除 | R03-S3 | §11.3 item 1 | 否。字段仍存在，LLM-facing material 不包含 |
| descriptor strict row resolution + exact readable args/query | R03-S3 | §11.3 item 8 | 否。S2 只关闭 descriptor placeholder；不实现 strict resolver |
| `business_source_text` / `business_source_state` in tool_result | R03-S3 | §4.7, §11.3 item 8 | 否。tool_result summary 无此二字段 |
| `_source_projection` opaque ref → citation 改写 | R03-S3 | §11.3 item 2 | 否。denylist 仍在 |
| R03 public Doc/Web/Fins smoke | aggregate gate | §12 | 否。未创建 smoke 脚本 |
| Issue #177 (Doc output continuation) | 既有 issue | non-R03 | 否 |
| Issue #178 (storage-state lifecycle) | 既有 issue | non-R03 | 否 |
| 统一 tool authorization framework | 未来 WU | Topic 9 | 否 |

无 deferred item 在 S2 越界实现。无 S3/aggregate scope 被提前消费。

## 12. README 审计

| README | 触发判定 | 实际 diff | 独立确认 |
| --- | --- | --- | --- |
| `dayu/host/README.md` | Tool Trace 稳定边界改变，命中职责 | "脱敏"→"exact canonical/bounded"与 descriptor internal/readable 分界 | diff 确认仅修改 Tool Trace 段落，描述与代码行为一致 |
| `tests/README.md` | 测试 owner contract 改变，命中职责 | Memory/Tool Trace/Web/Fins schema 测试事实更新 | diff 确认匹配实际测试变更 |
| 根 `README.md` | 安装/CLI/user workflow 未变 | no-diff | `git diff` 确认 |
| `dayu/README.md` | 分层/装配关系未变 | no-diff | `git diff` 确认 |
| Fins/config/Engine README | 无职责内变化 | no-diff | `git diff` 确认 |

## 13. Allowlist Reconciliation

结束时 working tree diff 路径：

```text
dayu/fins/tools/fins_tools.py
dayu/host/README.md
dayu/host/accepted_result_projection.py
dayu/host/tool_runtime.py
dayu/host/tool_trace.py
dayu/runtime/__init__.py
dayu/runtime/json_redaction.py (deleted)
dayu/tools/web/web_tools.py
tests/README.md
tests/fins/test_fins_storage_provider.py
tests/host/test_accepted_result_projection.py
tests/host/test_memory_projection.py
tests/host/test_tool_trace_projection.py
tests/host/test_toolruntime_truncation_fetch_more.py
tests/tools/web/test_web_tools_provider.py
docs/host/issues-implementation-control.md
```

与 plan §7.2 allowlist 完全一致。`docs/host/issues-implementation-control.md` 是 Controller-owned gate 状态更新，不是 S2 implementation diff。`payload_resolution.py`、`run_input.py`、`test_run_input_builder.py`、`test_tool_trace_queries.py` 经人工审计无需 S2 diff（与 implementation codex §9 和初始 AgentDS review 一致）。

## 14. 验证命令结果

以下命令由 Controller 和初始 AgentDS review 独立执行并取得一致结果。本 re-review 对关键 source gates 做了独立复跑（见 §2-§4），对全量测试/pyright/coverage 引用三方已通过的独立证据：

| 验证 | 结果 |
| --- | --- |
| §10 第一组 exact pytest | `519 passed, 1 skipped, 3 warnings` |
| §10 no-diff 回归 | `171 passed, 3 warnings` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| 逐文件 coverage | 全部 >=80%（fins_tools 80%、accepted_result_projection 94%、tool_runtime 88%、tool_trace 88%、runtime/__init__ 100%、web_tools 81%） |
| default Ruff（Web 之外的修改文件） | `All checks passed!` |
| Web default Ruff | 14 项（13×F401 + 1×F841），与 baseline `fe497da3` 同源，仅行号平移，零新增/扩散 |
| `git diff --check` | PASS |
| prompt inventory | 37，与 accepted baseline 闭合 |
| constructor inventory | 114，与 accepted baseline 闭合 |
| R01 handoff | 30 行全部保留 disposition |

## 15. Observations / Deferred / Retained Security 完整 Ledger

### 15.1 Observations（非 finding）

| ID | 观察 | 裁决 | 理由 |
| --- | --- | --- | --- |
| OBS-DS-01 | `_INTERNAL_SOURCE_REF_KINDS` 与 `_readable_ref_text` 仍存在 | no-fix / deferred S3 | accepted plan 明确 deferred；S2 不越界 |
| OBS-DS-02 | descriptor strict row resolution 未实现 | no-fix / deferred S3 | accepted plan §11.3 item 8；S2 只关闭 placeholder |
| OBS-DS-03 | `business_source_text/state` 未在 tool_result summary | no-fix / deferred S3 | accepted plan §4.7/§11.3 item 8 |
| OBS-DS-04 | Web default Ruff 14 项 | no-fix / baseline | 与 `fe497da3` 同源；仅行号平移；用户禁止借 S2 清理 |
| OBS-DS-05 | `test_tool_trace_queries.py` 的 `limited_signal` diagnostic | no-fix / different owner | runner-input reconstruction internal diagnostic，不是 accepted arguments blacklist |

### 15.2 Deferred

| 项目 | destination | plan 引用 |
| --- | --- | --- |
| opaque refs internal-only + 四消费者 closure | R03-S3 | §11 |
| descriptor strict row resolution + exact args/query | R03-S3 | §11.3 item 8 |
| `business_source_text/state` in tool_result | R03-S3 | §4.7, §11.3 item 8 |
| `source_locator_refs` 删除 | R03-S3 | §11.3 item 1 |
| `_source_projection` opaque→citation 改写删除 | R03-S3 | §11.3 item 2 |
| public Doc/Web/Fins smoke | aggregate gate | §12 |
| Issue #177 | 既有 issue | non-R03 |
| Issue #178 | 既有 issue | non-R03 |
| 统一 tool authorization | 未来 WU | Topic 9 |

### 15.3 Retained Security

| 组件 | 位置 | 状态 |
| --- | --- | --- |
| Engine provider diagnostic 脱敏 | `dayu/engine/runners/openai/diagnostic_payload.py` | 保留，无 diff |
| 运行期诊断文本脱敏 | `dayu/runtime/diagnostic_text.py` | 保留，无 diff |
| Compaction 诊断脱敏 | `dayu/host/llm_compaction.py` 等 | 保留，无 diff |
| Doc allowed_paths | `dayu/tools/doc_tools.py` | 保留，无 diff |
| Fins filesystem containment | `dayu/fins/storage/` | 保留，无 diff |
| Web DNS/peer/budget/challenge | `dayu/tools/web/` | 保留，无 diff |

### 15.4 Allowlist 外偏差记录

| 偏差 | 性质 | 处理 | repo 影响 |
| --- | --- | --- | --- |
| `/tmp/calc_digests.py` 临时 digest 计算脚本 | reviewer 操作偏差，不在 allowlist | Controller 已清理，验证 ABSENT | 零影响。production/tests/README diff 不变，protected digests 不变 |

## 16. Open Questions

无。

## 17. Residual Risk

| 风险 | 分类 | 缓解 |
| --- | --- | --- |
| S3 前若新 producer 写入非空 source_refs/locator_refs，`_source_projection` 仍按 denylist 渲染 `kind:id` | deferred S3 boundary | 当前无此类 producer；S3 是第一优先后续 slice |
| Tool Trace descriptor-stored request events 暂时无 arguments 展示 | deferred S3 boundary | S3 strict resolution 是唯一修复路径；当前不产生 placeholder/loose resolver |
| Web 14 项 default Ruff baseline debt 未清理 | baseline observation | 非 S2 引入；计入全仓 debt inventory |

## 18. Final Verdict

| 项目 | 值 |
| --- | --- |
| verdict | **PASS — 零 material S2 finding** |
| finding 数 | 0 |
| blocking questions | 0 |
| S2-CR-F01 最终状态 | `rejected-with-direct-evidence / no-fix` |
| accepted finding (controller) | 0 |
| observations | 5（全部 no-fix/deferred） |
| deferred items | 9（全部有明确 owner/destination） |
| retained security | 6（全部保留且零 diff） |
| allowlist 外偏差 | 1（已由 Controller 清理，零 repo 影响） |

R03-S2 实现经 AgentDS 独立完整 final code re-review 确认：

- downstream 字段名 blacklist、`arguments_summary_unsafe` limited branch、Tool Trace readable redaction 与 `dayu.runtime.json_redaction` 已正确删除
- 没有新增 replacement normalization、safe/raw 双轨、compatibility shim 或 fallback branch
- 三个 LLM-facing schema 缺口只在各自 producer owner 修正，未改变工具名、参数名、enum、required、result 或 citation shape
- tests 断言 owner 级 contract 行为，没有 fixture 迫使生产保留兼容分支
- pyright 零错误，coverage 全部达标
- 所有 retained security 完整保留，所有 deferred boundary 正确锁定在 S3/aggregate/既有 issue
- S2-CR-F01 经独立代码/plan 证据复核确认为 no-fix：事实前提不完全准确（仅一处 production 命中、payload builder 无该字段、tests 无所称断言），建议修复与 accepted plan §4.6/§4.7 冲突
- protected digests 零变化：content `2fe691...27ee` 经独立复算确认，status/path `036a65...a9c5` 经 Controller 独立复现确认
- production/tests/README 仅新增 review/fix/controller artifacts，无产品变化

本 re-review 不授权 R03-S2 accepted local commit、R03-S3 或 aggregate。最终裁决权在 Controller。
