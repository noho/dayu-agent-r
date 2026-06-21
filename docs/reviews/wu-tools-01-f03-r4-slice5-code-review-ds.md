# Code Review — WU-TOOLS-01-F03-R4 Slice 5

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f03-r4
- Base: 4514f550 (accepted Slice 4 commit)
- Output file: docs/reviews/wu-tools-01-f03-r4-slice5-code-review-ds.md
- Included scope:
  - `dayu/tools/doc_provider.py` — Doc provider fail-fast 与 `_parse_limits` 解析。
  - `tests/tools/test_doc_tools_provider.py` — Doc fail-fast 测试与显式 limits 投影测试。
  - `tests/fins/test_fins_storage_provider.py` — Fins 显式 limits 投影测试。
  - `tests/README.md` — 最小测试覆盖描述同步。
  - `tests/runtime/test_config_loader.py` — 确认 packaged config 原样读取（未在本 Slice 修改，作为 context 检查）。
  - `docs/host/issues-implementation-control.md` — 状态记录更新（非生产代码，不作为 correctness 审查对象）。
  - `docs/reviews/wu-tools-01-f03-r4-slice5-implementation-codex.md` — Codex 实现说明（作为 context 参照）。
- Excluded scope:
  - Slice 6 docs/design 同步。
  - `dayu/fins/tools/provider.py`、`dayu/fins/tools/fins_limits.py`、`dayu/fins/tools/fins_tools.py` 仅在理解 limits 解析全链路时读取，非本 Slice 修改。
  - `dayu/tools/doc_tools.py` 仅在理解 `build_doc_tool_definitions` 调用链时读取，非本 Slice 修改。
- Parallel review coverage: 无（单 reviewer，范围可控）。

## Review Method Summary

1. 阅读全部 diff（committed + unstaged），确认改动声称语义。
2. 沿四条关键路径逐行走读：
   - Doc provider `discover_tools` → `_parse_allowed_paths` → `ValueError` 抛出路径。
   - Doc provider `discover_tools` → `_parse_limits` → `DocToolLimits` 构造 → `build_doc_tool_definitions` → 参数 schema `maximum` 与 `ToolTruncateSpec.limits` 投影。
   - Fins provider `discover_tools` → `_parse_limits` → `FinsToolLimits` 构造 → `build_fins_read_tool_definitions` → `ToolTruncateSpec.limits` 投影。
   - ConfigLoader `load_runtime_config` → `tool_discovery.providers` 原样读取，不解析 provider 特有 limits 字段。
3. 对照六项 focus area 逐条验证。
4. Adversarial failure pass：检查空输入、非法类型、非正整数、配置缺失、参数化覆盖盲区。

## Findings

未发现实质性问题。

经过以下六项 focus area 逐条验证，以及 adversarial failure pass（空输入、非法类型、非正整数、配置覆盖、参数化盲区），本 Slice 实现与 Slice 5 plan 一致，无 blocking findings。

### Focus Area 1：Enabled Doc provider + missing/empty allowed_paths → ValueError

- **入口**: `discover_tools()` at `dayu/tools/doc_provider.py:47-50`。
- **实现**: `_parse_allowed_paths()` 返回空元组（缺失 key → `None` → `return ()` at line 149-150；空列表 → `return tuple(paths)` at line 158，paths 为空）。`discover_tools` 在 `if not allowed_roots:` 处抛出 `ValueError(_EMPTY_ALLOWED_PATHS_ERROR)`。
- **测试**: `test_provider_enabled_without_allowed_paths_fails_fast` at `tests/tools/test_doc_tools_provider.py:251-271`，参数化覆盖 `{"limits": {}}`（缺失 `allowed_paths`）与 `{"limits": {}, "allowed_paths": []}`（空白名单），两种路径均断言 `pytest.raises(ValueError, match=...)`。
- **旧行为清理**: 移除了 `ToolsDiscoveryError` import（原测试用于 ToolsDiscovery 聚合层空输出拒绝），移除了 `ToolsDiscovery().discover_from_bindings(...)` 的二级断言模式。ToolsDiscovery 的空输出防线仍在 `dayu/runtime/tools_discovery.py` 中保留，对非 Doc provider 路径仍有效。
- **结论**: 通过。Doc provider 启用但缺失或空白名单时不再返回空 `definitions`，改为在 provider 边界抛出含 Doc 业务语义的 `ValueError`。

### Focus Area 2：Doc provider limits 解析归属 provider 所有

- **Provider 端**: `_parse_limits()` at `dayu/tools/doc_provider.py:60-105` 是 Doc provider 私有函数，完整解析 `DocToolLimits` 五个字段，每个字段通过 `_positive_int()` 校验类型与范围。
- **ConfigLoader 端**: `tests/runtime/test_config_loader.py:414-422` 断言 `doc_provider.config["limits"]` 为原始 JSON dict（`{"list_files_max": 200, "get_sections_max": 200, ...}`），不做任何解析或类型转换。Fins 同理 at lines 389-400。
- **Packaged config**: `dayu/config/tool_discovery.json` 中 Doc limits 字段值与 ConfigLoader 测试断言完全一致。ConfigLoader 只负责把 packaged JSON 原样投影到 typed view，不解析 provider 特有语义。
- **结论**: 通过。Limits 解析逻辑完全在 Doc/Fins provider 各自 `_parse_limits()` 中；ConfigLoader 只做原样读取与类型校验。

### Focus Area 3：Doc 显式 limits 测试验证 schema maximums 与 truncate specs

- **测试**: `test_doc_provider_explicit_limits_shape_schema_and_truncate_specs` at `tests/tools/test_doc_tools_provider.py:976-1005`。
- **验证内容**:
  - 传入非默认 limits：`list_files_max=31, get_sections_max=32, search_files_max_results=33, read_file_max_chars=3400, read_file_section_max_chars=3500`。
  - 三个参数 schema maximum 通过 `_parameter_maximum()` helper 断言：`list_files.limit=31`、`get_file_sections.limit=32`、`search_files.limit=33`。
  - 两个截断声明通过 `_truncate_limit()` helper 断言：`read_file.max_chars=3400`、`read_file_section.max_chars=3500`。
- **与默认值区分**: 所有测试值均与 `DocToolLimits` 默认值（200, 200, 50, 80000, 50000）显著不同，确保断言验证的是配置值而非 dataclass 默认值。
- **Helper 健壮性**: `_parameter_maximum` 在 `isinstance(parameter_schema, Mapping)` 和 `isinstance(maximum, int)` 两道类型断言；`_truncate_limit` 在 `isinstance(truncate, ToolTruncateSpec)` 和 `isinstance(limit, int)` 两道类型断言。均使用强类型守卫，不依赖隐式转换。
- **结论**: 通过。测试正确验证了显式配置值在 parameter schema `maximum` 与 `ToolTruncateSpec.limits` 中的投影。

### Focus Area 4：Fins 显式 limits 测试验证所有 ToolDefinition-visible limits

- **测试**: `test_fins_provider_explicit_limits_shape_truncate_specs` at `tests/fins/test_fins_storage_provider.py:1115-1159`。
- **验证内容**:
  - 传入完整 limits（含 `processor_cache_max_entries: 16` 与九个 ToolDefinition-visible 字段）。
  - 九个 read tools 的 `ToolTruncateSpec.limits` 全部断言：`list_documents.max_items=21`、`get_document_sections.max_items=122`、`search_document.max_items=23`、`list_tables.max_items=54`、`read_section.max_chars=8100`、`get_page_content.max_chars=8200`、`get_table.max_items=830`、`get_financial_statement.max_items=1240`、`query_xbrl_facts.max_items=1250`。
  - 全部九个工具均被覆盖，与 `FINS_READ_TOOL_NAMES` 定义的九个工具名一一对应。
- **`processor_cache_max_entries` 处理**:
  - 该字段在 config 中显式传入（`16`），经 `_parse_limits()` 解析为 `FinsToolLimits.processor_cache_max_entries`，传入 `runtime.get_read_runtime(processor_cache_max_entries=...)` 用于 LRU processor cache 容量。
  - 该字段不进入 `build_fins_read_tool_definitions` 的任何 `ToolTruncateSpec` 或 parameter schema。
  - 测试正确地将它保留在 config 输入中（保证 limits 完整性），但不做 `ToolDefinition` 级别断言（正确性）。
- **与默认值区分**: 所有测试值均与 `FinsToolLimits` 默认值显著不同（如 `list_documents_max_items` 默认 300，测试 21；`read_section_max_chars` 默认 80000，测试 8100）。
- **结论**: 通过。测试覆盖全部九个 ToolDefinition-visible limits 字段，`processor_cache_max_entries` 被正确处理为 runtime cache 输入而非 ToolDefinition 可见字段。

### Focus Area 5：README 更新为最小 tests README 同步

- **修改范围**: `tests/README.md` 仅两处修改：
  - Doc provider 描述行（line 166）：从 "启用但缺少 `allowed_paths` 时 fail closed" 改为 "启用但缺失或空 `allowed_paths` 时以 Doc-specific `ValueError` fail fast"，并补充 "显式 limits 到参数上限和截断声明的投影"。
  - Fins 描述行（line 177）：补充 "显式 limits 到各工具截断声明的投影"。
- **未修改**: 根 `README.md`、`dayu/README.md`、`dayu/config/README.md`、设计文档均未改动。
- **结论**: 通过。README 更新严格限制在 `tests/README.md` 的测试覆盖事实描述，未扩散到 docs/design Slice 6 领域。

### Focus Area 6：Tests/pyright 充分性

- **pytest**: `tests/runtime/test_config_loader.py` + `tests/tools/test_doc_tools_provider.py` + `tests/fins/test_fins_storage_provider.py` → 97 passed。`tests/tools/test_combined_tools_acceptance.py` → 8 passed。
- **pyright**: `dayu/ tests/ utils/` → 0 errors, 0 warnings, 0 informations。
- **Stale imports**: `ToolsDiscoveryError` 从 `tests/tools/test_doc_tools_provider.py` import 中正确移除（diff line 44-47）；其他模块无 stale import。
- **Weak assertions**: 两项新增测试（Doc 显式 limits、Fins 显式 limits）均使用非默认配置值 + `isinstance` 类型断言，不依赖宽松 `==` 或隐式转换。
- **Missing edge cases**:
  - `allowed_paths` 参数化覆盖了缺失与空列表两条路径；`allowed_paths=None`（显式 null）与缺失行为一致（`config.get()` 对两者均返回 `None`），不构成独立盲区。
  - Limits 的 `_positive_int` 错误路径（非正整数、bool 类型）由函数自身分支覆盖；显式 limits 测试聚焦成功投影路径，符合 Slice 5 scope。
  - 未新增 `processor_cache_max_entries` 行为级测试——该字段需要 runtime cache 行为集成测试，超出本 Slice 范围，已在实现 artifact 中声明为 residual risk。
- **Scope violations**: 无。改动严格限制在 Slice 5 plan 范围内（Doc fail-fast + 两项显式 limits 测试 + README 同步）。
- **结论**: 通过。测试覆盖充分，pyright 清洁，无 stale import、weak assertion 或 scope violation。

## Open Questions

无。

## Residual Risk

1. **`processor_cache_max_entries` 缺少行为级集成测试**：当前仅验证该字段不被投影到 `ToolDefinition`。验证它确实影响 processor LRU cache 行为需要更重的 runtime cache 集成测试（构造多个 processor、观察缓存驱逐），目前无覆盖。已在实现 artifact 中声明，不属于本 Slice regression surface。**风险等级**: 低。

2. **`build_doc_tool_definitions` 的空 `allowed_roots` 防御守卫残留**：`dayu/tools/doc_tools.py:290-291` 的 `if not allowed_roots: return ()` 在 Doc provider 路径下不可达（因 `discover_tools` 提前 fail fast），但对直接调用方（如测试 monkeypatch 路径）仍是有效的防御守卫。不是 bug，但可能造成 "哪个层负责拒绝空白名单" 的维护困惑。建议在后续 Slice 中决定是否保留该守卫并更新其 docstring。**风险等级**: 低。

3. **`tests/tools/test_doc_tools_provider.py` 与 `tests/fins/test_fins_storage_provider.py` 共享了同形态的 `_truncate_limit` helper**：两边实现完全一致（包括 `isinstance` 断言顺序）。当前不影响 correctness，但若未来 `ToolTruncateSpec.limits` 的 key 名变更，需要两处同步修改。符合项目现有的 "测试 helper 与测试文件共存" 惯例，不构成新风险。**风险等级**: 低。

## Verdict

**通过 — 0 blocking findings。**

Slice 5 实现与 plan 一致，六项 focus area 全部通过。Doc provider 的 fail-fast 边界变更正确且测试覆盖充分；两项显式 limits 投影测试验证了配置值到 `ToolDefinition` 的完整链路；ConfigLoader 保持原样读取不解析 provider 语义；README 更新为最小同步。所有测试通过，pyright 清洁。
