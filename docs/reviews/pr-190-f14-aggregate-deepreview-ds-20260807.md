# F14 Aggregate Deepreview — AgentDS

## Verdict

**PASS** — 无 blocking defect。实现正确对应 accepted plan 的全部 owner contract、算法结构与生命周期规则。prior code review cycle（DS → MiMo → Controller adjudication → AgentCodex fix → DS/MiMo re-review → acceptance）已覆盖并修复全部 material findings。本轮 aggregate adversarial pass 未发现新的 correctness、semantic ownership drift、over-coupling 或 test fixture 真实性问题。

## Gate context

- **gate**: `aggregate deepreview`（agent: AgentDS）
- **accepted plan commit**: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- **implementation commit**: `6eb41ac1`
- **branch**: `codex/interactive-oracle`
- **review artifacts**:
  - Goal confirmation: `docs/reviews/f14-goal-confirmation-20260806-221301.md`
  - Plan + plan review chain: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`, `docs/reviews/pr-190-f14-plan-review-*.md`, `docs/gateflow/pr-190-f14-plan-review-adjudication-*.md`, `docs/reviews/pr-190-f14-plan-rereview-*.md`, `docs/gateflow/pr-190-f14-plan-rereview-acceptance-*.md`
  - Code review chain: `docs/reviews/pr-190-f14-code-review-ds-20260806.md`, `docs/reviews/pr-190-f14-code-review-mimo-20260806.md`, `docs/gateflow/pr-190-f14-code-review-adjudication-20260806.md`, `docs/reviews/pr-190-f14-code-rereview-ds-20260806.md`, `docs/reviews/pr-190-f14-code-rereview-mimo-20260806.md`, `docs/gateflow/pr-190-f14-code-rereview-acceptance-20260807.md`
  - Controller review: `docs/reviews/code-review-20260806-233618.md`
  - Implementation record: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`

## Scope

- **Mode**: current changes, `--base b222b8b0`
- **Included**:
  - `dayu/host/compact_material.py` — production material owner（435 行 diff）
  - `tests/host/test_compact_material.py` — owner tests（1512 行 diff）
  - `tests/host/test_run_input_builder.py` — integration test（713 行 diff）
  - `tests/host/test_dispatch_scheduler.py` — fixture update（48 行 diff）
  - `docs/host/design.md` — design truth update（14 行 diff）
  - `dayu/host/README.md` — developer overview update（2 行 diff）
  - 全部 `docs/reviews/` 与 `docs/gateflow/` review artifacts
- **Excluded**: Engine、prompt、provider、UI、Service、CLI、Fins、Oracle、scenario、schema migration

## Adversarial failure pass 结论

对以下攻击面逐项走读验证，未发现未修复 defect：

### correctness — 两阶段算法

- **metadata-first conservative frontier**（`_conservative_unconsumed_row_start_sequence`，L2711-2770）：
  - 从 `ORDER BY event_sequence ASC` SQL（L2669-2707）保证 canonical order
  - `grouped` 按首次出现顺序 append，`group[0].event_sequence` 机械等于该 group 最小 sequence
  - `group_consumed` 要求 `run_id is not None` + 唯一 user anchor + anchor ref ∈ consumed（L2756-2760）
  - consumed group 必须形成 strict prefix；unconsumed 之后出现 consumed → `HostDurableError`（L2762-2765）
  - `run_id=None` 与缺/多 user anchor 保守进入 typed projection

- **typed atomic exact proof**（`_unconsumed_atomic_material_blocks`，L2803-2853）：
  - block refs all-or-none：部分覆盖 → `HostDurableError`（L2835-2838）
  - unit blocks 必须同为 consumed 或同为 unconsumed（L2840-2843）
  - units 必须为 consumed prefix + unconsumed suffix（L2845-2849）
  - 复用既有 `_atomic_material_units` / `_sorted_material_blocks`

- **frontier 派生**（`_post_compact_delta_start_sequence`，L2633-2651）：
  - 从第一条保留 block 的 `event_sequence` 派生
  - 不再从 latest terminal sequence + 1 派生
  - 无 block 时返回 `current_input_sequence`

### semantic ownership — 无 drift

| 语义 | Owner | 验证 |
|------|-------|------|
| `compacted_source_refs` | `ContextCompactedSemanticPayload.compacted_source_refs`（compact_payload.py L162-182） | `_accepted_compacted_source_refs`（L2374-2389）只从 chain 各 terminal 的 `compacted_source_refs` 做 ordered-unique union；不从 flat evidence aggregate 生成 |
| `accepted_evidence_mapping_refs` | latest entry 的 `semantics.accepted_evidence_mapping_refs` | `represented_refs`（L512-513）只从 latest entry 投影；未改作 cumulative consumption truth |
| `latest_compacted_event_id/sequence` | latest entry 的 `event.event_id/event_sequence` | 只作为 provenance 暴露（L549-555）；不作为 consumption cursor |
| `post_compact_delta_start_sequence` | `_post_compact_delta_start_sequence` 从 material blocks 派生 | 不读取 terminal sequence；不执行 SQL |
| material coverage frontier | 上述语义的确定性派生值 | 不新增 durable cursor、schema 或第二 truth |

- `current_input_ref` 不在 `compacted_source_refs` 中（compact_payload.py L221：`source_refs == (current_input_ref, *compacted_source_refs)`），correct
- `compacted_source_refs` 只包含 represented + omitted coverage 的 source boundary entries 的 source_refs（compact_payload.py L169-182），protected/unselected labels 不进入，correct

### over-coupling — 无

- 只修改 Host material owner（`dayu/host/compact_material.py`）
- 未修改 Engine、prompt、provider、UI、Service、CLI、Fins
- 未新增 schema、public contract、durable cursor 或 fallback
- downstream consumer（Memory、RunInput、Tool Trace）继续从同一 strict terminal 投影，不各自重建 coverage
- `git diff --exit-code -- dayu/engine docs/engine dayu/config dayu/service dayu/ui dayu/fins` 通过

### lifecyle / state machine — 完整

| 路径 | 覆盖 | 证据 |
|------|------|------|
| accepted initial | ✅ | `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix`（L3050） |
| repair accepted | ✅ | 既有 scheduler/operation tests 复用（union 343 passed） |
| tier 1–3 accepted | ✅ | 同上 |
| CONTEXT_COMPACTION_ATTEMPT_REJECTED | ✅ | `test_pre_dispatch_non_accepted_compaction_events_do_not_advance_frontier`（L3580） |
| CONTEXT_COMPACTION_FAILED | ✅ | 同上 |
| cancelled / stale / late | ✅ | 既有 scheduler/cancellation tests 复用（不产生 CONTEXT_COMPACTED） |
| restart | ✅ | `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix` 含 reopen（L911-928） |
| reconnect | ✅ | `test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory`（test_run_input_builder.py L3852-4255） |
| tier 4/5 fallback | ✅ | 不产生 CONTEXT_COMPACTED，不推进 frontier |

### ref 完整性校验 — fail-closed

- `current_input_ref`：必须 exact 指向同 Session、更早的 `USER_INPUT_ACCEPTED`（L2318-2325）
  - 覆盖 missing / cross-session / forward 三种非法场景（`test_pre_dispatch_accepted_chain_rejects_invalid_current_input_reference`，L3667，3 parametrize）
- `PREVIOUS_*` source_refs：必须 exact 指向同 Session、更早的 `CONTEXT_COMPACTED`（L2326-2337）
  - 覆盖 missing / self / cross-session / forward 四种非法场景（`test_pre_dispatch_accepted_chain_rejects_invalid_previous_compact_reference`，L3881，4 parametrize）
- `event_sequence` 双重校验：SQL 返回的 sequence 与 `read_event_by_id` 返回 row 的 sequence 比对（L2279），防 concurrent phantom change

### test fixture 真实性 — 通过

- 所有 coverage-sensitive fixtures 显式提供真实 `current_input_ref` 与 per-label `source_refs_by_label`
  - `_append_compacted_event`（L5110-5143）接收 `current_input_ref` 和 `source_refs_by_label`
  - `_compacted_payload`（L5207-5248）通过生产 `accept_compact_candidate_v4` 构造 `CompactAcceptedTruthV4`
  - `_append_retained_previous_compacted_event`（L5146-5204）通过 `build_context_compacted_payload` + `accepted_truth_for_test_candidate` 生成同源 payload
- evidence ID 与 EventLog ID 显式不相等：
  - `_accepted_evidence_envelope_for_event` 使用 `evidence_id=f"evidence:{event_id}"`（L5086），而 canonical source ref 使用 `projection.evidence_id`（L2961）
  - `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix` 使用 `evidence:event-tool-result-consumed-prefix` 格式
  - 若误用 event_id 过滤，测试直接失败（plan B.1 要求）
- M2 reconnect 测试使用真实 `AcceptedEvidenceEnvelope`、`TOOL_CALL_REQUESTED`/`TOOL_RESULT_ACCEPTED`、`select_compact_segment`、`catch_up_conversation_memory_projection`、`build_pre_dispatch_compact_material_view`、reopen durable store、durable memory snapshot reader、ordinary RunInput builder — 无 mock/fake 替代生产 owner

### 项目指令检查

| 指令 | 状态 |
|------|------|
| 语义所有权：修复边界在 owner boundary | ✅ Host material owner (`compact_material.py`) |
| LLM-facing 文本不修改 | ✅ 无 prompt/config 修改 |
| 架构硬约束：分层不被破坏 | ✅ 无 Engine/UI/Service 修改 |
| 编码硬约束：docstring/类型/禁止兼容代码 | ✅ 全部新增函数有中文 docstring + 类型标注；无兼容性 re-export/wrapper |
| schema 变更：不新增 | ✅ |
| 测试：覆盖 ≥ 80% | ✅ 85% line coverage |
| pyright：0 errors | ✅ |

### prior findings 修复验证

| Finding | 来源 | 修复 | DS re-review | MiMo re-review | 本轮确认 |
|---------|------|------|-------------|---------------|---------|
| C1 — `run_id=None` metadata proof | Controller | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| M1 — 3+ 轮 rolling monotonicity | MiMo | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| M2 — reconnect 同源 | MiMo | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| M3 — design 校验时机表述 | MiMo | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| D2 — cross-reference 文档 | DS | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| D3 — docstring raises 格式 | DS | ✅ | ✅ ACCEPTED | ✅ ACCEPTED | ✅ |
| DS F1 — group[0] vs min() | DS | 拒绝（adjudication） | ✅ NOT ADOPTED | ✅ NOT ADOPTED | ✅ 拒绝理由成立 |

## Findings

未发现新的 correctness、semantic ownership drift、over-coupling 或 test fixture 真实性问题。

## Open Questions

无。

## Residual Risk

1. **Metadata-phase 全量 payload_json 加载**：`_post_compact_delta_rows` 现在读取当前 input 前全部 relevant canonical rows，每个 `EventLogRow` 构造包含完整 `payload_json`（schema 保证 NOT NULL）。对长 Session（数千 events），SQL 结果集内存占用随历史线性增长。accepted plan 风险表已明确接受此权衡（"accepted chain 读取成本随历史增长"），且 metadata-first approach 已避免 CPU 端 payload resolution（只对 conservative suffix 做 typed projection）。当前测试最大覆盖 ~20 events 的 fixture；长 Session 的 memory pressure 在生产 CLI observation 前无法验证。分类：accepted plan 已知的 trade-off，非 correctness issue。

2. **Production CLI observation 未执行**：F14 的 production CLI validation（真实 AAPL 2025 10-K corpus、真实 provider、FY2025 correction 进入 durable replacement、跨进程 reconnect）属于 Controller 后续 formal observation gate。deterministic owner tests 已独立证明 frontier correctness。分类：不在本 gate scope。

3. **全仓 frozen publication manifest 4 failures**：范围外既有 baseline inconsistency（manifest files 未被 F14 修改），owner 为 publication/config work unit。分类：不在本 gate scope。

4. **全仓 Ruff 89 errors**：全部位于本轮未修改文件；changed files focused Ruff 通过。分类：范围外 baseline。

5. **Group ordering 不变量无显式 assertion**：`_conservative_unconsumed_row_start_sequence` 中 `group[0].event_sequence` 的正确性依赖 SQL `ORDER BY event_sequence ASC` + `grouped` 单次 append 保持顺序 + EventLog 同一 Run 事件连续写入三个不变量。其中前两者在本函数 scope 内可验证（SQL 已声明 ORDER BY，`grouped` 构建在同一个 for 循环内），第三个由 EventLog append atomicity 保证。adjudication 已拒绝将 `group[0]` 改为 `min()`（认为重复计算不消除隐式依赖）。未来若引入非连续 Run 事件（如 attachment recovery），stage 2 atomic proof 会 fail-closed（`ValueError` → `HostDurableError`），不会静默丢失。分类：已知的已裁决 trade-off。

---

**Reviewer**: AgentDS
**Timestamp**: 2026-08-07T00:23:47+08:00
**Base**: b222b8b064f096d899a9de708e45cd1fb6e732e6
**Implementation**: 6eb41ac1
**Verdict**: PASS
