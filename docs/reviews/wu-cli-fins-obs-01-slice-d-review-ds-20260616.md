# WU-CLI-FINS-OBS-01 Slice D Code Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: D, Fins tool awaiting and wait adapter lightweight handle
- Reviewer: AgentDS (DeepSeek)
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md` Slice D
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-slice-d-implementation-codex.md`
- Control source: `docs/host/issues-implementation-control.md`

## Review Scope

审查当前未提交 diff（11 files changed, +1199/-511），对照设计真源、plan 真源 Slice D 契约、implementation artifact，逐项验证 7 个重点维度。

## 验证结果

### 验证命令

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q
# Result: 152 passed, 3 third-party edgar deprecation warnings

source .venv/bin/activate && pytest tests/fins/ tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
# Result: 427 passed, 1 skipped, 3 warnings

source .venv/bin/activate && pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations

git diff --check
# Result: clean

python -c "import dayu.fins.ingestion; print('ok')"
# Result: ok
```

---

### 1. ToolAwaitingOutcome(EXTERNAL_JOB) 是否保留，resume_token 是否是 opaque Fins observation handle，不是 job id/cursor/sidecar

**结论：PASS**

直接证据：

- `dayu/fins/tools/_ingestion_tool_helpers.py:22-53` — `_awaiting_outcome_from_observation_handle` 构造 `ToolAwaitingOutcome(await_kind=ToolAwaitKind.EXTERNAL_JOB)`，`resume_token` 来自 `observation_handle_id_to_resume_token(handle)`。
- `dayu/fins/ingestion/observation_handle.py:260-269` — `observation_handle_id_to_resume_token` 返回 `handle.handle_id`，即 opaque `finsobs_` + hex 格式的 observation handle id。
- `dayu/fins/ingestion/observation_handle.py:35-53` — `_HANDLE_ID_PATTERN` 固定为 `finsobs_[a-f0-9]{16,96}`；`_DISALLOWED_TOKEN_FRAGMENTS` 显式拒绝 `"job"`, `"sequence"`, `"cursor"`, `"resume"`, `"token"`, `"tool_call"`, `"storage"`, `".dayu"`, `"/"`, `"\\"` 等片段。`parse_observation_handle_id_token` 和 `_validate_handle_id` 均强制执行此约束。
- `tests/fins/test_fins_ingestion_tools.py` — 新增测试断言 `"finsjob_" not in outcome.snapshot.snapshot_id`（三处），显式验证 await ref 不含旧 job id 语义。

`ToolAwaitingOutcome(EXTERNAL_JOB)` 完整保留；`resume_token` 是 opaque Fins observation handle id，不是 job id、cursor 或 sidecar。

---

### 2. tools 是否调用 start_observed_*，不再 start_* durable job path；schema 是否无 durable job 文案且 LLM-facing 自解释

**结论：PASS**

直接证据：

- `dayu/fins/tools/download_tools.py:86-88` — `FinsDownloadToolCallable.__call__` 调用 `self.runtime.start_observed_download(request, cancellation_token=cancellation_token)`。
- `dayu/fins/tools/preprocess_tools.py:85-88` — `FinsPreprocessToolCallable.__call__` 调用 `self.runtime.start_observed_preprocess(request, cancellation_token=cancellation_token)`。
- `dayu/fins/tools/upload_tools.py:106-109` — `FinsUploadToolCallable.__call__` 调用 `self.runtime.start_observed_upload(request, cancellation_token=cancellation_token)`。

三个 tool callable 均不再调用 `start_download`、`start_preprocess`、`start_upload`（legacy durable job path）。

Schema LLM-facing 文案检查：

- `download_tools.py:164-169` — description: "Start a financial filing download operation... The tool returns immediately with an external-job wait state after a lightweight observation handle is registered; it does not wait for the download to finish."
- `preprocess_tools.py:163-168` — description: "Start a financial document preprocess operation... The tool returns immediately with an external-job wait state after a lightweight observation handle is registered; it does not wait for processing to finish."
- `upload_tools.py:164-169` — description: "Start a financial filing or material upload operation... The tool returns immediately with an external-job wait state after a lightweight observation handle is registered; it does not wait for file conversion or storage writes to finish."

三个 schema 均无 "durable job"、"job id"、"job record"、"sidecar"、"cursor"、"sequence" 等旧文案。参数 schema 自解释：字段名、类型、描述、default、enum 均在 schema 内自足说明，不依赖外部类型名或内部模块名。

---

### 3. wait_adapter 是否 parse observation token、poll/cancel/abandon observation runtime，completed/failed/cancelled/lost 映射正确；corrupt/missing handle -> LOST；transient unavailable 有 bounded max wait，不无限 pending

**结论：PASS**

直接证据：

- `dayu/fins/ingestion/wait_adapter.py:128-135` — `poll_wait` 调用 `_handle_from_wait_record(wait_record)` 解析 token；解析失败返回 None 时直接 `WaitPollLost(_lost_outcome())`；解析成功后调用 `self.runtime.poll_observation(handle)`、`self.runtime.cancel_observation(handle)`、`self.runtime.abandon_observation(handle)`。
- `dayu/fins/ingestion/wait_adapter.py:230-247` — `_handle_from_wait_record` 调用 `parse_observation_handle_id_token(wait_record.resume_token)`；`ValueError`（token 格式非法或含禁止片段）时返回 `None`，上游映射为 LOST。
- `dayu/fins/ingestion/wait_adapter.py:286-306` — `_poll_snapshot_result` 映射：PENDING/RUNNING → `WaitPollNotReady`；SUCCEEDED → `WaitPollReady(_completed_outcome(...))`；FAILED → `WaitPollReady(_failed_outcome(...))`；CANCELLED → `WaitPollReady(_cancelled_outcome(...))`；LOST → `WaitPollLost(_lost_outcome())`。
- `dayu/fins/ingestion/wait_adapter.py:267-283` — `_poll_error_result` 映射：TRANSIENT_UNAVAILABLE + 未过期 → `WaitPollNotReady`；TRANSIENT_UNAVAILABLE + 已过期 → `WaitPollLost`；PERMANENT_NOT_FOUND / PERMANENT_CORRUPT_HANDLE → `WaitPollLost`。
- `dayu/fins/ingestion/wait_adapter.py:478-488` — `_transient_pending_expired` 以 `wait_record.created_at` 为起点，`_TRANSIENT_PENDING_MAX_SECONDS = 300.0`（5 分钟）为有界窗口；超过窗口后 `WaitPollLost`。

corrupt/missing handle → LOST 覆盖完整：token 格式非法（`parse_observation_handle_id_token` 抛 `ValueError`）、token 含禁止片段（`_validate_handle_id` 抛 `ValueError`）、process-local registry 不存在 handle（`_observation_snapshot` 返回 `_lost_observation_snapshot`）、poll 抛出 `PERMANENT_NOT_FOUND` / `PERMANENT_CORRUPT_HANDLE` 均收敛为 LOST。

测试覆盖：
- `test_fins_wait_poll_adapter_corrupt_and_missing_handles_are_lost` — 验证 corrupt token（旧 `finsjob_` 格式）→ LOST、missing handle → LOST。
- `test_fins_wait_poll_adapter_transient_unavailable_is_bounded_not_ready` — 验证 transient → not-ready（窗口内）和 transient expired → lost（窗口外）。

---

### 4. FinsIngestionRuntime process-local observation registry 是否线程安全、无 durable job record/sidecar、cancel/abandon best-effort 且不删除业务产物；注意 bounded queue 在慢 poller 下是否有阻塞风险

**结论：PASS（含已记录 residual risk）**

线程安全：

- `dayu/fins/ingestion_runtime.py:1937-1939` — `FinsIngestionRuntime.create` 构造两个独立锁：`_start_lock: Lock`（legacy job start 用）和 `_observation_lock: Lock`（observation registry 用）。
- `_observation_lock` 在所有 observation registry 访问点被正确持有：
  - `_start_observed_stream:2276` — `with self._observation_lock:` 包裹 registry 写入和 executor 提交失败时的清理。
  - `cancel_observation:2187` — `with self._observation_lock:` 包裹 registry 读取和 cancellation_state 修改。
  - `abandon_observation:2215` — `with self._observation_lock:` 包裹 registry pop。
  - `_observation_snapshot:2305` — `with self._observation_lock:` 包裹 registry 读取和 queue drain。

无 durable job record/sidecar：

- `_start_observed_stream:2249-2287` — 构造 `_FinsIngestionExecutionContext` 时 `job_record=None`，使用 `direct_queue`（bounded Queue），不创建 `FinsIngestionJobRecord`，不写 `.dayu/fins_ingestion/jobs/*.json` 或 `*.events.jsonl`。
- `_run_direct_stream_producer` — 复用的 producer 通过 `_emit_context_progress` → `_put_direct_queue` 投递事件到 bounded queue，不经过 `_emit_progress_event`（job sidecar 路径）。

cancel/abandon best-effort 且不删除业务产物：

- `cancel_observation:2193-2198` — 只调用 `record.cancellation_state.request_cancel()` 设置本地取消标志；docstring 明确 "取消是 best-effort，不承诺中断不可取消的 blocking call"。
- `abandon_observation:2215-2218` — 只 `self._observations.pop(handle.handle_id, None)` 清理 process-local record 并 `request_cancel()`；不调用任何 storage delete/cleanup。docstring 明确 "不删除已经写入 Fins storage 的业务产物"。

Bounded queue 阻塞风险：

- `_DIRECT_EVENT_QUEUE_MAX_SIZE = 32`；producer 在 `_put_direct_queue:4255-4264` 中以 `timeout=0.05s` 循环重试 put。当 consumer（poller）已取消时，`cancellation_state.is_cancelled()` 返回 True，producer 丢弃事件并返回 False。
- 当 poller 只是慢（未取消）而 producer 高频投递时，32 项队列可能被填满，producer 线程会在 put 循环中阻塞。implementation artifact 已将此项记录为 residual risk："A very slow or absent poller can delay a highly chatty observed producer once the bounded queue is full."
- 这是 lightweight local observation contract 的可接受限制，不构成 blocking finding。未来 production poller/backoff work unit 可考虑 coalescing progress snapshot 替代 event buffering。

---

### 5. import boundary 是否干净：无函数内 lazy import 绕循环依赖、dayu.fins.ingestion.__init__ 不再 eager re-export wait_adapter 是否合理

**结论：PASS**

- `dayu/fins/ingestion/__init__.py` — 仅从 `.observation_handle` re-export 契约符号（`FinsObservationHandle`, `FinsObservationStatus`, `parse_observation_handle_id_token` 等），不再 re-export `wait_adapter` 的任何符号。
- `dayu/service/host_assembly.py:23-28` — 改为直接从 `dayu.fins.ingestion.wait_adapter` import `FINS_DOWNLOAD_AWAITING_TOOL_NAME`, `FINS_PREPROCESS_AWAITING_TOOL_NAME`, `FINS_UPLOAD_AWAITING_TOOL_NAME`, `build_fins_wait_adapter_registry`。
- `tests/service/test_host_assembly.py:28` — 同样改为 `from dayu.fins.ingestion.wait_adapter import FINS_INGESTION_WAIT_ADAPTER_KEY`。
- `dayu/fins/ingestion/wait_adapter.py` — 直接从 `dayu.fins.ingestion.observation_handle` import，无循环依赖；`from dayu.fins.service_runtime import DefaultFinsRuntime` 和 `from dayu.host.api import ...` 均为向下的合法依赖。
- 全量 diff 中未发现任何函数内 `import` 语句绕过循环依赖。
- `python -c "import dayu.fins.ingestion; print('ok')"` 通过，确认 `__init__` 不再触发 wait_adapter → service_runtime → ingestion_runtime 的 import chain。

`dayu.fins.ingestion.__init__` 不再 eager re-export wait_adapter 是合理的：observation_handle 是低层 contract 模块，wait_adapter 依赖 Host API 和 service_runtime，属于更高层组装模块。将 wait_adapter 符号从 `__init__` 移除避免了不必要的 import chain，Service assembly 和 tests 改为直接 import 是正确的分层做法。

---

### 6. old read_job/request_cancel/job_id 语义是否只留在 legacy runtime，不被 tools/wait_adapter 消费

**结论：PASS**

- `dayu/fins/ingestion_runtime.py` 仍保留 `start_download`（line 2687）、`start_preprocess`（line 2744）、`start_upload`（line 2800）、`read_job`（line 2850）、`read_job_events`（line 2867）、`request_cancel`（line 2896）——这些是 legacy durable job path，保留在 runtime 中但不再被 tools 或 wait_adapter 消费。
- 三个 tool callable（`download_tools.py`, `preprocess_tools.py`, `upload_tools.py`）均调用 `start_observed_*`，不调用 `start_*`（legacy job path）。
- `wait_adapter.py` 的 `FinsIngestionWaitPollAdapter` 只依赖 `FinsObservationRuntime` protocol，调用 `poll_observation` / `cancel_observation` / `abandon_observation`，不调用 `read_job` / `read_job_events` / `request_cancel`。
- `_ingestion_tool_helpers.py` 不再 import `FinsIngestionJobStart`，`_awaiting_outcome_from_observation_handle` 不再使用 `start.job_id` 填充 `resume_token`。
- 测试文件 `test_fins_ingestion_tools.py` 移除了 `_TERMINAL_JOB_STATUSES`、`_JOB_WAIT_TIMEOUT_SECONDS`、`_JOB_WAIT_POLL_SECONDS` 等旧 job 常量；移除了 `_OSErrorCreateJobStore`（模拟 job store 创建失败的 fake）；移除了所有 `read_job(job_id)` / `request_cancel(job_id)` 断言。新增的 `_FakeObservationRuntime` 实现 `FinsObservationRuntime` protocol，使用 `snapshots` dict 和 `poll_errors` dict 驱动 wait adapter 测试。

legacy `read_job`/`request_cancel`/`job_id` 语义完全局限在 `ingestion_runtime.py` 的 legacy job path（`start_*` → `_run_*_job` → `_mark_job_running_or_cancelled` → `_save_*`），不被 tools、wait_adapter 或 `_ingestion_tool_helpers` 消费。

---

### 7. tests/README impact

**结论：已检查，编辑推迟到 Slice E（符合 plan）**

- `tests/README.md` 已阅读。其 `Agent更新约束` 描述测试分层、运行方式与维护约定，边界覆盖当前 `tests/` 下已有测试。
- Slice D 修改了 `tests/fins/test_fins_ingestion_tools.py` 和 `tests/service/test_host_assembly.py`，触发 `tests/README.md` 检查。
- 当前 `tests/README.md` 不包含对 Fins ingestion tools / wait adapter 测试的具体描述，因此无需因本 slice 新增/删除具体测试文件而更新分层列表。
- 按 replacement plan Slice E 约定，跨 README 一致性编辑集中在 Slice E。本 slice 完成 impact assessment：`tests/README.md` 无需立即编辑。

---

## 其他观察

### observation_handle.py

- `FinsObservationPollError` 继承 `Exception` 并正确实现 `__init__` 校验（`error_kind` 类型检查、`message` 验证）。
- `FinsObservationHandle.__post_init__` 和 `FinsObservationSnapshot.__post_init__` 提供完整的字段组合校验（handle id 格式、时区、terminal/non-terminal result 存在性、retry_after 与状态匹配）。
- `observation_status_resolution_kind` 和 `observation_poll_error_resolution_kind` 将 Fins 内部状态中立映射到 Host wait resolution，不耦合 Host 具体 outcome 类型。
- `_DISALLOWED_TOKEN_FRAGMENTS` 同时用于 handle id 和 message 校验，防止 observation 诊断消息泄漏内部治理标识。

### wait_adapter.py

- `_run_async_observation` 使用 `asyncio.run()` 在 sync Host adapter 边界内执行 async observation runtime 方法。这是当前 Host poller 的同步调用约定的必要桥接。若未来 Host poller 改为 async，此桥接可移除。
- `_timestamp_or_now` 对 Host wait record 时间戳做防御性解析：非法格式回退为当前 UTC 时间，naive datetime 补充 `timezone.utc`。
- `_result_meta` 使用 `max(finished_at, started_at)` 防御时钟回退。
- `abandon_wait` 对 TRANSIENT_UNAVAILABLE 错误 re-raise（不吞没），确保 Host poller 能感知 abandon 失败。

### ingestion_runtime.py

- `_start_observed_stream` 在 executor 提交失败时正确清理已注册的 observation record（`self._observations.pop(handle.handle_id, None)`）。
- `_drain_observation_queue` 在 producer 完成但无 RESULT 时合成 `FAILED` observation snapshot（"Observation finished without a result."），确保 poller 不会无限 pending。
- `_put_direct_queue` 在 consumer 已取消时主动丢弃事件，避免 producer 线程阻塞在无人读取的队列上。
- `_safe_observation_message` 和 `_safe_direct_error_message` 均过滤路径、job id、cursor 等禁止片段，防止泄漏。

### 测试覆盖

新增/改写的关键测试：

| 测试 | 覆盖点 |
|---|---|
| `test_download_tool_returns_external_job_awaiting_outcome` | `ToolAwaitingOutcome(EXTERNAL_JOB)` + resume_token 不含 `finsjob_` |
| `test_fins_wait_poll_adapter_maps_observation_statuses` | SUCCEEDED/FAILED/CANCELLED/PENDING → Host poll result 映射 |
| `test_fins_wait_poll_adapter_corrupt_and_missing_handles_are_lost` | corrupt token + missing handle → LOST |
| `test_fins_wait_poll_adapter_transient_unavailable_is_bounded_not_ready` | TRANSIENT_UNAVAILABLE → not-ready（窗口内）/ lost（窗口外） |
| `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation` | abandon 调用 cancel + abandon，handle 被清理 |
| `test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop` | corrupt token abandon 为 noop |

旧测试语义迁移完整：`before_job_creation` → `before_observation_start`；`maps_terminal_and_missing_jobs` → `maps_observation_statuses`；`maps_corrupt_job_evidence_to_lost` → `corrupt_and_missing_handles_are_lost`；`abandon_marks_job_cancellation_requested` → `abandon_cancels_and_cleans_observation`。

---

## Residual Risk 更新

| ID | 状态 | 说明 |
|---|---|---|
| `WU-CLI-FINS-OBS-01-R8` | **closed** | process-local observation registry 线程安全已验证：`_observation_lock` 正确包裹所有 registry 读写路径；`cancel_observation` 和 `abandon_observation` 在持锁下操作；`_start_observed_stream` 在持锁下注册并在 executor 提交失败时清理。 |
| `WU-CLI-FINS-OBS-01-R9` | **closed** | Slice D wait adapter 已实现 bounded retry：`_TRANSIENT_PENDING_MAX_SECONDS = 300.0` 有界窗口；corrupt token（`parse_observation_handle_id_token` ValueError）→ `None` → LOST；E2E 测试覆盖 corrupt/missing handle → LOST 和 transient expired → LOST。 |
| (new) bounded queue slow poller | **deferred-with-owner** | 见 implementation artifact residual risk：慢 poller 下 bounded queue（32项）可能阻塞 producer。当前 lightweight observation contract 可接受；未来 production poller WU 可考虑 coalescing progress snapshot。Owner: future poller/backoff work unit。 |

---

## 结论

**PASS**

所有 7 个重点审查维度均通过。152 个 targeted tests 全部通过，427 个全量相关 tests 全部通过（1 skipped），full pyright 0 errors，git diff --check clean。

无 blocking findings。
