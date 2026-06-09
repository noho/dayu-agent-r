# WU-TOOLS-01-F01-03 Aggregate Deepreview — AgentMiMo

**审查时间**: 20260609-191500
**审查范围**: WU-TOOLS-01-F01-03 全部分支已提交内容 (commit `6f519cea`..`0566fb29`，110 files, +37747/-99)
**审查基准**: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`, 49 个 review artifacts

## 结论

**pass-with-findings**

2 个 medium severity non-blocking findings（LLM-facing 内部术语泄漏），1 个 low severity observation（pipeline 模块 import concrete storage 类型）。WU 目标已完成，6 个 slice 全部通过 controller adjudication，分层/边界/ticker/storage 测试合规，residual risks 均有 owner。

## 审查项逐项结果

### 1. WU 目标完成度 — PASS

WU-TOOLS-01-F01-03 目标：迁移 OLD SEC/CN/HK downloader、SEC/CN download/upload workflow 到 NEW shared Fins runtime/tool surface，不重写业务逻辑。

| Slice | 内容 | 状态 |
|-------|------|------|
| 1 | Ingestion runtime foundation (download/preprocess/upload job lifecycle) | accepted |
| 2 | SEC downloader + SEC download runtime migration | accepted |
| 3 | CN/HK downloader + CN/HK download runtime migration | accepted |
| 4 | Upload service + production upload runtime migration | accepted |
| 5 | Upload awaiting tool + provider + wait adapter + service assembly | accepted |
| 6 | Documentation + full validation + Issue 129 tracking | accepted |

OLD upload 语义通过 `DoclingUploadService` 保留，`FinsIngestionRuntime` 只管 job lifecycle，upload 作为长事务通过 durable job + `ToolAwaitingOutcome` + Host wait adapter 实现。

### 2. Upload 长事务机制 — PASS

- `FinsIngestionRuntime.start_upload()` 创建 durable `queued` record，提交到 background executor
- `ProductionFinsUploadRunner.run_upload()` 执行实际上传，返回 `FinsUploadResultSummary`
- `FinsUploadToolCallable` 返回 `ToolAwaitingOutcome(await_spec, snapshot)`
- `FinsIngestionWaitPollAdapter` 实现 `poll_wait` / `abandon_wait`，通过 `FinsIngestionRuntime` 读取 job 状态
- Host wait adapter 绑定：`WaitResumePolicy.POLL` + `WaitExternalJobRefSource.RESUME_TOKEN`

### 3. 分层/边界合规 — PASS（with observation）

| 检查项 | 结果 |
|--------|------|
| `dayu/fins/` → `dayu/host\|engine\|service` | PASS — 仅 `wait_adapter.py`（设计允许的适配层） |
| `dayu/runtime/` → `dayu/fins\|host\|engine` | PASS — 无违反 |
| `dayu/service/host_assembly.py` 依赖 | PASS — 只从 `dayu.fins.ingestion` 导入公共 API |
| 新增代码 `Any`/`object` 使用 | PASS — 零使用 |

**Observation**: `sec_pipeline.py:130-142` 和 `cn_pipeline.py:70-82` 在 protocol 类型之外还 import 了 concrete `Fs*` 类型和 `_fs_repository_factory`，用于 `build_*_adapter()` factory 函数。这是 factory 模式的合理用法，但若严格要求 protocol-only 边界，可将 factory 函数提取到独立 assembly 模块。**不阻塞**。

### 4. Ticker/Storage 边界 — PASS

- 所有 ticker 归一化通过 `dayu.fins.ticker_normalization`
- 所有 source document/blob/company meta 操作通过 `dayu.fins.storage` repository 协议
- 无直接文件系统写入（用户上传输入的 `read_bytes()` 除外）

### 5. LLM-facing schema 合规 — PASS-with-findings

| 检查项 | 结果 |
|--------|------|
| 参数 schema 不暴露内部术语 | PASS — `ticker`, `upload_kind`, `action`, `files` 等均为业务语义 |
| 不暴露 Host/EventLog/wait_id/tool_call_id/digest/cursor | PASS |
| 不暴露 Python 类型名/内部类名 | PASS |
| Read tools 合规 | PASS — `search_document` 显式剥离 `diagnostics` |

**Finding 1 (MEDIUM)**: `durable job record` 出现在 error message 中

| 文件 | 行号 | 泄漏字符串 |
|------|------|-----------|
| `dayu/fins/tools/upload_tools.py` | 123 | `message="上传任务未能创建 durable job record。"` |
| `dayu/fins/tools/download_tools.py` | 103 | `message="下载任务未能创建 durable job record。"` |
| `dayu/fins/tools/preprocess_tools.py` | 102 | `message="预处理任务未能创建 durable job record。"` |

`ToolFailedOutcome.result.message` 会直接返回给 LLM。`durable job record` 是内部存储概念，LLM 无法理解和处理。

**建议**: 改为 LLM 可理解的业务语言，如 `"上传任务启动失败，未能保存任务记录。"` / `"下载任务启动失败，未能保存任务记录。"`。

**Finding 2 (MEDIUM)**: `Fins ingestion runtime` 出现在 error hint 中

| 文件 | 行号 | 泄漏字符串 |
|------|------|-----------|
| `dayu/fins/tools/upload_tools.py` | 132 | `hint="请检查输入参数和 Fins ingestion runtime 配置。"` |
| `dayu/fins/tools/download_tools.py` | 112 | `hint="请检查输入参数和 Fins ingestion runtime 配置。"` |
| `dayu/fins/tools/preprocess_tools.py` | 111 | `hint="请检查输入参数和 Fins ingestion runtime 配置。"` |

`Fins ingestion runtime` 是内部类名 (`FinsIngestionRuntime`)。hint 要求 LLM "检查 Fins ingestion runtime 配置"，这是 LLM 无法执行的内部概念。

**建议**: 改为可操作的业务指引，如 `"请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。"`。

### 6. 测试与验证 — PASS

| 命令 | 结果 |
|------|------|
| `pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q` | 294 passed, 1 skipped, 3 warnings |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

294 个测试覆盖了：downloader 语义、download/upload workflow、pipeline facade、ingestion runtime lifecycle、tool/provider/wait adapter binding、service assembly fail-fast、schema leak 检测。

### 7. Residual Risks 归属 — PASS（with observation）

| 风险 | Owner | 状态 |
|------|-------|------|
| Crash recovery / non-terminal job on process death | Issue 129 + Issue 90 | OPEN，有 owner |
| Upload partial artifacts on crash | Issue 129 + Issue 90 | OPEN，有 owner |
| External job physical cancel/revoke | Issue 92 | OPEN，有 owner |
| Prepare/activate two-phase awaiting | Issue 129 | OPEN，有 owner |

**Observation**: 以下 deferred findings 无明确 issue/slice owner，属于 quality debt：

| ID | 描述 | 来源 |
|----|------|------|
| CTRL-S2-D1 | Broader SEC stream failure/overwrite test matrix | Slice 2 |
| CTRL-S2-D2 | SEC downloader helper de-duplication | Slice 2 |
| CTRL-S2-D3 | Finer-grained SEC cancellation in wait/retry loops | Slice 2 |
| CTRL-S3-D1 | Broader CN/HK workflow/runtime test matrix | Slice 3 |
| CTRL-S3-D2 | CN/HK downloader helper de-duplication | Slice 3 |
| CTRL-S4-D1 | Broader upload failure-path test matrix | Slice 4 |
| CTRL-S4-D2 | Upload progress helper literal-key consolidation | Slice 4 |
| CTRL-S3-D3 | HkexnewsDiscoveryClient class docstring | Slice 3 |

这些是测试加固和代码清理项，不是正确性缺口。现有确定性测试已覆盖核心路径。**建议**: 将 CTRL-S2-D1/D3、CTRL-S3-D1、CTRL-S4-D1 归入后续 hardening issue，其余低优先级 cleanup 可不追踪。

**HK upload 证据**: `service_runtime.py:150-151` 将 HK market 路由到 `cn_pipeline.upload_filing()`，与 OLD 代码模式一致。PLAN-R6 已通过实现验证。

## Findings

### F1-未修复-MEDIUM-`durable job record` 泄漏到 LLM error message

- **文件**: `dayu/fins/tools/upload_tools.py:123`, `download_tools.py:103`, `preprocess_tools.py:102`
- **输入场景**: `OSError` during job start
- **实际行为**: `ToolFailedOutcome.result.message` 包含 `durable job record` 内部术语
- **预期行为**: 使用 LLM 可理解的业务语言
- **影响**: LLM 无法理解内部存储概念，可能产生困惑或幻觉
- **建议**: 改为 `"X任务启动失败，未能保存任务记录。"` (X = 上传/下载/预处理)
- **是否 blocking**: 否（功能正确，仅影响 LLM 错误消息质量）

### F2-未修复-MEDIUM-`Fins ingestion runtime` 泄漏到 LLM error hint

- **文件**: `dayu/fins/tools/upload_tools.py:132`, `download_tools.py:112`, `preprocess_tools.py:111`
- **输入场景**: `Exception` during job start
- **实际行为**: `ToolFailedOutcome.result.hint` 包含 `Fins ingestion runtime` 内部类名
- **预期行为**: 使用 LLM 可操作的业务指引
- **影响**: hint 要求 LLM 检查其无法访问的内部配置
- **建议**: 改为 `"请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。"`
- **是否 blocking**: 否（功能正确，仅影响 LLM 错误指引质量）

## 验证命令

| 命令 | 结果 |
|------|------|
| `pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q` | 294 passed, 1 skipped, 3 warnings |
| `python -m pyright dayu/ tests/ utils/` | 0 errors |
| `git diff --check` | passed |
| `git log --oneline 6f519cea..0566fb29` | 11 commits (6 slices + 5 gate/docs) |

## 未验证项

- `test_combined_tools_acceptance.py` 已在 aggregate 测试矩阵中运行 (294 passed 包含其)
- Docling 集成测试 (`DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`) 未运行（需真实 Docling 环境）
- 未检查 `dayu/` 下非 `fins/` 的其他模块是否有本次 WU 引入的回归
