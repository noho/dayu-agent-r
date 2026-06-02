# WU-TOOL-02 Accept Candidate Structure Cleanup Plan

## Gate 与交付物

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- 当前 gate: `plan`
- 当前分支: `refactor/wu-tool-02-accept-candidate-cleanup`
- 设计真源: `docs/host/design.md`
- 总控真源: `docs/host/host-core-followup-implementation-control.md`
- 代码核对真源: `docs/reviews/wu-tool-02-discussion-code-inspection-20260602.md`
- 本 plan 交付物: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

本 work unit 只做 Host 内部 `ToolFactAcceptCandidate` typed structure 清理。它不改变 ToolRuntime 行为、Host accept barrier 语义、EventLog durable payload、accepted evidence envelope、memory、compaction、tool trace、duplicate governance、wait、retry、replay 或 resume 语义。

## 动机判断与直接证据

动机成立，但不是当前运行时 correctness blocker。当前风险是维护性、可测试性和后续演进风险：一个过宽 candidate 同时承载多类 fact kind 的互斥字段，使 producer、accept barrier、EventLog payload、trace、memory / compaction 消费和测试 helper 都必须理解整包字段，后续治理字段变更容易误伤 durable 语义。

直接代码证据：

- `dayu/host/tool_runtime.py` 中 `ToolFactAcceptCandidate` 当前集中承载 Session / Run / Attempt / execution identity、iteration、tool call、schema / identity digest、normalized args digest、fact kind、outcome / payload / truncation、raw tool outcome、duplicate governance、reuse refs、policy decision、tool idempotency、diagnostic refs、accept idempotency 与 semantic digest。
- `ToolFactAcceptCandidate.__post_init__` 已按 `COMPLETED`、`FAILED`、`CANCELLED`、`GOVERNED_ERROR`、`REUSE` 分支校验互斥字段，说明不同 fact kind 实际不是同一字段集合。
- `DefaultHostToolFactAcceptPort._accept_in_transaction()`、`_accept_idempotency_scope()`、`_read_accept_context()`、`_invalid_accept_context_reason()`、`_tool_accept_event_plan()`、`_tool_call_requested_event_request()`、`_append_tool_call_governed_if_needed()`、`_tool_result_payload()`、`_accepted_evidence_envelope()`、`_accepted_ack_from_rows()` 和 `_log_tool_fact_accept_result()` 均直接读取 candidate 顶层字段。
- Producer `_tool_fact_accept_candidate()` 和 `_tool_fact_reuse_accept_candidate()` 已分为普通 outcome 与 reuse 路径，但最终仍回填同一个超宽 dataclass；awaiting 路径使用 `ToolAwaitingAcceptCandidate`，属于独立 wait accept barrier，不应纳入本次结构拆分。
- `tests/host/test_toolruntime_accept_barrier.py`、`tests/host/test_toolruntime_executor.py`、`tests/host/test_toolruntime_duplicate_governance.py`、`tests/host/test_toolruntime_diagnostics.py`、`tests/host/test_toolruntime_truncation_fetch_more.py` 中测试 port 与 helper 仍直接构造或读取超宽 candidate。
- `dayu/host/tool_trace.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py`、`dayu/host/memory.py` 消费的是 committed EventLog payload，不消费 candidate 本身；因此本 work unit 必须保持 payload key 和事件语义不变，只允许 accept barrier 内部读取路径改为新 typed 子结构。

## Hard Boundaries

- `ToolFactAcceptCandidate` 保持 Host 内部类型，不导出为 Host public API，不新增 public API。
- 不改变 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` event type、event class、event id 派生输入、payload key、payload ref / digest、accepted evidence envelope 或 idempotency record 语义。
- 不改变 evidence-backed fact 生成门槛；assistant final answer 仍不自动成为 `evidence_backed_fact`。
- 不改变 duplicate governance attempt-local 语义、freshness、side-effect idempotency、wait、retry、replay、resume、accepted ack 或 accept barrier precondition。
- 不引入兼容 wrapper、旧字段 facade、兼容 re-export、旧字段 property 转发或 public API 扩展。
- 不新增 `Any`、`object`、无类型签名、magic payload，显式字段不得塞入 extra payload。
- 不做无关重构，不迁移 durable schema，不修改配置。

## Proposed Typed Structure

在 `dayu/host/tool_runtime.py` 内新增 Host 内部 frozen slots dataclass，均提供中文 docstring 和严格类型。命名可按实现局部微调，但职责边界必须保持：

- `ToolAcceptIdentity`
  - 字段：`session_id`、`run_id`、`attempt_id`、`execution_id`。
  - 用途：accept precondition、EventLog row identity、日志、idempotency scope。

- `ToolAcceptCall`
  - 字段：`iteration_id`、`tool_call_id`、`tool_name`、`tool_schema_digest`、`tool_identity_digest`、`normalized_arguments_digest`。
  - 用途：`TOOL_CALL_REQUESTED` payload、accepted evidence query、tool trace metadata。

- `ToolAcceptResult`
  - 字段：`outcome_digest`、`payload_digest`、`payload_ref`、`truncation`、`raw_tool_outcome`。
  - 用途：普通 result 和 governed error 的 `TOOL_RESULT_ACCEPTED` payload、payload descriptor validation、accepted evidence result ref、compaction raw material。
  - 约束：reuse 不持有该结构；需要写 `TOOL_RESULT_ACCEPTED` 的 fact kind 必须持有非空 `outcome_digest` 与 `raw_tool_outcome`；`COMPLETED` 继续要求 `payload_digest`。本 work unit 不借结构拆分新增 payload digest 校验语义；`payload_ref` 存在时保持当前 descriptor 存在性校验与当前已有 candidate 校验，不扩大为新的等值规则或新持久化约束。

- `ToolAcceptGovernance`
  - 字段：`policy_decision`、`tool_idempotency_key`、`duplicate`。
  - `duplicate` 建议使用 `ToolAcceptDuplicateGovernance | None`。
  - 用途：`TOOL_CALL_GOVERNED` payload、result payload policy fields、governed event 判定。

- `ToolAcceptDuplicateGovernance`
  - 字段：`duplicate_key`、`duplicate_decision`、`duplicate_scope`、`duplicate_decision_message`、`reuse_prior_event_refs`。
  - 用途：attempt-scoped duplicate / reuse / duplicate governed error 字段集中管理。
  - 约束：非 allow duplicate decision 必须有 key、scope、message；reuse 与 duplicate governed error 再由 fact kind validator 约束 prior refs。

- `ToolAcceptIdempotency`
  - 字段：`accept_idempotency_key`、`semantic_input_digest`。
  - 用途：Host idempotency scope、event id plan、`TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` payload、accepted evidence query。

- `ToolAcceptDiagnostics`
  - 字段：`diagnostic_refs`。
  - 用途：ack、governed event payload、result payload、日志和 test port inspection。
  - 说明：该结构可保留以维持职责分组；implementation agent 也可在不破坏职责分组、类型边界和测试可读性的前提下，把单字段 diagnostics 保留为组合根的直接字段。

`ToolFactAcceptCandidate` 保留为组合根，但顶层字段收敛为：

```text
ToolFactAcceptCandidate
  identity: ToolAcceptIdentity
  call: ToolAcceptCall
  tool_fact_kind: ToolFactKind
  result: ToolAcceptResult | None
  governance: ToolAcceptGovernance
  idempotency: ToolAcceptIdempotency
  diagnostics: ToolAcceptDiagnostics
```

实现时不得保留旧顶层字段 property 作为兼容 facade。所有 producer、consumer 和 tests 必须迁移到组合结构读取。

Validation 分解原则：

- 子结构 `__post_init__` 只校验本结构内部 invariant，例如非空文本、digest 格式、policy decision 自身字段组合、diagnostic refs 类型。
- 跨子结构约束和 fact-kind 约束必须由 `ToolFactAcceptCandidate` 组合根或专门 fact-kind validator 校验，例如 reuse 禁止 result、ordinary result 只能携带 allow policy、duplicate governed error 的 policy reason/message 必须匹配 duplicate decision。
- 错误消息、helper 命名和检查顺序可按实现局部代码质量调整，但不得改变现有语义、拒绝边界或 durable payload。

## Fact Kind 字段归属与校验规则

本章节表达语义约束和验收边界，不是逐行实现模板。Implementation agent 可以在保持语义不变、测试覆盖完整和 pyright 通过的前提下调整 validator 组织、错误消息与检查顺序。

### Ordinary Result: `COMPLETED` / `FAILED` / `CANCELLED`

- 必须有：`identity`、`call`、`tool_fact_kind`、`result`、`governance`、`idempotency`、`diagnostics`。
- `governance.policy_decision.kind` 必须为 `ALLOW`。
- `result.outcome_digest` 必须是 sha256 digest。
- `result.raw_tool_outcome` 必须存在。
- `COMPLETED` 必须有 `result.payload_digest`；`FAILED` / `CANCELLED` 可无 payload digest，但不得携带 reuse prior refs。
- `governance.duplicate` 可为 `None` 或 allow duplicate record；若存在 duplicate decision，必须满足 duplicate 通用校验。
- 写入 `TOOL_CALL_REQUESTED` 和 `TOOL_RESULT_ACCEPTED`；通常不写 `TOOL_CALL_GOVERNED`，除非 duplicate decision 非 allow。

### Reuse: `REUSE`

- 必须有：`identity`、`call`、`tool_fact_kind=REUSE`、`governance`、`idempotency`、`diagnostics`。
- 必须无：`result`。
- `governance.policy_decision.kind` 必须为 `REUSE`。
- `governance.duplicate` 必须存在，`duplicate_decision=REUSE`，`duplicate_key`、`duplicate_scope`、`duplicate_decision_message`、`reuse_prior_event_refs` 均必填。
- `policy_decision.reason_code` 必须等于 duplicate reuse reason，`policy_decision.message` 必须等于 duplicate decision message。
- 写入 `TOOL_CALL_REQUESTED` 和 `TOOL_CALL_GOVERNED`；不写新的 `TOOL_RESULT_ACCEPTED`；accepted ack 的 `result_digest` 仍回退 `semantic_input_digest`。

### Plain Governed Error: `GOVERNED_ERROR`

- 必须有：`identity`、`call`、`tool_fact_kind=GOVERNED_ERROR`、`result`、`governance`、`idempotency`、`diagnostics`。
- `governance.policy_decision.kind` 必须是非 `ALLOW` 且非 `REUSE`；plain runtime/policy governed error 使用 `GOVERNED_ERROR`。
- `result.outcome_digest` 必须是 sha256 digest，`result.raw_tool_outcome` 必须存在。
- `governance.duplicate` 可无；若无 duplicate，则不得携带 `reuse_prior_event_refs`。
- 写入 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED`。

### Duplicate Governed Error: `GOVERNED_ERROR`

- 必须有：plain governed error 的所有字段，且 `governance.duplicate` 必须存在。
- `duplicate_decision` 允许：`HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP`、`DURABLE_MISSING`。
- `HINT` / `REQUIRE_JUSTIFICATION` / `HARD_STOP`：
  - `policy_decision.kind.value` 必须等于 duplicate decision value。
  - `reuse_prior_event_refs` 必须非空。
  - `policy_decision.reason_code` 必须等于 duplicate reason。
  - `policy_decision.message` 必须等于 duplicate decision message。
- `DURABLE_MISSING`：
  - 不得携带 `reuse_prior_event_refs`。
  - `policy_decision.reason_code` 必须等于 durable-missing duplicate reason。
- 写入 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED`。

### Unsupported: `LOST`

- `ToolFactKind.LOST` 当前不在 `ToolFactAcceptCandidate` 支持范围内。
- 现有 validation 必须继续 fail-fast，不能为 `LOST` 新增 producer、payload、ack 或 EventLog 语义。
- 未来若需要由 ToolRuntime accept candidate 表达 lost tool fact，必须另行进入设计和 implementation work unit。

## Producer 迁移路径

- 普通工具 outcome candidate 在 scope 内。
  - 迁移 `_tool_fact_accept_candidate()`：先构造 `ToolAcceptIdentity`、`ToolAcceptCall`、`ToolAcceptResult`、`ToolAcceptGovernance`、`ToolAcceptIdempotency`、`ToolAcceptDiagnostics`，再构造组合根。
  - 保持 `_tool_fact_kind()`、`_tool_outcome_digest()`、`_tool_payload_digest()`、`_tool_semantic_input_digest()`、`_tool_accept_idempotency_key()` 的输入语义不变。

- Reuse candidate 在 scope 内。
  - 迁移 `_tool_fact_reuse_accept_candidate()`：构造无 `result` 的 `REUSE` candidate，prior outcome 只用于 digest / idempotency 派生和返回 Engine，不作为新 result payload。
  - 保持 reuse accepted ack 和 Engine-facing prior outcome 语义不变。

- Awaiting candidate 不在本次结构拆分 scope 内。
  - 原因：awaiting 走 `HostToolAwaitingAcceptPort` 与 `ToolAwaitingAcceptCandidate`，对应 wait / external job accept barrier，不是 `ToolFactAcceptCandidate` 的字段过宽问题。
  - 本 work unit 只需要确认 `_accept_awaiting()` 路径不被普通 fact candidate refactor 误改。

## Consumer 迁移路径

- Accept barrier validation:
  - `_accept_idempotency_scope()` 改读 `candidate.identity`、`candidate.call`、`candidate.idempotency`。
  - `_read_accept_context()` / `_invalid_accept_context_reason()` 改读 `candidate.identity`。
  - `_candidate_payload_descriptor_exists()` 只读 `candidate.result.payload_ref`，reuse 无 result 时直接 `True`。

- EventLog payload:
  - `_tool_accept_event_plan()` 的 digest input 必须保持原 key/value 语义不变，只从新结构读取。
  - `_tool_call_requested_event_request()` payload key 必须不变。
  - `_append_tool_call_governed_if_needed()` 和 `_tool_result_payload()` payload key 必须不变；仅改读取路径。
  - `_tool_event_request()` row identity、source、actor、idempotency key 不变。

- Accepted evidence envelope:
  - `_accepted_evidence_envelope()` 改读 `candidate.call`、`candidate.idempotency`、`candidate.result`。
  - `payload_ref` / `payload_digest` 选择逻辑不变。

- Accepted ack:
  - `_accepted_ack_from_rows()`、`_ack_result_digest()` 改读 `candidate.result` 与 `candidate.idempotency`。
  - reuse ack 仍无 `tool_result_event_ref`，`result_digest` 仍为 semantic input digest。

- Tool trace diagnostics:
  - `ToolFactAcceptedAck.diagnostic_refs` 仍来自 candidate diagnostics。
  - `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` payload 的 `diagnostic_refs` JSON key 和 shape 不变，`dayu/host/tool_trace.py` 不需要语义修改。

- Memory / compaction 读取路径:
  - `dayu/host/memory.py` 仍只消费 committed `TOOL_RESULT_ACCEPTED` cursor / payload，不应新增 candidate 依赖。
  - `dayu/host/compaction_evidence.py` 和 `dayu/host/compact_material.py` 仍按 `accepted_evidence_envelope` 与 `raw_tool_outcome` 读取，不改变 fail-closed 行为。

- 测试 helper:
  - 将测试中手写超宽 candidate 的 helper 改为构造组合子结构。
  - 优先新增测试内小 helper，例如 `_candidate_identity(seeded)`、`_candidate_call(tool_call_id)`、`_allow_governance()`、`_result_for(tool_call_id)`，避免生产代码引入测试专用 builder。

## File Ownership

### Production ownership

- `dayu/host/tool_runtime.py`
  - owner: implementation agent
  - 允许改动：内部 dataclass、validation helper、producer helper、accept barrier consumer helper、logging helper、EventLog payload helper、accepted ack helper、typing/docstring。
  - 禁止改动：public exports 语义、EventLog payload schema、durable schema、ToolRuntime executor 行为、duplicate governance policy 行为、awaiting accept semantics。

### Tests ownership

- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`

允许改动：candidate construction helper、assertion 读取路径、negative validation tests。禁止为了保旧断言而在 production 加旧字段 facade。

### Read-only verification ownership

- `dayu/host/tool_trace.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compact_material.py`
- `dayu/host/memory.py`

默认不修改。若 implementation agent 发现必须修改这些文件才能通过测试，先确认变更只是读取 EventLog payload 的稳定说明或测试适配；若需要改变 payload / projection 语义，立即停止交回 controller。

### Documentation ownership

- `dayu/host/README.md` 触发条件：若 Host 内部 ToolRuntime accept barrier 结构或开发手册稳定边界说明需要同步，才更新。当前仓库路径需先核对实际 README 位置；不得机械创建不存在的职责文档。
- `tests/README.md` 触发条件：若测试 helper 约定或测试分层说明发生稳定变化，才更新。
- 根 README、`docs/host/design.md`、总控文档不属于 implementation slice 默认改动范围；若实现发现需要设计真源变更，停止。

## Implementation Slices

### Slice 1: 新增子结构与局部 validation helper

Allowed files:

- `dayu/host/tool_runtime.py`

Non-goals:

- 不改变 `ToolFactAcceptCandidate` 当前顶层字段。
- 不迁移 accept barrier consumer。
- 不迁移 ToolRuntime executor producer。
- 不迁移 tests。
- 不修改 EventLog payload key 或 projection consumer。
- 不引入 public API 或兼容旧字段 property。

步骤：

1. 在 `tool_runtime.py` 中定义 `ToolAcceptIdentity`、`ToolAcceptCall`、`ToolAcceptResult`、`ToolAcceptDuplicateGovernance`、`ToolAcceptGovernance`、`ToolAcceptIdempotency`、`ToolAcceptDiagnostics`。
2. 新增只服务后续迁移的局部 validation helper，例如 identity / call / result / governance / duplicate / idempotency / diagnostics 的内部 invariant 校验；这些 helper 可以暂时未接入组合根，但必须类型完整、docstring 完整、无 `Any` / `object` / 无类型签名。
3. 保持现有 `ToolFactAcceptCandidate` 顶层字段、现有 producer、现有 accept barrier consumer 和现有 tests 不变，避免同文件中间态类型失败。
4. 明确 `ToolFactKind.LOST` 仍不接入新 helper 的 supported candidate 语义，未来另行设计。

预期断言：

- 该 slice 结束时 production 行为不变。
- `tool_runtime.py` pyright 通过；focused accept barrier tests 仍按旧 candidate 结构通过。
- 新增子结构的 validation 只覆盖内部 invariant，不提前承担跨子结构 fact-kind 约束。

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py
```

### Slice 2: 组合根、producer、accept barrier consumer 与核心 tests 一次性迁移

Allowed files:

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`

Non-goals:

- 不改变 dispatch、timeout、cancellation、truncation、fetch_more 或 accept retry 行为。
- 不修改 awaiting accept candidate。
- 不修改 tool trace / memory / compaction production consumer。

步骤：

1. 将 `ToolFactAcceptCandidate` 顶层一次性迁移为组合根，并更新中文 docstring。
2. 接入 Slice 1 新增的 validation helper：子结构校验内部 invariant，组合根 / fact-kind validator 校验 ordinary result、reuse、plain governed error、duplicate governed error 和 unsupported `LOST`。
3. 迁移 `_tool_fact_accept_candidate()`，让普通 completed / failed / cancelled / governed error outcome 生成组合 candidate。
4. 迁移 `_tool_fact_reuse_accept_candidate()`，让 reuse 生成无 `result` 的组合 candidate。
5. 迁移 accept barrier consumer：`_accept_idempotency_scope()`、`_read_accept_context()`、`_invalid_accept_context_reason()`、`_candidate_payload_descriptor_exists()`、event plan、EventLog payload、accepted evidence envelope、accepted ack 和 logging helper 均改读组合结构。
6. 保持 `_tool_awaiting_accept_candidate()` 不变，仅修复受类型变更影响的相邻 helper。
7. 更新 `test_toolruntime_accept_barrier.py` 的 `_completed_candidate()`、`_reuse_candidate()`、`_fact_kind_candidate()`，新增或调整 validation negative tests 覆盖 result / reuse / governed error / unsupported `LOST` 互斥规则。
8. 更新 executor/truncation 测试 port 中对 candidate 字段的读取路径。
9. 将测试内 `_accepted_ack_for_call()` 等手写 candidate helper 改为组合 helper，避免重复超宽构造参数。

预期断言：

- 同 key + 同 semantic digest 仍返回既有 ack 且不重复写 facts。
- `TOOL_RESULT_ACCEPTED` payload 仍携带 accepted evidence envelope 和 raw outcome。
- 大 payload 仍冷热分离，descriptor ref / digest 不变。
- reuse 仍只写 requested + governed，不写 result。
- duplicate scope 仍写入 governed payload。
- 普通工具 completed candidate 的 raw outcome、payload digest、schema digest、identity digest、semantic digest 与旧语义一致。
- policy governed、runtime timeout / cancel governed error 仍返回 governed failure outcome，并经 accept barrier 写入。
- accept rejected / timeout 仍返回对应 Engine-facing governed failure。
- truncation fact、cursor hint、fetch_more 行为不变。
- awaiting outcome 仍进入 `ToolAwaitingAcceptCandidate` 路径，不受本 slice 迁移影响。
- `ToolFactKind.LOST` candidate 仍 fail-fast，不产生新 payload 或 EventLog。

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
```

### Slice 3: Duplicate / diagnostics candidate inspection 迁移

Allowed files:

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_diagnostics.py`

Non-goals:

- 不改变 attempt-scoped duplicate governance key、scope、owner/waiter、durable missing 或 reuse semantics。
- 不改变 diagnostic emitter、diagnostic ref hint 格式或 tool trace payload。

步骤：

1. 确认 `ToolAcceptDuplicateGovernance` 覆盖 reuse、hint、require justification、hard stop、durable missing 所需字段。
2. 更新 duplicate governance tests 对 `duplicate_scope`、`duplicate_decision`、`reuse_prior_event_refs`、`diagnostic_refs` 的读取路径。
3. 更新 diagnostics tests 对 candidate / ack diagnostic refs 的读取路径。
4. 增加或保留断言：duplicate governed candidate 的 duplicate scope 为 attempt，并且 ack diagnostic refs 等于 candidate diagnostics refs。

预期断言：

- reuse candidate 仍为 `ToolFactKind.REUSE`，prior refs 不丢失。
- duplicate governed candidate 仍为 `ToolFactKind.GOVERNED_ERROR`，duplicate scope 为 attempt。
- require justification / hard stop / hint / durable missing 的 policy reason/message 校验仍生效。
- diagnostics refs 在 candidate、ack、Engine-facing hint 中不丢失。

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py
```

### Slice 4: EventLog payload consumers regression 与 README/doc sync

Allowed files:

- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_llm_compaction.py`
- `tests/README.md`，仅当测试约定稳定说明需要同步。
- `dayu/host/README.md`，仅当实际存在且 Host 开发手册需要同步内部 accept candidate 边界说明。

Read-only unless proven necessary:

- `dayu/host/tool_trace.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compact_material.py`
- `dayu/host/memory.py`

Non-goals:

- 不改变 tool trace hot/cold projection schema。
- 不改变 memory projection 对 `TOOL_RESULT_ACCEPTED` 的事实生成门槛。
- 不改变 compaction material 对 accepted evidence envelope / raw outcome 的 fail-closed 行为。

步骤：

1. 运行 payload consumer tests，确认 committed EventLog payload 未变。
2. 若 tests 中只有 candidate helper 路径需要更新，则仅更新 tests。
3. 若 README 触发条件成立，更新稳定说明；不写过程状态、不写未来计划、不重复设计真源。
4. 以 pyright 作为旧顶层字段迁移的主要证明；`rg` 只作为辅助检查，不能替代类型检查。建议辅助命令：`rg -n "candidate\\.(session_id|run_id|attempt_id|execution_id|iteration_id|tool_call_id|tool_name|tool_schema_digest|tool_identity_digest|normalized_arguments_digest|outcome_digest|payload_digest|payload_ref|truncation|raw_tool_outcome|duplicate_key|duplicate_decision|duplicate_scope|duplicate_decision_message|reuse_prior_event_refs|policy_decision|tool_idempotency_key|diagnostic_refs|accept_idempotency_key|semantic_input_digest)" dayu tests`。允许命中 EventLog payload 字符串、docstring、子结构字段和非 `ToolFactAcceptCandidate` 对象；需要人工判读。

预期断言：

- tool trace duplicate scope 和 diagnostics projection 不变。
- memory projection 仍不因 `TOOL_RESULT_ACCEPTED` 直接生成 evidence-backed fact。
- compaction evidence material 仍从 accepted envelope + raw outcome 读取。
- README 只在职责范围内同步稳定说明。

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py dayu/host/tool_trace.py dayu/host/compaction_evidence.py dayu/host/compact_material.py dayu/host/memory.py
```

### Slice 5: Aggregate verification 与 final local gate

Allowed files:

- 只允许修复前四个 slice 已触及文件中的遗漏问题。
- 若发现需要改其它 production 文件，先说明 root cause；若涉及 public contract、schema、EventLog、ToolRuntime 行为，停止。

步骤：

1. 运行受影响 Host tool runtime 测试集合。
2. 运行全量 pyright。
3. 运行必要的 aggregate review / deepreview。
4. 由 controller 在常规 slice review 与 aggregate deepreview 通过后，追加 AgentMiMo 与 AgentDS 并行全仓 review，作为 ready-to-open-draft-PR 前置条件。

建议验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py
source .venv/bin/activate && pyright
```

## README / Doc Sync Decision

- 本 plan 本身不要求修改 README。
- Implementation 后若仅内部 dataclass 拆分、EventLog payload 和用户可见工作流不变，则根目录 `README.md`、`dayu/README.md`、`docs/host/design.md` 不应更新。
- 若 `dayu/host/README.md` 存在且当前 Host 开发手册描述了 ToolRuntime accept candidate 内部结构，则按稳定事实同步；若不存在，不为本 work unit 机械创建。
- 若 tests helper 约定发生稳定变化并属于 `tests/README.md` 职责，则同步测试手册；否则不更新。
- 文档不得写过程状态、未来计划、实现流水或新旧术语并存。

## Review Gates

- 每个 implementation slice 完成后先运行该 slice 验证命令，再进入对应 slice review。
- 所有 slice 完成后运行 aggregate tests、全量 pyright 和 aggregate deepreview。
- 额外前置条件：本 work unit 全部实现、常规 slice review 与 aggregate deepreview 通过后，controller 必须追加派发 AgentMiMo 与 AgentDS 做并行全仓 review；两路 review 的 actionable findings 处理完成并 re-review 通过后，才能进入 `ready-to-open-draft-PR`。
- AgentMiMo / AgentDS 并行全仓 review 不替代测试、pyright、slice review 或 aggregate deepreview。

## Stop Conditions

Implementation agent 遇到以下情况必须停止并交回 controller：

- 需要改变 Host public contract、public exports、`open_host(options)`、public request / response dataclass 或 ToolRuntime 对 Engine 的可见行为。
- 需要修改 durable schema、EventLog event type、EventLog payload key、event id 派生语义、idempotency scope 或 accepted evidence envelope shape。
- 需要改变 duplicate governance attempt-local 语义、reuse / durable missing 语义、freshness、side-effect idempotency、wait / awaiting、retry、replay、resume 或 compaction / memory 语义。
- 需要引入兼容 wrapper、旧字段 property facade、兼容 re-export、`Any`、`object`、无类型签名或 extra payload。
- `dayu/host/tool_trace.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py`、`dayu/host/memory.py` 必须发生生产语义修改才能通过测试。
- 发现当前设计真源不足以裁决字段归属或事实语义。

## Blocking Questions For Controller

无。当前设计真源、总控文档和代码核对 artifact 足以进入 implementation gate。

## Handoff Readiness

Handoff-ready。Implementation agent 可以按上述 slices 直接执行，不需要重新设计结构边界、字段归属、file ownership 或测试矩阵。
