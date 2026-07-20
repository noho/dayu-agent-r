# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Corrected Aggregate Deepreview Zero-Change Fix — AgentCodex

## Gate identity and conclusion

- 记录时间：`2026-07-20T10:35:10+0800`（本机系统时钟）。
- 执行者：`AgentCodex`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本记录是 AR-F07 WIN4 corrected aggregate deepreview fix gate，
  不是新 WU 或 sub-WU。
- Aggregate base：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Reviewed HEAD：`de68672b803c4e355d2a18b0fbc2890497053230`。
- Controller verdict：`PASS / ACCEPTED_AGGREGATE_FINDING=0 / NEW=0 / BACKFLOW=0 / BLOCKER=0`。
- 本 gate verdict：`PASS / ZERO-CHANGE FIX RECORD / STOP`。

## Findings

未发现实质性问题。

Controller 已把 accepted aggregate finding 裁决为 `0`，两路 corrected aggregate deepreview 也都报告
new/backflow/blocker/open 为 `0`。从第一性原理看，不存在可由 code、product、test、README、control、plan 或既有
review owner 修复的 root cause；在下游增加 fallback、兼容分支、重复计算或展示补偿反而会制造 semantic ownership
drift。因此本 gate 只新增本 zero-change fix record，没有修改任何既有 file/code/product/test/README/control/plan/review。

## Immutable evidence locks

| Item | Fresh verified value | Result |
| --- | --- | --- |
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | MATCH |
| Reviewed HEAD | `de68672b803c4e355d2a18b0fbc2890497053230` | MATCH |
| Six-path binary/full-index diff SHA-256 | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | MATCH |
| `LC_ALL=C` sorted path-list SHA-256 | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | MATCH |
| AgentMiMo aggregate SHA-256 | `dec40a45edb5666bee732ba802d8137d1bad8f22c9bc592bdc35fc7d2a6ad692` | MATCH |
| AgentDS aggregate SHA-256 | `3137674c8d583ac868355e7dc724c59dafe497fc88534b027c9739a4ba8d443e` | MATCH |
| Controller adjudication SHA-256 | `28279c76975eb8b3e699453f73e5f4a08dd13c6feb9bbf8c5c59cd6a5e9d8949` | MATCH |

Six-path digest 使用以下固定顺序的完整 binary/full-index diff 复算，内容与冻结 payload 精确一致：

```text
README.md
dayu/cli/commands/init.py
tests/README.md
tests/cli/test_init_command.py
tests/cli/test_prompt_command.py
tests/cli/test_upload_filings_from_command.py
```

路径列表经 `LC_ALL=C sort` 后复算，摘要同样精确匹配。当前六个 payload 路径均无 working-tree 修改。

## Controller dispositions consumed

Controller adjudication 是 finding/residual disposition 的唯一 owner。本记录逐项消费且不重分类：

1. Darwin 无法证明真实 Windows console/cmd 闭环、R11/R12 与 RF01 的本地 Windows-only skips，统一去重为唯一
   residual `AR-F07-WIN-REMOTE`；owner/destination 固定为 `Controller → fresh R11/R12`。
2. fresh run 若出现新 failure，只触发 conditional diagnostic-first stop；它不是当前 finding、独立 residual 或新 WU。
3. caller-owned pipe/OS handle/process memory 对 secret 的短暂持有位于既定 threat model 外：`NON_FINDING / NO ACTION`。
4. Full Ruff `142` 项是已证明零新增的 baseline：`PRE_EXISTING / NON_FINDING / NO ACTION`；本 gate 不创建
   cleanup WU，也不把 scoped Ruff 的通过冒充 full Ruff cleanup。
5. `dayu/cli/commands/init.py` coverage 为 `92%`，高于单文件 `>=80%` 门槛：未覆盖行不是 finding，
   不创建 coverage WU。
6. POSIX sibling assertion asymmetry 与 `execution.stdout.count("Fins succeeded")` display assertion 均早于 aggregate
   base 且未被本 range 修改：`PRE_EXISTING / OUT_OF_SCOPE / NON_FINDING / NO ACTION`，不创建 sub-WU。
7. Topics 1-7 的 accepted decisions 不回流；Topics 8-9 保持 no-code；Issue 142/151/175/177/178、
   Web/WeChat/render、security mechanism 与 no-unified-authorization 边界均不漂移。

因此 accepted/new/backflow finding 均为 `0`，unclassified residual 为 `0`；除 `AR-F07-WIN-REMOTE` 外没有第二个
remote、安全、Ruff、coverage、POSIX 或 display residual，也没有新 WU/sub-WU。

## Fresh validation

所有 Python 命令均先执行 `source .venv/bin/activate`。Coverage 数据通过 `COVERAGE_FILE` 写入系统临时目录，
没有改写 workspace 内文件。

| Validation | Command / scope | Fresh result |
| --- | --- | --- |
| Full CLI | `pytest tests/cli -q` | `552 passed, 7 skipped, 3 warnings in 40.33s` |
| Full pyright | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff | 四个受影响 Python 路径 | `All checks passed!` |
| Init coverage | `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-report=term-missing -q` | `41 passed, 3 warnings`; `311` statements / `26` missed / `92%` |
| Six-path committed diff check | `git diff --check base...HEAD -- <six paths>` | PASS / 零输出 |
| Working-tree diff check | `git diff --check` | PASS / 零输出 |
| Staged diff check | `git diff --cached --check` | PASS / 零输出 |
| Staged names | `git diff --cached --name-only` | empty |

三个 pytest warning 均来自已安装 `edgar` package 的 deprecated imports。七个 skips 是当前 Darwin 上的
Windows-only nodes，只归入唯一 `AR-F07-WIN-REMOTE`，不构成本地 finding。Pyright 另有工具版本更新提示，
不影响零错误结果。

## Protected, deferred and security scans

- Aggregate base 到 reviewed HEAD 对 `.github/workflows/`、`dayu/fins/**`、`dayu/cli/output.py`、
  `dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、`dayu/runtime/**`、`dayu/config/**`、
  `dayu/engine/**`、`dayu/host/**`、`dayu/service/**`、`dayu/ui/**` 的 protected production/workflow diff 为 `0`。
- 六路径 added-diff 的 boundary-safe forbidden scan 对 `sys.__stdin__`、`msvcrt`、PowerShell/PTY/process-tree、
  `shell=True`、`errors=replace`、`hasattr/getattr` 为 `0`。
- 六路径 added-diff 对 deferred `Issue 142/151/175/177/178` 与 `web_tools_storage_states` 为 `0`。
- 六路径 added-diff 对 `unified secret/authorization`、`secret/authorization framework` 为 `0`；没有引入统一
  tool authorization 或统一 secret infrastructure。
- Upload test added-diff 对 `Fins result/summary/progress/succeeded/failure/cancelled` 及
  `execution.stdout/stderr` display-derived success 判断为 `0`。
- Production `getpass.getpass` 在 `dayu/cli/commands/init.py` 仅有 TTY owner 分支的一处调用；full CLI owner tests
  fresh 通过，non-disclosure、EOF/interrupt、TTY/redirected capability 与 public storage fact contracts 未漂移。

## Finding and residual ledger

| Category | Count / ID | Disposition |
| --- | --- | --- |
| Accepted aggregate finding at entry | `0` | Controller fixed input |
| Product/code/test/README fix | `0` | zero-change |
| New finding | `0` | none |
| Backflow finding | `0` | none |
| Blocker | `0` | none |
| Unclassified residual | `0` | none |
| Unique remote residual | `AR-F07-WIN-REMOTE` | Controller → fresh R11/R12 |

## Open questions

无。

## Stop boundary

本 gate 只新增本 artifact。进入本 gate 前已存在的 `docs/host/issues-implementation-control.md` working-tree 修改，
以及 AgentMiMo、AgentDS、Controller 三份 untracked aggregate artifacts，均按用户所有内容原样保留。

未执行 stage、commit、push、remote dispatch、PR mutation 或 reviewer dispatch；未进入 rereview。本记录完成后停在
`ZERO_CHANGE FIX RECORD`，不把 local PASS 解释为真实 Windows closure，也不提前推进 Controller 的后续 gate。
