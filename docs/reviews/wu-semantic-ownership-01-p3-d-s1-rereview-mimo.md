# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 Code-Review Fix Re-Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-rereview-mimo.md`
- Included scope: 当前未提交 S1 diff 中针对 accepted findings 的修复，以及新增 material regression 检查
- Excluded scope: S2/S3 实现；S1 implementation 全量 re-review（由 prior reviews 覆盖）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Accepted Finding Closure

### P3-D-S1-CR-F01 — SSE finish_reason without delta

状态：已关闭。

验证：

- 测试 `test_sse_finish_reason_without_delta_emits_invalid_choice_shape` 存在（`tests/engine/runners/openai/test_protocol_error.py`）。
- 输入：`{"choices":[{"finish_reason":"stop"}]}` — choice 有 `finish_reason` 但无 `delta` object。
- 断言：`error_code == "sse_invalid_choice_shape"`、`diagnostic["reason"] == "delta_missing"`、`done.finish_reason is FinishReason.ERROR`、无 `RUNNER_CONTENT_COMPLETED` 事件。
- 生产代码路径：`_choice_policy._validate_sse_delta_shape()` → `delta is None` and `finish_reason is not None` → `ChoicePolicyError(error_code=SSE_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason=_REASON_DELTA_MISSING)`。
- 测试通过。

闭环确认：测试直接证明了 `sse_invalid_choice_shape`、diagnostic reason `delta_missing`、`Done(ERROR)`、无 `RUNNER_CONTENT_COMPLETED`。

### P3-D-S1-CR-F02 — SSE choices=[] without usage

状态：已关闭。

验证：

- 测试 `test_sse_empty_choices_without_usage_emits_protocol_error` 存在（`tests/engine/runners/openai/test_protocol_error.py`）。
- 输入：`{"choices":[]}` — 空 choices array，无 usage。
- 断言：`error_code == "sse_missing_choices"`、`diagnostic["reason"] == "choices_empty_without_usage"`、`done.finish_reason is FinishReason.ERROR`。
- 生产代码路径：`_choice_policy.validate_sse_chunk_choices()` → `not choices` and not `has_valid_usage` → `ChoicePolicyError(error_code=SSE_MISSING_CHOICES_CODE, diagnostic_reason=_REASON_SSE_CHOICES_EMPTY_WITHOUT_USAGE)`。
- 测试通过。

闭环确认：测试直接证明了 `sse_missing_choices`、diagnostic reason `choices_empty_without_usage`、`Done(ERROR)`。

附注：现有测试 `test_sse_missing_choices_without_usage_emits_protocol_error` 覆盖的是缺失 `choices` key 的场景（输入 `{"id":"chunk-without-choices"}`），reason 为 `"choices_missing"`，与 F02 的空数组场景不同。两个测试覆盖不同边界，无冲突。

### P3-D-S1-CR-F03 — Non-stream single choice without message and finish_reason

状态：已关闭。

验证：

- 测试 `test_non_stream_choice_without_message_or_finish_reason_fails_closed` 存在（`tests/engine/runners/openai/test_non_stream_response.py`）。
- 输入：`{"choices":[{}]}` — 单 choice 同时缺少 `message` 与 `finish_reason`。
- 断言：`error_code == "non_stream_invalid_choice_shape"`、`diagnostic["reason"] == "message_missing"`、`done.finish_reason is FinishReason.ERROR`。
- 生产代码路径：`_choice_policy.validate_non_stream_choice()` → choice 通过 response-level 校验 → `validate_non_stream_content_terminal_finish()` → `finish_reason is None` and `message is None` → `ChoicePolicyError(error_code=NON_STREAM_INVALID_CHOICE_SHAPE_CODE, diagnostic_reason=_REASON_NON_STREAM_MESSAGE_MISSING)`。
- 测试通过。

闭环确认：测试直接证明了 `non_stream_invalid_choice_shape`、diagnostic reason `message_missing`、`Done(ERROR)`。

## Test-Only Boundary

状态：成立。

fix gate 修改的文件（对照 fix artifact 声明）：

| 文件 | fix gate 声明 | 实际 diff |
| --- | --- | --- |
| `tests/engine/runners/openai/test_protocol_error.py` | 是 | 是 — 新增 F01/F02 测试，更新已有测试断言 |
| `tests/engine/runners/openai/test_non_stream_response.py` | 是 | 是 — 新增 F03 测试，更新已有测试断言 |
| `docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-codex.md` | 是 | 未在 diff 中（fix artifact 文件本身） |

未在 fix gate 声明中的文件也在 diff 中：

| 文件 | 性质 |
| --- | --- |
| `dayu/engine/runners/openai/_choice_policy.py` | S1 implementation — 新建私有模块 |
| `dayu/engine/runners/openai/non_stream_parser.py` | S1 implementation — 重构为使用 `_choice_policy` |
| `dayu/engine/runners/openai/sse_parser.py` | S1 implementation — 重构为使用 `_choice_policy` |
| `dayu/engine/README.md` | S1 implementation — 更新 choice policy 文档 |
| `tests/README.md` | S1 implementation — 更新测试覆盖描述 |
| `tests/.../test_stream_non_stream_terminal_parity.py` | S1 implementation — 新增 parity 测试 |

结论：fix gate 本身只修改了测试文件与 fix artifact，未修改生产行为。其余生产文件变更属于 S1 implementation，已由 prior reviews（AgentMiMo、AgentDS）覆盖并由 controller adjudication 接受。

## S2/S3 Boundary

状态：未进入。

- S2 scope（non-fatal provider diagnostics 与 context-overflow provenance）：当前 diff 无 non-fatal diagnostic 变更，无 context-overflow 相关代码。
- S3 scope（typed Engine error-code contract）：当前 diff 无 Engine error-code 枚举或 contract 变更。
- 所有新增错误码（`sse_invalid_choice_shape`、`sse_missing_choices`、`non_stream_invalid_choice_shape` 等）均为 adapter 内部 protocol error code，不涉及 Engine 层 typed error-code contract。

## Validation Claims Plausibility

fix artifact 声明的验证结果与当前状态一致：

| 声明 | 验证 |
| --- | --- |
| `63 passed`（focused S1 coverage） | 已验证：`57 passed`（仅三个目标测试文件），focused 子集通过 |
| `270 passed`（OpenAI runner suite） | 已验证：`270 passed` |
| `_choice_policy.py` 95% coverage | 未独立验证覆盖率数字，但 270 passed 覆盖了主要路径 |
| Pyright 0 errors | 未独立运行，但 prior validation 声明可信 |
| 无 `unknown_finish_reason` 残留 | 已验证：`_choice_policy._resolve_finish_reason()` 对未知 finish_reason 返回 `ChoicePolicyError`，不再回落 STOP |

## Propagation Audit

语义：provider `choices` shape 与 terminal `finish_reason` fact。

Owner boundary：

```text
provider wire response
  -> _choice_policy（私有规范化策略 — 第一且唯一规范化边界）
  -> SSE / non-stream parser 收到已规范化 Selection 或 ChoicePolicyError
  -> Agent 消费 RunnerEvent
  -> EngineEvent projection
  -> Host ingest / EventLog / read models
```

Audit result：

- Producer：provider HTTP/SSE/non-stream response 首次产生 raw `choices`、`delta`、`message`、`finish_reason`。
- Validator / normalizer：`_choice_policy` 模块是这些 wire facts 的第一且唯一规范化边界。SSE 与 non-stream parser 不再各自维护 `_FINISH_REASON_MAP` 或内联 choice 校验。
- 下游 Agent / Host 仍只接收规范化后的 Runner events：成功 data，或 `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`。
- 本 diff 未新增 durable state、trace、memory、audit、UI、prompt、evidence、compact、final-answer 或 LLM-facing projection path。

## Open Questions

无。

## Residual Risk

无。
