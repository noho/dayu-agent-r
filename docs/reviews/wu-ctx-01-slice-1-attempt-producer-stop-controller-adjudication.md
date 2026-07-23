# WU-CTX-01 Slice 1 Attempt Producer Stop Controller Adjudication

## 1. Metadata

- work unit：`WU-CTX-01`
- gate：Slice 1 implementation
- implementation artifact：
  `docs/reviews/wu-ctx-01-slice-1-implementation-blocked-codex.md`
- accepted plan amendment commit：`3f4190ed`
- decision：`reopen-plan`
- partial production/tests：`not accepted`

## 2. First-principles judgment

本次stop动机成立，且不是旧fixture噪音。

Slice 1已经把worker actual request改为按current
`run_id/attempt_id/execution_id` strict-load frozen candidate/manifest。这个consumer
contract本身正确：若允许worker在manifest缺失时重新assembly，dispatch sizing、
manifest estimate和actual provider request会形成多个真源，后续usage anchor无法证明
同iteration pairing。

但accepted plan的producer audit不完整。它只让ordinary scheduler和reactive recovery
在Attempt start前写manifest，却把以下同样会创建pending dispatch的新Attempt owner
误判为“只需ordering regression、无需production动作”：

- `dayu.host.recovery` startup/orphan recovery；
- `dayu.host.admission` running/waiting steer；
- `dayu.host.waiting` completed/cancelled wait resume。

full Host regression的直接反例是这些新Attempt到达worker后统一失败为
`prepared runner-call manifest is missing before dispatch`。因此root cause是
“first runner call candidate producer集合遗漏”，不是strict loader过严，也不是单个
测试未迁移。

## 3. Rejected shortcuts

以下做法全部拒绝：

1. 在`dispatch.py`发现manifest缺失后调用旧RunInputBuilder二次assembly；
2. 在Attempt/RUN_STARTED commit后补写manifest；
3. 让startup recovery从当前local config重选policy/tools；
4. 只修改public/recovery fixtures伪造manifest，而不修production producer；
5. 把所有新路径机械标为`ORDINARY`，却不执行该stage的soft compact / hard block
   action；
6. 在manifest中复制旧estimate但实际request candidate已经因steer或wait result改变；
7. 为绕开owner扩展而修改`run_transition.py`，除非新plan提供现有caller transaction
   无法满足atomic ordering的直接证据。

## 4. Required plan amendment

恢复implementation前，AgentCodex必须修订plan并保持3 slices不变。修订至少回答：

### 4.1 Exhaustive first-call producer inventory

对每个创建或唤醒pending dispatch的生产入口列出：

- logical candidate是否变化；
- candidate来源；
- frozen policy/tool/mode来源；
- sizing stage与12/新增cell action；
- manifest写入transaction；
- start transition/row owner；
- replay/CAS/rollback；
- actual request strict-load；
- required tests。

至少覆盖ordinary start/queue promotion、proactive post-compact/fallback、reactive
post-compact、startup recovery、running/waiting steer、wait resume，以及Engine
within-Attempt continuation manifest。不得只按函数名grep；必须从pending dispatch
producer和worker consumer双向核对。

### 4.2 Candidate semantics

- startup recovery是同一logical request的重新dispatch：必须从source Attempt strict
  manifest读取frozen candidate，不从当前config或raw EventLog重建；新Attempt
  manifest绑定相同logical candidate，并明确sizing snapshot是合法复用还是重新派生。
- steer接受新用户输入，candidate已经变化：必须使用新`USER_INPUT_ACCEPTED`的durable
  effective execution/tool facts、当前memory/compact truth和新输入形成完整candidate；
  不得复制source candidate冒充新输入。
- wait resume增加LLM-facing
  `user -> assistant(tool_call) -> tool(result)` continuity，candidate已经变化：必须复用
  `run_input.py`现有accepted-result projection与resume message owner，在start前形成
  exact candidate；不得等`RUN_STARTED`后再从start payload重建。
- ordinary/reactive现有candidate contract继续成立。

### 4.3 Sizing stage/action completeness

计划必须从lifecycle owner出发冻结startup recovery、steer、wait resume和Engine
within-Attempt continuation的stage/action。若这些active-run continuation无法合法执行
`ORDINARY`的soft compact/hard block，就必须使用一个语义明确的closed continuation
stage或提供更好的owner设计；不得把hard pressure改写为normal，也不得用estimate伪造
failure fact。

若新增continuation stage，必须：

- 定义normal/soft/hard action及真实overflow的后续owner；
- 更新manifest strict schema、Slice 2 canonical fact parser、consumer audit和全矩阵
  tests；
- 说明它与`REACTIVE_POST_COMPACT`、`POST_COMPACT`、
  `DISPATCH_FALLBACK`的eligibility不重叠；
- 保持public DTO不泄漏内部stage，Service/UI不重算action。

### 4.4 Minimal owner boundary

`run_input.py`继续拥有candidate/manifest strict parsing、resume continuity与digest。
Attempt producers只负责编排各自transaction。计划应优先使用直接typed参数：

- 将manifest recorder对
  `StartGovernedRunInput | StartRecoveryRunInput`的偶然耦合收敛为所有producer可提供的
  朴素attempt/execution/dispatch identity输入；
- source candidate/sizing的transaction-local strict read只有一个实现；
- admission/recovery/waiting不得复制manifest parser、effective execution parser、
  tool-schema JSON或resume tool-result projection；
- composition wiring只传既有Host construction truth，不新增public per-run bag、
  callback seam或service locator。

允许新plan在直接证据支持下扩充Slice 1 production scope到
`admission.py`、`recovery.py`、`waiting.py`、必要的`command.py`/`open_host.py`
内部装配，以及对应tests/README；禁止扩到Service/UI、Engine production或Issue #119
Tool Trace analyzer。

## 5. Verification amendment

除既有Controller checkpoints外，Slice 1必须新增：

- startup recovery source manifest/candidate/sizing缺失或mismatch fail closed，合法
  replay在manifest-before-start后只wake一次；
- running steer、waiting steer、wait resume均断言candidate/manifest先于
  RUN_STARTED/ATTEMPT_STARTED，worker strict-load得到exact candidate；
- steer candidate包含新输入且不复用旧input digest；
- wait resume exact continuity和tool result只出现一次；
- continuation normal/soft/hard完整action矩阵，pressure不改写；
- all pending-dispatch producer inventory test/static audit；
- full `tests/host`通过，public ordering/static terminal manifest expectations按typed
  event identity迁移，不依赖相邻sequence；
- full pyright、所有changed production file line coverage `>=80%`；
- `run_transition.py`默认零diff，若非零即stop；
- README按自身约束更新，不因blocked partial提前发布。

## 6. Residual risk and next entry

| risk | disposition |
| --- | --- |
| 当前partial实现focused通过但full Host仍失败 | not accepted；保留worktree，禁止commit |
| candidate recorder绑定两种start input union | plan amendment必须收敛为producer-neutral direct identity |
| continuation action缺少lifecycle owner | blocking plan decision；不得由implementation临场猜测 |
| public/recovery/terminal tests存在相邻event顺序假设 | 新manifest可见顺序下迁移为typed identity/order断言 |
| full coverage数字已因owner refactor失效 | resumed implementation重新采集 |

没有需要用户新增产品选择的问题。下一入口是AgentCodex完成third Slice 1 plan
amendment，随后AgentMiMo / AgentDS双路plan review；通过并创建protected plan
amendment commit前不得恢复implementation。
