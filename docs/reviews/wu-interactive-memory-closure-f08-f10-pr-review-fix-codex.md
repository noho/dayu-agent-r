# Interactive Conversation Memory closure F08–F10：PR review fix/audit

## Gate identity

- Gate：Gateflow `PR review -> fix/audit -> re-review handoff`。
- Work unit：修复 Interactive Conversation Memory closure F08–F10。
- PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)，title=`fix(cli): close interactive conformance gaps`。
- Reviewed remote head：`72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`。
- Base：`main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`。
- 执行者：AgentCodex。
- Review inputs：
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-mimo.md`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-ds.md`
- Frozen contract：`docs/reviews/wu-interactive-memory-closure-f08-f10.md`。
- Deepreview artifact：`docs/reviews/pr-190-review-20260804-201303.md`。
- Parallel review coverage：无；本 gate 由 AgentCodex 沿代码、测试、frozen contract 和 PR external state 独立复核。
- Completion status：**fix/audit pass；停在 AgentMiMo / AgentDS 两路 PR re-review handoff**。
- 边界：未 commit、未 push、未运行五条正式 CLI scenarios，未修改三份 frozen baseline，未评论/approve/mark ready/merge/request reviewers。

## 第一性原理判断

本 work unit 的三个原始动机均成立：F08 的真实模型曾在明确 cap 下输出占位字符，F09 的 canonical row 与 hot
identity 曾分裂，F10 的 recovery tier 曾在 completed Host Run 内截断事实链。当前 PR review fix/audit 的判断标准不是
“两路 reviewer 都写了 PASS”，而是当前正式 producer/call path 是否仍存在能绕过 owner guard、改变 durable semantic set、
或使 Memory / Tool Trace / accepted truth 分叉的可达反例。

独立复核结论是：F08–F10 production/tests 没有当前 owner-level correctness gap；DS 四个 open questions 均不构成当前代码
finding，其中 F09 所称 E2E 缺失被现有真实 scheduler 集成测试直接证伪。唯一 accepted finding 是 PR body 与真实 remote head
漂移；该 finding 已通过只修改 PR body 的最小 external-state fix 关闭。

## Findings

### PR-BODY-01-已修复-[中]-draft PR summary 与真实 head 和当前 work unit 漂移

- **裁决**：`accepted`，re-review 状态=`已修复`。
- **入口/函数**：GitHub PR #190 body 的 `Summary`、`Exact-head validation`、`Review status`。
- **文件(行号)**：GitHub external state；不对应仓库文件。
- **输入场景**：reviewed remote head 已推进到 `72b7f145...`，且累计 PR 已包含 F08–F10。
- **实际分支**：body 仍把 accepted implementation target 写成 `58aeb7b...`，测试数字和 review status 只描述 F01–F07。
- **预期行为**：Gateflow draft PR summary 必须匹配真实 head；应保留累计 F01–F07 evidence，并准确写出 F08–F10 修复、验证边界和五条未运行 scenario obligations。
- **实际行为**：Summary 泛称 F01–F13，但没有给出 F08–F10 的 owner 语义；读者会把旧 exact-head 和旧验证数字误当作当前 head 证据。
- **直接证据**：写入前 `gh pr view 190 --json body` 返回 `Accepted PR-review implementation target: 58aeb7b...`；同次 metadata 查询返回 `headRefOid=72b7f145...`。
- **影响**：draft PR 的审计/验证边界失真，可能把历史 F01–F07 evidence 误投影为当前 F08–F10 exact-head 或正式 CLI conformance。
- **修复**：已用 `gh pr edit 190 --body ...` 更新 body；保留 F01–F07 bundle、digest、测试和 real-provider 历史信息，新增 F08–F10 语义、当前 head、当前/accepted validation、三份 frozen digest、五条未运行 scenarios 和两路 re-review handoff。
- **验证点**：写后 `gh pr view 190` 确认 body SHA-256 为 `ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8`；title、OPEN/draft、base/head、merge state、reviewDecision 均未改变。
- **修复风险（低/中/高）**：低；仅 external PR body，无代码、schema、branch 或 review state 修改。
- **严重程度（低/中/高/严重）**：中。

### Production / tests

未发现需要修改 production 或 tests 的实质性问题。

## 两路 review findings / conclusions 独立裁决

### MiMo：F08–F10 PASS

- **裁决**：`accepted` 作为证据结论，不以 PASS 字样本身作为理由。
- **F08 证据**：`conversation_compaction_user.md:34-37` 自足规定完整业务陈述、明确 cap 下 `null`、禁止占位/孤立字符/孤立标点/截断片段；frozen contract `:39-43` 把自然语言选择规则交给 prompt、shape/cap/accept-reject 交给 Host、真实语义观察交给 Agent-in-the-loop CI。`memory.py` 的 accepted-event projector 对 `None` 返回空 summary，并独立投影其它四类语义。
- **F09 证据**：`compaction_operation.py:258-345` 在同一 transaction 先写 projection descriptor、再写 manifest descriptor，并把同一 `manifest_descriptor.payload_ref` / `manifest_digest` 同时写入 hot payload、EventLog row 和 returned reference；formal resolver mismatch check 未放松。
- **F10 证据**：selector 以 `_AtomicMaterialUnit` 做 group 级 collective exclusion 和 strict-prefix budget；pipeline 从 frozen source snapshot 重建 exact provenance；operation 在 provider 前和 accepted truth 返回前验证 root，dispatcher 以 request/source-boundary 双 digest 过滤 feedback。
- **状态**：无 accepted code finding；结论维持 PASS。

### DS：总体 PASS

- **裁决**：`accepted` 作为证据结论。
- **理由**：DS 对 F08 prompt/null replacement、F09 manifest/hot/resolver、F10 group atomicity/feedback/root barrier 的主要数据链判断与当前代码一致；但其四个 open questions 与部分 residual statements 需逐项重新分类，见下文。

## DS 四个 Open Questions 逐项裁决

### DS-OQ-1：单标点 summary 是否构成当前 contract gap

- **裁决**：`rejected-with-reason`。
- **事实**：strict parser/Host deterministic governance 确实会接受 cap 内非空 `"."`；该机械观察成立。
- **拒绝理由**：frozen contract `:39-43`、accepted plan `:144-145,166-184,457-458` 明确把“自然语言是否形成完整业务陈述”的 owner 放在 prompt 与后续 Agent-in-the-loop observation，并明确禁止用长度、ASCII、词表、正则或句点特例把 Host 变成 semantic heuristic verifier。当前 prompt 已明确禁止孤立标点；production Host 不拥有第二套自然语言真值。
- **边界**：不得新增 punctuation fallback、parser 特例或“句点可接受”的 Host negative contract test。真实 provider 是否遵守该规则由后续 `interactive.g06.summary-null` 观察，不是本 gate 的 deterministic owner gap。
- **状态**：证据不支持当前 code finding；保留为后续 real-provider evidence obligation。

### DS-OQ-2：F09 是否缺 recorder → catch_up → formal public resolver owner E2E

- **裁决**：`rejected-with-reason`；DS 的“缺失”前提被代码测试直接证伪。
- **producer 证据**：`dispatch.py:2533-2537` 为真实 scheduler 装配 `DurableCompactorProposalManifestRecorder`；测试只 fake provider proposal，不 fake durable recorder/projector/resolver。
- **E2E 证据**：`tests/host/test_dispatch_scheduler.py:11756-11856` 的 `_resolve_and_assert_compactor_calls` 明确执行：
  `catch_up_tool_trace_projection` → `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal`，并逐 attempt 核对 source EventLog row、hot ref/digest、manifest descriptor、projection payload、provider/model、operation id、attempt number 和 response identity。
- **路径覆盖**：
  - `test_multi_turn_proactive_compact_feeds_subsequent_run_input`：single success；
  - `test_proactive_compaction_retries_quality_rejection_before_accept`：invalid → repair → success；
  - `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback`：四次 invalid 后 exhausted fallback；
  - `test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch`：row/hot mismatch fail closed。
- **状态**：owner-level E2E 已存在并在本 gate 重跑通过，无需补测试。

### DS-OQ-3：`CompactRepairFeedbackV2.to_json()` 是否会进入 LLM path

- **裁决**：`rejected-with-reason`。
- **精确事实**：`to_json()` 会进入 Host-internal `compactor_input_projection` durable Tool Trace artifact（`llm_compaction.py:604-625`），因此“完全没有调用”不成立；但它不会进入发送给模型的 `AgentRunRequest.messages`。
- **LLM call path 证据**：`prepare_compactor_proposal_run_input:317-347` 分别构造 `agent_request` 与 derived projection；`_agent_request_vnext:553-576` 的 user message 只调用 `_user_prompt_vnext`；后者在 `:667-703` 使用唯一 `_repair_feedback_prompt_json_vnext`，只投影 `required_action` 和 `issues`，不含 request/source-boundary digest。
- **contract 证据**：`CompactRepairFeedbackV2.to_json:1683-1696` docstring 已明确为 `durable/internal serialization`；`docs/host/design.md:1785-1788` 把 runner/compactor input projection 定义为 derived audit payload，不是 recovery、memory、dispatch 或 LLM context 真源。
- **反例审计**：全仓 production call sites只有 projection artifact 构造与 `_feedback_char_count` 的 bounded 计量；没有把 `feedback.to_json()` 拼入普通或 compactor LLM messages 的路径。现有测试还断言 prompt projection不含两个 governance digest。
- **状态**：不存在当前 LLM governance leak；仅因方法名未来可能被误用不是可报告 defect，也不足以授权 public/internal surface 重命名。

### DS-OQ-4：provenance multiset / event-id collision 是否可达

- **裁决**：`rejected-with-reason`。
- **multiset 证据**：`_sorted_selected_provenance_values:1626-1643` 排序但保留重复项；比较键同时包含 `canonical_source_refs` 和 `packed_content_digest`，不会因同 ref 不同内容而等价，也不会因两个完全相同项而丢失计数。
- **block identity 证据**：`selected_block_provenance_for_material_blocks:1908-1942` 要求 material block ids 与 selected ids 各自唯一，并按 id 从 frozen raw source snapshot 机械派生 refs/digest；pipeline `:982-1001` 重建 expected provenance 后 exact equality 校验。
- **event identity 证据**：`dayu/host/durable/schema.py:420-422` 对 EventLog `event_id` 施加 `UNIQUE`；`test_event_log_store.py` 分别证明同 id/同 body 幂等复用、同 id/不同 body identity conflict。UUID 碰撞不能静默产生两个不同 canonical facts。
- **反例结论**：完全相同 refs+digest 的重复块即使顺序互换也没有业务可观察差异，且 multiset 仍保留 cardinality；不同内容或不同数量会 fail closed。没有当前 producer 可达的 semantic substitution。
- **状态**：纯理论 collision 不是当前 residual correctness risk。

## DS-A / DS-B / DS-C 再裁决

### DS-A：operation selected-pack proof 未包含 `previous_compacted_view`

- **裁决**：`rejected-with-reason`；状态=`证据失效`。
- **正确 owner**：previous pair 由 compact-material 从 latest accepted candidate 机械生成，并由 `validate_previous_compacted_view_pair` / typed recovery transform 拥有；selected provenance 只拥有本轮 raw delta。
- **直接证据**：`initial_segment_selection:1387-1426` 只把 trace/evidence/answer 放入 selected ids，把 every previous label 固定写为 `previous_compacted_view` excluded reason；当前 production 中 `CompactionRequest(` 只有 `compact_pipeline.py:944` 一个构造点；pipeline 已对 frozen raw snapshot exact proof/root partition 负责。
- **operation contract**：`_validate_operation_selected_pack:1596-1623` 刻意只比较 trace/evidence/answer pack；`_validate_operation_root_request:1583-1593` 另对含 previous 的完整 source boundary 做顺序精确绑定。
- **拒绝修复理由**：把 previous 纳入 selected multiset 会把 stable durable memory 冒充 raw selected delta，并使合法 request 产生数量假阳性；让 operation 重读 durable snapshot则会复制 pipeline/material owner。

### DS-B：`_requires_budget_acceptance` 恒为 `True`

- **裁决**：`rejected-with-reason`；状态=`证据失效`。
- **直接证据**：`git blame` 把 `del request; return True` 与 proactive/reactive 统一 hard-threshold docstring定位到 `bd1d3e94c571e0b98096e9cfa4d169cefd8003c9`（2026-07-20），早于本 work unit；调用点 `compaction_operation.py:1146-1153` 在 accepted truth 前执行 owner gate。
- **拒绝理由**：该 helper 表达的是现有 Host hard-threshold policy seam，不是待实现 conditional；删除/条件化会削弱既有 contract。本 work unit 未引入该结构，也没有可达错误分支。

### DS-C：manifest recorder 内部创建 `PayloadStore`

- **裁决**：`rejected-with-reason`；状态=`证据失效`。
- **直接证据**：`PayloadStore`（`durable/payload.py:155-228`）无 constructor state、连接、transaction、缓存或 identity counter，方法只消费调用方传入 transaction；同类 `DurableRunnerCallManifestRecorder`（`run_input.py:966-978`）采用同样装配。
- **F09 identity 证据**：manifest ref/digest 来自 event id、canonical body 与返回 descriptor，不来自 store 实例身份；projection、manifest 和 EventLog append 位于同一 `run_write` transaction。
- **拒绝修复理由**：增加 optional DI seam 会扩大 constructor surface 和装配分支，却不能修复任何当前 identity 分叉。

## 两路 Open Questions / Residual Risks 完整归类

| 来源项 | 独立裁决 | Gateflow 分类 / owner |
|---|---|---|
| MiMo Open Questions：无 | accepted | 无 |
| MiMo residual 1：五条正式 CLI scenarios 未运行 | accepted residual | `covered by later approved evidence/readiness gate`；Oracle 总控 |
| MiMo residual 2：active-cancel 非确定性时序 | accepted observation，非本 WU regression | `assigned to later work unit if recurrence`；open_host active-cancel owner |
| MiMo residual 3：DS-A defense-in-depth | rejected-with-reason | 当前 contract domain 不成立；不登记 deferred risk |
| DS residual 1：五条正式 CLI scenarios 未运行 | accepted residual | 同 MiMo residual 1 |
| DS residual 2：previous view provenance | rejected-with-reason | 同 DS-A；不是当前 residual |
| DS residual 3：legacy compactor 无 manifest | accepted conditional limitation，非当前 defect | 若未来替换 compactor，由新实现 work unit 负责实现 `CompactorProposalPreparedCompactor`；当前 production 使用正式 prepared path |
| DS residual 4：本次未独立复跑 coverage | rejected as current gap | accepted aggregate gate 已有逐文件 83%–92%；本 gate只改 docs/external body，重新跑 489 owner tests和 full pyright，不用重复 coverage |
| DS residual 5：单标点 | rejected-with-reason as code gap | real-provider compliance 由 later evidence/readiness gate 覆盖 |
| DS residual 6：F09 full E2E 缺失 | rejected-with-reason | 现有三条 scheduler E2E + mismatch test 已直接覆盖 |
| DS residual 7：`to_json` 名称歧义 | rejected-with-reason | 当前 durable/internal docstring与唯一 LLM projector清晰；未来误用不构成 finding |
| DS OQ 4：provenance/event-id collision | rejected-with-reason | DB identity + exact digest/cardinality 已 fail closed |
| GitHub checks 为零 | accepted external observation | `requiring explicit user decision at later merge/readiness`；本 gate不得伪称 GitHub CI pass |

没有 `needs-more-evidence` 的当前 code finding，没有 blocking open question，没有 unclassified residual risk。

## 实际修改

### Production / tests / frozen files

- Production：无修改。
- Tests：无修改。
- 三份 frozen baseline：无修改。
- Local durable artifacts：新增本文件与 `docs/reviews/pr-190-review-20260804-201303.md`。

### PR external-state diff

- **修改字段**：仅 PR body。
- **修改前**：`Exact-head validation` 指向 `58aeb7b...`；验证数字和 review status 只覆盖 F01–F07；没有准确说明 F08–F10，也未列明五条禁止补跑 scenarios。
- **修改后**：指向 `72b7f145...`；分开记录 F08–F10 current work unit 与 prior F01–F07 historical checkpoint/evidence；明确 owner E2E 并非正式 CLI conformance；列出五条未运行 scenarios；next owner 为两路 re-review。
- **保留信息**：F01–F07 real-provider、bundle path/digest、checksum、secret scan、测试/coverage、早期失败观测和既有 scope boundary 全部保留。
- **未改变**：title=`fix(cli): close interactive conformance gaps`、state=`OPEN`、draft=`true`、base=`main`、head branch/OID、reviewDecision、mergeable/mergeStateStatus。
- **未执行**：comment、approve、request changes、mark ready、merge、request reviewers、commit、push。

## Validation

- 本地 HEAD：`72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`；与 GitHub `headRefOid` 相同。
- PR：OPEN draft，MERGEABLE/CLEAN；GitHub checks=`no checks reported`。
- Focused owner suite（11 files）：`489 passed, 1 skipped, 3 warnings in 7.99s`；skip 为 opt-in real-provider smoke。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check 68ba4038..72b7f145`：通过。
- F09 最小 owner E2E 属上述 suite，success / repair / exhausted fallback / mismatch 四条均通过。
- PR body 写后 SHA-256：`ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8`。
- Frozen SHA-256：
  - `docs/cli_ci_oracles.json`：`da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
  - `docs/cli_ci_scenarios.json`：`7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：`95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`
- 五条正式 CLI scenarios：**未运行**。

## Docs decision

本 gate 没有修改 production/tests、Host stable contract、测试分层或用户 CLI 工作流，因此不触发 README/design 更新。PR body
属于 draft PR 审计边界修正；durable review 结果只写入 `docs/reviews/`。

## Completion status

- PR review fix/audit：`pass`。
- Accepted findings：1 项（PR body drift），已修复。
- Accepted owner-level code/test findings：0 项。
- Rejected-with-reason：DS 四个 open questions、DS-A/B/C 及其重复 residual statements。
- Needs-more-evidence：0 个当前 finding；五条正式 scenarios 是 frozen plan 已分配的后续 evidence obligations。
- Current gate / next entry point：**AgentMiMo / AgentDS 两路 PR re-review handoff**。
- 未 commit、未 push；不得把本状态写成 accepted PR review commit、draft-PR-pass 或 final closeout。
