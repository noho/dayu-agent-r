# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 — AgentDS 第二路完整 Code Review

## Review Identity

- **Reviewer**: AgentDS（第二路完整 code review，非新 WU）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Gate**: `WIN4-RW-S2` dual complete code review（实现已完成、Controller 验证通过、AgentMiMo 第一路待并发）
- **Review scope**: immutable five-path implementation target（product/test/README）、AgentCodex implementation artifact、Controller validation、完整 plan/review chain、direct code/tests/README
- **锁**: implementation entry HEAD `bbb10959253fb3cb4bd22299196cf65a4a961b10`；five-path binary diff SHA-256 `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698`；staged empty
- **Output**: 本 artifact only；不得修改任何现有文件/product/test/README/control/workflow/design，不 stage/commit/push/dispatch/PR

## Immutable State Verification

| Item | Expected | Actual | Status |
| --- | --- | --- | --- |
| Implementation entry HEAD | `bbb10959253fb3cb4bd22299196cf65a4a961b10` | `bbb10959253fb3cb4bd22299196cf65a4a961b10` | ✓ MATCH |
| Five-path aggregate diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` | ✓ MATCH |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | ✓ MATCH |
| AgentCodex implementation artifact SHA-256 | `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910` | `1428620dda03ee52b632a16697d23a515456481efbcdbf6684ad4b9c71da7910` | ✓ MATCH |
| Controller validation SHA-256 | `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b` | `678205b4c6226e96f5b81c45ef33ca52da99b698085164123185e9751e2f325b` | ✓ MATCH |
| Final plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` | ✓ MATCH |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check` | pass | pass | ✓ PASS |

## §1 — Production Owner：`_read_secret_input()` 逐行 adversarial 审查

### 1.1 TTY path（`init.py:478-482`）

**入口**: `sys.stdin.isatty()` 返回 `True`。
**实际分支**: `getpass.getpass(prompt)` → 返回隐藏输入值。
**异常路径**:
- `EOFError` → 捕获后抛 `CliInitOperationError("secret input ended before completion")` — value-free。
- `KeyboardInterrupt` → 不捕获，原样透传，identity 保持。
- `OSError` → 不捕获，原样透传。

**直接证据**: `init.py:478-482`；`getpass.getpass` 唯一命中行 `init.py:480`（`rg -n 'getpass\.getpass'` 确认为唯一）。

**裁决**: 正确。TTY 路径使用 Python 标准库 `getpass.getpass()` 的隐藏输入；`EOFError` 收敛为同一 value-free 错误；`KeyboardInterrupt` 不做二次包装以保持 identity。

### 1.2 Redirected path（`init.py:484-493`）

**入口**: `sys.stdin.isatty()` 返回 `False`。
**执行顺序**:
1. `sys.stderr.write(prompt)` — prompt 写入 stderr（不含 secret value）
2. `sys.stderr.flush()` — 在读之前刷新，确保 prompt 可见
3. `value = sys.stdin.readline()` — 精确一次逐行读取
4. 空字符串检查 → EOF 收敛
5. Conditional line-ending 移除：仅移除一个 `\n`，条件移除前导 `\r`；bare CR 与其它尾随空白保留

**行结束处理矩阵**（`init.py:489-492`）:

| 输入 | `readline()` 返回 | 代码路径 | 返回值 | 判定 |
| --- | --- | --- | --- | --- |
| `"secret\n"` | `"secret\n"` | LF strip | `"secret"` | ✓ |
| `"secret\r\n"` | `"secret\r\n"` | CRLF strip | `"secret"` | ✓ |
| `"secret\r"` | `"secret\r"` | no LF → skip | `"secret\r"` | ✓ bare CR preserved |
| `"secret \t\n"` | `"secret \t\n"` | LF strip only | `"secret \t"` | ✓ whitespace preserved |
| `"\n"` | `"\n"` | LF strip | `""` | ✓ empty line → caller rejects for required |
| `""` (EOF) | `""` | EOF branch | `CliInitOperationError` | ✓ |
| `"secret"` (no newline) | `"secret"` | no LF → skip | `"secret"` | ✓ |

**直接证据**: `init.py:484-493`；参数化测试 `test_init_command.py:400-442` 覆盖 LF/CRLF/bare-CR/other-trailing-whitespace 四个 case。

**裁决**: 正确。不引入 loose normalization；bare CR 不是 logical line ending，正确保留为值的一部分。flush 在读之前确保 prompt 先于阻塞可见。

### 1.3 Call site 复用（`init.py:510, 522`）

两个 call site 复用同一个 `_read_secret_input()` owner：
- **Required** (line 510): `required_value = _read_secret_input(f"{required_name}（输入隐藏，不写日志）: ")` — 空值由 caller 拒绝
- **Optional** (line 522): `optional_value = _read_secret_input(f"可选 {optional_name}（留空跳过，输入隐藏）: ")` — 空值由 caller 跳过

**裁决**: 正确。输入 capability owner 不管业务规则（required vs optional）；空值判断留在 `_collect_environment_persistence_plan()` 的 caller boundary。职责分离清晰。

## §2 — Adversarial Attack Surface 审查

### 2.1 Stdin capability check 原子性

**场景**: `sys.stdin` 在 `isatty()` 检查与 `readline()` / `getpass()` 调用之间被替换。
**实际风险**: `dayu-cli init` 是单线程 CLI 命令；`sys.stdin` 替换在运行时不会发生（测试中 monkeypatch 在调用前完成）。
**裁决**: 不构成真实风险。非测试环境无此竞争条件。

### 2.2 `sys.stdin` 为 `None`

**场景**: 极端 Python 嵌入环境 `sys.stdin` 可能为 `None`。
**实际行为**: `sys.stdin.isatty()` → `AttributeError`，由 `run_init_command()` 的外层 `except Exception` 捕获并投影为 `EXIT_FAILURE`。
**裁决**: 可接受。此场景对所有使用 `sys.stdin` 的 Python 代码均存在，不是本函数特有。当前 CLI 入口要求 stdin 可用。

### 2.3 `sys.stderr` 为 `None` 或被关闭

**场景**: Redirected path 中 `sys.stderr.write(prompt)` 或 `sys.stderr.flush()` 失败。
**实际行为**: `OSError`/`AttributeError` 透传；此时尚未读取任何 secret value，无泄漏风险。
**裁决**: 正确。prompt 写入失败发生在读值之前，fail-closed 安全。

### 2.4 `sys.stdin.readline()` 抛出 `KeyboardInterrupt` 在读取中间

**场景**: 用户在输入过程中发送 SIGINT。
**实际行为**: `KeyboardInterrupt` 原样透传。`_read_secret_input()` 不捕获；`_collect_environment_persistence_plan()` 不捕获；`run_init_command()` 的外层 `except KeyboardInterrupt` 返回 `EXIT_KEYBOARD_INTERRUPT` (130)。
**直接证据**: `init.py:224-225`；测试 `test_init_command.py:617-658` 验证 exact identity 与 exit 130。
**裁决**: 正确。中断传播链完整；无 value 进入任何异常对象或公开输出。

### 2.5 `getpass.getpass()` 抛出非 `EOFError` 的异常

**场景**: 终端 I/O 错误（如 `OSError`、`termios.error`）。
**实际行为**: 不被 `_read_secret_input()` 捕获，透传到 `run_init_command()` → `except OSError` 或 `except Exception` → `EXIT_FAILURE`。
**裁决**: 正确。`_read_secret_input()` 的 docstring 声明 `OSError` 透传，行为一致。

### 2.6 Redirected stdin 提供多行输入

**场景**: stdin 包含 `"secret1\nsecret2\n"` 但只应读取一个 secret。
**实际行为**: `sys.stdin.readline()` 只读第一行 `"secret1\n"`，返回 `"secret1"`。后续 `readline()` 调用（下一个 optional 变量）会消费 `"secret2\n"`。
**裁决**: 正确。每次 `_read_secret_input()` 调用精确消费一行；调用次数与 required + optional 变量数匹配。

### 2.7 Redirected stdin 在单个 `_read_secret_input()` 调用期间到达 EOF

**场景**: stdin 内容为空或比预期少。
**实际行为**: `sys.stdin.readline()` 返回 `""` → `CliInitOperationError("secret input ended before completion")`。
**裁决**: 正确。与 TTY `EOFError` 收敛为同一 value-free 错误消息。

## §3 — Non-Disclosure 审查

### 3.1 Secret value 不进入 stdout/stderr

逐项检查所有公开输出路径:

| 输出路径 | 内容 | 含 secret value? | 证据 |
| --- | --- | --- | --- |
| `sys.stderr.write(prompt)` (redirected) | `"{VAR_NAME}（输入隐藏，不写日志）: "` | 否 | `init.py:484` |
| `getpass.getpass(prompt)` (TTY) | 隐藏输入，OS 级不回显 | 否 | `init.py:480` |
| `CliInitOperationError("secret input ended before completion")` | 固定 value-free 文本 | 否 | `init.py:482,488` |
| `CliInitOperationError(f"required environment value was not provided: {required_name}")` | 仅变量名 | 否 | `init.py:512` |
| `print("dayu-cli init: 将持久化以下环境变量名（不显示值）: ...")` | 仅变量名 | 否 | `init.py:537-540` |
| `_environment_failure_message()` | 仅 written_names/unwritten_names | 否 | `init.py:598-610` |
| `_report_persisted_environment_names()` | 仅 written_names | 否 | `init.py:613-628` |
| `_report_retained_environment_paths()` | 仅 retained_paths | 否 | `init.py:631-643` |
| `_format_operation_error()` | stage/error/retained paths/public states | 否 | `init.py:778-796` |

**测试验证**: `test_init_command.py:445-496` 验证 required/optional 的 secret value 均不进入 `captured.out`、`captured.err`、`redirected_stderr.getvalue()`。

### 3.2 Prompt 中的变量名可见但值不可见

Redirected stderr prompt 格式: `"{VAR_NAME}（输入隐藏，不写日志）: "` — 变量名可见（用户需知道在配置哪个变量），但读入的值从不回显。

**裁决**: 正确。这是 redirected stdin 场景下必要的可用性权衡；变量名本身不是 secret。

### 3.3 确认输出含变量名不含值

```python
print(f"dayu-cli init: 将持久化以下环境变量名（不显示值）: target={...} names={names}")
```

`names` 来自 `entry.name`（`EnvironmentPersistenceEntry.name`），不访问 `.value`。

**裁决**: 正确。测试 `test_init_command.py:445-496` 验证 `required_name in captured.out`、`optional_name in captured.out`，同时 `required_secret not in captured.out`、`optional_secret not in captured.out`。

## §4 — Test Ownership 审查

### 4.1 `test_init_command.py` 新增 7 个 owner tests

| Test | 验证目标 | Contract assertion |
| --- | --- | --- |
| `test_read_secret_input_uses_hidden_getpass_for_tty` | TTY path 使用 getpass，prompt 转发 | return value、prompt sequence |
| `test_read_secret_input_redirected_reads_exactly_one_logical_line` (×4) | Redirected line ending 处理 | LF/CRLF/bare-CR/whitespace、flush count、prompt、non-disclosure、no getpass |
| `test_redirected_secret_owner_is_reused_for_required_and_optional_values` | Call site 复用、顺序、non-disclosure | typed plan、stdin 消费、flush count、names visibility、values absence |
| `test_secret_input_eof_paths_share_value_free_owner_error` (×2) | TTY + redirected EOF 收敛 | 同一 exception type/message、value-free |
| `test_secret_input_eof_is_publicly_value_free_and_stops_before_publication` (×2) | Full CLI EOF 路径 | exit code、no config、no .dayu、no value in output |
| `test_secret_input_keyboard_interrupt_preserves_identity` (×2) | TTY + redirected interrupt | identity check (`is`)、capability 分流 |
| `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130` (×2) | Full CLI interrupt 路径 | exit 130、no persistence、no config、no .dayu |

**裁决**: 所有 tests 直接测试 production owner function 或完整的 CLI entry point。断言均为 contract 级：exact return value、exact exception type/message、exact exit code、exact state（config 不存在、`.dayu` 不存在）。不使用间接信号或碰巧相关字段。✓

### 4.2 Test fixture 不固化偶然行为

- `_TtySecretInput`: `isatty()` → `True` 是 owner contract 的 capability check 精确复制；`readline()` → `AssertionError` 是 fail-fast guard，不模拟生产行为
- `_FlushRecordingStderr`: 只增加计数而不改变 `io.StringIO` 语义
- `_InterruptingRedirectedSecretInput`: 只在 readline 边界抛 interrupt，不模拟其它 TextIOBase 行为
- `_install_tty_getpass`: 组合 stdin TTY declaration + getpass sequence，不包含隐含假设

### 4.3 已有测试的 fixture 迁移（5 处 `_GetpassSequence` → `_install_tty_getpass`）

修改前旧测试只 mock `getpass.getpass` 但不声明 TTY capability。修改后通过 `_install_tty_getpass()` 同时安装 TTY stdin 和 getpass sequence，使测试正确反映 production 实际行为。

| 旧用法 | 新用法 | 测试名 |
| --- | --- | --- |
| `monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret, "", "", "", "", "")))` | `_install_tty_getpass(monkeypatch, (secret, "", "", "", "", ""))` | `test_required_secret_refusal_stops_before_transaction_publication` |
| `monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))` | `_install_tty_getpass(monkeypatch, (secret,))` | `test_environment_persistence_failure_never_publishes_workspace` |
| `monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))` | `_install_tty_getpass(monkeypatch, (secret,))` | `test_persistence_interrupt_aborts_real_prepared_transaction_and_exits_130` |
| `monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))` | `_install_tty_getpass(monkeypatch, (secret,))` | `test_persistence_interrupt_abort_failure_reports_retained_truth_and_exits_130` |
| `monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))` | `_install_tty_getpass(monkeypatch, (secret,))` | `test_persistence_interrupt_aborts_before_broken_stderr_and_exits_130` |

以及 `_install_ollama_inputs` 内部调用从 `monkeypatch.setattr(getpass, "getpass", _GetpassSequence())` 改为 `_install_tty_getpass(monkeypatch)`。

**裁决**: 正确。这些旧测试之前隐式依赖 TTY getpass path 但没有声明 TTY capability；迁移补齐了缺失的 fixture。不改变 getpass value sequence 或业务断言。

### 4.4 `test_prompt_command.py` integration consumer

**变更**:
1. `import dayu.cli.commands.init as init_command` (line 19)
2. Module-private `_TtySecretInput(io.StringIO)` class (lines 104-120) — `io` 已存在（line 8）
3. `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())` (line 1244)

**冻结**: getpass value sequence `("", "", "", "", "")`、model input `("14", "", "", "")`、prompt/runtime assertions 完全不变。

**裁决**: 正确。只把缺失的 TTY capability 注入 integration consumer 的 stdin fixture；不修改任何业务断言或 getpass 值序列。如果 production 误入 redirected path，`_TtySecretInput.readline()` 的 `AssertionError` 会立即失败测试。

## §5 — Production Fallback / Compatibility 禁令审查

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `hasattr`/`getattr` 在 production init.py | 零命中 | `rg -n 'hasattr\|getattr' dayu/cli/commands/init.py` → 无匹配 |
| `sys.__stdin__` identity 检测 | 零命中 | `rg -n 'sys\.__stdin__' dayu/cli/commands/init.py` → 无匹配 |
| `msvcrt` 引用 | 零命中 | `rg -n 'msvcrt' dayu/cli/commands/init.py` → 无匹配 |
| pytest/mock/capture identity 检测 | 零命中 | `rg -n 'pytest\|mock\|capture' dayu/cli/commands/init.py` → 无匹配 |
| `os.name` 或 `platform.system()` 在 `_read_secret_input()` | 零使用 | `init.py:468-493` 只使用 `sys.stdin.isatty()` |
| TTY 路径失败后 fallback 到 readline | 不存在 | `init.py:478-482` 无 fallback 分支 |
| Redirected 路径失败后 fallback 到 getpass | 不存在 | `init.py:484-493` 无 fallback 分支 |
| 兼容性 re-export / wrapper / facade | 零新增 | diff 中无此类代码 |
| `_read_secret_input` 在生产代码中被 mock | 零处 | 所有测试通过 monkeypatch 控制 stdin/stderr/getpass，不 mock `_read_secret_input` 本身 |

**裁决**: 零违反。Production code 是纯 capability-based router，不识别测试框架、不保留 fallback 路径。

## §6 — Security Boundary 审查

### 6.1 SQLite/EventLog trusted-local 裁决

**当前裁决**: Config、Host internal SQLite 与 EventLog 属于 trusted-local domain。
**本轮**: `_read_secret_input()` 不读取、不写入、不迁移任何 durable store。secret value 经 `EnvironmentPersistenceEntry` → `plan_environment_persistence()` → `persist_environment()` 写入 OS 环境（setx/profile），此路径在 S1 已锁定。

**裁决**: 未扩大 durable secret 范围。✓

### 6.2 Tool Trace / audit / public / LLM-facing / operator diagnostic 明文禁令

**当前裁决**: Tool Trace、audit、public/LLM-facing/operator diagnostics 不得出现 API key/header 明文。
**本轮**: `_read_secret_input()` 不产生任何 trace event、audit event、log record。secret value 不进入任何 exception message、print 输出、或 diagnostic 文本。

**裁决**: 未新增明文投影路径。✓

### 6.3 Prompt flush 到 stderr 的内容安全

Redirected path: `sys.stderr.write(prompt)` — prompt 内容为 `"{VAR_NAME}（输入隐藏，不写日志）: "` 或 `"可选 {VAR_NAME}（留空跳过，输入隐藏）: "`。只含环境变量名，不含 secret value。

**裁决**: 安全。变量名是公共信息（`OPENAI_API_KEY` 等名称本身不是 secret）。

## §7 — Deferred / Real-Windows Boundaries 审查

| Deferred Scope | 本轮状态 | 证据 |
| --- | --- | --- |
| Issue 142, 151, 175, 177, 178 | 未实现、未预埋、未依赖 | diff 扫描零命中 |
| Web/WeChat/render | 未触及 | diff 范围不含相关路径 |
| Console/PTY/process isolation | 未引入 | forbidden token 扫描零命中 |
| setx redesign | 未修改 | `dayu/cli/init_environment.py` 零 diff |
| Unified secret/authorization framework | 未引入 | 无相关 import 或新增模块 |
| Fins generic diagnostic schema | 未触及 | diff 范围不含 Fins 路径 |
| Real Windows R11/R12 closure | 仍 pending | 本地 Darwin tests 通过；platform-dependent nodes skip |

**裁决**: 零 deferred scope 渗漏。Real Windows 仍是 `PENDING_RELEASE_BLOCKER`，唯一 destination 是 fresh R12 dispatch。

## §8 — Overcoupling / Semantic Ownership Drift 审查

### 8.1 层级依赖

- `_read_secret_input()` → `sys`, `getpass`（标准库） — 无 Dayu 内部依赖 ✓
- `_collect_environment_persistence_plan()` → `_read_secret_input()` + `init_environment` types — 同层依赖 ✓
- Test → `init_command._read_secret_input()` — 测试依赖 production owner ✓

无反向依赖。无跨层穿透调用。✓

### 8.2 语义所有权

| 语义 | Owner | 位置 | 独占性 |
| --- | --- | --- | --- |
| stdin capability 检测与分流 | `_read_secret_input()` | `init.py:468-493` | 唯一 |
| prompt 内容格式 | caller（`_collect_environment_persistence_plan`） | `init.py:510,522` | 唯一 |
| 空值业务规则（required→error, optional→skip） | `_collect_environment_persistence_plan()` | `init.py:511-512,523-524` | 唯一 |
| 环境持久化 | `init_environment` 模块（S1 owner） | 未修改 | 唯一 |
| EOF 收敛消息 | `_read_secret_input()` | `init.py:482,488` | 唯一（同一字符串） |

无 owner 重叠。无下游 fallback 修补上游语义。✓

### 8.3 测试解耦

- `test_init_command.py:_TtySecretInput` 与 `test_prompt_command.py:_TtySecretInput` 各自独立定义
- 无 shared test helper 或跨文件 import
- 符合 plan §13.4 的"不得抽 compatibility/shared production seam 或跨模块 facade"

**裁决**: 刻意解耦是正确的设计决策。DS-OBS-01 仍是 information observation，不构成 finding。

## §9 — README Boundary 审查

### 9.1 根 `README.md`

**变更**: 一句话解释 TTY vs redirected stdin 行为差异。
**边界检查**: 面向最终用户，说明两种输入方式的用户可见行为，不暴露内部实现细节或模块名。
**裁决**: 符合根 README 的用户文档边界。✓

### 9.2 `tests/README.md`

**变更**: 一段描述 real-init secret input owner 的测试矩阵和真实 Windows destination。
**边界检查**: 只记录当前 `tests/` 已存在的事实（owner test 覆盖范围、真实 Windows closure destination），不写用户手册或设计文档。
**裁决**: 符合 tests README 的维护约定边界。✓

## §10 — Edge Case 完整性审查

### 10.1 Redirected stdin 包含多条完整行但 optional 全部跳过

**场景**: 用户在 redirected stdin 中提供了所有 optional 值，但生产代码中已配置环境变量（`has_non_empty_environment_value` 为 True）则跳过读取。
**实际行为**: `_collect_environment_persistence_plan()` 对已配置的 optional 变量不调用 `_read_secret_input()`；stdin 中多余的行不会被消费，可能留在缓冲区。
**裁决**: 不构成缺陷。环境变量已配置时不应再提示输入；stdin 中未消费内容不影响 init 后续流程（model selection 由 `input()` 读取，使用独立 buffer）。

### 10.2 空行作为 required value

**场景**: redirected stdin 中 required variable 读入空行。
**实际行为**: `_read_secret_input()` 返回 `""`（`"\n"` 被 strip）；`_collect_environment_persistence_plan()` 检查 `if not required_value:` → `CliInitOperationError`。
**裁决**: 正确 fail-fast，value-free 错误消息。✓

### 10.3 多次 Ctrl+C 竞态

**场景**: 用户在 `_read_secret_input()` 中按 Ctrl+C，外层 `except KeyboardInterrupt` 处理 abort 时再次收到 SIGINT。
**实际行为**: 第二次 `KeyboardInterrupt` 会中断 abort 过程，但 Python 进程退出前不会进一步损坏状态。
**裁决**: 标准 POSIX 信号行为。`try_abort_prepared_transaction` 是 best-effort；第二次中断的 retained paths 仍会由 OS 保留。可接受。

## §11 — Findings

**0 findings。**

经完整的 adversarial 审查——producation owner TTY/redirected 分流、行结束处理、EOF 收敛、KeyboardInterrupt identity、non-disclosure 全链路、call site 复用、fixture 迁移、forbidden pattern 扫描、security boundary、deferred scope、overcoupling/semantic ownership drift、README boundary、edge case 矩阵——未发现 correctness defect、contract violation、semantic ownership drift、compatibility shim、production fallback 或 test gap。

### New findings

`0`。从零审查 immutable five-path implementation target、AgentCodex artifact、Controller validation 与完整 plan/review 链后，无新 finding。

### Backflow findings

`0`。DS-F01（rejected/no-fix）和 DS-OBS-01（information observation）在 re-review 阶段已闭合；本轮实现精确遵循 accepted plan 的 fixture 迁移范围。无回潮。

### Accepted candidate

N/A — 无 finding 需要 Controller 裁决。

### Blocker

`0`。PASS 投票（待 AgentMiMo 并发完成第二路 review 后 Controller 汇总）。

## §12 — Open Questions

`0`。Production owner contract、test coverage、security boundary、deferred scope 与 real-Windows destination 均已收敛。

## §13 — Residual Risk

| # | Risk | Severity | Owner | Destination |
| --- | --- | --- | --- | --- |
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合行为差异 | 中 | WIN4-RW-S2 | Final plan §13.8 fresh R12 dispatch；当前本地 skip 只记录平台事实 |
| R2 | caller-owned pipe/OS handle 与 CLI process memory 按输入本质暂存 secret value；本 WU 只承诺 CLI 不主动回显或投影 | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 失败或 fresh R12 在 secret 读取后出现新 failure | 低 | Controller diagnostic-first stop gate | §13.9；必须回 Controller，不复用当前 root cause 猜测 |
| R4 | Full Ruff baseline `142` 项为 entry 既有 | 信息 | 独立 Ruff cleanup WU | 本轮精确证明五元组集合与 digest 不变 |

## §14 — Protected State Summary

| Item | Value | Status |
| --- | --- | --- |
| Implementation entry HEAD | `bbb10959253fb3cb4bd22299196cf65a4a961b10` | ✓ |
| Five-path aggregate diff SHA-256 | `e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698` | ✓ MATCH |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | ✓ MATCH |
| Staged tree | empty | ✓ PASS |
| `git diff --check` | pass | ✓ PASS |
| Full pyright | `0 errors, 0 warnings, 0 informations` | ✓ PASS |
| Full CLI tests | `552 passed, 7 skipped, 3 warnings` | ✓ PASS |

## §15 — Final Verdict

**PASS**

理由：

1. **Production owner 正确**: `_read_secret_input()` 是 stdin capability-based router；TTY 使用 hidden `getpass`，redirected 使用 `readline()` with prompt→stderr→flush→read；无 pytest/mock 检测、无 fallback、无 compat shim、无 platform 特判。

2. **行结束处理精确**: 只移除一个 LF 并条件移除前导 CR；bare CR 与其它尾随空白保留。不引入 loose normalization。

3. **Non-disclosure 完整**: secret value 不进入 stdout、stderr、exception message、confirmation output、persistence diagnostic、Tool Trace、audit 或 LLM-facing 文本。所有公开输出只含变量名。

4. **EOF/Interrupt 收敛**: TTY `EOFError` 与 redirected empty-read 收敛为同一 value-free `CliInitOperationError`；`KeyboardInterrupt` identity 原样透传。

5. **Test ownership contract 级**: 7 个新增 owner tests + 2× 参数化覆盖 TTY/redirected/LF/CRLF/bare-CR/other-whitespace/flush/EOF/interrupt/required/optional/confirmation/non-disclosure；5 处旧 test fixture 迁移补齐缺失的 TTY capability 声明。所有断言为 exact contract 级。

6. **Integration consumer 精确**: `test_prompt_command.py` 只注入 TTY stdin fake + 必要 import；getpass sequence、model input、prompt/runtime 断言均冻结。TTY fake 的 `readline()` fail-fast 确保路径漂移立即暴露。

7. **Security/deferred 零渗漏**: Config/Host SQLite/EventLog 仍是 trusted-local domain；Tool Trace/audit 明文禁令保持；deferred Issues/Web/WeChat/render/PTY/setx redesign/unified secret 均未实现、未预埋、未依赖。

8. **Immutable state 完整**: 五个 payload SHA-256、five-path aggregate diff SHA-256、staged empty、`git diff --check` 全部精确匹配。

### Finding Ledger

| Finding | Status | Severity | Disposition |
| --- | --- | --- | --- |
| (none) | — | — | — |

### Next Gate

本轮 AgentDS code review 结论 **PASS / new finding 0 / backflow finding 0 / blocker 0**。待 AgentMiMo 并发完成第二路 code review 后，Controller 汇总双路结论做最终裁决。只有双路 PASS、accepted/open finding 为 0、Controller final adjudication 通过后，才可形成 accepted local commit。

在 Controller 最终裁决前，不得 stage、commit、push、dispatch、PR 或 merge。真实 Windows R12 closure 仍是 `PENDING_RELEASE_BLOCKER`，只能在 accepted local commit 与 WIN4 aggregate deepreview 闭合后 fresh dispatch。
