# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Aggregate Deepreview — AgentMiMo

## Review Target

Base `c1695df6`（R3-A final closeout 后）到当前工作区的全部 R3-B 改动，包括 commits `d1cdfca4` / `791ed144` / `50ed754e` / `1a70fd20` 以及未提交 aggregate validation fix。

## Changed Production Files

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/runners/openai/_choice_policy.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/contracts/tool_schema.py`
- `dayu/runtime/tool_call_projection.py`

## Changed Test / Doc Files

- 12 test files（含新增 `test_tool_call_identity_conflicts.py`、3 个 Host test fixture 迁移、2 个 aggregate validation fix）
- `docs/engine/design.md`、`dayu/engine/README.md`、`tests/README.md`

## Aggregate Review Focus 验证

### 1. RunnerDone commit boundary 全面一致 ✅

路径映射：

| Path | Terminal helper | Cancellation behavior |
| --- | --- | --- |
| Pre-done cancellation（line 828, 865, 899, 1033, 1295, 1306, 1317, 1964, 1985, 2091, 2338, 2373） | `_make_cancelled_terminal_with_close` | 直接收口 `RUN_CANCELLED` |
| Pre-done failure（line 831, 887, 999, 1009, 1324, 1350, 2296, 2361） | `_make_failed_or_cancelled_terminal_with_close` | 检查取消后决定 failed/cancelled |
| Post-done failure（line 905, 964, 2384） | `_make_iteration_failure_terminal` | `runner_done is not None` → 直接 `_make_terminal_failed`，不检查取消 |
| Force-answer pre-done（line 2372-2373） | `runner_done is None` 检查 → `_make_cancelled_terminal_with_close` | Pre-done 取消可抢占 |
| Force-answer post-done failure（line 2384） | `_make_iteration_failure_terminal` | 同 post-done failure |
| Tool-call done（line 1963-1965） | `_make_cancelled_terminal_with_close` | batch-ready/requested 已投影后取消 |
| Exception + no done（line 1350） | `_make_failed_or_cancelled_terminal_with_close` | Pre-done 取消可抢占 |
| Exception + done（line 1324） | `_make_failed_or_cancelled_terminal_with_close` | `_log_runner_call_completed` 只在 `state is None` 时返回 failure，此时 `runner_done` 必为 None |

`_make_iteration_failure_terminal` 实现确认：`runner_done is not None` → `_make_terminal_failed(failure)`；`runner_done is None` → `_make_failed_or_cancelled_terminal_with_close(failure)`。

5 个 post-done 测试覆盖 ordinary final、force-answer final、protocol error、HTTP error、tool-call candidate；2 个 exception/first-candidate 测试覆盖 runner exception 保留首候选和 exception+cancel 竞态。

### 2. EngineEvent/message/AgentRunRequest runtime validation ✅

- `ENGINE_EVENT_TYPE_TO_DATA` + `validate_engine_event_pairing()` + `EngineEvent.__post_init__()`：构造边界校验 type/data pairing。
- `_validate_message_role()` + 四个 message `__post_init__()`：构造边界校验固有 role。
- `AgentRunRequest.__post_init__()`：拒绝联合外 message 实例。
- 生产 `EngineEvent(...)` 构造点只有两处：`agent.py:2691`（`_make_event` 透传）和 `dispatch.py:4208`（`RUN_CANCELLED + RunCancelledData`），均为合法 pairing。
- Host `test_engine_ingest_mapping.py` 3 个旧 negative fixture 迁移到 owner-boundary `ValueError`/`TypeError` expectation；合法 consumer coverage 不变。
- 无 `object.__new__`、无 Host downstream repair。

### 3. OpenAI identity conflict / terminal shape / arguments ✅

**Identity conflict**：
- `_is_tool_call_index()` 检查非 bool 非负 int。
- `_resolve_index()` 统一 index/id/position 三种 routing signal。
- Synthetic→occupied / same-id/two-index / same-index/two-id → `tool_call_identity_conflict` fatal。
- `_move_partial_index()` 只做 index 重映射，删除旧 name/arguments merge。
- `_move_partial_index` 对已 occupied target 抛 `RuntimeError`（防御断言）。

**Terminal shape**：
- `_validate_terminal_shape()` 是唯一 owner：missing/null → fatal；tool calls + non-tool reason → fatal；content + TOOL_CALLS → fatal。
- `validate_sse_terminal_shape()` 和 `validate_non_stream_terminal_shape()` 包装该 helper。
- SSE/non-stream parser 零 `FinishReason.TOOL_CALLS` 直接赋值。

**Arguments**：
- Non-stream `_coerce_final_tool_call()` 删除 `isinstance(arguments, Mapping)` coercion。
- `not isinstance(arguments, str)` → `tool_call_arguments_not_string` fatal。

**Completed-before-error**：terminal shape validation 在 completed event 前执行；identity conflict 在 delta 写入 partial 前返回。

### 4. Schema bounds / typed enum equality / runtime mutable defense ✅

- `ToolParametersSchema.__post_init__()` 递归检查四个 count bounds，bool/非 int → TypeError，负数 → ValueError。
- `_first_invalid_count_bound()` runtime 防御 mutable mapping 篡改。
- `_json_values_equal()` 递归实现：bool ≠ number、finite number equivalence、nested list/object。
- `_validate_enum()` 使用 `any(_json_values_equal(...))`，删除 Python `in`/`not in`。
- Default 和显式参数经同一 `_project_field` → `_validate_enum` 路径。
- Doc/Web/Fins 只读验证通过，未修改业务 schema。

### 5. Documentation sync ✅

- `docs/engine/design.md`：同步 AgentMessage role、EngineEvent validation、RunnerDone commit、first failure candidate、tool-call identity、strict finish、string-only arguments、ToolParametersSchema bounds、runtime enum equality。删除重复 final commit bullet。
- `dayu/engine/README.md`：同步 message/event construction、Runner protocol normalization、RunnerDone commit、first failure candidate、ToolSchema count/enum。
- `tests/README.md`：同步 non-negative bounds、typed enum recursion、mutable defense、EngineEvent/message contract、RunnerDone cancellation ordering、identity-conflict matrix、strict terminal parity、string-only non-stream arguments。
- 各文档更新符合其 Agent 更新约束 / 文档职责边界，未过度。

### 6. Aggregate validation Host test fixes ✅

1. `test_public_steer.py`：新增 `await wait_for_diagnostic_event_type_count(... "ATTEMPT_RUNNING", 1)`。测试同步修复——旧代码在 attempt 未 running 时提交 steer，admission 正确拒绝。无 production 改动。

2. `test_read_api_terminal_policy.py`：将 `sha256:mismatch`（非法格式）改为 `sha256:0000...0000`（合法但错误的 digest），断言从 "payload digest mismatch" 改为 "descriptor digest mismatch"。测试输入修正——旧 digest 格式非法，durable owner 在格式校验阶段就拒绝，未到达测试意图验证的 digest 比较。无 production 改动。

### 7. Source scans ✅

所有 aggregate source scans 结果符合预期：

| Scan | 结果 |
| --- | --- |
| `state.(done_seen\|finish_reason\|provider_request_id)\|or FinishReason.STOP` | 无命中 |
| `state.failure_candidate =` | 仅 line 564（first-candidate helper 唯一赋值） |
| `isinstance(arguments, Mapping)\|json.dumps(dict(arguments))` | 无命中 |
| `done_finish_reason = FinishReason.TOOL_CALLS\|finish = FinishReason.TOOL_CALLS` | 无命中 |
| `FinishReason.TOOL_CALLS` | 仅 `_choice_policy.py:31`（wire mapping）和 `:366`（fail-closed comparison） |
| `source.name + target.name\|source.arguments_buffer + target.arguments_buffer` | 无命中 |
| `value not in enum_value\|value in enum_value` | 无命中 |
| `"(minLength\|maxLength\|minItems\|maxItems)"\s*:\s*-` | 无命中 |
| `hasattr(\|getattr(` | 无命中 |

无新增 compat shim、hasattr/getattr、loose parsing、反向依赖、Any/object 签名或未授权 scope。

## Aggregate Validation

- Default pytest：`4137 passed, 3 skipped, 5 deselected, 3 warnings`
- Pyright：`0 errors, 0 warnings, 0 informations`
- Git diff check：无输出

## Findings

未发现实质性问题。R3-B 三个 slices 的实现在 aggregate view 下全面一致：RunnerDone commit boundary 在所有 path 正确区分 post-done/pre-done；EngineEvent/message validation 在 owner 构造边界；OpenAI identity conflict/terminal shape/arguments 无漏网兼容；schema bounds/enum equality owner-closed；文档同步准确不过度；aggregate validation fix 为 test-only 合理修正。

## Open Questions

无。

## Residual Risks

| Risk | Classification | Owner / destination |
| --- | --- | --- |
| Synthetic delta preview 使用负内部 key | accepted current design | `ToolCallAggregator` |
| `run_agent_and_wait` 对非法 terminal 现在抛 `ValueError` 而非返回 `EngineRunOutcomeFailed` | 行为变更，符合 plan intent | Engine public contract |
| `ToolParametersSchema` 不覆盖 `oneOf`/`pattern`/nested object | accepted design boundary | 未来 schema WU |

## Aggregate Deepreview Conclusion

**status: pass**

R3-B aggregate deepreview 通过。三个 slices 在 aggregate view 下全面一致，无漏网兼容、无下游 repair、无新增 compat shim。Default pytest `4137 passed`，pyright `0 errors`，source scans 全部符合预期。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-aggregate-deepreview-mimo.md`
**findings**: 0
**blocking questions**: 0
