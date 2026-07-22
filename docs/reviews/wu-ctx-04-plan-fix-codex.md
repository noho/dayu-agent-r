# WU-CTX-04 plan fix 记录（AgentCodex）

## Gate metadata

- Work unit：`WU-CTX-04`
- Gate：plan fix only
- 输入计划：`docs/reviews/wu-ctx-04-plan-codex.md`
- 裁决真源：`docs/reviews/wu-ctx-04-plan-review-controller-adjudication.md`
- 代码基线：`974f9e1686f6e26f96830cd3478edc9d0d686c45`
- 写入边界：只修订输入计划并新建本记录；未修改design/control、生产代码、测试、README或其它review artifact，未启动implementation/下一gate。

## First-principles fix judgment

总控接受的七组要求都指向原计划尚未冻结的owner contract，而不是实现细节偏好：重复attachment会让handle级RW truth与对象级RO承诺互相矛盾；提前scheduler close或native unlock会破坏pre-start side effect exclusivity；wall-clock polling测试无法证明liveness owner；宽松cancel link读取无法覆盖terminal race；旧Slice 2公开target recovery却仍唤醒旧count状态机，不是稳定checkpoint。上述动机均由当前生产代码直接支持，必须在plan gate修正。

本轮没有为MIMO-005、DS-F01或DS-F07扩scope。MIMO-003只保留为实施diff出现后由reviewer核对的延期风险，没有预先新增模块或slice。

## Accepted finding 映射

| Finding / fix group | 计划修改位置 | 修后可执行证据 | 未解决项 | 本gate验证 |
| --- | --- | --- | --- | --- |
| DS-F02：同Host handle/Session唯一live public attachment | §1.3、§5.1、§5.4、Slice 1/2测试、§10 | 新增`HostSessionAttachmentConflictReason.ALREADY_ATTACHED`与typed detail；registry先检查`RECOVERING/ACTIVE/CLOSING` live index，再允许native acquire；重复attach为`CONFLICT/retryable=False`且native probe零增量；共享runtime复用唯一对象，独立竞争必须独立`open_host`。 | 无plan blocker；error type命名与closed union已冻结，实施按此落地。 | 对照当前`_PublicHostHandle`尚无attach/registry事实；文档grep确认contract、state与测试三处一致。 |
| MIMO-001 + DS-F03：close/drain/timeout边界 | §5.4、Slice 2 exact changes/tests、§10、§11.2 | attachment顺序冻结为new-work gate→attachment actor-bound mutation drain→pre-start lease drain→native release→CLOSED；Host顺序冻结为health/registry gate→poller stop→actor drain→pre-start drain→native release→scheduler close→其余owner close。明确复用`LLMContextCompactor`的`asyncio.wait_for`/`RunnerSpec.default_timeout_seconds`、provider transport timeout与冻结remaining attempt budget；barrier和真实Runner timeout两类测试均要求mutex不提前释放。 | 若实施发现pre-start provider绕过现有bound，Slice 2阻塞回plan；禁止force unlock或新默认timeout。这是明确blocker，不是未决设计。 | 核对`open_host`现有close顺序、`HostDispatchScheduler.close()`取消task行为、`LLMContextCompactor.run_prepared_compactor_proposal`和`run_compaction_operation`串行attempt路径。 |
| MIMO-004：确定性owned-session reconciliation | §5.5、Slice 2 exact changes/tests、§10 | 定义production/test共用`reconcile_owned_sessions_once(fixed_now=...) -> OwnedSessionReconciliationResult`；production loop只等待既有interval并调用step；测试direct call、barrier/counter/fixed now，不用wall-clock sleep，并覆盖dedupe、closing removal、old-owner no-promotion。 | 无。loop cadence只做wiring test，不声称测试wall-clock调度精度。 | 文档grep确认唯一one-shot名贯穿contract、slice与invariant。 |
| DS-F04：terminal后exact cancel query | §5.8、Slice 3 exact changes/tests、§10 | `state.py`拥有typed identity/candidate与精确SQL join，`run_transition.py`拥有canonical cancel event语义；定义`OwnedAttemptCancelTarget(identity, cancel_request_event_id)`及`read_exact_owned_attempt_cancel_targets(...)`。query不按Run status过滤；linked canonical `CANCEL_REQUESTED`严格校验id/class/type/session/run、空attempt/execution/ref/digest、producer的exact六字段payload与EventLog body digest；坏链fail closed，stale identity过滤，输出稳定有序。 | 无plan blocker；实施不得复用只扫`CANCELLING`或错链返回`None`的现有helper，也不得假设已有payload validator。 | 核对`RunRow.cancel_request_event_id`、`AttemptRow`、`DispatchRecordRow.owner_host_instance_id`、`_cancel_requested_event_request` exact payload shape及当前宽松read helper。 |
| DS-F05：Slice 2→3 crash handoff | §7、合并后Slice 2全部内容、§8.2/8.3、§11.3、§13/14 | 认定attachment-only无稳定checkpoint，原Slice 2/3合并为新Slice 2同一PR/release unit；内部attachment状态明确不可merge/deploy/tag/handoff；禁止compat/xfail/跳过recovery；boundary tests覆盖incomplete REQUESTED + fresh attach/replay overlap、manifest/provider crash、rejected crash与remaining budget，均要求原operation且request exact 1。 | 无。合并增加单slice上下文，但消除了错误的可发布中间语义。 | heading/编号grep确认全计划为3 slices，原proactive部分仅是Slice 2内部非handoff子步骤；completion report改为3/3。 |
| DS-F06：非UI/direct Host caller lifecycle | §3.1、§5.9、§6、Slice 2 allowed files/tests与断言、§10 | headless/script/bootstrap/smoke/test harness direct mutation caller必须显式attach并由自身owner在finally shield close；同runtime helper复用唯一对象；Service不持有、缓存或推断。测试覆盖未attach `ATTACHMENT_REQUIRED`、RW成功、RO拒绝、重复attach conflict；列出五个direct utils smoke迁移文件。 | 无。纯read/open/options case明确不需要伪造attachment。 | `rg`核对当前`utils`、Host tests与CLI/Service direct mutation/open_host call sites，计划加入全量迁移审计命令。 |
| MIMO-002：Slice 2 fixture/helper迁移完成性 | Slice 2“`open_host` fixture/helper迁移清单”、§8.2 | 清单覆盖shared options/helpers、runtime/recovery contexts、public mutation smoke、broader integration、CLI/Service fakes及五个utils scripts；completion要求把每个`open_host`/七类mutation命中归类为显式attach+close或故意typed拒绝，Service ownership grep受限，不能只凭pyright/抽样通过。 | 实际逐site勾选属于implementation review执行项；plan已给出封闭清单与完成判据。 | 对Slice 2原listed files及仓库`open_host(`/public mutation grep结果逐类核对；补入原清单遗漏的shared helpers与直接caller测试。 |

## Deferred / rejected reconciliation

- MIMO-003：仅在合并后Slice 2与Slice 3 implementation review基于实际diff检查`dispatch.py`、`open_host.py`、`session_attachment.py`的God function/module、constructor coupling与semantic ownership drift；本plan fix不预设新模块或扩scope。
- MIMO-005：维持驳回。fresh schema、旧字段strict unknown-field rejection与未来migration WU边界不变。
- DS-F01：维持驳回。`resolve_wait`是既有durable continuation，commit后直接`wake_dispatch`，不改成attachment promotion work。
- DS-F07：维持驳回。不新增docs-only slice；合并后仍保留focused cancel Slice 3与final integration。

## 未解决项与风险

- Blocking open questions：无。
- 实施期唯一finding级延期项为MIMO-003，由Slice 2/3 code review owner基于实际diff裁决。
- 既有operational residual risks继续由主计划§11.2管理：Windows native backend环境验证、provider crash窗口非exactly-once、poll cadence、fresh schema边界；本fix未把它们改造成新scope。
- 若pre-start provider出现未受既有Runner/provider timeout约束的直接证据，按主计划将Slice 2标为blocked并回plan，不能force unlock。

## Validation

- 完整阅读并互证：`AGENTS.md`、design、control、原计划、两份plan review与总控裁决。
- 生产代码直接证据：public Host当前无attachment registry；open_host当前执行workspace startup recovery/watchdog；scheduler close会取消promotion/active tasks；Runner compactor已有全调用timeout；Run/Attempt/dispatch/cancel link字段支持exact query但当前helper仍宽松。
- 测试/fixture证据：枚举Slice 2 listed files及仓库direct `open_host`、public mutation、CLI/Service fake/helper call sites，形成显式迁移清单。
- 文档一致性：检查slice编号、accepted关键contract与deferred/rejected边界；无implementation命令或测试执行，因为本gate禁止代码/测试修改与下一gate。
- 收尾要求：执行`git diff --check`；以gate开始时status为基线，确认本agent新增修改只涉及`docs/reviews/wu-ctx-04-plan-codex.md`与本文件。
