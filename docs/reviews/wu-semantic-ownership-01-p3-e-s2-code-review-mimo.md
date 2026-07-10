# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: unstaged workspace diff (S2 implementation)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-code-review-mimo.md`
- Included scope:
  - `dayu/service/wait_callback_endpoint.py`
  - `dayu/host/accepted_result_projection.py`
  - `tests/service/test_wait_callback_endpoint.py`
  - `tests/host/test_accepted_result_projection.py`
  - `tests/host/test_resolve_wait_command.py`
  - `tests/README.md`
- Excluded scope: S1 committed changes (`7c8bc0a8`), S3, unrelated untracked `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`
- Consumer boundary files checked (not modified): `dayu/host/read_api.py`, `dayu/host/run_input.py`, `dayu/host/evidence.py`, `dayu/host/memory.py`, `dayu/host/compact_material.py`

## Findings

未发现实质性问题。

## Verification Detail

### 1. Wait Callback Endpoint: bare-string `provider_status_ref` rejection

- `_provider_status_ref_from_json(...)` (`wait_callback_endpoint.py:542-558`) 已删除 `isinstance(raw, str)` 分支。
- 非 `None` 的 `provider_status_ref` 现在必须经过 `_require_json_object(raw, "provider_status_ref")` (`wait_callback_endpoint.py:553`)，该函数对非 `Mapping` 值抛 `TypeError` (`wait_callback_endpoint.py:652-653`)。
- 调用链 `_completion_envelope_from_request` → `_provider_status_ref_from_json` 的 `TypeError` 被 `handle_wait_callback_completion` 捕获 (`wait_callback_endpoint.py:193`)，返回 `malformed_payload` 400 响应。
- 无 `WaitAdapterKey("callback")` 伪造残留。`rg` 确认生产代码中无 `WaitAdapterKey("callback")` 字符串。
- 测试：`test_string_provider_status_ref_returns_malformed_payload_without_adapter_call` (`test_wait_callback_endpoint.py:304-317`) 正确验证裸字符串返回 `malformed_payload` 且 `adapter.envelopes == []`。
- `_lost_body()` 已改为 typed object shape (`test_wait_callback_endpoint.py:632-636`)。

### 2. Accepted Result Projection: no raw outcome status reconstruction

- `_status_from_raw_outcome(...)` 已完全删除。`rg -rn "_status_from_raw_outcome" dayu tests` 零命中。
- 已删除的 `_FIELD_RESULT`、`_FIELD_KIND`、`_FIELD_OK` 常量无残留引用。`rg -rn "_FIELD_RESULT\b|_FIELD_KIND\b|_FIELD_OK\b" dayu tests` 零命中。
- `_accepted_status(...)` (`accepted_result_projection.py:391-418`) 现在：
  - 先检查 `_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE` 或 `_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE` → 返回 `LOST`（无额外诊断）
  - 尝试 `_payload_status_text(payload, _FIELD_RESOLUTION_KIND)` → 有值时 `_status_from_text()` → `_status_with_unknown_diagnostic()`
  - 尝试 `_payload_status_text(payload, _FIELD_TOOL_FACT_KIND)` → 同上
  - 均无值时 → 返回 `(UNKNOWN, (_DIAGNOSTIC_ACCEPTED_STATUS_UNAVAILABLE,))`
- `_payload_status_text(...)` (`accepted_result_projection.py:441-460`) 对缺失、非字符串、空白值均返回 `None`，不会抛错，正确降级到 `UNKNOWN`。
- `_status_with_unknown_diagnostic(...)` (`accepted_result_projection.py:463-477`) 仅在 `status is UNKNOWN` 时追加 `accepted_status_unavailable` 诊断；已知状态（如 `COMPLETED`、`LOST`）不追加。
- `_status_from_text(...)` (`accepted_result_projection.py:421-438`) 覆盖 `completed`、`failed`、`cancelled`、`governed_error`、`lost`，未知值返回 `UNKNOWN`。

### 3. LOST vs UNKNOWN 语义区分

- **LOST**: payload 不可用（`result_payload_unavailable` 或 `event_payload_unavailable` 诊断存在）。测试覆盖 `result_payload_unavailable` 路径 (`test_accepted_result_projection.py:696-697`)。
- **UNKNOWN**: payload 可用但 typed status 字段缺失、空白、非字符串或值不在已知枚举中。测试覆盖：
  - 空白 status 字段 (`test_accepted_result_projection.py:349-356`)
  - 未知 typed status 值 (`test_accepted_result_projection.py:454-455`)
  - raw `result.ok=false` 无 typed status (`test_accepted_result_projection.py:774-776`)

### 4. Consumer boundary: no raw outcome status reconstruction

- `read_api.py`: `_canonical_tool_result_accepted_activity` (`read_api.py:1226`) 消费 `projection.status`（`AcceptedToolResultStatus` 枚举），通过 `_accepted_result_activity_state(projection.status)` (`read_api.py:1240`) 映射。`_preview_tool_result_accepted_activity` (`read_api.py:1253`) 读取 Host preview payload 的 `outcome_kind` 字段（Host 写入的 typed 字段），非 raw outcome。
- `run_input.py`: `_resume_wait_tool_message_content` (`run_input.py:3556`) 读取 durable payload 的 `result.kind` 字段（Host 写入的 typed result envelope），非 raw outcome。
- `evidence.py`: `raw_tool_outcome` helper 只生成 canonical raw outcome 文本用于 LLM-facing result text，不读取 `kind`/`result.ok` 推断 status。
- `memory.py`: 未命中 `AcceptedToolResultStatus` 或 raw outcome status 重建。
- `compact_material.py`: 消费 `projection.llm_material`；`raw_tool_outcome is missing` 仅是 fail-closed material 路径。
- 以上五个 consumer 文件均未被 S2 修改（`git diff --stat` 确认零变更）。

### 5. Tests quality

- `test_string_provider_status_ref_returns_malformed_payload_without_adapter_call`: 覆盖裸字符串拒绝路径。
- `test_projection_malformed_optional_payload_text_and_status_handling`: 空白 status 不再抛 `HostDurableError`，改为 `UNKNOWN + accepted_status_unavailable`。
- `test_projection_maps_governed_error_and_unknown_status`: 已知 typed status 正确映射，未知值映射 `UNKNOWN + accepted_status_unavailable`。
- `test_projection_maps_raw_result_ok_false_and_extracts_details`: raw `result.ok=false` 不再反推 `FAILED`，改为 `UNKNOWN + accepted_status_unavailable`，但 `result_details_text == "reason=not found"` 仍正确抽取。
- `test_resolve_wait_command.py`: stale assertion `"工具：long_tool"` → `"工具名称：long_tool"` 对齐 evidence renderer (`evidence.py:181`)。

### 6. README changes

- `tests/README.md`: 在 wait callback endpoint 覆盖摘要中加入"裸字符串 `provider_status_ref` 拒绝"。属于该 README 记录测试覆盖范围的职责，变更幅度为一个逗号分隔条目，无越界。

## Open Questions

无。

## Residual Risk

- `event_payload_unavailable` 诊断路径无直接测试覆盖。该诊断由 `_result_event_payload()` 在 EventLog payload 读取 `HostDurableError` 时产生 (`accepted_result_projection.py:278`)，`_accepted_status` 会将其映射为 `LOST`。此为 pre-existing 测试 gap，非 S2 引入。
- `UNKNOWN` 在 Read API activity 映射为 `FAILED` severity（`read_api.py:1297`）。这是现有消费者策略，S2 未改变。若产品层需区分 unknown 与 failed，应作为后续 projection/display policy 变更。
- 外部 callback 调用方仍发送裸字符串 `provider_status_ref` 将收到 `malformed_payload`，符合 S2 fail-closed 要求。

## Conclusion

**PASS**

S2 实现正确满足计划目标：Service callback endpoint 拒绝裸字符串 `provider_status_ref`，accepted result projection 不再从 raw outcome 重建 status，LOST/UNKNOWN 语义区分正确，consumer boundary 无 raw outcome status 重建，测试覆盖关键路径。未发现实质性问题。
