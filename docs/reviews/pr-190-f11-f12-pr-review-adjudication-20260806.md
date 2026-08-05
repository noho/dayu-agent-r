# PR 190 F11/F12 PR Review Adjudication

## Gate

- Reviewed head: `9fa3ff799506e66f995b4156dbb960c98c2f737e`
- MiMo artifact: `docs/reviews/pr-190-f11-f12-pr-mimo-review-20260806.md`
- DeepSeek artifact: `docs/reviews/pr-190-f11-f12-pr-ds-review-20260806.md`
- Controller decision date: 2026-08-06

两路 reviewer 均独立审阅了 PR 190。以下逐项裁决，不以 reviewer 结论一致性替代直接代码、设计与测试证据。

## MiMo findings

### MiMo-01 — force-answer 应移除 structured output

**Decision: rejected.**

`AgentRunRequest.structured_output` 是 run-scoped Engine contract。`docs/engine/design.md` 明确冻结 initial、工具后续、length continuation 与 force-answer 都原样传递同一个 request，且 provider 拒绝时保留原失败，不降级到更弱模式。Compactor 的 force-answer 仍必须产出同一 strict JSON shape；移除 schema 会削弱 Host 之前的 transport 请求并让降级路径产生不符合 run contract 的自由文本。当前实现与 design truth 同源，review 建议会造成 contract drift，故不修改生产代码。

### MiMo-02 — malformed compactor terminal 不应令 Tool Trace fail closed

**Decision: rejected.**

F11 acceptance 明确要求 manifest/input/response identity mismatch 必须 fail closed 或产生 typed limitation，禁止静默拼接。当前 public read 在 canonical binding 缺少 required manifest identity 时 fail closed，未从相邻事件或配置推断。把该错误局部吞掉会弱化正式 resolver 的 identity 保证；本 work unit 不新增第二种降级语义。

### MiMo-03 — rejected attempt 的 successful response identity 缺 analysis owner test

**Decision: accepted as a low-severity owner-test gap.**

`tests/host/test_tool_trace_queries.py::test_compactor_response_resolver_projects_rejected_nullable_identity` 已覆盖 public resolver 对 post-success rejection 的 typed identity，真实 evidence 也覆盖 successful/rejected 两类 canonical equality；但 analysis rules 的现有正向 projection fixture 只断言 `ACCEPTED`。F11 acceptance 要求正式 JSON/Markdown analysis 能让 CLI CI 消费 successful 和 rejected identity。增加一个 `ATTEMPT_REJECTED + successful_response_identity` analysis owner test，复用同一 typed projection helper，不改生产语义。

### MiMo-04 — parser 的 request 参数没有语义作用

**Decision: accepted.**

`parse_conversation_compact_output_vnext` 只做 JSON structure boundary；immutable request/source/cap binding 由后续 Context Governance accept barrier 唯一拥有。当前 `request` 参数只做类型检查，既不参与 strict parse，也不应在 parser 层参与 semantic acceptance，因而对调用者形成过度承诺。按用户已确认的 fresh contract 移除该参数及对应旧测试，调用方只传 `final_answer`。

### MiMo-05 / MiMo-06 — repair code/path 从异常字符串反推

**Decision: accepted and combined as one semantic-owner fix.**

当前 structure parser 把稳定 code 和 JSON path 编进 `ValueError` 文本，`llm_compaction` 再从经过脱敏/截断的字符串解析两项 typed fact。这直接违反项目“不得从字符串反推语义”的 owner 约束，也让 parser 文案与 repair taxonomy 偶然耦合。正确修复是在 `compact_structure.py` 的 strict parser boundary 产生携带 `CompactValidationIssueCodeV3` 与 JSON path 的 typed exception；`llm_compaction` 只对白名单 typed fields 做有界、安全 projection。不得从 message 恢复 code/path，不改变 strict validation、bounded repair、prompt/schema 或 acceptance contract。

### MiMo-07 — bounded repair feedback 可能在单 issue、零 labels 时抛 RuntimeError

**Decision: rejected as unreachable under the typed input bounds.**

`build_compact_repair_feedback_v3` 先把每个 issue 的 `json_path`、`message` 与每个 label 都限制到 240 字符；单 issue 且零 labels 的 canonical serialization 远低于 8192 字符。循环只在仍有 labels 时逐一移除，达到零 labels 时总长必已低于 cap。review 的触发条件无法由该函数的 typed/bounded intermediate state 构造；不为不可达状态增加兼容 fallback。

### MiMo-08 — runtime / Engine structured-output enums 缺同步守护

**Decision: rejected as evidence-invalid.**

`tests/service/test_host_assembly.py::test_structured_output_capability_enums_map_mechanically_by_value` 已断言两侧完整 value set 相等，并逐项验证机械构造。双 enum 是 `dayu.runtime` 不得反向 import Engine 的架构结果，现有 owner test 正是所需守护。

## DeepSeek findings

### DS-01 — aggregate coverage 声称 90%，单 suite 实测 85%

**Decision: rejected as a measurement mismatch, not a product or evidence defect.**

Aggregate acceptance 明确使用：

```text
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  --cov=dayu.host.compact_structure --cov-report=term-missing
```

该 owner-suite union 得到 89.66%，终端按整数显示 90%。DeepSeek 只运行 `test_compaction_contract.py`，得到 85%；两者测试集不同，不构成原声明错误。两种测量均超过项目要求的 80%。最终 validation 将再次记录完整命令与原始结果。

### DS-02 — immutable descriptor defensive branches 未覆盖

**Decision: rejected as a finding.**

这些分支只在模块内部 immutable literal 被错误构造时 fail fast，外部不能注入 descriptor。当前 public structure projections、strict parser 和 adversarial LLM output 分支由 owner suites 覆盖；为私有不可达 literal 构造路径暴露测试 seam 会扩大 surface，且 85%/90% 两种口径都已超过门槛。

## DeepSeek open questions and residuals

- GitHub 无 checks：如实记录为“no checks reported”，不伪称 CI PASS；本地 Gateflow validation 继续执行。
- 三条 replacement scenarios：按冻结边界保持 `unadjudicated`，由 Oracle controller 在 final head 上裁决。
- v2 artifact 不兼容：用户已明确要求 fresh schema、禁止 compatibility reader/shim，不是本 work unit residual defect。
- `session_summary=null`：required + nullable 是 intentional full-replacement contract，由 strict Host parser、Memory owner tests 和真实 observation 共同覆盖。
- non-TTY interactive：不属于 F11/F12 改动或本 PR-review fix；保留给其 CLI owner 的后续 scenario 验证，不在此门扩 scope。

## Required PR-review fix

1. 在 structure owner 定义 typed parse failure，直接携带稳定 issue code 与 JSON path；repair projection 不再解析错误字符串。
2. 移除无语义作用的 `parse_conversation_compact_output_vnext(request, ...)` 参数并迁移相应测试。
3. 增加 `ATTEMPT_REJECTED + successful response identity` 的 Tool Trace analysis JSON/Markdown owner test。
4. 运行 focused owner tests、changed-file coverage、全仓 pyright、Ruff、JSON validation 与 `git diff --check`。
5. 两路 reviewer 对修复后的 exact head 独立 re-review，全部 accepted 后才进入 final validation。

不修改 prompt、JSON output schema、Host acceptance、Memory projection、Engine structured-output semantics、oracle/scenario registry、immutable evidence 或 README/design truth。
