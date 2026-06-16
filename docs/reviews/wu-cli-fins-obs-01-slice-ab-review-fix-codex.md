# WU-CLI-FINS-OBS-01 Slice A/B Review Fix

## 范围

- Work unit：`WU-CLI-FINS-OBS-01`
- Slice：A/B merged diff review fix
- Plan 真源：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- Review artifacts：
  - `docs/reviews/code-review-20260616-111036-mimo.md`
  - `docs/reviews/code-review-20260616-111112-ds.md`

## 裁决

### Accepted

- MiMo R1 / R2：SIGINT 取消注入后，如果 direct stream 仍返回 terminal `RESULT`，CLI 不得用本地 cancel summary 覆盖 Service 终态；原测试名没有覆盖真实竞态。
- DS-001：用户可见输出中的 `Fins job summary` 残留旧 job 术语，违反 replacement plan 的 CLI direct 非 durable job 裁决。
- DS-002：`_FinsSigintMonitor` docstring 残留旧 job 术语，应改为 operation 语义。

### Deferred / Not Accepted

- MiMo R3 / DS-003：Service 和 CLI 双重 missing-RESULT fallback 当前作为 defense-in-depth 保留。Service `_ensure_result_event(...)` 是主保证；CLI fallback 只在 Service bug 或非标准 consumer path 中兜底。本 slice 不为低概率兜底扩大 API。
- MiMo R4：`_CliFinsCancellationToken` duck typing 当前满足 Service direct stream 参数边界。后续若 cancellation contract 扩展，再引入显式 Protocol。
- MiMo R5：`ingestion_runtime.py` async generator stub 的 `raise` + unreachable `yield` 是 Python async generator handoff 的必要写法，不修改。

## 修改

- `dayu/cli/commands/fins.py`
  - `_wait_for_terminal_handling_sigint(...)` 在 SIGINT 触发并请求取消后，会等待 `event_task`；如果 stream 返回了 terminal `FinsResultSummary`，直接返回该终态，不再覆盖为本地 cancelled summary。
  - `_FinsSigintMonitor` docstring 从 direct job 改为 direct operation。
- `dayu/cli/output.py`
  - 用户可见 summary 前缀从 `Fins job summary` 改为 `Fins summary`。
- `tests/cli/test_fins_commands.py`
  - 改写 `test_cancel_race_does_not_override_terminal_result`：stream 在取消注入后仍返回 `RESULT(status=SUCCESS)`，测试断言 CLI 返回真实终态。
- `tests/conftest.py`
  - 新增全局测试隔离 fixture，恢复每个测试前的 `dayu` namespace logger 状态，避免 CLI 入口日志装配把 pytest 捕获流 handler 泄漏给后续 `caplog` 测试。
- `tests/README.md`
  - 记录全局 logger 测试隔离 fixture。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py -q`
  - 24 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py`
  - 0 errors，0 warnings。
- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q`
  - 129 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/fins/direct_events.py dayu/service/fins_direct.py dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/cli/output.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py`
  - 0 errors，0 warnings。
- `rg -n "FinsDirectJobHandle|FinsDirectJobEvent|FinsDirectTerminalResult|stream_job_events_until_terminal|request_cancel\\(|Fins job summary|direct job" dayu/cli dayu/service tests/cli tests/service`
  - 生产 direct CLI / Service 路径无旧 durable API 或 `Fins job summary` 残留；README 中旧描述留给 Slice E。
- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_runtime.py -q`
  - 184 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/ tests/ utils/`
  - 0 errors，0 warnings。
- `git diff --check`
  - clean。

## README Impact

- 本 fix 只修 Slice A/B review findings。README 仍按 replacement plan Slice E 集中清理 `dayu/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`、`tests/README.md` 中旧 durable CLI direct 描述。
