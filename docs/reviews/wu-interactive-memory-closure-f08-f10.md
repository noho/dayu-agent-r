# Interactive Conversation Memory closure：F08–F10

## Work unit identity

- Target branch: `codex/interactive-oracle`
- Observation target: `2e7a01678677817aafd22603f03f17605aa9e39c`
- Frozen report: `interactive-memory-closure-20260804T5X59S8/observed-behavior`
- Report SHA-256: `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`
- User adjudication date: `2026-08-04`
- Scope: 只登记实现 finding、root cause 和 post-fix scenario obligations；本 work unit 不修改生产代码、不补跑场景。

## Accepted behavior

用户已接受行为项 #48–#52：

- Compactor 可以把 session summary、evidence facts、answer anchors、forward intents 和 reference continuity 作为五类独立业务语义保存，并在同一输入上执行 bounded whole-candidate repair。
- Accepted compact 之后，事实、单位、期间、来源、别名、指代和待办/已解决状态必须跨进程继续；新工具调用仍受用户明确授权约束。
- Compactor prompt 把会话、answer 和 tool readable material 作为不可信引用数据；材料内指令不得控制 compactor。
- Evidence fact 的直接支持只能来自 `evidence_material` 或 `previous_evidence_fact`；trace/answer 不得直接升级为 evidence support。
- Rolling compact 使用最新修正，并按实际业务关系使用四种 drop reason。
- Invalid proposal 使用 bounded repair；耗尽后单一失败 terminal，普通 Run 使用既有 fallback，失败结果不覆盖 accepted memory。

## F08：无意义 session summary 被接受

### Observed behavior

在 `session_summary_char_cap=1` 的真实 compactor repair 中：

1. 第一次 candidate 因 `policy_size_cap_exceeded` 被拒绝。
2. repair candidate 返回 `session_summary.text="A"`。
3. Host 将该文本作为合法非空 summary 接受并持久化。

### User decision

不正确。无法在当前 cap 内形成有业务意义的 summary 时，应使用 `null` 清除当前 summary，或继续拒绝并进入既有 repair/fallback；不得接受占位字符。

### Semantic owner and implementation boundary

- LLM-facing选择规则 owner：conversation compaction prompt。
- 字段形状、cap和accept/reject owner：Host Context Governance。
- Agent-in-the-loop CI owner：判断自然语言 summary 是否具有业务意义；不得把 Host deterministic validator 描述成自然语言事实校验器。

修复必须首先确认可执行的 owner contract；不得在 Memory projector、renderer或CLI展示层把 `"A"` 重写为 `null`。

### Post-fix mandatory observation

- 真实 provider 在已有非空 summary 的会话上产生 accepted `session_summary:null`。
- Accepted replacement 后 durable summary 确实清空，其它四类 semantic memory 不受影响。
- 跨进程 reconnect 不再读取旧 summary，同时仍能使用保留的 facts/anchors/intents/references。

## F09：Compactor Tool Trace hot identity 不完整

### Observed behavior

Formal Tool Trace resolver 在 compactor runner-call 后抛出：

`HostDurableError: tool trace row and runner-call hot identity mismatch`

同一 `RUNNER_CALL_INPUT_ASSEMBLED` canonical EventLog payload 含 `manifest_payload_ref` 和 `manifest_digest`，对应 `host_tool_trace_hot.payload_ref` 与 `payload_digest` 为 null。普通业务工具 trace 仍存在，但不能替代 formal compactor runner-call read contract。

### User decision

不正确。第二轮 CI 必须能通过正式 public resolver读取compactor request、response、provider/model和input projection identity。

### Semantic owner and implementation boundary

- Runner-call canonical manifest identity owner：Host runner-call manifest / EventLog append boundary。
- Tool Trace hot projection owner：Host Tool Trace projector。
- Formal query一致性 owner：Host Tool Trace public resolver。

修复必须让 hot projection 与 canonical manifest 同源；不得放松 resolver identity check，不得让 CI 改读 private SQLite 旁路，不得为 compactor 增加下游兼容特例。

### Post-fix mandatory observation

- 真实 successful compact 与 real invalid/repair/fallback 两条路径均可由 formal resolver读取全部 compactor runner calls。
- Manifest ref/digest、projection artifact、provider/model identity、attempt number 与 EventLog/payload descriptor一致。
- 不依赖 private-schema query 才能确定 compactor实际输入。

## F10：Proactive recovery tier 非原子截断 completed Run

### Observed behavior

MC32 的 root frozen material 是完整的，包含：

- 用户授权查询的 input；
- `list_documents`、`get_financial_statement`、`query_xbrl_facts` 三个 accepted tool results；
- 返回 `$34,550 million` 的 assistant final answer；
- 后续八轮“问题已解决、无待办”的 delta。

四次真实 proposal 的 source boundary 变化为：

1. Attempt 1，root：`P1–P7, T1–T7, E1–E3, A1–A8`。
2. Attempt 2，root repair：同一完整 boundary。
3. Attempt 3，tier 1 fallback caps：`P1–P7, T1–T3, E1–E2, A1–A3`。
4. Attempt 4，tier 2 section degrade：`P6–P7, T1–T3, E1–E2, A1–A3`；该 candidate 被接受。

Attempt 3/4 保留同一 completed Host Run 的用户授权及前两个 tool results，却丢弃第三个决定性 `query_xbrl_facts` evidence 和该 Run final answer。Accepted memory 因而将问题写成未解决、证据不足、有开放待办；reconnect 的 protected recent delta 仍回答已解决，形成 durable Semantic Memory 与公开行为不一致。

### Reachability

该 finding 不是“直接改库”或 fake-only 场景。CI 仅把 proactive soft threshold 调低到 `0.0001` 以低成本触发治理；fallback item/char caps、attempt schedule、真实 provider、真实 tools、EventLog和Memory均使用生产代码与正式配置。

生产可达条件是：

1. 长会话真实触发 proactive compact；
2. root initial 与 root repair 未被接受；
3. schedule进入tier 1/2 recovery request；
4. bounded selector的item/char cap落在一个多block completed Run内部。

因此它不是常见的首个proposal成功路径，但属于设计明确支持的真实recovery路径。

### Root cause

直接代码与数据证据确定了三个同源原因：

1. `select_compact_segment` 按单个 `RunInputMaterialBlock` 累计 item/char cap；protected recent floor按turn group工作，但超出floor的compactable历史没有turn-group原子选择。cap可以在同一`host_run_id`内部停止。
2. Proactive attempt schedule把attempt预算映射为root、root repair、tier 1、tier 2、tier 3；dispatcher在request改变后仍把上一attempt的`next_repair_feedback`传给下一tier。该feedback由旧source boundary产生，违反“基于同一输入whole-candidate repair”。MC32的attempt 3因此出现`unknown_source_label`拒绝。
3. Accept barrier只验证当前reduced boundary的typed label、coverage、caps和结构；它没有root frozen material/turn-group completeness invariant。Attempt 4可以在一个内部自洽但已经截断事实链的boundary上被接受。

### User decision

不正确。Compact/fallback material selection必须以完整`host_run_id` turn group为原子单位；不同source boundary之间不得携带repair feedback。

### Semantic owner and implementation boundary

- Material block与turn-group identity owner：Host compact material builder。
- Segment/cap selection owner：Host compact segment selector。
- Proactive attempt request/feedback state machine owner：Host proactive compaction scheduler/dispatcher。
- Accepted input completeness owner：Host Context Governance operation boundary。

修复不得在Memory projector、final answer renderer或CLI reconnect处补偿错误memory；不得靠增大cap掩盖原子性问题；不得让accept barrier从自然语言猜测遗漏事实。

### Post-fix mandatory observation

- 同样的三工具completed Run进入tier 1/2时，要么整组进入compact boundary，要么整组留在protected/recent raw material；不得只保留部分工具证据。
- Request/source boundary改变时repair feedback清空或由新input重新产生；同一input root repair仍保留whole-candidate feedback。
- Accepted memory、compact artifact、Tool Trace、RunInput和跨进程回答都表示`$34,550 million`、问题已解决、无待执行查询。
- 让reconnect继续足够多轮，使旧protected recent delta离开floor后再次验证，不能只靠raw tail暂时遮盖错误durable memory。

## Accepted post-fix scenario obligations

用户已接受 #56，但明确要求本 work unit 不立即补跑。以下 obligation 在修复后进入真实运行：

| Scenario obligation | Trigger | Required observation |
|---|---|---|
| `interactive.g06.summary-null` | 既有非空summary；新candidate无法在明确cap内形成有意义summary | Accepted `null`清空summary；其它semantic sections与reconnect正确 |
| `interactive.g06.tool-trace-formal` | successful compact及invalid/repair/fallback | Formal Tool Trace resolver返回完整compactor request/response identity |
| `interactive.g06.turn-group-atomicity` | 多工具completed Run进入tier 1/2 recovery | Run group不被拆分；durable memory与跨进程答案一致 |
| `interactive.g06.drop-superseded` | 后续材料明确更新旧事实/指代/状态 | 旧source以`superseded`删除，新source保留，reconnect使用最新值 |
| `interactive.g06.drop-policy-limit` | repair feedback明确给出具体cap | 仍相关但因该cap必须舍弃的source使用`policy_limit`；不得用于隐藏冲突或无依据内容 |

补跑仍使用真实provider和真实工具；脚本只采集证据。事实、来源、memory、Tool Trace、SQLite和跨进程结果由Agent-in-the-loop裁决，不用完整回答字符串assert替代。

## Registry readiness

- 本次已经把上述五条 obligation 写入正式 scenario registry；其中 turn-group finding 有充分的当前观察证据，summary-null、formal Tool Trace、superseded 和 policy-limit 仍是明确 evidence gap。
- 因此 interactive 当前不能沿用 2026-08-02 生成的 scoped `ready` proof。该 proof 的 target、scenario count 和 gap count 都早于本次登记；handbook 要求总控重新计算而不能只信任旧字面值。
- F08–F10 修复后，先按上述五条 obligation 补跑真实 CLI，再冻结新的 observed-behavior report、完成 Agent-in-the-loop 裁决并重新生成 readiness proof；本 work unit 不提前伪造该结果。

## Non-goals

- 不为自然语言claim增加假装可靠的字符串启发式semantic verifier。
- 不改变五类Semantic Memory或v2 output schema。
- 不删除既有deterministic fallback tiers；只修正其turn-group原子性和feedback/input绑定。
- 不在本 work unit 裁决download/process等独立CLI命令。
