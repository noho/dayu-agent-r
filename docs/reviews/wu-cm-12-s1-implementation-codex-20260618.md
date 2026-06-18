# WU-CM-12 S1 Implementation Artifact

## Gate

- Work unit：WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Gate：implementation
- Slice：S1 Material Block And Policy Owner Convergence
- 实施者：Codex
- 日期：2026-06-18

## 变更文件

- `dayu/host/compact_material.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`

## 直接证据

- `RunInputMaterialBlock` 原先不携带 `turn_group_id`，而设计第 24 章要求 material block 携带 turn group 数据，供共享 selected recent window 语义使用。
- `compact_material.py` 原先使用 `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` 和 truncation marker 截断 LLM-facing current input anchor。
- `memory.py` 原先使用 `_bounded_text(...)` 处理 compact-derived `summary_text` 与 fact `claim_text`，会返回静默前缀文本。
- Evidence chunking 已有 chunk label 与 provenance entry；本次测试补充断言 chunk label、parent label、canonical source refs 与 payload refs 同时存在。

## 实施决策

- 为 `RunInputMaterialBlock` 与 `run_input_material_block(...)` 增加 `turn_group_id: str | None`。
- pre-dispatch user input、assistant final answer 与 accepted tool evidence delta block 从 EventLog row `run_id` 填充 `turn_group_id`。
- ordinary current input material block 从 `CurrentRunFacts.run.run_id` 填充 `turn_group_id`。
- ordinary accepted tool evidence material block 从来源 `TOOL_RESULT_ACCEPTED` row 的 run id 填充 `turn_group_id`。
- stable previous compacted semantic block 保持 `turn_group_id=None`，因为 compact event row 不能证明每个 semantic item 的原始 source Run。
- 移除 current input 私有 cap 与 truncation marker。Current input anchor 现在保留完整 normalized text，keep/drop/fail-closed 留给 context governance。
- 删除 `_bounded_text`。compact-derived oversized session summary 与 evidence fact 现在整体丢弃并记录 `BUDGET_LIMIT_REACHED` diagnostic，不再返回前缀文本。

## 测试与验证

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
  - 结果：`117 passed in 0.92s`
- `source .venv/bin/activate && pyright dayu/host/compact_material.py dayu/host/memory.py dayu/host/run_input.py tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## README 判断

- `dayu/host/README.md` 不需要更新。本 slice 改的是 Host 内部 material block 字段与 LLM-facing material 生产行为，不改变 Host public API、稳定开发接口、状态机或已文档化扩展点。
- `tests/README.md` 不需要更新。新增测试只是扩展既有 Host Conversation Memory / compact material / RunInputBuilder 覆盖，不引入新的测试层级、命令、marker、fixture 分类或维护规则。

## 残余风险

- S1 只携带 `turn_group_id`，不实现 S2 的 turn-group selector / fallback cap 算法。
- ordinary `build_run_input_material_blocks(...)` 中既有 `continuity.messages` material 仍没有 row-level run provenance，因为该 provider contract 只暴露 `AgentMessage`；本 slice 没有伪造 run id。
- ordinary RunInput compact artifact 路径中 accepted compact summary 的 lossy rendering 不在 S1 范围，按 accepted plan 留给后续 slice。

## Stop Condition 状态

- Stop condition 未触发。无需修改 accepted compact output schema、durable EventLog payload schema、public API、Engine contract 或范围外生产模块。
- Slice S1 implementation 与验证已完成。未 commit、push、创建 PR、merge，也未进入 code review gate。
