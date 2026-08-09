# PR 190 interactive `session_summary=null` 真实观察补档

## 观察目的

核对正式 scenario `interactive.interactive.g06.summary-null@1`：已有非空 session summary 时，真实 provider 形成并被 Host 接受的 `session_summary=null` replacement 是否清除旧摘要，同时保留其它 Semantic Memory，并在跨进程重连后继续消费该状态。

本报告只整理既有 F13 production observation 的原始证据，不替用户裁决正确性。

## 运行环境与命令

- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX`
- Provider/model：真实 MiMo，`mimo-v2.5-pro-plan`
- CLI：production `dayu-cli interactive`
- 输入：POSIX PTY
- Workspace：`<run-root>/workspaces/chains/f13-postfix-provenance`
- Label：`f13-postfix-provenance`
- 关键 argv：`dayu-cli interactive --base <workspace> --label f13-postfix-provenance --detail --no-thinking --model mimo-v2.5-pro-plan`
- 关键进程段：
  - `interactive.F13O02-first-compact`
  - `interactive.F13O04-rolling-compact`
  - `interactive.F13O05-reconnect-view`
- 三段进程均 exit 0；terminal 的 canonical/echo/signals 状态在运行前后相同。

## 逐层观察

### 1. 先建立非空摘要

Host SQLite `event_log` sequence 133 记录 `CONTEXT_COMPACTED`。其 accepted replacement 包含：

- 非空 `session_summary`；
- 5 条 `evidence_facts`；
- 1 条 `answer_anchor`；
- 0 条 `forward_intents`；
- 0 条 `reference_continuity`。

摘要内容概括 AAPL FY2025 总净销售额、营业利润及真实 10-K 来源。因此后续 null replacement 的前置条件“已有非空 session summary”成立。

### 2. 真实 provider 返回 null，Host 接受 replacement

`interactive.F13O04-rolling-compact` 中，用户输入“不要调用工具。只触发当前会话整理，不获取新事实。”

Host SQLite sequence 165 记录第二个 `CONTEXT_COMPACTED`。accepted replacement 的 `session_summary` 为 JSON null，同时仍包含：

- 5 条 `evidence_facts`；
- 1 条 `answer_anchor`；
- 0 条 `forward_intents`；
- 0 条 `reference_continuity`。

因此 null 不是“整个 Memory 为空”，而是只清除 session summary；事实和回答锚点仍由同一个 accepted replacement 保留。

### 3. post-compact 主 Run 实际消费

sequence 166 紧接着写入 post-compact `RUNNER_CALL_INPUT_ASSEMBLED`；该 Run 最终在 sequence 177 `RUN_SUCCEEDED`。

sequence 177 的正式 Memory snapshot 计数为：

- `session_summary`: 0
- `evidence_backed_fact`: 5
- `answer_anchor`: 1
- `selected_recent_window`: 2
- 总 item: 8

这证明被清除的是旧摘要，而不是其它 Semantic Memory。

### 4. 跨进程重连

`interactive.F13O05-reconnect-view` 使用相同 workspace、label 和 model 重新启动 interactive。用户要求复述正式 Conversation Memory 中保留的 AAPL 真实证据事实，并说明用户文本 `21.7%` 是否有真实工具证据。

屏幕最终显示：

- AAPL FY2025 Total net sales 416,161、Operating income 133,050 等事实、单位、期间和 SEC 10-K 来源仍可用；
- `21.7%` 被明确标为没有真实工具证据，不能升级为 evidence fact；
- REPL 返回 `dayu>`，进程随后正常 exit 0。

重连没有恢复已被 null replacement 清除的旧 session summary，也没有丢失保留的事实与锚点。

## 证据入口

- `evidence/final-dayu-host.sqlite3`
- `evidence/interactive.F13O02-first-compact/sqlite-after.json`
- `evidence/interactive.F13O04-rolling-compact/{command,terminal,sqlite-before,sqlite-after,tool-trace}.json`
- `evidence/interactive.F13O05-reconnect-view/{command,terminal,sqlite-before,sqlite-after,tool-trace}.json`
- `evidence/execution-index-f13-postfix.json`
- `docs/gateflow/pr-190-f13-s3-validation-and-real-observation-20260806.md`

## 待用户裁决

请裁决以下行为是否正确：当真实 compactor 在已有非空摘要的会话中返回 `session_summary=null` 且 candidate 被 Host 接受时，只清除旧 session summary；其它 accepted Semantic Memory 保留；post-compact Run 与跨进程重连都消费这一同源状态。
