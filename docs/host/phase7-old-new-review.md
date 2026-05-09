# Host P7 OLD/NEW tool trace 语义 review

## Review 范围

- **OLD**: `dayu-agent/dayu/engine/tool_trace.py` + `tests/engine/test_tool_trace.py` + `utils/analyze_tool_trace.py`
- **NEW**: `dayu-agent-r/dayu/host/_tool_trace_projection.py` + `_tool_trace_jsonl_sink.py` + `contracts.py` + `utils/analyze_tool_trace_host.py` + 对应 `tests/host/test_phase7_*.py`

## 结论：有条件通过

NEW 在 trace record 结构层面对 OLD 的核心诊断语义做了保留或增强，但在 analyzer 层丢失了大量 OLD 已有的高价值诊断能力。需要补齐 analyzer 后才能完全替代 OLD。

---

## Finding 1: schema_version 差异明确，不误导

**状态: PASS**

- OLD: `tool_trace_v2`
- NEW: `tool_trace_v2_host`
- NEW analyzer `_validate_schema_version` 严格拒绝非 `tool_trace_v2_host`，并在错误消息中明确告知 OLD schema 有不同治理边界。
- `_tool_trace_jsonl_sink.py:9` 文档明确声明"不向后兼容 OLD `tool_trace_v2`"。

**证据**: `_tool_trace_jsonl_sink.py:34` `_TRACE_SCHEMA_VERSION_HOST = "tool_trace_v2_host"`；`analyze_tool_trace_host.py:191-197` 校验逻辑。

---

## Finding 2: tool_call request/result 配对机制改变，无 close() 补偿

**状态: WARNING — 语义正确但行为不等价**

- OLD: `V2ToolTraceRecorder` 用 `_pending_requests` / `_pending_results` 缓冲未配对记录，在 `close()` 时输出 `RESULT_MISSING` / `REQUEST_MISSING` 补偿记录（`tool_trace.py:1275-1305`）。
- NEW: `ToolTraceObserver.process()` 在同 batch 内按 `(iteration_id, tool_call_id)` 配对，未配对时抛 `ProjectionSchemaError`（`_tool_trace_projection.py:247-249`），由 `ProjectionCoordinator` 按 `BLOCKED_FAILED` 记录。
- NEW 没有跨 batch 缓冲，也没有 close() 补偿路径。

**影响**: OLD 的 `RESULT_MISSING` / `REQUEST_MISSING` 让 analyzer 能报告"run 结束时有未配对的工具调用"这一诊断事实。NEW 的 `ProjectionSchemaError` 只记录在 coordinator checkpoint 中，不会出现在 JSONL trace 里，analyzer 无法感知。

**建议**: 考虑在 trace record 中保留 `RESULT_MISSING` / `REQUEST_MISSING` 语义，或在 analyzer 中从 coordinator checkpoint 中提取。

---

## Finding 3: iteration_context_snapshot 增强

**状态: PASS — NEW 更丰富**

| 维度 | OLD | NEW |
|------|-----|-----|
| message summary | `source_tag` + `excerpt` + `content_hash` | `role` + `source_kind` + `excerpt` + `content_hash` + `char_size` + `token_estimate` |
| tool schema summary | `tool_schema_names` (名称列表) | `RunInputToolSchemaSummary` (name + schema_hash) |
| context meta | `summary_present`, `summary_version`, `recent_history_count`, `memory_keys`, `tool_context_count` | `message_count`, `role_sequence`, `total_char_size`, `total_token_estimate`, `memory_item_count`, `current_user_run_id` |
| raw payload | `raw_input_ref` (blob_id/content_hash/storage_uri/bytes) | `raw_input_blob_relative_path` (相对路径) |
| attempt_index | 无 | 有 |
| current_user_source_cursor | 无 | 有 |

**证据**: `contracts.py:466-560` 定义；`_tool_trace_projection.py:519-544` 构建逻辑。

NEW 增加了 `char_size` / `token_estimate` / `attempt_index` / `current_user_source_cursor` / `role_sequence`，对"模型到底看到了什么上下文"的回答比 OLD 更精确。

---

## Finding 4: iteration_usage 简化，丢失 budget_snapshot

**状态: WARNING**

- OLD `iteration_usage` 包含 `usage` 字典（含 `completion_tokens_details.reasoning_tokens`、`prompt_tokens_details.cached_tokens`）和 `budget_snapshot`（含 `max_context_tokens`、`current_prompt_tokens`、`total_prompt_tokens`、`total_completion_tokens`、`iteration_count`、`compaction_count`、`continuation_count`、`is_over_soft_limit`、`tool_call_budget`、`tool_calls_remaining`）。
- NEW `IterationUsageRecord` 只有 `prompt_tokens` / `completion_tokens` / `total_tokens`。

**影响**: OLD analyzer 的 `_build_context_pressure_runs` 依赖 `budget_snapshot.is_over_soft_limit` / `compaction_count` / `continuation_count` 来检测上下文压力。NEW 丢失了这些字段，无法做上下文压力诊断。

**证据**: OLD `tool_trace.py:1045-1085`；NEW `_tool_trace_jsonl_sink.py:426-474`。

---

## Finding 5: final_response 语义一致

**状态: PASS**

- OLD: `final_response.content` / `degraded` / `filtered` / `finish_reason`
- NEW: `FinalResponseRecord.content` / `degraded` / `filtered` / `finish_reason`

字段完全对齐。NEW 额外增加了 `source_event_position` 和 `idempotency_key`。

**证据**: OLD `tool_trace.py:1087-1134`；NEW `_tool_trace_jsonl_sink.py:477-529`。

---

## Finding 6: provider_protocol_error 替代 sse_protocol_error

**状态: WARNING — 语义偏移**

- OLD: `sse_protocol_error` — 专为 SSE 流式中断设计，携带 `error_type`（如 `tool_call_incomplete`）、`partial_tool_name`、`partial_arguments_ref`（冷存原始载荷）、`request_id`、`attempt`。
- NEW: `provider_protocol_error` — 通用 provider 错误，携带 `error_code`、`message`、`provider_request_id`、`raw_payload_json`（scrub 后内联）。

**影响**:
1. OLD 的 `partial_arguments_ref` 允许 analyzer 读取冷存中的部分 arguments 前缀（`_extract_sse_partial_arguments_excerpt`），用于定位"模型在流式输出到哪一段 arguments 时中断"。NEW 的 `raw_payload_json` 是 scrub 后的内联字符串，语义不同。
2. OLD 的 `error_type` 是结构化的（如 `tool_call_incomplete`），NEW 的 `error_code` 是中性码，analyzer 需要从 `message` 推断。
3. NEW 的 `_scrub_provider_secret` 只在 `provider_protocol_error` 上执行，不误删诊断材料（`scope_token` / `cursor` / `prompt` / `tool result` 不做过滤）。这是正确的。

**证据**: OLD `tool_trace.py:1136-1196`；NEW `_tool_trace_projection.py:418-468`。

---

## Finding 7: truncation -> fetch_more hint 可诊断

**状态: PASS — NEW 更结构化**

- OLD: `tool_call` record 的 `result_fact.truncated` 为 bool，analyzer 需要读冷存 raw payload 才能拿到 `truncation.cursor` / `truncation.scope_token` / `truncation.has_more`。
- NEW: `ToolCallRecord` 直接携带 `truncation_scope_token` / `truncation_cursor` / `truncation_has_more` / `truncation_limit`，无需读冷存。

**证据**: NEW `_tool_trace_jsonl_sink.py:251-283` 定义了 truncation 字段；`_tool_trace_projection.py:265-271` 从 `ToolResultTruncatedData` 提取。

---

## Finding 8: fetch_more scope_token/cursor 足以定位问题

**状态: PASS — NEW 更完整**

- OLD: analyzer 通过读冷存 raw payload + 检查下一个 tool_call 是否为 `fetch_more` 来判断续读情况。
- NEW: `ToolCallRecord` 直接携带 `fetch_more_consumed_cursor` / `fetch_more_next_cursor` / `fetch_more_chunk_size` / `fetch_more_has_more`，以及 `cursor_denial_reason` / `cursor_expired_at_monotonic`。

NEW analyzer `_detect_fetch_more_unknown_cursor` 检测 consumed_cursor 是否在该 run 之前出现过，`_detect_truncation_gaps` 检测 `truncation_has_more=True` 后是否有 fetch_more。这两个检测比 OLD 的"检查下一个 tool_call name"更精确。

**证据**: NEW `analyze_tool_trace_host.py:281-367`。

---

## Finding 9: duplicate tool calls 检测

**状态: PASS**

- OLD: 按 `(run_id, tool_name, stable_json(arguments))` 聚合，count > 1 为重复。
- NEW: 按 `(run_id, tool_name, arguments_json)` 聚合，count > 1 为重复（`analyze_tool_trace_host.py:247-278`）。

语义等价。NEW 额外有 `idempotency_key` 去重，处理 crash replay 场景。

---

## Finding 10: trace integrity — NEW 有 position 检查，无 raw_ref 完整性检查

**状态: WARNING**

- OLD: `_build_trace_integrity_issues` 检查三类问题：
  1. `iteration_context_snapshot.tool_calls` 含空值
  2. `iteration_context_snapshot.tool_calls` 与 `tool_call` 记录数不一致
  3. `iteration_context_snapshot` 缺少 `raw_input_ref`
  4. `tool_call` 缺少 `raw_result_ref`
- NEW: `_detect_position_gaps` 检查同 run 内 `source_event_position` 是否单调不下降。

NEW 的 position 检查是 OLD 没有的增量。但 NEW 没有检查 raw blob 文件是否实际存在。

**影响**: NEW 的 `IterationContextSnapshotRecord` 存储 `raw_input_blob_relative_path` 作为相对路径，但 analyzer 不验证文件是否存在。如果 blob 写入失败（crash between blob write and JSONL write），analyzer 不会报告。

**证据**: OLD `analyze_tool_trace.py:1344-1409`；NEW `analyze_tool_trace_host.py:370-405`。

---

## Finding 11: context pressure 诊断完全缺失

**状态: FAIL — 关键诊断能力丢失** `[已修复]`

> 修复说明：`utils/analyze_tool_trace_host.py` 新增 `_build_context_pressure_runs` / `ContextPressureRun`，在 NEW 字段范围内覆盖 `degraded` / `filtered` / 缺失 `final_response` / `provider_protocol_error` 计数四类信号；`is_over_soft_limit` / `compaction_count` / `continuation_count` 因 NEW `IterationUsageRecord` 不携带 `budget_snapshot`（参见 Finding 4），属于受限子集，已在 analyzer 模块 docstring 与 `ContextPressureRun` docstring 中显式记录为受限项。

OLD `_build_context_pressure_runs` 检测以下信号：
- `is_over_soft_limit`
- `compaction_count > 0`
- `continuation_count > 0`
- `degraded`
- `filtered`
- 无 `final_response` 且无 `sse_protocol_error`

NEW analyzer 无任何等价检测。原因：
1. `IterationUsageRecord` 不携带 `budget_snapshot`（Finding 4）
2. `FinalResponseRecord` 不携带 `degraded` / `filtered` 到 analyzer（虽然 record 字段存在）
3. 无 `context_pressure_runs` 分析函数

**影响**: 无法回答"哪些 run 因为上下文压力导致降级/失败"。

---

## Finding 12: tool-level statistics 完全缺失

**状态: FAIL — 关键诊断能力丢失** `[已修复]`

> 修复说明：`utils/analyze_tool_trace_host.py` 新增 `_summarize_tool_stats` / `ToolStats`，按 `tool_name` 聚合 `call_count` / `success_count` / `success_rate` / `truncation_count` / `truncation_rate` / `median_result_bytes` / `p90_result_bytes` / `top_error_codes`。结果字节数从 NEW `ToolCallRecord.result_value_json` 直接计算 UTF-8 字节长度（NEW 不再保留独立 `result_bytes` 字段，无需冷存读取）。OLD 的 `median_latency_ms` 因 NEW 不携带 latency 字段保持不输出，已在 `ToolStats` docstring 中显式记录。

OLD `_summarize_tool_stats` 提供：
- 每工具 call_count / success_count / success_rate
- truncation_count / truncation_rate
- median_latency_ms / median_result_bytes / p90_result_bytes
- top_error_codes

NEW analyzer 无任何等价聚合。

**影响**: 无法回答"哪个工具最常用、哪个工具最不稳定、哪个工具返回最大"。

---

## Finding 13: failure pattern analysis 完全缺失

**状态: FAIL — 关键诊断能力丢失** `[已修复]`

> 修复说明：`utils/analyze_tool_trace_host.py` 新增两层失败聚合：`_build_failure_patterns` / `FailurePattern` 按 `(tool_name, error_code)` 聚合；`_build_detailed_failure_patterns` / `DetailedFailurePattern` 在前者基础上经 `_classify_error_signature` 从 `failure_message` 文本与 `failure_error` 代码识别 `HTTP_403` / `HTTP_404` / `HTTP_429` / `HTTP_5XX` / `TIMEOUT` / `DNS_ERROR` / `SSL_ERROR` / `URL_BLOCKED` / `VALUE_ERROR` 等签名。OLD 通过 `meta.repair_hint` 等冷存结构字段做更细分类，NEW 仅依据 record 内置文本，签名集合是 OLD 的可决定子集，已在 `_classify_error_signature` docstring 中显式记录边界。

OLD 提供两层失败分析：
1. `_build_failure_patterns`: 按 `(tool_name, error_code)` 聚合
2. `_build_detailed_failure_patterns`: 从冷存 raw payload 提取 `error_signature`（URL_NOT_ALLOWED / URL_BLOCKED_BY_POLICY / TIMEOUT / DNS_ERROR / SSL_ERROR / HTTP_403 / HTTP_404 / HTTP_429 / HTTP_5XX / VALUE_ERROR）

NEW analyzer 无任何等价分析。

**影响**: 无法回答"工具失败的根因分布是什么"。

---

## Finding 14: large payload / large prompt 检测缺失

**状态: WARNING**

OLD `_build_large_payload_calls` 和 `_build_large_prompt_iterations` 使用自适应 P90 阈值检测异常大的结果/输入。

NEW 的 `ToolCallRecord` 不存储 `result_value_json` 的字节数，`IterationContextSnapshotRecord` 不存储 raw input 的字节数。analyzer 无法做大小分析。

**证据**: NEW `_tool_trace_jsonl_sink.py:251-348` 无 bytes 字段。

---

## Finding 15: recommendation engine 完全缺失

**状态: INFO — 不属于 trace record 层面**

OLD analyzer 包含 `_build_recommendations` 函数，基于分析结果自动生成 P0-P2 优化建议。

NEW analyzer 只输出原始诊断数据，无建议生成。

这是 analyzer 功能差异，不影响 trace record 语义正确性。

---

## Finding 16: provider secret scrub 不误删诊断材料

**状态: PASS**

- `_scrub_provider_secret` 只替换 `_PROVIDER_SECRET_KEYS` 中的键（`authorization`, `api_key`, `cookie` 等 9 个）。
- `scope_token` / `cursor` / `prompt` / `tool result` / `messages` 不在列表中，不会被 scrub。
- scrub 只在 `PROVIDER_PROTOCOL_ERROR` 的 `raw_payload` 上执行，不影响 `tool_call` / `iteration_context_snapshot` 等 record。

**证据**: `_tool_trace_jsonl_sink.py:34-46` 定义 key 列表；`_tool_trace_projection.py:435-441` 调用逻辑。

---

## Finding 17: NEW 新增能力（OLD 无）

| 新增能力 | 位置 |
|---------|------|
| `idempotency_key` 行级幂等 | `_tool_trace_jsonl_sink.py:65-100` |
| `source_event_position` EventLog 位置 | 每个 record dataclass |
| `attempt_index` Host attempt 序号 | `IterationContextSnapshotRecord` |
| `current_user_source_cursor` | `IterationContextSnapshotRecord` |
| `cursor_denial_reason` / `cursor_expired_at_monotonic` | `ToolCallRecord` |
| `fetch_more_consumed_cursor` / `fetch_more_next_cursor` / `fetch_more_chunk_size` / `fetch_more_has_more` | `ToolCallRecord` |
| `tool_schema_summaries` (name + schema_hash) | `IterationContextSnapshotRecord` |
| `role_sequence` / `total_char_size` / `total_token_estimate` / `memory_item_count` / `current_user_run_id` | `RunInputContextMeta` |
| `char_size` / `token_estimate` per message | `RunInputMessageSummary` |
| `os.fsync` 每行写入 | `_tool_trace_jsonl_sink.py:170-175` |
| `os.replace` 原子 blob 写入 | `_tool_trace_jsonl_sink.py:204-209` |
| position gap 检测 | `analyze_tool_trace_host.py:370-405` |
| schema_version 校验拒绝混用 | `analyze_tool_trace_host.py:178-197` |

---

## 汇总

| Finding | 状态 | 影响 |
|---------|------|------|
| 1. schema_version 差异明确 | PASS | 无 |
| 2. 配对机制改变无 close() 补偿 | WARNING | 未配对诊断不可见 |
| 3. iteration_context_snapshot 增强 | PASS | 更好的上下文诊断 |
| 4. iteration_usage 丢失 budget_snapshot | WARNING | 上下文压力诊断不可用 |
| 5. final_response 语义一致 | PASS | 无 |
| 6. provider_protocol_error 替代 sse_protocol_error | WARNING | 语义偏移需适配 |
| 7. truncation -> fetch_more 可诊断 | PASS | 更结构化 |
| 8. fetch_more cursor 定位足够 | PASS | 更精确 |
| 9. duplicate tool calls 检测 | PASS | 等价 |
| 10. trace integrity 部分缺失 | WARNING | blob 文件完整性不检查 |
| 11. context pressure 诊断缺失 | **FAIL** `[已修复]` | 关键能力丢失（已在 NEW 字段范围内补齐受限子集） |
| 12. tool-level statistics 缺失 | **FAIL** `[已修复]` | 关键能力丢失（latency 字段不可得，其余已补齐） |
| 13. failure pattern analysis 缺失 | **FAIL** `[已修复]` | 关键能力丢失（已基于 NEW 字段补齐两层签名） |
| 14. large payload 检测缺失 | WARNING | 大小分析不可用 |
| 15. recommendation engine 缺失 | INFO | analyzer 功能差异 |
| 16. secret scrub 不误删 | PASS | 无 |
| 17. NEW 新增能力 | PASS | 增量 |

---

## 建议补齐项（按优先级）

1. **P0**: analyzer 补齐 `context_pressure_runs` — 需要在 `IterationUsageRecord` 中恢复 `budget_snapshot` 或在 `FinalResponseRecord` 中暴露 `degraded` / `filtered` 给 analyzer。
2. **P0**: analyzer 补齐 tool-level statistics — 需要在 `ToolCallRecord` 中增加 `result_bytes` 或在 analyzer 中从 raw payload 读取。
3. **P0**: analyzer 补齐 failure pattern analysis — 需要在 `ToolCallRecord` 中增加 `failure_error` 的结构化细分，或允许 analyzer 读 raw payload。
4. **P1**: 考虑在 trace record 中保留 `RESULT_MISSING` / `REQUEST_MISSING` 语义。
5. **P1**: analyzer 补齐 raw blob 文件存在性检查。
6. **P2**: analyzer 补齐 large payload / large prompt 检测。
