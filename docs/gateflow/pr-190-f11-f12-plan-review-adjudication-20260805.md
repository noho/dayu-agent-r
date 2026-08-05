# PR 190 F11/F12 Plan Review Controller Adjudication / Fix

## Gate metadata

- Gate：`plan review -> fix`
- Work unit：PR 190 F11/F12 Interactive Memory 收口
- Reviewed plan：`docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- Plan base：`3087b1b983a97ce5012d54e818795f4755434a98`
- Review A：`docs/reviews/plan-review-20260805-144305.md`
- Review B：`docs/reviews/plan-review-20260805-144405.md`
- Controller authority：用户于2026-08-05逐项给出的接受、拒绝与收紧裁决
- Fix status：`complete`
- Current gate：`plan re-review`
- Next entry point：两路原reviewer独立re-review修订后的完整plan
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md`

## Scope and changed files

本fix gate只修改/新增：

- `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- `docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md`

未修改生产代码、`docs/host/design.md`、`docs/engine/design.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md`或finding baseline。两份review与旧observed evidence保持只读。

## Direct evidence used by controller

1. `docs/cli_ci.md:298-307,444`：`superseded`表示旧accepted contract已被替代；修改accepted oracle必须创建新版本并把旧版本标superseded；只有current accepted记录参与正式verdict。
2. registry direct query：611个scenario records的`accepted_oracle_refs`历史指向`cli.interactive.core-execution@1`；它们共有768个`oracle_predicate_refs`、29个unique stable predicate ids。
3. removed-ledger全registry scan：直接依赖只有scenario `interactive.interactive.g06.drop-superseded@1`、`interactive.interactive.g06.drop-policy-limit@1`，以及core predicate stable ids `interactive.29-compactor-output-accept-repair-fallback`、`interactive.30-compaction-semantic-memory-closure`；`tool-trace-formal@1`属于F11版本替换而非drop-ledger依赖。
4. `dayu/engine/contracts/runner.py::AsyncRunner.call`是`@runtime_checkable Protocol`；唯一生产实现为`AsyncOpenAIRunner.call/_call_impl`，生产调用点在`dayu/engine/agent.py`。
5. `dayu/host/compaction.py`当前拥有`CompactCandidateV2`及五个typed children；这是v3 domain dataclass的自然owner。
6. `MemoryProjectionPolicy`当前拥有全部section caps、default、validation和policy digest；`memory.py`已消费compaction domain types，故`compaction.py`不能再反向import Memory policy。跨LLM input边界需要无default/validation的immutable DTO，并由已经同时依赖两侧的Context Governance机械投影。
7. `ToolTraceAnalysisReport.__post_init__`当前硬校验schema version 1；fresh v2必须所有producer/renderer/tests同切，不能保留双读。
8. DeepSeek官方[JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/)与[Chat Completion reference](https://api-docs.deepseek.com/api/create-chat-completion)明确支持`response_format={"type":"json_object"}`；官方同时提示prompt必须要求JSON、输出可能截断/偶发empty content。
9. OpenAI官方[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)明确区分`json_object`与`json_schema`，并要求schema object的全部字段required、nullable通过null union表达、object设置`additionalProperties=false`。这只作为generic transport/schema设计证据，不授权当前catalog model能力。
10. `dayu/host/compaction_terminal.py::_read_operation_terminal_rows`与`dayu/host/proactive_compaction.py::_read_operation_rows`均使用固定page size、单调`after_event_sequence`和short-page exhaustion，不设任意总页数cap；现有测试证明目标跨full page仍须读到。
11. Host design既有约束明确request/source-boundary digest只参与Host内部binding/audit/request serialization，不进入LLM-facing repair JSON。

## Review A adjudication (`plan-review-20260805-144305.md`)

### A-F01 — Registry accepted/superseded lifecycle

- Decision：`accepted`
- Direct evidence：`docs/cli_ci.md:303,307,444`明确旧accepted contract被新版本替代后必须标superseded且不参与current verdict；v3删除`policy_limit`使旧scenario不再可满足。
- Plan delta：S5改为core@1和三个旧scenario更新`status=superseded`及`superseded_by`，保留旧contract/evidence/adjudication正文；append core@2 accepted和三个fresh scenario。补611 records/768 predicate refs按stable predicate id解析唯一current accepted oracle的规则与validation。
- Status：`已修复`

### A-F02 — `AsyncRunner.call` Protocol breaking change

- Decision：`accepted`
- Direct evidence：Protocol、唯一实现与Agent call site签名必须一致；runtime-checkable不验证签名，pyright才会暴露遗漏。
- Plan delta：S2明确required、无default的keyword-only参数；同一accepted commit更新Protocol、唯一实现、全部生产/test call sites，不允许`=None`隐藏漏传。
- Status：`已修复`

### A-F03 — v3 typed dataclass owner不清

- Decision：`accepted`
- Direct evidence：当前全部v2 domain dataclass归`compaction.py`所有；structure module应只处理JSON结构。
- Plan delta：冻结`compaction.py`拥有`CompactCandidateV3`、五个typed children与status enum；`compact_structure.py`单向import并构造domain types，不定义第二组dataclass，`compaction.py`不反向importstructure。
- Status：`已修复`

### A-F04 — `CompactOutputCapsV3`被认为是重复owner

- Decision：`rejected-with-reason`
- Direct evidence：`MemoryProjectionPolicy`不能直接作为LLM-facing input，因为它包含context/fallback/repair等非输出caps且属于Memory模块；直接让Memory import compaction会形成循环/反向耦合。跨边界DTO不等于语义owner。
- Plan delta：保留`CompactOutputCapsV3`作为immutable boundary DTO，但明确`MemoryProjectionPolicy`唯一拥有数值/default/validation/digest；DTO无default/validation，只能由已经同时依赖Memory policy与compaction domain的`context_governance.py`从同一instance逐字段机械构造。`compaction.py`与`memory.py`不新增相互import；增加一一映射test与依赖方向说明。
- Status：`已修复`

### A-F05 — Tool Trace analysis v1→v2策略缺失

- Decision：`accepted`
- Direct evidence：当前`ToolTraceAnalysisReport`只接受1；新增字段会改变public JSON contract。
- Plan delta：明确fresh schema v2删除v1 reader/validation，不保兼容；producer、JSON、Markdown、evidence consumers与tests在S1同切，v1构造/读取必须失败。
- Status：`已修复`

### A-F06 — structured-output capability证据边界

- Decision：`accepted`
- Direct evidence：DeepSeek官方文档明确json_object；Mimo没有本WU可引用的直接能力证明；真实请求只能验证本仓库装配，不能证明“不支持”。
- Plan delta：引用DeepSeek官方guide/reference；Mimo none改写为保守unknown；S4真实验证actual endpoint/model/options装配；OpenAI官方文档只作为generic design evidence；当前catalog无json_schema row。
- Status：`已修复`

### A-F07 — old superseded scenario与v3 omission语义间隙

- Decision：`accepted`
- Direct evidence：旧scenario required evidence明确要求`accepted-candidate-explicit-drop`，v3已删除该字段。
- Plan delta：旧scenario标superseded；replacement required evidence固定为retained current provenance + Host-derived omitted old labels + artifact/Memory/RunInput/reconnect无旧结论，不要求subjective reason。
- Status：`已修复`

### A-F08 — S3原子migration实施风险

- Decision：`rejected-with-reason`
- Direct evidence：拆成accepted checkpoints会出现v2 active contract与未消费v3 contract并存，或parser/prompt/persistence不同步；fresh schema与单一owner优先于小commit形式。
- Plan delta：维持单一accepted vertical migration；补worktree内部types→all consumers+prompt→delete v2→hash/tests顺序，补“只丢弃该slice未提交intended diff并回到S2 accepted commit”的rollback，以及两路review/deepreview缓解。
- Status：`已修复`

### A-F09 — initial/repair模板管理未指定

- Decision：`accepted`
- Direct evidence：两个手写output shape会漂移；模型跨调用无记忆使repair仍必须自足。
- Plan delta：shared packaged system contract；initial/repair都消费同一个`compact_structure` template/schema source；Host分别渲染两种user body。initial无repair protocol，repair含same input/template、previous attempt、bounded issues与whole-candidate action。
- Status：`已修复`

### A-F10 — `session_summary` required/nullable不明确

- Decision：`accepted`
- Direct evidence：v2 exact-key contract要求字段存在；官方schema设计资料也要求所有fields required、optional语义用null union。
- Plan delta：明确全部六个root keys required；`session_summary` required且object-or-null，缺key由schema/parser拒绝；nested objects同样exact required + `additionalProperties=false`。
- Status：`已修复`

## Review B adjudication (`plan-review-20260805-144405.md`)

### B-01 — 要求拆分S3 accepted checkpoints

- Decision：`rejected-with-reason`
- Direct evidence：与A-F08相同；拆分会制造双contract或半迁移accepted状态。
- Plan delta：维持一个accepted原子slice，补内部实施顺序、未提交diff回滚与review risk分类。
- Status：`已修复`

### B-02 — repair digest可能泄漏LLM-facing文本

- Decision：`accepted`
- Direct evidence：Host design与项目LLM-facing约束均要求治理digest不进入模型上下文。
- Plan delta：明确digest只在Host内部binding/audit/request serialization；initial/repair system/user全部禁止digest value与字段名；增加captured runner input反泄漏test。
- Status：`已修复`

### B-03 — S0 design update粒度不足

- Decision：`accepted`
- Direct evidence：Host §24/25与Engine §2/4/6/7/8/15分别承诺不同owner/contract，概述不足以生成准确patch。
- Plan delta：S0增加逐章节edit list，明确§24.3整节v2→v3、旧normative文字删除、F11 §14.1/§25.1、prompt/persistence/tests，以及Engine五处contract修改。
- Status：`已修复`

### B-04 — 建议任意max-pages scan cap

- Decision：`rejected-with-reason`
- Direct evidence：既有canonical owner采用每页有界但扫描到short-page exhaustion；任意10页cap会把后置真实terminal误判missing，破坏F11 exact resolution。
- Plan delta：复用有限event-type keyset exhaustion；page size固定有界、cursor严格单调；empty/short page仅可表示exhaustion，empty/invalid cursor、full-page不推进或row sequence不大于cursor全部fail closed；完整exhaustion后无match才返回None；不新增scan-cap limitation。测试覆盖multi-full-page、non-progress与damage。
- Status：`已修复`

### B-05 — DeepSeek capability缺官方引用

- Decision：`accepted`
- Direct evidence：DeepSeek两份官方页面明确json_object request shape与注意事项。
- Plan delta：计划加入官方URL，并要求S4验证本仓库真实model/endpoint/options；官方声明不替代real observation。
- Status：`已修复`

### B-06 — 建议恢复superseded语义/omission kind

- Decision：`rejected-with-reason`
- Direct evidence：用户已确认删除不可严格验证的model-produced ledger；Host只有provenance补集事实，没有可靠自然语言/subject matcher可产生reason。
- Plan delta：明确不恢复model-produced relation、不做Host自然语言推断、不加`omission_kind`；rolling correction只以current provenance + old omitted labels + downstream无旧结论证明；forward-intent status只描述待办，不能冒充evidence correction。
- Status：`已修复`

### B-07 — repair prompt structure未指定

- Decision：`accepted`
- Direct evidence：自足repair与single structure source必须同时成立。
- Plan delta：shared system contract；Host分别渲染initial/repair user body；两者消费同一immutable canonical structure template/schema；明确各自字段和captured-input tests。
- Status：`已修复`

## Open-question adjudication

### Review A questions

1. Registry validation检查范围：已解决。历史`accepted_oracle_refs`保留裁决时版本；current verdict按stable predicate id连接唯一accepted/non-superseded oracle。S5验证611 records、768 refs、29 ids，0 dangling/duplicate owner。
2. `CompactCandidateV3` children：已解决。五个类型、字段、status enum与source labels已逐项冻结在plan，owner为`compaction.py`。
3. 旧artifact/DB：已解决。不支持旧compact contract、schema-3 artifact与依赖它们的旧Session replay；不删除DB、不做migration，也不声称整个DB bootstrap不能打开。

### Review B questions

1. DeepSeek当前temperature/options：已解决。官方文档授权json_object shape，S4用本仓库实际non-stream compactor options观察成功/empty/provider failure；不从文档推断稳定率。
2. Mimo未来capability：已解决。当前none是保守unknown；未来直接证据通过独立`models.json` catalog change启用，不需要provider-name代码或本WU probe机制。
3. S5 Oracle时机/拒绝回路：已解决。S5不等Oracle controller，implementation/evidence可closeout但oracle pending；未来裁决拒绝产生明确follow-up WU，不篡改本WU已验证事实。

## Additional accepted tightening

- `compact_structure.py`的JSON Schema是immutable/canonical，固定name与canonical digest；template/schema/parser、actual request与captured manifest digest同源。
- 当前catalog不声明json_schema model；provider-neutral synthetic owner tests覆盖generic transport。OpenAI官方资料不等于当前catalog capability proof。
- old tool-trace-formal@1也进入superseded lifecycle，fresh v2等待Oracle controller；core@2的accepted authority只来自用户2026-08-05 design-contract确认。
- replacement scenarios在observation完整时为`unadjudicated`，证据不完整时为`needs-more-evidence`；两者都不参与current formal verdict。

## Residual risks and ownership

| Residual risk | Classification | Owner / handling |
|---|---|---|
| S3原子vertical migration审查面大 | covered by later approved slice | S3固定内部顺序、未提交diff rollback、两路code review与aggregate deepreview |
| Mimo none下malformed/repair频率 | covered by later approved slice | S4真实Mimo observation；strict parser/repair/fallback保底 |
| Mimo实际structured capability unknown | assigned to later work unit | 有直接provider/model证据后独立catalog WU |
| DeepSeek json_object真实波动/empty content | covered by later approved slice | S4记录actual endpoint/model/options与bounded failure |
| old compact artifact/session replay不兼容 | assigned to later work unit | 若发布要求升级，独立migration WU；本WU不兼容读取 |
| Tool Trace analysis v2仓外consumer | covered by later approved slice | S1 fresh cutover；PR body明确风险，仓外owner自行迁移 |
| replacement scenario Oracle pending | assigned to later work unit | 后续Oracle controller用户裁决；不阻塞implementation/evidence closeout |

没有unclassified residual risk，也没有需要本轮再次询问用户的blocking open question。

## Validation

- 两份review均完整读取：203行与240行。
- Review A F01-F10、Review B 1-7均有controller decision、direct evidence、plan delta与fix status。
- 两份review共6个open questions均已明确关闭。
- plan status已改为`ready-for-plan-rereview`。
- 本fix只涉及两个`docs/gateflow/` artifacts；production/design/registry/finding baseline未修改。
- 未运行pytest/pyright：本gate只修改plan Markdown，不包含代码；已要求后续各slice与aggregate执行完整验证。

## Completion status

- Controller adjudication：`PASS`
- Plan fix：`PASS`
- Plan re-review：`PENDING`
- Implementation：`NOT STARTED`
- Registry mutation：`NOT STARTED`
- Stage/commit/push：`NOT PERFORMED`
