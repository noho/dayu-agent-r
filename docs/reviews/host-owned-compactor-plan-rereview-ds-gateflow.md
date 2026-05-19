# Host-owned compactor plan re-review — AgentDS (Gateflow, second independent re-review)

## Gate

- Gate: parallel plan re-review after plan fix.
- Work unit: Host-owned LLM context compactor public opener contract.
- Source plan: `docs/host/host-owned-compactor-plan.md`
- Fix artifact: `docs/reviews/host-owned-compactor-plan-fix-codex-gateflow.md`
- Source review artifact (DS): `docs/reviews/host-owned-compactor-plan-review-ds-gateflow.md`
- Parallel review artifact (MiMo): `docs/reviews/host-owned-compactor-plan-review-mimo-gateflow.md`
- Reviewer role: second independent re-review agent; not controller. No implementation, no plan edit, no commit, no push, no PR.

## 审查范围

验证 controller-accepted fix items 是否已正确收口；同时验证 controller 对 plan §0 的最新编辑（design.md 真源声明）。不引入与这些 items 无关的新 scope，除非发现阻塞级问题。

---

## 1. 逐项验证

### Item 1: DS R1 — HostEvent 暴露/映射显式化，不要求新增 HostEventKind

**状态: FIXED**

**证据（plan §3.6 "HostEvent 映射" 段）:**

> HostEvent 映射：不新增 HostEventKind。当前 public contract 只有 PROGRESS、SUCCEEDED、FAILED、CANCELLED，且 dayu.host.read_api._host_event_from_row(...) 只把 RUN_SUCCEEDED / RUN_FAILED / RUN_CANCELLED 映射为 terminal HostEvent，其余 EventLog row 统一映射为 HostEventKind.PROGRESS。

逐事件映射完整且保守：

| EventLog fact | HostEvent 映射 | 依据 |
|---|---|---|
| `CONTEXT_COMPACTION_REQUESTED` | `PROGRESS` | 与现有非 terminal EventLog row 一致 |
| `CONTEXT_COMPACTED` | `PROGRESS` | 同上 |
| `CONTEXT_COMPACTION_FAILED` | `PROGRESS` | 若导致 Run 失败，由后续 `RUN_FAILED` 映射为 `FAILED` |
| `CONTEXT_COMPACTION_ATTEMPT_REJECTED` | `PROGRESS`（若进入 session watch） | committed canonical fact，不是 diagnostic-only |
| Engine runner HTTP retry | 不 emit HostEvent | 只进 runner log / aggregated diagnostic |

Plan §3.6 末尾明确：
> 不得新增 attempt-specific HostEventKind，也不得伪装成 terminal failure

实现不需要发明新 `HostEventKind` 值，只复用现有 `PROGRESS` / `SUCCEEDED` / `FAILED` / `CANCELLED`。映射表可逐行对应当前 `_host_event_from_row` 的保守 fallback 语义。

---

### Item 2: DS R3 — CONTEXT_COMPACTION_ATTEMPT_REJECTED payload builder/validator 及测试显式进入 Slice 4 scope

**状态: FIXED**

**证据（plan Slice 4 修改范围）:**

> - 必须在 dayu/host/context_events.py 新增 CONTEXT_COMPACTION_ATTEMPT_REJECTED event type、payload builder 与 validator；同步更新 tests/host/test_context_compact_events.py。

**证据（plan Slice 4 step 8）:**

> 在 dayu/host/context_events.py 增加 build_context_compaction_attempt_rejected_payload(...) 与 validate_context_compaction_attempt_rejected_payload(...)，并复用本模块现有 JSON helper 风格。payload 必填字段为 operation_id、attempt_number、failure_category、repairable、runner_attempt_summary_refs、diagnostic_refs、next_policy_decision、budget_after_attempted_compact；attempt_number 为正整数，runner_attempt_summary_refs 与 diagnostic_refs 为非空文本列表，budget_after_attempted_compact 可为非负整数或 None。

**证据（plan Slice 4 step 9）:**

> 更新 tests/host/test_context_compact_events.py，覆盖 attempt rejected payload builder 成功路径、缺必填字段、attempt_number 为 0 / bool / 非整数、空 diagnostic ref、非法 budget 的失败路径。

**证据（plan §6.2 验证矩阵）:**

> - test_compaction_attempt_rejected_payload_requires_positive_attempt_number
> - test_compaction_attempt_rejected_payload_requires_diagnostic_refs
> - test_compaction_attempt_rejected_maps_to_progress_host_event

文件路径、函数签名、payload 字段、校验规则和测试用例命名均显式给出。

---

### Item 3: DS R6 — no-network LLMContextCompactor test seam 具体化，不扩展 public constructor seam

**状态: FIXED**

**证据（plan Slice 2 测试实现要求）:**

> - 不引入网络 pytest。
> - LLMContextCompactor public 构造签名不得为了测试扩展 runner / callback seam；优先在 tests/host/test_llm_compaction.py 通过 monkeypatch dayu.host.llm_compaction.run_agent_and_wait 做 no-network 单元测试。

monkeypatch 目标为模块内部符号 `dayu.host.llm_compaction.run_agent_and_wait`，不是 public constructor 参数。

**证据（plan Slice 2 — monkeypatch fake 断言要求）:**

> monkeypatch 的 fake run_agent_and_wait 必须接收 AgentRunRequest，记录并断言 request 内的：
> - runner_spec 是构造时传入的同一个 RunnerSpec，尤其 RunnerSpec.max_retries 未被 compactor 改写；
> - runner_options 是构造时传入的 RunnerCallOptions；
> - tool_schemas=() 且 policy 禁止工具调用。

**证据（plan Slice 2 — runner failure 传播测试）:**

> runner failure 传播测试应让 fake run_agent_and_wait 抛出或返回 failed outcome，并断言 LLMContextCompactor.compact(...) 不在内部做 semantic repair loop、不吞掉 runner 层失败；semantic repair 只在 Slice 4 的 Host compaction operation 测试中覆盖。

test seam 路径、fake 注入方式、断言点和边界（compactor 不做 semantic repair）均具体化。`LLMContextCompactor.__init__` 不新增任何仅用于测试的参数。

---

### Item 4: DS R5 / controller decision — Slice 1-4 coupling 明确为一个 work unit / PR readiness boundary

**状态: FIXED**

**证据（plan Slice 3 step 7）:**

> Slice 1、2、3 可以作为 Gateflow 本地 slice checkpoint 提交，但只属于同一个 work unit 的中间状态；不得把它们描述或发布为可单独合并的 public contract 状态。Slice 1、2、3、4 必须在同一个 implementation PR readiness boundary 内连续完成，不接受"public API 已切、Host-owned compactor 已接线，但真实 LLM compact 仍可能在 Host write transaction 内执行"的可合并中间态。

**证据（plan §5.1 风险）:**

> Slice 1-4 中间态不可发版：Slice 1-4 可以形成本地 checkpoint，但只有全部完成并验证后才构成 PR-ready public opener contract。中途若只完成 API 收口与 Host-owned compactor 接线，而未完成 transaction 外 LLM call 拆分，真实 provider compact 仍可能持有 write transaction。

**证据（plan §7 handoff step 4）:**

> Slice 1-4 只能作为同一 PR readiness boundary 交付。

允许本地 Gateflow checkpoint（每个 slice 后提交），但 PR-ready 边界固定在 Slice 1-4 全部完成后。耦合关系清晰，不存在模糊"可择机发版"表述。

---

### Item 5: MiMo residual — Slice 4 step 1 明确只保留 internal compactor source seam，不保留 dispatch/ingest 控制流

**状态: FIXED**

**证据（plan Slice 4 step 1）:**

> 保持 compactor source seam 为 Host internal：HostDispatchScheduler 和 EngineEventIngestor 只能从 internal context_compactor 取 compactor，compactor 来源由 Slice 3 的 Host-owned 注入链提供。这里的"保持"只约束 compactor 来源，不表示 dispatch / ingest 的 compact 控制流保持不变；本 Slice 必须按 step 2-3 重构 request write、transaction 外 LLM call、result recheck/write 三段。

关键区分显式写出：
- "保持" = compactor 实例来源不变（仍是 internal `context_compactor`，由 Slice 3 注入）;
- "不表示控制流保持不变" — 方法内部必须拆成三段。

消除了原 MiMo gateflow review 发现的 "step 1 暗示不改方法结构 vs step 2-3 要求三段拆分" 的矛盾。implementation agent 不会误读为"不需要改 dispatch/ingest 方法结构"。

---

### Item 6 (追加): Controller 直接编辑 — plan §0 design.md 真源声明

**状态: VERIFIED — 不引入新问题，加强 plan 治理安全性**

**变更内容（plan §0 新增段落）:**

> `docs/host/design.md` 是本 work unit 的设计真源。本 plan 只把 design 中已冻结的 Host-owned compactor public opener contract 拆成可执行实现切片；当 plan 与 design 发生冲突时，以 `docs/host/design.md` 为准，implementation 必须先回到 controller 处理设计冲突，不能自行按 plan 覆盖 design。

**真源关切的解决验证:**

| 检查项 | 结果 |
|--------|------|
| 真源文档显式声明 | `docs/host/design.md` 明确指定为 work unit 设计真源 |
| Plan 角色限定 | plan 只是 decomposer，不取代 design |
| 冲突处理路径 | plan/design 冲突 -> 回到 controller，禁止 implementation 自行覆盖 design |
| 与现有 plan 约束兼容 | 不矛盾。plan 本身 §3.6 已引用 `_host_event_from_row` 代码事实作为证据，§1 泄露点清单已引用具体代码路径；新增声明补充了"当表述不一致时以 design 为准"的治理规则 |

**是否引入新问题:**

无。该声明是纯治理约束，不改变 plan 中的任何 slice 步骤、文件清单、测试要求或架构边界。它只增加了一条冲突升级路径——当 implementation 发现 plan 与 design 不一致时，必须回到 controller 而不是自行裁决。这是 defensive governance，符合 `CLAUDE.md` 的"质疑用户给定路径"和"最佳实践优先"纪律。

**与其他 review artifact 的关联:**

MiMo gateflow review §7.1 曾发现 plan 内部表述矛盾（Slice 4 step 1 vs step 2-3），已在 plan fix 中收口。新增的真源声明进一步加强了此类场景的防护：即使未来出现 plan 内部矛盾未被 review 捕获，implementation agent 也能以 `design.md` 为真源回到 controller 处理，不会自行按 plan 覆盖 design。

---

## 2. 整体评估

### 2.1 Plan 是否 implementation-ready

**是。** 五个 accepted fix items 全部收口，无残留歧义。Plan 现在包含：

- 逐事件的 HostEvent 保守映射，不新增 HostEventKind；
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的显式 builder/validator 签名、字段约束和测试覆盖；
- no-network monkeypatch test seam 的具体注入符号和断言边界；
- Slice 1-4 PR readiness boundary 的不可分开发版的明确约束；
- Slice 4 step 1 的 source seam vs control flow 的显式区分。

### 2.2 是否有非阻塞但值得注意的 residual risk

**R-rereview-1 [LOW] — Reactive compact 三段拆分的 `EngineEventIngestor` pending protocol**

Plan Slice 4 step 3 要求 reactive compact 拆成三段，但未写出 `EngineEventIngestor` 的方法如何返回 compact pending 标识让调用方在 transaction 外执行 LLM call。这已在 DS 原审（R2）和 MiMo gateflow 审（R-1）中标记。fix artifact 将其列为 "residual risk for implementation review"，定位正确——Slice 4 的测试要求（`test_reactive_compaction_calls_llm_outside_write_transaction`）会在实现时自然暴露具体交互形状，不阻塞 plan 批准。

**R-rereview-2 [LOW] — EventLog `event_class` 确认**

Plan 明确 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 是 "committed EventLog canonical fact"，但未写出 payload 中 `event_class` 的具体值。当前 codebase 中 `context_events.py` 的 `build_context_compaction_requested_payload` 使用 `CANONICAL_FACT`。实现时应确认 attempt rejected payload 也使用 `CANONICAL_FACT`，而非 `DIAGNOSTIC`。这是一个实现细节，不阻塞 plan 批准。

### 2.3 是否有阻塞级新问题

**无。** 经过完整再审查，fix 后的 plan 不引入新的阻塞级遗漏、矛盾或不一致。

---

## 3. 最终状态映射

| Item | 描述 | 状态 |
|------|------|------|
| DS R1 | HostEvent 映射显式，不新增 HostEventKind | **FIXED** |
| DS R3 | ATTEMPT_REJECTED payload builder/validator + 测试在 Slice 4 scope | **FIXED** |
| DS R6 | no-network test seam 具体，不扩展 public constructor | **FIXED** |
| DS R5 | Slice 1-4 耦合明确为一个 PR readiness boundary | **FIXED** |
| MiMo residual | Slice 4 step 1 只保留 source seam，不保留控制流 | **FIXED** |
| Controller edit | §0 design.md 真源声明 — 不引入新问题，加强治理安全性 | **VERIFIED** |

## 4. 结论

**PASS.** 所有 controller-accepted fix items (DS R1/R3/R5/R6, MiMo residual) 均已正确收口；controller 对 §0 的 design.md 真源声明编辑加强治理安全性，不引入新问题。Plan 当前为 implementation-ready。

两个 LOW 级 residual risks (R-rereview-1 reactive pending protocol, R-rereview-2 EventLog event_class) 不阻塞实现启动，应在 Slice 4 实现 review 时由 implementation reviewer 确认。
