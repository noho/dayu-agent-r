# Code Re-Review

## Gate identity

- **Gate**: WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S2 dual complete code re-review（AgentDS）
- **Not**: 新 WU、新 task、S3 implementation、accepted commit、push、workflow dispatch
- **Entry commit (HEAD)**: `e34edfa39f244d736aeaf8b9ea82ff9152698b2b`
- **Immutable production/test binary diff SHA-256**: `939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`
- **Production file SHA-256**: `ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`
- **Test file SHA-256**: `7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`
- **Controller adjudication SHA-256**: `63e0a95cca52091bda36d3a60fdbecd916f7549aec08d7902357f959b3128f43`
- **Zero-change artifact SHA-256**: `e96d82bdd3c069f5ae0a4d705e57796e31b57d1713890c7f0d09fec76ef9da7b`
- **Controller validation SHA-256**: `2c57bbf88f240f81c04ddddce1daad9d3003cf0af6f7c967d94e04e9200bf8bc`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-rereview-ds.md`

## Scope

- **Included**: `dayu/cli/init_environment.py`（production owner）、`tests/cli/test_init_environment.py`（test owner）的完整逐行 re-review
- **Excluded**: S1 production/test、S3、README、workflow、Host/Engine、Fins、deferred Issue paths、Controller control doc
- **Protected inputs**: AGENTS.md、accepted WIN4 remediation plan、S2 implementation artifact（AgentCodex）、S2 initial Controller validation、AgentMiMo initial review、AgentDS initial review、Controller adjudication、AgentCodex zero-change fix artifact、Controller zero-change validation

## Pre-review verification（独立重算）

| Check | Result |
|---|---|
| HEAD commit | `e34edfa39f244d736aeaf8b9ea82ff9152698b2b` ✓ |
| Binary diff SHA-256 | `939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea` ✓ |
| Production file SHA-256 | `ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e` ✓ |
| Test file SHA-256 | `7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2` ✓ |
| Adjudication SHA-256 | `63e0a95cca52091bda36d3a60fdbecd916f7549aec08d7902357f959b3128f43` ✓ |
| Zero-change artifact SHA-256 | `e96d82bdd3c069f5ae0a4d705e57796e31b57d1713890c7f0d09fec76ef9da7b` ✓ |
| Controller validation SHA-256 | `2c57bbf88f240f81c04ddddce1daad9d3003cf0af6f7c967d94e04e9200bf8bc` ✓ |
| `git diff --check` | PASS ✓ |
| `git diff --cached --name-only` | 零输出（staged tree empty）✓ |
| Diff stat | `2 files changed, 174 insertions(+), 51 deletions(-)` ✓ |
| `pytest tests/cli/test_init_environment.py -q` | **57 passed** ✓ |
| Branch coverage (`dayu/cli/init_environment.py`) | **93%**（307 stmt / 84 branch）✓ |
| `_persist_windows_environment()` 函数级 branch coverage | **100%**（missing lines 均为 POSIX 路径）✓ |
| pyright（scoped） | **0 errors, 0 warnings, 0 informations** ✓ |
| scoped Ruff | **All checks passed!** ✓ |
| `capture_output` grep（production） | 零命中 ✓ |
| `hasattr`/`getattr` grep（production） | 零命中 ✓ |
| `shell=True` grep（production） | 零命中 ✓ |
| `Any` type grep（两个 changed files） | 零命中 ✓ |
| `requires-python` 未修改 | 仍为 `>=3.11`（F01 未回流）✓ |

## 已驳回 candidate 的独立复核

### DS S2-CR-F01：`close_fds=True` + `DEVNULL` 在 Windows Python 3.11.0–3.11.3 触发 `ValueError`

**Controller 裁决**: REJECTED / FACTUALLY CONTRADICTED

**本轮独立复核结果**: **确认驳回，理由充分且不可辩驳。**

独立验证链：

1. **CPython 3.11 官方文档**（[`subprocess.Popen`](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen)）明确记录：
   > Changed in version 3.7: On Windows the default for *close_fds* was changed from `False` to `True` when redirecting the standard handles. It's now possible to set *close_fds* to `True` when redirecting the standard handles.

2. **[Python 3.7 What's New](https://docs.python.org/3/whatsnew/3.7.html#subprocess)** 记录同一变更：
   > On Windows the default for *close_fds* was changed from `False` to `True` when redirecting the standard handles. It's now possible to set *close_fds* to true when redirecting the standard handles.

3. **CPython 3.11.0 源码**（`Lib/subprocess.py`，GitHub raw）直接检查：Windows `_execute_child` 中**不存在**候选声称的 `ValueError("close_fds is not supported on Windows if you redirect stdin/stdout/stderr")` 检查。Windows 路径通过 `handle_list` 机制（`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`）正确处理 `close_fds=True` + 显式 stdio handle，该机制自 Python 3.7 起已完整实现。

4. **候选引用的 gh-91150 与 subprocess 无关**：该 issue 实际主题是 `asyncio.create_task()` 接受 `contextvars.Context` 参数，属于 asyncio 模块，与 `subprocess` 或 `close_fds` 完全无关。候选引用的 issue 编号为误引。

5. **当前实现使用 Python 3.11.15**（本地 `.venv`），已远高于 3.11.4。即使存在候选声称的边界（实际不存在），当前运行环境也不受影响。

**结论**：候选的前提事实不成立。CPython 官方文档为真源，源码直接证实无此 ValueError 检查。Controller 裁决正确，不得修改 `pyproject.toml`、README 或 production code。

### DS S2-CR-F02：`OSError` 与 `TimeoutExpired` 首位置（index=0）缺少显式测试

**Controller 裁决**: REJECTED / REDUNDANT CARTESIAN TEST MATRIX

**本轮独立复核结果**: **确认驳回，理由充分。**

独立验证链：

1. **生产代码分析**（`init_environment.py:437-442`）：
   ```python
   except subprocess.TimeoutExpired:
       return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
   except OSError:
       return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
   if completed.returncode != 0:
       return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
   ```
   三条 native failure 路径（`TimeoutExpired`、`OSError`、`nonzero returncode`）在 index=0 调用的是**完全相同的** `_windows_failure_result(plan=plan, written_names=(), failed_index=0)`。不存在按 exception type 分派的独立生产分支、独立状态转换或独立业务语义。

2. **已有测试覆盖**：
   - first-index `FAILURE`、空 `written_names`、全量 `unwritten_names` 状态转换已由 `test_windows_nonzero_reports_names_only_without_retry_or_injection` 的 `failure_at=0` 参数化变体直接执行（L1103-1148）。
   - `OSError` 的精确 exception branch 已由 `test_windows_os_error_reports_partial_names_without_retry_or_injection`（`os_error_at=1`）直接执行。
   - `TimeoutExpired` 的精确 exception branch 已由 `test_windows_timeout_hides_raw_argv_without_retry_or_injection`（`timeout_at=1`）直接执行，且额外验证 raw argv/value non-disclosure。

3. **增加 `exception kind × first index` 笛卡尔积测试的实质**：仅重复测试 Python runtime exception dispatch 机制，不关闭任何新的业务风险。`exception kind` 与 `index` 的组合不产生新的 `_windows_failure_result` 调用参数或新的 production branch。

**结论**：候选不构成 material finding。三类 failure 已在 owner boundary 被分别见证；first-index state transition 已被 nonzero-returncode 覆盖。Controller 裁决正确，不得增加重复测试。

## 完整逐行 re-review

### 1. Production code（`dayu/cli/init_environment.py`）

#### 1.1 模块级常量（L28）

```python
_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0
```

- 语义 owner 单一明确：`_persist_windows_environment()` 的单次 `setx` 执行上限。
- `Final[float]` 类型正确，防止运行时覆写。
- 30.0 秒对本地注册表写入命令是合理的 owner bound。
- 不是 outer 180 秒 smoke budget 的替代品——accepted plan §2.2 明确区分两者。 ✓

#### 1.2 `subprocess.run` 调用（L417-427）

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

逐参数验证：

| 参数 | 值 | 验证 |
|---|---|---|
| `args` | `("setx", entry.name, entry.value)` tuple | argv 为 tuple，shell=False，无注入面 ✓ |
| `shell` | `False` | 不经过 `cmd.exe`，无 CRT quote/batch 转义风险 ✓ |
| `stdin` | `subprocess.DEVNULL` | 无继承 stdin，消除 stdin pipe EOF 死等 ✓ |
| `stdout` | `subprocess.DEVNULL` | 删除 `capture_output=True`，消除无消费者 stdout pipe ✓ |
| `stderr` | `subprocess.DEVNULL` | 删除 `capture_output=True`，消除无消费者 stderr pipe ✓ |
| `close_fds` | `True` | 禁止继承非 stdio handle；Windows 通过 handle_list 机制实现 ✓ |
| `text` | `False` | binary mode，与 DEVNULL 一致，无 decode error 风险 ✓ |
| `check` | `False` | 手动检查 returncode，不依赖 subprocess 自动抛错 ✓ |
| `timeout` | `30.0` | 单次 setx owner bound ✓ |

- `subprocess.DEVNULL` 跨平台可用（POSIX: `/dev/null`，Windows: `nul`）。 ✓
- `capture_output` 零命中：`rg -n 'capture_output' dayu/cli/init_environment.py` 返回空。 ✓
- 逐参数顺序与 `_SetxRecorder.__call__` 的 strict keyword-only signature 精确匹配：任何多余/缺失 kwarg 都会导致测试 `TypeError`。 ✓

#### 1.3 Exception handling（L428-442）

```python
except KeyboardInterrupt:
    raise EnvironmentPersistenceInterrupted(
        _interrupted_result(
            target=_WINDOWS_SETX_TARGET,
            written_names=tuple(written_names),
            unwritten_names=tuple(item.name for item in plan.entries[index:]),
            retained_paths=(),
        )
    ) from None
except subprocess.TimeoutExpired:
    return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
except OSError:
    return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
if completed.returncode != 0:
    return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
```

逐路径验证：

- **KeyboardInterrupt**: 精确捕获，构造 typed `EnvironmentPersistenceInterrupted`（继承自 `KeyboardInterrupt`，不被普通 `except Exception` 捕获），`from None` 抑制原始 traceback。`written_names` 为当前 index 前已成功项，`unwritten_names` 为当前 index 起所有项。 ✓
- **TimeoutExpired**: 精确捕获 `subprocess.TimeoutExpired`（非父类 `SubprocessError`），**不绑定** exception 实例（无 `as e`）→ raw `cmd` attribute（含完整 `("setx", name, value)` argv）不可访问。不格式化、不记录、不转抛、不 retry。直接转换为 names-only failure/partial-failure。 ✓
- **OSError**: 与 TimeoutExpired 完全对称——不绑定 raw exception，不 retry，同一 `_windows_failure_result` 收口。 ✓
- **nonzero returncode**: 手动检查 `completed.returncode`，同一 `_windows_failure_result` 收口。 ✓
- Exception 捕获顺序正确：`KeyboardInterrupt` → `TimeoutExpired` → `OSError`，三者无继承关系重叠。 ✓
- `completed` 变量在 `if completed.returncode != 0` 处一定已定义（所有提前 return/raise 路径在到达该行前已退出）。 ✓

#### 1.4 Success path（L443-450）

```python
written_names.append(entry.name)
# ... loop ends ...
return EnvironmentPersistenceResult(
    status=EnvironmentPersistenceStatus.SUCCESS,
    target=_WINDOWS_SETX_TARGET,
    written_names=tuple(written_names),
    unwritten_names=(),
    retained_paths=(),
)
```

- `written_names.append(entry.name)` 仅在 `returncode == 0` 后执行——任何非零返回码已在 L441-442 提前返回。 ✓
- 整批成功后返回 SUCCESS 结果，所有 names 写入 `written_names`。 ✓
- 当前进程 `os.environ` 注入由上游 `persist_environment()` 函数（L328-331）在 `result.succeeded is True` 后整批执行，不在本函数内。 ✓

#### 1.5 `_windows_failure_result` helper（L453-479）

```python
status = (
    EnvironmentPersistenceStatus.PARTIAL_FAILURE
    if written_names
    else EnvironmentPersistenceStatus.FAILURE
)
return EnvironmentPersistenceResult(
    status=status,
    target=_WINDOWS_SETX_TARGET,
    written_names=written_names,
    unwritten_names=tuple(entry.name for entry in plan.entries[failed_index:]),
    retained_paths=(),
)
```

- 纯函数：仅基于 `written_names` 是否为空选择 `PARTIAL_FAILURE` vs `FAILURE`。 ✓
- `unwritten_names` 从 `failed_index` 起切片——first failure（index=0）返回全量 unwritten，middle failure 返回从失败项起未写入项。 ✓
- `retained_paths=()` — Windows setx 路径无临时文件，与 POSIX atomic write 不同。 ✓
- 不声称 rollback——accepted plan §2.2 明确 timeout/terminate 竞争下 `setx` 可能已完成 registry write，本函数不假装可回滚。 ✓

#### 1.6 Docstring 更新

- `EnvironmentPersistenceInterrupted` docstring（L200）："不包含值或 ``setx`` captured output" → "不包含值或 ``setx`` output"。语义正确——production 不再 capture output。 ✓
- `_interrupted_result` docstring（L781）："不携带 value/captured output" → "不携带 value/native output"。语义等价更新。 ✓

### 2. Test code（`tests/cli/test_init_environment.py`）

#### 2.1 `_SetxCall` dataclass（L34-46）

```python
@dataclass(frozen=True, slots=True)
class _SetxCall:
    args: tuple[str, str, str]
    shell: bool
    stdin: int
    stdout: int
    stderr: int
    close_fds: bool
    text: bool
    check: bool
    timeout: float
```

- `frozen=True, slots=True`：不可变，内存高效。 ✓
- 逐字段记录完整 native process contract（args、shell、所有 stdio、close_fds、text、check、timeout）。 ✓
- 仅在测试中使用（`_SetxRecorder.calls` 的元素类型），属于 test infrastructure，非生产 overdesign。 ✓

#### 2.2 `_SetxRecorder` 更新（L49-128）

- 构造器签名从 `raise_at: int | None` 重构为 `os_error_at: int | None` + `timeout_at: int | None`，异常类型语义明确分离。 ✓
- `calls` 类型从 `list[tuple[...]]` 升级为 `list[_SetxCall]`，结构性相等断言替代松散 tuple 比对。 ✓
- `__call__` signature 精确匹配 production `subprocess.run` 的 9 个 keyword-only 参数：`args, shell, stdin, stdout, stderr, close_fds, text, check, timeout`。任何多余/缺失 kwarg 都会导致 `TypeError`。 ✓
- 异常抛出顺序：`KeyboardInterrupt` → `TimeoutExpired` → `OSError` → 正常返回。`TimeoutExpired(cmd=args, timeout=timeout)` 构造时传入完整 raw argv，测试可验证 value non-disclosure。 ✓
- `CompletedProcess` 不再包含 fake `stdout=b"ignored stdout"` / `stderr=b"ignored stderr"`——production 不再拥有输出，测试 fake 同步消除。 ✓

#### 2.3 `_expected_setx_call` helper（L131-149）

```python
def _expected_setx_call(entry: EnvironmentPersistenceEntry) -> _SetxCall:
    return _SetxCall(
        args=("setx", entry.name, entry.value),
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        text=False,
        check=False,
        timeout=_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS,
    )
```

- 单一 helper 构造所有预期测试值，与 `_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS` 保持一致。 ✓
- 返回完整 `_SetxCall` dataclass，与 `recorder.calls` 做 `==` 比较。 ✓
- 仅在测试中使用，不进入生产路径。 ✓

#### 2.4 Test cases 验证

| 测试 | 覆盖路径 | 关键断言 |
|---|---|---|
| `test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success` | 整批成功（2 entries） | `recorder.calls == [_expected_setx_call(first), _expected_setx_call(second)]`；`environment_visible_during_calls == [False, False]`；整批注入后 `os.environ[name] == value`；value 不在 result repr/captured out/captured err |
| `test_windows_nonzero_reports_names_only_without_retry_or_injection[first]` | 首项 nonzero | `status=FAILURE`；`written_names=()`；`unwritten_names=全部`；零注入；零 retry |
| `test_windows_nonzero_reports_names_only_without_retry_or_injection[middle]` | 中间项 nonzero | `status=PARTIAL_FAILURE`；`written_names=(entries[0].name,)`；`unwritten_names=(entries[1].name, entries[2].name)` |
| `test_windows_os_error_reports_partial_names_without_retry_or_injection` | middle OSError | `os_error_at=1` → PARTIAL_FAILURE；与 nonzero middle 语义一致 |
| `test_windows_timeout_hides_raw_argv_without_retry_or_injection` | middle TimeoutExpired | `timeout_at=1` → PARTIAL_FAILURE；`entry.value not in result_repr`；`entry.value not in captured.out/err`；`raw_argv_repr not in result_repr/captured.out/captured.err` |
| `test_windows_interrupt_reports_written_and_unwritten_names_without_values[first]` | 首项 interrupt | `interrupt_at=0` → `written_names=()`、`unwritten_names=全部` |
| `test_windows_interrupt_reports_written_and_unwritten_names_without_values[middle]` | 中间 interrupt | `interrupt_at=1` → `written_names=(entries[0].name,)`、`unwritten_names=(entries[1].name, entries[2].name)` |
| `test_windows_interrupt_reports_written_and_unwritten_names_without_values[last]` | 末项 interrupt | `interrupt_at=2` → `written_names=(entries[0].name, entries[1].name)`、`unwritten_names=(entries[2].name,)` |
| `test_windows_environment_injection_interrupt_keeps_completed_store_truth` | 注入阶段 interrupt | 全部 setx 成功后中断：`written_names=全部`、`unwritten_names=()`、`environment == {}` |
| `test_unconfirmed_windows_plan_never_calls_setx` | 未确认 plan | `recorder.calls == []` |

全部 57 tests passed。每个 failure/interrupt case 均断言：
- 精确调用前缀（`recorder.calls == [_expected_setx_call(entry) for entry in ...]`）
- 调用次数（通过 calls 列表长度隐式断言——非零返回码路径提前返回不继续调用）
- 零 retry（recorder 调用次数 ≤ failure 位置 + 1）
- 零提前环境注入（`environment_visible_during_calls == [False] * N`）
- value non-disclosure（`entry.value not in repr(result)`）

#### 2.5 `_SetxRecorder` 异常抛出顺序分析

```python
if self._interrupt_at == call_index:
    raise KeyboardInterrupt
if self._timeout_at == call_index:
    raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)
if self._os_error_at == call_index:
    raise OSError("setx unavailable")
```

异常抛出顺序：KeyboardInterrupt → TimeoutExpired → OSError → 正常返回。此顺序与 production `try/except` 捕获顺序（KeyboardInterrupt → TimeoutExpired → OSError）**恰好互为镜像**——recorder 先抛高优先级异常，production 先捕获高优先级异常。同一索引处 recorder 只触发一个异常（三个 `if` 共享同一 `call_index`，且构造时只设置一个 `*_at` 参数），不会出现异常优先级竞争。 ✓

### 3. Semantic ownership 复核

- 唯一 semantic owner：`_persist_windows_environment()`——负责 `setx` executable/argv、stdio、handle inheritance、单次 timeout 以及 native outcome 到 names-only result 的投影。 ✓
- Contract 输入：`WindowsEnvironmentPersistencePlan`（typed dataclass）。 ✓
- Contract 输出：`EnvironmentPersistenceResult`（typed dataclass）或 `EnvironmentPersistenceInterrupted`（typed exception）。 ✓
- `_WINDOWS_SETX_TIMEOUT_SECONDS` 为 owner-bound 模块常量，非分散在各处的魔法数字。 ✓
- 未在下游 consumer、adapter、展示层或 fixture 中以 fallback/特例/重复计算/loose parsing 补偿缺失语义。 ✓
- 未新增 `hasattr`/`getattr`/兼容 shim/兼容 re-export。 ✓
- Registry round-trip/cleanup 仍属于真实 Windows smoke 验证 owner（S3）。 ✓
- `TimeoutExpired` 的 non-disclosure 是该 owner 的自然行为：catch → discard → project names-only。 ✓
- `_windows_failure_result()` 是纯 names-only result 投影 helper，不含回滚声称。 ✓

### 4. Overdesign 检查

- 实现为最小化修复：
  - 新增 1 行模块级常量。
  - 修改 1 处 `subprocess.run` 调用：删除 `capture_output`，新增 `stdin/stdout/stderr=DEVNULL`、`close_fds=True`、`timeout`。
  - 新增 2 行 `except subprocess.TimeoutExpired`。
- 无 process tree kill、Win32 handle enumeration、job object、registry fallback、PowerShell、outer timeout、shell、日志、retry 或兼容分支。 ✓
- `_SetxCall` dataclass 与 `_expected_setx_call` helper 仅在测试中使用，属于 test infrastructure，非生产 overdesign。 ✓

### 5. 安全与 deferred 边界

- Added-lines 零命中 `shell=True`、`errors=replace`、PowerShell、`winreg`/`reg.exe`、process group/job object、deferred Issue 142/151/175/177/178。 ✓
- `TimeoutExpired` raw argv/value 未进入 typed result、stdout/stderr capture、artifact 或日志——已验证：exception 不绑定（无 `as e`），`_windows_failure_result` 只使用 names。 ✓
- 未读取、发布或日志记录 configured secret/token/timeout raw argv。 ✓
- `pyproject.toml` 未修改——`requires-python = ">=3.11"` 不变（F01 未回流）。 ✓
- README 未修改——accepted plan 与 Controller validation 明确 README 更新属于 S3 owner。 ✓
- S3 outer harness、canary、等 deferred items 未被提前实施或触及。 ✓
- `tests/cli/test_init_smoke.py` 的既有 `reg.exe` 说明/调用 7 处未被 S2 diff 新增、修改或删除——属于 approved S3 owner。 ✓

### 6. 项目指令合规检查

| 指令 | 状态 |
|---|---|
| 语义所有权唯一明确 | ✓（`_persist_windows_environment` 为唯一 owner） |
| 中文 docstring 完整 | ✓（所有新增/修改函数均有完整中文 docstring） |
| 禁止 `object`/`Any`/无类型参数 | ✓（零命中） |
| 禁止 `hasattr`/`getattr` 逃避类型设计 | ✓（零命中） |
| 禁止魔法数字/字符串 | ✓（`_WINDOWS_SETX_TIMEOUT_SECONDS` 为 `Final` 模块常量） |
| 禁止兼容性代码 | ✓（零 re-export/wrapper/alias） |
| 禁止 God object/function/dataclass | ✓（实现最小化，无 God 结构） |
| 测试覆盖 ≥ 80% | ✓（93%，`_persist_windows_environment` 100%） |
| pyright 零诊断 | ✓ |
| 禁止向下游消费者补偿语义 | ✓（所有语义由 owner 直接产生） |

## Adversarial pass

以下 adversarial scenarios 均被逐行走读证伪或确认无害：

### A. `TimeoutExpired` 后 `completed` 未定义？

**证伪**。`except subprocess.TimeoutExpired:` 块以 `return` 结束，控制流不继续到 `if completed.returncode != 0`。同理 `OSError` 和 `KeyboardInterrupt`。 ✓

### B. `TimeoutExpired` 与 `OSError` 的捕获顺序导致误捕获？

**证伪**。`TimeoutExpired` 继承自 `SubprocessError`（→`Exception`），`OSError` 继承自 `Exception`，两者无继承关系。捕获顺序不影响正确性。 ✓

### C. `close_fds=True` + `DEVNULL` 在真实 Windows 上可能导致 handle 泄漏？

**已分析，非当前 owner 可修复**。CPython 3.7+ 通过 `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` 在 `close_fds=True` + 显式 stdio handle 时正确只继承指定的三个 DEVNULL handle。真实 Windows 行为仍需 S3 Controller R12 远端验证——本地 platform skip 不是 waiver。 ✓

### D. `TimeoutExpired` 后 setx 的 registry write 可能已完成，result 声称"unwritten" 是否误导？

**已分析，非缺陷**。Accepted plan §2.2 明确"不声称 rollback"。timeout 后 typed result 投影的是"未收到 success 确认的名称"，不是"registry 中不存在的名称"。这是外部命令的固有语义限制，S2 owner 无法提供原子 registry transaction。 ✓

### E. `_SetxRecorder` 的异常抛出顺序与 production 的捕获顺序是否匹配？

**确认匹配**。Recorder 抛出顺序（KeyboardInterrupt → TimeoutExpired → OSError）与 production 捕获顺序（KeyboardInterrupt → TimeoutExpired → OSError）恰好互为镜像。同一索引只触发一个异常类型。 ✓

### F. `_expected_setx_call` 是否会因 `_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS` 与 `_WINDOWS_SETX_TIMEOUT_SECONDS` 不同步而漂移？

**已分析，低风险**。两者均为 `Final[float] = 30.0`。任何一方被意外修改都会导致测试失败（recorder 记录的 timeout 与 expected 不匹配 → `==` 失败）。这是 test infrastructure 的 self-checking 属性。 ✓

## Findings

**Material finding: 0**

本轮完整逐行 re-review、CPython 官方文档/源码直接验证、adversarial pass、项目指令合规检查，均未发现新的 correctness、stability、maintainability、semantic ownership drift 或 security finding。

两项 DS initial review candidate（F01、F02）经独立复核确认 Controller 裁决成立：
- F01 的前提事实（Python 3.11.0–3.11.3 在 close_fds=True + DEVNULL 时抛 ValueError）与 CPython 官方文档和源码直接矛盾，引用的 gh-91150 甚至不是 subprocess 相关 issue。
- F02 要求增加 `exception kind × first index` 的笛卡尔积测试，但三类 failure 已分别在 owner boundary 被见证，first-index state transition 已被 nonzero-returncode 覆盖，不存在未测试的独立生产分支。

两项 rejected candidate 均未通过代码、测试、pyproject.toml、README 或 follow-up 语义回流。

## Final ledger

| 类别 | 值 |
|---|---|
| Accepted code finding | `0` |
| Rejected reviewer candidate（经独立复核确认） | `2` |
| Needs-evidence finding | `0` |
| Design contradiction | `0` |
| Local blocker | `0` |
| Current-slice production/test/README/workflow fix needed | `0` |
| Real Windows residual | `1`（`PENDING_RELEASE_BLOCKER`，三 slice accepted 后由 Controller 执行 R12） |

## Verdict

**`PASS / MATERIAL FINDING 0 / ADJUDICATION VERIFIED / READY_FOR_S2_ACCEPTED_COMMIT / REAL_WINDOWS_PENDING`**

S2 implementation 在本地环境中完全正确。Controller 对两项 candidate 的裁决经独立复核确认为正确。Immutable code/test diff、review dispositions 与 scope 均无漂移。Production 变更为最小化 setx native process contract 修复，tests 为严格 owner contract 覆盖。无 material finding、无 blocker、无 open question。

真实 Windows DEVNULL/handle/native-timeout 行为仍须三 slice accepted 后由 Controller 按 accepted plan §8/§9.3 执行 R12 远端验证。本地 pyright/test pass 不是 Windows waiver。

## 产出

- **文件**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-rereview-ds.md`
- **Production file SHA-256**: `ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`
- **Test file SHA-256**: `7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`
- **Immutable diff SHA-256**: `939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`
- **Blocker**: 无本地 blocker
