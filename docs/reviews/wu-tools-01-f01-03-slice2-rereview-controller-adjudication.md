# WU-TOOLS-01-F01-03 Slice 2 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 2: Migrate SEC Downloader And SEC Download Runtime`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice2-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice2-rereview-ds.md`
  - `docs/reviews/wu-tools-01-f01-03-slice2-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-03-slice2-code-review-controller-adjudication.md`

## Verdict

`pass`

AgentMiMo verdict: `fix-accepted`. AgentDS verdict: `pass`. Both reviewers confirmed all seven Controller-accepted Slice 2 findings are fixed, with 0 blocking findings and 0 new findings.

## Finding Closure

- `CTRL-S2-01`: fixed. SEC 6-K filtered rejected artifacts are counted in persisted summary `rejected_count` through `_is_rejected_filing_result(...)`; OLD workflow result status remains `skipped`.
- `CTRL-S2-02`: fixed. `StubDownloader.list_filing_files` docstring is now the first statement in the function body.
- `CTRL-S2-03`: fixed. Dead `_SpySourceRepository.download_files_stream` was removed.
- `CTRL-S2-04`: fixed. Stray `@pytest.mark.unit` decorators were removed; unknown marker warnings are gone.
- `CTRL-S2-05`: fixed. Unused `_maybe_await` and related imports were removed from `sec_pipeline.py`.
- `CTRL-S2-06`: fixed. `dayu/fins/pipelines/__init__.py` exists with a Chinese package overview docstring only.
- `CTRL-S2-07`: fixed. Persisted-summary adapter ownership is documented; `SecDownloadAdapter` still does not map NEW `rebuild_processed` to OLD `SecPipeline.download(rebuild=...)`; focused runtime test proves the request flag reaches the adapter.

## Controller Validation

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `113 passed, 3 warnings`
  - Remaining warnings are edgartools deprecation warnings from dependencies.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output.
- Targeted Slice 2 type scan:
  - Result: no `Any` or type `object` matches in touched Slice 2 production/test files.

## Residual Risk

- Live SEC network behavior remains explicit opt-in and outside deterministic tests.
- Deferred review items remain deferred: stream failure/overwrite coverage expansion, broad migrated helper de-duplication, and finer-grained SEC cancellation inside downloader wait/retry loops.

## Decision

Slice 2 is accepted locally and can be committed. Next implementation entry point is Slice 3: migrate CN/HK downloader and CN/HK download runtime.
