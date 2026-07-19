# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 aggregate deepreview zero-change fix confirmation — AgentCodex

## Gate、锁定目标与结论

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`；continuation：`AR-F07 WIN4`；仍属同一 remediation。
- 当前 gate：three-slice aggregate deepreview 后的 zero-change fix confirmation；不是新 WU、代码修复、
  accepted evidence commit、push、remote dispatch 或真实 Windows closure。
- Review 时间：`2026-07-20T04:56:46+08:00`（本机系统时钟）。
- Branch：`phaseflow/host-issues-control`。
- Accepted plan base：`15979f5d32738148bf53daf9defe2dca59b8360c`。
- Target `HEAD`：`d9a9edacfe610038e77c770ba43b63c0f613b549`。
- Five-owner-path aggregate binary diff SHA-256：
  `b22a8b2ef098986e5aab8066844732ee5c40a5e142ab95a0be7a00613fc93ab0`。
- Controller finding disposition 唯一真源：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-aggregate-deepreview-controller-adjudication.md`，
  SHA-256 `81146c0a86f53d11642f8f30b8ba7719c9cfd2c3cfd75796788e8a6bdb6a6731`。
- Verdict：`PASS / ACCEPTED_FINDING=0 / ZERO_CHANGE_AGGREGATE_FIX_CONFIRMED /
  READY_FOR_CONTROLLER_VALIDATION / REAL_WINDOWS_PENDING_RELEASE_BLOCKER`。
- 本 gate 唯一新增文件是本 review artifact。五个 owner paths、任何 README、production、workflow、accepted plan、
  design 与 control doc 均未修改；未 stage、commit、push、dispatch 或进入 PR 流程。

## Findings

未发现实质性问题。

Controller 已裁决 accepted、rejected、needs-evidence、design contradiction、local blocker 与 unclassified residual
全部为 `0`。独立重走 S1→S2→S3 的真实 owner/依赖链后，没有发现可以由当前 gate 关闭的新 code、test、README、
workflow 或 security finding；因此不存在成立的修改动机。对锁定实现增加 fallback、兼容分支、重复测试、process-tree
治理或文档补偿，反而会脱离 disposition 真源并制造 semantic ownership drift。

## 必读输入与内容锁

以下文件均已完整读取；行数、字节数与 SHA-256 来自当前 workspace：

| 输入 | 行数 / 字节数 | SHA-256 | 复核结论 |
|---|---:|---|---|
| `AGENTS.md` | 128 / 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | owner boundary、同源证据、验证与中文报告约束 |
| accepted WIN4 plan | 673 / 45,818 | `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a` | S1→S2→S3 allowlist、security/deferred 与 remote stop gate |
| S1 accepted-commit validation | 31 / 1,641 | `96a6a750ee5fcce383c23721b4a250069b1b4477d784b7c3b1433e56737b0399` | S1 accepted/open finding `0`，real Windows pending |
| S2 accepted-commit validation | 36 / 2,348 | `f5df387111ce0d1ccb92d5da66144f69add3415e1aea3c221248d27c3a0871f7` | S2 accepted/open finding `0`，两项 rejected candidate 已关闭 |
| S3 accepted-commit validation | 25 / 1,647 | `83dbf694665e848000715d47e7d3c2a52af00660286b88466dcea3467bbdb28f` | three slices locally accepted，real Windows pending |
| AgentMiMo aggregate deepreview | 162 / 12,436 | `a3239c2b05c3ac7de7daed0d847c43607ee11d259e3bd2f24a062b948585d5ad` | `PASS / MATERIAL FINDING 0` |
| AgentDS aggregate deepreview | 310 / 28,300 | `469a8001a5353175c4822d57cc0ccb43c75e0728a99cc2d75383841f12435730` | `PASS / MATERIAL FINDING 0 / NO BLOCKER` |
| aggregate Controller adjudication | 42 / 3,106 | `81146c0a86f53d11642f8f30b8ba7719c9cfd2c3cfd75796788e8a6bdb6a6731` | accepted finding `0`；要求本 zero-change confirmation |

同时读取并核对了 S1/S2/S3 initial/final Controller adjudication：S1 从始至终 material finding `0`；S2 的
Python 3.11 patch-version candidate 与无独立语义的 exception-kind/index 笛卡尔积测试 candidate 均为 rejected，且
零回流；S3 的 frame clearing、scripted output timing、renderer invariant 与 raw-timeout probe 均保持 observation/residual，
没有 current action 或兼容工作。

## Immutable aggregate diff 与 commit chain

Accepted chain 保持严格线性：

1. S1 `e34edfa39f244d736aeaf8b9ea82ff9152698b2b`，parent 为 accepted plan base；
2. S2 `5c8c11f88fb0d935ad5730aa7d892ad26a060633`，parent 为 S1；
3. S3 / target `d9a9edacfe610038e77c770ba43b63c0f613b549`，parent 为 S2。

五个 owner path 的完整 `base..HEAD` binary diff按以下固定顺序复算：

```text
tests/cli/test_upload_filings_from_command.py
dayu/cli/init_environment.py
tests/cli/test_init_environment.py
tests/cli/test_init_smoke.py
tests/README.md
```

结果仍为
`b22a8b2ef098986e5aab8066844732ee5c40a5e142ab95a0be7a00613fc93ab0`，与 Controller 锁值精确一致。
Diff stat 保持 `5 files changed, 1311 insertions(+), 96 deletions(-)`；当前 owner target 没有字节级漂移。

## 独立 owner、依赖与故障路径复核

### S1：合法 company-name 输入与 pre-execution oracle

- Fins `upload_company_meta` 继续独占 fresh create/update 的 company-name 必填语义；CLI renderer 只机械投影
  `UploadBatchPlan`，没有默认公司名、ticker 推断、FMP fallback、preseed storage 或 message parsing。
- Windows real-smoke test显式把 `Apple Inc.` 放入 generation argv；执行 `.cmd` 前，test-local oracle验证严格
  UTF-8/CRLF、固定 header、唯一非注释 `upload_filing` 业务命令、恰好一个 `--company-name` 与精确下一 token。
- Oracle 的 batch percent/caret 与 CRT 逆向解析由对抗 round-trip、零条/多条/错误命令/重复字段负例覆盖；
  `company_name_supplied=true` 从同一 oracle 返回值产生，没有从执行成功反推输入事实。

### S2：production setx native contract

- `dayu.cli.init_environment._persist_windows_environment()` 是 `setx` executable/argv、三路 `DEVNULL`、
  `close_fds=True`、`shell=False`、单次 `30.0s` timeout 与 native outcome→names-only result 的唯一 production owner。
- success 在整个 batch 完成后才注入当前 `os.environ`；first/middle nonzero、`OSError`、`TimeoutExpired` 与
  first/middle/last interrupt 均保持 written/unwritten names truth、零 retry、零提前注入。
- `TimeoutExpired` 不绑定、不格式化、不记录、不转抛；result、capture 与 exception projection不携带 raw argv/value。
  Timeout 后不声称 registry rollback，也没有引入原子 registry transaction 的虚假语义。

### S3：outer process、安全投影与 canary

- `_run_init()` 独占 outer CLI process lifecycle：三个 `TemporaryFile(mode="w+b")` binary handles覆盖 child execution
  与 bounded cleanup；stdin在启动前 strict UTF-8 encode/write/flush/rewind，成功后 stdout/stderr strict UTF-8 decode。
- outer `180s` 是 whole-init test deadline，S2 `30s` 是 per-setx production bound；两者粒度、owner 与错误投影不同。
  inner bound先关闭真实 setx hang，outer harness没有替代或掩盖 production fix。
- timeout 四状态逐项保持 deadline returncode、direct kill、bounded cleanup 与 cleanup-timeout 后恰好一次 nonblocking poll；
  failure path不读取 stdout/stderr，唯一 renderer只输出固定 category/timeout/returncode/cleanup/state 字段，并以
  `pytest.fail(..., pytrace=False)` 失败。
- GitHub Actions canary只从公开、合法、正 ASCII 十进制 `GITHUB_RUN_ID` 经 31-byte single-NUL domain 与冻结
  SHA-256 vector派生；非法 workflow env在 CLI 前 fail closed且无 random fallback。本地非 workflow路径仍随机。
- 真实 setx node确实把选中的 canary作为 CLI input并验证 registry round-trip，同时不把值投影到 CLI stdout/stderr；
  standalone R11不消费 canary，也未被错误纳入 R12 canary non-disclosure证明。

组合链没有重复 owner、下游 fallback、兼容 shim、loose parsing、`hasattr/getattr`、跨层反向依赖、共享可变状态或
fixture 固化偶然行为。S1→S3 复用 test oracle函数；S2 production 与 S3 outer test owner通过真实 CLI调用链串联，
没有共享第二套 timeout/security真源。

## Review disposition、scope、security、deferred 与 staging

| Disposition | 最终值 |
|---|---:|
| Accepted aggregate finding | `0` |
| Rejected aggregate finding | `0` |
| Needs-evidence finding | `0` |
| Design contradiction | `0` |
| Local blocker | `0` |
| Unclassified residual | `0` |
| Real Windows residual | `1`：`PENDING_RELEASE_BLOCKER` |

Scope 与安全复核结果：

- `base..HEAD` 的 runtime/product/test/README scope精确收敛到上述五个 owner paths；唯一 production diff是
  `dayu/cli/init_environment.py`，唯一 README diff是 `tests/README.md`。
- `.github/workflows/`、根 README、`dayu/README.md`、Fins production、Config/Engine/Host/Service/UI、design与
  deferred Issue implementation零 diff；commit中的 control/review evidence不被本 gate改写。
- Added-line scan对 `capture_output=True`、`shell=True`、replacement decode、`communicate(input=...)`、named temp、
  process group/job object/PowerShell，以及 Issue 142/151/175/177/178、`web_tools_storage_states`、
  `hasattr/getattr` 均零命中。
- 未读取 GitHub Secrets 或 configured production values；没有 needle artifact、registry authority替换、unified
  authorization、secret infrastructure、Web/WeChat/render 或 deferred capability。
- 写入前 `git diff --cached --name-only` 与 `git diff --cached --check` 均零输出；staged tree empty。
- 既有 `docs/host/issues-implementation-control.md` modification，以及 aggregate review/adjudication 与 S3
  accepted-commit validation untracked artifacts均为用户/Controller受保护输入，本 gate未修改、格式化或 stage。

## 本 gate Fresh 验证

所有 Python 命令均先执行 `source .venv/bin/activate`。

| 验证 | Fresh 结果 |
|---|---|
| combined owner suite：三个 CLI owner test files，`-x -q` | `105 passed, 7 skipped, 3 warnings in 26.10s` |
| full pyright：`python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff：四个 Python owner files | `All checks passed!` |
| `git diff --check <base> <HEAD>` | 零输出；PASS |
| working-tree `git diff --check` | 零输出；PASS |
| `git diff --cached --check` / staged names | 零输出；PASS / staged empty |
| base / HEAD / aggregate hash recheck | 三者精确匹配锁值 |

7 个 skip 是当前 Darwin 对真实 Windows nodes 的预期平台事实；3 个 warning 来自既有 edgartools deprecated imports，
均不关闭真实 Windows gate，也不是当前 diff finding。

本 gate没有 fresh运行完整 `tests/cli` 或 full Ruff，且不把既有结果冒充本轮执行。可引用但明确区分的历史证据来自
同一 immutable S3 payload：完整 CLI 为 `538 passed, 7 skipped, 3 warnings`；full Ruff entry/final 均为既有
`142` 条 exact normalized baseline，tuple SHA-256
`9df493aafef1701c3e2732ee61ea8dfb265d321a435ac12355733c70e245eda5`，新增/扩散 `0`。本轮 Fresh 证据仅是上表列出的
combined 105 owner tests、full pyright、scoped Ruff、三类 diff-check、stage 与 hash recheck。

## Open Questions

无。

## Residual Risk / Blocker

- Local blocker：`0`。
- 唯一 release blocker：`REAL_WINDOWS_PENDING / PENDING_RELEASE_BLOCKER`。本地 Darwin 与 test doubles不能证明真实
  `windows-latest` 上的 `cmd.exe`、`setx` stdio/handle/native-timeout、outer anonymous handles、junction/symlink、
  registry round-trip/cleanup及 Windows process termination行为。
- Closure owner/destination保持为 accepted aggregate evidence commit并push后的 Controller remote gate：必须从本次
  dispatch response锁定唯一 R12 `run_id`，校验 workflow identity/path、event、branch/ref与 accepted `head_sha`，
  对同一 run 的完整 log、JUnit、source hashes与全部 downloaded artifacts独立重算并扫描 canary。standalone R11继续
  按无 secret-input 与 artifact integrity验收，不得伪称由 R12 canary scan证明。
- 本 gate未执行 remote run、未豁免 blocker，也不宣称 WIN4-F01/F02/F03 或 AR-F07 已关闭。

## Stop boundary

本 gate停止在 `ZERO_CHANGE_AGGREGATE_FIX_CONFIRMED`。下一入口仅为 Controller独立验证本 artifact、锁定 hashes、
review disposition、scope/security/deferred、Fresh validations、staged-empty与 real-Windows pending状态；之后才能进入
AgentMiMo/AgentDS 双路完整 aggregate re-review。当前授权不允许修改五个 owner paths、任何 README、production、workflow、
accepted plan、design或control，不允许 stage、commit、push、dispatch、PR mutation或任何 remote closure。
