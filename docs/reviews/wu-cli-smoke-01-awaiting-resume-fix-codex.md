# WU CLI smoke 01 awaiting resume fix

## 范围

- Gate：fix / implementation。
- Work unit：CLI smoke / Host awaiting long transaction 行为闭环。
- 目标：修复长事务工具完成后 resume 输入不足导致模型重复启动同一工具的问题，并补足 wait poller / resume 关键链路可观测性。

## Root cause direct evidence

1. 用户复测日志证明 poller / resolve_wait 已经发生，不是“poller 未启动”：
   - `workspace/tmp/wu-cli-smoke-01-manual/interactive.log:1027` 有 `host.command.accepted operation=resolve_wait wait_id=wait-25c86...`。
   - `interactive.log:1029` 有 `host.waiting.resolve_wait.committed ... run_status=running ... dispatch_record_id=dispatch-resume-e2cc...`。
   - `interactive.log:1030` 有 `dispatch.wake_dispatch ... dispatch-resume-e2cc...`。
2. 同一次 resume dispatch 的 Runner 输入投影直接显示 message shape 错误：
   - `interactive.log:1037` 的 local worker accept 显示 `message_count=2`。
   - Host DB `event_log` event `456` 的 `RUNNER_CALL_INPUT_ASSEMBLED` manifest 同样显示 `message_count=2`。
   - 读取 payload `payload-runner-call-input-projection-event-runner-call-input-assembled-a232...` 得到角色序列 `["system", "user"]`，最后一条 user 内容仍是 `下载Visa财报`。
   - 同一 payload 的 system 文本包含旧 `Resume Guidance`、`tool_name=start_fins_download`、`resolution_kind=completed`，但没有 assistant tool-call + tool result 的协议消息。
3. 同源 payload 证明 Host 已经有业务完成结果，但没有以可执行工具协议形态投给模型：
   - DB event `453` 的 `TOOL_RESULT_ACCEPTED` payload 中 `resolution_kind=completed`，`result.value` 为 `operation=download`、`status=success`、`downloaded=35`、`failed=0`、`written documents=35`。
   - 同时旧 `TOOL_AWAITING` event `446` payload 没有 `accepted_arguments`，也没有 arguments digest 字段，RunInputBuilder 无法安全重建原始 assistant tool call。
4. resume 后模型重复启动同一长事务与上述输入形态一致：
   - `interactive.log:1044` resume attempt 开始，仍为 `message_count=2`。
   - `interactive.log:1072` 模型再次请求 `start_fins_download`，新 `tool_call_id=call_0e851...`。
   - `interactive.log:1074` Host 创建第二个 wait `wait-9441...`。
   - Host DB 显示 `wait-25c86...` status=`resolved`，`wait-9441...` status=`failed`，`run-3f814...` status=`failed`。
5. 可观测性次要问题：
   - `interactive.log:1081` 已有 `engine.agent.terminal terminal_type=run_suspended`。
   - 但紧接着 `interactive.log:1084` 出现 `dispatch.worker_events.clean_eof_without_terminal`，`interactive.log:1086` 又显示 lifecycle closeout 被 `terminal_already_closed` 拒绝。
   - 这是已确认 waiting suspension 后 worker stream 没有及时停止导致的误导性 CRITICAL，不是重复启动工具的主因。

## 修改列表

- `dayu/host/waiting.py`、`dayu/host/_event_payload.py`、`dayu/host/tool_runtime.py`
  - `TOOL_AWAITING` payload 新增 `accepted_arguments` 与参数 digest。
  - awaiting candidate 在写入前校验参数 digest 与持久化 payload 一致，避免 resume 时用未验证参数重建工具调用。
- `dayu/host/run_input.py`
  - wait resume 输入从单条 system guidance 改为按模型工具协议重建：
    - 当前用户请求消息；
    - 原始 assistant tool call；
    - 对应 tool result message。
  - 对旧事件缺少原始参数的场景保留自解释中文 fallback，不伪造工具调用。
  - resume continuity 已包含当前用户请求时，不再把同一 user prompt 追加到末尾。
- `dayu/host/engine_ingest.py`
  - 已确认的 waiting event 直接要求 dispatch 停止当前 worker stream，避免 valid `run_suspended` 后被误判为 clean EOF。
  - 未确认 / mismatch waiting event 仍不停止 stream，保持 fail-closed。
- `dayu/host/wait_adapter.py`
  - 新增 verbose 状态链日志：claim、observe outcome、resolve status、poll_once summary。
  - 日志只记录 wait id、adapter key、outcome 类别和计数，不记录工具结果 payload。
- `dayu/host/README.md`、`tests/README.md`
  - 补充 Host resume 输入重建边界与对应测试覆盖说明。
- `tests/host/*`
  - 更新 wait accepted payload 测试、resolve_wait resume 测试、RunInputBuilder resume 投影测试、Engine ingest waiting stream 语义测试和 wait poller 日志测试。

## 测试列表

已执行：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_awaiting_accept.py tests/host/test_engine_ingest_mapping.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py
```

结果：`219 passed`。

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

## 真实验证建议

本轮未运行真实网络 interactive E2E；原因是该路径依赖真实 LLM provider、SEC/Fins 外部网络与用户交互，会下载真实财报并产生工作区状态。最小人工验证命令：

```bash
source .venv/bin/activate
dayu-cli interactive --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-manual/interactive.log
```

输入：

```text
下载Visa财报
```

预期：

- Fins 下载完成后，debug log 能看到 `host.wait_poller.observe ... outcome=ready`、`host.wait_poller.resolve ... resolve_status=updated`、`host.waiting.resolve_wait.committed ... dispatch_record_id=dispatch-resume...`。
- resume dispatch 的 runner input 不再只有 system/user 两条消息；应包含当前 user、assistant tool call、tool result 的恢复上下文。
- 同一次用户请求完成后，模型不应再次调用 `start_fins_download` 来表示同一个已完成下载。
- valid `run_suspended` 后不应再出现误导性的 `dispatch.worker_events.clean_eof_without_terminal`。
- CLI Activity 不应在 Run 已 failed / resolved 后仍只停留在 `waiting`；若模型或工具失败，应展示终态失败原因。

## 残余风险

- 旧库中已存在的 `TOOL_AWAITING` event 没有原始参数，只能走 fallback guidance，无法 retroactively 重建 assistant tool call；这是旧事实缺字段导致的不可恢复边界。
- 本轮验证覆盖了 Host 行为、投影、日志和类型检查，但未覆盖真实 provider 对 assistant tool-call + tool result resume 消息的 E2E 响应差异。
- 当前重建的 assistant tool call 不携带 provider-specific state；OpenAI-compatible 工具协议应可工作，若某 provider 强依赖私有 tool-call state，需要在 runner adapter 层增加明确契约。

## Reviewer

建议需要 reviewer 复核，重点看：

- LLM-facing resume 消息是否足够自解释且不泄漏不必要 Host 内部治理字段。
- 新增 `accepted_arguments` 持久化是否满足后续 schema / payload 演进边界。
- valid waiting event 停止 worker stream 的 dispatch 语义是否覆盖所有现有 Engine event path。
