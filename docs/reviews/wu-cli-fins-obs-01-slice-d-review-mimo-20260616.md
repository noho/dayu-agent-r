# WU-CLI-FINS-OBS-01 Slice D Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: D, Fins tool awaiting and wait adapter lightweight handle
- Reviewer: MiMo (AgentMiMo)
- Implementer: Codex
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md` Slice D
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-slice-d-implementation-codex.md`
- Control source: `docs/host/issues-implementation-control.md`

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -x -q` → **92 passed**, 3 third-party deprecation warnings.
- `source .venv/bin/activate && pyright` → **0 errors, 0 warnings, 0 informations**.
- `git diff --check` → clean (no whitespace errors).

## Review dimensions

### 1. ToolAwaitingOutcome(EXTERNAL_JOB) 保留；resume_token 是 opaque Fins observation handle

**结论：PASS。**

- `_awaiting_outcome_from_observation_handle` (`_ingestion_tool_helpers.py:20`) 保留 `ToolAwaitSpec(await_kind=ToolAwaitKind.EXTERNAL_JOB, ...)`。
- `resume_token = observation_handle_id_to_resume_token(handle)` 只返回 `handle.handle_id`（`observation_handle.py:268`），不包含 job id、cursor、sequence 或 storage path。
- `_DISALLOWED_TOKEN_FRAGMENTS` (`observation_handle.py:42-53`) 主动拒绝含 `job`、`sequence`、`cursor`、`resume`、`token`、`tool_call`、`storage`、`.dayu`、`/`、`\` 片段的 handle id。
- 测试断言 `"job" not in resume_token`、`"cursor" not in resume_token`、`"sidecar" not in resume_token`、`"finsjob_" not in snapshot_id`（test 739-781 行）。

### 2. Tools 调用 start_observed_*；schema 无 durable job 文案且 LLM-facing 自解释

**结论：PASS。**

- `FinsDownloadToolCallable.__call__` 调用 `self.runtime.start_observed_download(request, cancellation_token=cancellation_token)`（`download_tools.py:83`），不再调用 `start_download`。
- `FinsPreprocessToolCallable.__call__` 调用 `self.runtime.start_observed_preprocess(...)`（`preprocess_tools.py:82`）。
- `FinsUploadToolCallable.__call__` 调用 `self.runtime.start_observed_upload(...)`（`upload_tools.py:103`）。
- 旧 `start.status in {CANCELLING, CANCELLED}` 后置检查已删除（start_observed_* 在启动前通过 `_raise_if_start_cancelled` 检查，失败时抛 `FinsIngestionStartCancelledError`）。
- Tool schema description 改写为 "returns immediately with an external-job wait state after a lightweight observation handle is registered"（download_tools.py:166、preprocess_tools.py:164、upload_tools.py:165），无 "durable job" 文案。
- 错误消息 "未能保存任务记录" 改为 "未进入等待状态"，无 durable 语义泄漏。

### 3. wait_adapter：parse observation token、poll/cancel/abandon observation、status 映射

**结论：PASS。**

- `_handle_from_wait_record` (`wait_adapter.py:230`) 调用 `parse_observation_handle_id_token(wait_record.resume_token)` 恢复 typed handle。corrupt token 返回 `None` → `WaitPollLost`。
- `poll_wait` (`wait_adapter.py:119`) 调用 `_run_async_observation(self.runtime.poll_observation(handle))`。
- 状态映射正确：
  - `PENDING` / `RUNNING` → `WaitPollNotReady`
  - `SUCCEEDED` → `WaitPollReady(ResolveWaitCompletedOutcome)`
  - `FAILED` → `WaitPollReady(ResolveWaitFailedOutcome)`
  - `CANCELLED` → `WaitPollReady(ResolveWaitCancelledOutcome)`
  - `LOST` / 兜底 → `WaitPollLost(ResolveWaitLostOutcome)`
- corrupt token 或 missing handle → `WaitPollLost`（不无限 pending）。
- `TRANSIENT_UNAVAILABLE` 初期 → `WaitPollNotReady`，超过 `_TRANSIENT_PENDING_MAX_SECONDS`（300s）→ `WaitPollLost`（`_transient_pending_expired` at `wait_adapter.py:478`）。
- `abandon_wait` (`wait_adapter.py:137`) best-effort 调用 `cancel_observation` + `abandon_observation`，不删除业务产物。

### 4. FinsIngestionRuntime process-local observation registry

**结论：PASS，有一项设计观察。**

- `_observation_lock: Lock` + `_observations: dict[str, _FinsObservedOperationRecord]`（`ingestion_runtime.py:1890-1891`）。所有 registry 读写都在 `with self._observation_lock:` 保护下，线程安全。
- 无 durable job record / sidecar 写入。observation 只在 process-local dict 中注册。
- `cancel_observation` (`ingestion_runtime.py:2187`) 只调用 `record.cancellation_state.request_cancel()`，best-effort，不删除业务产物。
- `abandon_observation` (`ingestion_runtime.py:2212`) 只 `pop` 本地 record + best-effort cancel，不删除 storage 产物。
- Bounded queue (`Queue(maxsize=_DIRECT_EVENT_QUEUE_MAX_SIZE)`) 在慢 poller 下会阻塞 producer thread（`put()` 等待空间）。这是标准 backpressure 机制，实现 artifact 正确记录为 residual risk。当前 local observation 场景可接受。

**设计观察**：`_FinsObservedOperationRecord` 是 mutable `@dataclass`（非 `frozen=True`），其 `status`、`result`、`message` 字段在 `_drain_observation_queue` 中修改。这些修改都在 `_observation_lock` 保护下，但未来维护者需注意：修改这些字段必须持锁。建议后续在类 docstring 中明确 "所有字段变更必须在 `_observation_lock` 保护下"。

### 5. Import boundary

**结论：PASS。**

- `observation_handle.py` 对 `ingestion_runtime` 的 import 改为 `TYPE_CHECKING` guard（`observation_handle.py:25-30`），消除运行时循环依赖。
- `dayu.fins.ingestion.__init__` 不再 eager re-export `wait_adapter` 符号。`__init__.py` 只 re-export `observation_handle` 符号。
- `host_assembly.py` 和 tests 改为从 `dayu.fins.ingestion.wait_adapter` 直接导入（`host_assembly.py:23`、test 1610-1615 行）。
- 无函数内 lazy import 绕循环依赖。

### 6. Old read_job / request_cancel / job_id 语义

**结论：PASS。**

- `wait_adapter.py` 不再 import `FinsIngestionJobRecord`、`FinsIngestionJobStatus`、`read_job`、`request_cancel`。
- Tools 不再 import `FinsIngestionJobStatus`。
- `FinsIngestionJobStore` 仍保留在 `ingestion_runtime.py`（legacy runtime 使用），但 Slice D 的 tools/wait_adapter 不消费它。
- 旧 `_persist_job`、`_job_record`、`_wait_ingestion_job_terminal`、`_write_corrupt_job_evidence`、`_runtime_with_job_store` 测试辅助函数已删除。

### 7. tests/README impact

**结论：观察，非 blocking。**

- `tests/fins/test_fins_ingestion_tools.py` 测试语义已从 durable job 改为 observation handle。实现 artifact 的 README impact assessment 正确：`tests/README.md` 触发检查，但实际编辑可集中在 Slice E。
- `dayu/fins/README.md` 仍含 "Fins durable job" 文案（最后一句 "把 Fins durable job 映射到 Host wait-resume 的 adapter"）。Slice E 应更新。

## Blocking findings

无。

## Non-blocking observations

1. **Mutable record 持锁约定**：`_FinsObservedOperationRecord` 是 mutable dataclass，字段变更必须在 `_observation_lock` 下。建议在类 docstring 中显式说明此约束，降低未来维护者遗漏锁保护的风险。

2. **`_run_async_observation` 使用 `asyncio.run()`**：每次 poll/cancel/abandon 调用创建新 event loop。当前 Host poller 是 sync thread，可行；但如果未来 poller 迁移到 async context，需要改用已有的 event loop。`wait_adapter.py:499` docstring 已记录此限制。

3. **`_safe_observation_message` 禁止片段硬编码**：`_safe_observation_message`（`ingestion_runtime.py:4748`）和 `observation_handle.py:_validate_message`（`observation_handle.py:349`）各自维护一份禁止片段列表。两份列表当前一致，但非共享常量。未来新增禁止片段时需同步两处。

4. **fins README 仍含 durable job 文案**：`dayu/fins/README.md` 最后一句 "把 Fins durable job 映射到 Host wait-resume 的 adapter" 需在 Slice E 更新为 lightweight observation handle 语义。

## 结论

**PASS。** Slice D 实现完整，与 plan 真源一致，测试通过，pyright 干净，无 blocking findings。
