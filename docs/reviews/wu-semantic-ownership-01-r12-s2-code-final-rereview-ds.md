# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 complete cumulative code final re-review — AgentDS

## Scope

- **Mode**: complete cumulative re-review of accepted-finding fix，不是新 WU。
- **WU**: umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2。
- **Fixed plan**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`（SHA `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`）。
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-controller-adjudication.md`。
- **Agent fix**: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-fix-codex.md`（SHA `9b38c2759a16503230766ecc95092681dd4271364d790e612b677e48288405e4`）。
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-fix-controller-validation.md`（53行/4,347字节/SHA `c9b51d06accae8ef3d2fba2ed598d3f5bd7efc0af4dd9cfe33ed97a029857906`）。
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r12-s2-code-final-rereview-ds.md`。
- **Review date**: 2026-07-18T13:22:56+08:00。

### 14-Path S2 Target Identity

#### 4 Fixed Hashes（本轮 accepted-finding fix 修改）

| 路径 | 行 | 字节 | SHA-256 | 验证 |
|---|---:|---:|---|---|
| `dayu/cli/init_environment.py` | 835 | 31,429 | `16353a72bce2efeeac1aae64f1f0c94cdca2e30e956be9412f2f0f20002059c0` | ✓ |
| `dayu/cli/commands/init.py` | 743 | 27,820 | `fe5d4a434ccd5b528ef61cf80295652bbcc4bfa961bd0be3c6dc2aecf95a3e19` | ✓ |
| `tests/cli/test_init_environment.py` | 1,245 | 48,353 | `5bc46652d54ae5e6860424c3acb952ce2dd615cb0df09eb1ae5c3b6c1f184618` | ✓ |
| `tests/cli/test_init_command.py` | 964 | 34,238 | `25de81a149fcaee079c1e693b278258390d1710d87617e350abbe5abd914a4b2` | ✓ |

#### 10 Immutable Hashes（Controller validation 确认未漂移）

| 路径 | SHA-256 | 验证 |
|---|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | ✓ |
| `dayu/cli/init_workspace.py` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` | ✓ |
| `dayu/cli/arg_parsing.py` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` | ✓ |
| `dayu/service/host_assembly.py` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` | ✓ |
| `dayu/service/entrypoint_runtime.py` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` | ✓ |
| `dayu/service/README.md` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` | ✓ |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | ✓ |
| `tests/cli/test_init_workspace.py` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` | ✓ |
| `tests/cli/test_arg_parsing.py` | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` | ✓ |
| `tests/service/test_host_assembly.py` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` | ✓ |

### 审查范围

全部 14 个 S2 implementation paths 已逐文件完整走读。4 个 fixed-hash 文件逐函数展开入参→条件→下游调用→返回值/raise→副作用；10 个 immutable-hash 文件做 adversarial 交叉验证，检查跨 owner 语义泄漏、S3 boundary 偷带与既有设计 contract 漂移。

### Parallel review coverage

无。本 artifact 由 AgentDS 单路完成。

## Accepted Finding Closure 裁决

### R12-S2-RR-F01 — CLOSED / VERIFIED

**直接证据**：

- `commands/init.py:168-173`：typed `EnvironmentPersistenceInterrupted` 分支先调用 `_try_abort_prepared_transaction(prepared)`（L169），再做 `_report_persisted_environment_names`、`_report_retained_environment_paths`、`_report_abort_failure`（L170-172），最后 `raise` 重新抛出原中断（L173）。
- `commands/init.py:174-177`：plain `KeyboardInterrupt` 分支同样先 abort（L175），再 `_report_abort_failure`（L176），最后 `raise`（L177）。
- `commands/init.py:178-182`：`EnvironmentPersistenceError` 分支先 abort（L179），再 report retained paths（L180）、report abort failure（L181），最后 `raise`（L182）。
- `commands/init.py:183-186`：`OSError` 分支同样先 abort（L184），再 report（L185），最后 `raise`（L186）。
- `commands/init.py:187-192`：Windows non-success result 分支先 abort（L188），再 report names/retained/abort（L189-191），最后 `raise CliInitOperationError`（L192）。
- `commands/init.py:609-623`：`_try_abort_prepared_transaction` 不执行任何 diagnostic I/O，只调用 `abort_prepared_workspace_transaction` 并捕获 `InitWorkspaceError` 返回 retained truth；其它异常不捕获（这是有意的：abort 中的 `OSError` 或 `KeyboardInterrupt` 会传播，但 `KeyboardInterrupt` 仍被外层 `except KeyboardInterrupt` 捕获并返回 exit 130）。
- `commands/init.py:639-650`：`_report_diagnostic_best_effort` 将所有 diagnostic I/O 异常吸收为 no-op，不覆盖控制流。

**Broken stderr 对抗测试**（`tests/cli/test_init_command.py:637-713`）：

- `test_persistence_interrupt_aborts_before_broken_stderr_and_exits_130` 覆盖 4 组合：typed/plain × abort-success/abort-failure。
- 所有 4 组合 `exit_code == EXIT_KEYBOARD_INTERRUPT`（130）。
- 所有 4 组合 `events[0] == "abort"`（abort 是首个事件）。
- Abort 成功时无 `.dayu-init-transaction-*` 遗留；abort 失败时保留精确 transaction path。
- `_BrokenStderr` 以 `OSError` 拒绝所有 stderr 写入，不改变 exit code。

**裁决**：F01 已关闭。typed/plain persistence interrupt 均先 abort prepared transaction，再输出 best-effort diagnostic；broken stderr 不阻止 abort、不改变 exit 130。abort 自身的 `OSError` 传播仍被外层 `KeyboardInterrupt` handler 保持 exit 130；只有极端场景（POSIX `_sync_directory` 在 abort 后失败抛 `OSError`）可改变 exit code——这是已记录的 §10.1 retained residual，不是 F01 未修复。

### R12-S2-RR-F02 — CLOSED / VERIFIED

**直接证据**：

- `init_environment.py:60-73`：`EnvironmentPersistenceError` 新增 `retained_paths: tuple[Path, ...]` 字段，构造函数 keyword-only 接收。
- `init_environment.py:168-183`：`EnvironmentPersistenceResult` 新增 `retained_paths: tuple[Path, ...]` 字段，字段只携带路径不携带 value/profile 内容。
- `init_environment.py:196-215`：`EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt`，`result.retained_paths` 携带 path-only truth。
- `init_environment.py:710-736`：`_cleanup_owned_profile_temporary` 使用 owner-local no-follow identity 分类：
  - `temporary_path is None` → 返回 `()`
  - `temporary_identity is None` → 返回 `(temporary_path,)`（不确定 identity，不删除）
  - `_classify_profile_path_identity` 返回 `ABSENT` → 返回 `()`（已清理）
  - 返回 `DRIFTED` / `UNREADABLE` → 返回 `(temporary_path,)`（不删除未知对象）
  - 返回 `OWNED` → `os.unlink`；unlink 失败返回 `(temporary_path,)`；成功返回 `()`
- `init_environment.py:739-764`：`_classify_profile_path_identity` 以 `os.lstat` 做 no-follow identity 比对（device + inode + S_ISREG）。`FileNotFoundError` → absent；其它 `OSError`/`KeyboardInterrupt` → unreadable；identity mismatch → drifted。不按名称猜测。
- `init_environment.py:64-68,204-215`：`EnvironmentPersistenceError` 和 `EnvironmentPersistenceInterrupted` 的 `repr` 永远不包含 `EnvironmentPersistenceEntry.value`（因为 `EnvironmentPersistenceEntry.__init__` 用 `field(repr=False)`）。
- `commands/init.py:593-606`：`_report_retained_environment_paths` 只投影路径字符串，不接触 value；CLI owner 不尝试删除 environment owner 的 temp。

**POSIX temp cleanup 故障测试**（`tests/cli/test_init_environment.py:821-915`）：

- `test_posix_cleanup_failure_reports_retained_owner_temp_without_value` 覆盖 unlink/identity-read × os-error/interrupt = 4 fault cases。
- 4/4 测试确认：`retained_paths` 精确等于仍存在的 `.dayu-init-env-*` 文件；文件真实含 secret value；但 `repr(exception)` 和 `repr(result)` 不包含 value。
- `test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement`（L918-963）：中断清理时 owner temp 被 unlink 并替换为未知普通文件；cleanup 正确分类为 `DRIFTED`，不删除 replacement；`retained_paths` 精确指向 replacement；replacement 内容不含原始 secret value。

**裁决**：F02 已关闭。environment owner 以 no-follow identity 精确分类 owned/absent/drifted/unreadable；只 unlink 精确 owned identity；identity drift 对象不删除并报告路径；所有异常/repr/CLI diagnostic 不含 secret value。

## Findings

### 未发现实质性问题

14 个 S2 path 经逐文件走读、逐函数入参→条件→下游→返回值→副作用展开，以及 adversarial failure pass 和 semantic ownership drift pass 后，未发现新的 material defect、design contradiction、或需要 block S2 completion 的 issue。

## Adversarial Challenge 结果

### 1. Generic Exception diagnostic boundary（`_report_diagnostic_best_effort` L649 `except Exception:`）

- **入口**: `commands/init.py:639-650` `_report_diagnostic_best_effort`
- **分析**: 该函数 contract 为"所有普通 diagnostic I/O 错误均被吸收"。`print(message, file=sys.stderr)` 可抛出 `OSError`（broken stderr，是 intended catch）、`ValueError`（closed file）、`UnicodeEncodeError`（非 UTF-8 终端）和 `TypeError`（`sys.stderr` 被替换为非 file-like 对象）。
- **判定**: 不构成 finding。函数名和 docstring 明确承诺 best-effort 语义；所有 6 个 call site 传入的 `message` 都是 owner 构造的保证字符串（literal 或返回 `str` 的函数），因此 `TypeError` 只能来自环境级 stderr 替换而非编程错误。`except Exception`（不包含 `KeyboardInterrupt`/`SystemExit`）是正确实现"不覆盖控制流"的最小安全网。`except OSError` 更窄但不足以覆盖 `UnicodeEncodeError`（这在非 UTF-8 终端真实可能发生）。

### 2. `prepare_workspace_transaction` L536 `except Exception as exc:`

- **入口**: `init_workspace.py:536-549`
- **分析**: 该 generic catch-all 在 `except InitWorkspaceError` 和 `except KeyboardInterrupt` 之后，确保任意未预期的 Exception（包括 `TypeError`、`AttributeError` 等编程错误）不会遗留 dangling transaction container。`from exc` 保留原始异常链。
- **判定**: 不构成 finding。这是 immutable path（SHA 已验证）的既有设计，属于 transaction safety net。编程错误被包裹为 `InitWorkspaceError(stage="staging_validation", message="staging validation failed: TypeError")` 且原始 traceback 可通过 `__cause__` 追溯。外层 `run_init_command` handler 捕获 `InitWorkspaceError` 返回 EXIT_FAILURE。这不是本轮修改引入，且是合理的 transaction safety 实践。

### 3. retained_paths owner 与 redaction

- **environment owner**（`init_environment.py`）：`retained_paths` 唯一 owner。只通过 `_cleanup_owned_profile_temporary` 产生路径；只在 identity `OWNED` 时 `unlink`；`DRIFTED`/`UNREADABLE`/unlink-failure 只报告路径不删除。`EnvironmentPersistenceEntry.value` 使用 `field(repr=False)`，确保 exception/result repr 永远不含值。
- **CLI owner**（`commands/init.py`）：通过 `_report_retained_environment_paths` 接收 `tuple[Path, ...]` 做 best-effort stderr 投影。不尝试删除、猜名或访问 environment owner 的 private temp。
- **Verdict**: 语义 ownership 正确。environment owner 拥有 identity 分类、cleanup 决策和 retained truth 产生；CLI owner 只做 path-only best-effort 投影。不存在跨 owner 语义泄漏。

### 4. POSIX replace before/after、cleanup unlink/identity read/identity drift 和 publication truth

- **replace before/after truth**（`init_environment.py:644-707`）：`_profile_replace_applied` 通过双重检查（source absent + destination identity 匹配）判断 `os.replace` 是否已生效。12 组合参数化测试（`test_posix_atomic_faults_preserve_store_truth_and_remove_owned_secret_temp`）覆盖 write/fsync/replace × os-error/interrupt × before/after。`replace+after+os-error` 正确返回 SUCCESS（replace 已完成）；其他 os-error 正确抛出 `EnvironmentPersistenceError`；interrupt 正确抛出 `EnvironmentPersistenceInterrupted` 并携带 truthful written/unwritten names。
- **cleanup unlink/identity read**（`test_posix_cleanup_failure_reports_retained_owner_temp_without_value`）：4 fault cases 正确报告 retained path 且不含 value。owner temp 文件真实保留且含 value，但 exception/result repr 不含 value。
- **identity drift**（`test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement`）：替换 owner temp 为未知普通文件后，cleanup 正确分类为 `DRIFTED`，不删除 replacement，报告精确路径。
- **publication truth**：`commands/init.py:168-192` 所有 persistence 故障路径均先 abort prepared transaction，再 best-effort 投影 diagnostic。abort 失败通过 `_report_abort_failure` 如实报告 retained transaction path 和 public root states。
- **Verdict**: POSIX replace/cleanup/identity/publication truth chain 正确且完整。没有静默声称 cleanup 成功、没有误删 identity-drift 对象、没有在 exception/diagnostic 中泄漏 secret value。

### 5. Broken stderr 与 abort failure 是否仍可改变 exit 130

- **直接证据链**:
  1. `commands/init.py:168-173`：typed interrupt → abort → diagnostics → `raise`（重新抛出 `EnvironmentPersistenceInterrupted`）
  2. `commands/init.py:214`：外层 `except KeyboardInterrupt: return EXIT_KEYBOARD_INTERRUPT` 捕获所有 `KeyboardInterrupt` 子类
  3. `commands/init.py:174-177`：plain interrupt 同样先 abort 再 raise
  4. `_try_abort_prepared_transaction`（L609-623）只捕获 `InitWorkspaceError`；`OSError`/`KeyboardInterrupt` 从 abort 传播
  5. 若 abort 传播 `KeyboardInterrupt`，外层 `except KeyboardInterrupt` 仍返回 exit 130
  6. 若 abort 传播 `OSError`（仅在 POSIX `_sync_directory` 失败时），外层 `except OSError`（L225-230）返回 EXIT_FAILURE（exit 1）
- **残余风险**: 极端场景（POSIX parent directory sync 在 abort cleanup 后失败抛 `OSError`）可将 exit 130 改为 exit 1。该场景需要：① persistence 已中断且 ② abort cleanup 已完成 identity-safe 删除但 ③ POSIX `fsync` on parent directory 失败。这是 fixed plan §10.1 已记录的 retained residual（"POSIX post-deletion parent directory sync is durability not correctness"），不是 F01 未修复。
- **Verdict**: broken stderr 不改变 exit 130（4 组合测试已证明）。abort failure 产生 `InitWorkspaceError`（被 `_try_abort_prepared_transaction` 捕获并返回），不影响 exit 130。唯一的 exit-130→exit-1 转换路径是 POSIX directory sync fault after successful cleanup，属于 §10.1 retained residual。

### 6. Windows truth 及 S3 boundary

- **Windows truth**: `init_environment.py:402-472` 使用 `subprocess.run(("setx", name, value), shell=False, capture_output=True, text=False, check=False)`。结果分类为 success/failure/partial_failure/interrupted，只报告 written/unwritten names。Windows partial failure 不声称回滚（`_windows_failure_result` 正确返回 `PARTIAL_FAILURE` 或 `FAILURE`）。`test_windows_*` 测试覆盖正常成功、partial failure（return code + OSError）、首项失败、first/middle/last interrupt、进程内注入中断等。所有测试确认 `shell=False`、`text=False` 且 `capture_output=True`。
- **S3 boundary**: 4 个 fixed-hash 文件扫描结果：
  - 无 `test_init_smoke` 导入或引用
  - 无 `r12-init-windows` 引用
  - 无 `importlib.import_module` 调用
  - 无 prewarm 相关代码
  - 无 README 修改
  - 无 stale explicit-interaction test migration
  - S3 内容未被偷带。该结论与 Controller validation scan 结果一致。

### 7. 过度设计、semantic ownership drift、兼容/fallback/test shim

- **过度设计**: 未发现。`_cleanup_owned_profile_temporary` 和 `_classify_profile_path_identity` 的 identity-locked cleanup 是 F02 的直接最低实现。没有引入通用 filesystem/cancellation framework、factory/callback 参数或 test-only branch。
- **semantic ownership drift**: 未发现。environment owner 独占 temp identity、cleanup 和 retained_path truth；CLI owner 独占 abort-first 编排和 best-effort diagnostic 投影；workspace owner 不变（immutable hash 已确认）。
- **兼容/fallback**: 全 14 path 扫描 `hasattr`/`getattr`/`compat`/`fallback`/`shim` 零命中。
- **test shim**: 测试中的 `_BrokenStderr`、`_SetxRecorder`、`_FaultingBinaryHandle`、`_InterruptingEnvironment` 都是 test-local fixtures，在 owner module lookup boundary 做 syscall fault injection。production 代码没有为此新增 callback/factory/profile/默认 callable 参数或 test-only branch。符合 fixed plan §8 fault injection contract。
- **deferred 偷带**: Fins root override（`host_assembly.py:1505-1509`）是 immutable path 既有实现：override 非 None 时无条件支配 effective Fins root（在 raw 语法校验后），不改写 raw config bytes。`entrypoint_runtime.py:517` 普通 runtime 显式传 `None`。未在 immutable path 中发现偷带的 S3/prewarm/额外 override/CLI-side Fins classification。

## Open Questions

1. **`_try_abort_prepared_transaction` 不捕获 `OSError`**：若 abort 期间 POSIX `_sync_directory` 失败，`OSError` 传播出 `_try_abort_prepared_transaction`，被外层 `except OSError` 捕获并返回 EXIT_FAILURE（exit 1）。这在 persistence-interrupt 情境下将 exit 130 改为 exit 1。当前测试不覆盖此路径（abort failure 测试注入的是 `InitWorkspaceError`，不是 `OSError`）。这是 fixed plan §10.1 retained residual 的已知面，但值得记录为 open question：是否需要在 S3 或后续 WU 中为 abort 的 OS-level 失败保持 exit 130？

2. **`EnvironmentPersistenceInterrupted` 在 `except KeyboardInterrupt` 中被捕获**：`commands/init.py:214` 的外层 `except KeyboardInterrupt` 捕获所有 `KeyboardInterrupt` 子类，包括 `EnvironmentPersistenceInterrupted`。这意味着如果一个 typed interrupt 从内部 propagation 路径逃逸到外层（而非在 L168-173 被处理），它的 typed result 信息（`written_names`/`retained_paths`）会丢失，只返回裸 exit 130。当前代码路径不存在此逃逸（所有 persistence 故障都在 L166-197 的精确 handler 中被捕获），但这是继承结构决定的 semantic fragility。不是当前 defect，但值得在后续重构中注意。

## Residual Risk

1. **POSIX cleanup 后 directory sync 失败**：按 fixed plan §10.1，validation cleanup 后 POSIX parent directory sync 失败是 pre-publication abort（已实现）；post-publication cleanup 后 sync 失败是 warning（已实现）。这些是正确的 durability boundary，不是 correctness defect。

2. **Windows directory crash-durability**：按 fixed plan §6.3.2，Windows 不承诺 parent-directory crash-durability。当前实现正确使用 `os.replace` 做 atomic namespace transition。S3 Windows runner 需在实际 Windows 上验证正常 transaction 不被缺少 directory fsync 永久拒绝——这是 S3 gate，不是 S2 block。

3. **`.dayu`/`config` 非 single-syscall atomic**：两个 managed roots 的 replace 序列不是跨 root 原子操作。fixed plan §10.1 已记录。rollback 正确逆序恢复。这是 known residual。

4. **S3 prewarm/smoke/Windows workflow 未执行**：S3 全部内容（prewarm、真实 POSIX/Windows smoke、README、Windows CI workflow）均未在本轮偷带。这是正确的 gate discipline，不是 residual risk——它只是说明 S2 completion 不等于 R12 completion。

## Verdict

**PASS — READY FOR S2 COMPLETION GATE.**

- **Accepted findings**: R12-S2-RR-F01 CLOSED, R12-S2-RR-F02 CLOSED。两项 closure 均由直接代码路径证据和 owner-level 测试支撑。
- **New findings**: 0。
- **14-path identity**: 全部 14 个 SHA-256 与 Controller validation 固定值精确一致。
- **S3 boundary**: 零偷带。
- **Semantic ownership**: 无漂移。environment owner 独占 temp identity/cleanup/retained truth；CLI owner 独占 abort-first 编排和 best-effort diagnostic 投影；workspace/Service owner 未变。
- **Adversarial challenges**: generic Exception boundary 是正确的最低安全网；retained_paths redaction 完整；POSIX replace/cleanup/identity/publication truth chain 正确；broken stderr 不改变 exit 130；Windows truth 完整；无过度设计/兼容/fallback/test shim。

AgentDS 在此停止，不修改代码/测试/plan/control/其它 artifact，不 commit。
