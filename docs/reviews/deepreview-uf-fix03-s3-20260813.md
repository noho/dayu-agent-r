# Deep review — UF-FIX03 S3 uncommitted changes

## Review metadata

- Baseline: `a65cec93`
- Scope: `git diff a65cec93` (7 files, +436/-13)
- Review date: 2026-08-13
- Reviewer: AgentMiMo
- Artifact path: `docs/reviews/deepreview-uf-fix03-s3-20260813.md`

## Predicate checklist

### 1) CLI generic unknown — operator log 有 traceback，普通 stderr 固定有界且无 raw exception/repr/绝对路径

**PASS**

`dayu/cli/commands/fins.py:218-226`：generic `except Exception` 不绑定 `exc`，使用 `_LOGGER.exception(...)` 写入完整 operator traceback，普通 stderr 固定为 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`。不拼接 `str(exc)`、`repr(exc)`、cause chain、绝对路径或第三方 traceback。已知 typed failure（`FinsDirectStreamProtocolError` 等）继续走各自的 typed projection 分支，不经过 generic handler。

`tests/cli/test_fins_commands.py` 的 `test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr` 断言：
- `captured.err` exact match 固定文案
- marker、`/absolute/path`、`Traceback`、`RuntimeError` 不在 stderr
- marker、`Traceback`、`RuntimeError` 在 `caplog.text`

`test_stream_failure_propagates_to_cli_error` 断言 raw stream exception `stream boom` 不在 stderr，走固定文案。

### 2) typed file label 位于第 9 detail 而 renderer cap=8 — 是否违反可行动公开 reason

**FINDING F1 — LOW**

`dayu/fins/ingestion_runtime.py:6372-6397` 构造 content failure detail ordering：

| position | label | 条件 |
|----------|-------|------|
| 0 | source kind | 始终 |
| 1 | status | 始终 |
| 2 | document | document_id 非空时（SEC filing 始终有） |
| 3 | requested files | 始终 |
| 4 | stored files | 始终 |
| 5 | failure kind | failure_reason 非空时 |
| 6 | failure code | failure_reason 非空时 |
| 7 | failure message | failure_reason 非空时 |
| 8 | retry hint | retry_hint 非空时（content failure 始终有） |
| 9 | file | file_label 非空时（content failure 始终有） |

`dayu/cli/output.py:65`：`_FINS_SUMMARY_MAX_ITEMS = 8`。`_summary_parts` 在 position 8 处截断。content failure 的 `file` label（canonical basename 如 `corrupt.docx`）始终位于 position 9，不出现在真实 CLI stderr。

测试 `test_direct_upload_filing_content_failure_is_typed_and_has_zero_publication` 断言 `details["file"] == file_name` 验证的是 raw result object（内部 detail tuple），不是 CLI 渲染输出。真实 CLI 用户只看到 `failure_kind`、`failure_code`、`failure message`，看不到哪个文件触发了失败。

S3 implementation artifact 已识别此限制并分类为"assigned to later work unit"。但 UF-FIX03 accepted plan 的公开 contract 要求"有界 typed reason"，`file` label 是 reason 的一部分却在 CLI 投影中丢失。用户要求"若违反必须列 finding，不得接受留待后续"。

**Severity**: LOW — typed result 内部携带完整信息，测试验证了 owner contract；CLI 显示层截断不影响数据正确性，但降低终端用户的可操作性。

**Root cause**: `_upload_result_details` 把 `file` 放在最后，`_summary_parts` 的 cap=8 没有对 content failure 的 `file` 做优先级提升。

**修复建议**: 提升 `file` label 的 detail priority（放在 `failure code` 之后、`failure message` 之前），或在 `_summary_parts` 中对 `file` label 做特殊保留。需要在 `dayu/cli/output.py` renderer 与 `dayu/fins/ingestion_runtime.py` detail ordering 之间做 owner 裁决。

### 3) positive direct upload regression — 直接证据证明不创建 Host Run/EventLog/Memory/Tool Trace/runtime/legacy job

**PASS**

`tests/fins/test_fins_ingestion_runtime.py` 的 `test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts`：

- 成功后从 Fins repository 读回 source meta、original blob 和 derived Docling asset → 证明 publication 成立
- `executor.operations == []` → 无 legacy job operation
- `tuple(jobs_dir.glob("*.json")) == ()` 和 `*.jsonl == ()` → 无 legacy job record
- `not paths.host_dir.exists()` → 无 Host directory
- `not paths.host_sqlite_path.exists()` → 无 Host SQLite（即无 Host Run/EventLog/Memory/Tool Trace durable fact）
- `not paths.artifact_root.exists()` → 无 Host artifact
- `not paths.runtime_lanes_db_path.exists()` → 无 runtime lane SQLite

这些是直接路径存在性断言，不是脆弱路径推断。只要 production 创建了任何 Host 或 legacy artifact，对应路径断言会立即失败。

### 4) success readback、empty、corrupt PDF/DOCX、mixed atomic zero publication 与 stored=0

**PASS**

- **success readback**: `test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts` 断言 `requested files=1`、`stored files=1`，并从 `source_repository`、`blob_repository`、`company_repository` 读回三重 publication。
- **empty**: parametrized `("empty.pdf", b"", frozenset(), "empty_input_file", ())` 断言 `requested=1`、`stored=0`、`failure kind=content`、`failure code=empty_input_file`。
- **corrupt PDF**: parametrized `("corrupt.pdf", b"corrupt PDF", frozenset({"corrupt.pdf"}), "docling_converter_execution", ("corrupt.pdf",))` 断言 typed failure、converter 被调用。
- **corrupt DOCX**: parametrized `("corrupt.docx", b"corrupt DOCX", frozenset({"corrupt.docx"}), "docling_converter_execution", ("corrupt.docx",))` 同上。
- **mixed atomic zero publication**: `test_direct_upload_filing_mixed_input_fails_fast_without_partial_publication` 断言 converter 顺序 `["valid.pdf", "corrupt.docx"]`、`requested=2`、`stored=0`、`_assert_direct_test_filing_was_not_published` 验证 company/source 无 publication。

所有失败路径统一断言 `stored files=0` 且 `_assert_direct_test_filing_was_not_published` 使用 `pytest.raises(FileNotFoundError)` 验证 source meta 和 company meta 均不存在。

### 5) README 是否准确且符合边界

**PASS**

- `README.md`：+2 行，只记录 requested/stored 语义、Docling 不重复计数、empty/corrupt/mixed 整批失败 stored=0、generic unknown 固定 stderr/log。不涉及 Host/Engine/Service 内部。
- `dayu/fins/README.md`：+4 段，记录 requested/stored owner、original-only count、non-ok stored zero、typed content failure、canonical label、pre-publication fail-fast 与 atomic publication contract。语义与代码一致。
- `tests/README.md`：+12 行，记录 focused command、success positive control 与 no Host/runtime/legacy artifact regression。与实际测试结构一致。

三个 README 的变更范围均在其各自职责边界内，未越界描述不属于本 slice 的内容。

### 6) frozen JSON/evidence 未改、未执行 UF-PF03

**PASS**

- `git diff a65cec93` 不包含 `docs/cli_ci_scenarios.json` 或 `docs/cli_ci_oracles.json`。
- SHA-256 验证：
  - `docs/cli_ci_scenarios.json`: `a357e5a1...` ✓
  - `docs/cli_ci_oracles.json`: `88b04ca4...` ✓
- Implementation artifact 明确声明"未运行 UF-PF03、未修改 frozen evidence"。

### 7) tests/pyright/coverage

**PASS**

- S3 focused: `363 passed`（已验证）
- pyright: `0 errors, 0 warnings, 0 informations`（已验证）
- Implementation artifact 报告 S1+S2+S3 focused: `468 passed`，total coverage `88%`
- `cn_pipeline.py` 69% 为既有文件，S3 未修改该 production file
- Broader test 的 `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 失败为 baseline fixture 问题，非 S3 引入

## Findings summary

| ID | Severity | File:Line | Description | Root cause | Fix suggestion |
|----|----------|-----------|-------------|------------|----------------|
| F1 | LOW | `dayu/fins/ingestion_runtime.py:6396` + `dayu/cli/output.py:506` | content failure 的 `file` label 位于 detail position 9，renderer cap=8 截断，真实 CLI stderr 不显示触发失败的文件名 | `_upload_result_details` 把 `file` 放在最后；`_summary_parts` 对所有 detail 等权截断 | 提升 `file` label 的 detail priority 或在 renderer 中对 content failure 的 `file` 做特殊保留；需 owner 裁决 |

## Verdict

**PASS (with one LOW residual finding)**

S3 未提交改动正确实现了 CLI unknown boundary fix、direct no-artifact regression guard 与 documentation sync。所有 7 个检查点通过直接代码和测试证据验证。F1（file label 截断）为 LOW severity 展示层限制，不影响数据正确性或测试 contract，已被 implementation artifact 正确识别并路由。
