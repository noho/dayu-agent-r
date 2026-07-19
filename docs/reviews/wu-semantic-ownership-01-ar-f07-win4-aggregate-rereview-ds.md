# AR-F07 WIN4 Aggregate Re-Review — AgentDS 第二路完整重审

## Scope

- **Mode**: aggregate re-review（current changes，五 owner path base..HEAD）
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01` umbrella AR-F07 WIN4 continuation
- **Role**: AgentDS — 双路 complete aggregate re-review 第二路
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `15979f5d32738148bf53daf9defe2dca59b8360c`（accepted WIN4 plan commit）
- **Target HEAD**: `d9a9edacfe610038e77c770ba43b63c0f613b549`（S3 accepted commit）
- **Accepted commit chain**: S1 `e34edfa3` → S2 `5c8c11f8` → S3 `d9a9edac`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-aggregate-rereview-ds.md`
- **Review date**: 2026-07-20T05:06:37+08:00

### Included scope

五个 owner path 的完整 `base..HEAD` diff、跨 slice 依赖链、证据链一致性：

| # | File | Slice | Role |
|---|------|-------|------|
| 1 | `tests/cli/test_upload_filings_from_command.py` | S1 | company-name parser/oracle + R11 workflow 契约 |
| 2 | `dayu/cli/init_environment.py` | S2 | production `setx` native stdio/timeout/names truth |
| 3 | `tests/cli/test_init_environment.py` | S2 | production owner 的逐契约测试 |
| 4 | `tests/cli/test_init_smoke.py` | S3 | outer CLI process failure projection + canary |
| 5 | `tests/README.md` | S3 | test-evidence boundary 说明 |

检查的证据链路：

- Accepted WIN4 plan（final SHA-256 `2359f242...fd73a`）— 673 lines / 45,818 bytes
- S1/S2/S3 各自的 Controller validation、MiMo/DS initial review、Controller adjudication、zero-change validation、MiMo/DS complete re-review、final Controller adjudication、accepted-commit post-validation
- 本轮 aggregate MiMo 初审（SHA-256 `a3239c2b...d5ad`）
- 本轮 aggregate DS 初审（SHA-256 `469a8001...5730`）
- 本轮 aggregate Controller adjudication（SHA-256 `81146c0a...6731`）
- 本轮 aggregate AgentCodex zero-change fix（SHA-256 `2033b173...7061`）
- 本轮 aggregate Controller validation（SHA-256 `03806775...4902`）
- Umbrella control doc（`docs/host/issues-implementation-control.md`）
- Production renderer `dayu/cli/upload_script.py`（S1 oracle 的验证目标）
- S1→S3 完整 38 个变更文件（5 个 owner path + 33 个 review/evidence artifact）

### Excluded scope

- 33 份 WIN4 evidence artifact（已由各自 Controller 验证锁定的 SHA-256；本 review 读取摘要和裁决但不对证据 artifact 做逐文件重审）
- 非 WIN4 的 umbrella 其他 AR-Fxx findings
- `.github/workflows/` 下的 R11/R12 workflow 文件（非本次变更，只读以验证 contract 一致性）
- 真实 Windows R11/R12 runner（仍为 `PENDING_RELEASE_BLOCKER`）
- 根 README、design docs、deferred issues

### Parallel review coverage

无。本 review 由单一 reviewer 沿完整证据链逐行走读，未使用 subagent。

---

## Immutable Target Verification

### Base/HEAD/commit chain

```text
15979f5d → e34edfa3 (S1: test) → 5c8c11f8 (S2: fix) → d9a9edac (S3: test / target HEAD)
```

严格线性 parent chain，无 merge、无 rebase、无 squash。

### Five-owner-path aggregate binary diff SHA-256

```text
git diff 15979f5d..d9a9edac -- tests/cli/test_upload_filings_from_command.py \
  dayu/cli/init_environment.py tests/cli/test_init_environment.py \
  tests/cli/test_init_smoke.py tests/README.md | shasum -a 256
```

结果：`b22a8b2ef098986e5aab8066844732ee5c40a5e142ab95a0be7a00613fc93ab0`，与 Controller 锁值精确一致。

### Zero-change artifact SHA-256

AgentCodex zero-change fix artifact：`2033b173f29651181f773d049d8c0ab75fedc78541a6712c68fb4cc21e347061`，与 Controller validation 锁值一致。

### Controller validation SHA-256

`0380677542e0edd9cdfd139f2f23aef9556da386b6ac7044d1ec9b9d351d4902`，已独立确认。

---

## Fresh Verification Results

所有命令均先执行 `source .venv/bin/activate`。

### Combined 105 owner tests

```text
pytest tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_init_environment.py tests/cli/test_init_smoke.py -x -q
```

| Metric | Result |
|--------|--------|
| Passed | **105** |
| Skipped | **7**（均为 `platform.system() != "Windows"` gate） |
| Warnings | **3**（既有 edgartools deprecated imports，非本次 diff） |
| Duration | 27.29s |

7 个 skip 是 Darwin 上真实 Windows nodes 的预期平台事实，不关闭也不削弱真实 Windows release gate。

### Full pyright

```text
python -m pyright dayu/ tests/ utils/
```

`0 errors, 0 warnings, 0 informations`

### Scoped Ruff

```text
python -m ruff check tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_init_environment.py tests/cli/test_init_smoke.py \
  dayu/cli/init_environment.py
```

`All checks passed!`

### Diff, staged, and status

| Check | Result |
|-------|--------|
| `git diff --check 15979f5d..d9a9edac` | 零输出，PASS |
| `git diff --check` (worktree) | 零输出，PASS |
| `git diff --cached --name-only` | 零输出（staged empty） |

Working tree dirty paths 仅为既有 control doc modification 与 untracked review artifacts（含本轮 aggregate 初审与 zero-change 链路），属于用户/Controller 受保护输入，未被本 gate 修改、格式化或 stage。

### Security and deferred boundary scans

| Scan | Target files | Expected | Actual |
|------|-------------|----------|--------|
| `capture_output=True` | `init_environment.py` | 零命中 | 零命中 ✓ |
| `shell=True` / `errors=replace` | `init_environment.py`, `test_init_smoke.py` | 零命中 | 零命中 ✓ |
| `winreg`/`reg.exe`/`PowerShell`/`Start-Process`/`CREATE_NEW_PROCESS_GROUP`/`JobObject` | 四个 Python owner path | `reg.exe` 仅限测试验证/清理 helper | `reg.exe` 仅出现在 `_run_reg_command`、`_delete_registry_value_and_verify_absent`、`_verify_registry_value_absent` 和 docstring 中 ✓ |
| Issue 142/151/175/177/178 / `web_tools_storage_states` | 四个 Python owner path | 零命中 | 零命中 ✓ |

`reg.exe` 匹配均为 test-verification helper 中用于验证 setx 写入 registry 和清理 registry value——这是计划明确允许的。生产代码不使用 `winreg`/`reg.exe`/`PowerShell`/process group/job object。未读取 GitHub Secrets 或 configured production values。

### Independent canary recalculation

```text
Domain: b"dayu-ar-f07-win4-r12-canary-v1\x00" (31 bytes, last byte = 0x00 single NUL)
run_id canonicalization: str(int(raw_run_id))
Digest: SHA-256(domain + canonical_run_id.encode("ascii")).hexdigest()
Known vector: run_id="1" → sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97
```

独立重算确认：domain length 31、last byte 0、已知向量匹配、run-id canonicalization 正确（`"1"` = `"0001"` → `"1"`）。

### Known canary vector test

`test_github_actions_canary_freezes_domain_vector_determinism_and_shape` 的 8 项 assertion（domain length 31、prefix 30 ASCII chars、single NUL、known vector exact hex、canonicalization、run-id 2 != run-id 1、prefix format、digest lowercase hex length 64）均通过。

---

## Findings

### 经完整逐行走读后：未发现实质性问题。

以下为逐项 evidence-based 审查结论，重点覆盖本指令指定的审查重点。

---

### 1. S1 company-name oracle — 完整验证

**审查路径**：`test_upload_filings_from_command.py` → `_assert_single_windows_upload_company_name()` → `_parse_windows_batch_fixed_argv()` → `_decode_windows_batch_fixed_token()` → `_parse_single_windows_crt_argument()`

**S1 变更内容**（+175 lines）：

1. **`_WINDOWS_REAL_SMOKE_COMPANY_NAME: Final[str] = "Apple Inc."`**（line 57）：唯一常量（非从 ticker/FMP/storage 推导）。

2. **`test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`**（line 494-564）：4 种无效输入（零条命令、错误 command type `upload_material`、两条 `upload_filing` 命令、重复 `--company-name` token），全部在 `pytest.raises(AssertionError)` 中正确拒绝。

3. **`_assert_single_windows_upload_company_name`**（line 1042-1095）：CRLF 结构验证、固定 header oracle（`@echo off`/`chcp 65001 >nul`/`setlocal DisableDelayedExpansion`）、恰好一个 regeneration comment + 一个 business line + 两个 post-command lines（`if errorlevel 1 exit /b %errorlevel%`/`exit /b 0`）、逐 token 解析唯一非注释 business command、断言恰好一个 `--company-name` 且下一 token 等于 `Apple Inc.`。

4. **`_parse_windows_batch_fixed_argv`**（line 1097-1132）：在 `^"` 边界切分 token、空格分隔连续 token、最终 token 以 `^"` 结尾后无空格。对 `^"`-escaped 双引号和反斜杠做 correct CRT 感知解析。

5. **Round-trip 证据**：`test_windows_renderer_round_trips_fixed_argument_oracles`（line 467-495）对 7 种对抗输入做 renderer → oracle round-trip。`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`（line 849-906）用真实 `cmd.exe /d /c` 验证 13 种 fixed + 2 种 appended 对抗 argv，所有 marker 零 injection。

**结论**：
- Oracle 是 production renderer（`_quote_windows_batch_argument`、`_render_windows_script`）的精确逆运算。
- Oracle 拒绝 zero/multiple/misleading business commands；不依赖 whole-file count、substring presence 或 execution result。
- `company_name_supplied=true` 从 oracle 返回值派生（同源），不是从执行成功反推。
- S3 的 `test_windows_generated_script_runs_real_cli_into_temp_storage` 使用同一 oracle（函数调用复用，非重新实现），并将 `company_name_supplied` 写入 artifact。
- Fins owner contract（缺 company name 时 fail closed）未被修改；不增加 infer/FMP/default/shared helper。

**无 drift、无遮蔽、无回退风险。**

---

### 2. S2 setx DEVNULL/native timeout/names truth — 完整验证

**审查路径**：`init_environment.py` `_persist_windows_environment()` L414-450

**S2 变更内容**（+8 lines production, ~200 lines test）：

1. **模块级常量**：`_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0`（line 28）

2. **`subprocess.run` contract**（lines 417-427）：
   - `args=("setx", entry.name, entry.value)` — argument tuple，非 string
   - `shell=False`
   - `stdin=subprocess.DEVNULL`, `stdout=subprocess.DEVNULL`, `stderr=subprocess.DEVNULL`
   - `close_fds=True`
   - `text=False`
   - `check=False`
   - `timeout=_WINDOWS_SETX_TIMEOUT_SECONDS`（30.0s）

3. **异常收口**（lines 428-442）：
   - `KeyboardInterrupt` → `EnvironmentPersistenceInterrupted` with names truth（line 428-436）
   - `subprocess.TimeoutExpired` → `_windows_failure_result`（line 437-438），不绑定、不格式化、不记录 raw exception
   - `OSError` → `_windows_failure_result`（line 439-440）
   - `completed.returncode != 0` → `_windows_failure_result`（line 441-442）

4. **Whole-batch injection**（lines 443-450）：三路异常收口均不注入已写前缀；success path 在 **所有** setx 成功后一次性注入 `os.environ`。

5. **`_windows_failure_result`**（lines 453-468）：返回 `status=FAILURE`（first nonzero）或 `status=PARTIAL_FAILURE`（middle nonzero/OSError/TimeoutExpired），携带 `written_names` 和 `unwritten_names` name-only。零 retry、零 ambiguous loss、零回滚。

**S2 test contract**：

- `_SetxCall` dataclass（frozen/slots）：9-field subprocess contract 完整记录（args、shell、stdin、stdout、stderr、close_fds、text、check、timeout）。
- `_expected_setx_call()`：构造 owner contract 的预期 call record——DEVNULL stdio、close_fds=True、shell=False、text=False、check=False、timeout=30.0。
- `_SetxRecorder`：支持 `os_error_at`（OSError）、`timeout_at`（TimeoutExpired）、`interrupt_at`（KeyboardInterrupt）三种异常注入。
- 成功路径测试（`test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success`）：验证 2-entry success → 整批注入 → `environment_visible_during_calls == [False, False]`。
- 失败路径测试覆盖：first nonzero (`failure_at=0`)、middle nonzero (`failure_at=1`)、OSError at index 1、Timeout at index 1（验证 raw argv 不在 result/repr 中）、interrupt at 0/1/2、env injection interrupt。
- 覆盖率：production `init_environment.py` ≥ 80%（plan 要求），`57 passed / 93%`（fresh S2 Controller validation 确认）。

**结论**：
- setx 不再暴露无消费者的 capture pipe；DEVNULL + close_fds 封闭 handle inheritance。
- 每个 setx 有自身 30s native bound，不依赖 outer harness 提供 timeout。
- 所有异常路径统一收口到 names-only result，不泄漏 raw argv/value。
- Timeout 不声称 registry rollback。
- S2 test contract 逐字段验证生产行为，不使用 `hasattr`/fallback/compat shim。

**无 drift、无遮蔽。**

---

### 3. S3 anonymous handles / outer timeout / safe projection / canary — 完整验证

**审查路径**：`test_init_smoke.py` `_run_init()` L585-670 → `_render_init_timeout()` L550-582 → `_github_actions_canary()` L516-531 → `_select_windows_test_canary()` L534-547

**S3 变更内容**（+916 lines）：

1. **Three anonymous handles**（lines 604-608）：
   - 三个 `tempfile.TemporaryFile(mode="w+b")` context handles 覆盖 stdin/stdout/stderr
   - stdin 在 Popen 前做 `input_text.encode("utf-8", errors="strict")` → write → flush → rewind → frame clear
   - Popen 只接收 handle（`stdin=stdin_handle`），不接收 `input=` 参数
   - 成功时 `stdout_bytes.decode("utf-8", errors="strict")` / `stderr_bytes.decode("utf-8", errors="strict")`
   - `finally` block / context unwind 保证 handles 关闭；无 named path、无 `mkstemp`/`NamedTemporaryFile`/`tmp_path`、无 `unlink`/`retained-path` 框架

2. **Outer timeout state machine**（lines 637-658）：
   - `process.wait(timeout=180)` — outer 180s whole-process deadline
   - Timeout path 精确顺序：`poll()` → if None then `kill()` → `wait(180)` → if timeout then `poll()`（恰好一次 post-cleanup nonblocking poll）
   - 不调用 `communicate()`、不读取 timeout path 的 stdout/stderr、不做二次 kill/递归 process tree 治理
   - 四个状态明确投影：deadline-exited (returncode_at_timeout=1)、kill+cleanup-success (-9)、kill+cleanup-timeout+running、kill+cleanup-timeout+exited

3. **Safe projection**（`_render_init_timeout` L550-582）：
   - 唯一输出字段：`category=dayu_cli_init_timeout`、`timeout_seconds=180`、`returncode_at_timeout=<int|not_exited>`、`cleanup=<completed|timeout>`、`cleanup_returncode=<int|not_available>`、optional `process_state_after_cleanup_timeout=<running|exited>`
   - 不含：argv、cwd、workspace path、stdin、stdout、stderr、raw exception class name
   - `pytest.fail(safe_message, pytrace=False)` — 不展开 process/input 的 internal frames

4. **Canary derivation**（lines 516-547）：
   - `_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"` — 31 bytes, single NUL, Python bytes literal
   - `_github_actions_canary(raw_run_id)`：`raw_run_id` 必须是正 ASCII 十进制整数 → `str(int(raw_run_id))` canonicalization → `SHA-256(domain + canonical_run_id.encode("ascii"))` → `f"sk-dayu-test-{digest}"`
   - `_select_windows_test_canary(environment)`：GitHub Actions 路径只从 `GITHUB_RUN_ID` 确定性派生；缺失/非法 run id → `AssertionError`，零 random fallback。本地非 GitHub Actions 路径仍随机。
   - R12 setx test（`test_windows_real_setx_round_trip_is_name_safe_and_cleaned` L1830）将 canary 作为 `OPENAI_API_KEY` 的值，验证 registry round-trip 成功，CLI stdout/stderr 零泄漏，cleanup 后 registry value 不存在。
   - Standalone R11 不消费 canary；不声称 canary 证明。

5. **Timeout negative tests**（`test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup` 4 个 parametrize case）：
   - 每个 case 验证：返回码投影正确、cleanup 状态正确、stdout/stderr handle 零读取、safe projection 不含 forbidden material、handles 在 context unwind 后关闭、raw `TimeoutExpired` 确实包含 sentinel（探针有效）但 safe projection 不含

6. **Canary owner tests**：
   - `test_github_actions_canary_freezes_domain_vector_determinism_and_shape`：8 项冻结 assertion
   - `test_github_actions_canary_fails_closed_without_random_fallback`：6 种非法环境全部 `AssertionError`，`_ForbiddenTokenFactory` 确认零 random fallback
   - `test_github_actions_canary_uses_public_run_id_without_random_fallback`：合法路径不触发 random

**结论**：
- S3 outer harness 的 180s timeout 与 S2 的 per-setx 30s 在**不同粒度**（whole-process vs per-native-call），职责独立，不互相遮蔽。
- 6 entries × 30s = 180s = outer timeout，恰好等于当前 sealed allowlist（`INIT_MODEL_CHOICES` + `OPTIONAL_ENVIRONMENT_NAMES` 固定 6 entries）。若未来扩 entry，需同时评估 timeout budget（已记录为 forward-compat observation）。
- Anonymous handles 的 cleanup contract 正确——handles 由 `with` context manager 保证关闭，不暴露 sentinel path/content。
- Canary domain 是唯一 Python bytes literal，末字节 single NUL `0x00`，known vector 冻结。独立重算确认。
- Canary 的 fail-closed 逻辑正确——非法 workflow env 不 fallback 到 random。

**无 drift、无遮蔽、零 backflow。**

---

### 4. inner/outer timeout — owner 非重复性

S2 ownership（`_persist_windows_environment`）：
- owner: per-setx 30s native timeout bound
- 粒度: 单次 `setx.exe` 调用
- 失效行为: 返回 `PARTIAL_FAILURE`，已写 names 保留，不注入

S3 ownership（`_run_init`）：
- owner: outer CLI process 180s deadline
- 粒度: 整个 `python -m dayu.cli init` 子进程
- 失效行为: `pytest.fail(pytrace=False)`，safe projection 不含 process material

两层 owner 不同、粒度不同、失效行为不同，语义不重复。

inner 30s bound 先于 outer 180s bound 触发。如果某个 setx 在 30s 内 timeout，production 返回 `PARTIAL_FAILURE`，CLI 继续（或退出），outer harness 在 180s 内捕获结果。如果 6 个 setx 全部 timeout（30s × 6 = 180s），刚好触及 outer bound——这是设计边界，不是遮蔽。

**无重复 owner、不互相遮蔽。**

---

### 5. strict UTF-8、interrupt、native failure、whole-batch injection — 逐路径验证

| Path | S2/S3 | Owner | 行为 | Test evidence |
|------|-------|-------|------|--------------|
| stdin 编码 | S3 | `_run_init` L609 | `input_text.encode("utf-8", errors="strict")` | `test_run_init_strict_utf8_rejects_invalid_input_before_popen` |
| stdout 解码 | S3 | `_run_init` L664 | `stdout_bytes.decode("utf-8", errors="strict")` | `test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels` |
| stderr 解码 | S3 | `_run_init` L665 | `stderr_bytes.decode("utf-8", errors="strict")` | same test |
| setx success + injection | S2 | `_persist_windows_environment` L443-450 | 所有 setx 0→注入→成功 | `test_windows_uses_argument_tuple_devnull_timeout_and_injects_only_after_all_success` |
| first nonzero | S2 | `_persist_windows_environment` L441-442 | `FAILURE`，零注入 | `test_windows_nonzero_reports_names_only_without_retry_or_injection[failure_at=0]` |
| middle nonzero | S2 | `_persist_windows_environment` L441-442 | `PARTIAL_FAILURE`，已写 names 保留 | `test_windows_nonzero_reports_names_only_without_retry_or_injection[failure_at=1]` |
| OSError | S2 | `_persist_windows_environment` L439-440 | `PARTIAL_FAILURE` | `test_windows_os_error_reports_partial_names_without_retry_or_injection` |
| TimeoutExpired | S2 | `_persist_windows_environment` L437-438 | `PARTIAL_FAILURE`，raw argv 不在 result/repr | `test_windows_timeout_hides_raw_argv_without_retry_or_injection` |
| KeyboardInterrupt | S2 | `_persist_windows_environment` L428-436 | `INTERRUPTED`，names truth | `test_windows_interrupt_reports_written_and_unwritten_names_without_values`（3 parametrize） |
| 注入后 interrupt | S2 | `_persist_windows_environment` L428-436 | `INTERRUPTED`，written_names 全量 | `test_windows_environment_injection_interrupt_keeps_completed_store_truth` |
| outer ordinary nonzero | S3 | `_run_init` L638 | typed result with returncode/stdout/stderr intact | `test_run_init_returns_ordinary_nonzero_as_typed_result` |
| outer timeout (4 state) | S3 | `_run_init` L639-658 | 四状态 safe projection | `test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup[0..3]` |

全部 14 种路径已由 owner tests 逐条验证，无缺口。

---

### 6. scope/security/deferred 边界

**Scope boundary**：
- `base..HEAD` 的生产文件变更仅为 `dayu/cli/init_environment.py`（+8 lines production code）。
- 无 `.github/workflows/`、根 README、`dayu/README.md`、Fins production、Config/Engine/Host/Service/UI、design doc 变更。
- 未提前实现 deferred Issue 142、151、175、177、178 或 Web/WeChat/render 能力。

**Security boundary**：
- 生产 `setx` argv/value 不进入 exception、log、JUnit、review artifact。
- S3 canary 在 GitHub Actions 路径只从公开 `GITHUB_RUN_ID` 确定性派生；不读取 GitHub Secrets 或 configured production values。
- `test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 验证 canary 不进入 CLI stdout/stderr，cleanup 后 registry value 不存在。
- Controller canary scan 的独立重算可行性已由本 review 确认——凭公开 run id、本模块 `_WINDOWS_CANARY_DOMAIN`（plain bytes literal）、标准 SHA-256 和 canonical decimal 规则可独立重算。
- Config/Host durable SQLite/EventLog trusted-local 裁决不变。
- Tool Trace/audit/public/LLM-facing/operator log 仍禁止 API key/header 明文。

**Deferred boundary**：
- 无新增 `shell=True`、PowerShell、`winreg`（生产）、process group/job object。
- 无 unified tool authorization 或 secret infrastructure。
- Gemini low-budget 保持 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

**无越界。**

---

### 7. review findings 零回流

以下 reviewer candidate 或 observation 已被 Controller 在 S1/S2/S3 各轮裁决中明确拒绝，本 aggregate re-review 确认零回流：

| 序号 | 来源 | 内容 | 裁决 | 本次确认 |
|------|------|------|------|----------|
| 1 | DS initial F01 (S2) | Python 3.11.0–3.11.3 `close_fds` patch-version claim | CPython 官方文档证伪，rejected | 零回流 ✓ |
| 2 | DS initial F02 (S2) | exception-kind/index 笛卡尔积测试 | 同一 helper 已分别覆盖，rejected | 零回流 ✓ |
| 3 | DS OBS-01..03 (S3) | frame clearing/scripted output timing/renderer invariant | observations，无 current action | 零回流 ✓ |
| 4 | MiMo raw-timeout probe residual (S3) | raw timeout 探针 | observation/residual | 零回流 ✓ |

S2 两项 rejected candidate 最终关闭且零回流；S3 review observations 无 current action 且零回流。

**本 review 也没有发现新 candidate。**

---

### 8. 本地证据不得关闭真实 Windows blocker

本 review 的所有验证（105 passed / 7 skipped / pyright / Ruff / diff-check / security scans / independent canary）都在 Darwin 上执行。

7 个 skipped tests（`@pytest.mark.skipif(platform.system() != "Windows", ...)`）覆盖了：

- junction fail-closed
- symlink privilege skip
- workspace root identity drift
- setx real round-trip
- 四态 config reload
- real CLI storage upload
- `cmd.exe` batch/CRT argv round-trip

这些测试通过 **test doubles**（`_SetxRecorder`、`_ScriptedInitProcess`、`_ScriptedInitPopenFactory`、`_TemporaryHandleRecorder`、`_ScriptedRegistryCommandRunner`）验证了 owner contract，但没有在真实 Windows 上验证 `cmd.exe` 子进程 stdin/stdout/stderr handle 语义、`TerminateProcess` 对 orphan `setx` 的行为和 concurrent registry mutation。

**本 review 不声称、不伪装、不 indirect-waiver 真实 Windows 行为。REAL_WINDOWS_PENDING_RELEASE_BLOCKER 保持完全 active。**

---

### 9. ✅ 本地证据链完整性确认

| 检查项 | 预期 | 实际 | 判定 |
|--------|------|------|------|
| combined owner tests | 105 passed / 7 skipped | 105 passed / 7 skipped | ✓ |
| full pyright | 0 errors, 0 warnings, 0 informations | 0 / 0 / 0 | ✓ |
| scoped Ruff | All checks passed | All checks passed | ✓ |
| aggregate binary diff SHA-256 | `b22a8b2ef...93ab0` | 匹配 | ✓ |
| zero-change artifact SHA-256 | `2033b173...7061` | 匹配 | ✓ |
| Controller validation SHA-256 | `03806775...4902` | 匹配 | ✓ |
| diff-check | 零输出 | 零输出 | ✓ |
| staged | empty | empty | ✓ |
| forbidden pattern: `capture_output=True` | 零 | 零 | ✓ |
| forbidden pattern: `shell=True` / `errors=replace` | 零 | 零 | ✓ |
| forbidden pattern: winreg/PowerShell/JobObject (production) | 零 | 零（reg.exe 仅测试验证/清理） | ✓ |
| forbidden pattern: deferred issues | 零 | 零 | ✓ |
| independent canary recalculation | 匹配 | 匹配 | ✓ |
| known vector `run_id="1"` | `sk-dayu-test-b8f2210d...0b97` | 匹配 | ✓ |
| S1 oracle → S3 real CLI | function-call reuse | function-call reuse | ✓ |
| S2 contract → S3 outer harness | real CLI call chain | real CLI call chain | ✓ |
| canary: standalone R11 | does not consume | does not consume | ✓ |
| canary: R12 setx test | consumes + round-trip + cleanup | consumes + round-trip + cleanup | ✓ |
| canary: Controller independent | feasible | confirmed feasible | ✓ |
| review findings backflow | zero | zero | ✓ |
| real Windows blocker | not waived | not waived | ✓ |

---

## Open Questions

1. **S2 `_WINDOWS_SETX_TIMEOUT_SECONDS` (30s) 与 S3 `_PROCESS_TIMEOUT_SECONDS` (180s) 的数值关系**：30s × 6 entries = 180s，恰好等于 outer bound。当前 sealed allowlist 为 6 entries（`INIT_MODEL_CHOICES` + `OPTIONAL_ENVIRONMENT_NAMES` 固定），但若未来扩至第 7 个 entry（210s > 180s），worst-case 会超出 outer bound。这是 **forward-compatibility observation**，不是当前 defect。

2. **S2 test constant `_EXPECTED_WINDOWS_SETX_TIMEOUT_SECONDS` (30.0) 与 production constant `_WINDOWS_SETX_TIMEOUT_SECONDS` (30.0) 同值但不 import**：test 通过独立常量 `_expected_setx_call()` 验证 contract，不 import production constant。这是合理的 test isolation 模式——test 的 purpose 是验证 production 使用 30.0 这一 fact，而非验证两个 Python module 共享同一 int object。

---

## Residual Risk

### `PENDING_RELEASE_BLOCKER` — 真实 Windows 行为（唯一 release blocker）

- **Risk**：S2 `DEVNULL`/`close_fds=True`/native timeout 与 S3 `TemporaryFile` anonymous handles/strict UTF-8/outer cleanup 在 Darwin 上通过 test double 验证，但真实 `cmd.exe`、`setx` 子进程 stdin/stdout/stderr handle 语义、`TerminateProcess` 对 orphan `setx` 的行为、以及 concurrent registry mutation 仍需真实 Windows runner 验证。
- **Owner**：Controller（三 slice 全部 accepted/push 后的 remote gate）。
- **Closure condition**：非 skip 的真实 `windows-latest` R11+R12 run，Controller 按 plan §9.3 锁定 dispatch response 返回的唯一 R12 `run_id`、验证 workflow identity/path、event、branch/ref 与 accepted implementation commit `head_sha`、独立重算并扫描同 run 完整 log 与全部 downloaded artifacts。
- **Current status**：`PENDING_RELEASE_BLOCKER`。S1/S2/S3 的 local acceptance 均未 waiver。

### 真实 Windows outer timeout 下的 orphan setx（已知限制）

- **Risk**：如果 outer CLI 被 kill（`_run_init` timeout path），Windows `TerminateProcess` 不保证杀死子 `setx.exe`。
- **Mitigation**：`test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 在 test 前后做幂等 `delete+proof-absent` cleanup；固定 key `OPENAI_API_KEY` 不会累积。
- **Severity**：低。计划明确禁止 process-tree/job-object 治理；这是明确接受的已知限制。

### 测试只在 Darwin 上执行

- **Risk**：combined 105 passed / 7 skipped 均在 Darwin 上运行。Windows-only code paths 通过 test double 验证。
- **Severity**：中。已在 `PENDING_RELEASE_BLOCKER` 中追踪。

---

## Ledger

| Category | Count | Detail |
|----------|------:|--------|
| Material code finding | **0** | 经五个 owner path 完整走读、production renderer 交叉验证、timeout state machine 展开、canary 独立重算、105-node test suite、full pyright、Ruff、安全扫描 |
| Accepted/open (from prior gate) | **0** | S1/S2/S3 各自的 final adjudication + aggregate initial adjudication 均为 0 |
| Rejected reviewer candidate (zero backflow) | **4** | DS F01 (patch-version → 被证伪)、DS F02 (exception-kind → 无独立分支)、DS OBS-01..03、MiMo raw-timeout probe residual |
| Accepted chain backflow | **0** | 无已接受 finding 被后续 gate 重新打开或逆转 |
| Needs-evidence | **0** | |
| Design contradiction | **0** | |
| Local blocker | **0** | |
| Unclassified residual | **0** | |
| Real Windows residual | **1** | `PENDING_RELEASE_BLOCKER`，三 slice accepted/push 后 Controller remote gate |
| Forward-compat observation | **1** | S2 timeout budget 与 allowlist size（见 Open Question 1） |

---

## Verdict

**`PASS / AGGREGATE_REREVIEW_COMPLETE / MATERIAL_FINDING_0 / NO_LOCAL_BLOCKER / ACCEPTED_CHAIN_BACKFLOW_0 / REAL_WINDOWS_PENDING_RELEASE_BLOCKER`**

五个 owner path 的 S1→S2→S3 完整实现经从零开始的 exhaustive 走读、production renderer 交叉验证、四状态 timeout state machine 展开、canary 独立重算、所有 112-node combined test suite 执行（105 passed / 7 skipped）、full pyright zero、scoped Ruff pass、三类 diff-check pass、staged empty、安全扫描通过。五个 owner path 的 aggregate binary diff SHA-256 与 immutable target 精确匹配。

S1 company-name oracle 与 production renderer 及 embedded R11 workflow 一致。S2 setx DEVNULL/native timeout/names truth 与 S3 outer anonymous-handle/safe projection/canary 正确串联，inner/outer timeout 职责独立不重复。Canary 从公开 run id fail closed、真实 setx node 消费、Controller 独立重算可行、standalone R11 不伪证。所有 14 种成功/失败/interrupt/UTF-8/超时路径逐条由 owner tests 验证。三 slice 间依赖通过函数调用复用而非实现重复保持一致性。

所有已被 Controller 拒绝的 reviewer candidate（DS F01/F02、DS OBS-01..03、MiMo raw-timeout probe residual）在代码、测试、README、plan 或 follow-up 中零回流。scope/security/deferred 边界无越界。Secret boundary 保持用户裁决——Config/Host durable trusted-local 不变，Tool Trace/audit 禁止明文。

**唯一 release blocker：`REAL_WINDOWS_PENDING_RELEASE_BLOCKER`**。本 review 在 Darwin 上执行；7 个 skipped Windows-specific tests 不证明也不 waiver 真实 Windows 行为。closure 需要非 skip 的真实 `windows-latest` R11+R12 run 与 Controller 独立 canary scan（按 plan §9.3 与 §8 closure matrix 执行）。
