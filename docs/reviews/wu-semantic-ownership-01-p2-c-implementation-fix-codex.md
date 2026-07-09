# WU-SEMANTIC-OWNERSHIP-01 P2-C implementation fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation fix
- Accepted finding: `P2C-IMPL-F01`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-controller-adjudication.md`

本次只修复 accepted finding 的测试覆盖缺口，不修改 production code，不改变 `AgentPolicy` 合约、运行时装配或 Host / Engine 行为。

## Owner Boundary

P2-C 的语义真源仍是调用方解析后的显式 `AgentPolicy.fallback_prompt` 与 `AgentPolicy.continuation_prompt` 文本：

1. Runtime / config owner 解析 profile-scoped prompt 文本。
2. Service assembly owner 把解析后的 prompt 文本传入 Engine policy。
3. Host durable restore owner 持久化并恢复完整 prompt 字段。
4. Engine contract owner 只校验字段存在且非空白，不拥有 LLM-facing 默认文本。
5. Engine contract tests owner 覆盖必填字段、显式字段保留和空白字段拒绝。

`P2C-IMPL-F01` 的 root cause 是测试迁移后 `continuation_prompt` 空白输入覆盖不如 `fallback_prompt` 对称；错误语义的 owner 是 Engine contract test，不是 production `AgentPolicy` 校验逻辑。因此修复落在 `tests/engine/test_agent_phase3_tool_call.py::test_agent_policy_rejects_invalid_values`。

## Fix

修改文件：

- `tests/engine/test_agent_phase3_tool_call.py`

修复内容：

- 将原先单个 `continuation_prompt=" "` 负例替换为循环覆盖 `("", "   ", "\n\t")`。
- 保留既有中文注释风格。
- 未抽取跨测试默认真源，未新增共享 fixture 或 helper。
- 未修改 production code。

## Propagation Audit

本次 fix 只影响测试断言矩阵，业务语义传播路径未变化：

1. Runtime / config 仍负责产生 resolved prompt 文本。
2. Service / Host 仍按 P2-C implementation 的显式字段路径传递、持久化、恢复 prompt。
3. Engine `AgentPolicy.__post_init__` 仍用同一 `strip() == ""` 规则拒绝 `fallback_prompt` 与 `continuation_prompt` 的空白文本。
4. Engine fallback / continuation 状态机仍只消费已通过构造期校验的 prompt。
5. 测试现在对 `fallback_prompt` 与 `continuation_prompt` 的空白值拒绝覆盖对称。

不存在“显示正确但持久化错误”或“trace 正确但 memory 错误”的传播风险；本次没有触及 durable state、trace、memory、audit、UI 输出或 LLM-facing prompt/schema。

## Verification

已在 `source .venv/bin/activate` 后运行：

```bash
pytest tests/engine/test_agent_phase3_tool_call.py
```

结果：`45 passed in 0.27s`。

```bash
pyright
```

结果：`0 errors, 0 warnings, 0 informations`。命令输出包含 pyright 新版本提示，不影响类型检查结果。

```bash
git diff --check
```

结果：通过，无输出。

## README Trigger

- 触发检查：修改了 `tests/`，按规则检查 `tests/README.md`。
- 判断结果：本次仅补齐既有 Engine contract 测试用例内部的输入覆盖，没有新增测试层级、测试目录职责、共享 fixture、运行命令或维护约定。
- 实际动作：不更新 README。

## Residual Risk

本次 accepted finding 已关闭。宽测试中已由 controller 分类的 non-P2-C residual 不属于本 fix gate，仍留给 umbrella 后续 owner 处理。
