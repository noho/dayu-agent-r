# WU-CLI-FINS-OBS-01 Slice S3 Implementation - AgentCodex

## Scope

本次只实现 Slice S3：在 `dayu.service.fins_direct` 暴露 reusable async event consumer，使 CLI / GUI / WeChat 可共享 Fins direct job event observation。未修改 CLI、Host、Engine、Fins runtime/event schema、adapter/runner protocol、pipeline stream、线程模型或设计真源。

## Changes

- `dayu/service/fins_direct.py`
  - `FinsDirectIngestionRuntime` protocol 增加 `read_job_events(job_id, *, after_sequence=0, limit=100)`。
  - 新增 `FinsDirectJobEvent`、`FINS_DIRECT_JOB_EVENT_READ_LIMIT`、`FINS_DIRECT_SYNTHETIC_TERMINAL_EVENT_LABEL`。
  - 新增 `FinsDirectCommandService.stream_job_events_until_terminal(handle, *, after_sequence=0)` async iterator：
    - 轮询 `runtime.read_job_events(...)`，按 sequence 游标投影事件。
    - 每条事件补齐 `command_name` 与 `ticker`。
    - terminal job event 通过 `read_job()` 读取 job record 并附带 `FinsDirectTerminalResult` 后停止。
    - empty read 后先按 `poll_interval_seconds` sleep，再读取 job record 判断 terminal fallback，避免 tight loop。
    - 若 job record 已 terminal 但 terminal event 缺失，记录 bounded WARN 并合成 terminal event 停止。
  - `wait_for_terminal(job_id)` 保持原轮询 job record 与 exit mapping 语义不变。

- `tests/service/test_fins_direct.py`
  - 覆盖 progress + terminal sequence 投影。
  - 覆盖 terminal event 缺失时合成 terminal event 与 bounded WARN。
  - 覆盖 empty read 后按 poll interval sleep，证明不会 tight loop。
  - 覆盖 event store failure 与 unknown job 异常透传。
  - 既有 wait_for_terminal exit mapping / cancel tests 保持通过。

## README Decision

- `dayu/service/README.md`：已更新。原因是 `dayu.service.fins_direct` 的稳定 reusable boundary 已从 start / poll terminal / cancel 扩展为 start / job event observation / poll terminal fallback / cancel。
- `tests/README.md`：已更新。原因是 `tests/service` 中 Fins direct 覆盖范围新增 event stream、terminal fallback、sleep 防 tight loop 与异常透传。

## Validation

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q`
  - 通过：`14 passed`
  - 仅出现 edgar 依赖的 deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/service/fins_direct.py tests/service/test_fins_direct.py`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过。

## Residual Risk

- S3 只消费 S1/S2 已有 event sidecar；不增强 Fins runtime 的事件产生粒度。
- terminal event 缺失时的合成事件不会写回 sidecar；它只防止 Service/UI 消费方悬挂，job record 仍是终态真源。
