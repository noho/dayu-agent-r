# Host Phase 3 Design Refinement Controller Adjudication

- **gate name**: Phase 3 design discussion / controller adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **source artifact**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **controller conclusion**: not-ready；Phase 3 动机成立，但 plan gate 前必须先确认并写回三个设计决策。
- **artifact path**: `docs/reviews/gateflow-phase-design-host-p3-controller-adjudication-20260514.md`

## Controller Finding Decisions

### BQ1: Phase 3 是否创建最小 dispatch intent / dispatch record durable row？

- **decision status**: accepted；requires user confirmation before design write-back
- **controller decision**: Phase 3 应创建最小 dispatch intent / dispatch record durable row。
- **理由**: `ATTEMPT_STARTED` 在设计真源中表示 Host 已创建 `STARTING` Attempt 并记录 dispatch intent；pre-dispatch cancel 也依赖 dispatch record `pending` / `waiting_for_lane` 语义。若 Phase 3 不创建最小 dispatch intent，`Attempt STARTING` 会缺少 durable startup truth；若 Phase 3 实现 scheduler / lane / WorkerProxy，则越界进入 Phase 5。
- **accepted direction**: Phase 3 只写 dispatch record `pending` 与 `cancelled`，可在 schema 中保留后续 status 枚举，但不得实现 scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch 或 `ATTEMPT_RUNNING`。

### BQ2: Phase 3 的 state index / CAS / idempotency 最小 contract 是否需要在 design.md 中补齐？

- **decision status**: accepted；requires user confirmation before design write-back
- **controller decision**: 需要补齐，且必须在 plan gate 前写入设计真源。
- **理由**: active Run invariant、queue FIFO、CAS loser 行为、operation idempotency scope 与 result refs 会直接决定 DDL、transition service 和多进程测试。把这些选择留给 implementation agent 会违反 schema / state-machine change 的 gateflow 要求。
- **accepted direction**: 在 `docs/host/design.md` 明确 Phase 3 durable state/index contract，包括 session / slot / run / attempt / dispatch record rows、active index 表达、queue ordering、CAS preconditions、rowcount=0 loser 处理、operation idempotency naming 与 semantic digest 输入。
- **controller preference**: active Run invariant 优先采用 SQLite partial unique index on `(session_id)` for active Run statuses，而不是独立 active-run table；原因是它让 active truth 跟随 `runs.status`，减少双写 owner。若实现或 review 证明 SQLite partial unique index 与当前测试/portable schema 不匹配，再回到 design discussion。

### BQ3: Phase 3 plan 是否只覆盖 Phase 3 transition subset，并把跨 phase matrix 行标记为 future-owner？

- **decision status**: accepted；requires user confirmation before design write-back
- **controller decision**: 是。Phase 3 只实现不需要 Engine / ToolRuntime / wait / recovery 的 transition subset。
- **理由**: §9.1 是全局状态迁移真源，包含 Phase 5 / 7 / 10 / 11 才能落地的路径。Phase 3 若按全矩阵实现会越界；若只实现 admission 而缺少 terminal / cancel closeout primitive，又无法验证 active slot release 与 queue promotion 闭环。
- **accepted direction**: Phase 3 owns create / ensure / close Session primitives、start/follow-up queue admission、queue promotion、cancel queued、cancel pre-dispatch starting、internal terminal closeout helper 和 terminal/cancel 后 promotion trigger。Engine final answer ingest、Tool awaiting、resolve_wait、steer、retry/replay、context compaction、recovery scan/dispatch 均保留为 future-owner transition references。

## Controller Required User Confirmation

这三个 accepted directions 都会写回 `docs/host/design.md` 与 `docs/host/implementation-control.md` Phase 3 条目，并影响后续 handoff-ready plan。由于它们涉及 schema、状态机、CAS、dispatch intent ownership 与测试期望，controller 不能在没有用户确认的情况下直接进入 plan gate。

需要用户确认：

1. Phase 3 创建最小 dispatch intent / dispatch record durable row，但不实现 scheduler、lane、WorkerProxy 或 Engine dispatch。
2. Phase 3 在 design.md 中补齐 durable state/index/CAS/idempotency contract；active Run invariant 第一版优先采用 SQLite partial unique index on active run statuses。
3. Phase 3 只实现本 phase owned transition subset；跨 phase matrix 行只作为 future-owner references。

## Current Gate Status

- **current gate**: Phase 3 design discussion / user confirmation
- **plan gate status**: blocked
- **next action after confirmation**: 派发 design fix / write-back，更新 `docs/host/design.md`、`docs/host/implementation-control.md`，再派 AgentMiMo 与 AgentDS 做 design fix re-review。
