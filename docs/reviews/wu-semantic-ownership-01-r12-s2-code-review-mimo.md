# R12 S2 Cumulative Complete Code Review — AgentMiMo

## Scope

- Mode: cumulative 14-path target (controller-fixed)
- Branch: `phaseflow/host-issues-control`
- Base: HEAD `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-mimo.md`
- Included scope: 14 个 controller validation 固定的 cumulative target 路径（7 production + 7 test）
- Excluded scope: control/review artifacts、plan、design docs、package JSON/manifests、Host/Engine/Fins/Tool production、S3-only paths
- Parallel review coverage: 无

## Findings

### 01-未修复-中-init_workspace 1618 行模块是否违反 God function 约束

- **入口/函数**: `dayu/cli/init_workspace.py` 整体模块
- **文件(行号)**: `dayu/cli/init_workspace.py:1-1618`
- **输入场景**: 任何 init workspace transaction
- **实际分支**: 单一模块承载 snapshot、四态、staging、validation、discovery、cleanup、publish、rollback、durability 共 30+ 个函数
- **预期行为**: AGENTS.md 禁止 God function/God object；函数职责应收敛
- **实际行为**: 模块为 1618 行，但内部分为清晰的公共 API（5 个导出函数）+ 私有 helper（~25 个），每个函数均 < 100 行、单一职责、中文 docstring 完整。核心状态机通过 typed dataclass 表达（`WorkspaceTransactionRequest`、`PreparedWorkspaceTransaction`、`WorkspaceTransactionResult`、`WorkspaceCleanupWarning`），不靠布尔标记驱动
- **直接证据**: 公共 API 为 `snapshot_managed_roots`、`determine_init_mode`、`prepare_workspace_transaction`、`abort_prepared_workspace_transaction`、`publish_workspace_transaction`；`__all__` 只导出这五个。每个私有 helper 有明确的 stage 参数用于 diagnostic
- **影响**: 1618 行模块不是 God function，因为 (1) 公共 API 只有 5 个，(2) 私有 helper 通过 typed request/result 传参、不共享可变状态，(3) 每个函数有单一 transaction stage 职责。唯一可质疑的是模块行数较多，但按 transaction lifecycle 分为 snapshot/staging/validation/publication/rollback/cleanup 六个阶段，函数边界清晰
- **建议改法和验证点**: 当前结构可接受；若后续继续膨胀可考虑按 transaction lifecycle 阶段拆分子模块，但 R12 范围内不必要
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（观察项，非 defect）

### 02-未修复-低-四态 snapshot/rename-after-effect/rollback/cleanup 状态可证性

- **入口/函数**: `publish_workspace_transaction`、`_rollback_or_raise`、`_cleanup_private_path`
- **文件(行号)**: `dayu/cli/init_workspace.py:570-743`（publish）、`1014-1104`（rollback）、`1252-1363`（cleanup）
- **输入场景**: backup move 后 `os.replace` 抛错、cleanup 中 quarantine identity 漂移、KeyboardInterrupt 在 publication boundary 前后
- **实际分支**: rename-after-effect 路径在 `os.replace` 调用后抛 `OSError`/`KeyboardInterrupt` 时检查源消失 + 目标存在 + identity 匹配，然后记录 backup record
- **预期行为**: 任何 rename 后异常必须如实记录已生效的 move，并在 rollback 中逆序恢复
- **实际行为**:
  - `publish_workspace_transaction:614-624`：backup move 的 `os.replace` 抛错后检查 `_path_exists_no_follow(source)=False` and `_path_exists_no_follow(dest)=True` and identity match，然后 append backup record 并 re-raise
  - `_rollback_or_raise:1040-1060`：逆序遍历 backup_records，先复核 backup identity 再 `os.replace(backup, original)`
  - `_cleanup_private_path:1296-1323`：quarantine `os.replace` 后检查 rename-after-effect，identity match 时抛 `InitWorkspaceError` 而非 `OSError`
- **直接证据**: 三处 rename-after-effect 检查都基于 `_path_identity` 精确比较，不靠文件名猜测
- **影响**: 状态可证性满足；每个 rename boundary 都有 identity 对账
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 03-未修复-低-KeyboardInterrupt 在 publication boundary 前后的区分

- **入口/函数**: `publish_workspace_transaction`
- **文件(行号)**: `dayu/cli/init_workspace.py:570-743`
- **输入场景**: 用户在 backup move、config replace 或 POSIX sync 期间发送 SIGINT
- **实际分支**: `KeyboardInterrupt` 被三个独立 except 块捕获：backup move 阶段（616-624）、config replace 阶段（644-655）、POSIX sync 阶段（668-669）；每个都先检查 rename-after-effect 再调用 `_rollback_or_raise`
- **预期行为**: KeyboardInterrupt 在 boundary 前必须触发完整 rollback；boundary 后（cleanup 阶段）只 warning
- **实际行为**:
  - boundary 前的 `KeyboardInterrupt`（backup/config replace/sync）→ `_rollback_or_raise` + `abort_prepared_workspace_transaction` + re-raise
  - boundary 后的 cleanup `KeyboardInterrupt`（724-736）→ `WorkspaceCleanupWarning`，不 rollback
  - boundary 判定逻辑：`published_config=True` + POSIX `_sync_directory` 成功 → 越过 boundary
- **直接证据**: line 668-669 POSIX sync 成功后才越过 boundary；line 703 开始的 cleanup loop 是 boundary 后
- **影响**: 正确区分了 boundary 前后的 KeyboardInterrupt 处理
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 04-未修复-低-Symlink/reparse 拒绝与 durability truth

- **入口/函数**: `_validate_ordinary_tree`、`_require_ordinary_directory`、`_cleanup_private_path`
- **文件(行号)**: `dayu/cli/init_workspace.py:1441-1516`
- **输入场景**: managed tree 中出现 symlink、Windows reparse point、special file
- **实际分支**: `_validate_ordinary_tree` 用 `os.scandir` + no-follow identity 逐 entry 检查；`_require_ordinary_directory` 用 `stat.S_ISLNK` + Windows `FILE_ATTRIBUTE_REPARSE_POINT` 检查
- **预期行为**: symlink/reparse point 必须在 mutation 前拒绝
- **实际行为**: POSIX `S_ISLNK` 和 Windows `FILE_ATTRIBUTE_REPARSE_POINT` 都有独立检查；`shutil.rmtree` 只在 `avoids_symlink_attacks is True` 时使用
- **直接证据**: line 1463 检查 `identity.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`；line 1343 检查 `shutil.rmtree.avoids_symlink_attacks is True`
- **影响**: 安全边界满足
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 05-未修复-中-Service Fins override raw grammar 与 ordinary None/非 Fins/Web 隔离

- **入口/函数**: `assemble_effective_tool_provider_configs`、`_effective_fins_workspace_root_config_value`
- **文件(行号)**: `dayu/service/host_assembly.py:529-560`（公共入口）、`1471-1525`（Fins root 解析）
- **输入场景**: R12 init validation 传入 `fins_workspace_root_override=<private_validation_root>`；ordinary runtime 传 `None`；非 Fins provider 传任何值
- **实际分支**:
  - `_effective_fins_workspace_root_config_value:1489-1503`：先校验 raw `configured_workspace_root` 的 type/non-empty grammar，再检查 override
  - override 非 `None` 时 line 1496-1503：expanduser → is_absolute 检查 → resolve → return
  - override 为 `None` 且 raw 为 `None` 时：返回 `workspace_root` 或 `None`
  - `_is_fins_workspace_bound_provider_config` 只匹配 Fins provider id/import path/source id，非 Fins provider 不进入此分支
- **预期行为**: raw grammar 总是先校验；override 只支配 Fins effective root；ordinary runtime 显式 `None`；非 Fins/Web 不消费 override
- **实际行为**:
  - `entrypoint_runtime.py:517` 显式传 `fins_workspace_root_override=None`
  - override 不改写 `provider_config.config`（raw mapping），只影响返回的 effective string
  - Web `playwright_storage_state_dir` 在 `_effective_tool_provider_config` 的另一分支处理，不经过 Fins override 路径
  - 非 Fins provider 不匹配 `_is_fins_workspace_bound_provider_config`，不进入 override 路径
- **直接证据**: `host_assembly.py:1489-1503` 中 raw grammar 校验在 override 检查之前；`entrypoint_runtime.py:517` 显式 `None`
- **影响**: 实现满足设计约束；raw bytes 不变、override 只支配 Fins root、非 Fins/Web 不消费
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 06-未修复-中-是否偷带统一 authorization

- **入口/函数**: 全部 S2 production 文件
- **文件(行号)**: `dayu/cli/init_workspace.py`、`dayu/cli/commands/init.py`、`dayu/cli/arg_parsing.py`、`dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`
- **输入场景**: 任意 init 或 Service 代码路径
- **实际分支**: `rg -n "authorization|authorisation|tool[_ -]?auth|permission" dayu/cli tests/cli` 在 S2 production 中零匹配
- **预期行为**: S2 不得引入统一 tool authorization framework
- **实际行为**: production 中无 authorization 相关字符串；host_context.py 的 `authorization_claims=()` 是既有 Host 接口，不在 S2 修改范围内
- **直接证据**: grep scan 零匹配
- **影响**: 无统一 authorization 泄漏
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 07-未修复-中-test_prompt_command_uses_init_generated_workspace_config 无交互 init 失败

- **入口/函数**: `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`
- **文件(行号)**: `tests/cli/test_prompt_command.py:1196-1247`
- **输入场景**: 第 1211 行 `cli_main.main(("init", "--base", str(workspace_root)))` 不提供 stdin 输入
- **实际分支**: 当前 init 需要交互式模型选择（`_select_model()` 调用 `input()`），无 stdin 时 EOF 触发 `CliInitOperationError`
- **预期行为**: 该测试属于 S3 test/workflow migration，不应通过 S2 production implicit default/compat fallback 修复
- **实际行为**: 测试在 S2 focused regression 中被排除（implementation handoff §6.1 不包含 `test_prompt_command.py`）；手off §9.6 第 6 项明确记录此分类
- **直接证据**: `test_prompt_command.py:1211` 调用 init 不传 stdin；implementation handoff §9.6 将其分类为 S3
- **影响**: S3 必须处理此测试迁移；S2 不应为此恢复隐式默认选择
- **建议改法和验证点**: S3 时需要 (a) 修改测试提供 mock stdin，或 (b) 添加 test fixture 让 init 路径支持非交互模式。禁止在 S2 production 添加 implicit default
- **修复风险（低/中/高）**: 中（S3 scope）
- **严重程度（低/中/高/严重）**: 中（S3 mandatory entry residual）

### 08-未修复-中-是否存在同类 stale caller

- **入口/函数**: `tests/cli/test_prompt_command.py` 及其它测试
- **文件(行号)**: `tests/cli/test_prompt_command.py:1196-1247`
- **输入场景**: 其它测试是否也以无交互方式调用 init
- **实际分支**: `grep -rn "cli_main.main.*init\|run_init_command" tests/` 只命中 `test_prompt_command.py:1211` 这一处非 init-test 的 init 调用
- **预期行为**: 确认无其它同类 stale caller
- **实际行为**: 唯一 stale caller 就是 `test_prompt_command.py:1211`
- **直接证据**: grep scan 结果
- **影响**: S3 只需处理一个 stale caller
- **建议改法和验证点**: S3 确认后修复
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中（S3 mandatory entry residual，同 F07）

### 09-未修复-低-S3 prewarm、真实 POSIX/Windows smoke、README/full CLI 是否仍未实现

- **入口/函数**: 固定 plan §7/§8 S3 内容
- **文件(行号)**: S2 累积 target 内不存在 `tests/cli/test_init_smoke.py`、`.github/workflows/r12-init-windows.yml`、prewarm helper
- **输入场景**: S3 验证要求
- **实际分支**: S2 implementation handoff 明确声明"未实现 S3/prewarm/workflow"；SHA-256 核验确认 `test_init_smoke.py` 和 `r12-init-windows.yml` 在当前工作树中不存在（`ABSENT`）
- **预期行为**: S3 的 prewarm、POSIX/Windows real smoke、junction/rollback CI、root/tests/config README 与 full CLI regression 仍需 S3 实现
- **实际行为**: implementation handoff §9.6 第 6 项已明确列出这些 S3 residual；无任何 S2 artifact 错误宣称已完成
- **直接证据**: implementation handoff §1、§9.6
- **影响**: S3 必须实现这些内容
- **建议改法和验证点**: 无需 S2 修改；S3 按 plan 实现
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（already-owned future residual）

### 10-未修复-低-PRESERVE 模式 prompt 文件缺失判断使用 exists() + is_symlink()

- **入口/函数**: `_copy_missing_prompt_files`
- **文件(行号)**: `dayu/cli/init_workspace.py:904`
- **输入场景**: PRESERVE 模式下 package prompt 目标路径存在或为 symlink
- **实际分支**: `if destination.exists() or destination.is_symlink(): continue`
- **预期行为**: 只跳过已存在文件；symlink 应被 `_validate_ordinary_tree` 已拒绝
- **实际行为**: `_validate_ordinary_tree` 在 line 818-820 对 public config 做了扫描，但 `_copy_missing_prompt_files` 在扫描后的逐文件复制阶段，`destination.is_symlink()` 检查是防御性冗余。staging 已通过 tree validation，symlink 不可能在 tree 中存在
- **直接证据**: line 818 `_validate_ordinary_tree(public_config, ...)` 在 line 822 `shutil.copytree` 之前
- **影响**: 冗余但无害的防御性检查
- **建议改法和验证点**: 无需修改；保持防御性编程
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 11-未修复-低-rollback 中 backup identity drift 的 retained_paths 包含所有 backup_records

- **入口/函数**: `_rollback_or_raise`
- **文件(行号)**: `dayu/cli/init_workspace.py:1072-1104`
- **输入场景**: rollback 期间某个 backup 的 identity 发生漂移
- **实际分支**: `except InitWorkspaceError` 块（1072-1089）合并当前 `exc.retained_paths` + 所有 `backup_records` 路径 + `transaction_root`，然后过滤 `_path_exists_no_follow`
- **预期行为**: retained_paths 应包含仍可定位的实际路径
- **实际行为**: 合并后用 `_path_exists_no_follow` 过滤已消失路径；`dict.fromkeys` 去重
- **直接证据**: line 1085 `tuple(path for path in retained if _path_exists_no_follow(path))`
- **影响**: retained_paths 如实反映当前可定位路径
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 12-未修复-低-post_publication_cleanup 错误类型投影

- **入口/函数**: `_post_publication_cleanup`
- **文件(行号)**: `dayu/cli/init_workspace.py:1194-1235`
- **输入场景**: cleanup 抛出 `InitWorkspaceError`、`OSError` 或 `KeyboardInterrupt`
- **实际分支**: `except (InitWorkspaceError, OSError, KeyboardInterrupt)` → 构造 `WorkspaceCleanupWarning`
- **预期行为**: warning 的 `error_type` 应反映底层异常类型
- **实际行为**: `partial_deletion` 和 `deletion_durability_unconfirmed` 对非 `InitWorkspaceError` 异常分别设为 `True` 和 `False`。`_underlying_error_type` 沿 `__cause__` chain 找最底层类型
- **直接证据**: line 1229-1232
- **影响**: 如实报告；非 `InitWorkspaceError` 异常的 `partial_deletion=True` 是保守正确假设
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

### 13-未修复-低-ConfigLoader 在 staging 路径加载不改写 package defaults

- **入口/函数**: `_validate_staged_runtime`
- **文件(行号)**: `dayu/cli/init_workspace.py:467`
- **输入场景**: staging validation 使用 `ConfigLoader(package_config_dir=staged_config_root).load()`
- **实际分支**: ConfigLoader 从 staging 路径加载当前 schema；staging 路径在 transaction-private 容器内
- **预期行为**: staging validation 不应修改 package defaults 或 public config
- **实际行为**: ConfigLoader 只读取配置；`discover_service_tools` 可能在 private validation root 创建 `.dayu/`/`portfolio/` side effect，但这些在 `_cleanup_private_path` 中被清理
- **直接证据**: line 474-480 validation cleanup 在 publication 前执行
- **影响**: 无污染
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/严重）**: 无实质问题

### 14-未修复-低-`_path_exists_no_follow` 对 OSError 返回 True

- **入口/函数**: `_path_exists_no_follow`
- **文件(行号)**: `dayu/cli/init_workspace.py:1424-1438`
- **输入场景**: no-follow stat 抛出 `OSError`（非 `FileNotFoundError`）
- **实际分支**: `except OSError: return True`
- **预期行为**: I/O 错误时保守返回存在（fail-closed）
- **实际行为**: 权限错误、磁盘故障等 `OSError` 被保守解释为"存在"，避免删除可能存在的对象
- **直接证据**: line 1436-1437
- **影响**: fail-closed 设计；可能在 I/O 错误时误判存在，但比误判不存在安全
- **建议改法和验证点**: 无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 无实质问题

## Open Questions

- 无。所有 14-path cumulative target 的实现已在直接代码证据下完成审查。

## Residual Risk

1. **S3 mandatory entry residual**（F07/F08）：`test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 以无交互方式调用旧 init，S3 必须迁移此测试。经扫描确认仅此一处 stale caller。
2. **S3 未实现项**（F09）：prewarm、POSIX real smoke、Windows real smoke（含 junction/rollback）、Windows CI workflow、root/tests/config README、full CLI regression 仍需 S3 实现。无 S2 artifact 错误宣称已完成。
3. **Windows parent-directory fsync 缺失**：R12 诚实不承诺 Windows power-loss directory crash durability；保留 same-volume replace、process-visible rollback 与 typed diagnostics。
4. **RESET 两个 managed roots 非 single-syscall atomic**：逐根 same-volume `os.replace` + rollback，不是跨根原子事务。
5. **`.dayu-init.lock` 只串行 init**：不锁定 Host/CLI/Web/WeChat 或其它 Dayu 进程。
6. **已持久化环境变量无法与 workspace publication 组成同一事务**：Windows `setx` partial failure 只报告 written names。
