# WU-CTX-01 Slice 1 first-call producer plan amendment（AgentCodex）

## 1. Gate result

- status：`Controller §5 plan fix complete / implementation not resumed`
- gate：Slice 1 first-call producer directed plan fix
- branch：`feat/wu-ctx-01`
- plan：
  `docs/reviews/wu-ctx-01-plan-codex.md`
- design：
  `docs/host/design.md` §25
- Controller adjudication：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-review-controller-adjudication.md`
- blocking questions：`None`

本gate只修计划并逐项落实Controller §5。现有partial production、tests、control doc与
其它review artifacts均
保持原样；未运行实现、未修改其内容、未commit。

## 2. 修改范围

本次只修改：

1. `docs/reviews/wu-ctx-01-plan-codex.md`
   - 修复source policy strict-load循环，固定exact input fact→shared parser→source
     loader→worker caller-policy校验链路。
   - 把wait resume闭集收窄为completed/cancelled，failed/lost保持terminal。
   - 彻底删除direct promotion计划旁路，scheduler ordinary governance成为唯一owner。
   - 固定5-stage显式穷举、`source_refs`全construction-site审计与planned/committed
     wait id/digest一致性。
   - 固定Engine limited manifest非pre-start recorder语义与3 slices边界。
   - 收紧3 slices的production/test allowlist、README trigger、full Host tests、full
     pyright与逐文件coverage。
2. `docs/host/design.md` §25
   - 将stage闭集扩为五值。
   - 固定active-run continuation eligibility、三pressure allow与真实overflow owner。
   - 固定startup exact policy source、steer同payload strict parse、wait closed resume
     set、Engine limited manifest与queued ordinary governance语义。
3. 本artifact
   - 报告本轮Controller accepted finding disposition、direct evidence与next gate。

未扩大两个独立产品修改，仍为：

1. provider-neutral usage-anchored adaptive sizing；
2. durable context-budget fact与typed public projection。

slice数量仍为3；不扩Service/UI/Engine production，不进入Issue #119。

## 3. Production direct evidence

### 3.1 Pending producer反向审计

对`DispatchRecordStatus.PENDING`、`insert_dispatch_record`与durable start row
constructors的production调用点反向审计得到：

| producer | direct evidence | plan disposition |
| --- | --- | --- |
| initial / queued ordinary | `dispatch.py` scheduler同时选择`ACCEPTED`与无active时最早`QUEUED` | 两者统一由ordinary governance拥有 |
| legacy direct queue promotion | `admission.py::promote_next_queued_run`直接创建pending；当前只有tests调用 | 删除production旁路并迁移tests；不保留compat |
| governed post-compact/fallback | `dispatch.py`调用governed start transition | manifest-before-start，stage按真实operation outcome |
| reactive recovery | `engine_ingest.py`调用recovery start transition | accepted compact后exact catch-up，再manifest-before-start |
| startup/orphan recovery | `recovery.py::_start_recovery_dispatch_or_ready`直接调用recovery start transition | 只能strict replay source candidate+sizing |
| running/waiting steer | `admission.py::_create_steer_attempt_result`直接写start facts与pending row | 新input/digest candidate与manifest必须先写 |
| wait resume | `waiting.py::_resolve_resume`调用resume transition创建start与pending row | transition前冻结planned accepted-result continuity与manifest |

`create_running_run_with_starting_attempt_in_transaction`目前没有production caller。
但`promote_queued_run_in_transaction`自身会append start facts、创建Attempt与pending
row；只删admission caller仍留下可绕过governance的production API。因此必须同时删除
admission method/operation、durable transition、`promote_queued_run_row`与专属
request/result/skip/validation/event/row helpers及专属tests；本轮撤销
`run_transition.py`零diff承诺。

### 3.2 Strict consumer正向审计

`dispatch.py::_build_frozen_run_input`对当前
`run_id/attempt_id/execution_id`调用
`load_prepared_runner_call_candidate_in_transaction`。它没有producer-kind fallback，
也不应增加source Attempt/current config重建。

因此根因不是worker过严，而是所有新Attempt producer没有共同满足
manifest-before-start contract。修复必须落在各producer transaction与共享RunInput
owner，不能落在worker、fixture或adapter。

### 3.3 Durable source owners

- `USER_INPUT_ACCEPTED.effective_execution_config`已有共享strict parser
  `_execution_config_projection.effective_execution_snapshot_from_json`；initial
  admission必须把实际baseline/tools/mode冻结进去，后续producer只读durable facts。
- 当前`load_prepared_runner_call_candidate_in_transaction`在解析candidate前要求caller
  先传`PolicySnapshot`，而candidate只保存policy ref/digest；startup若以candidate为
  policy来源会形成循环。source Run当前`input_event_id`指向的exact
  `USER_INPUT_ACCEPTED.effective_execution_config`是唯一可先行重建typed policy的真源。
- `run_input.py`已经拥有candidate parser/digest、manifest strict load与wait resume
  continuity读取；它继续是唯一语义owner。
- `waiting.py`已拥有strict wait request、resolution event plan和accepted result
  transaction orchestration；它不应复制tool-message parser。
- `run_transition.py`的typed start inputs已要求caller提供全部identity，并原样写入
  lifecycle rows；manifest recorder不应依赖其中任一种start input类型。
- Engine iteration ingestion已经能观察
  `IterationStartedData.input_projection`，但当前continuation sizing机械使用
  `ORDINARY`；这是stage ownership缺口，不需要修改Engine production。
- `waiting.py::_resolve_in_transaction`只把completed/cancelled交给`_resolve_resume`；
  failed调用`fail_run_from_waiting_in_transaction`，lost调用lost terminal transition，
  两者均不创建resume Attempt。

## 4. 关键裁决

### 4.1 新增closed `CONTINUATION`

需要新增，而不是复用`ORDINARY`。

startup exact replay、steer、wait resume和Engine within-Attempt iteration都已有
active-run lifecycle truth。若使用ordinary：

- soft action要求创建新的proactive operation，但这些路径没有unstarted Run/input
  owner，且会与recovery、steer或waiting状态机竞争；
- hard action要求unstarted Run failure owner，但Run已有旧Attempt或当前Attempt仍在
  执行，前置条件不成立；
- 改用compact-failed、lost或其它terminal owner会伪造业务事实。

完整total function固定为：

| stage | normal | soft | hard |
| --- | --- | --- | --- |
| `ORDINARY` | allow | compact | block |
| `POST_COMPACT` | allow | allow | block |
| `DISPATCH_FALLBACK` | allow | allow | block |
| `REACTIVE_POST_COMPACT` | allow | allow | allow |
| `CONTINUATION` | allow | allow | allow |

实现必须显式穷举五个stage/十五个cell，unknown fail closed；不得用default
fall-through让post-compact/fallback/continuation“碰巧”得到allow。

`CONTINUATION`只允许：

1. startup/orphan exact replay；
2. running/waiting steer；
3. wait completed/cancelled resume；
4. Engine `iteration_index > 0`。

failed/lost wait继续由existing terminal owner收口，零manifest、零new Attempt、零pending
dispatch。

真实provider overflow仍由Engine
`context_compaction_requested`与existing bounded reactive compaction/recovery
state machine拥有。sizing只如实记录pressure，不冒充overflow outcome。

### 4.2 Producer dataflow与event ordering

- ordinary / queue promotion：
  candidate -> sizing -> manifest -> `RUN_STARTED` -> `ATTEMPT_STARTED` -> pending row。
- startup：
  strict source candidate+sizing -> continuation manifest -> recovery start facts ->
  pending row。
- running steer：
  new `USER_INPUT_ACCEPTED` + new digest -> steer/old Attempt close -> candidate ->
  continuation manifest -> start facts -> pending row。
- waiting steer：
  new `USER_INPUT_ACCEPTED` + new digest -> steer/wait cancellation -> candidate ->
  continuation manifest -> start facts -> pending row。
- wait resume：
  strict wait/request + planned accepted result -> RunInput continuity -> candidate ->
  continuation manifest -> existing transition的
  `RESUME_REQUESTED` -> `TOOL_RESULT_ACCEPTED` -> start facts -> pending row。
- Engine within-Attempt continuation：
  accepted complete observed projection -> existing limited continuation manifest ->
  Slice 2 budget fact -> iteration link/preview；不构造prepared candidate，不调用
  pre-start candidate recorder。

Slice 1只冻结candidate、conservative sizing atoms、stage/action与manifest，不读取或
写`CONTEXT_BUDGET_EVALUATED`。Slice 2才为每条完整sizing路径在manifest后、start/link
前写canonical fact；startup从matching source manifest/fact校验并复用canonical sizing
atoms，以new Attempt identity和`CONTINUATION`重新派生action、追加新fact，不复用source
fact identity。Slice 3才允许eligible complete新candidate使用usage anchor；startup
exact replay不重新选择anchor。provider usage缺失/非法/歧义/lineage gap时继续使用Slice
1/2同一complete-candidate conservative estimator，绝不退化到display-text/subset
算法。

### 4.3 Source、replay与failure

- startup source Run/current input event missing，input event type/Session/Run identity
  mismatch，`effective_execution_config` strict parse失败，或manifest/candidate
  policy/request/tool/sizing mismatch、`not_applicable`：不创建new Attempt，由existing
  startup LOST/unrecoverable owner收口。
- startup valid source：exact replay candidate与sizing atoms，只把本次stage重绑定为
  continuation；不重新估算，不读取current config。
- steer任何parse/CAS/manifest失败：整笔rollback，包括新input、旧Attempt close与wait
  cancellation。
- wait request/result projection失败：wait保持waiting，零manifest/result/start。
- wait failed/lost：保持existing terminal failure/lost owner，零continuation
  manifest、零new Attempt、零pending dispatch。
- wait transition miss/CAS失败：candidate payload与manifest随同一transaction回滚。
- same idempotency key只允许相同resolution digest；不同digest conflict。
- Engine continuation缺任一frozen source：写closed unavailable manifest与lineage
  barrier，不从current config补齐。
- worker strict load mismatch：Host input integrity fail closed，不做consumer fallback。

## 5. Code-generation-ready owner interfaces

manifest recorder改为朴素direct identity：

```python
def record_prepared_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    payload_store: PayloadStore,
    *,
    run: RunRow,
    attempt_id: str,
    execution_id: str,
    occurred_at: datetime,
    candidate: PreparedRunnerCallCandidate,
    sizing_snapshot: RunnerCallSizingSnapshot,
) -> EventLogRow:
    ...
```

strict source read：

```python
@dataclass(frozen=True, slots=True)
class PreparedRunnerCallSource:
    manifest_event: EventLogRow
    manifest: RunnerCallInputManifest
    candidate: PreparedRunnerCallCandidate

def load_run_input_policy_snapshot_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
) -> PolicySnapshot:
    ...

def load_prepared_runner_call_source_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> PreparedRunnerCallSource:
    ...
```

policy helper用source `RunRow.input_event_id`精确读取并验证
`USER_INPUT_ACCEPTED`的type/Session/Run identity，再把
`effective_execution_config`交给共享strict parser重建`PolicySnapshot`。source loader
随后校验manifest/candidate policy ref/digest/request semantics、tool snapshot与sizing。
startup/wait/Engine共用它；existing worker loader保留caller policy参数，但先委托source
loader并额外比较caller policy typed identity/digests。禁止current opener policy、
current config或candidate raw digest反向构造policy。

explicit current-input candidate preparation：

```python
def prepare_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_input_event: EventLogRow,
    continuity: SessionContinuityView,
    policy_snapshot: PolicySnapshot,
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    memory_projection_policy: MemoryProjectionPolicy,
) -> PreparedRunnerCallCandidate:
    ...
```

wait continuity：

```python
def project_wait_resume_continuity(
    *,
    user_prompt: str,
    accepted_result: AcceptedToolResultProjection,
    source_refs: tuple[str, ...],
) -> SessionContinuityView:
    ...
```

planned payload与committed event row通过`accepted_result_projection.py`的同一个strict
core得到typed `AcceptedToolResultProjection`；RunInput不loose-parse mapping，只接受
completed/cancelled typed status。pre-start ref使用
`event_plan.tool_result_event_id`，transition committed id必须逐字相等，owner test断言
两条path messages/source refs/candidate digest一致。

`SessionContinuityView.source_refs`改为必填。用
`rg -n "SessionContinuityView\\(" dayu/host tests/host`审计全部construction site；
ordinary显式传`()`，wait传request/result refs；不增加默认值、union、callback、
factory、bag、lazy import、`getattr/hasattr`或compat wrapper。

internal composition不新增dependency bag。`HostAdmissionService`直接增加
`PayloadStore`、context policy、memory policy、truncation flag与owner host id；
existing baseline/tooling字段继续直接传入。`DefaultHostResolveWaitService`只直接接收
payload store与memory policy，policy/tools/mode从strict source取得。
`SessionAttachmentRecoveryScanner`只增加payload store，不接收current
baseline/tooling/context policy。`HostCommandHandle`不复制这些字段；`command.py`用
一个模块级constructor helper从唯一admission service逐项装配wait producer，
`open_host.py`的execution、wait-poller与recovery factories逐项显式传参。完整target
signatures见主计划§5.3.1。

## 6. 最小实现allowlist与验证

Slice 1 production allowlist在原有candidate/manifest/context owner上仅增加：

- `dayu/host/admission.py`
- `dayu/host/recovery.py`
- `dayu/host/waiting.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- 必要的`dayu/host/command.py`与`dayu/host/open_host.py`内部装配

`durable/state.py`与`run_transition.py`只允许删除legacy direct promotion专属
mutation/transition/types/helpers；其它governed/recovery/wait contract不改。Service/UI/
Engine production不修改。

direct promotion专属tests/imports/fixtures从`test_admission_queue.py`、
`test_admission_multiprocess.py`、`test_run_attempt_transitions.py`、
`test_state_schema.py`删除；替代owner tests落在scheduler ordinary queued pickup与
wake-only。其它新增Host test owner为public steer、accepted-result projection、wait
command/public completed/cancelled resume、failed/lost terminal反例、waiting
integration、recovery dispatch/scan/session attachment、open-host/command assembly。
现有manifest、run input、dispatch、engine ingest、projection、Tool Trace、lifecycle、
outbox与非promotion transition regression继续保留。

每个slice必须：

1. 运行其全部focused Host tests；
2. 运行full `python -m pyright dayu/ tests/ utils/`；
3. 对每个实际changed production Python文件以focused + affected integration tests
   单独执行line coverage `>=80%`；
4. 最终运行full Host/Service/Engine/CLI affected suites与项目标准suite；
5. 执行producer/consumer、stage、manifest v1、weak typing、import boundary、
   direct-promotion零符号、`SessionContinuityView`全construction-site与
   `git diff --check`静态审计。

README trigger保持：

- Slice 1按目标README约束检查并按需更新`dayu/host/README.md`、`tests/README.md`；
- Slice 2按需更新`dayu/service/README.md`；
- Engine、分层、root README预期无变更；若实现证据改变该判断必须stop。

## 7. Risks、questions与next gate

已通过计划收口的主要风险：

- strict worker面对缺manifest的新Attempt；
- startup从current config“重建”而非exact replay；
- steer遗漏新input或复用旧digest；
- wait只在`RUN_STARTED`后重建continuity；
- active-run path错误触发ordinary compact/block；
- manifest recorder与两类start input union偶然耦合；
- producer CAS失败留下孤立manifest、input、wait cancellation或start rows。
- source policy loader循环导致startup读取current config；
- failed/lost wait被误建continuation candidate；
- direct queue promotion dead API继续绕过ordinary governance；
- Engine continuation误用pre-start candidate recorder；
- Slice 1 sizing atoms、Slice 2 new fact、Slice 3 anchor互相越界。

Controller finding disposition：

| finding | disposition |
| --- | --- |
| MiMo-01 / CTRL-PR-02 / DS-PR-008 | fixed：exact source input fact先经共享parser重建policy；source loader为严格超集；worker委托后校验caller identity。 |
| MiMo-02 / DS-PR-001 | fixed：五stage/十五cell显式穷举，unknown fail closed。 |
| MiMo-03 | fixed：steer直接strict parse刚append的同一event payload。 |
| MiMo-04 | fixed：planned/committed tool-result event id逐字相等，projection与candidate digest owner test冻结。 |
| MiMo-05 / MiMo-06 | maintained rejected clarification：不新增public option；Engine走limited manifest且不调用pre-start recorder。 |
| DS-PR-002 | fixed：`source_refs`必填且全construction-site审计。 |
| DS-PR-003 / CTRL-PR-03 | fixed：admission/durable direct promotion整条删除，scheduler ordinary governance唯一owner，wake-only。 |
| DS-PR-004 | fixed：focused/full Host file lists去重，full `pytest tests/host -q`仍是gate。 |
| DS-PR-005 | fixed without value object：direct identity owner-local validation与mismatch tests，不新增bag/type。 |
| DS-PR-006 / CTRL-PR-01 | fixed：typed accepted-result projection且resume只含completed/cancelled；failed/lost terminal零manifest/new Attempt。 |
| DS-PR-007 | maintained rejected：transaction rollback + existing idempotency/CAS足够，不引入额外id coupling。 |
| DS-PR-009 / CTRL-PR-04 | fixed clarification：两项独立产品修改 + 必要owner修复；Slice 1 atoms、Slice 2 new fact、Slice 3 anchor边界明确。 |

blocking questions：`None`。

remaining risk：当前worktree中的partial implementation尚未按本amendment更新，也未完成
focused tests、full pyright、逐文件coverage或full Host suites，因此仍为
`not accepted`。

next gate仅为：交回Controller，派发AgentMiMo / AgentDS按本轮裁决定向双路plan
re-review。双路review与
Controller adjudication通过前，不恢复Slice 1 implementation，不commit。
