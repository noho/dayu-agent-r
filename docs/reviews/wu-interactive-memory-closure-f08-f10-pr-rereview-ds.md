# Interactive Conversation Memory closure F08–F10：DS 第二独立路线 PR Re-review

## Gate Identity

- **Gate**: Gateflow PR re-review handoff — AgentDS 第二独立路线。
- **Work unit**: 修复 Interactive Conversation Memory closure F08–F10。
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`。
- **Reviewed remote head**: `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`。
- **Base**: `main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`。
- **Review inputs**:
  - 原 DS review: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-ds.md`
  - MiMo 原 review: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-mimo.md`
  - Codex fix/audit: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-fix-codex.md`
  - 时间戳 artifact: `docs/reviews/pr-190-review-20260804-201303.md`
  - 当前 GitHub PR #190 body/metadata
- **Excluded scope**: MiMo re-review artifact/结论（按要求不得读取）；五条正式 CLI scenarios（按 deepreview skill 禁令未运行）；production/tests/PR body/frozen baseline（不得修改）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-rereview-ds.md`
- **Review date**: 2026-08-04

---

## PR 状态核对

| 检查项 | 结论 | 证据 |
|--------|------|------|
| PR state = OPEN | ✅ PASS | `gh pr view 190 --json state` → `"OPEN"` |
| PR isDraft = true | ✅ PASS | `gh pr view 190 --json isDraft` → `true` |
| Head = `codex/interactive-oracle` | ✅ PASS | `gh pr view 190 --json headRefName` → `"codex/interactive-oracle"` |
| Head oid = `72b7f145...` | ✅ PASS | `gh pr view 190 --json headRefOid` → `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` |
| Base = `main` | ✅ PASS | `gh pr view 190 --json baseRefName` → `"main"` |
| Title 不变 | ✅ PASS | `fix(cli): close interactive conformance gaps` |
| Reviews = 空 | ✅ PASS | `gh pr view 190 --json reviews` → `[]`（未评论/approve/request changes） |
| CI checks | ⚠️ 零条 checks | `gh pr checks 190` 返回空；PR body 明确写 "zero/no checks; this is not reported as a GitHub CI pass" |

---

## PR-BODY-01 逐项复核：draft PR summary 漂移是否已修复

本次 re-review 不读取 MiMo re-review artifact，但独立核对当前 GitHub PR #190 body 与 task requirements 中的每一项。

| 检查项 | 结论 | 直接证据 |
|--------|------|---------|
| 累计 F01–F07 evidence 完整保留 | ✅ | body 保留完整 "Prior F01–F07 checkpoint" 段落，含 real-provider bundle path/digest、checksum 743/743、test numbers、frozen hashes |
| F08–F10 summary 准确 | ✅ | body 新增 "F08–F10 current work unit" 段落：F08 require null + four semantic sections independent、F09 manifest/hot/resolver same ref/digest、F10 turn-group atomic + double-digest feedback + root accept barrier |
| F08–F10 owner 验证准确 | ✅ | body 列出 Codex fix/audit owner suite 489 passed, 1 skipped, full pyright 0 errors；Gateflow Host owner suite 2385 passed；full pytest 6639 passed；coverage ≥80% aggregate |
| Reviewed head 边界真实 | ✅ | "Exact-head validation" 指向 `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`；body SHA-256 `ee97bf68...32493c8` 与 Codex 写后记录一致 |
| 五条正式 CLI scenarios 明确未运行 | ✅ | body 列出五条 scenarios (`interactive.g06.summary-null`/`tool-trace-formal`/`turn-group-atomicity`/`drop-superseded`/`drop-policy-limit`) 并声明 "intentionally not run"、"remain owned by the later Oracle evidence/readiness gate" |
| 未将 owner tests 伪称正式 CLI conformance | ✅ | body 明确写 "deterministic owner tests and public-resolver integration tests below are not represented as formal CLI conformance or real-provider scenario evidence" |
| No checks 未被表述成 CI pass | ✅ | body 明确写 "GitHub checks: zero/no checks; this is not reported as a GitHub CI pass" |
| Title 无漂移 | ✅ | `fix(cli): close interactive conformance gaps` 未变 |
| OPEN/draft 无漂移 | ✅ | state=OPEN, isDraft=true |
| Base/head 无漂移 | ✅ | base=`main`, head=`codex/interactive-oracle` @ `72b7f145...` |
| Review state 无漂移 | ✅ | reviews=[]，无 comment/approve/request changes/mark ready/merge/request reviewers |

**PR-BODY-01 结论**: ✅ 已修复。全部 14 项检查通过。PR body 与真实 head 一致，累计 evidence 完整，边界声明清晰。

---

## 逐项独立复核：Codex 对 DS 提出项的裁决

### 1. 单标点 summary（DS-OQ-1）

- **原 DS 提出**: 若 LLM 输出 `{"text": ".", "source_labels": ["E1"]}`，strict parser 和 Host governance 均会接受——这是已知设计局限。
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:

- `conversation_compaction_user.md:36`: "如果当前明确 cap 内无法形成至少一条上述完整业务陈述，必须输出 JSON `null`。禁止用占位符、孤立字符、**孤立标点**、无上下文缩写或任何截断片段冒充 summary。" — 明确禁止孤立标点
- `context_governance.py:457-538` (`_collect_information_issues` / `_collect_policy_issues`): 对 `session_summary` 只做 shape/cap/coverage 确定性校验。`session_summary=None` 时不报告 LOW_INFORMATION；`session_summary` 非空时不检查自然语言语义质量
- frozen contract `:39-43`、accepted plan `:144-145,166-184,457-458`：明确将 "自然语言是否形成完整业务陈述" 的 owner 放在 prompt 与后续 Agent-in-the-loop observation，禁止用长度/ASCII/词表/正则/句点特例把 Host 变成 semantic heuristic verifier

**独立判断**:
- 机械观察（`"."` 会被 parser 和 Host governance 接受）在技术层面成立
- 但这是有意为之的设计边界：Host 被构建为确定性校验器而非语义质量裁判
- prompt 已明确禁止孤立标点；production Host 不拥有第二套自然语言真值
- 真实 provider 是否遵守该规则由后续 `interactive.g06.summary-null` scenario 验证
- **本问题不构成当前 code gap**；属 deferred real-provider evidence obligation

**状态**: 证据失效

---

### 2. F09 E2E — recorder → catch_up → query → formal resolver（DS-OQ-2）

- **原 DS 提出**: 缺少从 recorder 到 resolver 的完整 E2E 集成测试
- **Codex 裁决**: `rejected-with-reason`；称 DS 的"缺失"前提被代码测试直接证伪
- **独立复核结论**: **证据失效**

**直接代码证据** — 四条路径逐一验证:

**Success 路径**:
- `tests/host/test_dispatch_scheduler.py:8663-8762` (`test_multi_turn_proactive_compact_feeds_subsequent_run_input`)
- 第 8733 行调用 `_resolve_and_assert_compactor_calls(...)` with `accepted_attempt_number=1`
- `_resolve_and_assert_compactor_calls` (第 11756-11856 行) 完整执行:
  - `catch_up_tool_trace_projection`（第 11780 行）
  - `read_runner_call_reconstruction_signals_by_run`（第 11785 行）
  - `resolve_runner_call_projection_from_signal`（第 11795 行）
  - 逐 attempt 核对 source EventLog row、hot ref/digest、manifest descriptor、projection payload、provider/model、operation id、attempt number、response identity

**Repair 路径**:
- `tests/host/test_dispatch_scheduler.py:7211-7286` (`test_proactive_compaction_retries_quality_rejection_before_accept`)
- 第 7277 行调用 `_resolve_and_assert_compactor_calls(...)` with `attempt_payloads=(rejected_payload, compacted_payload)`, `accepted_attempt_number=2`
- 验证 rejected attempt 携带 proposal manifest（第 7275 行）、accepted attempt 携带 proposal manifest（第 7276 行）
- E2E resolver 同时核对 rejected 和 accepted 两条 attempt 的 identity

**Exhaust 路径**:
- `tests/host/test_dispatch_scheduler.py:8082-8187` (`test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback`)
- 第 8178 行调用 `_resolve_and_assert_compactor_calls(...)` with `attempt_payloads=rejected_payloads`, `accepted_attempt_number=None`
- 四次 invalid attempt 全部携带 proposal manifest（第 8167 行），通过 E2E resolver 核对

**Mismatch 路径**:
- `tests/host/test_tool_trace_queries.py:1848-1907` (`test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch`)
- 第 1898-1901 行：`pytest.raises(HostDurableError, match="tool trace row and runner-call hot identity mismatch")` — fail closed 断言

**独立判断**:
- 四条路径的 E2E 测试均已存在，覆盖 success/repair/exhaust/mismatch
- `_resolve_and_assert_compactor_calls` 是完整的 recorder→catch_up→query→resolver owner E2E
- 测试使用 `DurableCompactorProposalManifestRecorder`（通过 `dispatch.py:2533-2537` 装配），不 fake recorder/projector/resolver

**状态**: 证据失效

---

### 3. `CompactRepairFeedbackV2.to_json()` 是否进入 LLM path（DS-OQ-3）

- **原 DS 提出**: `to_json()` 方法名不具 "do not use for LLM" 的自文档性
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:

**`to_json()` 包含的字段**（`compaction.py:1689-1695`）:
```python
"request_digest": self.request_digest,
"source_boundary_digest": self.source_boundary_digest,
```
— 含双 governance digest

**LLM-facing 投影**（`llm_compaction.py:680-703`）:
```python
return {
    "required_action": feedback.required_action,
    "issues": [...],
}
```
— 只含 `required_action` + `issues`（code/json_path/message/source_labels），**不含** request_digest 或 source_boundary_digest

**调用证据**:
- `to_json()`: 进入 Host-internal `compactor_input_projection` durable Tool Trace artifact（`llm_compaction.py:604-625`）— 属 derived audit payload，不是 LLM context
- `_repair_feedback_prompt_json_vnext()`: 进入 LLM user message（`llm_compaction.py:667`）— 只投影 bounded issues，不含 governance digest
- `prepare_compactor_proposal_run_input:317-347`: 分别构造 `agent_request` 与 derived projection
- 全仓 production call sites: 只有 projection artifact 构造与 `_feedback_char_count` 计量；没有把 `feedback.to_json()` 拼入 LLM messages 的路径

**独立判断**:
- `to_json()` docstring（`compaction.py:1683`）已明确标注 "durable/internal serialization"
- LLM path 使用独立专用函数 `_repair_feedback_prompt_json_vnext`，已剥离双 digest
- 方法名未来可能被误用不是当前 correctness gap，也不足以授权 public/internal surface 重命名

**状态**: 证据失效

---

### 4. Provenance / event-id collision（DS-OQ-4）

- **原 DS 提出**: `_sorted_selected_provenance_values` 使用 sorted multiset 比较，依赖 canonical_source_refs 唯一性；若 EventLog event ID 碰撞可被构造，provenance check 不会检测
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:

**Multiset 比较**（`compaction.py:1626-1643`, `_sorted_selected_provenance_values`）:
- 排序但保留重复项
- 比较键同时包含 `canonical_source_refs` 和 `packed_content_digest`
- 不会因同 ref 不同内容而等价（digest 不同 → 不等）
- 不会因两个完全相同项而丢失计数（保留 cardinality）

**Block identity**（`compact_material.py:1908-1942`, `selected_block_provenance_for_material_blocks`）:
- 要求 material block ids 与 selected ids 各自唯一
- 按 id 从 frozen raw source snapshot 机械派生 refs/digest
- pipeline `:982-1001` 重建 expected provenance 后 exact equality 校验

**Event identity**:
- `dayu/host/durable/schema.py:420-422`: `event_id` 施加 `UNIQUE` 约束
- `test_event_log_store.py`: 分别证明同 id/同 body 幂等复用、同 id/不同 body identity conflict
- UUID 碰撞不能静默产生两个不同 canonical facts

**独立判断**:
- 完全相同 refs+digest 的重复块即使顺序互换也没有业务可观察差异，且 multiset 仍保留 cardinality
- 不同内容或不同数量会 fail closed
- 没有当前 producer 可达的 semantic substitution

**状态**: 证据失效

---

### 5. DS-A：operation selected-pack proof 未包含 previous_compacted_view

- **原 DS 提出**: `_validate_operation_selected_pack` 不覆盖 previous_compacted_view section，属 defense-in-depth gap
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:
- `_previous_compacted_view_pair_from_candidate`（`compact_material.py:2255-2342`）是 previous blocks 的真源
- `initial_segment_selection`（`compact_material.py:1388-1394`）明确将 previous 固定写入 `excluded_reason_codes`
- `selected_block_provenance` 只覆盖 delta material（trace/evidence/answer）
- 当前 production 中 `CompactionRequest(` 只有 `compact_pipeline.py:944` 一个构造点
- pipeline 已对 frozen raw snapshot exact proof/root partition 负责
- `_validate_operation_root_request:1583-1593` 另对含 previous 的完整 source boundary 做顺序精确绑定
- 将 previous 加入 proof-vs-pack 比较会把 stable durable memory 冒充 raw selected delta，使合法 request 产生数量假阳性

**独立判断**:
- previous view provenance 由独立的 typed contract 拥有（`validate_previous_compacted_view_pair`）
- selected provenance 只拥有本轮 raw delta
- 所有当前生产路径均通过 pipeline → snapshot 传递，无绕过路径
- 不构成 correctness gap

**状态**: 证据失效

---

### 6. DS-B：`_requires_budget_acceptance` 恒为 `True`

- **原 DS 提出**: helper 硬编码 `return True`，不执行实际条件判断
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:
- `git blame` 确认 `del request; return True` 由 `bd1d3e94c`（2026-07-20）引入，早于 accepted plan checkpoint `68ba4038`（2026-08-04）
- commit message: `WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth`
- docstring 明确覆盖 proactive + reactive 两条路径
- 调用点 `compaction_operation.py:1146-1153` 在 accepted truth 前执行 owner gate
- 该 helper 表达的是现有 Host hard-threshold policy seam，不是待实现 conditional
- 删除或条件化会暗示存在绕过硬闸门的合法路径，削弱既有 contract

**独立判断**:
- 本 work unit 未引入该结构
- 结构表达的是已冻结的 Host owner contract
- 不构成 correctness gap

**状态**: 证据失效

---

### 7. DS-C：manifest recorder 内部创建 `PayloadStore`

- **原 DS 提出**: recorder 内部直接实例化 `PayloadStore()`，缺少 DI seam
- **Codex 裁决**: `rejected-with-reason`
- **独立复核结论**: **证据失效**

**直接代码证据**:
- `PayloadStore`（`durable/payload.py:155-228`）无 constructor state、连接、transaction、缓存或 identity counter
- 方法只消费调用方传入 transaction
- 同类 `DurableRunnerCallManifestRecorder`（`run_input.py:977-978`）使用相同装配模式
- 全仓 11 处直接实例化 `PayloadStore()`
- F09 identity（manifest_digest、payload_ref）由 manifest content 和 event_id 决定，不由 PayloadStore 实例决定
- projection、manifest、EventLog append 位于同一 `run_write` transaction 内（`compaction_operation.py:258-347`）

**独立判断**:
- 增加 optional DI seam 会扩大 constructor surface 和装配分支
- 不能修复任何当前 identity 分叉（因为当前无分叉）
- 不构成 correctness gap

**状态**: 证据失效

---

## F09 E2E 四条路径直接验证

以下四条路径均经本 re-review 独立读代码验证：

| 路径 | 测试函数 | `_resolve_and_assert_compactor_calls` 调用 | `accepted_attempt_number` | 验证项 |
|------|---------|------------------------------------------|--------------------------|--------|
| Success | `test_multi_turn_proactive_compact_feeds_subsequent_run_input:8733` | ✅ | `1` | source EventLog row、hot ref/digest、manifest descriptor、projection payload、provider/model、response identity |
| Repair | `test_proactive_compaction_retries_quality_rejection_before_accept:7277` | ✅ | `2` | rejected attempt manifest + accepted attempt manifest 双轨道 identity |
| Exhaust | `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback:8178` | ✅ | `None` | 四次 invalid attempt 全部携带 proposal manifest，全部通过 formal resolver |
| Mismatch | `test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch:1898-1901` | N/A（直接 fail closed 断言） | N/A | `HostDurableError` with "tool trace row and runner-call hot identity mismatch" |

全部四条路径的 `_resolve_and_assert_compactor_calls` 内部链路（`catch_up_tool_trace_projection` → `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal`）均经本 re-review 独立走读确认（第 11756-11856 行）。

---

## 全部 Finding 状态汇总

| Finding | 原始来源 | Codex 裁决 | 独立复核结论 | 最终状态 |
|---------|---------|-----------|-------------|---------|
| PR-BODY-01 | Codex fix/audit | accepted | 代码已验证 body SHA-256 不变 + 14 项检查 PASS | **已修复** |
| DS-OQ-1 单标点 summary | DS review | rejected-with-reason | 机械观察成立但属设计边界，非 code gap | **证据失效** |
| DS-OQ-2 F09 E2E 缺失 | DS review | rejected-with-reason | 四条路径 E2E 均已存在 | **证据失效** |
| DS-OQ-3 to_json() 进入 LLM | DS review | rejected-with-reason | LLM 路径使用独立专用函数，已剥离 digest | **证据失效** |
| DS-OQ-4 provenance collision | DS review | rejected-with-reason | multiset cardinality + DB UNIQUE + digest 已 fail closed | **证据失效** |
| DS-A previous view proof | DS review | rejected-with-reason | previous 与 raw delta 属不同 owner | **证据失效** |
| DS-B budget helper 恒真 | DS review | rejected-with-reason | 既有 contract，早于本 WU | **证据失效** |
| DS-C recorder 内建 store | DS review | rejected-with-reason | store 无状态，identity 不来自实例 | **证据失效** |

---

## Open Questions

无。

原始 DS review 的四个 open questions 均已被代码/测试证据消解：DS-OQ-1 属设计边界而非 code gap，DS-OQ-2 被四条 E2E 测试证伪，DS-OQ-3 被 LLM path 代码审计消解，DS-OQ-4 被 multiset+UNIQUE+digest fail closed 消解。

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**（属于后续 Oracle evidence/readiness gate）:
   - `interactive.g06.summary-null`
   - `interactive.g06.tool-trace-formal`
   - `interactive.g06.turn-group-atomicity`
   - `interactive.g06.drop-superseded`
   - `interactive.g06.drop-policy-limit`
   - owner: Oracle 总控；当前 PR body 已明确列明未运行
   - 分类: deferred evidence obligation，非当前 gate blocking

2. **F08 real-provider 对 meaningful/null prompt 的稳定遵从性**:
   - 单标点占位符被 Host deterministic validator 接受是已知设计边界
   - 防御在 prompt NL 层而非 Host 代码层
   - 由后续 `interactive.g06.summary-null` scenario 覆盖
   - 分类: deferred real-provider observation

3. **GitHub checks 为零**:
   - 当前只报告 no checks，PR body 已明确写 "not reported as a GitHub CI pass"
   - 分类: 需用户在后续 merge/readiness gate 显式决策

4. **Legacy compactor path 无 manifest recording**:
   - 只有 `CompactorProposalPreparedCompactor` protocol 实现享有正式 Tool Trace identity
   - 当前 production 使用正式 prepared path
   - 分类: 条件限制（conditional limitation），非当前 defect

---

## Validation

| Check | Result |
|-------|--------|
| PR body SHA-256 | `ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8` — 与 Codex 写后记录匹配 ✅ |
| PR title | `fix(cli): close interactive conformance gaps` — 未改变 ✅ |
| PR state | OPEN, draft=true — 未改变 ✅ |
| Head OID | `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` — 与 task 要求一致 ✅ |
| Review state | reviews=[] — 无 comment/approve/mark ready/merge/request reviewers ✅ |
| 五条正式 CLI scenarios | 未运行（按 task 禁令）✅ |
| Production / tests / frozen baseline | 未修改 ✅ |

---

## Final Conclusion

**PASS**

本 AgentDS 第二独立路线 re-review 独立复核了：

1. **PR-BODY-01**: 全部 14 项检查通过 —— body 准确反映真实 head `72b7f145`、累计 F01–F07 evidence 完整、F08–F10 summary 和 owner 验证准确、reviewed head 边界真实、五条正式 CLI scenarios 明确未运行、未将 owner tests 伪称正式 CLI conformance、no checks 未表述成 CI pass、title/OPEN/draft/base/head/review state 无漂移。**状态: 已修复。**

2. **DS-OQ-1**: 单标点占位符被 Host 接受是设计边界，非 code gap —— prompt 已有明确禁止，Host 被有意不做 semantic heuristic。**状态: 证据失效。**

3. **DS-OQ-2**: F09 recorder→catch_up→query→formal resolver 完整 E2E 已存在 —— 四条路径（success/repair/exhaust/mismatch）均由真实调度器集成测试覆盖，`_resolve_and_assert_compactor_calls` 逐字段核对 identity。**状态: 证据失效。**

4. **DS-OQ-3**: `CompactRepairFeedbackV2.to_json()` 的 LLM governance - LLM path 使用独立专用函数 `_repair_feedback_prompt_json_vnext`，已剥离双 digest；`to_json()` 只用于 durable internal serialization。**状态: 证据失效。**

5. **DS-OQ-4**: provenance/event-id collision 不可达 —— multiset 保留 cardinality + DB UNIQUE + digest fail closed。**状态: 证据失效。**

6. **DS-A/B/C**: 三项 rejected-with-reason 全部经独立代码复核确认裁决正确。**状态: 证据失效。**

无 blocking finding、无需要 deferred 的 open question、无 unclassified residual risk。当前停止于 AgentDS re-review 完成点；下一步 owner 为 Controller 裁决两路 re-review 结论。
