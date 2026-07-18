# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 Complete Cumulative Code Re-Review — AgentDS

## Gate 身份

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 complete cumulative code re-review，不是新 WU。
- Authority：fixed plan `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`、Controller adjudication `fa0212521fc643eb041a5d8f651a420aae0e214872fd347696c1ed3f3e8b3666`、AgentCodex fix artifact `3a05658d3e5383223f04ef78d82135305597413a33fa263b1715abf4d48f4025`、Controller validation fixed target hashes。
- 只 review，不改产品/测试/plan/control/Controller artifacts。不 stage/commit/push/进入 S3。

## Scope

- Mode: cumulative 14-path target re-review（Controller validation 固定）
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-ds.md`
- Included scope: 14 个 Controller validation 固定的 cumulative target 路径（7 production + 7 test）
- Excluded scope: control/review/plan artifacts、design docs、package JSON/manifests、Host/Engine/Fins/Tool production、S3-only paths、`workspace/tmp/`

### 14-path cumulative target identity verification

| 路径 | 行 / 字节 | SHA-256 | 与 Controller validation 一致 |
|---|---:|---|---|
| `dayu/cli/init_catalog.py` | — | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✓ |
| `dayu/cli/init_environment.py` | 776 / 29,178 | `55756e0662d203811a84325cb79c3a42ea13592b790ec02966f361e670e71a40` | ✓ |
| `dayu/cli/init_workspace.py` | — | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` | ✓ |
| `dayu/cli/commands/init.py` | 689 / 25,789 | `3acbbec9049c91fd238a167a7a5a708a03be9b49a73f03907a710f32dffd56ce` | ✓ |
| `dayu/cli/arg_parsing.py` | — | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` | ✓ |
| `dayu/service/host_assembly.py` | — | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` | ✓ |
| `dayu/service/entrypoint_runtime.py` | — | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` | ✓ |
| `dayu/service/README.md` | — | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` | ✓ |
| `tests/cli/test_init_catalog.py` | — | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | ✓ |
| `tests/cli/test_init_environment.py` | 1,146 / 44,114 | `406ad395bfa8e6c644bca8f7a9349181bdabfd770a7e2ea1772828d54379eed6` | ✓ |
| `tests/cli/test_init_workspace.py` | — | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` | ✓ |
| `tests/cli/test_init_command.py` | 832 / 29,097 | `5f229547219f34db0116d8fed5a764ab2d741ae47423e62166bb4b1bca6f72cb` | ✓ |
| `tests/cli/test_arg_parsing.py` | — | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` | ✓ |
| `tests/service/test_host_assembly.py` | — | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` | ✓ |

**14/14 路径 hash 与 Controller validation 固定 target 精确一致；零漂移。**

## R12-S2-CR-F01..F03 逐项 closure 判定

### R12-S2-CR-F01 — HIGH — POSIX persistence interrupt 遗留含 secret 的 private temp

**Verdict: CLOSED。**

审查路径：`_write_profile_atomically`（`init_environment.py:570-642`）及其测试覆盖 `test_posix_atomic_faults`（`test_init_environment.py:713-817`）。

逐边界验证：

| 注入点 | 故障类型 | 测试覆盖 | private temp 清理 | profile durable truth | secret 泄漏 |
|---|---|---|---|---|---|
| write before | `OSError` | ✓ `operation=write,timing=before` | ✓ identity-locked unlink | absent | 否 |
| write before | `KeyboardInterrupt` | ✓ | ✓ identity-locked unlink | absent | 否 |
| write after | `OSError` | ✓ `operation=write,timing=after` | ✓ | absent | 否 |
| write after | `KeyboardInterrupt` | ✓ | ✓ | absent | 否 |
| fsync before | `OSError` | ✓ `operation=fsync,timing=before` | ✓ | absent | 否 |
| fsync before | `KeyboardInterrupt` | ✓ | ✓ | absent | 否 |
| fsync after | `OSError` | ✓ `operation=fsync,timing=after` | ✓ | absent | 否 |
| fsync after | `KeyboardInterrupt` | ✓ | ✓ | absent | 否 |
| replace before | `OSError` | ✓ `operation=replace,timing=before` | ✓ | absent | 否 |
| replace before | `KeyboardInterrupt` | ✓ | ✓ | absent | 否 |
| replace after | `OSError` | ✓ `operation=replace,timing=after` | ✓ | succeeded（正确） | 否 |
| replace after | `KeyboardInterrupt` | ✓ | ✓ | succeeded（`written_names=all`） | 否 |

**Identity drift 防护**（`init_environment.py:667-688`）：
- `_cleanup_owned_profile_temporary` 采用 no-follow `st_dev/st_ino` identity 比对（`_profile_path_has_identity`），只删除仍由本次 writer 持有的 private temp。
- `test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement`（test:820-864）证明：identity 漂移后的同名 replacement 不被按名删除，且 replacement 不含 owner secret。
- 测试中存在 retained unknown file（`not-owner-secret-material`），但该文件不含原始 secret。这是 fail-safe 行为——宁留 unknown 不误删。

**Replace-after-effect 对账**（`_profile_replace_applied`, line 645-665）：
- 检测逻辑：source 消失 AND destination 持有 owner identity → replace 已生效。
- `os.lstat` 异常保守返回 `False`（不匹配），确保无法判定时按"未发布"处理并清理 temp。这不会导致已发布 profile 被误删（因为 temp 路径已被 replace 移走）。

**写后校验中断**（`_persist_posix_environment:348-361`）：
- `_verify_written_profile` 中断时正确报告 `written_names=names, unwritten_names=()`——profile 已原子发布，只是进程内尚未注入。
- `test_post_write_structure_verification_precedes_environment_injection` 覆盖普通校验失败。

**Redaction contract**：
- `EnvironmentPersistenceInterrupted.result` 只含 `target`、`written_names`、`unwritten_names`，不含 values/captured output。
- `EnvironmentPersistenceInterrupted.__init__` 的 `super().__init__("environment persistence interrupted")` 不含 secret。
- 所有 12 个 fault 组合的测试都断言 `entry.value not in repr(captured.value)`、`entry.value not in repr(result)`、`entry.name not in os.environ`。

**F01 closure 确认**：private temp 在所有 write/fsync/replace 边界均被 identity-locked 清理，含 secret 的 temp 不留存，exception/repr 不含 secret，replace-after-effect 正确对账。

### R12-S2-CR-F02 — HIGH — Windows partial `setx` interrupt 丢失 written-names durable truth

**Verdict: CLOSED。**

审查路径：`_persist_windows_environment`（`init_environment.py:370-409`）及 `persist_environment` 注入阶段（line 298-309）。

逐场景验证：

| 场景 | 测试 | `written_names` | `unwritten_names` | env 注入 | values 泄漏 |
|---|---|---|---|---|---|
| first `setx` interrupt | `test_windows_interrupt...[first]` | `()` | `ALL` | 否 | 否 |
| middle `setx` interrupt | `test_windows_interrupt...[middle]` | `(entries[0],)` | `(entries[1], entries[2])` | 否 | 否 |
| last `setx` interrupt | `test_windows_interrupt...[last]` | `(entries[0], entries[1])` | `(entries[2],)` | 否 | 否 |
| store 完成后 injection interrupt | `test_windows_environment_injection_interrupt_keeps_completed_store_truth` | `ALL` | `()` | 部分（但未完成注入） | 否 |

**关键实现细节**：
- `written_names` 只在 `returncode == 0` 后才追加（line 403），确保只记录 OS store 已确认成功的名称。
- 中断时 `written_names` 精确为已确认前缀，`unwritten_names` 为当前项及后续项（line 396）。
- `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt`，不伪造 registry rollback。
- Windows `setx` 使用 `shell=False, capture_output=True, text=False`——captured stdout/stderr 不进入 result/exception。
- 全部 `setx` 成功后的进程内注入中断：`_InterruptingEnvironment` 测试证明 `written_names=ALL`（durable store 已完成）、`os.environ` 未注入任何值、`written_names` 如实报告。

**F02 closure 确认**：Windows first/middle/last `setx` 中断及 store 完成后 injection interrupt 均保留最小脱敏名称真值，不伪造 registry rollback，不泄露 values/captured output。

### R12-S2-CR-F03 — MEDIUM — persistence interrupt 未 abort prepared workspace transaction

**Verdict: CLOSED，附一个新 finding。**

审查路径：`run_init_command`（`commands/init.py:166-174`）及 `_abort_prepared_transaction_after_persistence_interrupt`（line 583-596）。

**已修复部分**：
- Plain `KeyboardInterrupt` path（line 172-174）：调用 `_abort_prepared_transaction_after_persistence_interrupt(prepared)` → re-raise → 外层 `except KeyboardInterrupt`（line 203）→ `return EXIT_KEYBOARD_INTERRUPT (130)`。
- Typed `EnvironmentPersistenceInterrupted` path（line 168-171）：调用 `_report_persisted_environment_names(exc.result)` → `_abort_prepared_transaction_after_persistence_interrupt(prepared)` → re-raise → 外层 `except KeyboardInterrupt`（line 203）→ `return EXIT_KEYBOARD_INTERRUPT (130)`。
- `test_persistence_interrupt_aborts_real_prepared_transaction_and_exits_130`（test:471-520）覆盖 plain 与 typed 两条路径，断言 exit 130、零 public config、零 `.dayu-init-transaction-*`。
- `test_persistence_interrupt_abort_failure_reports_retained_truth_and_exits_130`（test:523-582）覆盖 abort 失败路径，断言 retained path truth 仍输出、exit 仍为 130。
- `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt`——外层 `except KeyboardInterrupt` 统一捕获，返回 130。无通用 cancellation framework 引入。

**未修复部分（新 finding）**：见下方 R12-S2-RR-F01。

**F03 closure 确认**：plain/typed persistence interrupt 均 identity-safe abort prepared transaction 并返回 exit 130；abort 失败保留 truthful retained-path diagnostic。主体已关闭。唯一的残留风险是 diagnostic print 失败可阻止 abort（见新 finding）。

---

## Findings

### R12-S2-RR-F01 — MEDIUM — typed interrupt 路径 diagnostic print 先于 abort，print 失败可阻止 transaction cleanup 并改变 exit code

- **入口/函数**: `run_init_command`（`commands/init.py:166-174`）
- **文件(行号)**: `dayu/cli/commands/init.py:168-170`
- **输入场景**: persistence 抛出 `EnvironmentPersistenceInterrupted`（携带 written names），且 stderr 不可写（broken pipe、ENOSPC、权限错误等）
- **实际分支**: `except EnvironmentPersistenceInterrupted as exc:` → `_report_persisted_environment_names(exc.result)`（line 169）先于 `_abort_prepared_transaction_after_persistence_interrupt(prepared)`（line 170）
- **预期行为**: identity-safe abort 必须在任何可能失败的 diagnostic I/O 之前执行，或至少通过 try/finally 确保 abort 不被 diagnostic failure 阻止
- **实际行为**: `_report_persisted_environment_names`（line 564-580）在 `result.written_names` 非空时调用 `print(..., file=sys.stderr)`。若此 `print` 抛出 `OSError`，异常从 `except EnvironmentPersistenceInterrupted` 块内传播，替换原 `EnvironmentPersistenceInterrupted` 为 `OSError`（Python 3.11 异常链规则：except 块内新异常成为活跃异常，原异常降为 `__context__`）。结果：
  1. `_abort_prepared_transaction_after_persistence_interrupt(prepared)` 永远不会被调用 → `.dayu-init-transaction-*` 目录残留在 workspace
  2. 外层 `except OSError`（line 214）捕获新异常 → 返回 `EXIT_FAILURE(1)` 而非 `EXIT_KEYBOARD_INTERRUPT(130)`
  3. 已持久化的环境变量名（`written_names`）未被报告
- **直接证据**:
  - `commands/init.py:168-170`：`_report_persisted_environment_names` 在 `_abort_prepared_transaction_after_persistence_interrupt` 之前，无 try/finally 保护
  - `commands/init.py:574-579`：`_report_persisted_environment_names` 的 `print` 调用无 try/except OSError 防护
  - `commands/init.py:203`：`except KeyboardInterrupt` 在外层——`OSError` 不匹配此分支
  - `commands/init.py:214`：`except OSError as exc:` 在外层——会捕获 stderr 写入失败的 `OSError`
  - 对比 plain `KeyboardInterrupt` 路径（line 172-174）：直接调用 `_abort_prepared_transaction_after_persistence_interrupt`，无前置 diagnostic print，因此不受此问题影响
- **影响**: 在 stderr 不可写 + persistence 中断 + 存在已写 env names 的罕见组合下，prepared transaction 清理被跳过，workspace 残留 `.dayu-init-transaction-*`，exit code 由 130 变为 1。transaction 目录本身不含 secret（secret 仅在 `init_environment` 内部），但违反 fixed plan "任一 publish 故障或 KeyboardInterrupt 后 managed roots 恢复为发布前逐字节内容" 的 contract。
- **建议改法和验证点**:
  1. 交换顺序：先 `_abort_prepared_transaction_after_persistence_interrupt(prepared)`，后 `_report_persisted_environment_names(exc.result)`。abort 路径本身只在 abort 失败时才 print（且已在 `_abort_prepared_transaction_after_persistence_interrupt` 内部 try/except 捕获），正常情况下不产生 I/O。
  2. `_report_persisted_environment_names` 内部对 `OSError` 做防御性 catch（`try: print(...) except OSError: pass`），确保 diagnostic 永远不阻止控制流。
  3. 验证点：mock stderr 为 broken pipe，注入 typed interrupt，断言 abort 已执行（`.dayu-init-transaction-*` 不存在）、exit 仍为 130、`OSError` 不被外层误捕获。
- **修复风险（低）**: 纯 ordering + defensive catch，不改变 semantic owner boundary、不引入新 abstraction。
- **严重程度（中）**: 触发条件罕见（broken stderr + persistence interrupt + written names），但后果明确（transaction 泄露 + exit code 改变），违反 fixed plan abort contract。

---

## Mandatory Controller Challenge 验证

### Challenge 1: `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt` 后的 redaction/exit 130/contract scope

**Verdict: PASS。**

- `EnvironmentPersistenceInterrupted(KeyboardInterrupt)`（`init_environment.py:176`）——`isinstance(exc, KeyboardInterrupt)` 为 `True`，外层 `except KeyboardInterrupt` 统一捕获并返回 `EXIT_KEYBOARD_INTERRUPT (130)`（`exit_codes.py:11`）。
- `result: EnvironmentPersistenceResult` 只含 `target`、`written_names`、`unwritten_names`——不含 values、captured output、registry/profile content。
- `__init__` 的 `super().__init__("environment persistence interrupted")` 不含 secret。
- 无新增 public schema、通用 cancellation framework、callback/factory/profile。
- 唯一风险点即 R12-S2-RR-F01（diagnostic print 先于 abort 且 print 可失败改变 exit code）。

### Challenge 2: POSIX write/fsync/replace before/after、verification/injection interrupt、identity drift、cleanup unlink 或 identity-read uncertainty 是否可能遗留 secret

**Verdict: PASS — 无 secret 遗留路径。**

- write/fsync/replace 共 12 种故障组合全部由 `test_posix_atomic_faults` 覆盖，每种组合都断言 `entry.value not in repr(...)`、`entry.name not in os.environ`、`not tuple(tmp_path.glob(".dayu-init-env-*"))`。
- Replace-after-effect 对账（`_profile_replace_applied`）正确区分"已发布"与"未发布"，并在已发布时如实报告 `written_names=all`。
- `_cleanup_owned_profile_temporary` 的 `_profile_path_has_identity` 对 `os.lstat` 异常保守返回 `False`——identity 不确定时不删除，fail-safe 但可能遗留不含 secret 的 unknown 对象（如 identity drift test 中 retained 的 `not-owner-secret-material`）。
- 最坏情况：filesystem 严重故障使所有 lstat 调用失败——temp 可能不被清理，但 (1) 该场景是 catastrophic failure，不在 R12 single-fault contract 内；(2) temp 为 `0600`、含 secret 但位于只有 owner 可读的 HOME 目录。与 fixed plan §10.1 residual 一致。
- `_verify_written_profile` 中断正确报告 `written_names=all`（profile 已发布），不泄露值。

### Challenge 3: Windows first/middle/last `setx` 及 store 完成后 injection interrupt 的 written/unwritten truth

**Verdict: PASS。**

- first（`interrupt_at=0`）：`written_names=()`、`unwritten_names=ALL`。
- middle（`interrupt_at=1`）：`written_names=(entries[0],)`、`unwritten_names=(entries[1], entries[2])`。
- last（`interrupt_at=2`）：`written_names=(entries[0], entries[1])`、`unwritten_names=(entries[2],)`。
- Store 完成后 injection interrupt：`written_names=ALL`、`unwritten_names=()`、`os.environ` 未注入。
- 所有路径通过 `EnvironmentPersistenceInterrupted` 携带脱敏名称真值，不伪造 registry rollback，不泄露 values/captured output。
- `setx` 调用使用 `shell=False, capture_output=True, text=False`——captured stdout/stderr 不进入任何 result/exception。

### Challenge 4: CLI typed/plain interrupt、abort success/failure、diagnostic print failure 顺序是否可能阻止 abort 或改变 truth

**Verdict: PASS with one finding (R12-S2-RR-F01)。**

- Plain interrupt 路径（line 172-174）：直接 abort，无前置 diagnostic，safe。
- Typed interrupt 路径（line 168-171）：diagnostic print 先于 abort——见 R12-S2-RR-F01。
- `_abort_prepared_transaction_after_persistence_interrupt` 内部：abort 失败时 print diagnostic，但 print 在 `except InitWorkspaceError` 内——若此 print 也失败，`OSError` 同样改变 exit code。但此时 abort 已尝试（只是失败），transaction 的 retained state 是 truthful 的。
- Abort 成功时：零 I/O，不改变 exit code。

### Challenge 5: S3 stale caller/prewarm/real smoke/README/workflow 确认未偷带

**Verdict: PASS — 全部未偷带。**

| 检查项 | 方法 | 结果 |
|---|---|---|
| `importlib.import_module` / prewarm | `rg` production | 零命中 |
| `tests/cli/test_init_smoke.py` | `ls` | 不存在 |
| `.github/workflows/r12-init-windows.yml` | `ls` | 不存在 |
| `README.md` / `dayu/config/README.md` / `tests/README.md` init 更新 | `git diff` | 未修改（S3 scope） |
| `test_prompt_command_uses_init_generated_workspace_config` | Controller adjudication 记录 | 仍为 S3 mandatory residual，S2 无 implicit default/fallback |
| `cancell?ation\|callback\|factory\|compat\|fallback\|shim\|hasattr\(\|getattr\(\|implicit[_ -]?default\|test[_ -]?seam` | `rg` fix files | 零命中 |
| Full 14-path hash | `shasum -a 256` | 精确等于 Controller validation fixed targets |
| Immutable 10 fixed targets | `shasum -a 256` | 精确等于 Controller validation fixed targets |

---

## Open Questions

无。所有 Controller mandatory challenges 已通过直接代码证据完成审查。

## Residual Risk

### R12-S2-DS-RR-R01 — diagnostic print failure 可阻止 transaction abort（本 review new finding）

- Owner: `dayu/cli/commands/init.py` `run_init_command` typed interrupt handler
- Finding: R12-S2-RR-F01
- Severity: MEDIUM
- 触发条件: broken stderr + persistence interrupt + written env names
- 当前状态: 未被已有测试覆盖

### R12-S2-DS-RR-R02–R06 — 继承自原始 DS review 的 S3/fixed-plan residual（不变）

| ID | 描述 | Owner |
|---|---|---|
| R02 | S3 prewarm/smoke/README/full CLI | S3 |
| R03 | Windows directory crash-durability | fixed plan §10.1 |
| R04 | RESET 两根非 single-syscall atomic | fixed plan §10.1 |
| R05 | `.dayu-init.lock` 只串行 init | fixed plan §10.1 |
| R06 | OS environment 与 workspace 非同一事务 | fixed plan §10.1 |

### R12-S2-DS-RR-R07 — `_abort_prepared_transaction_after_persistence_interrupt` 内部 diagnostic print 也可在极端条件下改变 exit code

- 当 abort 本身失败（`InitWorkspaceError`）且 stderr 不可写时，`print(_format_operation_error(exc), file=sys.stderr)` 抛出 `OSError`，改变 exit code 从 130 到 1。但 abort 已被尝试（只是失败），retained path truth 仍是真实的。严重程度低于 R12-S2-RR-F01。可在修复 R12-S2-RR-F01 时一并防御。

---

## Verdict

**PASS_WITH_FINDINGS — R12-S2-CR-F01..F03 已关闭，1 个新 MEDIUM finding。**

- `R12-S2-CR-F01`（POSIX secret temp 遗留）: **CLOSED** — 12-path fault matrix + identity drift + replace-after-effect 全部正确。
- `R12-S2-CR-F02`（Windows written-names 丢失）: **CLOSED** — first/middle/last + injection interrupt 全部正确。
- `R12-S2-CR-F03`（transaction abort 缺失）: **CLOSED** — plain/typed interrupt 均 abort 并 exit 130。唯一残留即新 finding R12-S2-RR-F01。
- 新 finding: **1 MEDIUM**（R12-S2-RR-F01: diagnostic print ordering 可阻止 abort）。
- 14-path cumulative target: **全部 hash 精确一致，零漂移。**
- S3 boundary: **全部确认未偷带** —— prewarm、smoke、Windows workflow、README、stale caller 均严格属于 S3。
- Design contradiction: **NONE**。
- Blocking questions: **NONE**。

## Finding counts

- Accepted findings re-verified closed: 3 (F01, F02, F03)
- New findings: 1 MEDIUM (R12-S2-RR-F01)
- Total open findings: 1

## Artifact identity

- Path: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-ds.md`
