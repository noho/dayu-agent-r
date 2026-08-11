# wu-cli-download-01 Slice 2 — 独立严格 Code Re-Review

## Scope

| 项 | 值 |
|---|---|
| 审查类型 | 独立 adversarial re-review（当前未提交 dirty diff） |
| 基线 HEAD | `da27b92a` |
| Branch | `codex/download-oracle` |
| Work unit | `wu-cli-download-01` |
| Slice | 2 (DL-F07, DL-F11 summary) + review-fix amendment |
| 审查日期 | 2026-08-10 |
| 审查人 | AgentDS（独立路径，不依赖初审 reviewer 结论） |
| 输入文档 | accepted plan `wu-cli-download-01-plan-20260809.md`、amendment `wu-cli-download-01-slice2-plan-amendment-20260810-030216.md`、implementation `wu-cli-download-01-slice2-implementation-20260810-023031.md`、review-fix `wu-cli-download-01-slice2-review-fix-20260810-043450.md`、初审两篇 `code-review-20260810-slice2.md` 与 `code-review-20260810-051500.md`、amendment 两路 plan review `plan-review-20260810-slice2-cn-owner-mimo.md` 与 `plan-review-20260810-slice2-cn-owner-ds.md`、两路 rereview |
| Changed files | 27 files, +5696/-1345 |
| 审查范围 | 完整 `git diff HEAD`（未提交 current changes）；逐文件源码走读验证 |

## 1. 初审 Finding 闭合逐项核验

### R01 — Dead code in `_terminal_disposition_from_counts` → **ACCEPTED / 已闭合**

- **初审描述**：函数末尾 `return FAILED` 不可达。
- **当前代码证据**：`dayu/fins/download_contract.py:509` — `raise AssertionError("mixed download failure requires discovered_count > 0")`。不再存在不可达的 `return FAILED` fallback。
- **验证**：`discovered_count > 0` 检查保留为 defensive witness，不可达组合抛 `AssertionError` 而非静默返回错误终态。
- **结论**：✅ 已闭合。

### R02 — CN/HK adapter 将所有 workflow 级失败统一映射为 UNKNOWN → **ACCEPTED / 已闭合**

初审指出的问题在两个层面均已修复：

**层面 1：CNINFO/HKEX downloader transport 映射**

- `dayu/fins/downloaders/cninfo_downloader.py:746-784` — `_cninfo_http_failure` 实现五类 granular mapping：`TimeoutException → TIMEOUT`、`NetworkError → CONNECTION`、`HTTPStatusError → HTTP_STATUS`（5xx retryable、4xx non-retryable）、`ProtocolError → PROTOCOL`、其他 → `UNKNOWN`。`isinstance` 顺序 `TimeoutException` 在 `NetworkError` 之前（两者是 `HTTPError` 的平级子类，顺序不影响正确性，但显式分离是额外防御）。
- `dayu/fins/downloaders/hkexnews_downloader.py:668-706` — `_hkexnews_http_failure` 完全对称的五类映射，safe_message 不含 URL/contact/path。

**层面 2：document-local failure owner**

- `dayu/fins/pipelines/cn_download_filing_workflow.py:59-76` — `project_cn_filing_failure` 是唯一公开 helper。三段映射：`FinsDownloadProviderError → (f"provider_{category}", safe_message)`、`OSError → ("storage_failed", "下载产物读写失败")`、其他 → `("filing_execution_failed", "财报文档执行失败")`。
- PDF catch（line 206）调用 helper 一次，`FILE_FAILED` 和 `FILING_FAILED` 的 `reason_code` 与 `reason_message` 均复用同一 pair。
- Docling catch（line 339）调用同一 helper。
- 父 `cn_download_workflow.py:18` 通过 `from cn_download_filing_workflow import project_cn_filing_failure` 直接导入，line 283 调用。
- `CnDownloadCancelledError` 在 child（line 203/336）和 parent（line 278）均显式排除，不进入 helper。

**层面 3：adapter strict projection**

- `dayu/fins/pipelines/cn_pipeline.py:1445` — terminal status 严格限定为 `{ok, cancelled}`，legacy `status="failed"` 直接 `ValueError` fail closed。

**层面 4：operation-terminal propagation**

- `cn_download_workflow.py` 无 `_build_result(status="failed", message=str(exc))` 残留（rg 确认零匹配）。
- `_is_cancel_requested`（line 356-372）是简单 pass-through，无 wrapping。
- `_candidate_failure_facts` 和 `_reason_code_from_exception` 均已删除（rg 确认零匹配）。

**结论**：✅ 已闭合。

### R03 — `_classify_direct_error` 将 CONFIGURATION 归入 PROVIDER → **REJECTED / 未实现**

- **初审裁决**：rejected with reason — `FinsErrorKind` 是 coarse enum 用于内部 direct event 分类，public failure 投影已在 `FinsPublicFailureKind.CONFIGURATION` 正确分类。CLI 和 wait adapter 不依赖 `error_kind`。
- **当前代码验证**：`dayu/fins/ingestion_runtime.py:5205-5206` — `if isinstance(exc, FinsDownloadProviderError): return FinsErrorKind.PROVIDER`。行为与初审时一致，未改变。
- **结论**：✅ Rejection 被正确遵守，无错误实现。

### R04 — `_validate_public_text` 与 `_validate_safe_text` 命名与检查集不一致 → **REJECTED / 未实现**

- **初审裁决**：rejected with reason — 两个 validator 服务于不同边界（内部 contract 字段 vs LLM-facing content），各自检查集是有意设计。
- **当前代码验证**：
  - `download_contract.py` 的 `_validate_public_text` 检查 `://`、`raw payload`、`provider payload`、绝对路径前缀。
  - `direct_events.py` 的 `_validate_safe_text` 额外检查 job ID、governance 标识、正则绝对路径。
  - 未做重命名、合并或 weakening。
- **结论**：✅ Rejection 被正确遵守。

### R05 — `configure()` 与 workflow host 的二次 UA 配置潜在不一致 → **REJECTED / 未实现**

- **初审裁决**：rejected with reason — 当前所有已知路径一致。`configure(user_agent=None)` 语义为"不改动已配置身份"，workflow 二次 configure 是调参（sleep_seconds、max_retries）。
- **当前代码验证**：`dayu/fins/downloaders/sec_downloader.py:1116-1118` — `configure` 保留 `user_agent` 参数，`None` 时跳过校验。`_build_headers` 在 `UNCONFIGURED` 时抛 `SecUserAgentConfigurationError`。
- **结论**：✅ Rejection 被正确遵守。

### R06 — CN/HK rebuild path 的 `missing_periods` 条件分支未测试 → **ACCEPTED / 已闭合**

- **初审描述**：adapter 有 rebuild-only missing-key fallback，workflow 在 rebuild 模式下不产出 `missing_periods`。
- **当前代码证据**：
  - `dayu/fins/pipelines/cn_download_rebuild.py:121` — producer 始终 emit `"missing_periods": []`。
  - `dayu/fins/pipelines/cn_pipeline.py:1459` — adapter 使用 `_required_cn_text_list(result, "missing_periods")` 严格读取，无 rebuild fallback。
  - 旧条件 `if request.rebuild_local_artifacts and "missing_periods" not in result` 已删除（rg 确认零匹配）。
- **结论**：✅ 已闭合。

### R07 — Zero-candidate + FAILED/CANCELLED 终态语义需文档化 → **ACCEPTED / 已闭合**

- **初审描述**：`empty_terminal_override` 逻辑正确但缺少注释。
- **当前代码证据**：`dayu/fins/download_contract.py:1033-1037` — comment 已添加："零候选通常表示正常完成且没有命中；只有 adapter 启动前失败或取消可覆盖终态。" override 仅允许 `{FAILED, CANCELLED}`。
- **结论**：✅ 已闭合。

### R08 — CN pipeline SKIPPED 的 reason_message 固定文本 → **REJECTED / 未实现**

- **初审裁决**：rejected — 固定 safe_message 是有意安全脱敏设计，`reason_category` 携带精确粒度。
- **当前代码验证**：`dayu/fins/pipelines/cn_pipeline.py:1526-1538` — SKIPPED 分支仍使用固定 reason_message，`reason_category` 来自 workflow 私有的 reason_code/skip_reason。
- **结论**：✅ Rejection 被正确遵守。

### R09 — Storage locator `relative_to` 的 `ValueError` 未在 docstring 声明 → **REJECTED / 未实现**

- **初审裁决**：rejected — 当前 production 路径下 document_dir 始终在 workspace_root 内。
- **当前代码验证**：`dayu/fins/storage/_fs_source_document_core.py:455-456` — `relative_to` 调用未加额外 catch。docstring 已声明 `ValueError`（line 432："identity、source kind、meta 或相对关系非法时抛出"）。当前 docstring 比初审时更完整。
- **结论**：✅ Rejection 被正确遵守。

### C01 — SEC fallback/auxiliary paths 泄漏 URL/raw exception → **ACCEPTED / 已闭合**

每类辅助路径核验如下：

| 路径 | 位置 | 当前行为 | 状态 |
|---|---|---|---|
| `_try_fetch_index_items` | `sec_downloader.py:2053-2080` | docstring 宣告 `Raises: FinsDownloadProviderError`，底层 `_http_get_json` 已 typed mapping | ✅ |
| `_try_fetch_index_header_documents` | `sec_downloader.py:2082` | 同上，typed error 传播 | ✅ |
| `_try_fetch_primary_linked_html_files` | `sec_downloader.py:2117` | 同上，typed error 传播 | ✅ |
| `sec_download_filing_workflow` | `sec_download_filing_workflow.py:287-305` | catch `FinsDownloadProviderError` → 单 `FILING_FAILED` row，`reason_code=f"provider_{category}"`，`reason_message=exc.safe_message` | ✅ |
| 6-K preview `_precheck_6k_filter` | `sec_pipeline.py:1724-1729` | catch `FinsDownloadProviderError` → log only `transport_category.value` → return `DOWNLOAD_FAILED` | ✅ |
| Historical submissions `fetch_json` | `sec_pipeline.py:1202` | `fetch_json` 传播 typed error，外层无 catch → operation-fatal | ✅ |
| Browse company / SC13 role | `sec_downloader.py` | `_resolve_user_agent` 一次解析，`_build_headers` 在 HTTP 前 gate | ✅ |
| URL/raw exception 日志 | `sec_downloader.py` + `sec_pipeline.py` | rg 确认零匹配 `log.*url` 模式 | ✅ |
| `_build_headers` UA gate | `sec_downloader.py:2191-2192` | UNCONFIGURED → `SecUserAgentConfigurationError`，首次 HTTP 前阻断 | ✅ |

**结论**：✅ 已闭合。

### 初审 Finding 闭合汇总

| Finding | 初审裁决 | 闭合状态 |
|---|---|---|
| R01 | Accepted | ✅ 已闭合 |
| R02 | Accepted/upgraded | ✅ 已闭合 |
| R03 | Rejected | ✅ 未实现（符合裁决） |
| R04 | Rejected | ✅ 未实现（符合裁决） |
| R05 | Rejected | ✅ 未实现（符合裁决） |
| R06 | Accepted/upgraded | ✅ 已闭合 |
| R07 | Accepted | ✅ 已闭合 |
| R08 | Rejected | ✅ 未实现（符合裁决） |
| R09 | Rejected | ✅ 未实现（符合裁决） |
| C01 | Accepted | ✅ 已闭合 |

## 2. Stop-Condition Owner Helper 唯一同源检查

### `project_cn_filing_failure` 唯一性

- **定义**：`cn_download_filing_workflow.py:59` — 唯一定义。rg 确认全仓仅此一处。
- **子 workflow 调用**：PDF catch line 206 + Docling catch line 339 — 共 2 处。
- **父 workflow 调用**：`cn_download_workflow.py:283` — 1 处直接导入调用。
- **无 wrapper/facade/duplicate mapper**：父直接 `from cn_download_filing_workflow import project_cn_filing_failure`，无 forwarding wrapper。
- **旧 helper 已删除**：`_candidate_failure_facts` 和 `_reason_code_from_exception` 零匹配。

### PDF `FILE_FAILED` 与 `FILING_FAILED` 同源复用

- `cn_download_filing_workflow.py:206` — helper 调用一次，`reason_code` 和 `reason_message` 存入局部变量。
- `FILE_FAILED` event（line 207-218）：`"reason_code": reason_code, "reason_message": reason_message`。
- `FILING_FAILED` result（line 219-227）：`reason_code=reason_code, reason_message=reason_message`。
- 两处使用完全相同的 pair，无 PDF 专属 override。

### `str(exc)` / `message=str(exc)` 残留检查

- `cn_download_filing_workflow.py` — 零匹配。
- `cn_download_workflow.py` — 零匹配。
- `cn_download_rebuild.py` — 零匹配。

### Adapter 无 blanket provider UNKNOWN 猜测

- `cn_pipeline.py:1445` — terminal status 仅接受 `ok`/`cancelled`。Legacy `failed` 直接 `ValueError`。
- `cn_pipeline.py:1394-1400`（初审 R02 所指位置）— 该分支已不存在（rg 确认零匹配 `UNKNOWN.*retryable.*True` 模式）。

**结论**：`project_cn_filing_failure` 是唯一 source of truth，所有 consumer 同源复用，无 wrapper/facade/duplicate mapper，无 `str(exc)` 残留。✅

## 3. 专项 Adversarial 审查

### 3.1 SEC UA 首 HTTP Gate 与一次 Warning

- `_resolve_user_agent` 只在 `__init__`（line 1038）调用一次。
- 未配置时返回 `(UNCONFIGURED, None)` 并输出一次 warning。
- `configure` 不再调用 `_resolve_user_agent`，不重复 warning。
- `_build_headers`（line 2191）在 UNCONFIGURED 时抛 `SecUserAgentConfigurationError`，在 `_http_request` retry loop **之前**被调用。
- 未配置时 HTTP client 调用数为 0（有 test 验证）。
- 日志不含 contact value（`configured=true/false` boolean）。

**结论**：PASS。✅

### 3.2 Transport Error 脱敏映射

- SEC：`_sec_transport_category` + `_sec_transport_safe_message` 实现六类封闭映射。
- CNINFO：`_cninfo_http_failure` + `_cninfo_protocol_error` 实现五类映射 + 协议分离。
- HKEX：`_hkexnews_http_failure` 五类对称映射。
- 所有 safe_message 均为固定中文文本，不含 URL、endpoint、raw payload、contact 或 path。
- `FinsDownloadProviderError.__init__` 调用 `_validate_public_text(safe_message)` 防止构造时注入。
- 日志仅含 `transport_category` enum value、`method`、attempt count，不含 `url=` 或 `error={exc}`。

**结论**：PASS。✅

### 3.3 Typed Rows / Count / Terminal Disposition / Omitted 不变量

- `FinsDownloadResultSummary.__post_init__` 强制 `discovered_count == sum(counts)`、`len(document_rows) == discovered_count`、各 disposition 的 row count 与对应 count 一致。
- `FinsDownloadPublicSummary.__post_init__` 二次校验：`len(document_rows) + omitted_count == discovered_count`、visible disposition counts ≤ total counts。
- `_terminal_disposition_from_counts`（owner）包含 `AssertionError` defensive guard。
- `_download_terminal_disposition`（public）与 owner 逻辑一致，基于已验证的 public counts。
- `empty_terminal_override` 允许零候选的 FAILED/CANCELLED，不允许 PARTIAL_FAILURE。
- 18 → 10 rows 投影测试覆盖 `omitted_count == 8`。

**结论**：PASS。✅

### 3.4 Strict Projection — 无 `.get()` / `getattr` / `str()` Coercion

- SEC/CN adapter 使用 `_required_sec_text`、`_required_cn_text`、`_required_cn_text_list`、`_optional_sec_text` 等严格 helper。
- 旧代码中的 `str(item.get("status", "")).strip()` 和 `_json_int(summary.get(...), ...)` 已全部删除。
- `_bounded_download_summary` 改为 `isinstance` 检查后直接返回 typed 实例（`ingestion_runtime.py:6036-6053`）。
- `FinsDownloadResultSummary` 的 re-export 从 `ingestion_runtime.__all__` 移除。
- 未知 status 直接 `ValueError` fail closed。

**结论**：PASS。✅

### 3.5 Storage Locator Query — Read-Only 相对路径

- `SourceDocumentRepositoryProtocol.get_source_document_locator` 返回 `PurePosixPath`。
- `FsSourceDocumentRepository` wrapper 委托 core。
- `_FsSourceDocumentMixin.get_source_document_locator` 在 publication guard 内验证 meta 存在 → `relative_to(workspace_root)` → `PurePosixPath`。
- `FinsDownloadDocumentResult.__post_init__` 强制 locator 不是绝对路径且不含 `..`。
- `FinsDownloadPublicDocument.__post_init__` 对 locator 字符串做 `_validate_safe_text` + `PurePosixPath` 二次检查。
- docstring 已正确列出 `ValueError` 作为可能的异常类型。

**结论**：PASS。✅

### 3.6 CLI / Wait Adapter 同一公共真源、LLM-Facing 自足

- Runtime 从 `_FinsDownloadResultSummary` 构造 `FinsDownloadPublicSummary`，CLI 和 wait adapter 均消费同一 `FinsResultSummary.download` / `.failure`。
- CLI `_print_terminal_business_summary` 检查 `result.download is not None` → `_print_download_summary`。
- Wait adapter `_completed_result_value` 在 `result.download is not None` 时使用 `result.download.to_json_value()`。
- Wait adapter `_failure_message` 构造自解释 JSON（含 `download` + `failure` 对象）。
- CLI 和 wait adapter 均不 import 私有 storage 模块（rg 确认零匹配 `import.*storage`、`glob`、`rglob`、`os.walk` 模式）。
- `to_json_value()` 返回自解释 JSON，字段名和值均为业务可读。

**结论**：PASS。✅

### 3.7 反向依赖、过度耦合、兼容 Re-Export/Shim

- `dayu.runtime` 不 import `dayu.fins` / `dayu.host` / `dayu.service` / `dayu.ui`（已有 CI static check）。
- `FinsDownloadResultSummary` 从 `ingestion_runtime` 移至 `download_contract`，所有 production/test import 直接指向新真源。
- `ingestion_runtime` 使用 `as _FinsDownloadResultSummary` 别名内部导入，`__all__` 不再导出旧名。
- 无兼容 wrapper、双 schema 或别名 shim。
- `_bounded_download_summary` 从"重新构造并校验"改为 `isinstance` 直接返回，消除旧兼容路径。
- 旧 `FinsDownloadResultSummary.written_document_ids` 字段改为 property（从 `document_rows` 派生）。
- CN workflow child→parent 导入方向与现有 `from cn_download_filing_workflow import run_cn_download_single_filing_stream` 一致，无反向依赖。

**结论**：PASS。✅

### 3.8 Public Safe Text Validator 绕过/误杀检查

- `_validate_safe_text`（direct_events）：阻止 `://`、内部治理标识（job_id、cursor、event sequence 等）、job ID pattern、绝对路径（POSIX + Windows）。
- `_validate_public_text`（download_contract）：阻止 `://`、`raw payload`、`provider payload`、绝对路径前缀。
- `FinsDownloadProviderError.__init__` 调用 `_validate_public_text(safe_message)`。
- `FinsPublicFailure.__post_init__` 调用 `_validate_safe_text(safe_message)` 和 `_validate_safe_text(retry_hint)`。
- `FinsDownloadPublicDocument.__post_init__` 对所有文本字段调用 `_validate_safe_text`。
- Locator 路径额外通过 `PurePosixPath.is_absolute()` + `".."` 检查。
- 未发现绕过路径。

**结论**：PASS。✅

### 3.9 SEC auxiliary 逐 helper 分类完整性

- Browse company HTTP / XML parse / fetch_submissions：typed error 原样传播，operation-fatal。
- SC13 `fetch_sc13_party_roles`：typed error 原样传播，operation-fatal。
- 三个 `_try_fetch_*` file-evidence helpers：typed error 传播 → `list_filing_files` → `sec_download_filing_workflow` 单 `FILING_FAILED` row。
- Historical submissions `fetch_json`：typed error 原样传播，operation-fatal。
- 6-K preview：`FinsDownloadProviderError` caught → safe log → `DOWNLOAD_FAILED` → per-filing FAILED row。
- Optional HEAD：metadata-only 缺省，不改 disposition。

**结论**：每条辅助路径均有明确的 typed 传播或 safe catch。PASS。✅

### 3.10 CN/HK `_is_cancel_requested` Pass-Through

- `cn_download_workflow.py:356-372`：直接 `return cancel_checker()`，无 wrapping。
- `CnDownloadCancelledError` 由 `cancel_checker` 抛出后，在 child（line 203/336）和 parent（line 278）显式 catch。
- `FinsDownloadProviderError` 和 `OSError` 原样传播到 runtime 的 typed failure projection。
- Docstring 明确记录异常传播语义。

**结论**：PASS。✅

### 3.11 Leakage 全面扫描

**`url=` in changed production diff**：
- `sec_downloader.py`：`source_url=` 和 `url=` 出现在 provider-private request descriptor 构造和 HTTP 调用中（不是日志/public projection）。这是 amendment §3.4 明确允许的："Internal source URLs may remain in provider-private request descriptors."
- `cninfo_downloader.py` 和 `hkexnews_downloader.py`：仅 `adjunct_url` / `source_url` 数据构造，不在日志/public projection 中。

**`str(exc)` / `message=str(exc)` in CN/HK boundary**：
- `cn_download_filing_workflow.py`、`cn_download_workflow.py`、`cn_download_rebuild.py`：零匹配。
- `ingestion_runtime.py` 的 3 处 `str(exc)` 均不在 download 路径（分别为 unsupported source save、preprocess、generic direct error fallback）。

**`error=` / raw exception in logs**：
- Changed files 零匹配 `log.*url`、`log.*error=.*exc` 模式。

**Contact canary / 绝对路径 / traceback / raw payload marker**：
- Changed production files 零匹配。

**结论**：PASS。✅

## 4. 测试与 Coverage 真实性

### 4.1 测试覆盖矩阵

根据 review-fix implementation 报告的验证结果：

| 指标 | 结果 |
|---|---|
| Pre-edit amendment union | 497 passed, 6 failed |
| Amendment union after implementation | 513 passed, 3 warnings |
| pyright | 0 errors, 0 warnings, 0 informations |
| Ruff check (changed files) | All checks passed |
| compileall | Passed |
| git diff --check | Passed |

6 个 pre-edit 失败的原因：
1. 4 个 CN workflow 失败 → child PDF/Docling catch 仍 emit `pdf_download_failed` 和 `str(exc)` → 已由 `project_cn_filing_failure` 修复。
2. 2 个 UNKNOWN transport 测试构造问题 → `httpx.HTTPError(message)` 不支持 `request=` keyword → 已在测试中修正。

### 4.2 单文件 Coverage

Review-fix implementation 报告（使用同一 affected-union coverage data，每个 production file 单独 `--fail-under=80`）：

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

全部 11 个 review-fix production files ≥ 80%。无 aggregate 百分比掩盖单文件不足。

### 4.3 关键断言覆盖

- 未配置 SEC UA → typed fail，HTTP call count 0，warning 恰好一次。
- 配置日志不含 identity；请求诊断不含 endpoint。
- Typed provider error 的 sensitive cause 不进入 runtime public result。
- SEC/CN row counts 从 strict typed rows 派生，unknown status fail closed。
- 18 → 10 rows 投影，`omitted_count == 8`。
- CLI 与 wait adapter 均消费同一 typed public object。
- Wait 失败结果同时携带 `download` + `failure` JSON 对象。
- Child PDF/Docling direct owner tests：provider/OSError/execution 三类异常 → helper 一次调用 → identical `(reason_code, reason_message)` pair → safe serialization → cancellation identity。
- Parent same-source reuse test：直接调用 `project_cn_filing_failure` 与 parent leak catch 输出完全一致。
- CN/HK transport matrix：timeout hierarchy ordering (TimeoutException before NetworkError)、4xx non-retryable + single request、5xx retryable、malformed JSON → PROTOCOL non-retryable。
- Rebuild producer direct call：零文档/匹配文档/失败文档/取消 → `missing_periods: []` always present。
- SEC auxiliary direct owner tests：browse/SC13/history propagation、file-evidence → filing-local FAILED、6-K continuation、HEAD metadata-only。

**结论**：测试覆盖真实 owner contract 行为，failure paths、boundary conditions、regression surfaces 均有覆盖。✅

## 5. Architecture / Semantic Ownership / Public Contract 检查

### 5.1 语义所有权

- `project_cn_filing_failure` 在 document-local failure owner（`cn_download_filing_workflow.py`）唯一定义，consumer（子 PDF/Docling catch + 父 leak catch）直接复用，无下游补齐、重猜或 fallback。
- `_candidate_failure_facts` 和 `_reason_code_from_exception` 已删除，消除重复真源。
- `_cninfo_http_failure` / `_hkexnews_http_failure` 在 downloader owner 处产生 typed failure，adapter/runtime 不重分类。
- SEC auxiliary helpers 在异常发生点传播 typed error，不在 caller 处用 `None`/`[]`/continue 补救。

### 5.2 Public Contract 边界

- `FinsDownloadPublicSummary` / `FinsPublicFailure` 是 CLI 与 wait adapter 的唯一公共真源。
- CLI 和 wait adapter 不 import 私有 storage、不扫描文件、不解析 raw dict 或 log。
- `FinsDownloadDocumentResult` (owner level) → bounded → `FinsDownloadPublicDocument` (public level) → `to_json_value()` (serialization)。省略只发生在 public projection，owner 保留完整 rows。

### 5.3 依赖方向

- `UI → Service → Fins Runtime → Fins Adapter → Fins Pipeline/Downloader`，方向单向。
- `dayu.runtime` 不 import Fins/Host/Engine/Service/UI。
- `cn_download_workflow.py` → `cn_download_filing_workflow.py` 的导入方向与既有 `run_cn_download_single_filing_stream` 导入一致。

### 5.4 无过度设计

- 未新增 shared failure module、capability protocol、generice repair engine、new schema field 或 observability platform。
- `project_cn_filing_failure` 是最小直接 helper（三段 isinstance + tuple 返回），无 dataclass/callback/facade。
- `_bounded_download_summary` 变为 pure `isinstance` guard，消除旧重新构造/校验逻辑。

**结论**：所有 semantic ownership 边界清晰，public contract 唯一同源，依赖方向单向，无过度设计。✅

## 6. Findings

未发现新的 material finding。

初审 10 个 finding 中：
- 6 个 accepted finding（R01、R02、R06、R07、R08→R02 升级、C01）全部正确闭合。
- 5 个 rejected finding（R03、R04、R05、R08、R09）均未被错误实现。
- `project_cn_filing_failure` 是唯一 source of truth，全仓仅一处定义，所有 consumer 直接复用。

## 7. Open Questions

无。初审、amendment plan review 与 stop-condition review 的所有 open questions 已解决。

## 8. Residual Risk

| 风险 | 严重度 | 说明 | Owner |
|---|---|---|---|
| 真实 CLI 和 real-provider execution 未运行 | 中 | 按 controller 要求，Slice 2 禁止真实 CLI/provider。真实动态网络分类与终端 screen 观察留给 DL-G gate。 | DL-G01~G05 |
| `_download_terminal_disposition` 与 `_terminal_disposition_from_counts` 逻辑重复 | 低 | 两函数实现相同逻辑，但一个在 `download_contract.py`（owner level，含 defensive guard），一个在 `direct_events.py`（public level，无 defensive guard）。差异由两个层次的 `__post_init__` 不变量分别保证正确性，不会产生实际 bug。 | 后续 slice 或 closeout 可考虑统一 |
| SEC 对 4xx 的 retry policy 与 CN/HK 不对称 | 低 | CN/HK 4xx 为 fail-fast non-retryable，SEC 4xx 走完整 retry loop。这是 amendment 明确记录的有意设计差异。 | 未来统一的 plan amendment（本 WU scope 外） |
| Parent SIGKILL 时 system-temp 残留 | 低 | Slice 3 的 Docling process cleanup 在本 Slice 未实现。 | Slice 3 |
| 三个 upstream `edgar` deprecation warnings | 低 | 无关 Slice 2 download 语义，不影响测试结果。 | Dependency-maintenance WU |

## 9. Final Conclusion

**PASS**

Slice 2 完整未提交 diff（基线 `da27b92a`）经独立严格 adversarial re-review：

- **初审 6 个 accepted finding（R01/R02/R06/R07/C01）全部闭合**，每个 finding 的修复均有直接代码证据支撑。
- **5 个 rejected finding（R03/R04/R05/R08/R09）均未被错误实现**，代码严格遵循 controller 裁决。
- **`project_cn_filing_failure` 是唯一 source of truth**，全仓一处定义，子 workflow 两处 catch + 父 workflow 一处 leak catch 直接复用，无 wrapper/facade/duplicate mapper。
- **`str(exc)` / `message=str(exc)` 零残留**于 CN/HK filing/workflow boundary。
- **URL/contact/absolute path/raw payload 零泄漏**于变更后的 production public projection 与日志。
- **CLI 与 wait adapter 共享同一 typed public truth source**，不 import 私有 storage、不扫描文件、不解析 raw dict。
- **所有 modified production files ≥ 80% 单文件 statement coverage**，关键 failure paths 均有 owner-level 测试覆盖。
- **无新增 correctness/stability/maintainability finding**。

Diff 质量达到 merge-ready 标准。未闭合 material finding 为零。

---

Output path: `docs/reviews/code-review-20260810-slice2-rereview-ds.md`
