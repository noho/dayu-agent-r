# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-awaiting-poller-review-mimo.md
- Included scope: dayu/service/host_assembly.py (unstaged: `with_entrypoint_wait_poller_policy`, `_scene_selects_fins_awaiting_tools`), dayu/service/entrypoint_runtime.py (unstaged: `prepare_entrypoint_runtime` poller wiring), tests/service/test_host_assembly.py, tests/service/test_entrypoint_runtime_interactive_path.py, tests/service/test_entrypoint_runtime_prompt_path.py, dayu/service/README.md, dayu/README.md, tests/README.md
- Excluded scope: 本次 branch 中其它不相关改动（FMP resolver、scene context、tool trace、runtime display 等）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 review 重点的逐项证据审查结论：

### 1. Root cause 成立

**证据链**：`dayu/host/wait_adapter.py:331` 定义 `WaitPollerRuntimePolicy(enabled=True)`，`dayu/host/README.md:66` 明确 "`OpenHostOptions.wait_poller_policy=None` 时不启动 production wait poller"。Fins awaiting tool 返回 `ToolAwaitingOutcome` 后 Host 将 Run 推入 `WAITING`，需要 poller 调用 `resolve_wait` 才能恢复。之前 CLI interactive 的 `prepare_entrypoint_runtime` 直接将 `request.assembly_overrides`（其 `wait_poller_policy=None`）传入 `compose_open_host_options`，导致 `OpenHostOptions.wait_poller_policy=None`，poller 未启动，`WAITING` Run 永不恢复。

**结论**：root cause 成立，且与 `docs/host/design.md:1195-1220` 的 `resolve_wait` 设计一致。

### 2. 修复符合设计真源

- `docs/host/design.md:790` 明确 "wait poller adapter / supervisor（P10.5 不要求实现生产后台 loop）" 属于 background runtime supervisor。
- `docs/host/design.md:1219-1220` 明确 "production poller 可由 `open_host` 可选启动…它仍只是在拿到外部结果后调用同一个 `resolve_wait(...)`"。
- `dayu/host/README.md:66` 明确 "`OpenHostOptions.wait_poller_policy=None` 时不启动 production wait poller；传入启用的 policy 时，`HostToolingOptions.wait_poll_adapter_registry` 必须同时提供"。

修复在 Service assembly 层补齐 policy，不改 Host 默认 no-poller contract，不直接通知 Host，符合设计约束。

### 3. `with_entrypoint_wait_poller_policy` 实现审查

- **位置**：`dayu/service/host_assembly.py:267-290`，与同模块的 `_fins_awaiting_registry_inputs_from_provider_configs` 等 Fins awaiting helper 同层，位置正确。
- **类型/docstring**：完整中文 docstring，参数、返回值、异常齐全，无 `Any`/`object`。
- **无反向依赖**：只依赖同模块内部 helper `_scene_selects_fins_awaiting_tools` 和 `WaitPollerRuntimePolicy`（Host public contract），不反向 import Host 内部。
- **无 CLI scene 魔法分支**：判断逻辑基于 `PreparedSceneInputs.tool_selection.tool_names` 与 `ServiceDiscoveredTools.effective_provider_configs` 的实际交集，不硬编码 scene id。
- **尊重显式 override**：`if overrides.wait_poller_policy is not None: return overrides`（行 283），调用方已显式提供时不覆盖。
- **`_scene_selects_fins_awaiting_tools`**（行 2016-2044）：复用已有 `_fins_awaiting_registry_inputs_from_provider_configs`，`tool_names=None`（全量）时返回 `True`，`tool_names` 为空集时返回 `False`，有交集时返回 `True`。逻辑正确。

### 4. Awaiting tools 判断准确性

`_scene_selects_fins_awaiting_tools` 的判断路径：
1. 从 `discovered_tools.effective_provider_configs` 中识别启用的 Fins awaiting provider（复用 `_fins_awaiting_registry_inputs_from_provider_configs`）。
2. 与 `discovered_tools.tool_bundle.definitions` 取交集确认工具实际存在。
3. 与 `scene_inputs.tool_selection.tool_names` 取交集确认 scene 实际选择。
4. `tool_names=None`（全量选择）时只要有 Fins awaiting 工具就返回 `True`。

prompt scene 的 `tool_selection.tool_names` 不包含 Fins awaiting 工具 → 返回 `False` → poller 不启用。符合预期。

### 5. Interactive 与 session resume 共享 prepare path

- `dayu/cli/commands/interactive.py:290`：`runtime = await prepare_entrypoint_runtime(EntrypointRuntimeRequest(..., scene_id=scenario))` — interactive 入口。
- `dayu/cli/commands/session.py:211`：`return await prepare_entrypoint_runtime(EntrypointRuntimeRequest(..., scene_id=CLI_PROMPT_SCENARIO))` — session resume prompt 入口。
- `dayu/cli/commands/interactive.py:253`：`_prepare_interactive_existing_session_execution` 调用 `prepare_entrypoint_runtime`，scene_id 为 `CLI_INTERACTIVE_SCENARIO` — session resume interactive 入口。

三条路径都经过 `prepare_entrypoint_runtime` → `with_entrypoint_wait_poller_policy`，统一获得 poller 补齐。session resume prompt 走 `CLI_PROMPT_SCENARIO`，其 scene 不选择 Fins awaiting 工具，poller 不启用。session resume interactive 走 `CLI_INTERACTIVE_SCENARIO`，与 `dayu-cli interactive` 同一 scene，poller 正确启用。

### 6. 测试覆盖

| 路径 | 测试文件 | 断言 |
|------|----------|------|
| interactive poller enabled | `test_entrypoint_runtime_interactive_path.py:243-248` | `wait_poller_policy is not None`, `enabled`, `wait_poll_adapter_registry is not None` |
| prompt no-poller | `test_entrypoint_runtime_prompt_path.py:244` | `wait_poller_policy is None` |
| helper: Fins awaiting → poller | `test_host_assembly.py:335-378` | `overrides.wait_poller_policy is None`, `updated.wait_poller_policy is not None`, `enabled` |
| helper: prompt → no-poller | `test_host_assembly.py:381-426` | `updated is overrides`, `wait_poller_policy is None` |

README 更新：
- `dayu/service/README.md:24`：准确描述 `entrypoint_runtime` 的 poller 自动补齐行为。
- `dayu/README.md:100`：准确描述 product entrypoint helper 的 poller 补齐。
- `tests/README.md:143-145`：准确更新 host assembly 和 entrypoint runtime 的覆盖描述。

### 7. Adversarial failure pass

- **显式 override 丢失**：`with_entrypoint_wait_poller_policy` 首先检查 `overrides.wait_poller_policy is not None`，显式值不会被覆盖。
- **无 Fins provider 时误启用**：`_fins_awaiting_registry_inputs_from_provider_configs` 在无启用的 Fins awaiting provider 时返回 `None` → `_scene_selects_fins_awaiting_tools` 返回 `False`。
- **tool_bundle 为空时**：`available_tool_names` 为空 frozenset → `registry_inputs` 为 `None` → 返回 `False`。
- **Host 默认 contract 被改变**：`prepare_entrypoint_runtime` 只在 `with_entrypoint_wait_poller_policy` 返回非 None 时修改 overrides；Host 的 `OpenHostOptions.wait_poller_policy` 默认值仍为 `None`。

## Open Questions

无。

## Residual Risk

- `with_entrypoint_wait_poller_policy` 的 "显式 override 保持" 路径（`overrides.wait_poller_policy is not None`）缺少直接单元测试覆盖。当前测试只验证 `overrides.wait_poller_policy is None` 时的自动补齐和 `updated is overrides`（prompt scene）的 identity 返回。若需更严格，可补充：构造 `overrides=ServiceAssemblyOverrides(wait_poller_policy=WaitPollerRuntimePolicy(enabled=False))` 并验证 `updated is overrides` 且 `enabled=False` 不被覆盖。
- session resume interactive 路径的 poller 集成测试依赖 `test_interactive_command.py` 中的 mock，未在真实 Host + poller 端到端验证。当前覆盖层级合理，但若后续 poller 配置逻辑变更，需关注集成层。
