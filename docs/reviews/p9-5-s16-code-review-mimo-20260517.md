# P9.5 S16 Code Review — Contract Ownership Audit And Import/Public Surface Fixes

## Review Context

- Reviewer: AgentMiMo
- Scope: S16 Contract Ownership Audit And Import/Public Surface Fixes
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S16
- Implementation artifact: `docs/reviews/p9-5-s16-contract-ownership-audit-implementation-20260517.md`
- Diff: uncommitted changes on `p9.5-pre-p10-hardening`

## Verdict: PASS

S16 实现正确。所有变更为 test-only guard，未改生产代码，符合"只有发现直接生产违规时才改生产代码"的审计原则。import-boundary guards 符合 Contract Ownership 设计，`fetch_more` attempt-local 测试有效。

---

## Findings

### F1 — `dayu.runtime` 加入 `dayu.contracts` 禁止前缀

**Severity: PASS**

`tests/contracts/test_import_boundary.py:24` 将 `dayu.runtime` 加入 `CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES`。

**架构理由**：
- `dayu.contracts` 是层间共享 contract 层，应为最低依赖层
- `dayu.runtime` 是层中立运行期基础设施（日志装配、lane、filelock）
- contracts 不应依赖 runtime implementation module

**验证**：grep 确认 `dayu/contracts/*.py` 当前无 `dayu.runtime` import。此为预防性 guard。

**判定**：正确。contracts 作为最低依赖层不应反向依赖 runtime。

---

### F2 — Engine 禁止 `ToolCallable` 和模块级 `dayu.contracts.tool_declaration` 检查

**Severity: PASS**

`tests/engine/test_import_boundary.py` 做了两处增强：

1. `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS` 增加 `ToolCallable`（line 38）
2. `_engine_tool_ownership_import_violations` 增加模块级检查（line 103-105）

**架构理由**：
- 设计要求 Engine 只消费 `ToolSchema` / `ToolExecutor`，不持有 `ToolDefinition` / `ToolBundle` / `ToolCallable`
- `dayu.contracts.tool_declaration.__all__` 导出 `ToolBundle`、`ToolCallable`、`ToolDefinition`
- 模块级检查防止通过 `import module` 后 `module.ToolCallable` 绕开 symbol-level 检查

**测试更新**：`test_engine_tool_ownership_boundary_detects_tool_declaration_star_import` 现在期望 4 条违规（module + ToolBundle + ToolCallable + ToolDefinition），正确反映了两层检查。

**验证**：grep 确认 `dayu/engine/*.py` 当前无 `dayu.contracts.tool_declaration` import。此为预防性 guard。

**判定**：正确。Engine 不应持有工具执行语义。

---

### F3 — Host 禁止 `importlib` / `pkgutil` 业务工具扫描

**Severity: PASS**

`tests/host/test_import_boundary.py:191-203` 新增 `test_host_does_not_import_business_tool_scanners`。

**架构理由**：
- 设计要求 Host 不做工具发现、模块扫描或注册生命周期管理
- `ToolsDiscovery` 独立于 Host，由外部装配传入 `ToolBundle`
- Host 不应通过 `importlib` / `pkgutil` 动态扫描业务工具模块

**验证**：grep 确认 `dayu/host/*.py` 当前无 `importlib` / `pkgutil` import。此为预防性 guard。

**判定**：正确。Host 不应拥有业务工具扫描能力。

---

### F4 — `fetch_more` token owner 测试

**Severity: PASS**

`tests/host/test_import_boundary.py:206-222` 新增 `test_fetch_more_token_stays_inside_toolruntime_owner_modules`。

**架构理由**：
- `fetch_more` 是 Host ToolRuntime framework tool
- 由 ToolRuntime effective bundle 构造路径注入
- Engine / Host command / dispatch / contracts / runtime 不应为它写特化分支

**允许列表**：
- `host/tool_runtime.py` — 主实现（`FetchMoreToolCallable`、`_fetch_more_tool_definition` 等）
- `host/tooling.py` — `FrameworkToolName.FETCH_MORE` 枚举

**验证**：explore agent 确认 `fetch_more` token 只出现在上述两个文件中（`.py` 文件）。允许列表完整。

**方法论说明**：测试使用 string token 扫描（`FETCH_MORE_OWNERSHIP_TOKEN in file_path.read_text()`），不是 AST 分析。若未来 `fetch_more` 出现在注释或 docstring 中可能产生误报，但当前无此问题。实现 artifact 已记录此为"guard，不是语义证明"。

**判定**：正确。`fetch_more` ownership 边界清晰。

---

### F5 — `test_factory_creates_attempt_local_fetch_more_callable`

**Severity: PASS**

`tests/host/test_toolruntime_effective_bundle.py:205-237` 新增测试覆盖 attempt-local 隔离。

**断言覆盖**：

| 断言 | 验证内容 |
|------|----------|
| `first_handle.effective_bundle is not second_handle.effective_bundle` | 每次 factory 调用生成独立 bundle |
| `fetch_more_callable is not` 跨 handle | callable 实例隔离 |
| `fetch_more_callable is definitions_by_name["fetch_more"].callable` | callable 与 definition 同源 |
| `business_bundle is not` 跨 handle | business bundle 隔离 |
| `"fetch_more" not in business_bundle.definitions` | fetch_more 不污染业务 bundle |

**架构理由**：
- S16 plan 要求"Validate `fetch_more` is injected only by ToolRuntime factory into attempt-local effective ToolBundle"
- 测试证明 factory 每次生成独立 effective bundle，`fetch_more` 不跨 attempt 复用，不污染 business bundle

**判定**：测试有效，覆盖了 `fetch_more` attempt-local 隔离的关键不变量。

---

### F6 — 中文 docstring 和类型约束

**Severity: PASS**

逐项检查新增代码：

| 文件 | 函数/测试 | docstring | 类型标注 |
|------|-----------|-----------|----------|
| `test_import_boundary.py` | `test_host_does_not_import_business_tool_scanners` | 中文 ✓ | N/A（测试函数） |
| `test_import_boundary.py` | `test_fetch_more_token_stays_inside_toolruntime_owner_modules` | 中文 ✓ | N/A |
| `test_toolruntime_effective_bundle.py` | `test_factory_creates_attempt_local_fetch_more_callable` | 中文 ✓ | N/A |
| `test_toolruntime_effective_bundle.py` | `_fetch_more_enabled_handle` | 中文 ✓ | 返回类型 `ToolRuntimeHandle` ✓ |

所有新增函数均有中文 docstring，包含 `:returns:` 和 `:raises:` 参数。类型标注完整。

**判定**：符合编码硬约束。

---

### F7 — package exports 稳定性

**Severity: PASS (无变更)**

S16 plan 要求"Audit public exports: documented `dayu.engine` and `dayu.host` exports remain stable"。

实现 artifact 说明：

> `dayu.engine.__all__` 与 `dayu.host.__all__` 现有白名单测试已覆盖 documented stable surface，本次不收缩、不扩张。

现有测试文件：
- `tests/engine/test_package_exports.py`
- `tests/host/test_package_exports.py`

本次 diff 未修改这些文件，说明审计未发现需要移除的 accidental private export。

**判定**：public exports 稳定，无需变更。

---

### F8 — 全量测试覆盖

**Severity: INFO (已记录)**

实现 artifact 记录"本次未跑全量测试，只跑 S16 targeted tests、全量 pyright 与 diff check"。此为 test-only slice，targeted tests 足够覆盖变更风险，但不替代后续 aggregate validation（S18）。

**判定**：可接受，已在 artifact 中记录。

---

## Summary

| Finding | Description | Severity |
|---------|-------------|----------|
| F1 | `dayu.runtime` 加入 contracts 禁止前缀 | PASS |
| F2 | Engine 禁止 `ToolCallable` + 模块级检查 | PASS |
| F3 | Host 禁止 `importlib` / `pkgutil` | PASS |
| F4 | `fetch_more` token owner 测试 | PASS |
| F5 | `fetch_more` attempt-local 隔离测试 | PASS |
| F6 | 中文 docstring 和类型约束 | PASS |
| F7 | package exports 稳定 | PASS |
| F8 | 全量测试覆盖 | INFO |

## 结论

S16 实现完整、正确。所有变更为预防性 test-only guard，未改生产代码，符合审计原则。import-boundary guards 符合 Contract Ownership 设计，`fetch_more` attempt-local 测试有效覆盖关键不变量。无 blocker finding。可以接受。
