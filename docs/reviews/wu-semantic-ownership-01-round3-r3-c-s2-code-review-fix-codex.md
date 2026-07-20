# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Code Review Fix

## Scope

- Slice: S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets
- Fix owner: AgentCodex
- Input adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-controller-adjudication.md`
- Status: ready-for-rereview

## Fixed Findings

### S2-F01 CN commit failure test should assert storage absence

- Decision: fixed.
- File: `tests/fins/test_cn_download_workflow.py`
- Change: `test_cn_commit_failure_does_not_trigger_caller_rollback_or_success` now asserts `source_repository.get_source_meta("600519", "fil2024", SourceKind.FILING)` raises `FileNotFoundError` after storage-owned `commit_batch` failure.
- Production code changed: no.
- Semantic owner: the S2 caller-side commit-failure test matrix. The production owner remains storage `commit_batch` recovery; this fix only closes the CN test coverage asymmetry identified by MiMo.

## Verification

```bash
source .venv/bin/activate && pytest tests/fins/test_cn_download_workflow.py::test_cn_commit_failure_does_not_trigger_caller_rollback_or_success -q
```

Result: `1 passed`.

```bash
source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
```

Result: `194 passed, 3 warnings`.

```bash
source .venv/bin/activate && pytest tests/fins -q
```

Result: `519 passed, 1 skipped, 3 warnings`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: pass.

## Tool-Security Boundary

No tool-security behavior was implemented or changed by this fix. URL, TLS, redirect, SSRF, upload allowlist, remote byte-budget, prompt, and tool-schema policies remain deferred.

