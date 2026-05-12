# Host Tracking

本文档记录 Host 层后续需要承接的治理事项。这里的条目不是 Engine 已实现能力，也不是 Engine TODO；它们用于提醒 Host 设计时明确 ownership、状态真源与验证入口。

## 工具治理

### 语义级重复工具调用治理

- **来源**：OLD Engine 曾用工具名、参数与结果识别重复调用，并通过 hint / hard stop 干预循环。
- **当前归属**：Host / ToolRuntime。
- **不进入 Engine 的原因**：Engine 只防同一 run 内重复 `tool_call_id`，不理解工具语义、业务幂等性、用户意图或历史结果质量。
- **后续设计点**：Host 需要决定重复调用的判定范围、跨 run 记忆、提示策略、硬停止条件、审计事件与用户可见反馈。

### Tool result capping / truncation

- **来源**：OLD Engine 曾包含工具结果预算截断与上下文预算联动逻辑。
- **当前归属**：ToolRuntime / ToolExecutor，必要时由 Host 统一配置策略。
- **不进入 Engine 的原因**：Engine 只消费 `ToolExecutionOutcome`，不执行工具结果截断、不创建截断 cursor、不保存跨 run 工具状态。
- **后续设计点**：Host / ToolRuntime 需要定义截断策略、cursor 生命周期、`fetch_more` 类能力、审计记录、恢复输入与上下文预算协作方式。
