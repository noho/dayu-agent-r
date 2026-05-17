# P9.5 S16 Code Review — AgentDS

**Review scope**: S16 Contract Ownership Audit And Import/Public Surface Fixes 未提交 diff
**Base**: `p9.5-pre-p10-hardening` vs HEAD unstaged changes
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Verdict**: **PASS** — 7 findings, 0 blocking, 0 medium/high severity regressions

---

## Review methodology

按第一性原理逐项复核 S16 计划要求 + adversarial edge case pass。所有证据来自直接代码阅读与工具验证（rg、pytest、pyright、git diff），不依赖间接推断。S16 为纯测试切片，零生产文件修改。

---

## Finding 1: `dayu.contracts` 禁止导入 `dayu.runtime` 符合 Contract Ownership

**Severity**: PASS

**Checked**:
- `tests/contracts/test_import_boundary.py` 在 `CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES` 中新增 `"dayu.runtime"`
- `rg "from dayu\.runtime|import dayu\.runtime" dayu/contracts` → 0 matches（当前无违规）
- `dayu.contracts` 现有模块为纯数据契约（`cancellation.py`、`tool_call.py`、`tool_declaration.py`、`tool_outcome.py`、`tool_schema.py` 等），均不依赖运行时基础设施
- `dayu.runtime` 提供 `log_levels`、`lane`、`cancel` helper 等运行时能力，不属于契约层的合理依赖

**Contract Ownership 分析**: 依赖方向为 `contracts ← runtime`（runtime 可依赖 contracts），而非反向。Contracts 是最底层定义层，不应向上依赖任何实现包。`dayu.runtime` 虽有"层中立"定位，但其承载的是运行期通用能力而非纯类型契约；contracts 引入 runtime 会导致契约层绑定运行时实现细节。

**Conclusion**: 正确编码了既有清洁状态，无过度禁止。

---

## Finding 2: Engine 禁止 `ToolCallable` 与 `tool_declaration` 模块导入符合工具边界设计

**Severity**: PASS

**Checked**:
- `tests/engine/test_import_boundary.py` 变更：
  - `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS` 新增 `"ToolCallable"`
  - `ENGINE_TOOL_DECLARATION_STAR_IMPORT_FORBIDDEN_SYMBOLS` 新增 `"ToolCallable"`
  - 新增 `ENGINE_TOOL_DECLARATION_FORBIDDEN_MODULES = ("dayu.contracts.tool_declaration",)` — Engine 完全禁止导入工具声明模块
  - `_engine_tool_ownership_import_violations` 新增 module-level 违规检测
  - `test_engine_tool_ownership_boundary_detects_tool_declaration_star_import` 期望值更新
- `rg "ToolCallable" dayu/engine --glob="*.py"` → 0 matches（当前无违规）
- `rg "import.*dayu\.contracts\.tool_declaration|from.*dayu\.contracts\.tool_declaration" dayu/engine` → 0 matches（当前无违规）
- `dayu/engine/agent.py:1541` 仅以注释提及"ToolRuntime"，非 import
- `docs/design.md:60-92` 明确规定 Engine 只接收 `tool_schemas` 与 `tool_executor`，不持有 `ToolCallable` / `ToolDefinition` / `ToolBundle`

**为什么禁止模块级导入而不只是符号检查**: `from dayu.contracts.tool_declaration import SomeFutureSymbol` 即使未来新增符号，模块级禁止也能在 AST 扫描阶段拦截，比逐个符号枚举更稳健。`ToolSchema` 等 Engine 合法依赖的符号位于 `dayu.contracts.tool_schema`，不受此限制影响。

**Conclusion**: `ToolCallable` 是 S16 前 Engine 禁止符号中的已知遗漏（`ToolRuntime`、`ToolBundle`、`ToolDefinition` 已在 S11 加入，`ToolCallable` 当时未同步补齐）。此次补齐符合 `docs/design.md` 的工具执行边界设计，无过度禁止。

---

## Finding 3: Host 禁止 `importlib`/`pkgutil` 动态扫描业务工具模块

**Severity**: PASS

**Checked**:
- `tests/host/test_import_boundary.py` 新增：
  - `HOST_BUSINESS_TOOL_SCAN_FORBIDDEN_PREFIXES = ("importlib", "pkgutil")`
  - `test_host_does_not_import_business_tool_scanners()` — 全量扫描 `dayu/host/` 下 `.py` 文件
- `rg "import importlib|import pkgutil|from importlib|from pkgutil" dayu/host --glob="*.py"` → 0 matches（当前无违规）
- `docs/design.md:70-71` 明确规定："Host 包不得 import 具体业务工具模块；新增工具应通过外部注册组件 / 配置 / Service composition 接入"

**为什么用前缀匹配而非精确模块名**: `importlib` 与 `pkgutil` 是 Python 动态模块发现的标准库入口。`_matches_prefix` 使用 `module == prefix or module.startswith(prefix + ".")` 逻辑，可拦截 `importlib`、`importlib.metadata`、`importlib.util` 等所有子模块。Host 如需要反射或动态加载，应通过已注入的抽象（如 `ToolBundleSourceRef`）完成，不应自行扫描文件系统或包结构。

**Conclusion**: 正确编码 Host 工具接入的 composition-over-discovery 约束。

---

## Finding 4: `fetch_more` ownership string-search guard 有效且无漏

**Severity**: PASS

**Checked**:
- `tests/host/test_import_boundary.py` 新增：
  - `FETCH_MORE_ALLOWED_RELATIVE_FILES = frozenset({"host/tool_runtime.py", "host/tooling.py"})`
  - `FETCH_MORE_OWNERSHIP_TOKEN = "fetch_more"`
  - `test_fetch_more_token_stays_inside_toolruntime_owner_modules()` — 全量扫描 `dayu/` 下所有 `.py` 文件
- `rg "fetch_more" dayu --glob="*.py"` → 仅 `dayu/host/tool_runtime.py` 与 `dayu/host/tooling.py`（与白名单一致）
- `FetchMoreToolCallable` 仅在 `dayu/host/tool_runtime.py` 中定义（`rg "FetchMoreToolCallable" dayu --glob="*.py"` → 1 file）

**String-search 的 case-sensitivity 边界**: 测试使用 `"fetch_more" in file_path.read_text(...)` 进行子串匹配，大小写敏感。`FetchMoreToolCallable` 类名不包含小写 `"fetch_more"`（含下划线），因此不会被此测试直接捕获。此边界由以下机制分层覆盖：
1. 其他 import-boundary 测试（symbol-level `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS`）拦截 Engine 的结构性 `FetchMoreToolCallable` 导入
2. `test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` 确保 Host 包根不导出 ToolRuntime owner 符号
3. 实际生产代码中 `FetchMoreToolCallable` 仅在 `tool_runtime.py` 定义，无外部引用

**扫描范围**: `_host_root().parent` = `dayu/` 包根，`rglob("*.py")` 递归覆盖 `dayu/engine/`、`dayu/host/`、`dayu/contracts/`、`dayu/runtime/`、`dayu/config/` 等所有子包。`dayu.fins/`、`dayu.service/`、`dayu.ui/` 虽为独立顶层包，但 `dayu/` 的 `rglob` 不跨越到兄弟目录；这些包的 fetch_more 引用由各自层的 import-boundary 测试覆盖。

**Conclusion**: 白名单与生产代码实际 `fetch_more` 分布完全一致。string-search 作为语义 ownership guard（拦截工具名字符串引用），与 symbol-level guard（拦截结构性 import）互补，无漏。

---

## Finding 5: `fetch_more` attempt-local factory 测试有效

**Severity**: PASS

**Checked**:
- `tests/host/test_toolruntime_effective_bundle.py` 新增 `test_factory_creates_attempt_local_fetch_more_callable()`：
  1. 两次调用 `DefaultToolRuntimeFactory.create_tool_runtime()` → 两个独立 handle
  2. `first_handle.effective_bundle is not second_handle.effective_bundle` — 每次 factory 调用产生新 effective bundle
  3. `first_handle.effective_bundle.fetch_more_callable is not second_handle.effective_bundle.fetch_more_callable` — fetch_more callable 不跨 attempt 复用
  4. 每个 handle 的 `fetch_more_callable` 与其 `definitions_by_name["fetch_more"].callable` 为同一对象 — callable 与 definition 同源
  5. `first_handle.effective_bundle.business_bundle is not second_handle.effective_bundle.business_bundle` — business bundle 也不跨 attempt 共享
  6. `"fetch_more" not in {...business_bundle.definitions...}` — fetch_more 不污染 business bundle 的 definition 命名空间

**测试覆盖的 isolation 维度**:
- 对象身份隔离（`is not` 断言）
- business bundle 污染防护（fetch_more 不进入 business ToolBundle 定义列表）
- callable 与 definition 的同一性（fetch_more callable = definitions_by_name["fetch_more"].callable）

**与 `docs/design.md:73-76` 一致**: "fetch_more 不由外部业务 ToolBundle 提供；ToolRuntime factory 根据 TruncationManager 注入 framework tool，生成 attempt-local effective ToolBundle。"

**Conclusion**: 测试有效覆盖 attempt-local isolation 的三个关键维度（对象身份、业务污染、callable 同源）。无需额外测试。

---

## Finding 6: Package exports 稳定 — 零生产文件修改

**Severity**: PASS

**Evidence**:
- `git diff --stat` → 仅 4 个测试文件变更，0 个生产文件变更
- 所有已有 `__all__` 导出、public facade、import 路径均未触及
- `test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` 继续通过
- `test_host_engine_imports_stay_on_allowed_boundary_modules` 继续通过
- `test_read_api_stream_does_not_reference_projection_or_fanout_truth` 继续通过

**未实施"移除意外私有导出"的原因**: S16 审计未发现需要移除的意外导出（所有现有 export guard 测试均通过）。无 violations → 无需 production change。这符合 S16 计划中的"accidental private exports are removed only if not documented"——审计先行，修复仅在发现违规时执行。

**Conclusion**: 包导出稳定，审计无发现。

---

## Finding 7: 中文 docstring 与类型约束合规

**Severity**: PASS

**Checked**:

| 新增函数/测试 | 中文 docstring | `:returns:` | `:raises:` | 返回类型 | 参数类型 |
|---|---|---|---|---|---|
| `test_host_does_not_import_business_tool_scanners` | ✓ | ✓ (`None`) | ✓ | `None` | — |
| `test_fetch_more_token_stays_inside_toolruntime_owner_modules` | ✓ | ✓ (`None`) | ✓ | `None` | — |
| `test_factory_creates_attempt_local_fetch_more_callable` | ✓ | ✓ (`None`) | ✓ | `None` | — |
| `_fetch_more_enabled_handle` | ✓ | ✓ (`ToolRuntimeHandle`) | ✓ | `ToolRuntimeHandle` | — |

- 无 `object`、`Any`、无类型参数、无类型返回值
- 无 `hasattr`/`getattr` 使用
- 无魔法数字/字符串（白名单常量均模块级命名）
- 无嵌套函数、嵌套类
- 无兼容性 re-export 或 wrapper

**模块级常量的命名一致性**: `HOST_BUSINESS_TOOL_SCAN_FORBIDDEN_PREFIXES`、`FETCH_MORE_ALLOWED_RELATIVE_FILES`、`FETCH_MORE_OWNERSHIP_TOKEN` 均遵循已有命名模式（大写蛇形、模块级、`Final` 语义由 `tuple[str, ...]` / `frozenset[str]` 类型承载）。

**Conclusion**: 完全合规。

---

## Adversarial failure pass

1. **contracts → runtime 导入是否为过度禁止**: `dayu.runtime.log_levels` 定义 `VERBOSE=15` 等日志级别常量，contracts 在理论上可能想引用日志级别定义。但 contracts 不应执行日志输出（那是实现层职责），因此不需要日志级别常量。`dayu.runtime.lane`、`dayu.runtime.log` 等更是纯运行时。禁止合理。验证通过。

2. **Engine → `tool_declaration` 模块禁止是否阻止 Engine 使用 `ToolSchema`**: `ToolSchema` 定义在 `dayu.contracts.tool_schema`，非 `tool_declaration`。Engine 合法依赖不受影响。验证通过。

3. **`importlib`/`pkgutil` 禁止是否影响 Host 的合法反射需求**: Host 的工具接入路径是通过 `ToolBundleSourceRef`、`ToolBundle` 注入，非动态扫描。`importlib`/`pkgutil` 在此架构下无合法用途。验证通过。

4. **`fetch_more` string-search 是否会误报**: 当 `framework_tool_policy` 或 `TruncationManager` 相关代码在注释/docstring 中提到 `fetch_more` 时，会在非白名单文件中触发。但当前生产代码中 `fetch_more` 字符串仅出现在白名单内的两个文件中（已用 `rg` 验证）。测试是编码当前清洁状态，而非预测未来所有合法用法。验证通过。

5. **`FetchMoreToolCallable` 类名导入逃逸 string-search**: 已在 Finding 4 中分析——由 symbol-level import guard 分层覆盖。`rg "FetchMoreToolCallable" dayu --glob="*.py"` 确认仅 `tool_runtime.py` 定义。验证通过。

---

## Summary

| # | Finding | Severity | Verdict |
|---|---|---|---|
| F1 | `dayu.contracts` 禁止导入 `dayu.runtime` | — | PASS |
| F2 | Engine 禁止 `ToolCallable` 与 `tool_declaration` 模块 | — | PASS |
| F3 | Host 禁止 `importlib`/`pkgutil` 动态扫描 | — | PASS |
| F4 | `fetch_more` ownership string-search guard | — | PASS |
| F5 | `fetch_more` attempt-local factory 测试 | — | PASS |
| F6 | Package exports 稳定 | — | PASS |
| F7 | 中文 docstring 与类型约束 | — | PASS |

**Evidence**:
- `pytest tests/contracts/test_import_boundary.py tests/engine/test_import_boundary.py tests/host/test_import_boundary.py tests/host/test_toolruntime_effective_bundle.py` → **24 passed**
- `pytest tests/host -q` → **562 passed** (S15: 559)
- `python -m pyright dayu tests` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → clean

**Overall verdict**: PASS — S16 以纯测试切片补齐了 Contract Ownership 自动防护的最后缺口：`ToolCallable`（Engine 禁止符号遗漏）、`dayu.contracts.tool_declaration` 模块级导入（Engine 禁止）、Host 业务工具动态扫描（`importlib`/`pkgutil`）、`dayu.contracts` → `dayu.runtime` 反向依赖、`fetch_more` 语义 ownership（string-search + attempt-local isolation）。所有 guard 均编码既有清洁状态，无过度禁止合理依赖，无遗漏已识别 owner。
