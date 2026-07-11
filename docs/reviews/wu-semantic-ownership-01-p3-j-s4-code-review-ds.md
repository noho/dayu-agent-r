# WU-SEMANTIC-OWNERSHIP-01 P3-J S4 Code Review — AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `7eb3c339`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-code-review-ds.md`
- Included scope:
  - `dayu/runtime/config_loader.py`
  - `dayu/cli/commands/init.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/cli/test_init_command.py`
- Excluded scope:
  - `AGENTS.md`, `CLAUDE.md`
  - `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`
  - `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
  - Historical review artifacts not part of this work unit
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md` S4
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s4-controller-validation.md`
- Parallel review coverage: 无

## Review Method

逐文件完整 diff 走读，覆盖 5 个重点 review 方向：

1. runtime.config_loader 是否彻底移除 legacy_config_file_names() / _LEGACY_CONFIG_FILES public exposure
2. CLI init 私有 guard 是否 owner 正确
3. production caller outside CLI 是否仍依赖旧 helper
4. tests 是否证明 current schema 行为
5. README decision、分层、类型、docstring、无兼容读取/迁移

对每条变更路径执行了 adversarial failure pass：检查了 guard 边界条件、test fixture 覆盖、re-export 风险、pyright 类型安全，以及是否残留兼容 wrapper。

## Findings

### 逐项 Review 结论

#### 1. runtime.config_loader — legacy exposure 移除

**入口/函数**: `dayu/runtime/config_loader.py` 模块级常量与 public API surface
**文件(行号)**: 原 `config_loader.py:27-29` (`_LEGACY_CONFIG_FILES`)、原 `config_loader.py:896-903` (`legacy_config_file_names()`)
**直接证据**:

- `_LEGACY_CONFIG_FILES` 常量已从模块中彻底删除。diff 确认行 27-29（原定义）被移除。
- `legacy_config_file_names()` public 函数已彻底删除。diff 确认行 896-903（原函数体）被移除。
- Source scan：`rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu/ --include '*.py'` 返回 exit code 2（无匹配），production code 零残留。
- `dayu/runtime/__init__.py` 的 `__all__` 为空列表，包根不做 re-export。不存在兼容 wrapper 或兼容 re-export。
- `config_file_names()` 作为当前 schema 唯一 public 文件名 helper 保持不变。
- pyright: `0 errors, 0 warnings, 0 informations`。

**结论**: 符合 plan 3.7 节要求。runtime 不再拥有旧文件名的 public owner。✅

#### 2. CLI init 私有 guard — owner 正确性

**入口/函数**: `dayu/cli/commands/init.py` `_raise_if_legacy_top_level_config_asset_selected()`
**文件(行号)**: `init.py:32-34`（常量）、`init.py:211-229`（guard 函数）
**直接证据**:

- CLI 模块内新增私有常量 `_LEGACY_CONFIG_FILE_NAMES: Final[frozenset[str]]`（行 32-34），不再从 runtime import。
- Guard 函数签名为 `_raise_if_legacy_top_level_config_asset_selected(*, assets, workspace_config_dir)`，增加 `workspace_config_dir` 参数。
- Guard 条件从旧版 `asset.destination.name in legacy_names`（任意位置的旧文件名均拒绝）改为 `asset.destination.parent == workspace_config_dir AND asset.destination.name in _LEGACY_CONFIG_FILE_NAMES`（仅顶层 workspace config 目录下的旧文件名被拒绝）。
- 测试 `test_init_allows_prompt_asset_with_removed_config_file_name`（`tests/cli/test_init_command.py:325-344`）证明 `prompts/scenes/run.json` 不会被拦截 — guard 不误伤 prompt 子资产。
- 测试 `test_init_rejects_legacy_top_level_config_asset`（`tests/cli/test_init_command.py:285-322`）证明顶层 `llm_models.json` 被拦截 — guard 对顶层 config asset 仍 fail-closed。
- Guard 命名 `_raise_if_legacy_top_level_config_asset_selected` 明确语义边界：只对顶层 config asset 生效。
- Chinese docstring 完整：`param` / `returns` / `raises` 齐全。

**结论**: 符合 plan 3.7 节 "The CLI init asset copier owns that defensive guard, not ConfigLoader's public API" 及 "It must not create a broad prompt-asset filename ban" 要求。✅

#### 3. production caller outside CLI — 无残留依赖

**入口/函数**: 全 production code 扫描
**直接证据**:

- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu/ --include '*.py'` → exit code 2（零匹配），production code 中无任何对已删除函数的引用。
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' tests/ --include '*.py'` → exit code 2（零匹配），tests 中无任何对已删除函数的 import。
- 实现 artifact 记录的 broader scan（`dayu/engine/contracts/runner_spec.py`、`tests/engine/test_smoke_async_agent_providers.py`、`tests/engine/test_config_models.py`）中的 `llm_models.json` / `run.json` 引用均为历史 docstring 注释或 Engine config migration 断言，不调用 `legacy_config_file_names()`，不在 S4 scope 内。
- `dayu/config/README.md` 中的旧文件名引用是文档记录（声明已删除且不做兼容读取），不是运行时依赖。

**结论**: 无 production caller outside CLI 依赖已删除的 runtime helper。✅

#### 4. tests — 证明 current schema 行为，不固化旧 owner

**入口/函数**: 两个测试模块
**文件(行号)**: `tests/runtime/test_config_loader.py:26-28`、`tests/cli/test_init_command.py:23-25`
**直接证据**:

- 两个测试模块各定义 test-local `_REMOVED_CONFIG_FILE_NAMES` 常量，不从 runtime import 旧 helper。不再通过 runtime public legacy helper 获取旧文件名。
- `test_legacy_files_do_not_exist_and_are_not_read`（`tests/runtime/test_config_loader.py:797-810`）从仅调用 `legacy_config_file_names()` 升级为双重验证：
  1. `assert file_name not in current_file_names`（确认旧名不在 `config_file_names()` 中 — 这是 current schema 行为证明）
  2. `assert not (Path("dayu/config") / file_name).exists()`（确认包内旧文件不存在）
  3. 核心改进：在 workspace 中放置无效 JSON 的旧文件后调用 `load_runtime_config()` 成功，直接证明 ConfigLoader 不读取旧文件，而不是仅依赖一个被删除的 public helper 做间接断言。
- `test_init_empty_workspace_copies_current_config`（`tests/cli/test_init_command.py:28-52`）同时验证 current schema 文件被生成 AND 旧文件不被生成，使用 `config_file_names()` + test-local `_REMOVED_CONFIG_FILE_NAMES`。
- `test_init_rejects_legacy_top_level_config_asset`（`tests/cli/test_init_command.py:285-322`）是新测试，通过 monkeypatch `config_file_names()` 模拟未来回归场景，证明 guard 的行为而非仅测试当前配置快照。
- `test_init_allows_prompt_asset_with_removed_config_file_name`（`tests/cli/test_init_command.py:325-344`）是新测试，证明 guard 的边界精确性。

**结论**: tests 证明了 current schema 行为和 CLI guard 的正确性，不再通过 runtime public legacy helper 固化旧 owner。✅

#### 5. README decision、分层、类型、docstring、无兼容读取/迁移

**直接证据**:

- README decision：实现 artifact 记录 `dayu/config/README.md` 已声明旧文件删除且不做兼容读取 — 无需更新。Root `README.md` 无用户可见行为变更 — 无需更新。`tests/README.md` 无测试命令指南变更 — 无需更新。符合 plan 7 节 README check 预期。✅
- 分层：runtime 不再拥有旧配置文件名语义；CLI 拥有自己的 init asset guard。分层边界清晰，无反向依赖。✅
- 类型：`_LEGACY_CONFIG_FILE_NAMES` 在 CLI init 中标记为 `Final[frozenset[str]]`。所有新增/修改函数的参数均使用 keyword-only 严格类型注解。✅
- docstring：`_raise_if_legacy_top_level_config_asset_selected` 提供完整中文 docstring（param/assets、param/workspace_config_dir、returns、raises）。测试函数均提供中文 docstring 含 param/returns/raises。✅
- 无兼容读取/迁移：无旧 DB 兼容读取、无 workspace migration、无兼容 wrapper 或 re-export、无 `hasattr`/`getattr` 规避类型边界。✅

### 综合评估

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `tests/cli/test_init_command.py:23` 的 `_REMOVED_CONFIG_FILE_NAMES` 缺少 `Final` 标注（与 `tests/runtime/test_config_loader.py:26` 不一致），属于极轻微风格不一致，不影响正确性。不建议为此增加修复轮次。
- `dayu/engine/contracts/runner_spec.py` 与 `tests/engine/` 中两个文件的 `llm_models.json` 历史引用不在 S4 scope 内，是 Engine config migration 的历史文档/测试残留，不影响 runtime config loader public API surface。
- 当前 CLI guard 仅保护 `dayu-cli init` 路径。若未来有其他路径直接将旧 config 文件写入 workspace，ConfigLoader 不会读取它们（因为只读 `config_file_names()`），但不会主动拒绝写入。这属于 defense-in-depth 而非当前缺陷。
