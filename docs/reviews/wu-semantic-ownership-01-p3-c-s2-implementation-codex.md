# WU-SEMANTIC-OWNERSHIP-01 P3-C S2 implementation artifact

状态：PASS

## Root cause / owner boundary

S2 的问题成立。旧实现同时存在三类 ownership 漂移：

- previous compacted view 同一语义既能从 accepted compact candidate 读取，也能经 compact material / run input 的字符串 round-trip 和 memory snapshot 重建。
- ordinary RunInput 把 accepted compact artifact 当作第二套 compact renderer 注入 messages，和 Conversation Memory 的 accepted compact materialization 形成重复投影。
- post-compact budget 在 compaction operation 内部用本地 fragment traversal 估算，预算 owner 不在 `context_budget`，且 diagnostic 文本存在被误纳入预算的风险。

owner boundary 判定：

- accepted compact candidate 的 durable truth owner 是 `CONTEXT_COMPACTED` payload；typed 读取 owner 是 `dayu.host.compact_payload`。
- previous compacted blocks + typed readable view pair 的生成 owner 是 compact material projector；校验 owner 是 `CompactMaterialPack` / source snapshot 边界。
- ordinary RunInput 的 compact catch-up correctness owner 是 RunInputBuilder 对 compact event ref 与 memory latest compaction ref 的一致性校验；LLM-facing compact business facts 只能来自 Conversation Memory。
- post-compact budget owner 是 `dayu.host.context_budget`，operation 只提供 accepted candidate 业务文本和 current input。

## 改动摘要

- `compact_payload.py` 新增 accepted candidate business text helper，供 post-compact budget 统一消费。
- `compaction.py` 为 `CompactMaterialPack` 增加 `previous_compacted_readable_view`，并校验 previous blocks / typed readable view exact invariant。
- `compact_material.py` 删除 previous view string round-trip、snapshot 重建和重复 candidate parser；latest accepted compact 一次生成 blocks + typed view pair；tier recovery 只通过 pair transform 同步过滤。
- `compact_pipeline.py` 的 source snapshot 携带并校验 typed pair；tier2/tier3 复用 pair transform。
- `run_input.py` 删除 direct compact artifact renderer 和 `compact.messages` 拼接；`CompactArtifactView` 改为 compact event ref + raw-tail provenance；ordinary build 增加 compact event ref / memory latest compaction ref 一致性矩阵。
- `context_budget.py` 新增 `POST_COMPACT_BASE_MESSAGE_COUNT = 2` 和 `estimate_post_compact_budget(...)`；`compaction_operation.py` 改为调用 context budget owner，diagnostics 不计预算。
- `llm_compaction.py` 原地删除三个 dead `_POST_COMPACT_*` 常量。
- README 更新：`dayu/host/README.md` 与 `tests/README.md` 同步当前 typed pair、ordinary single system envelope、budget owner 与测试覆盖边界。

## 测试与 coverage

已运行：

- focused S2 tests：`pytest tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py -q`，136 passed。
- affected tests：`pytest tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py tests/host/test_llm_compaction.py -q`，285 passed, 1 skipped。
- import / weak typing guards：`pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`，25 passed。
- full pyright：`pyright dayu tests utils`，0 errors。
- import smoke：`dayu.host`, `dayu.host.memory`, `dayu.host.compact_material`, `dayu.host.run_input` 导入通过。
- `git diff --check` 通过。

Coverage（同 affected tests + touched production modules）：

- `dayu/host/compact_material.py` 86%
- `dayu/host/compact_payload.py` 87%
- `dayu/host/compact_pipeline.py` 94%
- `dayu/host/compaction.py` 88%
- `dayu/host/compaction_operation.py` 94%
- `dayu/host/context_budget.py` 93%
- `dayu/host/llm_compaction.py` 90%
- `dayu/host/run_input.py` 88%

## Source scan

以下扫描在 `dayu/host` 与 S2 touched tests 上零匹配：

- `_compact_material_source_ref`
- `_previous_compacted_*_vnext`
- `_parse_previous_forward_intent_text`
- `_parse_previous_reference_continuity_text`
- `_previous_blocks_from_snapshot`
- `_snapshot_*_texts`
- `compact.messages`
- `_compact_artifact_message_content`
- `_vnext_compact_candidate_semantic_lines`
- `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`
- `_POST_COMPACT_BASE_MESSAGE_COUNT`
- `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT`
- old previous reference string-wire constants

`git diff -- dayu/host/tool_trace.py` 为空。

## README decision

- `dayu/host/` 生产代码变更命中 Host README 触发条件；已按 README 约束更新 `dayu/host/README.md`，只描述当前实现边界。
- `tests/` 变更命中 tests README 触发条件；已更新 P12.6 测试覆盖描述。
- 根 README、`dayu/README.md`、controller doc 不属于本次变更职责，未修改。

## Propagation audit

- 产生：`CONTEXT_COMPACTED` accepted candidate 是 compact semantic truth；typed parser 在 `compact_payload` 严格恢复 candidate。
- 持久化：EventLog payload / artifact digest 仍是 durable truth；candidate digest mismatch 或 schema/enum 错误 fail closed。
- material projection：`compact_material` 从 typed candidate 一次生成 prompt-local previous blocks 与 `CompactReadableViewVNext`，并在 `PreDispatchCompactMaterialView` / `CompactMaterialPack` / pipeline source snapshot 校验 exact pair。
- recovery：tier2/tier3 只传 retained labels 给 pair transform，同步过滤 blocks 与 typed view，不按字段各自重建。
- compactor input：`conversation_compact_input_vnext_from_material_pack` 直接使用 typed previous readable view，不再解析 previous block 字符串。
- memory：Conversation Memory 消费 accepted compact payload 并记录 latest compaction event ref。
- ordinary RunInput：RunInputBuilder 不渲染 compact artifact message；只校验 compact event ref 与 memory latest compaction ref。无 ref / ref 相等可继续；单边缺失或 mismatch 触发 repair / fail closed。
- budget：operation 从 accepted candidate 提取业务文本，交给 `context_budget.estimate_post_compact_budget(...)`；diagnostics 不进入预算。
- LLM-visible 输出：ordinary input 只有 memory、protected raw tail、continuity 和 current input envelope；不存在 duplicate compact renderer。

## Remaining risks

- 本次只做 P3-C S2；未进入 S3，未实现 accepted evidence typed LLM material / renderer / mismatch exception。
- 未修改 controller doc、未 commit / push / PR。
- 工作区已有未跟踪 `docs/cli_ci*` 与 `docs/reviews/code-review-20260710-*` 文件，按要求未触碰。
