# Slice 2 Re-review — Independent Adversarial Pass

## 1. 审查元数据

| 项 | 值 |
|---|---|
| 审查类型 | 独立严格 re-review，基于初审 accepted/rejected findings 逐项核验 |
| 基线 HEAD | `da27b92a03f74d9a3785e208b63d2d0b6f5c2ad3` |
| Work unit | `wu-cli-download-01` |
| Slice | 2 (DL-F07, DL-F11 summary) + review-fix amendment |
| 审查日期 | 2026-08-10 |
| 审查人 | AgentMiMo（独立路径，基于完整 dirty diff 与所有 plan/review artifacts） |
| 输入文档 | `wu-cli-download-01-plan-20260809.md`、`wu-cli-download-01-slice2-plan-amendment-20260810-030216.md`、`wu-cli-download-01-slice2-implementation-20260810-023031.md`、`wu-cli-download-01-slice2-review-fix-20260810-043450.md`、初审 `code-review-20260810-slice2.md`、初审 `code-review-20260810-051500.md` |
| Changed files | 27（18 production + 9 test），含 review-fix 扩展的 additional in-scope owners |
| 产品代码修改 | 0（本次 re-review 不修改任何产品/测试代码） |
| 提交 | 不提交 |

## 2. 审查范围与方法

本次 re-review 完整读取了所有 27 个 changed files 的 `git diff da27b92a`，逐文件走读了：

- 所有 production 文件的关键新增函数、修改逻辑和删除路径
- 所有 test 文件的新增断言和修改行为
- 所有 plan/review/implementation artifacts 的 accepted findings、rejected findings 与 stop conditions

审查维度：correctness、stability、maintainability、adversarial failure pass、项目指令、架构/语义所有权、过度耦合、semantic ownership drift、LLM-facing/public contract、日志泄漏、取消/terminal uniqueness、storage locator、CLI/wait mechanical projection、tests/coverage 真实性。

## 3. Findings

**未发现实质性问题。**

所有初审 accepted findings 已验证闭合，rejected findings 未被错误实现，stop-condition owner helper 唯一同源。详见 §4 逐项核验。

## 4. 初审 Accepted Findings 逐项核验

### R01 — `_terminal_disposition_from_counts` dead code【已闭合】

**直接证据：** `download_contract.py:475-491`

```python
def _terminal_disposition_from_counts(*, discovered_count, downloaded_count, rejected_count, failed_count):
    if failed_count == 0:
        return FinsDownloadTerminalDisposition.SUCCEEDED
    if downloaded_count == 0 and rejected_count == 0:
        return FinsDownloadTerminalDisposition.FAILED
    if discovered_count > 0:
        return FinsDownloadTerminalDisposition.PARTIAL_FAILURE
    raise AssertionError("mixed download failure requires discovered_count > 0")
```

**验证结果：** 不可达 `return FAILED` 已替换为 `raise AssertionError`，作为 defensive assertion 保留。由 `FinsDownloadResultSummary.__post_init__` 不变量保证 `discovered_count == downloaded + skipped + rejected + failed`，当 `failed_count > 0` 且不满足全失败条件时 `discovered_count > 0` 恒真。amendment §6.1 的要求已满足。

### R02 — CN/HK adapter blanket UNKNOWN mapping【已闭合】

**直接证据：**

1. `cninfo_downloader.py:743-808`：新增 `_cninfo_http_failure(error)` 将 `httpx.TimeoutException` → `TIMEOUT/retryable`、`httpx.NetworkError` → `CONNECTION/retryable`、`httpx.HTTPStatusError` → `HTTP_STATUS`（5xx retryable, 4xx non-retryable）、`httpx.ProtocolError` → `PROTOCOL/non-retryable`、其他 → `UNKNOWN/retryable`。所有分类使用固定 safe message。
2. `hkexnews_downloader.py:665-711`：新增 `_hkexnews_http_failure(error)`，分类表与 CNINFO 一致。
3. `cn_download_workflow.py:107-115`：rebuild path 不再 catch `Exception` 并构造 `status="failed"`。`rebuild_cn_download_artifacts` 直接调用，异常原样传播。
4. `cn_download_workflow.py:280-282`：per-candidate catch 使用 `project_cn_filing_failure(exc)` 生成 `(reason_code, reason_message)`。
5. `cn_pipeline.py:1391-1398`：adapter 删除 blanket `status="failed" -> UNKNOWN/retryable=True` 构造。strict terminal projection 只接受 `ok`/`cancelled`，legacy `status="failed"` fail closed as `ValueError`。

**验证结果：** CNINFO/HKEX 在 downloader owner 边界映射 closed typed error；operation-terminal 异常不再被 `status="failed"` 字符串包装；adapter 不猜测 provider 语义。amendment §§3.1/6.2/6.3 的要求已满足。

### R06 — Rebuild `missing_periods`【已闭合】

**直接证据：**

1. `cn_download_rebuild.py:118-120`：`rebuild_cn_download_artifacts` 返回值新增 `"missing_periods": []`。
2. `cn_pipeline.py:1437`：adapter 使用 `_required_cn_text_list(result, "missing_periods")`，无 rebuild 专用 fallback。
3. `test_cn_download_workflow.py:1403`：rebuild 测试断言 `result["missing_periods"] == []`。

**验证结果：** producer 始终发出 required `missing_periods`；strict consumer 不区分 rebuild/normal path。amendment §6.4 的要求已满足。

### R07 — Zero-candidate terminal override【已闭合】

**直接证据：**

1. `download_contract.py:355-363`：`empty_terminal_override` 注释明确语义——零候选通常 `SUCCEEDED`，`FAILED`/`CANCELLED` 仅用于 adapter 启动前的失败/取消。
2. `direct_events.py:430-435`：`FinsDownloadPublicSummary.__post_init__` 同样包含 `empty_terminal_override`，public contract 一致。

**验证结果：** owner 和 public 两层都允许 zero-candidate 的 `FAILED`/`CANCELLED` override，禁止 `PARTIAL_FAILURE`。amendment §6.1 的要求已满足。

### C01 — SEC auxiliary provider errors and unsafe logs【已闭合】

**直接证据：**

1. `sec_downloader.py:1192-1206`：`_resolve_company_via_browse_edgar_ticker` HTTP 不再 catch `RuntimeError`，typed provider error 原样传播。
2. `sec_downloader.py:1236-1254`：`fetch_sc13_party_roles` HTTP 不再 catch `RuntimeError`，typed provider error 原样传播。
3. `sec_downloader.py:2064-2078`：`_try_fetch_index_items` 不再 catch `RuntimeError` 返回 `[]`，typed provider error 原样传播。
4. `sec_downloader.py:2093-2118`：`_try_fetch_index_header_documents` 同上。
5. `sec_downloader.py:2128-2148`：`_try_fetch_primary_linked_html_files` 同上。
6. `sec_pipeline.py:1199-1205`：historical submissions `fetch_json` 不再 catch `RuntimeError` 后 `continue`，typed provider error 原样传播。
7. `sec_pipeline.py:1721-1727`：6-K preview catch 改为 `FinsDownloadProviderError`，日志只记 `transport_category`。
8. `sec_download_filing_workflow.py:284-306`：`list_filing_files` 抛 typed provider error 时，catch 产生 exactly one FAILED filing row 并 return，不 begin batch、不 skip/reject。
9. `sec_downloader.py:1985-1993`：optional HEAD 失败改 catch `FinsDownloadProviderError`，日志只记 `transport_category`。

**验证结果：** operation-level helpers（browse/SC13/history）传播 typed error；file-evidence helpers 传播到 filing-local FAILED row；6-K preview 保留 `DOWNLOAD_FAILED` 分支并使用 safe diagnostic；HEAD 保持 metadata-only optional。amendment §§3.4/6.5 的要求已满足。

## 5. Rejected Findings 核验

### R03 — Rejected: No `FinsErrorKind` expansion【正确未实现】

`FinsErrorKind` 未增加 CONFIGURATION 成员。`_classify_direct_error` 对 `SecUserAgentConfigurationError`（`FinsDownloadProviderError` 子类）返回 `PROVIDER`。`FinsPublicFailureKind` 正确区分 `CONFIGURATION`。两个分类体系是独立的，public failure 投影正确。

### R04 — Rejected: No validator rename/merge【正确未实现】

`_validate_public_text` 和 `_validate_safe_text` 保持各自独立。检查集差异是 intentional：`_validate_safe_text` 用于 LLM-facing content，检查 job ID/内部标识；`_validate_public_text` 用于 internal contract 字段，检查 URL/raw payload。两者路径检查策略略有不同（regex vs prefix），但覆盖充分。

### R05 — Rejected: No UA lifecycle change【正确未实现】

`SecDownloader.configure()` 保留 `user_agent` 参数。当传入 `None` 时跳过校验；传入非 None 且与已配置值不同时抛 `ValueError`。这是 intentional fail-closed invariant。

### R08 — Rejected: No reason-message expansion【正确未实现】

SKIPPED/REJECTED/FAILED rows 使用固定 safe message（如"该文档按下载策略跳过""SEC 来源未能完成该文档"），不复制 raw provider text。`reason_category` 携带 fine-grained classification。这是 intentional security design。

### R09 — Rejected: No storage docstring change【正确未实现】

`get_source_document_locator` 的 Raises 部分已包含 `ValueError`（identity/source kind/meta 不合法时）。`relative_to` 的 `ValueError`（document_dir 不在 workspace_root 下）在正常 storage 结构下不会发生。

## 6. Stop-Condition Owner Helper 唯一同源核验

### `_download_terminal_disposition`（direct_events.py:1083-1108）

用于 public terminal 从 counts 机械派生终态。与 `_terminal_disposition_from_counts` 逻辑一致，但增加 `discovered_count > 0` 的 defensive assertion。

### `_terminal_disposition_from_counts`（download_contract.py:475-491）

用于 owner summary 从 counts 派生终态。增加 zero-candidate `FAILED`/`CANCELLED` override 的 `empty_terminal_override` 逻辑。

**两者关系：** 分属不同层（public vs owner），逻辑核心一致（`failed==0 → SUCCEEDED`、全失败 → `FAILED`、混合 → `PARTIAL_FAILURE`），各自增加所在层的边界条件。不存在重复定义或不一致。

### `project_cn_filing_failure`（cn_download_filing_workflow.py:56-76）

唯一定义。直接被以下三处消费：
1. `cn_download_filing_workflow.py` PDF catch（line ~203）
2. `cn_download_filing_workflow.py` Docling catch（line ~336）
3. `cn_download_workflow.py` parent per-candidate catch（line ~280）

无 wrapper、forwarding facade、private cross-module import 或 duplicate mapper。`_candidate_failure_facts` 和 `_reason_code_from_exception` 已删除。

## 7. Semantic Ownership Drift 检查

**未发现 drift。**

- `download_contract.py` 拥有 typed contract（disposition/result/summary/filters/error）
- `direct_events.py` 拥有 public event contract（public summary/failure/document）
- `ingestion_runtime.py` 拥有 runtime projection（`_public_download_summary`/`_download_public_failure_from_exception`）
- `sec_pipeline.py`/`cn_pipeline.py` 拥有 strict projection from workflow-private result
- `output.py`/`fins_wait_adapter.py` 机械投影 typed public object
- `_fs_source_document_core.py` 拥有 locator query

各层职责清晰，无下游补偿上游语义、无 fallback/shim、无 `.get()`/`getattr`/`str()` coercion。

## 8. LLM-facing / Public Contract 检查

- `FinsPublicFailure.to_json_value()` 返回自解释 JSON（classification/source/transport_category/message/retry_hint）
- `FinsDownloadPublicSummary.to_json_value()` 返回 nested 自解释 JSON（source/ticker/filters/counts/documents/missing_periods/omitted_count/terminal_disposition）
- CLI `_print_terminal_business_summary` 从 typed object 投影，不扫描文件、不读 raw dict
- Wait adapter `_completed_result_value` 和 `_failure_message` 从同一 typed object 投影
- `_validate_safe_text` 阻止 URL（`://`）、disallowed fragments、job ID pattern、absolute path（POSIX + Windows）
- `_validate_public_text` 阻止 URL（`://`）、raw/provider payload、absolute path
- 所有 safe message 使用固定中文文本或 category-derived stable code，不含 URL/contact/raw payload/traceback

## 9. 日志泄漏检查

- SEC 日志：`method={method}` 不含 `url=`；`transport_category={...}` 不含 `error=`；限流日志不含 url
- CNINFO 日志：`attempt={...} transport_category={...}` 不含 `url=` 或 `error=`
- HKEXNEWS 日志：同上
- HEAD 失败日志：`transport_category={...}` 不含 url 或 error
- 6-K 预下载日志：`transport_category={...}` 不含 url 或 error
- `_sec_file_failure_facts` 返回 `(reason_code, safe_message)`，不复制 `str(exc)`

## 10. 取消 / Terminal Uniqueness 检查

- `_is_cancel_requested`（cn_download_workflow.py 和 cn_download_rebuild.py）改为 no-catch pass-through
- `CnDownloadCancelledError` 由 caller 显式 catch 并设置 `cancelled = True`
- `FinsDownloadProviderError`/`OSError` 原样传播到 runtime 的 provider/storage classification
- 其他 `Exception` 原样传播到 runtime 的 execution classification
- CN operation-terminal catch 已删除，不再构造 `status="failed"` 字符串 envelope

## 11. Storage Locator 检查

- `get_source_document_locator` 在 `_FsSourceDocumentMixin` 中实现
- 获取 publication guard → 读取 persisted source meta → `relative_to(workspace_root)` → `PurePosixPath`
- `FinsDownloadDocumentResult.__post_init__` 校验：非绝对路径、不含 `..`
- `FinsDownloadPublicDocument.__post_init__` 二次校验：`_validate_safe_text` + PurePosixPath 绝对路径/`..` 检查
- Protocol、wrapper、core 三层一致，无 `getattr`/compat shim

## 12. CLI / Wait Mechanical Projection 检查

- CLI `_print_terminal_business_summary`：`result.download is not None` 时调用 `_print_download_summary`，否则 fallback 到旧 `_print_result_details`
- Wait adapter `_completed_result_value`：`result.download is not None` 时用 `result.download.to_json_value()`，否则用 `_details_value(result.details)`
- Wait adapter `_failure_message`：`result.failure is not None` 时构造 nested JSON（含 download + failure），否则用 `result.error_message`
- 两者均不 import storage、不扫描文件、不从 raw dict 构造 facts

## 13. Tests / Coverage 真实性检查

- review-fix 实现报告：`513 passed, 3 warnings in 10.26s`
- 3 个 warnings 是 upstream `edgar` deprecation warnings，非 Slice 2 断言或行为 warning
- 单文件覆盖率均 ≥80%（最低 `download_contract.py` 80.13%，最高 `fs_source_document_repository.py` 96%）
- 关键断言覆盖已在初审 §10 详细列出，本次 re-review 未发现新增 gap

## 14. Open Questions

无。

## 15. Residual Risk

| 风险 | 分类 | 说明 |
|---|---|---|
| 真实 CLI 和真实 provider 执行被明确禁止 | covered by later approved slice | DL-G real-observation gates |
| 3 个 upstream `edgar` deprecation warnings | assigned to later work unit | 与 Slice 2 download 语义无关 |
| 受控进程/取消和 storage 并发行为 | covered by later approved slice | Slice 3 / Slice 4 |

## 16. 结论

**PASS** — 无未闭合 material finding。

初审 accepted findings R01/R02/R06/R07/C01 全部验证闭合。Rejected findings R03/R04/R05/R08/R09 未被错误实现。Stop-condition owner helper 唯一同源。Semantic ownership drift、日志泄漏、LLM-facing contract、terminal uniqueness、storage locator、CLI/wait projection 均无问题。
