# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 Code Review — AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted workspace diff only)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-code-review-ds.md`
- Included scope: `dayu/engine/runners/openai/_choice_policy.py`, `sse_parser.py`, `non_stream_parser.py`, `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`, `test_protocol_error.py`, `test_non_stream_response.py`, `dayu/engine/README.md`, `tests/README.md`, `docs/host/issues-implementation-control.md`（仅 next entry point 单行更新）
- Excluded scope: 已提交的 P3-D plan commits（`c52519f0` 及之前）；`docs/reviews/wu-semantic-ownership-01-p3-d-s1-implementation-codex.md` 与 `docs/reviews/wu-semantic-ownership-01-p3-d-s1-controller-validation.md` 作为参考文档，不作为审阅对象
- Parallel review coverage: 无
- Design source: `docs/host/design.md`, `docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`

## Review Approach

沿以下主链路逐行走读：

1. `_choice_policy.py`：`validate_sse_chunk_choices` → `_validate_choice_index` → `_resolve_finish_reason` → `_validate_sse_delta_shape` → `_is_valid_sse_assistant_choice`；`validate_non_stream_choice`；`validate_non_stream_content_terminal_finish`
2. `sse_parser.py`：`_handle_chunk_object` 中的 validation placement → `_handle_choice_policy_error` → `_handle_choice` → `_finalize_success` 终态分支
3. `non_stream_parser.py`：`_emit_from_dict` 中的 validation placement → `_emit_choice_policy_error` → tool_calls / content 分支 → Done finish_reason 赋值
4. 测试文件：逐测试验证 failure path、boundary conditions、diagnostic_reason/error_code 断言
5. README 更新：逐文件检查 Agent 更新约束合规

同步执行 adversarial failure pass、semantic ownership drift pass、external protocol boundary 检查、branch ordering 检查、parameter effectiveness 检查。

## Findings

### 1-未修复-低-SSE delta 缺失但携带 finish_reason 的错误路径缺少测试

- **入口/函数**: `_validate_sse_delta_shape`
- **文件(行号)**: `dayu/engine/runners/openai/_choice_policy.py:391-393`
- **输入场景**: provider SSE chunk 返回 `{"choices":[{"finish_reason":"stop"}]}` —— finish_reason 存在但 delta 字段完全缺失（不是 `{}`，是 key 不存在）。
- **实际分支**: `delta = choice.get("delta")` → `None`；`finish_reason` 不是 `None` → 进入 `if delta is None: if finish_reason is None: return None` 的 else 分支 → 返回 `ChoicePolicyError(error_code=SSE_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason=_REASON_DELTA_MISSING)`
- **预期行为**: 按 P3-D plan contract decision #1，此场景应 fatal（"SSE choice with finish_reason must contain a delta object"）。当前实现正确。
- **实际行为**: 行为正确，fatal 且不合并 state。
- **直接证据**: `_choice_policy.py:388-396`。覆盖率报告显示 line 391-393 uncovered。
- **影响**: 若某 provider 在 terminal chunk 中只发 `finish_reason` 而无 `delta` 字段，当前实现会 fail closed 而非接受。这是 plan 的明确意图，但缺少直接回归测试。若未来因 provider 兼容需求放宽此约束，可能因缺少测试而被不慎修改。
- **建议改法和验证点**: 新增 SSE parity test，覆盖 `{"choices":[{"finish_reason":"stop"}]}`（delta 字段完全缺失），验证产出 `sse_invalid_choice_shape` 错误码与 `Done(ERROR)`。可与已有的 `test_sse_invalid_finish_reason_fails_closed`（delta 为 `{}`）对照。
- **修复风险（低）**: 仅新增测试，不修改生产代码。
- **严重程度（低）**: 实现行为正确，测试覆盖不足。不阻塞 merge。

### 2-未修复-低-SSE choices 为空数组且无 usage 的错误路径缺少直接测试

- **入口/函数**: `validate_sse_chunk_choices`
- **文件(行号)**: `dayu/engine/runners/openai/_choice_policy.py:144-151`
- **输入场景**: SSE chunk 为 `{"choices": []}` —— choices 是空数组且当前 chunk 无合法 usage。
- **实际分支**: `not choices` → `True`；`has_valid_usage` → `False` → 返回 `ChoicePolicyError(error_code=SSE_MISSING_CHOICES_CODE, diagnostic_reason=_REASON_SSE_CHOICES_EMPTY_WITHOUT_USAGE)`
- **预期行为**: fatal protocol error。与 plan contract decision #1（`choices=[]` 仅在 usage-only chunk 合法）一致。
- **实际行为**: 行为正确。
- **直接证据**: `_choice_policy.py:144-151`，覆盖率报告显示 line 147 uncovered。现有测试 `test_sse_usage_only_chunk_does_not_protocol_error` 覆盖了 `choices=[] + usage` 的合法路径（line 145-146），`test_sse_missing_choices_without_usage_emits_protocol_error` 覆盖了 choices 字段缺失的路径（line 132-137）。空数组无 usage 路径未被命中。
- **影响**: 低。该路径的 fatal 语义已通过相邻测试间接验证，但缺少直接断言。若未来调整 usage-only 豁免逻辑，可能无意中改变此路径行为。
- **建议改法和验证点**: 新增 SSE test，发送 `{"choices": []}`（无 usage），验证产出 `sse_missing_choices` 错误码（diagnostic_reason=`choices_empty_without_usage`）与 `Done(ERROR)`。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 不阻塞 merge。

### 3-未修复-低-non-stream choice 缺少 message 字段且 finish_reason 缺失时的错误码语义可增强

- **入口/函数**: `validate_non_stream_content_terminal_finish`
- **文件(行号)**: `dayu/engine/runners/openai/_choice_policy.py:286-304`
- **输入场景**: 非流式响应 `{"choices": [{"some_garbage": 1}]}` —— choice 通过 response-level policy（是 dict、单 choice、index 合法），但既无 tool_calls 也无 message 且无 finish_reason。
- **实际分支**: finish_reason 为 `None` → 进入 message 检查。`message = choice.get("message")` → `None` → 返回 `ChoicePolicyError(error_code=NON_STREAM_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason=_REASON_NON_STREAM_MESSAGE_MISSING)`
- **预期行为**: 应 fatal。当前实现正确。
- **实际行为**: 行为正确，但错误码 `non_stream_invalid_choice_shape` 相比具体问题（"choice 完全为空：无 finish_reason、无 message、无 tool_calls"）稍有泛化。diagnostic_reason `message_missing` 提供了准确细节，error_code 作为分类标签亦可接受。
- **直接证据**: `_choice_policy.py:289-294`，覆盖率报告显示 line 290, 296 uncovered。
- **影响**: 低。下游通过 error_code 分类时，此场景会被归入 `non_stream_invalid_choice_shape` 而非 `non_stream_missing_finish_reason`。由于两者都是 fatal protocol error 且 diagnostic_reason 区分度足够，实际排查不受影响。
- **建议改法和验证点**: 新增测试覆盖 choice 无 message 且无 finish_reason 的 case，验证 error_code 与 diagnostic_reason。可作为一个 parametrized case 加入 `test_non_stream_content_missing_or_null_finish_reason_fails_closed` 或独立测试。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 不阻塞 merge。

## Open Questions

无。

## Residual Risk

- **SSE 多 chunk 场景的 partial state 泄漏**：当 chunk N-1 的 content delta 已 yield 给下游后，chunk N 触发 choice policy 错误，下游会看到 `RUNNER_CONTENT_DELTA` + `PROVIDER_PROTOCOL_ERROR` + `RUNNER_DONE(ERROR)` 序列。`_finalize_success` 不会执行（`_terminated=True`），不会产出 `RUNNER_CONTENT_COMPLETED`。这是流式协议的固有特性，下游 Agent 必须能从 `RUNNER_DONE(ERROR)` 终态正确判断 run 失败，而非依赖"是否见到 content delta"推断成功。当前 Agent 实现通过 `failure_candidate` 机制处理此场景，风险已由现有 Agent 测试覆盖。
- **Python `isinstance(True, int) == True` 边界**：`_validate_choice_index`（line 326）正确使用 `isinstance(index, bool) or not isinstance(index, int)` 先过滤 bool 再检查 int，`_resolve_finish_reason`（line 356）使用 `not isinstance(raw, str)` 可同时过滤 bool/int/float/list/dict。两个入口的 bool-before-int/subclass 顺序正确。
- **float finish_reason（如 `1.5`）未显式测试**：`test_stream_and_non_stream_invalid_finish_reason_fail_closed` 的 parametrize 覆盖了 `1`（int）和 `True`（bool），未覆盖 `1.5`（float）。float 会命中 `not isinstance(raw, str)` 分支，与 int/bool 同路径。已有同路径测试间接覆盖，风险很低。
- **non-stream tool_calls 路径 finish_reason 缺失场景**：当 provider 返回 tool_calls 但 finish_reason 为 null/缺失时，`validate_non_stream_choice` 返回 `finish_reason=None`，tool_calls 路径绕过 `validate_non_stream_content_terminal_finish`，`done_finish_reason` 硬编码为 `TOOL_CALLS`。逻辑正确，但现有测试 `test_non_stream_tool_calls_emitted` 使用了显式 `"finish_reason": "tool_calls"`，未覆盖 finish_reason 缺失的 tool_calls 路径。
- **assert 语句的可读性**：`non_stream_parser.py:349` 的 `assert finish_reason is not None, "content terminal finish_reason checked"` —— 失败时错误消息指向检查条件本身而非违反的不变量。若此 assert 在生产中被触发，日志消息不够直观。风险极低，因为该 assert 是 `validate_non_stream_content_terminal_finish` 返回 `None` 后的 safety net，逻辑上不可达。

## Review Summary

P3-D S1 实现正确完成了 adapter choice and finish-reason policy 的所有要求：

- **`_choice_policy.py`** 将 SSE 与 non-stream 的 choices/finish_reason 校验收敛到单一私有策略模块，去除了两条路径各自维护的 `_FINISH_REASON_MAP` 重复定义。valid assistant choice 定义与 plan contract decision #1 一致：empty delta + finish_reason 为合法（finish_reason 触发 return True）；empty delta + 无 finish_reason 为非合法；有语义 delta 字段为合法。
- **SSE 路径**：`validate_sse_chunk_choices` 在 `_handle_chunk_object` 中先于 `_handle_choice` 执行，choice policy error 时立即设置 `_terminated=True` 并 return，不会继续处理 usage（`sse_parser.py:450-452` 的 usage 处理在 policy error return 之后）。content/tool state merge 只在 `_handle_choice` 内发生，policy 校验失败时该函数不会被调用。
- **Non-stream 路径**：`validate_non_stream_choice` 在选择 `choices[0]` 前校验 response-level choices；`validate_non_stream_content_terminal_finish` 在 content-only 路径（无 tool_calls）上 fail closed。tool_calls 路径硬编码 `FinishReason.TOOL_CALLS`，不受 provider finish_reason 影响。
- **finish_reason 边界**：bool/int/list/dict/empty string/unknown string 全部 fatal；null/missing 为 absent 不默认 STOP。`_resolve_finish_reason` 的 `not isinstance(raw, str)` 覆盖了所有非字符串类型。
- **READEME 更新**：`dayu/engine/README.md` 单行新增描述当前实现行为，`tests/README.md` 两处修改记录 choice policy fail-closed 测试覆盖。均为当前已实现行为的简洁描述，不包含未来计划或流水账，符合各自 Agent 更新约束。
- **测试**：60 focused tests 全部通过；coverage `sse_parser.py` 86%、`non_stream_parser.py` 89%、`_choice_policy.py` 92%，均超过 80% gate。pyright 0 errors。source scan 无残留 `unknown_finish_reason` 或 `finish_reason or FinishReason.STOP` fallback。
- **Semantic ownership**：adapter 是 provider choices/finish_reason 的唯一校验者与规范化者；downstream Agent/Host 只消费已归一化的 RunnerEvent，无需自行推断 choice policy 或 finish_reason 语义。
- **Scope 合规**：未进入 S2（provider diagnostic 拆分）或 S3（error code typing）。未新增 Host provider diagnostic 行为。

三项 Low 级 finding 均为测试覆盖补充建议，不涉及生产代码缺陷，不阻塞 merge。
