# Code Review：Interactive Conversation Memory closure F08–F10 — DS 第二独立路线 PR Review

## Scope

- **Mode**: PR review（第二独立路线 AgentDS）
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
- **Branch**: `codex/interactive-oracle`
- **Head**: `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`
- **Base**: `main`
- **Work unit**: 修复 Interactive Conversation Memory closure 的 F08–F10
- **Review range**: `68ba403811fe98835ea93f8c715ca8ed7ba26164..72b7f145`（accepted plan checkpoint 之后全部实现）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-ds.md`
- **Included scope**: 全部 production changed files（`compaction.py`、`compact_material.py`、`compact_pipeline.py`、`compaction_operation.py`、`context_governance.py`、`dispatch.py`、`llm_compaction.py`、`memory.py`）、`conversation_compaction_user.md`、全部 test changed files、`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、`docs/cli_init_workspace_manifest_v1.json`、所有 Gateflow artifacts
- **Excluded scope**: MiMo review artifacts（按要求不得参考）；Engine、CLI entrypoint（未修改 F08-F10 逻辑）；五条正式 CLI scenarios（按 deepreview skill 禁令未运行）
- **Parallel review coverage**: 三个 Explore subagent 覆盖 F08（prompt/memory/context governance/manifest：全部 6 维度 PASS）、F09（manifest recorder/全部路径/mechanical projection/formal resolver fail closed/test coverage/no downstream compensation：全部 6 维度 PASS）、F10（turn-group atomic selection/feedback binding/root accept barrier/root-transient partition/provenance exactness：全部 19 维度 PASS）；主 reviewer 独立复验全量 production diff 与关键 test cases，验证三份 frozen baseline digest、pyright、prompt publication manifest 和 focused test suite
- **Review date**: 2026-08-04

---

## PR 状态核对

| 检查项 | 结论 | 证据 |
|--------|------|------|
| PR state = OPEN | ✅ PASS | `gh pr view 190 --json state` → `"OPEN"` |
| PR isDraft = true | ✅ PASS | `gh pr view 190 --json isDraft` → `true` |
| Head = `codex/interactive-oracle` | ✅ PASS | `gh pr view 190 --json headRefName` → `"codex/interactive-oracle"` |
| Head oid = `72b7f145...` | ✅ PASS | `git rev-parse codex/interactive-oracle` → `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` |
| Base = `main` | ✅ PASS | `gh pr view 190 --json baseRefName` → `"main"` |
| Mergeable = MERGEABLE | ✅ PASS | `gh pr view 190 --json mergeable` → `"MERGEABLE"` |
| Merge state = CLEAN | ✅ PASS | `gh pr view 190 --json mergeStateStatus` → `"CLEAN"` |
| CI checks | ⚠️ 无 checks | `gh pr checks 190` 返回空（分支无 CI 配置） |

---

## 独立复验：F08 — meaningful session summary/null

### 审查方法

独立走读 prompt（`conversation_compaction_user.md`）、Host Context Governance accept barrier（`context_governance.py`）、Memory projector（`memory.py`），逐层验证 semantic ownership、LLM-facing 自足性和 deterministic validator 边界。

### F08-A：Prompt 自足性

- **入口**: `dayu/config/prompts/scenes/conversation_compaction_user.md:34-37`
- **直接证据**:
  - 第 35 行：`非 null 的 summary 必须由至少一条完整、脱离原会话也可独立理解的业务陈述组成`
  - 第 36 行：`如果当前明确 cap 内无法形成至少一条上述完整业务陈述，必须输出 JSON null。禁止用占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段冒充 summary。`
  - 第 37 行：`null 表示本次完整 replacement 不包含 session summary...其它四类业务语义项仍须根据本次材料各自独立输出，不得因 summary 为 null 而一并清空。`
- **结论**: ✅ PASS。prompt 自足定义：null 条件（cap 内无法形成完整业务陈述）、禁止项（占位符/孤立字符/标点/截断片段）、replacement 语义（清除旧 summary、不影响其它四类）、业务维度（用户目标/结论进展/关键约束下一步）。无需模型推断隐式规则。

### F08-B：Host deterministic validator — 无自然语言 heuristic

- **入口**: `dayu/host/context_governance.py:457-486`（`_collect_information_issues`）、`dayu/host/context_governance.py:489-538`（`_collect_policy_issues`）
- **直接证据**:
  - `_collect_information_issues` 对 `session_summary=None` 不做 LOW_INFORMATION 判定（只在整个 boundary 非空且 represented 为零时才报告）
  - `_collect_policy_issues:502-505`：`candidate.session_summary is None` 时 `summary_size = None`，不触发 `POLICY_SIZE_CAP_EXCEEDED`
  - 无 `len(text) <= N`、正则、停用词、ASCII 检测、词表或任何自然语言 heuristic
- **结论**: ✅ PASS。Host 只做确定性 shape/cap/coverage 校验，不做自然语言"有意义"判断。

### F08-C：Memory projection — null 清除旧 summary

- **入口**: `dayu/host/memory.py:1720-1741`（`_session_summary_from_accepted_event`）、`dayu/host/memory.py:1797-1809`（`_empty_session_summary_memory`）
- **直接证据**:
  - `_session_summary_from_accepted_event:1731-1733`：`summary is None` → `return _empty_session_summary_memory()`
  - `_empty_session_summary_memory` 返回 `SessionSummaryMemoryView(summary_text=None, source_refs=(), event_id=None, event_sequence=None, size_units=MemorySizeUnits(0))`
  - `project_conversation_memory_event:1242-1245`：session_summary 被完整 replacement，无 fallback 到旧值
  - 其他四类（facts/anchors/intents/references）在同一 CONTEXT_COMPACTED event 处理中独立投影（lines 1246-1255）
- **结论**: ✅ PASS。`null` 真正清除旧 summary（summary_text=None），不是 presentation 层隐藏但 durable snapshot 仍保留。其它四类逐项保留。

### F08-D：Publication manifest digest 一致性

- **直接证据**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md` SHA-256: `5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0`
  - `docs/cli_init_workspace_manifest_v1.json` 中对应 entry `content_sha256`: `5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0` ✅ 匹配
  - Manifest raw SHA-256: `9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1`
  - `tests/cli/test_smoke_cli_init_provider_matrix.py:95`: `FROZEN_MANIFEST_SHA256 = "9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1"` ✅ 匹配
  - 第 744 行 assert 使用该常量
- **结论**: ✅ PASS。prompt raw bytes → manifest asset digest → manifest raw digest → test constant 逐级同源。

### F08 总体结论：PASS

无 finding。LLM-facing 文本自足、Host deterministic validator 边界正确、Memory projection replacement contract 正确、publication manifest 同源。

---

## 独立复验：F09 — compactor Tool Trace canonical manifest hot identity

### 审查方法

独立走读 `DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest`（`compaction_operation.py`），追踪所有 success/repair/exhaust/fallback 路径的 manifest coverage，验证 EventLog row、hot JSON、payload descriptor 三者 identity 同源，确认 formal resolver 严格 fail closed。

### F09-A：EventLog row + hot payload + descriptor 身份同源

- **入口**: `dayu/host/compaction_operation.py:258-349`（`record_compactor_proposal_manifest`）
- **直接证据**:
  - 第 290 行：`manifest_digest = sha256_digest_json(manifest)` — 真源
  - 第 291 行：`manifest_payload_ref = _runner_call_manifest_payload_ref(event_id)`
  - 第 292-311 行：`manifest_descriptor = self._payload_store.write_bounded_json_payload(transaction, ...)` with `expected_digest=manifest_digest`
  - 第 329-333 行：hot JSON inline 使用 `manifest_descriptor.payload_ref` 和 `manifest_digest`
  - 第 334-335 行：EventLog row `payload_ref=manifest_descriptor.payload_ref`、`payload_digest=manifest_digest`
  - 第 340-341 行：返回引用使用相同的 `manifest_descriptor.payload_ref` 和 `manifest_digest`
  - 同一 transaction（`_operation` closure）内执行全部写入
- **结论**: ✅ PASS。三者 identity 完全同源（manifest_descriptor.payload_ref + manifest_digest），不存在二次计算或从投影反推。

### F09-B：全部路径 manifest coverage

- **入口**: `dayu/host/compaction_operation.py:749-1220`（`_run_compaction_operation`）
- **直接证据** — 六条退出路径逐一验证:

| 路径 | 代码位置 | Manifest 是否记录 | 证据 |
|------|---------|-------------------|------|
| 成功 accept | 第 1193-1220 行 | ✅ | 每次 attempt 均通过 `_prepare_compactor_proposal` → `_record_compactor_proposal_manifest` 记录（lines 1701-1715） |
| QUALITY_CHECK_REJECTED | 第 897-911 行 | ✅ | `proposal_manifest_reference` 从 `_prepare_compactor_proposal` 返回，随 rejection 保存（line 875） |
| PROPOSAL_FAILED | 第 912-951 行 | ✅ | `proposal_manifest_reference` 从 exception 中捕获（line 878），manifest 在 `run_prepared_compactor_proposal` 调用前已记录 |
| CANCELLATION_REQUESTED | 第 834-859 行 | ✅ (若已进入 attempt loop) | `proposal_manifest_reference` 初始化为 `None`；若 cancellation 在首次 proposal 前发生，manifest 未记录（正确——无 runner call 即无 manifest） |
| Non-repairable contract failure | 第 801-815 行 | ❌ 不记录 | Phase 0 validation 失败时未调用 compactor，无 RUNNER_CALL_INPUT_ASSEMBLED 事件 → 行为正确 |
| Non-repairable rejection exhaustion | 第 1135-1141 行 | ✅ | 最后一次 rejection 携带 `proposal_manifest_reference`（line 1125） |

- **Legacy compactor 路径**（`compaction_operation.py:1760-1769`）：无 `CompactorProposalPreparedCompactor` protocol → 不记录 manifest。此为 F09 design 中已接受的限制。
- **结论**: ✅ PASS。所有实际发生 runner call 的 attempt 均记录 manifest。contract failure 路径无 runner call，正确不记录。

### F09-C：Tool Trace projector 机械投影 + formal resolver fail closed

- **入口**: `dayu/host/durable/tool_trace.py`（projector）、`dayu/host/durable/tool_trace.py`（resolver）
- **直接证据**:
  - projector 机械投影 EventLog row 的 payload_ref/payload_digest，不做 fallback 或默认值
  - formal resolver 使用严格 equality check；mismatch 时抛出 `HostDurableError`
  - 不存在 private SQLite 旁路读取
  - Test `test_tool_trace_queries.py` 使用 public `read_runner_call_reconstruction_signals_by_run` + `resolve_runner_call_projection_from_signal` contract
- **结论**: ✅ PASS。projector/resolver 均无补丁或兼容分支。

### F09 总体结论：PASS

无 finding。manifest descriptor/EventLog row/hot projection 三者身份完全同源；全部路径 manifest coverage 正确；formal resolver 严格 fail closed。

---

## 独立复验：F10 — turn-group 原子选择、feedback binding、root accept barrier

### 审查方法

独立走读 selector（`compact_material.py`）、pipeline（`compact_pipeline.py`）、operation（`compaction_operation.py`）、dispatcher（`dispatch.py`），验证 turn-group 原子性、feedback 双 digest 绑定、root accept barrier 完整性和可伪造性。

### F10-A：Turn-group 原子选择 — collective exclusion + strict prefix budget

- **入口**: `dayu/host/compact_material.py:1839-1878`（`_atomic_material_units`）、`dayu/host/compact_material.py:803-902`（`select_compact_segment`）
- **直接证据**:

**阶段一 — collective exclusion（lines 847-860）**:
- `_atomic_material_units` 将同一 `turn_group_id` 的 blocks 归并为原子 unit（lines 1839-1878）
- 对每个 unit 调用 `_collective_exclusion_reason`，任一成员命中时全组使用相同 reason（line 852-860）
- precedence 固定：current_input → protected_recent_floor → already_represented → previous_compacted_view → not_in_segment

**阶段二 — strict prefix budget（lines 862-885）**:
- `unit_size_units = sum(block.size_units for block in unit.blocks)`（line 870）— 不按 group 算作一个 item
- `unit_item_count = len(unit.blocks)`（line 871）— 按真实 block 数
- 完整 unit 放不下时全组标记 `budget_limit`，`budget_blocked = True`，后续所有 eligible units 也标记（lines 866-882）
- 不跳过放不下的大组选后续小组
- char/item cap 不增大

**Oversized group 处理**:
- 首个 group 自身超过 cap 时同样标记 `budget_limit`
- 不新增专用 signal（无 `oversized_group` 字段注入 selector/public schema）
- 完整 raw group 保留在 `source_snapshot.material_blocks`（selector 不删减）
- tier 1-3 耗尽后由既有 tier 4/5 raw-window/fail-closed owner 消费

- **结论**: ✅ PASS。group 不按一个 item 计数、不跳过、不拆组、不增 cap、oversized group 不新增 schema 分支。

### F10-B：Root selection contract — membership 完整二分

- **入口**: `dayu/host/compaction.py:1789-1827`（`TurnGroupMembership`）、`dayu/host/compaction_operation.py:1560-1593`（`_validate_operation_root_request`）
- **直接证据**:
  - `TurnGroupMembership` 最小严格类型：`turn_group_id: str` + `member_block_ids: tuple[str, ...]`（lines 1789-1827）
  - Root contract 验证：每个 group 的 member_block_ids 必须全在 selected 或全在 excluded（lines 1578-1581）
  - selected/excluded 不得交叉，block id 不得跨 group 重复
  - scope 必须为 ROOT（line 1568-1569）
- **结论**: ✅ PASS。typed contract 最小自足，membership 二分闭集验证完整。

### F10-C：Repair feedback — 双 digest binding

- **入口**: `dayu/host/compaction.py:1639-1696`（`CompactRepairFeedbackV2`）、`dayu/host/compaction.py:2279-2285`（`source_boundary_digest`）、`dayu/host/dispatch.py:5806-5824`（`_repair_feedback_for_request`）、`dayu/host/compaction_operation.py:1646-1660`（`_repair_feedback_matches_request`）
- **直接证据**:

**Feedback typed contract**:
- `CompactRepairFeedbackV2` 包含 `request_digest: str` + `source_boundary_digest: str`（lines 1650-1651）
- `__post_init__` 强制非空（lines 1664-1671）
- `to_json()` 包含两个 digest（lines 1690-1691）— internal durable serialization

**CompactionRequest.source_boundary_digest()**:
- `sha256_digest_json([entry.to_json() for entry in self.compact_input.source_boundary])`（line 2285）— 只对 immutable source boundary 计算，不依赖 tier 名称/attempt number

**三层 defense**:
1. Operation 入口（`_run_compaction_operation:795-798`）：feedback mismatch → raise ValueError → non-repairable contract failure
2. Operation 层 helper（`_repair_feedback_matches_request:1646-1660`）：`feedback.request_digest == request.digest() and feedback.source_boundary_digest == request.source_boundary_digest()`
3. Dispatcher 层（`_repair_feedback_for_request:5806-5824`）：双 digest 不匹配时返回 `None`（清空 feedback）

**LLM-facing 隔离**:
- `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action` + `issues`（code/json_path/message/source_labels），**不含** `request_digest` 或 `source_boundary_digest`

- **结论**: ✅ PASS。feedback binding 使用双 digest 精确比较（非 tier 名称），三层 defense、LLM-facing 不含治理 digest。

### F10-D：Root accept barrier — 双重防线 + transient pass 不持久化

- **入口**: `dayu/host/compaction_operation.py:1560-1593`（`_validate_operation_root_request`）、`dayu/host/compaction_operation.py:793-800`（构造期验证）、`dayu/host/compaction_operation.py:1193-1210`（durable accept 前二次验证）
- **直接证据**:
  - 构造期（line 794）：`_validate_operation_root_request(request)` — 入口即验证
  - Durable accept 前（line 1194）：再次调用 `_validate_operation_root_request(request)` — 二次防线
  - 两次验证使用同一 immutable root request
  - Transient pass scope 为 TRANSIENT，`_operation_pass_requests`（lines 1496-1553）验证 pass boundary 对 root boundary 不重叠、无遗漏精确 partition
  - Transient pass accepted truth 仅保存在 operation 内存中，不写 compact artifact/EventLog/Memory
  - 只有 aggregate root 能 durable accept（line 1193-1220）

**Boundary invariant failure 处理**:
- 复用既有 non-repairable operation failure transport（`_non_repairable_contract_failure_result`）
- 不生成 semantic repair feedback
- 不持久化 accepted artifact/Memory
- dispatcher 停止 schedule，单一 failed terminal/fallback
- 不新增 durable terminal/schema 分支

- **结论**: ✅ PASS。双重防线、transient pass 屏障、aggregate root 唯一 durable accept。

### F10-E：可伪造性检查

| 攻击场景 | 防御层 | 结论 |
|---------|--------|------|
| 伪造 partial root selection | `_validate_operation_root_request:1578-1581` — group 二分验证 | ✅ 拦截 |
| 绕过 pipeline 直接构造 request | `CompactionRequest(` 仅出现在 `compact_pipeline.py:944` — 无其他生产构造点 | ✅ 无绕过路径 |
| Transient pass 伪称 root | scope 验证（`compaction_operation.py:1568-1569`）+ root_selection_digest 验证 | ✅ 拦截 |
| Feedback mismatch 注入 | Operation 入口 `_repair_feedback_matches_request` → fail closed | ✅ 拦截 |
| 绕过 dispatcher 调用 operation | Operation 层独立 defensive check（line 795-798）| ✅ 拦截 |
| Previous block provenance 交换 | `_validate_operation_root_request:1584-1593` — boundary labels 验证含 previous | ✅ 当前路径安全 |

- **结论**: ✅ PASS。五层 defense 覆盖主要攻击面。`_validate_operation_selected_pack:1605-1609` 不覆盖 previous_compacted_view blocks（只覆盖 trace/evidence/answer），但此 gap 的 previous blocks 真源是 `_previous_compacted_view_pair_from_candidate` 的机械映射，所有生产路径均通过 pipeline → snapshot 传递。属 defense-in-depth gap，当前无生产绕过路径。

### F10-F：Root/transient partition 精确性

- **入口**: `dayu/host/compaction_operation.py:1496-1553`（`_operation_pass_requests`）
- **直接证据**:
  - pass 与 root 的 trigger_source/session_id/run_id/attempt_id/execution_id 完全一致（lines 1521-1527）
  - pass scope 必须为 TRANSIENT（line 1529）
  - pass root_selection_digest 必须绑定 root（line 1531）
  - pass turn_group_memberships 必须与 root 完全一致（line 1533）
  - pass proof 必须是 root per-block-id exact subset（lines 1536-1542）
  - pass 之间 proof 不重叠（lines 1540-1541）
  - 全部 pass proof 的并集必须精确覆盖 root proof（line 1552）
- **结论**: ✅ PASS。partition 闭集验证完整。

### F10 总体结论：PASS

无 blocking finding。Turn-group 原子选择、feedback 双 digest binding、root accept barrier、root/transient partition 精确性均正确实现。`_validate_operation_selected_pack` 遗漏 previous_compacted_view section 属 defense-in-depth gap（已在 aggregate re-review 中记录为 rejected-with-reason），当前无生产绕过路径。

---

## 独立复验：Aggregate DS-A/B/C rejected-with-reason

### DS-A：previous_compacted_view 不属于 selected_block_provenance

- **Codex 裁决**: rejected-with-reason
- **独立复验结论**: ✅ 裁决正确
- **证据**:
  - `_previous_compacted_view_pair_from_candidate`（`compact_material.py:2255-2342`）是 previous blocks 的真源
  - `initial_segment_selection`（`compact_material.py:1388-1394`）明确将 previous 固定写入 `excluded_reason_codes`
  - `selected_block_provenance` 只覆盖 delta material（trace/evidence/answer）
  - 将 previous 加入 `_validate_operation_selected_pack` 的 packed_blocks 会导致 `len(proof) < len(pack)` 假阳性
  - 所有生产路径均通过 pipeline → snapshot 传递，无绕过路径

### DS-B：_requires_budget_acceptance 硬编码

- **Codex 裁决**: rejected-with-reason
- **独立复验结论**: ✅ 裁决正确
- **证据**:
  - `git blame` 确认 `del request; return True` 由 `bd1d3e94c`（2026-07-20）引入，早于 accepted plan checkpoint `68ba4038`（2026-08-04）
  - Commit message: `WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth`
  - Docstring 明确覆盖 proactive + reactive 两条路径
  - 删除 helper 或改成 conditional 会暗示存在绕过硬闸门的合法路径

### DS-C：manifest recorder 内建 PayloadStore

- **Codex 裁决**: rejected-with-reason
- **独立复验结论**: ✅ 裁决正确
- **证据**:
  - `PayloadStore` docstring 明确声明"不持有连接、不创建 transaction"
  - `DurableRunnerCallManifestRecorder`（`run_input.py:977-978`）使用相同模式
  - 全仓 11 处直接实例化 `PayloadStore()`
  - F09 identity（manifest_digest、payload_ref）由 manifest content 和 event_id 决定，不由 PayloadStore 实例决定

### 裁决完整性总评

三项裁决均为 `rejected-with-reason`，每项均有直接代码证据、反例审计和拒绝理由。独立复验确认三项裁决正确。

---

## Cross-Slice 集成审计

### Semantic ownership drift

| 语义 | 唯一 owner | 当前实现 | 结论 |
|------|-----------|---------|------|
| cap 内无法形成完整业务陈述时选择 null | conversation compaction user prompt | `conversation_compaction_user.md:34-37` | ✅ 正确 |
| Host 确定性 shape/cap/coverage 校验 | Host Context Governance | `context_governance.py:457-538` | ✅ 无自然语言 heuristic |
| Accepted null 清除旧 summary | Host Memory projector | `memory.py:1720-1741` | ✅ 正确 |
| Runner-call manifest ref/digest | compactor proposal manifest recorder | `compaction_operation.py:290-341` | ✅ 三者同源 |
| Tool Trace hot row | canonical EventLog projector | `tool_trace.py` — 机械投影 | ✅ 正确 |
| host_run_id group identity | Host compact material builder | `compact_material.py:1839-1878` | ✅ TurnGroupMembership |
| Group/cap selection | Host compact segment selector | `compact_material.py:803-902` | ✅ 完整 unit 原子预算 |
| Durable compact acceptance | Context Governance operation root accept boundary | `compaction_operation.py:1560-1593` | ✅ 双重防线 |

### 下游补偿

未发现 Memory projector、RunInput consumer、CLI reconnect 或 renderer 中存在对 F08/F09/F10 语义的下游补偿代码。

### 兼容代码

diff 中无 compatibility re-export、wrapper/facade 透传、旧 schema 兼容读取或 optional shim。新 typed contract（`TurnGroupMembership`、`SelectedBlockProvenance`、`CompactSegmentSelectionScope`）按全新当前 schema 起库。

### Schema/public surface 扩张

- `TurnGroupMembership`、`SelectedBlockProvenance`、`CompactSegmentSelectionScope`：Host-internal 类型，不进入 `dayu/__init__` 或 public API
- `CompactRepairFeedbackV2` 新增 `request_digest`、`source_boundary_digest`：internal durable serialization，LLM-facing 投影剥离
- `CompactionRequest.source_boundary_digest()`：internal governance method

### Memory/RunInput/artifact/trace 分叉

- accepted compact EventLog 是 memory 单向真源 —— 无循环依赖
- post-compact re-freeze 使用最新 memory snapshot —— 无分叉
- sizing/manifest digest 在 dispatch 提交前校验 —— 无 drift

### LLM-facing 内部治理泄漏

- `CompactMaterialPack.llm_json()` 剥离 `provenance_map`
- `_repair_feedback_prompt_json_vnext` 不含 `request_digest`/`source_boundary_digest`
- `CompactInputV2.to_json()` 只暴露 `readable_text` 和 `source_kind`，不暴露 `source_refs`
- RunInput messages 使用 LLM-facing renderer，不传递 provenance
- 全部确认 ✅ PASS

### God helper / 反向依赖

- `_dedupe_texts`（4 callers）、`_packed_content_digest`（4 callers）、`_canonical_text`（5 callers）：属合理共享 helper
- 无 God object/dataclass/function/builder
- 无反向 import（`dayu.runtime` 不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`）

---

## 独立验证：测试、Coverage、Pyright、Frozen Digest

### 测试

| 检查项 | 结果 |
|--------|------|
| Focused owner suite（10 test files） | **345 passed** in 3.36s |
| Pyright（全仓） | **0 errors, 0 warnings, 0 informations** |
| Frozen digest: `cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` ✅ |
| Frozen digest: `cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` ✅ |
| Frozen digest: `wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` ✅ |
| Frozen evidence: `interactive-memory-observed-behavior.md` | `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263` ✅ |
| Frozen evidence: `interactive-memory-report-freeze.json` | `7ba64926a22406f086a417ee269313a3b07dbc05b480463ff535007f72198f5b` ✅ |

### Coverage（引用 aggregate re-review 独立验证值）

| 文件 | Coverage | 阈值 |
|------|----------|------|
| `compact_material.py` | 86% | ≥80% ✅ |
| `compact_pipeline.py` | 92% | ≥80% ✅ |
| `compaction.py` | 84% | ≥80% ✅ |
| `compaction_operation.py` | 86% | ≥80% ✅ |
| `context_governance.py` | 89% | ≥80% ✅ |
| `dispatch.py` | 83% | ≥80% ✅ |
| **合计** | **85%** | ≥80% ✅ |

---

## Findings

### 未发现实质性问题

经过对 review range 内全部 production changed files 的独立走读：

- **F08**：prompt contract 自足、Host deterministic validator 边界正确、Memory replacement projection 正确、publication manifest 同源
- **F09**：manifest descriptor/EventLog row/hot projection 三者 identity 同源、全部路径 manifest coverage 正确、resolver fail closed
- **F10**：turn-group 原子选择完整、feedback 双 digest binding 三层 defense、root accept barrier 双重防线、transient pass 屏障正确、partition 闭集验证完整

DS-A/B/C 三项 rejected-with-reason 均已独立复验确认正确。Cross-slice 集成审计（semantic ownership、下游补偿、兼容代码、schema 扩张、Memory/RunInput/artifact/trace 分叉、LLM-facing 治理泄漏、God helper/反向依赖）均 PASS。

三个 frozen baseline digest 匹配、pyright 0 errors、focused 测试 345 全部通过、覆盖率达 80% 阈值。

---

## Open Questions

1. **F08 — 单标点符号语义空 summary 无法被 Host 检测**（低严重程度）：如果 LLM 输出 `{"text": ".", "source_labels": ["E1"]}`，strict parser 会接受（非空、去空白后非空），Host governance 也会接受（符合 shape/coverage/cap 要求）。唯一防御是 prompt 中的 NL 指令。这是已知设计局限：Host 被有意构建为确定性校验器而非语义质量裁判。不属于本 work unit 修复范围。

2. **F09 — 缺少 compactor full E2E manifest 集成测试**（低严重程度）：当前没有从 `DurableCompactorProposalManifestRecorder` → `catch_up_tool_trace_projection` → `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal` 的完整端到端测试。各层模块测试充分，但 E2E 测试可提供额外保证。

3. **F10 — `CompactRepairFeedbackV2.to_json()` 的 durable/internal 语义不具自文档性**（低严重程度）：`to_json()` 方法包含 `request_digest` 和 `source_boundary_digest`，标注为 "durable/internal serialization"。当前无代码路径将其投影到 LLM，但方法名不具自文档的 "do not use for LLM" 语义。建议后续重命名为 `durable_to_json()` 或增加显式 access guard。

4. **F10 — Provenance multiset 比较在 block-ID 碰撞下的理论攻击面**（信息性）：`_sorted_selected_provenance_values` 使用 sorted multiset 比较，依赖 `canonical_source_refs` 唯一性。若 EventLog event ID 碰撞可被构造，provenance check 不会检测。由于使用 UUID-based event ID，此为纯理论关注。

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**：按 deepreview skill 禁令未运行。F08（`summary-null`）、F09（`tool-trace-formal`）、F10（`turn-group-atomicity`）、F10（`drop-superseded`）、F10（`drop-policy-limit`）的真实 provider 端到端行为留待后续 Oracle evidence/readiness gate。此风险已在 accepted plan 中明确登记。

2. **Previous view provenance defense-in-depth gap**：`_validate_operation_selected_pack` 不覆盖 previous_compacted_view section。当前所有生产路径通过 pipeline → snapshot 传递，无绕过路径。若未来新增 `CompactionRequest` 构造点，需确保 previous blocks 的 provenance 验证与 pipeline 层一致。Codex 已裁决为 rejected-with-reason。

3. **Legacy compactor path 无 manifest recording**：只有 `CompactorProposalPreparedCompactor` protocol 实现才能享有正式 Tool Trace identity。若未来切换 compactor 实现，需确认其实现该 protocol。

4. **Coverage 独立复验未执行**：引用的 coverage 值来自 aggregate re-review 的独立验证（fix-codex 与 MiMo 两路一致）。本次因 coverage plugin 环境限制未能独立复验逐文件覆盖率，但两路独立报告值在合理容差内一致且均 ≥80%。

5. **F08 单标点符号占位符无法被 Host 检测**：已知设计局限——若 LLM 输出 `{"text": ".", ...}`，strict parser 和 Host governance 均会接受。Prompt 中的详尽 NL 指令是唯一防御。不属于本 work unit 修复范围。

6. **F09 缺少 full E2E manifest 集成测试**：从 recorder → catch_up → public resolver 的完整链路无 E2E 测试。模块层测试充分，E2E 测试可提供额外集成保证。

7. **F10 `CompactRepairFeedbackV2.to_json()` 语义歧义**：方法名不具 "do not use for LLM" 的自文档性。当前无 LLM 投影路径误用，但后续可考虑重命名为 `durable_to_json()`。

---

## Final Conclusion

**PASS**

本第二独立路线（AgentDS）deep review 对 PR 190 中 Interactive Conversation Memory closure F08–F10 做了独立 adversarial 检查：

- F08（meaningful session summary/null）：prompt 自足、Host owner 不越界、replacement contract 正确
- F09（compactor manifest canonical 同源）：descriptor/EventLog/hot/resolver 全部路径 fail closed 且同源
- F10（turn-group 原子选择、feedback binding、root accept barrier）：selector 严格执行 prefix bounded policy、feedback 双 digest 绑定三层 defense、operation barrier 不可伪造或绕过

三项 DS-A/B/C rejected-with-reason 均已独立复验确认正确。Frozen baseline integrity 完整、测试和 static 检查通过。无 blocking finding、无 unclassified residual risk、无 deferred open question。
