# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Re-Review — AgentMiMo

## 1. Review 身份与结论

| 项目 | 值 |
| --- | --- |
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation | `R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影` |
| reviewed target | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`（修订版） |
| plan evidence base | `444bb33eaebba5f56d3cd211ced90e3b9d67a4fc` |
| re-review inputs | 原始 review `wu-semantic-ownership-01-r03-plan-review-mimo.md`、controller adjudication `wu-semantic-ownership-01-r03-plan-review-controller-adjudication.md`、fix artifact `wu-semantic-ownership-01-r03-plan-fix-codex.md`、controller validation `wu-semantic-ownership-01-r03-plan-fix-controller-validation.md`、DS review `wu-semantic-ownership-01-r03-plan-review-ds.md` |
| review scope | 完整修订计划 + controller discussion + design truth + 当前代码/测试直接证据 |
| verdict | **PASS** |

## 2. F01–F08 逐项独立验证

### R03-PLAN-F01 — transaction 内真实 request row ref sequencing ✅ CLOSED

**验证方法**：读取 §4.2、§4.4、§6.3 item 4、§6.4，与当前代码 `tool_runtime.py:2464`、`waiting.py:620-629`、`EventLogAppendResult.row` 交叉核对。

**plan 修订内容**：
- §4.2 明确 "该 writer **只构造** `EventLogAppendRequest`，不 append、不分配或预测 `event_sequence`。真实 row 必须由调用方执行 `event_log_store.append_event(transaction, request).row` 取得"
- §4.4 item 3 "`append_event(...).row` 取得新插入或 same-body existing row 的真实 `event_id/event_sequence`；禁止预估、硬编码 `0/null` 或从 wait id 派生 sequence"
- §4.4 item 4 "以该 row 构造 `tool_call_requested_event_ref`，传给 `_tool_awaiting_event_request`"
- §4.4 item 6 "same-body existing request-row replay 使用既有真实 sequence，different digest/body conflict 不产生部分事实"
- §6.4 测试要求 "transaction linkage：awaiting payload 的 ref event id/sequence 与同事务真实 request row 一致"

**代码验证**：当前 `tool_runtime.py:2464` 的 ordinary accept 已示范正确模式（先 `append_event` 取 `.row` 再传给后续 event）。`EventLogAppendResult.row` 已包含真实 `event_sequence`。修订后的 sequencing contract 完整、可直接实施。

**结论**：F01 已在 owner-correct plan 位置关闭。

---

### R03-PLAN-F02 — citation projection 精确输入与 canonical JSONPath ✅ CLOSED

**验证方法**：读取 §4.6、§11.3 item 2、§11.4，追踪完整序列化链路 `FinsReadRuntime._build_citation` → `Citation.to_dict()` → `ToolResultSuccess.value` → `accepted_tool_outcome_json` → `raw_tool_outcome` → `project_accepted_tool_result`。

**plan 修订内容**：
- §4.6 "source owner 签名固定为 `_source_projection(raw_outcome: JsonValue | None, diagnostics: list[str]) -> AcceptedToolResultSourceProjection`"
- §4.6 "`project_accepted_tool_result` 必须把 `_result_payload` 已完成 payload/digest 校验后取得的当前 `raw_outcome` 直接传入；不得从 envelope refs、result text、trace row 或未校验 payload 重新读取"
- §4.6 canonical JSONPath："`kind == 'completed' -> result` 为 object -> `result.ok is True` -> `result.value` 为 object -> `value.citation` 为 object。只有全部条件成立时，才对**整个 producer-owned citation object**调用 `canonical_json_dumps`；Host 不枚举、筛选、排序或解释 citation 业务 key"
- §11.4 "用真实 `accepted_tool_outcome_json(ToolCompletedOutcome(ToolResultSuccess(ok=True, value={'citation': citation_object}, meta=None)))` 构造 raw outcome；不得手写与 codec 脱节的假 shape"

**序列化链路验证**：
1. `FinsReadRuntime` 九个方法均在 result dict 顶层放置 `"citation": Citation.to_dict()` — 代码确认
2. `accepted_tool_outcome_json(ToolCompletedOutcome)` 输出 `{"kind": "completed", "result": {"ok": true, "value": <tool_dict>, "meta": ...}}` — 代码确认（`accepted_tool_outcome.py:28-64`）
3. `project_accepted_tool_result` 在 line 203 获取 `raw_outcome = result_payload.get("raw_tool_outcome")` — 代码确认
4. **正确 JSONPath 为 `raw_outcome.result.value.citation`** — 通过完整序列化链路确认

**结论**：F02 已在 owner-correct plan 位置关闭。签名、传递方式、JSONPath 和测试要求均 code-generation-ready。

---

### R03-PLAN-F03 — Tool Trace business source 字段映射 ✅ CLOSED

**验证方法**：读取 §4.7、§11.3 item 8、§11.4，与当前 `_tool_result_summary_from_projection`（`tool_trace.py:1265`）和 `AcceptedToolResultSourceState`（`accepted_result_projection.py:93-98`）核对。

**plan 修订内容**：
- §4.7 "`trace_summary.tool_result` 精确新增两个字符串 mapping：`business_source_text = projection.source.text`、`business_source_state = projection.source.state.value`"
- §4.7 "state 直接复用现有 `AcceptedToolResultSourceState` 的 `available|unavailable`，不新建 enum/type、不复制 citation parser"
- §4.7 "`projection.source.diagnostic_reason` 只留 internal projection/diagnostic，不进入 business source 文本"
- §11.4 "`trace_summary.tool_result.business_source_text/state` 分别严格等于 shared `projection.source.text/state.value`，`diagnostic_reason` 不进入业务来源字段"

**代码验证**：
- `AcceptedToolResultSourceState` 已有 `AVAILABLE = "available"` 和 `UNAVAILABLE = "unavailable"` — 直接复用
- `AcceptedToolResultSourceProjection` 已有 `text: str`、`state: AcceptedToolResultSourceState`、`diagnostic_reason: str | None` — 映射源明确
- 当前 `tool_trace.py` 无 `business_source_text/state` 字段 — 确认是新增
- 当前 `_tool_result_summary_from_projection` 返回 dict 的 key 集合已知 — 新增两个 key 不破坏现有结构

**结论**：F03 已在 owner-correct plan 位置关闭。字段类型、枚举值、映射关系均自足说明。

---

### R03-PLAN-F04 — 四消费者统一 strict material 失败语义 ✅ CLOSED

**验证方法**：读取 §4.5、§4.6 renderer、§11.3 items 4/6/7/8、§11.4，与当前 `evidence.py:168`、`memory.py`、`run_input.py`、`compact_material.py`、`tool_trace.py` 调用链核对。

**plan 修订内容**：
- §4.5 "`render_accepted_tool_evidence_for_llm` 参数改为非 optional；删除整体 fallback constant/branch"
- §4.5 "RunInput、Memory、Compact、LLM-ready Tool Trace 均抛 `HostDurableError`"
- §4.5 "四个 LLM consumer 不得 catch 后跳过单条 evidence、继续构造部分输入、返回 fallback/limited signal 或改投 internal refs"
- §11.3 item 4 逐 consumer 指定 fail closed 行为
- §11.4 "为 RunInput、Memory、Compact、LLM-ready Tool Trace 各造 canonical accepted result `llm_material=None` corruption，四处均断言 `HostDurableError` 且没有 skip/fallback/limited output"

**当前代码确认**：
- `render_accepted_tool_evidence_for_llm(material: AcceptedToolEvidenceLLMMaterial | None)` — 当前接受 None 并返回 fallback（`evidence.py:168`）
- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 含 "可安全展示" 用语 — 确认需替换
- `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` 含 "可安全展示" 用语 — 确认需删除
- 四个 consumer 当前均有 fallback 路径 — 确认需删除

**结论**：F04 已在 owner-correct plan 位置关闭。fail closed 策略统一为 `HostDurableError`，四 consumer 行为一致。

---

### R03-PLAN-F05 — shared atom 输入映射与删除闭集 ✅ CLOSED

**验证方法**：读取 §4.2 atom mapping table、§6.3 items 2/3、§6.4，与当前代码 `_accepted_arguments_json`（`waiting.py:2389`）、`_awaiting_semantic_query_text`（`waiting.py:2399`）、`_payload_size_bytes`（`waiting.py:2412`）的调用方核对。

**plan 修订内容**：
- §4.2 table 明确 ordinary 从 `ToolFactAcceptCandidate.identity/call/idempotency/tool_fact_kind`、awaiting 从 `ToolAwaitingAcceptCandidate` 同名字段映射
- §4.2 "将 `ToolAcceptCall.tool_identity_digest` 原样传入，不在 shared builder 重算或反推"
- §6.3 item 3 "当前直接 source scan 已证明后三个 helper 都只被 waiting 本地 `_tool_call_requested_event_request` 调用，删除闭集完整"
- §6.4 "identity mapping：ordinary payload 的 `tool_identity_digest` 精确等于 `ToolAcceptCall.tool_identity_digest`，awaiting 精确等于 `ToolAwaitingAcceptCandidate.tool_identity_digest`；用与 schema digest 不同的 sentinel 证明 builder 未重算或反推"

**代码验证**：
- `_accepted_arguments_json` 仅被 `_tool_call_requested_event_request`（line 2337）调用 — 代码确认
- `_awaiting_semantic_query_text` 仅被 `_tool_call_requested_event_request`（lines 2339-2342）调用 — 代码确认
- `_payload_size_bytes` 仅被 `_tool_call_requested_event_request`（line 2369）调用 — 代码确认
- 三者删除闭集已证实，plan 已记录

**结论**：F05 已在 owner-correct plan 位置关闭。映射明确、删除闭集完整、sentinel 测试覆盖。

---

### R03-PLAN-F06 — request-event readable Tool Trace 不得投影内部实现提示 ✅ CLOSED

**验证方法**：读取 §4.7、§11.3 item 8、§11.4，与当前 `_tool_request_summary_from_payload`（`tool_trace.py:1184-1245`）核对。

**plan 修订内容**：
- §4.7 "`TOOL_CALL_REQUESTED` readable projection 不直接消费 event view 的 raw payload：先 `read_event_by_id(transaction, event.event_id)` 取得 canonical row，再调用 strict `tool_call_request_atoms(transaction, row)` 解析 inline/descriptor exact args 与 semantic query"
- §4.7 "row/atom 缺失、错类型或 digest/storage 损坏统一抛 `HostDurableError`；不得展示 payload ref/digest，也不得输出'参数正文由 accepted-result 同源投影提供'等内部实现 placeholder"
- §11.3 item 8 "删除 `_tool_request_summary_from_payload` 的 raw-payload/redaction/descriptor-placeholder 行为"
- §11.4 "readable Tool Trace `TOOL_CALL_REQUESTED` 对 inline/descriptor 都经 strict atom resolver 展示 exact bounded args/query；request row missing、wrong type、storage/digest mismatch 均抛 `HostDurableError`，且输出中不存在 payload ref/digest 或内部 placeholder 文案"

**当前代码确认**：
- `_tool_request_summary_from_payload` 当前直接从 raw payload 读取、执行 `_redacted_json`、输出 `normalized_arguments_digest`/`arguments_payload_ref`/`arguments_payload_digest`/`semantic_query_digest` 到 readable summary — 确认需重构
- 当前代码中 "参数正文由 accepted-result 同源投影提供" 文案未出现（DS-N05 已指出 plan 原建议含此内部术语） — plan 修订后已删除该建议文案

**结论**：F06 已在 owner-correct plan 位置关闭。strict atom resolver 路径、损坏行为和内部 placeholder 删除均明确。

---

### R03-PLAN-F07 — runtime package 文档项与 coverage 边界 ✅ CLOSED

**验证方法**：读取 §7.3、§10.2、§13.1、§13.3，与当前 `dayu/runtime/__init__.py` 和 `dayu/runtime/json_redaction.py` 核对。

**plan 修订内容**：
- §7.3 "`dayu/runtime/__init__.py` **只改模块 docstring**，删除与该已删模块对应的'层中立 JSON 敏感字段脱敏'概览项及 ``dayu.runtime.json_redaction`` 当前模块列表项，不改 `from __future__`、`__all__`、import/re-export 或任何运行逻辑"
- §13.3 "`dayu/runtime/__init__.py >= 80%`，仅 docstring 删除；现有 `tests/runtime/test_import_boundary.py` package import 覆盖，不豁免、不新增无关测试"

**当前代码确认**：
- `dayu/runtime/__init__.py:32` 含 ``dayu.runtime.json_redaction`` 模块列表项 — 确认需删除
- `json_redaction.py` 仅被 `_event_payload.py:20` 和 `tool_trace.py:81` import — 确认删除不影响其它模块
- `__init__.py` 无 `json_redaction` re-export — 确认只改 docstring

**结论**：F07 已在 owner-correct plan 位置关闭。修改范围精确、coverage 策略合理。

---

### R03-PLAN-F08 — propagation 负例与旧文案 assertions ✅ CLOSED

**验证方法**：读取 §11.3 items 3/4、§11.4、§13.5，与当前 `evidence.py` 文案和 sentinel 值核对。

**plan 修订内容**：
- §11.3 item 3 "`ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 改为不声称 Host 做过'安全展示'判断的业务中性文案"
- §11.4 sentinel matrix 新增 `ref_kind = "eventlogg"`、`ref_id = "event-typo-should-never-reach-llm"`
- §11.4 "删除/替换 `test_projection_missing_material_uses_owner_fallback`、Memory 中 `render_accepted_tool_evidence_for_llm(None)` 期望，以及所有旧 `工具证据不可用；缺少可安全展示...` / `业务来源不可用；工具结果未提供可安全展示...` assertions；新断言只接受 strict error 或 `该工具结果未提供业务来源。`，不保留 alias/兼容文本"

**当前代码确认**：
- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"` — 确认含 "可安全展示"，需替换
- `ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT = "工具证据不可用；缺少可安全展示的工具名称或工具结果。"` — 确认含 "可安全展示"，需删除
- `render_accepted_tool_evidence_for_llm(None)` 当前返回 fallback 文案 — 确认需改为 non-optional

**结论**：F08 已在 owner-correct plan 位置关闭。旧文案替换、sentinel 覆盖和 assertions 更新均明确。

---

## 3. 全计划重新挑战

### 3.1 正确性

| 挑战项 | 验证结果 |
| --- | --- |
| `_source_projection` 新签名是否自足 | ✅ 签名 `(raw_outcome: JsonValue \| None, diagnostics: list[str])` + §4.6 JSONPath + §11.4 测试要求，agent 无需自行决定 |
| `raw_outcome` 传递链路是否完整 | ✅ `project_accepted_tool_result` line 203 已从 digest-check 的 payload 获取 `raw_outcome`，直接传入 `_source_projection` |
| citation JSONPath 是否与 codec 一致 | ✅ 追踪 `FinsReadRuntime._build_citation` → `Citation.to_dict()` → `ToolResultSuccess.value` → `accepted_tool_outcome_json` → `raw_tool_outcome`，确认路径为 `result.value.citation` |
| `TOOL_AWAITING` payload 字段变更是否完整 | ✅ 删除 `normalized_arguments_digest`、`accepted_arguments`、`accepted_arguments_source_digest` + 任何 `arguments_*` 副本；新增 `tool_call_requested_event_ref={event_id,event_sequence}` |
| `_validate_wait_request_arguments_digest` 删除后 digest 校验如何保障 | ✅ `tool_call_request_atoms` 已在 reader 侧校验 `arguments_payload_digest == normalized_arguments_digest`，awaiting 的 digest proof 转移到 request atom reader |
| 四 consumer fail closed 是否一致 | ✅ 均为 `HostDurableError`，不 skip/fallback/limited signal |
| `business_source_text/state` 类型是否自足 | ✅ `str` + `AcceptedToolResultSourceState.value`（`available\|unavailable`），直接从 `projection.source` 映射 |

### 3.2 语义所有权

| 挑战项 | 验证结果 |
| --- | --- |
| Host 是否 import Fins | ✅ §1.4 非目标明确禁止；source projection 只读 `raw_outcome` 的精确 JSONPath |
| Host 是否枚举 citation keys | ✅ §4.6 "Host 不枚举、筛选、排序或解释 citation 业务 key"；整个 citation object 机械渲染 |
| 是否引入 BusinessSource | ✅ §1.4 非目标明确禁止 |
| producer schema 修正是否在 owner 处 | ✅ §7.2/§7.4 `fetch_more` 在 `tool_runtime.py`、`url` 在 `web_tools.py`、Fins 在 `fins_tools.py` — 均为 producer owner |
| opaque refs 是否彻底隔离 | ✅ `source_locator_refs` 从 `AcceptedToolResultProjection`、`RunInputMaterialBlock`、`InitialEvidenceMaterial` 删除；EventLog envelope 保留 |

### 3.3 耦合

| 挑战项 | 验证结果 |
| --- | --- |
| S1/S2/S3 依赖是否最小 | ✅ S1 建立 durable identity → S2 在 stable atom 上做 source audit → S3 在 stable material 上做 propagation closure |
| 跨 slice 文件修改是否有冲突 | ✅ S1 改 `_event_payload.py`（删除 `llm_safe_replay_arguments`）、S2 删除 `json_redaction.py`（不同函数/模块），无冲突 |
| shared writer 是否引入过度抽象 | ✅ 单一 `build_tool_call_requested_event_request` 函数 + typed input dataclass，不做 facade、factory 或 profile |

### 3.4 LLM-facing

| 挑战项 | 验证结果 |
| --- | --- |
| 旧 "可安全展示" 文案是否全部替换 | ✅ `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 替换为业务中性文案；`ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT` 删除；§11.4 测试矩阵覆盖 |
| cursor/scope_token 是否正确标注为引用标签 | ✅ §7.4 "`cursor`/`scope_token` 说明必须原样使用上一条结果给出的引用标签，标签不是业务事实或推理依据" |
| prompt assets 是否有遗漏修改 | ✅ §8.1 37 个 prompt asset 全部人工审计为 compliant/no-diff |
| internal placeholder 文案是否删除 | ✅ §4.7/§11.3 item 8 明确删除 "参数正文由 accepted-result 同源投影提供" 等内部术语 |

### 3.5 安全保留

| 挑战项 | 验证结果 |
| --- | --- |
| `file_path` 是否被 blacklist 误删 | ✅ §1.3 "file_path、上传文件路径、合法业务字段和 framework scope_token 不因字段名被删除或改写" |
| credential 是否进入 LLM schema | ✅ §3.4 "current production tool schemas 没有 api_key/password/credential/access_token 参数"；`password` 命中仅属 URL userinfo |
| scope_token 是否暴露为业务事实 | ✅ §7.4 明确标注为 "引用标签"，不是业务事实或推理依据 |

### 3.6 Inventory

| 挑战项 | 验证结果 |
| --- | --- |
| prompt asset 覆盖 | ✅ 37 个文件，§8.1 全覆盖 |
| constructor scan 覆盖 | ✅ 114 个路径，§8.4 全覆盖 |
| R01 §11 handoff 消费 | ✅ 30 rows（5+5+5+5+10），§9 全覆盖 |
| slice count | ✅ 仅 S1/S2/S3，无第四 slice |

### 3.7 Smoke / Deferred

| 挑战项 | 验证结果 |
| --- | --- |
| real smoke 是否不可降级 | ✅ §12.2 "缺任一前置条件时不能把 smoke 标成 skipped/pass，也不能用 fake tool 替代" |
| Issue #177/#178 是否被排除 | ✅ §1.4 非目标 |
| stop conditions 是否覆盖 | ✅ §16 八个 stop condition |

### 3.8 Test Gaps

| 挑战项 | 验证结果 |
| --- | --- |
| corruption matrix 覆盖 | ✅ §4.5 14 个 corruption/negative case + §6.4 测试列表 |
| sentinel propagation 覆盖 | ✅ §11.4 三组 sentinel（`fliing-typo`、`eventlog`、`eventlogg`）× 四 consumer |
| idempotency 覆盖 | ✅ §6.4 same-key/same-digest、same-body existing-row、different-digest conflict |
| transaction rollback 覆盖 | ✅ §6.4 三个注入点（request append 后、awaiting append 后、后续 mutation 处） |
| coverage targets | ✅ §13.3 逐文件 target，最高 `>=95%`（`tool_call_request.py`） |

## 4. 新 findings

无 material findings。

所有八个原始 findings（F01–F08）均已在修订计划的 owner-correct 位置关闭，修订内容与当前代码事实一致，无新引入的正确性、所有权、耦合、LLM-facing、安全保留、inventory、smoke/deferred 或 test gap。

## 5. Open Questions

无。

## 6. Residual Risks

与修订前一致，无新增：

| 风险 | 当前处理 | destination |
| --- | --- | --- |
| real smoke 环境不可用 | completion 必须真实通过；不能 skip/fake/降级 | controller 提供/确认 smoke 环境 |
| 非 Fins tools 无 explicit citation | source-unavailable，不猜 | 对应 tool producer |
| EventLog envelope 仍保存 opaque refs | internal provenance contract | evidence/audit owner |
| Issue #177/#178 | 完全不进入 R03 | 各 issue owner |

## 7. Plan Review Conclusion

**PASS**。

修订计划已 code-generation-ready。八个原始 findings 全部在 owner-correct plan 位置关闭：

- **F01**：transaction sequencing 明确为 `append_event(...).row` 取真实 sequence → 构造 ref → 传入 awaiting；禁止预估/硬编码/从 wait id 推导
- **F02**：`_source_projection(raw_outcome, diagnostics)` 签名固定；JSONPath 为 `result.value.citation`；Host 机械渲染整个 citation object
- **F03**：`business_source_text/state` 类型为 `str` + `AcceptedToolResultSourceState.value`；直接从 `projection.source` 映射
- **F04**：四 consumer 统一 `HostDurableError` fail closed；删除 fallback/limited signal/skip
- **F05**：identity digest 原样映射；三个 helper 删除闭集已证实
- **F06**：Tool Trace request 通过 strict atom resolver；删除 redaction/placeholder
- **F07**：`__init__.py` 只删 docstring module item；保留 `>=80%` coverage
- **F08**：sentinel 含 `eventlogg` typo；旧 "可安全展示" 文案全部替换/删除

全计划重新挑战未发现新 gap。无结构性不安全、无过度耦合、无 owner 边界违反、无 deferred scope 泄漏。
