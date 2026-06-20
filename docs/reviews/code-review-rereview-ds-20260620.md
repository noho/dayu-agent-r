# Code Review — WU-CM-15 Focused Re-review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phase/wu-cm-15`
- Base: `97518e93` (accepted plan commit)
- Output file: `docs/reviews/code-review-rereview-ds-20260620.md`
- Review timestamp: 2026-06-20 11:51:55 CST
- Included scope: `utils/smoke_host_public_conversation_memory_scenarios.py`, `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`, `tests/README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: 未改动的生产代码；其他 smoke 脚本（`utils/smoke_host_public_multiturn.py`、`utils/smoke_host_public_conversation_memory.py`）的 `_compact_pressure_reserve_tokens` 不属于本 change scope；其他 review artifacts 与 control docs。
- Parallel review coverage: 无。

## Review Focus Items

本 re-review 严格按 Controller 裁决的 7 项焦点逐条走读，每项给出明确 PASS / FAIL。

---

### 1. `_SMOKE_REACTIVE_OLD_MARKER` 是否真实进入 reactive-r1-old-seed prompt，oracle 是否不是空转

**结论：PASS**

证据链：

- `_SMOKE_REACTIVE_OLD_MARKER` = `"DAYU_SMOKE_REACTIVE_OLD_SEED_V1"`（`utils/smoke_host_public_conversation_memory_scenarios.py:284`）。
- `_reactive_compact_round_specs()` 的 r1 轮次 prompt 为 `f"记录旧上下文种子 {_SMOKE_REACTIVE_OLD_MARKER}，后续只作为 compact 可丢弃历史。"`（行 2620）。
- 测试 `test_smoke_spec_fact_keys_and_reactive_labels`（`test_...assembly.py:318`）断言 `_SMOKE_REACTIVE_OLD_MARKER in reactive_spec_by_label["reactive-r1-old-seed"].prompt`，验证 marker 已写入 LLM 可见 prompt。
- Oracle 非空转的核心证据在 `_assert_reactive_compact_acceptance`（`scenarios.py:3617-3621`）：对 recovery dispatch 调用 `_assert_marker_absent`（行 3791-3802），若 marker 出现在 recovery 文本中则抛 `RuntimeError`。
- 测试 `test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals`（`test_...assembly.py:613`）构造 old marker leak 场景（recovery 文本显式包含 `_SMOKE_REACTIVE_OLD_MARKER`），断言抛 `RuntimeError("reactive recovery dropped old unexpectedly contains marker")` → 证明 oracle 对 old marker leak 是 fail-closed 而非空转。
- 正常路径（行 572）构造不含 old marker 的 recovery dispatch，`_assert_reactive_compact_acceptance` 通过 → oracle 在正负两端都有覆盖。

**需要注意的边界**：assembly 单元测试使用 fabricated `CompactAuditReport` 和 `DeterministicSmokeObservation`，不驱动真实 Host。old marker 是否在真实 Host 历史中被正确写入、compact 是否按 tightened cap 正确排除，依赖实际 smoke run（`--suite memory-reactive-compact`）验证。assembly 测试已覆盖 helper 逻辑的正负路径，但完整集成行为仍需 smoke run。

---

### 2. memory-reactive-compact 的 suite-local selected recent cap 是否只影响该 suite，是否合理证明 r1 old seed 被 raw selected_recent 排除，同时 r5 protected recent 和 current input 保留

**结论：PASS**

证据链：

- `_smoke_options_for_suite`（`scenarios.py:3231-3232`）：`if suite is not SuiteMode.MEMORY_REACTIVE_COMPACT: return options` → 非 reactive suite 直接返回原始 options，不修改任何 policy。
- 仅当 `MEMORY_REACTIVE_COMPACT` 时（行 3233-3237），调用 `_reactive_compact_smoke_memory_policy` 构造 `MemoryProjectionPolicy` 的本地副本（通过 `dataclasses.replace`），替换原 policy 的 `selected_recent_window_item_cap` 和 `fallback_selected_recent_window_item_cap`。
- Host 生产 policy 从未被修改；suite-local cap 仅作用于 `assembly.options.memory_projection_policy` 的副本。
- `test_reactive_runtime_assembly_bounds_selected_recent_window`（`test_...assembly.py:168-187`）验证：
  - cap 计算公式 `selected_recent_window_item_cap = selected_recent_window_turn_floor * _SMOKE_REACTIVE_SELECTED_RECENT_ITEMS_PER_TURN`（行 183-186）。
  - fallback cap ≤ selected cap（行 187）。
- r1 排除的合理证明：round layout 为 r1(old) → r2, r3, r4(history gap = 3) → r5(protected recent) → r6(current input)。`selected_recent_window_turn_floor` = `_SMOKE_REACTIVE_HISTORY_GAP_ROUNDS + 1 = 4`（行 3256），即保护最近 4 轮。r1 距离 target 5 轮 → r1 被 raw selected_recent 排除。
- `_assert_reactive_compact_acceptance`（行 3605-3613）验证 recovery dispatch 同时包含 `current_input_marker` 和 `protected_recent_marker` → r5 和 current input 保留。

**无问题**。

---

### 3. `_assert_reactive_compact_acceptance` / `_deterministic_dropped_old_marker` 是否覆盖 missing dropped marker 与 old marker leak

**结论：PASS**

证据链：

- `_deterministic_dropped_old_marker(SuiteMode.MEMORY_REACTIVE_COMPACT)` 返回 `_SMOKE_REACTIVE_OLD_MARKER`（`scenarios.py:3843-3844`）。
- `_assert_reactive_compact_acceptance` 行 3615-3621：若 `observation.dropped_old_marker is None`，抛 `RuntimeError("memory-reactive-compact missing dropped old marker expectation")` → missing dropped marker 被覆盖。
- 测试行 578-589：构造 `dropped_old_marker=None` 的 observation，断言抛 `RuntimeError("missing dropped old marker expectation")` → missing dropped marker 路径已测试。
- `_assert_reactive_compact_acceptance` 行 3617-3621：调用 `_assert_marker_absent(recovery.joined_messages, marker=observation.dropped_old_marker)` → old marker leak 被覆盖。
- 测试行 591-614：构造 recovery dispatch 文本包含 `_SMOKE_REACTIVE_OLD_MARKER` 的 observation，断言抛 `RuntimeError("reactive recovery dropped old unexpectedly contains marker")` → old marker leak 路径已测试。

**覆盖完整**：missing dropped marker（dropped_old_marker=None → fail）和 old marker leak（marker 在 recovery 中 → fail）均有正负向断言和测试。

---

### 4. `_patched_compactor_runner` identity sanity check 是否有效且 finally restore

**结论：PASS**

证据链：

- `_patched_compactor_runner`（`scenarios.py:1851-1867`）：
  - 行 1860：`original_runner = llm_compaction._run_agent_request` — 在 try 前捕获原始值。
  - 行 1862：`llm_compaction._run_agent_request = runner` — 设置 patch。
  - 行 1863-1864：`if llm_compaction._run_agent_request is not runner: raise RuntimeError(...)` — 立即用 `is` 做 identity check。若 `_run_agent_request` 被 descriptor/property 拦截导致赋值后读取值不等于 runner，会 fail-fast。
  - 行 1866-1867：`finally: llm_compaction._run_agent_request = original_runner` — 无条件 restore。
- patch 的使用点仅一处（行 3097）：`with _patched_compactor_runner(compactor_runner):` — context manager 保证 finally 执行。
- 即使 identity sanity check 抛出 RuntimeError，`original_runner` 已在 try 前捕获，finally 中的 restore 仍会执行。

**无问题**。

---

### 5. `_compact_pressure_reserve_tokens` 是否已删除且未留下死代码

**结论：PASS**

证据链：

- `git diff 97518e93 -- utils/smoke_host_public_conversation_memory_scenarios.py` 显示 `_compact_pressure_reserve_tokens` 函数（原定义在 `scenarios.py`）已被完整删除（diff 中为 `-` 行）。
- 仓库全局搜索 `_compact_pressure_reserve_tokens`（排除其他 smoke 脚本 `smoke_host_public_multiturn.py` 和 `smoke_host_public_conversation_memory.py` 中的独立同名函数——二者不在本 change scope 内）：在 `scenarios.py` 和 `test_...assembly.py` 中均 **无** 引用。
- `_COMPACT_PRESSURE_RESERVE_TOKENS`（大写常量，`scenarios.py:196`）是独立的压力 reserve 常量（575,000），与已删除的函数 `_compact_pressure_reserve_tokens` 是不同的符号。该常量在 `_compact_pressure_padding` 和 `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 中有实际使用，不是死代码。
- 新增的 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS`（`scenarios.py:197`，160,000）用于 fallback suite 的独立压力预算估算，有实际使用。

**无残留**。

---

### 6. fallback deterministic smoke acceptance 是否仍覆盖 proactive failure fallback dispatch selected/dropped/current refs

**结论：PASS**

证据链：

- `_assert_fallback_dispatch_acceptance`（`scenarios.py:3632-3694`）覆盖：
  - `selected_block_ids` 非空（行 3654-3655）；
  - `dropped_block_ids` 非空（当 `dropped_old_marker is not None`）（行 3656-3657）；
  - `current_input_ref` 非空且非空白（行 3658-3659）；
  - fallback dispatch 包含 `current_input_marker`（行 3668-3672）；
  - fallback dispatch 包含 `protected_recent_marker`（selected recent）（行 3673-3677）；
  - fallback dispatch 不包含 `dropped_old_marker`（行 3678-3683）；
  - 不允许 fake semantic memory section 出现在 fallback dispatch 中（行 3684-3686）。
- 测试 `test_fallback_acceptance_helper_requires_proactive_request_and_window`（`test_...assembly.py:648-692`）：
  - 正常路径：`_fallback_report(include_request=True)` 包含 selected_block_ids、dropped_block_ids、current_input_ref（行 1029-1031），`_assert_fallback_dispatch_acceptance` 通过（行 676）。
  - 异常路径：`include_request=False` 时 `dropped_block_ids` payload 不存在 → `_assert_fallback_dispatch_acceptance` 应抛异常（行 678-679，但需确认此路径实际由 `CONTEXT_COMPACTION_REQUESTED` 缺失而非 dropped 缺失触发）。
  - 压力越界路径：pressure < soft → 抛 `RuntimeError("below soft threshold")`（行 691-692）。
- fallback round specs（`scenarios.py:2681-2732`）：f1-f5 为 old-dropped 种子（其中 f1 使用 `_SMOKE_FALLBACK_OLD_MARKER`），f6 为 selected recent marker，f7 为 pressure target + current input marker。
- `_deterministic_dropped_old_marker(SuiteMode.MEMORY_COMPACT_FALLBACK)` 返回 `_SMOKE_FALLBACK_OLD_MARKER`（`scenarios.py:3845-3846`），非 None → dropped_block_ids 检查生效。

**cover 完整**。

---

### 7. tests/README.md 的最小更新是否符合触发规则

**结论：PASS**

证据链：

- `tests/README.md` 更新内容（diff）：
  - 原：`` memory-core` / `memory-compact` suite 解析、pressure mode 参数、compact EventLog audit 摘要验收... ``
  - 新：`` memory-core` / `memory-compact` / `memory-reactive-compact` / `memory-compact-fallback` suite 解析、pressure mode 参数、reactive deterministic recovery dispatch oracle、compact failure fallback selected window oracle、compact EventLog audit 摘要验收... ``
- 触发规则：`tests/` 修改 → 检查并按需更新 `tests/README.md`（CLAUDE.md `README 更新触发` 节）。
- 更新内容：仅追加了新增 suite（`memory-reactive-compact`、`memory-compact-fallback`）及对应的 oracle 测试覆盖（`reactive deterministic recovery dispatch oracle`、`compact failure fallback selected window oracle`）。未修改其他行。
- 这符合"最小更新"原则：只反映 tests 目录下新增的关键测试覆盖范围，不扩写 README 职责。

**无问题**。

---

## Findings

未发现实质性问题。

---

## Open Questions

1. **reactive smoke 的 assembly 单元测试不驱动真实 Host**：`test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals`（`test_...assembly.py:520`）使用 fabricated `CompactAuditReport` 和 `DeterministicSmokeObservation`，验证的是 helper 逻辑的正负路径而非 end-to-end Host 行为。old marker 是否在真实 Host 运行中被正确写入 history、compact 是否按 tightened cap 真实排除 r1，依赖实际 smoke run 验证。当前 assembly 测试已完整覆盖 helper 逻辑，不构成 blocker，但属于集成覆盖缺失。

2. **`test_fallback_acceptance_helper_requires_proactive_request_and_window` 的 `include_request=False` 路径**：当 `include_request=False` 时，`_fallback_report` 不产生 `CONTEXT_COMPACTION_REQUESTED` 事件，因此异常确实由 `requested_proactive < 1`（行 3646-3647）触发而非 `dropped_block_ids` 缺失触发。`dropped_block_ids` 缺失路径未在 fallback 测试中单独覆盖（仅在 `dropped_old_marker is None` 时跳过检查）。不构成当前 blocker，但如后续需要，可补充 dropped_block_ids 独立缺失场景。

---

## Residual Risk

- `_COMPACT_PRESSURE_RESERVE_TOKENS` 常量从 160,000 提升至 575,000（`scenarios.py:196`），同时新增独立的 fallback reserve 常量 160,000。压力 reserve 变更影响 pressure 估算的 soft/hard threshold 边界判定。若上游 context budget policy 的 window size 或 ratio 变化导致压力估计偏移，smoke 的 pressure bounds 断言可能过拟合当前配置值。当前有对应的测试（`test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds`）覆盖压力边界，风险低。
- `_patched_compactor_runner` 的 identity sanity check 使用 `is not` 做对象同一性比较。在 CPython 中对于普通模块属性赋值通常成立，但若 `llm_compaction._run_agent_request` 有自定义 `__set__` descriptor 或 property 进行值变换，此检查会失败。当前 Host 实现中 `_run_agent_request` 为普通模块级变量，无此风险。
- smoke 脚本 `utils/smoke_host_public_conversation_memory_scenarios.py` 不属于 `dayu/` 生产代码，无测试覆盖率要求（CLAUDE.md 明确 `utils/` 下脚本默认无需测试、无覆盖率要求）。assembly 测试（`tests/runtime/test_...assembly.py`）已为 helper 提供单元级覆盖，覆盖率为 helper 函数级而非 smoke 脚本端到端级。
