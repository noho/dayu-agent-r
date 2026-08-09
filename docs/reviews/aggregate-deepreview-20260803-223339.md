# Aggregate Deepreview — PR 190 Compactor 输出业务语义

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `codex/interactive-oracle`
- Base: `62b7d4a2` (plan gate commit)
- PR: #190 (`fix(cli): close interactive conformance gaps`, author: noho, state: OPEN)
- Output file: `docs/reviews/aggregate-deepreview-20260803-223339.md`
- Review focus: `62b7d4a2..HEAD` 的完整 committed diff，重点为最终 shipped semantics 与跨 artifact 一致性
- Included scope: 2 个 committed commits（plan acceptance + S1 acceptance），涉及 20 files changed, 2387 insertions, 11 deletions
- Excluded scope: 无（全部 committed diff 均在 review 范围内）
- Parallel review coverage: 无

## Commits in Range

| Commit | Message | Date |
|---|---|---|
| `21b602c1` | `gateflow: accept plan for compactor output business semantics` | 2026-08-03 |
| `11b63911` | `gateflow: accept compactor output business semantics S1` | 2026-08-03 |

## Changed Files Summary

### Production (1 file)

| File | Change |
|---|---|
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | 在 output schema 字段旁补齐 `session_summary`、`evidence_facts`、`answer_anchors` 与四种 drop reason 的 LLM-facing 业务语义 |

### Tests (3 files)

| File | Change |
|---|---|
| `tests/host/test_llm_compaction.py` | 扩充 packaged prompt owner test：36 条业务语义 assertion（4 section 分组）+ 8 条 forbidden-term guard |
| `tests/host/test_public_compact_smoke.py` | 在默认真实装配路径添加 6 条最小语义哨兵 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 更新 `FROZEN_MANIFEST_SHA256`（manifest bytes 变化导致） |

### Publication (1 file)

| File | Change |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | 更新 `conversation_compaction_user.md` 条目的 `content_sha256` |

### Gateflow Artifacts (7 files)

| File | Role |
|---|---|
| `docs/gateflow/pr-190-compactor-output-business-semantics-plan-20260803.md` | Plan artifact (319 lines) |
| `docs/gateflow/pr-190-compactor-output-business-semantics-plan-review-acceptance-20260803-215810.md` | Plan review acceptance |
| `docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md` | Implementation artifact |
| `docs/gateflow/pr-190-compactor-output-business-semantics-s1-code-review-fix-20260803.md` | Code review fix artifact |
| `docs/gateflow/pr-190-compactor-output-business-semantics-s1-review-acceptance-20260803.md` | S1 review acceptance |

### Review Artifacts (8 files)

| File | Role |
|---|---|
| `docs/reviews/pr-190-review-20260803-203709.md` | 外部 follow-up review（触发本 work unit） |
| `docs/reviews/plan-review-20260803-212134.md` | 初始 plan review（识别 3 项纠正） |
| `docs/reviews/plan-review-20260803-214309.md` | AgentMiMo plan review（pass） |
| `docs/reviews/plan-review-20260803-214733.md` | AgentDS adversarial plan review（F01/F02 deferred/rejected） |
| `docs/reviews/plan-review-20260803-215317.md` | Re-review route 1（pass） |
| `docs/reviews/plan-review-20260803-215546.md` | Re-review route 2（pass） |
| `docs/reviews/code-review-20260803-220950.md` | AgentMiMo code review（pass） |
| `docs/reviews/code-review-20260803-221641.md` | AgentDS code review（F01/F02/F03） |
| `docs/reviews/code-review-20260803-222315.md` | Re-review route 1（pass） |
| `docs/reviews/code-review-20260803-222626.md` | Re-review route 2（pass） |

## Verification Evidence

### Hash Chain (两级 publication truth)

| 层级 | 文件 | 声称 SHA-256 | 独立验证 |
|---|---|---|---|
| L0 | `conversation_compaction_user.md` | `a2f5711c...` | `sha256sum` ✓ 一致 |
| L1 | `cli_init_workspace_manifest_v1.json` | `fb6d0ba8...` | `sha256sum` ✓ 一致 |
| L1 entry | manifest 中该 asset 的 `content_sha256` | `a2f5711c...` | 与 L0 ✓ 一致 |
| L2 | `FROZEN_MANIFEST_SHA256` | `fb6d0ba8...` | 与 L1 ✓ 一致 |

Chain 闭合：prompt bytes → asset digest → manifest entry → manifest bytes → manifest digest → test constant。

### Test Results

| 测试 | 结果 |
|---|---|
| `test_prompt_assets_are_self_contained_for_fresh_v2_contract` | ✓ 1 passed |
| `test_default_compactor_prompt_is_llm_facing_and_self_contained` | ✓ 1 passed |
| `test_accepted_compact_without_summary_clears_prior_session_summary` | ✓ 1 passed |
| `python -m pyright dayu/ tests/ utils/` | ✓ 0 errors |

### Frozen Files Preserved

| 文件 | 变化 |
|---|---|
| `dayu/host/compaction.py` | 无 diff ✓ |
| `dayu/host/context_governance.py` | 无 diff ✓ |
| `dayu/host/memory.py` | 无 diff ✓ |
| `dayu/config/prompts/scenes/conversation_compaction.md` | 无 diff ✓ |
| `dayu/config/prompts/manifests/conversation_compaction.json` | 无 diff ✓ |
| `dayu/config/execution_profiles.json` | 无 diff ✓ |
| `docs/cli_ci_oracles.json` | 无 diff ✓ |
| `docs/cli_ci_scenarios.json` | 无 diff ✓ |
| `docs/cli_ci.md` | 无 diff ✓ |

### Forbidden Internal Terms

对 prompt 全文检查 11 个活跃内部术语（`CompactCandidate`、`CompactDropReason`、`compaction.py`、`context_governance`、`memory.py`、`MemoryProjectionPolicy`、`SessionSummaryMemoryView`、`event_id`、`payload_ref`、`schema_version`、`current_input_anchor`），全部 absent ✓。

### README / Design

全部 README（根、`dayu/`、`dayu/host/`、`dayu/config/`、`tests/`）与 design 文档在 `62b7d4a2..HEAD` 范围内无 diff ✓。

## Findings

未发现实质性问题。

## 核验清单

### 1. AGENTS.md LLM-facing 北极星

prompt 变更遵守 LLM-facing 文本约束：
- 只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项 ✓
- 不用代码类型名、内部模块名、历史迁移名或 Host 实现术语 ✓
- 字段含义、类型、必填性、允许值均在 prompt 中自足说明 ✓
- `source_label` 被说明为"只是引用标签，不是业务事实或推理依据" ✓
- 未把系统状态、调度状态或 Host 治理信息伪装成财报事实 ✓

### 2. Owner / Contract 边界

- 唯一 LLM-facing 语义 owner：`conversation_compaction_user.md` ✓
- `compaction.py` 独占 typed shape、enum、strict parse ✓（未修改）
- `context_governance.py` 独占 accept/reject、coverage、policy cap ✓（未修改）
- `memory.py` 独占 accepted candidate 到 Memory view 的完整 replacement ✓（未修改）
- publication manifest 与 test constant 只承载 prompt bytes 的派生 truth ✓

### 3. 三项用户纠正

| 纠正 | 描述 | 状态 |
|---|---|---|
| `session_summary: null` 清除 | candidate 被接受后当前摘要变为空，清除先前摘要 | ✓ prompt 第 34 行，与 `memory.py:1732-1733` 同源 |
| `claim` 双来源 | `evidence_material` 或 `previous_evidence_fact` 均可直接支持 | ✓ prompt 第 39-40 行，与 `COMPACT_FACT_SOURCE_KINDS_V2` 同源 |
| `policy_limit` 可见 cap | 只有当前 repair feedback 明示具体 cap 时可用 | ✓ prompt 第 66 行，与 `context_governance.py:492-576` 同源 |

### 4. 四种 Drop Reason

| Reason | 正向条件 | 负向禁止 | 互斥边界 |
|---|---|---|---|
| `superseded` | 被更新/更完整/更权威替代 | 保留会过时/冲突/误导 | 需存在替代 source |
| `redundant` | 内容仍有效但已完整表达 | 不得掩盖冲突或遗漏 | 信息已被覆盖 |
| `out_of_scope` | 与当前任务/可预见后续无关 | 不得因难分类/冲突/依据不足滥用 | source 有效但不相关 |
| `policy_limit` | 当前 repair feedback 明示具体 cap | 首次/无 cap 禁止猜测；不得隐藏冲突 | source 相关但受 cap 挤出 |

四种 reason 是互斥解释，不是固定优先级 ✓（prompt 第 68 行）。

### 5. Repair Cap

`policy_limit` 的可见来源链：
1. `context_governance.py:492-576`：candidate 超限后生成含具体数值的 issue message
2. `build_compact_repair_feedback_v2`：投影为 repair feedback JSON
3. prompt 第 66 行：告知模型只有收到 repair feedback 且其中有具体 cap 时才能使用
4. 首次请求无 repair feedback → 无具体 cap → 禁止使用 ✓

链闭合。

### 6. Memory Replacement

`session_summary: null` 的 prompt 承诺与 Memory owner 行为一致：
- prompt："candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要"
- `memory.py:1732-1733`：`if summary is None: return _empty_session_summary_memory()`
- `memory.py:1229-1255`：`CONTEXT_COMPACTED` 整体替换五类 memory
- `test_memory_projection.py:1408-1442`：锁定 "without summary clears prior session summary" ✓

### 7. Publication Hash

两级 hash 链独立验证通过（见 Verification Evidence 节）。Chain 闭合，与所有 artifact 记录一致 ✓。

### 8. Frozen Oracle / Scenario / cli_ci.md

`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md` 在范围内无 diff ✓。

### 9. README / Design No-Change

全部 README 与 design 在范围内无 diff。触发判断：
- `dayu/config/README.md`：prompt 自足说明是既有职责，不改变目录职责 ✓
- `tests/README.md`：只强化既有测试，不新增层级 ✓
- 其它：Host contract、分层、装配、用户工作流均未变 ✓

### 10. Tests / Pyright Evidence

- owner test：36 条语义 assertion + 13 条 forbidden-term guard + 既有 schema/source-kind/repair/example 断言 ✓
- public smoke：6 条哨兵 + 完整 example 通过 production parser/accept barrier ✓
- Memory regression：`null` 清除行为锁定 ✓
- pyright：0 errors ✓

### 11. Finding Adjudication

| Finding | 来源 | Controller 裁决 | 状态 |
|---|---|---|---|
| F01（7 项 frozen semantic fragment 缺失） | AgentDS code review | `accepted` | ✓ 已修复（owner test 补齐 7 项独立 assertion） |
| F02（forbidden-term guard 不完整） | AgentDS code review | `accepted` | ✓ 已修复（扩展至 13 项，含 `Compact` 前缀） |
| F03（substring 前缀匹配策略漏检） | AgentDS code review | `rejected-with-reason` | ✓ 与 F01 同根，修复后证据不成立 |
| AgentDS plan F01（`forward_intents.status` 语义缺口） | AgentDS plan review | `deferred-with-owner` | ✓ owner 为后续独立 work unit |
| AgentDS plan F02（hash encoding concern） | AgentDS plan review | `rejected-with-reason` | ✓ `sha256sum` 读 raw bytes，fail closed |

不存在未修复、部分修复、needs-more-evidence 或 deferred code-review finding ✓。

### 12. 无 Overcoupling

变更范围极窄：1 个 prompt 文件 + 3 个测试文件 + 1 个 publication manifest。没有新增类型、模块、helper、schema、状态机、verifier、配置或兼容层。测试依赖方向正确（tests → prompt owner）。不存在跨层穿透、双向依赖或共享可变状态 ✓。

### 13. 无 Semantic Drift

- prompt 承诺的每条语义均与对应 owner（typed contract / Context Governance / Memory projection）的实际行为同源
- 不依赖隐式规则、兼容别名或"你应该知道"的外部上下文
- `policy_limit` 的可见来源链从 Context Governance 到 repair feedback 到 prompt 闭合
- `session_summary: null` 的清除语义与 Memory owner 的 replacement 行为一致
- 四种 drop reason 的互斥性由各自 distinct triggering condition 保证

无 drift ✓。

## Residual Risks

- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。deterministic tests 不能冒充真实模型行为。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- `assigned to later work unit`：`forward_intents.status`（`open`/`blocked`/`superseded`）与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。`superseded` 同时出现在 drop reason 和 `forward_intents.status` 中，模型可能产生跨 section 语义混淆，但 prompt 的 section 结构提供了足够上下文隔离。

所有 residual risk 均已分类并有 owner。无未分类 residual risk。

## Open Questions

无。

## Conclusion

`pass`

PR 190 当前补充 work unit（Compactor 输出业务语义）的完整 committed diff 经 aggregate deepreview 确认：

1. **Shipped semantics 正确**：prompt owner 中的 `session_summary`、`evidence_facts`、`answer_anchors`、四种 drop reason 业务语义均与对应 owner（typed contract、Context Governance、Memory projection）同源，三项用户纠正已完整兑现。
2. **跨 artifact 一致性**：plan frozen semantics → prompt text → owner tests → publication hash chain 全链闭合；review/re-review artifacts 中的 finding adjudication 与实际代码变更一致。
3. **无 overcoupling / semantic drift**：变更范围限于 1 个 prompt 文件 + 3 个测试 + 1 个 manifest，无生产代码修改，无新增类型/模块/schema/状态机。
4. **验证完整**：owner test（36 语义 + 13 forbidden）、public smoke、Memory regression、pyright、两级 publication hash、frozen file preservation 全部通过。
5. **Gateflow 完整**：plan → plan review（2 轮）→ acceptance → implementation → code review（2 轮）→ fix → re-review（2 轮）→ acceptance → commit，每个 gate 有 durable artifact，finding 裁决记录完整。

未发现实质性问题。Residual risks 均已分类并有 later-work-unit owner。
