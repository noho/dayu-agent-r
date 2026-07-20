# WU-SEMANTIC-OWNERSHIP-01 P3-E Aggregate Deep Review

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `phaseflow/host-issues-control`
- Base: `5c03bfbc` (P3-E plan base)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-aggregate-deepreview-mimo.md`
- Included scope:
  - S1 (`7c8bc0a8`): Tool result invariant and ToolRuntime LLM-facing hint cleanup
  - S2 (`be4ed91c`): Wait callback typed provider status ref and accepted status projection
  - S3 (`0b92a838`): Fins direct unique RESULT protocol error and docs sync
  - All associated tests, README updates, and controller artifacts as evidence
- Excluded scope:
  - `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`
  - `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
  - Uncommitted control-doc / aggregate-validation bookkeeping (context only)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对各 review focus 点的 evidence-based 走读结论：

### S1 - ToolResult invariant and ToolRuntime hint cleanup

1. **`ToolResultSuccess.__post_init__` / `ToolResultFailure.__post_init__`**: `ok` 判别字段在构造时 fail closed。`cast(Literal[True], False)` 和 `cast(Literal[False], True)` 均被运行时 `ValueError` 拒绝。测试覆盖完整（`tests/contracts/test_tool_result_envelope.py:29-40, 51-69`）。

2. **Governance reason / diagnostic refs 清理**: `_truncation_failure`、`_governed_failure_outcome`、`_accept_failure_outcome`、`_awaiting_accept_failure_outcome` 的 `hint` 参数均已设为 `None`。已删除 `_hint_with_diagnostic_refs`、`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`、`_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR` 及所有截断原因码常量。Source scan 确认无残留引用。

3. **`last_error_code` 诊断保留**: accept timeout / ack-lost 路径的 `last_error_code` 通过 `_accept_timeout_message` 保留在 `message` 中（如 `"tool fact accept ack timed out (last_error_code=ack_lost)"`），同时 Tool Trace diagnostic emitter 记录 `reason_code="accept_timeout"`。测试 `test_accept_timeout_bounded_retry_returns_governed_error` 和 `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` 分别验证了 `message` 包含 `last_error_code` 且 `hint is None`，以及 diagnostics 记录完整。`last_error_code` 不再进入 LLM-facing `hint`。

4. **已删除常量完全清除**: Source scan 确认 `_TRUNCATION_UNSUPPORTED_REASON`、`_TRUNCATION_CURSOR_MISSING_REASON` 等 8 个截断原因码常量、3 个 hint 格式常量在 production 和 tests 中均无残留。

### S2 - Wait callback typed provider status ref and accepted status projection

5. **`provider_status_ref` 裸字符串拒绝**: `_provider_status_ref_from_json` 已删除 `isinstance(raw, str)` 分支；非 `None` 值必须通过 `_require_json_object` 校验。测试 `test_string_provider_status_ref_returns_malformed_payload_without_adapter_call` 验证裸字符串返回 400 `malformed_payload` 且不调用 adapter。`_lost_body` fixture 已更新为 typed object shape。

6. **Accepted status LOST/UNKNOWN 区分**:
   - Payload unavailable（`_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE` 或 `_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE`）→ `LOST`。
   - Payload available 但 typed status 字段缺失/空白/非字符串 → `UNKNOWN` + `accepted_status_unavailable` 诊断。
   - 已删除 `_status_from_raw_outcome`，raw outcome `kind` / `result.ok` 不再重建 status。
   - 测试覆盖：`test_projection_missing_event_payload_maps_lost_with_diagnostic`（LOST）、`test_projection_maps_raw_result_ok_false_and_extracts_details`（raw outcome 不影响 status）、`test_projection_maps_governed_error_and_unknown_status`（governed_error 映射、unknown status 映射）、`test_projection_malformed_optional_payload_text_and_status_handling`（blank status → UNKNOWN）、`test_projection_missing_descriptor_maps_lost`（result payload unavailable → LST）。

7. **`_result_payload` exit 审计**: 函数有三个返回路径：
   - `resolved_payload_available` → 使用 fallback payload。
   - `envelope is None` → 返回 fallback + `accepted_evidence_envelope_missing` 诊断。
   - `HostDurableError` → 返回 `None` + `result_payload_unavailable` 诊断。
   所有 `result_payload=None` 出口均携带 `result_payload_unavailable` 诊断，`_accepted_status` 通过检查该诊断映射 `LOST`。

8. **Consumer propagation**:
   - `read_api._accepted_result_activity_state`: `COMPLETED` → completed, `CANCELLED` → cancelled, 其余（含 `UNKNOWN`）→ failed。Fail-closed，可接受。
   - `compact_material`: 通过 `projection.llm_material` 消费投影，不重建 status。`llm_material is None` 时抛 `HostDurableError`，正确。
   - `evidence.py` / `run_input.py`: 读取 `raw_tool_outcome` 仅用于 result details 抽取，不重建 status。
   - Source scan 确认无 consumer 从 `raw_tool_outcome` 重建 status。

### S3 - Fins direct unique RESULT protocol error

9. **`FinsDirectStreamProtocolError`**: 继承 `ValueError`，携带 typed `reason`（`FinsDirectStreamProtocolErrorKind` enum）、`operation_kind`（`FinsOperationKind` enum）和 `message`。`__init__` 校验 enum 类型和非空 message。导出在 `__all__`。

10. **Runtime drain-until-sentinel**: `_run_direct_stream` 缓冲第一个 `RESULT`，继续 drain 直到 `_DirectStreamProducerDone`。重复 `RESULT` 抛 `DUPLICATE_RESULT`；无 `RESULT` 抛 `MISSING_RESULT`。Producer 的 `finally` 块保证 `_DirectStreamProducerDone` 入队，不会 hang。测试 `test_direct_stream_drains_to_done_before_yielding_result` 验证正常流不 hang。

11. **Service `_ensure_result_event`**: missing/duplicate `RESULT` 均抛 `FinsDirectStreamProtocolError`。已删除 `_missing_result_event` synthetic helper。Source scan 确认无残留。

12. **CLI**: 删除 `FinsDirectStreamContractViolation`；`run_fins_direct_command` catch `FinsDirectStreamProtocolError` 渲染 `exc.message` 并返回 `EXIT_FAILURE`。`_consume_fins_direct_events` 兜底 raise 同一 typed error。测试 `test_direct_stream_protocol_error_surfaces_without_business_result` 验证 CLI 不伪造业务结果。

13. **Producer lifecycle 审计**: `_run_direct_stream_producer` 的 `try/except/finally` 结构保证：正常完成 → `finally` 发送 DONE；异常 → `except` 发送 FAILURE RESULT → `finally` 发送 DONE。所有路径均收敛到 DONE sentinel。Business failure `RESULT`（producer 主动 emit）仍作为正常 terminal event 传递。

### Cross-slice 交互

14. **无跨 slice 回归**: S1 hint 清理不影响 S2 status projection 或 S3 protocol error；S2 status 变更不影响 S1 ToolRuntime 或 S3 Fins stream；S3 protocol error 不影响 S1/S2 的 contract。三个 slice 修改的模块正交。

15. **README 一致性**: `dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md` 均已更新，反映新的 protocol error 语义和 typed provider status ref contract。

## Open Questions

无。

## Residual Risk

- S3 延迟 terminal `RESULT` 直到 producer done sentinel。当前 no-hang 测试通过；未来 producer lifecycle bug 应在 runtime owner 处暴露，不依赖下游 timeout hack。
- `_accepted_result_activity_state` 将 `UNKNOWN` 映射为 `FAILED`（fail-closed）。这是合理默认，但若未来需要区分 "unknown status" 和 "confirmed failure"，需在 read_api owner 处扩展 activity mapping。
- P3-E 不关闭 umbrella WU。后续全仓 deepreview 仍需在 umbrella closeout 前完成。
