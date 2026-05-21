# Code Review

## Scope

- Mode: role-scoped code review handoff
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice5-code-review-mimo-20260521.md`
- Included scope:
  - `utils/smoke_host_public_multiturn.py`
  - `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - `tests/host/test_public_compact_smoke.py`
  - `README.md`
  - `tests/README.md`
  - `docs/host/implementation-control.md`
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

### 1-未修复-低-`_find_smoke_tool` 依赖模块级全局可变状态作为 fallback

- **入口/函数**: `_find_smoke_tool(tool_bundle)` (line 1236)
- **文件(行号)**: `utils/smoke_host_public_multiturn.py:1244-1247`
- **输入场景**: `effective_tool_bundle` 中没有 `SmokeFactTool` callable 的工具定义时触发 fallback
- **实际分支**: line 1247 `return _DISCOVERED_SMOKE_TOOL` — 读取模块级全局变量
- **预期行为**: `_find_smoke_tool` 只从传入的 `tool_bundle` 中查找，或显式返回 `None`
- **实际行为**: 若 bundle 中没找到，函数 fallback 到模块级全局 `_DISCOVERED_SMOKE_TOOL`，该全局由 `discover_smoke_tools()` provider 函数在被 `ToolsDiscovery` 调用时通过 `global` 语句设置
- **直接证据**: line 324 `_DISCOVERED_SMOKE_TOOL: SmokeFactTool | None = None`，line 341-342 `global _DISCOVERED_SMOKE_TOOL; _DISCOVERED_SMOKE_TOOL = SmokeFactTool()`，line 1247 `return _DISCOVERED_SMOKE_TOOL`
- **影响**: 当前正常流程不会触发此 fallback（`discover_smoke_tools()` 设置全局的同时也把实例放入 definitions），但该 fallback 创建了隐式状态耦合：函数行为依赖于是否曾调用过 `discover_smoke_tools()`，而非仅依赖传入参数。在测试或多次调用场景下可能返回过期实例
- **建议改法和验证点**: 删除 fallback，`_find_smoke_tool` 只在 bundle definitions 中查找，找不到时返回 `None`；smoke tool 观测功能应由 bundle 内 tool callable 自身维护，不依赖全局状态
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-`discover_smoke_tools` docstring 描述与实际行为不一致

- **入口/函数**: `discover_smoke_tools(spec)` (line 327)
- **文件(行号)**: `utils/smoke_host_public_multiturn.py:327-353`
- **输入场景**: 阅读 docstring 理解函数调用条件
- **实际分支**: docstring 声称"该函数不会被脚本默认注入"
- **预期行为**: docstring 应准确描述该函数何时被调用
- **实际行为**: 该函数是 `ToolsDiscovery` 的 provider callable；当 workspace `tool_discovery.json` 配置了 `utils.smoke_host_public_multiturn:discover_smoke_tools` 且 `enabled=True` 时，`ToolsDiscovery` 会调用它。docstring 中"不会被脚本默认注入"的表述模糊，暗示脚本内部有注入逻辑，但实际上脚本不做任何注入，provider 调用完全由 `ToolsDiscovery` 驱动
- **直接证据**: line 333-334 docstring "该函数不会被脚本默认注入；只有当 workspace config 显式配置..."，而实际调用链为 `_tool_discovery_specs()` -> `ToolsDiscovery().discover()` -> provider callable
- **影响**: 不影响运行时行为，但对维护者理解调用链有轻微误导
- **建议改法和验证点**: 改为"该函数作为 ToolsDiscovery provider callable；只有当 workspace config 显式启用对应 provider spec 时才会被 ToolsDiscovery 调用"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Review Criteria Verification

### 1. smoke 默认路径是否真正使用 runtime location resolver + ConfigLoader + ToolsDiscovery + ScenePrepare + runtime assembly helper + Engine provider extension helper

**通过**。`_prepare_runtime_assembly()` (line 529-633) 完整串联：
- `resolve_runtime_locations()` (line 537)
- `ConfigLoader().load()` (line 541)
- `ToolsDiscovery().discover()` (line 553)
- `prepare_scene()` (line 560)
- `select_runner_option_hint()` (lines 575, 582)
- `merge_agent_policy_config()` (line 597)
- `provider_request_extension_from_json()` (line 1034)

### 2. 是否删除/废弃 manual / old hardcoded assembly

**通过**。脚本无 `--assembly-mode` 参数，无 DeepSeek 专用 runner 硬编码，无旧 context budget 字段，无 prompt asset fallback，无脚本内 `ToolBundle` mock 注入。所有配置来自 `ConfigLoader` typed view。

### 3. scene tool selection 是否只在 discovered bundle 内选择子集

**通过**。`prepare_scene()` 接收 `SceneToolCatalog.from_tool_bundle(effective_tool_bundle)` (line 569-571)，`effective_tool_bundle` 来自 `ToolsDiscovery().discover()` 输出。`_compose_submit_followup_request()` 只传 `tool_names` (line 786)，不传 raw `ToolBundle`。

### 4. diagnostics 是否在 Host 调用前输出关键字段和 suggested adapter/helper function names

**通过**。`_print_assembly_diagnostics()` (line 1455-1517) 输出 config overlay、prompt root、scene manifest root、host runtime id、execution profile id、model id + source、runner hint id + source、lane name、tool provider reports、tool selection、policy refs、agent policy sources、provider extension status、suggested helper names。

### 5. unknown override / unknown tool / unknown provider extension / disabled provider 是否 fail fast

**通过**。
- unknown host runtime: `_select_host_runtime_id()` line 811 raises `RuntimeAssemblySelectionError`
- unknown execution profile: `_select_execution_profile_id()` line 833 raises `RuntimeAssemblySelectionError`
- unknown provider extension: `provider_request_extension_from_json()` fail-closed
- disabled provider / no matching tools: `ScenePrepareError("tool_tags_any matched no tools")` — 由 `test_runtime_assembly_fails_before_host_when_tools_not_discovered` 覆盖

### 6. public Host usage 是否只走 open_host(options) 和 Host handle

**通过**。line 469 `async with open_host(assembly.options) as host:`，后续只调用 `host.ensure_session()`、`host.submit_followup()`、`host.watch_session_events()`、`host.get_session()`。

### 7. test_public_compact_smoke.py 的 context window fix 是否是测试 setup 修正

**通过**。`_SOFT_CONTEXT_WINDOW_SIZE` 从 360 调到 2400，新增 `_SOFT_THRESHOLD_TOKENS = 70`。改动只影响测试 setup 中 opener 内部 `HostCommandHandleOptions` validation 的 input budget 可用空间，不改变 Host public contract、compact 触发语义或 production validation。root cause 是 P12.1 ratio-first context budget 改动后旧小 context window setup 不再满足 command options validation 的 minimum protection 约束。

### 8. README 是否只同步用户可见当前事实

**通过**。`README.md` section 5.1 准确描述 smoke 脚本的 runtime assembly 路径、fail-fast 行为和 diagnostics 输出。`tests/README.md` 更新了 runtime test 分层说明。

### 9. strict typing / docstring / pyright / no Any/object

**通过**。pyright 0 errors, 0 warnings, 0 informations。所有 dataclass 字段有类型注解，所有函数有完整中文 docstring（参数、返回值、异常）。无 `Any`、`object` 使用。

## Open Questions

无。

## Residual Risk

- 默认包内 `tool_discovery.json` 的 `financial-tools` provider 为 disabled，真实 smoke 运行会在 Host 调用前 fail fast。需要 workspace overlay 启用 provider 后才能进入真实 Host 调用阶段。
- `_DISCOVERED_SMOKE_TOOL` 全局状态在进程生命周期内持久化，若多次调用 `_prepare_runtime_assembly()` 且 provider 配置变化，可能返回过期实例（当前 smoke 脚本单次运行，风险低）。

## Tests Run and Results

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q` | 8 passed |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 59 passed |
| `python utils/smoke_host_public_multiturn.py --help` | 通过，退出码 0 |
| `python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |

## Verdict

**PASS_WITH_FINDINGS**

两个低严重程度的 maintainability findings，不阻塞 merge。核心 review criteria 全部通过：smoke 脚本完整使用 runtime assembly 路径、手动硬编码已删除、scene tool selection 只在 discovered bundle 内选择、diagnostics 完整输出、unknown/disabled fail fast、public Host usage 正确、compact smoke fix 是测试 setup 修正、README 同步事实、pyright 0 errors。
