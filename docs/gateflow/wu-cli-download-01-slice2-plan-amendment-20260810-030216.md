# wu-cli-download-01 Slice 2 code-review follow-up plan amendment

## 1. Artifact state

| Item | Value |
|---|---|
| Gate | Gateflow Slice 2 code review -> plan amendment |
| Work unit | `wu-cli-download-01` |
| Baseline HEAD | `c6829400a5e37892464a614590062511554f9633` |
| Branch | `codex/download-oracle` |
| Date | 2026-08-10 |
| Inputs | 两份 code review、四份先前 plan review、`docs/reviews/plan-review-20260810-slice2-cn-owner-mimo.md`、`docs/reviews/plan-review-20260810-slice2-cn-owner-ds.md`、controller adjudication |
| Scope of this pass | Direct call-chain analysis and this amendment artifact only |
| Product/test changes in this pass | None |
| Next gate | Controller 确认本轮 doc-only 澄清后恢复 review-fix implementation；当前仍暂停产品/测试修改 |

The worktree already contains the reviewed Slice 2 implementation and part of the accepted review-fix. This artifact does not reinterpret those changes as a clean baseline and does not authorize edits outside the amended allowlist below. 下文的 owner 规则描述最终必须满足的状态；凡当前 dirty diff 已实现的部分，恢复 implementation 后只做验证，并仅在对应测试或静态检查真实失败时做最小修正，不得为了重新执行计划而无效重写。

## 2. First-principles judgment

The accepted follow-up is necessary and correctly rated medium for R02, R06, and C01:

- R02 was not merely an imprecise `UNKNOWN` category. At the review-trigger baseline, CN/HK operation failure provenance was destroyed before the adapter saw it: `run_cn_download_stream_impl` caught provider, storage, and execution exceptions, wrote `message=str(exc)` into a JSON result with `status="failed"`, and `CnDownloadAdapter.download` then labeled every such result as a retryable provider failure. The current dirty diff already addresses this operation path；§§3.1/5/6 record what remains to verify or implement.
- R06 is not only a missing test. `cn_pipeline._summary_from_pipeline_result` explicitly accepts an absent required field only for rebuild, so the consumer compensates for an incomplete producer contract. `rebuild_cn_download_artifacts` is the producer that omits `missing_periods`; it must always emit the field and the adapter fallback must be deleted.
- C01 is real. SEC fallback/auxiliary paths catch typed provider errors through their `RuntimeError` base, log URL or raw exception text, and return `None`, `[]`, or a business filter classification. A transport failure can therefore be observed as ticker-not-found, missing auxiliary files, SC13 direction rejection, or 6-K business rejection instead of a provider failure.

The rejected findings do not justify changes: R03 asks a coarse direct-event enum to duplicate the already precise public failure; R04 challenges an intentional stronger LLM-facing validator; R05 challenges the deliberate fail-closed single-composition UA invariant; R08 asks safe text to duplicate the retained fine reason category; R09 is contradicted by current protocol/wrapper/core docstrings.

## 3. Direct code evidence and owner call chains

### 3.1 CN/HK operation failure provenance

Normal operation call chain:

失败产生方向为：

`真实异常 owner -> run_cn_download_stream_impl async generator -> CnPipeline.download_stream async-for（无 catch） -> collect_cn_download_result_from_events async-for（无 catch） -> CnDownloadAdapter.download（无 catch/重分类） -> Fins runtime producer catch -> _download_public_failure_from_exception`

Direct evidence（前述 review trigger 与当前 dirty diff 状态必须区分）：

1. Review trigger 时，`dayu/fins/downloaders/cninfo_downloader.py` and `hkexnews_downloader.py` 在自己的 `httpx` request/retry exhaustion、JSON/protocol 与 PDF validation owner 处抛 generic `RuntimeError` 并泄漏 `url` / `last_exc`。当前 dirty diff 已有 closed `_cninfo_http_failure` / `_hkexnews_http_failure` 与分离后的 retry/parser boundaries；恢复后验证分类、调用次数与泄漏扫描，只有真实失败才修正，不从零重写。
2. Review trigger 时，`dayu/fins/pipelines/cn_download_workflow.py` 把 operation-terminal exceptions 转成 `_build_result(status="failed", message=str(exc))`。当前 dirty diff 已删除这类 operation-terminal catch，并已把 `_is_cancel_requested` 变为无 catch 的直接调用；该部分只保留回归验证。仍待实施的是 §3.2 指定的 child-owner helper 迁移与父 leak catch 直接复用。
3. Review trigger 时，`dayu/fins/pipelines/cn_pipeline.py::CnDownloadAdapter.download` 把任何 `status="failed"` 猜成 `FinsDownloadProviderError(UNKNOWN, retryable=True)`。当前 dirty diff 已改为 strict terminal projection；恢复后只验证 legacy failed mapping 继续 fail closed。
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

`cn_download_filing_workflow.py` catches PDF/conversion failures and emits a `FILING_FAILED` row so other selected documents may continue. That is document-outcome semantics, not the operation-terminal `status="failed"` path adjudicated in R02；但 stop-condition implementation 证明该文件正是文档级失败的真实异常 owner，不能继续排除。

Direct evidence:

1. `run_cn_download_single_filing_stream` 的 PDF catch（当前约 184 行）在 `discovery_client.download_report_pdf` 的真实异常边界捕获 `Exception`，随后同时向 `FILE_FAILED` 和 `FILING_FAILED` 写入 `reason_message=str(exc)`，并把原因固定成 `pdf_download_failed`。这里会丢失 `FinsDownloadProviderError`、path-bearing `OSError` 与 execution failure 的类别，而且会公开 raw URL/contact/path 文本。
2. 同一函数的 Docling catch（当前约 316 行）也把 `str(exc)` 写入 `FILING_FAILED`，具有相同 provenance 与泄漏问题。
3. 父 `cn_download_workflow.py` 只会看到子 workflow 已产出的终态事件；对于上述两条正常 document-local failure 路径，异常不会再到达父模块的 per-candidate `except Exception`。父模块无法从 `pdf_download_failed`、row 文本或日志恢复原 typed provenance，也不得下游重猜。
4. Stop-condition 聚焦测试得到 `450 passed / 6 failed`：其中四个失败直接显示真实 PDF owner 仍输出 `pdf_download_failed`，没有使用父模块的 closed helper；另外两个失败来自 unknown-`httpx` 测试构造，属于恢复 implementation 后继续收敛的独立测试问题，不改变 owner 裁决。

Owner decision:

- 将 `dayu/fins/pipelines/cn_download_filing_workflow.py` 列为 additional in-scope production owner。该模块作为 document-local failure owner，定义唯一公开 typed direct helper：`project_cn_filing_failure(error: Exception) -> tuple[str, str]`。它不是 compatibility wrapper，也不透传调用；它直接承诺现有 row 字段使用的 `(reason_code, safe_message)` 语义。
- helper 的封闭映射唯一为：`FinsDownloadProviderError -> (f"provider_{transport_category.value}", safe_message)`；`OSError -> ("storage_failed", "下载产物读写失败")`；其它 `Exception -> ("filing_execution_failed", "财报文档执行失败")`。`CnDownloadCancelledError` 必须在进入 helper 前继续原样传播到 cancelled state。
- **PDF catch 必须只调用 helper 一次；`FILE_FAILED` 与 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 两个字段都必须逐值复用这同一个返回 pair。** 不得保留 `FILE_FAILED.reason_code="pdf_download_failed"` 或只共享 message。Docling catch 的 `FILING_FAILED` 也调用该 helper。任何 row/event 均不得写 `str(exc)`。
- 父 `cn_download_workflow.py` 直接公开导入并调用同一个 `project_cn_filing_failure`，处理真正漏出子 workflow 的 document-local exception。删除父模块自己的重复 helper；不得保留第二份 `isinstance` 映射、private cross-module import、透传 facade 或 raw-dict/string parser。
- 继续使用现有 `reason_code` / `reason_message` row contract，不新增 per-row transport 字段或 public schema。category-derived reason 已保留精确来源类别，fixed safe message 保证 URL/contact/raw payload/绝对路径不泄漏。

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

- Ticker map miss -> `_resolve_company_via_browse_edgar_ticker` -> `_http_get_bytes` / `fetch_submissions`. Review trigger 时 typed provider failures 被 `RuntimeError` catch、记录 raw exception text 并返回 `None`；caller 随后误报 ticker not found。
- SC13 direction -> `fetch_sc13_party_roles` -> `_http_get_bytes`. Review trigger 时 network failure 返回 `None`；direction evaluator 可能记录 business rejection。
- Filing file discovery -> `_try_fetch_index_items`, `_try_fetch_index_header_documents`, `_try_fetch_primary_linked_html_files`. Review trigger 时 provider failure 返回 `[]`；downstream 6-K/XBRL selection 可能把 unavailable evidence 当作 `NO_MATCH` 或其它 business rejection。
- Historical submissions -> `sec_pipeline._collect_filings` -> `fetch_json`. Review trigger 时 provider failure 被完整 history URL/raw exception 日志后跳过，减少 discovered filings。
- 6-K preview -> `sec_pipeline._filter_6k_filing` -> `classify_6k_remote_candidates` -> `fetch_file_bytes`. Review trigger 时 provider failure 被 raw log 后转成既有 `DOWNLOAD_FAILED` filing-failure category；state transition 本来正确，只有 diagnostic 不安全。

逐 helper owner 裁决（“review-trigger behavior” 记录触发 amendment 的基线问题；“修订后”是 binding terminal state，其中当前 dirty diff 已完成的部分按 §§5/6.5 只验证）：

| Helper / call site | Review-trigger behavior | 修订后 owner 与结果 |
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

Stop-condition owner re-review adjudication:

| Review finding | Final disposition | Clarification in this revision |
|---|---|---|
| MiMo F01 | Resolved | CNINFO/HKEX closed retry loops are already present in the current dirty diff. §§3.1/5.2/6.2 now require verification and failure-driven correction only, not a from-zero rewrite. |
| MiMo F02 | Resolved | `_is_cancel_requested` is already a no-catch pass-through in the current dirty diff. §§3.1/5.2/6.3 retain its tests solely as regression protection. |
| MiMo F03 | Resolved | `sec_download_filing_workflow` already contains the approved typed filing-local catch. §§5.2/6.5 mark it implemented-and-pending-verification rather than a new production change. |
| DS F01 | Resolved | §5 now distinguishes additional in-scope owners from new work and records the state of every such owner; already-correct SEC/CN dirty code must not be rewritten without a failing check. |
| DS F02 | Resolved by policy clarification | §6.2 states that CN/HK 4xx fail-fast is this WU's non-retryable policy. The SEC retry-policy difference is deliberately unchanged and outside this owner amendment. |
| DS F03 | Resolved as already specified | §3.2 and §§6.3/8.2 now make the existing decision visually explicit: one helper invocation supplies both `reason_code` and `reason_message` to both PDF terminal events. No owner, schema, or scope change is introduced. |

## 5. Amended file allowlist

Only the following production/test files may be modified during the review-fix implementation. Documentation artifact updates remain under `docs/gateflow/` only.

### 5.1 Existing dirty production owners permitted for review-fix only

- `dayu/fins/download_contract.py` — current dirty diff 已完成 R01 defensive assertion 与 R07 contract behavior；恢复后验证，必要时只修对应失败。
- `dayu/fins/direct_events.py` — current dirty diff 已完成 R07 public-contract explanation；恢复后验证，不改 schema/validator。
- `dayu/fins/downloaders/sec_downloader.py` — current dirty diff 已包含 C01 auxiliary propagation 与 safe diagnostics；恢复后按 §8.4 验证，必要时只修对应失败。
- `dayu/fins/pipelines/sec_pipeline.py` — current dirty diff 已包含 C01 historical-submissions propagation 与 6-K safe diagnostics；恢复后按 §8.4 验证既有 filing-local state transition。
- `dayu/fins/pipelines/cn_pipeline.py` — current dirty diff 已完成 R02 strict terminal projection 与 R06 fallback removal；恢复后只做 regression verification / failure-driven correction。

The following existing dirty production files are frozen in this review-fix because the accepted findings do not belong to them:

- `dayu/cli/output.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/service/fins_wait_adapter.py`

They remain part of the underlying Slice 2 diff and validation union, but no follow-up edit is authorized.

### 5.2 Additional in-scope production owners proved necessary by the call chain

“Additional in-scope” 表示 call chain 证明这些 owner 可在本 review-fix 中修改，不表示每个文件都还有待新增实现。当前状态逐项如下：

- `dayu/fins/downloaders/cninfo_downloader.py` — **已实现，待验证/必要时仅修失败**：current dirty diff 已有 CNINFO closed HTTP/protocol/PDF mapping、retry/parser separation 与 safe logging；保留 unknown-`httpx` 测试收敛，不得无效重写 retry loop。
- `dayu/fins/downloaders/hkexnews_downloader.py` — **已实现，待验证/必要时仅修失败**：current dirty diff 已有 HKEX closed mapping、retry/parser separation 与 safe logging；同样只做矩阵验证和 failure-driven correction。
- `dayu/fins/pipelines/cn_download_filing_workflow.py` — **尚待实施的 owner 修复**：PDF/Docling document-local failure 的真实异常 owner；新增唯一公开 closed projection helper，并让 PDF 两个事件复用同一次 pair。
- `dayu/fins/pipelines/cn_download_workflow.py` — **部分已实现，剩余 owner 迁移**：operation-terminal exception preservation 与 `_is_cancel_requested` pass-through 已在 current dirty diff；只剩直接导入 filing owner helper、替换 parent leak catch 调用并删除父模块重复 helper。
- `dayu/fins/pipelines/cn_download_rebuild.py` — **已实现，待验证/必要时仅修失败**：current dirty diff 已由 producer 发出 required `missing_periods`。
- `dayu/fins/pipelines/sec_download_filing_workflow.py` — **已实现，待验证/必要时仅修失败**：current dirty diff 已把 `list_filing_files` typed provider failure 投影为恰好一个 FAILED filing row；本 amendment 不要求再次改写该 catch。

### 5.3 Existing dirty test files permitted for review-fix only

- `tests/fins/test_sec_downloader.py` — C01 owner behavior/log scan.
- `tests/fins/test_sec_pipeline_download.py` — C01 6-K and direct `sec_download_filing_workflow` owner behavior, including a named `test_sec_download_filing_*` unique-FAILED-row/continuation test.
- `tests/fins/test_cn_download_runtime.py` — R02 adapter/runtime projection and R06 strict missing-field behavior.
- `tests/fins/test_fins_ingestion_runtime.py` — R02 public provider/storage/execution mapping plus R01/R07 contract matrix.

The existing dirty `tests/cli/test_output.py` and `tests/service/test_fins_wait_adapter.py` are frozen; they are regression-run only because CLI/wait mechanical projection is unchanged.

### 5.4 Additional in-scope test owners proved necessary by owner placement

这些测试文件的 current dirty assertions 必须保留；恢复后先运行既有矩阵，仅补齐 owner 迁移所需的 child PDF/Docling 与 parent same-source assertions，并收敛已知 unknown-`httpx` 构造失败，不机械重写已通过用例。

- `tests/fins/test_cninfo_downloader.py` — CNINFO transport category/retryability/safe-log owner tests.
- `tests/fins/test_hkexnews_downloader.py` — HKEX transport/protocol category/retryability/safe-log owner tests.
- `tests/fins/test_cn_download_workflow.py` — exact provider/storage/execution propagation、rebuild producer contract，以及直接子 workflow PDF/Docling closed projection 与父 workflow 同源复用测试。
- `tests/fins/test_sec_pipeline_download_stream.py` — historical-submissions provider failure propagation at the actual collection workflow boundary.

### 5.5 Explicitly excluded after evaluation

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

The accepted change was an explicit from-zero retry-loop refactor in both synchronous downloaders, not a helper-only patch；**the current dirty diff already contains that refactor**. 恢复 implementation 后以本节分类表验证 `_http_get_json`、CNINFO `_http_post_form` 与 `_http_download_bytes`；只有测试、类型检查或静态扫描证明偏离时才做最小修正，不得重新改写已满足下列边界的 loop：

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

CN/HK 对 4xx 的“一次请求后立即停止”是本 WU 明确采用的 fail-fast non-retryable policy，不是从 SEC retry loop 推导出的共享规则。SEC 当前对 4xx 的既有 retry-policy 差异不在这次 CN filing-owner amendment 中扩张或统一；如需改变 SEC policy，必须由另一个明确授权的 plan amendment 处理。

Retry exhaustion raises `FinsDownloadProviderError` with the correct source, closed category/retryability, and a fixed source-specific message. Retry/HEAD diagnostics contain only operation kind, attempt count, and category/fixed event; no URL, request params, raw exception, response body, contact, or absolute path.

### 6.3 CN/HK workflow and adapter owners

Current dirty diff 已完成 operation-terminal typed propagation、`_is_cancel_requested` no-catch pass-through、adapter strict projection 与 rebuild strict consumption；这些行为恢复后只验证。尚待代码实现的是把既有 parent-local document failure mapping 移到 `cn_download_filing_workflow.py` 的正确 owner，并让 child/parent 直接复用。

- In rebuild, company/discovery, outer operation, and final cancel-check paths, `CnDownloadCancelledError` alone follows the existing cancelled state. Every other `Exception` propagates unchanged instead of becoming `status="failed"`.
- `CnPipeline.download_stream` and `collect_cn_download_result_from_events` remain no-catch pass-through layers. `CnDownloadAdapter.download` also does not catch or rebuild those exceptions; it removes the `UNKNOWN/retryable=True` construction and strictly validates only actual result mappings.
- `_is_cancel_requested` does not wrap exception text. `CnDownloadCancelledError` preserves cancellation; `FinsDownloadProviderError` and `OSError` preserve provider/storage; every other exception propagates to runtime's execution classification.
- `cn_download_filing_workflow.py` owns one public direct helper `project_cn_filing_failure(error: Exception) -> tuple[str, str]`. It directly maps provider -> category-derived stable reason plus `safe_message`; `OSError` -> `storage_failed` plus fixed safe text；other -> `filing_execution_failed` plus fixed safe text。朴素 tuple 返回值足以对应现有两个 row 字段，不引入 dataclass、callback、facade、新 schema 或共享模块。
- **PDF exception boundary calls the helper exactly once；both `FILE_FAILED` and `FILING_FAILED` must copy both values of that single `(reason_code, reason_message)` pair without override or recomputation.** Docling exception boundary uses the same helper for `FILING_FAILED`. `CnDownloadCancelledError` remains an earlier explicit branch and never becomes a failed row.
- `cn_download_workflow.py` imports that public helper directly for only the document-local exceptions that escape the child generator. Delete the parent-local `_candidate_failure_facts` and obsolete `_reason_code_from_exception`; prove there is exactly one mapping definition and no duplicate `isinstance` classification across the two modules.
- The helper is intentionally public at the same pipeline layer because two direct producers consume the same row semantics. A private cross-module import would hide a real dependency；a forwarding wrapper in the parent would create a second apparent owner without adding semantics。
- Business document failures already represented by filing rows continue to be aggregated; this amendment does not turn every failed row into operation failure.
- Runtime production code remains unchanged because its current typed mapping is already the correct owner; tests prove that all three exception families reach it.

### 6.4 Rebuild producer and strict projection owners

- Every successful/cancelled rebuild result contains `missing_periods` as a list, currently always empty because local rebuild performs no provider discovery.
- The adapter requires the key and exact list-of-non-empty-text type on every path. No `request.rebuild_local_artifacts` missing-key special case remains.

### 6.5 SEC provider/pipeline owners

Current dirty diff 已包含本节的 SEC auxiliary typed propagation、`sec_download_filing_workflow` filing-local catch、historical-submissions propagation、6-K safe diagnostic 与 HEAD optional behavior。恢复后以 §8.4 direct-owner tests 验证；只有真实失败才在原 allowlist owner 内最小修正，不得把已正确行为当作待新增功能重写。

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
- Directly call `run_cn_download_single_filing_stream` at the child owner. For both PDF and Docling boundaries, inject separately: a preconstructed `FinsDownloadProviderError`, a path-bearing `OSError`, and a raw execution exception containing URL/contact/payload canaries. Assert exact category-derived/fixed reason, fixed safe message, exactly one filing terminal, and absence of raw exception text；**PDF additionally asserts one helper call and exact equality of both `reason_code` and `reason_message` across `FILE_FAILED` and `FILING_FAILED`—neither field may retain a PDF-specific override.**
- For the provider cases, assert the typed error's `safe_message` is used and `transport_category` appears only through the category-derived reason. For path-bearing `OSError` and raw execution exceptions, assert absolute path、URL、contact、payload marker 与 traceback 均不出现在 event/row/log serialization。
- Exercise the parent workflow leak catch with the same three preconstructed exception families and assert its `(reason_code, reason_message)` exactly equals direct `project_cn_filing_failure` output；a later candidate must still complete。This proves same-source reuse instead of duplicated behavior。
- `rg`/AST proves no operation-terminal `_build_result(status="failed", message=str(exc))`, no PDF/Docling/per-candidate `reason_message=str(exc)`, exactly one `project_cn_filing_failure` definition, parent direct import/use with no forwarding wrapper, and no remaining `_candidate_failure_facts` / `_reason_code_from_exception` definition or reference.

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

Generate one affected-union coverage data set, then run `coverage report --include=<production-file> --fail-under=80` separately for every production file modified by the review-fix, including all six additional in-scope production owners whose current dirty or resumed implementation changes remain in the Slice 2 diff. Both `cn_download_filing_workflow.py` and `sec_download_filing_workflow.py` must be covered by direct owner tests, not only indirectly by their ticker pipelines. Do not use aggregate percentage to hide a low file.

Static scans must prove:

- Before editing, inventory existing assertions with `rg -n 'url=|error=|str\(exc\)|RuntimeError' tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py`; update only assertions whose old raw diagnostic/error type contradicts the accepted typed contract.
- no `url=`, `error={exc}`, raw exception interpolation, contact canary, raw/provider payload marker, traceback, or absolute workspace path in changed logging/public projection lines;
- CN/HK operation-terminal code has no `message=str(exc)` result construction；PDF、Docling 与 parent per-candidate rows/events have no `reason_message=str(exc)`；`project_cn_filing_failure` has exactly one definition in `cn_download_filing_workflow.py` and one direct parent import/use；`_candidate_failure_facts` / `_reason_code_from_exception` are absent；adapter has no blanket `status="failed"` provider guess;
- rebuild producer always emits `missing_periods` and adapter contains no rebuild missing-key fallback;
- SEC browse/history/SC13 provider catches do not return `None`, continue, or create a business outcome; the three file-evidence helpers do not return `[]`; `sec_download_filing_workflow` and 6-K preview each have exactly the approved filing-local FAILED projection and no rejection/skip fallback;
- CLI/wait have no filesystem scan, raw dict failure parsing, or private storage import;
- the modified-file set is a subset of this amendment allowlist plus Gateflow artifacts.

## 10. Stop conditions

Stop implementation and request another plan amendment before any out-of-scope edit if:

1. `cn_download_filing_workflow.py` is now explicitly authorized only for the owner changes in §§3.2/6.3. Stop if correctness additionally requires CN protocols/models、任何其它 CN workflow、`sec_sc13_filtering.py`、任何 SEC workflow file other than the allowlisted `sec_download_filing_workflow.py`、runtime production code、CLI/service/storage code，或新增 shared failure module。若 `project_cn_filing_failure` 的最小直接接口不足，也必须再次 amendment，不得增加 private import、wrapper 或 duplicate mapper。
2. A stream consumer contract requires `PIPELINE_COMPLETED(status="failed")` rather than typed exception propagation; do not invent a string/JSON compatibility envelope.
3. Correctness requires a new per-document transport field or another public row schema change. Category-derived use of the existing `reason_category` is allowed; a new schema is not.
4. An SEC failure cannot be placed into exactly one approved class: operation-fatal (browse company/SC13/history), filing-local FAILED (three file-evidence helpers/6-K preview), or metadata-only optional (HEAD). Do not substitute empty evidence or widen a filing failure to operation-fatal.
5. Fixing a test would require retaining a generic `RuntimeError`, raw-message assertion, missing-key fallback, or downstream classification guess.
6. Retry-loop refactoring changes bounded retry/backoff counts outside the accepted rules, treats parser `ValueError` as API misuse (or vice versa), or classifies timeout as connection. Stop rather than adding compatibility branches.
7. Any validation reveals count/omitted drift, contact/URL/raw/path leakage, changed UA call count, new pyright errors, or a modified production file below 80% coverage.
8. README, registry/oracle, controller task, real CLI, real provider, commit, branch, or PR mutation becomes necessary. Those actions remain prohibited in this review-fix gate.

## 11. Docs, residual risks, and completion state

- Docs decision: no README or accepted base-plan edit in this gate. This pass revises only this already committed standalone amendment；no other artifact、production file or test file is authorized before re-review acceptance。
- R03/R04/R05/R08/R09 are closed as rejected with the controller's reasons and create no implementation scope.
- CN/HK document-local provider category granularity is owned by `cn_download_filing_workflow.project_cn_filing_failure` and remains represented by category-derived existing reason field plus fixed safe row text, not the operation public failure envelope. PDF、Docling 与 parent leak catch all consume that one source of truth；no schema expansion is needed。
- Stop-condition trigger evidence is `450 passed / 6 failed` from the focused implementation run. Four failures proved the previously excluded child owner still emitted `pdf_download_failed` instead of the intended closed projection；this revision fixes the plan scope/owner error。The remaining two failures are unknown-`httpx` test-construction issues and are classified `fixed in current slice` once implementation resumes；they do not authorize production scope expansion。
- CN/HK filing-local continuation has one explicit owner: `cn_download_filing_workflow` produces the safe PDF/Docling failed events/rows，while `cn_download_workflow` directly reuses its public helper only for exceptions that actually escape the child generator。
- Filing-local continuation has two explicit SEC owners: file-list evidence failure at `sec_download_filing_workflow`, and 6-K preview `DOWNLOAD_FAILED` at `sec_pipeline`; tests must prove unique terminal row and later-filing continuation for both.
- Optional HEAD degradation remains a deliberate metadata-only behavior; tests must prove it cannot alter disposition.
- Historical submissions are operation-fatal even after earlier history payloads were collected; because candidate collection precedes filing mutation, this avoids publishing a silently incomplete selection. It remains a fixed-in-current-slice risk covered by owner tests.
- Retry-loop refactor risk is fixed in current slice by call-count/category/inheritance tests; no compatibility path is retained.
- Stop-condition re-review adjudication is complete with no blocker: MiMo F01/F02/F03 are respectively resolved by the no-rewrite retry-loop status、the already-pass-through cancel-check status、and the already-implemented SEC filing-owner status；DS F01 is resolved by per-owner implementation-state labels，DS F02 is resolved by the explicit CN/HK-only 4xx fail-fast policy with no SEC expansion，and DS F03 is resolved as already specified by the single helper-pair requirement for both PDF terminal events。No finding changes owner、allowlist、schema or stop-condition scope。
- Completion status: `plan-review-20260810-slice2-cn-owner-mimo.md` is PASS and `plan-review-20260810-slice2-cn-owner-ds.md` is PASS-WITH-RISKS with no blocking finding；their six findings are adjudicated in §4 and clarified here。Product/test implementation remains paused under the current doc-only instruction until controller authorizes resume。

Artifact path: `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md`
