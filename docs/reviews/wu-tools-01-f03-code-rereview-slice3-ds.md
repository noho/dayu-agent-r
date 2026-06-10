# WU-TOOLS-01-F03 Slice 3 Fix Gate Re-Review — AgentDS

## Scope

- Mode: current changes (fix gate re-review)
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-rereview-slice3-ds.md
- Included scope: controller required fixes 1 & 2 in `tests/tools/web/test_smoke_web_ci.py`，关联 smoke classify 逻辑 `utils/smoke_web_ci.py:_classify_pdf_loaded_artifact`
- Excluded scope: Slice 3 整体实现 review（已在前序 MiMo / DS review 完成）；`utils/diagnose_web_access.py` 的 content_type/content_length 字段新增（属于 Slice 3 实现，非 fix 范围）

## Required Fix 1: `original_completed=False` 且非 init/dependency error → `pdf_docling_invocation_failure`

### 验证路径

测试 case `"docling-invocation-not-completed"` 位于 `test_pdf_payload_failures_are_not_misclassified_as_pass`：

| 字段 | 值 | 来源 |
|------|-----|------|
| `docling_invoked` | True | → `evidence["invoked"] = True` |
| `docling_completed` | False | → `evidence["original_completed"] = False` |
| `docling_init_error` | False | → `evidence["original_exception_type"] = ""` (非 DoclingRuntimeInitializationError) |
| `stream_name` | "page.pdf" | → `evidence["stream_name"] = "page.pdf"` |

### 分类器走读 (`_classify_pdf_loaded_artifact`, `utils/smoke_web_ci.py:1257-1275`)

```
content_type check ("application/pdf") → pass
raw_length check (512 > 0)            → pass
fetch_length check (20 >= 20)         → pass
evidence["invoked"] = True            → pass
stream_name == "page.pdf"             → pass
original_completed = False            → BLOCK → pdf_docling_invocation_failure
```

`_classify_child_result` 中的 `docling_runtime_initialization_error` skip 分支不会被命中，因为 `docling_init_error=False`。

结论：**Fix 1 正确实现。** `original_completed=False` 且非 init/dependency error（`original_exception_type=""`, `docling_runtime_initialization_error=False`）的 synthetic payload 正确命中 `pdf_docling_invocation_failure` bucket，assertion 为 `result.status == "failed"`。

## Required Fix 2: `raw_length=0` → `pdf_content_length_failure`

### 验证路径

测试 case `"empty-raw-response-bytes"` 位于 `test_pdf_payload_failures_are_not_misclassified_as_pass`：

| 字段 | 值 | 来源 |
|------|-----|------|
| `raw_length` | 0 | → `requests_profile["result"]["content_length"] = 0` |
| `fetch_length` | `PDF_FETCH_MIN_CHARS` (20) | → 非零，不干扰 raw_length 判定 |
| `content_type` | "application/pdf" | → 不干扰 |

### 分类器走读 (`_classify_pdf_loaded_artifact`, `utils/smoke_web_ci.py:1235-1245`)

```
content_type check ("application/pdf") → pass
_raw_content_length → content_length=0 → raw_length=0
raw_length <= 0 → True → BLOCK → pdf_content_length_failure
```

`_raw_content_length` (line 892-910) 优先读取 `requests_profile.result.content_length`，值为 0，满足 `<= 0` 条件。

结论：**Fix 2 正确实现。** `raw_length=0` 的 synthetic payload 正确命中 `pdf_content_length_failure` bucket，assertion 为 `result.status == "failed"`。

## 附加验证项

### 未触碰 `dayu/tools/web`

`git diff --name-only` 输出仅含：
- `tests/tools/web/test_diagnose_web_access.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `utils/diagnose_web_access.py`
- `utils/smoke_web_ci.py`

0 个文件位于 `dayu/tools/web/`。**通过。**

### 未改生产行为

Required fix 的两个 test case 仅新增在 `tests/tools/web/test_smoke_web_ci.py`，是纯测试补充。`utils/smoke_web_ci.py` 与 `utils/diagnose_web_access.py` 的变更为 Slice 3 实现主体，非 fix gate 引入。**通过。**

### 未引入新问题

- `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` → **30 passed in 0.35s**
- `python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → **通过（无输出）**

测试中 `_diagnostic_payload` 新增 `stream_name` 参数默认值为 `"page.pdf"`，对已有 test case 无影响（已有 case 均使用 `docling_invoked=False`，此时 `stream_name` 在 evidence 中写为 `""`）。**通过。**

### Accepted-low 项状态确认

- `PDF_FETCH_MIN_CHARS` 公有常量：未改动，维持 accepted-low。
- `_raw_content_type` 的 `response_headers` fallback 隔离测试：未改动，维持 accepted-low。
- `_raw_content_length` fallback 到 `text_length` 的旧 artifact 语义精度：未改动，维持 accepted-low。

以上三项在 fix 前后无变化。**通过。**

## Extra Coverage（非 Required，无副作用）

Codex fix 同时补充了 `wrong-stream-name` case（`stream_name="fixture.bin"`，期望 `pdf_docling_invocation_failure`），覆盖了 `stream_name != _PDF_EXPECTED_STREAM_NAME` 分支。该 case 不干扰 required fix 验证，属于正向覆盖增量。在 `_diagnostic_payload` helper 中新增 `stream_name` 参数是支持该 case 的必要基础设施，参数默认值 `"page.pdf"` 保证向后兼容。

## Open Questions

无。

## Residual Risk

- `test_pdf_payload_failures_are_not_misclassified_as_pass` 中 6 个 case 仅断言 `status == "failed"` 与 `bucket == expected_bucket`，未反断言（如确认不是其他 failure bucket），但 bucket 互斥由 upstream classify 逻辑保证，低风险。
- `raw_length=0` case 的 `_raw_content_length` 回退到 `text_length` 的路径（`content_length` 缺失时）已有 fallback 逻辑但无独立 test case，属于 accepted-low 项范围，当前 fix gate 不要求。

## Conclusion

**pass**

两个 required fix 均已正确实现：`original_completed=False` 且非 init/dependency error 命中 `pdf_docling_invocation_failure`，`raw_length=0` 命中 `pdf_content_length_failure`。未触碰 `dayu/tools/web`，未引入新问题，accepted-low 项保持 accepted-low。30 测试通过，pyright 零错误。
