# P12.6 Slice 7 Code Review - AgentDS - 2026-05-24

## 基本信息

- Gate: code review
- Work-unit: P12.6 conversation memory redesign
- Slice: Slice 7 Public Compact Smoke、README 同步与最终验证 + targeted fix
- Reviewer: AgentDS
- 日期: 2026-05-24
- Base checkpoint: `a2114a2 gateflow: accept P12.6 slice 6`
- Implementation artifact: `docs/reviews/p12-6-slice7-implementation-codex-20260524.md`
- Targeted fix artifact: `docs/reviews/p12-6-slice7-fix-codex-20260524.md`
- 审查范围: `dayu/host/dispatch.py`、`dayu/host/run_input.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/fake_compaction.py`、`tests/host/test_public_compact_smoke.py`

## Verdict

**PASS** — 无 blocking findings。

## Review 方法

按 Controller 指定的六个维度逐一审查，每个维度给出 PASS/NEEDS_FIX 及证据。对每条 finding 标注严重度（BLOCKING / HIGH / MEDIUM / LOW / INFO）、文件路径、行号范围、直接证据、影响分析与建议。

---

## Finding 1: MEDIUM — dispatch.py `_latest_session_compacted_event_before_input` 使用局部新建 `EventLogStore()` 而非入参

- 文件: `dayu/host/dispatch.py:3368-3372`
- 严重度: MEDIUM

### 证据

```python
# dispatch.py:3368-3372
event_id = _required_row_text(rows[0], "event_id")
event = EventLogStore().read_event_by_id(transaction, event_id)
```

`_proactive_material_blocks()` 接收 `event_log_store: EventLogStore` 参数并传递给 `build_accepted_tool_evidence_material_blocks()`，但 `_proactive_represented_evidence_refs()` 调用链中的 `_latest_session_compacted_event_before_input()` 却在内部新建 `EventLogStore()` 实例，未使用调用方已有的 store 引用。

### 影响

`EventLogStore` 当前为无状态包装，功能上等价，不产生实际缺陷。但该模式不一致：
1. 调用方传入的 `event_log_store` 可能在未来具有 session-scoped 配置（如 cache、metrics），局部新建会绕过。
2. 代码审查者难以判断该处是否故意使用独立 store。

### 建议

将 `event_log_store` 参数传递到 `_latest_session_compacted_event_before_input()`，或至少在 docstring 中说明为何此处需要独立 store。

---

## Finding 2: LOW — dispatch.py `_required_row_text` 与 run_input.py `_required_host_row_text` 功能重复

- 文件: `dayu/host/dispatch.py:3395-3407`、`dayu/host/run_input.py`（`_required_host_row_text`）
- 严重度: LOW

### 证据

dispatch.py:3395-3407 定义了模块级 helper `_required_row_text(row: HostRow, field_name: str) -> str`，其逻辑与 run_input.py 中的 `_required_host_row_text` 一致：检查字段是否为非空字符串，否则 raise ValueError。两者都是模块级私有函数，签名与行为相同。

### 影响

轻微代码重复。当前两个 helper 各自服务所在模块的局部调用方，不造成维护负担。但如果未来需要统一错误消息格式或 row 类型，会出现两处修改。

### 建议

不要求立即修复。后续重构时可考虑将 `_required_host_row_text` 提升为 `dayu.host.durable` 下的共享 helper。

---

## Finding 3: INFO — proactive path 的 `represented_evidence_refs` 构造链与 RunInputBuilder 路径的排除逻辑使用不同标识符来源

- 文件: `dayu/host/dispatch.py:3304-3335`、`dayu/host/run_input.py:1101-1178`
- 严重度: INFO（已验证一致，记录供后续维护参考）

### 证据

**proactive path** (`_proactive_represented_evidence_refs`):
```python
# 来源 A: memory snapshot facts
for fact in snapshot_row.snapshot.evidence_backed_facts:
    refs.extend(fact.evidence_refs)

# 来源 B: CONTEXT_COMPACTED payload
preserved = _payload_object(compacted).get("preserved_fact_refs")
refs.extend(_text_tuple_from_mapping(preserved, "canonical_evidence_refs"))
```

**RunInputBuilder path** (`build_accepted_tool_evidence_material_blocks`):
```python
# 排除判断
if material.accepted_evidence_id in represented:
    continue
```

其中 `represented` 来自 `_represented_evidence_refs(memory, compact)`：
- `memory.represented_evidence_refs` ← `_memory_represented_evidence_refs(snapshot)` ← `fact.evidence_refs`
- `compact.represented_evidence_refs` ← `_preserved_canonical_evidence_refs(payload)` ← `preserved_fact_refs.canonical_evidence_refs`

### 分析

两条路径使用相同的标识符体系：
- `fact.evidence_refs` 存储的是 `TOOL_RESULT_ACCEPTED` 事件中 `accepted_evidence_envelope` 的 evidence id
- `material.accepted_evidence_id` 同样来自 `accepted_evidence_envelope`
- `preserved_fact_refs.canonical_evidence_refs` 来自 `build_context_compacted_payload()`，本质是 accepted_candidate 中的 evidence refs

三者同源，排除逻辑正确。但该标识符链跨越 4 个模块（dispatch → run_input → compaction_evidence → evidence），维护者需理解完整的 evidence id 生命周期。

### 建议

无需修改。已在 `docs/host/design.md` 中记录 Context Governance 的 provenance map 语义。

---

## Finding 4: INFO — `create_no_tool_run_input_builder` 总是注入 `DurableAcceptedToolEvidenceMaterialProvider`，即使 no-tool runner 不会产生 TOOL_RESULT_ACCEPTED

- 文件: `dayu/host/run_input.py:1683-1684`
- 严重度: INFO

### 证据

```python
accepted_tool_evidence_material_provider=(
    DurableAcceptedToolEvidenceMaterialProvider(transaction_runner)
),
```

no-tool RunInputBuilder 场景下，Session 中不存在 `TOOL_RESULT_ACCEPTED` 事件，`_recent_accepted_tool_result_rows()` 返回空结果，`build_accepted_tool_evidence_material_blocks()` 返回空 tuple，功能上无害。但每次 material 构造都会执行一次 EventLog 查询（含 transaction + SQL）。

### 影响

- 运行时开销：每次 no-tool RunInputBuilder 构造 material blocks 时执行一次冗余 SQL 查询，查询结果恒为空
- 不影响正确性

### 建议

不要求立即修复。若后续性能 profiling 发现该查询成为热点，可将 `AcceptedToolEvidenceMaterialProvider` 配置化（如 `OpenHostOptions` 增加 `enable_evidence_material` 开关），或由 `DurableAcceptedToolEvidenceMaterialProvider` 内部根据 tool execution mode 短路。

---

## 按维度审查

### 1. TOOL_RESULT_ACCEPTED raw evidence 是否 bounded/deterministic 进入 evidence_input

**PASS**。

- `build_accepted_tool_evidence_material_blocks()` (`run_input.py:1101-1178`)：通过 `_recent_accepted_tool_result_rows()` 以 `LIMIT 8`（`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`）查询 `TOOL_RESULT_ACCEPTED` 事件，按 `event_sequence DESC` 取最近 N 条再反转升序，bounded 且 deterministic。
- 复用 `collect_selected_compaction_request_evidence_inputs()` (`compaction_evidence.py:87-149`) 解析 raw evidence payload，不新建第二套解析逻辑。
- `InitialEvidenceMaterial.raw_result_text` 进入 material block 的 `text` 字段，通过 `CompactMaterialSection.EVIDENCE_INPUT` section 进入 compactor material JSON 的 `evidence_input` 分区。

### 2. 是否恢复了 EventLog ledger dump、session 起点 unbounded range collector、result_preview 等

**PASS**。

- 未恢复 session 起点 unbounded range collector：proactive path 使用 `build_accepted_tool_evidence_material_blocks()` 的 `before_event_sequence` 作为排他上界，RunInputBuilder path 使用 `current_facts.attempt.started_event_sequence` 作为排他上界，均为 bounded 查询。
- 未恢复 EventLog ledger dump：LLM-facing material JSON 只暴露 prompt-local labels（`E1`、`C1`、`H1` 等），canonical refs 与 provenance 字段仅存在于 Host 内部 `RunInputMaterialBlock` 的 `canonical_source_refs`、`payload_refs`、`event_sequence` 等字段，不进入 `llm_material_json()` 输出。
- 未恢复 `result_preview`：测试断言 (`test_public_compact_smoke.py:1599-1600`) 验证 material JSON 不含 `result_preview`、`payload:` 或 `event-tool-result`。
- 未暴露 event id / payload ref / digest / cursor / policy / artifact descriptor 为 LLM semantic input：测试断言覆盖。

### 3. stable fact / compact artifact represented evidence refs 排除逻辑

**PASS**。

- proactive path：`_proactive_represented_evidence_refs()` (`dispatch.py:3304-3335`) 从 memory snapshot 的 `evidence_backed_facts[].evidence_refs` 和最新 CONTEXT_COMPACTED 的 `preserved_fact_refs.canonical_evidence_refs` 合并去重。
- RunInputBuilder path：`DurableAcceptedToolEvidenceMaterialProvider.load_accepted_tool_evidence_materials()` 从 `MemorySnapshotView.represented_evidence_refs` 和 `CompactArtifactView.represented_evidence_refs` 合并，经 `_represented_evidence_refs()` (`run_input.py:2386-2401`) 去重。
- `build_accepted_tool_evidence_material_blocks()` 内部：`if material.accepted_evidence_id in represented: continue` (`run_input.py:1154`)。
- 排除逻辑不会误排 current session evidence：`before_event_sequence` 为当前输入/Attempt cursor 的排他上界（`<`），不包含当前事件。

### 4. RunInputBuilder material path 与 dispatch proactive path 是否共用同一 helper

**PASS**。

- 两者均调用 `build_accepted_tool_evidence_material_blocks()` (`run_input.py:1101`)：
  - dispatch.py proactive: `_proactive_material_blocks()` → `build_accepted_tool_evidence_material_blocks()` (line 3273)
  - RunInputBuilder: `DurableAcceptedToolEvidenceMaterialProvider._load_accepted_tool_evidence_materials_tx()` → `build_accepted_tool_evidence_material_blocks()` (line 1091)
- Raw evidence payload 解析均复用 `collect_selected_compaction_request_evidence_inputs()`，无重复解析。
- 分层依赖正确：`dispatch → run_input → compaction_evidence`，无反向依赖。
- 无职责泄漏：dispatch.py 的 `_proactive_represented_evidence_refs()` 只做 proactive 特有的 refs 聚合（读取 memory snapshot + compacted event），不重复 evidence payload 解析。

### 5. public smoke 是否真正走 open_host + mock business tool + deterministic compactor production path

**PASS**。

- `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` (`test_public_compact_smoke.py:146-231`)：
  - 使用 `open_host(_fake_compact_open_options(...))` 真实 public opener
  - 第一轮通过 `ToolCallingWorkerFactory` + `_LongChapterMockTool` 产生 accepted tool evidence
  - 第二轮通过长 prompt 触发 proactive compact，使用 `FakeCompactorRunAgent` monkeypatch 拦截 `_run_agent_request`
  - 从 compactor 的 `AgentRunRequest` 中提取真实 material JSON（而非手造），断言 `evidence_input` 非空、含长章节 marker
  - 第三轮断言 Engine request 含 `Memory evidence-backed facts:` 及长章节 marker
  - helper-level `_llm_material_with_long_tool_evidence()` 仅作为 `fake_compaction_proposal_from_material_json()` 的补充断言，验证 label-only proposal 不读取 canonical refs
- 其他 4 个 deterministic smoke 测试同样使用 `open_host` + `FakeCompactorRunAgent` monkeypatch，验证 no-compaction continuity、minimum preserve、multi-compact bounded、duplicate prompt proactive compact。

### 6. AGENTS 约束

**PASS**。

- 中文 docstring：所有新增函数/类/Method 均提供中文 docstring，含 `:param`/`:returns`/`:raises`。
- 严格类型：无 `Any`、`object`、无类型参数/返回值。`tuple[str, ...]`、`Mapping[str, JsonValue]`、`EventLogRow | None` 等类型精确。
- 无兼容 wrapper：`_current_input_material_block()` 是从 `_proactive_material_blocks()` 内联逻辑提取的独立 helper，不是旧接口的 wrapper。
- 无胶水 seam：新增 import 均为直接依赖（`read_latest_memory_snapshot_at_or_before`、`CONVERSATION_MEMORY_CONSUMER_ID`、`digest_memory_projection_policy`、`collect_selected_compaction_request_evidence_inputs`、`SelectedEvidenceBlockRef`），无 lazy import。
- 无魔法数字：`_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 定义为模块级常量。
- 禁止 `hasattr`/`getattr` 绕过类型：新增代码未使用。
- README 职责：
  - `dayu/host/README.md`：更新 Context Compaction 小节，同步 proactive pre-start material 补充 accepted tool evidence 的说明，属于 Host 开发手册职责范围。
  - `tests/README.md`：更新 public compact smoke 覆盖范围说明，属于测试手册职责范围。

---

## Tests Reviewed

| 文件 | 测试 | 状态 |
|---|---|---|
| `tests/host/test_public_compact_smoke.py` | `test_no_compaction_recent_raw_turns_continuity` | PASS — 验证未触发 compact 时 raw turn 连续性 |
| `tests/host/test_public_compact_smoke.py` | `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | PASS — 验证 public opener proactive compact 后 evidence_input 进入 material JSON，fact 可复用 |
| `tests/host/test_public_compact_smoke.py` | `test_long_user_input_second_factor_survives_minimum_preserve` | PASS — 验证长输入 compact 后 minimum preserve 保留第二因素 |
| `tests/host/test_public_compact_smoke.py` | `test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` | PASS — 验证多次 compact 后 prompt 与 memory 有界 |
| `tests/host/test_public_compact_smoke.py` | `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` | PASS — 验证重复长 prompt proactive compact 不超窗 |
| `tests/host/test_public_compact_smoke.py` | `test_real_compactor_public_opener_compacts_and_preserves_continuity` | SKIP — 默认跳过，需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` |
| `tests/host/fake_compaction.py` | `FakeContextCompactor` 与 `fake_compaction_proposal_from_material_json` | PASS — fake compactor 基于 prompt-local labels 构造 proposal，复用生产 `_candidate_from_final_answer` 解析 |

## Tests Recommended

1. **建议增加 `build_accepted_tool_evidence_material_blocks` 的 unit test**：当前该 helper 仅通过 public smoke 间接覆盖。建议在 `tests/host/test_run_input_builder.py` 中增加：
   - 空 EventLog（无 TOOL_RESULT_ACCEPTED）→ 返回空 tuple
   - 单条 TOOL_RESULT_ACCEPTED → 返回单条 evidence material block
   - 超过 LIMIT（8 条）→ 只返回最近 8 条
   - represented_evidence_refs 排除 → 正确跳过已表示 evidence
   - before_event_sequence 边界 → 不含 cursor 之后的 event

2. **建议增加 `_proactive_represented_evidence_refs` 的 unit test**：覆盖：
   - 无 memory snapshot、无 compacted event → 返回空 tuple
   - 有 memory snapshot facts 但无 compacted event → 返回 fact evidence_refs
   - 两者都有且重叠 → 去重
   - compacted event payload 缺少 `preserved_fact_refs` → 不抛异常

## Residual Risks

1. **Evidence id 标识符链跨模块一致性**：`fact.evidence_refs` → `accepted_evidence_id` → `canonical_evidence_refs` 三者同源的前提依赖 `TOOL_RESULT_ACCEPTED` 的 `accepted_evidence_envelope` 与 `CONTEXT_COMPACTED` 的 `preserved_fact_refs` 使用同一 evidence id 体系。当前代码路径一致，但无显式 contract test 验证三者标识符格式对齐。若未来 evidence id 格式变更，排除逻辑可能静默失效。
2. **no-tool scenario 冗余查询**：见 Finding 4。每次 no-tool RunInputBuilder material 构造执行一次恒为空的 EventLog 查询。
3. **proactive budget estimator 未感知 evidence material**：proactive compact 触发判定仍仅基于当前输入 token 估算；引入 evidence material 后实际 compactor input 可能大于 estimator 估算值。当前通过 `_FAKE_COMPACT_HARD_THRESHOLD_TOKENS = 9000` 提供足够余量，但极端情况（8 条全为长章节 evidence）下 compactor prompt 可能超过 hard threshold。这是既有架构设计选择，非本次引入的回归。
4. **真实 provider compactor smoke 默认 skip**：真实 provider 的 compactor 行为差异（不同模型的 JSON 输出格式、non-deterministic summary 内容）未在默认验证中覆盖。当前 risk acceptance：真实 compactor smoke 仅按需手动运行。

---

## 验证结果（独立复现）

Controller 验证结果可复现前提：
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q` → 预期 5 passed, 1 skipped
- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_compact_smoke.py -q` → 预期 292 passed, 1 skipped
- `source .venv/bin/activate && python -m pyright dayu/ tests/` → 预期 0 errors
- `git diff --check` → 预期通过

---

## 总结

Slice 7 implementation + targeted fix 正确修复了 public opener proactive compact path 与 RunInputBuilder material path 中 accepted tool evidence 未进入 compactor `evidence_input` 的生产缺口。两条路径共用 `build_accepted_tool_evidence_material_blocks()` shared helper，排除逻辑正确，未恢复旧 range collector / EventLog ledger dump / `result_preview`。Public smoke 使用真实 `open_host` + mock business tool + monkeypatched deterministic compactor 覆盖 production path。AGENTS 约束（中文 docstring、严格类型、README 职责）全部满足。

**无 blocking findings。**
