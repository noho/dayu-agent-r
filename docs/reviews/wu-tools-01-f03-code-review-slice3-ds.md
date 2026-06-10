# Code Review — WU-TOOLS-01-F03 Slice 3

## Scope

- Mode: current changes
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-review-slice3-ds.md
- Included scope:
  - `utils/smoke_web_ci.py`
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_smoke_web_ci.py`
  - `tests/tools/web/test_diagnose_web_access.py`
  - `docs/reviews/wu-tools-01-f03-implementation-slice3-codex.md`
- Excluded scope: unrelated history, production Web tools (`dayu/tools/web/`), Host/Engine/Service 层
- Parallel review coverage: 无（本次单 reviewer 全程走读）

## Verification Results

| 验证命令 | 结果 |
|---|---|
| `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | 30 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无输出 |

## 7 项 Challenge Point 逐条审查

### Challenge 1: Local HTTP Server opt-in / 127.0.0.1 / --allow-private-network-url / 默认 skip Playwright

**结论: 通过。**

证据链：

- `main()` (smoke_web_ci.py:2039): `opted_in = options.run_live or os.environ.get(_ENV_OPT_IN) == _ENV_OPT_IN_VALUE`，未 opt-in 时只写 skipped summary，不启动 server、不调用 diagnostics runner。
- `_running_local_fixture_server()` (smoke_web_ci.py:588): `http.server.ThreadingHTTPServer((_LOCAL_FIXTURE_HOST, 0), ...)`，其中 `_LOCAL_FIXTURE_HOST = "127.0.0.1"` (line 48)。port=0 使用随机可用端口。
- `_run_local_cases()` (smoke_web_ci.py:1783): `allow_private_network_url=True` 传入 `_diagnostic_command()`。
- `_diagnostic_command()` (smoke_web_ci.py:1753-1756): `if allow_private_network_url: command.append("--allow-private-network-url")` 且 `if not options.include_playwright: command.append("--skip-playwright")`。
- `include_playwright` 默认 `False`，由 `_options_from_namespace()` (line 2009): `include_playwright=bool(namespace.include_playwright)` 决定。
- 测试 `test_not_opted_in_writes_skipped_summary_and_does_not_call_runner` (test_smoke_web_ci.py:25) 验证未 opt-in 时 runner 不被调用。
- 测试 `test_opted_in_runs_local_html_and_pdf_cases` (test_smoke_web_ci.py:66) 验证 local diagnostics 命令包含 `--allow-private-network-url` 和 `--skip-playwright`。

### Challenge 2: /fixture.pdf 小而含稳定可抽取文本 / Content-Type / PDF_FETCH_MIN_CHARS

**结论: 通过。**

证据链：

- `_pdf_fixture_bytes()` (smoke_web_ci.py:419-461): 手工构造 PDF 1.4，包含 Helvetica Type1 字体、两行文本 `Dayu Web Smoke PDF` 与 `This PDF verifies Docling conversion.`。
- `do_GET()` (smoke_web_ci.py:492-497): `/fixture.pdf` 路径返回 `content_type=_LOCAL_PDF_CONTENT_TYPE` = `"application/pdf"` (line 52)。
- `PDF_FETCH_MIN_CHARS: Final[int] = 20` (line 76)，模块级 `Final` 常量，非魔法数字。
- 测试 `test_local_fixture_urls_and_pdf_fixture_are_stable` (test_smoke_web_ci.py:53) 验证 PDF bytes 包含预期文本、`PDF_FETCH_MIN_CHARS >= 20`。

### Challenge 3: PDF pass/fail/skip 只消费 diagnostics artifact facts

**结论: 通过。**

证据链：

- `_classify_pdf_loaded_artifact()` (smoke_web_ci.py:1202-1276) 所有判定字段均来自 `payload` 参数（diagnostics artifact），无 static inference。
  - content_type → `_raw_content_type(payload)` → 从 `requests_profile.result.response_headers` 或 `content_type` 字段读取
  - raw_length → `_raw_content_length(payload)` → 从 `requests_profile.result.content_length` 读取
  - fetch_length → `_fetch_content_length(payload)` → 从 `fetch_web_page_profile.content_length` 读取
  - evidence → `_docling_evidence(payload)` → 从 `docling_conversion_invocation_evidence` 读取
- 未修改 `dayu/tools/web/` 下任何生产代码。
- 未将 `extraction_source`、`renderer_source` 或其他 production-only 字段加入 LLM-facing success payload。
- 测试 `test_pdf_payload_failures_are_not_misclassified_as_pass` (test_smoke_web_ci.py:238) 验证所有 failure 分支均不误判为 pass。

### Challenge 4: Docling invocation evidence 完整性

**结论: 通过。**

证据链：

- `_classify_pdf_loaded_artifact()` (smoke_web_ci.py:1257-1275): 检查 `invoked=True`、`stream_name="page.pdf"`、`original_completed=True`，任一不满足 → `_BUCKET_PDF_DOCLING_INVOCATION_FAILURE` (exit code 1)。
- `_docling_init_skip()` (smoke_web_ci.py:950-967): 检查 `docling_runtime_initialization_error` 布尔字段 + `original_exception_type` 字符串匹配 `DoclingRuntimeInitializationError`/`ModuleNotFoundError`/`ImportError`。双重检查（布尔 + 异常类型名）保持与旧版 diagnostics artifact 兼容。
- `_classify_loaded_artifact()` 中的 skip 逻辑：
  - Line 1120: `child_returncode != 0 AND _docling_init_skip(payload) AND case_kind == _CASE_LOCAL_PDF` → PDF skip
  - Line 1129: `child_returncode != 0` (不满足上述) → 任何 case fail（包括 HTML）
  - Line 1151: `case_kind == _CASE_LOCAL_PDF AND _docling_init_skip(payload)` → PDF skip（子进程成功但 Docling init 问题）
- **关键**: `_docling_init_skip` 的 skip 分支（lines 1120, 1151）始终约束 `case_kind == _CASE_LOCAL_PDF`，HTML failure 不会被掩盖。`test_docling_skip_only_skips_pdf_and_does_not_hide_html_failure` (test_smoke_web_ci.py:309) 完整验证此行为。
- 测试覆盖：
  - `test_docling_wrapper_records_invoked_true_and_restores_callable` 验证 invoked/stream_name/completed 正常路径
  - `test_pdf_fetch_success_without_docling_invocation_keeps_failure_evidence_for_smoke` 验证 invoked=false 路径
  - `test_docling_runtime_initialization_exception_becomes_skip_observed_item` 验证 init error → skip
  - `test_generic_docling_conversion_exception_is_not_skip_observed_item` 验证普通异常不误归为 skip

### Challenge 5: Blocker artifact / stop condition

**结论: 通过。**

证据链：

- `_has_docling_invocation_blocker()` (smoke_web_ci.py:1844-1862): 只匹配 `case_kind == _CASE_LOCAL_PDF AND status == failed AND bucket == pdf_docling_invocation_failure`。
  - `_BUCKET_PDF_DOCLING_INVOCATION_FAILURE` 只在 `_classify_pdf_loaded_artifact()` 中 content_type 含 "pdf"、raw_length > 0、fetch_length >= PDF_FETCH_MIN_CHARS 但 Docling evidence 不成立时产生。
  - 不会匹配 `_BUCKET_DOCLING_INIT_SKIP`（skip 状态）、`_BUCKET_PDF_CONTENT_TYPE_FAILURE`、`_BUCKET_PDF_CONTENT_LENGTH_FAILURE` 或 `_BUCKET_DIAGNOSTIC_SCHEMA_GAP`。
- `_execute_smoke()` (smoke_web_ci.py:1924-1932): 如命中 blocker → 写 `_DOCLING_INVOCATION_BLOCKER_FILE` → `return` 提前退出，不执行 `_run_external_cases()`。external diagnostic-only 被正确停止。
- 测试 `test_pdf_invocation_blocker_writes_artifact_and_stops_external_cases` (test_smoke_web_ci.py:348) 验证：blocker 写入 → external 不运行 → external_cases 为空。

### Challenge 6: Diagnostics 新增 raw content_type/content_length

**结论: 通过。**

证据链：

- `_build_requests_profile()` (diagnose_web_access.py:1314-1317):
  - `"content_type": response.headers.get("Content-Type", "")` — response content-type header
  - `"content_length": len(response_bytes)` — `response.content` 原始字节长度
  - `"text_length": len(response_text)` — 保留 text 长度作为对照
- smoke 消费侧 (`smoke_web_ci.py`):
  - `_raw_content_type()` (line 870-889): 从 `response_headers` 做 case-insensitive key 匹配，fallback 到 `content_type` 字段。返回 `str`。
  - `_raw_content_length()` (line 892-910): 从 `result.content_length` 读取 `int|None`，fallback 到 `text_length`（向后兼容旧 artifact）。
  - `_fetch_content_length()` (line 913-928): 从 `fetch_web_page_profile.content_length` 读取 `int|None`。
- 所有字段读写均使用强类型 helper（`_string_field`、`_int_field`、`_bool_field`、`_nested_object`），无 `Any`/`object`/无类型签名扩散。
- 测试 `test_requests_profile_records_raw_response_byte_length` (test_diagnose_web_access.py:183) 验证 `content_length` 为 `len(response_bytes)`、`text_length` 为 `len(decoded_text)`，两者语义独立。
- 无反向依赖：diagnostics 脚本不 import Host/Engine/Service 内部模块；smoke 脚本只 import `dayu.contracts.json_value`。

### Challenge 7: README 触发判断

**结论: 成立，无需更新。**

证据链：

- `tests/README.md` line 143 已声明: `tests/tools/web/` 的 Web provider 测试必须 deterministic，通过 monkeypatch/fixture 替身控制，不做 live network 请求。
- 新增测试 `test_smoke_web_ci.py` 全部使用 synthetic/fake diagnostics payload 与 monkeypatch runner/server，符合 deterministic 约束。
- 新增测试 `test_diagnose_web_access.py` 新增的 `test_requests_profile_records_raw_response_byte_length` 使用 monkeypatch FakeSession/FakeResponse，不发起真实网络请求。
- 按 CLAUDE.md 触发规则: "先检查代码变更是否属于对应 README 的职责范围与目标读者；只有属于时才实际修改"。现有 README 已准确描述 `tests/tools/web/` 的 deterministic 约束，无需补充。

---

## Findings

### 1-未修复-低-`_raw_content_length` 回退到 `text_length` 对二进制内容语义不精确

- **入口/函数**: `smoke_web_ci.py:_raw_content_length()` (line 892-910)
- **文件(行号)**: utils/smoke_web_ci.py:909
- **输入场景**: diagnostics artifact 由旧版 `diagnose_web_access.py`（Slice 2 之前）生成，只包含 `text_length` 但不包含 `content_length`。
- **实际分支**: `_int_field(requests_result, "content_length")` 返回 `None` → 进入 fallback → `_int_field(requests_result, "text_length")`。
- **预期行为**: raw response bytes length 应该始终以 `len(response_bytes)` 为准。对 UTF-8 文本两者相等，但对二进制 PDF 或含多字节字符的响应，`len(response_text)` 可能不等于原始字节长度。
- **实际行为**: 当 `content_length` 缺失时，用 `text_length`（解码后字符串长度）代替 raw bytes length。对于 `text_length > 0` 但实际 raw bytes 可能更短或更长的内容，`raw_length` 检查 `<= 0` 的判定不会错误（因为 `text_length > 0` 同样通过），但语义上 `raw_length` 已不代表 raw bytes。
- **直接证据**: `smoke_web_ci.py:909` — `return _int_field(requests_result, "text_length")` 作为 `content_length` 的 fallback。
- **影响**: 仅影响旧版 diagnostics artifact 的向后兼容性。当前 Slice 3 的 diagnostics 始终同时写入 `content_length`（`len(response_bytes)`）和 `text_length`（`len(response_text)`），因此生产路径不受影响。风险窗口仅限于：操作者手动使用旧版 diagnostics 生成 artifact 后，再用新版 smoke 消费。
- **建议改法和验证点**: 可在 `_raw_content_length` 的 docstring 中说明该 fallback 仅用于向后兼容，`text_length` 不等于 raw bytes length。不需修改代码逻辑（因为 `<= 0` 检查对两者等效）。验证点：确认当前 `_build_requests_profile` 始终写入 `content_length` 字段。
- **修复风险（低）**: 仅文档注释变更。
- **严重程度（低）**: 不影响当前 slice 正确性，仅属于向后兼容语义精度问题。

### 2-未修复-低-PDF raw_length 为 0 或 None 的 failure 分支缺少显式测试覆盖

- **入口/函数**: `smoke_web_ci.py:_classify_pdf_loaded_artifact()` (line 1235-1244)
- **文件(行号)**: utils/smoke_web_ci.py:1235-1244
- **输入场景**: diagnostics artifact 中 `requests_profile.result.content_length` 为 0 或 `None`（例如 requests 层成功但响应体为空）。
- **实际分支**: `if raw_length is None or raw_length <= 0:` → `return _case_failure(bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE)`。
- **预期行为**: raw response bytes 为空或缺失时应判定为 PDF content length failure。当前代码分支正确。
- **实际行为**: 代码行为正确，但 `test_pdf_payload_failures_are_not_misclassified_as_pass` 测试中所有 case 的 `raw_length` 均 >= 128（来自 `_diagnostic_payload` helper 默认值），未覆盖 `raw_length=0` 或 `raw_length=None` 场景。
- **直接证据**: `test_smoke_web_ci.py:238-306` — `test_pdf_payload_failures_are_not_misclassified_as_pass` 的四个 case 均未设置 `raw_length=0`；`_diagnostic_payload` helper (line 579-639) 的 `raw_length` 默认值为 128。
- **影响**: 代码路径已存在且正确，但缺少回归保护。若未来重构意外改变 `_raw_content_length` 的返回值语义（例如返回 0 时误判为 None），可能导致空 PDF 响应被漏过。
- **建议改法和验证点**: 在 `test_pdf_payload_failures_are_not_misclassified_as_pass` 中增加一个 `raw_length=0` 的 case，断言 bucket 为 `pdf_content_length_failure`。
- **修复风险（低）**: 纯测试补充，不改变生产代码。
- **严重程度（低）**: 代码路径正确，仅测试覆盖缺口。

---

## Open Questions

无。

## Residual Risk

1. **真实 Docling runtime 版本的 PDF 文本抽取差异**：当前 PDF fixture 使用 Helvetica Type1 字体和简单 ASCII 文本流。在部分 Docling 版本或平台上，PDF 文本抽取仍可能因字体映射、编码解析差异而产生空或过短 markdown。这是设计上已预期的风险——计划明确要求：只要 Docling callable completed 且 fetch 成功返回，内容过短就是 local PDF fail，必须调整 fixture 或修正真实 bug，不得跳过 PDF route。

2. **`_DoclingInvocationWrapper` monkeypatch 的并发安全性**：当前 diagnostics 子进程内 Docling conversion 同步执行于 `asyncio.run()` 调用栈中，不存在并发风险。若未来 `_build_tool_fetch_profile` 改为异步并发调用，需重新评估 `_web_tools_module._docling_convert_to_markdown` 的 monkeypatch 线程安全性。

3. **外部 URL diagnostic-only 路径的 `child_returncode != 0` 分支**：`_classify_loaded_artifact` (line 1088) 对外部 URL + 非零 returncode 直接归为 diagnostic-only，不做 `_docling_init_skip` 检查。这是设计意图（外部 URL 只 diagnostic-only），但意味着即使外部 URL 的 diagnostics 子进程因 Docling 初始化失败而退出，也不会产生 skip 信号。当前实现正确，因为外部 URL 本不应依赖 Docling。

---

## 总体结论

**pass** — 30 tests passed, pyright 0 errors, git diff --check clean。

7 项 challenge point 逐条通过，2 项低严重度 finding（均为测试覆盖或向后兼容语义精度问题，不影响当前 slice 正确性）。未发现 blocking issue、架构违规、反向依赖、魔法数字扩散或生产 LLM-facing payload 变更。
