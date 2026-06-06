# WU-TOOLS-01 Slice S3 Re-Review

Gate: re-review
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Agent: AgentMiMo
Status: PASS

## Review Scope

仅审查 Controller 已接受 findings（A1, A2, A3）的 fix，不做 implementation / fix / commit / push / PR。

审查对象：

- `docs/reviews/wu-tools-01-slice3-code-review-controller-adjudication.md`（Controller 裁决）
- `docs/reviews/wu-tools-01-slice3-fix-codex.md`（Fix 说明）
- 当前未提交 diff（`git diff HEAD`）

## A1. OLD ToolRegistry / truncation owner 术语清理

**结论: PASS**

| 检查项 | 结果 |
|---|---|
| 模块 docstring 中 OLD ToolRegistry 引用 | 已清除。当前 docstring（`doc_tools.py:1-22`）只描述当前迁移边界，明确"调用方会在工具执行边界传入已经校验并归一化的路径参数；本模块函数体只处理文档读取和结构化提取逻辑"。 |
| 函数 docstring 中 OLD ToolRegistry 引用 | 已清除。`register_doc_tools` docstring（`doc_tools.py:120-135`）将 `allowed_paths`、`allow_file_write`、`allowed_write_paths`、`timeout_budget` 明确标记为"迁移保留参数；当前模块忽略该值"。 |
| OLD ToolRegistry() 示例 | 已移除。 |
| LLM-facing schema text 中错误安全 owner 暗示 | 已清理。五个 tool description 现在使用"配置允许访问且实际存在的目录/文件"措辞（`doc_tools.py:181`、`298`、`600`、`798`、`931`），不暗示函数体内部执行安全检查，也不暴露 Host/Engine 治理术语。 |

**无 blocking finding。**

## A2. register_doc_tools 签名保留但 collector.register_allowed_paths 不被信任

**结论: PASS**

| 检查项 | 结果 |
|---|---|
| `register_doc_tools` 签名保留 | 保留。签名含 `allowed_paths`、`allow_file_write`、`allowed_write_paths`、`timeout_budget` 参数。 |
| `registry.register_allowed_paths` 调用 | 已移除。四个遗留参数在函数体入口处通过 `del` 显式丢弃（`doc_tools.py:136-139`），不进入任何条件分支。 |
| 测试覆盖 | `test_collector_allowed_paths_are_not_trusted`（`test_doc_tools_provider.py:251-279`）传入所有遗留参数（包括 `allowed_paths=[tmp_path]`、`allow_file_write=True`、`timeout_budget=1.0`），断言 `collector._allowed_path_calls == []` 且执行结果为 `ToolFailedOutcome(error="permission_denied")`。 |

**无 blocking finding。**

## A3. list_files / search_files 返回路径可链到 read_file / get_file_sections / read_file_section

**结论: PASS**

### 投影实现审查

响应投影在 `dayu/tools/_legacy_adapter/definition_adapter.py` 中实现：

1. `project_legacy_return`（`definition_adapter.py:210`）调用新增的 `_project_legacy_response`。
2. `_project_legacy_response`（`definition_adapter.py:221`）按 `tool_name` 分派到 `_project_list_files_response` 和 `_project_search_files_response`。
3. `_project_list_files_response`（`definition_adapter.py:231`）从返回值中读取 `directory` 字段，将 `files[].path` 中的相对路径通过 `_project_response_path` 转为基于 `directory` 的绝对路径。
4. `_project_search_files_response`（`definition_adapter.py:259`）对 `matches[].file` 做同样投影。
5. `_project_response_path`（`definition_adapter.py:306`）对绝对路径做 `resolve(strict=False)`，对相对路径做 `(Path(base_directory) / path).expanduser().resolve(strict=False)`。

关键设计决策：

- **投影基于返回的 `directory` 字段**，而非猜测 provider allowed root。这避免了多个 allowed root 下相对文件名歧义的问题。
- **`dir_path` 来源可信**：`list_files` 和 `search_files` 中 `dir_path = Path(directory)` 经 adapter 路径输入投影后已经是校验过的绝对路径，返回值中的 `str(dir_path)` 因此也是绝对路径。
- **投影只改变返回值中的路径字段**，不改变 OLD 函数体的列表/搜索逻辑。

### 测试覆盖审查

`test_list_and_search_return_paths_can_chain_to_read_tools`（`test_doc_tools_provider.py:300-381`）：

- 构造 `allowed_root = tmp_path / "allowed-root"`，assert `allowed_root.resolve() != Path.cwd().resolve()`，确认 allowed root 不等于进程 CWD。
- 执行 `list_files` → 取 `files[0].path` → assert 值等于 `target.resolve()`（绝对路径）。
- 用返回的绝对路径依次调用 `read_file` 和 `get_file_sections`，均返回 `ToolCompletedOutcome`。
- 执行 `search_files` → 取 `matches[0].file` 和 `matches[0].ref` → assert `file` 等于 `target.resolve()`。
- 用返回的绝对路径和 ref 依次调用 `read_file` 和 `read_file_section`，均返回 `ToolCompletedOutcome`。

测试覆盖了 `list_files → read_file`、`list_files → get_file_sections`、`search_files → read_file`、`search_files → read_file_section` 四条链路，且在 allowed root ≠ CWD 条件下执行。

**无 blocking finding。**

## 4. 新增响应投影的分层/耦合审查

**结论: PASS**

| 检查项 | 结果 |
|---|---|
| Doc 专属工具名是否硬编码进共享层 | `_project_legacy_response`（`definition_adapter.py:221-227`）按 `tool_name` 字符串 `"list_files"` / `"search_files"` 分派。该函数位于 `_legacy_adapter/definition_adapter.py`，是迁移适配器层，不是共享业务层。`_legacy_adapter` 的职责就是处理迁移工具的特殊适配逻辑。 |
| Doc 专属输出结构是否侵入共享层 | `_project_list_files_response` 和 `_project_search_files_response` 了解 `files[].path` 和 `matches[].file` 字段结构，但这些是迁移工具的公开 JSON 合约，不是内部实现细节。投影函数在 `_legacy_adapter` 内部，不暴露给外部。 |
| 是否应改到 provider/声明级 projector | 当前实现位置合理。投影逻辑与 `project_legacy_return` 紧耦合（在同一调用链上），放在 `definition_adapter.py` 保持了响应投影的单一入口。如果未来有更多迁移工具需要类似投影，可以提取为注册式 projector，但当前只有两个工具，不值得提前抽象。 |
| 是否违反分层架构 | 不违反。`_legacy_adapter` 是 `dayu.tools` 包内的迁移基础设施，位于 provider（`doc_provider.py`）和业务函数（`doc_tools.py`）之间，符合 adapter 模式定位。 |

**无 blocking finding。**

## 5. 验证结果可信度

| 验证项 | 结果 | 可信度 |
|---|---|---|
| `pytest tests/tools/test_doc_tools_provider.py tests/documents` | 20 passed（0.80s） | 可信。独立复现，输出与 fix 报告一致。 |
| `pyright` | 0 errors, 0 warnings, 0 informations | 可信。独立复现。 |
| `git diff --check` | clean | 可信。独立复现。 |

**验证结果可信。**

## 其它观察（非 blocking）

1. `_legacy_adapter/exceptions.py` 的 `FileAccessError.__init__` 三参构造形状（`path, filename_or_details, details`）是为保持 OLD `doc_tools.py` 中 `FileAccessError(directory, "", "路径不是目录")` 调用不改写。这是迁移约束下的合理选择，不阻塞。

2. `_legacy_adapter/registry_collector.py` 的 `LegacySyncToolCallable` Protocol 新增 `__tool_name__` 和 `__tool_schema__` 属性，是为了让 `adapt_collected_tool` 能从 callable 上读取 decorator 注入的元数据。符合迁移适配器设计。

3. `dayu/config/README.md` 和 `tests/README.md` 的变更与 S3 功能一致，新增了 Doc provider 配置说明和测试文档。

## 结论

**PASS** — A1、A2、A3 三个 accepted findings 的 fix 实现正确、测试充分、验证可信。响应投影位于 `_legacy_adapter` 内部，不违反分层架构或引入过度耦合。无 blocking finding。
