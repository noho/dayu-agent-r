# WU-TOOLS-01 Slice S3 Re-Review (AgentDS)

Gate: re-review (fix gate)
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Reviewer: AgentDS
Status: PASS

## Scope

仅审 Controller 已接受 findings (A1/A2/A3) 的 fix，外加新增 response projection 的分层耦合检查。不审 implementation / deferred findings / OLD residual。

审查依据：
- `docs/reviews/wu-tools-01-slice3-code-review-controller-adjudication.md`
- `docs/reviews/wu-tools-01-slice3-fix-codex.md`
- `git diff HEAD`

## A1. OLD ToolRegistry / truncation owner wording cleanup — PASS

验证方式：全文搜索 + 逐段审读 LLM-facing schema text。

- `dayu/tools/doc_tools.py` 中已无 "ToolRegistry"、"TruncationManager" 字面量（grep 确认）。
- 模块 docstring (line 1-22) 正确描述当前边界："调用方会在工具执行边界传入已经校验并归一化的路径参数；本模块函数体只处理文档读取和结构化提取逻辑"。
- `register_doc_tools` docstring 不再包含 OLD ToolRegistry 示例；遗留参数标注为"迁移保留参数；当前模块忽略该值，不把它注册为可信访问范围"。
- `get_file_sections`/`read_file`/`read_file_section` docstring 不再声称函数体拥有 path safety / truncation ownership。
- `read_file` Note (line 854): "工具函数返回读取到的内容；超过展示限制时由工具执行入口按声明处理" — 正确将截断所有权导向执行入口（current ToolRuntime），不暗示函数体自己截断。
- LLM-facing tool descriptions 统一使用"配置允许访问"措辞。没有向 LLM 暗示 Doc 函数体执行安全校验的错误语义。

结论：A1 fix 完整，无残留 OLD 安全 owner 暗示。

## A2. Legacy registration params — PASS

验证方式：代码路径追踪 + 测试断言。

- `register_doc_tools` (doc_tools.py:112-171) 签名完整保留（`allowed_paths`, `allow_file_write`, `allowed_write_paths`, `timeout_budget`）。
- 函数体第 136-139 行对四个遗留参数执行 `del`，不向任何下游传递。
- 函数体内不存在 `registry.register_allowed_paths(...)` 调用（grep 确认）。
- 测试 `test_collector_allowed_paths_are_not_trusted` (test_doc_tools_provider.py:251-279):
  - 传入 `allowed_paths=[tmp_path]`, `allow_file_write=True`, `allowed_write_paths=[str(tmp_path)]`, `timeout_budget=1.0` 作为遗留参数。
  - 以 `path_policy=None` 适配声明。
  - 断言执行返回 `ToolFailedOutcome` 且 error=`"permission_denied"` — 无显式 path policy 时 fail closed。
  - 断言 `collector._allowed_path_calls == []` — collector 的 `register_allowed_paths` 未被调用。
- `registry_collector.py` 中 `register_allowed_paths` 方法 docstring 明确说明："该方法不解析、不校验、不归一化路径，也不把记录值暴露为可信白名单"。

结论：A2 fix 完整，collector 记录的 `register_allowed_paths` 不被信任为安全源。

## A3. Path chaining projection — PASS

验证方式：代码路径追踪 + 集成测试 + edge case reasoning。

### Response projection 实现

`_project_legacy_response` (definition_adapter.py:240-253) 对 `list_files` / `search_files` 做响应投影：

- `list_files.files[].path`: 基于返回 `directory` 归一化为绝对路径（`_project_list_files_response`, line 256-285）
- `search_files.matches[].file`: 同样逻辑（`_project_search_files_response`, line 288-317）
- `_project_response_path` (line 343-355): 已为绝对路径时直接 resolve；相对路径时以 `base_directory` 为基准拼接后 resolve
- 非 Mapping 返回值、缺失 directory/files/matches 字段时保持原值不变，不做破坏性投影

投影时机：在 `project_legacy_return` 中先于 ok/value envelope 解包执行（line 210）。对不使用 envelope 的 Doc 工具直接走 `_completed_outcome(value=projected_value)` 路径。

### 路径遍历安全

响应投影不做路径白名单校验（那是输入投影的职责）。`_project_response_path` 中的 `Path("../escape")` 经 `resolve()` 后会落到 `base_directory` 的父目录，但后续 read 工具调用时，`_project_paths` 输入投影会对该路径再次校验 `allowed_roots` 并拒绝。

安全链：response projection 归一化 → input projection 校验 → 进入迁移函数体。两层之间不依赖对方保证安全。符合 defense in depth。

### 测试覆盖

`test_list_and_search_return_paths_can_chain_to_read_tools` (test_doc_tools_provider.py:300-381):

- 显式创建 `allowed_root = tmp_path / "allowed-root"`，文件放在 `allowed_root / "reports" / "sample.md"`
- 断言 `allowed_root.resolve() != Path.cwd().resolve()` — 确保非 CWD 场景真实覆盖
- 验证链式调用:
  - `list_files → read_file`: 断言 `listed_path == str(target.resolve())`，read 返回 `ToolCompletedOutcome`
  - `list_files → get_file_sections`: 返回 `ToolCompletedOutcome`
  - `search_files → read_file`: 断言 `matched_path == str(target.resolve())`，read 返回 `ToolCompletedOutcome`
  - `search_files → read_file_section`: 断言 `matched_ref` 是有效 ref，read_section 返回 `ToolCompletedOutcome`
- 20/20 tests passed

结论：A3 fix 完整，list_files/search_files 返回路径可直接链入 read 工具，非 CWD allowed root 场景有真实覆盖。

## A4. Response projection 分层耦合检查 — NON-BLOCKING OBSERVATION

这是 re-review 指令中额外要求的检查点。

### 现状

`_project_legacy_response` 位于共享 `_legacy_adapter/definition_adapter.py`，内部分发硬编码了 Doc 专属工具名 `"list_files"` / `"search_files"` 和 Doc 专属输出字段 `files[].path` / `matches[].file`。

### 判断：不构成当前阻塞

理由：

1. **内聚性**：响应投影是输入投影的对称操作。adapter 已经在输入方向处理路径归一化（`_project_paths` + `ToolPathValidationPolicy`），输出方向做同样的归一化保持语义一致性。路径处理是 adapter 的固有职责而非 Doc 专属。

2. **私有性**：`_project_legacy_response` 及其辅助函数均为模块级私有函数，不在 `__all__` 中暴露，不影响 adapter 公共契约。

3. **可扩展性**：dispatch 模式（按 tool_name 分发）可自然增加条目。当前只有一个 provider 需要此投影，为它引入 provider 级 projector 注册机制属于过度设计，违反 CLAUDE.md "不做过度设计，以最小化满足需求为标准"。

4. **无业务逻辑泄漏**：投影只做路径归一化（Path 拼接 + resolve），不包含 Doc 业务规则、不修改 OLD 业务逻辑返回的其他字段、不在 provider 层和 adapter 层之间引入循环依赖。

### 设计笔记（供后续参考）

当前方案在只有一个 provider 需要响应投影时是合理的。如果未来出现以下信号，应该考虑将响应投影提升为声明级机制：

- 3 个以上不同 provider 需要在 adapter 中做响应投影
- 投影逻辑开始涉及业务字段重命名、结构重组而非纯路径归一化
- 单个 provider 的投影规则超过 5 条

可行的演进方向：在 `CollectedLegacyTool` 上增加 `response_path_fields: tuple[str, ...]` metadata（类似已有的 `file_path_params`），adapter 据此做泛化投影，消除工具名硬编码。

## 验证结果

- `pytest tests/tools/test_doc_tools_provider.py tests/documents`: **20 passed**
- `pyright`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **clean**（由 fix report 确认）
- 手工 grep: `doc_tools.py` 中 **0** 处 "ToolRegistry" / "TruncationManager" / "register_allowed_paths"

## 结论

**PASS**。A1/A2/A3 三个 Controller accepted findings 均已正确修复，新增响应投影不构成分层耦合阻塞。无 blocking finding。
