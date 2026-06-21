# WU-TOOLS-01-F03-R4 Plan Review — AgentMiMo

## Reviewed Target And Scope

- **Target**: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`
- **Scope**: Tools Discovery spec semantics cleanup — 删除 `allow_empty`、`include_read_tools`、upload `allowed_upload_roots`；Fins `workspace_root` 默认值迁移到 `workspace/`；limits 显式化；Doc provider 默认 `enabled=false`。
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md` WU-TOOLS-01-F03-R4 章节
- **Review timestamp**: 20260621-072155

## Assumptions Tested

1. ConfigLoader 只原样读取，不做业务路径解析 → plan 正确遵守。
2. ToolsDiscovery 只做显式 provider 聚合 → plan 正确遵守。
3. Service assembly 做 effective mapping → plan 正确遵守，但 wait adapter 路径有缺口。
4. Host/Engine 不拥有工具发现或 Fins 业务语义 → plan 正确遵守。
5. 删除 `allow_empty` 后启用 provider 空输出一律 fail fast → plan 正确实现。
6. Fins `workspace/` 相对路径在 Service 层解析为绝对路径 → plan 声明但存在耦合缺口。
7. Upload `allowed_upload_roots` 删除后不影响 repository 写入边界 → 正确，plan 有充分证据。

## Findings

### F01-未修复-高-wait_adapter_registry_from_provider_configs 未接收 effective config，相对 workspace_root 会直接失败

- **位置**: Slice 3 Exact changes / Risks: "Relative `workspace/` resolution base"
- **问题类型**: 过度耦合 / 不可直接实施
- **当前写法**: plan 要求 Slice 3 更新 `_effective_tool_provider_config` 把相对 `"workspace/"` 解析为绝对路径后再传给 provider。但 `_fins_wait_adapter_registry_from_provider_configs` 当前直接从 raw `provider_configs` 读取 `workspace_root`，不经过 `_effective_tool_provider_config`。
- **反例/失败场景**: packaged `workspace_root: "workspace/"` 后，`_fins_wait_adapter_registry_from_provider_configs` 调用 `_fins_workspace_root_from_provider_config`，该函数要求 `workspace_root` 为非空绝对路径。相对路径 `"workspace/"` 会直接抛出 `ValueError("Fins awaiting provider ... config.workspace_root must be absolute")`，Host assembly 整体失败。
- **为什么有问题**: plan 只描述了 discovery flow 中的 effective config 路径，但遗漏了 wait adapter 构造使用 raw config 的并行路径。两条路径读取同一 `provider_configs`，但只有 discovery path 获得 relative → absolute 转换。implementation agent 如果只按 plan 的 Slice 3 修改 `_effective_tool_provider_config` 和 discovery 调用链，wait adapter 路径会继续失败。
- **直接证据**:
  - `dayu/service/host_assembly.py:1409` `_fins_wait_adapter_registry_from_provider_configs` 直接遍历 `provider_configs`，调用 `_fins_workspace_root_from_provider_config(provider_config)`。
  - `dayu/service/host_assembly.py:1477` `_fins_workspace_root_from_provider_config` 要求 `value` 为非空字符串且 `is_absolute()`。
  - plan Slice 3 "Exact changes" 只提到更新 `_effective_tool_provider_config` 和 wait adapter tests，未说明 `_fins_wait_adapter_registry_from_provider_configs` 如何获得 effective config。
- **影响**: implementation agent 按 plan 执行后，Fins await 系列 provider 的 wait adapter 构造会在 packaged 默认配置下直接失败。Slices 4/5 的 provider 测试可能通过（因为直接传入绝对 workspace_root），但 Service assembly 集成测试会失败。
- **建议改法和验证点**:
  1. plan Slice 3 必须明确：`_fins_wait_adapter_registry_from_provider_configs` 要么接收 effective configs（即经过 `_effective_tool_provider_config` 处理后的 configs），要么在内部复用同样的 relative → absolute 解析逻辑。
  2. 最简方案：让 `_fins_wait_adapter_registry_from_provider_configs` 接收 `effective_provider_configs` 参数，调用方传入 `_effective_tool_provider_config` 处理后的 configs。
  3. 验证点：test 断言 packaged `"workspace/"` 在 wait adapter 构造路径下也能正确解析为绝对路径。
- **修复风险（低/中/高）**: 低。只需在 Slice 3 中让 wait adapter 函数接收 effective configs 或复用同一解析逻辑。
- **严重程度（低/中/高/严重）**: 高。这是一个确定性失败路径，不是边界条件。

---

### F02-未修复-中-相对 workspace_root 解析语义未收敛，_resolve_project_path 语义存疑

- **位置**: Slice 3 "Exact changes" 第 5 点 / Risks: "Relative `workspace/` resolution base"
- **问题类型**: open question 未收敛
- **当前写法**: plan 说 "if relative, resolve against Service request/runtime `workspace_root` using `_resolve_project_path`-equivalent semantics"，并在 Risks 中承认 "Implementation owner must verify whether `workspace/` resolves to `<project_root>/workspace` or should resolve to the effective Dayu workspace root."
- **反例/失败场景**: 如果 `_resolve_project_path` 的语义是"相对路径相对于 project root 解析"，那么 `"workspace/"` 会变成 `<project_root>/workspace`。但如果当前代码中 Fins workspace root 就是 project root 本身（即 `workspace_root` 参数的含义就是 Fins 存储根目录），那么解析出的 `<project_root>/workspace` 会指向一个不存在的子目录，导致 Fins runtime 初始化失败或指向错误位置。
- **为什么有问题**: plan 把关键解析语义作为 open question 留给 implementation owner，但这是一个会影响 packaged 默认配置是否能正常工作的核心决策。如果 implementation agent 猜错语义，所有 Fins provider 都会指向错误的 workspace。
- **直接证据**:
  - `dayu/service/host_assembly.py:620` 当前 `db_path=_resolve_project_path(request.workspace_root, host_runtime.sqlite.path)` 表明 `_resolve_project_path` 把相对路径相对于 `request.workspace_root` 解析。
  - `dayu/config/tool_discovery.json` 当前 Fins `workspace_root` 为 `null`，`_effective_tool_provider_config` 在 `None` 时注入 `workspace_root.expanduser().resolve(strict=False)`，即直接用 runtime workspace root 作为 Fins workspace root。
  - plan 改为 `"workspace/"` 后，语义从"直接用 runtime workspace root"变为"runtime workspace root 下的 workspace 子目录"，这是一个行为变化。
- **影响**: 如果解析语义不正确，Fins provider 会指向错误的 workspace 目录，所有财报读取/上传功能失败。
- **建议改法和验证点**:
  1. plan 应在进入 implementation 前收敛这个 open question，而不是留给 implementation owner。
  2. 需要明确：`"workspace/"` 应该解析为 `<runtime_workspace_root>/workspace` 还是 `<runtime_workspace_root>`。如果是后者，packaged 默认值应该直接用一个 sentinel（如 `"."`）或保留 `null` 但改变 effective config 的 null 处理逻辑。
  3. 验证点：明确的解析结果与 Fins 存储目录布局一致。
- **修复风险（低/中/高）**: 中。需要确认 Fins workspace 目录布局约定。
- **严重程度（低/中/高/严重）**: 中。当前 `null` 默认值在 effective config 中被 runtime workspace root 替换，如果改为 `"workspace/"` 但解析语义不对，行为会退化。

---

### F03-未修复-中-upload 默认注册后 scene tool exposure 缺乏具体验证步骤

- **位置**: Risks / Open Questions: "Product / UX owner"
- **问题类型**: 测试缺口
- **当前写法**: plan 承认 "If packaged `financial-upload-tools` now registers by default, scenes still decide selected tools. Product owner should confirm default scenes do not expose upload where not intended." 但只作为 residual risk 记录，没有在 implementation slices 中安排验证步骤。
- **反例/失败场景**: 当前 packaged config 中 `financial-upload-tools` 因 `allowed_upload_roots: []` 返回空工具集，upload 工具实际上不会进入 ToolBundle。删除 allowlist 后，upload 工具默认注册。如果某个 scene 的 tool_selection 没有显式排除 upload tool，LLM 会看到并可能调用上传工具。
- **为什么有问题**: 这是用户可见行为变化。plan 在 Risks 中提到但没有在 implementation 中安排验证，可能导致 "plan accepted → implementation → review 才发现 scene exposure 问题" 的返工。
- **直接证据**:
  - `dayu/fins/tools/upload_provider.py:42` 当前 `if not allowed_upload_roots: return ... definitions=()` 意味着 upload 工具默认不注册。
  - plan Slice 5 删除此逻辑后，upload provider 会始终注册 `start_fins_upload`。
  - plan 没有列出需要检查的 scene manifests 或验证命令。
- **影响**: 可能在 review 阶段才发现 scene tool exposure 问题，导致 implementation 返工。
- **建议改法和验证点**:
  1. plan Slice 5 或 Slice 8 应包含验证步骤：列出所有 scene manifests，确认 `financial-upload-tools` 的工具是否在预期 scene 的 tool_selection 中。
  2. 如果存在非预期暴露，在 Slice 1 或 Slice 5 中调整 scene tool_selection。
- **修复风险（低/中/高）**: 低。只需在 plan 中添加验证步骤。
- **严重程度（低/中/高/严重）**: 中。行为变化可被发现，但若不在 plan 中安排，implementation agent 可能遗漏。

---

## Open Questions

1. **`_resolve_project_path` 语义确认**（见 F02）：`"workspace/"` 是解析为 `<runtime_workspace_root>/workspace` 还是 `<runtime_workspace_root>`？这个决策直接影响 packaged 默认配置是否正确。
2. **Doc provider `allowed_paths` 为空时的 fail-fast 行为**：当前 doc provider 在 `allowed_paths` 为空时返回空 definitions（fail closed），不抛异常。plan 选择 `enabled=false` 是正确保守方案，但如果未来有人在 workspace overlay 中 `enabled=true` 但不设 `allowed_paths`，会触发 ToolsDiscovery fail fast。这个行为是否需要在 doc provider 自身中 fail fast with message，还是依赖 ToolsDiscovery 通用报错即可？

## Residual Risks

1. **Upload local file read authorization**（plan 已记录）：未来 Host / policy 设计。无 owner，但 plan 正确标记为 deferred。
2. **Relative `workspace/` 与 Fins storage layout 的长期一致性**：如果 Fins workspace 目录布局变化，Service 层的解析逻辑需要同步更新。建议在 Fins README 中明确约定。
3. **Packaged config 与 provider dataclass defaults drift**：plan Slice 6 通过测试 assert packaged defaults 来降低 drift 风险，但长期仍需维护纪律。

## Plan Review Conclusion

**Verdict**: `pass-with-findings`

**Blocking findings**: 1 (F01)

**Non-blocking findings**: 2 (F02, F03)

**可进入 plan accepted/fix gate 的条件**：

1. **必须修复 F01**：plan Slice 3 必须明确 `_fins_wait_adapter_registry_from_provider_configs` 如何获得 effective configs（接收 effective configs 参数，或在内部复用 relative → absolute 解析逻辑），并要求 implementation agent 在该 slice 中一并修改。
2. **建议修复 F02**：plan 应在 Risks 中将 `_resolve_project_path` 语义从 "implementation owner must verify" 提升为 "plan must confirm before implementation"，或在 plan 中直接明确解析语义。
3. **建议修复 F03**：plan Slice 5 或 Slice 8 应添加 scene tool exposure 验证步骤。

修复 F01 后，plan 整体 code-generation-ready 程度足够，implementation agent 可以按 slices 顺序执行。
