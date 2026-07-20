# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 complete cumulative code re-review — AgentMiMo

## Scope

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 complete cumulative code re-review，不是新 WU。
- Mode：cumulative 14-path target（Controller validation fixed）+ 4 fix paths。
- Branch：`phaseflow/host-issues-control`
- Base：HEAD `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`
- Output file：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-mimo.md`
- Included scope：14 个 cumulative target 路径（7 production + 7 test），其中 4 个为 F01-F03 fix paths。
- Excluded scope：control/review/plan artifacts、S3-only paths、workspace/tmp/。
- Parallel review coverage：无（单路 AgentMiMo 全量 review）。

### Authority artifacts

| 路径 | SHA-256 |
|---|---|
| fixed plan | `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` |
| Controller adjudication | `fa0212521fc643eb041a5d8f651a420aae0e214872fd347696c1ed3f3e8b3666` |
| Fix artifact (Codex) | `3a05658d3e5383223f04ef78d82135305597413a33fa263b1715abf4d48f4025` |
| Controller validation | （本 re-review 的直接上游） |

### 14-path cumulative target SHA-256 verification

| 路径 | 行 | 字节 | SHA-256 | 匹配 |
|---|---:|---:|---|---|
| `dayu/cli/init_catalog.py` | — | — | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✅ |
| `dayu/cli/init_environment.py` | 776 | 29,178 | `55756e0662d203811a84325cb79c3a42ea13592b790ec02966f361e670e71a40` | ✅ |
| `dayu/cli/init_workspace.py` | — | — | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` | ✅ |
| `dayu/cli/commands/init.py` | 689 | 25,789 | `3acbbec9049c91fd238a167a7a5a708a03be9b49a73f03907a710f32dffd56ce` | ✅ |
| `dayu/cli/arg_parsing.py` | — | — | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` | ✅ |
| `dayu/service/host_assembly.py` | — | — | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` | ✅ |
| `dayu/service/entrypoint_runtime.py` | — | — | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` | ✅ |
| `dayu/service/README.md` | — | — | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` | ✅ |
| `tests/cli/test_init_catalog.py` | — | — | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | ✅ |
| `tests/cli/test_init_environment.py` | 1,146 | 44,114 | `406ad395bfa8e6c644bca8f7a9349181bdabfd770a7e2ea1772828d54379eed6` | ✅ |
| `tests/cli/test_init_workspace.py` | — | — | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` | ✅ |
| `tests/cli/test_init_command.py` | 832 | 29,097 | `5f229547219f34db0116d8fed5a764ab2d741ae47423e62166bb4b1bca6f72cb` | ✅ |
| `tests/cli/test_arg_parsing.py` | — | — | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` | ✅ |
| `tests/service/test_host_assembly.py` | — | — | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` | ✅ |

全部 14 SHA-256 与 Controller validation 完全一致，10 个 immutable target 未漂移。

## R12-S2-CR-F01 closure verdict — 已关闭

### 挑战：EnvironmentPersistenceInterrupted 继承 KeyboardInterrupt 后的 redaction / exit 130 / contract scope

**redaction**：`EnvironmentPersistenceInterrupted.__init__` 只接收 `EnvironmentPersistenceResult`，其字段为 `status`、`target`、`written_names`、`unwritten_names`。`EnvironmentPersistenceEntry.value` 标记为 `field(repr=False)`。全文搜索确认 exception/result/repr/CLI output 中不包含 secret value。

**exit 130**：`commands/init.py:203` 的 `except KeyboardInterrupt: return EXIT_KEYBOARD_INTERRUPT` 捕获 `EnvironmentPersistenceInterrupted`（因为它是 `KeyboardInterrupt` 子类）。外层 handler 不区分 typed/plain interrupt，两者均返回 `130`。

**contract scope**：`EnvironmentPersistenceInterrupted` 不引入通用 cancellation framework、callback、factory、profile object 或兼容分支。`rg -n "cancellation|callback|factory|compat|fallback|shim|hasattr|getattr|implicit.*default|test.*seam"` 在四个 fix 文件中零匹配。

### 挑战：POSIX write/fsync/replace before/after、verification/injection interrupt、identity drift、cleanup unlink

**write/fsync/replace before/after**：`_write_profile_atomically`（lines 570-642）在 `mkstemp` 后立即从 fd 获取 `st_dev/st_ino` 存入 `_ProfileTemporaryIdentity`。`except KeyboardInterrupt` 块（lines 609-627）：
1. 调用 `_profile_replace_applied` 判断 replace 是否已生效（source identity 消失 + destination identity 匹配）。
2. 若 `file_descriptor >= 0` 则 `os.close(fd)`（fdopen 的 `__exit__` 已把 fd 设为 -1，因此 `os.fdopen` 正常关闭后不会 double-close）。
3. 调用 `_cleanup_owned_profile_temporary` 只删除仍匹配 owner identity 的 temp；identity 漂移时跳过。
4. 抛出 `EnvironmentPersistenceInterrupted`，携带精确的 `written_names`/`unwritten_names`。

**replace after-effect 对账**：`_profile_replace_applied`（lines 645-665）用 `_profile_path_has_identity` 做 no-follow `lstat` 比较 `st_dev/st_ino/st_mode`。source 消失 + destination 匹配 = 已发布。source 仍存在 = 未发布。source identity 漂移 = 未证实（fail closed 为未发布）。

**identity drift**：`test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement`（lines 820-864）mock `os.replace` 删除 owner temp 后写入同名未知内容再中断。断言：未知 replacement 不被删除、retained 文件不含 secret、profile absent。

**cleanup unlink**：`_cleanup_owned_profile_temporary`（lines 668-688）先验证 identity 再 unlink，unlink 失败（`OSError`）静默返回——不覆盖原始中断。

**verification interrupt**：`_persist_posix_environment`（lines 348-361）在 `_verify_written_profile` 调用处 catch `KeyboardInterrupt`，此时 profile 已发布，`written_names=names`、`unwritten_names=()`。正确。

**injection interrupt**：`persist_environment`（lines 298-309）在 `os.environ[entry.name] = entry.value` 循环处 catch `KeyboardInterrupt`，此时 OS store 已全部成功，`written_names=result.written_names`。正确。

**secret temp 遗留**：`test_posix_atomic_faults_preserve_store_truth_and_remove_owned_secret_temp` 覆盖 write/fsync/replace × before/after × os-error/interrupt = 12 种场景。所有场景断言 `not tuple(tmp_path.glob(".dayu-init-env-*"))`。replace-after-effect 中断场景断言 `written_names=(entry.name,)`、profile 含 secret（已发布）、temp 为空。

**F01 结论**：已关闭。POSIX persistence interrupt 在所有边界（write/fsync/replace before/after、verification、injection、identity drift）均正确清理 owner temp 并携带 redacted typed truth。

## R12-S2-CR-F02 closure verdict — 已关闭

### 挑战：Windows first/middle/last setx 及 store 完成后 injection interrupt 的 written/unwritten truth

**first/middle/last setx 中断**：`_persist_windows_environment`（lines 370-409）在 `subprocess.run` 调用处 catch `KeyboardInterrupt`（lines 391-398）。`written_names` list 已累积成功项，`unwritten_names` 从当前索引到末尾。`test_windows_interrupt_reports_written_and_unwritten_names_without_values`（lines 1017-1053）参数化 `interrupt_at=(0,1,2)` 覆盖 first/middle/last。断言 `written_names=entries[:interrupt_at]`、`unwritten_names=entries[interrupt_at:]`、调用次数 `=interrupt_at+1`、零注入、values 不在 repr/result 中。

**store 完成后 injection interrupt**：`persist_environment`（lines 298-309）在 `os.environ` 注入循环 catch `KeyboardInterrupt`。`test_windows_environment_injection_interrupt_keeps_completed_store_truth`（lines 1056-1085）用 `_InterruptingEnvironment(interrupt_at=0)` 在首个 `__setitem__` 中断。断言 `written_names=all`、`unwritten_names=()`、`environment=={}`（注入未完成）。

**不伪造 registry rollback**：`EnvironmentPersistenceInterrupted` 不尝试回滚 `setx` 已写入的 registry。Windows registry mutation 不可回滚是已知约束（fixed plan §10.1 retained residual）。

**不泄露 values/captured output**：`_interrupted_result`（lines 711-731）只构造 `EnvironmentPersistenceResult`，不携带 entry values 或 subprocess stdout/stderr。`_SetxRecorder` 捕获的 `stdout=b"ignored stdout"` 不进入 result。

**F02 结论**：已关闭。Windows first/middle/last setx 中断与 store 后 injection 中断均精确报告 written/unwritten names，不泄露 values，不伪造 rollback。

## R12-S2-CR-F03 closure verdict — 已关闭

### 挑战：CLI typed/plain interrupt、abort success/failure、diagnostic print failure 顺序

**typed interrupt 路径**：`commands/init.py:168-171` catch `EnvironmentPersistenceInterrupted` → `_report_persisted_environment_names(exc.result)` → `_abort_prepared_transaction_after_persistence_interrupt(prepared)` → `raise`。外层 `except KeyboardInterrupt` 返回 `EXIT_KEYBOARD_INTERRUPT`（130）。

**plain interrupt 路径**：`commands/init.py:172-174` catch `KeyboardInterrupt` → `_abort_prepared_transaction_after_persistence_interrupt(prepared)` → `raise`。外层返回 130。无 written names 报告（plain interrupt 不携带 typed truth）。

**abort success**：`_abort_prepared_transaction_after_persistence_interrupt`（lines 583-597）调用 `abort_prepared_workspace_transaction(prepared)`。成功时静默返回。`test_persistence_interrupt_aborts_real_prepared_transaction_and_exits_130`（lines 471-520）断言 `exit==130`、`config absent`、`.dayu absent`、`no .dayu-init-transaction-*`。

**abort failure**：abort helper catch `InitWorkspaceError` → `print(_format_operation_error(exc), file=sys.stderr)`。`test_persistence_interrupt_abort_failure_reports_retained_truth_and_exits_130`（lines 523-582）mock abort 为 `fail_abort`，断言 `exit==130`、`retained transaction present`、`pre_publication_abort_cleanup` 在 stderr、`OPENAI_API_KEY` 在 stderr、`.dayu=absent` 在 stderr。

**diagnostic print failure 顺序**：若 `_report_persisted_environment_names` 的 `print(..., file=sys.stderr)` 抛 `OSError`，该异常会传播到 `_abort_prepared_transaction_after_persistence_interrupt` 之外，被外层 `except KeyboardInterrupt` 之前的 `except OSError` 捕获，返回 `EXIT_FAILURE`（1）而非 `EXIT_KEYBOARD_INTERRUPT`（130）。这会改变 exit code。

**但这不是新问题**：原 S2 code 的 `except (EnvironmentPersistenceError, OSError): abort_prepared_workspace_transaction(prepared); raise` 路径中，abort 成功后 re-raise 原 `EnvironmentPersistenceError`，被外层 `except CliInitOperationError, ... EnvironmentPersistenceError ...` 捕获并 `print(..., file=sys.stderr)`。若此 print 失败，同样会改变 exit code。这是 pre-existing 的 stderr write failure 传播模式，不是 F03 fix 引入的回归。

**abort 不阻止**：abort helper 不 re-raise `InitWorkspaceError`，只 print diagnostic。因此 abort 失败不会阻止原 interrupt 传播。`raise` 在 `except EnvironmentPersistenceInterrupted` 块末尾重新抛出原 typed interrupt。

**F03 结论**：已关闭。plain/typed persistence interrupt 均 identity-safe abort prepared transaction 并保持 exit 130。abort failure 保留 retained truth。diagnostic print failure 改变 exit code 是 pre-existing stderr 传播模式，不是 F03 回归。

## Mandatory review challenges

### Challenge 1: 全部 14-path cumulative target 重新审查

全部 14 路径 SHA-256 核验通过。10 个 immutable target 未漂移。4 个 fix paths 行/字节与 Controller validation 一致。

`init_workspace.py` 的四态 contract（snapshot TOCTOU、rename-after-effect、rollback、cleanup、KeyboardInterrupt boundary、symlink/reparse、durability、portfolio truth）已在 S2 初审中验证，本次 re-review 确认其代码未被修改（SHA-256 一致）。

`host_assembly.py` 的 Service Fins override raw grammar、ordinary `None`、非 Fins/Web 隔离、未偷带统一 authorization 已在 S2 初审中验证，本次确认未修改。

`entrypoint_runtime.py` 显式 `fins_workspace_root_override=None` 已确认未修改。

`arg_parsing.py`、`init_catalog.py`、`Service README` 已确认未修改。

`test_init_catalog.py`、`test_init_workspace.py`、`test_arg_parsing.py`、`test_host_assembly.py` 已确认未修改。

### Challenge 2: S3 stale caller / prewarm / real smoke / README / workflow 未偷带

- `test_prompt_command_uses_init_generated_workspace_config` 仍在 `tests/cli/test_prompt_command.py:1211`，未被修改或删除。
- `rg -n "prewarm|importlib\.import_module|test_init_smoke"` 在 `dayu/cli/` 和 `tests/cli/` 中零匹配。
- `tests/cli/test_init_smoke.py` 不存在（ABSENT）。
- `.github/workflows/r12-init-windows.yml` 不存在（ABSENT）。
- 根 `README.md`、`dayu/config/README.md`、`tests/README.md` 未被修改。
- `rg -n "cancellation|callback|factory|compat|fallback|shim|hasattr\(|getattr\(|implicit[_ -]?default|test[_ -]?seam"` 在四个 fix 文件中零匹配。

**结论**：S3 mandatory residual 严格保持，无 production implicit default / compatibility fallback 偷带。

### Challenge 3: EnvironmentPersistenceInterrupted 的 KeyboardInterrupt 继承

- 类定义（`init_environment.py:176-195`）：`class EnvironmentPersistenceInterrupted(KeyboardInterrupt)`。
- `__init__` 只设置 `self.result`，调用 `super().__init__("environment persistence interrupted")`。
- `result` 字段类型为 `EnvironmentPersistenceResult`（frozen dataclass），只含 `status/target/written_names/unwritten_names`。
- 外层 `commands/init.py:203` `except KeyboardInterrupt` 捕获它并返回 `EXIT_KEYBOARD_INTERRUPT`。
- 没有引入 `__reduce__`、`__str__` override 或其他可能泄露 secret 的方法。

**结论**：继承链正确，exit 130 不漂移，contract scope 最小。

## Findings

未发现实质性问题。

F01-F03 修复在各自 semantic owner 内正确实现。所有 mandatory challenge 通过。无新 material finding。

## Open Questions

无。

## Residual Risk

1. **S3 mandatory entry residual**：`test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 仍为 stale caller，S3 必须迁移。已确认仅此一处。
2. **S3 未实现项**：prewarm、POSIX real smoke、Windows real smoke（含 junction/rollback）、Windows CI workflow、root/tests/config README、full CLI regression 仍需 S3。
3. **Windows parent-directory fsync 缺失**：fixed-plan retained residual。
4. **RESET 两根非 single-syscall atomic**：fixed-plan retained residual。
5. **`.dayu-init.lock` 只串行 init**：fixed-plan retained residual。
6. **OS environment 与 workspace 非同一事务**：fixed-plan retained residual。
7. **diagnostic print failure 改变 exit code**：pre-existing stderr 传播模式，非 F03 回归。

## Verdict

**PASS — 零 defect finding，F01-F03 均已关闭，零新 S2 accepted-fix candidate。**

R12 S2 fix 后的 cumulative implementation 在 POSIX persistence interrupt（F01）、Windows partial setx interrupt（F02）、CLI persistence interrupt abort（F03）三个 mandatory challenge 上全部通过直接代码证据验证。`EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt` 后仍只含 redacted names/target、exit 130 不漂移、没有引入通用 cancellation framework。所有 S3 mandatory residual 严格保持，无偷带。

**Finding counts**：0 LOW，0 MEDIUM，0 HIGH，0 CRITICAL

**F01 closure**：✅ closed
**F02 closure**：✅ closed
**F03 closure**：✅ closed

**Artifact path**：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-mimo.md`
