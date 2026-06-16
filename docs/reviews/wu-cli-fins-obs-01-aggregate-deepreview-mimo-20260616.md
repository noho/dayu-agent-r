# WU-CLI-FINS-OBS-01 Aggregate Deepreview (AgentMiMo)

## 范围与真源

- **Review 类型**：aggregate deepreview，审查 accepted replacement implementation 的跨 slice 完整性。
- **Review 范围**：commits `637d36a5`/`612b6b05` → `044a966d`，重点审查 `f79b59ab`（Slice A/B）、`a90d86aa`（Slice D0）、`11fd5e97`（Slice C）、`0b25416d`（Slice D）、`044a966d`（Slice E）。
- **设计真源**：`docs/host/design.md`、`docs/engine/design.md`。
- **Plan 真源**：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`。
- **总控真源**：`docs/host/issues-implementation-control.md`。
- **相关 artifacts**：`docs/reviews/wu-cli-fins-obs-01-slice-*`（A/B/D0/C/D/E 各 slice 的 implementation、review、fix、re-review records）。

## 审查方法

本 aggregate deepreview 对以下六个重点领域逐项做跨 slice 一致性验证。每项审查基于直接代码证据（grep、read、diff、test run），不依赖 review artifact 中间结论。

---

## 1. CLI Direct Path — AsyncIterator[FinsEvent]

### 证据

**CLI `dayu/cli/commands/fins.py`**：

- 模块 docstring："CLI 不直接调用 Fins ingestion runtime，不读取 Fins storage，也不把 direct operation 伪装成 Host Run"。
- 六个 direct command 全部通过 `FinsDirectCommandService` 的 `download(...)` / `process(...)` / `process_filing(...)` / `process_material(...)` / `upload_filing(...)` / `upload_material(...)` 返回 `AsyncIterator[FinsEvent]`。
- grep `job_id|sidecar|durable|EXTERNAL_JOB|WaitAdapter|observation_handle|read_job|request_cancel|FinsDirectJobHandle` 在 CLI 文件中：**NO MATCHES**。
- SIGINT 取消通过 `_CliFinsCancellationToken` 实现标准 `CancellationToken` 协议，不依赖 `request_cancel(job_id)`。

**Service `dayu/service/fins_direct.py`**：

- `FinsDirectIngestionRuntime` protocol 暴露 `download -> AsyncIterator[FinsEvent]`、`preprocess -> AsyncIterator[FinsEvent]`、`upload -> AsyncIterator[FinsEvent]`。
- `FinsDirectCommandService` 所有方法返回 `AsyncIterator[FinsEvent]`，不暴露 `FinsDirectJobHandle`、`stream_job_events_until_terminal(...)`、`read_job_events(...)` 或 `request_cancel(...)`。
- `_ensure_result_event` 保证 stream 正常结束时存在唯一 RESULT，缺失时合成 failure RESULT。

### 裁决

**PASS**。CLI direct 的六个命令全部通过普通 `AsyncIterator[FinsEvent]` 消费 live events。CLI 已彻底移除 durable job/sidecar/job_id coupling。Service protocol 干净。

---

## 2. Tool Awaiting — EXTERNAL_JOB + Lightweight Observation Handle

### 证据

**Contract `dayu/fins/ingestion/observation_handle.py`**：

- `FinsObservationHandle`：仅 `handle_id`（`finsobs_[a-f0-9]{16,96}`）、`operation_kind`、`created_at`。无 job id、sequence、cursor、storage path。
- `_DISALLOWED_TOKEN_FRAGMENTS`：`("job", "sequence", "cursor", "resume", "token", "tool_call", "storage", ".dayu", "/", "\\")` — 防止旧 durable job 语义混入 handle id 和 message。
- `FinsObservationRuntime` protocol：`start_observed_download/preprocess/upload` → `FinsObservationHandle`；`poll_observation` → `FinsObservationSnapshot`；`cancel_observation` → `FinsObservationSnapshot`；`abandon_observation` → `None`。
- `observation_handle_id_to_resume_token` / `parse_observation_handle_id_token`：handle id 与 resume token 之间的中立转换。

**Wait adapter `dayu/fins/ingestion/wait_adapter.py`**：

- `FinsIngestionWaitPollAdapter` 只通过 `FinsObservationRuntime` 观察/取消/释放 observation。
- 不导入、不调用 `read_job`、`read_job_events`、`request_cancel` 或任何 durable job store API。
- `build_fins_wait_adapter_registry` 构造 `WaitAdapterBinding(await_kind=EXTERNAL_JOB, resume_policy=POLL, external_job_ref_source=RESUME_TOKEN)`。

**Tool helpers `dayu/fins/tools/_ingestion_tool_helpers.py`**：

- `_awaiting_outcome_from_observation_handle` 通过 `observation_handle_id_to_resume_token(handle)` 构造 `ToolAwaitingOutcome(EXTERNAL_JOB)`。
- grep `read_job|request_cancel|job_id|job_store|job record|sidecar|durable job`：**NO MATCHES**。

**Runtime observation 实现 `dayu/fins/ingestion_runtime.py`**：

- Process-local observation registry 以 `_observation_lock` 保护并发。
- `start_observed_*` 在 lock 下注册 `_FinsObservedOperationRecord`，通过 `executor.submit` 启动后台 producer。
- `poll_observation` 在 lock 下读取 snapshot；handle 不存在 → 返回 LOST snapshot。
- `cancel_observation` 在 lock 下请求取消；`abandon_observation` 在 lock 下移除 record。
- 无 durable ledger、无 job event sidecar、无 per-job sequence 用于 observation path。

### 裁决

**PASS**。Tool awaiting 保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 非阻塞语义，但 await ref 已轻量化为 `FinsObservationHandle`。Handle 不包含 job id、sequence、cursor 或 storage path。默认 observation source 为 process-local registry（`_observation_lock` 保护），不引入 durable ledger。Host restart 后 handle 不可用时 resolve LOST，符合 plan 的轻量契约裁决。

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

- `start_download/start_preprocess/start_upload` 创建 durable job record（lines 2690/2747/2803）。
- `read_job/read_job_events/request_cancel` 仍在 runtime 中存在。
- 消费方：**仅** `tests/fins/test_fins_ingestion_runtime.py` 和 `tests/fins/test_cn_download_runtime.py` 中的 legacy job store 测试。
- grep 确认：`dayu/cli/`、`dayu/service/fins_direct.py`、`dayu/fins/tools/`、`dayu/fins/ingestion/wait_adapter.py` 均**不**导入或调用 legacy job store API。

**README 语义**（`dayu/fins/README.md` line 152）：

> legacy helpers `start_download(...)` / `start_preprocess(...)` / `start_upload(...)` / `read_job(...)` / `read_job_events(...)` / `request_cancel(...)` 仍保留在 runtime foundation 中服务 legacy job-store 覆盖；Service direct 和 Fins awaiting tools 不消费这些入口。

### 裁决

**PASS**。三层边界清晰：Direct layer 服务 CLI/Service direct consumers；Observed layer 服务 tool awaiting + Host wait adapter；Legacy layer 仅保留供 legacy job store 测试使用。README 明确标注 legacy helpers 的定位和消费边界。

---

## 4. 跨 Slice Regression 检查

### 4.1 Cancellation

| 路径 | 取消机制 | 语义 |
|---|---|---|
| CLI direct | `_CliFinsCancellationToken` → stream task cancel | 标准协程取消 + cancel race 保护（terminal result 不被覆盖） |
| Runtime direct | `cancellation_state.request_cancel()` on consumer exit（line 2454） | Producer 在 `_put_direct_queue` 中检查取消状态后丢弃事件 |
| Observed | `cancel_observation(handle)` → token cancellation + wait adapter 调用 abandon | Process-local |
| Blocking bridge | best-effort：token 标记但 sync call 可能到下一个检查点才停止 | 已在 docstring 中明确声明限制 |

**测试覆盖**：
- `test_cancel_race_does_not_override_terminal_result`：terminal RESULT 已产出后 Ctrl+C 不能覆盖终态。
- Runtime cancel transition tests 覆盖 token 生效后 operation 收口为 cancelled。

### 4.2 No-Result

**证据**：`_direct_missing_result_event`（line 4270）在 producer 正常结束但未产出 RESULT 时合成 `FinsEvent(RESULT, status=FAILURE, exit_code=1, error_kind=EXECUTION)`。observation path 的 `_drain_observation_queue` 在 `_DirectStreamProducerDone` 但无 result 时设置 `FAILED` status。

**测试覆盖**：Service tests 和 runtime tests 均覆盖 "stream 正常结束但缺少 result 时合成 failure result"。

### 4.3 Leakage

**证据**：`direct_events.py` 的 `_validate_safe_text` 实现多层防护：
- `_DISALLOWED_TEXT_FRAGMENTS`：`job_id`、`event sequence`、`cursor`、`resume token`、`tool_call_id`、`storage path`、`raw payload`、`provider payload`、`.dayu/fins_ingestion`、`财报正文`
- `_FINS_JOB_ID_PATTERN`：`finsjob_[0-9a-fA-F]{32}`
- `_ABSOLUTE_POSIX_PATH_PATTERN` / `_ABSOLUTE_WINDOWS_PATH_PATTERN`
- 字符上限：message 240、detail 240、title 120、stage 120、document_label 120

`observation_handle.py` 的 `_validate_message` 同样校验 `_DISALLOWED_TOKEN_FRAGMENTS`。

**测试覆盖**：Service tests 覆盖 "direct event leakage guard"；runtime tests 覆盖 "direct 用户事件不暴露路径、job id、raw provider payload 或正文"。

### 4.4 Storage Boundary

**证据**：grep `from dayu\.fins\.storage\|from dayu\.fins import` 在 `dayu/cli/` 和 `dayu/service/fins_direct.py` 中：**NO MATCHES**。CLI 和 Service direct 不绕过 `dayu.fins.storage` 仓储协议。

### 4.5 Import Boundary — **BLOCKING FINDING**

**证据**：

`tests/service/test_import_boundary.py` 定义：
- `SERVICE_FORBIDDEN_PREFIXES = ("dayu.config", "dayu.ui", "dayu.fins")`
- `SERVICE_ALLOWED_IMPORTS = ("dayu.fins.domain.enums", "dayu.fins.ingestion", "dayu.fins.ingestion_runtime", "dayu.fins.service_runtime")`

`dayu/service/fins_direct.py` line 21-31 导入 `dayu.fins.direct_events`，该模块不在 `SERVICE_ALLOWED_IMPORTS` 中，命中 `SERVICE_FORBIDDEN_PREFIXES` 的 `dayu.fins` 前缀。

**运行验证**：
```
FAILED tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers
AssertionError: service import boundary violations:
[('/Users/leo/workspace/dayu-agent-r/dayu/service/fins_direct.py', 'dayu.fins.direct_events')]
```

**根因**：`dayu.fins.direct_events` 是 Slice A/B（commit `f79b59ab`）引入的 contract 模块，定义 CLI、Service 与 Fins runtime direct path 共享的业务事件形态。它的设计意图是被 Service 层消费，但 `SERVICE_ALLOWED_IMPORTS` 白名单未同步更新。

**修复**：在 `tests/service/test_import_boundary.py` 的 `SERVICE_ALLOWED_IMPORTS` 中添加 `"dayu.fins.direct_events"`。

**严重性**：blocking。import boundary 测试是架构守护测试，当前失败会阻止后续 CI 通过。

### 4.6 Thread/Queue/To_Thread Bridge

**证据**（`ingestion_runtime.py`）：

- Direct stream 使用 `Queue(maxsize=...)` 有界队列。
- Consumer 端 `asyncio.to_thread(_direct_queue_get, queue, thread)` + timeout。
- Producer 端 `_put_direct_queue`：cancel branch 在 consumer 退出后丢弃事件，避免同步 producer 卡在无人读取的队列上。
- `finally` 块 guarantee：producer 异常转成 failure RESULT，finally 确保 `_DirectStreamProducerDone` 被发送。
- daemon thread：`daemon=True`，不会阻止进程退出。
- Wait adapter 的 `_run_async_observation` 使用 `asyncio.run()` 在 sync Host poller context 中执行 observation runtime async 方法。

### 裁决

**BLOCKING**。六个维度中 import boundary 存在 1 个 blocking finding：`dayu.fins.direct_events` 未在 `SERVICE_ALLOWED_IMPORTS` 白名单中。其余五个维度（cancellation、no-result、leakage、storage boundary、thread bridge）无跨 slice regression。

---

## 5. README/Tests/Control Residual Risk 一致性

### README 一致性

`dayu/fins/README.md`：
- 明确区分 direct stream（"返回 `AsyncIterator[FinsEvent]`"）、awaiting observation handle（"process-local registry"、"Host restart 后 LOST"）和 legacy job helpers（"仍保留...不是 CLI direct 或 awaiting tool 的公共引用"）。
- "Direct event 不包含 job id、sequence、cursor、resume token、sidecar path、绝对路径、provider raw payload 或财报正文。"

`dayu/service/README.md`：
- "Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`。"

`tests/README.md`：
- 正确分类 direct stream tests、awaiting handle tests、legacy job store tests。

### 测试覆盖

全量 pytest（排除 2 个 pre-existing failure）：**2806 passed, 2 skipped, 7 deselected**。

覆盖矩阵：
- Direct stream contract + Service boundary：`tests/service/test_fins_direct.py`
- CLI direct consumption + output + cancel + cancel race：`tests/cli/test_fins_commands.py`
- CLI non-Fins command guard：`tests/cli/test_init_command.py`、`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_upload_filings_from_command.py`
- Runtime direct stream + no-result + leakage + cancel + storage boundary：`tests/fins/test_fins_ingestion_runtime.py`
- Tool awaiting + observation handle + wait adapter state transitions + LOST recovery：`tests/fins/test_fins_ingestion_tools.py`
- Host assembly adapter binding：`tests/service/test_host_assembly.py`
- Import boundary：`tests/service/test_import_boundary.py` — **FAILING**（见 4.5）

### Pre-existing Failures（不在本 WU 范围）

| 测试 | 状态 | 说明 |
|---|---|---|
| `test_deterministic_two_turn_request_contains_prior_final_answer` | pre-existing | 基线 commit `637d36a5` 即失败；文件未在本 WU commits 中修改 |
| `test_mock_tool_result_feeds_same_run_and_later_run_continuity` | pre-existing | 基线 commit 即失败；文件未在本 WU commits 中修改 |

### Residual Risk 一致性

对照 `docs/host/issues-implementation-control.md` 的 Residual Risk 表：

| ID | 状态 | 裁决 |
|---|---|---|
| R3 | deferred-with-owner | UI redaction policy 后续 work unit；非本 WU 引入 |
| R5 | deferred-with-owner | token streaming 后续 work unit；非本 WU 引入 |
| R6 | closed | Slice A/C review confirmed boundary |
| R7 | closed | Slice D0 review confirmed contract-only |
| R8 | closed | Slice D review confirmed observation lock concurrency |
| R9 | closed | Slice D review confirmed TRANSIENT_UNAVAILABLE + LOST recovery |
| R10 | deferred-with-owner | Slow-poller bounded queue backpressure；轻量 process-local contract 的可接受限制 |

### R10 评估

R10：process-local observation source 使用有界 direct-event queue。极慢或缺失的 poller 可能对高频率 observed producer 产生背压。

**当前实现事实**：
- `_put_direct_queue` 使用 `Queue.put(timeout=...)` 并在 cancel branch 丢弃事件，防止 producer 无限阻塞。
- Observed path 的 `_FinsObservedOperationRecord` 存储 terminal snapshot 而非全量 event buffer。
- R10 的场景需要：poller 完全不消费 + producer 持续高频产出，才可能造成 producer 背压。

**裁决**：R10 是唯一 implementation-introduced deferred risk。它是轻量 process-local contract 的可接受限制。未来 production poller/backoff work unit 可考虑 coalescing progress snapshots。当前实现不产生 correctness bug 或资源泄漏。

### 裁决

**BLOCKING**。README 一致描述三层边界。Residual risks 中 R10 是唯一 implementation-introduced deferred risk。但 import boundary 测试 `test_service_does_not_import_forbidden_layers` 当前 FAILING，需要修复 `SERVICE_ALLOWED_IMPORTS` 白名单。

---

## 6. 运行验证

```
pyright:                    0 errors, 0 warnings
git diff --check 637d36a5..HEAD:  clean
pytest (full suite, excl 2 pre-existing):  2806 passed, 2 skipped, 7 deselected
pytest (import boundary):   FAILING — dayu.fins.direct_events not in SERVICE_ALLOWED_IMPORTS
```

---

## 总裁决

**BLOCKING — 1 finding**。

六个重点领域中五个通过跨 slice 一致性验证，一个存在 blocking finding：

1. ✅ **CLI direct path**：已彻底移除 durable job/sidecar/job_id coupling，六个 direct command 全部通过普通 `AsyncIterator[FinsEvent]` 消费 live events。Cancel 使用标准 `CancellationToken` 协议。
2. ✅ **Tool awaiting**：保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 非阻塞语义，await ref 已轻量化为 `FinsObservationHandle`。Process-local registry + `_observation_lock` 保护，不引入 durable ledger。
3. ✅ **Runtime 三层边界**：Direct/observed/legacy 三层边界清楚。Legacy job store 仅被 legacy job store 测试消费。
4. ❌ **Import boundary**：`dayu/service/fins_direct.py` 导入 `dayu.fins.direct_events`，但该模块未在 `SERVICE_ALLOWED_IMPORTS` 白名单中。`test_service_does_not_import_forbidden_layers` FAILING。
5. ✅ **README/tests/control**：README 一致描述三层边界。Residual risks 中 R10 是唯一 implementation-introduced deferred risk。
6. ✅ **pyright / git diff --check**：通过。

### Blocking Finding

| ID | 文件 | 问题 | 修复 |
|---|---|---|---|
| BF-1 | `tests/service/test_import_boundary.py` | `SERVICE_ALLOWED_IMPORTS` 缺少 `"dayu.fins.direct_events"`，导致 `dayu/service/fins_direct.py` 的 import 被误判为 violation | 在 `SERVICE_ALLOWED_IMPORTS` tuple 中添加 `"dayu.fins.direct_events"` |

### 非阻塞观察

| ID | 说明 |
|---|---|
| NO-1 | DS aggregate deepreview（`wu-cli-fins-obs-01-aggregate-deepreview-ds-20260616.md`）运行了 targeted test subset 而非 full suite，漏检了 import boundary 测试失败 |
| NO-2 | 2 个 pre-existing test failure（`test_deterministic_two_turn_request_contains_prior_final_answer`、`test_mock_tool_result_feeds_same_run_and_later_run_continuity`）不在本 WU 范围，但应在后续排查 |
