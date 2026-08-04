# Interactive Conversation Memory closure F08–F10：实施计划

## 1. Plan gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Plan 类型：code-generation-ready implementation plan；本 artifact 不修改生产实现。
- Goal confirmation：用户已确认，plan gate 不重复确认。
- 当前分支：`codex/interactive-oracle`。
- 当前观察目标：`2e7a01678677817aafd22603f03f17605aa9e39c`。
- Base ref：`github/main`，解析为 `113ea34d47b95812d79aa31705949bbb46bc6061`；仓库无 `origin`，该 ref 等价于用户指定的 `origin/main`。
- Frozen evidence：`workspace/tmp/interactive-memory-observed-behavior.md` 与 `workspace/tmp/interactive-memory-report-freeze.json`，冻结 report SHA-256 为 `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`。
- Scope finding：`docs/reviews/wu-interactive-memory-closure-f08-f10.md` 中的 F08、F09、F10。
- 工作区隔离：plan gate 开始时已有三份本 work unit frozen baseline：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/wu-interactive-memory-closure-f08-f10.md`。它们必须与本 plan、MiMo/DS 两份 plan review、plan fix、re-review、controller adjudication artifacts 一起进入同一个独立 accepted-plan checkpoint commit；implementation 开始后这三份 baseline 的 SHA-256 永不改变，也不得被覆盖或格式化。

## 2. Goal、动机与非目标

### 2.1 Goal

在不改变 compaction v2 output schema、不改变五类 Semantic Memory 业务模型的前提下，关闭三个已由真实 CLI 证据证明的缺陷：

1. F08：当明确的 summary cap 无法容纳至少一条完整、可独立理解的业务陈述时，模型选择 `session_summary: null`，禁止占位符、孤立字符/标点与截断片段；accepted `null` 作为完整 replacement 清除旧 summary，同时其它四类 memory 正常保留。
2. F09：compactor proposal 的 canonical runner-call manifest EventLog descriptor、Tool Trace hot projection 与 formal resolver 使用同一份 manifest ref/digest 真源。
3. F10：proactive recovery 对完整 `host_run_id` turn group 做原子选择；repair feedback 仅在相同 immutable request digest 与 source-boundary digest 下复用；任何 durable acceptance 必须通过 operation root boundary 的 turn-group 完整性验证。

### 2.2 动机判断

三个问题均真实存在，且严重性没有被高估：

- F08 已真实接受并持久化 `session_summary.text="A"`。Host 只能可靠校验 shape、cap、coverage 等确定性规则，不能用任意自然语言 heuristic 稳定判断摘要“有意义”；因此根修复必须先发生在 LLM-facing 选择规则，memory projector 只验证 replacement 行为。
- F09 的 canonical EventLog hot payload 已含正确 manifest identity，但同一 EventLog row 的 descriptor 字段被写成 `None`，导致 hot projector 机械投影 null，formal resolver 的严格同源校验正确地报错。根因是生产者 append boundary，不是 resolver 过严。
- F10 的 root frozen material 完整，截断发生在 recovery selector；旧 boundary 的 repair feedback 随后被带到新 request；当前 accept barrier 又只验证 reduced boundary 自洽性。三处直接代码行为共同使 completed Run 的部分事实链进入 durable memory，属于生产可达的 semantic corruption，不是测试构造问题。

### 2.3 Non-goals

- 不增加字符数阈值、词表、停用词、语言检测、标点检测或模式匹配等“有意义摘要” heuristic；Host 不承担自然语言意义判定。
- 不修改 `dayu.context_compaction.output.v2` 的字段、类型、枚举或 parser 宽容度。
- 不修改五类 memory 的定义，不新增第六类 memory，不在 projector、renderer、CLI 或 reconnect 层补偿错误语义。
- 不放松 Tool Trace formal resolver 的 identity check，不读取 private SQLite 绕过 public contract。
- 不删除 proactive recovery tiers，不通过增大 char/item cap 掩盖 group 原子性问题。
- 不改变 Engine 的 single-run 职责或 `UI -> Service -> Host -> Engine` 分层。
- implementation 不修改三份 frozen baseline 或 frozen evidence，不运行五条正式 CLI scenarios。
- 不在 plan-fix gate 创建提交、推送分支或做任何远端变更。

## 3. 已读取依据与 owner 判定

计划基于以下完整或相关 owner 级材料：

- 根 `AGENTS.md`。
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`。
- `docs/host/design.md`、`docs/engine/design.md`、`docs/cli_ci.md`。
- `docs/cli_ci_oracles.json` 中 `cli.interactive.core-execution` 的 F08–F10 clauses。
- `docs/cli_ci_scenarios.json` 中五条已冻结 scenario obligations。
- `workspace/tmp/interactive-memory-observed-behavior.md` 与 freeze JSON。
- compactor system/user prompt、Host compaction material/pipeline/operation/governance/dispatcher、runner-call manifest、Tool Trace projector/formal resolver、Memory projector 及相关测试。
- 根 README、`dayu/host/README.md`、`dayu/config/README.md`、`dayu/engine/README.md`、`dayu/README.md`、`tests/README.md` 的更新约束。

唯一语义 owner 如下：

| 语义 | 唯一 owner | 非 owner / 禁止修复处 |
|---|---|---|
| cap 内无法形成至少一条完整、可独立理解的业务陈述时选择 `null` | conversation compaction user prompt | Host 自然语言 heuristic、Memory projector、CLI |
| package prompt bytes 的 workspace 发布摘要 | `docs/cli_init_workspace_manifest_v1.json`，其 raw digest assertion 由 init smoke owner test 消费 | prompt 内容 owner、Host |
| candidate shape、cap、coverage 与 whole replacement acceptance | Host Context Governance | prompt 后处理、renderer |
| accepted `null` 清除 summary 且其它四类按 candidate 投影 | Host Memory projector contract | reconnect fallback、测试 fixture 特例 |
| runner-call canonical manifest ref/digest | compactor proposal manifest recorder 的 EventLog append boundary | Tool Trace resolver、private SQLite query |
| Tool Trace hot row | canonical EventLog 的 Tool Trace projector | compactor adapter 私有旁路 |
| runner-call formal reconstruction | public Tool Trace resolver | CI 直接读表 |
| `host_run_id` group identity | Host compact material builder | LLM、Memory projector |
| group/cap selection | Host compact segment selector | dispatcher 临时拼接、增大 cap |
| request/tier 与 repair feedback 转移 | proactive dispatcher state machine；schedule 只提供冻结 attempt plans | LLM prompt 自行忽略旧 label |
| durable compact acceptance | Context Governance operation root accept boundary | transient reactive pass、artifact writer、Memory projector |

## 4. 当前直接代码根因与数据流

### 4.1 F08 数据流与根因

当前数据流：

`conversation_compaction_user.md` → real provider candidate → strict v2 parser → Context Governance shape/cap/coverage 校验 → `CompactAcceptedTruthV2` → accepted compact artifact/EventLog → Memory projector replacement。

直接根因：prompt 已说明 nullable summary 与 cap，但没有明确要求“若 cap 无法容纳有意义且可独立理解的摘要，则必须返回 null，禁止占位符、孤立字符或截断片段”。Host 的确定性 validator 只看到非空字符串且长度为 1，于是合法地通过 shape/cap 校验。该行为不能通过可靠的 deterministic natural-language validator 修复。

### 4.2 F09 数据流与根因

正确数据流应为：

`DurableCompactorProposalManifestRecorder` 写 manifest payload descriptor → 同一 transaction append `RUNNER_CALL_INPUT_ASSEMBLED` canonical EventLog；hot JSON inline 完整 manifest body，并携带该 descriptor 的 `manifest_payload_ref`/`manifest_digest`；EventLog row descriptor 同时使用完全相同的 ref/digest → Tool Trace projector 机械投影 row → formal resolver 读取 source EventLog + hot row + payload descriptor 并严格核对 identity。

直接根因位于 `dayu/host/compaction_operation.py` 的 `DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest`：manifest descriptor 已成功产生，hot JSON 已 inline manifest body 并携带正确的 `manifest_payload_ref`/`manifest_digest`，但 `EventLogAppendRequest.payload_ref` 与 `payload_digest` 被显式写成 `None`。projector 投影 row descriptor 的 null 是预期机械行为，resolver 报 mismatch 是正确的 fail-closed 行为。

### 4.3 F10 数据流与根因

当前数据流：

canonical EventLog → compact material builder 产生带 `turn_group_id=host_run_id` 的 blocks → `select_compact_segment` → root / tier request plans → dispatcher 按 schedule 调用 compaction operation → transient/aggregate acceptance → compact artifact/EventLog → Memory projector → reconnect RunInput。

三个直接根因：

1. `select_compact_segment` 仅对 recent floor 使用 group-aware protection，预算循环仍逐个 block 累计 char/item cap，因此可在同一 completed Run 的 tool evidence 与 final answer 之间停止。
2. `_execute_proactive_compaction` 在每个 attempt 后无条件把 `next_repair_feedback` 赋给下一 attempt；root repair 同 request 时正确，但 root → tier 或 tier boundary 变化时仍复用旧 labels，违反 feedback 的“同一输入完整重产”语义。
3. `_run_compaction_operation` 会对当前 reduced input 做严格 coverage 校验，但没有 root selection 的完整 group proof；只要 partial boundary 内部自洽，就可能产生 durable accepted truth。

## 5. 目标状态机与核心不变量

### 5.1 Proactive attempt / feedback 状态机

状态保持现有 schedule：

`ROOT → ROOT_REPAIR → TIER_1_FALLBACK_CAPS → TIER_2_SECTION_DEGRADE → TIER_3_DELTA_ONLY → ACCEPT | EXHAUSTED/FALLBACK`

转移规则：

- 每个 attempt plan 冻结 `request_digest` 与 `source_boundary_digest`。
- rejection 产生的 `CompactRepairFeedbackV2` 必须携带这两个 immutable binding digest。
- 下一 attempt 的两个 digest 均与 feedback 完全相同时才可传入；典型合法边是 `ROOT → ROOT_REPAIR`。
- 任一 digest 不同时先清空 feedback，再执行新 request；tier 名称不能替代 digest 比较，避免未来 schedule 重排时产生隐式规则。
- operation 收到非空 feedback 时再次验证双 digest；不匹配视为 caller contract violation，禁止把 feedback 投影给 LLM 或写入 proposal input projection。
- 新 request 自己被拒绝后，可产生绑定新 digest 的新 feedback；不跨 boundary 继承旧 feedback。

### 5.2 Turn-group selection 状态机

selector 严格执行两个阶段，禁止在预算循环中临时回访或补偿 group：

- 阶段一先使用现有 `_sorted_material_blocks` 稳定排序，再归并原子 units：所有 `is_turn_group_material_block(block)` 且具有同一非空 `turn_group_id` 的 blocks 形成一个原子 unit；成员保持 event sequence/sub-index/kind/block-id 顺序；非 turn-group material 各自形成 singleton unit。unit 放置在其首个成员的稳定位置，不按 dict insertion order 或 group id 重排。
- 阶段一同时计算 collective exclusion：依次按 current-input、protected recent floor、already-represented、previous-compacted-view、not-in-segment 的既有优先级检查成员；group 任一成员命中时，全组采用最高优先级的同一 reason，且不进入预算阶段。reason precedence 由模块级常量/严格类型表达并有顺序无关测试，不能依赖遍历偶然性。
- 阶段二仅处理阶段一留下的 eligible units，按 unit 执行现有 prefix budget：以 unit 全部成员的 `size_units` 总和与真实 block 数一次性检查 char/item cap；完整 unit 能放入才整体选择。
- 首个放不下的 eligible unit（包括自身大于 cap 的首组）全部成员标记 `budget_limit`，selection 保持空或保持此前已选 prefix；随后所有 eligible units 也标记 `budget_limit`。不得为了“至少选一项”突破 cap、增大 cap、拆 group 或绕过大组选择后续小组。
- char/item cap 仍是上限：item cap 按真实 block 数计数，char cap 按成员 `size_units` 求和；不得扩大 cap，也不得把 group 算成一个 item。
- 单组本身超过 cap 时不新增 `oversized_group` signal，也不增加 selector/public schema 分支。全部 raw blocks 始终保留在同一个 frozen `source_snapshot.material_blocks` canonical snapshot；tier 1–3 只消费其原子 selection 视图，全部 compact recovery 未接受时，既有 `build_fallback_decision_input` 从完整 snapshot 构造 tier 4/5 raw-window selection 或 fail closed。不得在 selector、pipeline 或 dispatcher 静默删除该组。

### 5.3 Root / transient / durable acceptance 状态机

- `TurnGroupMembership` 是最小独立严格类型，只包含非空 `turn_group_id` 与按 material 顺序排列的非空唯一 `member_block_ids`；selection scope 是 root/transient 闭集严格类型。二者作为 `CompactSegmentSelection` 同一个不可分割 canonical contract 的直接字段，不另建 public schema、root-proof facade 或 God helper。
- Root segment selection 携带完整、稳定排序的 memberships，并把 scope、memberships 与 root binding 纳入 selection canonical serialization/digest。
- Root selection contract 验证每个 group 的全部成员只能处于“全部 selected”或“全部 excluded”之一；selected/excluded 不得交叉，block id 不得跨 group 重复。
- Reactive multi-pass selection 明确标记为 operation-private transient pass，并绑定 root selection digest。它可以为了 provider budget 拆分 root boundary，现有 pass queue 仍须对 root source boundary 构成不重叠、无遗漏的精确 partition。
- transient pass 的 accepted truth 只保存在 operation 内存中，不能写 compact artifact、不能产生 `CONTEXT_COMPACTED`、不能更新 Memory。
- 所有 pass 完成后仍按现有逻辑机械 aggregate，并用 immutable root input 做 coverage/cap revalidation。
- 在返回唯一 `CompactionOperationResult.accepted_truth` 之前，operation 再验证 root selection 的 turn-group membership 与 root boundary 完整性。验证失败复用既有 non-repairable operation failure transport：accepted truth 必须为 `None`、不得携带下一轮 semantic repair feedback；dispatcher 停止该 schedule 并沿既有 terminal permit/fallback 路径只产生一个 aggregate failed terminal，不新增 durable terminal/schema 分支。
- Proactive root/tier request 没有 pass queue，也必须经过同一个 root accept guard；因此即使未来 selector 回归，partial tier boundary 也不能 durable accept。

### 5.4 必须始终成立的不变量

1. `session_summary: null` 是完整 replacement 的合法值；accepted 后旧 summary 不再存在，candidate 中 facts、anchors、intents、references 各自独立投影。
2. Host 不对自然语言“有意义”做任意 heuristic；shape/cap/coverage contract 保持 deterministic。
3. 对每个 compactor runner call：`EventLog row payload_ref/digest == hot payload manifest ref/digest == Tool Trace hot row payload_ref/digest == formal resolver descriptor identity`。
4. 任一 root request 对一个 `host_run_id` 的 turn blocks 要么全选，要么全不选。
5. `selected_item_count <= item_cap` 且 `selected_size_units <= char_cap`；原子 group 不以突破预算换完整性。
6. repair feedback 仅满足 `feedback.request_digest == current_request.digest()` 且 `feedback.source_boundary_digest == current_request.source_boundary_digest()` 时可消费。
7. operation 最多产生一个 aggregate accepted/failed terminal；reactive pass 永不单独 durable accept。
8. accepted compact artifact、EventLog、Memory snapshot、Tool Trace 与 reconnect RunInput 均从 accepted root truth 和 canonical manifest 真源派生。
9. frozen source snapshot 不因 tier 1–3 selection 排除而删减；oversized group 的全部 raw blocks 在 compact recovery 后仍可被既有 tier 4/5 raw-window owner 消费，或由同一 owner fail closed。

## 6. 实施 slices

### Slice F08：summary null 的 LLM-facing 选择规则与 replacement contract

#### Allowed files

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_memory_projection.py`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`

除上述文件外不得修改。`docs/cli_init_workspace_manifest_v1.json` 与 init smoke 常量只承载最终 prompt bytes 的派生 publication truth，不拥有 summary 业务语义。特别禁止修改 v2 parser、Context Governance validator、Memory schema、frozen oracle/scenario/finding/evidence。

#### 实施步骤

1. 在 user prompt 的 `session_summary` 规则与 cap 规则处增加单一、自足、面向模型的动作要求：
   - summary 必须用完整、脱离原会话也可独立理解的业务陈述，表达当前用户目标、已经建立的结论或进展，以及仍影响后续的关键约束或下一步；只写本次会话中实际存在且后续需要的维度；
   - 在明确 cap 内无法形成至少一条完整业务陈述时，必须输出 JSON `null`；
   - 禁止用占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段冒充 summary；
   - `null` 表示完整 replacement 中清除当前 summary，不表示保留旧 summary；
   - 其它四类 semantic sections 仍按本次 candidate 独立输出，不得因 summary 为 null 一并清空。
2. 不加入字符数/词数阈值、语言词表、停用词、正则或 Host semantic acceptance；不使用内部 Python 类型名要求模型推断行为，不改变当前 prompt 已自足定义的 v2 schema。
3. 在 prompt contract test 中断言上述业务判断维度、`null` 条件、禁止项和 replacement 语义均存在，并断言 prompt 仍要求 whole replacement、strict JSON 与 untrusted material 边界。不得新增“句点或其它不合规占位符可被 Host 接受”的 negative acceptance test。
4. 扩展 Memory projector owner test：先建立含非空 summary 的 accepted snapshot，再接受 `session_summary=None` 且同时包含 fact、answer anchor、forward intent、reference continuity 的 replacement；断言 summary 被清除、其它四类逐项存在，重新读取 snapshot 后结果一致。
5. 对最终 prompt raw bytes 计算 SHA-256，只更新 `docs/cli_init_workspace_manifest_v1.json` 中 `config/prompts/scenes/conversation_compaction_user.md` 的唯一 `content_sha256`；再计算 manifest raw SHA-256，并只更新 `tests/cli/test_smoke_cli_init_provider_matrix.py` 的 `FROZEN_MANIFEST_SHA256`。不得改其它 asset entry、目录集合、manifest schema 或动态生成 expected。

#### 错误路径

- provider 仍输出超 cap summary：继续由现有 deterministic cap validator reject，进入既有 bounded repair/fallback。
- provider 违反 prompt 输出 cap 内占位符：Host 不增加自然语言 heuristic，也不新增测试把该不合规输出固化为接受行为；正式 real-provider scenario 由 Agent-in-the-loop 裁决。该剩余不确定性不在下游改写。
- accepted candidate 为 null：Memory projector 必须清除旧 summary，不得 fallback 到 previous summary。

#### F08 完成条件

- prompt 明确 null/no-placeholder/whole-replacement/four-section 规则。
- deterministic unit test 证明 replacement projection。
- publication manifest 中 prompt digest 与最终 raw bytes 一致，manifest raw digest 的唯一 owner test 常量同步且真实 init publication tree 校验通过。
- 不存在新增 heuristic、schema 改动或 compatibility branch。

### Slice F09：compactor runner-call manifest 的 canonical 同源修复

#### Allowed files

- `dayu/host/compaction_operation.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_dispatch_scheduler.py`

F09 不允许修改 `dayu/host/durable/tool_trace.py`、Tool Trace resolver identity 条件、private SQLite helper 或 frozen CLI material。

#### 实施步骤

1. 在 `DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest` 的同一 EventLog append 中：
   - `payload_ref` 使用刚写入的 `manifest_descriptor.payload_ref`；
   - `payload_digest` 使用同一 manifest canonical JSON 得到并已由 descriptor 校验的 `manifest_digest`；
   - hot JSON 继续 inline 完整 manifest body，并携带完全相同的 `manifest_payload_ref`/`manifest_digest`；EventLog row descriptor 改为同一 ref/digest。禁止把 hot body 改成 descriptor-only indirection，禁止二次计算另一份 manifest 或从投影反推。
2. 保持 projection artifact descriptor 独立指向 compactor input projection；不要把 manifest descriptor 与 projection descriptor 混用。
3. 保持 Tool Trace projector 机械投影、formal resolver 严格 equality check 和 payload descriptor 校验不变。
4. 增加真实 recorder 级 integration test：使用 durable recorder 产生 canonical event，catch up Tool Trace，通过 public `read_runner_call_reconstruction_signals_by_run` 与 `resolve_runner_call_projection_from_signal` 读取；断言 event/hot row/resolved manifest 的 ref、digest、compactor input projection ref/digest、operation id、attempt number、provider/model/response identity 可按现有正式 contract 关联。
5. 把 dispatcher 的 compactor trace 测试从“只通过测试私有 SQLite 读取 manifest”扩展为 formal resolver assertion；private query 仅可保留为存储诊断，不得作为通过条件。
6. 覆盖 successful compact 与 invalid→repair/fallback 的多 runner-call 路径：每个 attempt 都有独立 manifest descriptor，formal resolver 均成功，accepted/rejected response identity 与相应 attempt 对齐。

#### 错误路径

- descriptor 写入失败：EventLog 不得提交半条 runner-call fact，保持同一 transaction 回滚。
- event row 与 hot payload identity 不一致：formal resolver 继续抛 `HostDurableError`，测试不得软化。
- compactor proposal invalid 或最终 fallback：此前已执行的 runner calls 仍可 formal reconstruct；失败 terminal 不删除 trace。

#### F09 完成条件

- canonical EventLog row 不再出现 manifest ref/digest 为 null 而 hot payload 非 null 的分裂状态。
- formal resolver tests 使用 public read contract 通过。
- resolver/projector/private SQLite 均无补丁或兼容分支。

### Slice F10：turn-group 原子选择、feedback binding 与 root accept barrier

F09 与 F10 共享 `dayu/host/compaction_operation.py`、`tests/host/test_dispatch_scheduler.py`。实施顺序固定为先 F09、后 F10；F10 从已接受的 F09 checkpoint 继续，不执行 rebase，不回写或拆改 F09 commit。

#### Allowed files

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_llm_compaction.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

不修改 `dayu/engine/**`、Memory projector、RunInput reconnect consumer、v2 output schema、oracle/scenario/finding/evidence。

#### 实施步骤 A：typed root selection proof

1. 在 `dayu/host/compaction.py` 增加最小独立严格类型 `TurnGroupMembership`（`turn_group_id: str`、`member_block_ids: tuple[str, ...]`）与 root/transient 闭集 selection scope；不新建 public schema、`RootSelectionProof` facade、builder hierarchy 或聚合所有职责的 helper。
2. 将 `scope`、`turn_group_memberships` 与 transient-only `root_selection_digest` 作为 `CompactSegmentSelection` 同一不可分割 contract 的直接字段，并进入 canonical serialization/digest。这些字段只属于 Host internal governance，不进入 compactor v2 input/output。
3. `CompactSegmentSelection` constructor 校验 membership 内/跨 group 的 block id 唯一、root/transient 字段组合合法；root selection 中每个 group 必须在 `selected_block_ids` 与 `excluded_reason_codes` 间完整二分，禁止 partial selected/excluded。Transient pass 允许局部分片，但必须绑定 root digest，且不能作为 operation root。
4. 不实现自定义 equality/hash 兼容层；frozen dataclass 的直接字段自然参与当前对象相等性，canonical request/selection digest 由 owner serialization 生成。

#### 实施步骤 B：selector 原子预算

1. 阶段一：在 `dayu/host/compact_material.py` 用模块级私有 helper 消费 `_sorted_material_blocks` 结果，稳定归并原子 units，并为每个 unit 计算 collective exclusion；不使用嵌套函数、loose mapping 或二次不稳定排序。
2. collective exclusion precedence 固定为 current-input → protected recent floor → already-represented → previous-compacted-view → not-in-segment；任一 group member 命中时全组使用最高优先级 reason。测试必须打乱成员输入顺序仍得相同 disposition。
3. 阶段二：仅对 eligible units 按顺序执行 prefix budget；group size 是成员 `size_units` 总和，item count 是真实 block 数。完整 unit 不能同时满足两个 cap 时，所有成员标记 `budget_limit`，selection 为空或保留此前 prefix，并阻止所有后续 eligible units。
4. 首个 group 自身超过 cap 时同样不选；删除现有“首项可为 progress 而越过 size cap”的空间。不得拆组、增 cap、跳过大组或新增 oversized 专用 signal。
5. selector 输出完整 root memberships；selection digest 包含 membership 顺序、selected/excluded disposition、scope 与 root binding，同一输入/政策必得同一 digest。

#### 实施步骤 C：pipeline 区分 root 与 transient pass

1. `build_normal_compact_request_plan` 与每个 tier recovery plan 只接受 root-scope atomic selection。
2. `_single_block_segment_selection` 产生 transient-scope selection，绑定 root selection digest；不得伪装为一个新的完整 root。
3. `build_reactive_pass_queue_plan` 保留现有逐 block provider pass，且 `_operation_pass_requests` 继续验证所有 pass boundary 对 root boundary 是不重叠、无遗漏的 exact partition。
4. 在 request plan 构造时验证 root selection 的 selected block ids 与从同一 `source_snapshot.material_blocks` 投影出的 group proof 一致；发现 partial/missing membership 时在 provider 调用前 fail closed。
5. bounded root selection 不改变 `source_snapshot.material_blocks`。tier 1–3 即使反复将 oversized group 标为 `budget_limit`，完整 raw group 仍在 snapshot 中；compact recovery 耗尽后只能把同一 snapshot 交给现有 tier 4/5 raw-window/fail-closed owner，不能构造删减 snapshot。

#### 实施步骤 D：request/source-bound repair feedback

1. 在 `CompactionRequest` 增加 `source_boundary_digest()`：只对其 immutable `compact_input.source_boundary` 的 canonical JSON 计算 SHA-256；现有 `digest()` 继续代表完整 request。不得使用 tier 名称、attempt number、字符串 label 子集或时间戳代替 digest。
2. `CompactRepairFeedbackV2` 增加非空 `request_digest` 与 `source_boundary_digest`，纳入 internal durable `to_json()`；`_repair_feedback_prompt_json_vnext` 继续只向 LLM 投影 required action 与 issues，治理 digest 不暴露为业务事实。该 typed contract 与 selection 新字段均按全新当前 schema 起库，不增加旧库兼容读取、默认值、optional shim 或旧 fixture 分支。
3. `build_compact_repair_feedback_v2` 必须显式接收当前 request 的两个 digest；operation 中所有 proposal validation、root aggregate validation 与 budget rejection 路径均传入产生该 feedback 的准确 pass/root request。
4. dispatcher 每次 attempt 前比较 feedback binding 与 `attempt_plan.request` 的双 digest：都相同才传递，否则置 `None`。比较逻辑放在单一 typed helper 中，禁止按 `ROOT_REPAIR`/tier 名称硬编码。
5. `_run_compaction_operation` 在准备 proposal 前校验任何 non-null initial feedback 的 binding；不匹配时 provider 不得调用，feedback 不得进入 prompt/input projection。operation 复用既有 non-repairable `PROPOSAL_FAILED` result/diagnostic transport，返回 `accepted_truth=None`、`next_repair_feedback=None`；不得把异常抛出 scheduler 使 Run 崩溃。dispatcher 识别 non-repairable result 后停止 schedule，由现有 `_append_compaction_failed_with_proactive_fallback` 只写一个 failed terminal，再进入既有 fallback dispatch 或 fail closed。

#### 实施步骤 E：operation root accept boundary

1. 增加单一 root-boundary validator，输入为 operation root `CompactionRequest`，验证：root scope、memberships 完整二分、selected ids 与 root compact boundary/provenance 同源、turn-group 不 partial。
2. `_run_compaction_operation` 开始时验证 root request；在最终返回 accepted result 前再次验证同一 immutable root request，形成构造期与 durable accept 前双重防线。
3. 当有 reactive pass queue 时，validator 只针对原始 root request；pass truths 仍为 transient。aggregate candidate 继续经过现有 `accept_compact_candidate_v2(root_input, root_candidate, policy)` 与 hard-budget check，最后才可返回一个 accepted truth。
4. boundary invariant failure 不新增 durable terminal/schema 分支：使用既有 non-repairable operation failure transport并给出 Host boundary diagnostic；不得生成 semantic repair feedback，不得持久化 accepted artifact/Memory，dispatcher 停止 schedule并通过现有 terminal permit形成单一 failed terminal/fallback。禁止复用 `unknown_source_label` 等模型错误伪装 Host boundary 错误。

#### F10 错误路径

- group 缺少 `turn_group_id`：对需要 group identity 的 turn material 在 material builder/selector 输入校验处 fail closed；不得退化为 singleton 猜测。
- group 任一成员 protected/already represented：整组不选；不得在后续 packer 补回部分成员。
- group 超过任一 cap：整组 `budget_limit`，selected totals 不越界；后续 group 不越过该边界；完整 raw group 保留在 frozen snapshot，之后进入既有 raw-window/fail-closed 决策。
- feedback digest mismatch：dispatcher 正常清空；若绕过 dispatcher 直接调用 operation，则 provider 前 defensive fail closed，返回 non-repairable failed result，由 caller 走既有单一 failed terminal/fallback，不抛出导致 Run 崩溃。
- transient pass 失败或 aggregate root validation 失败：不产出 partial durable truth；允许现有 routed repair 在同一 pass request digest/boundary 内继续。
- root atomicity guard 失败：不可模型修复，单一失败 terminal/fallback，accepted artifact 与 Memory 均不改变。

#### F10 完成条件

- 三工具 completed Run 在 tier 1/2 中全入或全不入，item/char caps 仍严格满足。
- oversized group 不进入 compact selection 时完整保留在 canonical source snapshot；所有 compact tiers 耗尽后确实进入既有 tier 4/5 raw-window selection 或 fail closed，只有一个 terminal，且无 silent deletion。
- root repair 保留同源 feedback，任一 request/source boundary 变化均清空。
- reactive transient multi-pass 保留，且只有 aggregate root 能 durable accept。
- Memory/RunInput 无下游补偿代码。

## 7. 测试矩阵

| Slice | 层级 | Case | 关键断言 |
|---|---|---|---|
| F08 | prompt contract | cap 无法容纳至少一条完整业务陈述 | prompt 自足说明目标、结论/进展、约束/下一步等业务维度与 `null` 条件；禁止 placeholder/孤立字符/标点/截断片段，schema 未变 |
| F08 | Memory owner | prior summary + accepted null + 四类其它 memory | summary 清空；facts/anchors/intents/references 全部保留；reload 后相同 |
| F08 | negative | oversize summary | 仍由现有 cap validator reject/repair，不新增 heuristic |
| F08 | publication owner | prompt raw bytes、manifest asset digest、manifest raw digest | 三者逐级同源；真实 init publication tree 与 frozen manifest 精确相等；不动态重写 expected |
| F09 | recorder | actual compactor manifest append | EventLog row 与 hot payload 使用同一 descriptor ref/digest |
| F09 | projector/resolver integration | successful compactor call | public formal resolver 返回 manifest、projection、provider/model/attempt/response 可关联 identity |
| F09 | multi-attempt | invalid → repair，及耗尽/fallback | 每个 call 独立可 reconstruct；失败 terminal 不破坏 trace |
| F09 | adversarial | row/hot identity 人为不一致 | resolver 继续抛 `HostDurableError` |
| F10 | selector/item | cap 落在同一 run 的第三个 tool/final answer 前 | 整组全选或全 `budget_limit`，不 partial |
| F10 | selector/char | 聚合 size 刚好等于 cap、超过 1 unit | 等于可全选；超过则全组排除；总 size 不越界 |
| F10 | selector/prefix | 前组可放、下一大组不可放、后有小组 | 前组全选；大组及后续不选，保持 prefix policy |
| F10 | selector/oversized-first | 首个完整 group 超过 char 或 item cap | selection 为空，全组及后续 eligible units 为 `budget_limit`；cap 不增、无特殊 signal |
| F10 | selector/protection | 同组成员分别命中 recent/protected/already represented，且输入顺序变化 | 阶段一按固定 precedence 得到整组统一 reason；阶段二不再检查该组，结果顺序无关 |
| F10 | selector/identity | turn material 缺 group id | fail closed，不当 singleton |
| F10 | digest | 同输入重复构造；组顺序/成员/政策变化 | 同输入 digest 相同；任一实际 boundary 变化 digest 改变 |
| F10 | pipeline/raw retention | oversized group 在 tier 1–3 均为 `budget_limit` | 每个 selection 不 partial；原始 `source_snapshot.material_blocks` 仍逐项包含完整 raw group |
| F10 | scheduler | root reject → root repair | 双 digest 相同，feedback 保留 |
| F10 | scheduler | root repair → tier 1；tier 1 → section-degraded tier 2 | request 或 source digest 改变即 feedback 为 `None` |
| F10 | operation | 直接注入 mismatch feedback | provider 未调用；返回 non-repairable failed result，无 next feedback、无异常逃逸 |
| F10 | scheduler/defensive | 通过 test seam 让 mismatch feedback 到达 operation | operation fail closed 后 schedule 停止；只写一个 `CONTEXT_COMPACTION_FAILED`，随后走既有 raw-window dispatch 或 fail closed；Run 不因未捕获异常崩溃 |
| F10 | operation | reactive 同组 blocks 跨多个 transient pass | pass 可执行；exact partition 后 aggregate root revalidation；只返回一个 accepted truth |
| F10 | operation | 中间 pass accepted、后续 pass/aggregate 失败 | 无 accepted artifact/Memory，单一 aggregate terminal/fallback |
| F10 | operation | 伪造 partial root selection proof | root guard 阻止 durable acceptance，不产生 semantic repair feedback |
| F10 | fallback owner | oversized group + tier 1–3 全耗尽 | failed terminal 唯一；fallback owner 收到的 canonical snapshot 仍含全组 raw blocks，并明确产生 dispatch 或 fail-closed action，绝不静默删除 |
| F10 | integration | tier accepted complete group | artifact、Memory projection 与 subsequent RunInput 均来自完整 accepted root truth |

测试 fixture 必须表达 owner contract，不得把 partial group 或跨-boundary feedback 固化为合法旧行为。对新增/修改 production 文件测量单文件覆盖率，目标均为至少 80%；若 focused suite 不足，应补 owner-level branch tests，禁止使用 coverage ignore 掩盖。

## 8. 验证顺序与命令

每个 slice 完成后先运行 focused tests；F08/F09/F10 全部完成后运行合并验证。所有 Python 命令均先激活 Python 3.11 venv。

### 8.1 Focused validation

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py tests/host/test_memory_projection.py \
  tests/cli/test_smoke_cli_init_provider_matrix.py -q
python -m json.tool docs/cli_init_workspace_manifest_v1.json >/dev/null
sha256sum dayu/config/prompts/scenes/conversation_compaction_user.md \
  docs/cli_init_workspace_manifest_v1.json
```

```bash
source .venv/bin/activate
pytest tests/host/test_tool_trace_queries.py tests/host/test_dispatch_scheduler.py -q
```

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_llm_compaction.py -q
```

### 8.2 Combined regression、coverage 与 static validation

```bash
source .venv/bin/activate
pytest -q
```

```bash
source .venv/bin/activate
coverage run -m pytest tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_tool_trace_queries.py tests/host/test_llm_compaction.py tests/host/test_memory_projection.py
coverage report --include='dayu/host/compaction.py,dayu/host/compact_material.py,dayu/host/compact_pipeline.py,dayu/host/context_governance.py,dayu/host/compaction_operation.py,dayu/host/dispatch.py'
```

coverage report 中每个新增或修改的 production Python 文件都必须单文件达到至少 80%；若任一文件低于 80%，先补 owner-level branch tests，禁止用 omit、pragma 或合并平均值掩盖。

```bash
source .venv/bin/activate
python -m ruff check dayu tests utils
python -m ruff format --check dayu tests utils
python -m compileall -q dayu tests utils
python -m json.tool docs/cli_init_workspace_manifest_v1.json >/dev/null
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
```

```bash
source .venv/bin/activate
python -m pyright
```

```bash
git diff --check
git status --short
```

accepted-plan checkpoint 前记录三份 frozen baseline 的 SHA-256，implementation 每个 slice 后及全部完成后逐一比对；三者 digest 必须与 checkpoint 完全一致：

- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`

另外继续核对只读 frozen evidence：

- `workspace/tmp/interactive-memory-observed-behavior.md`
- `workspace/tmp/interactive-memory-report-freeze.json`

本 work unit 明确不运行以下五条正式 CLI scenarios：

- `interactive.g06.summary-null`
- `interactive.g06.tool-trace-formal`
- `interactive.g06.turn-group-atomicity`
- `interactive.g06.drop-superseded`
- `interactive.g06.drop-policy-limit`

它们属于实现、review、deepreview 完成后的独立真实 evidence/readiness 阶段；本次不得提前改写 evidence status。

## 9. README / design 触发判定

| 文档 | 判定 | 计划动作 |
|---|---|---|
| `docs/host/design.md` | 触发 | 更新稳定设计真相：完整 turn-group 原子 root selection、双 digest feedback binding、transient pass 与 root durable accept boundary。F09 既有 manifest 同源设计不改语义，只需确认表述与实现一致。 |
| `dayu/host/README.md` | 触发 | 实现完成后更新当前实现事实：group-atomic recovery、feedback binding、compactor canonical manifest 可被 formal resolver 读取。 |
| `tests/README.md` | 触发 | 当前文档已拥有 frozen publication manifest 与 Host 测试分层；F08 digest 同步不改变其既有 manifest 说明，F10 新增稳定的 selector/operation/terminal owner coverage 后按现状补充对应测试职责，不罗列单个测试名。 |
| `dayu/config/README.md` | 已读取开篇职责并判定不更新 | 该 README 只拥有默认配置、workspace 覆盖关系与 prompts 目录职责；F08 只修改一个 scene prompt 的业务判断文本，并同步派生 publication digest，不改变配置层级、装载、覆盖、schema 或 prompts 目录职责，因此 prompt 内容不属于该 README 的写作所有权。 |
| `dayu/engine/README.md`、`docs/engine/design.md` | 已检查，不触发 | Engine 无代码、协议或职责变化。 |
| `dayu/README.md` | 已检查，不触发 | 分层关系与装配边界不变。 |
| 根 `README.md` | 已检查，不触发 | 用户可见安装、CLI 参数、入口、输出通道、工作区位置和排障流程均不变。 |
| `docs/cli_ci.md` | 已检查，不触发 | 正式 scenario 执行与 evidence 冻结规则不变，本 work unit 不运行场景。 |

文档只在对应实现 slice 通过测试后更新，禁止先把未实现行为写成“当前已支持”。

## 10. 提交边界

本 fix gate 不创建提交。plan re-review 与 controller adjudication 通过后，accepted-plan checkpoint 必须是一个单一、独立 commit；不得先拆出 baseline commit、plan commit 或 review commit，也不得把 implementation 混入。该 commit 精确包含：

1. 三份 frozen baseline：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/wu-interactive-memory-closure-f08-f10.md`。
2. 本 plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
3. 两路 plan review：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-mimo.md`、`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-ds.md`。
4. plan fix：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-fix-codex.md`。
5. 随后产生并通过的 plan re-review 与 controller adjudication artifacts。

提交信息固定使用 `gateflow: accept plan for interactive-memory-closure-f08-f10`。commit 前以精确 pathspec 核对上述 artifacts，并记录三份 baseline digest；implementation 后任何 commit 都不得改变这三个 digest。

accepted-plan checkpoint 之后的 implementation 提交边界：

1. F08：prompt + publication manifest/digest owner test + prompt contract test + Memory replacement owner test；建议提交信息 `gateflow: accept interactive-memory-closure-f08-f10 F08`。
2. F09：canonical EventLog descriptor 修复 + formal Tool Trace integration tests；必须先于 F10；建议提交信息 `gateflow: accept interactive-memory-closure-f08-f10 F09`。
3. F10：typed selection/feedback contract、selector/pipeline/operation/dispatcher 修复、owner tests 与触发的 Host/test docs；直接基于 F09 checkpoint 继续，禁止 rebase；建议提交信息 `gateflow: accept interactive-memory-closure-f08-f10 F10`。
4. Review/deepreview 修复如跨 slice，应按 finding 的真实 owner 落回对应 slice；不得以一个 mixed “cleanup” commit 隐藏语义边界。

每次提交前必须使用精确 pathspec 核对 staged files；不得使用宽泛 staging 纳入无关 dirty changes。

## 11. Adversarial review checklist

- 是否有人尝试用 `len(text) <= 1`、ASCII、词表或正则把 F08 伪装成 deterministic semantic validation？若是，拒绝。
- 是否新增了 Host 接受句点/占位符的 negative test？若是，拒绝；它会把明确不合规的 LLM 输出固化为可接受 contract。
- `null` 是否真正删除旧 summary，还是 presentation 显示空但 durable snapshot 仍保留？必须以后者 owner test 判定。
- F09 是否只让 synthetic projector test 通过，却没有实际 recorder → EventLog → projector → formal resolver 链路？若是，不接受。
- F09 是否通过放松 mismatch check、补默认 ref/digest 或 private table join 通过？若是，不接受。
- group selector 是否把一个 group 计作一个 item，从而静默放大 item cap？若是，不接受。
- selector 是否在大组放不下后跳过它选择更晚小组，改变 prefix policy？若是，必须有设计证据；本计划不允许。
- oversized group 是否触发专用 signal、新 cap、group 拆分或从 source snapshot 删除？任一发生都拒绝；它只能保持 `budget_limit` 并进入既有 raw-window/fail-closed owner。
- already-represented/protected 状态是否导致同组成员不同 disposition？若是，不接受。
- feedback 是否按 stage 名而非双 digest 绑定？若是，不接受。
- repair feedback 的治理 digest 是否被投影进 LLM prompt、被模型当业务事实？若是，不接受。
- reactive pass 是否因 root atomic contract 被错误禁止，或某个 transient truth 被直接持久化？两者均不接受。
- operation guard 是否只验证 reduced tier boundary 内部 coverage，而没有验证 root group proof？若是，F10 未关闭。
- feedback mismatch 是否以异常逃逸 scheduler、造成 Run 崩溃或产生多个 terminal？若是，不接受；必须是 operation defensive failed result + 既有单一 terminal/fallback。
- accepted artifact、Memory、Tool Trace 与 RunInput 是否仍可能各自重算同一事实？必须保持 canonical EventLog/accepted truth 单源投影。

## 12. Residual risks 与 blocking findings

### Residual risks

- F08 的“自然语言有意义”按设计仍需 real-provider Agent-in-the-loop 观察；deterministic tests 只能证明 prompt contract 与 replacement projection，不能替代后续正式 scenario。
- Group-atomic policy 可能使超大 completed Run 在 fallback cap 下完全不进入 compactor，从而更早进入既有 raw-window/fail-closed 路径；这是保持事实链完整与严格 bounded policy 的预期取舍。owner tests 必须证明 canonical snapshot 保留全组、fallback decision 显式、terminal 唯一，不能只断言 selector 不选。
- 给 selection 与 repair feedback 增加 typed canonical fields 会自然改变新 request/selection digest。该变更按全新当前 schema 起库，不提供旧库兼容、旧记录重解析或 digest fallback；fixture 必须调用 production owner helper 生成当前 digest，禁止硬编码旧值。
- 历史 EventLog 中已写入的 request/selection digest 是产生时的 immutable fact，新代码不得加载历史 payload 后重算并覆盖或要求其等于当前版本 digest。运行时 binding 只比较本次冻结 schedule/current request 与由该 request 产生的 feedback；不跨代码版本验证历史 digest。
- F09 的真实 provider/model/response identity 最终仍需后续 formal CLI scenario 证明；本 work unit 只提供可重复的 public resolver integration contract。

### Blocking findings

当前无阻塞 plan-fix finding。总控裁决已全部映射到 owner、allowed files、状态机与验证命令；下一 gate 是独立 plan re-review，未通过 re-review/controller adjudication 与单一 accepted-plan checkpoint 前不得进入 implementation。
