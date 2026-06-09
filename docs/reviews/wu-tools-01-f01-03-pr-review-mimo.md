# WU-TOOLS-01-F01-03 PR Review — AgentMiMo

**审查时间**: 20260609-193638
**PR**: #131 `phase/wu-tools-01-f01-03` → `main`
**PR title**: WU-TOOLS-01-F01-03 production Fins ingestion migration
**审查范围**: PR 全量 diff (128 files, +40293/-111)
**审查基准**: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`

## 结论

**pass-with-findings**

1 个 medium non-blocking finding（新增 upload_tools.py 的 `_CANCELLED_MESSAGE` 含 "host"），1 个 low observation（`source` 参数缺 enum）。PR 整体质量优秀：迁移不是重写、upload 长事务正确、Host/Engine contract 未改、分层合规、README/Issue #129 一致、residual risks 有 owner。

## 审查项逐项结果

### 1. 迁移不是重写 — PASS

全部 7 个核心模块（sec_downloader, cninfo_downloader, hkexnews_downloader, sec_pipeline, cn_pipeline, docling_upload_service, sec_upload_workflow）的 OLD 业务规则完整保留：

- SEC: SC13 补齐、rejection registry、form window、browse-edgar retry、304 跳过
- CN: 巨潮黑名单/白名单、amended 优先、PDF magic bytes、announcementTime 排序
- HK: 披露易 stock list 解析、titleSearch、amended 判断、PDF 校验
- Upload: create/update/delete/skip/overwrite 矩阵、source fingerprint、document versioning、Docling 转换

参数签名零退化，download/upload 方法参数列表与 OLD 完全一致。唯一变化是关注点分离（workflow → pipeline → downloader → upload_service），不改变业务语义。

### 2. Upload 长事务 — PASS

- `FinsIngestionRuntime.start_upload()` 创建 durable `queued` record，提交到 background executor
- `FinsUploadToolCallable` 返回 `ToolAwaitingOutcome(await_spec, snapshot)`
- `FinsIngestionWaitPollAdapter` 实现 `poll_wait` / `abandon_wait`
- Host wait adapter 绑定：`WaitResumePolicy.POLL` + `WaitExternalJobRefSource.RESUME_TOKEN`
- 工具握手不阻塞：tool callable 在 job 创建后立即返回 awaiting outcome

### 3. Host/Engine public contract — PASS

| 目录 | 变更 |
|------|------|
| `dayu/host/` | 无变更 |
| `dayu/engine/` | 无变更 |
| `dayu/runtime/` | 无变更 |
| `dayu/service/host_assembly.py` | 纯追加：新增 upload provider 识别常量和 `if` 分支，不改公开 API |

### 4. 分层合规 — PASS

- `dayu/fins/` → `dayu/host|engine|service`：仅 `wait_adapter.py`（设计允许的适配层）
- `dayu/runtime/` → `dayu/fins|host|engine`：无违反
- `dayu/service/host_assembly.py` 只从 `dayu.fins.ingestion` 导入公共 API
- 新增代码零 `Any`/`object` 使用

### 5. LLM-facing schema/message/hint — PASS-with-findings

**Finding 1 (MEDIUM)**: 新增 `upload_tools.py` 的 `_CANCELLED_MESSAGE` 含 "host"

| 文件 | 行号 | 字符串 |
|------|------|--------|
| `dayu/fins/tools/upload_tools.py` | 58 | `"Fins upload start was cancelled by the host."` |

此常量通过 `ToolCancelledOutcome.message` 投影给 LLM。`download_tools.py:45` 和 `preprocess_tools.py:44` 有相同的 pre-existing "host" 字符串（在 main 分支已存在），但 `upload_tools.py` 是本 PR 新增的文件，应避免引入已知的内部术语泄漏。

**建议**: 改为 `"Fins upload start was cancelled."` 或 `"Fins upload start was cancelled by the system."`。可一并修复 download/preprocess 的 pre-existing 字符串，但不阻塞本 PR。

**是否 blocking**: 否。`"host"` 在 LLM-facing 语境中可被理解为"宿主系统"而非内部类名，且 download/preprocess 已有相同模式。但 aggregate deepreview 刚修复了 `durable job record` 和 `Fins ingestion runtime` 泄漏，此处应保持一致。

**Finding 2 (LOW)**: `source` 参数缺 enum 约束

`download_tools.py:198-200` 的 `source` 参数描述为 "Financial filing source selector. Use auto unless the user explicitly names a supported source."，但没有 `enum` 列出可选值。对比 `upload_kind`（有 enum）、`action`（有 enum）风格不一致。

**是否 blocking**: 否。Pre-existing 问题，不影响功能。

**其余检查项全部通过**:
- Tool description 无内部术语泄漏
- Error message/hint（F1/F2 修复后）无 `durable job record` / `Fins ingestion runtime`
- 参数 schema 除 `source` 外均自解释
- `reason = "host_cancelled"` 是 contracts 层常量，pre-existing，非本 PR 引入

### 6. README / Issue #129 / Control doc — PASS

- `dayu/fins/README.md`：upload provider、`start_upload` API、wait adapter 常量均已记录
- `dayu/config/README.md`：`financial-upload-tools` 配置行已添加
- `dayu/README.md`：upload 功能已加入 feature 列表
- `docs/host/issues-implementation-control.md`：状态为 `PR review`，与 PR #131 一致
- Issue #129 已评论 `start_upload` 纳入 prepare/activate 范围

### 7. Residual risks 归属 — PASS

| 风险 | Owner | 状态 |
|------|-------|------|
| Crash recovery / prepare/activate two-phase | Issue 129 + Issue 90 | OPEN，有 owner |
| External job physical cancel/revoke | Issue 92 | OPEN，有 owner |
| Broader upload failure-path matrix | Slice 4 deferred | quality debt，controller 判定 non-blocking |
| 6-8 quality debt items (test matrix, helper de-dup, docstring) | 无明确 issue | controller 判定 non-blocking quality debt |

correctness/stability 级别的 residual risks 均有明确 owner。quality debt items 无 individual issue tracking，但 controller 已判定为 non-blocking。

## 验证命令

| 命令 | 结果 |
|------|------|
| `pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q` | 294 passed, 1 skipped, 3 warnings |
| `python -m pyright dayu/ tests/ utils/` | 0 errors |
| `git diff --check` | passed |
| `git diff main..HEAD --name-only -- dayu/host/ dayu/engine/ dayu/runtime/` | 无变更 |

## 未验证项

- Docling 集成测试（需 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 环境变量）
- `dayu/` 下非 `fins/` 的其他模块回归（不在本 PR scope，但 aggregate 测试矩阵 294 passed 已覆盖 `tests/` 全量）
