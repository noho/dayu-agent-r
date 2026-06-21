# WU-TOOLS-01-F01-02-R1 Slice 3 Narrow Re-Review (AgentMiMo)

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 3 narrow re-review
- target finding: `S3-RR-F01`
- fix artifact: `docs/reviews/wu-tools-01-f01-02-r1-slice3-rereview-fix-codex.md`
- controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-controller-adjudication.md`
- modified files:
  - `dayu/service/host_assembly.py`
  - `tests/service/test_host_assembly.py`
- review timestamp: 2026-06-21T20:17:11

## 复核范围

仅复核 S3-RR-F01 narrow fix：`_tool_discovery_specs(...)` 死生产 helper 是否已删除，tests 是否迁移到 `_tool_discovery_spec(...)` 或当前 production discovery path，且 production discovery behavior 未改变。

## Findings

未发现实质性问题。

### 逐项复核结果

#### 1. `dayu/service/host_assembly.py` 中无 `_tool_discovery_specs` 定义

- **结论**: ✓ 通过
- **证据**: 阅读完整 `host_assembly.py`（2074 行），未找到 `_tool_discovery_specs` 函数定义。当前仅存在 `_tool_discovery_spec`（单数形式，line 1045）和 `_tool_discovery_bindings`（line 1074）。

#### 2. 代码和测试中无 `_tool_discovery_specs` 引用

- **结论**: ✓ 通过
- **证据**: `grep -rn "_tool_discovery_specs"` 在整个仓库中仅命中 `docs/` 目录下的 review artifacts、plan documents 和 archive documents。未命中任何 `.py` 生产代码或测试文件。
- **详情**: 所有匹配项均为历史 review/plan 文档中对旧函数的引用记录，不影响生产代码或测试执行。

#### 3. 测试迁移未降低断言强度

- **结论**: ✓ 通过
- **证据**: 阅读 `tests/service/test_host_assembly.py`（2486 行），确认：
  - line 94: 导入 `_tool_discovery_spec`（单数形式），不再导入 `_tool_discovery_specs`
  - `test_tool_discovery_spec_requires_provider_location` (line 1037): 测试 provider 同时缺少 import_path 和 entry_point 时 fail-fast → 与原测试等价
  - `test_tool_discovery_spec_uses_entry_point_location` (line 1058): 测试 entry point 正确映射为 discovery spec → 与原测试等价
  - `test_tool_discovery_provider_config_survives_loader_and_service_mapping` (line 1085): 测试 provider config 原样进入 ToolsDiscovery spec → 与原测试等价
  - `test_web_tool_discovery_config_survives_service_mapping` (line 1123): 测试 Web provider config 原样进入 spec → 与原测试等价
  - `test_fins_tool_discovery_spec_injects_runtime_workspace_root` (line 1155): 测试 Fins provider workspace root 注入 → 与原测试等价
  - `test_fins_tool_discovery_spec_preserves_explicit_workspace_root` (line 1189): 测试显式 workspace root 不被覆盖 → 与原测试等价
  - `test_fins_tool_discovery_spec_resolves_relative_workspace_root` (line 1220): 测试相对 workspace root 解析 → 与原测试等价
  - 其他 Fins workspace root 相关测试（line 1253-1320）均已迁移为直接测试 `assemble_effective_tool_provider_configs` + `_tool_discovery_spec`
- **迁移策略**: 原测试通过 `_tool_discovery_specs`（plural helper）间接测试单个 provider 映射；迁移后直接调用 `_tool_discovery_spec`（singular helper）测试相同行为，断言内容和强度保持一致。原 plural helper 只是 `tuple(_tool_discovery_spec(pc) for pc in provider_configs)` 的包装，删除后测试等价性不损失。

#### 4. 验证结果可信

- **结论**: ✓ 通过
- **证据**:
  - `pytest tests/service/test_host_assembly.py -q` → 52 passed, 3 warnings（edgar 废弃警告，已有）
  - `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` → 159 passed, 3 warnings
  - `pyright` → 0 errors, 0 warnings, 0 informations（仅提示 pyright 版本更新通知，非类型检查失败）
  - `git diff --check` → passed（无冲突标记）

## Open Questions

无。

## Residual Risk

- 无 S3-RR-F01 相关未覆盖行为：已删除的 helper 无残余引用，production discovery 继续通过 `_tool_discovery_bindings(...)` 路径。
- 本次 narrow fix 范围外的 Slice 3 其它 residual risks 由先前 review 记录，不在本次复核范围内。
