# WU-TOOLS-01-F01-03 Slice 3 Fix Re-Review — AgentDS

## Scope

- **Mode**: current changes (fix re-review)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice3-rereview-ds.md`
- **Reviewed scope**: 仅 Slice 3 fix gate 涉及的 CTRL-S3-01 至 CTRL-S3-06 accepted findings
- **Excluded scope**: deferred findings (CTRL-S3-D1/D2/D3), SEC pipeline, upload/process/CLI/Host/Engine
- **Source documents**:
  - `docs/reviews/wu-tools-01-f01-03-slice3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-03-slice3-fix-codex.md`

## Verdict

**pass** — 全部 6 个 CTRL-S3 accepted findings 均已 fixed；0 blocking findings；0 new findings。

---

## CTRL-S3 Finding Status

### CTRL-S3-01: CN/HK adapter factory defaults 分离

**Status: fixed**

- **文件**: `dayu/fins/pipelines/cn_pipeline.py:21-32, 726-737, 766-767, 772-815`
- **验证证据**:
  1. 导入各自下载器的常量，使用别名隔离：
     - `from dayu.fins.downloaders.cninfo_downloader import DEFAULT_SLEEP_SECONDS as CNINFO_DEFAULT_SLEEP_SECONDS, DEFAULT_MAX_RETRIES as CNINFO_DEFAULT_MAX_RETRIES` (lines 22-26)
     - `from dayu.fins.downloaders.hkexnews_downloader import DEFAULT_SLEEP_SECONDS as HKEXNEWS_DEFAULT_SLEEP_SECONDS, DEFAULT_MAX_RETRIES as HKEXNEWS_DEFAULT_MAX_RETRIES` (lines 27-32)
  2. `build_cn_download_adapter` (lines 766-767): 使用 `CNINFO_DEFAULT_SLEEP_SECONDS` / `CNINFO_DEFAULT_MAX_RETRIES`
  3. `build_hk_download_adapter` (lines 812-813): 使用 `HKEXNEWS_DEFAULT_SLEEP_SECONDS` / `HKEXNEWS_DEFAULT_MAX_RETRIES`
  4. 新测试 `test_cn_hk_adapter_factories_use_source_specific_downloader_defaults` (`test_cn_download_runtime.py:391-438`): monkeypatch 两组默认值为不同值（CN: 0.11/7, HK: 0.22/9），断言各自 adapter 的 pipeline sleep_seconds/max_retries 匹配对应下载器常量

### CTRL-S3-02: 移除 CN/HK download facade 中未使用的 `ProcessorRegistry`

**Status: fixed**

- **文件**:
  - `dayu/fins/pipelines/cn_pipeline.py` — `CnPipeline.__init__`、`build_cn_download_adapter`、`build_hk_download_adapter`
  - `dayu/fins/service_runtime.py:196-211`
- **验证证据**:
  1. `rg 'processor_registry' dayu/fins/pipelines/cn_pipeline.py` 无匹配 — 参数已从 `CnPipeline.__init__` 签名和构造函数体中移除
  2. `build_cn_download_adapter` 签名 (line 726-737) 无 `processor_registry` 参数
  3. `build_hk_download_adapter` 签名 (line 772-783) 无 `processor_registry` 参数
  4. `service_runtime.py:196-211` CN/HK adapter factory 调用不再传 `processor_registry`
  5. SEC pipeline `build_sec_download_adapter(..., processor_registry=...)` 和 `FinsIngestionRuntime.create(..., processor_registry=...)` 未改动

### CTRL-S3-03: CNInfo downloader stdlib lazy imports 上移至模块顶层

**Status: fixed**

- **文件**: `dayu/fins/downloaders/cninfo_downloader.py:34-35`
- **验证证据**:
  1. `import datetime as dt` (line 34) — 模块顶层
  2. `import hashlib` (line 35) — 模块顶层
  3. `_sha256_hex` 和 `_utc_now_isoformat` 函数体内不再有 lazy import，行为不变

### CTRL-S3-04: `CnDownloadCancelledError` 移至 `cn_download_models.py`

**Status: fixed**

- **文件**:
  - `dayu/fins/pipelines/cn_download_models.py:77-78` — 异常定义与 `__all__` 导出
  - `dayu/fins/pipelines/cn_download_filing_workflow.py:21` — 改为从 `cn_download_models` 导入
  - `dayu/fins/pipelines/cn_download_rebuild.py:20` — 改为从 `cn_download_models` 导入，不再依赖 `cn_download_filing_workflow`
- **验证证据**:
  1. `CnDownloadCancelledError(RuntimeError)` 定义为 `cn_download_models.py:77`，docstring: "CN/HK 下载工作流内部取消控制流异常"
  2. `cn_download_filing_workflow.py:21`: `from dayu.fins.pipelines.cn_download_models import (..., CnDownloadCancelledError, ...)` — 从 models 导入
  3. `cn_download_rebuild.py:20`: `from dayu.fins.pipelines.cn_download_models import (..., CnDownloadCancelledError, ...)` — 从 models 导入，不再依赖 filing_workflow
  4. 取消行为不变：`cn_download_filing_workflow.py:818` 仍 `raise CnDownloadCancelledError("操作已被取消")`，`cn_download_rebuild.py:294` 仍 `except CnDownloadCancelledError`

### CTRL-S3-05: 三个 CN 模块英文 docstring 中文化

**Status: fixed**

- **文件**:
  - `dayu/fins/pipelines/cn_download_pdf_gate.py`
  - `dayu/fins/pipelines/cn_download_source_upsert.py`
  - `dayu/fins/pipelines/cn_download_staging.py`
- **验证证据**:
  1. `cn_download_pdf_gate.py:1-6`: 模块 docstring 中文——"CN/HK PDF 下载段 gate 协议。本模块只定义 Fins pipeline 需要的窄协议与空实现，不依赖 Host、Service..."
  2. `cn_download_pdf_gate.py:17, 27-36, 44, 52-62`: 类/函数 docstring 中文化，参数/返回/异常段使用"参数:"、"返回:"、"异常:"标签
  3. `cn_download_source_upsert.py:1-7`: 模块 docstring 中文——"CN/HK 下载成功后的 source document commit 真源。本模块负责把已经落盘的 PDF 与 Docling JSON 提交为完成态 source meta..."
  4. `cn_download_staging.py:1-6`: 模块 docstring 中文——"CN/HK 下载链路的中断恢复探测。本模块只通过 ``DocumentBlobRepositoryProtocol`` 读取已落盘文件状态，不写入任何仓储..."
  5. 业务分支未改

### CTRL-S3-06: `cn_download_pdf_gate.py` 使用 absolute import

**Status: fixed**

- **文件**: `dayu/fins/pipelines/cn_download_pdf_gate.py:13`
- **验证证据**:
  1. `from dayu.fins.pipelines.cn_download_models import CnSourceProvider` — 绝对导入，与其他 CN pipeline 模块一致
  2. 无相对 import 残留（`rg 'from \.'` 无匹配）

---

## 新增 Findings

无。targeted type scan (`Any`/`object`)、boundary scan (Host/Engine/upload/process/CLI)、docstring 复核均无新增问题。

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest (6 测试文件) | 112 passed, 3 warnings (仅 edgartools deprecation) |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `Any`/type `object` 扩散 | 0 |
| Host/Engine/upload/process/CLI 引入 | 0 |
| 旧实现语义被重写 | 无 |
| upload 长事务边界被触碰 | 无 |

## Residual Risk

- deferred findings (CTRL-S3-D1/D2/D3) 未在本次 fix gate 处理，残留风险与原始 Slice 3 reviews 一致。
