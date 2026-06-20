# Code Review

## Scope

- Mode: current changes
- Branch: phase/wu-cm-15
- Base: 572a88df
- Output file: docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-mimo-20260620.md
- Included scope:
  - `docs/host/issues-implementation-control.md` — control doc gate/status 更新
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` — proactive pollution 测试、pressure bounds 断言调用
  - `utils/smoke_host_public_conversation_memory_scenarios.py` — reactive acceptance proactive guard、fallback failed_events guard、compactor runner hook AttributeError、pressure bounds 断言函数
- Excluded scope: `dayu/` production code（本次 diff 未修改）
- Parallel review coverage: 无

## Review Conclusion

**PASS**

未发现实质性问题。六项重点审查全部通过，详见下方逐项走读。

## Findings

未发现实质性问题。

## Adversarial Verification — 六项重点逐项走读

### 1. Reactive acceptance 是否拒绝 proactive requested/compacted/failed 污染，并有测试

**实现** (`utils/smoke_host_public_conversation_memory_scenarios.py:3591-3601`):

```python
if (
    summary.requested_proactive > 0
    or summary.compacted_proactive > 0
    or summary.failed_proactive > 0
):
    raise RuntimeError(
        "memory-reactive-compact observed unexpected proactive compact activity: ..."
    )
```

三个 proactive 污染维度全部覆盖：`requested_proactive`、`compacted_proactive`、`failed_proactive`。断言位于 reactive 信号检查之前，确保 proactive 污染在任何 reactive 验证之前就被拦截。

**测试** (`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:576-629`):

三种 proactive 污染场景全部显式测试：
1. 仅 proactive request（无 compacted/failed）
2. proactive request + proactive compacted
3. proactive request + proactive failed

每种均 `pytest.raises(RuntimeError, match="unexpected proactive compact activity")`。

**判定: PASS** — 实现语义正确，测试覆盖全部三个 proactive 维度的污染路径。

### 2. memory-compact --pressure-mode auto 启动期 pressure bounds 是否正确，仅作用于 SuiteMode.MEMORY_COMPACT + PressureMode.AUTO，不影响 fallback 数值

**实现** (`utils/smoke_host_public_conversation_memory_scenarios.py:3745-3790`):

```python
if suite is not SuiteMode.MEMORY_COMPACT or pressure_mode is not PressureMode.AUTO:
    return
```

守卫条件精确：仅当 `suite == MEMORY_COMPACT` **且** `pressure_mode == AUTO` 时才执行断言。其他 suite（`MEMORY_REACTIVE_COMPACT`、`MEMORY_COMPACT_FALLBACK`）或 mode（`OFF`）直接 return。

使用 `_COMPACT_PRESSURE_RESERVE_TOKENS`（575K），不触及 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS`（160K）。两个常量独立，无交叉影响。

**调用点** (`utils/smoke_host_public_conversation_memory_scenarios.py:2988`):

在 `run_smoke` 中，assembly 准备完成后、round specs 之前调用。对于 deterministic suites（`MEMORY_REACTIVE_COMPACT`、`MEMORY_COMPACT_FALLBACK`），`run_smoke` 在 line 2977-2979 提前 return 到 `_run_deterministic_compact_smoke`，根本不会到达此调用点——双重保护。

**测试** (`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:435-440`):

显式用 `PressureMode.AUTO` + `SuiteMode.MEMORY_COMPACT` 调用 `_assert_memory_compact_pressure_bounds`，验证断言通过。

**判定: PASS** — 守卫条件精确，常量隔离，调用点受 suite dispatch 保护，测试显式覆盖。

### 3. Fallback failed_events guard 是否语义化

**实现** (`utils/smoke_host_public_conversation_memory_scenarios.py:3669-3670`):

```python
if not failed_operation.failed_events:
    raise RuntimeError("memory-compact-fallback expected at least one failed compact event")
```

`failed_events` 类型为 `tuple[CompactFailedOperationAudit, ...]`（`CompactOperationAudit` line 815），`not tuple` 等价于 `len(tuple) == 0`。语义清晰：在访问 `[-1]` 之前确保至少有一个 failed event。

错误消息 "expected at least one failed compact event" 直接描述了断言意图，不是内部状态泄露。

**判定: PASS** — 语义化 guard，类型安全，错误消息面向业务。

### 4. Compactor runner hook AttributeError 是否语义化且 finally restore 不被破坏

**实现** (`utils/smoke_host_public_conversation_memory_scenarios.py:1857-1874`):

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
    ...
    yield
finally:
    llm_compaction._run_agent_request = original_runner
```

结构分析：两个独立的 `try` 块。第一个 `try/except` 捕获 `AttributeError` 并转为 `RuntimeError`（保留原始异常链 via `from exc`）。若此处抛出，函数立即退出，**第二个 `try/finally` 块从未进入**，因此 `finally` 中的 restore 不会引用未定义的 `original_runner`。

`RuntimeError` 消息语义化：说明了什么 hook 缺失（`_run_agent_request`）、在哪个模块（`dayu.host.llm_compaction`），不暴露内部堆栈。

**判定: PASS** — 结构上 finally restore 不会被破坏，错误消息语义化且保留异常链。

### 5. Control doc gate 文案、plan review chain 是否修正

**status table** (`docs/host/issues-implementation-control.md:146-153`):
- gate 从 `accepted-slice` 改为 `aggregate-review`
- implementation status 更新为引用 `572a88df` 并说明 aggregate deepreview gate 开启
- next entry point 更新为 "Run aggregate deepreview for WU-CM-15"
- blocking open questions 更新为 "None for WU-CM-15 aggregate-review gate"

**WU-CM-15 detail section** (`docs/host/issues-implementation-control.md:1890-1975`):
- 状态从 `accepted-slice` 改为 `aggregate-review`
- Implementation/Review 状态新增完整 plan review chain：initial plan review → adjudication → plan fix → focused re-review
- 新增 accepted implementation slice commit `572a88df`

**判定: PASS** — gate 文案与实际流程状态一致，plan review chain 完整记录。

### 6. 未做被明确禁止的公共 flow 抽取、模块拆分或 dayu production code 修改

**diff 范围确认**：
- `docs/host/issues-implementation-control.md` — 文档更新，非 production code
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` — 测试文件
- `utils/smoke_host_public_conversation_memory_scenarios.py` — `utils/` 下的分析辅助代码（CLAUDE.md: "分析辅助代码仅放在 `utils/`"）

无 `dayu/` 目录下的任何文件被修改。无新模块创建、无公共 flow 抽取、无模块拆分。

**判定: PASS** — 变更严格限定在 docs、tests、utils 范围内。

## Open Questions

无。

## Residual Risk

- `_assert_memory_compact_pressure_bounds` 仅在 `run_smoke` 入口处调用一次。若未来 `run_smoke` 的 control flow 变化导致该调用被跳过，bounds 断言将静默失效。当前 deterministic suites 有独立的 `_assert_fallback_pressure_bounds` 覆盖，风险可控。
- proactive pollution 测试依赖 `_compact_audit_report_from_rows` 正确构造 summary。该 helper 的内部实现若有回归，测试可能产生假阳性。当前该 helper 已有独立测试覆盖，风险低。
