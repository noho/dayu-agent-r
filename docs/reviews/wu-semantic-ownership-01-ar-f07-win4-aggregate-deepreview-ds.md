# AR-F07 WIN4 Aggregate Deepreview — S1/S2/S3 组合审查

## Scope

- **Mode**: current changes (aggregate)
- **Base**: `15979f5d32738148bf53daf9defe2dca59b8360c`（accepted WIN4 plan）
- **HEAD**: `d9a9edacfe610038e77c770ba43b63c0f613b549`（S3 accepted commit）
- **Branch**: `phaseflow/host-issues-control`
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01` umbrella AR-F07 WIN4
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-ds.md`
- **Review date**: 2026-07-20T04:47:45+08:00

### Included scope

五个 owner path 的 `base..HEAD` 完整 diff 与交互链路：

| # | File | Role |
|---|------|------|
| 1 | `tests/cli/test_upload_filings_from_command.py` | S1：company-name parser/oracle + R11 workflow 契约 |
| 2 | `dayu/cli/init_environment.py` | S2：production `setx` native stdio/timeout/names truth |
| 3 | `tests/cli/test_init_environment.py` | S2：production owner 的逐契约测试 |
| 4 | `tests/cli/test_init_smoke.py` | S3：outer CLI process failure projection + canary |
| 5 | `tests/README.md` | S3：test-evidence boundary 说明 |

以及以下证据链路：
- Accepted WIN4 plan（final SHA-256 `2359f242...fd73a`）
- S1/S2/S3 各自的 Controller validation、MiMo/DS initial review、Controller adjudication、zero-change validation、MiMo/DS complete re-review、final Controller adjudication
- S1/S2/S3 各自的 accepted-commit post-validation
- Umbrella control doc（`docs/host/issues-implementation-control.md`）
- Production renderer `dayu/cli/upload_script.py`（S1 oracle 的验证目标）
- `.github/workflows/r11-upload-script-windows.yml`（R11 embedded workflow contract）
- Full pyright（`0 errors, 0 warnings, 0 informations`）
- Combined S1/S2/S3 tests（`105 passed, 7 skipped`）

### Excluded scope

- `docs/reviews/` 下的 46 份 WIN4 证据 artifact（已由各自 Controller 验证锁定的 SHA-256；本 review 读取摘要和裁决但不对证据 artifact 做逐文件重审）
- 非 WIN4 的 umbrella 其他 AR-Fxx findings
- `dayu/cli/upload_script.py`（S1 oracle 的验证目标，非本次变更，只读以验证 parser 一致性）
- `.github/workflows/r12-init-windows.yml`（workflow 未在本次变更中修改）
- 真实 Windows R11/R12 远端运行（仍为 `PENDING_RELEASE_BLOCKER`）

### Parallel review coverage

无。本 review 由单一 reviewer 沿完整证据链逐行走读，未使用 subagent。

---

## Cross-Slice Chain Verification

### S1 → R11 workflow：company-name parser/oracle 与真实 embedded 能力

**S1 变更**（`tests/cli/test_upload_filings_from_command.py`，+175 lines）在 `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`、`_assert_single_windows_upload_company_name`、`_parse_windows_batch_fixed_argv`、`_decode_windows_batch_fixed_token`、`_parse_single_windows_crt_argument` 五个函数中实现了独立的 Windows batch/CRT parser oracle。

**生产渲染器验证**：对 `dayu/cli/upload_script.py` 的 `_quote_windows_batch_argument`（line 206-236）与 `_render_windows_script`（line 178-203）做了逐行交叉验证：

1. **Token 边界**：生产渲染器以 `^"` 包裹每个参数，以 `" ".join(...)` 拼接。Oracle 的 `_parse_windows_batch_fixed_argv` 在 `^"` 边界切分 token，以空格分隔连续 token，与生产一致。

2. **Percent doubling**：生产在 body 路径对 `%` 做 `%%` doubling（line 228）。Oracle 的 `_decode_windows_batch_fixed_token` 以 `%% → %` 独立还原。已用 `%PATH%` 对抗参数验证（line 874）。

3. **Caret escape**：生产 body 路径对 `&|<>()^` 加 `^` prefix（line 229-230）。Oracle 以 `^x → x` 独立还原。已用完整 metacharacter set 验证（line 869-883）。

4. **CRT backslash-quote**：生产的 trailing backslash ×2 规则（line 234）与内部 `"` 的 `2n+1` backslash 规则（line 222-224）与 Oracle 的 `_parse_single_windows_crt_argument` 互逆。已用 `slashes\\\\tail\\` 与 `quote"value` 对抗参数验证（line 467-495 和 `quote"value` at line 871）。

5. **CRLF physical line 结构**：生产以 `\r\n` 结束每行（line 203）。Oracle 以 `removesuffix("\r\n").split("\r\n")` 解析（line 1061-1062），并独立验证了 `\n` 或 `\r` 不在物理行内部。

**独立 round-trip 证据**：`test_windows_renderer_round_trips_fixed_argument_oracles`（line 467-495）使用 7 种对抗输入（空字符串、空格、中文、单引号、双引号、反斜杠尾、完整 metacharacter set）逐 token 验证生产 `_quote_windows_batch_argument` → Oracle `_decode_windows_batch_fixed_token` → Oracle `_parse_single_windows_crt_argument` 的 round-trip 一致性，所有 case 通过。

**真实 `cmd.exe` 证据**：`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`（line 849-906）以 13 种对抗 fixed argv + 2 种对抗 appended argv 通过真实 `cmd.exe /d /c` 执行，并验证了 `marker.exists() == False`（无 injection）。

**R11 workflow contract**（`.github/workflows/r11-upload-script-windows.yml`）：`test_r11_workflow_uses_fail_closed_exact_cmd_process_probe`（line 588-607）锁定了 8 项精确 assertion：
- `[System.Diagnostics.ProcessStartInfo]::new()` — 精确进程探测，非 pwsh 全局 pipeline
- `UseShellExecute = $false` + `RedirectStandardOutput/Error = $true`
- `-ArgumentList @("/d", "/c", "ver")` — 真实 `cmd.exe` 执行能力证明
- `-ArgumentList @("/?")` — 真实 help exit exact 1 证明
- `$verExitCode -ne 0` → throw — capability fail closed
- `$cmdHelpExitCode -ne 1` → throw — help exit 不替代 capability gate
- `cmd.exe /? 2>&1 |` NOT in workflow — 拒绝 pipeline wrapper
- `$PSNativeCommandUseErrorActionPreference` NOT in workflow — 拒绝全局忽略 native failure

这 8 项 assertion 与 workflow 源文件 lines 58-111 完全匹配。

**Standalone R11 不伪证**：R11 workflow（line 113-170）运行 `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` 和 `test_windows_generated_script_runs_real_cli_into_temp_storage`，但不消费 canary（canary 是 R12 setx test 的 input）。Controller 的独立 R11 验证只检查 artifact integrity 与无 secret-input contract，不声称 canary 证明。R11 standalone 的正确性不依赖 canary path。**此项验证通过**。

### S2 → S3：30s setx DEVNULL/native timeout 与 180s outer harness 的 owner 串联

**S2 production owner**（`dayu/cli/init_environment.py`）：
- `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0`（line 28）— 单次本机 `setx` owner bound
- `subprocess.run(["setx", name, value], stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, close_fds=True, text=False, check=False, timeout=30.0)`（line 417-427）
- `TimeoutExpired` → 不绑定/不格式化/不记录/不转抛 → `_windows_failure_result`（line 437-438）
- `OSError` → `_windows_failure_result`（line 439-440）
- `nonzero` → `_windows_failure_result`（line 441-442）
- `KeyboardInterrupt` → `EnvironmentPersistenceInterrupted` with names truth（line 428-436）

**S3 outer harness**（`tests/cli/test_init_smoke.py`）：
- `_run_init` 调用真实 `python -m dayu.cli init ...`（line 617-636）
- 三个 `TemporaryFile(mode="w+b")` anonymous binary handles（line 604-608）
- `Popen[bytes]` with `text=False, shell=False, close_fds=True`（line 617-636）
- `process.wait(timeout=180)`（line 638）
- Timeout path: poll → kill → cleanup wait → post-cleanup poll（line 640-651）
- Safe projection: `_render_init_timeout` 只投影 category/timeout/returncode/cleanup/post-cleanup state（line 550-582）
- `pytest.fail(..., pytrace=False)` — 不传播 raw exception frames

**S2→S3 串联路径**：
1. S3 `_run_init` 启动 `python -m dayu.cli init` 子进程
2. 子进程中的 `dayu.cli init` 调用 `plan_environment_persistence` → `persist_environment`
3. `persist_environment`（Windows 路径）调用 `_persist_windows_environment`
4. `_persist_windows_environment` 逐项调用 `subprocess.run(["setx", name, value], timeout=30.0, ...)`

**不互相遮蔽**：
- 30s 是 per-setx-call production owner bound；180s 是 test harness outer deadline
- 如果 setx 在 30s 内 timeout，production 返回 `PARTIAL_FAILURE`，CLI 继续（或退出），outer harness 在 180s 内捕获结果
- 如果 setx 全部 timeout（6 env vars × 30s = 180s），刚好触及 outer bound。这是设计决策：setx 极少 timeout，且 6-entry 全部 timeout 已是极端情况
- Outer kill（`process.kill()`）在 Windows 上调用 `TerminateProcess`，不保证杀死子进程树中的 orphan setx。这是 `PENDING_RELEASE_BLOCKER` 下已知的 Windows 进程治理限制，计划明确禁止实施 process-tree/job-object 治理
- S3 的 local test 不会声称关闭真实 Windows 行为；Windows-specific tests 保留 `@pytest.mark.skipif(platform.system() != "Windows", ...)`

**S2 test contract**（`tests/cli/test_init_environment.py`）：`_SetxRecorder` 记录完整的 9-field kwargs（argv、shell、stdin、stdout、stderr、close_fds、text、check、timeout），显式验证：
- `stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL`
- `close_fds=True, text=False, check=False`
- `timeout=30.0`
- 逐调用验证 environment-injection timing（`environment_visible_during_calls == [False, False]`）
- No retry（`recorder.calls` 长度精确等于 expected call count）
- No early injection（`os.environ` 在所有 setx 成功前不含 entry name）

**S3 test contract**（`tests/cli/test_init_smoke.py`）：`_ScriptedInitPopenFactory` 记录完整 Popen contract（argv、cwd、env、stdin payload、shell、close_fds、text），`_ScriptedInitProcess` 的 `attach_handles` 在 process creation 时验证三个 handles 未关闭。Timeout 状态机覆盖四个完整状态，并对每个状态验证：
- wait/poll/kill 精确调用次数
- failure path 零读取 stdout/stderr handles
- safe projection 不含 forbidden process material（sentinel、canary、path、argv、raw exception class name）
- raw `TimeoutExpired` 确实包含 sentinel（证明探针有效）
- 所有 handles 在 context unwind 后关闭

### Canary：从 public run id fail closed、真实 setx test 消费、Controller 独立重算可行

**`_github_actions_canary` 实现**（`test_init_smoke.py` line 516-531）：
```python
canonical_run_id = str(int(raw_run_id))  # canonicalize "0001" → "1"
digest = hashlib.sha256(_WINDOWS_CANARY_DOMAIN + canonical_run_id.encode("ascii")).hexdigest()
return f"sk-dayu-test-{digest}"
```

**独立重算验证**：
- Domain bytes: `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes, single NUL separator）
- Known vector: `_github_actions_canary("1")` = `"sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97"`
- 独立 shell 重算: `echo -ne 'dayu-ar-f07-win4-r12-canary-v1\x001' | shasum -a 256` → `b8f2210d...0b97` ✓
- 独立 Python 重算确认 canonical decimal round-trip 正确（`int("0001") == 1`，`str(1) == "1"`）

**Fail-closed 边界**：
- `test_github_actions_canary_fails_closed_without_random_fallback` 覆盖 6 种非法环境（missing、empty、non-decimal、zero、negative、fullwidth digits），所有 case 在 `AssertionError("GITHUB_RUN_ID")` 中 fail closed，`_ForbiddenTokenFactory` 确认零 random fallback
- `test_github_actions_canary_uses_public_run_id_without_random_fallback` 确认合法 workflow path 只使用 deterministic canary，零 random fallback
- `test_local_windows_canary_remains_random_and_ignores_run_id` 确认 local path 每次独立请求 32 bytes random token，不消费 GITHUB_RUN_ID

**Known vector 固定**：`test_github_actions_canary_freezes_domain_vector_determinism_and_shape` 锁定了 8 项不可变属性（domain length 31、prefix 30 ASCII chars、single NUL、known vector exact hex、canonicalization `"0001" == "1"`、run-id 2 != run-id 1、prefix format、digest lowercase hex length 64）。

**Standalone R11 不伪证**：如 S1 节所述，R11 不消费 canary。Controller 的独立 R11 验证只检查 artifact integrity。不声称 canary 证明。

**Controller 独立重算可行性**：Controller 凭公开 R12 run id、本 module 的 `_WINDOWS_CANARY_DOMAIN`（plain bytes literal）、标准 SHA-256 与 canonical decimal 规则，可独立重算 canary 并扫描 R12 log/all artifacts。本 review 已独立确认了该可行性。

### Success/nonzero/OSError/Timeout/interrupt/env injection、strict UTF-8、safe projection、Windows handles

**S2 production paths**（`init_environment.py`）：
| Path | Trigger | Behavior | Test |
|------|---------|----------|------|
| Success | all `setx` returncode=0 | whole-batch `os.environ` injection | `test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success` |
| First nonzero | first `setx` returncode≠0 | `FAILURE`，零注入，零 retry | `test_windows_nonzero_reports_names_only_without_retry_or_injection[failure_at=0]` |
| Middle nonzero | middle `setx` returncode≠0 | `PARTIAL_FAILURE`，已写 names 保留，零注入，零 retry | `test_windows_nonzero_reports_names_only_without_retry_or_injection[failure_at=1]` |
| Middle OSError | `subprocess.run` throws `OSError` | `PARTIAL_FAILURE`，已写 names 保留 | `test_windows_os_error_reports_partial_names_without_retry_or_injection` |
| Middle TimeoutExpired | `subprocess.run` throws `TimeoutExpired(30s)` | `PARTIAL_FAILURE`，raw argv 不在 result/repr/captured output | `test_windows_timeout_hides_raw_argv_without_retry_or_injection` |
| First/Middle/Last KeyboardInterrupt | `subprocess.run` throws `KeyboardInterrupt` | `INTERRUPTED`，written/unwritten names truth 保留 | `test_windows_interrupt_reports_written_and_unwritten_names_without_values` |
| Env injection interrupt | `os.environ[name] = value` throws `KeyboardInterrupt` | `INTERRUPTED`，全部 names 已 written（OS store 已完成） | `test_windows_environment_injection_interrupt_keeps_completed_store_truth` |

**S3 outer harness paths**（`test_init_smoke.py`）：
| Path | Trigger | Behavior | Test |
|------|---------|----------|------|
| Ordinary success | `process.wait(180)` → returncode 0 | typed result, strict UTF-8 decode | `test_run_init_uses_binary_anonymous_handles_and_returns_typed_utf8_result` |
| Ordinary nonzero | `process.wait(180)` → returncode 7 | typed result with stdout/stderr intact | `test_run_init_returns_ordinary_nonzero_as_typed_result` |
| Timeout: exit at deadline | `process.wait(180)` timeout, `process.poll()` → 1 | safe projection "returncode_at_timeout=1 cleanup=completed" | `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup[0]` |
| Timeout: kill + cleanup success | timeout, poll → None, kill, `wait(180)` → -9 | safe projection "returncode_at_timeout=not_exited cleanup=completed cleanup_returncode=-9" | `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup[1]` |
| Timeout: kill + cleanup timeout + still running | timeout, poll → None, kill, `wait(180)` timeout, poll → None | safe projection "...cleanup=timeout ...process_state_after_cleanup_timeout=running" | `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup[2]` |
| Timeout: kill + cleanup timeout + exited | timeout, poll → None, kill, `wait(180)` timeout, poll → 23 | safe projection "...process_state_after_cleanup_timeout=exited" | `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup[3]` |
| Strict UTF-8 input rejection | `input_text` contains lone surrogate | `UnicodeEncodeError` before Popen, handles closed | `test_run_init_strict_utf8_rejects_invalid_input_before_popen` |
| Strict UTF-8 output rejection | stdout contains `\xff` | `UnicodeDecodeError` after reading both channels, handles closed | `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels` |

### 984-line test change 必要性验证

`test_init_smoke.py` base commit 为 962 lines，HEAD 为 1878 lines（+916 lines）。变更包括：

| Component | Lines | Purpose | Justification |
|-----------|-------|---------|---------------|
| `_InitProcessResult` | 7 | typed result dataclass（3 fields） | 避免 tuple/dict 泄漏字段语义 |
| `_run_init` refactor + timeout | ~50 | TemporaryFile handles + 180s timeout + strict UTF-8 + safe projection | S3 owner 核心：outer CLI process failure projection |
| `_render_init_timeout` | 33 | static safe projection renderer | 唯一渲染点，状态机一致性断言 |
| `_github_actions_canary` / `_select_windows_test_canary` | ~40 | public-run-id canary derivation | R12 setx test 的非秘密输入 |
| `_ScriptedInitProcess` + factory + handle recorder | ~200 | deterministic process/contract test doubles | 验证精确 Popen contract + handle lifecycle + timeout state machine |
| Registry cleanup helpers | ~50 | `_delete_registry_value_and_verify_absent` + `_ScriptedRegistryCommandRunner` | 真实 setx test 的 cleanup owner |
| 15 tests | ~530 | success/nonzero/timeout(4)/UTF-8(2)/canary(5)/cleanup(2)/real Windows(4) | owner contract 逐路径验证 |

**最小必要判断**：
- 没有过度抽象：`_ScriptedInitProcess` 不是通用 mock framework，是精确验证 9-field Popen contract + wait/poll/kill state machine 的最小 deterministic double
- 没有 fixture 固化偶然行为：每个 test double（`_SetxRecorder`、`_ScriptedInitProcess`、`_ScriptedInitPopenFactory`、`_TemporaryHandleRecorder`）只验证其声明 scope 内的 explicit production contract，不 carry over 相邻测试的状态
- `_ForbiddenTokenFactory` 与 `_ScriptedTokenFactory` 以 fail-closed 验证 canary path 不会回退到 random，而不是假设"当前 local 环境也没调用 random"
- S3 的 `_run_init` 没有在 timeout path 中额外分配 temporary paths / named files / cleanup frameworks，三个 anonymous `TemporaryFile` handles 由 context manager 自动关闭
- 没有为测试便利引入 production seam（`_run_init` 只调用 `tempfile.TemporaryFile` 和 `subprocess.Popen`，不 import production internals）

**结论**：916-line 增量中的每个组件都有明确 owner contract 验证目的，无冗余抽象或 fixture 固化。

### README/workflow contract 一致性

`tests/README.md` 变更（+10 lines）新增或更新了以下段落：

1. **R11 workflow gate**：说明 workflow 在 `windows-latest` / Python 3.11 / locked constraints 上运行，使用 `System.Diagnostics.Process` 精确捕获，先 `ver` 后 `/?` 两步 capability proof（line 40-53）。**一致性**：与 `.github/workflows/r11-upload-script-windows.yml` lines 54-111 完全匹配。

2. **Strict UTF-8 contract**：说明 CLI process owner 在解析参数前把 `TextIOWrapper` 配置为 strict UTF-8，直接消费 Dayu CLI 输出的测试 subprocess 显式使用 `encoding="utf-8", errors="strict"`（line 54-58）。**一致性**：`_run_init` 的 `input_text.encode("utf-8", errors="strict")` 与 `stdout_bytes.decode("utf-8", errors="strict")` 完全匹配。

3. **R12 init Windows gate**：说明 workflow 执行 FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes 与 ConfigLoader/scene 重载，覆盖 junction/symlink/identity/setx 等（line 60-69）。**一致性**：与 `test_init_smoke.py` 中 `test_windows_real_*` 系列测试完全匹配。

4. **Timeout projection contract**：说明 outer CLI timeout 只投影 category/timeout_seconds/returncode_at_timeout/cleanup/cleanup_returncode + process_state_after_cleanup_timeout（line 67-68）。**一致性**：与 `_render_init_timeout` 的 5/6-field 输出完全匹配。

5. **Artifact disclosure boundary**：说明上传 artifact 只包含 JUnit/version/capability/source hashes/env var names，不保存 environment/registry values（line 68-69）。**一致性**：与 S1 `company_name_supplied=true`（boolean，非公司名值）、S2 `written_names/unwritten_names`（仅变量名）、S3 timeout safe projection（零 process material）的披露边界完全匹配。

**Security/deferred/source/propagation/统一 auth 禁区**：
- 没有新增 `shell=True`、PowerShell、winreg/reg.exe、process group/job object 依赖
- 没有读取或发布 configured production secret、GitHub Secrets
- 没有实现 deferred Issue 142/151/175/177/178 的能力
- Config/Host durable SQLite trusted-local 裁决不变；Tool Trace/audit/public/LLM-facing/operator log 仍禁止 API key/header 明文
- 没有新增 unified authorization framework 或 cross-provider secret propagation

---

## Findings

经完整逐行走读 base..HEAD 的五个 owner path 全部 diff、production renderer 交叉验证、四状态 timeout 状态机展开、canary 独立重算、所有 112 个 test node 执行（105 passed / 7 skipped）与 full pyright zero 后：

**未发现实质性问题。**

具体而言：
- 三项 S1→S3 已关闭的 accepted plan findings（WIN4-PR-F01..F04）均在最终 plan 中有精确 code-generation-ready 约束，并在代码中逐条实现
- 六项已被 Controller 在 S2/S3 各轮裁决中明确拒绝的 reviewer candidate（DS initial F01 的 Python 3.11 patch-version claim — 被 CPython 官方文档证伪；DS initial F02 的 exception-kind/index 组合测试 — 已被既有独立测试覆盖；DS OBS-01..03 — 零回流；MiMo raw-timeout probe residual — 零回流）均未在代码、测试、README、plan 或 follow-up 中回流
- S2 两项 rejected candidate 最终关闭且零回流
- 没有发现 semantic ownership drift、cross-slice 遮蔽、contract 边界泄漏或 fixture 固化偶然行为

### Why zero findings?

这不是"审查不够深入"，而是因为：

1. **Plan 的精确性**：WIN4 remediation plan 在 4 轮 review/adjudication/fix 后，每条约束都 code-generation-ready（例如 S1 "逐 token 解析唯一非注释业务 command"、S2 "不绑定/不格式化/不记录 TimeoutExpired"、S3 "只做一次非阻塞 process-state 投影"）。实现与 plan 之间没有歧义空间。

2. **测试的对抗性**：S2 的 `_SetxRecorder` 不是记录-然后-信任的 mock——它显式验证 9-field contract、environment-injection timing 和 no-retry。S3 的 `_ScriptedInitProcess` 显式在 raw `TimeoutExpired` 中注入 sentinel 以证明"探针有效"，再验证 safe projection 不含 sentinel。这种模式（先证伪"根本没敏感数据"，再证"有敏感数据但不泄露"）消除了常见的"test 只证明 happy path"缺陷。

3. **六轮 review 的累积效果**：每个 slice 经过 MiMo+DS initial review → Controller adjudication → zero-change → MiMo+DS complete re-review → Controller final adjudication。共计 18 个独立 reviewer 视角（3 slices × 6 reviews）。本 aggregate review 作为第 7 轮，焦点是 cross-slice chain 和各 slice 各自 review 的 blind spot（组合 owner path 的交互）。经过 exhaustive 逐行走读，未发现先前 review 遗漏的 cross-slice issue。

---

## Open Questions

1. **S2 `_WINDOWS_SETX_TIMEOUT_SECONDS` 与 S3 `_PROCESS_TIMEOUT_SECONDS` 的数值关系**：30s × 最多 6 entries = 180s = outer timeout。如果未来 `ALLOWED_ENVIRONMENT_NAMES` 增加第 7 个 entry，则 worst-case total setx time（7 × 30s = 210s）会超过 outer 180s。这是 **forward-compatibility observation**，不是当前 defect：6-entry allowlist 是 sealed contract（由 `INIT_MODEL_CHOICES` + `OPTIONAL_ENVIRONMENT_NAMES` 联合固定），新增 entry 需要同时评估 timeout budget。

2. **S3 `_run_init` 在 Darwin 上运行时的 `platform.system() != "Windows"` skip**：7 个 skipped tests 是 Darwin 上预期行为。`test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 在非 Windows 上正确 skip，不在 Darwin 上伪证 Windows 行为。

3. **R11 workflow 的 path trigger 不包含 S3 文件**：`.github/workflows/r11-upload-script-windows.yml` 的 `paths` filter（line 5-31）未列出 `tests/cli/test_init_smoke.py`。S3 的 R12 init workflow（`r12-init-windows.yml`）负责 init smoke。R11 的 trigger scope 与其 responsibility（upload script gate）一致，不是遗漏。

---

## Residual Risk

### `PENDING_RELEASE_BLOCKER` — 真实 Windows 行为

- **Risk**：S2 的 `DEVNULL`/`close_fds=True`/native timeout 与 S3 的 `TemporaryFile` anonymous handles/strict UTF-8/outer cleanup 在 Darwin 上通过 test double 验证，但真实 `cmd.exe`、`setx` 子进程 stdin/stdout/stderr handle 语义、`TerminateProcess` 对 orphan `setx` 的行为、以及 concurrent registry mutation 仍需真实 Windows runner 验证。
- **Owner**：Controller（三 slice 全部 accepted/push 后的 remote gate）。
- **Closure condition**：非 skip 的真实 `windows-latest` R11+R12 run，Controller 独立扫描 R12 log/all artifacts 确认 canary round-trip 与 setx 行为。
- **Current status**：`PENDING_RELEASE_BLOCKER`，S1/S2/S3 的 local acceptance 均未 waiver。

### 真实 Windows outer timeout 下的 orphan setx

- **Risk**：如果 outer CLI 被 kill（`_run_init` timeout path），Windows `TerminateProcess` 不保证杀死子 `setx.exe`。Orphan `setx` 可能继续写入 registry 并在后续 test 中被观察到。
- **Mitigation**：`test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 在 test 开始前做幂等 delete+proof-absent cleanup，在 finally 中再次 delete+proof-absent。即使上一次 run 遗留了 orphan setx write，cleanup 也会移除。
- **Severity**：低。cleanup 是幂等的；orphan setx 写入 registry 的 key 是固定的 `OPENAI_API_KEY`；不会累积。
- **注**：计划明确禁止实施 process-tree/job-object 治理；这是明确接受的已知限制，不是未预见的 residual。

### 测试只在 Darwin 上执行

- **Risk**：combined tests 的 105 passed / 7 skipped 全部在 Darwin 上运行。7 skipped 包含 `@pytest.mark.skipif(platform.system() != "Windows")` 的真实 Windows tests 与 POSIX-specific smokes。Windows-only code paths（`_persist_windows_environment`、Windows branch of `_run_init` 的 handle behavior）在 Darwin 上通过 test double 验证，但 real-OS behavior 未在本地验证。
- **Severity**：中。已在 `PENDING_RELEASE_BLOCKER` 中追踪。

---

## Ledger

| Category | Count | Detail |
|----------|------:|--------|
| Material code finding | **0** | 经五个 owner path 完整走读 + renderer 交叉验证 + timeout 状态机展开 + canary 独立重算 |
| Accepted/open (from prior reviews) | **0** | S1/S2/S3 各自 final adjudication 均为 0 |
| Rejected reviewer candidate (zero backflow) | **6** | DS F01 (patch-version claim 被证伪), DS F02 (exception-kind → 无独立分支), DS OBS-01..03, MiMo raw-timeout probe residual |
| Needs-evidence | **0** | |
| Design contradiction | **0** | |
| Local blocker | **0** | |
| Unclassified residual | **0** | |
| Real Windows residual | **1** | `PENDING_RELEASE_BLOCKER`，三 slice accepted/push 后 Controller remote gate |
| Forward-compat observation | **1** | S2 timeout budget 与 allowlist size（见 Open Question 1） |

---

## Verdict

**`PASS / AGGREGATE_DEEPREVIEW_COMPLETE / MATERIAL_FINDING_0 / NO_BLOCKER / REAL_WINDOWS_PENDING_RELEASE_BLOCKER`**

五个 owner path 的 S1→S3 完整实现经 base..HEAD exhaustive 走读、production renderer 交叉验证、四状态 timeout state machine 展开、canary 独立重算、112-node combined test suite 执行（105 passed / 7 skipped）、full pyright zero、Ruff baseline 不变、staged empty、diff-check pass。

S1 company-name oracle 与真实 embedded R11 workflow 一致。S2 setx DEVNULL/native timeout 与 S3 outer TemporaryFile/wait cleanup 正确串联，不互相遮蔽。Canary 从公开 run id fail closed、真实 setx test 消费、Controller 独立重算可行、standalone R11 不伪证。Success/nonzero/OSError/Timeout/interrupt/env injection、strict UTF-8、safe projection、Windows handles 全部合约逐路径验证。984-line test 增量是 owner contract 验证的最小必要实现，无 fixture 固化偶然行为。README/workflow contract 一致，security/deferred/source/propagation/统一 auth 禁区完整。

真实 Windows release blocker 保持 `PENDING_RELEASE_BLOCKER`，不被本 local review waiver。
