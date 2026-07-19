# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S3 Complete Code Review（AgentMiMo）

## 1. Review identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4`，同一 remediation continuation。
- Slice：`WIN4-S3 — Timeout-safe outer harness and final docs`。
- Gate：dual complete code review。
- Baseline HEAD：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`。
- Branch：`phaseflow/host-issues-control`。
- Immutable payload target：`tests/cli/test_init_smoke.py`、`tests/README.md`。
- Payload binary diff SHA-256：`8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4`。
- Test file SHA-256：`6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30`。
- Tests README SHA-256：`0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2`。
- AgentCodex implementation artifact SHA-256：`65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2`。
- Controller validation SHA-256：`d9bfcf308624fa1e219381c8fcade0d3015c92ac78fbe48927eabe4a3863f9c6`。

## 2. Verdict

`PASS / MATERIAL_FINDING_0`

## 3. Review scope

从零审查 `tests/cli/test_init_smoke.py`（+956/-41）和 `tests/README.md`（+7/-3）的完整 diff，以第一性原理逐项验证：
Popen[bytes] + anonymous handles contract、stdin flush/rewind/frame clearing、strict UTF-8 decode、timeout 四状态状态机、deadline poll 与 cleanup returncode 分离、cleanup timeout 恰好一次 poll 且无二次 wait/kill、failure path zero-read、pytest.fail(pytrace=False) 与 safe renderer、canary domain 31 bytes/single NUL/canonical ASCII/known vector、fail-closed/local random、test doubles 设计边界、README scope、security boundary、Windows-specific handle semantics。

## 4. Independent validation

Reviewer 在 `.venv` 下独立运行：

| Validation | Result |
| --- | --- |
| `pytest tests/cli/test_init_smoke.py -q` | `28 passed, 5 skipped, 3 warnings` |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff（changed files） | `All checks passed!` |
| `git diff --check` | PASS |
| Payload diff SHA-256 | `8bba3cd2...6c4` — exact match |
| Test file SHA-256 | `6748c609...ec30` — exact match |
| README SHA-256 | `0fa4165b...6aa2` — exact match |
| Canary domain verification | 31 bytes, single NUL, known vector `sk-dayu-test-b8f2210d...0b97` — exact match |

## 5. Adversarial dimension-by-dimension analysis

### 5.1 Popen[bytes] + three anonymous handles

**Contract**：`_run_init()` 在 context manager 内创建三个 `tempfile.TemporaryFile(mode="w+b")` anonymous binary handles，通过 `subprocess.Popen[bytes]` 显式传入 `stdin/stdout/stderr`，固定 `shell=False`、`close_fds=True`、`text=False`。不调用 `communicate()`，只使用 `wait(timeout=180)`。

**Review**：
- 三个 handles 确实是 `mode="w+b"` binary mode，与 `Popen[bytes]` 类型参数一致。
- `shell=False` + `close_fds=True` + `text=False` 是正确的跨平台安全组合。
- `stdin=stdin_handle` 把 anonymous handle 直接传给 Popen，child 进程通过继承的 fd 读取。
- context manager exit 保证三个 handles 在任何路径（success/timeout/exception）都被关闭。
- `communicate(` 零命中——没有使用 `subprocess.run(input=...)` 或 `Popen.communicate()`。

**Verdict**：PASS。anonymous binary handles + Popen[bytes] contract 正确，跨平台语义一致。

### 5.2 stdin flush/rewind/frame clearing

**Contract**：stdin 先 strict UTF-8 encode、write、flush、rewind；随后清空 `input_text` 和 `input_bytes` local variables，再启动 Popen。

**Review**：
- `input_text.encode("utf-8", errors="strict")` 在 Popen 前执行，非法 UTF-8 surrogate 在此失败。
- `stdin_handle.write(input_bytes)` + `flush()` + `seek(0)` 是正确的 anonymous handle 写入序列。
- `input_text = ""` 和 `input_bytes = b""` 在 Popen 调用前清空 helper frame 中的 input text/bytes 所有者。
- 清空发生在 `stdin_handle.write()` 之后、`Popen()` 之前——数据已在 handle 内，frame 中的变量被置空。
- 若 `Popen()` 本身抛出异常（如 `FileNotFoundError`），清空已执行，但 handle 内容仍可通过 context manager 访问——这是正确的，因为异常传播时需要 handle 存活。

**Verdict**：PASS。flush/rewind/frame clearing 时序正确，strict encode 在 Popen 前。

### 5.3 success strict decode

**Contract**：ordinary completion 后才 rewind/read stdout/stderr，并 strict UTF-8 decode。ordinary nonzero 仍返回 typed result，不重分类为 timeout。

**Review**：
- `stdout_handle.seek(0)` + `stdout_handle.read()` + `stdout_bytes.decode("utf-8", errors="strict")` 只在 `try` 块的 non-exception 路径执行。
- `UnicodeDecodeError` 在此处抛出，传播给调用方——test `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels` 验证了这一点。
- 该 test 同时验证 `stdout_handle.read_count == 1` 和 `stderr_handle.read_count == 1`——两个 channel 都被读取，不会因为第一个 channel 的 decode 失败而跳过第二个。
- `test_run_init_returns_ordinary_nonzero_as_typed_result` 验证 `returncode=7` 不被重分类为 timeout，stdout/stderr 正常解码。
- `_assert_init_result` 的 failure message 不包含 stdout/stderr 内容——只包含 expected/actual returncode。

**Verdict**：PASS。strict decode 覆盖两个 channel，nonzero 不重分类，failure projection 不回显 output。

### 5.4 timeout 四状态状态机

**Contract**：deadline 后先做一次 nonblocking `poll()`，锁定 `returncode_at_timeout`。deadline 时已退出：不 kill、不二次 wait，投影 completed cleanup。deadline 时仍运行：只 kill direct outer process，再做一次 `wait(timeout=180)`。cleanup wait 再次 timeout：恰好再做一次 nonblocking `poll()`，投影 `running` 或 `exited`；此后没有二次 wait/kill。

**Review**：四状态矩阵：

| State | deadline poll | kill | cleanup wait | post-cleanup poll | process_state |
| --- | --- | --- | --- | --- | --- |
| 已退出 | `returncode` (非 None) | 0 | 0 | 0 | N/A |
| 运行→cleanup 完成 | `None` | 1 | 1 (success) | 0 | N/A |
| 运行→cleanup timeout→running | `None` | 1 | 1 (timeout) | 1 → `None` | `"running"` |
| 运行→cleanup timeout→exited | `None` | 1 | 1 (timeout) | 1 → `returncode` | `"exited"` |

Code path：
1. `process.wait(timeout=180)` → `TimeoutExpired` caught.
2. `returncode_at_timeout = process.poll()` — 第一次 poll。
3. If `returncode_at_timeout is not None`：已退出，`cleanup="completed"`, `cleanup_returncode=returncode_at_timeout`，直接到 `pytest.fail()`。
4. If `returncode_at_timeout is None`：`process.kill()`，`cleanup_returncode = process.wait(timeout=180)`。
5. If cleanup wait 成功：`cleanup="completed"`，到 `pytest.fail()`。
6. If cleanup wait timeout：`cleanup="timeout"`，`cleanup_returncode = process.poll()` — 第二次 poll（也是最后一次）。
7. `process_state_after_cleanup_timeout = "running" if cleanup_returncode is None else "exited"`。

**Critical verification**：
- State 1（已退出）：0 kill, 0 cleanup wait, 0 post-cleanup poll ✓
- State 2（运行→cleanup 完成）：1 kill, 1 cleanup wait, 0 post-cleanup poll ✓
- State 3（运行→cleanup timeout→running）：1 kill, 1 cleanup wait (timeout), 1 post-cleanup poll → `None` ✓
- State 4（运行→cleanup timeout→exited）：1 kill, 1 cleanup wait (timeout), 1 post-cleanup poll → `returncode` ✓

每个状态的 `wait_calls`、`poll_calls`、`kill_calls` 精确匹配。cleanup timeout 后恰好一次 poll，此后无额外 wait/kill/process-tree 治理。

**Verdict**：PASS。四状态状态机完整且精确，无遗漏状态或多余操作。

### 5.5 deadline poll 与 cleanup returncode 不混淆

**Review**：
- `returncode_at_timeout` 来自 deadline 后的第一次 `poll()`——它记录 deadline 时刻的进程状态。
- `cleanup_returncode` 来自 `process.wait(timeout=180)` 成功时的 returncode，或 cleanup timeout 后的第二次 `poll()`。
- 当 deadline 时进程已退出（State 1），`returncode_at_timeout == cleanup_returncode`——两者是同一个 poll 结果，语义一致。
- 当 deadline 时进程运行但 cleanup 完成（State 2），`returncode_at_timeout = None`，`cleanup_returncode = wait()` 成功值——两者语义不同，正确分离。
- 当 deadline 时进程运行且 cleanup timeout（State 3/4），`returncode_at_timeout = None`，`cleanup_returncode` 来自第二次 poll——正确。

**Verdict**：PASS。deadline poll 与 cleanup returncode 语义清晰分离。

### 5.6 cleanup timeout 恰好一次额外 poll 且不再 wait/kill

**Review**：
- cleanup timeout 路径（line 648-651）：`cleanup = "timeout"`，`cleanup_returncode = process.poll()`，`process_state_after_cleanup_timeout = ...`。
- 此后直接到 `_render_init_timeout()` 和 `pytest.fail()`——没有额外的 `wait()`、`kill()`、`terminate()` 或 process-tree 操作。
- Test 验证 `process.poll_calls == 2`（deadline poll + post-cleanup poll）和 `process.kill_calls == 1`（仅一次 kill）。
- Test 验证 `process.wait_calls == [_PROCESS_TIMEOUT_SECONDS] * 2`（initial wait + cleanup wait）——恰好两次 wait。

**Verdict**：PASS。cleanup timeout 后恰好一次 poll，无二次 wait/kill。

### 5.7 failure path zero-read

**Contract**：failure path 不读取 stdout/stderr。

**Review**：
- `stdout_handle.seek(0)` / `stdout_handle.read()` / `stderr_handle.seek(0)` / `stderr_handle.read()` 只在 `try` 块的 non-exception 路径执行（line 660-665）。
- `except subprocess.TimeoutExpired` 路径直接到 `pytest.fail()`——不 seek/read stdout/stderr handles。
- Test 验证 `stdout_handle.read_count == 0` 和 `stderr_handle.read_count == 0`。

**Verdict**：PASS。failure path 确实不读取 stdout/stderr。

### 5.8 pytest.fail(pytrace=False) 与 safe renderer

**Contract**：通过 `pytest.fail(safe_message, pytrace=False)` 失败，不传播 raw `TimeoutExpired` frame/exception material。

**Review**：
- `pytrace=False` 阻止 pytest 在 failure 输出中包含 Python traceback——traceback 可能包含 local variable 值。
- `_render_init_timeout()` 只输出 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，以及 cleanup timeout 时的 `process_state_after_cleanup_timeout`。
- 不包含 argv、cwd、path、input、stdout、stderr、exception type 或 exception message。
- Test 的 `forbidden_material` 检查覆盖：sentinel、canary、sensitive_input、workspace_root、REPOSITORY_ROOT、"sensitive-cli-argv"、"stdin"、"stdout"、"stderr"、"TimeoutExpired"。
- Test 同时检查 `capsys.readouterr()` 的 stdout/stderr 不含 sentinel 或 canary——确认 pytest failure 本身不通过 capture 泄漏。
- Test 的 `str(raised.value)` 检查确认 safe message 不含 forbidden material。
- Test 的 `repr(raised.value)` 检查确认 repr 也不含 forbidden material。

**关于 raw timeout probe 的说明**：
Test 还验证 `str(raw_timeout)` 包含敏感材料——这测试的是 CPython `TimeoutExpired.__str__` 的当前行为，不是我们代码的安全性。这个 probe 的目的是确认 raw exception 确实"脏"（包含进程信息），从而证明我们需要 safe renderer。如果 CPython 改变 `__str__` 格式，probe 断言可能失败，但 safe renderer 仍然安全——这是可接受的 probe 策略。

**Verdict**：PASS。safe renderer 正确过滤所有 forbidden material，pytrace=False 阻止 traceback 泄漏。

### 5.9 canary domain 精确 31 bytes / single NUL

**Contract**：`_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`，精确 31 bytes，末字节为 single NUL。

**Review**：
- `_WINDOWS_CANARY_DOMAIN` 是模块级 `Final[bytes]` constant。
- `len(_WINDOWS_CANARY_DOMAIN) == 31` ✓
- `_WINDOWS_CANARY_DOMAIN[:-1] == "dayu-ar-f07-win4-r12-canary-v1".encode("ascii")` ✓
- `_WINDOWS_CANARY_DOMAIN[-1] == 0` ✓
- `_WINDOWS_CANARY_DOMAIN.count(bytes((0,))) == 1` — 只有一个 NUL ✓

**Verdict**：PASS。domain bytes 精确 31 bytes，single NUL。

### 5.10 canonical positive ASCII decimal

**Contract**：run id 通过 `str(int(raw))` canonicalize。

**Review**：
- `_github_actions_canary(raw_run_id)` 先检查 `raw_run_id.isascii()` 和 `raw_run_id.isdecimal()`。
- `int(raw_run_id)` 后检查 `run_id <= 0`。
- `canonical_run_id = str(run_id)` — `int("0001")` → `1` → `"1"` canonicalization。
- Test 验证 `_github_actions_canary("0001") == _github_actions_canary("1")` — canonicalization 正确。

**Verdict**：PASS。canonical decimal 正确处理 leading zeros。

### 5.11 known vector

**Contract**：run id `1` 的 accepted known vector 精确匹配。

**Review**：
- `hashlib.sha256(b"dayu-ar-f07-win4-r12-canary-v1\x00" + b"1").hexdigest() == "b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97"`
- `_github_actions_canary("1") == "sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97"`
- Test 精确匹配完整字符串。
- Test 还验证 `_github_actions_canary("2") != known_vector`、`startswith(_WINDOWS_CANARY_PREFIX)`、`len(digest) == 64`、`set(digest) <= set("0123456789abcdef")`。

**Verdict**：PASS。known vector 精确匹配，shape 正确。

### 5.12 workflow fail-closed / local random

**Contract**：`GITHUB_ACTIONS=true` 时只读取公开 `GITHUB_RUN_ID`；缺失、空、非 ASCII 十进制或非正值均在启动被测 CLI 前 fail closed，且不回退随机值。

**Review**：
- `_select_windows_test_canary()` 检查 `GITHUB_ACTIONS == "true"` 后，获取 `GITHUB_RUN_ID`。
- `raw_run_id is None` → `AssertionError("GITHUB_RUN_ID must be set in GitHub Actions")`。
- `_github_actions_canary()` 内部：`not isascii()` / `not isdecimal()` → `AssertionError`；`int(raw)` 后 `<= 0` → `AssertionError`。
- `_ForbiddenTokenFactory` 被 monkeypatch 到 `secrets.token_urlsafe`——任何调用都抛出 `AssertionError`。
- Test parametrizes 6 种 invalid 环境：missing、empty、non-decimal、zero、negative、full-width。
- 每种都验证 `forbidden_random.calls == 0`。
- 非 GitHub Actions 路径：`test_local_windows_canary_remains_random_and_ignores_run_id` 验证 `secrets.token_urlsafe(32)` 被调用两次，每次 32 bytes。
- 合法 workflow 路径：`test_github_actions_canary_uses_public_run_id_without_random_fallback` 验证 `forbidden_random.calls == 0`。

**Verdict**：PASS。fail-closed 完整，local random 正确，无 fallback。

### 5.13 real setx test 是否在 CLI 前选值且无辅助 needle

**Contract**：timeout negative test 每次使用新的随机 sentinel，并同时把 deterministic canary 放入 raw timeout command/output 探针；真实 setx test 断言选中值不进入 stdout/stderr。

**Review**：
- `test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 调用 `_select_windows_test_canary(os.environ)` 在 `_run_init()` 之前选值。
- 选中值作为 `sentinel` 传入 `_run_init()` 的 `input_text`。
- Test 断言 `sentinel not in result.stdout` 和 `sentinel not in result.stderr`。
- 没有新增 JUnit properties、辅助字段或 needle artifact。
- timeout test 的 canary 是 `_github_actions_canary("1")`——只用于 timeout 探针验证，不进入 setx test。

**Verdict**：PASS。setx test 在 CLI 前选值，无辅助 needle。

### 5.14 test doubles 是否过度设计/固化偶然行为

**Review**：

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

**关于固化偶然行为**：
- `_ScriptedInitProcess` 的 `wait_outcomes` / `poll_outcomes` 是 deterministic 状态机——测试的是 `_run_init()` 的代码路径，不是 CPython subprocess 的偶然行为。
- `_ScriptedInitPopenFactory` 验证 `stdin.tell() == 0`（rewind 正确）——这是 `_run_init()` 的 contract，不是偶然行为。
- handle 的 `flush_count` / `seek_calls` / `read_count` 验证 `_run_init()` 的显式操作——不是实现细节。

**Verdict**：PASS。test doubles 精确覆盖 contract 行为，未固化偶然行为。

### 5.15 README boundary

**Review**：
- `tests/README.md` diff 只增加两段：
  1. "产品 `setx` persistence 调用的 native output 没有消费者，因此不由产品捕获；real-init gate 的 outer CLI 仍通过 anonymous binary handles 捕获 stdout/stderr，并在 process 成功结束后 strict UTF-8 解码。"
  2. "outer CLI timeout 失败只投影 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，cleanup timeout 时再投影 `process_state_after_cleanup_timeout`；artifact 可记录环境变量名，但不记录 stdin input value。"
- 这些是测试 evidence boundary 的 accepted 区别——不是用户手册、Engine 设计文档或时间敏感记录。
- 没有扩写 README 的职责范围。
- Root README 不更新——用户可见 CLI grammar、交互、输出通道与排障入口不变。

**Verdict**：PASS。README 更新精确、克制，scope 正确。

### 5.16 scope / security / deferred boundary

**Review**：
- production diff：零。
- S1/S2 diff：零。
- workflow diff：零。
- root README diff：零。
- plan/design/deferred Issue paths diff：零。
- `capture_output=True` 在 `tests/cli/test_init_smoke.py`：零命中。
- `shell=True` / `errors=...replace` 在 S3 smoke：零命中。
- `communicate(` 在 S3 smoke：零命中。
- `mkstemp`、`NamedTemporaryFile`、`CREATE_NEW_PROCESS_GROUP`、`JobObject`、`Start-Process`、`PowerShell` 在 S3 smoke：零命中。
- deferred Issue / `web_tools_storage_states` 扫描：零命中。
- `git diff --check`：PASS。
- staged tree：empty。

**Verdict**：PASS。scope 精确，security 零命中，deferred boundary 未触碰。

### 5.17 Windows-specific Popen handle semantics 与真实 R12 residual

**Review**：
- `close_fds=True` 在 POSIX 上关闭所有非 stdin/stdout/stderr 的 fd——正确。
- `close_fds=True` 在 Windows 上不关闭继承的 handle——与 `Popen` 文档一致。当 `stdin/stdout/stderr` 显式传入 handle 时，Windows 上这些 handle 被继承到 child 进程。
- `text=False` 确保 binary mode——Windows 上不涉及 code page 转换。
- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes——这是 platform residual，不是 implementation finding。
- 真实 Windows R11/R12、dispatch-run lineage 与同一 R12 run 的 log/all-artifact canary scan 保持 `PENDING_RELEASE_BLOCKER`。

**Verdict**：PASS（platform residual，不是 code finding）。Windows handle semantics 正确，真实 Windows 验证由 Controller remote gate 负责。

## 6. Finding summary

| # | Severity | Description | Owner | Status |
| --- | --- | --- | --- | --- |
| — | — | 无 material finding | — | — |

## 7. Residual risks

- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes；状态为 `PENDING_RELEASE_BLOCKER`，owner 是 S3 accepted commit 后的 Controller-owned R12 dispatch。
- standalone R11 不消费 canary，不进入 R12 canary scan。
- raw timeout probe 断言测试 CPython `TimeoutExpired.__str__` 当前行为——如果 CPython 改变格式，probe 断言可能失败但 safe renderer 仍然安全。
- full Ruff `142` 条与 edgartools `3` 类 warning 是既有 baseline，不是本 slice finding。

## 8. Completion

`PASS / MATERIAL_FINDING_0 / READY_FOR_ACCEPTED_COMMIT_OR_FIX_ROUND`

Reviewer 从零完整审查 S3 payload diff、implementation artifact 与 controller validation，独立验证所有 SHA-256、测试结果、pyright、Ruff 和 diff-check。所有 adversarial 维度均通过，无 material finding。
