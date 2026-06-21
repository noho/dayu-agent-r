# WU-TOOLS-01-F03-R4 Slice 5 Implementation Artifact

## 动机判断

Slice 5 问题真实存在。直接证据是 `dayu/tools/doc_provider.py` 在 Doc provider 启用但 `allowed_paths` 缺失或为空时返回空 `definitions`，这会把 Doc 业务配置错误推迟到 `ToolsDiscovery` 的通用空输出错误，错误语义不够具体，也不利于配置定位。正确边界应由 Doc provider 在解析自身业务配置时 fail fast。

Packaged Doc / Fins limits 的配置真源已经在 `dayu/config/tool_discovery.json` 中显式存在，`tests/runtime/test_config_loader.py` 已断言 config loader 原样读出这些 packaged 值，因此本 Slice 不需要修改 packaged config。

## 改动内容

- `dayu/tools/doc_provider.py`
  - 删除 enabled + missing/empty `allowed_paths` 返回空 `definitions` 的分支。
  - 改为抛出 Doc-specific `ValueError`：`doc provider config.allowed_paths must contain at least one path when doc-tools is enabled`。
  - 同步模块与函数 docstring，明确缺失或空白名单是 Doc 业务配置错误。

- `tests/tools/test_doc_tools_provider.py`
  - 将旧的“空 definitions 后由 ToolsDiscovery 拒绝”测试改为 provider 边界直接断言 `ValueError`。
  - 覆盖 `allowed_paths` 缺失与空列表两种路径。
  - 新增显式完整 Doc limits 配置测试，断言 `list_files` / `get_file_sections` / `search_files` 参数 `maximum` 以及 `read_file` / `read_file_section` truncate `max_chars` 反映配置值。

- `tests/fins/test_fins_storage_provider.py`
  - 新增显式完整 Fins limits 配置测试，断言九个 read tools 的 truncate specs 反映配置值。
  - `processor_cache_max_entries` 作为完整配置输入保留；它影响 runtime cache，不投影到 `ToolDefinition.truncate`，因此不做 definition 断言。

- `tests/README.md`
  - 按 README 更新触发规则做最小同步：更新 Doc provider 缺失/空 `allowed_paths` fail-fast 覆盖事实，并补充 Doc / Fins 显式 limits 投影覆盖事实。

## Config / README 决策

- 未修改 `dayu/config/tool_discovery.json`。原因：packaged Doc / Fins limits 已经显式存在，且 `tests/runtime/test_config_loader.py` 已断言具体值。
- 未修改根 README、`dayu/README.md`、`dayu/config/README.md` 或设计文档。原因：本 Slice 未改变用户入口、安装/CLI 工作流、分层关系或配置 schema；只修正 Doc provider 错误边界并补测试覆盖。
- 修改 `tests/README.md` 是必要的最小同步，因为测试覆盖事实从 “fail closed” 变为 Doc-specific fail fast。

## `allowed_paths` 关键路径

`rg -n "allowed_paths" dayu/tools/doc_provider.py tests/tools/test_doc_tools_provider.py` 关键结果：

- `dayu/tools/doc_provider.py:29` 定义 Doc-specific 错误信息。
- `dayu/tools/doc_provider.py:47` `discover_tools()` 解析 `allowed_paths`。
- `dayu/tools/doc_provider.py:50` 缺失或空白名单直接抛出 `ValueError`。
- `dayu/tools/doc_provider.py:135` `_parse_allowed_paths()` 仍只负责类型解析与路径归一化，缺失或空列表返回空元组。
- `tests/tools/test_doc_tools_provider.py:251` 参数化覆盖缺失与空 `allowed_paths`。
- `tests/tools/test_doc_tools_provider.py:267` 断言 Doc-specific 错误文本。
- `tests/tools/test_doc_tools_provider.py:988` 显式 limits 测试使用合法 `allowed_paths`。
- `tests/tools/test_doc_tools_provider.py:1063` 常规 `_spec()` 仍使用显式 `allowed_paths`。

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`
  - 结果：`97 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`8 passed, 3 warnings`
- `source .venv/bin/activate && pyright dayu tests utils`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `rg -n "allowed_paths" dayu/tools/doc_provider.py tests/tools/test_doc_tools_provider.py`
  - 已执行并用于上方关键路径记录。

Warnings 均来自 edgar 依赖的 deprecation warning，非本 Slice 引入。

## 残留风险 / 未覆盖项

- 未新增 `processor_cache_max_entries` 行为级断言；该字段不进入 tool definitions，需要更重的 runtime cache 行为测试才可直接验证，超出 Slice 5 范围。
- 未做设计文档 Slice 6 同步；用户明确要求不实施 docs/design Slice 6。
- 未提交、未 push，且未修改 `docs/host/issues-implementation-control.md`。
