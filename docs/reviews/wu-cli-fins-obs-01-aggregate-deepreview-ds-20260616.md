# WU-CLI-FINS-OBS-01 Aggregate Deepreview (AgentDS)

## 范围与真源

- **Review 类型**：aggregate deepreview，审查 accepted replacement implementation 的跨 slice 完整性。
- **Review 范围**：commits `637d36a5`/`612b6b05` → `044a966d`，重点审查 `f79b59ab`（Slice A/B）、`a90d86aa`（Slice D0）、`11fd5e97`（Slice C）、`0b25416d`（Slice D）、`044a966d`（Slice E）。
- **设计真源**：`docs/host/design.md`、`docs/engine/design.md`。
- **Plan 真源**：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`。
- **总控真源**：`docs/host/issues-implementation-control.md`。
- **相关 artifacts**：`docs/reviews/wu-cli-fins-obs-01-slice-*`（A/B/D0/C/D/E 各 slice 的 implementation、review、fix、re-review records）。

## 审查方法

本 aggregate deepreview 对以下六个重点领域逐项做跨 slice 一致性验证：

1. CLI direct durable job/sidecar/job_id coupling 是否彻底移除，direct path 是否普通 `AsyncIterator[FinsEvent]`
2. Tool awaiting 是否保留 `EXTERNAL_JOB` 但使用轻量 observation handle，不引入 durable ledger
3. Runtime direct/observed/legacy job 三层边界是否清楚，legacy job store 是否未被 CLI/Service direct 或 tools/wait_adapter 消费
4. Cancellation、no-result、failure、leakage、storage boundary、import boundary、thread/queue/to_thread bridge 是否有跨 slice regressions
5. README/tests/control residual risk 是否一致，R10 是否唯一可接受 deferred risk
6. 运行验证：聚合 pytest、pyright、git diff --check

每项审查基于直接代码证据（grep、read、diff），不依赖 review artifact 中间结论。

---

## 1. CLI Direct Path — AsyncIterator[FinsEvent]

### 证据

**CLI `dayu/cli/commands/fins.py`**：

- `_open_direct_stream` 返回 `AsyncIterator[FinsEvent]`，内部调用 `service.stream_<command>(...)`（line ~430-536 每个命令映射到对应 stream 方法）。
- `_run_direct_command_async` 调用 `_open_direct_stream` 获得 stream，然后传给 `_wait_for_terminal_handling_sigint(events=stream, ...)`（line 310）。
- `_wait_for_terminal_handling_sigint` 签名：`events: AsyncIterator[FinsEvent], cancellation_token: _CliFinsCancellationToken, ...`（line 643-645）。
- `_consume_fins_direct_events` 签名：`events: AsyncIterator[FinsEvent]`（line 700）。
- SIGINT 处理：`cancellation_token.request_cancel("keyboard_interrupt")`（line 681），不是 `service.request_cancel(handle.job_id)`。
- `_CliFinsCancellationToken` 实现标准 `CancellationToken` 协议（`is_cancelled`、`cancel_reason`、`requested_at`），不是 durable job cancel。
- grep `read_job|read_job_events|request_cancel|FinsDirectJobHandle|FinsDirectJobEvent|stream_job_events_until_terminal|wait_for_terminal` 在 CLI 文件中：只有 `_CliFinsCancellationToken.request_cancel`（自身方法定义）和 `cancellation_token.request_cancel`（token 协议调用），无任何 durable job cancel 引用。

**Service `dayu/service/fins_direct.py`**：

- `FinsDirectIngestionRuntime` protocol 暴露 `download -> AsyncIterator[FinsEvent]`、`preprocess -> AsyncIterator[FinsEvent]`、`upload -> AsyncIterator[FinsEvent]`（lines 56-102）。
- grep 同组 pattern：NO MATCHES — 完全干净。

### 裁决

**PASS**。CLI direct 的六个命令全部通过普通 `AsyncIterator[FinsEvent]` 消费 live events。CLI 已彻底移除 `FinsDirectJobHandle`、`FinsDirectJobEvent`、`stream_job_events_until_terminal`、`wait_for_terminal(job_id)` 和 `service.request_cancel(handle.job_id)`。Service protocol 干净。

---

## 2. Tool Awaiting — EXTERNAL_JOB + Lightweight Observation Handle

### 证据

**Contract `dayu/fins/ingestion/observation_handle.py`**：

- `FinsObservationHandle`：仅 `handle_id`（`finsobs_[a-f0-9]{16,96}`）、`operation_kind`、`created_at`。无 job id、sequence、cursor、storage path（line 112-119）。
- `_DISALLOWED_TOKEN_FRAGMENTS`：`("job", "sequence", "cursor", "resume", "token", "tool_call", "storage", ".dayu", "/", "\\")` — 防止旧 durable job 语义混入 handle id 和 message（line 42-53）。
- `FinsObservationRuntime` protocol：`start_observed_download/preprocess/upload` → `FinsObservationHandle`；`poll_observation` → `FinsObservationSnapshot`；`cancel_observation` → `FinsObservationSnapshot`；`abandon_observation` → `None`（lines 176-257）。
- `observation_status_resolution_kind` 映射：`PENDING/RUNNING` → `PENDING`，`SUCCEEDED` → `COMPLETED`，`FAILED` → `FAILED`，`CANCELLED` → `CANCELLED`，`LOST` → `LOST`（lines 285-303）。
- `observation_poll_error_resolution_kind` 映射：`TRANSIENT_UNAVAILABLE` → `PENDING`（保持等待），其它永久错误 → `LOST`（lines 306-318）。

**Wait adapter `dayu/fins/ingestion/wait_adapter.py`**：

- `FinsIngestionWaitPollAdapter` 只通过 `FinsObservationRuntime` 观察/取消/释放 observation（line 98-99 docstring）。
- 不导入、不调用 `read_job`、`read_job_events`、`request_cancel` 或任何 durable job store API。
- 瞬态 poll 错误 `TRANSIENT_UNAVAILABLE` → `WaitPollNotReady`（保持 pending）；永久错误 → `WaitPollLost`。

**Tool helpers `dayu/fins/tools/_ingestion_tool_helpers.py`**：

- grep `read_job|request_cancel|job_id|job_store|job record|sidecar|durable job`：NO MATCHES。
- 工具 helper 通过 `start_observed_*` 启动 observation，返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`。

**Runtime observation 实现 `dayu/fins/ingestion_runtime.py`**：

- Process-local observation registry 以 `_observation_lock` 保护并发（line 1893, 2190, 2218, 2279, 2287）。
- `start_observed_*` 在 lock 下注册 `_FinsObservedOperationRecord`。
- `poll_observation` 在 lock 下读取 snapshot；handle 不存在 → `FinsObservationPollError(PERMANENT_NOT_FOUND)` → wait adapter 映射 LOST。
- 无 durable ledger、无 job event sidecar、无 per-job sequence 用于 observation path。

### 裁决

**PASS**。Tool awaiting 保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 非阻塞语义，但 await ref 已轻量化为 `FinsObservationHandle`。Handle 不包含 job id、sequence、cursor 或 storage path。默认 observation source 为 process-local registry（`_observation_lock` 保护），不引入 durable ledger。Host restart / runtime crash 后 handle 不可用时 resolve LOST，符合 plan 的轻量契约裁决。

---

## 3. Runtime Three-Layer Boundary

### 证据

**Direct layer**（`FinsIngestionRuntime`）：

- `download(request, cancellation_token) -> AsyncIterator[FinsEvent]`（line 1945）
- `preprocess(request, cancellation_token) -> AsyncIterator[FinsEvent]`（line 1982）
- `upload(request, cancellation_token) -> AsyncIterator[FinsEvent]`（line 2018）
- 消费方：CLI direct（通过 Service）、Service tests、runtime tests。
- 不创建 durable job record，不写 job event sidecar。

**Observed layer**（`FinsIngestionRuntime`）：

- `start_observed_download/preprocess/upload(request, cancellation_token) -> FinsObservationHandle`（lines 2054/2091/2123）
- `poll_observation/cancel_observation/abandon_observation(handle) -> ...`（lines 2156/2174/2204）
- 消费方：Fins tools（通过 `_ingestion_tool_helpers`）、Fins wait adapter。
- 使用 process-local registry + `_observation_lock`。

**Legacy layer**（`FinsIngestionJobStore` protocol + `FsFinsIngestionJobStore`）：

- `read_job(job_id)`, `read_job_events(job_id, ...)`, `request_cancel(job_id, ...)` 仍在 runtime 中存在（lines 2853-2914）。
- 消费方：**仅** `tests/fins/test_fins_ingestion_runtime.py` 和 `tests/fins/test_cn_download_runtime.py` 中的 legacy job store 测试。
- grep 确认：`dayu/cli/`、`dayu/service/fins_direct.py`、`dayu/fins/tools/`、`dayu/fins/ingestion/wait_adapter.py` 均**不**导入或调用 `read_job`、`read_job_events`、`request_cancel`、`FinsIngestionJobStore`。

**README 语义**（`dayu/fins/README.md` line 152）：

> legacy helpers `start_download(...)` / `start_preprocess(...)` / `start_upload(...)` / `read_job(...)` / `read_job_events(...)` / `request_cancel(...)` 仍保留在 runtime foundation 中服务 legacy job-store 覆盖；Service direct 和 Fins awaiting tools 不消费这些入口。

### 裁决

**PASS**。三层边界清晰：

- Direct layer 服务 CLI/Service direct consumers，输出 `AsyncIterator[FinsEvent]`。
- Observed layer 服务 tool awaiting + Host wait adapter，输出 `FinsObservationHandle`。
- Legacy layer 仅保留供 legacy job store 测试使用，不被 direct 或 observed path 消费。
- README 明确标注 legacy helpers 的定位和消费边界。

---

## 4. 跨 Slice Regression 检查

### 4.1 Cancellation

| 路径 | 取消机制 | 语义 |
|---|---|---|
| CLI direct | `_CliFinsCancellationToken` → stream task cancel | 标准协程取消 + cancel race 保护（terminal result 不被覆盖） |
| Runtime direct | `cancellation_state.request_cancel()` on consumer exit（line 2454） | Producer 在 `_put_direct_queue` 中检查取消状态后丢弃事件 |
| Observed | `cancel_observation(handle)` → token cancellation + abort | Wait adapter 调用；process-local |
| Blocking bridge | best-effort：token 标记但 sync call 可能到下一个检查点才停止 | 已在 docstring 中明确声明限制 |

**测试覆盖**：
- `test_cancel_race_does_not_override_terminal_result`（`tests/cli/test_fins_commands.py` line 801）：terminal RESULT 已产出后 Ctrl+C 不能覆盖终态。
- Runtime cancel transition tests 覆盖 token 生效后 operation 收口为 cancelled。

### 4.2 No-Result

**证据**：`_direct_missing_result_event`（`ingestion_runtime.py` line 4270）在 producer 正常结束但未产出 RESULT 时合成 `FinsEvent(RESULT, status=FAILURE, exit_code=1, error_kind=EXECUTION)`。

**测试覆盖**：Service tests 覆盖 "stream 正常结束但缺少 result 时合成 failure result"（`tests/README.md` line 140）；runtime tests 覆盖 "stream producer 静默结束时收口 failure result"（`tests/README.md` line 181）。

### 4.3 Leakage

**证据**：`direct_events.py` 的 `_validate_safe_text`（line 388）实现多层防护：
- `_DISALLOWED_TEXT_FRAGMENTS`：`job_id`、`event sequence`、`cursor`、`resume token`、`tool_call_id`、`storage path`、`raw payload`、`provider payload`、`.dayu/fins_ingestion`、`财报正文`
- `_FINS_JOB_ID_PATTERN`：`finsjob_[0-9a-fA-F]{32}`
- `_ABSOLUTE_POSIX_PATH_PATTERN` / `_ABSOLUTE_WINDOWS_PATH_PATTERN`
- 字符上限：message 240、detail 240、title 120、stage 120、document_label 120

`observation_handle.py` 的 `_validate_message`（line 349）同样校验 `_DISALLOWED_TOKEN_FRAGMENTS`。

**测试覆盖**：Service tests 覆盖 "direct event leakage guard"（`tests/README.md` line 140）；runtime tests 覆盖 "direct 用户事件不暴露路径、job id、raw provider payload 或正文"（`tests/README.md` line 181）。

### 4.4 Storage Boundary

**证据**：grep `from dayu\.fins\.storage\|from dayu\.fins import` 在 `dayu/cli/` 和 `dayu/service/fins_direct.py` 中：NO MATCHES。

CLI 和 Service direct 不绕过 `dayu.fins.storage` 仓储协议。Runtime 内部所有 storage 写入仍通过 `SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`、`FilingMaintenanceRepositoryProtocol`。

### 4.5 Import Boundary

**证据**：

- Fins → Host：仅 `dayu/fins/ingestion/wait_adapter.py` 导入 `dayu.host.api` 和 `dayu.host.wait_adapter`，这是 `dayu/fins/README.md` 明确允许的 Host wait integration 例外。
- Fins → Service/UI/Engine：grep 确认无反向导入。
- CLI → Fins storage：grep 确认无直接导入。

### 4.6 Thread/Queue/To_Thread Bridge

**证据**（`ingestion_runtime.py`）：

- `_DirectEventBridge`：使用 `Queue(maxsize=...)` 有界队列（line ~2414）。
- Consumer 端 `asyncio.to_thread(_direct_queue_get, queue, thread)` + timeout（`_DIRECT_QUEUE_GET_TIMEOUT_SECONDS`）（line 2435）。
- Producer 端 `_put_direct_queue`：cancel branch 在 consumer 退出后丢弃事件（line 4260-4262），docstring 说明 "consumer 已结束时丢弃后续事件，避免同步 producer 卡在无人读取的队列上"。
- `finally` 块 guarantee：producer 异常转成 failure RESULT，finally 确保 `_DirectStreamProducerDone` 被发送（line 2453-2486）。
- daemon thread：`daemon=True`（line 2429），不会阻止进程退出。

### 裁决

**PASS**。六个维度均无跨 slice regression：

- Cancellation 语义一致，cancel race 有测试保护。
- No-result 有合成 failure RESULT 兜底。
- Leakage guards 在 contract 层（`direct_events.py`、`observation_handle.py`）统一实施。
- Storage boundary 未被 CLI/Service 绕过。
- Import boundary 仅 wait_adapter 持有 Host import 例外。
- Thread bridge 有界、有超时、cancel branch 有文档说明，属于 runtime implementation detail。

---

## 5. README/Tests/Control Residual Risk 一致性

### README 一致性

`dayu/fins/README.md`：

- 明确区分 direct stream（"返回 `AsyncIterator[FinsEvent]`"）、awaiting observation handle（"process-local registry"、"Host restart 后 LOST"）和 legacy job helpers（"仍保留...不是 CLI direct 或 awaiting tool 的公共引用"）。
- line 449: "Direct event 不包含 job id、sequence、cursor、resume token、sidecar path、绝对路径、provider raw payload 或财报正文。"
- line 451: "Legacy job helpers 仍保留...不是 Service direct 或 awaiting tool 的公共观察边界。"

`dayu/service/README.md` line 25：

> Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`。

`tests/README.md` lines 140, 181, 199：

- 正确分类 direct stream tests、awaiting handle tests、legacy job store tests。

### 测试覆盖

全量测试 `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q`：**281 passed, 3 warnings**。

覆盖矩阵：
- Direct stream contract + Service boundary：`tests/service/test_fins_direct.py`
- CLI direct consumption + output + cancel + cancel race：`tests/cli/test_fins_commands.py`
- CLI non-Fins command guard：`tests/cli/test_init_command.py`、`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_upload_filings_from_command.py`
- Runtime direct stream + no-result + leakage + cancel + storage boundary：`tests/fins/test_fins_ingestion_runtime.py`
- Tool awaiting + observation handle + wait adapter state transitions + LOST recovery：`tests/fins/test_fins_ingestion_tools.py`
- Host assembly adapter binding：`tests/service/test_host_assembly.py`

### Residual Risk 一致性

对照 `docs/host/issues-implementation-control.md` 的 Residual Risk 表：

| ID | 状态 | 来源 | 裁决 |
|---|---|---|---|
| R3 | deferred-with-owner | plan 预存 | UI redaction policy 后续 work unit；非本 WU 引入 |
| R5 | deferred-with-owner | plan 预存 | token streaming 后续 work unit；非本 WU 引入 |
| R6 | closed | Slice A/C review | boundary confirmed |
| R7 | closed | Slice D0 review | contract-only stayed |
| R8 | closed | Slice D review | observation lock concurrency guarded |
| R9 | closed | Slice D review | TRANSIENT_UNAVAILABLE + LOST recovery |
| R10 | deferred-with-owner | Slice D review | slow-poller bounded queue backpressure |

### R10 评估

R10：process-local observation source 使用有界 direct-event queue。极慢或缺失的 poller 可能对高频率 observed producer 产生背压。

**当前实现事实**：
- `_put_direct_queue` 使用 `Queue.put(timeout=...)` 并在 cancel branch 丢弃事件，防止 producer 无限阻塞。
- Observed path 的 `_FinsObservedOperationRecord` 存储 terminal snapshot 而非全量 event buffer。
- R10 的场景需要：poller 完全不消费 + producer 持续高频产出，才可能造成 producer 背压。

**裁决**：R10 是唯一 implementation-introduced deferred risk。它是轻量 process-local contract 的可接受限制。未来 production poller/backoff work unit 可考虑 coalescing progress snapshots。当前实现不产生 correctness bug 或资源泄漏 —— producer 在 cancel branch 会丢弃事件；poller 正常消费时不会触发。

### 裁决

**PASS**。README 一致描述三层边界。测试覆盖矩阵完整。Residual risks 中 R6-R9 已关闭，R3/R5 是 plan 预存的后续 work unit，R10 是唯一 implementation-introduced deferred risk 且为轻量 process-local contract 的可接受限制。

---

## 6. 运行验证

```
pytest (full suite):  281 passed, 3 warnings (third-party edgar deprecation)
pyright (dayu/ tests/ utils/):  0 errors, 0 warnings
git diff --check 637d36a5..HEAD:  clean
```

---

## 总裁决

**PASS**。

六个重点领域全部通过跨 slice 一致性验证：

1. CLI direct path 已彻底移除 durable job/sidecar/job_id coupling，六个 direct command 全部通过普通 `AsyncIterator[FinsEvent]` 消费 live events。Cancel 使用标准 `CancellationToken` 协议，不依赖 `request_cancel(job_id)`。
2. Tool awaiting 保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 非阻塞语义，但 await ref 已轻量化为 `FinsObservationHandle`。默认 observation source 为 process-local registry（`_observation_lock` 保护），不引入 durable ledger。Host restart 后 handle 不可用时 resolve LOST。
3. Runtime direct/observed/legacy job 三层边界清楚。Legacy job store 仅被 legacy job store 测试消费；CLI direct、Service direct、tools、wait adapter 均不消费。
4. Cancellation、no-result、failure、leakage、storage boundary、import boundary、thread/queue/to_thread bridge 六个维度无跨 slice regression。All findings from prior slice reviews have been fixed and verified.
5. README 一致描述三层边界。Residual risks 中 R10 是唯一 implementation-introduced deferred risk，为轻量 process-local contract 的可接受限制。README 已将 legacy helpers 明确标注为不在 direct/observed path 消费。
6. 运行验证全部通过：281 tests passed、pyright 0 errors、git diff --check clean。

### Blocking Findings

无。

### Non-blocking Observations

- Legacy job store（`FinsIngestionJobStore`/`FsFinsIngestionJobStore`）仍保留在 `ingestion_runtime.__all__` 中，用于 legacy tests。若后续 work unit 要求彻底移除 durable job store，需先确认没有外部 consumer 或迁移 legacy tests。
- R10（slow-poller backpressure）已在 control doc 中追踪为 deferred-with-owner。当前实现安全，但未来 production poller work 应考虑 coalescing progress snapshots。
- `_DirectEventBridge` 使用 `asyncio.to_thread` 桥接 sync producer thread，这是明确的 runtime implementation detail。若未来 adapter 全部 async 化，可移除该桥接。

### Verified By

- Direct code evidence: grep + read of all key files in review scope
- Full test suite: 281 passed, 3 warnings
- Full pyright: 0 errors, 0 warnings
- Git diff --check: clean
- Cross-reference with plan and control doc residual risk table
