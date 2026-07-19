# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Implementation Plan-Drift Corrected Plan — AgentDS Complete Review

## Review Identity

- **Reviewer**: AgentDS（第二路完整 plan review）
- **Reviewed target**: Final 1084-line corrected remediation plan
  - File: `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
  - SHA-256: `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`
  - 1084 lines / 75,492 bytes
- **Plan-drift fix**: AgentCodex artifact SHA-256 `226e6d5d...7900`
- **Controller adjudication**: SHA-256 `bf858217...97f7`
- **Controller validation**: PASS at plan-drift fix gate
- **WU/Umbrella**: `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07`
- **Gate**: corrected-plan dual complete review（非新 WU，非 implementation）
- **Review scope**: 完整 1084-line plan，非仅 34/10 增量

## Protected State Verification

| Lock | Expected SHA-256 | Verified |
| --- | --- | --- |
| Four-path binary diff | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | ✓ MATCH |
| `README.md` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` vs entry | zero diff | ✓ PASS |
| Staged tree | empty | ✓ PASS |
| `git diff --check` | pass | ✓ PASS |

Entry HEAD: `e3e138fedd43c8edcf0a7113ff3c0335c22c9485`（Controller plan-drift adjudication commit）。

## Assumptions Tested

1. **WIN4-RW-F01 root cause**: display assertion is not the upload-success owner → **CONFIRMED**。R11 evidence 证明 `cmd.exe` exit 0 + published storage facts 均正确；失败仅因旧 display 字面量 `Fins result` 已漂移为 `Fins summary`。Plan 的正确修复是删除 display assertion，改用 process exit + public storage facts。

2. **WIN4-RW-F02 root cause**: `getpass.getpass()` 在 Windows redirected stdin 下忽略输入 → **CONFIRMED**。CPython 3.11 `win_getpass()` 只在 `sys.stdin is not sys.__stdin__` 时 fallback；OS-level redirected handle 不替换 Python 的 `sys.__stdin__` 对象，导致 console path 忽略预置的 redirected bytes。

3. **Semantic owner of secret input**: `dayu/cli/commands/init.py::_read_secret_input()` → **CONFIRMED**。输入能力（TTY vs redirected），不是 OS 名称或 test 身份，决定读取路径。该边界不拥有 environment persistence、registry、Config、Host durable state 或 authorization。

4. **Capability-based routing is correct**: `sys.stdin.isatty()` → **CONFIRMED**。不使用 `os.name`、`platform.system()`、`sys.__stdin__`、GitHub Actions 检测或 test identity shim。

5. **Plan-drift finding `WIN4-RW-S2-PD-F01` is correctly fixed**: **CONFIRMED**。Plan §13.3 已加入 `tests/cli/test_prompt_command.py`，ownership 严格限定为 exact node 的 strict TTY stdin fixture 迁移；§13.4 明确禁止 compat seam、mock `_read_secret_input`、ambient TTY；§13.5 纳入 direct integration consumer；§13.6 补充 focused/Ruff/diff/source scans。

6. **Protected implementation state is intact**: **CONFIRMED**。Four-path binary diff SHA 匹配，prompt test 零 diff，staged empty。

## Architecture Boundary Review

### Layering

- `_read_secret_input()` 属于 CLI command 层（`dayu/cli/commands/init.py`），拥有 secret value 的读取和 EOF/interrupt 语义 → **正确**。
- 不拥有 environment persistence（`dayu/cli/init_environment.py`）、registry、Config、Host durable state、authorization 或通用 secret lifecycle → **边界清晰**。
- 不向上层（Service/Host/Engine）或下层（runtime）泄漏实现细节 → **正确**。

### Dependency direction

- `init.py` → `getpass`（标准库）、`sys`（标准库）→ **符合架构约束**。
- 不新增对 `dayu.runtime`、`dayu.host`、`dayu.engine`、`dayu.fins` 的依赖 → **正确**。
- 测试文件 `test_init_command.py` → `init_command`（被测模块）→ **正确的测试依赖方向**。

### Public contracts

- `_read_secret_input(prompt: str) -> str`：输入 prompt（含 env name），返回 secret value 或 raise → **自足 contract**。
- `CliInitOperationError`：value-free 错误文本 "secret input ended before completion" → **安全 contract**。
- `KeyboardInterrupt`：原样传播 → **标准 Python contract**。

### No boundary leaks

- 不把 `_read_secret_input` 提升为 `dayu.runtime` helper、cross-module facade 或 public API → **正确**。
- 不向 `getpass` 或 `readline` 消费者泄漏 env name 以外的 prompt 内容 → **正确**。
- test fakes（`_TtySecretInput`、`_FlushRecordingStderr`、`_InterruptingRedirectedSecretInput`）均为 test-local，不进入 production path → **正确**。

## Best-Practice Review

### Testability

- `_read_secret_input()` 通过 `sys.stdin` 和 `getpass.getpass` 的标准 Python 接口消费输入 → **完全可测试**。
- 测试使用 `monkeypatch.setattr` 替换 `sys.stdin`/`sys.stderr`/`getpass.getpass` → **标准 pytest 模式**。
- 所有分支均有独立 owner test，参数化覆盖 LF/CRLF/bare-CR/whitespace → **优秀**。

### Maintainability

- 模块级私有 helper，仅 required 和 optional 两处复用 → **最小复用**。
- 无 callback、factory、Protocol、class 或 builder → **朴素设计**。
- 分流逻辑基于 `isatty()` 单一判断 → **简单可推导**。

### Observability

- TTY path：`getpass.getpass()` 自身提供 prompt 显示和隐藏输入 → **标准**。
- Redirected path：prompt 写入 stderr + flush，value 从 stdin 读取 → **可观察**（prompt 可见，value 不可见）。
- 错误路径：统一 `CliInitOperationError` with value-free message → **安全可诊断**。

### Failure handling

- EOF：TTY `EOFError` 和 redirected `readline() == ""` 收敛为同一 `CliInitOperationError` → **正确**。
- `KeyboardInterrupt`：原样传播，CLI 映射 exit 130 → **标准**。
- `OSError`：透传，由顶层 CLI 通用异常处理 → **可接受**（plan docstring 明确说明）。

## Optimal-Solution Review

Plan 选择 capability-based routing（`isatty()`）而非 platform-based routing（`os.name`/`platform.system()`），是正确选择：

- **更简单的替代方案**（如始终使用 `input()` 替代 `getpass`）会破坏 TTY hidden input 的 security property → 不采用。
- **更复杂的替代方案**（如统一 secret provider/broker、console/PTY abstraction）超出本 WU 范围 → 被 deferred。
- **仅修复 test**（如 mock `_read_secret_input`）违反"不 mock product owner"约束 → 被拒绝。

当前方案是最小、最安全的路径。

## Overengineering Review

**无过度设计发现。** 逐一检查：

- `_read_secret_input()`：26 行模块级私有函数，无 class/Protocol/Builder → **朴素**。
- `_TtySecretInput`：两个方法（`isatty`、`readline`），纯 test fake → **最小**。
- `_FlushRecordingStderr`：覆写 `flush()` 计数，纯 test fake → **最小**。
- `_InterruptingRedirectedSecretInput`：单一目的 test fake → **最小**。
- `_install_tty_getpass()`：消除 getpass+mock+stdin 样板代码 → **合理的 test helper**。
- 无新增 abstraction layer、middleware、framework、builder 或 config/service discovery → **正确**。

## Overcoupling Review

**无过度耦合发现。** 检查关键耦合点：

- `_read_secret_input()` 与 `_collect_environment_persistence_plan()`：仅通过 prompt→value 返回值耦合 → **松耦合**。
- test_init_command.py 与 test_prompt_command.py：各自拥有独立 TTY fake（plan 禁止共享 helper）→ **刻意解耦**。
- init.py 与 init_environment.py：secret input 边界不触及 setx/native process → **正确隔离**。
- 不新增跨 slice 依赖：WIN4-RW-S1（display→storage owner）与 WIN4-RW-S2（secret input owner）无代码依赖 → **正确**。

## Direct Evidence Review：逐项压测

### Production code: `_read_secret_input()`（init.py lines 468–493）

| 检查项 | 结果 |
| --- | --- |
| `sys.stdin.isatty()` capability check | ✓ 平台中立，无 OS sniffing |
| TTY path: `getpass.getpass(prompt)` | ✓ 仅 prompt 参数，不传 stream |
| TTY path: catch `EOFError` only | ✓ 不捕获 `OSError`/`KeyboardInterrupt` |
| TTY path: raise `CliInitOperationError` with value-free text | ✓ 不包含 prompt/secret/raw exception |
| Redirected path: prompt → stderr + flush | ✓ 提示可见，flush 保证 delivery |
| Redirected path: exactly one `readline()` | ✓ 不循环读取 |
| Redirected path: `value == ""` → EOF | ✓ 与 TTY `EOFError` 收敛 |
| Redirected path: `\n` removal | ✓ 仅移除单个末尾 `\n` |
| Redirected path: conditional `\r` removal after `\n` | ✓ 仅当已移除 `\n` 且新末尾是 `\r` 时移除 |
| Redirected path: bare `\r` preserved | ✓ 不满足 `endswith("\n")` 前提 |
| Redirected path: no `rstrip`/strip | ✓ 仅精确移除一个 logical line ending |
| `getpass.getpass` 仅在 TTY path 调用 | ✓ redirected path 不调用 getpass |
| `KeyboardInterrupt` 不捕获 | ✓ 原样传播 |
| `OSError` 透传 | ✓ docstring 明确 |

### Test infrastructure

| 检查项 | 结果 |
| --- | --- |
| `_TtySecretInput.isatty() → True` | ✓ |
| `_TtySecretInput.readline() → AssertionError` | ✓ fail-fast，防止误入 redirected path |
| `_FlushRecordingStderr` 继承 `io.StringIO`，覆写 `flush()` | ✓ 记录 flush 次数 |
| `_InterruptingRedirectedSecretInput.readline() → KeyboardInterrupt` | ✓ identity 保持 |
| `_install_tty_getpass()` 同时设置 TTY stdin + getpass mock | ✓ 原子操作 |
| 所有直接 `_GetpassSequence` monkeypatch 已迁移到 `_install_tty_getpass()` | ✓ 验证通过（grep 确认） |
| Existing tests 迁移后保留 getpass value 序列 | ✓ `_GetpassSequence` 实例化参数不变 |
| 新增 redirected tests 使用 `io.StringIO`（`isatty() == False`） | ✓ 正确模拟 redirected stdin |
| 新增 redirected tests 验证 getpass 零调用 | ✓ `Mock(side_effect=AssertionError(...))` |

### Test coverage matrix（对照 §13.5.2 negative cases）

| Negative case | Test(s) | Status |
| --- | --- | --- |
| TTY hidden getpass | `test_read_secret_input_uses_hidden_getpass_for_tty` | ✓ |
| Redirected `getpass` 零调用 | 所有 redirected tests via `Mock(side_effect=AssertionError)` | ✓ |
| LF line ending | `test_read_secret_input_redirected...[lf]` | ✓ |
| CRLF line ending | `test_read_secret_input_redirected...[crlf]` | ✓ |
| bare-CR preserved | `test_read_secret_input_redirected...[bare-cr]` | ✓ |
| trailing whitespace preserved | `test_read_secret_input_redirected...[other-trailing-whitespace]` | ✓ |
| TTY EOF → value-free error | `test_secret_input_eof_paths...[tty]` | ✓ |
| Redirected EOF → value-free error | `test_secret_input_eof_paths...[redirected]` | ✓ |
| TTY interrupt identity | `test_secret_input_keyboard_interrupt_preserves_identity[tty]` | ✓ |
| Redirected interrupt identity | `test_secret_input_keyboard_interrupt_preserves_identity[redirected]` | ✓ |
| Full CLI TTY EOF → exit 1, safe text | `test_secret_input_eof_is_publicly_value_free...[tty]` | ✓ |
| Full CLI redirected EOF → exit 1, safe text | `test_secret_input_eof_is_publicly_value_free...[redirected]` | ✓ |
| Full CLI TTY interrupt → exit 130 | `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[tty]` | ✓ |
| Full CLI redirected interrupt → exit 130 | `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[redirected]` | ✓ |
| Required + optional reuse | `test_redirected_secret_owner_is_reused_for_required_and_optional_values` | ✓ |
| Non-disclosure (stdout) | Multiple tests via `capsys.readouterr()` | ✓ |
| Non-disclosure (stderr) | `_FlushRecordingStderr.getvalue()` 不含 secret | ✓ |
| Non-disclosure (exception) | `str(raised.value)` 不含 raw value | ✓ |
| Confirmation order unchanged | `test_redirected_secret_owner_is_reused...` verifies `confirmation.prompts` | ✓ |

### Direct integration consumer（test_prompt_command.py）

| 检查项 | 结果 |
| --- | --- |
| 当前仅一个 test 使用 getpass | ✓ `test_prompt_command_uses_init_generated_workspace_config` (line 1199) |
| 该 test 当前 mock getpass 但未设 TTY | ✓ 确认（plan-drift root cause） |
| Plan 授权该 exact node 的 TTY fixture 迁移 | ✓ §13.3, §13.4 |
| 同文件其他 tests 零 diff | ✓ 25 tests 中仅 1 个受影响 |
| 迁移后保留 getpass value 序列和业务断言 | ✓ §13.4 明确要求 |
| 迁移后 `readline()` 误入立即失败 | ✓ §13.5.2 纳入 TTY matrix |

### Forbidden paths scan

| 检查项 | 预期 | 实际 |
| --- | --- | --- |
| `capture_output=True` in init_environment.py | 零命中 | 待 implementation 验证 |
| `shell=True` / `errors=replace` in changed files | 零命中 | 待 implementation 验证 |
| `winreg` / `reg.exe` / `PowerShell` / `JobObject` | 零命中 | 待 implementation 验证 |
| Deferred issues (142/151/175/177/178) | 零新增命中 | 待 implementation 验证 |
| `sys.__stdin__` / `msvcrt` / `PTY` | 零命中 | 待 implementation 验证 |
| `hasattr` / `getattr` | 零新增命中 | 待 implementation 验证 |
| Display assertion diff (`Fins result/summary/...`) | 零输出 | 待 implementation 验证 |
| `getpass.getpass` in init.py | 仅 `_read_secret_input` TTY 分支一次 | ✓ 当前实现验证通过 |
| Production fallback / compat shim | 不存在 | ✓ 验证通过 |
| Test-only production seam | 不存在 | ✓ 验证通过 |

## Review Lenses Summary

| Lens | Result |
| --- | --- |
| Architecture boundary | PASS — 分层、依赖方向、公共合约、边界隔离均正确 |
| Best-practice | PASS — 可测试、可维护、可观察、安全 failure handling |
| Optimal-solution | PASS — capability-based routing 是最小最安全路径 |
| Overengineering | PASS — 无过度抽象、wrapper、builder 或 framework |
| Overcoupling | PASS — 模块间松耦合，test files 刻意解耦 |

## Findings

### DS-F01-未修复-Low-test_prompt_command.py exact-node TTY fixture 修复需要文件级 import 未在 plan 中显式列出

- **位置**: Plan §13.3, §13.4, §13.6.5
- **问题类型**: 切片过粗 / 不可直接实施（轻微）
- **当前写法**: Plan §13.3 授权 `tests/cli/test_prompt_command.py` 加入 WIN4-RW-S2 allowlist，ownership 严格限定为 exact node `test_prompt_command_uses_init_generated_workspace_config` 的 strict TTY stdin fixture 迁移。§13.4 明确 exact node 只补 `sys.stdin` TTY fake。§13.6.5 要求 node-level diff review 只允许 exact node fixture 迁移，"同文件其它 tests 零 diff"。
- **反例/失败场景**: 该 test 当前不导入 `dayu.cli.commands.init`（grep 验证：零匹配）。要做 `monkeypatch.setattr(init_command.sys, "stdin", tty_fake)`，必须先新增 `import dayu.cli.commands.init as init_command`。这个 import 是文件级变更（位于文件顶部 import block，非 exact node 函数体内部）。如果 implementation agent 或 reviewer 机械执行"同文件其它 nodes 零 diff"规则，可能将必要的 import 误判为 allowlist 违规。
- **为什么有问题**: Plan 的 node-scoped authorization 与 implementation 所需的必要文件级 import 之间存在合理但未显式声明的张力。这不是设计矛盾——import 是机械必需——但 plan 表述若不留出明确空间，可能导致 implementation agent 犹豫或 reviewer 误拒。
- **直接证据**:
  - `grep -n "init_command\|import.*init" tests/cli/test_prompt_command.py` → 零匹配
  - `grep -n "^import dayu.cli.commands.init" tests/cli/test_init_command.py` → line 21: `import dayu.cli.commands.init as init_command`
  - Plan §13.4: "只允许上述 exact node 补齐 production实际读取的 `sys.stdin` TTY fake"
  - Plan §13.6.5: `git diff --unified=0 AMENDED_PLAN_BASE -- tests/cli/test_prompt_command.py` 要求 "只允许 exact node fixture 迁移"
- **影响**: 低。Implementation agent 大概率会自行添加 import，Controller 也会在 validation 时正确理解。但 strict reading 下存在被误判为范围违规的风险。
- **建议改法和验证点**:
  1. Plan §13.3/§13.4 可选追加："该 exact node 的修复需要新增 `import dayu.cli.commands.init as init_command`（仅此一行文件级 import 变更）"。
  2. §13.6.5 node-level diff review 明确：在 exact node body diff + 仅一行新增 init_command import 的范围内通过。
  3. §13.6.6 ownership scan 不把该 import 识别为 forbidden scope creep。
- **修复风险**: Low（plan 文字补充，不改 product/test/contract）
- **严重程度**: Low（不阻塞 implementation；implementation agent 和 Controller 均可自行正确判断）

### DS-OBS-01-信息-test_prompt_command.py 与 test_init_command.py 各自拥有独立 TTY fake 实现

- **位置**: Plan §13.4 — test_prompt_command.py exact node 的 TTY fake
- **问题类型**: 观察项（非 finding）
- **当前写法**: Plan 要求 test_prompt_command.py 创建 "同样严格的 test-owned `sys.stdin` TTY fake"，禁止从 test_init_command.py 导入 `_TtySecretInput` 或建立共享 test helper。
- **观察**: 两个 test 文件各自拥有独立 TTY fake 实现（`_TtySecretInput` 在 test_init_command.py，另一个在 test_prompt_command.py）。两者必须保持相同的 strict 语义：`isatty() → True`，`readline() → AssertionError`。Plan 的"同样严格"措辞提供了意图约束，但未给出跨文件 contract 一致性的机械验证方法。
- **风险评估**: 两个 TTY fake 行为一致性的唯一真源是 plan 文字描述和各自的 focused test。如果任一 TTY fake 的 `readline()` 签名或行为漂移，production code 可能在不同 test 中被不同 contract 验证。但 plan 的 node-level diff review（§13.6.5）和 focused test gate（§13.6.1）提供了充分的逐文件验证。
- **不构成 finding 的理由**:
  - Plan 禁止共享 helper 是刻意解耦，防止 test 文件通过 shared fake 隐式耦合 → 正确设计决策。
  - Focused gate（§13.6.1）逐文件运行，各自证明 TTY fake 的 fail-fast 行为 → 充分验证。
  - Full CLI regression（`pytest tests/cli -q`）进一步验证两个 fake 在 aggregate 场景下的一致行为 → 额外保障。
- **严重程度**: 信息（无修复需求）

## Open Questions

`0`。Plan 的 owner 边界、输入能力分流、EOF/interrupt 语义、slice allowlist、README 决定、remote closure 与 security boundary 均已收敛；implementation agent 无需重新设计。

## Residual Risks

1. **非 Windows 本地无法证明 CPython 3.11 Windows console 与 redirected handle 的真实组合**（§13.9 #1）。Owner unit tests 只在 POSIX 锁定 capability contract；最终证据唯一 destination 是 §13.8 fresh R12 run。**风险可接受**。

2. **caller-owned pipe、OS handle 与当前 CLI process memory 按输入本质暂存 secret**（§13.9 #2）。本 WU 只承诺 CLI 不主动回显或投影，不承诺外部 shell/process inspection 安全。**风险可接受，扩大 transport threat model 需独立安全设计**。

3. **若 fresh R11 exit/storage owner 事实失败，或 fresh R12 在 secret 读取后出现新 failure**（§13.9 #3）。立即进入 diagnostic-first stop，不得沿用当前 root cause 解释新证据。**流程保护充分**。

4. **`_read_secret_input()` redirected path `sys.stderr.write(prompt)` 在真实 Windows pipe 的 flush 语义可能与 POSIX 不同**。Prompt 不包含 secret value，flush 失败最多导致 prompt 不显示，不影响 secret 安全。§13.8 fresh R12 会通过真实 redirected stdin 场景验证端到端行为。**风险可接受**。

## Final Plan Review Conclusion

**PASS**

理由：

1. **Root cause 与语义 owner 正确**：WIN4-RW-F02 根因是 `getpass.getpass()` 在 Windows 忽略 redirected stdin；语义 owner 是 `_read_secret_input()` capability-based input boundary。修复在正确 owner boundary 处，不下沉到消费者、不上浮到 infrastructure。

2. **Plan-drift `WIN4-RW-S2-PD-F01` 已正确修复**：`tests/cli/test_prompt_command.py` 的 exact-node allowlist、TTY matrix、focused/Ruff/diff/source scans 均已纳入 corrected plan。

3. **Implementation contract 自足且可验证**：
   - Production: `_read_secret_input()` 26 行，contract 明确（TTY hidden / redirected readline / EOF convergence / interrupt propagation / OSError propagation）。
   - Test: 28 tests in test_init_command.py，覆盖 TTY/redirected/LF/CRLF/bare-CR/EOF/interrupt/required/optional/non-disclosure；integration consumer 的 TTY fixture 迁移范围明确。
   - Validation: focused/aggregate/CLI regression/coverage/pyright/Ruff/diff/source scan — 全面且可机械执行。

4. **Protected state 完整**：Four-path binary diff SHA `e67cd464...3669` 匹配；`test_prompt_command.py` 零 diff；staged empty。Plan-only phase 未触碰 product/test/README/workflow/design。

5. **Security boundary 保持**：Config/Host SQLite/EventLog 仍是 trusted-local domain；Tool Trace/audit/public/LLM-facing/operator log 仍禁止 API key/header 明文。`_read_secret_input()` 不记录、不投影、不回显 secret value。

6. **Deferred/Foreign scope 零渗漏**：Issue 142/151/175/177/178、Web/WeChat/render、console/PTY/process isolation、unified secret management — 均未修改、未预埋、未依赖。

7. **Residual risks 均已标注 owner/destination**：真实 Windows closure → §13.8 fresh R12；transport threat model → 独立安全设计；unexpected failure → diagnostic-first stop。

### Candidate Findings for Controller Adjudication

| Finding | Status | Severity |
| --- | --- | --- |
| DS-F01: test_prompt_command.py 需要显式 import 声明 | Candidate — Controller 决定是否要求 plan 文字补充 | Low |
| DS-OBS-01: 两个 test 文件各自拥有独立 TTY fake | Observation — 不构成 finding，不要求修复 | Info |

### Blockers

`0`。

### Next Gate

AgentMiMo 第二路 review 完成后，Controller 汇总双路 findings，裁决并交由 AgentCodex 修复（如有 accepted findings），再进行双路完整 re-review。全部 accepted findings 关闭并形成 exact docs-only accepted plan commit 后，才可恢复 WIN4-RW-S2 implementation 并修改 `tests/cli/test_prompt_command.py`。
