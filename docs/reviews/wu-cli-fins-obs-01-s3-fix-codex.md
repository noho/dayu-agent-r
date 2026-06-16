# WU-CLI-FINS-OBS-01 Slice S3 Fix - AgentCodex

## Scope

本次只修复 controller 裁决接受的 Slice S3 findings：`S3-FIX-01`、`S3-FIX-02`、`S3-FIX-03`。未修改 CLI、Host、Engine、Fins runtime、adapter/runner protocol、pipeline stream 或设计真源。

## Changes

- `dayu/service/fins_direct.py`
  - 新增 `FinsDirectRuntimeStateError`，用于表达 Fins direct runtime 持久化状态不一致。
  - `stream_job_events_until_terminal(...)` 遇到 terminal event 后仍按原逻辑读取 job record；若 record 是 `SUCCEEDED` / `FAILED` / `CANCELLED`，正常 terminal mapping 不变。
  - 若 terminal event 已到达但 `read_job(...)` 返回非终态 record，改为抛出 `FinsDirectRuntimeStateError`，不再把 runtime 数据不一致误报成 `FinsDirectUsageError`。

- `tests/service/test_fins_direct.py`
  - 新增 terminal event + 非终态 record 的 runtime 数据不一致测试。
  - 新增 `after_sequence=-1` fail-fast 测试，断言抛 `FinsDirectUsageError` 且不读取 runtime。
  - 新增 terminal event 到达后 `read_job(...)` 失败的异常透传测试。

## Validation

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q`
  - 通过：`17 passed`
  - 仅有 edgar 依赖 deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/service/fins_direct.py tests/service/test_fins_direct.py`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过。

## README Decision

本次未更新 README。理由：修复只调整异常分类并补充既有 `tests/service/test_fins_direct.py` 内的回归测试，不新增测试层级、运行方式、Service public 行为说明或用户可见能力；既有 `dayu/service/README.md` 与 `tests/README.md` 对 S3 event stream 能力的描述仍然准确。

## Deferred / Non-actions

- 未改变 terminal fallback 设计；合成 terminal event 仍只 yield 给 consumer，不写回 sidecar。
- 未增加 `wait_for_terminal(...)` 与 `stream_job_events_until_terminal(...)` 的互斥。
- 未修改 CLI、Host、Engine、Fins runtime、adapter/runner protocol、pipeline stream 或设计真源。
- 未 commit、push 或创建 PR。
