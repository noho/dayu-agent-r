# WU-TOOLS-01-F03-R4 Slice 1 Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `main` (accepted plan commit `fe212365`)
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-ds.md`
- Review agent: AgentDS
- Review date: 2026-06-21
- Included scope: Slice 1 — Packaged schema and generic provider spec cleanup
- Excluded scope: Slice 2-7 (Fins provider cleanup, upload callable, scene manifest, Doc provider fail-fast, docs, final validation)

**Reviewed files:**

Production/config:
- `dayu/config/tool_discovery.json`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/tools_discovery.py`
- `dayu/service/host_assembly.py`

Tests/utils updated for signature fallout:
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `utils/diagnose_web_access.py`

**Parallel review coverage:** 无。本 review 由单一 AgentDS 执行全链路逐行走读。

## Design Truth Alignment

已确认实现与以下设计真源对齐：

- `docs/host/design.md`：Host 不做工具发现，不读取 `tool_discovery.json`，不 import Fins/Doc/Web provider。实现正确地将所有变更限制在 `dayu.runtime`（ConfigLoader / ToolsDiscovery）和 `dayu.service`（Service assembly）层，未触及 Host / Engine 边界。
- `docs/engine/design.md`：Engine 不读取配置文件，`tool_schemas` 是本次 run 的模型可见工具唯一输入快照。实现不改变 Engine public contract。
- `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`：Slice 1 的 exact changes、allowed files、non-goals 和 completion signal 均已满足。

## Implementation Validation

重新运行 AgentCodex 报告的验证命令，结果一致：

```text
pytest tests/runtime/test_config_loader.py -q                              → 41 passed
pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q → 19 passed
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q → 54 passed
pytest tests/tools/test_combined_tools_acceptance.py -q                      → 8 passed
```

全部 122 个测试通过，仅有 3 个 upstream `edgar` deprecation warnings（与本次变更无关）。

```text
pyright dayu tests utils → 0 errors, 0 warnings, 0 informations
```

类型检查通过，无新增或扩散错误。

## Findings

### DS-F01-NonBlocking-Medium-有效 Fins workspace root 解析错误边界缺少直接测试

- **入口/函数**: `_effective_fins_workspace_root_config_value()` at `dayu/service/host_assembly.py:970-1012`
- **文件(行号)**: `dayu/service/host_assembly.py:970-1012`
- **输入场景**: Fins provider 的 `config.workspace_root` 值为非字符串 JSON 类型（如数字、数组、bool），或非空但全空白字符串，或相对路径字符串但调用方未提供 `workspace_root=None`。
- **实际分支**: 第 993 行 `isinstance(configured_workspace_root, str)` 为 `False` → `ValueError`；第 1000 行 `stripped_workspace_root == ""` → `ValueError`；第 1007 行 `workspace_root is None` → `ValueError`。
- **预期行为**: 三条错误路径均应在 Service assembly 阶段 fail fast，且错误消息精确指明 provider id 和缺失条件。
- **实际行为**: 错误分支逻辑正确（已逐行走读确认），但**没有直接测试覆盖这三条 `ValueError` 抛出路径**。现有测试 `test_fins_tool_discovery_spec_resolves_relative_workspace_root` 和 `test_discover_service_tools_carries_effective_fins_config_into_compose` 只覆盖了正常的相对路径解析和 absolute path 保留。
- **直接证据**:
  - `tests/service/test_host_assembly.py` 中 `test_fins_tool_discovery_spec_resolves_relative_workspace_root` 只覆盖 `workspace_root="workspace/"` 正常解析。
  - 没有测试传入 `config.workspace_root=123`（非字符串）、`config.workspace_root=""` 或 `config.workspace_root="   "`（空/全空白）、以及 `config.workspace_root="workspace/"` 但 `runtime_workspace=None` 时的 `ValueError` 抛出。
- **影响**: 三条错误路径只通过代码阅读验证，未被自动化测试锁定。未来重构此函数时，可能意外修改错误条件表达或错误消息格式而不被捕获。
- **建议改法和验证点**: 在 `tests/service/test_host_assembly.py` 中新增三个 parametrized 或独立测试：
  1. `test_effective_fins_workspace_root_rejects_non_string_config`：传入 `config={"workspace_root": 123}`，断言 `ValueError` 且消息包含 provider id 和 `"must be a string"`。
  2. `test_effective_fins_workspace_root_rejects_empty_or_blank_config`：传入 `config={"workspace_root": ""}` 和 `config={"workspace_root": "   "}`，断言 `ValueError` 且消息包含 `"must be non-empty"`。
  3. `test_effective_fins_workspace_root_rejects_relative_without_runtime_root`：传入 `config={"workspace_root": "workspace/"}` 且 `workspace_root=None`，断言 `ValueError` 且消息包含 `"requires runtime workspace_root"`。
- **修复风险（低）**: 仅新增测试，不改生产代码。
- **严重程度（中）**: 错误路径虽然是防御性代码（正常配置不会触发），但函数文档明确声明了这些 `raises ValueError` 契约，应有测试锁定。

### DS-F02-NonBlocking-Low-`_effective_tool_provider_config` 对 Fins provider 返回 unchanged config 的条件语义不精确

- **入口/函数**: `_effective_tool_provider_config()` at `dayu/service/host_assembly.py:943-967`
- **文件(行号)**: `dayu/service/host_assembly.py:963-964`
- **输入场景**: 当 Fins provider 的 `config.workspace_root` 为 `None`（JSON `null`），且调用方也未提供 runtime `workspace_root=None` 时。
- **实际分支**: 第 989 行 `configured_workspace_root is None` → `workspace_root is None` → `return None`；第 963 行 `effective_workspace_root is None` → `return provider_config.config`（保留原始 `None` 值）。
- **预期行为**: 保留原始 config，让后续 provider / wait adapter 在消费时自行 fail fast。这符合 plan 中的决策："Fins provider with `None` or missing `workspace_root` ... leave for fail fast"。
- **实际行为**: 行为正确，但语义不够精确：`workspace_root: null` 的 Fins provider 进入 `discover_service_tools` 后会因为路径为空字符串（或 `None`）在 provider 内部 fail。当前 packaged config 已经全部改为 `workspace_root: "workspace/"`，所以这个路径只在 workspace overlay 未提供 `workspace_root` 时才触发。
- **直接证据**: `dayu/service/host_assembly.py:960-964`。Packaged config `dayu/config/tool_discovery.json` 中所有 Fins provider 的 `workspace_root` 均为 `"workspace/"` 字符串，不再为 `null`。
- **影响**: 低影响。当前 packaged config 不再触发此路径，仅在 workspace overlay 覆盖 `workspace_root` 为 `null` 时才可能触发。但这是设计意图内行为（让 provider 自身 fail fast）。
- **建议改法和验证点**: 如果后续计划要求也对 `None` workspace root 在 Service assembly 阶段 fail fast（而非留给 provider），应在对应 slice 中修改此逻辑并补测试。当前 Slice 1 无需变更。
- **修复风险（低）**: 无生产代码修改需要。
- **严重程度（低）**: 可接受的语义模糊，非缺陷。

### DS-F03-NonBlocking-Low-Packaged `financial-upload-tools.enabled=false` 是临时桥接，存在状态漂移风险

- **入口/函数**: `dayu/config/tool_discovery.json` 第 45-54 行
- **文件(行号)**: `dayu/config/tool_discovery.json:50`
- **输入场景**: 当前 Slice 1 中 upload provider 的 `allowed_upload_roots` 已从 packaged config 中删除，但 provider 代码 (`dayu/fins/tools/upload_provider.py:40-42`) 仍会在 `allowed_upload_roots` 为空时返回空 `definitions`。因此 `enabled=false` 是防止空 definitions 触发 ToolsDiscovery 新 invariant 的唯一屏障。
- **实际分支**: `enabled=false` → `ToolsDiscovery.discover()` 跳过此 provider（`dayu/runtime/tools_discovery.py:209`）；upload provider 不被调用。
- **预期行为**: Slice 4 将删除 upload provider 内部的 allowlist 逻辑，恢复 `enabled=true` 默认注册。在此之前 `enabled=false` 是正确的临时措施。
- **实际行为**: 行为正确。但这是跨 slice 状态漂移点：如果在 Slice 4 之前有人将 `enabled` 改回 `true`（例如误操作或 workspace overlay），upload provider 会在 discovery 阶段触发 "returned empty tools" 错误。
- **直接证据**:
  - `dayu/config/tool_discovery.json:50`: `"enabled": false`
  - `dayu/fins/tools/upload_provider.py:42`: `if not allowed_upload_roots: return ToolsDiscoveryProviderOutput(..., definitions=())`
  - `dayu/runtime/tools_discovery.py:542-543`: `if not output.definitions: raise ToolsDiscoveryError(...)`
- **影响**: 低影响。当前条件下不会发生，但状态耦合缺少 code-level guard。如果 workspace overlay 重新启用 upload provider，会在运行时 fail fast（这是安全的，不是静默错误），但错误消息是通用的 "provider returned empty tools"，不是 "upload provider still requires allowed_upload_roots cleanup"。
- **建议改法和验证点**: 在 Slice 4 的 plan review 中将此作为状态一致性检查项。当前不需代码修改。如果担心，可在 upload provider 内临时添加注释说明 `allowed_upload_roots` 空列表会导致空输出、需 `enabled=false` 桥接。
- **修复风险（低）**: 无需立即修复。
- **严重程度（低）**: 设计意图内的已知临时状态，有后续 slice 承接。风险仅在于 Slice 4 被推迟或遗忘时，未来维护者可能不理解为何 upload 被禁用。

### DS-F04-NonBlocking-Low-`_effective_tool_provider_config` 中 `dict()` 复制可能被误读为不影响 frozen dataclass

- **入口/函数**: `assemble_effective_tool_provider_configs()` at `dayu/service/host_assembly.py:363-386`
- **文件(行号)**: `dayu/service/host_assembly.py:382-385`
- **输入场景**: `_effective_tool_provider_config()` 返回的 effective config 与原始 `provider_config.config` 不同时。
- **实际分支**: 第 382 行 `if effective_config == provider_config.config` 为 `False` → 第 385 行 `replace(provider_config, config=effective_config)` 产生新的 frozen dataclass 实例。
- **预期行为**: 不修改原始 `provider_config`（它是 frozen dataclass，不可变），通过 `replace()` 创建新实例。
- **实际行为**: 正确。`dict(provider_config.config)` 在第 965 行做浅复制，因为 `provider_config.config` 是 `Mapping[str, JsonValue]`，值类型为 `JsonValue`（不可变），浅复制安全。`replace()` 创建的是新实例，不影响调用方持有的原始 `provider_config`。
- **直接证据**:
  - `dayu/service/host_assembly.py:385`：`replace(provider_config, config=effective_config)`
  - `dayu/service/host_assembly.py:965`：`effective_config: dict[str, JsonValue] = dict(provider_config.config)`
  - `test_fins_tool_discovery_spec_resolves_relative_workspace_root` 第 1158 行断言 `provider.config["workspace_root"] == "workspace/"` 证明原始 config 未被修改。
- **影响**: 无实际风险，行为正确且被测试锁定。
- **建议改法和验证点**: 无需操作。
- **修复风险**: 不适用。
- **严重程度（低）**: 记录为正面确认，非缺陷。

### DS-F05-NonBlocking-Low-`utils/diagnose_web_access.py` 修改是纯签名 fallout，范围可接受

- **入口/函数**: `_fetch_web_page_definition()` at `utils/diagnose_web_access.py:1366-1372`
- **文件(行号)**: `utils/diagnose_web_access.py:1369`
- **输入场景**: 构造 `ToolsDiscoveryProviderSpec` 时删除 `allow_empty=False` 参数。
- **实际分支**: 单行修改：移除 `allow_empty=False` 关键字参数。
- **预期行为**: `utils/diagnose_web_access.py` 属于分析辅助脚本，不在 `dayu/` 生产代码内，但构造了 `ToolsDiscoveryProviderSpec` 实例。删除 `allow_empty` 字段后，该构造必须同步更新。
- **实际行为**: 修改正确，仅删除 `allow_empty=False` 一行。Web provider 总是返回 `search_web` / `fetch_web_page` 两个工具，从不返回空 definitions，因此原 `allow_empty=False` 只是签名必需参数，非语义必需。
- **直接证据**: `utils/diagnose_web_access.py:1366-1372`，diff 显示仅删除 `allow_empty=False` 一行。
- **影响**: 无影响。修改范围符合 "因 constructor/signature 删除 `allow_empty` 被更新的 tests / utils" 的预期。
- **建议改法和验证点**: 无需操作。Controller 在 plan review 中设定的审查焦点是 "是否只是 ToolDiscoveryProviderSpec signature fallout"，确认成立。
- **修复风险**: 不适用。
- **严重程度（低）**: 正面确认，非缺陷。

## 审查重点逐项回复

### 1. Correctness：删除 `allow_empty` 后一致性

**通过。** ConfigLoader → ToolsDiscovery → Service mapping 三层一致：
- `ToolDiscoveryProviderConfig` 不再包含 `allow_empty` 字段（`config_loader.py:587-590`）
- `_parse_tool_discovery_provider()` required fields 不再包含 `"allow_empty"`，且 unknown fields 校验会拒绝旧 provider record 中的 `allow_empty`（`config_loader.py:2023-2036`）
- `ToolsDiscoveryProviderSpec` 不再包含 `allow_empty`（`tools_discovery.py:95-104`）
- `_validate_provider_output()` 无条件拒绝空 `definitions`（`tools_discovery.py:542-543`）
- `host_assembly.py::_tool_discovery_specs()` 不再映射 `allow_empty`（`host_assembly.py:932-939`）
- 最终空 `ToolBundle(definitions=(), _allow_empty=True)` 仅当没有任何 enabled provider 贡献 definitions 时使用（`tools_discovery.py:262-266`）
- 测试覆盖：`test_tool_discovery_provider_allow_empty_is_rejected` 验证旧字段被拒绝；`test_empty_provider_is_rejected_even_when_other_providers_are_disabled` 验证空输出 fail fast；disabled provider skip 通过现有测试覆盖

**Enabled provider empty definitions 统一 fail fast：通过。**
**Disabled provider 仍可使最终 ToolBundle 为空：通过。**

### 2. Packaged config

**通过。** 确认以下变更：
- `workspace_root=workspace/`：所有 Fins provider 已更新
- OLD limits：`financial-read-tools.config.limits` 和 `doc-tools.config.limits` 已填入
- `doc-tools.enabled=false`：已设置
- `financial-upload-tools.enabled=false`：作为临时桥接（见 DS-F03）
- `include_read_tools` 已删除
- `allowed_upload_roots` 已删除
- `web-tools` 不变（仍 enabled，无 `allow_empty`）
- `ConfigLoader` 测试 (`test_default_runtime_config_files_load_as_typed_views`) 已更新断言验证上述变更

### 3. Service effective config

**通过。** `_effective_fins_workspace_root_config_value()` 实现正确：
- 类型安全：`isinstance(configured_workspace_root, str)` 检查（第 993 行）
- `expanduser()` 处理 `~`（第 1004 行）
- 相对路径通过 `_resolve_project_path()` 解析，复用现有 containment 检查
- 不修改原始 config：`assemble_effective_tool_provider_configs()` 使用 `replace()` 创建新实例（第 385 行）
- 测试验证：`test_fins_tool_discovery_spec_resolves_relative_workspace_root` 断言相对路径被解析，原始 config 未被修改
- 测试验证：`test_discover_service_tools_carries_effective_fins_config_into_compose` 断言 wait adapter 消费 effective config

**是否为 Slice 1 必要依赖：是。** Packaged `workspace_root="workspace/"` 是相对路径，没有 effective resolution 会导致 Fins provider 在 discovery 阶段因相对路径而失败，使 "Service discovery callable" 的 Slice 1 completion signal 无法达成。因此 effective resolution 是 Slice 1 的必要前置，不是 scope overrun。

### 4. Scope ownership：`utils/diagnose_web_access.py`

**可接受。** 修改为纯 signature fallout：仅删除 `allow_empty=False` 一行（见 DS-F05）。`utils/` 下的脚本使用 `ToolsDiscoveryProviderSpec` 公开 API，当该 API 的构造函数签名变化时，caller 必须同步更新。这不构成 scope overrun。

### 5. Tests

**通过。** 122 测试通过，覆盖：
- ConfigLoader 接受新 packaged config + 拒绝旧 `allow_empty` field（`test_tool_discovery_provider_allow_empty_is_rejected`）
- ToolsDiscovery 拒绝空 provider 输出（`test_empty_provider_is_rejected_even_when_other_providers_are_disabled`）
- Service effective workspace resolution（`test_fins_tool_discovery_spec_resolves_relative_workspace_root`）
- Effective config 不修改 original（`assert provider.config["workspace_root"] == "workspace/"`）
- Wait adapter 消费 effective config（`test_discover_service_tools_carries_effective_fins_config_into_compose`）
- Combined acceptance 测试 source_refs 从 6 减为 5（doc-tools disabled）
- `pyright` 0 errors

**缺少的测试覆盖：** `_effective_fins_workspace_root_config_value()` 的三条 `ValueError` 路径（见 DS-F01）。

### 6. AGENTS 约束

**通过。** 逐项检查：
- 中文 docstring：`_effective_fins_workspace_root_config_value()` 有完整中文 docstring（参数、返回值、异常）。其他修改的函数 docstring 已同步更新（`_validate_provider_output` 的 `:raises` 说明已从 "未显式允许时" 改为无条件）。
- 严格类型：无 `Any`/`object` 扩散。`_effective_fins_workspace_root_config_value()` 返回 `str | None`，`_effective_tool_provider_config()` 返回 `Mapping[str, JsonValue]`，类型标注完整。
- 无兼容旧 schema：`allow_empty` 作为 unknown field 被 ConfigLoader 拒绝，不留兼容读取路径。
- README 触发：确认 `dayu/config/` 和 `dayu/service/` 被修改但 README 更新被正确推迟到 Slice 6，与 plan 和 AGENTS 约束一致（"README files were not modified in this slice because the user explicitly forbade README modifications" — Implementation artifact line 72）。
- 无反向依赖：`dayu.runtime` 不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`。`dayu.service/host_assembly.py` 正确 import `dayu.host` 和 `dayu.engine` public contracts（向下依赖）。
- `hasattr`/`getattr` 使用：无新增。
- 无 God object/function/dataclass 扩散。

## Stale Field Grep Summary

```text
dayu/fins/tools/provider.py         — include_read_tools 仍存在（Slice 3 清理）
dayu/fins/tools/upload_provider.py   — allowed_upload_roots 仍存在（Slice 4 清理）
dayu/fins/tools/upload_tools.py      — allowed_upload_roots 仍存在（Slice 4 清理）
dayu/fins/direct_events.py           — allow_empty=False（自有语义，与 provider allow_empty 无关）
dayu/host/llm_compaction.py          — allow_empty（自有语义，与 provider allow_empty 无关）
dayu/contracts/tool_declaration.py   — _allow_empty InitVar（框架内部机制，非 provider 级别）
dayu/runtime/scene_prepare.py        — allow_empty（scene tool_selection 级别，独立语义）
dayu/config/prompts/manifests/*.json — allow_empty（scene tool_selection 级别，独立语义）
tests/ 中旧字段引用                   — 均在 Slice 3/4 范围内测试中，非 production config
```

**结论：** 生产 packaged config (`dayu/config/tool_discovery.json`) 和 ConfigLoader/ToolsDiscovery/Service mapping 层已无 `allow_empty` / `include_read_tools` / `allowed_upload_roots` 引用。残留引用全部属于后续 slice 清理范围、或独立语义（scene `allow_empty`、`ToolBundle._allow_empty` InitVar、compaction `allow_empty`）。

## Open Questions

无。

## Residual Risk

| 风险 | 严重程度 | Owner |
|---|---|---|
| `_effective_fins_workspace_root_config_value()` 三条 ValueError 路径无直接测试 | 中 | WU-TOOLS-01-F03-R4 Slice 7 最终验证时可补；或 deferred 到后续维护 |
| Upload provider `enabled=false` 桥接状态依赖后续 Slice 4 恢复 | 低 | Slice 4 plan review 必须验证此状态一致性 |
| `fins/tools/provider.py` 的 `include_read_tools` 内部逻辑仍存在但不再被 config 使用 | 低 | Slice 3 清理 |
| `fins/tools/upload_provider.py` 的 `allowed_upload_roots` 内部逻辑仍存在但不再被 config 使用 | 低 | Slice 4 清理 |
| Doc provider 仍会在 enabled + empty `allowed_paths` 时返回空 definitions | 低 | Slice 5 清理；当前 packaged `doc-tools.enabled=false` 防止触发 |

## Verdict

**pass-with-findings**

- Blocking findings: **0**
- Non-blocking findings: **3** (DS-F01, DS-F02, DS-F03)
- Positive confirmations (非缺陷): **2** (DS-F04, DS-F05)

### Controller Adjudication Guide

| Finding | 建议裁决 | 理由 |
|---|---|---|
| DS-F01 | accepted → fix in Slice 7 or deferred | 错误路径契约有文档声明但缺测试锁定；可在最终验证 slice 补三个简单测试，或明确 defer 到后续维护 |
| DS-F02 | rejected-with-reason or accepted as-is | 行为符合 plan 设计决策，`None` 保留给 provider fail fast 是有意选择 |
| DS-F03 | accepted → deferred-with-owner (Slice 4) | 临时桥接状态正确，但 Slice 4 plan review 应验证状态一致性 |
| DS-F04 | informational only | 正面确认实现正确 |
| DS-F05 | informational only | 正面确认范围可接受 |

### 可进入 accepted slice commit gate

Slice 1 实现满足所有 correctness、packaged config、Service effective config 和 AGENTS 约束要求。无 blocking findings。122 测试通过，pyright 0 errors。建议在 controller 确认 findings 裁决后进入 accepted slice commit gate，然后推进 Slice 2（Service effective Fins workspace path resolution — 已在 Slice 1 中大部分实现，Slice 2 可能仅需细化和补充测试）。

---

Review 完成于 2026-06-21 07:49:26 CST。
