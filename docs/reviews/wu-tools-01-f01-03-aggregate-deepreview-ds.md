# WU-TOOLS-01-F01-03 Aggregate DeepReview — AgentDS

## Scope

- **Mode**: aggregate (end-to-end WU review, all slices + closeout)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Commit range**: `6f519cea`（plan accepted） → `0566fb29`（slice6 closeout），共 11 commits
- **Output file**: `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-ds.md`
- **Reviewed scope**: 全部 6 个 slices + closeout 的 production、test、doc、config 变更（111 files, +37,747 / -99）
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Plan source**: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`

## Verdict

**pass** — 0 blocking findings；0 new findings at aggregate level；WU 目标完成，所有 slices 的 controller accepted fixes 均已合入，Issue 129 已更新，residual risks 均有 owner。

---

## WU 目标完成评估

### 核验结果

| 计划目标 | 状态 | 证据 |
|---|---|---|
| SEC/CN/HK production download 可通过 `start_download` + awaiting tool 启动 | 完成 | Slice 2 (SEC) + Slice 3 (CN/HK)；`DefaultFinsRuntime` 注册 6 个 adapter key |
| SEC/CN upload 可通过 `start_upload` + awaiting tool 启动 | 完成 | Slice 4 (upload runner) + Slice 5 (awaiting tool/provider) |
| Future CLI/CI/tool callers 使用相同 `DefaultFinsRuntime` 路径 | 完成 | 统一 `FinsIngestionRuntime` lifecycle；单一 `DefaultFinsRuntime` assembly |
| 所有 source/processed 写入通过 `dayu.fins.storage` | 完成 | 全部下载/上传工作流通过 `SourceDocumentRepositoryProtocol` / `DocumentBlobRepositoryProtocol` |
| Ticker/market 决策通过 `dayu.fins.ticker_normalization` | 完成 | `normalize_ticker` 统一入口；CN/HK/US 路由通过 market |
| Upload 作为长事务：durable Fins job → `ToolAwaitingOutcome` → Host wait-resume | 完成 | `start_upload` 立即返回；background runner 执行上传；wait adapter 轮询 Fins job 终态 |
| 迁移非重写：OLD SEC/CN/HK downloader 与 download/upload workflow 业务逻辑保留 | 完成 | 所有 OLD direct import tracing evidence 记录在实现 artifact 中 |

### 未完成项（明确 Non-Goal）

| Non-Goal | 状态 |
|---|---|
| Host prepare/activate two-phase awaiting | 未实现 — 属于 WU-WAIT-03 / Issue 129 |
| CN/HK process migration | 未迁移 — OLD process 模块不在 scope 内 |
| Physical cancel/revoke beyond cooperative `request_cancel` | Issue 92 / WU-WAIT-03 跟踪 |
| Crash-time restart of running Fins daemon jobs | Issue 129 跟踪 |
| OLD upload provider / wait adapter / CLI assembly | 未迁移 — 新建 NEW provider/adapter |

---

## Slice-by-Slice 状态汇总

| Slice | 内容 | Initial Review | Controller | Fix | Re-review | 最终状态 |
|---|---|---|---|---|---|---|
| 1 | Job record/store/upload foundation | fix-required (DS-S1, CTRL-RR1) | fix-required | 1 follow-up fix | pass | accepted |
| 2 | SEC downloader migration | fix-accepted (F1-F2 high) | fix-required | 7 fixes (CTRL-S2-01~07) | pass (all fixed) | accepted |
| 3 | CN/HK downloader migration | pass (0 high, F1 medium) | fix-required | 6 fixes (CTRL-S3-01~06) | pass (all fixed) | accepted |
| 4 | Upload service/production runner | fix-accepted (F1-F2 high) | fix-required | 4 fixes (CTRL-S4-01~04) | pass (all fixed) | accepted |
| 5 | Upload tool/provider/wait adapter | pass-with-findings (F1 medium) | fix-not-required (F1 rejected) | 0 fixes | N/A | accepted |
| 6 | Documentation, validation, Issue 129 closeout | N/A (controller closeout) | accepted | N/A | N/A | completed |

---

## Cross-Slice 边界一致性验证

### 1. 严格分层：UI → Service → Host → Engine

| 检查项 | 结果 |
|---|---|
| Fins tools/pipelines/downloaders → `dayu.host`/`dayu.engine` import | CLEAN — 零匹配 |
| `dayu/runtime/` → `dayu.fins`/`dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui` import | CLEAN — 零匹配 |
| Service assembly (`dayu/service/host_assembly.py`) → 具体 Fins provider 模块 import | CLEAN — 仅引用 provider id/import-path/source-id 字符串 |
| Storage access through `dayu.fins.storage` protocols | 所有文档级读写通过协议；downloaders 中 temp-file buffering 与 SEC throttle state 为基础设施级 FS 操作（预存，非本 WU 引入） |

### 2. Upload 长事务边界

| 检查项 | 结果 |
|---|---|
| `start_upload` 立即返回（不等待 Docling/conversion） | 通过 — `ingestion_runtime.py:1569-1576`：提交 background job 后立即 `return start` |
| 工具返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` | 通过 — `upload_tools.py:134`：`_awaiting_outcome_from_job_start(start)` |
| Wait adapter 轮询 Fins job 记录（不改 Host schema） | 通过 — `wait_adapter.py:103-143`：`poll_wait` 通过 `external_job_ref.external_job_id` 读取 |
| Cooperative cancellation 端到端 | 通过 — runtime → runner → pipeline → workflow 全链路 |

### 3. LLM-facing Schema 自查

| 检查项 | 结果 |
|---|---|
| 无 Host/EventLog/wait_id/tool_call_id/digest/cursor 在 tool schema 中 | 通过 — upload/download/preprocess 三个工具 schema grep 零匹配 |
| 参数自解释（ticker, upload_kind, action, files 等业务语言） | 通过 — 15 个 upload 参数均有业务可读描述 |
| 内部治理概念不暴露（`finsjob_`, `.dayu`, `source_kind` 等） | 通过 — LLM-facing schema 不暴露这些词 |
| 取消消息中 "host" 词 | 预存 — 三个工具均使用 `"cancelled by the host"` 消息，与 download/preprocess 工具一致，属于 `ToolCancelledOutcome` 标准契约 |

### 4. 默认禁用

| 检查项 | 结果 |
|---|---|
| `tool_discovery.json` 所有 provider `enabled: false` | 通过 — 全部 6 个 provider 默认禁用且 `allow_empty: true` |

---

## 验证摘要

| 检查项 | 结果 |
|---|---|
| 全量 pytest | **294 passed, 1 skipped, 3 warnings**（仅 edgartools deprecation） |
| 全量 pyright | **0 errors, 0 warnings, 0 informations** |
| `Any`/type `object` 扩散 | 0（全 WU 生产文件零 `Any` 注解） |
| Host/Engine/Service/UI/CLI 反向依赖 | 0（Fins 层内无违规 import） |
| runtime 反向依赖 | 0（`dayu/runtime/` 不依赖上层） |
| OLD 业务逻辑重写 | 无（所有业务迁移均有 OLD direct import tracing evidence） |
| 残留风险无 owner | 无（Issue 129 覆盖 crash recovery/prepare-activate；deferred failure-path matrix 有 Slice 4 controller 裁决记录） |

## Open Questions

无。

## Residual Risk

| 风险 | Owner/Destination | 状态 |
|---|---|---|
| Crash recovery / prepare-activate hardening for awaiting external jobs | Issue #129（已评论 2026-06-09，明确 `start_upload` 纳入 scope） | tracked |
| Physical cancel/revoke beyond cooperative `request_cancel` | Issue #92 / WU-WAIT-03 | tracked |
| Broader upload runtime failure-path matrix（conversion error, mid-upload cancel） | Slice 4 controller deferred CTRL-S4-D1 | deferred |
| CN/HK process/preprocess migration | Not in WU scope（plan non-goal） | out-of-scope |
| Real Docling integration CI coverage（需 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`） | Opt-in integration test（58 passed, 1 skipped 中唯一的 skip） | accepted limitation |
| SEC download state cache 使用直接 `open()` 写入 `.dayu/` 路径 | `sec_download_state.py:232-233` — 预存于 OLD pipeline，为 HTTP cache 基础设施非文档存储 | accepted limitation |
