# Code Review

## Scope

- Mode: current changes
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-review-slice3-mimo.md
- Included scope:
  - `utils/smoke_web_ci.py` — local HTTP server、HTML/PDF fixture、PDF pass/fail/skip 判定、blocker artifact、local case runner
  - `utils/diagnose_web_access.py` — raw requests profile 新增 `content_type` / `content_length`
  - `tests/tools/web/test_smoke_web_ci.py` — Slice 3 local case 测试、PDF failure matrix、blocker 测试
  - `tests/tools/web/test_diagnose_web_access.py` — requests profile raw byte length 测试
  - `docs/reviews/wu-tools-01-f03-implementation-slice3-codex.md` — 实现 artifact
- Excluded scope: unrelated history, Host / Engine / Service 生产代码
- Parallel review coverage: 无

## Findings

### 1-未修复-中-original_completed=False 分支在 invoked=True 且 stream_name 正确时缺少测试覆盖

- **入口/函数**: `test_pdf_payload_failures_are_not_misclassified_as_pass` / `_classify_pdf_loaded_artifact`
- **文件(行号)**: `tests/tools/web/test_smoke_web_ci.py:238-293`、`utils/smoke_web_ci.py:1259-1263`
- **输入场景**: PDF diagnostics artifact 中 `invoked=True`、`stream_name="page.pdf"`、`original_completed=False`、`docling_runtime_initialization_error=False`
- **实际分支**: `_classify_pdf_loaded_artifact` 第 1259-1263 行条件 `not _bool_field(evidence, "invoked") or stream_name != _PDF_EXPECTED_STREAM_NAME or not _bool_field(evidence, "original_completed")` 为 `True`，进入 `pdf_docling_invocation_failure`
- **预期行为**: 测试应覆盖该分支，证明 Docling callable 被调用但未正常返回（非 init error）时 smoke 判为 failure
- **实际行为**: 当前 `test_pdf_payload_failures_are_not_misclassified_as_pass` 覆盖了 non-pdf-content-type、short-fetch-content、missing-docling-evidence、wrong-stream-name 四个子 case；`test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` 中的 pdf-skip case 使用 `docling_completed=False, docling_init_error=True` 走的是 init skip 路径，不覆盖 `original_completed=False` 且非 init error 的组合
- **直接证据**: `test_pdf_payload_failures_are_not_misclassified_as_pass` 的 `cases` 列表没有 `(invoked=True, stream_name="page.pdf", original_completed=False, docling_init_error=False)` 这个 tuple
- **影响**: 若 `original_completed` 条件在后续重构中被误删或误改，无测试回归信号
- **建议改法和验证点**: 在 `test_pdf_payload_failures_are_not_misclassified_as_pass` 的 `cases` 列表中新增一个 `"docling-not-completed"` 子 case，payload 使用 `docling_invoked=True, docling_completed=False, docling_init_error=False`，expected_bucket 为 `"pdf_docling_invocation_failure"`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-PDF_FETCH_MIN_CHARS 从私有常量变为公有导出

- **入口/函数**: `utils/smoke_web_ci.py` 模块级常量
- **文件(行号)**: `utils/smoke_web_ci.py:76`
- **输入场景**: 外部模块 import `smoke_web_ci.PDF_FETCH_MIN_CHARS`
- **实际分支**: `_PDF_FETCH_MIN_CHARS` 被重命名为 `PDF_FETCH_MIN_CHARS`（去掉前导下划线），成为模块公有符号
- **预期行为**: CLAUDE.md 要求模块间依赖最小化；该常量语义上是 smoke 判定阈值，不是公共契约，但测试需要引用它
- **实际行为**: 公有导出是为了 `test_local_fixture_urls_and_pdf_fixture_are_stable` 和 `_diagnostic_payload` helper 能直接引用；这符合测试可见性需求，但扩大了模块公有面
- **直接证据**: `smoke_web_ci.py:76` 定义 `PDF_FETCH_MIN_CHARS: Final[int] = 20`，测试中 `smoke.PDF_FETCH_MIN_CHARS` 直接引用
- **影响**: 低——该常量语义稳定且受 `Final` 保护；但若未来有外部模块依赖此常量做业务判定，会造成 smoke 内部阈值与外部耦合
- **建议改法和验证点**: 当前做法可接受；建议在模块 docstring 或常量注释中明确说明"该常量仅供 smoke 判定和 smoke 测试使用，不属于 Web 工具公共契约"。不阻塞 merge
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-`_raw_content_type` 的 response_headers fallback 路径未被 smoke 测试直接覆盖

- **入口/函数**: `_raw_content_type`
- **文件(行号)**: `utils/smoke_web_access.py:883-889`（注：diagnose_web_access.py 中 `_build_requests_profile` 第 1314 行）、`utils/smoke_web_ci.py:883-889`
- **输入场景**: diagnostics artifact 中 `requests_profile.result` 没有 `content_type` 字段，但 `response_headers` 中有 `Content-Type`
- **实际分支**: `_raw_content_type` 先检查 `response_headers` 中的 key，再 fallback 到 `_string_field(requests_result, "content_type")`
- **预期行为**: 两条路径都应被测试覆盖
- **实际行为**: smoke 测试的 `_diagnostic_payload` helper 在 `requests_profile.result` 中同时设置了 `response_headers.Content-Type` 和 `content_type` 字段；`test_requests_profile_records_raw_response_byte_length` 验证了 `_build_requests_profile` 同时写入这两个字段。因此 `response_headers` 路径在实际 `_build_requests_profile` 中被写入，但 smoke 判定测试只验证了最终结果，没有隔离测试"只有 response_headers、没有 content_type 字段"的 fallback 路径
- **直接证据**: `_diagnostic_payload` helper 第 621 行设置 `"response_headers": {"Content-Type": content_type}`，第 622 行设置 `"content_type"` 为不存在的字段——实际 helper 没有设置顶层 `content_type`，只设置了 `response_headers`
- **影响**: 低——`_build_requests_profile` 总是同时写入两个字段，fallback 路径是防御性代码；但作为 diagnostics artifact schema 的消费者，应验证 fallback 语义
- **建议改法和验证点**: 可选——在 smoke 测试中新增一个 synthetic payload 只设置 `response_headers.Content-Type` 不设置 `content_type`，验证 `_raw_content_type` 仍能正确读取。不阻塞 merge
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

1. **未执行真实 opt-in smoke**: 实现 artifact 明确说明"未额外执行真实 `DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`"。真实 PDF smoke 在不同 Docling runtime 版本下仍可能出现可抽取文本过短；该场景应按 local PDF failure 暴露。本轮 review 验证了 deterministic 测试、pyright 和 diff check，但未验证真实 Docling 路径。
2. **PDF fixture 文本可抽取性**: `_pdf_fixture_bytes()` 使用 Type1 Helvetica 字体和标准 PDF text operator；该 fixture 在主流 PDF 解析器中应稳定可抽取，但 Docling 特定版本的 markdown 后处理（如添加换行、空白折叠）可能导致实际 `content_length` 与预期不同。`PDF_FETCH_MIN_CHARS=20` 提供了足够余量（两行文本合计约 60 字符），但未在测试中验证 Docling 实际输出。
3. **blocker artifact 只覆盖 `_BUCKET_PDF_DOCLING_INVOCATION_FAILURE`**: 若未来新增其它需要 blocker 的 bucket，`_has_docling_invocation_blocker` 不会自动覆盖。当前设计正确——blocker 语义严格限定为"fetch 成功但无法证明 Docling callable invocation"。

## Verification Results

| 命令 | 结果 |
|------|------|
| `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | 30 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无输出 |

## Plan Slice 3 Challenge Points Checklist

1. **local HTTP server opt-in**: `_running_local_fixture_server` 绑定 `127.0.0.1` 随机端口；只在 `_execute_smoke` → `_run_local_cases` 中调用，需 opt-in；diagnostics 命令显式传 `--allow-private-network-url`；默认 `--skip-playwright`。✓
2. **/fixture.pdf**: PDF 包含 `Dayu Web Smoke PDF` 和 `This PDF verifies Docling conversion.` 稳定文本；Content-Type `application/pdf`；`PDF_FETCH_MIN_CHARS = 20` 常量化。✓
3. **PDF pass/fail/skip 只消费 diagnostics artifact facts**: `_classify_pdf_loaded_artifact` 从 artifact 读取 content_type、content_length、Docling evidence；不使用 static inference；不修改生产 LLM-facing payload。✓
4. **Docling invocation evidence**: 检查 `invoked=True`、`stream_name="page.pdf"`、`original_completed=True`；缺 evidence 走 schema gap；stream 错、content 短、非 PDF 走 fail；dependency/init evidence 只 skip PDF 不掩盖 HTML failure。✓（但 `original_completed=False` 分支缺少独立测试，见 Finding 1）
5. **blocker artifact/stop condition**: 只用于 `_BUCKET_PDF_DOCLING_INVOCATION_FAILURE`；不误伤 dependency/init skip；停止 external diagnostic-only。✓
6. **diagnostics 新增 raw content_type/content_length**: 语义正确（raw bytes 长度 vs decoded text 长度）；测试覆盖 `test_requests_profile_records_raw_response_byte_length`；无反向依赖/Any/object/无类型签名/魔法数字扩散。✓
7. **README 触发判断**: 触及 `tests/`；现有 `tests/README.md` 已声明 `tests/tools/web/` 必须 deterministic；新增测试仍为 deterministic synthetic/fake diagnostics；不更新 README 的判断成立。✓
