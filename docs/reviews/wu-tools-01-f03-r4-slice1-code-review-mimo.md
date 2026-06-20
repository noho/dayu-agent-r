# WU-TOOLS-01-F03-R4 Slice 1 Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-mimo.md`
- Included scope: WU-TOOLS-01-F03-R4 Slice 1 implementation changes
- Excluded scope: Slice 2-7, README updates, design doc updates

## Findings

未发现实质性问题。

## Correctness Analysis

### 1. 删除 allow_empty 后的一致性验证

**ConfigLoader / ToolsDiscovery / Service mapping 一致性**：

- `ToolDiscoveryProviderConfig` 已删除 `allow_empty` 字段 (`config_loader.py:590`)
- `ToolsDiscoveryProviderSpec` 已删除 `allow_empty` 字段 (`tools_discovery.py:104`)
- `_parse_tool_discovery_provider()` 不再解析 `allow_empty` (`config_loader.py:2029`)
- `_tool_discovery_specs()` 不再映射 `allow_empty` (`host_assembly.py:934-938`)
- `_validate_provider_output()` 统一拒绝空 `definitions` (`tools_discovery.py:542-543`)

**enabled provider empty definitions 统一 fail fast**：

- `_validate_provider_output()` 在 `not output.definitions` 时抛出 `ToolsDiscoveryError` (`tools_discovery.py:542-543`)
- 测试 `test_empty_provider_without_allow_empty_fails` 验证空输出失败 (`test_tools_discovery.py:437`)
- 测试 `test_empty_provider_is_rejected_even_when_other_providers_are_disabled` 验证即使其他 provider disabled，空输出仍失败 (`test_tools_discovery.py:460`)

**disabled providers 仍可使最终 ToolBundle 为空**：

- `ToolsDiscovery.discover_from_bindings()` 在没有启用 provider 被调用时返回 `ToolBundle(definitions=(), _allow_empty=True)` (`tools_discovery.py:262-263`)
- 这是正确的语义：没有 provider 参与发现时，空 bundle 是合法的

### 2. Packaged config 验证

- `workspace_root=workspace/`：所有 Fins providers 已设置 (`tool_discovery.json:10,32,39,52`)
- OLD limits：`financial-read-tools.config.limits` 和 `doc-tools.config.limits` 已填入 OLD 默认值 (`tool_discovery.json:12-22,64-69`)
- `doc-tools.enabled=false`：已设置 (`tool_discovery.json:61`)
- `financial-upload-tools.enabled=false`：临时禁用，符合 Slice 1 handoff 约定 (`tool_discovery.json:50`)

### 3. Service effective config 验证

**relative workspace_root 解析**：

- 新增 `_effective_fins_workspace_root_config_value()` 用于解析相对路径 (`host_assembly.py:970-1012`)
- 相对路径使用 `_resolve_project_path()` 解析，包含路径逃逸检查 (`host_assembly.py:1627-1645`)
- 当 `configured_workspace_root` 为空字符串时抛出 `ValueError` (`host_assembly.py:999-1002`)
- 当相对路径缺少 `workspace_root` 时抛出 `ValueError` (`host_assembly.py:1007-1010`)

**类型安全**：

- 所有参数都有明确类型注解
- `configured_workspace_root` 使用 `isinstance(configured_workspace_root, str)` 检查 (`host_assembly.py:993`)

**无反向依赖**：

- `_effective_fins_workspace_root_config_value()` 只使用 `pathlib.Path` 和 `_resolve_project_path()`
- 不 import `dayu.engine` / `dayu.host` / `dayu.fins`

**无 raw config mutation**：

- `_effective_tool_provider_config()` 创建新的 `dict` 而不是修改原始 config (`host_assembly.py:965`)
- 测试 `test_fins_tool_discovery_spec_resolves_relative_workspace_root` 验证原始 config 未被修改 (`test_host_assembly.py:1150`)

### 4. Scope ownership 验证

**utils/diagnose_web_access.py 修改**：

- 只删除了 `allow_empty=False` 参数 (`diagnose_web_access.py:1367`)
- 这是 `ToolsDiscoveryProviderSpec` 签名更新的必要调整
- 不是 scope overrun，而是 signature fallout

### 5. Tests 验证

**pytest 覆盖**：

- `tests/runtime/test_config_loader.py`: 41 passed
- `tests/runtime/test_tools_discovery.py` + `test_tools_discovery_digest.py`: 19 passed
- `tests/service/test_host_assembly.py`: 47 passed
- `tests/tools/test_combined_tools_acceptance.py`: 8 passed
- `tests/tools/test_doc_tools_provider.py`: 通过
- `tests/fins/test_fins_storage_provider.py`: 通过
- `tests/fins/test_fins_ingestion_tools.py`: 通过

**pyright 验证**：

- `pyright dayu tests utils`: 0 errors, 0 warnings, 0 informations

**关键测试覆盖**：

- `test_tool_discovery_provider_allow_empty_is_rejected`: 旧 `allow_empty` 字段被拒绝 (`test_config_loader.py:1081-1082`)
- `test_fins_tool_discovery_spec_resolves_relative_workspace_root`: 相对路径解析 (`test_host_assembly.py:1119-1150`)
- `test_discover_service_tools_carries_effective_fins_config_into_compose`: effective config 传递到 wait adapter (`test_host_assembly.py:1226-1268`)
- `test_empty_provider_without_allow_empty_fails`: 空输出失败 (`test_tools_discovery.py:420-440`)

### 6. AGENTS 约束验证

- **中文 docstring**: 所有新增/修改的函数都有中文 docstring ✅
- **严格类型**: 所有参数和返回值都有类型注解 ✅
- **无 Any/object 扩散**: 未使用 `Any` 或 `object` ✅
- **无兼容旧 schema**: `allow_empty` 作为未知字段被拒绝 ✅
- **无 README 误触发或遗漏说明**: Slice 1 不修改 README，由后续 slice 处理 ✅

## Open Questions

无。

## Residual Risk

### 已识别的 residual risks

1. **Upload provider 临时禁用**: `financial-upload-tools.enabled=false` 是 Slice 1 的临时桥接，需要在后续 upload provider slice 中移除 provider 内 allowlist 逻辑并恢复默认注册。

2. **Fins read provider 内部 `include_read_tools`**: 虽然 packaged config 已删除该字段，但 provider 内部仍理解该字段。需要在 Slice 3 中清理。

3. **Doc provider empty `allowed_paths` 行为**: 当前 `doc-tools.enabled=false` 是临时措施。需要在 Slice 5 中实现 enabled Doc provider with empty `allowed_paths` 的 fail fast。

4. **Scene manifest exposure**: 需要在后续 slice 中处理默认 scene manifest 的 tool selection，防止 `start_fins_upload` 被 broad `"fins"` tag 匹配选中。

### 未覆盖的测试场景

1. **相对路径 + `workspace_root=None` 的组合**: 测试覆盖了相对路径解析成功的情况，但未测试当 `workspace_root=None` 时相对路径抛出 `ValueError` 的场景。

2. **空字符串 `workspace_root`**: 测试未覆盖 `workspace_root=""` 时的 `ValueError` 抛出。

3. **非字符串 `workspace_root`**: 测试未覆盖 `workspace_root=123` 时的 `ValueError` 抛出。

这些场景虽然被代码中的 `ValueError` 处理覆盖，但缺少专门的测试用例来锁定行为。

## Verdict

**pass**

实现正确，无 blocking findings。所有关键变更都按照 Slice 1 plan 执行：

1. `allow_empty` 已从 config schema、runtime spec 和 Service mapping 中删除
2. 空 `definitions` 统一 fail fast
3. 相对 `workspace_root` 正确解析为绝对路径
4. Packaged config 符合 Slice 1 / 后续 slice handoff 约定
5. `utils/diagnose_web_access.py` 修改只是 signature fallout，可接受
6. 测试覆盖充分，pyright 通过

## Blocking Findings

无 blocking findings。

## Recommendation

可以进入 accepted slice commit gate。后续 slices 应按计划继续处理：

- Slice 2: Service effective Fins workspace path resolution (已完成，因为 Slice 1 需要它)
- Slice 3: Fins read provider independent-provider semantics
- Slice 4: Fins upload provider and local-file allowlist removal
- Slice 5: Doc provider fail-fast and limits default assertions
- Slice 6: Documentation and design synchronization
- Slice 7: Final validation and cleanup
