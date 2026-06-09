# WU-TOOLS-01-F01-03 Aggregate DeepReview Re-Review — AgentDS

## Scope

- **Mode**: current changes (aggregate deepreview fix re-review)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Output file**: `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-rereview-ds.md`
- **Reviewed scope**: 仅 MiMo F1/F2 — LLM-facing `ToolFailedOutcome` message/hint 泄漏 `durable job record` 与 `Fins ingestion runtime` 的窄修复
- **Fix artifact**: `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-fix-codex.md`

## Verdict

**pass** — MiMo F1/F2 均已 fixed；0 blocking findings；0 new findings。

---

## MiMo F1: OSError start-failed message 泄漏 `durable job record`

**Status: fixed**

- **文件**: `dayu/fins/tools/download_tools.py:102-104`, `preprocess_tools.py:101-103`, `upload_tools.py:122-124`
- **验证证据**:
  1. 三个工具的 OSError handler 的 `message` 和 `hint` 均不含 `durable job record`
  2. `download_tools.py:102-104`: `message="下载任务启动失败，未能保存任务记录。"` + `hint="请稍后重试，或让系统维护者检查 Fins workspace 存储权限。"`
  3. `preprocess_tools.py:101-103`: `message="预处理任务启动失败，未能保存任务记录。"` + 同上 hint
  4. `upload_tools.py:122-124`: `message="上传任务启动失败，未能保存任务记录。"` + 同上 hint
  5. targeted scan: `rg "durable job record"` 在三个工具文件中无匹配

## MiMo F2: 非预期异常 hint 泄漏 `Fins ingestion runtime`

**Status: fixed**

- **文件**: `dayu/fins/tools/download_tools.py:110-112`, `preprocess_tools.py:109-111`, `upload_tools.py:130-132`
- **验证证据**:
  1. 三个工具的 unexpected exception handler 的 `message` 和 `hint` 均不含 `Fins ingestion runtime`
  2. `download_tools.py:110-112`: `message="下载任务启动失败，未进入等待状态。"` + `hint="请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。"`
  3. `preprocess_tools.py:109-111`: `message="预处理任务启动失败，未进入等待状态。"` + 同上 hint
  4. `upload_tools.py:130-132`: `message="上传任务启动失败，未进入等待状态。"` + 同上 hint
  5. targeted scan: `rg "Fins ingestion runtime"` 在三个工具文件中无匹配

## 测试覆盖

- **文件**: `tests/fins/test_fins_ingestion_tools.py:86-89, 638-781, 784-799`
- **验证证据**:
  1. `_FORBIDDEN_LLM_ERROR_FRAGMENTS` (lines 86-89): `("durable job " + "record", "Fins ingestion " + "runtime")` — 使用字符串拼接避免 targeted scan 自身命中
  2. 6 个新增测试函数（每个工具 × OSError + unexpected exception），均调用 `_assert_failed_outcome_hides_internal_terms(outcome)`
  3. `_assert_failed_outcome_hides_internal_terms` (lines 784-799): 拼接 `outcome.result.message + "\n" + outcome.result.hint`，对每个 banned fragment 执行 `assert fragment not in visible_text`
  4. 测试文件自身 targeted scan: `rg "durable job record|Fins ingestion runtime"` 无匹配（字符串拼接规避）

## 无新增问题

- 工具 docstring 中仍出现 "durable job"（如 `upload_tools.py:5`）——这些是内部开发者文档，不是 LLM-facing 文本，不在 F1/F2 scope 内
- `_ERROR_JOB_START_FAILED` 等常量名未变——这些是内部错误码（`fins_download_start_failed` 等），属于内部语义标识，对 LLM 用户可读，不暴露内部实现术语
- 无新增类型/分层/测试弱化问题

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest `tests/fins/test_fins_ingestion_tools.py` | 29 passed, 3 warnings (仅 edgartools deprecation) |
| pyright `dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `durable job record` / `Fins ingestion runtime` in tool files | 0 matches |
| `durable job record` / `Fins ingestion runtime` in test file | 0 matches |
| 新增 LLM-facing 术语泄漏 | 无 |
| 新增类型/分层问题 | 无 |
| 测试弱化 | 无 |
