# WU-SEMANTIC-OWNERSHIP-01 P3-A Plan Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A - Host lifecycle, run status, and terminal event source of truth`
- Gate: plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- Source review artifacts:
  - `docs/reviews/repo-review-20260710-092911.md` (AgentCodex)
  - `docs/reviews/repo-review-20260710-091608.md` (AgentDS)
  - `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` (AgentMiMo)
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`

## 结论

**verdict: pass-with-findings**

Plan 整体从第一性原理确认了 P3-A 的动机与 root cause，finding 裁决基本正确，owner boundary 清晰，slice 切分合理。发现 1 个 blocking finding、3 个 non-blocking findings。

## Findings

### F-01 [blocking] S2 缺少 lifecycle_events.py → run_transition.py / engine_ingest.py import cycle 预防的具体验证步骤

- **severity**: blocking
- **evidence**: plan section 5, S2 "Rollback risk" 行; `dayu/host/lifecycle_events.py` 模块级 import; `dayu/host/durable/run_transition.py` 当前无 `lifecycle_events` import; `dayu/host/engine_ingest.py` 当前无 `lifecycle_events` import
- **why it matters**: S2 要求 `run_transition.py` 和 `engine_ingest.py` 从 `lifecycle_events.py` 导入 terminal event type helper。`lifecycle_events.py` 当前是叶子模块（无 `dayu.host` 内部 import），但如果它新增 `AttemptStatus` 相关 helper 而 `AttemptStatus` 定义在 `dayu.host.durable.state` 中，就会产生 `lifecycle_events → state → (potentially back to lifecycle_events)` 的 cycle 风险。Plan 的 stop condition 提到了 "import cycle" 但没有具体说明 `lifecycle_events.py` 的依赖图分析和如何避免 cycle。
- **required fix**: 在 S2 实施步骤中增加依赖图前置检查：(1) 确认 `lifecycle_events.py` 当前无 `dayu.host.durable` 内部 import；(2) 若 S1 需要从 `state.py` 导入 `AttemptStatus`，明确 `lifecycle_events.py` 只依赖 `dayu.host.durable._row_rules` 或 `dayu.host.durable.enums`（若存在），不依赖 `state.py` 的 high-level helpers；(3) 若无法避免 cycle，明确将 Attempt event type helper 放在 `lifecycle_events.py` 而 Attempt status enum 从 `dayu.contracts` 或 `_row_rules` 导入。增加一条验证命令：`python -c "from dayu.host.lifecycle_events import *"` 确认无 cycle。

### F-02 [non-blocking] S1 `run_status_in_clause` SQL helper 的 query plan / index usage 验证不足

- **severity**: medium
- **evidence**: plan section 5, S1 "Exact allowed changes" 第 6 点; `dayu/host/durable/state.py:1596-1607` 现有硬编码 SQL
- **why it matters**: Plan 提出 `run_status_in_clause(statuses) -> tuple[str, tuple[str, ...]]` 动态生成 SQL IN clause。当前硬编码 5 个 `?` 占位符的 SQL 可能已被 SQLite query planner 优化为 index scan。动态生成的 `IN (?, ?, ...)` 在集合很小（4-6 个元素）时应该等价，但 plan 没有要求验证生成的 SQL 仍走 index。Stop condition 第 4 条提到了这个风险但只是"记录证据"。
- **required fix**: 建议在 S1 实施时增加一条 `EXPLAIN QUERY PLAN` 验证：对比硬编码 IN clause 与 helper 生成 IN clause 的 query plan，确认都走 `status` index。如果 helper 生成的 SQL 不走 index，应改为在 Python 层过滤而非 SQL 层。

### F-03 [non-blocking] S3 `_close_terminal` 抽取为 `_TerminalCloseoutCandidate` 时缺少与 P3-B 的接口边界说明

- **severity**: medium
- **evidence**: plan section 5, S3 "Exact allowed changes" 第 4 点; P3-B scope in controller adjudication
- **why it matters**: S3 计划从 `_close_terminal` 抽取内部 closeout core，可能引入 `_TerminalCloseoutCandidate` dataclass。P3-B 的 scope 是 terminal final answer projection 和 Outbox continuity，也涉及 terminal closeout path。如果 S3 的 closeout core 接口设计不考虑 P3-B 的消费方式，P3-B 可能需要再次修改同一 closeout core。
- **required fix**: 在 S3 的 non-goals 或 interface handoff 中明确：`_TerminalCloseoutCandidate`（或等价内部 dataclass）的字段必须包含 `final_answer_text` 或 terminal descriptor ref，使 P3-B 能直接消费同一 closeout core 而不需要再次修改 `_close_terminal`。不需要在 P3-A 实现 P3-B 的功能，但接口应预留。

### F-04 [non-blocking] S2 source scan test 的 whitelist 策略需要更精确

- **severity**: low
- **evidence**: plan section 5, S2 "Tests / expected assertions" 最后一点
- **why it matters**: Plan 提出对 `_EVENT_TYPE_RUN_*` / `_EVENT_TYPE_ATTEMPT_*` 前缀做 source scan，但 whitelist 策略只说"只允许 `lifecycle_events.py` 或测试/diagnostic whitelist"。当前 `run_transition.py` 和 `engine_ingest.py` 中的非 terminal event 常量（如 `_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_RUN_STARTED`、`_EVENT_TYPE_RUN_WAITING` 等）在 P3-A 范围外，不应被删除。Source scan 如果过于宽泛会误报这些合法常量。
- **required fix**: Source scan regex 应精确匹配 terminal event 常量：`_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)`。非 terminal 常量（`ACCEPTED`、`QUEUED`、`STARTED`、`RUNNING`、`CANCELLING`、`RECOVERING`、`WAITING`、`SUSPENDED`、`STEERED`）不在 P3-A scope 内，scan 不应覆盖。

## Finding 裁决验证

### SM-5 (rejected-with-reason): ✅ 正确

Plan 裁决 SM-5 为 rejected，理由是 cancelled wait row 服务于 poller abandon 外部 job。直接代码证据确认：

- `state.py:2070-2074`（实际是 `read_wait_records_for_poll_observation` docstring）明确说 "cancelled row 用于让 adapter 放弃外部 job；调用方不得把它交给 resolve_wait"。
- `claim_wait_record_for_poll` 的 SQL 对 CANCELLED 使用 `poll_abandoned_at IS NULL` 门控，只允许 poller 观察一次以执行 abandon。
- CANCELLED wait 不会进入 `resolve_wait`，也不是 Run terminal truth。

Plan 说"若未来要重命名为 `awaiting_abandon_pending`，应归 wait poller / external job lifecycle WU"是合理的 deferred 处理。

### SM-7 (needs-more-evidence): ✅ 正确

Plan 裁决 SM-7 为 needs-more-evidence。直接代码证据确认：

- `api.py:2399-2402` 的 `FollowupSnapshot.__post_init__` 只拒绝 `accepted_run_status=RECOVERING`。
- 但没有证据表明当前生产 submit path 能产生 recovering accepted followup。`mark_running_run_recovering_row` 是 recovery 内部 transition，不直接被 submit path 调用。
- 需要实际生产路径证据才能判断这个 guard 是否不足。

### SM-8 (rejected-with-reason): ✅ 正确

Plan 裁决 SM-8 为 rejected。直接代码证据确认：

- `state.py` 中 `_session_timeline_cursor` 相关代码返回 `closed_event_sequence` 或 `created_event_sequence`。
- 这是 cursor / EventLog sequencing 事实，不是 Session status 判定。
- Session row shape validation 已要求 open session 的 closed refs 为空。
- 把 timeline cursor 改成由 status 派生会丢失具体 EventLog cursor 信息。

## Owner Boundary 验证

Plan 的语义 owner boundary 表（section 3）正确识别了 6 个事实的产生、校验、持久化和投影边界：

1. **Run status closed set**: `RunStatus` enum + durable row rules → `host_runs.status` → admission/read model/purge ✅
2. **Attempt terminal status**: `AttemptStatus` enum + durable row rules → `host_attempts.status` → engine ingest/recovery ✅
3. **Host lifecycle event type**: `lifecycle_events.py` → EventLog `event_type` → durable transition/engine ingest ✅
4. **Terminal closeout identity**: EngineEvent candidate / Host lifecycle candidate → EventLog `event_id` + `event_sequence` ✅
5. **Terminal already closed predicate**: durable Run/Attempt status → `is_terminal_*` predicate ✅
6. **Pre-worker direct cancelability**: durable dispatch record state → `is_dispatch_record_direct_cancelable` helper ✅

## Slice 评估

### 3 个 slices 是否合理？

合理。按 control doc 的 slice 切分原则：

- **S1 (Lifecycle/status owner helpers)**: 建立 contract-only helpers，不改变行为路径。低 rollback risk。✅ 独立可验证。
- **S2 (Migrate terminal status/event consumers)**: 依赖 S1 的 stable contract。中低 rollback risk，主要风险是 import cycle。✅ 有明确输入/输出。
- **S3 (Host lifecycle closeout and lifecycle predicates)**: 依赖 S1/S2 的 helper 稳定性。中 rollback risk。✅ 语义闭环。

3 slices 对于"小型同一语义 cleanup"在默认 1-3 slice budget 内。每个 slice 都有明确 allowed files、exact allowed changes、tests/expected assertions 和 validation commands。符合 control doc 要求。

### S1-S3 依赖顺序

S1 → S2 → S3 依赖顺序正确。S2 需要 S1 的 helper，S3 需要 S2 的 consumer migration 完成后才能安全修改 closeout path。

## Architecture Drift 检查

- ✅ Plan 不引入新的 public Host API、Engine contract、durable schema、provider capability registry、第二套 watchdog。
- ✅ Plan 不修改 Engine contracts 或 Engine runner assembly。
- ✅ Plan 不改变 wait record lifecycle 或 wait poller behavior。
- ✅ Plan 不引入 RunStatus 新成员或 schema migration。
- ⚠️ S3 抽取 `_TerminalCloseoutCandidate` 可能影响 P3-B，但 plan 已在 non-goals 中说"不处理 P3-B"。需要在接口层面预留（见 F-03）。

## Import Cycle 风险

主要风险在 S2：`lifecycle_events.py` → `durable/state.py` → (可能 cycle)。Plan 的 stop condition 第 3 条提到了这个风险，但缺少具体预防步骤（见 F-01）。

## Test Gap 检查

- ✅ S1 覆盖 owner helper 的正确性。
- ✅ S2 覆盖 terminal event type 一致性、source scan。
- ✅ S3 覆盖 worker closeout identity、late rejection predicate、direct cancelability。
- ⚠️ S3 缺少 explicit propagation audit test（plan section 6 有 propagation audit plan 但不是 automated test）。

## README 触发检查

- `dayu/host/` 修改 → 检查 `dayu/host/README.md`：Plan 说"预计不更新"，合理，因为这是内部 owner helper 收束。
- `tests/` 修改 → 检查 `tests/README.md`：Plan 说"预计不更新"，合理。
- 不涉及用户可见行为变化、分层关系变化或 public contract 变化。

## LLM-facing 文本检查

P3-A 不涉及 LLM-facing 文本变更。所有修改都在 Host durable state、lifecycle event 和 internal helper 层面。✅

## Completion Report

```text
status: completed
artifact: docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-mimo.md
verdict: pass-with-findings
blocking findings count: 1
nonblocking findings count: 3
blockers: F-01 (import cycle 预防步骤缺失，需在 S2 实施前修复)
```
