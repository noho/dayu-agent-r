# WU-CTX-04 第二轮定向 plan fix 记录（AgentCodex）

## Gate metadata

- Work unit：`WU-CTX-04`
- Gate：second targeted plan fix only
- 输入计划：`docs/reviews/wu-ctx-04-plan-codex.md`
- 首轮 fix artifact：`docs/reviews/wu-ctx-04-plan-fix-codex.md`（只读，保持不变）
- 两份 re-review：`docs/reviews/plan-review-20260722-113813.md`、`docs/reviews/plan-review-20260722-113814.md`
- 裁决真源：`docs/reviews/wu-ctx-04-plan-re-review-controller-adjudication.md`
- 代码基线：`974f9e1686f6e26f96830cd3478edc9d0d686c45`
- 写入边界：只修订输入计划并新建本记录；未修改design/control、首轮fix、生产代码、测试、README或其它review artifact，未启动implementation/下一gate。

## First-principles fix judgment

两项动机均成立，且必须在plan owner boundary修正。

- `PRR-001`不是close步骤的排版偏好。fresh RW attachment只执行一次target recovery，而当前scheduler直到`HostDispatchScheduler.close()`才传播active worker lifecycle cancel并写host instance `STOPPING/STOPPED`。若Host先release mutex，fresh owner会在旧owner仍`RUNNING`时正确跳过recovery，之后periodic queued/accepted reconcile也不会补扫旧RUNNING Attempt，形成真实的恢复liveness缺口。正确边界是Host-close专用的scheduler-before-unlock barrier；单attachment close仍允许existing stable Attempt继续，不能一并改成scheduler close。
- `PRR-002`不是可延期的测试补录。`run_compaction_operation(...)`改为required first/max range后，`engine_ingest.py::_execute_reactive_compaction(...)`是现存production caller；不纳入allowed scope只能导致越权修改、兼容default或路径失效。正确边界是把reactive request producer和该唯一caller做机械schema/signature适配，budget来自request时同一policy snapshot，不改reactive count/overflow/recovery/fallback owner。

`dayu/host/llm_compaction.py`直接证明compactor proposal已有`RunnerSpec.default_timeout_seconds`包裹完整`asyncio.wait_for(run_agent_and_wait(...))`并在timeout后传播attempt cancellation token，因此总控判定`DS-RRN-01` evidence-invalid成立；本轮没有重开该项。

## Accepted finding mapping

| Finding | 主计划修改位置 | 冻结后的owner contract | 直接证据与验证 | 未解决项 |
| --- | --- | --- | --- | --- |
| `PRR-001` Host close在execution owner quiesce前释放mutex | §1.3；§2.1 direct evidence；§4 semantic owners；§5.4 lifecycle；§6 affected files；Slice 2 allowed scope/exact changes/tests；§8.2；§10；§14 | Host close固定为gate → wait poller stop → actor drain →全部attachment mutation/pre-start lease drain但继续持mutex → scheduler lifecycle close（停止promotion/background、token/`on_cancel`传播、active worker/task/handle/lane close、host instance `STOPPING -> STOPPED`）→ release mutex/attachment record →其余owner。单attachment close保持gate/drain/release且不关scheduler。mandatory cleanup或`STOPPED`失败时Host health/record保持`CLOSING`、mutex不release、后续owner不关闭并允许重试。 | 当前`open_host.py::_close_owned_resources`在actor后调用scheduler；`dispatch.py::HostDispatchScheduler.close`才执行上述worker/liveness动作，且当前普通异常会提前标`_close_cleanup_done`、Host随后仍`mark_closed`。确定性双openerbarrier要求scheduler close前B只能RO；token/hook在unlock前可见；close成功后B关闭旧RO并fresh RW，在同一次target recovery读取old owner `STOPPED`并推进旧Attempt恢复；异常注入证明不误release/不误报close完成。 | 无plan blocker。hook自身仍best-effort，但“已调用”必须在unlock前可观察；token、task/handle/lane与`STOPPED`属于mandatory barrier。 |
| `PRR-002` reactive production caller/测试遗漏 | §1.3；§2.1 direct evidence；§3 scope/non-goals；§5.7 schema/API；§6 affected files；Slice 2主清单与内部proactive职责分组的allowed production/tests/exact changes/assertions；§8.3；§10；§12；§14 | `dayu/host/engine_ingest.py`只预生成reactive request event/operation id、写同一`pending.policy` snapshot的frozen max，并以required `first_attempt_number=1`、`max_attempt_number=pending.policy.max_compaction_attempts_per_operation`调用operation；不重新读取ingestor policy，不改reactive operation count、overflow closeout、RECOVERING/stale gate、fallback或dispatch。`run_compaction_operation`删除旧`max_attempts`且first/max均无默认值，所有production/test call sites机械迁移。 | 当前`engine_ingest.py::_append_reactive_compaction_requested_event`未写新字段，`_execute_reactive_compaction`传`max_attempts`并再次读policy；`rg`确认production caller为`dispatch.py`与`engine_ingest.py`，direct test caller集中于`test_compaction_operation.py`和`test_compaction_cancellation_scope.py`。allowed/focused validation新增`test_engine_ingest_mapping.py`与`test_compaction_cancellation_scope.py`；断言request新shape、同源first/max及既有count/overflow/stale/fallback/cancellation scope不回归。 | 无plan blocker；没有其它Engine ingest语义获准修改。 |

## Closure / scope preservation

- 首轮7组closure保持`7/7 closed`：同handle唯一attachment、原attachment drain/timeout、deterministic one-shot reconcile、terminal exact cancel query、Slice 2/3 crash handoff合并、direct caller lifecycle、fixture/helper迁移清单均未重新打开。
- 仍为3个slices；Slice 2的attachment/recovery/proactive联合checkpoint、不可单独发布规则与Slice 3 cancel/final integration均不变。
- `MIMO-003`继续deferred到Slice 2/3 implementation diff review，owner仍为AgentMiMo/AgentDS。
- `MIMO-005`、`DS-F01`、`DS-F07`维持rejected-with-reason。
- `MIMO-NEW-002`、`MIMO-NEW-003`维持rejected-with-reason；未扩写one-shot私有算法，也未重排Slice 2内部职责分组。
- `DS-RRN-01`维持evidence-invalid；只保留“若发现其它pre-start provider绕过既有timeout则阻塞”的实施守卫。
- 未增加slice、durable schema/table/index、compat/default、reactive状态机改写、实现动作或下一gate动作。

## Validation

- 完整阅读：`AGENTS.md`；`docs/host/design.md`的Session attachment ownership、§27/§27.1；完整control doc；主计划；首轮fix；两份re-review；第二轮总控裁决。
- 生产直接证据：核对`open_host.py` Host close owner顺序、`dispatch.py` scheduler close/worker/lane/liveness/cleanup异常、`llm_compaction.py`完整Runner timeout、`engine_ingest.py` reactive request/operation caller、`compaction_operation.py`旧attempt signature与全部production/test call sites。
- 测试直接证据：核对`test_open_host_runtime.py` close顺序、`test_dispatch_scheduler.py` token/hook/active task/lane与cleanup异常、`test_recovery_*` STOPPED recovery边界、`test_engine_ingest_mapping.py` count/overflow/stale/fallback、`test_compaction_operation.py`与`test_compaction_cancellation_scope.py` direct call/cancellation scope。
- 计划内部cross-reference/stale scope扫描：确认Host-close顺序在§1.3/§4/§5.4/§6/Slice 2/§10/§14一致且旧错误顺序残留为零；确认`engine_ingest.py`、两份新增allowed tests、focused command与required call-site audit贯穿一致。
- 文档-only gate未运行pytest/pyright/coverage；这些命令属于后续implementation gate，当前未修改生产代码或测试。
- `git diff --check`：通过；因两个允许artifact均为未跟踪路径，另以`git diff --no-index --check /dev/null <file>`逐文件检查，均无whitespace diagnostics（仅因文件内容差异返回预期状态1）。
- changed-files审计：本agent新增修改只涉及`docs/reviews/wu-ctx-04-plan-codex.md`与本文件；gate开始前已存在的control/review工作树状态保持不动。

## Unresolved / residual risks

- Blocking open questions：无。
- 本轮两项accepted findings在plan层均已闭合，没有新增finding级未解决项。
- 既有residual risks不变：Windows native backend环境验证、provider crash外部call非exactly-once、poll cadence、fresh schema边界、MIMO-003 implementation diff review与Slice 2上下文规模。
- 本artifact不宣告plan re-review通过；下一步只能由总控按既定gate复核`PRR-001`/`PRR-002`，本agent不自动继续。

## Changed files

- `docs/reviews/wu-ctx-04-plan-codex.md`
- `docs/reviews/wu-ctx-04-plan-re-review-fix-codex.md`
