# Slice 2 Implementation Review

## 审查概况

| 项目 | 值 |
|---|---|
| Gate | Gateflow implementation review，Slice 2（DL-F07、DL-F11 summary） |
| 基线 HEAD | `c6829400a5e37892464a614590062511554f9633` |
| 审查时间 | 2026-08-10 |
| 审查范围 | 17 files changed, 3564 insertions(+), 771 deletions(-) |
| 审查结论 | **PASS** — 无 blocking finding |

## 验证执行

| 验证项 | 结果 |
|---|---|
| 受影响 Slice 2 测试（280 tests） | ✅ passed |
| pyright（dayu/ 全量） | ✅ 0 errors, 0 warnings, 0 informations |
| ruff check（changed files） | ✅ All checks passed |
| ruff format --check（changed files） | ✅ 11 files already formatted |
| compileall（dayu + tests） | ✅ 通过 |
| git diff --check | ✅ 通过 |

## Adversarial 审查维度

### 1. SEC UA 首 HTTP gate 与一次 warning

**结论：PASS**

- `SecDownloader.__init__` 只调用一次 `_resolve_user_agent`，保存 `SecUserAgentState.CONFIGURED | UNCONFIGURED` 与可选 `user_agent` 字符串。
- `_resolve_user_agent` 未配置时返回 `(UNCONFIGURED, None)` 并输出一次 `Log.warning`。
- `_build_headers` 在 `UNCONFIGURED` 状态下抛出 `SecUserAgentConfigurationError`，该方法在 `_http_request` 的 retry 循环**之前**（line 1782）调用，因此首个 HTTP 请求不可能发出。
- `configure` 方法不再调用 `_resolve_user_agent`，只校验显式传入值与构造时一致，不会重复 warning。
- 删除了 `_UNCONFIGURED_USER_AGENT` 常量，不存在匿名 fallback header。
- 证据：`sec_downloader.py:1017`（构造时解析一次）、`sec_downloader.py:2225-2226`（gate）、`sec_downloader.py:1782`（在 retry loop 前调用）。

### 2. Transport error 脱敏 mapping

**结论：PASS**

- `_sec_transport_category` 将 `httpx.TimeoutException`、`httpx.NetworkError`、`httpx.HTTPStatusError`、`httpx.ProtocolError`/`ValueError` 映射为封闭的 `FinsDownloadTransportCategory` enum。
- `_sec_transport_safe_message` 为每个分类返回固定中文说明，不含 URL、endpoint、raw payload、联系值或路径。
- `_http_request` 重试耗尽时抛出 `FinsDownloadProviderError`，只携带 `source`、`transport_category`、`retryable`、`safe_message`。
- 日志行已脱敏：
  - `method={method}` 但不含 `url={url}`（diff 确认删除了 url=）
  - `transport_category={_sec_transport_category(exc).value}` 但不含 `error={exc}`
  - `SEC 限流 {status_code}: 等待 {delay}s` 但不含 url
- `FinsDownloadProviderError.__init__` 通过 `_validate_public_text` 校验 `safe_message` 不含 URL（`://`）、raw payload 标记或绝对路径。
- 证据：`sec_downloader.py:885-986`（transport helper 集群）、`sec_downloader.py:1839-1852`（日志与异常构造）。

### 3. CN/HK operation status 误分类

**结论：PASS**

- CN/HK adapter 新增 `_CN_STATUS_DOWNLOADED`、`_CN_STATUS_SKIPPED`、`_CN_STATUS_FAILED` 三个常量。
- `_project_cn_document_row` 严格按这三个状态分支投影为 `FinsDownloadDocumentDisposition`；未知 status 直接 `raise ValueError("CN/HK 下载结果 status 未封闭: {status}")`。
- CN adapter 在 `_required_cn_text(result, "status") == "failed"` 时抛出 `FinsDownloadProviderError(source=request.source, transport_category=UNKNOWN, retryable=True)`，正确分类为 provider transport 失败。
- SEC adapter 同样封闭：`downloaded`、`skipped`、`rejected`、`failed` 四分支 + 未知 status fail closed。
- 证据：`cn_pipeline.py:103-105`（常量）、`cn_pipeline.py:1518-1556`（严格分支）、`cn_pipeline.py:1391-1398`（provider error）。

### 4. Typed rows / count / terminal disposition / omitted 不变量

**结论：PASS**

- `FinsDownloadResultSummary.__post_init__` 强制：
  - `discovered_count == downloaded + skipped + rejected + failed`
  - `len(document_rows) == discovered_count`
  - 每个 disposition 的 row 计数与对应 count 一致
  - `terminal_disposition` 由 `_terminal_disposition_from_counts` 机械派生；`discovered_count == 0` 时允许 `FAILED`/`CANCELLED` override
  - `missing_periods` 无重复且每个 period 通过 `_validate_public_text`
- `FinsDownloadPublicSummary.__post_init__` 强制：
  - `discovered_count == downloaded + skipped + rejected + failed`
  - `len(document_rows) + omitted_count == discovered_count`
  - visible disposition counts ≤ total counts
  - `terminal_disposition` 与 public counts 一致
- `_public_download_summary` 从完整 rows 取前 `FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS`（10）行构造 public rows，`omitted_count = discovered_count - len(public_rows)`。
- 测试覆盖：18 个 owner rows 投影 10 个 public rows，`omitted_count == 8`。
- 证据：`download_contract.py:296-364`（owner 不变量）、`direct_events.py:385-435`（public 不变量）、`ingestion_runtime.py:4929-4960`（runtime projection）。

### 5. Strict projection — 无 `.get()` / `getattr` / `str()` coercion

**结论：PASS**

- `_summary_from_pipeline_result`（SEC/CN）使用 `_required_sec_text`、`_optional_sec_text`、`_required_sec_mapping` 等严格 helper，不用 `.get()` 或 `str()`。
- `_project_sec_document_row` / `_project_cn_document_row` 对未知 status 直接 fail closed。
- `_project_sec_effective_filters` / `_project_cn_effective_filters` 校验 `overwrite`/`rebuild` flags 与 typed request 一致。
- `_bounded_download_summary` 从旧的"重新构造并校验"改为 `isinstance` 检查后直接返回原 typed 实例。
- 旧代码中的 `str(item.get("status", "")).strip()` 和 `_json_int(summary.get(...), ...)` 已全部删除。
- 证据：`sec_pipeline.py:1895-2113`（strict projection 集群）、`cn_pipeline.py:1427-1700`（strict projection 集群）。

### 6. Locator query — read-only 相对路径与 publication 语义

**结论：PASS**

- `SourceDocumentRepositoryProtocol.get_source_document_locator` 返回 `PurePosixPath`，在 publication guard 下验证 published meta 存在。
- `_FsSourceDocumentMixin.get_source_document_locator` 使用 `_acquire_publication_guard` → `_get_persisted_source_meta_unguarded` → `relative_to(self.workspace_root)` → `PurePosixPath(*relative.parts)`。
- `FinsDownloadDocumentResult.__post_init__` 校验 `artifact_locator` 不是绝对路径且不含 `..`。
- `FinsDownloadPublicDocument.__post_init__` 对 locator 字符串做 `_validate_safe_text` + `PurePosixPath` 绝对路径/`..` 检查。
- 证据：`_fs_source_document_core.py:411-462`（storage owner）、`download_contract.py:265-278`（owner contract）、`direct_events.py:307-320`（public contract）。

### 7. Runtime / CLI / Wait 同一公共真源、LLM-facing 自足

**结论：PASS**

- Runtime 从 `_FinsDownloadResultSummary`（owner）构造 `FinsDownloadPublicSummary`（public），CLI 和 wait adapter 都消费同一 `FinsResultSummary.download` / `.failure` 字段。
- CLI `_print_terminal_business_summary` 检查 `result.download is not None` 后调用 `_print_download_summary`，不再使用旧的 `_print_result_details` generic label/value。
- Wait adapter `_completed_result_value` 在 `result.download is not None` 时使用 `result.download.to_json_value()` 构造 nested JSON。
- Wait adapter `_failure_message` 在 `result.failure is not None` 时构造自解释 JSON（含 `download` + `failure` 对象），不退化为泛化错误文本。
- `FinsDownloadPublicSummary.to_json_value()` 和 `FinsPublicFailure.to_json_value()` 返回自解释 JSON，字段名和值都是业务可读的。
- 证据：`output.py:410-520`（CLI projection）、`fins_wait_adapter.py:565-610`（wait projection）。

### 8. 反向依赖、过度耦合、兼容 re-export/shim

**结论：PASS**

- `dayu.runtime` 不 import `dayu.fins` / `dayu.host` / `dayu.service` / `dayu.ui`。
- `FinsDownloadResultSummary` 从 `ingestion_runtime.py` 移至 `download_contract.py`，`ingestion_runtime` 使用 `as _FinsDownloadResultSummary` 别名导入，`__all__` 不再导出旧名。
- SEC/CN pipeline 直接从 `download_contract` 导入 `FinsDownloadResultSummary`，不再从 `ingestion_runtime` 导入。
- 旧 `FinsDownloadResultSummary` 的 `written_document_ids` 字段已删除，替换为 `document_rows` + `written_document_ids` property。
- 无兼容 wrapper、双 schema 或别名 shim。
- 证据：`ingestion_runtime.py:59`（别名导入）、`ingestion_runtime.py:7090`（__all__ 删除旧名）、`sec_pipeline.py:39`（直接导入）。

### 9. Allowlist 范围

**结论：PASS**

- Production diff 严格位于 Slice 2 allowlist（11 files）。
- Test diff 严格位于 Slice 2 allowlist（6 files）。
- 除 review artifact 外，无 allowlist 外文件变更。

### 10. Tests / Coverage gaps

**结论：PASS with notes**

- 受影响 Slice 2 测试集：280 passed。
- 单文件覆盖率：
  - `dayu/cli/output.py` — 83%
  - `dayu/fins/direct_events.py` — 87%
  - `dayu/fins/download_contract.py` — 81%
  - `dayu/fins/downloaders/sec_downloader.py` — 91%
  - `dayu/fins/ingestion_runtime.py` — 90%
  - `dayu/fins/pipelines/cn_pipeline.py` — 80%
  - `dayu/fins/pipelines/sec_pipeline.py` — 86%
  - `dayu/fins/storage/_fs_source_document_core.py` — 84%
  - `dayu/fins/storage/fs_source_document_repository.py` — 96%
  - `dayu/fins/storage/repository_protocols.py` — 100%
  - `dayu/service/fins_wait_adapter.py` — 93%
- 所有修改 production file 均达到 ≥80% 门槛。
- 关键断言覆盖：
  - 未配置 SEC 身份在首个 HTTP 前 typed fail，client 调用数为 0
  - 同一 downloader warning 恰好一次
  - 配置日志不含身份值；请求诊断不含 endpoint 或 raw exception
  - typed provider error 的敏感 cause 不进入 runtime public result
  - SEC/CN row counts 从 strict typed rows 派生
  - 真实 storage locator 是非绝对 PurePosixPath
  - 18 → 10 rows 投影，omitted_count == 8
  - CLI 与 wait adapter 均直接消费同一 typed public object

## 非阻塞性观察

1. **Ruff 基线**：仓库级 `ruff check .` 仍命中 86 个既有基线问题，均在 Slice 2 allowlist 外。Changed-file Ruff 全绿。不阻塞。

2. **真实 CLI 未运行**：按 controller 明确要求，Slice 2 未运行真实 CLI 或真实 provider。真实动态网络分类与终端 screen 观察留给 DL-G gate。

3. **Slice 3/4 未提前修改**：conversion-completed、canonical cancellation、并发/integrity 不属于本次实现。

## 结论

**PASS** — Slice 2 实现符合 DL-F07 与 DL-F11 的 accepted semantics，从 owner boundary 修复，无 semantic ownership drift，无 secret/URL/path/raw payload 泄露，typed 不变量严格守恒，strict projection 无 `.get()`/`str()` coercion，CLI 与 wait adapter 共享同一 runtime public truth source。
