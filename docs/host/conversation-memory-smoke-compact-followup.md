# Conversation Memory Smoke / Compact Follow-up Notes

本文记录 2026-06-19 `utils/smoke_host_public_conversation_memory_scenarios.py`
在 `--suite memory-compact --pressure-mode auto --long-rounds 25 --log-level DEBUG`
下暴露的三个后续问题，避免后续上下文 compact 后丢失判断依据。

本文不是设计真源。Host / memory / compact 设计真源仍是
`docs/host/design.md` 与 `docs/engine/design.md`。GitHub issue 80 只作为
Conversation Memory eval 目标参考，不要求一次性塞进 smoke。

## 当前停止点

- 当前工作区已有未完成 smoke/log 增强改动，集中在：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - `README.md`
  - `tests/README.md`
- 曾短暂出现的 `dayu/host/compact_material.py` production parser 诊断改动已回退。
- 后续恢复实施前，必须先检查当前 dirty diff，决定保留、修正或回退这些未完成 smoke 改动。

## 三个待修问题

### 1. 日志不足

现象：

- long25 日志能看到 compact failure 类型、run id、attempt number 和错误摘要。
- EventLog 能确认两个 `CONTEXT_COMPACTION_FAILED` 已落成 durable fact。
- 但日志和 EventLog 都不能直接定位 offending compact material block 或 rejected candidate 原文。

直接证据：

- 最终 round `long-l25-constraint-assert` terminal 为 `succeeded`。
- smoke 最终失败原因是 `memory-compact observed CONTEXT_COMPACTION_FAILED`。
- compact audit 汇总为：
  - `requested_proactive=6`
  - `compacted_proactive=4`
  - `failed_proactive=2`
  - `rejected_proactive=25`
- 两个 failed operation：
  - request seq 340 -> rejected seq 343..347 -> failed seq 348
  - request seq 362 -> rejected seq 365..369 -> failed seq 370
- failed payload 均有 `fallback_action=dispatch`，表示 Host 兜底继续 dispatch 了当前 run；
  这不等于 compact 成功，`memory-compact` suite 仍应 hard fail。

关键不足：

- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 只提供 `diagnostic_refs`，例如
  `ValueError:previous reference continuity text is invalid`。
- 这些 failed attempts 的 `proposal_manifest_ref` 为空，因此没有 rejected proposal /
  prepared runner input manifest 可打开。
- 当前日志没有输出 offending `previous_compacted_view` block 的 section、kind、label、
  content digest、event sequence、line index 或安全文本摘录。

下一步 smoke/log 修复目标：

- 输出 per-compact-operation timeline：
  - `operation_id`
  - request event sequence
  - run id
  - trigger source
  - rejected attempt count
  - final status: compacted / failed / pending
  - accepted seq / failed seq
  - failure reason
  - fallback action / fallback policy decision
- 输出 attempt reject histogram：
  - by `failure_category`
  - by normalized diagnostic suffix
  - by `proposal_manifest_ref` present / missing
- 当 `proposal_manifest_ref` 缺失且错误发生在 proposal preparation 前，输出类似：
  - `failure_stage=prepare_or_material_projection`
  - `log_insufficient=offending_material_block_unavailable`
- 修复 stdout 粘连问题：
  - long25 日志中 `SMOKE TOOL_CALLS_BY_KEY ...SMOKE FAIL` 粘在同一行。
  - 需要确保 failure、audit、tool summary 都独立换行并 flush。

非目标：

- 本问题不修改 production compact parser、accept barrier 或 compactor prompt。
- 不因为 `fallback_action=dispatch` 就把 `CONTEXT_COMPACTION_FAILED` 算作 smoke pass。

### 2. Smoke 还应加强的地方

issue 80 的评测目标强调 Conversation Memory 不能只看最终回答；应分层观察
Memory Store、Memory Projection、Prompt Assembly 与 Agent Outcome。第一版 eval
建议检查 memory snapshot、RunInputBuilder messages、tool call counts、diagnostics
和 final response facts。

当前 smoke 更接近“public Host 端到端行为 + compact audit”，覆盖不足主要在：

- 只输出 aggregate compact audit，不输出 operation-level compact timeline。
- 能发现 compact failed，但不能直接说明是 normal compact、repair 后 accepted、
  recovery fallback、dispatch fallback 还是 fail closed。
- `requested_reactive=0`，没有覆盖 reactive compact。
- 没有明确覆盖 fallback compact tier 1-3 与 dispatch fallback tier 4-5 的区别。
- 没有系统化检查 prompt assembly 层的 rendered memory material：
  - latest accepted compacted view
  - post-compact delta material
  - current input anchor
  - current input anchor 不应变成 citable source
- 没有系统化检查 memory snapshot 层：
  - snapshot cursor
  - accepted compact artifact
  - evidence-backed facts / answer anchors / forward intents /
    reference continuity items 的数量与来源标签
- 对 conflict / update、abstention / refusal、tool reuse efficiency 的覆盖仍弱。

建议分层，不把 issue 80 全量内容塞进日常 smoke：

- Daily smoke：
  - public Host end-to-end memory-core
  - memory-compact basic pressure
  - compact requested / compacted / failed / artifact presence
  - tool call count 与关键 final facts
- Diagnostic smoke：
  - per-operation compact timeline
  - rejected attempt histogram
  - fallback dispatch details
  - prompt assembly / memory snapshot 抽样诊断
- Eval / regression suite：
  - conflict / update
  - abstention / refusal
  - cross-session / dynamic profile
  - finance-specific provenance 与 evidence-backed fact recall

### 3. `--long-rounds 25` 暴露的 memory 问题

结论：

- 这次 long25 不是 smoke 误报。
- 25 轮最终回答本身成功，但 proactive compact 6 次中只有 4 次 accepted，
  2 次写入 `CONTEXT_COMPACTION_FAILED`。
- 对长期会话来说，这是 memory compact 稳定性问题：系统会越来越依赖
  deterministic recent-window dispatch fallback，而不是稳定滚动 accepted compacted view。

需要修正此前判断：

- 之前曾将主因概括为“compactor LLM / repair prompt 多次产出非法 proposal”。
- 代码与 EventLog 复核后，这个说法对两个 durable `CONTEXT_COMPACTION_FAILED`
  主链路不够准确。
- 这两个 failed operation 的 rejected attempts 中 `proposal_manifest_ref` 为空。
  在当前代码路径里，manifest 是在 `prepare_compactor_proposal_run_input` 成功后才记录；
  因此 `proposal_manifest_ref` 为空说明主失败发生在 runner call manifest 写入前。

更准确的主链路：

```text
CompactionOperation
  -> _prepare_compactor_proposal
  -> LLMContextCompactor.prepare_compactor_proposal_run_input
  -> conversation_compact_input_vnext_from_material_pack
  -> _previous_compacted_view_vnext
  -> _previous_compacted_references_vnext
  -> _parse_previous_reference_continuity_text
  -> ValueError("previous reference continuity text is invalid")
```

也就是说，两个 durable compact failure 的主问题更像是 Host 侧
compact material projection / previous compacted view 再投影路径不可解析，
而不是 LLM 已返回 proposal 后被 source-label accept barrier 拒绝。

同时日志中还观察到其它 proposal schema reject 信号：

- `reference_continuity_items[*].source_labels contains cross-section label: E1`
- `forward_intents[0].source_labels cites current input anchor: C1`

这些 reject 本身符合设计：

- `current_input_anchor` readable but not citable。
- candidate source labels 必须引用本次 prompt-local allowed labels。
- 未知、跨 section、stale、缺 source label、引用 current input anchor 都是 invalid。

但这些 label reject 不能与两个 durable `CONTEXT_COMPACTION_FAILED` 的主链路混为一谈；
它们应作为 secondary observed compact proposal robustness signals 单独分析。

production memory 后续调查方向：

- 查 `previous_compacted_view` 的 material block 是如何从 latest accepted compacted view /
  memory snapshot 渲染出来的。
- 查 `_parse_previous_reference_continuity_text` 依赖的文本协议：
  - 当前是 `reference_continuity=<reason>; text=<text>`。
  - parser 用 `split("; ")` 反解析。
  - 该文本协议是否可能被 business text 中的 `; `、换行、prefix 碰撞或旧 block shape 破坏。
- 查 recovery tiers 为什么在部分 operation 中 rejected 5 次后仍可 `CONTEXT_COMPACTED`
  （例如 seq 394 -> 401、490 -> 497、612 -> 619），而前两个 operation 最终 failed。
- 查 failed operation 的 fallback payload：
  - `fallback_action=dispatch`
  - `fallback_policy_decision=deterministic_recent_window`
  - 说明用户 run 被兜底执行，但 compact memory 没有成功物化。

production memory 修复非目标：

- 不放宽 accept barrier。
- 不让 current input anchor 成为可引用 source。
- 不把 LLM-facing memory / compact material 截断、preview 化或 summary 化来掩盖问题。
- 不把 failed dispatch fallback 写成 compact success。

## 后续实施建议

建议按三个独立 work unit 处理：

1. Smoke/log diagnostics only
   - 只改 `utils/`、测试和 README。
   - 增加 compact operation timeline、histogram、log insufficiency 标记、stdout 换行。
   - 不改 production memory。

2. Smoke/eval coverage expansion
   - 明确 daily smoke / diagnostic smoke / eval suite 边界。
   - 增加 reactive compact、fallback compact、prompt assembly / snapshot 抽样检查。
   - 不把 issue 80 全量目标塞进同一个 smoke。

3. Production memory compact failure
   - 单独修 Host compact material projection / previous compacted view 再投影问题。
   - 修复后再用 `--suite memory-compact --pressure-mode auto --long-rounds 25`
     复跑验证。

## 验收信号

Smoke/log diagnostics work unit 完成后，long25 再失败时应无需查 SQLite 就能看到：

- 哪个 operation failed。
- 它请求于哪个 event sequence。
- 它属于 proactive 还是 reactive。
- 它 rejected 了多少 attempt。
- 每类 rejected diagnostic 出现次数。
- 最终是 compacted、failed、fallback dispatch 还是 fail closed。
- 若无法定位 offending material block，stdout 应明确标记 log insufficiency。

Production memory work unit 完成后：

- long25 不应再出现 `CONTEXT_COMPACTION_FAILED`。
- 若仍出现，应能从新日志直接定位 offending material / proposal stage。
- accepted compact 不得通过截断、summary 化、preview 化 memory material 来换取通过。
