# Code Review 指南

本文档是本仓库的日常 code review prompt。执行 review 的 Agent 只审查当前仓库中已经存在的代码、测试与文档；不得引用仓库外材料或尚未成为当前代码事实的草稿来替当前代码找理由。

## 1. Review 范围

默认审查：

- `dayu/`
- `tests/`
- 与当前变更直接相关的 `docs/`
- 依赖锁文件、配置文件、README（仅在变更触发时）

只依据当前仓库中的代码真源、测试真源、README 职责说明和本指南做判断。若文档与代码不一致，以当前代码和测试为直接证据，同时报告文档漂移。

## 2. 总原则

- 必须沿真实代码路径逐行走读，禁止猜测。
- root cause 必须来自同一条逻辑 / 数据路径上的直接证据。
- 先判断问题动机是否成立；不要把风格偏好包装成 bug。
- 架构是 `UI -> Service -> Host -> Engine`，禁止反向依赖。
- 下层接口设计必须假设上层不存在，只表达本层稳定输入、输出和协作协议。
- 财报文档存取必须且只能通过 `dayu.fins.storage` 下的仓储协议与实现完成。
- 禁止兼容 wrapper / facade / re-export，除非它本身提供新的有效语义。
- 禁止 `Any`、`object`、无类型参数、无类型返回值。
- 工具 schema 内的字面量字符串是合理例外，不按 magic string 报告。

## 3. Review 结果格式

日常 review 结果写入：

```text
docs/reviews/code-review-YYYYMMDD-HHMM.md
```

每条 finding 使用以下格式：

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

## 4. 架构与依赖

当前分层固定为：

```text
UI -> Service -> Host -> Engine
```

检查项：

- Engine 不得 import Host / Service / UI 的具体实现。
- Host 不得 import Service / UI 的具体实现。
- Service 不得 import UI 的具体实现。
- `dayu.contracts` 不得 import 任一具体业务层或执行层。
- `dayu.engine.contracts` 可以依赖 `dayu.contracts`，不得依赖 Host / Service / UI / fins。
- `dayu.engine` 包根可以结构性 re-export 共享契约，但不得导出未实现入口、实现类占位或兼容性 facade。

必须报告：

- 任何反向 import。
- 任何绕过 Host 直接控制 Engine 的 Service / UI 调用。
- 任何让 Engine 理解 Host 治理、Service 业务受理、UI 展示状态的类型或字段。
- 任何让 Engine 直接读取财报文件、fins 目录或 fins storage 具体实现的路径。

## 5. 契约归属

契约归属判定规则：

> 如果语义真源在一方，另一方只是调用方，则契约落在语义真源所在层；如果两个层都需要独立实现、产生、解释或持久化它，且它描述的是层间协作协议而不是某一层的调用参数，则契约落在公共契约。

当前约定：

- `dayu.contracts`：层间共享协作契约。
- `dayu.engine.contracts`：Engine 语义真源契约。

检查项：

- `CancellationToken` 属于共享协作契约。
- `ToolExecutor` 属于共享协作契约，且只暴露执行所需的最小表面。
- `ToolExecutionRequest`、`ToolResultEnvelope`、`ToolExecutionOutcome`、`ToolAwaitSpec` 属于共享协作契约。
- `RunnerSpec`、`RunnerCallOptions`、`AgentRunRequest`、`AgentPolicy` 属于 Engine 语义真源契约。
- `EngineEvent`、`RunnerEvent`、`AgentRunResult` 属于 Engine 语义真源契约。
- 取消公共终态由结构化 run cancelled 事件 / outcome 表达，不应通过公共取消异常表达。

必须报告：

- 因“被多个层 import”而错误迁入公共契约的单层语义真源类型。
- 某一层为了实现另一层内部类型而反向贴合该层的设计。
- 公共契约中出现 `Any`、`object`、裸 `dict`、裸 `list`、开放 metadata 语义袋。

### 5.1. Engine 契约专项

检查项：

- `dayu.contracts.__all__` 必须是共享协作契约白名单。
- `dayu.engine.__all__` 不得导出未实现入口、实现类占位或取消异常。
- `AsyncRunner` Protocol 只能暴露 Runner 调用、能力查询、资源关闭所需的最小表面。
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

## 6. Runner 专项

当仓库中存在 Runner 实现时，必须检查：

- Runner 只产出 `RunnerEvent`，不产出 `EngineEvent`。
- Runner 不执行工具，不依赖 `ToolExecutor` / `ToolRegistry`。
- Runner 不实现 `set_tools`，不接受 `call(**extra_payloads)`。
- Runner 不读取配置文件来获得运行规格；运行规格必须来自显式强类型输入。
- provider 私有参数必须来自强类型 provider extension 或显式字段。
- OpenAI-compatible payload、SSE、tool call delta、usage、finish reason、HTTP error、retry/backoff、reasoning 标签处理必须以当前代码中的协议 adapter 直接证据审查。
- cancellation 只作为阻塞边界观察；结构化取消终态由 Engine / Agent 层提升。
- Runner 输入必须只来自 Runner 调用契约与显式运行规格，不得依赖 Host / Service 的运行状态。
- 消息 payload 必须能正确表达 system / user / assistant / tool 等消息角色。
- assistant message 中的 reasoning content、tool calls、provider extra content 必须能按契约进入下一轮请求。
- tool call delta 必须能稳定聚合为完整工具调用，不得因 chunk 顺序、index 缺失、arguments 分片或 arguments null 破坏状态。
- Runner 只能表达单次模型调用状态机，不得越界实现多轮 Agent loop。
- stream 与 non-stream 两条路径的最终事件语义必须一致。
- content delta、reasoning delta、tool call delta、tool calls completed、content completed、usage、done / error / cancel 边界不得存在顺序冲突。

必须报告：

- 为实现方便引入 `Any`、开放 `extra_body` 任意袋、`**kwargs`。
- Runner 导入 Host / trace / fins / tools / processors。
- Runner 把取消、失败或最终回答提升成 Host 可见终态。
- Runner 资源关闭不完整，或取消后留下 HTTP session、response、stream task。
- RunnerEvent 顺序无法被后续 Engine loop 无歧义消费。
- 使用隐式布尔标记、魔法字符串或弱类型 payload 表达关键状态迁移。

## 7. 状态机 Review

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
- 已存在 Runner 时，检查 Runner 协议状态机。
- 已存在 Agent loop 时，检查 Agent iteration 状态机。
- 已存在 Host 持久化和恢复能力时，检查 pending turn、reply outbox、conversation archive 等状态机。

Runner 协议状态机最低检查场景：

- content-only answer。
- reasoning + content。
- tool call streaming。
- tool call arguments 分片。
- usage-only chunk。
- 正常 done。
- 协议错误。
- HTTP / network / timeout 错误。
- retry 后成功。
- retry 耗尽。
- cancellation before request。
- cancellation during stream。
- close 后资源释放。

必须报告：

- 状态真源不唯一。
- 终态不吸收。
- 异常路径和正常路径使用不同转换规则。
- 外部事件、返回值、持久化事实互相冲突。

## 8. 参数传递与生效点

对每个关键参数检查：

- 来源：从哪里进入系统。
- 覆盖关系：默认值、配置值、请求值、override 谁优先。
- 落点：最终在哪一层、哪个函数、哪个字段被消费。
- 失效处理：非法值、空值、缺失值、类型错误是否明确处理。

必须报告：

- 参数传到中间对象但最终未消费。
- 参数在链路中被重新默认化、覆盖或丢失。
- 显式参数被塞入 metadata、extra payload、开放 JSON 袋。

## 9. 非预期输入

必须主动检查：

- 缺失必填参数。
- 类型错误。
- 非法枚举 / 非法字符串。
- 空内容 / 空消息。
- 越界数值 / 负数 / 超长输入。
- 重复请求 / 冲突参数 / 已终态再次推进。

合理策略只能是：

- 明确拒绝。
- 合法归一化。
- 安全降级。
- 有边界的重试。
- 安全 no-op。

“碰巧没崩”“吞错继续跑”“落入正常分支但语义已错”都必须报告。

## 10. README 与 docs

README 只写当前已落地事实，不写未来设计。

触发检查：

- 修改 `dayu/engine/`：检查 `dayu/engine/README.md`。
- 修改整体分层、装配方式、Host / Engine 边界：检查 `dayu/README.md`。
- 修改测试分层或运行方式：检查 `tests/README.md`。
- 修改用户命令、安装、配置、CLI：检查根 `README.md`。

如果代码已经落地但文档仍停留在草案或迁移语境，应报告文档漂移。

## 11. 验证要求

每次 code review 必须记录实际运行结果。

常规：

```bash
source .venv/bin/activate
pytest <受影响测试> -q
pyright
git status --short
```

若测试或 pyright 失败，除非已有明确外部环境原因，否则作为阻塞问题。

## 12. 本文档维护规则

每次完成一个可合并的代码切片，都必须检查并更新本文档：

- 新增当前已落地能力的专项 review 检查项。
- 删除或降级已不适用的草案、临时表述。
- 保持架构口径为 `UI -> Service -> Host -> Engine`。
- 保持契约归属规则与当前代码真源一致。
