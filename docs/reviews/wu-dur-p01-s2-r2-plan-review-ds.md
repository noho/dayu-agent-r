# WU-DUR-P01-S2-R2 runner-call event link plan review

## Review metadata

| field | value |
|---|---|
| reviewed target | `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md` |
| review scope | 全 plan（目标/非目标/动机/root cause/设计契约变更/实施切片/stop conditions/风险） |
| review date | 2026-06-05 |
| reviewer | planreview (adversarial) |
| output path | `docs/reviews/wu-dur-p01-s2-r2-plan-review-ds.md` |

## Assumptions tested

| # | assumption | evidence source | result |
|---|-----------|----------------|--------|
| A1 | root cause 是缺少追加式 manifest-to-iteration link，不是缺少 Engine 事件 | `dayu/host/run_input.py:3781-3782`（ordinary manifest `iteration_id=None`）；`dayu/host/engine_ingest.py:4984`（`payload_iteration_id is None and iteration_index == 0` fallback） | **confirmed** |
| A2 | `iteration_index == 0` 猜测在 continuation reset、retry 下可能误匹配 | `dayu/host/engine_ingest.py:4984`（纯 index 匹配，无 attempt-level prior-observation guard） | **confirmed** |
| A3 | Engine 已发出 `ITERATION_STARTED`，Host ingest 已处理该事件 | `dayu/engine/agent.py`（Engine 发出）；`dayu/host/engine_ingest.py:939-945`（Host ingest 入径） | **confirmed** |
| A4 | ordinary manifest 在 Engine dispatch 前写入，先于 `ITERATION_STARTED` | `dayu/host/run_input.py:1924-1930`（build 内调用 `record_runner_call_manifest`） | **confirmed** |
| A5 | 追加式 link event 不破坏现有 EventLog schema / projection | `docs/host/design.md:1526`（`RUNNER_CALL_INPUT_ASSEMBLED` 无状态副作用）；现有 Tool Trace 只消费 `RUNNER_CALL_INPUT_ASSEMBLED` | **partially confirmed** — 需要新 event type 进入 EventLog 类型表，但 plan 在 Slice 0 覆盖此变更 |
| A6 | continuation limited-signal manifest 已自带 `iteration_id`，不需要 link event | `dayu/host/engine_ingest.py:4474-4475`（`iteration_id=data.iteration_id`）；test `test_iteration_started_writes_limited_runner_call_manifest_for_continuation:2251` | **confirmed** |

## Findings

### F1-阻断-高-`_has_prior_iteration_observation` 契约未指定 durable 查询，implementation agent 可能用错信号

- **位置**: plan 第 112-113 行 link resolution contract step 3，"候选数为 0 且当前 attempt/execution 已有 earlier accepted iteration link 或 earlier accepted iteration preview"
- **问题类型**: 契约缺失
- **当前写法**: plan 声明需要 `_has_prior_iteration_observation(...)` helper（Slice 1 动作列表），但没有定义什么 durable 记录算 "prior iteration observation"。是检查该 attempt/execution 下是否存在任何 `ITERATION_STARTED` preview event？还是检查是否存在 `RUNNER_CALL_INPUT_ITERATION_LINKED` event？还是检查是否存在 `RUNNER_CALL_INPUT_ASSEMBLED`（continuation limited-signal manifest）？
- **反例/失败场景**: implementation agent 可能用 `SELECT COUNT(*) FROM event_log WHERE attempt_id=? AND event_type='ITERATION_STARTED'` 判断 prior observation。但若第一个 `ITERATION_STARTED` 的 preview event 被事务回滚或仅 append preview 失败，这个 query 会错误地认为 prior observation 不存在，导致第一个到达的 `ITERATION_STARTED` 被当作 "first iteration" 处理。更严重的是，如果 agent 用 `RUNNER_CALL_INPUT_ASSEMBLED` 计数做 prior observation（因为 continuation 也会写 limited-signal manifest），则可能在普通首轮 manifest 存在时（已有 1 条 `RUNNER_CALL_INPUT_ASSEMBLED`）被误判为 "已有 prior observation"，从而跳过 link resolution 直接走 continuation path。
- **为什么有问题**: "prior iteration observation" 是 fail-closed vs. continuation 的关键分支判断。用错查询会导致：要么把 continuation 当 first iteration 误 reject（过于严格）；要么把 first iteration 当 continuation 走 limited-signal path，掩盖 ordinary prepared manifest 缺失（过于宽松，与 plan fail-closed 目标冲突）。
- **直接证据**:
  - plan line 112-113 只描述语义，没有 durable query 规格
  - `dayu/host/engine_ingest.py:2348-2355` — 当前 `_find_runner_call_manifest_event` 用 iteration_id/iteration_index 匹配，没有 prior-observation guard
  - `dayu/host/engine_ingest.py:2380-2411` — `_append_limited_runner_call_manifest_event` 对当前所有 "未找到 manifest" 情况统一写 limited-signal
- **影响**: implementation agent 跑偏 — 用错误的 durable 信号实现 prior-observation 判断，导致 fail-closed 条件不可靠
- **建议改法和验证点**:
  1. 在 plan 的 link resolution contract 中明确定义：prior iteration observation = 当前 attempt/execution 下存在 `RUNNER_CALL_INPUT_ITERATION_LINKED` event（link 是最可靠信号）**且/或** 存在 `ITERATION_STARTED` preview event（preview 是已通过 link resolution 的 durable 证据）
  2. 排除只依赖 `RUNNER_CALL_INPUT_ASSEMBLED` 计数（因为 ordinary manifest 也在同一 event type 下，会制造假阳性）
  3. 如果实现期发现无法区分 link 存在 vs. preview 存在（例如两者在同 transaction 内），必须在 design gate 回退，把 prior-observation 查询定义为对 `RUNNER_CALL_INPUT_ITERATION_LINKED` 的 durable 查找
- **修复风险**: 低 — 只需在 plan 中追加 durable query 语义，不改变整体方案
- **严重程度**: 高

### F2-阻断-中-plan 未定义 "ordinary dispatch kind" 的准确闭集，filter 可能漏掉 lawful manifest

- **位置**: plan 第 106 行 link resolution contract step 3，"`runner_call_kind` 为 ordinary dispatch kind"
- **问题类型**: 契约缺失
- **当前写法**: plan 说只允许 `RUNNER_CALL_INPUT_ASSEMBLED` 的 unlinked manifest 中 `runner_call_kind` 为 "ordinary dispatch kind" 的作为候选，但没有列出具体哪些 kind 值属于 ordinary dispatch
- **反例/失败场景**: 如果 implementation agent 把 "ordinary dispatch kind" 理解为仅 `initial_user_dispatch`，则 `followup_user_dispatch` 和 `post_compaction_dispatch` 的 ordinary manifest 会被排除，导致 second-turn user input 或 post-compaction dispatch 场景下 manifest-to-iteration link 缺失。反过来，如果 agent 把 `compactor_proposal` 也当作 ordinary（因为这个 manifest 也是 RunInputBuilder 写的），则会把 compactor 的内部调用误 linked 到 user Run 的 iteration
- **为什么有问题**: `runner_call_kind` 当前有 5 个值（`initial_user_dispatch`, `followup_user_dispatch`, `tool_result_continuation`, `post_compaction_dispatch`, `compactor_proposal`），其中前 3 个（非 continuation 非 compactor）由 RunInputBuilder 写入，`iteration_id` 均为 `None`。plan 用 "ordinary dispatch kind" 做 filter 但没有闭集定义，implementation agent 需要猜测
- **直接证据**:
  - `dayu/host/run_input.py:4370-4385` — `_runner_call_kind_and_trigger` 返回的 kind 包括 `initial_user_dispatch`, `followup_user_dispatch`, `post_compaction_dispatch`
  - `dayu/host/run_input.py:3781` — 所有 ordinary manifest 的 `iteration_id` 均为 `None`
  - plan line 106 只写 "ordinary dispatch kind" 未给闭集
  - `docs/host/design.md:2678-2686` — Closed `RunnerCallKind` enum 定义了全部 5 个值
- **影响**: implementation agent 可能用错 filter 闭集，导致特定 runner_call_kind 的 ordinary manifest 无法被 link
- **建议改法和验证点**:
  1. 在 plan 中把 "ordinary dispatch kind" 替换为明确的闭集：`runner_call_kind in ("initial_user_dispatch", "followup_user_dispatch", "post_compaction_dispatch")`，或更直接地依赖 `iteration_id is None` + `validation_status="complete"`（这两个条件已经足够区分 ordinary manifest 与 continuation/compactor manifest）
  2. 实际上，"ordinary dispatch kind" filter 可能是冗余的——`iteration_id is None` + `validation_status="complete"` 已经精确标识 ordinary prepared manifest，因为：
     - ordinary manifest: `iteration_id=None`, `validation_status="complete"`
     - continuation limited-signal manifest: `iteration_id`=Engine 值, `validation_status="limited_signal"`
     - compactor manifest: `compactor_identity` 非 null, `runner_call_kind="compactor_proposal"`
  3. 验证：所有 `initial_user_dispatch`/`followup_user_dispatch`/`post_compaction_dispatch` 的 ordinary manifest 都能被 link
- **修复风险**: 低 — 将模糊描述替换为闭集，或简化为仅依赖已有 durable 字段
- **严重程度**: 中

### F3-阻断-中-link resolution 缺少对"同一 transaction 内 ordinary manifest 尚未写入"的 timing 约束

- **位置**: plan 第 100-122 行 link resolution contract
- **问题类型**: 并发恢复风险
- **当前写法**: plan 假设 `EngineEventIngestor` 处理 `ITERATION_STARTED` 时 ordinary manifest 已经由 `RunInputBuilder` 写入。link resolution 在 candidate=0 且无 prior observation 时直接 rejected
- **反例/失败场景**: `RunInputBuilder` 写入 ordinary manifest 与 `EngineEventIngestor` 处理 `ITERATION_STARTED` 在不同的 Host transaction 中执行。如果 Engine 启动极快，`ITERATION_STARTED` 到达时 `RunInputBuilder.record_runner_call_manifest()` 的 SQLite transaction 尚未提交（或 Worker dispatch 的 transaction 尚未 committed），此时 link resolution 会看到 candidate=0 且无 prior observation，直接 rejected + stop_worker_stream=True，导致合法的 ordinary Run 因 timing 问题失败
- **为什么有问题**: plan 的 link resolution contract 没有考虑 ordinary manifest 写入与 Engine ingest 之间的并发时序。在当前代码中这不是问题——因为 `_append_iteration_started_events` 会 fallback 到写 limited-signal manifest（而非 reject）。plan 把 missing manifest 从 limited-signal 升级为 rejected，但没有新增 timing guard
- **直接证据**:
  - `dayu/host/run_input.py:1925-1930` — manifest 在 `build()` 方法内部通过 `record_runner_call_manifest` 写入，该写入在 Attempt dispatch 之前还是之后取决于 composition root 的 transaction 边界设计
  - `dayu/host/engine_ingest.py:2333-2363` — 当前代码在 manifest 缺失时写 limited-signal，不 reject
  - plan 未提及 Host dispatch transaction 与 Engine ingest transaction 之间的 ordering guarantee
- **影响**: 在 Engine 启动极快或 Worker 与 Host 运行在不同进程/线程的场景下，合法的 initial runner call 可能因 manifest 尚未 durable 而被误 reject
- **建议改法和验证点**:
  1. plan 应明确：ordinary manifest 的写入与 Attempt dispatch 是否在同一 Host transaction 内。若在同一 transaction，则 Engine 在 dispatch 成功前不会收到 `ITERATION_STARTED`（因为 dispatch 由 Host 发起），时序保证成立
  2. 若不在同一 transaction，plan 需增加 retry / grace window 或确认 RunInputBuilder 的 manifest write 一定先于 `ITERATION_STARTED` 到达
  3. 更安全的做法：在 plan 的 stop condition 中增加一条——若发现 ordinary manifest 写入与 `ITERATION_STARTED` ingest 无 durable ordering guarantee，必须回到 design gate
- **修复风险**: 中 — 需要确认现有 dispatch transaction 边界，可能需要 design 澄清
- **严重程度**: 中

### F4-非阻断-中-`_find_unlinked_prepared_runner_call_manifest_events` 的 anti-join 查询设计未给出

- **位置**: plan 第 106-107 行（unlinked manifest 查找语义）与 Slice 1 动作列表
- **问题类型**: 切片过粗
- **当前写法**: plan 在 resolution contract step 3 中描述 "没有被任一 link event 引用" 的筛选条件，Slice 1 动作列表中列出 `_find_unlinked_prepared_runner_call_manifest_events(...)` helper，但没有任何 SQL 或 durable query 设计
- **反例/失败场景**: implementation agent 需要实现 anti-join：从 `event_log` 表中查出 `RUNNER_CALL_INPUT_ASSEMBLED` events，再排除那些被 `RUNNER_CALL_INPUT_ITERATION_LINKED` event 的 `manifest_event_id` 字段引用的。如果 agent 用两次查询 + Python 端做差集，可能漏掉同 transaction 内刚写入的 link event。如果用 NOT EXISTS 子查询，需要确保 SQLite 查询计划不退化
- **为什么有问题**: anti-join 是 plan 中唯一新增的复杂查询模式，且 `RUNNER_CALL_INPUT_ITERATION_LINKED` 的 hot payload 中 `manifest_event_id` 是 JSON 字段，SQLite 的 JSON 字段无法直接做高效索引。如果每次 link resolution 都要全表扫描 link events + 解析 JSON，在 Run 事件较多时性能劣化
- **直接证据**:
  - `dayu/host/engine_ingest.py:4935-4944` — 当前 `_find_runner_call_manifest_event` 用简单 `WHERE event_type = ?` 扫描，没有 anti-join
  - `dayu/host/run_input.py:3658-3667` — `_find_existing_runner_call_manifest_event` 同样用简单扫描
  - plan 只提到 stop condition "发现 current durable store / EventLog API 无法追加 RUNNER_CALL_INPUT_ITERATION_LINKED 而不破坏 schema" 时停止，但未对 finder helper 的查询复杂度设 stop condition
- **影响**: implementation agent 可能实现低效 anti-join，或为了避免复杂度而在 Python 端做差集（引入 TOCTOU 风险）
- **建议改法和验证点**:
  1. plan 应给出 anti-join 的推荐查询策略：使用 `manifest_event_id` 在 hot payload JSON 中的提取（若 SQLite 支持 `json_extract`），或使用专用索引列
  2. 更小的替代方案：在 link event 的 hot payload 中把 `manifest_event_id` 提升为 `event_log` 的独立 column（如果 schema 允许），或增加一个 dedicated state column 记录 "已被 link 的 manifest event id"
  3. 若当前 durable store 不支持高效 anti-join 且不能改 schema，应在 plan 中承认这个约束并给出 O(n) scan 的可接受性论证
- **修复风险**: 低 — 只需补充查询设计，不改变 plan 方案
- **严重程度**: 中

### F5-非阻断-低-新增 diagnostic reason 值未与现有 `RunnerCallReconstructionDiagnosticReason` 枚举对齐

- **位置**: plan 第 89-104 行（diagnostic reason 闭集定义）
- **问题类型**: 契约缺失
- **当前写法**: plan 列出 link event 的 diagnostic reason 值包括 `message_count_mismatch`, `role_sequence_digest_mismatch`, `missing_runner_call_manifest`, `payload_digest_mismatch`, `ambiguous_runner_call_manifest`。同时 `ENGINE_EVENT_REJECTED` 的 reason 包括 `runner_call_iteration_link_conflict`, `ambiguous_runner_call_manifest`, `runner_call_manifest_mismatch`
- **反例/失败场景**: implementation agent 在 `RunnerCallReconstructionDiagnosticReason` 中新增 reason 值时，可能与现有 Tool Trace consumer 的类型检查冲突。例如，若 `runner_call_manifest_mismatch` 被加到 `RunnerCallReconstructionDiagnosticReason` 但 Tool Trace 的 `_runner_call_signal_from_hot_row` 没有对应处理路径，会导致 HostDurableError
- **为什么有问题**: plan 提出了新的 reason 值，但没有说明它们应该进入哪个枚举、是否与现有 `RunnerCallReconstructionDiagnosticReason`（`dayu/host/durable/tool_trace.py`）对齐，还是创建一个新的 link-specific diagnostic enum
- **直接证据**:
  - `dayu/host/engine_ingest.py:257-260` — 现有 `_RUNNER_CALL_MANIFEST_REASON_*` 常量：`missing_runner_call_manifest`, `missing_projection_artifact`, `message_count_mismatch`, `role_sequence_digest_mismatch`
  - `dayu/host/durable/tool_trace.py` — `RunnerCallReconstructionDiagnosticReason` type alias
  - plan 提到 "若需要新增 diagnostic reason，例如 `ambiguous_runner_call_manifest`、`runner_call_iteration_link_conflict`、`runner_call_manifest_mismatch`，先在设计真源写闭集定义"（Slice 0 动作），但没有说明哪个真源（design.md 还是 tool_trace.py 的 enum）
- **影响**: implementation agent 可能把 reason 值放在错误的位置，或与现有 Tool Trace diagnostic 消费者产生类型冲突
- **建议改法和验证点**:
  1. 明确区分两类 reason：
     - Link event 自身的 diagnostic reason（如 `message_count_mismatch`, `role_sequence_digest_mismatch`）——可复用现有 `_RUNNER_CALL_MANIFEST_REASON_*` 常量
     - `ENGINE_EVENT_REJECTED` 的 reason（如 `runner_call_iteration_link_conflict`, `ambiguous_runner_call_manifest`）——这是 Engine ingest rejected reason 枚举的扩展，不属于 runner-call diagnostic
  2. 在 Slice 0 中明确这两个枚举的位置、文件名和闭集定义
- **修复风险**: 低
- **严重程度**: 低

### F6-非阻断-低-Slice 2 测试夹具复杂度过高，continuation reset 测试缺少 seeding 路径描述

- **位置**: plan 第 207-223 行 Slice 2 测试列表
- **问题类型**: 测试缺口
- **当前写法**: plan 列出了 8 个测试场景，包括 "initial link 已存在后，continuation `iteration_index=0`：不得匹配已 linked ordinary manifest"。但没有说明如何 seed durable store 来构造这个测试场景
- **反例/失败场景**: 要测试 continuation `iteration_index=0` reset，需要先 seed：
  1. 一条 ordinary `RUNNER_CALL_INPUT_ASSEMBLED`（iteration_id=None）
  2. 一条 `RUNNER_CALL_INPUT_ITERATION_LINKED`（link 该 ordinary manifest 到 iteration 0）
  3. 然后构造新的 `ITERATION_STARTED` candidate（iteration_index=0）
  implementation agent 需要知道如何直接在 test transaction 中写入 link event（因为 link event 是 Slice 1 新增的 event type，测试也需要能 append 它）。如果 test fixture 没有 link event 的 writer helper，测试无法构造"已有 link"的前置状态
- **为什么有问题**: 这个测试是 plan 的核心正确性证明——如果没有它，无法验证 continuation reset 不会误匹配。但测试的 seeding 路径依赖 Slice 1 的实现产物（link event writer），plan 没有给出测试夹具的契约
- **直接证据**:
  - `tests/host/test_engine_ingest_mapping.py:2199-2277` — 现有 continuation 测试只需 seed 基本 Run/Attempt，不需要 seed manifest（因为当前 continuation 总是写 limited-signal）
  - plan 的 Slice 2 依赖 Slice 1 的 link event 写入能力来构造 fixture
- **影响**: implementation agent 可能需要先实现 Slice 1 的 link writer，再回头写 Slice 2 的测试，或者用 raw SQL INSERT 绕过类型安全插入测试数据（引入测试脆弱性）
- **建议改法和验证点**:
  1. plan 应明确：Slice 2 可能需要在 Slice 1 完成后实现，因为测试夹具需要 link event writer
  2. 或者 plan 应给出测试夹具的最小 seeding 策略（例如复用 `_append_runner_call_iteration_link_event` helper 或使用 dedicated test helper）
  3. 如确有 slice 间依赖，应在 plan 的 slice 切分中显式声明
- **修复风险**: 低
- **严重程度**: 低

### F7-非阻断-低-plan 的 `_preview_payload` 改造路径有双重查询风险

- **位置**: plan 第 115-126 行 preview payload correlation + Slice 1 动作
- **问题类型**: 过度耦合
- **当前写法**: plan 要求 `_preview_payload` 的 `runner_call_manifest_validation` "使用 link resolution result，不再重新扫描并做 index fallback"。Slice 1 动作说 `_preview_payload` 使用 link resolution result
- **反例/失败场景**: 当前代码中 `_preview_payload`（line 4357-4385）在构造 preview payload 时调用 `_runner_call_manifest_validation_summary`，该函数内部调用 `_find_runner_call_manifest_event` 做独立查询（line 4851-4858）。如果 implementation agent 简单地在 `_preview_payload` 中再执行一次 link resolution，会产生双重查询。如果 agent 改为从 `_append_iteration_started_events` 的返回值传递 resolution result 到 `_preview_payload`，则需要修改两个函数的签名来传递 intermediate result
- **为什么有问题**: plan 没有指定 resolution result 如何在 `_append_iteration_started_events` 和 `_preview_payload` 之间传递。`_append_iteration_started_events` 返回 `tuple[EventLogRow, ...]`，`_preview_payload` 独立调用。传递 resolution result 需要改变至少一个函数的签名或引入内部状态
- **直接证据**:
  - `dayu/host/engine_ingest.py:2333-2363` — `_append_iteration_started_events` 返回 appended rows
  - `dayu/host/engine_ingest.py:4357-4385` — `_preview_payload` 独立接收 `transaction, context`，内部调用 `_runner_call_manifest_validation_summary`
  - `dayu/host/engine_ingest.py:942-945` — ingest 方法把 `_append_iteration_started_events` 结果传给 `_event_rows_result`，不传给 `_preview_payload`
- **影响**: implementation agent 可能选择简单路径（在 preview payload 中再做一次查询）而非正确路径（传递 result），导致双重扫描
- **建议改法和验证点**:
  1. plan 应明确 resolution result 的传递机制：是在 `_event_rows_result` 类型的 payload 中携带 link event id / validation summary，还是修改函数签名使 `_preview_payload` 接收 resolution result
  2. 如果传递机制过于复杂，可以在 plan 中允许 preview payload 做一次轻量查询（只查刚写入的 link event），只要不重复 index fallback 即可
- **修复风险**: 低
- **严重程度**: 低

### F8-非阻断-低-plan 未覆盖 "link event 写入后、preview 写入前" 的事务原子性问题

- **位置**: plan 第 108-114 行 link resolution contract step 2-3
- **问题类型**: 并发恢复风险
- **当前写法**: plan 的 resolution 结果包括 "append `RUNNER_CALL_INPUT_ITERATION_LINKED complete`，再 append `ITERATION_STARTED` preview"。这两个 append 在同一个 `_append_iteration_started_events` 调用中完成
- **反例/失败场景**: 如果 link event append 成功但 preview append 失败（例如同事务内的 constraint violation），事务回滚后 link event 也不存在（因为同事务）。这是正确的。但如果未来的代码演进把 link event 和 preview 拆到不同事务，就会出现 link 存在但 preview 缺失的中间状态。plan 没有把这个 "必须同事务" 的约束写入 stop condition 或风险
- **为什么有问题**: 当前 `_append_iteration_started_events` 在同一个 `HostTransaction` 中执行所有 append（line 2347-2363），事务原子性由 SQLite 保证。plan 的 stop condition 没有覆盖 "link event 与 preview 必须同事务" 的约束
- **直接证据**:
  - `dayu/host/engine_ingest.py:2333-2363` — 当前 append 在同一 transaction 参数内
  - plan line 108-114 — 提到 "再 append" 但未声明事务原子性要求
  - plan stop conditions 未覆盖分事务风险
- **影响**: 低（当前实现很可能自然保持同事务），但作为 stop condition 的完整性 gap 值得指出
- **建议改法和验证点**: 在 stop condition 中增加一条：link event 与其对应的 preview / rejected diagnostic 必须在同一 Host transaction 中 append
- **修复风险**: 低
- **严重程度**: 低

## Architecture boundary review

plan 的新增 `RUNNER_CALL_INPUT_ITERATION_LINKED` event 是 Host-owned reconstruction fact，定位为 canonical fact，无 Run/Attempt 状态副作用。不要求 Engine 反向依赖 Host，不修改 `RunInputBuilder` public contract，不改变 `AgentRunRequest` 形状。符合 `docs/host/design.md` 第 2 节分层边界约束。

一个次要注意点：link event 在 EventLog 类型表中需要新的 row（参考 `docs/host/design.md:1495` 的 EventLog 类型注册表），plan 在 Slice 0 覆盖了此变更。link event 的 audit/trace 列归属需要在 design sync 中明确（当前 plan 非目标声明不参与 lifecycle/recovery/memory/dispatch，这与 `RUNNER_CALL_INPUT_ASSEMBLED` 的定位一致）。

## Best-practice review

- append-only link fact 而非 mutation old manifest：符合 durable truth 最佳实践
- fail-closed on missing/mismatch/ambiguous：符合安全默认原则
- 通过 refs/digests 关联而非共享可变状态：符合 Event sourcing 模式
- link event id 由业务字段派生实现幂等：符合 idempotency key 模式

一个偏离：plan 的 `_find_unlinked_prepared_runner_call_manifest_events` 需要 anti-join 查询，在当前 SQLite + JSON hot payload 的存储模型下，anti-join on JSON field 不是最优查询模式。这不如"把 link status 写入 manifest event 的索引列"那样直接。但 plan 的非目标明确排除了"回写已写入的 manifest body / payload digest"，因此 anti-join 是为保持 append-only 的权衡。

## Optimal-solution review

plan 的方案在以下备选方案中是最小且最安全的：

| 备选 | 问题 |
|---|---|
| Engine 携带 Host manifest id | Engine 需要理解 Host 概念，违反分层边界 |
| 回写 ordinary manifest 的 `iteration_id` | mutation old truth，违反 durable truth |
| preview-only link（不写独立 event） | 不可审计，link 事实只存在于 preview payload 中，不是 canonical fact |
| 继续用 `iteration_index == 0` 猜测 + 加测试 | 仍然依赖 Engine 内部语义，不是 durable identity |

plan 选择独立 link event 是最符合现有架构方向（append-only, canonical fact, refs+digests）的方案。

## Overengineering review

plan 没有引入通用 correlation framework、event link engine、builder pattern 或 abstraction layer。新增的 helpers（`_find_runner_call_iteration_link_event`, `_find_unlinked_prepared_runner_call_manifest_events` 等 6 个）是模块级私有函数，符合现有 `engine_ingest.py` 的 helper pattern。没有过度设计。

## Overcoupling review

plan 保持了 prepared manifest（RunInputBuilder owner）、Engine preview（EngineEventIngestor owner）、Tool Trace（projection owner）的独立 ownership。link event 只通过 `manifest_event_id` / `manifest_payload_ref` / `manifest_digest` refs 连接，不共享可变状态。Tool Trace 集成是可选的（最小实现不改变现有 projection），不强制消费者升级。

唯一的耦合点：`_preview_payload` 需要 link resolution result 来构造 `runner_call_manifest_validation` summary。见 Finding F7。

## Open questions

1. **OQ1**: 普通首轮 `ITERATION_STARTED` 的 preview event 中 `runner_call_manifest_validation` 字段，当前返回的是 `_runner_call_manifest_validation_summary` 的结果（含 manifest_event_id, manifest_payload_ref, manifest_digest）。link event 写入后，preview 的 validation summary 是否还需要携带这些 manifest ref fields？还是改为携带 link event 的 ref？plan 说 "成功 link 时 preview payload 增加 `runner_call_iteration_link_event_id` 等字段"，但同时 `runner_call_manifest_validation` summary 也应该更新。这两者的关系需要在 implementation 时明确。

2. **OQ2**: 如果 Engine 在同一个 attempt/execution 内发送了两次 `iteration_index=0` 的 `ITERATION_STARTED`（Engine bug 或 retry 导致），plan 的 resolution：
   - 第一次：candidate=1（找到 unlinked ordinary manifest）→ link created
   - 第二次：candidate=0（ordinary manifest 已被 link），且有 prior observation（第一次的 link）→ continuation limited-signal → 写入一条新的 `RUNNER_CALL_INPUT_ASSEMBLED`（limited-signal, iteration_index=0）和 preview
   这是否合理？第二次 "iteration_index=0" 的 continuation limited-signal manifest 的 `runner_call_index` 会递增，manifest body 的 `runner_call_kind` 会是 `tool_result_continuation`，这可能不是 Engine 的真实意图。这个场景概率低但值得在 design sync 中标注为 "Engine contract violation, accepted as limited-signal continuation" 的明确裁决。

3. **OQ3**: 当 `ENGINE_EVENT_REJECTED` 因 `runner_call_iteration_link_conflict` 被 append 且 `stop_worker_stream=True` 时，Run/Attempt 的状态迁移是什么？plan 没有说明 rejected 后的 Host 状态机动作。当前代码中 `_append_rejected_diagnostic`（line 954-959）在 `stop_worker_stream=True` 时不改变 Run/Attempt 状态（只 append diagnostic event）。plan 应确认 `runner_call_iteration_link_conflict` rejected 后的状态迁移与现有 rejected diagnostic 一致。

## Residual risks

| risk | tracking | mitigation |
|---|---|---|
| Engine 发送双重 `iteration_index=0` `ITERATION_STARTED` | `WU-DUR-P01-S2-R2` 实施后作为 known edge case 记录，或新建 deferred risk | continuation limited-signal 路径接受该信号，不 crash；Tool Trace 会有一条意外 continuation signal |
| anti-join 查询在大 EventLog 下的性能 | `WU-DUR-P01-S2-R2` 实施后监控，若 `_find_unlinked_prepared_runner_call_manifest_events` 扫描行数随 Run 数线性增长 | 每个 attempt/execution 下的 ordinary manifest 通常为 1，link event 也为 1；查询范围按 run_id 过滤，行数受单 Run 事件总数限制 |
| Tool Trace consumer 未升级读取 link event 导致 analysis gap | deferred to Tool Trace consumer work unit | plan 最小实现不改变 Tool Trace；`RUNNER_CALL_INPUT_ASSEMBLED` 的 manifest ref/digest 仍可用，只是缺少 explicit link validation |

## Final conclusion: **revise**

plan 的 root cause 分析正确（同源且充分），新增 `RUNNER_CALL_INPUT_ITERATION_LINKED` 的方案在架构边界、最小性、非越层方面合理。但存在 **3 个阻断项**（F1, F2, F3）需要在 re-enter implementation gate 前修复：

**阻断项（必须修）**：
- **F1（高）**: `_has_prior_iteration_observation` 的 durable query 契约未定义 — 这是 fail-closed vs. continuation 的关键分支判断
- **F2（中）**: "ordinary dispatch kind" 未给闭集 — implementation agent 可能用错 filter 导致漏 link 普通 manifest
- **F3（中）**: link resolution 缺少 ordinary manifest 写入与 ITERATION_STARTED ingest 之间的 timing/ordering 约束

**非阻断建议（应在 implementation 前澄清）**：
- F4（中）: anti-join 查询设计未给出
- F5（低）: 新增 diagnostic reason 与现有枚举对齐未明确
- F6（低）: continuation reset 测试夹具 seeding 路径缺失
- F7（低）: preview payload 的 resolution result 传递机制未指定
- F8（低）: link event 与 preview 的事务原子性约束未进入 stop condition
- OQ1-OQ3: 三个 open questions 建议在 design sync (Slice 0) 中裁决

修复以上阻断项后 plan 可以进入 implementation gate。F4-F8 和 OQ1-OQ3 可在 Slice 0 design sync 中一并澄清，不必须全部事前解决，但 F4（anti-join）强烈建议在 Slice 1 开始前有明确的查询设计。
