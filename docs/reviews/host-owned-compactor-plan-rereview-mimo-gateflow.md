# Host-owned compactor plan re-review (MiMo, Gateflow)

## Gate

- Gate: plan re-review after plan fix.
- Work unit: Host-owned LLM context compactor public opener contract.
- Source plan: `docs/host/host-owned-compactor-plan.md` (fix 后版本 + §0 source-of-truth 补丁).
- Fix artifact: `docs/reviews/host-owned-compactor-plan-fix-codex-gateflow.md`.
- Source review artifact: `docs/reviews/host-owned-compactor-plan-review-mimo-gateflow.md`.
- Parallel review artifact: `docs/reviews/host-owned-compactor-plan-review-ds-gateflow.md`.

## Re-review scope

验证 controller-accepted 5 项 fix 是否在 plan 中实际落地，以及 §0 source-of-truth 补丁是否引入新问题。

## 结论：PASS

所有 5 项 accepted fix 均已在 plan 中明确落地，plan 现在 implementation-ready。

---

## Accepted Fix Items 逐项验证

### Fix Item 1: HostEvent exposure/mapping explicit, no new HostEventKind

**状态：FIXED**

**Plan 证据**：

- §3.6 "HostEvent 映射" 段（plan line 202-207）：明确声明"不新增 `HostEventKind`"，逐条列出映射关系：
  - `CONTEXT_COMPACTION_REQUESTED` -> `HostEventKind.PROGRESS`
  - `CONTEXT_COMPACTED` -> `HostEventKind.PROGRESS`
  - `CONTEXT_COMPACTION_FAILED` -> `HostEventKind.PROGRESS`（Run 终态由后续 `RUN_FAILED` 映射）
  - `CONTEXT_COMPACTION_ATTEMPT_REJECTED` -> committed EventLog canonical fact，只能按现有投影暴露为 `HostEventKind.PROGRESS` 或 `HostEventView(event_class=canonical_fact, event_type=...)`
  - Engine runner 内部 HTTP retry 不 emit HostEvent
- Slice 4 step 10（plan line 332）重复确认保守映射策略。

**验证**：mapping 完整覆盖所有 compact EventLog facts，实现者无需自行发明新 HostEventKind 值。与 `design.md:2616` 对齐。

---

### Fix Item 2: CONTEXT_COMPACTION_ATTEMPT_REJECTED payload builder/validator in Slice 4 scope

**状态：FIXED**

**Plan 证据**：

- Slice 4 修改范围（plan line 314）：明确列出 `dayu/host/context_events.py` 和 `tests/host/test_context_compact_events.py` 在 scope 内。
- Slice 4 step 7（plan line 329）：定义 payload 语义——operation id、attempt number、failure category、repairable、runner attempt summary refs、quality / parse / budget diagnostic refs、next policy decision。
- Slice 4 step 8（plan line 330）：要求新增 `build_context_compaction_attempt_rejected_payload(...)` 和 `validate_context_compaction_attempt_rejected_payload(...)`，给出完整字段列表和类型约束。
- Slice 4 step 9（plan line 331）：要求在 `test_context_compact_events.py` 覆盖成功路径和多种失败路径（缺必填字段、非法 attempt_number、空 diagnostic ref、非法 budget）。
- §6.2 测试矩阵（plan line 445-447）：列出 `test_compaction_attempt_rejected_payload_requires_positive_attempt_number`、`test_compaction_attempt_rejected_payload_requires_diagnostic_refs`、`test_compaction_attempt_rejected_maps_to_progress_host_event`。

**验证**：builder/validator 的 scope、字段定义、测试覆盖均在 Slice 4 中明确，不依赖实现者自行推断。

---

### Fix Item 3: no-network LLMContextCompactor test seam is concrete, no expanded public constructor

**状态：FIXED**

**Plan 证据**：

- Slice 2 测试实现要求（plan line 275-278）：
  - "LLMContextCompactor public 构造签名不得为了测试扩展 runner / callback seam"
  - 指定 monkeypatch 目标：`dayu.host.llm_compaction.run_agent_and_wait`
  - fake `run_agent_and_wait` 必须断言 `RunnerSpec.max_retries` 未被改写、`runner_options` 一致、`tool_schemas=()` 且 policy 禁止工具调用
  - runner failure 传播测试断言 compactor 不做内部 semantic repair loop、不吞掉 runner 层失败
- §7 handoff summary（plan line 484）再次确认 monkeypatch 目标和断言边界。

**验证**：monkeypatch 目标具体（模块级函数 `dayu.host.llm_compaction.run_agent_and_wait`），断言维度完整（runner spec/options 透传、tool disabled、failure 传播），且明确禁止扩展构造签名。解决了原 review 中 R6 的"测试方式未具体化"问题。

---

### Fix Item 4: Slice 1-4 coupling as one work unit / PR readiness boundary

**状态：FIXED**

**Plan 证据**：

- Slice 3 step 7（plan line 299）："Slice 1、2、3 可以作为 Gateflow 本地 slice checkpoint 提交，但只属于同一个 work unit 的中间状态；不得把它们描述或发布为可单独合并的 public contract 状态。Slice 1、2、3、4 必须在同一个 implementation PR readiness boundary 内连续完成。"
- §5.1 风险（plan line 392）："Slice 1-4 可以形成本地 checkpoint，但只有全部完成并验证后才构成 PR-ready public opener contract。"
- §7 handoff summary（plan line 486）："Slice 1-4 只能作为同一 PR readiness boundary 交付。"

**验证**：plan 明确区分了"本地 Gateflow checkpoint"（允许）和"可单独合并的 PR"（不允许），解决了原 review 中 R5 的 coupling 问题。

---

### Fix Item 5: Slice 4 step 1 preserves only internal compactor source seam, not control flow

**状态：FIXED**

**Plan 证据**：

- Slice 4 step 1（plan line 320）明确写出：
  - "这里的'保持'只约束 compactor 来源，不表示 dispatch / ingest 的 compact 控制流保持不变"
  - "本 Slice 必须按 step 2-3 重构 request write、transaction 外 LLM call、result recheck/write 三段"

**验证**：plan 消除了原 review 中发现的 step 1 与 step 2-3 的表述矛盾。step 1 现在只约束 compactor 注入来源（Host internal），同时显式声明控制流必须按 step 2-3 重构。Implementation agent 不会误判为"不需要改 dispatch/ingest 方法结构"。

---

## Residual Risks

以下为 fix artifact 提出的 residual risks，均为实现阶段关注项，不阻塞 plan 批准：

| ID | 描述 | 级别 |
|----|------|------|
| FR-1 | Reactive compact 三段拆分的 `EngineEventIngestor` 方法签名变化——plan 留给实现细节 | LOW |
| FR-2 | `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的 `event_class` 必须是 `CANONICAL_FACT`，不得记录敏感 prompt/provider payload | LOW |
| FR-3 | HostEvent progress mapping 依赖现有 `read_api` 投影行为，不得新增 attempt-specific HostEventKind | LOW |

---

## 最终状态映射

| Accepted Item | 状态 | Plan 落地位置 |
|--------------|------|-------------|
| 1. HostEvent mapping explicit | FIXED | §3.6 (line 202-207), Slice 4 step 10 (line 332) |
| 2. ATTEMPT_REJECTED builder/validator in Slice 4 | FIXED | Slice 4 修改范围 (line 314), step 7-9 (line 329-331), §6.2 (line 445-447) |
| 3. No-network test seam concrete | FIXED | Slice 2 测试要求 (line 275-278), §7 (line 484) |
| 4. Slice 1-4 PR readiness boundary | FIXED | Slice 3 step 7 (line 299), §5.1 (line 392), §7 (line 486) |
| 5. Step 1 source seam only, not control flow | FIXED | Slice 4 step 1 (line 320) |

---

## Stop Status

- 代码实现：未开始。
- 设计文档：未编辑。
- Commit / push / PR：未执行。
- 停止原因：re-review artifact 完成，所有 accepted fix items 确认落地。
