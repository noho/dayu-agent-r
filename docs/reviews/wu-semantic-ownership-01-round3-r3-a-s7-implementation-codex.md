# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S7 Implementation（AgentCodex）

## 状态

`ready-for-code-review`

本轮只实施 S7：Compaction Attempt Cancellation 与 Pre-call Recheck。未提交、未 push、未创建 PR、未修改总控文档，也未进入 S8。

## 第一性原理与 owner 判定

1. provider timeout 只证明一次外部 proposal attempt 超时，不证明 parent user Run 或 reactive compaction operation 已被用户取消。因此 timeout cancellation 的唯一正确 owner 是“单次 proposal attempt”，不能写入 Run lifecycle parent。
2. parent token 仍是 Run / reactive operation 生命周期真源。任意时刻 parent 取消后，child 必须立即投影 parent 的 `reason` / `requested_at`，且 parent 语义优先于先前写入的 attempt-local timeout。
3. repair / retry 是新的外部 proposal attempt，必须创建新的 child。清空或复用已 timeout 的 token 都会混淆两个不同 owner；前者篡改 parent truth，后者污染下一 attempt。
4. runner-call manifest commit 与 provider call 之间存在 durable precondition TOCTOU。正确 owner 不是 recorder 或 provider adapter，而是同一个 linked attempt token：recorder 返回后、provider await 前重新观察 parent。proactive parent 因而通过既有 `_DurableRunCancellationToken` 重新读取 Run status / input cursor。
5. Engine public `CancellationToken` 继续保持只读观察协议。可写面只存在于 Host-private attempt child 与 `LLMContextCompactor` 的私有结构化 signal seam，不扩张 Engine/contracts。

## 实际变更

### Production

- `dayu/host/compaction_operation.py`
  - 新增私有 `_CompactionAttemptCancellationToken(parent)`。
  - 每个 semantic proposal attempt 创建全新 child；child 的 `request_cancel(...)` 只写本地 reason/time。
  - child 读取时 parent reason / requested-at 优先；局部状态用短临界区保护。
  - `_prepare_compactor_proposal()` 在 manifest recorder 返回后调用统一 `_ensure_compactor_proposal_active(...)`，失效时保留 manifest reference 并阻止 provider。
  - 非 prepared compactor 也在 provider await 前使用同一 helper，保持入口一致。

以下 allowed production 文件经证据确认无需修改：

- `dayu/host/llm_compaction.py`：既有 timeout signal 会对传入 request token 调 `request_cancel(...)`；传入对象现已由 operation owner 收窄为 attempt child。
- `dayu/host/dispatch.py`：既有 `_DurableRunCancellationToken` 已拥有 proactive Run status / input cursor re-read；新 pre-call check 直接复用它，不建立第二套 durable 判定。
- `dayu/host/engine_ingest.py`：reactive path 已传入 run-local parent；child wrapping 在 operation 内统一完成。

### Tests

- 新增 `tests/host/test_compaction_cancellation_scope.py`：
  - attempt 1 timeout、attempt 2 成功；
  - timeout 后 parent cancel 优先且不调用 repair provider；
  - provider 运行中 child 立即观察 parent reason/time；
  - caller task cancellation 透传；
  - manifest 后 parent 失效阻止 provider并保留 manifest ref。
- 更新 `tests/host/test_dispatch_scheduler.py`：真实 durable recorder 提交 manifest 后，以独立 write transaction 改变 Run status；断言 provider count 为 0、manifest fact 已提交、无 `CONTEXT_COMPACTED`。

### Docs

- `docs/host/design.md`：明确 attempt-local linked child、parent 优先、Engine public read-only cancellation、manifest commit 后 durable recheck 和 provider await 不持事务。
- `dayu/host/README.md`：按 Host 开发者稳定边界更新 compactor cancellation / pre-call recheck 机制。
- `tests/README.md`：记录新增 deterministic cancellation scope 与 durable manifest race 覆盖。

## 必须反例覆盖

1. **timeout 后 retry 成功**：`test_attempt_timeout_does_not_cancel_parent_or_next_attempt` 使用 `max_attempts=2`，首次 runner 抛 `TimeoutError`，第二次返回合法 proposal；断言两个不同 child、首次 child reason 为 `compactor_proposal_timeout`、第二 child fresh、parent 未取消、result accepted。
2. **parent cancel 优先**：`test_parent_cancel_after_timeout_wins_before_retry` 在 timeout signal 写 child 后同步取消 parent；断言 provider 仅调用一次、child 最终 reason/time 与 parent 相同、最终 reason 为 `cancellation_requested` 而非 timeout。
3. **运行中 parent cancel 与 caller cancel 分离**：
   - `test_parent_cancel_is_visible_to_running_attempt_child` 用 `asyncio.Event` barrier 证明 provider 运行中 child 立即读取相同 parent reason/time，并按 Host cancellation result 收口。
   - `test_outer_task_cancellation_is_not_reclassified` 证明外层 `Task.cancel()` 仍抛 `asyncio.CancelledError`，不写 parent、不伪装为 Host cancellation result。
4. **manifest-to-provider durable race**：
   - `test_manifest_post_write_recheck_blocks_provider_and_keeps_reference` 证明 recorder 返回后失效会保留 manifest ref 且 provider count=0。
   - `test_proactive_compaction_rechecks_durable_state_after_manifest` 使用真实 SQLite store / durable manifest recorder，在 manifest commit 后用独立事务改变 Run status；同一 `_DurableRunCancellationToken` 的 pre-call read 命中，provider count=0。
5. **正常 proactive path 不改变事件/schema、不跨事务 await**：既有 `test_proactive_compaction_calls_llm_outside_write_transaction` 继续通过，并在 provider 内成功开启独立 read transaction；正常 path 仍只写既有 manifest / compact facts。新增实现没有 schema、event type 或 payload shape 变更。

所有 race oracle 都由同步 hook 或 `asyncio.Event` barrier 驱动，没有使用 sleep / 概率时序作为正确性判断。

## 验证结果

### Required focused pytest

```text
source .venv/bin/activate
pytest tests/host/test_compaction_cancellation_scope.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q

307 passed in 2.45s
```

### Required pyright

```text
python -m pyright dayu/host/compaction_operation.py dayu/host/llm_compaction.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/

0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n "_signal_timeout_cancellation|request_cancel\(" dayu/host/llm_compaction.py dayu/host/compaction_operation.py
```

分类：

- `llm_compaction.py:122` 是 Host-private structural signal protocol 的方法声明。
- `llm_compaction.py:323,350,358` 是既有 timeout handler；它只对 prepared `AgentRunRequest` 中的 token 发 signal。
- `compaction_operation.py:625` 是唯一具体 attempt-local `request_cancel` owner；operation 在每次 provider attempt 前注入新的该类型实例。
- 无 parent token reset、无 Engine public writable protocol、无下游 fallback / compatibility shim。

```text
git diff --name-only -- dayu/engine/
```

结果：无输出，Engine scope 未修改。

```text
git diff --check
```

结果：无输出。

## README / design 触发判断

- 命中 `dayu/host/` 修改触发条件；linked cancellation 与 durable pre-call barrier 是 Host 关键执行机制，属于 `dayu/host/README.md` 的开发者稳定边界，因此已更新。
- 新增 / 修改 Host tests，且 `tests/README.md` 的 `tests/host/` 章节维护 suite 覆盖范围，因此已更新。
- accepted plan 已明确该 owner 契约，而 `docs/host/design.md` 原文只笼统要求每次外部调用前后 recheck；为消除 parent/child writable ownership 歧义并保持设计真源，已做窄范围更新。
- 未触发根 README、`dayu/README.md` 或 Engine README：没有用户入口、层级装配或 Engine contract 变化。

## Residual risk

- provider 的物理停止仍取决于 Engine/runner 对只读 cancellation token 的协作观察；本 slice 保证 timeout scope 与 Host durable acceptance 正确，不承诺远端 provider 已物理取消。这是既有取消契约和明确 non-goal，不是 S7 correctness blocker。
- 未发现未归属的 S7 residual risk。没有修改 compaction schema、quality policy、memory 语义或 Engine provider timeout 分类。

## 结论

S7 stop condition 未触发：timeout-to-success、parent cancellation precedence、manifest-to-provider durable race 均由 deterministic tests 通过；parent 未被 proposal timeout 污染，Engine diff 为空。

最终状态：`ready-for-code-review`。
