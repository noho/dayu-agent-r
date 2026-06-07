# Code Review — WU-TOOLS-01-F01 Slice S4

## Scope

- Mode: current changes
- Branch: `host-wu-tools-01-f01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f01-s4-code-review-ds.md`
- Included scope: Slice S4 only — `dayu/fins/tools/provider.py`, `dayu/fins/tools/download_provider.py`, `dayu/fins/tools/preprocess_provider.py`, `dayu/fins/tools/download_tools.py`, `dayu/fins/tools/preprocess_tools.py`, `dayu/fins/tools/__init__.py`, `tests/fins/test_fins_ingestion_tools.py`, `tests/fins/test_fins_storage_provider.py`, `dayu/fins/README.md`, `tests/README.md`
- Excluded scope: `dayu/fins/ingestion_runtime.py`, `dayu/fins/service_runtime.py` (S1-S3, already reviewed), `docs/host/issues-implementation-control.md` (controller bookkeeping, not implementation), plan/review/fix artifacts from prior slices
- Parallel review coverage: 无。单 reviewer 逐文件走读。

## Validation Notes

运行了以下命令并确认通过：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py -q
# 56 passed, 3 warnings

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

## Contract / Architecture Boundary Checks

以下检查项逐一走读确认：

### Read provider 保持 read-only

- `provider.py`: `include_ingestion_tools` 字段已从 provider 实现中完全移除（grep 确认无匹配）。`_validate_fins_declarations` 只校验 9 个 read tool name，不涉及 ingestion。✓
- `test_read_provider_ignores_legacy_ingestion_switch`（test_fins_storage_provider.py:326）：传入 `include_ingestion_tools=True` 时 read provider 仍只返回 9 个 read tools。✓

### 独立 provider id / version / source ref / tool name

| Provider | ID | Version | Source ID | Tool Name |
|---|---|---|---|---|
| Read | `financial-tools` | `fins-read-tools-provider-v1` | `dayu.fins.tools` | (9 read tools) |
| Download | `financial-download-tools` | `fins-download-tools-provider-v1` | `dayu.fins.tools.download_provider` | `start_fins_download` |
| Preprocess | `financial-preprocess-tools` | `fins-preprocess-tools-provider-v1` | `dayu.fins.tools.preprocess_provider` | `start_fins_preprocess` |

无冲突，不与 read tools 或 framework reserved names 冲突。✓

验证测试：`test_tools_discovery_discovers_read_download_and_preprocess_independently`（test_fins_ingestion_tools.py:66）断言三个 provider 的 provider_id / spec_id / tool_names / source_ids 均独立且不交叉。✓

### Provider fail-fast 要求 absolute workspace_root

- `parse_fins_workspace_root_config`（provider.py:98-117）：要求字符串非空且为绝对路径，否则 `ValueError`。两个新 provider 均通过 `spec.config` 调用此函数。✓
- 两个新 provider 均通过 `DefaultFinsRuntime.create(workspace_root=...).get_ingestion_runtime()` 获取 runtime。✓

### ToolAwaitingOutcome 与 EXTERNAL_JOB

- `FinsDownloadToolCallable.__call__`（download_tools.py:40-88）和 `FinsPreprocessToolCallable.__call__`（preprocess_tools.py:41-89）：调用 `runtime.start_*` 后立即通过 `_awaiting_outcome_from_job_start` 返回 `ToolAwaitingOutcome`，不阻塞至 job 完成。✓
- `await_kind` 均为 `ToolAwaitKind.EXTERNAL_JOB`（download_tools.py:222, preprocess_tools.py:213）。✓
- `runtime.start_download` / `start_preprocess` 内部提交后台 executor 后立即返回 `FinsIngestionJobStart`，不等待后台 pipeline 完成。✓

### ToolFailedOutcome for errors

- 参数错误（`ValueError`）→ `_ERROR_INVALID_ARGUMENT` → `ToolFailedOutcome`。✓
- 持久化失败（`OSError`）→ `_ERROR_JOB_START_FAILED` → `ToolFailedOutcome`。✓
- 未预期异常（`Exception`）→ `_ERROR_JOB_START_FAILED` → `ToolFailedOutcome`。✓
- 测试 `test_tool_argument_error_returns_failed_outcome_before_job_creation`（test_fins_ingestion_tools.py:171）：确认参数错误时返回 `ToolFailedOutcome` 且无 job record 残留。✓

### Schema LLM-facing 自解释

- 两个 tool schema 只包含业务参数（ticker, source, form_types, filed_after, filed_before, overwrite_existing, rebuild_processed / source_kind, document_ids）及其业务描述。✓
- 测试 `test_ingestion_tool_schemas_hide_host_internal_fields`（test_fins_ingestion_tools.py:196）：断言不包含 `tool_call_id`, `digest`, `cursor`, `raw job record`, `Host`。✓

### ToolDiscovery / Host / Engine / Service contract 不变

- 两个新 provider 返回标准 `ToolsDiscoveryProviderOutput`，不携带 wait adapter object 或新字段。✓
- 不修改任何 contract 文件（`dayu/contracts/`）。✓

### AGENTS.md 合规

- 无 `Any` / `object` / `hasattr` / `getattr` 使用。✓
- 所有函数/类有完整中文 docstring。✓
- 无魔法字符串/数字，常量均定义为模块级 `Final`。✓
- 无反向依赖，import 方向正确。✓
- 无兼容 facade。✓

### README 同步

- `dayu/fins/README.md`：正确描述 download/preprocess provider 入口、ingestion runtime foundation、独立 provider 启用方式。不写未来计划。✓
- `tests/README.md`：更新了 `tests/fins/` 描述，将 ingestion tools "fail-closed" 替换为当前独立 provider 发现测试的描述。✓

## Findings

### 1-未修复-中-download_tools.py 与 preprocess_tools.py 存在大量重复辅助函数

- **入口/函数**: `_required_text`, `_optional_text_tuple`, `_optional_bool`, `_failed_outcome`, `_awaiting_outcome_from_job_start`
- **文件(行号)**:
  - `dayu/fins/tools/download_tools.py`:206-230 (`_awaiting_outcome_from_job_start`), 233-270 (`_failed_outcome`), 273-290 (`_required_text`), 338-362 (`_optional_text_tuple`), 365-385 (`_optional_bool`)
  - `dayu/fins/tools/preprocess_tools.py`:197-221 (`_awaiting_outcome_from_job_start`), 224-261 (`_failed_outcome`), 264-281 (`_required_text`), 310-334 (`_optional_text_tuple`), 337-357 (`_optional_bool`)
- **输入场景**: 任何涉及参数解析、失败构造或 job start 转 outcome 的工具调用。
- **实际分支**: 两个模块各自定义了语义完全相同的私有函数，各自独立执行。
- **预期行为**: 按 CLAUDE.md "重复逻辑必须抽取"约束，这些共享 helper 应抽取到 `dayu/fins/tools/` 下的一个共享私有模块（如 `_tool_helpers.py`），由 download_tools 和 preprocess_tools 分别 import。
- **实际行为**: 5 个函数在 2 个文件中各有一份完全相同实现的副本。
- **直接证据**:
  - `_required_text` 在 download_tools.py:273-290 和 preprocess_tools.py:264-281 实现完全一致，仅参数/返回值/异常类型相同。
  - `_failed_outcome` 在 download_tools.py:233-270 和 preprocess_tools.py:224-261 结构完全一致（参数签名、函数体、返回类型均相同）。
  - `_awaiting_outcome_from_job_start` 在 download_tools.py:206-230 和 preprocess_tools.py:197-221 实现完全一致。
  - `_optional_text_tuple` 和 `_optional_bool` 同样完全重复。
- **影响**: 参数解析逻辑变更时需同步修改两个文件，容易出现不一致；新增工具（如未来的 upload tool）需要再复制一份，持续扩散。当前行为正确，但违反项目编码硬约束。
- **建议改法和验证点**: 抽取 `_required_text`, `_optional_text_tuple`, `_optional_bool`, `_failed_outcome`, `_awaiting_outcome_from_job_start` 到 `dayu/fins/tools/_tool_helpers.py`，两个 tool 模块改为 import。验证：运行 `pytest tests/fins/test_fins_ingestion_tools.py` + `pyright` 确认无回归。
- **修复风险（低）**: 纯重构，不改变运行时行为。
- **严重程度（中）**: 违反项目硬约束 `重复逻辑必须抽取`，但当前行为正确，不导致 bug。

### 2-未修复-低-后台 daemon 线程可能在测试 fixture 清理后仍运行

- **入口/函数**: `test_download_tool_returns_external_job_awaiting_outcome` / `test_preprocess_tool_returns_external_job_awaiting_outcome`
- **文件(行号)**: `tests/fins/test_fins_ingestion_tools.py`:115-141, 143-168
- **输入场景**: 测试正常参数触发 `runtime.start_download` / `start_preprocess`，runtime 内部通过 `FinsIngestionThreadExecutor` 提交 daemon 线程后台执行 pipeline。
- **实际分支**: 测试仅断言 outcome 类型为 `ToolAwaitingOutcome`，不等待后台线程完成。后台线程在 daemon 模式下运行，生命周期不受测试函数控制。
- **预期行为**: 测试应确保后台线程在 fixture 清理前完成，或在测试中不依赖 daemon 线程的副作用，避免资源竞争。
- **实际行为**: 测试函数返回后，daemon 线程可能仍在访问 tmp_path 下的 workspace 文件。虽然 pytest 的 tmp_path 在 session 结束时才清理，且每个测试使用独立 workspace，跨测试文件系统冲突概率低，但 daemon 线程的累积（多个测试各启一个线程）和潜在的文件锁竞争构成可观察风险。
- **直接证据**: `FinsIngestionRuntime.start_download`（ingestion_runtime.py:969）调用 `self.executor.submit(...)` 提交 daemon 线程；测试在 `asyncio.run(...)` 返回后立即断言，不执行任何 join 或 wait 操作。
- **影响**: 当前 56 tests 全部通过，未观测到实际 flaky 失败。但在高负载 CI 或重复运行场景下可能出现线程间文件竞态或 resource warning。此问题根因在 S3 的 runtime executor 设计（daemon thread + 无显式 shutdown），S4 测试首次触发该路径。
- **建议改法和验证点**: 方案一（推荐）：在 `FinsIngestionRuntime` 增加 `shutdown()` 方法，测试 teardown 中调用。方案二：为 `FinsIngestionThreadExecutor` 增加非 daemon 模式 + join 机制。当前 S4 scope 不要求修改 runtime，但应在 S5/S6 中处理。验证：重复运行测试 100 次确认无 resource warning 或竞态。
- **修复风险（低）**: 需要修改 S3 runtime executor，但属于基础设施加固。
- **严重程度（低）**: 未观测到实际失败，当前 tests 全部通过，但构成潜在 flaky 风险。

## Open Questions

- 无。

## Residual Risk

- Host wait adapter 尚未实现（S5 scope）。Download/preprocess 工具正确返回 `ToolAwaitingOutcome`，但 Host 侧尚无对应的 `WaitPollAdapter` 来解析 job 终态并推进 resume。此为 S5 的明确 scope，非 S4 遗漏。
- 真实 SEC/CN/HK 网络下载 adapter 尚未实现。当前 runtime 对无 adapter 的来源返回 unsupported-source failed 终态，工具层行为正确。
- `FinsIngestionThreadExecutor` 无显式 shutdown/cleanup 机制（S3 设计决策），daemon 线程在进程退出时被强制终止。S4 测试首次触发该路径但未观测到实际失败。
- S4 未覆盖的场景：当 `executor.submit` 在 `start_download`/`start_preprocess` 中抛出异常时（极罕见，如线程创建失败），job record 已在 `queued` 状态持久化但后台 pipeline 未启动，形成孤儿 job record。工具层正确返回 `ToolFailedOutcome`，但孤儿 record 的清理机制属于 S3 runtime 范畴，不在 S4 scope。

## Verdict

**pass-with-findings**

两项 finding 均为中/低严重度，不构成 correctness blocking issue。所有 S4 plan expected assertions 均已通过测试验证，核心架构约束（独立 provider、ToolAwaitingOutcome、EXTERNAL_JOB、LLM-facing schema、contract 不变）全部满足。
