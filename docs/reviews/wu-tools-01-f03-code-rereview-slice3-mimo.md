# WU-TOOLS-01-F03 Slice 3 Fix Gate Re-Review - AgentMiMo

## 输入

- Controller adjudication: `docs/reviews/wu-tools-01-f03-code-review-slice3-controller-adjudication.md`
- Codex fix: `docs/reviews/wu-tools-01-f03-fix-slice3-codex.md`
- 当前未提交 diff

## Required Fixes 核对

### 1. PDF failure matrix 新增 `original_completed=False` 且非 init/dependency error，expected bucket `pdf_docling_invocation_failure`

**验证通过。**

位置：`tests/tools/web/test_smoke_web_ci.py`，`test_pdf_payload_failures_are_not_misclassified_as_pass` 函数，第 273-287 行。

```python
(
    "docling-invocation-not-completed",
    _diagnostic_payload(
        url="http://127.0.0.1/fixture.pdf",
        content_type="application/pdf",
        raw_length=512,
        fetch_length=smoke.PDF_FETCH_MIN_CHARS,
        docling_invoked=True,
        docling_completed=False,
        docling_init_error=False,
        stream_name="page.pdf",
    ),
    "pdf_docling_invocation_failure",
),
```

- `docling_invoked=True`: 满足
- `docling_completed=False`: 满足（对应 `original_completed=False`）
- `docling_init_error=False`: 满足（非 init/dependency error）
- `stream_name="page.pdf"`: 满足
- expected bucket `pdf_docling_invocation_failure`: 满足

### 2. 新增 `raw_length=0`，expected bucket `pdf_content_length_failure`

**验证通过。**

位置：`tests/tools/web/test_smoke_web_ci.py`，`test_pdf_payload_failures_are_not_misclassified_as_pass` 函数，第 248-259 行。

```python
(
    "empty-raw-response-bytes",
    _diagnostic_payload(
        url="http://127.0.0.1/fixture.pdf",
        content_type="application/pdf",
        raw_length=0,
        fetch_length=smoke.PDF_FETCH_MIN_CHARS,
        docling_invoked=True,
        docling_completed=True,
    ),
    "pdf_content_length_failure",
),
```

- `raw_length=0`: 满足
- expected bucket `pdf_content_length_failure`: 满足

## 其他验证

### 未修改生产行为

**验证通过。**

- `dayu/tools/web` 目录未被修改（`git diff --name-only | grep "dayu/tools/web"` 返回 0）
- 修改的生产代码仅在 `utils/diagnose_web_access.py` 和 `utils/smoke_web_ci.py`，属于 `utils/` 目录下的脚本

### Accepted-Low 项保持

**验证通过。**

- `PDF_FETCH_MIN_CHARS` 改名为公有常量（`_PDF_FETCH_MIN_CHARS` -> `PDF_FETCH_MIN_CHARS`）：维持 accepted-low，不强制要求重命名
- `_raw_content_type` 的 `response_headers` fallback 隔离测试：未新增，维持 accepted-low
- `_raw_content_length` fallback 到 `text_length` 的旧 artifact 语义精度：未处理，维持 accepted-low

## 验证命令结果

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
# 结果：30 passed in 0.38s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 结果：0 errors, 0 warnings, 0 informations

git diff --check
# 结果：通过，无输出
```

## 结论

**pass**

两个 required fixes 均已正确补充：
1. PDF failure matrix 新增 `original_completed=False` 且非 init/dependency error 的 case，bucket 为 `pdf_docling_invocation_failure`
2. 新增 `raw_length=0` 的 case，bucket 为 `pdf_content_length_failure`

Fix 未触碰 `dayu/tools/web`，未引入新问题，accepted-low 项保持不变。测试全部通过，类型检查无错误。
