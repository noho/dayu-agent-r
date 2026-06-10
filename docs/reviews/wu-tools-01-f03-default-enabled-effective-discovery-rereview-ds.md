# Code Review

## Scope

- Mode: current changes (unstaged + staged diffs against HEAD)
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-default-enabled-effective-discovery-rereview-ds.md
- Review date: 2026-06-10
- Focus areas:
  - `dayu/config/tool_discovery.json`: 默认 `enabled=true`
  - `dayu/service/host_assembly.py`: `assemble_effective_tool_provider_configs` / `discover_service_tools` 两阶段分离
  - `dayu/fins/tools/upload_provider.py`: upload 空 allowlist 安全返回空工具集
  - smoke/public smoke 脚本统一走 `ConfigLoader.load -> assemble_effective_tool_provider_configs -> discover_service_tools`
- Verification baseline: 83 focused passed, 209 affected passed, pyright 0, Web smoke passed, git diff --check passed

## Confirmation Points

### 1. discover_service_tools 内部不再 assembly — PASS

**入口/函数**: `discover_service_tools` (host_assembly.py:272)

**证据**:
- `discover_service_tools` 签名改为 `effective_provider_configs: Sequence[ToolDiscoveryProviderConfig]` — 不再接收 `config: RuntimeConfig` 或 `workspace_root`
- 函数体直接 `tuple(effective_provider_configs)` 后传给 `_tool_discovery_specs`，不再调用任何 assembly 逻辑
- `_tool_discovery_specs` (host_assembly.py:797) 签名不再含 `workspace_root` 参数；spec 构造直接使用 `provider_config.config`（已经由调用方装配完成），不再调用 `_effective_tool_provider_config`
- 旧的 `_effective_tool_provider_configs` 私有函数已删除（原 line 856），其逻辑升级为 public `assemble_effective_tool_provider_configs` (host_assembly.py:304)
- 所有调用方（3 个 smoke 脚本 + 3 个测试文件）已更新为两阶段模式：先调 `assemble_effective_tool_provider_configs` 再调 `discover_service_tools`

**结论**: `discover_service_tools` 职责收敛为纯 discovery，不再承担 assembly。分离干净，无残留。

### 2. upload 空 allowlist 不注册 tool 且不绑定 start_fins_upload wait adapter — PASS

**入口/函数**: `upload_provider.discover_tools` (upload_provider.py:25)

**证据**:
- `parse_allowed_upload_roots_config` (upload_provider.py:65) 对 `None` / `[]` 均返回 `()`
- `discover_tools` 在 `allowed_upload_roots` 为空时走 early return（line 42-48），返回 `definitions=()` 且**不调用** `parse_fins_workspace_root_config`，因此不会因缺失 workspace_root 而抛 ValueError
- `_fins_wait_adapter_registry_from_provider_configs` (host_assembly.py:1186) 新增 `available_tool_names: frozenset[str]` 参数，line 1208: `if tool_name not in available_tool_names: continue` — 当 upload provider 返回空 definitions 时，`start_fins_upload` 不在 `available_tool_names` 中，wait adapter 不会被绑定
- 测试覆盖：
  - `test_upload_provider_without_allowed_upload_roots_returns_empty_tools` (test_fins_ingestion_tools.py:305): 参数化覆盖 `{}` / `[]` / `None`，均断言 `result.definitions == ()`
  - `test_tooling_options_skips_wait_adapter_for_missing_awaiting_tool_definition` (test_host_assembly.py:656): upload provider config 存在但 ToolBundle 不含 `start_fins_upload` 时，`wait_adapter_registry is None`

**结论**: 空 allowlist 时 upload provider fail closed，不注册工具、不绑定 wait adapter、不初始化 Fins runtime。实现与测试对齐。

### 3. scene 外工具不泄漏 — PASS

**入口/函数**: `_tooling_options_from_discovery` (host_assembly.py:1149) → `compose_submit_followup_request` (host_assembly.py:437)

**证据**:
- 工具发现返回全量 ToolBundle（含所有 enabled=true 的 provider 输出），但实际工具可用性由 scene manifest 的 `tool_selection` 控制
- `compose_submit_followup_request` 接收 `tool_names: frozenset[str] | None`，由调用方传入 `scene_inputs.tool_selection.tool_names`
- 在 smoke 脚本中，`assembly.scene_inputs.tool_selection.tool_names` 用于每轮 `submit_followup` 的 `tool_names` 参数
- Wait adapter registry 只在 `available_tool_names`（来自 ToolBundle）中存在的 awaiting 工具上绑定，即使 provider config 声明了 Fins awaiting provider，若对应工具不在 ToolBundle 中也不绑定（line 1208）
- 默认 `enabled=true` + `allow_empty=true` + 空配置的 provider（如 doc-tools 的 `allowed_paths=[]`）会返回空工具集，不向 ToolBundle 注入工具
- Fins read/download/preprocess providers 需要 workspace_root；在 `assemble_effective_tool_provider_configs` 阶段若调用方提供 workspace_root 则注入，否则保持 `null`。provider 内部 `parse_fins_workspace_root_config` 对 null 会 fail-fast（ValueError），不会静默产生半初始化工具

**结论**: 工具可见性由 scene manifest 的 `tool_selection` 决定性控制。enabled=true 的 provider 即使返回工具，也不在 scene 未选择时暴露给 LLM。Wait adapter 与 ToolBundle 实际工具名对齐，不存在孤儿绑定。

### 4. docs/tests 同源 — PASS

**入口/函数**: README (dayu/config/README.md) vs 代码实现

**证据**:
- `dayu/config/README.md` line 175: 描述 Fins providers 均为 `enabled=true`，与 `tool_discovery.json` 一致
- README line 175: 描述 "Service 会把运行时 workspace 注入 effective spec，scene manifest 再决定实际选择哪些 Fins tools"，与 `assemble_effective_tool_provider_configs` 行为一致
- README line 184: 描述 upload provider "只有配置非空 `allowed_upload_roots` 时才注册上传工具；为空时返回空工具集并 fail closed"，与 `upload_provider.discover_tools` 行为一致
- README line 186: 描述 doc-tools "默认 `enabled=true` 且 `allowed_paths=[]`...白名单为空时 provider 会 fail closed，返回空工具集合"，与代码一致
- 测试更新同步：
  - `test_host_assembly.py`: 所有直接调用 `discover_service_tools(config, workspace_root=...)` 改为 `assemble_effective_tool_provider_configs(...)` → `discover_service_tools(effective_provider_configs)`
  - `test_combined_tools_acceptance.py`: `_discover_combined_tools` 采用两阶段，`test_combined_discovery_returns_single_bundle_without_reserved_names` 的期望 names 新增 `_FINS_AWAITING_TOOL_NAMES`，source_refs 数量从 3 更新为 6
  - `test_fins_ingestion_tools.py`: `test_upload_provider_requires_allowed_upload_roots` 替换为参数化 `test_upload_provider_without_allowed_upload_roots_returns_empty_tools`
  - `test_smoke_web_ci.py`: assembly_path label 更新为含 `assemble_effective_tool_provider_configs` 步骤
- Smoke 脚本（3 个）全部采用两阶段模式

**结论**: README 描述、代码实现、测试断言三者一致。无文档漂移。

### 5. 类型/分层/AGENTS.md 无问题 — PASS

**入口/函数**: 全模块 import 拓扑

**证据**:
- `dayu.service.host_assembly` 依赖 `dayu.runtime.*`、`dayu.host.*`、`dayu.fins.*` — Service → Runtime/Host/Fins，符合分层架构
- `dayu.fins.tools.upload_provider` 依赖 `dayu.runtime.tools_discovery`、`dayu.fins.service_runtime` — Fins tools → Runtime/Fins service runtime，无反向依赖
- 无 `dayu.runtime` → `dayu.service` / `dayu.host` / `dayu.engine` 反向 import
- 公开 API: `assemble_effective_tool_provider_configs` 返回 `tuple[ToolDiscoveryProviderConfig, ...]`，`discover_service_tools` 接收 `Sequence[ToolDiscoveryProviderConfig]`，类型签名一致
- `_tooling_options_from_discovery` 新增 `available_tool_names: frozenset[str]` 参数，类型明确，调用方（line 1172-1174）从 `tool_bundle.definitions` 构造，无类型丢失
- `ServiceDiscoveredTools.effective_provider_configs` 类型为 `tuple[ToolDiscoveryProviderConfig, ...]`，与 `_tooling_options_from_discovery` 的 `provider_configs` 参数类型匹配
- pyright 0 报错

**结论**: 分层清晰，类型安全，无架构违规。

## Findings

### 1-未修复-中-ConfigLoader deep merge 使 workspace overlay 新增 provider 时默认 provider 仍然参与发现

- **入口/函数**: `ConfigLoader.load` → `_overlay_roots` (config_loader.py:962)
- **文件(行号)**: dayu/runtime/config_loader.py:991-992
- **输入场景**: workspace overlay 的 `tool_discovery.json` 只声明自定义 provider（如 smoke 测试中的 `financial-tools`），不显式禁用包内默认 provider
- **实际分支**: `_overlay_roots` 对 `map_fields`（含 `providers`）执行 `dict(package_map); map_merged.update(workspace_map)` —— 默认 provider 全部保留，workspace 新 key 叠加
- **预期行为**: 调用方可能期望 overlay 只启用显式声明的 provider，但实际所有默认 enabled=true 的 provider 都参与发现
- **实际行为**: 当 `assemble_effective_tool_provider_configs` 被调用且 `workspace_root` 非 None 时，Fins read/download/preprocess providers 会收到注入的 workspace_root，在该路径上初始化 Fins runtime。若该路径不是已有的 Fins 工作区（例如 smoke 临时目录），会创建空的 Fins 目录结构。工具虽然注册到 ToolBundle，但若 scene manifest 不选择这些工具，LLM 不可见
- **直接证据**: config_loader.py:991-992 的 merge 逻辑 + tool_discovery.json 中 6 个 provider 均 `enabled=true`
- **影响**: 非 Fins 场景会多出 read/download/preprocess 工具的 discovery 开销与 Fins runtime 初始化。当前因 `allow_empty=true` 与 scene tool_selection 过滤，不影响正确性，但增加了不必要的初始化工作。若未来某个 Fins provider 的 `DefaultFinsRuntime.create` 对非 Fins 路径有副作用（如写入默认 schema），可能引入意外状态
- **建议改法和验证点**: 考虑在 `assemble_effective_tool_provider_configs` 或 `discover_service_tools` 层增加一个 guard：当 fins provider 的 effective `workspace_root` 解析后路径不存在或不是已有 Fins workspace 时，跳过该 provider（等同 disabled）。或在文档中明确说明 overlay 的 additive merge 语义
- **修复风险（低）**: 只影响 discovery 阶段的行为，不影响 tool 执行语义
- **严重程度（中）**: 当前不导致功能错误，但属于隐式行为，缺少显式 guard。在 Fins workspace 语义更严格时可能升级为 bug

### 2-未修复-低-Fins workspace-bound provider 识别依赖三重字符串匹配

- **入口/函数**: `_is_fins_workspace_bound_provider_config` (host_assembly.py:859) + `_fins_awaiting_tool_name_from_provider_config` (host_assembly.py:1223)
- **文件(行号)**: dayu/service/host_assembly.py:859-875, 1223-1251
- **输入场景**: provider 的 `provider_id`、`import_path`、`source_id` 任一匹配预定义 frozenset 即判定为 Fins provider
- **实际分支**: 三重 OR 匹配（provider_id in set OR import_path in set OR source_id in set）
- **预期行为**: 正确识别 Fins workspace-bound 与 Fins awaiting providers
- **实际行为**: 当前正确。但若新增 Fins provider 或重命名现有 provider id/import_path/source_id，需要同步更新 7 个 frozenset 常量（line 90-123）。缺少编译期或测试期的完整性校验
- **直接证据**: host_assembly.py:90-123 定义了 12 个 frozenset 常量，host_assembly.py:859-875 和 host_assembly.py:1223-1251 分别使用三重 OR 匹配
- **影响**: 维护成本。新增 Fins provider 时容易遗漏常量更新，导致 workspace_root 注入或 wait adapter 绑定静默失效
- **建议改法和验证点**: 不阻塞当前合并。后续可考虑让 provider 自身声明 `needs_workspace_root` 或 `awaiting_tool_name` 契约字段，或通过 `typing.Protocol` 收敛。当前三重匹配已覆盖测试（`test_fins_workspace_bound_provider_detection_boundaries`），但不是结构性方案
- **修复风险（低）**: 纯重构
- **严重程度（低）**: 维护性问题，非功能缺陷

## Open Questions

1. **Fins provider enabled=true + workspace_root 注入对非 Fins 场景的长期影响**：当 smoke 或普通 scene 以任意 `workspace_root` 调用 `assemble_effective_tool_provider_configs` 时，Fins read/download/preprocess providers 会在该路径初始化 Fins runtime。当前 `DefaultFinsRuntime.create` 似乎只是创建目录结构（不要求已有 Fins 数据），但需确认这种行为是否在所有环境下稳定，以及空 Fins workspace 的磁盘占用是否可接受。

2. **upload provider 的 `allow_empty=true` + `allowed_upload_roots=[]` 返回空工具集的语义边界**：当前 `enabled=true, allow_empty=true, config.allowed_upload_roots=[]` 时，upload provider 返回空 `definitions=()` 且 source_ref 仍然发出（含 `ToolBundleSourceRef`）。这是否会触发 `_tooling_options_from_discovery` 的 `not source_refs` 检查（line 1168）？不会——因为 upload provider 确实返回了 source_refs，只是 definitions 为空。ToolBundle 整体非空时（有其他 provider 的工具），`_tooling_options_from_discovery` 正常执行。若 ToolBundle 整体为空（所有 provider 都返回空），则 `_tooling_options_from_discovery` 返回 `None`，是正确的。

## Residual Risk

- **Test gap: 无显式测试覆盖 "workspace overlay 新增 provider + 默认 fins providers enabled=true 同时参与 discovery" 的集成场景**：现有测试通过 `allow_empty=true` 和 scene tool_selection 过滤间接保证了正确性，但没有显式断言 "Fins read/download/preprocess providers 在非 Fins workspace 下被启用且成功返回工具" 或 "这些工具被 scene 排除后不影响行为"。
- **未覆盖的 adversarial 场景：`workspace_root` 参数为相对路径**：`_effective_tool_provider_config` (host_assembly.py:832) 调用了 `workspace_root.expanduser().resolve(strict=False)` 做归一化，但未校验路径是否为绝对路径。若调用方传入相对路径，`resolve()` 会基于 cwd 解析，可能产生非预期路径。在生产路径中，调用方（smoke 脚本、Service）均传入已解析的绝对路径，风险低。
- **未覆盖的 adversarial 场景：`allowed_upload_roots` 数组元素包含重复路径**：`parse_allowed_upload_roots_config` 未对路径去重，可能导致重复 root 进入 `build_fins_upload_tool`。取决于下游实现是否幂等处理。

## Conclusion

**PASS** — 所有 5 个确认点通过验证。未发现 blocking finding。

核心变更的架构意图清晰且执行一致：
1. `discover_service_tools` 职责收敛为纯 discovery
2. `assemble_effective_tool_provider_configs` 承担 assembly 职责
3. upload 空 allowlist 三层安全（不注册工具、不绑定 wait adapter、不初始化 Fins runtime）
4. scene manifest 作为工具可见性真源
5. 所有 smoke/public smoke 脚本统一走两阶段装配路径

两个 findings 均为非阻塞：一个中等的隐式行为风险（ConfigLoader deep merge 语义），一个低的维护性关注（字符串匹配识别 Fins provider）。
