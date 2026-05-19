# PR-62 fullrepo accepted-fix final re-review

## Review scope

只 review 当前 workspace 未提交变更（`git diff HEAD`），不修改代码、不 commit、不 push、不打开 PR。

## Review 输入

- `docs/reviews/pr-62-fullrepo-review-controller-adjudication-20260519.md`
- `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-mimo-20260519.md`
- `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-ds-20260519.md`
- `docs/reviews/repo-review-20260519-182223.md`
- `docs/reviews/repo-review-20260519-182226.md`
- `docs/host/implementation-control.md`
- 当前 workspace `git diff HEAD`（25 files changed, +468 -68）

## Finding 1: awaiting accept timeout diagnostic_refs 可观察路径

### 结论：PASS

### 分析

`dayu/host/tool_runtime.py` 中 `_accept_awaiting_with_retry`（line 2816）的修复路径：

1. retry 循环中累积 `diagnostics: tuple[str, ...]`（line 2829），每次 timeout 后从 `result.diagnostic_refs` 取回已有 refs（line 2846）。
2. retry 耗尽后，emit 一条 `ToolTraceDiagnosticRecord(reason_code="accept_timeout")`，把 `ref_id` 追加到最终 `ToolAwaitingAcceptTimedOut.diagnostic_refs`（line 2857-2861）。
3. `_awaiting_accept_failure_outcome`（line 5296）把 `result.diagnostic_refs` 传给 `_hint_with_diagnostic_refs`（line 5317-5319），编码进最终 `ToolFailedOutcome.result.hint`。
4. `ToolAwaitingAcceptTimedOut` 的 `diagnostic_refs` 字段已从 `waiting.py`（line 307）补齐默认空元组。

两条测试覆盖：

- `test_awaiting_accept_timeout_returns_governed_error`（line 829）：直接 timeout 路径，`diagnostic_refs=()`，hint 不含 diagnostic_refs key。
- `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref`（line 861）：retry 耗尽路径，hint 包含 `diagnostic_refs=tool-diagnostic-memory-1`，diagnostics emitter 记录 1 条 `reason_code="accept_timeout"`。

诊断引用沿最终 `ToolFailedOutcome` 可观察路径完整保留。

## Finding 2: implementation-control.md deferred tracking 完整性

### 结论：PASS

`docs/host/implementation-control.md` 追踪区 `PR-62 fullrepo review deferred tracking`（line 1634-1703）完整覆盖 adjudication doc 中全部 14 个 deferred 项：

| # | 追踪项 | owner / destination | 非 blocker 理由 | 触发条件 | 验证要求 |
|---|--------|---------------------|-----------------|----------|----------|
| 1 | runtime lane close/acquire 竞态 | Phase 11 / runtime lane hardening | TTL cleanup 兜底 | Phase 11 多进程 hardening | concurrent close/acquire tests |
| 2 | durable bootstrap DDL 原子性 | durable bootstrap work unit | IF NOT EXISTS + schema version | 修改 bootstrap transaction | fresh DB / retry / visibility |
| 3 | after-commit 多错误聚合 | durable transaction observability | 不改变 committed truth | 新增多 callback sink | 多 callback 失败聚合 |
| 4 | Host crash recovery E2E | Phase 11 | 需多进程 harness | Phase 11 recovery 实现 | crash/restart E2E |
| 5 | watch 轮询性能 | Phase 11 / production watch | 无 correctness 回归 | watch consumer 扩大 | 延迟 / CPU / DB 压力 |
| 6 | import boundary helper 重复 | P9.5 / Phase 11 test hardening | 测试 helper 层 | 扩展 boundary 白名单 | 反向依赖禁止 |
| 7 | runtime log import 副作用 | runtime 日志清理 | 低风险 side effect | runtime 被更多层 import | 重复 import 幂等 |
| 8 | ToolFactAcceptCandidate God dataclass | ToolRuntime structure cleanup | 维护性非 correctness | 新增 candidate 字段 | accept/reuse/duplicate matrix |
| 9 | compact 失败最终降级 | Phase 10 follow-up / Phase 11 | 明确 failure reason | 修改 compact failure policy | failure matrix E2E |
| 10 | executor 普通异常 observability | Engine/ToolRuntime observability | 不破坏终态一致性 | 排障需求 | outcome / diagnostic 关联 |
| 11 | service/ui 测试缺失 | Service/UI work unit | 未实现 service/ui 层 | 新增 service/ui 入口 | contract / import boundary |
| 12 | 敏感异常 marker 精度 | diagnostics redaction | 过度脱敏非漏出 | 新增异常 taxonomy | redaction / 可诊断性 |
| 13 | open_host fallback 常量 | Host configuration governance | 已有内部兜底说明 | 修改 open_host options | 显式配置优先 |
| 14 | session watch 20ms | Phase 11 lifecycle hardening | 性能非 correctness | 引入 push/notification | watch 延迟 / CPU |

每项均包含 owner/destination、非 PR-62 blocker 理由、触发条件和后续验证要求。符合 implementation-control.md 追踪规则。

## Finding 3: adjudication doc 准确性

### 结论：PASS

`docs/reviews/pr-62-fullrepo-review-controller-adjudication-20260519.md` 准确记录：

- repo-review-20260519-182226：9 项 fixed（Finding 1/3/4/5/6/8/9/14/15/16），2 项 deferred（Finding 2/7/10/11/13）。
- repo-review-20260519-182223：4 项 fixed（Finding 1/2/3/4），8 项 deferred（Finding 5-12）。
- 验证结果：160 passed，pyright 0 errors/0 warnings，`git diff --check` clean。
- Finding 1 follow-up（awaiting diagnostic refs）已由 AgentCodex 修复。

## Finding 4: accepted fixes 风险分析

### 结论：PASS — 无新风险引入

逐文件分析：

**dayu/host/tool_runtime.py**（+47 lines）：
- `_hint_with_diagnostic_refs`：纯函数，无副作用，只编码字符串。
- `_accept_awaiting_with_retry` diagnostic accumulation：在已有 retry 循环中追加 diagnostics 收集，不改变控制流。
- duplicate governance 条件合并：语义等价重构，`duplicate_governed` 从预计算改为内联赋值。

**dayu/host/dispatch.py**（+98/-10 lines）：
- `_cancelled_eof_candidate`：cancel 后 clean EOF 合成 `RUN_CANCELLED` EngineEvent。只在 `cancellation_token.is_cancelled() and not self._closed` 时触发，不影响正常 EOF 路径。`_cancelled_eof_candidate` 是 module-level 私有辅助函数，构造确定性 candidate，不引入新状态。
- 原 clean EOF 路径降级为 cancel-synthesis 失败后的 fallback，日志级别不变。

**dayu/host/waiting.py**（+39/-10 lines）：
- `ToolAwaitingAcceptTimedOut.diagnostic_refs`：新增字段，默认空元组，向后兼容。
- `_resolve_created_event_ref`：从 inline 逻辑抽取为 module-level helper，增加 `event_id/event_sequence is None` 的 fail-closed guard。原调用点语义不变。

**dayu/host/llm_compaction.py / fake_compaction.py / compaction_budget.py**：
- `_budget_after_compact` 统一使用 `estimate_compacted_context_budget`，消除 `4 chars/token` 硬编码，改用 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN`。`FakeContextCompactor` 复用同一 helper。`compaction_budget.py` 是新增 module-level helper，只依赖 `dayu.host.compaction` 和 `dayu.host.context_budget`，不引入新层依赖。

**dayu/contracts/tool_await.py**（+10 lines）：
- `ToolAwaitSnapshot.__post_init__`：空 `snapshot_id` 校验，防御性验证。

**dayu/contracts/tool_outcome.py**（+1/-1 line）：
- `ALLOWED_TOOL_CANCELLED_REASONS` 类型从 `frozenset[str]` 收窄为 `frozenset[ToolCancelledReason]`。纯类型收窄，运行时语义不变。

**dayu/host/durable/_validation.py**（+2 lines）：
- `require_optional_non_empty_text` 增加 `isinstance(value, str)` 守卫。原路径对非文本值会触发 `AttributeError`，现改为结构化 `HostDurableError`。

**dayu/host/engine_ingest.py**（+4 lines）：
- unsupported event type 分支增加 `stop_worker_stream=True` fail closed。原行为是静默拒绝但不停 stream，现改为明确停止。

**总结**：所有 accepted fixes 均为针对性防御增强或类型收窄，不引入新契约、不改变分层边界、不引入新日志路径风险、不改变 compact budget 语义（只统一估算常数）、不改变 worker lifecycle、不改变 event ingestion 状态机。

## Finding 5: CLI/Web/GUI console scripts

### 结论：OUT OF SCOPE

用户已明确 CLI/Web/GUI 未开始实现，此项不在 review 范围内。

## 结论

**PASS**

### 验证命令

```bash
# 运行受影响测试
source .venv/bin/activate
pytest -q tests/host/test_toolruntime_executor.py tests/host/test_resolve_wait_command.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_durable_validation.py tests/contracts/test_tool_outcome_exhaustive.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_import_boundary.py tests/engine/test_agent_phase2.py

# pyright
pyright dayu/contracts/tool_await.py dayu/contracts/tool_outcome.py dayu/engine/agent.py dayu/host/compaction_budget.py dayu/host/dispatch.py dayu/host/durable/_validation.py dayu/host/engine_ingest.py dayu/host/fake_compaction.py dayu/host/llm_compaction.py dayu/host/tool_runtime.py dayu/host/waiting.py

# whitespace
git diff --check
```

### 剩余 deferred 项

全部 14 个 deferred 项已落入 `docs/host/implementation-control.md` 追踪区（line 1634-1703），每项均有 owner/destination、非 blocker 理由、触发条件和验证要求。无遗留 untracked deferred。
