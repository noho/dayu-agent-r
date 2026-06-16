# WU-CLI-FINS-OBS-01 Slice C Code Review (AgentDS)

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: review
- Reviewer: AgentDS
- Date: 2026-06-16
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-slice-c-implementation-codex.md`
- Plan 真源: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 控制文档: `docs/host/issues-implementation-control.md`

## Scope

本 review 只审查未提交 diff 中的三个文件：

- `dayu/fins/ingestion_runtime.py` (1453 行变更)
- `tests/README.md` (8 行变更)
- `tests/fins/test_fins_ingestion_runtime.py` (172 行变更)

## 验证结果

### 测试

```
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
59 passed, 3 warnings in 2.62s
```

全部 59 个测试通过（包含 4 个新增 direct stream 测试 + 55 个已有测试全部保留通过）。

### Pyright

```
source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py
0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### 交叉验证

```
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q
98 passed, 3 warnings in 2.30s
```

Slice A/B 测试全部保持通过，无回归。

## 逐项核对

### 1. Direct download/preprocess/upload 是否返回 AsyncIterator[FinsEvent]，产出 progress + 唯一 RESULT，且不静默结束

**结论：PASS。**

证据：

- `FinsIngestionRuntime.download()` 返回 `AsyncIterator[FinsEvent]`（`ingestion_runtime.py:1910-1945`），通过 `_run_direct_stream` 桥接同步 producer 线程。
- `FinsIngestionRuntime.preprocess()` 返回 `AsyncIterator[FinsEvent]`（`ingestion_runtime.py:1947-1981`）。
- `FinsIngestionRuntime.upload()` 返回 `AsyncIterator[FinsEvent]`（`ingestion_runtime.py:1983-2017`）。
- 每个 producer 都先 emit progress（如 `_emit_context_progress` at line 2150），再 emit 唯一 RESULT（如 `_emit_direct_result` at line 2175）。
- `_run_direct_stream` 在 line 2085-2091 对 RESULT 做去重（`result_seen` 守卫），产出第一个 RESULT 后立即 break。
- Producer 异常在 `_run_direct_stream_producer`（line 2113-2123）被 catch 并转成 `RESULT(status=FAILURE)`。
- 对静默结束的防御：三个 producer（`_produce_direct_download/preprocess/upload`）的实现路径均以 `_emit_direct_result(...)` 或 `_emit_direct_cancelled_result(...)` 收口；Service 层 `_ensure_terminal_result`（`fins_direct.py:497-510`）提供额外安全网。

**发现 DS-C01（见下文 Findings 章节）**：runtime 自身在 `ProducerDone` 到达但 `result_seen=False` 时不合成 failure RESULT，依赖 Service 层安全网。当前所有 producer 路径均覆盖此 case，不阻塞。

### 2. Direct path 是否不调用 start_*、不创建 durable job record、不写 job event sidecar、不依赖 job id/sequence/cursor

**结论：PASS。**

证据：

- `download/preprocess/upload` 均直接委托 `_run_direct_stream`（line 1932-1945, 1969-1981, 2005-2017），不经过 `start_download/start_preprocess/start_upload`。
- `_FinsIngestionExecutionContext` 在 direct path 中 `job_record=None`（line 2062），`direct_queue` 为有界 `Queue(maxsize=32)`（line 2048）。
- `_emit_context_progress`（line 3682-3723）按 `context.job_record is not None` 分支：direct path 走 `_direct_progress_event` + `_put_direct_queue`，不写 `.events.jsonl` sidecar。
- 测试 `test_direct_download_stream_writes_storage_and_does_not_create_job_record`（test line 920-953）断言 `jobs_dir` 下无 `.json` 和 `.jsonl` 文件。
- Direct events 不含 `job_id`、`sequence`、`cursor` 字段。`FinsEvent` contract 定义在 `dayu/fins/direct_events.py`，不携带 job 治理字段。

### 3. 旧 job store/read_job/read_job_events/request_cancel 是否仅保留给 awaiting legacy path，未被 CLI/Service direct path 使用

**结论：PASS。**

证据：

- `start_download/start_preprocess/start_upload`（line 2329, 2386, 2442）仍存在，保留 durable job record 创建和后台 executor 提交。
- `read_job/read_job_events/request_cancel` 仍存在，仅被 `dayu/fins/ingestion/wait_adapter.py:122`（`read_job`）和 `wait_adapter.py:148`（`request_cancel`）调用。
- Service direct path：`grep` 确认 `dayu/service/fins_direct.py` 不含 `start_download`、`start_preprocess`、`start_upload`、`read_job`、`read_job_events`、`request_cancel`、`job_id`、`FinsDirectJobHandle`、`stream_job_events` 任何引用。
- CLI direct path：`dayu/cli/commands/fins.py` 仅含 `_FinsSigintMonitor.request_cancel`（line 127，本地取消监视器），不调用 `service.request_cancel(job_id)`。

### 4. 内部 producer thread / queue / asyncio.to_thread bridge 是否 bounded、只作为 runtime implementation detail、不外露、不声称强取消；若过度设计或违反 async 裁决请标 blocking

**结论：PASS。不阻塞。**

证据：

- Queue bounded：`Queue(maxsize=_DIRECT_EVENT_QUEUE_MAX_SIZE)` = 32（line 2048）。
- Bridge 是 `_run_direct_stream` 内部实现细节：创建 daemon thread → `asyncio.to_thread` 消费 queue → 事件 yield → 最终设置 cancel state。不暴露在 public API、Service protocol、tool schema、Host wait adapter contract 或 README 中。
- 取消语义：operation-scoped `_DirectCancellationChecker`（line 1140-1161）结合 `CancellationToken` + `_DirectStreamCancellationState`。同步 adapter 在 `cancellation_checker()` 检查点（如 `_execute_download_request` line 3048/3061）响应取消。`_run_direct_stream` finally block（line 2093）设置 cancel state 通知 producer 停止。
- 不强声称强取消：测试 `test_direct_download_uses_operation_scoped_cancellation_token`（test line 977-1001）使用 `_CancelOnSecondCheckToken`，验证 token 在 checker 检查点生效后返回 `CANCELLED` RESULT（exit_code=130）。Codex implementation artifact 明确声明 "direct bridge 取消是 best-effort cooperative"。
- 不共享跨 operation state：每次 `_run_direct_stream` 调用创建独立 queue、thread、cancellation_state，无 daemon、无持久化 worker、无共享状态。
- `asyncio.to_thread` 仅在两处使用：`_direct_queue_get`（line 2076-2080）和 Service 层的 stream consumption。不构成架构级 bridge pattern。

### 5. Cancellation、exception、unsupported source、upload failure、leakage guard、storage repository boundary 是否正确

**结论：PASS。**

逐个子项：

- **Cancellation**：`_DirectCancellationChecker` 合并 `CancellationToken.is_cancelled()` 与本地 `_DirectStreamCancellationState`（line 1146-1161）。Producer 在关键检查点（line 2162, 2217, 2307, 3048, 3061）调用 checker。取消产出 `RESULT(status=CANCELLED, exit_code=130)`（line 3775-3795）。
- **Exception**：`_run_direct_stream_producer` 的 `except Exception`（line 2115）捕获所有业务异常，转为 `RESULT(status=FAILURE)`。异常分类 `_classify_direct_error`（line 4171-4190）按 `USER_INPUT/STORAGE/EXECUTION/UNKNOWN` 归类。错误消息 `_safe_direct_error_message`（line 4193-4221）过滤路径、job id、raw payload 泄漏。
- **Unsupported source**：测试 `test_direct_download_unsupported_source_returns_failure_result`（test line 957-973）验证 `source="unknown"` 产出 `FAILURE` RESULT，错误消息含 "不支持的下载来源"，exit_code=1。
- **Upload failure**：`_produce_direct_upload` 在 `upload_runner is None` 时（line 2274-2288）产出 `FAILURE` RESULT；在 `summary.status == "failed"` 时（line 2310-2319）产出 `FAILURE` RESULT。
- **Leakage guard**：测试 `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text`（test line 1493-1526）验证 event text 不含 `str(tmp_path)`、文件名、`finsjob_` prefix、raw payload 文本、财报正文。`_direct_progress_event`（line 3908-3947）只用 `normalized_ticker`、`source_kind.value`、`document_id` short label 和 bounded progress units。`_download_result_details/_preprocess_result_details/_upload_result_details`（line 4097-4168）仅投影 bounded count 和 business label。
- **Storage repository boundary**：`_store_downloaded_document`（line 3110）通过 `source_repository`、`blob_repository`、`filing_maintenance_repository` 写入。测试 `test_direct_download_stream_writes_storage_and_does_not_create_job_record` 验证 `source_repository.get_source_meta()` 和 `blob_repository.read_file_bytes()` 可读回写入的产物。

### 6. README impact 和 tests 是否合规

**结论：PASS。**

- `tests/README.md` 已更新（8 行变更）：
  - CLI Fins direct 测试描述从 `request_cancel(job_id)` 调整为 operation-scoped async cancellation + cancel race 收口。
  - Service Fins direct 测试描述从 job event / durable cancel API 调整为 `AsyncIterator[FinsEvent]` pass-through 与 no-job-handle boundary。
  - `tests/fins/test_fins_ingestion_runtime.py` 覆盖说明加入 direct stream、无 durable job record/sidecar、operation-scoped cancellation 与 leakage guard 覆盖。
- `dayu/fins/README.md`：Implementation artifact 确认已读取其 Agent 更新约束，但该 README 当前仍包含 durable Fins job 开发手册描述。按 replacement plan Slice E 集中同步 README 的约定，本 slice 不编辑此文件。该判断符合 plan 要求。
- 测试覆盖：4 个新增 direct stream 测试 + 所有旧 job store/sidecar 测试保留（作为 awaiting legacy path 回归保护）。新测试覆盖：
  - direct download storage write + no job record（test line 920-953）
  - unsupported source → failure result（test line 957-973）
  - operation-scoped cancellation token（test line 977-1001）
  - direct upload leakage guard（test line 1493-1526）

## Findings

### Finding DS-C01: Runtime `_run_direct_stream` 在 ProducerDone 到达但无 RESULT 时不合成 failure RESULT

- **文件**: `dayu/fins/ingestion_runtime.py:2073-2091`
- **严重度**: Low
- **是否阻塞**: 否

**详述**：

`_run_direct_stream` 的 consumer loop 在收到 `_DirectStreamProducerDone` 哨兵时直接 `break`（line 2083-2084），不检查 `result_seen` 是否为 True。若 producer 因 `BaseException`（非 `Exception` 子类，如 `KeyboardInterrupt` 在 daemon thread 中）退出，或未来 producer 实现有 bug 未 emit RESULT，runtime stream 将静默结束。

当前事实：
- 三个 producer 实现均在正常路径以 `_emit_direct_result` 或 `_emit_direct_cancelled_result` 收口。
- `_run_direct_stream_producer` 的 `except Exception` 捕获业务异常并转成 failure RESULT。
- Service 层 `_ensure_terminal_result`（`fins_direct.py:497-510`）在 stream 正常结束但缺少 RESULT 时合成 failure RESULT，提供端到端安全网。

**建议**：在 `_run_direct_stream` 的 loop break 后增加防御检查：若 `not result_seen`，yield 一个 `FAILURE` RESULT 说明 producer 未产出终态。这属于 defense-in-depth，当前所有代码路径均覆盖，不阻塞合并。

```python
# 建议在 line 2091 (break) 之后、finally 之前增加:
if not result_seen:
    yield _direct_missing_result_event(context)
```

### Finding DS-C02: `_put_direct_queue` 在取消后静默丢弃事件，无明确文档说明

- **文件**: `dayu/fins/ingestion_runtime.py:3877-3905`
- **严重度**: Low（观察项）
- **是否阻塞**: 否

**详述**：

`_put_direct_queue` 在 `cancellation_state.is_cancelled()` 为 True 时返回 `False`（line 3899-3900）。调用方（`_emit_context_progress` at line 3723、`_emit_direct_result` at line 3773）均不检查返回值，事件被静默丢弃。这在语义上正确——已取消的 consumer 不需要更多事件——但代码中未注释说明此行为是有意设计。建议在 `_put_direct_queue` docstring 或调用处添加一行注释："consumer 已取消时丢弃事件是预期行为"。

## 未覆盖项 / Residual Risk

- **`dayu/fins/README.md` durable job 文档描述**：仍待 Slice E 集中同步。归类为 covered by later approved slice。
- **Tools awaiting / wait adapter 仍依赖旧 job store**：`wait_adapter.py` 仍调用 `read_job/request_cancel`。归类为 covered by Slice D lightweight observation handle migration。
- **Runtime no-result 防御**：见 DS-C01。当前端到端行为正确（Service 层安全网），不阻塞。

## 结论

**PASS-WITH-FINDINGS**

Slice C 实现了 replacement plan 规定的 Fins ingestion runtime core API convergence：

1. Direct download/preprocess/upload 均返回 `AsyncIterator[FinsEvent]`，产出 PROGRESS + 唯一 RESULT。
2. Direct path 不调用 `start_*`，不创建 durable job record，不写 job event sidecar，不依赖 job id/sequence/cursor。
3. 旧 job store/read_job/read_job_events/request_cancel 仅保留给 awaiting legacy path（`wait_adapter.py`），CLI/Service direct path 不引用。
4. 内部 producer thread + bounded queue + `asyncio.to_thread` bridge 仅作为 runtime implementation detail，不外露，不声称强取消。设计符合 plan 的 async 裁决。
5. Cancellation（operation-scoped token/checker）、exception → FAILURE RESULT、unsupported source → FAILURE RESULT、upload failure → FAILURE RESULT、leakage guard（无 path/job id/raw payload/正文）、storage repository boundary 均正确实现且有测试覆盖。
6. `tests/README.md` 已更新；`dayu/fins/README.md` 按 plan 约定延迟到 Slice E。测试 59/59 通过，pyright 0 errors，Slice A/B 交叉测试 98/98 通过。

Findings DS-C01 和 DS-C02 均为 Low 严重度、非阻塞：DS-C01 是 defense-in-depth 建议，当前 Service 层安全网已保证端到端正确性；DS-C02 是文档补全建议。两项均不要求在当前 slice 修复，可推迟到 Slice E 或后续 cleanup。
