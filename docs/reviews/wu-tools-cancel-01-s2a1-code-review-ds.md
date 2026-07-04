# WU-TOOLS-CANCEL-01 S2A1 Code Review — AgentDS

## 审查范围

- Base commit: `8eddd26b`
- 审查对象：当前未提交 working tree diff（34 文件，+358/-9）
- Plan 真源：`docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- Implementation report：`docs/reviews/wu-tools-cancel-01-s2a1-implementation-codex.md`

---

## Findings

### F01 [MEDIUM] `utils/` 下 3 个 `ToolDefinition(` 构造站点未迁移

**位置：**
- `utils/smoke_host_public_conversation_memory.py:717`
- `utils/smoke_host_public_conversation_memory_scenarios.py:3406`
- `utils/smoke_host_public_multiturn.py:630`

**证据：**

```bash
rg -n "ToolDefinition\(" utils/
# 命中 3 处，均未传入 execution=...
```

**分析：**

Plan 规定的 scan 命令为 `rg -n "ToolDefinition\\(" dayu tests`，明确只扫描 `dayu/` 和 `tests/` 目录，未覆盖 `utils/`。Implementation report 也如实写明了 "sites in `dayu` and `tests` scanned by the required command"——scope 声明是准确的。

这三个文件属于分析辅助代码（`utils/`），项目 CLAUDE.md 明确规定 `utils/` 下的脚本默认无需测试、无覆盖率要求。由于 `execution` 字段有 `default_factory=AsyncDirectToolExecutionCapability`，这三个站点不会运行时 break，pyright 验证通过（0 errors）。

**但是：**

`utils/` 下的 `ToolDefinition(` 构造现在依赖 `default_factory` 的静默行为——如果未来 `ToolDefinition` 的 `execution` 语义发生演化（比如 `default_factory` 被移除，或默认值改为其他 mode），这些站点会在**无类型检查告警的情况下**获得错误语义。且项目 CLAUDE.md 要求"禁止把显式参数放进 extra payload"，这里的 symmetrically——显式参数也不应被 field default 悄悄替代，尤其是 production-facing smoke 脚本在模拟真实 tool declaration 流时。

**裁决：** 建议修复。这三个站点应显式添加 `execution=AsyncDirectToolExecutionCapability()`，与所有 `dayu/` 和 `tests/` 站点的迁移方式一致。Implementation report 应记录此排除及其理由（`utils/` 被 plan scan 命令 scope 排除 + default_factory 兜底）；但如果评审者认为 `utils/` 也属于"直接 `ToolDefinition` 构造站点"，则此条为 REQUIRED FIX。

**风险等级：** 低——当前无运行时或类型错误，但存在未来语义漂移风险。

---

### F02 [LOW] `default_factory=AsyncDirectToolExecutionCapability` 的语义张力

**位置：** `dayu/contracts/tool_declaration.py:114-116`

```python
execution: ToolExecutionCapability = field(
    default_factory=AsyncDirectToolExecutionCapability
)
```

**分析与裁决：**

Plan 要求"直接构造 `ToolDefinition` 的业务工具 helper 必须显式传入 `execution`"，同时允许"若参数为 `None`，由 helper / decorator 默认成 `AsyncDirectToolExecutionCapability(request_abort_capable=False)`"。这两个约束之间的关系需要精确解读：

1. **`default_factory` 是否等于 "compat wrapper/facade"？** 否。`default_factory` 是 Python frozen dataclass 的标准惯用写法（mutable default 不能用直接赋值），不是为旧接口保留兼容逻辑的 wrapper。Plan 反对的 compat wrapper 是指"方法体仅透传到真源模块，不增加有效语义"的胶水代码——`default_factory` 不在此列。

2. **`default_factory` 是否违反"必须显式传入"？** 存在张力但可接受。Plan 说的"必须显式传入"针对的是已知构造站点（要求逐站迁移），不是禁止 field default。`default_factory` 的作用是防御性兜底——若未来新增构造站点忘记传 `execution`，不会 runtime break。所有 31 个已知 `dayu/` + `tests/` 站点均已显式传入，满足 plan 的迁移要求。

3. **`default_factory` 的隐式语义风险：** `AsyncDirectToolExecutionCapability()` 构造时 `request_abort_capable=False`——这意味着默认行为是"不可中断的 async direct"。如果某个工具实际上应该是 `thread_backed` 或 `process_backed`，但构造时遗漏了 `execution=` 参数，静默获得 `async_direct` 默认——类型检查器不会报错，测试可能不会覆盖。这是 `default_factory` 的固有取舍，不是本实现的缺陷。

**裁决：ACCEPTABLE。** `default_factory` 是合理的防御性设计，不违反 plan 的反模式约束。建议在 `ToolDefinition.execution` 字段 docstring 中显式说明："默认值为 `AsyncDirectToolExecutionCapability(request_abort_capable=False)`；业务工具应在构造时显式声明 execution capability，不依赖 field default。"

---

### F03 [INFO] `tool_declaration.py.__all__` 中 re-export `ToolExecutionCapability`

**位置：** `dayu/contracts/tool_declaration.py:292`

**分析：**

`ToolExecutionCapability` 是 `TypeAlias`，定义在 `dayu/contracts/tool_execution.py`。`tool_declaration.py` import 它用于 `_ToolDecorator.execution` 字段和 `tool()` 参数类型注解，同时将其放入 `__all__`。这是否违反 CLAUDE.md 的"禁止兼容性 re-export"？

不违反。CLAUDE.md 禁止的是"仅为保持旧导入路径而转发符号"——即旧代码 `from dayu.contracts.tool_declaration import Foo` 工作正常，现在 `Foo` 移到了别处，但为了不 break 旧代码在 `tool_declaration.py` 加了一行 `from .new_module import Foo`。`ToolExecutionCapability` 是全新类型，它的 re-export 是因为它和 `ToolDefinition` 语义紧密绑定，放在 `tool_declaration.py` 的 `__all__` 中是合理的 API 暴露，不是兼容性妥协。

**裁决：ACCEPTABLE。** 不是兼容性 re-export。

---

### F04 [INFO] `tests/runtime/test_tools_discovery_digest.py` 中 `_DigestProcessTargetFactory` 的 `factory_id` 字段仅用于测试区分对象身份

**位置：** `tests/runtime/test_tools_discovery_digest.py:110-133`

**分析：**

`_DigestProcessTargetFactory` 有 `factory_id: str` 字段用于在 `test_process_backed_factory_identity_does_not_change_digest` 中构造两个不同 factory 实例以验证"factory 身份不进入 digest"。该字段的语义是测试专用标签，不会泄漏到生产代码。

docstring 说明 `factory_id` 是"仅用于区分对象身份的测试标签"——符合 plan 的"process target factory identity 不入 digest"要求。测试逻辑正确：两个 factory 有不同 `factory_id`（"left" / "right"），但 digest 相同。

**裁决：ACCEPTABLE。** 测试设计合理。

---

## 逐项检查结果

### 1. Scope：严格限于 S2A1 contract/declaration/digest ✅ PASS

| 检查项 | 结果 |
|--------|------|
| 未实现 S2A2 Host factory wiring | ✅ 确认：`dispatch.py` 无变更 |
| 未迁移 Doc/Fins/Web 到 process-backed | ✅ 确认：所有迁移站点均使用 `AsyncDirectToolExecutionCapability()` |
| 未修改 Engine contract | ✅ 确认：无 Engine 文件变更 |
| 未修改 `dayu.runtime.interruptible_process` | ✅ 确认：无该文件变更 |
| 未修改 Host cancel API / EventLog / durable schema | ✅ 确认：无相关变更 |
| 未添加 Host tool-name 分支 | ✅ 确认 |

### 2. `default_factory` 是否违反 plan 精神 ✅ ACCEPTABLE（见 F02）

### 3. `dayu.runtime/tools_discovery.py` 依赖边界 ✅ PASS

- import 来源验证：仅 `dayu.contracts`、`dayu.contracts._validation`、`dayu.runtime._digest`、标准库
- 无 `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 反向依赖
- `_tool_execution_json_value` 使用 `isinstance` 对三种 capability 做穷尽匹配，遇到未知类型抛出 `TypeError`

### 4. execution digest JSON shape ✅ PASS

| Mode | Plan Shape | Implementation | 匹配 |
|------|-----------|---------------|------|
| `async_direct` | `{"mode": "async_direct", "request_abort_capable": bool}` | 一致 | ✅ |
| `thread_backed` | `{"mode": "thread_backed", "production_safe_non_cooperative_cancel": false}` | 一致 | ✅ |
| `process_backed` | `{"mode": "process_backed"}` | 一致 | ✅ |

- Process target factory identity 不进入 digest ✅（`test_process_backed_factory_identity_does_not_change_digest` 验证通过）
- callable 引用不进入 digest ✅（已有测试 `test_callable_identity_change_does_not_change_digest` 验证）

### 5. ProcessBackedToolTarget/Context/Factory 类型完整性 ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `ProcessBackedToolContext` 所有字段为 pickle-safe 标量 | ✅ |
| `ProcessBackedToolTarget.__call__` 返回 `JsonValue` | ✅ |
| `ProcessBackedToolTargetFactory.build_process_target` 接收 `ToolCallRequest` + `ProcessBackedToolContext` | ✅ |
| Docstring 明确禁止返回 awaiting/cancelled/timeout | ✅ |
| Docstring 明确禁止捕获 repository/runtime/session/lock | ✅ |
| Pickle round-trip 测试覆盖 context → factory → target → envelope | ✅ |
| JSON 信封仅 `completed`/`failed` 两种合法形态 | ✅ |
| Thread-backed guard `Literal[False]` | ✅ |

### 6. 所有 ToolDefinition 构造站点迁移 ✅ PASS（含 F01 保留意见）

- `dayu/` 生产站点 6 处：全部显式迁移 ✅
- `tests/` 测试站点 25 处：全部显式迁移 ✅
- `utils/` 辅助站点 3 处：未迁移（见 F01）

### 7. Tests/README/pyright ✅ PASS

| 检查项 | 结果 |
|--------|------|
| `tests/README.md` 更新 | ✅ 新增 execution capability 覆盖描述 |
| `dayu/README.md` 更新 | ✅ 新增 `ToolExecutionCapability` 提及 |
| Pyright | ✅ 0 errors, 0 warnings, 0 informations |
| 测试矩阵（150 passed） | ✅ |
| `git diff --check` | ✅ |
| `test_package_exports.py` 同步 | ✅ 8 个新导出均已加入 `EXPECTED_EXPORTS` |

---

## Adversarial Failure Pass

| 攻击面 | 模拟攻击 | 防御状态 |
|--------|---------|---------|
| 子进程返回 `cancelled`/`timeout` 信封 | Protocol docstring 禁止 + `JsonValue` 返回类型无法在类型层 enforce | ⚠️ 依赖 code review / Host capsule 层防御（Plan 已分配给 S2A2） |
| Process target 捕获 repository lock | Docstring 明确禁止 + pickle round-trip 测试只能验证序列化，不能验证闭包捕获 | ⚠️ 依赖 code review；S2B/S2C/S2D 各自验证 |
| `default_factory` 静默掩盖遗漏的 `execution=` | 所有已知站点已显式迁移 | ✅ 已知站点无遗漏；未来站点风险见 F01/F02 |
| `process_backed` digest 碰撞 | 不同 factory 产相同 digest → 设计如此（plan 明确要求） | ✅ 符合设计 |
| `thread_backed` 被误用为生产 closeout | `Literal[False]` guard + digest 显式记录 | ✅ 测试 `test_thread_backed_capability_guard_is_always_false` 验证 |
| `ToolExecutionCapability` TypeAlias 穷尽性 | `_tool_execution_json_value` 最后分支 `raise TypeError` | ✅ fail-closed |
| Host 工具名分支逃逸 | diff 中无此类代码 | ✅ |
| `dayu.runtime` 反向依赖 | import 扫描通过 | ✅ |

---

## CLAUDE.md 项目指令检查

| 指令 | 检查结果 |
|------|---------|
| 分层架构 `UI -> Service -> Host -> Engine` | ✅ 未违反 |
| `dayu.runtime` 不得 import 上层 | ✅ |
| 禁止反向依赖 | ✅ |
| 禁止 `object`/`Any`/无类型参数 | ✅ 所有新增类型均为强类型 |
| 禁止兼容性 re-export | ✅（见 F03） |
| 禁止 magic number/string | ✅ `ToolExecutionMode` 使用 StrEnum |
| 中文 docstring | ✅ 所有新增模块/类/函数均有完整中文 docstring |
| schema 变更按全新起库 | ✅ 无旧库兼容逻辑 |
| 测试更新 | ✅ 新增 113 行测试 (`test_tool_declaration.py`) + 97 行测试 (`test_tools_discovery_digest.py`) |
| README 触发规则 | ✅ 已检查并按需更新 |

---

## Verdict

**PASS** — with one advisory finding (F01).

S2A1 implementation 严格限于 contract/declaration/digest scope，未越界做 S2A2 Host wiring、dispatch selection 或 Doc/Fins/Web process-backed 迁移。所有 `dayu/` 和 `tests/` 下的 `ToolDefinition(` 直接构造站点已显式迁移。Execution digest JSON shape 完全符合 plan 规定，process target factory identity 不入 digest。`dayu.runtime/tools_discovery.py` 无 Host/Engine/Service/UI/Fins 反向依赖。Pyright 0 errors，测试矩阵 150 passed。中文 docstring、README 更新、pickle round-trip 测试均充分。

F01（`utils/` 下 3 个未迁移站点）建议修复但不阻塞 S2A2 推进——这三个文件依赖 `default_factory` 继续正常工作，无运行时或类型错误。S2A2 开始前修复或记录排除原因均可。

---

## 未覆盖项与 Residual Risk 传递

以下风险由 plan 的 residual risk 章节已识别并分配给后续 slice，本 S2A1 不负责覆盖：

| 风险 | 分配 slice | 状态 |
|------|-----------|------|
| Process target JSON 信封 completed/failed/malformed 映射 | S2A2 | 未覆盖 |
| `BatchToolExecutionContext → ProcessBackedToolContext` 投影不含 `cancellation_token` | S2A2 | 未覆盖 |
| Host declaration-backed capsule factory | S2A2 | 未覆盖 |
| Doc process-backed 迁移 | S2B | 未覆盖 |
| Fins read spawned-child `DefaultFinsRuntime.create` pre-check | S2C | 未覆盖 |
| Web sync process-backed 或 async_direct close 验证 | S2D | 未覆盖 |
| Aggregate interrupt test（同 Run cancel/timeout late result） | S2E | 未覆盖 |
