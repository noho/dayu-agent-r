# wu-cli-download-01 Slice 2 review-fix implementation

## 1. Artifact state

| Item | Value |
|---|---|
| Gate | Gateflow Slice 2 code-review fix implementation |
| Work unit | `wu-cli-download-01` |
| Accepted amendment | commit `da27b92a03f74d9a3785e208b63d2d0b6f5c2ad3` |
| Branch | `codex/download-oracle` |
| Date | 2026-08-10 |
| Scope | Accepted Slice 2 base plan plus `wu-cli-download-01-slice2-plan-amendment-20260810-030216.md` |
| Completion | Implementation and validation complete; ready for controller's two independent code re-reviews |
| Commit / push / PR | Not performed |

## 2. Direct evidence and owner conclusion

The pre-edit amendment union produced `497 passed / 6 failed`. The six failures had exactly two causes:

1. Four CN workflow failures showed that `cn_download_filing_workflow.py` still emitted `pdf_download_failed` and `str(exc)` before the parent could observe the typed exception. This proved the child PDF/Docling catch was the real document-local failure owner.
2. Two UNKNOWN transport cases constructed abstract `httpx.HTTPError` with an unsupported `request=` keyword. The product retry loops were not involved; the test construction failed before the downloader received an exception.

The already-dirty CNINFO/HKEX retry loops, `_is_cancel_requested`, strict CN adapter, rebuild `missing_periods`, SEC auxiliary propagation, SEC filing-local catch, historical propagation, 6-K safe diagnostic, and optional HEAD behavior otherwise passed the affected union. They were not rewritten.

The implemented source of truth is therefore the public direct helper `cn_download_filing_workflow.project_cn_filing_failure(error)`. It owns the existing `(reason_code, reason_message)` row semantics and is directly consumed by the child PDF/Docling catches and the parent leak catch. No wrapper, second mapper, raw dict envelope, string parser, schema field, or downstream guess was added.

## 3. Changed files in this pass

### 3.1 Semantic implementation

- `dayu/fins/pipelines/cn_download_filing_workflow.py`
  - Added the only `project_cn_filing_failure(Exception) -> tuple[str, str]` definition.
  - Provider errors map to category-derived reason plus `safe_message`; `OSError` maps to `storage_failed` plus fixed safe text; all other exceptions map to `filing_execution_failed` plus fixed safe text.
  - PDF catch calls the helper exactly once and copies both returned fields into both `FILE_FAILED` and `FILING_FAILED`.
  - Docling catch uses the same helper; `CnDownloadCancelledError` remains an earlier re-raise branch.
  - Exported the helper as the direct same-layer public owner.
- `dayu/fins/pipelines/cn_download_workflow.py`
  - Directly imports and calls the child owner helper for exceptions escaping the child generator.
  - Deleted `_candidate_failure_facts` and removed the now-unused local provider-error import.
- `tests/fins/test_cn_download_workflow.py`
  - Added direct child-owner PDF/Docling tests for provider, path-bearing `OSError`, and raw execution exceptions.
  - Proves one helper call, identical two-field PDF pairs, one filing terminal, safe serialization, cancellation identity, parent same-source reuse, and later-candidate continuation.
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`
  - Corrected only the UNKNOWN test construction by creating `httpx.HTTPError(message)` without the unsupported `request=` keyword.

### 3.2 Validation-failure-driven maintenance inside the amended allowlist

- `dayu/fins/pipelines/cn_download_rebuild.py`
  - Removed one unused `CnDownloadCancelledError` import reported by Ruff; no behavior changed.
- Ruff mechanically formatted the following already-dirty, amended-allowlist files after `ruff format --check` identified them:
  - `dayu/fins/downloaders/cninfo_downloader.py`
  - `dayu/fins/downloaders/hkexnews_downloader.py`
  - `dayu/fins/downloaders/sec_downloader.py`
  - `dayu/fins/pipelines/cn_download_filing_workflow.py`
  - `dayu/fins/pipelines/cn_download_workflow.py`
  - `dayu/fins/pipelines/sec_download_filing_workflow.py`
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `tests/fins/test_cn_download_workflow.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/fins/test_hkexnews_downloader.py`
  - `tests/fins/test_sec_downloader.py`
  - `tests/fins/test_sec_pipeline_download.py`
  - `tests/fins/test_sec_pipeline_download_stream.py`

No frozen production/test file was edited for review-fix semantics. No README, registry, Oracle, controller task, real-observation artifact, CLI execution, provider call, commit, push, or PR mutation occurred.

## 4. Finding adjudication and implementation status

| Finding | Decision | Implementation / verification result |
|---|---|---|
| R01 | Accepted | Existing dirty defensive `discovered_count` assertion retained; count/terminal matrix passes. |
| R02 | Accepted, medium | Downloader typed mapping and operation propagation verified; child filing owner added; parent directly reuses it; adapter retains strict no-guess projection. |
| R03 | Rejected with reason | No `FinsErrorKind` expansion or runtime enum change. |
| R04 | Rejected | Direct-event validator remains the intentional stronger LLM-facing boundary. |
| R05 | Rejected | SEC UA single-composition and fail-closed invariant unchanged. |
| R06 | Accepted, medium | Rebuild producer emits `missing_periods`; strict consumer verified; no fallback restored. |
| R07 | Accepted | Zero-candidate override and defensive invalid-combination tests pass. |
| R08 | Rejected | Stable safe message plus fine category retained. |
| R09 | Rejected | No storage docstring/code scope added. |
| C01 | Accepted, medium | Existing dirty SEC propagation/safe logs verified; provider failures are not silently converted to empty/business evidence. |
| Stop-review MiMo F01-F03 | Resolved | Existing retry/cancel/SEC filing implementations were verified rather than rewritten. |
| Stop-review DS F01-F03 | Resolved | Per-owner status respected; CN/HK 4xx policy unchanged; PDF pair is produced by one helper call. |

## 5. Tests and validation

### 5.1 Test commands

| Command | Exact result |
|---|---|
| Pre-edit amendment union | `497 passed, 6 failed, 3 warnings` in `10.30s`; all six failures classified above. |
| `pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py -q` | `187 passed in 1.25s`. |
| Amendment union after implementation | `513 passed, 3 warnings in 10.26s`. |
| Same amendment union under final statement-coverage run | `513 passed, 3 warnings in 12.08s`. |

The three warnings are upstream `edgar` deprecation warnings for legacy HTML modules; no Slice 2 assertion or behavior warning occurred.

### 5.2 Type, lint, format, compilation, and diff

| Command | Exact result |
|---|---|
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` (plus a non-failing pyright update notice). |
| `python -m ruff check <27 changed Python files>` | `All checks passed!` |
| `python -m ruff format --check <27 changed Python files>` | `27 files already formatted` |
| `python -m compileall dayu tests` | Exit `0`; all trees enumerated without compile error. |
| `git diff --check` | Exit `0`, no whitespace error. |

### 5.3 Per-production-file statement coverage

Coverage used one affected-union data set, followed by a separate `coverage report --include=<file> --fail-under=80` command for every review-fix production owner. Branch coverage was not substituted for the plan's statement-coverage threshold.

| Production file | Coverage |
|---|---:|
| `dayu/fins/download_contract.py` | 80.13% |
| `dayu/fins/direct_events.py` | 86.02% |
| `dayu/fins/downloaders/sec_downloader.py` | 91.54% |
| `dayu/fins/pipelines/sec_pipeline.py` | 86.78% |
| `dayu/fins/pipelines/cn_pipeline.py` | 80.82% |
| `dayu/fins/downloaders/cninfo_downloader.py` | 89.88% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 85.12% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 88.55% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 86.11% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 82.89% |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 90.13% |

All eleven individual `--fail-under=80` invocations exited `0`.

### 5.4 Static owner and safety scans

- `project_cn_filing_failure` has exactly one definition. Static results show exactly two child calls (PDF and Docling) and one direct parent call.
- `_candidate_failure_facts` and `_reason_code_from_exception` have zero matches in the CN filing/workflow boundary.
- CN filing/workflow has zero `reason_message=str(exc)` or operation-download `message=str(exc)` matches. The two remaining `message=str(exc)` locations in `cn_pipeline.py` are pre-existing upload operations, not the download adapter or this WU's terminal path.
- CN adapter status is strictly limited to `ok`/`cancelled`; rebuild producer contains `"missing_periods": []` and the adapter uses `_required_cn_text_list` without a rebuild fallback.
- SEC direct-owner tests verify browse/SC13/history operation propagation, three evidence-helper propagation to one filing FAILED row, 6-K `DOWNLOAD_FAILED` continuation, and metadata-only HEAD degradation.
- Added-production diff and current review-fix production scan have zero matches for `url=`, raw exception interpolation, `str(exc)` public projection, contact canaries, raw payload markers, traceback canaries, or absolute `/Users/...` paths.
- CLI/wait adapter scan has zero filesystem traversal/private storage import/raw result classification matches; both continue to project the typed public object.
- Current modified code remains within the base Slice 2 plus amended allowlists. Gateflow artifacts are under `docs/gateflow/` only.

## 6. Invariants confirmed

- Provider/storage/execution provenance remains typed until its real operation or filing-local owner.
- PDF `FILE_FAILED` and `FILING_FAILED` receive the exact same `reason_code` and `reason_message` from one helper invocation.
- Cancellation never enters the failure helper and preserves exception identity.
- Filing-local failure produces exactly one filing terminal and does not prevent a later filing from completing.
- Counts, zero-candidate override, row order, bounded public rows, and exact omitted count remain unchanged and pass the affected union.
- Public/log output does not leak contact, URL, raw payload/exception, traceback, or absolute path.
- SEC UA composition/call count and optional HEAD behavior remain unchanged.
- CLI and wait adapter remain mechanical consumers; no file or log scan was added.

## 7. Residual risks and uncovered areas

| Item | Classification | Owner / destination |
|---|---|---|
| Real CLI and real-provider execution were intentionally prohibited in this gate. | `covered by later approved slice` | The base plan's approved DL-G real-observation gates; this review-fix performed no external call. |
| Three upstream `edgar` deprecation warnings remain. | `assigned to later work unit` | Dependency-maintenance owner; they are unrelated to Slice 2 download semantics and do not affect test outcomes. |
| Controlled process/cancellation and storage concurrency behavior are outside this Slice 2 follow-up. | `covered by later approved slice` | Base plan Slice 3 / Slice 4 and their owner tests. |

There is no unclassified residual risk, blocking owner question, schema requirement, or requested scope expansion.

## 8. Completion and next entry point

Slice 2 review-fix implementation is complete against accepted amendment `da27b92a`. The next Gateflow entry point is two independent code re-reviews of the complete dirty Slice 2 diff plus this artifact. No commit is authorized before controller adjudication and accepted re-review.

Artifact path: `docs/gateflow/wu-cli-download-01-slice2-review-fix-20260810-043450.md`
