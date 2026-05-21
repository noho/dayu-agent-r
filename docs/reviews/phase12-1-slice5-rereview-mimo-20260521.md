# Phase 12.1 Slice 5 Re-Review (MiMo)

## Scope

- Mode: re-review of controller-accepted fixes P12.1-S5-F1 / P12.1-S5-F2
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice5-rereview-mimo-20260521.md`
- Reviewed files:
  - `utils/smoke_host_public_multiturn.py`
  - `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - `docs/reviews/phase12-1-slice5-implementation-codex-20260521.md`（fix addendum）
  - `docs/host/implementation-control.md`（gate bookkeeping）
- Excluded: 不在 fix scope 内的历史 Phase 12 文件

## Fix Verification

### P12.1-S5-F1: `_find_smoke_tool` 只检查传入 ToolBundle，无模块级全局 fallback

**PASS**

直接证据：

1. `grep _DISCOVERED_SMOKE_TOOL utils/smoke_host_public_multiturn.py` → 无匹配。模块级全局变量 `_DISCOVERED_SMOKE_TOOL` 已删除。
2. `_find_smoke_tool`（line 1233-1244）只遍历 `tool_bundle.definitions`，用 `isinstance(definition.callable, SmokeFactTool)` 检查，找不到时显式 `return None`。无任何 fallback 到全局状态或历史调用结果。
3. `discover_smoke_tools`（line 324-350）不再使用 `global` 语句，只创建局部 `SmokeFactTool` 并放入返回的 `ToolsDiscoveryProviderOutput.definitions`。
4. 测试 `test_find_smoke_tool_only_inspects_passed_tool_bundle`（line 95-115）：
   - 先调用 `discover_smoke_tools(...)` 制造历史 provider 调用（验证 provider 调用后全局状态已不存在）。
   - 断言 `_find_smoke_tool(discovered_bundle) is not None`（从含工具的 bundle 中正确找到）。
   - 断言 `_find_smoke_tool(ToolBundle(definitions=())) is None`（空 bundle 不被历史 provider 调用污染）。
   - 该测试精确覆盖了 P12.1-S5-F1 的回归点。

### P12.1-S5-F2: `discover_smoke_tools` docstring 准确描述 ToolsDiscovery provider 语义

**PASS**

直接证据：

`discover_smoke_tools` docstring（line 327-336）：

> ToolsDiscovery provider callable，用于提供 smoke mock tool。
>
> 该函数仅在 workspace ``tool_discovery.json`` 显式启用 provider spec，且该 spec 的 import path 指向 ``utils.smoke_host_public_multiturn:discover_smoke_tools`` 时由 ``ToolsDiscovery`` 调用。

与旧版 "该函数不会被脚本默认注入" 相比，新 docstring：
- 明确声明函数角色为 `ToolsDiscovery` provider callable。
- 精确描述触发条件：workspace `tool_discovery.json` 显式启用 + import path 匹配。
- 明确调用权归属 `ToolsDiscovery`，不暗示脚本内部有注入逻辑。

## Regression Check

### Runtime assembly path

无回归。`_prepare_runtime_assembly` 调用链（resolve_runtime_locations → ConfigLoader → ToolsDiscovery → prepare_scene → select_runner_option_hint → merge_agent_policy_config → provider_request_extension_from_json）未被本次修改触及。

### Manual ToolBundle injection

无回归。脚本不包含 `--assembly-mode`、手动 `ToolBundle` 注入、脚本内默认工具 fallback。

### Host public usage

无回归。`run_smoke` 只通过 `open_host(assembly.options)` 打开 Host，使用 `Host` 接口方法交互。

### Strict typing

`python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` → 0 errors, 0 warnings, 0 informations。

## Tests Run and Results

| 命令 | 结果 |
|------|------|
| `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 3 passed |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 60 passed |
| `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q` | 8 passed |
| `python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |

## Implementation Artifact Gate Bookkeeping

`docs/host/implementation-control.md` line 226-227 当前 gate 已更新为 "Slice 5 re-review"，fix addendum 已追加到 implementation artifact。一致，无遗漏。

## Verdict

**PASS**

P12.1-S5-F1 / F2 均已正确收口：模块级 `_DISCOVERED_SMOKE_TOOL` 已删除、`_find_smoke_tool` 只检查传入 bundle、`discover_smoke_tools` docstring 准确表达 ToolsDiscovery provider 语义、focused test 精确覆盖历史 provider 调用不污染空 bundle 查找的回归点。无新增 blocker，无 regression。
