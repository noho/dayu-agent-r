# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Fixed Plan Re-Review — AgentMiMo

## Review metadata

- Timestamp（本机时钟）：`2026-07-20 05:56:27 +0800`。
- Reviewer：AgentMiMo（第一路完整 re-review）。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4` real-Windows
  diagnostic bounded amendment；不是新 WU，不 implementation。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，1060 行，SHA-256
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。
- Plan before fix：1045 行，SHA-256 `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Frozen remote code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Locked evidence runs：R11 `29703932798`；R12 `29703933666`。
- AgentMiMo initial review：SHA-256 `6782a69f3fa47e895c47321f3c8674050357afea0a48cede474682617b9aca36`。
- AgentDS initial review：SHA-256 `7df6dbf7e8b12b705611b85f97a35fe9655b96b39e124f02716100ba5b8e7e91`。
- Controller adjudication：SHA-256 `80c4966b839c968e3fa75cbac1271f8019d9d88c962281a6d9bb33134259ae15`。
- AgentCodex fix artifact：SHA-256 `be72dbfd708722e799b13b237be2459c68baee8ea29dc03cf130c0c9df90e902`。
- Controller fix validation：SHA-256 `34fe315b68e710bec75db5e76f5f2298c2830640e08d1d65fc15bfd4f450b984`。
- Conclusion：`PASS / NO_BLOCKER / NO_NEW_FINDINGS / WIN4-RW-PR-F01..F04_ALL_CLOSED / IMPLEMENTATION_NOT_AUTHORIZED`。

本 review artifact 不实施 production/test/workflow 变更，不更新 control/design/README，不 stage、commit、push、dispatch
或操作 PR。

## Reviewed inputs and evidence scope

已完整读取（从零完整 review，未只看四处 diff）：

- `AGENTS.md`；
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` 全部 1060 行；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-mimo.md`（初审）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-ds.md`（DS 初审）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-controller-adjudication.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-codex.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-controller-validation.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`；
- `docs/host/issues-implementation-control.md`（current gate/state）。

直接代码/测试/仓储/workflow evidence 核对：

- `dayu/cli/output.py` L63：`_FINS_EVENT_SUMMARY_PREFIX = "Fins summary"` — display prefix 由 output owner 拥有；
- `tests/cli/test_upload_filings_from_command.py` L964-989：旧 `assert "Fins result" in execution.stdout`（L965）、
  `execution.returncode == 0`（L964）、`source_artifact_count` rglob（L966-968）、oracle 写入（L970-989）；
- `dayu/cli/commands/init.py` L90：`CliInitOperationError(RuntimeError)` 定义；L482、L494：两处 `getpass.getpass()` 调用；
- `tests/cli/test_init_command.py` L135-167：`_GetpassSequence`；L250-273：`_install_ollama_inputs` monkeypatch
  `getpass.getpass` 和 `builtins.input`，不操作 `sys.stdin`；
- `tests/cli/test_init_smoke.py` L61：`_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes）；
  L585-670：`_run_init()` anonymous TemporaryFile handles、Popen lifecycle、timeout cleanup；
- `dayu/fins/storage/repository_protocols.py` L87-126：`SourceSnapshotProtocol` 显式 context manager（`__enter__`/`__exit__`）；
  L128-134：`ticker` property；L136-：`document_id`、`source_kind`、`primary_filename`、`files` properties；
- `dayu/fins/storage/fs_company_meta_repository.py`：`__init__(workspace_root: Path, *, file_store=None, repository_set=None)`；
- `dayu/fins/storage/fs_source_document_repository.py`：`__init__(workspace_root: Path, ...)`、`read_source_snapshot()`；
- CPython 3.11 `getpass.py`：`win_getpass()` 在 `sys.stdin is not sys.__stdin__` 时 fallback。

R12 run-specific canary 未读取、派生或回显。未读取 GitHub Secrets 或 configured production values。

## 1. WIN4-RW-PR-F01..F04 closure verification

### WIN4-RW-PR-F01 — SourceSnapshot context manager — CLOSED

- **初审来源**：AgentMiMo F-01、AgentDS DS-F02。
- **Controller 裁决**：`ACCEPTED / PLAN-ONLY / LOW`。
- **fixed plan 位置**：§13.2.1 第 3 点（L753-756）、§13.5.1（L849-850）。
- **修正内容**：冻结 `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`；
  identity、source kind、primary filename 与 descriptors 只在 `with` 块内读取。明确 CLI test 不重复增加 Fins
  close-after-use owner test。
- **验证**：§13.2.1 第 3 点文字精确包含 `with` 语句与 `as snapshot`；§13.5.1 第 3 点明确"只在 public `with`
  lifecycle 内读取"。`SourceSnapshotProtocol` 是显式 context manager（`__enter__`/`__exit__`），
  `__exit__` 释放 publication guard 和 temp resources。
- **是否有回归**：否。Plan 没有引入绕过 context manager 的替代方案。
- **状态**：`CLOSED`。

### WIN4-RW-PR-F02 — 既有 getpass tests TTY path 保证 — CLOSED

- **初审来源**：AgentMiMo F-02、AgentDS DS-F01。
- **Controller 裁决**：`ACCEPTED / PLAN-ONLY / MEDIUM`。
- **fixed plan 位置**：§13.4 WIN4-RW-S2（L828-832）、§13.5.2（L858-863）。
- **修正内容**：受影响既有 getpass tests 必须把 production 实际读取的 `sys.stdin` 替换为 test-owned 严格 typed
  TTY fake；`isatty()` 恒为 `True`，`readline()` 一旦被调用立即 assertion 失败。不得 mock production
  `_read_secret_input`，不得修改或依赖 `sys.__stdin__`，也不得依赖本机/CI ambient TTY。redirected owner
  tests 使用真实 `io.StringIO` 或等价严格 typed stream，显式保证 `isatty() == False`。
- **验证**：
  - 当前 `_install_ollama_inputs`（L250-273）只 monkeypatch `getpass.getpass` 和 `builtins.input`，不操作
    `sys.stdin`。引入 `_read_secret_input` 后，production code 调用链变为
    `_read_secret_input() → sys.stdin.isatty()`；当 `isatty()` 为 False 时走 redirected path，monkeypatch
    不生效。
  - Fixed plan 明确要求替换 `sys.stdin` 为 TTY fake。`io.StringIO` 的 `isatty()` 恒为 `False`，作为 redirected
    test stream 合适。
  - pytest 默认 `sys.stdin` 在 terminal 中 `isatty()` 为 True，但在 CI 中可能为 False；fixed plan 的 test-owned
    fake 消除了环境依赖。
  - `_read_secret_input` 的 TTY path 调用 `getpass.getpass(prompt)`，`getpass.getpass` 的 monkeypatch 生效；
    redirected path 调用 `sys.stdin.readline()`，使用 `io.StringIO` 可控。
- **是否有回归**：否。Plan 明确禁止 mock `_read_secret_input`、修改 `sys.__stdin__`、依赖 ambient TTY。
- **code-generation-ready 判断**：TTY fake class 是标准 Python，`isatty()` 返回 `True`，`readline()` 抛
  `AssertionError`；`io.StringIO` 是标准库。两者在 typing 和 pytest 下无歧义。
- **状态**：`CLOSED`。

### WIN4-RW-PR-F03 — EOF 表现显式收敛 — CLOSED

- **初审来源**：AgentMiMo F-03。
- **Controller 裁决**：`ACCEPTED / PLAN-ONLY / LOW`。
- **fixed plan 位置**：§13.2.2 第 3 点（L775-777）、§13.5.2（L866-868）。
- **修正内容**：TTY path 只捕获 `getpass.getpass()` 抛出的 `EOFError`；redirected path 只把 `readline() == ""`
  识别为 EOF。两者都在 helper 内收敛为同一个 value-free
  `CliInitOperationError("secret input ended before completion")`。`KeyboardInterrupt` 不捕获、不改写。
- **验证**：
  - TTY `getpass.getpass()` EOF → `EOFError`（CPython `fallback_getpass()`）。
  - Redirected `io.StringIO.readline()` EOF → `""`（标准库行为）。
  - `CliInitOperationError` 继承 `RuntimeError`（L90），不含 prompt/secret/raw buffer/raw exception text。
  - 当前 `run_init_command` 的 except 链已有 `except CliInitOperationError: return EXIT_FAILURE`。
- **是否有回归**：否。两种 EOF 表现明确分别指定，implementation agent 不需自行推断。
- **状态**：`CLOSED`。

### WIN4-RW-PR-F04 — bare CR 保留 — CLOSED

- **初审来源**：AgentDS DS-F03。
- **Controller 裁决**：`ACCEPTED / PLAN-ONLY / LOW`。
- **fixed plan 位置**：§13.2.2 第 2 点（L770-774）、§13.5.2（L864-865）、§13.6.1（after L903-904）、
  §13.6.3（after L928-929）、completion report（after L1056-1057）。
- **修正内容**：只有实际移除了末尾单个 `\n`，且新末尾是 `\r` 时，才继续移除该单个 `\r`。孤立 trailing `\r`
  原样保留。增加 bare-CR preservation owner test；禁止 `rstrip` 或等价过度删除。
- **验证**：
  - 算法：(1) 移除末尾 `\n` → (2) 若步骤 1 确实移除了 `\n` 且新末尾是 `\r`，移除该 `\r`。
  - `"value\r\n"` → 步骤 1 移除 `\n` → `"value\r"` → 步骤 2 移除 `\r` → `"value"` ✓
  - `"value\n"` → 步骤 1 移除 `\n` → `"value"` → 步骤 2 无 `\r` → `"value"` ✓
  - `"value\r"` → 步骤 1 无 `\n` 不操作 → `"value\r"` → 步骤 2 未移除 `\n` 故不移除 `\r` → `"value\r"` ✓
  - `"value"` → 无变化 ✓
  - 与 plan 自声明的"其它前导、尾随空白与字符原样保留"一致。
  - §13.5.2 明确"孤立 trailing `\r` 原样保留并有 bare-CR owner test"。
  - §13.6.1、§13.6.3 与 completion report 增加 bare-CR evidence 要求。
- **是否有回归**：否。算法正确，禁止 `rstrip` 约束明确。
- **状态**：`CLOSED`。

## 2. 1060 行 fixed plan 整体自洽性验证

### Root cause / owner 自洽

- WIN4-RW-F01：display assertion 不是 upload-success owner → success oracle 迁移到 process exit + public storage
  facts。Owner：`tests/cli/test_upload_filings_from_command.py`。§0、§13.1.1、§13.2.1、§13.4 WIN4-RW-S1 一致。
- WIN4-RW-F02：redirected secret input 在 CLI owner boundary 缺失 → 按 stdin capability 分流 TTY/redirected。
  Owner：`dayu/cli/commands/init.py`。§0、§13.1.2、§13.2.2、§13.4 WIN4-RW-S2 一致。
- 两者 root cause 不同、owner 不同、blast radius 不同。

### 精确 2 slices 自洽

- WIN4-RW-S1：只改 `tests/cli/test_upload_filings_from_command.py`。
- WIN4-RW-S2：改 `dayu/cli/commands/init.py`、`tests/cli/test_init_command.py`、`README.md`、`tests/README.md`。
- §13.3 allowlist 精确锁定上述路径。两个 slices 语义 owner、允许路径、blast radius 与独立验证矩阵不同，不得合并。
- §13.0 明确"精确增加 `2` 个 implementation slices"。

### Allowlist 自洽

- §13.3 禁止修改 `dayu/cli/output.py`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、Fins production、
  workflows、control/design/review artifacts、`dayu.runtime`、unified authorization、PowerShell/PTY/console wrapper 等。
- 与 §3.2 原始禁止路径一致，无扩大、无缩小。

### 顺序自洽

- §13.0："保持用户指定的 S1→S2 串行顺序"。
- §13.4 WIN4-RW-S1 Dependencies："无代码依赖"。
- §13.4 WIN4-RW-S2 Dependencies："无 S1 代码依赖，但按 S1→S2 串行实施。只有两 slice 均 accepted 后才允许
  aggregate validation 和 remote rerun"。

### README 自洽

- §13.7：`README.md` 在 WIN4-RW-S2 更新（secret input 行为说明）；`tests/README.md` 在 WIN4-RW-S2 更新
  （R12 redirected-stdin owner gate 说明）。其它 README 不更新。
- 与 AGENTS.md README 更新触发规则一致。

### Coverage / pyright / Ruff / scans 自洽

- §13.6.3：`dayu/cli/commands/init.py` 单文件 line coverage ≥80%，新增 TTY/redirected/LF/CRLF/bare-CR/EOF/
  interrupt/required/optional/confirmation branches 必须被 owner tests 直接命中。
- §13.6.4：full pyright 零诊断；scoped Ruff 零诊断；full Ruff baseline 精确比较。
- §13.6.5：diff/allowlist/README checks。
- §13.6.6：`getpass.getpass` 只在 TTY 分支出现一次；零 `sys.__stdin__`/`msvcrt`/PowerShell/PTY/JobObject；
  零 `shell=True`/`errors=replace`/`hasattr`/`getattr`；零新增 display assertion diff；零 Issue/authorization/
  secret infrastructure。

### Remote R11/R12 lineage 自洽

- §13.8：fresh R11/R12 dispatch identity、accepted head SHA、same-run artifact integrity、same-run canary gate。
- R11 与 R12 run id 独立锁定，不混用。
- Standalone R11 不消费 R12 canary，按 artifact integrity 与无 secret-input contract 验收。
- §9.3 Controller-owned canary scan procedure 不变。

## 3. TTY strict fake / redirected StringIO / typing / pytest 可行性

### TTY strict fake

- Plan 要求：test-owned `sys.stdin` fake，`isatty()` 恒为 `True`，`readline()` 一旦被调用立即 assertion 失败。
- 实现形式：简单 class，两个方法。`isatty` 返回 `bool`，`readline` 返回 `str`（虽然实际不返回）。
- `sys.stdin` 类型是 `TextIO`；`isatty()` 和 `readline()` 都是 `TextIO` 的方法。typing 无歧义。
- `monkeypatch.setattr(sys, "stdin", tty_fake)` 是标准 pytest 实践。
- `getpass.getpass()` 在 `sys.stdin is not sys.__stdin__` 时 fallback 到从 stream 参数读取；stream 默认
  为 `None` 即 `sys.stdin`（即 tty_fake）。TTY test 走 `getpass.getpass(prompt)` → monkeypatch 生效。

### Redirected StringIO

- `io.StringIO` 的 `isatty()` 返回 `False`。`readline()` 返回 `str`。
- `monkeypatch.setattr(sys, "stdin", io.StringIO("test-secret\n"))` 后，`_read_secret_input` 走 redirected path，
  调用 `sys.stdin.readline()` → 消费 `"test-secret\n"` → 移除 `\n` → 返回 `"test-secret"`。
- typing 完全匹配 `TextIO`。

### EOFError / empty-read / KeyboardInterrupt / value-free 语义

- TTY EOF：`getpass.getpass()` 抛 `EOFError` → plan 要求捕获并映射为 `CliInitOperationError`。
- Redirected EOF：`readline()` 返回 `""` → plan 要求识别并映射为同一 `CliInitOperationError`。
- `KeyboardInterrupt`：不捕获、不改写，继续由 CLI owner 映射为 exit `130`。
- `CliInitOperationError` 继承 `RuntimeError`（L90），message 不含 prompt/secret/raw buffer。
- 三种语义无冲突。

## 4. Public snapshot 与 artifact integrity

- §13.2.1 第 3 点明确 `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`，
  只在 `with` 块内读取。
- §13.5.1："source snapshot 的 identity/source kind/primary filename/descriptors 只在 public `with` lifecycle
  内读取；CLI test 不得重复增加 Fins close-after-use owner test"。
- Runner test 进程在 artifact upload 前用 `with` 读取 snapshot。
- Downloaded artifact 仍只做 physical integrity（§13.2.1 第 4 点：`source_artifact_count` 只保留为
  uploaded evidence package 的物理 integrity count）。

## 5. Security / deferred scope / non-overclaim 验证

- 不引入统一 authorization/secret infrastructure：§13.9 明确。
- 不实施 Issue 142/151/175/177/178：§13.3 禁止路径、§13.9 deferred/forbidden 列表。
- Config/Host internal SQLite/EventLog trusted-local：§13.9 不变。
- Tool Trace/audit/public/LLM-facing/operator diagnostics 禁止 API key/header 明文：§13.9 不变。
- Gemini low-budget 非 finding：§13.9 明确 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## 6. Adversarial challenge: 是否引入了不合规的 Fins protocol test?

Fixed plan §13.2.1 第 3 点和 §13.5.1 明确"CLI test 不得重复增加 Fins close-after-use owner test"。CLI test
只正确消费既有 public contract（`get_company_meta`、`list_source_document_ids`、`read_source_snapshot`），
不测试 `__exit__` 的内部 cleanup 语义。Fins protocol owner tests 是 `dayu/fins/` 下仓储测试的职责。

**结论**：未引入不合规的 Fins protocol test。

## 7. Adversarial challenge: 是否把 production helper mock 带回来?

Fixed plan §13.4 WIN4-RW-S2 明确"不得 mock production `_read_secret_input`"。既有的 `getpass.getpass`
monkeypatch 在 TTY path 继续有效（因为 `_read_secret_input` 的 TTY 分支调用 `getpass.getpass(prompt)`）；
redirected path 使用真实 `io.StringIO`，不 mock。

**结论**：未引入 production helper mock。

## 8. Adversarial challenge: 是否依赖 ambient TTY?

Fixed plan §13.4 WIN4-RW-S2 明确"不得依赖本机/CI ambient TTY"。TTY fake 替换 `sys.stdin`，不依赖环境
`isatty()` 返回值。redirected tests 使用 `io.StringIO`，其 `isatty()` 恒为 `False`。

**结论**：未依赖 ambient TTY。

## 9. Adversarial challenge: 是否引入 unconditional CR strip?

Fixed plan §13.2.2 第 2 点明确条件：只有实际移除了末尾 `\n` 且新末尾是 `\r` 时才移除 `\r`。§13.5.2 要求
bare-CR preservation owner test。禁止 `rstrip` 或等价过度删除。

**结论**：未引入 unconditional CR strip。

## 10. Adversarial challenge: 两路初审和 Controller 裁决的 finding 是否被完整保留到 re-review 上下文?

- AgentMiMo 初始 review（F-01/F-02/F-03）→ Controller 合并为 WIN4-RW-PR-F01/F02/F03 → AgentCodex 修 plan →
  Controller validation 确认修复 → 本 re-review 逐项验证关闭。
- AgentDS 初始 review（DS-F01/DS-F02/DS-F03）→ Controller 合并为 WIN4-RW-PR-F02/F01/F04 → 同上。
- 四项 accepted findings 全部有明确 plan 位置修正和验证证据。

## Findings

**无新 findings。**

1060 行 fixed plan 在 root cause、owner、2 slices、allowlist、顺序、README、coverage、pyright、Ruff、scans、
remote R11/R12 lineage、security boundary、deferred scope 与 completion report 方面均自洽。四项 accepted
findings（WIN4-RW-PR-F01..F04）全部在 plan 文本中明确修正，无回归。

TTY strict fake 与 redirected `io.StringIO` 在 Python typing / pytest 下 code-generation-ready；EOFError /
empty-read / KeyboardInterrupt / value-free 语义无冲突。Public snapshot 在 `with` 块内读取，downloaded artifact
只做 physical integrity。不引入统一 authorization/secret infra，不实施 Issue 142/151/175/177/178。

## Open questions

`0`。

## Residual risks and tracking destination

与初审一致，无新增：

1. 非 Windows 本地无法替代真实 CPython 3.11 Windows console/redirected handle 行为；owner unit tests 只锁定
   capability contract，最终证据唯一 destination 是 §13.8 fresh R12。
2. caller-owned pipe、OS handle 与 CLI process memory 按输入本质会暂存 secret；本 WU 只承诺 CLI 不主动回显
   或投影，不承诺外部 shell/process inspection 安全。
3. 若 fresh R11 exit/storage owner 事实失败，或 fresh R12 在 secret 读取之后出现新 failure，立即进入
   diagnostic-first stop；不得沿用当前两个 root cause 解释新证据。
4. Controller 继续独立拥有 same-run canary scan；implementation/test 不得取得 run-specific needle 或共享派生实现。

## Final plan review conclusion

`PASS / NO_BLOCKER / NO_NEW_FINDINGS / WIN4-RW-PR-F01..F04_ALL_CLOSED / IMPLEMENTATION_NOT_AUTHORIZED`

Fixed plan（1060 行）的整体 root cause/owner/精确 2 slices/allowlist/顺序/README/coverage/pyright/Ruff/scans/
remote R11/R12 lineage 自洽。四项 accepted findings 全部在 plan 文本中明确修正且无回归。TTY strict fake 与
redirected StringIO 在 Python typing/pytest 下 code-generation-ready。下一步只能是 AgentDS 完成第二路完整
re-review；两路均 PASS 且 Controller 最终裁决 accepted/open 为零后，才可形成 accepted amended-plan local commit。
Implementation 仍未授权。
