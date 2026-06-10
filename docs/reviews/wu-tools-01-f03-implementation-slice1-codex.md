# WU-TOOLS-01-F03 Slice 1 Implementation Artifact - AgentCodex

## Changed Files

- `utils/diagnose_web_access.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`

## Implementation Summary

- 在 diagnostics payload 增加 `diagnostic_schema_version` / `diagnostic_schema_revision`，并保持既有 `schema_version` 不变。
- 在 current `fetch_web_page` callable 诊断作用域内，对 `dayu.tools.web.web_tools._docling_convert_to_markdown` 安装窄 wrapper instrumentation：
  - wrapper 只在 `_build_tool_fetch_profile()` 本次调用内安装。
  - `finally` 恢复原始 callable。
  - wrapper 始终调用原始 callable，不替代生产行为，不吞异常。
  - 记录 `invoked`、`stream_name`、`raw_bytes_length`、`target_module`、`target_function`、`original_completed`、`original_exception_type`、`docling_runtime_initialization_error`、`diagnostic_url`。
- `docling_conversion_invocation_evidence` 只写入 diagnostics artifact：
  - fetch profile 内保留证据，便于单路径调试。
  - single diagnostic payload 顶层同步输出证据，便于后续 smoke 直接消费。
  - 未修改 production `fetch_web_page` LLM-facing success payload。
- `_build_batch_result_row()` 保留既有字段，并追加：
  - `observed_bucket`
  - `observed_failing_path`
  - `evidence_path`
  - `failure_url`
  - `diagnostic_action_hint`
  - `diagnostic_only_reason`
  - `diagnostic_schema_version`
  - `diagnostic_schema_revision`
  - Docling 证据摘要字段，供 summary helper 分类。
- `_build_batch_summary()` 追加：
  - `observed_buckets`
  - `observed_items`
  - `diagnostic_only_observed_items`
  - `skip_observed_items`
  - `diagnostic_action_hints`
  - `diagnostic_schema_version`
  - `diagnostic_schema_revision`
- 未新增 Playwright skipped + requests/fetch success 的 comparison bucket；保留现有 facts 判定路径。

## Tests / Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q`
  - Result: `19 passed in 0.39s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no whitespace errors.

## Docs Decision

- 已按 README 触发规则读取 `tests/README.md`。
- 本次只扩展既有 `tests/tools/web/` deterministic diagnostics 测试，没有新增测试层级或改变测试运行方式；`tests/README.md` 已说明该目录必须通过 monkeypatch / fixture 替身控制、不做 live network。
- 用户当前 slice 明确禁止修改 README，且无真实 blocker，因此未修改 README、control doc、smoke wrapper 或其它生产代码。

## Residual Risks / Uncovered Areas

- Slice 1 只提供 diagnostics facts 与 Docling invocation evidence；pass/fail/skip/diagnostic-only 的最终 smoke exit code 仍留给后续 Slice 2。
- wrapper 证据证明 current callable 作用域内是否实际调用 Docling callable；它不证明 Docling 输出文本质量。
- 外部站点不稳定性、真实 Playwright 环境差异、provider availability 仍未在本 slice 关闭。

## Completion Status

Slice 1 implementation complete. 已停止在 implementation gate；未进入 review / fix / commit / push / PR。
