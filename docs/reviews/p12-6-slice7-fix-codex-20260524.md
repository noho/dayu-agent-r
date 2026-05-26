# P12.6 Slice 7 Targeted Fix - AgentCodex - 2026-05-24

## 结论

本次 targeted fix 已修复 Slice 7 implementation review 指出的生产 public path 缺口：public opener 默认触发的 proactive compact path 以及 RunInputBuilder material path 都能把当前 Session 内、当前 cursor 之前、未被 stable fact / compact artifact 表示的 accepted `TOOL_RESULT_ACCEPTED` raw evidence 转为 `CompactMaterialSection.EVIDENCE_INPUT` material block。

未 commit、未 push，未修改 `docs/host/implementation-control.md`。

## Root Cause

Controller 给出的事实成立。`RunInputBuilder.build_material_blocks()` 原先只消费 memory、compact artifact、session continuity 和 current input；`build_run_input_material_blocks()` 也只把这些 message/current facts 转成 material block。普通 accepted `TOOL_RESULT_ACCEPTED` raw evidence 留在 EventLog / payload descriptor 中，没有进入 compactor material pack 的 `evidence_input`。

补充核查 `docs/host/design.md` 后，没有设计证据表明 pre-start proactive compact 只能 current-input-only。设计写明 Context Governance 负责 compact 编排，compact input 使用与 RunInputBuilder 同源的 ordinary input material block view，并且 proactive 是 Attempt 创建前的 input governance。当前代码中 `dispatch._proactive_material_blocks()` 只构造 current input anchor，因此也是同一 root cause 在默认 public opener proactive path 上的生产缺口。

## 生产修复

修改 `dayu/host/run_input.py`：

- 新增 `AcceptedToolEvidenceMaterialProvider` 与 durable/noop 实现。
- 新增共享 helper `build_accepted_tool_evidence_material_blocks(...)`。
- helper 只读取当前 Session、指定 cursor 之前最近的 accepted `TOOL_RESULT_ACCEPTED`，固定上限为 8，并按 event sequence 升序稳定输出。
- raw evidence 解析复用 `dayu.host.compaction_evidence.collect_selected_compaction_request_evidence_inputs(...)`，不新建第二套工具结果 payload 解析。
- `RunInputBuilder.build_material_blocks()` 现在把 accepted evidence material 加入 ordinary material blocks。
- `MemorySnapshotView` / `CompactArtifactView` 增加 represented evidence refs，用于排除已被 stable fact 或 accepted compact artifact 表示的 evidence。

修改 `dayu/host/dispatch.py`：

- proactive pre-start material 不再只包含 current input anchor。
- proactive path 复用 `build_accepted_tool_evidence_material_blocks(...)`，从当前输入 cursor 之前补入 bounded accepted tool evidence。
- proactive path 读取 latest memory snapshot 的 stable fact evidence refs 与 latest compact artifact preserved canonical evidence refs，排除已表示 evidence。
- 未恢复 session 起点 range collector；未做 EventLog ledger dump；未读取 `result_preview`；LLM-facing material JSON 仍只由 compact material pack 暴露 prompt-local labels、tool/query/source/result text。

## Public Smoke 证据

更新 `tests/host/test_public_compact_smoke.py` 的 `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`：

- 使用真实 `open_host(options)` public opener。
- 第一轮通过 mock business tool 产生长章节 accepted raw tool evidence。
- 第二轮触发默认 proactive compact。
- 断言 fake compactor 记录的 public material JSON 中存在 `evidence_input`，且包含长章节 marker。
- 断言 material JSON 不包含 `result_preview`、`payload:` 或 `event-tool-result`。
- fake compactor 只用 prompt-local `E` label 生成 fact candidate。
- 第三轮断言后续 ordinary RunInput 中出现 `Memory evidence-backed facts:` 且包含长章节 marker，证明 memory / RunInputBuilder 可复用 compacted fact。
- 手造 `_llm_material_with_long_tool_evidence()` 仅保留为 helper-level 补充断言。

## 验证

已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q
```

结果：`5 passed, 1 skipped`

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_compact_smoke.py -q
```

结果：`292 passed, 1 skipped`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过，无 whitespace error。

## README 决策

已按触发规则检查并更新：

- `dayu/host/README.md`：同步说明 proactive pre-start material 会补入当前输入 cursor 之前、当前 Session 内、未被 stable fact / compact artifact 表示的 bounded accepted tool evidence。
- `tests/README.md`：同步 public compact smoke 的新增 production path 断言。

未修改根 README、`dayu/README.md` 或其它包 README，因为本次 public API、配置入口、分层关系和 Service/UI/Fins 边界没有变化。

## 风险与未覆盖

- proactive budget estimator 仍按当前输入估算触发条件；本次修复只补齐 compactor material evidence，不改变 context budget estimator 的输入模型。
- accepted evidence 读取上限为 8，满足 bounded/deterministic 要求；如果未来需要按 token budget 或 evidence priority 调整，需要独立设计。
- 真实 provider compactor smoke 仍默认 skip，本次验证使用 deterministic fake compactor 覆盖 public opener production path。
