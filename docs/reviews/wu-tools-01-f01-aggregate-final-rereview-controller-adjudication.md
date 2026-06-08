# WU-TOOLS-01-F01 Aggregate Final Re-review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Gate: aggregate final review re-review
- Accepted finding under review: `F01-AGG-001`
- Fix artifact: `docs/reviews/wu-tools-01-f01-aggregate-final-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-aggregate-final-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-aggregate-final-rereview-ds.md`

## Controller Verdict

**pass**

`F01-AGG-001` 已修复。修复将 queued -> running 的 claim 与取消请求裁决下沉到 Fins job store 边界，并在一次 `_StoreFileLock` 内完成读取、终态判断、取消判断以及 RUNNING / CANCELLED 写入。`FinsIngestionRuntime._mark_job_running_or_cancelled` 不再走旧的 `read_job` + `save_job` 双锁路径。

## Evidence

- `FinsIngestionJobStore.claim_running_or_cancelled(...)` 已成为 job store 协议的一部分，签名使用直接参数并返回持久化后的 `FinsIngestionJobRecord`：`dayu/fins/ingestion_runtime.py:546`。
- `FsFinsIngestionJobStore.claim_running_or_cancelled(...)` 在单个 `_StoreFileLock` 内执行 `_read_record_locked`、terminal early return、CANCELLING / `cancellation_requested` -> CANCELLED 写入，以及默认 RUNNING 写入：`dayu/fins/ingestion_runtime.py:805`。
- `_mark_job_running_or_cancelled` 只调用 `claim_running_or_cancelled`，不再执行 `read_job` 后 `save_job`：`dayu/fins/ingestion_runtime.py:1281`。
- 回归测试断言 runtime 使用 claim 路径、未调用 `save_job`、最终为 `CANCELLED` 且保留 `cancellation_requested`：`tests/fins/test_fins_ingestion_runtime.py:878`。

## Re-review Findings Adjudication

| Finding / Observation | Source | Controller decision | Reason |
|---|---|---|---|
| `F01-AGG-001` fixed | MiMo + DS | accepted-fixed | 代码证据证明 claim-running 与 cancellation 收口已在 store 原子边界内完成；指定测试、pyright、`git diff --check` 均通过。 |
| `_save_cancelled` 仍使用 `save_job` | MiMo OBS-1 / DS observed-not-blocking | rejected-with-reason | 当前 finding 针对 queued -> running claim race；`_save_cancelled` 不是本 race 的写入路径。该方法由同一后台 job 执行流在已观察到 cancellation 后收口，外部 `request_cancel` 只写 CANCELLING，不写其它终态；没有当前代码证据显示会覆盖独立终态写入。不作为本 work unit active residual。 |

## Validation

两路 re-review 均报告：

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
  - `143 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过

Controller 仍需在 accepted commit 前执行最终复验。

## README Decision

不更新 README。当前修复只改变 Fins ingestion job store 内部治理状态的原子转换，不改变 read / download / preprocess provider schema、CLI/UI 使用方式、Host/Engine contract、配置入口或测试分层说明。

## Residual / Blocker

- blocker: none
- `WU-TOOLS-01-S4-R1` 保持关闭，不重新打开。
- 真实 SEC/CN/HK download adapters、upload ingestion provider、SEC/Fins 与 CN/HK CI pipeline/smoke、未来 NEW CLI download/process wrapper 仍由既有后续 work units 承接。

## Gate Decision

建议进入 accepted deepreview commit，然后进入 `ready-to-open-draft-PR` gate。
