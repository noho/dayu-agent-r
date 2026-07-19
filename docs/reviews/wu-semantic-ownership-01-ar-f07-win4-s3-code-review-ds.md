# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S3 Code Review (AgentDS)

## Result

`PASS / MATERIAL_FINDING_0 / NO_BLOCKER`

## Review identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4`，同一 remediation continuation，不是新 WU。
- Gate：`WIN4-S3 dual complete code review`，本 artifact 为 AgentDS route。
- Baseline HEAD：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`（S2 accepted commit）。
- Branch：`phaseflow/host-issues-control`。
- Controller validation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-controller-validation.md`，SHA-256 `d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6`，verdict `PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / REAL_WINDOWS_PENDING`。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md`，SHA-256 `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2`。

## Immutable target confirmation

| Material | Expected SHA-256 | Actual SHA-256 | Match |
| --- | --- | --- | --- |
| `tests/cli/test_init_smoke.py` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` | ✓ |
| `tests/README.md` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` | ✓ |
| Binary payload diff | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` | ✓ |
| Implementation artifact | `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2` | `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2` | ✓ |
| Controller validation | `d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6` | `d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6` | ✓ |

Diff stat：`tests/cli/test_init_smoke.py +963/-44`，`tests/README.md +7/-3`，共 `+970/-47`。

## Scope verification

Changed paths 严格限制为 `tests/cli/test_init_smoke.py` 与 `tests/README.md`。Production、S1/S2 owner、workflow、root README、plan/control/design 与 deferred Issue paths 零 diff。Staged tree empty，`git diff --check` 通过。

## Independent validation

所有命令均在 `source .venv/bin/activate` 后运行；环境 Python `3.11.15`、pytest `9.0.3`。

| Validation | Result |
| --- | --- |
| `pytest tests/cli/test_init_smoke.py -q` | `28 passed, 5 skipped, 3 warnings`；skip 全部为本地非 Windows 平台 |
| `pytest tests/cli/test_init_smoke.py tests/cli/test_init_environment.py tests/cli/test_upload_filings_from_command.py -q` | `105 passed, 7 skipped, 3 warnings` |
| `python -m pyright tests/cli/test_init_smoke.py` | `0 errors, 0 warnings` |
| `git diff --check` | PASS |
| Staged tree | empty |

三类 warning 均来自既有 edgartools deprecated imports，本 slice 未新增 warning owner。

## 1. Popen[bytes] + three anonymous handles contract

### 1.1 Production path：`_run_init()`

```python
with (
    tempfile.TemporaryFile(mode="w+b") as stdin_handle,
    tempfile.TemporaryFile(mode="w+b") as stdout_handle,
    tempfile.TemporaryFile(mode="w+b") as stderr_handle,
):
```

- `TemporaryFile(mode="w+b")` 在 POSIX 返回 `_io.BufferedRandom`，底层为 `os.open()` + `os.unlink()` 的匿名 fd；在 Windows 使用 `O_TEMPORARY`（可用时）或 named-temp-with-delete-on-close。
- `w+b` mode 保证 read/write/seek 均可，支持 stdin write→flush→rewind→child reads 与 success-path stdout/stderr rewind→read→decode。
- 三个 handles 由同一个 `with` context manager 管理，任意路径（success/timeout/exception）统一在 context unwind 时 close；`TemporaryFile.close()` 幂等，不会 double-close panic。

独立验证：真实 Popen[bytes] 与 TemporaryFile stdin handle 的 POSIX 闭环确认 child 可正确读取 `b'hello from tempfile\n'`。

### 1.2 Popen contract

```python
process: subprocess.Popen[bytes] = subprocess.Popen(
    (sys.executable, "-u", "-m", "dayu.cli", "init", "--base", str(workspace_root), *flags),
    cwd=_REPOSITORY_ROOT,
    env=environment,
    stdin=stdin_handle, stdout=stdout_handle, stderr=stderr_handle,
    shell=False, close_fds=True, text=False,
)
```

- `text=False` → Popen 以 bytes mode 运行，stdin 接受 `BinaryIO`，stdout/stderr 返回 bytes。这避免了 implicit encode/decode 与 ambient code page 问题。
- `shell=False` → 无 shell injection 风险。
- `close_fds=True` → POSIX 下除 stdin/stdout/stderr 外所有 fd 被关闭；Windows 下通过 `STARTUPINFO.lpAttributeList` 精确控制 handle 继承。
- stdin/stdout/stderr 均为 anonymous `TemporaryFile` handles — 无 named path，无 `/proc` 或 `lsof` 泄漏路径。
- `cwd=_REPOSITORY_ROOT` 保留既有 behavior，与 S1/S2 一致。

### 1.3 stdin frame clearing

```python
input_bytes = input_text.encode("utf-8", errors="strict")
stdin_handle.write(input_bytes)
stdin_handle.flush()
stdin_handle.seek(0)

# timeout failure 前主动清空 helper frame 中唯一的 input 文本与 bytes 所有者。
input_text = ""
input_bytes = b""
```

- `write → flush → seek(0)` 保证 child process 继承 fd 时 position 从 0 开始，读取完整 input。
- `input_text = ""` 与 `input_bytes = b""` 在 Popen 启动前执行：若后续 `pytest.fail` 或任何异常展开 frame locals，这两个变量为空字符串/空 bytes，不会回显原始 input 值。
- `strict` encoding 在 Popen 之前执行：非法 UTF-8 input 直接抛出 `UnicodeEncodeError`，不启动子进程。

**Adversarial check**：frame clearing 的有效性依赖 CPython 的引用计数机制 — 重新绑定局部变量名会解除对原始对象的引用，但不会立即释放对象内存。但 `pytest.fail(pytrace=False)` 不展开 frame locals，因此 frame clearing 是 defense-in-depth。实际安全保障来自 `pytrace=False` + safe renderer。

**结论：Popen 与 handle contract 正确。**

## 2. Timeout four-state machine

### 2.1 State machine tracing

```python
try:
    returncode = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
except subprocess.TimeoutExpired:
    returncode_at_timeout = process.poll()
    cleanup: Literal["completed", "timeout"] = "completed"
    cleanup_returncode = returncode_at_timeout
    process_state_after_cleanup_timeout: Literal["running", "exited"] | None = None
    if returncode_at_timeout is None:
        process.kill()
        try:
            cleanup_returncode = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            cleanup = "timeout"
            cleanup_returncode = process.poll()
            process_state_after_cleanup_timeout = "running" if cleanup_returncode is None else "exited"
    safe_message = _render_init_timeout(...)
    pytest.fail(safe_message, pytrace=False)
```

四项 parametrized state 独立验证通过：

| State | deadline poll | kill | cleanup wait | cleanup poll | Projection |
| --- | --- | --- | --- | --- | --- |
| 1: 已退出 | `1` (exit) | 不触发 | 不触发 | 不触发 | `completed, rc=1` |
| 2: 运行→清理完成 | `None` (running) | 1次 | 返回 `-9` | 不触发 | `completed, rc=-9` |
| 3: 清理超时仍运行 | `None` (running) | 1次 | TimeoutExpired | `None` (running) | `timeout, running` |
| 4: 清理超时已退出 | `None` (running) | 1次 | TimeoutExpired | `23` (exit) | `timeout, exited` |

### 2.2 Cleanup timeout 的恰好一次 poll

```python
except subprocess.TimeoutExpired:
    cleanup = "timeout"
    cleanup_returncode = process.poll()        # 恰好一次
    process_state_after_cleanup_timeout = ...   # 精确一次投影
```

- cleanup timeout 后恰好一次 `poll()`，没有第二次 `wait()` 或 `kill()`。
- 满足 accepted plan 的四项补强之一：`S3 cleanup-timeout 后只做一次非阻塞 process-state 投影`。

### 2.3 Failure path 的 zero-read

```python
# success-path only — 在 try/except 之后
stdout_handle.seek(0)
stderr_handle.seek(0)
stdout_bytes = stdout_handle.read()
stderr_bytes = stderr_handle.read()
```

- `pytest.fail()` 抛出 `Failed(BaseException)` 使流程跳出 `except` 块之前就终止了执行，不会到达 `read()` 行。
- owner test 确认 `stdout_handle.read_count == 0` 与 `stderr_handle.read_count == 0`。

### 2.4 returncode 真源

- `cleanup_returncode` 初始值取自 `returncode_at_timeout`（deadline 时已退出）。
- 需要 kill 时，cleanup wait 成功则覆盖为 cleanup wait 的 returncode；cleanup wait 超时则被 `process.poll()` 覆盖。
- 所有状态的 returncode 都来自 `poll()` 或 `wait()` 的直接返回值 — 没有从 `TimeoutExpired` 对象或间接计算中派生，满足 `returncode 真源` 约束。

**结论：timeout 状态机正确、完备，四个状态覆盖了 plan 的全部组合。Cleanup timeout 后恰好一次 poll，无额外 wait/kill。**

## 3. Safe renderer 与 pytest.fail(pytrace=False)

### 3.1 Renderer contract

```python
def _render_init_timeout(
    *,
    returncode_at_timeout: int | None,
    cleanup: Literal["completed", "timeout"],
    cleanup_returncode: int | None,
    process_state_after_cleanup_timeout: Literal["running", "exited"] | None,
) -> str:
```

输出格式：
```
category=dayu_cli_init_timeout timeout_seconds=180 returncode_at_timeout=<rc|not_exited> cleanup=<completed|timeout> cleanup_returncode=<rc|not_available> [process_state_after_cleanup_timeout=<running|exited>]
```

- `timeout_seconds` 使用 `:g` 格式避免浮点噪声：`180.0` → `180`。
- 不含 argv、cwd、path、input、output、raw exception type/class name。
- `process_state_after_cleanup_timeout` 仅在 cleanup timeout 后出现，满足 `只投影 cleanup timeout 后的额外字段` 约束。

### 3.2 Invariant guard

```python
if cleanup == "completed" and process_state_after_cleanup_timeout is not None:
    raise AssertionError("completed cleanup cannot have a post-timeout process state")
if cleanup == "timeout" and process_state_after_cleanup_timeout is None:
    raise AssertionError("timed-out cleanup requires a post-timeout process state")
```

- 内部 invariant 捕获 caller 的不一致参数组合。AssertionError message 只包含状态标签，不含 sensitive material。
- 若 renderer invariant 失败，会以普通 AssertionError 传播（非 `pytrace=False`），但这是编程错误（不应发生），且 message 不包含敏感数据。

### 3.3 pytrace=False 分析

- `pytest.fail(msg, pytrace=False)` 抛出 `Failed`（`pytest.fail.Exception`），它是 `BaseException` 的子类（非 `Exception`）。
- `pytrace=False` 告诉 pytest 在 report 中不展开 traceback、不展示 frame locals、不展示 `__context__` chain。JUnit XML 中只包含 msg string。
- owner test 显式验证 `str(raised.value)` 精确等于 expected safe message，且 sentinel/canary/sensitive_input/workspace_root/repository_root/cli-argv/stdin/stdout/stderr/TimeoutExpired 均不在 message 或 `repr(raised.value)` 中。

**Adversarial check — `TimeoutExpired.__context__`**：当 `pytest.fail()` 在 `except subprocess.TimeoutExpired:` 块中被调用时，Python 隐式将 `TimeoutExpired` 设为 `Failed.__context__`。但在 `pytrace=False` 下，pytest 的 `Failed` 类 `_pytrace` 属性控制整个 traceback chain 的渲染 — `__context__` 与 `__cause__` 均不显示。独立验证确认：`TimeoutExpired.__str__` 包含 command args（含 sentinel），但 `pytest.fail(safe_message, pytrace=False)` 的 JUnit/stderr/terminal 输出仅包含 safe_message。

**结论：safe renderer 正确，pytrace=False 有效防止 raw exception material 泄漏。**

## 4. GitHub Actions canary

### 4.1 Domain bytes 与 known vector

```python
_WINDOWS_CANARY_DOMAIN: Final[bytes] = b"dayu-ar-f07-win4-r12-canary-v1\x00"
```

独立验证：
- 长度：`31` bytes ✓
- ASCII 前缀：`dayu-ar-f07-win4-r12-canary-v1`（30 bytes）✓
- 末字节：`\x00`（single NUL）✓
- NUL 计数：`1`（exactly one）✓
- 无其他 NUL 字节 ✓

Known vector 独立重算：
- SHA-256(`dayu-ar-f07-win4-r12-canary-v1\x00` + `1`) = `b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓
- Full canary：`sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓

这满足 accepted plan re-review 的两项精确修复：(a) domain separator 锁成末字节 NUL `0x00` 的 Python bytes literal 并加 known vector；(b) 消除 `\x00` 与普通字符之间的双 owner 歧义。

### 4.2 Canonicalization 与 determinism

```python
def _github_actions_canary(raw_run_id: str) -> str:
    if not raw_run_id.isascii() or not raw_run_id.isdecimal():
        raise AssertionError("GITHUB_RUN_ID must be a positive ASCII decimal integer")
    run_id = int(raw_run_id)
    if run_id <= 0:
        raise AssertionError("GITHUB_RUN_ID must be a positive ASCII decimal integer")
    canonical_run_id = str(run_id)
    digest = hashlib.sha256(_WINDOWS_CANARY_DOMAIN + canonical_run_id.encode("ascii", errors="strict")).hexdigest()
    return f"{_WINDOWS_CANARY_PREFIX}{digest}"
```

- `str(int(raw_run_id))` canonicalize：`"0001"` → `int("0001")` → `1` → `str(1)` → `"1"`。独立验证 `_github_actions_canary("0001") == _github_actions_canary("1")`。
- `isascii() + isdecimal()` 守卫：阻止全角数字、负数、空字符串、非数字字符。
- `run_id <= 0` 守卫：阻止零值。
- Canonical run id 以 `errors="strict"` ASCII encode → 保证 domain + canonical run id 的 SHA-256 输入为确定性的 ASCII bytes。
- `_WINDOWS_CANARY_PREFIX` = `"sk-dayu-test-"`，digest 为 64-char lowercase hex → total 76-char canary。

### 4.3 Fail-closed matrix

| Condition | Behavior |
| --- | --- |
| `GITHUB_ACTIONS!=true`（本地） | `secrets.token_urlsafe(32)`，随机 |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID` 缺失 | `AssertionError`，不 fallback 随机 |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID=""` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="abc"` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="0"` | `AssertionError`（`run_id <= 0`） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="-1"` | `AssertionError`（`isdecimal()` → False，`-` 不是 decimal） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="１２"`（全角） | `AssertionError`（`isascii()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="1"` | 确定性 canary，`ForbiddenTokenFactory.calls == 0` |

全部路径均 fail-closed，不存在静默 fallback 到随机值或错误 canary 的情况。

### 4.4 本地随机路径

- 非 GitHub Actions 环境调用 `secrets.token_urlsafe(32)`：每次返回独立的 256-bit 加密随机 token（~43 chars URL-safe Base64）。
- owner test 使用 `_ScriptedTokenFactory` 验证每次调用请求 `32` bytes、两次调用返回互异值。
- 本地随机值不进入 GitHub Actions workflow log/artifact，Controller 不能以扫描本地值伪造 R12 canary 证明。

### 4.5 真实 setx node 与 needle artifact

- `test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 在 `_run_init` 之前调用 `_select_windows_test_canary(os.environ)` 选取 canary 作为 input value，然后断言 canary 不在 stdout/stderr 中、`OPENAI_API_KEY` 变量名在 stdout 中。
- 最终 `finally` block 通过 `_delete_registry_value_and_verify_absent` 清理 registry value。
- 没有写 needle artifact、JUnit property 或辅助字段。

**结论：canary contract 正确。Domain bytes、single NUL、known vector、canonicalization、determinism、fail-closed、local random 全部验证通过。**

## 5. Test doubles review（984-line diff）

### 5.1 Test infrastructure inventory

| Component | Lines | Purpose | Verdict |
| --- | --- | --- | --- |
| `_InitProcessResult` | 4 | Typed result with returncode/stdout/stderr only | 必要 |
| `_TrackedTemporaryHandle` | 37 | Record read/flush/seek on anonymous binary handles | 必要，owner-level contract verification |
| `_TemporaryHandleRecorder` | 17 | Record TemporaryFile mode + handle lifecycle | 必要 |
| `_ScriptedInitProcess` | 105 | Deterministic Popen state machine：wait/poll/kill outcomes, handle lifecycle, TimeoutExpired probes | 必要但最复杂 |
| `_ScriptedInitPopenFactory` | 64 | Record exact Popen contract (argv/cwd/env/stdin payload/shell/close_fds/text) + stdin rewind check | 必要 |
| `_ScriptedTokenFactory` | 17 | Scripted token_urlsafe for local random test | 必要 |
| `_ForbiddenTokenFactory` | 12 | Prove GitHub Actions path never falls back to random | 必要 |
| `_github_actions_canary` | 18 | Canary derivation from public run ID | 生产代码 |
| `_select_windows_test_canary` | 13 | Canary selector | 生产代码 |
| `_render_init_timeout` | 27 | Safe timeout projection renderer | 生产代码 |
| `_run_init` | 73 | Outer real CLI lifecycle owner | 生产代码 |

### 5.2 `_ScriptedInitProcess` 是否过度设计？

逐项审查 `_ScriptedInitProcess` 的每个 feature：

1. **Scripted wait/poll/kill**（~20 lines）：按顺序消费预定义 outcomes。无内置状态机，只是 FIFO queue 消费器。这是 deterministic testing 的最小实现 — `unittest.mock.Mock(side_effect=[...])` 也能做到，但 scripted process 还额外提供了 handle lifecycle tracking。

2. **Handle lifecycle tracking**（~25 lines）：`attach_handles`、`_require_open_handles`、closed-before-Popen/closed-during-lifecycle 检测。这些是测试正确性的核心：若 `_run_init` 提前关闭 handles 或 never binds them，这些 assertion 会 catch。这是 `Mock` 无法做到的。

3. **_write_output_once**（~12 lines）：模拟 child 写入 stdout/stderr。最多一次，在首次 `wait()` 调用时触发。这一设计正确反映了 child process 的典型行为 — 输出在 exit 前发生。

4. **TimeoutExpired probe**（~10 lines）：构造包含 sentinel 的 raw `TimeoutExpired`，用于验证 raw timeout 确实含探针而 safe projection 不含。

5. **Exact call count guards**（~10 lines）：`"unexpected second init process wait"` / `"unexpected second init process poll"` — 禁止超出脚本的调用，确保每个 state 的 exact wait/poll/kill count 完全匹配预期。

每个 feature 都有直接的测试断言对应。没有死代码、没有"just in case"的 defense、没有 mock framework 的 workaround。这是 clean 的手写 test double，不是过度设计。

### 5.3 重复语义检查

- `_TrackedTemporaryHandle` 与 `_TemporaryHandleRecorder` 之间的关系清晰：Recorder 创建 tracked handles，每个 tracked handle 记录自身操作。无职责重叠。
- `_ScriptedInitPopenFactory` 与 `_ScriptedInitProcess` 之间的关系清晰：Factory 记录 Popen 输入 contract 并绑定 handles 到 process；Process 执行运行时行为（wait/poll/kill/write output）。无职责重叠。
- 各 `_ForbiddenTokenFactory` / `_ScriptedTokenFactory` 之间无交叉 — 前者用于 fail-closed 测试，后者用于 local random 测试。

### 5.4 是否测到了真实 owner？

- `_run_init()` 是 outer real-CLI process 的 **唯一 test owner**。所有 owner test 都通过 `_install_scripted_init_process` 替换 `tempfile.TemporaryFile` 与 `subprocess.Popen`，然后直接调用 `_run_init()`。
- Owner tests 断言的是 `_run_init` 的行为 contract，而不是 mock 的内部实现。每个断言都对应 plan 中定义的一个 contract 要求。
- 真实 POSIX/Windows smoke tests（`test_posix_real_*`, `test_windows_real_*`）走完整的真实进程路径，不替换 TemporaryFile/Popen。

**结论：test doubles 规模合理，每个 component 都有明确且唯一的测试目的，无冗余语义，无 mock framework workaround，真实 owner contract 被覆盖。**

## 6. README changes

- `+9/-3` lines in `tests/README.md`。
- 补充了 outer CLI timeout failure projection 的安全字段说明：`category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`、`process_state_after_cleanup_timeout`。
- 补充了 artifact 可记录环境变量名但不记录 stdin input value 的约束。
- 没有扩大 root README 的用户 CLI workflow 或交互/排障职责。
- 符合 `tests/README.md` 的更新边界：只描述当前测试事实。

## 7. Security scan

| Scan | Result |
| --- | --- |
| `communicate(` in S3 payload | 零命中 |
| `shell=True` in S3 payload | 零命中 |
| `errors=...replace` in S3 payload | 零命中 |
| `mkstemp` / `NamedTemporaryFile` in S3 payload | 零命中（使用 `TemporaryFile` 而非 `NamedTemporaryFile`） |
| `CREATE_NEW_PROCESS_GROUP` / `JobObject` / `Start-Process` / `PowerShell` | 零命中 |
| Process group / job object | 零命中 |
| Replacement decode in failure path | 零命中 |
| GitHub Secrets / configured production values 读访问 | 零命中 |
| `reg.exe` 新增调用 | 零命中（既有 registry cleanup/query owner 未修改） |
| `winreg` 或 process-isolation alternatives | 零命中 |
| Production / S1 / S2 / workflow / root README / plan / design / deferred paths | 零 diff |

## 8. Semantic ownership verification

| 语义 | Owner | 实现位置 | 正确? |
| --- | --- | --- | --- |
| Outer real CLI process lifecycle | `_run_init()` in `tests/cli/test_init_smoke.py` | `_run_init()` | ✓ |
| Three anonymous binary handles | `_run_init()` via `TemporaryFile(mode="w+b")` | Context manager | ✓ |
| stdin write/flush/rewind | `_run_init()` | Lines before Popen call | ✓ |
| Timeout deadline poll | `_run_init()` except handler | `process.poll()` | ✓ |
| Bounded direct-process cleanup | `_run_init()` except handler | `process.kill()` + `process.wait(timeout=...)` | ✓ |
| Cleanup timeout single poll | `_run_init()` except handler | Exactly one `process.poll()` after cleanup timeout | ✓ |
| Safe failure projection | `_render_init_timeout()` | Only category/timeout/cleanup fields | ✓ |
| `pytest.fail(pytrace=False)` | `_run_init()` except handler | `pytest.fail(safe_message, pytrace=False)` | ✓ |
| Canary derivation | `_github_actions_canary()` | SHA-256 of domain + canonical run ID | ✓ |
| Canary selection policy | `_select_windows_test_canary()` | GitHub Actions → deterministic; local → random; fail-closed | ✓ |
| Test evidence boundary | `tests/README.md` | Only test-observable behavior | ✓ |

无语义所有权漂移：每个业务事实有唯一 owner，下游消费者不从 raw fields 反推语义。

## 9. Project constraints compliance

| 约束 | 检查结果 |
| --- | --- |
| 中文 docstring（函数必须提供完整中文 docs） | ✓ — 所有新增函数/类有完整中文 docstring |
| 禁止 `Any`/`object`/无类型签名 | ✓ — 全部有精确类型注解 |
| 禁止 `hasattr`/`getattr` | ✓ — 零命中 |
| 禁止魔法数字/字符串 | ✓ — 常量均有 `Final` 命名 |
| 禁止兼容性代码 | ✓ — 无 re-export、wrapper、fallback |
| 测试跟随实现边界 | ✓ — 旧 `_run_init` 被完整替换，无兼容分支 |
| 模块级私有辅助函数 | ✓ — 全部为 `_` 前缀的模块级函数/类 |
| 语义 owner 明确 | ✓ — 每个 contract 有唯一 owner |

## 10. Adversarial failure pass

针对以下 adversarial scenarios 做了逐项验证：

| Scenario | Result |
| --- | --- |
| `input_text` 含 surrogate character（`\ud800`）| `UnicodeEncodeError` before Popen，零 Popen call ✓ |
| `stdout` 含 invalid UTF-8（`\xff`）| `UnicodeDecodeError` after reading both channels ✓ |
| `TimeoutExpired.__str__` 含 sentinel | True（raw timeout），但 `pytrace=False` 阻止了泄漏 ✓ |
| `TimeoutExpired.output` 含 sentinel bytes | True（raw timeout），但 failure path 不读取 handles ✓ |
| Cleanup timeout 后第二次 wait/kill | 零命中（test 精确断言 wait_calls/poll_calls/kill_calls）✓ |
| Popen 前 stdin 未 rewind | `_ScriptedInitPopenFactory` 以 `stdin.tell() != 0` 断言 ✓ |
| GitHub Actions 中 `secrets.token_urlsafe` 回退 | `_ForbiddenTokenFactory` 零调用 ✓ |
| Invalid run ID 暴露 raw value | Test 验证 raw value 不在 AssertionError message 中 ✓ |
| 三个 handles 提前关闭 | `_ScriptedInitProcess._require_open_handles()` + test 断言 `all(handle.closed)` ✓ |
| 成功路径 handle 读取次数 != 1 | Test 断言 `stdout_handle.read_count == 1, stderr_handle.read_count == 1` ✓ |
| Double-close panic | `TemporaryFile.close()` 幂等，context manager 保证 unwind ✓ |
| locale/charmap 影响 strict decode | `errors="strict"` 固定，不受 `sys.getdefaultencoding()` 影响 ✓ |

全部 adversarial scenarios 通过或被 fail-closed 机制捕获。

## 11. Observations（非 material finding）

以下 observations 不构成 defect，不阻塞 accepted commit，仅作为 design note 记录：

### OBS-01：Frame clearing 的 defense-in-depth 性质

`input_text = ""` 与 `input_bytes = b""` 是有效的 defense-in-depth，但其实际安全保障来自 `pytest.fail(pytrace=False)` 不展开 frame locals。若未来 pytest 改变 `pytrace=False` 行为或引入新的 frame introspection mechanism，frame clearing 是最后一道防线。当前两层的组合安全、且没有替代机制。

**严重度**：NONE。当前行为正确，是 design choice 而非 defect。

### OBS-02：`_ScriptedInitProcess._write_output_once` 的时序简化

`_write_output_once()` 在首次 `wait()` 调用时写入 stdout/stderr。这简化了真实 child process 的行为（真实进程可能在 wait 前、wait 中、或 wait 后的任意时间点写入）。但对于 timeout 测试，由于 failure path 不读取 handles（已验证），写入时序不影响正确性。成功路径的写入时序仅影响 typed result 的内容（已验证正确）。

**严重度**：NONE。测试目的不依赖精确的 output timing，只依赖 typed result 的 exact match。

### OBS-03：`_render_init_timeout` 内部 invariant 失败时的非 `pytrace=False` 传播

若 `_render_init_timeout` 的 caller 传入不一致参数，renderer 抛出普通 `AssertionError`（非 `pytest.fail.Exception`）。这个错误不会经过 `pytrace=False` 保护。但：(a) 这只在编程错误时发生；(b) `AssertionError` message 不含 sensitive material（只有状态标签）；(c) 此时的 traceback 只涉及 renderer 的 caller（`_run_init` 中的 safe_message 构造行），不涉及 `TimeoutExpired` 对象。

**严重度**：NONE。不影响安全性；是 fail-closed 编程错误检测。

## 12. Real Windows residual

- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes。
- `test_windows_real_*` nodes 均被 `@pytest.mark.skipif(platform.system() != "Windows", ...)` 正确 skip。
- R12 dispatch-run lineage、workflow/event/branch/head SHA 验证与同-run log/all-artifact canary scan 仍为 `PENDING_RELEASE_BLOCKER`。
- 本 slice 的 Controller-owned remote gate 按 plan §5.3/§5.4 在 S3 accepted commit 并 push 后由 Controller 执行。
- 当前 local result 不声称关闭 WIN4/AR-F07 release blocker。

## 13. Ledger

| Category | Count |
| --- | --- |
| Accepted material finding | `0` |
| Rejected/not-a-finding | `0` |
| Needs evidence | `0` |
| Design contradiction | `0` |
| Local blocker | `0` |
| Unclassified residual | `0` |
| Observation (non-blocking) | `3`（OBS-01, OBS-02, OBS-03） |
| Real Windows residual | `PENDING_RELEASE_BLOCKER`，由 Controller remote gate 负责 |

## 14. Verdict

`PASS / MATERIAL_FINDING_0 / NO_BLOCKER / READY_FOR_CONTROLLER_ADJUDICATION`

Diff stat：`+970/-47`。Semantic ownership 正确。Popen binary handles contract、timeout four-state machine、safe renderer with `pytrace=False`、canary domain bytes/single-NUL/known-vector/fail-closed/local-random 全部正确实现。Test doubles 的 984-line diff 无过度设计或重复语义。No production/S1/S2/workflow/README overflow。Real Windows residual 保持 `PENDING_RELEASE_BLOCKER`，等待 S3 accepted commit 后 Controller remote gate。

Artifact path：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-code-review-ds.md`。
