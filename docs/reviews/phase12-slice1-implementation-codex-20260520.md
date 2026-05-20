# Phase 12 Slice 1 Implementation Artifact - AgentCodex

## Summary

- 新增 `dayu/contracts/tool_source.py`，将 `ToolBundleSourceKind` / `ToolBundleSourceRef` 迁入 `dayu.contracts` 作为 canonical source ref 契约。
- 更新 `dayu/host/tooling.py`，Host tooling 继续使用并导出同一 canonical source ref 类型，未新增或重塑 `HostToolingOptions` 字段与 Host 行为。
- 新增 `dayu/runtime/tools_discovery.py`，实现层中立 `ToolsDiscovery`、provider spec / callable protocol、import path / package entry point 解析、provider report 与 `ToolBundle` 聚合。
- 新增 `tests/runtime/test_tools_discovery.py`，覆盖 fake callable 聚合、import path、entry point、重复 provider identity、重复工具名、disabled provider、空输出失败与 `allow_empty` 成功。
- 更新 `tests/host/test_tooling_options.py`，验证 Host 包根 source ref 导出直接等于 `dayu.contracts` canonical 类型。
- 更新 `dayu/runtime/__init__.py` 与 `dayu/README.md`，同步 runtime / contracts 稳定边界说明。

## Contract Decisions

- `ToolBundleSourceKind` / `ToolBundleSourceRef` 的 ownership 下移到 `dayu.contracts.tool_source`；`dayu.host.tooling` 不再定义旧类型，只引用 canonical type。
- `ToolsDiscoveryProviderSpec` 只携带显式 `spec_id`、provider location、`enabled`、`allow_empty` 与 `Mapping[str, JsonValue]` config，不携带 Host / Service 上下文。
- provider callable 同步返回 `ToolsDiscoveryProviderOutput`，其中包含 provider identity、version ref、source refs 与 `ToolDefinition` 集合。
- provider location 第一版只支持显式 `module:attribute` import path 与 package entry point group/name；不做递归 package 扫描。
- `ToolsDiscoveryResult` 只返回 `ToolBundle`、provider reports 与 source refs，不返回或保存 raw discovery adapter / callable。
- Slice 1 不实现 digest 与 framework reserved-name validation；Host 现有 reserved-name 行为保持不变。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q`
  - Result: `26 passed in 0.70s`
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && git diff --check`
  - Result: passed with no output.
- Additional boundary check: `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - Result: `6 passed in 0.54s`

## README Sync Decision

- `dayu/runtime` 新增公共层中立工具发现能力，且 `dayu/contracts` 新增 source ref canonical 契约，触发 `dayu/README.md` 检查。
- 已更新 `dayu/README.md` 中 runtime 能力、contracts 边界与新业务工具扩展入口说明。
- 未更新 `dayu/host/README.md`：Host public surface 名称未变，`ToolBundleSourceKind` / `ToolBundleSourceRef` 仍作为 Host 包根稳定导出；本文档当前表述未与代码行为冲突。
- 未更新 `tests/README.md`：测试分层与运行方式未变化。

## Residual Risk

- Package entry point 测试使用 monkeypatch 的 `importlib.metadata.entry_points`，覆盖解析行为但不验证真实安装包 metadata；真实插件分发路径可在后续 ConfigLoader / packaging 集成测试覆盖。
- Slice 1 未计算 source refs digest，也未在 runtime 侧拒绝 reserved framework tool name；这些均属于 accepted plan 的 Slice 2 范围。
- `ToolsDiscoveryProviderSpec.config` 是 typed JSON mapping，但本 slice 不做 JSON runtime validator；当前契约只保证类型边界，外部配置文件解析校验由后续 ConfigLoader slice 负责。

## Completion Status

Phase 12 Slice 1 assigned implementation completed. No stop condition was hit.

## Fix Addendum - P12-S1-F1

Accepted finding source: `docs/reviews/phase12-slice1-code-review-controller-adjudication-20260520.md`.

Changed files:

- `dayu/runtime/tools_discovery.py`: wraps `ModuleNotFoundError` from explicit provider import path module import as `ToolsDiscoveryError`, preserving exception chaining with `from exc`.
- `tests/runtime/test_tools_discovery.py`: adds focused coverage for a missing import path module raising `ToolsDiscoveryError` with a `ModuleNotFoundError` cause.

Validation after fix:

- `source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q`
  - Result: `27 passed in 0.60s`
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && git diff --check`
  - Result: passed with no output.

Scope / residual risk:

- No Slice 2 digest or reserved-name runtime validation was implemented.
- No ConfigLoader, ScenePrepare, Host durable state, Engine, Service, UI, Fins, config schema, or prompt asset changes were made.
- No blocker remains for P12-S1-F1.
