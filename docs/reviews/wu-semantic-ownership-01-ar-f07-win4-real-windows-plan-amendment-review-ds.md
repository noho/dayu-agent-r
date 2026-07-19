# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review — AgentDS

## Review metadata

- Timestamp（本机时钟）：`2026-07-20 05:41:47 +0800`。
- Reviewer：AgentDS（第二路完整 adversarial plan review）。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（SHA-256 `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`）。
- Frozen remote code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Locked evidence runs：R11 `29703932798`；R12 `29703933666`。
- Companion artifacts read：
  - Controller adjudication（SHA-256 `254022d11c6e52324622ba9b52050a3ae6832d84333eece145572c0c1ec6d4cf`）；
  - AgentCodex amendment artifact（SHA-256 `b985a2a402255c0be7fef49b2d428c70d3f5dd459f9026f2d958fa4dc8dc1cf9`）；
  - Controller validation（SHA-256 `2ea4080e7191e6eb656a35ce24978949896fc12a6d7c85d251cde2b5ad0a89df`）。
- Direct code/test/storage/workflow evidence read：完整。
- Conclusion：`PASS_WITH_FINDINGS / 3_MATERIAL_FINDINGS / 0_BLOCKERS / IMPLEMENTATION_NOT_AUTHORIZED`。

本 review artifact 不实施 production/test/workflow 变更，不更新 control/design/README，不 stage、commit、push、dispatch 或操作 PR。

---

## Reviewed inputs and evidence scope

已完整读取：

- `AGENTS.md`；
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（全部 1045 行，含 §13 amendment）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-failure-controller-adjudication.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`。

直接代码/测试/仓储/workflow 证据：

- `tests/cli/test_upload_filings_from_command.py`（1185 行）：旧 display assertion（L965 `"Fins result"`）、company-name oracle（L950-952）、artifact oracle（L970-989）、`_assert_single_windows_upload_company_name`（L1045-1084）、POSIX real workflow（L790-847）；
- `dayu/cli/output.py`（498 行）：当前 terminal summary prefix `_FINS_EVENT_SUMMARY_PREFIX = "Fins summary"`（L63）、succeeded prefix `_FINS_EVENT_SUCCEEDED_PREFIX = "Fins succeeded"`（L66）；
- `dayu/cli/commands/init.py`（771 行）：`_collect_environment_persistence_plan`（L468-516）中两处 `getpass.getpass()` 调用（L482、L494）；
- `tests/cli/test_init_command.py`（1064 行）：`_GetpassSequence`（L135-167）、`_install_ollama_inputs`（L250-273）中 `monkeypatch.setattr(getpass, "getpass", ...)`；
- `tests/cli/test_init_smoke.py`（1878 行）：`_run_init`（L585-670）的 anonymous handle lifecycle、`_WINDOWS_CANARY_DOMAIN`（L61）、`_github_actions_canary`（L516-531）、`_select_windows_test_canary`（L534-547）、timeout state machine tests（L886-1018）、canary freeze tests（L1021-1141）；
- `dayu/fins/storage/fs_company_meta_repository.py`：`FsCompanyMetaRepository.__init__(workspace_root: Path, ...)`（L18-43）、`get_company_meta(ticker: str) -> CompanyMeta`；
- `dayu/fins/storage/fs_source_document_repository.py`：`FsSourceDocumentRepository.__init__(workspace_root: Path, ...)`（L223-251）、`list_source_document_ids(ticker, source_kind) -> list[str]`、`read_source_snapshot(...) -> SourceSnapshotProtocol`；
- `dayu/fins/storage/repository_protocols.py`：`SourceSnapshotProtocol`（context manager，含 `ticker`/`document_id`/`source_kind`/`primary_filename`/`files`/`source_meta`/`provenance` properties）；
- `dayu/fins/storage/_fs_source_snapshot.py`：`_FsSourceSnapshot` 实现，`materialize_files=False` 时返回 light snapshot（descriptors + metadata only）；
- `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml`。

---

## Goal, non-goals and success signal

Goal 是在既有 plan 中增加两个、按真实 semantic owner 切分且可直接交给 implementation agent 的 slices：

1. `WIN4-RW-S1`：删除 test consumer 对 display literal 的成功耦合，以 process exit 和 public Fins storage owner facts 证明 upload success，保留 company-name oracle 与 artifact integrity。
2. `WIN4-RW-S2`：在 CLI secret-input owner 按 stdin capability 区分 TTY hidden getpass 与 redirected line-oriented input，由 owner tests 锁定 EOF/interrupt/order/non-disclosure。

Non-goals 保持：不修 output renderer、setx/harness/workflow、Fins production/schema、Config/Host durable domain、Issue 142/151/175/177/178、统一 authorization/secret infra 或 Gemini quota。

本地 success signal 是 owner tests、CLI regression、coverage、pyright、Ruff、diff/allowlist、README/source scans 全部满足；最终 closure signal 仍是 accepted implementation commit 上的 fresh R11/R12 dispatch、同 run artifact integrity 和 R12 Controller-owned value-free canary gate。

---

## Assumptions tested

| Assumption | Adversarial test | Direct evidence and disposition |
|---|---|---|
| `FsCompanyMetaRepository(storage)` 只接受一个 Path 参数即可构造 | 检查 `__init__` 签名 | `FsCompanyMetaRepository.__init__(self, workspace_root: Path, *, file_store=None, repository_set=None)` — `workspace_root` 是唯一必选位置参数；`file_store`/`repository_set` 均为可选 keyword。假设成立。 |
| `FsSourceDocumentRepository(storage)` 同样可单一 Path 构造 | 检查 `__init__` 签名 | `FsSourceDocumentRepository.__init__(self, workspace_root: Path, *, file_store=None, repository_set=None, create_directories=True)` — 同上。假设成立。 |
| `read_source_snapshot(materialize_files=False)` 提供 ticker/document_id/source_kind/primary_filename/files 属性 | 检查 `SourceSnapshotProtocol` 与 `_FsSourceSnapshot` | Protocol 明确定义 `ticker`/`document_id`/`source_kind`/`primary_filename`/`files`（`tuple[SourceSnapshotFileDescriptor, ...]`）为只读 property。`materialize_files=False` 时返回 light snapshot，只含 descriptors+metadata，无 temp tree。假设成立。 |
| `SourceSnapshotProtocol` 是 context manager | 检查 protocol 定义 | 有 `__enter__`/`__exit__`，且实现 `_FsSourceSnapshot` 在 `__exit__` 中清理资源。假设成立。 |
| `sys.stdin.isatty()` 在 pytest 中默认返回 True | 检查 pytest 实际行为 | pytest 继承父进程 stdin；本地 terminal 中为 True，但 CI/redirected 环境可能为 False。**假设不完全成立** — 见 Finding DS-F01。 |
| `getpass.getpass()` 在 CPython 3.11 Windows 上 `sys.stdin is sys.__stdin__` 时走 console `msvcrt.getwch()` | Controller 已直接检查 CPython 3.11 `getpass.py` 源码 | Controller 裁决已确认。假设成立。 |
| 既有 `test_init_command.py` 的 `_GetpassSequence` mock 在 `isatty()==True` 时继续工作 | 检查 mock 安装方式 | `_install_ollama_inputs` 只 mock `getpass.getpass` 和 `builtins.input`，不设 `sys.stdin`。`_read_secret_input` 的 TTY 分支调用 `getpass.getpass(prompt)` → mock 被调用。假设成立的前提是 `isatty()` 为 True。 |
| R12 canary domain bytes 与已知向量已被既有 test 冻结 | 检查 `test_init_smoke.py` L61 和 L1021-1041 | `_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes，末字节 single NUL `0x00`）；已知向量 `canonical_run_id="1"` → `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97`。owner tests 逐字节验证。假设成立。 |

---

## Focus area 1: WIN4-RW-S1 — Fins public repositories and bounded SourceSnapshot lifecycle

### Evidence summary

Plan §13.2.1 指定了精确的 public repository 调用链：

1. `FsCompanyMetaRepository(storage).get_company_meta("AAPL")` → 断言 `ticker == "AAPL"` 且 `company_name == "Apple Inc."`。
2. `FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)` → 断言返回唯一一个 document id。
3. 对该 id 调用 `read_source_snapshot`（`materialize_files=False`）→ 断言 `ticker`、`document_id`、`SourceKind.FILING`、`primary_filename` 等于 source basename、`files`（descriptor 集合）非空且包含 primary。
4. `source_artifact_count` 降为 physical integrity count，不再承担业务 success 语义。

**Constructor feasibility verified：** `FsCompanyMetaRepository.__init__(workspace_root: Path, *, file_store=None, repository_set=None)` — `workspace_root` 是唯一必选位置参数。`FsSourceDocumentRepository.__init__(workspace_root: Path, *, file_store=None, repository_set=None, create_directories=True)` — 同上。当前 test 中 `storage = artifact_directory`（Path 类型），传入后 repository 内部调用 `build_fs_repository_set(workspace_root=storage, ...)` 完成自举。

**Snapshot lifecycle：** `SourceSnapshotProtocol` 是 context manager（有 `__enter__`/`__exit__`）。`materialize_files=False` 时返回 light snapshot，不复制文件，只持有 descriptors + metadata，资源开销小。但 plan 没有显式要求实现使用 `with` 语句。

**Display assertion removal：** Plan §13.2.1 点 1 正确删除 `"Fins result"` 断言（当前代码 L965），且不增加任何新 display text 断言。保持 `execution.returncode == 0`（当前代码 L964）。

**Physical artifact count：** Plan §13.2.1 点 4 明确 `source_artifact_count` 只承担 physical integrity。当前代码 L969 的 `len(source_artifacts)` 使用 `rglob("*")` 计算文件数。Plan 不要求修改此逻辑。

### Adversarial test results

1. **Repository 构造可行：** 已从 `__init__` 签名直接证实单一 `Path` 参数即可构造。反例不成立。
2. **`get_company_meta` 在 storage 为空或 company meta 不存在时抛 `FileNotFoundError`：** 这是正确的 fail-closed 行为。Plan §13.5.1 要求此种情况测试失败，但未指定是 catch 后转 `AssertionError` 还是 let propagate。这是微小实现细节，不构成 finding。
3. **Snapshot 未用 `with` 可能导致资源泄漏：** `_FsSourceSnapshot` 在 `__exit__` 中清理资源（包括 light snapshot 的 publication guard release）。若实现未使用 context manager，publication guard 不会在 finally 中释放，可能导致后续读取被锁。这是一个真实风险。
4. **`read_source_snapshot` 方法归属：** Plan 只说 "对该 id 读取 `materialize_files=False` 的 storage-owned source snapshot"，未指明该方法在 `FsSourceDocumentRepository` 上。但 plan 提供了充分语义线索，implementation agent 可从 `FsSourceDocumentRepository` 的 public methods 中找到 `read_source_snapshot`。

### Conclusion for WIN4-RW-S1

Plan 的 repository 调用链在现有 public API 上可行。核心风险是 snapshot context manager 使用规范未显式化——见 Finding DS-F02。

---

## Focus area 2: WIN4-RW-S2 — `_read_secret_input` capability 分流

### Evidence summary

Plan §13.2.2 定义 `_read_secret_input(prompt: str) -> str`：

1. `sys.stdin.isatty()` 为 True → `getpass.getpass(prompt)`。
2. 为 False → `sys.stderr.write(prompt); sys.stderr.flush(); sys.stdin.readline()`，然后先移除末尾 `\n`，再移除其前 `\r`。
3. EOF（TTY getpass EOF 或 redirected empty stream）→ `CliInitOperationError("secret input ended before completion")`，不含 prompt/value。
4. `KeyboardInterrupt` 不捕获、不改写。
5. `_collect_environment_persistence_plan()` 只把两处 `getpass.getpass()` 替换为 `_read_secret_input(prompt)`。
6. 分流 capability-based，不使用 `os.name`/`platform.system()`/`sys.__stdin__`/GitHub Actions。

### Adversarial test results

#### Challenge A: pytest/Windows 既有 fixtures 是否误走 redirected path

当前 `test_init_command.py` 的 `_install_ollama_inputs()` 只 mock `getpass.getpass` 和 `builtins.input`，不操作 `sys.stdin`。`_read_secret_input` 的 TTY 分支调用 `getpass.getpass(prompt)` —— 仅当 `sys.stdin.isatty()` 为 True 时。

**真实风险场景：**
- 本地 terminal 运行 pytest：`isatty()` → True，TTY 分支，mock 被调用 → 正常。
- GitHub Actions CI 运行 pytest：CI runner 的 stdin 通常不是 TTY，`isatty()` 可能返回 False。
- 非 TTY IDE test runner（如某些 VS Code test explorer 配置）：同样可能返回 False。

当 `isatty()` 返回 False 时，`_read_secret_input` 走 redirected 分支，调用 `sys.stdin.readline()`。但 `sys.stdin` 未被 mock，`readline()` 读取真实 stdin（CI 中通常为 EOF），导致：
- `CliInitOperationError("secret input ended before completion")`；
- `getpass.getpass` mock 的 `_GetpassSequence` 从未被调用；
- 所有依赖 getpass mock 返回 secret 值的测试（如 `test_required_secret_refusal_stops_before_transaction_publication`、`test_environment_persistence_failure_never_publishes_workspace` 等）全部失败。

**Plan 已意识到此风险：** §13.4 明确要求 "更新受影响既有 getpass fixtures使其明确处于 TTY path"。但 plan 没有指定具体机制。

**可行修复路径：**
- 最佳做法：在 `_install_ollama_inputs` 或等效 fixture 中 mock `sys.stdin` 为一个 `io.StringIO` 替代品，使 `isatty()` 返回 True，`readline()` 在意外调用时抛 `AssertionError`。既保证 TTY 路径被使用，又防止 redirected 路径被意外触发。
- 次优做法：直接在测试中 mock `init_command._read_secret_input` 替代对 `getpass.getpass` 的 mock。但这会降低测试对 owner contract 的覆盖。

**严重性评估：** 这是计划不完整（implementation agent 需自行决定 fixture 更新方式）而非计划错误。风险可控，因为：
1. 本地开发环境几乎总是有 TTY；
2. CI 失败会在第一次 fresh R12 run 时立即暴露，不会潜伏；
3. 修复简单（mock `sys.stdin.isatty`）。

→ 见 Finding DS-F01。

#### Challenge B: LF/CRLF line ending 算法

Plan 的算法：先 `rstrip('\n')`（移除末尾单个 `\n`），再 `rstrip('\r')`（移除其前单个 `\r`）。

逐例验证：
- `"value\n"` → 移除 `\n` → `"value"` → 无 `\r` → `"value"` ✓
- `"value\r\n"` → 移除 `\n` → `"value\r"` → 移除 `\r` → `"value"` ✓
- `"value"` → 无 `\n` → `"value"` → 无 `\r` → `"value"` ✓
- `"value\r"` → 无 `\n` → `"value\r"` → 移除 `\r` → `"value"`（bare CR 被当作 line ending 消费）
- `"val\nue\n"` → 移除末尾 `\n` → `"val\nue"` → 无 `\r` → `"val\nue"` ✓（中间 `\n` 保留）

算法将 bare `\r`（无前置 `\n`）也视为 line ending 并移除。这在现代系统中几乎不会发生（Windows redirected stdin 的 `readline()` 在 Python text mode 下已做 universal newline 转换），但严格来说 bare CR 在 old Mac 风格的 redirected 文件中可能作为 line ending 出现。对于 API key secret，值中包含 bare `\r` 的概率接近零。

**结论：** 算法在实践上正确，edge case 影响概率极低。不构成 finding。

#### Challenge C: EOF 与 KeyboardInterrupt 语义

Plan §13.2.2 点 3：TTY getpass EOF 与 redirected empty stream 都收敛为 `CliInitOperationError("secret input ended before completion")`。该消息不含 prompt 或 value。

Plan §13.2.2 点 3：`KeyboardInterrupt` 不捕获、不改写，由现有 CLI owner 映射为 exit `130`。

**验证：** 当前 `run_init_command` 的 except 链（L224-240）已有 `except KeyboardInterrupt: return EXIT_KEYBOARD_INTERRUPT`，以及 `except CliInitOperationError: return EXIT_FAILURE`。`_read_secret_input` 抛出的 `CliInitOperationError` 会被正确捕获。

**结论：** EOF/interrupt 语义自洽。不构成 finding。

#### Challenge D: required/optional/confirmation 顺序

Plan §13.2.2 点 4：`_collect_environment_persistence_plan()` 只把两处 `getpass.getpass()` 换成 `_read_secret_input(prompt)`。required 空行继续 value-free fail closed；optional 空行继续 skip；`OPTIONAL_ENVIRONMENT_NAMES` 顺序不变；names-only preview 不变；最终 `_confirm()` 不变。

**验证：** 当前代码 L482-501 的逻辑顺序是：检查 required → 读 required secret → 遍历 optional names → 跳过已有 env → 读 optional secret → 全部收集后 names-only preview → `_confirm()`。Plan 不对这段逻辑做任何重排。

**结论：** 顺序保持正确。不构成 finding。

#### Challenge E: non-disclosure

Plan §13.5.2 要求 redirected stdin 下 "secret value在 stdout/stderr/captured exception/diagnostic中零命中"；TTY 下 hidden getpass 同理。`CliInitOperationError` 的 message 不含 prompt 和 value。

**结论：** non-disclosure 语义完整。不构成 finding。

#### Challenge F: 是否引入了 callback/factory/平台特例/test shim

Plan §13.2.2 明确：`_read_secret_input` 是模块级私有 helper（`def _read_secret_input(prompt: str) -> str`），不新增 callback、factory、Protocol、class、runtime helper 或跨模块 facade。§13.4 禁止在 `_run_init()`、workflow 或 Windows-only test 注入 shim。

**结论：** 符合约束。不构成 finding。

### Conclusion for WIN4-RW-S2

Design 正确且自洽。唯一 material finding 是既有 test fixtures 在非 TTY 环境下的 TTY-path 保证机制未具体化。

---

## Focus area 3: Slice allowlist/顺序/README/coverage/pyright/Ruff/scans

### Evidence summary

Plan §13.3 定义 allowlist：

| Slice | Allowed paths |
|---|---|
| WIN4-RW-S1 | `tests/cli/test_upload_filings_from_command.py` |
| WIN4-RW-S2 | `dayu/cli/commands/init.py`; `tests/cli/test_init_command.py`; `README.md`; `tests/README.md` |

Forbidden paths：`dayu/cli/output.py`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、所有 `dayu/fins/` production code、两个 workflow yml、control/design/review artifacts。

### Adversarial test results

1. **allowlist 是否最小充分：** S1 只修改一个 test 文件，删除 display assertion 并增加 repository-based 成功断言。S2 修改 production init.py（`_read_secret_input` + 两处替换）、test_init_command.py（owner tests + 既有 fixture 更新）、README.md 和 tests/README.md。两个 workflow、test_init_smoke.py、output.py、init_environment.py 和所有 Fins production code 均被禁止修改。allowlist 精确匹配 owner boundary。

2. **S1→S2 串行顺序：** Plan §13.4 要求 S1→S2 串行实施。S1 无代码依赖；S2 无 S1 代码依赖，但 "只有两 slice均 accepted后才允许 aggregate validation和 remote rerun"。这是合理的 review 边界要求，不是代码依赖。

3. **coverage：** `dayu/cli/commands/init.py` 单文件 line coverage ≥80%，新增 TTY/redirected/LF/CRLF/EOF/interrupt/required/optional/confirmation branches 必须被 owner tests 直接命中。禁止 pragma/omit 或以 real-Windows skip 替代。

4. **pyright/Ruff：** full pyright 零诊断；scoped Ruff 零诊断；full Ruff baseline 按 `(filename, location, code, message, fix-applicability)` 精确比较，新增/扩散为零。

5. **forbidden-source scans：** §13.6.6 通过 `rg` 扫描确保 `getpass.getpass` 只在 TTY 分支出现一次、零 `sys.__stdin__`/`msvcrt`/PowerShell/PTY/JobObject、零 `shell=True`/`errors=replace`/`hasattr`/`getattr`、零新增 display assertion diff、零 Issue/authorization/secret infrastructure。

**结论：** allowlist、顺序、validation matrix 和 source scans 均完整且最小充分。不构成 finding。

---

## Focus area 4: Fresh R11/R12 dispatch identity、accepted head、same-run evidence/canary scan

### Evidence summary

Plan §13.8 定义 fresh remote rerun matrix。关键要求：

1. R11 identity：dispatch response 返回唯一新 run id；metadata 精确绑定 R11 workflow/path、`workflow_dispatch`、target ref 与 accepted implementation head SHA。不从最近 run、时间或 artifact 名反推。
2. R12 identity：同上，与 R11 run 独立锁定，不混用。
3. R12 same-run canary gate：Controller 按 §2.3/§9.3 frozen text 独立派生，仅在进程内 exact scan 同一 R12 run 的全部 artifact files 与全部 workflow log files，零命中。
4. Standalone R11 不消费 R12 canary：继续按 artifact integrity 与无 secret input contract 验收。

### Adversarial test results

1. **Run identity 唯一性：** Plan §13.8 要求每次 dispatch response 返回唯一 run id，并在读取任何 evidence 前锁定。Controller validation 已确认此流程在 `29703932798`/`29703933666` 上正确执行。R11 与 R12 run id 独立，不混用。

2. **Canary derivation 合同冻结：** Plan §2.3 冻结了完整 domain bytes（`b"dayu-ar-f07-win4-r12-canary-v1\x00"`，31 bytes，末字节 single NUL `0x00`）、canonicalization 规则（`str(int(GITHUB_RUN_ID))`）、digest 算法（`sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`）、prefix（`sk-dayu-test-`）和已知向量（`run_id="1"` → `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97`）。既有 `test_init_smoke.py` L61 和 L1021-1041 已逐字节锁定这些合同。

3. **Controller 独立重算：** Plan §9.3 要求 Controller 不与 test/production 共享 helper、constant module 或生成实现；不从 test output/artifact 取得 needle。Controller validation 已确认这一点。

4. **Standalone R11 不消费 canary：** Plan §13.8 和 §9.3 多次明确 standalone R11 不进入 canary scan，且不得声称由 R12 scan 提供 non-disclosure 证明。

5. **Value-free evidence：** Plan §9.3 点 5 要求命中时只记录 R12 `run_id`、`head_sha`、artifact-relative locator、`match_category=test_canary` 和 failed status，不得包含 canary/matched content。扫描命令、review artifact 和 control doc 同样零回显。

**结论：** dispatch identity、accepted head、same-run evidence canary scan 设计完整且 value-free。不构成 finding。

---

## Focus area 5: 不引入统一 authorization/secret infra

### Evidence summary

Plan §13.9 明确：

- Config 与 Host internal SQLite/EventLog 是 trusted-local domain；
- 只有 Tool Trace/audit 以及 public/LLM-facing/operator diagnostics 禁止 API key/header 明文；
- 本 amendment 不读取、迁移、重写或扩大 durable secret 范围；
- 不把 redirected stdin 伪装成 encrypted transport；
- 不新增 zeroization、credential broker、unified authorization 或 secret infra；
- Issue 142/151/175/177/178、Web/WeChat/render、通用 console/PTY/process isolation、setx redesign、Fins generic diagnostic schema 均 deferred/forbidden；
- Gemini low-budget 继续是 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不是 finding、blocker 或验收输入。

### Adversarial test results

1. **Secret boundary 未扩大：** `_read_secret_input` 只负责从 stdin 读取 secret value，不持久化、不缓存、不转发。Secret value 仍由既有 `_collect_environment_persistence_plan` 放入 `EnvironmentPersistenceEntry`，再经 `persist_environment` 写入 OS store（setx 或 profile）。上下游语义 owner 不变。

2. **No secret infra creep：** Plan 反复禁止统一 authorization/secret management。§3.2、§11、§13.3、§13.9 均明确。implementation agent 没有模糊地带。

3. **Config/Host trusted-local 不变：** Plan 不修改 Config/Host durable state 读写，不修改 Tool Trace/audit 的明文禁止规则。

**结论：** 不构成 finding。

---

## Required review lenses

### Architecture boundary review

**WIN4-RW-S1：** Test consumer 从 display text 迁移到 process exit + public `dayu.fins.storage` repository facts。依赖方向正确——test 消费既有 public contract，不创建新的 production seam。`SourceSnapshotProtocol` 是 storage owner 的既有 public contract，test 不绕过它直接读 raw JSON/private core。

**WIN4-RW-S2：** `_read_secret_input` 是 `dayu/cli/commands/init.py` 内的模块级私有 helper，由 `_collect_environment_persistence_plan` 唯一复用。不侵入 `dayu.runtime`、`dayu.cli.init_environment`、Config 或 Host。`UI -> Service -> Host -> Engine` 分层边界不变。

**Verdict：** 架构边界保持。

### Best-practice review

方案使用 capability detection（`isatty()`）、单一 logical-line read、明确 EOF/interrupt 语义、owner-level negative tests、动态 non-disclosure 断言和 fresh remote acceptance。避免 timeout、display text、mock 或 warning suppression 获得假绿。

线路 ending 算法（先 `\n` 后 `\r`）是经典的 `rstrip('\r\n')` 手动实现，等价于 Python 的 universal newline 预期行为。使用显式两步而非 `str.rstrip('\r\n')` 可以避免 `"value\r\r\n"` 被过度剥离（`rstrip` 会移除所有 trailing `\r` 和 `\n` 字符），正确处理中间 `\r` 保留。**但**这同时也意味着 `"value\r"` 末尾单个 `\r` 会被移除——见 §2.2 line ending 分析。

### Optimal-solution review

可信替代方案：
- 修改 `dayu/cli/output.py` 恢复旧 prefix → 修错 owner（renderer 不是 test success 的 owner）。
- 给 test 换新硬编码词 → 只是推迟问题，下次 output owner 变更 display text 时再次失败。
- 在 `_run_init()` 加 Windows input shim → 修错层，shim 在 subprocess harness 而不是 CLI input owner。
- 使用 PowerShell/PTY/console wrapper → 扩大 blast radius。

Plan 选择两个最小 owner-local 变更，是当前证据下更简单、可测试、可演进的路径。

### Overengineering review

- `_read_secret_input` 是单一模块级私有 helper（`def _read_secret_input(prompt: str) -> str`），不是 class/Protocol/factory/callback/跨模块 facade。
- WIN4-RW-S1 复用既有 public `FsCompanyMetaRepository`/`FsSourceDocumentRepository`/`SourceSnapshotProtocol`，不新增 storage abstraction、test helper 或 production seam。
- 无 credential broker、redaction framework、process framework、schema 或 migration。

**Verdict：** 无过度设计。

### Overcoupling review

- 两个 slices 串行但没有代码依赖；只有最终 remote rerun 依赖二者同时 accepted。
- S1 不需要修改 Fins/output/workflow；S2 不需要修改 harness/setx。
- README 与 S2 保持同一提交/回滚边界，没有建立额外 docs transaction。
- `_read_secret_input` 只由 `_collect_environment_persistence_plan` 复用；没有扩散到 model selection、confirmation 或其他 input 路径。

**Verdict：** 无过度耦合。

---

## Findings

### DS-F01 [中] — 既有 test_init_command.py getpass fixtures 在非 TTY 环境下可能误入 redirected path

- **位置**：Plan §13.2.2（`_read_secret_input` 设计）、§13.4 WIN4-RW-S2（"更新受影响既有 getpass fixtures使其明确处于 TTY path"）、§13.5.2（negative cases）。
- **问题类型**：不可直接实施 / 测试缺口
- **当前写法**：Plan §13.4 要求更新既有 getpass fixtures 使其明确处于 TTY path，但未指定具体机制。`_read_secret_input` 的分流完全依赖 `sys.stdin.isatty()` 的返回值；当返回值不确定时（CI、IDE test runner），既有 mock 策略失效。
- **反例/失败场景**：
  1. GitHub Actions CI 运行 `pytest tests/cli/test_init_command.py`，`sys.stdin.isatty()` 返回 `False`。
  2. `_collect_environment_persistence_plan()` 调用 `_read_secret_input(prompt)`。
  3. `_read_secret_input` 走 redirected 分支，调用 `sys.stdin.readline()` 读取真实 stdin（CI 中为 EOF）。
  4. `CliInitOperationError("secret input ended before completion")` 被抛出。
  5. `_GetpassSequence` mock 中的 `prompts` 列表为空（从未被调用），所有依赖 getpass mock 的测试断言失败。
  6. 即使 test_init_command.py 中非 secret-specific 测试（如 `test_first_cli_flow_uses_real_lock_discovery_and_current_config`）也会因 `_GetpassSequence` 未被调用而失败——它们依赖 getpass mock 返回空字符串来跳过 optional secrets。
- **为什么有问题**：Plan 明确要求分流是 capability-based（`isatty()`）且平台中立，但这个决策把 `isatty()` 变成了所有使用 `_read_secret_input` 的测试的隐藏前置条件。Plan 虽然提到要更新 fixtures，但没有给出具体更新方式（mock `sys.stdin.isatty`？mock `_read_secret_input`？替换 `sys.stdin`？），implementation agent 需要自行决定，可能产生不一致或脆弱方案。
- **直接证据**：
  - `tests/cli/test_init_command.py` L250-273：`_install_ollama_inputs` 只 mock `builtins.input` 和 `getpass.getpass`，不操作 `sys.stdin`。
  - `tests/cli/test_init_command.py` L523-554：`test_required_secret_refusal_stops_before_transaction_publication` 使用 `_GetpassSequence((secret, "", "", "", "", ""))`，依赖 getpass 被调用 6 次（1 required + 5 optional）。
  - Plan §13.2.2 点 1：`sys.stdin.isatty()` 为 True 时只调用 `getpass.getpass(prompt)`。
  - Plan §13.2.2 点 2：为 False 时，不调用 `getpass`，只对 `sys.stdin` 调用 `readline()`。
- **影响**：实施 Agent 若未正确处理 fixture 更新，会导致 test_init_command.py 全部或部分测试在 CI 中失败；first fresh R12 run 会立即暴露，但浪费一次 dispatch round-trip。若采用 mock `sys.stdin.isatty` 返回 True 的修复，可能掩盖 `_read_secret_input` 在真实 redirected 环境下的 bug。
- **建议改法和验证点**：
  1. 在 plan 中明确：既有 `test_init_command.py` 中任何触发 `_collect_environment_persistence_plan` 的测试，必须显式控制 `sys.stdin` 使 `isatty()` 返回 True，且 `readline()` 在意外调用时 fail closed。
  2. 具体实现建议（不绑定）：在 `_install_ollama_inputs` 中增加 `monkeypatch.setattr(sys.stdin, "isatty", lambda: True)`，同时 mock `sys.stdin.readline` 抛 `AssertionError("redirected path unexpectedly entered in TTY test")`。
  3. 新增至少一个 CI-safe 测试：在 `monkeypatch.setattr(sys.stdin, "isatty", lambda: False)` 且 `sys.stdin` 替换为 `io.StringIO("test-secret\n")` 的情况下，验证 redirected 路径正确消费输入、不回显。
  4. R12 CI workflow 的 pytest 步骤应验证 `test_init_command.py` 全部通过，作为 pre-dispatch 本地证据。
- **修复风险（低）**：fixture 更新只影响测试，不修改 production code；mock `sys.stdin.isatty` 是标准 pytest 实践。
- **严重程度（中）**：不阻塞 production 正确性（production 中 `isatty()` 反映真实输入能力），但阻塞 CI 中 test_init_command.py 的可重复性。若被忽略，会导致 CI red 和远程 rerun 延迟。

---

### DS-F02 [低] — WIN4-RW-S1 未显式要求 SourceSnapshot context manager 用法

- **位置**：Plan §13.2.1 点 3（"对该 id 读取 materialize_files=False 的 storage-owned source snapshot"）。
- **问题类型**：不可直接实施
- **当前写法**：Plan 描述需要从 snapshot 读取 ticker/document_id/source_kind/primary_filename/files 等属性，但未说明 `read_source_snapshot()` 返回的 `SourceSnapshotProtocol` 是 context manager，必须使用 `with` 语句以确保 publication guard 在读取完成后释放。
- **反例/失败场景**：
  1. Implementation agent 调用 `snapshot = repo.read_source_snapshot(ticker, doc_id, SourceKind.FILING, materialize_files=False)` 后直接读取属性，未使用 `with`。
  2. `_FsSourceSnapshot` 的 publication guard（文件锁）在 snapshot 对象的整个生命周期内持有。
  3. 若 agent 未显式调用 `snapshot.close()` 或使用 `with`，publication guard 只在 `_FsSourceSnapshot.__del__` 时释放（依赖 GC 时机，不确定）。
  4. 同一 test 中后续的 `get_company_meta()` 调用（也需要 publication guard）可能因锁未释放而阻塞或超时。
  5. 在 Windows 上文件锁语义与 POSIX 不同，锁泄漏可能导致更难诊断的 `PermissionError`。
- **为什么有问题**：Plan 在 §13.2.1 点 3 中精确列出了需要验证的 snapshot 属性，但没有把 "with 语句 / context manager" 作为强制性使用方式写入 spec。`SourceSnapshotProtocol` 的 `__enter__`/`__exit__` 在 protocol 定义中明确存在，但 plan 不提及，implementation agent 可能忽视。
- **直接证据**：
  - `dayu/fins/storage/repository_protocols.py`：`SourceSnapshotProtocol` 定义 `__enter__`/`__exit__`，是一个 context manager。
  - `dayu/fins/storage/_fs_source_snapshot.py`：`_FsSourceSnapshot.__exit__` 调用 `_cleanup_snapshot_attempt`，释放 publication guard 和可能的 temp tree。
  - `dayu/fins/storage/fs_source_document_repository.py`：`read_source_snapshot` 的 docstring 说明了 light vs full snapshot，但 context manager 要求是 protocol 级约束。
- **影响**：实施 Agent 可能写出无 `with` 的 snapshot 使用代码，导致锁泄漏、后续 storage 读取失败或不稳定。
- **建议改法和验证点**：
  1. Plan §13.2.1 点 3 应改为："对该 id 通过 `with repo.read_source_snapshot(...) as snapshot:` 读取 materialize_files=False 的 storage-owned source snapshot，在 with 块内断言..."
  2. 负向测试可在 plan §13.5.1 增加一条：snapshot 必须在 with 块内使用，或显式 close 后不可再读取属性（但这是 repository owner test 的职责，不必在 CLI test 中重复）。
- **修复风险（低）**：只是 plan 文字精确化，不改变设计。
- **严重程度（低）**：`SourceSnapshotProtocol` 的 context manager 语义在既有 Fins tests 中广泛使用，implementation agent 参照既有模式即可发现。不影响 plan 总体可行性。

---

### DS-F03 [低] — `_read_secret_input` 的 line ending 算法可能过度剥离孤立 trailing `\r`

- **位置**：Plan §13.2.2 点 2（"先移除末尾单个 `\n`，再移除其前单个 `\r`"）。
- **问题类型**：契约缺失
- **当前写法**：算法先移除末尾 `\n`，再移除其前 `\r`。对于 `"value\r"`（末尾只有 `\r` 无 `\n`），第二步会移除 `\r`，使返回值变成 `"value"`。但 `"value\r"` 可能来自 old Mac 风格 redirected 文件或 binary-safe 管道，其中 bare `\r` 如果是 secret value 的合法组成部分，则会被错误剥离。
- **反例/失败场景**：
  1. 用户在某 old Mac 格式文本文件中写入 API key `"sk-test\r"`（末尾 `\r` 是 key 的一部分）。
  2. 通过 `python -m dayu.cli init < file.txt` 重定向输入。
  3. Python text mode `sys.stdin.readline()` 在 old Mac 文件上可能返回 `"sk-test\r"`（不转换 bare `\r`）。
  4. 算法检测不到末尾 `\n`，执行第二步检测到末尾 `\r`，移除 → `"sk-test"`。
  5. 传递给下游的 API key 少了一个字符，认证失败。
- **为什么有问题**：与 plan 自己声明的 "其它前导、尾随空白与字符原样保留" 不一致——`\r` 在此算法下会被当作 line ending 移除，即使它没有伴随 `\n`。
- **直接证据**：
  - Plan §13.2.2 点 2："返回一行时只移除一个 logical line ending：先移除末尾单个 `\n`，再移除其前单个 `\r`；其它前导、尾随空白与字符原样保留"。
  - 当输入为 `"value\r"` 时：步骤 1 无 `\n` 不操作 → `"value\r"`；步骤 2 检测到末尾 `\r` 移除 → `"value"`。这违反了"其它尾随字符原样保留"。
- **影响**：极低。原因：
  1. API key 中包含 bare `\r` 在现实中几乎不存在（绝大多数 API key 是 base64/hex 字符集）。
  2. Old Mac 格式（`\r` 作为行终止符）已废弃超过 20 年，在现代 redirected 管道中不太可能遇到。
  3. Windows redirected stdin 的 Python text mode `readline()` 会做 universal newline 转换，将 `\r\n` 转为 `\n`，将 bare `\r` 转为 `\n`（取决于 Python 版本和 build）。实际上 `readline()` 返回的字符串中不应出现 bare `\r`。
- **建议改法和验证点**：
  1. 可在 plan 中明确：line ending 移除仅适用于 `\n` 和 `\r\n` 两种 canonical 形式；bare `\r` 不被视为 line ending 并原样保留。实现改为：先移除末尾单个 `\n`；然后若字符串以 `\r` 结尾且原字符串以 `\r\n` 结尾（即步骤 1 确实移除了东西），才移除 `\r`。
  2. 也可接受当前算法，但 plan 文字中 "其它尾随空白与字符原样保留" 应改为 "其它尾随字符原样保留，bare `\r`（无前置 `\n`）被视为合法值的一部分并原样保留"。
- **修复风险（低）**：实现调整只是一行逻辑变更。
- **严重程度（低）**：影响概率极低，且大概率在真实环境中根本不可触发（Python universal newline 转换会先处理）。

---

## Open questions

`0`。当前 owner、输入能力分流、EOF/interrupt、slice allowlist、README、remote closure 与 security boundary 均已收敛。三个 findings 均有明确 fix plan，不需要 implementation agent 自行重新设计。

---

## Residual risks and tracking destination

1. **非 Windows 本地无法替代真实 CPython 3.11 Windows console/redirected handle 行为**（同 AgentCodex R1）：由 fresh R12 closure gate 追踪。
2. **caller pipe、OS handle 与 CLI process memory 必然暂存输入值**（同 AgentCodex R2）：本 WU 只承诺 CLI 不主动回显/投影。更广 transport threat model 属于独立安全设计。
3. **fresh remote 若在已修 owner 之后出现新 failure**（同 AgentCodex R3）：必须回到 diagnostic-first plan amendment。
4. **Controller 继续独立拥有 same-run canary scan**（同 AgentCodex R4）：implementation/test 不得取得 run-specific needle 或共享派生实现。
5. **DS-F01 的 TTY-path fixture 更新若被遗漏**：CI 中 test_init_command.py 失败会立即暴露；不影响 production 正确性，但会造成 CI red round-trip。建议 Controller 在 pre-implementation 阶段确认 fixture 更新策略，或要求 implementation agent 在 completion report 中明确报告 TTY/redirected fixture 机制。

---

## Final plan review conclusion

`PASS_WITH_FINDINGS / 3_MATERIAL_FINDINGS / 0_BLOCKERS / IMPLEMENTATION_NOT_AUTHORIZED`

**Findings severity summary：**

| Finding | Severity | Blocking? | Category |
|---|---|---|---|
| DS-F01 — 既有 getpass fixtures 在非 TTY 环境下可能误入 redirected path | 中 | No | 测试可重复性 |
| DS-F02 — WIN4-RW-S1 未显式要求 SourceSnapshot context manager 用法 | 低 | No | Plan 精确性 |
| DS-F03 — line ending 算法可能过度剥离孤立 trailing `\r` | 低 | No | Edge case 契约 |

**No blockers。** 三个 findings 均不构成结构性设计缺陷或 root cause 误判。DS-F01 需要 implementation agent 在 fixture 更新时做出明确选择，但其修复简单且可被 CI 立即验证。DS-F02/DS-F03 是 plan 文字精确性问题，不影响核心设计正确性。

Amendment 的 motivation、root cause、semantic owners、两个 slices 的 allowlist/顺序、negative tests、coverage/pyright/Ruff/diff/README/source scans、fresh remote rerun、same-run canary gate 与 deferred/security boundary 均已明确，可直接交给 implementation agent。下一步：AgentMiMo 完成第二路完整 review 后，Controller 汇总两路 findings 并裁决是否进入 plan fix → re-review → accepted amended-plan commit。
