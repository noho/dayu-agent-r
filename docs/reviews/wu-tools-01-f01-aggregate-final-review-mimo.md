# WU-TOOLS-01-F01 Aggregate Final Review

## Scope

- Mode: aggregate final review / closeout stance
- Branch: `host-wu-tools-01-f01`
- Base: `main`
- Review date: 2026-06-07
- Output file: `docs/reviews/wu-tools-01-f01-aggregate-final-review-mimo.md`
- Included scope: S1-S6 all production modules, tests, config, READMEs
- Excluded scope: historical review artifacts (docs/reviews/*), OLD code not touched by F01
- Parallel review coverage: 无

## Conclusion

**pass**

## Findings

未发现实质性问题。

## Verification Results

### pytest

```
source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py -v

142 passed, 3 warnings in 1.95s
```

### pyright

```
source .venv/bin/activate && pyright

0 errors, 0 warnings, 0 informations
```

## Detailed Evidence

### 1. F01 原始目标闭环验证

**Goal**: establish one shared `dayu.fins` service/runtime foundation for read, download and preprocess/process.

**Evidence**:

- `dayu/fins/service_runtime.py:36` `DefaultFinsRuntime` assembles read repositories, processor registry, `FinsToolService` (lazy) and `FinsIngestionRuntime` (lazy). All three tool groups share this assembly root.
- `dayu/fins/ingestion_runtime.py:877` `FinsIngestionRuntime` provides `start_download`, `start_preprocess`, `read_job`, `request_cancel`. Download and preprocess pipelines share the same ticker normalization (`dayu.fins.ticker_normalization.normalize_ticker`), storage protocols (`dayu.fins.storage`) and job store (`FsFinsIngestionJobStore`).
- `dayu/fins/tools/download_provider.py:21` and `dayu/fins/tools/preprocess_provider.py:21` each call `DefaultFinsRuntime.create(workspace_root=...)` and `runtime.get_ingestion_runtime()` — same runtime root, same workspace-derived job store.
- `dayu/fins/tools/download_tools.py:70` and `dayu/fins/tools/preprocess_tools.py:69` return `ToolAwaitingOutcome` via `_awaiting_outcome_from_job_start(start)`.
- CLI future wrapper 不在本轮，但 `DefaultFinsRuntime` 是未来 CLI 的唯一业务入口，不存在分叉路径。

### 2. 层级与依赖合规性

**Constraint**: Fins 不反向依赖 Service/UI/Engine；只允许 wait_adapter 精确桥接 Host wait contract；dayu.runtime 不 import Fins。

**Evidence**:

- `grep -r "from dayu.fins" dayu/runtime/` → **无结果**。`dayu.runtime` 不 import `dayu.fins`。
- `grep -r "from dayu.engine" dayu/fins/` → **无结果**。
- `grep -r "from dayu.service" dayu/fins/` → **无结果**。
- `grep -r "from dayu.ui" dayu/fins/` → **无结果**。
- `dayu/fins/ingestion/wait_adapter.py:30-38` imports `dayu.host.api`, `dayu.host.durable.state`, `dayu.host.wait_adapter` — 这是文档要求的精确桥接点，且只在 `wait_adapter.py` 一个文件中。
- `dayu/service/host_assembly.py:22-26` imports `dayu.fins.ingestion` 的常量和 `build_fins_wait_adapter_registry` — Service → Fins 方向合规。

### 3. ToolDiscovery target shape 闭环

**Constraint**: default config 是 `financial-read-tools` / `financial-download-tools` / `financial-preprocess-tools` 三组 disabled entries；workspace overlay 可独立启用；旧 `include_ingestion_tools` 不再是目标配置。

**Evidence**:

- `dayu/config/tool_discovery.json` 包含 5 个 provider，全部 `enabled=false`。Fins 三组：`financial-read-tools`、`financial-download-tools`、`financial-preprocess-tools`。
- `grep -r "include_ingestion_tools" dayu/` → **无结果**。旧配置键已从生产代码完全移除。
- `tests/fins/test_fins_ingestion_tools.py:212` 和 `tests/runtime/test_config_loader.py:388` 以负面断言确认旧键不存在。
- `dayu/config/README.md:175-183` 正确文档化三组 provider 及其独立启用方式。

### 4. Awaiting flow 完整性

**Constraint**: download/preprocess tool returns `ToolAwaitingOutcome`；Service assembly binds `wait_adapter_registry`；poll adapter maps queued/running/cancelling/succeeded/failed/cancelled/missing correctly；`abandon_wait` 只 request_cancel。

**Evidence**:

- `dayu/fins/tools/_ingestion_tool_helpers.py:19-43` `_awaiting_outcome_from_job_start` 构造 `ToolAwaitingOutcome(await_spec=ToolAwaitSpec(await_kind=EXTERNAL_JOB, resume_token=job_id))`。
- `dayu/fins/ingestion/wait_adapter.py:101-125` `FinsIngestionWaitPollAdapter.poll_wait`:
  - `job_id is None` → `WaitPollLost`
  - `FileNotFoundError/ValueError` → `WaitPollLost`
  - `QUEUED/RUNNING/CANCELLING` → `WaitPollNotReady`
  - `SUCCEEDED` → `WaitPollReady(completed_outcome)`
  - `FAILED` → `WaitPollReady(failed_outcome)`
  - `CANCELLED` → `WaitPollReady(cancelled_outcome)`
  - default → `WaitPollLost`
- `dayu/fins/ingestion/wait_adapter.py:127-142` `abandon_wait` 只调用 `runtime.request_cancel(job_id)`，不删除 source docs 或 Host wait records。
- `dayu/service/host_assembly.py:1071-1073` `_tooling_options_from_discovery` 调用 `_fins_wait_adapter_registry_from_provider_configs` 并传入 `HostToolingOptions.wait_adapter_registry`。
- `dayu/service/host_assembly.py:1084-1113` 通过 provider_id/import_path/source_id 三重匹配识别 Fins awaiting provider，并校验同一 assembly 中 workspace_root 一致性。

### 5. Storage/ticker boundary 合规

**Constraint**: 财报文档存取通过 `dayu.fins.storage`；ticker normalization 走公共 API；job store 只存治理状态。

**Evidence**:

- `dayu/fins/ingestion_runtime.py:43-48` imports `dayu.fins.storage` 下的 4 个仓储协议。
- `dayu/fins/ingestion_runtime.py:951` `start_download` 调用 `ticker_normalization.normalize_ticker(request.ticker)`。
- `dayu/fins/ingestion_runtime.py:996` `start_preprocess` 调用 `ticker_normalization.normalize_ticker(request.ticker)`。
- `FsFinsIngestionJobStore` 存储路径 `.dayu/fins_ingestion/jobs`，只保存 `FinsIngestionJobRecord`（job_id, status, timestamps, request_summary, result_summary, failure_summary, cancellation_requested），不保存财报正文。
- `dayu/fins/service_runtime.py:17-28` `DefaultFinsRuntime.create` 通过 `build_fs_repository_set` 构建仓储集，仓储实现由 `dayu.fins.storage` 提供。

### 6. State machine 完整性

**Evidence**:

- 状态枚举 `FinsIngestionJobStatus`: `QUEUED → RUNNING → SUCCEEDED/FAILED/CANCELLED`，另有 `CANCELLING` 中间态。
- `_TERMINAL_STATUSES = {SUCCEEDED, FAILED, CANCELLED}`。
- `_mark_job_running_or_cancelled` (line 1196): 先检查 `cancellation_requested/CANCELLING` → cancelled；再检查 terminal → 原样返回；否则 → running。
- `save_succeeded_or_cancelled` (line 709): 在 file lock 内原子读-判断-写。terminal → 原样返回；`cancellation_requested/CANCELLING` → cancelled；否则 → succeeded。
- `_run_download_job` (line 1153) 和 `_run_preprocess_job` (line 1112): 每个循环迭代先 `read_job` 检查取消请求；pipeline 完成后再检查一次。
- `request_cancel` (line 776): terminal → 原样返回；否则 → CANCELLING。
- `_save_failed_from_exception` (line 1852) 和 `_save_download_unsupported` (line 1819): 二次落盘失败只 warning 日志，不抛出异常。

### 7. WU-TOOLS-01-S4-R1 关闭判定

**同意关闭。**

**证据**:

- S1 建立 `DefaultFinsRuntime` / `FinsIngestionRuntime` 和 durable job store。
- S2/S3 实现 preprocess/download runtime 路径。
- S4 暴露独立 read/download/preprocess providers，download/preprocess 返回 `ToolAwaitingOutcome`。
- S5 将 Fins awaiting jobs 接入 Host wait-resume contract，无 Host/Engine contract 变更。
- S6 对齐默认配置、workspace overlay 测试和 README，移除旧 `include_ingestion_tools`。
- 残余项（SEC/CN/HK 网络 adapter、upload ingestion、CI/smoke 迁移、CLI wrapper）不阻塞 S4-R1 scope（shared Fins ingestion runtime + download/preprocess awaiting providers）。

### 8. Tests/README 足够性

**Tests**:

- `tests/fins/test_fins_ingestion_runtime.py` (1199 lines): job store CRUD、file lock、atomic write、ticker normalization、download pipeline、preprocess pipeline、cancellation flow、edge cases。
- `tests/fins/test_fins_ingestion_tools.py` (1067 lines): download/preprocess tool callable、awaiting outcome、parameter validation、provider discovery、workspace overlay、Host assembly wiring。
- `tests/service/test_host_assembly.py` (+249 lines): Fins await adapter wiring、duplicate binding rejection、workspace root consistency。
- `tests/runtime/test_config_loader.py` (+23 lines): default config loads with three Fins providers。
- `tests/tools/test_combined_tools_acceptance.py` (+7 lines): combined discovery includes Fins providers。
- `tests/host/test_phase7_waiting_integration.py` 和 `tests/host/test_public_resolve_wait_resume.py`: Host wait-resume integration。

**READMEs**:

- `dayu/fins/README.md`: 已更新，覆盖 ingestion runtime、awaiting tools、wait adapter、job store 边界。
- `dayu/config/README.md`: 已更新，文档化三组 Fins providers 及独立启用方式。
- `tests/README.md`: 已更新，覆盖 `tests/fins/` 测试层描述。

## Open Questions

无。

## Residual Risk

1. **并发 file lock 压力测试缺失**: `FsFinsIngestionJobStore` 使用 `fcntl.flock(LOCK_EX)` 进程间互斥锁，当前测试未覆盖高并发竞争场景。低风险：file lock 语义由 OS 保证，且 job store 设计为 workspace-scoped 单进程写入为主。

2. **`_save_cancelled` 未使用原子终态方法**: `FinsIngestionRuntime._save_cancelled` (line 1751) 直接调用 `save_job` 而非 `save_succeeded_or_cancelled`。实际无正确性问题（调用点在 mark_running 阶段或 pipeline 完成后的取消检查，均在 file lock 保护下读取并确认非终态），但与 `_save_succeeded` 使用原子方法的模式不一致。低风险：不影响正确性。

3. **真实下载 adapter 缺失**: 当前 `download_adapters` 为空映射，所有下载请求会进入 unsupported-source failed 终态。这是 F01 scope 内的已知状态（SEC/CN/HK adapter 为 deferred owner），不影响 runtime foundation 的正确性。

4. **`ingestion_runtime.py` 模块体量**: 2639 行，包含请求类型、adapter 协议、job record、job store、executor、runtime、辅助函数。职责边界清晰（数据类型 → 协议 → 持久化 → 执行 → 运行时 → 辅助），但后续扩展可能需要拆分。低风险：当前可维护。
