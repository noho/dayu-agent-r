# P9.5 S11 ToolRuntime Boundary Cleanup Implementation

## Motivation Judgment

问题真实存在，但不适合做大规模模块拆分。

直接证据显示 `dayu/host/tool_runtime.py` 当前为 5150 行，单文件同时承载 effective bundle / schema projection、Host accept barrier、truncation / `fetch_more`、duplicate governance、diagnostics 与 factory wiring。它已经不是“小而 cohesive”的模块。

本 slice 的目标不是按候选 owner 机械拆成多个模块，而是只在能降低真实耦合、或让后续 S12 / S16 更局部化时收窄边界。把 public ToolRuntime 类型迁出会要求保留旧 `dayu.host.tool_runtime` 导入路径；这会变成 compatibility re-export，命中本 slice stop condition。因此本次只抽取不改变公开导入路径的私有 schema projection / digest helper。

## Direct Evidence

- `docs/host/design.md` §2：ToolRuntime / TruncationManager 是 Host-owned 工具治理 owner，Engine 不拥有工具治理。
- `dayu/README.md` “工具定义与执行边界”：Engine 只接收 `tool_schemas` 与 `tool_executor`，不得导入、持有或分支判断 `ToolDefinition`、`ToolBundle`、ToolRuntime 或具体工具实现。
- `docs/host/p9-5-pre-p10-hardening-plan.md` S11：只在移除真实耦合或让 S12 / S16 局部化时抽取；禁止 compatibility re-export、test-only wrapper、lazy import seam、公共 API 变化。
- `wc -l dayu/host/tool_runtime.py`：5150 行，存在真实 owner 聚合压力。
- `dayu/host/tool_runtime.py` 原实现中 schema projection / digest helper 位于 accept barrier、truncation、duplicate、diagnostics 同一模块内，但这些 helper 只服务 effective bundle schema 投影和摘要计算，不拥有 Host accept barrier 或 runtime 状态机。

## Changed Files

- `dayu/host/tool_runtime.py`
  - 保留 `ToolRuntimeHandle`、factory、accept barrier、truncation / `fetch_more`、duplicate governance、diagnostics、public `__all__` 与行为路径。
  - 改为从私有 helper 模块导入 effective schema projection / digest helper。
- `dayu/host/tool_runtime_schema_projection.py`
  - 新增私有 owner，承载 reserved framework name 校验、effective definition name 索引、business bundle digest、tool schema digest 与 schema/truncate JSON projection。
- `tests/host/test_import_boundary.py`
  - 增加 Host 包根不得导出 ToolRuntime / ToolBundle / ToolDefinition owner 的边界测试。
  - 增加私有 schema projection helper 不依赖 Engine 或 Host mutator owner 的边界测试。
- `tests/engine/test_import_boundary.py`
  - 增加 Engine 不得通过 import 引入 `ToolRuntime`、`ToolBundle`、`ToolDefinition` 的专项边界测试。

## Extraction Decision

已执行有限抽取：`tool_runtime_schema_projection.py`。

原因：

- 它移出的是纯 schema projection / digest helper，不改变 public imports，不需要 compatibility re-export。
- 它让 S12 / S16 后续检查工具声明与 schema 投影边界时可以局部检查私有 owner，而不必从 accept barrier / truncation / duplicate 的 5000 行聚合模块中推断。
- 它不改变 EventLog facts、Host accept barrier、duplicate policy、truncation cursor scope、diagnostic refs 或 factory 行为。

未抽取 public owner grouping：

- `EffectiveToolBundle`、`ToolRuntimeHandle`、factory、accept port、diagnostic emitter 等仍从 `dayu.host.tool_runtime` 导入。
- 若迁移这些 public 类型，要么改变公开导入路径，要么引入 compatibility re-export；二者均不符合 S11 stop condition。

## Validation Output

```text
$ source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py tests/host/test_import_boundary.py tests/engine/test_import_boundary.py
45 passed in 0.61s
```

```text
$ source .venv/bin/activate && pytest tests/host/test_toolruntime_*.py
55 passed in 0.26s
```

```text
$ source .venv/bin/activate && python -m pyright dayu/host tests/host dayu/engine tests/engine
0 errors, 0 warnings, 0 informations
```

```text
$ git diff --check
clean
```

## Docs Decision

未更新 README。

原因：本次只新增 Host 私有 helper 模块并补 import-boundary 测试；`dayu/host/README.md` 中 ToolRuntime boundary、public import、accept barrier、truncation、duplicate 与 diagnostics 描述仍与当前代码一致。`tests/README.md` 的测试分层与运行方式也未发生职责变化。

## Residual Risks

- `dayu/host/tool_runtime.py` 仍然较大，accept barrier、truncation、duplicate、diagnostics 与 executor 仍在同一公开模块内；这是为了避免 public type 迁移触发 compatibility re-export 或 public API 变化。
- 新私有 helper 仍复用 `dayu.host.durable.codec.sha256_digest_json` 作为既有 digest 真源；本 slice 没有把 digest helper 下沉到 runtime 或 contracts，避免扩大架构变更。
- S12 / S16 若需要迁移 public ToolRuntime 类型，必须先重新裁决公开导入路径，不能在本 slice 里用 re-export 绕过。

## Stop Status

未触发 stop condition。未引入 public compatibility wrapper、test-only private re-export、semantic change、EventLog fact change、duplicate policy change、truncation cursor scope change、Engine runtime semantic change、commit、push 或 PR。
