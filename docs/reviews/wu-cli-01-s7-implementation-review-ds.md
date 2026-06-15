# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-ui-implementation
- Base: HEAD (uncommitted changes + committed S7)
- Output file: docs/reviews/wu-cli-01-s7-implementation-review-ds.md
- Included scope:
  - `dayu/cli/commands/init.py` — 新增 init runner（主审查对象）
  - `dayu/cli/main.py` — init runner 分发接入
  - `tests/cli/test_init_command.py` — init 行为测试
  - `tests/cli/test_arg_parsing.py` — placeholder runner 测试迁移
  - `dayu/config/README.md` — init bootstrap 语义补充
  - `tests/README.md` — CLI init 测试覆盖记录
  - `docs/reviews/wu-cli-01-s7-implementation-codex.md` — Codex implementation report（核对用）
  - `docs/host/ui-implementation-control.md` — 仅核对 gate bookkeeping
- Excluded scope: S1-S6 accepted 范围；旧 provider interactive、旧 migrations、旧 llm_models.json / run.json 兼容（非目标，除非实现错误带回）
- Parallel review coverage: 无

## 审查方法

逐行走读了以下核心链路：

1. CLI 入口 → parser → runner 分发（`main.py:66-77`）
2. `run_init_command` 完整 try/except 退出码映射（`init.py:76-108`）
3. workspace root 解析 → 创建（`init.py:111-138`）
4. 配置资产收集 → 旧 schema 拦截 → 冲突检查 → 逐文件原子复制（`init.py:141-265`）
5. reset 白名单 → 预检（symlink + containment）→ 逐路径删除（`init.py:268-345`）
6. ConfigLoader 加载生成结果（`test_init_command.py:222-239`）
7. 各测试覆盖的 happy path、failure path、boundary condition

所有 finding 均基于直接代码路径证据；root cause 与触发输入、实际分支、返回值或副作用在同一条逻辑/数据路径上。

## Findings

### S7-RV-F01 [低] `_raise_if_legacy_asset_selected` 对子目录文件存在误伤风险

- **入口/函数**: `_raise_if_legacy_asset_selected` → `_collect_current_config_assets`
- **文件(行号)**: `dayu/cli/commands/init.py:208-221`
- **输入场景**: 包内 `dayu/config/prompts/` 的任意子目录下存在名为 `llm_models.json` 或 `run.json` 的文件（当前包内不存在，但未来若有人添加同名 prompt fragment 会触发）
- **实际分支**: `asset.destination.name in legacy_names` — 使用 `Path.name`（仅文件名）匹配，`prompts/scenes/run.json` 的 `.name` 为 `run.json`，命中 `legacy_config_file_names()` 返回的 `frozenset({"llm_models.json", "run.json"})`
- **预期行为**: 仅拦截顶层 `workspace/config/` 下的旧配置文件名，不应拦截子目录中的 prompt asset（例如 `prompts/scenes/run.json` 是合法的 prompt 文件名，与旧 `run.json` 语义完全不同）
- **实际行为**: 任意目录深度下文件名为 `llm_models.json` 或 `run.json` 都会被拒绝，init 报 `legacy config file must not be generated` 并 exit 1
- **直接证据**:
  - `init.py:218`: `if asset.destination.name in legacy_names:` — `.name` 只取最后一级文件名
  - `config_loader.py:26-28`: `_LEGACY_CONFIG_FILES = frozenset({"llm_models.json", "run.json"})`
  - 验证命令确认：`Path("workspace/config/prompts/scenes/run.json").name` → `"run.json"` ∈ legacy set
- **影响**: 当前包内 `prompts/` 下无同名文件，实际不受影响；但检查逻辑未按目录深度区分，未来若有人添加同名 prompt asset 会被误拦截，且错误消息未说明文件路径，排查困难
- **建议改法和验证点**:
  - 将检查限制为仅匹配顶层 config 目录下的文件：`asset.destination.parent == workspace_config_dir and asset.destination.name in legacy_names`，或显式在 docstring/注释中声明该检查适用于所有目录深度
  - 补充测试：在 prompts 子目录下放置同名文件，验证当前行为（固定当前行为为预期）
- **修复风险**: 低 — 仅缩小检查范围或补充文档，不改变正常路径行为
- **严重程度**: 低 — 当前无实际触发场景，属于防御逻辑的精确度问题

### S7-RV-F02 [低] `reset` 属性未在 `_new_default_namespace()` 中显式初始化

- **入口/函数**: `_new_default_namespace` → `parse_cli_args` → `run_init_command`
- **文件(行号)**: `dayu/cli/arg_parsing.py:229`（`overwrite` 初始化）vs 无对应 `reset` 初始化行
- **输入场景**: 若有代码直接构造 `ParsedCliArgs()` 并传入 `run_init_command`（不走 argparse），且该代码未显式设置 `args.reset`，访问 `args.reset` 会触发 `AttributeError`
- **实际分支**: `init.py:87`: `if args.reset:` — 依赖 argparse `store_true` 的隐式默认值 `False`；不走 argparse 时该属性不存在
- **预期行为**: `reset` 与 `overwrite` 同为 `store_true` 布尔标志，应具有一致的初始化策略
- **实际行为**: `overwrite` 在 `_new_default_namespace()` 第 229 行显式设为 `False`，`reset` 未初始化，仅靠 argparse `store_true` 隐式默认
- **直接证据**:
  - `arg_parsing.py:229`: `namespace.overwrite = False`
  - `arg_parsing.py:193-248`: `_new_default_namespace()` 全文搜索，`reset` 字符串仅在 `argparse.SUPPRESS` 列表中出现（属于其他字段），无 `namespace.reset` 赋值
  - `arg_parsing.py:359`: `parser.add_argument("--reset", action="store_true", ...)` — 无显式 `default`
- **影响**: 生产路径始终经过 argparse 解析，`store_true` 隐式默认 `False` 不会触发；但若未来测试或内部调用直接构造 `ParsedCliArgs`，可能遇到意外 `AttributeError`
- **建议改法和验证点**: 在 `_new_default_namespace()` 中增加 `namespace.reset = False`，与 `overwrite` 初始化对齐
- **修复风险**: 低 — 单行显式默认值赋值，不影响 argparse 行为（argparse 会覆盖为命令行实际值）
- **严重程度**: 低 — 生产路径不受影响，属于防御性初始化一致性问题

### S7-RV-F03 [低] `_raise_for_existing_assets` 与 `_copy_file_atomic` 对"目标父路径为普通文件"场景无前置检查

- **入口/函数**: `_copy_file_atomic` → `_copy_current_config_assets`
- **文件(行号)**: `dayu/cli/commands/init.py:255` (`destination.parent.mkdir`)
- **输入场景**: `workspace/config` 本身是一个普通文件（而非目录），例如用户此前意外创建了名为 `config` 的文件
- **实际分支**: `_raise_for_existing_assets` 仅检查各 asset 的 `destination` 是否是目录（`init.py:236-239`），未检查 `workspace/config/`（asset 的 parent）是否是文件；`_copy_file_atomic:255` 执行 `destination.parent.mkdir(parents=True, exist_ok=True)` 时，`exist_ok=True` 不会因父路径是文件而报错，但后续 `shutil.copy2` 在尝试写入 `workspace/config/models.json` 时会因父路径是文件而失败
- **预期行为**: 在复制开始前检测 `workspace/config` 是否是普通文件，给出清晰的错误消息
- **实际行为**: 错误延迟到 `_copy_file_atomic` 的 `OSError`（`NotADirectoryError` 或类似），被 `run_init_command:106-108` 捕获为通用 `_COPY_FAILURE_TEMPLATE`，消息为 `dayu-cli init: failed to copy config asset: [Errno 20] Not a directory: ...`
- **直接证据**:
  - `init.py:236-239`: `_raise_for_existing_assets` 检查 `asset.destination.is_dir()` 而非 `asset.destination.parent`
  - `init.py:255`: `destination.parent.mkdir(parents=True, exist_ok=True)` — `exist_ok=True` 不检查父路径是否为非目录文件
- **影响**: 错误消息对用户不够清晰——用户看到"failed to copy config asset"而非"workspace/config exists but is a file, not a directory"。实际触发概率极低
- **建议改法和验证点**: 在 `_ensure_workspace_root` 后或 `_copy_current_config_assets` 入口处增加 `workspace_config_dir` 路径检查：若存在且非目录，提前 fail fast 并给出明确错误
- **修复风险**: 低 — 新增前置检查，不改变正常路径行为
- **严重程度**: 低 — 极端 corner case，错误最终仍会被捕获并返回退出码 1，只是错误消息不够精确

## Open Questions

无。

## Residual Risk

1. **部分复制状态残留**: `_copy_current_config_assets` 中文件逐个复制，非目录级事务。SIGINT 在复制中途到达时，已通过 `os.replace` 完成的文件会留在 workspace 中，后续文件未复制。`run_init_command` 正确返回 130 且不输出成功消息，符合 S7 cancel 要求。此风险已在 Codex report 中记录，当前设计接受。

2. **reset TOCTOU**: `_validate_reset_whitelist_paths` 预检全部路径 → 逐路径 `_delete_reset_path` 之间存在 TOCTOU 窗口。在此期间若外部进程将已通过检查的路径替换为 symlink，`shutil.rmtree` 不会跟随 symlink（Python 3.11 默认行为），实际不会造成数据泄露。此窗口在 CLI 单用户场景下不构成实际威胁。

3. **`_copy_file_atomic` 临时文件残留**: 若进程在 `temp_path.unlink()` 执行前被 SIGKILL（非 SIGINT），临时文件 `.dayu-init-<uuid>-<filename>` 会残留在目标目录中。这些文件前缀固定，可被用户手动识别和清理；不影响 `ConfigLoader`（只读取已知配置文件名）。当前设计无后台清理机制，属于可接受的 SIGKILL 残留。

4. **测试覆盖缺口**:
   - `_resolve_workspace_root` 空字符串分支（`init.py:120-121`）无直接单测；通过 argparse 的 required subcommand 机制间接保护
   - `_ensure_workspace_root` 的 `OSError` → `CliInitUsageError` 转换路径（`init.py:135-136`）无直接单测
   - `_collect_current_config_assets` 的缺失 `prompts/` 目录（`init.py:192-193`）和缺失包内配置文件（`init.py:183-184`）无直接单测
   - `_delete_reset_path` 的文件删除分支（`init.py:345` `path.unlink()`）无直接单测（当前测试只覆盖目录删除）
   - 以上均为错误路径/边界条件，覆盖率 88% ≥ 80% 阈值，且这些路径在生产中行为正确（通过代码走读确认），不阻塞 merge

5. **`_normalize_system_exit_code` 未覆盖分支**（`main.py:94,97`）: `code is None`（返回 0）和 `isinstance(code, int)` 为 False 的 fallback 路径无单测。当前 `main.py` 覆盖率 95% ≥ 80%，这两个分支对应 argparse `SystemExit(0)`（help 正常退出）和非整数退出码（极端罕见），不影响 merge。
