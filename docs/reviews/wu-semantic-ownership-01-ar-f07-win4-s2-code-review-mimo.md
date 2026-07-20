# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `e34edfa39f244d736aeaf8b9ea82ff9152698b2b`（S1 accepted commit）
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-review-mimo.md`
- Included scope:
  - `dayu/cli/init_environment.py`：WIN4-S2 production owner change（setx native stdio/timeout）
  - `tests/cli/test_init_environment.py`：WIN4-S2 owner contract tests
- Excluded scope：Controller control doc、S1 post-commit artifact、WIN4 plan、README、workflow、Fins、Host/Engine
- Parallel review coverage：无

## Target verification

- Entry commit：`e34edfa39f244d736aeaf8b9ea82ff9152698b2b`
- Code/test binary diff SHA-256：`939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea` ✓
- 57 owner tests passed ✓
- pyright zero diagnostics ✓

## Findings

未发现实质性问题。

## Review detail

### 1. setx argv / DEVNULL / close_fds / timeout kwargs

**Production code** (`init_environment.py:417-427`)：

```python
completed = subprocess.run(
    ("setx", entry.name, entry.value),
    shell=False,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    close_fds=True,
    text=False,
    check=False,
    timeout=_WINDOWS_SETX_TIMEOUT_SECONDS,
)
```

逐项确认：

- argv 为 tuple `("setx", entry.name, entry.value)`，`shell=False`，无 shell 注入面。
- `stdin/stdout/stderr` 全部 `subprocess.DEVNULL`：删除了 `capture_output=True`，无消费者 pipe 不再存在。
- `close_fds=True`：禁止继承非 stdio handle。在 Windows + 显式 stdio handles 场景下，子进程只继承三个 DEVNULL handle，其余描述符关闭。
- `text=False`：binary mode，与无消费者 DEVNULL 一致。
- `check=False`：手动检查 `returncode`。
- `timeout=30.0`：单次 setx owner bound，不是 outer 180 秒 budget 的替代。
- `capture_output` 零命中：production code 和 test recorder 均不存在此参数。

**Recorder 签名**（`test_init_environment.py:77-89`）：精确匹配 production kwargs（`args, shell, stdin, stdout, stderr, close_fds, text, check, timeout`）。任何多余或缺失 kwargs 都会导致 recorder 签名不匹配测试失败。

**Expected call helper**（`test_init_environment.py:131-149`）：`_expected_setx_call()` 构造完整 `_SetxCall` dataclass，与 `_SetxRecorder` 记录的每次调用做精确相等断言。

### 2. TimeoutExpired exception identity / non-disclosure / no retry

**Production code**（`init_environment.py:437-438`）：

```python
except subprocess.TimeoutExpired:
    return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
```

确认：

- 精确捕获 `subprocess.TimeoutExpired`，不绑定 exception 实例。
- 不格式化、不记录、不转抛 raw exception（`TimeoutExpired.args` 含完整 `("setx", name, value)` argv）。
- 与 `OSError` 收口路径完全对称：均返回当前 index 的 names-only failure/partial-failure。
- 无 retry：timeout 后 `setx` 是否已产生 durable side effect 不明，重试会扩大不确定写入。
- 无 `from` clause：不保留 exception chain。

**Test**（`test_init_environment.py:1208`）：`_SetxRecorder` 在 `timeout_at` 索引抛出 `subprocess.TimeoutExpired(cmd=args, timeout=timeout)`，其中 `args` 含完整 raw argv/value。测试断言：
- `entry.value not in result_repr`：值不出现在 typed result。
- `entry.value not in captured.out / captured.err`：值不出现在 stdout/stderr。
- `raw_argv_repr not in result_repr / captured.out / captured.err`：raw argv tuple repr 也不出现。

### 3. returncode / OSError / KeyboardInterrupt names truth

**Production code**（`init_environment.py:414-443`）：

- `KeyboardInterrupt` → `EnvironmentPersistenceInterrupted`（typed exception，携带 `written_names` + `unwritten_names`，`from None`）。
- `TimeoutExpired` → `_windows_failure_result()`（names-only failure/partial-failure）。
- `OSError` → `_windows_failure_result()`（同上）。
- `returncode != 0` → `_windows_failure_result()`（同上）。
- 全部成功 → `EnvironmentPersistenceStatus.SUCCESS`。

状态名 `_WINDOWS_SETX_TARGET = "setx"` 与 `_WINDOWS_SETX_TIMEOUT_SECONDS = 30.0` 均为 `Final` 模块级常量，无魔法值。

**Test coverage**：
- success：`test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success`
- first/middle nonzero：`test_windows_nonzero_reports_names_only_without_retry_or_injection`（parametrized `failure_at ∈ {0, 1}`）
- middle OSError：`test_windows_os_error_reports_partial_names_without_retry_or_injection`
- middle TimeoutExpired：`test_windows_timeout_hides_raw_argv_without_retry_or_injection`
- first/middle/last KeyboardInterrupt：`test_windows_interrupt_reports_written_and_unwritten_names_without_values`（parametrized `interrupt_at ∈ {0, 1, 2}`）
- environment-injection interrupt：`test_windows_environment_injection_interrupt_keeps_completed_store_truth`

每个 failure/interrupt case 均断言精确调用前缀（`recorder.calls == [_expected_setx_call(...) for ...]`）、environment 可见性、no injection、no retry、value non-disclosure。

### 4. whole-batch injection 时序

**Production code**（`init_environment.py:443-450`）：`written_names.append(entry.name)` 在 `returncode` 检查通过后执行；`os.environ` 注入只在循环完成后、返回 `SUCCESS` result 前发生（由 `persist_environment` 上游函数执行）。任何单项失败都立即 `_windows_failure_result()` return，不注入。

**Test**：success test 断言 `os.environ[first.name] == first.value` 且 `os.environ[second.name] == second.value`；failure test 断言 `all(entry.name not in os.environ for entry in entries)`。`environment_visible_during_calls` 记录每次调用时环境是否已注入，failure 路径全部为 `[False, ...]`。

### 5. strict recorder 覆盖

`_SetxRecorder.__call__` 签名包含 production `subprocess.run` 的全部 kwargs（`args, shell, stdin, stdout, stderr, close_fds, text, check, timeout`）。若 production 新增/删除 kwargs，recorder 签名不匹配会直接导致测试 `TypeError`。

`_SetxCall` dataclass 逐字段记录完整 native process contract，test helper `_expected_setx_call()` 构造 owner contract 的精确预期。两者做 `==` 比较。

### 6. semantic owner

WIN4-S2 的唯一 semantic owner 是 `_persist_windows_environment()`：它负责 `setx` executable/argv、stdio、handle inheritance、单次 timeout 以及 native outcome 到 names-only result 的投影。

- Registry round-trip/cleanup 仍属于真实 Windows smoke 验证 owner（S3）。
- `TimeoutExpired` 的 non-disclosure 是该 owner 的自然行为：catch → discard → project names-only。
- `_windows_failure_result()` 是纯 names-only result 投影 helper，不含回滚声称。

### 7. overdesign 检查

实现为最小化修复：
- 新增 1 行模块级常量。
- 修改 1 处 `subprocess.run` 调用：删除 `capture_output`，新增 `stdin/stdout/stderr=DEVNULL`、`close_fds=True`、`timeout`。
- 新增 2 行 `except subprocess.TimeoutExpired`。
- 无 process tree kill、Win32 handle enumeration、job object、registry fallback、PowerShell、outer timeout、shell、日志、retry 或兼容分支。

### 8. Windows 跨平台可用性

- `close_fds=True` + 显式 `stdin/stdout/stderr=DEVNULL`：在 Windows 上，Python 子进程模块在 `close_fds=True` 时只继承显式传入的 stdio handle。`setx.exe` 是简单注册表写入工具，不需要 console 或继承 handle。
- `shell=False` + tuple argv：Windows 上不经过 `cmd.exe`，避免 CRT quote/batch 转义问题。
- `text=False` + DEVNULL：无输出解码，无 charmap/cp1252 风险。
- `timeout=30.0`：`subprocess.run` 在 Windows 上使用 `WaitForSingleObject` 实现 timeout，kill 使用 `TerminateProcess`。

### 9. 安全 / deferred / README 边界

- Added-lines 无 `shell=True`、`errors=replace`、PowerShell、winreg、reg.exe、process group/job object、deferred Issue 142/151/175/177/178 或兼容分支。
- 未读取、请求、导出或扫描 GitHub Secrets / configured production values。
- `TimeoutExpired` raw argv/value 未进入 typed result、stdout/stderr capture、artifact 或日志。
- README 不更新：public init grammar、用户工作流和输出通道未变；`tests/README.md` 的 setx/outer-harness 统一说明放在 S3。
- S3 outer harness safe timeout projection、canary 与 README 仍为后续 approved slice，未提前实施。

### 10. Tests 质量

- 57 tests passed，覆盖 POSIX 和 Windows 全路径。
- branch coverage 93%（`dayu/cli/init_environment.py`），高于 ≥80% 目标。
- Windows tests 使用严格 `_SetxRecorder` + `_SetxCall` dataclass + `_expected_setx_call()` helper，不依赖 mock 或 loose assertion。
- parametrized failure/interrupt tests 覆盖 first/middle/last 索引。
- `TimeoutExpired` test 特别断言 raw argv repr non-disclosure。
- `environment_visible_during_calls` 断言每次调用时环境注入状态。

## Open Questions

无。

## Residual Risk

- `REAL_WINDOWS_PENDING`：DEVNULL/close-fds/native timeout 的真实 R12 round-trip 与 R11/R12 clean closure 仍须三 slices accepted 后由 Controller 按 plan §8/§9.3 执行。本地 pyright/test pass 不是 Windows waiver。
- `WIN4-S3_PENDING`：outer harness safe timeout projection、run-id canary 与 `tests/README.md` 仍未实现。
- aggregate native scan 的既有 `reg.exe` 命中属于 S3 real registry smoke，不是 S2 新增 finding。

## Verdict

`PASS / MATERIAL FINDING 0 / READY_FOR_ACCEPTED COMMIT / REAL_WINDOWS_PENDING`

实现精确匹配 accepted plan WIN4-S2 的全部 5 项 exact changes 和 WIN4-F02 negative cases。Production 变更为最小化 setx native process contract 修复，tests 为严格 owner contract 覆盖。无 material finding、无 open question、无 blocker。真实 Windows DEVNULL/handle/timeout 行为仍须后续 Controller-owned R12 远端验证。
