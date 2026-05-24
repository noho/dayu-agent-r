# P12.6 Design Re-Review — Mimo

## Gate

Design re-review. Verify accepted findings are fixed without regressions. Not implementation review.

## Reviewed Artifacts

- `docs/reviews/p12-6-design-review-mimo-20260524.md` (original review)
- `docs/reviews/p12-6-design-review-ds-20260524.md` (original review)
- `docs/reviews/p12-6-design-review-controller-adjudication-20260524.md` (controller adjudication)
- `docs/host/design.md` §24 Conversation Memory and §25 Context Governance (current state)
- `docs/host/implementation-control.md` current status

## Verification Scope

Controller adjudication accepted 7 findings and requested re-review to verify:

1. Accepted findings are fixed in `docs/host/design.md`.
2. No new public API drift, Engine dependency, Fins leakage, extra payload escape hatch, overdesigned retention, or contradiction with Host governance boundaries was introduced.

## Accepted Findings Verification

### Accepted Finding 1: compact segment boundary is under-specified

- **Controller decision**: accepted. Design must define compact segment selection.
- **Current design doc**: §25 lines 2754-2766 define compact segment with explicit proactive/reactive boundaries, block-based selection, and deterministic output.
- **Verification**: **FIXED**. Proactive path upper/lower bounds are explicit (lines 2757-2760). Reactive path segment from overflow material list is explicit (lines 2761-2762). Block-based selection with token/budget pressure is specified (lines 2763-2764). Deterministic output requirement is stated (lines 2765-2766).

### Accepted Finding 2: material pack section mapping is under-specified

- **Controller decision**: accepted. Each canonical content item must have one LLM-facing section owner.
- **Current design doc**: §25 lines 2768-2779 define one-to-one section mapping with explicit exclusions.
- **Verification**: **FIXED**. `stable_input` source is explicit (line 2770). `current_input_anchor` exclusion from `history_input` is explicit (lines 2771-2772). `history_input` exclusion of accepted tool result raw content is explicit (lines 2773-2774). `evidence_input` source and envelope role are explicit (lines 2775-2778). Host internal mapping prohibition from LLM-facing content is explicit (line 2779).

### Accepted Finding 3: accepted evidence raw data path is ambiguous

- **Controller decision**: accepted with corrected implementation-independent wording. Envelope is provenance metadata, not result-content container.
- **Current design doc**: §24 lines 2560-2569 define envelope as provenance anchor. §25 lines 2775-2778 define evidence block raw content source.
- **Verification**: **FIXED**. §24 line 2564: "Accepted evidence envelope 是 provenance anchor，不是 evidence 内容的 lossy 容器". §25 line 2776: raw content comes from "compact segment 内 `TOOL_RESULT_ACCEPTED` canonical fact 所引用且 digest 校验通过的 Host payload / raw result descriptor". The data flow from EventLog to evidence block is now explicit.

### Accepted Finding 4: long-session consolidation V1 owner is ambiguous

- **Controller decision**: accepted. V1 consolidation owned by memory projection policy and bounded selection.
- **Current design doc**: §24 lines 2586-2597 define consolidation as basic semantics with V1 path.
- **Verification**: **FIXED**. Line 2593: "第一版 consolidation 由 memory projection policy 与 RunInputBuilder / compactor input bounded selection 执行". Line 2594: "`memory_retention_candidate` 作为后续增强，不阻塞 V1". The tension between "basic semantics" and "first version" is resolved: V1 achieves bounded semantics through policy-level selection, not compactor output schema.

### Accepted Finding 5: reactive multi-pass durable submission is ambiguous

- **Controller decision**: accepted. Multi-pass is one compaction operation; only one merged `CONTEXT_COMPACTED` is committed.
- **Current design doc**: §25 lines 2802-2807 define reactive multi-pass durable semantics.
- **Verification**: **FIXED**. Line 2802: "reactive multi-pass 是同一个 compaction operation 内的 material block batch processing". Line 2804-2805: "中间 pass 的 compact 产物只能作为 operation-level transient artifact 或 diagnostic artifact 暂存". Line 2805-2806: "Host 只能在所有 required passes 通过 quality / budget gate 后提交一个合并的 `CONTEXT_COMPACTED`". Line 2806-2807: "若中间 pass 失败且 repair budget 耗尽，整个 operation 写入一个最终 `CONTEXT_COMPACTION_FAILED`". Atomic commit semantics are now explicit.

### Accepted Finding 6: memory snapshot cursor handling for compaction is missing

- **Controller decision**: accepted. Snapshot cursor validation and catch-up/rebuild required before material pack build.
- **Current design doc**: §25 lines 2781-2783 define cursor validation requirement.
- **Verification**: **FIXED**. Lines 2781-2782: "material pack build 启动前必须校验 memory snapshot cursor". Lines 2782-2783: "若 snapshot cursor 不能覆盖构造 `stable_input` 和 compact segment 所需的 EventLog cursor，Host 必须先执行 memory projection catch-up / rebuild 或在 policy 允许范围内做 inline delta repair". Failure path is explicit (line 2783).

### Accepted Finding 7: episode summary bounded rendering wording is vague

- **Controller decision**: accepted. `history_input` episode summaries limited to segment-generated and policy-bounded recent summaries.
- **Current design doc**: §25 lines 2746-2748 define bounded episode summary rendering.
- **Verification**: **FIXED**. Lines 2746-2748: history_input includes "compact segment 新产生的 episode summaries，以及 policy 允许的 bounded recent episode summaries；超出 policy 上限或与本次 segment 无关的较旧 summaries 只保留 artifact / EventLog refs". This aligns with §24 bounded rendering principle (line 2590).

## Regression Check

### Public API drift

- No new public API surface introduced. `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_REQUESTED`, and `CONTEXT_COMPACTION_ATTEMPT_REJECTED` are EventLog canonical facts within Host governance, not public API expansion. HostEvent exposure is explicitly scoped (§25 lines 2729).
- **Verdict**: No regression.

### Engine dependency

- No Engine changes required. §25 line 2654: "Engine 不做 Host-side compact retry，也不理解 Host compaction attempt state machine". Material pack construction, segment selection, and multi-pass orchestration are all Host-internal.
- **Verdict**: No regression.

### Fins leakage

- No Fins or tool-provider involvement in compaction. Tool provider only produces `TOOL_RESULT_ACCEPTED`; fact extraction is Host-governed. Material pack evidence_input reads from EventLog canonical facts, not from Fins storage.
- **Verdict**: No regression.

### Extra payload escape hatch

- Budget parameters (`context_window_size`, `reserved_output_tokens`) are explicit typed inputs from Service composition root (§25 line 2675). No per-run metadata or extra payload escape hatch for budget parameters.
- **Verdict**: No regression.

### Overdesigned retention

- V1 consolidation uses memory projection policy bounded selection, not a new compactor retention-intent schema. `memory_retention_candidate` is explicitly deferred as optional future enhancement (§24 line 2594). No overdesigned retention system introduced.
- **Verdict**: No regression.

### Host governance boundaries

- Context Governance is orchestrator, does not directly write memory snapshot (§25 line 2671).
- Compactor is Host-owned typed port (§25 line 2711).
- Memory projection only consumes canonical facts (§24 line 2618).
- `evidence_backed_facts` only from accepted evidence refs (§24 line 2615).
- `final_answer` cannot upgrade to `evidence_backed_fact` (§24 line 2614).
- **Verdict**: No regression.

## Deferred Items (Controller Adjudication)

The controller deferred 4 items to planning. These are implementation strategy details, not design blockers:

1. Whether to refactor `CompactionRequest` to material-pack-oriented structure.
2. Exact deterministic algorithm for current input anchor short text / digest.
3. V1 relevance strategy for bounded evidence-backed fact working set.
4. Edge handling for single evidence block exceeding compactor budget.

These items do not block design re-review gate. They belong in the implementation-ready plan.

## Conclusion

**PASS**

All 7 accepted findings from the controller adjudication are verified as fixed in `docs/host/design.md` §24 and §25. Each fix is evidence-based: the design doc now contains explicit text addressing the specific gap identified by the original review. No new public API drift, Engine dependency, Fins leakage, extra payload escape hatch, overdesigned retention, or Host governance boundary contradiction was introduced.

The design refinement is specific enough to enter plan gate. The 4 deferred items are implementation strategy details that belong in the handoff plan, not in the design truth source.
