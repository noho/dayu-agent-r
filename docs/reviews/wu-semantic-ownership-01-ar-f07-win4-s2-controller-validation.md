# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S2 Controller Validation

## Result

`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / REAL_WINDOWS_PENDING`

## Immutable target

- Entry commit：`e34edfa39f244d736aeaf8b9ea82ff9152698b2b`。
- Production/test target：`dayu/cli/init_environment.py`、`tests/cli/test_init_environment.py`。
- Code/test binary diff SHA-256：`939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`。
- Final production file SHA-256：`ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`。
- Final test file SHA-256：`7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`。
- AgentCodex implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-implementation-codex.md`，SHA-256 `1e2a8a418d2375dc5ab10d81cbcc1ecba225806ef9ee98d9b6fa2f920d02187c`。

Controller 同时复核了两条受保护的既有 dirty artifacts：control doc Git blob 仍为 `fb0856d5352cd930b7ba3aec63b9735c613b6e29`，S1 accepted-commit validation Git blob 仍为 `f6a47cbaffcbb6404526f10a7f16d4d703aae663`；AgentCodex 未改写它们。

## Owner and behavior verification

Controller 逐行确认：

- `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0` 是单次本机 `setx` owner bound。
- argv 保持 `("setx", entry.name, entry.value)`，并显式使用 `shell=False`、三路 `subprocess.DEVNULL`、`close_fds=True`、`text=False`、`check=False` 和该 timeout；`capture_output` 已删除。
- `subprocess.TimeoutExpired` 被精确捕获且不绑定、不格式化、不记录、不转抛；它与 `OSError` 一样投影为当前 index 的 names-only failure/partial-failure，且没有 retry。
- whole-batch success 后才注入当前 `os.environ`；nonzero、`OSError` 与 `KeyboardInterrupt` 的 written/unwritten names truth 保持不变。
- Strict `_SetxRecorder` 记录完整 kwargs，并通过 signature 直接拒绝额外或缺失参数；fake stdout/stderr 已删除。
- Tests 覆盖 success、first/middle nonzero、middle `OSError`、middle `TimeoutExpired`、first/middle/last `KeyboardInterrupt`、environment-injection interrupt、no retry、no early injection 与 value/raw argv non-disclosure。

## Independent validation

Controller 在 `.venv` 下独立运行：

- Owner tests + branch coverage：`57 passed`；`dayu/cli/init_environment.py` combined coverage `93%`，高于 `>=80%`。
- Init/argument focused regression：`163 passed, 5 skipped, 3 existing edgar deprecation warnings`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：`All checks passed!`。
- `git diff --check`：PASS；staged tree empty。

AgentCodex 另运行完整 CLI 等价互斥分片，合计 `521 passed, 7 skipped`；full Ruff entry/final 都是既有 142-entry exact tuple，canonical SHA-256 均为 `82b3556a9515c8875553ad77cde6565f8340b07a9d84ba3681a115fb3b8780f6`，新增/扩散为 `0`。

## Scope, README, security and residuals

- README 不更新：public init grammar、用户工作流和输出通道未变，`tests/README.md` 的 S2/S3 组合说明由 accepted S3 owner负责。
- S2 added-lines 没有 `shell=True`、replace decode、PowerShell、winreg/reg.exe、process group/job object、deferred Issue 142/151/175/177/178 或兼容分支。
- 没有读取或发布 configured production secret；timeout raw argv/value 未进入 typed result、stdout/stderr capture、artifact 或日志。
- 未实施 S3 outer harness、canary、README、workflow 或 registry authority替换。

真实 Windows DEVNULL/handle/timeout 行为仍须三 slice accepted 后由 Controller 新跑 R12；本地结果不是 waiver。下一 gate 仅授权 AgentMiMo / AgentDS 对上述 immutable S2 implementation 进行并发完整 code review。
