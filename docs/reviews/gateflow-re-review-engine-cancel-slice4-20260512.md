# Gateflow Re-review: engine-cancel-commit-boundary-and-tool-timeout / Slice 4

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `docs sync and full validation`
- **Review artifact**: `docs/reviews/gateflow-code-review-engine-cancel-slice4-20260512.md`
- **Fix artifact**: `docs/reviews/gateflow-fix-engine-cancel-slice4-20260512.md`
- **Review scope**: 复核 Slice 4 文档 finding 是否修复，并确认 README / design 无新增 stale contradiction
- **Conclusion**: pass

上一轮 finding 已修复。`docs/engine/design.md` 的取消约束段落现在明确区分：Engine 负责 `ToolExecutor.execute` handshake 等待预算，并在 outcome 返回前超时时收口为不可恢复 `run_failed(tool_execution_timeout)`；外部长事务 timeout、取消传播、后台任务收口和 orphan control 由 Host / ToolRuntime / ToolExecutor 负责。

## Finding 修复状态

### Finding 1: design.md 仍称工具超时由 Host ToolRuntime 负责，否认 Engine handshake timeout

- **Status**: fixed
- **Evidence**:
  - `docs/engine/design.md` 的取消约束段落已替换旧句，不再把所有工具超时笼统归 Host ToolRuntime。
  - 当前段落与后文 bounded handshake 稳定规则一致：`AgentPolicy.tool_execution_timeout_seconds` 是 ToolExecutor handshake timeout 真源，Engine 等待同一 timeout，timeout before outcome 时取消 execute task 并 `run_failed(tool_execution_timeout)`。
  - README 与 design.md 均表达外部长事务治理不属于 Engine，且不否认 Engine handshake timeout。

## Stale Check

- `rg '工具超时、取消、后台任务收口|取消优先|已观察到 cancellation token 后|不能继续产出 `final_answer`|提交 `final_answer` 前' -n dayu/engine/README.md docs/engine/design.md`
  - 结果：无匹配。
- 额外搜索 `Engine 只接收终态工具结果或等待事实` 仍在 `docs/engine/design.md` 的外部长事务职责句中出现；该句前一条已经明确 Engine 负责 handshake timeout，因此不构成 stale contradiction。

## 验证命令

- `git diff --check`
  - 结果：通过，无输出。

## Residual Risk

- 本次未重跑测试和 pyright；本 slice fix 仅调整文档矛盾，且已按请求运行 diff check 与 stale phrase search。
- 本次是 re-review-only；未修改文档正文。
