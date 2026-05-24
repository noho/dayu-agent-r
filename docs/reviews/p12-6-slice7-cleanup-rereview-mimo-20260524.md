# P12.6 Slice 7 Cleanup Re-review - AgentMiMo - 2026-05-24

## Verdict

**PASS** — 所有 accepted findings 已修复，cleanup 未引入新 blocking/high findings，原有 public proactive accepted evidence success signal 仍成立。

## Re-review 范围

- Base: `a2114a2 gateflow: accept P12.6 slice 6`
- Cleanup agent: AgentCodex
- 原 review artifacts: MiMo (`p12-6-slice7-code-review-mimo-20260524.md`)、DS (`p12-6-slice7-code-review-ds-20260524.md`)
- Cleanup artifact: `p12-6-slice7-cleanup-codex-20260524.md`
- Diff 范围: `dayu/host/compact_payload.py`（新）、`dayu/host/dispatch.py`、`dayu/host/run_input.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/fake_compaction.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_run_input_builder.py`
- 忽略: `docs/host/implementation-control.md`

---

## Accepted Findings 修复状态

### MiMo F1 [Medium] `_text_tuple_from_mapping` 与 `_optional_text_list` 逻辑重复 → FIXED

**修复方式**: 新建 `dayu/host/compact_payload.py` 模块，将 `optional_text_list_field` 抽取为公共 helper。

**验证**:
- `dispatch.py` 中 `_text_tuple_from_mapping` 已删除（grep 确认无匹配）。
- `run_input.py` 中 `_optional_text_list` 已删除（grep 确认无匹配）。
- `dispatch.py` 第 131 行 `from dayu.host.compact_payload import preserved_canonical_evidence_refs`，`_proactive_represented_evidence_refs` 在第 3335 行调用 `preserved_canonical_evidence_refs(_payload_object(compacted))`。
- `run_input.py` 第 46-49 行 `from dayu.host.compact_payload import optional_text_list_field, preserved_canonical_evidence_refs, preserved_fact_refs_summary`，`_optional_summary_text_from_compacted_payload` 在第 2690-2691 行调用 `optional_text_list_field`，`DurableCompactArtifactProvider` 在第 1267 行调用 `preserved_canonical_evidence_refs`。
- 无重复解析逻辑残留。

### MiMo F2 [Medium] proactive represented evidence refs 构造未复用 `_preserved_canonical_evidence_refs` → FIXED

**修复方式**: `dispatch._proactive_represented_evidence_refs` 现在导入并调用 `compact_payload.preserved_canonical_evidence_refs`。

**验证**:
- `dispatch.py:3335` — `refs.extend(preserved_canonical_evidence_refs(_payload_object(compacted)))`，直接复用 compact_payload helper，无手写两层嵌套。

### DS Finding 1 / MiMo F4 [Low→Medium] `_latest_session_compacted_event_before_input` 使用局部新建 `EventLogStore()` → FIXED

**修复方式**: `_latest_session_compacted_event_before_input` 签名新增 `event_log_store: EventLogStore` 参数，内部使用该参数（第 3371 行 `event = event_log_store.read_event_by_id(transaction, event_id)`）。

**验证**:
- 签名: `dispatch.py:3339-3340` — `(transaction: HostTransaction, event_log_store: EventLogStore, *, run: RunRow)`
- 调用方传入: `dispatch.py:3331-3332` — `_latest_session_compacted_event_before_input(transaction, event_log_store, run=run)`，`event_log_store` 来自 `_proactive_represented_evidence_refs` 的参数。
- 上层传入: `dispatch.py:1380-1382` — `_proactive_represented_evidence_refs(transaction, self._event_log_store, ...)`，使用 `HostDispatchScheduler._event_log_store`。
- 无局部新建 `EventLogStore()` 残留。

### MiMo F3 [Low] `fake_compaction.py` 导入 `_candidate_from_final_answer` 私有符号 → ACCEPTED AS NON-BLOCKING（cleanup artifact 已记录）

未修改，符合 controller 指令。

---

## Cleanup 是否引入新问题

### 分层 / 依赖方向

- `compact_payload.py` 只依赖 `dayu.contracts.json_value.JsonValue` 和 `collections.abc.Mapping`，无反向依赖。
- `dispatch.py` 和 `run_input.py` 都从 `compact_payload` 导入，依赖方向正确（上层 → 同层共享 helper）。
- `dispatch.py` 已有的 `from dayu.host.run_input import ...` 未新增符号，F1/F2 修复通过 `compact_payload` 共享而非跨模块私有 helper 导入，避免了 dispatch 对 run_input 私有符号的新增耦合。

### 类型 / Docstring

- `compact_payload.py` 三个函数均有完整中文 docstring，含 `:param` / `:returns`。
- 类型签名严格：`Mapping[str, JsonValue]`、`tuple[str, ...]`，无 `Any` / `object`。
- `_latest_session_compacted_event_before_input` 新增参数 `event_log_store: EventLogStore` 类型正确，docstring 已同步更新。

### `_preserved_fact_refs_text` 移除

- `run_input.py` 中 `_preserved_fact_refs_text` 已删除（grep 确认无匹配），其 payload field 常量 `_PAYLOAD_FIELD_PRESERVED_FACT_REFS`、`_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS`、`_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS` 也已删除（diff 确认）。
- `test_run_input_builder.py` 第 1115 行断言改为 `preserved_fact_refs_summary(payload)`（来自 `compact_payload`），测试语义不变。

### README 同步

- `dayu/host/README.md` Context Compaction 段落新增 "proactive pre-start material 会补入当前输入 cursor 之前、当前 Session 内、未被 stable fact / compact artifact 表示的 bounded accepted tool evidence" 描述，在 Host 开发手册职责范围内。
- `tests/README.md` public-path smoke 段落更新为更精确的 smoke 测试覆盖描述（no-compaction continuity、deterministic proactive compact、evidence_input 进入 material JSON、minimum preserve、multi-compact bounded、duplicate prompt bounded），在测试手册职责范围内。
- 无越界内容。

### DS Finding 2 [Low] `_required_row_text` 与 `_required_host_row_text` 重复 → NOT IN CLEANUP SCOPE

未修改，符合 controller 指令。当前两处 helper 各自服务所在模块，不构成 blocking issue。

---

## Public Proactive Accepted Evidence Success Signal 是否仍成立

**仍成立。**

- `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 通过 `open_host(_fake_compact_open_options(...))` 走真实 public opener。
- 第一轮通过 `ToolCallingWorkerFactory` + `_LongChapterMockTool` 产生 accepted raw tool evidence。
- 第二轮触发 proactive compact（soft threshold 90 tokens，长输入），`FakeCompactorRunAgent` monkeypatches `_run_agent_request`。
- 断言 compactor material JSON 包含 `evidence_input` 且含 `_LONG_CHAPTER_MARKER`。
- 断言第三轮 RunInput 包含 `Memory evidence-backed facts:` 且含 marker。
- 测试结果: `5 passed, 1 skipped`，与 cleanup artifact 声称一致。

---

## 验证结果（独立复现）

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_public_compact_smoke.py -q` | ✅ 5 passed, 1 skipped |
| `pytest tests/host/test_compaction_contract.py ... test_public_compact_smoke.py -q` | ✅ 292 passed, 1 skipped |
| `pyright dayu/host/compact_payload.py dayu/host/dispatch.py dayu/host/run_input.py tests/host/fake_compaction.py tests/host/test_public_compact_smoke.py tests/host/test_run_input_builder.py` | ✅ 0 errors, 0 warnings, 0 informations |
| `git diff --check` | ✅ 无 whitespace 问题 |

---

## Residual Risks（继承自原 review，cleanup 未改变）

1. **Evidence id 标识符链跨模块一致性**：`fact.evidence_refs` → `accepted_evidence_id` → `canonical_evidence_refs` 三者同源的前提依赖 `TOOL_RESULT_ACCEPTED` 的 `accepted_evidence_envelope` 与 `CONTEXT_COMPACTED` 的 `preserved_fact_refs` 使用同一 evidence id 体系。当前一致，无显式 contract test。
2. **proactive budget estimator 未感知 evidence material**：proactive compact 触发判定仍仅基于当前输入 token 估算；引入 evidence material 后实际 compactor input 可能大于 estimator 估算值。
3. **accepted evidence 读取上限硬编码为 8**：未来若需按 token budget 或 evidence priority 调整，需独立设计。
4. **真实 provider compactor smoke 默认 skip**：真实 LLM 输出解析路径需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 单独验证。

---

## 总结

Cleanup 正确修复了 MiMo F1/F2（重复 payload 解析逻辑抽取到 `compact_payload`）和 DS Finding 1 / MiMo F4（`EventLogStore` 参数注入）。新增 `compact_payload.py` 模块分层干净、类型严格、docstring 完整。README 同步在职责范围内。测试和 pyright 全部通过。无新 blocking/high findings。
