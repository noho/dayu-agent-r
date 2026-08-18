# Deep re-review — UF-FIX03 S3 uncommitted changes (post-fix)

## Review metadata

- Baseline: `a65cec93`
- Scope: `git diff a65cec93` (8 files, +692/-30)
- Review date: 2026-08-13
- Reviewer: AgentMiMo (re-review)
- Input artifacts:
  - `docs/reviews/deepreview-uf-fix03-s3-20260813.md` (first review)
  - `docs/reviews/deepreview-uf-fix03-s3-agentds-20260813.md` (first review)
  - `docs/gateflow/uf-fix03-s3-review-fix-20260813.md` (fix doc)
- Artifact path: `docs/reviews/deepreview-uf-fix03-s3-rereview-mimo-20260813.md`

## Fix verification matrix

### F1 — canonical file label 在 renderer 前 8 项内

**PASS**

`dayu/fins/ingestion_runtime.py:6372-6397` 修复后 `_upload_result_details` 排序：

| position | label | 条件 |
|----------|-------|------|
| 0 | source kind | 始终 |
| 1 | status | 始终 |
| 2 | requested files | 始终 |
| 3 | stored files | 始终 |
| 4 | failure kind | failure 存在时 |
| 5 | failure code | failure 存在时 |
| 6 | file | failure 存在且 file_label 非空时 |
| 7 | failure message | failure 存在时 |
| 8 | retry hint | failure 存在且 retry_hint 非空时 |
| 9 | document | document_id 非空时 |

content failure 的 `file` label 现在位于 position 6，在 `_FINS_SUMMARY_MAX_ITEMS = 8` 的 cap 之内。

测试验证：
- `test_upload_direct_details_consume_typed_failure_label_and_retry_hint` 断言完整 10 项顺序 tuple 与 `[:8]` 前缀 tuple，确认 `file` 在 position 6。
- `test_real_cli_content_failure_has_bounded_stderr_and_zero_fresh_workspace_mutation` 参数化覆盖 `empty.pdf`、`corrupt.pdf`、`corrupt.docx`，逐项断言 `file="{file_name}"` 出现在真实 CLI subprocess stderr。

排序完全由 `ingestion_runtime._upload_result_details` 机械投影，CLI renderer 无任何特例或重排逻辑。

### F2 — unknown `--log-file` 文案自足可行动

**PASS**

`dayu/cli/commands/fins.py:99-101`：常量 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE` 改为 `"命令执行失败，请使用 --log-file PATH 重试并查看日志"`。

`dayu/cli/commands/fins.py:220-227`：generic `except Exception` 不绑定 `exc`，`_LOGGER.exception(...)` 写完整 operator traceback，stderr 使用常量。

测试验证：
- `test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr` 断言：
  - `captured.err == _UNKNOWN_DIRECT_FAILURE_STDERR`（exact match）
  - `_UNKNOWN_DIRECT_FAILURE_MARKER`、`/absolute/path`、`Traceback`、`RuntimeError` 不在 stderr
  - `caplog.text` 包含 marker、`Traceback`、`RuntimeError` 和 `Fins direct command failed; command=download`
- `test_stream_failure_propagates_to_cli_error` 断言 `stream boom` 不在 stderr，走固定文案。

README (`README.md:316`) 说明 `--log-file PATH` 用法，与代码一致。

### F3 — upload_filing 四状态 CLI requested/stored 护栏

**PASS**

`tests/cli/test_fins_commands.py:2299-2457`：`test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts` 参数化覆盖 `ok`/`deleted`/`skipped`/`failed` 四状态。

测试链路：
1. 构造 `FinsUploadResultSummary`（production typed summary owner）
2. 使用 `validate_fins_upload_filing_request(...)` 取得 typed request
3. 构造最小 `_FinsIngestionExecutionContext`（仅填入取消 checker 等无关字段）
4. 调用 `ingestion_runtime._direct_upload_terminal_events(...)` 投影为真实 `FinsResultSummary`
5. 调用既有 `render_fins_direct_event(...)` 渲染

每状态断言：
- `requested_files="{count}"` 在正确 stream
- `stored_files="{count}"` 在正确 stream
- `uploaded_files` 不出现

未复制 validation、company-meta、status、error 或 count 逻辑。取消 checker 使用协议实现 `_NeverCancelledJobChecker`，仅填充无关字段。

### _upload_result_details 排序验证

**PASS**

排序完全由 `dayu/fins/ingestion_runtime.py::_upload_result_details(...)` 的 typed owner 机械投影。前 8 项为 counts → kind → code → file → message。无 renderer 特例。`dayu/cli/output.py` 的 `_FINS_SUMMARY_MAX_ITEMS = 8` 做通用截断，不感知 detail 语义。

### 测试复用 public validator / production terminal owner

**PASS**

- CLI 四状态测试使用 `validate_fins_upload_filing_request(...)` (public validator) 和 `_direct_upload_terminal_events(...)` (production terminal owner)。
- runtime 正控/失败测试使用 `_build_direct_upload_test_runtime` → `_inject_upload_runtime_converter` → `ProductionFinsUploadRunner` (production pipeline)。
- 无复制业务逻辑。

### no-artifact jobs path 真源

**PASS**

`test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts`：
```python
job_store = ingestion.job_store
assert isinstance(job_store, ingestion_runtime.FsFinsIngestionJobStore)
jobs_dir = job_store.root_dir
```
从 typed `FsFinsIngestionJobStore.root_dir` 派生，不再硬编码 `".dayu/fins_ingestion/jobs"`。

### frozen JSON / no-touch 验证

**PASS**

- `git diff a65cec93` 不包含 `docs/cli_ci_scenarios.json` 或 `docs/cli_ci_oracles.json`。
- SHA-256：
  - scenarios: `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb` ✓
  - oracles: `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8` ✓
- Host/Engine/runtime/config/Service production/storage 无相对基线改动。

### README frozen / no-touch

**PASS**

- `README.md`: +2 行，描述 requested/stored 语义、`--log-file PATH` 用法。在 README 职责边界内。
- `dayu/fins/README.md`: +4 段，描述 requested/stored owner、canonical file label、typed terminal projection。在 fins README 职责边界内。
- `tests/README.md`: +12 行，记录 focused command 集合与覆盖范围。在 tests README 职责边界内。

### Tests / pyright

**PASS**

- S3 focused: `368 passed, 3 warnings`（本次验证）
- pyright: `0 errors, 0 warnings, 0 informations`（本次验证）
- 未执行 UF-PF03，符合 plan 排除。

## Residual risks

- `cn_pipeline.py` coverage `69%`：该文件不是 S3 production diff，未用无关测试掩盖。需 controller 裁决。
- upload tool 既有 fixture 缺 fresh create `company_name`：assigned to later work unit。
- 真实 Docling 多平台 variance：assigned to later work unit UF-PF03。

## Verdict

**PASS**

F1、F2、F3 三项 findings 均已闭环修复并通过直接代码与测试证据验证。`_upload_result_details` 排序由 typed owner 机械投影，前 8 项包含 counts/kind/code/file/reason；测试复用 public validator 与 production terminal owner；no-artifact jobs path 从 typed `root_dir` 派生；README 与 frozen/no-touch 均合规。
