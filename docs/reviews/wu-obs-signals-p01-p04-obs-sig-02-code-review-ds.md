# WU-OBS-SIGNALS-01 / OBS-SIG-02 Code Review — AgentDS

## Gate

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `code review`
- Slice: `OBS-SIG-02 / P02 Tool Duration Signal`
- Reviewer: AgentDS
- Artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-ds.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Accepted plan: `docs/host/wu-obs-signals-p01-p04-plan.md` P02 section (lines 236-273)
- Implementation report: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-implementation-codex.md`

## Scope

Review `OBS-SIG-02` implementation — tool duration signal from `ToolResultMeta` → `TOOL_RESULT_ACCEPTED` payload → Tool Trace projection. Validate correctness, stability, architecture alignment, AGENTS.md constraint compliance, and test coverage. Do not modify production code, commit, push, or open PR.

---

## Findings

### Finding 1 — PASS: Motivation 与 Root Cause 成立

**严重度**: 信息性 — 无缺陷

**证据**:
- `dayu/contracts/tool_result.py:27-60`: `ToolResultMeta` 是 durable accepted outcome 的稳定真源，`__post_init__` 已校验 `finished_at >= started_at` 与 timezone awareness 一致。
- `dayu/contracts/tool_outcome.py:62-115`: `ToolCompletedOutcome.result.meta`、`ToolFailedOutcome.result.meta`、`ToolCancelledOutcome.meta` 均为 `ToolResultMeta | None` — 三种可进入 accept path 的终态 outcome 都有 meta。`ToolAwaitingOutcome` 没有 meta，实现正确拒绝。
- `dayu/host/tool_runtime.py:5927-5953` (`_tool_timing_from_meta`): 从 meta 的 `finished_at - started_at` 计算 `duration_ms`，来源是工具执行开始/结束时间，不是 projection 时间或 Engine wall-clock 猜测。

**影响**: 动机成立。duration 来源是工具自身记录的执行边界，不依赖日志解析、进程内计时或投影时间反推。

**建议**: 无需改动。

---

### Finding 2 — PASS: Producer 覆盖全部终态 Outcome

**严重度**: 信息性 — 无缺陷

**证据**:
- `dayu/host/tool_runtime.py:5908-5924` (`_tool_result_meta`):
  - `ToolCompletedOutcome` → `outcome.result.meta`
  - `ToolFailedOutcome` → `outcome.result.meta`
  - `ToolCancelledOutcome` → `outcome.meta`
  - `ToolAwaitingOutcome` → `TypeError` (不携带 accepted result timing)
  - 未知类型 → `TypeError` (防御性收口)
- `dayu/host/tool_runtime.py:5514-5521` (`_tool_fact_accept_candidate`): 所有 accept candidate 统一通过 `_tool_result_meta(outcome)` 提取 meta 并传入 `ToolAcceptResult.tool_timing`。
- `dayu/host/tool_runtime.py:3807-3810` (`_tool_result_payload`): `tool_timing` 作为固定字段写入 `TOOL_RESULT_ACCEPTED` payload，不依赖 outcome 类型分支。

**影响**: completed / failed / cancelled 三种终态 outcome 的 timing 全部覆盖。awaiting outcome 被显式拒绝，不会静默丢失 timing。GOVERNED_ERROR（policy block）场景下 outcome 仍是 `ToolFailedOutcome`，meta 通常为 None，产生 `missing_tool_result_meta` 信号。

**建议**: 无需改动。

---

### Finding 3 — PASS: Missing Meta 产生显式 Limited Signal

**严重度**: 信息性 — 无缺陷

**证据**:
- `dayu/host/tool_runtime.py:5935-5943` (`_tool_timing_from_meta`): `meta is None` 时返回 `status="missing_tool_result_meta"`，所有 timing 字段设为 `null`，`duration_source` 为 `null`。
- `dayu/host/tool_runtime.py:4391-4397` (`_validate_tool_timing_signal`): `missing_tool_result_meta` 状态下校验所有 timing 字段必须为 `null`——防御性防止不完整信号。
- `dayu/host/tool_trace.py:1347-1357` (`_optional_tool_timing_signal`): 对 `missing_tool_result_meta` 做同样校验，确保 projection 不传播非法混合状态。
- 缺失 meta **不** fail tool accept 或 projection——下游 analyzer 可据此报告 "limited signal"。

**影响**: Missing meta 不会导致 `TOOL_RESULT_ACCEPTED` 失败、run 失败或 projection 失败。analyzer 可通过 `status` 字段区分"有耗时数据"和"工具未提供 meta"。

**建议**: 无需改动。

---

### Finding 4 — PASS: Duration 语义正确且 Defense-in-Depth 充分

**严重度**: 信息性 — 无缺陷

**证据**:
- `dayu/host/tool_runtime.py:5944-5953` (`_tool_timing_from_meta`): `duration_ms = int((meta.finished_at - meta.started_at) // _ONE_MILLISECOND)`。`_ONE_MILLISECOND = timedelta(milliseconds=1)` 是模块级常量，避免魔法数字。
- `dayu/contracts/tool_result.py:56-59`: `ToolResultMeta.__post_init__` 已保证 `finished_at >= started_at`，因此在生产路径中不可能产生负 `duration_ms`。
- `dayu/host/tool_runtime.py:5945-5946`: Producer 仍然显式校验 `duration_ms < 0`，作为 defense-in-depth。
- `dayu/host/tool_runtime.py:4381-4387`: Producer 校验 `duration_ms` 为非负整数（且拒绝 `bool` 类型的 Python `True`/`False` 被误判为 1/0）。
- `dayu/host/tool_trace.py:1335-1339`: Consumer 独立校验 `duration_ms >= 0`，对 EventLog 中可能的 malformed 数据 fail closed。
- `int()` wrap 在 `//` 上是冗余的（`timedelta // timedelta` 返回 `int`），但不造成语义错误。

**影响**: Duration 计算链完整：meta 校验 → producer 计算 → producer 校验 → EventLog 持久化 → consumer 独立校验。每一层都有类型/边界守卫。

**建议**: 无需改动。`int()` wrap 是防御性无害冗余，可保留。

---

### Finding 5 — PASS: 分层边界完整，无 Scope Creep

**严重度**: 信息性 — 无缺陷

**证据**:
- Engine public contract: 未修改。`ToolResultMeta`、`ToolExecutionOutcome`、`BatchToolExecutionOutcome` 等均为 Engine contracts 已有类型。
- SQLite schema: 未修改。`tool_timing` 写入已有 `trace_summary_json` 字段，未新增列。
- ToolExecutor scheduling: 未修改。`_tool_fact_accept_candidate` 只在 accept path 中调用，不改变 execute/timeout/cancel 语义。
- Timeout / cancel / accept retry / duplicate governance: 未修改。`tool_timing` 是纯附加字段，不参与任何治理决策。
- P03 / P04: 未实现。`failure_metadata` 和 `partial_tool_call_signal` 在 `_TraceSummarySignals` 中仍走 `_optional_signal_object` 通用路径，P02 只替换了 `tool_timing` 为专用校验。
- Analyzer aggregation: 未实现。`duration_ms` 是单行字段，median/p99/distribution 等聚合属于 `WU-OBS-00`。

**影响**: 所有变更限于 `dayu/host/` 层，未触及 Engine contract、SQLite durable schema 或 ToolRuntime execution semantics。无 scope creep。

**建议**: 无需改动。

---

### Finding 6 — PASS: Projection Hot/Cold 同源且 Fail-Closed

**严重度**: 信息性 — 无缺陷

**证据**:
- `dayu/host/tool_trace.py:1297-1312` (`_trace_summary_signals`): `tool_timing` 通过 `_optional_tool_timing_signal(payload)` 读取，与 `trace_summary_json` 中其他 signal 走同一入口。
- `dayu/host/tool_trace.py:1315-1358` (`_optional_tool_timing_signal`):
  - 缺失/`null` → 返回 `None`，不写入 `trace_summary`（non-failing limited signal）。
  - 非 object 类型 → `HostDurableError`（由 `_optional_signal_object` 抛出）。
  - 不支持的 `schema_version` → `HostDurableError`。
  - 不支持的 `status` → `HostDurableError`。
  - `available` 状态下 `duration_ms < 0` → `HostDurableError`。
  - `available` 状态下 `duration_source != "tool_result_meta"` → `HostDurableError`。
  - `missing_tool_result_meta` 状态下任何非 null 字段 → `HostDurableError`。
- 测试 `test_tool_trace_copies_optional_summary_signal_objects` 和 `test_tool_trace_projects_tool_timing_available_and_missing_signals` 验证 hot row `trace_summary` 与 cold JSONL 中的 `tool_timing` 一致。

**影响**: Projection 只 copy/validate，不重新计算。Malformed payload fail closed，missing signal non-failing。Hot/cold 同源验证通过。

**建议**: 无需改动。

---

### Finding 7 — PASS: AGENTS.md 编码约束合规

**严重度**: 信息性 — 无缺陷

**证据**:

| 约束 | 状态 | 证据 |
|------|------|------|
| 中文 docstring 完整 | ✅ | `_tool_result_meta` (line 5908-5914), `_tool_timing_from_meta` (line 5927-5933), `_validate_tool_timing_signal` (line 4360-4365), `_require_signal_text` (line 4401-4407), `_optional_tool_timing_signal` (line 1315-1322), `_required_int` (line 1537-1543) — 全部有参数/返回值/异常 docstring |
| 无 `Any`/`object`/无类型签名 | ✅ | 所有新增函数有完整类型标注：`-> ToolResultMeta \| None`, `-> Mapping[str, JsonValue]`, `-> str`, `-> int` |
| 无兼容 seam | ✅ | 无 re-export, 无 facade, 无 wrapper |
| 无 `hasattr`/`getattr` 滥用 | ✅ | 未使用 |
| 无 magic string 扩散 | ✅ | `_TOOL_TIMING_STATUS_AVAILABLE`, `_TOOL_TIMING_STATUS_MISSING_META`, `_TOOL_TIMING_DURATION_SOURCE_META` 等均为模块级常量 |
| 无 unnecessary 嵌套函数 | ✅ | 所有新增函数为模块级私有函数 |
| 无 God object/function | ✅ | `_trace_summary_signals` 通过 grouped carrier `_TraceSummarySignals` 传递，未新增独立 parameter |
| 无显式参数进 `extra payload` | ✅ | `tool_timing` 是 `ToolAcceptResult` 的显式字段 |

**LLM-facing 文本**: `tool_timing` 信号是内部 diagnostic signal，写入 EventLog canonical fact `TOOL_RESULT_ACCEPTED`，属于 durable truth 的一部分。它不直接进入 LLM prompt context。未来的 analyzer 如果需要将其翻译为 LLM-facing 文本，应在 analyzer 层按 AGENTS.md 语义约束改写，不暴露裸 `duration_ms`、`schema_version`、`duration_source` 等字段作为推理依据。

**建议**: 无需改动。

---

### Finding 8 — OBSERVATION: Producer/Consumer 校验逻辑近似重复

**严重度**: 低 — 非阻塞

**证据**:
- `dayu/host/tool_runtime.py:4360-4398` (`_validate_tool_timing_signal`): Producer 校验，抛出 `ValueError`。
- `dayu/host/tool_trace.py:1315-1358` (`_optional_tool_timing_signal`): Consumer 校验，抛出 `HostDurableError`。

两处对 `available` / `missing_tool_result_meta` 状态下的字段存在性、类型、nullability 做了结构相同的校验。若未来 `tool_timing` shape 演进（如新增 field），两处需同步更新。

**影响**: 当前 shape 简单（5 个固定字段），重复度低。若后续 P03/P04 引入更复杂 signal shape，可考虑抽取 shared validation contract。当前阶段不构成维护风险。

**建议**: 当前无需改动。若后续 OBS-SIG-03/04 引入类似 producer/consumer 校验模式且 shape 更复杂，再评估是否需要抽取 `dayu/contracts/` 下的共享 signal validator。

---

### Finding 9 — OBSERVATION: `_require_signal_text` 返回 `str` 但调用方不使用返回值

**严重度**: 低 — 非阻塞

**证据**:
- `dayu/host/tool_runtime.py:4379`: `_require_signal_text(signal, "started_at")` — 返回值丢弃。
- `dayu/host/tool_runtime.py:4380`: `_require_signal_text(signal, "finished_at")` — 返回值丢弃。
- `dayu/host/tool_trace.py:1333`: `_required_text(signal, "started_at")` — 同样丢弃返回值。
- `dayu/host/tool_trace.py:1340`: `_required_text(signal, "duration_source")` — 使用返回值做相等比较，这是实际需要返回值的唯一路径。

**影响**: `_require_signal_text` 被设计为 validation-only helper，返回 `str` 语义上允许调用方使用返回值。当前调用方只用它做校验，不影响正确性。

**建议**: 无需改动。若希望更精确表达 validation-only 语义，可改为返回 `None`，但当前模式与 `_required_text` 签名保持一致性，有利于可读性。

---

## Open Questions

无。

## Residual Risk

| 风险 | 严重度 | Owner | 缓解 |
|------|--------|-------|------|
| 第三方工具不填充 `ToolResultMeta` 时 analyzer 只能报告 limited signal | 低 | `WU-OBS-00` | `status="missing_tool_result_meta"` 是显式信号，analyzer 可据此区分"无数据"和"有数据"，不会静默丢失 |
| Producer/consumer 校验逻辑如不同步演进可能导致 shape drift | 低 | 后续 OBS slice | 当前 shape 简单（5 字段），双侧独立校验是防御性正确的设计；后续若引入更复杂 shape，可在 plan gate 评估抽取共享 contract |

## Scope Creep Assessment

Pass. 变更严格限于 OBS-SIG-02 范围：

- ✅ 只在 `dayu/host/tool_runtime.py` 和 `dayu/host/tool_trace.py` 中新增/修改代码。
- ✅ 未修改 Engine public contract、SQLite schema、ToolExecutor scheduling。
- ✅ 未实现 P03 structured failure metadata 或 P04 partial tool-call signal。
- ✅ 未实现 analyzer aggregation（median/p99/distribution 等）。
- ✅ 未修改 timeout/cancel/accept retry/duplicate governance 语义。
- ✅ `docs/host/issues-implementation-control.md` 的 gate bookkeeping 更新正确：gate 从 `implementation` 推进到 `code review`，status 更新为 `OBS-SIG-02 implementation completed and entering code review`，`next entry point` 指向 `OBS-SIG-02 code review gate via AgentMiMo / AgentDS`。

## Architecture Alignment

Pass. 所有变更与 `docs/host/design.md` 和 `docs/engine/design.md` 的设计事实对齐：

- `docs/host/design.md:1355-1369`: EventLog canonical fact 是治理真源 → `tool_timing` 作为 additive payload field 写入 `TOOL_RESULT_ACCEPTED`，不改变治理语义。
- `docs/host/design.md:1652-1663`: Tool Trace 是 EventLog 派生 projection → `tool_timing` 由 projection consumer 从 EventLog 读取并复制，不新增 source of truth。
- `docs/engine/design.md:303-325`: `ToolExecutionOutcome` 和 `ToolResultMeta` 是 Engine 已有公共契约 → OBS-SIG-02 只消费已有契约，不新增 Engine 导出。
- `docs/engine/design.md:423-483`: EngineEvent stream 是中性事件边界，调用方需在 Engine 外部 ingest 成 durable facts → Host EventLog 的 `TOOL_RESULT_ACCEPTED` 已经是 Host-owned durable fact，`tool_timing` 是在该 fact 上的 additive projection。

## Test Coverage Assessment

### 覆盖矩阵

| 场景 | 文件 | 测试 | 状态 |
|------|------|------|------|
| Producer: meta present → tool_timing available | `test_phase6_toolruntime_integration.py:373-436` | `test_toolruntime_result_payload_carries_duration_from_result_meta` | ✅ |
| Producer: meta absent → missing_tool_result_meta | `test_phase6_toolruntime_integration.py:294-310` | `test_engine_continues_only_after_toolruntime_host_accept` (新增 assertion) | ✅ |
| Projection: available + missing signals in hot/cold | `test_tool_trace_projection.py:462-528` | `test_tool_trace_projects_tool_timing_available_and_missing_signals` | ✅ |
| Projection: optional signal copy in existing test | `test_tool_trace_projection.py:440-488` | `test_tool_trace_copies_optional_summary_signal_objects` (更新 fixture) | ✅ |
| Projection: negative duration → HostDurableError | `test_tool_trace_projection.py:531-596` | `test_tool_trace_rejects_malformed_tool_timing_signal[negative duration]` | ✅ |
| Projection: non-integer duration → HostDurableError | `test_tool_trace_projection.py:531-596` | `test_tool_trace_rejects_malformed_tool_timing_signal[string duration]` | ✅ |
| Projection: missing-meta with non-null field → HostDurableError | `test_tool_trace_projection.py:531-596` | `test_tool_trace_rejects_malformed_tool_timing_signal[started_at non-null]` | ✅ |
| Existing tests: accept barrier with tool_timing | `test_toolruntime_accept_barrier.py` | `test_tool_accept_result_rejects_payload_ref_digest_mismatch`, `_completed_candidate()`, `_fact_kind_candidate()` | ✅ |
| Existing tests: executor with tool_timing | `test_toolruntime_executor.py:1338-1348` | `_accepted_ack_for_call()` | ✅ |
| Consumer impact: no state-machine side effect | All above | ToolRuntime execution semantics unchanged, Run/Attempt status unchanged | ✅ |

### 未覆盖场景

- `_tool_result_meta` 收到 `ToolAwaitingOutcome` → 抛出 `TypeError`: 此为防御性 guard，awaiting outcome 不会进入 accept path。如需要可直接用 `pytest.raises(TypeError)` 覆盖，但当前集成测试已通过 full accept path 隐式验证 awaiting 路径不会触发 meta 提取。
- `_tool_timing_from_meta` 中 `duration_ms < 0` 的 `ValueError`: 由 `ToolResultMeta.__post_init__` 保证不可达，production path 中无法触发。投影层的 malformed 测试已覆盖负 duration 的 consumer 路径。

### Pyright

```
0 errors, 0 warnings, 0 informations
```

## Validation

独立重新运行受影响的测试与 pyright：

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py \
  tests/host/test_phase6_toolruntime_integration.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_toolruntime_executor.py -v
```

结果: **80 passed in 0.61s**

```bash
source .venv/bin/activate && pyright
```

结果: **0 errors, 0 warnings, 0 informations**

测试与 pyright 结果与 implementation artifact 报告一致，验证可信。

## Verdict

**PASS**

无 blocking finding。实现精确遵循 plan 中 OBS-SIG-02 P02 specification，motivation 成立，root cause 正确（duration 来自 `ToolResultMeta` durable accepted outcome），completed/failed/cancelled 三种终态全部覆盖，missing meta 产生显式 limited signal 而非静默丢失，malformed payload fail closed with `HostDurableError`，分层边界完整（未修改 Engine contract、SQLite schema、ToolExecutor scheduling），未实现 P03/P04 或 analyzer aggregation，AGENTS.md 编码约束合规，测试覆盖 producer/consumer/hot-cold/malformed 路径，pyright 零错误。

Residual risk 低且已有明确 owner（WU-OBS-00 analyzer 需处理 `missing_tool_result_meta` limited signal）。Producer/consumer 校验逻辑近似重复为当前设计意图内的 tradeoff（不同 error contract），不构成阻塞问题。

等待 controller 裁决。
