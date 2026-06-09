# WU-TOOLS-01-F01-03 Slice 2 Fix Re-Review — AgentDS

## Scope

- **Mode**: current changes (fix re-review)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice2-rereview-ds.md`
- **Reviewed scope**: 仅 Slice 2 fix gate 涉及的 CTRL-S2-01 至 CTRL-S2-07 accepted findings
- **Excluded scope**: deferred findings (CTRL-S2-D1/D2/D3/D4), rejected findings (CTRL-S2-R1), CN/HK/upload/process/CLI, Host/Engine 内部
- **Source documents**:
  - `docs/reviews/wu-tools-01-f01-03-slice2-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-03-slice2-fix-codex.md`

## Verdict

**pass** — 所有 7 个 CTRL-S2 accepted findings 均已 fixed；0 blocking findings；0 new findings。

## CTRL-S2 Finding Status

### CTRL-S2-01: SEC persisted summary 统计 6-K filtered rejected artifact

**Status: fixed**

- **入口**: `_summary_from_pipeline_result` / `_is_rejected_filing_result`
- **文件**: `dayu/fins/pipelines/sec_pipeline.py:140-142,1492-1501,1528-1536`
- **验证证据**:
  1. 新增模块级常量 `_SEC_STATUS_DOWNLOADED`, `_SEC_STATUS_REJECTED`, `_SEC_STATUS_SKIPPED`, `_SEC_REASON_6K_FILTERED`（lines 139-142），消除魔法字符串
  2. `_is_rejected_filing_result(item)` (line 1528-1536) 判断 `status == "rejected"` 或（`status == "skipped"` 且 `skip_reason/reason_code == "6k_filtered"`），正确覆盖 OLD SEC 6-K 拒绝 artifact 的两种表示
  3. `_summary_from_pipeline_result` 中 `rejected_count` 通过调用 `_is_rejected_filing_result` 递增 (line 1500)，不再依赖不存在的 `status == "rejected"` 字面量
  4. OLD workflow 状态语义未改写：`sec_download_filing_workflow.py` 中 6-K filtered 的 filing result 仍使用 `"status": "skipped"`（lines 206, 231, 277, 377）
  5. 新测试 `test_sec_download_adapter_counts_6k_filtered_as_rejected_in_persisted_summary` (`test_sec_pipeline_download.py:1247-1315`) 使用 SEC pipeline adapter + 境外 issuer submissions + 6-K 文本 stub，断言 `summary.rejected_count == 1, summary.skipped_count == 1, summary.downloaded_count == 0`

### CTRL-S2-02: `StubDownloader.list_filing_files` docstring 修复

**Status: fixed**

- **入口**: `StubDownloader.list_filing_files`
- **文件**: `tests/fins/test_sec_pipeline_download.py:178-196`
- **验证证据**:
  1. `self.list_filing_files_call_count += 1` 位于 line 196，在 docstring（lines 178-194）之后
  2. Python 解释器现在将 lines 178-194 的三引号字符串识别为该函数的 `__doc__`
  3. 已有测试 `list_filing_files_call_count == 0` 断言 (lines 814, 1049) 继续通过，功能等价

### CTRL-S2-03: 删除死 `_SpySourceRepository.download_files_stream`

**Status: fixed**

- **入口**: `_SpySourceRepository`
- **文件**: `tests/fins/test_sec_pipeline_download_stream.py:190-203`
- **验证证据**:
  1. `_SpySourceRepository` 类仅保留 `has_filing_xbrl_instance` spy 方法 (line 199)，不再定义 `download_files_stream`
  2. 全文搜索 `_SpySourceRepository.*download_files_stream` 无匹配
  3. 无替代误导路径；流式下载路径仍通过 `StubDownloader.download_files_stream` / `StreamStubDownloader.download_files_stream` 覆盖

### CTRL-S2-04: 移除 `@pytest.mark.unit` 装饰器

**Status: fixed**

- **入口**: 4 个测试函数
- **文件**: `tests/fins/test_sec_downloader.py`
- **验证证据**:
  1. `rg 'pytest.mark.unit' tests/fins/test_sec_downloader.py` 无匹配 — 4 个装饰器已全部移除
  2. pytest 输出仅 3 warnings，全部为 edgartools deprecation——无 `PytestUnknownMarkWarning`
  3. 未修改 `pyproject.toml` markers 注册表

### CTRL-S2-05: 删除 `sec_pipeline.py` 中未使用的 `_maybe_await`

**Status: fixed**

- **入口**: 模块级 `_maybe_await` + 相关 import
- **文件**: `dayu/fins/pipelines/sec_pipeline.py`
- **验证证据**:
  1. `rg '_maybe_await' dayu/fins/pipelines/sec_pipeline.py` 无匹配 — helper 已删除
  2. `rg 'import inspect|Awaitable|TypeVar' dayu/fins/pipelines/sec_pipeline.py` 无匹配 — 专属 import 已删除
  3. 其他 pipeline 模块中的 `_maybe_await` 未被删除（controller 裁决为 deferred CTRL-S2-D2），符合 fix scope

### CTRL-S2-06: 新增 `dayu/fins/pipelines/__init__.py`

**Status: fixed**

- **入口**: 包初始化文件
- **文件**: `dayu/fins/pipelines/__init__.py`
- **验证证据**:
  1. 文件内容仅一行中文包概览 docstring: `"""财报生产摄取管线模块包。"""`
  2. 未导入任何模块、未定义任何符号，仅满足 CLAUDE.md "模块应提供中文概览 docstring" 要求

### CTRL-S2-07: 澄清 persisted-summary adapter 对 `rebuild_processed` 的责任边界

**Status: fixed**

- **入口**: `FinsDownloadRequest`, `FinsSourceDownloadAdapterResult`, `SecDownloadAdapter.download`
- **文件**:
  - `dayu/fins/ingestion_runtime.py:143-145` — `FinsDownloadRequest.rebuild_processed` docstring 补充说明 adapter 不得假设等同于来源侧本地重建开关
  - `dayu/fins/ingestion_runtime.py:276-278` — `FinsSourceDownloadAdapterResult.persisted_summary` docstring 明确 adapter 对 source 文件、rejected artifact 及 processed reprocess 标记等仓储副作用负责
  - `dayu/fins/pipelines/sec_pipeline.py:1423-1428` — `SecDownloadAdapter.download` docstring 明确 `request.rebuild_processed` 不映射为 OLD `SecPipeline.download(rebuild=...)`，OLD `rebuild` 仅表示本地 source meta 重建
  - `dayu/fins/pipelines/sec_pipeline.py:1448` — `rebuild=False` 硬编码保持，未将 NEW `rebuild_processed` 映射到 OLD `rebuild`
  - `tests/fins/test_fins_ingestion_runtime.py:878-904` — 新测试 `test_start_download_persisted_summary_adapter_receives_rebuild_processed` 使用 fake `_PersistedSummaryDownloadAdapter` 验证：
    - `rebuild_processed=True` 传递到 adapter request
    - request summary 记录 `rebuild_processed: True`
    - adapter 请求对象接收 `rebuild_processed=True`

## 无新增 Findings

- **CN/HK, upload/process, CLI 边界**: `rg 'from dayu\.(host|engine)|cn_download|hk_download|upload_workflow|process_workflow'` 在 `dayu/fins/downloaders/` 和 `dayu/fins/pipelines/` 中无匹配
- **Any / type object**: targeted scan 仅命中 4 处 `type: ignore[assignment]`（test_sec_downloader.py 中 monkeypatch 私有 `_client` 属性的预存测试写法），非新增
- **pyright**: 0 errors
- **pytest unknown marker**: 0 warnings（原 4 条 `unit` marker 警告已消失）
- **git diff --check**: 通过

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest (4 测试文件) | 113 passed, 3 warnings (仅 edgartools deprecation) |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `pytest.mark.unit` 残留 | 0 |
| CN/HK/upload/process/CLI 引入 | 0 |
| Host/Engine 反向依赖 | 0 |
| `Any`/type `object` 新增 | 0 |

## Open Questions

无。

## Residual Risk

- `_is_rejected_filing_result` 通过 `skip_reason` 与 `reason_code` 双重匹配 `"6k_filtered"` 识别 SEC 6-K 拒绝 artifact。若未来 OLD workflow 变更 skip_reason 命名，该函数需同步更新；但变更受 controller 保护（不得重写 OLD workflow 语义）。
- deferred findings（CTRL-S2-D1/D2/D3）未在本次 fix gate 处理，残留风险与原 review 一致。
