# Phase 5 Design Re-Review: RunInputBuilder / LocalProxy / EngineEvent Ingest

## Review Role

Independent reviewer. Review only the Phase 5 design refinement artifact; do not modify production code, do not fix findings, do not commit, do not push, do not enter plan or implementation gate.

## Artifacts Inspected

- `docs/host/design.md` — Host 架构真源（§13.4, §17, §22, §23, §25.1）
- `docs/host/implementation-control.md` — 实施总控文档（Phase 5 条目与追踪区）
- `docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md` — Phase 5 design refinement artifact

## Review Lens

1. Refinement 是否满足 implementation-control Phase 5 目标
2. 是否保持 design.md 边界：UI -> Service -> Host -> Engine、Engine 不理解 Host Attempt、Host durable truth、LocalProxy 语义基准、RemoteProxy transport substitution
3. 三个 user-confirmed decisions 是否连贯且充分
4. 是否存在阻塞 handoff implementation-ready plan 的歧义
5. 过度设计、规格不足、隐藏反向依赖、schema / 状态机缺口、取消缺口、stream EOF terminal closeout 缺口、residual risk ownership

---

## 1. Phase 5 目标覆盖度

**implementation-control Phase 5 目标**：连接 RunInputBuilder、Attempt dispatch record、LLM lane、LocalProxy / EngineWorker、EngineEvent ingest 与 terminal 收口，形成本地 Engine 执行闭环。

**Refinement 覆盖检查**：

| Phase 5 子目标 | Refinement 覆盖 | 证据 |
|---|---|---|
| RunInputBuilder typed provider protocols | P5-D3 (deferred to plan) | Refinement 未枚举具体 provider，但正确指出 plan gate 必须覆盖 |
| Dispatch record 状态扩展 | P5-D2 (accepted) | `pending / waiting_for_lane / dispatching / cancelled` |
| LocalProxy / EngineWorker envelope | P5-D1 (accepted) | Host-owned identity envelope |
| EngineEvent ingest mapping | Plan gate 列表项 | 正确引用 design.md §13.4 |
| Terminal closeout (stream EOF / worker crash) | Plan gate 列表项 | 正确引用 design.md §17 |
| Active dispatch cancel | Plan gate 列表项 | 正确引用 design.md §22 |

**结论**：Refinement 正确识别了 Phase 5 必须覆盖的所有子目标。Refinement 不是 plan，不需提供具体类型定义；它的职责是确认设计决策和识别 plan 必须覆盖的内容。这两项均已完成。

---

## 2. 边界保持度

### 2.1 UI -> Service -> Host -> Engine 分层

- **P5-D1**：Engine 公共 `EngineEvent` 契约保持 Host-agnostic。Host-owned LocalProxy / EngineWorker envelope 绑定 `attempt_id + execution_id`。**边界保持**。
- **P5-D3**：Phase 5 不实现 ToolRuntime governance。Engine 只看见 `ToolExecutor` protocol。**边界保持**。

### 2.2 Engine 不理解 Host Attempt

- design.md §17："Engine 公共 `EngineEvent` 契约只表达 Engine run 内部事件，不提升为 Host Attempt identity carrier"。
- Refinement P5-D1 写回："不得为了 Phase 5 让 Engine 理解 Host `Attempt`、Host durable state、dispatch record 或 recovery policy"。**边界保持**。

### 2.3 Host durable truth

- P5-D2：dispatch record 状态扩展为 Host dispatch 诊断 / 重复派发抑制状态，"不表达 lease / fencing / Attempt owner"。与 design.md §17 一致。**边界保持**。
- P5-D3：`tool_awaiting` / `run_suspended` 不得创建 `WAITING` canonical truth。与 implementation-control 强制约束一致。**边界保持**。

### 2.4 LocalProxy 语义基准 / RemoteProxy transport substitution

- design.md §17："LocalProxy 是语义基准。RemoteProxy 是 transport substitution，不是治理 boundary"。
- Refinement residual risks："RemoteProxy 等价语义仍属于 Phase 14 owner；Phase 5 plan 只能定义 LocalProxy semantic baseline"。**边界保持**。

**结论**：无边界违反。

---

## 3. 三个 User-Confirmed Decisions 评估

### P5-D1. Engine contract remains Host-agnostic

**连贯性**：好。Engine 不修改公共 `EngineEvent` 契约；Host-owned envelope 在 ingest 边界校验 `attempt_id + execution_id`。这与 design.md §17 的 "LocalProxy / EngineWorker identity boundary" 完全一致。

**充分性**：充分。该决策明确了 Phase 5 不触碰 Engine 代码，implementation agent 不会在 Engine contract 修改上做出错误选择。

**潜在关注**：无。

### P5-D2. Dispatch record state expands in Phase 5

**连贯性**：好。`pending -> waiting_for_lane -> dispatching -> cancelled` 与 design.md §17 的 dispatch semantic contract 一致。

**充分性**：基本充分。四个状态覆盖了 dispatch 生命周期的主要阶段。有一个非阻塞观察（见 F-O1）。

**潜在关注**：`dispatching` 之后 dispatch record 的最终状态未明确——dispatch 成功后 record 保持 `dispatching` 还是迁移到新状态？design.md §17 描述了 dispatch 失败路径（Attempt -> FAILED/LOST），但未描述 dispatch 成功后 dispatch record 的归宿。这不影响 plan gate，但 plan agent 需要决策。

### P5-D3. ToolRuntime / WAITING remains out of Phase 5

**连贯性**：好。与 implementation-control 强制约束完全一致："phase plan、implementation 或 fix 不得让 EngineEvent `tool_awaiting` / `run_suspended` 创建 wait record、推进 Run `WAITING` 或关闭 Attempt"。

**充分性**：充分。明确了 Phase 5 的 fake executor 策略和 unsupported execution path 处理方式。

**潜在关注**：无。

**结论**：三个 decisions 连贯、充分、互相不冲突。

---

## 4. Findings

### F-O1. `dispatching` 后 dispatch record 归宿未明确

- **严重性**：Observation（非阻塞）
- **直接证据**：Refinement P5-D2 列出四个 dispatch record 状态 `pending / waiting_for_lane / dispatching / cancelled`。design.md §17 描述了 `dispatching` 后 WorkerProxy 失败的路径（Attempt -> FAILED/LOST），但未描述 dispatch 成功（EngineWorker accept + `ATTEMPT_RUNNING` appended）后 dispatch record 是否需要进一步状态迁移。
- **影响**：Plan agent 需要决策：(a) `dispatching` 是 dispatch record 的终态，后续靠 Attempt status 判断；或 (b) 引入第五个状态如 `dispatched` 或 `completed`。选项 (a) 更简单且与现有 design.md 一致（design.md 未描述第五个状态），但 plan 必须显式确认。
- **建议**：Plan agent 应确认 `dispatching` 是 dispatch record 在成功 dispatch 后的终态，recovery scan 通过 Attempt status（而非 dispatch record status）判断后续行为。若需要第五个状态，必须先回到 design.md。
- **是否阻塞 plan gate**：否。Plan agent 可以在 plan 阶段决策，不需要 refinement 先行解决。

### F-O2. RunInputBuilder Phase 5 最小 provider 集合未枚举

- **严重性**：Observation（非阻塞）
- **直接证据**：Refinement plan gate 要求 "RunInputBuilder typed provider protocols 的第一版最小集合，且当前用户输入只能来自 `USER_INPUT_ACCEPTED` canonical fact"。design.md §23 列出 7 个 provider protocol 名称。Refinement 未枚举 Phase 5 实际需要哪些。
- **影响**：Plan agent 需要决定 Phase 5 实现哪些 provider（real vs stub）。Phase 5 只支持 no-tool 或最小 fake ToolExecutor，因此 `ToolSchemaSnapshotProvider` 可以是最小实现；`MemorySnapshotProvider` 和 `CompactArtifactProvider` 可以返回空/None；`CurrentRunFactProvider` 和 `SceneParameterProvider` 必须实现。
- **建议**：Plan agent 应枚举 Phase 5 最小 provider 集合，并明确哪些是 real、哪些是 stub/noop。
- **是否阻塞 plan gate**：否。Plan gate 要求已正确列出该覆盖项。

### F-O3. `cancel_session_runs` dispatching/active worker 子集归属确认

- **严重性**：Observation（非阻塞）
- **直接证据**：implementation-control Phase 5 范围："cancel propagation"。design.md §22："Phase 5 owns 该路径"（指已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy）。implementation-control 追踪区："Phase 4 `cancel_session_runs` 只允许实现 queued / pre-dispatch `STARTING` 子集；Phase 5 / 7 / 11 owner 必须在各自 phase 补齐 dispatching / active worker、`WAITING`、`RECOVERING`"。
- **影响**：Phase 5 必须实现 `cancel_session_runs` 对 dispatching/active worker 的传播路径。Refinement 的 plan gate 列表项已正确包含 "Phase 5 active dispatch cancel 与 `cancel_session_runs` dispatching / active worker 子集"。
- **建议**：Plan agent 必须在 plan 中明确 `cancel_session_runs` 的 dispatching/active worker 子集实现范围。
- **是否阻塞 plan gate**：否。Refinement 正确识别了该覆盖项。

### F-O4. `run_failed(context_compaction_required)` 在 Phase 5 的处理边界

- **严重性**：Observation（非阻塞）
- **直接证据**：design.md §13.4 将 `run_failed` 映射为 "ATTEMPT_FAILED + (RUN_FAILED or RUN_RECOVERING by Host policy); context_compaction_required 在可恢复时进入 RUN_RECOVERING + new Attempt"。design.md §25.1 描述了 reactive trigger 路径。P5-D3 只排除 ToolRuntime / WAITING，未排除 context compaction recovery。
- **影响**：Phase 5 的 EngineEvent ingest 必须至少结构化处理 `run_failed` 事件。若 Engine fake executor 触发了 context compaction 路径（虽然 Phase 5 场景下不太可能），Phase 5 需要决定是否实现基本的 RUN_RECOVERING 状态迁移还是只做 RUN_FAILED 收口。Plan agent 需要明确 Phase 5 对 `run_failed(context_compaction_required)` 的处理策略。
- **建议**：Plan agent 应确认 Phase 5 的 fake executor 场景不会触发 context compaction 路径，或定义 Phase 5 对该路径的最小处理（例如只做 RUN_FAILED 收口，不实现 recovery loop）。
- **是否阻塞 plan gate**：否。Plan agent 可以在 plan 阶段决策。

### F-O5. `usage_reported` EngineEvent 在 Phase 5 的结构化处理

- **严重性**：Observation（非阻塞）
- **直接证据**：design.md §13.4 将 `usage_reported` 映射为 "usage projection input; canonical only if needed for audit policy"。Refinement 未提及 Phase 5 对该事件的处理。
- **影响**：Phase 5 的 EngineEvent ingest 必须至少能结构化接收 `usage_reported`（即使只记录 diagnostic）。Plan agent 需要决定 Phase 5 是忽略、记录 diagnostic 还是写入 canonical event。
- **建议**：Plan agent 应确认 `usage_reported` 在 Phase 5 的最小处理策略（建议记录 diagnostic / preview，不写 canonical fact）。
- **是否阻塞 plan gate**：否。这是 plan-phase 实现细节。

### F-O6. Plan Gate Readiness 与 design.md 重叠度

- **严重性**：Observation（非阻塞，信息性）
- **直接证据**：Refinement plan gate 列表的多项内容（EngineEvent terminal/non-terminal 映射、stream EOF closeout 策略、dispatch recheck races）在 design.md §17 和 §13.4 中已有详细规范。
- **影响**：无负面影响。Plan gate 列表正确指向 design.md 对应章节，作为 plan agent 必须覆盖的 checklist。这不是过度设计，而是正确的 phase 管理。
- **建议**：无。Plan agent 应按 plan gate 列表逐项对齐 design.md。
- **是否阻塞 plan gate**：否。

---

## 5. 阻塞性评估

**无 blocking finding。**

所有 6 个 findings 均为 Observation 级别，不阻塞 plan gate。Refinement 正确完成了 design refinement 的职责：

1. 确认了三个架构敏感决策（Engine-agnostic contract、dispatch record 扩展、ToolRuntime/WAITING 边界）
2. 识别了 plan 必须覆盖的 6 个关键领域
3. 保持了 design.md 的所有架构边界
4. 正确标注了 residual risks 的后续 owner

---

## 6. Residual Risk Ownership 确认

| Residual Risk | Refinement 标注的 Owner | 与 implementation-control 一致性 |
|---|---|---|
| RemoteProxy 等价语义 | Phase 14 | 一致（Phase 14 条目） |
| ToolRuntime accept ack / fetch_more / duplicate governance | Phase 6 | 一致（Phase 6 条目） |
| WAITING cancel / wait record cancel | Phase 7 | 一致（Phase 7 条目） |
| RECOVERING dispatch / positive orphan proof | Phase 11 | 一致（Phase 11 条目） |

**结论**：Residual risk ownership 完整且与 implementation-control 一致。

---

## 7. 总结

Phase 5 design refinement 已完成 design refinement 阶段的职责。三个 user-confirmed decisions 连贯、充分且互相不冲突。所有架构边界保持完好。无 blocking finding。

**6 个 Observation findings** 均为 plan-phase 可解决的实现细节，不需要 refinement 先行修正：

- F-O1: `dispatching` 后 dispatch record 归宿
- F-O2: RunInputBuilder Phase 5 最小 provider 集合
- F-O3: `cancel_session_runs` dispatching/active worker 子集
- F-O4: `run_failed(context_compaction_required)` 处理边界
- F-O5: `usage_reported` 结构化处理
- F-O6: Plan Gate 与 design.md 重叠度（信息性）

**结论：无 blocking finding，可以进入 Phase 5 plan gate。**
