# P1-C Plan Adversarial Review — AgentDS

## Review Metadata

- **Date**: 2026-07-09
- **Reviewer**: AgentDS (Claude Code)
- **Plan under review**: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- **Supporting artifacts**:
  - AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-controller-validation.md`
  - Umbrella plan: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
  - Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
  - Design truth: `docs/host/design.md`, `docs/engine/design.md`
- **Conclusion**: **pass-with-risks** (1 blocking, 5 non-blocking)

## Executive Summary

P1-C plan 的动机成立，直接证据经过独立代码验证确认，owner boundary 划分正确，slices 可执行。但存在 1 个 blocking finding（memory evidence_kind 渲染路径在 S1 中未作为确定性行动项）和 5 个 non-blocking findings。Blocking finding 不影响 plan 的整体结构，只需在 S1 implementation shape 中增加一个明确的 action item 即可解除。

---

## Findings

### P1C-PLAN-DS-F01 — RunInput memory evidence_kind 渲染未在 S1 中作为确定性行动项

- **Severity**: HIGH
- **Blocking**: YES
- **Direct evidence**:
  - `dayu/host/run_input.py:2349`: `_memory_evidence_fact_message()` 将 `evidence_kind={fact.evidence_kind.value}` 渲染进 `SystemMessage` content，该 message role 为 `SYSTEM`，必然进入 LLM context。
  - `dayu/host/run_input.py:3445-3450`: fallback codec 路径同样渲染 `evidence_kind={evidence_kind}`。
  - `dayu/host/memory.py:469`: `MemoryEvidenceBackedFactKind` 是独立于 `FactEvidenceKindVNext` 的并行 evidence kind 枚举。
  - `dayu/host/memory.py:1892`: hardcode `MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE`。
- **Root cause**: Plan 的 S1 implementation shape 第 4 条写 "Accepted compact view / memory rendering 中如果仍输出 `evidence_kind=...`，必须判断是否进入 LLM context。若进入，改为业务可读字段或删除；若仅 diagnostic/internal，则在 S0/S3 分类中说明。"——但该条以条件判断形式出现，未将该路径列为确定性 S1 action item。当前代码证据已明确显示该路径进入 LLM context（构造 `SystemMessage`），不需要 S0 再判断。
- **Owner boundary**: `run_input.py` 的 memory rendering 属于 RunInputBuilder projection 边界，应随 S1 清理或随 P2-B memory/test hardening 处理。若推迟到 P2-B，必须在 S0/S3 分类中明确写出"deferred to P2-B with reason"，不能以条件判断形式留空。
- **Suggested fix**: 在 S1 implementation shape 中增加一条确定性 action："`_memory_evidence_fact_message()` 中 `evidence_kind={fact.evidence_kind.value}` 改为业务可读标签或删除；若 `MemoryEvidenceBackedFactKind` 只有一个枚举值 `DERIVED_FROM_EVIDENCE`，该字段对模型无区分信息量，建议直接删除渲染"。或在 S3 propagation audit 中将其显式分类为 "deferred to P2-B"。
- **Verification**: 代码路径 `run_input.py:2349` → `SystemMessage` → LLM context 已确认。

### P1C-PLAN-DS-F02 — Duplicate governance 非 AWAITING_FANOUT 消息的 LLM-facing 暴露未完整分析

- **Severity**: HIGH
- **Blocking**: NO（可通过 S0 分类补全）
- **Direct evidence**:
  - `dayu/host/tool_runtime.py:2964-2970`: 当 `policy_decision.kind is ALLOW` 且 `duplicate_decision.kind is not ALLOW`（即 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING），policy_decision 被 `_policy_decision_from_duplicate()` 覆盖。
  - `dayu/host/tool_runtime.py:2986-2987`: 覆盖后的 `policy_decision` 若非 ALLOW，进入 `_governed_failure_outcome(policy_decision)` → `ToolFailedOutcome` → LLM-facing tool outcome。
  - `dayu/host/tool_duplicate_governance.py:89-98`: HINT/HARD_STOP 消息内容本身是模型可执行的行为指令（如"请优先使用上一次工具结果继续推理"），不含 Host wait/poll/adapter 治理词，可能是合法的 LLM-facing 文本。
  - 但 `awaiting_fanout` 消息 "相同工具请求已经进入等待状态" 走 `_awaiting_fanout_record()` 的提前返回路径（`tool_runtime.py:2959-2963`），不进入 `ToolFailedOutcome`——其 message 只留在 `DuplicateDecision` 对象中，进入 ToolTrace diagnostic。
- **Root cause**: Plan 第 41-42 行只分析了 AWAITING_FANOUT 的 context path，未分析 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION 同样经过 `_governed_failure_outcome` 进入 LLM context 的路径。该遗漏可能导致 implementation 时只处理 AWAITING_FANOUT 文案而忽略其他 duplicate 消息。
- **Owner boundary**: Duplicate governance policy → ToolRuntime governed failure → ToolFailedOutcome → Engine tool_result_accepted → LLM tool message。
- **Suggested fix**: 在 S0 classification 中增加对 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING 消息的 LLM-facing 分类。由于这些消息内容（如"请使用上一次工具结果继续推理"）可能是合法业务可读指令而非治理泄漏，分类结论可以是"保留为 LLM-facing 行为指令，不按治理泄漏处理"。关键是 S0 必须显式分类，不能只分析 AWAITING_FANOUT。
- **Verification**: 代码路径 `tool_runtime.py:2964-2987` → `_governed_failure_outcome()` → `ToolFailedOutcome` → LLM context 已确认。

### P1C-PLAN-DS-F03 — "等待工具结果返回" 分类标准缺乏可操作判据

- **Severity**: MEDIUM
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/config/prompts/base/tools.md:71`: `start_fins_download` 的 `<when_tool>` 块中写"调用后等待工具结果；结果会说明..."。
  - `dayu/config/prompts/base/tools.md:79`: `start_fins_preprocess` 同模式。
  - Engine design (`docs/engine/design.md:388-389`): "这些恢复输入必须是 LLM-facing 的业务可读消息...不能要求模型理解 wait record、poll adapter、external job lifecycle、observation handle 或 Host/ToolRuntime 治理术语"。
- **Root cause**: Plan 将"等待工具结果返回"分类为"业务可读行为说明"可保留，但判据主要靠语义直觉（"不要求模型理解 Host wait id / poll / adapter"）而非可操作 checklist。Implementation 时不同人可能对同一短语做出不同分类。
- **Owner boundary**: Fins tool schema owner（`tools.md` 中的 `<when_tool>` prompt fragment）。
- **Suggested fix**: 在 S0 分类表中增加 explicit litmus test：一条 LLM-facing 文本是否构成 governance leakage 的判据是——删除该文本后，模型是否仍然能完成工具调用任务？若"调用后等待工具结果"删除后模型会误以为工具同步返回，则该文本是任务必要的行为说明，不是治理泄漏。若"未进入等待状态"删除后模型仍能从 `error` 字段判断失败，则该文本是治理泄漏。将此 litmus test 写入 S0 artifact。
- **Verification**: 现有代码中 `<when_tool>` 块的"等待工具结果"是 prompt fragment 级行为指引，符合 Engine design 的 resume 输入要求。

### P1C-PLAN-DS-F04 — `ToolBusinessCancelled` fallback 路径未纳入分析

- **Severity**: MEDIUM
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/runtime/tool_call_projection.py:97-112`: `ToolBusinessCancelled` dataclass docstring 写"message: 可选取消说明；为空时由 `host_cancelled_outcome` 填充默认说明。"
  - `dayu/tools/doc_tools.py:2095`: `return ToolBusinessCancelled(message="文档工具调用已被宿主取消。", hint=_DOC_CANCELLED_HINT)` —— message 已显式传入但 content 仍含"宿主取消"。
  - `dayu/tools/doc_tools.py:71`: `_DOC_CANCELLED_HINT` 仍含"后续调度"。
  - `dayu/tools/web/web_tools.py:164-165`: `_WEB_SEARCH_CANCELLED_MESSAGE` 仍含"宿主取消"。
- **Root cause**: Plan S2 分析了 `host_cancelled_outcome()` 的直接调用点，但未分析通过 `ToolBusinessCancelled` → `host_cancelled_outcome()` 的间接 fallback 路径。当前所有已知 call site 都显式传了 message，但 message 内容本身仍含"宿主取消"。此外 `ToolBusinessCancelled` 的 docstring 承诺 fallback 到 runtime default，与 S2 要求"message/hint 必填"冲突。
- **Owner boundary**: `ToolBusinessCancelled` 是 runtime 层的业务取消中间类型，但它的 fallback 语义指向 runtime default，与 S2 的 owner boundary 修正方向相反。
- **Suggested fix**: S2 implementation shape 增加一条：`ToolBusinessCancelled` 的 message/hint 改为必填（或删除该类型并将其调用点直接改为调用方自构造 outcome）。同时审计 doc_tools.py/web_tools.py 的 `_CANCELLED_MESSAGE` 中的"宿主取消"是否应改为"工具调用已取消"等业务可读表达。
- **Verification**: 当前 3 个 `ToolBusinessCancelled` 构造点（doc_tools 1 个 + web_tools 2 个 + fins_tools 间接）均显式传 message，但不排除未来新增调用点依赖 fallback。

### P1C-PLAN-DS-F05 — Compaction evidence_kind Host 派生方案未具体化

- **Severity**: MEDIUM
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/host/compaction.py:83-88`: `FactEvidenceKindVNext` 枚举值 `TOOL_RESULT`、`TOOL_SOURCE_TEXT`、`ACCEPTED_EVIDENCE_MATERIAL` 当前由 LLM 在 compaction 输出中选择。
  - `dayu/host/compaction.py:1185-1191`: `EvidenceBackedFactCandidateVNext.evidence_kind` 是 typed 必填字段，parser 校验。
  - `dayu/host/llm_compaction.py:665`: parser 将 LLM 输出的字符串映射为 `FactEvidenceKindVNext`。
  - Plan S1 提议"Host 在解析阶段根据 label 所属 material section 派生 typed evidence kind"。
- **Root cause**: Plan 描述了"Host derived evidence kind"的方向但不具体。当前 compaction material 的 `evidence_material` section 包含 tool result text、source text、accepted evidence material 混合内容，不同 kind 可能来自同一 material section。仅靠 section label 可能无法可靠派生 evidence_kind。Plan 未说明 Host derivation 的输入信号是什么（label prefix？material block kind？tool outcome kind？）。
- **Owner boundary**: Host compaction material builder → evidence material section → compact candidate evidence_kind。
- **Suggested fix**: S1 implementation shape 增加一条："在 S1 开始前，先确认 Host derivation 的可靠输入信号。至少列出 3 条候选方案：① 按 `evidence_material` block 的 `CompactMaterialBlockKind` 派生；② 在 compact material construction 时预标注 evidence kind 为 material block metadata；③ 保留 LLM-facing `evidence_kind` 字段但将其值域改为业务可读标签（如 `direct_tool_output`/`source_document_text`/`previously_accepted_fact`）。在 S0/S1 交界处由 implementer 选择并记录理由。"
- **Verification**: 当前 `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE`（`compaction.py:61`）已存在，可能是 derivation 的可靠信号。

### P1C-PLAN-DS-F06 — "后续调度" 在多个 caller 处重复硬编码，S2 只清理了 Fins 入口

- **Severity**: LOW
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/fins/tools/fins_tools.py:80`: `_FINS_CANCELLED_HINT = "当前工具调用已停止；等待新的用户指令或后续调度。"`
  - `dayu/tools/doc_tools.py:71`: `_DOC_CANCELLED_HINT = "当前工具调用已停止；等待新的用户指令或后续调度。"`
  - `dayu/fins/tools/read_runtime_helpers.py:337`: `hint="当前工具调用已停止；等待新的用户指令或后续调度。"`
  - 三处硬编码了相同的"后续调度"文案。
- **Root cause**: 相同语义在 3 个模块中独立硬编码，违反"禁止每个消费者各自重建"原则。虽然 S2 会修改这些文案，但 plan 未要求抽取共享 cancel hint helper 或至少确保三处改写一致。
- **Owner boundary**: 各工具 callable owner 各自定义 cancel hint → 应有一个 shared tool cancel hint contract。
- **Suggested fix**: S2 implementation shape 增加一条："三处 `_CANCELLED_HINT` 的改写必须保持一致；优先抽取一个 shared `_tool_cancelled_hint()` helper 或常量到 `dayu.contracts` 或 `dayu.runtime`（仅限业务可读中性文本）。若暂时不抽取，implementation artifact 必须记录三处改写的一致性验证结果。"
- **Verification**: 当前三处文案完全相同（包括标点），确认是复制粘贴。

---

## Cross-cutting Observations

### 动机验证

Plan 的动机成立，且经过独立代码验证确认：
- Compaction prompt 确实要求 LLM 理解 `user_visible_run_state` 和 `evidence_kind=tool_source_text|accepted_evidence_material`（`conversation_compaction_user.md:16,40`）。
- Runtime 确实提供 Host-governance 默认 LLM 文案（`tool_call_projection.py:39-40`）。
- Fins tool outcome 确实含"未进入等待状态"（`download_tools.py:105,113`）。
- Cancel hint 确实含"后续调度"（三处硬编码）。

### Owner Boundary 验证

Plan 的 owner boundary 划分与代码证据一致：
- Compaction LLM-facing schema → Host compaction/compact material boundary。✅
- Fins tool schema/outcome → Fins tool callable owner。✅
- Runtime cancelled helper → runtime 只拥有层中立构造，不拥有 Host-governance 文案。✅
- P1-A accepted-result projection → 保持不变。✅
- P1-B lifecycle/cancel durable contract → 保持不变。✅
- Duplicate governance → S0 先分类再决定。✅（但见 F02 关于分析不完整）

### "等待工具结果返回" 分类判断

Plan 对"等待工具结果返回"不做 blanket delete 是正确的。直接证据确认：
- `<when_tool start_fins_download>` 中的"调用后等待工具结果；结果会说明..."是工具行为说明，告诉模型该工具是异步的、结果稍后返回。
- 该文本不要求模型理解 Host wait id、poll adapter、状态机或治理标识。
- 删除该文本可能导致模型误以为工具同步返回并编造结果。

但分类标准需要更可操作的判据（见 F03）。

### Stop Condition 验证

Plan 的 5 个 stop condition 均基于真实风险：
1. Durable compaction schema 变更 → 真实风险，compaction contract 涉及 `EvidenceBackedFactCandidateVNext` typed validation。
2. 字段仍必须暴露 Host governance → 真实风险，需确认没有上游缺失。
3. Runtime 公共 API 迁移不可控 → 真实风险（见 F04）。
4. Duplicate awaiting fanout 改写会改变 typed behavior → 真实风险，当前 AWAITING_FANOUT 直接返回 prior awaiting outcome，不受 message 影响。
5. rg 扫描命中大型 HTML → 已通过 `--glob '!**/*.html' --glob '!**/*.htm'` 缓解。

### Slice 可执行性

| Slice | 可执行 | 风险 |
|-------|--------|------|
| S0 | ✅ | 分类标准需要 litmus test（F03） |
| S1 | ✅（with fix） | memory evidence_kind 需确定性 action（F01）；Host derivation 方案需具体化（F05） |
| S2 | ✅ | ToolBusinessCancelled 路径需补充（F04）；三处 cancel hint 需一致性（F06） |
| S3 | ✅ | 无明显风险 |

### 不扩大验证

Plan 严格遵守 P1-C scope：
- 不改 P1-A accepted-result projection contract。✅
- 不改 P1-B lifecycle/cancel durable contract。✅
- 不进入 P2-A CLI/Service、P2-B memory/test hardening、P2-C fallback prompt。✅
- 不重构 Fins ingestion runtime、wait adapter、ToolRuntime fanout。✅

### Validation Commands 验证

Validation commands（第 6 节）覆盖充分：
- pytest 覆盖 compaction、runtime、fins、tools 测试。✅
- 两条 rg scan 覆盖 governance leakage 和 duplicate/等待 两类模式。✅
- pyright + git diff --check。✅

但缺少 P1-A contract 完整性验证——建议增加一个 targeted assertion：
```bash
source .venv/bin/activate && rg -n "accepted_result_projection\|AcceptedEvidenceEnvelope\|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
```
确认 P1-C 变更后这些 consumer 仍通过 P1-A helper 消费 accepted result projection。

### README Trigger 验证

Plan 的 README 决策完整：
- `dayu/host/README.md` ✅（compaction/material 变更）
- `dayu/fins/README.md` ✅（tool schema/outcome 变更）
- `dayu/config/README.md` ✅（prompt asset 变更）
- `tests/README.md` ✅
- `dayu/runtime/README.md` → 不存在该文件，无需触发 ✅
- 根 `README.md` → 正确不触发 ✅
- `dayu/README.md` → 正确不触发 ✅

### Propagation Audit 模板验证

Plan 第 8 节的 propagation audit 模板覆盖了全部 9 个语义族，包括 P1-A/P1-B contract preservation 检查。✅

---

## Residual Scan Noise Risk 评估

Plan 的两条 baseline rg 命令中的 `poll` 和 `adapter` 模式会命中内部代码：
- `dayu/host/tool_runtime.py` 中 `_poll_*` 辅助函数
- `dayu/host/waiting.py` 中 `poll awaiting candidate requires external_job_ref`
- adapter registry 相关代码

这些命中是预期的 internal-only 匹配。Plan 第 285 行正确分类为"allowed internal"。Implementation 时需确保不因 grep 噪音而误判为 leakage。

---

## Conclusion

**Verdict: pass-with-risks**

P1-C plan 的动机基于当前代码直接证据且已验证，owner boundary 划分正确，slices 可执行且不过度耦合，stop conditions 覆盖真实风险。1 个 blocking finding（F01：memory evidence_kind 渲染路径未在 S1 中作为确定性行动项）不影响 plan 整体结构，只需在 S1 implementation shape 中增加一个明确的 action item。

5 个 non-blocking findings 可在 S0/S3 classification 和 implementation artifact 中自然解决，不需要改变 plan structure 或 slice ordering。

### Action Items for Plan Author

1. **[REQUIRED]** S1 implementation shape 第 4 条改为确定性行动：明确 `_memory_evidence_fact_message()` 中的 `evidence_kind=...` 渲染需要修改或删除，或显式分类为 "deferred to P2-B with reason"。
2. **[RECOMMENDED]** S0 classification 增加 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING 的 LLM-facing 路径分析。
3. **[RECOMMENDED]** S0 增加"等待工具结果返回"分类的 litmus test 判据。
4. **[RECOMMENDED]** S2 增加 `ToolBusinessCancelled` fallback 路径分析和三处 cancel hint 一致性要求。
5. **[RECOMMENDED]** S1 增加 evidence_kind Host derivation 的候选方案列举。
