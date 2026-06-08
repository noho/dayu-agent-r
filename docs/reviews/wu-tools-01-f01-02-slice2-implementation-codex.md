# WU-TOOLS-01-F01-02 Slice 2 Implementation Review

## 改动摘要

- `search_web` 声明增加 `execution_context_param_name="execution_context"`，函数签名新增 `execution_context: BatchToolExecutionContext | None = None`。
- `search_web` 通过既有 `_resolve_execution_cancellation_token` 取得 Host 注入的 token，并在调用 `search_public_web` 前执行 pre-call checkpoint。
- `search_public_web` 新增 `cancellation_token: CancellationToken | None = None`，在查询 / 域名 / provider 归一化后、每个 fallback provider attempt 开始前、provider 返回结果后且过滤 / 返回前执行 checkpoint。
- provider 失败仍沿用原 fallback 逻辑；取消命中时抛出 legacy adapter 可投影的 `ToolBusinessError(code="tool_cancelled")`，避免继续尝试后续 fallback provider。
- `fetch_web_page` 生产行为未改，只补测试确认 Playwright fallback 收到的 token object 与 execution context token 是同一对象。
- combined ToolRuntime 验收测试补充确认 `search_web` 经 ToolRuntime / legacy adapter 路径拿到同一个 context cancellation token。

## 验证命令和结果

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`20 passed, 3 warnings in 1.09s`
  - warning：均来自 `edgar` 依赖的 deprecated module 提示，非本次改动引入。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README 触发判断

- 生产改动位于 `dayu/tools/web/`，未命中 AGENTS.md 中列出的 README 触发目录。
- 测试改动位于 `tests/`，已检查 `tests/README.md` 的更新约束。该 README 记录测试分层、运行方式与维护约定；本次只在既有 `tests/tools` Web provider 与 combined acceptance 分层内补覆盖，没有新增测试层级、运行方式或维护约定，因此不更新 README。

## Remaining Risks

- 本 Slice 不尝试中断已经进入同步 `requests` 的 provider HTTP 调用；仍依赖现有 bounded timeout 语义。
- 取消只在 provider attempt 边界和 provider 返回后协作式观察；如果 provider 内部阻塞到 timeout，取消响应会等到当前同步请求返回或超时。
- 未改 Host / Engine public contract，也未引入 adapter-wide cancellation outcome；search 取消仍按 legacy Web `tool_cancelled` failed outcome 投影。
