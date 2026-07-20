# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Implementation — Controller Validation

## Verdict

**PASS / READY FOR DUAL COMPLETE CODE REVIEW**

本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 AR-F07 WIN4-RW-S2 implementation continuation，不是新 WU。Controller 独立检查 direct diff、owner contract、测试、覆盖率、类型、lint、README、安全与 deferred scope 后，未发现 stop condition、allowlist drift 或未经授权的语义。

## Immutable target

| Item | Value |
|---|---|
| implementation entry HEAD | `bbb10959253fb3cb4bd22299196cf65a4a961b10` |
| final plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` |
| four protected paths binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` |
| five product/test/README paths aggregate diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` |
| AgentCodex implementation artifact SHA-256 | `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910` |
| staged tree | empty |
| `git diff --check` | PASS |

Immutable review target 是上述五个 product/test/README payload 加 AgentCodex implementation artifact 与本 Controller validation/control evidence。Review agents不得修改、stage、commit、push或dispatch。

## Semantic-owner validation

1. `dayu.cli.commands.init::_read_secret_input()` 是唯一 secret-input capability owner：TTY 调 `getpass.getpass()`；redirected stdin先向 stderr写 names-only prompt并flush，再精确 `readline()` 一次。
2. TTY `EOFError` 与 redirected empty read收敛为同一 value-free `CliInitOperationError`；`KeyboardInterrupt`、`OSError`均不被吞掉。
3. 只移除一个 LF以及其前的CR；bare CR与其它尾随空白保持，不引入 loose normalization。
4. 两个 required/optional call sites复用同一 owner；没有下游 fallback、pytest/mock/capture identity、`sys.__stdin__`、platform-specific shim或 shared test seam。
5. `tests/cli/test_prompt_command.py` 的新增内容只有必要 import、module-private strict typed TTY fake和 exact integration node的一次stdin注入；其它nodes、getpass values、prompt/runtime assertions均未修改。

## Fresh Controller validation

所有 Python 命令均在 `.venv` / Python 3.11 环境运行。

| Validation | Controller result |
|---|---|
| `pytest tests/cli -q` | `552 passed, 7 skipped, 3 warnings` |
| `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-branch ... -q` | `41 passed`; `init.py` line coverage `91%` |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff on four affected Python files | `All checks passed!` |
| `git diff --check` | PASS |

三个 warning均来自已安装 `edgar` package 的既有 deprecated imports，与本 slice 无关。AgentCodex 另行 fresh 通过 owner exact nodes `14 passed`、prompt exact node `1 passed`、init smoke `28 passed, 5 skipped`、upload file `20 passed, 2 skipped`、three-file aggregate `89 passed, 7 skipped`、POSIX redirected-init smoke `exit=0 / disclosure_matches=0`；Controller 的 full CLI与 whole owner file独立覆盖这些本地 contract。

Agent 首次错误并发运行 upload whole-file 与其固定目录 exact node，两个进程竞争 `workspace/tmp/r11-posix-real`；直接路径证据与随后串行 exact node PASS证明这是验证命令竞争，不是产品或测试实现失败，且没有为此修改代码、测试或 timeout。

## README, security and deferred scope

- 根 README 只向最终用户说明 TTY隐藏与 redirected逐行输入；`tests/README.md`只说明 owner test矩阵和真实Windows destination，均符合各自更新边界。
- Config、Host internal SQLite/EventLog继续属于 trusted-local domain。本 slice未新增 durable store或 projection；Tool Trace、audit、public/LLM-facing/operator diagnostics仍不得出现API key/header明文。
- Production source scan只在 `_read_secret_input()` TTY分支命中一次 `getpass.getpass()`；未命中 `hasattr/getattr`、`sys.__stdin__`、`msvcrt`、pytest/mock/capture identity、shell/process/PTY兼容路径。
- `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml`、`tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py`与`dayu/fins/**`相对entry均零diff。
- 没有实现Issue 142/151/175/177/178、Web/WeChat/render、setx redesign、console/PTY/process isolation、统一secret/authorization framework或Fins generic diagnostic schema。

## Review authorization and remaining boundary

当前 local accepted/open finding、needs-evidence、design contradiction与blocker均为 `0`。只授权 AgentMiMo/AgentDS 并发执行完整 code review，必须从 direct code/tests/README、final plan、完整review链和immutable target审查，而不能只看 implementation summary。

真实 Windows R11/R12仍是 `PENDING_RELEASE_BLOCKER`，只能在 S2 code-review/fix/re-review、accepted local commit与WIN4 aggregate deepreview闭合后 fresh dispatch；当前不得复用旧 run作为closure，也不得提前push/dispatch/PR。
