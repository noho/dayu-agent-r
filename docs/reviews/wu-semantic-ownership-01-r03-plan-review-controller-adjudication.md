# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Review Controller Adjudication

## 1. Gate 与输入

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：`R03`。
- plan：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`。
- reviews：`docs/reviews/wu-semantic-ownership-01-r03-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-r03-plan-review-ds.md`。
- verdict：**PLAN_FIX_REQUIRED**。这是同一 R03 plan task 的 follow-up；不 clear AgentCodex，不进入 implementation，不创建新 WU。

Controller 完整读取两份 review，并以当前源码复核 EventLog append、accepted outcome codec、accepted-result projection、Tool Trace、Memory/Compact renderer 与 ToolRuntime/waiting candidate。两路均确认 root cause、三片 sequencing、inventory、R01 handoff、Engine no-diff 与 deferred boundary 正确；以下 accepted findings 只补足 code-generation-ready contract，不改变产品裁决或 slice 数量。

## 2. Accepted plan findings

### R03-PLAN-F01 — transaction 内真实 request row ref sequencing

- **来源**：DS-F01；MiMo 005。
- **直接证据**：ordinary `tool_runtime.py` 与 awaiting `waiting.py` 当前都先 `append_event(...).row` 再写后续 facts；`EventLogAppendResult.row` 已包含真实 `event_sequence`。
- **裁决**：accepted。计划须明确 awaiting accept 的顺序：shared writer 构造 request -> append 得真实 row -> 以 row 的 `event_id/event_sequence` 构造 ref -> append `TOOL_AWAITING` -> 后续 run/attempt/wait facts；同一 transaction rollback 与 idempotent existing-row replay保持原子。禁止预估、硬编码或从 wait id 推导 sequence。

### R03-PLAN-F02 — citation projection 的精确输入与 canonical JSONPath

- **来源**：MiMo 001；DS-F02。
- **直接证据**：`accepted_tool_outcome_json(ToolCompletedOutcome)` 明确输出 `{"kind":"completed","result":{"ok":true,"value":...}}`；Fins read runtime 把 citation object写入 success value 的 `citation`，`project_accepted_tool_result` 已得到 canonical `raw_outcome`。
- **裁决**：accepted with owner correction。计划须指定 `_source_projection(raw_outcome: JsonValue | None, diagnostics: list[str])`（命名可按实现惯例微调）由 `project_accepted_tool_result` 直接传入已 digest-check 的 `raw_outcome`，只在 `kind == "completed"`、`result.ok is True`、`result.value` 为 object、`citation` 为 object时将**整个 citation object**用 `canonical_json_dumps` 渲染；其它情况统一 source-unavailable。Host 不枚举/解释 Fins citation keys，不 import Fins，不接收 opaque refs，不引入 `BusinessSource`。S3 测试必须用真实 `accepted_tool_outcome_json(ToolCompletedOutcome(ToolResultSuccess(...)))` 构造路径，不能手写一个与 codec 脱节的假 shape。

### R03-PLAN-F03 — Tool Trace business source 字段映射

- **来源**：MiMo 002。
- **裁决**：accepted。计划须明确 readable `tool_result` mapping 增加两个字符串字段：`business_source_text = projection.source.text`、`business_source_state = projection.source.state.value`，state 复用现有 `AcceptedToolResultSourceState` 的 `available|unavailable`，不新建 enum/类型或复制 citation parser。`diagnostic_reason` 只留 internal projection/diagnostic，不作为业务来源文本。

### R03-PLAN-F04 — 四消费者统一 strict material 失败语义

- **来源**：MiMo 003。
- **裁决**：accepted。计划须明确 `render_accepted_tool_evidence_for_llm` 只接收非 optional material；任一 canonical `TOOL_RESULT_ACCEPTED` 在 projection 后缺 `llm_material` 时，RunInput、Memory、Compact 和 LLM-ready Tool Trace 都在 owner boundary 抛 `HostDurableError`，不得跳过单条 evidence、生成 fallback/limited signal、局部 catch 后继续或把内部 ref投影给模型。现有上层 durable error path负责暴露失败；R03 不新增 consumer-specific recovery。

### R03-PLAN-F05 — shared atom 输入映射与删除闭集

- **来源**：MiMo 004；DS-N04。
- **裁决**：accepted。计划须记录 `_accepted_arguments_json` / `_awaiting_semantic_query_text` 当前仅由 waiting 本地 request writer 调用，删除闭集已证实；ordinary 的 `tool_identity_digest` 从 `ToolAcceptCall`、awaiting 从 `ToolAwaitingAcceptCandidate` 显式映射到 shared atom，不能在 builder 重算或从 schema/log反推。

### R03-PLAN-F06 — request-event readable Tool Trace 不得投影内部实现提示

- **来源**：DS-N05，Controller owner correction。
- **直接证据**：计划原建议文案“参数正文由 accepted-result 同源投影提供”包含内部实现术语，不满足 AGENTS LLM-facing 约束；当前 Tool Trace canonical fact path已有 transaction 和 event id。
- **裁决**：accepted。S3 必须让 `TOOL_CALL_REQUESTED` readable summary 通过 `read_event_by_id` + strict `tool_call_request_atoms` 解析 inline/descriptor exact args和 semantic query；展示 bounded exact args，不展示 ref/digest，不发内部占位提示。损坏同样 `HostDurableError` fail closed。

### R03-PLAN-F07 — runtime package 文档项与 coverage 边界

- **来源**：DS-F04。
- **裁决**：accepted in part。计划须明确 `dayu/runtime/__init__.py` 只删除模块概览 docstring 中的 `dayu.runtime.json_redaction` 列表项，无 re-export 或运行逻辑改动；仍按 AGENTS 的修改文件 coverage 目标保留 `>=80%`，由现有 package import/export test证明，不因改动小而豁免。

### R03-PLAN-F08 — propagation 负例与旧文案 assertions

- **来源**：MiMo N1；DS-N02。
- **裁决**：accepted。S3 sentinel matrix追加当前 internal-kind typo（如 `eventlogg`），并明确更新旧 source-unavailable/fallback 文案 assertions；不得保留旧 safe-display 语义或 compatibility alias。

## 3. Rejected / already-covered items

- **DS-F03 rejected / no code**：真实 Doc/Web/Fins public-run smoke 是用户要求的 aggregate hard gate，不能因外部环境成本降级；计划已经允许 S1/S2/S3 各自按完整 gate接受，再在 aggregate smoke 阻塞时报告真实 blocker。新增 minimal Doc-only path不能替代 Web/Fins awaiting closure，且现有 full smoke 本身已含 Doc ordinary run。
- **MiMo 001 的 citation key 枚举建议 rejected**：Host 枚举 `source_type/ticker/document_id/...` 会建立 Fins semantic reverse dependency；accepted fix机械渲染完整 producer-owned citation object。
- **MiMo N3 already covered**：S1 tests 已列 small/large inline/descriptor、idempotent same-key 与 different-digest conflict。
- **DS-N03 already covered**：计划 source gates 已扫描 `_INTERNAL_SOURCE_REF_KINDS` / `_readable_ref_text` 与旧 contract测试。
- **DS-F04 的 coverage 降级建议 rejected**：AGENTS 要求所有修改代码文件执行单文件 coverage gate；docstring-only package文件可通过 import test自然覆盖。
- 其它 non-blocking notes 作为实施注意项保留，不新增 plan scope或第四 slice。

## 4. 下一入口

下一入口仅为 AgentCodex 同一 plan task follow-up：修改 plan artifact关闭 `R03-PLAN-F01..F08`，新增 plan-fix artifact `docs/reviews/wu-semantic-ownership-01-r03-plan-fix-codex.md`，记录逐项修复位置和 artifact-only validation。不得修改 control、review artifacts、production、tests、README/design，不 commit/push，不进入 implementation。之后必须由 AgentMiMo / AgentDS 对完整修订计划并发 re-review。
