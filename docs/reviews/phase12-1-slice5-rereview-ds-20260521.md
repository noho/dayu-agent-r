# Phase 12.1 Slice 5 Re-Review (AgentDS)

## Scope

- Mode: re-review of controller accepted fixes P12.1-S5-F1 and P12.1-S5-F2
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Prior DS review: `docs/reviews/phase12-1-slice5-code-review-ds-20260521.md`
- Controller adjudication: `docs/reviews/phase12-1-slice5-code-review-controller-adjudication-20260521.md`
- Implementation artifact (with fix addendum): `docs/reviews/phase12-1-slice5-implementation-codex-20260521.md`
- Output file: `docs/reviews/phase12-1-slice5-rereview-ds-20260521.md`
- Included scope: only P12.1-S5-F1 / P12.1-S5-F2 fix changes in `utils/smoke_host_public_multiturn.py` and `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- Excluded scope: unrelated historical Phase 12 files, other Slice 5 files

## Verdict

**PASS**

## Fix Verification

### P12.1-S5-F1: `_find_smoke_tool` must not fall back to module-global mutable state

**Evidence:**

- `_find_smoke_tool` at `utils/smoke_host_public_multiturn.py:1233-1244` 只遍历传入 `tool_bundle.definitions`，未找到 `SmokeFactTool` callable 时返回 `None`。
- 模块级 `_DISCOVERED_SMOKE_TOOL` 已完全删除：`grep` 在文件中 0 匹配。
- `discover_smoke_tools` at line 324-350 仅创建局部 `SmokeFactTool` 实例并放入返回的 `ToolsDiscoveryProviderOutput.definitions`，不再通过 `global` 语句设置模块级变量。
- 测试 `test_find_smoke_tool_only_inspects_passed_tool_bundle` at `tests/runtime/test_smoke_host_public_multiturn_assembly.py:95-115` 先调用 `discover_smoke_tools(...)` 制造历史 provider 调用，再断言 `_find_smoke_tool(ToolBundle(definitions=())) is None`，覆盖回归点。

**结论：修复准确，无残留 fallback。**

### P12.1-S5-F2: `discover_smoke_tools` docstring must describe ToolsDiscovery provider semantics

**Evidence:**

- `discover_smoke_tools` docstring at `utils/smoke_host_public_multiturn.py:327-332` 明确声明：
  - 该函数是 "ToolsDiscovery provider callable"。
  - 调用条件为 workspace `tool_discovery.json` 显式启用 provider spec 且 spec 的 import path 指向 `utils.smoke_host_public_multiturn:discover_smoke_tools`。
  - 调用方为 `ToolsDiscovery`。
- 不再使用"脚本默认注入"等模糊表述。

**结论：docstring 精确描述调用权归属与触发条件。**

## Regression Check

### Runtime assembly path

- `test_runtime_assembly_uses_workspace_tool_discovery_and_typed_overrides` 完整验证 `resolve_runtime_locations` → `ConfigLoader` → `ToolsDiscovery` → `ScenePrepare` → `select_runner_option_hint` → `merge_agent_policy_config` → `provider_request_extension_from_json` 链路。
- `test_runtime_assembly_fails_before_host_when_tools_not_discovered` 验证默认 disabled provider 不被人造 `ToolBundle` 掩盖。

### Manual ToolBundle injection

- `_prepare_runtime_assembly` 内部无脚本内 mock `ToolBundle` 创建或注入路径；所有工具来自 `ToolsDiscovery().discover()` 输出。

### Host public usage

- `run_smoke` 仅通过 `async with open_host(assembly.options) as host:` 进入 Host，后续只调用 `ensure_session`、`submit_followup`、`watch_session_events`、`get_session`。

### Strict typing

- `pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` → 0 errors, 0 warnings, 0 informations。

## Test Results

| 命令 | 结果 |
|------|------|
| `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 3 passed |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 60 passed |
| `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q` | 8 passed |
| `python utils/smoke_host_public_multiturn.py --help` | 通过，退出码 0 |
| `python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Open Questions

无。

## Residual Risk

- 本次仅验证 P12.1-S5-F1 / P12.1-S5-F2 修复正确性，未重新审计 Slice 5 其他实现细节。
- `test_public_compact_smoke.py` 的 context window fix 已在 DS 初次 review 中确认为测试 setup 修正，不阻塞。
- 真实 provider 网络调用未验证（默认 `tool_discovery.json` provider 为 disabled），属于后续 work unit。
