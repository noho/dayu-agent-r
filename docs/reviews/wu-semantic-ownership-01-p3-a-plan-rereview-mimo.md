# WU-SEMANTIC-OWNERSHIP-01 P3-A Plan Re-Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A - Host lifecycle, run status, and terminal event source of truth`
- Gate: plan re-review after Codex plan fix
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md`
- Prior reviews:
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-controller-adjudication.md`

## 结论

**verdict: pass**

AgentCodex plan fix 已关闭 controller adjudication 接受的全部 13 个 findings（PF-01 到 PF-13）。Plan 文本中每个 PF 修复都有具体、可实施、可验证的落地。未发现新 blocker、过度设计或 owner boundary drift。Plan 可进入 implementation gate。

## PF-01 到 PF-13 逐项验证

### PF-01 [blocking] S3 closeout identity scheme — ✅ closed

Plan S3 (lines 320-348) 现在定义了：
- `_HostLifecycleCloseoutCandidate` 必填字段：`envelope`, `observed_at`, `worker_event_index`, `plan`, `lifecycle_source`, `execution_id`
- 完整 event_id 派生公式：`event-host-lifecycle-{sha256("host-lifecycle-terminal" + session_id + run_id + attempt_id + execution_id + worker_event_index + event_class + event_type + sub_index + lifecycle_source + plan.reason)}`
- 与现有 `_EVENT_ID_PREFIX = "event-engine-"` 的命名空间隔离说明
- duplicate terminal detection 按最终 event ids 查重，Engine-origin 和 Host-lifecycle 不碰撞
- Host lifecycle ref 格式：`host-lifecycle:{execution_id}:{worker_event_index}:{lifecycle_source}:{plan.reason}`，明确标注为治理来源标签而非 Engine event id
- late rejection routing 基于 `_HostLifecycleCloseoutCandidate.lifecycle_source` / `plan.reason` / closeout plan kind，不再读取 `candidate.engine_event.type`

### PF-02 [blocking] S3 active-cancel race decision table — ✅ closed

Plan S3 (lines 350-360) 包含 5 行决策表：

| Run 状态 | Incoming fact | Decision | Owner / recorded fact |
|---|---|---|---|
| CANCELLING | Engine FINAL_ANSWER | reject late terminal | Host ingest rejected/diagnostic path |
| CANCELLING | Engine RUN_FAILED | reject late terminal | Host ingest rejected/diagnostic path |
| CANCELLING | Host lifecycle clean EOF | diagnostic/no-op, 不合成 Engine RUN_FAILED | Host lifecycle closeout owner |
| CANCELLING | Host lifecycle lost/crash | worker-lost diagnostic, 不接受为 Engine RUN_FAILED | Host lifecycle closeout owner |
| CANCELLING | Other Engine events | reject/ignore by stale-event rules | Host ingest diagnostic/stale event owner |

表后含 stop condition：若 cancel/watchdog design 要求 worker crash 在 CANCELLING 时 first-committer-wins 写 RUN_LOST，必须停止并要求 design truth 裁决。

### PF-03 [blocking] S3 candidate shape 避免 god-bag — ✅ closed

Plan S3 (lines 320-323) 现在明确：
- 保留 `EngineEventCandidate` 用于 Engine-origin closeout
- 新增 `_HostLifecycleCloseoutCandidate` 用于 worker lifecycle closeout，各自有必填字段
- 禁止 optional-field probing 区分两种 origin
- 如需共享 closeout core，只能使用 tagged union：`TerminalCloseoutOrigin` discriminator + typed payload

### PF-04 [blocking] S2 source scan 强制化与精确化 — ✅ closed

Plan S2 (lines 273-280) 现在：
- source scan 升级为"强制 validation，不是可选测试"
- 精确 regex：`_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)`，只匹配 terminal 常量
- 预期结果明确：`run_transition.py` 和 `engine_ingest.py` 不得残留 terminal `_EVENT_TYPE_*` constant 定义、if/elif mapping 或裸字符串 producer
- 禁止 diagnostic whitelist 泛化放行
- 独立列出非 terminal residual 常量清单（`run_transition.py` 10 个 + `engine_ingest.py` 9 个），作为 P3-J / future EventLog schema hardening 输入

### PF-05 [blocking] import cycle 预防具体化 — ✅ closed

Plan section 3 (lines 135-162) 现在包含：
- 完整 import graph baseline（5 个模块的依赖方向和禁止方向）
- 已验证 `dayu/host/api.py` 不导入 `dayu/host/durable/` 下模块
- 具体验证命令：`python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"`
- Stop condition：若 helper placement 引入 import cycle，implementation 必须停止并回到 design/plan fix

### PF-06 [high] SM-7 pre-implementation 验证步骤 — ✅ closed

Plan SM-7 section (lines 87-93) 现在：
- 要求进入 S1 前搜索生产代码中所有 `FollowupSnapshot(...)` 构造点和 `accepted_run_status` 传参
- 提供具体搜索命令
- 定义 found（升级为 P3-A scope 或记录 deferred owner）和 not-found（记录搜索结果和 closure basis）两条路径

### PF-07 [medium] SQL helper 验证 — ✅ closed

- S1 (line 225)：SQL helper owner test，断言 `run_status_in_clause(...)` 对空集合 fail-fast，placeholder 数量与 params 一致
- S2 (line 298)：SQL/query-plan validation，通过 `EXPLAIN QUERY PLAN` 或等价行为断言确认 helper 生成的 IN clause 不破坏 durable read helper 行为；明确"不能为了 planner 顾虑保留手写 status list"

### PF-08 [medium] `_TERMINAL_STATUS_PAIRS` owner 决策 — ✅ closed

Plan S2 (line 261) 声明为 derived transition invariant：
- 从 `state.TERMINAL_RUN_STATUSES`、`state.TERMINAL_ATTEMPT_STATUSES` 和 lifecycle terminal event helper 支持的 closeout 子集派生
- 不是 durable row-rule truth，也不是 event type mapping truth
- 只允许 Run/Attempt 同名 terminal pair 进入 closeout
- Line 281 要求 derived invariant 测试，新增 terminal status 时必须触发测试失败

### PF-09 [medium] `START_BLOCKING_RUN_STATUSES` 假设显式化 — ✅ closed

Plan S1 (lines 212, 224)：
- docstring 必须说明假设："所有 non-terminal statuses except QUEUED 都会阻塞启动新 Run"
- 明确用于 accepted/start-blocking admission 查询，不等于 active slot
- 增加精确成员集合测试，新增 non-terminal status 时测试失败，迫使开发者显式审查

### PF-10 [medium] propagation audit 可执行标准 — ✅ closed

Plan section 6 (lines 387-398) 每条 audit 路径现在有具体验证方法：
1. Run terminal event type：source scan + transition tests + read/projection tests
2. Attempt terminal event type：owner tests + engine ingest mapping tests + source scan
3. Run status predicate：state schema tests + source scan/review + SQL/query-plan tests
4. Worker lifecycle closeout：worker clean EOF/lost tests + projection/read tests
5. Late event rejection：status predicate tests + active-cancel decision-table tests
6. Direct cancelability：state helper or command tests + source review

### PF-11 [medium] P3-B 边界保持 — ✅ closed

Plan non-goals (line 176)："不预设计 P3-B final answer / terminal descriptor 新字段。S3 如抽取 closeout core，只能保持现有 `_close_terminal` 已有 final-answer / terminal descriptor 参数和行为；P3-B 后续可消费同一 closeout path，但 P3-A 不新增 final-answer-specific 字段，除非它们已由当前 `_close_terminal` 调用签名要求。"

### PF-12 [low] README 实际检查 — ✅ closed

- S1 (line 236)："implementation 必须先阅读并检查 `dayu/host/README.md` 和 `tests/README.md`...再记录'更新'或'不更新'的实际依据。不能用'预计不更新'替代检查"
- S2 (line 300)：同上
- S3 (line 383)：同上

### PF-13 [low] event type value helper 策略 — ✅ closed

Plan S1 (line 210)："event type value projection 采用简单分离 helper，不做 TypeVar / overload 泛化：保留 Run event value helper 只接收 `tuple[HostRunEventType, ...]`，新增 `attempt_event_type_values(events: tuple[HostAttemptEventType, ...]) -> tuple[str, ...]`。禁止用 `Any` 或宽泛 enum bag 规避类型。"

## 新 blocker / 过度设计 / owner boundary drift 检查

### S3 candidate 形状

两条 typed path 设计正确：
- `EngineEventCandidate` 保持不变用于 Engine-origin closeout
- `_HostLifecycleCloseoutCandidate` 专用于 worker EOF/crash
- 各自有明确必填字段，不混合 optional 字段
- 共享 closeout core 使用 tagged union 方案，符合 AGENTS.md 禁止 god-bag 约束

无 god-bag 风险。✅

### active cancel 表的 stop condition

表后 stop condition 设计正确：若 cancel/watchdog design 要求 first-committer-wins 写 RUN_LOST，必须停止裁决而非自行决定。这是正确的防御性设计。✅

### Import graph 验证

验证命令具体可执行，import graph baseline 完整记录了 5 个模块的依赖方向。✅

### Propagation audit

Section 6 的 6 条 audit 路径每条都有具体验证方法（source scan、owner tests、transition tests、read/projection tests、SQL validation、diagnostics、source review），不再是描述性 checklist。✅

### 过度设计检查

- ✅ 不引入新的 public Host API、Engine contract、durable schema、provider capability registry
- ✅ 不修改 Engine contracts 或 Engine runner assembly
- ✅ 不改变 wait record lifecycle 或 wait poller behavior
- ✅ 不引入 RunStatus 新成员或 schema migration
- ✅ 不预设计 P3-B final-answer 字段
- ✅ 不处理非 terminal Host EventLog 常量（已记录为 residual input）

无过度设计。✅

### Owner boundary drift 检查

Plan 的语义 owner boundary 表（section 3）与初始 plan 一致，6 个事实的产生、校验、持久化和投影边界无变化。✅

## Completion Report

```text
status: completed
artifact: docs/reviews/wu-semantic-ownership-01-p3-a-plan-rereview-mimo.md
verdict: pass
blocking findings count: 0
nonblocking findings count: 0
blockers: none
```
