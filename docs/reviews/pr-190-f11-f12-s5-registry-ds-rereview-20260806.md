# PR 190 S5 registry/docs — DS re-review（2026-08-06）

## Re-review 元数据

- **Re-review 类型**: DS finding 闭合验证 + 独立全量复算（不依赖 MiMo、不依赖第一次 DS review 的中间结论）
- **审阅基线**: `1a79ff1859117027340910152c0ce208a7f37b5d`
- **审阅范围**: 全部 S5 review/fix/adjudication artifacts + 当前 registry/docs 工作树状态
- **审阅目标**:
  1. 验证 DS finding 1 是否通过精确、互斥的 inventory 术语与精确 owner identity 闭合
  2. 验证 DS finding 2 与两条 open question 是否被正确裁决，无未授权 registry 变更
  3. 独立复算全部计数：historical 611/768/29、current interactive-command 612/768/28、full 1059/1614/64、owner-defined 66
  4. 验证全部 ref 唯一解析、registry graph/JSON/digests/evidence refs/readiness frozen prefix 完整性
  5. 验证 initial review 之后仅有 implementation wording 与 fix/review artifacts 变更
- **审阅方法**: 从零独立运行全部机器检查；逐条核对 adjudication 裁决与 registry 实际状态；不使用第一次 DS review 或 MiMo review 的中间数据
- **输出文件**: `docs/reviews/pr-190-f11-f12-s5-registry-ds-rereview-20260806.md`
- **约束**: 不修改实现文件或 registry 文件；不 commit；不 push

---

## DS Finding 1 闭合验证

### Finding 原文

DS finding 1（低严重度）：MiMo review artifact 声称 "29 stable predicate ids, 0 dangling, 0 duplicate current owner"，但实际 oracle 定义 30 个 interactive predicate_id（`interactive.01` 至 `interactive.30`），其中 baseline 引用 28 个，2 个（10、17）零引用。

### Adjudication 裁决

Controller 裁决为**接受，低严重度文档歧义**。`29` 是 historical referenced subset 中实际被引用的 predicate id 数量（28 interactive + 1 prompt cross-entry），不是 owner-defined 总数。要求 fix 精确区分 "referenced" 与 "owner-defined"，并同时记录完整 registry 的 66/64 统计。

### Fix 实施

Fix artifact（`docs/reviews/pr-190-f11-f12-s5-registry-fix-20260806.md`）将原 implementation artifact 的 2 行混合统计拆分为 4 个互斥口径：

1. **historical referenced subset**
2. **current `command=interactive` inventory**
3. **current full registry inventory**
4. **accepted owner schema inventory / stable resolution**

### 独立复算验证

以下全部计数通过独立 Python 脚本从当前 registry 直接计算，不使用任何 artifact 中的中间结果：

#### Historical referenced subset（基线中至少引用一个 interactive.* predicate 的 scenario）

| 指标 | 声称值 | 独立复算 | 结果 |
| --- | --- | --- | --- |
| Records | 611 | 611 | **PASS** |
| Total refs（这些 scenario 的全部 predicate refs） | 768 | 768 | **PASS** |
| Referenced predicate ids | 29 | 29 | **PASS** |
| Ref owner: interactive@2 | 766 | 766 | **PASS** |
| Ref owner: prompt@1 | 2 | 2（PX01/PX02 cross-entry） | **PASS** |
| Referenced id owner: interactive@2 | 28 | 28 | **PASS** |
| Referenced id owner: prompt@1 | 1 | 1（`interactive.03` via cross-entry） | **PASS** |

**Evidence**: 直接 inventory 扫描，排除 3 条 unadjudicated replacement scenario，对 1056 条 baseline scenario 统计 predicate refs 及其 owner。

#### Current `command=interactive` inventory

| 指标 | 声称值 | 独立复算 | 结果 |
| --- | --- | --- | --- |
| Records | 612 | 612 | **PASS** |
| Total refs | 768 | 768 | **PASS** |
| Referenced predicate ids | 28 | 28 | **PASS** |
| 全部 refs 解析到 interactive@2 | ✓ | 768/768 → interactive@2 | **PASS** |
| 全部 ids 解析到 interactive@2 | ✓ | 28/28 → interactive@2 | **PASS** |

**Evidence**: 直接 `command=interactive` 过滤 → 612 records，展开全部 `oracle_predicate_refs` → 768 refs，收集 unique predicate_id → 28 ids。

#### Current full registry inventory

| 指标 | 声称值 | 独立复算 | 结果 |
| --- | --- | --- | --- |
| Records | 1059 | 1059 | **PASS** |
| Total refs | 1614 | 1614 | **PASS** |
| Referenced predicate ids | 64 | 64 | **PASS** |
| Ref owner: interactive@2 | 770 | 770 | **PASS** |
| Ref owner: prompt@1 | 728 | 728 | **PASS** |
| Ref owner: init@1 | 116 | 116 | **PASS** |
| Referenced id owner: interactive@2 | 28 | 28 | **PASS** |
| Referenced id owner: prompt@1 | 26 | 27（含 1 个 shared `interactive.03`） | 参见注 |
| Referenced id owner: init@1 | 10 | 10 | **PASS** |

**注**: 在 current full registry 层面，`interactive.03-label-is-cross-entry-conversation-alias` 被 prompt scenario PX01/PX02 引用，因此统计 "prompt scenarios 引用的 predicate ids" 时会包含它（27 = 26 prompt-only + 1 interactive cross-entry）。Fix artifact 按 owner 维度汇报 "prompt@1: 26 referenced ids"，这是指 "owner 为 prompt@1 的 predicate ids 中被引用的数量"。两个统计口径不同但均正确：64 = 28（owner=interactive）+ 26（owner=prompt）+ 10（owner=init），不重复计算 cross-referenced id。

#### Accepted owner schema inventory

| 指标 | 声称值 | 独立复算 | 结果 |
| --- | --- | --- | --- |
| Owner-defined stable predicates | 66 | 66 | **PASS** |
| interactive@2 predicates | 30 | 30 | **PASS** |
| prompt@1 predicates | 26 | 26 | **PASS** |
| init@1 predicates | 10 | 10 | **PASS** |
| Duplicate current owners | 0 | 0 | **PASS** |
| Cross-owner predicate IDs | 0 | 0 | **PASS** |

**Evidence**: 从 3 个 current accepted oracle（status=accepted, superseded_by=null）直接提取全部 predicate_id，验证无跨 owner 重复。

### Finding 1 闭合判定: **PASS**

四个统计口径精确、互斥、可独立复核。每个口径明确标注了统计对象（scenario records / predicate refs / referenced ids / owner-defined predicates）和统计范围（historical baseline subset / current command inventory / full registry / owner schema）。不再存在 "29" 与 "30" 的歧义。

---

## DS Finding 2 闭合验证

### Finding 原文

DS finding 2（低严重度）：609 条 active scenario 的 frozen `accepted_oracle_refs` 指向已 superseded 的 `cli.interactive.core-execution@1`，若未来消费者直接用 frozen refs 做 current resolution 会得到错误 oracle。

### Adjudication 裁决

Controller 裁决为**拒绝为 finding，保留为已缓解的维护注意事项**。理由：

1. 这是本次用户确认的 lifecycle contract，不是实现偏差
2. `docs/cli_ci.md` 已明确：`accepted_oracle_refs` 是历史版本证据，不参与 current owner resolution；current owner 只能由 stable `oracle_predicate_refs` 解析
3. 机器检查证明 1614 refs 全部唯一解析，0 dangling、0 duplicate owner
4. 批量改写 frozen refs 或新增兼容读法会破坏历史 verdict 的可解释性
5. 后续新 consumer 的 owner tests 必须锁定上述解析规则；当前 S5 不扩张 README/example

### 独立验证

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 1614 `oracle_predicate_refs` 全部唯一解析 | **PASS** | 0 dangling, 0 duplicate current owner |
| `accepted_oracle_refs` 未批量改写 | **PASS** | 1056 baseline scenario → 0 AOR changes |
| 含 `interactive@1` 的 frozen AOR 数量 | 611 | 与 historical referenced subset 的 611 records 一致 |
| `docs/cli_ci.md` 中两阶段解析规则存在 | **PASS** | 已读取确认 |
| 无未经授权的 registry 变更 | **PASS** | registry digests 与 initial implementation artifact 完全一致 |

### Finding 2 闭合判定: **PASS**

Finding 被正确裁决为 rejected-with-reason。Lifecycle contract 已由用户确认，doc 规则已明确，机器验证全部通过。未因该 finding 对 registry 做任何未授权变更。

---

## Open Questions 裁决验证

### DS Open Question 1: PX01/PX02 是否需要 lifecycle update

**Controller 裁决**: 不需要。Frozen refs 正确记录原裁决版本，stable interactive predicate 已解析到 `core-execution@2`。

**独立验证**:

| 检查项 | PX01 | PX02 |
| --- | --- | --- |
| status | accepted v1 | accepted v1 |
| accepted_oracle_refs | `['cli.prompt.core-execution@1', 'cli.interactive.core-execution@1']` | 同 |
| oracle_predicate_refs | `['prompt.08-...', 'interactive.03-...']` | 同 |
| `interactive.03` 解析到 core@2 | ✓ | ✓ |
| S5 未修改 | ✓ | ✓ |

**判定: PASS** — PX01/PX02 未被修改，裁决正确。

### DS Open Question 2: predicate 10/17 当前零 scenario 引用

**Controller 裁决**: 不属于本 work unit 的 finding。它们是既有 accepted oracle predicates，本 work unit 只替换 F11/F12 对应的 29/30 contract。

**独立验证**:

- `interactive.10-idle-ctrl-c`: 零引用 — **正确，pre-existing**
- `interactive.17-idle-escape-and-sequences`: 零引用 — **正确，pre-existing**
- 两条 predicate 在 core@2 中 contract 文本未变（仅 29/30 被替换）
- 未因该 open question 做任何 scenario 新增或 predicate 删除

**判定: PASS** — 裁决正确，无未授权变更。

---

## 独立全量复算

以下所有计数通过独立 Python 脚本从当前 registry JSON 直接计算。

### 计数汇总

| 口径 | Records | Refs | Referenced IDs | Owner-Defined Predicates |
| --- | --- | --- | --- | --- |
| Historical referenced subset | 611 | 768 | 29 | N/A |
| Current interactive command | 612 | 768 | 28 | N/A |
| Current full registry | 1059 | 1614 | 64 | N/A |
| Accepted owner schema | N/A | N/A | N/A | 66 |

### Owner 分布

| Owner | Defined Predicates | Referenced IDs | Total Refs |
| --- | --- | --- | --- |
| `cli.interactive.core-execution@2` | 30 | 28 | 770 |
| `cli.prompt.core-execution@1` | 26 | 26 | 728 |
| `cli.init.workspace-initialization@1` | 10 | 10 | 116 |
| **Total** | **66** | **64** | **1614** |

### Ref 解析验证

- 1614 total refs → 0 dangling → 0 duplicate current owner
- 全部 refs 通过 stable `predicate_id` 唯一解析到 3 个 current accepted owner
- Cross-entry refs: PX01/PX02 的 `interactive.03-label-is-cross-entry-conversation-alias` 正确解析到 `cli.interactive.core-execution@2`

---

## Registry 完整性验证

### Supersession graph

| 检查项 | Oracle | Scenario |
| --- | --- | --- |
| Dangling refs | 0 | 0 |
| Asymmetric edges | 0 | 0 |
| Cycles | 0 | 0 |

**PASS** — 全部 edge 双向可解析，有向无环。

### Old record preservation（lifecycle-normalized）

| Old Record | base≡current SHA-256 | Only status/superseded_by changed |
| --- | --- | --- |
| `cli.interactive.core-execution@1` | `abd3563e...` | ✓ |
| `interactive.interactive.g06.tool-trace-formal@1` | `e70611c4...` | ✓ |
| `interactive.interactive.g06.drop-superseded@1` | `96478661...` | ✓ |
| `interactive.interactive.g06.drop-policy-limit@1` | `7c892546...` | ✓ |

**PASS** — 4/4 lifecycle-normalized digest 与基线一致。其它 2 oracle + 1053 scenario exact equal。

### Frozen `accepted_oracle_refs`

- 1056 baseline scenario → 0 changes
- 611 scenarios 含 `cli.interactive.core-execution@1` → 全部保留
- 0 批量改写

**PASS**

### Registry digests

| File | SHA-256 | 与 implementation artifact 一致 | 与 fix artifact 一致 |
| --- | --- | --- | --- |
| `docs/cli_ci_oracles.json` | `3404e241...` | ✓ | ✓ |
| `docs/cli_ci_scenarios.json` | `f4363fc5...` | ✓ | ✓ |

**PASS** — 注册表文件 digests 在 initial implementation → fix → 当前 三个阶段完全一致，证明 fix 未修改 registry 数据。

### Evidence root

| 检查项 | 结果 |
| --- | --- |
| Root path 存在 | ✓ `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY` |
| Report SHA-256 | `bbaa52a0...` → **MATCH** |
| Manifest SHA-256 | `38f0b01f...` → **MATCH** |

**PASS**

### Readiness frozen prefix

- 追加标记 `Final implementation status appended on 2026-08-06` 之前的所有原文逐字节保留
- Frozen prefix: 132 行, 14548 chars
- Appended section: 2081 chars

**PASS**

### Registry status

- Oracle `registry_status`: `calibration`
- Scenario `registry_status`: `calibration`
- 未标 `ready`

**PASS**

### Unadjudicated replacement scenarios

| Scenario | Status | Adjudication |
| --- | --- | --- |
| `tool-trace-formal@2` | unadjudicated | pending-oracle-controller-adjudication |
| `rolling-correction-replacement@1` | unadjudicated | pending-oracle-controller-adjudication |
| `cap-constrained-memory-replacement@1` | unadjudicated | pending-oracle-controller-adjudication |

**PASS** — 未将 S4 evidence observation 自动投影为 accepted。

### Removed-ledger 扫描

- 当前（status≠superseded）scenario 中 0 命中 `policy_limit`/`explicit_drop`/`drop_reason`/`drop_ledger`
- Oracle 命中仅在 core@1（已 superseded）和 core@2 forbidden 列表（正确禁止）

**PASS**

### Predicate 29/30 contract

- `interactive.29-compactor-output-accept-repair-fallback`: 5 expected（含 Host accept barrier/provenance/caps/repair 所有权）+ 5 forbidden（含禁止模型产出 omission ledger/drop reason/cap attribution）
- `interactive.30-compaction-semantic-memory-closure`: 8 expected（含五类业务语义、Host omitted 补集、bounded repair、public Tool Trace projection）+ 6 forbidden（含禁止 per-omitted-source ledger、raw history 重新投影）

**PASS** — 精确对应 v3 Host-owned contract。模型只产出业务语义 + 必要 provenance；Host 拥有 represented/omitted exact complement、caps、usage audit、bounded repair/fallback。

---

## 变更范围验证

**要求**: 验证 initial review 之后仅有 implementation wording 与 fix/review artifacts 变更，registry 文件未被二次修改。

| 文件 | Initial S5 创建 | Fix 修改 | 当前状态 |
| --- | --- | --- | --- |
| `docs/cli_ci_oracles.json` | ✓ | 未修改 | digest 与 initial 一致 |
| `docs/cli_ci_scenarios.json` | ✓ | 未修改 | digest 与 initial 一致 |
| `docs/cli_ci.md` | ✓ | 未修改 | — |
| `docs/reviews/wu-interactive-memory-postfix-readiness.md` | ✓ | 未修改 | frozen prefix preserved |
| `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md` | ✓ | **修改**（validation 统计口径拆分） | 当前版本含 4 口径 |
| `docs/reviews/pr-190-f11-f12-s5-registry-fix-20260806.md` | — | **新增** | fix artifact |
| `docs/reviews/pr-190-f11-f12-s5-registry-ds-review-20260806.md` | — | — | 第一次 DS review（未修改） |
| `docs/reviews/pr-190-f11-f12-s5-registry-mimo-review-20260806.md` | — | — | MiMo review（未修改） |
| `docs/reviews/pr-190-f11-f12-s5-registry-review-adjudication-20260806.md` | — | — | Adjudication（未修改） |

**PASS** — Registry 文件（oracles.json, scenarios.json）digests 在全部三个阶段一致，仅 implementation artifact 的 validation 说明措辞与新增 fix/review artifacts 变更。无未授权 registry 修改。

---

## Findings

未发现实质性问题。

两条 DS finding 均已闭合：

- **DS finding 1**: 通过 4 个互斥、精确的统计口径闭合。每个口径的计数经独立复算验证正确。
- **DS finding 2**: 被裁决正确拒绝。Lifecycle contract 由用户确认，doc 规则明确，机器验证全部通过，无未授权 registry 变更。

两条 open question 均被正确裁决：
- PX01/PX02 不需要 lifecycle update（PX01/PX02 未修改，frozen refs 保留，dynamic resolution 正确）
- Predicate 10/17 零引用不属于本 work unit（pre-existing，未修改）

---

## Open Questions

无。

---

## Residual Risk

1. **Oracle controller 未完成裁决**: 三条 replacement scenario 的 Formal Oracle 仍为 pending。风险 ownership 属于 Oracle controller，不在 S5 scope。
2. **Reconnect raw history 语义边界**: 未来 Oracle 裁决需精确区分 audit trail vs semantic reintroduction。风险属于 Oracle controller。
3. **Immutable evidence root 长期保留**: 由 CLI CI evidence-retention owner 负责。Registry 已固定 identity/digest。

---

## 最终裁决

**PASS** — 全部验证项通过：

| 验证项 | 结果 |
| --- | --- |
| DS finding 1 闭合（4 口径精确、互斥、可复核） | **PASS** |
| DS finding 2 裁决正确（无未授权 registry 变更） | **PASS** |
| DS open question 1 裁决正确（PX01/PX02 未修改） | **PASS** |
| DS open question 2 裁决正确（predicate 10/17 未修改） | **PASS** |
| Historical 611/768/29 复算 | **PASS** |
| Current interactive 612/768/28 复算 | **PASS** |
| Full 1059/1614/64 复算 | **PASS** |
| Owner-defined 66 复算 | **PASS** |
| 全部 ref 唯一解析（1614 refs, 0 dangling） | **PASS** |
| Supersession graph（0 dangling, 0 asymmetric, 0 cycle） | **PASS** |
| Old record preservation（4/4 lifecycle-normalized match） | **PASS** |
| Frozen accepted_oracle_refs（0 changes） | **PASS** |
| Registry digests（跨所有 artifact 一致） | **PASS** |
| Evidence root/report/manifest | **PASS** |
| Readiness frozen prefix | **PASS** |
| Registry status = calibration | **PASS** |
| Only implementation wording + fix/review artifacts changed | **PASS** |

未修改实现文件或 registry 文件。未 commit，未 push。
