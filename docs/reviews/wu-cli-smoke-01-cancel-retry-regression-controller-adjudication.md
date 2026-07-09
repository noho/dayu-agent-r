# WU-CLI-SMOKE-01 cancel retry regression controller adjudication

## 裁决结论

`PASS_WITH_ACCEPTED_FIX`。本轮修复满足用户确认的核心语义：

- `awaiting` 是 Host 内部 lifecycle / governance 概念。
- 对 LLM 来说，awaiting 与非 awaiting 没有区别。
- 同样的 `USER_INPUT_ACCEPTED`、普通 `TOOL_RESULT_ACCEPTED` 与 `RUN_SUCCEEDED` 事实，有无中间 `TOOL_AWAITING`，第二轮 LLM-facing memory 的 role/text 视图必须完全一致。
- Conversation Memory 不得投影“任务已启动”“任务已取消”“等待”“poll”“abandoned”等 Host lifecycle 文本。

## 证据

AgentCodex root-cause artifact: `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-root-cause-codex.md`。

AgentCodex implementation artifact: `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-fix-codex.md`。

Initial review artifacts:

- `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-review-mimo.md`
- `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-review-ds.md`

Review-fix artifact: `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-review-fix-codex.md`。

Re-review artifacts:

- `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-rereview-mimo.md`
- `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-rereview-ds.md`

Controller validation:

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_downloader.py -q
```

Result: `123 passed, 3 warnings`。warnings 来自 edgartools deprecation。

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

Result: pass。

## Findings 裁决

### AgentMiMo F1

`LOW`。单 filing 下载中途取消的端到端测试仍可继续增强，但本轮 root cause 是 SEC collection/header/index/candidate 路径取消检查点缺失，且当前实现已经把 `cancellation_checker` 传入单 filing 文件处理、6-K prescreening 与 rejected artifact persistence。该 finding 不阻塞当前修复。

### AgentMiMo F2

`INFO`。`_cancelled_pipeline_completed_event` 签名风格不影响行为，不进入 fix gate。

### AgentMiMo F3

已接受并闭环。新增 `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`，精确断言有无 `TOOL_AWAITING` 时 LLM-facing selected recent window 与 recent evidence 的 role/text 视图相同。

### AgentMiMo F4 / AgentDS R2

不接受为生产代码 fix。`build_conversation_memory_snapshot_from_events` 是测试 direct projector helper，不代表 durable consumer production path；production `ConversationMemoryProjectionConsumer` 已通过 event filter 不订阅 `TOOL_AWAITING`。为了让 direct projector 测试的 diagnostics 为空而在 `dayu.host.memory` 增加 `TOOL_AWAITING` 特判，会重新让 memory 层识别 Host waiting lifecycle，违背用户裁决的 LLM-facing 边界。

### AgentDS R1

已接受并修复。`persist_rejected_filing_artifact` 会在取消检查点抛出 `SecDownloadCancelledError`，docstring 已补充该异常声明。

## Controller 裁决

本轮变更可以进入 accepted commit。剩余 LOW/INFO findings 不影响用户报告的 cancel/retry regression，也不改变 LLM-facing memory 语义。后续若需要补充更宽的 Fins cancel E2E coverage，应作为测试增强处理，不应重新引入 awaiting memory projection。
