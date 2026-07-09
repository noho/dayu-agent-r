# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `a124e0a8`（workspace changes since this commit, including staged, unstaged, and untracked files）
- Output file: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s2-code-review-mimo.md`
- Included scope:
  - `dayu/fins/resolver/__init__.py`（新增）
  - `dayu/fins/resolver/fmp_company_info.py`（新增）
  - `dayu/service/scene_context.py`（新增）
  - `dayu/cli/commands/prompt.py`（修改）
  - `dayu/cli/commands/interactive.py`（修改）
  - `dayu/cli/commands/session.py`（修改）
  - `tests/fins/test_fmp_company_info_resolver.py`（新增）
  - `tests/service/test_entrypoint_runtime.py`（修改）
  - `tests/service/test_entrypoint_runtime_interactive_path.py`（修改）
  - `tests/service/test_import_boundary.py`（修改）
  - `tests/cli/test_prompt_command.py`（修改）
  - `tests/cli/test_interactive_command.py`（修改）
  - `tests/cli/test_session_command.py`（修改）
  - `dayu/fins/README.md`（修改）
  - `tests/README.md`（修改）
- Excluded scope: S1 scene 条件块过滤（已 commit `2824ee59`）、S3 prompt assets/manifests 清理
- Parallel review coverage: 4 subagents（FMP resolver 正确性、scene_context 正确性、CLI wiring 与测试、架构边界）

## Findings

### 01-未修复-低-`_interactive_context_slot_values` 返回类型与其它 CLI command 不一致

- **入口/函数**: `dayu/cli/commands/interactive.py` `_interactive_context_slot_values`
- **文件(行号)**: `dayu/cli/commands/interactive.py:898`
- **输入场景**: 任何 interactive session 启动
- **实际分支**: 函数签名 `-> dict[str, str]`
- **预期行为**: 与 `prompt.py` (`-> dict[str, JsonValue]`) 和 `session.py` (`-> dict[str, JsonValue]`) 的返回类型注解保持一致
- **实际行为**: 返回 `dict[str, str]`。`str` 是 `JsonValue` 的子类型，运行时无错误，但类型注解不统一
- **直接证据**: `interactive.py:898` `def _interactive_context_slot_values() -> dict[str, str]:` vs `prompt.py:652` `def _prompt_context_slot_values(...) -> dict[str, JsonValue]:` vs `session.py:647` `def _session_context_slot_values() -> dict[str, JsonValue]:`
- **影响**: 仅影响代码一致性和未来扩展性。若 interactive 未来需要非字符串 context slot 值（如 `current_time`），返回类型需同步修改
- **建议改法和验证点**: 将 `-> dict[str, str]` 改为 `-> dict[str, JsonValue]`，import `JsonValue`；运行 pyright 确认
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-CLI adapter 层非法 ticker ValueError 传播无端到端测试

- **入口/函数**: `dayu/cli/commands/prompt.py` `_prompt_context_slot_values` -> `build_entrypoint_context_slot_values` -> `normalize_ticker`
- **文件(行号)**: `dayu/cli/commands/prompt.py:240-241`
- **输入场景**: 用户传入无法被 `normalize_ticker` 识别的 ticker（如 `"!@#$"`）
- **实际分支**: `normalize_ticker` 抛 `ValueError` -> `build_entrypoint_context_slot_values` 传播 -> `_prompt_context_slot_values` 传播 -> `prompt.py:240` 捕获为 `CliCommandUsageError`
- **预期行为**: CLI 返回 `EXIT_USAGE_ERROR` 并展示清晰错误消息
- **实际行为**: 代码路径正确，`prompt.py:240-241` 显式捕获 `ValueError` 并转为 `CliCommandUsageError`。但无 CLI 端到端测试覆盖此路径
- **直接证据**: `prompt.py:240-241` `except ValueError as exc: raise CliCommandUsageError(str(exc)) from exc`；`scene_context.py:154` `normalize_ticker(stripped_ticker).canonical` 会抛 `ValueError("无法识别的 ticker 形态: ...")`；所有 prompt 测试使用的 ticker 均为合法值（`" AAPL "`, `"V"`）
- **影响**: 若 `normalize_ticker` 的校验规则变化，CLI 层不会立即发现退化
- **建议改法和验证点**: 在 `tests/cli/test_prompt_command.py` 新增测试用非法 ticker 验证 `EXIT_USAGE_ERROR` 返回和错误消息不包含内部异常栈
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-手动构造 context_slot_values 的测试缺少 current_time key

- **入口/函数**: `tests/cli/test_prompt_command.py` 中 `test_prompt_sigint_after_run_id_cancels_host_run`、`test_prompt_sigint_before_run_id_returns_local_interrupt`、`_prepare_prompt_runtime`
- **文件(行号)**: `tests/cli/test_prompt_command.py:1300-1303`, `:1784-1786`, `:1883-1885`
- **输入场景**: 测试直接构造 `EntrypointRuntimeRequest` 而非通过 CLI 命令
- **实际分支**: 手动构造的 `context_slot_values` 只包含 `fins_default_subject` 和 `base_user`，不含 `current_time`
- **预期行为**: 测试 fixture 应与真实 CLI 路径生成的 slot values 结构一致
- **实际行为**: 当前 `prepare_entrypoint_runtime` 不校验 `current_time` key 存在性，测试通过。但与真实 CLI 路径存在隐性结构差异
- **直接证据**: `test_prompt_command.py:1300-1303` 手动构造 `{"fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。", "base_user": "本地 CLI 用户"}` 无 `current_time` key；真实 CLI 路径 `prompt.py:236-239` 通过 `build_entrypoint_context_slot_values` 生成含 `current_time` 的完整 slot values
- **影响**: 若未来 ScenePrepare 开始校验 `current_time` 的存在，这些测试需同步更新
- **建议改法和验证点**: 在 S3 统一 prompt assets/manifests 时一并更新这些手动构造的 fixture，或现在补充 `current_time` key
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。所有 subagent 提出的 open questions 已通过代码验证解答：
  - interactive scene manifest 是否要求 `fins_default_subject`？**已确认不要求。** `grep` 结果显示 `fins_default_subject` 只出现在 `prompt.json` manifest 中，`interactive.json` 不要求。
  - `normalize_ticker` 是否抛 `ValueError`？**已确认。** `dayu/fins/ticker_normalization.py:125` `raise ValueError(f"无法识别的 ticker 形态: {raw!r}")`。

## Residual Risk

1. **无真实 FMP 网络 smoke。** 自动测试使用 fake HTTP client 覆盖了 FMP resolver 的全部逻辑路径，但未验证真实 FMP API 的响应格式、网络延迟和认证行为。Plan 已将此分类为 optional smoke，不阻塞 S2。
2. **`base_user` 残留。** 三个 CLI command 仍硬编码 `DEFAULT_BASE_USER = "本地 CLI 用户"` 和 `CONTEXT_SLOT_BASE_USER = "base_user"`。当前 prompt/interactive/wechat manifest 仍要求此 slot。S3 将负责全局清理。
3. **`current_time` 生成但未被当前 prompt manifest 消费。** `build_entrypoint_context_slot_values` 总是生成 `current_time` slot，但当前 `prompt.json` manifest 的 scene `.md` 可能尚未包含 `{{current_time}}` placeholder。S3 将负责对齐 prompt assets/manifests。
4. **FMP resolver 第二跳（search-name）失败路径未被专项测试覆盖。** 当前测试只覆盖了 search-symbol 失败和整体 HTTP timeout，未单独测试 search-symbol 成功但 search-name 失败的场景。代码逻辑正确（`_fetch_search_results` 对两跳使用相同的错误处理），但测试覆盖有 gap。
