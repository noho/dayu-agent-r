# WU-CLI-SMOKE-01 cancel retry regression fix

## 变更摘要

本次修复按总控最终裁决执行：awaiting 只属于 Host durable/event/audit 与 wait governance，不进入 LLM-facing memory schema。若用户输入、工具参数、工具结果或最终回答相同，第二轮 LLM-facing memory 不应因为底层工具是 awaiting 还是非-awaiting 而不同。

### Host memory

- `dayu.host.memory` 不再把 `TOOL_AWAITING` 投影为 selected recent window 或 recent evidence。
- `dayu.host.durable.memory` 的 projection consumer event filter 不再订阅 `TOOL_AWAITING`。
- 删除旧的 awaiting 参数投影文本生成逻辑，避免向模型暴露“等待、外部工具、任务、启动、取消、poll、abandoned”等 Host 生命周期语义。
- 取消状态不进入长期 memory；取消仍由 Host/CLI 当轮生命周期处理。

### Fins SEC cancellation

- SEC downloader 的 public fetch/resolve/listing 边界补齐 `cancellation_checker` 参数，并向底层 `_http_get_json`、`_http_get_bytes`、`_http_download`、index/header/candidate helper 继续传递。
- SEC download workflow 在公司解析、submissions 拉取、history submissions、SC13 Browse EDGAR 补选、SC13 方向过滤、index/header/candidate collection、6-K remote candidate、rejected artifact persistence 和单 filing 文件处理路径传播同一个 cancel checker。
- collection 阶段观察到取消时，stream 直接产出 `cancelled` 的 `PIPELINE_COMPLETED`，不继续进入 filing 文件列表或下载请求。
- `SecDownloadCancelledError` 在 cancellation path 继续向上冒泡，不再被 index/header helper 当作普通网络失败吞掉。

### 文档

- `dayu/host/README.md` 更新 Conversation Memory projection 边界：Memory 不消费 Host waiting lifecycle。
- `dayu/fins/README.md` 更新 SEC 下载取消检查点范围。
- `tests/README.md` 更新 Host memory 与 SEC collection 取消测试覆盖说明。

## 测试覆盖

- `tests/host/test_memory_projection.py` 断言 `TOOL_AWAITING` 不产生 LLM-facing memory，不包含等待/awaiting/外部工具/任务/启动/取消/abandoned/poll 等文本，并确认 durable memory consumer 不订阅 awaiting。
- `tests/fins/test_sec_pipeline_download_stream.py` 增加 collection 阶段取消测试：history submissions 拉取命中取消后，不继续进入 `list_filing_files`。
- `tests/fins/test_sec_downloader.py` 的 HTTP/collection 替身签名同步真实 downloader 边界，保证测试能观察 cancellation checker 传递。
- `tests/fins/test_sec_pipeline_download.py` 的 downloader stub 同步新的取消传播协议。

## 验证

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_downloader.py -q
```

结果：`122 passed, 3 warnings`。warnings 来自 edgartools deprecation。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## 剩余风险

- 本次未重跑真实 `asciinema` 交互 smoke；修复通过 DB/log 直接证据定位，并用 deterministic unit/integration tests 覆盖根因边界。
- SEC 下载依然是合作式取消；正在执行中的单个同步第三方调用或已发出的 HTTP 请求不能被伪装成强制中断，但新检查点会阻止取消后继续进入后续 collection/header/index/candidate 请求。
- Awaiting 仍存在于 Host durable truth 与 wait audit 中；本次只收紧 LLM-facing memory，不改变 Host wait/resume durable state machine。
