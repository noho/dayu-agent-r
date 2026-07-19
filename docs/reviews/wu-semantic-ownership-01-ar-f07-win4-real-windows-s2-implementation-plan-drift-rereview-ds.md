# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Corrected-Plan — AgentDS Complete Re-Review

## Re-Review Identity

- **Reviewer**: AgentDS（第二路完整 re-review，非新 WU）
- **Re-reviewed targets**:
  - Final 1084-line corrected remediation plan, SHA-256 `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`
  - AgentMiMo initial review, SHA-256 `b5c9e8aa02429198de1a40d83745dbcaf8f85454635dbdbd0a30a6838e70daa7`
  - AgentDS initial review, SHA-256 `c5c18d0ef19e3f3889592ca99baca47e91219e3e6084e66461b4f30bed7761b1`
  - Controller adjudication, SHA-256 `9df3cf0a0b7e5c7793b6982036be672adda110fe16c169382c03209a3bae9f0c`
  - AgentCodex zero-change artifact, SHA-256 `86082feb4414e5d07c7d9cd70566debc5dd81828740d6ffc9eb24ae6b48b4350`
  - Controller zero-change validation, SHA-256 `342c8771c5635551da8cb87d79abe5d7f90699edf70c0afd2b5097130a1a384e`
  - Direct production code: `dayu/cli/commands/init.py` (SHA-256 `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4`)
  - Direct test code: `tests/cli/test_init_command.py` (SHA-256 `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8`), `tests/cli/test_prompt_command.py` (zero diff)
  - Protected four-path binary diff & staged tree
- **Re-review scope**: 完整 1084-line plan、两路 initial review、Controller adjudication、zero-change artifact/validation、direct code/tests 与 protected tree。不是只看 DS-F01/OBS 摘要。
- **锁**: four-path diff `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669`，prompt 当前零 diff，staged empty。

## Protected State Verification

| Lock | Expected | Actual | Status |
| --- | --- | --- | --- |
| Four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | ✓ MATCH |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` diff | zero | zero | ✓ PASS |
| Staged tree | empty | empty | ✓ PASS |
| Plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | ✓ MATCH |
| Entry HEAD | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | ✓ MATCH |

## §1 — DS-F01 拒绝复核：exact-node ownership 是否合理包含必要最小 imports/module-private fake

### 1.1 原始 DS-F01 内容

原始 DS-F01 提出：`test_prompt_command.py` exact-node TTY fixture 迁移需要文件级 `import dayu.cli.commands.init as init_command`，而 plan 未显式逐行授权该 import。Strict reading 下可能被 reviewer 误判为 allowlist 违规。

### 1.2 Controller 裁决

`REJECTED / ALREADY_AUTHORIZED_BY_OWNER_SCOPE / NO_PLAN_CHANGE`。理由：

1. §13.3 已把整个 `tests/cli/test_prompt_command.py` 放入 WIN4-RW-S2 allowlist，exact-node 限制约束业务消费者与语义范围，不要求所有机械支持行都位于函数体内。
2. §13.4 已要求 test-owned strict TTY fake；依据项目约束"优先模块级私有辅助函数"，实现它必需的最小标准库/被测模块 import 与模块级私有 fake 定义本就是 fixture 迁移的一部分。
3. §13.6.5 冻结的是同文件其它 tests、getpass value sequence 与业务断言，不禁止 import block 或只服务该 exact node 的 private fake。
4. 把 exact import spelling 继续写入 plan 不增加 owner correctness，只会把 code-generation-ready contract 过度耦合到逐行实现。

### 1.3 从零独立复核

#### 1.3.1 当前代码事实

| 检查项 | 结果 |
| --- | --- |
| `test_prompt_command.py` 当前是否 import `init_command` | **否** — `grep -c "import dayu.cli.commands.init"` → `0` |
| `test_prompt_command.py` 当前是否 import `sys` | **否** — `grep -c "^import sys"` → `0` |
| `test_init_command.py` 使用的 import 写法 | `import dayu.cli.commands.init as init_command` (line 21) |
| exact node `test_prompt_command_uses_init_generated_workspace_config` 当前 mock getpass 但未设 TTY | **是** — line 1219-1223 只 mock `getpass.getpass`，未 set `sys.stdin` |

#### 1.3.2 必要机械变更推导

为使 exact node 的 `_read_secret_input()` 走 TTY 路径，implementation agent 必须：

1. 在文件顶部 import block 新增: `import dayu.cli.commands.init as init_command`
2. 在模块级新增 private TTY fake（`isatty() → True`, `readline() → AssertionError`）
3. 在 exact node 函数体内新增: `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())`

其中 (1) 和 (2) 是**文件级**变更（import block + module-level class），但它们**只被 exact node 消费**，不修改任何其他 test 函数体。

#### 1.3.3 边界判断

Controller 的"exact node 限制约束业务消费者与语义范围，不要求所有机械支持行都位于函数体内"这一判断成立：

- §13.3 的 exact-node 限制针对的是**哪个 test 的业务语义被修改**，而非逐行代码位置。import 和 private fake class 是机械依赖，不改变任何其他 test 的业务契约。
- §13.6.5 冻结"同文件其它 tests、getpass value sequence 与业务断言"，import block 和 private fake 不触碰这些冻结项。
- 如果要求 plan 列出每个 import 和 private class，会把 plan 从 code-generation-ready contract 降级为逐行实现说明书，增加耦合而不提升正确性。
- 实际实现仍受 pyright（零诊断）、Ruff（零新增）、node diff（`git diff --unified=0`）和 focused test gate 的机械验证。

#### 1.3.4 是否存在真正 implementation ambiguity

**否。** Implementation agent 的路径完全确定：

- 参照 `test_init_command.py:21` 的同一 import 写法；
- 参照 `test_init_command.py:170-191` 的 `_TtySecretInput` 契约（`isatty() → True`, `readline() → AssertionError`）；
- 在 exact node 内添加 `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())`；
- 保留既有 getpass value 序列（`("", "", "", "", "")`）和所有业务断言。

没有需要 implementation agent 自行设计的 ambiguity。

#### 1.3.5 是否存在 backflow 风险

**否。** 变更方向是单向的：test consumer → production owner。`test_prompt_command.py` 只新增对 `init_command` 模块的 test-only 依赖和 TTY fake，不修改 `init.py`、不新增 production seam、不影响其他 test 文件。

### 1.4 DS-F01 最终判断

**Controller 拒绝正确。** DS-F01 不应被复活为 accepted finding。Plan 的 file-level authorization + exact-node business-scope constraint + mechanical validation gates（pyright/Ruff/node diff/focused test）已充分覆盖必要的最小 imports 和 module-private fake。无需 plan 文字补充。

---

## §2 — DS-OBS-01 复核：本地 fake 解耦

### 2.1 原始 DS-OBS-01

观察到 `test_init_command.py` 和 `test_prompt_command.py` 各自拥有独立 TTY fake 实现。Plan 禁止共享 helper，这是刻意解耦。不构成 finding。

### 2.2 从零独立复核

#### 2.2.1 两个 TTY fake 的 contract 一致性

`test_init_command.py:_TtySecretInput` (lines 170-191):
- `isatty() → True`
- `readline() → AssertionError("TTY secret input must not call stdin.readline")`

Plan §13.4 要求 `test_prompt_command.py` 的 TTY fake "同样严格"——contract 最低要求是 `isatty() → True` 且 `readline()` 误入立即失败。

两个文件各自的 focused test gate（§13.6.1）分别验证：
- `test_init_command.py`: `test_read_secret_input_uses_hidden_getpass_for_tty` 等直接测试 `_TtySecretInput` 的 fail-fast 行为
- `test_prompt_command.py`: exact node 的 `init`→`prompt` integration 测试，通过 full CLI 路径间接触发 TTY fake 的 fail-fast 行为

Full CLI regression（`pytest tests/cli -q`）额外提供 aggregate 场景下的行为一致性验证。

#### 2.2.2 共享 helper 的风险分析

如果抽取共享 helper：
- 两个 test 文件通过 shared fake 隐式耦合 → 违反 test isolation 原则
- 修改 shared fake 会影响两个文件的测试行为 → 增加变更 blast radius
- 可能演变为 production/test compatibility seam → 违反项目约束

Plan 的"禁止共享 helper"设计是正确的。

### 2.3 DS-OBS-01 最终判断

**维持 information observation，不构成 finding。** 两个独立 TTY fake 的 contract 一致性由各自的 focused test gate 和 full CLI regression 验证，刻意解耦是正确的设计决策。

---

## §3 — 全面复核：root cause、product owner、禁止 pytest/mock、focused/full validation、security、trusted-local SQLite/EventLog、Tool Trace/audit 明文禁止、deferred/remote 边界

### 3.1 Root cause 复核

| Finding | Root cause claim | 直接证据 | 复核结论 |
| --- | --- | --- | --- |
| WIN4-RW-F01 | display assertion 不是 upload-success owner | R11 evidence: `cmd.exe` exit 0 + published storage facts 正确；失败仅因旧 display 字面量 `Fins result` 漂移为 `Fins summary` | **成立** |
| WIN4-RW-F02 | `getpass.getpass()` 在 Windows redirected stdin 下忽略输入 | CPython 3.11 `win_getpass()` 只在 `sys.stdin is not sys.__stdin__` 时 fallback；OS-level redirected handle 不替换 Python `sys.__stdin__` 对象 | **成立** |

两个 root cause 均由直接 evidence 锁定，无间接推测。

### 3.2 Product owner 复核

| Owner | 位置 | 职责边界 | 复核结论 |
| --- | --- | --- | --- |
| WIN4-RW-F01 success oracle | `tests/cli/test_upload_filings_from_command.py` | 业务成功由 OS exit 0 + public Fins storage facts 证明，不依赖 display 文本 | **正确** |
| WIN4-RW-F02 secret input | `dayu/cli/commands/init.py:_read_secret_input()` | 输入能力（TTY vs redirected）决定读取路径；不拥有 environment persistence、registry、Config、Host durable state 或 authorization | **正确** |

每个语义有唯一清晰 owner，无 owner 重叠或缺失。

### 3.3 禁止 pytest/mock compatibility

逐项检查 production code `_read_secret_input()` (init.py:468-493):

| 检查项 | 结果 |
| --- | --- |
| 使用 `sys.stdin.isatty()` — 标准 Python | ✓ 平台中立 |
| 无 `hasattr`/`getattr` | ✓ |
| 无 `sys.__stdin__` identity 检查 | ✓ |
| 无 `os.name`/`platform.system()` 特判 | ✓ |
| 无 GitHub Actions 环境变量检测 | ✓ |
| 无 pytest/mock/capture identity 检测 | ✓ |
| 无 fallback/compatibility shim | ✓ |

测试代码使用标准 `monkeypatch.setattr` + `io.StringIO` + `Mock`，无 test-only production seam。

### 3.4 Focused/full validation 复核

Plan §13.6 验证矩阵完整且可机械执行：

| 验证层次 | 覆盖范围 | 可执行性 |
| --- | --- | --- |
| Per-slice focused tests (§13.6.1) | WIN4-RW-S1: `test_upload_filings_from_command.py`; WIN4-RW-S2: `test_init_command.py` + exact node in `test_prompt_command.py` + `test_init_smoke.py` | ✓ 命令明确 |
| Aggregate regression (§13.6.2) | Three-file aggregate + `pytest tests/cli -q` | ✓ 命令明确 |
| Coverage (§13.6.3) | `dayu/cli/commands/init.py` ≥ 80% line coverage，新增 branches 必须直接命中 | ✓ 阈值与命令明确 |
| Pyright (§13.6.4) | Full pyright 零诊断 | ✓ 命令明确 |
| Ruff (§13.6.4) | Scoped Ruff 零诊断 + full Ruff baseline 精确比较，新增/扩散为零 | ✓ 命令明确 |
| Diff/allowlist (§13.6.5) | `git diff --check`, `git diff --name-only AMENDED_PLAN_BASE`, staged empty, node-level diff review | ✓ 命令明确 |
| Source scans (§13.6.6) | getpass 命中点、forbidden symbols 零命中、display-added-diff 零输出、deferred issues 零新增 | ✓ 命令明确 |

### 3.5 Security boundary 复核

| 安全边界 | 当前裁决 | 本 amendment 是否修改 | 复核结论 |
| --- | --- | --- | --- |
| Config/Host SQLite/EventLog | trusted-local domain | 否 — 不读写 durable stores | **保持** |
| Tool Trace/audit/public/LLM-facing/operator log | 禁止 API key/header 明文 | 否 — 不新增 projection | **保持** |
| `_read_secret_input()` | 不记录、不投影、不回显 secret value | 设计即如此 | **保持** |
| Canary contract (§2.3/§9.3) | 确定性纯函数派生，Controller 独立验证，value-free evidence | 否 — 冻结 contract 不变 | **保持** |

`_read_secret_input()` 的 redirected path 把 prompt 写入 stderr（不含 secret value），只消费 stdin 一行。TTY path 使用 `getpass.getpass()` 的标准隐藏输入。两个路径都不把 value 写入 stdout/stderr/exception/log。

### 3.6 Trusted-local SQLite/EventLog 复核

本 amendment 不读取、迁移、重写或扩大 durable secret 范围。`_read_secret_input()` 只返回 secret value 给 `_collect_environment_persistence_plan()`，后者通过既有 `EnvironmentPersistenceEntry` → `plan_environment_persistence()` → `_persist_windows_environment()` (setx) 或 POSIX profile 路径完成持久化。不新增 durable store 访问路径。

### 3.7 Tool Trace/audit 明文禁止复核

`_read_secret_input()` 不产生任何 Tool Trace、audit event 或 log。secret value 以 `EnvironmentPersistenceEntry.value` 形式传递给 setx/profile writer，后者已在 §2.2（WIN4-S2）锁定 `DEVNULL + close_fds` contract。不新增明文投影路径。

### 3.8 Deferred/remote boundary 复核

| Deferred scope | 状态 | 复核 |
| --- | --- | --- |
| Issue 142, 151, 175, 177, 178 | Deferred/forbidden | ✓ 未修改、未预埋、未依赖 |
| Web/WeChat/render | Deferred/forbidden | ✓ 未触及 |
| Console/PTY/process isolation | Deferred/forbidden | ✓ 未引入 |
| setx redesign | Deferred/forbidden | ✓ 未修改 |
| Unified authorization/secret management | Deferred/forbidden | ✓ 未引入 |
| Fins generic diagnostic schema | Deferred/forbidden | ✓ 未触及 |
| Gemini low-budget | `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING` | ✓ 保持 |

Remote closure: fresh R11/R12 dispatch 是 closure 的唯一 destination（§13.8）；现有 runs `29703932798` / `29703933666` 只证明 amendment root cause。本地 skip 只记录平台事实。Controller-owned canary scan contract 冻结于 §2.3/§9.3。

---

## §4 — Findings

### New findings

`0`。从零复核 plan、两路 initial review、Controller adjudication、zero-change artifact/validation、direct code/tests 与 protected tree 后，无新 finding。

### Backflow findings（先前已闭合、本轮重新出现）

`0`。`WIN4-RW-S2-PD-F01` 已闭合，本轮无回潮。

### DS-F01 最终判断

**Controller 拒绝正确，维持 REJECTED。** 详细论证见 §1。Plan 的 file-level authorization + exact-node business-scope constraint + mechanical validation gates 已充分覆盖必要的最小 imports 和 module-private fake。不存在 implementation ambiguity 或 backflow 风险。

### DS-OBS-01 最终判断

**维持 information observation，不构成 finding。** 详细论证见 §2。两个独立 TTY fake 的刻意解耦是正确的设计决策。

---

## §5 — Blockers

`0`。

---

## §6 — Open Questions

`0`。Plan 的 owner 边界、输入能力分流、EOF/interrupt 语义、slice allowlist、README 决定、remote closure 与 security boundary 均已收敛；implementation agent 无需重新设计。

---

## §7 — Residual Risks

| # | Risk | Owner | Destination |
| --- | --- | --- | --- |
| R1 | 非 Windows 本地无法证明 CPython 3.11 Windows console 与 redirected handle 的真实组合 | WIN4-RW-S2 owner unit tests | §13.8 fresh R12 run |
| R2 | caller-owned pipe、OS handle 与 CLI process memory 按输入本质暂存 secret；本 WU 只承诺 CLI 不主动回显或投影 | 安全设计 | 独立安全设计 WU（不在本 amendment） |
| R3 | fresh R11 exit/storage owner 事实失败，或 fresh R12 在 secret 读取后出现新 failure | diagnostic-first stop gate | §10 / §13.9 |
| R4 | `_read_secret_input()` redirected path `sys.stderr.write(prompt)` 在真实 Windows pipe 的 flush 语义可能与 POSIX 不同 | §13.8 fresh R12 端到端验证 | Prompt 不含 secret value，flush 失败最多导致 prompt 不显示 |

---

## §8 — Protected State Summary

| Item | Value | Status |
| --- | --- | --- |
| Entry HEAD | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | ✓ |
| Plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | ✓ MATCH |
| Four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | ✓ MATCH |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` diff | zero | ✓ PASS |
| Staged tree | empty | ✓ PASS |
| `git diff --check` | pass | ✓ PASS |

## §9 — Final Re-Review Conclusion

**PASS**

理由：

1. **DS-F01 拒绝成立**：Plan 的 file-level authorization（§13.3）+ exact-node business-scope constraint（§13.4）+ mechanical validation gates（pyright/Ruff/node diff/focused test）已充分覆盖必要的最小 imports 和 module-private fake。不存在真正的 implementation ambiguity 或 backflow 风险。Controller 的 `ALREADY_AUTHORIZED_BY_OWNER_SCOPE` 裁决正确。

2. **DS-OBS-01 维持信息观察**：两个独立 TTY fake 的刻意解耦是正确的设计决策，各自 focused gate 和 full CLI regression 提供充分的 contract 一致性验证。

3. **Root cause 与 product owner 正确**：WIN4-RW-F01（display assertion 不是 upload-success owner）与 WIN4-RW-F02（`getpass.getpass()` 在 Windows redirected stdin 下忽略输入）均由直接 evidence 锁定。语义 owners 明确且边界清晰。

4. **代码实现 contract 自足且可验证**：
   - Production: `_read_secret_input()` 26 行，contract 明确（TTY hidden / redirected readline / EOF convergence / interrupt propagation）
   - Test: 28 tests in `test_init_command.py`，覆盖 TTY/redirected/LF/CRLF/bare-CR/EOF/interrupt/required/optional/non-disclosure；integration consumer 的 TTY fixture 迁移范围明确
   - Validation: focused/aggregate/CLI regression/coverage/pyright/Ruff/diff/source scan — 全面且可机械执行

5. **Protected state 完整**：Four-path binary diff SHA、四个 payload 文件 SHA、prompt test 零 diff、staged tree empty — 全部 verified。

6. **Security boundary 保持**：Config/Host SQLite/EventLog 仍是 trusted-local domain；Tool Trace/audit/public/LLM-facing/operator log 仍禁止 API key/header 明文。`_read_secret_input()` 不记录、不投影、不回显 secret value。

7. **Deferred/Foreign scope 零渗漏**：Issue 142/151/175/177/178、Web/WeChat/render、console/PTY/process isolation、unified secret management — 均未修改、未预埋、未依赖。

8. **无新 finding，无 backflow finding**：从零复核全部 artifact 和 direct code/tests 后，确认无 new finding、无 backflow finding。

### Finding Ledger

| Finding | Status | Severity | Disposition |
| --- | --- | --- | --- |
| `WIN4-RW-S2-PD-F01` (MiMo 001) | 已闭合 | 中 | Fixed in plan，等待 final re-review closure |
| DS-F01 | Rejected | Low | Controller 拒绝 → 复核确认拒绝成立 |
| DS-OBS-01 | Information | — | 观察，不构成 finding |

### Next Gate

本轮 DS re-review 结论 PASS / new finding 0 / backflow finding 0 / blocker 0。待 AgentMiMo 第二路 re-review 完成后，Controller 汇总双路 re-review 结论做最终裁决。只有双路 PASS、accepted/open finding 为 0、Controller final adjudication 通过后，才可形成 accepted plan commit 并恢复 WIN4-RW-S2 implementation。在此 gate 闭合前，不得修改 plan/control/existing artifacts/product/test/README/workflow/design，不得 stage/commit/push/dispatch。
