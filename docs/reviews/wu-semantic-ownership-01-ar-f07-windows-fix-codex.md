# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows Validation Fix

## Gate 与范围

- Work unit：现有 `WU-SEMANTIC-OWNERSHIP-01` umbrella 的 AR-F07 validation-fix gate。
- Draft PR：#179。
- 基线 HEAD：`07db7af3855b7fc80a24d74a3214bef215752d8d`。
- Agent：AgentCodex。
- 风险级别：`production-high`。本轮同时涉及 CLI 跨平台加载、workspace transaction durability、
  Windows 环境清理测试真值与 GitHub Actions release gate。
- 授权边界：只修改本 artifact、四个 finding 的唯一 owner、owner contract tests、对应 Windows
  workflows 与 `tests/README.md`；不修改 control doc，不 stage、commit、push、修改 PR 或触发 workflow。

本轮不是新 WU，也不创建替代 WU。四项 finding 都会在同一 AR-F07 follow-up 中修复；由于它们分别属于
按键平台能力、workflow capability probe、Windows test environment cleanup 和 init transaction durability
四个独立 owner，不把其中任何语义下沉到 CLI entrypoint、测试 shim 或下游异常捕获。

## 目标、成功信号与非目标

目标：关闭 Controller 已接受的 `AR-F07-WIN-F01` 至 `AR-F07-WIN-F04`，使 Windows CLI import、
R11 cmd 能力验证、真实 `setx` round-trip cleanup 和 init staging durability 各自在唯一 owner 处符合契约。

成功信号：

1. 非 POSIX 进程可以 import `dayu.cli`；运行态按键 factory 在非 POSIX TTY 上明确返回 no-op monitor。
2. R11 workflow 用 exit 0 的真实 `cmd.exe` 命令证明 cmd execution capability；help artifact 不再被错误地
   当作成功命令，且不会用任意错误忽略来弱化 gate。
3. Windows registry cleanup 以“目标 value 已不存在”为最终真值；value 原本不存在时保持幂等，value 仍存在
   或出现未分类退出码时失败，错误文本只含变量名，不含 secret value。
4. Windows init staging 对普通文件完成真实 flush，不在 publication fault injection 之前以 `EBADF` 失败；
   POSIX no-follow file sync、whole-tree staging、backup/swap/rollback、containment、symlink/reparse fail-closed
   与 cleanup truth 保持不变。
5. macOS 可执行验证全部通过；真实 Windows pass 只由后续 R12/R11 rerun 与下载 artifact 关闭，不在本地伪造。

非目标：

- 不修改 Gemini/provider/model/key/retry/quota/budget。
- 不实施 Issue #142、#151、#175、#177、#178 或 Web/WeChat/render deferred 能力。
- 不引入统一 tool authorization framework。
- 不改变 init 四态、secret 存储位置、upload batch 业务/脚本 grammar 或 Fins storage。
- 不增加 lazy import、`hasattr/getattr`、下游 catch、测试专用生产分支或兼容 shim。

## Windows 证据与第一性原理判断

### Evidence set

- R12 run `29690620412`、job `88202555076`、head SHA `07db7af3`：
  `workspace/tmp/wu-semantic-ownership-01-r12-run-29690620412/`。
- R11 run `29690620419`、job `88202555102`、head SHA `07db7af3`：
  `workspace/tmp/wu-semantic-ownership-01-r11-run-29690620419/`。
- R12 `init-pytest-junit.xml`：8 tests 中 5 failures；前三个 init subprocess failure 和 `setx`
  主 failure 都直接包含 `dayu/cli/run_keys.py:14 -> ModuleNotFoundError: termios`。
- R12 `r11-pytest-junit.xml`：test collection 经 `dayu.cli.main -> session_execution -> run_keys`
  同样因 `termios` 失败。
- R11 `cmd-help.txt`：`cmd.exe /?` 已完整输出帮助；workflow 仍因真实 exit code 1 失败，证明“有帮助输出”
  与“exit 0 capability probe”不是同一事实。
- R12 publication failure stack：fault object 尚未构造/安装；第一次
  `prepare_workspace_transaction(FIRST)` 在 `_sync_staged_config -> os.fsync(O_RDONLY fd)` 抛
  `OSError: [Errno 9] Bad file descriptor`，因此不是 monkeypatch 误伤。

### 动机判断

四项 finding 严重性成立。F01 阻断所有依赖 `dayu.cli.main` 的 Windows entrypoint 与测试 collection；F02 让
可用的真实 cmd runner 被错误 probe 判失败；F03 会用 cleanup 二次错误覆盖原始 failure，无法证明 registry
污染状态；F04 使正常 Windows transaction 无法到达 publication/rollback contract。它们都是 AR-F07 release
blocker，不是可延期的测试噪声。

## Root cause 与 semantic owner

### AR-F07-WIN-F01 — PRODUCT

- Root cause：`dayu/cli/run_keys.py` 在模块加载时无条件 import `termios` 与 `tty`。TTY 检查发生在 import
  之后，因此 Windows/non-POSIX 没有机会进入已有 no-op policy。
- Owner：`dayu.cli.run_keys` 的平台 capability/factory boundary。
- 修复决策：平台能力在模块加载时静态确定；只在 POSIX 导入 POSIX terminal modules。factory 先判断平台
  capability，再判断 `stdin.isatty()`；非 POSIX 无条件产生 `NoopRunningKeyMonitor`。`TtyRunningKeyMonitor`
  自身也在 start/restore 边界 fail closed 为 no-op，避免调用者绕过 factory 后访问未提供的 POSIX capability。

### AR-F07-WIN-F02 — WORKFLOW

- Root cause：`.github/workflows/r11-upload-script-windows.yml` 把 `cmd.exe /?` 的 help-display 退出语义当作
  “cmd 可成功执行”的语义。真实 runner 返回 1，但输出证明 cmd 本身存在且工作。
- Owner：R11 workflow 的 Windows cmd capability probe。
- 修复决策：用 `cmd.exe /d /c ver` 作为真实、无副作用、稳定 exit 0 gate，并保存输出。继续保存 help artifact，
  但显式只接受已知 0/1 help exit classification，任何其它退出码仍失败；禁止 `continue-on-error`、`|| true`
  或吞掉 pytest/cmd execution failure。

### AR-F07-WIN-F03 — TEST / ENV OWNER

- Root cause：F01 使 init 在 `setx` 前失败；`finally` 随后对不存在的 `OPENAI_API_KEY` 执行 `reg delete`。
  `reg delete` 对 missing value 返回非零，测试错误地把命令 return code 当作最终 registry state，产生
  `registry cleanup failed` 并覆盖原始 failure。
- Owner：`tests/cli/test_init_smoke.py` 的真实 Windows registry setup/cleanup helper。
- 修复决策：抽取 name-only helper，delete 后用精确 value query 验证 absent；delete 的 0（实际删除）与 1
  （目标可能已不存在）均必须继续接受 state verification，其他退出码失败。精确 value query 返回 1 后，
  还必须用父 key query 返回 0 证明 key 可访问，避免把访问失败误当 absent；所有自定义错误只投影变量名。
  setup 与 finally 复用同一 helper。

### AR-F07-WIN-F04 — PRODUCT / TRANSACTION OWNER

- Root cause：`_sync_staged_config` 对所有平台都以 `os.O_RDONLY` 打开 staging regular files 后 `os.fsync`。
  Windows Python 3.11 runner 对该 descriptor 执行 flush 返回 `EBADF`。失败发生在 fault injection 之前；
  `_ReplaceFault` 的 boundary matching 不是根因。
- Owner：`dayu.cli.init_workspace._sync_staged_config` 的 staged-file durability contract。
- 修复决策：由模块级私有 helper 唯一选择 file sync open flags：Windows 使用 `os.O_RDWR` 获得可 flush
  descriptor；POSIX 保持 `os.O_RDONLY | os.O_NOFOLLOW`。继续在打开后 `fstat` 验证 regular file，随后
  `fsync`/close；不触碰 rename、backup、rollback、identity、containment 或 cleanup state machine。

## 精确 implementation plan

### Slice VF1 — platform capability 与 workflow gate

Allowed paths：

- `dayu/cli/run_keys.py`
- `tests/cli/test_run_keys.py`
- `.github/workflows/r11-upload-script-windows.yml`
- `.github/workflows/r12-init-windows.yml`

动作：

1. 将 POSIX terminal imports 置于 module-load platform branch；新增明确 capability constant。
2. factory 与 TTY implementation 在 capability boundary 返回 no-op/不启动；保留 Ctrl+T/Esc 与 POSIX
   terminal restore 语义。
3. 让 `test_run_keys.py` 在非 POSIX 可 collection：平台无关测试始终执行，PTY/termios tests 只在 POSIX
   导入并运行；新增“报告为 TTY 的非 POSIX 输入仍返回 no-op”owner test。
4. 两条 workflow 的 path filter 纳入 `run_keys.py`/owner test；Windows test matrix显式执行 non-POSIX
   no-op owner node。
5. R11 用 `cmd.exe /d /c ver` gate 并保存 `cmd-version.txt`；help artifact 记录真实 exit classification，
   不再要求 help exit 0，也不忽略未分类错误。

Completion signal：本地 run-keys tests 通过；workflow 文本不存在 `cmd.exe /?` exit-0 断言或错误吞并；
Windows rerun 能越过 CLI import/collection。

### Slice VF2 — registry cleanup truth 与 staged-file durability

Allowed paths：

- `tests/cli/test_init_smoke.py`
- `dayu/cli/init_workspace.py`
- `tests/cli/test_init_workspace.py`

动作：

1. 新增 registry value name-only 删除/absence verification helper；setup/finally 复用。
2. 测试 helper contract 覆盖 delete=0/value-query=1/key-query=0、delete=1/value-query=1/key-query=0、
   unexpected delete code、value-query=0（value 仍在）、unexpected value-query code 和父 key 不可访问；
   不把 subprocess stdout/stderr/secret 加进失败信息。
3. 新增 staged-file sync flags 私有 helper；Windows 返回 `O_RDWR`，Darwin/Linux 返回
   `O_RDONLY|O_NOFOLLOW`，非法平台沿现有 validation fail closed。
4. owner test 断言 Windows/POSIX exact flags；保留已有 publication rollback test 作为真实 transaction
   contract，等待 Windows rerun验证真实 flush。

Completion signal：macOS owner tests 与完整相关 init tests 通过；生产 diff 不改变 transaction
state transitions；Windows rerun 到达并通过 publication fault/rollback node。

### Slice VF3 — docs/evidence closure

Allowed paths：

- `tests/README.md`
- `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md`

动作：

1. 更新 tests README 的 R11 artifact 与 Windows gate说明，使其匹配 `ver` capability evidence、help exit
   classification、non-POSIX key owner node 和 idempotent registry cleanup truth。
2. README trigger audit：根 README、`dayu/config/README.md`、`dayu/fins/README.md`、`dayu/README.md`
   的用户工作流/配置/Fins/分层 contract 均未变化，不做机械更新。
3. 在本 artifact 回写 exact changed paths、命令/结果、finding disposition 与 residual。

本方案没有引入新抽象框架：只在四个现有 owner boundary 修正平台事实、durability flags 与测试/workflow
oracle；不改变业务 schema、公共 CLI grammar、Host/Engine/Fins contract 或 deferred capability。

## Planned changed paths

1. `dayu/cli/run_keys.py`
2. `tests/cli/test_run_keys.py`
3. `.github/workflows/r11-upload-script-windows.yml`
4. `.github/workflows/r12-init-windows.yml`
5. `tests/cli/test_init_smoke.py`
6. `dayu/cli/init_workspace.py`
7. `tests/cli/test_init_workspace.py`
8. `tests/README.md`
9. `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md`

任何额外 path 必须先在本 artifact 说明 owner 原因；禁止修改
`docs/host/issues-implementation-control.md` 或其它 control doc。

## 验证矩阵

所有 Python 命令先执行 `source .venv/bin/activate`。

### Focused owner tests

```bash
pytest tests/cli/test_run_keys.py -q
pytest tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py -q
pytest tests/cli/test_upload_filings_from_command.py tests/cli/test_arg_parsing.py -q
```

预期：macOS 可执行 nodes 全通过；Windows-only nodes 明确 skip，不能用于声称 Windows pass。

### 相关 CLI tests

```bash
pytest tests/cli -q
```

预期：无新增 failure；若命中 baseline failure，必须以基线 commit/既有 artifact 直接归因，不得模糊归类。

### 单文件覆盖率

```bash
pytest tests/cli/test_run_keys.py --cov=dayu.cli.run_keys --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q
```

预期：两个修改生产文件均不低于 80%。`test_init_smoke.py` 是真实 subprocess/platform smoke owner，
不作为生产模块覆盖率 owner。

### 类型、lint、diff 与边界扫描

```bash
python -m pyright dayu/ tests/ utils/
python -m ruff check \
  dayu/cli/run_keys.py dayu/cli/init_workspace.py \
  tests/cli/test_run_keys.py tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py
git diff --check
git diff --name-only
git diff --cached --name-only
rg -n "hasattr|getattr|continue-on-error|cmd\.exe /\? failed with exit code" \
  dayu/cli/run_keys.py dayu/cli/init_workspace.py \
  .github/workflows/r11-upload-script-windows.yml \
  tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py
```

预期：pyright 0 error；scoped Ruff 0；diff check pass；staged path 为空；禁止模式无新增命中。

### 必须由真实 Windows rerun 关闭

本地完成后仍保留一个分类明确的 external validation residual：以修复后的 head 重新运行 R12 与 R11
Windows workflows，下载并核验 artifacts。至少必须证明：

- R12 init 8 个锁定 nodes 通过（或普通 symlink 仅按精确 privilege contract skip）。
- R12 的 R11 两个 cmd/upload nodes 通过，无 collection error。
- R11 cmd `ver` capability gate exit 0；help exit 被显式记录；真实 recorder/CLI storage gates 通过。
- JUnit 不再包含 `ModuleNotFoundError: termios`、registry cleanup false failure 或
  `staging_validation -> EBADF`。

在这些 rerun evidence 到位前，本 artifact 只能报告 `LOCAL_FIX_VALIDATED / WINDOWS_RERUN_REQUIRED`，
不得报告 AR-F07 closed 或 Windows pass。

## Findings disposition（实施前）

| Finding | Decision | 当前状态 |
|---|---|---|
| AR-F07-WIN-F01 | accepted；修平台 capability owner | 已修复；真实 Windows import/collection 待 rerun |
| AR-F07-WIN-F02 | accepted；修 workflow cmd probe owner | 已修复；真实 cmd gate 待 rerun |
| AR-F07-WIN-F03 | accepted；修 test registry cleanup owner | 已修复；真实 registry round-trip 待 rerun |
| AR-F07-WIN-F04 | accepted；修 transaction durability owner | 已修复；真实 Windows flush/rollback 待 rerun |

## 实施与验证结果

### 实施结果

#### F01

- `dayu/cli/run_keys.py` 只在 `os.name == "posix"` 的 module-load branch 导入 `termios/tty`；没有
  function-local lazy import。
- `new_running_key_monitor` 在任何 stdin/TTY 判断前消费唯一平台 capability，非 POSIX 固定返回
  `NoopRunningKeyMonitor`；直接构造 TTY monitor 时，`start` 和 terminal restore 同样先消费该 capability。
- `tests/cli/test_run_keys.py` 可在非 POSIX collection；PTY/termios owner tests 只在 POSIX import/run，
  新增“reported TTY + non-POSIX => no-op”contract。R11/R12 workflow 都显式运行该 node 并把相关
  source/test 纳入 path filter/hash evidence。

Disposition：`AR-F07-WIN-F01 = 已修复`。本地证明 owner 行为和 POSIX 回归；真实 Windows import、CLI
entrypoint 与 test collection 仍由 rerun 证明。

#### F02

- R11 workflow 用 `cmd.exe /d /c ver` 的 exit 0 作为真实 cmd execution gate，并产出
  `cmd-version.txt`。
- `cmd.exe /?` 继续产出 `cmd-help.txt`；真实 help exit 写入 `environment.txt`，只接受已知 0/1
  classification，其他值仍使 workflow 失败。没有 `continue-on-error`、任意错误忽略或 pytest gate 弱化。

Disposition：`AR-F07-WIN-F02 = 已修复`。YAML 可解析且文本边界通过本地检查；真实 PowerShell/cmd
execution 仍由 R11 rerun 证明。

#### F03

- Windows smoke 的 setup/finally 统一调用 `_delete_registry_value_and_verify_absent`。
- Owner 先分类 `reg delete` 0/1，再要求精确 value query=1，最后要求父 key query=0；因此 missing value
  是幂等 success，而 access failure、未分类命令码或 value 仍存在全部 fail closed。
- Strict scripted runner matrix 覆盖 delete 0/1、value still present、delete/query 未分类、父 key 不可访问，
  并用带 `test-secret-*` 的 captured output 证明自定义错误只包含变量名。

Disposition：`AR-F07-WIN-F03 = 已修复`。本地 deterministic owner matrix 通过；真实 `setx` 写入、query、
delete 与 rerun 后 registry 无污染仍由 R12 Windows node 证明。

#### F04

- `_staged_file_sync_open_flags` 成为 staged regular-file durability flag 的唯一 owner：Windows 返回
  `os.O_RDWR`，Darwin/Linux 返回 `os.O_RDONLY | os.O_NOFOLLOW`，未知平台沿现有 typed error fail closed。
- `_sync_staged_config` 继续执行 ordinary-tree validation、`os.open -> fstat regular -> fsync -> close`；
  publication `os.replace`、backup、rollback、identity、containment、symlink/reparse 与 cleanup 路径零改动。
- Owner contract test 固定 Windows/POSIX exact flags；原 publication replace failure/rollback test 在 macOS
  继续通过，真实 Windows node 必须证明修复后的 writable descriptor 能越过 staging 并命中预期 publication fault。

Disposition：`AR-F07-WIN-F04 = 已修复`。原“monkeypatch 误伤”候选由 XML call order 与本次 owner fix
证伪；真实 Windows transaction evidence 待 rerun。

### Exact changed paths

1. `.github/workflows/r11-upload-script-windows.yml`
2. `.github/workflows/r12-init-windows.yml`
3. `dayu/cli/init_workspace.py`
4. `dayu/cli/run_keys.py`
5. `tests/README.md`
6. `tests/cli/test_init_smoke.py`
7. `tests/cli/test_init_workspace.py`
8. `tests/cli/test_run_keys.py`
9. `docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md`

没有修改 `docs/host/issues-implementation-control.md` 或其它 control doc；没有修改 provider/model/key/
retry/quota/budget、Fins business owner、Web/WeChat/render、Issue #142/#151/#175/#177/#178 或 tool authorization。

### 验证命令与结果

全部命令在 `source .venv/bin/activate` 后执行。

| 验证 | 结果 |
|---|---|
| `pytest tests/cli/test_run_keys.py -q` | `7 passed` |
| `pytest tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py -q` | `102 passed, 5 skipped`；5 个为 macOS 不可执行的 Windows nodes |
| `pytest tests/cli/test_upload_filings_from_command.py tests/cli/test_arg_parsing.py -q` | `81 passed, 2 skipped`；2 个为 Windows cmd nodes |
| F03 deterministic cleanup matrix | `6 passed` |
| 本地 R11 workflow exact node mirror | `2 passed, 2 skipped`；non-POSIX owner/argparse pass，真实 cmd nodes skip |
| 本地 R12 workflow exact node mirror | `4 passed, 5 skipped`；平台无关 owner/rollback pass，真实 Windows nodes skip |
| `pytest tests/cli -q` | `513 passed, 7 skipped` |
| run-keys 单文件覆盖率 | `88.73%`（`--cov-fail-under=80` pass） |
| init-workspace 单文件覆盖率 | `87.27%`（`--cov-fail-under=80` pass） |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（5 个修改 Python files） | `All checks passed!` |
| 两个 workflow PyYAML parse | `yaml-ok` |
| `git diff --check` | pass |
| `git diff --cached --name-only` | empty；全部修改保持 unstaged |
| 禁止边界检查 | 无 `hasattr/getattr` 调用、lazy import、downstream catch、`continue-on-error` 或旧 help-exit-0 断言新增 |

现有三条 `edgar` deprecation warnings 在 focused/CLI tests 中保持非阻塞；本次变更不触及其 owner。

### README trigger 决策

- `tests/` 与 workflows 改动命中 `tests/README.md`，已同步 cmd execution/help evidence、non-POSIX no-op
  owner node 和 idempotent registry cleanup truth。
- 根 `README.md`：现有用户工作流和 Windows 支持承诺未变化，本修复只让实现符合已写 contract；不更新。
- `dayu/config/README.md`：init 四态、secret owner、transaction contract 未变化；不更新。
- `dayu/fins/README.md`：upload batch/Fins 语义未变化；不更新。
- `dayu/README.md`：分层与装配边界未变化；不更新。

## Residual risk

- `requiring external-state change`：真实 Windows rerun 及新 artifacts 尚未执行；用户明确禁止本 Agent 触发
  workflow，因此只能由 Controller/获授权操作者关闭。该 residual 是 AR-F07 release gate，不得 waiver。
- `fixed in current slice`：F01 的 Windows import root cause、F02 的 cmd probe owner、F03 的 cleanup truth 和
  F04 的 writable flush descriptor contract 均已在唯一 owner 与 owner tests 中修复。
- `no current residual`：Gemini/provider/model/key/retry/quota/budget 及 deferred issue 均未触碰；没有因本修复
  新增或重新分类其状态。

## Stop status

`LOCAL_FIX_VALIDATED / WINDOWS_RERUN_REQUIRED`。

下一入口不是新 WU：由获授权 Controller/操作者在修复后的同一 PR head 上 rerun R12/R11 Windows workflows，
下载并核验新的 JUnit/cmd/registry/transaction artifacts。只有这些 evidence 通过后，AR-F07 才可关闭并继续
PR #179 的既有 gate；本 Agent 未触发 workflow，也未 stage/commit/push/修改 PR。
