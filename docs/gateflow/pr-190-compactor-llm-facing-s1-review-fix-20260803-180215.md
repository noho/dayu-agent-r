# PR 190 Compactor LLM-facing S1 code review fix

## Gate metadata

- Gate: `code review -> fix`
- Work unit: 修复 PR 190 的 Compactor LLM-facing prompt findings F01-F02
- Approved slice: `S1 — Prompt trust boundary and self-contained contract`
- Branch: `codex/interactive-oracle`
- Completion status: `fix-complete`
- Commit status: 未提交
- Re-review status: 未执行
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-s1-review-fix-20260803-180215.md`
- Updated implementation artifact: `docs/gateflow/pr-190-compactor-llm-facing-s1-implementation-20260803.md`
- Next Gateflow entry point: `re-review`

## Scope

本 gate 只修复 S1 code review findings。没有修改 renderer、parser、Context Governance、Memory、frozen schema、publication hash、README 或其它 slice；没有提交，也没有进入 re-review。

允许且实际修改的四个 S1 文件：

- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_public_compact_smoke.py`

本 gate 同时更新两个 gate artifacts：

- `docs/gateflow/pr-190-compactor-llm-facing-s1-implementation-20260803.md`
- `docs/gateflow/pr-190-compactor-llm-facing-s1-review-fix-20260803-180215.md`

两份 review artifact 保留原文，未修改：

- `docs/reviews/pr-190-s1-code-review-mimo-20260803-175642.md`，SHA-256 `9322eeaca0e81d8c12b0811c7b4f27e59e47ea36e8b5c516e9164cae7356613c`
- `docs/reviews/pr-190-s1-code-review-ds-20260803-175751.md`，SHA-256 `5b5b87b2ef0b8e86c254a435a4b128038479cbd9f976daf613624cbca0f9d1e3`

## Finding decisions and fixes

### MiMo S1-01 — repair marker 与当前 renderer mismatch

- Review source: `docs/reviews/pr-190-s1-code-review-mimo-20260803-175642.md`
- Decision: `accepted`
- Fix status: `已修复`
- Direct evidence: `_user_prompt_vnext` 当前仍用 `PREVIOUS_VALIDATION_REPORT_JSON` 追加脱敏反馈 JSON；S1 是独立 checkpoint，不能让 prompt 承诺当前 renderer 不会产生的 marker/projector schema。
- Fix: 两份 prompt 撤回 `REPAIR_FEEDBACK_JSON_BEGIN/END`、`required_action/issues` exact schema 的未来承诺，改为 generic 自足语义：若请求末尾含前一次完整 candidate 的脱敏校验反馈，按其中的问题和直接修复动作，从同一输入完整重产 JSON，不复制、拼接、补写或复用旧输出。
- Test decision: `test_prompt_assets_are_self_contained_for_fresh_v2_contract` 不再断言未来 repair marker/schema，改为断言 generic whole-candidate contract；`test_repair_feedback_is_separate_and_requires_whole_candidate` 保持对当前 renderer、脱敏、反馈上限和 whole-candidate 语义的验证。
- Boundary decision: 不修改 renderer。S2 原子落地 marker、唯一 projector、prompt 与对应测试。

### DS Finding 1 — repair 路径 staged checkpoint 断裂

- Review source: `docs/reviews/pr-190-s1-code-review-ds-20260803-175751.md`
- Decision: `accepted`
- Fix status: `已修复`
- Direct evidence: 与 MiMo S1-01 指向同一 root cause，即 prompt 对 repair transport/schema 的承诺领先于 renderer owner。
- Fix: 复用 MiMo S1-01 的同一 owner-boundary 修复，不增加临时 marker 兼容说明，不在 renderer 下游补偿。
- Residual: S2 的 marker/projector/prompt 原子变更仍由 later approved slice 拥有；当前 S1 checkpoint 已无 contract mismatch。

### MiMo S1-02 — forbidden terms 使用宽泛英文子串

- Review source: `docs/reviews/pr-190-s1-code-review-mimo-20260803-175642.md`
- Decision: `accepted`
- Fix status: `已修复`
- Direct evidence: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 以 substring 检查 `Host`、`Memory`、`Attempt`、`Python`、`dataclass`、`StrEnum`，会把合法业务英文当作内部实现泄漏。
- Fix: 删除上述宽泛子串，保留既有 `Host-owned context compaction`、`CompactValidationReportV2`、`CompactRepairFeedbackV2` 和其它 typed/internal names；新增当前 repair 路径相关的精确内部术语 `CompactValidationIssueV2`、`previous_attempt_number`、`additional_issue_count`、`Memory policy`。
- Test decision: 继续以真实 production prompt assets 验证精确内部术语不进入 LLM-facing 文本，避免合法业务英文误报。

## Changed files

- `dayu/config/prompts/scenes/conversation_compaction.md`：repair 规则改为 generic whole-candidate 语义。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`：撤回未来 marker/exact schema，保留自足的问题、直接修复动作和完整重产规则。
- `tests/host/test_llm_compaction.py`：repair contract 断言改为当前 S1 generic 语义，不断言 S2 marker/schema。
- `tests/host/test_public_compact_smoke.py`：forbidden terms 从宽泛英文子串收窄为精确内部术语。
- `docs/gateflow/pr-190-compactor-llm-facing-s1-implementation-20260803.md`：回写 fix gate 状态、裁决、验证和 residual。
- `docs/gateflow/pr-190-compactor-llm-facing-s1-review-fix-20260803-180215.md`：新增本 durable fix artifact。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q`
  - 结果：`24 passed in 0.35s`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -k 'default_compactor_prompt or prompt_contract or prompt_example or adversarial'`
  - 结果：`1 passed, 23 deselected in 0.38s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无 whitespace error。

## Docs decision

本 gate 不更新 README。当前授权严格限定四个 S1 文件和两个 gate artifacts；config/tests README 的稳定职责说明仍由 approved S4 拥有。两份 code review artifact 作为原始审查证据保留，不回写 finding 状态。

## Residual risks and uncovered areas

- `fixed in current slice` — prompt/renderer repair marker/schema mismatch 已消除：S1 只承诺当前 renderer 可满足的 generic whole-candidate 语义。
- `fixed in current slice` — forbidden-term 宽泛英文误报风险已通过精确内部术语替换消除。
- `covered by later approved slice` — S2 原子落地 repair marker、唯一 LLM-facing projector、prompt 和对应测试，不把中间断裂态作为 checkpoint。
- `covered by later approved slice` — S3 real-provider observation 验证真实模型是否抵抗 current/trace/evidence/answer 注入。
- `covered by later approved slice` — S3 同步两个 prompt asset 的 frozen publication hash。
- `covered by later approved slice` — S4 裁决并更新 config/tests README 与 Host design 的稳定 owner 文档。

没有 unclassified residual risk。

## Completion decision

两路 review 的三个 finding 记录已逐项裁决；两个同源 repair findings 由同一 owner-boundary 修复闭合，forbidden-term finding 已收窄。所有 required validation 通过。本 gate 状态为 `fix-complete`，按用户指令不提交、不进入 re-review；下一 Gateflow entry point 为 `re-review`。
