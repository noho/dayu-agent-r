# WU-TOOLS-01-F01-02-R1 Slice 3 Narrow Re-Review (AgentDS)

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 3 narrow re-review fix
- target finding: `S3-RR-F01`: `_tool_discovery_specs` dead production helper
- input fix: `docs/reviews/wu-tools-01-f01-02-r1-slice3-rereview-fix-codex.md`
- input adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-controller-adjudication.md`
- review mode: narrow re-review — only verify S3-RR-F01 fix correctness

## Verification Items

### V1: `_tool_discovery_specs` 已从 `dayu/service/host_assembly.py` 删除

**结论：通过。** 通读 `dayu/service/host_assembly.py`（2074 行），文件内只存在 `_tool_discovery_spec`（单数，line 1045），不包含 `_tool_discovery_specs`（复数）的定义或引用。

### V2: 代码和测试中无 `_tool_discovery_specs` 引用

**结论：通过。** `grep -rn "_tool_discovery_specs" --include="*.py" dayu/ tests/` 零匹配。生产代码与测试代码中已无任何 `_tool_discovery_specs` 引用。

### V3: 测试迁移未降低断言强度

**结论：通过。** 逐一复核了 `tests/service/test_host_assembly.py` 中所有直接调用 `_tool_discovery_spec` 的测试：

| 测试 | 断言要点 | 强度评估 |
|---|---|---|
| `test_tool_discovery_spec_requires_provider_location` | 缺少 import_path/entry_point 时 raise ValueError | 强：fail-fast + 错误消息匹配 |
| `test_tool_discovery_spec_uses_entry_point_location` | entry point 映射到 spec_id、enabled、config 字段 | 强：三字段精确断言 |
| `test_tool_discovery_provider_config_survives_loader_and_service_mapping` | ConfigLoader → `_tool_discovery_spec` 原样传递 config["allowed_paths"] 和 config["limits"] | 强：嵌套字段值断言 |
| `test_web_tool_discovery_config_survives_service_mapping` | Web config 完整 dict 原样进入 spec.config | 强：全 dict eq 断言 |
| `test_fins_tool_discovery_spec_injects_runtime_workspace_root` | 运行时 workspace root 注入 spec.config，raw config 未被污染 | 强：双断言（注入+隔离） |
| `test_fins_tool_discovery_spec_preserves_explicit_workspace_root` | 显式 workspace root 不被运行时默认值覆盖 | 强：反向验证 |
| `test_fins_tool_discovery_spec_resolves_relative_workspace_root` | 相对路径由 Service 解析为绝对路径，raw config 保持不变 | 强：双断言（解析+隔离） |

迁移策略正确：旧 `_tool_discovery_specs(Sequence[...])` 对每个 config 循环调用 `_tool_discovery_spec(...)` 并返回 list。每个被测测试只关心单个 provider-to-spec 映射行为，直接调用 `_tool_discovery_spec(...)` 等价于旧路径且消除了不必要的 list 包装。断言强度与迁移前一致，未发现弱化。

### V4: 验证命令结果可信

| 命令 | 结果 | 可信度 |
|---|---|---|
| `pytest tests/service/test_host_assembly.py -q` | 52 passed, 3 warnings | 通过，warnings 为 edgar 第三方 deprecation |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` | 159 passed, 3 warnings | 通过 |
| `pyright` | 0 errors, 0 warnings, 0 informations | 通过 |
| `git diff --check` | 无输出（clean） | 通过 |

所有验证命令结果与 Codex fix artifact 声称一致。本地复现验证通过。

### V5: Production discovery behavior 未改变

**结论：通过。** 生产路径为 `_tool_discovery_bindings(...)` → 循环内 `_tool_discovery_spec(provider_config)` → 返回 `ToolsDiscoveryProviderBinding`。删除 `_tool_discovery_specs` 后，此调用链无任何变化。`_tool_discovery_spec` 的入参、分支、返回值和副作用保持原样。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 无 S3-RR-F01 专项 residual risk：`_tool_discovery_specs` 已完全移除，无残留引用，测试迁移到位，生产行为不变。
- 更广泛的 Slice 3 residual risk 不在本次 narrow re-review 范围内。

## Conclusion

**pass** — `_tool_discovery_specs` 死生产 helper 已彻底删除，测试已迁移到 `_tool_discovery_spec` 且断言强度保持，production discovery behavior 未改变，所有验证命令可复现通过。无 blocker。
