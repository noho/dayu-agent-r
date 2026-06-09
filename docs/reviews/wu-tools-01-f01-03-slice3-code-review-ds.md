# WU-TOOLS-01-F01-03 Slice 3 Code Review — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice3-code-review-ds.md`
- **Included scope**:
  - Production: `dayu/fins/downloaders/cninfo_downloader.py`, `dayu/fins/downloaders/hkexnews_downloader.py`, `dayu/fins/downloaders/__init__.py`, `dayu/fins/pipelines/cn_download_*.py` (10 files), `dayu/fins/pipelines/cn_form_utils.py`, `dayu/fins/pipelines/cn_pipeline.py`, `dayu/fins/pipelines/download_events.py`, `dayu/fins/service_runtime.py`
  - Tests: `tests/fins/test_cninfo_downloader.py`, `tests/fins/test_hkexnews_downloader.py`, `tests/fins/test_cn_download_workflow.py`, `tests/fins/test_cn_download_runtime.py`, `tests/fins/test_cn_pipeline.py`, `tests/fins/test_fins_ingestion_runtime.py`
  - Docs: `dayu/fins/README.md`, `tests/README.md`, `docs/reviews/wu-tools-01-f01-03-slice3-implementation-codex.md`
- **Excluded scope**: CN/HK upload/process/CLI, Host/Engine 内部, 非 CN/HK 的 SEC pipeline 文件
- **Parallel review coverage**: 4 subagents covered CN/HK downloader protocol compliance, CN pipeline migration correctness/PDF gate/Docling, service_runtime adapter registration, and CN/HK test coverage. All subagent findings independently verified by primary reviewer against source code.

## Verdict

**pass** — 0 blocking findings (高)；1 medium non-blocking finding；11 low findings。

迁移质量高：CNInfo/HKEXNews 下载器业务逻辑完整保留，`cn_pipeline.py` 为窄 download facade，persisted-summary adapter 协议正确实现，`rebuild_processed` 未映射到 OLD rebuild，Docling 转换不在 PDF gate 持有期间执行，所有写入通过 storage 协议，无 Host/Engine 反向依赖，无 CN/HK SEC 交叉污染。

---

## Findings

### F1-[未修复]-[中]-HK adapter 默认 sleep/retry 值间接耦合于 CNINFO 常量

- **入口/函数**: `build_hk_download_adapter` / `CnPipeline.__init__`
- **文件(行号)**:
  - `dayu/fins/pipelines/cn_pipeline.py:68-69` — `DEFAULT_CN_HK_SLEEP_SECONDS` 和 `DEFAULT_CN_HK_MAX_RETRIES` 绑定 `CNINFO_DEFAULT_SLEEP_SECONDS` / `CNINFO_DEFAULT_MAX_RETRIES`
  - `dayu/fins/pipelines/cn_pipeline.py:792-793` — `build_hk_download_adapter` 使用 `DEFAULT_CN_HK_SLEEP_SECONDS` / `DEFAULT_CN_HK_MAX_RETRIES` 作为默认值
- **输入场景**: HK 交易所 API 限流规则变更，HKEXNews downloader 需要不同于 CNInfo 的 `sleep_seconds` / `max_retries` 默认值。
- **实际分支**: HK adapter factory 的默认值与 CN adapter factory 共享同一对常量，而常量名 `DEFAULT_CN_HK_*` 暗示联合意图，但其值源自 `CNINFO_DEFAULT_*` 而非 `HKEXNEWS_DEFAULT_*`。
- **预期行为**: 各 source 的限流默认值应直接从其对应 downloader 模块的常量推导，或 HK adapter factory 应有独立默认值。
- **实际行为**: 暂无运行时 bug——CNInfo 与 HKEXNews 的 `DEFAULT_SLEEP_SECONDS` 当前恰好相同（均为 0.3），`DEFAULT_MAX_RETRIES` 也相同（均为 3）。但若 HKEXNews downloader 未来独立调整限流参数，HK adapter factory 不会感知变更。
- **直接证据**:
  - `cn_pipeline.py:68`: `DEFAULT_CN_HK_SLEEP_SECONDS: Final[float] = CNINFO_DEFAULT_SLEEP_SECONDS`
  - `cn_pipeline.py:69`: `DEFAULT_CN_HK_MAX_RETRIES: Final[int] = CNINFO_DEFAULT_MAX_RETRIES`
  - `cn_pipeline.py:792`: `sleep_seconds: float = DEFAULT_CN_HK_SLEEP_SECONDS`
  - `cn_pipeline.py:793`: `max_retries: int = DEFAULT_CN_HK_MAX_RETRIES`
- **影响**: 维护风险——如果 HK 限流规则变更，仅更新 `hkexnews_downloader.py` 的下载器常量不足以同步 adapter factory 默认值
- **建议改法和验证点**:
  1. 将 `DEFAULT_CN_HK_SLEEP_SECONDS` 和 `DEFAULT_CN_HK_MAX_RETRIES` 拆分为独立常量，分别源自 `CNINFO_DEFAULT_*` 和 `HKEXNEWS_DEFAULT_*`
  2. 或直接在各 `build_*_adapter` factory 函数默认参数中引用对应下载器的常量
  3. 添加断言测试：验证 CN adapter 和 HK adapter 的 sleep_seconds/max_retries 默认值分别匹配各自下载器常量
- **修复风险（低）**: 仅常量命名与默认值链路调整，不改变运行时行为（当前值相同）
- **严重程度（中）**: non-blocking

### F2-[未修复]-[低]-`CnPipeline` 接受但未使用 `processor_registry` 参数

- **入口/函数**: `CnPipeline.__init__`
- **文件(行号)**: `dayu/fins/pipelines/cn_pipeline.py:170, 235`
- **输入场景**: 所有 `CnPipeline` 构造场景。
- **实际分支**: `processor_registry` 作为参数传入并存储为 `self._processor_registry`，但全类无任何方法读取该字段。
- **预期行为**: 若参数在 Slice 3 内不使用，应明确标注为预留（docstring + `# noqa` 或显式 `_` 前缀说明），避免维护者误以为其被消费。
- **直接证据**: `rg '_processor_registry' cn_pipeline.py` 仅在 line 235 赋值，无读取点
- **影响**: 死代码；可能误导维护者以为 processor_registry 在 Slice 3 内已有行为
- **建议改法和验证点**: 在 docstring/注释中标注为后续 slice 预留
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F3-[未修复]-[低]-部分 CN pipeline 模块使用英文 docstring，与其他模块中文 docstring 不一致

- **入口/函数**: 模块级 / 函数级 docstring
- **文件(行号)**:
  - `dayu/fins/pipelines/cn_download_pdf_gate.py:9-73`（全英文）
  - `dayu/fins/pipelines/cn_download_source_upsert.py`（全英文）
  - `dayu/fins/pipelines/cn_download_staging.py`（全英文）
- **输入场景**: 静态代码
- **实际行为**: `cn_download_models.py`、`cn_download_protocols.py`、`cn_download_workflow.py` 等模块使用中文 docstring，而上述三个模块使用英文。同一 package 内风格不一致。
- **直接证据**: 对比 `cn_download_models.py:1-4`（中文模块 docstring）与 `cn_download_source_upsert.py:1-4`（英文模块 docstring）
- **影响**: 风格不一致，维护困惑
- **建议改法和验证点**: 统一为中文 docstring（CLAUDE.md 要求 "函数必须提供完整中文 docstring"）
- **修复风险（低）**: 仅格式变更
- **严重程度（低）**: non-blocking

### F4-[未修复]-[低]-`CnDownloadCancelledError` 从 `cn_download_filing_workflow` 跨模块导入 `cn_download_rebuild`

- **入口/函数**: `cn_download_rebuild._is_cancel_requested`
- **文件(行号)**: `dayu/fins/pipelines/cn_download_rebuild.py:18`
- **输入场景**: rebuild 路径中检测到取消信号时。
- **实际行为**: `cn_download_rebuild.py` 从 `cn_download_filing_workflow.py` 导入 `CnDownloadCancelledError`（一个 `RuntimeError` 子类）。该异常定义在 `cn_download_filing_workflow.py:57`，是简单控制流异常，但导致 `rebuild` 模块依赖 `filing_workflow` 模块。
- **预期行为**: 共享控制流异常应放在公共 errors 模块或 `cn_download_models.py` 中，避免反向模块依赖。
- **直接证据**: `cn_download_rebuild.py:18`: `from dayu.fins.pipelines.cn_download_filing_workflow import CnDownloadCancelledError`
- **影响**: 低风险的模块间循环引用隐患
- **建议改法和验证点**: 将 `CnDownloadCancelledError` 提取到 `cn_download_models.py` 或专门的 `cn_download_errors.py`
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F5-[未修复]-[低]-`test_hkexnews_downloader.py` 缺少下载重试与 HEAD 软失败降级测试

- **入口/函数**: 缺失的测试函数
- **文件**: `tests/fins/test_hkexnews_downloader.py`
- **输入场景**: HKEXNews 下载过程中 HTTP 503 重试或 HEAD 请求失败。
- **实际行为**: HKEXNews downloader 实现了重试逻辑（`max_retries=3`）和 HEAD 请求，但测试中无对应的重试与 HEAD 失败降级测试。CNInfo downloader 有 `test_download_report_pdf_retries_then_raises` 和 `test_list_report_candidates_head_failure_softly_degrades`。
- **直接证据**: `test_cninfo_downloader.py:1203`（重试测试）、`:944`（HEAD 失败测试）存在对应覆盖；`test_hkexnews_downloader.py` 中无等价测试
- **影响**: HK downloader 重试与降级路径未经测试覆盖，回归风险
- **建议改法和验证点**: 添加对应 HKEXNews 的重试与 HEAD 失败降级测试
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F6-[未修复]-[低]-`test_cn_download_workflow.py` 缺少下载失败、取消与日期过滤测试

- **入口/函数**: 缺失的测试函数
- **文件**: `tests/fins/test_cn_download_workflow.py`
- **输入场景**: discovery client 抛出 RuntimeError / cancellation_checker 返回 True / filed_after/before 窄范围过滤
- **实际行为**: 全部 4 个测试仅覆盖成功路径；无失败路径、取消传播、日期过滤或 form_type（H1/Q1/Q3/Q4）过滤测试
- **直接证据**: 4 tests exist; none exercises RuntimeError raise from discovery client, cancellation checker=True, or narrow date ranges
- **影响**: 失败与取消路径未经 workflow 级测试覆盖
- **建议改法和验证点**: 添加失败路径、取消、日期过滤测试
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F7-[未修复]-[低]-`test_cn_download_runtime.py` 缺少下载失败路径与显式 source 覆盖测试

- **入口/函数**: 缺失的测试函数
- **文件**: `tests/fins/test_cn_download_runtime.py`
- **输入场景**: 下载运行时异常 / `source="hkexnews"` 显式指定 / `source="auto"` CN 市场
- **实际行为**: 所有测试预期 SUCCEEDED，无 FAILED 状态路径；`source="hkexnews"` 显式 source 与 `source="auto"` CN 市场的 start_download 路径未测试
- **直接证据**: 全文件 `FinsIngestionJobStatus.FAILED` 无匹配
- **影响**: 运行时失败收口与 auto 路由路径测试覆盖不全
- **建议改法和验证点**: 添加失败与 auto 路由覆盖测试
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F8-[未修复]-[低]-`test_cn_pipeline.py` 缺少 persisted_summary 持久化与 PDF gate 作用域测试

- **入口/函数**: 缺失的测试函数
- **文件**: `tests/fins/test_cn_pipeline.py`
- **输入场景**: adapter 返回 persisted_summary 后 source_repository 写入验证 / PDF gate 租赁期间 Docling 排除验证
- **实际行为**: `test_download_runs_cn_workflow` 仅验证 result dict 结构，未验证 source_repository 写入内容；PDF gate 作用域仅在 workflow 测试中覆盖，pipeline 级未复现
- **直接证据**: 与 `test_cn_download_workflow.py` 和 `test_cn_download_runtime.py` 中的 source_meta 断言相比，pipeline 测试中缺少等价验证
- **影响**: adapter 级 persisted_summary 端到端验证偏弱
- **建议改法和验证点**: 添加 source_repository 写入内容的断言
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F9-[未修复]-[低]-`test_hkexnews_downloader.py` 缺少构造函数参数校验测试

- **文件**: `tests/fins/test_hkexnews_downloader.py`
- **输入场景**: `HkexnewsDiscoveryClient(max_retries=-1)` 或 `sleep_seconds=-1.0`
- **实际行为**: CNInfo 测试有 `test_constructor_rejects_invalid_max_retries` 和 `test_constructor_rejects_negative_sleep_seconds`，HKEXNews 无等价测试
- **直接证据**: `test_cninfo_downloader.py:1300,1307` 存在；`test_hkexnews_downloader.py` 中无等价
- **影响**: HK downloader 构造参数非法值行为的回归保护缺失
- **严重程度（低）**: non-blocking

### F10-[未修复]-[低]-`test_cn_pipeline.py` CN 下载测试未验证 source_repository 写入

- **文件(行号)**: `tests/fins/test_cn_pipeline.py:227-265`
- **输入场景**: pipeline 下载成功后
- **实际行为**: 测试验证 `summary["downloaded"]` 和 `discovery.download_calls`，但未读取 `source_repository` 验证 `source_meta` 已持久化
- **直接证据**: `test_cn_download_workflow.py` 和 `test_cn_download_runtime.py` 均有 source_meta 断言；pipeline 测试缺失
- **严重程度（低）**: non-blocking

### F11-[未修复]-[低]-CNInfo/HKEXNews downloader 间存在重复私有辅助符号

- **文件**:
  - `dayu/fins/downloaders/cninfo_downloader.py` / `dayu/fins/downloaders/hkexnews_downloader.py`
- **重复符号**: `JsonScalar`/`JsonValue` 类型别名、`_HeadMeta` dataclass、`_PERIOD_SORT_KEY`、`_PDF_MAGIC_BYTES`/`_PDF_MIN_BYTES`、`_utc_now_isoformat()`、限流与退避逻辑
- **实际行为**: 两个 downloader 模块各自定义字节一致或语义相同的私有符号。每个模块自身完整自足，但共享逻辑的修改需两处同步
- **直接证据**: 逐模块对比确认
- **影响**: 维护同步负担；CLAUDE.md "重复逻辑必须抽取"
- **建议改法和验证点**: 抽取到 `dayu/fins/downloaders/_download_utils.py`
- **修复风险（低）**
- **严重程度（低）**: non-blocking

---

## 正面确认项

以下关键审查点逐一验证通过：

| 审查项 | 结论 | 证据 |
|---|---|---|
| CNInfo/HKEXNews 下载器保留 OLD 业务语义 | 通过 | discovery、title filtering、amended preference、language detection、PDF fingerprint、HTTP retry/sleep 规则完整保留 |
| `cn_download_rebuild.py` 仅本地 source meta rebuild | 通过 | 模块 docstring 明确 "不访问巨潮、披露易或 Docling"；import 路径无 docling/upload/process |
| `build_cn_filing_ids` 仅迁入 ID 生成算法 | 通过 | `cn_form_utils.py:187-190`: SHA-1 + seed 算法，无 upload service 依赖 |
| `cn_pipeline.py` 为窄 download facade | 通过 | 模块 docstring: "只迁移...下载面...上传、process、CLI 不在本 Slice 内" |
| `FinsSourceDownloadAdapter` persisted-summary 协议正确 | 通过 | `CnDownloadAdapter.download()` 返回 `persisted_summary` 不返回 `documents` |
| `rebuild_processed` 未映射到 OLD rebuild | 通过 | `cn_pipeline.py:606`: `rebuild=False` 硬编码；docstring 明确语义分离 |
| Docling 转换不在 PDF gate 持有期间执行 | 通过 | gate 仅包裹 `download_report_pdf`；Docling 转换在单独 `asyncio.to_thread` |
| Docling 默认转换通过 `dayu.documents.docling_runtime` | 通过 | `cn_pipeline.py:17-20`: `from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling` |
| `DefaultFinsRuntime` 注册 6 个 adapter key | 通过 | `service_runtime.py:221-228`: (sec,US), (auto,US), (cninfo,CN), (auto,CN), (hkexnews,HK), (auto,HK) |
| SEC 注册未被破坏 | 通过 | Slice 2 的 SEC adapter 构建与注册路径未改动 |
| CN/HK User-Agent 各自独立 | 通过 | CNInfo: `"DayuAgent/1.0 (+cn-download)"`；HKEXNews: `"DayuAgent/1.0 (+hk-download)"` |
| storage-only writes（无直接 FS 路径） | 通过 | 所有持久化通过 `dayu.fins.storage` 协议 |
| network-free tests | 通过 | 全部使用 MockTransport / fake objects / tmp_path |
| 无 Host/Engine 反向依赖 | 通过 | `rg 'from dayu\.(host|engine)'` 无匹配 |
| 无 upload/process/CLI 引入 | 通过 | `rg 'upload_workflow|process_workflow'` 无匹配 |
| 无 `Any`/`object` 类型 | 通过 | targeted scan 在生产文件中无匹配 |
| 中文 docstring | 通过 | 大部分模块中文 docstring；F3 记录了少数英文模块 |
| pyright | 通过 | 0 errors |
| pytest | 通过 | 111 passed, 3 warnings (仅 edgartools deprecation) |

## Open Questions

1. **CNInfo rate-limit 模式变更**: 原 OLD 描述中提到 `random.uniform(4, 7)` 的随机抖动模式，迁移后改为 0.3s 最小间隔节流。若 0.3s 最小间隔比 OLD 4-7s 抖动更激进（高吞吐），是否确认 CNInfo/HKEXNews API 能承受该频率？当前测试均为 mock transport，无实际 API 行为验证。

## Residual Risk

1. **HK defaults 耦合**: 如 F1 所述，HK adapter factory 的 `sleep_seconds`/`max_retries` 默认值源自 CNINFO 常量。当前值相同无运行时影响，但若 HK 独立调整限流参数需同步两处。

2. **CN/HK 下载失败路径测试覆盖不足**: workflow 级与 runtime 级的下载失败、取消、日期过滤测试缺失（F5-F10），回归保护偏弱。

3. **Docling 集成未在 Slice 3 测试集中实际运行**: 默认 Docling 转换路径通过 `convert_pdf_bytes_with_docling` 注入，但 Slice 3 测试全部使用 fake converter；真实 Docling 运行时集成未经验证。

4. **`download_events.py` 为 SEC/CN/HK 共享模块**: 当前仅包含通用事件类型。若未来 CN/HK pipeline 需要 CN/HK 特有事件类型，需注意共享模块变更对 SEC pipeline 的兼容影响。
