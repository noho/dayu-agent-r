# PR 190 S5 registry/docs implementation — 独立对抗性深审

## 审阅元数据

- **审阅类型**: 独立对抗性深审（不依赖 MiMo review，独立机器验证 + 人工走读）
- **审阅目标**: PR 190 F11/F12 S5 registry/docs implementation slice
- **审阅基线**: `1a79ff1859117027340910152c0ce208a7f37b5d`（MiMo review 记录基线 HEAD）
- **审阅范围**: 五个授权实现文件（`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md`、`docs/reviews/wu-interactive-memory-postfix-readiness.md`、`docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`（MiMo review，只读参照））
- **审阅方法**: 独立重跑全部决定性机器检查 + 逐记录走读 oracle/scenario diff + predicate contract 对比 + evidence root 验证 + 交叉引用完整性扫描
- **审阅日期**: 2026-08-06
- **输出文件**: `docs/reviews/pr-190-f11-f12-s5-registry-ds-review-20260806.md`

## 审阅声明

本审阅是独立对抗性深审：不依赖 MiMo review artifact 中的结论或验证数据，仅将其作为上下文参照；所有机器检查从零独立重跑，所有判断基于直接代码/数据证据。

## 审阅结论总览

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 旧 record 逐字节保留（除 lifecycle 字段） | **PASS** | 4 条 lifecycle-normalized SHA-256 base≡current |
| 其它旧 record 不变 | **PASS** | 2 oracle + 1053 scenario exact equal |
| 1056 条历史 `accepted_oracle_refs` 不变 | **PASS** | 逐条对比 0 变化 |
| 稳定 predicate refs 唯一解析 | **PASS** | 66 predicates, 0 dangling, 0 duplicate current owner |
| 全部 `oracle_predicate_refs` 解析 | **PASS** | 1614 total refs, 0 unresolved |
| Supersession graph 有效 | **PASS** | 0 dangling, 0 cycle, 0 asymmetric edge（oracle + scenario） |
| Registry schema 有效 | **PASS** | JSON validity + 类型/结构检查 |
| 新 oracle/scenario 正确替换 drop-ledger contract | **PASS** | predicate 29/30 contract 对比 |
| Replacement scenario unadjudicated | **PASS** | 3/3 status=unadjudicated, pending-oracle-controller-adjudication |
| Evidence root/report/digest 真实 | **PASS** | 路径存在 + SHA-256 exact match + 全部 relative refs 可访问 |
| Secret scan | **PASS** | 0 findings |
| Readiness frozen prefix 精确 | **PASS** | byte-identical to baseline |
| 当前文件 digest | **PASS** | 与 MiMo review 声称一致 |
| Registry 顶层 `registry_status` | **PASS** | 两者均为 `calibration` |
| 兼容性别名 | **PASS** | 未发现 |
| 隐藏旧 contract 依赖 | **PASS** | 未在当前（非 superseded）scenario 中发现 ledger 概念 |
| 语义所有权漂移 | **PASS** | 未发现 |

**最终裁决: PASS** — 五个授权文件变更经过独立对抗性验证，所有决定性机器检查通过，未发现实质缺陷。

---

## 决定性机器检查

以下所有检查均为独立运行，不依赖 MiMo review 的输出或中间结果。

### 1. JSON 有效性与结构完整性

```text
python -m json.tool docs/cli_ci_oracles.json → PASS
python -m json.tool docs/cli_ci_scenarios.json → PASS
```

- Oracle inventory: 4 records（`cli.init.workspace-initialization@1`, `cli.prompt.core-execution@1`, `cli.interactive.core-execution@1`, `cli.interactive.core-execution@2`）
- Scenario inventory: 1059 records（1056 baseline + 3 new replacement）
- 4/1059 unique keys, 0 duplicate

### 2. 旧 record 逐字节保留（lifecycle 归一化）

对四条受影响的旧 record，删除唯一允许变化的 `status` 与 `superseded_by` 后计算 compact sorted JSON SHA-256，base≡current:

| Record | Lifecycle-normalized SHA-256 | Match |
| --- | --- | --- |
| `cli.interactive.core-execution@1` | `d28bec703838dcd57ed827a39b1a976c8bc39c3c5f733b1417f928677cfe92d4` | PASS |
| `interactive.interactive.g06.tool-trace-formal@1` | `462355690e5ba61925231c7da23e732ad667bb4a1a13853eb45f4c6fe5724318` | PASS |
| `interactive.interactive.g06.drop-superseded@1` | `55d6dd21c4339c3e16ae4cecf18e1c2bf68ba8125daeb873d9469972ce005a01` | PASS |
| `interactive.interactive.g06.drop-policy-limit@1` | `ab05fc91b8dcc238055aba4c8a27593eb3434516ef45daf054c4f2512183d000` | PASS |

只有 `status`（`accepted→superseded`）和 `superseded_by`（`null→<new_version>`）变更；所有其它字段逐字节一致。

另外 2 条 oracle（`cli.init.workspace-initialization@1`, `cli.prompt.core-execution@1`）与 1053 条其它 scenario exact equal。

### 3. 历史 `accepted_oracle_refs` 冻结

1056 条 baseline scenario 的 `accepted_oracle_refs` 全部 exact equal — 0 批量改写。符合 docs 声明："`accepted_oracle_refs` 只记录 scenario 获裁决时所依据的 oracle version，oracle lifecycle replacement 不得批量改写这些历史引用。"

### 4. 稳定 predicate 当前解析

构建 `predicate_id → current accepted owner` 映射（status=accepted, superseded_by=null）：

```text
Total stable predicates: 66
Dangling: 0
Duplicate current owners: 0
```

全部 1614 个 `oracle_predicate_refs`（跨 1059 scenarios）解析成功，0 unresolved。

Predicate ref 分布：
- `cli.interactive.core-execution@2`: 770 refs（含 baseline 766 + 新增 4）
- `cli.prompt.core-execution@1`: 728 refs
- `cli.init.workspace-initialization@1`: 116 refs

### 5. Supersession graph

Oracle 层：`core@1 → core@2`（core@2.supersedes=core@1, core@1.superseded_by=core@2）

Scenario 层：
- `tool-trace-formal@1 → tool-trace-formal@2`
- `drop-superseded@1 → rolling-correction-replacement@1`
- `drop-policy-limit@1 → cap-constrained-memory-replacement@1`

全部 edge 双向可解析，0 dangling, 0 cycle, 0 asymmetric。

### 6. Evidence root 完整性

```text
Root: /Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY
```

- `observed-report.md` SHA-256: `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411` → **MATCH**
- `digest.json` SHA-256: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` → **MATCH**
- `metadata/secret-scan.json`: 0 findings → **PASS**
- 全部 relative refs（18 个文件/目录）可访问 → **PASS**

### 7. Readiness frozen prefix

```text
diff <(git show HEAD:docs/reviews/wu-interactive-memory-postfix-readiness.md) \
     <(head -130 docs/reviews/wu-interactive-memory-postfix-readiness.md)
→ 0 differences
```

"## Final implementation status appended on 2026-08-06" 之前的所有原文逐字节保留。

### 8. 当前文件 digest

| 文件 | 实际 SHA-256 | MiMo 声称 | Match |
| --- | --- | --- | --- |
| `docs/cli_ci_oracles.json` | `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf` | 同 | PASS |
| `docs/cli_ci_scenarios.json` | `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37` | 同 | PASS |

---

## Predicate contract 替换分析

### core@1 → core@2: predicate 29（compactor-output-accept-repair-fallback）

**core@1 expected[1]**（旧，已删除的语义）：
> "input source boundary与represented/explicitly-dropped semantic coverage是不同typed facts；Conversation Memory只能按accepted coverage删除raw item。"

**core@2 expected[1]**（新）：
> "v3 initial request必须包含immutable input、真实output caps、nullable summary语义与同源完整结构；strict parser拒绝missing/unknown/duplicate keys、错误nested shape与旧v2字段，Host拒绝全空、无有效provenance、重复semantic item或超过同源cap的candidate。"

**core@2 forbidden[0]**（新增禁止项）：
> "要求模型生成omission ledger、drop reason、cap归因或其它Host可机械派生的治理事实。"

**分析**: core@1 要求模型产出 represented/explicit-drop 语义；core@2 明确禁止模型产出 omission ledger/drop reason/cap attribution，将这些治理事实的 ownership 收归 Host。`expected[0]` 中的 "represented" 是描述 Host 从 provenance 派生补集的能力，不是要求模型产出。替换正确。

### core@1 → core@2: predicate 30（compaction-semantic-memory-closure）

**core@2 forbidden[0]**（新增）：
> "要求模型为每个omitted source生成ledger、自然语言reason、cap attribution或主观新旧关系。"

**core@2 forbidden[2]**（新增）：
> "把raw history中保留的旧文本重新投影成active Semantic Memory或当前RunInput结论。"

**分析**: 两条新增禁止项精确对应 F11/F12 replacement contract：禁止模型产出 ledger/reason/cap attribution（收归 Host），禁止 raw history 污染 active semantic truth。替换正确。

### 替换 summary

- core@1 要求模型产出 4 类 reason、policy_limit、represented/explicit-drop ledger → **全部移除**
- core@2 要求模型只产出 5 类业务语义 + 必要 provenance → **正确**
- Host 拥有 represented/omitted exact complement、caps、usage audit、bounded repair/fallback、accepted truth → **正确**
- 30 个 predicate_id 全部保留，只替换 29/30 的 contract 文本 → **正确**

---

## Scenario replacement 分析

### tool-trace-formal@1 → tool-trace-formal@2

| 维度 | @1（旧） | @2（新） |
| --- | --- | --- |
| required_evidence | `formal-tool-trace-query-result`, `runner-call-manifest-and-input-projection`, `provider-model-response-identity`, `eventlog-payload-descriptor-correlation`, `secret-scan` | `public-host-tool-trace-resolver-and-analysis-response-identity`, `canonical-terminal-response-identity-equality`, `secret-scan` |
| accepted_oracle_refs | `cli.interactive.core-execution@1` | `cli.interactive.core-execution@2` |

**分析**: 旧 evidence 要求依赖 EventLog payload descriptor correlation 和 runner-call manifest（内部投影），新 evidence 只要求 public Host Tool Trace resolver 与 canonical terminal equality。F11 的 public projection 替换正确，Host governance 未弱化。

### drop-superseded@1 → rolling-correction-replacement@1

| 维度 | @1（旧） | @2（新） |
| --- | --- | --- |
| required_evidence | `accepted-candidate-explicit-drop`, `memory-artifact-runinput`, `cross-process-consumption`, `formal-tool-trace`, 等 | `retained-current-replacement-provenance`, `host-derived-omitted-old-labels`, `compact-artifact-memory-post-compact-runinput-without-old-conclusion`, `cross-process-reconnect-without-old-conclusion` |

**分析**: 旧 evidence 要求 "accepted-candidate-explicit-drop"（模型产出 drop ledger），新 evidence 要求 Host-derived omitted old labels + reconnect 无旧结论。Host governance 强化（from model-ledger to Host-derivation）。

### drop-policy-limit@1 → cap-constrained-memory-replacement@1

| 维度 | @1（旧） | @2（新） |
| --- | --- | --- |
| required_evidence | `explicit-cap-and-accepted-policy-limit-drop`, `initial-rejection-and-repair-feedback`, 等 | `real-output-caps-in-initial-input`, `host-cap-and-usage-audit`, `accepted-provenance-and-omitted-exact-complement`, `same-boundary-bounded-repair-and-budget-exhausted-fallback`, `compact-artifact-memory-runinput-and-reconnect-same-truth` |

**分析**: 旧 evidence 要求 policy-limit-drop（模型归因），新 evidence 要求 Host cap/usage audit + accepted provenance + omitted exact complement + bounded repair/fallback。Host governance 强化。

### 三条 replacement scenario 的 adjudication 状态

全部三条：
- `status`: `unadjudicated`
- `user_adjudication_identity`: `pending-oracle-controller-adjudication`
- `applicable_from`: `after-oracle-controller-adjudication`
- `evidence_status`: `sufficient`（S4 真实观察完整）
- `conformance_at_observation`: `oracle-review-pending`

**结论**: 未将 S4 evidence observation 自动投影为 accepted scenario。正确。

---

## 对抗性扫描

### Removed-ledger 全 registry 扫描

Oracle 层命中：
- `core@1` predicate 29（`represented` — 旧 contract 中，预期且已 superseded）
- `core@1` predicate 30（`policy_limit` — 旧 contract 中，预期且已 superseded）
- `core@2` predicate 29（`represented` — 在 expected[0] "Host...派生represented/omitted精确补集" 中，是 Host 能力描述而非模型要求；verified: forbidden[0] 明确禁止模型产出）

Scenario 层命中：
- `drop-superseded@1` required_evidence 含 `explicit-drop`（已 superseded → 预期）
- `drop-policy-limit@1` required_evidence 含 `policy-limit`（已 superseded → 预期）

**当前（status≠superseded）scenario 中 0 命中** — 未发现计划外 ledger 依赖。

### 兼容性别名扫描

- 所有 oracle/scenario ID 唯一，无旧名复用
- 所有 version 为正整数
- 无兼容性 re-export、wrapper 或 facade

### 语义所有权漂移检查

- Oracle lifecycle: oracle registry 拥有 current accepted predicate contract → 正确
- Scenario evidence: scenario registry 拥有 versioned observation obligation → 正确
- Current resolution: 按 stable `predicate_id` 动态解析 → 正确（不是 consumer 反推）
- 三个 replacement scenario 的 evidence 未被错误投影为 accepted readiness proof → 正确

### 交叉命令引用

两个 prompt scenario（PX01、PX02）的 `accepted_oracle_refs` 包含 `cli.interactive.core-execution@1`（现在 superseded）。这是预期的历史冻结行为：
- `accepted_oracle_refs`: 记录 scenario 获裁决时的 oracle version → 不迁移（per docs）
- `oracle_predicate_refs`: 动态按 stable predicate ID 解析到 `cli.interactive.core-execution@2` → verified correct
- 这两个 scenario 的 status 仍为 `accepted`，但 `interactive.03-label-is-cross-entry-conversation-alias` predicate 通过 stable ID 正确解析到 current core@2

**结论**: 交叉命令引用通过 stable predicate ID 正确解析，不存在因 oracle supersession 导致的 dangling resolution。

---

## Findings

### 1-未修复-低-MiMo review 中稳定 predicate 计数与实际 inventory 不一致

- **入口/函数**: MiMo review artifact 第 110 行验证表 "stable predicate current resolution" 行
- **文件(行号)**: `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md:111`
- **输入场景**: N/A — 文档一致性检查
- **实际分支**: N/A
- **预期行为**: 稳定 predicate_id 数量应与实际 oracle inventory 一致
- **实际行为**: MiMo review 声称 "29 stable predicate ids, 0 dangling, 0 duplicate current owner"，但实际 oracle 定义 30 个稳定 predicate_id（`interactive.01` 至 `interactive.30`），其中 baseline scenarios 中 28 个有引用，2 个（`interactive.10-idle-ctrl-c`、`interactive.17-idle-escape-and-sequences`）当前零引用。
- **直接证据**: 独立 inventory 扫描确认 oracle 中 30 个 predicate_id，非 29 个。MiMo 可能只统计了 baseline 中有 scenario 引用的 predicates + 1，但 oracle 本身定义是 30。
- **影响**: 文档歧义，不影响 oracle/scenario 语义正确性或 resolution 行为。零引用的 predicate 10 和 17 仍作为已接受的 stable predicate 存在于 oracle 中，未来 scenario 可以引用它们。
- **建议改法和验证点**: 不修改实现文件。建议 MiMo review 将 "29 stable predicate ids" 修正为 "30 stable predicate ids（其中 28 有当前 scenario 引用，2 零引用但 predicate 有效）"。
- **修复风险（低）**: 仅文档修正。
- **严重程度（低）**: 不影响 correctness、stability 或 registry 完整性。仅 MiMo review artifact 中的计数歧义。

### 2-未修复-低-609 条 active scenario 的 frozen accepted_oracle_refs 指向已 superseded oracle

- **入口/函数**: Scenario registry 中的 `accepted_oracle_refs` 字段
- **文件(行号)**: `docs/cli_ci_scenarios.json` — 609 条 status≠superseded 的 scenario
- **输入场景**: 任何人直接读取 `accepted_oracle_refs` 字段而不通过 `oracle_predicate_refs` 做 stable predicate ID 动态解析
- **实际分支**: N/A — 这是数据层面的历史冻结行为
- **预期行为**: 按 docs 声明，`accepted_oracle_refs` 是历史冻结字段，只记录 scenario 获裁决时的 oracle version；current resolution 使用 `oracle_predicate_refs` + stable predicate ID
- **实际行为**: 609 条 active scenario 的 `accepted_oracle_refs` 包含 `cli.interactive.core-execution@1`（已 superseded），但其 `oracle_predicate_refs` 通过 stable predicate ID 正确解析到 `cli.interactive.core-execution@2`
- **直接证据**: 独立 inventory 扫描确认 609 条 scenario 的 frozen refs 指向 @1，同时全部 770 个 interactive `oracle_predicate_refs` 均正确解析到 @2（0 unresolved）
- **影响**: 如果未来有消费者直接用 `accepted_oracle_refs` 做 current resolution 而不通过 stable predicate ID 动态解析，会得到错误的 superseded oracle。当前 docs 已明确两阶段解析规则，但数据层面的 dual-ref 模式（frozen 旧 + dynamic 新）增加了 registry 读者的认知负担。
- **建议改法和验证点**: 不修改实现。建议在 `docs/cli_ci.md` 或 registry README 中增加一个显式的 "如何读取 registry" 示例，展示 frozen `accepted_oracle_refs` vs dynamic `oracle_predicate_refs` 的不同用途。该改进可由后续 work unit 执行。
- **修复风险（低）**: 纯文档改进。
- **严重程度（低）**: 不是功能缺陷。当前两层解析规则已正确实施且可验证；风险仅在于未来维护者可能误解数据语义。

---

## Open Questions

1. PX01/PX02 自身是否需要 lifecycle update？这两个 prompt scenario 的 frozen `accepted_oracle_refs` 包含 `cli.interactive.core-execution@1`，其 `oracle_predicate_refs` 中 `interactive.03-label-is-cross-entry-conversation-alias` 正确解析到 @2。按当前文档规则，它们不需要更新。但若未来 interactive core-execution 再次发生 replacement（@2→@3），这两个 prompt scenario 的 `accepted_oracle_refs` 将指向 @1 而动态解析指向 @3，间隔更大。该 concern 是 future work unit 的讨论范围，不阻塞当前 S5。

2. Predicate 10（idle-ctrl-c）和 17（idle-escape-and-sequences）当前零 scenario 引用。它们是已接受的 stable predicate，但在当前 scenario registry 中无对应 formal scenario。这不算 gap（predicate 本身仍有效），但值得在后续 calibration campaign 中关注是否需要补充 scenario。

---

## Residual Risk

1. **Oracle controller 未完成裁决**: 三条 replacement scenario 的 formal Oracle 仍为 pending。当前 S5 正确地将它们标记为 `unadjudicated`，不参与正式覆盖率或 readiness proof。但如果 Oracle controller 后续 reject 任何一条 replacement scenario，对应的 `supersedes` 链需要回退或建立 alternative。该风险 ownership 属于 Oracle controller，不在 S5 scope 内。

2. **Reconnect raw history 的语义边界**: S4 observation 确认 reconnect 回答中旧数值仅以"已失效历史值"出现。当前 predicate 30 forbidden[2] 明确禁止 raw history 重新投影为 active semantic truth。但未来的 Oracle 裁决需要在该边界上做出更精确的区分（audit trail vs semantic reintroduction）。风险属于 Oracle controller，registry 当前状态正确。

3. **Immutable evidence root 的持续保留**: evidence root 在本地文件系统中可访问且 digest 匹配。长期保留（跨月/跨年）由 CLI CI evidence-retention owner 负责，不在 registry scope 内。Registry 已固定 root/report/manifest identity 与 digest，当前不存在 integrity gap。

4. **Uncovered areas**: 本审阅未运行 pytest/coverage/pyright（五个授权文件无 Python/schema 变更），未运行 frozen formal CLI scenarios（S5 stop boundary）。这些省略不替代代码 gate 的对应验证。

---

## 审阅后记

本审阅独立重跑了 MiMo review 中所有决定性机器检查，全部通过。此外额外执行了对抗性 removed-ledger 全 registry 扫描、兼容性别名扫描、语义所有权漂移检查和交叉命令引用完整性验证。两条低严重度 finding 不阻塞 S5 通过，建议在后续 work unit 中处理。

未修改五个实现文件或任何代码。未 commit、未 push。
