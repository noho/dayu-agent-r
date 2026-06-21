# WU-TOOLS-01-F03-R4 Slice 5 Code-Review Fix

## Scope

- 只处理 Controller 已接受的 MiMo F1 / F2 test-hardening findings。
- 未修改生产代码。
- 未修改 `docs/host/issues-implementation-control.md`。
- 未提交，未 push，未执行新的 review。

## Changes

1. `tests/fins/test_fins_storage_provider.py`
   - 在 `test_fins_provider_explicit_limits_shape_truncate_specs` 保留九个 ToolDefinition-visible limits 断言。
   - 追加遍历全部 Fins tool definitions 的 negative assertion，显式确认 `processor_cache_max_entries` 不出现在任何 `ToolTruncateSpec.limits` 中。

2. `tests/tools/test_doc_tools_provider.py`
   - 新增 `test_doc_provider_partial_limits_fall_back_to_defaults`。
   - 测试只传 `list_files_max=99`，断言 `list_files.limit.maximum` 使用显式值。
   - 同时断言 `get_file_sections`、`search_files`、`read_file`、`read_file_section` 的可见 limits 使用 `DocToolLimits()` 默认值。

3. `tests/README.md`
   - 未修改。现有测试手册已描述 Doc / Fins provider limits 投影事实；本轮只增加同一事实下的回归保护，无新增测试层级或运行方式。

## Validation

已在激活 `.venv` 后运行：

```bash
pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q
```

结果：`57 passed, 3 warnings`。warnings 均来自 `edgar` 依赖的既有 deprecation warning。

```bash
pytest tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：`49 passed, 3 warnings`。warnings 均来自 `edgar` 依赖的既有 deprecation warning。

```bash
pyright dayu tests utils
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 另提示存在新版本 `v1.1.410`，当前环境使用 `v1.1.409`。

## Residual Risk

- 本轮只补 ToolDefinition 投影层面的测试保护，不验证 `processor_cache_max_entries` 对 Fins processor LRU cache 容量的行为影响；该行为级集成测试仍属于更重的 runtime cache 覆盖范围。
- 未发现需要修改生产代码的真实 bug。
