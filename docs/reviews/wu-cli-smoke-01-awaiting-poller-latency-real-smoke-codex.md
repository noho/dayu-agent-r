# WU CLI Smoke 01 Awaiting Poller Latency Real Smoke

## 结论

Pass。

真实 `dayu-cli interactive` 路径已验证当前未提交的 awaiting poller latency/idle 修复对两个用户问题有效：

- Fins 美股下载完成到 Host `resolve_wait` 提交约 1 秒，符合 poll cadence；未出现 30/60/120 秒错误退避导致的几十秒或百秒尾延迟。
- `final_answer` / Run terminal 后，超过 10 秒观察窗口内未出现每秒持续的 `claimed=0` 或 `observed=0` 空轮询摘要。
- 同一目标 run 内 `start_fins_download` 请求次数为 1。

## 命令

```bash
source .venv/bin/activate && dayu-cli interactive --base workspace/tmp/wu-cli-smoke-01-poller-latency-real/base --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-poller-latency-real/interactive.log --detail
```

交互输入：

```text
下载Visa财报
```

退出方式：最终回答后观察日志窗口，再用 EOF 退出；未把 `exit` 作为普通输入。

## Stdout 摘要

CLI 进入 awaiting 后显示工具等待状态：

```text
Activity: waiting 等待工具完成：Start Fins Download tool=Start Fins Download 外部工具仍在执行
```

最终回答：

```text
Visa（股票代码：V）的财报下载已完成，共成功下载35份文档。
```

## Log 关键证据

日志文件：`workspace/tmp/wu-cli-smoke-01-poller-latency-real/interactive.log`

关键时间线：

| 事件 | 日志时间 |
| --- | --- |
| `start_fins_download` requested | `2026-07-08 20:12:24` |
| Fins pipeline 美股下载完成 | `2026-07-08 20:14:53` |
| `host.wait_poller.observe outcome=ready` | `2026-07-08 20:14:54` |
| `host.waiting.resolve_wait.committed` | `2026-07-08 20:14:54` |
| `engine.agent.terminal terminal_type=final_answer` | `2026-07-08 20:14:58` |
| `host.engine_ingest ... engine_event_type=final_answer ... terminal_closeout=True` | `2026-07-08 20:14:58` |

直接日志摘录：

```text
[2026-07-08 20:14:53] [INFO] [dayu.fins.FINS.SEC_PIPELINE] 美股下载完成: ticker=V total=35 downloaded=35 skipped=0 rejected=0 failed=0 elapsed_ms=145084
[2026-07-08 20:14:54] [VERBOSE] [dayu.host.wait_adapter] host.wait_poller.observe ... outcome=ready
[2026-07-08 20:14:54] [VERBOSE] [dayu.host.waiting] host.waiting.resolve_wait.committed ... run_status=running ...
[2026-07-08 20:14:58] [VERBOSE] [dayu.engine.agent] engine.agent.terminal ... terminal_type=final_answer
[2026-07-08 20:14:58] [VERBOSE] [dayu.host.engine_ingest] ... engine_event_type=final_answer ... terminal_closeout=True ...
```

延迟判断：

- Fins completion `20:14:53` -> ready observe `20:14:54`：约 1 秒。
- Fins completion `20:14:53` -> resolve committed `20:14:54`：约 1 秒。
- 未见 30/60/120 秒级尾延迟。

空轮询判断：

```bash
rg -n "claimed=0|observed=0" workspace/tmp/wu-cli-smoke-01-poller-latency-real/interactive.log
```

结果：无匹配。`interactive.log` 共 1166 行，`final_answer` 相关日志在 1149-1152 行，后续没有每秒持续的 `host.wait_poller.poll_once.claimed claimed=0` 或 `poll_once.done observed=0`。

工具调用次数：

```bash
rg -c "engine\\.agent\\.tool_call_requested .*tool_name=start_fins_download" workspace/tmp/wu-cli-smoke-01-poller-latency-real/interactive.log
```

结果：`1`。

## DB 关键证据

DB：`workspace/tmp/wu-cli-smoke-01-poller-latency-real/base/.dayu/host/dayu_host.sqlite3`

`host_runs`：

```text
run_id                                status     terminal_at
run-85e3e4ce8bba4124ae6c4379491a4399  succeeded  2026-07-08T12:14:58.601102Z
```

`host_wait_records`：

```text
wait_id                                                                tool_name            external_job_id                           status    terminal_at
wait-e62131ad0766f9ea1db4e56779952c00aa651662af62f7a60ecfd6b794e58ced  start_fins_download  finsobs_f99109204bab4535bef8beb6244596a4  resolved  2026-07-08T12:14:54.002765Z
```

`event_log`：

```text
31  RESUME_REQUESTED       2026-07-08T12:14:54.002765Z
32  TOOL_RESULT_ACCEPTED   2026-07-08T12:14:54.002765Z
84  ATTEMPT_SUCCEEDED      2026-07-08T12:14:58.601102Z
85  RUN_SUCCEEDED          2026-07-08T12:14:58.601102Z
```

`host_tool_trace_hot` 中 `start_fins_download` 仅对应同一个 `tool_call_id=call_3c45625ae1684b628d06b98a` 的 awaiting/result：

```text
27  TOOL_AWAITING         start_fins_download  call_3c45625ae1684b628d06b98a
32  TOOL_RESULT_ACCEPTED  start_fins_download  call_3c45625ae1684b628d06b98a
```

## 残余风险

- 本次是真实 SEC/provider 与真实 LLM runner smoke，只覆盖一次 Visa 下载成功路径；不覆盖 provider 慢响应、失败、取消、并发多 run 等场景。
- 日志时间为本地时间，DB `occurred_at` / `terminal_at` 为 UTC；两者相差 8 小时，事件顺序一致。
- `host_wait_records.poll_last_outcome` 终态行仍显示 `not_ready`，但 wait status 已为 `resolved`，EventLog 已记录 `RESUME_REQUESTED` / `TOOL_RESULT_ACCEPTED`，且日志明确有 `outcome=ready` 与 `resolve_wait.committed`。该字段不影响本次两个用户问题的结论，但可作为后续诊断字段一致性观察项。
