# WU-SEMANTIC-OWNERSHIP-01 P1-C Plan

## 1. 目标 / 动机 / 严重性判断

目标：清理当前仍会进入 LLM 上下文或由 LLM 直接消费的 Host / ToolRuntime / runtime 治理术语，尤其是 compaction prompt、Fins tool schema / tool outcome、runtime cancelled outcome 默认文案，以及需要确认的 duplicate-governance message 暴露路径。

第一性原理判断：动机仍成立，但需要精确分级。

- 成立部分：LLM-facing 输入不能要求模型理解 Host wait、poll、adapter、run-state governance、internal evidence pipeline stage 或宿主取消治理。当前代码仍存在这些文本直接进入 prompt、tool schema 或 tool result 的路径。
- 严重性：P1 合理。该问题主要是 LLM-facing semantic drift 风险，不是 P0 durable correctness。它会让模型把治理状态当业务事实或行动依据，尤其在 compaction 与工具错误恢复中造成错误记忆、错误下一步或错误用户回复。
- 不能扩大：P1-C 不重写 P1-A 已建立的 accepted-result projection contract，不改变 P1-B typed lifecycle/cancel durable contract，不进入 P2-A CLI/Service、P2-B memory/test hardening 或 P2-C fallback prompt source-of-truth。
- 不能机械删除：“等待工具结果返回”只有在描述长事务工具结果稍后返回、并且不要求模型理解 Host wait id / poll / adapter / 状态机时，可以是业务可读行为说明。只有“等待状态 / 未进入等待状态 / 后续调度 / Host wait id / poll / adapter / user_visible_run_state / evidence_kind internal enum / 宿主取消 / 不要把本次取消视为业务失败”等才按治理泄漏处理。

成功信号：

- Compaction user prompt 不再要求 LLM 输入/输出 `user_visible_run_state`、`tool_source_text`、`accepted_evidence_material` 等内部治理或 evidence pipeline 枚举。
- Host compaction contract / parser / material builder 仍保留 typed validation，但 LLM-facing schema 只暴露业务可读、任务必要、自解释字段；如仍保留 source/type 字段，值必须是业务语义而非内部 pipeline stage。
- Fins awaiting tools 的失败 outcome、cancel hint 与 schema 文案不再出现“等待状态”“未进入等待状态”“后续调度”等治理词；“等待工具结果返回”按业务可读条件保留或轻微改写。
- `dayu.runtime.tool_call_projection.host_cancelled_outcome()` 不再由层中立 runtime 生成 Host-governance LLM-facing 默认文案；调用方必须提供业务可读 message / hint，或 runtime 仅提供中性、非 Host 语义的校验边界。
- Duplicate-governance message 路径被分类：若只进 trace/audit/internal diagnostic，记录为非 P1-C 必改；若能进入 tool outcome 或 LLM context，改写 LLM-facing message，不改变 duplicate typed contract。
- Targeted scan、focused tests、pyright、`git diff --check` 通过。

## 2. 当前直接证据

已用定向扫描核验，避免扫描大型生成/fixture 财报 HTML：

```bash
rg -n "等待工具结果|等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|evidence_kind|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
rg -n "duplicate|governance|等待工具结果|等待结果|等待状态" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

直接证据分类：

- `dayu/config/prompts/base/tools.md`：`start_fins_download` / `start_fins_preprocess` 写有“调用后等待工具结果；结果会说明...”。这是 prompt 中 LLM-facing 文本，但当前措辞只表达长事务工具结果稍后返回，没有出现 Host wait id、poll、adapter 或等待状态治理。按本 plan 分类为“允许保留或轻微业务化”，不能 blanket delete。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`：直接文档化输入 `trace_kind=user_visible_run_state`，以及输出 `evidence_kind=tool_result|tool_source_text|accepted_evidence_material`。该文件是 compactor user prompt，必然进入 LLM context；DS 05 / DS 06 仍真实存在。
- `dayu/host/compaction.py`：`TraceReadableKindVNext.USER_VISIBLE_RUN_STATE`、`FactEvidenceKindVNext.TOOL_SOURCE_TEXT`、`FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL` 仍是 vNext compact contract 字段；这说明 root cause 不只是 prompt 文案，而是 LLM-facing schema 与 Host typed enum 同名暴露。
- `dayu/host/run_input.py`：`_memory_evidence_fact_message()` 已确认把 `evidence_kind={fact.evidence_kind.value}` 渲染进 `SystemMessage`，fallback codec 路径也会渲染 `evidence_kind={evidence_kind}`。这是确定性 LLM-facing cleanup 项，必须在 S1 删除或改成业务可读文本；修复不得破坏 P1-A accepted-result projection helper。
- `dayu/runtime/tool_call_projection.py`：`_DEFAULT_HOST_CANCELLED_MESSAGE = "工具调用已被宿主取消。"` 与 `_DEFAULT_HOST_CANCELLED_HINT = "不要把本次取消视为业务失败；如仍需要结果，请在后续步骤重新发起请求。"` 仍由层中立 runtime 提供，MiMo 11 仍真实存在。
- `dayu/fins/tools/download_tools.py`、`upload_tools.py`、`preprocess_tools.py`：启动失败 outcome 中仍有“未进入等待状态”；这些 ToolFailedOutcome 会成为 tool result，被 LLM 直接消费。schema description 中“调用后等待工具结果返回”按业务可读分类，不作为必删项。
- `dayu/fins/tools/fins_tools.py`、`read_runtime_helpers.py`：cancel hint 仍含“等待新的用户指令或后续调度”；该 hint 会进入 ToolCancelledOutcome，是治理泄漏。
- `dayu/host/tool_duplicate_governance.py`：`DuplicateGovernanceMessages.awaiting_fanout` 默认文案为“相同工具请求已经进入等待状态；当前重复请求共享同一个等待结果。”。代码路径显示 `DuplicateDecisionKind.AWAITING_FANOUT` 在 `dayu/host/tool_runtime.py` 中直接返回 prior awaiting outcome；message 主要进入 duplicate decision / diagnostic JSON，而不是 governed failure outcome。但 REUSE / HINT / HARD_STOP / REQUIRE_JUSTIFICATION / DURABLE_MISSING 可能经 `_policy_decision_from_duplicate()` -> `_governed_failure_outcome()` 进入 `ToolFailedOutcome`；S0 必须逐类确认这些消息是合法 LLM-facing 行为指导还是治理泄漏。
- `dayu/host/tool_runtime.py` 中另有 `awaiting adapter binding is not configured`、`poll awaiting requires a durable external job ref`、`tool execution cancelled before completion` 等 governed failure message 可能进入 ToolFailedOutcome；它们不是原 accepted finding，但属于同一 residual scan，应在 S2 判断是否纳入同一 LLM-facing cleanup。
- `dayu/runtime/tool_call_projection.py` 的 `ToolBusinessCancelled` docstring 仍把 message 描述为可选并承诺 fallback 到 `host_cancelled_outcome()` 默认说明；Doc/Web tool cancellation message 仍含“宿主取消”，Doc/Fins cancellation hint 仍含“后续调度”。这些都属于 S2 scope。

Root cause：

- LLM-facing schema / prompt 与 Host internal typed enum 共用同一字段和值，导致模型被要求分类或复述内部治理阶段。
- Tool / runtime helper 在 owner boundary 错位：层中立 runtime 和 Fins tool outcome 直接生产 Host-governance 文案，而不是由业务 tool 或 Host projection boundary 生产业务可读说明。
- 部分 duplicate / ToolRuntime diagnostic message 的 LLM-facing 边界未被显式分类，导致同一 message 可能被误用为模型指令、tool result 或诊断。

## 3. LLM-facing Semantic Owner Boundary

| 语义族 | 首次产生 | 校验 | 持久化 / 诊断 | 投影 / 进入 LLM context | P1-C 修复边界 |
|---|---|---|---|---|---|
| Fins awaiting tool 行为说明 | Fins tool definition / prompt fragment | Tool schema construction tests；prompt scan | Tool schema snapshot / scene prompt asset | Engine `ToolSchema`、base tool prompt | Fins tool schema 与 config prompt；只保留业务可读“工具结果稍后返回”，禁止 Host wait 治理词 |
| Fins start failure / cancel outcome | Fins tool callable / read helper | Tool outcome contract；Fins tests | Tool result accepted EventLog / raw outcome | Tool message、accepted-result projection、memory/trace/run input | Fins tool owner 直接改 message/hint；不在 Host projection 下游掩盖 |
| Runtime host-cancelled default | `dayu.runtime.tool_call_projection` 当前默认 | Runtime helper tests | ToolCancelledOutcome | 各工具未传 message/hint 时进入 tool result | runtime 不拥有 Host-governance LLM text；改为要求调用方显式传业务可读文本，或提供中性 fallback 且 tests 禁止 Host 词 |
| Compaction trace kind | Host compact material builder / compaction contract | `dayu.host.compaction` parser/checker | `CONTEXT_COMPACTED` accepted candidate / compact artifact | `conversation_compaction_user.md` 的 input schema 与 compactor prompt | Host compaction owner 预分类为业务可读 section/field；prompt 不要求 LLM 理解 `user_visible_run_state` |
| Compaction evidence kind | Host compact material / compactor output parser | `EvidenceBackedFactCandidateVNext` typed validation | accepted compact candidate / memory projection | compactor output schema、accepted compact view、memory system message | 不让 LLM 输出内部 pipeline enum；如保留 typed enum，Host 自己派生，不由 LLM 选择 |
| Accepted-result query/status/source | P1-A `accepted_result_projection.py` | P1-A projection helper | EventLog / payload / memory | Trace、RunInput、CompactMaterial | 不改语义 owner；P1-C 只清理 LLM-facing 命名和值，不用 prompt 文案掩盖 projection contract |
| Terminal/cancel durable facts | P1-B lifecycle/cancel contract | P1-B durable transition / row codec | EventLog / `host_runs.cancel_request_event_id` | public HostEvent / diagnostics | 不改 durable contract；只清理 tool outcome/prompt 文案中的 Host-governance wording |
| Duplicate governance messages | `dayu.host.tool_duplicate_governance` policy | `DuplicateGovernanceMessages` validation | ToolTrace diagnostic / policy decision JSON | 可能的 governed failure outcome、trace/memory/compaction scan 待确认 | S0 先分类 context path；LLM-facing 则改写，internal diagnostic 可保留治理术语或另设 diagnostic-only message |

## 4. 非目标 / Stop Conditions

非目标：

- 不实现 P1-C；本文档只给 implementation plan。
- 不关闭 umbrella WU；P1-C 之后仍需 P2-A、P2-B、P2-C 与后续 full-repository deepreview。
- 不改 P1-A accepted-result typed projection 的 query/status/source/result truth。
- 不改 P1-B Host lifecycle/cancel durable schema 或 terminal/cancel truth。
- 不进入 CLI/Service boundary、memory/test fixture hardening、config fallback prompt source-of-truth。
- 不重构 Fins ingestion runtime、wait adapter、ToolRuntime fanout、poller、cancel watchdog 或 compaction orchestration。
- 不为旧 compact artifact / 旧 DB schema 增加兼容读取；若 schema 变更不可避免，按全新 schema 起库策略裁决。

Stop conditions：

- 发现 compaction prompt 字段清理必须改变 accepted compact durable schema，且 design truth 未先说明新 schema。
- 发现某个 LLM-facing 字段仍必须暴露 Host wait id、poll adapter、run state 或 evidence pipeline stage 才能完成任务；这说明上游 projection owner 缺失，应停下重新裁决。
- 发现 runtime `host_cancelled_outcome()` 已被大量外部公共调用依赖默认文案且无法在当前 slice 安全迁移；不得用兼容默认 Host 文案继续保留。
- 发现 duplicate awaiting fanout message 实际进入 LLM context，但改写会改变 fanout/reuse typed behavior；应拆出 Host duplicate governance WU，不在 P1-C 内重写行为。
- `rg` 扫描命中大型 HTML / generated fixture；必须收窄 glob，不能把 generated financial HTML 纳入人工审查噪音。

## 5. Implementation Slices

### S0. Root-cause Confirmation and Exposure Classification

Objective：在 implementation 开始时冻结当前直接证据、分类“业务可读等待说明”与“治理泄漏”，并确认 duplicate-governance message 是否进入 LLM context。

Files：

- 只读：`dayu/config/prompts/base/tools.md`
- 只读：`dayu/config/prompts/scenes/conversation_compaction_user.md`
- 只读：`dayu/host/compaction.py`
- 只读：`dayu/host/run_input.py`
- 只读：`dayu/host/tool_duplicate_governance.py`
- 只读：`dayu/host/tool_runtime.py`
- 只读：`dayu/runtime/tool_call_projection.py`
- 只读：`dayu/fins/tools/*.py`
- 产出 implementation artifact 中的 S0 分类表，不单独改代码。

Implementation shape：

- 运行 targeted scans，使用 `--glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'`。
- 分类每个命中项为 `llm-facing-must-fix`、`business-readable-allowed`、`internal-diagnostic-only`、`test-only`、`out-of-scope`。
- 对 duplicate-governance 路径列出当前 context path，不只覆盖 `AWAITING_FANOUT`。S0 分类必须逐一覆盖 `REUSE`、`HINT`、`HARD_STOP`、`REQUIRE_JUSTIFICATION`、`DURABLE_MISSING`：`DuplicateDecision.message` -> `_policy_decision_from_duplicate()` -> `_governed_failure_outcome()` -> `ToolFailedOutcome` -> accepted tool result / LLM tool message，并区分“合法 LLM-facing 行为指导”和“治理泄漏”。例如“请优先使用上一次工具结果继续推理”可以是业务可读行为指导；“等待状态 / wait id / poll / adapter / durable governance”才是 P1-C 必改治理泄漏。
- 对 `AWAITING_FANOUT` 单独列出 context path：`DuplicateGovernanceMessages.awaiting_fanout` -> `DuplicateDecision.message` -> `ToolRuntime._awaiting_fanout_record()` / diagnostic emitter / policy decision JSON / Tool Trace / RunInput / Memory。只有确认进入 LLM context 时才纳入 S2 改写。
- 对“等待工具结果返回”执行 litmus test：删除该文本后，模型是否会误以为工具同步返回或编造结果？若会，则该文本是任务必要的行为说明，可以保留或轻微业务化；若错误/失败语义已可由 `error`、message 或 outcome type 表达，例如“未进入等待状态”，则等待/治理词应删除或改写。

Tests：

- S0 不改代码，不跑测试；只记录 scan output 与分类依据。

Residual scan：

```bash
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

Stop condition：分类发现 accepted finding 已不存在或已全是 internal-only，应停止实施并让 controller 重新裁决 P1-C scope。

### S1. Compaction LLM-facing Schema Cleanup

Objective：让 compactor prompt 与 LLM output schema 不再要求模型理解 Host run-state governance 或 evidence pipeline internal enum，同时保持 Host typed validation 自洽。

Files：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `dayu/host/compaction.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/run_input.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`

Implementation shape：

- 将 prompt input 中 `trace_kind=user_visible_run_state` 改为业务可读、自解释的 trace category，例如“用户可见进展/结果摘要”，不得保留 run-state governance 命名。
- 将 prompt output 中 `evidence_backed_facts[*].evidence_kind` 的职责从 LLM 选择内部 pipeline enum 中移出。优先方案：LLM 输出只需要 `claim_text`、`evidence_labels`、`source_labels`；Host 在解析阶段根据 label 所属 material section 派生 typed evidence kind，或把 evidence kind 固定为 Host-owned internal value。
- 在修改 compaction schema 前必须选择并记录 evidence kind Host derivation 策略，不得把策略留给实现时临场猜测。候选策略至少包括：按 `CompactMaterialBlockKind` / material section 派生；在 compact material construction 阶段把 evidence kind 预标注为 Host-owned metadata；保留 LLM-facing source/type 字段但值域改为自解释业务标签，并通过 typed mapping helper 映射到 Host 内部 enum。implementation artifact 必须说明选择理由、可靠输入信号、为何不会让 LLM 继续输出 `tool_source_text` / `accepted_evidence_material`。
- 若实现选择保留一个 LLM-facing source/type 字段，该字段必须是业务可读值并在 prompt 中自足解释；Host 内部 enum 与 LLM-facing value 之间必须有一个 typed mapping helper，禁止让模型输出 `tool_source_text` / `accepted_evidence_material`。
- `dayu/host/run_input.py` 中 `_memory_evidence_fact_message()` 的 `evidence_kind={fact.evidence_kind.value}` 渲染，以及 fallback codec 的 `evidence_kind={evidence_kind}` 渲染，已确认进入 `SystemMessage`，必须作为确定性 LLM-facing cleanup 行动删除或改为业务可读文本。若 `MemoryEvidenceBackedFactKind` 只有单一业务含义且对模型无区分信息量，优先删除该字段；不得推迟到 P2-B 或仅在下游测试夹具掩盖。
- 不改变 P1-A `accepted_result_projection.py` 的 accepted tool result query/status/source truth；compact material 对 accepted evidence 的 query/result/source 仍消费 P1-A helper。
- 旧 compact artifacts 按本项目 schema 变更规则处理为全新 schema 起库，不新增兼容读取、兼容别名或兼容 parser 分支；如果 implementation 发现必须兼容旧 artifact，停止并回到 controller 裁决。

Tests：

- 更新 compaction prompt/schema tests，断言 prompt 中不出现 `user_visible_run_state`、`tool_source_text`、`accepted_evidence_material`。
- 更新 parser / contract tests，覆盖新 output schema 或 Host-derived evidence kind。
- 更新 compact material / run input tests，确认 accepted result query/source/result 仍从 P1-A projection 派生。
- `tests/host/test_run_input_builder.py` 必须明确覆盖 memory rendering：`_memory_evidence_fact_message()` 与 fallback codec 不再向 LLM-facing `SystemMessage` 渲染 `evidence_kind=...` 内部字段。

Residual scan：

```bash
source .venv/bin/activate && rg -n "user_visible_run_state|tool_source_text|accepted_evidence_material|evidence_kind=" dayu/config dayu/host tests/host --glob '!**/*.html' --glob '!**/*.htm'
```

Stop condition：移除 LLM `evidence_kind` 输出需要改变 durable compact payload schema，但 schema/design 决策不清。

### S2. Tool / Runtime LLM-facing Text Cleanup

Objective：清理 Fins tool schema/outcome、runtime host-cancelled helper、以及确认进入 LLM context 的 duplicate/ToolRuntime governed messages。

Files：

- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/runtime/tool_call_projection.py`
- `dayu/tools/doc_tools.py`
- `dayu/tools/web/web_tools.py`
- `dayu/host/tool_duplicate_governance.py`，仅当 S0 确认 message 进入 LLM context。
- `dayu/host/tool_runtime.py`，仅改 LLM-facing governed failure message，不改 behavior。
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/runtime/test_tool_call_projection.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/host/test_toolruntime_duplicate_governance.py` / `tests/host/test_toolruntime_executor.py`，仅当修改 duplicate/ToolRuntime 文案。

Implementation shape：

- Fins start failure message 将“未进入等待状态”改为业务可读启动失败说明，例如“下载任务未能启动” / “预处理任务未能启动”；hint 只给用户/模型可执行恢复建议，不提 Host wait state。
- Fins read / tool cancel hint 将“等待新的用户指令或后续调度”改为业务可读说明，例如“当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。”不得提“后续调度”。
- Tool schema description 中“调用后等待工具结果返回”按本 plan 分类为可保留；如果实现改写，应仅改为“工具结果返回后...”等业务可读表达，不删除长事务行为提示。
- `host_cancelled_outcome()` 默认 Host 文案必须移出 runtime。优先方案：`message` 与 `hint` 改为必填非空参数；所有调用点显式传入业务可读文本。若调用点过多，可提供 `cancelled_outcome(...)` 中性 helper，但不得包含“宿主取消”或“不要把本次取消视为业务失败”。
- `ToolBusinessCancelled` 必须纳入同一迁移：清理 optional message/hint fallback 与 docstring，不再承诺由 runtime 填充 Host-governance 默认说明；可改为必填非空 message/hint，或改成调用方直接构造业务可读 cancelled outcome。相关测试必须覆盖缺省行为或 fail-fast contract。
- 对 `dayu/tools/doc_tools.py`、`dayu/tools/web/web_tools.py`、Fins read tools 的调用点做显式 message/hint 审计，确保没有依赖 runtime 默认 Host 文案，并清理 Doc/Web cancellation messages 中的“宿主取消”以及 Doc/Web/Fins cancellation hints 中的“后续调度”。
- Fins / Doc / Web cancellation hint 改写必须保持一致。优先复用一个层中立、业务可读 helper 或 constant，但不得引入 Host governance 文案或让 `dayu.runtime` 反向依赖上层；若不抽取共享 helper/constant，implementation artifact 必须列出三处最终文案并做一致性审计。
- Duplicate awaiting fanout：若 S0 确认为 internal diagnostic-only，则不改默认文案，只在 implementation artifact 分类；若进入 LLM-facing tool outcome / RunInput / Memory，则把 message 改为业务可读，如“相同请求已有进行中的工具结果；请使用返回的同一结果继续推理。”不得出现“等待状态”。
- ToolRuntime governed messages 中如 `awaiting adapter`、`poll awaiting` 进入 ToolFailedOutcome，则改为业务可读系统能力说明；reason_code 可保留机器可读治理码，但 message/hint 不暴露 adapter/poll。

Tests：

- Fins ingestion tool schema/outcome tests 断言 no governance leakage。
- Runtime helper tests 断言默认 Host 文案不存在，缺 message/hint 按新 contract fail fast 或使用中性文本。
- Doc/Web/Fins tool cancellation tests 更新为显式业务可读 message/hint。
- Duplicate/ToolRuntime tests 只在 S0 分类命中 LLM-facing path 时更新。

Residual scan：

```bash
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|宿主取消|不要把本次取消视为业务失败|awaiting adapter|poll awaiting|tool execution cancelled before completion" dayu/fins dayu/runtime dayu/tools dayu/host tests --glob '!**/*.html' --glob '!**/*.htm'
```

Stop condition：runtime helper 签名改动触发跨包公共 API 不可控迁移；不得保留 Host-governance 默认文案，应停下裁决是否拆 slice。

### S3. Validation, README Decisions, Propagation Audit

Objective：完成全量 targeted scan、README 触发判断、propagation audit 与 residual-risk reconciliation。

Files：

- `dayu/host/README.md`，按触发规则检查后按需更新。
- `dayu/fins/README.md`，按触发规则检查后按需更新。
- `dayu/config/README.md`，按触发规则检查后按需更新。
- `tests/README.md`，按触发规则检查后按需更新。
- `docs/host/design.md`，仅当 implementation 改变 compaction public contract / LLM-facing schema design truth 时先更新。
- `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-codex.md`。

Implementation shape：

- 运行 baseline validation commands。
- 将 residual scan 命中逐项分类；允许 internal code/test 命中 `poll_interval_seconds`、adapter registry、Host design docs 等非 LLM-facing internal contexts，但不允许 LLM-facing prompt/schema/tool outcome 命中治理词。
- 增加 P1-A accepted-result projection contract preservation scan / validation：确认 `dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/memory.py` 等 consumer 仍使用或保留 P1-A accepted-result projection 真源，不在 P1-C 中重新推导 query/status/source/result，也不用 LLM-facing 文案替代 typed projection contract。
- README 决策必须按各 README 的 Agent 更新约束执行；只记录当前代码已实现的稳定事实，不写 WU 流水账。
- 输出 propagation audit，确认同一语义从产生、校验、持久化/诊断、投影到 LLM context 一致。

Tests：

- 运行下节 validation commands。

Residual scan：

- baseline 两条 `rg` 必须跑；命中项按 `allowed internal` / `test fixture` / `must fix` 分类。

Stop condition：任一 targeted scan 在 LLM-facing 文件或 tool outcome 路径中仍命中治理泄漏，且没有 owner / destination。

## 6. Exact Validation Commands

P1-C implementation 完成后必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
source .venv/bin/activate && rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
source .venv/bin/activate && pyright
git diff --check
```

预期：

- pytest 通过。
- 第一条 governance scan 在 LLM-facing prompt/schema/tool outcome 路径无未分类泄漏；internal runtime/config/tests 命中需在 implementation artifact 中解释。
- 第二条 duplicate/等待 scan 明确分类“等待工具结果返回”为业务可读或命中点已改写；duplicate governance message 若仍含治理词，必须证明不进入 LLM context。
- P1-A scan 确认 P1-C consumers 仍通过 accepted-result projection 真源消费 query/status/source/result；若命中显示重新推导，必须回到 S1/S3 修正。
- pyright 无新增或扩散错误。
- `git diff --check` 通过。

## 7. README / Design Trigger Decisions

- 修改 `dayu/host/`：必须读取并遵守 `dayu/host/README.md` Agent 更新约束。若只是内部文案 helper 清理且不改变 Host public contract，可记录“不更新”；若改变 compaction public contract / LLM-facing schema，则按当前代码事实更新 Host README 或先更新 `docs/host/design.md`。
- 修改 `dayu/fins/`：必须读取并遵守 `dayu/fins/README.md` Agent 更新约束。若仅改 tool schema/outcome 文案，通常不更新；若稳定边界“Fins 工具只暴露业务语义结果”需要补充当前实现事实，可按需更新。
- 修改 `dayu/config/`：必须检查 `dayu/config/README.md`。prompt asset 文案清理通常不改变 config 目录职责，可不更新；若 compaction prompt schema 字段变化属于配置资产稳定说明，按需补充。
- 修改 `tests/`：必须检查 `tests/README.md`。仅更新既有测试断言通常不更新；若新增测试层级或维护规则，才更新。
- 不触发根 `README.md`，除非用户可见 CLI / Web / workflow / 排障方式变化。
- 不触发 `dayu/README.md`，除非分层关系、装配方式或 `UI / Service / Host / Agent` 边界变化。

## 8. Propagation Audit Template

Implementation 完成前按下列模板填入 `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-codex.md`：

| 语义 | 产生 | 校验 | 持久化 / 诊断 | LLM-facing 投影 | 一致性结论 |
|---|---|---|---|---|---|
| Fins long-running tool result behavior | Fins tool schema / base prompt | schema tests / prompt scan | tool schema snapshot | ToolSchema + base tools prompt | “等待工具结果返回”是否仅为业务可读行为说明 |
| Fins start failure | Fins tool callable | outcome tests | ToolFailedOutcome / EventLog raw outcome | tool message / accepted-result projection | 是否不含“等待状态”治理词 |
| Fins/read cancellation | Fins tool/read helper | cancellation tests | ToolCancelledOutcome | tool message / projection | 是否不含“后续调度”治理词 |
| Runtime cancelled helper | runtime helper caller | runtime + tool tests | ToolCancelledOutcome | tool message | runtime 是否不再拥有 Host-governance default text |
| Compaction trace material | Host compact material builder | compaction contract tests | compact material payload | compactor user prompt | LLM 是否只看业务可读 trace category |
| Compaction evidence fact | Host parser / label mapping | parser/checker tests | accepted compact candidate / memory | compactor output schema / run input | LLM 是否不再分类 internal evidence pipeline stage |
| Duplicate governance | duplicate policy / ToolRuntime | S0 path classification | diagnostic / policy JSON / possible outcome | trace/run input/memory scan | 是否 internal-only；若 LLM-facing 是否已改写 |
| P1-A accepted-result projection | P1-A helper | existing projection tests | EventLog/payload/memory | trace/run input/compact | P1-C 是否未用文案掩盖 typed projection contract |
| P1-B lifecycle/cancel contract | P1-B helper / durable row | existing lifecycle tests | EventLog / run row | public HostEvent / diagnostics | P1-C 是否未改变 durable truth |

## 9. Residual Risk Handling

- 若 `evidence_kind` typed enum 仍需保留在 durable compact candidate 中，implementation artifact 必须说明它是 Host-owned persisted typed value，而不是 LLM 要分类的业务事实；同时确认其 LLM-facing rendering 不泄漏内部 enum。
- 若 duplicate `awaiting_fanout` 文案仅进入 Tool Trace diagnostic，当前 P1-C 可记录为 internal diagnostic residual，不强制改写；若将来 Tool Trace analyzer 把 diagnostic 直接投给 LLM，应由对应 analyzer WU 重新审计。
- 若 `poll` / `adapter` 在 tests 或 internal runtime docstring 中仍命中，必须分类为 internal-only；不得为清 grep 改内部精确术语。
- 如果 compaction schema cleanup 涉及 old artifacts，不做兼容迁移；按全新 schema 起库处理，除非 controller 明确追加兼容升级要求。
