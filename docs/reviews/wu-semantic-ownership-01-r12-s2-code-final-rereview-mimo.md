# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 complete cumulative code re-review — AgentMiMo

## Scope

- Mode: accepted-finding fix re-review（不是新 WU）
- Branch: `phaseflow/host-issues-control`
- Fixed plan: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`（SHA `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`）
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-controller-adjudication.md`
- Agent fix: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-fix-codex.md`（SHA `9b38c2759a16503230766ecc95092681dd4271364d790e612b677e48288405e4`）
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-fix-controller-validation.md`（53 行 / 4,347 字节 / SHA `c9b51d06accae8ef3d2fba2ed598d3f5bd7efc0af4dd9cfe33ed97a029857906`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-final-rereview-mimo.md`
- 审查时间: 2026-07-18

## Target identity 验证

### 4 个 changed paths（以 Controller validation 为准）

| 路径 | 行 | 字节 | SHA-256 | 状态 |
|---|---:|---:|---|---|
| `dayu/cli/init_environment.py` | 835 | 31,429 | `16353a72bce2efeeac1aae64f1f0c94cdca2e30e956be9412f2f0f20002059c0` | ✓ 精确匹配 |
| `dayu/cli/commands/init.py` | 743 | 27,820 | `fe5d4a434ccd5b528ef61cf80295652bbcc4bfa961bd0be3c6dc2aecf95a3e19` | ✓ 精确匹配 |
| `tests/cli/test_init_environment.py` | 1,245 | 48,353 | `5bc46652d54ae5e6860424c3acb952ce2dd615cb0df09eb1ae5c3b6c1f184618` | ✓ 精确匹配 |
| `tests/cli/test_init_command.py` | 964 | 34,238 | `25de81a149fcaee079c1e693b278258390d1710d87617e350abbe5abd914a4b2` | ✓ 精确匹配 |

### 10 个 immutable S2 paths

| 路径 | SHA-256 | 状态 |
|---|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✓ 精确匹配 |
| `dayu/cli/init_workspace.py` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` | ✓ 精确匹配 |
| `dayu/cli/arg_parsing.py` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` | ✓ 精确匹配 |
| `dayu/service/host_assembly.py` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` | ✓ 精确匹配 |
| `dayu/service/entrypoint_runtime.py` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` | ✓ 精确匹配 |
| `dayu/service/README.md` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` | ✓ 精确匹配 |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | ✓ 精确匹配 |
| `tests/cli/test_init_workspace.py` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` | ✓ 精确匹配 |
| `tests/cli/test_arg_parsing.py` | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` | ✓ 精确匹配 |
| `tests/service/test_host_assembly.py` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` | ✓ 精确匹配 |

## Findings

未发现实质性问题。

## Accepted findings closure

### R12-S2-RR-F01 — CLOSED

**审查范围**: `commands/init.py` 第 166-192 行（persistence interrupt/error 路径）。

**直接证据**:

1. **abort-first 顺序** (`commands/init.py:168-192`): typed/plain persistence interrupt、`EnvironmentPersistenceError` 和普通 `OSError` 四条路径全部先调用 `_try_abort_prepared_transaction(prepared)`，再执行 diagnostic 投影。验证代码:
   - `:169` — `abort_error = _try_abort_prepared_transaction(prepared)`
   - `:175` — plain interrupt 路径同样先 abort
   - `:179` — `EnvironmentPersistenceError` 路径同样先 abort
   - `:184` — `OSError` 路径同样先 abort

2. **abort helper 无 diagnostic I/O** (`commands/init.py:609-624`): `_try_abort_prepared_transaction` 只调用 `abort_prepared_workspace_transaction(prepared)`，返回可空 `InitWorkspaceError`，不做任何 stderr 写入。

3. **broken stderr 测试** (`test_init_command.py:637-712`): `test_persistence_interrupt_aborts_before_broken_stderr_and_exits_130` 覆盖 typed/plain × abort success/failure 四组合:
   - `events[0] == "abort"` — abort 始终是第一个事件
   - `exit_code == EXIT_KEYBOARD_INTERRUPT` — 四组合均 exit 130
   - abort success 时 `retained_transactions == ()` — 无 private transaction 遗留
   - abort failure 时 `len(retained_transactions) == 1` — 保留 truthful private transaction

4. **abort failure retained truth** (`test_init_command.py:574-634`): `test_persistence_interrupt_abort_failure_reports_retained_truth_and_exits_130` 验证 abort failure diagnostic 包含 stage、retained path、public states 和 written names，且 exit 130。

**adversarial 挑战 — broken stderr 能否改变 exit 130?**

`_report_diagnostic_best_effort` (`commands/init.py:639-650`) 使用 `except Exception` 吸收 stderr 写入失败。该异常被吸收后，控制流继续到 `raise`（原始中断），最终 `run_init_command` 的顶层 `except KeyboardInterrupt` 返回 `EXIT_KEYBOARD_INTERRUPT`。因此 broken stderr 不能改变 exit 130。

**裁定**: R12-S2-RR-F01 已在 semantic owner 关闭。abort 是 diagnostic I/O 前的首个事件；broken stderr 不能覆盖原始中断或改变 exit code。

### R12-S2-RR-F02 — CLOSED

**审查范围**: `init_environment.py` 第 710-764 行（cleanup/identity 分类），第 54-73 行（retained_paths 字段），`commands/init.py` 第 593-606 行（retained path 投影）。

**直接证据**:

1. **封闭 identity 分类** (`init_environment.py:739-764`): `_classify_profile_path_identity` 使用 no-follow `os.lstat` 精确分为四类:
   - `OWNED` — `S_ISREG` 且 `st_dev`/`st_ino` 精确匹配 expected
   - `ABSENT` — `FileNotFoundError`
   - `DRIFTED` — 存在但 identity 不匹配（非 regular file 或 dev/ino 不等）
   - `UNREADABLE` — `OSError`/`KeyboardInterrupt`

2. **identity-safe cleanup** (`init_environment.py:710-736`): `_cleanup_owned_profile_temporary` 只对 `OWNED` 调用 `os.unlink`:
   - `:728` — `ABSENT` 返回空
   - `:730` — `DRIFTED`/`UNREADABLE` 返回 `(temporary_path,)`，不删除
   - `:732-735` — `unlink` 抛 `OSError`/`KeyboardInterrupt` 时返回 `(temporary_path,)`

3. **retained_paths 只含 Path** (`init_environment.py:54-73, 169-183`):
   - `EnvironmentPersistenceError.retained_paths: tuple[Path, ...]` — 只含路径
   - `EnvironmentPersistenceResult.retained_paths: tuple[Path, ...]` — 只含路径
   - `EnvironmentPersistenceInterrupted.result.retained_paths` — 通过 result 间接只含路径
   - entry `value` 标记为 `repr=False`，不进入 repr

4. **CLI 投影不含 value** (`commands/init.py:593-606`): `_report_retained_environment_paths` 只调用 `str(path)` 投影路径名，不读取文件内容。

5. **测试矩阵**:
   - `test_posix_cleanup_failure_reports_retained_owner_temp_without_value` (`test_init_environment.py:821-915`): 覆盖 unlink/identity-read × os-error/interrupt 四组合。验证: `retained_paths == retained`，`retained[0].read_text().find(entry.value) >= 0`（文件真实含值），但 `entry.value not in rendered_exception` 且 `entry.value not in rendered_truth`。
   - `test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement` (`test_init_environment.py:918-963`): 验证 identity drift 时不误删，retained path 报告正确。

**adversarial 挑战 — POSIX replace before/after、identity drift 与 publication truth**:

- **replace-before interrupt** (`init_environment.py:644-663`): `_profile_replace_applied` 检查 source 是否 ABSENT 且 destination 是否 OWNED。如果 replace 未发生，`profile_replaced=False`，names 进入 `unwritten_names`，temp 被清理。
- **replace-after interrupt**: 如果 replace 已完成，`profile_replaced=True`，names 进入 `written_names`。
- **identity drift**: `_cleanup_owned_profile_temporary` 对 `DRIFTED` 返回路径不删除，测试 `test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement` 直接验证。
- **publication truth**: `EnvironmentPersistenceResult.written_names`/`unwritten_names` 精确反映 replace 是否已发生；CLI 通过 `_report_persisted_environment_names` 和 `_report_retained_environment_paths` 分别投影。

**adversarial 挑战 — generic Exception 是否吞编程错误?**

`_report_diagnostic_best_effort` (`commands/init.py:639-650`) 使用 `except Exception`。这确实会捕获编程错误（如 `TypeError`、`AttributeError`）。但在该场景中:
- 调用点已在已知中断/失败状态（persistence interrupt、abort failure 等）
- 函数唯一目的是不覆盖已确定的 transaction/interrupt 控制流
- 被吸收的异常不会丢失业务状态（abort 已完成或已失败）
- 丢失的只是诊断可见性

如果 `message` 参数本身导致 `print` 抛编程错误（如编码问题），该异常被吸收后用户看不到 retained_paths 信息。这是一个低严重度的可观察性减弱，但不改变 abort/exit 语义。当前实现符合 "diagnostic I/O 不得覆盖已确定的 transaction/interrupt 控制流" 的设计意图。

**裁定**: R12-S2-RR-F02 已在 semantic owner 关闭。identity 分类封闭且安全，retained_paths 只含 Path 不含 value，unlink/identity-read 故障均被准确报告，外部/identity-drift 对象不被误删。

## Adversarial 挑战汇总

| 挑战项 | 结论 | 直接证据 |
|---|---|---|
| generic `Exception` 过宽/吞编程错误 | 低风险可观察性减弱，不改变 abort/exit 语义 | `commands/init.py:648-649` 吸收点在已知中断/失败状态 |
| retained_paths owner 与 redaction | 正确：只含 `Path`，不含 value | `init_environment.py:61,183` 字段类型；`:733` unlink 故障返回路径 |
| POSIX replace before/after truth | 正确：`_profile_replace_applied` 精确判断 | `init_environment.py:684-707` identity-based 对账 |
| cleanup unlink/identity-read | 正确：`OWNED` 才 unlink，`DRIFTED`/`UNREADABLE` 报告路径 | `init_environment.py:728-735` |
| identity drift | 正确：不误删未知 replacement | `test_init_environment.py:918-963` |
| broken stderr 能否改变 exit 130 | 不能：`except Exception` 吸收后仍 `raise` 原始中断 | `commands/init.py:648-649` → `:173` |
| abort failure 是否阻止 exit 130 | 不阻止：abort failure 被 best-effort 报告，原始中断仍传播 | `commands/init.py:169-173` |
| Windows truth | 正确：partial failure 只报告 names，不注入 | `init_environment.py:446-472` |
| S3 boundary | 无偷带：production/test 不含 prewarm/smoke/README/Windows workflow | Explore 搜索零命中 |
| 过度设计 | 无：三个新模块分别承载三类 owner，无通用 framework | 代码结构与 fixed plan §10.3 一致 |
| semantic ownership drift | 无：environment owner 拥有 retained truth，CLI owner 只投影 | `init_environment.py` 拥有分类/清理；`commands/init.py` 只调用后投影 |
| 兼容/fallback/test shim | 无 | Explore 搜索零命中 |
| deferred 偷带 | 无 | Explore 搜索零命中 |

## Open Questions

无。

## Residual Risk

1. POSIX cleanup 失败时，含敏感值的 owner temp（mode `0600`）仍真实保留于磁盘。当前 contract 是准确报告 retained path 且不泄漏 value，让操作者可定位。R12 不创建安全删除重试器或通用 FS framework。
2. `_report_diagnostic_best_effort` 的 `except Exception` 可能在极端情况下吞掉编程错误，导致诊断信息不可见。这不影响 abort/exit 语义，但降低可观察性。
3. S3 prewarm、真实 POSIX/Windows smoke、Windows workflow、README 与 stale explicit-interaction caller migration 仍未执行。
4. Windows directory crash durability、RESET 两根非 single-syscall atomic、`.dayu-init.lock` 只串行 init、OS environment 与 workspace 非同一事务仍是 fixed plan §10.1 retained residual。

## Verdict

**PASS — 0 new findings, 2/2 accepted findings closed.**

R12-S2-RR-F01 与 R12-S2-RR-F02 均已在各自 semantic owner 关闭。abort-first 顺序经 broken stderr adversarial 测试验证；retained_paths identity-safe cleanup 经 unlink/identity-read × os-error/interrupt 四组合测试验证。4 个 changed paths SHA-256 精确匹配，10 个 immutable paths SHA-256 精确匹配。无 S3 偷带、无 semantic ownership drift、无兼容/fallback/test shim。

当前 accepted findings open: `0`。S2 可进入完成状态。
