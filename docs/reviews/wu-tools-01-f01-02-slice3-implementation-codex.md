# WU-TOOLS-01-F01-02 Slice 3 Implementation / Fix - AgentCodex

## 改动摘要

- 在 `dayu/tools/doc_tools.py` 为五个 Doc tools 增加 legacy adapter execution context 注入：
  `list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section` 均声明
  `execution_context_param_name="execution_context"`，业务函数接收
  `BatchToolExecutionContext | None`。
- 新增文档工具取消 helper：
  `_resolve_doc_cancellation_token`、`_raise_if_doc_cancelled`、`_raise_doc_cancelled`。
  取消通过 `ToolBusinessError(code="tool_cancelled", ...)` 交给 legacy adapter 稳定投影为
  `ToolFailedOutcome(error="tool_cancelled")`。
- 按 Slice 3 要求补齐协作式 checkpoint：
  - `list_files`：glob 前、文件迭代内、return 前。
  - `get_file_sections`：processor 创建前、processor `list_sections` 后、fallback 全量读取前、Markdown 提取前。
  - `search_files`：`rglob` 前、每个文件迭代内、processor search / line scan 前、return 前。
  - `read_file`：每个 encoding attempt 前、`readlines` 后、行范围处理前。
  - `read_file_section`：processor 创建前、`processor.read_section` 前、子章节遍历前，并防止子章节遍历 helper 吞掉 `tool_cancelled`。
- 更新 `tests/tools/test_doc_tools_provider.py`：
  - 覆盖五个 Doc tools 预取消均返回 `tool_cancelled`。
  - 覆盖 `execution_context` 不进入 LLM-facing schema。
  - 覆盖 `search_files` 遍历中取消后不继续扫描后续文件。
  - 覆盖 `read_file` 首个编码失败触发取消后不再尝试 fallback 编码。

## 验证命令和结果

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`30 passed, 3 warnings`
  - warnings 均来自第三方 `edgar` deprecation warning，非本次改动引入的失败。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README 触发判断

- 本次修改了 `tests/tools/test_doc_tools_provider.py`，命中 AGENTS.md 的 `tests/` README 检查触发。
- 已阅读 `tests/README.md` 的更新边界：该文档要求新增测试层级时同步更新测试分层说明。
- 本次仅在既有 `tests/tools/` / Doc tools provider 分层内补充取消语义用例，没有新增测试层级、运行方式或测试目录职责，因此不更新 README。
- 未修改 `dayu/engine/`、`dayu/host/`、`dayu/fins/`、`dayu/config/`，也未改变 `UI / Service / Host / Agent` 分层关系或装配方式。

## Remaining Risks

- Doc tools 使用同步文件 I/O 与同步 processor API；checkpoint 只能在调用前后观察取消，不能中断已经进入的单次阻塞 `open/read` 或 processor 内部同步调用。
- `_try_create_processor` 仍保持原有宽泛降级语义；本 Slice 只在调用前后 checkpoint，不改变 processor 创建失败的 fallback 行为。
- 未引入工具私有取消状态；取消真源仍是 Host 注入的 `CancellationToken`，工具仅观察。
