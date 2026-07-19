# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第二轮 Windows fix（AgentCodex）

## 状态与边界

- 状态：`LOCAL_FIX_VALIDATED / WINDOWS_RERUN_REQUIRED`；同一 AR-F07 follow-up 已按本文件计划实施并完成本地门禁。
- 基线：`ac5e755ba7148a5d2f30f3f11222548b3c57cd9e`；draft PR：`179`。
- 这不是新 WU，也不创建替代 WU；不修改 control doc，不 stage/commit/push，不修改 PR，不 dispatch workflow。
- 不实施 Issue 142、151、175、177、178、Web/WeChat/render deferred 能力或统一 tool authorization framework；不修改 provider/model/key/retry/quota/budget。
- 数据裁决保持不变：本地 Config / Host internal SQLite / EventLog 可以持有 key/header；Tool Trace、audit、public、LLM、log、output、diff、review 禁止 secret 明文。本 artifact 只记录环境变量名和错误类型，不记录值。
- Gemini 低预算分类为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## 已完整核对的真源

- 第二轮真实 Windows evidence：
  - `workspace/tmp/wu-semantic-ownership-01-r11-run-29692213143/`
  - `workspace/tmp/wu-semantic-ownership-01-r12-run-29692213135/`
- 治理与已接受设计：`AGENTS.md`、`docs/host/issues-implementation-control.md` 当前 AR-F07、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、R11/R12 accepted plans、现有 AR-F07 plan/fix/review/adjudication artifacts。
- 当前实现与测试：CLI 入口、init/upload 命令、公共输出、upload script renderer/publisher、R11/R12 workflows 及对应 CLI tests。
- OLD 行为证据：`/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` 的 `upload_filings_from` `.sh/.cmd` 真实工作流。OLD 的 direct batch body、UTF-8/CRLF、`chcp 65001`、追加 argv 行为是工作流证据；其 `subprocess.list2cmdline` 与未经验证的 raw `%*` 不是可恢复的 owner 设计。

## 第二轮 artifact 事实

### R11 run 29692213143

- artifact 只有完整的 `cmd-version.txt`、`cmd-help.txt` 与 `environment.txt`，没有 pytest/JUnit/renderer oracle。
- `ver` 已产生 Windows 版本证据；`cmd.exe /?` 已产生完整 help artifact，且 `environment.txt` 记录 `cmd_help_exit_code=1`。
- workflow 在 help probe 后停止，证明不是 cmd capability 不存在，而是 pwsh native pipeline 在 owner 自己分类 exit code 前先终止 step。

### R12 run 29692213135

- init JUnit：9 nodes，7 pass、2 fail。失败节点是
  `test_windows_real_four_state_and_config_reload` 与
  `test_windows_real_setx_round_trip_is_name_safe_and_cleaned`，二者共同直接报
  `UnicodeEncodeError: 'charmap' codec can't encode characters`；其余 junction、symlink、workspace identity、non-POSIX key monitor、publication rollback、scan-delete race 均通过。
- R11-in-R12 JUnit：2 nodes，2 fail。
  - recorder 实际 argv 在带 literal quote 后丢失固定 `&` 的语义并未追加 `%*` argv；oracle 同时包含 empty、space、中文、literal quote、trailing slash、literal percent、`!`、`&` 及 injection-shaped appended argv。
  - real CLI storage node 在 `python -m dayu.cli ... upload_filing` 中文输出处报同一 `UnicodeEncodeError`。
- 因此 R12 的两个 `setx` 相关表面失败均属于 WIN2-F01 传播，不产生新的 registry owner 语义；环境 evidence 仍只暴露变量名。

## Accepted findings：直接根因与唯一 owner

### WIN2-F01 — PRODUCT / 公共 CLI stream owner

- 直接根因：Windows runner 的 redirected `sys.stdout`/`sys.stderr` 是 locale/charmap 编码的真实 `TextIOWrapper`；`chcp 65001` 不会重建 Python 已创建的文本 wrapper。init 与 upload 的合法中文输出因此在公共 CLI 进程边界编码失败。
- 唯一 owner：`dayu/cli/main.py`，因为 console script 与 `python -m dayu.cli` 都汇入 `main()`，而命令模块和 `dayu/cli/output.py` 不是所有 stdout/stderr 写入的共同边界。
- 修复：在参数解析和任何 CLI 输出之前，把真实标准 `io.TextIOWrapper` 的 stdout/stderr 明确 reconfigure 为 UTF-8 + strict。只识别具体 wrapper 类型；`StringIO` 等非 `TextIOWrapper` capture 保持调用方语义。失败继续透传，禁止吞错、测试环境补丁、命令级 catch、lazy import 或 `hasattr/getattr`。

### WIN2-F02 — PRODUCT / Windows batch renderer owner

- 直接根因：`dayu/cli/upload_script.py` 当前只实现 CRT backslash/quote 规则和 percent doubling，但把普通 `"..."` 直接写入 batch。`cmd.exe` 不把反斜杠视作 quote escape，literal quote 会改变 cmd parse state；其后的 literal `&` 被当作命令分隔符，raw `%*` 也不再处于预期语法位置，导致 fixed argv 截断、appended argv 丢失并形成注入面。
- 唯一 owner：`dayu/cli/upload_script.py` 的 Windows renderer。Fins typed plan、CLI command、publisher、测试和 workflow 都不是平台 quoting owner。
- 修复：保留 direct executable body 和 raw `%*` public passthrough，不恢复 JSON argv 协议或 `list2cmdline`。renderer 同时完成 batch 与 CRT 两层编码：percent 按 batch 规则 doubling；所有由 CRT 需要的 quote 以及 cmd metacharacter 用 caret 保护，使 cmd 不持有 renderer 的 quote state，cmd 解码后再由目标进程 CRT 精确恢复一个 argv。拒绝会跨 batch 行/NUL 的 argv。POSIX 继续使用 `shlex.join(...)` + `"$@"`。

### WIN2-F03 — WORKFLOW / R11 process probe owner

- 直接根因：R11 workflow 通过 pwsh native pipeline 执行 `cmd.exe /?`；真实 exit 1 在脚本读 `$LASTEXITCODE` 并执行 0/1 分类前已由 pwsh native error policy 终止。
- 唯一 owner：`.github/workflows/r11-upload-script-windows.yml` 的 runner capability step。
- 修复：仅该 step 用 `System.Diagnostics.Process` 做精确、redirected、无 shell 的 per-process 调用，完整保存 stdout/stderr；严格断言 `cmd.exe /d /c ver == 0` 与 `cmd.exe /? == 1`。不全局修改 PowerShell native error policy，不 ignore 任意 native failure，不弱化后续真实 cmd execution gate。

## 精确修改计划与 planned paths

1. `dayu/cli/main.py`：增加公共标准流 UTF-8/strict 配置 owner，并在 `main()` 第一条可执行路径调用。
2. `tests/cli/test_arg_parsing.py`：用真实 `io.TextIOWrapper(BytesIO, encoding="cp1252")` 锁定中文 bytes round-trip，并锁定非-wrapper capture 不被改写。
3. `dayu/cli/upload_script.py`：重写唯一 Windows token renderer 的 batch+CRT 编码，增加跨行/NUL fail-closed 校验；不改变 POSIX renderer 与 publisher。
4. `tests/cli/test_upload_filings_from_command.py`：用独立 batch decode + CRT oracle 覆盖 empty/space/中文/quote/backslash/percent/`!`/全部 cmd metacharacter，覆盖换行/NUL拒绝；强化真实 Windows fixed/appended 顺序及 marker assertion；增加 R11 workflow owner 静态 contract。
5. `.github/workflows/r11-upload-script-windows.yml`：增加 `dayu/cli/main.py` path trigger，改为精确 process probe。
6. `.github/workflows/r12-init-windows.yml`：增加公共 CLI stream owner 的 path trigger；不修改 `setx`/registry test 语义。
7. `tests/README.md`：按测试 README trigger 更新 R11 exact exit 与 CLI UTF-8 owner 证据说明。
8. 本文件：回填实际 changed paths、命令、结果、finding disposition 和 residual。

根 `README.md` 不计划修改：命令、参数、输出位置、工作区路径和用户工作流均未变化；本次是既有 Windows CLI 输出和既有 `.cmd` contract 的 correctness 修复。`dayu/README.md` 不计划修改：分层与装配边界未变化。

## 验证矩阵

- focused owner tests：CLI stream、Windows renderer oracle、workflow static contract、真实 POSIX renderer/CLI smoke。
- 受影响 CLI tests 与完整 `tests/cli`。
- 单文件 coverage：修改的 production Python 文件 `dayu/cli/main.py`、`dayu/cli/upload_script.py` 各自 line coverage `>=80%`。
- full Pyright：`python -m pyright dayu/ tests/ utils/`。
- changed Ruff、`git diff --check`。
- source/security/deferred scans：无 lazy import/`hasattr/getattr`/`list2cmdline`/`shell=True`/delayed expansion/JSON argv 协议；diff 无 secret value；deferred/control paths 无改动；README triggers 已裁决。
- 本地 POSIX/CLI smoke 不声明 Windows pass。WIN2-F01/F02/F03 最终 closure 必须由修改后 R11 与 R12 的真实 `windows-latest` rerun 证明；AgentCodex 不 dispatch workflow。

## 风险

- 本地不能运行真实 `cmd.exe`，独立语法 oracle 只能证明设计变换，不能替代 R11/R12 runner；真实 runner 是三项 finding 的最终关闭证据。
- Windows batch 有 cmd parser 与目标进程 CRT parser 两层语法；修复必须保持两层测试分离，不能用 production helper 自证。
- UTF-8 reconfigure 作用于 CLI 进程真实标准流；必须验证非 `TextIOWrapper` capture 保持原样，也不能把编码失败降级为静默替换。
- workflow 的 .NET process capture 必须在真实 pwsh runner 复核 help exact exit 1；本地只能做 YAML/source contract 检查。

## 实施结果

### WIN2-F01

- `dayu/cli/main.py` 在任何参数解析、usage/help、命令输出或日志装配之前，对当前 stdout/stderr 中具体的
  `io.TextIOWrapper` 调用 `reconfigure(encoding="utf-8", errors="strict")`。
- console script `dayu-cli = dayu.cli.main:main` 与 `python -m dayu.cli -> run_module() -> main()` 共用同一 owner。
- 没有改 init/upload 命令、测试环境、provider、locale 或 `PYTHONIOENCODING`；没有 catch 编码异常。真实 wrapper
  reconfigure 失败继续透传，`StringIO` 等非 wrapper capture 保持原样。
- owner test 从 `cp1252/strict` 的真实 `TextIOWrapper(BytesIO)` 出发，写入中文后断言底层 bytes 是严格 UTF-8；另有
  非-wrapper contract。`PYTHONIOENCODING=cp1252:strict python -m dayu.cli --help` 的本地 redirected-style smoke 成功输出中文。

Disposition：`LOCAL OWNER FIX VALIDATED / WINDOWS RERUN REQUIRED`。产品根因已在公共 CLI stream owner 修复；
init four-state、setx round-trip 与 upload real CLI 的 Windows closure 等待 R11/R12 rerun。

### WIN2-F02

- `dayu/cli/upload_script.py` 的唯一 Windows renderer 现在生成 caret-protected CRT quote；fixed token 内的 `%` doubling、
  `^&|<>()` caret protection、literal quote/backslash CRT 规则由同一算法完成。`DisableDelayedExpansion` 保持，`!` 不被二次展开。
- renderer 对 command 与 regeneration argv 的 NUL/CR/LF fail-closed，防止单行 executable body 或 `REM` 注释逃逸。
- direct command body、每条命令后的 raw `%*`、fixed-before-appended 顺序、CRLF/UTF-8、errorlevel gate 保持；没有
  `list2cmdline`、`shell=True`、fallback、JSON/base64 argv 公共协议或 publisher/CLI 下游补偿。
- 独立 test decoder 先模拟 batch percent/caret 解码，再用独立 CRT parser 恢复 argv；覆盖 empty、space、中文、
  literal quote、trailing backslash、literal percent、`!` 与全部 cmd metacharacter。真实 Windows node 也扩展到全部 fixed
  metacharacter，并在 argv equality 前先断言 injection marker 不存在。真实 POSIX sh round-trip 与 CLI/temp-storage smoke 均通过。

Disposition：`LOCAL OWNER FIX VALIDATED / WINDOWS RERUN REQUIRED`。本地证明 owner 变换、fail-closed 和 POSIX retained
semantics；真实 fixed/appended argv、cmd parse 与 marker absence 只能由 R11/R12 rerun 关闭。

### WIN2-F03

- R11 capability step 用 `System.Diagnostics.ProcessStartInfo/Process` 单次调用 `cmd.exe`，设置
  `UseShellExecute=false` 并分别 redirect stdout/stderr；异步读完两个流后保存 UTF-8 artifact 并返回精确 exit code。
- `ver` 必须 exact 0，help 必须 exact 1；二者都写入 names-only environment evidence。没有修改
  `$ErrorActionPreference`/`$PSNativeCommandUseErrorActionPreference`，没有 `continue-on-error`，后续 pytest/cmd execution gate 未弱化。
- R11/R12 path triggers 都补入公共 owner `dayu/cli/main.py`。workflow source contract 与 YAML parse 本地通过。

Disposition：`LOCAL WORKFLOW FIX VALIDATED / WINDOWS RERUN REQUIRED`。pwsh/.NET process 和真实 help exact exit 仍由 R11
rerun 关闭。

### 传播项与 no-code decisions

- R12 两个 `setx` failure：`PROPAGATED WIN2-F01 / NO REGISTRY CODE CHANGE`。第二轮证据显示它们在 CLI 中文输出处失败；
  cleanup、names-only evidence 和 registry owner contract未放宽，也没有留下 registry value。
- Gemini quota：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- secret scope：没有新增或修改 Config/Host/EventLog/Trace/audit/public/LLM/log key/header 语义；diff added-lines secret-value scan为零。
- deferred scope：Issue 142、151、175、177、178、Web/WeChat/render 与统一 authorization 均未实施。

## Actual changed paths 与冻结摘要

共 8 paths，全部保持 unstaged：

1. `.github/workflows/r11-upload-script-windows.yml`
2. `.github/workflows/r12-init-windows.yml`
3. `dayu/cli/main.py`
4. `dayu/cli/upload_script.py`
5. `tests/README.md`
6. `tests/cli/test_arg_parsing.py`
7. `tests/cli/test_upload_filings_from_command.py`
8. `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-codex.md`

七个 tracked paths 的 `git diff --binary` SHA-256：
`7058c07324a87b3959420f75c963705125ec50c4b6dad160e2bb466d55381e22`。

Tracked file content SHA-256：

| Path | SHA-256 |
|---|---|
| `.github/workflows/r11-upload-script-windows.yml` | `4c915a9c79efa5ee0166eb6fae44513ecc077b974217ca1e855e8b7ec4507f43` |
| `.github/workflows/r12-init-windows.yml` | `ba99b5a40c6d3116e1d83b05cd97139dcc62699722269b0aa6fc1a8d5ebea7b8` |
| `dayu/cli/main.py` | `127a7b13c3b8b7738f4b3ecfc9fef73383d8e7952bdef566a4449bafcf932509` |
| `dayu/cli/upload_script.py` | `a7b5868e748b3f71b38415f1471f9fed7080bc292110e458888b36e5a5a9daeb` |
| `tests/README.md` | `768b7500c616b0a43d53d0b91db73691e6249d98c43ed1302a2af003a2972eb2` |
| `tests/cli/test_arg_parsing.py` | `990d90328fb553e8122317abf08d6f6869a46b51eb1dd1448689de3aca1b7341` |
| `tests/cli/test_upload_filings_from_command.py` | `548843d329b5d6e8fa3c5aabc4653e9991c06013ec84969b15e2a5df12fc5e2a` |

## 验证结果

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| Gate | 结果 |
|---|---|
| 新增 stream/renderer/line rejection/POSIX focused nodes | `7 passed` |
| `test_arg_parsing.py + test_upload_filings_from_command.py` | `87 passed, 2 Windows-only skipped` |
| 两 owner 文件 coverage run | `87 passed, 2 skipped`；`dayu/cli/main.py 94%`，`dayu/cli/upload_script.py 92%` |
| 完整 `pytest tests/cli -q` | `519 passed, 7 skipped` |
| 明确 POSIX/module CLI smoke 3 nodes | `3 passed` |
| `PYTHONIOENCODING=cp1252:strict python -m dayu.cli --help` 中文 oracle | exit `0` |
| full Pyright `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| changed Ruff 4 Python paths | `All checks passed!` |
| R11/R12 workflow YAML parse | PASS |
| `git diff --check` | PASS |
| staged manifest | empty |
| source/security/deferred/no-touch scans | PASS；零未分类命中 |

pytest 仅报告既有 `edgar` deprecated import warnings；无本任务 failure。source scan 明确排除
`hasattr/getattr`、lazy/importlib、`list2cmdline`、`shell=True`、`EnableDelayedExpansion`、JSON/base64 argv 协议；workflow
无全局 native-error ignore。control doc、controller discussion、Config/Engine/Fins/Host/Runtime/Service/Tools 与 deferred UI paths diff均为零。

README trigger 已核对：修改 tests 后按 `tests/README.md` 职责更新 Windows gate/CLI stream 说明；根 README 面向最终用户的
命令、参数、路径、输出和工作流未变化，故 no-diff；无分层/装配变化，`dayu/README.md` no-diff。

## Residual 与 Windows rerun closure matrix

本地没有发现新的 design truth conflict 或 owner drift；不存在继续本地修复的 accepted finding。以下 residual 不能被 macOS 伪造：

1. 修复被 Controller 接受并形成新 head 后，R11 rerun 必须证明 `cmd_ver_exit_code=0`、
   `cmd_help_exit_code=1`，且 help probe 后继续执行 pytest；recorder fixed/appended argv exact equality、marker absent、real CLI storage全部通过。
2. R12 rerun 必须证明 init 9 nodes 通过（普通 symlink 仅允许按既有精确 privilege contract skip），尤其 four-state/config reload
   与真实 setx round-trip 不再出现 charmap error；内嵌 R11 两个 nodes 通过。
3. artifacts 继续只含 JUnit、生成脚本/oracle、版本、capability、source hash 和环境变量名；不得含 secret/registry value。

在两条真实 `windows-latest` rerun evidence 到位前，三项 finding 只能标记
`LOCAL_FIX_VALIDATED / WINDOWS_RERUN_REQUIRED`，不能声明 Windows pass 或 AR-F07 gate closed。AgentCodex 未 dispatch workflow，
未 stage/commit/push、未修改 PR/control doc。
