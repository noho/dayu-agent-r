# WU-CM-15 Aggregate Deepreview

## Scope

- **Mode**: current changes (aggregate deepreview, deepreview skill)
- **Branch**: `phase/wu-cm-15`
- **Base**: `0439cd80` (WU-CM-13/14 Conversation Memory compact continuity)
- **HEAD**: `572a88df` (gateflow: accept WU-CM-15 smoke coverage)
- **Uncommitted**: `docs/host/issues-implementation-control.md` (gate 从 `accepted-slice` 更新为 `aggregate-review`)
- **Output file**: `docs/reviews/deepreview-wu-cm-15-aggregate-ds-20260620.md`
- **Timestamp**: 2026-06-20 11:57:46 CST
- **Reviewer role**: AgentDS (aggregate deepreview gate)
- **Included scope**:
  - `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md` (plan artifact)
  - `docs/reviews/plan-review-20260620-102108.md` (AgentMiMo plan review)
  - `docs/reviews/plan-review-20260620-102145.md` (AgentDS plan review)
  - `docs/reviews/plan-review-20260620-102923.md` (AgentMiMo plan re-review)
  - `docs/reviews/plan-review-20260620-102930.md` (AgentDS plan re-review)
  - `docs/reviews/wu-cm-15-plan-fix-codex-20260620.md` (plan fix)
  - `docs/reviews/wu-cm-15-plan-review-adjudication-20260620.md` (plan review adjudication)
  - `docs/reviews/wu-cm-15-implementation-codex-20260620.md` (implementation artifact)
  - `docs/reviews/code-review-20260620-112127.md` (AgentDS code review #1)
  - `docs/reviews/code-review-20260620-112301.md` (AgentMiMo code review #2)
  - `docs/reviews/wu-cm-15-code-review-adjudication-20260620.md` (code review adjudication)
  - `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md` (code review fix)
  - `docs/reviews/code-review-20260620-115326.md` (AgentMiMo focused re-review)
  - `docs/reviews/code-review-rereview-ds-20260620.md` (AgentDS focused re-review)
  - `docs/reviews/wu-cm-15-code-review-rereview-adjudication-20260620.md` (re-review adjudication)
  - `utils/smoke_host_public_conversation_memory_scenarios.py` (smoke script, +1721 lines)
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` (assembly tests, +327 lines)
  - `tests/README.md` (+1 line)
  - `docs/host/issues-implementation-control.md` (control doc, WU-CM-15 section 及 gate 字段)
- **Excluded scope**: `dayu/` production code (未修改，验证通过); GitHub Issues/PRs (WU-CM-15 无对应 GitHub Issue); `docs/host/design.md` / `docs/engine/design.md` (未修改，仅作为 references)
- **Parallel review coverage**:
  - Agent 1: Plan artifact + plan reviews + plan fix + plan adjudication (7 files)
  - Agent 2: Smoke script + assembly tests (2 files, full read)
  - Agent 3: Code review #1/#2 + fix + re-reviews + adjudications (8 files, 完整 finding lifecycle 追踪)
  - Agent 4: Control doc + tests/README.md + README trigger rules (4 files)
  - Main reviewer: synthesis, de-duplication, severity adjudication, cross-verification of conflicting conclusions
- **Not-covered areas**: `docs/host/design.md` / `docs/engine/design.md` 的 section title 映射未被逐节校验（仅在 plan review 层检查了 forbidden section title strings 的引用一致性）

## Gate Goal

WU-CM-15 的目标是：只增加 public smoke 覆盖 reactive compact 路径和 deterministic compact-failure fallback 路径，不改 Host/Engine production contract/schema，保持 memory-compact strict proactive accepted semantics。

本次 aggregate deepreview 的裁决目标：

- **PASS**：如果无 correctness / stability / maintainability blocker，所有 medium/low/info findings 均已记录且可追溯。
- **BLOCK**：如果存在 blocker-level finding 需要修复后才能进入 final closeout / draft PR gate。

---

## Findings

### 1-未修复-中-Reactive acceptance helper 不检查 proactive compact 零值，suite isolation 语义不完整

- **入口/函数**: `_assert_reactive_compact_acceptance` (line 3573)
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:3573-3629`
- **输入场景**: 若真实运行环境（非 deterministic stub）因 policy 变更、config drift 或 future Host 内部行为变化而同时触发 proactive compact 和 reactive compact，例如 `requested_proactive=1, failed_proactive=1` 伴随 `requested_reactive=1, compacted_reactive=1`。
- **实际分支**: `_assert_reactive_compact_acceptance` 只检查 `requested_reactive >= 1`、`compacted_reactive >= 1`、`failed_reactive == 0`，完全不检查 `requested_proactive`、`compacted_proactive`、`failed_proactive`。
- **预期行为**: reactive suite 的语义应是 "仅通过 reactive compact 路径完成 compact，无 proactive compact 活动污染"。应在入口处断言 `requested_proactive == 0 and compacted_proactive == 0 and failed_proactive == 0`，或至少断言 `failed_total == 0`（与 `_assert_compact_acceptance` 的 line 4795 一致）。
- **实际行为**: 即使 proactive compact 意外触发并失败，reactive acceptance 仍 PASS。
- **直接证据**:
  - `_assert_reactive_compact_acceptance` (lines 3586-3591): 仅引用 `summary.requested_reactive`、`summary.compacted_reactive`、`summary.failed_reactive`
  - `_assert_compact_acceptance` (line 4795): `failed_total = audit.failed_proactive + audit.failed_reactive`
  - `_assert_fallback_dispatch_acceptance` (line 3646): 检查 `summary.requested_proactive < 1` 因为 fallback 依赖 proactive compact 请求
  - `grep -n "requested_proactive\|failed_proactive\|compacted_proactive" utils/smoke_host_public_conversation_memory_scenarios.py` 确认 reactive acceptance 函数体内不包含这些字段
- **影响**: 当 future Host/Service config 变更导致 reactive suite 的 setup 无意间触发 proactive compact 时，proactive 的失败将被静默掩盖。虽然当前 deterministic smoke 下 proactive 触发概率低（`_runtime_round_specs` 中 reactive suite 的 `user_pressure_text` 为空，无 proactive pressure trigger），但防御缺失让将来 config drift 的回归检测失效。
- **建议改法和验证点**:
  1. 在 `_assert_reactive_compact_acceptance` 开头增加: `if summary.requested_proactive > 0 or summary.compacted_proactive > 0 or summary.failed_proactive > 0: raise RuntimeError("memory-reactive-compact observed unexpected proactive compact activity")`。
  2. Assembly 测试新增一个参数化场景：构造含 `requested_proactive=1` 的 `CompactAuditReport`，验证断言触发。
- **修复风险**: 低。3 行断言 + 1 个测试场景。不改变现有执行路径和生产代码。
- **严重程度**: 中

### 2-未修复-中-Control doc `blocking open questions` 字段引用已废弃的 gate 名称 `accepted-slice`

- **入口/函数**: `docs/host/issues-implementation-control.md` line 153
- **文件(行号)**: `docs/host/issues-implementation-control.md:146 vs 153`
- **输入场景**: 读者在 aggregate-review gate 下查阅 control doc，看到 `blocking open questions` 声称当前 gate 为 `accepted-slice`，但 `当前状态` 表中 gate 为 `aggregate-review`。
- **实际分支**: 未提交 diff 更新了 `当前状态` 表中的 gate (line 146)、`implementation status` (line 147)、`next entry point` (line 150)，但未更新 `blocking open questions` (line 153) 中的 gate 名称。
- **预期行为**: control doc 推进规则 (line 178) 要求 gate 变更时必须同步更新 gate、active work unit、next entry point 和 blocking open questions 四个字段。`blocking open questions` 文本应反映当前 gate。
- **实际行为**: `blocking open questions` 仍写 "None for WU-CM-15 **accepted-slice** gate"。
- **直接证据**:
  - Working tree line 146: `| gate | aggregate-review |`
  - Working tree line 153: `| blocking open questions | None for WU-CM-15 accepted-slice gate. ...`
- **影响**: 降低 control doc 作为精确状态机真源的可靠性。后续 gate 推进若继续省略该字段的同步更新，字段会累积 gate 名称过期。
- **建议改法和验证点**: 将 line 153 的 `accepted-slice` 替换为 `aggregate-review`。若担心未来 gate 推进时再次遗忘，可改为 "None at current gate." 不绑定 gate 名称。
- **修复风险**: 极低。仅文案修正。
- **严重程度**: 中

### 3-未修复-中-`_COMPACT_PRESSURE_RESERVE_TOKENS` 从 160K 增至 575K 未附回归保护

- **入口/函数**: `_compact_pressure_padding_with_reserve` (line 4357) / `_COMPACT_PRESSURE_RESERVE_TOKENS` (line 196)
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:196-197, 4357-4395`
- **输入场景**: real-provider `memory-compact` suite 依赖足够大的 prompt pressure 跨越 soft threshold 触发 proactive compact。Reserve 从 160K 增至 575K（3.6x）意味着在相同 `target_tokens` 下 prompt padding 更小，proactive compact 触发点更晚。
- **实际分支**: `_compact_pressure_padding` 调用 `_compact_pressure_padding_with_reserve(options, reserve_tokens=_COMPACT_PRESSURE_RESERVE_TOKENS)`，其中 `reserve_tokens=575_000`。
- **预期行为**: 常量变更应有明确计算依据（如基于 deepseek-v4-flash 128K context window 和默认 policy ratio 反推），并在 `memory-compact` suite 的启动期断言中验证 `estimated_total_pressure_tokens >= soft_threshold_tokens`，防止 real-provider smoke 因 reserve 过大而无法触发 proactive compact。
- **实际行为**: 仅 fallback suite 有 pressure bounds 断言（`_assert_fallback_pressure_bounds`），`memory-compact` suite 的 real-provider 路径没有启动期 pressure bounds 检查。如果 reserve 过大导致 prompt pressure 不足以跨越 soft threshold，`_assert_compact_acceptance` 会报 `requested_proactive < 1` 硬错误，但 root cause（reserve 配置不合理）被淹没。
- **直接证据**:
  - `_COMPACT_PRESSURE_RESERVE_TOKENS` line 196: `575_000`
  - Assembly 测试 `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 验证了 helper 逻辑正确，但不验证 real-provider compact 实际触发
  - fallback suite 的 `_assert_fallback_pressure_bounds` 存在（line 3698），但 `memory-compact` 路径无同类保护
- **影响**: 若 575K reserve 在目标环境下过大，real-provider `memory-compact` smoke 将失败，但错误信息不直接定位到 reserve 常量配置。
- **建议改法和验证点**:
  1. 在 `_COMPACT_PRESSURE_RESERVE_TOKENS` 常量旁添加计算公式注释，说明 575K 的计算依据（context window size、policy ratio、target padding 范围）。
  2. 在 `run_smoke` 中加入类似 fallback suite 的启动期 pressure bounds 断言。
- **修复风险**: 低。仅增加注释和启动期断言。
- **严重程度**: 中

### 4-未修复-低-Fallback acceptance helper 的 `failed_events[-1]` 访问缺少非空 guard

- **入口/函数**: `_assert_fallback_dispatch_acceptance` (line 3632)
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:3651`
- **输入场景**: 若 `CompactOperationAudit` 因 compact audit 构造 bug 导致 `failed > 0` 但 `failed_events` 为空元组。
- **实际分支**: `failed_event = failed_operation.failed_events[-1]` 在元组为空时抛出 `IndexError`（无显式 guard）。
- **预期行为**: 应在访问 `failed_events[-1]` 前显式检查 `len(failed_operation.failed_events) > 0`，给出语义化错误信息。
- **实际行为**: 无 guard，边界错误信息为模糊的 `IndexError`。
- **直接证据**: line 3651: `failed_event = failed_operation.failed_events[-1]`
- **影响**: 仅在 compact audit 报告构造 bug 时触发（非正常路径），排障困难。
- **建议改法和验证点**: 在 line 3651 前增加 `if not failed_operation.failed_events: raise RuntimeError("memory-compact-fallback expected at least one failed event")`。
- **修复风险**: 极低。
- **严重程度**: 低

### 5-未修复-低-`run_smoke` 与 `_run_deterministic_compact_smoke` 存在 ~60 行结构性重复

- **入口/函数**: `run_smoke` (line 2966) / `_run_deterministic_compact_smoke` (line 3054)
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:2966-3167`
- **输入场景**: 两个函数执行几乎相同的公共 Host smoke flow：`_prepare_runtime_assembly -> _runtime_round_specs -> open_host -> ensure_session -> for-loop _run_round -> get_session -> _print_compact_summary -> _compact_audit_report -> _print_compact_audit_summary -> SMOKE PASS`。差异仅在 worker_factory 注入、compactor_runner patch、per-round assertion 和最终 assertion。
- **实际分支**: 两个函数独立实现了约 60 行几乎相同的代码。
- **预期行为**: 公共 Host smoke flow 应抽取为共享函数，两个入口只做差异化配置和 assertion。
- **实际行为**: 两份几乎相同的代码。违反了 CLAUDE.md "重复逻辑必须抽取" 约束。
- **直接证据**: 详见 subagent plan-review report 中的结构对比表。
- **影响**: 公共流程的 bug fix 需要在两处同步修改，容易遗漏。`_run_deterministic_compact_smoke` 的 per-round assertion 比 `run_smoke` 弱（缺少 `_assert_round_result` 调用），这是一个 subtle 差异。
- **建议改法和验证点**: 提取 `_execute_public_host_smoke_flow(assembly, specs, smoke_run_id, ...)` 公共函数，接收可选的 `worker_factory` 注入、`compactor_runner` patch 和 post-host assertion callback。非当前 WU scope，建议作为后续重构 work unit 追踪。
- **修复风险**: 中（重构涉及两个执行路径，需保证所有 4 个 suite 通过）
- **严重程度**: 低

### 6-未修复-低-Smoke 脚本模块尺寸达 5674 行（+39%），接近可维护性阈值

- **入口/函数**: N/A（模块级）
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py` (5674 lines)
- **输入场景**: 新增 deterministic worker/compactor/capture/stub infrastructure（~1500 行）全部写入同一文件。
- **实际分支**: 同一模块承担 4 种 suite mode routing、pressure injection、3 种执行路径、compact EventLog audit 完整系统、deterministic worker factory/worker、compactor runner stub（accept/reject 两条路径）、monkeypatch context manager、fallback pressure estimation、dispatch capture、marker-based oracle 断言、tool mock 和 pressure padding。
- **预期行为**: 新增的 deterministic smoke infrastructure 可拆分到独立模块，保持 smoke 脚本聚焦 suite routing 和 assertion orchestration。
- **实际行为**: 所有新增代码挤入同一文件。
- **直接证据**: `wc -l` 5674 lines（base 时 ~4089 lines，+39%）
- **影响**: 新开发者定位困难；未来新增 suite 会继续挤入同一文件。违反了 AGENTS.md "模块间依赖最小化" 的精神（虽未直接违反字面条款，因为条款主要针对 class/function/dataclass）。
- **建议改法和验证点**: 后续 WU 将确定性 smoke infrastructure（`_DeterministicCompactWorkerFactory`、`_AcceptingSmokeCompactorRunner`、`_RejectingSmokeCompactorRunner`、`_patched_compactor_runner`、`DeterministicSmokeObservation`、`DeterministicDispatchCapture`、`SmokeCompactorRunner` protocol、`FallbackPressureObservation`）提取为 `utils/smoke_compact_deterministic.py`。
- **修复风险**: 中（需正确处理 `sys.path` 以支持 `utils/` 下脚本直接运行）
- **严重程度**: 低

### 7-未修复-低-`_patched_compactor_runner` monkey-patch 私有模块属性，无 AttributeError 保护

- **入口/函数**: `_patched_compactor_runner` (line 1851)
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:1851-1867`
- **输入场景**: 未来 `dayu/host/llm_compaction.py` 重构，将 `_run_agent_request` 改为局部函数、闭包或 class method，模块属性不存在。
- **实际分支**: `original_runner = llm_compaction._run_agent_request` —— 若 `_run_agent_request` 不存在，`AttributeError` 直接抛出，而非转化为语义化错误信息。
- **预期行为**: 应在 access 前后捕获 `AttributeError` 并 `raise RuntimeError("llm_compaction._run_agent_request not found; Host compactor interface changed") from e`
- **实际行为**: `AttributeError` 直接传播，无上下文。
- **直接证据**:
  - line 72: `import dayu.host.llm_compaction as llm_compaction`
  - line 1860: `original_runner = llm_compaction._run_agent_request`（无 try/except）
- **影响**: 若 Host 内部重构改变私有属性名称，smoke 脚本在 setup 阶段崩溃，错误信息不明确指示 Host contract 变化。
- **建议改法和验证点**: 在 `_patched_compactor_runner` 的 setup 阶段加 `try/except AttributeError`，或要求 Host 暴露 public injection point。当前 plan 已接受此 trade-off，但仍需防御性错误处理。
- **修复风险**: 低。加 try/except 包装即可。
- **严重程度**: 低

### 8-未修复-低-Control doc WU-CM-15 段省略了 plan review artifact chain

- **入口/函数**: `docs/host/issues-implementation-control.md` WU-CM-15 `Implementation / Review 状态` 段
- **文件(行号)**: `docs/host/issues-implementation-control.md:1960-1971`
- **输入场景**: 读者查 control doc 了解 WU-CM-15 的完整审计链条。其他 WU（如 WU-CLI-ACTIVITY-01, WU-CLI-SESSION-01, WU-CM-13）记录了完整 plan review chain。
- **实际分支**: WU-CM-15 段仅记录 "accepted plan" 后直接跳到 "implementation artifact"，省略了 4 个 plan review artifact、1 个 plan fix artifact、1 个 plan review adjudication artifact。
- **预期行为**: 与其他 WU 段一致的完整 artifact chain 记录。
- **实际行为**: 6 个 plan review artifact 在磁盘上存在且可访问，但 control doc 中未形成可追溯链条。
- **直接证据**: 6 个 plan review artifact 全部在 `docs/reviews/` 中（2026-06-20 10:22-10:30 创建）。对比 WU-CLI-ACTIVITY-01 (line 254-259) 记录了完整 review chain。
- **影响**: 降低 control doc 作为完整审计链条的可追溯性。
- **建议改法和验证点**: 参考 WU-CLI-ACTIVITY-01 的格式补充 plan review artifact 条目。
- **修复风险**: 极低。
- **严重程度**: 低

---

## 特别审查项

### old marker oracle 非空转

**结论：非空转。**

- `_deterministic_dropped_old_marker(MEMORY_REACTIVE_COMPACT)` 返回 `_SMOKE_REACTIVE_OLD_MARKER`（line 3844）
- r1 prompt 包含 `_SMOKE_REACTIVE_OLD_MARKER`（line 2620: `f"记录旧上下文种子 {_SMOKE_REACTIVE_OLD_MARKER}..."`）
- Assembly 测试验证了该 marker 在 r1 prompt 中（`test_...assembly.py:318`）
- `_assert_reactive_compact_acceptance` 对 `dropped_old_marker is None` fail-closed（line 3602），并对 recovery dispatch 调用 `_assert_marker_absent`（line 3618）
- `_sanitize_compactor_material_text` 防止 fake compact 将 marker 重新引入 proposal（line 1974-1985）

数据链完整：marker 注入 r1 → Host 历史包含 marker → reactive compact 排除 r1 → recovery dispatch 不含 marker → oracle 断言 marker 缺席。非空转。

### suite-local memory policy 是否过度耦合

**结论：未过度耦合。**

- Reactive suite 使用 `_reactive_compact_smoke_memory_policy`（line 3231-3275），独立于 fallback suite 的 policy
- Fallback suite 使用 `--pressure-mode auto` 的 `_fallback_compact_pressure_padding_with_reserve`（line 3472），独立于 real-provider `memory-compact` 的 `_compact_pressure_padding`
- 两个确定性 suite 通过 `_DeterministicCompactWorkerFactory` 注入各自的 memory policy（reactive: `selected_recent_window_turn_floor=1`, fallback: `selected_recent_window_turn_floor=2`）
- 非全局可变状态，各 suite 通过 `dataclasses.replace(assembly.options, ...)` 注入独立 policy

轻微耦合点：
- `_reactive_compact_smoke_memory_policy` 假设 `policy.selected_recent_window_turn_floor <= 4`，若 Service 默认值变大则抛 `ValueError`（fail-fast，可接受）
- 所有 suite 共享同一个 `_compact_audit_report` 和 `_compact_audit_summary` 提取逻辑（正确——compact EventLog 的 audit 格式是 Host 公共契约）

### fallback pressure 分离

**结论：正确分离。**

- Fallback suite 有独立常量 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS = 160_000`（line 197），与 `memory-compact` 的 `_COMPACT_PRESSURE_RESERVE_TOKENS = 575_000` 独立
- Fallback suite 的 pressure estimation 使用 `--pressure-mode auto` 触发 `_fallback_compact_pressure_padding_with_reserve`
- Fallback 的 prompt pressure 计算路径（`_estimate_chars_as_tokens` + `_compact_pressure_padding_with_reserve`）与 proactive pressure 路径物理分离
- `_assert_fallback_pressure_bounds` 验证 fallback pressure 落在 soft-hard threshold 区间内
- Fallback suite 不会意外触发 proactive compact（`_runtime_round_specs` 中 fallback `user_pressure_text` 由 fallback padding 计算，proactive compact 由单独的 pressure 触发逻辑控制）

### stdout bounded

**结论：有界，合理。**

- 所有 print 都在 `_print_compact_summary`、`_print_compact_audit_summary`、`_print_round`、`_print_assembly_diagnostics` 等结构化函数中
- 每个 suite 输出审计摘要固定字段数（5-10 个统计项）
- deterministic smoke 的 `_AcceptingSmokeCompactorRunner` 和 `_RejectingSmokeCompactorRunner` 不打印日志（仅在 `--debug-smoke-output` 时输出 compact proposal 摘要）
- `_print_compact_pressure_plan` 输出 token 计算详情（~3-5 行），有界
- 无无限循环打印、无限展开数据结构、无 bounds-unsafe 的 `repr()` dump

### real-provider memory-compact residual 是否合理

**结论：合理，已正确分类。**

- `--suite memory-compact` 依赖真实 compactor LLM provider API key。`test-provider-key` 导致 `CONTEXT_COMPACTION_FAILED` → Host fallback dispatch，这不是 smoke "失败"而是 auth failure。所有 review artifacts 一致分类此状态为 "环境/residual，非 WU-CM-15 blocker"
- plan Risk 节明确记录："`memory-compact` smoke 在无有效 compactor provider key 的环境中会失败"
- 本 WU 的 deterministic smoke 不依赖有效 API key，用 `_AcceptingSmokeCompactorRunner` / `_RejectingSmokeCompactorRunner` stub 覆盖了 compact success 和 compact failure 两条路径
- 后续需要有效 API key 或 injectable compactor mock 来关闭此残余

### README/control doc 是否同步

**结论：基本同步，有 1 处 gate 名称不一致（Finding #2）。**

- `tests/README.md` 已正确更新，反映新增的 `memory-reactive-compact` / `memory-compact-fallback` suite
- README 触发规则正确执行：仅 `tests/` 修改触发 `tests/README.md` 更新，无遗漏
- Production `dayu/` 未修改，`dayu/host/README.md` / `dayu/engine/README.md` 等不触发（正确）
- Control doc gate 字段正确从 `accepted-slice` 更新为 `aggregate-review`
- Control doc `blocking open questions` 字段仍引用旧 gate 名称 `accepted-slice`（见 Finding #2）
- Control doc WU-CM-15 段省略了 plan review artifact chain（见 Finding #8）

---

## Cross-Verification Summary

### 四个 subagent 的一致性检查

| 维度 | Plan review | Implementation | Review artifacts | Control doc | 交叉验证结论 |
|------|-------------|----------------|------------------|-------------|-------------|
| **old marker oracle 非空转** | 确认修复后完整 | 确认 prompt 包含 marker | 确认 Controller 纠正 | 不适用 | **一致：非空转** |
| **production code 零变更** | 确认 | 确认 | 确认 | 确认 | **一致** |
| **memory-compact strict semantics 保持** | 确认 | 确认（fallback 断言正确） | 确认 | 确认 | **一致** |
| **plan review chain 记录不全** | N/A | N/A | N/A | 发现缺失 6 个 artifact | **确认为真** |
| **`blocking open questions` gate 名称过期** | N/A | N/A | N/A | 发现 `accepted-slice` 残留 | **确认为真** |
| **reactive proactive 零值检查缺失** | N/A | 发现 | N/A | N/A | **确认为真** |
| **`_COMPACT_PRESSURE_RESERVE_TOKENS` 变更无回归保护** | N/A | 发现 | N/A | N/A | **确认为真** |
| **`run_smoke`/`_run_deterministic_compact_smoke` 重复** | 发现 | N/A | N/A | N/A | **确认为真** |
| **smoke 脚本行数膨胀** | 发现 | N/A | N/A | N/A | **确认为真** |
| **`failed_events[-1]` 无 guard** | N/A | 发现 | N/A | N/A | **确认为真** |

无 subagent 结论冲突。所有 finding 均基于直接代码证据验证。

### 未修改 Host/Engine production contract/schema 确认

`git diff --stat 0439cd80...HEAD -- dayu/` 输出为空。变更仅发生在 `utils/`（smoke script）、`tests/runtime/`（assembly tests）、`tests/README.md`、`docs/host/host-issues/`（plan artifact）和 `docs/reviews/`（review artifacts）。

### 20 个 assembly tests 全部通过确认

Controller validation 记录在 control doc line 1968：`pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed (`20 passed`)。

### pyright 0 errors 确认

Controller validation 记录在 control doc line 1968：`python -m pyright dayu/ tests/ utils/` passed (`0 errors`)。

---

## Open Questions

1. **575K reserve 选择依据**：`_COMPACT_PRESSURE_RESERVE_TOKENS = 575_000` 的计算公式未文档化。是否基于 deepseek-v4-flash 128K context window 和默认 policy ratio (soft=0.75, hard=0.9) 反推？建议在常量处添加 formula comment。

2. **Reactive suite per-round assertion 缺失是有意设计还是遗漏**：`_run_deterministic_compact_smoke` 不调用 `_assert_round_result`，而 `run_smoke` 调用。如果是有意的（因为 deterministic worker 的 final answer 不携带 seed marker），应在 plan 或代码注释中说明。

3. **`_patched_compactor_runner` 是否有 Host public injection point 替代方案**：当前 monkey-patch `llm_compaction._run_agent_request` 是否可通过 `OpenHostOptions` 或 worker factory 的正式扩展点替代？未来 Host 重构时应考虑此需求。

4. **Plan review artifact chain 省略是否为有意**：WU-CM-15 是 light smoke coverage WU，非 production code change。省略是否因 plan review 内容简单而有意选择？建议在 control doc 中加一行说明。

---

## Residual Risk

| ID | Risk | Severity | Owner | Mitigation |
|----|------|----------|-------|------------|
| RR-01 | Real-provider `memory-compact` suite 在 575K reserve 下能否稳定触发 proactive compact，未经 real-provider 环境验证 | 中 | WU-CM-15 closeout | 使用有效 API key 运行 `--suite memory-compact` 验证 |
| RR-02 | `_patched_compactor_runner` monkey-patch 依赖 `dayu.host.llm_compaction._run_agent_request` 私有属性 | 中 | future Host refactor | Host compactor 模块重构时同步更新 smoke script；已有 fail-fast identity check |
| RR-03 | `run_smoke` / `_run_deterministic_compact_smoke` 结构性重复 | 中 | future smoke refactor | 后续 smoke-related WU 中提取公共 Host flow |
| RR-04 | Smoke 脚本 5674 行（+39%）模块边界膨胀 | 低 | future smoke refactor | 下一个 smoke WU 前拆分 deterministic infrastructure 到独立模块 |
| RR-05 | `_COMPACT_FALLBACK_FORBIDDEN_SECTIONS` section title 字符串与 host/design.md 映射漂移风险 | 低 | Host section title change | Host section title 变更时同步更新 forbidden section strings；考虑添加 sanity check |
| RR-06 | `failed_events[-1]` 无 guard | 低 | future smoke hardening | 添加语义化 guard |
| RR-07 | Reactive proactive 零值检查缺失 | 中 | WU-CM-15 closeout | 已在 Finding #1 中记录 |

---

## 裁决

**PASS**（无 correctness / stability / maintainability blocker）。

WU-CM-15 实现了声称的目标：只增加 public smoke 覆盖 reactive compact 路径和 deterministic compact-failure fallback 路径。未修改 Host/Engine production contract/schema（`git diff --stat 0439cd80...HEAD -- dayu/` 为空）。`memory-compact` strict proactive accepted semantics 保持不变（`_assert_compact_acceptance` 未修改）。

所有 8 个 findings 均为 non-blocker（3 个 medium、5 个 low），均已在本文档中记录并可追溯。其中 3 个 medium findings 建议在 closeout 前修复：

- **Finding #1**（reactive proactive 零值检查缺失）：3 行断言 + 1 个测试场景，修复风险低
- **Finding #2**（control doc `blocking open questions` gate 名称过期）：1 行文案修正，修复风险极低
- **Finding #3**（575K reserve 无回归保护）：注释 + 启动期断言，修复风险低

review-fix 流程的 Controller 纠正（old marker 空转 oracle）暴露了 fix agent 倾向于字面实施 finding 而非追踪 root cause 完整数据链的系统性风险，但该风险已被 Controller 在本 WU 中成功拦截，且不影响代码当前正确性。

无 AGENTS.md / CLAUDE.md 硬约束违规。

---

*Review performed 2026-06-20 by AgentDS aggregate deepreview with 4 subagent parallel review passes. Cross-verification confirms no subagent conclusion conflicts.*
