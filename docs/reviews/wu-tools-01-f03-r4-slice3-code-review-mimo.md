# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `c785f218` (gateflow: accept WU-TOOLS-01-F03-R4 slice 1)
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-mimo.md`
- Included scope:
  - `dayu/fins/tools/provider.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/tools/test_combined_tools_acceptance.py` (read-only, no changes, verified no stale refs)
  - `dayu/fins/README.md`
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md` (WU control file, out-of-scope for code findings)
  - `docs/reviews/wu-tools-01-f03-r4-slice3-implementation-codex.md` (Codex implementation artifact)
- Excluded scope: future Slice 4/5/6 implementation work (upload `allowed_upload_roots`, Doc provider, docs slice)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下逐项对齐用户 focus questions，基于直接证据：

### Focus 1: read provider 不再支持 `include_read_tools`，只依赖 provider-level `enabled`

**证据**：

- `dayu/fins/tools/provider.py:28` — `_CONFIG_INCLUDE_READ_TOOLS_FIELD` 常量已删除。
- `dayu/fins/tools/provider.py:44-58` — `discover_tools(...)` 无条件执行 `_parse_limits` → `parse_fins_workspace_root_config` → `DefaultFinsRuntime.create` → `build_fins_read_tool_definitions` → `_validate_fins_definitions` → 返回九个 definitions。无任何 `include_read_tools` 分支。
- `dayu/fins/tools/provider.py:180` — `_parse_bool_default` 辅助函数已删除。
- `rg -n "include_read_tools|_CONFIG_INCLUDE_READ_TOOLS_FIELD|_parse_bool_default" -g '*.py' dayu tests utils` — 无命中。

**结论**：read provider 内部不再有二级开关。是否参与发现完全由 `ToolsDiscoveryProviderSpec.enabled` 控制。

### Focus 2: enabled read provider 始终解析 limits、要求显式绝对 `workspace_root`、创建 `DefaultFinsRuntime`、返回九个 read definitions

**证据**：

- `dayu/fins/tools/provider.py:44-58` — 调用链：`_parse_limits(spec.config)` → `parse_fins_workspace_root_config(spec.config)` → `DefaultFinsRuntime.create(workspace_root=workspace_root)` → `build_fins_read_tool_definitions(read_runtime=read_runtime, limits=limits)` → `_validate_fins_definitions(definitions)`。
- `dayu/fins/tools/provider.py:61-80` — `parse_fins_workspace_root_config` 要求非空字符串且 `is_absolute()`，否则 `ValueError`。
- `dayu/fins/tools/provider.py:183-203` — `_validate_fins_definitions` 断言 `names == FINS_READ_TOOL_NAMES`。
- `dayu/fins/tools/fins_tools.py:56-66` — `FINS_READ_TOOL_NAMES` 包含恰好 9 个工具名。
- `tests/fins/test_fins_storage_provider.py:84-94` — 测试侧 `_FINS_READ_TOOL_NAMES` 也包含恰好 9 个工具名，与生产常量一致。
- `tests/fins/test_fins_storage_provider.py:722-733` — 新测试 `test_fins_read_provider_requires_workspace_root_when_enabled` 验证 `workspace_root=None` 时 `discover_tools` 抛出 `ValueError(match="workspace_root")`。

**结论**：enabled 路径严格按预期执行。无短路、无静默跳过。

### Focus 3: 删除 `tests/runtime/test_config_loader.py` 中 `include_read_tools` 字符串断言是否可接受

**证据**：

- `tests/runtime/test_config_loader.py:388` — 旧断言 `assert "include_read_tools" not in read_provider.config` 已删除。
- 该断言的目的是验证 packaged config 不包含 `include_read_tools`。Slice 1 已将 `dayu/config/tool_discovery.json` 中的 `include_read_tools` 字段删除（`docs/reviews/wu-tools-01-f03-r4-slice1-implementation-codex.md:44`）。
- `rg -n "include_read_tools" dayu/config/` — 命中仅限 `dayu/config/README.md`（旧文档描述，deferred to docs slice），packaged JSON 已无该字段。
- Slice 3 completion signal 要求 "no production or test Python references `include_read_tools`"。删除此断言是 completion signal 的直接结果：断言检查的对象已不存在，保留断言反而引入对已删除字段的隐式依赖。
- 同一测试文件 `test_config_loader.py:388` 仍保留 `assert "include_ingestion_tools" not in read_provider.config`，验证同类负断言模式仍被使用。

**结论**：删除可接受。Slice 1 已清理 packaged config，Slice 3 清理 provider 内部语义，断言对象已不存在。保留断言反而会让未来开发者困惑于一个已删除字段的负断言。

### Focus 4: README 变更是否为 AGENTS 触发规则要求的最小同步，而非不受控的 docs-slice overrun

**证据**：

- `dayu/fins/README.md` 两处变更：
  1. 第 111 行：删除 `include_read_tools=false` 语义描述，替换为 "read provider 是否参与发现只由 provider-level `enabled` 控制"。
  2. 第 666 行：删除 `include_read_tools=false` 时不解析 workspace 的描述，替换为 "read provider 启用时始终解析 workspace 并注册九个 read tools"。
  - 变更范围严格限于 `dayu/fins/tools/provider.py` 行为变更的事实同步，未扩展到未修改模块。
- `tests/README.md` 一处变更：
  - 第 177 行：删除 `include_read_tools=false` 返回空工具集的描述，替换为 "read provider 启用时要求显式绝对 workspace root"。
  - 变更范围严格限于 `tests/fins/` 测试覆盖的事实同步。
- CLAUDE.md 触发规则：`dayu/fins/` 修改 → 检查并按需更新 `dayu/fins/README.md`；`tests/` 修改 → 检查并按需更新 `tests/README.md`。两个 README 变更均由触发规则驱动。
- `dayu/config/README.md` 仍包含旧 `include_read_tools` 描述（`dayu/config/README.md:190`），但 Slice 3 未修改 `dayu/config/`，且 Slice 1 implementation artifact 已将 config README 更新归入后续 docs slice。本轮不扩展到该文档是正确的。

**结论**：README 变更是触发规则要求的最小同步，不是不受控的 docs-slice overrun。

### Focus 5: tests 和 pyright 是否充分

**验证结果**：

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_config_loader.py -q`：118 passed，3 个 edgar 依赖 deprecation warnings。
- `pyright dayu/fins/tools/provider.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/runtime/test_config_loader.py`：0 errors, 0 warnings, 0 informations。
- `tests/tools/test_combined_tools_acceptance.py` 无 `include_read_tools` 引用，config 已使用新语义（第 660-674 行）。
- `dayu/` 下无 Python 文件引用 `include_read_tools`。
- 新测试 `test_fins_read_provider_requires_workspace_root_when_enabled` 覆盖了 Slice 3 的核心语义变更：启用 provider 时缺少 `workspace_root` 必须 fail-fast。
- 旧测试 `test_fins_provider_can_disable_read_tools_without_workspace_root` 已删除，其语义（`include_read_tools=false` 返回空工具集）在 Slice 3 中不再成立。

**边界覆盖评估**：

- `workspace_root=None` → fail-fast：已覆盖（新测试）。
- `workspace_root` 相对路径 → fail-fast：已覆盖（`test_fins_workspace_root_must_be_explicit_absolute_path`，第 1145 行）。
- `workspace_root` 正常绝对路径 → 返回九个 tools：已覆盖（多个现有测试通过 `_discover_definitions` 调用）。
- `limits` 解析：已覆盖（`_spec` helper 默认传入 limits，多个测试间接覆盖）。
- 无 stale imports：`_parse_bool_default` 和 `_CONFIG_INCLUDE_READ_TOOLS_FIELD` 的 import 已随函数/常量删除一并移除。

**结论**：tests 和 pyright 充分。未发现缺失的边界测试、stale imports、LLM-facing text 回归或 scope 违规。

## Open Questions

无。

## Residual Risk

- `dayu/config/README.md` 仍包含旧 `include_read_tools` 和 `allowed_upload_roots` 描述（第 190 行）。已由 Slice 1 implementation artifact 和 Codex Slice 3 artifact 明确标记为 deferred to later docs slice。不影响 Slice 3 correctness。
- `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md` 中多处历史描述仍提及 `include_read_tools`（如第 52、59、64 行等）。这些是 plan 文档中的问题陈述和历史上下文，不是活跃代码路径，不需要在 Slice 3 中清理。
- 旧 review artifacts（`docs/reviews/wu-tools-01-slice4-code-review-mimo.md` 等）中多处提及 `include_read_tools`。这些是历史记录，不影响当前实现。
