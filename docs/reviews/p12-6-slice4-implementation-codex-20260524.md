# P12.6 Slice 4 Implementation Artifact

## 动机判断

Slice 4 动机成立。`docs/host/design.md` §24 / §25 明确要求 LLM-facing compact input 只能是去重后的 material pack 与 prompt-local labels，accepted evidence envelope、payload digest、event id、cursor、policy snapshot 等 Host ledger 字段只能留在 Host 内部 provenance / audit mapping 中。现有 Slice 1-3 已提供 material pack、provenance map 与 evidence map，本 Slice 收紧 prompt rendering、JSON parser 与 accept barrier 是消除 LLM 越权引用 Host canonical refs 的必要步骤。

## 改动文件

- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`

未修改 `docs/host/implementation-control.md`。

## 实现摘要

- `_compaction_request_prompt_block(...)` 改为只渲染 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor` 四个 LLM-facing material pack section，不再输出 `trigger_source` / `material_pack` 包装，也不读取 EventLog 或 envelope helper。
- LLM prompt 文案改为要求 fact candidate 引用 prompt-local evidence labels，并新增 `preservation_evidence` 输出 schema；schema 不要求 LLM 输出 canonical Host refs。
- parser 对 fact、minimum preserve、preserved labels、ranges 与 preservation evidence 统一先校验 prompt-local label section，再映射到 canonical refs 后构造 `CompactionCandidate`。
- parser 对未知 label、cross-section label、空 fact evidence labels、非 material source label fail closed。
- quality checker 增加 summary 直接把 prompt-local evidence label 升级为 confirmed fact ref 的拒绝防线。
- 测试覆盖指定用例：prompt 不倾倒 ledger、accepted evidence envelope metadata 不渲染、prompt-local evidence label 映射、未知 / 跨 section label 拒绝、fact 无 evidence label 拒绝、minimum preserve source label 边界。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q`
  - 结果：49 passed
- `source .venv/bin/activate && python -m pyright dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/compaction.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：pass
- prompt asset forbidden ledger key 搜索：
  - 结果：无 `accepted_evidence_envelopes:`、`compact_raw_context:`、`input_event_refs:`、payload digest/ref、event id、cursor、policy snapshot 等命中。

## README 决策

触发检查范围：`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`。本 Slice 只收紧内部 compactor parser、prompt asset schema 与测试覆盖；现有 README 已在职责范围内描述 Host compactor、prompt asset 职责与 P12.6 prompt-local label 测试覆盖，没有用户命令、公共入口、配置 schema 或测试分层变化，因此无需更新 README。

## 风险与未覆盖项

- 未覆盖真实 provider 对新 `preservation_evidence` schema 的遵循度；该风险归后续 compactor smoke / Slice 5 governance 接线观察。
- 本 Slice 不实现 proactive / reactive durable compaction operation 接线与 multi-pass merge，按计划归 Slice 5。
- `docs/host/implementation-control.md` 当前工作区已有未归属修改，本次只读未处理。

## 完成状态

Slice 4 implementation 完成；未 commit、未 push。
