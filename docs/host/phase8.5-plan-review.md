# P8.5 Plan Review Artifact

- **review gate name**: plan review
- **reviewed target**: `docs/host/phase8.5-plan.md`
- **reviewer**: plan review agent (Claude)
- **review date**: 2026-05-11
- **reviewer conclusion**: **pass-with-risks**
- **artifact path**: `docs/host/phase8.5-plan-review.md`

## Assumptions Tested

1. **fetch_more 具体工具名编码进 RunEventType 是 root cause** — 成立。`contracts.py:73-75`、`_run_event_serializer.py:1476-1478`、`_conversation_memory.py:690-741`、`_tool_trace_projection.py:611-684` 均直接绑定 `ToolFetchMore*Data`。
2. **通用 tool-call facts 已经覆盖 fetch_more request/result** — 成立。`_event_translation.py:117-139` 已对 `fetch_more` 的 `TOOL_CALL_REQUESTED` 做 redaction，说明通用路径已存在。
3. **durable memory repair 存在全 EventLog 扫描** — 成立但需澄清。`_collect_missing_session_ids()` 用 SQL `LEFT JOIN` 按 `kind` 过滤，可利用索引；但 `_fetch_canonical_events_for_session()` 按 global position 分页拉取全量后 client-side 过滤 session_id，确实是 O(全库)。
4. **ToolTraceObserver 在 SQLite 事务内执行同步 I/O** — 成立。`_event_observer.py:262-263` 在 `self.storage.transaction()` 内 `await observer.process(tx, ...)`，`_tool_trace_jsonl_sink.py:173-174` 在 process 内执行 `flush+fsync`。
5. **`_verify_run_id_matches()` 用 OWNER_MISMATCH 表达 run_id mismatch** — 成立。`_attempt_supervisor.py:414`。
6. **`lease_context` 缺少参数校验** — 成立。`_attempt_supervisor.py:511-548` 无 `run_id` 非空、`attempt_index >= 0` 校验。
7. **RunInput raw payload 内联进 EventLog** — 成立。`contracts.py:581-582` 有 `raw_input_messages_json: str`、`raw_tool_schemas_json: str` 字段，`_run_input_context_fact.py:115-119` 直接 `json.dumps` 内联。
8. **Affected files 引用 `tests/host/test_run_event_serializer.py`** — 不成立，实际文件为 `tests/host/test_phase6_run_event_serializer.py`。
9. **open questions 是否收敛** — 大部分收敛，但存在两个 blocking implementation choices。

## Findings

### 01-未修复-[中]-plan affected files 引用不存在的测试文件路径
- **Plan位置**: §5 Affected Files / Modules → Host contracts / serializer 行
- **问题类型**: 不可直接实施
- **计划当前写法**: `tests/host/test_run_event_serializer.py` 或 "现有 serializer 覆盖文件"
- **为什么有问题**: `tests/host/test_run_event_serializer.py` 不存在。实际文件是 `tests/host/test_phase6_run_event_serializer.py`。plan 同时还提到 "tool trace / memory projection 相关测试文件" 但未指定具体路径。implementation agent 需要自行搜索定位，增加了 handoff 歧义。
- **直接证据**: `Glob("tests/host/test_*serializer*.py")` 返回 `tests/host/test_phase6_run_event_serializer.py` 和 `tests/host/test_phase7_contract_serializer.py`。
- **影响**: implementation agent 可能新建冗余文件或遗漏已有测试更新。
- **建议改法和验证点**: 将 `tests/host/test_run_event_serializer.py` 改为 `tests/host/test_phase6_run_event_serializer.py`；将 "tool trace / memory projection 相关测试文件" 明确为 `tests/host/test_phase7_*.py` 下相关文件。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### 02-未修复-[中]-RunInput raw payload side store 缺少 transaction 和 ownership 细节
- **Plan位置**: §2.4 point 3 和 §7 Required schema/index changes → RunInput raw payload side store
- **问题类型**: 契约缺失
- **计划当前写法**: 定义了 table columns 和 uniqueness，要求 "与 EventLog append 同一事务或具备明确失败回滚边界"。
- **为什么有问题**: 未指定 writer 是谁（`RunInputContextFactBuilder`？`LocalRunHarness`？），未指定 reader 是谁（`ToolTraceObserver`？`startup_reconcile`？），未指定是否使用同一个 `HostStorage` 事务。implementation agent 需要自行设计 transaction ownership 和 reader 路径，这是关键架构决定。
- **直接证据**: §7 定义了 columns 但只说 "EventLog fact stores only blob_id / content_hash / byte_size and summary fields"，未说明 side store 的 append 是在 `_run_input_context_fact.py` 还是 `_run_harness.py` 的哪个事务中完成。
- **影响**: implementation agent 可能设计出与 EventLog 非原子的 side store，或在 reader 路径引入 hidden dependency。
- **建议改法和验证点**: 明确 writer 在 `LocalRunHarness._run_to_store` 的 attempt 生命周期事务内；明确 reader 是 `ToolTraceObserver.process` 按 blob_id 回读；明确使用 `HostStorage.transaction()` 同事务。补充 stop condition：side store 无法与 EventLog fact 同事务时停下回报。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### 03-未修复-[中]-SSE partial tool-call diagnostic 的 layer boundary 不够明确
- **Plan位置**: §2.4 point 4 和 Slice 6
- **问题类型**: 架构边界
- **计划当前写法**: "Engine / Host trace 必须持久化一个通用 partial-tool-call diagnostic fact"；implementation prompt 说 "Host event translation / trace projection 必须能把该 diagnostic 写入 EventLog 或 trace record"。
- **为什么有问题**: SSE partial tool-call 发生在 Engine Runner 层（`sse_parser.py` / `runner.py`），但 diagnostic fact 需要进入 Host EventLog。plan 没有明确这个 diagnostic 是 Engine `EngineEvent` 的新成员，还是 Host `_event_translation.py` 在翻译 `RUN_FAILED` 时附加的 summary。如果是前者，Engine public contract 需要扩展；如果是后者，Engine 已有的 failure event 信息是否足以产生有意义的 partial summary 需要验证。
- **直接证据**: Slice 6 implementation prompt 说 "阅读 dayu/engine/runners/openai/sse_parser.py、runner.py、dayu/engine/agent.py" 但没有指定 diagnostic fact 的 owner layer。`agent.py` 可能需要检测 `_tool_calls_seen == True` 但 `_completed_tool_calls` 为空的状态。
- **影响**: implementation agent 可能把 partial diagnostic 放在 Engine 侧（扩展 EngineEvent，违反 "Engine 不扩展 RunEventType" 的隐含约束）或 Host 侧（但 Host 翻译时可能已丢失 partial delta 信息）。
- **建议改法和验证点**: 明确 diagnostic 是 Host-owned fact，在 `_event_translation.py` 翻译 `RUN_FAILED` 且检测到 Engine `RunnerToolCallsStartedData` 但无 `RunnerToolCallsCompletedData` 时生成。或者明确 Engine 需要新增一个 `RunnerPartialToolCallsData` 事件，由 Host 翻译为 RunEvent。二选一裁决后再 handoff。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### 04-未修复-[低]-durable memory repair `_fetch_canonical_events_for_session` 仍是全库扫描
- **Plan位置**: §2.2 point 3 和 Slice 3
- **问题类型**: 不可直接实施
- **计划当前写法**: 要求 "提供按 session_id 过滤的 durable event fetch 能力或等价 SQL helper，并配套索引"。
- **为什么有问题**: `_collect_missing_session_ids()` 已经用 SQL 做了高效过滤（LEFT JOIN + WHERE kind），但 `_fetch_canonical_events_for_session()` 仍然用 `fetch_events_by_position` 分页拉取全量 event 后 client-side 过滤 session_id。plan 说要加 index 和 helper，但没有指定 helper 的 SQL shape——是直接 `SELECT ... WHERE session_id = ? AND kind = ? ORDER BY event_position`，还是复用 `fetch_events_by_position` 并加 session 过滤参数？前者需要修改 `DurableRunEventStore` 接口，后者效率不够。
- **直接证据**: `_conversation_memory_durable.py:386-402` 确认当前实现是全库分页 + client-side 过滤。
- **影响**: 若 implementation agent 不改变 `DurableRunEventStore` 接口，只是加 index 不解决问题；若改变接口，需要同步更新 `fetch_events_by_position` 的所有调用方。
- **建议改法和验证点**: 明确新增 `DurableRunEventStore.fetch_events_by_session(session_id, kind, after, limit)` 方法，SQL 为 `SELECT ... FROM host_run_events WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`。新索引覆盖 `(session_id, kind, event_position)`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

### 05-未修复-[中]-attempt lease hardening Slice 7 过粗且包含 open design choice
- **Plan位置**: §8 Slice 7
- **问题类型**: 切片过粗
- **计划当前写法**: Slice 7 包含 6 个子任务：RUN_ID_MISMATCH reason、BUSY reason 细化、lease_context 参数校验、next_attempt_index 测试、renew_loop 竞争测试、recovery/fencing 覆盖。
- **为什么有问题**: (1) "BUSY reason 要细化到可诊断 attempt-index conflict" 是 open design choice：当前 `AttemptLeaseDecision.BUSY` 不携带 reason，需要在 `AttemptLeaseResult` 或 `AttemptFencingReason` 中新增枚举值，这是 contract 变更。(2) 6 个子任务中有 3 个是新测试（next_attempt_index、renew_loop、recovery/fencing），2 个是 contract 修正（RUN_ID_MISMATCH、BUSY），1 个是参数校验。对于一个 slice 来说，contract 变更 + adversarial tests 的组合容易让 implementation agent 在测试编写上消耗大量时间而忽略 contract 修正的边界。
- **直接证据**: `AttemptLeaseDecision` 只有 `ACQUIRED / BUSY / TERMINAL / FENCED`，`AttemptFencingReason` 没有 `RUN_ID_MISMATCH`。BUSY acquire 路径（`_run_state_store.py:531`）的 `IntegrityError` 到 `AttemptLeaseResult(decision=BUSY)` 不携带诊断 reason。
- **影响**: implementation agent 可能只做简单的 reason 枚举扩展而忽略 attempt-index conflict 的具体诊断信息，或在测试上耗时过长。
- **建议改法和验证点**: 将 Slice 7 拆为 7a（contract 修正：RUN_ID_MISMATCH + BUSY reason + lease_context 校验）和 7b（adversarial tests）。7a 更小更可验证。或者至少明确 BUSY reason 的具体枚举值名（如 `AttemptFencingReason.ATTEMPT_INDEX_CONFLICT`）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### 06-未修复-[中]-"不先做 append_many" stop condition 缺少可验证基线
- **Plan位置**: §2.1 point 6 和 Slice 2 implementation prompt point 7
- **问题类型**: 不可直接实施
- **计划当前写法**: "implementation 必须先用测试证明新模型下 fetch_more 不会在 required cursor mechanism fact 失败前向 Engine 返回成功结果"；若测试证明失败 "立即停下并回报，需要重新裁决事务边界"。
- **为什么有问题**: plan 没有定义"成功结果已持久化但 cursor fact 失败"的具体 failure scenario 如何注入。ToolRuntime 当前是先 append cursor facts 再返回结果（`_tool_runtime.py:840` 左右 completed_event append 在返回前），所以 call-return 顺序天然保证了 cursor fact 先于 Engine 收到结果。implementation agent 需要设计一个注入点让 cursor append 失败但 TOOL_RESULT_ACCEPTED 成功，这可能需要 mock EventLog append 或破坏事务。
- **直接证据**: `_tool_runtime.py:840` 显示 `completed_event = await self._append_fetch_completed(...)` 在返回前执行。如果 `_append_fetch_completed` 内部的 cursor fact append 失败，整个 `_fetch_more` 会抛异常，Engine 不会收到成功结果。
- **影响**: implementation agent 可能写出的测试只是验证当前 happy path（cursor append 成功），而不是真正测试 cursor fact 失败场景，导致 stop condition 形同虚设。
- **建议改法和验证点**: 明确注入方法：在 `_append_fetch_completed` 或等价路径的 cursor fact append 阶段注入 `sqlite3.DatabaseError`，断言 `_fetch_more` 抛出异常且 Engine 收到的是 failure outcome。或者如果当前代码已经天然保证了（因为 cursor append 在返回前），则明确说"当前 call-return 顺序天然保证，stop condition 不会触发，无需 append_many"，删除测试要求。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

### 07-未修复-[低]-open question 未收敛：corrupt snapshot 诊断的具体表达形式
- **Plan位置**: §2.2 point 2
- **问题类型**: open question 未收敛
- **计划当前写法**: "corrupt snapshot row 的默认处理是 fail fast / report repair required"；"P8.5 仅定义为'备份后删除损坏 snapshot row，再由 startup repair 走缺失 row 自动重建'"。
- **为什么有问题**: "fail fast / report repair required" 的具体表达未定义：是抛异常（什么类型？）、设置 status 字段、还是 log WARNING？当前 `_conversation_memory_durable.py:517-537` 和 `628-684` 在 decode/schema error 时直接抛异常，startup_reconcile 调用方是否 catch 了这个异常？如果 startup_reconcile 因 corrupt row 抛异常中断，后续 sessions 的 repair 也会被跳过。
- **直接证据**: `_conversation_memory_durable.py:517-537` 显示 row 存在但 decode 失败时抛 `json.JSONDecodeError` 或 `TypeError`。当前 `repair_missing_session_snapshots` 不处理 corrupt row（只处理 missing row）。
- **影响**: implementation agent 可能设计出在 startup_reconcile 中遇到 corrupt row 就中断整个 reconcile 的行为，或静默跳过。
- **建议改法和验证点**: 明确：corrupt row 在 startup_reconcile 中被捕获为 typed diagnostic（如 `RepairDiagnostic.CORRUPT_SNAPSHOT`），不中断其它 session 的 repair，记录 WARNING 日志，不自动 delete/overwrite。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

### 08-未修复-[低]-EventLog 中已有的 TOOL_FETCH_MORE_* 行数据迁移未说明
- **Plan位置**: §1 Goal / Success Signal 和 §6 Contract impact
- **问题类型**: 契约缺失
- **计划当前写法**: "不提供兼容 re-export、兼容 wrapper、兼容 decoder 分支"；"按全新 schema 起库处理"。
- **为什么有问题**: "全新 schema 起库" 意味着旧 EventLog 数据丢弃。但如果 P8 已有测试/生产数据包含 `TOOL_FETCH_MORE_REQUESTED` 等事件类型，这些行在 serializer 删除对应 decoder 后会变成不可反序列化的死数据。plan 没有说明这是可接受的（因为是 development branch 数据）还是需要 migration。
- **直接证据**: 当前分支 `migration/host-p8-5-stabilization` 是 development branch，`TOOL_FETCH_MORE_*` 只存在于 P8 测试数据中。schema 变更按全新起库处理，旧数据不需要迁移。
- **影响**: 低。development branch 数据不进入生产。但 implementation agent 应确认不保留旧数据兼容 reader。
- **建议改法和验证点**: 在 plan 中显式声明："P8.5 是 development branch 内的 schema 修正，旧 EventLog 测试数据按全新起库处理丢弃，不写兼容 reader。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

## Open Questions and Residual Risk

### Open Questions

1. **SSE partial diagnostic 的 Engine/Host 边界**（Finding 03）：需要 controller 裁决 diagnostic fact 是 Engine-owned 还是 Host-owned。这是 blocking implementation choice。
2. **BUSY reason 细化的具体枚举值**（Finding 05）：需要 controller 确认 `AttemptFencingReason.ATTEMPT_INDEX_CONFLICT` 或等价值。
3. **append_many stop condition 是否真实可触发**（Finding 06）：需要 controller 裁决是保留测试要求还是删除（如果当前代码天然保证）。

### Residual Risks

| Risk | Owner | Status |
| --- | --- | --- |
| observer claim lease / outbox / hard-gate | P15 / issue #28 | Explicitly not P8.5 |
| `InMemoryRunEventStore` 生产语义收口 | P16 interface freeze | Deferred |
| schema bootstrap 半失败治理 | P15 | Deferred |
| `LocalRunHarness` God Object 膨胀 | P9 / P16 | Deferred |
| `DurableHarnessBundle` public/internal 边界 | P16 | Deferred |
| P15 required projection enforcement | P15 | Deferred |
| `HostStorage.close()` 后台 task 生命周期 | P9 lifecycle | Deferred |

## Summary

P8.5 plan 的动机成立，核心裁决（删除具体工具名 RunEventType、fetch_more 作为普通 tool call 建模、mechanism facts 保留为通用事实）方向正确且有直接代码证据支撑。plan 的结构、non-goals、stop conditions 和 residual risk tracking 整体质量高。

主要风险集中在：
- **handoff 精度**：affected files 路径不准确（Finding 01）、SSE partial diagnostic 的 layer boundary 未裁决（Finding 03）、RunInput side store 的 transaction ownership 未定义（Finding 02）。
- **slice 粒度**：Slice 7 过粗且包含 open design choice（Finding 05）、append_many stop condition 缺乏可验证基线（Finding 06）。
- **运维边界**：corrupt snapshot 诊断表达未收敛（Finding 07）。

无 blocker 级 findings。controller 裁决 3 个 open questions 后即可 handoff implementation agent。
