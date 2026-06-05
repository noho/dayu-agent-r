# Fins 开发手册

`dayu.fins` 是财报分析能力包，当前提供财报文件系统仓储、财报文档处理器、读取服务和 read tools provider。它不属于 Host / Engine / Service / UI 任一层，具体财报文档访问必须通过 `dayu.fins.storage` 下的仓储协议与实现完成。

## 边界

- `dayu.fins.storage` 是财报文档存取边界，包含公司元数据、源文档、processed 文档、blob 文件和批处理事务仓储协议与文件系统实现。
- `dayu.fins.processors` 复用 `dayu.documents.processors` 的共享文档处理器基础，补充财报表单、章节、表格和 XBRL 相关处理能力。
- `dayu.fins.tools.service.FinsToolService` 负责参数标准化、ticker / document_id 路由、processor 缓存和 read tool 业务结果构造。
- `dayu.fins.tools.provider.discover_tools` 是当前 ToolsDiscovery provider 入口，只暴露 read tools。
- `dayu.fins.service_runtime.DefaultFinsRuntime` 只装配 read tools 需要的仓储实现、processor registry 与 `FinsToolService`，不持有 Host、Service、EventLog 或 ingestion job manager。

## 读取路径

读取工具的执行路径为：

```text
ToolsDiscovery
  -> dayu.fins.tools.provider.discover_tools
  -> DefaultFinsRuntime.create(workspace_root=...)
  -> dayu.fins.storage filesystem repositories
  -> FinsToolService
  -> dayu.fins.processors / dayu.documents.processors
  -> dayu.tools._legacy_adapter
  -> current ToolDefinition / ToolRuntime
```

启用 read tools 时，Provider config 必须显式提供绝对 `workspace_root`。Provider 不从当前工作目录或环境变量猜路径；默认包内配置保持 disabled 且 `workspace_root=null`，启用时必须由 workspace overlay 提供真实绝对路径。`include_read_tools=false` 时，provider 返回空工具集且不解析 `workspace_root`。

当前 read tools：

- `list_documents`
- `get_document_sections`
- `read_section`
- `search_document`
- `list_tables`
- `get_table`
- `get_page_content`
- `get_financial_statement`
- `query_xbrl_facts`

这些工具统一带 `fins` tag。需要截断的工具声明当前 `dayu.contracts.tool_schema.ToolTruncateSpec`；实际截断和 `fetch_more` 由 Host ToolRuntime 负责。

## Ingestion 状态

当前 provider 不暴露下载 / 预处理 ingestion tools。旧 ingestion 工具是 `start/status/cancel` 后台 job 轮询模型，需要等待当前 ToolRuntime 的 `ToolAwaitingOutcome` 或 wait-adapter 语义承接后再迁移。

## 扩展约束

- 新增财报读取能力时，先扩展 storage protocol 或 processor 能力，再由 `FinsToolService` 暴露业务语义。
- 不得让 Host、Engine、Service 或 runtime 直接读取财报文件树。
- 不得迁移 OLD ToolRegistry、OLD TruncationManager、OLD `fetch_more` 或 OLD truncate / fetch-more projection。
- 面向 LLM 的工具 schema、错误、结果字段必须自解释，不暴露裸内部 ref / digest 代替业务语义。
