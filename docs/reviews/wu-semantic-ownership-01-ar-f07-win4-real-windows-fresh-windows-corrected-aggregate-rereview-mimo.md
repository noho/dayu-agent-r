# Code Review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Corrected Aggregate Re-Review（AgentMiMo 第一路）

## Review Identity

- **Reviewer**: AgentMiMo
- **Review type**: WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 corrected aggregate 第一路完整 re-review，不是新 WU
- **Aggregate base**: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- **Reviewed HEAD**: `de68672b803c4e355d2a18b0fbc2890497053230`
- **Six-path binary/full-index diff SHA-256**: `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` ✓ 已独立验证
- **Six-path sorted path-list SHA-256**: `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` ✓ 已独立验证
- **Latest accepted implementation**: `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` ✓ 已独立验证
- **Zero-change fix artifact**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-deepreview-fix-codex.md` / `1584fbc7...` ✓
- **Controller fix validation**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-deepreview-fix-controller-validation.md` / `90806625...` ✓
- **Review timestamp**: 2026-07-20T10:43:16+08:00

## Scope

- **Mode**: Current Changes Mode（corrected aggregate re-review）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-rereview-mimo.md`
- **Included scope**（six product/test/README paths）:
  - `README.md` — S2 用户可见 TTY/redirected 行为说明
  - `dayu/cli/commands/init.py` — S2 `_read_secret_input()` owner 及其两个 call sites
  - `tests/README.md` — S1+S2 owner test 矩阵说明
  - `tests/cli/test_init_command.py` — S2 secret-input owner exact nodes + S1 fixture 迁移
  - `tests/cli/test_prompt_command.py` — S2 `test_prompt_command_uses_init_generated_workspace_config` fixture 迁移
  - `tests/cli/test_upload_filings_from_command.py` — S1 display dependency 删除 + public repository contracts + RF01 primary/raw-source independent contract
- **Excluded scope**:
  - `.github/workflows/` — 零 diff
  - `tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py` — 零 diff
  - `dayu/fins/**` — 零 diff
  - `docs/host/` control/plan/review artifacts — 已读取用于审查依据，不纳入 payload
- **Parallel review coverage**: 无（scope 有限，单 reviewer 可完整覆盖）

## Review Chain Context

本 corrected aggregate re-review 完整消费以下链路：

1. 旧 WIN4 S1 全链（implementation → code review → code rereview → accepted commit `9eeb467a`）
2. 旧 WIN4 S2 全链（implementation → plan drift review → plan drift rereview → code review → code rereview → accepted commit `40b46141`）
3. 旧 aggregate deepreview 双路（MiMo + DS）→ Controller adjudication → zero-change fix → Controller validation
4. 旧 aggregate re-review 双路（MiMo + DS）→ Controller adjudication → accepted evidence commit `6964d99b`
5. Fresh Windows failure adjudication → corrected plan → plan correction review/fix/rereview 全链
6. RF01 test oracle implementation → code review → code rereview → accepted commit `32906841`
7. RF01 accepted commit Controller validation（`PASS / AGGREGATE_DEEPREVIEW_REQUIRED`）
8. Corrected aggregate deepreview 双路（MiMo + DS）→ Controller adjudication（`PASS / ACCEPTED_AGGREGATE_FINDING=0`）
9. AgentCodex zero-change fix record（`PASS / ZERO-CHANGE FIX RECORD`）
10. Controller zero-change fix validation（`PASS / ZERO_CHANGE_FIX_ACCEPTED / AGGREGATE_PAYLOAD_UNCHANGED / READY_FOR_DUAL_COMPLETE_AGGREGATE_REREVIEW`）
11. 当前 HEAD `de68672b`（docs: authorize AR-F07 WIN4 corrected aggregate review）

## Governance Inputs

本 re-review 完整读取以下治理输入：

- `CLAUDE.md`（项目指令与架构硬约束）
- `AGENTS.md`（代理执行约束）
- `docs/host/issues-implementation-control.md`
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（§13.2—§13.9 amended plan）
- WIN4-RW S1 全部 review/fix/rereview/accepted-commit artifacts
- WIN4-RW S2 全部 implementation/plan-drift/review/fix/rereview/accepted-commit artifacts
- Fresh Windows failure adjudication + corrected plan 全链
- RF01 test oracle implementation/review/fix/rereview/accepted-commit 全链
- Corrected aggregate deepreview MiMo（452 lines / PASS / finding 0）
- Corrected aggregate deepreview DS（492 lines / PASS / finding 0）
- Controller corrected aggregate adjudication（PASS / ACCEPTED_AGGREGATE_FINDING=0）
- AgentCodex zero-change fix record（125 lines / PASS）
- Controller zero-change fix validation（PASS / AGGREGATE_PAYLOAD_UNCHANGED）

## Immutable State Verification

| Item | Expected | Fresh Actual | Status |
|---|---|---|---|
| Current HEAD | `de68672b803c4e355d2a18b0fbc2890497053230` | `de68672b803c4e355d2a18b0fbc2890497053230` | ✓ MATCH |
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | ✓ MATCH |
| Six-path binary diff SHA-256 | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | ✓ MATCH |
| Six-path sorted path-list SHA-256 | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | ✓ MATCH |
| Latest accepted implementation | `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` | `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` | ✓ MATCH |
| Zero-change fix SHA-256 | `1584fbc748387b9e30487f40e0395c5e68cf01175e84cdfe8cea5fc393db8537` | `1584fbc748387b9e30487f40e0395c5e68cf01175e84cdfe8cea5fc393db8537` | ✓ MATCH |
| Controller fix validation SHA-256 | `90806625b3c0caf400fbf58a277201702d4028334cff42388f1720d37d328b5d` | `90806625b3c0caf400fbf58a277201702d4028334cff42388f1720d37d328b5d` | ✓ MATCH |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check`（六路径） | PASS | PASS | ✓ PASS |
| Working-tree `git diff --check` | PASS | PASS | ✓ PASS |

### Per-file content SHA-256

| File | SHA-256 | Corrected Aggregate Deepreview | Delta |
|---|---|---|---|
| `README.md` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485...` | 零 diff |
| `dayu/cli/commands/init.py` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a96...` | 零 diff |
| `tests/README.md` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de0131...` | 零 diff |
| `tests/cli/test_init_command.py` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84...` | 零 diff |
| `tests/cli/test_prompt_command.py` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df2...` | 零 diff |
| `tests/cli/test_upload_filings_from_command.py` | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `3827b569...` | 零 diff |

六个文件的 SHA-256 与 corrected aggregate deepreview（MiMo 第一路）完全一致。AgentCodex zero-change fix 未修改任何 payload 文件；Controller validation 确认 `AGGREGATE_PAYLOAD_UNCHANGED`。

## Fresh Verification Results

| Check | Result |
|---|---|
| `pytest tests/cli/test_init_command.py -x -q` | 41 passed |
| `pytest tests/cli/test_prompt_command.py -x -q` | 45 passed |
| `pytest tests/cli/test_upload_filings_from_command.py -x -q` | 20 passed, 2 skipped（platform marker） |
| `pytest tests/cli -q`（full CLI） | 552 passed, 7 skipped |
| `pyright`（四个 changed Python files） | 0 errors, 0 warnings, 0 informations |
| `ruff check`（四个 changed Python files） | All checks passed! |
| `init.py` coverage | 92%（311 statements / 26 missed / ≥80%） |
| Protected paths diff（workflows/fins/output/init_smoke/init_environment/runtime/config/engine/host/service/ui） | 零 diff |
| `getpass.getpass` in production | 仅 line 480 TTY 分支一次 |
| Forbidden `sys.__stdin__|msvcrt|PowerShell|Start-Process|PTY|JobObject|CREATE_NEW_PROCESS_GROUP|process.tree`（added lines whole-word） | 零命中 |
| Forbidden `shell=True|errors=replace|hasattr|getattr`（added lines） | 零命中 |
| Deferred `Issue 142/151/175/177/178` | 零命中 |
| `unified.*secret|unified.*authorization` | 零命中 |
| Display-added-diff scan | 零命中 |
| Staged tree | empty |
| Working-tree diff-check | PASS |

## Findings

未发现实质性问题。

## Adversarial Aggregate Re-Review Detail

### 1. Upload Script 跨平台 Grammar/argv/Company-Name/Public Storage Facts 与 RF01 Primary/Raw-Source Independent Contract 组合

**从零复核 `test_windows_generated_script_runs_real_cli_into_temp_storage`（lines 912–1041）**:

**S1 display dependency 彻底删除**:
- 旧 `assert "Fins result" in execution.stdout` 已删除。
- 成功判断链：line 981 `execution.returncode == 0`（OS process exit）→ line 982-984 `FsCompanyMetaRepository` typed facts → line 985-990 `FsSourceDocumentRepository` unique document id → line 992-1017 snapshot identity/descriptors/sha256 within `with` block → line 1018-1021 `rglob` physical integrity → line 1022-1041 oracle artifact。
- `execution.stdout` 在整个函数中零引用用于业务判断。

**RF01 primary/raw-source independent contract**:
- Line 1003-1008: `primary_descriptors` 独立 tuple comprehension，`descriptor.name == snapshot.primary_filename` exact match，`assert len(primary_descriptors) == 1`。
- Line 1009-1017: `raw_source_descriptors` 独立 tuple comprehension，`descriptor.name == source_path.name` exact match，`assert len(raw_source_descriptors) == 1`，`raw_source_descriptor.sha256 is not None` + exact hash match。
- 两段是独立 comprehension、独立变量作用域、独立 `len == 1` 断言。
- 旧断言 `snapshot.primary_filename == source_path.name` 已删除 —— Fins 合法选择不同 descriptor 为 primary 时不再失败。
- `hashlib` 已在文件头部导入（line 6），无新增 import。

**Fail-closed 验证表**:

| 输入条件 | primary 断言 | raw-source 断言 | 结果 |
|---|---|---|---|
| `primary_filename` 不匹配任何 descriptor | `len=0` → fail | 独立 | 正确 fail |
| `source_path.name` 不匹配任何 descriptor | 独立 | `len=0` → fail | 正确 fail |
| 同一 name 出现两次 | `len=2` → fail | `len=2` → fail | 正确 fail |
| `sha256` 为 `None` | 独立 | `is not None` → fail | 正确 fail |
| `sha256` 与 fixture 不一致 | 独立 | 等式 fail | 正确 fail |
| primary==raw（同一 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |
| primary≠raw（不同 descriptor） | `len=1` | `len=1`，sha256 通过 | 正确 pass |

**S1 与 RF01 组合行为**: S1 删除 display dependency、改用 public repository contracts；RF01 修正 snapshot assertion block 使 primary/raw-source 独立。两者修改同一函数的不同行范围，RF01 在 S1 基础上工作，不引入冲突。

**结论**: 通过。

### 2. Init Provider/Model/API Key、Redirected stdin/TTY/setx/Atomic/Reset 用户工作流

**从零复核 `_read_secret_input()`（`init.py:468-493`）**:

- TTY 路径: `sys.stdin.isatty()` → `getpass.getpass(prompt)` → `EOFError` → `CliInitOperationError`（value-free）。`KeyboardInterrupt`/`OSError` 不捕获，原样透传。
- Redirected 路径: `sys.stderr.write(prompt)` + `sys.stderr.flush()` → `sys.stdin.readline()` 一次 → `value == ""` EOF 收敛 → `endswith("\n")` 移除 LF → `endswith("\r")` 移除 CRLF 的 CR。bare CR 与其它尾随空白保持，不引入 `rstrip`。
- 平台中立性: 未使用 `os.name`、`platform.system()`、`sys.__stdin__`、`msvcrt`、`hasattr`、`getattr`。

**Call sites（`init.py:510, 522`）**:
- Required: 空值由 caller `_collect_environment_persistence_plan()` 拒绝（line 511-512）。
- Optional: 空值由 caller 跳过（line 523-524）。
- Input capability owner 不管业务规则；空值判断留在 caller boundary。

**README.md 变更**: 描述从"会隐藏输入值"扩展为"TTY 隐藏输入值；stdin 被重定向时，每个 secret 提示写入 stderr，并从 stdin 逐项读取一行，CLI 不把值写回 stdout/stderr"。准确反映实现行为。

**结论**: 通过。

### 3. Trusted-Local Config/Host Durable API Key/Header 允许存在，但 Tool Trace/audit/Public/LLM/Log/Review Evidence 不得明文；不得误报统一 Secret Infrastructure

**各输出路径 secret 泄露检查**:

| 输出路径 | 含 secret value? | 证据 |
|---|---|---|
| `sys.stderr.write(prompt)` (redirected) | 否 — 仅变量名 | `init.py:484` |
| `getpass.getpass(prompt)` (TTY) | 否 — OS 级不回显 | `init.py:480` |
| `CliInitOperationError` | 否 — 固定 value-free 文本 | `init.py:482,488` |
| `print(...)` 确认 | 否 — 仅变量名 | `init.py:537-540` |
| S1 oracle artifact | 否 — `test_node/result/sha256/count/cmd/company_name` | `test_upload_filings_from_command.py:1022-1037` |
| S1 snapshot assertions | 否 — hash 比较，不暴露内容 | `test_upload_filings_from_command.py:1016-1017` |

**Config/Host internal SQLite/EventLog**: 继续属于 trusted-local domain。本 aggregate 未新增 durable store 或 projection。

**统一 secret infrastructure 检查**: `rg -n 'unified.*secret|unified.*authorization'` 在全部 changed files 零命中。本 WU 只修复 stdin capability routing，不引入统一 authorization 框架。

**结论**: 通过。

### 4. R11/R12 Workflow Metadata/Artifact Integrity/Same-Run Value-Free Canary/Storage State/Reset 边界

- `.github/workflows/r11-upload-script-windows.yml` 相对 base 零 diff。
- `.github/workflows/r12-init-windows.yml` 相对 base 零 diff。
- 两个 workflow 的 triggers、locked install、JUnit always-upload、test collection、argv/setx/redirected-handle/artifact/canary contract 均未改变。
- R11/R12 的 same-run value-free canary 设计不变。
- Storage state/reset 边界不受本 aggregate 影响。

**结论**: 通过。

### 5. Topic 1-7 Accepted Decisions 是否仍满足；Topic 8-9 No-Code；Issue 142/151/175/177/178 与 Web/WeChat/Render Tracker 没有偷带

**Topic 1-7 验证**:

| Topic | Decision | 本 aggregate 是否满足 |
|---|---|---|
| T1: stdin capability 分流 | TTY hidden getpass / redirected line read | ✓ `init.py:478-493` |
| T2: LF/CRLF/bare CR 处理 | 条件移除，不 strip | ✓ `init.py:489-492` |
| T3: EOF 收敛 | value-free 统一错误 | ✓ `init.py:482,488` |
| T4: prompt flush | redirected 时 stderr.flush() | ✓ `init.py:485` |
| T5: KeyboardInterrupt 透传 | 原样传播 | ✓ docstring + tests |
| T6: required/optional 顺序 | caller 按序调用 | ✓ `init.py:510,522` |
| T7: 值不进入公开输出 | 零泄露 | ✓ §3 above |

**Topic 8-9**: No-code（不在本 WU scope）。`rg -n` 在 changed files 中无命中。

**Issue 142/151/175/177/178**: `rg -n 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178'` 在 changed production/test paths 零命中。Web/WeChat/render: `init.py` / `test_init_command.py` 零命中。

**结论**: 通过。

### 6. No Compatibility/Fallback/Downstream Repair/LLM-facing Drift

**No compatibility code**:
- 无兼容性 re-export、兼容性常量 re-export、兼容性 wrapper/facade。
- `_TtySecretInput` 在 `test_init_command.py` 与 `test_prompt_command.py` 各自独立定义（test-local 解耦）。
- `_install_tty_getpass` helper 只在 `test_init_command.py` 中定义和使用。

**No fallback**:
- `sys.stdin.isatty()` 是唯一分流点，无 fallback、特例、`hasattr`/`getattr`。
- Production code 是纯 capability-based router。

**No downstream repair**:
- 旧 `assert "Fins result" in execution.stdout` 已删除，成功判断完全基于 public repository typed facts。
- `_read_secret_input()` 不修补 caller 的业务语义；caller 自己决定空值处理。

**No LLM-facing drift**:
- README.md 变更准确反映实现行为，无漂移。
- tests/README.md 变更准确描述 owner test 矩阵。
- 无 tool schema、memory/compact/trace/evidence material 变更。

**结论**: 通过。

### 7. Security Mechanisms 保留且没有统一 Tool Authorization Framework

**Security mechanisms 保留**:
- TTY hidden getpass（`getpass.getpass`）标准库安全输入保留。
- Redirected stdin 不回显（stderr prompt + stdin read，不 echo back）。
- Secret 值不写入 workspace（`init.py:537-540` confirmation 只显示变量名）。
- Secret 值不进入 success/failure output。
- POSIX managed block / Windows setx 持久化机制不变。
- Config/Host internal 属于 trusted-local domain。

**No unified tool authorization framework**:
- `rg -n 'unified.*secret|unified.*authorization|secret.*framework|authorization.*framework'` 零命中。
- 本 WU 只修复 stdin capability routing。

**结论**: 通过。

### 8. Correctness/Stability/Maintainability、Cross-Slice State/Owner Handoff、Semantic Ownership Drift、Overcoupling、Adversarial Failure Pass

**Correctness**:
- `_read_secret_input()` 逻辑简单、路径清晰：isatty → getpass 或 stderr+readline → line ending 处理 → return/raise。
- Call sites 复用同一 owner，职责分离清晰。
- Upload test 公共仓储断言覆盖 company meta、source document、snapshot identity、descriptors、sha256。

**Stability**:
- 所有错误路径（EOF、KeyboardInterrupt、OSError）有明确处理或透传。
- 测试覆盖 TTY/redirected 分流、LF/CRLF/bare CR、EOF 收敛、KeyboardInterrupt identity、required/optional 顺序、值不进入公开输出。

**Maintainability**:
- `_read_secret_input()` 是模块级私有辅助函数，职责单一。
- Test fakes（`_TtySecretInput`、`_FlushRecordingStderr`、`_InterruptingRedirectedSecretInput`）在各自 test module 内独立定义。
- 无 God object/function/dataclass。

**Cross-slice state/owner handoff**:
- S1（upload test）与 S2（init secret input）文件集合零重叠。
- S1 owner: public repository contracts。S2 owner: stdin capability owner。独立，无交叉。
- RF01 在 S1 基础上修正 snapshot assertion，不与 S2 交叉。

**Semantic ownership drift**:

| 语义 | Owner | 位置 | 独占性 |
|---|---|---|---|
| stdin capability 检测与分流 | `_read_secret_input()` | `init.py:468-493` | 唯一 |
| prompt 内容格式 | caller (`_collect_environment_persistence_plan`) | `init.py:510,522` | 唯一 |
| 空值业务规则 | `_collect_environment_persistence_plan()` | `init.py:511-512,523-524` | 唯一 |
| EOF 收敛消息 | `_read_secret_input()` | `init.py:482,488` | 唯一 |
| 上传成功判断 | public repository contracts | `test_upload_filings_from_command.py:982-1017` | 唯一 |
| primary/raw-source 独立性 | Fins storage contract | `test_upload_filings_from_command.py:1003-1017` | 唯一 |
| Display 文案 | 已删除 | — | 无 owner |

无 owner 重叠。无下游 fallback 修补上游语义。无跨层穿透调用。无反向依赖。

**Overcoupling**:
- S1 仅修改一个测试文件，不涉及生产代码。
- S2 仅修改 `init.py` 的一个函数和两个 call sites，加上对应的测试和文档。
- RF01 仅修改 S1 测试文件中的 snapshot assertion block。
- `_TtySecretInput` 在 `test_init_command.py` 与 `test_prompt_command.py` 各自独立定义。
- 无 shared helper、无 shared fake、无跨文件 import、无 shared mutable state。

**Adversarial failure pass**:
- 缺失必填参数: `_collect_environment_persistence_plan` 在 required_value 为空时 raise。
- EOF: TTY EOFError 和 redirected empty read 收敛为同一 value-free 错误。
- KeyboardInterrupt: 原样透传，映射 exit 130。
- Duplicate descriptors: `len > 1` 断言失败。
- Zero hit descriptors: `len == 0` 断言失败。
- sha256 None: `is not None` guard fail-closed。
- sha256 mismatch: 等式 fail。
- 空 stdin: redirected `readline()` 返回 `""`，触发 EOF 错误。
- bare CR: 保持，不被 strip。
- 已终态再次推进: 不适用（stateless 函数）。

**结论**: 通过。

### 9. Fresh 本地测试/pyright/Ruff/README 与真实 Windows Pending Evidence 充分性

| Validation | Fresh Result | Status |
|---|---|---|
| `pytest tests/cli/test_init_command.py -x -q` | 41 passed | ✓ PASS |
| `pytest tests/cli/test_prompt_command.py -x -q` | 45 passed | ✓ PASS |
| `pytest tests/cli/test_upload_filings_from_command.py -x -q` | 20 passed, 2 skipped | ✓ PASS |
| `pytest tests/cli -q`（full CLI） | 552 passed, 7 skipped | ✓ PASS |
| `pyright`（四个 changed Python files） | 0 errors, 0 warnings, 0 informations | ✓ PASS |
| `ruff check`（四个 changed Python files） | All checks passed! | ✓ PASS |
| `init.py` coverage | 92% | ✓ PASS |
| `git diff --check` | PASS | ✓ PASS |

**README 一致性**:
- `README.md` 变更准确描述 TTY/redirected 行为。
- `tests/README.md` 变更准确描述 owner test 矩阵。
- 两个 README 的变更范围与代码变更一致。

**真实 Windows pending evidence**:
- `test_windows_generated_script_runs_real_cli_into_temp_storage` 被 `@pytest.mark.skipif(os.name != "nt")` 标记。
- macOS 无法执行 `cmd.exe`，Windows exact node 显示 `PLATFORM SKIP`。
- Owner tests 已锁定 capability contract（TTY/redirected 分流、LF/CRLF/bare CR、EOF、interrupt）。
- 真实 Windows 验证需在 accepted implementation commit 后通过 fresh R11/R12 workflow 执行。

**结论**: 通过（真实 Windows 仍 pending，见 Residual Risk）。

### 10. 所有旧/新 Review Findings 是否关闭，有无 New/Backflow/Blocker/Residual Owner 缺口

**旧 review findings 状态**:

| Review Chain | Findings | Status |
|---|---|---|
| S1 code review (MiMo) | 0 | CLOSED |
| S1 code rereview (MiMo) | 0 | CLOSED |
| S2 code review (MiMo) | 0 | CLOSED |
| S2 code rereview (MiMo) | 0 | CLOSED |
| S2 plan drift review (MiMo) | 0 | CLOSED |
| S2 plan drift rereview (MiMo) | 0 | CLOSED |
| Aggregate deepreview (MiMo) | 0 | CLOSED |
| Aggregate deepreview (DS) | 0 | CLOSED |
| Aggregate re-review (MiMo) | 0 | CLOSED |
| Aggregate re-review (DS) | 0 | CLOSED |
| RF01 code review (MiMo) | 0 | CLOSED |
| RF01 code rereview (MiMo) | 0 | CLOSED |
| RF01 code review (DS) | 0 | CLOSED |
| RF01 code rereview (DS) | 0 | CLOSED |
| Corrected aggregate deepreview (MiMo) | 0 | CLOSED |
| Corrected aggregate deepreview (DS) | 0 | CLOSED |
| Corrected aggregate Controller adjudication | 0 accepted | CLOSED |
| AgentCodex zero-change fix | 0 product change | CLOSED |
| Controller zero-change validation | PASS | CLOSED |

**New finding**: 无。六个 payload 文件 SHA-256 与 corrected aggregate deepreview 完全一致。AgentCodex zero-change fix 未修改任何 payload。Controller validation 确认 `AGGREGATE_PAYLOAD_UNCHANGED`。Fresh tests/type/lint/scans 结果与 corrected deepreview 一致。

**Backflow finding**: 无。Controller adjudication 裁决的 accepted aggregate finding 为 0。AgentCodex zero-change artifact 确认 zero-change disposition。Controller validation 确认 `ZERO_CHANGE_FIX_ACCEPTED`。无代码回流。

**Blocker**: 无。

**Residual owner 缺口**: 无新增。既有 residual owners（见 §Residual Risk）与 corrected deepreview 及 Controller adjudication 一致。

**结论**: 通过。

## Open Questions

无。

## Finding / New / Backflow / Blocker / Open / Unclassified Residual Ledger

| Category | Count | Status |
| --- | ---: | --- |
| Accepted finding | `0` | CLOSED |
| New finding | `0` | CLOSED |
| Backflow finding | `0` | CLOSED |
| Blocker | `0` | CLOSED |
| Open | `0` | CLOSED |
| Unclassified residual | `0` | CLOSED |
| Unique remote residual | `AR-F07-WIN-REMOTE` | Controller → fresh R11/R12 |

## Residual Risk

| # | Risk | Severity | Owner | Destination |
|---|---|---|---|---|
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合行为差异 | 中 | WIN4-RW | Final plan §13.8 fresh R12 dispatch |
| R2 | caller-owned pipe/OS handle 与 CLI process memory 按输入本质暂存 secret value；本 WU 只承诺 CLI 不主动回显或投影 | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 失败或 fresh R12 在 secret 读取后出现新 failure | 低 | Controller diagnostic-first stop gate | §13.9；必须回 Controller |
| R4 | Full Ruff 142 项为 entry 既有 baseline | 信息 | 独立 Ruff cleanup WU | 本轮精确证明六元组集合与 digest 不变 |
| R5 | S1 `test_windows_generated_script_runs_real_cli_into_temp_storage` 被 `@pytest.mark.skipif(os.name != "nt")` 标记，本机 macOS 无法执行 | 中 | WIN4-RW | Fresh R11 闭合 |
| R6 | RF01 snapshot assertion block 在 macOS 上只验证到 `materialize_files=False` 的 snapshot 层，真实 Windows cmd.exe 执行路径的完整闭环未被本地覆盖 | 中 | WIN4-RW | Fresh R11 闭合 |

Residual 的数量、owner 和 destination 与 corrected deepreview、Controller adjudication 及 AgentCodex zero-change fix 一致。

## Non-Finding / No-Action

- **POSIX assertion asymmetry**: 兄弟测试 `test_posix_generated_script_runs_real_cli_into_temp_storage` 不包含 snapshot/descriptor 断言。Pre-existing / out-of-scope / non-finding / no-action。
- **pipe/OS handle/process memory 对 secret 的短暂持有**: 在用户已裁决的当前 threat model 之外；`NO ACTION`，不创建"独立安全设计 WU"。
- **Full Ruff 142 entry baseline**: 已证明零新增；`PRE_EXISTING / NON_FINDING / NO ACTION`，不创建 cleanup WU。
- **`init.py` coverage 92%**: 高于 `>=80%` 门槛且关键 owner tests 已覆盖；未覆盖行不是当前 finding，拒绝新 coverage WU。
- **POSIX sibling display assertion**: `execution.stdout.count("Fins succeeded")` 在 aggregate base 之前存在且未被本 range 修改；`PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO ACTION`，不创建 sub-WU。

## Verification Ledger

| 项目 | 值 | 验证方式 |
|---|---|---|
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | `git rev-parse` |
| Reviewed HEAD | `de68672b803c4e355d2a18b0fbc2890497053230` | `git rev-parse HEAD` |
| Six-path binary diff SHA-256 | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | `LC_ALL=C git diff --binary --full-index` |
| Six-path sorted path-list SHA-256 | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | `LC_ALL=C sort + shasum -a 256` |
| Latest accepted implementation | `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` | `git log --oneline` |
| Zero-change fix artifact | `1584fbc748387b9e30487f40e0395c5e68cf01175e84cdfe8cea5fc393db8537` | AgentCodex artifact |
| Controller fix validation | `90806625b3c0caf400fbf58a277201702d4028334cff42388f1720d37d328b5d` | Controller artifact |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `hashlib.sha256` |
| `init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `hashlib.sha256` |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `hashlib.sha256` |
| `test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `hashlib.sha256` |
| `test_prompt_command.py` SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `hashlib.sha256` |
| `test_upload_filings_from_command.py` SHA-256 | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `hashlib.sha256` |
| Full CLI tests | 552 passed, 7 skipped | `pytest tests/cli -q` |
| Pyright | 0 errors, 0 warnings, 0 informations | `pyright <four files>` |
| Ruff | All checks passed! | `ruff check <four files>` |
| `init.py` coverage | 92% | `pytest --cov` |
| `git diff --check`（六路径） | PASS | `git diff --check base...HEAD` |
| Working-tree diff-check | PASS | `git diff --check` |
| Staged tree | empty | `git diff --cached --name-only` |
| Protected paths diff | 零 diff | `git diff --stat base..HEAD` |
| Forbidden patterns（added lines whole-word） | 零命中 | `grep ^+ | grep -cw` |
| Deferred issues | 零命中 | `grep ^+` |
| Display-added-diff | 零命中 | `grep ^+` |

## Verdict

**PASS**

- **Finding**: 0
- **New**: 0
- **Backflow**: 0
- **Blocker**: 0
- **Open**: 0
- **Unclassified residual**: 0
- **Unique remote residual**: `AR-F07-WIN-REMOTE`（Controller → fresh R11/R12）

## Correct Next Gate

Controller adjudication → accepted aggregate evidence commit → push → fresh R11/R12 workflow_dispatch。不得直接 PR / closeout。

## Review Metadata

- Reviewer: AgentMiMo
- Review type: corrected aggregate re-review（第一路，非新 WU）
- Review date: 2026-07-20
- Review time: 10:43:16 +0800
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Reviewed HEAD: `de68672b803c4e355d2a18b0fbc2890497053230`
- Six-path binary/full-index diff SHA-256: `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd`
- Six-path sorted path-list SHA-256: `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf`
- Latest accepted implementation: `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5`
- Zero-change fix artifact: `1584fbc748387b9e30487f40e0395c5e68cf01175e84cdfe8cea5fc393db8537`
- Controller fix validation: `90806625b3c0caf400fbf58a277201702d4028334cff42388f1720d37d328b5d`
- S1 code review (MiMo): PASS
- S1 code rereview (MiMo): PASS
- S2 code review (MiMo): PASS
- S2 code rereview (MiMo): PASS
- S2 plan drift review (MiMo): PASS
- S2 plan drift rereview (MiMo): PASS
- Aggregate deepreview (MiMo): PASS
- Aggregate re-review (MiMo): PASS
- RF01 code review (MiMo): PASS
- RF01 code rereview (MiMo): PASS
- Corrected aggregate deepreview (MiMo): PASS
- Corrected aggregate re-review (MiMo): PASS
