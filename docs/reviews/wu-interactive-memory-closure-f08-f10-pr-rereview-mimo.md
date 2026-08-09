# PR 190 Re-Review — Interactive Conversation Memory closure F08–F10（AgentMiMo 独立路线）

## Scope

- **Mode**: PR Re-Review（AgentMiMo 第一独立路线）
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
- **Head**: `codex/interactive-oracle` @ `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`
- **Base**: `main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`
- **PR state**: OPEN draft, MERGEABLE, CLEAN, no CI checks
- **Review inputs**:
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-mimo.md`（原 MiMo PR review）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-ds.md`（DS PR review）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-fix-codex.md`（Codex fix/audit）
  - `docs/reviews/pr-190-review-20260804-201303.md`（时间戳 artifact）
- **Work unit**: 独立复核 PR body/metadata 漂移修复、DS rejected-with-reason 裁决、F09 E2E 测试链路
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-rereview-mimo.md`
- **Review date**: 2026-08-04

---

## PR Metadata 验证

| 检查项 | 预期值 | 实际值 | 状态 |
|--------|--------|--------|------|
| PR state | OPEN | OPEN | ✅ 未漂移 |
| isDraft | true | true | ✅ 未漂移 |
| title | `fix(cli): close interactive conformance gaps` | `fix(cli): close interactive conformance gaps` | ✅ 未漂移 |
| head branch | `codex/interactive-oracle` | `codex/interactive-oracle` | ✅ 未漂移 |
| head OID | `72b7f145...` | `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` | ✅ 未漂移 |
| base branch | `main` | `main` | ✅ 未漂移 |
| base OID | `113ea34d...` | `113ea34d47b95812d79aa31705949bbb46bc6061` | ✅ 未漂移 |
| mergeable | MERGEABLE | MERGEABLE | ✅ |
| merge state | CLEAN | CLEAN | ✅ |
| reviewDecision | 空 | 空 | ✅ 未漂移 |
| GitHub checks | 无 | `no checks reported on the 'codex/interactive-oracle' branch` | ✅ |

**结论**: PR 外部状态全部未漂移，与 Codex fix/audit 记录一致。

---

## PR-BODY-01 修复验证

### 修复前状态（来自 Codex fix/audit）

- `Exact-head validation` 指向 `58aeb7b...`（F01–F07 历史 checkpoint）
- 测试数字和 review status 只覆盖 F01–F07
- 没有准确说明 F08–F10 修复内容
- 未列明五条禁止补跑 scenarios

### 修复后状态（当前 PR body）

| 检查维度 | 结论 | 直接证据 |
|----------|------|----------|
| reviewed head 准确 | ✅ 已修复 | body 写 `Current reviewed remote head: 72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` |
| F01–F07 evidence 保留 | ✅ 保留 | body 保留 `Prior F01–F07 checkpoint and immutable evidence` 完整段落，含 bundle path/digest、real-provider、测试数字、coverage |
| F08–F10 说明 | ✅ 准确 | F08: meaningful/null + clear semantics；F09: manifest identity 同源；F10: turn-group atomicity + feedback binding + root barrier |
| owner tests 说明 | ✅ 准确 | `current Codex PR fix/audit owner suite: 489 passed, 1 skipped`；`deterministic owner tests and public-resolver integration tests below are not represented as formal CLI conformance` |
| 五条 scenarios 未运行 | ✅ 明确 | 列出 `interactive.g06.summary-null`、`tool-trace-formal`、`turn-group-atomicity`、`drop-superseded`、`drop-policy-limit`；标注 `intentionally not run`、`owned by the later Oracle evidence/readiness gate` |
| 未伪称 GitHub CI | ✅ | `GitHub checks: zero/no checks; this is not reported as a GitHub CI pass` |
| 未伪称正式 conformance | ✅ | `deterministic owner tests...are not represented as formal CLI conformance or real-provider scenario evidence` |
| body SHA-256 | ✅ 匹配 | `ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8` |

**PR-BODY-01 结论**: **已修复。** body 准确反映当前 head、保留累计 evidence、说明 F08–F10 修复边界、明确五条未运行 scenarios、未伪称 CI 或 conformance。

---

## Codex rejected-with-reason 复核

### DS-OQ-1：单标点 summary 是否构成当前 contract gap

- **Codex 裁决**: `rejected-with-reason`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - frozen contract `:39-43` 明确把"自然语言是否形成完整业务陈述"的 owner 放在 prompt 与后续 Agent-in-the-loop observation
  - frozen contract 明确禁止用长度、ASCII、词表、正则或句点特例把 Host 变成 semantic heuristic verifier
  - 当前 prompt 已明确禁止孤立标点
  - production Host 不拥有第二套自然语言真值
- **边界**: 不得新增 punctuation fallback、parser 特例或 Host negative contract test

### DS-OQ-2：F09 是否缺 recorder → catch_up → formal public resolver owner E2E

- **Codex 裁决**: `rejected-with-reason`；DS 的"缺失"前提被代码测试直接证伪
- **复核结论**: ✅ 裁决成立
- **直接证据**（独立验证 `tests/host/test_dispatch_scheduler.py`）:

  **E2E helper 函数**（`:11756-11856`）:
  - `_resolve_and_assert_compactor_calls` 明确执行完整链路：
    `catch_up_tool_trace_projection` → `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal`
  - 逐 attempt 核对 source EventLog row、hot ref/digest、manifest descriptor、projection payload、provider/model、operation id、attempt number 和 response identity

  **调用该 helper 的测试**:

  | 测试函数 | 行号 | 覆盖路径 |
  |----------|------|----------|
  | `test_multi_turn_proactive_compact_feeds_subsequent_run_input` | 8733 | single success |
  | `test_proactive_compaction_retries_quality_rejection_before_accept` | 7277 | invalid → repair → success |
  | `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback` | 8178 | 四次 invalid 后 exhausted fallback |

  **Mismatch fail-closed 测试**（`tests/host/test_tool_trace_queries.py:1848`）:
  - `test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch`：故意构造 row/hot identity mismatch，断言 `HostDurableError`

  **路径覆盖总结**: success / repair / exhaust / mismatch 四条全覆盖 ✅

- **状态**: owner-level E2E 已存在，无需补测试

### DS-OQ-3：`CompactRepairFeedbackV2.to_json()` 是否会进入 LLM path

- **Codex 裁决**: `rejected-with-reason`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - `to_json()` 只进入 Host-internal `compactor_input_projection` durable Tool Trace artifact
  - 不进入发送给模型的 `AgentRunRequest.messages`
  - `_agent_request_vnext` 的 user message 只调用 `_repair_feedback_prompt_json_vnext`，后者只投影 `required_action` + `issues`，不含 request/source-boundary digest
  - docstring 已明确为 `durable/internal serialization`
- **状态**: 不存在当前 LLM governance leak

### DS-OQ-4：provenance multiset / event-id collision 是否可达

- **Codex 裁决**: `rejected-with-reason`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - `_sorted_selected_provenance_values` 排序但保留重复项；比较键同时包含 `canonical_source_refs` 和 `packed_content_digest`
  - `selected_block_provenance_for_material_blocks` 要求 material block ids 与 selected ids 各自唯一
  - EventLog `event_id` 施加 `UNIQUE` 约束；同 id/不同 body identity conflict fail closed
  - UUID 碰撞不能静默产生两个不同 canonical facts
- **状态**: 纯理论 collision 不是当前 residual correctness risk

### DS-A：operation selected-pack proof 未包含 `previous_compacted_view`

- **Codex 裁决**: `rejected-with-reason`；状态=`证据失效`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - `previous_compacted_view` 是已接受 durable semantic memory 的 typed pair，不是本轮 raw delta selection
  - `initial_segment_selection` 固定把 previous labels 记入 excluded reasons，不生成 previous 的 `SelectedBlockProvenance`
  - `_validate_operation_selected_pack` 验证的是 raw delta 的 provenance 与 pack 一致性
  - 将 previous 加入 proof-vs-pack 比较会把 stable previous memory 冒充 selected raw delta，产生假阳性
- **状态**: 当前 contract domain 不成立；不登记 deferred risk

### DS-B：`_requires_budget_acceptance` 恒为 `True`

- **Codex 裁决**: `rejected-with-reason`；状态=`证据失效`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - `git blame` 确认 `del request; return True` 由 `bd1d3e94c`（2026-07-20）引入，早于本 work unit
  - Host hard-threshold contract 要求 proactive 和 reactive compact 都必须执行 budget acceptance
  - 删除或改为 conditional 会削弱已冻结的 Host owner contract
- **状态**: 属 maintainability 清理，不是 correctness gap

### DS-C：manifest recorder 内部创建 `PayloadStore`

- **Codex 裁决**: `rejected-with-reason`；状态=`证据失效`
- **复核结论**: ✅ 裁决成立
- **直接证据**:
  - `PayloadStore` 不持有连接、transaction、缓存或 identity 状态
  - 同类 `DurableRunnerCallManifestRecorder` 使用相同装配模式
  - F09 identity（manifest_digest、payload_ref）由 manifest content 和 event_id 决定，不由 PayloadStore 实例决定
- **状态**: 不存在当前 identity 分叉

---

## 原 MiMo Review F08–F10 结论复核

### F08：无意义 session summary 被接受

- **原结论**: PASS
- **复核结论**: ✅ 维持 PASS
- **证据链**: prompt 自足规则（`conversation_compaction_user.md:34-37`）→ Host deterministic validator 无自然语言 heuristic（`context_governance.py:457-538`）→ Memory projector null→clear 语义正确（`memory.py:1720-1741`）→ 其它四类语义独立保留

### F09：Compactor Tool Trace hot identity 不完整

- **原结论**: PASS
- **复核结论**: ✅ 维持 PASS
- **证据链**: manifest descriptor/EventLog row/hot projection 三者 identity 同源（`compaction_operation.py:258-345`）→ formal resolver fail closed（`tool_trace_queries.py`）→ E2E 测试覆盖 success/repair/exhaust/mismatch 四条路径

### F10：Proactive recovery tier 非原子截断 completed Run

- **原结论**: PASS
- **复核结论**: ✅ 维持 PASS
- **证据链**: turn-group 原子选择（`compact_material.py:1839-1878`）→ budget 在 group 粒度评估（`compact_material.py:803-902`）→ root/transient exact partition（`compact_pipeline.py`）→ repair feedback 双 digest 绑定三层 defense（`dispatch.py` + `compaction_operation.py`）→ operation 入口/出口双重验证（`compaction_operation.py:793-800, 1193-1210`）

---

## Validation Evidence

| 检查项 | 结果 |
|--------|------|
| PR metadata 漂移 | 无漂移 ✅ |
| PR body SHA-256 | `ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8` ✅ |
| Focused owner tests | 443 passed in 3.41s ✅ |
| pyright | 0 errors, 0 warnings ✅ |
| Frozen baseline: `cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` ✅ |
| Frozen baseline: `cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` ✅ |
| Frozen baseline: `wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` ✅ |
| F09 E2E 链路 | `recorder→catch_up→public resolver` 四条路径全覆盖 ✅ |
| GitHub checks | no checks reported ✅ |
| 五条正式 CLI scenarios | 未运行 ✅ |

---

## Findings

未发现实质性问题。

- PR-BODY-01 已修复：body 准确反映当前 head、保留累计 evidence、说明 F08–F10 修复边界、明确五条未运行 scenarios、未伪称 CI 或 conformance
- PR metadata 全部未漂移：title/OPEN/draft/base/head/review state 均与 Codex fix/audit 记录一致
- Codex 对 DS-OQ-1/2/3/4 和 DS-A/B/C 的 rejected-with-reason 全部成立
- DS-OQ-2 的"E2E 缺失"前提被 `test_dispatch_scheduler.py` 中 `_resolve_and_assert_compactor_calls` 的四条路径调用直接证伪
- 原 MiMo review F08–F10 PASS 结论维持

---

## Open Questions

无。

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**：按 frozen plan 明确登记为后续 evidence/readiness gate 的 obligations，owner 为 Oracle 总控。本 re-review 不得伪称已运行。

2. **GitHub checks 为零**：分支无 CI 配置，`requiring explicit user decision at later merge/readiness`。

3. **active-cancel 非确定性时序**：不在 F08–F10 diff；`assigned to later work unit if recurrence`。

4. **F08 单标点符号占位符无法被 Host 检测**：已知设计局限——Host 被有意构建为确定性校验器而非语义质量裁判。Prompt 中的详尽 NL 指令是唯一防御。不属于本 work unit 修复范围。

5. **Legacy compactor path 无 manifest recording**：只有 `CompactorProposalPreparedCompactor` protocol 实现才能享有正式 Tool Trace identity。当前 production 使用正式 prepared path，此为已知 design limitation。

---

## Final Conclusion

**PASS**

本 AgentMiMo 第一独立路线 re-review 对 PR 190 做了以下独立验证：

1. **PR metadata 漂移检查**：title/OPEN/draft/base/head/review state 全部未漂移 ✅
2. **PR-BODY-01 修复验证**：body 准确反映当前 head `72b7f145...`、保留 F01–F07 累计 evidence、说明 F08–F10 修复/owner tests、明确五条未运行 scenarios、未伪称 GitHub CI 或正式 conformance ✅
3. **Codex rejected-with-reason 复核**：DS-OQ-1/2/3/4 和 DS-A/B/C 共七项裁决全部成立 ✅
4. **F09 E2E 链路直接验证**：`tests/host/test_dispatch_scheduler.py:11756-11856` 的 `_resolve_and_assert_compactor_calls` 确实执行 `catch_up_tool_trace_projection → read_runner_call_reconstruction_signals_by_run → resolve_runner_call_projection_from_signal` 完整链路，覆盖 success/repair/exhaust/mismatch 四条路径 ✅
5. **原 MiMo F08–F10 PASS 结论复核**：三处修复均在正确 owner boundary 实施，结论维持 ✅
6. **当前验证**：443 owner tests passed、pyright 0 errors、三份 frozen baseline digest 不变 ✅

无 blocking finding、无 unclassified residual risk、无 deferred open question。
