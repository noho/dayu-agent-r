# PR-62 Fullrepo Accepted-Fix Final Re-Review (AgentDS)

## Scope

- Mode: current changes（未提交 workspace changes 相对 HEAD `55c8d1d`）
- Branch: `feat/host-p10-5-public-contract-freeze`
- 输入 artifacts:
  - `docs/reviews/pr-62-fullrepo-review-controller-adjudication-20260519.md`
  - `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-ds-20260519.md`
  - `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-mimo-20260519.md`
  - `docs/host/implementation-control.md`
- 25 个文件变更（24 modified + 1 new）

## 验证结果

- `pytest` 受影响测试: **148 passed**
- `pyright` 生产代码: **0 errors, 0 warnings**
- `pyright` 测试代码: **0 errors, 0 warnings**
- `git diff --check`: clean

---

## 1. Awaiting Accept Timeout diagnostic_refs 传播链

### 上一轮 concern 回顾

上一轮 DS re-review Finding 01 指出：`_awaiting_accept_failure_outcome` 在将
`ToolAwaitingAcceptTimedOut` 转为 `ToolFailedOutcome` 时丢弃 `diagnostic_refs`，
导致重试过程中的诊断和最终 timeout 诊断虽被 emitter 发出，但 ref_id 无法传播到最终 outcome。

### 本轮验证

**已修复。** 修复包含三层变更：

1. **`ToolAwaitingAcceptTimedOut` 新增 `diagnostic_refs` 字段** (`waiting.py:302`)
   - 类型 `tuple[str, ...]`，默认空 tuple
   - 向下兼容旧构造

2. **`_accept_awaiting_with_retry` 累积诊断并发射 timeout_ref** (`tool_runtime.py:2829-2857`)
   - 新增 `diagnostics: tuple[str, ...] = ()` 初始化
   - 中间重试的 `ToolAwaitingAcceptTimedOut` 携带累积的 `diagnostic_refs`
   - 循环退出后 emit `timeout_ref`，最终 result 包含 `(*diagnostics, timeout_ref.ref_id)`

3. **`_awaiting_accept_failure_outcome` 通过 hint 传播诊断** (`tool_runtime.py:5314-5321`)
   - 新增 `_hint_with_diagnostic_refs` helper 将诊断 ref id 编码到 `ToolResultFailure.hint` 字段
   - 格式：`{base_hint};diagnostic_refs=ref1,ref2,...`

### 测试覆盖

- `test_awaiting_accept_timeout_returns_governed_error`: 更新断言，验证 hint 包含 `diagnostic_refs=` 和 `tool-diagnostic-` 前缀
- `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref`: **新增测试**，验证 retry 耗尽时 hint 精确匹配 `"accept_ack_lost;diagnostic_refs=tool-diagnostic-memory-1"`，且 emitter 发出 `accept_timeout` 原因码

**结论：上一轮 DS concern 已完整修复，测试覆盖充分。**

---

## 2. Non-Awaiting Accept Timeout 对称缺口（新发现）

### 发现

`_accept_failure_outcome` (非 awaiting 路径, `tool_runtime.py:5274-5293`) 存在与上一轮
awaiting 路径完全对称的 `diagnostic_refs` 丢弃问题：

- `_accept_with_retry` (line 2935-2984) 已正确累积 `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`
  并随 `ToolFactAcceptTimedOut` 返回（line 2980-2983）
- 但 `_accept_failure_outcome` line 5289-5292 只提取 `result.last_error_code` 作为 hint，
  不调用 `_hint_with_diagnostic_refs`，丢弃 `result.diagnostic_refs`

### 证据

- `tool_runtime.py:5289-5292`:
  ```python
  return _tool_failed_outcome(
      error=_TOOL_RUNTIME_ACCEPT_TIMEOUT_ERROR,
      message="tool fact accept ack timed out",
      hint=result.last_error_code or _TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON,
  )
  ```
- 对比 `_awaiting_accept_failure_outcome` (line 5314-5321) 已使用 `_hint_with_diagnostic_refs`

### 影响

非 awaiting accept timeout 场景下，中间重试诊断和最终 timeout 诊断的 ref_id 无法从
`ToolFailedOutcome` 传递到下游 trace。由于 `ToolFactAcceptTimedOut.diagnostic_refs`
类型为 `tuple[ToolTraceDiagnosticRef, ...]`（对象），而 `_hint_with_diagnostic_refs`
接受 `tuple[str, ...]`（ref_id 字符串），修复时需做 `.ref_id` 提取适配。

### 严重程度

**低** — 与上一轮 awaiting 路径问题对称，但非 awaiting 路径（普通 tool fact accept timeout）
在生产中出现的概率和排障价值相对低于 awaiting 路径。当前测试（`test_accept_timeout_bounded_retry_returns_governed_error`、
`test_accept_retry_exhausted_returns_governed_timeout`）使用 `diagnostic_refs=()` 空元组，
未覆盖非空路径。

### 建议

非 PR-62 blocker。建议在后续 ToolRuntime observability 切片中统一修复：
将 `_accept_failure_outcome` 改为 `_hint_with_diagnostic_refs` 调用，并补测试覆盖非空
`diagnostic_refs` 路径。此项应进入 `implementation-control.md` 追踪区。

---

## 3. implementation-control.md Deferred Tracking 完整性

### 验证结果

`docs/host/implementation-control.md` 中 PR-62 fullrepo review deferred tracking
（line 1634-1703）完整覆盖 13 项 deferred。每项均包含：

| 项目 | Owner/Destination | 非 Blocker 理由 | 触发条件 | 验证要求 |
|------|-------------------|----------------|----------|----------|
| runtime lane close/acquire 竞态 | Phase 11 | lane 属 `dayu.runtime` 容量 primitive | Phase 11 多进程 | concurrent close/acquire tests |
| durable bootstrap DDL 原子性 | durable bootstrap/schema hardening | `IF NOT EXISTS` 幂等恢复 | 修改 bootstrap transaction boundary | fresh DB bootstrap, retry |
| after-commit 多错误聚合 | durable transaction observability | after-commit 失败不改变 committed truth | 新增多个 after-commit sink | 多 callback 失败聚合 |
| Host crash recovery E2E | Phase 11 | 需多进程/强杀式 harness | Phase 11 recovery scan | 进程 crash/restart E2E |
| watch 轮询性能 | Phase 11 / production watch scale | 20ms polling 无 correctness 回归 | watch consumer 数量扩大 | watch 延迟/CPU/DB 压力 |
| import boundary helper 重复 | P9.5 / Phase 11 test hardening | 重复在测试 helper 层 | 继续扩展 boundary 白名单 | 单一真源 helper |
| runtime log import 副作用 | runtime 日志清理 | 低风险全局 logging 注册 | runtime 包被更多层 import | 重复 import 幂等 |
| `ToolFactAcceptCandidate` God dataclass | P9.5 / ToolRuntime structure cleanup | 消费者明确，无 correctness 影响 | 新增 candidate 字段 | ordinary/awaiting/reuse/duplicate matrix |
| compact 失败最终降级路径 | Phase 10 / Phase 11 | operation 返回明确 failure reason | 修改 proactive/reactive compact failure policy | proactive/reactive/hard threshold E2E |
| executor 普通异常 observability | Engine/ToolRuntime observability | 异常转为 tool failed outcome | 工具 executor 异常排障 | outcome/diagnostic 可关联 |
| service/ui 测试缺失 | Service/UI work unit | 代码未实现 | 新增 `dayu.service`/`dayu.ui` | contract tests |
| 敏感异常 marker 精度 | diagnostics/redaction policy | 偏保守 redact 不会漏标 | 新增异常 taxonomy | redaction/可诊断性 |
| open_host fallback 常量 | Host configuration/composition | 已文档化非生产默认值 | 修改 `open_host` options | 显式配置优先 |

**结论：所有 deferred 项均有 owner/destination、非 blocker 理由、触发条件和验证要求，tracking 完整。**

---

## 4. Controller Adjudication Artifact 准确性

`docs/reviews/pr-62-fullrepo-review-controller-adjudication-20260519.md` 准确记录：

1. **已修复项**（来自两个 fullrepo review 的 14 项）：裁决描述与 workspace diff 一致
2. **Deferred 项**（13 项）：分类准确，均与 `implementation-control.md` 追踪区对齐
3. **验证结果**：160 passed + pyright 0 errors 可复现（本轮 148 passed，差异因测试集范围不同）
4. **DS follow-up**：line 25 明确记录了 "follow-up re-review 确认 `_awaiting_accept_failure_outcome` 会在转最终失败 outcome 时丢弃已有 refs"，并已将 fix 归入已修复

**结论：裁决 artifact 记录准确，DS follow-up 已体现。**

---

## 5. Accepted Fixes 新风险审查

### 5.1 Compaction Budget Helper (`compaction_budget.py`)

- 双路估算（typed_fragment_tokens + budget_proportion_estimate）取 max，比旧 `min(summary_tokens, hard_threshold - 1)` 显著改善
- fake/LLM compactor 均调用同一 `estimate_compacted_context_budget` 入口
- 上一轮 DS 02-低（ref strings 语义不匹配）仍为残余：`_preserved_ref_texts` 返回 ref ID 字符串，token 估算极小但不影响 `max()` 结果
- **无新 correctness 风险**

### 5.2 Cancel EOF 合成 (`dispatch.py:_cancelled_eof_candidate`)

- 守卫条件正确：`is_cancelled()` + `not self._closed` 确保只对主动 cancel 后的 clean EOF 合成
- `run_terminal_closed` 初始化 `False`，合成失败时正确 fallback 到 `clean_eof_without_terminal`
- 上一轮 DS 03-低（requested_at/reason fallback 掩盖 invariant）仍为残余
- **无新 correctness 风险**

### 5.3 Engine Ingest Unsupported Fail-Closed (`engine_ingest.py`)

- `_ingest_validated` 涵盖全部 18 个 `EngineEventType`
- Unsupported fallthrough 设置 `stop_worker_stream=True` fail-closed
- 测试覆盖 `test_unsupported_engine_event_shape_is_rejected` 和 `test_preview_event_rejects_missing_or_wrong_data`
- **无新 correctness 风险**

### 5.4 `_close_runner_once` Once 语义 (`engine/agent.py`)

- 从 `else` 改为 `finally` 置 `_closed = True`，确保 close 异常后仍标记已关闭
- 测试 `test_close_runner_once_marks_closed_after_close_error` 验证 `close_count == 1`
- **正确**

### 5.5 `require_optional_non_empty_text` 类型守卫 (`durable/_validation.py`)

- 新增 `isinstance(value, str)` 守卫，防止非文本值导致 `AttributeError`
- 测试 `test_require_optional_non_empty_text_rejects_runtime_non_text_values` 覆盖 `int`、`bytes`、空字符串、空白字符串
- **正确**

### 5.6 `_resolve_created_event_ref` Fail-Closed (`waiting.py`)

- 从内联逻辑抽出为模块级函数，resume/terminal 路径缺失 event ref 时抛出 `INTERNAL_ERROR`
- 幂等重放在 fail-closed 检查之前（line 739-749），不破坏幂等语义
- 测试 `test_resolve_created_event_ref_fails_closed_for_missing_resume_start` 覆盖
- **正确**

### 5.7 `ALLOWED_TOOL_CANCELLED_REASONS` 类型精确化

- `frozenset[str]` → `frozenset[ToolCancelledReason]`
- **低风险类型改善**

### 5.8 `ToolAwaitSnapshot` 空 `snapshot_id` 校验

- 新增 `__post_init__` 拒绝空/空白 `snapshot_id`
- 测试 `test_tool_await_snapshot_rejects_empty_snapshot_id` 覆盖
- **正确**

### 5.9 Duplicate Governance 条件合并

- 原 `duplicate_governed` + `policy_decision.kind` 两次判断合并为单次
- 语义保留：`duplicate_governed` 仍作为 boolean 传递给候选构造
- **正确，无行为变更**

---

## 6. Public Contract / 分层 / Worker Lifecycle 风险

- `delay/host/compaction_budget.py` 为 Host 内部 helper，不暴露 public contract
- Cancel EOF 合成在 `dispatch.py` 内的 `_HostCancellationToken` 守卫下，不改变 public event 语义
- `_close_runner_once` 改为 finally 后不改变 Engine 外部行为
- 无新的跨层依赖、层级泄漏或 worker lifecycle 语义变更

---

## 7. 未覆盖项

- 非 awaiting accept timeout `diagnostic_refs` 丢弃（见 Section 2）未在 implementation-control.md 追踪区中
- 上一轮 DS re-review 的 02-低（ref strings token 估算语义不匹配）和 03-低（`_cancelled_eof_candidate` fallback 掩盖 invariant）仍为残余，已在上一轮 artifact 中记录但未进入 implementation-control.md 追踪区

---

## 结论

**PASS**

- 上一轮 DS concern（awaiting accept timeout diagnostic_refs 丢弃）已完整修复，测试覆盖充分
- 148 passed + pyright 0 errors，所有 accepted fixes 均正确实施
- implementation-control.md deferred tracking 完整覆盖 13 项，每项均有 owner/destination/理由/触发条件/验证要求
- Controller adjudication artifact 准确记录裁决和 DS follow-up
- 新发现 Section 2（非 awaiting accept 对称缺口）为低严重度，不阻塞 PR-62

### 建议追加入追踪区

以下两项建议在 accept 前或 accept 后第一时间写入 `implementation-control.md` 追踪区：

1. **非 awaiting accept timeout `diagnostic_refs` 在 `_accept_failure_outcome` 被丢弃**
   - Owner: ToolRuntime observability hardening
   - 非 PR-62 blocker 理由：对称于已修复的 awaiting 路径问题，但非 awaiting 路径生产排障价值相对低，且当前测试均使用空 diagnostic_refs 元组
   - 触发条件：修改 `_accept_failure_outcome`、新增 accept timeout diagnostic 需求
   - 验证要求：`_accept_failure_outcome` 调用 `_hint_with_diagnostic_refs`，补非空 diagnostic_refs 测试

2. **Compaction budget ref strings token 估算语义不匹配**
   - Owner: compaction budget hardening
   - 非 PR-62 blocker 理由：`max(typed_fragment_tokens, budget_proportion_estimate)` 中比例估算主导，实际行为不受 ref-string-based 估算影响
   - 触发条件：修改 `_preserved_ref_texts` 或 `_estimate_preserved_context_tokens`
   - 验证要求：extreme case（`retained_count == 0` 且所有 refs 为空）下有 defensive 行为
