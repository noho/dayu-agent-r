# WU-ENG-02 Residual Risk Fix Gate

## 范围

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: residual risk fix
- PR: https://github.com/noho/dayu-agent-r/pull/114
- design_doc: `docs/host/design.md`
- plan: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- control_doc: `docs/host/issues-implementation-control.md` 本 gate 未修改

## Residual 判断与处理

### WU-ENG-02-S1-R1 工具超时 RunFailedData 缺少 client_correlation_id

结论：完成。

第一性原理判断：工具超时不是外部 owner 问题。工具 batch 由某次 Runner tool call decision 触发，`_ToolCallsDecision.client_correlation_id` 已经是当前工具批的本地关联 id；terminal closeout 重新构造 `RunFailedData` 时丢字段是同一数据链路内的信息丢失，应在本 PR 修复。

直接证据：

- `dayu/engine/agent.py` 的 `_execute_tool_batch()` 在 `WaitTimedOut` 分支已有 `decision.client_correlation_id`。
- 原 `_make_tool_timeout_terminal_with_close()` 重新创建 `RunFailedData` 时只写 `provider_request_id=None`，未写 `client_correlation_id`。

处理：

- `_make_tool_timeout_terminal_with_close()` 改为显式接收 `client_correlation_id`，并写入 terminal `RunFailedData`。
- `tests/engine/test_agent_phase3_tool_call.py` 直接断言工具超时 terminal `RunFailedData.client_correlation_id` 等于触发该工具批的 Runner request identity。

### WU-ENG-02-S1-R2 force-answer failure EngineEvent 缺直接 client_correlation_id 断言

结论：关闭。

第一性原理判断：代码行为已经存在，不需要 defer。force-answer 是第二次逻辑 Runner 调用，失败 terminal 应关联第二次 request identity；缺口是 focused Engine test 没有直接锁住该事实。

直接证据：

- `_run_force_answer()` 复用 `_run_runner_iteration()`，后者每次 Runner call 都通过 `_next_runner_request_identity()` 生成新的 identity。
- force-answer 空内容和继续工具调用失败路径已从当前 iteration state 取 `client_correlation_id`。

处理：

- `tests/engine/test_agent_phase3_tool_call.py` 补充断言：
  - `force_answer_empty` 的 `RunFailedData.client_correlation_id` 等于第二次 Runner request identity。
  - force-answer 继续 tool call 的 `RunFailedData.client_correlation_id` 等于第二次 Runner request identity。

### WU-ENG-02-S3-R2 ContextRecoveryCloseInput.client_correlation_id 缺专用 validation / payload test

结论：关闭。

第一性原理判断：Context recovery closeout 是 Host durable transition 的直接 payload 写入点，应直接测 durable EventLog payload 和输入校验，而不是通过下游 projection 间接证明。当前生产校验已经存在，不需要改生产代码。

直接证据：

- `ContextRecoveryCloseInput.client_correlation_id` 已存在。
- `_validate_context_recovery_close_input()` 已调用 `_require_optional_non_empty_text(..., field_name="client_correlation_id")`。
- `_context_recovery_attempt_failed_event_request()` 与 `_run_recovering_event_request()` 都把 `client_correlation_id` 写入 payload。

处理：

- `tests/host/test_run_attempt_transitions.py` 新增 focused durable tests：
  - 直接断言 `ATTEMPT_FAILED` 与 `RUN_RECOVERING` payload 写入 `client_correlation_id`。
  - 直接断言空白 `client_correlation_id` 被 `HostDurableError` 拒绝。

### WU-ENG-02-S2-R2 static header conflict ValueError 上层结构化收口

结论：关闭。

第一性原理判断：该冲突是 `RunnerSpec` 自身语义不一致：启用 per-call `OPENAI_X_CLIENT_REQUEST_ID` policy 时，静态 `headers` 不能同时定义大小写不敏感的 `X-Client-Request-Id`。这不需要 Service/config public error taxonomy，也不需要产品决策；应在 Engine contract construction boundary fail fast。Host/config assembly 若构造该 `RunnerSpec`，会提前得到稳定 `ValueError`。

直接证据：

- plan 明确静态 `RunnerSpec.headers` 不应承载动态 per-call id。
- OpenAI runner 原先在发送请求前检查静态 header 冲突，说明冲突语义已经成立，但触发点过晚。

处理：

- `RunnerSpec.__post_init__()` 新增冲突校验：`client_correlation_policy == OPENAI_X_CLIENT_REQUEST_ID` 且静态 headers 含大小写不敏感 `X-Client-Request-Id` 时抛稳定 `ValueError`。
- OpenAI runner 改为复用 `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` 常量，只负责 header 映射，不重复冲突判断。
- `tests/engine/contracts/test_runner_spec.py` 覆盖 RunnerSpec 边界冲突与 policy disabled 时允许静态 header。
- `tests/engine/runners/openai/test_request_identity.py` 同步为 construction-time failure 断言。

### WU-ENG-02-S3-R1 usage observation client_correlation_id

结论：必须 defer。

第一性原理判断：usage observation 是 post-call provider usage / context budget calibration signal，不是 provider-related debugging 主链路的 terminal/protocol/context recovery 关联字段。给 usage observation 增加 `client_correlation_id` 不是补测试或局部 payload 透传，而是扩展 Engine `UsageReportedData` contract，并决定 analyzer 如何解释 usage signal 与 provider request identity 的关系；这属于 WU-OBS-00 / GitHub Issue #70 analyzer contract 范围。

直接证据：

- `dayu/engine/contracts/engine_events.py` 中 `UsageReportedData` 只有 `iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`，没有 `provider_request_id` 或 `client_correlation_id`。
- `dayu/host/engine_ingest.py` 的 usage projection payload 当前写 `"provider_request_id": None`，没有可用的 Engine contract 字段可以同源传入 `client_correlation_id`。
- `docs/host/design.md` 将 usage 定义为 post-call observation，用于估算器校准、diagnostic 与后续治理参考；不得回改当前 dispatch decision。

唯一 defer 理由：需要先扩展 issue-70 analyzer / WU-OBS-00 的 usage signal contract，决定 `UsageReportedData` 是否承载 client correlation 以及 analyzer 如何消费；当前 WU 不应扩大到 analyzer contract。

owner：WU-OBS-00 / GitHub Issue #70 analyzer。

## 变更文件

- `dayu/engine/agent.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/runners/openai/runner.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/contracts/test_runner_spec.py`
- `tests/engine/runners/openai/test_request_identity.py`
- `tests/host/test_run_attempt_transitions.py`
- `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`

未修改：

- `docs/host/issues-implementation-control.md`（工作树中已有总控改动，本 gate 未触碰）
- README 文件
- GitHub PR metadata

## 验证

命令：

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/host/test_run_attempt_transitions.py
```

结果：`125 passed in 0.71s`。

命令：

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

结果：`71 passed in 0.70s`。

命令：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## 完成结论

本 gate 已在当前 PR 内关闭没有硬性 defer 理由的 residuals：S1-R1、S1-R2、S3-R2、S2-R2。S3-R1 保留为必须 defer，唯一理由是需要 WU-OBS-00 / GitHub Issue #70 先裁决并扩展 usage observation / analyzer signal contract。
