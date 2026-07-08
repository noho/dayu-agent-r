# wu-cli-smoke-01 awaiting resume 真实 smoke 验证

## 结论

Pass。

当前未提交改动在真实 `dayu-cli interactive` 长事务场景下通过验证：Visa 财报下载完成后没有永久停在 `waiting`，wait poller 观察到 ready，Host resolve wait 并创建 `dispatch-resume...`，resume runner input 恢复了 `system + user + assistant tool_call + tool result` 上下文，同一目标 run 内没有第二次调用 `start_fins_download`，也没有出现 `dispatch.worker_events.clean_eof_without_terminal` 误导性诊断。

## 执行环境与命令

- 工作区：`/Users/leo/workspace/dayu-agent-r`
- 独立 base：`workspace/tmp/wu-cli-smoke-01-auto/base`
- 日志：`workspace/tmp/wu-cli-smoke-01-auto/interactive.log`
- Host DB：`workspace/tmp/wu-cli-smoke-01-auto/base/.dayu/host/dayu_host.sqlite3`
- CLI 命令：

```bash
source .venv/bin/activate && dayu-cli interactive --base workspace/tmp/wu-cli-smoke-01-auto/base --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-auto/interactive.log --detail
```

实际 stdin：

- 先发送 `下载Visa财报\n`，终端只回显未提交。
- 再发送 `下载Visa财报\r`，Host 接收并启动目标 run。EventLog 因此记录的 `display_text` 为两行同文；这不影响目标验证，因为该 run 内 `start_fins_download` 仍只请求一次。
- 下载完成后发送 `exit\r`；当前 interactive 将其作为普通用户输入处理并产生一个无关的第二个 run。
- 最后发送 EOF 正常退出 CLI，进程退出码 0。

关键耗时：

- Host ready：2026-07-08 18:06:38 CST。
- 目标 run 接收：2026-07-08 18:07:27 CST。
- `start_fins_download` 进入 waiting：2026-07-08 18:07:31 CST。
- wait ready/resolve：2026-07-08 18:11:03 CST。
- 目标 run succeeded：2026-07-08 18:11:11 CST。
- 目标 run 从接收到成功约 3 分 44 秒；waiting 阶段约 3 分 32 秒。

## stdout 摘要

CLI activity 先显示：

- `Activity: started 运行已接受`
- `Activity: in_progress 运行已开始`
- `Activity: started 调用工具：Start Fins Download tool=Start Fins Download 参数字段数：1`
- `Activity: waiting 等待工具完成：Start Fins Download tool=Start Fins Download 外部工具仍在执行`

下载完成后，CLI 不再停在 waiting，而是输出最终回答并回到 `dayu>`：

- `Visa 财报下载已完成。`
- `发现文档：35 份`
- `成功下载：35 份`
- `写入文档：35 份`
- `跳过：0`
- `拒绝：0`
- `失败：0`

## 关键日志证据

`workspace/tmp/wu-cli-smoke-01-auto/interactive.log` 中目标 run 为 `run-6e67dc4681fb4b6baf3e7e4bd431cf63`。

- line 167：`engine.agent.tool_call_requested ... tool_name=start_fins_download tool_call_id=call_d664cc07ac964d9dac061418`
- line 169：`host.waiting.accept_tool_awaiting.committed ... wait_id=wait-91142b205920563c282fb1bf481164f1dc2579df394d3653f09c84b5e6d5fe62`
- line 1190：`host.wait_poller.observe ... outcome=ready`
- line 1193：`host.waiting.resolve_wait.committed ... dispatch_record_id=dispatch-resume-401dc1c3119a84a6ff2a34108ecbc251afd68c1a0af04c7fe2435793d365c155`
- line 1196：`host.wait_poller.resolve ... outcome=ready resolve_status=updated`
- line 1203：`host.local_proxy.accept ... dispatch_record_id=dispatch-resume-... message_count=4 disable_tools=False`
- line 1253：`dispatch.worker_events.consume_done ... run_terminal_closed=True`

`rg "dispatch.worker_events.clean_eof_without_terminal|valid run_suspended|RUN_SUSPENDED|run_suspended" workspace/tmp/wu-cli-smoke-01-auto/interactive.log` 无命中。

## Host DB 证据

目标 run 终态：

```sql
select run_id, status, created_at, terminal_at
from host_runs
order by created_at;
```

结果摘要：

- `run-6e67dc4681fb4b6baf3e7e4bd431cf63`：`succeeded`，`2026-07-08T10:07:27.959771Z` 到 `2026-07-08T10:11:11.167292Z`。
- `run-1192890c5b9d4b7fad649962d0637343`：`succeeded`，这是输入 `exit` 产生的无关 run。

wait record 终态：

```sql
select wait_id, run_id, attempt_id, status, external_job_id, poll_last_outcome, terminal_at, updated_at
from host_wait_records;
```

结果摘要：

- `wait-91142b205920563c282fb1bf481164f1dc2579df394d3653f09c84b5e6d5fe62`
- `status=resolved`
- `external_job_id=finsobs_9025359ef0dc4f82b0fad27ea919d321`
- `terminal_at=2026-07-08T10:11:03.815095Z`

dispatch 记录：

```sql
select dispatch_record_id, run_id, attempt_id, status, worker_kind, execution_target, created_at, updated_at
from host_attempt_dispatch_records
where run_id='run-6e67dc4681fb4b6baf3e7e4bd431cf63'
order by created_at;
```

结果摘要：

- 初始 dispatch：`dispatch-4248039a113a4b6286c9bdbfa6cd427e`，attempt `attempt-987471b1f4a64fb3813018091adf7dbb`。
- resume dispatch：`dispatch-resume-401dc1c3119a84a6ff2a34108ecbc251afd68c1a0af04c7fe2435793d365c155`，attempt `attempt-resume-401dc1c3119a84a6ff2a34108ecbc251afd68c1a0af04c7fe2435793d365c155`。

resume runner input 组成：

```sql
select json_extract(j.value,'$.index') as idx,
       json_extract(j.value,'$.role') as role,
       json_extract(j.value,'$.content_size_bytes') as content_size,
       json_extract(j.value,'$.provider_tool_calls_digest') as tool_calls_digest
from payload_descriptors d
join host_sqlite_payloads p on p.payload_id=d.sqlite_payload_id,
     json_each(p.payload_json,'$.message_entries') j
where d.payload_ref='payload-runner-call-input-manifest-event-runner-call-input-assembled-7ef8e0fab77370d52fbcd85245916a5e74c030db5204de5eecf3ff544caaaf03'
order by idx;
```

结果摘要：

- idx 0：`system`，content size 10020。
- idx 1：`user`，content size 33。
- idx 2：`assistant`，content size 0，`provider_tool_calls_digest=sha256:6d777fe2acc84992ba5b9f36e4b89067c24c351150ef9771fd5853a93554a095`。
- idx 3：`tool`，content size 319。

这说明 resume input 不是只有 `system/user`，而是恢复了 assistant tool call 与 tool result。

同一目标 run 的 `start_fins_download` 调用次数：

```sql
select count(*) as start_fins_download_requested
from event_log
where run_id='run-6e67dc4681fb4b6baf3e7e4bd431cf63'
  and event_type='TOOL_CALL_REQUESTED'
  and json_extract(payload_json,'$.tool_name')='start_fins_download';
```

结果：`1`。

相关事件链：

- event 27：`TOOL_CALL_REQUESTED start_fins_download call_d664cc07ac964d9dac061418`
- event 28：`TOOL_AWAITING start_fins_download ... wait-91142...`
- event 33：`TOOL_RESULT_ACCEPTED start_fins_download ... wait-91142...`

## Debug log 排障充分性

本次 debug log 足以定位 wait/resume 主链路：包含 wait_id、adapter_key、ready observe、resolve_status、dispatch-resume id、resume worker accept、message_count 和 consume_done 终态。

runner input 的角色明细没有直接逐项打印在 log 中，但 log 给出了 `message_count=4` 和 resume dispatch id；结合 Host DB 的 runner-call manifest payload，可以直接验证角色序列为 `system/user/assistant/tool`。因此“log + Host DB”组合满足排障需要。

## 残余风险

- 本次验证使用真实 SEC 下载和真实 LLM，外部网络、SEC 返回内容和模型输出具有非确定性；本次证据只能证明当前环境下该路径通过。
- 由于 prompt_toolkit 下第一次 LF 未提交，目标 run 的 user prompt 在 EventLog 中显示两行同文；但这未导致第二次工具调用，且不影响 wait/resume 修复点判断。
- `exit` 在当前 interactive 中被当作普通输入处理，产生了一个无关的成功 run；最终使用 EOF 退出 CLI。该行为不是本 gate 的目标问题。
- Host DB 的部分 payload 包含 runner 配置等敏感运行信息；本报告只摘录必要结构化证据，未复制密钥或完整 payload。
