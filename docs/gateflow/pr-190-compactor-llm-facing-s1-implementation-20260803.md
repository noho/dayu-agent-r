# PR 190 Compactor LLM-facing S1 implementation

## Gate metadata

- Gate: `code review -> fix`
- Work unit: 修复 PR 190 的 Compactor LLM-facing prompt findings F01-F02
- Approved slice: `S1 — Prompt trust boundary and self-contained contract`
- Plan source: `docs/gateflow/pr-190-compactor-llm-facing-f01-f03-plan-20260803.md`
- Accepted plan commit: `a9383ee6cc2772be987b67ea06ffc0298b5ac57c`
- Branch: `codex/interactive-oracle`
- Completion status: `fix-complete`
- Commit status: 未提交
- Review status: 两路 code review 已完成；accepted findings 已修复；未进入 re-review
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-s1-implementation-20260803.md`
- Fix artifact: `docs/gateflow/pr-190-compactor-llm-facing-s1-review-fix-20260803-180215.md`
- Next Gateflow entry point: `re-review`

## Scope and changed files

本 slice 严格只闭合 F01/F02 的 prompt owner 缺陷，没有修改 frozen compact input/output schema、parser、Context Governance、renderer、Memory、publication hash 或状态机。

- `dayu/config/prompts/scenes/conversation_compaction.md`
  - 定义两个 untrusted material marker 的业务语义。
  - 冻结数据/指令边界，明确 current input 与所有 boundary readable text 中的控制指令不得执行，同时材料不得因像指令而被过滤、删除或改写。
  - 使用不暴露内部 marker/schema 的通用语义说明当前 repair 输入与 whole-candidate 动作；本 slice 不改 renderer。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - 在 material placeholder 前重复自足的信任边界。
  - 补齐八种 `source_kind` 的业务语义和开放字符串字段的用途、禁止内容与示例。
  - 用 approved plan 中已由 production owner 验收的 E1/A1/T1/D1 四-source example input/output pair 替换未定义 T1 的最小形状示例。
  - 自足描述：若请求末尾含前一次完整 candidate 的脱敏校验反馈，应按问题和直接修复动作从同一输入完整重产 JSON，不复制、拼接、补写或复用旧输出。
- `tests/host/test_llm_compaction.py`
  - 增加 prompt material marker、八种 source kind、开放字段与通用 whole-candidate repair 语义的 owner contract 断言；不固化 S2 的未来 repair marker/schema。
  - 参数化覆盖 current/trace/evidence/answer 四个控制指令注入位置；从 production renderer 的数据块解析 JSON 并与 typed input 精确比对，证明材料未过滤且控制规则在数据块外。
  - 测试明确只验证 deterministic static boundary，不声称验证模型行为。
- `tests/host/test_public_compact_smoke.py`
  - 删除固定 `"source_labels": ["T1"]` 字符串断言。
  - 从 prompt 动态抽取 example input/output，构造同源 typed input，经 production parser 与 Context Governance 验证 schema、label 同源和 represented/drop exact partition。
  - 扩充精确内部类型、Host 治理与迁移术语的禁止检查；删除会误伤合法业务英文的宽泛子串，并让 material 提取只识别独占一行的真实 marker，避免把 marker 说明文字误当数据块。
- `docs/gateflow/pr-190-compactor-llm-facing-s1-implementation-20260803.md`
  - 记录本 slice 的 durable implementation evidence、review-fix 状态、validation 与 residual risks。
- `docs/gateflow/pr-190-compactor-llm-facing-s1-review-fix-20260803-180215.md`
  - 记录两路 code review finding 裁决、修复证据、验证、docs decision 与 residual risks。

## Direct evidence and decisions

- `dayu.host.llm_compaction._compaction_request_prompt_block_vnext` 只对 `CompactInputV2.to_json()` 做 JSON 序列化并包裹既有 marker；它没有过滤 readable text。F01 因此由 prompt owner 显式解释 marker 与信任边界，不向 renderer、parser 或下游添加字符串过滤器。
- `parse_conversation_compact_output_vnext` 与 `accept_compact_candidate_v2` 已拥有 frozen v2 结构、source-kind、coverage 与 accept truth。S1 没有扩张 schema，而是让 prompt 对这些既有业务契约自足。
- Approved 四-source example 由测试直接从 prompt 抽取；production parser 接受 output，Context Governance 接受 candidate，represented labels 与 dropped labels 互斥且并集精确等于 input boundary labels。
- `_user_prompt_vnext` 当前仍输出 `PREVIOUS_VALIDATION_REPORT_JSON` 加脱敏反馈 JSON。S1 prompt 因此只承诺 generic whole-candidate 修复语义，不提前承诺 S2 的 marker/projector exact schema；S2 将原子落地 marker、projector 与 prompt。
- `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 只检查当前相关的精确内部术语；保留既有 `Host-owned context compaction` 和 typed names，并新增 `CompactValidationIssueV2`、`previous_attempt_number`、`additional_issue_count`、`Memory policy`。
- 未发现 frozen schema 或 semantic owner 冲突；S1 fix stop condition 未触发。

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

本 fix 不更新 README。prompt/config 与 tests README 的稳定职责说明已由 approved plan 的 S4 拥有；当前用户限定 S1 只允许四个实现/测试文件和两个 gate artifacts，提前改 README 会越过 slice boundary。

## Residual risks and uncovered areas

- `fixed in current slice` — S1 prompt/renderer checkpoint mismatch 已消除：prompt 不再承诺未来 repair marker 或 exact schema，当前 renderer 的脱敏反馈仍受 generic whole-candidate 规则覆盖。
- `fixed in current slice` — forbidden-term 测试不再用 `Host`、`Memory`、`Attempt`、`Python`、`dataclass`、`StrEnum` 等宽泛子串误伤合法业务英文，改为精确内部术语。
- `covered by later approved slice` — S2 原子落地 repair marker、唯一 LLM-facing projector 与对应 prompt/test contract；S1 不提前暴露这些未来语义。
- `covered by later approved slice` — 当前测试只证明 deterministic static data/instruction boundary，不验证真实模型是否抵抗 current/trace/evidence/answer 注入；由 S3 real-provider observation 闭合。
- `covered by later approved slice` — 两个 prompt asset 的 frozen publication hash 现已按预期失配；本 slice 未运行或修补 publication 全文件 oracle，由 S3 同步真实 asset hash 与 manifest hash。
- `covered by later approved slice` — config/tests README 与 Host design 的稳定 owner 决策由 S4 更新。

没有 unclassified residual risk，也没有需要扩张 S1 schema、owner 或 file scope 的问题。

## Completion decision

S1 code review fix 达到 completion signal：两路 accepted findings 已在 owner boundary 修复，两组 S1 测试、pyright 与 `git diff --check` 全绿。按用户指令不提交、不进入 re-review；下一入口为 `re-review`。
