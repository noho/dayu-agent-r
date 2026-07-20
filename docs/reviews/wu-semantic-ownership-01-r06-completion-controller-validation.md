# WU-SEMANTIC-OWNERSHIP-01 / R06 Completion Controller Validation

## 1. Gate 与裁决

- umbrella work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：R06 Fins storage transaction + complete-source publication；不是新 WU，也不是重新打开历史 sub-WU。
- handoff artifact：`docs/reviews/wu-semantic-ownership-01-r06-completion-codex.md`。
- Controller verdict：**PASS / READY_FOR_R06_COMPLETION_ACCEPTED_LOCAL_COMMIT**。
- 当前授权仅限本 completion artifact、本文和同步后的 control state 形成 exact-scope local commit；不授权 R07 implementation、任何 deferred Issue、统一 tool authorization、push 或 PR。

## 2. Git 对象与 exact scope

Controller 直接核验：

| evidence | result |
| --- | --- |
| accepted plan commit | `0d802220fd1ca4ec67addc85915df27becc9b594`，父提交 `9c07b88d9e855f19f0b828f671022119cc5599a1` |
| accepted plan content SHA-256 | `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` |
| transition base | `d048adf7ec1135aaf575384432ebf1137f8a34f2` |
| accepted implementation commit | `4f417e916043ac981d86e113702e010699017ad9`，父提交和 merge-base 都是 transition base |
| accepted implementation tree | `4a7df7583fd2e836bfdf9d07f7486d583596e75f` |
| implementation diff | `88 files changed, 16729 insertions(+), 3614 deletions(-)` |
| allowlist 分类 | 38 production、16 tests、2 README、31 review/fix/validation artifacts、1 control，其他为 0 |

AgentCodex handoff 中四类文件清单与 Git diff 逐项一致；所有引用的 markdown artifact 均存在。本 gate 开始前的 Controller control diff 被原样保留，AgentCodex 只新增指定 handoff artifact。

## 3. Contract 与 owner closure

Controller 接受 handoff 对最终 tree 的以下陈述：

- `BatchToken(transaction_id, ticker)` 是唯一显式 mutation capability；真实 authority 由同一个 storage shared core 的 active registry 判定，不再依赖 ContextVar、task/thread、PID/hostname 或 caller stack。
- lifecycle 只由 batching repository 拥有；十九个 public mutation 均要求 keyword-only、non-optional、无默认值的 `batch`，唯一 transaction-internal public read 是 required-batch staged XBRL probe。
- ambient authority、auto-batch、source lifecycle facade、callback-captured batch、`stage_source_document()` 和 incomplete source-meta acknowledgement 均已删除。
- 四个 production composition roots 各自只创建一个 shared repository set/core；cross-core token fail closed。
- blob-first、final-once producer flow 与 storage-owned complete-source validator 同源；validator 在 publication 前遍历完整 staged ticker tree，reader 不可见 incomplete source。
- writer mutex、短 publication guard、minimal journal、`COMMITTED` 唯一 commit point、crash recovery 和 published read/open old-or-new contract 由 storage owner 闭合。
- long-staging、两次真实 rename barrier、fresh crash-phase recovery 和 delayed open 证据覆盖 online 与 crash 两类独立风险。

R06 没有提前冻结 R07 snapshot/revision、bounded retry、cache、selector/generation layout 或 opaque-ID mapping 方案。

## 4. 验证复核

本 completion gate 不重跑已经接受的产品测试矩阵。Controller 从 accepted implementation/fix/re-review evidence 和保留的 coverage JSON 复核：

| validation | accepted result |
| --- | --- |
| direct cumulative owner cases | `11 passed, 3 warnings` |
| full affected aggregate | `732 passed, 1 skipped, 3 warnings` |
| changed production coverage | 38/38 files 有记录；按 `covered_lines / num_statements` 计算全部 `>=80%`，最低 `dayu/fins/pipelines/sec_download_state.py` 为 `119/148 = 80.41%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-Python scoped Ruff | pass |
| full Ruff delta | base `162`、current `152`、current-only `0`、base-only `10` |
| mutation AST | production `54`、tests `129`、missing explicit batch keyword `0` |
| owner/source scans | ambient authority `0`；production incomplete acknowledgement/false completion `0`；optional/default batch `0`；deferred-scope implementation `0` |
| artifact hygiene | handoff no-index diff check、workspace `git diff --check`、trailing-whitespace scan均通过；staged paths `0` |

coverage JSON 的综合 `percent_covered` 包含 branch 分母，不是 AGENTS.md 的单文件 line coverage 口径；Controller 明确按 line coverage 复算，没有用综合值代替门槛。

README 决定正确：Fins 和 tests README 已同步当前 transaction/publication contract；根 README、`dayu/README.md` 与 design truth 的职责未被本 R06 行为变化触发。

## 5. Finding 最终状态

- plan accepted findings `R06-PF-01..08` 全部 closed。
- slice findings `R06-S1-CR-F01..03`、`R06-S2-CR-F01`、`R06-S3-CV-F01` 全部 closed；较早 `R06-S1-VF-01..04` 也全部 closed。
- cumulative accepted groups `R06-CR-F01..F04` 全部 closed。
- 最终 accepted implementation ledger 为 `9 closed / 0 open / 0 blocker`；每个原始 MiMo/DS finding 均有 accepted/rejected/deferred/no-action disposition。
- 旧 `R06-CR-DS-F07` 按最终 Controller adjudication 明确为 **REJECTED**：当前 default local key/root 与 contained local path 精确等价，FileStore collaborator 拥有自身 key/root containment，没有 reachable divergence 或 bypass 证据。
- `R06-CR-DS-F06` 只把 revision-change-after-build 风险交给 R07，不授权当前修复。

没有 accepted finding 被留作“后续优化”，也没有需要用户重新裁决的 R06 产品问题。

## 6. Security、非目标与 residual owner

保留且未削弱：filesystem containment、symlink rejection、storage identity validation、Web DNS/peer 与 egress policy、resource budgets、atomic write/fsync、process late-publication fencing、cancellation checks、writer/publication/recovery locks，以及 Doc `allowed_paths` / Web policy config 等局部权限机制。

R06 未实现统一 tool authorization framework；没有新增 principal/run/attempt permission model、policy DSL、role/capability、resource scope 或 sandbox。Issue 142、151、175、177、178 和 R07-R11 能力均未偷带。

| residual | owner / destination |
| --- | --- |
| multi-call / processor-lifetime same-version snapshot/revision 与裸 `Path` 延迟读取 | R07 independent plan gate |
| publication lock release syscall 极低概率失败、活进程仍持 kernel fd lock | `dayu.runtime.filelock` / process termination；禁止 unsafe force-release |
| 三条既有 `edgar` deprecation warnings | dependency maintenance owner |
| 一个既有可选 Docling integration skip | Docling integration environment/test owner |

## 7. 下一入口

唯一允许的顺序是：

```text
exact-scope R06 completion accepted local commit
  -> Controller records the real completion commit SHA
  -> R07 independent code-generation-ready plan gate
```

R07 必须重新读取实际 base、独立产出 plan，并完整执行双路 plan review/fix/re-review；本 completion handoff 不是 R07 implementation 授权。R06 completion 不关闭 umbrella WU。

## PASS / READY_FOR_R06_COMPLETION_ACCEPTED_LOCAL_COMMIT
