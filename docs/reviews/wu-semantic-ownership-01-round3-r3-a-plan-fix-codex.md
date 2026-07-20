# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A - Host lifecycle, wait, admin, durable integrity, scheduler health`
- Gate: plan fix only after MiMo/DS plan review and controller adjudication
- Updated plan: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`
- Allowed changes: only the updated plan and this fix artifact

## Changed Files

1. `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`

MiMo/DS review artifacts与controller adjudication均只读；未修改production code、tests、README、design source、control doc或其它文件。

## Accepted Plan-review Finding Mapping

| Source finding | Status | Exact fix location in plan |
| --- | --- | --- |
| DS F-01：旧S2约15个契约，slice过粗 | fixed | `Slice 数量与合并裁决`说明8-slice成本与owner边界，并把旧S2拆为S2-S5：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:170`、`:298`、`:389`、`:481`、`:542` |
| DS F-02：fatal/admission race机制未指定 | fixed | `Deterministic fatal/admission race mechanics`固定真实actor、typed barrier invoker、`asyncio.Event`同步点、直接fatal注入、lease/actor barrier、durable identity和wake顺序断言、caller-cancel变体及禁止sleep oracle：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:430`；S3 stop condition：`:479` |
| DS F-03：S3 daemon observation lifecycle不完整 | fixed | 冻结`max_outstanding_adapter_calls`、token `ACTIVE -> INVALIDATED -> FINISHED` publish gate、shared close deadline与真实CLOSING/STOPPED：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:148`；S6 late-result/cap/close tests与stop：`:647`、`:686` |
| DS F-04：S1 descriptor schema可行性未知 | fixed | 冻结只读pre-check并基于当前DDL证据裁决无需schema变更：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:107`；S1任何代码编辑前的命令、预期列和zero-edit stop：`:234` |
| DS F-05：`Process.start()`失败重试依赖模糊运行时判断 | fixed | 冻结“start异常后同一handle不可重试，close后新建handle”，不以pid/is_alive猜测：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:165`；S8 non-goal与pre/post-spawn tests：`:765`、`:786` |
| DS F-06：Host/HostAdmin Protocol拆分不明确 | fixed | 明确两个独立Protocol、无继承/compatibility wrapper及各自方法集合：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:112`；S2 Protocol反例：`:356` |
| MiMo F1：DR-017/DR-029误诊与S5过度设计 | fixed-as-controller-narrowed | 第一性原理表纠正DR-017 partial start/cleanup poisoning与DR-029 attempted-release后failure：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:63`、`:65`；冻结最小single-flight/step-completion修复而非强制五状态：`:162`；S8目标与测试：`:755`、`:784` |
| MiMo F2：旧S2 admin/actor/health/recovery/watchdog/cancel耦合 | fixed | 与DS F-01同一修复；拆分及handoff/gate-cost裁决位于`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:170`，独立slice headings位于`:298`、`:389`、`:481`、`:542` |
| MiMo F3：projector metadata descriptor shape不一致 | fixed | 冻结六字段完整descriptor、三个producer填充规则、compactor rename/schema/source refs和Tool Trace五字段projection：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:102`；S1 producer/summary tests与scan：`:265`、`:279` |
| MiMo F4：`_HostDurableActor`线程安全规范不足 | fixed | actor callable typing、worker-owned command handle/connection、scheduler独立connection、loop bridges、caller cancellation、busy/retry与close order完整定义：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:113`至`:119`；S2反例/review/stop：`:357`、`:379`、`:387` |
| MiMo F5：`_expire_wait_in_transaction()`关系不明确 | fixed | 明确typed input/output、caller-provided transaction、现有`ResolveWaitFailedOutcome`/payload/event plan/`WaitingRunTerminalInput`构造及复用`fail_run_from_waiting_in_transaction()`：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:144`至`:146`；S6 owner tests：`:649` |
| MiMo F6：DR-017 queue feeder partial cleanup未被覆盖 | fixed-merged | 冻结process failure后的finally queue cleanup、step completion与shielded single-flight：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:166`；S8 kill/join/process-close failure仍清queue的反例：`:788`，stop：`:817` |

## Updated Slice Count And Rationale

- Slice count由5更新为8。
- 旧S2拆为：S2 admin opener/public durable actor，S3 scheduler health/admission/retry/replay，S4 startup recovery batching，S5 active-cancel watchdog/transaction-local classification；原wait/compaction/runtime顺延为S6-S8。
- 超过5个slice的额外gate成本已在plan `Slice 数量与合并裁决` 显式核算：actor thread ownership、health/admission state machine、recovery cursor与cancel watchdog具有不同semantic owner、failure injection、rollback blast radius和review expertise。新增3个implementation/review/commit gate的固定成本低于把这些production-high竞态重新捆绑后的定位与回滚风险。
- 每个slice均有独立目标、non-goals、allowed production files、allowed tests/docs、反例、validation、review focus与stop condition；S2→S3→S4/S5的contract handoff已明确，不按文件或raw finding机械切分。

## Accepted R3-A Coverage Preservation

Plan新增`R3-A accepted finding / confirmation traceability`账本，逐项把DR-006/007/008/009/010/011/012/017/025/029，以及retry exhaustion、watchdog wake、proactive compaction TOCTOU、recovery batching、cancel classification、compact ref fallback和Fins boundary split映射到slice、tests、source scan与stop evidence：`docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md:821`。

没有defer任何当前R3-A accepted finding。唯一保留给后续owner的是controller已裁决的Fins wait-adapter reverse dependency之R3-D Service/Fins搬迁半边；S6仍交付R3-A Host-owned bounded contract并用`dayu/fins/`空diff作为stop条件。

## Validation

- Passed: `git diff --check`。
- Passed for untracked plan coverage: `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`，无whitespace warning。
- Passed for untracked fix-artifact coverage: `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`，无whitespace warning。
- Passed old-single-S2 scan：以下pattern均无命中：`计划切片数：5`、`本计划使用 5 个 slice`、`S2 内的 admin opener`、旧heading `Slice S2：Host Admin / Async Durable Boundary / Admission 与 Scheduler Health`。
- Passed new-slice heading scan：S1-S8恰好8个heading，位置为plan `:203`、`:298`、`:389`、`:481`、`:542`、`:605`、`:690`、`:753`。
- Passed required-heading scan：S1-S8每个slice都恰好包含以下8个heading：`目标与 finding`、`Non-goals`、`Allowed production files/modules`、`Allowed tests/docs`、`必须测试的反例`、`验证命令`、`Review focus`、`Stop condition`；scan输出为每个slice `required_headings=8/8`且`slice_count=8`。

本gate只修改plan文档，不运行implementation tests或pyright；这不是代码验证gate。

## Change Boundary Confirmation

- Production code changes: none
- Test changes: none
- README/design changes: none
- Control-doc changes: none
- Commit/push/PR/implementation actions: none
- Review input changes: none

## Stop Status

`ready-for-plan-rereview`

所有controller accepted plan-review findings均已映射并修正，无直接blocker。下一步只能由phaseflow controller派发MiMo/DS plan re-review；本Agent停在plan-fix gate。
