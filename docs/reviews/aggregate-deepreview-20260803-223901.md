# Aggregate Deepreview — PR 190 Compactor 输出业务语义（第二路独立）

## Scope

- Mode: current changes (aggregate deepreview，第二路独立)
- Branch: `codex/interactive-oracle`
- Base: `62b7d4a2`（plan gate commit）
- PR: #190 (`fix(cli): close interactive conformance gaps`, author: noho, state: OPEN)
- Output file: `docs/reviews/aggregate-deepreview-20260803-223901.md`
- Review focus: `62b7d4a2..HEAD` 全部 committed diff，聚焦最终 shipped prompt/owner tests/hash 与 plan/review/acceptance artifact 一致性
- Included scope: 2 个 committed commits（`21b602c1` plan acceptance + `11b63911` S1 acceptance），涉及 20 files changed，2387 insertions，11 deletions
- Excluded scope: 无（全部 committed diff 均在 review 范围内）
- Parallel review coverage: 无（本次为单 reviewer 全程独立走读与独立摘要验证）
- 独立性声明：本 review 未读取第一路 aggregate deepreview（`docs/reviews/aggregate-deepreview-20260803-223339.md`），所有结论仅基于 `62b7d4a2..HEAD` committed diff、独立摘要计算与直接 owner 代码走读

## Commits in Range

| Commit | Message |
|---|---|
| `21b602c1` | `gateflow: accept plan for compactor output business semantics` |
| `11b63911` | `gateflow: accept compactor output business semantics S1` |

## Changed Files Summary

### Production（1 file）

| File | Change |
|---|---|
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | 在 output schema 字段旁补齐 `session_summary`、`evidence_facts`、`answer_anchors` 与四种 drop reason 的 LLM-facing 业务语义（约 37 行新增） |

### Tests（3 files）

| File | Change |
|---|---|
| `tests/host/test_llm_compaction.py` | 扩充 packaged prompt owner test：36 条业务语义 assertion（按 4 section 分组）+ 13 条 forbidden-term guard（含代码 review fix 补齐的 7 项 frozen fragment 与 8 项 forbidden guard） |
| `tests/host/test_public_compact_smoke.py` | 在默认真实装配路径添加 6 条最小语义哨兵 + 4 条 drop reason 哨兵 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 更新 `FROZEN_MANIFEST_SHA256`（manifest bytes 派生变化） |

### Publication（1 file）

| File | Change |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | 更新 `conversation_compaction_user.md` 条目的 `content_sha256` |

### Gateflow Artifacts（6 files，见 committed diff）

### Review Artifacts（10 files，见 committed diff）

## Independent Verification Evidence

### L0: Prompt hash

```bash
$ sha256sum dayu/config/prompts/scenes/conversation_compaction_user.md
a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce
```

Manifest entry（`docs/cli_init_workspace_manifest_v1.json:40`）：`content_sha256: a2f5711c...` ✓ 一致

### L1: Manifest hash

```bash
$ sha256sum docs/cli_init_workspace_manifest_v1.json
fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c
```

### L2: Frozen manifest constant

`tests/cli/test_smoke_cli_init_provider_matrix.py:95-97`：`FROZEN_MANIFEST_SHA256 = "fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c"` ✓ 与 L1 一致

### Hash chain conclusion

L0 → manifest entry → L1 → FROZEN_MANIFEST_SHA256 全链闭合。

### Forbidden-term independent check

对 prompt 全文独立搜索 13 个 forbidden term（`Compact`、`compaction.py`、`context_governance`、`memory.py`、`MemoryProjectionPolicy`、`SessionSummaryMemoryView`、`event_id`、`payload_ref`、`schema_version`、`current_input_anchor`、`previous_compacted_view`、`evidence_backed_facts`、`reference_continuity_items`）：全部 absent ✓。

`Compact` 大小写敏感检查确认 prompt 中无任何 `Compact*` 出现（`compaction` 仅以 schema identifier `dayu.context_compaction.input.v2` / `dayu.context_compaction.output.v2` 与 `<<compaction_request>>` marker 的小写形式出现，不触发 forbidden guard）。

### Frozen files preservation

| 文件 | `62b7d4a2..HEAD` diff |
|---|---|
| `dayu/host/compaction.py` | 无 ✓ |
| `dayu/host/context_governance.py` | 无 ✓ |
| `dayu/host/memory.py` | 无 ✓ |
| `dayu/config/prompts/scenes/conversation_compaction.md` | 无 ✓ |
| `dayu/config/prompts/manifests/conversation_compaction.json` | 无 ✓ |
| `dayu/config/execution_profiles.json` | 无 ✓ |
| `docs/cli_ci_oracles.json` | 无 ✓ |
| `docs/cli_ci_scenarios.json` | 无 ✓ |
| `docs/cli_ci.md` | 无 ✓ |
| 全部 README、全部 design | 无 ✓ |

### Durable input preservation

| File | Plan 记录 SHA-256 | 独立计算 SHA-256 | 一致 |
|---|---|---|---|
| `docs/reviews/pr-190-review-20260803-203709.md` | `e7add55e...` | `e7add55e...` | ✓ |
| `docs/reviews/plan-review-20260803-212134.md` | `1d592ae4...` | `1d592ae4...` | ✓ |

### Test validation（独立执行）

| 测试 | 结果 |
|---|---|
| `test_prompt_assets_are_self_contained_for_fresh_v2_contract` | ✓ 1 passed |
| `test_default_compactor_prompt_is_llm_facing_and_self_contained` | ✓ 1 passed |
| `test_accepted_compact_without_summary_clears_prior_session_summary` | ✓ 1 passed |
| publication/config assembly suite（`test_smoke_cli_init_provider_matrix` + `test_config_loader` + `test_host_assembly`） | ✓ 267 passed, 3 warnings（第三方 `edgar` deprecation） |
| `python -m pyright` on changed files | ✓ 0 errors, 0 warnings, 0 informations |

### Owner test coverage completeness（独立验证）

对 prompt 中 36 项 frozen business semantics fragment 逐一比对 owner test 的 `assert ... in user_prompt`：

全部 36 项在 owner test 的四个 section for loop 中有独立 assertion ✓。F01 修复补齐的 7 项（`不得发明新结论`、`继续保留旧内容会过时、冲突或误导`、`replacement 中保留的是替代后的当前内容`、`丢弃它不会损失独立业务信息`、`不得加入材料没有的事实、结论或任务`、`不得把 trace_material 或 answer_material 当作事实依据`、`不把工具证据、未来动作或新推断伪装成既有结论`）均通过独立 grep 确认存在于 test 中。

## Findings

未发现实质性问题。

### 说明：为什么写"未发现"

本次独立 review 从以下维度对 `62b7d4a2..HEAD` committed diff 做了逐文件、逐语义片段、逐 hash 链的独立走读与独立摘要验证，所有检查结果均与 plan/review/acceptance artifact 记录一致：

1. **AGENTS.md LLM-facing 北极星**：prompt 文本只写模型完成任务所需的动作、输入、输出、判断规则与禁止事项；无内部类型名、模块名、Host 实现术语；字段含义、类型、必填性、允许值自足说明；`source_label` 被多次说明为"引用标签，不是业务事实或推理依据"（system prompt 第 13 行 + user prompt 第 36、87 行 + repair feedback 第 91 行）；未把系统状态伪装成财报事实。

2. **`session_summary: null`**：prompt 第 34 行完整说明："本次完整 replacement 不包含 session summary；candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要，但不影响同一 candidate 中其它四类业务语义项"。与 `memory.py:1732-1733`（`if summary is None: return _empty_session_summary_memory()`）同源，与 `memory.py:1229-1255`（`CONTEXT_COMPACTED` 整体替换五类 memory）一致，与 `test_memory_projection.py:1408-1442`（"without summary clears prior session summary"）同源。

3. **`claim` 双来源**：prompt 第 39 行显式要求 `support_labels` 只能引用 `evidence_material` 或 `previous_evidence_fact`；第 40 行负向约束"不得把 `trace_material` 或 `answer_material` 当作事实依据"。与 `COMPACT_FACT_SOURCE_KINDS_V2 = (PREVIOUS_EVIDENCE_FACT, EVIDENCE_MATERIAL)`（`compaction.py:98-101`）一致。

4. **`context_labels`**：prompt 第 41 行明确"不能直接支持 `claim`，也不能弥补缺失或不充分的 `support_labels`"。与 `COMPACT_FACT_CONTEXT_SOURCE_KINDS_V2 = (TRACE_MATERIAL, ANSWER_MATERIAL)`（`compaction.py:104-108`）一致。

5. **`answer_anchors`**：prompt 第 43-46 行覆盖 section 职责（不伪装工具证据/未来动作/新推断）、title（主题标签）、detail（既有结论 + 条件/边界，不发明新结论）、source_labels（`answer_material` 或 `previous_answer_anchor`）。与 `COMPACT_ANSWER_SOURCE_KINDS_V2 = (PREVIOUS_ANSWER_ANCHOR, ANSWER_MATERIAL)`（`compaction.py:110-114`）一致。

6. **四种 drop reason**：各有正向条件与负向禁止，互斥性由 distinct triggering condition 保证。

   | Reason | 正向触发条件 | 负向禁止 |
   |---|---|---|
   | `superseded` | 被更新/更完整/更权威替代 | 保留会过时/冲突/误导 |
   | `redundant` | 内容仍有效但已完整表达 | 不得掩盖冲突或遗漏 |
   | `out_of_scope` | 与任务/可预见后续无关 | 不得因难分类/冲突/依据不足滥用 |
   | `policy_limit` | 当前 repair feedback 明示具体 cap + 必须舍弃才满足 cap | 首次/无 repair feedback/无具体 cap 禁止猜测；不得隐藏冲突 |

   Line 68 声明"四种 reason 是对 source 实际业务关系的互斥解释，不是固定优先级"。

7. **`policy_limit` 具体 cap 链**：
   - `context_governance.py:492-577`：`_collect_policy_issues` 用 `MemoryProjectionPolicy` 的具体 cap 值生成 issue message（如 `"上限 {policy.session_summary_char_cap} 个字符"`）
   - `context_governance.py:117-147`：`build_compact_repair_feedback_v2` 将 issue 投影为 typed repair feedback
   - prompt 第 66 行：告知模型只有"当前 repair feedback 已明确给出一个具体 cap"时才可用 `policy_limit`
   - 首次请求无 repair feedback → 无具体 cap → 禁止使用
   - 链闭合，且无 cap 的 repair feedback（如仅有 `UNCOVERED_SOURCE` issue）不会授权 `policy_limit`

8. **Memory / Host owner**：prompt 语义全部与唯一 owner（`conversation_compaction_user.md`）一致；`compaction.py` 独占 typed shape/enum/strict parse（未修改）；`context_governance.py` 独占 accept/reject/coverage/policy cap（未修改）；`memory.py` 独占 accepted candidate 完整 replacement 投影（未修改）。

9. **Forbidden guard**：owner test 的 13 项 forbidden-term guard 覆盖当前活跃内部术语（v1 历史 5 项 + `Compact` 前缀 + `compaction.py`/`context_governance`/`memory.py` + `MemoryProjectionPolicy`/`SessionSummaryMemoryView` + `event_id`/`payload_ref`）。`Compact` 为大小写敏感匹配，不误禁业务所需的小写 schema identifiers。

10. **Frozen registry**：frozen oracle、frozen scenario、`cli_ci.md`、execution profiles、scene manifests 全部 preserved（`62b7d4a2..HEAD` 无 diff）。

11. **README / design no-change**：全部 README 与 design 在范围内无 diff。触发判断——`dayu/config/README.md`（prompt 自足是既有职责）、`tests/README.md`（强化既有测试）、Host/design（contract/状态机未变）、根 README（用户工作流未变）、`dayu/README.md`（分层/装配未变）——均正确。

12. **Review finding 裁决**：

    | Finding | 来源 | Controller 裁决 | 独立核实 |
    |---|---|---|---|
    | F01（7 项 frozen semantic fragment 缺失） | AgentDS code review | `accepted` | ✓ 已修复：owner test 中每项有独立 assertion |
    | F02（forbidden-term guard 不完整） | AgentDS code review | `accepted` | ✓ 已修复：扩展至 13 项 |
    | F03（substring 前缀匹配漏检） | AgentDS code review | `rejected-with-reason` | ✓ 合理：与 F01 同 root cause，F01 修复后证据不成立 |
    | AgentDS plan F01（`forward_intents.status`/`reference_continuity.reason` 语义缺口） | AgentDS plan review | `deferred-with-owner` | ✓ owner 为后续独立 work unit |
    | AgentDS plan F02（hash encoding concern） | AgentDS plan review | `rejected-with-reason` | ✓ `sha256sum` 读 raw bytes，fail closed |

    无未修复、部分修复、needs-more-evidence 或 deferred code-review finding。

13. **Overcoupling**：变更范围极窄——1 个 prompt + 3 个测试 + 1 个 publication manifest。无新增类型、模块、helper、schema、状态机、verifier、配置或兼容层。测试依赖方向正确（tests → prompt owner）。无跨层穿透、双向依赖或共享可变状态。

14. **Semantic drift**：prompt 的每条语义均与对应 owner（typed contract / Context Governance / Memory projection）的实际行为同源。`policy_limit` 可见来源链从 Context Governance → repair feedback → prompt 闭合。`session_summary: null` 清除语义与 Memory owner replacement 行为一致。四种 drop reason 互斥性由各自 distinct triggering condition 保证。无 loose parsing、fallback、兼容 shim、默认值或下游补偿。

15. **测试证据**：owner test（36 语义 + 13 forbidden + 既有 schema/source-kind/repair/example 断言）、public smoke（6 哨兵 + 完整 example 通过 production parser/accept barrier）、Memory regression（`null` 清除行为锁定）、publication/config assembly（267 passed）、pyright（0 errors）。

16. **系统 prompt 一致性检查**：`conversation_compaction.md`（system prompt）与 `conversation_compaction_user.md`（user prompt）无矛盾。System prompt 无 stale reference、无内部术语泄漏。System prompt 委托用户消息定义字段语义（"严格遵守用户消息中列出的字段名、类型、必填性、允许值和 source-kind 引用规则"），与 user prompt 的 self-contained 定位一致。

## 核验清单（与用户指定要点逐一对应）

| # | 核验项 | 结论 |
|---|---|---|
| 1 | AGENTS.md 北极星 | ✓ prompt 遵守 LLM-facing 文本约束 |
| 2 | `session_summary: null` | ✓ 清除语义与 Memory owner 同源 |
| 3 | `claim` 双来源 | ✓ `evidence_material` + `previous_evidence_fact` 显式声明 |
| 4 | `policy_limit` 具体 cap | ✓ 可见来源链闭合，首次请求无 cap 时禁止 |
| 5 | 四种 reason | ✓ 各有正向/负向定义，互斥不固定优先级 |
| 6 | Memory / Host owner | ✓ prompt 是唯一 LLM-facing owner，Host 三模块未修改 |
| 7 | forbidden guard | ✓ 13 项覆盖当前活跃内部术语，prompt 干净 |
| 8 | frozen registry | ✓ oracle/scenario/cli_ci/execution profiles/scene manifests preserved |
| 9 | README / design no-change | ✓ 全部无 diff，触发判断正确 |
| 10 | review finding 裁决 | ✓ 所有 finding 已关闭或 deferred |
| 11 | overcoupling | ✓ 无 |
| 12 | semantic drift | ✓ 无 |
| 13 | 测试证据 | ✓ 独立摘要验证 36 项全覆盖 + 独立测试执行通过 |

## Open Questions

无。

## Residual Risk

- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。Deterministic tests 不能冒充真实模型行为。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- `assigned to later work unit`：`forward_intents.status`（`open`/`blocked`/`superseded`）与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。

关于 `forward_intents.status` 的 residual risk 补充说明：当前 prompt 只定义枚举字面量但未定义各值业务含义。`superseded` 同时出现在 `explicitly_dropped_sources.reason`（有完整业务定义）和 `forward_intents.status`（无业务定义）中——模型可能将 drop reason 的 `superseded` 语义误用到 forward_intent status 上。不过 prompt 的 section 结构提供了上下文隔离，且该 gap 已被 controller 明确 `deferred-with-owner`，不属于当前 work unit 的 scope。

所有 residual risk 均已分类并有 owner。无未分类 residual risk。

## Conclusion

`pass`

PR 190 当前补充 work unit（Compactor 输出业务语义）的 `62b7d4a2..HEAD` 完整 committed diff 经第二路独立 aggregate deepreview 确认：

1. **Shipped semantics 正确**：prompt owner 中 `session_summary`（含 `null` 清除）、`evidence_facts`（含 claim 双来源、context_labels 约束）、`answer_anchors`（含不伪装/不发明约束）、四种 drop reason（含 `policy_limit` cap 前提链）的业务语义均与对应 typed contract / Context Governance / Memory projection owner 同源，三项用户纠正完整兑现。
2. **跨 artifact 一致性**：plan frozen semantics → prompt text → owner tests → publication hash chain 全链闭合；review/re-review artifacts 的 finding adjudication 与实际代码变更一致；所有 claim 经独立摘要验证。
3. **无 overcoupling / semantic drift**：变更限于 1 个 prompt + 3 个测试 + 1 个 manifest，无生产代码修改，无新增类型/模块/schema/状态机。
4. **验证完整**：owner test（36 语义 + 13 forbidden）、public smoke、Memory regression、publication/config assembly、pyright、两级 hash 链、frozen file preservation、durable input preservation 全部独立验证通过。
5. **Gateflow 完整**：plan → plan review（2 轮）→ acceptance → implementation → code review（2 轮）→ fix → re-review（2 轮）→ acceptance → commit，每个 gate 有 durable artifact，finding 裁决记录完整。

历史已修复 finding（F01/F02）经独立核实确认已修复，未重报为未修复。未发现实质性问题。
