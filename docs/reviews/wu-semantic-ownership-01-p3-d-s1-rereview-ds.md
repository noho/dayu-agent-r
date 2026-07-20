# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 Code Re-review — AgentDS

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: HEAD（当前未提交 workspace diff）
- Output file: docs/reviews/wu-semantic-ownership-01-p3-d-s1-rereview-ds.md
- Included scope: 当前未提交 S1 diff 中针对 accepted findings 的修复（F01/F02/F03 对应的新增测试），以及是否引入新增 material regression
- Excluded scope: S1 implementation 生产代码（`_choice_policy.py`、`non_stream_parser.py`、`sse_parser.py` 重构）不在本次 re-review 范围内；S2/S3 不在范围内
- Parallel review coverage: 无

## Reference Artifacts

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-codex.md`
- Fix controller validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-controller-validation.md`
- Prior reviews: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-code-review-mimo.md`, `docs/reviews/wu-semantic-ownership-01-p3-d-s1-code-review-ds.md`

## Findings

### P3-D-S1-CR-F01 — SSE finish_reason without delta → 已关闭

- **入口/函数**: `test_sse_finish_reason_without_delta_emits_invalid_choice_shape`（`tests/engine/runners/openai/test_protocol_error.py:744`）
- **文件(行号)**: `tests/engine/runners/openai/test_protocol_error.py:744-769`
- **输入场景**: SSE chunk `{"choices":[{"finish_reason":"stop"}]}` — choice 携带 `finish_reason` 但缺少 `delta` object
- **实际分支**: `validate_sse_chunk_choices()` → `_validate_sse_delta_shape()` → `delta is None and finish_reason is not None` → `ChoicePolicyError(SSE_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason="delta_missing")` → `_handle_choice_policy_error()` → `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`
- **预期行为**: Controller 要求 fail-closed：`sse_invalid_choice_shape`、diagnostic reason `delta_missing`、`Done(ERROR)`、无 `RUNNER_CONTENT_COMPLETED`
- **实际行为**: 断言序列 `[PROVIDER_PROTOCOL_ERROR, RUNNER_DONE]`，`error_code == "sse_invalid_choice_shape"`，`diagnostic["reason"] == "delta_missing"`，`done.finish_reason is FinishReason.ERROR`，`RUNNER_CONTENT_COMPLETED not in event types`
- **直接证据**: `_choice_policy.py:389-396`（`_validate_sse_delta_shape` 中 `delta is None and finish_reason is not None` 分支）→ `sse_parser.py:299-304`（`_feed_json_object` 中 `isinstance(selection, ChoicePolicyError)` → `_handle_choice_policy_error`）
- **影响**: 无 — Finding 已关闭
- **严重程度**: 已关闭

### P3-D-S1-CR-F02 — SSE choices=[] without usage → 已关闭

- **入口/函数**: `test_sse_empty_choices_without_usage_emits_protocol_error`（`tests/engine/runners/openai/test_protocol_error.py:650`）
- **文件(行号)**: `tests/engine/runners/openai/test_protocol_error.py:650-671`
- **输入场景**: SSE chunk `{"choices":[]}` 且无合法 `usage` object
- **实际分支**: `validate_sse_chunk_choices(parsed, has_valid_usage=False)` → `not choices` → `has_valid_usage is False` → `ChoicePolicyError(SSE_MISSING_CHOICES_CODE, diagnostic_reason="choices_empty_without_usage")` → Done(ERROR)
- **预期行为**: Controller 要求 `sse_missing_choices`、diagnostic reason `choices_empty_without_usage`、`Done(ERROR)`
- **实际行为**: 断言 `error_code == "sse_missing_choices"`，`diagnostic["reason"] == "choices_empty_without_usage"`，`done.finish_reason is FinishReason.ERROR`
- **直接证据**: `_choice_policy.py:144-151`（choices 为空且无 usage 的分支）→ `_REASON_SSE_CHOICES_EMPTY_WITHOUT_USAGE`
- **影响**: 无 — Finding 已关闭
- **严重程度**: 已关闭

### P3-D-S1-CR-F03 — Non-stream missing message shape → 已关闭

- **入口/函数**: `test_non_stream_choice_without_message_or_finish_reason_fails_closed`（`tests/engine/runners/openai/test_non_stream_response.py:605`）
- **文件(行号)**: `tests/engine/runners/openai/test_non_stream_response.py:605-627`
- **输入场景**: 非流式 `{"choices":[{}]}` — 单 choice 同时缺少 `message` 与 `finish_reason`
- **实际分支**: `validate_non_stream_choice()` → `NonStreamChoiceSelection(choice={}, finish_reason=None)` → `validate_non_stream_content_terminal_finish(choice={}, finish_reason=None)` → `finish_reason is None and message is None` → `ChoicePolicyError(NON_STREAM_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason="message_missing")` → Done(ERROR)
- **预期行为**: Controller 要求 `non_stream_invalid_choice_shape`、diagnostic reason `message_missing`、`Done(ERROR)`
- **实际行为**: 断言 `error_code == "non_stream_invalid_choice_shape"`，`diagnostic["reason"] == "message_missing"`，`done.finish_reason is FinishReason.ERROR`
- **直接证据**: `_choice_policy.py:289-294`（`_REASON_NON_STREAM_MESSAGE_MISSING` 分支）→ `non_stream_parser.py:305-313`（`_emit_choice_policy_error`）
- **影响**: 无 — Finding 已关闭
- **严重程度**: 已关闭

### 未发现实质性问题

三个 accepted findings 均正确关闭，未引入新增 material regression。

## Test-Only Boundary Verification

Fix artifact（`docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-codex.md`）声明 "本 fix gate 未修改 production 文件"。经核实：

- Fix gate 修改的文件：`tests/engine/runners/openai/test_protocol_error.py`、`tests/engine/runners/openai/test_non_stream_response.py`、fix artifact 自身
- 当前 uncommitted diff 中的 production 文件变更（`_choice_policy.py` 新增、`non_stream_parser.py` / `sse_parser.py` / `dayu/engine/README.md` 修改）均为 S1 implementation gate 的产物，非 fix gate 引入
- Fix 新增的三个测试均聚焦于 accepted findings 对应的代码路径，未修改任何 production 行为
- Test-only boundary 成立 ✓

## S2/S3 边界检查

- `_choice_policy.py` 中的 error code 常量均为 S1 adapter 级私有字符串（如 `sse_invalid_choice_shape`、`non_stream_missing_choices`），非 S3 级 typed Engine error code
- `sse_parser.py` 中的 `sse_missing_finish_reason` 是 parser 级终态不变量错误，属于 S1 范围
- 无 context-overflow provenance（S2）相关变更
- 无 typed Engine error-code contract（S3）相关变更
- S2/S3 未进入 ✓

## Validation Claims 复核

Fix controller validation（`docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-controller-validation.md`）的验证结论均已独立复核：

| Validation | Claim | Re-review Result |
| --- | --- | --- |
| Focused S1 tests | `63 passed` | `63 passed` ✓ |
| OpenAI runner suite | `270 passed` | `270 passed` ✓ |
| Pyright | `0 errors, 0 warnings, 0 informations` | `0 errors, 0 warnings, 0 informations` ✓ |
| `git diff --check` | pass | pass（无输出）✓ |
| `unknown_finish_reason` / `finish_reason or FinishReason.STOP` scan | 无命中 | 无命中 ✓ |
| `_FINISH_REASON_MAP` 仅存在于 `_choice_policy.py` | 已确认 | 仅 `_choice_policy.py:28` 定义 ✓ |

全部验证声明 plausible 且可复现。

## Propagation Audit

三个 accepted findings 对应的语义传播路径：

```text
provider wire response
  → _choice_policy.validate_sse_chunk_choices / validate_non_stream_choice / validate_non_stream_content_terminal_finish
  → ChoicePolicyError (error_code + diagnostic_reason)
  → _handle_choice_policy_error / _emit_choice_policy_error
  → RunnerProtocolErrorData + RunnerDoneData(ERROR)
  → Agent / Host 消费
```

Owner boundary 保持不变。三个新增测试锁定了 owner boundary 上的 fatal cases，未新增 durable state、trace、memory、audit、UI、prompt 或 LLM-facing projection path。S1 implementation 的 propagation audit 仍成立。

## Open Questions

无。

## Residual Risk

无。
