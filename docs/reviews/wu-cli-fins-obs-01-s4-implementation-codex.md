# WU-CLI-FINS-OBS-01 Slice S4 Implementation

## 变更

- `dayu/cli/commands/fins.py`
  - Fins direct command 启动 job 后改为消费 `FinsDirectCommandService.stream_job_events_until_terminal(handle)`。
  - `_wait_for_terminal_handling_sigint` 等待 event-consumer task；第一次 SIGINT 调用 `service.request_cancel(handle.job_id)` 并继续等待 terminal event；第二次 SIGINT 取消本地 event-consumer task、输出本地退出提示并返回 130。
  - CLI 不调用 `read_job_events`，也不再用 `wait_for_terminal` 作为 live command 等待路径。

- `dayu/cli/output.py`
  - 新增 `render_fins_direct_event(...)`。
  - progress/status 输出到 stdout；success terminal 输出到 stdout；failed/cancelled terminal 输出到 stderr。
  - terminal result summary 使用 bounded `key=value` 行输出；渲染侧不展开 raw payload，并对敏感 key、绝对路径形态文本和超长文本做过滤 / 截断。

- `tests/cli/test_fins_commands.py`
  - fake service 改为产出 progress + terminal event stream。
  - 参数化覆盖 `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 六个 live commands 的 progress 和 terminal summary 输出。
  - 覆盖 failed terminal stderr + failure exit、cancelled terminal stderr + 130、第一次 SIGINT durable cancel 后继续等 terminal、第二次 SIGINT 本地退出且 cancel 只请求一次。

- `tests/cli/test_upload_filings_from_command.py`
  - 补充断言确认 `upload_filings_from` 的 stdout script、`--output`、error stderr 路径不出现 Fins live job UI 文本。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q`
  - 通过：`29 passed`
  - 仅有既有 `edgar` deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过。

## README Decision

- 已更新 `tests/README.md`：本次修改触及 `tests/`，且新增 / 迁移了 CLI Fins live event stream 测试覆盖，属于该 README 当前测试分层职责。
- 未更新 `dayu/README.md`：本次 S4 没有改变跨包依赖、分层关系、装配方式或总览级稳定边界。

## Residual Risk

- S4 只实现 CLI event consumer 与 UI print；不包含 S5 的 CLI 日志装配和全 scoped command UI/log audit。
- 事件内容细粒度仍由 S1-S3 已落地的 Service/Fins event stream 决定；S4 不修改 Fins runtime/event schema 或 pipeline stream。
