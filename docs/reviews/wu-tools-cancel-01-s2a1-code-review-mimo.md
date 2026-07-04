# WU-TOOLS-CANCEL-01 S2A1 Code Review — AgentMiMo

## Gate

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: `S2A1 contract / declaration / digest`
- Reviewer: `AgentMiMo`
- Base commit: `8eddd26b`
- Date: 2026-07-04

## Findings

### F1 [Low] `_tool_execution_json_value` 未使用 `ToolExecutionMode` 枚举

**文件**: `dayu/runtime/tools_discovery.py:472-488`

`_tool_execution_json_value` 用硬编码字符串 `"async_direct"` / `"thread_backed"` / `"process_backed"` 构造 digest JSON，而 `dayu.contracts.tool_execution.ToolExecutionMode` 枚举已定义且已导出这些值。

**影响**: 如果未来有人修改枚举值而忘记同步 digest 函数，digest 会静默漂移。当前值一致所以无运行时错误，但违反 single-source-of-truth 原则。

**建议**: `ToolExecutionMode` 已在 S2A1 定义并导出，digest 应引用 `ToolExecutionMode.ASYNC_DIRECT.value` 等。若认为枚举是 S2A2 专属，至少在函数 docstring 中标注与枚举的对应关系。

---

### F2 [Low] `_tool_execution_json_value` 缺少 TypeError 路径测试

**文件**: `tests/runtime/test_tools_discovery_digest.py`

`_tool_execution_json_value` 对未知 capability 类型 `raise TypeError`（`tools_discovery.py:488`），但无对应测试。现有 digest 测试覆盖了三种已知类型的变化检测，未覆盖 fail-closed 路径。

**建议**: 补充一个测试用 mock/自定义类验证 `TypeError` 被抛出。

---

### F3 [Info] `ToolExecutionMode` 枚举导出但无消费者

**文件**: `dayu/contracts/tool_execution.py:42-51`, `dayu/contracts/__init__.py:128`

`ToolExecutionMode` 已定义并导出到 `dayu.contracts` 公共命名空间，但当前无任何模块 import 或使用它。`tools_discovery.py` 用 `isinstance` 分支 + 硬编码字符串；`host/tool_runtime.py` 有自己的同名内部枚举。

**影响**: 当前无功能问题。S2A2 必须决定是收敛 Host 内部 `ToolExecutionMode`（`tool_runtime.py:357`）到 contracts 版本，还是删除 contracts 中的冗余定义。`host/run_input.py:278` 的 `ToolExecutionMode` 是完全不同的概念（`NO_TOOL_DISABLED` / `NO_TOOL_REPLAY`），不在此列。

---

### F4 [Info] `ToolDefinition.execution` 使用 `default_factory` 而非显式 `| None`

**文件**: `dayu/contracts/tool_declaration.py:111-113`

Plan 草案说"直接构造 ToolDefinition 的业务工具 helper 必须显式传入 execution"，实现用 `field(default_factory=AsyncDirectToolExecutionCapability)` 在 dataclass 层提供默认。`_ToolDecorator` 则用 `execution: ToolExecutionCapability | None = None` 显式处理。

**裁决**: 可接受。理由：
1. 所有 `rg -n "ToolDefinition\(" dayu tests` 命中的构造站点已确认全部显式传入 `execution=AsyncDirectToolExecutionCapability()`，无一遗漏。
2. `default_factory` 是类型安全的 typed default，不是兼容 wrapper/facade，不逃避类型检查。
3. 测试 helper 的 `| None` 默认分支由 `_ToolDecorator` 和测试 helper `_definition()` 显式处理，均 fallback 到 `AsyncDirectToolExecutionCapability()`。
4. 如果未来新增构造站点忘记传 `execution`，会静默使用 async_direct，这恰好是"未声明时默认 async_direct"的 plan 原意。

---

## Scope Compliance

### 1. 是否严格限于 S2A1 contract/declaration/digest

✅ **PASS**。实现严格限于：
- `dayu/contracts/tool_execution.py` 新增
- `dayu/contracts/tool_declaration.py` 扩展 `ToolDefinition` / decorator / `tool()`
- `dayu/contracts/__init__.py` 导出
- `dayu/runtime/tools_discovery.py` digest 投影
- 所有 `ToolDefinition(` 构造站点迁移
- 测试与 README 同步

未做 S2A2 work：未改 `host/dispatch.py`，未改 production capsule 选择，未改 `dayu.runtime.interruptible_process`。

### 2. `default_factory` 裁决

✅ **可接受为 typed default**。见 F4 分析。不是兼容 wrapper/facade，不违反 plan 精神。

### 3. `dayu.runtime/tools_discovery.py` 只依赖 contracts

✅ **PASS**。imports 来自 `dayu.contracts` 和 `dayu.contracts._validation`，无 Host/Engine/Service/UI/Fins 反向依赖。

### 4. execution digest JSON shape

✅ **PASS**。三种 mode 的 JSON shape 完全符合 plan：
- `async_direct`: `{"mode": "async_direct", "request_abort_capable": bool}`
- `thread_backed`: `{"mode": "thread_backed", "production_safe_non_cooperative_cancel": false}`
- `process_backed`: `{"mode": "process_backed"}`

Process target factory identity 不入 digest，由 `test_process_backed_factory_identity_does_not_change_digest` 验证。

### 5. ProcessBackedToolTarget/Context/Factory 类型完整性

✅ **PASS**。
- 类型、docstring、Protocol 签名符合 plan 草案。
- `JsonValue` 信封 contract 在 docstring 中显式声明只允许 `completed` / `failed`，排除 `awaiting` / `cancelled` / `timeout` / `host_cancelled`。
- pickle round-trip 测试覆盖 context、factory、target、envelope 全链路。
- `Literal[False]` guard 阻止 `thread_backed` 被当作非协作 blocking cancel 证据。

### 6. 所有 ToolDefinition 构造站点是否迁移

✅ **PASS**。`rg -n "ToolDefinition\(" dayu tests` 全部命中站点已确认包含 `execution=AsyncDirectToolExecutionCapability()`。生产站点（doc_tools, download_tools, upload_tools, preprocess_tools, tool_runtime fetch_more, tool_declaration decorator）和全部测试 helper 均已迁移。

### 7. Tests/README/pyright

✅ **PASS**。
- `pyright`: 0 errors, 0 warnings, 0 informations
- `pytest` focused suite: 150 passed
- `git diff --check`: passed
- `tests/README.md` 和 `dayu/README.md` 已按触发规则更新

---

## Verdict

**PASS**

S2A1 实现严格限于 contract/declaration/digest 范围，未误入 S2A2。所有构造站点已迁移，digest shape 符合 plan，pickle round-trip 和 thread guard 测试充分，pyright 零错误。

两个 Low 级 findings（F1 枚举未引用、F2 TypeError 路径无测试）不阻塞 gate，可在 S2A2 或后续 cleanup 中处理。S2A2 必须处理 F3（Host 内部 `ToolExecutionMode` 与 contracts 版本的收敛）。
