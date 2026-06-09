# WU-TOOLS-01-F01-03 Slice 1 Follow-Up Fix - Codex

## Scope

- 修复 Controller re-review 接受的 `CTRL-RR1`。
- 未修改 `docs/host/issues-implementation-control.md`。
- 未修改 OLD downloader / pipeline。
- 未引入真实 upload runner、awaiting tool、wait adapter 或后续 Slice scope。

## CTRL-RR1 Fix

- 在 `FinsIngestionJobStore` 协议中新增 `save_failed_or_cancelled_if_active(job_id, *, failure_summary, result_summary, finished_at)`。
- `FsFinsIngestionJobStore.save_failed_or_cancelled_if_active` 在同一个 `file_lock` 内读取当前 record 并裁决：
  - 当前已终态：原样返回。
  - 当前 `cancellation_requested=True` 或 `status=CANCELLING`：写入并返回 `CANCELLED`，同时设置 `cancellation_requested=True`。
  - 否则写入 `FAILED`，并带入已校验的 `failure_summary` 和 `result_summary`。
- `_save_failed` 改为调用该原子 current-state 方法，不再基于调用方传入的旧 record 构造 `FAILED` 后调用 `save_job`。
- `_ClaimRaceJobStore` 同步实现同一协议语义，保持测试 fake store 与 production store 行为一致。

## Tests

- 新增 `test_save_failed_uses_current_cancelling_record_instead_of_stale_active_record`：
  - 使用 production `FsFinsIngestionJobStore`。
  - 将 stale active record 传给 `_save_failed` 前，先通过 `request_cancel` 把 store 当前 record 标成 `CANCELLING`。
  - 断言最终状态为 `CANCELLED`，不是 `FAILED`，且 `failure_summary` / `result_summary` 没有被 late failure 覆盖。
- 更新 `test_save_failed_from_exception_logs_secondary_job_store_failure`，改为 monkeypatch 新的 failed 原子终态方法，继续覆盖失败收口二次落盘失败的诊断路径。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：`37 passed`
  - 备注：存在 3 条既有 `edgar` deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## README

- 已按本轮变更触发范围复核 README 更新规则；本次变更只补齐 `dayu.fins.ingestion_runtime` 内部 durable job failed terminalization 的并发语义，并在既有 `tests/fins/test_fins_ingestion_runtime.py` 中增加同类回归测试。
- 该变更不改变 `dayu/fins/README.md` 面向开发者说明的 capability、架构边界、对外入口或状态机说明，也不改变 `tests/README.md` 的测试分层、运行方式或维护约定，因此未更新 README。

## Residual Risk

- 本次仅修复 failed terminalization 与 cancellation 的同源 stale-record 竞态。真实 upload workflow、Host wait adapter、awaiting tool 和物理取消 / revoke 仍不在 Slice 1 follow-up scope 内。
