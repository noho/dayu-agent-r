# WU-SEMANTIC-OWNERSHIP-01 Umbrella Plan

## 1. Umbrella goal / motivation / success signal

本 work unit 是 semantic ownership hardening umbrella，目标是关闭
`docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md` 中全部 accepted backlog findings，并在关闭既有 findings 后继续执行多轮 full-repository deepreview，直到新增 accepted findings 也被修复、re-reviewed、提交，或被明确分配给后续 owner / destination。

动机成立。直接证据显示多个核心事实仍存在单一真源缺失或下游重建：

- Engine Runner `finish_reason` 仍由 `RunnerContentCompletedData` 与 `RunnerDoneData` 双源携带；Agent mismatch 时仍保留 earlier `state.finish_reason`。
- Runner / Engine usage 事件仍不携带 `provider_request_id`，Host ingest 仍在 usage durable fact 中写 `None`。
- Fins preprocess / upload direct result 仍有 loose dict、重复成功规则和分散的 `ingest_method` 字符串。
- Host evidence/query/status、terminal event type、cancel linkage、LLM-facing 文本、CLI/Service、memory/test、config fallback prompt 等仍存在 partial owner drift 或需要确认的 residual drift。

成功信号：

- 8 个 sub WU 按顺序全部完成自己的 plan、plan review、implementation、code review、fix、re-review、accepted commit、验证矩阵、README 决策和 residual-risk reconciliation。
- 每个 sub WU 的修复落在语义 owner boundary 或直接上游输入校验处，不在下游展示层、测试夹具或单入口做特例。
- durable state、trace、memory、audit、UI 输出、LLM-facing prompt/schema 中同一业务事实可追溯到同一个 source-of-truth 或同一个 projection helper。
- 既有 accepted findings 全部关闭后，controller 继续多轮 full-repository deepreview；新增 accepted findings 也必须关闭或有明确 owner/destination 后，umbrella 才能 final closeout。

## 2. Non-goals / scope boundary

非目标：

- 本 plan gate 不实现、不修复、不 review、不提交、不 push、不创建 PR 或 GitHub Issue。
- 不把 8 个 owner 不同的 findings 合并成一次大改。
- 不做兼容旧 schema / 旧测试路径；涉及 schema 时按全新 schema 起库处理，除非后续 sub WU 明确要求升级兼容。
- 不引入新的 God object、跨层 facade、兼容性 re-export、兼容性 wrapper 或胶水 seam。
- 不改变 Dayu 的分层定位：`UI -> Service -> Host -> Engine`；`dayu.runtime` 仍是层中立基础设施包。
- 不用 deepreview 替代每个 sub WU 的直接代码证据确认；review artifacts 是 backlog 真源，不是 root cause 的唯一证据。

当前 plan artifact 允许写入范围仅为：

- `docs/host/wu-semantic-ownership-01-umbrella-plan.md`

## 3. Design document alignment

Host design 对齐点：

- Host 是 Run / Attempt lifecycle、取消、EventLog、durable facts、memory / context governance 与 projection 的 owner。EngineEvent 进入 Host 前不是 durable truth，必须经 Host ingest 校验 identity、state 和 event type 后才能影响 durable state。
- RunInputBuilder / memory / compact material 必须把 Host 内部 id、payload ref、digest、cursor、policy、dispatch 状态改写为 LLM-facing 自解释输入，不能把治理信息伪装成业务事实。
- Tool Trace、Outbox、Read Model、Conversation Memory 是派生视图，不能反向驱动 Run / Attempt 状态，也不能从等待、poll、cancel lifecycle 推断 LLM-facing 业务语义。
- Cancellation linkage、terminal event type、terminal status、accepted evidence/query/status 属于 Host durable contract 或 Host projection contract，不能由每个消费者各自定义或 back-query。

Engine design 对齐点：

- Runner 只表达 provider 调用边界的 RunnerEvent；Agent 才提升为 EngineEvent。Runner 不拥有 Agent 多轮、Host durable state、trace、memory、audit 或 prompt 渲染。
- `RunnerDoneData.finish_reason` 应表达本次 Runner 调用完成原因的最终裁定；中间 content completion 不应成为 finish reason 权威。
- `usage_reported` 是 provider usage 事实，若 provider request id 存在，应从 Runner 边界一路透传到 EngineEvent，再由 Host durable ingest 记录。
- Engine 可以描述 awaiting tool result 行为，但进入模型上下文的 tool schema / prompt 不能要求模型理解 Host wait id、poll adapter、runtime 状态或其它等待治理标识。
- Runtime config / Service assembly 应向 Engine 提供已解析 policy；Engine `AgentPolicy` 不应持有独立 LLM-facing fallback prompt 默认文本真源。

## 4. First-principles judgment

Umbrella WU 成立，因为这些 findings 不是单个文案或测试问题，而是同类失效模式：同一业务事实缺少单一 owner，导致下游消费者通过 back-query、fallback、blacklist、loose dict、重复字符串或默认值重建事实。此类问题一旦发生在 finish reason、usage、terminal、cancel、accepted evidence、memory 或 LLM-facing prompt 中，会形成“显示正确但 durable 错误”或“trace 正确但 memory 错误”的生产级风险。

必须拆成 sub WU，而不是一次大改。原因：

- 语义 owner 不同：Engine Runner authority、Fins business result、Host durable cancellation、Host projection、CLI/Service adapter、Runtime config 各自 owner boundary 不同。
- 验证矩阵不同：Engine 需要 Runner / Agent / provider parser parity；Fins 需要 direct/awaiting/job/upload/preprocess；Host durable 需要 schema/state/projection；LLM-facing 需要 prompt/schema/material scan；CLI/Service 需要 command behavior；Config 需要 assembly and policy construction。
- 回滚风险不同：P0-A 影响 Engine contract 与 Host usage facts；P1-B 可能涉及 durable schema；P1-C 可能涉及 compaction schema 和 prompt；P2-C 影响大量 `AgentPolicy(...)` 构造路径。
- 依赖顺序真实存在：P0-A 的 Engine contract 先于 Host usage durable facts；P1-A 的 accepted evidence contract 先于 P1-C 的 evidence/compaction文本清理；P1-B 的 terminal/cancel真源先于 P2-B memory/test hardening。

当前方案没有过度设计：每个 sub WU 只围绕一个语义闭环，默认 1 到 3 个 implementation slices；只有 schema、状态机、LLM-facing contract 或跨消费者 projection 需要时才拆 slice。计划不引入新平台层、不新增通用 registry、不用“以后可能”的抽象扩展当前问题。

## 5. Umbrella execution protocol

Controller 必须按以下顺序串行推进：

1. P0-A：Engine runner finish reason and usage authority。
2. P0-B：Fins preprocess/upload typed result contracts。
3. P1-A：Host accepted evidence/query/status typed projection contract。
4. P1-B：Host event type and cancellation durable contract。
5. P1-C：LLM-facing governance leakage cleanup。
6. P2-A：CLI/service boundary consistency。
7. P2-B：Memory/test contract hardening。
8. P2-C：Config fallback prompt source of truth。

每个 sub WU 必须独立完成：

- root-cause confirmation artifact，基于当前代码直接证据。
- sub WU plan artifact。
- plan review / fix / re-review artifact。
- implementation artifact，按 approved slices 执行。
- code review / fix / re-review artifact。
- accepted commit。
- validation matrix，包括受影响测试、pyright、`git diff --check`。
- README 决策。
- propagation audit。
- residual-risk reconciliation。

任何 sub WU 有 unclassified residual risk、accepted finding 未修复、re-review 未通过、schema/contract owner 无法裁决或验证失败，controller 必须停下裁决，不得进入下一个 sub WU。

Sub WU contract conflict handling：

- 若后续 sub WU 发现与已 accepted sub WU contract 冲突，controller 必须停下，不得在下游消费者、展示层、测试夹具或单入口用 workaround 掩盖冲突。
- controller 必须先确认是否需要更新设计真源；若设计真源缺失或与 accepted contract 冲突，先在对应 design doc 中写清事实 owner、校验者、持久化者和投影者。
- 裁决路径只能是二选一：为早前 accepted contract 新开 fix slice 并修改该 contract，或在当前 sub WU 中增加显式 typed mapping，把两个合法 contract 的语义边界写清。
- typed mapping 只能用于两个 owner boundary 都成立但 public contract 不同的情况；若上游 contract 本身错误，必须修上游，禁止下游 workaround。

## 6. Sub WU plans

### P0-A. Engine runner finish reason and usage authority

目标：

- 让 Runner done finish reason 成为唯一权威，消除 content-completed finish reason 双源竞争。
- 让 usage 在 Runner boundary 聚合并携带 `provider_request_id`，由 Agent 透传到 `UsageReportedData`，Host durable ingest 不再写硬编码 `None`。

Owner boundary：

- 产生事实：OpenAI-compatible Runner parser。
- 校验事实：Runner event contract / parser tests；Agent 只消费权威信号。
- 持久化事实：Host ingest `USAGE_REPORTED` / terminal closeout。
- 投影事实：Host usage diagnostic、Tool Trace / audit / read model 只消费 Host durable facts。

当前直接证据：

- `dayu/engine/contracts/runner_events.py` 中 `RunnerContentCompletedData.finish_reason` 仍存在，`RunnerUsageRecordedData` 无 `provider_request_id`。
- `dayu/engine/contracts/engine_events.py` 中 `ContentCompleteData.finish_reason` 和 `UsageReportedData` 仍无 `provider_request_id`。
- `dayu/engine/agent.py` 在 `RunnerDoneData` mismatch 时仍把 `finish_reason = state.finish_reason`。
- `dayu/engine/runners/openai/sse_parser.py` `_finalize_success()` 分别产出 content completed finish reason 与 done finish reason。
- `dayu/host/engine_ingest.py` usage payload / diagnostic 中仍有 `"provider_request_id": None`。

非目标：

- 不改变 Host 的 Run/Attempt 状态机。
- 不引入 provider-specific usage schema。
- 不让 Host 根据 content/tool calls 猜 finish reason。

预期 contract/schema/state/public-interface 变化：

- 默认 root-cause fix：从 `RunnerContentCompletedData` 和 `ContentCompleteData` 移除 `finish_reason`。
- `RunnerDoneData.finish_reason` / `IterationCompletedData.finish_reason` 是唯一 Runner-call completion authority；content-completed 事件只表达内容片段完成，不再携带或投影 finish reason。
- Agent-side overwrite 不是主路径，不能作为保留第二个非权威 `finish_reason` 字段的理由。
- P0-A implementation 前必须扫描 `ContentCompleteData.finish_reason` 与 `RunnerContentCompletedData.finish_reason` 的全部消费者。若发现 Engine Agent event bridge 或 parser/tests 之外的预期外生产消费者，controller 必须停下重新裁决 public contract 迁移，不得继续 implementation。
- `RunnerUsageRecordedData` 增加 `provider_request_id: str | None`。
- `UsageReportedData` 增加 `provider_request_id: str | None`。
- SSE parser 对 stream usage chunk 在 Runner boundary 聚合为一次 usage event；非流式 parser 也写入同一个字段。
- Host ingest 使用 `data.provider_request_id` 写 durable usage payload 和 diagnostic observation。

Allowed files/modules：

- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/host/engine_ingest.py`
- 受影响 Engine / Host tests。
- README 检查：`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`。

Implementation slices：

- S0 root-cause confirmation：运行消费者扫描，列出每个 `ContentCompleteData.finish_reason` / `RunnerContentCompletedData.finish_reason` 构造点与消费点，并确认没有预期外生产消费者；若有，停止让 controller 裁决。
- S1 finish reason authority：移除 content-completed finish reason 字段，Agent final decision 只使用 `RunnerDoneData.finish_reason`，更新 stream/non-stream parity tests。
- S2 usage identity propagation：Runner usage 增加 `provider_request_id`，SSE 聚合 usage，非流式透传，Agent -> EngineEvent -> Host ingest 全链路透传。
- S3 validation/doc sync：只在 S1/S2 contract 变化触发 README 时更新相关 README，并补充 propagation audit。

测试/验证命令：

- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_agent_phase3_tool_call.py`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace*.py`
- `source .venv/bin/activate && rg -n "ContentCompleteData\\(.+finish_reason|RunnerContentCompletedData\\(.+finish_reason|\\.finish_reason" dayu/engine dayu/host tests`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- 若移除/变更 Engine events 字段，必须检查并按需更新 `dayu/engine/README.md`。
- 若 Host usage durable payload 或 Tool Trace 语义变化，检查并按需更新 `dayu/host/README.md` 和 `tests/README.md`。

Residual risk：

- 非 OpenAI Runner 如有同类 event construction，implementation 前必须扫描确认；若不在当前代码路径，记录为 non-applicable 或 later owner。
- 如果消费者扫描发现预期外生产消费者，不得降级为 Agent-side overwrite；必须先由 controller 重新裁决 contract 迁移。

Stop condition：

- 发现第三方或 public contract 大量依赖 `ContentCompleteData.finish_reason` 且不能在本 sub WU 内安全迁移。
- usage 聚合需要改变 provider billing semantics，而非单纯取最终 usage。
- Host durable schema 需要新增列而不是 payload 字段传递。

### P0-B. Fins preprocess/upload typed result contracts

目标：

- 让 preprocess result summary 中 skipped / not-supported / failed / success 规则由一个 typed helper 表达。
- 让 upload pipeline 到 runtime 的结果从 loose `dict[str, JsonValue]` 收敛为 typed contract。
- 让 document source classification 的 `ingest_method` 使用单一 typed source-of-truth。

Owner boundary：

- 产生事实：Fins pipeline / ingestion runtime。
- 校验事实：Fins typed result dataclass / helper。
- 持久化事实：Fins storage repository meta / job store / direct result summary。
- 投影事实：Service direct stream、CLI rendering、awaiting wait adapter 只消费 typed summary。

当前直接证据：

- `FinsPreprocessResultSummary.skipped_count` 仍可包含 `not_supported_document_ids` 数量。
- `_produce_direct_preprocess` 与 `_run_preprocess_job` 仍重复 `processed_count == 0 and (...)` failure 判定。
- `FinsUploadRuntime._run_*_upload()` 返回 `dict[str, JsonValue]`，`_upload_summary_from_result()` 用 fallback helper 解析字段。
- `sec_upload_workflow.py` meta 中仍硬编码 `"ingest_method": "upload"`。
- `document_models.py` 中 `ingest_method: str = "download"` 与 `from_meta_dict()` fallback 仍使用裸字符串。

Root-cause confirmation 必做扫描：

- implementation 前必须运行 `rg "ingest_method" dayu/fins/`，把所有读写点归类为 pipeline producer、pipeline rebuild/filter、source upsert、storage serialization/deserialization、maintenance/read path、tests。
- allowed files 必须覆盖扫描结果中的全部生产读写点；若新增命中点不属于下列 allowed files，先更新 sub WU plan 或停下让 controller 裁决，不得只改已知路径。
- preprocess success/result helper 必须在 root-cause confirmation 阶段裁决为 boolean helper 或 typed status enum/helper，并列出 direct、job、awaiting、direct-stream consumers。
- root-cause confirmation 必须说明 JSON summary 是否新增 `not_supported_count`；若新增，列出 direct result、job record、awaiting result、CLI/Service rendering 的字段传播路径。

非目标：

- 不改变财报仓储目录布局。
- 不设计跨进程 durable Fins operation ledger。
- 不修改 Host wait-resume contract，除非 upload/preprocess summary 的 typed result 需要同步字段名。

预期 contract/schema/state/public-interface 变化：

- 引入或扩展 Fins-local typed result：例如 `FinsPreprocessOutcomeSummary` / `FinsUploadPipelineResult` / `FinsIngestMethod`，具体命名由 sub WU plan 按现有 Fins pattern 确认。
- `not_supported_count` 与 `skipped_count` 语义分离；`skipped_count` 只表达已支持但跳过。
- 提供单一 `preprocess_result_status(summary)`、`summary.is_successful()` 或等价 typed helper；返回类型必须由 root-cause confirmation 先裁决，direct/job/awaiting/direct-stream 均复用，禁止每个消费者重写成功规则。
- upload pipeline 返回 typed result，不允许 runtime 用 missing-field fallback 造出 `"unknown"` 或 `False`。
- `ingest_method` 的合法值由 Fins domain owner 定义，storage meta serialization/deserialization 只在 owner 边界转换字符串。

Allowed files/modules：

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_*` / `sec_download_*` 中由 `rg "ingest_method" dayu/fins/` 发现的其它必要文件。
- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/tools/read_runtime.py`
- Fins focused tests。
- README 检查：`dayu/fins/README.md`、`tests/README.md`。

Implementation slices：

- S0 root-cause confirmation：完成 `ingest_method` 全量扫描、preprocess helper 类型选择、direct/job/awaiting/direct-stream consumer 清单、JSON summary `not_supported_count` 决策。
- S1 preprocess summary/status：拆分 skipped/not-supported，抽取 success/failure helper，direct/job/awaiting/direct-stream/preprocess details 共用。
- S2 upload typed result：pipeline host `_build_result` 或 workflow output 改 typed contract，runtime summary 消费 typed result，删除 loose fallback helper。
- S3 ingest method source-of-truth：引入 Fins-local enum/constant helper，替换 `rg "ingest_method" dayu/fins/` 覆盖到的全部生产裸字符串读写点，保持 storage JSON 字段仍为业务可读值。

测试/验证命令：

- `source .venv/bin/activate && pytest tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py`
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
- `source .venv/bin/activate && rg -n "ingest_method" dayu/fins/`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- 修改 Fins business contract 或 direct stream result 时必须检查 `dayu/fins/README.md`。
- 修改 direct CLI/Service behavior 时检查 `tests/README.md`，如用户可见输出变更再检查根 README。

Residual risk：

- `ingest_method` 旧 meta 兼容不是当前目标；若现有测试依赖旧 meta，需要按全新起库规则更新测试。
- CN/HK/SEC 多 pipeline 的 source classification 可能有未覆盖路径，implementation 前必须用 `rg "ingest_method"` 全量核对。

Stop condition：

- 发现 upload pipeline result typed 化需要大规模重写 storage repository 协议。
- 发现 `not_supported` 在产品语义上确实应计入 skipped；需要 controller 裁决命名与用户可见语义。

### P1-A. Host accepted evidence/query/status typed projection contract

目标：

- 收敛 tool request query text、accepted result status、readable source text 的 Host projection 真源。
- 消除 trace / durable memory / run input / compact material 对同一 query/status/source 的独立 back-query、fallback chain 或 blacklist 过滤。

Owner boundary：

- 产生事实：Host ToolRuntime / waiting resolve 在 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED` accept boundary。
- 校验事实：accepted evidence/result envelope typed contract。
- 持久化事实：EventLog canonical payload / payload descriptor 中的 accepted envelope。
- 投影事实：Tool Trace、Conversation Memory、RunInputBuilder、Read API、compact material 从同一 typed projection helper 派生。

当前直接证据：

- 已有 `AcceptedEvidenceEnvelope`、`AcceptedEvidenceToolQuery`，说明 finding 已部分关闭。
- 但 envelope 当前仍只保存 request event ref、digest 等，未保存 resolved LLM-safe query text 或 status/source typed projection。
- `compact_material._readable_query_text_from_envelope()` 仍 back-query `TOOL_CALL_REQUESTED` atom。
- `durable/memory._tool_result_query_text()` 仍独立 back-query request atom。
- `run_input._llm_facing_evidence_source_text()` 仍用 internal prefix blacklist 过滤 source note。
- `tool_trace._tool_result_status()` 仍按 `resolution_kind -> tool_fact_kind -> raw_outcome.kind -> raw_outcome.result.ok` 多级 fallback 推断状态。

非目标：

- 不改变 Engine tool protocol。
- 不把 Host wait/poll lifecycle 暴露给模型。
- 不抢 P1-C 的 prompt / compaction 文案清理；本 sub WU 只建立 typed projection contract。

预期 contract/schema/state/public-interface 变化：

- 在 accepted evidence envelope 或 sibling accepted-result projection atom 中增加 typed fields：`readable_query_text`、`result_status`、`readable_source_text` 或等价结构。
- ToolRuntime / waiting resolve 在 accept 时从 request atom、raw outcome、source refs 生成这些 fields，并校验 digest/provenance。
- 提供单一 Host projection helper，供 Tool Trace、Memory、RunInput、CompactMaterial、Read API 消费。
- 下游消费者删除 request back-query、status heuristic chain 和 source blacklist，最多处理缺失 typed projection的 fail-closed diagnostic。

Allowed files/modules：

- `dayu/host/evidence.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/waiting.py`
- `dayu/host/engine_ingest.py` 中 accepted tool result payload helper。
- `dayu/host/tool_trace.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/compact_material.py`
- `dayu/host/read_api.py`
- Host tests covering ToolRuntime, waiting, memory, run input, compact material, read API, tool trace。
- README 检查：`dayu/host/README.md`、`tests/README.md`。

Implementation slices：

- S1 root-cause confirmation and contract choice：确认是扩展 `AcceptedEvidenceEnvelope` 还是新增 sibling typed projection atom。若涉及 EventLog schema payload version，记录全新 schema 策略。
- S2 producer-side typed projection：ToolRuntime / waiting accept 写入 typed query/status/source projection，并补 invalid/missing fail-closed tests。
- S3 consumer migration：Tool Trace / Read API / Durable Memory / Conversation Memory / RunInputBuilder / CompactMaterial 全部改读同一 helper，删除 back-query / blacklist / heuristic fallback。
- S3 completeness checklist：implementation artifact 必须逐消费者列出当前 fallback/back-query/blacklist 路径、替换后的 helper、覆盖测试和 residual risk。清单必须至少包含 Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder、CompactMaterial。
- 若 S3 上下文过大，允许拆为 S3a/S3b 等较小 semantic slices；拆分只能降低上下文压力，不能漏掉上述任一消费者。

测试/验证命令：

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_phase7_waiting_integration.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_tool_trace*.py tests/host/test_projection_read_model.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- Host README 中 accepted evidence / memory / trace / run input 说明需要按 contract 变化检查并更新。
- tests README 如新增或迁移 semantic memory / evidence tests，按职责更新。

Residual risk：

- 既有 EventLog payload 没有新 fields；按全新 schema 起库处理，不加兼容读取，除非 controller 明确要求。
- 如果 plan review 认为 envelope 不应膨胀，必须选择 sibling atom 并说明 source-of-truth 关系。

Stop condition：

- contract choice 会改变 durable schema 或 public Host API 且当前设计真源未覆盖。
- 发现某消费者确实需要不同语义，不应统一为同一 projection field。

### P1-B. Host event type and cancellation durable contract

目标：

- 收敛 Host terminal event type / terminal status / lifecycle set 的 source-of-truth。
- 把 `cancel_request_event_id` 从 `RUN_CANCELLING` JSON payload loose parsing 移到 typed durable state 或 typed indexed relation。

Owner boundary：

- 产生事实：Host admission / run transition。
- 校验事实：Host durable transition layer。
- 持久化事实：Host durable run state / EventLog / indexed relation。
- 投影事实：Outbox、Read Model、Tool Trace、Engine ingest、dispatch watchdog 只读同一 durable contract。

当前直接证据：

- `read_model.py`、`outbox.py`、`tool_trace.py`、`durable/outbox.py`、`engine_ingest.py` 等仍重复 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` 字符串。
- `outbox.py` `_TERMINAL_EVENT_TYPES` 包含 `RUN_LOST`，但 `_TERMINAL_STATUS_BY_EVENT_TYPE` 不含 lost，并通过 skip path 处理，需要核对 terminal set/public outbox semantics。
- `durable/run_transition.py` active cancel watchdog 仍读取 latest `RUN_CANCELLING` EventLog，再用 `_cancel_request_event_id_from_cancelling()` loose JSON parsing。
- `request_active_attempt_cancel_in_transaction()` 仍先把 `cancel_request_event_id` 写入 `RUN_CANCELLING` payload，再标记 run cancelling。

非目标：

- 不重新设计 cancellation UX。
- 不改变 Engine cancellation token contract。
- 不让 Outbox 把 `RUN_LOST` 错误投影成用户成功/失败/取消之一；controller 已裁决它不是 public outbox terminal item。

预期 contract/schema/state/public-interface 变化：

- 建立 Host-owned terminal event/status helper 或 constants module，供 projections 复用；不得是兼容 re-export。
- Controller design decision：`RUN_LOST` 是 Host terminal/lifecycle fact，不是 public outbox terminal item。Public outbox watermark 不应因 `RUN_LOST` 要求 outbox item。
- terminal helper 必须区分三类语义：Host terminal event set（包含 `RUN_LOST`）、public outbox terminal item event set（排除 `RUN_LOST`）、非 public terminal fact 的 explicit skip/diagnostic behavior。
- 若 `docs/host/design.md` 尚未写清上述区别，P1-B 必须先更新 design truth，再进入 implementation。
- Durable run state 新增 `cancel_request_event_id` 列或 typed indexed relation；mark cancelling 时写入并校验非空。
- Watchdog / engine_ingest / dispatch 直接从 RunRow 或 typed relation 读取 cancel linkage，不再解析 payload JSON 作为 critical link。

Allowed files/modules：

- `docs/host/design.md`，仅当 design truth 缺少 `RUN_LOST` terminal/public outbox 区分时允许先更新。
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/read_model.py`
- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/tool_trace.py`
- Host durable/projection/cancel tests。
- README 检查：`dayu/host/README.md`、`tests/README.md`。

Implementation slices：

- S0 design truth confirmation：检查 `docs/host/design.md` 是否明确 `RUN_LOST` 是 Host terminal/lifecycle fact 且不是 public outbox terminal item；若缺失，先更新 design truth。
- S1 terminal event/status contract：抽取 owner helper，替换 repeated terminal sets，覆盖 outbox/read model/tool trace/ingest tests，并确保 public outbox watermark 不因 `RUN_LOST` 要求 outbox item。
- S2 cancellation durable linkage：新增 typed durable field/relation，transition 写入和读取迁移，删除 loose payload critical parsing。
- S3 schema/test/doc sync：按全新 schema 起库更新 schema tests、cancel watchdog tests、README。

测试/验证命令：

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_open_host_runtime.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_projection_read_model.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- Durable schema / Host lifecycle / cancellation 变化触发 `dayu/host/README.md` 检查。
- Tests README 如新增 cancel lifecycle / schema coverage，按需更新。

Residual risk：

- `RUN_LOST` 不产生 public outbox terminal item是 controller 已裁决设计；剩余风险只在于 design truth 是否已经写清，若未写清必须先补 design。
- Schema 变更按全新起库；若当前工作区已有 DB 迁移需求，停下由 controller 裁决。

Stop condition：

- 发现 `cancel_request_event_id` 需要历史 workspace migration。
- 发现 terminal event set 与 public terminal notification set 在设计上冲突，且不能通过先更新 design truth 明确 owner boundary 后解决。

### P1-C. LLM-facing governance leakage cleanup

目标：

- 清理工具 schema、tool outcome 文本、compaction prompt/material 中面向 LLM 的 Host/Engine/runtime 治理泄漏。
- 保持 P1-A 建立的 evidence/query/status contract，不在文案层替代 contract 修复。
- 让 `dayu.runtime` 不再持有 Host-governance LLM-facing 默认文本。

Owner boundary：

- 产生 LLM-facing 文本：Fins tool schema/outcome、Host compact material/prompt rendering、runtime helper 调用方。
- 校验：对应 schema/prompt parser tests 和 prompt smoke。
- 持久化/投影：Host / ToolRuntime / compactor material 仅投影业务可读语义。

当前直接证据：

- Fins preprocess/upload failed outcome 文本仍含“未进入等待状态”。
- base tools prompt 仍含“调用后等待工具结果”；此短语在 Engine design 中可接受，但 implementation 必须区分“等待工具结果返回”与“等待状态/Host wait治理”。
- duplicate-tool/governance outcome 文本可能包含“等待状态”等治理语义；P1-C 必须确认这些消息是否进入 LLM context。
- `conversation_compaction_user.md` 仍要求 LLM 输出 `evidence_kind=tool_result|tool_source_text|accepted_evidence_material`，并输入 `trace_kind=user_visible_run_state`。
- `dayu/runtime/tool_call_projection.py` 中 `host_cancelled_outcome()` 默认 message/hint 仍写“宿主取消”“不要把本次取消视为业务失败”。

非目标：

- 不改变 P1-A accepted evidence contract。
- 不让模型理解 Host wait id、poll adapter、runtime state、EventLog id、payload ref、digest。
- 不把所有“等待工具结果”字样机械删除；只删除或改写会让模型承担 Host治理判断的文本。

预期 contract/schema/state/public-interface 变化：

- LLM-facing waiting wording boundary：业务级“等待工具结果返回”只可用于描述长事务工具会稍后返回结果的模型可见行为；治理级“等待状态”“未进入等待状态”“后续调度”、Host wait/poll/adapter 术语、Host-governance default text 不得进入 LLM-facing 文本。
- P1-C 必须扫描 prompt/config、tool schema/outcome helper、duplicate-tool/governance messages，并明确分类哪些文本进入 LLM context；若 duplicate-tool/governance messages 会进入 LLM context，必须按治理泄漏处理。
- Fins tool schema/error/hint 改为业务动作与业务结果描述，不出现“等待状态”“后续调度”等 Host治理概念。
- Compaction prompt 输出 schema 不再要求 LLM 判断内部 pipeline `evidence_kind`；Host 预标注或在 accept 时派生 evidence kind。
- `trace_kind=user_visible_run_state` 改为业务可读类别，或由 Host 在 material construction 中转换为模型不需理解的 label。
- `host_cancelled_outcome(message, hint)` 改为必填，runtime 不提供 Host-governance LLM-facing 默认文本；调用方在自身层级提供业务文本。

Allowed files/modules：

- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/config/prompts/base/tools.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/run_input.py`
- `dayu/runtime/tool_call_projection.py`
- Related prompt/schema/material tests。
- README 检查：`dayu/config/README.md`、`dayu/fins/README.md`、`dayu/host/README.md`、`tests/README.md`。

Implementation slices：

- S0 LLM-facing wording classification：列出“等待工具结果返回”保留条件、治理级 waiting 禁止词、duplicate-tool/governance messages 是否进入 LLM context。
- S1 Fins tool schema/outcome wording：清理等待治理泄漏，保留业务结果和用户下一步。
- S2 compaction prompt/schema ownership：Host 预标注 evidence/trace readable category，LLM output schema 删除内部 pipeline enum 或改为业务自解释字段。
- S3 runtime cancelled outcome owner：`host_cancelled_outcome` message/hint 必填，调用方补齐层内业务文本。

测试/验证命令：

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools`
- `source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests`
- `source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- Prompt schema 变化触发 `dayu/config/README.md` 检查。
- Tool schema/outcome 变化触发 `dayu/fins/README.md` 检查。
- Compaction material 变化触发 `dayu/host/README.md` 和 `tests/README.md` 检查。

Residual risk：

- Compaction schema 改动可能影响 fake compactor / smoke fixtures；测试必须按新 LLM-facing contract 更新，不在生产代码保留旧 schema兼容。
- “等待工具结果”是否允许必须按 Engine design 裁决，不作为 blanket violation。

Stop condition：

- 删除 `evidence_kind` 需要改变 memory durable schema 或 existing compact artifact parser。
- 清理文案会降低模型完成工具调用任务的自解释能力。

### P2-A. CLI/service boundary consistency

目标：

- 让 `session resume` 不导入 prompt/interactive 私有函数，改用 Service-owned或CLI public narrow entrypoint。
- 让 Fins direct missing RESULT contract 只在 Service 层兜底；CLI 收到正常结束无 RESULT 应视为 contract violation，而不是自己合成 fallback。
- 收敛 HostApiError formatting / exit code mapping。

Owner boundary：

- 产生业务流程：Service entrypoint runtime / Fins direct service。
- CLI：只负责参数、输出、SIGINT、本地 exit code 映射。
- Host API error：Host public API 产生，CLI shared renderer / mapper 投影。

当前直接证据：

- `dayu/cli/commands/session.py` 直接导入 `_execute_prompt_on_existing_session`、`_prepare_prompt_existing_session_execution`、`_execute_interactive_on_existing_session`、`_prepare_interactive_existing_session_execution` 等私有函数。
- `dayu/service/fins_direct.py` 已有 `_ensure_result_event()` 合成 missing RESULT failure。
- `dayu/cli/commands/fins.py` `_consume_fins_direct_events()` 结束无 result 时仍调用 CLI 本地 `_missing_result_event()`，重复 Service contract。
- `session.py` 内部仍有 `_host_error_context` / `_exit_code_for_host_error` 等本地映射，需确认是否与 prompt/interactive/main 分散格式重复。

非目标：

- 不改变 CLI 用户命令语法，除非移除错误 fallback 后错误消息必须更新。
- 不把 Service 变成 CLI output renderer。
- 不让 CLI 读取 Host durable internals。

预期 contract/schema/state/public-interface 变化：

- 默认采用 Service-owned existing-session execution helper 承载 prompt/interactive resume 的共享 submit/watch/session execution 语义。
- CLI 保留参数解析、终端渲染、SIGINT、本地 exit code 映射和 command-specific output；Service helper 不接收或生成 CLI display concerns。
- 只有 root-cause confirmation 证明复用逻辑纯属 UI/rendering，且下沉 Service 会泄漏 CLI display concerns 时，才允许选择 CLI-public narrow helper；该例外必须由 controller 裁决后写入 P2-A sub WU plan。
- CLI Fins direct event consumer 删除 `_missing_result_event()` fallback；若 iterator 结束无 result，抛 `RuntimeError` 或 CLI usage/runtime error，暴露 Service contract violation。
- HostApiError formatting / exit code 提供单一 CLI helper，session/prompt/interactive/purge 复用。

Allowed files/modules：

- `dayu/cli/commands/session.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/output.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/fins_direct.py` only if Service public helper needs tightening。
- CLI/Service tests。
- README 检查：root `README.md` if user-visible CLI behavior changes; `dayu/service/README.md`; `tests/README.md`。

Implementation slices：

- S0 root-cause confirmation：确认复用逻辑属于 Service execution 语义还是 CLI rendering；默认选择 Service-owned helper，除非 controller 接受 CLI-public exception。
- S1 session resume Service boundary：replace private imports with Service-owned helper, preserve behavior tests.
- S2 Fins direct missing RESULT boundary and HostApiError helper：remove CLI fallback, centralize error formatting/exit code if duplication confirmed.

测试/验证命令：

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_interactive_command.py tests/cli/test_interactive_run_view.py tests/service/test_fins_direct.py tests/service/test_entrypoint_runtime_interactive_path.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- CLI visible failure text/exit code change requires root README check.
- Service helper boundary change requires `dayu/service/README.md` check.

Residual risk：

- Private functions may currently be narrow but not exported by design. Default path is Service entrypoint helper; CLI-public helper requires evidence that the helper is pure UI/rendering and Service extraction would leak display concerns.

Stop condition：

- Public entrypoint extraction requires broad CLI command architecture redesign.
- Existing tests assert CLI fallback as intended product behavior; controller must裁决 Service vs CLI owner。

### P2-B. Memory/test contract hardening

目标：

- 强化 import-boundary tests，使 relative imports 也被检查。
- 确认并关闭 memory projection / run_input / compact material 的 final-answer continuity、accepted evidence query/source/status residual drift。
- 清理测试中裸 pending digest 或 synthetic placeholder pattern，确保 tests 不训练生产代码保留无效兼容。

Owner boundary：

- Import boundary owner：tests enforce architecture contract。
- Final-answer continuity owner：Host terminal ingest / `_terminal_answer` helper。
- Memory / RunInput / Compact material owner：只消费 accepted canonical facts 或 typed projection。
- Test fixtures owner：测试必须跟随生产 contract，不得伪造“合法 pending digest”。

当前直接证据：

- `tests/runtime/test_import_boundary.py` 与 `tests/host/test_import_boundary.py` 的 `_imported_module_names()` 只在 `node.level == 0` 时记录 `ImportFrom`，relative import 未覆盖。
- `dayu/host/_terminal_answer.py` 和 `dayu/host/terminal_payload.py` 已存在 final-answer continuity helper，说明 MiMo 08 已部分关闭。
- `dayu/host/durable/memory.py` 和 `dayu/host/run_input.py` 仍会把 descriptor-backed terminal artifact content transient hydrate 成 `final_answer`，实施前需确认这是否仍是 accepted finding，还是已由 helper/documented boundary 修复。
- 未找到精确 `snapshot_digest="pending"` 模式；但存在 snapshot digest integrity tests 与 manual corruption tests，implementation 前必须二次确认该 finding 是否 obsolete。

Root-cause confirmation 必须先产出 finding status table：

- 每个 P2-B finding 的状态只能是 `active`、`obsolete-with-evidence`、`needs-design-update` 或 `deferred-with-owner`。
- `active` finding 才进入 normal implementation/review/fix/re-review closure。
- `obsolete-with-evidence` finding 可通过 controller-accepted confirmation artifact 做 no-code/no-commit pass 关闭，禁止为了制造实现痕迹而假改生产代码或测试。
- `needs-design-update` 必须先更新设计真源；`deferred-with-owner` 必须写清 owner/destination，不得作为 silent skip。

非目标：

- 不重新设计 Conversation Memory。
- 不把 failed/cancelled/lost diagnostic 文本变成 assistant final answer。
- 不为旧 fixture 保留 production compatibility。

预期 contract/schema/state/public-interface 变化：

- Import-boundary helper 必须 resolve relative import 到绝对 module name，再匹配 forbidden prefixes。
- Final-answer continuity 若仍有 drift，应收敛为单一 helper；如果当前 helper 已满足设计，则将 finding 标记为 obsolete/closed-with-evidence，不做无意义改动。
- Tests 中 placeholder digest 必须替换为真实 `sha256_digest_json(...)` 或合法 fixture builder。

Allowed files/modules：

- `tests/runtime/test_import_boundary.py`
- `tests/host/test_import_boundary.py`
- `tests/contracts/test_import_boundary.py` if same relative-import blind spot exists。
- `dayu/host/_terminal_answer.py`
- `dayu/host/terminal_payload.py`
- `dayu/host/durable/memory.py`
- `dayu/host/run_input.py`
- Relevant memory/run input tests。
- README 检查：`tests/README.md`、`dayu/host/README.md` if contract changes。

Implementation slices：

- S1 import-boundary test hardening：relative import resolution helper and regression fixtures.
- S2 memory/final-answer/test fixture audit：先产出 finding status table；仅修 `active` drift；`obsolete-with-evidence` 走 controller-accepted confirmation artifact；replace invalid placeholder digest patterns if found.

测试/验证命令：

- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/host/test_import_boundary.py tests/contracts/test_import_boundary.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`
- `source .venv/bin/activate && rg -n "snapshot_digest\\s*=\\s*[\"']pending[\"']|pending digest|final_answer.*artifact" tests dayu/host`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- Import-boundary coverage change should update `tests/README.md` if it changes documented boundary tests.
- Host README only if final-answer continuity contract changes.

Residual risk：

- Some findings may be obsolete due to recent fixes. Controller must use the finding status table to distinguish no-code closure from active implementation, rather than force churn.

Stop condition：

- Current helper design conflicts with review finding, but design docs endorse helper behavior.
- Relative import resolution would require package discovery beyond `dayu` roots and risk false positives.

### P2-C. Config fallback prompt source of truth

目标：

- 消除 runtime config 与 Engine `AgentPolicy` 的 fallback / continuation prompt 默认文本双真源。
- 让 assembly boundary 明确提供 resolved prompt values，Engine contract 不自带独立 LLM-facing默认文案。

Owner boundary：

- 产生默认值：runtime config / execution profile。
- 校验默认值：runtime config loader / assembly helper。
- 消费默认值：Service assembly 构造 `AgentPolicy`。
- Engine：只接收 typed `AgentPolicy`，不定义 LLM-facing fallback prompt默认文本。

当前直接证据：

- `dayu/runtime/config_loader.py` 定义 `_DEFAULT_FALLBACK_PROMPT` 与 `default_fallback_prompt()`。
- `dayu/engine/contracts/agent_policy.py` 定义 `_DEFAULT_FALLBACK_PROMPT`、`_DEFAULT_CONTINUATION_PROMPT`，并在 dataclass 字段上使用默认值。
- `dayu/runtime/assembly.py` 仍通过 `code_default.fallback_prompt` / `code_default.continuation_prompt` 作为 fallback source。
- `dayu/service/host_assembly.py` 多处构造 `AgentPolicy(...)`，大多显式传入 prompt，但 tests 里仍有直接构造路径。

Root-cause confirmation 必做扫描：

- P2-C 必须先运行 `rg "AgentPolicy\\(" dayu/ tests/`，并按 owner layer 分类构造点：Engine contract/tests、Runtime assembly/config、Service assembly、Host/CLI assembly 或 fixtures、tests。
- Engine 不得 import runtime config、config loader 或 execution profile 来恢复默认 prompt；Engine 只接收调用方传入的 prompt。
- production 和 tests 都必须从所属 assembly/fixture boundary 显式传入 prompt，不允许 test-only default helper、compatibility wrapper、兼容性 re-export 或 `AgentPolicy()` fallback。

非目标：

- 不改变 fallback/continuation 文本内容，除非 runtime config 真源要求。
- 不把 Engine 反向依赖 runtime config。
- 不引入 callback/factory/profile over-design。

预期 contract/schema/state/public-interface 变化：

- `AgentPolicy.fallback_prompt` 和 `AgentPolicy.continuation_prompt` 改为必填字段，保留非空校验。
- Runtime assembly 的 code default 不再来自 Engine `AgentPolicy()` 默认；必须来自 config loader / explicit assembly input。
- 所有 production and test `AgentPolicy(...)` 构造路径从所属 assembly/fixture boundary 显式传入 prompts。
- `AgentPolicy()` 缺少 prompt 时应 TypeError。

Allowed files/modules：

- `dayu/engine/contracts/agent_policy.py`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/assembly.py`
- `dayu/runtime/scene_prepare.py`
- `dayu/service/host_assembly.py`
- Tests with direct `AgentPolicy(...)` construction。
- README 检查：`dayu/engine/README.md`、`dayu/config/README.md`、`dayu/service/README.md`、`tests/README.md`。

Implementation slices：

- S0 root-cause confirmation：运行 `rg "AgentPolicy\\(" dayu/ tests/`，按 layer 分类构造点，并确认 Engine 无 runtime config/config loader 依赖路径。
- S1 contract and assembly update：make Engine prompt fields required, update runtime/service assembly to pass resolved values.
- S2 test migration and docs：update direct AgentPolicy fixtures, assert missing prompt TypeError, README checks.

测试/验证命令：

- `source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host`
- `source .venv/bin/activate && rg -n "AgentPolicy\\(" dayu/ tests/`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Docs / README 决策：

- Engine README must reflect `AgentPolicy` receives resolved prompt values.
- Config / Service README must reflect execution profile prompt source-of-truth if not already stated.

Residual risk：

- Many tests directly construct `AgentPolicy`; migration is mechanical but broad. Do not add test-only defaults, compatibility wrappers, or Engine-side runtime config imports.

Stop condition：

- A public API promises `AgentPolicy()` can be constructed without prompts.
- Runtime assembly cannot identify a single default source without changing config schema.

## 7. Sub WU dependencies and handoff

- P0-A precedes P1/P2 Host work because Host durable usage and terminal facts must consume corrected Engine events.
- P0-B is independent from Engine but should finish before P1-C Fins tool schema cleanup, so Fins result wording can reference typed result semantics.
- P1-A precedes P1-C because compaction / evidence wording cleanup must not paper over missing accepted evidence typed contract.
- P1-B precedes P2-B because memory/test hardening should test final durable terminal/cancel semantics after event/cancel truth is centralized.
- P2-A can run after P1-C, because CLI/Service boundary should not be mixed with Host/LLM-facing contract cleanup.
- P2-C last because making `AgentPolicy` prompts required touches many tests; doing it after semantic owner fixes reduces rebase churn.

Handoff format after each sub WU:

- sub WU id and title。
- accepted plan artifact path and commit。
- implementation slice artifacts and accepted commits。
- code review / re-review artifacts and final finding states。
- validation commands and pass/fail summary。
- README decision。
- propagation audit summary。
- residual risks classified as fixed / later approved slice / later WU / existing issue / requiring decision。
- next sub WU entry condition。

## 8. Full-repository deepreview phase

After P0-A through P2-C are accepted, controller must not close WU-SEMANTIC-OWNERSHIP-01. It must enter additional full-repository deepreview rounds:

1. Each round dispatches at least AgentMiMo and AgentDS over the full repository, not only changed files.
2. Produce durable review artifacts under `docs/reviews/`.
3. Minimum review dimensions: Engine contracts、Host durable truth、Host projections、Fins contracts、CLI/Service boundary、LLM-facing text、config/prompt、tests/import-boundary coverage。
4. Controller adjudicates every finding as accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence。
5. Accepted current-umbrella findings become new sub WUs or slices under this umbrella unless controller assigns an explicit later owner/destination.
6. For each accepted current-umbrella finding, perform root-cause confirmation, implementation, review, fix, re-review, accepted commit, validation, README decision and residual-risk reconciliation.
7. After fixes, repeat full-repository rounds until at least two consecutive rounds produce no new accepted current-umbrella finding, unless the user explicitly changes the exit condition.

Umbrella final closeout requires:

- all 8 listed sub WUs complete；
- all accepted findings from subsequent deepreview complete or assigned；
- at least two consecutive full-repository deepreview rounds after fixes with no new accepted current-umbrella finding, unless the user explicitly changed that exit condition；
- pyright and appropriate full/focused test matrix complete or failures explicitly owned；
- `git diff --check` pass；
- control doc updated in the appropriate later gate；
- final closeout artifact records full finding status and residual risks。

## 9. Controller completion report format

每个 sub WU closeout report：

1. Sub WU id / title。
2. Root-cause confirmation artifact。
3. Plan / review / implementation / re-review artifact paths。
4. Accepted commit hash。
5. Findings fixed / rejected / obsolete / deferred。
6. Propagation audit summary。
7. Validation commands and results。
8. README decision。
9. Residual risks and owners。
10. Next entry point。

Umbrella final completion report：

1. Umbrella artifact index。
2. 8 个 sub WU completion table。
3. Full-repository deepreview rounds table。
4. All accepted findings final state。
5. Validation summary。
6. Docs / README updates。
7. Remaining risks / owners。
8. Draft PR / PR review / final closeout status if later gates open PR。
9. Statement that fixing original review artifacts alone was not treated as umbrella completion。

## 10. Current plan-gate validation

This plan fix gate changes only the umbrella plan and optional plan fix report. Required validation for this gate:

- `git diff --check`
- If the plan or fix report is still untracked, run `git diff --no-index --check /dev/null <path>` for each new file.

Production tests and pyright are not required for this plan gate because no production code, tests, README or config files are changed. Each sub WU above lists the tests and pyright required for its implementation gate.
