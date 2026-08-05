# PR 190 F11/F12 S4 Evidence Gate — AgentDS 独立 Re-review（2026-08-06）

## Scope

- **Mode**: Evidence gate re-review（只读，不修改 production/oracle/scenario/evidence root）
- **PR**: 190（https://github.com/noho/dayu-agent-r/pull/190），head branch `codex/interactive-oracle`
- **Baseline HEAD**: `d9f044f944dd44e0d369f9d93e0533d2b725e413`
- **Repo artifact (corrected)**: `docs/reviews/pr-190-f11-f12-s4-real-provider-observation-20260805.md`
- **Adjudication**: `docs/reviews/pr-190-f11-f12-s4-evidence-review-adjudication-20260806.md`
- **Fix artifact**: `docs/reviews/pr-190-f11-f12-s4-evidence-fix-20260806.md`
- **Original reviews**: MiMo (`pr-190-f11-f12-s4-evidence-mimo-review-20260805.md`)、DS (`pr-190-f11-f12-s4-evidence-ds-review-20260806.md`)
- **Immutable evidence root**: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- **Root `digest.json` SHA-256**: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-evidence-ds-rereview-20260806.md`
- **Reviewer**: AgentDS（与 MiMo 相互独立，未读取另一路 re-review）
- **Excluded scope**: 未读取 private SQLite quarantine 内容（仅通过 `metadata/workspace-private-db-exclusion.json` 验证 exclusion boundary 与 SHA-256 一致性）；未运行 provider；未读取另一路 re-review；未 commit/push

---

## 1. Digest Identity 与 Read-only 完整性

| 检查项 | 预期值 | 实测值 | 结论 |
|--------|--------|--------|------|
| `digest.json` SHA-256 | `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` | `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` | ✅ exact match |
| 总文件数 | 160（含 self-excluded `digest.json`） | 160 | ✅ |
| evidence 目录数 | 8 (01–08) | 8 | ✅ |
| screen 文件数 | 10 (00–09) | 10 | ✅ |
| 根目录权限 | read-only | `dr-x------` | ✅ |
| 子目录权限 | read-only | `dr-xr-xr-x` / `dr-x------` | ✅ |

---

## 2. 裁决独立验证

### 2.1 MiMo-02（accepted）—— 已改为 canonical request operation/frozen_material_list_digest

**裁决**: 接受。repo artifact 使用了 `0f9c284b...` 派生 digest，不可由 machine-readable evidence 直接定位。

**独立验证**:

- 旧值 `0f9c284b` 在 `evidence/06-deepseek-bounded-repair/compact-eventlog.json` 中 **全文搜索命中 0 次**，确认不可定位。
- 修正后的 repo artifact 第 51 行已改为：
  - operation ID: `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`
  - canonical field: `payload.frozen_material_list_digest=sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`
- 上述 operation ID 与 digest **均可在 canonical eventlog 中直接 grep 定位**：
  - `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`：eventlog 命中 ✅
  - `b798e8e5`：eventlog 命中（`frozen_material_list_digest` 字段） ✅
- 修正后的 report 第 53 行声明 "immutable bundle 内的 `observed-report.md` 已由 root `digest.json` 封存，不得回写"，确认不修改已封存 evidence ✅

**结论**: MiMo-02 修复完成。**PASS**。

### 2.2 MiMo-01（rejected）—— failed-terminal fallback_input_window 支持裁决

**裁决**: 拒绝。Reviewer 混淆了 canonical FAILED terminal 的 fallback input boundary 与 dispatch 完成后的 Memory 投影。

**独立验证**:

- Canonical `CONTEXT_COMPACTION_FAILED` event（Mimo exhausted）:
  - `event_id`: `event-context-compaction-failed-a0d7f790cf2d4b9b8ea7b72ad026609a`
  - `payload.fallback_input_window.selected_block_ids`: **9** 个 ✅
  - `payload.fallback_input_window.dropped_block_ids`: **2** 个 ✅
- 同一 evidence 的 post-dispatch Memory (`memory.json`):
  - `snapshot.trace_memory.selected_recent_window`: **8** items ✅
  - `dropped_recent_window` key: **不存在** ✅
- DeepSeek exhausted 同理：
  - Canonical FAILED: selected=9, dropped=2 ✅
  - Post-dispatch Memory: selected_recent_window=8, no dropped_recent_window key ✅
- 修正后的 report 第 30 行已显式区分两个投影：
  > "canonical `CONTEXT_COMPACTION_FAILED.payload.fallback_input_window`（失败 terminal 的 input boundary）记录 ... selected=9、dropped=2。dispatch 完成后的 `memory.json.snapshot.trace_memory.selected_recent_window` 为 8 items，是另一投影，不是该 selection ledger，也不拥有 `dropped_block_ids`。"

**结论**: 裁决正确。**PASS**。

### 2.3 DS-01（rejected）—— config selector extends / effective runner identity 支持裁决

**裁决**: 拒绝。Reviewer 把 SMOKE ASSEMBLY 的配置 selector id 当成 effective provider/model。

**独立验证**:

- `workspaces/deepseek-session/config/models.json`:
  ```json
  {"models": {"mimo-v2.5-pro-plan": {"extends": "deepseek-v4-flash"}}}
  ```
  配置 selector `mimo-v2.5-pro-plan` **extends** `deepseek-v4-flash` ✅
- `evidence/04-deepseek-baseline/provider-identity.json`: `provider=deepseek, model=deepseek-v4-flash, capability=json_object` ✅
- `evidence/04-deepseek-baseline/compactor-attempts.json`: `provider=deepseek, model=deepseek-v4-flash` ✅
- Same for evidence/05–08（全部 DeepSeek evidence） ✅
- SMOKE ASSEMBLY 诊断打印的是 assembly 配置阶段的 selector，不是 execution profile 应用后的 resolved identity ✅
- 修正后的 report 第 52 行已明确区分 selector 与 effective identity ✅

**结论**: 裁决正确。**PASS**。

### 2.4 DS-02（rejected）—— baseline/replacement Memory before-after 支持裁决

**裁决**: 拒绝。Reviewer 声称 baseline 与 replacement Memory summary 均为 null；实际 baseline 非空、replacement 为 null。

**独立验证**:

- `evidence/04-deepseek-baseline/memory.json`:
  - `session_summary_memory.summary_text`:
    > "本会话总览标签为DAYU_S4_SUMMARY_BASELINE，研究对象为示例公司毛利率口径。已形成回答结论DAYU_S4_ANSWER_BASELINE：旧口径下毛利率18.2%……"
  - **非空** ✅
- `evidence/05-deepseek-replacement-constrained/memory.json`:
  - `session_summary_memory.summary_text`: **`None`**（JSON null） ✅
- 这是完整的 before/after evidence：baseline 有 summary → replacement `session_summary:null` 清除 ✅

**结论**: 裁决正确。**PASS**。

### 2.5 DS-03（rejected）—— Host answer-anchor audit 36=7+1+28 支持裁决

**裁决**: 拒绝。Reviewer 只统计了 detail 的 28 chars，漏掉了 title (7) 和换行 (1)。Host owner 计量公式为 `title + "\n" + detail`。

**独立验证**:

- Repair attempt 1（`evidence/06-deepseek-bounded-repair/compactor-attempts.json`）的 `output_content`:
  - `answer_anchors[0].title` = `"当前毛利率口径"` → **7 chars** ✅
  - `answer_anchors[0].detail` = `"当前唯一有效毛利率为21.7%，旧口径18.2%已失效。"` → **28 chars** ✅
  - title (7) + newline (1) + detail (28) = **36** ✅
- Canonical eventlog（`compact-eventlog.json`）中 repair operation 的 `CONTEXT_COMPACTED` audit:
  - `policy_usage_audit.answer_anchor_char_actual`: **36** ✅
  - `policy_usage_audit.answer_anchor_char_cap`: **30**（`policy_ref=s4-real-bounded-repair`） ✅
  - `36 > 30` → rejection 正确 ✅
- Repair attempt 2（accepted）:
  - `answer_anchors[0].title` = `"当前毛利率21.7%"` → 10 chars
  - `answer_anchors[0].detail` = `"旧口径18.2%已失效"` → 11 chars
  - title (10) + newline (1) + detail (11) = **22** ≤ 30 → accepted ✅
  - Canonical audit: `answer_anchor_char_actual=22, cap=30` ✅

**结论**: 裁决正确。**PASS**。

---

## 3. S4 全部 F11/F12 Evidence 重核

### 3.1 F11 — Successful Compact Identity

| Evidence | Provider | Model | Request ID Availability | Disposition |
|----------|----------|-------|------------------------|-------------|
| 01-mimo-baseline | mimo | mimo-v2.5-pro | unavailable | accepted |
| 02-mimo-boundary | mimo | mimo-v2.5-pro | unavailable | accepted |
| 04-deepseek-baseline | deepseek | deepseek-v4-flash | present | accepted |
| 05-deepseek-replacement | deepseek | deepseek-v4-flash | present | accepted (×2) |
| 06-deepseek-bounded-repair | deepseek | deepseek-v4-flash | present | accepted (×3), rejected (×1) |
| 07-deepseek-reconnect | deepseek | deepseek-v4-flash | present | accepted (×3), rejected (×1) |

**验证方式**: 每个 evidence 的 `public-tool-trace/tool-trace-analysis.json` 直接从 public resolver 投影，未读取 private SQLite。

**结论**: **PASS**。所有 successful compact 的 provider/model/request_id 均可从 public evidence 定位；Mimo 的 request_id unavailable 如实记录，无伪造。

### 3.2 F11 — Successful-Response-Then-Rejected Identity

| Evidence | Rejected Attempt | Response Identity Preserved | Terminal Binding |
|----------|-----------------|----------------------------|------------------|
| 03-mimo-exhausted-fallback | attempt 1, 2 | ✅（response identity 保留在 public-canonical-equality.json） | ✅（绑定 rejected terminal） |
| 06-deepseek-bounded-repair | attempt 1 | ✅ | ✅（`CONTEXT_COMPACTION_ATTEMPT_REJECTED` event 包含 `successful_response_identity`） |
| 08-deepseek-exhausted-fallback | attempt 1, 2 | ✅ | ✅ |

**结论**: **PASS**。

### 3.3 F12 — Public/Canonical Equality

| Evidence | canonical_terminal_count | finding_count | all_equal |
|----------|--------------------------|---------------|-----------|
| 01-mimo-baseline | 1 | 0 | true |
| 02-mimo-boundary | 1 | 0 | true |
| 03-mimo-exhausted-fallback | 2 | 0 | true |
| 04-deepseek-baseline | 1 | 0 | true |
| 05-deepseek-replacement-constrained | 2 | 0 | true |
| 06-deepseek-bounded-repair | 4 | 0 | true |
| 07-deepseek-reconnect | 4 | 0 | true |
| 08-deepseek-exhausted-fallback | 2 | 0 | true |

**结论**: **PASS**。全部 8 个 evidence 目录 `finding_count=0`，所有 comparison 的 `equal=true`，无 canonical equality 违反。

---

## 4. Transport 重核

### 4.1 Mimo `capability=none`

| Evidence | Attempt | structured_output_request | outbound_response_format_type |
|----------|---------|---------------------------|------------------------------|
| 01-mimo-baseline | 1 | `null` | `null` |
| 03-mimo-exhausted-fallback | 1, 2 | `null` | `null` |

**结论**: **PASS**。Mimo 所有 attempt 的 structured output request 与 outbound response format 均为 `null`，不存在 structured output downgrade 路径。

### 4.2 DeepSeek `capability=json_object`

| Evidence | Attempt | structured_output_request | outbound_response_format_type |
|----------|---------|---------------------------|------------------------------|
| 04-deepseek-baseline | 1 | `json_object` | `json_object` |
| 05-deepseek-replacement | 1 | `json_object` | `json_object` |
| 06-deepseek-bounded-repair | 1, 2 | `json_object` | `json_object` |
| 08-deepseek-exhausted-fallback | 1, 2 | `json_object` | `json_object` |

**结论**: **PASS**。所有 DeepSeek attempt 均实际装配 `json_object` structured output 到 outbound request。

---

## 5. Bounded Repair 重核

| 检查项 | 实测值 | 结论 |
|--------|--------|------|
| Canonical operation ID | `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff` | ✅ |
| `frozen_material_list_digest` | `sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee` | ✅ |
| Attempt 1/2 绑定同一 operation | eventlog 中 `CONTEXT_COMPACTION_REQUESTED` → `ATTEMPT_REJECTED` → `CONTEXT_COMPACTED` 链 | ✅ |
| Attempt 1 rejected reason | `policy_size_cap_exceeded`（screen diagnostic），answer_anchor=36 > cap=30 | ✅ |
| Attempt 2 accepted | `answer_anchor_char_actual=22 ≤ cap=30`（`s4-real-bounded-repair` policy） | ✅ |
| Rejection repairable | screen: `repairable=True`, `next_policy_decision=retry_semantic_repair` | ✅ |
| Same-boundary（material 不变） | `frozen_material_list_digest` 在两次 attempt 间一致 | ✅ |
| Repair 只改 self-contained feedback/whole-candidate replay | attempt 1 与 attempt 2 的 `output_content` 不同（answer_anchor 从 36 chars 缩至 22 chars），其余结构一致 | ✅ |

**结论**: **PASS**。

---

## 6. Exhaustion/Fallback 重核

| 检查项 | Mimo (evidence/03) | DeepSeek (evidence/08) | 结论 |
|--------|-------------------|------------------------|------|
| Attempt rejected 数 | 2（EventLog: `ATTEMPT_REJECTED` × 2） | 2（EventLog: `ATTEMPT_REJECTED` × 2） | ✅ |
| Failed terminal 数 | 1（EventLog: `COMPACTION_FAILED` × 1） | 1（EventLog: `COMPACTION_FAILED` × 1） | ✅ |
| Compact artifact 数 | 0（`COMPACT_ARTIFACT_FILE_COUNT 0`） | 0 | ✅ |
| `latest_compaction_event_ref` | `null` | `null` | ✅ |
| Semantic memory 状态 | 空 | 空 | ✅ |
| Canonical fallback selected/dropped | selected=9, dropped=2 | selected=9, dropped=2 | ✅ |
| Post-dispatch Memory selected_recent_window | 8 items | 8 items | ✅ |
| Post-dispatch Memory dropped_recent_window | key 不存在 | key 不存在 | ✅ |

**结论**: **PASS**。两种 exhausted fallback 均为单 failed terminal，无 compact artifact 产出，Memory 未污染（`latest_compaction_event_ref=null`，semantic memory 为空）。canonical FAILED terminal 的 9/2 与 post-dispatch Memory 的 8 items 是不同生命周期阶段的独立投影，ownership 清晰。

---

## 7. Memory/Reconnect 重核

| 检查项 | 实测值 | 结论 |
|--------|--------|------|
| Reconnect `latest_compaction_event_ref` | `event-context-compacted-98b6d9e9661f4aab998db4976a563252`（replacement compact，非 repair compact） | ✅ |
| Reconnect `session_summary_memory.summary_text` | `null`（replacement `session_summary:null` 已清除） | ✅ |
| Reconnect Memory 含旧结论 18.2% | false（`summary_text` 为 null，无任何旧结论） | ✅ |
| Reconnect 在新进程复用同一 session | `screen/07-deepseek-reconnect.txt` 确认新进程 | ✅ |

**结论**: **PASS**。Reconnect 看到的是 durable snapshot 的 replacement compact 状态，旧结论 18.2% 未恢复为活动 Memory 结论。

---

## 8. Secret Scan 重核

| 检查项 | 实测值 | 结论 |
|--------|--------|------|
| Scanned file count | 160 | ✅ |
| Credential sources | 2（`MIMO_PLAN_API_KEY`、`DEEPSEEK_API_KEY`，仅环境变量名，无值） | ✅ |
| Exact value findings | 0 | ✅ |
| Authorization/Bearer/API-key pattern findings | 0 | ✅ |
| 4 private SQLite 已 quarantine | ✅（quarantine SHA-256 与 exclusion 记录全部 MATCH） | ✅ |
| Public evidence tree 无 `dayu_host.sqlite3` | ✅（仅有 `runtime_lanes.sqlite3`，不含 credential snapshot） | ✅ |
| Quarantine 不在 root digest | ✅ | ✅ |

**结论**: **PASS**。零 secret finding。4 个 `dayu_host.sqlite3` 已正确 quarantine，SHA-256 映射可审计。

---

## 9. 三态无过度宣称

| 层 | 声明 | 诚实性 | 验证 |
|----|------|--------|------|
| Implementation | PASS | ✅ 诚实 | 观察基线为已 push HEAD；本轮未修改生产代码；git diff 确认仅 review docs 变更 |
| Real-provider observation | PASS | ✅ 诚实 | 所有 scenario exit_status=0；Mimo/DeepSeek 均真实可用；无 timeout/API rejection |
| Oracle | PENDING | ✅ 诚实 | 未运行 frozen formal CLI scenarios；未修改 oracle/scenario/registry；report 多处强调不得投影 |

**结论**: **PASS**。无跨越声明，无 PENDING→PASS 投影。

---

## 10. 补充验证项

| 检查项 | 结论 |
|--------|------|
| System prompt digest 一致性（`97479acc0cc686cb9a72d18b310aff58...`） | ✅ 已验证 baseline/replacement/repair 共 4 个 attempt 的 system prompt 均为相同 SHA-256、相同长度 (328 chars) |
| DeepSeek config `extends` 链 | ✅ `mimo-v2.5-pro-plan` → `extends=deepseek-v4-flash` 直接证实 |
| 4 quarantine SQLite SHA-256 映射 | ✅ 全部 MATCH exclusion 记录 |
| 10 command inventory ↔ 10 screen files | ✅ 一一对应，所有 exit_status=0 |
| `observed-report.md` 未回写 | ✅ immutable evidence root 的 `observed-report.md` 未被本轮修改 |
| Repair attempt operation binding | ✅ eventlog 中同一 operation ID 绑定 attempt 1 (rejected) 与 attempt 2 (accepted) |
| 36-char audit 公式 | ✅ `derive_compact_policy_usage_actuals_v3` 的 `title + "\n" + detail` 在 attempt 1 output（7+1+28=36）与 canonical audit（`answer_anchor_char_actual=36`）之间一致 |

---

## Findings

**未发现实质性问题。**

所有 5 项裁决（MiMo-01/02、DS-01/02/03）均有独立 direct evidence 支撑。修正后的 repo artifact 已正确引用 canonical operation/frozen_material_list_digest（MiMo-02），并补全了 fallback projection boundary、selector/effective identity 区分和 36-char 公式说明（MiMo-01/DS-01/DS-03 裁决澄清）。S4 全部 F11/F12 evidence 的 public/canonical equality、transport、bounded repair、exhaustion/fallback、Memory/reconnect、secret scan 均独立验证通过，三态声明诚实。

---

## Open Questions

无。

---

## Residual Risk

1. **Formal oracle 仍为 PENDING**: F08–F10 的 5 个 formal CLI scenario obligations 在此 observation 中未覆盖；必须由后续独立 oracle gate 裁决。本 re-review 的 PASS 仅针对 F11/F12 S4 evidence gate，不替代 oracle conformance。

2. **02-mimo-boundary 无 compaction 级 evidence**: boundary 测试未触发 compaction（session 未达阈值），`compactor-attempts.json` 为空数组。这不影响 capability=none 的 transport 验证，但不提供 compaction 级的 Mimo boundary behavior evidence。

3. **Reconnect 中旧值以"已失效"出现在 raw answer text**: reconnect 的 LLM 回答中提及旧值 18.2% 作为"已失效"，这不是 Memory/RunInput 的活动结论。但若后续 review 需要严格区分 raw history preservation 与 semantic reintroduction，应在 Memory 级做独立验证而非依赖 LLM 回答措辞。

4. **Smoke harness ASSEMBLY diagnostic 的 selector vs resolved 区分**: screen 的 `compactor_model_id=mimo-v2.5-pro-plan` 是配置 selector。虽然 evidence chain（`config/models.json`、`provider-identity.json`、`compactor-attempts.json`）可完整追溯到 resolved identity，但 screen 作为首要人类可读 evidence 面，缺乏 resolved 值行会持续造成读者混淆。这不是 observation artifact 的问题，而是 smoke harness 的 diagnostic 设计问题——建议在后续 work unit 中为 ASSEMBLY 段增加 resolved identity 行，不阻塞本 gate。

---

## Conclusion

经过对 immutable evidence root 的完整独立重核：

- **裁决独立验证**: 5/5 裁决（MiMo-01/02、DS-01/02/03）均有 direct canonical evidence 支撑，全部 PASS。
- **MiMo-02 修复**: 已正确改为 canonical request operation `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff` 和 `frozen_material_list_digest=sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`；`0f9c` 已移除；immutable `observed-report.md` 未回写。**PASS**。
- **S4 全部 F11/F12 evidence**: public/canonical equality（全部 `finding_count=0`）、transport（Mimo none / DeepSeek json_object）、bounded repair、exhaustion/fallback、Memory/reconnect、secret scan（0 finding）、三态诚实——全部独立验证通过。**PASS**。
- **Findings**: 0。**PASS**。

本轮 re-review 接受 S4 evidence gate 当前状态。Oracle gate 仍需独立执行。
