# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows Fix — AgentDS 第二路独立 immutable code review

## Scope

- Mode: current changes (unstaged working tree vs `07db7af3855b7fc80a24d74a3214bef215752d8d`)
- Branch: `phaseflow/host-issues-control`
- Review agent: AgentDS (second independent reviewer; read-only, no code/control/PR mutation)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-ds.md`
- Base HEAD: `07db7af3855b7fc80a24d74a3214bef215752d8d`

### Snapshot verification

- Tracked binary diff SHA-256: `18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5` → **MATCH** ✓
- Tracked path-list SHA-256: `b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001` → **MATCH** ✓

Both immutable snapshots confirmed; no drift detected. Proceeding with review of the verified tree.

### Included scope (8 changed files + 1 new file)

1. `.github/workflows/r11-upload-script-windows.yml` (modified)
2. `.github/workflows/r12-init-windows.yml` (modified)
3. `dayu/cli/init_workspace.py` (modified)
4. `dayu/cli/run_keys.py` (modified)
5. `tests/README.md` (modified)
6. `tests/cli/test_init_smoke.py` (modified)
7. `tests/cli/test_init_workspace.py` (modified)
8. `tests/cli/test_run_keys.py` (modified)

Plus read-only review context:
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md` (Codex implementation artifact)
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-controller-validation.md` (Controller validation artifact)
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` (Topic 1-9 adjudication record)
- First-round artifacts: `workspace/tmp/wu-semantic-ownership-01-r12-run-29690620412/` and `workspace/tmp/wu-semantic-ownership-01-r11-run-29690620419/`

### Excluded scope

- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md` (review input, not under review)
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-controller-validation.md` (review input)
- Untracked files outside the review boundary

### Parallel review coverage

单 reviewer 逐文件走读，未使用 subagent 并行。

---

## Findings

### 综述

对 7 个审查领域逐项走读后，四项 AR-F07 修复（F01–F04）均在正确 semantic owner boundary 处完成，未引入 downstream fallback、lazy import、兼容 shim 或 test-only production branch。以下按审查领域逐项报告 PASS 或 material finding。

---

### 审查领域 1：非 POSIX conditional imports / name resolution

**PASS** — 无 material finding。

逐路径验证：

- **`dayu/cli/run_keys.py:18-20`**：`if os.name == "posix": import termios, tty`。这是 Python 标准平台条件导入模式，发生在模块加载时（非函数内 lazy import）。Windows 上 `os.name == "nt"`，条件不成立，`termios`/`tty` 不会被导入。符合 AGENTS.md "禁止胶水 seam，使用 lazy import 必须有充分理由"——此处不是 lazy import，而是模块级条件导入。
- **`dayu/cli/run_keys.py:27`**：`_POSIX_TERMINAL_CONTROL_AVAILABLE: Final[bool] = os.name == "posix"`。唯一的平台 capability 真源，在模块加载时静态确定，不依赖运行时状态。
- **`new_running_key_monitor`（line 256）**：先检查 `_POSIX_TERMINAL_CONTROL_AVAILABLE`，短路后不再调用 `isatty()`。正确：非 POSIX 固定返回 `NoopRunningKeyMonitor`，不依赖 stdin 的任何属性。
- **`TtyRunningKeyMonitor.start()`（line 151）**：在 `isatty()` 检查前先检查 `_POSIX_TERMINAL_CONTROL_AVAILABLE`。防御正确：即使调用方绕过 factory 直接构造 `TtyRunningKeyMonitor`，非 POSIX 上也安全 no-op。
- **`_restore_terminal_attrs`（line 285）**：在访问 `termios.tcsetattr` 前检查 `_POSIX_TERMINAL_CONTROL_AVAILABLE`。防御正确：即使从异常恢复路径被调用，非 POSIX 上也不会触发 `NameError`。
- **`tests/cli/test_run_keys.py:14-16`**：`if os.name == "posix": import pty, termios`。测试侧也使用相同的平台条件导入模式。PTY 相关测试 `test_tty_running_key_monitor_reads_action_and_restores_terminal` 和 `test_tty_running_key_monitor_restores_terminal_when_thread_start_fails` 有 `@pytest.mark.skipif(os.name != "posix", ...)` 标记。

无 `hasattr`/`getattr`、lazy import、下游兼容 seam 或 function-local import。typing 层面：`_TerminalAttribute`/`_TerminalAttributes` 别名始终可用（不依赖 `termios` 导入），`RunningKeyMonitor` Protocol 和 `TtyRunningKeyMonitor` 类始终可引用。

---

### 审查领域 2：Windows O_RDWR + fsync durability owner

**PASS** — 无 material finding。

逐路径验证：

- **`dayu/cli/init_workspace.py:997-1011`**：`_staged_file_sync_open_flags` 是 staged regular-file durability flag 的唯一 owner。Windows 返回 `os.O_RDWR`，Darwin/Linux 返回 `os.O_RDONLY | os.O_NOFOLLOW`，未知平台通过 `_validate_platform` fail closed。语义正确：Windows Python 3.11 的 `os.fsync` 对 `O_RDONLY` descriptor 返回 `EBADF`（首轮 R12 JUnit 直接证据），`O_RDWR` 提供可 flush descriptor。
- **containment**：`_sync_staged_config` 在调用 `_staged_file_sync_open_flags` 前已通过 `_validate_ordinary_tree` 完成 ordinary tree 全量扫描，拒绝 symlink/reparse/special file。因此 `os.open` 不会沿链接打开外部文件。Windows 上 `os.O_NOFOLLOW` 不可用（`os.name == "nt"` 时不定义），但 tree validation 已提供等效防护。
- **link/reparse/identity**：`_sync_staged_config` 的 `os.open → fstat S_ISREG → fsync → close` 链路不变。`fstat` 在 open 后验证文件仍是 regular file，防止 open 和 fsync 之间的 TOCTOU 替换。`_sync_directory`（POSIX 专用）不受此变更影响，继续使用 `_READ_ONLY_OPEN_FLAGS | os.O_NOFOLLOW | os.O_DIRECTORY`。
- **rollback**：`publish_workspace_transaction`、`_rollback_or_raise`、`_discard_private_container_or_raise` 和 `_cleanup_private_path` 均未修改。publication、backup/swap、identity verification 和 cleanup state machine 保持完整。
- **`_READ_ONLY_OPEN_FLAGS`**：常量 `os.O_RDONLY` 仍被 `_sync_directory` 使用（仅 POSIX），不被 `_sync_staged_config` 使用。没有废弃常量漂移。

---

### 审查领域 3：registry delete/query/key-access 语义正确性

**PASS** — 无 material finding。

`tests/cli/test_init_smoke.py:816-845` 的 `_delete_registry_value_and_verify_absent` 实现三步验证状态机：

**Step 1 — delete**（line 835-837）：`reg delete /v name /f`，接受 returncode 0（实际删除）和 1（value 原本不存在）。不在此集合内的退出码直接 `raise AssertionError`，fail closed。

**Step 2 — exact value query**（line 838-842）：`reg query /v name`。returncode 0 表示 value 仍在 → fail（"registry cleanup left env name present"）。returncode 1 表示 value 不存在 → 继续。其他 returncode → fail closed（"registry cleanup verification failed"）。

**关键正确性证明**：`reg query /v name` 对 missing value 返回 1，对 missing key 也返回 1。仅靠 returncode 1 无法区分"value absent, key ok"和"key absent"。因此第三步必须存在。

**Step 3 — key accessibility probe**（line 843-845）：`reg query key`（不带 `/v`），必须 returncode 0。证明父 key 可访问且存在，从而区分"value absent"和"key absent / access denied"。

**幂等性**：当 value 原本不存在时，delete 返回 1，query `/v` 返回 1，key query 返回 0 → 幂等成功。

**信息安全**：错误消息只包含 `value_name`（变量名），不包含 `stdout`/`stderr`（可能含 secret value）。`test_registry_cleanup_rejects_unproved_absence_without_command_output`（line 883-907）用 `stdout="test-secret-value"` 的 scripted runner 证明错误消息不含 `"test-secret"`。

**Owner test matrix**（line 848-907）：

| 测试 | 覆盖场景 | PASS |
|------|----------|------|
| `test_registry_cleanup_accepts_deleted_or_already_absent_value[0]` | delete=0, query/v=1, query-key=0 | ✓ |
| `test_registry_cleanup_accepts_deleted_or_already_absent_value[1]` | delete=1（原本 absent）, query/v=1, query-key=0 | ✓ |
| `test_registry_cleanup_rejects...[2,]` | 未分类 delete code | ✓ |
| `test_registry_cleanup_rejects...[0,0]` | value 仍在 | ✓ |
| `test_registry_cleanup_rejects...[0,2]` | 未分类 query/v code | ✓ |
| `test_registry_cleanup_rejects...[0,1,1]` | 父 key 不可访问 | ✓ |

**locale/access/exit code 误判分析**：`reg.exe` 退出码语义稳定（0=成功，1=未找到/失败），不依赖 locale。管理员权限问题（如 key 存在但无权读取）会导致 query 返回非 0/1 退出码或 key_access 非零，均被 fail-closed 捕获。

---

### 审查领域 4：R11 cmd ver/help PowerShell LASTEXITCODE、artifact 与 fail-closed 条件

**PASS** — 无 material finding。

**R11 workflow 变更**（`.github/workflows/r11-upload-script-windows.yml:53-71`）：

1. **cmd execution gate**（line 62-65）：`cmd.exe /d /c ver 2>&1 | Set-Content ...`，随后检查 `$LASTEXITCODE -ne 0`。`ver` 是 Windows 内置命令，始终 exit 0。`/d` 禁用 AutoRun（防止注册表注入干扰）。PowerShell 7+（`shell: pwsh`）中 `$LASTEXITCODE` 正确捕获管道中 native command 的退出码。首轮 evidence 中 `cmd-help.txt` 成功捕获，间接证明 `$LASTEXITCODE` 在管道中正确工作。

2. **help exit classification**（line 66-71）：`cmd.exe /? 2>&1 | Set-Content ...` → 捕获 `$LASTEXITCODE` → 记录到 `environment.txt` → 只接受 0/1，其他退出码 fail。首轮 evidence 证明 `cmd.exe /?` 在 Windows Server 2022 上返回 1。此变更不要求 help exit 0，不吞掉未分类错误，不使用 `continue-on-error`/`|| true`。

3. **pytest nodes**（line 80）：新增 `test_run_keys.py::test_new_running_key_monitor_uses_noop_for_non_posix_tty`。正确：此 node 在 Windows 上必须通过，证明 CLI import 不因 `termios` 失败。

**R12 workflow 变更**（`.github/workflows/r12-init-windows.yml`）：

1. **path filter**（line 14, 25）：新增 `dayu/cli/run_keys.py` 和 `tests/cli/test_run_keys.py`。正确：修改 run_keys 时应触发 init Windows gate。

2. **hash evidence**（line 71-72）：`Get-FileHash` 新增 `dayu/cli/run_keys.py` 和 `tests/cli/test_run_keys.py`。正确：提供跨平台文件内容 proof。

3. **test nodes**（line 90）：新增 `test_new_running_key_monitor_uses_noop_for_non_posix_tty`。与 R11 一致。

**artifact 完整性**：R11 evidence 包包含 `cmd-version.txt`（ver 输出）、`cmd-help.txt`（help 输出）、`environment.txt`（含 `cmd_help_exit_code`）、JUnit、生成脚本、recorder oracle、CLI storage oracle、stdout/stderr。R12 evidence 包包含 JUnit、`versions.txt`、`environment-names.txt`（仅变量名，无值）、`source-hashes.json`（跨平台 hash proof）。均不保存 environment values 或 registry values。

**fail-closed 条件汇总**：

| 条件 | 行为 |
|------|------|
| `cmd.exe /d /c ver` exit ≠ 0 | workflow fail |
| `cmd.exe /?` exit ∉ {0,1} | workflow fail |
| pytest exit ≠ 0 | workflow fail |
| missing deterministic evidence files | workflow fail |
| recorder oracle row count ≠ 1 | workflow fail |
| CLI evidence contract mismatch | workflow fail |
| generated script hash mismatch | workflow fail |
| source artifact count mismatch | workflow fail |

全部 fail-closed，无弱化为 warning 或 skip。

---

### 审查领域 5：tests — owner-level、test-only production branch、Windows skip

**PASS** — 无 material finding。

**Owner-level 验证**：

- `test_new_running_key_monitor_uses_noop_for_non_posix_tty`：验证 factory 和直接构造 `TtyRunningKeyMonitor` 在非 POSIX 都返回/表现为 no-op。这是平台 capability boundary 的 owner contract——不是测试 CLI entrypoint，而是测试 platform capability owner 的决策逻辑。
- `test_registry_cleanup_accepts_deleted_or_already_absent_value`：验证 exact 三步调用序列（delete → query/v → query key），非验证 subprocess 行为。这是 cleanup helper 的 owner contract。
- `test_registry_cleanup_rejects_unproved_absence_without_command_output`：验证四种失败模式都 fail closed 且不泄露 secret。这是 cleanup helper 的 security contract。
- `test_staged_file_sync_open_flags_match_platform_flush_contract`：验证 exact flags（Windows=O_RDWR，Darwin/Linux=O_RDONLY|O_NOFOLLOW）和未知平台 fail closed。这是 durability flag owner 的 contract。

**test-only production branch 检查**：

- `_POSIX_TERMINAL_CONTROL_AVAILABLE` 是模块级 `Final` 常量，生产代码和测试代码使用相同条件判断。测试用 `monkeypatch.setattr` 覆盖此常量来模拟非 POSIX——这是 pytest 标准模式，不是 test-only branch。生产代码中 `_POSIX_TERMINAL_CONTROL_AVAILABLE` 仅由 `os.name` 决定，不存在"if testing: ..."分支。
- `_ScriptedRegistryCommandRunner` 是测试专用 helper class（位于测试文件内），不进入生产路径。生产路径使用默认 `_run_registry_command`。
- `_ReportedTty` 是测试专用 `io.StringIO` 子类（位于测试文件内），仅用于模拟 isatty() 行为。

**Windows skip 计数**：

- `tests/cli/test_run_keys.py`：2 个 PTY 测试有 `@pytest.mark.skipif(os.name != "posix", ...)`。在 Windows 上明确 skip——这是正确行为，因为 PTY contract 仅在 POSIX 存在。
- `tests/cli/test_init_smoke.py`：5 个 POSIX 专用测试有 `@pytest.mark.skipif(os.name != "posix", ...)`，5 个 Windows 专用测试有 `@pytest.mark.skipif(platform.system() != "Windows", ...)`。
- `tests/cli/test_init_workspace.py`：`test_staged_file_sync_open_flags_match_platform_flush_contract` 在所有平台运行，但 Darwin/Linux flag 断言仅在 `os.name == "posix"` 时执行（因为 `os.O_NOFOLLOW` 在 Windows 上不可用）。这正确避免了 Windows 上的 `AttributeError`。跨平台 hash evidence 由 R12 workflow 的 `Get-FileHash` 提供。

**skip 未误算为 pass**：所有 `skipif` 使用明确条件（`os.name != "posix"` 或 `platform.system() != "Windows"`），不会因非预期原因误 skip。Controller 验证报告中 7 个 skip 全部为 macOS 不可执行的 Windows-only nodes，未被计作 Windows pass。

---

### 审查领域 6：Topic 1-9 / no-deferred / security / user Config-SQLite secret 裁决

**PASS** — 无裁决被改变。

逐项核对 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 的 9 个 final disposition：

| Topic | Final disposition | 本次变更是否触及 |
|-------|-------------------|-------------------|
| 1 Doc input budgets | accepted code fix; remove 32MiB/10000-entry limits | 否 |
| 2 Web policy | accepted; documented in `docs/tool/design.md` | 否 |
| 3 Host LLM-safe arguments | accepted; remove downstream blacklist repair | 否 |
| 4 OpaqueEvidenceRef | accepted; no guessed business sources | 否 |
| 5 Wait poller | accepted; explicit config owner, retry/backoff not LOST | 否 |
| 6 Fins contracts | accepted; 7 owner boundaries | 否 |
| 7 Public entrypoints/init | accepted; OLD-aligned init | 否 |
| 8 Engine 240 chars | accepted as-is; no code fix | 否 |
| 9 Tool security wording | design clarification; keep current safety | 否 |

**deferred issues 检查**：

- Issue #142（workspace migration）：未触及。
- Issue #151（write/assets）：未触及。
- Issue #175（Fins Docling process isolation）：未触及。
- Issue #177（TruncationManager connection）：未触及。
- Issue #178（storage-state lifecycle）：未触及。

**security / Config-SQLite secret**：`init_workspace.py` 不接触 secret（模块 docstring 明确："它不接触 secret"）。`run_keys.py` 仅处理 TTY 按键，不涉及配置持久化。`test_init_smoke.py` 的 `_delete_registry_value_and_verify_absent` 仅使用变量名，不与 SQLite 或 secret 持久化路径交互。

---

### 审查领域 7：对抗性 failure / race / overdesign / semantic ownership drift

**PASS** — 无 material finding。以下逐项说明。

#### 7a. Semantic ownership

逐一核对每个变更的语义 owner：

| 语义 | Owner | 变更位置 | 验证 |
|------|-------|----------|------|
| 平台 terminal control 可用性 | `dayu.cli.run_keys._POSIX_TERMINAL_CONTROL_AVAILABLE` | 模块级常量 | ✓ 唯一真源 |
| 运行态按键 monitor 创建策略 | `new_running_key_monitor` | factory 函数 | ✓ 唯一入口 |
| TTY monitor 启动安全守卫 | `TtyRunningKeyMonitor.start()` | capability boundary | ✓ 防御层 |
| staged file flush 平台 flags | `_staged_file_sync_open_flags` | 模块级私有 helper | ✓ 唯一 owner |
| registry cleanup truth | `_delete_registry_value_and_verify_absent` | 测试 helper | ✓ 三步验证 |
| cmd execution capability gate | R11 workflow `cmd.exe /d /c ver` | workflow step | ✓ 唯一 probe |
| help exit classification | R11 workflow `$cmdHelpExitCode` | workflow step | ✓ 显式分类 |

无 downstream fallback、无 `hasattr`/`getattr` 兼容检查、无 loose parsing、无重复计算语义。

**无语义漂移**：`_sync_staged_config` 不再内联计算 open flags，而是委托给 `_staged_file_sync_open_flags`——这是语义集中（从消费者迁移到 owner），不是漂移。原 `_READ_ONLY_OPEN_FLAGS` 常量仍被 `_sync_directory`（POSIX directory sync owner）使用，职责清晰。

#### 7b. Overdesign

- `_staged_file_sync_open_flags`：5 行有效逻辑（`_validate_platform` + if/else），无多余抽象。
- `_delete_registry_value_and_verify_absent`：三步验证是最小充分设计——delete→query/v→query key 没有一步是多余的。
- `_POSIX_TERMINAL_CONTROL_AVAILABLE`：单个 `Final[bool]`，无 capability enum、platform registry 或 plugin 框架。
- `_ScriptedRegistryCommandRunner`：测试专用 scripted stub（42 行），不提升为生产抽象。

**无未来预留代码**：没有任何"未来可能支持 X"的未使用参数、抽象类或配置项。

#### 7c. Race conditions

- `_sync_staged_config`：在 `_validate_ordinary_tree`（read lock）和 `os.open` 之间有窗口，但 `os.fstat` 在 open 后验证 regular file 类型，且文件位于 transaction-private staging 目录（仅当前进程可访问），不存在并发写入者。
- Registry cleanup：三个 `reg.exe` 子进程调用是串行的，但并发 `reg.exe` 进程（如系统策略更新）理论上可能在 query 和 delete 之间修改 key。这是 Windows registry 的固有属性，非本变更引入。三步验证减少了误判窗口（delete→query 证明 value 已 absent，key query 证明 key 仍可访问），比原实现（仅读 delete returncode）更安全。
- `_POSIX_TERMINAL_CONTROL_AVAILABLE`：模块加载时设定，运行时不改变，无 TOCTOU。

#### 7d. Failure paths

| 场景 | 行为 | 评估 |
|------|------|------|
| Windows 上 import `termios` | 模块加载条件跳过，不触发 `ModuleNotFoundError` | ✓ fail-safe |
| 非 POSIX TTY 上 factory 返回 TTY monitor | `start()` 检查 capability 后 no-op | ✓ defense-in-depth |
| `_restore_terminal_attrs` 在非 POSIX 被调用 | 检查 capability 后返回，不访问 `termios` | ✓ defense-in-depth |
| `O_RDWR` open 失败（权限） | `OSError` 传播到 `prepare_workspace_transaction` 的 exception handler，触发 staging cleanup | ✓ fail-closed |
| `reg delete` 返回未分类退出码 | `AssertionError`("registry cleanup command failed") | ✓ fail-closed |
| `reg query /v` 返回 0（value 仍在） | `AssertionError`("registry cleanup left env name present") | ✓ fail-closed |
| `reg query key` 返回非 0（key 不可访问） | `AssertionError`("registry cleanup key access failed") | ✓ fail-closed |
| `cmd.exe /d /c ver` 非零退出 | workflow throw → job failure | ✓ fail-closed |
| `cmd.exe /?` 返回未知退出码 | workflow throw → job failure | ✓ fail-closed |
| 未知平台调用 `_staged_file_sync_open_flags` | `InitWorkspaceError(stage="platform")` | ✓ fail-closed |
| 测试 monkeypatch 后 `TtyRunningKeyMonitor.close()` | `_closed` 状态正确，线程/fd 为 None → 安全 no-op | ✓ safe |

#### 7e. 项目指令合规

对照 `AGENTS.md`（即 `CLAUDE.md`）关键约束：

- **禁止兼容性代码**：未引入 re-export、兼容性常量、wrapper/facade。✓
- **禁止 `hasattr`/`getattr` 逃避类型边界**：全局搜索确认零新增。✓
- **禁止 lazy import 无充分理由**：条件导入是模块加载时的平台判断，不是函数内 lazy import。✓
- **禁止魔法数字/字符串**：`os.O_RDWR`、`os.O_RDONLY`、`os.O_NOFOLLOW` 是标准库常量。returncode `{0,1}` 来自 `reg.exe` 文档的稳定语义。✓
- **优先模块级私有辅助函数**：`_staged_file_sync_open_flags`、`_delete_registry_value_and_verify_absent` 均为模块级。✓
- **禁止 God object/function**：每个 helper 职责单一。✓
- **docstring 完整**：所有新增函数/类有中文 docstring，含参数、返回值、异常说明。✓

---

## Open Questions

1. **`$LASTEXITCODE` 管道行为的确切 PowerShell 版本依赖**：在 PowerShell 7+ 中 `$LASTEXITCODE` 正确捕获管道中 native command 的退出码。`windows-latest`（Windows Server 2022）默认使用 PowerShell 7.4+，行为已验证（首轮 evidence 中 `cmd-help.txt` 成功捕获）。如果 GitHub Actions 将来降级 runner 的 PowerShell 版本，`$LASTEXITCODE` 在管道中的行为可能变化。**评估**：低风险，因为 `shell: pwsh` 明确指定 PowerShell 7+，且 `ver` 命令本身不会失败。如果 `$LASTEXITCODE` 未正确设置，最坏情况是 workflow 误报失败（fail-closed），不会静默通过。

2. **Windows `os.O_NOFOLLOW` 可用性**：在 Windows Python 3.11 中 `os.O_NOFOLLOW` 未定义（仅在 POSIX 模块中可用）。当前代码通过 `_validate_ordinary_tree` 在 `os.open` 前已完成 symlink/reparse 拒绝，因此不依赖 `O_NOFOLLOW` 进行 open-time 防护。但如果未来 `_sync_staged_config` 的调用顺序被重构（先 open 后 validate），Windows 上将缺少 open-time no-follow 防护。**评估**：当前调用顺序安全。建议在 `_sync_staged_config` 的 docstring 或行内注释中记录"tree validation 必须在 os.open 前完成"的顺序约束。

---

## Residual Risk

1. **`requiring external-state change`**：真实 Windows R12/R11 rerun 尚未执行。F01–F04 的本地修复（platform capability boundary、cmd execution gate、registry cleanup truth、durability flags）已通过 macOS owner tests 验证，但真实 Windows flush（F04）、registry round-trip（F03）、CLI import/collection（F01）和 cmd ver execution（F02）必须由 Windows runner 上的实际通过来关闭。此 residual 与 Codex artifact 和 Controller validation 一致，是 AR-F07 release gate，不是 waiver。

2. **cross-platform flag test 覆盖**：`test_staged_file_sync_open_flags_match_platform_flush_contract` 在 Windows 上不验证 Darwin/Linux flags（因为 `os.O_NOFOLLOW` 在 Windows 上不可用）。`_staged_file_sync_open_flags` 的 POSIX 分支行为由 macOS/Linux CI 上的同一测试覆盖，但 Windows runner 上该分支未被直接断言。R12 workflow 的 `Get-FileHash` 提供跨平台 source identity proof（`init_workspace.py` 的 SHA-256），可以间接证明文件未漂移。**评估**：低风险，行为由平台字符串直接映射，确定性极高。

3. **registry key 存在性假设**：`_delete_registry_value_and_verify_absent` 的第三步 key-access probe 假设 `HKCU\Environment` key 在正常 Windows 用户环境中始终存在。如果该 key 被第三方软件删除或权限被修改（非正常状态），cleanup 会 fail-closed 并报告 "registry cleanup key access failed"。这在 Windows smoke test 上下文中是正确行为——异常环境状态应导致测试失败而非静默通过。但如果未来此 helper 被复用于其他 registry key（可能默认不存在的 key），需要增加 key 创建逻辑。**评估**：当前使用场景正确。helper 的 contract 文档明确说明它验证父 key 可访问性。

---

## Artifact SHA-256

```
a107146b08411b7ec6b3cf611c078cf786569692c4026845038d8af4fbc4f316
```

## Classification summary

| 审查领域 | 结论 | 类型 |
|----------|------|------|
| 1. 非 POSIX conditional imports/name resolution | PASS | — |
| 2. Windows O_RDWR + fsync durability | PASS | — |
| 3. Registry delete/query/key-access | PASS | — |
| 4. R11 cmd ver/help LASTEXITCODE | PASS | — |
| 5. Tests owner-level / test-only branch / skip miscount | PASS | — |
| 6. Topic 1-9 / deferred / security / Config-SQLite | PASS | — |
| 7. Adversarial failure/race/overdesign/semantic ownership drift | PASS | — |

**Material findings: 0**（必须修复：0，needs Windows evidence：0，non-blocking observation：0）

**Open Questions**: 2（均非阻塞，已在 Open Questions 中记录）

**Residual Risk**: 3（均已在 Codex artifact 和 Controller validation 中确认，待 Windows rerun 关闭）

`LOCAL_FIX_REVIEWED / WINDOWS_RERUN_REQUIRED` — AgentDS 第二路审查确认四项修复在正确 owner boundary 处实现，本地 macOS owner tests 和类型/边界扫描通过，零 material finding；与 Codex artifact 和 Controller validation 的结论一致。
