# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Code Review — AgentDS

## 0. Gate 与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| review target | baseline 到当前 working tree 的 R03-S2 production/tests/README diff |
| implementation artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md` |
| controller validation | `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md` |
| AgentDS verdict | **PASS — 零 material S2 finding** |
| finding 数 | 0 |
| blocking questions | 无 |

R03-S2 的实现边界与 accepted plan 一致：downstream 字段名 blacklist、`arguments_summary_unsafe` limited branch、Tool Trace readable redaction 与 `dayu.runtime.json_redaction` 已删除，没有新增 replacement normalization。三个 schema 缺口只在各自 producer owner 修复。所有 deferred S3 boundary、retained security 与 baseline lint debt 均未越界。

## 1. 审查方法

按用户指定顺序完整读取了全部 8 项权威输入，并以 baseline 到 working tree 的完整 diff 与逐文件源码走读为直接证据。审查路径：

1. **full diff walk**：`git diff fe497da3 --` 全部 16 个 changed files，逐文件确认 diff 与 plan allowlist 一致
2. **production call-path trace**：`accepted_result_projection.py` 的 `_query_projection` → `_source_projection` → `_llm_material`；`tool_trace.py` 的 `_canonical_trace_summary_signals` → `_tool_request_summary_from_payload` / `_tool_request_summary_from_tool_result` → `_tool_result_summary_from_projection`
3. **adversarial failure pass**：空 envelope、缺失 semantic query、descriptor args、corrupted payload、字段名含 `path/token/password` 的合法业务参数
4. **semantic ownership drift pass**：逐一确认被删代码已无下游补偿、新增 schema helper 是唯一文案真源、LLM-facing material 不携带内部 ref/digest
5. **source gate verification**：独立执行 §10.3 四项 grep，逐命中人工归属
6. **独立复跑**：§10 exact pytest suite、full pyright、coverage、Ruff baseline 对照

## 2. Findings

未发现实质性问题。

## 3. 逐项验证记录

### 3.1 删除项闭环

| 删除项 | plan 位置 | 逐文件证据 | 状态 |
| --- | --- | --- | --- |
| `_contains_unsafe_argument_key` | §7.3 | `accepted_result_projection.py` 不再定义/调用；`rg` 零命中 | 已删除 |
| `arguments_summary_unsafe` diagnostic | §7.3 | 同上 | 已删除 |
| `LIMITED_SIGNAL` query state | §7.3 | `AcceptedToolResultQueryState` 只有 `SEMANTIC_QUERY` 与 `ARGUMENTS_SUMMARY` | 已删除 |
| `_redacted_json` + redaction import | §7.3 | `tool_trace.py` 不再导入 runtime redaction，不定义 `_redacted_json` | 已删除 |
| `dayu/runtime/json_redaction.py` | §7.3 | 文件已删除；`git diff fe497da3 -- dayu/runtime/json_redaction.py` 确认为完整删除 | 已删除 |
| `dayu/runtime/__init__.py` JSON 脱敏概览项 | §7.3 + R03-PLAN-F07 | diff 确认只删除 "层中立 JSON 敏感字段脱敏" 与模块清单中的 `json_redaction`；无 import/export/runtime logic 改动 | 已删除 |
| "LLM-safe request/replay arguments" 命名 | §7.3 | `rg 'llm_safe_replay_arguments\|arguments_summary_unsafe\|unsafe_argument\|safe_arguments' dayu tests` 在生产代码零命中 | 已删除 |

### 3.2 新增/修改项验证

| 项目 | plan 位置 | 直接证据 | 状态 |
| --- | --- | --- | --- |
| fetch_more description + 3 param descriptions | §7.4 item 1 | `tool_runtime.py:282-285` description，`:5713-5736` cursor/scope_token/limit | 符合 LLM-facing 自足性 |
| fetch_web_page.url description | §7.4 item 2 | `web_tools.py:169-172` URL description | 符合 LLM-facing 自足性 |
| Fins `_ticker_parameter_schema` / `_document_id_parameter_schema` | §7.4 item 3 | `fins_tools.py:1710-1748` 两个模块级私有 helper，9 个 read definition 复用 ticker，8 个复用 document_id | 模块级私有 helper，是唯一文案真源 |
| `_query_projection` 缺 semantic query 时机械展示 bounded canonical args | §7.3 | `accepted_result_projection.py:517-521`：`f"参数：{canonical_json_dumps(atoms.arguments_json)}"` | 不按字段名分类 |

### 3.3 测试 owner contract

| 测试 | 断言内容 | 证据 |
| --- | --- | --- |
| `test_projection_mechanically_displays_legal_business_argument_names` | `file_path`/`password_policy_name`/`scope_token`/`ticker` 全部原值可见；state 为 `ARGUMENTS_SUMMARY` 而非 `LIMITED_SIGNAL` | `test_accepted_result_projection.py:775-837` |
| `test_projection_consumer_mechanically_displays_legal_business_argument_names` (memory) | 同一三个合法业务字段在 memory text 中原值可见；无 event id / tool_call_id 泄漏 | `test_memory_projection.py:2576-2650` |
| `test_wait_resolution_tool_trace_summarizes_request_and_result_details` | `file_path`/`password_policy_name`/`scope_token` exact visible；无 `<redacted>` | `test_tool_trace_projection.py:999-1146` |
| `test_tool_trace_does_not_inline_large_tool_call_arguments` | descriptor ref/digest 不在 readable summary；normalized digest 保留在 internal row | `test_tool_trace_projection.py:2083-2148` |
| `test_fetch_more_schema_explains_continuation_reference_labels` | exact description + 3 param descriptions + required + additional_properties | `test_toolruntime_truncation_fetch_more.py:226-269` |
| `test_web_tool_display_and_description_stay_at_declaration_boundary` | url description exact assertion | `test_web_tools_provider.py:4277-4283` |
| `test_fins_read_tool_schemas_do_not_expose_execution_context` | 9 tool shared ticker + 8 shared document_id exact assertions | `test_fins_storage_provider.py:1565-1602` |

### 3.4 独立验证结果

| 验证 | 命令 | 结果 |
| --- | --- | --- |
| §10 第一组 exact pytest | `pytest tests/host/test_accepted_result_projection.py ... tests/fins/test_fins_storage_provider.py -q` | `519 passed, 1 skipped, 3 warnings` |
| §10 no-diff 回归 | `pytest tests/tools/test_doc_tools_provider.py ... -q` | `171 passed, 3 warnings` |
| full pyright | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| coverage | 全 Host test suite | `fins_tools.py 80%`、`accepted_result_projection.py 94%`、`tool_runtime.py 88%`、`tool_trace.py 88%`、`runtime/__init__.py 100%`、`web_tools.py 81%` — 全部 >=80% |
| default Ruff（Web 之外的修改文件） | `ruff check` | `All checks passed!` |
| Web default Ruff | `ruff check dayu/tools/web/web_tools.py` | 14 项（13×F401 + 1×F841），与 `git show HEAD:dayu/tools/web/web_tools.py \| ruff check --stdin-filename ...` 完全一致 → 零新增/扩散 |

### 3.5 Source gates（独立执行）

**Gate 1**: `llm_safe_replay_arguments|arguments_summary_unsafe|unsafe_argument|safe_arguments|accepted_arguments_source_digest`
- production 零命中
- 唯一命中：`tests/host/test_wait_awaiting_accept.py:337` 的 `accepted_arguments_source_digest` **absence assertion**（S1 owner test，不在 S2 allowlist）

**Gate 2**: `redact_sensitive_json_fields|json_redaction|_SENSITIVE_KEY_FRAGMENTS|JSON_REDACTION_MARKER`
- Host/runtime/tests 零命中；删除模块不存在
- `dayu/engine/runners/openai/diagnostic_payload.py:26,448`：`_SENSITIVE_KEY_FRAGMENTS` — Engine provider diagnostic 独立安全脱敏 owner，**retained security，不是 accepted arguments/Tool Trace readable normalization**

**Gate 3**: `_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text`
- 仍在 `accepted_result_projection.py:58,586,604,612` — R03-S3 deferred opaque source owner，plan + controller 明确禁止 S2 删除

**Gate 4**: `api_key.*token.*secret.*password|password.*secret.*token.*api_key` in `dayu/host dayu/runtime tests/host`
- 零命中

### 3.6 allowlist reconciliation

结束时 implementation diff 路径：

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
```

与 plan §7.2 allowlist 完全一致。`payload_resolution.py`、`run_input.py`、`test_run_input_builder.py`、`test_tool_trace_queries.py` 经人工审计无需 S2 diff（与 implementation codex §9 一致）。无 allowlist 外文件被修改。

### 3.7 README trigger

| README | 触发判定 | 实际 diff | 状态 |
| --- | --- | --- | --- |
| `dayu/host/README.md` | Tool Trace 稳定边界改变，命中职责 | 将 "脱敏" 陈述改为 exact canonical/bounded 与 descriptor internal/readable 分界 | 正确 |
| `tests/README.md` | 测试 owner contract 改变，命中职责 | 更新 Memory/Tool Trace/schema owner 测试事实 | 正确 |
| 根 `README.md` | 安装/CLI/user workflow 未变 | no-diff | 正确 |
| `dayu/README.md` | 分层/装配关系未变 | no-diff | 正确 |
| Fins/config/Engine README | 无职责内变化 | no-diff | 正确 |

## 4. Rejected / no-fix observations

以下每项都经过了完整的直接证据链验证，结论是它们不属于 S2 material finding：

### 4.1 Opaque source ref guessing 保留在 `_source_projection`

- **位置**：`accepted_result_projection.py:58-68`（`_INTERNAL_SOURCE_REF_KINDS`）、`:567-614`（`_source_projection` + `_readable_ref_text`）
- **为什么不是 S2 finding**：accepted plan §11.3 item 2 明确把 opaque source owner removal 放入 R03-S3；Controller validation §3 明确裁决 "不得在 S2 删除"；当前生产路径的 `source_refs` 与 `locator_refs` 均为空，guessing 路径在生产中不可达
- **风险**：若 S3 前有新 producer 写入非空 source_refs，unknown kind 会进入 source text；但这是 S3 的 raison d'être，不是 S2 回归

### 4.2 `_tool_request_summary_from_payload` 只读 inline args

- **位置**：`tool_trace.py:1172-1225`（通过 `_inline_arguments_json` 读 `arguments_inline_json`）
- **为什么不是 S2 finding**：accepted plan §11.3 item 8 + R03-PLAN-F06 明确把 `TOOL_CALL_REQUESTED` 的 `read_event_by_id + strict tool_call_request_atoms` descriptor resolution 放入 S3；当前行为（inline 显示 exact args，descriptor 不显示且不产生 placeholder）是 accepted S2 contract。该函数不尝试 loose resolve descriptor，不产生 ref/digest 输出，不构成 loose resolver
- **风险**：descriptor-stored request events 在 Tool Trace 中暂时无 arguments 展示；S3 strict resolution 是唯一修复路径

### 4.3 `business_source_text` / `business_source_state` 尚未加入 tool_result summary

- **位置**：`tool_trace.py:1245-1302`（`_tool_result_summary_from_projection`）
- **为什么不是 S2 finding**：accepted plan §4.7 与 §11.3 item 8 明确把这两个字段的添加放入 S3；当前 tool_result summary 的 `status`/`result_status`/`result_summary_text`/`result_details`/`result_text` 与 `raw_outcome_digest` 均为 accepted S2 contract

### 4.4 Web 14 项 default Ruff baseline debt

- **位置**：`dayu/tools/web/web_tools.py` 13×F401 + 1×F841
- **为什么不是 S2 finding**：`git show HEAD:dayu/tools/web/web_tools.py | ruff check --stdin-filename ...` 产生相同 14 项；本次只插入 4 行 URL description，仅导致 F841 行号平移；零新增/扩散。Controller 明确禁止借 schema-only diff 修改无关代码

### 4.5 `AcceptedToolResultProjection.source_locator_refs` 字段仍存在

- **位置**：`accepted_result_projection.py:162`（dataclass field）、`:241-243`（populated from envelope）
- **为什么不是 S2 finding**：accepted plan §11.3 item 1 明确把该字段删除放入 S3；当前 LLM-facing material（`_llm_material` 产物）不包含 opaque refs；字段保留仅用于 internal/diagnostic round-trip，与 S2 contract 一致

## 5. Retained security

| 组件 | 位置 | owner | 说明 |
| --- | --- | --- | --- |
| Engine provider diagnostic 脱敏 | `dayu/engine/runners/openai/diagnostic_payload.py:26,448` | Engine provider diagnostic | `_SENSITIVE_KEY_FRAGMENTS` 用于 provider payload 诊断脱敏，不是 accepted arguments blacklist；不受 S2 删除影响 |
| 路径 containment | `dayu/fins/storage/` | Fins storage | 保留；不在 S2 scope |
| Web DNS/peer/budget/challenge | `dayu/tools/web/` | Web tool producer | 保留；不在 S2 scope |
| Doc allowed_paths | `dayu/tools/doc_tools.py` | Doc tool producer | 保留；不在 S2 scope |

## 6. Deferred boundaries

| 项目 | deferred to | plan 引用 |
| --- | --- | --- |
| opaque refs internal-only + 四消费者 propagation closure | R03-S3 | §11 |
| descriptor strict row resolution + exact args/query + corruption fail-close | R03-S3 | §11.3 item 8 |
| `business_source_text` / `business_source_state` in tool_result summary | R03-S3 | §4.7, §11.3 item 8 |
| `AcceptedToolResultProjection.source_locator_refs` 删除 | R03-S3 | §11.3 item 1 |
| `_source_projection` opaque ref → citation 改写删除 | R03-S3 | §11.3 item 2 |
| public Doc/Web/Fins smoke | aggregate gate | §12 |
| Issue #177 (Doc output continuation) | 既有 issue | non-R03 |
| Issue #178 (storage-state lifecycle) | 既有 issue | non-R03 |
| 统一 tool authorization framework | 未来 WU | Topic 9 |

## 7. Open Questions

无。

## 8. Residual Risk

| 风险 | 分类 | 缓解 |
| --- | --- | --- |
| S3 前若有新 producer 写入非空 source_refs/locator_refs，`_source_projection` 仍会按 denylist 渲染 `kind:id` | deferred S3 boundary | 当前无此类 producer；S3 是第一优先后续 slice |
| Tool Trace descriptor-stored request events 暂时无 arguments 展示 | deferred S3 boundary | S3 strict resolution 是唯一修复；当前不产生 placeholder/loose resolver |
| Web 14 项 default Ruff baseline debt 未被清理 | baseline observation | 非 S2 引入；计入全仓 debt inventory |
| test_dispatch_scheduler.py 1 个 pre-existing failure | pre-existing | `test_wake_queue_promotion_uses_tracked_async_promotion_task` — 与 S2 无关的既有 flaky test |

## 9. 最终 verdict

**R03-S2 实现通过 AgentDS 完整 adversarial code review。零 material S2 finding。**

实现正确删除了下游字段名 blacklist repair、`arguments_summary_unsafe` limited branch、Tool Trace readable redaction 与 `dayu.runtime.json_redaction`。三个 schema 缺口只在 producer owner 修正。LLM-facing material 不携带内部 ref/digest。所有 deferred S3 boundary、retained security 与 baseline lint debt 均被保留且未被越界修改。tests 断言 owner contract 行为，pyright 零错误，coverage 全部达标。

可进入 R03-S3。
