# Phase 10 Slice 6 Code Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Verdict: PASS_WITH_RESIDUAL**

## Scope

Production composition integration — HostCommandHandleOptions budget fields, composition helper, public contract tests:
- `dayu/host/api.py` (+43/-0)
- `dayu/host/command.py` (+55/-2)
- `tests/host/test_public_contracts.py` (+110/-0)
- `dayu/host/README.md` / `tests/README.md`

## Verification

- `pytest tests/host/test_context_budget.py` — 20 passed
- `pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py` — 17 passed
- `pytest tests/host/test_context_compact_events.py` — 15 passed
- `pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py` — 64 passed
- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py` — 104 passed
- `pytest tests/host/test_public_contracts.py` — 39 passed
- `pyright` — 0 errors
- `git diff --check` — 通过

---

## Findings

### F1. `compose_host_local_execution_options` 缺少 production 入口调用证据 (RESIDUAL)

**文件:** `dayu/host/command.py:276-307`

**证据:**
`compose_host_local_execution_options` 是 Slice 6 新增的唯一 production composition wiring helper。全局搜索显示其调用仅出现在 `tests/host/test_public_contracts.py` (:600, :631)。不存在于任何 production 入口（Service layer、main、CLI）。

**Plan 要求 (phase10-context-governance-plan.md:510):**
> `dayu/host/command.py` constructs `ContextBudgetPolicy` from those options when opening local execution

**分析:**
此 helper 本身不是"孤立 helper"——它正确地实现了 plan 要求的 typed wiring 契约，是 composition root 应该调用的公共接口。但由于 `dayu/host/` 包内没有 Service/composition root 层（Service 层在 `dayu/service/`），当前无 production 调用方是 layer placement 的自然结果。

**Severity: RESIDUAL**。不构成 correctness 风险。`compose_host_local_execution_options` 是正确放置的 public contract surface，等待 composition root 调用。当前的 public contract test 已充分验证其 wiring 正确性（policy 字段传递、artifact root 注入、memory policy 独立）。

**建议:** 不需要在当前 slice 补 production 入口调用。等到有 Service/composition root 实现时，应通过 `compose_host_local_execution_options` 构造 `HostLocalExecutionOptions` 并传入 `HostDispatchScheduler.open()`。

**Owner:** Phase 10 aggregate validation owner 或后续 composition root owner。

---

### F2. `context_window_size` / `reserved_output_tokens` 默认值削弱"显式输入"语义 (MEDIUM)

**文件:** `dayu/host/api.py:61-63`, `dayu/host/api.py:1173-1174`

**证据:**
```python
# api.py:61-63
HOST_CONTEXT_WINDOW_SIZE_DEFAULT = 8192
HOST_RESERVED_OUTPUT_TOKENS_DEFAULT = 1024

# api.py:1173-1174
context_window_size: int = HOST_CONTEXT_WINDOW_SIZE_DEFAULT
reserved_output_tokens: int = HOST_RESERVED_OUTPUT_TOKENS_DEFAULT
```

**Plan 要求 (phase10-context-governance-plan.md:510):**
> Service / composition root supplies the two positive integers to `HostCommandHandleOptions`

**Design 要求 (implementation-control.md:2258):**
> `reserved_output_tokens` 由 Service / composition root 作为 Host context policy 显式 typed input 传入

**对比:**
- Plan 中 `HostCommandHandleOptions.context_window_size: int` 无默认值标记
- `HostLocalExecutionOptions.context_budget_policy` 是 `ContextBudgetPolicy | None = None`——预算本身的 Optional 语义是"无 policy 则放行"（已有文档），但 command options 层面的默认值使 composition root 可以不显式提供这两个字段
- `_validate_command_context_budget_fields` (:1244-1268) 使用 `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` 与 `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 作为 `minimum_protection_tokens` 的 fallback 计算基准——但当 composition root 未主动传入 `context_window_size` 和 `reserved_output_tokens` 时，默认值会生成合法的 policy 而不报警

**实际影响:**
- 如果 composition root 忘记显式传入 `context_window_size` 或 `reserved_output_tokens`，系统会静默使用 8192/1024，不会报错
- 这违背 plan 和 design 中"显式输入"的语义——默认值使选项变成可选
- 但当前没有 production composition root 实现，此风险尚未在 production 中触发

**Severity: MEDIUM**。设计约束与实现之间存在张力。默认值的存在使"显式输入"变成"可选输入"，增加了 composition root 误用的可能。但由于这些值只在 `default_context_budget_policy(...)` 中消费（该函数仍然要求显式传入两个参数），语义链路的一端仍然保持"必须显式构造 policy"。

**建议修复方向:**
- 方案 A: 移除 `context_window_size` 和 `reserved_output_tokens` 的默认值，强制 composition root 显式传入
- 方案 B: 保留默认值但在 README 中明确标注"默认值仅用于 local dev/test；production 必须由 composition root 显式覆盖"
- 推荐 A，因为 plan 和 design 一致要求显式输入

**Owner:** Phase 10 Slice 6 owner。

---

### F3. `context_compactor` 未注入——plan gap (RESIDUAL)

**文件:** `dayu/host/command.py:290-307`

**证据:**
`compose_host_local_execution_options` 使用 `dataclasses.replace(options.local_execution, context_budget_policy=..., compact_artifact_root=...)`，不设置 `context_compactor` 字段。`HostLocalExecutionOptions.context_compactor` (:741) 保持原有值（在 `replace` 中保持不变）。

**Plan 要求 (phase10-context-governance-plan.md:504-506):**
> - context governance orchestrator factory or typed options
> - `context_compactor: ContextCompactor`
> - compact artifact store root via existing durable artifact root

**Plan 要求 (phase10-context-governance-plan.md:515):**
> Add deterministic fake compactor wiring for tests and optional local developer configuration

**分析:**
1. `context_compactor` 作为 `HostLocalExecutionOptions` 的字段已存在（:741 `= None`）。`compose_host_local_execution_options` 通过 `dataclasses.replace` 保留 `local_execution` 上已设置的 compactor——这是正确的显式注入行为。Helper 不应默认注入 fake compactor（会违反"production 不得隐式使用 fake compactor"的规则）。
2. 但 plan 明确要求 "fake compactor wiring for tests"——当前实现不提供任何 test helper 来简化 fake compactor 注入。
3. 实现 artifact (:44) 将此标记为 residual: "未配置 compactor 且触发 compact 时仍按 S4/S5 fail closed。真实 production compactor adapter 归后续 explicit composition owner。"

**Severity: RESIDUAL**。不注入 compactor 是正确的 production 边界——防止隐式 fake compactor 进入 production。但 plan 要求的 fake compactor test wiring 缺失。

**建议:** 如果需要满足 plan 的 "fake compactor wiring for tests" 要求，可考虑在 `tests/host/` 下添加 test helper（不由 `compose_host_local_execution_options` 提供，而是独立 test fixture）。当前 S4/S5 测试已通过直接构造 `FakeContextCompactor()` 并传入 `HostLocalExecutionOptions` 覆盖了此路径。

**Owner:** Phase 10 test owner。

---

### F4. 缺失 full multi-turn E2E test (MEDIUM)

**证据:**
实现 artifact (:19-22) 明确声明:
> 未新增更大的 full multi-turn E2E，因为当前可验证点已由 `test_memory_projection.py`、`test_run_input_builder.py`、`test_dispatch_scheduler.py` 和 `test_phase5_local_execution_integration.py` 分层覆盖

**Plan 要求 (phase10-context-governance-plan.md:529-535):**
> End-to-end local fake worker scenario:
> - Run 1 creates raw turns and tool verified fact.
> - Follow-up Run under budget includes recent raw turns and verified fact.
> - Later Run over soft threshold triggers proactive compact.
> - `CONTEXT_COMPACTED` is consumed by memory projection.
> - Subsequent Run messages contain pinned state, verified facts, recent raw turns floor and episode summaries in P9/P10 order.

**分析:**
现有分层测试覆盖了各个子组件:
- `test_dispatch_scheduler.py`: proactive pre-start governance gate + reactive recovery dispatch
- `test_memory_projection.py`: CONTEXT_COMPACTED → memory projection consumption
- `test_run_input_builder.py`: memory snapshot → RunInputBuilder message construction
- `test_phase5_local_execution_integration.py`: public `start_run` + scheduler dispatch + worker 闭环

但**没有任何单一测试**验证以下完整链:
```
User Input → ACCEPTED Run → governance budget check → proactive compact →
CONTEXT_COMPACTED → memory projection consumption → RUN_STARTED →
new Attempt → Engine request 包含 compacted 后的 memory state →
Engine response → next user input → memory projection 包含上次事实
```

这是 Phase 10 exit condition "多轮会话主体闭环可验证" 的核心要求。当前的分层测试加起来可以证明各环节独立正确，但不能证明跨环节集成时没有协议错配、cursor 越界或 event ordering bug。

**具体风险:**
1. S4 proactive compact `_run_pre_start_governance` 与 memory projection catch-up 之间：projection catch-up 的 `max_event_sequence` 参数来自 compacted_event_sequence——但没有 E2E 测试验证这个 sequence 在 RunInputBuilder 的 `_latest_compacted_event_before_attempt` 查询中能正确匹配（该查询要求 `event_sequence < attempt.started_event_sequence`）。
2. 多轮间 P9 + P10 memory 排序：pinned state、verified facts、recent raw turns、episode summary 的 budget 优先级排序——`test_run_input_builder.py` 覆盖了单轮构造，但没有覆盖"前一轮 compact 产生的 episode summary + 后一轮新 tool fact"的混合多轮场景。

**Severity: MEDIUM**。不达到 plan 要求，但:
- 现有分层测试已覆盖所有关键转换点和 CAS 条件
- 各组件之间有 typed 合约保证边界对齐（`ContextBudgetPolicy`、`CompactionRequest`、`CONTEXT_COMPACTED` payload schema、`DurableCompactArtifactProvider` cursor）
- 缺失的 E2E 可在不改变生产代码的情况下添加

**建议修复方向:** 在 `test_phase5_local_execution_integration.py` 或新建 aggregate test 中追加一个多轮 fake worker 场景：
1. 第一轮: fake worker 产出 tool call + tool result → tool fact 进入 memory
2. 第二轮: 主动将 context_window_size 设小使 budget 触发 soft threshold → proactive compact 产生 CONTEXT_COMPACTED
3. 第三轮: 验证 RunInputBuilder 消息包含前两轮信息 + episode summary
4. 验证 memory projection correct cursor

**Owner:** Phase 10 aggregate validation owner。

---

### F5. Budget 字段分层隔离——验证通过 (PASS)

**文件:** `tests/host/test_public_contracts.py:808-838`

**证据:**
`test_context_budget_inputs_are_not_per_run_fields` (:808-838) 使用 `dataclasses.fields()` 反射检查:
- `StartRunRequest` 字段集合
- `SubmitFollowupRequest` 字段集合
- `HostMetadataEntry` 字段集合

断言 `{"context_window_size", "reserved_output_tokens", "context_budget_hard_threshold_tokens", "context_budget_minimum_protection_tokens"}` 与以上三个字段集合完全 disjoint。

**验证:**
- `HostCommandHandleOptions` (composition 层) 承载 budget 字段 ✓
- `HostLocalExecutionOptions.context_budget_policy` (typed 层) 承载构造后的 policy ✓
- Per-run request / metadata / Engine spec / provider overflow 不承载 ✓

**Verdict: PASS**。分层隔离正确，无越界泄漏。

---

### F6. 架构边界、类型、文档与 pyright (PASS)

**检查结果:**
1. **分层**: `dayu/host/command.py` 只 import `dayu.host.api`、`dayu.host.context_policy`、`dayu.host.durable.*`——均在 Host 层内或公共契约。无 UI/Service/Engine/Fins 反向依赖 ✓
2. **类型**: 所有新增字段有完整类型标注；optional 字段使用 `int | None`；返回值类型 `HostLocalExecutionOptions | None` ✓
3. **Docstring**: `compose_host_local_execution_options` (:277-296) 有完整中文 docstring，包含参数、返回值、data flow 说明 ✓
4. **`__post_init__` 校验**: `_validate_command_context_budget_fields` (:1244-1268) 通过构造 `default_context_budget_policy(...)` 触发 `ContextBudgetPolicy.__post_init__` 校验——TypeError 校验在 `__post_init__` 的类型守卫中（`context_window_size` 非 int → TypeError）✓
5. **`__all__`**: `compose_host_local_execution_options` 已加入 `command.py:1204` ✓
6. **pyright**: 0 errors ✓
7. **README**: `dayu/host/README.md` 更新了 command handle options 的 context budget 描述与 composition data flow；`tests/README.md` 补充了 `test_context_compact_events.py` 入口与分类标注 ✓
8. **Memory vs context policy 分离**: `compose_host_local_execution_options` 不修改 `memory_projection_policy`——由 `dataclasses.replace` 自然保留 ✓

**Verdict: PASS**。

---

## 完整覆盖矩阵

| 检查项目 | 状态 | 证据 |
|----------|------|------|
| `HostCommandHandleOptions` context budget 字段 | ✓ | api.py:1173-1176 |
| `_validate_command_context_budget_fields` 校验 | ✓ | api.py:1244-1268 |
| `compose_host_local_execution_options` wiring | ✓ | command.py:276-307 |
| budget → per-run request 隔离 | ✓ | test_public_contracts.py:808-838 |
| budget → metadata 隔离 | ✓ | test_public_contracts.py:808-838 |
| memory policy 独立 | ✓ | test_public_contracts.py:622 |
| compact artifact root 注入 | ✓ | command.py:299-300 |
| 类型 + docstring + pyright | ✓ | 0 errors |
| README 同步 | ✓ | README.md updated |
| `__all__` 出口 | ✓ | command.py:1204 |
| production entry 调用 | ✗ | 无 production caller → **F1 RESIDUAL** |
| 显式输入语义（默认值风险） | ✗ | 8192/1024 默认 → **F2 MEDIUM** |
| compactor 注入 (plan gap) | ✗ | 不设置 compactor → **F3 RESIDUAL** |
| full multi-turn E2E test | ✗ | plan 要求但未实现 → **F4 MEDIUM** |

---

## Findings Summary

| ID | Severity | Category | File:Line | Owner |
|----|----------|----------|-----------|-------|
| F1 | RESIDUAL | 无 production entry 调用 | command.py:276 | composition root owner |
| F2 | MEDIUM | 默认值削弱显式输入 | api.py:1173-1174 | Slice 6 owner |
| F3 | RESIDUAL | compactor 不注入 (plan gap) | command.py:290-307 | test owner |
| F4 | MEDIUM | 缺失 multi-turn E2E test | (none) | aggregate validation owner |
| — | PASS | budget 分层隔离 | test_public_contracts.py:808-838 | — |
| — | PASS | 类型/docstring/README/pyright | all files | — |

**Verdict: PASS_WITH_RESIDUAL** — 无 blocking finding。2 个 MEDIUM (F2 默认值语义、F4 缺失 E2E)，2 个 RESIDUAL (F1 无 production caller、F3 compactor 不注入)。所有 finding 有明确 owner 和建议修复方向，不阻塞当前 slice gate。

---

## 未覆盖风险 (Residual Risk)

1. **F2 — 默认值 8192/1024**: 若 composition root 忘记显式传入，系统静默使用默认值而不报警。建议移除默认值或增加 composition root 警告。
2. **F4 — 缺失 full multi-turn E2E**: plan 要求的 "多轮会话主体闭环" 无单一测试覆盖完整链路。当前分层测试覆盖组件正确性，但跨组件集成无端到端验证。
3. **F1 — 无 production 调用**: `compose_host_local_execution_options` 只有 test 调用方。这是 layer placement 的自然结果，等待 composition root 接入。
4. **F3 — Fake compactor test wiring**: plan 要求但未实现。S4/S5 测试通过直接构造 `FakeContextCompactor()` 绕过，不依赖此 slice。
5. **S4/S5 residuals 延续**: compactor/artifact write 在 DB transaction 内、budget estimate 只用 display_text、`promote_next_queued_run` 旧 API 表面——均不在 S6 修改范围内，owner 明确。
