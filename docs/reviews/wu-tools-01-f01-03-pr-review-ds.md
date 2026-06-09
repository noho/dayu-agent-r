# WU-TOOLS-01-F01-03 PR Review — AgentDS

## Scope

- **PR**: [#131](https://github.com/noho/dayu-agent-r/pull/131) — WU-TOOLS-01-F01-03 production Fins ingestion migration
- **Branch**: `phase/wu-tools-01-f01-03` → `main`
- **Author**: noho (Leo Liu)
- **Commits**: 16（`6f519cea` plan accepted → `3102b375` draft PR recorded）
- **Changes**: +40,293 / −111，111 files
- **Output file**: `docs/reviews/wu-tools-01-f01-03-pr-review-ds.md`

## Verdict

**pass** — 0 blocking findings；PR 可 merge。

所有 6 slices 的 controller accepted fixes 均已合入，aggregate deepreview accepted fixes（MiMo F1/F2 LLM-facing 术语修复）已合入，cross-slice 边界一致，full validation 通过。

---

## 审查要点

### 1. 迁移非重写 —— OLD 业务逻辑保留

**通过。** 所有 OLD SEC/CN/HK downloader 与 SEC/CN download/upload workflow 的迁移均有 OLD direct import tracing evidence 记录在 slice implementation artifacts 中。业务语义（auto/create/update/delete actions, skip/overwrite, source fingerprint/version, filing/material IDs, Docling injection, cooperative cancellation）完整保留。

`dayu/host/` 和 `dayu/engine/` 在 PR diff 中零改动——Host/Engine public contracts 未被修改。

### 2. Upload 长事务边界

**通过。** `start_upload` 立即返回 `FinsIngestionJobStart`，不等待 Docling 转换或存储写入。工具返回 `ToolAwaitingOutcome(EXTERNAL_JOB, resume_token=job_id)`，Host wait adapter 通过 `FinsIngestionWaitPollAdapter` 轮询 Fins job 终态。整个链路：runtime → runner → pipeline → workflow 使用 cooperative cancellation。

### 3. 分层合规

**通过。**
- Fins tools/pipelines/downloaders 零 `dayu.host`/`dayu.engine` import
- `dayu/runtime/` 零反向依赖
- Service assembly (`host_assembly.py`) 仅引用 provider id/import-path/source-id 字符串，不导入具体 Fins provider 模块
- 所有文档级读写通过 `dayu.fins.storage` 协议

### 4. LLM-facing 自查

**通过。** 三个工具 schema（download/preprocess/upload）无 Host/EventLog/wait_id/tool_call_id/digest/cursor/raw job path 泄漏。aggregate deepreview fix（MiMo F1/F2）已将 OSError/unexpected exception 的 message/hint 中的 `durable job record` 和 `Fins ingestion runtime` 替换为中文化业务可读文本。"cancelled by the host" 短语存在于三个工具中，属于 `ToolCancelledOutcome` 标准契约，与 download/preprocess 预存一致。

### 5. README/Issue/Control Doc 一致性

**通过。**
- `dayu/fins/README.md`: 更新为当前实现事实（production upload runner + awaiting tool provider + wait adapter binding）
- `dayu/config/README.md`: 新增 `financial-upload-tools` provider 说明
- `tests/README.md`: 更新为包含 upload service/pipeline/runtime/tool/assembly 测试覆盖
- `dayu/README.md`: top-level 概述包含 upload awaiting
- Issue #129: 已评论记录 `start_upload` 纳入 prepare/activate scope
- `docs/host/issues-implementation-control.md`: WU 状态从 `discussion-ready` → `PR review`

### 6. Residual Risk Ownership

**通过。** 所有 residual risks 均有 owner：
- Crash recovery / prepare-activate: Issue #129
- Physical cancel beyond cooperative: Issue #92 / WU-WAIT-03
- Upload failure-path matrix: Slice 4 controller deferred CTRL-S4-D1
- CN/HK process migration: plan non-goal（out of scope）

---

## PR 完整性检查

| 检查项 | 结果 |
|---|---|
| 所有 committed 文件包含在 PR 中 | 通过（111 files, 16 commits） |
| 无 dirty untracked 非 review 文件 | 通过（仅 `docs/reviews/` 下 review artifacts 为 untracked） |
| 无危险文件（.env, credentials, .pem 等） | 通过 |
| 所有 tool_discovery providers 默认 disabled | 通过（全部 6 个 `enabled: false`） |
| Aggregate fix（MiMo F1/F2）已合入 PR | 通过（"未能保存任务记录" 在三工具中） |

## 验证摘要

| 检查项 | 结果 |
|---|---|
| 全量 pytest | **294 passed, 1 skipped, 3 warnings**（仅 edgartools deprecation） |
| 全量 pyright | **0 errors, 0 warnings, 0 informations** |
| Host/Engine contract diff | **零改动** |
| Stack check（不分层 import） | **通过** |

## Open Questions

无。

## Residual Risk

PR merge 后需关注：
1. **crash recovery / prepare-activate**: Issue #129 跟踪，后续 WU 按计划处理
2. **upload failure-path test matrix**: Slice 4 deferred，不影响当前 production 正确性但值得后续 hardening
3. **真实 Docling integration CI**: 需 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` opt-in
