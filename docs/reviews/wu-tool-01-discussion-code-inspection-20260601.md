# WU-TOOL-01 Discussion / Code Inspection

## 结论

WU-TOOL-01 的动机成立。当前实现仍有 run-scoped duplicate governance owner，duplicate key 不包含 `attempt_id`，且 duplicate 治理提示由执行路径硬编码。按 `docs/host/design.md` 的 Host 强治理目标，duplicate governance 应收敛为 attempt-local，并且 policy / 提示应来自 typed 配置或 Attempt snapshot，而不是依赖 worker-local run cache 或硬编码文案。

## 直接证据

- `dayu/host/tool_runtime.py` 模块概览仍描述 `run-scoped in-memory duplicate governance`。
- `DuplicateGovernanceRequest` 当前只包含 tool identity、normalized args、arguments 和 semantic duplicate key，不包含 `attempt_id`。
- `_duplicate_key()` 只 hash tool name、tool identity digest、normalized args digest 和 semantic duplicate key，不包含 `attempt_id`。
- `InMemoryRunScopedDuplicateGovernanceRegistry` 按 `run_id` 返回共享 state；同一 Run 的多个 ToolRuntime handle 会共享 duplicate 记忆。
- `DefaultToolRuntimeFactory.create_tool_runtime()` 通过 `duplicate_governance_for_run(run_id=...)` 注入 duplicate governance。
- `_duplicate_message()` 对 `reuse`、`hint`、`require_justification`、`hard_stop` 的模型/诊断说明使用硬编码字符串。
- `ToolFactAcceptCandidate` docstring 仍称 `duplicate_key` 为 run-local duplicate key。
- `tests/host/test_toolruntime_duplicate_governance.py` 文件级 docstring 和测试名仍以 run-local / run-scoped 行为为目标，其中 `test_same_run_runtime_handles_share_duplicate_index` 明确断言同一 Run 多 handle 共享 duplicate index。

## 用户补充约束

用户要求：提示、policy 要可配置。

controller 裁决：接受该约束。它不是扩大成跨 Attempt 复用或 durable duplicate ledger，而是修正当前实现中 hardcoded duplicate message 与半配置 policy 的边界问题。最佳实践是让 duplicate policy、提示文案和 justification 参数名通过 typed policy 或 Attempt snapshot 进入 ToolRuntime，并保持 attempt-local scope。

## Scope 裁决

当前 work unit 应覆盖：

- 将 duplicate key / index 的 scope 改为当前 Attempt，至少绑定 `attempt_id`。
- 删除或改写 run-scoped registry，不保留 run-scope 与 attempt-scope 两套兼容行为。
- 保留 in-memory、non-durable duplicate index；Host restart、worker restart、新 Attempt 均不继承。
- 把 duplicate policy action、治理提示文案与 justification 参数名改为 typed configurable contract。
- diagnostic / `TOOL_CALL_GOVERNED` payload 必须能表达 attempt-scoped duplicate scope，并引用当前 Attempt 内 prior event refs。
- 测试必须覆盖同一 Attempt duplicate、跨 Attempt 不继承、可配置 policy、可配置提示、justification 参数名、diagnostic scope。

当前 work unit 不应覆盖：

- 跨 Attempt / 跨 Run / 跨 Session 复用历史工具结果。
- durable duplicate ledger 或从 EventLog 重建 duplicate index。
- tool result freshness、行情/汇率当前性、外部副作用幂等策略。
- 将业务工具发现、tool profile 或 scene/config assembly 纳入本 work unit。

## 下一步

进入 planning gate，派发 planning agent 生成 code-generation-ready plan。plan 必须以 `docs/host/design.md` 和本 artifact 为依据，明确 affected files、contract shape、slice 切分、测试矩阵、README 决策和 stop conditions。
