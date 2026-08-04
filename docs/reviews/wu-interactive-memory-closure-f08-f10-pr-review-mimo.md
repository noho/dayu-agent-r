# PR 190 Review — Interactive Conversation Memory closure F08–F10（AgentMiMo 独立路线）

## Scope

- **Mode**: PR Review（AgentMiMo 第一独立路线）
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
- **Head**: `codex/interactive-oracle` @ `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`
- **Base**: `main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`
- **PR state**: OPEN draft, MERGEABLE, CLEAN, no CI checks
- **Review range**: accepted plan `68ba4038` 至当前 head `72b7f145`（F08–F10 实现 + 测试 + docs + Gateflow artifacts）
- **Work unit**: 修复 Interactive Conversation Memory closure 的 F08–F10
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-mimo.md`
- **Review date**: 2026-08-04

## PR Status Verification

| Item | Expected | Actual | Status |
|------|----------|--------|--------|
| PR state | OPEN draft | OPEN draft | ✅ |
| Head OID | `72b7f145` | `72b7f145` | ✅ |
| Base OID | `113ea34d` | `113ea34d` | ✅ |
| Mergeable | MERGEABLE | MERGEABLE | ✅ |
| Merge state | CLEAN | CLEAN | ✅ |
| Frozen baseline: `cli_ci_oracles.json` | `da049231...` | `da049231...` | ✅ |
| Frozen baseline: `cli_ci_scenarios.json` | `7c991d14...` | `7c991d14...` | ✅ |
| Frozen baseline: `wu-interactive-memory-closure-f08-f10.md` | `95a09543...` | `95a09543...` | ✅ |

三份 frozen baseline digest 与 accepted-plan checkpoint 精确相同，implementation 未改写 Oracle baseline。

## F08：无意义 session summary 被接受

### 审查项

| 审查维度 | 结论 | 证据 |
|----------|------|------|
| 唯一 prompt/Host owner | ✅ | prompt 侧修复在 `conversation_compaction_user.md`；shape/cap/accept-reject 属 Host Context Governance；无 Memory projector/CLI 下游补偿 |
| 禁止自然语言 heuristic | ✅ | "如果当前明确 cap 内无法形成至少一条上述完整业务陈述，必须输出 JSON `null`" — 确定性规则，非启发式 |
| null 作为 first-class 输出 | ✅ | 禁止占位符、孤立字符、孤立标点、无上下文缩写或截断片段；null 表示清除旧 summary |
| Host null 处理正确 | ✅ | `context_governance.py` 中 `session_summary is None` 时跳过 cap 检查、label 检查和 represented section 标记 |
| null round-trip 一致 | ✅ | `compact_payload.py:_parse_session_summary` 正确处理 `None`；`compaction.py` typed pair 支持 `None` |
| 其它四类语义不受影响 | ✅ | prompt 明确要求"其它四类业务语义项仍须根据本次材料各自独立输出，不得因 summary 为 null 而一并清空"；`test_memory_projection.py` 测试验证 |
| 测试覆盖 | ✅ | `test_llm_compaction.py` 验证 prompt 含 F08 关键短语；`test_memory_projection.py` 验证 null→clear + 四类语义保留 |

### F08 结论

**PASS。** prompt 侧修复完整，确定性规则明确，Host 已有正确 null 处理路径，测试覆盖 prompt 自足性和 null→clear 语义。无 semantic ownership drift。

## F09：Compactor Tool Trace hot identity 不完整

### 审查项

| 审查维度 | 结论 | 证据 |
|----------|------|------|
| canonical manifest identity 同源 | ✅ | `compaction_operation.py:331-332`：`payload_ref=manifest_descriptor.payload_ref, payload_digest=manifest_digest` — EventLog row 与 hot projection 从同一 transaction 已写出的 descriptor 派生 |
| manifest body 含 projection artifact 字段 | ✅ | manifest body 新增 `runner_call_projection_artifact_ref/digest/size_bytes`，从已持久化的 projection descriptor 填充 |
| resolver fail closed 保持 | ✅ | `engine_ingest.py`、`context_events.py` 未修改；resolver 逻辑未变更 |
| identity mismatch 拒绝测试 | ✅ | `test_tool_trace_queries.py:test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch` — 故意构造 mismatch 断言 `HostDurableError` |
| hot payload contract 测试更新 | ✅ | `test_runner_call_hot_payload_contract.py:_compactor_manifest` 从 pop 字段改为填充值，反映真实 producer 行为 |
| 未修改 resolver/projector | ✅ | `engine_ingest.py`、`context_events.py`、`_runner_call_manifest.py` 均无变更；修复完全在 producer 侧 |

### F09 结论

**PASS。** 根因修复在 producer（`DurableCompactorProposalManifestRecorder`），将 manifest descriptor ref/digest 写入 EventLog append request。resolver 和 projector 未修改，fail-closed 行为保留。测试覆盖 identity mismatch 拒绝路径。

## F10：Proactive recovery tier 非原子截断 completed Run

### 审查项

| 审查维度 | 结论 | 证据 |
|----------|------|------|
| turn-group 原子选择 | ✅ | `compact_material.py:_AtomicMaterialUnit` + `_atomic_material_units`：同 `turn_group_id` 的 blocks 绑定为不可分割单元；`_collective_exclusion_reason` 统一排除原因 |
| budget 在 group 粒度评估 | ✅ | `select_compact_segment` 重写为 per-unit loop；group 超 cap 时全体排除 `_REASON_BUDGET_LIMIT`；`budget_blocked` 全局传播 |
| root/transient exact partition | ✅ | `compact_pipeline.py:_validate_segment_against_source_snapshot`：ROOT 必须 exact partition；TRANSIENT 必须绑定 `root_selection_digest` |
| provenance 一致性验证 | ✅ | `compact_pipeline.py:_validate_selected_pack_current_input_separation`：拒绝 selected block 与 current input canonical ref 重叠 |
| repair feedback 双 digest 绑定 | ✅ | `CompactRepairFeedbackV2` 携带 `request_digest` + `source_boundary_digest`；`context_governance.py:build_compact_repair_feedback_v2` 在所有构造路径填入 |
| feedback 跨 boundary 过滤 | ✅ | `dispatch.py:_repair_feedback_for_request` 仅在双 digest 匹配时返回 feedback；不匹配返回 `None` |
| operation 入口验证 | ✅ | `compaction_operation.py:_run_compaction_operation` 在 provider 调用前执行 `_validate_operation_root_request` + `_repair_feedback_matches_request` |
| operation 出口再验证 | ✅ | `compaction_operation.py:1190` 在返回 accepted result 前再次调用 `_validate_operation_root_request` |
| non-repairable failure 快速退出 | ✅ | `dispatch.py:_compaction_result_is_non_repairable` 在 contract violation 时跳出 proactive schedule loop |
| 概念类型完备 | ✅ | `compaction.py` 新增 `CompactSegmentSelectionScope`、`TurnGroupMembership`、`SelectedBlockProvenance`；`CompactSegmentSelection` 新增 scope/memberships/provenance/root_digest 字段 |
| 测试覆盖 attack vectors | ✅ | provenance tamper（3 变体）、feedback digest mismatch、root boundary mismatch、current-input ref overlap、whole-group swap、unknown block ID、partial turn-group membership — 全部断言 fail before provider |

### F10 结论

**PASS。** turn-group 原子选择从 material selector 到 operation boundary 全链路实施；repair feedback 双 digest 绑定防止跨 boundary 泄漏；root/transient exact partition 和 provenance 一致性在 pipeline 和 operation 两层验证；operation 入口和出口双重验证。测试覆盖所有已知 attack vector。

## DS Aggregate Findings 复核

### DS-A：operation selected-pack proof 未包含 previous_compacted_view

**复核结论：rejected-with-reason 成立。**

直接证据复核：
1. `previous_compacted_view` 是已接受 durable semantic memory 的 typed pair，不是本轮 raw delta selection。
2. `initial_segment_selection` 固定把 previous labels 记入 excluded reasons（`compact_material.py` 相关逻辑），不生成 previous 的 `SelectedBlockProvenance`。
3. `_validate_operation_selected_pack` 验证的是 raw delta（trace/evidence/answer）的 provenance 与 pack 一致性；previous view 由 `validate_previous_compacted_view_pair` 独立拥有。
4. 将 previous 加入 proof-vs-pack 比较会把 stable previous memory 冒充 selected raw delta，产生假阳性。

### DS-B：`_requires_budget_acceptance` 恒为 true

**复核结论：rejected-with-reason 成立。**

直接证据复核：
1. `git blame` 和历史 commit `bd1d3e94` 证明该行为早于本 work unit。
2. Host hard-threshold contract 要求 proactive 和 reactive compact 都必须执行 budget acceptance。
3. 删除或改为 conditional 会削弱已冻结的 Host owner contract。
4. 属 maintainability 清理，不是 correctness gap。

### DS-C：manifest recorder 内部创建 PayloadStore

**复核结论：rejected-with-reason 成立。**

直接证据复核：
1. `PayloadStore` 不持有连接、transaction、缓存或 identity 状态。
2. 同类 `DurableRunnerCallManifestRecorder` 使用相同装配模式。
3. F09 只把同一 manifest descriptor ref/digest 写入 canonical EventLog 和 hot projection，不存在实例身份派生的第二套 truth。

## Validation Evidence

| Check | Result |
|-------|--------|
| Focused owner tests | 232 passed, 0 failed |
| pyright（6 changed host files） | 0 errors, 0 warnings |
| Frozen baseline: `cli_ci_oracles.json` | digest 不变 ✅ |
| Frozen baseline: `cli_ci_scenarios.json` | digest 不变 ✅ |
| Frozen baseline: `wu-interactive-memory-closure-f08-f10.md` | digest 不变 ✅ |

## Findings

未发现实质性问题。

F08–F10 三处修复均在正确 owner boundary 实施：
- F08 prompt 侧确定性规则，Host 已有正确 null 处理路径
- F09 producer 侧 manifest identity 修复，resolver/projector 未修改
- F10 material selector → pipeline → operation 全链路 turn-group 原子性 + feedback 绑定

DS aggregate 三项 finding 均已被 controller rejected-with-reason，re-review 确认证据失效，当前独立复核确认 rejection 理由成立。

## Open Questions

无。

## Residual Risk

1. **五条正式 CLI scenarios 未运行**：work unit 明确禁止补跑；assigned to later approved work，owner 为 Oracle 总控。
2. **active-cancel 非确定性时序**：不在本 work unit diff；assigned to later work unit if recurrence。
3. **DS-A 的 defense-in-depth gap**：`_validate_operation_selected_pack` 未包含 `previous_compacted_view` blocks。当前调用路径安全（previous view 由独立 validator 保证），但 operation 层缺乏 defense-in-depth。controller 已 rejected，不登记为 deferred risk；若未来 recovery tier 路径变更，应重新评估。

## Semantic Ownership Drift Check

| 语义 | 正确 owner | 是否漂移 |
|------|-----------|----------|
| session summary null/meaningful choice | conversation compaction prompt | 未漂移 — prompt 自足规则 |
| summary shape/cap/accept-reject | Host Context Governance | 未漂移 — Host 已有正确 null 处理 |
| runner-call manifest identity | Host runner-call manifest/EventLog append boundary | 未漂移 — producer 修复，resolver 未改 |
| hot projection identity | Host Tool Trace projector | 未漂移 — projector 未改 |
| turn-group identity | Host compact material selector | 未漂移 — `TurnGroupMembership` 在 owner 定义 |
| segment selection atomicity | Host compact segment selector | 未漂移 — `_AtomicMaterialUnit` 在 owner 实现 |
| repair feedback binding | Host proactive scheduler/operation | 未漂移 — 双 digest 在 owner 填入和验证 |
| accept barrier completeness | Host Context Governance operation boundary | 未漂移 — `_validate_operation_root_request` 在 owner 实施 |

无 Memory projector、renderer、CLI、private SQLite 或测试 fixture 下游补偿；无兼容 alias/wrapper、loose parser、旧 schema 读取或新增 public schema。
