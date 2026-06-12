# Code Review: WU-OBS-SIGNALS-01 / OBS-SIG-00

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main` (committed changes), `HEAD` (uncommitted changes)
- Output file: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-code-review-ds.md`
- Review timestamp: 2026-06-11T19:51:27+08:00
- Work unit: WU-OBS-SIGNALS-01
- Slice: OBS-SIG-00 Shared Tool Trace Signal Foundation
- Gate: code review
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Approved plan: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-implementation-codex.md`

### Included scope (reviewed files)

- `dayu/host/tool_trace.py` — uncommitted diff (production code)
- `tests/host/test_tool_trace_projection.py` — uncommitted diff (tests)
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-implementation-codex.md` — implementation artifact
- `docs/host/issues-implementation-control.md` — status bookkeeping diff reviewed for consistency

### Excluded scope

- `docs/host/wu-obs-signals-p01-p04-plan.md` — plan gate artifact, not implementation
- All prior plan review / re-review / controller adjudication artifacts — already accepted
- `dayu/host/durable/tool_trace.py` — not modified
- `dayu/host/engine_ingest.py`, `dayu/host/tool_runtime.py`, `dayu/host/context_budget.py` — not modified (scope: OBS-SIG-00 only)

### Parallel review coverage

无。本次 scope 集中在单一模块的两个文件，逐行走读。

## Review Method Summary

按以下顺序执行：

1. 阅读 plan gate artifact 确认 OBS-SIG-00 的 exact changes、allowed files、non-goals、error handling invariants、test requirements。
2. 阅读 `dayu/host/tool_trace.py` 完整 diff，沿 `_extract_tool_trace` -> `_extract_canonical_trace` / `_extract_diagnostic_trace` / `_extract_usage_trace` -> `_trace_summary_signals` -> `_optional_signal_object` -> `_TraceSummarySignals.present_items` -> `_trace_summary` -> `_build_hot_row` / `_build_cold_line` 链路逐行走读。
3. 检查 runner-call path (`_extract_runner_call_trace` -> `_runner_call_trace_summary`) 是否正确不引入 signals（设计决定）。
4. 阅读 `tests/host/test_tool_trace_projection.py` 完整 diff，逐测试验证断言覆盖 copy / missing-null / invalid-type reject 场景。
5. 执行 adversarial failure pass：空 object、bool/string/int/list 非法类型、diagnostic/usage 路径一致性、cold JSONL 同源性、`_build_cold_line` digest 正确性。
6. 检查 AGENTS.md / CLAUDE.md 合规性：类型签名、docstring、Any/object、magic string、兼容 seam、README 决策。
7. 运行 `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` 与 `pyright` 验证。

## Findings

未发现实质性问题。

### 逐项验证记录

#### 1. 是否只实现 OBS-SIG-00，没有提前实现 P01-P04 signal 值生产/提取

**通过。** diff 只在 `dayu/host/tool_trace.py` 中添加：

- 四个私有字段常量（`context_pressure`、`tool_timing`、`failure_metadata`、`partial_tool_call_signal`）。
- 私有 `_TraceSummarySignals` grouped carrier dataclass。
- `_trace_summary_signals` 与 `_optional_signal_object` helper 函数。
- 将 grouped carrier 接入 `_trace_summary`，再通过 `_extract_canonical_trace` / `_extract_diagnostic_trace` / `_extract_usage_trace` 三条路径复制已存在的 signal object。

未修改 `dayu/host/engine_ingest.py`、`dayu/host/tool_runtime.py`、`dayu/host/context_budget.py`。未新增任何 signal 值计算逻辑。`_trace_summary_signals` 只做类型验证与透传，不做内容推导。

#### 2. _trace_summary 是否通过 grouped carrier 避免 God function

**通过。** plan 要求"不要给 `_trace_summary` 加四个独立 optional 参数"。实现使用单个 `signals: _TraceSummarySignals` 参数，signal 字段的解包与排序由 `_TraceSummarySignals.present_items()` 封装。`_trace_summary` 自身的参数数量增长受控（从 14 个增加到 15 个 keyword-only 参数，其中 signals 是结构化 carrier）。函数签名清晰，每个参数语义独立，未出现上帝函数膨胀。

#### 3. signal 字段存在但非 object/null 是否 fail closed 为 HostDurableError

**通过。** `_optional_signal_object` (`tool_trace.py:1161-1177`) 逻辑：

```python
value = payload.get(field_name)
if value is None:
    return None
if not isinstance(value, Mapping):
    raise HostDurableError(f"tool trace {field_name} must be JSON object or null")
return cast(Mapping[str, JsonValue], value)
```

- 字段缺失（`payload.get` 返回 `None`）→ `None`，`present_items()` 不输出。
- 显式 `null`（JSON null → Python `None`）→ `None`，同上。
- 非 Mapping 类型（`str`、`int`、`list`、`bool`）→ `HostDurableError`，fail closed。
- 空 `{}`→ 合法 JSON object，透传（符合 spec，spec 不要求拒绝空 object）。

测试 `test_tool_trace_rejects_non_object_summary_signal_fields` 参数化覆盖四种非法类型（`str`、`int`、`list`、`bool`），断言 `pytest.raises(HostDurableError, match=field_name)`。

#### 4. hot/cold trace_summary 是否同源

**通过。** `_extract_*_trace` 各路径中，`extracted.trace_summary` 由 `_trace_summary(..., signals=...)` 统一构造一次，然后：

- `_build_hot_row` 使用 `trace_summary=extracted.trace_summary`（line 998）。
- `_build_cold_line` 使用 `_FIELD_TRACE_SUMMARY: extracted.trace_summary`（line 1058）。

hot row 与 cold JSONL 的 `trace_summary` 来自同一次 `_trace_summary` 调用，同源性保证。

测试 `test_tool_trace_copies_optional_summary_signal_objects` 末尾断言 `_cold_trace_summary(cold_lines, 0) == row.trace_summary` 验证 cold 与 hot 完全一致。既有测试 `test_tool_call_chain_projects_hot_rows_and_cold_lines` 也继续断言 cold summary 与 hot row 一致。

#### 5. 测试是否覆盖复制、缺失/null 不输出、非法类型 fail closed

**通过。** 三个新增测试：

| 测试 | 覆盖场景 |
| --- | --- |
| `test_tool_trace_copies_optional_summary_signal_objects` | 四类 signal object 均被复制到 hot row 和 cold JSONL 的 `trace_summary` |
| `test_tool_trace_omits_missing_or_null_summary_signal_objects` | 缺失信号字段（payload 不含 key）和显式 `null` 均不在 hot/cold summary 中输出 |
| `test_tool_trace_rejects_non_object_summary_signal_fields` | 参数化覆盖 `str`、`int`、`list`、`bool` 四种非法类型，断言 `HostDurableError` 且匹配字段名 |

既有测试（runner-call、correlation、cold writer failure、rebuild、source key conflict）全部保持通过。

#### 6. 是否违反 AGENTS.md / CLAUDE.md

**通过。** 逐项检查：

- **类型签名**：`_TraceSummarySignals` 字段类型为 `Mapping[str, JsonValue] | None`；`_trace_summary_signals` 返回 `_TraceSummarySignals`；`_optional_signal_object` 返回 `Mapping[str, JsonValue] | None`。无 `Any`、无 `object`、无无类型参数。
- **中文 docstring**：`_TraceSummarySignals`、`present_items`、`_trace_summary_signals`、`_optional_signal_object` 均有完整中文 docstring 含参数、返回值、异常说明。
- **无 magic string**：四个 signal 字段名均为模块级私有常量（`_FIELD_CONTEXT_PRESSURE` 等），测试侧使用同名常量引用。
- **无兼容 seam**：未新增 re-export、兼容性常量或 wrapper。
- **README 决策**：implementation artifact 记录已阅读 `dayu/host/README.md` 和 `tests/README.md` 的 Agent 更新约束，判断本轮不需要更新。判断依据合理：未改变 public API、架构边界、package contract 或测试运行命令。
- **pyright**：`0 errors, 0 warnings, 0 informations`。
- **test**：21 passed，覆盖新增行为和既有行为。

#### 7. Adversarial Failure Pass

执行以下 adversarial 检查，均未发现缺陷：

| 场景 | 检查结果 |
| --- | --- |
| signal 字段值为空 list `[]` | `isinstance([], Mapping)` → `False` → `HostDurableError` |
| signal 字段值为数字 `0` | `isinstance(0, Mapping)` → `False` → `HostDurableError` |
| signal 字段值为空字符串 `""` | `isinstance("", Mapping)` → `False` → `HostDurableError` |
| signal 字段值为 `True`/`False` | `isinstance(True, Mapping)` → `False` → `HostDurableError` |
| signal 字段值为空 object `{}` | `isinstance({}, Mapping)` → `True` → 透传（符合 spec） |
| diagnostic/usage 路径 signal 复制一致性 | 两个路径均调用 `_trace_summary_signals(payload)`，与 canonical 路径使用同一 helper |
| cold line digest 包含 signal 字段 | `_build_cold_line` 的 `sha256_digest_json(fields_without_digest)` 在 signal 写入 `trace_summary` 之后计算，digest 覆盖 signal 内容 |
| runner-call 路径不引入 signal | `_extract_runner_call_trace` 使用 `_runner_call_trace_summary(event)`，不经过 `_trace_summary`，不读取 signal 字段。设计正确——runner-call summary 有独立结构 |
| signal 字段不与 cold line 顶层字段冲突 | signal 字段名（`context_pressure` 等）不在 `fields_without_digest` 顶层 dict 中，仅出现在嵌套的 `trace_summary` object 内 |
| 现有消费者兼容性 | signal 字段是 `trace_summary` 内 additive optional key，不删除、不重命名既有字段，不改变 EventLog payload schema、SQLite schema 或 ToolRuntime 语义 |

## Open Questions

无。

## Residual Risk

- **R1: signal 内部结构无校验**。OBS-SIG-00 只验证 signal 字段是 JSON object，不校验内部字段（`schema_version`、`status`、`signal_source` 等）。Risk owner：后续 P01-P04 各 slice 负责在 producer 侧保证 signal 内部结构正确；若 producer 写入无意义 JSON object，projection 会透传。Severity：低——后续 slice 已有明确的 signal shape contract，且 analyzer 需要处理 limited signal，空 object 会被视为 `status` 缺失的异常信号。
- **R2: runner-call path 不消费 signal**。`_extract_runner_call_trace` 调用 `_runner_call_trace_summary` 而非 `_trace_summary`，因此 runner-call events 即使 payload 中包含 signal 字段也不会进入 trace_summary。Risk owner：目前 plan 中 signal 来源（TOOL_RESULT_ACCEPTED、USAGE_REPORTED、PROVIDER_PROTOCOL_ERROR、context compaction events）均非 runner-call event，无需处理。若未来需要在 runner-call 路径暴露 signal，需显式设计。Severity：低——当前 plan 无此需求。
- **R3: 仅 canonical path 测试 signal copy**。新增测试 `test_tool_trace_copies_optional_summary_signal_objects` 使用 `TOOL_RESULT_ACCEPTED`（canonical path），未单独测试 diagnostic path（PROVIDER_PROTOCOL_ERROR）或 projection_signal path（USAGE_REPORTED）的 signal 复制。但因三条路径共用 `_trace_summary_signals` + `_trace_summary`，且 diagnostic/usage 路径的既有测试（query tests）已通过，风险很低。Severity：低——后续 P01-P04 slice 各自的 projection 测试会覆盖对应路径。

## Completion Report

- **Artifact path**: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-code-review-ds.md`
- **Verdict**: PASS — 未发现实质性问题
- **Finding count**: 0
- **Blocking open questions**: 无
- **Validation executed**:
  - `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` — 21 passed in 0.40s
  - `pyright` — 0 errors, 0 warnings, 0 informations
- **Recommendation**: 可进入下一 gate（OBS-SIG-01 P01 implementation）。
