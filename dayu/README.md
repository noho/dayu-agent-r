# Dayu 开发手册总览

本文档是 `dayu/` 包的开发手册总览，记录整体架构、设计意图、稳定边界、扩展入口、代码阅读顺序。

## Agent更新约束【必须遵守】

- 本文档不写过程状态，只保留稳定说明。

## 设计目标

- 宿主强约束下的 LLM in the loop。

## 整体架构

Dayu 的整体架构是：

```text
UI -> Service -> Host -> Engine
```

这条链路表达的是控制权和依赖方向：

- `UI` 负责用户交互入口，只处理展示、输入收集与命令触发。
- `Service` 负责业务请求受理与场景装配，把用户意图转成可执行请求。
- `Host` 负责 Agent 运行宿主边界，拥有 session / run 生命周期、取消、治理、工具运行时与恢复策略。
- `Engine` 负责执行已准备好的模型交互、Runner / Agent 状态机与强类型事件流。

依赖只能沿 `UI -> Service -> Host -> Engine` 向下发生；下层不得反向依赖上层。Engine 不理解 UI、Service 或 Host 的治理细节；Host 不承载财报业务语义；Service 不绕过 Host 直接控制 Engine。

`dayu.contracts` 承载跨层共享协作契约。契约层不得依赖具体业务层或执行层实现。

财报领域能力属于独立领域边界；财报文档存取必须通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成，不应泄漏到 Engine 或 Host 内部。

## 术语约定

以下术语用于描述 Agent 执行链路。包级 README 和设计文档应优先使用这些词，避免同一概念多名并存。

- `session`：一条可持续的会话上下文。它属于 Host / 上层语义，Engine 不持有 session 生命周期。
- `run`：一次 Agent 执行请求。一个 session 可以包含多次 run；Engine 只处理单次 run 的执行语义。
- `attempt`：Host 为完成一次 run 发起的内部尝试。attempt 可用于 retry、恢复或治理，不进入 Engine 执行状态机。
- `iteration`：Engine 内一次模型调用与后续决策循环。一次 run 可以包含多次 iteration，例如普通 tool loop 或 final-answer continuation。

`turn` 不用于描述 Engine / Runner 执行路径；如需表达用户视角的多轮对话，应在 UI / Service / Host 语义内明确其与 `session`、`run` 的关系。

## Runtime

`dayu.runtime` 是层中立运行期基础设施包，不属于 `UI / Service / Host / Engine` 任一业务层。

公共运行时能力应优先沉淀在 `dayu.runtime`，但不得把业务语义、Host 治理状态或 Engine 协议状态机放入 runtime。

## 日志与可观测性

Dayu 的日志用于诊断系统执行过程，不承担 UI 输出职责。面向用户的命令行输出、smoke 汇总、交互界面展示应走各自的 UI / stdout 通道；日志只表达系统内部执行路径、细节、告警和错误。

日志级别语义如下：

| 级别 | 用途 |
| --- | --- |
| `DEBUG` | 看清执行细节。用于 Engine / Runner 的有界策略分支、事件分类、计数、finish reason、usage token、retry 判断等诊断信息。不得输出大 prompt、大 tool result、delta 全量、provider secret 或大段响应。 |
| `VERBOSE` | 看清执行路径。用于 Engine run 开始 / 结束、iteration 边界、Runner 调用开始 / 结束、tool loop 进入 / 退出、fallback / continuation 与 terminal 产出等骨架日志。它应比 `DEBUG` 更安静，适合人工跟踪一次 run 的主路径。 |
| `INFO` | 汇报重要信息。用于进程启动、smoke 摘要、run finished 摘要等调用方或运维人员需要知道的非异常信息。生产默认 `INFO` 应保持克制。 |
| `WARN` | 汇报可恢复异常。用于 provider 临时失败后 retry、可降级协议差异等需要关注但本次执行仍可继续的情况。 |
| `ERROR` | 汇报本次操作失败。用于 Engine run failed、provider 协议错误导致执行失败等。 |
| `CRITICAL` | 汇报系统 invariant / contract 被破坏。用于按设计绝不应发生的断言级事件，例如 Engine stream 结束但没有 terminal event。 |

`dayu.runtime.log_levels` 是层中立日志 level 数值真源，统一定义 Dayu 使用的标准级别整数常量与 `VERBOSE=15` 数值；该模块无装配副作用，不注册 stdlib level name、不安装 handler、不读取配置。

当前 `dayu.runtime.log` 负责把 `VERBOSE=15` 注册为 stdlib level name `VERBOSE`，位于 `DEBUG=10` 与 `INFO=20` 之间。启用 `DEBUG` 时应同时看到执行路径和细节；启用 `VERBOSE` 时应主要看到执行路径骨架；启用 `INFO` 时不应看到单次 iteration / tool call 的内部过程。

执行路径日志的归属原则：

- Engine 负责记录自身状态机路径：run 开始、iteration 边界、Runner 调用、Runner event 分类后的关键决策、tool loop、fallback、continuation、terminal。
- Runner / provider 层负责记录传输诊断信息：HTTP attempt、响应状态、provider request id、retry / backoff、SSE idle heartbeat / timeout 等。
- Engine / Runner 日志不得泄漏 provider secret、完整 prompt、完整工具参数、完整工具结果、delta 全量或大段响应。

日志字段命名统一使用以下词汇：

- `run_id`：一次 Engine run 标识。
- `iteration_id` / `iteration_index`：Engine 内一次模型调用与后续决策循环。
- `provider` / `request_id`：Runner / provider 传输诊断标识。

## Contract Ownership

公共契约只承载层间协作协议，不承载业务语义真源、治理语义真源或某一层的内部状态机。

设计任何 contract 时，必须先回答语义真源在哪一层：

- UI 展示语义归 UI；公共契约只表达 UI 需要调用下层的稳定输入输出。
- Service 业务受理语义归 Service；公共契约不沉淀业务流程细节。
- Host 治理语义归 Host；session / run 生命周期、取消、恢复、工具治理等不进入 Engine 契约。
- Engine 执行语义归 Engine；Runner / Agent 事件流和模型交互状态机不向上泄漏内部实现。
- 财报领域语义归领域能力边界；公共契约不直接表达财报存储、解析或指标规则。

因此，`dayu.contracts` 只能放跨层都需要理解的协作对象，例如工具调用请求、工具执行结果、取消观察 token 等。若一个类型只有某一层理解，或者携带该层私有状态，它应留在该层内部；如果多层都需要读写它，应优先重新审视边界，而不是把它提前公共化。
