# Host Phase 7 Plan Review (DS) — 2026-05-16

## 审查范围

- **目标**: `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- **设计真源**: `docs/host/design.md` §20、§21、§22
- **总控真源**: `docs/host/implementation-control.md` Phase 7
- **参考裁决**: `docs/reviews/host-phase7-design-fix-re-review-controller-adjudication-20260516.md`
- **方法**: adversarial plan review，以设计真源、总控真源与当前代码事实为证据，压测 plan 是否 code-generation-ready 与 implementation-ready

## 已测试假设

| # | 假设 | 结论 |
|---|------|------|
| A1 | Plan 的 slice 切分可独立验证、不跨越治理 owner | 基本成立；S4 略宽(见 F4) |
| A2 | `ResolveWaitRequest` typed outcome envelope 足以替换 `outcome_ref` | 成立 |
| A3 | `observed_at` 的 `datetime` 选择与已有契约一致 | 成立；`ToolAwaitSpec.deadline` 已用 `datetime` |
| A4 | Engine 不能通过 `tool_awaiting`/`run_suspended` 创建 wait state | Plan 正确表述；但新行为规格不足(见 F1) |
| A5 | Wait record schema 与 CAS helpers 可实施 | 成立；但缺失 Run transition helper(见 F3) |
| A6 | `resolve_wait` 幂等语义可测试 | 成立；但 resolved 状态的 different-key 拒绝测试缺失(见 F5) |
| A7 | cancel-vs-resolve first-committer-wins 可测试 | 成立 |
| A8 | `WAIT_LATE_RESULT_REJECTED` schema 完整 | 基本成立；但 idempotency 策略有条件未收敛(见 F6) |
| A9 | Slice 不要求实现 Agent 重新设计契约 | 成立 |
| A10 | Host/Engine 边界不被侵犯 | Plan 正确表述；但 EngineEvent ingest 修改细节不足(见 F1) |

---

## Findings

### F1-未修复-高-EngineEvent TOOL_AWAITING/RUN_SUSPENDED 新行为未收敛到足够具体的实现规格

- **位置**: §3.13 "EngineEvent Awaiting / Suspended Boundary"；P7-S4 exact changes "Update EngineEvent ingest"
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: Plan §3.13 给出三条规则：
  1. Engine event 携带已匹配 accepted refs → "append diagnostic or preview confirmation and return accepted/duplicate"
  2. Engine event 没有匹配 refs → "reject as diagnostic unsupported / stale; it still must not create wait record"
  3. 不得因为迟到 `run_suspended` 而 fail 已进入 `WAITING` 的 Run
  4. 重复 ingest 保持幂等

  但 P7-S4 "exact changes" 只写 "Update EngineEvent ingest for TOOL_AWAITING / RUN_SUSPENDED: matching accepted refs become diagnostic / idempotent confirmation; missing refs do not create wait state and do not fail an already waiting Run."
- **反例/失败场景**: 当前 `engine_ingest.py:717-745` 的 `_diagnostic_then_failed_waiting` 在收到任何 `TOOL_AWAITING`/`RUN_SUSPENDED` Engine event 时，写 diagnostic 后通过 `_close_terminal` 把 Run 收口为 `FAILED`。该行为对每个进入的 Engine event 都生效——无论 ToolRuntime 是否已经 accepted awaiting。若实现 Agent 只按 §3.13 的文字实现两路分支（匹配 refs → diagnostic；不匹配 → reject），但不明确"reject"的具体动作（是只写 diagnostic 不 fail Run？还是返回 rejected？），则：
  - 过度保守：Engine event 先于 ToolRuntime accept 到达时，拒绝并 fail Run → 破坏 Host canonical path。
  - 过度宽松：Engine event 在 Run 已由其他路径 terminal 后到达，写 diagnostic 但不检查 Run 状态 → 脏写 diagnostic。
- **为什么有问题**: 设计真源 `docs/host/design.md` §20 明确：Engine `tool_awaiting`/`run_suspended` 只能携带 accepted refs 作为 diagnostic/idempotent confirmation，不能创建 wait record，不能把 Run 推入 `WAITING`。但当前代码的 `_diagnostic_then_failed_waiting` 直接把每个此类 Engine event 当成 terminal failure trigger。Plan 正确指出了方向变更，但没有给出足以让实现 Agent 直接编码的精确行为矩阵：对于每种 (Run.status, 是否有 accepted refs, event type) 组合，返回什么。
- **直接证据**:
  - `dayu/host/engine_ingest.py:450-465`: `RUN_SUSPENDED`/`TOOL_AWAITING` 当前无条件走 `_diagnostic_then_failed_waiting`
  - `dayu/host/engine_ingest.py:717-745`: `_diagnostic_then_failed_waiting` 调用 `_close_terminal` 把 Run 收口为 FAILED
  - `docs/host/design.md` §20 L2019: "Engine tool_awaiting / run_suspended 不能创建 wait record，不能把 Run 推入 WAITING，不能关闭 Attempt"
- **影响**: 实现 Agent 被迫自行设计 EngineEvent 的分支矩阵，可能写出：Engine event 在 ToolRuntime accept 之前到达时错误 fail Run；或在 Run 已 terminal 后仍追加 diagnostic 造成脏写
- **建议改法和验证点**:
  1. 在 Plan §3.13 补充精确行为表，至少覆盖 (Run.status 为 RUNNING/Wait accepted 前, Run.status 为 WAITING/Wait accepted 后, Run.status 为 terminal, Attempt 不匹配) × (event 有/无 accepted refs) 的组合。
  2. 明确 EngineEvent `TOOL_AWAITING`/`RUN_SUSPENDED` 在任何情况下都不得调用 `_close_terminal` 或等价 terminal closeout。
  3. P7-S4 验证命令中已包含 `test_engine_ingest_mapping.py`，应确保新增用例覆盖上述组合。
- **修复风险**: 低 — 只需补充行为表，不改变架构。
- **严重程度**: 高 — EngineEvent ingest 是 Host/Engine 边界的核心防御面，行为歧义会直接导致 Run 状态机漂移。

### F2-未修复-高-WAITING cancel 路径与现有 cancel 状态机集成点不明确

- **位置**: §3.11 "WAITING Cancel And First-Committer-Wins"；P7-S4 exact changes "Extend cancel_run / cancel_session_runs service path"
- **问题类型**: 不可直接实施 / 状态机漏洞
- **当前写法**: P7-S4 "exact changes": "Extend cancel_run / cancel_session_runs service path to support WAITING Run by cancelling active wait records and setting Run CANCELLED. Preserve existing queued / pre-dispatch / active-worker cancel behavior."
- **反例/失败场景**: 当前 cancel 路径在 `command.py` → `admission.py` → `durable/state.py` 中有明确分支：`QUEUED` 直接 cancel、`STARTING`+pending dispatch 直接 cancel、`RUNNING` 走 `CANCELLING`→`ATTEMPT_CANCELLED`+`RUN_CANCELLED`。WAITING cancel 是这些分支之外的**新分支**，但它复用了部分目标状态（Run CANCELLED，但不创建 ATTEMPT_CANCELLED）。实现 Agent 如果：
  1. 简单地把 WAITING 当成现有某个分支处理（如 QUEUED 分支），会导致不正确的 `ATTEMPT_CANCELLED` 或错误的 status 前置条件。
  2. 在 `cancel_session_runs` 中为 WAITING 写全新路径，但与 `cancel_run` 的 WAITING 路径逻辑不一致。
  3. 不确定是在 `admission.py` 的 cancel service 中加分支，还是在 `run_transition.py` 中加状态 helper。
- **为什么有问题**: Plan 在 §3.11 描述了语义（step 1-7），但在 §5 P7-S4 "exact changes" 中只用一句话概括，没有指定：哪个文件/函数需要加 WAITING 分支、CAS 前置条件是什么、是否需要新的 state helper。对比 P7-S3 对 `resolve_wait` 的 exact changes 有 7 条具体步骤，P7-S4 的 cancel 部分显著欠规格。
- **直接证据**:
  - `docs/host/design.md` §22 L2215-2218: WAITING cancel 语义已定义
  - Plan §3.11 语义完整，但 §5 P7-S4 exact changes 只有 1 行描述
  - 当前 `dayu/host/admission.py` 和 `dayu/host/durable/run_transition.py` 没有 WAITING cancel 分支
  - Plan §4.1 P7-S4 列出 `admission.py` 为 allowed file，备注 "only for public cancel service integration" — 但没有说明具体在哪里加什么
- **影响**: 实现 Agent 在 cancel 路径中自行选择集成点，可能导致：cancel 并发窗口期行为不一致、与 `resolve_wait` 竞态下 first-committer-wins 失效、`cancel_session_runs` 遗漏 WAITING Run
- **建议改法和验证点**:
  1. 在 P7-S4 exact changes 中给出与 P7-S3 同等的步骤级规格：具体哪个文件、哪个函数、CAS 前置条件、调用哪个 state helper。
  2. 明确 `cancel_session_runs` 的 WAITING 分支是委托 `cancel_run` 还是独立实现。
  3. 明确 cancel 后是否需要 `after_commit` hook 通知 poller（§3.11 step 7 已描述语义，但实现锚点未指定）。
  4. 验证：P7-S4 的 `test_wait_cancel_late_result.py` 应包含 `cancel_session_runs` 对 WAITING Run 的覆盖。
- **修复风险**: 低 — cancel 语义已在 design doc 中完整定义，只需 plan 补足实现锚点。
- **严重程度**: 高 — cancel 是 Host 治理的硬正确性路径，实现锚点不清会导致并发行为分歧。

### F3-未修复-高-WAITING→RUNNING 的 Run transition helper 未列入 plan 交付物

- **位置**: §3.7 "Wait Record Schema / Status / CAS" (CAS helpers 列表)；§3.9 step 9 "set Run RUNNING with current new Attempt"
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: §3.7 CAS helpers 列表只包含 8 个 wait record helper（`insert_wait_record` 到 `cancel_active_wait_records_for_run`）。§5 P7-S2 也列出 "Host transaction ... sets Run WAITING and Attempt SUSPENDED atomically" 但未指定用哪个 helper 做 Run transition。
- **反例/失败场景**: `resolve_wait` completed outcome 需要把 Run 从 `WAITING` 转为 `RUNNING`。当前 `dayu/host/durable/state.py` 中的 `start_run` helper 的 CAS 前置条件是 `RunStatus.QUEUED`（见 state.py:1470-1484），不能直接复用。`terminal_run_row` 的 CAS 前置条件虽是 `RUNNING`/`WAITING`，但它是终端收口，不做 WAITING→RUNNING 过渡。若实现 Agent 被迫：
  1. 在 `resolve_wait` pipeline 中内联写 Run row UPDATE → 违反 state helper 封装约定，且容易与现有 `mark_run_started`/`start_run` 语义重复。
  2. 新增一个非标准 helper → 其他 slice 不知道它的存在，后续 phase 可能重复造轮子。
- **为什么有问题**: Plan 在 §4.1 P7-S2/S3 的 allowed files 中都列出了 `dayu/host/durable/run_transition.py`，表明 plan 预见到需要修改 Run transition。但 §3.7 的 helper 列表完全遗漏了 Run 层面的 transition helper，只列了 wait record helper。这违反 design doc §20 L2105：wait record resolution 与 RUN_STARTED、new Attempt、dispatch record 必须在同一事务中收口——该事务需要同时操作 wait record 表、Run 表、Attempt 表、dispatch record 表，但 plan 只给了 wait record 的 helper。
- **直接证据**:
  - `dayu/host/durable/state.py:1463-1484`: `start_run` CAS 前置条件是 `QUEUED`，不能用于 `WAITING`→`RUNNING`
  - `dayu/host/durable/state.py:1725-1782`: `terminal_run_row` 处理 `RUNNING`/`WAITING`→终态，但不处理 `WAITING`→`RUNNING`
  - Plan §3.7 helper 列表: 8 个 helpers，全部作用于 wait record 表
  - Plan §4.1 P7-S3 allowed files: `dayu/host/durable/run_transition.py` — 表明需要 Run transition 变更但 plan 未指定
- **影响**: 实现 Agent 自行设计 WAITING→RUNNING transition，可能与现有 `start_run`/`mark_run_started` 产生语义冲突或代码重复；`RUN_STARTED(start_reason=resume)` 的 event 写入顺序可能不一致。
- **建议改法和验证点**:
  1. 在 §3.7 或新增 §3.15 中列出所需的 Run transition helpers：至少包括 `resume_run_from_waiting(transaction, run_id, new_attempt_id, started_event_refs)` 或等价 helper。
  2. 明确该 helper 的 CAS 前置条件（Run.status=`WAITING`，无其他 active wait 或当前 wait 已 resolved）、写入字段和返回类型。
  3. 确认 `terminal_run_row` 用于 WAITING→FAILED/LOST 场景时是否需要适配（当前已预留 WAITING 源状态，大概率可直接使用）。
  4. P7-S3 测试应包含 WAITING→RUNNING transition 的 CAS_LOST 场景（另一个并发 resolution 已抢先 CAS）。
- **修复风险**: 低 — Run transition 模式已在 Phase 3/5/6 稳定，只需按同模式新增。
- **严重程度**: 高 — `resolve_wait` 的核心状态迁移无 helper 锚点，实现 Agent 被迫做状态机设计决策。

### F4-未修复-中-Poller 生命周期与并发模型未指定

- **位置**: §3.12 "Poll / Manual Adapter"；P7-S4 exact changes "Add minimal poller / adapter protocol"
- **问题类型**: 并发恢复风险 / 不可直接实施
- **当前写法**: Plan §3.12 给出协议定义（`WaitPollAdapter` protocol、`WaitPollResult` 类型）和行为规则（何时调用 `resolve_wait`、cancelled 时停止），但没有指定 poller 的运行模型。
- **反例/失败场景**:
  1. Poller 作为 asyncio task 在 Host 的 event loop 中运行 → 如果 Host 是多线程的，poller 需要线程安全。
  2. Poller 在独立线程中运行 → 调用 `resolve_wait`（需要 Host handle / transaction）时的跨线程安全性未定义。
  3. Poller 随 Host startup 自动启动 → 但在 recovery phase (Phase 11) 之前，Host restart 后 poller 如何发现已有的 active wait records 未定义。
  4. Host graceful shutdown 时，poller 的停止顺序未定义 — 如果 poller 正在 `resolve_wait` 事务中而 Host 关闭数据库连接，可能导致事务悬挂。
- **为什么有问题**: 设计真源 `docs/host/design.md` §20 L2104 明确 "wait poller 是 background runtime 中的 trigger / adapter"，但没有进一步指定 background runtime 的生命周期管理。Plan 作为 handoff document，需要至少为第一版指定：启动时机、停止时机、与 Host transaction 的交互约束。
- **直接证据**:
  - `docs/host/design.md` §20 L2104: "wait poller 是 background runtime 中的 trigger / adapter"
  - Plan §3.12: 只描述了协议和行为规则，无生命周期管理
  - Plan §4.1 P7-S4 allowed files 中没有看到 poller lifecycle manager 文件
  - Plan §11 Residual Risks: "Recovery scan for existing WAITING Runs after Host restart should restore adapter observation" 说明 restart 恢复是已知问题但推迟
- **影响**: 实现 Agent 自行选择 poller 运行模型，可能导致：与 Phase 11 recovery 的集成冲突、跨线程 SQLite 访问问题、shutdown 时资源泄漏
- **建议改法和验证点**:
  1. Plan §3.12 或新增子节明确第一版 poller 运行模型：建议为 Host 内部的 asyncio task，单线程内通过 Host handle 调用 `resolve_wait`。
  2. 明确 poller 的启动在 Host composition root 的哪个位置，停止在 Host shutdown 的哪个步骤。
  3. 明确第一版不处理 Host restart 后的 poller 恢复（已在 §11 Residual Risks 中记录），但必须在 P7-S4 的 poller 中留有恢复入口或至少注释标记。
  4. 测试应包含 poller 在 cancelled wait 后停止的验证。
- **修复风险**: 低至中 — 只需选择合理的第一版模型并记录，不涉及架构变更。
- **严重程度**: 中 — 不影响单个 `resolve_wait` 调用的正确性，但影响 Host 运行期稳定性与 Phase 11 集成。

### F5-未修复-中-resolved/failed wait 对 different key resolve 的拒绝测试缺失

- **位置**: §3.9 step 8 "If wait record status is resolved / failed, allow only idempotent replay of existing resolution; different key is INVALID_STATE"；P7-S3 tests
- **问题类型**: 测试缺口
- **当前写法**: P7-S3 tests 包含：
  - "Same (wait_id, idempotency_key) + same outcome returns existing RunSnapshot"
  - "Same key + different outcome raises IDEMPOTENCY_CONFLICT"
  但**没有**包含：different key 对已 resolved/failed wait 的 `INVALID_STATE` 拒绝。
- **反例/失败场景**: 外部系统（如 poll adapter 与 manual operator 同时）用不同 `idempotency_key` 对同一个已 resolved 的 wait 调用 `resolve_wait`。若实现 Agent 漏掉了这个检查，wait record 的 `resolved` 状态可能被第二次 resolution 覆盖，产生第二份 canonical tool result 和第二个 resume Attempt。
- **为什么有问题**: 设计真源 `docs/host/design.md` §20 L2110: "已 resolved 的 wait record 只允许幂等重放既有结果，不允许第二次 resolution。" Controller adjudication 也确认 `resolve_wait` idempotency 必须逐项覆盖。
- **直接证据**:
  - Plan §3.9 step 8 明确语义
  - P7-S3 tests 列表缺少此场景
  - `docs/host/design.md` §20 L2110
- **影响**: 测试不覆盖可能导致实现遗漏，在生产中 different-key 二次 resolution 绕过 first-committer-wins 防护
- **建议改法和验证点**: 在 P7-S3 tests 中新增：对已 resolved 的 wait，用新的不同 `idempotency_key` 调用 `resolve_wait`，期望 `HostApiErrorCode.INVALID_STATE`，且不产生新 Attempt、不追加 canonical facts。
- **修复风险**: 低 — 增加一个测试用例。
- **严重程度**: 中 — 是防重复 resolution 的关键防线，但可以通过实现 Agent 常识性防御部分缓解。

### F6-未修复-中-迟到 diagnostic 的 idempotency 策略未收敛

- **位置**: §3.10 "EventLog Facts" 最后一段；P7-S4 stop condition
- **问题类型**: open question 未收敛
- **当前写法**: "Late diagnostic event ids must be deterministic for the same rejected wait result so duplicate retries do not create unbounded diagnostics. If deterministic duplicate detection cannot be implemented without a separate idempotency record, use the same wait_resolution idempotency scope for rejected-late diagnostics."
- **反例/失败场景**: Poll adapter 在 wait 已被 cancel 后，用相同的 `idempotency_key` 重试 `resolve_wait`，每次都触发 `WAIT_LATE_RESULT_REJECTED` diagnostic。如果 diagnostic 的 event_id 不全等且没有 idempotency guard，每次重试都会在 EventLog 中追加一条新 diagnostic event。无限重试 → 无限 diagnostic → EventLog 膨胀。
- **为什么有问题**: Plan 自己承认这是潜在问题（"If deterministic duplicate detection cannot be implemented..."），但把决策推迟到实现时。P7-S4 stop condition 也写了 "If deterministic late diagnostic idempotency conflicts with existing EventLog id strategy, stop for controller decision." 这等于告诉实现 Agent：遇到问题就停。更好的做法是 plan 阶段就做出选择，避免实现到一半才发现卡点。
- **直接证据**:
  - Plan §3.10 L280-281
  - Plan §9 stop condition: "Late diagnostic idempotency cannot be made bounded/deterministic."
  - `docs/host/design.md` §20 L2111-2116: 要求 diagnostic event 但不指定 idempotency 实现策略
- **影响**: 实现到 P7-S4 时可能触发 stop condition，导致返工；或实现 Agent 强行绕过导致 EventLog 膨胀
- **建议改法和验证点**: 在 plan 中做出明确选择：建议第一版使用 `wait_resolution` 的 idempotency scope（`wait_id` + `idempotency_key`），同一个被拒绝的 late result 重试时走 `resolve_wait` 的 idempotency 检查，返回既有 diagnostic refs 而不追加新 event。如果这个方案有技术障碍，在 plan 中提前说明并给出替代方案。
- **修复风险**: 低 — 二选一的工程决策。
- **严重程度**: 中 — P7-S4 stop condition 已有兜底，但 plan 阶段收敛可避免浪费实现时间。

---

## Open Questions

1. **`HostPayloadRef` 从 `tool_runtime.py` 移到 `api.py` 后，ToolRuntime 的现有调用方是否需要同步更新 import？** Plan §3.2 要求移动，但未说明 ToolRuntime 内部对 `HostPayloadRef` 的引用如何处理。影响范围小（仅 import 路径变更），但实现 Agent 需要显式指导。
2. **`_event_payload.py` 的变更边界不清。** P7-S2 和 P7-S4 都列出 `_event_payload.py` 为 allowed file，但 exact changes 中没有描述该文件的具体变更。例如新增 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、`RESUME_REQUESTED` 等 event 的 payload 构造 helper 应该放在哪里？建议 plan 明确归属。
3. **`ResolveWaitRequest.context` 字段的语义。** 当前 `ResolveWaitRequest` 有 `context: HostCallContext` 字段，Plan §3.2 的描述中没有提及 `context` 字段被保留还是删除。建议明确：保留作为调用上下文，或删除并改为从 `wait_id` 反查 Run/Session。

---

## Residual Risks (Plan 已记录，确认可接受)

| 风险 | Plan 位置 | 评估 |
|------|-----------|------|
| Callback 产品化推迟 | §11 | 可接受；adapter contract 已预留 |
| 外部 job physical cancel 为 best-effort | §11 | 可接受；不影响 Host terminal correctness |
| Cross-process duplicate governance 仍限 Phase 6 in-memory | §11 | 可接受；已在 Phase 6 风险中 |
| Recovery scan 恢复 adapter observation 推迟到 Phase 11 | §11 | 可接受；已在 plan non-goals 中 |
| Tool trace projection 未实现 | §11 | 可接受；diagnostic events 已为后续 phase 提供输入 |

---

## Final Plan Review Conclusion

**结论: FAIL**

Plan 在 typed outcome envelope、wait record schema、`resolve_wait` pipeline 语义和 slice 整体结构上已达到较高的具体程度，大部分 controller 硬要求已逐项覆盖。但以下三个高严重度 findings 阻止 plan 进入 code-generation-ready：

1. **F1**: EngineEvent `TOOL_AWAITING`/`RUN_SUSPENDED` 新行为未收敛到精确行为矩阵 — 实现 Agent 被迫自行设计 Host/Engine boundary 防御逻辑。
2. **F2**: WAITING cancel 路径与现有 cancel 状态机的集成锚点缺失 — 实现 Agent 被迫自行选择 cancel 注入点，可能导致并发行为分歧。
3. **F3**: WAITING→RUNNING 的 Run transition helper 未列入交付物 — `resolve_wait` 的核心状态迁移缺少 state helper 契约。

三个 findings 的修复风险均为**低**：只需补充规格表、步骤描述和 helper 列表，不涉及架构变更或返工。

建议 plan 修复后重新提交 plan review，预期可在一个 review round 内收敛到 PASS。
