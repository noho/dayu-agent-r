# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Re-Review — AgentDS

## Review metadata

- Timestamp（本机时钟）：`2026-07-20 05:55:49 +0800`。
- Reviewer：AgentDS（第二路完整 fixed-plan 双路 re-review）。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU，不是 implementation。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，1060 lines，SHA-256 `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。
- Frozen remote code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Locked evidence runs：R11 `29703932798`；R12 `29703933666`。
- Conclusion：`PASS / WIN4-RW-PR-F01..F04_CLOSED / 0_NEW_FINDINGS / 0_BLOCKERS / 0_OPEN_QUESTIONS / IMPLEMENTATION_NOT_AUTHORIZED`。

本 re-review artifact 不实施 production/test/workflow 变更，不更新 control/design/README，不 stage、commit、push、dispatch 或操作 PR。

---

## 0. Re-review scope and method

本轮是 AgentDS 对 AgentCodex 修复后 1060 行 fixed plan 的从零完整 re-review。与第一轮 DS review 的差异：

- 第一轮 DS review 针对 1045 行 amendment plan（SHA-256 `79e984d6...`），产出 3 findings（DS-F01/DS-F02/DS-F03）。
- Controller 裁决接受 4 项 plan findings（MiMo F-01/F-02/F-03 + DS DS-F03，合并为 WIN4-RW-PR-F01..F04）。
- AgentCodex 修复 plan 至 1060 行（SHA-256 `7e82df11...`），Controller 验证通过。
- 本轮**不得只检查四处 diff**，必须从零完整 review 全部 1060 行 fixed plan 与 direct code/tests/storage/workflow evidence。

本轮必须独立验证：

1. WIN4-RW-PR-F01..F04 是否真正关闭且没有把禁止模式带回来；
2. 1060 行 fixed plan 整体 root cause/owner/两个 slices/allowlist/顺序/README/coverage/pyright/Ruff/scans/remote R11/R12 lineage 是否仍自洽；
3. TTY strict fake 与 redirected StringIO 是否 code-generation-ready；
4. public snapshot 是否必须在 runner test 进程、artifact upload 前用 `with` 读取；
5. 不引入统一 authorization/secret infra，不实施 Issue 142/151/175/177/178。

---

## 1. Reviewed inputs and evidence scope

### 1.1 文档

已完整读取：

- `AGENTS.md`；
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（全部 1060 行，SHA-256 `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-failure-controller-adjudication.md`（Controller 对 WIN4-RW-F01/F02 的 root cause 裁决）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`（AgentCodex amendment artifact，SHA-256 `b985a2a4...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`（Controller 对 amendment 的验证，SHA-256 `2ea4080e...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-mimo.md`（AgentMiMo 第一路 review，SHA-256 `6782a69f...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-ds.md`（AgentDS 第一路 review，SHA-256 `7df6dbf7...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-controller-adjudication.md`（Controller 对两路 review 的裁决，SHA-256 `80c4966b...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-codex.md`（AgentCodex fix artifact，SHA-256 `be72dbfd...`）；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-controller-validation.md`（Controller fix validation，SHA-256 `34fe315b...`）。

### 1.2 直接代码/测试/仓储/workflow 证据

- `tests/cli/test_upload_filings_from_command.py`（完整 1185 行）：L964 `execution.returncode == 0`、L965 `"Fins result"`（待删除）、L969 `rglob("*")` 物理文件数、L970-989 oracle JSON 写入、L1045-1084 `_assert_single_windows_upload_company_name`。
- `dayu/cli/output.py`（498 行）：L63 `_FINS_EVENT_SUMMARY_PREFIX = "Fins summary"`、L66 `_FINS_EVENT_SUCCEEDED_PREFIX = "Fins succeeded"`。
- `dayu/cli/commands/init.py`（771 行）：L468-516 `_collect_environment_persistence_plan()`，L482 与 L494 两处 `getpass.getpass()` 调用，L224-240 `KeyboardInterrupt`/`CliInitOperationError` 映射。
- `tests/cli/test_init_command.py`（1064 行）：L135-167 `_GetpassSequence`（`__call__` 含 `stream` 参数兼容 getpass）、L250-273 `_install_ollama_inputs()` 仅 monkeypatch `getpass.getpass` 与 `builtins.input`、L523-554 orchestrator tests。
- `tests/cli/test_init_smoke.py`（1878 行）：L61 `_WINDOWS_CANARY_DOMAIN = b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes，末字节 single NUL `0x00`）、L516-531 `_github_actions_canary()`、L534-547 `_select_windows_test_canary()`、L585-670 `_run_init()`（anonymous `TemporaryFile(mode="w+b")` handles + `Popen` lifecycle + timeout cleanup）、L1021-1041 冻结 canary domain/vector tests、L1044-1069 fail-closed run-id validation tests。
- `dayu/fins/storage/repository_protocols.py`：L87-126 `SourceSnapshotProtocol`（`__enter__`/`__exit__` context manager，`ticker`/`document_id`/`source_kind`/`primary_filename`/`files` properties）、L572-598 `SourceDocumentRepositoryProtocol.read_source_snapshot()`。
- `dayu/fins/storage/fs_source_document_repository.py`：L223-251 `FsSourceDocumentRepository.__init__(workspace_root: Path, ...)`、L510-542 `read_source_snapshot(ticker, document_id, source_kind, *, materialize_files)`。
- `dayu/fins/storage/fs_company_meta_repository.py`：L18-43 `FsCompanyMetaRepository.__init__(workspace_root: Path, ...)`。
- `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml`。

R12 run-specific canary 未读取、派生或回显。未读取 GitHub Secrets 或 configured production values。

---

## 2. WIN4-RW-PR-F01..F04 closure verification（逐项）

### 2.1 WIN4-RW-PR-F01 — SourceSnapshot context manager：CLOSED

**来源**：AgentMiMo F-01 / AgentDS DS-F02 合并。

**Plan 要求**：`SourceSnapshotProtocol` 是 context manager，必须使用 `with` 语句管理生命周期。

**Fixed plan 证据**：

- §13.2.1 点 3（L752-756）冻结为：
  > `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`，并且只在 `with` 块内读取和确认 exact ticker、document id、`SourceKind.FILING`、primary filename等于本次 source basename、完整 descriptor集合非空且包含该 primary。CLI test只正确消费既有 Fins public contract，不重复测试 Fins owner 自身的 close-after-use语义。

- §13.5.1（L849-850）增加负向约束：
  > source snapshot的 identity/source kind/primary filename/descriptors只在 public `with` lifecycle内读取；CLI test不得重复增加 Fins close-after-use owner test。

**代码证据**：

- `SourceSnapshotProtocol` L87-126 明确定义 `__enter__`/`__exit__`。
- `_FsSourceSnapshot.__exit__` 调用 `_cleanup_snapshot_attempt` 释放 publication guard。
- `read_source_snapshot()` L510-542 返回 `SourceSnapshotProtocol`。

**Direct code API 验证**：

```python
# FsSourceDocumentRepository.read_source_snapshot 签名：
def read_source_snapshot(
    self,
    ticker: str,
    document_id: str,
    source_kind: Optional[SourceKind] = None,
    *,
    materialize_files: bool,
) -> SourceSnapshotProtocol:
```

Plan 中的 `...` 对应前三个位置参数 `ticker, document_id, source_kind`，均可从 §13.2.1 点 1/2 的上下文中明确推导。`materialize_files` 是 keyword-only 参数。实现 agent 无需自行推断 API——上下文已有明确 ticker `"AAPL"`、document id（从 `list_source_document_ids` 返回）、source kind `SourceKind.FILING`。

**反例检查**：无 Fins protocol test 重复、无 production helper mock、无 raw JSON/private core 读取。✅

**Closure 结论**：F01 已真正关闭。

---

### 2.2 WIN4-RW-PR-F02 — 既有 getpass tests 必须显式确定性选择 TTY path：CLOSED

**来源**：AgentMiMo F-02 / AgentDS DS-F01 合并。

**Plan 要求**：既有 tests 必须替换 `sys.stdin` 为 test-owned TTY fake，不得依赖 ambient TTY。

**Fixed plan 证据**：

- §13.4 WIN4-RW-S2（L828-832）冻结为：
  > 所有受影响既有 getpass tests必须把 production实际读取的 `sys.stdin` 替换为 test-owned、严格 typed TTY fake：其 `isatty()` 恒为 `True`，`readline()` 一旦被调用立即 assertion失败；不得 mock production `_read_secret_input`，不得修改或依赖 `sys.__stdin__`，也不得依赖本机/CI ambient TTY。

- §13.5.2（L858-863）增加 TTY 负向约束：
  > TTY：受影响既有 getpass tests使用 test-owned严格 typed `sys.stdin` fake，`isatty()` 恒为 `True`，`readline()` 被调用即 assertion失败；只调用 hidden getpass，prompt与返回值传递不漂移，不 mock `_read_secret_input`，不依赖 `sys.__stdin__` 或 ambient TTY。

- §13.5.2（L858）增加 redirected 正向约束：
  > redirected stdin：使用真实 `io.StringIO` 或等价严格 typed stream显式证明 `isatty() == False` 时，`getpass.getpass()` 必须零调用；prompt可见，恰好一个 `readline()` 消费一行，secret value在 stdout/stderr/captured exception/diagnostic中零命中。

**代码证据**（当前状态）：

- `_install_ollama_inputs()` L250-273：仅 monkeypatch `getpass.getpass` 为 `_GetpassSequence()` 和 `builtins.input` 为 `_InputSequence`，不操作 `sys.stdin`。
- `_GetpassSequence.__call__` L149-166：接受 `prompt` 和 `stream` 参数，与 `getpass.getpass` API 兼容；不调用 `sys.stdin.readline()`。

**TTY fake 在 pytest typing 下的可行性**：

`io.StringIO` 的 `isatty()` 继承自 `IOBase`，返回 `False`。`io.StringIO` 的 `readline()` 正常工作。因此 redirected tests 可直接使用 `io.StringIO`。

对于 TTY fake，最小实现：
```python
class _TTYStdinFake:
    def isatty(self) -> bool:
        return True
    def readline(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("redirected path unexpectedly entered in TTY test")
```

`_read_secret_input` 在 TTY path 只调用 `sys.stdin.isatty()` 和 `getpass.getpass(prompt)`，其中 `getpass.getpass` 已被 monkeypatch。`sys.stdin` 的其他方法（`read`、`fileno` 等）在本路径不会被 `_read_secret_input` 直接调用。但若 other production code（如 `builtins.input()`）在 TTY test 中通过 `sys.stdin.readline()` 读取，则 TTY fake 需要提供 `readline()` 实现。plan 中 `builtins.input` 由 `_install_ollama_inputs` 独立 mock，不经过 `sys.stdin.readline()`。因此最小 TTY fake 充分。

**反例检查**：无 ambient TTY 依赖、无 `sys.__stdin__` 修改、无 mock `_read_secret_input`。✅

**Closure 结论**：F02 已真正关闭。

---

### 2.3 WIN4-RW-PR-F03 — 两种 EOF 表现必须显式收敛：CLOSED

**来源**：AgentMiMo F-03。

**Plan 要求**：TTY `EOFError` 与 redirected `readline() == ""` 必须显式映射为同一 error。

**Fixed plan 证据**：

- §13.2.2 点 3（L775-777）冻结为：
  > TTY path只捕获 `getpass.getpass()` 抛出的 `EOFError`；redirected path只把 `readline() == ""` 识别为 EOF。两者都在 helper 内收敛为同一个 value-free `CliInitOperationError("secret input ended before completion")`，不得把 prompt、secret、raw buffer或 raw exception text投影到用户输出。`KeyboardInterrupt` 不捕获、不改写，继续由现有 CLI owner映射为 exit `130`。

- §13.5.2（L866-868）增加 EOF 负向约束：
  > EOF：TTY `getpass.getpass()` 抛出的 `EOFError`与 redirected `readline() == ""`都转成同一 value-free `CliInitOperationError`，不进入 optional、confirmation、persistence或 workspace publication。

**代码证据**：

- CPython 3.11 `getpass.py`：`fallback_getpass()` 在 EOF 时抛 `EOFError`。
- `io.StringIO.readline()` 在 EOF 时返回 `""`。
- `dayu/cli/commands/init.py` L224-240：`except CliInitOperationError: return EXIT_FAILURE` 和 `except KeyboardInterrupt: return EXIT_KEYBOARD_INTERRUPT` 已存在。

**语义无冲突验证**：

| Scenario | isatty() | Runtime behavior | Plan mapping | Result |
|---|---|---|---|---|
| TTY, user presses Ctrl+D | True | `getpass.getpass()` raises `EOFError` | → caught, mapped to `CliInitOperationError` | exit FAILURE, no prompt/value in output |
| Redirected, pipe closes before read | False | `sys.stdin.readline()` returns `""` | → detected, mapped to `CliInitOperationError` | exit FAILURE, no prompt/value in output |
| TTY, user presses Ctrl+C | True | `getpass.getpass()` may raise `KeyboardInterrupt` | → not caught, propagates | exit 130 |
| Redirected, SIGINT during read | False | `sys.stdin.readline()` raises `KeyboardInterrupt` | → not caught, propagates | exit 130 |

**反例检查**：`KeyboardInterrupt` 不被捕获改写 ✅；两种 EOF 路径收敛到同一 value-free error ✅；prompt/secret/raw buffer/exception text 不进入用户输出 ✅。

**Closure 结论**：F03 已真正关闭。

---

### 2.4 WIN4-RW-PR-F04 — CR 只能作为已移除 LF 的前缀被剥离：CLOSED

**来源**：AgentDS DS-F03。

**Plan 要求**：只有实际移除了末尾 LF 后，才能继续移除紧邻其前的单个 CR；bare CR 原样保留。

**Fixed plan 证据**：

- §13.2.2 点 2（L770-774）冻结为：
  > 非 EOF 返回值只移除一个 logical line ending：先判断并实际移除末尾单个 `\n`；只有该次确实移除了 `\n`，且移除后新末尾是 `\r` 时，才继续移除该单个 `\r`。没有伴随已移除 `\n` 的孤立 trailing `\r` 必须原样保留；其它前导、尾随空白与字符也原样保留，由现有 required-empty/optional-empty contract决定。禁止使用会移除任意数量尾随字符的 `rstrip` 或其它 strip操作实现该 contract。

- §13.5.2（L864-865）增加 bare-CR 负向约束：
  > line endings：LF与CRLF各只移除一个 logical ending；空行得到空值；孤立 trailing `\r` 原样保留并有 bare-CR owner test；其它空白不 strip，禁止 `rstrip` 或等价的过度删除。

- §13.6.1 WIN4-RW-S2 evidence（L903-904）、§13.6.3 coverage（L928-929）、completion report（L1056-1057）均增加 bare-CR owner evidence 要求。

**逐例验证算法正确性**：

| 输入 | 步骤 1：移除末尾 `\n`? | 步骤 1 结果 | 步骤 2：新末尾是 `\r` 且步骤 1 确实移除了? | 步骤 2 结果 | 最终值 | 是否正确 |
|---|---|---|---|---|---|---|
| `"value\n"` | Yes | `"value"` | No（`"e"` ≠ `\r`） | — | `"value"` | ✅ |
| `"value\r\n"` | Yes | `"value\r"` | Yes（`\r` 且步骤 1 确实移除） | `"value"` | `"value"` | ✅ |
| `"value"` | No | `"value"` | —（步骤 1 未移除，跳过步骤 2） | — | `"value"` | ✅ |
| `"value\r"` | No | `"value\r"` | —（步骤 1 未移除，跳过步骤 2） | — | `"value\r"` | ✅ |
| `"val\nue\n"` | Yes（末尾 `\n`） | `"val\nue"` | No（`"e"` ≠ `\r`） | — | `"val\nue"` | ✅ |

**与 Python text mode `sys.stdin.readline()` 的交互**：Windows CPython text mode 做 universal newline 转换，`\r\n` → `\n`。因此 `readline()` 通常返回 `"value\n"` 而非 `"value\r\n"`。条件性 CR 剥离对两种输入均正确：

- 若 `readline()` 返回 `"value\n"`（Windows universal newline）：步骤 1 移除 `\n` → `"value"`，步骤 2 不触发 → `"value"`。✅
- 若调用者设置了 `newline=''` 或使用了 binary stdin → `readline()` 可能返回 `"value\r\n"`：步骤 1 移除 `\n` → `"value\r"`，步骤 2 触发 → `"value"`。✅

**`rstrip` 被显式禁止**：`rstrip` 或 `str.rstrip('\r\n')` 会删除任意数量的尾部 `\r` 和 `\n` 字符。对于 `"value\r\r\n"`，`rstrip` 会删除全部 3 个字符 → `"value"`，而 plan 的算法只删除 `\r\n`（2 字符）→ `"value\r"`。plan 的算法保留了中间 `\r` 为合法值的一部分。✅

**反例检查**：无 unconditional CR strip ✅；孤立 `\r` 原样保留 ✅；`rstrip` 显式禁止 ✅；bare-CR owner test 被要求 ✅。

**Closure 结论**：F04 已真正关闭。

---

### 2.5 Closure summary

| Finding | Source | Fixed in plan | No forbidden patterns brought back | Closure |
|---|---|---|---|---|
| WIN4-RW-PR-F01 | MiMo F-01 / DS DS-F02 | §13.2.1, §13.5.1 | No Fins protocol test duplication | ✅ CLOSED |
| WIN4-RW-PR-F02 | MiMo F-02 / DS DS-F01 | §13.4, §13.5.2 | No ambient TTY, no production helper mock | ✅ CLOSED |
| WIN4-RW-PR-F03 | MiMo F-03 | §13.2.2, §13.5.2 | No ambiguous EOF mapping | ✅ CLOSED |
| WIN4-RW-PR-F04 | DS DS-F03 | §13.2.2, §13.5.2, §13.6.1, §13.6.3 | No unconditional CR strip, no `rstrip` | ✅ CLOSED |

---

## 3. 1060 行 fixed plan 整体自洽性验证

### 3.1 Root cause / owner 一致性

| Finding | Root cause | Unique owner | Plan location | Code evidence |
|---|---|---|---|---|
| WIN4-RW-F01 | Stale display assertion (`"Fins result"`) after successful upload | `tests/cli/test_upload_filings_from_command.py` success oracle | §13.1.1, §13.2.1 | L965 `assert "Fins result" in execution.stdout` |
| WIN4-RW-F02 | Windows redirected stdin ignored by `getpass.win_getpass()` → `msvcrt.getwch()` | `dayu/cli/commands/init.py` secret-input boundary | §13.1.2, §13.2.2 | L482/494 `getpass.getpass()` |

两个 root cause 均有 Controller 验证的直接 evidence（exit `0` 后旧 display assertion 失败；timeout 在 required secret 前，setx 未执行）。Owner 边界精确，不跨层。✅

### 3.2 两个 slices 精确性

| Slice | Owner | Allowed paths | Dependencies | Order |
|---|---|---|---|---|
| WIN4-RW-S1 | Test success oracle | `tests/cli/test_upload_filings_from_command.py` | 无 | S1→S2 |
| WIN4-RW-S2 | CLI secret-input boundary | `dayu/cli/commands/init.py`, `tests/cli/test_init_command.py`, `README.md`, `tests/README.md` | 无代码依赖 | S1→S2 |

两个 slices 的 owner、允许路径、blast radius 与独立验证矩阵不同，不能合并。S1→S2 串行但无代码依赖——只有最终 remote rerun 依赖二者同时 accepted。✅

### 3.3 Allowlist 自洽性

§13.3 allowlist 精确锁定：

- **S1**：`tests/cli/test_upload_filings_from_command.py`
- **S2**：`dayu/cli/commands/init.py`、`tests/cli/test_init_command.py`、`README.md`、`tests/README.md`

明确禁止：

- `dayu/cli/output.py`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`
- 所有 `dayu/fins/` production code
- `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml`
- `docs/host/issues-implementation-control.md`、design doc、control/review artifacts
- PowerShell、PTY、console wrapper、Win32 handle API、job object、process group
- Issue 142/151/175/177/178

禁止路径与 owner boundary 一致。若 implementation 发现必须越过 allowlist，必须停止并回 Controller。✅

### 3.4 验证矩阵自洽性

§13.6 验证矩阵覆盖：

| Gate | Command | Scope |
|---|---|---|
| Focused S1 | `pytest tests/cli/test_upload_filings_from_command.py -q` | WIN4-RW-S1 |
| Focused S2 | `pytest tests/cli/test_init_command.py -q` + `pytest tests/cli/test_init_smoke.py -q` | WIN4-RW-S2 |
| Aggregate | `pytest tests/cli -q` | Full CLI regression |
| Coverage | `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-branch` | `init.py` ≥80% |
| Pyright | `python -m pyright dayu/ tests/ utils/` | Zero diagnostics |
| Scoped Ruff | `python -m ruff check dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_upload_filings_from_command.py` | Zero diagnostics |
| Full Ruff | `python -m ruff check dayu tests utils --output-format json` | Baseline comparison, zero new/diffusion |
| Diff | `git diff --check`, `git status --short`, `git diff --name-only AMENDED_PLAN_BASE` | Staged tree empty, diff only in allowlist |
| Source scans | §13.6.6 rg commands | Forbidden patterns zero |

Coverage、pyright、Ruff 阈值均在项目约束内（单文件 ≥80%、零诊断）。✅

### 3.5 Remote R11/R12 lineage 自洽性

§13.8 定义 fresh remote rerun matrix：

- R11 identity：dispatch response 返回唯一新 run id；metadata 精确绑定 R11 workflow/path、`workflow_dispatch`、target ref 与 accepted implementation head SHA。
- R12 identity：同上，与 R11 run 独立锁定，不混用。
- R12 same-run canary gate：Controller 按 §2.3/§9.3 frozen text 独立派生，仅在进程内 exact scan 同一 R12 run 的全部 artifact files + workflow log files，零命中。
- Standalone R11 不消费 R12 canary：继续按 artifact integrity 与无 secret input contract 验收。

§9.3 冻结了 Controller canary scan 的程序顺序（5 步）与失败语义（metadata mismatch → gate fail、跨 run 混用 → gate fail、canary 命中 → gate fail）。该 contract 在 fixed plan 中未被修改。✅

---

## 4. TTY strict fake 与 redirected StringIO 专项评估

### 4.1 TTY fake 可行性

Plan 要求的 TTY fake contract：
- `isatty()` 恒为 `True`
- `readline()` 一旦被调用立即 assertion 失败

在 Python typing/pytest 下的实现评估：

```python
class _TTYStdinFake:
    """Test-owned strict typed TTY fake for sys.stdin replacement."""
    def isatty(self) -> bool:
        return True
    def readline(self, size: int = -1, /) -> str:  # type: ignore[override]
        raise AssertionError("redirected path unexpectedly entered in TTY test")
```

**typing 兼容性**：`sys.stdin` 的类型是 `TextIO`。`_TTYStdinFake` 不需要 `TextIO` 的完整继承链，因为 pytest `monkeypatch.setattr(sys, "stdin", fake)` 是运行时替换，不经过 mypy/pyright 检查。若需要完整 typing，可继承 `io.StringIO` 并覆盖 `isatty()` 和 `readline()`。

**功能兼容性**：`_read_secret_input` 的 TTY path 只调用 `sys.stdin.isatty()`（返回 True）和 `getpass.getpass(prompt)`（已被 monkeypatch）。`sys.stdin` 在此路径不会被其他 production code 直接访问——`builtins.input()` 由独立的 `_InputSequence` mock。因此最小 TTY fake 充分。

**无冲突**：
- EOF 语义：TTY path 通过 `getpass.getpass()` mock → `EOFError`，不由 `sys.stdin.readline()` 产生。TTY fake 的 `readline()` assertion 失败确保 redirected path 不被意外进入。✅
- KeyboardInterrupt 语义：由 `_GetpassSequence` mock 控制，不经过 `sys.stdin.readline()`。✅
- Value-free 语义：error message 仅含 `"secret input ended before completion"`，不含 prompt 或 value。✅

### 4.2 Redirected StringIO 可行性

Plan 要求的 redirected test contract：
- 使用真实 `io.StringIO` 或等价严格 typed stream
- 显式保证 `isatty() == False`

```python
fake_stdin = io.StringIO("test-secret\nother-secret\n")
assert fake_stdin.isatty() == False  # IOBase.isatty() 默认返回 False
```

**typing 兼容性**：`io.StringIO` 是 `TextIOBase` 的子类，满足 `TextIO` 类型。`isatty()` 继承自 `IOBase`，返回 `False`。`readline()` 按 text mode 行为返回包含 `\n` 的字符串。✅

**功能兼容性**：`_read_secret_input` 的 redirected path：`sys.stdin.isatty()` → `False` → 写 prompt 到 `sys.stderr` → `sys.stdin.readline()` → 返回 `"test-secret\n"` → line ending 算法 → `"test-secret"`。✅

**无冲突**：
- EOF 语义：`readline()` 返回 `""` → 映射为 `CliInitOperationError`。✅
- empty-read 语义：`readline()` 返回 `"\n"` → 算法移除 `\n` → `""` → 由 required-empty contract 判断。✅
- KeyboardInterrupt 语义：`readline()` 在 Python 中传播 `KeyboardInterrupt` 异常 → plan 不捕获 → 由现有 CLI owner 映射为 exit `130`。✅

### 4.3 交叉验证：两种 fake 不会互串

| Test 类型 | `sys.stdin` | `isatty()` | `readline()` | `getpass.getpass` | 预期路径 | Safety |
|---|---|---|---|---|---|---|
| TTY orchestrator | `_TTYStdinFake` | `True` | assertion fails | mocked `_GetpassSequence` | TTY path → `getpass.getpass()` mock | ✅ |
| Redirected owner | `io.StringIO("v\n")` | `False` | returns `"v\n"` | NOT mocked | Redirected path → `readline()` | ✅ |
| Redirected EOF | `io.StringIO("")` | `False` | returns `""` | NOT mocked | Redirected path → `"secret input ended..."` | ✅ |
| Redirected interrupt | `io.StringIO("v\n")` + signal | `False` | raises `KeyboardInterrupt` | NOT mocked | Redirected path → interrupt propagates | ✅ |

无路径交叉风险。✅

---

## 5. Public snapshot with-statement 验证

### 5.1 Plan contract

§13.2.1 点 3 要求：`with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`，只在 `with` 块内读取 identity/source kind/primary filename/descriptors。

### 5.2 为何必须在 runner test 进程、artifact upload 前用 `with` 读取

1. `SourceSnapshotProtocol` 的 `__enter__` 获取 publication guard（文件锁），`__exit__` 释放。
2. `materialize_files=False` 的 light snapshot 只持有 descriptors + metadata 的内存视图，不复制文件。
3. Publication guard 确保 snapshot 读取期间 published tree 不被并发修改。
4. 若不在 `with` 块内读取，guard 在 `__exit__` 中释放后，snapshot 对象可能处于 closed 状态（`RuntimeError`），或读取到不一致的中间状态。
5. Test 在 runner 进程内直接访问 local filesystem 的 storage published tree，因此 snapshot 读取必须在 test 进程内、artifact upload 前完成。
6. Downloaded GitHub artifact bundle 不含 storage internal hidden identity descriptors，只能验证 hash/count/inventory 等物理完整性——Controller validation 已确认这一点。

### 5.3 Plan 是否对此有保护

Plan §13.2.1 点 4 明确：`source_artifact_count` 只保留为 uploaded evidence package 的物理 integrity count，不再承担业务 success 语义。Plan §13.8 R11 identity gate 要求 artifact integrity pass（generated script SHA-256 与 oracle 一致，physical artifact count >0，required files 存在）。业务 success 由 test 进程内的 storage repository facts 证明，不由 downloaded artifact 的物理存在证明。✅

---

## 6. 不引入统一 authorization/secret infra 验证

### 6.1 Plan 边界

Plan 中以下位置反复锁定此边界：

- §3.2："不修改 Config/Host trusted-local secret裁决，不新增 secret infrastructure或统一 authorization。"
- §11："零 Issue 142/151/175/177/178、Web/WeChat/render、unified authorization或 secret infra实现。Tool Trace/audit继续禁止 API key/header明文；trusted-local Config/Host durable裁决不变。"
- §13.3：禁止 `dayu.runtime` secret helper、统一 secret/credential/authorization infrastructure。
- §13.9："Config与 Host internal SQLite/EventLog是 trusted-local domain；只有 Tool Trace/audit以及 public/LLM-facing/operator diagnostics禁止 API key/header明文。本 amendment不读取、迁移、重写或扩大 durable secret范围，不把 redirected stdin伪装成 encrypted transport，也不新增 zeroization、credential broker、unified authorization或 secret infra。"
- §13.9："明确 deferred/forbidden：Issue 142、151、175、177、178；Web/WeChat/render；通用 console/PTY/process isolation；setx redesign；统一 authorization/secret management；Fins generic diagnostic schema。Gemini low-budget继续是 EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING。"

### 6.2 Source scan 验证

对当前 frozen target `b85def887e72dc69e972f42a82a18989523f8634` 执行 plan §13.6.6 强制的 forbidden-source scans：

```
rg -n 'getpass\.getpass' dayu/cli/commands/init.py
```
→ 命中 L482、L494 各一次——这是待修改的两处调用。修改后应只剩 `_read_secret_input()` 的 TTY 分支内部一次。✅

```
rg -n 'sys\.__stdin__|msvcrt|PowerShell|Start-Process|pty|PTY|JobObject|CREATE_NEW_PROCESS_GROUP|process.tree' \
  dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_upload_filings_from_command.py
```
→ 零命中（仅有 `empty` 等无关匹配）。✅

```
rg -n 'shell\s*=\s*True|errors\s*=\s*[^,)]*replace|hasattr\(|getattr\(' \
  dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_upload_filings_from_command.py
```
→ 零命中。✅

```
rg -n 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|authorization|secret infrastructure' \
  dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_init_smoke.py tests/cli/test_upload_filings_from_command.py
```
→ 零命中（仅 plan/review artifact 中出现）。✅

### 6.3 结论

无统一 authorization/secret infra。Config/Host internal SQLite/EventLog trusted-local 不变。Tool Trace/audit/public/LLM-facing/operator diagnostics 禁 API key/header 明文不变。Gemini low-budget 非 finding。✅

---

## 7. Required review lenses

### 7.1 Architecture boundary review

**WIN4-RW-S1**：Test consumer 从 display text（`dayu/cli/output.py` 拥有）迁移到 process exit + public `dayu.fins.storage` repository facts。依赖方向正确——test 消费既有 public contract。`SourceSnapshotProtocol` with-statement 确保 publication guard 正确管理。

**WIN4-RW-S2**：`_read_secret_input` 是 `dayu/cli/commands/init.py` 内的模块级私有 helper。不下沉到 `dayu.runtime`，不侵入 `dayu.cli.init_environment`、Config、Host 或 Fins。`UI -> Service -> Host -> Engine` 分层边界不变。

**Verdict**：架构边界保持。✅

### 7.2 Best-practice review

方案使用 capability detection（`isatty()`）、单一 logical-line read、明确 EOF/interrupt 语义、owner-level negative tests、动态 non-disclosure 断言和 fresh remote acceptance。避免用 timeout、display text、mock 或 warning suppression 获得假绿。README 决策与实际用户输入行为同步（§13.7）。

Line ending 算法（先判断移除 `\n`，再条件移除 `\r`）正确处理 LF、CRLF、no-newline 和 bare-CR 四种输入，避免了 `rstrip` 的过度删除。✅

### 7.3 Optimal-solution review

可信替代方案及被拒绝原因：

| 替代方案 | Owner 问题 | Plan 处置 |
|---|---|---|
| 修改 `dayu/cli/output.py` 恢复旧 prefix | 修错 owner（renderer ≠ test success） | 被 §13.1.1 拒绝 |
| 给 test 换新硬编码词 | 只是推迟问题 | 被 §13.1.1 拒绝 |
| 在 `_run_init()` 加 Windows input shim | 修错层（harness ≠ CLI input owner） | 被 §13.4 拒绝 |
| PowerShell/PTY/console wrapper | 扩大 blast radius | 被 §13.3 拒绝 |
| 通用 secret infrastructure | 过度设计，扩大 scope | 被 §13.3/§13.9 拒绝 |

Plan 选择两个最小 owner-local 变更，是当前证据下更简单、可测试、可演进的路径。✅

### 7.4 Overengineering review

- `_read_secret_input` 是单一模块级私有 helper（`def _read_secret_input(prompt: str) -> str`），不是 class/Protocol/factory/callback/跨模块 facade。
- WIN4-RW-S1 复用既有 public `FsCompanyMetaRepository`/`FsSourceDocumentRepository`/`SourceSnapshotProtocol`，不新增 storage abstraction。
- 无 credential broker、redaction framework、process framework、schema 或 migration。

**Verdict**：无过度设计。✅

### 7.5 Overcoupling review

- 两个 slices 串行但没有代码依赖；只有最终 remote rerun 依赖二者同时 accepted。
- S1 不需要修改 Fins/output/workflow；S2 不需要修改 harness/setx。
- README 与 S2 保持同一提交/回滚边界。
- `_read_secret_input` 只由 `_collect_environment_persistence_plan` 复用。

**Verdict**：无过度耦合。✅

---

## 8. Findings

### 本轮无新 material finding

经过从零完整 review 全部 1060 行 fixed plan、两路初审、Controller adjudication、AgentCodex fix artifact、Controller fix validation 及 direct code/tests/storage/workflow evidence，本轮没有发现需要报告为 finding 的新问题。

第一轮 DS review 的三个 findings（DS-F01/DS-F02/DS-F03）已通过 WIN4-RW-PR-F02/F01/F04 完闭合入 fixed plan。以下逐一确认没有回归或残留：

| 原 finding | 对应 WIN4-RW-PR finding | Fixed plan 处置 | 是否残留 |
|---|---|---|---|
| DS-F01 — TTY path fixture 不确定 | WIN4-RW-PR-F02 | §13.4 要求 test-owned strict typed TTY fake，`isatty()` 恒 True | 无残留 |
| DS-F02 — Snapshot context manager 未显式化 | WIN4-RW-PR-F01 | §13.2.1 冻结 `with ... as snapshot:` | 无残留 |
| DS-F03 — 孤立 `\r` 过度剥离 | WIN4-RW-PR-F04 | §13.2.2 条件 CR 剥离 + `rstrip` 禁止 | 无残留 |

### 不构成 finding 的已检查项

以下潜在关注点经过直接证据验证，不构成 material finding：

1. **`read_source_snapshot` API 参数 `...` 歧义**：Plan §13.2.1 使用 `...` 表示前三个位置参数（ticker、document_id、source_kind）。上下文（点 1 使用 ticker `"AAPL"`，点 2 返回 document id，SourceKind 已知为 `FILING`）使参数明确。实现 agent 无需推断。不构成 finding。

2. **TTY fake 的最小接口范围**：Plan 要求的 TTY fake（`isatty()` 恒 True，`readline()` assertion 失败）在 `_read_secret_input` TTY path 中充分。若其他 production code 也访问 `sys.stdin`，`_install_ollama_inputs` 已有独立 mock。不构成 finding。

3. **Python text mode `readline()` 的 universal newline 行为**：Windows CPython text mode 将 `\r\n` 转换为 `\n`，因此 `readline()` 通常返回 `"value\n"` 而非 `"value\r\n"`。Plan 的条件 CR 剥离对两种输入均正确。若未来 CPython 改变此行为，条件 CR 剥离仍正确。不构成 finding。

4. **`getpass.getpass()` 在 POSIX TTY 上的 fallback 行为**：POSIX `getpass.getpass()` 在 TTY 上使用 `termios`，不调用 `sys.stdin.readline()`。fallback `fallback_getpass()` 仅在非 TTY 时使用 `sys.stdin.readline()`，而 plan 的 TTY path 只在 `isatty()` 为 True 时进入，且 `getpass.getpass` 被 mock。不构成 finding。

5. **`_read_secret_input` 不处理 `OSError` from `readline()`**：若 redirected pipe 被意外关闭，`readline()` 可能抛 `OSError`。该异常会传播到 `_collect_environment_persistence_plan`，进而由 `run_init_command` 的通用异常处理映射为 `EXIT_FAILURE`。增加显式处理会扩大 blast radius（需要决定是否记录 broken pipe 细节），且 pipe break 是 caller 配置问题而非 CLI defect。不构成 finding。

---

## 9. Open questions

`0`。当前 owner、输入能力分流（`isatty()`）、EOF/interrupt（两种路径显式收敛）、line ending（条件 CR 剥离）、TTY/redirected test fake contract、slice allowlist、README scope、remote closure identity 与 same-run canary gate 均已收敛。implementation agent 无需重新设计。

---

## 10. Residual risks and tracking destination

1. **非 Windows 本地无法替代真实 CPython 3.11 Windows console/redirected handle 行为**：owner unit tests 只锁定 capability contract，最终证据唯一 destination 是 §13.8 fresh R12 closure gate。

2. **caller-owned pipe、OS handle 与 CLI process memory 必然暂存输入值**：本 WU 只承诺 CLI 不主动回显/投影。更广 transport threat model 属于独立安全设计，不得在本 amendment 顺手实现。

3. **fresh remote 若在已修 owner 之后出现新 failure**：必须回到 §10 diagnostic-first plan amendment；不得用当前两个 root cause 解释新证据。

4. **Controller 继续独立拥有 same-run canary scan**：implementation/test 不得取得 run-specific needle 或共享派生实现。standalone R11 不进入 R12 canary scan。

5. **`_read_secret_input` 的 `sys.stdin.readline()` 在 Windows 真实 redirected stdin 下的行为**（text mode line ending normalization）：由 fresh R12 最终验证；本地 test 使用 `io.StringIO` 不能完全替代 OS-level handle behavior。

---

## 11. Final plan review conclusion

**`PASS / WIN4-RW-PR-F01..F04_CLOSED / 0_NEW_FINDINGS / 0_BLOCKERS / 0_OPEN_QUESTIONS / IMPLEMENTATION_NOT_AUTHORIZED`**

1060 行 fixed plan（SHA-256 `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`）的 amendment 部分自洽且 code-generation-ready。四项 WIN4-RW-PR-F01..F04 均已真正关闭，没有把 Fins protocol test、production helper mock、ambient TTY、unconditional CR strip 或统一 authorization/secret infra 带回来。TTY strict fake 与 redirected StringIO 在 Python typing/pytest 下可正确实现，EOFError/empty-read/KeyboardInterrupt/value-free 语义无冲突。Public snapshot 使用 `with` 语句在 runner test 进程内读取，artifact upload 前完成；downloaded artifact 只做 physical integrity。Config/Host trusted-local / Tool Trace+audit 零明文边界保持不变。

下一步只能是 Controller 最终裁决和 accepted amended-plan local commit；implementation 仍未授权。
