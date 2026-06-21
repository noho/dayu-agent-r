# WU-TOOLS-01-F03-R4 Slice 3 implementation artifact

## Gate

implementation only。按用户约束，本轮未执行 code review、deepreview、commit、push，也未修改 `docs/host/issues-implementation-control.md`。

## 范围

Slice 3 目标成立：`financial-read-tools` 已是独立 provider，内部 `include_read_tools` 二级开关与 provider-level `enabled` 重复，并允许启用 provider 时跳过 `workspace_root` fail-fast。当前实现应让 `enabled` 成为 read provider 是否参与发现的唯一开关。

## 改动

- `dayu/fins/tools/provider.py`
  - 删除 `_CONFIG_INCLUDE_READ_TOOLS_FIELD`。
  - 删除 `_parse_bool_default(...)`。
  - `discover_tools(...)` 启用路径始终解析 limits、解析显式绝对 `workspace_root`、创建 `DefaultFinsRuntime`，并返回九个 Fins read tool definitions。
- `tests/fins/test_fins_storage_provider.py`
  - 删除旧的“关闭 read tools 时不解析 workspace_root”语义测试。
  - 改为覆盖启用 read provider 时缺失 `workspace_root` 必须 fail-fast。
  - 更新 `_spec(...)` helper 和相对路径失败测试，不再构造 `include_read_tools`。
- `tests/fins/test_fins_ingestion_tools.py`
  - 更新 workspace overlay fixture，不再给 read provider 传 `include_read_tools`。
- `tests/runtime/test_config_loader.py`
  - 移除旧字段名负断言，确保 test code 中没有 `include_read_tools` 引用。
- `dayu/fins/README.md`、`tests/README.md`
  - 按 README 触发规则做最小同步：read provider 启用时要求显式绝对 workspace root，并返回九个 read tools；参与发现只由 provider-level `enabled` 控制。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：77 passed，3 个 edgar 依赖 deprecation warnings。
- `source .venv/bin/activate && pyright dayu tests utils`
  - 结果：0 errors, 0 warnings, 0 informations。
- `rg -n "include_read_tools|_CONFIG_INCLUDE_READ_TOOLS_FIELD|_parse_bool_default" -g '*.py' dayu tests utils`
  - 结果：无生产或测试 Python 代码引用。

## README 决策

本轮修改触发 `dayu/fins/README.md` 与 `tests/README.md` 的当前事实同步，已做最小更新。`dayu/config/README.md` 仍包含旧配置描述，但本 Slice 未修改 `dayu/config/`，且 Slice 1 artifact 已将 config README 的完整语义同步归入后续 docs slice；本轮不扩展到该文档。

## 残留风险

- covered by later approved slice：`dayu/config/README.md` 仍有旧配置描述，需要在后续 docs slice 与 config / upload 语义清理一起更新。
- covered by later approved slice：upload provider 的 `allowed_upload_roots` 行为仍未在本 Slice 处理，属于 Slice 4。

## 完成状态

Slice 3 implementation complete。当前 read provider 不再支持内部 `include_read_tools` 语义；启用 provider 必须提供显式绝对 `workspace_root`，并返回九个 read tools。
