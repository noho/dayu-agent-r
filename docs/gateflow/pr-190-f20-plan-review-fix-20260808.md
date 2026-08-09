# PR 190 F20 plan-review fix（2026-08-08）

## 1. Authority 与结论

- Work unit：F20；gate：`plan-review-fix`。
- 首轮 reviewed plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，旧 byte SHA-256
  `795f15dc6d43027c4648ec2cd423ba0cc3b061b479326801f3c7475495c4e166`。
- AgentDS review：`docs/reviews/plan-review-20260808-202420.md`，`FAIL`，SHA-256
  `029b3b3eb281efbcc7bbd6a7a314b7fdcc5d76d7b0332309ad2e3b46e4de0cb7`。
- AgentMiMo review：`docs/reviews/plan-review-20260808-202626.md`，`FAIL`，SHA-256
  `80cfa9d0eae38d532baa92bc20469f0004720dbd9da36c5294df062c577df977`。
- Controller adjudication：`docs/gateflow/pr-190-f20-plan-review-adjudication-20260808.md`，`FAIL`，SHA-256
  `7586a7d6bf717e5edf4ada52fece4001d9f65b8830d73ba28ea05e1b3078d864`。
- Binding goal：`docs/gateflow/pr-190-f20-goal-confirmation-20260808.md`，SHA-256
  `9e537fb663e647dccb702056316ad7a9a79c15a14149f8f222c76b289a9c67e0`。
- RR2 reviewed plan SHA-256：`503e7d1a27757c763d2a4f9cb68e047c3532f960daaec1d41e29e0640c651d0a`。
- RR2 AgentDS review：`docs/reviews/plan-review-20260808-205705.md`，`FAIL`，SHA-256
  `d252d036692a3dc61aca6178b2bb04ecc98a414f5330a4e11c1f1137afc86305`。
- RR2 AgentMiMo review：`docs/reviews/plan-review-20260808-205808.md`，`FAIL`，SHA-256
  `84ae6448303f155a9af0f7d8d1709b15831d93e3728bbb58d47742a987d23ba5`。
- RR2 Controller adjudication：`docs/gateflow/pr-190-f20-rr2-plan-review-adjudication-20260808.md`，`FAIL`，SHA-256
  `ab0298a36308558efae24f962f3eec09f291be712fb6af22fc3003b81642bcc7`。
- RR3 target plan byte SHA-256：`68a1a708ab2fc1cb86e3c6cc8f180794a88b182ab9509ba7ae0c4ff0b265d6a6`。
- RR3 AgentMiMo review：`docs/reviews/plan-review-20260808-212457.md`，`FAIL`，SHA-256
  `e4c9edf6d1364b8077dfa2a8de4c1f80884eaf406fa98f03b4edaee452226516`。
- RR3 AgentDS review：`docs/reviews/plan-review-20260808-212538.md`，`FAIL`，SHA-256
  `c6c79a55c5ceb213c449cb955a91ea57390d3314265fa6580b21d70fcf269480`。
- RR3 Controller adjudication：`docs/gateflow/pr-190-f20-rr3-plan-review-adjudication-20260808.md`，`FAIL`，SHA-256
  `beb39341708f78c79692ede4bc16f7f8230cd80155054cfc9aa1b0293967b626`。
- RR4 target plan byte SHA-256：`afb34d790c8773fa01e764a218b82554c790ff76bab96a0739f862cb294c7094`。
- RR4 AgentDS review：`docs/reviews/plan-review-20260808-214120.md`，`PASS`，SHA-256
  `7e4bcd41c0d0bdcf3715bc689b1b8bb2ed673c90e397ba68cc561a85433bdb43`。
- RR4 AgentMiMo review：`docs/reviews/plan-review-20260808-214233.md`，`FAIL`，SHA-256
  `706c2e4a3a5bb786c4daa7282e2ba2dcde6d3c3745fa52c51f1f4cba5eeb1a9e`。
- RR4 Controller adjudication：`docs/gateflow/pr-190-f20-rr4-plan-review-adjudication-20260808.md`，`FAIL`，SHA-256
  `58ef255387fc781b03e5e03fa2808e6ceb043d0c58a38e256b0e34e9998e232c`。
- RR5 target plan byte SHA-256：`b0a9bb895d609afdced0da759003f67400312a3c28ef190fbf6eeffde9882a99`。
- RR5 AgentMiMo review：`docs/reviews/plan-review-20260808-215833.md`，`PASS`，SHA-256
  `2e5c11e8cc178c9009e700e06975dab1d6466de96bfb53e9f0c0e9cd2648262c`。
- RR5 AgentDS review：`docs/reviews/plan-review-20260808-215803.md`，`FAIL`，SHA-256
  `f704414a77d17d408e427bb9bd088e3437fa60ddee681da24108a86f25348a88`。
- RR5 Controller adjudication：`docs/gateflow/pr-190-f20-rr5-plan-review-adjudication-20260808.md`，`FAIL`，SHA-256
  `a1926e2c231f8ece5c1a9e8f5aeefb8380f390a7ea12e2bf58293252441e7f0f`。
- RR6 target plan byte SHA-256：`66074bc59b468c2614e14b7e6840a39b45d09aac9e4454dbff576550ac8b27f7`。
- 本fix verdict：首轮F20-PA-01..05与RR2至RR4 findings保持闭合，RR5 accepted finding已落实；状态为
  `ready-for-independent-rr6`。
  这不是plan acceptance，也不授权实现、真实provider或formal observation。

## 2. Finding closure

| Finding | 修订位置 | 修复 | plan-level直接验证 |
| --- | --- | --- | --- |
| F20-PA-01 | plan §5.1、§7 Slice 1、§8 | 删除R2 parent+child recipe，冻结storage-owned R1/R2 sibling refs、parent、字符数与content digest；no-padding使用无ancestor/descendant共同选择、digest唯一、双向无全文包含。production storage不公开源offset，显式冻结`source_range_state=not_exposed_by_storage_owner`，不伪造range；fresh seed必须经同一repository API重算。 | storage owner audit SHA已绑定；R2只含五个top-level siblings且不含任何`s_0013_c*`；任何identity/predicate漂移均`setup-blocked`且provider start=0。 |
| F20-PA-02 | plan §2 signal 3、§5.2、§7 Slice 1、§8、§10、§12 | 删除手算`accepted_view_max_increment_tokens`与universal worst-case主张。直接定位未治理`intent_type`/`reason`及complete renderer/estimator owner，把universal finite owner缺失登记为residual。lower/caps隔离branch都走production accept→terminal→Memory→RunInput→complete estimator，冻结`E/P`、anchor/fallback公式、atoms与render digest。 | owner代码直接显示未治理字段进入RunInput；计划只证明governed fields at caps +固定bounded canonical metadata的场景存在性。formal不再声称pre-forward guard，并分别验证pre-compact trigger、post-compact consumption与R4 reconnect。 |
| F20-PA-03 | plan §5.3 R4、§5.4、§7 Slice 2、§8、§10、§12 | R4 ordinary manifest必须消费第二次accepted truth、action=`allow_dispatch`且operation count仍为2才可声明reconnect。Chain 01预算为`4×21 + 3×5 = 99`，全局为`99+73+73=245`；第三operation可在已启动R4 segment内bounded运行到terminal，随后seal且不再开segment。 | 计划冻结99/73/73与245；R4 compact/第三operation只能needs-more，既不漏算calls，也不再声称首次compactor call为0。 |
| F20-PA-04 | plan §5.4、§5.5、§5.6、§7 Slice 3、§8、§12 | summary chain保持`attempted`/`provider_not_started`封闭variants，并把deadline拆为common global/allocation owner与attempt-only active owner。self-test从private typed projection独立重算budget/count/terminal/deadline，与summary和execution-index作exact equality及terminal双向穷尽。 | provider-not-started强制allocation state=not_started、active=not_created且禁止active fields；corruption覆盖伪造active、missing activation、cutoff越global及SHA/variant漂移。 |
| F20-PA-05 | plan §2 signal 9、§5.2、§7 Slice 1、§8、§12 | proof只经`HostDispatchScheduler.open`消费同一`HostLocalExecutionOptions.worker_factory/context_compactor`，分别冻结两个typed port/ledger；OS deny-network在Dayu import前作为唯一deny owner覆盖process tree，parent audit只拥有parent outbound ledger且命中时先记后raise，credential unavailable/unused。 | 两ledger分别与allow-only ordinary manifests和compactor proposal manifests/attempts/terminals exact equality；precompact trigger不进入worker ledger；parent actual outbound hits=0；Host tool request/result/canonical terminal与storage owner identity exact闭合。 |

## 3. RR2 finding closure

| Finding | 修订位置 | 修复 | plan-level直接验证 |
| --- | --- | --- | --- |
| F20-RR2-PA-01 | plan §2、§3、§5.2、§5.3、§5.4、§6.2、§7、§8、§10、§12 | 删除formal不存在的pre-forward wrapper/request interception/delegate-zero-call语义。formal固定stock production CLI/default factory/production `LLMContextCompactor`，并只在segment后分别接纳R2/R3 ordinary trigger、accepted后的post-compact consumption与R4 reconnect canonical truth。R4第三operation可在已启动segment内消耗99 cap并形成terminal。proof在scheduler local-execution composition中分开ordinary factory与ContextCompactor ledger，并在Dayu import前用OS deny-network+parent audit隔离。 | production CLI没有wrapper installation path；formal不再声称能拦截dispatch。proof两ledger分别与各自manifests/attempts/terminals exact equality；OS binary/profile/bootstrap/event set冻结，OS-only parent/spawned-child numeric TCP/UDP matrix通过，parent audit hit=0，Host tool/storage closure闭合。 |
| F20-RR2-PA-02 | plan §2 signal 8、§5.4、§5.5、§7、§8、§10、§12 | deadline分为global owner、每chain immutable allocation owner和attempt-only active owner。attempted active cutoff=`min(activated_at+540s, global cutoff)`；provider-not-started只保留allocation state=not_started与active=not_created。 | publication exact union禁止skip active fields；private truth独立复算`3×540=1,620s`、active cutoff/effective seconds；corruption覆盖伪造active、missing activation、cutoff越global与variant/key漂移。 |

## 4. RR3 finding closure

| Finding | 修订位置 | 修复 | plan-level直接验证 |
| --- | --- | --- | --- |
| F20-RR3-PA-01 | plan §1、§2、§3、§5.3、§5.4、§7 Slice 2、§8、§10、§12 | binding goal更新为当前SHA并绑定RR3 reviews/adjudication；删除旧goal SHA与pre-dispatch guard残留。formal仍固定stock production CLI/default factory/production `LLMContextCompactor`，只在segment后按各stage canonical truth接受证据。 | 当前goal SHA唯一；计划没有wrapper、request interception或delegate-zero-call语义；B2仍为`unadjudicated`、overall readiness仍为`not ready`。 |
| F20-RR3-PA-02 | plan §2 signal 9、§4.1、§5.2、§7 Slice 1、§8、§10、§12 | 删除全部subprocess child allowlist与Fins target executable/argv/module/digest推断。OS sandbox是process-tree唯一network deny owner；parent Python audit只拥有parent socket/name-resolution attempt ledger，命中时先ledger后抛run-owned typed proof exception。Fins业务身份由Host tool request/result/canonical terminal与storage owner exact closure拥有。 | OS-only matrix只要求parent与spawned-child numeric TCP/UDP为`EPERM`且无endpoint接触；parent DNS hook probe覆盖三个resolver event的先ledger后raise、resolver前fail closed，不把DNS OS错误码当owner且不要求child DNS hook；actual parent hit=0。不解析`resource_tracker`、`spawn_main`、pipe/pickle/argv/PID/order。tool execution failure、terminal missing/extra或storage drift直接FAIL，无direct/in-process fallback。 |

## 5. RR4 finding closure

| Finding | 修订位置 | 修复 | plan-level直接验证 |
| --- | --- | --- | --- |
| F20-RR4-MIMO-001 | plan §1、§2、§4.1、§5.2、§5.3、§5.5、§7、§8、§10、§12 | 将三个owner predicate严格拆开：R2/R3 pre-compact`ordinary`只以attempt-free canonical budget证明soft/hard trigger与request/同operation terminal linkage；每个accepted后的唯一`post_compact`直接绑定accepted truth并证明hard以下allow及Run/Attempt/dispatch equality；R4独立`ordinary`必须消费第二次truth、allow且operation count=2。 | self-test逐项拒绝ordinary/post_compact refs互换、pre-compact digest冒充consumption、R4 compact/第三operation冒充reconnect；hard post-compact在dispatch前block，R4 soft trigger只进入needs-more。 |

## 6. RR5 finding closure

| Finding | 修订位置 | 修复 | plan-level直接验证 |
| --- | --- | --- | --- |
| F20-RR5-DS-001 | plan §1、§2、§4.1、§5.2、§5.5、§7、§8、§12 | 从pre-compact compact trigger删除Host runner manifest kind/ref/SHA/sizing snapshot及Attempt/execution要求；formal只消费attempt-free canonical budget cursor/logical projection ref/input digest/stage/prediction/action与request/terminal。proof需要完整candidate时只写closed run-owned proof projection，并与budget digest/ref exact相等，不能进入formal schema。 | `post_compact`与R4 allow仍要求真实Host manifest及Run/Attempt/execution/dispatch equality；self-test新增伪造precompact manifest FAIL，并保留refs互换、digest冒充consumption、R4 compact冒充reconnect三项FAIL。 |

Controller direct owner核验还确认：production Service assembly把`DefaultLocalEngineWorkerFactory()`写入`OpenHostOptions.worker_factory`，
interactive CLI直接消费assembly；`open_host`则从`CompactorRunnerBaseline`构造production`LLMContextCompactor`。因此formal继续使用
`OpenHostOptions/open_host/CLI`，但proof不能借该public opener注入deterministic compactor。proof唯一composition已修正为production
`HostDispatchScheduler.open(..., local_execution=HostLocalExecutionOptions(...))`：ordinary owner是
`HostLocalExecutionOptions.worker_factory`，compactor owner是`HostLocalExecutionOptions.context_compactor`；Session/Run/input只经同一
durable store/transaction runner的production admission/service APIs，direct SQL/store与proof`open_host`调用必须为0。

网络隔离方案只用于provider-free proof。`/usr/bin/sandbox-exec`binary SHA冻结为
`8290e4be7387a0df83cd1559e86afd880464f269450573d012795761fe298f16`；OS profile覆盖process tree。Python audit hook在任何Dayu
import前安装，只拥有parent AF_INET/AF_INET6 socket创建/连接、DNS/name resolution与UDP sendto attempt ledger，AF_UNIX event-loop
socketpair不计hit；命中event时先写typed ledger，再抛run-owned typed proof exception并使proof立即FAIL。该hook不拥有process creation或Fins
target语义，不检查/拒绝/允许child，也不解析argv、PID、order、pipe/pickle payload；
production Fins worker及`resource_tracker`、`spawn_main`等helper只继承OS deny-network，不安装hook、不冒充bootstrap。OS-only negative
matrix只覆盖parent与spawned-child numeric TCP/UDP的`EPERM`和no-contact；DNS `getaddrinfo`实际可能返回`gaierror`，该OS错误码不作为
network owner证据。独立parent audit-hook DNS probe要求`getaddrinfo`/`gethostbyname`/`getnameinfo`逐项先ledger后typed exception并在resolver
前fail closed，不安装child DNS hook；actual proof要求parent hit=0。Fins recipe由Host tool request/result/canonical terminal与storage owner
identity exact闭合；tool execution失败、terminal缺失/额外或storage drift直接proof FAIL，禁止`sitecustomize`、产品symbol替换或
direct/in-process fallback。

## 7. Storage-owner correction

Controller曾以`jq`直接读取private`sections.json`。该路径违反“财报文档存取只能经`dayu.fins.storage`”的owner约束；其输出已作废，
本修订没有引用它，也没有把它作为PASS依据。

唯一采用的材料证据是`docs/gateflow/pr-190-f20-storage-material-audit-20260808.md`（SHA-256
`b2baa721f9b43087863b0dff099963df942683a8559922ac57a1dace947d4bbd`）。该审计只经
`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`及production Fs implementations读取published bytes，
并明确说明storage contract没有`[start,end)`offset。修订计划据此不发明range；fresh F20 seed仍须重新走同一storage owner并exact match，
历史审计不能替代fresh执行gate。

RR2前的Controller self-check还发现原§5.1“从F19 clean seed复制”存在路径歧义。修订计划已改为只从run tree外、与F18/F19
durable bundle完全分离的既有canonical clean seed创建workspace：copy前冻结clean-seed owner ref、tree byte SHA与path-redacted
source-root identity，并要求resolved canonical seed root及每个copy source与F18/F19 bundle roots均不存在same/ancestor/descendant关系、
symlink或alias逃逸。input corpus可以与storage-owner audit exact match，但不得从F18/F19 failed bundle路径复制任何文件或状态。

## 8. PA-02 owner verification

修订前的“maximum caps upper bound”命题被缩小，原因由以下直接代码事实同源证明：

1. `dayu/host/compact_structure.py:149-169,389-399`将`intent_type`、`reason`及labels定义为非空TEXT/TEXT_ARRAY，
   没有`maxLength`；
2. `dayu/host/context_governance.py:351-421`只对五类业务文本计cap，不计`intent_type`与`reason`；
3. `dayu/host/run_input.py:4663-4695`把两字段直接渲染进Memory messages；
4. `dayu/host/context_budget.py:1251-1289`对完整message/JSON/tool-schema atoms估算；
   `dayu/host/context_budget.py:923-1038`分别拥有fallback `P=E_current`与anchored
   `P=U_anchor+(E_current-E_anchor)`；
5. `dayu/service/host_assembly.py:1849-1864`的default runner options是`max_tokens=None`，不能补成accepted-output cap。

因此当前没有可供F20声称的universal finite serialized upper owner。这一缺口是residual owner question，不是用户目标中的F20 blocker；
修订计划只要求一个其他metadata取固定合法有限canonical literals、governed fields达到caps的完整candidate通过production owner链，
formal actual accepted snapshot不使用不存在的pre-forward hard guard；R2/R3 pre-compact`ordinary`trigger、accepted后的
`post_compact`consumption与R4`ordinary`reconnect只在segment后按各自Host canonical stage/action/identity truth接纳，不满足即seal并停止
后续segment。

## 9. 静态验证与 scope seal

完成的docs-only验证：

- 修订计划不再选择`s_0013`及其child chunks的重叠组合；
- 修订计划不再使用“F19 clean seed”作为workspace来源；Slice 1显式冻结canonical clean-seed owner ref/SHA/path gate，并要求其与
  F18/F19 bundle roots完全disjoint；
- 调用预算文本唯一采用Chain 01=99、Chain 02/03=73、总计245；
- formal contract只允许stock production CLI/default factory/production`LLMContextCompactor`，不存在pre-forward wrapper/request
  interception/delegate-zero-call claim；R2/R3 trigger只取attempt-free canonical budget truth、不要求Host manifest；accepted后的
  post-compact consumption与R4 allow继续要求真实manifest，R4只在operation count=2时成立；第三operation允许当前segment bounded
  terminal，terminal后停止新segment；
- stage corruption逐项fail closed：伪造precompact Host manifest、ordinary/post_compact refs互换、pre-compact digest冒充consumption、
  R4 compact冒充reconnect；
- publication contract包含global/allocation/active deadline typed owners、两个exact discriminated variants、private truth独立复算、
  terminal双向穷尽及active-deadline corruption matrix；
- provider-free contract包含scheduler+同一`HostLocalExecutionOptions`双端口composition、same-store production admission、ordinary
  factory与ContextCompactor独立ledger、Dayu import前OS deny-network process-tree enforcement、parent outbound audit actual hits=0、
  OS-only parent/spawned-child numeric TCP/UDP negative matrix、独立parent audit-hook DNS三resolver先ledger后typed exception，以及Host tool
  request/result/canonical terminal与storage owner exact closure；DNS OS错误码不作为owner证据，不要求child DNS hook；不存在child
  allowlist或对multiprocessing私有pipe/pickle/argv/PID/order的解析；
- 两个untracked文档分别执行no-index whitespace/error check且无finding；未读取、修改、暂存或提交ownership不明的
  `docs/reviews/plan-review-20260808-095346.md`；
- 没有调用真实provider，没有修改F18/F19 bundle，没有修改产品、测试、oracle/scenario或README。

下一entry point只能是AgentMiMo与AgentDS对RR6 target同一byte SHA做独立review。RR6两路latest未同时`PASS`前，禁止实现与真实provider。
B2保持`unadjudicated`，overall readiness保持`not ready`。
