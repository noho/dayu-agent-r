# WU-SEMANTIC-OWNERSHIP-01 P3-J Plan Review — AgentMiMo

## Review Target

- Artifact: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-J - Host durable schema and weak-contract hardening backlog`
- Reviewer: AgentMiMo
- Review date: 2026-07-11

## Review Scope

- Source finding disposition correctness (especially memory freshness reject, host_run_results reject, execution_target defer, SS-8/SS-9/SS-11/SS-12 reject)
- S1 event_type closed-set implementability and completeness risk
- S1 queue_policy typed owner / AdmissionPolicy dual-owner risk
- S2 idempotency scope/result kind and descriptor kind completeness
- S3 legacy config re-ownership and runtime boundary
- Slice sizing, coupling, and validation sufficiency
- Architecture boundary, best practice, optimal solution, overengineering, and overcoupling lenses

## Assumptions Tested

1. All P3-J source findings are correctly classified with current-code evidence.
2. S1 event_type closed-set can be made exhaustive from current code.
3. S1 queue_policy typed owner does not introduce dual ownership or public API churn.
4. S2 idempotency scope/result kind legal set is provably complete.
5. S2 DDL CHECK will not lock out future extension or break existing fixtures.
6. S3 legacy config removal respects runtime boundary.
7. Slices are independently testable and not overcoupled.

## Findings

### F1-未修复-中-S1 event_type closed-set 未在 plan 中预枚举，依赖实现时扫描

- **位置**: S1 Concrete allowed changes, "Define a single Host EventLog legal-set owner"
- **问题类型**: 不可直接实施
- **当前写法**: plan 要求 "It must include all current production EventLog event types found by source scan"，但未在 plan artifact 中列出已知 production event type 集合。实现 agent 必须在实现时自行做全量扫描。
- **反例/失败场景**: 实现 agent 的 source scan 遗漏某个 production event type（例如 `USAGE_REPORTED`、`RUNNER_CALL_INPUT_ASSEMBLED`、`CONTEXT_COMPACTION_ATTEMPT_REJECTED`），DDL CHECK 写入后，该 event type 的 append 将被 SQLite 拒绝，导致生产 EventLog 写入失败。
- **为什么有问题**: plan 的 stop condition 只说 "Stop and report blocking open question if the production event-type set cannot be made exhaustive"，但没有给实现 agent 提供已知集合作为扫描基线。当前代码中 event type 常量分散在 `lifecycle_events.py`（10 个 Run + 6 个 Attempt）、`admission.py`（7 个）、`run_transition.py`（10+ 个）、`tool_trace.py`（10+ 个）、`read_api.py`（10+ 个）、`engine_ingest.py`（多个），且存在跨模块重复定义（source review SS-1 直接证据）。实现 agent 若只扫描部分模块，极易遗漏。
- **直接证据**:
  - `lifecycle_events.py:17-45`: HostRunEventType (10 members) + HostAttemptEventType (6 members)
  - `admission.py:147-153`: 7 private `_EVENT_TYPE_*` constants
  - `run_transition.py:94-103`: 10 private `_EVENT_TYPE_*` constants
  - `tool_trace.py:90-101`: 10+ private `_EVENT_TYPE_*` constants
  - `read_api.py:97-113`: 10+ private `_EVENT_TYPE_*` constants
  - source review SS-1 证据：三套独立终端事件类型常量
- **影响**: 实施 agent 跑偏 / DDL CHECK 锁死有效 event type / 生产写入失败
- **建议改法和验证点**: plan 应在 S1 中预枚举已知 production event type 集合（从 source review SS-1 和当前代码 evidence 汇总），作为实现 agent 的扫描基线。实现 agent 以此为起点做 source scan 验证，发现增量时补充。验证点：枚举集合 ⊇ 所有 `rg -n 'event_type="[^"]+"' dayu/host` 命中值。
- **修复风险（低）**: 只需在 plan 中增加一个枚举列表。
- **严重程度（中）**: 不阻塞 plan 进入实现，但增加实现 agent 跑偏风险。

### F2-未修复-中-S1 queue_policy typed owner 与 AdmissionPolicy 的关系未明确，存在双 owner 风险

- **位置**: S1 Concrete allowed changes, "Introduce a public / durable RunQueuePolicy or equivalent typed owner"
- **问题类型**: 架构边界 / 契约缺失
- **当前写法**: plan 说 "Replace admission-local AdmissionPolicy duplication or make it an alias to the single owner without compatibility re-export"，但 `AdmissionPolicy` 已经是 `admission.py` 中的 `StrEnum`（QUEUE, REJECT, ATTACH_ACTIVE），而 `StartRunRequest.queue_policy` 和 `RunRow.queue_policy` 仍是 `str`。plan 用 "RunQueuePolicy or equivalent" 描述新 owner，未明确新类型与现有 `AdmissionPolicy` 的关系。
- **反例/失败场景**: 实现 agent 创建 `RunQueuePolicy` 新类型放在 durable 模块，同时保留 `AdmissionPolicy` 作为 admission 内部类型，导致同一语义（queue/reject/attach_active）有两个独立 owner。后续新增 queue_policy 值时需要同步两处。
- **为什么有问题**: `AdmissionPolicy` 当前只在 `admission.py` 内部使用（`grep -rn AdmissionPolicy dayu/host/durable/ dayu/host/api.py` 返回空），说明 durable 层和 public API 层目前没有类型化 queue_policy。plan 的方向正确（引入 typed owner），但 "or equivalent" 留下歧义：是新建类型替代 `AdmissionPolicy`，还是把 `AdmissionPolicy` 提升为公共 owner？
- **直接证据**:
  - `admission.py:179-184`: `AdmissionPolicy(StrEnum)` 定义
  - `api.py:1799`: `StartRunRequest.queue_policy: str`
  - `durable/state.py:286`: `RunRow.queue_policy: str`
  - `durable/schema.py:491`: `queue_policy TEXT NOT NULL`（无 CHECK）
  - `grep -rn AdmissionPolicy dayu/host/durable/ dayu/host/api.py` 返回空
- **影响**: 实施 agent 创建双 owner / 兼容 re-export / public API churn
- **建议改法和验证点**: plan 应明确：`AdmissionPolicy` 就是 queue_policy 的 typed owner，将其从 admission 私有提升为 host 公共类型（或在公共模块定义并让 admission 导入），`StartRunRequest.queue_policy` 和 `RunRow.queue_policy` 改为 `AdmissionPolicy` 类型。验证点：全仓只有一个 queue_policy 枚举定义，无兼容 re-export。
- **修复风险（低）**: 只需明确 plan 中的类型归属。
- **严重程度（中）**: 不阻塞 plan，但增加实现 agent 引入双 owner 风险。

### F3-未修复-中-S1 切片过宽：三个独立语义变更耦合在一个 slice 中

- **位置**: S1 Purpose, "Add closed-set protection for Host EventLog event types. Add typed queue policy ownership and durable CHECK. Make RunResultRow.terminal_status typed at the row decoder boundary."
- **问题类型**: 过度耦合
- **当前写法**: S1 包含三个独立的语义变更：(1) event_type closed-set + DDL CHECK + 15+ consumer 文件重定向，(2) queue_policy typed owner + DDL CHECK + admission/durable/public API 更新，(3) RunResultRow.terminal_status 类型化 + consumer 更新。plan 用 "semantic closure" 理由合并。
- **反例/失败场景**: event_type owner 引入导致某个 consumer 文件的 import 路径变化，触发 pyright 报错或测试失败，阻塞 queue_policy 和 terminal_status 的实现。或者 event_type DDL CHECK 遗漏某个 production 值，导致测试大面积失败，整个 S1 回退。
- **为什么有问题**: 三个变更的 owner boundary 不同（event_type owner vs queue_policy owner vs terminal_status owner），propagation path 不同，failure mode 不同。耦合在一个 slice 中，局部失败阻塞全局。plan 的 validation matrix 把所有 S1 测试放在一个 pytest 命令中，无法区分哪个变更引入了回归。
- **直接证据**:
  - S1 Allowed files: 15+ consumer 文件（lifecycle_events, context_events, durable/event_log, durable/schema, durable/state, durable/run_transition, durable/read_model, api, admission, read_model, read_api, outbox, tool_trace, durable/memory, memory, run_input, compact_material, dispatch, engine_ingest, tool_runtime, waiting, durable/session_lifecycle）
  - S1 Tests: 5 个 test 文件 + focused consumer tests
  - 三个独立 DDL CHECK 变更
- **影响**: 局部失败阻塞全局 / 实现 agent 返工范围大 / review 难度高
- **建议改法和验证点**: 将 S1 拆为 S1a (event_type closed-set) 和 S1b (queue_policy + terminal_status)。S1a 先落地 event_type owner 和 DDL CHECK，验证 consumer 重定向无回归。S1b 在 S1a 稳定后落地 queue_policy 和 terminal_status。验证点：每个 sub-slice 独立通过 pyright 和测试。
- **修复风险（低）**: 只需调整 slice 边界。
- **严重程度（中）**: 不阻塞 plan，但增加实现风险。

### F4-未修复-低-S2 idempotency scope/result kind DDL CHECK 完整性证明不足

- **位置**: S2 Concrete allowed changes, "DDL CHECK for both columns is allowed only after the audit confirms no intentionally open extension point"
- **问题类型**: 契约缺失
- **当前写法**: plan 列出了 production scope/result kind 值（ensure_session, create_session, close_session, start_run, submit_followup_queue, submit_followup_steer, retry_run, replay_run, cancel_run, cancel_session_runs, tool_awaiting_accept, wait_resolution, wait_late_rejection, purge_session / session, run, tool_awaiting_accept_ack, wait_resolution, wait_late_rejection_diagnostic, purge_tombstone），但这些值分散在 4 个模块中，plan 未证明它们是完整集合。
- **反例/失败场景**: 实现 agent 在审计后添加 DDL CHECK，但遗漏了某个 future 或 test-only scope_kind，导致新功能开发时 idempotency 写入被 DDL 拒绝。
- **为什么有问题**: idempotency 是 Host 命令幂等性基础设施，未来可能扩展新的 scope_kind（例如新的 Host command 类型）。DDL CHECK 会锁死当前集合。plan 的 stop condition 说 "Stop and report if idempotency is intentionally open for external callers"，但没有明确 "external callers" 的定义——是 Host 内部新模块，还是跨层外部调用？
- **直接证据**:
  - `admission.py:161-167`: 7 operation constants
  - `session_lifecycle.py:65-67`: 3 operation constants
  - `waiting.py:122-131`: 3 scope + 3 result constants
  - `purge.py:66-72`: 1 scope + 1 result constant
  - `durable/schema.py:363-382`: `scope_kind TEXT NOT NULL` 和 `result_kind TEXT NOT NULL`（无 CHECK）
- **影响**: DDL CHECK 锁死未来 extension / 新 Host command 无法使用 idempotency
- **建议改法和验证点**: plan 应明确：(1) idempotency scope/result kind 的 extension 边界是 "Host 内部 command 类型"，不是外部插件；(2) DDL CHECK 应包含当前已知全集 + 明确的 extension policy（例如 "新增 scope_kind 需同时更新 DDL CHECK 和 owner enum"）。验证点：DDL CHECK 值集合 = owner enum 值集合 = source scan 命中集合。
- **修复风险（低）**: 只需明确 extension policy。
- **严重程度（低）**: 不阻塞 plan，但 DDL CHECK 策略需要明确。

### F5-未修复-低-S1 event_type DDL CHECK 与测试 fixture 的时序依赖

- **位置**: S1 Tests / validation, "Replace test-only arbitrary event types with legal values"
- **问题类型**: 切片过粗
- **当前写法**: plan 要求 "Replace test-only arbitrary event types with legal values, except tests that explicitly assert invalid event type rejection"，但未明确 DDL CHECK 添加和测试 fixture 更新的先后顺序。
- **反例/失败场景**: 实现 agent 先添加 DDL CHECK，再更新测试 fixture。在 CHECK 生效后、fixture 更新前，所有使用 `TYPE_A`、`TEST_EVENT` 等任意 event type 的测试将在 fresh schema 上失败。
- **为什么有问题**: `test_projection_runner.py` 大量使用 `event_type="TYPE_A"`（10+ 处）。如果 DDL CHECK 先于 fixture 更新生效，这些测试全部失败，阻塞 S1 验证。
- **直接证据**:
  - `tests/host/test_projection_runner.py:307,410,442,490,532,560,606,725,764,771`: `event_type="TYPE_A"`
  - `durable/schema.py:329`: `event_type TEXT NOT NULL`（当前无 CHECK）
- **影响**: 测试大面积失败 / S1 验证阻塞
- **建议改法和验证点**: plan 应明确实现顺序：(1) 先更新测试 fixture 使用 legal event types，(2) 再添加 DDL CHECK，(3) 最后添加 Python validation。验证点：每个步骤后独立运行测试通过。
- **修复风险（低）**: 只需明确实现顺序。
- **严重程度（低）**: 不阻塞 plan，但实现顺序需注意。

## Explicit Lens Review

### Architecture Boundary Review

plan 正确遵守了 Host 分层边界：
- event_type owner 在 Host 内部（lifecycle_events.py 或新 event_types.py），不跨越 Engine/Service 边界。
- queue_policy owner 在 Host 公共 contract 和 durable 层，不引入 runtime 或 Engine 依赖。
- terminal_status 变更在 durable read-model 边界，不改变 public API 语义。
- S3 变更在 runtime/config_loader.py 和 cli/commands/init.py，不引入 reverse dependency。

未发现架构边界违反。

### Best-Practice Review

plan 的 best practice 表现良好：
- 优先 typed contracts 而非字符串常量。
- DDL CHECK 作为最后一道防线，而非唯一验证手段。
- Row decoder fail-closed 行为保留。
- Stop conditions 防止实现 agent 越界。

唯一偏离：S1 切片过大，不符合 "small-cleanup budget" 的最佳实践。

### Optimal-Solution Review

plan 方案是 credible alternatives 中最实际的路径：
- 不做 broad whole-store migration（正确）。
- 不引入 ORM 或 generic HostRow replacement（正确）。
- 不重新设计 execution_target closed set（正确，deferred to Service owner）。
- S3 直接删除 legacy exposure 而非添加 TODO（正确）。

未发现更优方案。

### Overengineering Review

plan 明确禁止过度设计：
- "No broad whole-store migrations"
- "No generic EventLog payload schema campaign"
- "No generic metadata schema migration"
- "No typed wrapper for every payload metadata key"

未发现过度设计。

### Overcoupling Review

S1 存在过度耦合风险（Finding F3）：三个独立语义变更耦合在一个 slice 中。S2 和 S3 切片大小合理，无过度耦合。

## Open Questions

无阻塞性 open questions。plan 的两个 slice-local stop conditions 是合理的：
- S1: production event-type set 是否可穷尽
- S2: idempotency scope/result kind 是否对外部调用者开放

## Residual Risks

1. **S1 event_type consumer 重定向范围**: 15+ 文件的 import 路径变更可能引入 pyright 报错或 circular import。建议实现 agent 逐文件验证，不要批量替换。
2. **S2 descriptor kind 的 diagnostic kinds**: plan 提到 "producer-specific ad hoc diagnostic kinds"，但未列出具体值。实现 agent 可能遇到 plan 未覆盖的 descriptor kind。
3. **DDL CHECK 与现有数据库**: plan 正确 scope 到 fresh schema，但用户可能有现有数据库。建议在 plan 中记录：DDL CHECK 仅影响 fresh schema，现有数据库需要手动迁移或重建。

## Conclusion

**pass-with-risks**

plan 整体质量高：source finding disposition 正确且有代码证据支撑，slice 分割合理（除 S1 过宽），non-goals 清晰，stop conditions 适当。主要风险在 S1 切片宽度和 event_type closed-set 枚举完整性。这些风险不阻塞 plan 进入实现，但实现 agent 需要注意。

Material findings: 5 (0 blocking, 3 medium, 2 low)
Blocking open questions: 0
