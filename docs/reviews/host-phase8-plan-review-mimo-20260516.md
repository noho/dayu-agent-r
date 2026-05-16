# Host Phase 8 Plan Review - MiMo - 2026-05-16

## Gate

当前 gate：Phase 8 `Projection Core / Host Event Stream / Minimal Read Model` plan review。

Review target：`docs/host/phase8-projection-core-event-stream-plan.md`

设计真源：

- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

总控真源：

- `docs/host/implementation-control.md` Phase 8

相关 artifact：

- `docs/reviews/host-phase8-design-discussion-codex-20260516.md`
- `docs/reviews/host-phase8-design-discussion-controller-adjudication-20260516.md`

## Review Scope

本 review 覆盖 plan 的全部 14 个 section，重点攻击：

- plan 是否 code-generation-ready，implementation agent 能否直接按 plan 写代码。
- typed consumer contract 是否足够具体，无 `Any` / `object` / raw payload bag。
- projection 是否反向成为 Host governance truth。
- checkpoint advance 与 projection writes 的事务原子性是否明确。
- stream fanout 是否被限制为 non-truth wakeup。
- repair helper 是否是真实的内部 primitive，而非测试 fixture。
- 每个 slice 是否能独立通过 tests 和 pyright。
- schema 是否与 design truth 一致。

## Assumptions Tested

1. `HOST_SCHEMA_VERSION` 当前为 4，plan 要求 bump 到 5 → 已验证（`schema.py:24`）。
2. `EventLogRow` 包含 `event_sequence`、`event_id`、`event_class`、`event_type`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`occurred_at`、`payload_ref`、`payload_digest`、`payload_json` → 已验证（`event_log.py:112-156`）。
3. `payload_object()` 已存在于 `_event_payload.py`，可解析 `EventLogRow.payload_json` 为 `Mapping[str, JsonValue]` → 已验证（`_event_payload.py:359-373`）。
4. `HostTransactionRunner.run_write()` 提供 `BEGIN IMMEDIATE` 事务，operation 内所有写入在 COMMIT 时原子提交 → 已验证（`transaction.py:213-265`）。
5. `stream_run_events` 直接从 EventLog `read_events_after()` 读取，不依赖 projection → 已验证（`read_api.py:163-181`）。
6. `RunSnapshot` 已有 `terminal_result_summary`、`outbox_summary`、`event_cursor` 字段 → 已验证（`api.py:1686-1738`）。
7. `SessionSnapshot` 已有 `timeline_cursor` 字段 → 已验证（`api.py:1647-1683`）。
8. `HostCommandHandle._transaction_runner()` 返回 `HostTransactionRunner` → 已验证（`command.py:160-166`）。
9. Plan 声明的测试文件 `test_durable_schema.py`、`test_public_event_stream.py`、`test_public_run_api.py`、`test_public_session_api.py`、`test_package_exports.py`、`test_import_boundary.py`、`test_weak_typing_guard.py` 均已存在 → 已验证。
10. `EventClass` 枚举包含 `CANONICAL_FACT`、`PREVIEW`、`DIAGNOSTIC`、`PROJECTION_SIGNAL` → 已验证（`event_log.py:55-65`）。

## Findings

### P8-PR-001-未修复-低-ProjectionRunner 事务依赖注入模式未明确

- **位置**: §2.2 Host 内部契约、§4.1 文件清单、§7 P8-S1
- **问题类型**: 不可直接实施
- **当前写法**: Plan 定义了 `ProjectionConsumer` Protocol 和 `ProjectionRunner`，但未指定 `ProjectionRunner` 如何获取事务能力。
- **反例/失败场景**: Implementation agent 可能让 `ProjectionRunner` 自建 SQLite connection，绕过 `HostTransactionRunner` 的 busy retry 和 WAL 配置；或让它直接持有 `HostCommandHandle` 引入循环依赖。
- **为什么有问题**: 现有 `dispatch.py` 已通过 `self._transaction_runner` 使用 `HostTransactionRunner`，`ProjectionRunner` 应遵循同一模式。Plan 未指定这一点，implementation agent 需要自行推断。
- **直接证据**: `command.py:160-166` 暴露 `_transaction_runner()`；`dispatch.py:59` 持有 `HostTransactionRunner` 引用。Plan §2.2 只说"第一版必须复用现有 `HostTransactionRunner`"，未说明注入方式。
- **影响**: 低。Implementation agent 可从现有代码推断正确模式，但缺少显式指导可能导致首次实现偏差。
- **建议改法和验证点**: 在 §2.2 或 §7 P8-S1 中补充："`ProjectionRunner` 构造时接收 `HostTransactionRunner` 实例，由 `HostCommandHandle` 组装时注入。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### P8-PR-002-未修复-中-RunResult terminal event 冲突检测逻辑不够具体

- **位置**: §3.3 Minimal RunResult 表、§5 Checkpoint / 幂等 / 失败不变量第 4 条
- **问题类型**: 契约缺失
- **当前写法**: "Upsert by `run_id` only when `terminal_event_id` and `terminal_event_sequence` match existing truth or supersede absent row. Different terminal event for same `run_id` indicates EventLog / projection invariant violation; consumer must raise projection error and not advance checkpoint."
- **反例/失败场景**: Implementation agent 可能使用 `INSERT OR REPLACE` 或 `INSERT ... ON CONFLICT(run_id) DO UPDATE SET ...`，这会静默覆盖已有的不同 `terminal_event_id`，违反"不同终态事件 = invariant violation"约束。`terminal_event_id` 的 UNIQUE 约束只能防止两个不同 run 指向同一 terminal event，不能防止同一 run 被覆盖为不同 terminal event。
- **为什么有问题**: 这是 RunResult 幂等性的核心不变量。如果 implementation 静默覆盖，会导致 projection 产出与 EventLog truth 不一致，且 checkpoint 会推进到错误位置。
- **直接证据**: Plan §3.3 "Different terminal event for same `run_id` indicates EventLog / projection invariant violation"；§5 第 4 条 "consumer apply 成功但 checkpoint 写失败时，后续 replay 会重复调用 consumer；consumer 必须依赖 `event_id` / terminal identity upsert 保证幂等"。
- **影响**: 中。Implementation agent 可能实现错误的 upsert 逻辑，导致 projection 数据静默损坏。
- **建议改法和验证点**: 在 §3.3 幂等段落补充具体 consumer 逻辑："consumer 先 SELECT 已有 row by `run_id`；若存在且 `terminal_event_id` 匹配，返回 DUPLICATE；若存在但 `terminal_event_id` 不匹配，raise projection error；若不存在，INSERT 新 row。" 并在测试中增加"Conflicting terminal event for same Run -> projection failure, checkpoint not advanced"的显式断言。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P8-PR-003-未修复-中-repair helper 事务原子性与 batch replay 边界未明确

- **位置**: §6 Minimal Rebuild / Repair 路径
- **问题类型**: 状态机漏洞
- **当前写法**: "`reset_checkpoint=True` 时，在一个 transaction 内删除 `host_run_results`、`host_session_timeline_items`、minimal read model consumer checkpoint 与 failure row，然后从 EventLog cursor 0 replay。" 签名包含 `batch_size: int`。
- **反例/失败场景**: 如果"在一个 transaction 内"意味着删除和全部 replay 都在同一事务中，大 EventLog 会长时间持有写锁，阻塞 EventLog append 和 command path。如果 `batch_size` 暗示分批提交，那么"在一个 transaction 内"的描述与分批语义矛盾。Implementation agent 可能实现为：删除在一个事务、replay 分多个事务，导致中途失败时 projection 处于部分重建状态——但 checkpoint 已重置为 0，下次 replay 会重复已成功的部分。
- **为什么有问题**: `batch_size` 参数暗示分批处理，但 plan 的事务描述暗示原子操作。两者语义冲突时 implementation agent 需要自行决定，可能产生不一致的 repair 行为。
- **直接证据**: Plan §6 "在一个 transaction 内删除...然后从 EventLog cursor 0 replay" vs 签名 `batch_size: int`。§10 残余风险 "checkpoint + projection writes share one SQLite transaction, so long consumers can hold write locks"。
- **影响**: 中。Repair 在大 EventLog 下可能阻塞 command path，或在分批模式下中途失败导致需要再次 repair。
- **建议改法和验证点**: 明确 repair 语义为两阶段：(1) `reset_checkpoint=True` 时，一个事务内删除所有 projection rows + checkpoint + failure row（快速，短锁）；(2) 从 cursor 0 分批 replay，每批 `batch_size` 个事件，每批一个事务（checkpoint 在每批末尾推进）。中途失败时 checkpoint 记录已完成位置，再次调用 repair 可从断点继续。`reset_checkpoint=False` 直接从当前 checkpoint 分批 catch up。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### P8-PR-004-未修复-低-P8-S2 fanout wakeup 端口形态未指定

- **位置**: §2.4 Stream Fanout 非真源边界、§4.1 `command.py` 和 `dispatch.py` 允许变更、§7 P8-S2
- **问题类型**: 不可直接实施
- **当前写法**: Plan §2.4 "Phase 8 可以实现最小 wakeup / fanout 基础"，§4.1 "仅允许 after-commit wakeup 调用 projection runner 的 wakeup port"，§7 P8-S2 "If adding a fanout / wakeup abstraction, keep it internal and non-truth"。
- **反例/失败场景**: Implementation agent 可能跳过 fanout（plan 用的是"可以"而非"必须"），导致 Phase 8 没有 wakeup 机制；或实现一个过重的 pub-sub 系统。
- **为什么有问题**: Fanout 在 plan 中是可选的（"可以实现"），但 after-commit wakeup 是 projection runner 触发的关键路径。如果 implementation agent 不实现 wakeup，projection 只能通过 repair 或手动调用运行，失去实时性。
- **直接证据**: Plan §4.1 `dispatch.py` "仅允许 after-commit wakeup 调用 projection runner 的 wakeup port"；§7 P8-S2 "If adding a fanout / wakeup abstraction"。
- **影响**: 低。Wakeup 是优化而非 correctness 路径（plan 明确了这一点），缺失 wakeup 只导致 projection lag 增大。
- **建议改法和验证点**: 明确 wakeup 端口为可选的 `Callable[[], None]` 或 `asyncio.Event`，由 `ProjectionRunner` 构造时注入。P8-S2 的完成信号可以改为"after-commit wakeup hook 已接入或显式声明为 noop"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。所有 finding 已给出具体修复建议。

## Residual Risks

1. **Generic runner drift toward untyped event bus**: Plan §10 已识别并由 §12 blocking criteria 控制。风险等级：低。
2. **Long consumer holding write lock**: Plan §10 已识别。Phase 8 的 minimal read model consumer 工作量小，不会长时间持锁；重负载 sinks 后置到 Phase 13。风险等级：低。
3. **Stream fanout hidden truth**: Plan §10 已识别并由 P8-S2 tests 控制。风险等级：低。
4. **Repair helper only in tests**: Plan §10 已识别并由 §6 要求 production internal helper。风险等级：低。
5. **Schema version skew**: Plan §3 要求 fresh schema bump 到 5，且要求 implementation agent 在发现版本变化时停止。风险等级：低，但依赖 implementation agent 遵守停止条件。

## Residual Items / Deferred Tracking

- Phase 9 owner：Conversation Memory projection，复用 Phase 8 consumer / checkpoint framework。
- Phase 11 owner：Recovery scan，只读 Host durable truth，不读 projection truth。
- Phase 13 owner：Audit / Tool Trace / Outbox concrete sinks。
- Phase 15 owner：production hardening、admin rebuild CLI。
- Service / UI owner：channel delivery、seen cursor 存储。

## Verdict

**PASS-with-risks**。

Plan 整体 code-generation-ready，设计真源与总控真源覆盖充分，typed consumer contract、checkpoint 语义、EventLog cursor truth、read model rebuild、non-goals 和 slice 边界均已明确固定。4 个 findings 均为中低严重程度，不构成 blocking：

- P8-PR-001（低）：事务依赖注入模式可从现有代码推断。
- P8-PR-002（中）：terminal event 冲突检测需要更具体的 consumer 逻辑描述，但 plan 已声明不变量。
- P8-PR-003（中）：repair helper 的事务语义与 batch_size 需要澄清，但 plan 已提供足够的约束框架。
- P8-PR-004（低）：wakeup 端口是可选优化，不影响 correctness。

Plan 可以进入 implementation，建议 controller 裁决是否要求 implementation agent 在开始前先 fix P8-PR-002 和 P8-PR-003，或在 implementation 过程中自行处理。
