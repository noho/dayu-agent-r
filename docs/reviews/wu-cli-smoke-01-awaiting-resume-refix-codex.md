# WU CLI smoke 01 awaiting resume re-fix

## 范围

- Gate：re-fix。
- Work unit：CLI smoke / Host awaiting long transaction resume 输入闭环。
- 输入 review：
  - `docs/reviews/wu-cli-smoke-01-awaiting-resume-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-awaiting-resume-review-ds.md`

## Findings 闭环

### 1. LLM-facing fallback 文本泄漏 result wrapper

处理方式：已修复。

- `dayu/host/run_input.py:3894-3912` 的 `_resume_wait_fallback_message(...)` 不再 `json.dumps(payload["result"])`，改为复用 `_resume_wait_tool_message_content(...)` 的业务结果投影。
- `_RESUME_GUIDANCE_PREFIX` 已从英文 `Resume guidance:` 替换为中文 `恢复上下文：`。
- fallback 文本只包含工具名、完成状态、业务结果 JSON 和中文恢复说明，不再投影 `kind` / `result` / `ok` 这类 Host/Engine result envelope 字段。

测试：

- `tests/host/test_run_input_builder.py:441-498` 断言 fallback 包含 `工具结果：{"answer": 42}`，且不包含 `Resume guidance`、`"kind"`、`"result"`、`"ok"`、wait/tool/event/payload/digest 等内部引用。

### 2. 旧/异常 event fallback 不应让 resume 整体失败

处理方式：已修复。

- `dayu/host/run_input.py:3915-3952` 的 `_resume_wait_accepted_arguments(...)` 将以下情况安全降级为 `None`，由上层走 fallback guidance：
  - `wait_created_event_ref` 缺失；
  - ref 指向的 event 不存在；
  - ref 指向的 event 不是 `TOOL_AWAITING`；
  - `TOOL_AWAITING` 缺少 `accepted_arguments` 或 `accepted_arguments_source_digest`。
- 同时保留 fail-closed 边界：`accepted_arguments` 字段存在但非 object、source digest 字段存在但非文本、source digest 与 awaiting 原始参数 digest 不一致时仍抛 `HostDurableError`，不吞掉 schema 编码 bug。

测试：

- `tests/host/test_run_input_builder.py:501-557` 覆盖缺 ref、ref 不存在、事件类型不匹配、payload 缺少新 source digest 时降级 fallback。
- `tests/host/test_run_input_builder.py:559-597` 覆盖新字段存在但 digest 不同源时 fail closed。

### 3. accepted_arguments 明文持久化敏感参数风险

处理方式：已修复。

- 新增层中立 helper `dayu/runtime/json_redaction.py:1-58`，递归按 JSON object key 脱敏 `api_key`、`password`、`secret`、`token`，不依赖 Host/Engine/Fins 业务语义。
- `dayu/host/_event_payload.py:26-88` 的 `tool_awaiting_payload(...)` 仍接收原始 accepted arguments，但 EventLog payload 只写入 LLM-safe replay 投影。
- `dayu/host/_event_payload.py:118-129` 的 `_llm_safe_replay_arguments(...)` 对 replay 参数脱敏。
- payload 新增 `accepted_arguments_source_digest`，保存原始参数 digest；`dayu/host/run_input.py:3944-3951` 读取时校验该 digest 与 `TOOL_AWAITING.normalized_arguments_digest` 一致。

边界说明：

- `TOOL_RESULT_ACCEPTED.normalized_arguments_digest` 在 resolve wait 路径当前承载 wait resolution 语义 digest，不是原始参数 digest；re-fix 中没有把它作为参数同源校验依据。参数同源校验回到 `wait_created_event_ref -> TOOL_AWAITING` 的原始参数 digest。
- LLM replay 使用脱敏后的 replay arguments；这足以重建协议闭环，不用于重新执行工具。

测试：

- `tests/host/test_wait_awaiting_accept.py:229-274` 覆盖 `token`、`api_key`、`password`、`client-secret` 原始值不进入 EventLog payload，payload 中只保留 `<redacted>` 和非敏感业务字段。
- `tests/host/test_run_input_builder.py:644-705` 覆盖 resume 重建 assistant tool call 时只使用 LLM-safe replay arguments。

### 4. `_continuity_starts_with_current_user` 隐式结构契约

处理方式：已修复。

- 函数改为 `_continuity_contains_current_user(...)`，见 `dayu/host/run_input.py:3785-3804`。
- docstring 明确 `DurableSessionContinuityProvider` 当前只返回 resume 专用 `user -> assistant(tool_call) -> tool` 消息，不拼接 memory/snapshot 前缀。
- 实现从只检查首条消息改为遍历 continuity 中的 `UserMessage`，未来 provider 组合出现前缀消息时也不会重复追加当前用户输入。

测试：

- 既有 `test_resume_wait_messages_rebuild_tool_result_roundtrip` 与本轮新增异常 fallback 测试继续覆盖 resume continuity 包含当前 user 时不重复尾部追加的主路径。

### 5. 非 dict completed value 的 tool content 投影

处理方式：已核实并补测试，无需修改生产逻辑。

- Engine 普通工具注入路径证据：
  - `dayu/engine/agent.py:376-393` 的 `_project_tool_success_for_llm(...)` 对 Mapping value 透传 object，对非 Mapping value 包为 `{"content": value}`。
  - `dayu/engine/agent.py:2035-2052` 将该投影写入 `ToolMessage.content`。
- Host resume 路径 `dayu/host/run_input.py:3983-3994` 与该格式一致：Mapping value 透传，非 Mapping value 包为 `{"content": value}`。

测试：

- `tests/host/test_run_input_builder.py:600-641` 覆盖 completed value 为字符串时，resume tool message content 为 `{"content": "download finished"}`。

## README 检查

- `dayu/host/README.md` 已更新 resume runner input 边界：使用 LLM-safe replay 参数重建工具调用，并用原始参数 digest 关联 accepted truth。
- `tests/README.md` 已更新 Host 测试覆盖说明：补充 LLM-safe replay 参数、敏感参数不进入 replay payload、旧事件 fallback 与异常引用降级。
- `dayu/README.md` 已更新 runtime 能力列表：补充 JSON 敏感字段脱敏 helper。

## 验证

已执行：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_awaiting_accept.py tests/host/test_engine_ingest_mapping.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py
```

结果：`227 passed`。

已执行：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

已执行：

```bash
git diff --check
```

结果：通过，无输出。

## 残余风险

- 旧库中已存在且没有 `accepted_arguments` / `accepted_arguments_source_digest` 的 `TOOL_AWAITING` fact 仍只能走 fallback guidance，无法 retroactively 重建 assistant tool call；这是旧事实缺字段导致的不可恢复边界。
- LLM-safe replay 参数会脱敏敏感字段，因此 resume protocol 中的 assistant tool call arguments 不一定与原始工具调用逐字一致；它只服务 LLM 上下文闭环，不服务重新执行。
- 本轮仍未运行真实 provider + SEC/Fins 网络 E2E；验证范围为 Host durable facts、RunInputBuilder 投影、wait resolve、Engine ingest、wait adapter/poller 单元与类型检查。
