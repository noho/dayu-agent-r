# WU-OBS-SIGNALS-01 Aggregate Deepreview Fix Re-review - AgentMiMo

## Verdict

PASS

## 输入

- Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-controller-adjudication.md`
- Fix artifact (AgentCodex): `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-fix-codex.md`
- Workspace diff: `git diff` on branch `phaseflow/wu-obs-signals-p01-p04`

## 检查项

### 1. `dayu.host.tool_trace_signals` 是否只是 Host 内部共享 contract

**PASS** — `tool_trace_signals.py` 只 import 标准库（`hashlib`, `dataclasses`, `__future__`），无 `dayu.runtime`、`dayu.engine`、`dayu.service` 或其他层的 import。不引入反向依赖，不暴露给 LLM-facing 文本。

证据：`dayu/host/tool_trace_signals.py:8-11` — 仅 `from __future__ import annotations`, `import hashlib`, `from dataclasses import dataclass`。

### 2. 四类 signal JSON 形状、schema_version、status、failure_kind、bounded text 规则不变

**PASS** — diff 确认三个模块移除的本地常量值与 `tool_trace_signals.py` 中导出的值完全一致：

| 常量 | 旧值（三模块本地） | 新值（共享模块） |
|---|---|---|
| `CONTEXT_PRESSURE_SCHEMA_VERSION` | 1 | 1 |
| `TOOL_TIMING_SCHEMA_VERSION` | 1 | 1 |
| `TOOL_TIMING_STATUS_AVAILABLE` | "available" | "available" |
| `TOOL_TIMING_STATUS_MISSING_META` | "missing_tool_result_meta" | "missing_tool_result_meta" |
| `TOOL_TIMING_DURATION_SOURCE_META` | "tool_result_meta" | "tool_result_meta" |
| `FAILURE_METADATA_SCHEMA_VERSION` | 1 | 1 |
| `PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION` | 1 | 1 |
| `PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE` | "none" | "none" |
| `PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT` | "present" | "present" |
| `TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` | 512 | 512 |
| `FAILURE_KIND_TOOL_FAILED` | "tool_failed" | "tool_failed" |
| `FAILURE_KIND_TOOL_CANCELLED` | "tool_cancelled" | "tool_cancelled" |
| `FAILURE_KIND_POLICY_BLOCKED` | "policy_blocked" | "policy_blocked" |
| `FAILURE_KIND_PROVIDER_PROTOCOL_ERROR` | "provider_protocol_error" | "provider_protocol_error" |
| `FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED` | "context_compaction_attempt_rejected" | "context_compaction_attempt_rejected" |
| `FAILURE_KIND_CONTEXT_COMPACTION_FAILED` | "context_compaction_failed" | "context_compaction_failed" |
| `FAILURE_METADATA_ALLOWED_KINDS` | 6-member frozenset | 6-member frozenset |

`BoundedTraceSignalText` dataclass（`tool_trace_signals.py:74-86`）与移除的 `_BoundedFailureText`（旧 `tool_runtime.py`）字段、类型、frozen/slots 完全一致。`bound_trace_signal_text()`（`tool_trace_signals.py:89-108`）与移除的 `_bounded_failure_text()` 逻辑完全一致：`None` → 三元组 `(None, None, False)`；非 `None` → `sha256:` digest + `[:512]` 截断 + `len > 512` 标志。

### 3. 校验异常类型不变

**PASS**

- `tool_runtime.py` — ToolRuntime 校验仍抛 `ValueError`（`tool_runtime.py:370`, `tool_runtime.py:410` 等多处）。
- `tool_trace.py` — ToolTrace projection 校验仍抛 `HostDurableError`（`tool_trace.py:420`, `tool_trace.py:507` 等多处）。

异常类型未因常量迁移而改变。

### 4. P01/P02/P03/P04 来源约束不变

**PASS**

- P01 context_pressure：`CONTEXT_PRESSURE_SCHEMA_VERSION`、`CONTEXT_PRESSURE_SOURCE_USAGE_REPORTED` 等来源常量仍在 `engine_ingest.py` 本地定义（`engine_ingest.py:273`-`276`），未迁入共享模块，无新来源引入。
- P02 tool_timing：`TOOL_TIMING_DURATION_SOURCE_META` 值 "tool_result_meta" 不变，`tool_runtime.py` 仍只从 `ToolResultMeta` 读取 duration。
- P03 failure_metadata：`tool_runtime.py` 仍只生产 `tool_failed`、`tool_cancelled`、`policy_blocked` 三种 kind，无 raw args 泄漏。
- P04 partial_tool_call_signal：`engine_ingest.py` 仍只消费 Engine bounded `PartialToolCallSummary`。

无新来源引入，无 raw args 泄漏路径。

### 5. README 不更新的裁决

**PASS** — 裁决合理。本次只收敛 Host 内部 signal 常量为单一真源，不新增 stable developer-facing 接口，不改变 Tool Trace 投影的对外行为或字段。`dayu/host/README.md` 已覆盖 Tool Trace signal 投影说明；`tests/README.md` 未触发更新条件。

### 6. 采信验证结果

**PASS** — 已独立复现：

```text
160 passed in 1.20s  (pytest, 6 个 Host 测试文件)
pyright: 0 errors
git diff --check: OK
```

与 AgentCodex 报告一致。

## Findings

None

## Coverage Notes

本次 fix 只涉及常量抽取与 import 重定向，160 个 Host 测试覆盖了所有 signal 生产/消费路径。pyright 0 errors 确认无类型漂移。

## Validation

| 检查项 | 结果 |
|---|---|
| `tool_trace_signals` 无反向依赖 | ✅ |
| `tool_trace_signals` 不进入 `dayu.runtime` | ✅ |
| signal JSON 形状不变 | ✅ |
| schema_version / status / failure_kind 不变 | ✅ |
| bounded text digest 与截断规则不变 | ✅ |
| ToolRuntime 校验仍为 ValueError | ✅ |
| ToolTrace projection 校验仍为 HostDurableError | ✅ |
| P01-P04 来源约束不变 | ✅ |
| README 不更新裁决合理 | ✅ |
| 160 tests passed | ✅ |
| pyright 0 errors | ✅ |
| diff check OK | ✅ |

## Residual Risks

无新增 active residual risk。WU-OBS-00 analyzer 未落地仍是本 work unit 的既有后续 owner。
