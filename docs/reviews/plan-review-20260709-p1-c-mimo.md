# P1-C Plan Adversarial Review — AgentMiMo

## Review Metadata

- **Date**: 2026-07-09
- **Reviewer**: AgentMiMo (MiMo via Claude Code)
- **Plan under review**: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- **Supporting artifacts**:
  - AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-controller-validation.md`
  - AgentDS review: `docs/reviews/plan-review-20260709-p1-c-ds.md`
  - Umbrella plan: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
  - Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
  - Design truth: `docs/host/design.md`, `docs/engine/design.md`
- **Conclusion**: **pass** (0 blocking, 7 non-blocking)

## Executive Summary

P1-C plan 动机基于当前代码直接证据且已独立验证，owner boundary 划分正确，slices 可执行且不过度耦合，stop conditions 覆盖真实风险。Plan 整体结构健全，无 blocking finding。

DS review 提出的 F01（memory evidence_kind 渲染）经独立判断**不构成 blocking**：`run_input.py` 已在 S1 文件清单中，plan 的条件判断措辞虽然可以更确定，但 implementer 在 S1 执行时必然会发现并处理该路径。这是一个措辞强化建议，不是结构性缺陷。

DS F02（duplicate governance 非 AWAITING_FANOUT 路径）是有效的分析补充，应在 S0 分类中覆盖，但不 blocking plan structure。

本 review 共产出 7 个 non-blocking findings，均可在 S0/S1/S2 implementation artifact 中自然解决。

---

## DS F01 Blocking 判定：不 blocking

DS F01 声称 `run_input.py:2349` 的 `_memory_evidence_fact_message()` 将 `evidence_kind={fact.evidence_kind.value}` 渲染进 `SystemMessage`，该路径必然进入 LLM context，而 S1 只以条件判断形式提及，未列为确定性行动项。

**MiMo 独立判定：non-blocking。理由如下：**

1. **`run_input.py` 已在 S1 文件清单中**（plan 第 130 行）。Implementer 在 S1 执行时必须审阅该文件。
2. **Plan 第 141 行**写 "Accepted compact view / memory rendering 中如果仍输出 `evidence_kind=...`，必须判断是否进入 LLM context。若进入，改为业务可读字段或删除"。这是条件判断没错，但条件的两个分支都有明确行动（改或删），不会出现"什么也不做"的结果。
3. **S1 residual scan**（plan 第 153 行）`rg -n "evidence_kind="` 会命中 `run_input.py` 的该渲染路径，implementer 不可能忽略。
4. **措辞强化 ≠ 结构缺陷**。将"如果仍输出"改为"当前已确认输出"是改进，但不影响 plan 的可执行性或完整性。

**建议**：在 S1 implementation shape 第 4 条中将"如果仍输出"改为"当前已确认在 `run_input.py:2349` 输出"，消除歧义。这是措辞优化，不改变 plan structure。

---

## Findings

### P1C-PLAN-MIMO-F01 — S1 residual scan 缺少 `run_input.py` 命中项的预期分类

- **Severity**: LOW
- **Blocking**: NO
- **Direct evidence**:
  - Plan 第 153 行 S1 residual scan: `rg -n "user_visible_run_state|tool_source_text|accepted_evidence_material|evidence_kind=" dayu/config dayu/host tests/host`
  - `dayu/host/run_input.py:2349`: `_memory_evidence_fact_message()` 渲染 `evidence_kind={fact.evidence_kind.value}`
  - `dayu/host/run_input.py:3445-3450`: fallback codec 路径同样渲染 `evidence_kind={evidence_kind}`
  - `dayu/host/memory.py:469`: `MemoryEvidenceBackedFactKind` 是独立于 `FactEvidenceKindVNext` 的并行枚举
- **Root cause**: S1 residual scan 会命中 `run_input.py` 中的 `evidence_kind=` 渲染，但 plan 未预先说明这些命中的预期分类。`MemoryEvidenceBackedFactKind` 是独立枚举，其清理逻辑可能与 `FactEvidenceKindVNext` 不同，plan 未区分。
- **Owner boundary**: `run_input.py` memory rendering 属于 RunInputBuilder projection 边界。
- **Suggested fix**: 在 S1 implementation shape 中增加一条："`run_input.py` 中 `_memory_evidence_fact_message()` 和 fallback codec 的 `evidence_kind` 渲染属于 `MemoryEvidenceBackedFactKind`（独立于 `FactEvidenceKindVNext`），需单独判断：若该枚举只有 `DERIVED_FROM_EVIDENCE` 一个值，对模型无区分信息量，建议直接删除渲染；若有多个值，改为业务可读标签。"
- **Verification**: `memory.py:469` 确认 `MemoryEvidenceBackedFactKind` 独立存在；`run_input.py:2349` 确认渲染路径进入 `SystemMessage`。

### P1C-PLAN-MIMO-F02 — Duplicate governance 非 AWAITING_FANOUT 消息的 LLM-facing 路径分析缺失

- **Severity**: MEDIUM
- **Blocking**: NO（S0 分类可自然补全）
- **Direct evidence**:
  - `dayu/host/tool_runtime.py:2964-2970`: 当 `policy_decision.kind is ALLOW` 且 `duplicate_decision.kind is not ALLOW` 时，policy_decision 被 `_policy_decision_from_duplicate()` 覆盖。
  - `dayu/host/tool_runtime.py:2986-2987`: 覆盖后的 `policy_decision` 若非 ALLOW，进入 `_governed_failure_outcome(policy_decision)` → `ToolFailedOutcome` → LLM-facing tool outcome。
  - `dayu/host/tool_duplicate_governance.py:89-98`: HINT/HARD_STOP 消息内容是模型可执行的行为指令（如"请优先使用上一次工具结果继续推理"），不含 Host wait/poll/adapter 治理词。
- **Root cause**: Plan 第 41-42 行只分析了 AWAITING_FANOUT 的 context path，未分析 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING 同样经过 `_governed_failure_outcome` 进入 LLM context 的路径。
- **Owner boundary**: Duplicate governance policy → ToolRuntime governed failure → ToolFailedOutcome → Engine tool_result_accepted → LLM tool message。
- **Suggested fix**: 在 S0 classification 中增加对 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING 消息的 LLM-facing 路径分析。由于这些消息内容是合法业务可读指令而非治理泄漏，分类结论应为"保留为 LLM-facing 行为指令，不按治理泄漏处理"。关键是 S0 必须显式分类，不能只分析 AWAITING_FANOUT。
- **Verification**: 代码路径 `tool_runtime.py:2964-2987` → `_governed_failure_outcome()` → `ToolFailedOutcome` → LLM context 已确认。

### P1C-PLAN-MIMO-F03 — "等待工具结果返回" 分类判据缺乏可操作 litmus test

- **Severity**: MEDIUM
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/config/prompts/base/tools.md:71`: `start_fins_download` 的 `<when_tool>` 块中写"调用后等待工具结果；结果会说明..."。
  - Plan 第 12 行: "等待工具结果返回只有在描述长事务工具结果稍后返回、并且不要求模型理解 Host wait id / poll / adapter / 状态机时，可以是业务可读行为说明。"
  - Engine design (`docs/engine/design.md:388-389`): "这些恢复输入必须是 LLM-facing 的业务可读消息...不能要求模型理解 wait record、poll adapter、external job lifecycle、observation handle 或 Host/ToolRuntime 治理术语"。
- **Root cause**: Plan 将"等待工具结果返回"分类为"业务可读行为说明"可保留，但判据主要靠语义直觉而非可操作 checklist。Implementation 时不同人可能对同一短语做出不同分类。
- **Owner boundary**: Fins tool schema owner（`tools.md` 中的 `<when_tool>` prompt fragment）。
- **Suggested fix**: 在 S0 分类表中增加 explicit litmus test：一条 LLM-facing 文本是否构成 governance leakage 的判据是——删除该文本后，模型是否仍然能完成工具调用任务？若"调用后等待工具结果"删除后模型会误以为工具同步返回，则该文本是任务必要的行为说明，不是治理泄漏。若"未进入等待状态"删除后模型仍能从 `error` 字段判断失败，则该文本是治理泄漏。将此 litmus test 写入 S0 artifact。
- **Verification**: 现有代码中 `<when_tool>` 块的"等待工具结果"是 prompt fragment 级行为指引，符合 Engine design 的 resume 输入要求。

### P1C-PLAN-MIMO-F04 — `ToolBusinessCancelled` fallback 路径与 S2 "message/hint 必填" 方向冲突

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

### P1C-PLAN-MIMO-F05 — Evidence kind Host derivation 方案未具体化，可能与 LLM 历史选择产生语义不一致

- **Severity**: MEDIUM
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/host/compaction.py:83-88`: `FactEvidenceKindVNext` 枚举值 `TOOL_RESULT`、`TOOL_SOURCE_TEXT`、`ACCEPTED_EVIDENCE_MATERIAL` 当前由 LLM 在 compaction 输出中选择。
  - `dayu/host/compaction.py:61`: `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE` 已存在，可能是 derivation 的可靠信号。
  - Plan S1 第 139 行: "Host 在解析阶段根据 label 所属 material section 派生 typed evidence kind，或把 evidence kind 固定为 Host-owned internal value。"
- **Root cause**: Plan 描述了"Host derived evidence kind"的方向但不具体。当前 compaction material 的 `evidence_material` section 包含 tool result text、source text、accepted evidence material 混合内容，不同 kind 可能来自同一 material section。仅靠 section label 可能无法可靠派生 evidence_kind。更关键的是，如果 Host derivation 逻辑与 LLM 历史选择不一致，旧 compact artifacts（LLM 选择的 evidence_kind）与新 compact artifacts（Host 派生的 evidence_kind）之间会产生语义不一致。
- **Owner boundary**: Host compaction material builder → evidence material section → compact candidate evidence_kind。
- **Suggested fix**: S1 implementation shape 增加一条："在 S1 开始前，先确认 Host derivation 的可靠输入信号。至少列出 3 条候选方案：① 按 `evidence_material` block 的 `CompactMaterialBlockKind` 派生；② 在 compact material construction 时预标注 evidence kind 为 material block metadata；③ 保留 LLM-facing `evidence_kind` 字段但将其值域改为业务可读标签（如 `direct_tool_output`/`source_document_text`/`previously_accepted_fact`）。在 S0/S1 交界处由 implementer 选择并记录理由。"同时在 residual risk 中增加："Host derivation 与 LLM 历史选择的语义一致性风险——旧 compact artifacts 不做兼容迁移，按全新 schema 处理。"
- **Verification**: `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE`（`compaction.py:61`）已存在，可作为候选 derivation 信号。

### P1C-PLAN-MIMO-F06 — S2 三处 cancel hint 硬编码重复，plan 未要求一致性保障

- **Severity**: LOW
- **Blocking**: NO
- **Direct evidence**:
  - `dayu/fins/tools/fins_tools.py:80`: `_FINS_CANCELLED_HINT = "当前工具调用已停止；等待新的用户指令或后续调度。"`
  - `dayu/tools/doc_tools.py:71`: `_DOC_CANCELLED_HINT = "当前工具调用已停止；等待新的用户指令或后续调度。"`
  - `dayu/fins/tools/read_runtime_helpers.py:337`: `hint="当前工具调用已停止；等待新的用户指令或后续调度。"`
  - 三处硬编码了完全相同的"后续调度"文案（包括标点）。
- **Root cause**: 相同语义在 3 个模块中独立硬编码，违反"禁止每个消费者各自重建"原则。虽然 S2 会修改这些文案，但 plan 未要求抽取共享 cancel hint helper 或至少确保三处改写一致。
- **Owner boundary**: 各工具 callable owner 各自定义 cancel hint → 应有一个 shared tool cancel hint contract。
- **Suggested fix**: S2 implementation shape 增加一条："三处 `_CANCELLED_HINT` 的改写必须保持一致；优先抽取一个 shared `_tool_cancelled_hint()` helper 或常量到 `dayu.runtime`（仅限业务可读中性文本）。若暂时不抽取，implementation artifact 必须记录三处改写的一致性验证结果。"
- **Verification**: 当前三处文案完全相同（包括标点），确认是复制粘贴。

### P1C-PLAN-MIMO-F07 — S1 测试清单缺少 `test_run_input_builder.py` 的显式引用

- **Severity**: LOW
- **Blocking**: NO
- **Direct evidence**:
  - Plan 第 134 行 S1 files 列表: 包含 `tests/host/test_run_input_builder.py`。
  - Plan 第 241 行 validation commands: `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools` —— 包含 `test_run_input_builder.py`。
  - 但 S1 tests 部分（plan 第 146-148 行）只写了 "更新 compaction prompt/schema tests"、"更新 parser / contract tests"、"更新 compact material / run input tests"，未显式列出 `test_run_input_builder.py`。
- **Root cause**: S1 tests 描述使用了概括性语言（"compact material / run input tests"），未像 S2 tests 部分那样显式列出每个测试文件。虽然 validation commands 中包含了该文件，但 S1 tests 描述与 S1 files 列表之间存在对齐缺口。
- **Owner boundary**: 测试清单完整性。
- **Suggested fix**: S1 tests 部分增加 "`tests/host/test_run_input_builder.py`：确认 memory rendering 中 evidence_kind 渲染已清理"。
- **Verification**: S1 files 列表（第 134 行）和 validation commands（第 241 行）都包含该文件，只是 S1 tests 描述遗漏。

---

## Cross-cutting Observations

### 动机验证

Plan 的动机成立，且经过独立代码验证确认：
- Compaction prompt 确实要求 LLM 理解 `user_visible_run_state` 和 `evidence_kind=tool_source_text|accepted_evidence_material`（`conversation_compaction_user.md:16,40`）。✅
- Runtime 确实提供 Host-governance 默认 LLM 文案（`tool_call_projection.py:39-40`）。✅
- Fins tool outcome 确实含"未进入等待状态"（`download_tools.py:105,113`）。✅
- Cancel hint 确实含"后续调度"（三处硬编码）。✅

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
1. Durable compaction schema 变更 → 真实风险，compaction contract 涉及 `EvidenceBackedFactCandidateVNext` typed validation。✅
2. 字段仍必须暴露 Host governance → 真实风险，需确认没有上游缺失。✅
3. Runtime 公共 API 迁移不可控 → 真实风险（见 F04）。✅
4. Duplicate awaiting fanout 改写会改变 typed behavior → 真实风险，当前 AWAITING_FANOUT 直接返回 prior awaiting outcome，不受 message 影响。✅
5. rg 扫描命中大型 HTML → 已通过 `--glob '!**/*.html' --glob '!**/*.htm'` 缓解。✅

### Slice 可执行性

| Slice | 可执行 | 风险 |
|-------|--------|------|
| S0 | ✅ | 分类标准需要 litmus test（F03）；duplicate 非 AWAITING_FANOUT 路径需补充分析（F02） |
| S1 | ✅ | memory evidence_kind 需确定性措辞（DS F01 措辞优化）；Host derivation 方案需具体化（F05）；run_input 测试清单需补充（F07） |
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

但 DS 建议增加 P1-A contract 完整性验证是合理的：
```bash
source .venv/bin/activate && rg -n "accepted_result_projection\|AcceptedEvidenceEnvelope\|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
```
确认 P1-C 变更后这些 consumer 仍通过 P1-A helper 消费 accepted result projection。建议在 S3 validation 中增加此 scan。

### README Trigger 验证

Plan 的 README 决策完整：
- `dayu/host/README.md` ✅（compaction/material 变更）
- `dayu/fins/README.md` ✅（tool schema/outcome 变更）
- `dayu/config/README.md` ✅（prompt asset 变更）
- `tests/README.md` ✅
- 根 `README.md` → 正确不触发 ✅
- `dayu/README.md` → 正确不触发 ✅

### Umbrella Plan Slice 对齐

Umbrella plan 的 P1-C slice 结构（S0: wording classification, S1: Fins tool schema, S2: compaction prompt/schema, S3: runtime cancelled outcome）与实际 P1-C plan 的 slice 结构（S0: root-cause confirmation, S1: compaction schema, S2: tool/runtime text, S3: validation）不完全一致。这是合理的——umbrella plan 是高层指导，sub WU plan 在 root-cause confirmation 后按实际证据调整了 slice 切分。不构成问题。

### Residual Scan Noise Risk

Plan 的两条 baseline rg 命令中的 `poll` 和 `adapter` 模式会命中内部代码：
- `dayu/host/tool_runtime.py` 中 `_poll_*` 辅助函数
- adapter registry 相关代码

这些命中是预期的 internal-only 匹配。Plan 第 285 行正确分类为"allowed internal"。Implementation 时需确保不因 grep 噪音而误判为 leakage。

---

## Conclusion

**Verdict: pass**

P1-C plan 的动机基于当前代码直接证据且已验证，owner boundary 划分正确，slices 可执行且不过度耦合，stop conditions 覆盖真实风险。无 blocking findings。

DS review 的 F01（memory evidence_kind 渲染）经独立判断不构成 blocking：`run_input.py` 已在 S1 文件清单和 residual scan 覆盖范围内，plan 的条件判断措辞虽可更确定，但 implementer 在 S1 执行时必然发现并处理该路径。建议措辞强化，不需改变 plan structure。

7 个 non-blocking findings 可在 S0/S1/S2 implementation artifact 中自然解决，不需要改变 plan structure 或 slice ordering。

### Action Items for Plan Author

1. **[RECOMMENDED]** S1 implementation shape 第 4 条措辞强化：将"如果仍输出"改为"当前已确认在 `run_input.py` 中输出"，消除歧义。
2. **[RECOMMENDED]** S0 classification 增加 REUSE/HINT/HARD_STOP/REQUIRE_JUSTIFICATION/DURABLE_MISSING 的 LLM-facing 路径分析（F02）。
3. **[RECOMMENDED]** S0 增加"等待工具结果返回"分类的 litmus test 判据（F03）。
4. **[RECOMMENDED]** S2 增加 `ToolBusinessCancelled` fallback 路径分析（F04）。
5. **[RECOMMENDED]** S1 增加 evidence_kind Host derivation 的候选方案列举（F05）。
6. **[RECOMMENDED]** S2 增加三处 cancel hint 一致性要求（F06）。
7. **[RECOMMENDED]** S1 tests 描述增加 `test_run_input_builder.py` 显式引用（F07）。
8. **[RECOMMENDED]** S3 validation 增加 P1-A contract consumer 完整性 scan。
