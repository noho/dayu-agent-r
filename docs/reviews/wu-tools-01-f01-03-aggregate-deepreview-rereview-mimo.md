# WU-TOOLS-01-F01-03 Aggregate Deepreview Re-Review — AgentMiMo

**审查时间**: 20260609-192307
**审查范围**: AgentCodex 对 aggregate deepreview MiMo F1/F2 的窄修复
**修复 artifact**: `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-fix-codex.md`

## 结论

**pass**

F1/F2 全部修复，测试覆盖充分，未引入新问题。

## 复核项

### 1. F1/F2 修复验证 — PASS

**F1 (`durable job record` → 业务语言)**:

| 文件 | 行号 | 修复前 | 修复后 |
|------|------|--------|--------|
| `upload_tools.py` | 123 | `上传任务未能创建 durable job record。` | `上传任务启动失败，未能保存任务记录。` |
| `download_tools.py` | 103 | `下载任务未能创建 durable job record。` | `下载任务启动失败，未能保存任务记录。` |
| `preprocess_tools.py` | 102 | `预处理任务未能创建 durable job record。` | `预处理任务启动失败，未能保存任务记录。` |

**F2 (`Fins ingestion runtime` → 可操作指引)**:

| 文件 | 行号 | 修复前 | 修复后 |
|------|------|--------|--------|
| `upload_tools.py` | 132 | `请检查输入参数和 Fins ingestion runtime 配置。` | `请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。` |
| `download_tools.py` | 112 | `请检查输入参数和 Fins ingestion runtime 配置。` | `请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。` |
| `preprocess_tools.py` | 111 | `请检查输入参数和 Fins ingestion runtime 配置。` | `请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。` |

Targeted scan (`rg -n "durable job record|Fins ingestion runtime" dayu/fins/tools/ tests/fins/test_fins_ingestion_tools.py`) 无匹配。

### 2. 测试覆盖 — PASS

`_assert_failed_outcome_hides_internal_terms` (test_fins_ingestion_tools.py:784-799) 断言 `ToolFailedOutcome.result.message` 和 `hint` 不包含 `_FORBIDDEN_LLM_ERROR_FRAGMENTS` 中的两个被禁短语。

被覆盖的测试用例（6 个）：

| 测试 | 工具 | 错误类型 |
|------|------|---------|
| `test_download_tool_os_error_from_start_returns_start_failed_outcome` | download | OSError |
| `test_download_tool_unexpected_start_exception_returns_start_failed_outcome` | download | RuntimeError |
| `test_preprocess_tool_os_error_from_start_returns_start_failed_outcome` | preprocess | OSError |
| `test_preprocess_tool_unexpected_start_exception_returns_start_failed_outcome` | preprocess | RuntimeError |
| `test_upload_tool_os_error_from_start_returns_start_failed_outcome` | upload | OSError |
| `test_upload_tool_unexpected_start_exception_returns_start_failed_outcome` | upload | RuntimeError |

`_FORBIDDEN_LLM_ERROR_FRAGMENTS` (line 86-89) 使用字符串拼接避免 scan 自身匹配，设计合理。

### 3. 未引入新问题 — PASS

- 无新 LLM-facing 术语泄漏
- pyright 0 errors
- `git diff --check` passed
- 29 passed, 3 warnings（既有 edgar deprecation）
- 修复范围严格限定在 message/hint 字符串，未改动任何行为逻辑

## 验证命令

| 命令 | 结果 |
|------|------|
| `pytest tests/fins/test_fins_ingestion_tools.py -q` | 29 passed, 3 warnings |
| `pyright upload_tools.py download_tools.py preprocess_tools.py` | 0 errors |
| `rg "durable job record\|Fins ingestion runtime" dayu/fins/tools/ tests/fins/test_fins_ingestion_tools.py` | 无匹配 |
| `git diff --check` | passed |
