# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 Implementation Plan-Drift Corrected Plan — AgentMiMo Complete Plan Review

## Review identity

- Reviewer: AgentMiMo（第一路完整 plan review）。
- Target: final 1084-line plan SHA-256 `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`。
- Scope: complete plan（§0–§13），not only 34/10 diff。
- Context: `WIN4-RW-S2-PD-F01` 已由 Controller 裁决、AgentCodex 修复并由 Controller 验证通过；当前状态 `IMPLEMENTATION_PAUSED / PENDING_DUAL_COMPLETE_PLAN_REVIEW`。
- Protected stopped implementation: 四个 payload SHA-256 不变，`test_prompt_command.py` 零 diff，staged tree empty。

## Assumptions tested

| # | Assumption | Direct evidence | Verdict |
| --- | --- | --- | --- |
| A1 | `_read_secret_input()` capability-based split 是唯一正确 product owner | `init.py:468-493` 使用 `sys.stdin.isatty()` 分流；CPython 3.11 Windows `win_getpass()` 在 redirected handle 下仍走 console `msvcrt.getwch()`（plan §13.1.2 evidence 4）；Linux `unix_getpass()` 读 `/dev/tty` | CORRECT |
| A2 | TTY path 不会被 pytest capture stdin 污染 | `_TtySecretInput`（`test_init_command.py:170-191`）`isatty()` 恒 `True`，`readline()` 立即 `AssertionError`；`_install_tty_getpass` 同时设置 `init_command.sys.stdin` 与 `getpass.getpass` | CORRECT |
| A3 | Redirected path 不调用 `getpass.getpass()` | `test_init_command.py:430-442` 中 `hidden_input = Mock(side_effect=AssertionError(...))`，redirected stdin 使用 `io.StringIO`，`hidden_input.assert_not_called()` | CORRECT |
| A4 | `test_prompt_command.py` 授权只限 exact node fixture 迁移 | `test_prompt_command.py` 当前零 diff（`git diff --exit-code` PASS）；plan §13.3 严格限定 ownership 为 `test_prompt_command_uses_init_generated_workspace_config` 的 strict typed TTY stdin fixture | CORRECT |
| A5 | typed fake 不需要 shared production seam | `_TtySecretInput` 是 test-local class，不导入 production 模块，不修改 `sys.__stdin__`，不依赖 ambient TTY | CORRECT |
| A6 | 四 payload SHA-256 lock 未被破坏 | 重新计算全部匹配：`7cf41485...4cce`、`b0601a96...e4c4`、`c5de0131...25fe`、`1541fb84...e5f8`；binary diff SHA-256 = `e67cd464...33669` | CORRECT |
| A7 | prompt 零 diff / staged empty 保持 | `git diff --exit-code -- tests/cli/test_prompt_command.py` PASS；`git diff --cached --exit-code` PASS | CORRECT |
| A8 | Security / deferred scope 零漂移 | plan §13.9 明确保持 trusted-local Config/Host SQLite/EventLog、Tool Trace/audit 禁止明文、deferred Issues 142/151/175/177/178 不实施 | CORRECT |

## Findings

### 001-已修复-中-WIN4-RW-S2-PD-F01: plan allowlist 遗漏 test_prompt_command.py

- **位置**: §13.3 WIN4-RW-S2 allowlist、§13.6.4/§13.6.6 scoped validation
- **问题类型**: 切片过粗 / 契约缺失
- **当前写法**: §13.3 S2 allowlist 只列 `dayu/cli/commands/init.py`、`tests/cli/test_init_command.py`、`README.md`、`tests/README.md`，遗漏了 direct integration consumer `tests/cli/test_prompt_command.py`
- **反例/失败场景**: `pytest tests/cli -q` broader gate 暴露唯一失败节点 `test_prompt_command_uses_init_generated_workspace_config`；该 test mock `getpass.getpass` 但未把 `sys.stdin` 设为 TTY，pytest capture stdin `isatty()=False`，`_read_secret_input()` 正确进入 redirected path，`readline()` 由 capture stream 抛 `OSError`，CLI 返回 1
- **为什么有问题**: plan §13.4 要求"所有受影响既有 getpass tests"迁移到 strict TTY fake，但 allowlist 漏了直接消费者，导致 implementation agent 无法合法修改该文件
- **直接证据**: Controller adjudication direct evidence（full CLI regression 唯一失败）；`test_prompt_command.py:1199-1261` 当前 mock `getpass.getpass` 但未设置 TTY stdin
- **影响**: implementation agent 无法完成 WIN4-RW-S2；full CLI regression 持续红
- **建议改法和验证点**: §13.3 加入 `tests/cli/test_prompt_command.py`，ownership 严格限 exact node 的 strict typed TTY stdin fixture 迁移；§13.6 加入 scoped Ruff / source scans / node-level diff review
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

**状态**: `ACCEPTED_CANDIDATE` → 已由 Controller 裁决为 `PLAN_DRIFT_ACCEPTED`，AgentCodex 修复，Controller 验证为 `FIXED_IN_PLAN`。本轮确认闭合。

## Six-challenge deep verification

### Challenge 1: product owner capability 分流是否仍唯一正确

**结论: CORRECT — 无 pytest/mock 兼容诱惑。**

1. `_read_secret_input()`（`init.py:468-493`）是唯一 secret input owner。分流逻辑只检查 `sys.stdin.isatty()`，不使用 `os.name`、`platform.system()`、`sys.__stdin__` identity 或 GitHub Actions 环境变量。
2. CPython 3.11 Windows `win_getpass()` 只在 `sys.stdin is not sys.__stdin__` 时 fallback；OS-level redirected handle 不替换 Python 的 `sys.__stdin__` 对象。因此 redirected stdin 在 Windows 上走 console `msvcrt.getwch()`，不消费 redirected bytes——这正是 plan §13.1.2 的 root cause。
3. Linux `unix_getpass()` 读 `/dev/tty`（存在时）或 `sys.stdin`（`/dev/tty` 不存在时）。redirected stdin 下 `/dev/tty` 通常不可用，因此 `getpass` 会读 redirected stream。但我们的 capability-based split 直接跳过 `getpass` 读 `sys.stdin.readline()`，行为一致。
4. Production code 中无 `hasattr`/`getattr`/`sys.__stdin__` 检查、无 fallback 到 `getpass`、无 `os.name` 特判。`_read_secret_input()` 内部只捕获 TTY path 的 `EOFError` 和 redirected path 的空 read，两者收敛为同一 `CliInitOperationError`。
5. 测试中 `_TtySecretInput.readline()` 立即 `AssertionError`，`_GetpassSequence` 不消费 stream 参数。没有任何 pytest/mock 兼容 shim 进入 production。

### Challenge 2: test_prompt_command.py 授权是否严格只限 exact node

**结论: CORRECT — 只改 fixture，不改 getpass 序列 / prompt / runtime 断言 / 其它 nodes。**

1. `test_prompt_command.py` 当前零 diff（`git diff --exit-code` PASS）。
2. plan §13.3 明确：ownership 严格限 `test_prompt_command_uses_init_generated_workspace_config` 的 strict typed TTY stdin fixture 迁移；同文件其它 tests 零 diff。
3. 该 exact node（`test_prompt_command.py:1199-1261`）当前 mock `builtins.input` 返回 `("14", "", "", "")`，mock `getpass.getpass` 返回 `("", "", "", "", "")`，但未设置 `sys.stdin` 为 TTY。
4. 修复只需添加 `_TtySecretInput()` 作为 `init_command.sys.stdin`（或 `prompt_command` 模块引用的 `sys.stdin`），保持既有 getpass value 序列、prompt/runtime assembly 断言和执行顺序不变。
5. plan §13.6.5 要求 node-level diff review：`git diff --unified=0 AMENDED_PLAN_BASE -- tests/cli/test_prompt_command.py`，只允许该 node 的 fixture 迁移。
6. 不存在"抽取 shared production seam"、"mock `_read_secret_input`"或"修改其它 prompt tests"的授权。

### Challenge 3: typed fake 是否无需 shared production seam 且 readline 误入 fail-fast

**结论: CORRECT — 完全 test-local，readline 立即 assertion failure。**

1. `_TtySecretInput`（`test_init_command.py:170-191`）继承 `io.StringIO`，只覆盖 `isatty()` 和 `readline()`。
2. `isatty()` 恒返回 `True`，声明 TTY capability。
3. `readline()` 立即 `raise AssertionError("TTY secret input must not call stdin.readline")`——任何调用都表示 TTY owner path 漂移。
4. 该 class 不导入 production 模块、不修改 `sys.__stdin__`、不依赖 ambient TTY、不共享 constant/helper。
5. `_install_tty_getpass`（`test_init_command.py:325-340`）同时设置 `init_command.sys.stdin = _TtySecretInput()` 和 `getpass.getpass = getpass_sequence`，确保 TTY path 只走 hidden getpass。
6. Redirected tests 使用真实 `io.StringIO`，显式保证 `isatty() == False`。

### Challenge 4: focused/full CLI/pyright/Ruff/node diff/source scans 能否验证

**结论: CORRECT — plan §13.6 覆盖完整验证矩阵。**

1. **Focused tests**: §13.6.1 per-slice focused commands 覆盖 `test_init_command.py`、`test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`、`test_init_smoke.py`。
2. **Full CLI regression**: §13.6.2 `pytest tests/cli -q` mandatory。
3. **Coverage**: §13.6.3 `dayu/cli/commands/init.py` line coverage >= 80%。
4. **Pyright**: §13.6.4 full pyright 零诊断。实际验证：`0 errors, 0 warnings, 0 informations` ✅。
5. **Ruff**: §13.6.4 scoped Ruff 零诊断 + full Ruff baseline 比较。实际验证：`All checks passed!` ✅。
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
4. **Canary contract**: plan §2.3/§9.3 冻结纯函数、domain separator bytes、已知向量；Controller 不共享 helper、不读 GitHub Secrets。
5. **No fallback/compat**: plan §11 零 compatibility re-export/wrapper/alias、零 platform fallback、零 test-only production seam、零 Issue implementation。

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
- `test_prompt_command.py` 授权严格限 exact node 的 typed TTY stdin fixture 迁移；
- typed fake 完全 test-local、readline 误入 fail-fast、无 shared production seam；
- validation matrix（focused/full CLI/pyright/Ruff/node diff/source scans）完整；
- 四 payload lock、prompt 零 diff、staged empty 全部 verified；
- security / deferred / real Windows pending 零漂移。

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
