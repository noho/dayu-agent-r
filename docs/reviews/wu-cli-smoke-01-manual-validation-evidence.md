# WU-CLI-SMOKE-01 Manual Validation Evidence

## Scope

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: manual validation collection
- Date: 2026-07-06
- Evidence source: user-provided terminal transcript and logs under `workspace/tmp/wu-cli-smoke-01-manual/`

## MANUAL-01 Real Provider Prompt

Command:

```bash
dayu-cli --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-manual/prompt.log \
  prompt --label wu-cli-smoke-manual-prompt "请用一句话回答：当前 dayu-cli prompt 是否可以正常调用真实模型？"
```

Observed UI output:

```text
这不是财报分析相关的问题，我无法回答。我的角色是买方分析师，可用工具仅限于公司财报/公告文档检索与分析，不具备关于 dayu-cli 或其模型调用状态的信息。
```

Controller adjudication:

- `MANUAL-01` is accepted for real provider / prompt transport evidence.
- The model response is a business-scope refusal because the prompt asks about `dayu-cli` rather than a financial-report analysis task. That is not a prompt-chain failure.
- `prompt.log` contains real runner traffic with HTTP 200 provider response and terminal `final_answer` ingestion.

## MANUAL-02 Real Interactive Loop And Running-State Ctrl+C

Command:

```bash
dayu-cli --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-manual/interactive.log \
  interactive --label wu-cli-smoke-manual-interactive
```

Observed UI sequence:

```text
dayu> 下载Visa财报
...
HostDurableError
dayu> 下载Visa财报
Interactive: cancel requested
active_cancel_watchdog_closeout
dayu> 下载Visa财报
...
HostDurableError
```

Controller adjudication:

- Interactive entered the input loop and accepted submitted prompts.
- Running-state Ctrl+C behavior is accepted: the UI displayed `Interactive: cancel requested`, and `interactive.log` records `host.local_proxy.cancel_close_requested ... reason=cli_sigint` plus `dispatch.active_cancel_watchdog.tick scanned=1 eligible=1 closed=1`.
- The Agent tool path failed when the model called `start_fins_download`. This is not accepted as final-closeout pass because the user also observed direct `dayu-cli download --ticker V` entering the Fins progress stream.

## Direct Fins Download Comparison

Command:

```bash
dayu-cli download --ticker V
```

Observed UI output:

```text
Fins progress: operation="download" ticker="V" stage="download.preparing" message="下载准备中"
Fins progress: operation="download" ticker="V" stage="download.started" message="下载已开始"
Fins progress: operation="download" ticker="V" document="fil_0001403161-21-000060" stage="download.filing_started" message="开始下载"
^CFins operation cancel requested.
Fins operation already cancelling; local process exiting.
```

Controller adjudication:

- Direct Fins CLI path can start the same ticker download and respond to local cancellation.
- Therefore the interactive Agent failure must not be dismissed as a generic external service outage without further code-path evidence.

## New Blocking Finding

### MANUAL-F01 Agent Fins Awaiting Download Path Fails While Direct Download Starts

- **Observed failing path**: interactive Agent calls `start_fins_download`; `interactive.log` records repeated `tool_name=start_fins_download`, `host.waiting.accept_tool_awaiting.accepted`, followed by `tool_result_accepted ... outcome=failed`.
- **Observed working comparison path**: direct `dayu-cli download --ticker V` starts Fins progress for ticker `V` and reaches `download.filing_started`.
- **Impact**: WU-CLI-SMOKE-01 cannot final-closeout as "dayu-cli core Fins direct / interactive main path usable" until this divergence is explained or fixed.
- **Required next action**: run a narrow root-cause fix gate for the Agent Fins awaiting path. The fix must compare direct Fins direct command flow with Agent `start_fins_download` awaiting flow using direct code and log evidence.

## AgentCodex Investigation Attempt

AgentCodex was dispatched for a manual-validation fix gate. It confirmed partial evidence from durable/log inspection:

- `TOOL_RESULT_ACCEPTED` persisted only `outcome_kind=failed` and did not expose failure detail in the queried EventLog projection.
- The manual workspace `host_wait_records` query returned `0` rows after the run.
- The failing path reached `host.waiting.accept_tool_awaiting.accepted` in logs but did not produce an accepted final closeout for the download tool.

The AgentCodex task did not produce a completed fix artifact or code change before the controller interrupted it for non-convergence. No files were modified. A narrower follow-up fix gate is required.
