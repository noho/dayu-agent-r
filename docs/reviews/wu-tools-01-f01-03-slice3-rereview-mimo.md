# WU-TOOLS-01-F01-03 Slice 3 Fix Re-Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f01-03
- Base: main
- Timestamp: 20260609-155355
- Reviewer: AgentMiMo

### Included scope

- Slice 3 fix 后 dirty changes，重点核对 Controller accepted findings CTRL-S3-01 至 CTRL-S3-06

### Excluded scope

- Deferred findings（CTRL-S3-D1 至 CTRL-S3-D3）
- upload/process/CLI、Host/Engine 集成

## Controller Accepted Findings Status

### CTRL-S3-01: CN/HK adapter factory defaults 分离

**状态：fixed**

- **证据**：`cn_pipeline.py:766-767` `build_cn_download_adapter` 使用 `CNINFO_DEFAULT_SLEEP_SECONDS`/`CNINFO_DEFAULT_MAX_RETRIES`；`cn_pipeline.py:812-813` `build_hk_download_adapter` 使用 `HKEXNEWS_DEFAULT_SLEEP_SECONDS`/`HKEXNEWS_DEFAULT_MAX_RETRIES`。
- 旧的 `DEFAULT_CN_HK_SLEEP_SECONDS`/`DEFAULT_CN_HK_MAX_RETRIES` combined constants 已移除。
- deterministic test：`test_cn_download_runtime.py:391` `test_cn_hk_adapter_factories_use_source_specific_downloader_defaults` 通过 monkeypatch 将 CN/HK defaults 设为不同值，断言各 factory 构建的 adapter pipeline 使用匹配的值（行 435-437）。

### CTRL-S3-02: 移除 unused ProcessorRegistry

**状态：fixed**

- **证据**：grep `ProcessorRegistry|processor_registry` 在 `cn_pipeline.py` 返回 0 匹配。`service_runtime.py:196-203` `build_cn_download_adapter` 和 `204-211` `build_hk_download_adapter` 调用均不传 `processor_registry`。
- SEC 不受影响：`service_runtime.py:189` `build_sec_download_adapter` 仍接收 `processor_registry=self.processor_registry`；`service_runtime.py:217` `FinsIngestionRuntime.create` 仍接收 `processor_registry`。

### CTRL-S3-03: cninfo_downloader stdlib lazy imports 上移

**状态：fixed**

- **证据**：`cninfo_downloader.py:34-35` `import datetime as dt` 和 `import hashlib` 现位于模块顶层 import 区域。`_sha256_hex` 和 `_utc_now_isoformat` 函数体内不再有 lazy import。

### CTRL-S3-04: CnDownloadCancelledError 移到 shared module

**状态：fixed**

- **证据**：`cn_download_models.py:77` 定义 `CnDownloadCancelledError(RuntimeError)`，`cn_download_models.py:189` 在 `__all__` 中导出。`cn_download_rebuild.py` 不再 import `cn_download_filing_workflow`，依赖方向正确。

### CTRL-S3-05: 英文 docstrings 中文化

**状态：fixed**

- **证据**：
  - `cn_download_pdf_gate.py:1-5`：中文模块 docstring；行 17 中文类 docstring；行 25-37 中文方法 docstring 含参数/返回/异常。
  - `cn_download_source_upsert.py:1-7`：中文模块 docstring。
  - `cn_download_staging.py:1-6`：中文模块 docstring；行 19-27 中文类 docstring 含属性说明。
- 业务分支未改。

### CTRL-S3-06: cn_download_pdf_gate.py 使用 absolute import

**状态：fixed**

- **证据**：`cn_download_pdf_gate.py:13` 为 `from dayu.fins.pipelines.cn_download_models import CnSourceProvider`（absolute import），不再使用 relative import。

## Additional Checks

### upload/process/CLI/Host/Engine 越界

**未引入**。`dayu/fins/pipelines/cn_*.py` 中 grep `from dayu.(host|engine|service|ui)` 返回 0 匹配。

### Any/type object 扩散

**未引入**。`dayu/fins/downloaders/*.py` 和 `dayu/fins/pipelines/cn_*.py` 中 grep `\bAny\b|: object\b|-> object\b` 均返回 0 匹配。

### 旧实现迁移语义未被重写

**确认**。CNInfo/HKEXNews downloader 业务逻辑、CN download workflow 编排、PDF gate/Docling 分离、rebuild 语义均未被修改。fix 仅涉及 defaults 分离、dead import 移除、import 上移、异常模块迁移、docstring 中文化、import 风格统一。

### upload 长事务边界未被触碰

**确认**。无 upload workflow 代码被引入或修改。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- Deferred findings（CTRL-S3-D1 broader test matrix、CTRL-S3-D2 helper de-duplication、CTRL-S3-D3 HKEXNews class docstring）仍为 deferred 状态。
- live CN/HK 网络行为仍不在确定性测试范围内。

## Validation

| 验证项 | 结果 |
|---|---|
| `pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q` | 112 passed, 3 warnings（edgartools deprecation） |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |
| targeted Any/object scan（Slice 3 文件） | 0 匹配 |
| boundary scan（upload/process/CLI/Host/Engine） | 0 匹配 |

## Verdict

**pass**

- 6/6 Controller accepted findings 均为 **fixed**。
- 0 blocking findings。
- 0 新增 findings。
- 可进入 controller adjudication。
