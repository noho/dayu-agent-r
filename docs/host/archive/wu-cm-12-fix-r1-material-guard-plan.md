# WU-CM-12-FIX-R1 EventLog Material Guard Repair Plan

## 1. 目标 / 动机 / 成功信号

目标：修复 WU-CM-12 中仍残留的 EventLog-derived LLM-facing input material 过度合法性 guard。当前输入、历史对话材料、accepted tool evidence 只要来自可校验 EventLog / payload / artifact，就默认是合法 LLM input material；Host 不得仅因私有 DTO 字段长度、默认 chunk 字符数或私有 row limit 超限而拒绝它们。

第一性原理判断：动机成立，且严重性没有被高估。Context window 治理应回答“当前可发送多少材料”，DTO 私有字段 cap 只能回答“字段结构是否可读”。把 EventLog 已接受材料因为 `CurrentInputAnchorVNext.text`、`EvidenceReadableItemVNext.response_text` 或 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` 拒绝，会把 Host durable truth 误判成非法输入，违反 `LLM in the loop` 下 Host 对事实边界的职责。

成功信号：

- compact input DTO 不再以私有字段长度拒绝 EventLog-derived input material。
- 默认 evidence material 不再因为 4096 字符常量被切成 chunks；若未来需要 chunk，只能由显式预算/selection 决策触发，并保留 canonical provenance。
- ordinary / fallback accepted tool evidence 读取不再受 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 限制；缩小只发生在 selection / floor / context budget / fallback / fail-closed 语义中。
- 不新增 public API、durable schema、EventLog canonical semantics 或 Engine provider contract。
- affected tests、pyright、`git diff --check` 通过；final closeout 输出控制文档要求的常量审计清单。

## 2. 设计对齐

设计真源是 `docs/host/design.md` 和 `docs/engine/design.md`。

- `docs/host/design.md` 24.6 规定 ordinary path 不做字段级 runtime silent truncation；section 上限、selected recent window cap、floor 与 working set 是 projection / assembly 前的确定性治理。
- `docs/host/design.md` 25 规定 Context Governance 是 Host 责任；Engine 不做 Host-side compact retry / budget / policy。
- `docs/host/design.md` 25 中 compact material selection 的关键约束是：缩小时只能 whole-block keep-drop、section-aware keep-drop、chunking with provenance 或 fail closed，不能用字段级 silent truncation 或 lossy preview 冒充完整材料。
- `docs/host/design.md` 25 规定 `current_input_anchor` 来自当前 `USER_INPUT_ACCEPTED`，必须保留为最终用户输入保护锚点，不得吞掉或重复渲染。
- `docs/host/design.md` 25 规定 EventLog / payload / artifact source refs 与 digest 损坏时应按 compaction failure / pre-dispatch failure 收口；这是真正 fail-closed 条件，不是字段 cap 条件。
- `docs/engine/design.md` 15 明确 Engine 只表达 provider context overflow 可恢复事实；如何压缩、重构消息、重新 dispatch 都属于 Engine 外部 Host 职责。
- `docs/host/issues-implementation-control.md` 的 `WU-CM-12-FIX-R1` 行明确要求移除、放松或替换 compact input DTO field-length guards、`CurrentInputAnchorVNext.text`、`EvidenceReadableItemVNext.response_text`、default evidence chunking 和 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`。
- 同一控制文档要求 final closeout 输出代码常量审计清单：列出仍存在且未由 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 定义的 LLM-facing memory / compact material 产量常量，并标注“已删除 / 已迁入 policy / 保留但非 LLM-facing / 保留为 parser safety guard / deferred-with-owner”。

## 3. 直接代码证据

- `dayu/host/compaction.py:645` 的 `CurrentInputAnchorVNext` 在 `__post_init__` 中调用 `_require_bounded_non_empty_text(... max_chars=CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS)`；常量在 `dayu/host/compaction.py:680`，当前值 1200。这会让长 current input 在 DTO 层被判非法。
- `dayu/host/compaction.py:1029` 的 `EvidenceReadableItemVNext` 在 `__post_init__` 中调用 `_require_bounded_non_empty_text(... max_chars=EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS)`；常量在 `dayu/host/compaction.py:1078`，当前值 4096。
- `dayu/host/compact_material.py:89` 定义 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096`；`_pack_evidence_blocks` 在 `dayu/host/compact_material.py:2836` 默认调用 `_evidence_chunks`，`_evidence_chunks` 在 `dayu/host/compact_material.py:2937` 按该常量切分所有超长 evidence。
- `dayu/host/compact_material.py:601` 的 `conversation_compact_input_vnext_from_material_pack` 把 material pack 映射为 `ConversationCompactInputVNext`，因此上述 DTO cap 是 compactor proposal 前的真实失败入口。
- `dayu/host/run_input.py:232` 定义 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8`；`DurableAcceptedToolEvidenceMaterialProvider.__init__` 在 `dayu/host/run_input.py:1332` 默认使用该常量；`build_accepted_tool_evidence_material_blocks` 在 `dayu/host/run_input.py:1407` 继续把它传给 `_recent_accepted_tool_result_rows`；SQL 在 `dayu/host/run_input.py:3306` 使用 `LIMIT ?`。
- `dayu/host/compact_material.py:477` 的 `build_pre_dispatch_compact_material_view` 已经从 EventLog durable truth 构造 pre-dispatch material view，docstring 明确“不在 source builder 阶段用固定条数裁剪 post-compact delta 或 accepted evidence blocks”。这应成为修复 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` 的同源入口。
- `dayu/host/context_fallback.py:410` 的 proactive fallback material rebuild 已经复用 `build_pre_dispatch_compact_material_view`，说明无需发明第二套 retrieval-volume truth。
- `dayu/config/execution_profiles.json:26` 的 `memory_projection_policy` 已包含 selected recent window、fallback selected recent window、floor 与 semantic section caps；本修复不应新增第二套 material budget truth。
- `tests/host/test_compact_material.py:1192` 已有 current input 不按私有 cap 截断的 pack 层测试，但还缺少 `ConversationCompactInputVNext` DTO 转换层回归。
- `tests/host/test_compact_material.py:1350` 已证明 pre-dispatch source builder 能保留超过旧 8 条 evidence，但 ordinary `DurableAcceptedToolEvidenceMaterialProvider` 仍有私有 row limit，测试没有覆盖真实 provider 入口。

用户给定的 `dayu/host/memory_projection.py` 在当前仓库不存在；相关 production owner 是 `dayu/host/memory.py` 与 `dayu/host/durable/memory.py`。本修复不需要新增 `memory_projection.py`。

## 4. Scope / Non-goals

允许范围：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/run_input.py`
- 直接受影响 tests：`tests/host/test_compact_material.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_memory_projection.py`
- 如需更新常量审计或说明，implementation / final closeout artifact 放在 `docs/reviews/`，但本 plan gate 不修改控制文档。

非目标：

- 不实现 WU-CM-13 reactive compact recovery tier 1-3。
- 不修改 public API、durable schema、EventLog canonical semantics、Engine provider contract。
- 不新增 summary、preview、字段级 truncation 或第二套 material budget。
- 不把 tool truncation policy、UI/log diagnostic 截断规则混入 LLM-facing material 预算。
- 不改 `docs/host/design.md`、`docs/engine/design.md` 或 `docs/host/issues-implementation-control.md`。
- 不为旧接口、旧测试或旧行为保留兼容 wrapper。

## 5. 实施决策

1. compact input DTO 只校验结构，不拥有 EventLog material 长度合法性。
   - 对 `ConversationCompactInputVNext` 的输入材料字段，字段值应校验为非空文本、enum 合法、tuple 类型合法、label 唯一、current input 不可引用。
   - 不再用 `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS` 或 `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS` 判断 input material 是否非法。
   - `ConversationCompactOutputVNext` 及其 LLM-generated candidate 的 `MAX_VNEXT_*` parser safety guards 保留；这些是 output accept barrier，不是 EventLog-derived input material legality guard。

2. default evidence chunking 移除。
   - 默认 material pack 中，一个 accepted evidence block 对应一个 prompt-local label，例如 `E1`。
   - 删除或停用 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 驱动的默认 `_evidence_chunks` 调用。
   - 本 WU 不保留无生产调用方的显式 budget chunk helper。默认 chunking 移除后，如果 `_evidence_chunks`、`_EvidenceChunk`、`evidence_chunk_label` 与 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 没有生产调用方，必须一并删除；不得为未来可能的 budget chunking 留 dead code。
   - 未来如需显式 budget chunking，必须由后续 WU / design owner 重新设计，明确预算来源、触发条件、`chunk_parent_label` / `chunk_ordinal` / canonical evidence provenance 语义。
   - 大 evidence 仍然是合法 input material。若 selected material 超过 hard context budget，Context Governance 走既有 compact failure / dispatch fallback / fail-closed；不得回退到字段级切片。

3. accepted tool evidence row limit 移除。
   - 删除 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`、`max_evidence_blocks` 默认参数和 `_recent_accepted_tool_result_rows(... LIMIT ?)` 作为 material legality / retrieval-volume guard 的角色。
   - `DurableAcceptedToolEvidenceMaterialProvider` 改为复用 `build_pre_dispatch_compact_material_view(...)`，并以该 EventLog-backed material view 作为 accepted evidence material 的权威来源；删除旧 direct-SQL material builder 后，不要求为了对比新旧结果而保留旧路径。
   - provider 的精确映射为：在读 transaction 中调用 `build_pre_dispatch_compact_material_view(transaction, event_log_store, run=current_facts.run, current_display_text=current_facts.user_prompt)`；`current_display_text` 必须来自 `current_facts.user_prompt`。
   - 从返回 view 的 `material_blocks` 中只选择 `kind == CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE` 的 whole blocks。
   - 再计算 `represented_refs = _represented_evidence_refs(memory, compact)`，把 represented refs 作为第二道 whole-block filter 应用到上述 accepted evidence blocks，防止 memory / compact 已代表的 evidence 重复进入 material。
   - 不新增“最多读 N 条 evidence”的私有常量。如果需要 transaction/page 粒度优化，必须是 page size，不得改变 correctness 或材料合法性；本修复不要求新增 page helper。

4. fail-closed 条件收窄到设计批准场景。
   - current input 本身超过 hard budget、EventLog/payload/artifact 损坏、source boundary/provenance 不一致、cancellation/session/run state 不允许继续，才是 hard stop。
   - “字段超过 1200/4096”或“第 9 条 accepted evidence”不是 hard stop。

5. 不扩大架构。
   - 不新增 policy schema 字段。
   - 不新增 Host / Service seam。
   - 不把 Context Governance 改成 memory projection owner。

## 6. Slices

### Slice 1: Compact Input DTO Guards And Default Evidence Chunking

目标：消除 compact input DTO 对 EventLog-derived input material 的私有字段长度拒绝，并移除默认 evidence chunking。

允许文件：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_llm_compaction.py`

具体改动：

- 在 `CurrentInputAnchorVNext.__post_init__` 中把 bounded check 改为 non-empty check，删除 `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`。
- 在 `EvidenceReadableItemVNext.__post_init__` 中把 `response_text` bounded check 改为 non-empty check，删除 `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS`。
- 审计 `ConversationCompactInputVNext` 下所有 input material DTO：如果 bounded check 只保护 EventLog-derived input material，改为 non-empty / type / enum / label check；如果 check 属于 LLM-generated output candidate，保留。
- 修改 `_pack_evidence_blocks` 和 `_provenance_from_evidence_blocks`，默认不调用 `_evidence_chunks`，一个 source evidence block 输出一个 `CompactEvidenceBlock` 和一个 provenance entry。
- 删除 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 的默认产量角色。
- 默认 chunking 移除后，如果 `_evidence_chunks`、`_EvidenceChunk`、`evidence_chunk_label` 与 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 没有生产调用方，必须删除，不得重命名后保留为未接入的显式 budget chunk helper。
- 保留 `validate_material_label` 对 `E1.1` 形式的解析能力可以接受，但它不能作为默认 chunking 的证据；相关 chunk helper 与测试如果没有生产调用必须删除。

测试要求：

- 新增/更新测试：长 current input 经 `build_compact_material_pack` 后再调用 `conversation_compact_input_vnext_from_material_pack`，完整进入 `CurrentInputAnchorVNext.text`，不抛错，不截断。
- 新增/更新测试：超过 4096 字符的 accepted evidence 经 material pack 和 vNext input 后仍是单个 `E1` evidence item，`response_text` 完整，不生成默认 `E1.1` / `E1.2`。
- 更新原 `test_single_large_evidence_block_is_chunked_under_same_provenance` 为“默认不 chunk”的迁移断言，不再测试显式 budget chunk helper。最小断言必须包含：单个 `E1` label、`raw_result_text` / vNext `response_text` 保持全文、`content_digest` 基于全文、payload / provenance refs 保留、没有 `E1.1` / `E1.2` label、没有 `chunk_parent_label` / `chunk_ordinal` 语义残留。
- `test_llm_context_compactor_prepares_same_source_runner_input` 应覆盖长 current/evidence 不在 prepare 阶段失败。

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py -q
pyright dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py
```

停止条件：

- 如果删除 DTO input caps 需要修改 public schema version 或 Engine message contract，停止并返回 plan gate。

### Slice 2: Accepted Tool Evidence Provider Limit Removal

目标：移除 ordinary / fallback material source 中 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` 对 accepted evidence 的私有 row 数限制。

允许文件：

- `dayu/host/run_input.py`
- `tests/host/test_run_input_builder.py`
- 必要时只读/轻微测试联动 `tests/host/test_compact_material.py`

具体改动：

- 删除 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`。
- 删除 `DurableAcceptedToolEvidenceMaterialProvider.__init__(..., max_evidence_blocks=...)` 的参数和字段；如果测试 helper 传入该参数，更新测试，不加兼容参数。
- 删除 `build_accepted_tool_evidence_material_blocks(..., max_evidence_blocks=...)` 参数；如果函数只剩薄封装且不再提供有效语义，优先删除，或改为 EventLog delta truth helper。
- 删除 `_recent_accepted_tool_result_rows(..., limit)` 的 `LIMIT ?` 查询路径。
- 在 provider 读 transaction 中调用 `build_pre_dispatch_compact_material_view(transaction, event_log_store, run=current_facts.run, current_display_text=current_facts.user_prompt)`，其中 `current_display_text` 必须来自 `current_facts.user_prompt`。
- 只从返回 view 的 `material_blocks` 中选取 `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE` whole blocks；随后计算 `_represented_evidence_refs(memory, compact)`，并把这些 refs 作为第二道 whole-block filter 排除已代表 evidence。
- 新的 EventLog-backed material view 是 accepted evidence material 的权威路径；删除旧 direct-SQL builder 后，不为新旧字段对比保留旧路径。
- 保持 raw outcome 读取、digest 校验、result_preview 拒绝、payload/artifact provenance 规则同 `compact_material.py` source builder 一致，不在 `run_input.py` 重新解释工具结果结构。
- 如果 `current_facts.user_prompt` 与 EventLog `display_text` 不一致，沿用 `build_pre_dispatch_compact_material_view` 的 durable mismatch fail-closed。

测试要求：

- 新增/更新真实 provider 入口测试：写入 10 条以上 `TOOL_RESULT_ACCEPTED`，通过 `DurableAcceptedToolEvidenceMaterialProvider` 或 `RunInputBuilder.build_material_blocks(...)` 读取，断言超过 8 条都可进入 material block 候选。
- 测试 represented evidence refs 仍 whole-block 排除，不能重复进入 material。
- 测试 provider 读取 raw outcome，不读取 preview / ref / digest 作为 LLM-facing text。
- 测试 key fields 存在且语义来源正确：`text` / `raw_result_text` 来自完整 raw outcome，`readable_tool_name` 来自工具调用可读名称，`readable_query_text` 来自工具调用 query / arguments 的业务可读文本，`accepted_evidence_id` 来自 accepted evidence canonical id，`canonical_source_refs` / provenance refs 保留 payload / artifact / event refs，represented refs 命中的 evidence 被 whole-block 排除。
- 测试 `rg` 不再出现 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`。

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q
pyright dayu/host/run_input.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py
```

停止条件：

- 如果实施证明必须新增 durable index/table/schema 或 public policy 字段才能移除 row limit，停止并返回用户裁决。

### Slice 3: Focused Regression, Constant Audit Prep, Full Validation

目标：把两个修复入口合并验证，并为 final closeout 常量审计准备可执行检查。

允许文件：

- `tests/host/test_compact_material.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py` 仅当现有断言受 DTO/input-material cap 语义影响
- implementation report artifact under `docs/reviews/`

具体改动：

- 加一个 focused regression，覆盖 `CompactionRequest -> LLMContextCompactor.prepare_compactor_proposal_run_input(...)`，输入含长 current input、长 evidence response、超过 8 条 accepted evidence 候选时不因私有 guard 抛错。
- 加常量审计命令到 implementation report，不在 plan gate 修改控制文档。
- 审计范围至少包含：
  - `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`
  - `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS`
  - `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS`
  - `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`
  - 任何新增的 LLM-facing memory / compact material 产量常量
- 对仍保留的 `MAX_VNEXT_*` output candidate/parser safety constants 明确分类为“保留为 parser safety guard”，不能误标为 input material budget。

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
python -m pyright dayu/ tests/ utils/
rg -n "CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS|EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS|EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS|_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT" dayu tests
git diff --check
```

预期 `rg` 结果：四个旧常量不应在 production code 中出现。`EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 不得通过重命名方式作为显式 budget chunk helper 继续保留；本 WU 不批准新增该 policy 字段或 dead helper。

## 7. README / Docs 决策

本 plan gate 只新增 `docs/host/host-issues/wu-cm-12-fix-r1-material-guard-plan.md`，不触发 README 更新。

implementation gate 若只修改 `dayu/host/` 和 `tests/host/`，必须按 AGENTS.md 检查：

- 读取 `dayu/host/README.md` 的 Agent 更新约束，再判断是否需要更新。
- 读取 `tests/README.md` 的 Agent 更新约束，再判断是否需要更新。
- 当前预期：不改变用户可见 CLI/Web/安装/入口/日志/工作区路径，不需要根 README。
- 当前预期：不改变 Host/Engine/Public API 分层说明，不需要 `dayu/README.md`。

## 8. 风险 / Open Questions

- 风险：移除 default evidence chunking 后，单条超长 evidence 可能让 compactor input 超预算。裁决：这是 Context Governance budget / fallback / fail-closed 的职责，不是 DTO 字段合法性职责；本 WU 不实现 WU-CM-13 reactive multi-pass chunking。
- 风险：移除 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT` 后，EventLog delta 很大时 material view 构造成本上升。裁决：这是 non-blocking residual；当前已有 `build_pre_dispatch_compact_material_view` 作为 EventLog truth source，本 WU 不为性能风险重引入私有 row limit 或 page correctness cap。若真实长 session evidence scan 成本被观测到，deferred-with-owner 到未来 Host material source performance hardening WU；WU-CM-13 是 reactive compact recovery owner，不是该性能 hardening owner。
- 风险：旧测试可能把 4096 chunking 当成正确行为。裁决：测试必须迁移到设计语义，不能为了保旧测试继续默认 chunk。
- Open question：无 blocking open question。若实现中发现必须改 public schema / durable schema / Engine contract，立即停止。

## 9. 为什么这不是过度设计

- 修复删除私有 guard，并复用现有 `build_pre_dispatch_compact_material_view`、selection、budget、fallback 语义；没有新增 memory framework。
- 不新增 policy 字段，不新增 service callback/factory，不新增 public API。
- 不把大材料“智能摘要”或 preview 化；只恢复 Host durable truth 与 Context Governance 的职责分离。
- 常量审计不是新功能，是控制文档已明确要求的 final closeout gate 条件。

## 10. Completion Report Format

implementation agent 完成后报告必须使用以下格式：

```text
WU-CM-12-FIX-R1 implementation report

改动：
- ...

关键裁决：
- ...

测试：
- command -> result
- pyright -> result
- git diff --check -> result
- constant audit rg -> result

README/docs：
- ...

Residual risk：
- none / ...

未做：
- 未实现 WU-CM-13 reactive compact recovery
- 未修改 public API / durable schema / EventLog canonical semantics / Engine provider contract
```

final closeout 必须额外输出常量审计表，列名固定为：

```text
| constant | location | status | reason |
|---|---|---|---|
```

允许 status 只有：`已删除`、`已迁入 policy`、`保留但非 LLM-facing`、`保留为 parser safety guard`、`deferred-with-owner`。

## 11. Plan Gate Validation

本 plan gate 只允许写本 artifact。完成后运行：

```bash
git diff --check
```

不得 commit、push、open PR、修改 control doc，且不得进入 implementation / review gate。
