# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S3 Complete Code Re-Review（AgentDS）

## 1. Review identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4`，同一 remediation continuation，不是新 WU。
- Slice：`WIN4-S3 — Timeout-safe outer harness and final docs`。
- Gate：dual complete code re-review（此 artifact 为 AgentDS route）。
- Baseline HEAD：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`（S2 accepted commit）。
- Branch：`phaseflow/host-issues-control`。
- Controller zero-change validation：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-code-review-fix-controller-validation.md`，SHA-256 `14a56fd256decd828aa05d774fe6385a98f5177fe514b2a1020f103f0b56eee9`，verdict `PASS / ZERO_CHANGE_FIX_CONFIRMED / READY_FOR_DUAL_COMPLETE_CODE_REREVIEW`。
- AgentCodex zero-change artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-code-review-fix-codex.md`，SHA-256 `3a5c0795d2516ef64877072d00c38788f23cf8ff6ac1f4053885911b9e2dae33`。
- Initial Controller adjudication：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-code-review-controller-adjudication.md`，SHA-256 `d930b774495caae85bf781b307dce4e76460027c20ad013b50ca7f2425098485`。
- Initial code reviews：AgentMiMo SHA-256 `68982769a89fa337377821f6284726a5e2d27077063f0399af3293403fff4272`；AgentDS SHA-256 `a873b018e093ac8308020dbbeaeff3b9f7495307d3397c5c31a23567e9de5966`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-controller-validation.md`，SHA-256 `d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6`。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md`，SHA-256 `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2`。

## 2. Evidence chain integrity

### 2.1 Immutable target re-confirmation

| Material | Locked SHA-256 | Fresh SHA-256 | Match |
| --- | --- | --- | --- |
| `tests/cli/test_init_smoke.py` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` | ✓ |
| `tests/README.md` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` | ✓ |
| Binary payload diff | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` | ✓ |

Diff stat：`tests/cli/test_init_smoke.py +963/-44`，`tests/README.md +7/-3`；共 `+970/-47`。

Implementation artifact、Controller validation、initial reviews、Controller adjudication、zero-change fix artifact 与 Controller zero-change validation 全部 SHA-256 均与各 gate 锁定值精确匹配。Evidence chain 无漂移。

### 2.2 Evidence chain graph

```
S2 accepted commit (5c8c11f)
  │
  ├── S3 implementation (AgentCodex) ── SHA 65afdbcd...a355e2
  │     │
  │     ├── S3 Controller validation ── SHA d9bfcf30...3f9c6 ── PASS
  │     │
  │     ├── Initial review (AgentMiMo) ── SHA 68982769...4272 ── PASS/MATERIAL_FINDING_0
  │     ├── Initial review (AgentDS) ── SHA a873b018...e5966 ── PASS/MATERIAL_FINDING_0/NO_BLOCKER
  │     │
  │     ├── Controller adjudication ── SHA d930b774...8485 ── ACCEPTED_FINDING=0/ZERO_CHANGE_FIX
  │     │
  │     ├── Zero-change fix (AgentCodex) ── SHA 3a5c0795...dae33 ── ZERO_CHANGE_FIX_CONFIRMED
  │     ├── Zero-change Controller validation ── SHA 14a56fd2...eee9 ── PASS
  │     │
  │     └── ★ 本 artifact（re-review AgentDS route）
  │
  └── Immutable payload: test_init_smoke.py + tests/README.md
```

## 3. Independent validation

Reviewer 在 `.venv` 下独立运行全部验证；环境 Python `3.11.15`、pytest `9.0.3`、pyright `1.1.409`。

| Validation | Fresh result |
| --- | --- |
| `pytest tests/cli/test_init_smoke.py -q` | `28 passed, 5 skipped, 3 warnings in 16.11s`；skip 全部为本地非 Windows 平台 |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | 零输出；PASS |
| `git diff --cached --name-only` | 零输出；staged tree empty |
| Payload diff SHA-256 vs locked | `8bba3cd2...6c4` — exact match |
| Test file SHA-256 vs locked | `6748c609...ec30` — exact match |
| README SHA-256 vs locked | `0fa4165b...6aa2` — exact match |
| Canary domain + known vector 独立重算 | domain 31 bytes, single NUL, digest `b8f2210d...0b97` — exact match |

三类 warning 均来自既有 edgartools deprecated imports；本 slice 未新增 warning owner。

## 4. Complete adversarial re-verification

从零逐行审查 `tests/cli/test_init_smoke.py`（1877 行）与 `tests/README.md` diff，以第一性原理重新验证全部 11 个 contract 维度。

### 4.1 Popen[bytes] + three anonymous handles

**逐行验证**：`_run_init()` 在 context manager 内创建三个 `tempfile.TemporaryFile(mode="w+b")` handles（line 604-608），通过 `subprocess.Popen[bytes]` 显式传入 `stdin/stdout/stderr`（line 617-636），固定 `shell=False`、`close_fds=True`、`text=False`。不调用 `communicate()`（grep 零命中）。三个 handles 由同一 `with` 管理，任意路径统一 unwind。

Owner test `test_run_init_uses_binary_anonymous_handles_and_returns_typed_utf8_result`（line 713-781）精确断言：
- `process_factory.shell is False`、`close_fds is True`、`text is False`
- `handle_recorder.modes == ["w+b", "w+b", "w+b"]`
- argv/cwd/env 保留
- stdin flush/seek 各一次
- 成功路径 stdout/stderr 各读一次
- 所有 handles 在退出后已关闭

**验证**：PASS。anonymous binary handles + Popen[bytes] contract 正确，跨平台语义一致。

### 4.2 stdin strict encode/flush/rewind/frame clearing

**逐行验证**（line 609-616）：
1. `input_bytes = input_text.encode("utf-8", errors="strict")` — 在 Popen 前执行
2. `stdin_handle.write(input_bytes)` + `flush()` + `seek(0)` — 正确的 anonymous handle 写入序列
3. `input_text = ""` + `input_bytes = b""` — 清空 local frame 中的 input 所有者
4. 然后才 `subprocess.Popen(...)`

Adversarial 验证：
- 非法 UTF-8 input（`\ud800`）→ `UnicodeEncodeError` before Popen，`process_factory.call_count == 0`（line 817-848）
- `_ScriptedInitPopenFactory` 验证 `stdin.tell() == 0`（已 rewind），然后 `stdin.read()` 验证 payload，再 `seek(0)` 归还 handle（line 403-413）
- 若 `Popen()` 自身抛异常（如 `FileNotFoundError`），frame locals 已清空，stdin handle 仍含数据但由 context manager 保护

**Frame clearing defense-in-depth 再确认**：`input_text = ""` 与 `input_bytes = b""` 只在 Popen 调用前执行。若 `pytest.fail()` 被调用，它发生在 Popen 之后、except 块之内——此时 frame locals 已清空。但实际安全保障来自 `pytest.fail(safe_message, pytrace=False)` 不展开 frame locals。独立验证确认：`pytest.fail.Exception.__context__` 在 `pytrace=False` 下不被渲染到 terminal/JUnit（见 §4.8）。Frame clearing 是有效的 defense-in-depth。

**验证**：PASS。flush/rewind/frame clearing 时序正确。

### 4.3 Success strict UTF-8 decode

**逐行验证**（line 660-670）：
```python
stdout_handle.seek(0)
stderr_handle.seek(0)
stdout_bytes = stdout_handle.read()
stderr_bytes = stderr_handle.read()
stdout = stdout_bytes.decode("utf-8", errors="strict")
stderr = stderr_bytes.decode("utf-8", errors="strict")
```
- 两个 channel 都在 decode 前读取——不会因 stdout decode 失败而丢失 stderr 数据。
- Owner test `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels`（line 851-883）验证 stdout decode 失败时 `stdout_handle.read_count == 1` 且 `stderr_handle.read_count == 1`——两个 channel 都被读取。
- Ordinary nonzero test（line 784-814）验证 `returncode=7` 不重分类为 timeout，且 `_assert_init_result` failure message 不含 output。

**验证**：PASS。strict decode 覆盖两个 channel，nonzero 不重分类，failure projection 不回显 output。

### 4.4 Timeout four-state machine

**逐行验证**（line 637-658）：状态机流程：

1. `process.wait(timeout=180)` → `TimeoutExpired` caught
2. `returncode_at_timeout = process.poll()` — deadline poll
3. 若 `returncode_at_timeout is not None`：已退出 → `cleanup="completed"`，直接 `pytest.fail()`
4. 若 `returncode_at_timeout is None`：`process.kill()` → `process.wait(timeout=180)`
5. 若 cleanup wait 成功 → `cleanup="completed"`，`pytest.fail()`
6. 若 cleanup wait timeout → `cleanup="timeout"`，`process.poll()`（恰好一次），投影 running/exited

四状态 parametrized test（line 935-1018）覆盖：

| State | Deadline poll | Kill | Cleanup wait | Cleanup poll | wait_calls | poll_calls | kill_calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1: 已退出 | `1` (exit) | 0 | 0 | 0 | 1 | 1 | 0 |
| 2: 运行→清理完成 | `None` | 1 | success (`-9`) | 0 | 2 | 1 | 1 |
| 3: 清理超时仍运行 | `None` | 1 | timeout | 1 → `None` | 2 | 2 | 1 |
| 4: 清理超时已退出 | `None` | 1 | timeout | 1 → `23` | 2 | 2 | 1 |

每个 state 的 `wait_calls`、`poll_calls`、`kill_calls` 由 owner test 精确断言（line 1001-1003）。Cleanup timeout 后恰好一次 poll（`process.poll_calls == 2` 对 State 3/4），此后无额外 wait/kill/process-tree 治理。

**返回码真源独立确认**：
- `cleanup_returncode` 初始值取 `returncode_at_timeout`（State 1）
- 需要 kill 时被 cleanup wait 成功值覆盖（State 2）
- cleanup wait 超时时被第二次 `poll()` 覆盖（State 3/4）
- 所有状态的 returncode 都来自 `poll()` 或 `wait()` 的直接返回值——不从 `TimeoutExpired` 对象派生

**验证**：PASS。四状态状态机完整精确，无遗漏状态或多余操作。

### 4.5 Cleanup timeout 恰好一次额外 poll 且不再 wait/kill

**逐行验证**（line 648-651）：
```python
except subprocess.TimeoutExpired:
    cleanup = "timeout"
    cleanup_returncode = process.poll()
    process_state_after_cleanup_timeout = "running" if cleanup_returncode is None else "exited"
```
- 此后直接到 `_render_init_timeout()` 和 `pytest.fail()`——没有额外 `wait()`、`kill()`、`terminate()` 或 process-tree 操作。
- State 3 test 验证 `process.poll_calls == 2`、`process.kill_calls == 1`、`process.wait_calls == [_PROCESS_TIMEOUT_SECONDS] * 2`。

**验证**：PASS。cleanup timeout 后恰好一次 poll，无二次 wait/kill。

### 4.6 Failure path zero-read

**逐行验证**：`stdout_handle.seek(0)` / `read()` / `stderr_handle.seek(0)` / `read()` 只在 `try` 块的非异常路径执行（line 660-665）。`except subprocess.TimeoutExpired` 路径直接到 `pytest.fail()`（line 658）。

Owner test（line 1015-1017）验证 `stdout_handle.read_count == 0` 与 `stderr_handle.read_count == 0`。

**验证**：PASS。failure path 确实不读取 stdout/stderr。

### 4.7 Safe renderer

**逐行验证** `_render_init_timeout()`（line 550-582）：
- 输出格式：`category=dayu_cli_init_timeout timeout_seconds=180 returncode_at_timeout=<rc|not_exited> cleanup=<completed|timeout> cleanup_returncode=<rc|not_available> [process_state_after_cleanup_timeout=<running|exited>]`
- `timeout_seconds` 使用 `:g` 格式避免浮点噪声
- 不含 argv、cwd、path、input、output、exception type/class name
- `process_state_after_cleanup_timeout` 仅在 cleanup timeout 后追加
- Internal invariant guard（line 567-569）：`completed` 不可有 post-timeout state，`timeout` 必须有 post-timeout state

**验证**：PASS。renderer 只包含安全状态字段，invariant guard 正确。

### 4.8 pytest.fail(pytrace=False) 与 context chain

**独立验证 `__context__` chain**：当 `pytest.fail()` 在 `except subprocess.TimeoutExpired:` 块中被调用时，Python 隐式将 `TimeoutExpired` 设为 `Failed.__context__`。独立 Python 脚本证实：
- `Failed.__context__` 存在且包含 inner exception（含 secret）
- `str(Failed)` 与 `repr(Failed)` 不含 inner exception 的 secret
- `pytrace=False` 禁止 pytest 渲染 traceback chain → terminal/JUnit 只包含 safe message

Owner test（line 973-1018）的 `forbidden_material` checklist 覆盖：sentinel、canary、sensitive_input、workspace_root、REPOSITORY_ROOT、`"sensitive-cli-argv"`、`"stdin"`、`"stdout"`、`"stderr"`、`"TimeoutExpired"`。验证 `str(raised.value)`、`repr(raised.value)`、`capsys.readouterr().out` 与 `capsys.readouterr().err` 全部零命中。

**关于 raw timeout probe**：Test 同时验证 `str(raw_timeout)` 和 `raw_timeout.output` 包含敏感探针——这证明 raw exception 确实"脏"，从而证明 safe renderer 的必要性。若 CPython 未来改变 `TimeoutExpired.__str__` 格式，probe 断言会 fail closed（test 失败），但 safe renderer 仍安全——这是可接受的 probe 策略。此 residual 已在 MiMo initial review 与 Controller adjudication 中记录，不构成 finding。

**验证**：PASS。safe renderer 正确过滤所有 forbidden material，pytrace=False 阻止 traceback chain 泄漏。

### 4.9 GitHub Actions canary

**Domain bytes 独立验证**（line 61）：
- `_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`
- 长度：`31` bytes ✓
- 前缀：`dayu-ar-f07-win4-r12-canary-v1`（30 ASCII bytes）✓
- 末字节：`\x00`（single NUL）✓
- NUL 计数：exactly `1` ✓

**Known vector 独立重算**（line 1021-1041）：
- SHA-256(`dayu-ar-f07-win4-r12-canary-v1\x00` + `1`) = `b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓
- Full canary：`sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓

**Canonicalization**（line 516-531）：
- `isascii()` + `isdecimal()` 守卫 → 阻止全角数字、负数、空字符串
- `int(raw)` 后 `<= 0` 守卫 → 阻止零值
- `str(int("0001"))` → `"1"` → deterministic canonicalization ✓
- Owner test 验证 `_github_actions_canary("0001") == _github_actions_canary("1")` ✓

**Fail-closed matrix**（line 1044-1091）：6 种 invalid environment 全部验证 `AssertionError` 且 `forbidden_random.calls == 0`：

| Condition | Behavior |
| --- | --- |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID` 缺失 | `AssertionError`，random 零调用 |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID=""` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="abc"` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="0"` | `AssertionError`（`run_id <= 0`） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="-1"` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="１２"`（全角） | `AssertionError`（`isascii()` → False） |

**合法 workflow path**（line 1094-1114）：`GITHUB_RUN_ID="0001"` → deterministic canary，`forbidden_random.calls == 0`。

**本地随机路径**（line 1117-1140）：非 GitHub Actions 环境每次调用 `secrets.token_urlsafe(32)`，两次调用返回互异值。Owner test 使用 `_ScriptedTokenFactory` 验证每次 `calls == [32, 32]`。

**真实 setx node**（line 1829-1865）：`_select_windows_test_canary(os.environ)` 在 `_run_init()` 前选值；断言 `sentinel not in result.stdout` 与 `sentinel not in result.stderr`；finally 清理 registry value。没有新增 JUnit property 或 needle artifact。

**验证**：PASS。domain bytes、single NUL、known vector、canonicalization、determinism、fail-closed、local random 全部正确。

### 4.10 Test doubles design boundary

逐项审查 test infrastructure：

| Component | Lines | Purpose | Verdict |
| --- | --- | --- | --- |
| `_InitProcessResult` | 4 | Typed result（returncode/stdout/stderr only） | 必要，contract 定义 |
| `_TrackedTemporaryHandle` | 37 | Record read/flush/seek on anonymous binary handles | 必要，owner contract 验证 |
| `_TemporaryHandleRecorder` | 17 | Record TemporaryFile mode + handle lifecycle | 必要 |
| `_ScriptedInitProcess` | 105 | Deterministic Popen wait/poll/kill state machine | 必要但最复杂 |
| `_ScriptedInitPopenFactory` | 64 | Record exact Popen contract + stdin rewind check | 必要 |
| `_ScriptedTokenFactory` | 17 | Scripted token_urlsafe for local random test | 必要 |
| `_ForbiddenTokenFactory` | 12 | Prove GitHub Actions path never falls back to random | 必要 |
| `_github_actions_canary` | 18 | Canary derivation（生产代码） | 必要 |
| `_select_windows_test_canary` | 13 | Canary selector（生产代码） | 必要 |
| `_render_init_timeout` | 27 | Safe timeout projection renderer（生产代码） | 必要 |
| `_run_init` | 73 | Outer real CLI lifecycle owner（生产代码） | 必要 |

**`_ScriptedInitProcess` 逐 feature 再审**：
1. Scripted wait/poll/kill（FIFO queue consumer）：最小 deterministic 状态机
2. Handle lifecycle tracking：测试正确性核心——`_run_init` 提前关闭 handles 会被 catch
3. `_write_output_once`：最多一次、在首次 `wait()` 触发——正确反映真实 child 行为
4. TimeoutExpired probe：构造含 sentinel 的 raw exception，验证 raw/projection 分离
5. Exact call count guards：禁止超出脚本的调用

每个 feature 都有直接 owner test 断言。无 dead code、无 "just in case" defense、无 mock framework workaround。

**语义重复检查**：
- `_TrackedTemporaryHandle` vs `_TemporaryHandleRecorder`：Recorder 创建 tracked handles → 清晰分层
- `_ScriptedInitPopenFactory` vs `_ScriptedInitProcess`：Factory 记录 Popen input contract → Process 执行运行时行为 → 无职责重叠
- `_ForbiddenTokenFactory` vs `_ScriptedTokenFactory`：前者 fail-closed 测试，后者 local random 测试 → 无交叉

**是否测到了真实 owner**：所有 owner test 通过 `_install_scripted_init_process` 替换 `tempfile.TemporaryFile` 与 `subprocess.Popen`，直接调用 `_run_init()`。每个断言对应 plan 中定义的 contract 要求。真实 POSIX/Windows smoke tests（`test_posix_real_*`, `test_windows_real_*`）走完整真实进程路径。

**验证**：PASS。test doubles 规模合理，每个 component 有明确且唯一的测试目的，无冗余语义，无 mock framework workaround，未固化偶然行为。

### 4.11 README boundary

`tests/README.md` diff（`+7/-3`）增加两段：
1. "产品 `setx` persistence 调用的 native output 没有消费者...outer CLI 仍通过 anonymous binary handles 捕获 stdout/stderr，并在 process 成功结束后 strict UTF-8 解码。"
2. "outer CLI timeout 失败只投影 `category`、`timeout_seconds`...artifact 可记录环境变量名，但不记录 stdin input value。"

这是测试 evidence boundary 的 accepted 区别——不是用户手册、Engine 设计文档或排障指南。没有扩大 root README 的职责范围。

**验证**：PASS。README 更新精确克制，scope 正确。

## 5. Scope, security, and deferred boundary re-verification

| Scan | Result |
| --- | --- |
| `communicate(` in S3 payload | 零命中 |
| `shell=True` in S3 payload | 零命中 |
| `errors=...replace` in S3 payload | 零命中 |
| `mkstemp` / `NamedTemporaryFile` in S3 payload | 零命中 |
| `CREATE_NEW_PROCESS_GROUP` / `JobObject` / `Start-Process` / `PowerShell` | 零命中 |
| `hasattr` / `getattr` in S3 new code | 零命中 |
| `Any` / `object` / 无类型签名 in S3 new code | 零命中 |
| GitHub Secrets / configured production values 读访问 | 零命中 |
| `reg.exe` 新增调用 | 零命中（既有 registry cleanup/query owner 未修改） |
| `winreg` 或 process-isolation alternatives | 零命中 |
| Production diff beyond S2 | 零（`dayu/cli/init_environment.py` 零 diff） |
| S1/S2 owner diff | 零 |
| Workflow diff | 零 |
| Root README diff | 零 |
| Plan / design / deferred Issue paths diff | 零 |
| `git diff --check` | PASS |
| Staged tree | empty |

Pre-existing dirty `docs/host/issues-implementation-control.md` 的 gate 状态更新不是 S3 payload 的一部分；AgentCodex 未改写它。

## 6. Semantic ownership re-verification

| 语义 | Owner | 实现位置 | 正确? |
| --- | --- | --- | --- |
| Outer real CLI process lifecycle | `_run_init()` in `tests/cli/test_init_smoke.py` | `_run_init()` line 585-670 | ✓ |
| Three anonymous binary handles | `_run_init()` via `TemporaryFile(mode="w+b")` | Context manager line 604-608 | ✓ |
| stdin write/flush/rewind | `_run_init()` | Lines 609-612 | ✓ |
| stdin frame clearing | `_run_init()` | Lines 615-616 | ✓ |
| Popen[bytes] contract | `_run_init()` | Lines 617-636 | ✓ |
| Timeout deadline poll | `_run_init()` except handler | `process.poll()` line 640 | ✓ |
| Bounded direct-process cleanup | `_run_init()` except handler | `process.kill()` + `process.wait(timeout=...)` line 645-647 | ✓ |
| Cleanup timeout single poll | `_run_init()` except handler | Exactly one `process.poll()` line 650 | ✓ |
| Safe failure projection | `_render_init_timeout()` | Line 550-582 | ✓ |
| `pytest.fail(pytrace=False)` | `_run_init()` except handler | Line 658 | ✓ |
| Canary derivation | `_github_actions_canary()` | Line 516-531 | ✓ |
| Canary selection policy | `_select_windows_test_canary()` | Line 534-547 | ✓ |
| Test evidence boundary | `tests/README.md` | Only test-observable behavior | ✓ |

无语义所有权漂移：每个业务事实有唯一 owner，下游消费者不从 raw fields 反推语义。S3 的 test outer process 不以 test cleanup 替代 S2 production setx owner，不增加 process-tree/job object/process group/workflow redact/global subprocess helper 或 named-temp cleanup framework。

## 7. Observation re-review

### 7.1 OBS-01（frame clearing defense-in-depth）→ 维持 non-material

Frame clearing（`input_text = ""` / `input_bytes = b""`）的安全保障来自 `pytest.fail(pytrace=False)` 不展开 frame locals。Frame clearing 是有效的 defense-in-depth——若未来 pytest 改变 `pytrace=False` 行为或引入新的 frame introspection mechanism，它是最后一道防线。当前两层组合安全，没有需要替换的机制。

**回流检查**：零回流。没有增加 frame-inspection 兼容、额外 try/finally 或 pytest/JUnit workaround。

### 7.2 OBS-02（scripted output timing 简化）→ 维持 non-material

`_write_output_once()` 在首次 `wait()` 时写入——这简化了真实 child process 的 output timing。但 timeout path 不读取 handles（verified），成功路径的 typed result exact match 已验证。时序简化不参与被断言的业务语义。

**回流检查**：零回流。没有增加 output-timing 模拟框架或 real-subprocess write-ordering probe。

### 7.3 OBS-03（renderer invariant 非 pytrace=False 传播）→ 维持 non-material

`_render_init_timeout` 内部 invariant 失败时抛出普通 `AssertionError`（非 `pytest.fail.Exception`）。但：(a) 只在编程错误时发生；(b) message 只含状态标签，不含 sensitive material；(c) traceback 只涉及 renderer caller，不涉及 `TimeoutExpired` 对象。

**回流检查**：零回流。没有增加 renderer fallback、try/except wrapper 或 exception-type conversion。

### 7.4 MiMo residual（CPython `TimeoutExpired.__str__` 格式变化）→ 维持 non-material

若 CPython 改变 `TimeoutExpired.__str__` 格式，raw-timeout owner probe 会 fail closed（test 失败），但 safe renderer 仍安全——safe renderer 不依赖 CPython exception format。这是可接受的 probe 策略。

**回流检查**：零回流。没有增加 CPython exception format 兼容或 version-gated probe。

### 7.5 新增 observation：本 re-review 无新 observation

经从零完整审查 1877 行 test 文件与 README diff，未发现 new material finding、new observation 或需补充的 design note。

## 8. Project constraints compliance re-check

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
| 禁止 God object/function/dataclass | ✓ — 职责分离清晰 |
| LLM-facing 文本约束 | ✓ — 不涉及（本 slice 不修改 prompt/tool schema/memory） |

## 9. Ledger

| Category | Initial review | Post-adjudication | This re-review |
| --- | --- | --- | --- |
| Accepted material finding | `0` | `0` | `0` |
| Rejected/not-a-finding | `0` | `0` | `0` |
| Needs evidence | `0` | `0` | `0` |
| Design contradiction | `0` | `0` | `0` |
| Local blocker | `0` | `0` | `0` |
| Unclassified residual | `0` | `0` | `0` |
| Observation (non-blocking) | `3`（OBS-01, 02, 03） | `3`（maintained） | `3`（unchanged, zero reintroduction） |
| MiMo raw-timeout probe residual | `1` | `1`（maintained） | `1`（unchanged, zero reintroduction） |
| New observation this re-review | — | — | `0` |
| Real Windows residual | `PENDING_RELEASE_BLOCKER` | `PENDING_RELEASE_BLOCKER` | `PENDING_RELEASE_BLOCKER` |

## 10. Verdict

`PASS / MATERIAL_FINDING_0 / NO_BLOCKER / OBSERVATION_REINTRODUCTION=0 / READY_FOR_CONTROLLER_ADJUDICATION`

从零完整审查 S3 immutable payload（`tests/cli/test_init_smoke.py` +963/-44、`tests/README.md` +7/-3）、implementation artifact、Controller validation、两路 initial review、Controller adjudication、zero-change fix artifact 与 Controller zero-change validation。独立验证所有 SHA-256、测试（`28 passed, 5 skipped`）、pyright（`0 errors`）、diff-check 与 staged-tree。

全部 11 个 contract 维度通过 adversarial re-verification：Popen[bytes] + three anonymous handles、stdin flush/rewind/frame clearing、strict UTF-8 decode、timeout four-state machine、cleanup timeout single poll、failure path zero-read、safe renderer with pytrace=False、canary domain bytes/single NUL/known vector/fail-closed/local random、test doubles design boundary、README scope、security/deferred boundary。

三个 OBS observations 与 MiMo raw-timeout probe residual 均维持 non-material，零回流——没有添加 frame-inspection 兼容、output-timing 模拟、renderer fallback、CPython exception format 兼容或任何 test shim。无 new finding 或 new observation。

## 11. Real Windows residual

- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes。
- `test_windows_real_*` nodes 均被 `@pytest.mark.skipif(platform.system() != "Windows", ...)` 正确 skip。
- R12 dispatch-run lineage、workflow/event/branch/head SHA 验证与同-run log/all-artifact canary scan 仍为 `PENDING_RELEASE_BLOCKER`。
- 真实 Windows closure 的 owner/destination 保持为 S3 accepted commit 并 push 后的 Controller remote gate。
- 当前 local result 不声称关闭 WIN4/AR-F07 release blocker。

## 12. Next gate

本 artifact 停止在 `READY_FOR_CONTROLLER_ADJUDICATION`。下一 gate 仅为 Controller 读取本 artifact 与 MiMo 并发 re-review artifact，做最终 adjudication；通过后才可进入 S3 accepted commit、push 与 remote Windows dispatch。当前授权不允许 accepted commit、push、remote dispatch、merge 或 observation 实现。

Artifact path：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-code-rereview-ds.md`。
