# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction 独立复审（AgentDS）

## 1. 复审结论

**PASS**

本复审是对既有 R03-S1 plan correction 的完整独立 adversarial review，不是新 WU、新 plan 或 implementation authorization。

修订计划（`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` 经 AgentCodex correction artifact 修改后的版本）在 durable transition writer owner、source Attempt identity、WaitRecord/source Attempt 同源 precondition、resume/terminal union 共用 writer、public/direct 两层测试分离、exact allowlist、coverage、stop、fresh-schema/no-compatibility 与 S2/S3/Issue #177/#178 scope boundary 上，经独立 adversarial challenge 后零 material finding。

## 2. 复审范围与方法

### 2.1 已读取输入

按用户指定顺序完整读取：

| 序号 | 文件 | 用途 |
| --- | --- | --- |
| 1 | `AGENTS.md` | 项目硬约束、语义所有权规则、编码规范 |
| 2 | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` | 完整修订计划（含 AgentCodex correction 修改） |
| 3 | `docs/reviews/wu-semantic-ownership-01-r03-plan-rereview-controller-adjudication.md` | R03 final plan adjudication（ACCEPTED_PLAN） |
| 4 | `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-adjudication.md` | R03-S1 plan correction 触发裁决 |
| 5 | `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-codex.md` | AgentCodex correction artifact |
| 6 | `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-validation.md` | Controller correction validation |
| 7 | `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md` | 已有 S1 implementation artifact（受保护输入） |
| 8 | `docs/host/design.md` | Host 设计真源 |

### 2.2 已核对直接代码证据

| 文件 | 核对行/区域 | 核对目标 |
| --- | --- | --- |
| `dayu/host/durable/run_transition.py` | L3737–3766 `_waiting_tool_result_event_request` | `execution_id=None` 硬编码缺陷 |
| `dayu/host/durable/run_transition.py` | L1755–1858 `resume_run_from_waiting_in_transaction` | resume union 分支的 source_attempt 已读取但未传入 writer |
| `dayu/host/durable/run_transition.py` | L1861–1881 `fail_run_from_waiting_in_transaction` | terminal union 分支同理 |
| `dayu/host/durable/run_transition.py` | L1884–1904 `mark_run_lost_from_waiting_in_transaction` | lost terminal 分支同理 |
| `dayu/host/durable/run_transition.py` | L1907–1986 `_terminal_run_from_waiting_in_transaction` | 共用 writer 调用与 sequencing |
| `dayu/host/durable/run_transition.py` | L5299–5369 `_invalid_waiting_resolution_precondition` | 无 `wait_record.execution_id == source_attempt.execution_id` 检查 |
| `dayu/host/durable/run_transition.py` | L567–641 `ResumeRunFromWaitingInput` / `WaitingRunTerminalInput` | 无 `suspended_execution_id` 字段 |
| `dayu/host/durable/state.py` | L330–347 `AttemptRow` | `execution_id: str` 字段确认 |
| `dayu/host/durable/state.py` | L481–515 `WaitRecordRow` | `execution_id: str` 字段确认，无 FK 约束 |
| `dayu/host/waiting.py` | L1136–1208 `_resolve_resume` | public resolve 路径：构造 `ResumeRunFromWaitingInput` 但不传 `suspended_execution_id` |
| `dayu/host/waiting.py` | L1210–1279 `_resolve_failed` | public failed 路径：同理 |
| `dayu/host/waiting.py` | L1838–1919 `_tool_result_resolution_payload` | 上游 request-atom guard：L1947 校验 `awaiting.execution_id != wait_record.execution_id` |
| `dayu/host/waiting.py` | L1922–1957 `_wait_tool_call_requested_event` | 确认 public corrupt path 先抛 `HostDurableError`，不可达 transition |
| `tests/host/test_resolve_wait_command.py` | L152–197 `test_resolve_wait_completed_resumes_run_and_wakes_dispatch` | 当前 public test 不断言 `execution_id` |
| `tests/host/test_resolve_wait_command.py` | L542–620 `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` | 当前 public terminal test 不断言 `execution_id` |
| `tests/host/test_resolve_wait_command.py` | L1062–1095 `_seed_waiting_run` | 确认 seeded execution_id 为 `"execution-resolve"` |

### 2.3 未读取但无影响

`docs/host/issues-implementation-control.md` 文件过大（368KB），未完整读取。该文件是 WU 总控文档，其 R03-S1 相关内容已通过 control validation artifacts 间接覆盖；总控的 gate routing 与状态机不影响本次 plan correction 的 owner contract 核查。

## 3. Assumptions 逐项 adversarial challenge

### A1. durable transition writer 是 `execution_id` 的唯一 owner

**claim**：`_waiting_tool_result_event_request` 是 wait-resolution `TOOL_RESULT_ACCEPTED` 的 EventLog writer，应使用 suspended source Attempt 的 durable `execution_id`。

**direct evidence**：
- `_waiting_tool_result_event_request` (L3737–3766)：`execution_id=None` 硬编码。
- 两个 caller (`resume_run_from_waiting_in_transaction` L1771, `_terminal_run_from_waiting_in_transaction` L1931) 均已读取 `source_attempt: AttemptRow`，但未将其传入 writer。
- `ResumeRunFromWaitingInput` 有 `suspended_attempt_id: str` (L595)，但没有 `suspended_execution_id`。
- 唯一其他 candidate writer（`_tool_result_resolution_payload` in `waiting.py` L1877）使用 `execution_id=wait_record.execution_id` 仅构造 payload JSON，不写 EventLog 的 `execution_id` column。

**challenge result**：**成立**。当前 EventLog `execution_id` 的唯一 writer 是 `_waiting_tool_result_event_request`，它将 `execution_id` 硬编码为 `None`。transition 已拥有 `source_attempt.execution_id`，只需传入 writer。

**反例**：无。Engine 不写 Host EventLog；`waiting.py` 只构造 JSON payload field `execution_id`，不是 EventLog column。没有其他模块可能成为该 `execution_id` column 的 writer。

---

### A2. `WaitRecord.execution_id` 与 `source_attempt.execution_id` 不同源时可在任何 append 前 fail closed

**claim**：`_invalid_waiting_resolution_precondition` 当前已校验 run/attempt/wait 的 id 与状态，只需增加 `wait_record.execution_id == source_attempt.execution_id` 即可在任何 append 前 fail closed。

**direct evidence**：
- `_invalid_waiting_resolution_precondition` (L5299–5369)：已有 12 个 explicit checks（L5344–5356），不包含 execution equality。
- 该函数在两个 caller 的 append 之前调用（`resume_run_from_waiting_in_transaction` L1773, `_terminal_run_from_waiting_in_transaction` L1933）。
- 返回 `INVALID_STATE` 时（L5358），所有 event/state mutation fields 均为 `None`。

**challenge result**：**成立**。新增一个 equality check 与现有 checks 的执行时序完全相同（在所有 append 之前），语义一致（都是 identity/status mismatch → `INVALID_STATE`）。

**反例**：如果 `WaitRecord.execution_id` 在 SQLite schema 中受 UNIQUE 约束且与另一记录的 `execution_id` 冲突——不存在此约束。`WaitRecordRow.execution_id` 是普通 `str` 字段，无 UNIQUE 或 FK 约束。

---

### A3. resume/terminal union 共用 writer 不会引入分支差异

**claim**：`resume_run_from_waiting_in_transaction` 与 `_terminal_run_from_waiting_in_transaction` 共用 `_waiting_tool_result_event_request`，修复后两个 union 分支都写 `source_attempt.execution_id`。

**direct evidence**：
- resume path (L1790): `_waiting_tool_result_event_request(request, run)`
- terminal path (L1947): `_waiting_tool_result_event_request(request, run)`
- 二者传入完全相同的参数 `(request, run)`，使用同一个 writer。
- 修复后二者都将接收 `source_attempt` 参数。

**challenge result**：**成立**。共用已存在于当前代码；修复只需同步修改 writer 签名和两个 call site。

---

### A4. public guard 不能冒充 lower proof

**claim**：public `resolve_wait` 路径中 `_wait_tool_call_requested_event` (L1947) 先校验 `awaiting.execution_id != wait_record.execution_id`，腐化 WaitRecord execution 后会先抛 `HostDurableError`，不会到达 transition 的 `INVALID_STATE`。因此需要独立 direct transition test。

**direct evidence**：
- public call chain：`resolve_wait` → `_resolve_resume/_resolve_failed/_resolve_lost` → `_tool_result_resolution_payload` → `_wait_tool_call_requested_event` (L1947: `awaiting.execution_id != wait_record.execution_id` → `HostDurableError`) → 然后才调用 transition。
- Transition call chain：`resume_run_from_waiting_in_transaction` → `_invalid_waiting_resolution_precondition` → 当前无 execution equality check。
- 两层 guard 校验不同语义：public guard 校验 request-atom/awaiting link 一致性；transition guard 校验 WaitRecord/source Attempt identity 同源。两者都是正确的 owner-level validation，不能互相替代。

**challenge result**：**成立**。两层 guard 在不同 owner boundary 校验不同 invariant，不可合并或替代。

---

### A5. direct transition mismatch fixture 的 FK 可行性

**claim**：用 `create_running_run_with_starting_attempt_in_transaction` 创建辅助 Attempt（FK-valid），腐化目标 WaitRecord 的 `execution_id` 为辅助 Attempt 的值，可以制造 WaitRecord/source Attempt execution 不同源但 FK 仍 valid 的测试前提。

**direct evidence**：
- `WaitRecordRow` L488–492: `attempt_id: str`, `execution_id: str` — FK 在 `attempt_id`，不在 `execution_id`。
- `create_running_run_with_starting_attempt_in_transaction` 在 test fixture 中已作为 helper 使用（`test_resolve_wait_command.py` L1149）。
- `_seed_waiting_run` (L1062–1095) 使用 `execution_id="execution-resolve"` 建立正常 Run/Attempt。
- 辅助 Attempt 使用不同 Run/Attempt id 和不同 `execution_id`，FK 通过 `attempt_id` 满足。

**challenge result**：**成立**。SQLite FK 在 `attempt_id`，腐化 `execution_id` 不违反任何约束。

**次要实现注意**：需要直接 UPDATE `host_wait_records.execution_id`（当前 state 模块可能无此 helper），但这是测试层实现细节，不构成 plan 级别歧义。

---

### A6. 全表 no-partial assertion 的完整性

**claim**：direct transition test 在 `INVALID_STATE` 返回后，以腐化前的 durable snapshot 为 baseline，按稳定主键顺序读取并断言 EventLog、`host_runs`、`host_attempts`、`host_wait_records`、`host_attempt_dispatch_records` 全表 rows 完全相等。

**direct evidence**：
- `INVALID_STATE` 返回前只有 `_invalid_waiting_resolution_precondition` 中的只读检查（L5344–5356），无任何 append/mutation。
- 所有 event/state mutation fields 在 `INVALID_STATE` 路径中均为 `None`（L5358–5368）。
- 确认：如果未来有人在 precondition 之后、INVALID_STATE 返回之前插入副作用，全表 assertion 会检测到。这是该测试设计的防御价值。

**challenge result**：**成立**。全表 snapshot 比较覆盖了直接和间接 side effects。

---

### A7. exact allowlist 闭合性

**claim**：纠正后的 S1 implementation exact allowlist 为 8 production + 9 test + 2 README。

**direct evidence**：
- production：`tool_call_request.py`（新增）, `tool_runtime.py`, `waiting.py`, `_event_payload.py`, `payload_resolution.py`, `accepted_result_projection.py`, `run_input.py`, `durable/run_transition.py`
- test：`test_toolruntime_accept_barrier.py`, `test_wait_awaiting_accept.py`, `test_resolve_wait_command.py`, `test_run_input_builder.py`, `test_accepted_result_projection.py`, `test_compact_material.py`, `test_memory_projection.py`, `test_tool_trace_projection.py`, `test_tool_trace_queries.py`
- doc：`dayu/host/README.md`, `tests/README.md`

**challenge result**：**成立**。相较已接受 S1 边界只新增 `run_transition.py`（production owner）和一个 test file（`test_resolve_wait_command.py` 已是 allowlist 内）。四个 strict-consumer test path 是 Controller 已接受的 test-only 扩边。

**边界验证**：现有 dirty implementation diff 路径（`git status` 显示的 M/?? paths）与 allowlist 的集合差异 = `dayu/host/tool_call_request.py`（新增，在 allowlist 内）+ Controller artifacts（`docs/reviews/wu-semantic-ownership-01-r03-s1-*.md`，不在 implementation allowlist 内，属于 gate artifacts）。无计划外 production/test/doc 文件。

---

### A8. S2/S3/deferred scope 未侵入

**claim**：修订计划严格限制在 S1 scope，不含 S2 blacklist 删除、S3 opaque-ref propagation、Issue #177/#178 或统一 tool authorization。

**direct evidence**：
- §1.4 非目标：显式排除 Issue #177/#178、统一 auth、BusinessSource、compatibility/migration。
- §6.2 exact allowlist：不含 `dayu/runtime/json_redaction.py`（S2）、`dayu/host/evidence.py`（S3）、`dayu/host/memory.py`（S3）、`dayu/host/compact_material.py`（S3）、`dayu/host/tool_trace.py`（S2/S3）。
- §6.3 符号级改动：只有 S1 的 shared writer、TOOL_AWAITING ref、resolve strict link、request-atom guard、accepted-result strict projection、resume exact args、transition writer/precondition。没有 blacklist、safe/unsafe classifier、opaque ref separation、citation/renderer contract。
- AgentCodex implementation artifact §9.2：diff-only scan 确认 S1 未实施 S2/S3 改动（`rg` on OpaqueEvidenceRef/source_refs 零 diff 命中）。
- §16 risk table：S2/S3 风险 listed with destination = later approved slice。

**challenge result**：**成立**。Scope boundary 清晰可验证。

---

### A9. fresh-schema / no-compatibility

**claim**：R03 按 fresh schema 起库，不提供旧 EventLog/schema migration、compatibility reader、fallback message 或 legacy fixture。

**direct evidence**：
- §1.4 非目标："不为旧 EventLog/schema 提供 migration、compatibility reader、fallback message 或 legacy fixture；本 WU 按 fresh schema 起库。"
- §4.5 corruption contract：所有 corruption/negative case 都是 fail closed（`HostDurableError` 或 `INVALID_STATE`），不走 fallback。
- §4.5 明确删除 `_resume_wait_fallback_message`。
- §6.3.9：删除 resume fallback message 与 safe/fallback docstring。
- AGENTS.md L93：schema 变更一律按全新 schema 起库，禁止旧库兼容读取。

**challenge result**：**成立**。No-compatibility 是项目全局约束且被 plan 显式遵守。

---

### A10. coverage targets 与 stop conditions

**claim**：S1 逐文件 coverage >= 80%（`tool_call_request.py` >= 95%，`payload_resolution.py`/`accepted_result_projection.py` >= 90%），低于目标必须补 allowlist 内 owner-level tests 或停止。

**direct evidence**：
- §6.5 coverage table 列出每文件目标、primary owner tests、验证命令。
- §6.6 stop："若 upstream 无法提供 exact canonical arguments、durable source Attempt 无法提供 exact execution id... 立即停止回 Controller。"
- §16 stop conditions 表：列出 11 个具体 stop 条件。

**challenge result**：**成立**。Coverage targets 与 stop conditions 都显式、可验证、绑定到具体文件与反例。

---

## 4. Architecture Boundary Review

| boundary | 当前 owner | plan 修改 | 是否穿透 |
| --- | --- | --- | --- |
| EventLog `execution_id` column writer | `_waiting_tool_result_event_request` in `run_transition.py` | 是 — 接收 source_attempt，写 `source_attempt.execution_id` | 否 |
| `TOOL_CALL_REQUESTED` append | ordinary/awaiting caller via shared writer | 否 — 已在 S1 implementation 中完成 | 否 |
| `TOOL_AWAITING` payload | `_event_payload.py` | 否 — 已在 S1 implementation 中完成 | 否 |
| WaitRecord durable row | `state.py` mutation helpers | 否 — `execution_id` 由 accept-time 写入，不改 | 否 |
| AttemptRow durable row | `state.py` mutation helpers | 否 | 否 |
| resolve wait public API | `waiting.py` `DefaultHostResolveWaitService` | 否 — 只在构造 transition input 时可能需要传新字段 | 否（同一层内调用） |
| RunInput builder | `run_input.py` | 否 — strict consumer equality 已在 S1 落地 | 否 |
| strict consumer equality | `accepted_result_projection.py` | 否 — `execution_id=None` 兼容已删除 | 否 |

唯一新增的 owner boundary 是 transition → EventLog `execution_id` column，这是现有 durable writer 职责的正确执行，不是新建 abstraction。

## 5. Overcoupling Review

- transition writer 接收 `source_attempt: AttemptRow` 会引入 `run_transition.py` 对 `state.AttemptRow` 的现有依赖（该模块已大量依赖 state types）。 无新增耦合。
- 计划中的 "等价的明确 typed source execution 参数"（即只传 `source_execution_id: str`）更轻量，但两种方案都在当前模块的依赖边界内。
- resume/terminal union 共用 `_waiting_tool_result_event_request` 保持不变；不改现有复用关系。
- public guard (`_wait_tool_call_requested_event`) 与 transition guard (`_invalid_waiting_resolution_precondition`) 职责分离：前者校验 request-atom link，后者校验 durable identity 同源。分层 guard 不耦合。

**结论**：无 material overcoupling。

## 6. Overengineering Review

- 修订计划只新增一个 precondition check 和修正一个 hardcoded `None`，不新建 abstraction、builder、protocol、migration 或 config 项。
- direct transition test 使用现有 fixture helper（`_seed_waiting_run`、`create_running_run_with_starting_attempt_in_transaction`），不新建 test utility module 或 production seam。
- 只有一个新增 test file（`test_resolve_wait_command.py` 已在 allowlist 内），不需要新建测试文件。

**结论**：无 overengineering。

## 7. Open Questions

无。

## 8. Residual Risks

| 风险 | 严重程度 | 跟踪 |
| --- | --- | --- |
| direct transition test 需要 raw UPDATE 修改 `WaitRecord.execution_id`，当前 state 模块可能无此 helper | 低 | 测试层实现细节；可用 `transaction._connection.execute("UPDATE host_wait_records SET execution_id = ? WHERE wait_id = ?", ...)` 解决 |
| `waiting.py` 构造 `ResumeRunFromWaitingInput` 时可能需要新增 `suspended_execution_id` 字段传入 | 低 | 已在 plan allowlist 内；`wait_record.execution_id` 在 caller scope 中可直接读取 |
| 如果 plan 选择传 `AttemptRow` 而非 `str`，writer 签名变化可能被 future refactor 误改回 `None` | 低 | `test_resolve_wait_command.py` 的 public 正常 identity test 会因 strict consumer equality 失败而立即捕获 |

## 9. 最终复审结论

**PASS**

修订计划在 durable transition writer owner、source Attempt execution identity、WaitRecord/source Attempt 同源 precondition 执行时序、resume/terminal union 共用 writer、public/direct 两层测试职责分离、direct transition mismatch fixture FK 可行性、全表 no-partial assertion、exact allowlist、coverage targets、stop conditions、fresh-schema/no-compatibility 与 S2/S3/deferred scope boundary 上，经独立 adversarial challenge 后没有发现 material finding。

计划已 code-generation-ready，可按现有 gate routing 进入 MiMo/DS 双路 review 和 Controller adjudication。

---

*复审时间：2026-07-15 09:31 CST*
*复审人：AgentDS（planreview skill）*
*复审范围：plan correction only；未修改 plan/code/tests/control/prior artifacts*
