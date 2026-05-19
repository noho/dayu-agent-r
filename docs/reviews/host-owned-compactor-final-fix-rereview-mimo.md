# Host-owned Compactor Final Fix Re-Review

## Scope

- Mode: current changes
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/host-owned-compactor-final-fix-rereview-mimo.md`
- Included scope: workspace unstaged/staged diff（Host-owned compactor final review fix），聚焦 7 个检查维度
- Excluded scope: `dayu/runtime/`（零变更）、`dayu/ui/`、`dayu/service/`、`dayu/fins/`
- Parallel review coverage: 无，单 reviewer 逐项走读

---

## 结论：PASS

所有 blocker findings 已 root-cause 修复，改动一致、测试充分、无新增问题。

---

## 逐项审查

### 1. llm_compaction.py 是否彻底无 thread/asyncio.run/join 桥

**结论：已彻底清除。**

直接证据：
- `dayu/host/llm_compaction.py` diff 删除了 `import asyncio`、`import threading`、`from dataclasses import dataclass`（diff 行 11-14）
- 删除了 `_ThreadRunState` dataclass（diff 行 74-85）
- `_run_agent_request_sync` 替换为 `async _run_agent_request`，body 仅一行 `return await run_agent_and_wait(request)`（diff 行 221-234）
- 删除了 `_run_agent_request_in_thread` 函数（diff 行 290-305）
- `LLMContextCompactor.compact` 从 `def` 改为 `async def`（diff 行 163）
- `grep 'threading\.\|thread\.join\|asyncio\.run(' dayu/host/` 返回零匹配
- `inspect.getsource` 测试（`test_llm_compaction.py:test_llm_context_compactor_does_not_use_thread_bridge`）静态断言源码不含 `threading`、`thread.join(`、`asyncio.run`

**不再是表面修复（thread.join timeout），而是 root-cause 修复：将整个调用链 async 化，从根源消除线程桥。**

### 2. ContextCompactor async port 改动是否在 fake/tests/dispatch/engine_ingest 中一致

**结论：完全一致。**

直接证据：
- `dayu/host/compaction.py:874` — `ContextCompactor` Protocol 的 `compact` 改为 `async def`
- `dayu/host/fake_compaction.py:28` — `FakeContextCompactor.compact` 改为 `async def`
- `dayu/host/compaction_operation.py:68` — `run_compaction_operation` 改为 `async def`，内部 `await compactor.compact(request)`
- `dayu/host/dispatch.py:676` — `_run_pre_start_governance` 改为 `async def`，内部 `await self._execute_proactive_compaction`
- `dayu/host/dispatch.py:910` — `_execute_proactive_compaction` 改为 `async def`，内部 `await run_compaction_operation`
- `dayu/host/dispatch.py:630` — `run_queue_promotion` 改为 `async def`，内部 `await self._run_pre_start_governance`
- `dayu/host/dispatch.py:2499` — `_consume_worker_events` 中 `ingestor.ingest` 改为 `await ingestor.ingest_async`
- `dayu/host/engine_ingest.py:504` — 新增 `async def ingest_async`，内部 `await self._execute_reactive_compaction`
- `dayu/host/engine_ingest.py:1377` — `_execute_reactive_compaction` 改为 `async def`，内部 `await run_compaction_operation`
- 同步 `ingest()` 方法保留但对 reactive compaction 路径 raise `RuntimeError("reactive context compaction requires ingest_async")`

测试一致性：
- `test_compaction_contract.py` — 所有 8 个测试改为 `@pytest.mark.asyncio` + `await compactor.compact()`
- `test_llm_compaction.py` — 所有 6 个测试改为 `await compactor.compact()`，新增 1 个 source inspection 测试
- `test_compaction_operation.py`（新增）— 覆盖 async compaction operation retry/failure
- `test_context_budget.py` — 新增 `test_budget_estimate_rejects_non_dispatchable_hard_threshold`
- `test_context_policy.py` — 新增 `test_context_budget_policy_rejects_non_dispatchable_hard_threshold`
- 全部 46 个 compaction 相关测试通过

### 3. wake_queue_promotion/promotion drain task 是否有 owner、异常收口、close cancel/await

**结论：符合要求。**

直接证据：
- `dayu/host/dispatch.py:626` — `self._promotion_drain_task = asyncio.create_task(self._promotion_drain_loop())`，scheduler 持有引用
- `dayu/host/dispatch.py:1575-1623` — `_promotion_drain_loop` 完整异常收口：
  - `RuntimeError` + `self._closed` 分支：debug 日志，静默退出
  - `RuntimeError` + 非 closed：warning 日志 + `exc_info=True`
  - `Exception`：warning 日志 + `exc_info=True`
  - `asyncio.CancelledError`：debug 日志 + `raise`（透传取消）
- `dayu/host/dispatch.py:1526-1529` — `close()` 中 cancel + `await _suppress_task_cancel(promotion_task)`
- 不是裸后台 task：有 scheduler owner、有异常收口、有 close 时 cancel/await

### 4. 全量 dayu/host + dayu/engine 的 create_task 是否都有 owner/lifecycle/cleanup

**结论：全部有 owner 和 lifecycle 管理。**

`dayu/host` create_task 清单（4 处）：

| 位置 | task | owner | cleanup |
|------|------|-------|---------|
| `dispatch.py:603` | `_drain_loop` | `self._drain_task` | `close()` cancel + await（行 1522-1525） |
| `dispatch.py:626` | `_promotion_drain_loop` | `self._promotion_drain_task` | `close()` cancel + await（行 1526-1529） |
| `dispatch.py:1987` | `_consume_worker_events` | `self._active_tasks` set + `add_done_callback(discard)` | `close()` 遍历 cancel + await（行 1532-1534） |
| `local_proxy.py:208` | `anext(self._events)` | `self._active_anext` | `close()` cancel + await（行 231-238）；`finally` 块清理（行 216-219） |

`dayu/engine` create_task 清单（1 处）：

| 位置 | task | owner | cleanup |
|------|------|-------|---------|
| `runners/openai/runner.py:630` | `response_enter` | 局部 `response_task` | `_release_response_task_if_acquired` cancel + await（行 648-658）；`try/except CancelledError` 路径覆盖 |

无裸 create_task。

### 5. budget hard threshold 最小 2 的 policy/estimate 修复是否 root-cause 且测试充分

**结论：root-cause 修复，测试充分。**

直接证据：
- `dayu/host/context_policy.py:24` — 新增 `MIN_CONTEXT_HARD_THRESHOLD_TOKENS = 2`
- `dayu/host/context_policy.py:108-120` — `ContextBudgetPolicy` 两处校验：
  - 显式 `hard_threshold_tokens` 时：`< MIN_CONTEXT_HARD_THRESHOLD_TOKENS` 则 raise
  - 未显式时：`computed_hard_threshold_tokens = input_budget_tokens - minimum_protection_tokens`，`< MIN_CONTEXT_HARD_THRESHOLD_TOKENS` 则 raise
- `dayu/host/context_budget.py:205-210` — `BudgetEstimate` 同样校验 `hard_threshold_tokens < MIN_CONTEXT_HARD_THRESHOLD_TOKENS`
- 测试覆盖：
  - `test_context_policy.py:test_context_budget_policy_rejects_non_dispatchable_hard_threshold` — 验证 `hard_threshold_tokens=1` 被拒绝，`minimum_protection_tokens` 导致 computed < 2 被拒绝
  - `test_context_budget.py:test_budget_estimate_rejects_non_dispatchable_hard_threshold` — 验证 `hard_threshold_tokens=1` 被拒绝

root-cause 逻辑：`hard_threshold_tokens == 1` 时 `_budget_after_compact` 返回 0（`min(half, 1-1)=0`），compact 后零预算使 compact 完全无效。最小值 2 确保 compact 后至少有 1 token 正预算。

### 6. Service-facing public contract 是否仍只暴露 CompactorRunnerBaseline

**结论：是。**

直接证据：
- `dayu/host/__init__.py` — `__all__` 中只有 `CompactorRunnerBaseline`，无 `ContextCompactor`、`LLMContextCompactor`、`FakeContextCompactor`
- `dayu/host/api.py` — 仅导入 `CompactorRunnerBaseline`，`ContextCompactor` 仅作为内部类型注解使用
- `test_package_exports.py` 和 `test_public_contracts.py` 全部通过（48 tests）

### 7. README 和 artifact 是否准确，AGENTS.md/CLAUDE.md 用户约束变更是否未被误改

**README 更新准确：**
- `dayu/host/README.md` — 更新了 Context Governance Boundary 描述：
  - "通过 async `ContextCompactor` port 直接 await Engine public runner"（反映 async 化）
  - "hard threshold 必须至少为 2，确保 compact 后仍存在正整数预算"（反映 min 2 约束）
- `tests/README.md` — 更新了测试覆盖描述：
  - 新增 "Host-owned LLM compactor async runner path（`test_llm_compaction.py`）"
  - 新增 "async compaction operation retry/failure（`test_compaction_operation.py`）"

**AGENTS.md/CLAUDE.md 变更未误改：**
两文件 diff 完全一致，变更内容：
- "不是 `LLM on the loop`" 删除 — 简化表述，语义不变
- "Agent / AsyncAgent / AsyncOpenAIRunner" 简化为 "Agent / Runner" — 去除过时类名
- `dayu.runtime` 描述精简 — 合并两行为一行，语义不变
- 新增 "设计公共契约优先使用直接传参数的朴素接口" — 补充架构约束

以上均为用户手工修改的精简/补充，未引入语义冲突或约束弱化。

---

## Open Questions

- 无

## Residual Risk

- `ingest()` 同步方法对 reactive compaction 路径 raise `RuntimeError`，若未来有调用方在非 async 上下文触发 reactive compaction 会直接失败。当前所有 dispatch 路径已使用 `ingest_async`，风险可控，但需在后续扩展时注意。
