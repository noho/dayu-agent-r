# WU-CLI-SMOKE-01 Docling async convert 调研

## 结论先行

调研动机成立。当前风险不是“缺少一个 async wrapper”，而是第三方 Docling PDF convert 是同步阻塞 API；`asyncio.to_thread(...)` 或 `run_in_executor(...)` 只能取消等待方，不能强制中断已经进入 Docling / PDF backend / 模型推理的 OS thread。

本地已安装版本为 `docling==2.90.0`、`docling-core==2.74.0`。基于本地 Python introspection 与 `.venv` 源码检查，没有发现 `DocumentConverter` 的原生 `async convert` / `aconvert` / 可取消 streaming / cancellation token / callback 入口。Docling 2.90.0 有 `PdfPipelineOptions.document_timeout`，但它是 pipeline 内部合作式文档超时，源码明确说明阻塞 worker thread 可能被遗留到阻塞调用自然返回；它不能替代 Host 级 hard interrupt。

最佳实践建议：当前不应尝试把 Docling “改成原生 async”。若 CN/HK Docling convert 需要 hard interrupt，应开新 work unit，把 Docling convert 从 Fins observation 的线程内同步调用迁到 process/subprocess 隔离边界，并由父进程负责 timeout、terminate、kill、日志与 artifact 回收。

## 本仓库当前调用链与取消边界

### Docling runtime 真源

`dayu/documents/docling_runtime.py` 是当前 Docling PDF 转换统一入口。

- `build_docling_pdf_converter(...)` 构造 `docling.document_converter.DocumentConverter`，只注册 PDF format option，并配置 backend、device、OCR、表格结构等参数。证据：`dayu/documents/docling_runtime.py:342-392`。
- `run_docling_pdf_conversion(...)` 生成 backend x device 尝试链，逐次构造 converter，然后执行传入的 `convert_operation(converter)`。证据：`dayu/documents/docling_runtime.py:510-602`。
- `convert_pdf_bytes_with_docling(...)` 把 bytes 包成 `DocumentStream`，最终执行 `lambda converter: converter.convert(stream)`。证据：`dayu/documents/docling_runtime.py:629-667`。

因此本仓库当前真正调用的 Docling 公开 API 是：

```python
DocumentConverter.convert(DocumentStream(...))
```

调用前后由 Dayu 自己负责 fallback、异常包装和导出 JSON / Markdown；Docling 调用内部没有传入 Dayu cancellation token。

### CN/HK 下载路径

CN/HK 下载 workflow 在进入 Docling 前后有合作式取消检查，但转换本体通过 `asyncio.to_thread(...)` 包同步函数：

- `cn_download_filing_workflow.py:456-460`：

```python
docling_json_bytes = await asyncio.to_thread(
    convert_pdf_to_docling_json,
    pdf_bytes,
    pdf_filename,
)
```

`convert_pdf_to_docling_json` 默认来自 `CnPipeline.convert_pdf_bytes_to_docling_json_bytes(...)`，后者同步调用 `convert_pdf_bytes_with_docling(...)` 并导出 JSON bytes。证据：`dayu/fins/pipelines/cn_pipeline.py:287-317`。

取消边界：外层 awaitable 可以被取消，workflow 可在 convert 前后检查取消；但已经在线程里执行的 `DocumentConverter.convert(...)` 不能被 Python cancellation 强制停止。

### CN/HK/SEC 上传路径

上传路径通过 `DoclingUploadService` 复用同步转换函数：

- 每个文件转换前检查 `cancellation_checker`，但转换调用本身不接收 checker。证据：`dayu/fins/pipelines/docling_upload_service.py:477-490`。
- `_convert_bytes_with_docling(...)` 同步调用 `convert_pdf_bytes_with_docling(...)`。证据：`dayu/fins/pipelines/docling_upload_service.py:597-627`。

上传路径通常运行在 Fins ingestion 后台 producer 中；不是 `asyncio.to_thread` 包裹每个 convert，而是整个 producer 由 Fins 后台执行器调度。

### Fins awaiting / Host poll 路径

当前 Fins awaiting tool 不等待长事务完成，只登记 process-local observation handle 并返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`。Host accepted wait 后通过 activation adapter 激活后台执行。README 已记录该语义：`dayu/fins/README.md:717-725`。

关键边界：

- 默认 Fins ingestion executor 是 daemon thread executor。证据：`dayu/fins/ingestion_runtime.py:1056-1098`。
- Host wait poll adapter 只观察 snapshot；cancel/abandon 时调用 `runtime.cancel_observation(handle)` / `runtime.abandon_observation(handle)`。证据：`dayu/fins/ingestion/wait_adapter.py:134-180`。
- `cancel_observation(...)` 的 docstring 明确说取消是 best-effort，不承诺中断不可取消 blocking call。证据：`dayu/fins/ingestion_runtime.py:2321-2349`。

这意味着 Host awaiting cancel 可以把 operation-scoped cancellation state 设置为 cancelled，但如果后台线程正卡在 Docling 同步转换里，Fins producer 要等 Docling 返回后才能观察该 state。

## 本地 Docling 公开 API 调研

### Controller 补充官方文档核对

Controller 在 AgentCodex 本地源码调研后补查了 Docling 官方 API reference。官方 `DocumentConverter` reference 仍只列出 `convert(...)`、`convert_all(...)`、`convert_string(...)` 和 `initialize_pipeline(...)`，其中 `convert(...)` 返回 `ConversionResult`，`convert_all(...)` 返回同步 `Iterator[ConversionResult]`；未列出 `async convert`、`aconvert`、cancellation token 或 callback 参数。

Controller 同时查到 docling-project/docling 的公开 enhancement “Add per-page progress callback support to DocumentConverter”（2026-05-22 打开），issue body 明确描述当前 core SDK 只有 document-level conversion visibility，没有 page-level callback/event system，并把 cancellation / timeout / streaming progress 作为该 proposal 的动机。这与本地 `docling==2.90.0` introspection 结论一致：当前不能把 Docling 视为已提供 caller-observable async/cancellable convert API。

### 环境版本

本地命令：

```bash
source .venv/bin/activate
python -c 'import importlib.metadata as md; print(md.version("docling")); print(md.version("docling-core"))'
```

结果：

- `docling 2.90.0`
- `docling-core 2.74.0`

### DocumentConverter API

本地 introspection 结果：

- `DocumentConverter.convert(...) -> ConversionResult`
- `DocumentConverter.convert_all(...) -> Iterator[ConversionResult]`
- `DocumentConverter.convert_string(...) -> ConversionResult`
- `DocumentConverter.initialize_pipeline(...)`
- `inspect.iscoroutinefunction(DocumentConverter.convert) == False`
- `inspect.iscoroutinefunction(DocumentConverter.convert_all) == False`

`.venv/lib/python3.11/site-packages/docling/document_converter.py` 证据：

- `convert(...)` 是普通 `def`，内部调用 `convert_all(source=[source], ...)` 并 `return next(all_res)`。本地源码行：`document_converter.py:326-388`。
- `convert_all(...)` 是普通 `def`，返回同步 `Iterator[ConversionResult]`。本地源码行：`document_converter.py:390-468`。
- `_convert(...)` 根据 Docling settings 可用 `ThreadPoolExecutor` 做 batch 并发，但仍是同步 iterator。introspection 源码显示它 `for item in pool.map(...)` 或 `for item in map(...)` 后 `yield item`。

成员扫描没有发现 `aconvert`、`async_convert`、`cancel`、`callback` 或 `timeout` 形式的 `DocumentConverter` 公开方法。

### Pipeline timeout

Docling 2.90.0 的 `PdfPipelineOptions` 有 `document_timeout: Optional[float] = None`。本地源码描述为超过后停止处理并返回 `PARTIAL_SUCCESS`，推荐生产环境 90-120 秒。证据：`.venv/lib/python3.11/site-packages/docling/datamodel/pipeline_options.py:1112-1122`。

但 `standard_pdf_pipeline.py` 的实现显示：

- timeout 在主循环中按 `time.monotonic()` 检查，超过后关闭输入队列并 break。证据：`.venv/lib/python3.11/site-packages/docling/pipeline/standard_pdf_pipeline.py:663-682`。
- 源码注释明确说明：如果 worker thread 卡在 blocking call，例如模型推理或 PDF backend `load_page/get_size`，cleanup 只短暂等待；该线程会继续运行直到阻塞调用完成，并可能持有资源。证据：`.venv/lib/python3.11/site-packages/docling/pipeline/standard_pdf_pipeline.py:631-634`。

因此 `document_timeout` 是有价值的耗时上限信号，但不是 hard interrupt。它最多减少正常 pipeline 长跑，不解决 native/backend 阻塞或线程资源泄漏。

### 其它 async / streaming / callback 迹象

本地 `rg` 扫描 `docling` 与 `docling_core` 包：

- 未发现 `DocumentConverter` 或 PDF convert 路径的 `async def` / `aconvert`。
- `docling.datamodel.service.callbacks` 存在 service request callback 数据结构，但不是本仓库当前 `DocumentConverter.convert(DocumentStream)` API 的取消 token。
- VLM/API model 里有 HTTP request timeout、SSE streaming helper、ThreadPoolExecutor 等实现细节；它们不构成 PDF convert 的 Host 可取消 async API。

## 同步 convert 包 async 的方案对比

| 方案 | 取消语义 | 资源隔离 | 超时能力 | 日志 / trace | 与当前 Host awaiting poll path 契合度 |
| --- | --- | --- | --- | --- | --- |
| `asyncio.to_thread` | 只能取消 await wrapper；不能停止 OS thread。Docling 继续运行直到返回或崩溃。 | 无进程隔离；可能持有模型、PDF backend lock、GPU/CPU 资源。 | 可在 await 外层加 `wait_for`，但超时后线程仍跑。Docling `document_timeout` 可补充但不是强中断。 | 最简单，继承当前进程日志；但超时后后台线程日志归属和生命周期不清晰。 | 当前 CN/HK 下载已使用，集成成本最低；不能关闭 hard interrupt 风险。 |
| `loop.run_in_executor(ThreadPoolExecutor)` | 与 `to_thread` 本质相同；取消 `Future` 不会杀掉正在执行的线程。 | 可用专用线程池限制并发，但仍无强隔离。 | 可控排队与并发；不能强制停止 running task。 | 可给 executor 命名、限流；仍有悬挂线程问题。 | 比 `to_thread` 更显式，但不改变核心取消语义；不值得作为 hard interrupt 方案。 |
| 独立 process / subprocess | 父进程可在超时或 Host cancel 时 terminate，再 kill；能中断卡住的第三方同步调用。 | 强隔离 Docling 模型、PDF backend、native crash、内存膨胀；失败只污染子进程。 | 父进程可设置 wall-clock timeout；可叠加 Docling `document_timeout` 做软超时。 | 需要定义 stdout/stderr、结构化结果 envelope、临时文件/artifact、exit code、cleanup 语义。 | 最契合 Host 强约束：poll cancel 可触发父进程治理。但当前 Fins observation 只是 process-local thread record，需要新增 process-backed Docling job 边界或替换 Fins executor 局部实现。 |
| job queue / worker process | 取消语义取决于 worker：如果每个 convert 独立 child process，可 hard interrupt；如果长驻 worker 内直接同步 convert，则只能杀 worker。 | 可控并发、预热模型、队列背压；但 worker 污染和重启策略要设计。 | job lease / heartbeat / timeout 可治理；需要处理 orphan、retry、幂等。 | 最适合生产可观测性：job id、阶段事件、资源用量、stderr、产物路径都可归档。 | 与 awaiting poll path 很契合，外部 job id 可自然对应 Host wait record；但实现面比单次 subprocess 大，应单独 WU。 |

## 建议

### 不建议

不建议把当前 `asyncio.to_thread` 替换成 `run_in_executor` 作为主要修复。它只能改善并发池治理，不能改变“running thread 不可硬取消”的根因。

不建议把 Docling `document_timeout` 包装成“已支持取消”。它可以作为内部软超时配置加入候选方案，但源码已经说明阻塞 worker thread 仍可能继续运行。

不建议现在追逐原生 async API。当前安装版本没有这个公开能力；即使未来 Docling 增加 async wrapper，也必须确认其是否能取消底层 PDF backend / native inference，而不能只看函数是否 `await`。

### 建议的新 WU 方向

建议开新 work unit，目标不是“Docling async convert”，而是“Fins Docling convert process isolation and timeout governance”。

建议范围：

1. 在 Fins/Docling 边界定义窄转换接口：输入 PDF bytes、stream name、转换 profile；输出 Docling JSON bytes 或 typed failure。接口不要暴露 Host/Engine 状态。
2. 将单次 Docling convert 放入独立 child process 或 subprocess。父进程负责 timeout、terminate、kill、stderr/stdout 收集、临时文件清理。
3. Fins observation cancel 命中后，不只设置 cancellation state，还要能触达当前 convert process handle 并请求 terminate/kill。
4. 保留 Docling `document_timeout` 作为 child 内软超时，父进程 wall-clock timeout 作为硬上限。
5. 明确幂等和落盘边界：PDF blob 已落盘但 Docling JSON 未落盘时保持现有中间态语义；子进程失败不写半成品 JSON。
6. 对 CN/HK download 与 upload 同时覆盖；SEC upload 如复用同一 `DoclingUploadService`，也应纳入影响分析。

可复用参照：

- `dayu.runtime.interruptible_process` 已提供层中立 process 启动、wait、terminate、kill、bounded close primitive。
- Host `ProcessBackedToolExecutionCapsule` 已把 thread-backed 与 process-backed 的 interrupt 语义区分清楚：thread-backed 不能 terminate/kill OS thread；process-backed 可调用 terminate/kill。证据：`dayu/host/tool_runtime.py:1700-1740` 与 `dayu/host/tool_runtime.py:1762-1848`。

注意：当前 Fins Docling convert 发生在 awaiting tool 激活后的 Fins runtime producer 内，不是普通 read tool 的 `ToolDefinition.execution=ProcessBackedToolExecutionCapability` 路径。直接把 awaiting tool 声明成 process-backed 不能自动解决 producer 内的 Docling 子步骤，需要在 Fins ingestion runtime 或 Docling converter adapter 层引入可取消 process handle。

## Concise conclusion

Docling 2.90.0 当前没有可用于本仓库 `DocumentConverter.convert(DocumentStream)` 路径的原生 async / cancellable convert API。现有 `asyncio.to_thread` 风险判断准确。

## Recommendation

不要做 `to_thread -> run_in_executor` 的表面替换。下一步应开新 WU，把 Fins Docling convert 迁到独立 process/subprocess 边界，父进程治理 wall-clock timeout、terminate/kill、日志和结果 envelope；Docling `document_timeout` 只作为 child 内软保护。

## Residual risks

- 本调研基于本地安装的 `docling==2.90.0` 与 Controller 对当前 Docling 官方 API reference / 公开 enhancement issue 的补充核对；若未来升级 Docling，需要重新 introspection 新版本 API 与源码语义。
- process 隔离会引入模型加载成本、GPU/CPU 资源回收、跨进程序列化、日志归档和并发限流设计，需要单独评审。
- 若使用长驻 worker 复用模型，取消一个 stuck convert 可能需要杀整个 worker；这会影响吞吐和缓存，需要明确 worker 生命周期策略。
