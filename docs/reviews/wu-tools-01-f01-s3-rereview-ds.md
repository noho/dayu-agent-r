# WU-TOOLS-01-F01 Slice S3 Re-Review Artifact (DS)

## Gate Metadata

- Gate: re-review (fix verification).
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S3 - Download Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-s3-fix-codex.md`
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`

## Verdict

**pass**

Both accepted findings are fixed with correct implementation and adequate test coverage. No new correctness, stability, or testing issues introduced by the fix.

## Accepted Finding Status

### F01-S3-001 — fixed

- **Finding**: success terminalization 与 cancellation 之间的 TOCTOU，要求 success 终态写入必须在 job store 同一锁内重新读取当前状态并裁决 SUCCEEDED 或 CANCELLED。
- **Fix location**:
  - Protocol `FinsIngestionJobStore.save_succeeded_or_cancelled` — `ingestion_runtime.py:522-544`
  - Implementation `FsFinsIngestionJobStore.save_succeeded_or_cancelled` — `ingestion_runtime.py:709-756`
  - `_save_succeeded` 改为委托 `save_succeeded_or_cancelled` — `ingestion_runtime.py:1724-1749`
- **Fix correctness**: `save_succeeded_or_cancelled` 在 `_StoreFileLock` 内执行完整流程：读当前 record → 已是终态则原样返回 → `cancellation_requested` 或 `CANCELLING` 则写入 `CANCELLED` → 否则写入 `SUCCEEDED`。锁内重读消除了 TOCTOU 窗口。download 与 preprocess 共用同一终态裁决路径（均通过 `_save_succeeded` 委托）。
- **Test**: `test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled` — `test_fins_ingestion_runtime.py:654-711`。通过 monkeypatch `FsFinsIngestionJobStore.save_succeeded_or_cancelled` 在真实终态裁决前插入 `request_cancel`，验证最终状态为 `CANCELLED` 且 `result_summary` 为空（未被 SUCCEEDED 覆盖）。测试逻辑正确覆盖了 TOCTOU 竞态场景。
- **Coverage note**: 测试仅覆盖 download 路径的触发链路；preprocess 路径共享同一 `_save_succeeded` → `save_succeeded_or_cancelled` 调用链，机制层面已被覆盖，不构成遗漏。

### F01-S3-002 — fixed

- **Finding**: `_mark_job_running_or_cancelled` 返回任意 `_TERMINAL_STATUSES` 时，download/preprocess runners 必须立即 return，避免已终态 job 再次进入业务执行路径。
- **Fix location**:
  - `_run_preprocess_job` — `ingestion_runtime.py:1128-1129`：`if record.status in _TERMINAL_STATUSES: return`
  - `_run_download_job` — `ingestion_runtime.py:1176-1177`：同上
- **Fix correctness**: 两处 runner 入口在 `_mark_job_running_or_cancelled` 返回后统一对 `_TERMINAL_STATUSES`（SUCCEEDED / FAILED / CANCELLED）立即返回，不再区分 CANCELLED 与其他终态。状态机闭包完整。
- **Test**: `test_runners_return_for_preterminalized_jobs_without_executing` — `test_fins_ingestion_runtime.py:714-786`。验证：
  - download job 被预先写入 SUCCEEDED 后，fake adapter 未被调用（`download_adapter.requests == []`），原始 `result_summary` 保留。
  - preprocess job 被预先写入 SUCCEEDED 后，`_execute_preprocess_request` 未被调用（`preprocess_execute_calls == 0`），原始 `result_summary` 保留。
  - 两条路径均覆盖，断言精确。

## New Findings

**none** — 本次 fix 未引入新的 correctness、stability 或 testing 问题。

### 观察（非 blocking）

1. **`_save_cancelled` / `_save_failed` 在 runner 预检查路径中使用 `save_job` 而非锁内重读**: `ingestion_runtime.py:1751-1773`（`_save_cancelled`）和 `ingestion_runtime.py:1775-1817`（`_save_failed`）直接通过 `save_job` 写入终态，不执行锁内重读裁决。与 F01-S3-001 同类的 TOCTOU 存在于 cancel/fail 方向。在当前单 runner 架构下不可触发（同一 job 只有一个 runner 线程写入 SUCCEEDED，而 `_save_cancelled` 和 `_save_failed` 与该 runner 在同一 try/except 控制流内互斥），且 controller 明确只接受 success terminalization 覆盖 cancellation 的修复范围。fix artifact 已将此记为剩余风险。建议后续 slice 统一所有终态写入路径的锁内裁决模式。

## Validation Notes

- 测试运行: `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py` — **37 passed**，3 个 edgar 依赖 deprecation warnings（与本次修改无关）。
- 类型检查: `pyright` — **0 errors, 0 warnings, 0 informations**。
- README: 已检查 `dayu/fins/README.md`。本次修复只改变 job 状态机内部并发终态裁决与 runner 早退条件，未改变用户命令、配置入口、adapter 契约或测试维护说明，README 无需更新。

## Blocking Open Questions

none
