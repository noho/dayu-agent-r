# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan

## 1. 目标 / 动机 / 成功信号

本 sub WU 的目标是为 Host accepted evidence / query / status / source 建立单一 typed projection contract，使 Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder 和 CompactMaterial 消费同一个 Host 投影真源，而不是各自回读 EventLog、各自写 fallback chain、各自过滤 internal source 或各自推断 result status。

第一性原理判断：动机仍成立，但 umbrella plan 中“完全没有 accepted evidence envelope”的部分已经过期。当前代码已经有 `AcceptedEvidenceEnvelope`、`TOOL_CALL_REQUESTED` request atom、`raw_tool_outcome` 和 digest 校验路径；真实剩余问题是这些 durable facts 仍没有统一的 accepted-result readable projection helper，导致同一 query/status/source 在多个消费者内重复重建。

成功信号：

- `TOOL_RESULT_ACCEPTED` 的 request/query、status、raw outcome、readable source 均可由一个 Host typed projection helper 产生。
- Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder、CompactMaterial 不再保留独立 query/status/source 推断逻辑。
- wait-resolution result 与普通 accepted result 使用同一 projection contract；不能从 `TOOL_AWAITING`、wait record、poll/runtime 状态反推 LLM-facing 业务语义。
- projection helper 对 missing request atom、digest mismatch、payload descriptor 缺失、source 不可读等情况给出同一 typed limited-signal 语义。
- focused tests、受影响 Host tests、pyright 和 `git diff --check` 通过。

## 2. 当前直接证据

执行的必扫命令：

```bash
rg -n "AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery|accepted_evidence|accepted evidence|_readable_query_text_from_envelope|_tool_result_query_text|_llm_facing_evidence_source_text|_tool_result_status|source_note|resolution_kind|tool_fact_kind|raw_tool_outcome" dayu/host tests/host
```

证据分类：

- producer：`dayu/host/tool_runtime.py` 写 `TOOL_CALL_REQUESTED` request atom 与普通 `TOOL_RESULT_ACCEPTED`；`dayu/host/waiting.py` 写 wait-resolution `TOOL_RESULT_ACCEPTED`。
- validator / envelope codec：`dayu/host/evidence.py` 定义 `AcceptedEvidenceEnvelope`、`AcceptedEvidenceToolQuery`、`accepted_evidence_envelope_from_payload()` 与 `accepted_tool_raw_outcome_text_from_payload()`。
- durable payload / payload descriptor：`dayu/host/tool_runtime.py` 的 `_tool_result_payload_plan()` / `_tool_result_payload()` 与 `dayu/host/_event_payload.py` 的 `tool_result_wait_resolution_payload()` 负责 hot/cold payload。
- projection helper：`dayu/host/compact_material.py` 的 `_readable_query_text_from_envelope()`、`dayu/host/durable/memory.py` 的 `_tool_result_query_text()`、`dayu/host/tool_trace.py` 的 `_tool_request_summary_from_tool_result()` / `_tool_result_status()`、`dayu/host/run_input.py` 与 `dayu/host/compact_pipeline.py` 的 `_llm_facing_evidence_source_text()`。
- Tool Trace：`dayu/host/tool_trace.py` 对 `TOOL_RESULT_ACCEPTED` 分别构造 request summary 与 result summary，并按 `resolution_kind -> tool_fact_kind -> raw_outcome.kind/result.ok` 推断 status。
- Read API：`dayu/host/read_api.py` 的 `_tool_result_accepted_activity()` 只读取 `outcome_kind`，再映射 activity status / severity；普通 accepted result canonical payload 的主字段是 `tool_fact_kind`，wait-resolution payload 同时含 `resolution_kind`。
- Durable Memory：`dayu/host/durable/memory.py` 为 memory projection 回读 request atom，但没有 semantic query 时直接返回 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。
- Conversation Memory：`dayu/host/memory.py` 消费 `event.evidence_query_text` 与 raw outcome，构造 selected recent evidence 文本。
- RunInputBuilder：`dayu/host/run_input.py` 对 accepted evidence block 再次过滤 source note，并在 resume wait fallback 中直接读取 `resolution_kind`。
- CompactMaterial：`dayu/host/compact_material.py` 回读 request atom；没有 semantic query 时回退到参数 JSON，和 durable memory 的 unavailable 降级不一致。
- CompactMaterial / compact pipeline source：`dayu/host/compact_material.py` 先把 opaque refs 拼成 `ref_kind:ref_id`，`dayu/host/run_input.py` 与 `dayu/host/compact_pipeline.py` 再用重复 blacklist helper 过滤 internal source。
- tests：`tests/host/test_memory_projection.py`、`tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_host_activity_event_projection.py` 等已有分散 fixture 和断言，需要随 production owner 迁移。

仍真实存在的 root cause：

- query 投影不是单一真源。`compact_material` 在无 semantic query 时回退到参数 JSON；`durable/memory` 在同类情况下返回 unavailable；`tool_trace` 有自己的 request summary 和 limited summary。
- status 投影不是单一真源。`tool_trace` 自己按多个字段和 raw outcome 推断；`read_api` 只看 `outcome_kind`；ordinary ToolRuntime canonical payload 使用 `tool_fact_kind`，wait-resolution payload 另有 `resolution_kind`。
- source 投影不是单一真源。source refs 先被拼成 source note 字符串，再由 RunInputBuilder / compact pipeline 用重复 blacklist 过滤；这把 business source 与 Host provenance 混在同一字符串里。
- raw outcome / payload descriptor 读取逻辑在多个消费者内重复存在，增加“trace 正确但 memory 错误”或“compact 正确但 run input 错误”的 drift 风险。

已过期或已部分修复的旧证据：

- accepted evidence envelope 已存在，不应再计划“从零新增 envelope”。
- wait-resolution result 已携带 envelope 与 raw outcome，不应再把修复落在 wait adapter 下游。
- Tool Trace 已能从 accepted result envelope 回到 request atom，不是完全缺少 request pairing；剩余问题是这套 pairing / fallback / status / source 没有成为共享投影契约。

## 3. Owner Boundary

- 产生事实：`dayu.host.tool_runtime` 的 accept barrier 产生普通 accepted request/result facts；`dayu.host.waiting` 在 resolve wait 时产生 wait-resolution accepted result facts。
- 校验事实：`dayu.host.evidence` 校验 envelope schema、producer event ref、digest/ref 结构；payload descriptor 读取 helper 校验 hot/cold payload ref 与 digest；新 projection helper 校验 request/result identity match。
- 持久化事实：Host EventLog 与 payload descriptor 是 durable truth；`TOOL_CALL_REQUESTED` 保存 LLM-safe request atom；`TOOL_RESULT_ACCEPTED` 保存 accepted evidence envelope、status fields、raw outcome、payload refs/digests。
- 投影事实：新 Host accepted-result projection helper 负责把 durable truth 改写为 business-readable query/status/source/result view；Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder、CompactMaterial 只消费该 helper。

修复不得落在：

- 单个消费者内的特例 fallback；
- UI / Service / CLI 展示层；
- tests fixture 的兼容分支；
- wait / poll / runtime 下游治理路径。

## 4. Selected Contract Approach

选择新增 sibling Host projection contract/helper，不扩展 `AcceptedEvidenceEnvelope` 本体。

理由：

- `AcceptedEvidenceEnvelope` 的现有模块 docstring 明确它描述事件、工具调用、digest 与不透明 refs，不复制 request / query 正文，也不解析业务 source / locator 语义。
- Host design 明确 accepted evidence envelope 是 provenance mapping，不应成为 lossy result preview 或事实内容容器。
- 当前 root cause 是多个消费者对同一 durable facts 的投影不一致；把派生文本写回 envelope 会混淆 durable truth 与 readable projection。
- 新 helper 能在不改 EventLog schema 的前提下统一 query/status/source/result 语义。若 implementation 发现必须新增 payload 字段或版本，按全新 schema 起库策略记录，不做旧库兼容读取。

建议新增模块：

- `dayu/host/accepted_result_projection.py`

建议 typed contract：

- `AcceptedToolResultProjection`：包含 `evidence_id`、`tool_name`、`query_text`、`query_state`、`status`、`result_text`、`result_details_text`、`readable_source_text`、`payload_refs`、`diagnostic`。
- `AcceptedToolResultStatus`：封闭状态值，例如 `completed`、`failed`、`cancelled`、`governed_error`、`lost`、`unknown`。状态由 payload 中的 Host accepted status fields 归一，优先级和 wait-resolution / ordinary result 映射只在 helper 内定义。
- `AcceptedToolResultQueryProjection`：封装 query 文本、来源为 semantic query / arguments summary / limited signal、以及 limited-signal reason。
- `AcceptedToolResultSourceProjection`：只暴露 business-readable source；internal refs 保留在 internal refs 字段或 diagnostic，不进入 LLM-facing 文本。

helper 输入建议为 `HostTransaction`、`EventLogStore` 或等价 read protocol、`TOOL_RESULT_ACCEPTED` row。接口应保持朴素，不引入 callback / factory / profile。helper 内部负责从 envelope 指向的 `TOOL_CALL_REQUESTED` request atom 读取 query 信息并校验 request/result identity；消费者不得直接调用 request atom back-query。identity mismatch、missing request atom、digest mismatch 和 payload descriptor 缺失不抛给消费者做分支判断，而是归一为 projection 的 typed limited-signal / `diagnostic`。

Tool Trace 分界选择窄方案：projection helper 只拥有 query/status/source/result truth；Tool Trace 可以保留 trace 专属的参数有界渲染、脱敏和展示格式 helper，但这些 helper 只能消费 projection 字段与已校验的 display-only 参数视图，不能重新拥有 accepted query/status/source/result 语义，不能直接回读 request atom 来决定 query/status/source。

Read API 分界选择迁移到 canonical `TOOL_RESULT_ACCEPTED` projection helper。`_activity_from_row()` 需要新增 canonical `TOOL_RESULT_ACCEPTED` 的显式分发边界：PREVIEW event class 仍按 preview payload 处理既有 activity，CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 通过 projection helper 产生 activity status / summary，二者不得在同一 row 上互相 fallback。`AcceptedToolResultStatus` 到 `HostActivityStatus` 的映射为：`completed -> COMPLETED`；`failed`、`governed_error`、`lost`、`unknown -> FAILED`；`cancelled -> CANCELLED`。`unknown` 代表 durable status fields 存在但无法映射到封闭状态，Read API 必须 fail closed 为 failed activity，而不是隐藏该 accepted result。

status 归一规则必须在 S1 先落成测试再迁消费者：

| durable signal | `AcceptedToolResultStatus` |
|---|---|
| wait-resolution `resolution_kind == "completed"` 或 ordinary `tool_fact_kind == "completed"` / success raw outcome | `completed` |
| wait-resolution `resolution_kind == "cancelled"` 或 ordinary cancellation field / cancelled raw outcome | `cancelled` |
| governance / policy / host-governed accepted error field | `governed_error` |
| wait-resolution `resolution_kind == "lost"`、payload descriptor 缺失、raw outcome 缺失且 envelope 指向的 accepted result 不可重建 | `lost` |
| ordinary failure field、raw outcome kind failure 或 `result.ok == false` | `failed` |
| status fields 存在但不属于已知允许值 | `unknown` |

status 字段优先级：先读 canonical accepted status fields（wait-resolution 的 `resolution_kind` 高于 ordinary `tool_fact_kind`），再读 raw outcome 的 kind/result.ok 作为同一 helper 内的降级依据；禁止消费者自行实现这条 fallback chain。Tool Trace 现有 `_tool_result_status()` 在 S2 中删除，或重构为只把 projection status 格式化为 Tool Trace 展示文本的 adapter；它不得继续读取 payload 字段推断 status。

`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 的 owner 迁移到 `accepted_result_projection.py`，作为 query typed limited-signal 的唯一定义；旧模块若仍需要该文案只能从 projection owner 导入。Conversation Memory 只能消费 projection `query_text` / `query_state`，不得根据 `event.evidence_query_text is None` 自行决定 fallback 条件。

## 5. 非目标

- 不改变 Engine tool protocol。
- 不改变 ToolRuntime accept barrier 的工具执行状态机。
- 不把 `TOOL_AWAITING`、wait record、poll adapter、runtime 状态投影成 LLM-facing 业务事实。
- 不为旧 schema / 旧 fixture 写兼容读取分支；历史缺字段只进入统一 limited-signal 或 fail closed。
- 不新增 UI / Service 级展示规则。
- 不把 source refs 的业务分类扩展成通用 provenance 平台；本轮只收敛当前 accepted evidence projection 需要的 source 语义。
- `InitialEvidenceMaterial` / `_evidence_blocks()` 不是 accepted-result projection owner，本轮不把它们改造成 EventLog accepted result 读取路径。它们只允许承载调用方已经提供的初始材料 readable query/source/result；若 S3 测试需要用 accepted tool result 构造 initial material，测试输入必须先经 projection helper 派生，不能在 fixture 内手写另一套 accepted query/source 语义。

## 6. Implementation Slices

### S1. Accepted Result Projection Contract

目标：新增 Host accepted-result projection helper，统一 envelope、request atom、raw outcome、query/status/source/result 读取与 limited-signal 语义。

允许文件：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py` 仅允许增加 projection 所需的窄 helper 或导出，不改变 envelope 职责。
- focused tests：`tests/host/test_accepted_result_projection.py`

允许改动：

- 从 `TOOL_RESULT_ACCEPTED` row 读取 digest-checked payload。
- 读取并校验 envelope 指向的 `TOOL_CALL_REQUESTED` request atom。
- 统一 query 降级：优先 semantic query；无 semantic query 时使用 bounded arguments summary；不可安全读取时返回 typed limited-signal。
- 统一 status 映射：ordinary canonical `tool_fact_kind` 与 wait-resolution canonical `resolution_kind` 映射到同一个 `AcceptedToolResultStatus`；PREVIEW `outcome_kind` 只保留在 Read API 既有 PREVIEW path，不作为 canonical projection truth。
- 统一 source 投影：把 accepted-result source readable 生产逻辑迁移到 projection helper；只输出 business-readable source，internal provenance refs 不进入 `readable_source_text`。`compact_material._readable_source_text_from_refs()` 对 accepted result 的使用必须被 helper 输出替代。
- 统一 raw outcome/result details 投影，复用 Tool Trace 现有 details 抽取规则或迁移为共享私有 helper。

完成信号：新 helper tests 覆盖 ordinary completed、failed/cancelled/governed_error、lost/unknown、wait-resolution completed/cancelled/lost、semantic query、arguments fallback、request atom 缺失、identity mismatch、payload descriptor、source filtering、unavailable query limited-signal 文案 owner。

### S2. Consumer Migration

目标：迁移全部下游消费者到 S1 helper，删除独立 back-query / fallback / blacklist / status inference。

允许文件：

- `dayu/host/tool_trace.py`
- `dayu/host/read_api.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/run_input.py`
- `dayu/host/compact_pipeline.py`
- 受影响 focused tests。

允许改动：

- Tool Trace 的 `TOOL_RESULT_ACCEPTED` query/status/source/result truth 由 projection helper 输入；Tool Trace 只保留 display-only 参数有界渲染/脱敏，不再直接回读 request atom 决定 query/status/source，也不保留 `_tool_result_status()` 的 payload fallback chain。
- Read API 在 `_activity_from_row()` 中新增 CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 分发，activity status / summary 由 projection helper 输入；PREVIEW path 不作为 canonical accepted result 的 fallback，不再只依赖 `outcome_kind` 声称覆盖 accepted result activity。
- Durable Memory 的 `evidence_query_text` 由 projection helper 输入，和 CompactMaterial 保持同一降级语义。
- Conversation Memory 只消费 projection view 提供的 query/result/source 文本；不再根据缺失字段自行使用 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。
- CompactMaterial 构造 accepted evidence block 时使用 projection view，不再私有回读 request atom；accepted-result source 不再经 `_readable_source_text_from_refs()` 生产 `source_note`。
- RunInputBuilder 删除重复 `_llm_facing_evidence_source_text()` blacklist 逻辑，改用 helper 已清洗的 readable source。
- Compact pipeline 的 accepted evidence source note 消费 projection helper 的 `readable_source_text`，删除 `_llm_facing_evidence_source_text()` 和 `_is_internal_evidence_source_part()` 独立实现。

完成信号：指定 consumer migration checklist 全部勾选；生产代码中不再出现消费者私有 `_readable_query_text_from_envelope`、`_tool_result_query_text`、重复 `_llm_facing_evidence_source_text`、`_tool_result_status` payload fallback chain、accepted-result `_readable_source_text_from_refs` 或 accepted-result `source_note` 生产逻辑。

### S3. Tests / Docs / Propagation Audit

目标：补齐 cross-consumer equivalence tests、README/design 决策和最终 propagation audit。

允许文件：

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_host_activity_event_projection.py`
- `dayu/host/README.md` 按触发规则检查后按需更新
- `tests/README.md` 按触发规则检查后按需更新
- `docs/host/design.md` 仅当 implementation 改变 public projection contract 或 durable schema 时更新

允许改动：

- 增加同一 accepted result 同时投影到 Tool Trace / Memory / RunInput / CompactMaterial 的等价性断言。
- 增加 source 不泄漏 internal refs 的断言。
- 增加 ordinary 与 wait-resolution status 映射一致性断言。
- 增加 Read API canonical `TOOL_RESULT_ACCEPTED` activity 分发断言，覆盖 `AcceptedToolResultStatus` 到 `HostActivityStatus` 的映射。
- 增加 grep / fixture 审计，确认 `InitialEvidenceMaterial` / `_evidence_blocks()` 没有被当作 accepted-result query/source owner；若测试经 initial material 表达 accepted tool result，输入必须来自 projection helper。
- 更新 README 或 design truth，只记录实际 contract 变化。

完成信号：validation commands 全部通过，README/design 触发结论已记录，propagation audit 无未分类 residual risk。

## 7. Allowed Files / Modules

默认允许：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py`
- `dayu/host/tool_trace.py`
- `dayu/host/read_api.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/run_input.py`
- `dayu/host/compact_pipeline.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_host_activity_event_projection.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/design.md`，仅在 public projection contract / durable schema 发生设计真源变化时允许。

不允许：

- `dayu/engine/`。
- `dayu/service/` / `dayu/ui/`。
- Fins storage / tool implementation。
- 测试私有 fixture 中保留旧语义兼容分支。

## 8. Consumer Migration Completeness Checklist

- [ ] Tool Trace：`TOOL_RESULT_ACCEPTED` query/status/source/result truth 由 projection helper 产生；trace 参数摘要只保留 display-only 有界渲染/脱敏。
- [ ] Read API：CANONICAL_FACT `TOOL_RESULT_ACCEPTED` activity status / summary 由 projection helper 产生；PREVIEW path 不冒充 canonical accepted result projection。
- [ ] Durable Memory：`evidence_query_text` 和 payload view 由 projection helper 产生。
- [ ] Conversation Memory：selected recent evidence 消费 projection query/result/source，不再自建 unavailable 文案或 fallback 条件。
- [ ] RunInputBuilder：accepted evidence content 消费 projection source，不再复制 blacklist source filter。
- [ ] CompactMaterial：accepted evidence block 消费 projection query/source/raw outcome，不再私有 `_readable_query_text_from_envelope()`，不再用 `_readable_source_text_from_refs()` 为 accepted result 生产 source note。
- [ ] Compact pipeline：accepted evidence source note 消费 projection source，不再复制 blacklist source filter。
- [ ] Initial material：`InitialEvidenceMaterial` / `_evidence_blocks()` 保持非 accepted-result owner；相关测试不得手写 accepted query/source 语义。
- [ ] Tests：全部 fixture 经同一 helper 或 production constructor 构造，避免测试侧各自重建 query/status/source。

## 9. Validation Commands

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py
source .venv/bin/activate && rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host
source .venv/bin/activate && pyright
git diff --check
```

预期：

- focused tests 通过。
- grep 只允许新共享 helper 内部命中 `tool_call_request_atoms`、status/query/source projection 私有函数或 non-accepted initial material 边界命中；消费者禁止命中旧私有 query/status/source helper、accepted-result `source_note` 生产、`_readable_source_text_from_refs` accepted-result 调用和 request atom back-query。
- pyright 无新增或扩散错误。
- `git diff --check` 无 whitespace 错误。

## 10. README / Design Update Triggers

- 修改 `dayu/host/` 必须检查 `dayu/host/README.md` 的 Agent 更新约束并按需更新。
- 修改 `tests/` 必须检查 `tests/README.md` 的 Agent 更新约束并按需更新。
- 如果新增 helper 只是把既有 Host design 中的 accepted evidence projection 代码化，`docs/host/design.md` 可不更新。
- 如果 implementation 新增 public projection contract、改变 `TOOL_RESULT_ACCEPTED` payload 字段、改变 EventLog schema version 或调整 source/status 设计语义，必须先更新 `docs/host/design.md`，再改 README / tests。
- 不触发根 README，除非用户可见 CLI / Web / workflow / 日志定位发生变化。

## 11. Stop Conditions / Residual Risks

Stop conditions：

- implementation 发现必须改变 EventLog schema 或 payload version，但设计真源尚未明确新 schema 起库策略。
- source refs 的业务可读分类无法从现有 `OpaqueEvidenceRef` 判断，且没有上游 producer contract 可安全补齐。
- Tool Trace / Memory / RunInput 对同一 projection 的预算截断需求冲突，无法用 shared projection + consumer-level bounded rendering 分层解决。
- 有消费者仍需要 wait / poll / runtime 状态才能解释 query/status/source；这说明 owner boundary 错，应停止重新裁决。

Residual risks：

- 当前 `source_refs` / `locator_refs` 生产路径大多为空；S1 可能只能先定义 source projection contract 和 no-leak behavior，业务 source 丰富度属于后续 source producer WU。
- Tool Trace 的 result details 抽取可能仍需 bounded rendering；该截断是 Tool Trace 展示策略，不应反向改变 projection truth。
- 如果 legacy EventLog fixture 缺 envelope / raw outcome，测试应迁移到新 production constructor；确需覆盖缺字段，只能断言统一 limited-signal 或 fail closed。

## 12. Propagation Audit Plan

实施完成前必须逐项确认：

1. 产生：ToolRuntime / waiting 是否仍同事务写入 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、envelope、raw outcome 和 status fields。
2. 校验：projection helper 是否校验 producer event ref、request atom event type、session/run/attempt/execution、tool call id、tool name、arguments digest、payload ref/digest。
3. 持久化：EventLog hot payload 与 payload descriptor 是否同源；projection 不写回 durable truth，不伪造缺失字段。
4. 审计 / Trace：Tool Trace hot/cold summary 的 query/status/result/source 是否只从 projection helper 派生；参数摘要是否仅为 display-only 有界渲染/脱敏。
5. Read API：CANONICAL_FACT `TOOL_RESULT_ACCEPTED` activity status / summary 是否只从 projection helper 派生；PREVIEW path 是否与 canonical path 有明确分发边界。
6. Durable Memory / Conversation Memory：evidence query/result/source 是否与 Tool Trace 使用同一 projection 语义。
7. RunInputBuilder：ordinary run input / resume wait input 是否不暴露 internal refs、digest、wait/poll/runtime 治理术语。
8. CompactMaterial / CompactMaterial to LLM compactor：accepted evidence material 是否不再独立回读 query、生产 accepted-result `source_note` 或 blacklist source。
9. Tests：cross-consumer equivalence tests 是否证明同一 accepted result 在 Trace / Memory / RunInput / CompactMaterial 中语义一致。
