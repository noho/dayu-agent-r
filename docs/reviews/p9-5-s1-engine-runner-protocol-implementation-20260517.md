# P9.5 S1 Engine Runner Protocol Decoupling Implementation

## 范围

- Gate: P9.5 S1 Engine Runner Protocol Decoupling implementation。
- 分支: `p9.5-pre-p10-hardening`。
- 目标: Engine Agent 主链路只消费 `AsyncRunner` 协议；public entry 继续通过私有默认装配点使用当前 OpenAI-compatible runner。

## 第一性原理判断

问题真实存在：`_AsyncAgent` 已经通过构造参数接收 `AsyncRunner`，但 `dayu.engine.agent` 仍直接导入并构造 `AsyncOpenAIRunner`，使 Agent 协调模块携带具体 provider runner 依赖。严重性属于 P10 前的边界噪音，不是 public API blocker；最佳修复是把当前默认 runner 装配移动到私有模块，而不是引入 factory、registry 或 provider selection。

## 变更文件

- `dayu/engine/_default_runner.py`
  - 新增私有默认 Runner 装配模块。
  - 提供 `build_default_runner(request: AgentRunRequest) -> AsyncRunner`。
  - 该模块是唯一允许 top-level import `AsyncOpenAIRunner` 的当前默认装配点。
- `dayu/engine/agent.py`
  - 移除直接 `AsyncOpenAIRunner` import。
  - `_build_runner(request) -> AsyncRunner` 改为委托 `build_default_runner(request)`。
  - 未改变 `run_agent_messages`、`run_agent_and_wait` 或 `_AsyncAgent.__init__` 签名。
- `tests/engine/test_agent_phase2.py`
  - 新增 `_AsyncAgent` 使用注入 fake runner 的回归测试，默认 OpenAI runner 若被误实例化会失败。
  - 新增 `run_agent_messages` public entry 回归测试，证明当前默认装配仍构造 OpenAI-compatible runner，并在 stream close 时 close runner。
- `tests/engine/test_protocols_surface.py`
  - 新增断言：`dayu.engine.agent` 不直接持有 `AsyncOpenAIRunner` 符号。

## 验证

- `source .venv/bin/activate && pytest tests/engine/test_protocols_surface.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py`
  - 结果: 66 passed。
- `source .venv/bin/activate && python -m pyright dayu/engine tests/engine`
  - 结果: 0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果: 通过，无输出。

## 文档决策

未修改 `dayu/engine/README.md`。原因：当前 README 已明确 `AsyncRunner` 是 Engine 调用 provider 的协议接口，并把 OpenAI Runner 具体实现类列为非稳定接口；本次只移动私有默认装配点，未改变稳定接口、公共入口、Runner 协议或调用方式。

## 残余风险

- `run_agent_messages` 仍按现有设计构造当前默认 OpenAI-compatible runner；本 slice 未引入 runner 选择契约，也未尝试解决多 provider 装配问题。
- `dayu.engine.agent` 通过私有 helper 依赖默认装配模块；这符合 S1 边界，但不是 public extension point。

## Stop Status

- 未触发 stop condition。
- 未更改 public `run_agent_messages` 签名。
- 未添加 runner registry / factory / plugin / provider selection map。
- 未向 Engine 引入 Host state、tool governance、memory 或 P10+ 语义。
- 未修改允许范围外文件。
