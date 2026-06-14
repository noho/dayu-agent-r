# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-ui-implementation`
- Base: `main`（未提交 workspace changes + branch commits）
- Output file: `docs/reviews/wu-cli-01-s7-implementation-review-mimo.md`
- Included scope:
  - `dayu/cli/commands/init.py`（新增）
  - `dayu/cli/main.py`（修改：接入 init runner）
  - `tests/cli/test_init_command.py`（新增）
  - `tests/cli/test_arg_parsing.py`（修改：占位 test 改用 synthetic future command）
  - `dayu/config/README.md`（修改：补充 init 语义）
  - `tests/README.md`（修改：补充 init 测试覆盖面）
  - `docs/reviews/wu-cli-01-s7-implementation-codex.md`（implementation report）
  - `docs/host/ui-implementation-control.md`（gate bookkeeping 更新）
- Excluded scope: S1–S6 已 accepted 范围
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下逐项审查结论：

### Reset data-loss 风险

白名单硬编码为 4 个路径（`init.py:300-305`）：`config/`、`.dayu/host/`、`.dayu/artifacts/`、`.dayu/web_tools_storage_states/`。不在白名单内的路径（runtime sqlite、Fins 数据、用户文件）不会被删除。测试 `test_init_reset_only_deletes_hardcoded_whitelist`（`test_init_command.py:102-156`）显式确认以下路径保留：`runtime_lanes.sqlite3`、`fins_ingestion/jobs/`、`sec_cache/`、`fins/`、`workspace/fins/`、普通用户文件。白名单构造使用纯字符串目录名拼接，不含 `..` 或用户输入，无法通过参数注入扩展。

### 路径 containment 与 symlink 处理

`_validate_reset_whitelist_paths`（`init.py:308-331`）对每个白名单路径执行两项检查：

1. `path.is_symlink()`：检测路径本身是否为 symlink。对不存在的路径返回 `False`（已验证），不影响正常跳过逻辑。
2. `resolved_path.relative_to(resolved_workspace)`：`resolve(strict=False)` 跟踪所有 symlink 层级，确保最终路径在 workspace 内。

两个测试覆盖直接 symlink 逃逸（`test_init_reset_symlink_escape_fails_fast_without_deleting`）和父目录 symlink 逃逸（`test_init_reset_parent_symlink_containment_escape_fails_fast`），且均验证失败时未执行任何删除。

TOCTOU 风险：验证与删除之间无用户交互或 I/O 等待，窗口极窄，当前 CLI 单线程场景下不可利用。

### 旧 schema 是否可能生成

`_collect_current_config_assets`（`init.py:167-205`）从 `config_file_names()`（返回 5 个当前 JSON 文件）和 `prompts/` 目录收集资产。`_raise_if_legacy_asset_selected`（`init.py:208-221`）在复制前检查目标文件名是否落入 `legacy_config_file_names()`（`{"llm_models.json", "run.json"}`），命中则 fail fast。测试 `test_init_does_not_generate_legacy_config_files` 直接验证。

当前 `dayu/config/` 目录不含 `llm_models.json` 或 `run.json`，因此 `_raise_if_legacy_asset_selected` 是防御性检查，正常路径不会触发。该防御仍有必要：若未来有人误将旧文件加入 `config/` 目录，init 会阻止其进入 workspace。

### ConfigLoader 是否能加载生成结果

测试 `test_init_generated_workspace_config_loads_with_config_loader`（`test_init_command.py:222-239`）验证 init 生成的 workspace config 可被 `ConfigLoader().load(workspace_config_dir=...)` 加载，且 `models`、`execution_profiles`、`host_runtime` 字段非空。

### CLI 到 runner 分发

`main.py:46` 将 `COMMAND_INIT` 映射到 `run_init_command`，与 `COMMAND_INTERACTIVE`、`COMMAND_PROMPT` 等同级注册。`init` 之前使用 `run_not_implemented_command` 占位，S7 替换为真实 runner。`test_arg_parsing.py` 的 `test_placeholder_runner_returns_not_implemented` 已从使用 `init` 改为 synthetic `future_command`，避免与真实实现冲突。

### README 触发边界

- `dayu/config/README.md`：新增段落说明 `dayu-cli init` 的当前 schema bootstrap 语义。触发条件为 `dayu/config/` 修改，但 init 实现在 `dayu/cli/commands/init.py`，对 config 目录有行为依赖。新增内容限于 config 层职责范围内的 `init` 行为描述，未越界。✅
- `tests/README.md`：新增 init 测试覆盖面描述。触发条件为 `tests/` 修改。✅

### 测试覆盖真实风险

测试矩阵：

| 测试 | 覆盖风险 |
|---|---|
| `test_init_empty_workspace_copies_current_config` | happy path：空 workspace bootstrap |
| `test_init_existing_files_without_overwrite_fails` | 覆盖保护：已有文件默认拒绝 |
| `test_init_overwrite_replaces_existing_config_file` | `--overwrite` 替换语义 |
| `test_init_reset_only_deletes_hardcoded_whitelist` | reset 白名单边界 + 禁删路径保留 |
| `test_init_reset_symlink_escape_fails_fast_without_deleting` | symlink 逃逸 fail fast |
| `test_init_reset_parent_symlink_containment_escape_fails_fast` | 父目录 symlink 逃逸 fail fast |
| `test_init_generated_workspace_config_loads_with_config_loader` | 生成结果可被 ConfigLoader 加载 |
| `test_init_does_not_generate_legacy_config_files` | 旧 schema 不生成 |
| `test_init_sigint_maps_to_130` | SIGINT 退出码 130 |

覆盖率：`init.py` 88%，`main.py` 95%（来自 codex report）。

未覆盖的边界：
- reset 过程中 SIGINT（当前只测试复制阶段 SIGINT）。
- 部分 reset 后的 workspace 状态一致性。

这些是低风险残余：reset 删除的是可重建路径（config + .dayu 子目录），即使部分删除后中断，再次 `init --reset --overwrite` 可恢复。

## Open Questions

无。

## Residual Risk

- reset 过程中 SIGINT 可能导致白名单路径部分删除、部分保留。由于删除的都是可重建路径，再次 `init --reset --overwrite` 可恢复，风险低。
- 复制是逐文件原子替换，不是目录级事务。SIGINT 可能导致部分文件已替换、部分未替换。codex report 已记录此行为符合当前 slice cancel 要求。
