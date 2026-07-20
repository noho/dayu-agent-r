# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `15979f5d32738148bf53daf9defe2dca59b8360c`（accepted WIN4 plan commit）
- Target HEAD: `d9a9edacfe610038e77c770ba43b63c0f613b549`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-mimo.md`
- Included scope: 3 commits（S1 `e34edfa3`、S2 `5c8c11f8`、S3 `d9a9edac`）覆盖 5 个 owner paths + control doc + tests/README.md
- Excluded scope: production workflow（`.github/workflows/`）、root README、design docs、deferred issues
- Parallel review coverage: 无

## Commit chain

| Commit | Message | Parent |
|---|---|---|
| `e34edfa3` | `test: accept AR-F07 WIN4 S1 remediation` | `15979f5d`（plan） |
| `5c8c11f8` | `fix: accept AR-F07 WIN4 S2 remediation` | `e34edfa3`（S1） |
| `d9a9edac` | `test: accept AR-F07 WIN4 S3 remediation` | `5c8c11f8`（S2） |

## Owner paths reviewed

| Path | Slice | Role |
|---|---|---|
| `tests/cli/test_upload_filings_from_command.py` | S1 | company-name script oracle |
| `dayu/cli/init_environment.py` | S2 | setx native contract owner |
| `tests/cli/test_init_environment.py` | S2 | setx owner contract tests |
| `tests/cli/test_init_smoke.py` | S3 | outer process harness + canary |
| `tests/README.md` | S3 | owner boundary documentation |
| `docs/host/issues-implementation-control.md` | all | control doc |

## Verification results

| Check | Result |
|---|---|
| `pytest tests/cli/test_upload_filings_from_command.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py -x -q` | `105 passed, 7 skipped`（7 skip 均为 `platform.system() != "Windows"` gate） |
| `pyright`（4 个 owner paths） | `0 errors, 0 warnings, 0 informations` |
| `ruff check`（4 个 owner paths + tests/README.md） | `All checks passed!` |
| `git diff --check 15979f5d..d9a9edac` | 通过，无 whitespace 错误 |

## Findings

未发现实质性问题。

以下为组合故障点的逐项 evidence-based 审查结论：

### 1. S1 company-name script oracle 与 S3 真实 R11 embedded 路径一致性

**审查路径**: `test_upload_filings_from_command.py` `_assert_single_windows_upload_company_name()` → `_parse_windows_batch_fixed_argv()` → `_decode_windows_batch_fixed_token()` → `_parse_single_windows_crt_argument()`

**结论**: 无冲突。

- S1 oracle 通过 `upload_script.render_upload_script()` 生成 batch 内容并解析验证。
- S3 的 `test_windows_generated_script_runs_real_cli_into_temp_storage` 调用同一 `render_upload_script` 生成真实 CLI script，然后调用同一 `_assert_single_windows_upload_company_name` oracle。
- renderer 产出的 `^"token" %*` 格式由 `_parse_windows_batch_fixed_argv` 按 batch percent/caret 与 Windows CRT 语义正确解析。
- S1 负面测试覆盖了无 company-name、错误 command type、多条业务命令、重复 `--company-name` 等场景，parser 均正确拒绝。
- Oracle 返回 `bool` 供 S3 artifact 同源记录，不产生额外 owner。

### 2. S2 setx DEVNULL/30s timeout 与 S3 outer TemporaryFile/180s cleanup 职责不重复

**审查路径**: `init_environment.py` `_persist_windows_environment()` L417-438 → `test_init_smoke.py` `_run_init()` L604-670

**结论**: 无重复、无掩盖。

- **S2 inner layer**: `subprocess.run(("setx", ...), stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, close_fds=True, timeout=30.0)` — 每次单个 setx 调用的 30 秒 native timeout。Output 无消费者，不捕获。
- **S3 outer layer**: `subprocess.Popen(...)` + `tempfile.TemporaryFile` × 3（stdin/stdout/stderr）+ `process.wait(timeout=180.0)` — 整个 init 进程的 180 秒 outer timeout。Output 由 test 捕获并 strict UTF-8 解码。
- 两层 timeout 在不同粒度：inner per-setx-call（30s）先于 outer whole-process（180s）触发。若某次 setx 挂起，inner 30s 先捕获并返回 names-only partial failure；outer 180s 覆盖整个 init 进程的累积时间。
- S2 `TimeoutExpired` 收口路径（L437-438）与 `OSError` 收口路径（L439-440）共享 `_windows_failure_result` helper，只投影 written/unwritten names，不投影 raw argv 或 captured output。
- S3 timeout safe projection（`_render_init_timeout` L550-582）只投影 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`，不投影 argv、paths、stdin 或 stdout/stderr content。

### 3. S3 canary 进入 real setx input 并在 CLI 前 fail closed

**审查路径**: `test_init_smoke.py` `_select_windows_test_canary()` L534-547 → `test_windows_real_setx_round_trip_is_name_safe_and_cleaned()` L1830-1865 → `test_github_actions_canary_freezes_domain_vector_determinism_and_shape()` L1021-1041 → `test_github_actions_canary_fails_closed_without_random_fallback()` L1070-1091

**结论**: 闭环成立。

- `_select_windows_test_canary` 在 GitHub Actions 环境下通过 `_github_actions_canary(run_id)` 派生确定性 canary（`sk-dayu-test-` + 64 位 SHA-256 hex），不使用 `secrets.token_urlsafe` 随机回退。
- `test_windows_real_setx_round_trip_is_name_safe_and_cleaned`（L1830）将 canary 作为 `OPENAI_API_KEY` 的值注入真实 setx，然后：
  - 断言 canary 出现在 `reg.exe query` 输出（证明 setx 写入成功）
  - 断言 canary 不出现在 CLI stdout/stderr（证明脱敏成立）
- Domain bytes 冻结为 `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes，single NUL terminator），已知向量 `run_id="1"` 对应 `sk-dayu-test-b8f2210d...`。
- `test_github_actions_canary_fails_closed_without_random_fallback` 覆盖缺失 run_id、空 run_id、非十进制、零值、负值、全角数字 6 种非法输入，均在 CLI 前抛出 `AssertionError` 且不回退到 `secrets.token_urlsafe`。
- `test_github_actions_canary_uses_public_run_id_without_random_fallback` 验证合法路径（run_id="0001" canonicalization）不触发随机回退。
- Standalone R11 测试（`test_windows_generated_script_runs_real_cli_into_temp_storage`）不注入 canary，不伪造 canary 证明；canary 注入只发生在 real-setx round-trip 测试中。

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

- 所有 timeout 测试验证 safe projection 不泄漏 sentinel、canary、workspace path、repository root、stdin/stdout/stderr content 或 raw `TimeoutExpired` material。
- `TimeoutExpired.raw_output` 探针确认 raw exception 包含敏感值（证明 timeout 确实发生在包含敏感数据的上下文中），但 safe projection 成功脱敏。

### 5. README 与 workflow 合同一致性

**审查路径**: `tests/README.md` diff

**结论**: 一致、不越界。

- 新增文本描述了两个已实现的行为：
  1. "`setx` persistence 调用的 native output 没有消费者，因此不由产品捕获"——与 S2 `DEVNULL` 实现一致。
  2. "real-init gate 的 outer CLI 仍通过 anonymous binary handles 捕获 stdout/stderr，并在 process 成功结束后 strict UTF-8 解码"——与 S3 `_run_init` 实现一致。
- Timeout projection 字段列表（`category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、`cleanup_returncode`、`process_state_after_cleanup_timeout`）与 `_render_init_timeout` 实现精确匹配。
- Artifact 约束（"可记录环境变量名，但不记录 stdin input value"）与 canary 脱敏行为一致。
- 未修改 workflow 文件、root README 或 design docs。

### 6. Semantic ownership / 过度设计 / Security

**结论**: 无漂移、无过度设计。

- **S1**: company-name oracle 解析逻辑 owner 是 `test_upload_filings_from_command.py` 的 `_assert_single_windows_upload_company_name` + `_parse_windows_batch_fixed_argv`。S3 通过函数调用复用，不重新实现。
- **S2**: setx subprocess contract owner 是 `init_environment._persist_windows_environment`。Test 通过 `_SetxRecorder` + `_SetxCall` dataclass 验证完整 contract（argv、shell、stdin、stdout、stderr、close_fds、text、check、timeout），不使用 fallback 或 `hasattr`。
- **S3**: outer process timeout projection owner 是 `test_init_smoke._render_init_timeout`。Canary derivation owner 是 `_github_actions_canary` + `_WINDOWS_CANARY_DOMAIN`。两者都是单一 source of truth。
- `_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS`（test constant）与 `_WINDOWS_SETX_TIMEOUT_SECONDS`（production constant）同值 `30.0`；test 不 import production constant 以保持 test fixture 独立性，这是合理的 test isolation 模式。
- Security: canary 只出现在 test trace / JUnit / registry query 中，不出现在 CLI stdout/stderr 或 artifact plaintext 中。Canary derivation 不使用 `secrets.token_urlsafe` 随机回退（GitHub Actions 路径）。Domain bytes 有 single NUL terminator 和 known vector 冻结。

### 7. Deferred issues 与 source/propagation scans

**结论**: 无新 deferred issue。所有 Windows 真实环境测试仍由 `platform.system() != "Windows"` gate skip，这是正确的：真实 Windows 行为只能在 Windows runner 上验证，local skip PASS 不代表通过。

- Control doc 正确记录 `PENDING_RELEASE_BLOCKER` 状态。
- Source scan: `_WINDOWS_CANARY_PREFIX`、`_WINDOWS_CANARY_DOMAIN`、`_WINDOWS_SETX_TIMEOUT_SECONDS` 只出现在各自 owner 模块中，无跨模块传播。
- `_WINDOWS_BATCH_HEADER_ORACLE`、`_WINDOWS_REGENERATION_PREFIX`、`_WINDOWS_RENDERED_COMMAND_SUFFIX`、`_WINDOWS_POST_COMMAND_LINES` 只出现在 S1 owner test 中，S3 通过函数调用复用 oracle 而不直接引用这些常量。

## Open Questions

无。

## Residual Risk

1. **真实 Windows 环境未验证**: 7 个 Windows-specific 测试在 local macOS 上被 skip。这些测试覆盖了 junction fail-closed、symlink privilege skip、workspace root identity drift、setx round-trip、四态 config reload 等关键行为。必须在 Windows runner 上通过后才能 release。
2. **S3 `_run_init` timeout path handle cleanup**: timeout 路径中 `stdout_handle.read()` 和 `stderr_handle.read()` 不会执行（`pytest.fail` 先抛出），但三个 `TemporaryFile` handles 由 `with` context manager 保证关闭。这是正确的，但 timeout 路径的 handle read count 断言（`stdout_handle.read_count == 0`）只在 scripted test 中验证，real-init timeout 场景下 handle 内容被丢弃——这是设计意图（不读取可能包含敏感数据的 output），但值得在 Windows real smoke 中确认。

## Verdict

`PASS / MATERIAL FINDING 0 / THREE_SLICES_AGGREGATE_ACCEPTED`

WIN4-S1、S2、S3 三 slice 组合无实质性问题。跨 slice 依赖（S1 oracle → S3 real CLI、S2 contract → S3 outer harness）通过函数复用而非重复实现保持一致。所有 owner paths 通过 pytest（105 passed / 7 skipped）、pyright（0 errors）、ruff 和 git diff --check。真实 Windows 环境验证仍为 release closure gate。
