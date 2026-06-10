# WU-TOOLS-01-F03 Slice 2 Implementation Artifact

## Gate

- Gate: implementation only
- Agent: AgentCodex
- Work unit: WU-TOOLS-01-F03 Web CI Smoke Generation
- Slice: Slice 2 Opt-in Smoke CLI and Summary Contract
- Branch: `wu-tools-01-f03-web-ci-smoke`

## Changed Files

- `utils/smoke_web_ci.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`

未创建 `utils/smoke_web_ci.sh`。

## Implementation Summary

- 新增 `utils/smoke_web_ci.py`，提供显式 opt-in Web smoke CLI。
- CLI 参数包含 `--run-live`、`--output-dir`、`--request-timeout`、`--tool-timeout-budget`、`--include-playwright`、`--external-url-file`、`--external-limit`、`--diagnostic-only-external`，并额外支持 `--run-label` 以便 deterministic 输出。
- 默认未设置 `DAYU_RUN_WEB_CI_SMOKE=1` 且未传 `--run-live` 时，只写 `skipped` summary，exit code 为 `0`，不调用 diagnostics runner。
- 输出 `summary.json` 与 `summary.md`，summary contract 包含 `status`、`exit_code`、`run_label`、`output_dir`、`failures`、`skips`、`diagnostic_only`、`local_cases`、`external_cases`。
- 实现 diagnostics artifact schema validation：
  - 校验 `diagnostic_schema_version` / `schema_version` 与 `diagnostic_schema_revision`。
  - local HTML 校验 `requests_profile.sampled`、`requests_profile.result.ok`、`fetch_web_page_profile.sampled`、`fetch_web_page_profile.ok`。
  - local PDF 额外校验 raw content-type、raw content length、fetch content length、`docling_conversion_invocation_evidence`。
- 实现子进程 / artifact 映射：
  - local schema gap -> `diagnostic_schema_gap`，exit code `2`。
  - local requests/fetch/PDF content-type/content-length/Docling invocation failure -> exit code `1`。
  - Docling init/dependency evidence -> PDF skip，exit code `0`，不掩盖其它 local failure。
  - child nonzero、artifact missing、JSON parse failure 按 local/external 语义分别处理。
  - external case 始终 diagnostic-only，不产生 exit code `1`。
- `--external-url-file` 默认不运行；提供后只按 diagnostic-only 处理，`--external-limit` 生效。
- 本 slice 未实现 Slice 3 的 local HTTP server live fixture。

## Tests Added

- 未 opt-in：验证 `status=skipped`，summary 路径稳定，diagnostics runner 不被调用。
- synthetic diagnostics artifact：覆盖 pass、fail、skip、diagnostic-only、diagnostic_schema_gap。
- local failure exit code `1`，schema gap exit code `2`。
- external failure diagnostic-only 不覆盖 local pass。
- external-limit 限制 runner 调用次数，summary JSON/MD 写入 `--output-dir`。

## Validation Results

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - Result: passed, `24 passed in 0.35s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `bash -n utils/smoke_web_ci.sh`
  - Not run; wrapper was not created.

## Docs Decision

- `tests/README.md` was checked because this slice adds `tests/tools/web/test_smoke_web_ci.py`.
- No README update was made. The existing `tests/tools/web/` rule already requires deterministic tests with no live network; the new tests follow that boundary and do not add a new test layer.
- Host / Engine README files were not checked for edits because this slice did not modify Host / Engine code or boundaries.
- `docs/host/issues-implementation-control.md` was not modified, per slice stop condition and allowed-file scope.

## Residual Risks / Uncovered Areas

- Covered by later approved slice: Slice 3 still needs the local loopback HTML/PDF fixture and real opt-in local diagnostics execution path.
- Covered by later approved slice: PDF fixture content extraction and real Docling route verification remain to be proven by live local fixture.
- Covered by later approved slice: optional external diagnostics can use the current external runner path, but broader corpus selection policy belongs to Slice 4.
- External site anti-bot, DNS, timeout, browser/storage-state and provider availability remain diagnostic-only by design; they are not local gate failures in this slice.

## Completion Status

Slice 2 implementation complete. Stopping at implementation artifact as requested; no review, fix loop, next slice, commit, push, or PR action performed.
