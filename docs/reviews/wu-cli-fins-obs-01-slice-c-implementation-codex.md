# WU-CLI-FINS-OBS-01 Slice C Implementation

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: implementation
- Implementer: Codex
- Date: 2026-06-16

## Scope

本 slice 只修改：

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/README.md`

未修改 `dayu/fins/ingestion/wait_adapter.py`、tools awaiting helper、Host/Engine contract，也未实现 observation registry。

## First-Principles Judgment

Slice C 的问题真实存在：Slice A/B 已经把 Service/CLI direct path 收敛到 `AsyncIterator[FinsEvent]`，但 `FinsIngestionRuntime.download/preprocess/upload` 仍是 Slice A 占位实现。若不实现 runtime direct stream，Service/CLI direct path 只能依赖 fake runtime 或失败，无法使用真实 Fins storage repository 和业务 helper。

本次没有删除旧 `start_*`、`read_job`、`read_job_events`、`request_cancel`。原因是 Slice D lightweight observation wait adapter 尚未迁移，旧 job store 当前仍是 awaiting legacy path 的 poll/cancel 真源。直接删除会破坏现有 tools awaiting 路径，不符合用户裁决。

## Implementation Summary

- 实现 `FinsIngestionRuntime.download/preprocess/upload -> AsyncIterator[FinsEvent]`。
- direct path 使用 runtime 内部有界 queue + daemon producer thread bridge 执行当前同步 adapter/runner。
- direct path 不调用 `start_*`，不创建 durable queued job record，不写 job event sidecar。
- direct path 和 legacy job path 共享下载、预处理、上传业务 helper；helper 改为接收 `_FinsIngestionExecutionContext`，通过上下文区分：
  - legacy awaiting job path: job-store cancellation checker + sidecar progress sink；
  - direct stream path: operation-scoped cancellation checker + in-memory `FinsEvent` sink。
- direct stream 正常业务完成产出 progress 和唯一 `RESULT`；unsupported source、upload failed status、producer exception 转为 failure `RESULT`。
- direct cancellation 使用 operation-scoped token/checker；同步 adapter 无法强中断时只提供 best-effort cooperative 语义，未声称物理强取消。
- direct 用户事件只投影 bounded count、业务短标签和安全错误说明；不投影 absolute path、raw provider payload、document body、job id、sequence 或 cursor。
- 删除已失效的 `FinsDirectStreamNotImplementedError` 占位异常。

## Tests

新增 / 更新 `tests/fins/test_fins_ingestion_runtime.py` 覆盖：

- direct download 真实写入 source/blob repository，并产出 progress + 唯一 success result。
- direct download 不创建 durable job record 或 `.events.jsonl` sidecar。
- unsupported download source 收口为 failure result，不静默结束。
- direct download 使用 operation-scoped cancellation token/checker 并返回 cancelled result。
- direct upload 用户事件不暴露路径、job id、raw provider payload 或正文。
- 保留旧 job store tests，作为 awaiting legacy path still present 的回归保护。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：59 passed，3 个现有 `edgar` deprecation warnings。
- `source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

## README Impact

- 已按 `tests/README.md` 的职责更新测试分层说明：
  - CLI Fins direct 测试描述从 `request_cancel(job_id)` 调整为 operation-scoped async cancellation。
  - Service Fins direct 测试描述从 job event / durable cancel API 调整为 `AsyncIterator[FinsEvent]` pass-through 与 no-job-handle boundary。
  - `tests/fins/test_fins_ingestion_runtime.py` 覆盖说明加入 direct stream、无 durable job record/sidecar、operation-scoped cancellation 与 leakage guard 覆盖。
- 已读取 `dayu/fins/README.md` 的 Agent 更新约束。该 README 当前仍包含 durable Fins job 的开发手册描述；本 slice 用户允许文件未包含 `dayu/fins/README.md`，且 replacement plan 指定 README 统一由 Slice E closeout 同步，因此本 slice 未编辑该文件。

## Residual Risks

- `dayu/fins/README.md` 中 durable Fins job 开发手册描述仍需要 Slice E 按最终 direct stream / awaiting handle 边界集中同步；归类为 covered by later approved slice: Slice E README synchronization。
- tools awaiting 和 wait adapter 仍依赖旧 job store/read_job_events/request_cancel；归类为 covered by later approved slice: Slice D lightweight observation handle migration。
- direct bridge 基于同步 adapter/runner 的 bounded thread queue。取消是 best-effort cooperative：adapter/runner 只有在调用 cancellation checker 或自然返回时才能收口；归类为 assigned to current design limitation until adapters are async-capable，已通过测试固定不声称强取消。

## Completion Status

Slice C implementation completed locally. No commit, push, or PR was created.
