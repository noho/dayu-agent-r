# Interactive Conversation Memory Closure F08–F10：aggregate deepreview 总控裁决

## Gate identity

- Gate：Gateflow aggregate deepreview → fix → re-review → accepted deepreview checkpoint。
- Work unit：修复 Interactive Conversation Memory closure 的 F08–F10。
- Review range：accepted plan checkpoint `68ba403811fe98835ea93f8c715ca8ed7ba26164` 至 accepted F10 commit
  `fd15b6601a985c538cdbe6a529af99d07c281a05`。
- 总控裁决者：AgentController。
- 裁决原则：逐项核对代码、历史、owner contract、测试和两路 durable artifact；不以“两路一致”代替证据。
- 结论：**PASS**。没有 accepted finding、blocking open question、deferred finding 或未分类 residual risk；无需修改
  production/tests。
- 当前 next entry point：创建 accepted deepreview commit，随后进入 `ready-to-open-draft-PR`。

## Durable review chain

- MiMo aggregate deepreview：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-mimo.md`
- DS aggregate deepreview：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-ds.md`
- Codex fix/audit：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-fix-codex.md`
- MiMo aggregate re-review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-rereview-mimo.md`
- DS aggregate re-review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-rereview-ds.md`

两路 reviewer 均独立检查 F08 prompt/null replacement、F09 canonical manifest/EventLog/hot/public resolver identity、F10
turn-group atomicity、bounded policy、root/transient partition、repair feedback/request binding、durable terminal、LLM-facing
governance isolation、Memory/RunInput/artifact 同源、compat/schema/public-surface drift 和 semantic ownership drift。

## Findings 逐项裁决

### MiMo aggregate：无实质性 finding

**裁决：accepted PASS。** MiMo 对 52 个变更文件、六个 production owner、prompt/hash/manifest 链、十个 owner test
文件和 slice artifacts 做了 cross-slice 检查；其 PASS 结论与当前代码及 owner tests 一致。MiMo 提到的正式 CLI evidence、
真实 provider 和 future constructor 防御均已归类，不是当前 correctness finding。

### DS-A：operation selected-pack proof 未包含 previous_compacted_view

**裁决：`rejected-with-reason`；re-review 状态为“证据失效”。** 机械观察成立，但 finding 的 contract 前提不成立：

1. `previous_compacted_view` 是已接受 durable semantic memory 的 typed pair，不是本轮 raw delta selection；
   `initial_segment_selection` 固定把 previous labels 记入 excluded reasons，不会生成 previous 的
   `SelectedBlockProvenance`。
2. pipeline 的 frozen source snapshot、selected proof 和 root partition 只拥有 raw trace/evidence/answer delta；previous pair
   由 `validate_previous_compacted_view_pair` 和 typed keep/drop transform 独立拥有。
3. `CompactInputV2.source_boundary` 机械包含 previous、trace、evidence、answer 的完整最终 pack；operation 对完整 boundary
   做顺序精确绑定。把 previous 加入 `_validate_operation_selected_pack` 会把 stable previous memory 冒充 selected raw delta，
   并使合法请求出现 proof/pack 数量假阳性。
4. `CompactionRequest` 当前唯一 production 构造点经过 compact pipeline；没有找到能改变 durable semantic set、通过
   provider 前 guard 的正式路径反例。

MiMo 与 DS re-review 均独立确认该裁决。不新增错误 domain 的 provenance 字段、兼容分支或 defense-in-depth fixture。

### DS-B：`_requires_budget_acceptance` 恒为 true

**裁决：`rejected-with-reason`；re-review 状态为“证据失效”。** `git blame` 和历史 commit
`bd1d3e94c571e0b98096e9cfa4d169cefd8003c9` 证明该行为早于本 work unit，并由既有 Host hard-threshold contract 明确要求：
proactive 与 reactive compact 都必须在接受 candidate 前执行 budget acceptance。将其改为 conditional、删除 policy seam 或
描述为 future optional gate 会削弱已冻结的 Host owner contract；不是 F08–F10 引入的 correctness 或 maintainability gap。

### DS-C：manifest recorder 内部创建 `PayloadStore`

**裁决：`rejected-with-reason`；re-review 状态为“证据失效”。** `PayloadStore` 不持有连接、transaction、缓存或 identity
状态；transaction 和 descriptor 均由调用参数决定。同类 `DurableRunnerCallManifestRecorder` 使用相同装配模式。F09 只把同一
manifest descriptor ref/digest 写入 canonical EventLog 和 hot projection，不存在实例身份派生的第二套 truth。增加 optional
DI seam 只会扩大 constructor surface，没有 correctness 收益。

## Cross-slice semantic-owner verdict

| Finding | 唯一 owner | Aggregate verdict |
|---|---|---|
| F08 meaningful summary / null choice | conversation compaction prompt；shape/cap/accept-reject 属 Host Context Governance | 已修复；prompt 自足禁止 placeholder，`null` 继续执行完整 replacement/clear 语义，不引入自然语言 heuristic |
| F09 compactor Tool Trace hot identity | Host runner-call manifest/EventLog append boundary；hot projection 属 Host Tool Trace projector；一致性属 formal resolver | 已修复；canonical row、hot projection 与 returned manifest reference 复用同一 descriptor ref/digest，resolver 保持 fail closed |
| F10 turn-group / budget / feedback binding | Host compact material selector、pipeline frozen snapshot、proactive scheduler 与 operation accept boundary | 已修复；completed Run 原子、strict-prefix bounded、root/transient exact partition、feedback 双 digest 绑定、accepted input 完整性均在 owner boundary 生效 |

没有 Memory projector、renderer、CLI、private SQLite 或测试 fixture 下游补偿；没有兼容 alias/wrapper、loose parser、旧 schema
读取或新增 public schema。

## Validation adjudication

- F08–F10 focused owner suite：`489 passed, 1 skipped`；skip 为 opt-in real provider smoke。
- focused coverage suite：`418 passed, 1 skipped`；六个 production owner 单文件均不低于 80%，合计 85%：
  - `compact_material.py` 86%
  - `compact_pipeline.py` 92%
  - `compaction.py` 84%
  - `compaction_operation.py` 86%
  - `context_governance.py` 89%
  - `dispatch.py` 83%
- Host compaction/Tool Trace/Memory/RunInput/proactive owner suite：`2385 passed, 1 skipped, 6 deselected`。
- 全仓 pytest：总控首轮 `6638 passed, 10 skipped, 6 deselected, 1 failed`；唯一 active-cancel watchdog 时序失败随后
  隔离 6/6 通过，总控第二轮 `6639 passed, 10 skipped, 6 deselected` 完整绿色。DS 另观察到同一区域两个非确定性
  cancel tests，隔离 8/8 通过，且两文件均不在 F08–F10 diff；分类为 work-unit 外的并发观测，不用 workaround 掩盖。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- changed Python files Ruff：通过。
- `python -m compileall -q dayu tests utils`：通过。
- 三份 JSON `python -m json.tool`：通过。
- `git diff --check 68ba4038..fd15b660`：通过。
- 五条正式 CLI scenarios：依任务边界未运行；不把 deterministic tests 冒充真实 provider conformance evidence。

DS re-review 的 coverage 独立复验限制由总控与 MiMo 已完成的 focused coverage evidence 覆盖，不构成缺失验证。

## Frozen baseline integrity

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

三份 digest 与 accepted-plan checkpoint 精确相同，implementation/review 未改写 Oracle baseline。

## Docs decision

本 aggregate loop 不新增 production contract，因此不再次修改 design/README。已接受 slices 中：

- `docs/host/design.md` 冻结 F09 runner-call identity 与 F10 Host owner contract；
- `dayu/host/README.md` 更新 Host compaction/trace/selection 职责；
- `tests/README.md` 更新 owner-test 边界；
- F08 prompt 与权威 workspace manifest/hash consumer 同步更新；
- `docs/engine/design.md`、`dayu/config/README.md`、根 `README.md`、`dayu/README.md` 不命中职责变更，保持不变。

## Residual risk disposition

- 五条正式 CLI scenarios 与 readiness proof：`assigned to later approved work`，owner 为 Oracle 总控；本 work unit 明确禁止
  补跑或重生成。
- active-cancel 非确定性时序：`assigned to later work unit if recurrence`，owner 为 `open_host` active-cancel runtime/test；
  不在本 work unit diff，当前无稳定复现。
- Legacy compactor 若未来不实现 prepared-manifest protocol：`assigned to future implementation owner if that path is selected`；
  当前正式 compactor path 已受 F09 contract 约束，不是当前 residual correctness gap。
- DS-A/B/C：均已 `rejected-with-reason`，不登记为 deferred risk。

没有 unclassified residual risk；没有需要用户决策的新 issue；没有 blocking open question。

## Completion status

Aggregate deepreview loop **PASS**。两路 durable review、Codex fix/audit、两路 durable re-review 和本逐项总控裁决完整；
accepted findings 数量为零，当前 gate 可以创建 accepted deepreview commit。未运行禁止的正式 CLI scenarios，未 push、未更改
PR 190 状态。
