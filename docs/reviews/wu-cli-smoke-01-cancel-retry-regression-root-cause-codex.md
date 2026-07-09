# WU-CLI-SMOKE-01 cancel retry regression root cause

## 结论

修复动机成立，且严重性没有被高估。本次回归不是 Coinbase/COIN 个例，而是两个边界问题叠加：

1. Host awaiting lifecycle 泄漏进 LLM-facing memory。`TOOL_AWAITING` 是 Host durable/event/audit 事实，不应让模型看到“等待、任务、启动、取消、poll、abandoned”等内部生命周期语义。验收原则：如果用户输入、工具参数、工具结果/最终回答相同，第二轮 LLM-facing memory 不应因为底层工具是 awaiting 还是非-awaiting 而不同。
2. SEC 下载 cancellation checker 没有贯穿 filing collection/headers/candidate collection 的所有远端请求入口。Host run 已进入 terminal 后，Fins 仍继续发起 browse-edgar、index.json、index-headers、candidate bytes 等请求。

正确边界：awaiting 只存在于 Host durable/event/audit；LLM-facing memory 只投影用户可见输入、普通工具结果、最终回答和 compact 后的业务连续性。若没有真正 tool result/resume summary，`TOOL_AWAITING` 不应生成独有 memory。

## 直接证据

- Host DB `host_runs` 显示第一轮 `run-e2d3ff48f8274cabb7235ce079716fc4` 为 `cancelled`，第二轮 `run-ec3b7372ac1f444b9d2a94ba484c6e07` 为 `succeeded`。
- `host_wait_records` 只有第一轮 `start_fins_download` wait，状态为 `cancelled`，`poll_last_outcome=abandoned`；第二轮没有 wait record。
- EventLog 第 42 号是第一轮 `TOOL_AWAITING`，参数 `{"ticker":"COIN"}`；第 46 号是 `CANCEL_REQUESTED`；第 47 号是 `RUN_CANCELLED`。
- 第二轮事件显示模型调用了 `list_documents(ticker=COIN)`，返回 `total=0 documents=[]`，随后调用 `get_current_time`，最后 final answer 声称下载已启动；没有 `start_fins_download` / `TOOL_AWAITING`。
- `interactive.log` 显示 Host cancel 在 23:12:14/15 左右完成，但 23:12:16 之后仍继续 SEC `index-headers.html`、browse-edgar、多个 `index.json` 请求，直到 23:12:20 才在文档边界输出取消日志。

## Root Cause

### Memory 边界根因

旧实现把 `TOOL_AWAITING` 直接投影进 `selected_recent_window` / `recent_evidence`，并生成 LLM-facing 文本描述“等待完成的外部工具步骤”和已接受参数。这把 Host 内部 awaiting lifecycle 暴露给模型，让第二轮对话的 memory 语义因为执行机制不同而不同。

这违反了总控裁决的边界：模型只发起普通 tool call；Host 发现长事务后暂停并恢复。对模型来说 awaiting 与非-awaiting 不应产生不同 memory 语义。

### SEC cancel 根因

底层 `_execute_sec_request(...)` 已支持 `cancellation_checker`，但多个 public downloader / collection 方法没有接收或转发该 checker：

- `resolve_company`
- `fetch_submissions`
- `fetch_json`
- `fetch_browse_edgar_filenum`
- `resolve_primary_document`
- `fetch_sc13_party_roles`
- `fetch_file_bytes`
- `_try_fetch_index_items`
- `_try_fetch_index_header_documents`
- `_try_fetch_primary_linked_html_files`

上层 SC13 browse 补拉、方向过滤、history submissions 补拉、6-K candidate 分类等调用这些入口时，实际传入的是 `None`，所以取消只能在后续文档边界被观察到。

## 非根因

- 不是 COIN 特例，不应硬编码 ticker。
- 不是 CLI 显示问题。CLI 已显示 `Cancelled.`，但后台 SEC 请求继续发生。
- 不是单纯 poller abandoned 问题。poller abandoned 已发生，问题是 Fins/SEC producer 的合作式取消传播不完整。

## 修复方向

- Conversation Memory 不消费 `TOOL_AWAITING`，也不消费 `RUN_CANCELLED` 来生成长期 memory。取消只作为当前 Host/CLI 生命周期处理，不成为 LLM 可推理的业务状态。
- SEC 下载 workflow 将 `cancel_checker` 贯穿到 collection、SC13、headers/index、6-K candidate 和 rejected artifact 下载路径。
- 测试必须断言 `TOOL_AWAITING` 不产生包含“等待 / awaiting / 外部工具 / 任务 / 启动 / 取消 / abandoned / poll”等词的 LLM-facing memory，并断言 collection 阶段取消不会继续进入 filing 文件请求。

