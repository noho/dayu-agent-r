# PR 190 Compactor LLM-facing S2 implementation

## Gate metadata

- Gate: `implementation`，Slice S2 — Internal rejection truth and LLM repair projection
- Work unit: 修复 PR 190 Compactor LLM-facing findings F01-F03
- Accepted base: `64aade0763788d7bff92f77b91895efa0606aac6`
- Branch: `codex/interactive-oracle`
- Plan: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- S1 acceptance: `docs/gateflow/pr-190-compactor-llm-facing-s1-rereview-acceptance-20260803-181200.md`
- Status: `implementation-complete`；未执行 code review、accepted-slice commit、S3 或 S4
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-s2-implementation-20260803.md`

## First-principles judgment and direct evidence

S2 动机成立。实现前的 production direct evidence 如下：

1. `dayu/host/llm_compaction.py::_user_prompt_vnext` 使用 `PREVIOUS_VALIDATION_REPORT_JSON`，并直接把 `CompactRepairFeedbackV2.to_json()` 放进 LLM user message。
2. `CompactRepairFeedbackV2.to_json()` 同时包含 `previous_attempt_number`、`additional_issue_count`、`required_action` 和 `issues`；前两者是 Host internal 治理/transport 信息，不帮助模型完成修复。
3. `dayu/host/llm_compaction.py::_compactor_input_projection_json` 与 `dayu/host/context_governance.py::_feedback_char_count` 仍需要 internal serialization；因此正确修复不是删改 internal 字段，而是新增唯一 LLM-facing typed projector。
4. `dayu/host/context_governance.py::_collect_policy_issues/_section_caps` 在真实拒绝判断点同时持有 candidate 实际计量值、同一次验收使用的 `MemoryProjectionPolicy` cap 和 `estimate_memory_size_units`；旧 message 却只写模糊的 `Memory policy item/size cap`。
5. production policy 路径实际有 1 个 `session_summary.text` 字符上限，以及 4 个 section 各自的 item/aggregate-character 双上限，所以全 section 同时越界的真实 issue 数是 `1 + 4 * 2 = 9`，与 accepted plan 一致。

Root cause 位于 LLM repair projection owner 与 Context Governance policy reject owner，不在 parser、Memory projector、state machine、fixture 或下游消费者。

## Owner decisions

### Internal truth and LLM projection

- `CompactRepairFeedbackV2` 继续拥有 bounded、脱敏的 Host internal transport truth；`to_json()` 明确为 durable/internal serialization。
- `dayu/host/llm_compaction.py::_repair_feedback_prompt_json_vnext` 是唯一 LLM-facing repair projector。它只接收 `CompactRepairFeedbackV2`，直接读取 typed feedback/issue 字段，不调用 `feedback.to_json()`，也不接受 raw mapping。
- projector 顶层精确投影 `required_action`、`issues`；每个 issue 精确投影 `code`、`json_path`、`message`、`source_labels`。
- renderer 只在 repair attempt 追加由独占行 `REPAIR_FEEDBACK_JSON_BEGIN` / `REPAIR_FEEDBACK_JSON_END` 包围的严格 JSON；旧 marker 已从 production path 删除。
- `required_action` 由 typed feedback 真源直接携带，当前文本自足要求：基于同一输入生成完整 replacement JSON、完整替换前次输出、不是 patch、不得复制/拼接/补写/复用 rejected output。

### Policy cap reject truth

- `session_summary.text` 的 actual/cap/字符计量和缩减动作在 `_collect_policy_issues` 的真实判断点生成。
- 四个 section 的 item actual/cap 与删减/合并动作在 `_section_caps` 生成。
- 四个 aggregate size issue 使用 production owner 的实际投影文本：
  - `evidence_facts`: 各 `claim` 字符数之和；
  - `answer_anchors`: 每项 `title`、一个换行符和 `detail` 的字符数之和；
  - `forward_intents`: 各 `text` 字符数之和；
  - `reference_continuity`: 各 `text` 字符数之和。
- renderer 不读取 policy/candidate，也不猜测或重算 actual/cap。

### Prompt contract

- S1 generic repair 段落按 S1 re-review 批准的 slice boundary 原子升级为 exact marker/schema/action contract。
- 两份 prompt 都说明首次请求无 repair block，repair JSON 顶层字段、issue 四字段的类型/必填性/含义，以及 whole-candidate 动作。
- user prompt 提供最小 repair JSON 示例，但不在示例中伪造一组独占 marker 行，避免 first attempt 被误识别为真实 repair block。
- prompt 明确 repair feedback 不是业务材料，`source_labels` 只是问题定位引用标签，不是业务事实或推理依据；禁止复制、拼接或复用 rejected output/partial。

## Changed files

- `dayu/host/llm_compaction.py`: 新增 typed pure repair projector；统一新 marker；停止 LLM renderer 使用 internal `to_json()`。
- `dayu/host/compaction.py`: 自足化 whole-candidate `required_action`；澄清 feedback/to_json internal serialization ownership。
- `dayu/host/context_governance.py`: 在 policy owner 判断点生成精确 actual/cap/measurement/action；澄清 internal bounded serialization docstrings。
- `dayu/config/prompts/scenes/conversation_compaction.md`: system repair contract 升级为 exact marker/schema/action。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`: user repair contract补齐字段类型、必填性、含义、最小示例与非业务材料边界。
- `tests/host/test_llm_compaction.py`: 覆盖 first/repair marker、exact JSON、typed projector、internal 字段隔离、whole-candidate action、脱敏/总长与 prompt 自足 contract。
- `tests/host/test_compaction_contract.py`: 覆盖真实 9 条 simultaneous cap issues，逐条断言 exact actual/cap/measurement/action，并验证 internal feedback/projector 无截断。
- 本 artifact。

未修改 frozen oracle、scenario registry、publication manifest、public smoke provider seam、state machine、attempt budget、strict output schema/parser、accepted truth/outcome owner、README 或 design 文档。

## Validation

在 Python 3.11 项目虚拟环境中执行：

1. `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q`
   - 结果：`48 passed in 0.35s`。
2. `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_pipeline.py -q`
   - 结果：`71 passed in 0.38s`。
3. `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -k 'default_compactor_prompt'`
   - 结果：`1 passed, 23 deselected in 0.32s`；只验证 deterministic default prompt contract，未运行 real provider。
4. `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
   - 结果：`0 errors, 0 warnings, 0 informations`。
5. `git diff --check`
   - 结果：通过（无输出）。

验证覆盖的关键不变量：

- first attempt 无独占 repair marker 行；repair attempt 恰有一对新 marker；旧 marker 不存在。
- block JSON 可解析，top-level/issue keys 精确；不含 attempt/count/internal typed terms。
- typed projector 直接接收 `CompactRepairFeedbackV2`，不经 raw mapping/internal serialization。
- 全 section 同时越界保留 9 条 issues，`additional_issue_count == 0`，projected block 未截断且小于现有 8192 字符边界。
- strict parser、Context Governance accept owner、operation state machine 与 outcome ownership 未改；相关回归通过。

## Docs decision

- 本轮只写 S2 required durable artifact。
- prompt assets 已变化，但 frozen publication hashes 属于 approved S3；本轮按明确 non-goal 不更新。
- `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 与 `docs/host/design.md` 属于 approved S4；本轮按明确 non-goal 不更新。

## Residual risks and uncovered areas

| Residual | Classification | Owner / destination |
|---|---|---|
| real provider 是否稳定服从新 repair contract 尚未观察 | covered by later approved slice | S3 real-provider adversarial/repair smoke |
| 两个 prompt asset 的 publication hashes 尚未同步 | covered by later approved slice | S3 publication oracle/hash |
| Host/config/tests README 与 Host design 尚未同步当前稳定边界 | covered by later approved slice | S4 docs/README |
| 本 slice 尚未执行独立 code review/re-review | current Gateflow next entry point | S2 code review |

无 unclassified residual risk，无 blocking open question。

## Completion status

- Decision: `S2 implementation complete`
- Finding F03 status at implementation gate: `已实现，待独立 code review`
- Next Gateflow entry point: `S2 code review`
- Commit status: 未 commit，遵守用户要求。
