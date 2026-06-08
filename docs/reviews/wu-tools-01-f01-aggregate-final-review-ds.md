# WU-TOOLS-01-F01 Aggregate Final Review

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools`
- Gate: aggregate final review / closeout
- Review type: final code review, correctness-first
- Inputs: S1-S6 accepted commits (f598f8a2, 2e12dfb4, 4b91d3af, 2727b900, 5336d7b2, 157ec0b5); bookkeeping 4993eac0; S6 re-review controller adjudication `docs/reviews/wu-tools-01-f01-s6-rereview-controller-adjudication.md`
- Artifact path: `docs/reviews/wu-tools-01-f01-aggregate-final-review-ds.md`

## Verdict

**pass**

F01 已完成其声明的全部目标：共享 Fins runtime foundation 已建立、三组独立 provider 已就位、下载/预处理 awaiting flow 已通过 Host wait-resume contract 闭环、层级依赖合规、默认 tool_discovery.json 已对齐目标形态、`include_ingestion_tools` 已从代码库完全移除。发现 1 个低严重度 findings，不阻塞 pass。

## Review Axes

### 1. F01 原始目标闭环

**判断：闭环。**

- `DefaultFinsRuntime` (dayu/fins/service_runtime.py:36) 是 read/download/preprocess 的共享 assembly root，统一装配仓储、processor registry 与 ingestion runtime foundation。
- `FinsIngestionRuntime` (dayu/fins/ingestion_runtime.py:877) 提供 typed download/preprocess 请求/结果/摘要/job record/job store/start/read/cancel 全部基础能力。
- 下载 runtime 通过 `FinsSourceDownloadAdapter` 协议 (ingestion_runtime.py:271) 支持 source/market adapter 选择，无适配器时 fail closed。
- 预处理 runtime 通过 `FinsIngestionRuntime._preprocess_one_document` (ingestion_runtime.py:1647) 走 source repository → processor registry → processed repository 闭环。
- Read provider (provider.py:48)、download provider (download_provider.py:21)、preprocess provider (preprocess_provider.py:21) 三组独立，各通过 `DefaultFinsRuntime.create(workspace_root=...)` 获取 runtime。
- CLI 未恢复；`dayu/cli` 目录仍不存在；CLI 边界保持为未来 thin adapter over shared runtime。

**证据**：`dayu/fins/service_runtime.py` 44 行 workspace_root 参数与 179-188 行 get_ingestion_runtime() 懒加载；`dayu/fins/ingestion_runtime.py` 877-890 行 create() 与 934-977 行 start_download/start_preprocess。

### 2. 层级与依赖合规

**判断：合规。**

| 检查项 | 结果 | 证据 |
|---|---|---|
| `dayu.runtime` 不 import `dayu.fins` | PASS | Grep `dayu/runtime/**/*.py` 无匹配 |
| `dayu.fins` 通用模块不 import Host/Service/Engine/UI | PASS | 仅 `dayu/fins/ingestion/wait_adapter.py` 导入 `dayu.host` |
| `wait_adapter.py` 只导入 `dayu.host`，不导入 `dayu.service/engine/ui` | PASS | 测试常量 (test_fins_storage_provider.py:75) 显式允许 host 但禁止 engine/service/ui |
| `dayu.service` 只导入 `dayu.fins.ingestion` | PASS | Service import boundary test (test_import_boundary.py:13-16) 显式禁止通用 fins 但允许 fins.ingestion |
| `dayu.engine` 不 import `dayu.fins` | PASS | 测试 `test_runtime_and_engine_do_not_import_fins` (test_fins_storage_provider.py:378) |
| Host/Engine public contracts 未变更 | PASS | `dayu/contracts/tool_await.py` / `tool_outcome.py` / `dayu/host/api.py` 未修改 |
| Host durable schema 未变更 | PASS | Host wait record 仍由 Host 拥有 |
| `HostToolingOptions.wait_adapter_registry` 只通过 Service assembly 注入 | PASS | `dayu/service/host_assembly.py:1071-1073` 通过 `_fins_wait_adapter_registry_from_provider_configs` 构造 |

### 3. ToolDiscovery Target Shape 闭环

**判断：闭环。**

- 默认 `tool_discovery.json` 包含三组 Fins provider：
  - `financial-read-tools` → `dayu.fins.tools.provider:discover_tools` (enabled=false)
  - `financial-download-tools` → `dayu.fins.tools.download_provider:discover_tools` (enabled=false)
  - `financial-preprocess-tools` → `dayu.fins.tools.preprocess_provider:discover_tools` (enabled=false)
- `include_ingestion_tools` 已从代码库完全移除：grep `dayu/` 无匹配。
- Read provider 不再解析 `include_ingestion_tools`；只有 `include_read_tools` 布尔开关。
- Workspace overlay 可独立启用任一 provider；`dayu/config/README.md:182-183` 明确说明 download/preprocess 通过独立 provider 启用。

**证据**：`dayu/config/tool_discovery.json:1-64` 三组 disabled 条目；`dayu/fins/tools/provider.py:34` 只有 `include_read_tools` 字段。

### 4. Awaiting Flow 完整性

**判断：完整。**

Download/preprocess tool callable 路径：
1. 参数验证 → `FinsDownloadToolCallable.__call__` (download_tools.py:47) 或 `FinsPreprocessToolCallable.__call__` (preprocess_tools.py:46)
2. 调用 `runtime.start_*` → 创建 durable `queued` job record
3. 返回 `ToolAwaitingOutcome(await_spec=ToolAwaitSpec(await_kind=EXTERNAL_JOB, resume_token=job_id))`

Poll adapter 状态映射 (wait_adapter.py:101-125)：

| Fins job status | Host poll result |
|---|---|
| queued/running/cancelling | `WaitPollNotReady` |
| succeeded | `WaitPollReady(ResolveWaitCompletedOutcome)` |
| failed | `WaitPollReady(ResolveWaitFailedOutcome)` |
| cancelled | `WaitPollReady(ResolveWaitCancelledOutcome)` |
| missing/corrupt (FileNotFoundError/ValueError) | `WaitPollLost(ResolveWaitLostOutcome)` |

`abandon_wait` (wait_adapter.py:127-142) 只调用 `runtime.request_cancel(job_id)`，不删除 source docs 或 Host wait records。

Service assembly 检测 Fins awaiting providers 通过 provider_id/import_path/source_id (host_assembly.py:1116-1138)，不依赖 diagnostic strings。Workspace root 不一致时在 `open_host` 前 fail fast (host_assembly.py:1164-1182)。

**证据**：`dayu/fins/tools/download_tools.py:95` 返回 awaiting outcome；`dayu/fins/ingestion/wait_adapter.py:101-125` poll 映射；`dayu/service/host_assembly.py:1084-1113` registry 构造。

### 5. Storage/Ticker Boundary 合规

**判断：合规。**

- 财报文档存取通过 `dayu.fins.storage` 仓储协议：
  - 下载走 `SourceDocumentRepositoryProtocol` + `DocumentBlobRepositoryProtocol` + `FilingMaintenanceRepositoryProtocol` (ingestion_runtime.py:1383-1550)
  - 预处理走 `SourceDocumentRepositoryProtocol` + `ProcessedDocumentRepositoryProtocol` (ingestion_runtime.py:1647-1722)
- Ticker normalization 通过 `dayu.fins.ticker_normalization`：
  - `start_download` (ingestion_runtime.py:951) 调用 `ticker_normalization.normalize_ticker`
  - `start_preprocess` (ingestion_runtime.py:996) 调用 `ticker_normalization.normalize_ticker`
- Job store 只存治理状态 (ingestion_runtime.py:47-49)，路径 `<workspace_root>/.dayu/fins_ingestion/jobs`，不保存财报正文或 processed payload。
- `FsFinsIngestionJobStore` 使用 fcntl 文件锁 (ingestion_runtime.py:1883-1951) + atomic replace (tmp → os.replace → fsync directory) 保证跨实例安全。

**证据**：`dayu/fins/ingestion_runtime.py:880-887` runtime 字段列表；`dayu/fins/ingestion_runtime.py:59` 路径常量。

### 6. Tests/README 支撑 Closeout

**判断：足够。**

- 142 tests pass，pyright 0 errors 0 warnings。
- Import boundary tests 覆盖所有关键约束（见 §2）。
- `dayu/fins/README.md` 已更新：描述三组 provider 入口、ingestion 状态、job store 路径、wait adapter 语义、扩展约束。
- `dayu/config/README.md` 已更新：tool_discovery.json 说明三组 Fins provider、workspace overlay 启用规则、read 可配置 limits、download/preprocess 通过独立 provider 启用。
- `tests/README.md` 已更新：tests/fins/ 节覆盖 download/preprocess provider discovery、awaiting callable、poll adapter、ingestion runtime 测试。
- 根 `README.md` 按 plan 未更新（CLI absent）。
- Residual risks 均有 owner (issues-implementation-control.md:197-226)。

### 7. WU-TOOLS-01-S4-R1 关闭裁决

**判断：同意关闭。**

S6 controller adjudication 已裁决 closed。复查确认：

- S1: `DefaultFinsRuntime` / `FinsIngestionRuntime` / durable job store → PASS
- S2: Preprocess source → processed pipeline → PASS
- S3: Download adapter protocol / fake adapter / storage write / unsupported-source failure → PASS
- S4: 三组独立 provider / `ToolAwaitingOutcome` / `include_ingestion_tools` 移除 → PASS
- S5: Wait adapter poll mapping / Service assembly registry wiring → PASS
- S6: Config alignment / docs sync / regression closeout → PASS

无直接阻塞证据要求重新打开此 residual。

## Findings

### F01-AGG-001 (Low) — `_mark_job_running_or_cancelled` 与 `request_cancel` 之间存在 TOCTOU race window

- **File**: `dayu/fins/ingestion_runtime.py:1196-1224` (`_mark_job_running_or_cancelled`) vs `:776-803` (`request_cancel`)
- **Evidence**: `_mark_job_running_or_cancelled` 在 `read_job`（持锁读取）与 `save_job`（持锁写入）之间释放 fcntl 锁。在此期间，另一线程/进程的 `request_cancel` 可以获取锁、将状态从 QUEUED 改为 CANCELLING。之后 `save_job` 会用 RUNNING 覆盖 CANCELLING，导致取消请求静默丢失。
- **Severity**: Low。Race window 极窄（两次 fcntl 操作之间的纯 Python 代码执行时间）；实际场景中取消请求通常在 job 进入 WAITING 后较长时间才到达，此时 job 早已是 RUNNING；最坏后果是取消被忽略、job 跑完，结果仍正确（只是不是 cancelled）。
- **Recommendation**: 将 `_mark_job_running_or_cancelled` 的 read-check-write 合并为一个持锁原子操作（例如在 job store 协议中增加 `claim_running(job_id) -> FinsIngestionJobRecord` 方法，在单次 fcntl 持锁内完成读取、状态检查、写入 RUNNING 或 CANCELLED）。此优化可随下一次 Fins job store 演进（如 F04/F05 引入真实下载适配器时）一并实施，不阻塞当前 closeout。

### No blocking findings

无 correctness、architecture、contract 或 security 层面的阻塞性 findings。

## Validation

```text
source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py \
  tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_public_resolve_wait_resume.py -q

→ 142 passed in 1.96s

source .venv/bin/activate && python -m pyright

→ 0 errors, 0 warnings, 0 informations
```

## Residual Risk Reconciliation

| ID | 状态 | Owner |
|---|---|---|
| WU-TOOLS-01-S4-R1 | closed | F01 S1-S6 完成；Controller 已裁决 closed；aggregate review 同意 |
| WU-TOOLS-01-S1-R1 | deferred-with-owner | WU-TOOLS-01-F04/F05 (SEC/Fins CI) and WU-TOOLS-01-F06/F07 (CN/HK Docling CI) |
| WU-TOOLS-01-S1-R2 | deferred-with-owner | WU-TOOLS-01-F08 (processor registry naming cleanup) |
| WU-TOOLS-01-S5-R2 | deferred-with-owner | WU-TOOLS-01-F02 (Web CI diagnostics) then WU-TOOLS-01-F03 (Web CI smoke) |
| F01-AGG-001 | deferred-with-owner | Low severity TOCTOU in job state transition; recommend fix alongside F04/F05 real download adapter introduction |

## Gate Decision

**允许进入 ready-to-open-draft-PR gate。**

所有 S1-S6 slices 已 accepted；aggregate final review 结论 pass；无阻塞性 findings；tests 142 passed / pyright 0 errors；import boundary 合规；docs 已同步；residual risks 均有 deferred owner。
