# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 Implementation Evidence（AgentCodex）

## 1. Gate identity and result

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4-RW-S2`；不是新 WU。
- Gate：corrected accepted plan 后恢复的同一 `WIN4-RW-S2 implementation`。
- Accepted corrected-plan commit：`23321e7573f3dba8e6a20eb1bdf70ca03ba367b1`。
- Controller authorization HEAD / implementation entry：
  `bbb10959253fb3cb4bd22299196cf65a4a961b10`。
- Branch：`phaseflow/host-issues-control`；不是 protected trunk。
- Accepted final plan：
  `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，SHA-256
  `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`。
- Gate result：
  `IMPLEMENTED / LOCAL_VALIDATION_PASS / REAL_WINDOWS_PENDING / STOPPED_AT_S2_IMPLEMENTATION`。
- 本轮没有 stage、commit、push、workflow dispatch、PR 操作或 reviewer dispatch。

## 2. First-principles and semantic-owner judgment

修复动机成立，但严重性仍限定为 direct integration test propagation 缺口，不是新的 production defect。
`dayu.cli.commands.init::_read_secret_input()` 已在正确 owner boundary 依据当前 `sys.stdin.isatty()` 选择 TTY hidden
getpass 或 redirected logical-line input。此前 full CLI 唯一失败的直接原因是
`test_prompt_command_uses_init_generated_workspace_config` mock 了 getpass value sequence，却没有给 production 实际读取的
stdin 声明 TTY capability；pytest capture stdin 因 `isatty() == False` 正确进入 redirected owner path。

因此唯一正确的本轮修改 owner 是该 direct test consumer 的 caller-owned stdin fixture。让 production 识别 pytest、mock、
capture stream，或在 redirected read 失败后 fallback 到 getpass，都会把测试身份泄漏进产品语义并形成 compatibility shim；
本轮没有采用这些路径，也没有修改 production owner。

## 3. Protected payload and exact implementation

进入本轮前已有四路径 payload 被原样保留，没有重做、回滚、格式化或覆盖：

| Protected path | Final SHA-256 |
| --- | --- |
| `README.md` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` |
| `dayu/cli/commands/init.py` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` |
| `tests/README.md` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` |
| `tests/cli/test_init_command.py` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` |

四路径完整 worktree diff SHA-256 仍精确为：
`e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669`。

本轮 product/test 新增修改只涉及
`tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 的 fixture 迁移：

1. 增加必要最小被测模块 import `dayu.cli.commands.init as init_command`；
2. 增加只服务该 node 的模块级私有 `_TtySecretInput(io.StringIO)`；其 `isatty()` 恒为 `True`，任何
   `readline()` 调用立即抛 `AssertionError`；
3. 在 exact node 内把 production 实际读取的 `init_command.sys.stdin` 设为该 caller-owned fake；
4. 既有 getpass value sequence `("", "", "", "", "")`、model input sequence、generated workspace config、
   prompt/runtime assembly、db path 与 nested-workspace 断言全部未修改；
5. 同文件其它 test nodes 函数体零 diff，没有抽 shared helper，也没有从
   `tests/cli/test_init_command.py` 导入私有 fake。

`tests/cli/test_prompt_command.py` 最终内容 SHA-256 为
`8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a`；相对 authorization HEAD 的
该文件 diff SHA-256 为 `5ac9deaf72e7c2930eb87d9a68e0bac5e662ffd8e6f6feff838bd85964a27642`。
五个 product/test/README payload 的 aggregate diff SHA-256 为
`e66bf3660a6bbe4d82d93115b7cdfb481cb94f943d2126ee38c9df83f6285698`。

本 implementation evidence 只新增本文：
`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-codex.md`。

## 4. Fresh focused and regression validation

所有 Python 命令都先执行 `source .venv/bin/activate`；本地环境为 Darwin / Python `3.11.15`。

| Validation | Result | Count / note |
| --- | --- | --- |
| exact secret-input owner nodes | PASS | `14 passed, 3 warnings`；`1.16s` |
| exact prompt integration consumer | PASS | `1 passed, 3 warnings`；`1.25s` |
| `pytest tests/cli/test_init_command.py -q` | PASS | `41 passed, 3 warnings`；`2.41s` |
| `pytest tests/cli/test_init_smoke.py -q` | PASS | `28 passed, 5 skipped, 3 warnings`；`17.38s` |
| `pytest tests/cli/test_upload_filings_from_command.py -q` | PASS | `20 passed, 2 skipped, 3 warnings`；`13.61s` |
| POSIX real upload exact node（串行） | PASS | `1 passed, 3 warnings`；`11.35s` |
| three-file aggregate | PASS | `89 passed, 7 skipped, 3 warnings`；`27.09s` |
| `pytest tests/cli -q` | PASS | `552 passed, 7 skipped, 3 warnings`；`37.82s` |

Exact owner nodes逐项覆盖并通过：TTY test-owned stream、redirected `io.StringIO`、LF、CRLF、bare CR、其它尾随空白、
required/optional调用顺序、两类 EOF 收敛、TTY/redirected KeyboardInterrupt identity与 CLI exit `130`、confirmation顺序和
动态 value non-disclosure。Direct prompt integration node证明 TTY路径只消费原 getpass sequence；若误入 `readline()` 会立即失败。

本机两个 upload real-Windows nodes及五个 init real-Windows/capability nodes按既有平台条件 skip；这些只记录平台事实，不作为
真实 Windows closure。

一次同时运行 upload whole-file 与其中 POSIX exact node 的验证尝试产生了固定 smoke 目录竞争：两个进程都直接使用并删除
`workspace/tmp/r11-posix-real`，whole-file副本通过而 exact-node副本失败。该失败由测试路径同源证据锁定为验证命令并发冲突，
不是 product/test implementation failure；停止错误并发后，exact node 串行 fresh 重跑通过。没有为此修改 production、test或
timeout。

三个 warning 都来自已安装 `edgar` package 的 deprecated import；本 slice 未修改相关代码。

## 5. Coverage, type and lint

- Coverage command：`pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-branch ... -q`。
- `dayu/cli/commands/init.py`：`311` statements、`26` missed、`100` branches、`11` partial，line coverage
  `90.99756690997567%`，终端取整显示 `91%`，满足 `>=80%`。
- Coverage JSON：`workspace/tmp/win4-rw-init-command-coverage.json`。
- Full pyright：`python -m pyright dayu/ tests/ utils/` ->
  `0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：final plan §13.6.4 四个文件 -> `All checks passed!`。
- Ruff version：`ruff 0.15.11`。
- Entry full Ruff baseline：`142` 项；按
  `(filename, location, code, message, fix-applicability)` 排序后的 canonical JSON SHA-256 为
  `82b3556a9515c8875553ad77cde6565f8340b07a9d84ba3681a115fb3b8780f6`。
- Final full Ruff：同为 `142` 项、同一 canonical SHA-256；`cmp` 完全相同，新增或扩散 `0`。没有清理、掩盖或移动
  unrelated baseline。

## 6. POSIX redirected-input smoke

使用独立 `workspace/tmp` root、独立 `HOME`/POSIX shell profile、动态非生产 sentinel和真实
`python -m dayu.cli init` 执行 redirected stdin smoke。输入依次为 model choice、required secret logical line与最终确认；
optional integrations通过隔离环境显式标记为已配置，避免 ambient environment影响输入顺序。

结果：`PASS / exit=0 / config published / profile persisted / stdout+stderr exact sentinel matches=0`。stderr只包含
names-only prompt；没有把 value、环境快照或 profile内容写入 evidence。该 smoke 证明 POSIX真实 redirected owner消费路径，
不替代后续 Windows redirected-handle closure。

## 7. Diff, README, source and security scans

- `git diff --check`：PASS。
- 相对 authorization HEAD 的 worktree product/test/README paths 精确为五个 §13.3 allowed paths：四个 protected payload加
  `tests/cli/test_prompt_command.py`；新增本文后仅再增加固定 implementation artifact。
- `git diff --cached --name-only`：空；staged tree empty。
- Accepted plan commit到authorization HEAD的 committed delta精确是 Controller-owned control状态与accepted-commit
  validation两个 docs paths；它们不属于 worktree implementation diff，也未被本轮改写。
- 两个 Windows workflow、`tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、
  `dayu/cli/init_environment.py` 与全部 `dayu/fins/` production paths相对 authorization HEAD零 diff。
- Prompt file node-level diff只有三组：必要 import、module-private typed fake、exact node stdin注入；其它nodes、getpass
  sequence与业务断言零 diff。
- 已重新读取根 README 的最终用户边界和 `tests/README.md` 的测试维护边界。现有 protected README diff只说明当前已实现
  TTY/redirected行为及owner coverage；本轮没有追加、重排或改写 README，也没有写 future workflow、canary公式、run-specific
  value或内部治理流水账。
- `rg -n 'getpass\.getpass' dayu/cli/commands/init.py` 只命中 `_read_secret_input()` TTY分支一次。
- `shell=True`、`errors=replace`、`hasattr/getattr`、production pytest/mock/capture identity、`sys.__stdin__`、`msvcrt`、
  PowerShell、Start-Process、word-bounded PTY/pty、JobObject、process group/tree扫描均为零语义命中。
- Plan 原样给出的未加词界 `pty|PTY` grep会把既有单词 `empty` 误报为 substring match；这些命中全部来自 accepted protected
  base内容。使用词界执行同一 forbidden-token扫描为零，且本轮 prompt diff对原始pattern也零新增命中。没有把该扫描器
  false positive当作 product root cause或借机修改 plan/source。
- Upload added-display diff scan为零；没有新增 `Fins result/summary/progress/...` 或 execution stdout/stderr success判断。
- Issue 142/151/175/177/178、`authorization`、`secret infrastructure`扫描为零新增命中。
- Dynamic owner tests与 POSIX smoke共同证明 required/optional values在 stdout、stderr、公开 exception/diagnostic与 pytest
  capture中零命中；没有使用固定 secret blacklist替代动态证据。

## 8. Security and deferred boundary

Config、Host internal SQLite与EventLog继续属于 trusted-local domain；本 slice不读取、迁移、重写或扩大其 durable secret
范围。只维持 Tool Trace、audit、public/LLM-facing/operator diagnostics不得出现 API key/header明文的现有裁决。

本轮没有实现或预埋 production fallback、read-failure fallback、pytest/mock/capture identity、shared test helper、compat shim、
统一 secret/credential/authorization、Issue 142/151/175/177/178、Web/WeChat/render、console/PTY/process isolation、setx
redesign或 Fins generic diagnostic schema。没有读取 GitHub Secrets、configured production values或 run-specific canary。

## 9. Open questions, residual risks and completion boundary

- Blocking open questions：`0`。
- Residual risk 1：Darwin owner tests不能证明 CPython 3.11 Windows console与 redirected OS handle组合。分类：
  `covered by later approved remote validation`；唯一 destination是 final plan §13.8 的 fresh R12。
- Residual risk 2：caller-owned pipe、OS handle与当前 CLI process memory按输入本质暂存 value。分类：
  `assigned to later independent security design`；本 WU只承诺 CLI不主动回显或投影。
- Residual risk 3：若 fresh R11 storage facts失败，或 fresh R12在 secret读取之后出现新 failure。分类：
  `covered by diagnostic-first stop gate`；必须回 Controller，不沿用当前 root cause猜测。
- Residual risk 4：full Ruff `142` 项为 entry既有 baseline。分类：`pre-existing baseline / outside current slice`；本轮精确证明
  五元组集合与 digest不变。

当前没有 accepted implementation commit，也没有 fresh R11/R12 dispatch-returned run id或 remote canary closure；这些不能在
用户明确禁止 commit/dispatch的本 gate伪造或补做。`WIN4-RW-S2` 本地 implementation与 §13.6验证已完成，真实 Windows closure
仍 pending。本 artifact停止在当前 implementation gate；下一 entry point是 Controller validation与后续 code review，不由本轮
自行 dispatch，也不 stage、commit、push或进入 remote/PR gate。
