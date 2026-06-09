# WU-TOOLS-01-F01-03 Slice 5 Code Review — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice5-code-review-ds.md`
- **Included scope**:
  - Production: `dayu/fins/tools/upload_tools.py`, `dayu/fins/tools/upload_provider.py` (new); `dayu/fins/tools/_ingestion_tool_helpers.py`, `dayu/fins/ingestion/wait_adapter.py`, `dayu/fins/ingestion/__init__.py`, `dayu/service/host_assembly.py`, `dayu/config/tool_discovery.json` (modified)
  - Tests: `tests/fins/test_fins_ingestion_tools.py`, `tests/service/test_host_assembly.py` (modified)
  - Docs: `dayu/README.md`, `dayu/config/README.md`, `dayu/fins/README.md`, `tests/README.md`
- **Excluded scope**: OLD upload business logic, CN/HK/upload/process/CLI, Host/Engine internals
- **Parallel review coverage**: 3 subagents covered upload tool/provider/helpers, wait adapter/service assembly/config, and tests/schema/README/AGENTS compliance. All findings verified by primary reviewer.

## Verdict

**pass-with-findings** — 0 blocking correctness defects；1 medium non-blocking finding；upload tool/provider/wait adapter 实现正确，分层合规，LLM-facing schema 自查质量高。

核心实现质量高：`start_fins_upload` 工具只做参数解析、路径安全校验、delegate 到 shared runtime，不复制上传业务逻辑。Provider fail-closed（绝对路径 workspace_root + 非空绝对 allowed_upload_roots）。Wait adapter 不改 Host wait schema，workspace mismatch 与 duplicate binding 在 open_host 前失败。Tool schema 不暴露 Host/EventLog/wait_id 等内部治理词。无 Host/Engine/Service/UI/CLI 反向依赖。

---

## Findings

### F1-[未修复]-[中]-下载工具测试 `_wait_ingestion_job_terminal` 被移除，与预处理/上传测试不一致

- **文件(行号)**: `tests/fins/test_fins_ingestion_tools.py:320-344`
- **输入场景**: 运行 `test_download_tool_returns_external_job_awaiting_outcome`。
- **实际行为**: diff 显示 `_wait_ingestion_job_terminal(runtime, outcome.await_spec.resume_token)` 被移除。当前测试在验证 `record.operation_kind` 和 `record.normalized_ticker` 后直接结束，不等待 job 到达终态。
- **预期行为**: 与 `test_preprocess_tool_returns_external_job_awaiting_outcome` (line 372) 和 `test_upload_tool_returns_external_job_awaiting_outcome` (line 411) 一致，应等待 job 终态以验证完整的 download job 生命周期。
- **直接证据**:
  - `git diff -- tests/fins/test_fins_ingestion_tools.py` 显示 `-    _wait_ingestion_job_terminal(runtime, outcome.await_spec.resume_token)` 在下载测试中被移除
  - `test_preprocess_tool_returns_external_job_awaiting_outcome` 和 `test_upload_tool_returns_external_job_awaiting_outcome` 均保留 `_wait_ingestion_job_terminal` 调用
- **影响**: 下载测试不再验证 job 终态到达——若 download job 因回归进入非预期中间状态，测试不会捕获
- **建议改法和验证点**: 恢复 `_wait_ingestion_job_terminal` 调用
- **修复风险（低）**: 单行恢复，不影响其他测试
- **严重程度（中）**: non-blocking

---

## 正面确认项

| 审查项 | 结论 | 证据 |
|---|---|---|
| **工具层 — 参数校验与错误处理** | | |
| `_upload_request_from_arguments` 正确解析 filing/material 字段 | 通过 | `upload_tools.py:305-360`；filing 要求 fiscal_year/fiscal_period；material 要求 form_type/material_name |
| auto/create/update 要求 files，delete 拒绝 files | 通过 | `upload_tools.py:425-431` |
| 空文件/空字符串在 durable job 创建前失败 | 通过 | `upload_tools.py:481`（zero-byte check）+ `:172`（empty string check），均在 `start_upload()` 之前 |
| 路径校验：非空字符串、expand/resolve、existing file、在 allowed_upload_roots 内 | 通过 | `upload_tools.py:458-483` 四步检查 |
| 参数/路径错误返回 `ToolFailedOutcome`（在 job 创建前） | 通过 | `upload_tools.py:110-117` |
| 取消返回 `ToolCancelledOutcome` | 通过 | `upload_tools.py:97-99, 106-109` |
| OSError/异常返回 `fins_upload_start_failed` | 通过 | `upload_tools.py:118-133` |
| 工具只 delegate 到 shared runtime，不复制业务逻辑 | 通过 | `FinsUploadToolCallable.__call__` 仅做 parse → validate → `self.runtime.start_upload()` |
| **Provider 层 — fail-closed** | | |
| enabled 但无绝对 `workspace_root` → fail closed | 通过 | `upload_provider.py:40`；`parse_fins_workspace_root_config` 校验路径非空、绝对路径 |
| enabled 但无非空绝对 `allowed_upload_roots` → fail closed | 通过 | `upload_provider.py:57-83`：列表非空、每元素非空字符串、绝对路径 |
| 构造 `DefaultFinsRuntime.get_ingestion_runtime()` 并 delegate 到 `build_fins_upload_tool` | 通过 | `upload_provider.py:42-52` |
| Provider/source ID 正确 | 通过 | `_PROVIDER_ID = "financial-upload-tools"`；`_SOURCE_ID = "dayu.fins.tools.upload_provider"` |
| **Wait adapter / Assembly 层** | | |
| `FINS_UPLOAD_AWAITING_TOOL_NAME` 定义 + `FINS_SUPPORTED_AWAITING_TOOL_NAMES` 包含三者 | 通过 | `wait_adapter.py:58-70` |
| poll/abandon 正确覆盖 upload job（无需 Host schema 变更） | 通过 | `wait_adapter.py:103-143`；通过 `external_job_ref.external_job_id` 通用适配 |
| `host_assembly.py` 识别 upload provider 三要素（id/import_path/source_id） | 通过 | `host_assembly.py:96-116` |
| workspace mismatch → `ValueError`（open_host 前） | 通过 | `host_assembly.py:1180-1198` |
| duplicate binding → `ValueError`（open_host 前） | 通过 | `wait_adapter.py:140-156` |
| download/preprocess 路径未改动 | 通过 | 对称扩展，无移除 |
| Service assembly 不导入具体 provider 模块 | 通过 | 仅引用字符串 frozenset，不 import tool modules |
| `tool_discovery.json` upload 默认 disabled | 通过 | `enabled: false`，结构一致 |
| `__init__.py` 导出 `FINS_UPLOAD_AWAITING_TOOL_NAME` | 通过 | `__init__.py:13-21` |
| **LLM-facing Schema** | | |
| 无 Host/EventLog/wait_id/tool_call_id/digest/cursor 等内部治理词 | 通过 | `upload_tools.py` schema 文本 grep 零匹配 |
| 参数自解释（ticker, upload_kind, action, files, fiscal_year, etc.） | 通过 | 15 个参数均有业务语言描述 |
| `source_kind` 不出现在 LLM 输入中 | 通过 | LLM 用 `upload_kind: filing/material`；`source_kind` 仅在 runtime 内部映射 |
| `allowed_upload_roots` 治理概念不暴露 | 通过 | Schema 描述为 "Paths must be under the configured upload roots" |
| **分层 / 依赖** | | |
| Fins tools 不 import Host/Engine/Service/UI/CLI | 通过 | 仅 `dayu.contracts.*`, `dayu.fins.*`, `dayu.runtime.tools_discovery` |
| Service assembly 不 import 具体 Fins tool provider 模块 | 通过 | 仅通过 provider id/import-path/source-id 字符串识别 |
| **AGENTS 合规** | | |
| 中文 docstring | 通过 | 所有新文件/函数提供完整中文 docstring |
| 无 `Any`/`object` 类型 | 通过 | targeted scan 零匹配 |
| 无 `@pytest.mark.unit` | 通过 | 新测试无此装饰器 |
| **README 更新** | | |
| 只记录已实现事实（不声称工具 hardened/生产就绪） | 通过 | `README.md:467` 列出 4 项实现能力，无定性断言 |
| 遵循各 README 的 Agent 更新约束 | 通过 | 所有 4 个 README 均仅更新事实反映，未扩写职责范围 |
| **Controller 补充 — 空文件校验** | | |
| 空文件在 job 创建前返回失败 outcome | 通过 | `upload_tools.py:481` + 测试 `test_upload_tool_empty_file_returns_failed_outcome_before_job_creation:476-510` |

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest (3 测试文件) | 73 passed, 3 warnings (仅 edgartools deprecation) |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `Any`/type `object` 扩散 | 0 |
| Host/Engine/Service/UI/CLI 反向依赖 | 0 |
| upload 业务逻辑重新实现 | 无 |
| Host wait schema 修改 | 无 |
| LLM schema 内部治理词泄露 | 0 |

## Open Questions

无。

## Residual Risk

1. **download 测试弱化 (F1)**: `_wait_ingestion_job_terminal` 在下载工具测试中被移除，download job 终态验证缺失。建议恢复。

2. **upload 失败路径测试仅在 deferred scope 内**: 上传工具级测试覆盖了参数错误、路径越界、空文件等"工具前"失败；但 Docling 转换失败、上传运行中取消等 runtime 级失败路径由 Slice 4 deferred coverage 覆盖，不在 Slice 5 内。不是 Slice 5 引入的新风险。

3. **Crash recovery**: 上传 job 的 crash recovery 与 prepare/activate hardening 仍由 WAIT/Issue 129 follow-up 跟踪，Slice 5 不引入私有 Host-like 状态机。
