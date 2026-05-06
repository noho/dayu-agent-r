# Code Review 指南

本文档是本仓库的日常 code review prompt。执行 review 的 Agent 只审查当前仓库中已经存在的代码、测试与文档；不得引用仓库外材料、迁移过程或尚未成为当前代码事实的草稿来替当前代码找理由。

## 1. Review 范围

默认审查：

- `dayu/`
- `tests/`
- 与当前变更直接相关的 `docs/`
- README、配置、约束文件、脚本和依赖锁文件（仅在变更触发时）

只依据当前仓库中的代码真源、测试真源、README 职责说明和本指南做判断。若文档与代码不一致，以当前代码和测试为直接证据，同时报告文档漂移。

## 2. 总原则

- 必须沿真实代码路径逐行走读，禁止猜测。
- root cause 必须来自同一条逻辑 / 数据路径上的直接证据。
- 先判断问题动机是否成立；不要把风格偏好包装成 bug。
- 架构固定为 `UI -> Service -> Host -> Engine`，禁止反向依赖。
- `dayu.runtime` 是层中立公共运行时基础设施，不属于任一业务层，不得承载业务语义或治理状态。
- 下层接口设计必须假设上层不存在，只表达本层稳定输入、输出和协作协议。
- 财报文档存取必须且只能通过 `dayu.fins.storage` 下的仓储协议与实现完成。
- 禁止兼容 wrapper / facade / re-export，除非它本身提供新的有效语义。
- 禁止 `Any`、`object`、无类型参数、无类型返回值。
- 工具 schema 内的字面量字符串是合理例外，不按 magic string 报告。
- review 先列 findings；不要先写总结，不要泛泛表扬，不要把编码风格当成主要问题。

## 3. Review 结果格式

默认写入：

```text
docs/reviews/code-review-YYYYMMDD-HHMM.md
```

如果用户指定输出路径，以用户指定路径为准。每条 finding 使用以下格式：

```text
### 编号-未修复-[严重程度（低/中/高/严重）]-finding 简述
- **入口/函数**: 问题发生在什么执行入口或函数
- **文件(行号)**: 具体位置
- **输入场景**: 什么输入会触发问题
- **实际分支**: 代码实际走到了哪个分支
- **预期行为**: 按当前系统设计应该如何处理
- **实际行为**: 现在返回了什么、写入了什么状态、或漏做了什么
- **直接证据**: 判断条件、参数传递路径、返回值或状态更新位置
- **影响**: 错误 answer / 错误状态 / 静默失效 / 不可恢复 / 局部行为错误
- **建议改法和验证点**
- **修复风险（低/中/高）**
- **严重程度（低/中/高/严重）**
```

review 结束后，按严重程度和修复风险给出汇总列表。没有发现问题时，也要说明已检查范围、已运行验证和残余风险。

## 4. 业务逻辑 Review

本节只检查真实执行链上的“输入 -> 分支 -> 输出 / 副作用”是否正确，不检查实现风格是否“像是对的”。

### 4.1 端到端执行链路

以真实入口为起点检查完整主链路：

```text
UI -> Service -> Host -> Engine -> Host -> Service -> UI
```

至少覆盖：

- 正常输入 -> 正常 answer 返回 UI。
- 正常输入 + tool calling -> tool 结果回填 -> 继续执行 / 结束。
- tool 失败 / model 失败 / timeout / cancel / interrupt -> 是否进入预期失败分支。
- retry / redelivery / continuation -> 是否基于稳定事实推进。
- 非法输入 / 非法 override / 缺失 prompt / 缺失 config / 不支持参数组合 -> 是否明确拒绝、归一化、降级或 fail closed。

必须报告：

- 参数已传入但最终未生效。
- 分支应触发却未触发。
- 错误被吞掉后继续执行。
- 结果返回上层时语义已漂移。
- 状态已失败但 UI / caller 仍看到成功。

### 4.2 参数传递、覆盖优先级与生效点

对每个关键参数检查：

- **来源**：CLI、配置、请求、manifest、调用参数还是默认值。
- **覆盖关系**：默认值、配置值、请求值、override 谁优先。
- **落点**：最终在哪一层、哪个函数、哪个字段被消费。
- **失效处理**：非法值、空值、缺失值、类型错误值是否明确处理。

必须报告：

- 参数只传到中间对象但没有被最终执行层读取。
- 参数在链路中被重新默认化、覆盖、丢失或被不同层不一致解释。
- 显式参数被塞入 metadata、extra payload、开放 JSON 袋。
- 上层依据返回值认为参数已生效，但下游实际没有按该参数执行。

### 4.3 分支条件与路由

检查所有关键 `if` / `elif` / `match` / dispatch / router 是否由真正决定该分支的事实驱动，而不是由间接信号、历史标记或碰巧相关字段驱动。

必须报告：

- 宽条件抢先命中，导致更具体分支不可达。
- 条件重叠但没有明确优先级。
- 缺少默认分支，异常输入悄悄落空。
- router 同时承担参数转换、路由、结果合并，导致分支逻辑被误复用。
- 分支条件不能直接表达真实业务含义。

### 4.4 函数级执行链

对关键 public 函数，以及分支复杂、状态更新复杂、I/O 边界明显的 private helper，按以下顺序展开：

```text
入参 -> 条件判断 -> 下游调用 -> 返回值 / raise -> 副作用
```

必须检查：

- 正常入参域。
- `None`、空字符串、空列表、缺失字段、非法枚举、错误类型、越界值、互相冲突的参数组合。
- 调用下游前是否满足下游前置条件。
- 返回值、异常、状态变更是否与调用方预期一致。
- 某分支是否更新了部分状态后抛错，留下半提交状态。

## 5. 架构与依赖

当前分层固定为：

```text
UI -> Service -> Host -> Engine
```

目录职责：

| 层 / 模块 | 典型目录 | 职责边界 |
|---|---|---|
| UI | `dayu/cli/`, `dayu/ui/`, `dayu/web/`, `dayu/wechat/` | 用户交互入口 |
| Service | `dayu/service/`, `dayu/services/` | 业务理解与请求受理 |
| Host | `dayu/host/` | 通用托管执行、会话、治理、恢复 |
| Engine | `dayu/engine/` | 执行已准备好的模型交互、Runner/Agent 状态机 |
| Runtime | `dayu/runtime/` | 层中立运行期基础设施 |
| 共享契约 | `dayu/contracts/` | 层间共享协作契约 |
| 领域能力 | `dayu/fins/` | 财报工具和处理能力 |

检查项：

- Engine 不得 import Host / Service / UI 的具体实现。
- Host 不得 import Service / UI 的具体实现。
- Service 不得 import UI 的具体实现。
- `dayu.runtime` 不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `dayu.contracts` 不得 import 任一具体业务层或执行层。
- `dayu.engine.contracts` 可以依赖 `dayu.contracts`，不得依赖 Host / Service / UI / fins。
- 上层不得绕过 Host 直接控制 Engine。
- 下层接口不得泄漏上层治理、业务受理或展示状态。

必须报告：

- 任何反向 import。
- 任何跨层穿透调用。
- 任何让 Engine 理解 Host 治理、Service 业务受理、UI 展示状态的类型或字段。
- 任何让 Engine 直接读取财报文件、fins 目录或 fins storage 具体实现的路径。
- 任何 `dayu.runtime` 承载业务语义、Host 治理状态或 Engine 协议状态机。

## 6. 契约归属

契约归属判定规则：

> 如果语义真源在一方，另一方只是调用方，则契约落在语义真源所在层；如果两个层都需要独立实现、产生、解释或持久化它，且它描述的是层间协作协议而不是某一层的调用参数，则契约落在公共契约。

当前约定：

- `dayu.contracts`：层间共享协作契约。
- `dayu.engine.contracts`：Engine 语义真源契约。

检查项：

- `CancellationToken` 属于共享协作契约。
- `ToolExecutor` 属于共享协作契约，且只暴露执行所需最小表面。
- `ToolExecutionRequest`、`ToolExecutionOutcome`、`ToolResultEnvelope`、`ToolAwaitSpec` 属于共享协作契约。
- `RunnerSpec`、`RunnerCallOptions`、`AgentRunRequest`、`AgentPolicy` 属于 Engine 语义真源契约。
- `EngineEvent`、`RunnerEvent`、`AgentRunResult` 属于 Engine 语义真源契约。
- 取消公共终态由结构化 run cancelled event / outcome 表达，不应通过公共取消异常表达。

必须报告：

- 因“被多个层 import”而错误迁入公共契约的单层语义真源类型。
- 某一层为了实现另一层内部类型而反向贴合该层设计。
- 公共契约中出现 `Any`、`object`、裸 `dict`、裸 `list`、开放 metadata 语义袋。

### 6.1 Engine 契约专项

检查项：

- `dayu.contracts.__all__` 必须是共享协作契约白名单。
- `dayu.engine.__all__` 不得导出未实现入口、实现类占位或取消异常。
- `AsyncRunner` Protocol 只能暴露 Runner 调用、能力查询、资源关闭所需最小表面。
- `RunnerEvent` 不得包含 Host 治理字段，例如 `session_id`、`run_id`、`sequence`、`event_id`。
- `EngineEvent` 必须包含 Host 可观察所需的稳定字段，例如 `event_id`、`sequence`、`occurred_at`、`session_id`、`run_id`、`type`、`data`。
- terminal event 集合必须封闭，且 final / failed / cancelled / suspended 互斥。
- `ToolExecutionOutcome` 必须是封闭联合；新增分支必须有显式处理和测试。
- `ToolAwaitSpec` 不得塞进普通工具结果 metadata。
- metadata 只能承载非契约 debug / observer hint，不得承载显式契约事实。

必须报告：

- Engine contract 中出现 Host / Service / UI / fins 具体概念。
- Engine contract 导出实现细节或占位入口。
- 弱类型绕过封闭联合或事件 data。

## 7. Runner 专项

当仓库中存在 Runner 实现时，必须检查：

- Runner 只产出 `RunnerEvent`，不产出 `EngineEvent`。
- Runner 不执行工具，不依赖 `ToolExecutor` / `ToolRegistry`。
- Runner 不实现 `set_tools`，不接受 `call(**extra_payloads)`。
- Runner 不读取配置文件来获得运行规格；运行规格必须来自显式强类型输入。
- provider 私有参数必须来自强类型 provider extension 或显式字段。
- OpenAI-compatible payload、SSE、tool call delta、usage、finish reason、HTTP error、retry/backoff、reasoning 标签处理必须以当前协议 adapter 的直接证据审查。
- cancellation 只作为阻塞边界观察；结构化取消终态由 Engine / Agent 层提升。
- stream 与 non-stream 两条路径的最终事件语义必须一致。
- content delta、reasoning delta、tool call delta、tool calls completed、content completed、usage、done / error / cancel 边界不得存在顺序冲突。
- response / stream / HTTP session 必须在成功、错误、取消和 close 边界完整释放。

必须报告：

- 为实现方便引入 `Any`、开放 `extra_body` 任意袋、`**kwargs`。
- Runner 导入 Host / trace / fins / tools / processors。
- Runner 把取消、失败或最终回答提升成 Host 可见终态。
- RunnerEvent 顺序无法被后续 Engine loop 无歧义消费。
- 使用隐式布尔标记、魔法字符串或弱类型 payload 表达关键状态迁移。

## 8. Agent / Engine Loop 专项

当仓库中存在 Agent loop 时，必须检查：

- Agent 是 run-scoped 状态机；不得成为跨 run 的持久对象真源。
- `run_agent_messages` / `run_agent_and_wait` 等公共入口是否只接受强类型 request / policy / runner spec / cancellation。
- Runner 调用、Runner event 消费、tool batch、continuation、fallback、final / failed / cancelled / suspended terminal 是否形成唯一终态。
- `run_cancelled` 必须表示 Host 取消请求已被 Engine 接受并收口为取消终态；取消不是普通 error，也不能伪装成工具失败或最终回答。
- tool calling 必须保持：模型 tool call -> `ToolExecutionRequest` -> `ToolExecutionOutcome` -> LLM-facing tool message 注入下一轮 Runner。
- ToolExecutor 只由 Engine 消费；Engine 不持有 ToolRegistry，不发现工具，不治理权限。
- continuation 若已实现，必须固定其工具策略、次数限制、内容拼接、取消优先和 max iteration 关系。
- content filter、length、tool calls、protocol error、provider error、cancellation 的优先级必须可证明。
- Runner close 必须在 final / failed / cancelled / suspended / outer cancellation 边界执行一次且至多一次。

必须报告：

- 双 terminal、无 terminal 或 terminal 顺序冲突。
- cancellation 被普通 error / tool failed / final answer 吞掉。
- tool batch 未完整配对却注入 LLM-facing messages。
- continuation、force-answer、max_iterations、consecutive failed tool batches 互相覆盖。
- Engine 在没有 Host 真源的情况下实现 conversation memory、transcript、context compaction、resume 或 tool runtime 治理。

## 9. 状态机 Review

凡是存在“真源状态 + 触发条件 + 状态写入 + 对外事件 / 副作用 + 后续收敛”的闭环，都按状态机审查。

最低展开格式：

- 输入事实
- 状态读取
- 分支判断
- 状态写入
- 对外事件 / 返回值 / 异常
- 下游消费与后续收敛

当前必须重点检查：

- Contract 事件终态集合是否封闭。
- Outcome 联合是否封闭。
- 包根导出白名单是否形成稳定边界。
- Runner 协议状态机。
- Agent iteration 状态机。
- Host pending turn、reply outbox、conversation archive、resume / retry / redelivery 状态机（如果当前代码中已存在）。

每个状态机至少展开：

- 一条正常主路径。
- 一条失败路径。
- 一条取消 / 超时 / interrupt 路径。
- 一条恢复路径：resume / retry / redelivery / continuation 中与该状态机关联的真实路径。
- 一条并发或调和路径：竞争写入、孤儿状态、cleanup、外部终态收敛。

必须报告：

- 状态真源不唯一。
- 终态不吸收。
- 状态转移依赖日志、命名、布尔缓存、临时推断或“看起来像完成了”的间接迹象。
- 正常路径和异常路径使用不同转换规则。
- cleanup / resume / retry 只修复局部状态，没有把相关状态机一起调和。
- 外部事件、返回值、持久化事实互相冲突。

## 10. 非预期输入

必须主动检查：

- 缺失必填参数。
- 类型错误。
- 非法枚举 / 非法字符串。
- 空内容 / 空消息 / 空 prompt。
- 越界数值 / 负数 / 超长输入。
- 重复请求 / 冲突参数 / 已终态再次推进。

合理策略只能是：

- 明确拒绝。
- 合法归一化。
- 安全降级。
- 有边界的重试。
- 安全 no-op。

“碰巧没崩”“吞错继续跑”“落入正常分支但语义已错”都必须报告。

## 11. 返回值、副作用与外部可见结果

同时检查：

- 返回给上层 / UI 的结果。
- 持久化状态更新。
- pending turn / resume snapshot / reply outbox / conversation archive 等外部状态。
- event / log / trace / diagnostics 中记录的执行事实。

必须报告：

- 函数返回成功，但状态未提交或提交一半。
- UI 看到完成，但 Host / 存储侧仍处于可恢复或运行中状态。
- 错误分支返回看似成功的默认值，掩盖真实失败。
- trace / log / event 与真源状态冲突。

## 12. README 与 Docs

README 只写当前已落地事实，不写未来设计。

触发检查：

- 修改 `dayu/engine/`：检查 `dayu/engine/README.md`。
- 修改 `dayu/host/`：检查 `dayu/host/README.md`。
- 修改 `dayu/fins/`：检查 `dayu/fins/README.md`。
- 修改 `dayu/config/`：检查 `dayu/config/README.md`。
- 修改测试分层或运行方式：检查 `tests/README.md`。
- 修改整体分层、装配方式、Host / Engine 边界：检查 `dayu/README.md`。
- 修改用户命令、安装、配置、CLI：检查根 `README.md`。

如果代码已经落地但文档仍停留在草案、旧术语或过期设计表述，应报告文档漂移。

必须报告：

- README 宣称未实现能力已可用。
- README 否认当前已实现能力。
- README 把 Host / Service / UI 能力写进 Engine 包职责。
- README 示例导入路径、命令、参数名已经过期。

## 13. 测试与验证

每次 code review 必须记录实际运行结果。

常规：

```bash
source .venv/bin/activate
pytest <受影响测试> -q
pyright
git status --short
```

若测试或 pyright 失败，除非已有明确外部环境原因，否则作为阻塞问题。

检查测试本身：

- 测试是否覆盖正常路径、失败路径、取消路径和边界路径。
- 测试是否只为了保旧行为而压制新架构。
- 测试是否用 `Any` / `object` / `type: ignore` 绕过真实契约。
- README 守护测试是否守当前事实，而不是旧事实。

## 14. 本文档维护规则

每次完成一个可合并的代码切片，都必须检查并更新本文档：

- 新增当前已落地能力的专项 review 检查项。
- 删除或降级已不适用的草案、临时表述。
- 保持架构口径为 `UI -> Service -> Host -> Engine`。
- 保持契约归属规则与当前代码真源一致。
