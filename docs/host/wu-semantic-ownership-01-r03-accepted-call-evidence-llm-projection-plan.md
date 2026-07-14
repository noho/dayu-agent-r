# WU-SEMANTIC-OWNERSHIP-01 R03 accepted call / evidence LLM projection 实施计划

## 0. Gate 元数据

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation | `R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影` |
| 当前 gate | **plan gate only** |
| goal confirmation | 已由用户完成；本 gate 不重新提产品问题 |
| 当前分支 | `phaseflow/host-issues-control` |
| plan 取证基线 | `444bb33eaebba5f56d3cd211ced90e3b9d67a4fc` |
| 当前 worktree | plan 写入前 clean |
| 本 gate 唯一允许写入 | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` |
| 本 gate 明确禁止 | production、tests、README、design truth、control doc、prior artifact、commit、push、implementation |
| 下一 gate | 对本计划做独立 adversarial plan review；review 接受前不得进入 implementation |
| 状态 | `PLAN_READY_FOR_REVIEW`；不是 implementation authorization |

本计划继续同一个 umbrella WU，不创建 feature、issue、子 WU 或新的授权框架。R02 只作为前序 gate 已完成且未侵入 R03 owner 的边界证据；R02 completion 与 completion controller validation 的最终结论为 `PASS`，但不向 R03 输入新的产品决定。

### 0.1 已完整读取的权威输入

本 gate 已按用户指定顺序完整读取：

1. `AGENTS.md`
2. `docs/host/issues-implementation-control.md`
3. `docs/phaseflow-umbrella-optimization-control.md`
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
5. `docs/host/design.md`
6. `docs/engine/design.md`
7. `docs/tool/design.md`
8. `docs/fins/design.md`
9. `docs/ui/design.md`
10. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`，重点核对 R03
11. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md`，重点核对 §11 的逐文件 handoff inventory
12. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-completion.md` 与 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-completion-controller-validation.md`，仅核对 prior-gate boundary

裁决优先级固定为：controller discussion 与已接受决定 > design truth > remediation plan > 当前直接代码/数据证据 > 原始 overdesign review 的候选证据。三份原始 overdesign review 不能覆盖 controller discussion。

## 1. 第一性原理判断、目标与成功条件

### 1.1 动机判断

问题真实存在，且严重性没有被高估。直接代码证据显示，同一“Host 已接受的工具调用”当前存在两套 durable 表达和三类下游补偿：

- ordinary accept 在 `dayu/host/tool_runtime.py::_tool_call_request_payload_plan` 写原始 canonical arguments，并支持 inline/descriptor 与可选 semantic query；
- awaiting accept 在 `dayu/host/waiting.py::_tool_call_requested_event_request` 先调用 `llm_safe_replay_arguments` 改写参数，再生成另一套 inline-only payload 和 synthetic query；
- `TOOL_AWAITING` 又通过 `dayu/host/_event_payload.py::tool_awaiting_payload` 重复保存 redacted arguments 和 normalized digest；
- `dayu/host/payload_resolution.py::tool_call_request_atoms` 校验 payload digest，却没有断言 `arguments_payload_digest == normalized_arguments_digest`，因而不能证明读取到的正文就是原始 accepted arguments；
- `dayu/host/accepted_result_projection.py` 用字段名黑名单决定参数能否进入 LLM，并把未知 opaque ref 拼成 `kind:id` 业务来源；
- `dayu/host/tool_trace.py` 再次调用通用递归字段脱敏，形成第二套下游“安全参数”语义；
- resume、Memory 和 accepted evidence 对缺失/损坏 material 仍有 fallback，掩盖 canonical linkage corruption。

根因不是“少过滤几个字段”或“少隐藏几个 ref”，而是 accepted-call identity、LLM-readable query、业务 citation 与 internal provenance 的 owner 被拆散到多个消费者。修复必须回到 owner boundary，不能扩大 blacklist 或再建 safe/raw 双轨。

### 1.2 R03 目标

在不改变 Engine 结构化 tool-call contract、不引入统一授权框架、不处理 Issue #177/#178 的前提下，完成以下单一闭环：

1. ordinary 与 awaiting 都通过同一个 Host-owned request-atom builder 写唯一 `TOOL_CALL_REQUESTED` contract；
2. `TOOL_AWAITING` 只保存等待治理事实和显式 request-atom link，不重复 accepted arguments/digest；
3. request atom 只保存原始 canonical accepted arguments、同源 digest 与可选 producer semantic query，不存在 LLM-safe normalization；
4. prompt/tool schema/test prompt/Host-Engine-Tool renderer 在各自 owner 处完成逐文件人工审计，真实 schema 缺口只在 producer owner 修正；
5. accepted-result projection 以 semantic query 或原始 canonical arguments 构造 query，以 result 内显式 `citation` 构造业务来源；缺 citation 时给出唯一业务中性 unavailable 文案；
6. `OpaqueEvidenceRef` 只留在 EventLog envelope/audit/internal provenance，不进入共享 LLM material、RunInput、Memory、compactor readable material 或 LLM-ready Tool Trace summary；
7. 任何 request link 缺失、错类型、错 identity 或 digest mismatch 都 fail closed，不走 legacy/fallback/compatibility 路径。

### 1.3 完成判据

R03 只有同时满足下列条件才可完成：

- three-slice implementation、slice review、aggregate deep review 与 controller adjudication 均闭合；
- ordinary/awaiting 的 `TOOL_CALL_REQUESTED` 使用同一 builder、同一字段集合、同一 digest/descriptor/query invariant；
- `TOOL_AWAITING` payload 中不存在 `accepted_arguments`、`accepted_arguments_source_digest`、`normalized_arguments_digest` 或其它 arguments/digest 副本；
- resume 只沿 `TOOL_AWAITING -> tool_call_requested_event_ref -> TOOL_CALL_REQUESTED` 读取 exact canonical arguments；
- 删除 `llm_safe_replay_arguments`、`arguments_summary_unsafe`、递归 sensitive-key taxonomy、synthetic awaiting query、unknown `kind:id` source guessing 和 shared projection 中的 opaque refs；
- `file_path`、上传文件路径、合法业务字段和 framework `scope_token` 不因字段名被删除或改写；
- current production ToolDefinition/tool schema 没有让模型提交真实 credential；必要的 cursor/scope token 被明确说明为续读引用标签而不是业务事实；
- explicit Fins citation 在 RunInput、Memory、Compact、LLM-ready Tool Trace 四消费者中同源一致；无 citation 时四处均为同一 unavailable 语义；
- unknown、misspelled、internal opaque refs 在 EventLog envelope 中仍可 round-trip，但四个 LLM-facing 消费者均看不到 ref kind/id；
- 每个 R01 §11 handoff row 在 completion inventory 中有逐行 disposition 和直接证据；
- 受影响 tests、逐文件 coverage、pyright、diff/source/propagation scans 与真实 public-run smoke 全部通过；仅 grep 零命中不能作为完成证据；
- README 只按职责边界更新，completion artifact 完整记录实际变更、验证、风险和 stop decisions。

### 1.4 非目标

- 不处理 GitHub Issue #177 的 Doc output continuation wiring。
- 不处理 GitHub Issue #178。
- 不新增统一 tool authorization、credential broker、role schema、BusinessSource、safe/raw 双写或通用敏感字段 validator。
- 不改变 Engine `ToolCallRequest`、Runner provider payload 或 Tool outcome canonical shape；直接证据显示它们是机械 typed transport，不拥有本缺陷。
- 不让 Host import `dayu.fins`；Host 只机械读取 accepted outcome 中精确的 `result.value.citation` JSON 字段。
- 不为旧 EventLog/schema 提供 migration、compatibility reader、fallback message 或 legacy fixture；本 WU 按 fresh schema 起库。
- 不重新审判 R01 的 Doc complete-input contract，不恢复 source/directory cap，不改 output/navigation guidance。
- 不改 design truth、umbrella/control docs 或 prior artifacts。

## 2. 语义 owner 与边界

| 语义 | 唯一 owner | 允许消费者行为 | 禁止行为 |
| --- | --- | --- | --- |
| LLM 返回的结构化 tool call | Engine/contracts `ToolCallRequest` | 机械传递 name/arguments/provider state | Engine 推断 Host wait、citation 或安全字段 |
| Host 已接受的原始 arguments identity | ToolRuntime accept boundary | canonical JSON + digest；交给 request-atom writer | redaction、字段名分类、safe/raw 双写 |
| `TOOL_CALL_REQUESTED` durable atom | 新 `dayu/host/tool_call_request.py` | ordinary/awaiting 共用 writer；reader 严格验证 | 两个入口各写一套 payload |
| waiting governance | `dayu/host/waiting.py` + `TOOL_AWAITING` | wait/adaptor/snapshot/external-job/link | 保存 arguments/digest，或从 wait id 猜 request id |
| query 的业务语义 | producer semantic query；缺失时 accepted projection 机械序列化 canonical args | 不做 key 分类 | synthetic “工具 X 请求参数”或下游 repair |
| tool schema name/description/params/enums/errors | 具体 ToolDefinition/tool producer 文件 | 自足、业务可读、必要引用标签有说明 | Host 代替 producer 打 blacklist 补丁 |
| accepted result LLM material | `accepted_result_projection.py` + `evidence.py` | 组合已验证 request、raw result、explicit citation | 从 opaque refs、日志、id、digest 猜业务事实 |
| Fins citation | `dayu/fins/domain/tool_models.py::Citation` 与 `dayu/fins/tools/read_runtime.py::_build_citation` | Host 机械 canonical JSON 渲染 | Host import Fins 或发明 BusinessSource |
| opaque refs | `evidence.py::AcceptedEvidenceEnvelope` internal provenance/audit | EventLog codec、audit/internal diagnostics round-trip | 进入 LLM material 或 readable source |
| RunInput/Memory/Compact/Trace | 各自机械 consumer | 只消费 shared typed material | 重新解析 envelope、重建 query/source、fallback 修补 |

没有直接证据表明当前内部 opaque refs 需要进入 compact provenance 或 Tool Trace readable summary。因此 R03 不创建“internal provenance view”新抽象；EventLog envelope 已是现有 internal source of truth。未来若有真实 internal-query consumer，需要另行证明并建立不能被 renderer 接受的独立类型，不能在本 R03 预建。

## 3. 当前代码证据与 root-cause call paths

### 3.1 ordinary accepted call

```text
ToolRuntimeHandle.execute
  -> _tool_fact_accept_candidate / _tool_fact_reuse_accept_candidate
  -> ToolAcceptCall(accepted_arguments=call.arguments,
                    normalized_arguments_digest=sha256({"arguments": args}))
  -> DefaultHostToolFactAcceptPort._accept_in_transaction
  -> _tool_call_requested_event_request
  -> _tool_call_request_payload_plan
       inline | PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON
       absent | inline | descriptor semantic_query
  -> TOOL_CALL_REQUESTED
  -> TOOL_RESULT_ACCEPTED.accepted_evidence_envelope.tool_query.request_event_ref
```

这条路径已经拥有正确的原始 arguments、冷热 payload 和 digest 基础，但实现被埋在 `tool_runtime.py` 私有函数中，awaiting 无法复用。

### 3.2 awaiting accepted call 与 resume

```text
ToolRuntimeHandle.execute
  -> _tool_awaiting_accept_candidate(accepted_arguments=call.arguments)
  -> DefaultHostToolAwaitingAcceptPort._accept_in_transaction
  -> waiting._tool_call_requested_event_request
       llm_safe_replay_arguments
       inline-only payload
       synthetic semantic query
  -> TOOL_AWAITING(tool_awaiting_payload 再写 redacted args + original digest)
  -> WaitRecord(created_event_id = TOOL_AWAITING)

resolve_wait
  -> _wait_tool_call_requested_event
       从 wait_id 字符串派生 request event id
       从 TOOL_AWAITING 重复 digest 证明 request
  -> wait resolution TOOL_RESULT_ACCEPTED

resume RunInput
  -> project_accepted_tool_result
  -> request arguments 不可用时 _resume_wait_fallback_message
```

这里同时存在正文被改写、digest 分裂、事件 id 猜测、重复 durable truth 和 fallback 掩盖 corruption。

### 3.3 LLM projection 与 opaque source

```text
TOOL_RESULT_ACCEPTED
  -> project_accepted_tool_result
       _request_atoms_projection
       _query_projection
          semantic_query
          else _contains_unsafe_argument_key -> limited signal
          else canonical args
       _source_projection
          known internal kind -> drop
          unknown kind -> "kind:id"
  -> AcceptedToolResultProjection(llm_material, source_locator_refs)
       -> RunInput
       -> durable Memory / memory renderer
       -> compact material / compactor input
       -> Tool Trace readable summary
```

`source_locator_refs` 当前被塞入同时携带 LLM text 的 `RunInputMaterialBlock`，类型边界允许 opaque refs 随 LLM material 传播；Tool Trace 又独立执行 `redact_sensitive_json_fields`。这不是单一 projection。

### 3.4 当前 source-owner 审计发现

- `dayu/engine/agent.py::_project_tool_outcome_for_llm` 与 `dayu/engine/runners/openai/payload.py` 只机械序列化 typed message/outcome/schema，当前 compliant，计划 no-diff。
- 所有 prompt assets 已逐文件人工读取；当前未发现 credential、opaque ref source guessing 或 Host governance 伪装成业务事实，计划 no-diff。
- current production tool schemas 没有 `api_key/password/credential/access_token` 参数。`dayu/tools/web/web_tools.py` 的 `password` 命中只属于 URL userinfo 解析，不是 LLM schema 参数。
- 三个真实 schema 自足性缺口必须在 owner 修正：
  - `dayu/host/tool_runtime.py::_fetch_more_tool_definition` 的 description 过短，`cursor/scope_token/limit` 无参数说明；
  - `dayu/tools/web/web_tools.py::_FETCH_WEB_PAGE_PARAMETERS.url` 无参数说明；
  - `dayu/fins/tools/fins_tools.py` 多个 read tool 的共用 `ticker/document_id` 无参数说明。
- `dayu/fins/tools/read_runtime.py::_build_citation` 由 `Citation.to_dict()` 输出 producer-owned business citation；这是当前唯一有直接 evidence 的 explicit citation owner。

## 4. 目标 contract 与 old-to-new data flow

### 4.1 新 canonical flow

```text
LLM tool call
  -> current ToolDefinition schema validation
  -> ToolRuntime exact canonical accepted arguments + normalized digest
  -> AcceptedToolCallRequestAtomInput
  -> build_tool_call_requested_event_request  [唯一 writer]
       ordinary ─┐
       awaiting ─┴─> TOOL_CALL_REQUESTED
                       exact args / same digest / optional producer query
  -> ordinary execution result
     or TOOL_AWAITING(governance + explicit request event ref only)
  -> TOOL_RESULT_ACCEPTED envelope(link to request atom; opaque refs internal)
  -> strict AcceptedToolResultProjection
       query = producer query | canonical accepted args
       source = exact result.value.citation | source-unavailable
       result = canonical raw outcome
  -> one typed LLM material
       -> RunInput
       -> Memory
       -> Compact readable evidence
       -> LLM-ready Tool Trace summary
```

### 4.2 新 request-atom writer

新增 `dayu/host/tool_call_request.py`，只定义一个 coherent request-atom input 与一个 writer，不做 facade：

```python
class ToolCallRequestEventOrigin(StrEnum):
    ORDINARY_ACCEPT = "host.tool_runtime.accept"
    AWAITING_ACCEPT = "host.tool_runtime.awaiting_accept"

@dataclass(frozen=True, slots=True)
class AcceptedToolCallRequestAtomInput:
    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    iteration_id: str
    tool_call_id: str
    tool_name: str
    tool_schema_digest: str
    tool_identity_digest: str
    accepted_arguments: Mapping[str, JsonValue]
    normalized_arguments_digest: str
    tool_fact_kind: str
    accept_idempotency_key: str
    semantic_input_digest: str
    semantic_query_text: str | None

def build_tool_call_requested_event_request(
    transaction: HostTransaction,
    *,
    atom: AcceptedToolCallRequestAtomInput,
    event_id: str,
    occurred_at: datetime,
    origin: ToolCallRequestEventOrigin,
) -> EventLogAppendRequest: ...
```

该 writer **只构造** `EventLogAppendRequest`，不 append、不分配或预测 `event_sequence`。真实 row 必须由调用方执行 `event_log_store.append_event(transaction, request).row` 取得；`EventLogAppendResult.row` 同时覆盖新插入和 same-body existing-row replay，并携带数据库实际分配的 `event_id/event_sequence`。

两个入口到 atom 的显式映射固定为：

| atom field group | ordinary accept | awaiting accept |
| --- | --- | --- |
| execution identity | `ToolFactAcceptCandidate.identity` | `ToolAwaitingAcceptCandidate.session_id/run_id/attempt_id/execution_id` |
| call identity/name/schema/args | `ToolFactAcceptCandidate.call` | `ToolAwaitingAcceptCandidate` 同名字段 |
| `tool_identity_digest` | **原样取** `ToolAcceptCall.tool_identity_digest` | **原样取** `ToolAwaitingAcceptCandidate.tool_identity_digest` |
| fact/idempotency | `candidate.tool_fact_kind` + `candidate.idempotency` | `tool_fact_kind="awaiting"` + candidate 的 accept idempotency fields |
| semantic query | `ToolAcceptCall.semantic_query_text` | `None` |

ordinary 只有真正写 accepted fact 时才进入该映射；低层 fake ack 允许的 `accepted_arguments=None` 不得进入 writer。builder 不重算 `tool_identity_digest`，不从 ToolDefinition/schema/log/digest 反推，也不因 ordinary/awaiting 来源不同改变 payload contract。

实施允许根据现有命名规范微调类型名，但不得改变 owner、输入语义或再包一层透传 facade。模块与所有新增/修改函数必须有完整中文 docstring（参数、返回、异常），签名不得使用 `Any/object`。

writer 的硬 invariant：

- `arguments_json = {"arguments": dict(accepted_arguments)}`；
- `sha256_digest_json(arguments_json) == normalized_arguments_digest`，否则写前失败；
- `arguments_payload_digest` 必须等于上述同一 digest；
- inline/descriptor 只由 `transaction.payload_inline_threshold_bytes` 决定；awaiting 不例外；
- descriptor kind 固定为 `TOOL_CALL_ARGUMENTS_JSON`；query descriptor kind 固定为 `TOOL_CALL_SEMANTIC_QUERY_TEXT`；
- semantic query 只能是 producer 显式提供的非空文本；缺失就是 `absent`，不得 synthetic；
- actor 固定为 `host.tool_runtime`，origin 只决定 source 诊断值；
- ordinary/awaiting 的 payload key set 完全相同，只有业务值（例如 `tool_fact_kind`、idempotency）不同。

### 4.3 `TOOL_CALL_REQUESTED` payload contract

唯一 payload 字段：

```text
session_id, run_id, attempt_id, execution_id, iteration_id,
tool_call_id, tool_name, tool_schema_digest, tool_identity_digest,
normalized_arguments_digest,
arguments_json_size_bytes, arguments_storage_kind,
arguments_inline_json, arguments_payload_ref, arguments_payload_digest,
tool_fact_kind, accept_idempotency_key, semantic_input_digest,
semantic_query_storage_kind, semantic_query_text,
semantic_query_payload_ref, semantic_query_digest
```

reader `tool_call_request_atoms` 必须额外证明：

1. event type 正确；
2. arguments storage shape 与 descriptor kind 正确；
3. 解析出的 `arguments_json` digest 等于 `arguments_payload_digest`；
4. `arguments_payload_digest == normalized_arguments_digest`；
5. query storage/digest shape 正确；
6. 任一不一致抛 `HostDurableError`，不返回 partial atoms。

### 4.4 `TOOL_AWAITING` payload contract

保留字段：

```text
session_id, run_id, attempt_id, execution_id, iteration_id,
wait_id, tool_call_id, tool_name,
tool_call_requested_event_ref={event_id,event_sequence},
await_spec, adapter_key, resume_policy,
snapshot_ref, external_job_ref,
accept_idempotency_key, semantic_input_digest
```

明确删除：

```text
normalized_arguments_digest
accepted_arguments
accepted_arguments_source_digest
任何 arguments payload/digest 副本
```

`TOOL_AWAITING` 的 `tool_call_requested_event_ref` 由同一 accept transaction 中先写入的真实 row 生成，不从 `wait_id` 或 prefix 反推。awaiting `_accept_in_transaction` 的不可变 sequencing 为：

1. mutation 前读取 accept idempotency record；same semantic digest 直接从既有 rows 返回 ack，不追加任何 fact，different digest 返回 conflict 且不写入；
2. shared writer 构造 `TOOL_CALL_REQUESTED` request；
3. `append_event(...).row` 取得新插入或 same-body existing row 的真实 `event_id/event_sequence`；禁止预估、硬编码 `0/null` 或从 wait id 派生 sequence；
4. 以该 row 构造 `tool_call_requested_event_ref`，传给 `_tool_awaiting_event_request`，随后 append `TOOL_AWAITING`；
5. 再依次 append `RUN_WAITING`、`ATTEMPT_SUSPENDED`，写 wait record、run/attempt state 与 idempotency result；
6. 上述步骤全部留在同一个 `HostTransactionRunner.run_write` transaction。步骤 2–5 任一异常都必须 rollback request row、awaiting row、后续 facts、wait/state/idempotency mutation；不得提交孤立 request atom。same-body existing request row replay 使用其真实 sequence继续，different-body identity conflict 抛错并整体 rollback。

### 4.5 resume 与 corruption contract

| corruption/negative case | 唯一处理 |
| --- | --- |
| awaiting payload 缺 request ref | `HostDurableError`；不 resolve、不 resume |
| ref shape 非 `{event_id,event_sequence}` | fail closed |
| ref 指向不存在 row | fail closed |
| ref 指向非 `TOOL_CALL_REQUESTED` | fail closed |
| session/run/attempt/execution 不同源 | fail closed |
| tool name/call id 不同源 | fail closed |
| request args inline/descriptor shape 损坏 | fail closed |
| request arguments payload digest mismatch | fail closed |
| normalized digest 与 arguments payload digest mismatch | fail closed |
| semantic query descriptor/digest mismatch | fail closed |
| accepted-result envelope 的 request ref/digest 与 atom 不一致 | fail closed |
| resume canonical args 不可读 | fail closed；删除 `_resume_wait_fallback_message` |
| canonical `TOOL_RESULT_ACCEPTED` projection 后 `llm_material` 缺失 | RunInput、Memory、Compact、LLM-ready Tool Trace 均抛 `HostDurableError` |
| Tool Trace 的 `TOOL_CALL_REQUESTED` row/atom 缺失或损坏 | `HostDurableError`；不输出 placeholder、limited signal 或 internal ref/digest |

失败关闭必须发生在写 wait resolution/resume facts 或构造 LLM input 之前；不得生成“继续回答但不重建 tool call”的 compatibility system message。四个 LLM consumer 不得 catch 后跳过单条 evidence、继续构造部分输入、返回 fallback/limited signal 或改投 internal refs；沿现有上层 durable-error path 暴露失败，R03 不新增 consumer-specific recovery。

### 4.6 query/source/material contract

- query：`semantic_query_text` 存在时原样使用；否则对 exact `arguments_json` 做 bounded canonical JSON 展示。bounded 只控制输出长度，不改变字段和值，也不按名字分类。
- source owner 签名固定为 `_source_projection(raw_outcome: JsonValue | None, diagnostics: list[str]) -> AcceptedToolResultSourceProjection`（命名可按现有惯例微调，输入语义不可改变）。`project_accepted_tool_result` 必须把 `_result_payload` 已完成 payload/digest 校验后取得的当前 `raw_outcome` 直接传入；不得从 envelope refs、result text、trace row 或未校验 payload 重新读取。
- canonical JSONPath 由现有 `accepted_tool_outcome_json(ToolCompletedOutcome(...))` contract 固定为 `kind == "completed" -> result` 为 object -> `result.ok is True` -> `result.value` 为 object -> `value.citation` 为 object。只有全部条件成立时，才对**整个 producer-owned citation object**调用 `canonical_json_dumps`；Host 不枚举、筛选、排序或解释 citation 业务 key，未知/新增 JSON member 也随整个 object 机械渲染。其它 outcome、缺失、拼错或非 object 均使用唯一文案 `该工具结果未提供业务来源。` 并记录 internal diagnostic。
- opaque envelope refs：完全不参与 source 投影；unknown、typo、internal kind 都不特殊分类。
- result：继续使用 accepted outcome canonical JSON 文本。
- renderer：`render_accepted_tool_evidence_for_llm(material: AcceptedToolEvidenceLLMMaterial) -> str` 只接受非 optional material；删除整体 fallback constant/branch。任一 canonical accepted result 缺 material 都按 §4.5 在四 consumer owner boundary 抛 `HostDurableError`。

这不是发明 `BusinessSource`。Host 只识别 producer 已公开的精确 `citation` 字段和 accepted outcome codec shape，不 import Fins，不解析 citation domain enum，不枚举 Fins citation keys，也不从 `url/path/document_id/ref_kind` 等 raw fields 猜来源。

### 4.7 Tool Trace 内外边界

- internal hot/cold row 可以继续保存 event id、tool call id、payload ref、digest、cursor/ref 等诊断字段；它们不属于 LLM-ready summary。
- `trace_summary.tool_request` 的 readable fields 只含 tool name、query、exact accepted arguments/arguments text 和明确状态；删除 redacted arguments 与 readable ref/digest 文案。
- `TOOL_CALL_REQUESTED` readable projection 不直接消费 event view 的 raw payload：先 `read_event_by_id(transaction, event.event_id)` 取得 canonical row，再调用 strict `tool_call_request_atoms(transaction, row)` 解析 inline/descriptor exact args与 semantic query，最后只做 bounded 展示。row/atom 缺失、错类型或 digest/storage 损坏统一抛 `HostDurableError`；不得展示 payload ref/digest，也不得输出“参数正文由 accepted-result 同源投影提供”等内部实现 placeholder。
- `TOOL_RESULT_ACCEPTED` summary 必须通过 strict shared projection 取得完整 query/args/source/material；缺 material 同样抛 `HostDurableError`。
- readable `trace_summary.tool_result` 精确新增两个字符串 mapping：`business_source_text = projection.source.text`、`business_source_state = projection.source.state.value`。state 直接复用现有 `AcceptedToolResultSourceState` 的 `available|unavailable`，不新建 enum/type、不复制 citation parser；`projection.source.diagnostic_reason` 只留 internal projection/diagnostic，不进入 business source 文本。

## 5. Slice 总览、依赖与最小性

| slice | 闭合目标 | 依赖 | 独立 review 边界 |
| --- | --- | --- | --- |
| S1 | ordinary/awaiting shared request atom + durable replay identity | 无 | durable writer/reader/link/resume corruption |
| S2 | 删除 blacklist repair + 完整逐文件 LLM source audit + owner schema 修正 | S1 exact atom | producer/schema/query source ownership |
| S3 | opaque refs internal-only，四消费者 propagation closure | S1、S2 | shared material 与 consumer separation |

Topic 3 与 Topic 4 必须留在一个 R03：Topic 3 决定 accepted request/query 的真源和 shared material；Topic 4 正好约束同一个 material 的 source/provenance 组成及其四个消费者。如果拆成两个 remediation，中间态只能是“query 已统一但 source 仍猜 opaque ref”，或“opaque ref 已删但各消费者仍从两套 safe args 重建 query”，两者都不是可接受 contract。

三片是最小 independently reviewable closure：S1 是 durable identity；S2 是 producer/source owner 与人工 inventory；S3 是同一 typed projection 的 propagation。把 S1 并入 S2 会让 schema 文本 review 混入事务/descriptor corruption；把 S2 与 S3 合并会使 owner audit 无法与 consumer propagation 独立核验；继续细分 S3 则会让 RunInput/Memory/Compact/Trace 在多个提交间暂时漂移，并迫使重复 fixture/fallback。不得增加第四片。

## 6. R03-S1 — ordinary/awaiting shared request atom 与 durable replay identity

### 6.1 目标结果

一个 transaction-safe、descriptor-capable、strict-digest request atom writer 同时服务 ordinary 和 awaiting；`TOOL_AWAITING` 只链接该 atom；resolve/resume 对断链或 digest corruption 失败关闭。

### 6.2 精确允许文件

生产：

- `dayu/host/tool_call_request.py`（新增）
- `dayu/host/tool_runtime.py`
- `dayu/host/waiting.py`
- `dayu/host/_event_payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/run_input.py`

测试：

- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_wait_awaiting_accept.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_accepted_result_projection.py`

文档：

- `dayu/host/README.md`
- `tests/README.md`

本 slice 不得修改其它 production/test/doc 文件。若直接证据要求扩出 allowlist，停止并回 plan review，不得顺手修改。

### 6.3 符号级改动

1. 新模块实现 §4.2 的 typed input、origin 与唯一 writer，并从 `tool_runtime.py` 移入：
   - `_ToolCallRequestPayloadPlan`
   - `_SemanticQueryPayloadPlan`
   - `_tool_call_request_payload_plan`
   - `_semantic_query_payload_plan`
   - request arguments/query descriptor ref/id helper
   - 只服务上述 writer 的 canonical size/digest helper
2. `tool_runtime.py::_tool_call_requested_event_request` 删除；ordinary accept 按 §4.2 显式从 `ToolFactAcceptCandidate.identity/call/idempotency/tool_fact_kind` 映射 atom，尤其将 `ToolAcceptCall.tool_identity_digest` 原样传入，不在 shared builder 重算或反推。
3. `waiting.py::_tool_call_requested_event_request`、`_accepted_arguments_json`、`_awaiting_semantic_query_text`、本地 `_payload_size_bytes` 删除；当前直接 source scan 已证明后三个 helper 都只被 waiting 本地 `_tool_call_requested_event_request` 调用，删除闭集完整。awaiting 按 §4.2 从 `ToolAwaitingAcceptCandidate` 同名字段显式映射 atom，尤其原样传入 `candidate.tool_identity_digest`，`semantic_query_text=None`，不从 structural `ToolCallRequest` 发明业务 query。
4. awaiting `_accept_in_transaction` 严格执行 §4.4 sequencing：shared writer 构造 request -> `append_event(...).row` 取得真实 row -> 用 row 的 `event_id/event_sequence` 构造 ref -> 传入 `_tool_awaiting_event_request` -> append `TOOL_AWAITING` -> 后续 facts/state/idempotency。`tool_awaiting_payload` 删除 accepted args/normalized digest 参数和字段，只新增该真实 ref；禁止预估/硬编码 sequence 或从 wait id 推导。任一后续失败由同一 `run_write` 整体 rollback；same-digest idempotent existing-record replay不追加，same-body existing request-row replay使用既有真实 sequence，different digest/body conflict不产生部分事实。同时从 `_event_payload.py` 删除已经失去调用方的 `llm_safe_replay_arguments` 及 redaction import；S2 再删除仍被 Tool Trace 使用的通用 taxonomy 模块。
5. `_wait_tool_call_requested_event` 先严格读取 `wait_record.created_event_id` 对应 `TOOL_AWAITING`，再读显式 request ref；删除 `_tool_call_requested_event_id_from_wait_id` 和 `_validate_wait_request_arguments_digest`。
6. resolve 路径调用 `tool_call_request_atoms` 完成正文/digest proof，构建 envelope 时只使用 typed atoms，不重复从 raw payload 读 digest。
7. `payload_resolution.py::tool_call_request_atoms` 新增 normalized/payload digest equality guard，并把“LLM-safe 参数”文案改成“Host 已接受的 exact canonical 参数”。
8. `accepted_result_projection.py::_request_atoms_projection` 对 canonical envelope 的 missing/broken/unreadable/mismatch request link 抛 `HostDurableError`，不产 limited query。
9. `run_input.py::_resume_wait_messages_from_current_start` 要求 strict projection 提供 exact arguments；删除 `_resume_wait_fallback_message` 与 safe/fallback docstring。

### 6.4 S1 tests 与反例

- ordinary small args 与 awaiting small args：payload key set、storage kind、arguments digest、query storage contract 相同；原始业务字段 `file_path`、`scope_token` 值不变。
- ordinary/awaiting large args：都走 `TOOL_CALL_ARGUMENTS_JSON` descriptor，reader 返回 exact args；hot EventLog 不内联大正文。
- optional semantic query：ordinary 显式 query 支持 inline/descriptor；awaiting 缺 producer query 为 `absent`，没有 synthetic 文本。
- `TOOL_AWAITING` exact key-set 断言；明确 absence assertions 覆盖三个被删字段和任何 `arguments_*` 字段。
- transaction linkage：awaiting payload 的 ref event id/sequence 与同事务真实 request row 一致。
- transaction rollback：分别在 request append 后、awaiting append 后、后续 run/attempt/wait/idempotency mutation 处注入异常，断言整组 EventLog rows、wait record、run/attempt state 和 idempotency record均未提交，不存在孤立 request atom。
- idempotent replay：同 key/same digest 返回既有 ack，不写第二组 facts；same-body existing request row 使用既有真实 sequence；different semantic digest 或 different-body event identity 冲突保持且无部分写入。
- identity mapping：ordinary payload 的 `tool_identity_digest` 精确等于 `ToolAcceptCall.tool_identity_digest`，awaiting 精确等于 `ToolAwaitingAcceptCandidate.tool_identity_digest`；用与 schema digest 不同的 sentinel证明 builder 未重算或反推。
- corruption matrix覆盖 §4.5，每个 case 断言无新 resolution/resume EventLog row、Run/Attempt 状态未被错误推进。
- 删除旧测试：`test_awaiting_accept_persists_only_llm_safe_replay_arguments`、legacy/abnormal awaiting fallback tests、`test_resume_wait_replays_only_llm_safe_arguments`；用 owner-contract tests 替换，不保留兼容分支倒逼生产。

### 6.5 S1 验证

```bash
source .venv/bin/activate
pytest \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_wait_awaiting_accept.py \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_accepted_result_projection.py -q

pytest tests/host -k 'tool_call_requested or awaiting_accept or replay_arguments or request_atom' -q
```

逐文件 coverage target：新增 `dayu/host/tool_call_request.py >= 95%`；其余每个修改 production file `>= 80%`。低于目标必须补 owner-level branch/corruption tests，不得 `pragma: no cover`、降低阈值或用 mock 固化旧 payload。

### 6.6 S1 完成/stop

S1 handoff 必须包含 shared writer contract、old/new payload snapshots、corruption matrix、测试/coverage/pyright 结果和精确 diff。若 upstream 无法提供 exact canonical arguments、需修改 Engine tool-call contract、需兼容旧 waiting facts或需 schema migration，立即停止回 controller。

## 7. R03-S2 — 删除 blacklist repair，修正 LLM source owners

### 7.1 目标结果

下游不再按字段名判断“安全”；prompt/schema/result/message 的每个真实 LLM source 在 owner 处自足。完成一份人工逐文件 inventory，并逐行消费 R01 §11。

### 7.2 精确允许文件

生产：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/tool_trace.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/run_input.py`
- `dayu/host/tool_runtime.py`
- `dayu/runtime/__init__.py`
- `dayu/runtime/json_redaction.py`（删除）
- `dayu/tools/web/web_tools.py`
- `dayu/fins/tools/fins_tools.py`

测试：

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`

文档：

- `dayu/host/README.md`
- `tests/README.md`

所有 `dayu/config/prompts/**`、`dayu/tools/doc_tools.py`、`dayu/tools/utils/provider.py`、Fins ingestion schema files、Engine files和对应 tests 在当前 evidence 下都是 **audited no-diff**，不属于 S2 edit allowlist。人工 inventory 仍必须逐文件记录它们。

### 7.3 删除项

- `accepted_result_projection.py::_contains_unsafe_argument_key`
- `arguments_summary_unsafe` diagnostic 与相关 limited-query branch
- `tool_trace.py::_redacted_json` 及其 import
- `dayu/runtime/json_redaction.py` 全模块；`dayu/runtime/__init__.py` **只改模块 docstring**，删除与该已删模块对应的“层中立 JSON 敏感字段脱敏”概览项及 ``dayu.runtime.json_redaction`` 当前模块列表项，不改 `from __future__`、`__all__`、import/re-export 或任何运行逻辑
- 所有 “LLM-safe request/replay arguments” 命名和 docstring
- 任何测试中的 fake `token/api_key/password/secret -> <redacted>` contract

保留 canonical JSON serialization、bounded text 和 digest；它们是格式/完整性，不是 LLM-safe normalization。

### 7.4 owner schema 修正

只修当前人工审计确认的三个缺口：

1. `fetch_more`
   - tool description 说明只续读上一条截断结果；
   - `cursor`/`scope_token` 说明必须原样使用上一条结果给出的引用标签，标签不是业务事实或推理依据；
   - `limit` 说明是可选本次补读单位数；
   - 不声称 Doc Issue #177 已完整 wiring。
2. `fetch_web_page.url`
   - 说明是要抓取的完整 `http/https` URL，优先使用 `search_web` 返回 URL；
   - 不在 schema 发明 credential fallback 或 URL blacklist。
3. Fins read tools
   - 使用两个模块级私有 schema helper 统一 `ticker` 与 `document_id` 说明；
   - `ticker` 说明自然股票代码写法；
   - `document_id` 说明只能来自同 ticker 的 `list_documents.documents[].document_id`，切换 ticker 后重新选择，禁止猜测；
   - 不改变九个工具名称、参数名、enum、required set、结果 shape 或 citation owner。

其它 schema 已 compliant 时 no-diff，禁止以“统一风格”为名扩大改写。

## 8. S2 人工逐文件 LLM source inventory baseline

本节是实施前冻结的 manual baseline。completion report 必须复制为 final inventory，追加 `actual diff/test evidence`，不能用 `rg` 输出替代。

### 8.1 Prompt assets

| file | exact source / LLM-facing evidence | owner | disposition |
| --- | --- | --- | --- |
| `dayu/config/prompts/base/agents.md` | base agent behavior fragment | config prompt owner | compliant / no-diff |
| `dayu/config/prompts/base/fact_rules.md` | 财报事实/引用规则 fragment | config prompt owner | compliant / no-diff |
| `dayu/config/prompts/base/soul.md` | base role fragment | config prompt owner | compliant / no-diff |
| `dayu/config/prompts/base/tools.md` | tool workflow；含 R01 Doc navigation | config prompt owner | compliant / no-diff；保留 Doc navigation |
| `dayu/config/prompts/scenes/audit.md` | scene system fragment | audit scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/confirm.md` | scene system fragment | confirm scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/conversation_compaction.md` | compactor system prompt | compactor owner | compliant / no-diff；label 明示非业务事实 |
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | compactor user schema/template | compactor owner | compliant / no-diff；字段/类型/示例自足 |
| `dayu/config/prompts/scenes/decision.md` | scene system fragment | decision scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/fix.md` | scene system fragment | fix scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/infer.md` | scene system fragment | infer scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/interactive.md` | interactive prompt | interactive scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/overview.md` | overview prompt | overview scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/prompt.md` | CLI prompt scene | prompt scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/regenerate.md` | regenerate prompt | regenerate scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/repair.md` | repair prompt | repair scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md` | real smoke scene prompt | smoke fixture owner | compliant / no-diff |
| `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md` | scenario smoke prompt | smoke fixture owner | compliant / no-diff |
| `dayu/config/prompts/scenes/smoke_host_public_multiturn.md` | multiturn smoke prompt | smoke fixture owner | compliant / no-diff |
| `dayu/config/prompts/scenes/wechat.md` | WeChat scene prompt | WeChat scene owner | compliant / no-diff |
| `dayu/config/prompts/scenes/write.md` | write scene prompt | write scene owner | compliant / no-diff |
| `dayu/config/prompts/manifests/audit.json` | fragment assembly metadata | scene manifest owner | not directly LLM-facing; referenced MD audited / no-diff |
| `dayu/config/prompts/manifests/confirm.json` | 同上 | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/conversation_compaction.json` | fragments + fallback/continuation policy text | compactor manifest owner | compliant / no-diff |
| `dayu/config/prompts/manifests/decision.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/fix.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/infer.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/interactive.json` | fragments/tool selection | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/overview.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/prompt.json` | fragments/tool selection | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/regenerate.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/repair.json` | fragment assembly metadata | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` | smoke assembly | smoke fixture owner | no-diff |
| `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json` | smoke assembly | smoke fixture owner | no-diff |
| `dayu/config/prompts/manifests/smoke_host_public_multiturn.json` | smoke assembly | smoke fixture owner | no-diff |
| `dayu/config/prompts/manifests/wechat.json` | fragments/tool selection | scene manifest owner | no-diff |
| `dayu/config/prompts/manifests/write.json` | fragment assembly metadata | scene manifest owner | no-diff |

人工检查结论：没有 prompt asset 需要 R03 修改。若 implementation 时直接 evidence 发生变化，只能先停回 plan review；不得扩大 scope。

### 8.2 Production tool schemas、result/error sources

| file | exact sources | LLM-facing | owner | disposition |
| --- | --- | --- | --- | --- |
| `dayu/tools/doc_tools.py` | 5 ToolDefinitions：`list_files/get_file_sections/search_files/read_file/read_file_section`；params/errors/results | yes | Doc tool producer | compliant / no-diff；完整消费 R01 §11 |
| `dayu/tools/web/web_tools.py` | `search_web/fetch_web_page` descriptions、params、errors、results | yes | Web tool producer | **modify-at-owner**：仅补 `url` description；其它 no-diff |
| `dayu/tools/web/web_search_projection.py` | search success summary/next action/hint | yes | Web result projection owner | compliant / no-diff |
| `dayu/tools/web/web_tool_projection_text.py` | Web failure/cancel/recovery text | yes | Web projection text owner | compliant / no-diff；R02 boundary retained |
| `dayu/tools/utils/provider.py` | `get_current_time` description、timezone enum/errors/result | yes | utils tool producer | compliant / no-diff |
| `dayu/fins/tools/fins_tools.py` | 9 read ToolDefinitions、params/errors/results | yes | Fins read tool producer | **modify-at-owner**：共用 `ticker/document_id` descriptions；其它 no-diff |
| `dayu/fins/tools/read_runtime.py` | 9 read result payload 与 exact `citation` | yes | Fins read result owner | compliant / no-diff；citation 是 business source 真源 |
| `dayu/fins/domain/tool_models.py` | `Citation` fields/`to_dict()` | yes via result | Fins citation owner | compliant / no-diff |
| `dayu/fins/tools/download_tools.py` | `start_fins_download` schema/errors/awaiting outcome | yes | Fins download producer | compliant / no-diff |
| `dayu/fins/tools/preprocess_tools.py` | `start_fins_preprocess` schema/errors/awaiting outcome | yes | Fins preprocess producer | compliant / no-diff |
| `dayu/fins/tools/upload_tools.py` | `start_fins_upload` schema/errors/awaiting outcome | yes | Fins upload producer | compliant / no-diff；`files` 是合法业务输入，不得 blacklist |
| `dayu/host/tool_runtime.py` | framework `fetch_more` schema/error/result | yes | Host framework tool owner | **modify-at-owner**：description + 3 param descriptions |
| `dayu/engine/agent.py` | ordinary `ToolMessage` outcome projection | yes | Engine outcome transport | compliant / no-diff；机械 typed serialization |
| `dayu/engine/runners/openai/payload.py` | system/user/assistant/tool messages + ToolSchema serialization | yes | provider payload adapter | compliant / no-diff；不解释业务语义 |
| `dayu/host/run_input.py` | resume messages、memory/material system messages | yes | Host RunInput owner | modify only to remove fallback/safe terminology |
| `dayu/host/evidence.py` | four-line evidence renderer | yes | Host evidence renderer | S3 modify source/fallback contract |
| `dayu/host/accepted_result_projection.py` | query/source/result/material | yes | Host accepted projection owner | S1/S2/S3 modify |
| `dayu/host/memory.py` + `durable/memory.py` | selected evidence material | yes | Memory projection/reader | S3 strict consume；不重建 |
| `dayu/host/compact_material.py` + `compact_pipeline.py` | compactor evidence/readable prompt | yes | compact material owner | S3 strict consume；opaque separation |
| `dayu/host/llm_compaction.py` | prompt assets + typed compact input -> Engine messages | yes | Host compactor request assembly | compliant / no-diff；不重建 source/query |
| `dayu/host/tool_trace.py` | readable request/result summaries | potentially LLM-readable | Tool Trace projection owner | S2/S3 modify；diagnostic refs 留 internal row |
| `dayu/host/durable/tool_trace.py` | hot rows/query/ref resolver | no，internal diagnostic/query | durable trace owner | no-diff；不把 internal row 当业务 source |
| `dayu/runtime/scene_prepare.py` | prompt fragment/context slot deterministic assembly | yes via final system prompt | runtime scene assembly | compliant / no-diff；只机械装配已审计 assets |

### 8.3 Tests/smokes 中的真实 LLM prompt/schema fixtures

| file | fixture evidence | disposition |
| --- | --- | --- |
| `tests/tools/test_doc_tools_provider.py` | R01 exact Doc schema/result/smoke calls | retain / no-diff |
| `tests/tools/test_combined_tools_acceptance.py` | effective framework `fetch_more` schema | retain behavior；S2 schema assertion由 Host owner test承担 |
| `tests/tools/web/test_web_tools_provider.py` | Web ToolDefinitions | modify `url` description assertion only |
| `tests/fins/test_fins_storage_provider.py` | 9 Fins read ToolDefinitions | modify common field description assertions |
| `tests/engine/runners/openai/test_payload_build.py` | messages/schema serialization fixture | not business-semantic owner / no-diff |
| `tests/engine/test_agent_phase3_tool_call.py` | ToolMessage roundtrip fixture | not R03 source owner / no-diff |
| `tests/host/public_smoke_support.py` | deterministic public Host tool schemas/messages | compliant test-only business fixture / no-diff |
| `tests/host/test_public_compact_smoke.py` | real compactor prompt assembly and evidence labels | S3 propagation assertions；不改 compactor schema truth |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | real prompt/tool assembly | compliant / no-diff |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | scenario prompts/tool schema | compliant / no-diff |
| `utils/smoke_host_public_multiturn.py` | real provider + public Host scene/tool prompt | compliant existing smoke / no-diff |
| `utils/smoke_host_public_conversation_memory.py` | real provider memory prompt/schema | compliant existing smoke / no-diff |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | real/scenario compactor prompts | compliant existing smoke / no-diff |
| `utils/smoke_host_public_awaiting_entrypoint.py` | public Host deterministic awaiting fixture | compliant boundary smoke；不是 R03 real-tool completion smoke |
| `utils/smoke_host_public_r03_semantic_ownership.py` | 新增真实 Doc/Web/Fins public-run smoke | S3 add；见 §11 |
| `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` | 新 smoke assembly/secret-output guard | S3 add |

其余命中 `SystemMessage/UserMessage/ToolDefinition/AgentRunRequest` 的 Engine/Host tests 只验证 typed transport、取消、retry、identity 或状态机，不定义新的业务 prompt/schema；completion inventory 必须列出实际 scan 命中并记录 `not-LLM-semantic-owner-with-evidence`，不能把它们误当成可随意改文案的 owner。

### 8.4 全仓 constructor scan 候选的逐文件人工分类

下表消费全仓 executable Python 文件中的 `AgentRunRequest/SystemMessage/UserMessage/ToolFunctionSchema/ToolDefinition` 候选；扫描范围为 `dayu/**/*.py`、`tests/**/*.py`、`utils/**/*.py`，README 与 prompt assets 分别由 §8.1、§9、§14 处理。分类依据是逐文件回看实际 constructor、literal、export 和调用目的，而不是把 `rg` 零命中当结论。

| file | direct evidence | final classification / R03 action |
| --- | --- | --- |
| `tests/contracts/test_tool_declaration.py` | 只构造 declaration contract 的重复/名称错误样本 | typed contract fixture；not LLM semantic owner / no-diff |
| `tests/engine/contracts/test_agent_run.py` | `hello` message 验证 request contract | typed transport fixture / no-diff |
| `tests/engine/test_agent_message_union.py` | `x` message 验证封闭消息联合/role | typed transport fixture / no-diff |
| `tests/engine/test_agent_phase2.py` | `hello` request 与 mock schema验证 agent loop | Engine orchestration fixture / no-diff |
| `tests/engine/test_agent_phase3_tool_call.py` | `calculate` + mock schema/outcome roundtrip | Engine ToolMessage transport fixture；§8.3 已列 / no-diff |
| `tests/engine/test_metadata_boundary.py` | `hello` request 验证 metadata 不进入协议 | boundary fixture / no-diff |
| `tests/engine/runners/openai/test_payload_build.py` | `sys/hi` + mock schema 验证 outbound serialization | provider payload serializer fixture；§8.3 已列 / no-diff |
| `tests/engine/runners/openai/test_payload_assistant_reasoning_content_preserved.py` | `hi` 验证 reasoning replay | provider transport fixture / no-diff |
| `tests/engine/runners/openai/test_cancellation_boundaries.py` | `hi` 验证 cancel checkpoints | lifecycle fixture / no-diff |
| `tests/engine/runners/openai/test_cancellation_no_done_event.py` | `hi` 验证 cancel terminal | lifecycle fixture / no-diff |
| `tests/engine/runners/openai/test_http_error_event.py` | `hi` 验证 HTTP failure events | transport/error fixture / no-diff |
| `tests/engine/runners/openai/test_http_unknown_status_runner.py` | `hi` 验证未知 HTTP status | transport/error fixture / no-diff |
| `tests/engine/runners/openai/test_request_identity.py` | `hi` 验证 request identity | identity fixture / no-diff |
| `tests/engine/runners/openai/test_response_cleanup_race.py` | `hi` 验证 response close race | lifecycle fixture / no-diff |
| `tests/engine/runners/openai/test_retry_backoff.py` | `hi` 验证 retry/backoff | lifecycle fixture / no-diff |
| `tests/engine/runners/openai/test_runner_b3_extra.py` | `hi` 验证 provider extra/body | transport fixture / no-diff |
| `tests/engine/runners/openai/test_runner_diagnostics.py` | `hi` 验证 diagnostics | diagnostic fixture / no-diff |
| `tests/engine/runners/openai/test_stream_idle.py` | `hi` 验证 idle/heartbeat | lifecycle fixture / no-diff |
| `tests/engine/runners/openai/test_stream_usage_capability_gating.py` | `hi` 验证 usage capability | transport fixture / no-diff |
| `tests/engine/runners/openai/test_streaming_capability_and_content_type.py` | `hi` 验证 stream/content-type | transport fixture / no-diff |
| `tests/host/test_local_proxy_engine_ingest.py` | `hello` request 验证 Host/Engine proxy ingest | Host boundary fixture / no-diff |
| `tests/host/test_dispatch_scheduler.py` | `dispatch after lag`、proactive `system/user` 与 mock ToolDefinition | scheduler/compaction state fixture / no-diff |
| `tests/host/test_engine_ingest_mapping.py` | reactive `system/user` request | ingest/state fixture / no-diff |
| `tests/host/test_logging.py` | `_SECRET_PROMPT` 用于证明日志不泄漏 | security diagnostic fixture；不是业务 prompt owner / no-diff |
| `tests/host/test_compaction_operation.py` | `system/user` 构造 compaction lifecycle request | compaction state fixture / no-diff |
| `tests/host/test_tool_trace_queries.py` | UserMessage 只验证 runner-input reconstruction | internal trace query fixture / S3仅改传播 assertions |
| `tests/host/test_run_input_builder.py` | resume/current/system messages + mock ToolDefinition | real Host LLM-input owner test / S1-S3 modify |
| `tests/host/test_public_compact_smoke.py` | default compactor prompt、public Host、mock long tool schema | real compactor prompt fixture / S3 propagation assertions |
| `tests/host/public_smoke_support.py` | deterministic public Host ordinary/awaiting schemas | public boundary fixture / no-diff |
| `tests/host/test_toolruntime_executor.py` | mock ToolDefinition 执行边界 | ToolRuntime state fixture / no-diff |
| `tests/host/test_phase6_toolruntime_integration.py` | mock ToolDefinition ordinary accept integration | ToolRuntime integration fixture / no-diff |
| `tests/host/test_phase7_waiting_integration.py` | mock awaiting ToolDefinition | waiting state fixture / no-diff |
| `tests/host/test_per_run_tool_selection.py` | mock ToolDefinition selection | schema selection fixture / no-diff |
| `tests/host/test_tooling_options.py` | mock ToolDefinition option assembly | construction fixture / no-diff |
| `tests/host/test_tool_runtime_schema_projection.py` | mock ToolDefinition schema projection | schema transport fixture / no-diff |
| `tests/host/test_toolruntime_diagnostics.py` | mock ToolDefinition diagnostics | diagnostic fixture / no-diff |
| `tests/host/test_toolruntime_duplicate_governance.py` | mock ToolDefinition duplicate decisions | governance fixture / no-diff |
| `tests/host/test_toolruntime_effective_bundle.py` | mock ToolDefinition + framework injection | schema/effective-bundle fixture / no-diff |
| `tests/host/test_toolruntime_truncation_fetch_more.py` | mock truncating tool + real framework schema | Host framework schema owner test / S2 modify |
| `tests/host/test_host_activity_event_projection.py` | mock ToolDefinition activity projection | UI/activity diagnostic fixture / no-diff |
| `tests/runtime/test_tools_discovery.py` | mock ToolDefinition/provider discovery | discovery contract fixture / no-diff |
| `tests/runtime/test_tools_discovery_digest.py` | mock ToolDefinition digest stability | digest fixture / no-diff |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | real smoke assembly + conflict mock | real smoke fixture / no-diff |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | scenario prompts + conflict mock | real scenario fixture / no-diff |
| `tests/service/test_host_assembly.py` | mock ToolDefinition composition | Service construction fixture / no-diff |
| `tests/tools/test_combined_tools_acceptance.py` | combined current schemas + framework injection | owner acceptance fixture / no-diff |
| `tests/tools/web/test_diagnose_web_access.py` | mock schema用于诊断工具 import/assembly 测试 | diagnostic fixture / no-diff |
| `tests/tools/web/test_smoke_web_ci.py` | mock schema用于 Web CI execution shell | tool execution fixture；不定义生产 schema / no-diff |
| `utils/smoke_async_agent_providers.py` | `_PROMPT` 进入真实 provider `AgentRunRequest` | real provider smoke prompt；业务中性、无 refs/credentials / no-diff |
| `utils/smoke_host_public_awaiting_entrypoint.py` | public awaiting mock ToolDefinition + finance assistant prompt | public waiting boundary fixture / no-diff；不替代 R03 real-tool smoke |
| `utils/smoke_host_public_multiturn.py` | real provider/public Host + smoke fact schema/prompts | real public smoke fixture / no-diff |
| `utils/smoke_host_public_conversation_memory.py` | real provider/public Host + finance memory schema/prompts | real memory smoke fixture / no-diff |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | scenario prompts + finance mock schema + compactor material | real/scenario LLM fixture / no-diff |
| `utils/diagnose_web_access.py` | operator diagnostic input/output，无 Agent message/schema constructor | not LLM-facing / no-diff |
| `dayu/contracts/__init__.py` | 只导出 `ToolDefinition/ToolFunctionSchema` public contract | package export；不产生 LLM 文本 / no-diff |
| `dayu/contracts/tool_declaration.py` | 定义 typed declaration/decorator，并机械承接 producer 提供的 name/description/parameters | schema shape/validation owner，不是具体业务文案 owner / no-diff |
| `dayu/contracts/tool_schema.py` | 定义 `ToolFunctionSchema` 等 typed shape 与声明期结构校验 | schema contract owner；不产生具体 schema 文案 / no-diff |
| `dayu/engine/__init__.py` | 只重导出 Engine request/message/schema contracts | package export；不产生 LLM 文本 / no-diff |
| `dayu/engine/_default_runner.py` | 从 `AgentRunRequest` 装配默认 Runner | provider assembly；不读取/改写消息或 schema 语义 / no-diff |
| `dayu/engine/contracts/__init__.py` | 只重导出 Agent request/message contracts | package export / no-diff |
| `dayu/engine/contracts/agent_run.py` | 校验 messages 非空且属于封闭 union | typed request owner；不产生 LLM 文本 / no-diff |
| `dayu/engine/contracts/messages.py` | 定义 `SystemMessage/UserMessage` 等 content carrier | typed message owner；content 由 Host/config producer 提供 / no-diff |
| `dayu/engine/runners/openai/_types.py` | 定义 outbound schema/message `TypedDict` | provider wire shape；不产生具体文案 / no-diff |
| `dayu/fins/tools/provider.py` | 调用 `build_fins_read_tool_definitions` 并校验/聚合九个 definitions | discovery assembly；具体 schema owner 是 `fins_tools.py` / no-diff |
| `dayu/host/admission.py` | 使用 definitions 生成 selected display-name snapshot 与治理摘要 | Host admission/governance；不产生 ToolFunctionSchema 文案 / no-diff |
| `dayu/host/api.py` | public Host/worker protocol 传递 typed `AgentRunRequest` | lifecycle API；不构造 LLM source / no-diff |
| `dayu/host/compaction_operation.py` | state 仅持有 `AgentRunRequest` 与 compact input | compaction lifecycle；真实 prompt assembly 在 `llm_compaction.py` / no-diff |
| `dayu/host/dispatch.py` | 从 `run_input` 结果机械构造 `AgentRunRequest` | Host dispatch consumer；不得重建 query/source / no-diff |
| `dayu/host/local_proxy.py` | 把已构造 request 交给 Engine 并转发 event stream | transport proxy / no-diff |
| `dayu/host/tool_runtime_schema_projection.py` | 对 producer schema 做 JSON/digest projection | diagnostic identity；不改写 description/parameters / no-diff |
| `dayu/runtime/tools_discovery.py` | 聚合 definitions、校验名称并计算 schema digest | runtime discovery；不拥有具体 LLM 文案 / no-diff |
| `dayu/service/host_assembly.py` | Fins awaiting 分支按名称调用现有三个 `build_fins_*_tool` producer | Service assembly；不复制 schema 文案 / no-diff |
| `dayu/tools/__init__.py` | 包概览只提及声明 contract | not LLM-facing / no-diff |
| `dayu/tools/web/provider.py` | 配置 Web runtime，调用 `build_web_tool_definitions` 并校验集合 | discovery/provider assembly；具体 schema owner 是 `web_tools.py` / no-diff |
| `tests/contracts/test_package_exports.py` | 只断言 contracts package export symbol 集 | package surface fixture / no-diff |
| `tests/engine/runners/openai/test_runner_only_emits_runner_event.py` | symbol 名只出现在 EngineEvent export deny-list | architecture boundary fixture / no-diff |
| `tests/engine/test_import_boundary.py` | `ToolDefinition` 只用于 forbidden import/export symbol set | architecture boundary fixture / no-diff |
| `tests/engine/test_package_exports.py` | 只断言 Engine public export symbol 集 | package surface fixture / no-diff |
| `tests/fins/test_fins_ingestion_tools.py` | `ToolDefinition` 用于 ingestion schema 内部字段泄漏断言 | real Fins awaiting schema owner test；current compliant / no-diff，纳入 aggregate regression |
| `tests/host/recovery_support.py` | fake WorkerProxy 仅接收 typed request | recovery harness；不构造业务 prompt/schema / no-diff |
| `tests/host/stress_support.py` | stress WorkerProxy 仅接收 typed request | stress harness / no-diff |
| `tests/host/test_active_cancel_dispatch.py` | fake proxy `accept` 的 request 类型签名 | cancellation lifecycle fixture / no-diff |
| `tests/host/test_compaction_cancellation_scope.py` | fake compactor runner 只观察 typed request/cancellation | compaction cancellation fixture / no-diff |
| `tests/host/test_effective_execution_config.py` | recording proxy 保存 request 以断言 execution config | configuration projection fixture / no-diff |
| `tests/host/test_import_boundary.py` | `ToolDefinition` 只用于 Host root forbidden export set | architecture boundary fixture / no-diff |
| `tests/host/test_llm_compaction.py` | fake runner 捕获真实 compactor `AgentRunRequest` | real compactor prompt owner test；assets/assembly已 compliant / no-diff |
| `tests/host/test_open_host_runtime.py` | recording proxy 观察 public Host 生成的 request | runtime/lifecycle fixture / no-diff |
| `tests/host/test_phase5_local_execution_integration.py` | fake proxy 接收 request 验证 local execution | integration lifecycle fixture / no-diff |
| `tests/host/test_public_lifecycle_smoke.py` | public lifecycle fake proxy 接收 request | lifecycle smoke；非真实 LLM source audit smoke / no-diff |
| `tests/host/test_public_open_host_options.py` | proxy 接收 request 验证 public options | option assembly fixture / no-diff |
| `tests/host/test_public_retry_replay.py` | sequenced proxy 保存 request 验证 retry/replay | replay lifecycle fixture / no-diff |
| `tests/host/test_storage_maintenance.py` | no-op proxy request 签名用于 storage maintenance 场景 | storage fixture / no-diff |
| `tests/host/test_storage_usage_report.py` | no-op proxy request 签名用于 usage report 场景 | storage fixture / no-diff |
| `tests/host/test_submit_followup_public_contract.py` | recording proxy 保存 follow-up request | public lifecycle fixture；prompt 由 RunInput owner测试覆盖 / no-diff |
| `tests/host/test_watch_session_events.py` | fake proxy request 签名用于 event watch 场景 | event-stream fixture / no-diff |
| `utils/smoke_web_ci.py` | 通过真实 Service discovery 取得 `ToolDefinition` 并直接执行 callable | real Web execution smoke；不自定义 LLM prompt/schema / no-diff |

completion report 必须重新运行：

```bash
rg -l 'AgentRunRequest|SystemMessage|UserMessage|ToolFunctionSchema|ToolDefinition' \
  dayu tests utils --glob '*.py' | sort
```

逐路径与本节及 §8.2/§8.3 做集合核对，只允许新增本计划列出的 R03 smoke/test；任何其它新增 semantic fixture 必须先回 plan review。transport fixture 的短 literal 不需要被改写成财报 prompt，也不得借 R03 扩大 Engine/Host state tests。

## 9. R01 §11 mandatory handoff 逐行消费

以下每行都必须在 R03 completion final inventory 中保留；“R03 disposition”是对 R01 final state 的消费，不是重新裁决。

### 9.1 五个 ToolFunctionSchema descriptions

| R01 row | R03 disposition |
| --- | --- |
| `list_files` description | retain/no-diff；完整 `total/returned/scanned_entries` 与 navigation 语义不变 |
| `get_file_sections` description | retain/no-diff；大文件先定位章节是 output/navigation efficiency |
| `search_files` description | retain/no-diff；只保留 `result_limit` partial 语义 |
| `read_file` description | retain/no-diff；字符 output partial 语义合法 |
| `read_file_section` description | retain/no-diff；ref/navigation 与 output partial 合法 |

### 9.2 五组 parameter descriptions

| R01 row | R03 disposition |
| --- | --- |
| list `directory/pattern/recursive/limit` | retain/no-diff；无 source input cap |
| sections `file_path/limit` | retain/no-diff；`file_path` 不得被 blacklist |
| search `query/directory/include_types/limit` | retain/no-diff |
| read `file_path/start_line/end_line` | retain/no-diff；行范围是 output narrowing |
| read-section `file_path/ref` | retain/no-diff；ref 是必要业务导航标签且自解释 |

### 9.3 五组 error/message/hint owners

| R01 row | R03 disposition |
| --- | --- |
| argument validation `_DocBusinessFailure` | retain/no-diff |
| `_project_doc_paths` | retain/no-diff；路径是工具 owner 的合法业务输入 |
| business exception projection | retain/no-diff |
| cancellation projection | retain/no-diff |
| former source budget failure/catch/hints | 继续 absent；不得恢复或转交 Issue #177 |

### 9.4 五组 result keys

| R01 row | R03 disposition |
| --- | --- |
| list final keys | retain exact set；no-diff |
| search final keys | retain exact set/reason；no-diff |
| read final keys | retain output partial fields；no-diff |
| sections final keys | retain；no-diff |
| read-section final keys | retain；no-diff |

### 9.5 其它逐文件 source

| R01 row | R03 disposition |
| --- | --- |
| `dayu/config/prompts/base/tools.md` Doc workflow | retain/no-diff；不误删“大文件先看 sections” |
| `tests/tools/test_doc_tools_provider.py` exact descriptions | retain/no-diff |
| 同文件 real complete-input smoke fixture | retain/no-diff；不把它当 R03 public-run smoke |
| 同文件 key/absence/source assertions | retain/no-diff |
| `tests/tools/test_combined_tools_acceptance.py` | retain/no-diff；不声称 Issue #177 完成 |
| `dayu/tools/doc_provider.py` | not LLM-facing operator/composition；no-diff |
| `dayu/config/tool_discovery.json` | not LLM-facing raw config；no-diff |
| `dayu/config/README.md` R01 config text | development doc；R01 内容 no-diff |
| `tests/README.md` R01 test ownership text | 保留 R01 已完成内容；R03 只追加当前 Host/schema test 事实 |
| root `README.md` | user doc；R03 无安装/CLI workflow 变化，no-diff |

R03 source scan 若再次看到已删除的 source cap token，只能作为 unexpected regression 处理；不得借 R03 修改 R01 owner 或重新设计 complete-input。

## 10. S2 tests、validation 与 handoff

### 10.1 tests

- accepted projection：合法 `file_path/scope_token/password-like-but-business-name` 均机械显示；不再有 unsafe classifier branch。测试字段优先使用真实 current schema，不保留 fake-secret compatibility fixture。
- Tool Trace：request/result summary 使用 exact args；descriptor ref/digest 只留 internal row，不进入 readable summary。
- `fetch_more`：exact description/param descriptions，明确 cursor/scope token 是引用标签；运行行为不变。
- Web：`url` description exact assertion；R02 Web policy/error/result tests保持。
- Fins：九个 read definitions 的 `ticker/document_id` exact descriptions；tool names/required/enums/results/citation unchanged。
- Doc/base prompt/Engine serializer：只做 no-diff evidence，不制造空测试改动。

### 10.2 commands

```bash
source .venv/bin/activate
pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_toolruntime_truncation_fetch_more.py \
  tests/tools/web/test_web_tools_provider.py \
  tests/fins/test_fins_storage_provider.py -q

pytest \
  tests/tools/test_doc_tools_provider.py \
  tests/tools/test_combined_tools_acceptance.py \
  tests/runtime/test_import_boundary.py \
  tests/runtime/test_scene_assets_migration.py \
  tests/engine/runners/openai/test_payload_build.py \
  tests/engine/test_agent_phase3_tool_call.py -q
```

逐文件 coverage target：所有修改 production file `>=80%`；`accepted_result_projection.py`、被删 blacklist 对应 branches 与新增 schema helper `>=90%`。删除模块不以 coverage 代替 source/diff proof。

### 10.3 source gates

```bash
rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|unsafe_argument|safe_arguments|accepted_arguments_source_digest' dayu tests
rg -n 'redact_sensitive_json_fields|json_redaction|_SENSITIVE_KEY_FRAGMENTS|JSON_REDACTION_MARKER' dayu tests
rg -n '_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text' dayu tests
rg -n 'api_key.*token.*secret.*password|password.*secret.*token.*api_key' dayu/host dayu/runtime tests/host
```

预期前三组没有 production/test contract 命中；第四组每个命中必须人工归属，不能通过扩充正则或删合法 config/diagnostic security code求零。所有 grep 都只是 gate，人工 inventory 才是 completeness proof。

## 11. R03-S3 — opaque refs internal-only propagation closure

### 11.1 目标结果

共享 LLM projection 和四个消费者只携带 explicit query/result/citation；opaque refs 保留在 EventLog envelope/audit，类型上与 renderer/RunInput material 分离。

### 11.2 精确允许文件

生产：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/tool_trace.py`

测试/真实 smoke：

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`（新增）
- `utils/smoke_host_public_r03_semantic_ownership.py`（新增；`utils/` 依 AGENTS 无 coverage 要求）

文档：

- `dayu/host/README.md`
- `tests/README.md`

明确 no-diff：`dayu/host/compaction.py` 的 `PromptLocalProvenanceEntry`、`dayu/host/durable/tool_trace.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/domain/tool_models.py`。前两者是 internal provenance/diagnostic owner；后两者已经提供 explicit citation。

### 11.3 符号级改动

1. `AcceptedToolResultProjection` 删除 `source_locator_refs` 与 `OpaqueEvidenceRef` import。
2. `project_accepted_tool_result` 把 `_result_payload` 已 digest-check 的当前 `raw_outcome` 直接传给 `_source_projection(raw_outcome, diagnostics)`；该 helper 只按 §4.6 的 `accepted_tool_outcome_json` exact path检查 object shape，并机械 canonical-render 整个 citation object。删除 envelope 参数依赖、`_INTERNAL_SOURCE_REF_KINDS`、`_READABLE_SOURCE_SEPARATOR`、`_readable_ref_text`；不枚举 citation keys。
3. `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 改为不声称 Host 做过“安全展示”判断的业务中性文案。
4. `render_accepted_tool_evidence_for_llm` 参数改为非 optional；删除 `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` 和整体 fallback branch。canonical `TOOL_RESULT_ACCEPTED` projection 缺 `llm_material` 时，RunInput、Memory、Compact、LLM-ready Tool Trace 四个 owner boundary 一律抛 `HostDurableError`；不得 skip、consumer-specific catch/recovery、fallback、limited signal或继续构造部分 LLM input。
5. `RunInputMaterialBlock`、`run_input_material_block`、`InitialEvidenceMaterial` 删除 `source_locator_refs`；`_provenance_from_evidence_blocks`/`_evidence_provenance` 对 internal `PromptLocalProvenanceEntry.source_locator_refs` 固定传空 tuple。EventLog envelope 仍保存原 refs，不新建重复 view。
6. `memory.py::_selected_evidence_text` 要求 TOOL_RESULT_ACCEPTED projection event 有 typed material；没有则抛 `HostDurableError`，不跳过该 evidence、不渲染 fallback。
7. `run_input.py`、`compact_material.py`/`compact_pipeline.py` 在 accepted-evidence branch 先验证并收窄非空 typed material；缺失均抛 `HostDurableError`，有值才调用唯一 renderer。沿现有上层 durable error path终止当前 projection/input construction，不新增局部 catch。
8. Tool Trace 的 `TOOL_CALL_REQUESTED` branch 用 `read_event_by_id` + strict `tool_call_request_atoms` 解析 canonical row，inline/descriptor 都展示 bounded exact args/query；删除 `_tool_request_summary_from_payload` 的 raw-payload/redaction/descriptor-placeholder 行为，损坏抛 `HostDurableError`。readable result summary 只从 shared projection 映射 `business_source_text=projection.source.text` 和 `business_source_state=projection.source.state.value`，缺 material抛 `HostDurableError`；删除 readable request/result map 中 ref/digest source 文案，internal row columns保持。

### 11.4 propagation/negative tests

建立一组共享 sentinel fixture：

```text
ref_kind = "fliing-typo"
ref_id   = "opaque-should-never-reach-llm"
internal ref_kind = "eventlog"
internal ref_id   = "event-internal-only"
internal-kind typo ref_kind = "eventlogg"
internal-kind typo ref_id   = "event-typo-should-never-reach-llm"
```

同一个 accepted result 同时携带上述 `source_refs/locator_refs`，分别验证：

- envelope codec round-trip 后 refs 原样存在，证明 internal provenance 未被删除；
- `AcceptedToolResultProjection` public fields/LLM material 无 OpaqueEvidenceRef；
- RunInput messages 无 `fliing-typo/eventlog/eventlogg` sentinel kind/id；
- Conversation Memory selected evidence 无三组 sentinel kind/id；
- compactor `EvidenceReadableItemVNext.source_note` 无三组 sentinel kind/id；
- Tool Trace `trace_summary.tool_result.business_source_text` 无三组 sentinel kind/id，internal hot row仍可保留独立诊断 refs/ids；
- no citation、`citaiton` 拼错、citation 非 object 都输出同一 unavailable 文案，不尝试 ref fallback；
- 用真实 `accepted_tool_outcome_json(ToolCompletedOutcome(ToolResultSuccess(ok=True, value={"citation": citation_object}, meta=None)))` 构造 raw outcome；不得手写与 codec 脱节的假 shape。包含额外未知 JSON member 的整个 `citation_object` 在四消费者中 canonical text 完全相同，证明 Host 没有枚举/筛选 producer keys；
- citation object 中的业务值允许出现，因为它来自 producer-owned explicit citation，不是 opaque envelope ref；
- readable Tool Trace `TOOL_CALL_REQUESTED` 对 inline/descriptor 都经 strict atom resolver展示 exact bounded args/query；request row missing、wrong type、storage/digest mismatch均抛 `HostDurableError`，且输出中不存在 payload ref/digest 或内部 placeholder 文案；
- `trace_summary.tool_result.business_source_text/state` 分别严格等于 shared `projection.source.text/state.value`，`diagnostic_reason` 不进入业务来源字段；
- 为 RunInput、Memory、Compact、LLM-ready Tool Trace 各造 canonical accepted result `llm_material=None` corruption，四处均断言 `HostDurableError` 且没有 skip/fallback/limited output；
- 删除/替换 `test_projection_missing_material_uses_owner_fallback`、Memory 中 `render_accepted_tool_evidence_for_llm(None)` 期望，以及所有旧 `工具证据不可用；缺少可安全展示...` / `业务来源不可用；工具结果未提供可安全展示...` assertions；新断言只接受 strict error 或 `该工具结果未提供业务来源。`，不保留 alias/兼容文本；
- request link/digest corruption 继续按 S1 fail closed，不能因 source unavailable 被降级吞掉。

### 11.5 S3 tests

```bash
source .venv/bin/activate
pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_public_compact_smoke.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q

pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  -k 'source or ref or projection or memory or compact or trace or citation' -q
```

每个修改 production file coverage target `>=80%`；`evidence.py` renderer/source branches与 `accepted_result_projection.py` citation/negative branches `>=90%`。

## 12. 真实 public-run smoke

### 12.1 为什么现有 smoke 不足

`utils/smoke_host_public_awaiting_entrypoint.py` 使用 deterministic mock awaiting tool；`utils/smoke_host_public_multiturn.py` 使用真实 provider/public Host 装配但业务工具是 `record_smoke_fact`。它们保留为边界 smoke，却不能证明真实 Doc/Web/Fins owner 的 R03 传播。因此新增一个窄的 R03 smoke，不改现有通用脚本。

### 12.2 新 smoke contract

`utils/smoke_host_public_r03_semantic_ownership.py` 必须：

- 通过 current `ConfigLoader -> ToolsDiscovery -> ScenePrepare/Service assembly -> open_host -> ensure_session -> submit public turn` 运行，不直接调用 Host 私有 accept helper；
- 使用真实 configured model provider，不用 scripted/fake runner；
- ordinary Doc run 调用真实 Doc ToolDefinition 读取调用方提供的 `--doc-file`；
- ordinary Web run 调用真实 `search_web` 或 `fetch_web_page`；
- Fins run 调用真实 `start_fins_preprocess`（或调用方显式选择的 current Fins awaiting tool），经过 production wait adapter/poller accept/resume；不得手工写 wait result；
- 通过 Host owner read/projection API读取 Memory、Compact、Tool Trace；若某 read 只有内部 diagnostic API，必须在脚本中明确标记 internal read，不把它伪装成 public product API；执行链本身必须是 public run；
- 断言 ordinary/awaiting request atom exact args/digest、`TOOL_AWAITING` 无副本、四消费者 citation/source 一致、opaque sentinel 不泄漏；
- stdout 不打印 provider secret、headers、完整 prompt、完整 result payload、opaque refs 或本地 credential；只打印 bounded pass/fail summary。

建议 CLI：

```text
--workspace-root PATH
--scene-id ID
--doc-file PATH
--web-query TEXT
--fins-ticker TEXT
--fins-document-id TEXT
--fins-awaiting-tool start_fins_preprocess|start_fins_download|start_fins_upload
--keep-workspace
```

completion 中的实际运行命令必须给出非秘密参数和结果；workspace 必须有真实 provider credential、可访问 Web 网络以及真实 Fins source/processed fixture。缺任一前置条件时不能把 smoke 标成 skipped/pass，也不能用 fake tool 替代；R03 completion 停止并报告未满足前置条件。

该 aggregate hard gate 不分层降级：现有 full smoke 已包含 Doc ordinary run，新增 Doc-only/minimal path 不能替代 Web 与 Fins awaiting closure。S1/S2/S3 可先各自完成其 approved slice gate；若 aggregate 时外部环境仍缺失，只记录真实 blocker，不回退已接受 slice、不弱化 full smoke，也不重做 fake/scripted 证据。

### 12.3 smoke command template

```bash
source .venv/bin/activate
python utils/smoke_host_public_r03_semantic_ownership.py \
  --workspace-root "$R03_SMOKE_WORKSPACE" \
  --scene-id interactive \
  --doc-file "$R03_DOC_FILE" \
  --web-query "OpenAI official documentation" \
  --fins-ticker "$R03_FINS_TICKER" \
  --fins-document-id "$R03_FINS_DOCUMENT_ID" \
  --fins-awaiting-tool start_fins_preprocess \
  --keep-workspace
```

脚本实现不得把显式参数藏入 extra payload；所有参数使用 typed dataclass 和直接函数参数。

## 13. Aggregate validation

### 13.1 受影响 suites

```bash
source .venv/bin/activate
pytest \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_wait_awaiting_accept.py \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_toolruntime_truncation_fetch_more.py \
  tests/tools/test_doc_tools_provider.py \
  tests/tools/test_combined_tools_acceptance.py \
  tests/tools/web/test_web_tools_provider.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/runtime/test_import_boundary.py \
  tests/runtime/test_scene_assets_migration.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py \
  tests/engine/runners/openai/test_payload_build.py \
  tests/engine/test_agent_phase3_tool_call.py -q

pytest tests/host tests/tools tests/fins tests/runtime tests/engine tests/service -q
```

### 13.2 pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

必须零新增/扩散错误。删除 optional fallback 后的所有 type narrowing 必须显式完成，不用 `cast(Any)`、`getattr/hasattr` 或 ignore 绕过。

### 13.3 逐文件 coverage

对每个修改 production module 运行对应 owner tests 与单文件 `--cov=<module> --cov-report=term-missing`。目标冻结如下；同一文件跨 slice 时采用最高目标：

| production file | target | primary owner tests |
| --- | ---: | --- |
| `dayu/host/tool_call_request.py` | `>=95%` | accept barrier + awaiting accept + payload resolution corruption |
| `dayu/host/tool_runtime.py` | `>=80%` | accept barrier + fetch_more schema/truncation |
| `dayu/host/waiting.py` | `>=80%` | awaiting accept + resolve wait |
| `dayu/host/_event_payload.py` | `>=80%` | awaiting payload exact-key tests |
| `dayu/host/payload_resolution.py` | `>=90%` | inline/descriptor/digest corruption matrix |
| `dayu/host/accepted_result_projection.py` | `>=90%` | request/query/citation/ref negative projection |
| `dayu/host/run_input.py` | `>=80%` | ordinary/resume/material propagation |
| `dayu/host/tool_trace.py` | `>=80%` | request/result readable/internal separation |
| `dayu/runtime/__init__.py` | `>=80%` | 仅 docstring 删除；现有 `tests/runtime/test_import_boundary.py` package import 覆盖，不豁免、不新增无关测试 |
| `dayu/runtime/json_redaction.py`（删除） | N/A | deletion/source proof，不保留 dead module |
| `dayu/tools/web/web_tools.py` | `>=80%` | Web provider schema + execution regression |
| `dayu/fins/tools/fins_tools.py` | `>=80%` | Fins read schema + storage provider regression |
| `dayu/host/evidence.py` | `>=90%` | renderer required-material + citation/unavailable cases |
| `dayu/host/memory.py` | `>=80%` | accepted selected-evidence strict projection |
| `dayu/host/durable/memory.py` | `>=80%` | durable memory projection/round-trip |
| `dayu/host/compact_material.py` | `>=80%` | evidence material/provenance separation |
| `dayu/host/compact_pipeline.py` | `>=80%` | compactor readable material propagation |

命令模板（每行将模块名和该行 primary tests 显式展开执行，不用 package aggregate 值代替）：

```bash
source .venv/bin/activate
pytest <PRIMARY_OWNER_TEST_FILES> \
  --cov=<DOTTED_PRODUCTION_MODULE> \
  --cov-report=term-missing -q

# runtime package docstring-only change仍执行单文件 gate；不把整个 runtime package 当分母
coverage run -m pytest tests/runtime/test_import_boundary.py -q
coverage report --include='*/dayu/runtime/__init__.py' --fail-under=80 -m
```

completion artifact 记录上表每个文件的实际百分比和未覆盖行；不得只给 aggregate package coverage。新增 schema helper 与所有 corruption/source negative branch 必须被直接执行，即使文件总覆盖率已经达标。

### 13.4 diff 与 allowlist

```bash
git diff --check
git diff --name-only "$R03_IMPLEMENTATION_BASE_SHA"...HEAD
git status --short
```

逐 slice 与 aggregate 都将 `git diff --name-only` 和本计划 exact allowlist 做集合比较。design/control/prior artifact、Issue #177/#178、authorization 文件有任何 diff 都是 hard stop。

### 13.5 propagation scans

```bash
rg -n 'OpaqueEvidenceRef|source_refs|locator_refs|ref_kind|ref_id' \
  dayu/host/accepted_result_projection.py \
  dayu/host/run_input.py \
  dayu/host/memory.py \
  dayu/host/compact_material.py \
  dayu/host/tool_trace.py

rg -n 'payload_ref|artifact_ref|event_id|digest|cursor|tool_call_id' \
  dayu/host/accepted_result_projection.py \
  dayu/host/evidence.py \
  dayu/host/compact_material.py \
  dayu/host/tool_trace.py

rg -n '工具证据不可用；缺少可安全展示|业务来源不可用；工具结果未提供可安全展示|参数正文由 accepted-result 同源投影提供' \
  dayu tests
```

第一组预期 shared/LLM material path 零 opaque type/source guessing；第二组允许 internal provenance/diagnostic 字段命中，但每个命中必须人工证明没有进入 `source_text`、compactor `source_note` 或 LLM-ready trace summary；第三组预期零命中，证明旧 safe/fallback 与内部 placeholder 文案 assertions 已被替换且没有 compatibility alias。不能机械要求全仓零 id/ref/digest。

另外用 runtime sentinel test 读取实际 RunInput messages、Memory snapshot、compactor request material 和 trace summary，断言 `opaque-should-never-reach-llm` 与 `event-typo-should-never-reach-llm` 全部缺失。该传播测试才是 closure 主证据，grep 只是辅助 gate。

## 14. README trigger decisions

| README | 决定 | 原因/边界 |
| --- | --- | --- |
| `dayu/host/README.md` | **必须更新** | 当前仍写 `LLM-safe request atom/replay args`、fallback 与“bounded 脱敏 trace”；改为 exact atom、explicit link、strict corruption、citation/internal provenance 分离 |
| `tests/README.md` | **必须更新** | Host/request atom/source propagation/schema owner tests 与 real R03 smoke 是当前测试职责内新事实；保留 R01 段落 |
| `dayu/fins/README.md` | 检查后 no-diff | 已说明 Fins tool schema/error/result 面向 LLM 自解释及 citation owner；补参数描述不改变稳定 capability/路径 |
| `dayu/engine/README.md` | no-diff | Engine typed call/message contract不变；`agent.py`/payload serializer无 production diff |
| `dayu/config/README.md` | no-diff | prompt assets/config 无 diff，scene/config contract不变 |
| root `README.md` | no-diff | 安装、CLI/Web/WeChat 入口、命令参数、默认输出、日志、workspace、最终用户流程不变 |
| `dayu/README.md` | no-diff | UI/Service/Host/Engine/Fins 分层和装配关系不变 |

README 只能在对应 implementation slice 的代码已经落地后更新当前事实，不写 R03 过程、未来计划或文件流水账。

## 15. Review handoffs 与 completion artifact

### 15.1 slice handoff

每片提交给 code review 的 handoff 必须包含：

- slice base/commit SHA 与 exact diff paths；
- 本计划对应 contract/invariant；
- old-to-new call path；
- accepted/rejected/no-diff decisions；
- corruption/negative tests；
- 逐文件 coverage、pyright、source scan、diff check；
- README decision；
- residual/stop condition。

任何 review finding 必须由 controller 判定 owner 与 slice，不允许在下游消费者做临时补丁。

### 15.2 completion artifact

最终新建：

`docs/reviews/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-completion.md`

必须包含：

1. umbrella/R03 身份、accepted plan/review/controller refs、base/slice/aggregate SHAs；
2. 三片实际文件与符号清单；
3. ordinary/awaiting final payload snapshots 和 shared builder proof；
4. corruption matrix 与 no-fallback proof；
5. 本计划 §8 的完整 final manual inventory，每行有 `compliant | modified-at-owner | not-LLM-facing-with-evidence`、实际 diff/test evidence；
6. 本计划 §9 的每个 R01 row 逐行消费结果；
7. opaque refs EventLog round-trip + 四消费者 absence + explicit citation一致性；
8. 所有 test/coverage/pyright/diff/source/propagation scan 的完整命令与结果；
9. 真实 public-run smoke 的非秘密输入、public execution chain、projection结果和 PASS 证据；
10. README final decision；
11. review/deepreview finding ledger；
12. residual owner、未覆盖项与 stop decisions。

只有 completion artifact 经 controller 独立复核后，R03 才能标记完成并进入下一 remediation。不得仅凭代码 merge、grep 零命中或 mock smoke 宣称完成。

## 16. 风险、residual owners 与 stop conditions

| 风险/残留 | 当前处理 | owner/destination |
| --- | --- | --- |
| 未来 tool schema 新增真实 credential 参数 | 当前无此 schema；若出现立即 stop，不在 Host 加 blacklist | 具体 tool producer/config owner + controller |
| exact accepted args 进入 LLM 可能暴露未来错误 schema 输入 | 这是 producer schema defect，不允许下游 repair | 具体 ToolDefinition owner |
| 非 Fins tools 当前可能无 explicit citation | 合法 source-unavailable，不从 URL/path/ref 猜 | 对应 tool producer；未来需 citation 时在 producer另行设计 |
| internal Tool Trace 仍保存 ids/refs/digests | 允许 internal diagnostic；LLM-ready summary 与其分离 | durable Tool Trace owner |
| EventLog envelope 仍保存 opaque refs | 这是 accepted internal provenance contract | evidence/audit owner |
| real Web/provider/Fins smoke 依赖外部环境 | completion 必须真实通过；不能 skip/fake | controller 提供/确认 smoke 环境 |
| Issue #177 continuation 尚未完整 wiring | 不在 R03；`fetch_more` schema修文案不改变该事实 | Issue #177 |
| Issue #178 | 完全不进入 R03 | Issue #178 |

出现下列任一情况立即停止，不继续实现：

- current direct evidence 证明 controller Topic 3/4 决定与实际 owner 冲突；
- exact args 在 ToolRuntime accept 前已经不可恢复；
- schema owner 确实要求 LLM 提交 credential 且无法迁到 config/environment；
- 需要 Host import Fins、发明 BusinessSource、解析 arbitrary citation/ref kind；
- 需要兼容旧 DB/EventLog、双写 safe/raw、legacy fallback 或 migration；
- 需要 Issue #177/#178、统一授权或新的第四 slice 才能继续；
- 任何计划外 production/test/doc 文件成为必改；
- real public-run smoke 只能靠 fake/scripted provider 或伪 awaiting result 才能通过。

当前直接证据没有触发上述 stop；因此本计划可进入独立 plan review，但尚未授权 implementation。

## 17. Plan gate 自检

- 目标、动机、成功条件、非目标与 owner 已显式固定。
- Topic 3/4 accepted decisions全部保留，没有引入 safe normalization、BusinessSource、compatibility 或 auth framework。
- 只有 S1/S2/S3 三片，且解释了同一 R03 和最小三片原因。
- 每片列出 exact production/test/doc allowlist、symbols、data flow、contracts、negative cases、dependencies、tests、coverage 与 stop。
- prompt assets、production tool schemas、Host/Engine/Tool renderers、tests/smokes 和 R01 §11 已形成 manual per-file baseline：当前 37 个 prompt asset 全覆盖，114 个 executable-Python constructor scan path 均有逐文件 disposition，R01 §11 的 30 个 data row 全部消费；grep 仅作 gate。
- compliant prompt/schema 已标 no-diff；只对直接证据确认的 `fetch_more`、Web `url`、Fins common ids 修 owner。
- README、real smoke、completion artifact、residual owner 与 gate stop 已定义。
- 本 artifact 不修改 production/tests/README/design/control/prior artifacts，不进入 implementation，不 commit/push。
