# wu-cli-download-01 Slice 2 code-review follow-up plan amendment

## 1. Artifact state

| Item | Value |
|---|---|
| Gate | Gateflow Slice 2 code review -> plan amendment |
| Work unit | `wu-cli-download-01` |
| Baseline HEAD | `c6829400a5e37892464a614590062511554f9633` |
| Branch | `codex/download-oracle` |
| Date | 2026-08-10 |
| Inputs | 两份 code review、`docs/reviews/plan-review-20260810-031151.md`、`docs/reviews/plan-review-20260810-031203.md`、controller adjudication |
| Scope of this pass | Direct call-chain analysis and this amendment artifact only |
| Product/test changes in this pass | None |
| Next gate | 原两位 reviewer 独立 re-review；implementation remains paused |

The worktree already contains the reviewed Slice 2 implementation. This artifact does not reinterpret those changes as a clean baseline and does not authorize edits outside the amended allowlist below.

## 2. First-principles judgment

The accepted follow-up is necessary and correctly rated medium for R02, R06, and C01:

- R02 is not merely an imprecise `UNKNOWN` category. CN/HK operation failure provenance is destroyed before the adapter sees it: `run_cn_download_stream_impl` catches provider, storage, and execution exceptions, writes `message=str(exc)` into a JSON result with `status="failed"`, and `CnDownloadAdapter.download` then labels every such result as a retryable provider failure. The adapter cannot recover facts that the workflow erased.
- R06 is not only a missing test. `cn_pipeline._summary_from_pipeline_result` explicitly accepts an absent required field only for rebuild, so the consumer compensates for an incomplete producer contract. `rebuild_cn_download_artifacts` is the producer that omits `missing_periods`; it must always emit the field and the adapter fallback must be deleted.
- C01 is real. SEC fallback/auxiliary paths catch typed provider errors through their `RuntimeError` base, log URL or raw exception text, and return `None`, `[]`, or a business filter classification. A transport failure can therefore be observed as ticker-not-found, missing auxiliary files, SC13 direction rejection, or 6-K business rejection instead of a provider failure.

The rejected findings do not justify changes: R03 asks a coarse direct-event enum to duplicate the already precise public failure; R04 challenges an intentional stronger LLM-facing validator; R05 challenges the deliberate fail-closed single-composition UA invariant; R08 asks safe text to duplicate the retained fine reason category; R09 is contradicted by current protocol/wrapper/core docstrings.

## 3. Direct code evidence and owner call chains

### 3.1 CN/HK operation failure provenance

Normal operation call chain:

失败产生方向为：

`真实异常 owner -> run_cn_download_stream_impl async generator -> CnPipeline.download_stream async-for（无 catch） -> collect_cn_download_result_from_events async-for（无 catch） -> CnDownloadAdapter.download（无 catch/重分类） -> Fins runtime producer catch -> _download_public_failure_from_exception`

Direct evidence:

1. `dayu/fins/downloaders/cninfo_downloader.py` and `hkexnews_downloader.py` own `httpx` request/retry exhaustion, JSON/protocol validation, and PDF validation. They currently raise generic `RuntimeError`, frequently embedding `url` and `last_exc`; their HEAD warnings also log `url={url} error={exc}`.
2. `dayu/fins/pipelines/cn_download_workflow.py` catches exceptions from `resolve_company`, company publication, candidate discovery, rebuild, and cancellation checks. Its `_build_result(status="failed", reason_code=..., message=str(exc))` converts all operation-terminal exceptions to untyped JSON text.
3. `dayu/fins/pipelines/cn_pipeline.py::CnDownloadAdapter.download` sees only `status="failed"` and constructs `FinsDownloadProviderError(UNKNOWN, retryable=True)`, regardless of whether the original exception was provider transport, `OSError`, or execution.
4. `CnPipeline.download_stream` 只 `async for` 转发 workflow event，`collect_cn_download_result_from_events` 也只迭代直到 `PIPELINE_COMPLETED`；两处均没有 `try/except`。Python async-generator 异常会按上述链条原样越过两层。
5. `dayu/fins/ingestion_runtime.py::_download_public_failure_from_exception` already has the correct closed terminal mapping: `FinsDownloadProviderError -> provider/configuration`, `OSError -> storage`, all other exceptions -> execution. It needs the original typed exception, not another downstream parser.

Owner decision:

- Each CNINFO/HKEX downloader maps its own `httpx`/provider protocol failure at the point of occurrence to the shared closed `FinsDownloadProviderError` contract. Source-specific retry policy and safe messages remain private module helpers; no new common facade is introduced.
- `run_cn_download_stream_impl` 的 rebuild、company/discovery、outer operation 与 final cancel-check 四组 operation-terminal `except Exception` 不再构造 `status="failed"`。除 `CnDownloadCancelledError` 继续进入当前 cancelled 语义外，`FinsDownloadProviderError`、`OSError`、`ValueError`、`RuntimeError` 及其它 `Exception` 都原样抛出。
- `CnPipeline.download_stream` 和 `collect_cn_download_result_from_events` 明确不新增 catch/转换；它们只让异常越过 generator/collector 边界。
- `CnDownloadAdapter` removes the blanket `status="failed" -> provider UNKNOWN` conversion and does not catch/rebuild owner exceptions. Its strict projection accepts only the workflow terminal states explicitly supported by the current slice; an unexpected legacy/fake `status="failed"` mapping fails closed as `ValueError` and is never guessed to be provider transport.
- `_is_cancel_requested` 对 `CnDownloadCancelledError` 维持 cancelled；对 `FinsDownloadProviderError`、`OSError` 与其它异常均不字符串包装。前两者原样到 runtime 的 provider/storage 分类，其它原样到 execution 分类。
- No raw-dict failure envelope or string-to-enum parser is added. Such a schema would create a second failure truth source and retain the current provenance-loss boundary.

### 3.2 CN/HK single-document failures are a distinct owner

`cn_download_filing_workflow.py` catches PDF/conversion failures and emits a `FILING_FAILED` row so other selected documents may continue. That is document-outcome semantics, not the operation-terminal `status="failed"` path adjudicated in R02.

Therefore `cn_download_filing_workflow.py` is explicitly excluded from this amendment. The newly typed downloader exception has a fixed safe message when that filing workflow converts it to a row, so it does not leak URL/raw payload. In the in-scope `cn_download_workflow.py` per-candidate catch, provider errors use `safe_message`; `OSError` uses a fixed storage-safe reason; all other exceptions use a fixed execution-safe reason. No document row writes `str(exc)`. Adding a new per-row transport field would change the public row schema and still requires a separate amendment.

### 3.3 Rebuild `missing_periods`

Call chain:

`CnDownloadAdapter -> CnPipeline.download_stream(rebuild=True) -> run_cn_download_stream_impl -> rebuild_cn_download_artifacts -> _summary_from_pipeline_result`

Direct evidence:

- `rebuild_cn_download_artifacts` returns filters, filings, notes, warnings, and summary but no `missing_periods`.
- `_build_result` in the normal CN/HK workflow always emits `missing_periods`.
- `_summary_from_pipeline_result` contains a rebuild-only missing-key fallback.

Owner decision: local rebuild has no provider discovery, so its owner always emits `"missing_periods": []`. The adapter always uses `_required_cn_text_list`; missing or mistyped fields fail closed for normal and rebuild paths alike.

### 3.4 SEC auxiliary provider errors and unsafe logs

Call chains with direct semantic impact:

- Ticker map miss -> `_resolve_company_via_browse_edgar_ticker` -> `_http_get_bytes` / `fetch_submissions`. Typed provider failures are currently caught as `RuntimeError`, logged with raw exception text, and returned as `None`; the caller then reports ticker not found.
- SC13 direction -> `fetch_sc13_party_roles` -> `_http_get_bytes`. Network failure currently returns `None`; the direction evaluator may record a business rejection.
- Filing file discovery -> `_try_fetch_index_items`, `_try_fetch_index_header_documents`, `_try_fetch_primary_linked_html_files`. Provider failure currently returns `[]`; downstream 6-K/XBRL selection can treat unavailable evidence as `NO_MATCH` or another business rejection.
- Historical submissions -> `sec_pipeline._collect_filings` -> `fetch_json`. Provider failure is logged with the full history URL and raw exception, then skipped, reducing discovered filings.
- 6-K preview -> `sec_pipeline._filter_6k_filing` -> `classify_6k_remote_candidates` -> `fetch_file_bytes`. Provider failure is logged raw and converted to the existing `DOWNLOAD_FAILED` filing-failure category; the state transition is correct, only the diagnostic is unsafe.

逐 helper owner 裁决：

| Helper / call site | 当前误行为 | 修订后 owner 与结果 |
|---|---|---|
| `_resolve_company_via_browse_edgar_ticker` HTTP | typed error 被 catch 后 `None` | downloader 原样传播；company resolution operation-fatal |
| browse-edgar XML parse | `RuntimeError` 后 `None` | downloader 映射 `PROTOCOL/non-retryable` 并传播；operation-fatal |
| browse 命中后的 `fetch_submissions` | typed error 后 `continue` | downloader 原样传播；operation-fatal |
| `fetch_sc13_party_roles` | typed error 后 `None` | downloader 原样传播；SC13 direction collection operation-fatal |
| `_try_fetch_index_items` | typed error 后 `[]` | helper 原样传播到 `list_filing_files`，再到 `sec_download_filing_workflow`；当前 filing 唯一 FAILED row，后续 filing 继续 |
| `_try_fetch_index_header_documents` | typed error 后 `[]` | 同上；不得把 unavailable evidence 当空 evidence |
| `_try_fetch_primary_linked_html_files` | typed error 后 `[]` | 同上；不得把 unavailable evidence 当空 evidence |
| `_http_head` | typed error 后 `None` | 保持 metadata-only optional；只记 closed category/fixed safe event，不改变 disposition |
| historical submissions `fetch_json` | raw log 后 `continue` | `sec_pipeline` 原样传播；candidate collection operation-fatal |
| 6-K preview `_precheck_6k_filter` | raw log 后 `DOWNLOAD_FAILED` | 保留既有 per-filing `DOWNLOAD_FAILED -> FILING_FAILED`，只把日志改为 closed category/fixed safe text；后续 filing 继续 |

Owner decision:

- `SecDownloader` continues to own the already implemented `httpx -> FinsDownloadProviderError` mapping. Provider-response parse failures at an SEC parser boundary become non-retryable `PROTOCOL` errors with fixed safe text.
- 三个 file-evidence helper 必须传播 typed error，因为失败证据不能当空证据；但 `dayu/fins/pipelines/sec_download_filing_workflow.py` 是 blast-radius owner：它在 `list_filing_files` 抛 typed provider error 时直接发当前 filing 的唯一 `FILING_FAILED` row并 return，不 begin batch、不写 rejection/skip，ticker workflow继续下一 filing。
- Historical submissions、browse company 与 SC13 role 发生在 operation-level selection/resolution owner，仍为 operation-fatal。
- 6-K preview 已有正确的 per-filing FAILED state transition，不升级为 operation-fatal；只移除 raw exception 日志并记录 closed category/fixed text。
- Internal source URLs may remain in provider-private request descriptors. C01 changes logging and public failure semantics, not the internal HTTP request model.

## 4. Review adjudication to implementation mapping

| Finding | Decision | Planned action |
|---|---|---|
| R01 | Accepted, low | Remove the unreachable fallback but retain `discovered_count` as a defensive witness; an impossible non-positive value at the mixed-failure branch raises `AssertionError` instead of returning a silent fallback. |
| R02 | Accepted/upgraded, medium | Map CNINFO/HKEX failures at downloader owner; preserve provider/storage/execution exceptions through CN workflow; delete adapter blanket provider guess. |
| R03 | Rejected with reason | No enum/runtime change. Public nested failure remains the exact closed classification. |
| R04 | Rejected | No validator rename, merge, or weakening. |
| R05 | Rejected | No UA lifecycle change. `None` remains “do not change”; a different non-empty UA remains fail closed. |
| R06 | Accepted/upgraded, medium | Rebuild owner always emits required `missing_periods`; delete adapter missing-key fallback; add producer and strict-consumer tests. |
| R07 | Accepted, low | Explain zero-candidate `FAILED`/`CANCELLED` override at owner/public contract validation and test the exact allowed/forbidden matrix. |
| R08 | Rejected | No reason-message expansion. Fine category plus fixed safe message remains intentional. |
| R09 | Rejected | No storage docstring/code change; current docstrings already list `ValueError`. |
| C01 | Accepted, medium | Remove URL/raw-exception SEC diagnostics; operation-level helpers propagate, file-evidence helpers become one FAILED filing row, 6-K preview remains a FAILED filing row, and HEAD remains metadata-only optional. |

Planreview revision dispositions:

| Review finding | Controller decision / revision |
|---|---|
| MiMo F01 | Accepted: generator -> `CnPipeline.download_stream` -> collector -> adapter -> runtime no-catch path is now explicit. |
| MiMo F02 | Accepted: every SEC helper is classified in §3.4 with operation/file-local/metadata blast radius. |
| MiMo F03 + DS F04/F08 | Accepted: CN/HK retry loops are rebuilt, parser/API misuse are separated, and exception inheritance order is binding. |
| MiMo F04 | Accepted: §8.3 directly calls the rebuild producer, not only the adapter. |
| MiMo F05 + DS F05 | Accepted: all non-cancel operation exceptions propagate; the obsolete reason helper is deleted/replaced by a safe per-candidate helper. |
| MiMo F06 | Accepted as test-scan work: existing URL/raw-message assertions are inventoried and updated only in allowed tests. |
| MiMo F07 | Already covered: the legacy `status="failed" -> ValueError` test remains explicit in §8.2. |
| DS F01 | Partially accepted: empty evidence is rejected, but operation-fatal is rejected; `sec_download_filing_workflow` owns a single FAILED filing row. |
| DS F02/F03 | Accepted: cancel-check preserves typed/storage facts and per-candidate rows never use raw exception strings. |
| DS F06 | Rejected with reason: defensive `discovered_count` is retained and impossible combinations assert. |
| DS F07 | Accepted: 6-K preview remains per-filing FAILED, with safe typed diagnostics. |

## 5. Amended file allowlist

Only the following production/test files may be modified during the review-fix implementation. Documentation artifact updates remain under `docs/gateflow/` only.

### 5.1 Existing dirty production files permitted for review-fix only

- `dayu/fins/download_contract.py` — R01 and R07 only.
- `dayu/fins/direct_events.py` — R07 public-contract explanation only; no schema/validator change.
- `dayu/fins/downloaders/sec_downloader.py` — C01 auxiliary propagation and safe diagnostics only.
- `dayu/fins/pipelines/sec_pipeline.py` — C01 historical-submissions operation propagation plus 6-K per-filing safe diagnostics only.
- `dayu/fins/pipelines/cn_pipeline.py` — R02 blanket-classification removal/strict terminal validation and R06 fallback removal only.

The following existing dirty production files are frozen in this review-fix because the accepted findings do not belong to them:

- `dayu/cli/output.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/service/fins_wait_adapter.py`

They remain part of the underlying Slice 2 diff and validation union, but no follow-up edit is authorized.

### 5.2 New production additions proved necessary by the call chain

- `dayu/fins/downloaders/cninfo_downloader.py` — CNINFO HTTP/protocol/PDF error owner and safe logging.
- `dayu/fins/downloaders/hkexnews_downloader.py` — HKEX HTTP/protocol/PDF error owner and safe logging.
- `dayu/fins/pipelines/cn_download_workflow.py` — operation-terminal exception preservation; the current provenance-loss owner.
- `dayu/fins/pipelines/cn_download_rebuild.py` — required `missing_periods` producer owner.
- `dayu/fins/pipelines/sec_download_filing_workflow.py` — `list_filing_files` typed provider failure to exactly one FAILED filing row; no operation-fatal conversion.

### 5.3 Existing dirty test files permitted for review-fix only

- `tests/fins/test_sec_downloader.py` — C01 owner behavior/log scan.
- `tests/fins/test_sec_pipeline_download.py` — C01 6-K and direct `sec_download_filing_workflow` owner behavior, including a named `test_sec_download_filing_*` unique-FAILED-row/continuation test.
- `tests/fins/test_cn_download_runtime.py` — R02 adapter/runtime projection and R06 strict missing-field behavior.
- `tests/fins/test_fins_ingestion_runtime.py` — R02 public provider/storage/execution mapping plus R01/R07 contract matrix.

The existing dirty `tests/cli/test_output.py` and `tests/service/test_fins_wait_adapter.py` are frozen; they are regression-run only because CLI/wait mechanical projection is unchanged.

### 5.4 New test additions proved necessary by owner placement

- `tests/fins/test_cninfo_downloader.py` — CNINFO transport category/retryability/safe-log owner tests.
- `tests/fins/test_hkexnews_downloader.py` — HKEX transport/protocol category/retryability/safe-log owner tests.
- `tests/fins/test_cn_download_workflow.py` — exact provider/storage/execution propagation and rebuild producer contract.
- `tests/fins/test_sec_pipeline_download_stream.py` — historical-submissions provider failure propagation at the actual collection workflow boundary.

### 5.5 Explicitly excluded after evaluation

- `dayu/fins/pipelines/cn_download_filing_workflow.py`: document-local continuation owner; not the operation failure provenance bug.
- `dayu/fins/pipelines/cn_download_protocols.py` and `cn_download_models.py`: no new error envelope/model is needed when exceptions retain their type.
- `dayu/fins/pipelines/sec_sc13_filtering.py`: the accepted mis-modeling is fixed upstream by making `fetch_sc13_party_roles` propagate provider failures. The later rejection-artifact fallback occurs only after an independently established business direction mismatch and is not the cause of that rejection.
- `dayu/fins/pipelines/sec_download_workflow.py`: ticker-level workflow already allows operation-fatal typed provider exceptions to escape and already continues after a filing terminal row.
- `dayu/fins/pipelines/sec_filing_collection.py`: `classify_6k_remote_candidates` already propagates typed downloader errors to `_precheck_6k_filter`; no catch or remapping exists there.
- All CLI/service/storage files not listed above, README files, registries/oracles, controller task files, and real-observation artifacts.

## 6. Exact owner changes

### 6.1 Download contract owner

- Keep `discovered_count` in `_terminal_disposition_from_counts`. After `failed_count > 0`, and after the all-failed guard, return `PARTIAL_FAILURE` only when `discovered_count > 0`; otherwise raise `AssertionError` because the caller violated the count invariant. Delete the unreachable silent `return FAILED` fallback.
- Document that zero candidates normally derive `SUCCEEDED`, while explicit `FAILED` and `CANCELLED` are allowed only for failure/cancellation before candidate ownership begins.
- Keep all count, row, omitted, missing-period, safe-text, and locator invariants unchanged.

### 6.2 CNINFO/HKEX provider owners

This is an explicit from-zero retry-loop refactor in both synchronous downloaders, not a helper-only patch. `_http_get_json`, CNINFO `_http_post_form`, and `_http_download_bytes` must separate request transport from response parsing/validation:

1. Validate method inputs and provider/API preconditions before entering the retry loop. Those `ValueError` instances remain API misuse and are never converted to provider failure.
2. Inside the loop, perform only the HTTP request plus `raise_for_status`. Catch `httpx` transport/status exceptions, classify them, log only operation/attempt/category, and retry only when the classification says retryable.
3. For JSON methods, parse `response.json()` after a successful request in a separate parser boundary. `json.JSONDecodeError` or response-decoding `ValueError` becomes immediate `PROTOCOL/non-retryable`; it is not retried as transport and is not confused with pre-loop API misuse.
4. Validate stock-list/title-search/provider schema after parsing. Provider-shape violations and HKEX `HkexnewsProviderProtocolError` become `PROTOCOL/non-retryable` with fixed safe text; do not embed response values or raw payload.
5. Validate PDF size/magic after successful byte download. Failure is `PROTOCOL/non-retryable`, with no URL in the exception.

Closed classification table:

| Captured failure | Category | Retryable | Ordering / boundary |
|---|---|---|---|
| `httpx.TimeoutException` | `TIMEOUT` | yes | Must be tested/checked before `NetworkError` because timeout is its subclass |
| non-timeout `httpx.NetworkError` | `CONNECTION` | yes | After timeout |
| `httpx.HTTPStatusError` with 4xx | `HTTP_STATUS` | no | Stop without consuming remaining retries |
| `httpx.HTTPStatusError` with 5xx | `HTTP_STATUS` | yes | Retry to configured bound |
| `httpx.ProtocolError` | `PROTOCOL` | no | Stop immediately |
| malformed JSON/provider schema/PDF shape | `PROTOCOL` | no | Separate post-response parser/validator boundary |
| other captured `httpx.HTTPError` | `UNKNOWN` | yes | Bounded retry; fixed safe message |
| pre-request argument/API misuse `ValueError` | not provider | n/a | Preserve `ValueError` unchanged |

Retry exhaustion raises `FinsDownloadProviderError` with the correct source, closed category/retryability, and a fixed source-specific message. Retry/HEAD diagnostics contain only operation kind, attempt count, and category/fixed event; no URL, request params, raw exception, response body, contact, or absolute path.

### 6.3 CN/HK workflow and adapter owners

- In rebuild, company/discovery, outer operation, and final cancel-check paths, `CnDownloadCancelledError` alone follows the existing cancelled state. Every other `Exception` propagates unchanged instead of becoming `status="failed"`.
- `CnPipeline.download_stream` and `collect_cn_download_result_from_events` remain no-catch pass-through layers. `CnDownloadAdapter.download` also does not catch or rebuild those exceptions; it removes the `UNKNOWN/retryable=True` construction and strictly validates only actual result mappings.
- `_is_cancel_requested` does not wrap exception text. `CnDownloadCancelledError` preserves cancellation; `FinsDownloadProviderError` and `OSError` preserve provider/storage; every other exception propagates to runtime's execution classification.
- The in-scope per-candidate catch remains document-local, but replaces `_reason_code_from_exception`/`str(exc)` with one closed helper: provider -> category-derived stable reason plus `safe_message`; `OSError` -> `storage_failed` plus fixed safe text; other -> `filing_execution_failed` plus fixed safe text. Then delete `_reason_code_from_exception` and prove no references remain.
- Business document failures already represented by filing rows continue to be aggregated; this amendment does not turn every failed row into operation failure.
- Runtime production code remains unchanged because its current typed mapping is already the correct owner; tests prove that all three exception families reach it.

### 6.4 Rebuild producer and strict projection owners

- Every successful/cancelled rebuild result contains `missing_periods` as a list, currently always empty because local rebuild performs no provider discovery.
- The adapter requires the key and exact list-of-non-empty-text type on every path. No `request.rebuild_local_artifacts` missing-key special case remains.

### 6.5 SEC provider/pipeline owners

- Browse company, browse XML/submissions, SC13 role, and historical-submissions failures propagate as operation-level typed provider errors.
- The three `_try_fetch_*` file-evidence helpers propagate typed provider errors through `list_filing_files`; they never return `[]` for unavailable evidence.
- `sec_download_filing_workflow.run_download_single_filing_stream` catches only the typed provider error around `list_filing_files`, emits exactly one FAILED filing terminal with category-derived stable reason and fixed safe text, performs no batch/rejection/skip mutation for that filing, and returns. The ticker workflow consumes that terminal row and continues later filings.
- 6-K preview keeps its existing `DOWNLOAD_FAILED -> FILING_FAILED` state transition. `_precheck_6k_filter` changes only its diagnostic to closed category/fixed safe text; it does not throw operation-fatal and does not return `NO_MATCH` for provider failure.
- Optional HEAD degradation remains allowed only when its absence cannot change disposition; it records a category-only safe diagnostic.
- No change to UA single composition, first-HTTP gate, retry/throttle state, or target-file partial-failure row semantics.

## 7. Binding invariants

1. SEC UA composition is still exactly once; unconfigured identity fails before first HTTP, produces zero HTTP calls and exactly one warning, and never logs contact data.
2. A real provider transport/protocol failure is never inferred downstream from a raw dict/string and never reclassified as storage, execution, missing ticker/period, skip, or business rejection. At operation boundaries it remains typed public failure; at the two explicit filing-local owners it becomes a FAILED row, never a rejection/skip.
3. `OSError` reaches runtime as storage; non-provider/non-storage operation exception reaches runtime as execution.
4. Provider category/retryability is closed and sourced at the downloader exception boundary. Timeout is classified before its `NetworkError` parent; 4xx is non-retryable, 5xx is retryable, and parser/API misuse boundaries cannot cross.
5. Logs/public failure contain no contact, URL, raw payload, raw exception, traceback, absolute path, or provider request/response body.
6. `discovered_count == downloaded + skipped + rejected + failed`; rows and per-disposition counts remain identical and order-preserving.
7. Owner rows remain complete; public truncation remains the only omission point and `omitted_count == discovered_count - len(public_rows)` exactly.
8. `missing_periods` is required, independent of document counts, and never synthesized by adapter/runtime/CLI.
9. Zero candidate terminal override is exactly `{FAILED, CANCELLED}`; `PARTIAL_FAILURE` is forbidden and a normal zero-candidate completion remains `SUCCEEDED`.
10. CLI and wait adapter continue to mechanically project the same typed public object; neither scans files/logs nor parses source-private results.

## 8. Adversarial owner tests

### 8.1 CNINFO/HKEX transport matrix

For each provider, inject timeout, a non-timeout network failure, client/server HTTP status, malformed JSON/protocol response, and an unknown `httpx` failure. Assert exact category, retryable flag, source enum, fixed safe message, direct cause policy, call count, and absence of URL/contact/raw exception in exception text and captured logs.

- The timeout case is a hierarchy-ordering test: a real `httpx.TimeoutException` must be `TIMEOUT`, never `CONNECTION`; a separate plain `NetworkError` must be `CONNECTION`.
- 4xx makes exactly one request and is non-retryable; 5xx consumes the configured bounded retries and is retryable after exhaustion.
- Malformed JSON/schema/PDF performs no transport retry after a successful HTTP response and becomes `PROTOCOL/non-retryable`.
- A pre-request invalid ticker/provider/API argument raises the original `ValueError` and makes zero HTTP calls.
- Existing retry/backoff call-count behavior is retained for retryable errors only.

### 8.2 CN/HK provenance matrix

- Discovery raises a preconstructed `FinsDownloadProviderError`: workflow/collector/adapter preserves the same typed object; runtime public failure is provider transport with the same closed category.
- Company/rebuild storage raises `OSError`: it is not converted to JSON or provider; runtime public failure is storage.
- Rebuild provider/storage/execution failures each propagate through generator -> pipeline stream -> collector -> adapter; the exact object/cause is not replaced by a failed result.
- Cancellation checker raising `CnDownloadCancelledError` remains cancelled; raising `FinsDownloadProviderError` or `OSError` preserves the exact object; raising another exception reaches runtime as execution without its text entering public output.
- A fake/legacy workflow result containing `status="failed"` without a typed exception fails strict projection as `ValueError`; adapter must not guess provider. This test was already present in the original amendment and remains binding.
- A document-local provider failure uses `safe_message`; a path-bearing `OSError` and raw execution exception each produce fixed safe failed-row text, exactly one failed row, and permit other candidates to proceed.
- `rg`/AST proves no operation-terminal `_build_result(status="failed", message=str(exc))`, no per-candidate `reason_message=str(exc)`, and no remaining `_reason_code_from_exception` definition/reference.

### 8.3 Rebuild strictness

- Directly call `rebuild_cn_download_artifacts` with zero local documents, matching documents, failed local documents, and cancellation; every returned mapping must contain the key with exact value `"missing_periods": []`. This producer test must fail if the field is deleted, independent of adapter tests.
- Removing or mistyping that key in a fake result causes strict adapter failure even when `rebuild_local_artifacts=True`.
- Missing periods remain outside all four document counts.

### 8.4 SEC auxiliary failures

- Browse-ticker HTTP failure propagates the typed provider object and cannot fall through to ticker-not-found.
- Browse XML protocol failure becomes `PROTOCOL`, not `None`.
- Submissions-after-browse failure propagates, not `continue`.
- SC13 role HTTP failure propagates and cannot record direction mismatch.
- For each of index JSON, index headers, and linked-primary evidence, downloader helper propagates a preconstructed typed error; `list_filing_files` does not replace it with `[]`; direct `sec_download_filing_workflow` owner test asserts exactly one FAILED row for that filing, no skip/rejection/batch, and a following filing still completes.
- Historical-submissions provider failure terminates as provider failure, not a reduced candidate set.
- 6-K preview provider failure retains the existing `DOWNLOAD_FAILED` branch, produces exactly one FAILED row for that filing, never `NO_MATCH`/rejection, logs only closed category/fixed safe text, and allows a later filing to complete.
- Optional HEAD failure leaves metadata empty without changing disposition and logs only a closed category.

### 8.5 Count/terminal/public safety regression

- Cover all terminal derivations, including mixed downloaded/rejected/failed rows and the exact zero-candidate override matrix.
- Directly exercise the defensive helper with the otherwise-impossible mixed-failure/non-positive-`discovered_count` combination and assert `AssertionError`; no fallback terminal is allowed.
- Re-run the 18-owner-row -> 10-public-row case and assert `omitted_count == 8` with order unchanged.
- Re-run CLI/wait projection equivalence and all canary scans without editing those consumers.

## 9. Validation plan after implementation

No validation command in this amendment authorizes a real CLI or real provider call. After both planreviews accept the amendment, run:

```bash
source .venv/bin/activate
pytest \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/cli/test_output.py \
  tests/service/test_fins_wait_adapter.py -q
python -m pyright dayu/ tests/ utils/
python -m ruff check <all changed Python files in the Slice 2 diff>
python -m ruff format --check <all changed Python files in the Slice 2 diff>
python -m compileall dayu tests
git diff --check
```

Generate one affected-union coverage data set, then run `coverage report --include=<production-file> --fail-under=80` separately for every production file modified by the review-fix, including the five newly allowlisted production files. `sec_download_filing_workflow.py` must be covered by direct owner tests, not only indirectly by the ticker pipeline. Do not use aggregate percentage to hide a low file.

Static scans must prove:

- Before editing, inventory existing assertions with `rg -n 'url=|error=|str\(exc\)|RuntimeError' tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py`; update only assertions whose old raw diagnostic/error type contradicts the accepted typed contract.
- no `url=`, `error={exc}`, raw exception interpolation, contact canary, raw/provider payload marker, traceback, or absolute workspace path in changed logging/public projection lines;
- CN/HK operation-terminal code has no `message=str(exc)` result construction, per-candidate rows have no `reason_message=str(exc)`, `_reason_code_from_exception` is absent, and adapter has no blanket `status="failed"` provider guess;
- rebuild producer always emits `missing_periods` and adapter contains no rebuild missing-key fallback;
- SEC browse/history/SC13 provider catches do not return `None`, continue, or create a business outcome; the three file-evidence helpers do not return `[]`; `sec_download_filing_workflow` and 6-K preview each have exactly the approved filing-local FAILED projection and no rejection/skip fallback;
- CLI/wait have no filesystem scan, raw dict failure parsing, or private storage import;
- the modified-file set is a subset of this amendment allowlist plus Gateflow artifacts.

## 10. Stop conditions

Stop implementation and request another plan amendment before any out-of-scope edit if:

1. Correctness requires modifying `cn_download_filing_workflow.py`, CN protocols/models, `sec_sc13_filtering.py`, any SEC workflow file other than the newly allowlisted `sec_download_filing_workflow.py`, runtime production code, CLI/service/storage code, or adding a shared provider-error module.
2. A stream consumer contract requires `PIPELINE_COMPLETED(status="failed")` rather than typed exception propagation; do not invent a string/JSON compatibility envelope.
3. Correctness requires a new per-document transport field or another public row schema change. Category-derived use of the existing `reason_category` is allowed; a new schema is not.
4. An SEC failure cannot be placed into exactly one approved class: operation-fatal (browse company/SC13/history), filing-local FAILED (three file-evidence helpers/6-K preview), or metadata-only optional (HEAD). Do not substitute empty evidence or widen a filing failure to operation-fatal.
5. Fixing a test would require retaining a generic `RuntimeError`, raw-message assertion, missing-key fallback, or downstream classification guess.
6. Retry-loop refactoring changes bounded retry/backoff counts outside the accepted rules, treats parser `ValueError` as API misuse (or vice versa), or classifies timeout as connection. Stop rather than adding compatibility branches.
7. Any validation reveals count/omitted drift, contact/URL/raw/path leakage, changed UA call count, new pyright errors, or a modified production file below 80% coverage.
8. README, registry/oracle, controller task, real CLI, real provider, commit, branch, or PR mutation becomes necessary. Those actions remain prohibited in this review-fix gate.

## 11. Docs, residual risks, and completion state

- Docs decision: no README or accepted base-plan edit in this gate. This standalone amendment is the only new file.
- R03/R04/R05/R08/R09 are closed as rejected with the controller's reasons and create no implementation scope.
- Document-local provider category granularity remains represented by category-derived `reason_category` plus fixed safe row text, not the operation public failure envelope. This is fixed in current Slice 2 review-follow-up and needs no schema expansion.
- Filing-local continuation has two explicit SEC owners: file-list evidence failure at `sec_download_filing_workflow`, and 6-K preview `DOWNLOAD_FAILED` at `sec_pipeline`; tests must prove unique terminal row and later-filing continuation for both.
- Optional HEAD degradation remains a deliberate metadata-only behavior; tests must prove it cannot alter disposition.
- Historical submissions are operation-fatal even after earlier history payloads were collected; because candidate collection precedes filing mutation, this avoids publishing a silently incomplete selection. It remains a fixed-in-current-slice risk covered by owner tests.
- Retry-loop refactor risk is fixed in current slice by call-count/category/inheritance tests; no compatibility path is retained.
- Completion status: amendment revision drafted; not accepted until both original reviewers re-review. No product/test implementation may resume before that gate.

Artifact path: `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md`
