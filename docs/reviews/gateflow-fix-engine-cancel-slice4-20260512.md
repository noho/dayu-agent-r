# Gateflow Fix: engine-cancel-commit-boundary-and-tool-timeout / Slice 4

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `docs sync and full validation`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice4-20260512.md`
- **Fix conclusion**: 接受并修复 review finding。

## Finding 处理

### Finding 1: design.md 仍称工具超时由 Host ToolRuntime 负责，否认 Engine handshake timeout

- **状态**: fixed
- **修复文件**:
  - `docs/engine/design.md`
- **修复内容**:
  - 取消约束段落改为区分两类 timeout。
  - Engine 负责 `ToolExecutor.execute` handshake 等待预算，并在 outcome 返回前超时时收口为不可恢复 `run_failed(tool_execution_timeout)`。
  - 外部长事务 timeout、取消传播、后台任务收口和 orphan control 仍归 Host / ToolRuntime / ToolExecutor。

## 验证

- `git diff --check`
  - 结果：通过，无输出
- `rg '工具超时、取消、后台任务收口|取消优先|已观察到 cancellation token 后|不能继续产出 `final_answer`|提交 `final_answer` 前' -n dayu/engine/README.md docs/engine/design.md`
  - 结果：无匹配

## 残余风险

- 本次只修复文档矛盾，不改生产代码。
