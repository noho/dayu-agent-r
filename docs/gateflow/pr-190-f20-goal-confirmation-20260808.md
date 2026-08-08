# PR 190 F20 goal confirmation（2026-08-08）

## Work unit identity and preflight

- Work unit：F20；类型：architecture-sensitive root-cause investigation与formal observation/publication。
- branch：`codex/interactive-oracle`；entry HEAD：`a76681f1413151b916e0761bd96c57de2ae07d0f`；与
  `github/codex/interactive-oracle`同步。
- merge/rebase/cherry-pick：不存在；`github/main...HEAD=0/112`，main是HEAD祖先。
- PR 190：OPEN/DRAFT，head=`codex/interactive-oracle`，base=`main`，merge state=`CLEAN`，head OID与本地一致。
- worktree：只有ownership未知且用户明确排除的`docs/reviews/plan-review-20260808-095346.md`；不得读取、修改、暂存或提交。
- control handoff：`docs/gateflow/pr-190-f19-final-closeout-20260808.md`；design truth：
  `docs/host/design.md`与`docs/engine/design.md`。

## First-principles owner decision

F20动机成立，但F19的0次compaction已有足以约束plan的直接owner证据，不应预设产品缺陷：

1. `dayu.host.context_budget.context_sizing_pressure_and_decision`与`_stage_pressure_action`拥有五阶段action语义；
   `ordinary + soft_threshold_exceeded`才返回`compact_soft_threshold`，`continuation`在normal/soft/hard三种pressure下都返回
   `allow_dispatch`。
2. `dayu.host.dispatch`在pre-start ordinary candidate冻结后消费该typed decision；只有`compact_soft_threshold`进入proactive
   request/material/compactor path。`allow_dispatch`直接提交dispatch，不产生`CONTEXT_COMPACTION_REQUESTED`。
3. `docs/host/design.md`明确active-run continuation不启动proactive operation；真实provider overflow才由Engine发出reactive
   `context_compaction_requested`。`docs/engine/design.md`也明确Engine不拥有Host budget/proactive threshold。
4. F19两条SQLite/EventLog direct evidence的effective context window均为1,048,576，soft threshold均为18,874：
   - Chain 01 ordinary：9,329、15,340，均为normal/allow；continuation：13,880 normal、38,398 soft/allow、20,057
     soft/allow、22,385 soft/allow。
   - Chain 02 ordinary：9,329、15,371、15,961，均为normal/allow；continuation：13,880 normal、38,386 soft/allow、
     36,641 soft/allow。
5. F19 typed RunInput candidate证明大section只在active Run tool-result continuation形成高pressure；下一Run ordinary candidate
   受真实selected recent/memory projection约束，实际没有达到soft threshold。由section字符数或continuation pressure反推下一
   ordinary必然compact违反owner contract。

Controller据此把F19 root cause初步裁决为`observation setup/material-policy boundary insufficient`，不是产品缺陷。F20 plan必须从
上述typed owner和durable refs完整重验；若发现相反direct evidence，必须停止observation并回到产品owner design/implementation gate，
禁止在CLI、adapter、analyzer、harness或fixture补偿。

## Confirmed goal and success signals

用户已在当前指令中明确确认F20目标：

1. 从Host context-budget/compaction trigger owner、两份design truth以及F19 EventLog/SQLite/RunInput direct evidence形成可审计
   root-cause artifact，区分setup不足与产品缺陷，不从错误字符串、profile名、section大小或事件顺序猜测。
2. 在不修改产品语义的前提下，设计fresh fixed-profile场景，并以production owner进行provider-free boundary proof：首次ordinary
   boundary在R1初始dispatch之后达到soft threshold并触发proactive compaction；accepted first compact之后，新的真实AAPL FY2025
   material必须使后续独立ordinary boundary再次达到soft threshold。这里的“accepted replacement最大caps”只指
   `MemoryProjectionPolicy`实际治理的文本字段达到各自caps时，存在一个其余typed字段取合法、显式、有限canonical值的完整
   accepted candidate，且该candidate经production accept → Memory → RunInput → estimator后的保守边界仍低于hard threshold；
   它不主张policy未治理字段的任意字符串存在universal有限上界。按用户在 RR2 后的明确裁决，provider-free proof通过production
   Host typed construction分别注入run-owned deterministic ordinary worker factory与deterministic compactor typed port，并用Host
   owner ledger证明两类calls各自同源；proof process tree受fail-closed deny-network约束。正式provider链不包装
   `DefaultLocalEngineWorkerFactory`、不拦截request，始终使用stock production CLI/default factory/production compactor。正式证据按
   Host sizing stage拆成三个互不替代的owner predicate：（a）R2、R3各自唯一、attempt-free的pre-compact `ordinary` canonical budget
   fact必须以cursor、logical candidate projection ref、input digest、stage、prediction与action绑定同一候选，满足
   `soft <= predicted < hard`与`compact_soft_threshold`，并与同operation request/terminal exact linkage，只证明合法trigger；该compact
   分支不产生runner-call manifest，provider-free proof如需审计完整candidate，只能另存明确标为run-owned proof projection并与budget
   input digest/ref exact equality，正式stock CLI不得用它补造Host事实；
   （b）每个accepted replacement在Memory catch-up后重建的唯一`post_compact` budget/manifest/candidate必须直接绑定该accepted truth，
   满足`predicted < hard`与`allow_dispatch`，并与后续Run/Attempt/dispatch identity相等，只证明replacement被实际消费；（c）R4 fresh
   reconnect的`ordinary` candidate必须消费第二次accepted truth、满足`allow_dispatch`且proactive operation count仍为2；若R4达到soft并
   启动第三operation，则原样seal为既有`needs-more-evidence`分支。任一predicate缺失、stage/action错配或identity不相等均fail closed且
   不计入B2。proof不能只重放F19未compact counterfactual。
3. Formal observation只使用production CLI、POSIX PTY、真实AAPL corpus/production tools与`mimo-v2.5-pro-plan`；最多三条fresh
   chain、bounded global/per-chain deadline。DeepSeek只review，不运行正式provider。
4. 至少观察两次accepted compaction：第一次建立canonical previous EvidenceFact；后一次在cap下让previous fact与新的FY2025
   EvidenceFact竞争，并验证keep/omit、逐fact accepted provenance与omitted exact complement。
5. 覆盖accepted replacement、artifact/EventLog/Memory/RunInput/public Tool Trace同源和fresh reconnect。repair-accepted与
   attempt-budget-exhausted fallback若不能自然发生在同一真实链，必须用互斥的独立fresh chain和各自terminal truth覆盖，不得拼接或
   伪称同链；自然未触发不得output injection、重标或用unit test冒充。
6. Provider前必须由MiMo/DS独立review plan、external tooling、trigger proof与publication self-test且两路均为二值PASS。
   self-test必须直接断言`observation-summary.json.chains[]`每项拥有自身budget、actual ordinary/compactor counts、terminal refs、
   seal/verdict，以及chain/global deadline owner relative ref与file-byte SHA；同时强制execution index、逐chain path-redacted Tool
   Trace、final-byte digest与`secret-scan.json` last-writer/zero-writes-after。
7. 产出B2编号、人类可读observed-behavior report交用户逐项裁决。F20不得修改accepted oracle/scenario、替用户接受B2或把overall
   readiness标ready。用户裁决与完整readiness validation仍是init/prompt/interactive进入第二轮CI前的独立必要gate。

## Non-goals and scope boundary

- 不修改F18/F19 public/private bundles；只以既有bundle id、relative refs和冻结SHA引用其失败/needs-more历史。
- 不为触发观察而修改Host/Engine/CLI/adapter/analyzer/scene或测试夹具；只有owner direct evidence证明产品缺陷时才停止并重新进入
  产品实现gate，不做场景侧fallback。
- 不修改issue 192 duplicate-governance INFO，不处理Fins schema优化，不扩展B1 cold analyzer。
- 不新建PR、不merge、不mark ready、不approve/request reviewer、不rebase/force-push、不删除分支。
- 不把publication hygiene PASS解释为semantic publication conformance，也不把provider自然输出解释为用户Oracle裁决。

## Gate state

用户当前指令已完成binding Goal Confirmation。current gate / next entry point：`plan`。下一具体任务派发给AgentCodex，产出最小
code-generation-ready root-cause/trigger/publication plan与provider-free tooling proposal；随后MiMo/DS使用`planreview`进行两路独立
review。F19 closeout负责历史状态，本文负责F20 scope contract；两份design truth用于裁决Host/Engine owner边界。当前无blocking
open question。
