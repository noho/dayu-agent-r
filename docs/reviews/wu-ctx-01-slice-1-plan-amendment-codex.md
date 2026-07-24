# WU-CTX-01 Slice 1 Plan Amendment Handoff

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`plan amendment`
- lane：`AgentCodex plan/fix`
- Controller truth：
  `docs/reviews/wu-ctx-01-slice-1-stop-controller-adjudication.md`
- decision：`complete / ready for dual plan re-review`
- implementation status：`not accepted`
- blocking questions：`None`
- next entry point：只交回Controller进入AgentMiMo / AgentDS双路
  `plan re-review`

本gate没有继续implementation，没有修改production、tests、control doc或其它既有
artifact，没有commit、push或创建PR。worktree中的Slice 1 partial code/tests与
Controller改动全部保留；re-review pass并形成新的accepted-plan-amendment protected
local commit前不得恢复implementation。

## 1. First-principles judgment

blocker成立且严重性评估准确。

accepted compact的业务作用不是“额外增加一份summary”，而是让accepted semantic view
代表其覆盖的旧raw history；后续ordinary input只能继续携带真实post-compact delta、
未被本次selected compact覆盖的protected raw与current input。当前实现只更新五类
semantic memory，却没有把persisted compact coverage投影到selected recent window，
所以exact candidate在compact前后不收缩。这个问题改变实际LLM-facing memory，不能由
estimator fixture、threshold、`run_input.py`下游过滤或第二次compact补救。

soft pressure也不等于所有stage都必须compact。soft的action语义是ordinary阶段先尝试
一次compact；同一snapshot已经完成或耗尽唯一proactive operation后，
post-compact/fallback soft必须允许dispatch并如实保留soft pressure。hard仍是不可
dispatch边界，必须显式terminal fail closed。

因此修复边界必须同时落在：

1. compact payload typed source boundary；
2. Conversation Memory selected recent projection；
3. `ContextSizingResult` stage-aware action与Host terminal flow。

这三点是Slice 1 complete-candidate foundation的owner修正，不构成第三项产品修改，也
不改变固定3 slices。

## 2. Direct production evidence

| evidence | observed truth | amendment consequence |
| --- | --- | --- |
| `dayu/host/compact_payload.py::source_boundary_refs` | producer按顺序写`request.current_input_ref`，再写去重material/evidence/fact refs | 第一个ref是current input boundary，其余才是covered refs |
| `dayu/host/compact_payload.py::ContextCompactedSemanticPayload` / `parse_context_compacted_semantic_payload` | typed semantic view只恢复candidate/evidence/artifact，没有读取persisted`source_boundary_refs` | strict parser必须成为raw list唯一reader并显式投影`current_input_ref`/`compacted_source_refs` |
| `dayu/host/memory.py::project_conversation_memory_event` | accepted compact更新summary/facts/anchors/intents/reference continuity与latest compact ref，原样保留selected window | memory owner必须删除covered older raw并同源重建recent evidence |
| `dayu/host/run_input.py::_memory_messages` | 渲染snapshot selected window；protected raw-tail path已有source-ref/content-digest dedupe | RunInput只消费修正后的typed view，禁止新增coverage filter |
| `dayu/host/context_budget.py::ContextSizingResult` / `_pressure_and_decision` | partial implementation把soft pressure在全部stage固定映射为compact action | pressure与action必须分离；action消费stage |
| `dayu/host/dispatch.py::_prepare_and_commit_start_in_transaction` | post-compact/fallback只在decision allow时start，soft/hard都普通返回`None` | soft改为allow；hard返回closed terminal outcome并写Run failure |

这些证据与Controller裁决逻辑/数据同源；没有发现需要修改Engine、Service public
contract、durable run transition、通用transaction runner或Issue #119 correlation的
新证据。

## 3. Design amendment

`docs/host/design.md`只补了两处必要设计真源，没有重写其它架构：

1. §24.4 Snapshot Typed Schema：
   - `source_boundary_refs`非空、非空字符串、全局唯一；
   - 第一项typed为`current_input_ref`；
   - 其余typed为`compacted_source_refs`，允许为空；
   - Conversation Memory按typed covered refs删除selected recent older raw；
   - current input、未covered protected raw与后续新delta保留；
   - recent evidence、incremental/rebuild/inline repair/persisted reload同源；
   - RunInput禁止再实现compact coverage filter。
2. §25 Usage-Anchored Adaptive Context Sizing：
   - pressure只由prediction与thresholds派生；
   - ordinary normal/soft/hard为allow/compact/block；
   - post-compact与dispatch-fallback normal/soft/hard为allow/allow/block；
   - soft pressure不得伪装normal；
   - hard必须显式fail closed；
   - 同一snapshot不得启动第二次proactive operation。

## 4. Plan amendment

`docs/reviews/wu-ctx-01-plan-codex.md`同步修订：

- §0：gate、Controller truth、三文件写入范围、partial implementation
  `not accepted`与双路re-review前置条件。
- §1：goal/success明确compact boundary修正属于Slice 1 foundation，不改变两个独立
  修改；新增typed coverage、stage matrix、去重与真实size effect成功信号。
- §2：补compact payload、memory、RunInput与stage/action直接production证据，并把
  root cause收敛到typed coverage与stage action owner。
- §3：补in-scope/non-goal/不过度设计边界，明确禁止RunInput filter、raw-list
  consumer parsing与第二次proactive operation。
- §4：新增compact coverage、selected recent与stage-aware action semantic owners。
- §5.5：冻结pressure/action 9-cell matrix。
- §5.8：冻结exact persisted/typed contract、memory过滤顺序、repair/rebuild一致性、
  raw-tail去重与size下降/不伪造下降规则。
- §6.3-§6.5：同步post-compact/fallback flow、closed terminal outcome与同snapshot
  operation不变量。
- §7：扩充affected production/tests与consumer audit。
- §8.2：扩充Slice 1 objective、allowed scope、exact changes、owner assertions、
  validation、completion与stop conditions；Slice 2同步canonical fact对stage-aware
  action的消费。
- §9：补source boundary、memory、9-cell action、size effect test matrix与static
  audits。
- §11：按README自身职责改为每slice先读约束、同slice审计/更新，final aggregate
  audit。
- §12：分类coverage、去重、soft重复compact、hard silent accepted与partial
  implementation风险。
- §14-§15：逐项记录accepted blocker disposition与只交回双路plan re-review的
  next entry point。

## 5. Exact typed contract

persisted producer contract保持：

```text
source_boundary_refs =
  unique_in_order(
    current_input_ref,
    *selected_compact_material_refs,
    *accepted_evidence_and_fact_provenance_refs,
  )
```

typed semantic view新增：

```text
current_input_ref: str
compacted_source_refs: tuple[str, ...]
```

strict parser是唯一允许读取raw list的位置。consumer不得索引raw list、按prefix猜
角色或按sequence/time推断coverage。只有`[current_input_ref]`合法表示“本次没有covered
material”，不得因此删除任何selected recent item。

memory projection逐item使用`event_id + source_refs`作为canonical source set：

- 命中current input：保留；
- 否则命中任一covered ref：删除；
- 否则：保留；
- 最后执行既有bounded policy并从结果重建recent evidence。

该规则保证covered older raw删除、current input保留、protected excluded raw保留、
new delta保留，并让full rebuild、incremental、repair与reload复用一个owner。

## 6. Stage-aware action与stop-condition resolution

| stage | normal | soft | hard |
| --- | --- | --- | --- |
| `ORDINARY` | allow dispatch | one proactive compact operation | block + terminal fail closed |
| `POST_COMPACT` | allow dispatch | allow dispatch；pressure仍soft | block + terminal fail closed |
| `DISPATCH_FALLBACK` | allow dispatch | allow dispatch；pressure仍soft | block + fallback/failure terminal closeout |

原stop conditions逐项收敛：

| stop condition | resolution |
| --- | --- |
| post-compact candidate无法收缩 | typed compact coverage进入memory owner；有covered material时删除covered raw |
| 修复需要修改Slice 1 allowlist外`memory.py` | Controller已扩充owner scope；plan同步新增 |
| 修复会改变LLM-facing memory | 由existing design truth明确授权，只在memory owner修正，不在RunInput补偿 |
| protected raw与covered raw边界不清 | `compacted_source_refs`只表示selected compact覆盖；未命中refs的protected raw保留 |
| post-compact soft/hard普通无dispatch | soft按stage allow；hard走closed terminal outcome |
| 同snapshot是否再次compact不清 | ordinary最多一条operation；post-compact/fallback不启动第二条 |

新的stop conditions只保留owner真源再次失效、canonical refs无法唯一表达coverage、
existing Run failure owner无法收口hard、或需要allowlist外production修改等真正架构
阻断项。

## 7. Allowed scope delta

保持两个独立修改与3 slices不变。Slice 1相对原accepted plan新增：

**Production**

- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`

**Tests**

- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_memory_repair.py`

**README audit/update allowance**

- `dayu/host/README.md`
- `tests/README.md`

owner tests必须覆盖：

- covered older user/assistant/evidence raw删除；
- current input只保留/渲染一次；
- 未被selected compact覆盖的protected raw保留；
- compact后新delta保留；
- recent evidence同源；
- rebuild/incremental/inline repair/persisted reload一致；
- memory selected与ordinary raw tail按source ref/content digest去重；
- 确有covered material时post-compact exact size下降；
- 无covered material时不伪造下降；
- 9-cell stage matrix、soft pressure保真、hard terminal closeout与同snapshot单operation。

## 8. Finding disposition

| finding | disposition | evidence |
| --- | --- | --- |
| accepted blocker：compact coverage owner缺失 | `fixed in plan` | design §24.4；plan §4/§5.8/§8.2/§9 |
| accepted blocker：stage-independent pressure/action | `fixed in plan` | design §25；plan §5.5/§6.5/§8.2-§8.3 |
| partial implementation可否进入review | `rejected` | 未完成focused tests/full pyright/coverage；Controller明确`not accepted` |
| 是否需要RunInput临时filter | `rejected-with-reason` | 违反Conversation Memory唯一owner并制造第二真源 |
| 是否需要第二次proactive compact | `rejected-with-reason` | 违反同snapshot单operation不变量 |

## 9. Validation

本gate按用户要求只做Markdown与scope静态验证：

- 完整读取implementation handoff、Controller adjudication、原plan、design §24-§25
  与必要production直接证据。
- `git diff --check`：通过。
- Markdown code fence计数均为偶数：design=`182`、plan=`54`、amendment=`4`。
- implementation slices heading audit：仍且仅有Slice 1/2/3。
- 新增allowlist中的
  `test_context_compact_events.py`、`test_memory_projection.py`、
  `test_memory_repair.py`均为现有owner test文件。
- heading/contract关键字审计命中typed current/covered refs、3-stage action、
  partial implementation disposition与双路re-review入口。
- 结束scope对账确认：本gate新增写入只涉及design、plan与本amendment artifact；
  开始基线中的production/tests/control与两个既有stop artifacts均未继续编辑。
- 未运行pytest、coverage、代码smoke或pyright。
- 未把当前partial implementation的历史测试结果当作amendment通过证据。

## 10. Residual risks

| risk | classification |
| --- | --- |
| 当前partial implementation仍可能有fixture migration、rollback、manifest matrix等未完成项 | resumed Slice 1 owner；plan re-review前保持not accepted |
| typed covered refs若producer选择语义与当前直接证据不一致 | Slice 1 stop condition；不得在consumer补偿 |
| post-compact exact hard的具体terminal reason/error code需与既有lifecycle常量对齐 | Slice 1 implementation detail，owner/transition已冻结；不得改变public contract |
| README实际内容是否命中目标读者职责 | 每slice先读目标README约束后裁决；不机械同步 |

没有unclassified residual risk，没有blocking question。

## 11. Controller handoff

- amendment artifact：本文件
- plan artifact：`docs/reviews/wu-ctx-01-plan-codex.md`
- design truth：`docs/host/design.md` §24.4、§25
- current decision：`ready for dual plan re-review`
- next：Controller派发AgentMiMo / AgentDS双路plan re-review
- forbidden next：直接恢复implementation、code review、commit、push或PR
