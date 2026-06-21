# WU-TOOLS-01-F03-R4 Slice 7 Final Validation

## Scope

- 验证 WU-TOOLS-01-F03-R4 全部已接受 slices 的组合结果。
- 修复 final validation 暴露出的相关测试夹具遗漏。
- 不修改生产代码、配置、README 或稳定设计文档。
- 不进入 aggregate deepreview、push、PR 或 merge。

## Changes

- `tests/runtime/test_scene_assets_migration.py`
  - 将 fake tool catalog 从旧的泛化 `fake_fins_lookup` 更新为当前默认 scene manifest 显式选择的 Fins read / download / preprocess 工具名。
  - 该测试验证 scene assets migration 后的 manifest 与工具 catalog 可匹配；Slice 4 删除 broad `"fins"` / `"ingestion"` 默认选择后，测试夹具必须跟随当前显式工具名。

## Validation

已在激活 `.venv` 后运行：

```bash
pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
```

结果：`60 passed`。

```bash
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
```

结果：`58 passed, 3 warnings`。warnings 来自既有 `edgar` deprecation warning。

```bash
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q
```

结果：`70 passed, 3 warnings`。warnings 来自既有 `edgar` deprecation warning。

```bash
pytest tests/runtime/test_scene_prepare.py -q
```

结果：`31 passed`。

```bash
pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：`42 passed, 3 warnings`。warnings 来自既有 `edgar` deprecation warning。

```bash
pytest tests/runtime/test_scene_assets_migration.py -q
```

结果：`7 passed`。

```bash
pytest tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
```

结果：`1 passed`。

```bash
pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py
```

结果：`866 passed, 1 skipped, 3 warnings`。warnings 来自既有 `edgar` deprecation warning。

```bash
pytest tests/tools/web -q
```

结果：`75 passed, 1 failed, 3 warnings`。

失败项：

- `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases`
- 失败原因：测试断言 `captured.out` 包含 `web smoke execution started`，但当前日志进入 pytest 的 `Captured log call`，不在 stdout。
- 归类：非本 WU 引入。本 WU 未修改 `tests/tools/web/test_smoke_web_ci.py` 或 `utils/smoke_web_ci.py`；当前失败在单独运行 `tests/tools/web` 时复现。该问题属于 web smoke 日志捕获 / 测试期望边界，不属于 Tools Discovery spec 语义清理。

```bash
pyright dayu tests utils
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 另提示存在新版本 `v1.1.410`，当前环境使用 `v1.1.409`。

## Stale Field Grep

```bash
rg -n "include_read_tools|allowed_upload_roots" dayu tests README.md
```

结果：

- `include_read_tools` 无生产、测试或 README 命中。
- `allowed_upload_roots` 只剩 `tests/runtime/test_config_loader.py` 的负向断言，确认 packaged upload provider config 不包含该字段。

```bash
rg -n "workspace_root\": null" dayu/config/tool_discovery.json tests
```

结果：无命中。

```bash
rg -n "\"allow_empty\"|allow_empty" dayu/config dayu/runtime dayu/service dayu/fins dayu/tools tests README.md
```

剩余命中分类：

- scene manifest 与 `dayu/runtime/scene_prepare.py` 的 `tool_selection.allow_empty`，这是 scene 工具选择空匹配语义，不是 ToolsDiscovery provider 空输出控制。
- `ToolBundle._allow_empty=True` 只用于 runtime 内部 no-tool bundle 构造。
- `dayu/fins/direct_events.py` 的 `allow_empty` 是 direct event 字符串字段校验语义。
- `tests/runtime/test_config_loader.py` 保留 provider-level `allow_empty` 作为旧字段拒绝测试。
- `tests/runtime/test_scene_tool_selection.py` / `tests/runtime/test_scene_prepare.py` 覆盖 scene `tool_selection.allow_empty`。
- `tests/contracts/test_tool_declaration.py` 覆盖 `ToolBundle._allow_empty` 内部行为。
- `README.md` / `tests/README.md` / `dayu/config/README.md` 中的命中均说明当前允许的 scene 或负向测试语义。

## Residual Risk

- `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases` 当前失败已分类为非本 WU 引入的 web smoke 日志捕获问题。当前 WU 不修改 web smoke 工具或日志策略；后续应由 web smoke / CI owner 单独裁决是否修正测试断言或日志输出通道。
- 未运行全仓 `pytest` 不带 ignore 的最终全绿矩阵，因为上述已分类 web smoke 单测会稳定失败。

## Completion

Final validation 对 WU-TOOLS-01-F03-R4 的 Tools Discovery 语义清理未发现新的本 WU 阻塞问题。下一步进入 aggregate deepreview，由 AgentMiMo / AgentDS 对完整 work unit diff、artifact、控制文档和 residual risk 分类做交叉审查。
