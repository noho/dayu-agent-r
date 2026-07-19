# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S3 Complete Code Re-Review（AgentMiMo）

## 1. Re-review identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4`，同一 remediation continuation。
- Slice：`WIN4-S3 — Timeout-safe outer harness and final docs`。
- Gate：dual complete code re-review（zero-change fix confirmation 后）。
- Baseline HEAD：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`。
- Branch：`phaseflow/host-issues-control`。
- Immutable payload target：`tests/cli/test_init_smoke.py`、`tests/README.md`。
- Payload binary diff SHA-256：`8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4`。
- Test file SHA-256：`6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30`。
- Tests README SHA-256：`0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2`。
- AgentCodex implementation artifact SHA-256：`65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2`。
- Controller validation SHA-256：`d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6`。
- Initial AgentMiMo review SHA-256：`68982769a89fa337377821f6284726a5e2d27077063f0399af3293403fff4272`。
- Initial AgentDS review SHA-256：`a873b018e093ac8308020dbbeaeff3b9f7495307d3397c5c31a23567e9de5966`。
- Controller adjudication SHA-256：`d930b774495caae85bf781b307dce4e76460027c20ad013b50ca7f2425098485`。
- AgentCodex zero-change artifact SHA-256：`3a5c0795d2516ef64877072d00c38788f23cf8ff6ac1f4053885911b9e2dae33`。
- Controller zero-change validation SHA-256：`14a56fd256decd828aa05d774fe6385a98f5177fe514b2a1020f103f0b56eee9`。

## 2. Verdict

`PASS / MATERIAL_FINDING_0 / OBSERVATION_BACKFLOW_0 / NO_BLOCKER`

## 3. Re-review scope

从零审查 `tests/cli/test_init_smoke.py`（1877 行，+956/-41 diff）和 `tests/README.md`（+7/-3 diff）的完整内容。
不复用任何先前 review 结论；以第一性原理逐项验证所有 owner contract、状态机、安全边界、test doubles 设计、
scope 与 observation 回流。

## 4. Immutable evidence verification

Re-reviewer 在 `.venv` 下独立运行并验证所有锁定 SHA-256：

| Material | Expected SHA-256 | Actual SHA-256 | Match |
| --- | --- | --- | --- |
| HEAD commit | `5c8c11f8...633` | `5c8c11f88fb0d935ad5730aa7d892ad26a060633` | ✓ |
| Payload binary diff | `8bba3cd2...6c4` | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` | ✓ |
| `tests/cli/test_init_smoke.py` | `6748c609...ec30` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` | ✓ |
| `tests/README.md` | `0fa4165b...6aa2` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` | ✓ |
| Implementation artifact | `65afdbc...55e2` | `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2` | ✓ |
| Controller validation | `d9bfcf3...f9c6` | `d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6` | ✓ |
| Initial MiMo review | `6898276...f4272` | `68982769a89fa337377821f6284726a5e2d27077063f0399af3293403fff4272` | ✓ |
| Initial DS review | `a873b01...e5966` | `a873b018e093ac8308020dbbeaeff3b9f7495307d3397c5c31a23567e9de5966` | ✓ |
| Controller adjudication | `d930b77...8485` | `d930b774495caae85bf781b307dce4e76460027c20ad013b50ca7f2425098485` | ✓ |
| Codex zero-change | `3a5c079...ae33` | `3a5c0795d2516ef64877072d00c38788f23cf8ff6ac1f4053885911b9e2dae33` | ✓ |
| Controller zero-change val | `14a56fd...eee9` | `14a56fd256decd828aa05d774fe6385a98f5177fe514b2a1020f103f0b56eee9` | ✓ |

Staged tree empty；`git diff --check` PASS。

## 5. Fresh independent validation

| Validation | Result |
| --- | --- |
| `pytest tests/cli/test_init_smoke.py -q` | `28 passed, 5 skipped, 3 warnings in 16.10s` |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff（changed files） | `All checks passed!` |
| `git diff --check` | PASS |
| Staged tree | empty |

三类 warning 均来自既有 edgartools deprecated imports，本 slice 未新增 warning owner。

## 6. Adversarial dimension-by-dimension re-review

### 6.1 Popen[bytes] + three anonymous handles

**代码位置**：`_run_init()` line 604-636。

```python
with (
    tempfile.TemporaryFile(mode="w+b") as stdin_handle,
    tempfile.TemporaryFile(mode="w+b") as stdout_handle,
    tempfile.TemporaryFile(mode="w+b") as stderr_handle,
):
```

- 三个 handles 均为 `mode="w+b"` binary mode，与 `Popen[bytes]` 类型参数一致。
- `shell=False` + `close_fds=True` + `text=False` 是正确的跨平台安全组合。
- `stdin=stdin_handle` 把 anonymous handle 直接传给 Popen，child 通过继承 fd 读取。
- context manager exit 保证三个 handles 在任何路径（success/timeout/exception）都被关闭。
- `communicate(` 在整个文件中零命中——没有使用 `subprocess.run(input=...)` 或 `Popen.communicate()`。

**Re-verdict**：PASS。anonymous binary handles + Popen[bytes] contract 正确。

### 6.2 stdin flush/rewind/frame clearing

**代码位置**：`_run_init()` line 609-616。

```python
input_bytes = input_text.encode("utf-8", errors="strict")
stdin_handle.write(input_bytes)
stdin_handle.flush()
stdin_handle.seek(0)

# timeout failure 前主动清空 helper frame 中唯一的 input 文本与 bytes 所有者。
input_text = ""
input_bytes = b""
```

- `input_text.encode("utf-8", errors="strict")` 在 Popen 前执行，非法 UTF-8 surrogate 在此失败。
- `write → flush → seek(0)` 是正确的 anonymous handle 写入序列。
- `input_text = ""` 和 `input_bytes = b""` 在 Popen 调用前清空 frame 中的 input 变量。
- 清空发生在 `stdin_handle.write()` 之后、`Popen()` 之前——数据已在 handle 内，frame 变量被置空。

**Re-verdict**：PASS。flush/rewind/frame clearing 时序正确，strict encode 在 Popen 前。

### 6.3 success strict decode

**代码位置**：`_run_init()` line 660-670。

```python
stdout_handle.seek(0)
stderr_handle.seek(0)
stdout_bytes = stdout_handle.read()
stderr_bytes = stderr_handle.read()
stdout = stdout_bytes.decode("utf-8", errors="strict")
stderr = stderr_bytes.decode("utf-8", errors="strict")
```

- `seek(0)` + `read()` + `decode("utf-8", errors="strict")` 只在 `try` 块的 non-exception 路径执行。
- `UnicodeDecodeError` 在此处抛出，传播给调用方。
- test `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels` 验证两个 channel 都被读取（`stdout_handle.read_count == 1` 和 `stderr_handle.read_count == 1`）。
- `test_run_init_returns_ordinary_nonzero_as_typed_result` 验证 `returncode=7` 不被重分类为 timeout。
- `_assert_init_result` 的 failure message 不包含 stdout/stderr 内容——只包含 expected/actual returncode。

**Re-verdict**：PASS。strict decode 覆盖两个 channel，nonzero 不重分类。

### 6.4 timeout 四状态状态机

**代码位置**：`_run_init()` line 637-658。

四状态矩阵：

| State | deadline poll | kill | cleanup wait | post-cleanup poll | process_state |
| --- | --- | --- | --- | --- | --- |
| 1: 已退出 | `returncode` (非 None) | 0 | 0 | 0 | N/A |
| 2: 运行→cleanup 完成 | `None` | 1 | 1 (success) | 0 | N/A |
| 3: 运行→cleanup timeout→running | `None` | 1 | 1 (timeout) | 1 → `None` | `"running"` |
| 4: 运行→cleanup timeout→exited | `None` | 1 | 1 (timeout) | 1 → `returncode` | `"exited"` |

Code path 逐行验证：

1. `process.wait(timeout=180)` → `TimeoutExpired` caught（line 638-639）。
2. `returncode_at_timeout = process.poll()` — 第一次 poll（line 640）。
3. If `returncode_at_timeout is not None`：已退出，`cleanup="completed"`, `cleanup_returncode=returncode_at_timeout`（line 641-642），直接到 `pytest.fail()`（line 652-658）。
4. If `returncode_at_timeout is None`：`process.kill()`（line 645），`cleanup_returncode = process.wait(timeout=180)`（line 647）。
5. If cleanup wait 成功：`cleanup="completed"`（default），到 `pytest.fail()`。
6. If cleanup wait timeout：`cleanup="timeout"`（line 649），`cleanup_returncode = process.poll()` — 第二次 poll（line 650）。
7. `process_state_after_cleanup_timeout = "running" if cleanup_returncode is None else "exited"`（line 651）。

Parametrized test `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup` 精确覆盖四种状态，断言：
- 每个状态的 `wait_calls`、`poll_calls`、`kill_calls` 精确匹配。
- cleanup timeout 后恰好一次 poll，此后无额外 wait/kill/process-tree 治理。

**Re-verdict**：PASS。四状态状态机完整且精确，无遗漏状态或多余操作。

### 6.5 deadline poll 与 cleanup returncode 不混淆

- `returncode_at_timeout` 来自 deadline 后的第一次 `poll()`——记录 deadline 时刻的进程状态。
- `cleanup_returncode` 来自 `process.wait(timeout=180)` 成功时的 returncode，或 cleanup timeout 后的第二次 `poll()`。
- State 1：`returncode_at_timeout == cleanup_returncode`——两者是同一个 poll 结果，语义一致。
- State 2：`returncode_at_timeout = None`，`cleanup_returncode = wait()` 成功值——语义不同，正确分离。
- State 3/4：`returncode_at_timeout = None`，`cleanup_returncode` 来自第二次 poll——正确。

**Re-verdict**：PASS。deadline poll 与 cleanup returncode 语义清晰分离。

### 6.6 cleanup timeout 恰好一次额外 poll 且不再 wait/kill

- cleanup timeout 路径（line 649-651）：`cleanup = "timeout"`，`cleanup_returncode = process.poll()`，`process_state_after_cleanup_timeout = ...`。
- 此后直接到 `_render_init_timeout()` 和 `pytest.fail()`——没有额外的 `wait()`、`kill()`、`terminate()` 或 process-tree 操作。
- Test 验证 `process.poll_calls == 2`（deadline poll + post-cleanup poll）和 `process.kill_calls == 1`。
- Test 验证 `process.wait_calls == [_PROCESS_TIMEOUT_SECONDS] * 2`（initial wait + cleanup wait）——恰好两次 wait。

**Re-verdict**：PASS。cleanup timeout 后恰好一次 poll，无二次 wait/kill。

### 6.7 failure path zero-read

- `stdout_handle.seek(0)` / `stdout_handle.read()` / `stderr_handle.seek(0)` / `stderr_handle.read()` 只在 `try` 块的 non-exception 路径执行（line 660-665）。
- `except subprocess.TimeoutExpired` 路径直接到 `pytest.fail()`——不 seek/read stdout/stderr handles。
- Test 验证 `stdout_handle.read_count == 0` 和 `stderr_handle.read_count == 0`。

**Re-verdict**：PASS。failure path 确实不读取 stdout/stderr。

### 6.8 pytest.fail(pytrace=False) 与 safe renderer

**代码位置**：`_render_init_timeout()` line 550-582，`_run_init()` line 658。

- `_render_init_timeout()` 只输出 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，以及 cleanup timeout 时的 `process_state_after_cleanup_timeout`。
- 不包含 argv、cwd、path、input、stdout、stderr、exception type 或 exception message。
- `pytrace=False` 阻止 pytest 在 failure 输出中包含 Python traceback。
- Test 的 `forbidden_material` 检查覆盖：sentinel、canary、sensitive_input、workspace_root、REPOSITORY_ROOT、"sensitive-cli-argv"、"stdin"、"stdout"、"stderr"、"TimeoutExpired"。
- Test 同时检查 `capsys.readouterr()` 的 stdout/stderr 不含 sentinel 或 canary。
- Test 的 `str(raised.value)` 和 `repr(raised.value)` 检查确认 safe message 不含 forbidden material。

**关于 raw timeout probe**：Test 验证 `str(raw_timeout)` 包含 sensitive material——这测试 CPython `TimeoutExpired.__str__` 的当前行为，确认 raw exception 确实"脏"，从而证明需要 safe renderer。如果 CPython 改变 `__str__` 格式，probe 断言可能失败，但 safe renderer 仍然安全——这是可接受的 probe 策略。

**Re-verdict**：PASS。safe renderer 正确过滤所有 forbidden material，pytrace=False 阻止 traceback 泄漏。

### 6.9 canary domain 精确 31 bytes / single NUL / known vector

**代码位置**：line 61，`_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`。

独立验证：
- `len(_WINDOWS_CANARY_DOMAIN) == 31` ✓
- `_WINDOWS_CANARY_DOMAIN[:-1] == "dayu-ar-f07-win4-r12-canary-v1".encode("ascii")` ✓
- `_WINDOWS_CANARY_DOMAIN[-1] == 0` ✓
- `_WINDOWS_CANARY_DOMAIN.count(bytes((0,))) == 1` — 只有一个 NUL ✓

Known vector 独立重算：
- `hashlib.sha256(b"dayu-ar-f07-win4-r12-canary-v1\x00" + b"1").hexdigest()` = `b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓
- `_github_actions_canary("1")` = `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` ✓

**Re-verdict**：PASS。domain bytes 精确 31 bytes，single NUL，known vector 精确匹配。

### 6.10 canonical positive ASCII decimal

**代码位置**：`_github_actions_canary()` line 516-531。

- `raw_run_id.isascii()` 和 `raw_run_id.isdecimal()` 守卫。
- `int(raw_run_id)` 后检查 `run_id <= 0`。
- `canonical_run_id = str(run_id)` — `int("0001")` → `1` → `"1"` canonicalization。
- Test 验证 `_github_actions_canary("0001") == _github_actions_canary("1")`。

**Re-verdict**：PASS。canonical decimal 正确处理 leading zeros。

### 6.11 workflow fail-closed / local random

**代码位置**：`_select_windows_test_canary()` line 534-547。

| Condition | Behavior |
| --- | --- |
| `GITHUB_ACTIONS!=true`（本地） | `secrets.token_urlsafe(32)`，随机 |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID` 缺失 | `AssertionError`，不 fallback 随机 |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID=""` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="abc"` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="0"` | `AssertionError`（`run_id <= 0`） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="-1"` | `AssertionError`（`isdecimal()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="１２"`（全角） | `AssertionError`（`isascii()` → False） |
| `GITHUB_ACTIONS=true` + `GITHUB_RUN_ID="1"` | 确定性 canary，`ForbiddenTokenFactory.calls == 0` |

- `_ForbiddenTokenFactory` 被 monkeypatch 到 `secrets.token_urlsafe`——任何调用都抛出 `AssertionError`。
- Test parametrizes 6 种 invalid 环境，每种都验证 `forbidden_random.calls == 0`。
- 非 GitHub Actions 路径：`test_local_windows_canary_remains_random_and_ignores_run_id` 验证 `secrets.token_urlsafe(32)` 被调用两次，每次 32 bytes。
- 合法 workflow 路径：`test_github_actions_canary_uses_public_run_id_without_random_fallback` 验证 `forbidden_random.calls == 0`。

**Re-verdict**：PASS。fail-closed 完整，local random 正确，无 fallback。

### 6.12 real setx test 与 needle artifact

- `test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 调用 `_select_windows_test_canary(os.environ)` 在 `_run_init()` 之前选值。
- 选中值作为 `sentinel` 传入 `_run_init()` 的 `input_text`。
- Test 断言 `sentinel not in result.stdout` 和 `sentinel not in result.stderr`。
- 没有新增 JUnit properties、辅助字段或 needle artifact。

**Re-verdict**：PASS。setx test 在 CLI 前选值，无辅助 needle。

### 6.13 test doubles 设计边界

Test doubles 分析：

| Double | 职责 | 是否过度设计 |
| --- | --- | --- |
| `_TrackedTemporaryHandle` | 记录 read/flush/seek 次数 | 否——验证 handle lifecycle contract |
| `_TemporaryHandleRecorder` | 记录三个 handles 的 mode 与实例 | 否——验证 TemporaryFile 被正确创建 3 次 |
| `_ScriptedInitProcess` | 模拟 wait/poll/kill 行为 | 否——测试 timeout 状态机的四种路径 |
| `_ScriptedInitPopenFactory` | 记录 Popen 参数并返回 scripted process | 否——验证 argv/cwd/env/shell/close_fds/text contract |
| `_ScriptedTokenFactory` | 返回顺序固定但互异的 token | 否——验证 local random 每次请求 32 bytes |
| `_ForbiddenTokenFactory` | 拒绝任何 random fallback | 否——验证 GitHub Actions 路径不回退 |
| `_ScriptedRegistryCommandRunner` | 按顺序返回指定退出码 | 否——验证 registry cleanup 状态机 |

每个 feature 都有直接的测试断言对应。没有死代码、没有"just in case"的 defense、没有 mock framework 的 workaround。
`_ScriptedInitProcess` 的 `wait_outcomes` / `poll_outcomes` 是 deterministic 状态机——测试的是 `_run_init()` 的代码路径，不是 CPython subprocess 的偶然行为。

**Re-verdict**：PASS。test doubles 精确覆盖 contract 行为，未固化偶然行为。

### 6.14 README boundary

- `tests/README.md` diff 只增加两段：
  1. 产品 `setx` persistence 调用的 native output 没有消费者，因此不由产品捕获；real-init gate 的 outer CLI 仍通过 anonymous binary handles 捕获 stdout/stderr，并在 process 成功结束后 strict UTF-8 解码。
  2. outer CLI timeout 失败只投影 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，cleanup timeout 时再投影 `process_state_after_cleanup_timeout`；artifact 可记录环境变量名，但不记录 stdin input value。
- 这些是测试 evidence boundary 的 accepted 区别——不是用户手册、Engine 设计文档或时间敏感记录。
- 没有扩写 README 的职责范围。
- Root README 不更新——用户可见 CLI grammar、交互、输出通道与排障入口不变。

**Re-verdict**：PASS。README 更新精确、克制，scope 正确。

### 6.15 scope / security / deferred boundary

| Scan | Result |
| --- | --- |
| production diff | 零 |
| S1/S2 diff | 零 |
| workflow diff | 零 |
| root README diff | 零 |
| plan/design/deferred Issue paths diff | 零 |
| `capture_output=True` in S3 smoke | 零命中 |
| `shell=True` / `errors=...replace` in S3 smoke | 零命中 |
| `communicate(` in S3 smoke | 零命中 |
| `mkstemp` / `NamedTemporaryFile` in S3 smoke | 零命中 |
| `CREATE_NEW_PROCESS_GROUP` / `JobObject` / `Start-Process` / `PowerShell` | 零命中 |
| deferred Issue / `web_tools_storage_states` | 零命中 |
| `git diff --check` | PASS |
| staged tree | empty |

**Re-verdict**：PASS。scope 精确，security 零命中，deferred boundary 未触碰。

### 6.16 Windows-specific Popen handle semantics

- `close_fds=True` 在 POSIX 上关闭所有非 stdin/stdout/stderr 的 fd——正确。
- `close_fds=True` 在 Windows 上不关闭继承的 handle——与 `Popen` 文档一致。当 `stdin/stdout/stderr` 显式传入 handle 时，Windows 上这些 handle 被继承到 child 进程。
- `text=False` 确保 binary mode——Windows 上不涉及 code page 转换。
- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes——这是 platform residual，不是 implementation finding。

**Re-verdict**：PASS（platform residual，不是 code finding）。

## 7. Observation 零回流确认

Controller adjudication 裁决的四项 observations 均按 Controller 裁决保持无 current action：

- DS OBS-01：frame clearing 是 `pytest.fail(..., pytrace=False)` 与 safe renderer 之外的 defense-in-depth。
- DS OBS-02：scripted process 的 output timing 不参与被断言的业务语义。
- DS OBS-03：renderer invariant error 只包含固定状态标签，不形成 sensitive-material projection。
- MiMo residual：CPython 若改变 `TimeoutExpired.__str__` 格式，raw-timeout owner probe 会 fail closed，不会让 safe renderer 泄漏值。

本 re-review 没有为这些 observation 增加 fallback、兼容 shim、额外 test double、pytest/JUnit workaround、process-tree 治理或 follow-up issue。Observation 回流计数为 `0`。

## 8. Finding summary

| # | Severity | Description | Owner | Status |
| --- | --- | --- | --- | --- |
| — | — | 无 material finding | — | — |

## 9. Ledger

| Category | Count |
| --- | --- |
| Accepted material finding | `0` |
| Rejected/not-a-finding | `0` |
| Needs evidence | `0` |
| Design contradiction | `0` |
| Local blocker | `0` |
| Unclassified residual | `0` |
| Observation backflow | `0` |
| Real Windows residual | `PENDING_RELEASE_BLOCKER`，由 Controller remote gate 负责 |

## 10. Residual risks

- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes；状态为 `PENDING_RELEASE_BLOCKER`，owner 是 S3 accepted commit 后的 Controller-owned R12 dispatch。
- standalone R11 不消费 canary，不进入 R12 canary scan。
- raw timeout probe 断言测试 CPython `TimeoutExpired.__str__` 当前行为——如果 CPython 改变格式，probe 断言可能失败但 safe renderer 仍然安全。
- full Ruff `142` 条与 edgartools `3` 类 warning 是既有 baseline，不是本 slice finding。

## 11. Completion

`PASS / MATERIAL_FINDING_0 / OBSERVATION_BACKFLOW_0 / NO_BLOCKER / READY_FOR_ACCEPTED_COMMIT`

Reviewer 从零完整审查 S3 payload diff、全部 11 个 artifact SHA-256、implementation artifact、controller validation、两路 initial review、controller adjudication、zero-change fix confirmation、controller zero-change validation。独立验证所有 SHA-256、测试结果（28 passed, 5 skipped）、pyright（0 errors）、Ruff（All checks passed）和 diff-check。所有 adversarial 维度均通过，无 material finding，observation 零回流。

Payload 字节未变化；production、S1/S2、workflow、root README、plan/design/deferred paths 零 diff。真实 Windows closure 保持 `PENDING_RELEASE_BLOCKER`，等待 S3 accepted commit 并 push 后 Controller remote gate。
