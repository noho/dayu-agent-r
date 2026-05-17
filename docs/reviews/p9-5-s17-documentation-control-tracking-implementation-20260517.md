# P9.5 S17 Documentation And Control Tracking Implementation

## 审计结论

S17 动机成立，但不应机械同步 S1-S16 的实现过程。当前需要修的是稳定文档中已经与代码事实或测试 guard 不完全一致的少量表述：

- Engine runner 文档仍把当前默认 runner 装配描述为函数式入口直接创建内置 OpenAI-compatible Runner，未明确 S1 后的私有默认装配点边界。
- 工具边界文档只写 `tool_schemas` 来自 effective `ToolBundle`，未同步强调 ToolRuntime 执行使用的 `tool_executor` 也必须来自同一个 attempt-local effective bundle。
- Host memory catch-up 文档仍写 projection catch-up failure 记录 logger exception；S15 后实际语义是 projection-local `WARNING`，只记录 `error_type`。
- `tests/README.md` 的 import-boundary 分层描述缺少 S16 已落地的 runtime 禁止 Host、contracts 禁止 runtime implementation、Engine 禁止工具声明 owner / memory、Host 禁止动态业务工具扫描与 `fetch_more` owner guard。

未发现需要改 public API、示例命令、README 结构或设计真源语义的更大不一致。

## 改动文件摘要

- `dayu/README.md`
  - 在“工具定义与执行边界”中补充 `tool_schemas` 与 `tool_executor` 必须来自同一个 attempt-local effective `ToolBundle`。

- `docs/design.md`
  - 同步仓库级工具边界说明，补齐 `tool_executor` 与 effective `ToolBundle` 的同源约束。

- `dayu/engine/README.md`
  - 将当前 runner 装配说明改为“函数式入口通过私有默认装配点创建内置 OpenAI-compatible Runner”，并明确该私有装配点不是 public factory / registry / runner selection extension point。

- `dayu/host/README.md`
  - 将 memory / projection catch-up failure 说明从 logger exception 校准为 projection-local `WARNING` + `error_type`，并保持“失败不回滚 durable command / accept 结果”的稳定语义。

- `tests/README.md`
  - 补齐 runtime / contracts / engine / host import-boundary 当前测试事实。
  - 补充 Host business tool scanner guard 与 `fetch_more` ToolRuntime / tooling owner guard。

## 未更新文件与理由

- `docs/host/design.md`
  - 当前 Host 专题设计已包含 ToolRuntime effective bundle、`fetch_more` 普通工具路径、Host 不扫描业务工具模块、Engine 不理解工具声明 owner、memory projection / catch-up 边界等设计真源；本次 README 修正没有改变 Host 专题设计。

- `docs/host/implementation-control.md`
  - 当前控制文档已记录 S16 accepted 且当前 gate 为 S17。S17 本轮没有新增需要重新归属的 residual risk，也没有发现未关闭 tracking item；按用户要求不重复 S15/S16 历史，不写过程流水。

- 根目录 `README.md`
  - 本轮未改变安装、配置、CLI、trace/render 或用户工作流；根 README 不在 S17 触发范围内。

## README 示例命令核对

本轮没有修改 README 中的 Python import 示例、pytest 命令或 pyright 命令。现有被触达文件中的示例仍对应当前代码入口：

- `dayu.engine` 包根仍导出 `AgentRunRequest`、`EngineEvent`、`run_agent_messages`。
- `dayu.engine.contracts` 仍导出 `AgentRunRequest`、`RunnerSpec`。
- `tests/README.md` 的测试命令只引用当前存在的测试目录 / 文件。

## 验证

- `git diff --check`
  - 结果：clean。

## 剩余风险

- S17 只做稳定文档校准，没有运行全量测试；下一 gate S18 仍应执行 aggregate validation。
- `dayu/host/README.md` 历史上仍有少量 phase 编号作为能力来源提示。本次只改直接失准内容，避免把 S17 扩成文档重写。
