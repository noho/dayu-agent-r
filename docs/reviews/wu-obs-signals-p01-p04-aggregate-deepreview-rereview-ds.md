# WU-OBS-SIGNALS-01 Aggregate Deepreview Fix Re-review — AgentDS

## Scope

- 审查输入：`docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-fix-codex.md`
- 审查目标：验证 AgentCodex 对 Controller 接受的 DS finding 1（常量与 bounded text 规则重复定义）的修复是否完整、正确、不引入 regressions。
- 不审查 DS finding 2（跨 event read）——Controller 已裁决 not accepted as current fix。
- 不修改代码、不提交、不推送。
- 输出 artifact：`docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-rereview-ds.md`

---

## Verdict: **PASS**

---

## Findings: None

---

## Checklist

### 1. `dayu.host.tool_trace_signals` 只做 Host 内部共享 signal contract，不进入 `dayu.runtime`，不引入反向依赖

**结论：PASS**

**证据**：

- 新文件 `dayu/host/tool_trace_signals.py` 位于 `dayu/host/` 包下，属于 Host 层内部模块。
- 文件只 import 标准库 `hashlib` 和 `dataclasses`，无任何 `dayu.runtime`、`dayu.engine` 或其它 dayu 子包的引用。
- `grep -rn 'from dayu.host.tool_trace_signals' dayu/runtime/` → 无结果。`dayu.runtime` 不引用此模块。
- 所有引用方均为 Host 层模块：`dayu/host/tool_runtime.py`、`dayu/host/tool_trace.py`、`dayu/host/engine_ingest.py`。依赖方向为 Host 内部横向引用，不跨层。

### 2. 迁移到共享常量后，四类 signal JSON 形状、schema_version、status、failure_kind、bounded text digest 与截断规则保持不变

**结论：PASS**

**证据**：

| 常量/规则 | 迁前值 | 迁后值 | 一致性 |
|---|---|---|---|
| `CONTEXT_PRESSURE_SCHEMA_VERSION` | `1` | `1` | ✅ |
| `TOOL_TIMING_SCHEMA_VERSION` | `1` | `1` | ✅ |
| `FAILURE_METADATA_SCHEMA_VERSION` | `1` | `1` | ✅ |
| `PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION` | `1` | `1` | ✅ |
| `TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` | `512` | `512` | ✅ |
| `TOOL_TIMING_STATUS_AVAILABLE` | `"available"` | `"available"` | ✅ |
| `TOOL_TIMING_STATUS_MISSING_META` | `"missing_tool_result_meta"` | `"missing_tool_result_meta"` | ✅ |
| `TOOL_TIMING_DURATION_SOURCE_META` | `"tool_result_meta"` | `"tool_result_meta"` | ✅ |
| 6 种 failure_kind | 各自字面量定义 | 共享常量引用，字面量相同 | ✅ |
| `FAILURE_METADATA_ALLOWED_KINDS` | frozenset of 6 kinds | frozenset of 6 kinds | ✅ |

**bounded text 逻辑等价性**：

迁前 `_bounded_failure_text`（`tool_runtime.py:6188-6206`）：
```python
if value is None:
    return _BoundedFailureText(value=None, sha256_digest=None, truncated=False)
digest = f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
return _BoundedFailureText(
    value=value[:_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS],
    sha256_digest=digest,
    truncated=len(value) > _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS,
)
```

迁后 `bound_trace_signal_text`（`tool_trace_signals.py:96-108`）：
```python
if value is None:
    return BoundedTraceSignalText(value=None, sha256_digest=None, truncated=False)
digest = f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
return BoundedTraceSignalText(
    value=value[:TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS],
    sha256_digest=digest,
    truncated=len(value) > TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS,
)
```

两者在做完全相同的计算：null → (None, None, False)；non-null → 截取前 512 字符 + `sha256:{64-hex}` digest + `truncated = len > 512`。唯一差异是类名从私有 `_BoundedFailureText` 改为共享模块级 `BoundedTraceSignalText`，函数名从 `_bounded_failure_text` 改为 `bound_trace_signal_text`。调用点 `tool_runtime.py:6140, 6152` 已正确迁移到新函数名。

**无残留引用**：`grep -rn '_bounded_failure_text\|_BoundedFailureText' dayu/` → 无结果。旧实现已完全移除。

### 3. ToolRuntime 校验异常仍为 ValueError，ToolTrace projection 校验异常仍为 HostDurableError

**结论：PASS**

**证据**：

ToolRuntime（`tool_runtime.py`）：
- `_validate_failure_metadata_signal` → `raise ValueError(...)` at lines 4458, 4460, 4462, 4480
- `_validate_bounded_text_fields` → `raise ValueError(...)` at lines 4540, 4543, 4546, 4548, 4550
- `_validate_failure_diagnostic_refs` → `raise ValueError(...)` at lines 4563, 4566

ToolTrace（`tool_trace.py`）：
- `_validate_bounded_text_field` → `raise HostDurableError(...)` at lines 1697, 1702, 1707, 1711, 1715
- 所有其它 projection 校验 → `HostDurableError`（grep 确认 pattern 未变）

异常语义未变：ToolRuntime 在 accept 阶段使用 `ValueError` 拒绝非法信号；ToolTrace 在 projection 阶段使用 `HostDurableError` 记录并跳过 malformed payload。两边都使用 `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 做同一边界判断（512）。

### 4. P01/P02/P03/P04 来源约束不变

**结论：PASS**

**证据**：

diff 分析确认以下生产路径的代码逻辑完全未变（仅常量引用源和 bounded text 函数名变更）：

- **P01 `context_pressure`**：`_usage_context_pressure_signal` 在 `engine_ingest.py:4112-4171` 未修改；`_context_compaction_failed_pressure` 和 `_context_compaction_attempt_rejected_pressure` 在 `tool_trace.py` 未修改。
- **P02 `tool_timing`**：`_tool_timing_from_meta` 在 `tool_runtime.py:6083-6110` 未修改。duration 计算仍为 `int((meta.finished_at - meta.started_at) // _ONE_MILLISECOND)`。
- **P03 `failure_metadata`**：`_failure_metadata_from_outcome` 在 `tool_runtime.py:6091-6150` 仅将 `_bounded_failure_text` 调用改为 `bound_trace_signal_text`。三种 kind（tool_failed, tool_cancelled, policy_blocked）+ engine_ingest（provider_protocol_error）+ tool_trace 派生（context_compaction_attempt_rejected, context_compaction_failed）的 6 种闭集未变。
- **P04 `partial_tool_call_signal`**：`_provider_protocol_partial_tool_call_signal` 在 `engine_ingest.py:5978-6007` 未修改。只序列化 `PartialToolCallSummary` 的 bounded 字段，无 raw args 字段。`_is_bare_sha256_hex` 校验逻辑未变。

**无新来源**：无新增 import 引入 Engine 内部类型、治理事实或 raw payload 访问路径。无 raw args 泄漏路径。

### 5. README 不更新的裁决合理

**结论：PASS**

**证据**：

- `dayu/host/README.md` 当前已说明 Tool Trace 投影 context pressure、tool timing、failure metadata 等只读结构化 signal（第 353 行）。本次变更仅将内部常量从三个模块提取到共享模块，是纯内部重构，不引入新功能、新 API、新 schema 或新 developer-facing 接口。
- `tests/README.md` 未触发更新：不新增测试层级、运行方式或维护规则。
- 根据 CLAUDE.md 的 README 更新触发规则："先检查代码变更是否属于对应 README 的职责范围与目标读者；只有属于时才实际修改，不做机械同步。" 本次纯内部重构不属于任何 README 读者需要感知的范围。

### 6. 独立验证

**结论：PASS**

```text
source .venv/bin/activate && pyright dayu/host/tool_trace_signals.py dayu/host/tool_runtime.py dayu/host/tool_trace.py dayu/host/engine_ingest.py
→ 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && python -m pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_phase6_toolruntime_integration.py -q
→ 160 passed in 1.19s
```

与 AgentCodex 报告的 160 passed、pyright 0 errors 完全一致。无测试退化。

---

## Coverage Notes

| 检查项 | 方法 | 结果 |
|---|---|---|
| 新模块层级归属 | 文件路径 + import 审查 | Host 内部，不进入 runtime |
| 反向依赖 | `grep -rn 'tool_trace_signals' dayu/runtime/` | 无 |
| 常量值一致性 | diff 对比迁前/迁后值 | 所有值完全相同 |
| bounded text 逻辑等价 | 逐行对比 `_bounded_failure_text` vs `bound_trace_signal_text` | 逻辑完全相同 |
| 残留旧引用 | `grep -rn '_bounded_failure_text\|_BoundedFailureText' dayu/` | 无 |
| ValueError 保持 | grep tool_runtime.py 校验路径 | ✅ |
| HostDurableError 保持 | grep tool_trace.py 校验路径 | ✅ |
| P01-P04 生产路径 | diff 审查有无逻辑修改 | 仅常量引用源 + 函数名重命名 |
| README 裁决 | 对照 CLAUDE.md 触发规则 | 合理 |
| pyright | 受影响文件 | 0 errors |
| tests | 160 affected tests | 全部通过 |

---

## Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| `BoundedTraceSignalText` 与 `bound_trace_signal_text` 从私有变为模块级公开名，理论上可能被 Host 外模块引用 | Low（注意级） | WU-OBS-SIGNALS-01 maintainer | 当前无外部引用。如未来需要限制可见性，可考虑以 `_` 前缀标记为 Host 内部 API，但当前 `dayu.host.tool_trace_signals` 的模块 docstring 已声明"只承载 Host 内部共享"，不构成实质风险 |
| WU-OBS-00 analyzer 未落地 | Medium | WU-OBS-00 | 此为既有 residual risk，不受本次 fix 影响。已在 control document 登记为 `pending-prerequisite` |

---

## Validation

### 运行验证

```text
pyright (affected files): 0 errors, 0 warnings, 0 informations
Test run: 160 passed, 0 failed
```

### 采信验证

- AgentCodex fix artifact 所述变更与 git diff 完全一致。
- 所有 Controller re-review checklist 项均已独立验证通过。
- 无新增 active residual risk。
