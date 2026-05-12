# Gateflow Code/Docs Review: engine-cancel-commit-boundary-and-tool-timeout / Slice 4

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `docs sync and full validation`
- **Repository**: `/Users/leo/workspace/dayu-agent-r`
- **Branch**: `host/phase_0_design`
- **Review scope**: 当前未提交文档 diff
- **Conclusion**: fail

`dayu/engine/README.md` 已按 Engine 开发手册职责同步当前代码事实，准确覆盖 policy timeout、ToolExecutionContext timeout、ToolExecutor handshake timeout、timeout 失败语义和取消提交边界。但 `docs/engine/design.md` 仍残留一处旧口径，与当前代码和同文档后文稳定规则冲突。

## Findings

### 1. severity: medium / design.md 仍称工具超时由 Host ToolRuntime 负责，否认 Engine handshake timeout

- **file/line**: `docs/engine/design.md:355`
- **evidence**:
  - 该行写道：“工具超时、取消、后台任务收口由 Host ToolRuntime 负责；Engine 只接收终态工具结果或等待事实。”
  - 当前代码已经实现 Engine 侧 `ToolExecutor.execute` bounded handshake timeout：`AgentPolicy.tool_execution_timeout_seconds` 写入 `ToolExecutionContext.timeout_seconds`，并由 Agent 等待同一 timeout；timeout 命中时不可恢复 `run_failed(tool_execution_timeout)`。
  - 同一文档后文也已写明稳定规则：`AgentPolicy.tool_execution_timeout_seconds` 是 ToolExecutor handshake timeout 真源，Engine 主动执行同一 timeout，timeout before outcome 时取消 execute task 并 `run_failed(tool_execution_timeout)`（`docs/engine/design.md:526-533`）。
- **impact**:
  - design.md 在“取消约束”段落和后文“bounded handshake 稳定规则”之间自相矛盾。
  - 读者会误以为所有工具 timeout 都归 Host ToolRuntime，Engine 不负责任何工具超时；这与 Slice 2/4 的当前实现和 README 当前说明冲突。
- **fix**:
  - 将该 bullet 改为区分两类 timeout：Engine 负责 `ToolExecutor.execute` handshake 等待预算与 `tool_execution_timeout` 收口；外部长事务 timeout、cleanup、orphan control、后台任务治理仍属 Host / ToolRuntime / ToolExecutor。

## Checked Behaviors

- `dayu/engine/README.md` 没有写未来设计，内容聚焦 Engine 接口、公共契约、执行路径、状态机、事件流、关键机制和扩展点，符合 Engine 开发手册职责。
- README 已准确表达：
  - `AgentPolicy.tool_execution_timeout_seconds` 是有限正数 handshake timeout 真源。
  - Engine 构造 `ToolExecutionContext.timeout_seconds` 时填入该值。
  - Engine 使用同一预算等待 `ToolExecutor.execute`。
  - timeout 先于 outcome 时取消 execute task，并以不可恢复 `run_failed(tool_execution_timeout)` 收口。
  - cancellation commit boundary 是“阻止未来工作，不覆盖已接受事实”。
- README 已清理旧口径：不再说取消无条件优先于 final / suspended / tool result，也不再暗示 content / reasoning delta 可被取消吞掉。
- `docs/engine/design.md` 新增和已存在的稳定规则大体与当前代码一致；除 finding 1 外，未发现同范围 stale contradiction。

## 验证命令

- 用户已验证：`source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine -q`
  - 结果：`323 passed`
- 用户已验证：`source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- 本次确认：`git diff --check`
  - 结果：通过，无输出

## Residual Risk

- 本次未重跑完整测试与 pyright；采用用户提供的已验证结果，并本地确认 `git diff --check` 通过。
- 本次是 review-only；未修改文档内容。
