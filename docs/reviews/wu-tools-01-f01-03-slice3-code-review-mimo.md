# WU-TOOLS-01-F01-03 Slice 3 Code Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f01-03
- Base: main
- Timestamp: 20260609-152317
- Reviewer: AgentMiMo

### Included scope

- `dayu/fins/downloaders/cninfo_downloader.py`（新增）
- `dayu/fins/downloaders/hkexnews_downloader.py`（新增）
- `dayu/fins/downloaders/__init__.py`（dirty changes）
- `dayu/fins/pipelines/cn_*.py`（12 个新增文件）
- `dayu/fins/pipelines/download_events.py`（dirty changes）
- `dayu/fins/service_runtime.py`（dirty changes）
- `tests/fins/test_cninfo_downloader.py`（新增）
- `tests/fins/test_hkexnews_downloader.py`（新增）
- `tests/fins/test_cn_download_workflow.py`（新增）
- `tests/fins/test_cn_download_runtime.py`（新增）
- `tests/fins/test_cn_pipeline.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`（dirty changes）
- `dayu/fins/README.md`、`tests/README.md`（dirty changes）
- `docs/reviews/wu-tools-01-f01-03-slice3-implementation-codex.md`

### Excluded scope

- SEC downloader/pipeline（Slice 2 已完成）
- upload workflow、process workflow、CLI、Host/Engine 集成（明确不在 Slice 3）

### Parallel review coverage

- Subagent 1：`dayu/fins/downloaders/`（CNInfo/HKEXNews downloader 语义保留、AGENTS 硬约束、HK defaults）
- Subagent 2：`dayu/fins/pipelines/cn_*.py`（CN workflow 语义保留、rebuild 边界、facade 设计、PDF gate/Docling）
- Subagent 3：`dayu/fins/service_runtime.py`（runtime registration、CN/HK factory 参数、SEC 不被破坏）
- Subagent 4：测试文件（network-free、覆盖场景、AGENTS 硬约束）

## Findings

### S3-01-未修复-中-`ProcessorRegistry` 被导入、存储但从未在下载路径中消费

- **入口/函数**: `CnPipeline.__init__`、`build_cn_download_adapter`、`build_hk_download_adapter`
- **文件(行号)**: `dayu/fins/pipelines/cn_pipeline.py:21, 170, 211-212, 235`
- **输入场景**: 构造 `CnPipeline` 或调用 adapter factory 时
- **实际分支**: `processor_registry` 作为 required parameter 传入，存储为 `self._processor_registry`
- **预期行为**: 下载 facade 不应引入 process 层依赖
- **实际行为**: `self._processor_registry` 仅在行 235 赋值，从未被读取。`CnDownloadWorkflowHost` Protocol 不暴露该字段，下载 workflow 从未访问它
- **直接证据**: grep `self._processor_registry[^=]` 仅返回行 235（赋值）
- **影响**: 调用方（runtime、测试）必须构造 `ProcessorRegistry` 实例即使它未被使用；违反窄 download facade 设计意图；引入对 `dayu.documents.processors.processor_registry` 的不必要耦合
- **建议改法和验证点**: 从 `CnPipeline.__init__`、`build_cn_download_adapter`、`build_hk_download_adapter` 签名中移除 `processor_registry`；后续 Slice 需要时再添加
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Blocking**: 否（不影响运行时行为，但违反窄 facade 设计）
- **建议裁决**: accepted

### S3-02-未修复-中-`cninfo_downloader.py` 标准库 lazy import 无充分理由

- **入口/函数**: `_sha256_hex`、`_utc_now_isoformat`
- **文件(行号)**: `dayu/fins/downloaders/cninfo_downloader.py:1059, 1067`
- **输入场景**: 任何调用这两个函数的路径
- **实际分支**: `import hashlib` 和 `import datetime as dt` 位于函数体内
- **预期行为**: 标准库无副作用，应在模块顶层 import
- **实际行为**: `hashlib` 和 `datetime` 被 lazy import 在函数体内；对比 `hkexnews_downloader.py` 正确地在顶层 import `hashlib`（行 12）
- **直接证据**: 行 1059 `import hashlib`、行 1067 `import datetime as dt` 均在函数体内
- **影响**: 违反 AGENTS.md "禁止胶水 seam，使用 lazy import 必须有充分理由"
- **建议改法和验证点**: 将 `import hashlib` 和 `import datetime as dt` 移到模块顶层 import 区域
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Blocking**: 否
- **建议裁决**: accepted

### S3-03-未修复-低-两个 downloader 的 `_utc_now_isoformat` 实现不一致且未抽取共享

- **入口/函数**: `_utc_now_isoformat`
- **文件(行号)**: `cninfo_downloader.py:1064-1069` vs `hkexnews_downloader.py:1230-1243`
- **输入场景**: 生成时间戳时
- **实际分支**: CN 用 `datetime.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()`，HK 用 `time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())`
- **预期行为**: 相同语义的重复逻辑应抽取到共享模块
- **实际行为**: 两个同名函数独立定义，实现路径不同
- **直接证据**: 两处定义的函数体不同但输出语义等价
- **影响**: 违反 AGENTS.md "重复逻辑必须抽取"
- **建议改法和验证点**: 抽取到 `cn_download_models.py` 或共享工具模块
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

### S3-04-未修复-低-`_HeadMeta` 和 `JsonValue`/`JsonScalar` 类型重复定义

- **入口/函数**: 模块级类型定义
- **文件(行号)**: `cninfo_downloader.py:55-59, 837-842` vs `hkexnews_downloader.py:36-39, 167-173`
- **输入场景**: 无（类型定义）
- **实际分支**: 两个模块各自独立定义相同的 `_HeadMeta` dataclass 和 `JsonValue`/`JsonScalar` TypeAlias
- **预期行为**: 共享类型应抽取到公共模块
- **实际行为**: 完全相同的类型定义重复出现
- **直接证据**: 字段和结构完全相同
- **影响**: 违反 DRY 原则
- **建议改法和验证点**: 抽取到 `cn_download_models.py`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

### S3-05-未修复-低-`HkexnewsDiscoveryClient` 类 docstring 过于简略

- **入口/函数**: `HkexnewsDiscoveryClient` 类
- **文件(行号)**: `dayu/fins/downloaders/hkexnews_downloader.py:210-211`
- **输入场景**: 查看类文档
- **实际分支**: 类 docstring 仅一行 `"披露易 HK discovery / 下载客户端。"`
- **预期行为**: 类 docstring 应覆盖职责范围、协议实现说明、构造参数注入能力
- **实际行为**: 仅 9 个字；对比 `CninfoDiscoveryClient`（行 169-176）有完整 6 行 docstring
- **直接证据**: 行 211 的 docstring 内容
- **影响**: 违反 AGENTS.md "类与模块应提供中文概览 docstring"
- **建议改法和验证点**: 补充职责范围、协议实现、构造注入等说明
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

### S3-06-未修复-低-`cn_download_pdf_gate.py` 使用相对 import，与其他 11 个文件不一致

- **入口/函数**: 模块级 import
- **文件(行号)**: `dayu/fins/pipelines/cn_download_pdf_gate.py:13`
- **输入场景**: import 风格一致性
- **实际分支**: `from .cn_download_models import CnSourceProvider`（相对 import）
- **预期行为**: 同包内应使用绝对 import 以保持 grep-ability 和一致性
- **实际行为**: 其他 11 个 `cn_*.py` 文件均使用绝对 import
- **直接证据**: 对比 `cn_download_filing_workflow.py:19` 使用 `from dayu.fins.pipelines.cn_download_models import ...`
- **影响**: 纯风格问题，无功能影响
- **建议改法和验证点**: 改为 `from dayu.fins.pipelines.cn_download_models import CnSourceProvider`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

## 未发现实质性问题的审查点

以下审查点经 subagent 深度走读，未发现实质性问题：

### 迁移不是重写

- CNInfo/HKEXNews downloader 完整保留 OLD 业务语义：巨潮 stockList 解析、hisAnnouncement 翻页、category 分类映射、标题黑名单/amended 优先、PDF magic bytes 校验；披露易 active/inactive stock list、title search、语言策略、多 STOCK_CODE 匹配、英文公告过滤、中文数字年份解析、季度财期推断
- CN download workflow 正确编排：ticker normalization -> form/window resolution -> company meta upsert -> candidate discovery -> overwrite cleanup -> per-filing stage machine -> summary aggregation
- `_select_candidates_for_a4` 按期间业务窗口（FY 5 年、interim 2 年）匹配 OLD 行为
- 所有业务规则以模块级常量承载，未做简化或省略

### cn_download_rebuild.py 仅本地 source meta rebuild

- `rebuild_cn_download_artifacts` 仅读取已有 source documents 并写回 meta
- 不 import upload、process、docling runtime 或 CLI
- 模块 docstring 明确声明："不访问巨潮、披露易或 Docling"

### build_cn_filing_ids 迁移合理性

- `build_cn_filing_ids` 从 OLD upload helper 迁入 `cn_form_utils`
- 消费方为 `cn_download_filing_workflow.py:128` 和 `cn_download_workflow.py:741`，均为 download direct dependency
- 纯 hash-based ID generator，无副作用

### cn_pipeline.py 窄 download facade

- `CnPipeline` 仅暴露 `download()` 和 `download_stream()` 作为 public methods
- `CnDownloadAdapter.download()` 返回 `persisted_summary`，正确维护同步协议
- `rebuild_processed` 未错误映射到 OLD `rebuild`（行 606 硬编码 `rebuild=False`，docstring 明确说明语义边界）

### DefaultFinsRuntime registration

- 正确注册全部 6 个 `(source, market)` 组合：`(sec,US)`、`(auto,US)`、`(cninfo,CN)`、`(auto,CN)`、`(hkexnews,HK)`、`(auto,HK)`
- SEC 注册未被破坏——新增注册是纯增量
- HK adapter 未误用 CN defaults：HKEXNews 有独立 `DEFAULT_USER_AGENT`（`"DayuAgent/1.0 (+hk-download)"`）、`DEFAULT_SLEEP_SECONDS`（0.3）、`DEFAULT_MAX_RETRIES`（3）；`CnPipeline.__init__` 按 discovery client 分派正确的 user_agent

### PDF gate/Docling

- Docling conversion 不在 PDF gate lease 内执行
- `_download_report_pdf_with_gate` 仅包裹 PDF download，Docling 转换在 gate `with` block 外通过 `asyncio.to_thread` 执行
- 默认 conversion 通过 `dayu.documents.docling_runtime`，不依赖 upload service

### storage-only writes、ticker_normalization

- downloader 唯一写操作为临时文件，不涉及 Fins workspace
- 业务数据写入通过 repository 协议完成
- 两个 downloader 均不 import `dayu.fins.storage` 或 `dayu.fins.ticker_normalization`

### Host/Engine 反向依赖

- 全部 dirty changed files 无 `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui` import

### AGENTS 硬约束

- 中文 docstring：所有新函数/类/方法均有中文 docstring
- 禁止 Any/object：全部生产文件和测试文件均无 `Any` 或 `: object` 类型注解
- 无魔法数字/字符串：所有常量以 `Final` 标注并命名
- 无兼容 wrapper：无 `__getattr__` lazy import、无 deprecation shim

### Tests

- network-free：全部 6 个测试文件通过 httpx.MockTransport / fake discovery client / fake adapter 隔离网络
- 覆盖成功/失败/重复/overwrite：downloader 级覆盖 304 跳过、HTTP 失败、PDF magic bytes 校验；workflow 级覆盖 fast-skip、PDF gate 不覆盖 Docling、missing candidate
- runtime registration：`test_default_runtime_registers_production_download_adapters` 验证全部 6 个 adapter 映射和 identity

## Open Questions

无。

## Residual Risk

1. **`overwrite=True` 重下载路径缺少 dedicated workflow-level 测试**：当前 workflow 测试覆盖 fast-skip（`overwrite=False`），但未测试已提交文档在 `overwrite=True` 时强制重下载的行为。downloader 级有 `overwrite=True` 测试，但 workflow event sequence 级未覆盖。建议补充。
2. **HK workflow event sequence 未在 workflow-level 测试中覆盖**：HK 路径在 pipeline facade 和 runtime 级有测试，但 workflow 级的事件序列（PIPELINE_STARTED -> COMPANY_RESOLVED -> ... -> PIPELINE_COMPLETED）未验证。
3. **workflow-level 中途失败传播未测试**：downloader 级有失败测试，但 workflow 集成级的失败事件传播、最终事件序列、部分状态清理未覆盖。
4. **`ProcessorRegistry` dead import（S3-01）**：需从 factory 签名中移除以保持窄 facade 设计。
5. **live SEC/CN/HK 网络行为仍不在确定性测试范围内**。

## Verdict

**pass-with-findings**

- 0 blocking findings
- 2 个中 severity findings（S3-01 ProcessorRegistry dead import、S3-02 标准库 lazy import）
- 4 个低 severity findings（S3-03-S3-06：类型重复、docstring 简略、import 风格不一致）
- 迁移语义保留正确、boundary 清洁、registration 正确、PDF gate/Docling 设计合理、AGENTS 硬约束遵守
