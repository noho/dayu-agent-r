# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `4514f550` (accepted Slice 4 commit)
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-mimo.md`
- Included scope: `dayu/tools/doc_provider.py`, `tests/tools/test_doc_tools_provider.py`, `tests/fins/test_fins_storage_provider.py`, `tests/runtime/test_config_loader.py`, `tests/tools/test_combined_tools_acceptance.py`, `tests/README.md`, `docs/reviews/wu-tools-01-f03-r4-slice5-implementation-codex.md`
- Excluded scope: Slice 6 docs/design synchronization, except residual risk
- Parallel review coverage: 无

## Findings

### 1-未修复-中-Fins test 未显式断言 `processor_cache_max_entries` 不投影到 ToolDefinition

- **入口/函数**: `test_fins_provider_explicit_limits_shape_truncate_specs`
- **文件(行号)**: `tests/fins/test_fins_storage_provider.py:1115-1159`
- **输入场景**: 显式完整 Fins limits 配置，包含 `processor_cache_max_entries=16` 和 9 个 ToolDefinition-visible limits
- **实际分支**: 测试断言了 9 个 truncate spec limits，但未对 `processor_cache_max_entries` 做任何断言
- **预期行为**: 按 Focus 4，测试应显式验证 `processor_cache_max_entries` 不是 ToolDefinition-visible limit。最直接的证据是断言每个工具的 `truncate.limits` 键集合不包含 `processor_cache_max_entries`
- **实际行为**: 测试将 `processor_cache_max_entries=16` 放入 config 但不做任何 negative assertion。如果实现错误地将该值投影到某个工具的 truncate spec，测试不会发现
- **直接证据**: `tests/fins/test_fins_storage_provider.py:1135` 设置 `processor_cache_max_entries=16`；`tests/fins/test_fins_storage_provider.py:1151-1159` 只断言 9 个 truncate limit 值，不断言键集合完整性。`dayu/fins/tools/provider.py:49` 将该值传给 `runtime.get_read_runtime()` 而非 `build_fins_read_tool_definitions()` 的 truncate 参数
- **影响**: 实现正确，但测试未覆盖回归场景。如果未来有人错误地将 `processor_cache_max_entries` 加入工具 truncate spec，现有测试不会捕获
- **建议改法和验证点**: 在 `test_fins_provider_explicit_limits_shape_truncate_specs` 末尾增加对每个工具 `truncate.limits` 键集合的断言，确认不含 `processor_cache_max_entries`；或对任意一个工具断言 `set(definition.truncate.limits.keys()) == {"max_items"}` 或 `{"max_chars"}`（按策略）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-Doc/Fins test 未覆盖 partial limits fallback 到 dataclass 默认值

- **入口/函数**: `test_doc_provider_explicit_limits_shape_schema_and_truncate_specs`, `test_fins_provider_explicit_limits_shape_truncate_specs`
- **文件(行号)**: `tests/tools/test_doc_tools_provider.py:976-1005`, `tests/fins/test_fins_storage_provider.py:1115-1159`
- **输入场景**: limits 配置只包含部分字段，其余字段缺失
- **实际分支**: 两个测试都传入完整 limits（Doc 5 个字段全填、Fins 10 个字段全填），没有 partial limits 测试
- **预期行为**: 计划明确说 "Missing individual limit fields still fall back to dataclass defaults for test construction convenience"；应有测试覆盖 partial limits 场景，证明缺失字段正确回退到 `DocToolLimits()` / `FinsToolLimits()` 默认值
- **实际行为**: 无 partial limits 测试。`_positive_int()` 在字段缺失时返回 `default`（`doc_provider.py:129`），逻辑正确但无测试直接验证
- **直接证据**: `doc_provider.py:128-129` `value = payload.get(field_name); if value is None: return default`；`tests/tools/test_doc_tools_provider.py:989-995` 所有 5 个 limits 字段都填了非默认值
- **影响**: 回退逻辑正确，但缺失回归保护。如果 `_positive_int()` 的 `None` 分支被意外修改，无测试捕获
- **建议改法和验证点**: 增加一个 partial limits 测试：只传 `list_files_max=99`，断言 `list_files` 参数 maximum 为 99 且其他工具使用 dataclass 默认值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `processor_cache_max_entries` 的 runtime cache 行为（LRU 容量）需要更重的集成测试才能直接验证，超出 Slice 5 范围。当前测试只验证该值不投影到 ToolDefinition，不验证 cache 容量是否生效。
- Slice 6 docs/design 同步未实施；`docs/host/design.md` 中关于 `allow_empty` 的旧语义段落仍存在，需 Slice 6 处理。
- `docs/reviews/wu-tools-01-f03-r4-slice5-implementation-codex.md` 已正确记录实现决策和验证结果，无实质问题。

## Verdict

**Accept with conditions** — 0 blocking findings, 2 non-blocking test gaps。

实现正确：Doc provider 在 enabled + missing/empty `allowed_paths` 时抛出 Doc-specific `ValueError`，不再返回空 definitions。ConfigLoader 只读取 raw packaged config，limits 解析由 provider 自身 `_parse_limits()` 负责。tests/pyright 全通过（97 passed, 0 errors）。README 更新是最小 tests README 同步，未 overrun 到 docs/design。

条件：建议在后续提交中补充 Finding 1 的 negative assertion（`processor_cache_max_entries` 不出现在 ToolDefinition truncate limits 中），以及 Finding 2 的 partial limits fallback 测试。
