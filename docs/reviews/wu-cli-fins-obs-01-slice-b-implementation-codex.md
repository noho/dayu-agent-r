# WU-CLI-FINS-OBS-01 Slice B Implementation Report

## 实施范围

- `dayu/cli/commands/fins.py`
  - 用 direct `AsyncIterator[FinsEvent]` consumption 替换旧 `_start_direct_job(...)`、`_wait_for_terminal_handling_sigint(...)` 的 job handle / durable cancel 语义。
  - 六个 direct command 改为调用 `FinsDirectCommandService.download/process/process_filing/process_material/upload_filing/upload_material`。
  - 新增 CLI operation-scoped `_CliFinsCancellationToken`，第一次 SIGINT 设置 token 并取消当前 stream task。
  - 移除 CLI 对 `FinsDirectJobHandle`、`FinsDirectJobEvent`、`FinsDirectTerminalResult`、`stream_job_events_until_terminal(...)`、`request_cancel(job_id)` 的依赖。
  - direct stream 正常结束但无 `RESULT` 时，CLI 渲染 failure result 并返回失败退出码。

- `dayu/cli/output.py`
  - `render_fins_direct_event(...)` 改为接收 `FinsEvent`，基于 `FinsResultSummary` 输出 success / failure / cancelled。
  - 取消提示改为 operation 级文案，不再输出后台 job id 追踪语义。
  - 保留有界文本与绝对路径脱敏 helper。

- `tests/cli/test_fins_commands.py`
  - fake service 改为 direct stream methods，返回 `AsyncIterator[FinsEvent]`。
  - 覆盖六个 direct command、progress 渲染、result 退出码、failure 输出、stream no-result、stream 异常、SIGINT cancellation、cancel race、output redaction、upload file allowlist、`upload_filings_from` 不启动 live stream、CLI 不直接 import Fins storage。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q`
  - 结果：`110 passed`
  - 备注：第三方 `edgar` 依赖产生 3 条 deprecation warning，非本次修改引入。

- `source .venv/bin/activate && pyright dayu/cli/commands/fins.py dayu/cli/output.py dayu/service/fins_direct.py dayu/fins/direct_events.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py`
  - 结果：`0 errors, 0 warnings, 0 informations`

- `source .venv/bin/activate && python -c "import dayu.cli.commands.fins; import dayu.cli.output"`
  - 结果：通过，无输出。

- `git diff --check`
  - 结果：通过，无输出。

## README Impact Assessment

- `tests/README.md`
  - 已检查。Slice B 修改 `tests/cli/test_fins_commands.py`，当前 README 仍描述 Fins direct CLI 的 durable `request_cancel(job_id)`、job id 与 terminal fallback 旧语义。
  - 按 accepted replacement plan，实际 README 同步留给 Slice E；本 Slice 只记录影响。
- `dayu/README.md`
  - 已检查 `Agent更新约束【必须遵守】`。Slice B 改变 CLI direct 用户可见边界，不再输出后台 job id 或 durable cancel 语义；总览文档当前仍包含旧描述。
  - CLI 和 Service 已完成 A/B handoff，但 runtime / awaiting 后续 Slice 尚未完成，因此实际 README closeout 留给 Slice E。
- `dayu/service/README.md`
  - 已在 Slice A assessment 中确认旧 durable direct job 描述需要 Slice E 统一更新；Slice B 未修改 `dayu/service/`。
- `dayu/fins/README.md`
  - 已在 Slice A assessment 中确认 direct runtime 真实实现未落地前不应提前写稳定能力；Slice B 未修改 `dayu/fins/`。

## Residual Risk

- `WU-CLI-FINS-OBS-01-R6`：仍 open。Slice B 只消费 Slice A contract；真实 `dayu.fins` runtime stream implementation 仍留给 Slice C。
- `WU-CLI-FINS-OBS-01-R7`：未触发。本 Slice 未设计或实现 lightweight observation handle。
- `WU-CLI-FINS-OBS-01-R8`：未触发。本 Slice 未实现 observation registry、runtime 并发访问或 blocking bridge。

## 未覆盖项

- `dayu/fins/ingestion_runtime.py` 的真实 direct stream 仍未实现，后续 Slice C 处理。
- tools / wait adapter lightweight observation handle 仍未迁移，后续 D0/D 处理。
- README 实际同步留给 Slice E。
