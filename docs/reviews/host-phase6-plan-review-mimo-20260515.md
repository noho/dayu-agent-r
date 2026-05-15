# Host Phase 6 Plan Review - MIMO - 2026-05-15

## 结论

**Verdict: PASS (with findings)**

Plan 是 implementation-ready / code-generation-ready。设计真源对齐、non-goals 守卫、accept barrier 语义、idempotency mapping、run-scoped truncation / fetch_more、run-local duplicate governance 均正确覆盖。未发现阻塞性问题。

## Finding 统计

- finding count: 4
- blocking count: 0
- open questions: 0

---

### MIMO-F1-未修复-低-EventLog 工具事件类型假设未显式验证

- **Plan位置**: §4.2 Schema Decision, §4.3 EventLog Facts
- **问题类型**: 实现前提假设
- **直接证据**: Plan 声明"No new durable table is allowed for Phase 6"并允许"adding tool canonical event payload types / codecs / validation needed by EventLog if the current implementation stores an event type allow-list or payload shape registry in schema code"。经验证 `dayu/host/durable/event_log.py:265` 的 `append_event` 不做 event_type closed set 验证（`event_type: TEXT NOT NULL`），`_RUN_INPUT_CONTINUITY_EVENT_TYPES` 只用于 run input continuity 查询而非全局白名单。因此 P6 新增 `TOOL_CALL_REQUESTED` / `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` 事件类型无需 schema version bump，假设成立。
- **影响**: 实现 agent 可能花时间验证此假设或过度保守地触碰 schema.py。
- **建议修复**: 在 §4.2 明确记录："经验证 EventLog append_event 不做 event_type closed set 验证，P6 新增 TOOL_* 事件类型无需 schema version bump；仅需在 `_event_payload.py` 添加对应的 payload 解析辅助函数。"

---

### MIMO-F2-未修复-低-批量 ToolExecutor 并发语义未显式覆盖

- **Plan位置**: §3.4 ToolExecutor Wrapper, §7 Testing Matrix
- **问题类型**: 测试覆盖缺口
- **直接证据**: §3.4 步骤声明"批内一个 call 的 accept failure 不得让其它已 accepted call 的事实回滚"，这是一个重要的并发 / 部分失败语义。但 §7 Testing Matrix 的 unit 和 integration 列表均未包含批量执行场景（如：2 个 call，第 1 个 accepted、第 2 个 accept rejected → 第 1 个结果仍返回给 Engine）。
- **影响**: 实现 agent 可能遗漏批量部分失败测试，导致回归时无法捕获回滚 bug。
- **建议修复**: 在 §7 unit tests 补充："batch execution: one call accept failure does not roll back other already-accepted calls in the same batch"。

---

### MIMO-F3-未修复-低-ToolAwaitingOutcome 受治理结果类型未指定

- **Plan位置**: §3.4 ToolExecutor Wrapper step 5, §3.9 Awaiting / Replay Guards
- **问题类型**: contract 细节模糊
- **直接证据**: §3.4 step 5 声明"如果返回 ToolAwaitingOutcome，Phase 6 必须转为 governed unsupported outcome"。§3.5 ToolFactKind 列出 `completed`、`failed`、`cancelled`、`reuse`、`governed_error`，其中 `awaiting` 只能进入 `governed_error` 或 `unsupported_awaiting` policy decision。但 plan 未指定受治理 unsupported 结果映射为 `ToolFailedOutcome` 还是 `ToolCancelledOutcome`，也未指定 policy decision 是 `governed_error` 还是 `unsupported_awaiting`（后者未出现在 ToolFactKind 列表中）。
- **影响**: 实现 agent 需要自行选择，可能导致多个实现间不一致。
- **建议修复**: 明确指定"ToolAwaitingOutcome 在 Phase 6 映射为 `ToolFailedOutcome`（含 governed error message），policy decision 使用 `governed_error`，ToolFactKind 使用 `governed_error`。`unsupported_awaiting` 作为 policy decision 内部标识，不进入 canonical ToolFactKind。"

---

### MIMO-F4-未修复-信息-slice 切分偏离实现控制建议

- **Plan位置**: §6 Implementation Slices
- **问题类型**: 与实现控制文档偏差
- **直接证据**: `docs/host/implementation-control.md` Phase 6 建议 4 个 slices（ToolRuntime ports / effective ToolBundle；Host accept barrier；TruncationManager / fetch_more；duplicate governance / diagnostic emitter）。Plan 实际切分为 6 个 slices，将 S3（ToolExecutor wrapper + ack retry + side-effect policy + awaiting guard）和 S6（integration + docs）独立出来。
- **影响**: 无负面影响。6-slice 方案更精细，每个 slice 更聚焦，更符合 slice 切分原则（可独立验证的行为闭环）。S3 将 ToolExecutor wrapper 与 accept barrier 分离是正确的，因为 S2 可以独立测试 accept port 而不需要完整 executor。
- **建议修复**: 无需修复。可在 plan 中简要说明偏离理由（如："将实现控制建议的 4 slices 细化为 6 slices，以保证每个 slice 的独立可验证性"）。

---

## Design Source 对齐验证

| 设计真源要求 | Plan 覆盖 | 验证 |
|---|---|---|
| Host-owned ToolRuntime (§18) | §1.1, §3.1-3.2, §6 S1-S3 | PASS |
| effective ToolBundle 同源 (§18.1) | §3.3, §6 S1 tests | PASS |
| ToolRuntime ports (§18.2) | §3.2 全部 8 个 ports | PASS |
| accept barrier (§18.2) | §3.4, §3.5, §6 S2-S3 | PASS |
| accept idempotency key (BQ2 裁决) | §4.4 | PASS |
| ack timeout 默认治理 (BQ1 裁决) | §3.4 step 8-9, §3.5 | PASS |
| 语义级重复工具调用治理 (§18.3) | §3.7, §6 S5 | PASS |
| TruncationManager / fetch_more (§19) | §3.6, §6 S4 | PASS |
| run-scoped cursor (BQ4 裁决) | §3.6, §1.3 non-goals | PASS |
| side-effect / paid policy (BQ6) | §3.8, §6 S3 | PASS |
| Phase 7 边界 (BQ5 裁决) | §3.9, §1.3 non-goals | PASS |

## Non-goals 守卫验证

| 被禁止的 scope creep | Plan 守卫位置 | 验证 |
|---|---|---|
| Phase 7 wait record / WAITING / resolve_wait | §1.3, §3.4 step 5, §3.9, §6 S3 non-goals | PASS |
| Phase 11 recovery | §1.3, §3.6 cursor errors, §9 | PASS |
| Phase 13 projection | §1.3, §3.2 ToolTraceDiagnosticEmitter | PASS |
| Phase 14 remote wire protocol | §1.3, §3.1, §6 S3 stop condition | PASS |
| Phase 12 tool discovery | §1.3 | PASS |
| durable cursor descriptor | §1.3, §3.6, §4.2 forbidden | PASS |
| Engine tool governance | §1.3, §3.1, §6 S3 stop condition | PASS |
| dayu.fins import | §5.3 forbidden files | PASS |
| Any / object / 无类型签名 | §3.2 约束, §6 S1 tests | PASS |
| extra payload | §1.3, §4.3 | PASS |

## Controller Adjudication 覆盖验证

| 裁决项 | Plan 覆盖 | 验证 |
|---|---|---|
| BQ1 ack timeout 默认治理 | §3.4 step 8-9, §3.5 ToolAcceptRetryPolicy | PASS |
| BQ2 accept idempotency mapping | §4.4 | PASS |
| BQ3 effective ToolBundle 同源 (降级) | §3.3, §6 S1 tests | PASS |
| BQ4 durable cursor (降级) | §3.6, §1.3, §4.2 forbidden | PASS |
| BQ5 Phase 6/7 边界 | §3.9, §1.3 | PASS |
| BQ6 side-effect/paid (拆分) | §3.8, §9 P7 owner | PASS |

## Artifact 路径

`docs/reviews/host-phase6-plan-review-mimo-20260515.md`

## 验证结果

`git diff --check`: 无 whitespace 错误。
