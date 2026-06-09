# WU-TOOLS-01-F01-03 Slice 5 Code Review — AgentMiMo

**审查时间**: 20260609-190141
**审查范围**: Slice 5 Upload Awaiting Tool, Provider, Wait Adapter, And Service Assembly (workspace dirty changes)
**审查基准**: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md` (Slice 5), `docs/host/design.md`, `docs/engine/design.md`
**实现 artifact**: `docs/reviews/wu-tools-01-f01-03-slice5-implementation-codex.md`

## 结论

**pass**

7 项审查全部通过，无 finding。OLD upload 语义未被重写，upload 长事务边界未被触碰，分层/依赖合规，tool schema LLM-facing 自解释。

## 审查项逐项结果

### 1. start_fins_upload 工具职责边界 — PASS

- `FinsUploadToolCallable.__call__` (upload_tools.py:76-134) 只做：参数解析 → allowed_upload_roots/非空文件校验 → `runtime.start_upload()` → 返回 `ToolAwaitingOutcome`。
- 参数/路径错误在 `_upload_request_from_arguments` 阶段抛 `ValueError`，被 catch 后返回 `ToolFailedOutcome`，**durable job 尚未创建**。
- 空文件 (0 字节) 校验在 `_resolve_upload_path` (upload_tools.py:481-482)：`candidate.stat().st_size <= 0`。
- auto/create/update 要求非空 files；delete 拒绝 files (upload_tools.py:410-420)。
- 不等待 Docling、不复制业务规则、不涉及 UI/CLI。

### 2. Upload provider fail closed — PASS

- `discover_tools` (upload_provider.py:25-54) 必须经过 `parse_fins_workspace_root_config` 和 `parse_allowed_upload_roots_config` 两条校验路径，任一失败抛 `ValueError`，不返回空工具集。
- `parse_fins_workspace_root_config` (provider.py:98-117)：类型 → 非空 → 绝对路径三重校验，无 cwd/env fallback。
- `parse_allowed_upload_roots_config` (upload_provider.py:57-83)：非空 list → 每元素非空 str → 绝对路径四重校验。
- `build_fins_upload_tool` 内部 `_normalize_allowed_upload_roots` 做二次防御校验。

### 3. Wait adapter / service assembly — PASS

- `FINS_UPLOAD_AWAITING_TOOL_NAME` 通过 `upload_tools.UPLOAD_TOOL_NAME` 常量别名引入，不硬编码字符串。
- `FINS_SUPPORTED_AWAITING_TOOL_NAMES` 包含 download/preprocess/upload 三个成员。
- Wait adapter 复用 Host 已有 `ResolveWait*Outcome` 类型，resume policy 仍为 `POLL`，**不改 Host wait schema**。
- `_single_fins_workspace_root` (host_assembly.py) 在 assembly 阶段做 workspace 一致性校验。
- `_deterministic_tool_names` (wait_adapter.py) 做 duplicate binding 校验。
- 两者均在 `open_host` 前 fail-fast。
- host_assembly 只从 `dayu.fins.ingestion` 导入常量和工厂函数，不导入具体 provider 模块。

### 4. Tool schema LLM-facing 自解释 — PASS

Schema (upload_tools.py:208-302) 使用业务语义参数：`ticker`, `upload_kind`, `action`, `files`, `fiscal_year`, `fiscal_period`, `form_type`, `material_name`, `document_id`, `internal_document_id`, `amended`, `filing_date`, `report_date`, `company_name`, `ticker_aliases`, `overwrite`。

未暴露：Host, EventLog, wait_id, tool_call_id, digest, cursor, raw job path, durable, ingestion runtime, awaiting 等内部术语。

`internal_document_id` 是既有业务概念 (ingestion_runtime.py 中 17+ 处使用)，指"来源系统内部文档 ID"，非工程治理层面的 "internal"。description 为 "Optional explicit material internal document id. Omit unless the user supplied a precise source id."，LLM 可自解释。

### 5. 分层/依赖合规 — PASS

- `upload_tools.py`：只依赖 `dayu.contracts.*`, `dayu.fins.ingestion_runtime`, `dayu.fins.tools._ingestion_tool_helpers`。无 Host/Engine/Service/UI/CLI 依赖。
- `upload_provider.py`：只依赖 `dayu.contracts.*`, `dayu.runtime.tools_discovery.*`, `dayu.fins.service_runtime`, `dayu.fins.tools.provider`, `dayu.fins.tools.upload_tools`。无 Host/Engine/Service/UI/CLI 依赖。
- `host_assembly.py`：只从 `dayu.fins.ingestion` 导入常量和 `build_fins_wait_adapter_registry`，不导入具体 provider。
- `_ingestion_tool_helpers.py`：新增 `_optional_int` / `_required_int`，与已有 `_optional_text` / `_required_bool` 模式一致。

### 6. 测试覆盖 — PASS

新增 8 个测试覆盖：
- provider fail closed (缺少 `allowed_upload_roots`)
- awaiting outcome (durable job, EXTERNAL_JOB await kind)
- 路径校验 (allowed root 外的文件)
- 空文件拒绝 (0 字节)
- delete 拒绝 files
- 取消 (pre-cancelled token)
- OSError / RuntimeError 异常处理

修改 5 个既有测试扩展 upload 覆盖，**未弱化 download/preprocess 行为**。

Assembly 测试覆盖：成功 binding、workspace root mismatch fail-fast、duplicate binding fail-fast。

Controller 补充的空文件校验有对应测试 `test_upload_tool_empty_file_returns_failed_outcome_before_job_creation`。

### 7. README 更新 — PASS

4 个 README 变更均为事实性描述：
- `dayu/fins/README.md`：upload provider 条目、`allowed_upload_roots` 要求、`start_upload` API、wait adapter 常量。
- `dayu/config/README.md`：`financial-upload-tools` provider 配置行。
- `tests/README.md`：新增测试场景描述。
- `dayu/README.md`：upload 加入 feature 列表。

均为单行事实更新，无推测性内容，格式保持一致。

Plan 将 README 更新归为 Slice 6 职责，但本次变更是对 Slice 5 新增功能的事实性记录，不提前声称 Slice 6 内容。

## 验证命令

| 命令 | 结果 |
|------|------|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_runtime.py -q` | 106 passed, 3 warnings |
| `pyright upload_tools.py upload_provider.py wait_adapter.py host_assembly.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

## Open Questions

无。

## Residual Risks

- `test_combined_tools_acceptance.py` 未变更 (Plan 提及 "if needed")，说明 combined fixture 未受影响，无风险。
- Plan 将 README 更新归为 Slice 6，本次提前完成但内容仅为事实性记录，不构成偏差风险。
