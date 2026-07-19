# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第三轮 Windows finding fix（AgentCodex）

## Gate、状态与边界

- gate：第三轮真实 Windows evidence accepted finding `WIN3-F01` implementation/fix；这是同一
  `WU-SEMANTIC-OWNERSHIP-01` umbrella、同一 `AR-F07` remediation continuation，不是新 WU。
- baseline / HEAD：`4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`；branch：
  `phaseflow/host-issues-control`。
- 状态：`LOCAL_FIX_VALIDATED / WINDOWS_RERUN_REQUIRED`。本地实现和门禁已通过，但本机不能把
  Windows-only skip 当作真实 Windows 通过，`WIN3-F01` 和 AR-F07 均不能在本 artifact 中关闭。
- 未 stage、commit、push，未修改 PR，未 dispatch workflow；未修改产品编码、workflow、registry/junction
  命令、provider/config/Host/EventLog 或 deferred scope。
- Controller 已有改动保持原样：
  - `docs/host/issues-implementation-control.md` 当前内容 SHA-256
    `ef567e33df3cc68c6428271f66897d44c1478344fb77a64e13d21c08a7185516`；
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-evidence-controller-adjudication.md`
    当前内容 SHA-256
    `7ae06070fb37f2660f043ec8ed9f14d86555035b93a7ae4a21380130ea0e065d`。

## 第一性原理判断与直接证据

修复动机成立，并且严重性是 release-gate blocking，而不是产品输出或 registry 新缺陷：一个明确输出
UTF-8 bytes 的进程若被 `subprocess` text consumer 按 ambient cp1252 解码，reader thread 会在合法 UTF-8
字节处失败；此后 `CompletedProcess.stdout/stderr` 可以成为 `None`，pipe drain 也会失去可靠性。继续改产品、
增加 `PYTHONIOENCODING` 或 loose fallback 都会把 consumer 的错误所有权转移到 producer 或全局环境。

下载证据的关键真源与 SHA-256：

| Evidence path | SHA-256 | 直接事实 |
|---|---|---|
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r11-29694082161/r11-windows-upload-script-29694082161/pytest-stdout.txt` | `f534d03cd8f32d60bc3ce57dc5360482f60f1b2c651cce7f10a4de5b329932ae` | 两个 reader thread 在 `encodings/cp1252.py` 抛 `UnicodeDecodeError`，execution stderr 为 `None` |
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r11-29694082161/r11-windows-upload-script-29694082161/pytest-junit.xml` | `789025856c2a61d7dc1af01e710ea55978aecd66568802de231821a27410ea06` | R11 为 `3 passed / 1 failed`；真实 batch/CRT argv node 已通过，CLI storage consumer 失败 |
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r12-29694082143/r12-init-windows-29694082143/init-pytest-junit.xml` | `fa18bc36994f371b932624f7c4cbd21d3dccd7bd938da439b2e8982cd16a693a` | four-state 首个 CLI return code 为 0 但 stdout 为 `None`；setx 在同一 `_run_init` consumer timeout |
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r12-29694082143/r12-init-windows-29694082143/r11-pytest-junit.xml` | `3339b5f670779a24c5f79172a9a1d9121c9042469d9c114935412c01910026d8` | 内嵌 R11 的 argv node 通过、CLI storage consumer 失败 |
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r11-29694082161/r11-windows-upload-script-29694082161/environment.txt` | `5541e756dd75df6bbc5f15fd3332b13d2ec3b4e04d70507305a39ace09e16012` | `cmd_ver_exit_code=0`、`cmd_help_exit_code=1` |
| `workspace/tmp/wu-semantic-ownership-01-ar-f07-r12-29694082143/r12-init-windows-29694082143/source-hashes.json` | `6ce43e201ea41f5c5e9e637a6972fbd3d991279ee941dee4ef403b44d72f6fa3` | 远端 source lock |

两组 evidence 还证明产品进程不再发生 `UnicodeEncodeError`；R11 与 R12 的真实 recorder oracle 均精确
恢复 fixed/appended argv。因此 WIN2-F01/F02/F03 的正向证据保留，当前只修 consumer decode finding。

## 唯一语义 owner 与修复

### Owner

唯一 owner 是捕获 Dayu CLI stdout/stderr 的测试 `subprocess` direct-consumer boundary。Dayu CLI process owner
已经明确产生 UTF-8/strict bytes；每个实际打开 text pipe 的直接 consumer 必须用
`encoding="utf-8", errors="strict"` 解码。这里不抽象通用 subprocess helper，因为调用点少、命令职责不同，
额外框架会隐藏协议并扩大变更面。

### 精确 consumer audit

| Path / consumer | 处置 |
|---|---|
| `tests/cli/test_init_smoke.py::_run_init` | 显式 strict UTF-8；覆盖 four-state、setx 和其它 init real smoke |
| `tests/cli/test_init_smoke.py::_start_init_process` | 显式 strict UTF-8；覆盖 waiting notification 的长运行 `Popen` reader |
| `tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage` generation / execution | 两个 direct consumers 均显式 strict UTF-8 |
| `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` generation / execution | 两个 WIN3-F01 direct consumers 均显式 strict UTF-8 |
| `tests/cli/test_arg_parsing.py::test_python_module_help_decodes_cli_output_as_strict_utf8` | 模块入口 direct consumer 显式 strict UTF-8，并断言中文 help 文本，形成本地 owner-level contract |
| POSIX/Windows recorder、prewarm `python -c`、junction `cmd.exe`、`reg.exe` | 不消费 Dayu CLI 输出；保持原编码行为，无 diff |

共修复 7 个 direct-consumer 调用点。没有 `cp1252`、`errors=ignore/replace`、fallback、
`PYTHONIOENCODING`、全局 locale/environment shim 或通用 subprocess framework。

## 精确 changed paths 与 hash

本 gate 的 implementation scope 是下列 5 个 paths；前 4 个 tracked paths 相对 HEAD 的 canonical
`git diff --binary` SHA-256 为
`9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`。

| Path | SHA-256 / 状态 |
|---|---|
| `tests/README.md` | `504b7c1ff84ed15e1f64a50decbad60841336d46a99662aadaabc45b1566af4b` |
| `tests/cli/test_arg_parsing.py` | `89f355d9959f456975036935871aa22b337636c081fc3c832c289e543025ea6c` |
| `tests/cli/test_init_smoke.py` | `565b108b6a6796ee0393d9f472cb83a3eb287f7af1c465d8d9e99cf51c4e5f56` |
| `tests/cli/test_upload_filings_from_command.py` | `7c105d40f3a16e92fd4a4f95f7df69337b5d642aeca48a68e2c52a53f1e3b649` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md` | 本 implementation artifact；self-hash 不能无递归地内嵌，由 Controller 在下一 gate 外部锁定 |

`git diff --numstat` 对前四个 paths 分别为 `3/1`、`6/3`、`4/0`、`8/0`。没有产品、workflow、
根 README、分层 README 或 deferred path diff。

## 验证

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| Gate | Result |
|---|---|
| 三个受影响 test files | `98 passed, 7 skipped, 3 warnings in 28.50s`；7 个 skip 均为本机 Windows-only |
| owner coverage run | `87 passed, 2 skipped`；`dayu/cli/main.py 94%`、`dayu/cli/upload_script.py 92%`，两文件均 `>=80%` |
| 本地 R11 精确选择 | `2 passed, 2 skipped`；两个真实 Windows cmd/upload nodes 明确 skip |
| 本地 R12 init 精确选择 | `4 passed, 5 skipped`；五个真实 Windows nodes 明确 skip |
| 本地 R12 内嵌 R11 精确选择 | `2 skipped` |
| full Pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| `git diff --check` / cached diff-check | PASS / PASS；staged set empty |
| prohibited consumer shim scan | `PROHIBITED_PYTHON_DIFF_HITS=0` |
| configured secret diff scan | `CONFIGURED_SECRET_DIFF_HITS=0`；只输出计数，不输出值 |
| production/workflow/deferred path scan | zero diff |

pytest 只报告既有 `edgar` deprecation warnings。受影响测试已覆盖所有修改的 Python test files；未运行或宣称
真实 Windows pass。

## README、安全与 deferred 裁决

- 修改 `tests/` 触发 `tests/README.md`；已在其测试职责内记录 direct consumer 的 strict UTF-8 解码契约，
  同时明确纯 recorder、registry 与 junction native 命令不共享该契约。
- 根 `README.md` 无需更新：用户可见命令、参数、输出通道、路径和工作流均未变化。
- `dayu/README.md` 及其它产品 README 无需更新：没有分层、装配或产品模块变更。
- Config / Host internal SQLite / EventLog trusted-local 与 Tool Trace / audit / public / LLM / log / output
  secret-zero 裁决不变；diff 没有 configured secret value。
- Issue 142、151、175、177、178、Web/WeChat/render、统一 authorization 与 Gemini provider 配置均无 diff。

## Finding disposition 与真实 Windows residual

- `WIN3-F01`：`LOCAL FIX VALIDATED / WINDOWS RERUN REQUIRED`。代码层 root cause 已在唯一 consumer owner
  修复；在第四轮真实 Windows evidence 到达前保持 accepted-open，不提前关闭。
- `WIN2-F01/F02/F03`：第三轮已有 positive evidence，继续保持
  `EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。
- 第四轮 R11 必须在真实 `windows-latest` 上证明完整 `4/4`，且 artifact 仍包含 exact capability、argv、
  marker absence、CLI storage 和双流可读证据。
- 第四轮 R12 必须证明 init `9/9`、内嵌 R11 `2/2`，不再出现 reader decode exception、`stdout=None`
  或 setx timeout；artifact 继续只能保存环境变量名，不得保存 registry/API key/header value。
- 上述 residual 的 owner 是后续已授权的真实 Windows rerun/Controller evidence adjudication；它不要求新的代码
  fallback 或新 issue。当前没有未分类 residual risk。

结论：`PASS_LOCAL_IMPLEMENTATION / READY_FOR_CONTROLLER_VALIDATION / WINDOWS_RERUN_REQUIRED`。
