# Code Review

## Scope

- Mode: current changes (focused re-review, relative to `572a88df`)
- Branch: `phase/wu-cm-15`
- Base: `572a88df`
- Output file: `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-ds-20260620.md`
- Included scope:
  - `docs/host/issues-implementation-control.md` (control doc gate 文案和 plan review chain)
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` (assembly test 新增 reactive pollution 与 pressure bounds 覆盖)
  - `utils/smoke_host_public_conversation_memory_scenarios.py` (reactive pollution guard、pressure bounds 启动期断言、fallback failed_events guard、compactor runner hook AttributeError)
- Excluded scope: 无。仅审阅上述三个文件的未提交改动。
- Parallel review coverage: 无。本次为聚焦 re-review，由主 reviewer 逐条走读。

## Findings

未发现实质性问题。

所有 6 项聚焦审查点均 PASS：

### 1. Reactive acceptance 拒绝 proactive requested/compacted/failed 污染 — PASS

**Guard（生产路径）**: `_assert_reactive_compact_acceptance` — `utils/smoke_host_public_conversation_memory_scenarios.py:3594-3604`

```python
if (
    summary.requested_proactive > 0
    or summary.compacted_proactive > 0
    or summary.failed_proactive > 0
):
    raise RuntimeError(
        "memory-reactive-compact observed unexpected proactive compact activity: "
        f"requested_proactive={summary.requested_proactive} "
        f"compacted_proactive={summary.compacted_proactive} "
        f"failed_proactive={summary.failed_proactive}"
    )
```

逐行走读确认：
- 入口 `_assert_reactive_compact_acceptance` 在 `summary = report.summary` 后首先执行 proactive 污染检查（行 3593-3604），先于 reactive 信号断言（行 3605-3610）。
- 检查了 `requested_proactive`、`compacted_proactive`、`failed_proactive` 三个维度，覆盖 "requested-only"、"requested+compacted"、"requested+failed" 三种污染模式。
- 错误消息包含具体计数，可诊断。

**测试覆盖**: `test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals` — `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:579-629`

三组 polluting rows 逐组验证：
1. 仅 proactive requested（`trigger_source: "proactive"`）→ `RuntimeError("unexpected proactive compact activity")`
2. proactive requested + compacted → `RuntimeError("unexpected proactive compact activity")`
3. proactive requested + failed → `RuntimeError("unexpected proactive compact activity")`

所有三组均正确触发异常，`match="unexpected proactive compact activity"` 匹配 guard 抛出的异常消息。

**结论**: PASS。

### 2. memory-compact --pressure-mode auto 启动期 pressure bounds 正确 — PASS

**Guard**: `_assert_memory_compact_pressure_bounds` — `utils/smoke_host_public_conversation_memory_scenarios.py:3745-3790`

逐行走读确认：
- **Scope 守卫（行 3760）**: `if suite is not SuiteMode.MEMORY_COMPACT or pressure_mode is not PressureMode.AUTO: return` — 使用 identity 比较（enum singleton），仅当 `SuiteMode.MEMORY_COMPACT` 且 `PressureMode.AUTO` 同时成立时继续执行；其他任何 suite/mode 组合均为 no-op 早退。
- **Reserve 常量（行 3765）**: 使用 `_COMPACT_PRESSURE_RESERVE_TOKENS`（575_000），**不是** `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS`（160_000）。fallback 的 reserve 值完全独立，不受本函数影响。
- **压力计算公式（行 3766-3768）**: `prompt_tokens + tool_pressure_tokens + reserve_tokens`，与同一文件中已有的 `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 汇编测试中的手工计算完全一致。
- **Bounds 断言（行 3777-3790）**: 分别检查 `pressure_tokens < soft_threshold_tokens`（below）和 `pressure_tokens >= hard_threshold_tokens`（reached），语义清晰，错误消息包含所有关键数值。

**调用点**:
- `run_smoke`（行 2991）: 仅对非 deterministic suite（即 `MEMORY_COMPACT`）生效；`MEMORY_REACTIVE_COMPACT` / `MEMORY_COMPACT_FALLBACK` 在行 2982-2986 已提前分发到 `_run_deterministic_compact_smoke`，不会进入本路径。
- Assembly test（行 438-442）: 显式以 `PressureMode.AUTO, SuiteMode.MEMORY_COMPACT` 调用，验证函数在正确模式下不会异常。

**Fallback 不影响验证**: fallback suite 使用独立的 `_fallback_pressure_observation`（行 3496-3533）计算 `FallbackPressureObservation`，其 `pressure_tokens` 来自 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS`（160_000）；fallback 验收使用 `_assert_fallback_pressure_bounds`（行 3719-3742）读取 `observation.pressure_tokens`。两条路径在常量、计算函数和断言函数上完全独立。

**结论**: PASS。

### 3. fallback failed_events guard 语义化 — PASS

**Guard（行 3670-3671）**:
```python
if not failed_operation.failed_events:
    raise RuntimeError("memory-compact-fallback expected at least one failed compact event")
```

逐行走读确认：
- `failed_operation` 来自 `_fallback_failed_operation(report)`（行 3667），该函数（行 3793-3808）返回 `CompactOperationAudit`，其 `failed_events` 字段类型为 `tuple[CompactFailedOperationAudit, ...]`（行 823）。
- `not failed_operation.failed_events` 对空 tuple `()` 求值为 `True`，正确捕获"没有 failed event"的情况。
- 错误消息 "memory-compact-fallback expected at least one failed compact event" 语义清晰，直接说明期望与实际不符。
- guard 之后立即使用 `failed_operation.failed_events[-1]`（行 3672）取最后一个 failed event 做 `fallback_action` 验证，guard 确保了索引安全。

**结论**: PASS。

### 4. compactor runner hook AttributeError 语义化且 finally restore 不被破坏 — PASS

**实现**: `_patched_compactor_runner` — `utils/smoke_host_public_conversation_memory_scenarios.py:1851-1874`

```python
try:
    original_runner = llm_compaction._run_agent_request
except AttributeError as exc:
    raise RuntimeError(
        "Host compactor runner hook changed: "
        "dayu.host.llm_compaction._run_agent_request is missing"
    ) from exc
try:
    llm_compaction._run_agent_request = runner
    if llm_compaction._run_agent_request is not runner:
        raise RuntimeError("failed to patch dayu.host.llm_compaction._run_agent_request")
    yield
finally:
    llm_compaction._run_agent_request = original_runner
```

逐行走读确认：
- **AttributeError 语义化**: 将裸 `AttributeError`（模块属性缺失）转换为 `RuntimeError("Host compactor runner hook changed: dayu.host.llm_compaction._run_agent_request is missing")`，消息明确指出变更位置和影响，使用 `from exc` 保留原始异常链，不丢失诊断信息。
- **finally restore 不被破坏**: `original_runner` 赋值（行 1862）在 `try/except AttributeError` 内——要么成功赋值，要么抛 `RuntimeError` 退出函数。`try/finally` 块（行 1868-1874）仅在 `original_runner` 已成功绑定时进入。`finally` 块中 `llm_compaction._run_agent_request = original_runner` 不会遇到 `UnboundLocalError`。
- **patch 验证**: 赋值后立即验证 `llm_compaction._run_agent_request is not runner`（行 1870），提供早期失败检测。
- **嵌套 try 结构正确**: 外层 `try/except AttributeError` 只包裹属性访问，内层 `try/finally` 包裹 patch → yield → restore 完整生命周期。如果 AttributeError 触发，控制流在抛 `RuntimeError` 后离开函数，不进入内层 `try/finally`，无残留副作用。

**结论**: PASS。

### 5. control doc gate 文案、plan review chain 修正 — PASS

**Gate 变更**:
- `gate` 从 `accepted-slice` 更新为 `aggregate-review`（行 146）。
- `implementation status` 从 "implementation and code-review fix completed. Focused re-review PASS" 更新为 "accepted implementation slice commit `572a88df` created. Aggregate deepreview gate is open"（行 147）。
- `next entry point` 从 "Create accepted implementation slice commit" 更新为 "Run aggregate deepreview for WU-CM-15, adjudicate findings, then either fix or proceed to final closeout / draft PR gate"（行 150）。
- `blocking open questions` 从 "accepted-slice gate" 更新为 "aggregate-review gate"（行 153）。

**Plan review chain（行 1960-1974）**:
完整链已记录：
```
accepted plan → initial plan review (MiMo + DS) → plan review adjudication →
plan fix → focused plan re-review (MiMo + DS) →
implementation artifact → code review (DS + MiMo) → code review adjudication →
fix artifact → focused re-review (MiMo + DS) → focused re-review adjudication →
accepted implementation slice commit
```

每个环节均记录了具体文件路径和 reviewer 标识，与 `docs/reviews/` 下已有文件一致。

**WU-CM-15 状态（行 1893）**: 从 `accepted-slice` 更新为 `aggregate-review`，与 gate 字段同步。

**结论**: PASS。

### 6. 未做被明确禁止的公共 flow 抽取、模块拆分或 dayu production code 修改 — PASS

**文件改动清单**:
```
docs/host/issues-implementation-control.md   (control doc)
tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py  (assembly test)
utils/smoke_host_public_conversation_memory_scenarios.py  (smoke util)
```

**确认**:
- `git diff 572a88df --name-only -- dayu/` 无输出：`dayu/` 目录下零改动。
- 无新增公共模块、无模块拆分、无 flow 抽取。
- 所有改动均在 `utils/`（分析辅助代码）、`tests/`（测试）和 `docs/`（文档）范围内，符合项目目录约束。

**结论**: PASS。

## Open Questions

- **reactive acceptance 未检查 `rejected_proactive`**: `_assert_reactive_compact_acceptance` 的 proactive pollution guard 检查了 `requested_proactive`、`compacted_proactive`、`failed_proactive`，但未检查 `summary.rejected_proactive`。若 reactive-only 场景中出现 proactive rejected 事件（例如因并发 compact 被拒绝），同样说明 proactive 路径被触发，属于污染。当前用户需求明确列出 requested/compacted/failed 三项，但 `rejected_proactive` 的覆盖缺口是否需要在后续补充，取决于用户裁决。

- **`_assert_memory_compact_pressure_bounds` 在 assembly test 中仅测试正向路径**: 当前 test 只在 `PressureMode.AUTO + SuiteMode.MEMORY_COMPACT` 下验证函数通过，未显式验证早退路径（其他 suite/mode 组合下为 no-op）。早退逻辑足够简单（行 3760 的 `is not` guard），风险极低，但严格来说缺乏 negative case 的 assembly 级覆盖。

## Residual Risk

- **无 real-provider 端到端验证的 `memory-compact` auto pressure bounds**: `_assert_memory_compact_pressure_bounds` 的启动期断言依赖于 `_COMPACT_PRESSURE_RESERVE_TOKENS = 575_000`，该预留值是为真实模型输出涨幅预留的。若真实 compactor provider 输出显著超出预留（例如模型升级后输出量变化），bounds 断言可能误报。这属于环境/模型演进风险，不是当前代码逻辑缺陷。与 control doc 中记录的 "Real-provider `memory-compact` smoke still depends on a valid compactor provider key" 一致。

- **reactive pollution test 的 boundary case**: 当前 test 使用 `base_rows`（两个 reactive event）+ `polluted_rows`（1-2 个 proactive event）构造 scenario。未覆盖 proactive event 出现在 reactive event 之前（而非之后）的场景。但从 `_compact_audit_report_from_rows` 的实现来看，summary 计数只依赖于 event type 和 trigger_source，与 sequence 排序无关，因此排序不影响 guard 行为。低风险。
