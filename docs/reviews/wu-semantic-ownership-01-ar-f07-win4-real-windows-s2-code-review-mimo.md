# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 — 第一路 Code Review（AgentMiMo）

## Verdict

**PASS / 未发现实质性问题**

本次 review 是既有 `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07 WIN4-RW-S2` 的第一路完整 code review，不是新 WU。AgentMiMo 独立审查 direct code/tests/README、final plan、完整 review 链和 immutable target 后，未发现 blocker、new findings 或 semantic ownership drift。

## Scope

- Mode: Current Changes Mode
- Branch: `phaseflow/host-issues-control`
- Base: `main` (immutable implementation entry HEAD `bbb10959253fb3cb4bd22299196cf65a4a961b10`)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-mimo.md`
- Included scope:
  - `dayu/cli/commands/init.py` — `_read_secret_input()` owner 及其两个 call sites
  - `tests/cli/test_prompt_command.py` — `test_prompt_command_uses_init_generated_workspace_config` fixture 迁移
  - `tests/cli/test_init_command.py` — secret-input owner exact nodes
  - `README.md` — 用户可见 TTY/redirected 行为说明
  - `tests/README.md` — owner test 矩阵说明
  - `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` — final plan
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-controller-validation.md` — Controller validation
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-codex.md` — AgentCodex implementation artifact
- Excluded scope:
  - `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml` — 零 diff
  - `tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py` — 零 diff
  - `dayu/fins/**` — 零 diff
- Parallel review coverage: 无（scope 有限，单 reviewer 可完整覆盖）

## Immutable target

| Item | Value |
|---|---|
| implementation entry HEAD | `bbb10959253fb3cb4bd22299196cf65a4a961b10` |
| final plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` |
| five product/test/README paths aggregate diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` |
| AgentCodex implementation artifact SHA-256 | `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910` |
| Controller validation SHA-256 | `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b` |
| staged tree | empty |
| `git diff --check` | PASS |

## Findings

未发现实质性问题。

## Adversarial review detail

### 1. stdin capability owner

**直接证据**: `dayu/cli/commands/init.py:468-493` — `_read_secret_input()` 是唯一 secret-input capability owner。

```python
def _read_secret_input(prompt: str) -> str:
    if sys.stdin.isatty():
        try:
            return getpass.getpass(prompt)
        except EOFError as exc:
            raise CliInitOperationError("secret input ended before completion") from exc

    sys.stderr.write(prompt)
    sys.stderr.flush()
    value = sys.stdin.readline()
    if value == "":
        raise CliInitOperationError("secret input ended before completion")
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    return value
```

- TTY 路径：`sys.stdin.isatty()` 为 True 时调用 `getpass.getpass()`，隐藏输入。
- Redirected 路径：先向 stderr 写 names-only prompt 并 flush，再精确 `readline()` 一次。
- 没有 `hasattr/getattr`、`sys.__stdin__`、platform-specific shim 或 production fallback。

**结论**: owner boundary 清晰，capability 分流由 `sys.stdin.isatty()` 唯一决定。

### 2. TTY/getpass

**直接证据**: `dayu/cli/commands/init.py:479-482` — TTY 分支只调用 `getpass.getpass()`，`EOFError` 收敛为 `CliInitOperationError`。

- `getpass.getpass()` 是标准库的 TTY hidden input 实现。
- `KeyboardInterrupt` 不被 catch，原样透传（`dayu/cli/commands/init.py:224-225`）。
- `OSError` 不被 catch，原样透传（`dayu/cli/commands/init.py:235-240`）。

**结论**: TTY 路径正确，无吞异常、无 fallback。

### 3. Redirected single-line/flush/EOF/interrupt/CRLF/bare-CR

**直接证据**: `dayu/cli/commands/init.py:484-493`。

- `sys.stderr.write(prompt)` + `sys.stderr.flush()`：确保 prompt 在 redirected stdin 下可见。
- `sys.stdin.readline()`：精确读取一次 logical line。
- `value == ""`：EOF 检测，收敛为 `CliInitOperationError`。
- `value.endswith("\n")`：移除一个 LF。
- `value.endswith("\r")`：移除 LF 前的 CR（CRLF 处理）。
- bare CR 与其它尾随空白保持，不引入 loose normalization。

**结论**: redirected 路径正确处理了 single-line、flush、EOF、CRLF 和 bare-CR。

### 4. Required/optional ordering/non-disclosure

**直接证据**: `dayu/cli/commands/init.py:496-543` — `_collect_environment_persistence_plan()`。

- `required_name` 先读取，若为空则 `raise CliInitOperationError`。
- `OPTIONAL_ENVIRONMENT_NAMES` 后读取，空值跳过。
- 两次 `_read_secret_input()` 调用复用同一 owner。
- 确认 prompt 只显示 `names`，不显示 values（`dayu/cli/commands/init.py:537-540`）。

**结论**: required/optional 顺序正确，values 不被披露。

### 5. Exact prompt consumer fixture

**直接证据**: `tests/cli/test_prompt_command.py:104-126` — `_TtySecretInput`。

```python
class _TtySecretInput(io.StringIO):
    def isatty(self) -> bool:
        return True

    def readline(self, size: int = -1, /) -> str:
        del size
        raise AssertionError("TTY secret input must not call stdin.readline")
```

- `isatty()` 恒为 `True`，声明 caller-owned stdin 具有 TTY 能力。
- `readline()` 立即抛 `AssertionError`，拒绝 TTY secret owner 误入 redirected stdin 路径。
- Module-private，只服务 `test_prompt_command_uses_init_generated_workspace_config` 一个 node。
- 没有从 `tests/cli/test_init_command.py` 导入私有 fake。

**直接证据**: `tests/cli/test_prompt_command.py:1239-1249` — fixture 注入。

```python
monkeypatch.setattr(builtins, "input", Mock(side_effect=("14", "", "", "")))
monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
monkeypatch.setattr(getpass, "getpass", Mock(side_effect=("", "", "", "", "")))
```

- `init_command.sys.stdin` 设为 caller-owned `_TtySecretInput()`。
- `getpass.getpass` 仍被 mock，因为 TTY 路径走 `getpass.getpass()`。
- 既有 getpass value sequence、model input sequence、generated workspace config、prompt/runtime assembly、db path 与 nested-workspace 断言全部未修改。

**结论**: fixture 锁定 owner contract，不依赖 pytest capture 偶然性。

### 6. 无 pytest/mock/capture production fallback

**直接证据**: `rg -n 'getpass\.getpass' dayu/cli/commands/init.py` 只命中 `_read_secret_input()` TTY 分支一次。

**直接证据**: `rg -n 'sys\.__stdin__|hasattr|getattr|msvcrt|pytest|mock|capture' dayu/cli/commands/init.py` 为零语义命中。

**结论**: production 不识别 pytest、mock、capture stream，不 fallback。

### 7. README

**直接证据**: `README.md:95-100`。

> 当所选模型需要 API Key 且当前进程没有对应变量时，`init` 在真实终端（TTY）隐藏输入值；
> stdin 被重定向时，每个 secret 提示写入 stderr，并从 stdin 逐项读取一行，CLI 不把值写回
> stdout/stderr。两种方式都在一次最终确认中只展示目标与变量名。

- 只向最终用户说明 TTY 隐藏与 redirected 逐行输入。
- 不写内部实现细节、Host/Engine 术语或 future workflow。

**直接证据**: `tests/README.md` 只说明 owner test 矩阵和真实 Windows destination。

**结论**: README 符合各自更新边界。

### 8. SQLite/EventLog trusted-local 裁决

**直接证据**: 本 slice 未新增 durable store 或 projection。

- Config、Host internal SQLite/EventLog 继续属于 trusted-local domain。
- 只维持 Tool Trace、audit、public/LLM-facing/operator diagnostics 不得出现 API key/header 明文的现有裁决。

**结论**: trusted-local 边界未被突破。

### 9. Tool Trace/audit/public/LLM-facing/operator diagnostic 不泄密

**直接证据**:

- `_environment_failure_message()` (`dayu/cli/commands/init.py:598-610`) 只输出 `written_names` 和 `unwritten_names`，不输出 values。
- `_report_persisted_environment_names()` (`dayu/cli/commands/init.py:613-628`) 只输出 `written_names`。
- `_format_operation_error()` (`dayu/cli/commands/init.py:778-796`) 不输出 secret values。
- Dynamic owner tests 与 POSIX smoke 共同证明 required/optional values 在 stdout、stderr、公开 exception/diagnostic 与 pytest capture 中零命中。

**结论**: diagnostic 不泄密。

### 10. Deferred/real-Windows boundaries

**直接证据**: Controller validation §5。

- Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合。
- 唯一 destination 是 final plan §13.8 的 fresh R12。
- 当前没有实现或预埋 production fallback、read-failure fallback、pytest/mock/capture identity、shared test helper、compat shim。
- 没有实现 Issue 142/151/175/177/178、Web/WeChat/render、setx redesign、console/PTY/process isolation、统一 secret/authorization framework 或 Fins generic diagnostic schema。

**结论**: deferred scope 正确，未越界。

## Open Questions

无。

## Residual Risk

1. **Darwin owner tests 不能证明 Windows console/redirected handle**: 分类：`covered by later approved remote validation`；唯一 destination 是 final plan §13.8 的 fresh R12。
2. **Caller-owned pipe/OS handle 暂存 value**: 分类：`assigned to later independent security design`；本 WU 只承诺 CLI 不主动回显或投影。
3. **Fresh R11 storage facts 失败或 R12 在 secret 读取之后出现新 failure**: 分类：`covered by diagnostic-first stop gate`；必须回 Controller。
4. **Full Ruff 142 项为 entry 既有 baseline**: 分类：`pre-existing baseline / outside current slice`。

## Review conclusion

- **PASS/FAIL**: PASS
- **Severity**: 无
- **New findings**: 0
- **Backflow findings**: 0
- **Accepted candidate**: N/A
- **Blocker**: 0
- **Open**: 0
- **Residual owner/destination**: 见 Residual Risk
- **Immutable state**: implementation entry HEAD `bbb10959253fb3cb4bd22299196cf65a4a961b10`，staged empty
- **Next gate**: Controller validation 后，真实 Windows R11/R12 闭合

## Review metadata

- Reviewer: AgentMiMo
- Review date: 2026-07-20
- Review time: 07:36:55
- Implementation entry HEAD: `bbb10959253fb3cb4bd22299196cf65a4a961b10`
- Final plan SHA-256: `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`
- AgentCodex implementation artifact SHA-256: `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910`
- Controller validation SHA-256: `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b`
