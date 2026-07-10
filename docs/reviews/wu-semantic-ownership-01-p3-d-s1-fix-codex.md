# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 code-review fix - AgentCodex

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S1 - Adapter choice and finish-reason policy`
- Gate: code-review fix
- Agent: AgentCodex
- Scope: 当前未提交的 P3-D S1 diff
- Status: S1 code-review fix complete
- Blocker: none

## Finding Closure

### P3-D-S1-CR-F01

状态：已修复。

闭环：

- 新增 focused SSE 回归测试，覆盖 provider chunk `{"choices":[{"finish_reason":"stop"}]}`。
- 测试断言 fatal `sse_invalid_choice_shape`、diagnostic reason `delta_missing`、`RunnerDoneData(ERROR)`，且没有 `RUNNER_CONTENT_COMPLETED`。
- 未修改生产行为；直接代码证据已表明 `_choice_policy.validate_sse_chunk_choices(...)` 对携带 `finish_reason` 但缺少 `delta` object 的 choice 返回 `sse_invalid_choice_shape`。

### P3-D-S1-CR-F02

状态：已修复。

闭环：

- 新增 focused SSE 回归测试，覆盖无 `usage` 的 `{"choices":[]}`。
- 测试断言 fatal `sse_missing_choices`、diagnostic reason `choices_empty_without_usage`、`RunnerDoneData(ERROR)`。
- 未修改生产行为；直接代码证据已表明 `choices=[]` 仅在 `has_valid_usage=True` 时合法。

### P3-D-S1-CR-F03

状态：已修复。

闭环：

- 新增 focused non-stream 回归测试，覆盖单 choice 同时缺少 `message` 与 `finish_reason`。
- 测试断言 `non_stream_invalid_choice_shape`、diagnostic reason `message_missing`、`RunnerDoneData(ERROR)`。
- 未修改生产行为；直接代码证据已表明 `validate_non_stream_content_terminal_finish(...)` 在该分支返回 `non_stream_invalid_choice_shape` 与 diagnostic reason `message_missing`。

## Exact Files Changed

本 fix gate 修改：

- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-codex.md`

本 fix gate 未修改 production 文件。Controller 指定的无关未跟踪文件未修改、未暂存、未删除、未重命名。

## 验证结果

Focused S1 coverage command：

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov=dayu.engine.runners.openai._choice_policy --cov-report=term-missing -q
```

结果：通过，`63 passed`。

Coverage：

- `dayu/engine/runners/openai/_choice_policy.py`：95%
- `dayu/engine/runners/openai/sse_parser.py`：86%
- `dayu/engine/runners/openai/non_stream_parser.py`：89%
- 本次统计模块 total：89%

OpenAI runner suite：

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai -q
```

结果：通过，`270 passed`。

Pyright：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：通过，`0 errors, 0 warnings, 0 informations`。Pyright 只输出了版本提示。

Whitespace：

```bash
git diff --check
```

结果：通过。

## Source Scan

命令：

```bash
rg -n "unknown_finish_reason|FinishReason\\.STOP|finish_reason or FinishReason\\.STOP" dayu/engine/runners/openai tests/engine/runners/openai
```

结果：无 `unknown_finish_reason` 命中，无 `finish_reason or FinishReason.STOP` 命中。

剩余 `FinishReason.STOP` 命中均符合预期：

- `dayu/engine/runners/openai/_choice_policy.py:29`：显式 provider 字符串 `"stop"` 映射到 `FinishReason.STOP`。
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py:247`：显式 stop 的成功路径断言。
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py:147`、`:154`、`:448`：显式 stop 的 parity / 成功路径断言。
- `tests/engine/runners/openai/test_sse_content_delta.py:52`：SSE stop 成功路径断言。
- `tests/engine/runners/openai/test_protocol_error.py:675`：malformed usage 后继续成功收口的 stop 断言。
- `tests/engine/runners/openai/test_non_stream_response.py:87`、`:133`、`:181`：non-stream stop 成功路径断言。
- `tests/engine/runners/openai/test_sse_done.py:31`：`[DONE]` stop 成功路径断言。
- `tests/engine/runners/openai/test_http_error_event.py:779`：无关 HTTP event flow 的 stop 成功路径断言。

## README Decision

已检查 `tests/README.md`。其更新边界是新增测试层级时同步更新；本 fix 只在现有 `tests/engine/runners/openai/` 层级内新增 focused regression tests，不改变测试层级、运行方式、public behavior 或开发者测试维护规则。因此不需要更新 README。

本 fix gate 未修改 `dayu/engine/` production 文件，因此本 fix 自身不触发 `dayu/engine/README.md` 更新。

## Propagation Audit

语义：provider `choices` shape 与 terminal `finish_reason` fact。

Owner boundary 保持不变：

```text
provider wire response
  -> OpenAI adapter private choice policy
  -> SSE / non-stream parser normalized RunnerEvent
  -> Agent consumes RunnerEvent
  -> EngineEvent projection
  -> Host ingest / EventLog / read models
```

Audit result：

- Producer：provider HTTP/SSE/non-stream response 首次产生 raw `choices`、`delta`、`message`、`finish_reason`。
- Validator / normalizer：OpenAI-compatible Runner adapter 仍是这些 wire facts 的第一且唯一规范化边界。
- 本 fix 对 owner boundary 上的三个 fatal case 增加直接测试：
  - SSE `finish_reason` without `delta` 在任何 content completion 前 fatal。
  - SSE `choices=[]` without valid `usage` fatal。
  - Non-stream choice without both `message` and `finish_reason` fatal。
- 下游 Agent / Host 仍只接收规范化后的 Runner events：成功 data，或 `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`。
- 本 fix 未新增 durable state、trace、memory、audit、UI、prompt、evidence、compact、final-answer 或 LLM-facing projection path。

S1 implementation 的 propagation audit 仍成立。

## Residual Risks

- Fixed in current slice：三个 accepted code-review test coverage gaps。
- Covered by later approved slice S2：non-fatal provider diagnostics 与 context-overflow provenance。
- Covered by later approved slice S3：typed Engine error-code contract。
- Existing accepted behavior：provider 返回多个 choices 或 malformed choice shape 时 fail closed，不做 merge 或任意选择。
- Uncovered area：本 fix 未对 accepted findings 和必做验证命令之外的 S1 implementation 全量 re-review。

S1 code-review fix complete.
