# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`（unstaged + staged diff，不含已提交 plan commits）
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-code-review-mimo.md`
- Included scope: P3-D S1 实现 diff — `_choice_policy.py`、`sse_parser.py`、`non_stream_parser.py`、三个测试文件、`dayu/engine/README.md`、`tests/README.md`、`docs/host/issues-implementation-control.md`
- Excluded scope: 已提交的 P3-D plan commits（`c52519f0`、`e3c008b9` 等）；docs/reviews/ 下的 implementation artifact 和 controller validation 文件（review 产物，非生产代码）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为 review 过程中确认的关键验证点，均无 material defect：

### _choice_policy 校验逻辑与 plan 对齐确认

- `_is_valid_sse_assistant_choice`：`finish_reason` 非 None 即 valid；否则要求 `delta` dict 中至少一个 semantic field（`role`/`content`/`reasoning_content`/`tool_calls`）非 None。empty delta `{}` + 无 finish_reason = 不算 valid assistant choice。usage-only chunk（`choices=[]` + valid usage）返回 `SSEChoiceSelection(choice=None)`。non-zero index 在 `_validate_choice_index` 中 fail closed。multiple valid choices 在主循环末尾 fail closed。均与 plan §S1 Required changes 一致。
- `validate_non_stream_choice`：missing/non-list/empty/multi-choice/choice non-object/non-zero index 均 fail closed。无 usage-only exception（non-stream 无此语义）。与 plan 一致。

### SSE fatal path 发生在 merge 之前确认

- `_handle_chunk_object()`（`sse_parser.py:430-452`）：先调用 `validate_sse_chunk_choices()`，若返回 `ChoicePolicyError` 则进入 `_handle_choice_policy_error()`（设置 `self._terminated = True`），直接 `return`。content/tool state merge 在 `_handle_choice()` 中执行，只有 `isinstance(selection, SSEChoiceSelection) and selection.choice is not None` 时才到达。fatal path 不会泄漏 partial state。usage 处理在 choice 之后，但 fatal 已 return，不会执行。

### non-stream tool_calls 路径 TOOL_CALLS invariant 确认

- `non_stream_parser.py:346-350`：`tool_calls_emitted=True` 时 `done_finish_reason = FinishReason.TOOL_CALLS`，覆盖 provider finish_reason。content path 若无 tool_calls，`validate_non_stream_content_terminal_finish` 确保 finish_reason 非 None；assert 作为最后防线。tool_calls 完整路径的 TOOL_CALLS 推断仍然 adapter-owned。

### content path missing/null finish_reason fail closed 确认

- `validate_non_stream_content_terminal_finish`（`_choice_policy.py:268-305`）：finish_reason 为 None 时，检查 message shape 后返回 `ChoicePolicyError(error_code=NON_STREAM_MISSING_FINISH_REASON_CODE)`。non-stream `_emit_from_dict` 在 content path 收到该 error 后 yield protocol error + Done(ERROR) 并 return。
- SSE `_finalize_success`（`sse_parser.py:686-707`）：`self._finish_reason is None` 且非 tool_calls path 时，yield `RunnerProtocolErrorData(error_code="sse_missing_finish_reason")` + `RunnerDoneData(ERROR)` 并 return。

### bool/int/list/dict/empty/unknown finish_reason 边界确认

- `_resolve_finish_reason`（`_choice_policy.py:341-375`）：`None` → absent；non-string non-null → `FINISH_REASON_NOT_STRING` fatal；`""` → `FINISH_REASON_EMPTY` fatal；unknown string → `FINISH_REASON_UNKNOWN` fatal。覆盖 bool（`True`/`False` 非 str → NOT_STRING）、int（`1` → NOT_STRING）、list（`["stop"]` → NOT_STRING）、dict（`{"kind":"stop"}` → NOT_STRING）、empty string、unknown string（`"safety_stop"`）。测试 `test_stream_and_non_stream_invalid_finish_reason_fail_closed` parametrize 覆盖全部六种非法值。

### SSE cross-chunk conflicting finish_reason 确认

- `validate_sse_chunk_choices`（`_choice_policy.py:174-183`）：`current_finish_reason is not None and finish_result is not None and finish_result is not current_finish_reason` → `SSE_CONFLICTING_FINISH_REASON_CODE` fatal。测试 `test_sse_conflicting_terminal_finish_reason_fail_closed` 验证 length→stop 冲突。

### README 更新合规确认

- `dayu/engine/README.md`：在 Runner 行为 bullet 中新增一条关于 choices/finish_reason fail-closed policy 的说明。不包含未来计划或 S2/S3 内容。符合 `dayu/engine/README.md` Agent 更新约束（已有该 section 记录 OpenAI-compatible Runner 行为）。
- `tests/README.md`：新增 choice policy fail-closed coverage 说明。不包含未来计划。符合 tests/README.md 约束。
- `docs/host/issues-implementation-control.md`：更新 gate state 记录。属控制文档，非 README Agent 更新约束范围。

### 测试覆盖真实 failure path 确认

- `test_stream_and_non_stream_invalid_finish_reason_fails_closed`：6 种非法 finish_reason 值 × stream + non-stream parity。验证 `PROVIDER_PROTOCOL_ERROR` + `Done(ERROR)`，验证无 `RUNNER_CONTENT_COMPLETED`。
- `test_stream_and_non_stream_multi_choice_fail_closed`：stream 双 choice chunk + non-stream 双 choice response。验证 specific error code。
- `test_stream_and_non_stream_explicit_non_zero_index_fail_closed`：index=1 × stream + non-stream。
- `test_sse_empty_delta_plus_one_valid_choice_uses_only_valid_choice`：empty delta 不算 valid，单 valid choice 正常处理。
- `test_sse_conflicting_terminal_finish_reason_fail_closed`：跨 chunk length→stop 冲突。
- `test_sse_content_without_terminal_finish_reason_fail_closed`：content-only 无 finish_reason。
- `test_non_stream_content_missing_or_null_finish_reason_fails_closed`：parametrize `{}` 和 `{"finish_reason": None}`。
- `test_non_stream_empty_or_non_list_choices_error`：parametrize `[]` 和 `{"0": {...}}`。
- `test_sse_non_object_choice_logs_diagnostic`（更新）：choices 内非 object 成员现在 fatal 而非仅 warning。
- 测试验证的是真实协议行为（fail closed、error code、无 content completed 事件），不是适配实现细节。

### 旧模式清除确认

- Source scan `rg -n "unknown_finish_reason|FinishReason\.STOP|finish_reason or FinishReason\.STOP"`：无 `unknown_finish_reason`；无 `finish_reason or FinishReason.STOP` fallback。剩余 `FinishReason.STOP` 命中均为正向映射（`"stop"` → `STOP`）或正向测试断言。
- `_FINISH_REASON_MAP` 已从 `sse_parser.py` 和 `non_stream_parser.py` 移除，仅存在于 `_choice_policy.py`。

## Open Questions

无。

## Residual Risk

- **non-stream message shape 未校验（pre-existing）**：`validate_non_stream_choice` 不检查 choice 内 `message` 字段是否存在或是否为 dict。若 provider 返回 `{"choices": [{"finish_reason": "stop"}]}`（无 message），当前代码走 content path 产出 `RunnerContentCompletedData(content=None, reasoning_content=None)` + `RunnerDoneData(STOP)`。此行为与 S1 前一致（旧代码同样 `.get("message")` 不校验），非 S1 引入的回归。S1 scope 为 choice 和 finish_reason policy，message shape 校验属后续改进空间。
- **SSE missing terminal finish_reason error code 常量位置**：`sse_parser.py` 本地定义 `_MISSING_TERMINAL_FINISH_REASON_CODE = "sse_missing_finish_reason"` 而非从 `_choice_policy.py` 导入。功能正确，但若后续统一 error code 管理可能需迁移。不阻塞 S1。
