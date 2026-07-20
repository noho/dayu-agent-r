# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Re-Review — AgentDS

## 0. Review 身份与边界

| 项目 | 值 |
| --- | --- |
| umbrella WU | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation | `R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影` |
| 本轮角色 | 对已修复计划的独立 adversarial re-review |
| reviewed target | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`（修订后） |
| 对比基线 | 原始 DS review `docs/reviews/wu-semantic-ownership-01-r03-plan-review-ds.md`、MiMo review `docs/reviews/wu-semantic-ownership-01-r03-plan-review-mimo.md`、controller adjudication、Codex fix artifact |
| 裁决优先级 | controller discussion 与已接受决定 > design truth > remediation plan > 当前直接代码证据 |
| 写入 | 仅本文 `docs/reviews/wu-semantic-ownership-01-r03-plan-rereview-ds.md` |
| 禁止 | 编辑 plan/control/production/tests/README/design/prior artifact、commit、push、implementation |

### 已完整读取的输入

1. 修订后 plan（完整 1224 行）
2. 原始 DS review（`wu-semantic-ownership-01-r03-plan-review-ds.md`）
3. MiMo review（`wu-semantic-ownership-01-r03-plan-review-mimo.md`）
4. Controller adjudication（`wu-semantic-ownership-01-r03-plan-review-controller-adjudication.md`）
5. Codex fix artifact（`wu-semantic-ownership-01-r03-plan-fix-codex.md`）
6. Controller fix validation（`wu-semantic-ownership-01-r03-plan-fix-controller-validation.md`）
7. 当前代码直接证据（逐文件读取，见 §2 证据清单）

---

## 1. R03-PLAN-F01 至 F08 闭合独立验证

以下逐项以当前代码直接证据验证每个 finding 在修订 plan 中已闭合。

### F01 — transaction 内真实 request row ref sequencing ✅ 已闭合

- **controller 要求**：shared writer 构造 request → `append_event(...).row` 得真实 row → 以 row 的 `event_id/event_sequence` 构造 ref → append `TOOL_AWAITING` → 后续 facts；同一 transaction rollback 与 idempotent replay 原子。
- **plan 实现位置**：
  - §4.2 writer 签名明确：writer "只构造 EventLogAppendRequest，不 append、不分配或预测 event_sequence。真实 row 必须由调用方执行 event_log_store.append_event(transaction, request).row 取得"
  - §4.2 writer invariant："EventLogAppendResult.row 同时覆盖新插入和 same-body existing-row replay，并携带数据库实际分配的 event_id/event_sequence"
  - §4.4 sequencing 步骤 2-5 显式写出：shared writer → `append_event(...).row` → 构造 ref → `_tool_awaiting_event_request` → 后续 facts/state/idempotency
  - §4.4 步骤 6："上述步骤全部留在同一个 HostTransactionRunner.run_write transaction。步骤 2–5 任一异常都必须 rollback...不得提交孤立 request atom"
  - §6.3 item 4 以 a-e 子步骤写出 exact sequencing
  - §6.4 测试：transaction linkage、transaction rollback（分别在 request append 后、awaiting append 后、后续 mutation 处注入异常）、idempotent replay（same-key/same-digest、same-body existing row、different digest/body conflict）
- **直接代码证据**：
  - `EventLogAppendResult.row: EventLogRow`（`event_log.py:311`）包含 `event_sequence: int`（`event_log.py:131`），由数据库分配
  - 当前 `waiting.py:620-625` 已有正确模式：先 `append_event(...).row` 得 `tool_call_requested`，但当前 `_tool_awaiting_event_request`（line 2422-2469）**不接受** request row 参数——这正是 plan 要修复的缺陷
  - 当前 `_accept_in_transaction`（line 585-684）已在同一 transaction 内执行全部步骤
- **判定**：sequencing contract 完整可实施。**闭合**。

### F02 — citation projection 的精确输入与 canonical JSONPath ✅ 已闭合

- **controller 要求**：`_source_projection(raw_outcome: JsonValue | None, diagnostics: list[str])` 由 `project_accepted_tool_result` 直接传入已 digest-check 的 raw_outcome；按 `accepted_tool_outcome_json` exact path 读取并 canonical-render 整个 citation object；Host 不枚举 Fins keys。
- **plan 实现位置**：
  - §4.6：完整 JSONPath 描述——`kind == "completed" -> result` 为 object → `result.ok is True` → `result.value` 为 object → `value.citation` 为 object
  - §4.6："只有全部条件成立时，才对整个 producer-owned citation object 调用 canonical_json_dumps；Host 不枚举、筛选、排序或解释 citation 业务 key，未知/新增 JSON member 也随整个 object 机械渲染"
  - §11.3 item 2："project_accepted_tool_result 必须把 _result_payload 已完成 payload/digest 校验后取得的当前 raw_outcome 直接传入"
  - §11.4：测试必须用真实 `accepted_tool_outcome_json(ToolCompletedOutcome(ToolResultSuccess(ok=True, value={"citation": citation_object}, meta=None)))` 构造路径
- **直接代码证据**：
  - `accepted_tool_outcome_json(ToolCompletedOutcome(...))` 输出 `{"kind":"completed","result":{"ok":True,"value":...,"meta":...}}`（`accepted_tool_outcome.py:36-44`）
  - Fins `_build_citation` 返回 `Citation.to_dict()` 字典，嵌入为 `{"citation": citation_dict, ...}`（`read_runtime.py:770-778`）
  - JSON 路径 `result.value.citation` = dict access `raw_outcome["result"]["value"]["citation"]`，与 codec 完全一致
  - 当前 `project_accepted_tool_result`（line 203）已从 `_result_payload` 提取 `raw_outcome`，可直接传入修改后的 `_source_projection`
  - 当前 `_source_projection`（line 644-678）接收 `(envelope, diagnostics)`——plan 改为 `(raw_outcome, diagnostics)`
  - `Citation.to_dict()`（`tool_models.py:119-125`）过滤 None 值，`canonical_json_dumps` 保证稳定输出
- **判定**：JSONPath 与 codec 一致，输入传递路径完整。**闭合**。

### F03 — Tool Trace business_source_text/state 字段映射 ✅ 已闭合

- **controller 要求**：readable `tool_result` 新增 `business_source_text = projection.source.text`、`business_source_state = projection.source.state.value`，复用现有 `AcceptedToolResultSourceState`。
- **plan 实现位置**：
  - §4.7："readable trace_summary.tool_result 精确新增两个字符串 mapping：business_source_text = projection.source.text、business_source_state = projection.source.state.value。state 直接复用现有 AcceptedToolResultSourceState 的 available|unavailable，不新建 enum/type、不复制 citation parser"
  - §11.3 item 8："readable result summary 只从 shared projection 映射 business_source_text=projection.source.text 和 business_source_state=projection.source.state.value，缺 material 抛 HostDurableError"
  - §11.4 测试："trace_summary.tool_result.business_source_text/state 分别严格等于 shared projection.source.text/state.value，diagnostic_reason 不进入业务来源字段"
- **直接代码证据**：
  - `AcceptedToolResultSourceState` 已有 `AVAILABLE = "available"`、`UNAVAILABLE = "unavailable"`（`accepted_result_projection.py:95-106`）
  - `AcceptedToolResultSourceProjection` 已有 `text: str`、`state: AcceptedToolResultSourceState`、`diagnostic_reason: str | None`（`accepted_result_projection.py:118-124`）
  - `_tool_result_summary_from_projection`（`tool_trace.py:1265`）当前不包含 source 字段——正是 plan 要新增的位置
- **判定**：字段类型、枚举、映射关系完整规格化。**闭合**。

### F04 — 四消费者统一 strict material 失败语义 ✅ 已闭合

- **controller 要求**：`render_accepted_tool_evidence_for_llm` 只接收非 optional material；缺 `llm_material` 时 RunInput/Memory/Compact/LLM-ready Trace 统一抛 `HostDurableError`，不得 skip/fallback/limited signal。
- **plan 实现位置**：
  - §4.5 表格：corruption case → HostDurableError 逐项列出
  - §4.6 renderer："render_accepted_tool_evidence_for_llm(material: AcceptedToolEvidenceLLMMaterial) -> str 只接受非 optional material；删除整体 fallback constant/branch"
  - §11.3 item 4："render_accepted_tool_evidence_for_llm 参数改为非 optional；删除 ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT 和整体 fallback branch"
  - §11.3 item 6："memory.py::_selected_evidence_text 要求 TOOL_RESULT_ACCEPTED projection event 有 typed material；没有则抛 HostDurableError，不跳过该 evidence、不渲染 fallback"
  - §11.3 item 7："run_input.py、compact_material.py/compact_pipeline.py 在 accepted-evidence branch 先验证并收窄非空 typed material；缺失均抛 HostDurableError"
  - §11.4 测试：为 RunInput/Memory/Compact/LLM-ready Trace 各造 `llm_material=None` corruption，四处均断言 `HostDurableError` 且没有 skip/fallback/limited output
- **直接代码证据**：
  - 当前 `render_accepted_tool_evidence_for_llm(material: AcceptedToolEvidenceLLMMaterial | None)`（`evidence.py:168-186`）接受 None 并返回 fallback
  - 当前 `memory.py:1702` 调用 `render_accepted_tool_evidence_for_llm(event.accepted_tool_evidence)`——若 material 为 None 则走 fallback
  - 当前 `compact_material.py:2579-2580` **已有** `if projection.llm_material is None: raise HostDurableError(...)`——部分 compliant
  - 当前 `run_input.py:3487-3491` 调用 `project_accepted_tool_result` 后检查 `accepted_arguments is None` 并走 `_resume_wait_fallback_message`
- **判定**：四个 consumer 的 fail-closed 策略已统一规格化为 `HostDurableError`，无差异化 fallback。**闭合**。

### F05 — shared atom 输入映射与删除闭集 ✅ 已闭合

- **controller 要求**：ordinary 从 `ToolAcceptCall.tool_identity_digest`、awaiting 从 `ToolAwaitingAcceptCandidate.tool_identity_digest` 原样映射；builder 不重算；删除闭集已证实。
- **plan 实现位置**：
  - §4.2 映射表：ordinary `tool_identity_digest` **原样取** `ToolAcceptCall.tool_identity_digest`；awaiting **原样取** `ToolAwaitingAcceptCandidate.tool_identity_digest`
  - §4.2："builder 不重算 tool_identity_digest，不从 ToolDefinition/schema/log/digest 反推，也不因 ordinary/awaiting 来源不同改变 payload contract"
  - §6.3 item 3："当前直接 source scan 已证明后三个 helper 都只被 waiting 本地 _tool_call_requested_event_request 调用，删除闭集完整"
  - §6.4 测试："identity mapping：ordinary payload 的 tool_identity_digest 精确等于 ToolAcceptCall.tool_identity_digest，awaiting 精确等于 ToolAwaitingAcceptCandidate.tool_identity_digest；用与 schema digest 不同的 sentinel 证明 builder 未重算或反推"
- **直接代码证据**：
  - `ToolAcceptCall.tool_identity_digest: str`（`tool_runtime.py:509`）
  - `ToolAwaitingAcceptCandidate.tool_identity_digest: str`（`waiting.py:259`）
  - `_accepted_arguments_json`（`waiting.py:2389`）仅被 `_tool_call_requested_event_request`（line 2323）调用
  - `_awaiting_semantic_query_text`（`waiting.py:2399`）仅被 `_tool_call_requested_event_request`（line 2323）调用
  - `_payload_size_bytes`（`waiting.py:2412`）仅被 `_tool_call_requested_event_request`（line 2323）调用
  - 删除闭集完整：三个 helper 的唯一调用方 `_tool_call_requested_event_request` 在 S1 被删除
- **判定**：identity mapping 方向正确，删除闭集有直接代码证据。**闭合**。

### F06 — request-event readable Tool Trace 不得投影内部实现提示 ✅ 已闭合

- **controller 要求**：`TOOL_CALL_REQUESTED` readable summary 通过 `read_event_by_id` + strict `tool_call_request_atoms` 解析 inline/descriptor exact args/query；不展示 ref/digest，不发内部占位提示；损坏 `HostDurableError` fail closed。
- **plan 实现位置**：
  - §4.7："TOOL_CALL_REQUESTED readable projection 不直接消费 event view 的 raw payload：先 read_event_by_id(transaction, event.event_id) 取得 canonical row，再调用 strict tool_call_request_atoms(transaction, row) 解析 inline/descriptor exact args 与 semantic query，最后只做 bounded 展示"
  - §4.7："row/atom 缺失、错类型或 digest/storage 损坏统一抛 HostDurableError；不得展示 payload ref/digest，也不得输出'参数正文由 accepted-result 同源投影提供'等内部实现 placeholder"
  - §11.3 item 8：删除 `_tool_request_summary_from_payload` 的 raw-payload/redaction/descriptor-placeholder 行为；删除 readable request/result map 中 ref/digest source 文案
  - §11.4 测试：readable Tool Trace `TOOL_CALL_REQUESTED` 对 inline/descriptor 都经 strict atom resolver 展示 exact bounded args/query；损坏抛 `HostDurableError`，输出中不存在 payload ref/digest 或内部 placeholder 文案
- **直接代码证据**：
  - 当前 `_tool_request_summary_from_payload`（`tool_trace.py:1184-1245`）直接从 raw payload 读取并包含 `arguments_payload_ref`、`arguments_payload_digest`、`normalized_arguments_digest`、`semantic_query_digest` 等 ref/digest 字段
  - 当前 `tool_call_request_atoms`（`payload_resolution.py:112-155`）已执行 strict event type/storage digest 校验，但缺少 `arguments_payload_digest == normalized_arguments_digest` 交叉验证（plan §4.3 step 4 补充）
  - `read_event_by_id`（`event_log.py:348`）返回 `EventLogRow | None`——API 已可用
- **判定**：strict atom resolution 路径完整，内部 placeholder 与 ref/digest 展示已明确删除。**闭合**。

### F07 — runtime package 文档项与 coverage 边界 ✅ 已闭合

- **controller 要求**：`dayu/runtime/__init__.py` 只删除模块概览 docstring 中的 `dayu.runtime.json_redaction` 列表项；保留 `>=80%` coverage。
- **plan 实现位置**：
  - §7.3："dayu/runtime/__init__.py 只改模块 docstring，删除与该已删模块对应的'层中立 JSON 敏感字段脱敏'概览项及 dayu.runtime.json_redaction 当前模块列表项，不改 from __future__、__all__、import/re-export 或任何运行逻辑"
  - §13.3 coverage table：`dayu/runtime/__init__.py >= 80%`，由 `tests/runtime/test_import_boundary.py` 覆盖
  - §13.3 命令模板：显式 `coverage run` + `coverage report --include='*/dayu/runtime/__init__.py'`
- **直接代码证据**：
  - `dayu/runtime/__init__.py:11`：docstring 概览含"层中立 JSON 敏感字段脱敏"
  - `dayu/runtime/__init__.py:32`：docstring 模块列表含 `dayu.runtime.json_redaction`
  - `dayu/runtime/__init__.py:39`：`__all__: list[str] = []`——无 re-export
  - 无 `from dayu.runtime.json_redaction import` 在 `__init__.py` 中
- **判定**：修改范围精确，coverage 目标可执行。**闭合**。

### F08 — propagation 负例与旧文案 assertions ✅ 已闭合

- **controller 要求**：S3 sentinel matrix 追加 `eventlogg` typo；明确更新旧 source-unavailable/fallback 文案 assertions。
- **plan 实现位置**：
  - §11.4 sentinel matrix 包含：`ref_kind="eventlogg"`（internal-kind typo）、`ref_kind="eventlog"`、`ref_kind="fliing-typo"`
  - §11.4："删除/替换 test_projection_missing_material_uses_owner_fallback、Memory 中 render_accepted_tool_evidence_for_llm(None) 期望，以及所有旧'工具证据不可用；缺少可安全展示...'/'业务来源不可用；工具结果未提供可安全展示...' assertions；新断言只接受 strict error 或'该工具结果未提供业务来源。'，不保留 alias/兼容文本"
  - §13.5 propagation scans：第三组 grep 预期零命中旧 safe/fallback/placeholder 文案
- **直接代码证据**：
  - 当前 `_INTERNAL_SOURCE_REF_KINDS`（`accepted_result_projection.py:61-71`）包含 `"eventlog"`，不包含 `"eventlogg"`——typo 测试证明删除 denylist 后 typo 不会通过其他分支泄漏
  - 当前 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 值为"业务来源不可用；工具结果未提供可安全展示的来源。"——含"安全展示"措辞
  - 当前 `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` 值为"工具证据不可用；缺少可安全展示的工具名称或工具结果。"——含 fallback 语义
  - plan §11.4 明确要求替换所有旧文案 assertions
- **判定**：sentinel matrix 覆盖 denylist 内/外/typo 三类 ref kind；旧文案替换路径完整。**闭合**。

---

## 2. 三片 plan 重新挑战

### 2.1 S1 — ordinary/awaiting shared request atom 与 durable replay identity

**已覆盖的关键点**：

- ✅ shared writer 输入 contract（`AcceptedToolCallRequestAtomInput`）覆盖所有必填字段
- ✅ ordinary/awaiting 两个入口到 atom 的显式映射表（§4.2）
- ✅ payload 字段集合、inline/descriptor 逻辑、digest invariant 完全相同
- ✅ `TOOL_AWAITING` 删除四个字段（`normalized_arguments_digest`、`accepted_arguments`、`accepted_arguments_source_digest`、arguments payload/digest 副本）
- ✅ 删除闭集：`waiting.py` 三个私有 helper + `llm_safe_replay_arguments`
- ✅ transaction rollback：注入异常断言整组 rows 未提交
- ✅ idempotent replay：same-digest ack、same-body existing row、different digest/body conflict
- ✅ identity mapping：`tool_identity_digest` 从 typed candidate 原样传递，用 sentinel 证明 builder 未重算
- ✅ corruption matrix 覆盖 §4.5 全部 12 个 negative case

**新挑战——无新发现**：

- **`_event_payload.py` S1/S2 修改边界**：S1 修改 `tool_awaiting_payload` 删除 args/digest 参数并新增 `tool_call_requested_event_ref`；S2 删除 `llm_safe_replay_arguments` 和 redaction import。两者修改同一文件不同函数，无冲突。plan §6.3 item 4 明确说明 S1 删除 `llm_safe_replay_arguments`（因其调用方已在 S1 被删除），S2 再删除整个 `json_redaction.py` 模块（在 Tool Trace 停止使用后）。sequencing 正确。
- **`payload_resolution.py::tool_call_request_atoms` 的 normalized/payload digest equality guard**：plan §4.3 step 4 要求 `arguments_payload_digest == normalized_arguments_digest`。当前代码（`payload_resolution.py:140`）只检查 `sha256_digest_json(arguments_json) == arguments_payload_digest`，不交叉验证 normalized digest。这是正确的补充，当前代码 gap 通过此 guard 关闭。
- **large args descriptor path**：plan §6.4 已列 "ordinary/awaiting large args：都走 TOOL_CALL_ARGUMENTS_JSON descriptor，reader 返回 exact args；hot EventLog 不内联大正文"。当前 `tool_runtime.py:4370-4399` 已有 descriptor 写入逻辑，shared writer 复用即可。

### 2.2 S2 — 删除 blacklist repair，修正 LLM source owners

**已覆盖的关键点**：

- ✅ 删除 `_contains_unsafe_argument_key`（递归敏感字段名扫描）
- ✅ 删除 `arguments_summary_unsafe` diagnostic 与 `_limited_query` branch
- ✅ 删除 `tool_trace.py::_redacted_json` 及其 import
- ✅ 删除 `dayu/runtime/json_redaction.py` 全模块
- ✅ `dayu/runtime/__init__.py` 仅改 docstring
- ✅ 三个 owner schema 修正（`fetch_more` description + 3 param descriptions、Web `url` description、Fins 共用 `ticker/document_id` descriptions）
- ✅ 人工 inventory baseline 已冻结（37 prompt assets + 23 production schemas + 15 test/smoke fixtures + 61 constructor scan paths）
- ✅ R01 §11 30 rows 逐行消费

**新挑战——无新发现**：

- **`arguments_summary_unsafe` 删除后的 query 构造路径**：plan §4.6 明确：semantic_query 存在时原样使用；否则对 exact `arguments_json` 做 bounded canonical JSON 展示。删除 `_contains_unsafe_argument_key` 后不再有 "query limited signal" 分支，所有合法业务字段（`file_path`、`scope_token`、`password-like-but-business-name`）均机械展示。无功能退化。
- **Fins `ticker/document_id` 共用 helper**：plan §7.4 item 3 要求使用两个模块级私有 schema helper。这是合理的——避免九个工具中重复文案，同时保持每个工具的 `name/required/enum/result shape` 不变。符合 DRY 原则且修订范围最小。
- **prompt assets 与 Engine files 的 no-diff 边界**：plan §8.1/§8.2 已人工逐文件确认。当前直接证据未发现任何 prompt asset 或 Engine file 需要修改。

### 2.3 S3 — opaque refs internal-only propagation closure

**已覆盖的关键点**：

- ✅ `AcceptedToolResultProjection` 删除 `source_locator_refs` 与 `OpaqueEvidenceRef` import
- ✅ `_source_projection` 改为只接收 `(raw_outcome, diagnostics)`
- ✅ 四个消费者的 `source_locator_refs` 删除或固定空 tuple
- ✅ `render_accepted_tool_evidence_for_llm` 参数改为非 optional
- ✅ 四个 consumer 缺 material 统一抛 `HostDurableError`
- ✅ Tool Trace `TOOL_CALL_REQUESTED` 经 strict atom resolver
- ✅ Tool Trace readable result 新增 `business_source_text/state`
- ✅ sentinel propagation tests 覆盖所有四个消费者
- ✅ citation object 额外未知 member 一致性测试

**新挑战——无新发现**：

- **`compact_material.py` 中 `source_locator_refs` 的多处使用**：grep 确认 `compact_material.py` 有 6 处 `source_locator_refs` 赋值/引用。plan §11.3 item 5 明确 "RunInputMaterialBlock、run_input_material_block、InitialEvidenceMaterial 删除 source_locator_refs"，S3 allowlist 包含 `compact_material.py`。所有使用点均为机械删除（不是语义重构），implementation agent 无需做设计决策。
- **`PromptLocalProvenanceEntry.source_locator_refs` 固定空 tuple**：plan §11.3 item 5 明确 EventLog envelope 仍保存原 refs，internal provenance 传空 tuple。不新建重复 view。这条路径正确：不删除 internal provenance 结构（避免破坏现有 compaction 类型系统），但确保进入该路径的值始终为空。
- **`_source_projection` 从 `raw_outcome` 读取 citation 时，`raw_outcome` 类型为 `JsonValue | None`**：当 `raw_outcome` 为 None 或非 dict 时，按 §4.6 走 source-unavailable 分支。当 `raw_outcome` 为 dict 但非 completed shape 时（如 kind="failed"），同样走 source-unavailable。所有路径已覆盖。

---

## 3. 跨 slice 架构与完整性检查

### 3.1 所有权一致性

| 语义 | plan owner | 代码验证 |
| --- | --- | --- |
| accepted args identity | ToolRuntime accept boundary → shared writer | `tool_runtime.py` accept 已有原始 args + digest |
| TOOL_CALL_REQUESTED durable atom | 新 `tool_call_request.py` | 两个入口共用同一 writer，同字段集合 |
| waiting governance | `waiting.py` + `TOOL_AWAITING` | 只存 governance + explicit ref link |
| query 业务语义 | producer semantic query；缺失时 canonical args | 不再 synthetic |
| accepted result LLM material | `accepted_result_projection.py` + `evidence.py` | single typed material，四个消费者复用 |
| Fins citation | `read_runtime.py::_build_citation` → `Citation.to_dict()` | Host 机械 canonical-render |
| opaque refs | `evidence.py::AcceptedEvidenceEnvelope` | EventLog envelope/audit round-trip |

无跨 owner 语义冲突或双写。

### 3.2 LLM-facing 约束合规

- ✅ prompt assets 全部审计 no-diff（§8.1）
- ✅ tool schema 自足性缺口在 producer owner 修正（§7.4）
- ✅ 删除所有 "LLM-safe"、"safe replay"、"安全展示" 措辞
- ✅ 内部治理标识（event_id、digest、payload_ref、cursor）不进入 LLM material
- ✅ citation 缺失时统一业务中性文案："该工具结果未提供业务来源。"
- ✅ 无 Host governance 伪装成业务事实

### 3.3 安全/retention

- ✅ opaque refs 保留在 EventLog envelope，可 round-trip（§11.4 envelope codec test）
- ✅ RunInput/Memory/Compact/LLM-ready Trace 均不含 opaque ref sentinel
- ✅ 当前 production tool schemas 无 credential 参数（§3.4 审计确认）
- ✅ `password` 命中仅属于 URL userinfo 解析（`web_tools.py`），不是 LLM schema 参数
- ✅ 未来 credential 出现时 plan §16 有 stop condition

### 3.4 Inventory 完整性

- prompt assets：37 文件全覆盖（§8.1）
- production tool schemas：23 文件全覆盖（§8.2）
- tests/smokes LLM fixtures：15 文件全覆盖（§8.3）
- executable-Python constructor scan：114 路径全覆盖（§8.4）
- R01 §11 handoff：30 rows 逐行消费（§9）

### 3.5 Smoke/deferred

- ✅ 新 `utils/smoke_host_public_r03_semantic_ownership.py` contract 完整（§12.2）
- ✅ 包含 ordinary Doc、ordinary Web、Fins awaiting 三条真实路径
- ✅ aggregate hard gate 不降级（§12.2）
- ✅ residual risks 有明确 destination（§16）
- ✅ Issue #177/#178 显式排除

### 3.6 测试覆盖率

- ✅ 每 slice 有精确 test file allowlist 和 commands
- ✅ 每 production file 有显式覆盖率目标
- ✅ S1 corruption matrix、S2 source gates、S3 propagation tests 均有列
- ✅ coverage 命令模板完整

---

## 4. 新发现

**无。** 经逐项验证 F01-F08 闭合状态、重新挑战三片 plan 的 correctness/ownership/coupling/LLM-facing/security-retention/inventory/smoke-deferred/test gaps，未发现任何 material finding。

---

## 5. Open Questions

无。原始 DS review 和 MiMo review 的所有 open questions 已由 controller adjudication 和 Codex fix 收敛。

---

## 6. Residual Risks

| 风险 | 分类 | 当前处理 | destination |
| --- | --- | --- | --- |
| real smoke 环境不可用导致 R03 completion 阻塞 | 流程/运维 | plan §12.2 aggregate hard gate；S1/S2/S3 可先独立 accept | controller 提供 smoke 环境 |
| 非 Fins tool 当前无 explicit citation | accepted source-unavailable | plan §4.6 统一 unavailable 文案 | 对应 tool producer |
| 未来 tool schema 新增真实 credential 参数 | 已由 plan §16 stop condition 覆盖 | 不进入 Host blacklist | 具体 tool producer + controller |
| internal Tool Trace 仍保存 refs/digests | internal diagnostic | LLM-ready summary 严格隔离 | durable Tool Trace owner |
| Issue #177/#178 | 不进入 R03 | plan §1.4 显式排除 | 各 issue owner |

无新增 residual risk。

---

## 7. Final Plan Re-Review Conclusion

**PASS**

R03 修订计划在以下维度均达到 code-generation-ready 水平：

- **F01-F08 闭合**：八项 controller-accepted findings 均已在 owner-correct plan 位置有可实施规格，并经当前代码直接证据独立验证。
- **三片结构**：S1 durable identity → S2 source/projection audit → S3 propagation closure，依赖链正确，每片有独立 review 边界。
- **ownership**：每个业务语义有唯一 owner，无跨层穿透或双写。
- **LLM-facing**：所有 prompt/schema/message/renderer 经人工 inventory 审计；删除所有 blacklist/safe/fallback 措辞。
- **安全/retention**：opaque refs 留在 EventLog envelope；LLM material 严格分离。
- **inventory**：37 prompt assets + 114 constructor paths + R01 30 rows 全覆盖。
- **smoke/deferred**：真实 Doc/Web/Fins smoke contract 完整；residual risks 有明确 destination。
- **test gaps**：corruption matrix、propagation sentinel tests、逐文件 coverage 均已定义。

本轮 re-review 未发现任何 material finding。plan 可进入 implementation。

---

## 8. Artifact path

`docs/reviews/wu-semantic-ownership-01-r03-plan-rereview-ds.md`
