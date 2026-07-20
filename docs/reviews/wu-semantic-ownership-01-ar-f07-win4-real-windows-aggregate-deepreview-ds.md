# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW S1+S2 Aggregate Deepreview（AgentDS）

## Scope

- Mode: current changes（aggregate deepreview of accepted WIN4-RW S1 + WIN4-RW S2 implementation）
- Branch: `phaseflow/host-issues-control`
- HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- Base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-aggregate-deepreview-ds.md`
- Review date/time: 2026-07-20T08:13:32+08:00
- Included scope: exact six product/test/README paths（aggregate binary diff SHA `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361`）:
  - `README.md`
  - `dayu/cli/commands/init.py`
  - `tests/README.md`
  - `tests/cli/test_init_command.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_upload_filings_from_command.py`
- Excluded scope: 全部 control/review/plan artifacts、`.github/workflows/`、`dayu/fins/`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、`dayu/cli/output.py` 及其他非 allowlist 路径。这些 excluded paths 的相对 base 的 diff 经 `git diff --stat` 确认为零。
- Parallel review coverage: 无。本 review 是 Controller 授权的单路完整 aggregate deepreview（第二路 DS），与 AgentMiMo 并行独立执行。
- Staged/worktree: clean（`git status --short` 零输出）。

## Governance Inputs

本 review 完整读取以下治理输入：

- `AGENTS.md` / `CLAUDE.md`（项目指令与架构硬约束）
- `docs/host/issues-implementation-control.md`（当前 gate 状态为 `WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 S1+S2 aggregate deepreview`）
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（§13.2—§13.9 amended plan）
- `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`（R11 独立计划）
- `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`（R12 独立计划）
- WIN4-RW S1 全部 review/fix/rereview/accepted-commit artifacts（Controller adjudication 已全部闭合）
- WIN4-RW S2 全部 implementation/plan-drift/review/fix/rereview/accepted-commit artifacts（Controller adjudication 已全部闭合）
- S1 accepted commit `9eeb467ab45ca945882234026ef95301cd5b609d`
- S2 accepted commit `40b461410da48333670e0ca54385aa0d9dc4c79a`

本 review 不重新裁决已闭合的 S1、S2 review 链 findings；只检查六路径 aggregate 中是否存在交叉回归、语义所有权漂移、过度耦合、未覆盖边界或 deferred scope 渗漏。

## Findings

### 1. 未发现实质性问题

经完整六路径 aggregate deepreview，在以下全部审查维度中均未发现 material finding：

#### 1.1 WIN4-RW-S1: process-exit + public storage published-fact success owner

- **入口/函数**: `test_windows_generated_script_runs_real_cli_into_temp_storage`
- **文件**: `tests/cli/test_upload_filings_from_command.py:979-1033`
- **审查结论**: PASS，零 finding

直接证据链：

1. 旧 `assert "Fins result" in execution.stdout` 已被删除（diff line `-    assert "Fins result" in execution.stdout`）。未新增任何 stdout/stderr display text、prefix、substring、regex 或 parser 断言。display-added-diff scan（`rg '^\+.*(Fins (result|summary|progress|succeeded|failure|cancelled)|execution\.(stdout|stderr))'`）返回 exit 1（零命中），证实零新增 display assertion。

2. `execution.returncode == 0` 保留为 OS process exit 事实的真源。失败时仍使用 `execution.stderr` 帮助 test failure，不把 stdout 文案推导为 success/document id/stage/root cause。

3. 业务成功由两个同源事实共同证明：
   - `FsCompanyMetaRepository(storage).get_company_meta("AAPL")` → `ticker == "AAPL"` 且 `company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME`
   - `FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)` → 唯一 published filing document id
   - `source_repository.read_source_snapshot(..., materialize_files=False)` → 在 `with` 块内确认 exact ticker、document id、`SourceKind.FILING`、primary filename、descriptor 集合非空

4. `source_artifacts`（`portfolio/` 下 `rglob`）保留为 physical integrity count，不承担业务 success 语义。

5. Company-name pre-execution oracle `_assert_single_windows_upload_company_name()` 仍在执行前逐 token 证明 exact one `Apple Inc.`；comment-only/零条/多条 business command 继续 fail closed。

6. 新增 import（`SourceKind`, `FsCompanyMetaRepository`, `FsSourceDocumentRepository`）全部来自 `dayu.fins.storage` 与 `dayu.fins.domain.enums`——CLI test 只消费既有 Fins public contract，不重复测试 Fins owner 自身的 close-after-use 语义。

7. Fins production code（`dayu/fins/`）相对 base 零 diff，确认未修改 Fins owner contract。

8. `dayu/cli/output.py` 相对 base 零 diff，确认未修改 CLI output owner。

#### 1.2 WIN4-RW-S2: stdin capability secret-input owner 组合行为

- **入口/函数**: `_read_secret_input` → `_collect_environment_persistence_plan`
- **文件**: `dayu/cli/commands/init.py:468-493`
- **审查结论**: PASS，零 finding

直接证据链：

1. Capability 分流以 `sys.stdin.isatty()` 为唯一判断条件，平台中立（未使用 `os.name`/`platform.system()`/`sys.__stdin__`/`msvcrt`）：
   - `isatty() == True` → `getpass.getpass(prompt)`（隐藏输入，不回显）
   - `isatty() == False` → prompt 写入 `sys.stderr` 并 flush，然后 `sys.stdin.readline()` 恰好一次

2. `getpass.getpass` 在 `init.py` 中只出现在 `_read_secret_input()` 的 TTY 分支（line 480），确认零冗余调用。

3. Line ending 处理精确遵守 §13.2.2 contract：
   ```python
   if value.endswith("\n"):
       value = value[:-1]
       if value.endswith("\r"):
           value = value[:-1]
   ```
   - LF → 移除 `\n`，无 trailing `\r` → 干净值
   - CRLF → 移除 `\n`，再移除 `\r` → 干净值
   - bare CR → `endswith("\n")` 为 False → 不移除 → 保留 trailing `\r`
   - 未使用 `rstrip` 或等价过度删除操作

4. EOF 收敛：TTY 路径 `EOFError` 与 redirected 路径 `readline() == ""` 均转成同一 value-free `CliInitOperationError("secret input ended before completion")`，不投影 prompt/secret/raw buffer/raw exception text。

5. `KeyboardInterrupt` 不捕获、不改写，由现有 CLI owner 映射为 exit `130`。

6. Required 空行继续 value-free fail closed；optional 空行继续 skip；`OPTIONAL_ENVIRONMENT_NAMES` 顺序、已有环境跳过规则、names-only preview、最终 `_confirm()` 与 confirmed typed plan 顺序不变。

7. Forbidden patterns scan 全部零命中：
   - `sys.__stdin__|msvcrt|PowerShell|Start-Process|pty|PTY|JobObject|CREATE_NEW_PROCESS_GROUP|process.tree` → exit 1（零命中） 在 `init.py`, `test_init_command.py`, `test_prompt_command.py` 中
   - `shell=True|errors=replace|hasattr(|getattr(` → exit 1（零命中）
   - `getpass.getpass` → 仅在 line 480 TTY 分支命中一次

8. `_TtySecretInput` 在 `test_init_command.py` 与 `test_prompt_command.py` 各有一份独立定义——这是 §13.3 明确要求的 test-local 解耦，不是代码重复。两个文件各拥有自己的 capability fake，确保 `isatty()` 恒为 `True` 且 `readline()` 误入即 assertion 失败，互不耦合。

#### 1.3 R11/R12 workflow 不变性

- **审查结论**: PASS，零 finding

`.github/workflows/r11-upload-script-windows.yml` 与 `.github/workflows/r12-init-windows.yml` 相对 base 零 diff（`git diff --stat` 确认）。两个 workflow 的现有 triggers、locked install、JUnit always-upload、test collection、argv/setx/redirected-handle/artifact/canary contract 均未改变。

#### 1.4 Storage snapshot lifetime

- **文件**: `tests/cli/test_upload_filings_from_command.py:992-1009`
- **审查结论**: PASS，零 finding

`read_source_snapshot(..., materialize_files=False)` 在 `with` context manager 内消费（line 992—1009），snapshot identity/source kind/primary filename/descriptors 只在 public `with` lifecycle 内读取。CLI test 不重复增加 Fins close-after-use owner test。

#### 1.5 LLM/public/audit/tool trace non-disclosure

- **审查结论**: PASS，零 finding

1. Secret value 在以下输出通道中零命中（由 dynamic owner tests 使用随机 `secrets.token_urlsafe(24)` 验证，非固定 blacklist）：
   - stdout：`assert required_secret not in captured.out` / `assert optional_secret not in captured.out`
   - stderr：`assert required_secret not in redirected_stderr.getvalue()` / `assert optional_secret not in redirected_stderr.getvalue()`
   - exception text：`assert raw_exception_value not in str(raised.value)`（EOF error）/ `assert raw_exception_value not in captured.err`
   - `_read_secret_input` 不把 secret 写回任何输出流：TTY 路径只调用隐藏 `getpass`，redirected 路径只写 prompt 到 stderr（不含 value），从 stdin 读取 value 后不写回

2. Config/Host internal SQLite/EventLog 仍属 trusted-local domain，本次 diff 不读取、不迁移、不重写、不扩大 durable secret 范围。

3. Tool Trace/audit/public/LLM-facing/operator log 继续禁止 API key/header 明文；本次 diff 不创建新的 projection 或放宽既有裁决。

#### 1.6 SQLite/EventLog/config trusted-local 裁决

- **审查结论**: PASS，零 finding

本次六路径 diff 不涉及 SQLite/EventLog 读写、config schema 变更或 durable secret 扩大。Config loader、Host durable state、LLM-facing projection 的 trusted-local 裁决不变。

#### 1.7 无 display 成功 oracle

- **审查结论**: PASS，零 finding

旧 `assert "Fins result" in execution.stdout` 已删除。未新增任何 stdout/stderr display text、prefix、substring、regex 或 parser 断言。业务成功仅由 `execution.returncode == 0` + public Fins storage facts 证明。display-added-diff scan 零命中。

#### 1.8 无 production pytest/mock fallback

- **审查结论**: PASS，零 finding

Production `_read_secret_input()` 仅使用标准库 `sys.stdin.isatty()`、`sys.stdin.readline()`、`sys.stderr.write()`/`flush()` 与 `getpass.getpass()`。无 test-only production seam、无 callback/factory/profile 参数、无 `hasattr`/`getattr` 探测、无 `sys.__stdin__` 模拟。

Tests 使用 `pytest.monkeypatch` 在模块 lookup boundary 替换 `sys.stdin`/`sys.stderr`/`getpass.getpass`——这是标准 test isolation，不是 production 中的 test shim。

#### 1.9 无 unified secret/authorization

- **审查结论**: PASS，零 finding

`_read_secret_input()` 只拥有 secret 值的读取和 EOF/interrupt 语义，不拥有 environment persistence、registry、Config、Host durable state、authorization 或通用 secret lifecycle。未新增 `dayu.runtime` secret helper、credential broker、zeroization 或 unified authorization infrastructure。deferred scan（`rg 'authorization|secret infrastructure'`）在 changed paths 中零命中。

#### 1.10 Deferred Issues 142/151/175/177/178 与 Web/WeChat/render 无渗漏

- **审查结论**: PASS，零 finding

Deferred scan（`rg 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|web_tools_storage_states'`）在全部 changed production/test paths 中零命中（exit 1）。`dayu/web/`、`dayu/wechat/`、`dayu/render/` 的删除已在 R11 独立完成，不在本次 WIN4 diff 范围。Web/WeChat/render placeholder 能力未恢复。

#### 1.11 Semantic ownership drift

- **审查结论**: PASS，零 finding

逐一核验 semantic owner map：

| 语义 | 唯一 owner | 当前实现 | 漂移？ |
|---|---|---|---|
| secret input 能力分流 | `dayu/cli/commands/init.py::_read_secret_input` | `sys.stdin.isatty()` 精确分流，TTY→getpass，redirected→stderr+readline | 无 |
| secret value 的 EOF/interrupt | 同上 | 两种 EOF 收敛为同一 value-free error；KeyboardInterrupt 原样透传 | 无 |
| environment persistence plan | `_collect_environment_persistence_plan` | 两处调用 `_read_secret_input`，required/optional 语义不变 | 无 |
| upload success oracle | OS process exit + Fins public storage repositories | `returncode == 0` + `FsCompanyMetaRepository` + `FsSourceDocumentRepository` public contract | 无（已从 display consumer 迁走） |
| company-name requirement | `dayu/fins/pipelines/upload_company_meta.py` | Fins production 零 diff，fail-closed 不变 | 无 |
| company-name pre-execution oracle | `_assert_single_windows_upload_company_name` | 逐 token 证明 exact one `Apple Inc.`，comment/零条/多条 fail closed | 无 |

无下游 fallback、特例、重复计算、loose parsing、兼容 shim 或测试固化补救上游 contract。

#### 1.12 Overcoupling

- **审查结论**: PASS，零 finding

- `_TtySecretInput` 在两个 test 文件中独立定义，无共享 helper/constant module——这是 §13.3 的明确要求（test-local 解耦），不是耦合。
- CLI test 只消费 Fins public storage contract（`FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`read_source_snapshot`），不依赖 Fins 内部实现、raw JSON、private core path 或 `rglob` 反推业务事实。
- 六路径之间无新增跨层依赖、无反向 import、无 shared mutable state、无过宽公共契约。

#### 1.13 交叉回归

- **审查结论**: PASS，零 finding

Full CLI test suite: `552 passed, 7 skipped`（全部 skip 为 Windows-only real nodes 在 macOS 上的平台 skip，非 regression）。init_command focused: `41 passed`。prompt_command focused: 通过（包含在 full CLI 中）。test_upload_filings_from_command focused: `20 passed, 2 skipped`（2 skipped 为 Windows-only real nodes）。pyright full: `0 errors, 0 warnings, 0 informations`。Ruff scoped（四个 changed Python files）: `All checks passed!`。git diff --check: exit 0。

#### 1.14 Stop conditions

- **审查结论**: PASS，零 finding

All plan §13 stop conditions 经实际 diff 验证：

- `dayu/cli/output.py` 零 diff ✓
- `dayu/cli/init_environment.py` 零 diff ✓
- `tests/cli/test_init_smoke.py` 零 diff ✓
- `.github/workflows/r11-upload-script-windows.yml` 零 diff ✓
- `.github/workflows/r12-init-windows.yml` 零 diff ✓
- `dayu/fins/` 全部 production paths 零 diff ✓
- 无 `sys.__stdin__` / `msvcrt` / PowerShell / PTY / JobObject 新增 ✓
- 无 `shell=True` / `errors=replace` / `hasattr` / `getattr` 新增 ✓
- 无 deferred Issue 142/151/175/177/178 渗漏 ✓
- 无 `capture_output=True` 新增 ✓
- `getpass.getpass` 仅在 TTY 分支命中一次 ✓

#### 1.15 Remote residual owners

- **审查结论**: PASS（local），真实 Windows closure pending

| Residual | Owner/Destination | 状态 |
|---|---|---|
| 非 Windows 本地无法证明 CPython 3.11 Windows console 与 redirected handle 的真实组合 | §13.8 fresh R12 workflow_dispatch | PENDING_RELEASE_BLOCKER；owner unit tests 已锁定 capability contract |
| caller-owned pipe、OS handle 与 CLI process memory 暂存 secret | 独立安全设计（不在本 WU scope） | 已记录为 §13.9 residual risk #2 |
| fresh R11/R12 exit/storage owner facts 失败时需 diagnostic-first stop | §10 diagnostic-first stop gate | 当前 root cause 已知，不预先增加 diagnostic infra |

### 2. Coverage、type 与 lint 验证

#### 2.1 Coverage

`dayu/cli/commands/init.py`: `91%` line coverage（311 statements, 26 missed, 100 branches, 11 partial）。超过 `>=80%` 阈值。

Miss 区域分析（line 427-436 custom OpenAI 交互输入、line 191-210 catalog exception handlers 等）均为交互式用户输入路径或 catalog 文件缺失异常路径，在自动化测试中难以覆盖。这些路径由 CLI 真实 smoke 覆盖。

#### 2.2 Pyright

Full pyright: `0 errors, 0 warnings, 0 informations`。

#### 2.3 Ruff

Scoped Ruff（四个 changed Python files）: `All checks passed!`。Full Ruff baseline: 142 findings，均为 immutable baseline（非本次 diff 引入）。WU-SEMANTIC-OWNERSHIP-01 整个 umbrella 期间 Ruff 基线从 144 降为 142，系其他 sub-WU 的合法清理，不属本次 WIN4 diff。

#### 2.4 Git diff

`git diff --check 8fafe9bad4828c83fa6cf80a1dc2199fe78472d9..d4e092d1c3ae2110cec2d72a49013130843f7e21`: exit 0。Staged tree empty。

### 3. Permuted Owner Contract 验证

#### 3.1 Secret input contract matrix

| 场景 | Test | 验证结果 |
|---|---|---|
| TTY hidden getpass | `test_read_secret_input_uses_hidden_getpass_for_tty` | PASS: getpass 序列正确，prompt 匹配，stdin.readline 未调用 |
| LF line ending | `test_read_secret_input_redirected_reads_exactly_one_logical_line[lf]` | PASS: `\n` 移除，stderr flush 一次 |
| CRLF line ending | `test_read_secret_input_redirected_reads_exactly_one_logical_line[crlf]` | PASS: `\r\n` 移除 |
| bare CR | `test_read_secret_input_redirected_reads_exactly_one_logical_line[bare-cr]` | PASS: `\r` 保留 |
| trailing whitespace | `test_read_secret_input_redirected_reads_exactly_one_logical_line[other-trailing-whitespace]` | PASS: ` \t` 保留 |
| required+optional 复用 | `test_redirected_secret_owner_is_reused_for_required_and_optional_values` | PASS: 两个调用点复用同一 owner，flush 计数=2 |
| TTY EOF→value-free error | `test_secret_input_eof_paths_share_value_free_owner_error[tty]` | PASS: EOFError→CliInitOperationError，value 未泄漏 |
| redirected EOF→value-free error | `test_secret_input_eof_paths_share_value_free_owner_error[redirected]` | PASS: readline=""→同 error |
| TTY EOF stops publication | `test_secret_input_eof_is_publicly_value_free_and_stops_before_publication[tty]` | PASS: exit=1, config/.dayu 未创建 |
| redirected EOF stops publication | `test_secret_input_eof_is_publicly_value_free_and_stops_before_publication[redirected]` | PASS: exit=1, config/.dayu 未创建 |
| TTY KeyboardInterrupt identity | `test_secret_input_keyboard_interrupt_preserves_identity[tty]` | PASS: interrupt object identity 保持 |
| redirected KeyboardInterrupt identity | `test_secret_input_keyboard_interrupt_preserves_identity[redirected]` | PASS: interrupt object identity 保持 |
| TTY interrupt→exit 130 | `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[tty]` | PASS: exit=130, persistence 未调用 |
| redirected interrupt→exit 130 | `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[redirected]` | PASS: exit=130, persistence 未调用 |
| prompt_command integration | `test_prompt_command_uses_init_generated_workspace_config` | PASS: strict TTY stdin fake, readline 误入 assertion 失败 |

#### 3.2 Upload success oracle contract matrix

| 场景 | Test | 验证结果 |
|---|---|---|
| process exit 0 + storage facts | `test_windows_generated_script_runs_real_cli_into_temp_storage` | macOS skip（platform），但 code path 经 review 确认 |
| no display assertion | display-added-diff scan | 零命中 |
| company-name pre-execution oracle | `_assert_single_windows_upload_company_name` | 保留，逐 token 证明 |
| snapshot within `with` | `read_source_snapshot(..., materialize_files=False)` | `with` context manager，正确 |
| Fins production zero diff | `git diff --stat -- dayu/fins/` | 零 diff |

## Open Questions

无。

当前 owner、输入能力分流、EOF/interrupt、slice allowlist、storage snapshot lifetime、LLM/public/audit/tool trace non-disclosure、trusted-local 裁决、display oracle 移除、deferred scope 隔离与 remote residual owners 均已收敛。

## Residual Risk

1. **真实 Windows closure pending**: 两个 real Windows nodes（`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`、`test_windows_generated_script_runs_real_cli_into_temp_storage`）在 macOS 上 skip（平台事实）。真实 Windows 组合行为（CPython 3.11 Windows console + redirected handle）的唯一 destination 是 §13.8 fresh R11/R12 workflow_dispatch。本地 owner tests 已锁定 capability contract，但最终 closure 仍需 remote runner evidence。

2. **Caller-owned pipe/OS handle secret 残留**: 本 WU 只承诺 CLI 不主动回显或投影 secret value，不承诺外部 shell/process inspection 安全。扩大 transport threat model 需独立安全设计。

3. **Ruff baseline 从 144→142**: 两个 finding 的减少来自 WU-SEMANTIC-OWNERSHIP-01 umbrella 下其他 sub-WU 的合法清理（`dayu/cli/commands/session.py:70:F401` 等），不属本次 WIN4 diff。Aggregate verification 确认 scoped Ruff 零新增。

4. **Coverage gap**: `init.py` 中交互式 custom OpenAI 输入路径（line 427-436）与 catalog exception handlers（line 191-210）未被自动化 owner tests 覆盖。这些路径由 CLI 真实 smoke 间接验证，不构成 blocker。

## Aggregate Verdict

**PASS — 0 new finding / 0 backflow finding / 0 blocker**

### Evidence summary

| 验证项 | 结果 |
|---|---|
| Full CLI tests | `552 passed, 7 skipped` |
| init_command focused | `41 passed` |
| upload_filings_from focused | `20 passed, 2 skipped` |
| init.py coverage | `91%` (≥80%) |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff (4 changed Python files) | `All checks passed!` |
| `git diff --check` | exit 0 |
| Staged tree | empty |
| display-added-diff scan | 零命中 |
| Forbidden patterns scan | 零命中（production paths） |
| Deferred issues scan | 零命中 |
| `getpass.getpass` call sites | 仅 TTY 分支一次 |
| Workflow files diff | 零 diff |
| test_init_smoke.py diff | 零 diff |
| init_environment.py diff | 零 diff |
| dayu/cli/output.py diff | 零 diff |
| Fins production diff | 零 diff |

### Immutable state

- Six-path aggregate binary diff SHA: `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361`
- S1 accepted commit: `9eeb467ab45ca945882234026ef95301cd5b609d`
- S2 accepted commit: `40b461410da48333670e0ca54385aa0d9dc4c79a`
- Aggregate HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- S1 five-payload binary diff: `71855b78...4d3d`（不变）
- S2 five-payload binary diff: `e66bf366...698`（不变）
- Six-path allowed paths manifest: 不变（等于 §13.3 WIN4-RW-S1 + WIN4-RW-S2 allowlist 的并集）

### Next gate

Controller adjudication。若 Controller 接受本 aggregate deepreview PASS（与 AgentMiMo 并行 DS 路结果对齐），则：

1. 关闭 WIN4-RW S1+S2 aggregate deepreview gate。
2. AgentCodex 处理全部 accepted aggregate findings（当前为零，仍需留 record）。
3. 双路 aggregate re-review。
4. Closure 后才可 push 与 fresh R11/R12 workflow_dispatch。

真实 Windows closure 必须等待 §13.8 fresh R11/R12 rerun，并由 Controller 按 §9.3 执行独立 same-run canary scan。Local PASS 不声称 cross-platform closure。
