# WU-TOOLS-01-F01-03 Slice 2 Code Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f01-03
- Base: main
- Timestamp: 20260609-142607
- Reviewer: AgentMiMo

### Included scope

- `dayu/fins/downloaders/`（SEC downloader 迁移）
- `dayu/fins/pipelines/`（SEC download workflow 迁移）
- `dayu/fins/ingestion_runtime.py`（dirty changes：adapter request/result 新增字段、persisted_summary short-circuit）
- `dayu/fins/service_runtime.py`（dirty changes：DefaultFinsRuntime 注册 SEC adapter）
- `tests/fins/test_sec_downloader.py`（新增）
- `tests/fins/test_sec_pipeline_download.py`（新增）
- `tests/fins/test_sec_pipeline_download_stream.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`（dirty changes）
- `dayu/fins/README.md`、`tests/README.md`（dirty changes）
- `docs/reviews/wu-tools-01-f01-03-slice2-implementation-codex.md`

### Excluded scope

- CN/HK downloader、upload workflow、process workflow、CLI、Host/Engine 集成（明确不在 Slice 2）
- `docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、`docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`（设计/控制真源，仅作参照）

### Parallel review coverage

- Subagent 1：`dayu/fins/downloaders/`（SEC-only boundary、OLD 迁移证据、AGENTS 硬约束、adapter 设计）
- Subagent 2：`dayu/fins/pipelines/`（SEC-only boundary、OLD 迁移证据、AGENTS 硬约束、runtime registration、storage-only writes、double write）
- Subagent 3：`dayu/fins/ingestion_runtime.py` + `dayu/fins/service_runtime.py`（runtime 集成、registration、cancellation、AGENTS 硬约束）
- Subagent 4：测试文件（network-free、覆盖场景、AGENTS 硬约束、marker warnings）

## Findings

### S2-01-未修复-中-docstring 错位导致函数无 docstring

- **入口/函数**: `StubDownloader.list_filing_files`
- **文件(行号)**: `tests/fins/test_sec_pipeline_download.py:167`
- **输入场景**: 任何查看该函数 docstring 的工具链或开发者
- **实际分支**: `self.list_filing_files_call_count += 1` 是函数体第一个语句
- **预期行为**: docstring 应为函数体第一个语句
- **实际行为**: 三引号字符串在 `+= 1` 之后，Python 不将其识别为 docstring，`help()` 和工具链无法提取
- **直接证据**: 行 167 `self.list_filing_files_call_count += 1` 在行 168 `"""返回固定远端文件列表。` 之前
- **影响**: 违反 AGENTS.md "函数必须提供完整中文 docstring"；工具链无法提取函数文档
- **建议改法和验证点**: 将 `self.list_filing_files_call_count += 1` 移到 docstring 之后
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Blocking**: 否（AGENTS 约束违反，不影响运行时行为）
- **建议裁决**: accepted

### S2-02-未修复-中-`_SpySourceRepository.download_files_stream` 为死代码

- **入口/函数**: `_SpySourceRepository.download_files_stream`
- **文件(行号)**: `tests/fins/test_sec_pipeline_download_stream.py:205-226`
- **输入场景**: 任何测试执行路径
- **实际分支**: `SecPipeline.download_stream` 从 `self._downloader` 获取 `download_files_stream`（sec_pipeline.py:1242），不从 `source_repository` 获取
- **预期行为**: 测试 stub 只保留实际被调用的方法
- **实际行为**: `_SpySourceRepository.download_files_stream` 已定义但从未被调用；唯一使用 `_SpySourceRepository` 的测试（行 310）仅验证 `has_filing_xbrl_instance_calls`
- **直接证据**: sec_pipeline.py:1242 `download_stream_func = getattr(self._downloader, "download_files_stream", None)`；行 310 测试不调用 `download_files_stream`
- **影响**: 误导读者认为 `source_repository` 参与流式下载；违反 AGENTS.md "模块间依赖最小化"
- **建议改法和验证点**: 删除 `_SpySourceRepository.download_files_stream` 方法及其相关 import
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Blocking**: 否（死代码不影响运行时行为）
- **建议裁决**: accepted

### S2-03-未修复-中-`download_stream` 缺少 failure path 和 overwrite 测试

- **入口/函数**: `SecPipeline.download_stream`
- **文件(行号)**: `tests/fins/test_sec_pipeline_download_stream.py`（全文）
- **输入场景**: 流式下载中途失败、`overwrite=True`、多文件混合成功/失败
- **实际分支**: 当前 4 个测试仅覆盖成功、skip、XBRL 回填、同步聚合
- **预期行为**: 测试应覆盖 failure path（`download_files_stream` 抛异常）、`overwrite=True`、部分成功部分失败
- **实际行为**: 缺少上述场景的测试
- **直接证据**: 文件中无 `overwrite=True` 的测试用例；无 `DownloaderEvent(event_type="file_failed")` 的测试；无 stream 内部异常的测试
- **影响**: 流式下载的失败路径和覆盖写路径未被验证，回归风险
- **建议改法和验证点**: 补充 3 个测试：stream 中途异常、overwrite=True 正确覆盖、多文件混合事件
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **Blocking**: 否（Slice 2 scope 为迁移，非 stream feature 完整覆盖；现有非 stream 测试已覆盖失败路径）
- **建议裁决**: deferred-with-owner（Slice 3 或专项测试 pass 补齐）

### S2-04-未修复-低-`@pytest.mark.unit` 使用未注册 marker

- **入口/函数**: 4 个测试函数
- **文件(行号)**: `tests/fins/test_sec_downloader.py:1005, 1078, 1146, 1229`
- **输入场景**: pytest 运行时
- **实际分支**: `pyproject.toml` 仅注册 `stress` marker
- **预期行为**: 使用的 marker 应在 `pyproject.toml` 注册
- **实际行为**: `@pytest.mark.unit` 未注册，产生 `PytestUnknownMarkWarning`；且仅 `test_sec_downloader.py` 使用，其余 3 个测试文件不使用，存在不一致
- **直接证据**: `pyproject.toml:139-141` 仅注册 `stress`；`test_sec_downloader.py` 4 处使用 `@pytest.mark.unit`
- **影响**: pytest warning 噪音；marker 语义不一致
- **建议改法和验证点**: 在 `pyproject.toml` 注册 `unit` marker，或移除 4 处装饰器（其余测试文件未使用）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

### S2-05-未修复-低-`_maybe_await` 在 sec_pipeline.py 中为死代码

- **入口/函数**: `_maybe_await`
- **文件(行号)**: `dayu/fins/pipelines/sec_pipeline.py:293-308`
- **输入场景**: 无（从未被调用）
- **实际分支**: grep 仅返回定义行，无调用点
- **预期行为**: 不应存在未使用的函数
- **实际行为**: `_maybe_await` 已定义但从未在 sec_pipeline.py 中调用；`inspect` import（行 14）也仅为此函数服务
- **直接证据**: `grep '_maybe_await(' sec_pipeline.py` 仅返回行 293（定义）
- **影响**: 死代码误导读者；违反 AGENTS.md "优先使用模块级私有辅助函数"
- **建议改法和验证点**: 删除 `_maybe_await` 及其专属 `inspect` import
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted

### S2-06-未修复-低-`_SpySourceRepository.download_files_stream` 缺少返回类型注解

- **入口/函数**: `_SpySourceRepository.download_files_stream`
- **文件(行号)**: `tests/fins/test_sec_pipeline_download_stream.py:212`
- **输入场景**: pyright 类型检查
- **实际分支**: 方法签名无返回类型
- **预期行为**: 应标注 `-> AsyncIterator[DownloaderEvent]`（与同文件 `StreamStubDownloader.download_files_stream` 一致）
- **实际行为**: 无返回类型注解
- **直接证据**: 行 212 `):` 无 `-> ...` 返回类型
- **影响**: 违反 AGENTS.md "禁止无类型返回值"（虽为死代码，S2-02 删除后此问题自然消失）
- **建议改法和验证点**: 随 S2-02 一并删除
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Blocking**: 否
- **建议裁决**: accepted（随 S2-02 一起处理）

## 未发现实质性问题的审查点

以下审查点经 subagent 深度走读，未发现实质性问题：

### SEC-only boundary

- `dayu/fins/downloaders/__init__.py` 仅导出 `SecDownloader`，模块 docstring 明确声明 CN/HK 后续 Slice 迁移
- `SecDownloadAdapter.download()` 有显式 `market != "US"` 校验（sec_pipeline.py:1450）
- 全局搜索无 CN/HK downloader 代码实现
- 无 upload/process/CLI 代码
- 无 Host/Engine 反向依赖

### OLD 迁移证据

- SEC downloader 语义完整保留：HTTP 层（限流、文件锁、指数退避、304 条件下载）、SEC 接口（ticker map、submissions、browse-edgar、index.json、SGML）、文件级语义（RemoteFileDescriptor、DownloaderEvent、source_fingerprint）
- 类型迁移使用 NEW domain/contracts/ticker_normalization
- SEC download workflow 1:1 迁移：公司解析、ticker alias、form window、SC13 filtering、browse-edgar retry、per-filing stream、diagnostics、rejection registry、stale cleanup、cancellation at filing boundary

### FinsSourceDownloadAdapterRequest / Result 设计

- `overwrite_existing` 正确映射到 `SecPipeline.download(overwrite=...)`
- `cancellation_checker` 正确映射到 `SecPipeline.download(cancel_checker=...)`，类型 `FinsJobCancellationChecker`（Protocol, `() -> bool`）
- `persisted_summary` 与 `documents`/`rejected_artifacts` 互斥，runtime 有严格 guard clause（ingestion_runtime.py:1908-1911），无 double write 风险

### DefaultFinsRuntime registration

- `(sec, US)` 和 `(auto, US)` 正确注册到同一 SEC adapter 实例（service_runtime.py:197-199）
- `SEC_DOWNLOAD_SOURCE = "sec"`（sec_pipeline.py:138）
- adapter 为 lazy singleton（double-checked lock）

### Cancellation 传递

- `_RuntimeJobCancellationChecker` -> `FinsSourceDownloadAdapterRequest.cancellation_checker` -> `SecDownloadAdapter.download` -> `SecPipeline.download(cancel_checker=...)` -> `sec_download_workflow.py:430` filing boundary check
- 类型链完整，无断裂

### Storage-only writes

- 业务数据写入全部通过 repository 协议：SourceDocumentRepository、CompanyMetaRepository、ProcessedDocumentRepository、DocumentBlobRepository、FilingMaintenanceRepository
- SEC HTTP cache（`sec_download_state.py`）使用直接文件 I/O，但属于 HTTP 响应缓存层，非业务数据写入，不违反 storage-only 约束

### AGENTS 硬约束

- 中文 docstring：所有新函数/类/方法均有中文 docstring，含 Args/Returns/Raises
- 禁止 Any/object：全部 4 个生产文件和 4 个测试文件均无 `Any` 或 `: object` 类型注解
- 无魔法数字/字符串：SEC 限流常量有 `Final` 标注和中文注释

### Tests

- network-free：全部 4 个测试文件通过 monkeypatch/stub 隔离所有网络调用
- 覆盖成功/失败/重复/overwrite：非 stream 测试覆盖 304 跳过、下载成功/失败、HTTP 503、0 字节、overwrite=True/False、primary abort、指纹匹配跳过、rebuild 模式、取消竞态
- runtime registration：`test_default_runtime_registers_sec_and_auto_us_download_adapter` 验证 SEC 和 auto adapter 装配关系和同一性

## Open Questions

- 无。

## Residual Risk

1. **stream failure path 未覆盖**：流式下载中途失败、`overwrite=True`、多文件混合事件的测试缺失（S2-03）。建议 Slice 3 或专项测试 pass 补齐。
2. **SEC User-Agent / rate-limit 未通过 DefaultFinsRuntime 暴露**：`build_sec_download_adapter` 接受 `user_agent`/`sleep_seconds`/`max_retries`，但调用方未传入，使用内部默认值。生产部署前需确认默认 User-Agent 是否满足 SEC fair-access policy。
3. **`rebuild_processed` 语义落差**：adapter 协议要求该字段但 SEC adapter 静默忽略（sec_pipeline.py:1458 硬编码 `rebuild=False`）。语义上正确（runtime 的 rebuild_processed 与 pipeline 的 rebuild 含义不同），但缺少文档说明。建议在 adapter docstring 中明确语义边界。
4. **OLD 遗留模式**：`_await_if_needed`（sec_downloader.py:1951）和 `_maybe_await`（6 个文件重复定义）为 OLD 迁移遗留兼容 wrapper，应在后续清理 pass 中统一移除。
5. **`_build_result(**payload)` kwargs 模式**：sec_pipeline.py:1392 使用 `**payload: JsonValue` 接受任意关键字参数，为 OLD pipeline 遗留模式，后续应考虑用 TypedDict 替代。
6. **SEC HTTP cache 绕过 repository 抽象**：`sec_download_state.py` 使用直接文件 I/O 做 HTTP 响应缓存，非业务数据，但与 NEW repository 抽象不一致。

## Verdict

**pass-with-findings**

- 0 blocking findings
- 3 个中 severity findings（S2-01 docstring 错位、S2-02 死代码、S2-03 stream 测试缺失）：均为代码质量/测试覆盖问题，不影响运行时正确性
- 3 个低 severity findings（S2-04 marker 未注册、S2-05 死代码、S2-06 缺少类型注解）
- SEC-only boundary 严格执行，OLD 语义完整保留，runtime registration 正确，cancellation 传递完整，storage-only writes 成立，无 double write 风险
