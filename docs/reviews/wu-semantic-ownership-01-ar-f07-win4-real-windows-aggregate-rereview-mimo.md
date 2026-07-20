# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW S1+S2 Aggregate Re-Review（AgentMiMo 第一路）

## Verdict

**PASS / 未发现实质性问题**

本次 re-review 是既有 `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07 WIN4-RW` 第一路完整 aggregate re-review，不是新 WU。AgentMiMo 从完整 unchanged six-path target、S1/S2 全链、两路 initial aggregate deepreview、Controller adjudication、AgentCodex zero-change artifact、Controller validation 与 direct workflows/code/tests/README 从零复核，未发现 blocker、new findings、backflow findings 或 semantic ownership drift。

## Scope

- Mode: Current Changes Mode（aggregate re-review）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1+S2
- Branch: `phaseflow/host-issues-control`
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Reviewed HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-aggregate-rereview-mimo.md`
- Included scope（six product/test/README paths）:
  - `dayu/cli/commands/init.py` — S2 `_read_secret_input()` owner 及其两个 call sites
  - `tests/cli/test_init_command.py` — S2 secret-input owner exact nodes + S1 fixture 迁移
  - `tests/cli/test_prompt_command.py` — S2 `test_prompt_command_uses_init_generated_workspace_config` fixture 迁移
  - `tests/cli/test_upload_filings_from_command.py` — S1 display dependency 删除 + public repository contracts
  - `README.md` — S2 用户可见 TTY/redirected 行为说明
  - `tests/README.md` — S1+S2 owner test 矩阵说明
- Excluded scope:
  - `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml` — 零 diff
  - `tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py` — 零 diff
  - `dayu/fins/**` — 零 diff
  - `docs/host/` control/plan/review artifacts — 已读取用于审查依据，不纳入 payload
- Parallel review coverage: 无（scope 有限，单 reviewer 可完整覆盖）

## Governance Inputs

本 re-review 完整读取以下治理输入，未只看摘要：

- `CLAUDE.md`（项目指令与架构硬约束）
- `docs/host/issues-implementation-control.md`（gate 状态为 `WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 S1+S2 aggregate deepreview`）
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（§13.2—§13.9 amended plan）
- WIN4-RW S1 全部 review/fix/rereview/accepted-commit artifacts
- WIN4-RW S2 全部 implementation/plan-drift/review/fix/rereview/accepted-commit artifacts
- AgentMiMo initial aggregate deepreview（365 lines / `3053b43e...a97`）
- AgentDS initial aggregate deepreview（341 lines / `21fea925...cea`）
- Controller adjudication（`65143fb1...2ca`）— accepted aggregate finding 0
- AgentCodex zero-change artifact（138 lines / `473aeb8de2420e1f46fd5c518a7dd748914a3a36f65d7e9dee577de34d94f2b8`）
- Controller validation（`4372e2e6f695468d475c6b749c9871d1ae4561df8dc226d54e353285c9ef149e`）
- S1 accepted commit `9eeb467ab45ca945882234026ef95301cd5b609d`
- S2 accepted commit `40b461410da48333670e0ca54385aa0d9dc4c79a`

## Immutable State Verification

| Item | Expected | Fresh Actual | Status |
|---|---|---|---|
| Current HEAD | `d4e092d1c3ae2110cec2d72a49013130843f7e21` | `d4e092d1c3ae2110cec2d72a49013130843f7e21` | ✓ MATCH |
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | ✓ MATCH |
| Six-path aggregate binary diff SHA-256 | `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` | `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` | ✓ MATCH |
| `README.md` content SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` content SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` content SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` content SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | ✓ MATCH |
| `tests/cli/test_upload_filings_from_command.py` content SHA-256 | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` | ✓ MATCH |
| AgentCodex zero-change artifact SHA-256 | `473aeb8de2420e1f46fd5c518a7dd748914a3a36f65d7e9dee577de34d94f2b8` | `473aeb8de2420e1f46fd5c518a7dd748914a3a36f65d7e9dee577de34d94f2b8` | ✓ MATCH |
| Controller validation SHA-256 | `4372e2e6f695468d475c6b749c9871d1ae4561df8dc226d54e353285c9ef149e` | `4372e2e6f695468d475c6b749c9871d1ae4561df8dc226d54e353285c9ef149e` | ✓ MATCH |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check` | pass | pass | ✓ PASS |

## Fresh Verification Results

| Check | Result |
|---|---|
| `pytest tests/cli/test_init_command.py -x -q` | 41 passed |
| `pytest tests/cli/test_prompt_command.py -x -q` | 45 passed |
| `pytest tests/cli/test_upload_filings_from_command.py -x -q` | 20 passed, 2 skipped（platform marker） |
| `pytest tests/cli -q`（full CLI） | 552 passed, 7 skipped |
| `pyright`（四个 changed files） | 0 errors, 0 warnings, 0 informations |
| `ruff check`（四个 changed Python files） | All checks passed! |
| Protected paths diff（workflows/fins/output/init_smoke/init_environment） | 零 diff |
| `getpass.getpass` in production | 仅 line 480 TTY 分支一次 |
| Forbidden `sys.__stdin__|msvcrt|PowerShell|Start-Process|pty|PTY|JobObject|CREATE_NEW_PROCESS_GROUP|process.tree` | 零命中（word-boundary） |
| Forbidden `shell=True|errors=replace|hasattr|getattr` | 零命中 |
| Deferred `Issue 142/151/175/177/178` | 零命中 |
| Display-added-diff scan | 零命中 |

## Findings

未发现实质性问题。

## Adversarial Re-Review Detail

本 re-review 从零复核以下全部维度，不依赖 initial deepreview 的结论作为 shortcut。

### 1. S1: Display Success Dependency 彻底删除（从零复核）

**逐行走读** `test_windows_generated_script_runs_real_cli_into_temp_storage`（lines 912–1030）：

- 旧 `assert "Fins result" in execution.stdout` 已从 diff 中删除（`-` 行）。
- 当前成功判断链：line 981 `execution.returncode == 0`（process exit）→ line 982-984 `FsCompanyMetaRepository` typed facts → line 985-990 `FsSourceDocumentRepository` unique document id → line 992-1006 snapshot identity/descriptors within `with` block → line 1007-1010 `rglob` physical integrity → line 1011-1030 oracle artifact。
- `execution.stdout` 在整个函数中零引用用于业务判断。`execution.stderr` 仅在 `assert` 失败时用作诊断信息。
- Display-added-diff scan 零命中。

**结论**：display dependency 彻底清除，零回流。**PASS**。

### 2. S1: Public Repository Contracts 正确性（从零复核）

**直接证据**（lines 982-1006）：

- `FsCompanyMetaRepository(storage)` 和 `FsSourceDocumentRepository(storage)` 是 `dayu.fins.storage` 公开导出的具体实现。
- Company facts: `get_company_meta("AAPL")` → `ticker == "AAPL"` 且 `company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME`（`"Apple Inc."`）。
- Source inventory: `list_source_document_ids("AAPL", SourceKind.FILING)` → `len == 1` → unique `document_id`。
- Snapshot: `read_source_snapshot("AAPL", document_id, SourceKind.FILING, materialize_files=False)` 在 `with` 块内断言 identity/source_kind/primary_filename/descriptors。
- 所有 import（`SourceKind`, `FsCompanyMetaRepository`, `FsSourceDocumentRepository`）来自 `dayu.fins.storage` 与 `dayu.fins.domain.enums`。
- `dayu/fins/` 相对 base 零 diff — Fins owner contract 未被修改。

**结论**：public repository 构造正确，CLI test 只消费既有 public contract。**PASS**。

### 3. S1: Storage Snapshot Lifetime（从零复核）

**直接证据**（lines 992-1006）：

- `read_source_snapshot(..., materialize_files=False)` 在 `with` context manager 内消费。
- 所有 snapshot 属性断言在 `with` 块内执行。
- 块后只有 `rglob("*")`（physical artifact count）和 oracle 写入，不访问 snapshot。

**结论**：snapshot lifetime 在 `with` 块内闭合，无泄漏。**PASS**。

### 4. S2: stdin Capability Owner 逐行走读（从零复核）

**入口**: `dayu/cli/commands/init.py:468-493`。

**TTY 路径**（line 478-482）:
- `sys.stdin.isatty()` 唯一分流点。
- `getpass.getpass(prompt)` — 标准库隐藏输入。
- `EOFError` → `CliInitOperationError("secret input ended before completion")` — value-free，`from exc` 保持 cause chain。
- `KeyboardInterrupt` / `OSError` 不捕获，原样透传。

**Redirected 路径**（line 484-493）:
- `sys.stderr.write(prompt)` + `sys.stderr.flush()` — prompt 先于读取可见。
- `sys.stdin.readline()` — 精确一次逐行读取。
- `value == ""` → EOF 收敛为同一 value-free `CliInitOperationError`。
- `value.endswith("\n")` → 移除一个 LF；`value.endswith("\r")` → 移除 LF 前的 CR（CRLF）。
- bare CR 与其它尾随空白保持，不引入 `rstrip` 或 loose normalization。

**平台中立性**：未使用 `os.name`、`platform.system()`、`sys.__stdin__`、`msvcrt`、`hasattr`、`getattr`。

**结论**：owner boundary 清晰，capability 分流由 `sys.stdin.isatty()` 唯一决定。**PASS**。

### 5. S2: Call Sites 复用（从零复核）

**直接证据**（`init.py:510, 522`）:

- Required（line 510）: 空值由 caller `_collect_environment_persistence_plan()` 拒绝（line 511-512）。
- Optional（line 522）: 空值由 caller 跳过（line 523-524）。
- Input capability owner 不管业务规则；空值判断留在 caller boundary。

**结论**：职责分离清晰，无 owner 重叠。**PASS**。

### 6. S2: prompt_command Integration Consumer（从零复核）

**直接证据**（`test_prompt_command.py:1244`）:

- `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())` 注入 strict TTY fake。
- `_TtySecretInput`（line 104-127）在该文件独立定义，`isatty()` → `True`，`readline()` → `AssertionError`。
- `getpass.getpass` mock 保留空字符串序列（line 1248）。
- 不修改同文件其它 prompt tests、getpass value sequence 或 runtime 业务断言。

**结论**：exact integration node 的 strict TTY fixture 迁移正确。**PASS**。

### 7. S1+S2 组合行为（从零复核）

| 维度 | S1 | S2 | 交叉影响 |
|---|---|---|---|
| 文件 | `test_upload_filings_from_command.py` | `init.py`, `test_init_command.py`, `test_prompt_command.py` | 零重叠 |
| Owner | public repository contracts | stdin capability owner | 独立 |
| 生产代码改动 | 无（仅测试） | `init.py` 32 行改动 | 无交叉 |
| Import | `dayu.fins.storage`, `dayu.fins.domain.enums` | `sys`, `getpass` | 无交叉 |

**结论**：S1 与 S2 完全独立，无交叉回归、无 overcoupling。**PASS**。

### 8. Workflow / Snapshot / Canary（从零复核）

- `.github/workflows/r11-upload-script-windows.yml` 相对 base 零 diff。
- `.github/workflows/r12-init-windows.yml` 相对 base 零 diff。
- 两个 workflow 的 triggers、locked install、JUnit always-upload、test collection、argv/setx/redirected-handle/artifact/canary contract 均未改变。

**结论**：workflow/snapshot/canary 不变性保持。**PASS**。

### 9. Non-Disclosure / Trusted-Local（从零复核）

| 输出路径 | 含 secret value? | 证据 |
|---|---|---|
| `sys.stderr.write(prompt)` (redirected) | 否 — 仅变量名 | `init.py:484` |
| `getpass.getpass(prompt)` (TTY) | 否 — OS 级不回显 | `init.py:480` |
| `CliInitOperationError` | 否 — 固定 value-free 文本 | `init.py:482,488` |
| `print(...)` 确认 | 否 — 仅变量名 | `init.py:537-540` |
| S1 oracle artifact | 否 — `test_node/result/sha256/count/cmd/company_name` | `test_upload_filings_from_command.py:1011-1030` |

- Config/Host internal SQLite/EventLog 继续属于 trusted-local domain。
- 本 aggregate 未新增 durable store 或 projection。
- Tool Trace/audit/public/LLM-facing/operator diagnostics 不得出现 API key/header 明文的裁决不变。

**结论**：non-disclosure 与 trusted-local 边界未被突破。**PASS**。

### 10. No Display Oracle / No Production Fallback / No Unified Authorization（从零复核）

**No display oracle**:
- 旧 `assert "Fins result" in execution.stdout` 已删除。
- 成功判断仅由 `execution.returncode == 0` + public repository typed contracts 给出。
- 不依赖 stdout/stderr display 文案、prefix、substring、regex 或 parser。

**No production fallback**:
- `rg -n 'sys\.__stdin__|msvcrt|PowerShell|Start-Process|JobObject|CREATE_NEW_PROCESS_GROUP|process\.tree'` 在全部 changed files 零命中。
- `rg -nw 'pty|PTY'` 零命中。
- `rg -n 'shell\s*=\s*True|errors\s*=\s*[^,)]*replace|hasattr\(|getattr\('` 零命中。
- `getpass.getpass` 在 production 只命中 `_read_secret_input()` TTY 分支一次。
- Production code 是纯 capability-based router。

**No unified authorization**:
- `rg -n 'unified.*secret|unified.*authorization|secret.*framework|authorization.*framework'` 零命中。
- 本 WU 只修复 stdin capability routing，不引入统一 authorization 框架。

**结论**：三者均通过。**PASS**。

### 11. Deferred Scope（从零复核）

- `rg -n 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178'` 在 changed production/test paths 零命中。
- `rg -n 'Web|WeChat|render'` 在 `init.py` / `test_init_command.py` 零命中（`test_prompt_command.py` 和 `test_upload_filings_from_command.py` 中的 `render` 引用是诊断输出变量名，不是 infrastructure）。
- 未实施 setx redesign、console/PTY/process isolation 或 Fins generic diagnostic schema。
- 未实施 unified secret/authorization infrastructure。

**结论**：deferred scope 正确，未越界。**PASS**。

### 12. Semantic Ownership Drift（从零复核）

| 语义 | Owner | 位置 | 独占性 |
|---|---|---|---|
| stdin capability 检测与分流 | `_read_secret_input()` | `init.py:468-493` | 唯一 |
| prompt 内容格式 | caller (`_collect_environment_persistence_plan`) | `init.py:510,522` | 唯一 |
| 空值业务规则 | `_collect_environment_persistence_plan()` | `init.py:511-512,523-524` | 唯一 |
| EOF 收敛消息 | `_read_secret_input()` | `init.py:482,488` | 唯一 |
| 上传成功判断 | public repository contracts | `test_upload_filings_from_command.py:982-1006` | 唯一 |
| Display 文案 | 已删除 | — | 无 owner |

无 owner 重叠。无下游 fallback 修补上游语义。无跨层穿透调用。无反向依赖。

**结论**：semantic ownership drift 未发生。**PASS**。

### 13. New / Backflow Finding 检查

本 re-review 相对 initial aggregate deepreview 检查是否存在 new finding 或 backflow finding：

- **New finding**: 无。Six-path payload 未变（content SHA-256 全部 MATCH），fresh tests/type/lint/scans 结果与 initial deepreview 一致。
- **Backflow finding**: 无。Controller adjudication 裁决的 accepted aggregate finding 为 0；AgentCodex zero-change artifact 确认 zero-change disposition；Controller validation 确认 unchanged six-path target。

**结论**：new finding 0，backflow finding 0。**PASS**。

### 14. MiMo Initial Next-Gate 文字裁决

Initial aggregate deepreview 的 next-gate 文字写为 "aggregate deepreview 完成后，push、fresh R11/R12 dispatch"。Controller adjudication 已明确指出该文字不具授权效力，固定流程仍需 zero-change aggregate fix record → Controller validation → 双路完整 aggregate re-review → accepted evidence commit，之后才可 push。

本 re-review 确认：固定流程已正确执行至当前步骤（zero-change fix + Controller validation 已完成，本 re-review 是双路 aggregate re-review 之一）。该文字裁决不构成 backflow finding。

**结论**：文字裁决已由 Controller 纠正，不构成 blocker。**PASS**。

### 15. Overcoupling（从零复核）

- S1 仅修改一个测试文件，不涉及生产代码。
- S2 仅修改 `init.py` 的一个函数和两个 call sites，加上对应的测试和文档。
- 两个 slice 的文件集合零重叠。
- `_TtySecretInput` 在 `test_init_command.py` 与 `test_prompt_command.py` 各自独立定义（§13.3 明确要求的 test-local 解耦）。
- 无 shared helper、无 shared fake、无跨文件 import、无 shared mutable state。

**结论**：无 overcoupling。**PASS**。

### 16. Residual Owners 验证

| Residual | Owner / Destination | 状态 |
|---|---|---|
| R1: Darwin 不能证明 Windows console/redirected handle 组合 | §13.8 fresh R11/R12 | PENDING；owner unit tests 已锁定 capability contract |
| R2: caller-owned pipe/OS handle 暂存 secret | 独立安全设计 | 不在本 WU scope |
| R3: fresh remote 新失败 | Controller diagnostic-first stop gate | 当前 root cause 已知 |
| R4: Ruff 142 baseline / coverage miss | 独立 cleanup / owner tests | 不是 current finding |

Residual 的数量、owner 和 destination 与 Controller adjudication 及 AgentCodex zero-change artifact 一致。

**结论**：residual owners 无漂移。**PASS**。

## Open Questions

无。

## Residual Risk

| # | Risk | Severity | Owner | Destination |
|---|---|---|---|---|
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合行为差异 | 中 | WIN4-RW | Final plan §13.8 fresh R12 dispatch |
| R2 | caller-owned pipe/OS handle 与 CLI process memory 按输入本质暂存 secret value；本 WU 只承诺 CLI 不主动回显或投影 | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 失败或 fresh R12 在 secret 读取后出现新 failure | 低 | Controller diagnostic-first stop gate | §13.9；必须回 Controller |
| R4 | Full Ruff 142 项为 entry 既有 baseline | 信息 | 独立 Ruff cleanup WU | 本轮精确证明六元组集合与 digest 不变 |
| R5 | S1 `test_windows_generated_script_runs_real_cli_into_temp_storage` 被 `@pytest.mark.skipif(os.name != "nt")` 标记，本机 macOS 无法执行 | 中 | WIN4-RW | Fresh R11 闭合 |

## Review Conclusion

- **PASS/FAIL**: PASS
- **Severity**: 无
- **New findings**: 0
- **Backflow findings**: 0
- **Blocker**: 0
- **Open**: 0
- **Residual owner/destination**: 见 Residual Risk — 与 initial deepreview 及 Controller adjudication 一致
- **Immutable state**: HEAD `d4e092d1c3ae2110cec2d72a49013130843f7e21`，aggregate base `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`，staged empty，six-path aggregate binary diff SHA-256 `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` MATCH
- **Fixed next gate**: 双路 aggregate re-review 完成后，Controller final adjudication → accepted evidence commit → push / fresh R11/R12

## Review Metadata

- Reviewer: AgentMiMo
- Review type: aggregate re-review（第一路，非新 WU）
- Review date: 2026-07-20
- Review time: 08:39:52 +0800
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Reviewed HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- Six-path aggregate binary diff SHA-256: `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361`
- AgentCodex zero-change artifact SHA-256: `473aeb8de2420e1f46fd5c518a7dd748914a3a36f65d7e9dee577de34d94f2b8`
- Controller validation SHA-256: `4372e2e6f695468d475c6b749c9871d1ae4561df8dc226d54e353285c9ef149e`
- S1 code review (MiMo): PASS
- S1 code rereview (MiMo): PASS
- S2 code review (MiMo): PASS
- S2 code rereview (MiMo): PASS
- S2 plan drift review (MiMo): PASS
- S2 plan drift rereview (MiMo): PASS
- Aggregate deepreview (MiMo): PASS
- Aggregate re-review (MiMo): PASS
