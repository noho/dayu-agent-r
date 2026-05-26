# P12.6 Plan Review — DS Adversarial Review

## Review Metadata

- **Reviewer**: DS (Design Reviewer, role-scoped plan review)
- **Target**: `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- **Gate**: Handoff implementation-ready plan review, NOT implementation
- **Timestamp**: 2026-05-24T19:52:44+08:00
- **Truth sources**: `docs/host/design.md` §1, §24, §25; `docs/host/implementation-control.md` Phase 12.6
- **Prior review artifacts**:
  - `docs/reviews/p12-6-design-review-controller-adjudication-20260524.md` (7 accepted findings, 4 deferred to planning)
  - `docs/reviews/p12-6-design-rereview-mimo-20260524.md` (PASS)
  - `docs/reviews/p12-6-design-rereview-ds-20260524.md` (PASS, 2 residual observations)
- **Discussion input only (not design truth)**: `docs/host/conversation-memory-compact-io-first-principles-discussion.md`

## Scope

Verify that the plan is handoff-ready and code-generation-ready:

1. Slices small enough and independently verifiable.
2. Allowed files clear and consistent across plan sections.
3. Tests tied to contract boundaries, not implementation internals.
4. No missing contract decisions — all 4 controller-deferred items resolved.
5. No Engine/Fins/Service/UI/public API drift.
6. No `Any`/`object`/extra payload/lazy seam escape hatches.
7. All 7 accepted design findings converted to mandatory implementation requirements.
8. Stop conditions well-defined per slice.

## Assumptions Tested

1. **Plan scope aligns with design doc §24/§25**: Verified by cross-referencing plan §3/§6 against design doc sections.
2. **All controller-deferred items are decided in plan §6**: Verified — see findings below.
3. **Section 7 file list is the exhaustive allowlist for all slices**: The plan states "Implementation slices 可修改以下文件或同目录紧邻测试。超出列表必须先停下报告 Controller。" This must be the canonical constraint.
4. **Slice ordering allows incremental verification**: Each slice's verification command covers only that slice's files — confirmed.
5. **Tests assert on typed contracts, not implementation details**: Test names use terms like `material_pack`, `prompt_local`, `canonical_ref`, `ledger_dump` — these are contract-level concepts.
6. **No new public API surface**: Public surface prohibition in §5 is explicit and unconditional.

## Findings

### F1-未修复-中-Slice 3 允许修改文件与 §7 主清单不一致

- **位置**: §7 受影响文件与模块 vs. Slice 3 允许修改文件
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**:
  - §7 主清单 Host source 列出 15 个文件，不含 `dayu/host/evidence.py`；测试列出 12 个文件，不含 `tests/host/test_toolruntime_accept_barrier.py`。
  - Slice 3 "允许修改文件" 列出了 `dayu/host/evidence.py` 和 `tests/host/test_toolruntime_accept_barrier.py`。
- **反例/失败场景**: Implementation agent 启动 Slice 3，发现需要修改 `dayu/host/evidence.py`，按 §7 指令 "超出列表必须先停下报告 Controller"，Slice 3 被阻塞。或者 implementation agent 不检查 §7 直接修改，违反 plan 自身约束。
- **为什么有问题**: §7 明确声明为 exhaustive allowlist（"超出列表必须先停下报告 Controller"），但 Slice 3 的局部 allowlist 超出了主清单。两份清单互相矛盾，implementation agent 无法判断哪个是 canonical constraint。
- **直接证据**:
  - §7 主清单 Host source 不含 `evidence.py`（plan 行 251-266）
  - §7 主清单测试不含 `test_toolruntime_accept_barrier.py`（plan 行 274-287）
  - Slice 3 列出 `dayu/host/evidence.py`（plan 行 409）和 `tests/host/test_toolruntime_accept_barrier.py`（plan 行 413）
  - 当前仓库中两个文件均存在（`dayu/host/evidence.py`、`tests/host/test_toolruntime_accept_barrier.py`）
- **影响**: 实施 Agent 跑偏 / review 不可验收 / 后续返工
- **建议改法和验证点**: 将 `dayu/host/evidence.py` 和 `tests/host/test_toolruntime_accept_barrier.py` 补入 §7 主清单。验证：两处清单完全一致。
- **修复风险（低）**: 纯文本一致性修复，不涉及设计决策变更。
- **严重程度（中）**: 会直接阻塞 Slice 3 实施，但修复简单。

### F2-未修复-低-`PromptLocalEvidenceMap` 未纳入 §6.1 typed contracts 枚举

- **位置**: §6.1 vs. §6.5
- **问题类型**: 契约缺失
- **当前写法**: §6.5 描述 "建立 `PromptLocalEvidenceMap`：LLM label 到 canonical accepted evidence id、tool result event、tool call event、payload / artifact refs"，但 §6.1 枚举的 typed contracts（`CompactMaterialSection`、`CompactMaterialBlockKind`、`PromptLocalMaterialLabel`、`CompactMaterialBlock`、`CompactEvidenceBlock`、`CurrentInputAnchor`、`CompactMaterialPack`、`CompactSegmentSelection`、`CompactionRequest`）中未包含 `PromptLocalEvidenceMap`。
- **反例/失败场景**: Implementation agent 实现 Slice 3 时不确定 `PromptLocalEvidenceMap` 的 typed shape（dataclass? TypedDict? type alias?），可能自行设计导致与 `provenance_map` 或 accept barrier 的契约不一致。
- **为什么有问题**: `PromptLocalEvidenceMap` 是 evidence label → canonical provenance 映射的核心数据结构，跨越 Slice 2（material pack builder 生成 label）、Slice 3（evidence collector 填充映射）、Slice 4（accept barrier 消费映射）。缺少 typed contract 定义会导致三个 slice 之间靠隐式约定对接。
- **直接证据**: plan §6.1 行 102-112 枚举了所有 typed contracts 但不含 `PromptLocalEvidenceMap`；§6.5 行 423 使用了该类型名但未定义其 shape。
- **影响**: 实施 Agent 跑偏 / review 不可验收
- **建议改法和验证点**: 在 §6.1 中增加 `PromptLocalEvidenceMap` 的 typed contract 定义（建议为 `dict[str, CanonicalEvidenceProvenance]` 或独立 dataclass），明确其字段、不可变性（frozen?）和与 `CompactMaterialPack.provenance_map` 的关系。验证：§6.1 与 §6.5 对该类型的描述一致。
- **修复风险（低）**: 只需补一个类型定义。
- **严重程度（低）**: Implementation agent 有足够上下文推断合理 shape，但会增加 slice 间不必要的设计决策。

### F3-未修复-低-Prompt-local label 生成算法未指定

- **位置**: §6.2 Prompt-local label 与 canonical provenance
- **问题类型**: 不可直接实施
- **当前写法**: §6.2 给出 label 示例格式（`C1`、`H1`、`H2`、`E1`、`E1.1`、`E1.2`、`S1`、`S2`），但未定义 label 生成算法：前缀如何分配给 section、数字序号是全局递增还是 per-section、chunk label（如 `E1.1`）的格式规则。
- **反例/失败场景**: 两个不同的 implementation agent（或同一 agent 在不同 slice）对 label 格式做出不同假设，导致 Slice 2 生成的 label 与 Slice 4 的 parser 期望不一致。
- **为什么有问题**: Label 格式是 material pack builder（Slice 2）和 LLM output parser（Slice 4）之间的隐含协议。虽然 Slice 4 可以通过模块级常量引用 Slice 2 的 label 生成 helper 来解决，但 plan 未显式声明这一依赖。
- **直接证据**: plan §6.2 行 124-128 给出示例但无生成规则；§6.2 行 139 提到 parser "引用未知 label、跨 section label、重复 canonical content 或 label 指向非本次 material pack 时 fail closed"，说明 parser 需要理解 label 格式以校验 section membership，但 plan 未定义 parser 如何从 label 推断 section。
- **影响**: 实施 Agent 跑偏
- **建议改法和验证点**: 在 §6.2 增加一句："label 生成由 `dayu/host/compact_material.py` 中的模块级私有 helper 负责，格式为 `{section_prefix}{ordinal}` 或 `{section_prefix}{ordinal}.{chunk_ordinal}`；parser 通过同一 helper 或共享常量校验 label 格式和 section membership。" 验证：Slice 2 和 Slice 4 的验证命令均覆盖 label 相关测试。
- **修复风险（低）**: 加一句话明确 owner。
- **严重程度（低）**: Implementation agent 自然会用共享 helper，不会真正跑偏，但缺少显式声明使 review 难以确认一致性。

## Deferred Items Verification

Controller adjudication deferred 4 items to planning. Plan §6 addresses all four:

| Deferred Item | Plan Resolution | Location | Verdict |
|---|---|---|---|
| CompactionRequest shape decision | material-pack-oriented contract, old fields deleted/demoted | §6.1 | Resolved |
| Current input anchor short text / digest algorithm | bounded prefix + truncated marker + full digest in internal mapping | §6.2 / Slice 2 | Resolved |
| V1 relevance strategy for bounded evidence-backed fact working set | pinned subject match / goal keyword overlap / recent user reference / newer extraction / policy top-K | §6.8 | Resolved |
| Single evidence block exceeding compactor budget | deterministic evidence chunks (E1.1, E1.2) under same canonical provenance | §6.3 Reactive selection | Resolved |

All deferred items have concrete, testable decisions.

## Design Finding → Plan Requirement Mapping

All 7 controller-accepted findings are traceable to mandatory plan requirements:

| Accepted Finding | Plan Requirement | Location |
|---|---|---|
| F1: compact segment boundary under-specified | §6.3 deterministic segment selection rules | §6.3, Slice 2 |
| F2: material pack section mapping under-specified | §6.4 one-to-one section mapping with dedupe guard | §6.4, Slice 2 |
| F3: accepted evidence raw data path ambiguous | §6.5 digest-checked descriptor path, no envelope preview | §6.5, Slice 3 |
| F4: long-session consolidation V1 owner ambiguous | §6.8 V1 consolidation owner = memory projection policy + bounded selection | §6.8, Slice 6 |
| F5: reactive multi-pass durable submission ambiguous | §6.7 single operation, transient intermediate, one merged commit | §6.7, Slice 5 |
| F6: memory snapshot cursor handling missing | §6.6 cursor validation + catch-up/rebuild/inline delta before material pack build | §6.6, Slice 2 |
| F7: episode summary bounded rendering vague | §6.8 policy-bounded recent summaries, older refs-only | §6.8, Slice 6 |

No accepted finding was dropped or weakened.

## Boundary Integrity Check

### Public API Drift

Plan §5 is an explicit blocklist with stop conditions in each slice. No slice's allowed modifications touch `api.py`, `open_host.py`, or any public surface file. **Clean.**

### Engine Dependency

No Engine files in allowed-modification lists. Plan §3.2 explicitly excludes Engine. Stop conditions in Slice 2/5 trigger if Engine modification appears needed. **Clean.**

### Fins Leakage

No Fins files in allowed-modification lists. Plan §3.2 explicitly excludes Fins. Evidence reading path (§6.5) goes through `TOOL_RESULT_ACCEPTED` canonical facts, not Fins storage. **Clean.**

### Extra Payload / Any / object / Lazy Seam

Plan §4 explicitly forbids these. Plan §3.2 line 68: "不通过 extra payload、Any、object、lazy glue seam、callback / factory escape hatch 绕开 typed contract." **Clean.**

### Overdesigned Retention

Plan §6.8: "V1 consolidation 不新增 retention-intent schema". No `RetentionPolicy`, `RetentionIntent`, or `MemoryRetentionManager` abstractions. **Clean.**

### Host Governance Boundaries

One-way relationship preserved: EventLog → memory projection (read model) → Context Governance (reads snapshot, writes compact events) → memory projection consumes compact events. No circular dependency. Context Governance does not directly write memory snapshot. **Clean.**

## Slice Coherence Check

| Slice | Can be implemented independently? | Tests verify contract boundaries? | Stop conditions well-defined? |
|---|---|---|---|
| Slice 1 | Yes — typed contracts only, no runtime integration | Yes — asserts on JSON keys, section mapping, fail-closed | Yes — 3 conditions |
| Slice 2 | Depends on Slice 1 contracts | Yes — deterministic output, section mapping, cursor validation | Yes — 3 conditions |
| Slice 3 | Depends on Slice 1+2 contracts | Yes — raw descriptor path, label mapping, chunking, fail-closed | Yes — 3 conditions |
| Slice 4 | Depends on Slice 1+2+3 contracts | Yes — prompt content assertions, label mapping, quality gate | Yes — 2 conditions |
| Slice 5 | Depends on Slice 1-4 | Yes — material pack usage, multi-pass durability, budget | Yes — 3 conditions |
| Slice 6 | Depends on Slice 1+2 contracts (can parallel with 3-5) | Yes — bounded working set, materialization, dedup | Yes — 2 conditions |
| Slice 7 | Depends on all prior slices | Yes — public path smoke scenarios | Yes — 2 conditions |

Slice dependency graph is acyclic. Slice 6 can theoretically run in parallel with Slices 3-5 since it only depends on Slice 1+2 contracts, though the plan's sequential numbering implies serial execution. This is not a defect — sequential is safer for review gating.

## Open Questions

无阻塞性 open question。以下为确认项：

1. **OQ1**: Slice 4 的 prompt asset 修改 (`conversation_compaction.md` / `conversation_compaction_user.md`) 是否涉及 JSON schema 结构变更？若是，schema 变更是嵌入 prompt markdown 还是在代码中定义？plan 未明确，但 implementation agent 可从现有 prompt asset 推断。

2. **OQ2**: Slice 1 删除旧字段后，是否存在其他 Host 模块（非 allowed-modification 列表内）通过 `hasattr`/`getattr` 动态访问已删除字段？按 §4 编码护栏，`hasattr`/`getattr` 默认禁用，此风险可控。

## Residual Risks

1. **大 session rebuild performance**：plan §11 明确标记为后续 hardening，本 phase 只要求语义正确。**建议追踪位置**：`docs/host/implementation-control.md` Phase 12.6 退出后的 Open Questions 追踪区。

2. **V1 relevance strategy 使用 Host-neutral text overlap**：plan §11 标记 "V1 relevance strategy 使用 Host-neutral text overlap / recency / subject refs，不能理解财报业务语义"。这是诚实的设计限制，但意味着 evidence-backed fact working set 的排序可能在财报场景下不够精准。**建议追踪位置**：后续 Fins / retrieval owner phase。

3. **Reactive multi-pass budget 耗尽 fail closed**：plan §11 确认这是设计选择。需要确保 smoke 测试覆盖预算耗尽路径，避免无限 retry。plan Slice 5 测试 `test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run` 和 `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event` 已覆盖。

4. **Label-to-provenance mapping 扩大 artifact 面**：plan §11 标记 review 必须确认未把 raw prompt 或敏感 provider payload 写入 EventLog。Slice 1 测试 `test_context_compacted_payload_records_mapping_refs_not_raw_prompt` 已覆盖。

## Conclusion

**PASS** — 条件通过，需修复 F1 后 handoff。

Plan 整体 code-generation-ready：7 个 controller-accepted design findings 全部落地为可测试的 mandatory requirements；4 个 deferred items 全部在 §6 中有具体决策；slices 粒度合适、边界清晰、停止条件明确；未引入 Engine/Fins/Service/UI/public API 漂移；未使用 Any/object/extra payload/lazy seam。

阻塞项仅 F1（§7 与 Slice 3 文件清单不一致），修复简单（将 `dayu/host/evidence.py` 和 `tests/host/test_toolruntime_accept_barrier.py` 补入 §7 主清单）。F2、F3 为低严重度建议修，不阻塞 handoff。

修复 F1 后 plan 可直接交由 implementation agent 按 slice 顺序执行。
