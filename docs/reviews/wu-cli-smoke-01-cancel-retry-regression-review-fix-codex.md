# WU-CLI-SMOKE-01 cancel retry regression review fix

## 接受的 review findings

### A. Memory 死分支

已接受并修复。`dayu.host.memory` 删除了 `_EVENT_TYPE_TOOL_AWAITING` 常量和 `TOOL_AWAITING` 专属 `pass` 分支。Conversation Memory 不再在代码路径中识别 awaiting 事件；durable memory consumer 也不订阅该事件。若测试或旧调用直接传入该事件，它不会产生 selected recent window 或 recent evidence。

### B. Docstring 异常声明

已接受并修复。补充了会传播 `SecDownloadCancelledError` 的 SEC cancellation path 文档，覆盖：

- `SecDownloader.resolve_company`
- `SecDownloader._resolve_company_via_browse_edgar_ticker`
- `SecDownloader.fetch_submissions`
- `SecDownloader.fetch_json`
- `SecDownloader.fetch_browse_edgar_filenum`
- `SecDownloader.resolve_primary_document`
- `SecDownloader.fetch_sc13_party_roles`
- `SecDownloader.fetch_file_bytes`
- `SecDownloader._try_fetch_index_items`
- `SecDownloader._try_fetch_index_header_documents`
- `SecDownloader._try_fetch_primary_linked_html_files`
- `classify_6k_remote_candidates`

只调整 docstring 的 `Raises` 说明，未改变运行时行为。

### 控制器补修

控制器发现 `_RelativeHtmlLinkExtractor.handle_starttag` 的 docstring 被误列为会抛 `SecDownloadCancelledError`。该 `HTMLParser` 回调没有 `cancellation_checker`，也不会抛出该异常；已修正为 `Raises: 无`。

### C. 精确验收测试

已接受并修复。新增测试 `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`，用相同 user input、普通 tool result 和 final answer 对比有无中间 `TOOL_AWAITING` 的 memory role/text 视图，断言 LLM-facing selected recent window 与 recent evidence 完全一致。

保留并调整原有 `TOOL_AWAITING` 测试：继续断言它不产生 LLM-facing memory，不包含 awaiting / waiting lifecycle / tool name / ticker 参数等文本；不再要求 direct projector 对未订阅事件没有 diagnostic。

## 验证结果

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py -q
```

结果：`41 passed`。

```bash
source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_downloader.py -q
```

结果：`82 passed, 3 warnings`。warnings 来自 edgartools deprecation。

控制器补修后追加运行：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/fins/test_sec_downloader.py -q
```

结果：`87 passed`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## 未处理观察

- 未重跑真实 asciinema/CLI smoke。当前 review fix 只触及 memory projection 死分支、docstring 和 deterministic tests；真实交互 smoke 仍属于最终人工验收或上层 smoke gate。
- 未扩大 SEC 取消实现范围。review finding B 只要求异常文档准确性，本轮没有改动取消行为，避免引入无关风险。
