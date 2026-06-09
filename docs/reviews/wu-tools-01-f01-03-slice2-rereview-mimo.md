# WU-TOOLS-01-F01-03 Slice 2 Fix Re-Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f01-03
- Base: main
- Timestamp: 20260609-144510
- Reviewer: AgentMiMo

### Included scope

- Slice 2 fix 后 dirty changes，重点核对 Controller accepted findings CTRL-S2-01 至 CTRL-S2-07

### Excluded scope

- CN/HK downloader、upload workflow、process workflow、CLI、Host/Engine 集成
- Deferred findings（CTRL-S2-D1 至 CTRL-S2-D3）

## Controller Accepted Findings Status

### CTRL-S2-01: SEC 6-K filtered rejected artifact 计入 persisted summary rejected_count

**状态：fixed**

- **证据**：`dayu/fins/pipelines/sec_pipeline.py:1516-1536` 新增 `_is_rejected_filing_result` 函数，判断条件为 `status == "rejected"` 或 (`status == "skipped"` 且 `skip_reason == "6k_filtered"` 或 `reason_code == "6k_filtered"`)。
- `_summary_from_pipeline_result`（行 1500）调用 `_is_rejected_filing_result` 统计 `rejected_count`。
- 常量 `_SEC_REASON_6K_FILTERED = "6k_filtered"` 在行 142 定义。
- OLD workflow status 语义未改写：6-K filtered filings 在 OLD 结果中仍为 `status="skipped"`。
- 测试 `test_sec_pipeline_download.py` 中有确定性测试证明 6-K filtered 产生 `rejected_count > 0`。

### CTRL-S2-02: `StubDownloader.list_filing_files` docstring 恢复

**状态：fixed**

- **证据**：`tests/fins/test_sec_pipeline_download.py:178` docstring 现为函数体第一个语句。`self.list_filing_files_call_count += 1` 已移至 docstring 之后。

### CTRL-S2-03: 死的 `_SpySourceRepository.download_files_stream` 删除

**状态：fixed**

- **证据**：`tests/fins/test_sec_pipeline_download_stream.py:190-203` `_SpySourceRepository` 仅保留 `has_filing_xbrl_instance` spy 方法。`download_files_stream` 已删除，无替代误导路径。生产流式路径从 `self._downloader` 获取 `download_files_stream`（sec_pipeline.py:1242），不从 `source_repository` 获取。

### CTRL-S2-04: `@pytest.mark.unit` 移除

**状态：fixed**

- **证据**：`tests/fins/test_sec_downloader.py` 中无 `pytest.mark` 使用（grep 返回 0 匹配）。pytest unknown marker warning 已消除。

### CTRL-S2-05: `_maybe_await` 及相关 import 删除

**状态：fixed**

- **证据**：`dayu/fins/pipelines/sec_pipeline.py` 中无 `_maybe_await` 定义或调用（grep 返回 0 匹配）。`inspect`、`Awaitable`、`TypeVar` import 已删除。

### CTRL-S2-06: `dayu/fins/pipelines/__init__.py` 新增中文包概览 docstring

**状态：fixed**

- **证据**：`dayu/fins/pipelines/__init__.py` 内容为 `"""财报生产摄取管线模块包。"""`，仅含中文包概览 docstring，无其他代码。

### CTRL-S2-07: persisted-summary adapter 责任边界说明

**状态：fixed**

- **证据**：
  - `FinsSourceDownloadAdapterResult.persisted_summary` docstring（ingestion_runtime.py:276-278）明确说明："adapter 对 source 文件、rejected artifact 以及必要的 processed reprocess 标记等仓储副作用负责，runtime 只记录摘要"。
  - `SecDownloadAdapter.download` 仍传递 `rebuild=False`（sec_pipeline.py:1448），未将 NEW `rebuild_processed` 映射到 OLD `SecPipeline.download(rebuild=...)`。
  - 新增测试 `test_start_download_persisted_summary_adapter_receives_rebuild_processed`（test_fins_ingestion_runtime.py:878）证明 persisted-summary adapter 接收并记录 `rebuild_processed=True`。

## Additional Checks

### CN/HK、upload/process、CLI、Host/Engine 反向依赖

**未引入**。`dayu/fins/` 中唯一引用 `dayu.host` 的文件为 `dayu/fins/ingestion/wait_adapter.py`（不在 Slice 2 dirty changes 中）。Slice 2 生产文件无 Host/Engine import。

### Any / type object / 无类型签名

**未新增**。Slice 2 涉及的生产文件（`dayu/fins/downloaders/`、`dayu/fins/pipelines/sec_pipeline.py`、`dayu/fins/pipelines/__init__.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/service_runtime.py`）和测试文件中无 `Any` 或 `: object` / `-> object` 类型注解。

### 控制侧验证

**通过**。

| 验证项 | 结果 |
|---|---|
| `pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q` | 113 passed, 3 warnings（edgartools deprecation） |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |
| targeted Any/object scan（Slice 2 文件） | 0 匹配 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- Live SEC network behavior 仍不在确定性测试范围内。
- Deferred findings（CTRL-S2-D1 stream failure/overwrite 覆盖、CTRL-S2-D2 helper 去重、CTRL-S2-D3 细粒度取消）仍为 deferred 状态，未在本轮 fix 中处理。

## Verdict

**fix-accepted**

- 7/7 Controller accepted findings 均为 **fixed**。
- 0 blocking findings。
- 0 新增 findings。
