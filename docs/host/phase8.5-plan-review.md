# P8.5 Re-plan Review

- **review gate name**: plan review
- **reviewed target**: `docs/host/phase8.5-plan.md`
- **source of truth**: `docs/host/design.md`, `docs/host/migration-plan.md`, `dayu/host/README.md`, `tests/README.md`, current code facts
- **reviewer conclusion**: fail
- **artifact path**: `docs/host/phase8.5-plan-review.md`

## Assumptions Tested

- 新 plan 必须完整吸收新版 Host tool design：Engine 只看 `ToolSchema` / `ToolExecutionRequest` / `ToolExecutionOutcome`，不看 `ToolDefinition`、callable、framework dispatch 或 manager。
- EventLog 只记录普通 tool calling：`TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`；不保留 `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_*`、`TOOL_FETCH_MORE_*`。
- `RuntimeTruncateManager` 拥有截断状态机与 cursor store；`HostToolRuntime` 只组合 manager 并做普通 dispatch。
- Dayu local-agent payload policy 是窄 scrub：普通 tool args/result/cursor/`scope_token` 不因字段名被 redaction；只 scrub `API_KEY` / explicit credentials。
- Plan 必须 handoff-ready：implementation agent 不应自行决定 schema、public contract、file ownership、state transition 或 test expectations。

## Findings

### 01-未修复-[严重]-framework fetch_more schema 自动投影路径不够 handoff-ready

- **Plan位置**: §2.1 `dayu.contracts` 边界，§5 Affected Files，Slice 1 implementation instructions。
- **问题类型**: 架构边界 / 契约缺失 / 不可直接实施 / file ownership 不清。
- **计划当前写法**: Plan 要求 Host 自动把私有 framework tool definition 的 schema 投影到 Engine 可见 tool schemas，调用方不再手工 import `framework_fetch_more_tool_schema()`；同时 Slice 1 allowed files 只列 `contracts.py`、`__init__.py`、`_run_event_serializer.py`、`_tool_runtime.py`、私有新增模块、`_event_translation.py`、`dayu/contracts/*` 和 tests / utils / README。
- **反例/失败场景**: 当前 `EngineWorker` 直接把 `request.options.tool_schemas` 传给 `AgentRunRequest.tool_schemas`。如果 Slice 1 只改 `_tool_runtime.py` 和 contracts，`fetch_more` 私有 schema 不会自动进入 Engine 可见 schema；如果 implementation agent 为了完成目标去改 `_run_harness.py`、`_worker.py` 或 `RunOptions` normalization，又会越过 Slice 1 allowed files。
- **为什么有问题**: 新设计要求 Host 私有 `fetch_more` definition 只投影 schema 给 Engine，但 plan 没指定投影 owner、精确 call path、是否写回 `RunOptions.tool_schemas`、RunInput context fact 看到的是原始 schemas 还是增强后 schemas，也没授权当前实际传递链路的关键文件。
- **直接证据**:
  - Plan §2.1 lines 88-94、Slice 1 lines 317-320 要求 Host 投影私有 schema。
  - Plan Slice 1 allowed files lines 296-300 未列 `dayu/host/_worker.py`、`dayu/host/_run_harness.py` 或装配层。
  - `dayu/host/_worker.py:42-52` 当前直接使用 `request.options.tool_schemas`。
  - `dayu/host/_run_harness.py:2416-2422` 当前 RunInput context fact builder 也直接使用 `request.options.tool_schemas`。
- **影响**: 实施 Agent 可能继续让调用方手工传 `fetch_more` schema，违反 Host 私有 framework tool 边界；也可能临时扩大改动或把 `ToolDefinition` 泄漏到 public request / options，导致 review 不可验收。
- **建议改法和验证点**:
  - 在 plan 中明确 schema 投影 owner 和 call path，例如由 Host 私有 framework tool provider 提供 `framework_tool_schemas()`，在 Host 进入 EngineWorker 前构造增强后的 tuple；不得修改 Engine。
  - 明确是否允许修改 `_run_harness.py` / `_worker.py` / `_durable_harness.py`，以及 RunInput context fact 应记录增强后的 Engine-visible schemas。
  - 增加测试：调用方只传业务 tool schema，Engine request 中仍包含 `fetch_more` schema；`RunOptions.tool_schemas` 不被 public mutation 污染；Engine 不接收 `ToolDefinition`。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 严重。
- **controller decision status**: pending-controller-decision。

### 02-未修复-[严重]-EventLog 保留 cursor/scope_token 后，memory projection 的短期凭证边界未定义

- **Plan位置**: §1 Success Signal，§2.3 Tool Trace / Observer，Slice 1 tests。
- **问题类型**: 架构边界 / 状态机漏洞 / 测试缺口 / hidden data-loss-debuggability risk。
- **计划当前写法**: Plan 明确 EventLog / trace 中普通 tool call args 与 ordinary result payload 默认保留，cursor、`scope_token`、tool data 本身不是 redaction 触发条件；Slice 1 要测试 EventLog / trace 保留 `fetch_more` args 与 `truncation.fetch_more_args`。
- **反例/失败场景**: `TOOL_RESULT_ACCEPTED` 中保留 `truncation.fetch_more_args.scope_token` 后，如果 conversation memory projection 按普通 tool fact 摘要或 payload 重放这些字段，下一轮 RunInput 可能把旧 run 的 cursor / `scope_token` 再喂给模型。模型可能复用 stale cursor，造成错误补读、无意义 failed tool call，或把同 run 短期 capability 误当成长期事实。
- **为什么有问题**: 新设计区分了 EventLog / trace 可保留用于诊断，与 memory / RunInput 不应消费短期 cursor capability。但 plan 只写了 trace retention 和 redaction，不写 memory projection 对 ordinary accepted result 中 `truncation.fetch_more_args` 的处理规则。
- **直接证据**:
  - `docs/host/design.md:1170-1175`：`scope_token` 只用于同一 run 内 framework `fetch_more`，不得进入 memory projection / RunInputBuilder 输入；trace 冷层必须能保留。
  - Plan lines 65-66、321-328 要求 EventLog / trace 保留 cursor / `scope_token`。
  - `dayu/host/_conversation_memory.py:624-650` 当前从 `ToolResultAcceptedData` 生成 `ConversationToolFact`；后续删除专属 facts 后，这条普通 accepted-result 路径会成为主要 memory tool fact 入口。
- **影响**: 删除专属 facts 后，短期 cursor capability 可能经 memory 变成跨 run 输入，破坏 `fetch_more` single-run / single-use 语义，也会让后续 Agent 误以为“local-agent 不 redaction”等于“memory 可长期保留 capability 字段”。
- **建议改法和验证点**:
  - 在 plan 中明确 memory projection 规则：EventLog / trace 保留 ordinary payload；Conversation Memory / RunInputBuilder 只保留安全摘要，不输出 raw cursor / `scope_token` / `truncation.fetch_more_args`。
  - Slice 1 或 Slice 3 增加测试：EventLog / trace 可见 cursor 和 `scope_token`；memory snapshot / RunInputBuilder rendered tool facts 不包含 raw cursor / `scope_token`。
  - 明确这不是字段级 redaction，而是 memory ingestion policy：短期 runtime capability 不进入长期对话事实。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 严重。
- **controller decision status**: pending-controller-decision。

### 03-未修复-[高]-共享 ToolTruncationInfo 契约仍禁止写入 RunEvent，plan 未列入 contract impact

- **Plan位置**: §5 Affected Files，§6 Contract / Serializer / Projection / Schema Impact，Slice 1 allowed files。
- **问题类型**: 契约缺失 / 架构边界 / 测试缺口。
- **计划当前写法**: Plan 要求 `TOOL_RESULT_ACCEPTED` 保存普通 tool result payload，并允许 accepted result 中 cursor / `scope_token` 作为普通 payload 保留；affected files 只列 `dayu/contracts/tool_declaration.py` 与 `dayu/contracts/__init__.py`。
- **反例/失败场景**: Implementation agent 按 plan 删除 `_event_translation.py` 的 truncation scrub 后，`ToolResultSuccess.truncation` 会进入 RunEvent；但公共契约 `ToolTruncationInfo` docstring 仍声明 cursor “不得写入 Host RunEvent / memory / 日志”。代码行为和契约文档相互矛盾。
- **为什么有问题**: 新 payload policy 改变的不只是 Host serializer/projection，也改变了 shared tool result contract 的语义说明。plan 漏列 `dayu/contracts/tool_result.py` 和对应 tests，会导致 public contract 继续指导后续 Agent 写回旧 redaction 逻辑。
- **直接证据**:
  - Plan lines 85-86、321-323：accepted result 中 cursor / `scope_token` 可以作为普通 payload 保留。
  - `dayu/contracts/tool_result.py:27-45`：`ToolTruncationInfo.cursor` docstring 明确“不得写入 Host RunEvent / memory / 日志”。
  - Plan affected files lines 198-209 只列 `dayu/contracts/tool_declaration.py`、`dayu/contracts/__init__.py`，未列 `dayu/contracts/tool_result.py`。
- **影响**: 契约 drift 会让实现、测试和文档互相打架；review 难以判断到底以 plan 还是 public contract 为准。
- **建议改法和验证点**:
  - 把 `dayu/contracts/tool_result.py` 和相关 contracts tests 加入 Slice 1 affected files。
  - 修改 `ToolTruncationInfo` 文档：cursor / `scope_token` 可短期作为 LLM-facing ordinary tool result payload 进入 EventLog / trace；不得进入 memory /普通日志/README 大块输出。
  - 增加 contract-level test，锁定 `ToolTruncationInfo` 是 ordinary result payload 的一部分，不是 Host public fetch_more handle。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。
- **controller decision status**: pending-controller-decision。

### 04-未修复-[严重]-RunInput raw payload side store 的 schema / API 仍留给 implementation 设计

- **Plan位置**: §6 Schema Impact，Slice 4 implementation instructions。
- **问题类型**: schema 缺失 / 不可直接实施 / open question 未收敛。
- **计划当前写法**: Plan 说 Slice 4 需要 Host durable raw payload side store，具体 table/schema 由 implementation 写入 plan-compatible report；Slice 4 只要求移除 inline raw payload、增加 side store、和 EventLog append 同 transaction。
- **反例/失败场景**: Implementation agent 必须自行决定 table 名、primary key、payload kind、blob id 唯一性、content hash、byte size、created_at、reader API、transaction API、是否按 run/iteration 建索引、serializer 如何处理 missing blob。这些都是 schema/state-machine 契约，不是实现细节。
- **为什么有问题**: Gateflow plan 要求 schema/storage changes 在 plan 阶段收敛。把 schema “由 implementation report 决定”会让 later review 只能审实现方案，而不是审 approved plan 合规性。
- **直接证据**:
  - Plan lines 275-279：Slice 4 raw payload side store 具体 table/schema 由 implementation 写入 report。
  - Plan lines 492-494：只规定 side store 与 EventLog append 同 transaction，没有定义 schema / API。
  - `dayu/host/contracts.py:545-584` 当前 `RunInputContextSnapshotBuiltData` 内联 `raw_input_messages_json` / `raw_tool_schemas_json`，这是明确 schema contract 变更。
- **影响**: Slice 4 不 handoff-ready；可能出现不兼容的 side-store schema、无法恢复 trace raw payload、EventLog fact 引用 orphan blob、或 schema bootstrap 半失败。
- **建议改法和验证点**:
  - Plan fix 中定义 side store 表名、columns、primary/unique key、索引、writer/reader API、事务边界和 missing/corrupt payload error semantics。
  - 明确 `RunInputContextSnapshotBuiltData` 删除哪些字段、保留哪些 hash/blob id/byte size 字段。
  - 增加测试：同 transaction rollback 不产生 side-store row；EventLog fact 引用的 blob 必须可读；missing side-store row 在 trace projection 中 fail-fast 或 typed diagnostic。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 严重。
- **controller decision status**: pending-controller-decision。

### 05-未修复-[中]-design.md 仍残留旧专属 fact 口径，plan 未指定优先级或前置清理

- **Plan位置**: §8 Review Gates，Slice 6 Documentation Closeout。
- **问题类型**: 架构边界 / handoff 风险 / 文档真源冲突。
- **计划当前写法**: Plan 要求 review 只对照 `docs/host/design.md:1077-1233`，并把 `docs/host/design.md` 的实现事实冲突修正放到最终 Slice 6。
- **反例/失败场景**: 后续 implementation agent 按 prompt 读取完整 `docs/host/design.md`，会同时看到新版 §11 和旧 P8/P7 段落。旧段落仍写“ToolRuntime 产生 truncate / cursor / fetch_more facts”，这正是本轮宣布失败的旧路线。
- **为什么有问题**: 用户已把 `docs/host/design.md` 定为新的设计真源。如果真源内有互斥口径，plan 不能只引用一个 line range 后把清理推迟到最后，否则 worker 读取顺序不同就可能复活旧实现。
- **直接证据**:
  - Plan lines 671-674：review gate 只要求检查 `design.md:1077-1233`。
  - Plan lines 631-641：`design.md` 修正放在 Slice 6 documentation closeout。
  - `docs/host/design.md:664-665` 仍写所有 attempt-scoped append 包括 “ToolRuntime 产生的 truncate / cursor / fetch_more facts”。
  - `docs/host/design.md:952-955` 仍写 P8-S2 observer process 与 checkpoint 同事务同生同灭，而 Slice 3 要改 non-required trace observer transaction 边界。
- **影响**: 文档真源冲突会误导 worker / reviewer，尤其 Slice 1 和 Slice 3；也会让 review 时无法判断设计偏差是实现问题还是历史事实残留。
- **建议改法和验证点**:
  - Plan fix 要么先做一个文档前置 cleanup gate，把 design.md 中与新版 §11 冲突的旧句子改成“P8 当前事实，P8.5 将删除/改造”；要么在 plan 顶部明确冲突优先级：P8.5 implementation 以新版 §11 / plan 为准，旧 P7/P8 facts 仅为历史 current-code evidence。
  - Slice 6 仍可做最终 README/migration closeout，但不要把会误导 implementation 的 design 真源冲突留到最后。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。
- **controller decision status**: pending-controller-decision。

### 06-未修复-[中]-Slice 3 非事务 trace observer 语义不足以直接实现

- **Plan位置**: Slice 3 Tool Trace / Observer Projection Stability。
- **问题类型**: 状态机漏洞 / 不可直接实施 / 测试缺口。
- **计划当前写法**: Plan 建议为非 required observer 增加 `NonTransactionalObserverSink`：先在 transaction 外执行 JSONL/blob I/O，成功后短 transaction 推 checkpoint；失败时记录 failure，不推进 checkpoint。
- **反例/失败场景**: 如果 JSONL 写入成功但进程在 checkpoint 前 crash，重启会 replay 同 batch 并写重复 JSONL。旧设计依赖 idempotency key 让 analyzer 去重，但 Slice 3 没写明该 crash window 是 accepted semantics，也没要求测试 duplicate replay。若记录 failure 也在短事务中完成，I/O failure 与 checkpoint failure 的状态枚举、retry_count、lag_events 语义均不清楚。
- **为什么有问题**: 该 slice 改 observer checkpoint 状态机，不只是“把 I/O 移出 transaction”。plan 没定义 required vs non-required observer 的 precise protocol、failure status、idempotency expectations 和 replay behavior。
- **直接证据**:
  - Plan lines 445-449 描述非事务 path，但未定义 checkpoint crash window / duplicate semantics。
  - `docs/host/design.md:940-947` 旧 trace 设计明确依赖 `idempotency_key` 去重 replay 副本。
  - `dayu/host/_event_observer.py:261-271` 当前在一个 storage transaction 内 `await observer.process` 后推进 checkpoint。
- **影响**: 实施 Agent 可能写出“transaction 外 I/O + checkpoint”但缺少可验证的 crash/replay 语义；review 无法判断重复 JSONL 是 bug 还是 accepted at-least-once 行为。
- **建议改法和验证点**:
  - Plan 中明确 non-required trace observer 的 accepted semantics：JSONL 是 at-least-once，checkpoint 前 crash 允许重复行，必须依赖 idempotency_key 去重；checkpoint 推进失败后不得标 success。
  - 明确 failure recording 使用哪些 `ObserverStatus` / `ProjectionStore.record_failure` 字段，是否增加新 status。
  - 增加测试：I/O 成功 checkpoint 前失败会 replay 并产生相同 idempotency_key；I/O 失败不推进 checkpoint、不阻塞 required memory observer。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。
- **controller decision status**: pending-controller-decision。

### 07-未修复-[低]-closeout grep guard 会被历史 docs 命中，缺少 expected-result 约束

- **Plan位置**: Slice 6 validation。
- **问题类型**: 测试缺口 / review 不可验收。
- **计划当前写法**: Slice 6 validation 运行 `rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" docs dayu tests utils`。
- **反例/失败场景**: `docs/host/migration-plan.md` 作为 residual registry / 历史事实索引会保留旧 phase 名称和旧风险文本；plan 自身也会包含这些 forbidden strings。直接 grep `docs` 不说明允许命中，会让 closeout validation 永远非零，或者诱导 implementation agent 删除历史审计上下文。
- **为什么有问题**: grep guard 应区分 production code / current README / current tests 的 forbidden references 与 historical artifacts 的 audit references。
- **直接证据**:
  - Plan lines 645-650 的 grep scope 包含 `docs`。
  - `docs/host/migration-plan.md:139-141` 当前作为 residual risk registry 明确记录旧 `TOOL_FETCH_MORE_*` / `TOOL_CURSOR_*` 风险。
- **影响**: closeout gate 的验证信号不稳定；可能误删历史 artifact，或把失败 grep 当成可忽略噪音。
- **建议改法和验证点**:
  - 把 grep guard 分成 production/readme/test guard 和 historical-doc audit guard。
  - 对 `docs/host/migration-plan.md` / prior review artifacts 明确允许“历史事实 / residual risk”命中，但 current README、design current sections、production code 不允许命中。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。
- **controller decision status**: pending-controller-decision。

## Open Questions

- **blocking**: Slice 1 的 `fetch_more` schema 自动投影 owner 是 `_run_harness.py`、`_worker.py`、`HostToolRuntime` provider，还是某个新的 Host 私有 assembly module？Plan 必须裁决。
- **blocking**: EventLog / trace 保留 cursor/`scope_token` 后，Conversation Memory / RunInputBuilder 是否必须显式移除或摘要化这些短期 capability 字段？按 design 当前答案应为“必须”，但 plan 需要写入实现规则。
- **blocking**: RunInput raw payload side store 的具体 SQLite schema、API 和 transaction ownership 是什么？Plan 当前未定义。

## Residual Risk

- 删除专属 facts 后的 trace/debuggability 方向是正确的，但必须靠普通 tool payload、summary、trace idempotency key 和 memory ingestion policy 共同闭环；当前 plan 对 trace 有方向，对 memory 与 checkpoint replay 仍不够具体。
- `dayu.contracts.framework_fetch_more_tool_schema` / `FRAMEWORK_FETCH_MORE_TOOL_NAME` 的最终移除方向正确，但需要和 schema 自动投影路径一起收敛，否则会在 contracts public surface 留下半旧半新的状态。

## Final Conclusion

结论：**fail**。

新版 P8.5 方向与 controller 最新设计一致，但 plan 仍有 3 个 blocking implementation choices 未收敛：

1. Host 私有 `fetch_more` schema 如何自动投影到 Engine-visible schemas。
2. EventLog / trace 保留 cursor 与 `scope_token` 后，memory / RunInput 如何避免长期复用短期 capability。
3. RunInput raw payload side store 的 schema 与 transaction API。

这些问题不应交给 implementation agent 自行设计；建议先进入 plan fix，再 re-review。
