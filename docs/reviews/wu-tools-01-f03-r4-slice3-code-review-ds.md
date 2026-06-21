# Code Review — WU-TOOLS-01-F03-R4 Slice 3

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `c785f218` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 1`)
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-ds.md`
- Review date: 2026-06-21
- Included scope:
  - `dayu/fins/tools/provider.py` — Fins read provider
  - `tests/fins/test_fins_storage_provider.py` — read provider tests
  - `tests/fins/test_fins_ingestion_tools.py` — workspace overlay fixture
  - `tests/runtime/test_config_loader.py` — config loader assertion removal
  - `tests/tools/test_combined_tools_acceptance.py` — baseline verification (not modified)
  - `dayu/fins/README.md` — Fins README sync
  - `tests/README.md` — tests README sync
  - `docs/reviews/wu-tools-01-f03-r4-slice3-implementation-codex.md` — implementation artifact
  - `docs/host/issues-implementation-control.md` — controller status updates (not implementation changes)
- Excluded scope: Slice 4/5/6 future implementation work; `dayu/config/README.md` (intentionally deferred to Slice 6)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项焦点验证

**Focus 1: read provider 不再支持 include_read_tools，仅依赖 provider-level enabled？**

- `dayu/fins/tools/provider.py:29`：`_CONFIG_INCLUDE_READ_TOOLS_FIELD` 已删除。
- `dayu/fins/tools/provider.py:180-198`（旧行号）：`_parse_bool_default(...)` 函数已整体删除。
- `dayu/fins/tools/provider.py:44-58`：`discover_tools(...)` 不再包含 `include_read_tools` 分支判断和提前 return 路径。函数现在直接从 limits 解析、workspace_root 解析到 runtime 创建和 tool definitions 构建，无任何条件跳过。
- `rg -n "include_read_tools|_CONFIG_INCLUDE_READ_TOOLS_FIELD|_parse_bool_default" -g '*.py' dayu tests utils` 返回 `NO_MATCHES`，确认生产代码和测试代码中零引用。
- `discover_tools` 的调用方是 `ToolsDiscovery`（位于 `dayu.runtime`），它在调用前检查 `enabled`。因此 `enabled` 是 provider 参与发现的唯一开关。

✅ 确认。

**Focus 2: 启用的 read provider 是否始终解析 limits、要求显式绝对 workspace_root、创建 DefaultFinsRuntime、返回恰好九个 read definitions？**

- `dayu/fins/tools/provider.py:45`：`limits = _parse_limits(spec.config)` — 始终解析 limits。
- `dayu/fins/tools/provider.py:46`：`workspace_root = parse_fins_workspace_root_config(spec.config)` — 始终解析 workspace_root。
- `dayu/fins/tools/provider.py:61-80`：`parse_fins_workspace_root_config(...)` 要求值是非空字符串（`isinstance(value, str) and value.strip() != ""`，第 75 行）且为绝对路径（`path.is_absolute()`，第 78 行）。不存在 cwd/env 回退分支。
- `dayu/fins/tools/provider.py:47`：`runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)` — 始终创建 DefaultFinsRuntime。
- `dayu/fins/tools/provider.py:51`：`definitions = build_fins_read_tool_definitions(read_runtime=read_runtime, limits=limits)` — 始终构建 read tool definitions。
- `dayu/fins/tools/provider.py:52`：`_validate_fins_definitions(definitions)` — 始终校验工具名集合。
- `dayu/fins/tools/provider.py:198-200`：`_validate_fins_definitions` 要求 `names == FINS_READ_TOOL_NAMES`。
- `dayu/fins/tools/fins_tools.py:56-69`：`FINS_READ_TOOL_NAMES` 包含恰好九个工具名：`list_documents`、`get_document_sections`、`read_section`、`search_document`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts`。

✅ 确认。

**Focus 3: tests/runtime/test_config_loader.py 中删除 include_read_tools 字符串断言是否可接受？**

- 被删除行：`assert "include_read_tools" not in read_provider.config`。
- Slice 1（commit `c785f218`）已将 `dayu/config/tool_discovery.json` 中 `financial-read-tools.config.include_read_tools` 字段删除。
- Slice 3 完成信号为"No production or test code references `include_read_tools`"，`rg` 已确认满足。
- `ConfigLoader._parse_tool_discovery_provider(...)` 对未知字段会 reject；因此即使外部 overlay 传入 `include_read_tools`，也会在 ConfigLoader 层 fail fast。不再需要 provider 测试中的负断言做回归守卫。
- 该断言删除后，相邻的 `assert "include_ingestion_tools" not in read_provider.config`（`tests/runtime/test_config_loader.py:388`）仍然保留，作为不同字段（ingestion provider 字段不应泄漏到 read provider config）的边界检查。

✅ 可接受。旧负断言是 Slice 1 config 清理前的回归守卫；在打包配置已清理、生产代码零引用、ConfigLoader 已拒绝未知字段的前提下，该断言已无独立回归价值。

**Focus 4: README 修改是否最小、由 AGENTS triggers 驱动，而非不受控的 docs-slice 越界？**

- `dayu/fins/README.md:111`：更新了 `discover_tools` 描述，从"`include_read_tools=false` 时返回空工具集且不解析 `workspace_root`"改为"启用时必须在 provider config 中提供绝对 `workspace_root`，并返回九个 read tools；read provider 是否参与发现只由 provider-level `enabled` 控制"。这是对 `dayu/fins/tools/provider.py` 修改的直接语义同步。
- `dayu/fins/README.md:666`：更新了"Workspace root 与 provider fail fast"段落，删除"read provider 在 `include_read_tools=false` 时允许不解析 workspace"的特例，改为"read provider 启用时始终解析 workspace 并注册九个 read tools"。这是对同一行文义的直接同步。
- `tests/README.md:177`：更新了 `tests/fins/` 覆盖描述，从"`include_read_tools=false` 返回空工具集且不解析 workspace root"改为"read provider 启用时要求显式绝对 workspace root"。这是对测试覆盖语义变更的直接同步。
- `dayu/config/README.md` 未修改：implementation artifact 和 plan 均明确将该文件的旧配置描述更新归入 Slice 6（documentation slice），不做本次 Slice 3 越界修改。

✅ 确认。README 修改命中 AGENTS trigger（`dayu/fins/` 和 `tests/` 均有修改），改动范围限定于本次 provider 行为变更的直接语义同步，未扩展到不相关文档。

**Focus 5: 测试和 pyright 是否充分？是否有遗漏的边界测试、过时 import、LLM-facing 文本回归或范围越界？**

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`：**77 passed**，3 个上游 `edgar` deprecation warnings（非本 WU 范围）。
- `pyright dayu tests utils`：**0 errors, 0 warnings, 0 informations**。
- `rg` 确认零残留引用。
- 旧测试 `test_fins_provider_can_disable_read_tools_without_workspace_root` 已替换为 `test_fins_read_provider_requires_workspace_root_when_enabled`（`tests/fins/test_fins_storage_provider.py:722`），覆盖了 `workspace_root=None` → `ValueError` 路径。
- `test_fins_workspace_root_must_be_explicit_absolute_path`（`:1145`）保留并更新：移除了 `include_read_tools` 构造参数，继续覆盖相对路径 → `ValueError` 路径。
- `_spec(...)` helper（`:1316`）不再构造 `include_read_tools`。
- `_write_split_fins_provider_overlay(...)`（`tests/fins/test_fins_ingestion_tools.py:1608`）不再向 read provider config 写入 `include_read_tools`。
- `test_combined_tools_acceptance.py` 作为验证基线通过（8 passed），无修改——符合 Slice 3 非目标。
- LLM-facing tool schema 定义在 `dayu/fins/tools/fins_tools.py` 中，不在 Slice 3 修改范围内，无回归风险。
- 无过时 import：`provider.py` 的 import 列表无变更，`_parse_bool_default` 删除后无残留 import。
- `_validate_fins_definitions`（`:198`）作为运行时安全网保留，校验 `build_fins_read_tool_definitions` 的输出始终与 `FINS_READ_TOOL_NAMES` 一致。

✅ 确认。测试覆盖了正向路径（正常 workspace_root → 9 tools）、两个 fail-fast 路径（None workspace_root、相对 workspace_root），以及回归基线（combined acceptance tests）。pyright 零错误。

## Open Questions

无。

## Residual Risk

- `dayu/config/README.md` 仍包含旧 `include_read_tools` 配置描述，已由 plan Slice 6 承接，不在本 Slice 修复范围。
- upload provider 的 `allowed_upload_roots` 清理由 Slice 4 承接，不在本 Slice 范围。
- 当 `workspace_root` 为非字符串类型（如整数）或全空白字符串时，`parse_fins_workspace_root_config` 会正确 fail fast，但这两条边界没有独立测试用例。当前测试覆盖了 `None` 和相对路径两条主路径；非字符串/全空白字符串的 fail-fast 行为由同一函数内的同一 `isinstance`/`strip` 守卫覆盖，回归风险低。

## Verdict

**pass** — 无阻塞发现。Slice 3 的实现完整移除了 Fins read provider 的 `include_read_tools` 二级开关，启用的 provider 始终解析 limits、要求显式绝对 workspace_root、创建 DefaultFinsRuntime、通过 `_validate_fins_definitions` 校验后返回九个 read tool definitions。测试、pyright、残留引用 grep 均通过。README 修改限于触发的文档语义同步。`dayu/config/README.md` 的旧内容由后续 Slice 6 承接。
