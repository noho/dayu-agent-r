# WU-CM-12-FIX-R1 Slice 3 Validation Report

日期：2026-06-18

Agent：AgentCodex

当前 gate：implementation / Slice 3

## 1. 目标与裁决

Slice 3 目标是合并验证 Slice 1 与 Slice 2 已接受行为，并为 final closeout 常量审计准备证据。

第一性原理判断：本 Slice 的动机成立，但当前代码与测试已经覆盖要求的两个回归入口。继续新增测试会重复覆盖同一行为，增加维护成本，不提高缺陷发现能力。因此本轮不修改 production，不修改 tests，只新增本报告 artifact。

未进入 review gate，未修改 control doc，未 stage、commit、push 或打开 PR。

## 2. Focused Regression 覆盖核对

### 2.1 CompactionRequest 到 LLMContextCompactor.prepare_compactor_proposal_run_input

已由 `tests/host/test_llm_compaction.py::test_llm_context_compactor_prepares_same_source_runner_input` 覆盖。

关键断言：

- `_request_with_long_input_material()` 构造 `CompactionRequest`，包含长 current input：`"current " + ("input " * 300)`。
- 同一个 request 包含长 evidence response：`"evidence " + ("detail " * 700)`。
- 调用 `LLMContextCompactor.prepare_compactor_proposal_run_input(...)` 不抛错。
- prepared input 与真实 `AgentRunRequest` 同源：`prepared.message_count == len(request.messages) == 2`，roles 为 `("system", "user")`，`prepared.compaction_request_digest == compaction_request.digest()`。
- 从 compactor user prompt 解析出的 material JSON 保留全文：`current_anchor["text"] == "current " + ("input " * 300)`。
- evidence 保留单块 prompt-local label：`evidence_item["source_label"] == "E1"`。
- evidence response 保留全文：`evidence_item["response_text"] == "evidence " + ("detail " * 700)`。

补充相关覆盖：

- `tests/host/test_compact_material.py::test_current_input_anchor_keeps_whole_text_without_private_cap` 覆盖 pack 到 vNext input 的 current input 全文保留。
- `tests/host/test_compact_material.py::test_single_large_evidence_block_stays_whole_with_same_provenance` 覆盖超长 evidence 默认不 chunk，保留 `E1`、全文 digest、payload / artifact / source locator refs，且无 `E1.1` / `E1.2` 与 chunk metadata。
- `tests/host/test_compact_material.py::test_conversation_compact_input_vnext_maps_evidence_to_evidence_material` 覆盖 accepted evidence 进入 vNext `evidence_material`，`response_text` 不截断。

结论：不需要新增 duplicate focused regression。

### 2.2 RunInputBuilder accepted evidence provider 超过 8 个 evidence blocks

已由 `tests/host/test_run_input_builder.py::test_run_input_builder_accepted_tool_evidence_material_has_no_private_row_cap` 覆盖。

关键断言：

- 通过真实 store / transaction runner 写入 `count=10` 的 prior accepted tool evidence。
- 通过 `create_no_tool_run_input_builder(...).build_material_blocks(_attempt_snapshot(seeded))` 走真实 RunInputBuilder material provider 入口。
- `_accepted_tool_evidence_blocks(blocks)` 返回 10 个 evidence blocks。
- `accepted_evidence_id` 顺序与 seeded evidence 完全一致。
- 最后一条 evidence 的 `text` 等于完整 `canonical_json_dumps(seeded_evidence[-1].raw_outcome)`，证明不是 preview / ref / digest 替代。

补充相关覆盖：

- `tests/host/test_run_input_builder.py::test_run_input_builder_represented_refs_exclude_whole_accepted_evidence_blocks` 覆盖 memory / compact represented refs 仍 whole-block 排除。
- `tests/host/test_run_input_builder.py::test_run_input_builder_accepted_tool_evidence_uses_raw_outcome_text` 覆盖 raw outcome、readable tool name、readable query text、accepted evidence id、canonical refs、payload refs 与 tool call event ref。
- `tests/host/test_compact_material.py::test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap` 覆盖 EventLog-backed pre-dispatch compact material source builder 超过旧 8 条不 fail closed。

结论：不需要新增 duplicate focused regression。

## 3. 验证结果

### 3.1 Combined pytest

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py tests/host/test_memory_projection.py -q
```

结果：PASS，`240 passed in 1.03s`。

### 3.2 Pyright

命令：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：PASS，`0 errors, 0 warnings, 0 informations`。

备注：pyright 输出包含版本提示 `v1.1.409 -> v1.1.410`，不是类型错误。

### 3.3 Old symbol rg audit

命令：

```bash
rg -n "CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS|EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS|EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS|_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT|max_evidence_blocks|build_accepted_tool_evidence_material_blocks|_recent_accepted_tool_result_rows" dayu tests
```

结果：PASS，退出码 1，无输出。该命令的退出码 1 表示没有匹配，符合 Slice 3 预期。

### 3.4 git diff whitespace

命令：

```bash
git diff --check
```

结果：PASS，无输出。

新增 untracked 报告文件单独执行：

```bash
git diff --no-index --check /dev/null docs/reviews/wu-cm-12-fix-r1-s3-validation-codex-20260618.md
```

结果：PASS，无输出；退出码 1 是 no-index 对新增文件存在差异的预期状态，不表示 whitespace failure。

## 4. Preliminary Code Constant Audit

### 4.1 已删除 / 无残留的旧 guard 与旧入口

以下旧符号在 `dayu` 与 `tests` 中均无匹配：

- `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`
- `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS`
- `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS`
- `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`
- `max_evidence_blocks`
- `build_accepted_tool_evidence_material_blocks`
- `_recent_accepted_tool_result_rows`

分类：已删除。它们不再作为 EventLog-derived LLM-facing input material 的私有字段长度、默认 chunk 或 retrieval-count 合法性 guard。

### 4.2 保留为 parser safety guard 的 MAX_VNEXT 常量

`dayu/host/compaction.py` 保留以下 `MAX_VNEXT_*` 常量：

- `MAX_VNEXT_SESSION_SUMMARY_CHARS`
- `MAX_VNEXT_FACT_CLAIM_TEXT_CHARS`
- `MAX_VNEXT_ANSWER_ANCHOR_TEXT_CHARS`
- `MAX_VNEXT_FORWARD_INTENT_TEXT_CHARS`
- `MAX_VNEXT_REFERENCE_CONTINUITY_TEXT_CHARS`
- `MAX_VNEXT_DIAGNOSTIC_TEXT_CHARS`
- `MAX_VNEXT_SOURCE_LABELS_PER_ITEM`
- `MAX_VNEXT_FACT_ITEMS`
- `MAX_VNEXT_ANSWER_ANCHOR_ITEMS`
- `MAX_VNEXT_FORWARD_INTENT_ITEMS`
- `MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS`
- `MAX_VNEXT_DIAGNOSTIC_ITEMS`

分类：保留为 parser safety guard / output accept barrier。

依据：这些常量用于校验 LLM-generated compact output candidate 的文本长度、source label 数量和 candidate item 数量。它们不用于拒绝 EventLog-derived compact input material，不是 current input / evidence material 的输入预算真源。

### 4.3 仍由 memory_projection_policy 管理的 LLM-facing production caps

`dayu/host/memory.py::MemoryProjectionPolicy` 的字段与 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 对齐，覆盖：

- selected recent window item / char cap / turn floor
- fallback selected recent window item / char cap
- evidence fact item / char cap / floor
- session summary char cap
- answer anchor item / char cap
- forward intent item / char cap
- reference continuity item / char cap / floor
- inline delta lag / repair event limits

`dayu/host/memory.py` 中的 `DEFAULT_MEMORY_*` / `DEFAULT_*_CAP` 常量仍存在，但它们是 `default_memory_projection_policy(...)` 的 typed fallback defaults，字段均投影为 `MemoryProjectionPolicy`，且对应字段在 `execution_profiles.json` 的 `memory_projection_policy` 中定义。它们不是新增的第二套 compact material 私有 guard；final closeout 可继续标记为“policy-field code fallback defaults”，并确认 packaged assembly 以 execution profile 为真源。

### 4.4 未发现的剩余 LLM-facing compact material 私有产量常量

本轮审计未发现 Slice 1 / Slice 2 修复范围内仍有未归属 `memory_projection_policy` 的 LLM-facing memory 或 compact material production constants。

保留但不属于该类的常量示例：

- `dayu/host/compact_material.py` 中的 prompt-local label 前缀、ordinal、section reason code、payload field name：属于 label / provenance / schema 字段或诊断 reason，不是产量预算。
- `dayu/host/run_input.py` 中的 system envelope section title、projector id、manifest id prefix：属于 renderer / manifest / projection 元数据，不是 memory / compact material 产量 cap。
- `dayu/host/compaction_operation.py::_MAX_SAFE_EXCEPTION_MESSAGE_CHARS`：属于异常诊断文本安全裁剪，不是 EventLog-derived LLM-facing memory / compact material production cap。
- `dayu/host/context_policy.py` 的 context threshold / compaction attempt defaults：属于 Context Governance budget / retry policy，不属于 `memory_projection_policy` 管辖的 LLM-facing memory / compact material 产量常量。

## 5. README / Docs

本轮只新增 `docs/reviews/` 下的 Slice 3 validation artifact。未修改 `dayu/host/`、`tests/`、用户可见 CLI / Web / 安装 / 入口 / 日志 / 工作区路径，也未改变分层关系或 public contract。因此不触发 README 更新。

未修改 `docs/host/issues-implementation-control.md`。

## 6. 风险与未覆盖项

未发现需要在 Slice 3 修改代码的真实行为缺口。

剩余风险：

- 本报告是 preliminary constant audit prep，不替代 final closeout 的最终控制文档 reconciliation。
- `default_memory_projection_policy(...)` 的代码 fallback defaults 与 packaged `execution_profiles.json` 的具体数值不同，但字段同源于 `MemoryProjectionPolicy`。若 final closeout 要求消除所有 fallback default values，需要另行裁决，因为这超出 Slice 3 的允许改动范围。
