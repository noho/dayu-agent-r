# WU-TOOLS-01-F03-R3 Fix Gate Artifact

## Scope

- Gate: fix
- Agent: Codex
- 修复范围: 只处理 Controller accepted findings。
- 参考 review:
  - `docs/reviews/wu-tools-01-f03-r3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f03-r3-code-review-ds.md`

## Fixed

### MiMo F1

`utils/smoke_web_ci.py` 中 `_execute_smoke()` 现在在 Docling invocation blocker 判断前运行 `_run_search_provider_cases()`。

- Docling blocker 分支仍会写 blocker artifact。
- Docling blocker 分支仍跳过 external URL cases。
- Search diagnostics 不依赖 Docling，结果会传入 `_summary_from_cases(search_cases=...)`。
- 如果 search assembly infra 失败，仍由现有 `hard_gate_cases = local_cases + search_cases` 语义进入 summary，并贡献 schema/infra exit code。

新增 deterministic 覆盖：

- `tests/tools/web/test_smoke_web_ci.py::test_pdf_invocation_blocker_runs_search_cases_and_stops_external_cases`
- 该测试用 monkeypatch 替换直接 assembly/search cases，构造 local PDF Docling invocation blocker，断言：
  - `external_cases == ()`
  - `len(summary.search_cases) == 4`
  - `len(summary.diagnostic_only) == 4`

### MiMo F2

`tests/tools/web/test_smoke_web_ci.py` 中 `discovered_configs` 从 `list[object]` 改为 `list[smoke.RuntimeConfig]`，保留测试对 Service discovery 输入 config 的精确类型记录。

### MiMo F4

`utils/smoke_web_ci.py` 中 `_tool_context()` 已移除 `cast(CancellationToken, ...)`，直接传入 `_OpenCancellationToken()`。

`python -m pyright dayu/ tests/ utils/` 通过，说明当前 `CancellationToken` protocol 与 `_OpenCancellationToken` 的结构化类型兼容，不需要保留 cast。

## Intentional No-Fix

### MiMo F3

`_classify_search_error_text()` 中中文错误文本 heuristic 不在本 gate 修改范围内。该逻辑是 secondary heuristic；主要分类仍来自 provider/key presence、HTTP status、requests exception 类型等更确定信号。Controller 未接受为必须修。

### MiMo F5

`_ASSEMBLY_PROVIDER_CONFIG` 的 module-level dict 不在本 gate 修改范围内。当前调用点对 assembly config 使用拷贝，search cases 使用 per-provider config，语义可接受。Controller 未接受为必须修。

## README Check

本次修改触及 `tests/` 与 `utils/smoke_web_ci.py`。`tests/README.md` 已记录 `tests/tools/web/` deterministic 约束、typed `search_cases` 边界，以及 smoke CLI 中 search diagnostics 默认运行。本次只是补充已有 blocker 分支覆盖，没有新增测试层级、运行方式或文档职责范围内的新约束，因此未修改 README。

## Verification

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - Result: `39 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - Result: `133 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported a newer version notice only.
- `source .venv/bin/activate && python utils/smoke_web_ci.py`
  - Result: exit `0`
  - Output dir: `workspace/output/web_smoke/web-smoke-20260610T065309Z`
  - Summary: `status=passed`, `local_cases=4`, `external_cases=2`, `search_cases=4`, `diagnostic_only=6`
- `git diff --check`
  - Result: passed

Warnings were dependency deprecation warnings from `edgar` and are unrelated to this fix gate.

## Residual Risk

- Search provider diagnostics in the live smoke still depend on current network/provider behavior, but pytest coverage for this gate remains deterministic through monkeypatch replacement.
- F3/F5 remain intentional no-fix per Controller decision.
