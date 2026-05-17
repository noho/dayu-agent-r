# P9.5 S1 Engine Runner Protocol Decoupling — Code Review

- Reviewer: AgentMiMo
- Date: 2026-05-17
- Branch: `p9.5-pre-p10-hardening`
- Scope: S1 Engine Runner Protocol Decoupling
- Changed files: `dayu/engine/agent.py`, `dayu/engine/_default_runner.py`, `tests/engine/test_agent_phase2.py`, `tests/engine/test_protocols_surface.py`, `docs/reviews/p9-5-s1-engine-runner-protocol-implementation-20260517.md`

## Review Lens

- Correctness: 变更是否正确实现 S1 目标，不引入新 bug。
- Architecture boundary: 是否遵守分层与依赖方向，不泄漏实现细节。
- Tests: 测试是否真正证明了所声明的行为。
- Type/docstring constraints: 是否遵守编码硬约束。
- P9.5 scope: 是否在计划范围内，不越界。

## Findings

### F1 [PASS] 架构边界正确：`AsyncOpenAIRunner` 依赖已从 agent 协调模块移除

**证据**: `dayu/engine/agent.py` diff 显示 `from dayu.engine.runners.openai.runner import AsyncOpenAIRunner` 已替换为 `from dayu.engine._default_runner import build_default_runner`。`_build_runner` 委托给 `build_default_runner`，不再直接构造 `AsyncOpenAIRunner`。

**验证**: `test_agent_module_does_not_import_concrete_openai_runner_symbol` 断言 `AsyncOpenAIRunner` 不在 `vars(agent_module)` 中。

**结论**: 通过。Agent 协调模块不再持有具体 provider runner 符号。

### F2 [PASS] `_AsyncAgent` 只消费注入的 `AsyncRunner` 协议

**证据**: `test_async_agent_uses_injected_runner_without_default_runner` 将 `default_runner_module.AsyncOpenAIRunner` monkeypatch 为 `_ExplodingDefaultRunner`（构造时抛 `AssertionError`），然后用 `_ScriptedRunner` 实例化 `_AsyncAgent` 并成功运行。证明 `_AsyncAgent` 主链路完全不触碰默认 runner 装配。

**结论**: 通过。注入的 runner 被正确使用，默认 runner 未被误实例化。

### F3 [PASS] `run_agent_messages` public entry 仍通过默认装配点构造 OpenAI runner

**证据**: `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` 将 `AsyncOpenAIRunner` monkeypatch 为 `_PublicEntryDefaultRunner`，验证：(1) 构造了 1 个实例，(2) `spec` 和 `cancellation_token` 来自 request，(3) `close_count == 1`。

**结论**: 通过。public entry 保持现有默认装配行为，流关闭时正确 close runner。

### F4 [PASS] `_default_runner.py` 是唯一允许 top-level import `AsyncOpenAIRunner` 的模块

**证据**: `dayu/engine/_default_runner.py` 顶层 `from dayu.engine.runners.openai.runner import AsyncOpenAIRunner`，`build_default_runner` 是唯一导出。`dayu/engine/agent.py` 无此 import。`dayu/engine/_default_runner.py` 不在 `__init__.py` 的 public namespace 中（私有模块）。

**结论**: 通过。OpenAI runner 依赖被收口到单个私有装配点。

### F5 [PASS] 未引入 factory/registry/provider selection

**证据**: `build_default_runner` 是直接构造 `AsyncOpenAIRunner` 的简单函数，无条件分支、无注册表、无插件机制。`_build_runner` 委托给 `build_default_runner`，无额外逻辑。diff 中无新抽象层。

**结论**: 通过。符合计划"不做 factory/registry/provider selection"的约束。

### F6 [PASS] 未使用 lazy import seam 或 compatibility wrapper

**证据**: 所有 import 均为模块顶层。`_build_runner` 不是 compatibility wrapper——它原本就存在，只是内部实现从直接构造改为委托，语义未变。

**结论**: 通过。

### F7 [PASS] 未引入 Host governance、memory 或 tool governance

**证据**: 变更仅涉及 runner 构造路径的移动。`_AsyncAgent` 签名、`run_agent_messages` 签名、`run_agent_and_wait` 签名均未改变。无新 state、新 event type 或新治理语义。

**结论**: 通过。

### F8 [PASS] 类型与 docstring 约束

**证据**:
- `_default_runner.py` 提供完整中文 docstring（概览、参数、返回值、异常）。
- `build_default_runner` 签名类型完整：`request: AgentRunRequest` -> `AsyncRunner`。
- `_build_runner` 更新后的 docstring 也保持中文并更新了语义描述。
- 新增测试类与函数均有中文 docstring。

**结论**: 通过。

### F9 [NOTE] 测试覆盖：未新增 `test_agent_phase3_tool_call.py` 变更

**证据**: 实现 artifact 声称 `test_agent_phase3_tool_call.py` 在验证范围内（`pytest tests/engine/test_agent_phase3_tool_call.py`），但 diff 中该文件无变更。这是正确的——S1 不修改 tool call 逻辑，只是确认现有 tool call 测试在变更后仍然通过。

**结论**: 非问题。现有测试通过即为验证。

### F10 [NOTE] `_PublicEntryDefaultRunner.constructed` 使用类级可变默认

**证据**: `test_agent_phase2.py:256` — `constructed: list["_PublicEntryDefaultRunner"] = []` 是类级可变默认值。测试开头调用 `.constructed.clear()` 清理，功能正确。

**影响**: 这是测试代码中的常见模式，且 `.constructed.clear()` 确保隔离。不影响正确性。

**结论**: 非问题，仅供记录。

### F11 [PASS] `dayu/engine/README.md` 未修改——符合触发规则

**证据**: 实现 artifact 说明"当前 README 已明确 AsyncRunner 是 Engine 调用 provider 的协议接口，并把 OpenAI Runner 具体实现类列为非稳定接口；本次只移动私有默认装配点，未改变稳定接口、公共入口、Runner 协议或调用方式"。

**验证**: 检查 `dayu/engine/README.md` 中 `AsyncRunner` 和 OpenAI Runner 的描述——README 已声明 OpenAI Runner 具体实现类非稳定接口。本次变更不改变公共接口文档的准确性。

**结论**: 通过。不更新 README 是正确决策。

## Blocking Findings

**无 blocking finding。**

## Residual Risks

1. **`_build_runner` 是私有 helper，不是 extension point**：当前实现正确，但如果未来有人误将其视为扩展点，可能引入不必要的间接层。这不是当前风险，仅作记录。
2. **`_default_runner.py` 的 `build_default_runner` 直接透传异常**：与原 `_build_runner` 行为一致，Runner 构造失败仍然透传。这是正确行为。
3. **测试不覆盖 `_default_runner.py` 的独立单元测试**：该模块极简（单行委托），且通过 `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` 间接覆盖。独立单元测试的边际价值极低。

## Scope Compliance

| 约束 | 状态 |
|---|---|
| 不改变 public `run_agent_messages` 签名 | 通过 |
| 不添加 runner registry/factory/plugin | 通过 |
| 不使用 lazy import seam | 通过 |
| 不使用 compatibility wrapper | 通过 |
| 不引入 Host state/tool governance/memory | 通过 |
| 不修改允许范围外文件 | 通过 |
| 不新增 `Any`/`object` 签名 | 通过 |
| 不引入魔法数字/字符串 | 通过 |

## Conclusion

S1 实现正确、边界清晰、测试充分。变更严格限于将 OpenAI runner 的直接构造从 `agent.py` 移动到私有 `_default_runner.py`，不引入额外抽象，不改变公共接口，不泄漏实现细节。现有 test suite 通过（66 passed），pyright 无错误。**0 blocking findings。**
