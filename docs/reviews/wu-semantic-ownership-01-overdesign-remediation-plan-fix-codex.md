# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Fix — AgentCodex

## Gate 身份与范围

- **角色**：AgentCodex，既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 remediation 总计划 `fix` gate；不是新 WU、feature、issue、re-review 或 implementation。
- **唯一 finding disposition owner**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`。AgentMiMo / AgentDS 原始 severity、verdict 与建议只提供证据，不能覆盖 controller 裁决。
- **产品真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 与 `docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
- **流程真源**：`docs/host/issues-implementation-control.md` 当前 gate=`remediation plan fix`，以及 `docs/phaseflow-umbrella-optimization-control.md`；本轮用户明确要求的 per-sub-WU 完整 gate 高于其中的低风险流程优化。
- **允许修改闭集**：
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
  - 本 artifact
- **禁止动作**：未修改 control/design/产品代码/测试/README/其它 review；未 commit、push、创建 PR 或进入下一 gate。

## 第一性原理与 owner 判断

修复动机成立。初版总计划的 Topic 1—7 owner map、12 个 sub-WU 切分和总体依赖没有失效；真实缺口是总计划把若干必须由 sub-WU 子计划或平台 owner 决定的事实过早固定，并且没有把用户要求的逐 sub-WU gate 写成确定状态机。因此本轮只修计划 owner 边界：

- umbrella plan 只拥有切分、顺序、全局 invariant、验证与外部 gate 条件，不能代替 R01—R12 的 code-generation-ready plan。
- Windows `.cmd` renderer 拥有 batch parsing/argv boundary；`subprocess.list2cmdline` 不能代签 cmd.exe 语义。
- Fins storage 拥有 snapshot/revision/identity invariant；hash、前缀、retry 次数、异常/lease类名不是 umbrella 产品事实。
- `host_runtime.json` 独占 wait poller 部署数值；typed policy、Service、Host 不保存第二默认。
- prompt/tool schema/renderer source owner 独占 LLM-facing 语义；R03 grep 只能是自动门禁，不是完整 audit owner。
- XBRL producer validation 可以保留 internal raw total；public/LLM projection 只拥有 deduplicated `fact_count`。
- Fins batch plan 拥有 OLD 分类/去重；CLI分别拥有 renderer smoke与真实CLI执行投影。
- CLI init managed-root manifest 独占 reset 目标；当前产品没有 assets ownership，未来 Issue 151 才能扩展同一 manifest。

该处理没有新增第二 owner、fallback、兼容 shim或越界实现。

## 13 项 plan-fix 闭集

| # | 状态 | 具体修订位置与 closure |
| ---: | --- | --- |
| 1 | 已关闭 | Plan §0、§7.3（约第5—228行）、§22.2—22.4、§24：R01—R12 各自必须走独立 plan→双plan review→controller adjudication→AgentCodex fix→双re-review→accepted plan commit→implementation→双code review→controller adjudication→fix→双re-review→accepted sub-WU commit；补齐 artifact naming 与 entry/exit criteria；umbrella plan 明确不能替代子计划。 |
| 2 | 已关闭 | Plan §6 第145行、§7.3：固定当前 `phaseflow/host-issues-control` 按 R01→R12 串行 accepted commits；删除独立实施分支/rebase方案；只允许两路 reviewer 并发读取 immutable target。 |
| 3 | 已关闭 | Plan §7.1/§7.3（第159、200行附近）、§22.2/§22.3：所有 severity 的 controller-accepted actionable finding 均进入 AgentCodex fix与双re-review；rejected/deferred/note不得误实现。 |
| 4 | 已关闭 | Plan §7.3、§22.2—22.3（第1168—1182行）：controller在 accepted-plan、accepted-sub-WU、accepted-deepreview、accepted-PR-review gates 创建local commit；criteria满足后push/open draft PR无需再次询问；保留ready/merge/approve/request reviewers/external comment/issue mutation/delete branch禁令。 |
| 5 | 已关闭 | Plan §18.1—18.4（第907—963行）、§21、§22.1：新增职责单一Windows batch renderer边界，明确`DisableDelayedExpansion`、`%`、`!`、`&|^()`、单双引号、连续/尾随反斜杠、Unicode与追加参数invariant；明确`list2cmdline`不是batch quoting owner；真实cmd.exe recorder/CLI grammar为release blocker。 |
| 6 | 已关闭 | Plan §14.2—14.5（第715—769行）：删除固定hash/prefix/revision grammar、固定retry次数、新异常名、cache lease/class lifecycle；只保留storage-owned同版本snapshot/revision/identity、bounded retry可选、既有typed `source_changed_during_read`、cache不持有失效资源、containment与round-trip invariant。 |
| 7 | 已关闭 | Plan §4、§19.3—19.5（第96、1005—1073行）、§21/§23：当前managed-root manifest仅`.dayu`与`config`；当前不创建/搬入assets、不删除用户自建assets；future Issue151 owner才能加入同一manifest；portfolio永不删；first/reset各prewarm一次，ordinary/overwrite零次。 |
| 8 | 已关闭 | Plan §11.2—11.4（第523—574行）：`host_runtime.json`是所有部署policy数值唯一真源；`WaitPollerRuntimePolicy`无deployment-value defaults/无参构造；Service/Host不复制数值，测试显式构造完整snapshot。 |
| 9 | 已关闭 | Plan §7.5、§8.5、§10.4—10.5（第265、343—347、483—512行）：R03交付人工逐文件source inventory/audit、逐项disposition、R01 handoff消费记录与自动门禁；明确grep非完整性证明；未新增credential fallback/blacklist/特例脱敏。 |
| 10 | 已关闭 | Plan §7.5、§15.2—15.4、§22.1：internal provider validation/diagnostic可保留raw `total`；public/tool/LLM只允许`fact_count == len(returned deduplicated facts)`；增加限定目录/类型的正反scan与owner-level test。 |
| 11 | 已关闭 | Plan §18.2—18.4：补OLD直接文件/行号、annual=5、latest-year periodic=6、presentation=6、call cap=recognized reports、`FINANCIAL_STATEMENTS`无cap、同期等价`_pick_best_per_period` owner；严格区分recorder quoting smoke与真实`python -m dayu.cli -> Service/Fins -> temp storage`端到端smoke。 |
| 12 | 已关闭 | Plan §18.1/§18.3、§22.1/§22.3：R11子计划implementation前必须确认真实Windows runner/CI owner；若需新增最小workflow，先列入子计划closed allowlist；actual cmd.exe check最迟aggregate/PR通过，缺runner/skip/failure不得final closeout。 |
| 13 | 已关闭 | Plan §6第145行、§8.5、§10.4：R01 completion report的逐文件Doc LLM-facing删除/保留清单是R03人工inventory mandatory input，避免平行修改与重复owner。 |

## AgentDS findings disposition

| Finding | Controller disposition | 本轮处理 |
| --- | --- | --- |
| DS-PF-01 | accepted | 已修复。Plan §18.2—18.3定义专用batch renderer与真实cmd.exe对抗验证；不再把`list2cmdline`当batch quoting。 |
| DS-PF-02 | accepted in part | 已按裁决部分修复。Plan §14只保留storage invariant与既有typed error；未保留固定次数、新异常名、snapshot/cache类名。storage-owned方向仍保留。 |
| DS-PF-03 | accepted in part | 已修复accepted部分。Plan §21新增平台quoting安全矩阵；Windows env/config非全局原子residual继续保留。拒绝把unsafe quoting写成residual。 |
| DS-PF-04 | accepted | 已修复。Plan §10要求人工逐文件inventory、disposition和completion evidence；grep降为自动门禁。 |
| DS-PF-05 | accepted | 已修复。Plan §18.1/§18.3与§22定义runner owner、最迟aggregate/PR真实执行和final-closeout blocker。 |
| DS-PF-06 | accepted | 已修复。Plan §15与§22区分internal raw total正向残留和public/LLM反向零残留。 |
| DS-PF-07 | rejected-with-reason | 未实现。R05 publication fencing与R09 terminal validator继续是独立owner；未新增组合场景或跨层错误identity。 |
| DS-PF-08 | accepted with stronger correction | 已按更强裁决修复。Plan §6取消独立分支/rebase，改为当前分支串行commit；R01清单显式handoff到R03。 |
| DS-PF-09 | accepted | 已修复。Plan §18.2/§18.3补OLD精确证据、`FINANCIAL_STATEMENTS`无cap和同期dedup owner。 |
| DS-PF-10 | note / no plan fix required | 未把note升级为fix。Plan保留R12子计划第一步核对current `models.json` 的既有要求，不复制新的catalog snapshot。 |
| DS-PF-11 | accepted with correction | 已修复。Plan §19明确current-product-owned assets语义、当前package无assets、用户assets不删、future Issue151 manifest owner。 |
| DS-PF-12 | note | 无fix；保留其正面检查结论，不增加产品或流程contract。 |

## AgentMiMo findings disposition

| Finding | Controller disposition | 本轮处理 |
| --- | --- | --- |
| MIMO-PF-01 | accepted | 与DS-PF-11合并关闭；见Plan §19 managed-root manifest。 |
| MIMO-PF-02 | accepted | 与DS-PF-01合并关闭；`%`、`!`及cmd元字符风险全部进入真实renderer/smoke gate，不作residual。 |
| MIMO-PF-03 | accepted | 已修复。Plan §11删除typed policy deployment defaults与无参构造语义。 |
| MIMO-PF-04 | rejected-with-reason | 未实现reviewer建议的credential fallback/特例脱敏。Plan §10只保留owner不清时stop回controller，并补完整source audit。 |
| MIMO-PF-05 | accepted | 已修复。Plan §19明确first/reset各一次，ordinary/overwrite零prewarm，删除条件性歧义。 |
| MIMO-PF-06 | accepted | 已修复。Plan §18.3把recorder与真实CLI/Service/Fins/storage端到端smoke分开。 |
| MIMO-PF-07 | accepted / merged | 与MIMO-PF-03合并关闭；deployment数值只来自`host_runtime.json`，非policy内部常量逐条归属。 |
| MIMO-PF-08 | note | 无fix；closed affected-module正面结论保留。 |
| MIMO-PF-09 | note | 无fix；retained/modified安全矩阵正面结论保留，并按controller新增Windows条目。 |
| MIMO-PF-10 | note | 无fix；Topic 8/9与Issue 142/151/175/177/178边界继续保留。 |
| MIMO-PF-11 | note | 无fix；12 sub-WU/30 slices切分不变。 |
| MIMO-PF-12 | note | 无fix；依赖图业务方向不变，仅按controller改为当前分支全串行。 |
| MIMO-PF-13 | note | 无fix；R03继续回到prompt/tool schema/producer owner，未新增normalization层。 |
| MIMO-PF-14 | note，冲突由controller覆盖 | 未采纳“固定retry/新类型无speculative design”的note；按controller CTL/DS证据收窄R07，不把note当accepted finding。 |
| MIMO-PF-15 | note | 无fix；验证框架正面结论保留，并补per-sub-WU gate与Windows closure。 |

## Controller findings disposition

| Finding | Disposition | 本轮处理 |
| --- | --- | --- |
| CTL-PF-01 | accepted / blocking | 已修复。Plan §7.3加入每个R01—R12独立完整gate、artifact naming、entry/exit与accepted commit规则。 |
| CTL-PF-02 | accepted / blocking | 已修复。Plan §7/§22统一为全部severity的accepted finding必须fix+双re-review。 |
| CTL-PF-03 | accepted / blocking | 已修复。Plan §7.3/§22.3明确controller local commits与已授权push/open draft PR；保留未授权外部动作禁令。 |
| CTL-PF-04 | accepted | 已修复。Plan §6固定当前分支R01→R12串行accepted commits，只并发review。 |
| CTL-PF-05 | accepted | 已修复。Plan §14删除固定identity hash/prefix/revision/registry形态，只保留storage mapping/round-trip/containment/fail-closed invariant。 |

## Scope 与越界自审

- Topic 8：仍是no-code，Engine 240字符异常消息策略未进入修复。
- Topic 9：仍不设计统一authorization framework；只保留并准确记录现有I/O防御。
- Issue 142/151/175/177/178：均未被实现；只保留原owner/destination。Issue151只拥有未来product assets及managed-root manifest扩展。
- DS-PF-07、MIMO-PF-04两个rejected finding未实现。
- DS-PF-10/12、MIMO-PF-08—15等note未被升级成实现要求；MIMO-PF-14与controller冲突处由controller覆盖。
- 未引入第二owner、credential fallback、字段blacklist、兼容schema、旧路径读取、下游补偿或R05/R09跨层耦合。

## 验证结果

- `git diff --check`：通过，exit 0、无输出。由于两个目标文件都在preflight时为untracked/新增，另分别执行`git diff --no-index --check /dev/null <target>`；两条命令均无whitespace diagnostic，`no-index`仅因目标与`/dev/null`不同按约定返回1。
- 两个目标artifact diff review：通过。对plan执行whole-file `--no-index --stat`并逐段复读§0—7、§10—11、§14—15、§18—19、§21—26；对本fix artifact做完整复读。反向scan确认固定R07 hash/revision/retry/新异常/cache类名、旧prewarm歧义、severity过滤和fake recorder旧表述均无残留。
- `git status --short` scope check：通过。与preflight相比，既有dirty design/control/review输入保持不变；原本untracked的plan仍是唯一被修订目标，只新增本允许的fix artifact，没有产品代码、测试、README或其它review新改动。
- 测试/pyright：本轮只修改plan/review artifact，未修改产品代码或测试；不运行implementation验证。

## Remaining questions

无。所有controller-accepted plan finding都有明确closure；下一动作只能是AgentMiMo/AgentDS双路re-review与controller裁决。

## Stop status

`plan fix complete`。本artifact完成后停止，不进入re-review、R01子计划或implementation。
