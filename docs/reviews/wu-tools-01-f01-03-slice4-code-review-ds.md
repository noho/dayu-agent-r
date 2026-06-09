# WU-TOOLS-01-F01-03 Slice 4 Code Review — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice4-code-review-ds.md`
- **Included scope**:
  - Production: `dayu/fins/pipelines/docling_upload_service.py`, `sec_upload_workflow.py`, `upload_company_meta.py`, `upload_filing_events.py`, `upload_material_events.py`, `upload_progress_helpers.py` (new); `sec_pipeline.py`, `cn_pipeline.py`, `ingestion_runtime.py`, `service_runtime.py` (modified)
  - Tests: `test_docling_upload_service.py`, `test_docling_upload_service_integration.py`, `test_sec_pipeline_upload_filing_stream.py`, `test_sec_pipeline_upload_material_stream.py` (new); `test_cn_pipeline.py`, `test_fins_ingestion_runtime.py` (modified)
  - Docs: `dayu/fins/README.md`, `tests/README.md`, `docs/reviews/wu-tools-01-f01-03-slice4-implementation-codex.md`
- **Excluded scope**: upload tool/provider, wait adapter/service assembly, CLI, Host/Engine public contracts, process/rebuild modules
- **Parallel review coverage**: 3 subagents covered upload service/workflow modules, pipeline/runtime changes, and test coverage/AGENTS compliance. All findings verified by primary reviewer against source code.

## Verdict

**fix-accepted** — 2 high findings, 3 medium findings, 4 low findings. 0 blocking correctness defects; all issues are maintainability/clarity/docstring or test coverage gaps.

Migration 质量高：OLD upload 语义完整保留（auto/create/update/delete actions, skip/overwrite, source fingerprint/version, SEC/CN filing/material IDs, Docling injection），`FinsIngestionRuntime` 仍只管 lifecycle，`ProductionFinsUploadRunner` 只做 handoff/summary，upload 长事务 job 边界正确，storage/ticker 边界正确，无 Host/Engine/CLI/tool/provider 反向依赖。

---

## Findings

### F1-[未修复]-[高]-`sec_pipeline.py` 与 `cn_pipeline.py` 模块 docstring 过期——声称 upload 不在本 Slice

- **入口/函数**: 模块级 docstring
- **文件(行号)**:
  - `dayu/fins/pipelines/sec_pipeline.py:3-5` — "上传、process、CLI 和 Host 集成不在本 Slice 内"
  - `dayu/fins/pipelines/cn_pipeline.py:3-5` — "上传、process、CLI 和 Host 集成不在本 Slice 内"
- **输入场景**: 开发者阅读模块 docstring 理解模块职责。
- **实际行为**: 两个模块现已包含大量 upload facade 方法（`upload_filing`、`upload_filing_stream`、`upload_material`、`upload_material_stream`），但模块 docstring 仍声称 upload 不在模块范围内。
- **预期行为**: docstring 应反映当前模块职责，包含 upload facade 说明。
- **直接证据**:
  - `sec_pipeline.py:5`: "上传、process、CLI 和 Host 集成不在本 Slice 内" 与 lines 599-858 的 4 个 upload 方法矛盾
  - `cn_pipeline.py:5`: "上传、process、CLI 和 Host 集成不在本 Slice 内" 与 lines 608-1096 的 upload 方法矛盾
- **影响**: 维护者可能误判模块职责范围，影响代码导航与变更决策
- **建议改法和验证点**: 更新两个模块 docstring 为包含 upload facade（同时保留 download 说明和 process/CLI/Host 排除声明）
- **修复风险（低）**: 仅 docstring 文本变更
- **严重程度（高）**: blocking（误导性文档）

### F2-[未修复]-[高]-`sec_pipeline.py` 与 `cn_pipeline.py` 模块 docstring 过期——声称 process 不在本 Slice

- **入口/函数**: 模块级 docstring（与 F1 同位置）
- **文件(行号)**: 同上 `sec_pipeline.py:3-5`、`cn_pipeline.py:3-5`
- **说明**: 当前 Slice 确实不包含 process，但 docstring 将 upload 和 process 并列排除，使 upload 的事实存在被掩盖。建议在修复 F1 时明确区分：upload facade 已迁移，process 仍排除。
- **严重程度**: 并入 F1 修复

### F3-[未修复]-[中]-`docling_upload_service.py` 的 `__all__` 暴露 10 个 `_` 前缀私有符号

- **入口/函数**: 模块级 `__all__`
- **文件(行号)**: `dayu/fins/pipelines/docling_upload_service.py:1237-1264`
- **直接证据**: `__all__` 包含以下 `_` 前缀符号：
  - `_PendingFileAsset` (line 1246)
  - `_build_upload_source_fingerprint` (line 1247)
  - `_can_skip_upload` (line 1248)
  - `_convert_bytes_with_docling` (line 1249)
  - `_increment_document_version` (line 1250)
  - `_normalize_ticker` (line 1251)
  - `_pick_primary_docling_file` (line 1252)
  - `_resolve_document_version` (line 1253)
  - `_resolve_upsert_mode` (line 1254)
  - `_validate_source_files` (line 1255)
- **输入场景**: 外部调用方通过 `from docling_upload_service import *` 或检查 `__all__` 了解公共 API。
- **实际行为**: `_` 前缀语义约定表示"私有实现细节"，但 `__all__` 将其标记为公共 API。形成自相矛盾——外部测试文件（`test_docling_upload_service.py:14-18`、`test_docling_upload_service_integration.py:11`）直接导入这些符号。
- **预期行为**: 要么去掉 `_` 前缀（如需公共 API），要么从 `__all__` 移除（如确实私有），测试通过内部路径或公开工厂函数访问。
- **影响**: 公共 API 边界模糊；调用方无法判断哪些符号稳定、哪些可能变更；测试便利性驱动了 API 设计
- **建议改法和验证点**:
  1. 决定每个符号的公共/私有归属
  2. 公共符号去掉 `_` 前缀；私有符号从 `__all__` 移除
  3. 更新测试导入路径
- **修复风险（低）**: 仅重命名与导入变更
- **严重程度（中）**: non-blocking

### F4-[未修复]-[中]-`DefaultFinsRuntime` 为 upload 与 download 创建独立 pipeline 实例

- **入口/函数**: `DefaultFinsRuntime.get_ingestion_runtime`
- **文件(行号)**: `dayu/fins/service_runtime.py:501-542`
- **输入场景**: `DefaultFinsRuntime.create()` 后调用 `get_ingestion_runtime()`。
- **实际行为**: 创建了 5 个 pipeline 实例：
  - `SecPipeline` × 2（1 download adapter + 1 upload）
  - `CnPipeline` × 3（1 CN download adapter + 1 HK download adapter + 1 upload）
  upload pipeline 与 download pipeline 共享同一组 storage repository 实例（行为正确），但作为独立 Python 对象不共享状态。
- **预期行为**: 从正确性角度看，共享 repository 实例即满足功能需求。但 5 个 pipeline 实例表明架构意图不够清晰——upload pipeline 从 download pipeline 独立是正确的（不同 state/依赖），但 3 个 `CnPipeline` 实例（2 download + 1 upload）其中 download 之间也有 CN/HK 拆分的冗余。
- **影响**: 维护困惑——未来修改变更 pipeline 构造逻辑需确认是否影响 upload；非功能缺陷
- **建议改法和验证点**: 在 `get_ingestion_runtime()` 方法中添加注释说明分离意图，或考虑 pipeline 实例复用（如 download 共用 CN/HK 同一 pipeline、仅 sleep_seconds 差异化注入 adapter 层）
- **修复风险（低）**: 仅为架构注释或重构，不改变行为
- **严重程度（中）**: non-blocking

### F5-[未修复]-[中]-upload 测试缺少失败路径覆盖

- **入口/函数**: 缺失的测试函数
- **文件**:
  - `tests/fins/test_docling_upload_service.py` — 无 conversion error/invalid files 测试
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py` — 无转换错误/空文件/取消中流测试
  - `tests/fins/test_sec_pipeline_upload_material_stream.py` — 同上
  - `tests/fins/test_cn_pipeline.py` (diff) — CN upload 无失败路径
  - `tests/fins/test_fins_ingestion_runtime.py` (diff) — 无取消/转换失败运行时测试
- **直接证据**: 所有 upload 测试均为成功路径（58 passed），无 `RuntimeError`、`ValueError` 或 `cancellation_checker=True` 路径
- **影响**: 上传失败收口路径未经测试覆盖；若 Docling 转换异常、文件列表为空、取消请求中断上传，job 终态行为未经回归保护
- **建议改法和验证点**: 按优先级添加：① Docling 转换失败 → FAILED job ② 取消中途检查 → CANCELLED job ③ 空文件列表 → 适当错误终态
- **严重程度（中）**: non-blocking（成功路径已知正确，旧实现已在此行为上稳定运行）

### F6-[未修复]-[低]-`cast_upload_host` 为死代码

- **入口/函数**: `cast_upload_host`
- **文件(行号)**: `dayu/fins/pipelines/sec_upload_workflow.py:539-552, 557`
- **输入场景**: 无调用方。
- **实际行为**: `cast_upload_host(host)` 是 `return cast(SecUploadWorkflowHost, host)` 的 trivial 包装——`typing.cast` 本身不产生运行时代码，且 Python Protocol 使用结构子类型无需显式 cast。全代码库零调用方。
- **预期行为**: 删除死代码。
- **直接证据**: `rg 'cast_upload_host' --type py` 仅命中定义 (line 539) 和 `__all__` (line 557)，无任何调用点
- **影响**: 死代码污染模块 API 面；维护者可能误以为此函数有调用方
- **建议改法和验证点**: 从代码与 `__all__` 中移除
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F7-[未修复]-[低]-`test_fins_ingestion_runtime.py` 缺少 SEC material 与 CN filing 运行时路径覆盖

- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:1194-1280`
- **实际行为**: 仅覆盖 `ProductionFinsUploadRunner` 的 SEC filing + CN material 两种组合，缺：
  - SEC material upload via production runner
  - CN filing upload via production runner
- **直接证据**: diff 中仅 2 个测试函数，覆盖路径不完整
- **影响**: 4 种 market × kind 组合中 2 种未经 runtime 级测试
- **严重程度（低）**: non-blocking（pipeline 级测试已覆盖 4 种路径，runtime 级缺失为集成测试缺口）

### F8-[未修复]-[低]-`test_docling_upload_service.py` 缺少 `action="update"` 直测

- **文件**: `tests/fins/test_docling_upload_service.py`
- **实际行为**: `execute_upload` 的 `action="update"` 路径仅经过 `_resolve_upsert_mode` helper 间接测试，无全链路 `execute_upload(action="update")` 直接测试
- **严重程度（低）**: non-blocking（auto→update 路径在 pipeline 级测试中间接覆盖）

### F9-[未修复]-[低]-`upload_progress_helpers.py` 字典键使用字符串字面量而非引用上游常量

- **文件(行号)**: `dayu/fins/pipelines/upload_progress_helpers.py:12-24`
- **实际行为**: `_UPLOAD_FILE_TO_FILING_EVENT_TYPE` 和 `_UPLOAD_FILE_TO_MATERIAL_EVENT_TYPE` 的键使用裸字符串 `"conversion_started"`、`"file_uploaded"` 等。这些值与 `docling_upload_service.py` 中 `UploadFileEventType` Literal 类型定义对应，但未引用共享常量。
- **影响**: 若 `UploadFileEventType` 字面量值变更，需手动同步此模块
- **严重程度（低）**: non-blocking（值变化概率低，且变更会被类型检查发现）

---

## 正面确认项

| 审查项 | 结论 | 证据 |
|---|---|---|
| OLD upload 语义保留（auto/create/update/delete） | 通过 | `docling_upload_service.py:55,186-187,198-214,289-293,697-702` |
| skip/overwrite 逻辑保留 | 通过 | `docling_upload_service.py:224-241,697-702` |
| source fingerprint/version 保留 | 通过 | `docling_upload_service.py:705-728,731-751` |
| SEC/CN filing/material ID 保留 | 通过 | `docling_upload_service.py:856-892,994-1029,1032-1064` |
| Docling 通过注入点（Callable）调用 | 通过 | `docling_upload_service.py:144,490` |
| storage writes 仅通过协议 | 通过 | `SourceDocumentRepositoryProtocol`, `DocumentBlobRepositoryProtocol` |
| `FinsIngestionRuntime` 仅管 lifecycle | 通过 | `ingestion_runtime.py:1764-1790`; 无业务规则泄露 |
| `ProductionFinsUploadRunner` 仅 handoff/summary | 通过 | `service_runtime.py:59-233` |
| upload job 为长事务 durable job | 通过 | `start_upload` → background runner → cooperative cancellation |
| 无 upload tool/provider/wait adapter/CLI | 通过 | boundary scan 无匹配 |
| 无 Host/Engine 公共契约修改 | 通过 | diff 仅触及 fins 内部 |
| US→SEC, CN/HK→CN pipeline 路由 | 通过 | `service_runtime.py:105-233` |
| cancellation_checker 端到端传递 | 通过 | runtime → runner → pipeline → workflow |
| HK upload 不拒绝（保留 OLD 支持） | 通过 | `cn_pipeline.py` upload 方法无 market 拒绝逻辑 |
| README 仅声明 direct runtime runner 存在 | 通过 | `README.md:464` 明确 "不暴露 upload tool provider" |
| 中文 docstring | 通过 | 所有新代码中文 docstring |
| `Any`/`object` 类型 | 通过 | targeted scan 无匹配 |
| Host/Engine/CLI/tool/provider 反向依赖 | 通过 | boundary scan 无匹配 |
| process/rebuild 未迁移 | 通过 | import 路径无 process/rebuild 模块 |
| Docling 转换不在 gate lease 内 | 通过 | upload 无 PDF gate 概念; Docling 调用直接执行 |

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest (6 测试文件) | 58 passed, 1 skipped, 3 warnings (仅 edgartools deprecation) |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `Any`/type `object` 扩散 | 0 |
| Host/Engine/upload tool/provider/CLI 引入 | 0 |
| process/rebuild 模块引入 | 0 |
| OLD 业务语义被重写 | 无 |
| upload 工具/provider 边界被触碰 | 无 |

## Open Questions

1. **Skip 测试**: `test_docling_upload_service_integration.py` 的单测试被 `os.environ.get("DAYU_RUN_DOCLING_UPLOAD_INTEGRATION") != "1"` 跳过。这是正确的 opt-in 集成测试模式——真实 Docling 集成需显式环境变量且需 `docling` 包已安装。非问题。

## Residual Risk

1. **模块 docstring 过期 (F1)**: 两个 pipeline 模块 docstring 声称 upload 不在范围内，可能导致维护者误判。低风险修复，强建议在 merge 前修正。

2. **upload 失败路径测试覆盖不足 (F5)**: 所有测试仅覆盖成功路径。Docling 转换失败、取消中流等场景未经测试保护。虽然 OLD 实现在这些路径上已稳定运行，但迁移变更可能引入边界行为差异。

3. **真实 Docling 集成未在 CI 默认运行**: 集成测试需要 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 手动启用——Docling 运行时（ML 模型下载等）不在默认 CI 矩阵内。

4. **upload tool/provider/wait adapter 仍在 Slice 5**: 当前 upload 仅支持 `FinsIngestionRuntime.start_upload()` direct runtime 调用。LLM 需通过 tool provider 发起 upload 仍在后续 Slice。
