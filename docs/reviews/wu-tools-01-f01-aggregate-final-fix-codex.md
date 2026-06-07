# WU-TOOLS-01-F01 Aggregate Final Fix

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Gate: aggregate final review fix
- Accepted finding: `F01-AGG-001`
- Artifact: `docs/reviews/wu-tools-01-f01-aggregate-final-fix-codex.md`
- Commit / push: not performed by user instruction

## 修复说明

`F01-AGG-001` 成立：旧 `_mark_job_running_or_cancelled` 先 `read_job` 再 `save_job`，两次操作分别获取 job store 锁。若 `request_cancel` 在两次锁之间把 job 从 `QUEUED` 改为 `CANCELLING`，后续 `save_job(RUNNING)` 会覆盖取消请求。

本次修复把 queued -> running / cancelled 的裁决下沉到 Fins job store 边界：

- 在 `FinsIngestionJobStore` 协议中新增 `claim_running_or_cancelled(job_id, *, started_at, updated_at) -> FinsIngestionJobRecord`。
- 在 `FsFinsIngestionJobStore` 中实现该方法，并在一次 `_StoreFileLock` 内完成：
  - `_read_record_locked(job_id)`；
  - terminal 状态原样返回；
  - `CANCELLING` 或 `cancellation_requested=True` 写入 `CANCELLED`，同时保留 `cancellation_requested=True`；
  - 其它非终态写入 `RUNNING`。
- `_mark_job_running_or_cancelled` 改为只调用 `job_store.claim_running_or_cancelled(...)`，不再执行 `read_job` + `save_job` 双锁路径。

该修复只改变 Fins job governance state machine 的原子性，不改变 Host/Engine contracts，不改变 tool/provider/config schema，不改变财报正文存储边界。

## 改动文件

- `dayu/fins/ingestion_runtime.py`
  - 新增 job store 协议方法。
  - 新增文件系统 job store 原子 claim-running 实现。
  - 调整 `_mark_job_running_or_cancelled` 调用原子方法。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 `_ClaimRaceJobStore` 测试 double。
  - 新增 `test_claim_running_preserves_cancel_between_read_and_running_write` 回归测试。
  - 新增 `_is_terminal_job_status` 测试 helper。
- `docs/reviews/wu-tools-01-f01-aggregate-final-fix-codex.md`

## Regression Test

新增回归测试通过测试 double 精确模拟旧 race：

- `read_job` 在首次读取 `QUEUED` 时返回旧 queued record，同时把 store 内真实状态改为 `CANCELLING`，模拟旧 read/save 窗口里的取消请求。
- 若 runtime 仍使用旧 `read_job` + `save_job`，它会用 stale queued record 写入 `RUNNING`，最终覆盖取消。
- 修复后 runtime 只调用 `claim_running_or_cancelled`，测试 double 在 claim 内触发取消并重新读取当前状态，最终保存 `CANCELLED`。
- 测试断言：
  - `claim_running_calls == 1`；
  - `save_job_calls == 0`；
  - 最终状态是 `CANCELLED`；
  - 不进入 `RUNNING`；
  - `cancellation_requested=True`。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py`
  - 结果：`27 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
  - 结果：`143 passed, 3 warnings`
  - warnings 均为 `edgar` 依赖 deprecation warning。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## README No-update Decision

- `dayu/fins/README.md`：不更新。本次只修 job store 内部原子状态转换；README 已描述 job store 存治理状态和 cancellation/wait adapter 边界，未出现不一致。
- `dayu/config/README.md`：不更新。provider config 形态无变化。
- `tests/README.md`：不更新。测试层级和运行方式无变化，仅新增同一测试文件内的 regression case。
- 根 `README.md`：不更新。未恢复 CLI/UI，也未新增用户可见命令。
- `dayu/README.md`：不更新。未改变稳定分层关系。

## Residual / Blocker

- fixed in current fix gate:
  - `F01-AGG-001`: queued -> running claim 与取消请求之间的 TOCTOU race 已通过 job store 原子 claim 修复。
- assigned to later work unit:
  - 真实 SEC/CN/HK 网络 download adapters。
  - upload ingestion provider。
  - SEC/Fins 与 CN/HK CI pipeline/smoke。
  - 未来 NEW CLI download/process wrapper。
- blocker: none。

## Ready-to-open-draft-PR 建议

仍建议进入 `ready-to-open-draft-PR` gate。

理由：

- Aggregate final review 唯一 accepted finding 已修复。
- 指定 pytest、pyright 与 `git diff --check` 均通过。
- 修复未扩大 F01 scope，未触碰 Host/Engine contracts、CLI/UI、真实网络 adapter 或 README 广泛清理。
- `WU-TOOLS-01-S4-R1` 仍可保持关闭；本 finding 是 shared runtime 内部取消 race 的低概率 correctness fix，不说明 runtime/provider/wait-adapter 目标不完整。
