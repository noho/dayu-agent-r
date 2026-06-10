# WU-TOOLS-01-F03 Slice 3 Implementation - AgentCodex

## 范围

- 实现 `utils/smoke_web_ci.py` 的显式 opt-in local live smoke：
  - 启动 `127.0.0.1` 本地 HTTP server。
  - 提供 `/index.html` 与 `/fixture.pdf`。
  - local diagnostics 命令显式传入 `--allow-private-network-url`。
  - 默认继续传入 `--skip-playwright`，除非 operator 显式 `--include-playwright`。
- PDF fixture 响应 `Content-Type: application/pdf`，PDF bytes 包含稳定文本：
  - `Dayu Web Smoke PDF`
  - `This PDF verifies Docling conversion.`
- 定义 `PDF_FETCH_MIN_CHARS = 20`，PDF local gate 使用该常量判断 `fetch_web_page` 内容长度。
- PDF local gate 继续只消费 diagnostics artifact：
  - raw requests sampled/ok。
  - response content-type 包含 PDF。
  - raw response content length 大于 0。
  - fetch sampled/ok。
  - fetch content length 至少 `PDF_FETCH_MIN_CHARS`。
  - `docling_conversion_invocation_evidence.invoked=True`。
  - `stream_name="page.pdf"`。
  - `original_completed=True`。
- 若 local PDF fetch 成功但 Docling invocation evidence 不成立，smoke 写入
  `output_dir/blockers/local-pdf-docling-invocation-blocker.md` 并停止后续 external diagnostic-only case。
- 强化 `utils/diagnose_web_access.py` 的 raw requests profile，追加 `content_type` 与基于 `response.content` 的 `content_length`。
- 未修改 `dayu/tools/web` 生产行为，未修改生产 Web tool LLM-facing success payload。

## 测试

- 更新 `tests/tools/web/test_smoke_web_ci.py`：
  - local fixture URL 与 PDF bytes 稳定性。
  - opt-in 后运行 local HTML/PDF cases。
  - local diagnostics 命令包含 `--allow-private-network-url`。
  - HTML/PDF synthetic payload pass/fail/skip。
  - PDF 缺 evidence、非 PDF content-type、fetch 内容过短、stream name 错误均 fail。
  - Docling dependency/init evidence 只 skip PDF，不掩盖 HTML failure。
  - PDF invocation evidence blocker 会写 artifact，并停止 external case。
  - external diagnostic-only 不覆盖 local pass。
- 更新 `tests/tools/web/test_diagnose_web_access.py`：
  - raw requests profile 记录 response bytes 长度。

## 验证结果

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - 通过：`30 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过：无输出。

## README 判断

- 本次修改触及 `tests/`，已检查 `tests/README.md`。
- 现有 README 已声明 `tests/tools/web/` 必须 deterministic，搜索 provider、requests 主路径和 Playwright fallback 通过 monkeypatch / fixture 替身控制，不做 live network 请求。
- 新增测试仍为 deterministic synthetic/fake diagnostics，不要求真实 live Docling，也不改变默认 pytest 层级职责，因此不更新 `tests/README.md`。

## 残余风险

- 本轮按指定验证命令执行 deterministic 测试、pyright 与 diff check；未额外执行真实 `DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`。
- 真实 opt-in PDF smoke 在不同 Docling runtime 版本下仍可能出现可抽取文本过短；该场景应按 local PDF failure 暴露，不能降级为 static inference。
- 若真实 fetch 对 local PDF 成功但 diagnostics wrapper 无法证明 Docling callable invocation，当前 smoke 会以 `pdf_docling_invocation_failure` fail，并写 blocker artifact；不得通过修改生产 payload 绕过。
