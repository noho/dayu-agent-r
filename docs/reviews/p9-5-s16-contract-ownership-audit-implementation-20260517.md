# P9.5 S16 Contract Ownership Audit And Import/Public Surface Fixes Implementation

## 动机与审计结论

S16 动机成立，但应保持 audit / guardrail 范围：Contract Ownership 的核心风险不是当前行为错误，而是 Engine / Host / runtime / contracts 的 import 与 public surface 在后续 hardening 中无声漂移。最小正确动作是补自动化边界测试，只有发现直接生产违规时才改生产代码。

本次审计现有 import-boundary / export / fetch_more 测试后确认：

- `dayu.runtime` 已有 AST 扫描，覆盖不 import Engine / Host / Service / UI / Fins。
- `dayu.engine` 已有 AST 扫描，覆盖不 import Host / Service / UI / Fins、HTTP client 边界、tool trace 边界和部分工具声明 owner 符号。
- `dayu.host` 已有 AST 扫描，覆盖不 import Config / Fins / Service / UI、Engine import 只在本地执行边界模块、projection / memory 私有边界和 Host 根不导出 ToolRuntime / ToolBundle / ToolDefinition。
- `dayu.contracts` 已有 AST 扫描，覆盖不 import Engine / Host / Service / UI / Fins，但缺少 runtime implementation owner 检查。
- `dayu.engine` / `dayu.host` 包根导出已有严格白名单测试，当前 documented public exports 稳定，无 accidental private export 需要移除。
- `fetch_more` 已有行为测试覆盖 reserved name 冲突、policy disabled、truncation disabled 和 schema / callable 同源注入，但缺少 attempt-local callable 以及 “引用只留在 ToolRuntime owner” 的 guard。

未发现需要改生产代码的直接违规，因此本次只补测试，不移动 contract、不改 public API、不引入 compatibility wrapper。

## 改动文件摘要

- `tests/contracts/test_import_boundary.py`
  - 将 `dayu.runtime` 加入 `dayu.contracts` 永久禁止 import 前缀，防止公共 contract 依赖 runtime implementation module。

- `tests/engine/test_import_boundary.py`
  - 将 `ToolCallable` 加入 Engine 禁止导入的工具声明 owner 符号集合。
  - 禁止 Engine 直接 import `dayu.contracts.tool_declaration` 模块本身，避免通过模块属性绕开 symbol-level 检查。
  - 更新 synthetic star import 测试，验证 `ToolBundle` / `ToolCallable` / `ToolDefinition` 都会被识别。

- `tests/host/test_import_boundary.py`
  - 新增 Host 禁止 import `importlib` / `pkgutil` 的边界测试，锁住 “Host 不扫描业务工具模块”。
  - 新增 `fetch_more` token owner 测试，限制生产代码中 `fetch_more` 只出现在 `dayu.host.tool_runtime` 与 `dayu.host.tooling`。

- `tests/host/test_toolruntime_effective_bundle.py`
  - 新增 factory attempt-local 测试，验证每次 `DefaultToolRuntimeFactory.create_tool_runtime(...)` 都生成独立 `EffectiveToolBundle` 与独立 `FetchMoreToolCallable`，且不会把 `fetch_more` 污染回业务 `ToolBundle`。

## Contract Ownership 裁决

- `dayu.runtime`：保持层中立基础设施包，不 import Engine / Host / Service / UI / Fins；本次未改生产代码。
- `dayu.contracts`：只承载层间共享 contract，不依赖 concrete Engine / Host / runtime implementation module；新增测试锁住 `dayu.runtime`。
- Engine：继续只消费 `ToolSchema` / `ToolExecutor` / tool call outcome 等 Engine 需要理解的 contract；不得 import `ToolDefinition` / `ToolBundle` / `ToolCallable`、ToolRuntime、Host、memory、Fins 或 concrete tools。
- Host：可拥有 ToolRuntime / memory / durable / projection 等治理实现，但不得 import Service / UI / Fins，不得扫描业务工具模块。
- `fetch_more`：仍是 Host ToolRuntime framework tool，由 ToolRuntime effective bundle 构造路径注入；Engine / Host command / dispatch / contracts / runtime 不为它写特化分支。
- Public exports：`dayu.engine.__all__` 与 `dayu.host.__all__` 现有白名单测试已覆盖 documented stable surface，本次不收缩、不扩张。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/contracts/test_import_boundary.py tests/engine/test_import_boundary.py tests/engine/contracts/test_import_boundary.py tests/host/test_import_boundary.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/contracts/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_toolruntime_effective_bundle.py`
  - 结果：77 passed。
- `source .venv/bin/activate && python -m pyright dayu tests`
  - 结果：0 errors / 0 warnings / 0 informations。
- `git diff --check`
  - 结果：clean。

## README 决策

本次只补测试 guard，没有改变 public API、包根导出、ToolRuntime 行为、fetch_more 语义、Host / Engine 分层或测试运行约定。`dayu/README.md`、`dayu/host/README.md` 与 `tests/README.md` 当前已描述 Contract Ownership、Host 不扫描业务工具模块、ToolRuntime effective bundle / fetch_more 行为和测试覆盖范围，因此不更新 README。

## 剩余风险

- `fetch_more` owner 测试以生产源码 token 扫描作为 guard，能防止 Host / Engine 特化分支回归，但不是语义证明；行为语义仍由 ToolRuntime effective bundle / executor / accept barrier 测试覆盖。
- Host 禁止 `importlib` / `pkgutil` 是有意收紧的扫描能力 guard；若未来 Host 确有非业务扫描的基础设施需求，需要先重新裁决 owner，而不是直接放宽。
- 本次未跑全量测试，只跑 S16 targeted tests、全量 pyright 与 diff check；针对本 slice 风险足够，但不替代后续 aggregate validation。
