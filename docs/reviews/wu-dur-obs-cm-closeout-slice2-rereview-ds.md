# WU-DUR-P01 Slice 2 Fix Re-Review — AgentDS

## Verdict

**pass-with-findings**

三个 accepted findings 均已修复，核心数据流闭合，Engine/Host boundary 保持清洁。存在一个未覆盖测试的 fail-closed 路径和一个 iteration matching 边界场景，不阻塞 Slice 2 接受但应记录为 residual risk。

## 复审范围

- 修复 artifact：`docs/reviews/wu-dur-obs-cm-closeout-slice2-fix-codex.md`
- 裁决 artifact：`docs/reviews/wu-dur-obs-cm-closeout-slice2-code-review-controller-adjudication.md`
- 设计文档：`docs/host/design.md` §§ 13.1, 13.3, 16, 23.1
- 修复触及的 production 文件：`dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `dayu/host/run_input.py`, `dayu/host/durable/schema.py`, `dayu/engine/contracts/engine_events.py`, `dayu/engine/agent.py`
- 修复触及的测试文件：`tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_projection.py`
- 验证：pytest 155 passed, pyright 0 errors

## Accepted Fixes Verification

### S2-F1 — Continuation canonical manifest (blocking → fixed)

**声明**：Engine-internal continuation `iteration_started` 在无匹配 manifest 时，Host ingest 写入 canonical `RUNNER_CALL_INPUT_ASSEMBLED` limited-signal manifest，非 preview-only，不伪造 complete truth。

**证据**：

- `engine_ingest.py:2292-2322` `_append_iteration_started_events`：先查 `_find_runner_call_manifest_event`，若 `None` 则写 `_append_limited_runner_call_manifest_event`（canonical），再追 preview。
- `engine_ingest.py:2324-2369` `_append_limited_runner_call_manifest_event`：构造 `EventClass.CANONICAL_FACT`、`_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED`，写入 manifest payload descriptor，append EventLog。
- `engine_ingest.py:4395-4461` `_limited_runner_call_manifest_body`：diagnostic status=`limited_signal`、reason=`missing_projection_artifact`，message_entries=[]，不内联 full messages / prompts / provider raw。
- 测试 `test_engine_ingest_mapping.py:2016-2094`：断言 manifest event 为 `CANONICAL_FACT`、`validation_status == "limited_signal"`、`diagnostic.reason == "missing_projection_artifact"`，preview payload 中携带 `runner_call_manifest_validation`。

**判定**：已修复。continuation 路径写入 canonical fact，不伪装 complete truth。

### S2-F2 — Tool Trace non-complete diagnostic (medium → fixed)

**声明**：Tool Trace 从 canonical typed diagnostic 读取，非 complete 缺 required diagnostic 时 fail closed（raise `HostDurableError`），不硬编码 `None`。

**证据**：

- `tool_trace.py:596-634` `_runner_call_diagnostic`：若 `status == "complete"` 返回完整字段均为 None 的 summary；否则检查 `diagnostic` 是否为 `Mapping`，若非则 `raise HostDurableError("runner-call diagnostic must be object")`（line 622，fail closed）。
- `tool_trace.py:624-633`：从 diagnostic object 读取 `status`, `reason`, `missing_atom_kind`, `missing_ref_kind`, `missing_ref`, `observed_count`, `expected_count`, `observed_digest`, `expected_digest` — 均为 typed 字段读取，不硬编码 None。
- 测试 `test_tool_trace_projection.py:536-606`：构造 `validation_status == "limited_signal"` 的 canonical payload，断言 Tool Trace hot row 和 cold JSONL 均正确投影所有 diagnostic 字段。

**注意**：fail-closed 路径（line 622 `raise HostDurableError`）未被测试覆盖。见 Finding-1。

**判定**：已修复。diagnostic 从 typed canonical payload 读取，非 complete 缺 diagnostic 时 fail closed。

### S2-F3 — Continuation validation visibility (medium → fixed)

**声明**：continuation validation 通过 canonical manifest event 与 Tool Trace signal 可见，非仅 `EventClass.PREVIEW`。

**证据**：

- 同一测试 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`（line 2016）同时验证：
  - `manifest_event.event_class == EventClass.CANONICAL_FACT`（line 2064）— 非 preview-only。
  - `preview_payload["runner_call_manifest_validation"]["status"] == "limited_signal"`（line 2091）— validation summary 进入 preview 供 observable 使用。
- Tool Trace 测试 `test_tool_trace_projects_limited_runner_call_manifest_diagnostic`（line 536）验证 diagnostic 进入 Tool Trace hot projection 和 cold JSONL。
- `engine_ingest.py:4797-4870` `_runner_call_manifest_validation_summary`：从已存在的 canonical manifest event 读取 validation，供 preview 使用（continuation 路径下 manifest 刚写入，该函数会读到刚写入的 manifest）。

**判定**：已修复。validation 通过 canonical 路径可见，不仅限于 preview。

## Engine/Host Boundary Verification

**验证点**：Engine 无 Host refs/index/source refs；Host limited manifest 不内联完整 messages/provider raw。

**证据**：

- `dayu/engine/contracts/engine_events.py:61-76` `IterationStartedData`：仅含 `iteration_id`, `iteration_index`, `message_count`, `role_sequence_digest`, `runner_input_serializer_schema_version` — 无 Host refs, runner_call_index, manifest ref, source refs。
- `dayu/host/engine_ingest.py:4395-4461` `_limited_runner_call_manifest_body`：`message_entries=[]`（不内联），`source_cursor_refs` 仅从 context durable state 派生，不内联完整 content/prompt/snapshot。
- `dayu/host/run_input.py:3616-3645` `_runner_call_message_entry`（ordinary 路径）：存储 `content_digest`（非 content）、`content_size_bytes`、`source_refs`（ref 非 body）、`projector_metadata_id`。

**判定**：boundary 保持清洁。

## runner_call_index / Manifest Lookup Verification

**验证点**：不把 continuation 误配到 ordinary first manifest；幂等/重复 ingest 合理。

**证据**：

- `engine_ingest.py:4873-4923` `_find_runner_call_manifest_event`：按 `run_id` + `event_type` 扫描全部 manifest events，再按 `attempt_id` + `execution_id` + `_runner_call_manifest_matches_iteration` 匹配。
- `engine_ingest.py:4926-4943` `_runner_call_manifest_matches_iteration`：精确匹配 `iteration_id`，或当 manifest `iteration_id is None` 且 `iteration_index == 0` 时匹配（兼容 ordinary first-call manifest 尚无 iteration_id 的场景）。
- Continuation 路径（iteration_index >= 1）不会落入 `iteration_index == 0` 的 fallback。
- 幂等 reingest：若同一 `iteration_id` 的 manifest 已存在，`_find_runner_call_manifest_event` 返回已有 event，`_append_iteration_started_events` 在 line 2315 判断 `existing is None` 为 False，跳过写入，仅追加 preview。
- `_next_runner_call_index`（line 4735）靠 `COUNT(*)` 现有 manifest events 计算，仅在写新 manifest 时调用，幂等 reingest 不增加计数。

**注意**：若 Engine 在 continuation 场景下 reset iteration_index 为 0（用新的 iteration_id），fallback `iteration_index == 0 AND iteration_id is None` 会命中 ordinary first-call manifest。见 Finding-2。

**判定**：正常路径下正确。边界场景见 Finding-2。

## Findings

### Finding-1 — severity: medium

**文件**：`dayu/host/tool_trace.py:622`

**问题**：`_runner_call_diagnostic` 在非 complete 且 diagnostic 不是 `Mapping` 时 `raise HostDurableError`（fail closed）。该 fail-closed 路径未被测试覆盖。

**证据**：`tests/host/test_tool_trace_projection.py` 中 `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` 仅覆盖 diagnostic 存在且合法的情况；不存在非 complete 且 diagnostic 为 `None` 或非 object 类型的测试用例。

**影响**：该路径若在生产环境触发会导致 HostDurableError 中断 trace projection，但不会破坏 EventLog truth。属于 defensive fail-closed 的未测试路径。

**建议**：后续 slice 或 hardening 轮次补充一个测试用例。

### Finding-2 — severity: low

**文件**：`dayu/host/engine_ingest.py:4943`

**问题**：`_runner_call_manifest_matches_iteration` 的 fallback 规则 `payload_iteration_id is None and iteration_index == 0` 在 Engine continuation 重置 iteration_index 为 0 时可能误配 ordinary first-call manifest。

**证据**：当前 Engine 实现中 continuation 通常递增 iteration_index，该场景在正常操作下不触发。但 `_runner_call_manifest_matches_iteration` 作为独立函数未在测试中验证所有边界组合。

**影响**：仅在 Engine behavior change（如 reset iteration counter for tool-loop continuation）时可能触发。当前不阻塞。

**建议**：后续 slice 将该函数抽取为可测试单元，或增加 boundary test。

## Tests / Pyright

| 检查 | 结果 |
|---|---|
| pytest (5 test modules) | 155 passed in 1.06s |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | clean |

测试覆盖：
- `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`：S2-F1 + S2-F3 核心路径。
- `test_tool_trace_projects_runner_call_manifest_signal`：ordinary complete manifest signal 投影。
- `test_tool_trace_projects_limited_runner_call_manifest_diagnostic`：S2-F2 limited diagnostic 投影。
- 已有 ordinary path 测试（RunInputBuilder manifest、ingest validation 等）继续通过，无回归。

未覆盖（见 Findings）：
- Tool Trace fail-closed 路径（non-complete 缺 diagnostic → HostDurableError）。
- `_runner_call_manifest_matches_iteration` 边界组合的独立单元测试。
- 幂等 reingest 的显式测试用例（当前通过代码逻辑隐式覆盖）。

## README Sync

修复 codex 声明的 README 更新：
- `dayu/host/README.md` — 检查确认包含 canonical limited-signal manifest 与 Tool Trace non-complete diagnostic 的文档。
- `tests/README.md` — 检查确认包含对应覆盖范围说明。
- `dayu/engine/README.md` — 修复 codex 声明无需更新（Engine event boundary 未变），与代码一致。

## Remaining Risks

1. **Engine iteration_index reset 场景**：若 Engine 行为变更导致 continuation iteration_index 重置为 0，`_runner_call_manifest_matches_iteration` 的 fallback 可能误配。当前 Engine 实现不会触发此场景。建议在后续 slice 中加固匹配逻辑（例如要求 ordinary manifest 在 ingest 时回填 iteration_id）。

2. **Tool Trace fail-closed 未测试**（Finding-1）：defensive code path 缺少 test，不影响当前 correctness 但降低 regression protection。

3. **Artifact-store fallback**：continuation manifest body 当前通过 SQLite payload 存储，不涉及大 payload artifact-store 路径。若 future continuation messages 数目极大导致 manifest body 超过 `payload_inline_threshold_bytes`，需触发 artifact-store fallback。当前 bounded summary manifest 不会触发该路径。

## Ready for Controller Adjudication

**yes**
