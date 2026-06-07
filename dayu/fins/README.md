# Fins 开发手册

`dayu.fins` 是财报分析能力包，当前提供财报文件系统仓储、财报文档处理器、读取服务、read tools provider 和 ingestion runtime foundation。它不属于 Host / Engine / Service / UI 任一层，具体财报文档访问必须通过 `dayu.fins.storage` 下的仓储协议与实现完成。

## 边界

- `dayu.fins.storage` 是财报文档存取边界，包含公司元数据、源文档、processed 文档、blob 文件和批处理事务仓储协议与文件系统实现。
- `dayu.fins.processors` 复用 `dayu.documents.processors` 的共享文档处理器基础，补充财报表单、章节、表格和 XBRL 相关处理能力。
- `dayu.fins.tools.service.FinsToolService` 负责参数标准化、ticker / document_id 路由、processor 缓存和 read tool 业务结果构造。
- `dayu.fins.tools.provider.discover_tools` 是当前 ToolsDiscovery provider 入口，只暴露 read tools。
- `dayu.fins.ingestion_runtime` 提供下载 / 预处理请求、下载 adapter 协议、job record、job store、start、read、cancel，以及 download source adapter -> source/blob/rejected artifact 与 preprocess source -> processed pipeline 的 typed runtime foundation。
- `dayu.fins.service_runtime.DefaultFinsRuntime` 是 Fins shared assembly root，装配 read repositories、blob / filing maintenance repositories、processor registry、`FinsToolService`，以及 workspace-scoped ingestion runtime foundation / job store / download / preprocess pipeline；它不持有 Host、Service 或 EventLog。

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

当前 `dayu.fins` 仍只通过 provider 暴露 read tools；download / preprocess tool providers 尚未实现。

`DefaultFinsRuntime` 会装配 workspace-scoped ingestion runtime foundation。该 foundation 当前提供 typed download / preprocess request、download adapter protocol、job record、job store、start、read 与 cancel 基础能力。`start_download` 会先持久化 `queued` job record，再按 `normalize_ticker(...)` 后的 ticker / market 与 source 选择 Fins-owned adapter；有 adapter 时通过 source repository、blob repository 与 filing maintenance repository 写入源文档和 rejected filing artifact，无 adapter 时写入明确 unsupported-source failed 终态，不伪造成功。当前没有真实 SEC / CN / HK 网络下载 adapter。`start_preprocess` 会先持久化 `queued` job record，再通过 source repository 读取已存在源文档、通过 processor registry 生成 sections / tables 等 processed 产物，并通过 processed repository create / update 写入；`rebuild_processed=false` 时跳过已有 processed 文档，`rebuild_processed=true` 时重建。当前仍不暴露 Host wait adapter 或 tool provider。

job store 由 workspace root 派生，当前路径为 `.dayu/fins_ingestion/jobs`。它只保存 job governance records，不保存财报正文、processed payload 或 raw provider payload。

## 扩展约束

- 新增财报读取能力时，先扩展 storage protocol 或 processor 能力，再由 `FinsToolService` 暴露业务语义。
- 不得让 Host、Engine、Service 或 runtime 直接读取财报文件树。
- 不得迁移 OLD ToolRegistry、OLD TruncationManager、OLD `fetch_more` 或 OLD truncate / fetch-more projection。
- 面向 LLM 的工具 schema、错误、结果字段必须自解释，不暴露裸内部 ref / digest 代替业务语义。
