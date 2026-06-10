# WU-TOOLS-01-F03 Slice 3 Fix - AgentCodex

## 修复点

- 在 `tests/tools/web/test_smoke_web_ci.py` 的 PDF failure matrix 中补充 `empty-raw-response-bytes` case：`raw_length=0`、`fetch_length=PDF_FETCH_MIN_CHARS`，期望 bucket 为 `pdf_content_length_failure`。
- 在同一 matrix 中补充 `docling-invocation-not-completed` case：`docling_invoked=True`、`stream_name="page.pdf"`、`docling_completed=False`、`docling_init_error=False`，期望 bucket 为 `pdf_docling_invocation_failure`。

本次未修改 `dayu/tools/web`，未修改生产行为，未修改 smoke / diagnose helper。

## 验证命令与结果

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
```

结果：`30 passed in 0.36s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## 未处理的 accepted-low 项

- `PDF_FETCH_MIN_CHARS` 为公有常量：维持 accepted-low，不处理。
- `_raw_content_type` 的 `response_headers` fallback 隔离测试：维持 accepted-low，不处理。
- `_raw_content_length` fallback 到 `text_length` 的旧 artifact 语义精度：维持 accepted-low，不处理。
