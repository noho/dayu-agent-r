# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S2 Implementation

## Gate identity and outcome

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07` fourth Windows remediation。
- Gate：`WIN4-S2 implementation`；风险级别为 High Risk production owner change。
- Plan baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- Accepted plan：`15979f5d32738148bf53daf9defe2dca59b8360c`。
- Entry / accepted S1 commit：`e34edfa39f244d736aeaf8b9ea82ff9152698b2b`。
- Verdict：`PASS_LOCAL_IMPLEMENTATION / READY_FOR_CONTROLLER_VALIDATION / REAL_WINDOWS_PENDING`。
- Stop：停在当前 implementation gate；未进入 S3、code review、commit、push、workflow dispatch 或 PR gate。

## First-principles judgment and owner

本 slice 动机成立。第四轮 R12 直接证据已经证明 outer CLI process 返回 1 后，stdout reader 仍等待 inherited pipe EOF；而当前唯一 native process 创建点
`dayu.cli.init_environment._persist_windows_environment()` 使用 `capture_output=True`，production 只读取 `returncode`，没有 stdout/stderr、错误、日志或测试
output consumer。无消费者 pipe 没有业务语义，却把 descendant handle lifetime 耦合到 outer capture EOF；同时每次 `setx` 没有自己的执行上限。

唯一语义 owner 是 `_persist_windows_environment()`：它负责 `setx` executable/argv、stdio、handle inheritance、单次 timeout 以及 native outcome 到 names-only
result 的投影。Registry round-trip/cleanup 仍属于真实 Windows smoke 验证 owner；本 slice 没有替换 registry authority，也不声称 timeout 后 durable write 已回滚。

S1 已在 accepted commit 修正 Windows real-smoke 的 company-name 测试输入；本 slice 未修改或重新解释 Fins owner。S3 的 outer process safe failure projection、canary 与
`tests/README.md` 仍为后续 approved slice，未提前实施。

## Exact changed scope and implementation

Changed paths：

- `dayu/cli/init_environment.py`：Windows native process contract owner。
- `tests/cli/test_init_environment.py`：该 owner contract 的唯一直接测试。
- 本 artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-implementation-codex.md`。

Production implementation：

- 新增模块级 `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0`。
- 每次调用固定 argv `("setx", entry.name, entry.value)`，并显式传入 `shell=False`、三个 `subprocess.DEVNULL`、`close_fds=True`、`text=False`、
  `check=False` 与 30 秒 timeout；删除 `capture_output`。
- 精确 `except subprocess.TimeoutExpired:`，不绑定、检查、格式化、记录或转抛 raw exception；与 `OSError` 一样返回当前 index 的 names-only
  failure/partial-failure；不 retry。
- `KeyboardInterrupt` 的 typed written/unwritten names truth、nonzero/OSError truth，以及全部 `setx` 成功后才批量注入 `os.environ` 的既有状态机保持不变。
- 没有新增日志、outer timeout、shell、PowerShell、process-tree kill、job object、registry fallback 或 compatibility branch。

Test owner implementation：

- `_SetxRecorder` 改为完整严格签名；任何缺少/多余 subprocess kwarg（包括重新出现 `capture_output`）都会直接使 owner test 失败。
- `_SetxCall` 逐字段记录 argv、shell、stdin/stdout/stderr、close_fds、text、check 与 timeout；fake stdout/stderr 已删除，返回码是唯一 native output input。
- 直接覆盖 whole-batch success、first/middle nonzero、middle `OSError`、middle `TimeoutExpired`、first/middle/last `KeyboardInterrupt` 和 environment-injection
  interrupt；每个 native failure/interruption case 都断言精确调用前缀、全部 kwargs、no retry 与 no environment injection。
- Timeout fake 使用含完整 raw argv/value 的 `subprocess.TimeoutExpired`。测试断言 value 与 raw argv repr 均不进入 result repr、stdout 或 stderr capture；结果只保留
  already-confirmed/unconfirmed names，未声称 registry rollback。

## Immutable diff and protected paths

- Code/test binary diff SHA-256：`939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`。
- Final production file SHA-256：`ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`。
- Final test file SHA-256：`7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`。
- 既有 Controller control doc Git blob 保持 `fb0856d5352cd930b7ba3aec63b9735c613b6e29`，其 unstaged binary diff SHA-256 保持
  `7f8b8e2690168ff084238ce4f707fdecb3ad07e49ecdc6cfc08ac94394b02d71`。
- 既有 S1 post-commit Controller artifact Git blob 保持 `f6a47cbaffcbb6404526f10a7f16d4d703aae663`。
- 未修改 S1 implementation/test、S3、README、design、workflow、Fins、Host/Engine 或 deferred Issue 路径。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

- Target owner test：`pytest tests/cli/test_init_environment.py -q` → `57 passed`。
- Branch coverage：同一 owner file 使用 `--cov=dayu.cli.init_environment --cov-branch` → `57 passed`；line `291/307 = 94.79%`，branch
  `73/84`，combined `93%`，高于 `>=80%`；JSON 位于 ignored temp output
  `workspace/tmp/win4-init-environment-coverage.json`。
- Related CLI regression：为满足执行 cell 上限，以互斥集合运行完整 `tests/cli` collection：排除 upload 文件部分 `501 passed, 5 skipped`；
  `test_upload_filings_from_command.py` 部分 `20 passed, 2 skipped`。合计 `521 passed, 7 skipped = 528 collected`，无遗漏、失败或 xfail。
- Full pyright：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- Scoped Ruff（production/test owner 加 S2 相关 smoke/upload files）→ `All checks passed!`。
- Full Ruff entry/final：Ruff `0.15.11`；两次均为既有 `142` entries。按
  `(filename, location, code, message, fix-applicability)` 排序后的 canonical tuple SHA-256 均为
  `82b3556a9515c8875553ad77cde6565f8340b07a9d84ba3681a115fb3b8780f6`；exact comparison exit 0，新增/扩散为 0。
- `git diff --check` → PASS。

本地 platform skip 不能替代真实 Windows closure；本轮未 dispatch R11/R12，也未产生可声称远端 closure 的 run id、metadata、artifact 或 canary scan evidence。

## README, source and security decision

- README 不更新。Public init grammar、交互、输出通道和最终用户 workflow 未变化；accepted plan 明确把 `tests/README.md` 的 setx/outer-harness 统一说明放在 S3，且
  本轮 allowlist 不允许修改 README。
- `capture_output=True` 在 production owner 中零命中；`shell=True` / `errors=replace` 零命中；timeout exception binding、fake stdout/stderr、retry 与 owner logging
  零命中。
- Added-lines forbidden scan对 `winreg`、`reg.exe`、PowerShell、process group/job object、deferred Issue 142/151/175/177/178 和
  `web_tools_storage_states` 零命中；deferred-term tree scan零命中。
- Accepted aggregate native-tool scan仍显示 `tests/cli/test_init_smoke.py` 七处既有 `reg.exe` 说明/调用；entry commit 逐行相同，accepted S1 artifact 已将其归入
  后续 approved S3/真实 registry smoke owner。本 slice 没有新增、修改或删除这些行。
- 未读取、请求、导出或扫描 GitHub Secrets/configured production values；未把 environment value、raw timeout exception、setx argv、stdout/stderr 或 registry value
  写入 result、capture、artifact 或日志。

## Residual risks and next entry point

- `REAL_WINDOWS_PENDING`：DEVNULL/close-fds/native timeout 的真实 R12 round-trip 与 R11/R12 clean closure 仍需三 slices accepted 后由 Controller 按 plan §8/§9.3
  执行。分类：`covered by later approved slice / Controller-owned remote closure`。
- `WIN4-S3_PENDING`：outer harness safe timeout projection、run-id canary 与 README 仍未实现。分类：`covered by later approved slice WIN4-S3`。
- Aggregate native scan 的既有 `reg.exe` 命中属于 S3 real registry smoke，不是 S2 新增 finding。分类：`covered by later approved slice WIN4-S3`。
- 不存在未分类 residual risk、blocking open question 或 S2 owner 外修复需要。

Next entry point：Controller validation of this immutable S2 implementation diff；随后才可进入 dual complete code review/fix/re-review/accepted commit。当前 staged tree
保持为空；本轮不 commit。
