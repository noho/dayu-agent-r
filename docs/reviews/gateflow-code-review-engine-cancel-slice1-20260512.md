# Gateflow Code Review: engine-cancel-commit-boundary-and-tool-timeout / Slice 1

## 结论

- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Slice**: `contract-timeout-policy-and-runtime-helper`
- **Repository**: `/Users/leo/workspace/dayu-agent-r`
- **Branch**: `host/phase_0_design`
- **Review scope**: 当前未提交 Slice 1 改动
- **Conclusion**: fail

动机成立：Slice 1 需要先建立 `AgentPolicy.tool_execution_timeout_seconds` 真源和 runtime 层中立 owned-awaitable timeout helper，后续 Agent 才能在工具握手边界统一表达 cancel / timeout race。当前 diff 大体落在 approved scope 内，但发现 2 个需要修复的问题。

## Findings

### 1. severity: high / 已取消 token 入口仍会启动 target awaitable

- **file/line**: `dayu/runtime/cancellation.py:223`
- **evidence**:
  - `await_or_cancel_or_timeout` 在任何 `token.is_cancelled()` 入口检查前先执行 `asyncio.ensure_future(awaitable)`，随后才进入 `asyncio.wait(...)` 与 `token.is_cancelled()` 分支（`dayu/runtime/cancellation.py:223-241`）。
  - 现有 `await_or_cancel` 对同类入口有显式短路：token 已取消时关闭 coroutine 并返回 `WaitCancelled`，不启动 awaitable（`dayu/runtime/cancellation.py:110-113`），对应测试也断言 `started is False`（`tests/runtime/test_cancellation.py:109-127`）。
  - 临时验证命令显示新 helper 在调用前 token 已取消时仍让 target 执行了入口副作用：输出 `WaitCancelled True True`，第三个 `True` 表示 coroutine body 已运行。
- **impact**:
  - 这违反“已取消 token 入口”应阻止未来工作的取消边界。后续 Agent 用该 helper 包住 `ToolExecutor.execute(...)` 时，如果 run 在进入 helper 前已取消，工具握手 coroutine 仍可能执行同步副作用、发起外部 I/O 或创建下游任务，然后才被取消。
  - 当前新增测试只覆盖 `timeout_seconds=0.0` 且 token 已取消时返回 `WaitCancelled`（`tests/runtime/test_cancellation.py:436-452`），没有断言 target 未启动，因此漏掉了这个行为缺陷。
- **fix**:
  - 在 `await_or_cancel_or_timeout` 入口先检查 `token.is_cancelled()`；若 awaitable 是 coroutine，按 `await_or_cancel` 现有做法关闭 coroutine，然后返回 `WaitCancelled`。
  - 增加 `test_await_or_cancel_or_timeout_short_circuits_when_already_cancelled`，断言 token 预取消时 outcome 为 `WaitCancelled` 且 target body 未运行。
  - 保持 timeout / cancellation 命中后的 owned target 语义：一旦 helper 已经通过 `ensure_future` 拥有 target，cancel / timeout 时仍必须 cancel target 并 await done。

### 2. severity: medium / mandatory positive timeout 校验允许 NaN 与 infinity

- **file/line**: `dayu/engine/contracts/agent_policy.py:74`
- **evidence**:
  - `AgentPolicy.__post_init__` 只检查 `self.tool_execution_timeout_seconds <= 0`，因此 `float("nan")` 会绕过校验，`float("inf")` 也会被接受。
  - 临时验证命令输出：`nan accepted nan` 与 `inf accepted inf`。
  - 新增非法值测试只覆盖 `0.0` 和 `-1.0`（`tests/engine/test_agent_phase3_tool_call.py:690-697`）。
- **impact**:
  - Slice 1 approved scope 要求该字段是 mandatory positive `float`。`NaN` 不是正数，`infinity` 作为工具握手 timeout 也不是可治理的有限预算。允许这些值进入公共策略会把错误推迟到 runtime wait 或后续 Agent 工具执行路径，削弱 contract fail-fast。
- **fix**:
  - 使用 `math.isfinite(self.tool_execution_timeout_seconds)` 与 `> 0` 一起校验。
  - 将 `_INVALID_TOOL_EXECUTION_TIMEOUTS` 扩展为覆盖 `0.0`、负数、`math.nan`、`math.inf`。

## Scope / Contract Checks

- `rg "AgentPolicy\\(" -n` 显示仓库内当前构造点已补齐 mandatory `tool_execution_timeout_seconds`，未发现遗漏构造。
- `dayu.runtime.cancellation` 未引入 Engine / Host / Service / UI 依赖，层边界保持中立。
- 新增/修改签名未使用 `Any`、无类型参数或无类型返回值；`type="object"` 仅出现在工具 schema 测试字面量中，属于 schema 例外。
- 新增 helper 和测试函数具备中文 docstring。
- 当前 Slice 1 未修改 README。就本 diff 而言，README 中未发现必须同步的 `AgentPolicy(...)` 调用示例；`docs/engine/phase0-plan.md` 的旧签名属于历史 plan 文档，不应作为本 Slice 越界修改对象。

## 验证命令

- `git status --short --branch`：当前分支 `host/phase_0_design`，6 个未提交 Slice 1 文件。
- `git diff --check`：通过。
- `source .venv/bin/activate && pytest tests/runtime/test_cancellation.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`：68 passed。
- `source .venv/bin/activate && pyright dayu/ tests/ utils/`：0 errors, 0 warnings, 0 informations。
- 临时 pre-cancel 探针：`WaitCancelled True True`，证明 finding 1。
- 临时 policy finite 探针：`nan accepted nan`、`inf accepted inf`，证明 finding 2。

## Residual Risk

- 本次是 review-only；未修改生产或测试实现。
- 未运行全量测试。已运行与 Slice 1 直接相关的 runtime cancellation、Engine Agent phase2 / phase3 tool-call 测试与全仓 pyright。
