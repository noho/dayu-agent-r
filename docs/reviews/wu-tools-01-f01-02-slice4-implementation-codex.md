# WU-TOOLS-01-F01-02 Slice 4 Implementation / Fix - AgentCodex

## 改动摘要

- 在 `dayu/fins/tools/fins_tools.py` 为九个 Fins read tools 增加 legacy adapter execution context 注入：
  `list_documents`、`get_document_sections`、`read_section`、`search_document`、`list_tables`、
  `get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts` 均声明
  `execution_context_param_name="execution_context"`，工具函数接收
  `BatchToolExecutionContext | None` 并把其中的 `CancellationToken` 传入 `FinsReadRuntime`。
- 移除 `read_section` 的历史 `**_kwargs` 吞参；该参数不属于当前 schema，也不能作为 token 传递通道。
- 在 `dayu/fins/tools/read_runtime.py` 为九个 read runtime 方法增加 keyword-only
  `cancellation_token: CancellationToken | None = None`，并新增 `_raise_if_fins_cancelled` /
  `_raise_fins_cancelled`，取消通过 `ToolBusinessError(code="tool_cancelled", ...)` 交给 legacy adapter
  稳定投影为 `ToolFailedOutcome(error="tool_cancelled")`。
- 按风险密度补齐 checkpoint：
  - repository 元数据 / source 列表 / primary source / processed capability 读取前后；
  - processor 创建、章节 / 表格 / 页面 / 报表 / XBRL capability 读取前后；
  - 文档、章节、表格、statement rows、XBRL facts 等结果组装循环内；
  - document identity alias 扫描、section semantic enrich、multi-query 聚合等 traversal 内。
- 在 `dayu/fins/tools/search_engine.py` 为 `_execute_query_search` 增加
  `cancellation_token` 参数，并在 exact search、expansion phase、每个 expansion query 的 processor
  search 前后检查取消，防止取消后继续 fallback / candidate search。
- 更新测试：
  - Fins read declarations 断言九个 read tools 均有 execution context 注入元数据。
  - `list_documents` pre-cancel 返回 `tool_cancelled`。
  - `search_document` 搜索过程中取消后停止后续候选查询。
  - `read_section` 在 processor read 前取消返回 `tool_cancelled`，且不调用 processor read。
  - `query_xbrl_facts` 在 facts 过滤 checkpoint 命中取消后返回 `tool_cancelled`。
  - combined tools acceptance 断言 `execution_context` / `cancellation_token` 不进入 LLM-facing schema。

## 验证命令和结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py -q`
  - 结果：`17 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`28 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`45 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

以上 warnings 均来自第三方 `edgar` deprecation warning，非本次改动引入的失败。

## README 触发判断

- 本次修改了 `dayu/fins/`，命中 AGENTS.md 的 `dayu/fins/README.md` 检查触发。
- 已阅读 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。该 README 记录 Fins package 的能力定位、两条执行路径、对外接口、公共契约、架构与稳定边界。
- 本次未改变 Fins read tools 名称、provider 装配方式、仓储协议边界、对外参数 schema 或 Host / Engine / Service 分层关系；read cancellation 属于已有 ToolRuntime 执行上下文在 read path 内部的协作式观察与 checkpoint 实现，因此不更新 `dayu/fins/README.md`。
- 本次修改了 `tests/`，命中 `tests/README.md` 检查触发。
- 已阅读 `tests/README.md`。本次只在既有 Fins provider / combined tools acceptance 分层内补充取消语义用例，没有新增测试目录、测试层级或运行方式，因此不更新 `tests/README.md`。

## Remaining Risks

- XBRL payload normalization 与 table row normalization 的具体 normalize helper 位于本 Slice allowed files 之外；本实现已在 helper 调用前后和 raw facts / normalized facts、table payload 返回后补 checkpoint，但没有修改 helper 内部每个 normalize 子步骤。
- Processor 内部自身的长 CPU / I/O 工作仍只能在调用边界前后观察取消；若某个 processor method 在内部长时间阻塞，需要后续 processor owner 在对应 processor 内补更细粒度 checkpoint。
