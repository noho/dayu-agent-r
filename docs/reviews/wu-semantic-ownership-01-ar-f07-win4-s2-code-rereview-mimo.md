# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S2 Code Re-Review — AgentMiMo

## Scope

- Mode：current changes（从零完整 re-review）
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；continuation：`AR-F07`；slice：`WIN4-S2`
- Branch：`phaseflow/host-issues-control`
- Entry commit / HEAD：`e34edfa39f244d736aeaf8b9ea82ff9152698b2b`（S1 accepted commit）
- Code/test binary diff SHA-256：`939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`
- Production file SHA-256：`ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`
- Test file SHA-256：`7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`
- Output file：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-rereview-mimo.md`
- Included scope：`dayu/cli/init_environment.py`（production owner）、`tests/cli/test_init_environment.py`（test owner）
- Excluded scope：Controller control doc、S1 post-commit artifact、WIN4 plan、README、workflow、Fins、Host/Engine
- Protected inputs：AGENTS.md、accepted WIN4 remediation plan、S2 implementation artifact（AgentCodex）、S2 Controller validation、S2 initial dual code review（MiMo + DS）、Controller adjudication、AgentCodex zero-change fix artifact、Controller zero-change fix validation

## Pre-review verification

| 检查项 | 结果 |
|---|---|
| HEAD commit | `e34edfa39f244d736aeaf8b9ea82ff9152698b2b` ✓ |
| Binary diff SHA-256 | `939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea` ✓ |
| Production file SHA-256 | `ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e` ✓ |
| Test file SHA-256 | `7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2` ✓ |
| Diff stat | `2 files changed, 174 insertions(+), 51 deletions(-)` ✓ |
| `git diff --check` | PASS ✓ |
| `git diff --cached --name-only` | 零输出；staged tree empty ✓ |
| `pytest tests/cli/test_init_environment.py -q` | `57 passed in 0.09s` ✓ |
| `pyright dayu/cli/init_environment.py tests/cli/test_init_environment.py` | `0 errors, 0 warnings, 0 informations` ✓ |
| Branch coverage（`dayu/cli/init_environment.py`） | `307 stmt / 84 branch` → combined `93%`（≥80%）✓ |

## Evidence chain SHA-256 锁定

| Artifact | SHA-256 | 本次复核 |
|---|---|---|
| S2 implementation（AgentCodex） | `1e2a8a418d2375dc5ab10d81cbcc1ecba225806ef9ee98d9b6fa2f920d02187c` | ✓ 一致 |
| S2 Controller validation | `2d50c80fb4812d23ffd525ddcd2798ea3bd67d1ee4879b202ebfa7f51d33c1de` | ✓ 一致 |
| S2 initial MiMo review | `dfe93b67b8e0537bcd2109e7a77a0be407bf11ac7df1f61c5edd3f371bff27ae` | ✓ 一致 |
| S2 initial DS review | `ff3a1ff5e2b3a245b5c43f94844fe47704f10b2d48ed0c035f8f717a177ac6a5` | ✓ 一致 |
| S2 Controller adjudication | `63e0a95cca52091bda36d3a60fdbecd916f7549aec08d7902357f959b3128f43` | ✓ 一致 |
| S2 zero-change fix（AgentCodex） | `e96d82bdd3c069f5ae0a4d705e57796e31b57d1713890c7f0d09fec76ef9da7b` | ✓ 一致 |
| S2 zero-change Controller validation | `2c57bbf88f240f81c04ddddce1daad9d3003cf0af6f7c967d94e04e9200bf8bc` | ✓ 一致 |

全部 artifact SHA-256 与实现、验证、两路 initial review、adjudication、zero-change fix 和 Controller validation 的锁定值完全一致。没有 baseline 漂移。

## Findings

**未发现实质性问题。Accepted finding 为 0。**

## 逐项完整 re-review

### 1. setx argv / DEVNULL / close_fds / timeout kwargs

**Production code**（`init_environment.py:417-427`）：

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

从零逐项确认：

- argv 为 tuple `("setx", entry.name, entry.value)`，`shell=False`，无 shell 注入面。✓
- `stdin/stdout/stderr` 全部 `subprocess.DEVNULL`：删除了 `capture_output=True`，无消费者 pipe 不再存在，消除 R12 root cause（outer CLI process 返回 1 后 stdout reader 等待 inherited pipe EOF）。✓
- `close_fds=True`：禁止继承非 stdio handle。CPython 3.11 官方文档明确记录：自 Python 3.7 起，Windows 上 `close_fds=True` 可与重定向标准句柄共存（"Changed in version 3.7: On Windows the default for close_fds was changed from False to True when redirecting the standard handles. It's now possible to set close_fds to True when redirecting the standard handles."）。项目 `requires-python = ">=3.11"` 完全覆盖此能力。✓
- `text=False`：binary mode，与无消费者 DEVNULL 一致，无 decode error 风险。✓
- `check=False`：手动检查 `returncode`，不依赖 subprocess 自动抛错。✓
- `timeout=30.0`：单次 setx owner bound（`_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float]`），不是 outer 180 秒 budget 的替代。✓
- `capture_output` 零命中：production code 中不存在此参数。✓

**Recorder 签名**（`test_init_environment.py:77-89`）：精确匹配 production kwargs（`args, shell, stdin, stdout, stderr, close_fds, text, check, timeout`），keyword-only。任何多余或缺失 kwargs 都会导致 recorder 签名不匹配测试 TypeError。✓

**Expected call helper**（`test_init_environment.py:131-149`）：`_expected_setx_call()` 构造完整 `_SetxCall` frozen dataclass，与 `_SetxRecorder` 记录的每次调用做精确相等断言。✓

### 2. TimeoutExpired exception identity / non-disclosure / no retry

**Production code**（`init_environment.py:437-438`）：

```python
except subprocess.TimeoutExpired:
    return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
```

从零确认：

- 精确捕获 `subprocess.TimeoutExpired`（非父类 `SubprocessError`）。✓
- 异常**未绑定到变量**（无 `as`），raw cmd/output/stderr 不可访问。✓
- **不格式化、不记录、不转抛** raw exception（`TimeoutExpired.args` 含完整 `("setx", name, value)` argv）。✓
- 与 `OSError` 收口路径完全对称：均返回当前 index 的 names-only failure/partial-failure。✓
- **无 retry**：timeout 后 `setx` 是否已产生 durable side effect 不明，重试会扩大不确定写入。✓
- 无 `from` clause：不保留 exception chain。✓

**Test**（`test_init_environment.py:1186-1228`）：`_SetxRecorder` 在 `timeout_at=1` 索引抛出 `subprocess.TimeoutExpired(cmd=args, timeout=timeout)`，其中 `args` 含完整 raw argv/value。测试断言：

- `entry.value not in result_repr`：值不出现在 typed result。✓
- `entry.value not in captured.out / captured.err`：值不出现在 stdout/stderr。✓
- `raw_argv_repr not in result_repr / captured.out / captured.err`：raw argv tuple repr 也不出现。✓
- `recorder.calls == [_expected_setx_call(entries[0]), _expected_setx_call(entries[1])]`：精确调用前缀。✓
- `environment_visible_during_calls == [False, False]`：未提前注入。✓

### 3. returncode / OSError / KeyboardInterrupt names truth

**Production code**（`init_environment.py:414-450`）：

- `KeyboardInterrupt` → `EnvironmentPersistenceInterrupted`（typed exception，携带 `written_names` + `unwritten_names`，`from None`）。✓
- `TimeoutExpired` → `_windows_failure_result()`（names-only failure/partial-failure）。✓
- `OSError` → `_windows_failure_result()`（同上）。✓
- `returncode != 0` → `_windows_failure_result()`（同上）。✓
- 全部成功 → `EnvironmentPersistenceResult(status=SUCCESS)`。✓

**Test coverage**（从零确认每个 exception branch 与 index 组合）：

| 测试 | 异常类型 | index | 断言 |
|---|---|---|---|
| `test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success` | — | — | SUCCESS、全量 written_names、空 unwritten_names、环境注入 ✓ |
| `test_windows_nonzero_reports_names_only_without_retry_or_injection`（`failure_at ∈ {0, 1}`） | returncode | first / middle | FAILURE / PARTIAL_FAILURE、精确 written/unwritten、no retry、no injection ✓ |
| `test_windows_os_error_reports_partial_names_without_retry_or_injection` | OSError | middle（index=1） | PARTIAL_FAILURE、精确 written/unwritten、no retry、no injection ✓ |
| `test_windows_timeout_hides_raw_argv_without_retry_or_injection` | TimeoutExpired | middle（index=1） | PARTIAL_FAILURE、精确 written/unwritten、no retry、no injection、value/argv non-disclosure ✓ |
| `test_windows_interrupt_reports_written_and_unwritten_names_without_values`（`interrupt_at ∈ {0, 1, 2}`） | KeyboardInterrupt | first / middle / last | INTERRUPTED、精确 written/unwritten、no injection、value non-disclosure ✓ |
| `test_windows_environment_injection_interrupt_keeps_completed_store_truth` | KeyboardInterrupt（env injection） | — | INTERRUPTED、全部 written_names、空 unwritten_names、no injection ✓ |

关键观察：`OSError` 与 `TimeoutExpired` 各自在 middle-index 被直接执行，覆盖了精确 exception branch。first-index 的 `FAILURE`、空 `written_names`、全量 `unwritten_names` 状态转换已由 nonzero-returncode `failure_at=0` 测试直接执行。三类 native failure 共享同一个 `_windows_failure_result()` 纯函数，`exception kind × index` 没有独立生产分支或额外业务语义。✓

### 4. whole-batch injection 时序

**Production code**（`init_environment.py:443-450`）：`written_names.append(entry.name)` 在 `returncode` 检查通过后执行；`os.environ` 注入只在循环完成后、返回 `SUCCESS` result 前发生（由 `persist_environment` 上游函数执行）。任何单项失败都立即 `_windows_failure_result()` return，不注入。✓

**Test**：

- success test 断言 `os.environ[first.name] == first.value` 且 `os.environ[second.name] == second.value`。✓
- failure test 断言 `all(entry.name not in os.environ for entry in entries)`。✓
- `environment_visible_during_calls` 记录每次调用时环境是否已注入，failure 路径全部为 `[False, ...]`。✓

### 5. strict recorder 覆盖

`_SetxRecorder.__call__` 签名包含 production `subprocess.run` 的全部 kwargs（`args, shell, stdin, stdout, stderr, close_fds, text, check, timeout`），keyword-only。若 production 新增/删除 kwargs，recorder 签名不匹配会直接导致测试 `TypeError`。✓

`_SetxCall` frozen dataclass 逐字段记录完整 native process contract，test helper `_expected_setx_call()` 构造 owner contract 的精确预期。两者做 `==` 比较。✓

### 6. semantic owner

WIN4-S2 的唯一 semantic owner 是 `_persist_windows_environment()`：它负责 `setx` executable/argv、stdio/handle inheritance、单次 timeout 以及 native outcome 到 names-only result 的投影。✓

- `WindowsEnvironmentPersistencePlan`（typed dataclass）为合约输入，`EnvironmentPersistenceResult`（typed dataclass）为合约输出。✓
- 未在下游 consumer、adapter、展示层或 fixture 中以 fallback/特例/重算/loose parsing 补偿缺失语义。✓
- `_WINDOWS_SETX_TIMEOUT_SECONDS` 为 owner-bound 模块常量，非分散魔法值。✓
- 未新增 `hasattr`/`getattr`/兼容 shim/兼容 re-export。✓
- Registry round-trip/cleanup 仍属于真实 Windows smoke 验证 owner（S3）；本 slice 不替换 registry authority。✓

### 7. overdesign 检查

实现为最小化修复：

- 新增 1 行模块级常量 `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0`。
- 修改 1 处 `subprocess.run` 调用：删除 `capture_output`，新增 `stdin/stdout/stderr=DEVNULL`、`close_fds=True`、`timeout`。
- 新增 2 行 `except subprocess.TimeoutExpired`。
- 无 process tree kill、Win32 handle enumeration、job object、registry fallback、PowerShell、outer timeout、shell、日志、retry 或兼容分支。✓
- `_SetxCall` dataclass 与 `_expected_setx_call` helper 仅在测试中使用，属于 test infrastructure，非生产 overdesign。✓

### 8. CPython 官方文档证据验证

Controller adjudication 引用的 CPython 官方文档证据已独立验证：

- [Python 3.11 `subprocess.Popen` 官方文档](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen)的 `close_fds` 条目明确记录："Changed in version 3.7: On Windows the default for close_fds was changed from False to True when redirecting the standard handles. It's now possible to set close_fds to True when redirecting the standard handles."
- `requires-python = ">=3.11"` 完全覆盖 Python 3.7+ 的此能力，不存在 DS S2-CR-F01 声称的 patch-version contract 缺口。

Controller 对 DS S2-CR-F01 的 `REJECTED / FACTUALLY CONTRADICTED` 裁决正确。✓

### 9. 异常分支 / first-index / shared helper 覆盖验证

Controller 对 DS S2-CR-F02 的 `REJECTED / REDUNDANT CARTESIAN TEST MATRIX` 裁决已独立验证：

- `OSError` 的精确 exception branch 已由 `test_windows_os_error_reports_partial_names_without_retry_or_injection`（`os_error_at=1`）直接执行。✓
- `TimeoutExpired` 的精确 exception branch 已由 `test_windows_timeout_hides_raw_argv_without_retry_or_injection`（`timeout_at=1`）直接执行。✓
- first-index 的 `FAILURE`、空 `written_names`、全量 `unwritten_names` 状态转换已由 `test_windows_nonzero_reports_names_only_without_retry_or_injection`（`failure_at=0`）直接执行。✓
- 三类 native failure 共享唯一 `_windows_failure_result()` 纯函数，exception type 与 index 的组合没有独立生产分支或额外业务语义。✓
- branch coverage 93%，高于 ≥80% 目标。✓

增加 `exception kind × first/middle index` 的笛卡尔积只重复同一 helper contract，不关闭新业务风险。裁决正确。✓

### 10. scope / security / deferred boundary

- Added-lines 零命中 `shell=True`、`errors=replace`、PowerShell、`winreg`/`reg.exe`、process group/job object、deferred Issue 142/151/175/177/178 或兼容分支。✓
- 未读取、请求、导出或扫描 GitHub Secrets / configured production values。✓
- `TimeoutExpired` raw argv/value 未进入 typed result、stdout/stderr capture、artifact 或日志。✓
- README 不更新：public init grammar、用户工作流和输出通道未变；`tests/README.md` 的 setx/outer-harness 统一说明放在 S3。✓
- S3 outer harness safe timeout projection、canary 与 README 仍为后续 approved slice，未提前实施。✓
- `tests/cli/test_init_smoke.py` 的既有 `reg.exe` 说明/调用 7 处未被 S2 diff 新增、修改或删除。✓

### 11. Windows 真实 residual 分类

- `REAL_WINDOWS_PENDING`：DEVNULL/close-fds/native timeout 的真实 R12 round-trip 与 R11/R12 clean closure 仍须三 slices accepted 后由 Controller 按 plan §8/§9.3 执行。分类：`covered by later approved slice / Controller-owned remote closure`。✓
- `WIN4-S3_PENDING`：outer harness safe timeout projection、run-id canary 与 `tests/README.md` 仍未实现。分类：`covered by later approved slice WIN4-S3`。✓
- Aggregate native scan 的既有 `reg.exe` 命中属于 S3 real registry smoke，不是 S2 新增 finding。分类：`covered by later approved slice WIN4-S3`。✓
- 不存在未分类 residual risk、blocking open question 或 S2 owner 外修复需要。✓

### 12. rejected candidates 回流检查

从零独立验证两项 rejected candidate 均未通过代码、测试、文档或 follow-up 语义回流：

- **DS S2-CR-F01**（Python 3.11.0–3.11.3 `close_fds` + `DEVNULL` ValueError）：`pyproject.toml` 未修改，`requires-python` 仍为 `>=3.11`，README 未新增错误版本风险说明，production 未添加兼容分支或版本检测。✓ 未回流。
- **DS S2-CR-F02**（`OSError` / `TimeoutExpired` first-index 缺少显式测试）：未增加 `@pytest.mark.parametrize` 变体、新 fixture 或笛卡尔积测试。✓ 未回流。

## Open Questions

无。

## Residual Risk

| Risk | 分类 | 责任方 |
|---|---|---|
| 真实 Windows DEVNULL/close_fds/timeout round-trip behavior（R12） | `covered by later approved slice` | Controller S3 |
| S3 outer harness、canary、README | `covered by later approved slice WIN4-S3` | Controller S3 |
| Deferred issues（142/151/175/177/178） | `covered by approved later slices` | Controller / Owner |

## Final Ledger

| 项目 | 值 |
|---|---|
| Accepted code finding | `0` |
| Rejected reviewer candidate（from initial review） | `2`（均未回流） |
| Needs-evidence finding | `0` |
| Design contradiction | `0` |
| Local blocker | `0` |
| Current-slice production/test/README/workflow fix | `0` |
| Real Windows residual | `1`（`PENDING_RELEASE_BLOCKER`，Controller-owned remote closure） |

## Verdict

`PASS / MATERIAL FINDING 0 / READY_FOR_ACCEPTED COMMIT / REAL_WINDOWS_PENDING`

经过从零完整 re-review 与全 evidence chain SHA-256 锁定验证，S2 implementation 在本地环境中完全正确：

- setx argv / DEVNULL / close_fds / timeout / text=False / check=False / shell=False 全部显式且安全。✓
- TimeoutExpired 精确捕获、不绑定、不披露、不转抛、不重试。✓
- returncode / OSError / KeyboardInterrupt 的 names truth 在所有路径一致。✓
- whole-batch injection 时序正确——只在全部成功后注入 `os.environ`。✓
- strict recorder contract 确保 subprocess 接口回归可被 test 立即检测。✓
- semantic owner 单一明确，无 ownership drift 或 downstream compensation。✓
- 无 overdesign、无安全泄漏、无 deferred scope 越界。✓
- CPython 官方文档证据确认 `close_fds=True` + redirected stdio 自 Python 3.7 起在 Windows 上支持。✓
- 两项 rejected candidate 均未回流。✓
- accepted finding 为 0，material finding 为 0。✓

真实 Windows DEVNULL/handle/timeout 行为仍须后续 Controller-owned R12 远端验证；本地结果不是 waiver。

下一 gate 条件：S2 accepted local commit。
