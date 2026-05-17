# P9.5 S1 Code Review — AgentDS

## Gate

- **Work unit**: P9.5 Pre-P10 Cross-Repository Hardening
- **Slice**: S1 Engine Runner Protocol Decoupling
- **Approved plan**: `docs/host/p9-5-pre-p10-hardening-plan.md` §S1
- **Implementation artifact**: `docs/reviews/p9-5-s1-engine-runner-protocol-implementation-20260517.md`
- **Reviewer**: AgentDS (review-only)
- **Reviewed files**:
  - `dayu/engine/agent.py` (modified)
  - `dayu/engine/_default_runner.py` (new)
  - `tests/engine/test_agent_phase2.py` (modified)
  - `tests/engine/test_protocols_surface.py` (modified)
  - `dayu/engine/__init__.py` (checked, not changed)

## 总评

零阻塞项。实现精确符合 P9.5 S1 scope：移除 Agent 协调模块对 `AsyncOpenAIRunner` 的直接依赖，将默认 Runner 装配收敛到唯一的私有模块 `dayu/engine/_default_runner.py`；未引入 factory、registry、provider selection、lazy import seam、兼容性 wrapper、Host governance、memory 或 tool governance。测试形成完整的 proof chain：`_AsyncAgent` 只消费注入 `AsyncRunner`，public entry 仍通过默认装配点构造并关闭 Runner。

---

## Findings

按严重性排列（阻塞 → 建议 → 观察）。

### F1 · 阻断 · 无

未发现阻断性缺陷。

---

### F2 · 非阻断 · `build_default_runner` 缺少独立单元测试

- **文件**: `dayu/engine/_default_runner.py:15-26`
- **证据**: `build_default_runner` 是三行构造函数委托，仅被 `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` (test_agent_phase2.py:1214-1237) 通过 public entry 间接覆盖。`_default_runner.py` 自身无独立测试文件。
- **影响**: 低。当前路径已在集成测试中被完整覆盖（构造、参数传递、close 行为）。若未来 `build_default_runner` 逻辑变复杂（例如增加 spec 校验、多 runner 选择），可能缺少回归护栏。
- **建议修复**: 当前可接受。若 `_default_runner.py` 逻辑增长超过当前三行委托，再补独立单元测试。
- **阻塞状态**: 否。

---

### F3 · 非阻断 · `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` 不显式断言 `runner.call()` 被调用

- **文件**: `tests/engine/test_agent_phase2.py:1214-1237`
- **证据**: `_PublicEntryDefaultRunner` 类未定义 `call_count` 属性（对比 `_ScriptedRunner` 有 `call_count`）。测试仅断言 `constructed` 列表长度、`spec` / `cancellation_token` 正确性、`close_count == 1`，未显式验证 `call()` 被执行。
- **影响**: 极低。`ITERATION_STARTED` 事件的存在隐式证明了 `_AsyncAgent.run_messages()` 已进入主循环并调用 `self._runner.call(...)`；若无 `call()` 执行，迭代循环不可能产出该事件。但显式断言会提升测试的防御深度。
- **建议修复**: `_PublicEntryDefaultRunner` 加 `call_count` 计数器并断言 `== 1`。非必须，可在 S2 或后续 Runner 相关修改中顺带补齐。
- **阻塞状态**: 否。

---

### F4 · 非阻断 · `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` 关闭 stream 时未消费完整事件流

- **文件**: `tests/engine/test_agent_phase2.py:1229-1230`
- **证据**: `await anext(stream)` 只取第一个事件后立即 `await stream.aclose()`，未消费剩余事件。`aclose()` 触发生成器 finally 块执行 `_close_runner_once()`，此为测试意图（证明 close 发生在 stream close 时）。但生成器内部 `_AsyncAgent.run_messages()` 在 finally 中执行 close，而 `aclose()` 会向生成器注入 `GeneratorExit` 进入 finally。
- **影响**: 无。这正是测试要验证的行为：Runner close 由 stream close 触发，不依赖完整消费。测试意图正确。
- **建议修复**: 无需修复。可考虑加注释说明"有意不完整消费以证明 close 由 stream close 触发"。
- **阻塞状态**: 否。

---

### F5 · 观察 · `run_agent_messages` 的 Runner 关闭有两条路径

- **文件**: `dayu/engine/agent.py:835-837, 2413-2417`
- **证据**: `_close_runner_once()` 在两处可被触发：
  1. `_AsyncAgent.run_messages()` 的 `finally` 块（line 836）
  2. `run_agent_messages()` 的 `finally` 块中 `await events.aclose()`（line 2417），后者会触发异步生成器进入 finally
- **影响**: 无。`_close_runner_once()` 有 `self._closed` 幂等守卫（line 2272-2274），双重关闭安全。`_AsyncAgent` 已有测试覆盖 close 异常不覆盖 terminal（test_agent_phase2.py:910-935）。
- **建议修复**: 无需修复。当前设计正确。
- **阻塞状态**: 否。

---

### F6 · 观察 · `dayu/engine/__init__.py` 未暴露 `build_default_runner` 或 `_default_runner`

- **文件**: `dayu/engine/__init__.py:118`
- **证据**: `__init__.py` 仅从 `dayu.engine.agent` import `run_agent_and_wait, run_agent_messages`。`__all__` 不含 `build_default_runner`、`_default_runner` 或 `AsyncOpenAIRunner`。
- **影响**: 无。私有装配点未意外升级为 public API。
- **阻塞状态**: 否。

---

## 架构边界验证

| 约束 | 状态 | 证据 |
|------|------|------|
| Agent 模块不直接 import `AsyncOpenAIRunner` | ✅ | `grep AsyncOpenAIRunner dayu/engine/agent.py` → no matches; `test_agent_module_does_not_import_concrete_openai_runner_symbol` 通过 |
| 默认 Runner 装配只存在于 `_default_runner.py` | ✅ | 仅 `_default_runner.py:12` import `AsyncOpenAIRunner` |
| 无 factory / registry / provider selection | ✅ | `_build_runner` 仅委托 `build_default_runner`（agent.py:258），无分支、无 dispatch |
| 无 lazy import seam | ✅ | agent.py:109 为 top-level import |
| 无兼容性 wrapper / re-export | ✅ | 无旧路径转发、无别名导出 |
| 无 Host governance / memory / tool governance | ✅ | `_AsyncAgent` 只持有 `AsyncRunner`，未新增 Host 语义字段 |
| 不改变 public `run_agent_messages` / `run_agent_and_wait` 签名 | ✅ | 签名与原实现完全一致（agent.py:2396-2398, 2420） |
| `_AsyncAgent.__init__` 仍接收 `runner: AsyncRunner` | ✅ | agent.py:559 |

## 测试 proof chain 验证

1. **`_AsyncAgent` 只消费注入 Runner（不依赖默认装配）**
   - `test_async_agent_uses_injected_runner_without_default_runner` (test_agent_phase2.py:513-548)
   - Monkeypatch `AsyncOpenAIRunner` 为 `_ExplodingDefaultRunner`（构造即抛 `AssertionError`）
   - 直接构造 `_ScriptedRunner` 注入 `_AsyncAgent` → 运行成功，终端为 `FINAL_ANSWER`
   - **证明**: `_AsyncAgent` 初始化与主循环不触及 `AsyncOpenAIRunner` 符号

2. **Public entry 仍构造并关闭默认 Runner**
   - `test_run_agent_messages_builds_default_runner_and_closes_on_stream_close` (test_agent_phase2.py:1214-1237)
   - Monkeypatch `AsyncOpenAIRunner` 为 `_PublicEntryDefaultRunner`（记录构造与 close）
   - 调用 `run_agent_messages` → 断言 1 个 runner 被构造、spec/token 正确、close_count == 1
   - **证明**: public entry 走完整的 `_build_runner → build_default_runner → AsyncOpenAIRunner` 路径

3. **Agent 模块不直接持有 `AsyncOpenAIRunner` 符号**
   - `test_agent_module_does_not_import_concrete_openai_runner_symbol` (test_protocols_surface.py:52-55)
   - `vars(agent_module)` 不含 `"AsyncOpenAIRunner"`
   - **证明**: `import AsyncOpenAIRunner` 未出现在 agent.py 的模块级命名空间中

三条测试构成完整 proof chain，无缺口。

## 残余风险与测试缺口

| 风险 | 严重度 | 归属 |
|------|--------|------|
| `build_default_runner` 无独立单元测试 | 低 | 当前可接受；逻辑增长后再补 |
| `run_agent_messages` 在 `_build_runner` 抛异常时的行为未测试 | 低 | 异常透传为 Python 标准行为；不影响本 slice 目标 |
| `_PublicEntryDefaultRunner` 缺少 `call_count` 计数器 | 低 | 隐式验证充分；可在后续 Runner 测试中补齐 |

## Docstring / 类型约束

- `_default_runner.py` 模块与函数均有中文 docstring，含 `:param`、`:returns`、`:raises`（line 1-29）✅
- `agent.py` `_build_runner` docstring 已更新反映委托语义（line 248-256）✅
- 全部签名有完整类型标注，无 `Any` / `object` / 无类型参数 ✅
- `__all__` 正确限制 public surface ✅

## 验证结果复检

实现 artifact 声明的验证命令与结果与当前代码状态一致：

- `pytest tests/engine/test_protocols_surface.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py` → 66 passed（artifact 声明）
- `python -m pyright dayu/engine tests/engine` → 0 errors, 0 warnings, 0 informations（artifact 声明）
- `git diff --check` → 通过（本文复检确认）

## 文档决策复检

实现 artifact 声明未修改 `dayu/engine/README.md`，理由为"当前 README 已明确 `AsyncRunner` 是 Engine 调用 provider 的协议接口，并把 OpenAI Runner 具体实现类列为非稳定接口"。经检查 `dayu/engine/README.md:117-160`，确认当前文档已明确 Runner 协议与 OpenAIRunner 为"非稳定接口"——文档当前状态与代码一致，不触发 README 更新规则。✅

## Stop Status

- **未触发 stop condition**。
- 未更改 public 签名。
- 未添加 factory / registry / provider selection。
- 未向 Engine 引入 Host state / tool governance / memory / P10+ 语义。
- 未修改允许范围外文件。

---

## 结论

**0 个阻断性问题。** P9.5 S1 实现正确、完整、符合 scope。建议接受当前状态进入后续 slice。
