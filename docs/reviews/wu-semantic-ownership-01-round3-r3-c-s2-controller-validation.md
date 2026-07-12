# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
- Gate: controller validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-implementation-codex.md`
- Prerequisite accepted slice: R3-C S1 commit `6e9ad77e`

## File Scope

Changed production files are within the accepted S2 allowed set:

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`

Changed test/artifact files are within the accepted S2 allowed set:

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-implementation-codex.md`

No S3 Host/Service wait adapter files, README files, design docs, control docs, prompt files, or tool schema files were modified.

## Controller Validation Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
```

Result: `194 passed, 3 warnings`.

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate
pytest tests/fins -q
```

Result: `519 passed, 1 skipped, 3 warnings`.

```bash
git diff --check
```

Result: pass, no output.

## Contract Scans

```bash
rg -n "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path" dayu/fins/downloaders dayu/fins/pipelines tests/fins
```

Result: no matches.

```bash
rg -n '\bDownloadedReportAsset\b|\.pdf_path\b|pdf_path[[:space:]]*[:=]' dayu/fins tests --glob '*.py'
```

Result: only legal `DownloadedReportAsset` type/import/return/docstring references and constructor sites remain; no `.pdf_path`, `pdf_path:`, or `pdf_path=` matches remain.

```bash
rg -n 'DownloadedReportAsset[[:space:]]*\(' dayu/fins tests --glob '*.py'
```

Result: two production constructors and four test fixture constructors remain; controller spot-check confirms they use `pdf_bytes=`.

## Contract Checks

- Upload create/update/overwrite now enters one caller-owned batch for non-delete mutations; file read/validation/conversion remain outside the batch.
- Generic downloaded-document storage now keeps reset/source/blob/processed mutation inside one caller-owned batch.
- CN/HK network download, reusable blob reads, Docling conversion, and progress `yield`s happen outside the active batch; the storage commit helper contains no `await` or `yield`.
- CN/HK commit helpers use `commit_started` ownership handoff: before `commit_batch()` caller rollback is allowed; from `commit_batch()` call onward storage owns token lifecycle and caller does not rollback.
- `commit_cn_filing_source_document()` is documented and used as a stage-only helper inside the caller-owned batch; it does not begin, commit, or rollback a batch.
- `DownloadedReportAsset` owner now exposes `pdf_bytes: bytes`; CNInfo/HKEX downloaders removed `tempfile` and temp path handoff while leaving HTTP request, URL, redirect, TLS, retry, and `response.content` reading behavior unchanged.

## Tool-Security Scope Check

`git diff -G 'allowlist|symlink-safe|SSRF|byte-budget|tool schema|prompt|TLS|redirect' -- dayu/fins/downloaders dayu/fins/pipelines dayu/fins/ingestion_runtime.py tests/fins` produced no diff output.

A broad keyword scan still finds pre-existing redirect-related code in downloader modules and SEC downloader tests, but those lines are not changed by S2. Controller classifies this as existing HTTP behavior, not tool-security implementation.

S2 did not implement upload allowlists, file authority policy, URL/TLS/redirect/SSRF provenance, remote byte budgets, or LLM-facing security schema/prompt/tool schema changes.

## README Decision

Controller accepts the implementation artifact's README decision. `dayu/fins/README.md` and `tests/README.md` sync remains deferred until S1, S2, and S3 have all landed and passed slice review, per `R3-C-PF-09`.

## Controller Decision

Status: `ready-for-code-review`.

Next gate: AgentMiMo and AgentDS S2 code review. No commit is authorized before review/adjudication.
