# Dayu 整体架构设计

本文档记录 Dayu 的仓库级设计决策。包内局部机制仍由对应包级 README
或专题设计文档承载；当某个设计原则会横跨 Engine、Host、Service、UI
或 runtime 时，优先写入本文档，作为后续实施与 review 的共同真源。

## 1. 日志与可观测性

Dayu 的日志用于诊断系统执行过程，不承担 UI 输出职责。面向用户的命令行
输出、smoke 汇总、交互界面展示应走各自的 UI / stdout 通道；日志只表达
系统内部执行路径、细节、告警和错误。

日志级别语义如下：

| 级别 | 用途 |
| --- | --- |
| `DEBUG` | 看清执行细节。用于有界的策略分支、计数、截断参数、cursor fingerprint、tool outcome、compact 前后 budget 等诊断信息。不得输出大 prompt、大 tool result、delta 全量、raw cursor 或 scope token。 |
| `VERBOSE` | 看清执行路径。用于 `session -> run -> attempt -> iteration` 边界、Engine 状态转移、Runner 调用开始 / 结束、tool loop 进入 / 退出、terminal 产出等骨架日志。它应比 `DEBUG` 更安静，适合人工跟踪一次 run 的主路径。 |
| `INFO` | 汇报重要信息。用于进程启动、smoke 摘要、run finished 摘要等调用方或运维人员需要知道的非异常信息。生产默认 `INFO` 应保持克制。 |
| `WARN` | 汇报可恢复异常。用于 provider 临时失败后 retry、context compact fallback、治理降级、非致命契约偏差等需要关注但本次执行仍可继续的情况。 |
| `ERROR` | 汇报本次操作失败。用于 run failed、工具执行不可恢复失败、provider 协议错误导致执行失败等。 |
| `CRITICAL` | 汇报系统 invariant / contract 被破坏。用于“按设计绝不应发生”的断言级事件，例如 Engine stream 结束但没有 terminal event。 |

`dayu.runtime.log_levels` 是层中立日志 level 数值真源，统一定义 Dayu 使用的
标准级别整数常量与 `VERBOSE=15` 数值；该模块无装配副作用，不注册 stdlib
level name、不安装 handler、不读取配置。当前 `dayu.runtime.log` 负责把
`VERBOSE=15` 注册为 stdlib level name `VERBOSE`，位于 `DEBUG=10` 与
`INFO=20` 之间。启用 `DEBUG` 时应
同时看到执行路径和细节；启用 `VERBOSE` 时应主要看到执行路径骨架；
启用 `INFO` 时不应看到单次 iteration / tool call 的内部过程。

执行路径日志的归属原则：

- Engine 负责记录 Engine 自身状态机路径：run 开始、attempt / iteration
  边界、Runner 调用、Runner event 分类后的关键决策、tool loop、fallback、
  continuation、terminal。
- Host 负责记录 Host 托管路径：run accepted、background task、EventLog
  写入终态、ToolRuntime 调用边界、context compact retry、fetch_more 路由、
  conversation memory 更新。
- EventStore 是存储事实层，默认不应在 `DEBUG` 下逐条打印 preview delta
  或 subscribe wait / batch 轮询过程；这些信息会淹没 Engine / Host 主路径。
  只有 append terminal、非法 append、订阅完成等存储诊断边界才适合输出。
- ToolRuntime 统一记录工具调用前后两侧边界，所有业务工具和 framework tool
  使用同一套日志键；日志可以输出 tool name、run/session、outcome、是否
  truncated、cursor fingerprint、event cursor，不得输出 raw cursor、
  scope token 或完整工具结果。
- Runner / provider 层可以记录 HTTP attempt、响应状态、provider request id
  等传输诊断信息，但不得泄漏 provider secret、完整 prompt 或大段响应。

日志字段命名统一使用以下词汇：

- `session_id`：会话级标识。
- `run_id`：一次 Host run 标识。
- `attempt` / `attempt_index`：一次 retry / compact retry 尝试。
- `iteration_id` / `iteration_index`：Engine 内一次模型调用与后续决策循环。

不使用 `turn` 表达 Host / Engine 执行路径。多轮会话可以在用户语义层描述为
多次 run，但日志字段仍使用 `run`、`attempt`、`iteration`。

## 2. 工具定义与执行边界

工具能力分为声明、治理和执行三个边界。

- `@tool(...)` 是工具声明入口，用于在工具现场同源声明 `ToolSchema`、
  截断声明、展示 metadata、标签和单工具 callable。
- `ToolDefinition` 是 Host / ToolRuntime 的装配输入，包含 schema、
  truncate、display、tags 与 `ToolCallable`；它不进入 Engine request，
  也不作为 Engine 稳定接口。
- 外部工具注册组件是工具发现 / 注册边界，产出业务 `ToolBundle` 并通过
  `HostToolingOptions` 传给 Host construction。Host 包不得 import 具体业务
  工具模块；新增工具应通过外部注册组件 / 配置 / Service composition 接入。
- `fetch_more` 不由外部业务 `ToolBundle` 提供；ToolRuntime factory 根据
  TruncationManager 注入 framework tool，生成 attempt-local effective
  `ToolBundle`。RunInputBuilder 投影给 Engine 的 `tool_schemas` 与
  ToolRuntime 执行使用的 `tool_executor` 必须来自同一个 effective
  ToolBundle。
- `ToolCallable` 是单工具调用协议，形状是
  `async (call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome`。
  工具函数可以通过闭包捕获 Web client、仓储、manager 等工具运行所需依赖；
  Host 仍只消费外部传入的业务 `ToolBundle`，不扫描业务工具模块。
- `ToolExecutor` 是 Host / ToolRuntime 治理后的 batch 执行入口，形状是
  `execute(BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。Engine 只调用
  这个入口，不调用单工具 callable。

Host 接收业务 `ToolBundle`；ToolRuntime factory 生成 effective `ToolBundle`，
把其中的 `ToolSchema` 投影给 Engine，并把 `ToolCallable` 包装进受治理的
`ToolExecutor`。权限、审批、限流、并发、内部 timeout、审计、长事务
awaiting、orphan cleanup 和工具级取消都属于 Host / ToolRuntime；
`dayu.contracts` 不提供默认执行器，也不定义 batch 内部执行策略。

Engine 只接收 `tool_schemas` 和 `tool_executor`。Engine 不导入、不持有、
不分支判断 `@tool`、`ToolDefinition`、`ToolCallable`、具体工具实现或工具
运行时治理对象。
