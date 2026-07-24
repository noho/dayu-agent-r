# WU-CTX-01 Reactive Plan Amendment Re-review Controller Adjudication

## 1. Metadata

- work unit：`WU-CTX-01`
- gate：Slice 1 second reactive plan amendment re-review
- reviewed plan：`docs/reviews/wu-ctx-01-plan-codex.md`
- amendment handoff：
  `docs/reviews/wu-ctx-01-slice-1-reactive-plan-amendment-codex.md`
- AgentDS review：`docs/reviews/plan-review-20260724-000414.md`
- AgentMiMo review：`docs/reviews/plan-review-20260724-001004.md`
- design truth：`docs/host/design.md` §25
- decision：`pass`

## 2. Controller conclusion

两路review均确认以下核心contract已自洽且可实施：

1. closed `REACTIVE_POST_COMPACT`将pressure truth与lifecycle action分离；
   4-stage/12-cell中该stage的normal/soft/hard均保留真实pressure并允许recovery
   dispatch。
2. accepted reactive compact不伪造`CONTEXT_COMPACTION_FAILED`、
   `RUN_FAILED`或`RUN_LOST`；新的真实provider overflow继续进入existing bounded
   reactive loop，只有真实compact failure才进入failed fallback owner。
3. accepted compact commit后先完成exact memory catch-up，再在同一recovery start
   transaction内冻结complete candidate、写candidate/manifest并调用existing
   recovery transition；actual request strict-load同一candidate。
4. `run_transition.py`无需修改；两个独立产品修改和3个implementation slices均未
   漂移。

因此第二次plan amendment通过，不开启第三轮plan fix。当前partial production/tests
仍未被接受；恢复Slice 1 implementation后必须完成本artifact中的implementation
checkpoints、focused tests、full pyright与coverage，再进入code review。

## 3. Finding disposition

| finding | disposition | Controller evidence / required action |
| --- | --- | --- |
| DS-F1 manifest缺少`sizing_stage` | rejected-as-plan-finding / implementation checkpoint | revised plan §5.3已把`sizing_stage`列为strict manifest v2字段，complete/unavailable时必填closed stage，compactor proposal为null；production尚未落地正是Slice 1工作。必须实现builder/parser/round-trip/unknown-stage fail-closed。 |
| DS-F2 conjunction gate缺少false-positive tests | accepted-as-test-checkpoint | 增加proactive accepted、catch-up未达标、recovery Attempt已存在、source Attempt未terminal、无matching accepted compact/startup orphan五类negative tests；不得以pressure或字符串猜stage。 |
| DS-F3 bounded loop exhausted路径不够具体 | rejected-as-plan-gap / accepted-as-regression-checkpoint | design §25与plan §6.5/§8.2已冻结真实next overflow、limit exhausted、真实failed fact、tier 4/5 fallback及recovering failure transition的顺序。本Slice不得重写该owner；增加/保持ordering regression，证明只有真实`CONTEXT_COMPACTION_FAILED`可被failure transition消费。 |
| DS-F4 `_pressure_and_decision`映射不具体 | rejected-as-plan-finding / implementation checkpoint | revised plan §5.5已给出12-cell total function与constructor/helper共同验证要求。实现必须修改唯一owner `_pressure_and_decision`，并让`ContextSizingResult.__post_init__`和builder复用它；12-cell全矩阵测试必需。 |
| DS-F7 worker digest mismatch收口 | deferred / existing integrity owner | 本WU只要求strict loader fail closed且禁止二次assembly；不借机重写既有Attempt terminal closeout。若实现发现现有strict-loader异常无法由既有worker错误路径收口，必须stop并以直接证据重开scope。 |
| DS-Q1 compactor proposal usage diagnostic | clarified / non-anchor | compactor proposal manifest保持`not_applicable`，其usage不得进入ordinary anchor、budget decision或public fact。现有internal diagnostic可跳过或标记不可用，但不得新增第二预算真源。 |
| DS-Q2 reactive memory cursor | clarified / existing projection truth | candidate保存exact catch-up完成后由RunInput owner实际读取的memory snapshot cursor；不得使用compact event cursor冒充memory cursor。 |
| MiMo-01 reactive hard仍block | rejected-as-plan-finding / implementation checkpoint | review核对的是未完成production；plan已明确`REACTIVE_POST_COMPACT × hard = ALLOW_DISPATCH`。按DS-F4 checkpoint实现并测试。 |
| MiMo-02 terminated source Attempt loader未定义 | partially accepted / interface frozen below | plan方向正确，但关键transaction-local入口应在实施前由Controller冻结，避免`engine_ingest.py`复制manifest parser或读取当前local config。见§4。 |
| MiMo-03 catch-up failure仅warning | rejected-as-plan-finding / implementation checkpoint | plan §6.4/§8.2和amendment §4已明确未达到exact sequence时零start/零wake并保持`RECOVERING`。production尚未落地；必须补owner test。 |
| MiMo-04 rollback仍用`HostDurableError` | rejected-as-plan-finding / implementation checkpoint | plan §5.6已冻结owner-local private rollback signal并在`run_write`外收敛；当前production是待改对象。低层integrity error仍传播，不得混用。 |
| MiMo-05 candidate缺少`tool_execution_mode` | rejected-as-plan-finding / implementation checkpoint | plan §5.1和amendment §4已明确该字段进入strict candidate projection与digest；production尚未落地。不同mode digest不同、source frozen mode复用均需测试。 |
| MiMo-06 reactive仍用display text | rejected-as-plan-finding / implementation checkpoint | plan明确删除display-text sizing并要求identity-free complete candidate。reactive sizing digest必须与recovery manifest candidate digest配对。 |

## 4. Frozen transaction-local loader checkpoint

`dayu.host.run_input`继续拥有manifest/candidate strict parsing。Slice 1实现必须提供一个
可在caller现有transaction内复用的typed primitive，语义签名固定为：

```python
def load_prepared_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    policy_snapshot: PolicySnapshot,
) -> PreparedRunnerCallCandidate:
    ...
```

具体私有/公开命名可遵循模块惯例，但语义不得改变：

- existing public `load_prepared_runner_call_candidate(...)`必须委托该primitive，
  不能保留第二份manifest/candidate validation；
- `engine_ingest.py`必须从source Run的durable `USER_INPUT_ACCEPTED.
  effective_execution_config`读取冻结execution JSON，复用
  `dayu.host._execution_config_projection.effective_execution_snapshot_from_json`
  还原typed `PolicySnapshot`；不得读取当前local config或复制JSON parser；
- 然后以source `run_id/attempt_id/execution_id`在当前recovery-start transaction内
  strict-load terminated source Attempt candidate；
- candidate payload必须包含`tool_execution_mode`并纳入strict schema和
  `input_snapshot_digest`；post-compact candidate复用source frozen policy、
  tool schemas、disable-tools和tool-execution-mode；
- durable effective config、source manifest、candidate、tool snapshot或任一digest
  缺失/不匹配时fail closed，不创建、不wake recovery Attempt；
- worker仍按新Attempt/execution strict-loadrecovery manifest/candidate并构造actual
  request，不允许二次assembly。

该checkpoint是对revised plan现有“transaction-local strict loader + frozen source
policy/tool inputs”contract的接口收敛，不改变architecture、allowed files或slice边界。

## 5. Required Slice 1 verification

- 4-stage/12-cell pressure/action全矩阵；
- reactive conjunction gate happy path及§3列出的五类false-positive；
- exact catch-up failure零start/零wake、accepted compact保留、Run仍
  `RECOVERING`；
- source manifest/effective config/candidate/tool snapshot/mode缺失或digest不一致均
  fail closed；
- candidate/manifest-before-start、same transaction rollback、并发winner不重复wake；
- worker actual request与recovery sizing消费同一candidate digest；
- reactive hard保留hard pressure但仍start recovery，且零矛盾terminal facts；
- next overflow在limit内进入existing next operation；limit exhausted后只有真实failed
  fact可进入tier 4/5/failure owner；
- `git diff --exit-code -- dayu/host/durable/run_transition.py`；
- affected tests、full pyright、changed production file coverage与README audit。

## 6. Residual risks

| risk | owner / disposition |
| --- | --- |
| partial implementation已有fixture失败且尚未完成reactive path | resumed Slice 1 implementation；不得沿用旧测试结果作为通过证据 |
| terminated source candidate strict-load涉及durable policy重建 | §4 frozen checkpoint + owner tests |
| accepted outcome reconciliation与并发winner race | `engine_ingest.py` owner tests；不得以terminal compensation修复 |
| bounded next-overflow loop可能被本次重构意外回归 | existing lifecycle owner regression；`run_transition.py`零diff |
| full pyright、coverage、README audit尚未完成 | Slice 1 completion gate |

没有blocking question。下一入口是创建accepted reactive plan amendment protected local
commit，然后恢复AgentCodex执行Slice 1 implementation。
