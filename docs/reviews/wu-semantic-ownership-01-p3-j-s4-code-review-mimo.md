# WU-SEMANTIC-OWNERSHIP-01 P3-J S4 Code Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `7eb3c339`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-code-review-mimo.md`
- Included scope: `dayu/runtime/config_loader.py`, `dayu/cli/commands/init.py`, `tests/runtime/test_config_loader.py`, `tests/cli/test_init_command.py` 相对 base `7eb3c339` 的未提交 diff
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md` 以及其它 untracked files
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项确认：

### 1. runtime.config_loader legacy exposure 彻底移除

- `dayu/runtime/config_loader.py` 删除了 `_LEGACY_CONFIG_FILES` 常量（原 L27-29）和 `legacy_config_file_names()` 公共函数（原 L893-903）。
- `config_file_names()` 保留为当前 schema 文件名的唯一 runtime 真源。
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests` 返回零匹配，无残留引用、兼容 wrapper 或 re-export。
- `dayu/runtime/__init__.py` 无 legacy 符号导出。
- **结论**：runtime 层不再持有旧配置文件名的任何语义。

### 2. CLI init guard owner 正确性

- `dayu/cli/commands/init.py` 将旧文件名集合收为 CLI 私有 `_LEGACY_CONFIG_FILE_NAMES`（L32-34），不通过 runtime import。
- guard 函数 `_raise_if_legacy_top_level_config_asset_selected`（L211-229）通过 `asset.destination.parent == workspace_config_dir` 限制只拦截顶层 config 目录直接子文件。
- 验证：`prompts/scenes/run.json` 的 `destination.parent` 为 `config/prompts/scenes`，不等于 `workspace_config_dir`，故不被拦截。
- **结论**：guard 只限制 top-level copied config assets，不误伤 prompts 子资产。Owner 归属 CLI init 命令，符合 plan S4。

### 3. 无 production caller 依赖旧 helper

- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests` 零匹配。
- `rg -n 'from dayu.runtime.config_loader import.*legacy' dayu tests` 零匹配。
- `dayu/cli/commands/init.py` 仅 import `config_file_names`。
- 剩余 `llm_models.json` / `run.json` 引用仅出现在：CLI 私有 guard 常量、测试负向断言、`dayu/config/README.md` 删除说明、Engine 历史 docstring，均非 runtime public exposure。
- **结论**：无 production caller outside CLI 仍依赖旧 helper。

### 4. tests 行为证明

- `tests/runtime/test_config_loader.py`：删除 `legacy_config_file_names` import，使用本地 `_REMOVED_CONFIG_FILE_NAMES` 常量做负向断言（L27, L804-810）。`test_legacy_files_do_not_exist_and_are_not_read` 证明旧 workspace 文件不被读取，且断言 `file_name not in current_file_names` 直接验证 `config_file_names()` 不包含旧名。
- `tests/cli/test_init_command.py`：
  - `test_init_does_not_generate_legacy_config_files`（L265-282）证明 init 不生成旧文件。
  - `test_init_rejects_legacy_top_level_config_asset`（L285-322）通过 monkeypatch `config_file_names` 注入旧名，验证 guard 在顶层 config 资产被污染时 fail fast。
  - `test_init_allows_prompt_asset_with_removed_config_file_name`（L325-344）验证 prompt 子目录下同名文件不被拦截。
  - `_write_minimal_current_config_assets` 辅助函数仅写入 `config_file_names()` 返回的当前 schema 文件。
- **结论**：tests 证明 current schema 行为和 CLI guard，未通过 runtime public legacy helper 固化旧 owner。

### 5. README / 分层 / 类型 / docstring 合规

- `dayu/config/README.md`：已读取，L15 和 L46 明确记录旧文件删除且不提供兼容读取路径，无需更新。
- Root `README.md`：用户可见 init 行为未变（不生成旧文件），无需更新。
- `tests/README.md`：测试命令组未变，无需更新。
- 类型：`_LEGACY_CONFIG_FILE_NAMES: Final[frozenset[str]]`，`_raise_if_legacy_top_level_config_asset_selected(*, assets: Sequence[_CopyAsset], workspace_config_dir: Path) -> None`，签名完整。
- docstring：guard 函数有完整中文 docstring，含参数、返回值、异常说明。
- 分层：CLI init 不 import runtime 以外模块；runtime 不 import CLI。guard 职责正确归属 CLI。
- 无兼容读取/迁移：loader 仅读取 `config_file_names()` 定义的当前 schema 文件。
- **结论**：符合 AGENTS.md 和 plan S4。

## Open Questions

无。

## Residual Risk

- `dayu/engine/contracts/runner_spec.py:32` 仍有历史 docstring 提及 `llm_models.json`，非 runtime config exposure，不影响 S4 owner boundary。
- `tests/engine/test_smoke_async_agent_providers.py:167` 和 `tests/engine/test_config_models.py:37` 保留旧名断言作为 Engine 迁移负向覆盖，不在 S4 scope。

## Verification

- `pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q`：66 passed, 3 warnings。
- `pyright dayu/runtime/config_loader.py dayu/cli/commands/init.py tests/runtime/test_config_loader.py tests/cli/test_init_command.py`：0 errors, 0 warnings。
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests`：无匹配。
