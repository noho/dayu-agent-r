# UF-FIX06 Slice 2 code re-review — AgentMiMo

## Review metadata

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：2（code review fix 后 re-review）
- Reviewer：AgentMiMo
- 日期：2026-08-15
- 基线提交：`c1db7b49`
- 输入：workspace diff（未提交）、Controller 裁决、fix artifact

## Accepted findings 逐项验证

### A1：LLM-facing files 要求不自足 → FIXED

**裁决要求**：同源 projection 必须显式说明 filing 与 material 的 auto/create/update 均至少提供一个文件、delete 不得提供文件。

**验证**：
- `upload_format_contract.py:561-576`：`project_fins_upload_format_text()` 的 `filing_files` 包含 `"auto/create/update 必须至少提供一个文件"` 与 `"delete 不得提供文件"`。
- `upload_tool_files` 包含 `"upload_kind=material 时，auto/create/update 必须至少提供一个文件"` 与 `"delete 不得提供文件"`。
- `test_upload_format_contract.py:284-297`：`test_text_projection_is_self_contained_and_uses_exact_suffix_order` 断言 `filing_text` 和 `tool_text` 均包含 `"auto/create/update 必须至少提供一个文件"` 和 `"delete 不得提供文件"`。
- `test_arg_parsing.py:398-433`：CLI help 测试断言同源片段。
- `test_fins_ingestion_tools.py:908-926`：LLM schema 测试断言 `"upload_kind=material 时，auto/create/update 必须至少提供一个文件"` 和 `"delete 不得提供文件"`。
- CLI help 与 LLM schema 均消费 `FINS_UPLOAD_FORMAT_TEXT`，同源。

**闭环确认**。

### A2：usage failure 的 240 字符 owner invariant 可被格式路径绕过 → FIXED

**裁决要求**：格式 owner 必须在保留 canonical `file_label` 的同时产生不超过 240 字符的 path-free message；usage public fact 自身必须 fail-fast 校验 closed code union 与 240 字符 message invariant。

**验证**：

1. **格式 owner 有界消息**：
   - `upload_format_contract.py:61-82`：`_bounded_format_failure_message()` 先尝试完整模板 `"财报主文件格式不受支持：{file_label}"`，若超过 240 字符则退回固定有界文案 `"财报主文件格式不受支持"`。
   - `upload_format_contract.py:91-111`：`FinsUploadFormatError.__init__()` 调用 `_bounded_format_failure_message` 作为 `super().__init__()` 的参数，`self.file_label` 保持完整 canonical label。
   - 因此 `str(error)` 始终 ≤240，`error.file_label` 始终是 canonical basename。

2. **usage public fact fail-fast**：
   - `ingestion_runtime.py:693-714`：`FinsUploadUsageFailure.__post_init__()` 校验：
     - `code` 必须是 `FinsUploadUsageCode` 或 `FinsUploadFormatFailureKind`（TypeError）
     - `message` 必须是非空字符串（TypeError/ValueError）
     - `message` 长度不能超过 240（ValueError）
   - 测试 `test_upload_usage_failure_fact_rejects_open_code_and_unbounded_message` 覆盖三种 fail-fast 场景。

3. **长 basename 集成测试**：
   - `test_upload_format_contract.py:231-263`：230 字符 basename（`'a' * 226 + '.doc'`）→ `file_label` 保持完整 230 字符 → message 退回 `"财报主文件格式不受支持"`（无 label），≤240。
   - `test_fins_ingestion_runtime.py:837-875`：validator 端测试同样用 230 字符 basename，断言 `cause.file_label == basename`、`failure.message == "财报主文件格式不受支持"`、`len(failure.message) <= 240`、`str(tmp_path) not in failure.message`。
   - `test_fins_commands.py:2371-2423`：material CLI 测试用 230 字符 basename 断言 CLI stderr 输出为 bounded message。

4. **极长 basename（>240 字符）的安全性**：
   - `canonicalize_fins_public_file_label` 中 `_public_file_label_requires_hiding` 检查 `len(value) > 240`，若超过则返回固定隐藏标签 `"输入文件（文件名已隐藏）"`（12 字符）。
   - 此路径下 `file_label = "输入文件（文件名已隐藏）"`，message = `"财报主文件格式不受支持：输入文件（文件名已隐藏）"`（24 字符），远低于 240。
   - 因此从 0 到任意长度的 basename 全域覆盖，message 始终 ≤240。

**闭环确认**。

### A3：material CLI 调用方 docstring 漏报新异常 → FIXED

**裁决要求**：`_upload_material_stream` 的中文 docstring 补齐 `FinsUploadFormatError`。

**验证**：
- `fins.py:708-711`：diff 显示新增 `:raises FinsUploadFormatError: 任一文件不具备 converter-required 格式时抛出。`

**闭环确认**。

### A4：`.json` candidate 限定缺失 → FIXED

**裁决要求**：help/schema 同源 projection 必须明说 `.json` 仅表示 Docling JSON candidate，不承诺任意 JSON 内容可转换。

**验证**：
- `upload_format_contract.py:566`：`filing_files` 包含 `".json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换。"`。
- `upload_tool_files` 继承 `filing_files`，包含同一文案。
- `test_upload_format_contract.py:293-294`：断言 `".json 仅是 Docling JSON 候选"` 和 `"不代表任意 JSON 内容可转换"` 在 `filing_text` 和 `tool_text` 中。
- `test_arg_parsing.py:427-428`：CLI help 断言同源片段。
- `test_fins_ingestion_tools.py:917-918`：LLM schema 断言同源片段。

**闭环确认**。

### A5：无关格式化 churn → FIXED

**裁决要求**：恢复 `upload_batch.py` 与既有测试中不承载 Slice 2 语义的纯 Black 重排。

**验证**：
- 原始 diff `upload_batch.py`：96 deletions（大量格式化 churn：regex 换行、`_MATERIAL_ROUTING_TABLE` 格式化等）。
- 修复后 diff `upload_batch.py`：23 deletions，仅包含语义变更：`FINS_UPLOAD_FILE_SUFFIXES` 删除（19 行）、import 新增、`__all__` 删除、`_discover_source_files` 中 suffix 检查替换（2 行变化）。
- 原始 diff `test_upload_batch.py` 和 `test_arg_parsing.py` 有大量 Black 格式化 churn；修复后仅保留新增测试的 diff。
- 源码 audit 测试 `test_batch_consumes_format_owner_without_legacy_allowlist` 增加了 `# Governance audit` 注释说明其治理目的。

**闭环确认**。

## 新增 regression 检查

### R1：`FinsUploadUsageFailure.__post_init__` 对既有路径的影响

新增的 `__post_init__` 校验 `code` 类型、`message` 非空、`message` ≤240。对既有 `fins_upload_usage_failure()` 路径：
- 所有 `_USAGE_MESSAGES` 值均为固定中文文案，长度 ≤240。
- 文件相关 code 的 `{file_name}` 由 `_admit_fins_upload_file_basename` 保证为安全 basename，总长度 ≤240。
- 无 regression。

### R2：`_raise_upload_format_usage` 与 `FinsUploadUsageFailure` 的集成

`_raise_upload_format_usage` 构造 `FinsUploadUsageFailure(code=error.kind, message=str(error))`。`str(error)` 由 `_bounded_format_failure_message` 保证 ≤240。`__post_init__` 验证通过。无 regression。

### R3：material CLI `FinsUploadFormatError` 异常流

material CLI 的 `_validated_upload_files` 抛出 `FinsUploadFormatError` → `run_fins_direct_command` 的 `except FinsUploadFormatError` 捕获 → `render_cli_error(f"dayu-cli {args.command_name}: {exc}")`。`str(exc)` 由格式 owner 保证 ≤240。`FinsUploadFormatError` 不继承 `FinsUploadUsageError`，catch 顺序正确。无 regression。

### R4：delete action + files 历史行为

Adjudication 明确 deferred。diff 中未修改 delete + files 行为。`_UPLOAD_ACTION_DELETE and not request.files` 检查保持不变。无越权修改。

## Verdict

**PASS**

0 blocking findings。5 个 accepted findings（A1-A5）全部正确闭环。无新 regression。delete + files 历史行为未被越权修改。格式化 churn 已清理。
