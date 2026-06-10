# WU-TOOLS-01-F03 Slice 3 Code Review Controller Adjudication

## 输入

- Implementation artifact: `docs/reviews/wu-tools-01-f03-implementation-slice3-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f03-code-review-slice3-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f03-code-review-slice3-ds.md`
- Controller validation:
  - `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` -> 30 passed
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> 0 errors
  - `git diff --check` -> passed

## 总体裁决

结论：`pass-with-fixes`。

Slice 3 的实现方向符合 plan：opt-in 后启动 `127.0.0.1` local HTTP server，提供 HTML/PDF fixture，local diagnostics 使用 `--allow-private-network-url`，默认 skip Playwright，PDF 判定消费 diagnostics artifact 中的 raw content-type/content-length、fetch content length 与 Docling invocation evidence，没有修改生产 Web tool LLM-facing payload。

但 review 发现两个测试覆盖缺口，均应在当前 fix gate 关闭，避免 PDF Docling route 的关键失败分支缺少回归信号。

## Required Fixes

1. 补充 `original_completed=False` 且非 Docling init/dependency error 的 PDF failure 测试。
   - 来源：MiMo Finding 1。
   - 要求：在 `tests/tools/web/test_smoke_web_ci.py` 的 PDF failure matrix 中增加 case，payload 满足 `docling_invoked=True`、`stream_name="page.pdf"`、`docling_completed=False`、`docling_init_error=False`，期望 bucket 为 `pdf_docling_invocation_failure`。
   - 理由：这是 Slice 3 的核心 Docling callable completion 证据之一，不能只由代码条件隐含覆盖。

2. 补充 local PDF raw response bytes 为空的 failure 测试。
   - 来源：DS Finding 2。
   - 要求：在 `tests/tools/web/test_smoke_web_ci.py` 中增加 `raw_length=0` case，期望 bucket 为 `pdf_content_length_failure`。
   - 理由：计划要求 PDF raw response bytes length 大于 0，当前代码分支正确但缺少显式回归保护。

## Accepted / Deferred

- `PDF_FETCH_MIN_CHARS` 为公有常量：accepted-low。该常量服务 smoke 判定和 tests，不属于 Web tool 公共契约；当前不要求重命名。
- `_raw_content_type` 的 `response_headers` fallback 隔离测试：accepted-low。当前 synthetic helper 已实际走 `response_headers` 路径，且 diagnostics 现在直接写 `content_type`。
- `_raw_content_length` fallback 到 `text_length` 的旧 artifact 语义精度：accepted-low。当前 Slice 3 diagnostics 已写入 raw bytes `content_length`，fallback 只影响旧 artifact；不要求为 F03 当前 gate 修改。

## Fix Gate 验证要求

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`

