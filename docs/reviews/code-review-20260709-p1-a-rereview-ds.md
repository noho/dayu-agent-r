# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Fix Narrow Re-review — AgentDS

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: code fix re-review
- Reviewer: AgentDS
- Date: 2026-07-09
- Scope: controller accepted findings `P1A-CR-F01` through `P1A-CR-F05` only
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-codex.md`
- Fix validation: `docs/reviews/wu-semantic-ownership-01-p1-a-fix-controller-validation.md`
- Input reviews: `docs/reviews/code-review-20260709-p1-a-mimo.md`, `docs/reviews/code-review-20260709-p1-a-ds.md`

## Verdict

**`pass`**

全部 5 个 controller accepted findings 已闭合。修复未引入新 blocker。80 个受影响测试通过，pyright 0 errors，grep 残留扫描确认无消费者重建旧语义。

---

## Finding Closure Verification

### P1A-CR-F01: Conversation Memory 不再从 envelope/raw outcome 下游重建 accepted evidence

**Status**: closed.

**Evidence** (`dayu/host/memory.py`):

- `accepted_evidence_envelope_from_payload` 与 `accepted_tool_raw_outcome_text_from_payload` 顶层 import 已删除（diff -19）。
- 本地 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 模块级常量已删除（diff -98），替换为局部导入 wrapper `_accepted_evidence_query_unavailable_text()`（line 608-622），文案真源仍为 `dayu.host.accepted_result_projection`。
- `_selected_evidence_text()` 重写：主路径检查 `event.evidence_tool_name is not None and event.evidence_result_text is not None`，使用 projection 字段；缺失时 fail closed 返回 limited-signal 文本 `"工具结果已接受；可读投影字段缺失，未展开原始工具响应。"`（line 1705）。
- 旧 envelope/raw-outcome 降级路径已完全移除，不再从 payload 重建 query/source/result。
- `_accepted_evidence_readable_text()` 新增 `source_text` 参数（line 1698），Memory 输出现在包含来源行。
- `MemoryProjectionEvent` 新增 `evidence_tool_name`、`evidence_result_text`、`evidence_source_text` 字段（line 966-968），由 durable memory consumer 提供。
- `tests/host/test_memory_projection.py` 已更新，覆盖 projection 字段使用与缺失 projection 字段 fail closed 行为。

**Propagation audit**: Conversation Memory 不再有独立 accepted evidence 重建路径。✓

---

### P1A-CR-F02: Compact pipeline unavailable query 文案使用 projection owner

**Status**: closed.

**Evidence** (`dayu/host/compact_pipeline.py`):

- 本地常量 `_UNAVAILABLE_TOOL_QUERY` 已删除（diff -75）。
- 本地常量 `_EVIDENCE_SOURCE_PART_SEPARATOR` 与 `_INTERNAL_EVIDENCE_SOURCE_PREFIXES` 已删除（diff -78--82）。
- `_llm_facing_evidence_source_text()` 与 `_is_internal_evidence_source_part()` 函数已删除（diff -1130--1154）。
- 新增 `from dayu.host.accepted_result_projection import ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`（line 35-37）。
- `_accepted_tool_evidence_content()` 中 `None` fallback 使用 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`（line 1112）；source 直接使用 `block.readable_source_text`（line 1121-1122），不再经过消费者私有 blacklist。
- Import 边界干净：无兼容性 re-export。

**Grep 确认**: `_UNAVAILABLE_TOOL_QUERY`、`_llm_facing_evidence_source_text`、`_is_internal_evidence_source_part` 在整个 `dayu/host/` 下零命中。

---

### P1A-CR-F03: `_arguments_fallback_query` 误导签名/意图已修

**Status**: closed.

**Evidence** (`dayu/host/accepted_result_projection.py`):

- 旧 `_arguments_fallback_query(payload, reason)` 已删除。
- 替换为 `_request_unavailable_query(reason)`（line 549-556），接受单个 `reason` 参数，不暗示可从 payload 降级。
- 函数体委托给 `_limited_query(reason)`，行为不变：request atom 不可用时统一产出 limited-signal query。
- 调用方（`_query_projection` line 489）在 `atoms is None` 时调用 `_request_unavailable_query(reason)`，语义清晰：request atom 不可用 = 无 query 可投影。

**Grep 确认**: `_arguments_fallback_query` 在整个代码库中零命中。

---

### P1A-CR-F04: Projection helper 测试覆盖 accepted plan completion signals

**Status**: closed.

**Evidence** (`tests/host/test_accepted_result_projection.py`, 11 个测试):

| Completion Signal | Test | 行号 |
|---|---|---|
| identity mismatch | `test_projection_identity_mismatch_returns_limited_signal` | 268 |
| wait-resolution priority | `test_projection_wait_resolution_status_takes_priority` | 315 |
| internal source ref filtering | `test_projection_filters_internal_source_refs` | 343 |
| descriptor payload / missing descriptor | `test_projection_reads_descriptor_payload_and_reports_missing_descriptor` | 375 |
| unsafe argument keys | `test_projection_unsafe_argument_keys_return_limited_signal` | 471 |
| raw outcome `result.ok == false` | `test_projection_maps_raw_result_ok_false_and_extracts_details` | 519 |
| result details extraction | `test_projection_maps_raw_result_ok_false_and_extracts_details` | 519 |
| semantic query + completed status | `test_projection_uses_semantic_query_status_result_and_business_source` | 78 |
| arguments fallback + failed status | `test_projection_falls_back_to_arguments_when_semantic_query_is_absent` | 136 |
| missing request atom + cancelled status | `test_projection_missing_request_atom_returns_limited_signal` | 190 |
| governed_error/unknown mapping | `test_projection_maps_governed_error_and_unknown_status` | 222 |

全部测试使用真实 durable store write + read 风格，无 mock-only 捷径。11 passed。

---

### P1A-CR-F05: Cross-consumer equivalence test 已补

**Status**: closed.

**Evidence** (`tests/host/test_accepted_result_projection.py:552-678`):

- `test_same_accepted_result_has_equivalent_consumer_projection` 构造同一 accepted result，验证 Tool Trace、Conversation Memory、RunInputBuilder、CompactMaterial 四个消费者的 query/status/source/result 语义一致。
- 测试使用真实 durable store write + read，写入 request atom、accepted result、current input 三个 facts。
- Consumer 读取边界：
  - **Tool Trace**: 通过 `ToolTraceProjectionConsumer` + `read_tool_trace_hot_row` 读取 hot row，断言 `trace_request["query_text"]`、`trace_result["result_status"]`、`trace_result["result_text"]` 与 projection 一致。
  - **Conversation Memory**: 通过 `_memory_projection_event_from_view` + `build_conversation_memory_snapshot_from_events` 构造 snapshot，验证 memory text 包含 projection query/result/source。
  - **RunInputBuilder**: 调用 `_accepted_tool_evidence_content(evidence_block)`，断言 output 包含 `query=`、`source=`、`result=` 字段值与 projection 一致。
  - **CompactMaterial**: 通过 `build_pre_dispatch_compact_material_view` 构造 view，断言 `readable_query_text`、`readable_source_text`、`text` 与 projection 一致。
- 断言比较 consumer 输出与 projection owner 结果，不重复实现投影规则。

---

## Grep Residual Classification

| 调用 | 文件 | 分类 |
|---|---|---|
| `accepted_evidence_envelope_from_payload` | `evidence.py` | 定义/导出 ✓ |
| `accepted_evidence_envelope_from_payload` | `accepted_result_projection.py` | projection owner 内部使用 ✓ |
| `accepted_evidence_envelope_from_payload` | `durable/memory.py:455` | durable memory producer，为 Conversation Memory 提供 projection 字段 ✓ |
| `accepted_evidence_envelope_from_payload` | `compact_material.py:2260` | compact material producer，读取 envelope 后调用 `project_accepted_tool_result()` ✓ |
| `accepted_evidence_envelope_from_payload` | `run_input.py:3249` | payload 解析 helper，非 evidence 文本重建 ✓ |
| `accepted_tool_raw_outcome_text_from_payload` | `evidence.py` | 定义/导出 ✓ |
| `accepted_tool_raw_outcome_text_from_payload` | `accepted_result_projection.py` | projection owner 内部使用 ✓ |

全部命中均已分类为 projection owner 内部使用或 producer 侧 payload 解析，无 consumer 侧 evidence 重建。

---

## Validation Commands Summary

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_pipeline.py -q` | 80 passed |
| `pyright` | 0 errors, 0 warnings |
| `rg _arguments_fallback_query dayu/host/` | 零命中 |
| `rg _UNAVAILABLE_TOOL_QUERY\|_llm_facing_evidence_source_text\|_is_internal_evidence_source_part dayu/host/` | 零命中 |

---

## Residual Risk

- `_contains_unsafe_argument_key` 仍为 projection owner 内的有界启发式（已知，controller 已 defer）。
- `source_note` 仍为 compaction schema 词汇（已知，controller 已 reject-with-reason）。
- 无本次 fix 引入的新 residual risk。

---

## Conclusion

**`pass`**

P1A-CR-F01 至 P1A-CR-F05 全部闭合。Conversation Memory 不再从 envelope/raw outcome 下游重建 accepted evidence；compact pipeline unavailable query 文案使用 projection owner 单一直源；`_arguments_fallback_query` 已替换为语义清晰的 `_request_unavailable_query`；projection helper 测试覆盖全部 accepted plan completion signals；cross-consumer equivalence test 已补。所有回归验证通过，无新 blocker。
