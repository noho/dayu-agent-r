# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Aggregate Re-review（第一路）

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `15979f5d32738148bf53daf9defe2dca59b8360c`（accepted WIN4 plan commit）
- Target HEAD: `d9a9edacfe610038e77c770ba43b63c0f613b549`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-aggregate-rereview-mimo.md`
- Included scope: 3 commits（S1 `e34edfa3`、S2 `5c8c11f8`、S3 `d9a9edac`）覆盖 5 个 owner paths + control doc + tests/README.md
- Excluded scope: production workflow（`.github/workflows/`）、root README、design docs、deferred issues
- Parallel review coverage: 无
- Review date/time: 2026-07-20T05:01:38+08:00

## Immutable target verification

| 锁定项 | 预期值 | Fresh 复算值 | 状态 |
|---|---|---|---|
| Base commit | `15979f5d32738148bf53daf9defe2dca59b8360c` | `15979f5d32738148bf53daf9defe2dca59b8360c` | ✓ |
| HEAD commit | `d9a9edacfe610038e77c770ba43b63c0f613b549` | `d9a9edacfe610038e77c770ba43b63c0f613b549` | ✓ |
| S1 commit | `e34edfa39f244d736aeaf8b9ea82ff9152698b2b` | `e34edfa39f244d736aeaf8b9ea82ff9152698b2b` | ✓ |
| S2 commit | `5c8c11f88fb0d935ad5730aa7d892ad26a060633` | `5c8c11f88fb0d935ad5730aa7d892ad26a060633` | ✓ |
| S3 commit | `d9a9edacfe610038e77c770ba43b63c0f613b549` | `d9a9edacfe610038e77c770ba43b63c0f613b549` | ✓ |
| Five-owner-path aggregate diff SHA-256 | `b22a8b2ef098986e5aab8066844732ee5c40a5e142ab95a0be7a00613fc93ab0` | `b22a8b2ef098986e5aab8066844732ee5c40a5e142ab95a0be7a00613fc93ab0` | ✓ |
| Zero-change artifact SHA-256 | `2033b173f29651181f773d049d8c0ab75fedc78541a6712c68fb4cc21e347061` | 已读取并核对内容 | ✓ |
| Controller validation SHA-256 | `0380677542e0edd9cdfd139f2f23aef9556da386b6ac7044d1ec9b9d351d4902` | 已读取并核对内容 | ✓ |

Commit chain 严格线性：S1 parent = plan base → S2 parent = S1 → S3 parent = S2。无分支、无 squash、无 rebase。

## Fresh 验证结果

所有 Python 命令均先执行 `source .venv/bin/activate`。

| 验证项 | 结果 |
|---|---|
| combined 105 owner tests（`pytest tests/cli/test_upload_filings_from_command.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py -x -q`） | `105 passed, 7 skipped, 3 warnings` |
| full pyright（`python -m pyright dayu/ tests/ utils/`） | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（4 个 owner Python files） | `All checks passed!` |
| full Ruff（`python -m ruff check dayu tests utils --output-format json`） | 142 条（与 baseline 一致，新增/扩散 0） |
| `git diff --check 15979f5d..d9a9edac` | 零输出；PASS |
| working-tree `git diff --check` | 零输出；PASS |
| `git diff --cached --check` / `git diff --cached --name-only` | 零输出；staged empty |
| aggregate binary diff SHA-256 重算 | 精确匹配锁值 |

7 个 skip 是 Darwin 上真实 Windows nodes 的预期平台事实；3 个 warning 来自既有 edgartools deprecated imports。二者均不关闭真实 Windows release gate。

## Review evidence chain

本轮从零完整读取以下证据链：

| 证据 | 结论 |
|---|---|
| S1 implementation（`wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`） | company-name 修正 + pre-execution oracle 实现 |
| S1 Controller validation（`wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`） | PASS |
| S1 code review MiMo/DS | 均 PASS / material finding 0 |
| S1 Controller adjudication | accepted finding 0 |
| S1 zero-change fix + Controller validation | PASS |
| S1 final re-review MiMo/DS | 均 PASS / material finding 0 |
| S1 final Controller adjudication | 关闭完整 S1 review 链 |
| S1 accepted-commit Controller validation | PASS / READY_FOR_WIN4_S2 |
| S2 implementation（`wu-semantic-ownership-01-ar-f07-win4-s2-implementation-codex.md`） | setx DEVNULL/close_fds/30s timeout/names truth |
| S2 Controller validation | PASS |
| S2 code review MiMo/DS | MiMo PASS/f0；DS PASS + 2 LOW candidate |
| S2 Controller adjudication | accepted 0 / rejected 2（CPython 证伪 + helper 覆盖） |
| S2 zero-change fix + Controller validation | PASS / rejected 零回流 |
| S2 final re-review MiMo/DS | 均 PASS / material finding 0 |
| S2 final Controller adjudication | 关闭完整 S2 review 链 |
| S2 accepted-commit Controller validation | PASS / READY_FOR_WIN4_S3 |
| S3 implementation（`wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md`） | anonymous handles / outer timeout / safe projection / canary |
| S3 Controller validation | PASS |
| S3 code review MiMo/DS | 均 PASS / material finding 0 |
| S3 Controller adjudication | accepted 0 |
| S3 zero-change fix + Controller validation | PASS |
| S3 final re-review MiMo/DS | 均 PASS / material finding 0 / backflow 0 |
| S3 final Controller adjudication | 关闭完整 S3 review 链 |
| S3 accepted-commit Controller validation | PASS / THREE_SLICES_LOCALLY_ACCEPTED |
| Aggregate deepreview MiMo（`wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-mimo.md`） | PASS / MATERIAL FINDING 0 |
| Aggregate deepreview DS（`wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-ds.md`） | PASS / MATERIAL FINDING 0 / NO BLOCKER |
| Aggregate Controller adjudication | accepted finding 0 / ZERO_CHANGE_CONFIRMATION_REQUIRED |
| AgentCodex zero-change fix（`wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-fix-codex.md`） | PASS / ZERO_CHANGE_CONFIRMED |
| Controller zero-change validation（`wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-fix-controller-validation.md`） | PASS / READY_FOR_DUAL_COMPLETE_AGGREGATE_REREVIEW |

全部 accepted/rejected/needs-evidence/design contradiction/local blocker/unclassified residual 均为 0。S2 的两项 rejected candidates（Python 3.11 patch-version 与笛卡尔积测试）零回流。

## Findings

未发现实质性问题。

以下为从零完整复核三 slice 组合行为和全部 evidence chain 的逐项结论：

### 1. S1 company-name oracle 与 production renderer 一致性

**审查路径**: `test_upload_filings_from_command.py` `_assert_single_windows_upload_company_name()` → `_parse_windows_batch_fixed_argv()` → `_decode_windows_batch_fixed_token()` → `_parse_single_windows_crt_argument()` → `dayu/cli/upload_script.py` `_quote_windows_batch_argument()` / `_render_windows_script()`

**结论**: 无冲突。

- S1 oracle 按 renderer 的 batch percent/caret 和 Windows CRT backslash/quote 语义逐 token 恢复 fixed argv。
- 生产 renderer 以 `^"` 包裹参数、`%%` doubling、`^` prefix metacharacters、CRT trailing-backslash 规则；oracle 独立逆向并经 7 种对抗 round-trip 验证。
- 真实 `cmd.exe /d /c` 执行 13 种对抗 fixed argv + 2 种 appended argv 通过，marker injection 零命中。
- Fins `upload_company_meta` 继续独占 fresh create/update 的 company-name 必填语义；CLI renderer 只机械投影，不推导默认值。
- S3 的 real CLI smoke 调用同一 `render_upload_script` 和同一 `_assert_single_windows_upload_company_name` oracle，不重新实现。
- `company_name_supplied=true` 从同一逐 token 断言结果产生，没有从 execution success 反推输入事实。

### 2. S2 setx DEVNULL/close_fds/30s timeout 与 S3 outer TemporaryFile/180s cleanup 职责不重复

**审查路径**: `init_environment.py` `_persist_windows_environment()` L417-450 → `test_init_smoke.py` `_run_init()` L585-670

**结论**: 无重复、无掩盖。

- **S2 inner layer**: `subprocess.run(("setx", ...), stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, close_fds=True, timeout=30.0)` — 每次单个 setx 调用的 30 秒 native timeout。Output 无消费者，不捕获。
- **S3 outer layer**: `subprocess.Popen(...)` + `tempfile.TemporaryFile` × 3（stdin/stdout/stderr）+ `process.wait(timeout=180)` — 整个 init 进程的 180 秒 outer timeout。Output 由 test 捕获并 strict UTF-8 解码。
- 两层 timeout 在不同粒度：inner per-setx-call（30s）先于 outer whole-process（180s）触发。若某次 setx 挂起，inner 30s 先捕获并返回 names-only partial failure；outer 180s 覆盖整个 init 进程的累积时间。
- S2 `TimeoutExpired` 收口路径（L437-438）与 `OSError` 收口路径（L439-440）共享 `_windows_failure_result` helper，只投影 written/unwritten names，不投影 raw argv 或 captured output。
- S3 timeout safe projection（`_render_init_timeout` L550-582）只投影 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，不投影 argv、paths、stdin 或 stdout/stderr content。
- S2 production constant `_WINDOWS_SETX_TIMEOUT_SECONDS`（L28）与 test constant `_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS`（L30）同值 `30.0`；test 不 import production constant 以保持 test fixture 独立性，这是合理的 test isolation 模式。

### 3. S3 canary 进入 real setx input 并在 CLI 前 fail closed

**审查路径**: `test_init_smoke.py` `_select_windows_test_canary()` L534-547 → `_github_actions_canary()` L516-531 → `test_windows_real_setx_round_trip_is_name_safe_and_cleaned()` → `test_github_actions_canary_freezes_domain_vector_determinism_and_shape()` → `test_github_actions_canary_fails_closed_without_random_fallback()`

**结论**: 闭环成立。

- `_select_windows_test_canary` 在 GitHub Actions 环境下通过 `_github_actions_canary(run_id)` 派生确定性 canary（`sk-dayu-test-` + 64 位 SHA-256 hex），不使用 `secrets.token_urlsafe` 随机回退。
- Domain bytes 冻结为 `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes，single NUL terminator），已知向量 `run_id="1"` 对应 `sk-dayu-test-b8f2210d...`。
- Owner test 精确冻结完整 domain bytes、single-NUL 事实、run id `1` 的 accepted known vector、determinism、canonicalization、不同 run id、prefix/digest shape。
- `test_github_actions_canary_fails_closed_without_random_fallback` 覆盖缺失 run_id、空 run_id、非十进制、零值、负值、全角数字 6 种非法输入，均在 CLI 前抛出 `AssertionError` 且不回退到 `secrets.token_urlsafe`。
- 真实 setx node 确实把选中的 canary 作为 CLI input 并验证 registry round-trip，同时不把值投影到 CLI stdout/stderr。
- Standalone R11 测试不注入 canary，不伪造 canary 证明；canary 注入只发生在 real-setx round-trip 测试中。

### 4. success/nonzero/OSError/Timeout/interrupt/env injection 组合覆盖

**审查路径**: `test_init_environment.py` 全部 Windows 测试 + `test_init_smoke.py` timeout/canary/UTF-8 测试

**结论**: 覆盖充分。

| Failure mode | S2 test | Status mapping |
|---|---|---|
| first nonzero | `test_windows_nonzero_...failure_at=0` | `FAILURE`（written_names=()） |
| middle nonzero | `test_windows_nonzero_...failure_at=1` | `PARTIAL_FAILURE`（written_names=(entries[0].name,)） |
| OSError at index 1 | `test_windows_os_error_...` | `PARTIAL_FAILURE` |
| Timeout at index 1 | `test_windows_timeout_...` | `PARTIAL_FAILURE` |
| interrupt at 0/1/2 | `test_windows_interrupt_...`（parametrize） | `INTERRUPTED` |
| all success + env injection | `test_windows_uses_argument_tuple_devnull_timeout_...` | `SUCCESS`，整批注入 |
| interrupt after all success | `test_windows_environment_injection_interrupt_...` | `INTERRUPTED`，written_names 全量 |

S3 额外覆盖：

| Scenario | Test |
|---|---|
| timeout→exited（cleanup completed） | `test_run_init_timeout_has_safe_projection_...`（4 parametrize cases） |
| timeout→kill→completed | 同上 |
| timeout→kill→timeout→running | 同上 |
| timeout→kill→timeout→exited | 同上 |
| strict UTF-8 invalid input | `test_run_init_strict_utf8_rejects_invalid_input_before_popen` |
| strict UTF-8 invalid output | `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels` |
| ordinary nonzero | `test_run_init_returns_ordinary_nonzero_as_typed_result` |

所有 timeout 测试验证 safe projection 不泄漏 sentinel、canary、workspace path、repository root、stdin/stdout/stderr content 或 raw `TimeoutExpired` material。`TimeoutExpired.raw_output` 探针确认 raw exception 包含敏感值（证明 timeout 确实发生在包含敏感数据的上下文中），但 safe projection 成功脱敏。

### 5. _SetxRecorder 严格签名覆盖完整 subprocess contract

**审查路径**: `test_init_environment.py` `_SetxRecorder.__call__()` L77-128 → `_SetxCall` L34-45 → `_expected_setx_call()` L131-149

**结论**: 完整覆盖。

- `_SetxCall` dataclass 精确记录 `args`、`shell`、`stdin`、`stdout`、`stderr`、`close_fds`、`text`、`check`、`timeout` 九个字段。
- `_SetxRecorder.__call__()` 签名要求传入所有九个参数，任何缺少/多余 kwargs（包括重新出现 `capture_output`）都会直接使 owner test 失败。
- `_expected_setx_call()` 构造预期值：`args=("setx", entry.name, entry.value)`、`shell=False`、三路 `DEVNULL`、`close_fds=True`、`text=False`、`check=False`、`timeout=30.0`。
- Timeout fake 使用含完整 raw argv/value 的 `subprocess.TimeoutExpired`。测试断言 value 与 raw argv repr 均不进入 result repr、stdout 或 stderr capture；结果只保留 already-confirmed/unconfirmed names，未声称 registry rollback。

### 6. README 与 workflow/contract 一致性

**审查路径**: `tests/README.md` diff

**结论**: 一致、不越界。

- 新增文本描述了两个已实现的行为：
  1. "`setx` persistence 调用的 native output 没有消费者，因此不由产品捕获"——与 S2 `DEVNULL` 实现一致。
  2. "real-init gate 的 outer CLI 仍通过 anonymous binary handles 捕获 stdout/stderr，并在 process 成功结束后 strict UTF-8 解码"——与 S3 `_run_init` 实现一致。
- Timeout projection 字段列表（`category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`、`process_state_after_cleanup_timeout`）与 `_render_init_timeout` 实现精确匹配。
- Artifact 约束（"可记录环境变量名，但不记录 stdin input value"）与 canary 脱敏行为一致。
- 未修改 workflow 文件、root README 或 design docs。

### 7. Semantic ownership / 过度设计 / Security

**结论**: 无漂移、无过度设计。

- **S1**: company-name oracle 解析逻辑 owner 是 `test_upload_filings_from_command.py` 的 `_assert_single_windows_upload_company_name` + `_parse_windows_batch_fixed_argv`。S3 通过函数调用复用，不重新实现。
- **S2**: setx subprocess contract owner 是 `init_environment._persist_windows_environment`。Test 通过 `_SetxRecorder` + `_SetxCall` dataclass 验证完整 contract，不使用 fallback 或 `hasattr`。
- **S3**: outer process timeout projection owner 是 `test_init_smoke._render_init_timeout`。Canary derivation owner 是 `_github_actions_canary` + `_WINDOWS_CANARY_DOMAIN`。两者都是单一 source of truth。
- Security: canary 只出现在 test trace / JUnit / registry query 中，不出现在 CLI stdout/stderr 或 artifact plaintext 中。Canary derivation 不使用 `secrets.token_urlsafe` 随机回退（GitHub Actions 路径）。Domain bytes 有 single NUL terminator 和 known vector 冻结。
- Config/Host internal SQLite/EventLog 按用户裁决属于同一本地 trusted domain；API key/headers 可存在于该 domain。Tool Trace 和 audit 不得泄露 API key 明文——本实现未修改 production，不涉及此边界。
- 未引入 secret infrastructure 或统一 tool authorization。
- Issue 142、151、175、177、178 及 Web/WeChat/render tracker 能力均未被实现。

### 8. Deferred issues 与 source/propagation scans

**结论**: 无新 deferred issue。

- Source scan: `_WINDOWS_CANARY_PREFIX`、`_WINDOWS_CANARY_DOMAIN`、`_WINDOWS_SETX_TIMEOUT_SECONDS` 只出现在各自 owner 模块中，无跨模块传播。
- `_WINDOWS_BATCH_HEADER_ORACLE`、`_WINDOWS_REGENERATION_PREFIX`、`_WINDOWS_RENDERED_COMMAND_SUFFIX`、`_WINDOWS_POST_COMMAND_LINES` 只出现在 S1 owner test 中，S3 通过函数调用复用 oracle 而不直接引用这些常量。
- `capture_output=True` 在 production owner 中零命中；`shell=True` / `errors=replace` 零命中；`communicate(` 在 smoke test 中零命中；`mkstemp`、`NamedTemporaryFile`、`CREATE_NEW_PROCESS_GROUP`、`JobObject`、`Start-Process`、`PowerShell` 在 S3 smoke 中零命中。
- `reg.exe` references 在 `test_init_smoke.py` 中是既有 registry cleanup/query owner，不是新增。
- Deferred-term scan（Issue 142/151/175/177/178、`web_tools_storage_states`）零命中。

### 9. Review findings 零回流验证

**结论**: 零回流。

- S2 的两项 rejected candidates（Python 3.11 `close_fds` patch-version 与异常分支/first-index 笛卡尔积测试）在 initial review 后被 Controller 以 CPython 官方文档和 failure helper 覆盖证伪拒绝，零回流到后续 gate。
- S3 的 reviewer observations（frame clearing、scripted output timing、renderer invariant、raw-timeout probe）均保持 observation/residual，没有 current action 或兼容工作。
- Aggregate initial review 的零 finding 保持到 zero-change confirmation 和本轮 re-review。
- 未发现从 rejected/observation 状态回流到 implementation 的代码或测试。

## Open Questions

无。

## Residual Risk

1. **真实 Windows 环境未验证**: 7 个 Windows-specific 测试在 local macOS 上被 skip。这些测试覆盖了 junction fail-closed、symlink privilege skip、workspace root identity drift、setx round-trip、四态 config reload 等关键行为。必须在 Windows runner 上通过后才能 release。

2. **S3 `_run_init` timeout path handle cleanup**: timeout 路径中 `stdout_handle.read()` 和 `stderr_handle.read()` 不会执行（`pytest.fail` 先抛出），但三个 `TemporaryFile` handles 由 `with` context manager 保证关闭。这是正确的，但 timeout 路径的 handle read count 断言只在 scripted test 中验证，real-init timeout 场景下 handle 内容被丢弃——这是设计意图（不读取可能包含敏感数据的 output），但值得在 Windows real smoke 中确认。

3. **Gemini low-budget**: 预期测试账号状态，不是代码 finding。用户裁决明确标记为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Verdict

`PASS / MATERIAL FINDING 0 / THREE_SLICES_AGGREGATE_REREVIEW_ACCEPTED`

## Material findings 严重度

无。

## Accepted chain backflow

无。S2 的两项 rejected candidates 零回流；S3 的 reviewer observations 零回流。Aggregate initial review → Controller adjudication → zero-change confirmation → Controller validation → 本轮 re-review 的完整链路中，accepted/rejected/needs-evidence/design contradiction/local blocker/unclassified residual 始终为 0。

## Local blocker

0。

## REAL_WINDOWS_PENDING_RELEASE_BLOCKER

7 个真实 Windows 测试（junction fail-closed、symlink privilege skip、workspace root identity drift、setx round-trip、四态 config reload、real R11 upload、real R12 init）在 local Darwin 上被 `platform.system() != "Windows"` gate skip。本地验证结果不关闭真实 Windows blocker。

Closure owner/destination 保持为 accepted aggregate evidence commit 并 push 后的 Controller remote gate：必须从本次 dispatch response 锁定唯一 R12 `run_id`，校验 workflow identity/path、event、branch/ref 与 accepted `head_sha`，对同一 run 的完整 log、JUnit、source hashes 与全部 downloaded artifacts 独立重算并扫描 canary。Standalone R11 继续按无 secret-input 与 artifact integrity 验收，不得伪称由 R12 canary scan 证明。
