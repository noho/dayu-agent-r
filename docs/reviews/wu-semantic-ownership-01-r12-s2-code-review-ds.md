# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 Cumulative Code Review — AgentDS

## Scope

- Mode: current changes (cumulative R12 S2 implementation relative to HEAD `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`)
- Branch: `phaseflow/host-issues-control`
- Base: `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-ds.md`
- Fixed review target: Controller validation SHA-256 table (15 paths)
- Included scope: 10 tracked changed files + 4 S1 read-only production files
- Excluded scope: control/review/plan artifacts, untracked review docs, `workspace/tmp/`
- Parallel review coverage: 无（单路 AgentDS 全量 review）

### Changed files

| 路径 | 状态 | 终态 SHA-256 |
|---|---|---|
| `dayu/cli/init_catalog.py` | S1 read-only | `937315f3...` |
| `dayu/cli/init_environment.py` | S1 read-only | `71be5ba8...` |
| `dayu/cli/init_workspace.py` | S2 new | `b5aac7f4...` |
| `dayu/cli/commands/init.py` | S2 modified | `fd927bad...` |
| `dayu/cli/arg_parsing.py` | S2 modified | `add2353a...` |
| `dayu/service/host_assembly.py` | S2 modified | `658b57e5...` |
| `dayu/service/entrypoint_runtime.py` | S2 modified | `4e165403...` |
| `dayu/service/README.md` | S2 modified | `d1eed1d0...` |
| `tests/cli/test_init_workspace.py` | S2 new | `c363bc19...` |
| `tests/cli/test_init_command.py` | S2 modified | `db965a53...` |
| `tests/cli/test_arg_parsing.py` | S2 modified | `9a0b7aa6...` |
| `tests/service/test_host_assembly.py` | S2 modified | `28e09940...` |

S1 四路径 hashes 经核验未漂移。

## Mandatory Controller Review Challenges

### Challenge 1: init_workspace.py 1618 行是否违反 God function/object

**结论：不违反。**

`init_workspace.py` 是一个模块，不是一个函数。其结构如下：

- 5 个 public 函数：`snapshot_managed_roots`（56 行）、`determine_init_mode`（22 行）、`prepare_workspace_transaction`（169 行）、`abort_prepared_workspace_transaction`（10 行）、`publish_workspace_transaction`（174 行）
- ~20 个模块级私有辅助函数，每个职责单一
- 8 个 frozen/slots dataclass，每个有明确语义边界

模块拥有唯一语义域：managed-root transaction。它不接触 secret（`init_environment.py`），不拥有模型选择逻辑（`init_catalog.py`），不编排用户交互（`commands/init.py`），不解析配置 schema（`ConfigLoader`），不分类 Fins provider（`host_assembly.py`）。

**最长函数分析**：`prepare_workspace_transaction`（line 381–549，169 行）编排 13 个步骤，每个步骤委托给独立私有 helper。try/except 嵌套深度源于 transaction 语义必需的 cleanup-on-error 模式：在 staging 构造中任何步骤失败都需要安全清理已创建的 private container。这不是 God function 式的职责混合，而是 transaction coordinator 的 defensive error handling。

`publish_workspace_transaction`（line 570–743，174 行）类似：backup→replace→rollback 的 try/except 结构是 rename-after-effect 检查和逆序恢复所必需的。

**状态可证性**：四态由 `InitMode` typed enum 表达，状态判定 `determine_init_mode` 是纯函数（输入 snapshot + flags → 输出 mode），`WorkspaceSnapshot`/`WorkspaceTransactionRequest`/`PreparedWorkspaceTransaction`/`WorkspaceTransactionResult` 形成不可变状态链。每个 public function 的输入/输出都是 typed dataclass，状态转换可追踪。

**风险**：169 行的函数在长期维护中可能累积更多职责。建议在后续迭代中监控 `prepare_workspace_transaction` 是否超过 200 行——若超过，应考虑拆分为 staging 阶段和 validation 阶段两个子函数。但当前不构成 God function。

**严重程度**：无 finding。这是固定计划 §10.3 明确论证的设计："三个新模块分别承载已经存在且不可互换的三类 owner：静态选择事实、OS secret store、跨目录 transaction；orchestrator 只编排，不形成 God function。"

### Challenge 2: 四态 snapshot/rename-after-effect/rollback/cleanup/KeyboardInterrupt/symlink-reparse/durability/portfolio truth

**结论：所有路径均正确实现，portfolio truth 保持。**

逐路径验证：

**Snapshot TOCTOU**：`_require_snapshot_unchanged`（line 782–799）在 mutation boundary 前重取并比较完整 `WorkspaceSnapshot`（identity + content_digest），漂移即 fail closed。RESET 场景中 unlocked→locked snapshot 双重确认由 `_require_confirmed_snapshot`（line 334–354）执行。

**Rename-after-effect**：`publish_workspace_transaction` 中 backup replace（line 614–641）和 config replace（line 643–656）均在 `os.replace` 调用后执行 post-hoc identity 对账：若 syscall 已生效但抛异常，代码检测到 source 缺失 + destination 存在 + identity 匹配，正确记录已生效事实后再 raise。这是对 POSIX `os.replace` 非原子错误报告的已知问题的标准防御。

**Rollback**：`_rollback_or_raise`（line 1014–1104）按逆序恢复：先清理已发布的 config（若 `published_config=True`），再逐个 `backup→original` replace，最后 sync workspace root。每个 restore 前核验 backup identity 未漂移。rollback 失败时报告精确 stage、current public truth、retained paths。

**Cleanup**：严格区分 pre-publication abort（`_discard_private_container_or_raise`，失败即 raise）和 post-publication cleanup（`_post_publication_cleanup`，失败转 warning）。两者不共用语义。

**KeyboardInterrupt**：
- `prepare_workspace_transaction` 中 line 528–535：单独 catch `KeyboardInterrupt`，执行 identity-locked discard 后重新 raise
- `publish_workspace_transaction` 中 line 682–689：`KeyboardInterrupt` 触发完整 rollback + abort 后重新 raise
- 锁等待中 SIGINT：`file_lock` 现有 typed release 语义确保释放

**Symlink/reparse**：
- `_require_ordinary_directory`（line 1441–1467）：拒绝 `S_ISLNK` 和 Windows `FILE_ATTRIBUTE_REPARSE_POINT`
- `_validate_ordinary_tree`（line 1470–1516）：no-follow 递归扫描整棵树，拒绝 nested symlink/reparse/special file
- `_cleanup_private_path`（line 1252–1363）：quarantine 前后均执行 identity 复核，POSIX 使用 `O_NOFOLLOW` flag，Windows 使用 `st_file_attributes` / `st_reparse_tag`

**Durability**：
- POSIX：staging file `O_NOFOLLOW` + `fsync`，leaf-to-root directory `O_DIRECTORY` + `fsync`，publication 后 workspace root sync
- Windows：staging file `fsync`（`_commit()`），same-volume `os.replace` 保证 process-visible atomic transition；明确不承诺 parent-directory crash durability（按 fixed plan §6.3.2）

**Portfolio truth**：
- `MANAGED_ROOT_MANIFEST` 只含 `.dayu` 和 `config`（line 133）
- `_roots_replaced_by_mode`（line 998–1011）：只有 RESET 替换两个 roots，其它模式只替换 config
- 全文搜索：production 代码中无 `assets` 或 `portfolio` 创建/删除路径
- `_public_root_truth`（line 1579–1598）只报告 manifest roots 的存在性

**严重程度**：无 finding。四态 contract 在所有验证路径上正确实现。

### Challenge 3: Service Fins override raw grammar 与 ordinary None/非 Fins/Web isolation

**结论：正确实现，无越界。**

Raw grammar 优先：
```
line 1492-1503 in host_assembly.py:
  if configured_workspace_root is not None:
      type check (must be str)
      strip check (must be non-empty)
  if fins_workspace_root_override is not None:  ← 只有通过 raw grammar 后才进入
      expanduser + is_absolute check
      return str(resolved)
  if stripped_workspace_root is None:           ← 无配置 + 无 override
      return workspace_root (普通 runtime default)
  # 否则按配置的绝对/相对路径解析
```

Override 无条件支配合法 raw 三态（未配置/显式绝对/显式相对）——在 path selection 前 return，不修改 raw config bytes、staging bytes 或 schema。

Ordinary runtime 显式 `None`：
```
entrypoint_runtime.py line 517:
  fins_workspace_root_override=None,
```

非 Fins/Web 隔离：
- `_is_fins_workspace_bound_provider_config` 是 Fins provider 分类的唯一 owner
- Web `playwright_storage_state_dir` 使用 `effective_web_storage_state_dir`，不消费 `fins_workspace_root_override`
- 全文搜索确认：override 只进入 `_effective_fins_workspace_root_config_value`，不进入任何非 Fins 路径

未偷带统一 authorization：
- 全文搜索 production 代码：`authorization`、`tool_auth`、`permission` 零命中
- `fins_workspace_root_override` 是直接 `Path | None` 参数，不是通用 permission/authorization framework
- Topic 9 保持 closed

**严重程度**：无 finding。

### Challenge 4: test_prompt_command 无交互 init failure — 是否确属 S3 test/workflow migration

**结论：Controller 分类成立。无其他同类 stale caller。**

直接证据：
```
tests/cli/test_prompt_command.py:1211:
  assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
```

该测试以无交互方式调用旧 init（无模型选择、无 secret 收集）。新 init 要求显式交互输入（`_select_model()` → `_read_input("模型组合编号或 choice id: ")` 阻塞等待 stdin），因此该测试必然失败。

全文搜索确认只有唯一一个 stale caller：
- `tests/cli/test_prompt_command.py:1211` — 唯一命中
- 无其他测试或 production 代码以无交互方式调用 `run_init_command` 或 `cli_main.main(("init", ...))`

修复路径分类：
- 该测试的语义 owner 是 S3 test/workflow migration：它测试 prompt entrypoint 使用 init 生成的 config，需要在 S3 获得真实 subprocess smoke 或 mock 交互输入后才能迁移
- S2 production 代码不得为适配此测试添加 implicit default、compatibility fallback 或 test shim
- 当前 S2 代码正确：`_select_model()` 要求显式输入，`_parse_model_choice("")` 抛出 `CliInitOperationError("model choice is required")`

**严重程度**：无 finding。这是 already-owned future residual（S3 mandatory entry），不是 S2 defect。

### Challenge 5: S3 prewarm、真实 POSIX/Windows smoke、README/full CLI 是否仍未实现且未被错误宣称

**结论：全部未实现且未被错误宣称。**

逐项验证：

**Prewarm**：
- production 代码全文搜索 `importlib.import_module`、`prewarm`、`dayu.cli.commands.prompt`、`dayu.cli.commands.interactive`：零命中
- `commands/init.py` 的 `run_init_command` 在成功发布后直接 print 结果并返回，没有 prewarm 调用
- 固定计划 §7 的 exact-two-root import-only prewarm 未实现

**真实 POSIX smoke**：
- 无 `tests/cli/test_init_smoke.py` 文件
- 无真实 subprocess init smoke（FIRST→PRESERVE→OVERWRITE→RESET 完整流程）

**真实 Windows smoke**：
- 无 `.github/workflows/r12-init-windows.yml` 文件
- 无 Windows runner 真实 normal transaction 或 junction/reparse 证明

**README**：
- 根 `README.md`、`dayu/config/README.md`、`tests/README.md` 均未更新
- `dayu/service/README.md` 已在 S2 按约束更新（仅 Service owner contract 变更）

**Full CLI regression**：
- 未执行 `pytest tests/cli -q`（固定计划 §9 S3 final profile）

**未被错误宣称**：
- Implementation handoff §9 明确："S3 的 prewarm、POSIX/Windows real smoke、其它 README与full CLI仍未实现"
- Controller validation §5 明确："必须确认 S3 的 prewarm、真实 POSIX/Windows smoke...仍未偷带入 S2，也未被错误宣称完成"
- 代码中无 `S3`、`prewarm`、`test_init_smoke` 字符串（已全文搜索确认）

**严重程度**：无 finding。这是 S3 mandatory entry residual，已由 fixed plan 和 Controller 明确归属。

## Findings

### F-01 — 低 — `prepare_workspace_transaction` 函数长度与嵌套深度构成维护风险

- **入口/函数**: `prepare_workspace_transaction`
- **文件(行号)**: `dayu/cli/init_workspace.py:381-549`
- **输入场景**: 任何 valid `WorkspaceTransactionRequest`
- **实际分支**: 正常执行路径
- **预期行为**: 当前行为正确——staging 构造、model application、manifest projection、validation、cleanup、sync 顺序执行，任一失败触发 cleanup
- **实际行为**: 函数 169 行，包含 4 层 try/except 嵌套（line 394 `try: transaction_root = mkdtemp` → line 406 `try: identity` → line 429 `try: build/validate/cleanup/sync` → line 508 `except InitWorkspaceError` 内含 cleanup 的二次 try/except），以及 `except KeyboardInterrupt` 和 bare `except Exception`
- **直接证据**:
  - line 394: `try: transaction_root = Path(tempfile.mkdtemp(...))`
  - line 406: `try: transaction_identity = ...`
  - line 429: `try: _build_staged_config(...)` （自此开始 ~120 行都在此 try 块内）
  - line 508-527: `except InitWorkspaceError as exc:` 内含条件分支（retained_paths 是否为空）+ `_discard_private_container_or_raise` 的二次 try/except
  - line 528-535: `except KeyboardInterrupt:` + discard
  - line 536-549: `except Exception as exc:` + discard + re-raise as InitWorkspaceError
- **影响**: 未来在 staging 流程中增加步骤（如新增配置校验、新增 manifest 操作）时，容易在错误的 try/except 层级插入代码，导致 cleanup 语义错误（例如：在 validation 成功但 cleanup 失败后忘记 sync staging config）
- **建议改法和验证点**:
  1. 将 line 429-507（`_build_staged_config` 到 `staged_config_identity`）提取为 `_stage_and_validate` 私有函数，返回 `_StagedValidationResult`（包含 `staged_config_root`、`staged_config_identity`、`tool_count`、`scene_ids`）
  2. `prepare_workspace_transaction` 只保留 transaction container 创建、调用 `_stage_and_validate`、在失败时 discard
  3. 验证点：提取后的函数必须保持相同的异常传播语义（InitWorkspaceError 携带 retained_paths，KeyboardInterrupt 重新抛出，unknown Exception 包装为 InitWorkspaceError）
- **修复风险（低）**: 纯重构，不改变行为。但 S2 当前处于 review gate，不应在 review 阶段重构
- **严重程度（低）**: 当前行为正确，仅影响长期维护性。不是 correctness/stability 问题
- **S2 accepted-fix candidate**: 否。该 finding 建议在 S3 或后续 cleanup WU 中处理，不在当前 S2 review→fix→re-review 循环中修复

### F-02 — 低 — `_public_root_truth` 函数中 `path.exists()` 与 `path.is_symlink()` 存在冗余检查

- **入口/函数**: `_public_root_truth`
- **文件(行号)**: `dayu/cli/init_workspace.py:1593`
- **输入场景**: 在 publication fault 后调用 `_public_root_truth` 报告当前 public root 状态
- **实际分支**: `present = path.exists() or path.is_symlink()`
- **预期行为**: 检测路径是否存在（包括 dangling symlink）
- **实际行为**: `path.exists()` 在 Python 中返回 `True` 当路径存在且（若为 symlink）其 target 存在；`path.is_symlink()` 返回 `True` 当路径本身是 symlink（不论 target 是否存在）。两者取 `or` 意味着：ordinary path → `True`；symlink to existing → `True`（双重覆盖）；dangling symlink → `True`（由 `is_symlink()` 覆盖）
- **直接证据**: line 1593: `present = path.exists() or path.is_symlink()`
- **影响**: 无功能影响——managed roots 已在进入此函数前被 `_require_ordinary_directory` 和 `_validate_ordinary_tree` 拒绝 symlink。此处的 `or path.is_symlink()` 是防御性冗余，逻辑正确但不精简
- **建议改法和验证点**: 可简化为 `present = path.exists() or path.is_symlink()`（保持当前写法以明确表达意图）或改为 `present = True if path.is_symlink() else path.exists()`（但行为等价）。当前写法可接受，无需强制修改
- **修复风险（低）**: 纯风格问题
- **严重程度（低）**: 无功能影响
- **S2 accepted-fix candidate**: 否

### F-03 — 无 finding — `commands/init.py` `run_init_command` 中环境持久化失败后的 transaction abort 异常传播正确

**验证结论**：line 164-177 的异常处理链路正确。

```python
try:
    persistence_result = _persist_environment_if_needed(persistence_plan)
except (EnvironmentPersistenceError, OSError):
    abort_prepared_workspace_transaction(prepared)  # POSIX 失败：清理 staging 后重新 raise
    raise
if persistence_result is not None and not persistence_result.succeeded:
    _report_persisted_environment_names(persistence_result)
    abort_prepared_workspace_transaction(prepared)  # Windows 失败：报告 names + 清理 staging
    raise CliInitOperationError(...)
try:
    result = publish_workspace_transaction(prepared)
except (InitWorkspaceError, KeyboardInterrupt):
    _report_persisted_environment_names(persistence_result)  # 发布失败但环境可能已写
    raise
```

POSIX 路径：`_persist_posix_environment` 失败抛出 `EnvironmentPersistenceError` → caught by first except → abort staging → re-raise original error。正确：workspace 未发布，staging 已清理。

Windows 路径：`_persist_windows_environment` 失败返回 `FAILURE`/`PARTIAL_FAILURE` → second if → 报告已写 names → abort staging → raise `CliInitOperationError`。正确：workspace 未发布，staging 已清理，已写 env names 被报告。

Publication 失败但环境已持久化：`publish_workspace_transaction` raise → third except → 报告已写 env names → re-raise。正确：`publish_workspace_transaction` 内部已执行 rollback + abort，此处只需报告 env names（无法回滚 OS store）并传播错误。

**严重程度**：无 finding。

## Open Questions

1. `init_workspace.py` 的 `_cleanup_private_path` 函数被用于 rollback 中删除已发布的 public config（line 1033-1039）。该函数名为 "private" 但实际在 rollback 路径中操作 public path。虽然 containment 校验（`_require_private_child`）对此场景仍然成立（因为 public config 是 workspace root 的直接 child），但函数名可能误导未来维护者。建议在 S3 或后续 cleanup WU 中重命名为 `_cleanup_owned_path` 或添加 rollback-specific wrapper。

2. `publish_workspace_transaction` 中 line 723-736：post-publication POSIX workspace-root sync 失败时，warning 的 `path` 字段设置为 `prepared.transaction_root` 而该 path 在此时可能已被 `_post_publication_cleanup` 删除。warning 中 `path_exists=False` 正确反映了这一点，但 `path=prepared.transaction_root` 可能让 operator 误以为 transaction root 仍存在。这是 truthful reporting（path 字段指操作的 target path，不是 retained path），但值得在 S3 README 中说明 warning 字段的解读方式。

## Residual Risk

### R12-S2-DS-R01 — S3 未实现项（already-owned future residual）

| 项目 | Owner | 状态 |
|---|---|---|
| Import-only prewarm | S3 `commands/init.py` | 未实现 |
| 真实 POSIX subprocess smoke | S3 `tests/cli/test_init_smoke.py` | 未实现 |
| 真实 Windows normal transaction/junction/rollback | S3 `.github/workflows/r12-init-windows.yml` | 未实现 |
| 根 README / config README / tests README | S3 | 未更新 |
| Full CLI regression (`pytest tests/cli -q`) | S3 | 未执行 |
| `test_prompt_command_uses_init_generated_workspace_config` 迁移 | S3 test/workflow migration | 当前失败 |

所有项目已由 fixed plan、implementation handoff 和 Controller validation 明确归属 S3，未被错误宣称为 S2 已完成。

### R12-S2-DS-R02 — Windows directory crash-durability（fixed-plan retained residual）

Python 3.11 Windows 没有本项目已验证的 parent-directory `fsync` 等价机制。R12 诚实只承诺 staging file `fsync`、same-volume `os.replace` 的 process-visible atomic transition、live rollback 和 isolation。S3 真实 Windows normal transaction 是 release evidence，不承诺 power-loss directory persistence。这是 fixed plan §10.1 明确保留的 residual。

### R12-S2-DS-R03 — RESET 两根非 single-syscall 原子（fixed-plan retained residual）

两个 managed roots（`.dayu` 和 `config`）的 per-root `os.replace` + rollback 不是跨 root single-syscall atomic transaction。R12 不扩展 Host/process lock。这是 fixed plan §10.1 明确保留的 residual。

### R12-S2-DS-R04 — `.dayu-init.lock` 只串行 init（fixed-plan retained residual）

锁只防止两个 init 进程竞争发布，不阻止 active Host/CLI/Web/WeChat 进程继续写 managed roots。RESET warning 要求用户先停止 active 进程。这是 fixed plan §10.1 明确保留的 residual。

### R12-S2-DS-R05 — OS environment 与 workspace 非同一事务（fixed-plan retained residual）

已持久化到 OS store 的环境变量无法与 workspace publication 组成同一事务。Windows `setx` 多变量不能跨调用回滚。这是 fixed plan §10.1 明确保留的 residual。

## Verdict

**PASS — 零 defect finding，零 S2 accepted-fix candidate。**

R12 S2 cumulative implementation 在 correctness、stability、semantic ownership、security 和 adversarial 维度上通过了 fixed plan 和 Controller validation 的全部 5 项 mandatory review challenges。四个模块的 semantic owner 边界清晰，无越界、无 God function/object、无 authorization 泄漏、无 secret 泄漏、无 test shim 进入 production。四态 transaction 的 snapshot/rename-after-effect/rollback/cleanup/KeyboardInterrupt/symlink-reparse/durability/portfolio truth 在所有验证路径上正确。

两个 LOW findings（F-01 函数长度维护风险、F-02 冗余检查）均不构成 correctness/stability 问题，不建议在当前 S2 review→fix→re-review 循环中修复。所有 S3 mandatory entry residuals 已由 fixed plan 和 Controller 明确归属，未被错误宣称完成。

**Finding counts**: 2 LOW（均非 S2 accepted-fix candidate），0 MEDIUM，0 HIGH，0 CRITICAL

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-ds.md`
