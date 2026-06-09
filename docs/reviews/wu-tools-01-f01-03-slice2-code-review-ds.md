# WU-TOOLS-01-F01-03 Slice 2 Code Review — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice2-code-review-ds.md`
- **Included scope**:
  - Production: `dayu/fins/downloaders/` (new), `dayu/fins/pipelines/` (new), `dayu/fins/ingestion_runtime.py` (modified), `dayu/fins/service_runtime.py` (modified)
  - Tests: `tests/fins/test_sec_downloader.py` (new), `tests/fins/test_sec_pipeline_download.py` (new), `tests/fins/test_sec_pipeline_download_stream.py` (new), `tests/fins/test_fins_ingestion_runtime.py` (modified)
  - Docs: `dayu/fins/README.md`, `tests/README.md`, `docs/reviews/wu-tools-01-f01-03-slice2-implementation-codex.md`
  - Design/control sources: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- **Excluded scope**: CN/HK downloader, upload workflow, process workflow, CLI, Host/Engine internals (reviewed only for reverse dependency violations)
- **Parallel review coverage**: 4 subagents covered SEC downloader protocol compliance, SEC pipeline migration correctness, ingestion_runtime/service_runtime contract changes, and test coverage/quality. All subagent findings were independently verified against source code by the primary reviewer.

## Verdict

**fix-accepted** — 2 blocking findings (severity `高`), 2 important non-blocking findings (severity `中`), 5 low-severity findings. See below for recommended fix directions and controller adjudication prompts.

---

## Findings

### F1-[未修复]-[高]-`rebuild_processed` 在上传 adapter `persisted_summary` 快速路径中静默丢弃

- **入口/函数**: `SecDownloadAdapter.download` → `_execute_download_request`
- **文件(行号)**:
  - `dayu/fins/pipelines/sec_pipeline.py:1458` — `rebuild=False` 硬编码
  - `dayu/fins/ingestion_runtime.py:1908-1911` — `persisted_summary is not None` 快速返回，跳过 `_store_downloaded_document` 循环
- **输入场景**: 调用方通过 `FinsDownloadRequest(rebuild_processed=True)` 发起 SEC 下载，期望下载完成后标记已有 processed 产物需重处理。
- **实际分支**:
  1. `_execute_download_request` 构造 `FinsSourceDownloadAdapterRequest(rebuild_processed=True)` 传给 adapter
  2. `SecDownloadAdapter.download` 调用 `self._pipeline.download(..., rebuild=False)` — 硬编码 `False`，忽略 `request.rebuild_processed`
  3. `SecPipeline.download` 接受 `rebuild` 参数并传递给底层 workflow，但 adapter 固定传 `False` 使其从未生效
  4. 返回 `persisted_summary` 非 None，runtime 在 line 1911 快速返回，整个 `_store_downloaded_document` 循环（含 `rebuild_processed` 判断 line 2026）不可达
- **预期行为**: `rebuild_processed=True` 应触发 processed 文档重处理标记，或至少在 adapter 层明确拒绝并报错。
- **实际行为**: 参数被静默丢弃，调用方意图无任何效果。
- **直接证据**:
  - `sec_pipeline.py:1458`: `rebuild=False` 字面量，不引用 `request.rebuild_processed`
  - `ingestion_runtime.py:1908-1911`: `if adapter_result.persisted_summary is not None: ... return _bounded_download_summary(adapter_result.persisted_summary)` 跳过 lines 1916-1947 的文档循环
  - `ingestion_runtime.py:2026-2027`: `if rebuild_processed: _mark_processed_reprocess_required_if_present(...)` 仅在 `persisted_summary` 为 None 时可达
- **影响**: 调用方期望行为被静默忽略；若上层依赖 `rebuild_processed` 触发下游流程，将出现逻辑缺口且无任何可见错误信号。
- **建议改法和验证点**:
  1. 在 `SecDownloadAdapter` 中将 `request.rebuild_processed` 传递给 `SecPipeline.download(rebuild=request.rebuild_processed)`
  2. 或在 `SecDownloadAdapter.download()` 中，若 `request.rebuild_processed` 为 True 且 adapter 不支持，应显式 `raise ValueError`，不可静默忽略
  3. 添加测试：`FinsDownloadRequest(rebuild_processed=True)` 发起 SEC 下载，验证 processed rebuild 标记确实生效或被明确拒绝
- **修复风险（中）**: 传递 `rebuild_processed` 到 `SecPipeline.download(rebuild=...)` 涉及 OLD pipeline rebuild 路径；需确认 OLD `rebuild` 语义与新 `rebuild_processed` 对齐，且不会触发意外的全量重下载
- **严重程度（高）**: blocking

### F2-[未修复]-[高]-`_summary_from_pipeline_result` 中 `rejected_count` 恒为 0，下游决策依赖错误值

- **入口/函数**: `_summary_from_pipeline_result` → `_run_download_job`
- **文件(行号)**:
  - `dayu/fins/pipelines/sec_pipeline.py:1510` — `if item.get("status") == "rejected":`
  - `dayu/fins/pipelines/sec_download_filing_workflow.py:206,230,276,377` — 唯一的状态字面量为 `"skipped"`, `"failed"`, `"downloaded"`
  - `dayu/fins/ingestion_runtime.py:1723` — `if summary.failed_count > 0 and summary.downloaded_count == 0 and summary.rejected_count == 0:`
- **输入场景**: SEC 下载 pipeline 中所有 filing 均被 6-K 分类过滤（status=skipped）但有部分下载失败（status=failed）。
- **实际分支**:
  1. Pipeline 返回 filing result，状态为 `"skipped"`（6-K 过滤）和 `"failed"`
  2. `_summary_from_pipeline_result` 遍历 filings，检查 `item.get("status") == "rejected"`，但没有任何代码路径设置 `"rejected"` 状态
  3. `rejected_count` 始终为 0
  4. `_run_download_job:1723` 决策条件 `summary.rejected_count == 0` 为 True（恒为 True），可能误判 job 为 FAILED
- **预期行为**: 被 6-K 分类过滤（rejection_registry 中登记）的 filing 应在 summary 中计入 rejected_count，使下游正确区分「全部失败且无拒绝」与「部分拒绝+部分失败」。
- **实际行为**: `rejected_count` 恒为 0；`_run_download_job:1723` 条件将拒绝文档视为不存在，可能将本应标记 SUCCEEDED（有拒绝但无错误）或至少不应标记为空文档失败（有拒绝有失败）的 job 错误标记为 FAILED。
- **直接证据**:
  - `sec_download_filing_workflow.py`: 所有 `"status"` 值搜索，仅出现 `"skipped"`, `"failed"`, `"downloaded"`，无 `"rejected"`
  - `sec_pipeline.py:1510`: `if item.get("status") == "rejected":` 匹配为空
  - `ingestion_runtime.py:1723`: `summary.rejected_count == 0` 作为 FAILED 判定条件之一，依赖上述错误值
- **影响**: 下载 job 终态误判；在有 6-K 过滤拒绝但无下载内容的场景中，job 可能被错误标记为 FAILED 而非 SUCCEEDED
- **建议改法和验证点**:
  1. 在 `_summary_from_pipeline_result` 中统计 `skip_reason` 为 `"6k_filtered"` 的 item 作为 rejected_count
  2. 或在整个 pipeline 中为新 runtime 接口单独定义 rejected status 语义，在 `sec_download_filing_workflow.py` 中增加 `"rejected"` 状态
  3. 添加测试：全 6-K 过滤场景验证 rejected_count > 0 且 job 不被误判为 FAILED
- **修复风险（低）**: 仅影响 summary 计数字段；修改 status 判断不改变 pipeline 的核心下载与持久化逻辑
- **严重程度（高）**: blocking

### F3-[未修复]-[中]-取消检查仅在文档边界生效，不覆盖单文档内文件下载与限流等待

- **入口/函数**: `SecDownloader.download_files` / `download_files_stream`
- **文件(行号)**:
  - `dayu/fins/downloaders/sec_downloader.py:1253-1452` — `download_files_stream` 与 `download_files` 不检查 cancellation_checker
  - `dayu/fins/pipelines/sec_download_workflow.py:430` — `download_workflow` 仅在文档间检查取消
  - `dayu/fins/downloaders/sec_downloader.py:1845` — `_rate_limit()` 可因 SEC 429/503 进入长时间冷却，无取消中断机制
- **输入场景**: 下载单个多文件 filing 时（如包含大量附件的 10-K），在下载过程中收到取消请求。
- **实际分支**: 取消检查仅在文档边界（filing 之间）触发；单个 filing 的多个文件遍历、HTTP 重试循环和限流冷却期间均不检查取消状态。
- **预期行为**: 取消检查应在文件级迭代、HTTP 重试之间以及 `_rate_limit` 长等待中触发，实现真正的协作式取消。
- **实际行为**: 取消后可能需等待当前 filing 的全部文件下载完成、所有重试耗尽、限流冷却结束后才响应取消。
- **直接证据**:
  - `sec_downloader.py:1253-1452`: 循环体内无 `cancellation_checker` 调用
  - `sec_download_workflow.py:430` 注释明确说明 "仅在文档边界生效"
  - `sec_downloader.py:1845`: `_rate_limit` 中 `time.sleep()` 不可中断
- **影响**: 取消延迟可能达到秒级甚至分钟级（SEC 限流冷却）；浪费带宽与 SEC 请求配额
- **建议改法和验证点**:
  1. 在 `download_files_stream` 的文件迭代循环中增加 `cancellation_checker` 检查
  2. 将 `_rate_limit` 的长 sleep 拆分为短 sleep + 循环检查取消
  3. 添加测试：在文件级注入取消 checker，验证中途终止且不继续下载剩余文件
- **修复风险（中）**: 需在 loop 内和 sleep 内增加取消检查点，可能影响已有的测试断言（文件计数）
- **严重程度（中）**: non-blocking，但建议在 Slice 后续修复

### F4-[未修复]-[中]-`DefaultFinsRuntime` 硬依赖 SEC pipeline 具体实现

- **入口/函数**: `DefaultFinsRuntime.get_ingestion_runtime`
- **文件(行号)**: `dayu/fins/service_runtime.py:179, 197-200`
- **输入场景**: 任何 `DefaultFinsRuntime.create(workspace_root=...)` 后调用 `get_ingestion_runtime()`。
- **实际分支**: lazy import `from dayu.fins.pipelines.sec_pipeline import SEC_DOWNLOAD_SOURCE, build_sec_download_adapter` 将 SEC 实现绑定到 DefaultFinsRuntime。
- **预期行为**: 遵循 CLAUDE.md "模块间依赖最小化，优先接口或协议"；DefaultFinsRuntime 作为 default assembly root 可接受一定的具体装配，但 import 级硬绑定限制了替换实现的能力。
- **实际行为**: 任何 consumer（包括测试）import `DefaultFinsRuntime` 时都会间接 import SEC pipeline 全部依赖树。
- **直接证据**: `service_runtime.py:179`: `from dayu.fins.pipelines.sec_pipeline import ...` lazy import 在 `get_ingestion_runtime` 方法内部
- **影响**: 架构耦合；若要替换 SEC adapter 实现或支持多来源注入，需修改 DefaultFinsRuntime。当前 lazy import 缓解了冷启动开销但未解决耦合。
- **建议改法和验证点**: 可在 `FinsIngestionRuntime.create` 层面暴露 adapter 注入参数，将 SEC 装配上提到调用方或 bootstrap 层。
- **修复风险（低）**: 仅为架构重构，不改变运行时行为
- **严重程度（中）**: non-blocking（DefaultFinsRuntime 作为 assembly root 允许有限的具体装配）

### F5-[未修复]-[低]-`pytest.mark.unit` 未在 pyproject.toml 注册，测试运行产生 4 条警告

- **入口/函数**: 4 个测试函数
- **文件(行号)**: `tests/fins/test_sec_downloader.py:1005, 1078, 1146, 1229`
- **输入场景**: `pytest tests/fins/test_sec_downloader.py` 运行时。
- **实际分支**: pytest 无法识别 `unit` marker，每个标记测试发出 `PytestUnknownMarkWarning`。
- **直接证据**: pytest 输出含 4 条 `Unknown pytest.mark.unit` 警告；`pyproject.toml:139-141` 仅注册 `stress` marker
- **影响**: 测试输出噪音；可能掩盖其他真实警告
- **建议改法和验证点**: 在 `pyproject.toml` markers 中添加 `"unit: fast unit tests"` 或移除测试上的 `@pytest.mark.unit` 装饰器
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F6-[未修复]-[低]-`_maybe_await` 在 6 个文件中重复定义

- **文件(行号)**:
  - `dayu/fins/pipelines/sec_pipeline.py:293`
  - `dayu/fins/pipelines/sec_download_filing_workflow.py:136`
  - `dayu/fins/pipelines/sec_download_persistence.py:68`
  - `dayu/fins/pipelines/sec_download_workflow.py:201`
  - `dayu/fins/pipelines/sec_filing_collection.py:49`
  - `dayu/fins/pipelines/sec_sc13_filtering.py:236`
- **输入场景**: 迁移引入的 async-sync 桥接模式，作为类型安全的 `isinstance check + await` 包装。
- **实际行为**: 6 个模块中各自定义字节一致的 `_maybe_await`。
- **直接证据**: 逐文件对比函数体完全一致
- **影响**: 违反 CLAUDE.md "重复逻辑必须抽取"；后续修改需同步 6 处
- **建议改法和验证点**: 提取到 `dayu/fins/pipelines/_async_utils.py` 或等效共享模块
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F7-[未修复]-[低]-`_coerce_optional_int` 与 `_normalize_optional_string` 在 2 个文件中重复定义

- **文件(行号)**:
  - `dayu/fins/pipelines/sec_download_persistence.py:376-424`
  - `dayu/fins/pipelines/sec_fiscal_fields.py:495-523`
- **实际行为**: 两个模块中字节一致的 helper 函数
- **直接证据**: 逐行对比确认重复
- **影响**: 同 F6 — 重复逻辑
- **建议改法和验证点**: 提取到共享模块
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F8-[未修复]-[低]-`_SpySourceRepository.download_files_stream` 为死代码

- **文件(行号)**: `tests/fins/test_sec_pipeline_download_stream.py:205-226`
- **输入场景**: `_SpySourceRepository` 被实例化但 `download_files_stream` 方法从未被调用（下载通过 `downloader` 执行，不通过 source_repository）。
- **实际行为**: 死方法，疑似 copy-paste 残留
- **直接证据**: 全文搜索确认无调用点
- **影响**: 误导维护者；可能引入与实际 `StreamStubDownloader.download_files_stream` 行为不一致的隐式假定
- **建议改法和验证点**: 删除该 dead 方法
- **修复风险（低）**
- **严重程度（低）**: non-blocking

### F9-[未修复]-[低]-`dayu/fins/pipelines/` 缺少 `__init__.py`

- **文件**: `dayu/fins/pipelines/` (`__init__.py` 不存在)
- **输入场景**: 按项目惯例应有模块级 docstring
- **实际行为**: 无 `__init__.py`，无模块级中文 docstring
- **直接证据**: `ls dayu/fins/pipelines/__init__.py` 不存在
- **影响**: 违反 CLAUDE.md "类与模块应提供中文概览 docstring" 的模块级要求；Python 3.3+ 允许隐式命名空间包但项目约定要求显式 `__init__.py`
- **建议改法和验证点**: 添加含中文概览 docstring 的 `__init__.py`
- **修复风险（低）**
- **严重程度（低）**: non-blocking

---

## Open Questions

1. **SEC User-Agent 未在 DefaultFinsRuntime 中显式配置**: `build_sec_download_adapter()` 调用未传 `user_agent` 参数。生产部署时需通过 `SEC_USER_AGENT` 环境变量提供，否则 SEC EDGAR 访问策略可能拒绝请求。当前 `_UNCONFIGURED_USER_AGENT` fallback 值仅产生警告日志，不是安全缺陷但属于部署风险。

2. **`FinsSourceDownloadAdapterRequest.source` 字段在 SEC adapter 中未消费**: adapter 未验证 `request.source` 是否匹配 `"sec"`。若 runtime 错误路由非 SEC source 到此 adapter，会静默从 SEC 下载而非报错。当前无此场景（`_select_download_adapter` 正确路由），但缺少防御性校验。

---

## Residual Risk

1. **取消粒度**: SEC downloader 内部 `download_files`/`download_files_stream` 不检查取消（详见 F3）；当前取消仅在文档边界生效（`sec_download_workflow.py:430`）。若单个 filing 包含大量附件或 SEC 限流冷却较长，取消延迟可达数分钟。

2. **流式下载测试覆盖不足**: `test_sec_pipeline_download_stream.py` 仅 5 个测试，缺少 file failed 事件、overwrite 路径、取消中断、空 primary 文档中止等场景覆盖。

3. **上传不在 Slice 2**: 按用户约束，upload 是长事务但本 Slice 不实现 upload。`persisted_summary` 设计为 upload adapter 预留了扩展点，但 upload adapter 的 `persisted_summary` 与 download adapter 在不同语义下可能需不同的 bounded validation 规则。

4. **`_run_download_job:1723` 的条件 `rejected_count == 0` 耦合于 F2**: 修复 F2 后该条件语义变为正确（被拒绝的 filing 不计入 "未写入任何源文档"），但若 F2 未修，该条件恒为 True，存在误判风险。

5. **跨进程 SEC 限流文件锁**: `_reserve_global_request_slot` 使用 `fcntl` 文件锁实现跨进程限流。在 macOS 上 NFS/网络文件系统场景下 `fcntl` 行为可能不可靠——这是 OLD 代码已知的限制，非本 Slice 引入。

6. **pipeline 内跨模块 magic strings**: 状态码 (`"downloaded"`, `"skipped"`, `"failed"`)、skip reason (`"6k_filtered"`)、事件类型等字符串在多个文件中以字面量形式分散定义。虽未违反 CLAUDE.md 最高约束（工具 schema 字面量豁免），但跨模块一致性依赖人工协调。
