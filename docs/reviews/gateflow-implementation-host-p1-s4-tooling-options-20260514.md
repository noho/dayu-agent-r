# Host Phase 1 Slice 4 Implementation: Tooling Options

## Changed Files

- `dayu/host/tooling.py`
  - 新增 `ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions` 与 `default_framework_tool_policy_view()`。
  - `ToolBundleSourceKind` 按 approved plan 与 `docs/host/design.md` 真源实现为 `explicit_provider`、`config_binding`、`package_entrypoint`、`service_composition`。
  - `ToolBundleSourceRef` 校验 `source_id` 非空，`version_ref` / `content_digest` 存在时非空。
  - `FrameworkToolPolicyView` 校验 enabled framework tools 是 reserved framework tool names 的子集。
  - `HostToolingOptions` 校验 `source_refs` 非空，并拒绝业务 `ToolBundle` 占用 reserved framework tool name，例如 `fetch_more`。
- `dayu/host/__init__.py`
  - 从 `dayu.host.tooling` 导出 Slice 4 public symbols。
  - 保持 `dayu.host.api` 只承载 request / snapshot / status / context / error 边界。
- `tests/host/test_tooling_options.py`
  - 新增 tooling options 覆盖：`StrEnum`、默认 policy、frozen / frozenset、enabled subset、source ref 字符串校验、source refs 非空、reserved name 冲突、正常 bundle、默认 policy 不共享可变状态。
- `tests/host/test_package_exports.py`
  - 更新包根导出白名单。
  - 明确 tooling symbols 从包根导出但不进入 `dayu.host.api.__all__`。
- `tests/host/test_import_boundary.py`
  - 保持 Host 不导入 Engine / Fins / Service / UI 的边界测试。
  - 增加 Host request dataclasses 不携带 `business_tool_bundle` 字段的断言。
- `dayu/host/README.md`
  - 同步当前已实现 Host tooling options 边界、校验规则和 non-goals。
- `dayu/README.md`
  - 同步项目级 Host / ToolBundle / HostToolingOptions 术语与边界。
- `tests/README.md`
  - 同步 host tooling options 测试入口和维护约定。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_tooling_options.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
  - 通过：`14 passed in 0.09s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过：无输出
- 补充验证：`source .venv/bin/activate && pytest tests/host -q`
  - 通过：`26 passed in 0.09s`

## Non-Goals

- 未实现 ToolRuntime factory。
- 未注入 `fetch_more`。
- 未解析 policy provider。
- 未实现 ToolsDiscovery / ScenePrepare provider contract。
- 未实现 tool profile registry。
- 未实现 Attempt tool snapshot durability、bundle digest 或 schema digest。
- 未修改 Engine / Fins / Service / UI、`dayu.runtime/**`、Host durable store、command path、EventLog、state machine、dispatch、ToolRuntime factory 或 policy provider。

## Residual Risks

- `HostToolingOptions` 当前只做 construction-time typed boundary 与 reserved name 防御性校验；durable tool snapshot refs、bundle / schema digest 与 policy binding refs 仍需后续 ToolRuntime / command path phase 落地。
- 当前只支持单个 construction-time business `ToolBundle`；多 scene tool profile 仍需先定义 profile registry / ref typed contract，并冻结到 Attempt snapshot。

## Stop Condition Status

- 未触发 stop condition。
- 本 slice 未需要决定 ToolsDiscovery / ScenePrepare provider contract、tool profile registry、Attempt snapshot durability、ToolRuntime policy resolution 或 framework tool injection。
