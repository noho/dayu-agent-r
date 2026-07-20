# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows Validation Fix — AgentMiMo Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `07db7af3855b7fc80a24d74a3214bef215752d8d`（HEAD）
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-code-review-mimo.md`
- Included scope: 8 unstaged tracked files + 2 untracked review docs
- Excluded scope: binary/vendor/generated/lockfile
- Parallel review coverage: 无

## Snapshot Verification

- Binary diff SHA-256：`18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5` — **MATCH** ✓
- Tracked path-list SHA-256：`b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001`（expected）vs `2cfef7ff1ad177102674501a9c18c70b0a94c41a461ed0c994e697439f47056a`（computed）— **MISMATCH**

Binary diff 内容完全一致，path-list hash 不匹配。已尝试 `\r\n` 换行、含/不含 untracked files 等变体，均无法复现 expected hash。可能为 controller 验证时计算方法差异（如含 `.claude/` 或其他辅助路径）。不影响内容审查，记录为 non-blocking observation。

## Findings

### 01-未修复-低-path-list SHA-256 snapshot hash 不可复现

- **入口/函数**: snapshot verification protocol
- **文件(行号)**: controller validation artifact `immutable implementation snapshot` section
- **输入场景**: `git diff --name-only -- . | sort | shasum -a 256`
- **实际分支**: 计算得到 `2cfef7ff...`，非预期 `b9f39d74...`
- **预期行为**: 同一 base + 同一工作树产出同一 sorted path-list hash
- **实际行为**: binary diff hash 匹配但 path-list hash 不匹配
- **直接证据**: binary diff SHA-256 `18876f5b...` 完全匹配；path-list SHA-256 在多种换行/包含变体下均无法复现 expected 值
- **影响**: 不影响代码正确性或实现内容；仅表明 snapshot protocol 需要更精确的 hash 计算规范
- **建议改法和验证点**: path-list hash 规范应明确：输入为 `git diff --name-only` 的 sorted 输出、行尾为 `\n`、不含 trailing newline、不含 untracked files
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

**以下六项均为 PASS。**

### 审查项 1：非 POSIX conditional imports / name resolution

**PASS** — 无 finding。

验证路径：

1. `run_keys.py:18-20`：`termios` 和 `tty` 仅在 `if os.name == "posix":` 分支下导入，位于模块顶层，无 function-local lazy import。
2. `run_keys.py:27`：`_POSIX_TERMINAL_CONTROL_AVAILABLE: Final[bool] = os.name == "posix"` 为模块级常量，加载时静态确定。
3. `run_keys.py:256`：`new_running_key_monitor()` 在 `isatty()` 判断前消费该 capability 常量，非 POSIX 固定返回 `NoopRunningKeyMonitor()`。
4. `run_keys.py:151`：`TtyRunningKeyMonitor.start()` 在 `isatty()` 和 `termios` 操作前检查 `_POSIX_TERMINAL_CONTROL_AVAILABLE`。
5. `run_keys.py:285`：`_restore_terminal_attrs()` 在 `termios.tcsetattr` 前检查同一常量。
6. 无 `hasattr`/`getattr`/lazy import/下游 catch/兼容 seam。

三重 guard（factory + start + restore）均为同一 `_POSIX_TERMINAL_CONTROL_AVAILABLE` 常量，不存在绕过路径。直接构造 `TtyRunningKeyMonitor` 在非 POSIX 上 start/close 为 no-op。

### 审查项 2：Windows O_RDWR + fsync durability

**PASS** — 无 finding。

验证路径：

1. `init_workspace.py:997-1011`：`_staged_file_sync_open_flags` 成为 staged-file durability flag 的唯一 owner。
2. Windows 返回 `os.O_RDWR` 以获得可 `fsync` 的 descriptor（Windows `os.fsync` 需要可写 fd）。
3. POSIX 返回 `os.O_RDONLY | os.O_NOFOLLOW`，防止沿符号链接打开。
4. `_validate_platform()` 先验证平台合法性，未知平台沿 typed error fail closed。
5. `init_workspace.py:978-987`：打开后 `fstat` 验证 regular file → `fsync` → `close`，与平台无关。
6. 目录遍历使用 `os.walk(followlinks=False)` 不跟踪 junction/symlink。
7. `publication os.replace`、backup、rollback、identity、containment、symlink/reparse 与 cleanup 路径零改动。

Windows `O_RDWR` 不会打开 symlink/junction 的目标，因为 `os.walk(followlinks=False)` 已在遍历层拦截，且 `_validate_ordinary_tree` 在 staging 前执行 containment 检查。`O_NOFOLLOW` 在 Windows 上不存在，但 reparse point 检测已由 `_path_identity` 在 `test_windows_real_preseeded_junction_fails_closed` 等真实 Windows node 中覆盖。

### 审查项 3：registry delete/query/key-access

**PASS** — 无 finding。

验证路径：

1. `test_init_smoke.py:816-845`：`_delete_registry_value_and_verify_absent` 执行三步验证：
   - `reg delete` 接受 exit {0, 1}（0=实际删除，1=原本不存在）
   - 精确 value query 必须返回 1（absent），返回 0（value 仍存在）→ fail
   - 父 key query 必须返回 0（key 可访问），避免把 access failure 误判为 absent
2. `test_init_smoke.py:848-871`：参数化测试 delete=0 和 delete=1 两条幂等路径，验证三次调用顺序。
3. `test_init_smoke.py:874-907`：严格失败矩阵覆盖：
   - delete=2 → "command failed"
   - delete=0, query=0 → "left env name present"
   - delete=0, query=2 → "verification failed"
   - delete=0, query=1, key=1 → "key access failed"
4. 所有自定义错误只含变量名 `_OPENAI_ENV_NAME`，不含 `test-secret`（stdout/stderr 不泄露）。
5. `test_init_smoke.py:910-939`：真实 Windows `setx` round-trip 的 setup/finally 复用同一 helper。

`reg delete` 对不存在的 value 返回 1 是 Windows 行为，不是 error。三步验证确保只有"精确 value absent + key 可访问"才被视为 cleanup success。

### 审查项 4：R11 cmd ver/help / R12 path filter / test nodes / hash evidence

**PASS** — 无 finding。

验证路径：

**R11 workflow**：
1. `r11-upload-script-windows.yml:62`：`cmd.exe /d /c ver` 作为真实 cmd execution gate，exit 0 证明 capability。
2. `r11-upload-script-windows.yml:66-71`：`cmd.exe /?` 产出 `cmd-help.txt`，help exit 写入 `environment.txt`，只接受 {0, 1} classification，其他值 fail。
3. `r11-upload-script-windows.yml:63-64`：`ver` exit ≠ 0 直接 throw，不吞错误。
4. 无 `continue-on-error`、`|| true` 或 pytest gate 弱化。
5. `r11-upload-script-windows.yml:80`：pytest 执行新增 `test_run_keys.py::test_new_running_key_monitor_uses_noop_for_non_posix_tty`。
6. path filter 包含 `dayu/cli/run_keys.py` 和 `tests/cli/test_run_keys.py`。

**R12 workflow**：
1. `r12-init-windows.yml:68-77`：source hashes 包含 `dayu/cli/run_keys.py` 和 `tests/cli/test_run_keys.py`。
2. `r12-init-windows.yml:90`：init gate 新增 `test_run_keys.py::test_new_running_key_monitor_uses_noop_for_non_posix_tty`。
3. path filter 包含 `dayu/cli/run_keys.py` 和 `tests/cli/test_run_keys.py`。
4. R11 subset（`r11-pytest-junit.xml`）继续在 R12 中执行两个 upload nodes。

**首轮证据确认**：
- R12 JUnit（`init-pytest-junit.xml`）：8 tests，5 failures，全部含 `run_keys.py:14 -> ModuleNotFoundError: termios`。
- R12 R11-subset JUnit（`r11-pytest-junit.xml`）：collection error 同因 `termios`。
- R11 `cmd-help.txt`：180 行完整帮助输出，workflow 因 exit 1 失败（正确行为）。

### 审查项 5：tests owner-level / test-only production branch / Windows skip

**PASS** — 无 finding。

验证路径：

1. `test_registry_cleanup_accepts_deleted_or_already_absent_value`（参数化 2 cases）：验证 helper contract，不含生产代码分支。
2. `test_registry_cleanup_rejects_unproved_absence_without_command_output`（参数化 4 cases）：验证失败矩阵，不含生产代码分支。
3. `test_staged_file_sync_open_flags_match_platform_flush_contract`：验证平台 flags contract。
4. `test_new_running_key_monitor_uses_noop_for_non_posix_tty`：monkeypatch `_POSIX_TERMINAL_CONTROL_AVAILABLE=False`，验证 factory 和直接构造 TTY monitor 的 no-op 行为。此测试在任何平台可执行。
5. `test_tty_running_key_monitor_reads_action_and_restores_terminal`：标记 `skipif(os.name != "posix")`，正确排除。
6. `test_tty_running_key_monitor_restores_terminal_when_thread_start_fails`：同上 `skipif`。
7. `_ScriptedRegistryCommandRunner` 和 `_ReportedTty` 均为测试夹具，不进入生产代码。
8. macOS 验证：`7 passed`（run_keys）、`102 passed, 5 skipped`（init_smoke + init_workspace）。5 skip 均为 `platform.system() != "Windows"` 的真实 Windows nodes。
9. 无 test-only production branch：生产代码中所有 platform 分支都由真实平台语义驱动，不由测试标志驱动。

### 审查项 6：Topic 1-9 / no-deferred / security / Config-SQLite secret

**PASS** — 无 finding。

验证路径：

1. `overdesign-controller-discussion.md` 中 Topic 1-9 全部已有 user adjudication。
2. 本次改动不触碰 Doc input budgets、Web policy、Host LLM-safe arguments、OpaqueEvidenceRef、Wait poller、Fins contracts、Public entrypoints、Engine 240 chars、Tool security wording。
3. 无新增 deferred issues。
4. Config-SQLite secret 存储位置未改变（`init_workspace.py` 的 `_sync_staged_config` 只处理文件 flags，不处理 secret 内容）。
5. `init_workspace.py` 的 `_validate_platform` 沿用现有 typed error fail closed。
6. 无新增 lazy import、`hasattr`/`getattr`、下游 catch、兼容 shim 或 test-only production branch。

### 审查项 7：对抗性 failure / race / overdesign / semantic ownership drift

**PASS** — 无 finding。

验证路径：

1. **Race**：`_POSIX_TERMINAL_CONTROL_AVAILABLE` 是模块加载时确定的 `Final[bool]`，运行时不可变，无竞态。
2. **Overdesign**：四项修复各在唯一 owner boundary 修正平台事实/durability flags/测试 oracle，未引入新抽象框架。
3. **Semantic ownership drift**：
   - platform capability owner：`run_keys.py` 的模块级常量和 factory。
   - durability flags owner：`init_workspace._staged_file_sync_open_flags`。
   - cleanup truth owner：`test_init_smoke._delete_registry_value_and_verify_absent`。
   - workflow gate owner：R11 workflow 的 `cmd.exe /d /c ver` + help exit classification。
   四个语义均在正确 owner 处，无 fallback/特例/重复计算。
4. **Failure paths**：
   - `TtyRunningKeyMonitor.start()` 在 POSIX capability 不可用时静默 no-op（不抛异常）。
   - `_staged_file_sync_open_flags` 对未知平台抛 typed error。
   - registry helper 对未分类 exit code fail closed。
   - R11 workflow 对未分类 help exit fail closed。
5. **Rollback safety**：init transaction 的 backup/swap/rollback 路径零改动。

## Open Questions

无。

## Residual Risk

1. **Windows rerun 必须执行**：本地 macOS 验证通过，但以下事实只能由真实 Windows runner 证明：
   - R12 init 8 个 nodes 通过（或按精确 privilege contract skip）。
   - R11 `ver` exit 0、help exit 记录、recorder/CLI storage gates 通过。
   - JUnit 不再含 `ModuleNotFoundError: termios`、registry cleanup false failure 或 `EBADF`。
2. **path-list hash 规范**：snapshot protocol 应明确 hash 计算的精确输入格式。

## Conclusion

四项 AR-F07 finding 均在唯一 owner boundary 形成正确修复：platform capability 常量控制非 POSIX import/factory/restore、`O_RDWR` 解决 Windows fsync、registry helper 以精确 absent 为 truth、`cmd.exe /d /c ver` 替代 help-as-gate。代码无 lazy import、`hasattr`/`getattr`、下游 catch、兼容 shim 或 test-only production branch。测试覆盖 owner-level contract 和 failure matrix。无 semantic ownership drift、race 或 overdesign。真实 Windows pass 待 R11/R12 rerun 关闭。

Artifact SHA-256：`94e356f92d2ac8e2e90cab2473025afde1b708d2d83a1919aa24026c65b3c366`
