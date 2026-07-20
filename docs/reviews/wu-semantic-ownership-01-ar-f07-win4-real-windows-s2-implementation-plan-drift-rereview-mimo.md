# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 Corrected-Plan — AgentMiMo 第一路完整 Re-Review

## Review identity

- Reviewer: AgentMiMo（第一路完整 re-review）。
- Target: final 1084-line corrected plan SHA-256 `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`。
- File: `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Scope: complete plan（§0–§13），not only 34/10 diff。
- Context: `WIN4-RW-S2-PD-F01` 已由 Controller 裁决为 `PLAN_DRIFT_ACCEPTED`、AgentCodex 修复、Controller 验证为 `FIXED_IN_PLAN`；当前状态 `IMPLEMENTATION_PAUSED / PENDING_DUAL_COMPLETE_PLAN_REVIEW`。
- Gate: 双路完整 re-review 之第一路。双路 closure 后形成 docs-only accepted plan commit，才可恢复 WIN4-RW-S2 implementation。
- 不是新 WU。

## Protected state verification

| Lock | Expected | Actual | Status |
| --- | --- | --- | --- |
| Entry HEAD | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | PASS |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | PASS |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | PASS |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | PASS |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | PASS |
| Four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | PASS |
| `tests/cli/test_prompt_command.py` diff | zero | zero | PASS |
| Staged tree | empty | empty | PASS |
| `git diff --check` | pass | pass | PASS |

## Assumptions tested

| # | Assumption | Direct evidence | Verdict |
| --- | --- | --- | --- |
| A1 | `_read_secret_input()` capability-based split 是唯一正确 product owner | `init.py:468-493` 使用 `sys.stdin.isatty()` 分流；CPython 3.11 Windows `win_getpass()` 在 redirected handle 下仍走 console `msvcrt.getwch()`（plan §13.1.2 evidence 4）；Linux `unix_getpass()` 读 `/dev/tty` | CORRECT |
| A2 | TTY path 不会被 pytest capture stdin 污染 | `_TtySecretInput`（`test_init_command.py:170-191`）`isatty()` 恒 `True`，`readline()` 立即 `AssertionError`；`_install_tty_getpass` 同时设置 `init_command.sys.stdin` 与 `getpass.getpass` | CORRECT |
| A3 | Redirected path 不调用 `getpass.getpass()` | `test_init_command.py` redirected tests 中 `hidden_input = Mock(side_effect=AssertionError(...))`，`hidden_input.assert_not_called()` | CORRECT |
| A4 | Plan §13.3 allowlist 已包含 `test_prompt_command.py` | §13.3 WIN4-RW-S2 allowed paths 明确列出 `tests/cli/test_prompt_command.py`，ownership 严格限 exact node | CORRECT |
| A5 | typed fake 不需要 shared production seam | `_TtySecretInput` 是 test-local class，不导入 production 模块，不修改 `sys.__stdin__`，不依赖 ambient TTY | CORRECT |
| A6 | 四 payload SHA-256 lock 未被破坏 | 重新计算全部匹配：`7cf41485...4cce`、`b0601a96...e4c4`、`c5de0131...25fe`、`1541fb84...e5f8`；binary diff SHA-256 = `e67cd464...33669` | CORRECT |
| A7 | prompt 零 diff / staged empty 保持 | `git diff --exit-code -- tests/cli/test_prompt_command.py` PASS；`git diff --cached --exit-code` PASS | CORRECT |
| A8 | Security / deferred scope 零漂移 | plan §13.9 明确保持 trusted-local Config/Host SQLite/EventLog、Tool Trace/audit 禁止明文、deferred Issues 142/151/175/177/178 不实施 | CORRECT |

## DS-F01 disposition（重点复核）

### DS-F01 rejected/no-fix 是否正确

**结论: CORRECT — rejected/no-fix 正确，plan 文字已自足授权。**

DS-F01 声称：`test_prompt_command.py` 当前不导入 `dayu.cli.commands.init`，要做 `monkeypatch.setattr(init_command.sys, "stdin", tty_fake)` 必须先新增文件级 import，plan 的 node-scoped authorization 与必要文件级 import 之间存在张力。

逐条反驳：

1. **Plan 已隐含授权 import。** §13.4 写道："direct integration consumer `test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 只补同样严格的 test-owned `sys.stdin` TTY fake"。"补齐"（补全缺失的能力）天然包含实现该能力所需的机械步骤——import 是 fixture 迁移的必要前提，不是独立的 scope 扩张。

2. **§13.6.5 diff review 机制已覆盖。** `git diff --unified=0 AMENDED_PLAN_BASE -- tests/cli/test_prompt_command.py` 的审查范围是"只允许 exact node fixture 迁移"。新增 `import dayu.cli.commands.init as init_command` 是 fixture 迁移的必要组成部分——它出现在 diff 中，reviewer 可以机械验证它只服务于该 node 的 TTY stdin 设置。

3. **§13.3 已有显式边界声明。** "`test_prompt_command.py` 的新增授权不是 prompt suite、runtime assembly或业务断言的范围扩张：只允许上述 exact node 补齐 production实际读取的 `sys.stdin` TTY fake；同文件其它 prompt tests必须相对 `AMENDED_PLAN_BASE` 零 diff。" 这条已经足够精确——import 是"补齐 production实际读取的 `sys.stdin` TTY fake"的机械前提。

4. **不列出 import 反而是最佳实践。** Plan 如果显式列出 `import dayu.cli.commands.init as init_command`，反而会：
   - 把实现细节固化到 plan 文字中（如果 import 路径变化，plan 就过时了）；
   - 暗示 import 本身需要独立授权（但它只是 fixture 迁移的自然组成部分）；
   - 违反"最小化 plan 文字"原则。

5. **Controller 裁决逻辑正确。** Controller 在 adjudication 中写道："正确 owner属于直接测试消费者迁移：`test_prompt_command_uses_init_generated_workspace_config` 必须提供test-owned、严格typed TTY stdin fake"。"提供"包括所有必要机械步骤。

**DS-F01 状态: REJECTED / NO-FIX。Plan 文字已自足，不需要补充 import 声明。**

## DS-OBS-01 disposition（重点复核）

### DS-OBS-01 test-local 解耦是否正确

**结论: CORRECT — 观察项正确，不构成 finding。**

DS-OBS-01 观察：`test_prompt_command.py` 与 `test_init_command.py` 各自拥有独立 TTY fake 实现，两者必须保持相同的 strict 语义（`isatty() → True`，`readline() → AssertionError`），但 plan 未给出跨文件 contract 一致性的机械验证方法。

逐条分析：

1. **Plan 刻意禁止共享 helper 是正确设计决策。** §13.4 明确"不得抽 compatibility/shared production seam或跨模块 facade"。如果两个 test 文件共享 `_TtySecretInput`，就会通过 shared fake 形成隐式耦合——一个文件修改 fake 行为会影响另一个文件的测试语义。

2. **跨文件一致性由 contract specification 保证，不靠共享实现。** §13.2.2 定义了 `_read_secret_input()` 的 capability contract：TTY path 使用 hidden getpass，redirected path 使用 readline。§13.5.2 定义了 TTY matrix：`isatty()` 恒为 `True`，`readline()` 被调用即 assertion 失败。这两个 specification 是跨文件一致性的真源。

3. **Focused test gate 提供逐文件验证。** §13.6.1 要求 `pytest tests/cli/test_init_command.py -q` 和 `pytest tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config -q` 分别通过。每个文件独立证明其 TTY fake 的 fail-fast 行为。

4. **Full CLI regression 提供聚合验证。** §13.6.2 `pytest tests/cli -q` 验证两个 fake 在 aggregate 场景下的一致行为。

5. **§13.6.6 forbidden source scans 提供机械验证。** `hasattr`/`getattr` 零命中、`sys.__stdin__`/`msvcrt`/PowerShell/PTY 零命中——这些 scan 确保没有 test 文件偷偷绕过 capability contract。

**DS-OBS-01 状态: OBSERVATION / INFO。不构成 finding，不要求修复。**

## Root cause 重新挑战

### WIN4-RW-F02 root cause 是否仍正确

**结论: CORRECT — `getpass.getpass()` 在 Windows redirected stdin 下忽略输入。**

1. CPython 3.11 `win_getpass()` 只在 `sys.stdin is not sys.__stdin__` 时 fallback 到 `input()`。OS-level redirected handle（如 GitHub Actions 的 stdin pipe）不替换 Python 的 `sys.__stdin__` 对象——`sys.stdin` 和 `sys.__stdin__` 仍是同一个 `io.TextIOWrapper` 实例。因此 `win_getpass()` 认为 stdin 未被替换，继续走 console `msvcrt.getwch()`，忽略 redirected bytes。

2. Plan 的 capability-based routing（`sys.stdin.isatty()`）是正确修复：redirected stdin 的 `isatty()` 返回 `False`，`_read_secret_input()` 直接走 `sys.stdin.readline()`，绕过 `getpass`。

3. 不使用 `os.name`/`platform.system()` 是正确决策——capability-based 判断比 platform-based 判断更准确、更可移植、更不易被环境变化破坏。

## Product fallback 禁令重新挑战

**结论: CORRECT — 零 fallback、零 compat shim。**

1. `_read_secret_input()` 在 redirected path 不调用 `getpass.getpass()`——如果 `readline()` 抛 `OSError`，原样透传，不 fallback 到 getpass。
2. `_TtySecretInput.readline()` 立即 `AssertionError`——如果 TTY path 意外调用 `readline()`，测试立即失败，不默默通过。
3. Plan §13.4 明确"不得 mock production `_read_secret_input`"——测试必须验证真实 product owner，不绕过。
4. Plan §13.3 明确"不得在 `_run_init()`、workflow或 Windows-only test注入 shim"——不为通过测试而修改 production。

## Validation matrix 重新挑战

**结论: CORRECT — 完整且可机械执行。**

| 验证维度 | Plan 覆盖 | 机制 |
| --- | --- | --- |
| Focused tests | §13.6.1 per-slice commands | `test_init_command.py`、`test_prompt_command.py::exact_node`、`test_init_smoke.py` |
| Full CLI regression | §13.6.2 mandatory | `pytest tests/cli -q` |
| Coverage | §13.6.3 | `dayu/cli/commands/init.py` line coverage >= 80% |
| Pyright | §13.6.4 | full pyright 零诊断 |
| Ruff | §13.6.4 | scoped Ruff + full Ruff baseline 比较 |
| Node-level diff | §13.6.5 | `git diff --unified=0 AMENDED_PLAN_BASE -- tests/cli/test_prompt_command.py` |
| Source scans | §13.6.6 | `getpass.getpass` 命中、`sys.__stdin__`/`msvcrt`/PowerShell/PTY 零命中、`hasattr`/`getattr` 零命中 |
| Allowlist | §13.3 + §13.6.5 | 只允许 §13.3 列出的 paths |
| README | §13.7 + §13.6.5 | rg 扫描 + diff review |

## Security / deferred / real-Windows boundaries 重新挑战

**结论: CORRECT — 零漂移。**

1. **Security boundary**: plan §13.9 保持 Config/Host internal SQLite/EventLog 为 trusted-local domain；Tool Trace/audit/public/LLM-facing/operator diagnostics 禁止 API key/header 明文。本 amendment 不读写 durable stores，不新增 projection。
2. **Deferred scope**: plan §13.9 明确 deferred/forbidden：Issue 142、151、175、177、178；Web/WeChat/render；通用 console/PTY/process isolation；setx redesign；统一 authorization/secret management；Fins generic diagnostic schema。
3. **Real Windows pending**: plan §13.8 明确 fresh R11/R12 closure 需要 new dispatch；当前 R11 `29703932798` / R12 `29703933666` 只证明 amendment root cause，不得复用为 closure。本地 skip 只记录平台事实。
4. **Canary contract**: plan §2.3/§9.3 冻结纯函数、domain separator bytes、已知向量；Controller 不共享 helper、不读 GitHub Secrets。

## Six-challenge deep verification

### Challenge 1: product owner capability 分流是否仍唯一正确

**结论: CORRECT — 无 pytest/mock 兼容诱惑。**

1. `_read_secret_input()`（`init.py:468-493`）是唯一 secret input owner。分流逻辑只检查 `sys.stdin.isatty()`，不使用 `os.name`、`platform.system()`、`sys.__stdin__` identity 或 GitHub Actions 环境变量。
2. Production code 中无 `hasattr`/`getattr`/`sys.__stdin__` 检查、无 fallback 到 `getpass`、无 `os.name` 特判。
3. 测试中 `_TtySecretInput.readline()` 立即 `AssertionError`，没有任何 pytest/mock 兼容 shim 进入 production。

### Challenge 2: test_prompt_command.py 授权是否严格只限 exact node

**结论: CORRECT — 只改 fixture，不改 getpass 序列 / prompt / runtime 断言 / 其它 nodes。**

1. `test_prompt_command.py` 当前零 diff（`git diff --exit-code` PASS）。
2. plan §13.3 明确：ownership 严格限 `test_prompt_command_uses_init_generated_workspace_config` 的 strict typed TTY stdin fixture 迁移。
3. 该 exact node（`test_prompt_command.py:1199-1261`）当前 mock `getpass.getpass` 但未设置 `sys.stdin` 为 TTY。
4. plan §13.6.5 要求 node-level diff review，只允许该 node 的 fixture 迁移。
5. §13.3 明确"同文件其它 prompt tests必须相对 `AMENDED_PLAN_BASE` 零 diff"。

### Challenge 3: typed fake 是否无需 shared production seam 且 readline 误入 fail-fast

**结论: CORRECT — 完全 test-local，readline 立即 assertion failure。**

1. `_TtySecretInput`（`test_init_command.py:170-191`）继承 `io.StringIO`，只覆盖 `isatty()` 和 `readline()`。
2. `isatty()` 恒返回 `True`，声明 TTY capability。
3. `readline()` 立即 `raise AssertionError("TTY secret input must not call stdin.readline")`——任何调用都表示 TTY owner path 漂移。
4. 该 class 不导入 production 模块、不修改 `sys.__stdin__`、不依赖 ambient TTY、不共享 constant/helper。

### Challenge 4: focused/full CLI/pyright/Ruff/node diff/source scans 能否验证

**结论: CORRECT — plan §13.6 覆盖完整验证矩阵。**

1. **Focused tests**: §13.6.1 per-slice focused commands 覆盖 `test_init_command.py`、`test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`、`test_init_smoke.py`。
2. **Full CLI regression**: §13.6.2 `pytest tests/cli -q` mandatory。
3. **Coverage**: §13.6.3 `dayu/cli/commands/init.py` line coverage >= 80%。
4. **Pyright**: §13.6.4 full pyright 零诊断。
5. **Ruff**: §13.6.4 scoped Ruff 零诊断 + full Ruff baseline 比较。
6. **Node-level diff**: §13.6.5 `git diff --unified=0 AMENDED_PLAN_BASE -- tests/cli/test_prompt_command.py` 确保只允许 exact node fixture 迁移。
7. **Source scans**: §13.6.6 覆盖 `getpass.getpass` 命中、`sys.__stdin__`/`msvcrt`/PowerShell/PTY 零命中、`hasattr`/`getattr` 零命中、display-added-diff 零命中、deferred scope 零命中。

### Challenge 5: 四 payload lock / prompt 零 diff / staged empty 是否保持

**结论: CORRECT — 全部 verified。**

| Lock | Expected | Actual | Status |
| --- | --- | --- | --- |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | PASS |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | PASS |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | PASS |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | PASS |
| Four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | PASS |
| `tests/cli/test_prompt_command.py` diff | zero | zero | PASS |
| Staged tree | empty | empty | PASS |

### Challenge 6: security / deferred / real Windows pending 是否零漂移

**结论: CORRECT — 零漂移。**

1. **Security boundary**: plan §13.9 保持 Config/Host internal SQLite/EventLog 为 trusted-local domain；Tool Trace/audit/public/LLM-facing/operator diagnostics 禁止 API key/header 明文。本 amendment 不读写 durable stores，不新增 projection。
2. **Deferred scope**: plan §13.9 明确 deferred/forbidden：Issue 142、151、175、177、178；Web/WeChat/render；通用 console/PTY/process isolation；setx redesign；统一 authorization/secret management；Fins generic diagnostic schema。
3. **Real Windows pending**: plan §13.8 明确 fresh R11/R12 closure 需要 new dispatch；当前 R11 `29703932798` / R12 `29703933666` 只证明 amendment root cause，不得复用为 closure。本地 skip 只记录平台事实。
4. **No fallback/compat**: plan §13.4 零 compatibility re-export/wrapper/alias、零 platform fallback、零 test-only production seam、零 Issue implementation。

## Findings

**0 findings。** DS-F01 rejected/no-fix 正确；DS-OBS-01 不构成 finding。无新 findings、无 backflow findings。

## Open questions

`0`。当前 owner、输入能力分流、EOF/interrupt、slice allowlist、README、remote closure 与 security boundary 均已收敛。

## Residual risks

| # | Risk | Owner | Destination |
| --- | --- | --- | --- |
| R1 | 非 Windows 本地无法证明 CPython 3.11 Windows console 与 redirected handle 的真实组合 | WIN4-RW-S2 owner unit tests | §13.8 fresh R12 |
| R2 | caller-owned pipe / OS handle 按输入本质暂存 secret；本 WU 只承诺 CLI 不主动回显或投影 | 安全设计 | 独立安全设计 WU（不在本 amendment） |
| R3 | fresh R11 exit/storage owner 事实失败，或 fresh R12 在 secret 读取后出现新 failure | diagnostic-first stop gate | §10 / §13.9 |

## Plan review conclusion

**PASS**

Final 1084-line plan（SHA-256 `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`）：

- product owner capability 分流正确，无 pytest/mock 兼容诱惑；
- `test_prompt_command.py` 授权严格限 exact node 的 typed TTY stdin fixture 迁移，§13.3 allowlist 已自足授权必要最小 test-local imports；
- typed fake 完全 test-local、readline 误入 fail-fast、无 shared production seam；
- validation matrix（focused/full CLI/pyright/Ruff/node diff/source scans）完整且可机械执行；
- 四 payload lock、prompt 零 diff、staged empty 全部 verified；
- security / deferred / real Windows pending 零漂移；
- DS-F01 rejected/no-fix 正确，DS-OBS-01 不构成 finding。

`WIN4-RW-S2-PD-F01` 已闭合。plan 足够 code-generation-ready，可交给 implementation agent。

## Protected state

| Item | Value |
| --- | --- |
| Entry HEAD | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` |
| Plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` |
| Four-payload binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` |
| `test_prompt_command.py` diff | zero |
| Staged tree | empty |
| Implementation status | `PAUSED` |

## Next gate

AgentDS 并发完整 re-review。双路 closure 后形成 docs-only accepted plan commit，才可恢复 WIN4-RW-S2 implementation。
