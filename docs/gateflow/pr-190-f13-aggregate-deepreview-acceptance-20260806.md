# PR 190 F13 Aggregate Deepreview Acceptance

## Gate decision

- gate: aggregate `$deepreview --base 2d914beefb7bdee3e762df06f5f1ef0d115da143`
- head: `b9908d9a709d6fd101d6bbd88ab66900ce25fdd9`
- reviewed scope: S0 + S1 + S2，85 files
- verdict: `ACCEPTED`
- unresolved blocking/high/medium/low needs-fix: none

## Review evidence

- MiMo：`docs/reviews/pr-190-f13-aggregate-deepreview-mimo-20260806.md`，
  verdict `ACCEPTED`；补充完整 skill artifact：`docs/reviews/deep-review-20260806.md`。
- DeepSeek：`docs/reviews/pr-190-f13-aggregate-deepreview-ds-20260806.md`，
  final verdict `ACCEPTED`；原 F2 已按 typed construction evidence re-review 后 dismissed。
- MiMo 复跑 262 个受影响核心测试，DeepSeek 复跑 290 个 adversarial/owner tests；均通过。
  这些仍是 test evidence，不是 production interactive CLI evidence。

## Controller adjudication

### DS F2 — aggregate retained/new classification

Dismissed。每个 `previous_evidence_fact` boundary entry 本身就是 Host-owned atomic fact；
underlying `canonical_evidence_refs` 可以多条，但 retain selector 必须且只能选择该 atom 的一个
label。`derive_compact_accepted_replacement_v4` 唯一构造
`selection_labels=(entry.source_label,)`；new fact 才允许多个 current-evidence labels。
`CompactAcceptedTruthV4` 又只能由私有 acceptance permit 产生，aggregate 后还会 root
revalidation。因此 `len==1 + PREVIOUS_EVIDENCE_FACT kind` 是 exact typed binding，不是
heuristic。为不存在的 multi-label retained state 增加分类分支会掩盖 contract corruption，并
构成过度设计。DS 已在原 artifact 追加 resolution，最终无 unresolved NEEDS_FIX。

### MiMo LOW 1 — fake forward/reference sections 固定为空

No change。F13 mandatory owner semantics 是 EvidenceFact provenance；forward intent 与 reference
continuity 的 parser/acceptance/durable contract 已有 owner tests。强迫通用 fake 在没有对应业务
材料时生成非空 intent/reference 会让 fixture 编造语义，且不证明 production provider 行为。真实
provider/CLI 观察由 S3 独立完成，不用 fake 填补。

### MiMo LOW 2 — LLM schema v4 与 artifact schema 5 数字不同

Dismissed。两者 owner 与版本空间不同：v4 是 LLM input/output shape，schema 5 是 durable
artifact serialization；本次 replacement 新字段要求 artifact version 前移。将数字人为对齐反而
会混淆契约。

### MiMo LOW 3 — Tool Trace canonical terminal full scan

Accepted as non-blocking performance residual。full scan 是低频 public diagnostic read path，并以
完整 keyset exhaustion 和 duplicate-terminal fail-closed 换取 correctness；本 work unit 没有性能
目标，也没有观测到性能回归。未来只有出现量化证据时才由独立 work unit 设计索引，当前不预置
第二 projection owner。

## Accepted aggregate semantics

- previous EvidenceFact 只可 retain/omit；claim 与逐 fact refs 从同一 immutable boundary atom
  原样复制。
- new EvidenceFact support 只允许 current `evidence_material`，Host 机械计算非空逐 fact refs；
  user/assistant/summary/answer/context 不能升级为 EvidenceFact。
- strict durable parser 重演 proposal/boundary/replacement exact binding；aggregate 只等于逐 fact
  refs 的 ordered union 且属于 boundary。
- artifact、EventLog、rolling、Memory、reconnect、RunInput 与 Tool Trace 消费同一 accepted
  replacement；rejected/failed/fallback/stale/late 不产生 accepted materialization 或第二 terminal。
- prompt/schema 自足且不暴露 canonical refs、event id、digest、payload ref 或 Host governance。
- 无 compatibility alias/reader、natural-language entailment heuristic、drop ledger、raw payload
  second parser 或 downstream display compensation。

## Evidence boundary

Aggregate gate 只接受 implementation 与 test/static evidence。S3 仍必须执行完整 final validation
与真实 provider observation；三条 Oracle formal replacement scenarios 保持 unadjudicated，任何
post-fix observation 都不得替用户作 formal acceptance 裁决。
