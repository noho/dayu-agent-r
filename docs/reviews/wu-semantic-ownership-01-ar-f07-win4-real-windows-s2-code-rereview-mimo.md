# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 — 第一路 Code Re-Review（AgentMiMo）

## Verdict

**PASS / 未发现实质性问题**

本次 re-review 是既有 `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07 WIN4-RW-S2` 的第一路完整 code re-review，不是新 WU。AgentMiMo 独立从零复核 immutable five-path target、final plan、implementation/Controller validation、两路 initial code review、Controller adjudication、AgentCodex zero-change artifact（Controller EOF trim 后 SHA `994e809e79f7faf3c969c4e59553b73ea24efa45214cd2ef72479a6b07675dcb`，原始含 EOF 空白 SHA `c1821b294d2c22bcc0629b135be48a74f9008cb6067384fc462989f549a08c3a`）、Controller zero-change validation SHA `ed584c86815cedee66ad14204196d4e3d4545e0f2eec0c32d04c540c1e1abe16` 及 direct code/tests/README，未发现 blocker、new findings、backflow findings 或 semantic ownership drift。

## Scope

- Mode: Current Changes Mode
- Branch: `phaseflow/host-issues-control`
- Base: `main` (immutable implementation entry HEAD `bbb10959253fb3cb4bd22299196cf65a4a961b10`)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-rereview-mimo.md`
- Included scope:
  - `dayu/cli/commands/init.py` — `_read_secret_input()` owner 及其两个 call sites
  - `tests/cli/test_prompt_command.py` — `test_prompt_command_uses_init_generated_workspace_config` fixture 迁移
  - `tests/cli/test_init_command.py` — secret-input owner exact nodes
  - `README.md` — 用户可见 TTY/redirected 行为说明
  - `tests/README.md` — owner test 矩阵说明
  - `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` — final plan
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-controller-validation.md` — Controller validation
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-codex.md` — AgentCodex implementation artifact
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-mimo.md` — MiMo initial code review
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-ds.md` — DS initial code review
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-controller-adjudication.md` — Controller adjudication
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-fix-codex.md` — AgentCodex zero-change artifact
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-code-review-fix-controller-validation.md` — Controller zero-change validation
- Excluded scope:
  - `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml` — 零 diff
  - `tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py` — 零 diff
  - `dayu/fins/**` — 零 diff
- Parallel review coverage: 无（scope 有限，单 reviewer 可完整覆盖）

## Immutable State Verification

| Item | Expected | Fresh Actual | Status |
|---|---|---|---|
| Implementation entry HEAD | `bbb10959253fb3cb4bd22299196cf65a4a961b10` | `bbb10959253fb3cb4bd22299196cf65a4a961b10` | ✓ MATCH |
| Five-path aggregate binary diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` | ✓ MATCH |
| `README.md` content SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` content SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` content SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` content SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | ✓ MATCH |
| AgentCodex implementation artifact SHA-256 | `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910` | — | corroborative |
| Controller validation SHA-256 | `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b` | — | corroborative |
| Controller adjudication SHA-256 | `36f46ce688ae06ad3937e0a583c52f9fb1ed7c4db49d11a4573487c6b30ff953` | — | corroborative |
| AgentCodex zero-change artifact SHA-256（Controller EOF trim 后） | `994e809e79f7faf3c969c4e59553b73ea24efa45214cd2ef72479a6b07675dcb` | — | corroborative |
| AgentCodex zero-change artifact SHA-256（原始含 EOF 空白） | `c1821b294d2c22bcc0629b135be48a74f9008cb6067384fc462989f549a08c3a` | — | corroborative；追加一个 LF 即恢复 |
| Controller zero-change validation SHA-256（format-follow-up 版） | `ed584c86815cedee66ad14204196d4e3d4545e0f2eec0c32d04c540c1e1abe16` | — | corroborative |
| Final plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | — | corroborative |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check` | pass | pass | ✓ PASS |

所有七个 product/test/README payload 的 content SHA-256 均由 re-reviewer fresh 执行 `sha256sum` 验证。Five-path aggregate binary diff SHA-256 由 fresh `git diff --binary | shasum -a 256` 验证。Implementation entry HEAD 由 `git rev-parse HEAD` 验证。Staged tree 由 `git diff --cached --stat` 验证为空。

## Findings

未发现实质性问题。

## Adversarial Review Detail

### 1. Production Owner：`_read_secret_input()` 逐行走读

**入口**: `dayu/cli/commands/init.py:468-493` — `sys.stdin.isatty()` 唯一分流点。

**TTY 路径** (`init.py:478-482`):
- `getpass.getpass(prompt)` — 标准库隐藏输入，`init.py:480` 唯一命中点。
- `EOFError` → `CliInitOperationError("secret input ended before completion")` — value-free，`init.py:481-482`。
- `KeyboardInterrupt` 不捕获，原样透传。
- `OSError` 不捕获，原样透传。

**Redirected 路径** (`init.py:484-493`):
- `sys.stderr.write(prompt)` + `sys.stderr.flush()` — prompt 先于读取可见，`init.py:484-485`。
- `sys.stdin.readline()` — 精确一次逐行读取，`init.py:486`。
- `value == ""` → EOF 收敛为同一 value-free `CliInitOperationError`，`init.py:487-488`。
- `value.endswith("\n")` → 移除一个 LF，`init.py:489-490`。
- `value.endswith("\r")` → 移除 LF 前的 CR（CRLF），`init.py:491-492`。
- bare CR 与其它尾随空白保持，不引入 loose normalization。

**结论**: owner boundary 清晰，capability 分流由 `sys.stdin.isatty()` 唯一决定。没有 `hasattr/getattr`、`sys.__stdin__`、platform-specific shim 或 production fallback。

### 2. Call Sites 复用

**直接证据**: `init.py:510, 522` — 两个 call sites 复用同一个 `_read_secret_input()` owner。
- Required (line 510): 空值由 caller `_collect_environment_persistence_plan()` 拒绝 (`init.py:511-512`)。
- Optional (line 522): 空值由 caller 跳过 (`init.py:523`)。
- Input capability owner 不管业务规则；空值判断留在 caller boundary。

**结论**: 职责分离清晰，无 owner 重叠。

### 3. Diagnostic 不泄密

**直接证据**:
- `_environment_failure_message()` (`init.py:598-610`) — 只输出 `written_names` 和 `unwritten_names`。
- `_report_persisted_environment_names()` (`init.py:613-628`) — 只输出 `written_names`。
- `_report_retained_environment_paths()` (`init.py:631-643`) — 只输出 `retained_paths`。
- `_format_operation_error()` (`init.py:778-796`) — 不输出 secret values。
- 确认输出 (`init.py:537-540`) — 只含 `names`，不访问 `.value`。

**结论**: 所有公开输出路径只含变量名，不含 secret values。

### 4. Forbidden Pattern Scan

| Pattern | init.py hit | Evidence |
|---|---|---|
| `hasattr`/`getattr` | 0 semantic hit | `rg` line 602 is docstring word "captured"，not identity check |
| `sys.__stdin__` | 0 | — |
| `msvcrt` | 0 | — |
| `pytest`/`mock`/`capture` identity | 0 semantic hit | — |
| `getpass.getpass` | 1 | `init.py:480` only，inside `_read_secret_input()` TTY branch |

**结论**: Production code 是纯 capability-based router，不识别测试框架、不保留 fallback 路径。

### 5. Test Fixture 审查

**新增 fixtures** (`test_init_command.py`):
- `_TtySecretInput` (line 170): `isatty()` → `True`，`readline()` → `AssertionError`。Module-private，精确复制 owner capability check。
- `_FlushRecordingStderr` (line 194): 记录 flush count，不改变 `io.StringIO` 语义。
- `_InterruptingRedirectedSecretInput` (line 218): 在 readline 边界抛 interrupt，identity 保持。
- `_install_tty_getpass` (line 325): 组合 TTY stdin + getpass sequence。

**Integration consumer** (`test_prompt_command.py`):
- `_TtySecretInput` (line 104): 独立定义，不从 `test_init_command.py` 导入。Module-private。
- 注入点 (line 1244): `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())`。
- `readline()` fail-fast 确保 TTY path 漂移立即暴露。
- getpass sequence、model input、prompt/runtime assertions 均冻结不变。

**旧 test fixture 迁移** (5 处):
- `_GetpassSequence` → `_install_tty_getpass`：补齐缺失的 TTY capability 声明。
- `_install_ollama_inputs` 内部 (line 365): 同样迁移。
- 不改变 getpass value sequence 或业务断言。

**结论**: 所有 fixtures 锁定 owner contract，不固化偶然行为。

### 6. Non-Disclosure 全链路

| 输出路径 | 内容 | 含 secret value? | 证据 |
|---|---|---|---|
| `sys.stderr.write(prompt)` (redirected) | `"{VAR_NAME}（输入隐藏，不写日志）: "` | 否 | `init.py:484` |
| `getpass.getpass(prompt)` (TTY) | 隐藏输入，OS 级不回显 | 否 | `init.py:480` |
| `CliInitOperationError` | 固定 value-free 文本 | 否 | `init.py:482,488` |
| `CliInitOperationError` (required) | 仅变量名 | 否 | `init.py:512` |
| `print(...)` 确认 | 仅变量名 | 否 | `init.py:537-540` |
| `_environment_failure_message()` | 仅 names | 否 | `init.py:598-610` |
| `_report_persisted_environment_names()` | 仅 names | 否 | `init.py:613-628` |
| `_format_operation_error()` | stage/error/public states | 否 | `init.py:778-796` |

**结论**: secret value 不进入 stdout、stderr、exception message、confirmation output、persistence diagnostic、Tool Trace、audit 或 LLM-facing 文本。

### 7. Edge Case 矩阵

| Case | Behavior | Evidence |
|---|---|---|
| Redirected stdin 多行 | `readline()` 只读第一行，后续行留给下一次调用 | `init.py:486` |
| 空行作为 required value | `""` (LF stripped) → `CliInitOperationError` | `init.py:489-490, 511-512` |
| bare CR | 保留为值的一部分 | `init.py:491-492` |
| CRLF | CR+LF 均移除 | `init.py:489-492` |
| stdin 为 `None` | `AttributeError` → 外层 `except Exception` → `EXIT_FAILURE` | `init.py:235-240` |
| stderr 写入失败 | `OSError` 透传，无 secret 已读取 | `init.py:484` |
| 多次 Ctrl+C | 第二次 interrupt 中断 abort，POSIX 标准行为 | `init.py:224-225` |

**结论**: 所有 edge case 有直接证据支撑，行为正确。

### 8. Security / Deferred / Real-Windows Boundaries

- Config、Host internal SQLite/EventLog 继续属于 trusted-local domain。
- Tool Trace、audit、public/LLM-facing/operator diagnostics 不得出现 API key/header 明文的既有裁决不变。
- Issue 142/151/175/177/180、Web/WeChat/render、setx redesign、console/PTY/process isolation、统一 secret/authorization framework 或 Fins generic diagnostic schema 均未实现、未预埋、未依赖。
- Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合。唯一 destination 是 final plan §13.8 的 fresh R12。

**结论**: security/deferred boundaries 未被突破。

### 9. Overcoupling / Semantic Ownership Drift

| 语义 | Owner | 位置 | 独占性 |
|---|---|---|---|
| stdin capability 检测与分流 | `_read_secret_input()` | `init.py:468-493` | 唯一 |
| prompt 内容格式 | caller (`_collect_environment_persistence_plan`) | `init.py:510,522` | 唯一 |
| 空值业务规则 | `_collect_environment_persistence_plan()` | `init.py:511-512,523-524` | 唯一 |
| EOF 收敛消息 | `_read_secret_input()` | `init.py:482,488` | 唯一 |

无 owner 重叠。无下游 fallback 修补上游语义。无跨层穿透调用。无反向依赖。

### 10. README Boundary

- 根 `README.md`: 一句话解释 TTY vs redirected stdin 行为差异，面向最终用户，不暴露内部实现细节。
- `tests/README.md`: 一段描述 owner test 矩阵和真实 Windows destination，只记录当前事实。

**结论**: 均符合各自更新边界。

## DS-F01 / DS-OBS-01 Disposition 确认

- **DS-F01** (rejected/no-fix): 在 re-review 阶段已闭合。本轮实现精确遵循 accepted plan 的 fixture 迁移范围，无回潮。
- **DS-OBS-01** (information observation): 在 re-review 阶段已闭合。刻意解耦（两个文件各自定义 `_TtySecretInput`）是正确的设计决策，不构成 finding。

**结论**: 无 backflow。

## MiMo Next-Gate 文字 Controller 纠正确认

Controller adjudication 已明确指出 MiMo initial review artifact 的 next-gate 文字把 review 后流程压缩为"Controller validation 后 remote closure"，该文字不是 finding，也不具 gate 授权效力。总控固定流程是：

1. Zero-change fix record（AgentCodex 已完成）
2. Controller validation（已完成）
3. 双路完整 code re-review（本 artifact 即为第一路）
4. Controller final adjudication
5. Accepted local commit
6. WIN4 aggregate deepreview
7. Push、fresh R11/R12

Controller 已在 adjudication 中纠正，Codex zero-change artifact 已采用 Controller 固定 gate sequence。本 re-review artifact 同样采用 Controller 固定 gate sequence，不回流 MiMo initial 的压缩文字。

## Open Questions

无。

## Residual Risk

| # | Risk | Severity | Owner | Destination |
|---|---|---|---|---|
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合行为差异 | 中 | WIN4-RW-S2 | Final plan §13.8 fresh R12 dispatch |
| R2 | caller-owned pipe/OS handle 与 CLI process memory 按输入本质暂存 secret value；本 WU 只承诺 CLI 不主动回显或投影 | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 失败或 fresh R12 在 secret 读取后出现新 failure | 低 | Controller diagnostic-first stop gate | §13.9；必须回 Controller |
| R4 | Full Ruff 142 项为 entry 既有 baseline | 信息 | 独立 Ruff cleanup WU | 本轮精确证明五元组集合与 digest 不变 |

## Review Conclusion

- **PASS/FAIL**: PASS
- **Severity**: 无
- **New findings**: 0
- **Backflow findings**: 0
- **Accepted candidate**: N/A
- **Blocker**: 0
- **Open**: 0
- **Residual owner/destination**: 见 Residual Risk
- **Immutable state**: implementation entry HEAD `bbb10959253fb3cb4bd22299196cf65a4a961b10`，staged empty，five-path aggregate binary diff SHA-256 `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` MATCH
- **Next gate**: Controller final adjudication 后才可 accepted local commit；push、fresh R11/R12 尚未获授权

## Follow-up Closure：AgentCodex Zero-Change Artifact EOF 格式修正

### 触发

Pre-commit `git diff --check` 发现 AgentCodex zero-change artifact 原始版本末尾多一个空白行（188 行）。Controller 仅删除该 EOF 空白行，使文件归一化为 187 行。

### Delta 证明

| Check | Result |
|---|---|
| Controller EOF trim 后 SHA-256 | `994e809e79f7faf3c969c4e59553b73ea24efa45214cd2ef72479a6b07675dcb` |
| 原始含 EOF 空白 SHA-256 | `c1821b294d2c22bcc0629b135be48a74f9008cb6067384fc462989f549a08c3a` |
| 追加一个 LF 后 SHA-256 | `c1821b294d2c22bcc0629b135be48a74f9008cb6067384fc462989f549a08c3a` — 精确恢复旧 SHA ✓ |
| 188 行 → 187 行 | 唯一变化是删除末尾一个空行 ✓ |
| 正文、finding ledger、所有 product/test/README bytes | 零变化 ✓ |
| Updated Controller validation SHA-256 | `ed584c86815cedee66ad14204196d4e3d4545e0f2eec0c32d04c540c1e1abe16` |
| Five-path aggregate binary diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` — 不变 ✓ |
| Staged tree | empty ✓ |
| `git diff --check` | PASS ✓ |

### Format-Only Delta 对 Re-Review 判定的影响

EOF 空白行删除是纯格式操作：
- 不改变 Codex artifact 的任何 finding、owner judgment、test validation、security scan、deferred boundary 或 residual ledger 条目。
- 不改变 Controller validation 的 disposition（accepted code finding 0、PASS）。
- 不改变 five-path product/test/README payload 的任何字节。
- 不改变任何既有 review artifact、plan、control doc 或 workflow state。

**原 PASS / new finding 0 / backflow finding 0 / blocker 0 判定保持不变。**

## Review Metadata

- Reviewer: AgentMiMo
- Review type: code re-review（第一路，非新 WU）
- Review date: 2026-07-20
- Review time: 07:52:03 +0800
- Implementation entry HEAD: `bbb10959253fb3cb4bd22299196cf65a4a961b10`
- Final plan SHA-256: `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`
- AgentCodex implementation artifact SHA-256: `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910`
- Controller validation SHA-256: `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b`
- AgentMiMo initial review SHA-256: `9bb557d33b07bfa19a354969420605b3302fb79ec82263aba785f876702a3211`
- AgentDS initial review SHA-256: `108804a4b4db7274ee6e75f7961704c781c7fe55fbfe9d7fd9c2f2f0d4ad6e7c`
- Controller adjudication SHA-256: `36f46ce688ae06ad3937e0a583c52f9fb1ed7c4db49d11a4573487c6b30ff953`
- AgentCodex zero-change artifact SHA-256（Controller EOF trim 后）: `994e809e79f7faf3c969c4e59553b73ea24efa45214cd2ef72479a6b07675dcb`
- AgentCodex zero-change artifact SHA-256（原始含 EOF 空白）: `c1821b294d2c22bcc0629b135be48a74f9008cb6067384fc462989f549a08c3a`
- Controller zero-change validation SHA-256（format-follow-up 版）: `ed584c86815cedee66ad14204196d4e3d4545e0f2eec0c32d04c540c1e1abe16`
